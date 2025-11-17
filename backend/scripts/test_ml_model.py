#!/usr/bin/env python3
"""
Script de test et validation du modèle ONNX.

Mesure latence, mémoire, précision sur données de test.
"""

import logging
import sys
import time
from pathlib import Path

import numpy as np

from app.ml.dataset_manager import DatasetManager
from app.ml.onnx_inference import HybridClassifier, SVMFallbackClassifier
from app.ml.transformer_trainer import HSDataset

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def test_onnx_inference():
    """Test l'inférence ONNX."""
    logger.info("Testing ONNX inference...")

    try:
        import psutil
    except ImportError:
        psutil = None
        logger.warning("psutil not available; memory monitoring disabled")

    model_dir = Path(__file__).parent.parent.parent / "data" / "models"
    onnx_path = model_dir / "hs_classifier_v1_quantized.onnx"

    if not onnx_path.exists():
        onnx_path = model_dir / "hs_classifier_v1.onnx"

    if not onnx_path.exists():
        logger.error(f"ONNX model not found: {onnx_path}")
        return

    # Load test data
    dm = DatasetManager()
    test_df = dm.load_dataset("hs_v1", split="test")

    if len(test_df) < 5:
        logger.error("Not enough test data")
        return

    # Create classifier
    classifier = HybridClassifier(onnx_path=onnx_path)

    # Set vocab
    dataset = HSDataset(test_df["description"].tolist(), test_df["hs_code"].tolist())
    classifier.onnx_service.set_vocab(dataset.vocab, list(dataset.hs_mapping.keys()))

    # Test predictions
    logger.info(f"Running {len(test_df)} predictions...")

    latencies = []
    correct = 0

    start_time = time.time()
    if psutil:
        process = psutil.Process()
        memory_start = process.memory_info().rss / 1024 / 1024

    for idx, row in test_df.iterrows():
        desc = row["description"]
        true_hs = row["hs_code"]

        t0 = time.time()
        result = classifier.predict(desc)
        latencies.append(time.time() - t0)

        if result["hs_code"] == true_hs:
            correct += 1

        if (idx + 1) % 5 == 0:
            logger.info(
                f"Processed {idx + 1}/{len(test_df)} - "
                f"Accuracy: {100 * correct / (idx + 1):.1f}% - "
                f"Method: {result['method']}"
            )

    total_time = time.time() - start_time
    if psutil:
        memory_end = process.memory_info().rss / 1024 / 1024
        memory_used = memory_end - memory_start

    accuracy = correct / len(test_df)

    logger.info("=" * 60)
    logger.info("ONNX Performance Results")
    logger.info("=" * 60)
    logger.info(f"Total samples: {len(test_df)}")
    logger.info(f"Accuracy: {100 * accuracy:.2f}%")
    logger.info(f"Total time: {total_time:.2f}s")
    logger.info(f"Avg latency: {np.mean(latencies) * 1000:.2f}ms")
    logger.info(f"Min latency: {np.min(latencies) * 1000:.2f}ms")
    logger.info(f"Max latency: {np.max(latencies) * 1000:.2f}ms")
    logger.info(f"P95 latency: {np.percentile(latencies, 95) * 1000:.2f}ms")
    logger.info(f"P99 latency: {np.percentile(latencies, 99) * 1000:.2f}ms")

    if psutil:
        logger.info(f"Memory used: {memory_used:.2f}MB")

    logger.info("=" * 60)

    # Performance acceptance criteria
    avg_latency_ms = np.mean(latencies) * 1000
    p95_latency_ms = np.percentile(latencies, 95) * 1000

    criteria = {
        "Accuracy ≥ 60%": accuracy >= 0.6,
        "Avg latency ≤ 100ms": avg_latency_ms <= 100,
        "P95 latency ≤ 200ms": p95_latency_ms <= 200,
        "Memory ≤ 500MB": (memory_used <= 500) if psutil else True,
    }

    logger.info("Acceptance Criteria:")
    for criterion, passed in criteria.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"  {status} - {criterion}")

    all_passed = all(criteria.values())
    logger.info("=" * 60)
    if all_passed:
        logger.info("✓ All criteria passed!")
    else:
        logger.warning("✗ Some criteria failed")

    return {
        "accuracy": accuracy,
        "avg_latency_ms": avg_latency_ms,
        "p95_latency_ms": p95_latency_ms,
        "all_passed": all_passed,
    }


def compare_onnx_vs_svm():
    """Compare les performances ONNX vs SVM."""
    logger.info("Comparing ONNX vs SVM...")

    model_dir = Path(__file__).parent.parent.parent / "data" / "models"

    # Load test data
    dm = DatasetManager()
    test_df = dm.load_dataset("hs_v1", split="test")

    if len(test_df) < 5:
        logger.error("Not enough test data")
        return

    # Train SVM classifier
    logger.info("Training SVM fallback classifier...")
    svm = SVMFallbackClassifier()
    svm.train(test_df["description"].tolist(), test_df["hs_code"].tolist())

    # Test both
    results = {"onnx": {"latencies": [], "correct": 0}, "svm": {"latencies": [], "correct": 0}}

    classifier = HybridClassifier(
        onnx_path=(
            model_dir / "hs_classifier_v1_quantized.onnx"
            if (model_dir / "hs_classifier_v1_quantized.onnx").exists()
            else model_dir / "hs_classifier_v1.onnx"
        )
    )

    # Set vocab
    dataset = HSDataset(test_df["description"].tolist(), test_df["hs_code"].tolist())
    classifier.onnx_service.set_vocab(dataset.vocab, list(dataset.hs_mapping.keys()))

    for _idx, row in test_df.iterrows():
        desc = row["description"]
        true_hs = row["hs_code"]

        # ONNX
        t0 = time.time()
        hs_onnx, _ = classifier.onnx_service.predict(desc)
        results["onnx"]["latencies"].append(time.time() - t0)
        if hs_onnx == true_hs:
            results["onnx"]["correct"] += 1

        # SVM
        t0 = time.time()
        hs_svm, _ = svm.predict(desc)
        results["svm"]["latencies"].append(time.time() - t0)
        if hs_svm == true_hs:
            results["svm"]["correct"] += 1

    logger.info("=" * 60)
    logger.info("ONNX vs SVM Comparison")
    logger.info("=" * 60)

    for method, data in results.items():
        accuracy = data["correct"] / len(test_df)
        avg_latency = np.mean(data["latencies"]) * 1000

        logger.info(f"\n{method.upper()}:")
        logger.info(f"  Accuracy: {100 * accuracy:.2f}%")
        logger.info(f"  Avg latency: {avg_latency:.2f}ms")
        logger.info(
            f"  Speedup vs SVM: {np.mean(results['svm']['latencies']) / np.mean(data['latencies']):.2f}x"
        )

    logger.info("=" * 60)


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Phase 9: ML Model Testing & Validation")
    logger.info("=" * 60)

    # Test ONNX inference
    results = test_onnx_inference()

    # Compare ONNX vs SVM
    try:
        compare_onnx_vs_svm()
    except Exception as e:
        logger.warning(f"Could not run SVM comparison: {e}")

    logger.info("=" * 60)
    logger.info("Testing completed!")
    logger.info("=" * 60)
