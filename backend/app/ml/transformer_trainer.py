"""
Pipeline d'entraînement transformer pour classification HS.

Entraîne un petit transformer avec attention, tokenization HS codes.
Export ONNX avec quantization post-entraînement.
"""

import logging
from pathlib import Path

import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset

logger = logging.getLogger(__name__)


class HSDataset(Dataset):
    """Dataset PyTorch pour descriptions et codes HS."""

    def __init__(self, descriptions: list[str], hs_codes: list[str], vocab_size: int = 5000):
        """
        Initialise le dataset.

        Args:
            descriptions: Descriptions des marchandises
            hs_codes: Codes HS correspondants
            vocab_size: Taille du vocabulaire
        """
        self.descriptions = descriptions
        self.hs_codes = hs_codes
        self.vocab_size = vocab_size

        # Construire le vocabulaire
        self.vocab = self._build_vocab(descriptions)

        # Encoder les codes HS (mapping)
        self.hs_mapping = {code: i for i, code in enumerate(sorted(set(hs_codes)))}
        self.num_classes = len(self.hs_mapping)

    def _build_vocab(self, texts: list[str]) -> dict:
        """Construit un vocabulaire simple."""
        vocab = {"<PAD>": 0, "<UNK>": 1}
        idx = 2

        for text in texts:
            for word in text.lower().split():
                word = "".join(c for c in word if c.isalnum())
                if word and word not in vocab and idx < self.vocab_size:
                    vocab[word] = idx
                    idx += 1

        return vocab

    def encode_text(self, text: str, max_len: int = 50) -> list:
        """Encode un texte en indices."""
        tokens = text.lower().split()[:max_len]
        encoded = [self.vocab.get("".join(c for c in word if c.isalnum()), 1) for word in tokens]

        # Padding
        encoded += [0] * (max_len - len(encoded))
        return encoded[:max_len]

    def __len__(self):
        return len(self.descriptions)

    def __getitem__(self, idx):
        desc = self.descriptions[idx]
        hs_code = self.hs_codes[idx]

        encoded_desc = torch.tensor(self.encode_text(desc), dtype=torch.long)
        hs_label = torch.tensor(self.hs_mapping[hs_code], dtype=torch.long)

        return encoded_desc, hs_label


class MiniTransformer(nn.Module):
    """Mini-transformer pour classification HS (léger pour ONNX)."""

    def __init__(
        self,
        vocab_size: int = 5000,
        num_classes: int = 100,
        hidden_dim: int = 128,
        num_heads: int = 4,
        num_layers: int = 2,
    ):
        """
        Initialise le mini-transformer.

        Args:
            vocab_size: Taille du vocabulaire
            num_classes: Nombre de codes HS possibles
            hidden_dim: Dimension cachée
            num_heads: Nombre de heads attention
            num_layers: Nombre de layers transformer
        """
        super().__init__()

        self.embedding = nn.Embedding(vocab_size, hidden_dim, padding_idx=0)
        self.pos_encoding = nn.Embedding(50, hidden_dim)  # Max sequence length = 50

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=256,
            batch_first=True,
            dropout=0.1,
        )

        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        self.pool = nn.AdaptiveAvgPool1d(1)
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, num_classes),
        )

    def forward(self, input_ids):
        # Embedding
        embeddings = self.embedding(input_ids)

        # Position encoding
        seq_len = input_ids.shape[1]
        pos_ids = torch.arange(seq_len, device=input_ids.device).unsqueeze(0)
        pos_embeddings = self.pos_encoding(pos_ids)

        embeddings = embeddings + pos_embeddings

        # Mask pour padding
        padding_mask = input_ids == 0

        # Transformer
        transformed = self.transformer(embeddings, src_key_padding_mask=padding_mask)

        # Pooling
        pooled = transformed.mean(dim=1)  # Average pooling

        # Classification
        logits = self.classifier(pooled)

        return logits


class TransformerTrainer:
    """Entraîne un transformer pour classification HS."""

    def __init__(self, model_dir: Path = None):
        """
        Initialise le trainer.

        Args:
            model_dir: Répertoire pour sauvegarder les modèles
        """
        if model_dir is None:
            backend_dir = Path(__file__).parent.parent.parent
            model_dir = backend_dir.parent / "data" / "models"

        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Using device: {self.device}")

    def train(
        self,
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        epochs: int = 10,
        batch_size: int = 32,
        lr: float = 1e-3,
    ) -> tuple[nn.Module, dict]:
        """
        Entraîne un transformer.

        Args:
            train_df: DataFrame d'entraînement avec colonnes ['description', 'hs_code']
            val_df: DataFrame de validation
            epochs: Nombre d'epochs
            batch_size: Taille des batches
            lr: Learning rate

        Returns:
            (modèle entraîné, métriques)
        """
        try:
            logger.info(f"Training transformer: {len(train_df)} samples")

            # Datasets
            train_dataset = HSDataset(
                train_df["description"].tolist(), train_df["hs_code"].tolist()
            )

            val_dataset = HSDataset(val_df["description"].tolist(), val_df["hs_code"].tolist())

            train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
            val_loader = DataLoader(val_dataset, batch_size=batch_size)

            # Modèle
            model = MiniTransformer(
                vocab_size=len(train_dataset.vocab),
                num_classes=train_dataset.num_classes,
                hidden_dim=128,
                num_heads=4,
                num_layers=2,
            ).to(self.device)

            # Optimizer et loss
            optimizer = optim.Adam(model.parameters(), lr=lr)
            criterion = nn.CrossEntropyLoss()

            # Entraînement
            metrics = {"train_loss": [], "val_accuracy": [], "val_loss": []}

            for epoch in range(epochs):
                # Train
                model.train()
                train_loss = 0
                for _batch_idx, (inputs, targets) in enumerate(train_loader):
                    inputs, targets = inputs.to(self.device), targets.to(self.device)

                    optimizer.zero_grad()
                    outputs = model(inputs)
                    loss = criterion(outputs, targets)
                    loss.backward()
                    optimizer.step()

                    train_loss += loss.item()

                avg_train_loss = train_loss / len(train_loader)
                metrics["train_loss"].append(avg_train_loss)

                # Validation
                model.eval()
                val_loss = 0
                correct = 0
                total = 0

                with torch.no_grad():
                    for inputs, targets in val_loader:
                        inputs, targets = inputs.to(self.device), targets.to(self.device)

                        outputs = model(inputs)
                        loss = criterion(outputs, targets)
                        val_loss += loss.item()

                        _, predicted = torch.max(outputs, 1)
                        correct += (predicted == targets).sum().item()
                        total += targets.size(0)

                avg_val_loss = val_loss / len(val_loader)
                val_accuracy = correct / total

                metrics["val_loss"].append(avg_val_loss)
                metrics["val_accuracy"].append(val_accuracy)

                logger.info(
                    f"Epoch {epoch+1}/{epochs}: "
                    f"train_loss={avg_train_loss:.4f}, "
                    f"val_loss={avg_val_loss:.4f}, "
                    f"val_acc={val_accuracy:.4f}"
                )

            return model, metrics

        except Exception as e:
            logger.error(f"Error training transformer: {e}")
            raise

    def save_model(self, model: nn.Module, name: str):
        """Sauvegarde le modèle PyTorch."""
        model_path = self.model_dir / f"{name}.pth"
        torch.save(model.state_dict(), model_path)
        logger.info(f"Saved model: {model_path}")

    def export_onnx(
        self,
        model: nn.Module,
        vocab_size: int,
        output_name: str = "hs_classifier",
    ) -> Path:
        """
        Exporte le modèle en ONNX.

        Args:
            model: Modèle PyTorch
            vocab_size: Taille du vocabulaire
            output_name: Nom du fichier ONNX

        Returns:
            Chemin du fichier ONNX
        """
        try:
            model.eval()

            # Dummy input
            dummy_input = torch.randint(0, vocab_size, (1, 50))

            onnx_path = self.model_dir / f"{output_name}.onnx"

            torch.onnx.export(
                model,
                dummy_input,
                str(onnx_path),
                input_names=["input_ids"],
                output_names=["logits"],
                opset_version=12,
                do_constant_folding=True,
            )

            logger.info(f"Exported ONNX model: {onnx_path}")
            return onnx_path

        except Exception as e:
            logger.error(f"Error exporting ONNX: {e}")
            raise
