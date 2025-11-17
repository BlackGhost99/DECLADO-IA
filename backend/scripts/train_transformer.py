#!/usr/bin/env python3
"""
Script d'entraînement du transformer pour classification HS.

Collect annotations → Create dataset → Train transformer → Export ONNX
"""

import logging
import sys
from pathlib import Path

from app.ml.dataset_manager import AnnotatedHS, DatasetManager
from app.ml.mlflow_tracker import MLflowTracker
from app.ml.transformer_trainer import TransformerTrainer

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def create_sample_dataset():
    """Crée un dataset de sample annotations."""
    logger.info("Creating sample dataset...")

    dm = DatasetManager()

    # Sample data
    samples = [
        ("T-shirts en coton, taille M", "6109"),
        ("Chemises formelles, coton pur", "6105"),
        ("Pantalons en denim bleu", "6204"),
        ("Robes de soirée, polyester", "6204"),
        ("Vestes en laine pour hommes", "6203"),
        ("Chaussures de sport en cuir", "6402"),
        ("Chaussures de travail imperméables", "6402"),
        ("Bottes de pluie en caoutchouc", "6401"),
        ("Chapeaux en feutre naturel", "6501"),
        ("Casquettes de baseball en coton", "6505"),
        ("Sacs à main en cuir véritable", "4202"),
        ("Sacs à dos en nylon résistant", "4202"),
        ("Ceintures en cuir pour hommes", "4203"),
        ("Portefeuilles en cuir italien", "4205"),
        ("Gants en cuir de chèvre", "4203"),
        ("Écharpes en soie pure", "6214"),
        ("Foulards imprimés multicolores", "6214"),
        ("Cravates en soie de haute qualité", "6211"),
        ("Chemises de nuit en satin", "6207"),
        ("Costumes complets trois pièces", "6203"),
        ("Blazers de sport en coton mélangé", "6203"),
        ("Jupes plissées en laine", "6204"),
        ("Leggings de sport en lycra", "6203"),
        ("Pulls en laine mérinos fine", "6110"),
        ("Cardigans en coton léger", "6110"),
        ("Sweatshirts en polyester épais", "6109"),
        ("Pyjamas en coton organique", "6207"),
        ("Sous-vêtements thermiques en laine", "6108"),
        ("Bas de compression médicaux", "6115"),
        ("Chaussettes en bambou antibactérien", "6115"),
    ]

    # Collect annotations
    for desc, hs_code in samples:
        annotation = AnnotatedHS(
            description=desc,
            hs_code=hs_code,
            confidence=1.0,
            annotator="training_script",
        )
        dm.collect_annotation(annotation, source="training")

    logger.info(f"Collected {len(samples)} annotations")

    # Create dataset
    metadata = dm.create_dataset("hs_v1", split_ratios=(0.7, 0.15, 0.15))

    if metadata:
        logger.info(f"Dataset created: {metadata}")

    return dm


def train_transformer():
    """Entraîne le transformer."""
    logger.info("Training transformer...")

    dm = DatasetManager()
    trainer = TransformerTrainer()
    tracker = MLflowTracker()

    # Load dataset
    train_df = dm.load_dataset("hs_v1", split="train")
    val_df = dm.load_dataset("hs_v1", split="val")

    if len(train_df) < 5:
        logger.error("Not enough training data")
        return None

    # Start MLflow experiment
    params = {
        "model": "MiniTransformer",
        "hidden_dim": 128,
        "num_heads": 4,
        "num_layers": 2,
        "batch_size": 8,
        "epochs": 5,
        "learning_rate": 0.001,
    }

    run_dir = tracker.start_experiment("hs_transformer_v1", params)

    # Train
    model, metrics = trainer.train(
        train_df, val_df, epochs=params["epochs"], batch_size=params["batch_size"]
    )

    # Log metrics
    for i in range(len(metrics["train_loss"])):
        tracker.log_metrics(
            run_dir,
            {
                "train_loss": metrics["train_loss"][i],
                "val_loss": metrics["val_loss"][i],
                "val_accuracy": metrics["val_accuracy"][i],
            },
            step=i,
        )

    # Save PyTorch model
    trainer.save_model(model, "hs_transformer_v1")

    # Export ONNX
    onnx_path = trainer.export_onnx(model, len(train_df), output_name="hs_classifier_v1")

    # Log artifacts
    tracker.log_artifact(run_dir, trainer.model_dir / "hs_transformer_v1.pth", "model.pth")
    tracker.log_artifact(run_dir, onnx_path, "model.onnx")

    tracker.end_experiment(run_dir, status="success")

    logger.info("Training completed!")
    logger.info(f"Model saved: {trainer.model_dir / 'hs_transformer_v1.pth'}")
    logger.info(f"ONNX saved: {onnx_path}")

    return model


def quantize_onnx():
    """Quantize le modèle ONNX pour réduire la latence/mémoire."""
    logger.info("Quantizing ONNX model...")

    try:
        from onnxruntime.quantization import QuantType, quantize_dynamic

        model_dir = Path(__file__).parent.parent.parent / "data" / "models"
        onnx_path = model_dir / "hs_classifier_v1.onnx"
        quantized_path = model_dir / "hs_classifier_v1_quantized.onnx"

        if not onnx_path.exists():
            logger.error(f"Model not found: {onnx_path}")
            return None

        quantize_dynamic(
            str(onnx_path),
            str(quantized_path),
            weight_type=QuantType.QUInt8,
        )

        logger.info(f"Quantized model saved: {quantized_path}")

        # Compare file sizes
        original_size = onnx_path.stat().st_size / 1024 / 1024
        quantized_size = quantized_path.stat().st_size / 1024 / 1024

        logger.info(f"Original size: {original_size:.2f} MB")
        logger.info(f"Quantized size: {quantized_size:.2f} MB")
        logger.info(f"Compression ratio: {original_size / quantized_size:.2f}x")

        return quantized_path

    except ImportError:
        logger.warning("onnxruntime[tools] not available; skipping quantization")
        return None
    except Exception as e:
        logger.error(f"Error quantizing ONNX: {e}")
        return None


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Phase 9: ML Transformer Training Pipeline")
    logger.info("=" * 60)

    # Step 1: Create sample dataset
    create_sample_dataset()

    # Step 2: Train transformer
    model = train_transformer()

    # Step 3: Quantize ONNX
    if model:
        quantize_onnx()

    logger.info("=" * 60)
    logger.info("Pipeline completed!")
    logger.info("=" * 60)
