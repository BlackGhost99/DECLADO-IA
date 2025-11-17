"""
Configuration et tracking MLflow pour l'entraînement de modèles.

Intégration MLflow pour suivi expériences, métriques, et artefacts.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class MLflowTracker:
    """Tracker pour expériences MLflow."""

    def __init__(self, tracking_dir: Path = None):
        """
        Initialise le tracker MLflow.

        Args:
            tracking_dir: Répertoire pour les logs MLflow
        """
        if tracking_dir is None:
            backend_dir = Path(__file__).parent.parent.parent
            tracking_dir = backend_dir.parent / "data" / "mlflow"

        self.tracking_dir = Path(tracking_dir)
        self.tracking_dir.mkdir(parents=True, exist_ok=True)

        # Configuration MLflow
        self.mlflow_uri = f"file://{self.tracking_dir.resolve()}"

        logger.info(f"MLflowTracker initialized: {self.mlflow_uri}")

    def start_experiment(self, experiment_name: str, params: dict) -> str:
        """
        Démarre une expérience MLflow.

        Args:
            experiment_name: Nom de l'expérience
            params: Paramètres de l'expérience

        Returns:
            ID de l'expérience
        """
        try:
            # Créer un dossier pour l'expérience
            exp_dir = self.tracking_dir / experiment_name
            exp_dir.mkdir(exist_ok=True)

            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = exp_dir / run_id

            run_dir.mkdir(exist_ok=True)

            # Sauvegarder les paramètres
            with open(run_dir / "params.json", "w") as f:
                json.dump(params, f, indent=2)

            logger.info(f"Started experiment: {experiment_name} (run_id={run_id})")

            return str(run_dir)

        except Exception as e:
            logger.error(f"Error starting experiment: {e}")
            return None

    def log_metrics(self, run_dir: str, metrics: dict, step: int = 0):
        """
        Enregistre des métriques.

        Args:
            run_dir: Répertoire du run
            metrics: Dictionnaire des métriques
            step: Étape/époque
        """
        try:
            run_path = Path(run_dir)
            metrics_file = run_path / "metrics.jsonl"

            entry = {"step": step, "timestamp": datetime.now().isoformat(), **metrics}

            with open(metrics_file, "a") as f:
                f.write(json.dumps(entry) + "\n")

            logger.debug(f"Logged metrics for step {step}: {metrics}")

        except Exception as e:
            logger.error(f"Error logging metrics: {e}")

    def log_artifact(self, run_dir: str, artifact_path: Path, artifact_name: str):
        """
        Enregistre un artefact (modèle, fichier, etc.).

        Args:
            run_dir: Répertoire du run
            artifact_path: Chemin du fichier
            artifact_name: Nom de l'artefact
        """
        try:
            import shutil

            run_path = Path(run_dir)
            artifacts_dir = run_path / "artifacts"
            artifacts_dir.mkdir(exist_ok=True)

            if artifact_path.is_file():
                dest = artifacts_dir / artifact_name
                shutil.copy2(artifact_path, dest)
            else:
                dest = artifacts_dir / artifact_name
                shutil.copytree(artifact_path, dest, dirs_exist_ok=True)

            logger.info(f"Logged artifact: {artifact_name}")

        except Exception as e:
            logger.error(f"Error logging artifact: {e}")

    def end_experiment(self, run_dir: str, status: str = "success"):
        """
        Termine une expérience.

        Args:
            run_dir: Répertoire du run
            status: 'success' ou 'failed'
        """
        try:
            run_path = Path(run_dir)

            metadata = {
                "status": status,
                "end_time": datetime.now().isoformat(),
            }

            with open(run_path / "metadata.json", "w") as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"Ended experiment: {run_dir} ({status})")

        except Exception as e:
            logger.error(f"Error ending experiment: {e}")

    def get_best_run(self, experiment_name: str, metric_name: str = "accuracy") -> dict | None:
        """
        Récupère le meilleur run d'une expérience.

        Args:
            experiment_name: Nom de l'expérience
            metric_name: Métrique à optimiser

        Returns:
            Métadonnées du meilleur run
        """
        try:
            exp_dir = self.tracking_dir / experiment_name
            if not exp_dir.exists():
                return None

            best_run = None
            best_metric = -float("inf")

            for run_dir in exp_dir.iterdir():
                if not run_dir.is_dir():
                    continue

                metrics_file = run_dir / "metrics.jsonl"
                if not metrics_file.exists():
                    continue

                with open(metrics_file) as f:
                    last_line = None
                    for line in f:
                        last_line = line

                    if last_line:
                        metrics = json.loads(last_line)
                        if metric_name in metrics:
                            value = metrics[metric_name]
                            if value > best_metric:
                                best_metric = value
                                best_run = {
                                    "run_dir": str(run_dir),
                                    "metric_value": value,
                                    "metrics": metrics,
                                }

            return best_run

        except Exception as e:
            logger.error(f"Error getting best run: {e}")
            return None
