"""
Unit tests for ML Pipeline
Phase 10: Tests, QA et Performance - ML Components
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.ml.config import (
    BATCH_SIZE,
    MAX_SEQ_LEN,
    MIN_ANNOTATION_CONFIDENCE,
    MODEL_DIR,
    ONNX_QUANT_MODEL,
    VOCAB_SIZE,
)

# ============================================================================
# ML Config Tests
# ============================================================================


@pytest.mark.unit
@pytest.mark.ml
def test_ml_config_constants():
    """Test ML configuration constants are properly set."""
    assert VOCAB_SIZE == 5000, "Vocabulary size should be 5000"
    assert MAX_SEQ_LEN == 128, "Max sequence length should be 128"
    assert BATCH_SIZE == 16, "Batch size should be 16"
    assert MIN_ANNOTATION_CONFIDENCE >= 0.0 and MIN_ANNOTATION_CONFIDENCE <= 1.0
    assert isinstance(MODEL_DIR, str)
    assert ONNX_QUANT_MODEL.endswith(".onnx")


# ============================================================================
# DatasetManager Tests
# ============================================================================


@pytest.mark.unit
@pytest.mark.ml
def test_dataset_manager_initialization(sample_training_data):
    """Test DatasetManager can load CSV data."""
    from app.ml.dataset_manager import DatasetManager

    dm = DatasetManager(csv_path=sample_training_data)
    assert dm.csv_path == sample_training_data
    assert dm.df is None  # Not loaded yet


@pytest.mark.unit
@pytest.mark.ml
def test_dataset_manager_load_csv(sample_training_data):
    """Test CSV loading and validation."""
    from app.ml.dataset_manager import DatasetManager

    dm = DatasetManager(csv_path=sample_training_data)
    dm.load_csv()

    assert dm.df is not None
    assert len(dm.df) > 0
    assert "hs_code" in dm.df.columns
    assert "description" in dm.df.columns


@pytest.mark.unit
@pytest.mark.ml
def test_dataset_manager_train_val_test_split(sample_training_data):
    """Test dataset splitting into train/val/test."""
    from app.ml.dataset_manager import DatasetManager

    dm = DatasetManager(csv_path=sample_training_data)
    dm.load_csv()
    dm.prepare_splits(train_ratio=0.7, val_ratio=0.15, test_ratio=0.15)

    assert dm.train_df is not None
    assert dm.val_df is not None
    assert dm.test_df is not None

    # Check splits add up to original
    total_split = len(dm.train_df) + len(dm.val_df) + len(dm.test_df)
    assert total_split == len(dm.df)


# ============================================================================
# TransformerTrainer Tests
# ============================================================================


@pytest.mark.unit
@pytest.mark.ml
@pytest.mark.slow
def test_transformer_trainer_initialization():
    """Test TransformerTrainer can be instantiated."""
    from app.ml.transformer_trainer import TransformerTrainer

    trainer = TransformerTrainer(
        vocab_size=VOCAB_SIZE, max_seq_len=MAX_SEQ_LEN, num_classes=10, device="cpu"
    )

    assert trainer.vocab_size == VOCAB_SIZE
    assert trainer.max_seq_len == MAX_SEQ_LEN
    assert trainer.num_classes == 10
    assert trainer.device == "cpu"


@pytest.mark.unit
@pytest.mark.ml
def test_transformer_vocab_building(sample_training_data):
    """Test vocabulary building from training texts."""
    from app.ml.dataset_manager import DatasetManager
    from app.ml.transformer_trainer import TransformerTrainer

    dm = DatasetManager(csv_path=sample_training_data)
    dm.load_csv()
    texts = dm.df["description"].tolist()

    trainer = TransformerTrainer(
        vocab_size=100, max_seq_len=32, num_classes=10, device="cpu"  # Small for testing
    )

    trainer.build_vocab(texts)
    assert trainer.tokenizer is not None
    assert len(trainer.tokenizer.word_index) <= 100


# ============================================================================
# ONNXInferenceService Tests
# ============================================================================


@pytest.mark.unit
@pytest.mark.ml
def test_onnx_service_initialization():
    """Test ONNXInferenceService initialization."""
    from app.ml.onnx_inference import ONNXInferenceService

    service = ONNXInferenceService(onnx_path="dummy.onnx", fallback_to_svm=True)

    assert service.onnx_path == "dummy.onnx"
    assert service.fallback_to_svm is True
    assert service.session is None  # Not loaded yet


@pytest.mark.unit
@pytest.mark.ml
def test_onnx_service_fallback_svm():
    """Test SVM fallback when ONNX unavailable."""
    from app.ml.onnx_inference import ONNXInferenceService

    service = ONNXInferenceService(onnx_path="nonexistent_model.onnx", fallback_to_svm=True)

    # Should not raise even if ONNX missing
    result = service.predict_topk(["test description"], k=3)
    assert isinstance(result, list)


# ============================================================================
# MLflowTracker Tests
# ============================================================================


@pytest.mark.unit
@pytest.mark.ml
@pytest.mark.requires_mlflow
def test_mlflow_tracker_initialization():
    """Test MLflowTracker setup."""
    from app.ml.mlflow_tracker import MLflowTracker

    tracker = MLflowTracker(
        experiment_name="test_experiment", tracking_uri=None  # Local filesystem
    )

    assert tracker.experiment_name == "test_experiment"


@pytest.mark.unit
@pytest.mark.ml
def test_mlflow_log_params_mock():
    """Test MLflow parameter logging with mock."""
    from app.ml.mlflow_tracker import MLflowTracker

    with patch("app.ml.mlflow_tracker.mlflow") as mock_mlflow:
        tracker = MLflowTracker(experiment_name="test")
        tracker.start_run()
        tracker.log_params({"learning_rate": 0.001, "batch_size": 16})

        # Verify mlflow.log_param was called
        assert mock_mlflow.log_param.call_count >= 1


# ============================================================================
# HS Classifier Service Tests
# ============================================================================


@pytest.mark.unit
@pytest.mark.ml
def test_hs_classifier_service_singleton():
    """Test HSClassifierService singleton pattern."""
    from app.ml.hs_classifier_service import get_classifier_service

    service1 = get_classifier_service()
    service2 = get_classifier_service()

    assert service1 is service2, "Should return same instance"


@pytest.mark.unit
@pytest.mark.ml
def test_hs_classifier_suggest_basic():
    """Test basic HS code suggestion."""
    from app.ml.hs_classifier_service import get_classifier_service

    service = get_classifier_service()
    results = service.suggest_hs_code("t-shirt en coton", top_k=3)

    assert isinstance(results, list)
    assert len(results) <= 3

    # Check structure
    if len(results) > 0:
        assert "code" in results[0]
        assert "confidence" in results[0]
        assert "description" in results[0]


@pytest.mark.unit
@pytest.mark.ml
def test_hs_classifier_empty_input():
    """Test HS classifier with empty input."""
    from app.ml.hs_classifier_service import get_classifier_service

    service = get_classifier_service()
    results = service.suggest_hs_code("", top_k=3)

    # Should handle gracefully
    assert isinstance(results, list)


# ============================================================================
# Integration: Full Pipeline
# ============================================================================


@pytest.mark.integration
@pytest.mark.ml
@pytest.mark.slow
def test_ml_pipeline_train_to_inference(sample_training_data, tmp_path):
    """
    Integration test: Train model → Export ONNX → Inference

    This simulates the complete ML workflow.
    """
    from app.ml.dataset_manager import DatasetManager
    from app.ml.onnx_inference import ONNXInferenceService
    from app.ml.transformer_trainer import TransformerTrainer

    # 1. Load data
    dm = DatasetManager(csv_path=sample_training_data)
    dm.load_csv()
    dm.prepare_splits(train_ratio=0.8, val_ratio=0.1, test_ratio=0.1)

    # 2. Build vocab
    trainer = TransformerTrainer(
        vocab_size=50,  # Small for test speed
        max_seq_len=16,
        num_classes=len(dm.df["hs_code"].unique()),
        device="cpu",
    )
    trainer.build_vocab(dm.train_df["description"].tolist())

    # 3. Export mock ONNX (skip actual training for speed)
    onnx_path = tmp_path / "test_model.onnx"
    # Normally: trainer.export_onnx(str(onnx_path))
    # For test: create dummy file
    onnx_path.write_bytes(b"DUMMY_ONNX")

    # 4. Test inference service
    service = ONNXInferenceService(onnx_path=str(onnx_path), fallback_to_svm=True)

    # Should fall back to SVM since ONNX is dummy
    predictions = service.predict_topk(["test product"], k=2)
    assert isinstance(predictions, list)


# ============================================================================
# Performance Tests
# ============================================================================


@pytest.mark.performance
@pytest.mark.ml
def test_ml_inference_latency(performance_logger):
    """Test ML inference latency is acceptable."""
    from app.ml.hs_classifier_service import get_classifier_service

    service = get_classifier_service()
    test_descriptions = [
        "smartphone android",
        "chaussures en cuir",
        "robe femme coton",
    ]

    # Warm-up
    service.suggest_hs_code(test_descriptions[0], top_k=3)

    # Measure
    performance_logger.start("ml_inference")
    for desc in test_descriptions:
        service.suggest_hs_code(desc, top_k=3)
    performance_logger.end("ml_inference")

    avg_latency = performance_logger.get_duration("ml_inference") / len(test_descriptions)
    performance_logger.report()

    # Should be under 100ms per inference
    assert avg_latency < 0.1, f"Average latency {avg_latency*1000:.2f}ms exceeds 100ms threshold"


@pytest.mark.performance
@pytest.mark.ml
def test_ml_batch_processing_throughput(performance_logger):
    """Test batch processing throughput."""
    from app.ml.hs_classifier_service import get_classifier_service

    service = get_classifier_service()
    batch = ["produit test " + str(i) for i in range(200)]

    performance_logger.start("batch_200")
    for item in batch:
        service.suggest_hs_code(item, top_k=1)
    performance_logger.end("batch_200")

    duration = performance_logger.get_duration("batch_200")
    throughput = len(batch) / duration

    performance_logger.report()
    print(f"📊 Throughput: {throughput:.2f} items/sec")

    # Should process at least 10 items/second
    assert throughput >= 10, f"Throughput {throughput:.2f} items/sec below 10 items/sec target"
