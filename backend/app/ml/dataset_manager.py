"""
Gestionnaire de dataset pour entraînement ML.

Collecte, versioning, et préparation des données d'entraînement.
Intégration avec DVC pour versioning des datasets.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AnnotatedHS(BaseModel):
    """Exemple d'entraînement annoté avec HS code."""

    description: str  # Description de la marchandise
    hs_code: str  # Code HS correct (4-10 chiffres)
    origin_country: Optional[str] = None  # Pays d'origine
    confidence: float = 1.0  # Confiance de l'annotation (0-1)
    annotator: str = "system"  # Qui a annoté
    timestamp: datetime = None  # Quand annoté


class DatasetManager:
    """Gère la collecte, versioning, et préparation des datasets."""

    def __init__(self, data_dir: Path = None):
        """
        Initialise le gestionnaire de dataset.

        Args:
            data_dir: Répertoire de base pour les données
        """
        if data_dir is None:
            backend_dir = Path(__file__).parent.parent.parent
            data_dir = backend_dir.parent / "data" / "ml"

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.annotations_dir = self.data_dir / "annotations"
        self.annotations_dir.mkdir(exist_ok=True)

        self.datasets_dir = self.data_dir / "datasets"
        self.datasets_dir.mkdir(exist_ok=True)

        logger.info(f"DatasetManager initialized: {self.data_dir}")

    def collect_annotation(self, annotation: AnnotatedHS, source: str = "user") -> bool:
        """
        Collecte une annotation utilisateur.

        Args:
            annotation: Annotation avec HS code correct
            source: Source de l'annotation (user, system, external, etc.)

        Returns:
            True si succès
        """
        try:
            if annotation.timestamp is None:
                annotation.timestamp = datetime.now()

            # Fichier JSONL pour annotations (append-only)
            annotations_file = self.annotations_dir / f"annotations_{source}.jsonl"

            with open(annotations_file, "a", encoding="utf-8") as f:
                f.write(annotation.model_dump_json() + "\n")

            logger.info(
                f"Collected annotation: {annotation.description[:50]}... → {annotation.hs_code}"
            )
            return True

        except Exception as e:
            logger.error(f"Error collecting annotation: {e}")
            return False

    def load_annotations(
        self, source: Optional[str] = None, min_confidence: float = 0.5
    ) -> List[AnnotatedHS]:
        """
        Charge les annotations collectées.

        Args:
            source: Filtrer par source (user, system, etc.)
            min_confidence: Confiance minimale

        Returns:
            Liste des annotations
        """
        annotations = []

        try:
            if source:
                files = [self.annotations_dir / f"annotations_{source}.jsonl"]
            else:
                files = list(self.annotations_dir.glob("annotations_*.jsonl"))

            for file in files:
                if not file.exists():
                    continue

                with open(file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            data = json.loads(line)
                            ann = AnnotatedHS(**data)
                            if ann.confidence >= min_confidence:
                                annotations.append(ann)
                        except Exception as e:
                            logger.warning(f"Error parsing annotation: {e}")

            logger.info(f"Loaded {len(annotations)} annotations")
            return annotations

        except Exception as e:
            logger.error(f"Error loading annotations: {e}")
            return []

    def create_dataset(
        self, name: str, split_ratios: Tuple[float, float, float] = (0.7, 0.15, 0.15)
    ) -> dict:
        """
        Crée un dataset versioning avec splits train/val/test.

        Args:
            name: Nom du dataset
            split_ratios: (train, validation, test) ratios

        Returns:
            Métadonnées du dataset
        """
        try:
            annotations = self.load_annotations()

            if len(annotations) < 10:
                logger.warning(f"Not enough annotations ({len(annotations)}) to create dataset")
                return None

            # Convertir en DataFrame
            data = [
                {
                    "description": ann.description,
                    "hs_code": ann.hs_code,
                    "origin_country": ann.origin_country or "UNKNOWN",
                    "confidence": ann.confidence,
                }
                for ann in annotations
            ]

            df = pd.DataFrame(data)

            # Splits
            n = len(df)
            train_idx = int(n * split_ratios[0])
            val_idx = train_idx + int(n * split_ratios[1])

            train_df = df[:train_idx]
            val_df = df[train_idx:val_idx]
            test_df = df[val_idx:]

            # Sauvegarder les datasets
            dataset_dir = self.datasets_dir / name
            dataset_dir.mkdir(exist_ok=True)

            train_df.to_csv(dataset_dir / "train.csv", index=False)
            val_df.to_csv(dataset_dir / "val.csv", index=False)
            test_df.to_csv(dataset_dir / "test.csv", index=False)

            metadata = {
                "name": name,
                "created": datetime.now().isoformat(),
                "total_samples": len(df),
                "train_samples": len(train_df),
                "val_samples": len(val_df),
                "test_samples": len(test_df),
                "unique_hs_codes": df["hs_code"].nunique(),
                "split_ratios": split_ratios,
            }

            with open(dataset_dir / "metadata.json", "w") as f:
                json.dump(metadata, f, indent=2)

            logger.info(
                f"Created dataset '{name}': "
                f"train={len(train_df)}, val={len(val_df)}, test={len(test_df)}"
            )

            return metadata

        except Exception as e:
            logger.error(f"Error creating dataset: {e}")
            return None

    def load_dataset(self, name: str, split: str = "train") -> pd.DataFrame:
        """
        Charge un dataset.

        Args:
            name: Nom du dataset
            split: 'train', 'val', ou 'test'

        Returns:
            DataFrame du split
        """
        try:
            dataset_dir = self.datasets_dir / name
            file = dataset_dir / f"{split}.csv"

            if not file.exists():
                logger.error(f"Dataset not found: {file}")
                return pd.DataFrame()

            return pd.read_csv(file)

        except Exception as e:
            logger.error(f"Error loading dataset: {e}")
            return pd.DataFrame()

    def get_dataset_stats(self, name: str) -> dict:
        """
        Retourne les statistiques du dataset.

        Args:
            name: Nom du dataset

        Returns:
            Statistiques
        """
        try:
            dataset_dir = self.datasets_dir / name
            metadata_file = dataset_dir / "metadata.json"

            if metadata_file.exists():
                with open(metadata_file) as f:
                    return json.load(f)

            return {}

        except Exception as e:
            logger.error(f"Error getting dataset stats: {e}")
            return {}
