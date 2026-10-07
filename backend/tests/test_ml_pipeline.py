"""
Unit tests for the ML pipeline (app/ml).

Covers config, DatasetManager, MLflowTracker (file based), ONNX inference with
SVM fallback, HSClassifierService and the PyTorch transformer trainer.

Heavy dependencies are never exercised for real:
- onnxruntime sessions are replaced by a tiny fake session (except one test that
  feeds an invalid file to the real runtime to check the error path);
- torch is not a backend requirement, so transformer_trainer is loaded against a
  small numpy-backed fake ``torch`` package injected through ``sys.modules``;
- no model download, no network, no MLflow server.

All filesystem activity happens under ``tmp_path``.
"""

import contextlib
import importlib.util
import json
import math
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import app.ml.config as ml_config
import app.ml.dataset_manager as dataset_manager
import app.ml.hs_classifier_service as hs_service
import app.ml.mlflow_tracker as mlflow_tracker
import app.ml.onnx_inference as onnx_inference
from app.ml.dataset_manager import AnnotatedHS, DatasetManager
from app.ml.hs_classifier_service import HSClassifierService, get_classifier_service
from app.ml.mlflow_tracker import MLflowTracker
from app.ml.onnx_inference import (
    HybridClassifier,
    ONNXInferenceService,
    SVMFallbackClassifier,
)

pytestmark = [pytest.mark.unit, pytest.mark.ml]

ML_DIR = Path(ml_config.__file__).resolve().parent


# ============================================================================
# Helpers
# ============================================================================


def _load_module_copy(filename: str, alias: str):
    """Execute an app/ml source file as a fresh, unregistered module.

    Used to exercise import-time branches (missing optional dependencies)
    without reloading - and thus mutating - the real ``app.ml`` modules.
    Coverage is attributed to the original file path.
    """
    spec = importlib.util.spec_from_file_location(alias, ML_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_module_file(tmp_path: Path, *parts: str) -> str:
    """Build a fake ``__file__`` located under tmp_path (repo/backend/app/ml/<file>)."""
    return str(tmp_path.joinpath("repo", "backend", "app", "ml", *parts))


SVM_DESCRIPTIONS = [
    "cotton t-shirt for men",
    "cotton shirt short sleeves",
    "knitted cotton t-shirt",
    "white cotton shirt",
    "cotton tee shirt printed",
    "cotton shirt for women",
    "steel screw bolt",
    "steel nut and bolt",
    "iron steel screw",
    "stainless steel bolt",
    "steel screw zinc",
    "galvanized steel bolt",
]
SVM_CODES = ["6109"] * 6 + ["7318"] * 6


@pytest.fixture(scope="module")
def trained_svm():
    svm = SVMFallbackClassifier()
    svm.train(SVM_DESCRIPTIONS, SVM_CODES)
    return svm


# ============================================================================
# Config
# ============================================================================


def test_ml_config_constants():
    """Configuration values are coherent with the current pipeline."""
    assert ml_config.VOCAB_SIZE == 5000
    assert ml_config.MAX_SEQUENCE_LENGTH == 50
    assert ml_config.BATCH_SIZE == 32
    assert 0.0 <= ml_config.MIN_ANNOTATION_CONFIDENCE <= 1.0
    assert ml_config.TRAIN_SPLIT + ml_config.VAL_SPLIT + ml_config.TEST_SPLIT == pytest.approx(1.0)
    assert ml_config.MIN_CONFIDENCE_THRESHOLD < ml_config.HIGH_CONFIDENCE_THRESHOLD
    assert ml_config.ONNX_PROVIDERS == ["CPUExecutionProvider"]
    assert ml_config.ONNX_OPSET_VERSION == 12
    assert isinstance(ml_config.ML_DATA_DIR, Path)
    assert ml_config.ONNX_MODEL_DIR == ml_config.ML_DATA_DIR / "models" / "onnx"
    assert ml_config.PYTORCH_MODEL_DIR.parent == ml_config.SVM_MODEL_DIR.parent
    assert ml_config.CURRENT_ONNX_MODEL_VERSION == "v1_quantized"
    assert set(ml_config.TRACKED_METRICS) >= {"train_loss", "val_accuracy"}
    assert ml_config.PERFORMANCE_TARGETS["accuracy_min"] == pytest.approx(0.60)


# ============================================================================
# DatasetManager
# ============================================================================


def _annotation(i: int, code: str = "6109", confidence: float = 1.0) -> AnnotatedHS:
    return AnnotatedHS(description=f"product number {i}", hs_code=code, confidence=confidence)


def test_dataset_manager_creates_directories(tmp_path):
    dm = DatasetManager(data_dir=tmp_path / "ml")
    assert dm.data_dir == tmp_path / "ml"
    assert dm.annotations_dir.is_dir()
    assert dm.datasets_dir.is_dir()


def test_dataset_manager_default_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        dataset_manager, "__file__", _fake_module_file(tmp_path, "dataset_manager.py")
    )
    dm = DatasetManager()
    assert dm.data_dir == tmp_path / "repo" / "data" / "ml"
    assert dm.annotations_dir.is_dir()


def test_collect_and_load_annotations(tmp_path):
    dm = DatasetManager(data_dir=tmp_path)
    ann = AnnotatedHS(description="t-shirt coton", hs_code="6109", origin_country="FR")
    assert ann.timestamp is None

    assert dm.collect_annotation(ann, source="user") is True
    assert ann.timestamp is not None  # filled in by collect_annotation
    assert dm.collect_annotation(_annotation(1, "6203", confidence=0.2), source="system")

    user_file = dm.annotations_dir / "annotations_user.jsonl"
    lines = user_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["hs_code"] == "6109"

    # All sources, default min_confidence=0.5 drops the low-confidence one
    loaded = dm.load_annotations()
    assert [a.hs_code for a in loaded] == ["6109"]
    assert loaded[0].origin_country == "FR"

    # Lower threshold keeps both; source filter restricts files read
    assert len(dm.load_annotations(min_confidence=0.0)) == 2
    system = dm.load_annotations(source="system", min_confidence=0.0)
    assert [a.hs_code for a in system] == ["6203"]
    # Unknown source -> missing file is skipped
    assert dm.load_annotations(source="external") == []


def test_load_annotations_skips_malformed_lines(tmp_path):
    dm = DatasetManager(data_dir=tmp_path)
    dm.collect_annotation(_annotation(1), source="user")
    with open(dm.annotations_dir / "annotations_user.jsonl", "a", encoding="utf-8") as f:
        f.write("{not json}\n")
        f.write(json.dumps({"description": "missing hs_code"}) + "\n")

    loaded = dm.load_annotations(source="user")
    assert len(loaded) == 1


def test_collect_annotation_error_returns_false(tmp_path):
    dm = DatasetManager(data_dir=tmp_path)
    # A directory where the JSONL file should be makes open() fail
    (dm.annotations_dir / "annotations_broken.jsonl").mkdir()
    assert dm.collect_annotation(_annotation(1), source="broken") is False


def test_load_annotations_error_returns_empty(tmp_path):
    dm = DatasetManager(data_dir=tmp_path)
    (dm.annotations_dir / "annotations_dir.jsonl").mkdir()
    assert dm.load_annotations() == []


def test_create_dataset_requires_ten_annotations(tmp_path):
    dm = DatasetManager(data_dir=tmp_path)
    for i in range(9):
        dm.collect_annotation(_annotation(i))
    assert dm.create_dataset("too_small") is None
    assert not (dm.datasets_dir / "too_small").exists()


def test_create_load_and_stats_dataset(tmp_path):
    dm = DatasetManager(data_dir=tmp_path)
    codes = ["6109", "6203", "7318", "8471"]
    for i in range(20):
        dm.collect_annotation(_annotation(i, codes[i % 4]))

    meta = dm.create_dataset("v1")
    assert meta["name"] == "v1"
    assert meta["total_samples"] == 20
    assert (meta["train_samples"], meta["val_samples"], meta["test_samples"]) == (14, 3, 3)
    assert meta["unique_hs_codes"] == 4
    assert meta["split_ratios"] == (0.7, 0.15, 0.15)

    ds_dir = dm.datasets_dir / "v1"
    for split in ("train", "val", "test", "metadata"):
        assert (ds_dir / f"{split}.{'json' if split == 'metadata' else 'csv'}").exists()

    train = dm.load_dataset("v1", "train")
    assert len(train) == 14
    assert list(train.columns) == ["description", "hs_code", "origin_country", "confidence"]
    assert set(train["origin_country"]) == {"UNKNOWN"}
    assert len(dm.load_dataset("v1", "test")) == 3

    stats = dm.get_dataset_stats("v1")
    assert stats["total_samples"] == 20
    assert stats["split_ratios"] == [0.7, 0.15, 0.15]  # tuple serialised as list


def test_create_dataset_custom_ratios(tmp_path):
    dm = DatasetManager(data_dir=tmp_path)
    for i in range(10):
        dm.collect_annotation(_annotation(i))
    meta = dm.create_dataset("half", split_ratios=(0.5, 0.3, 0.2))
    assert (meta["train_samples"], meta["val_samples"], meta["test_samples"]) == (5, 3, 2)


def test_create_dataset_error_returns_none(tmp_path):
    dm = DatasetManager(data_dir=tmp_path)
    for i in range(10):
        dm.collect_annotation(_annotation(i))
    # A file where the dataset directory should go makes mkdir() fail
    (dm.datasets_dir / "clash").write_text("x")
    assert dm.create_dataset("clash") is None


def test_load_dataset_missing_and_error(tmp_path):
    dm = DatasetManager(data_dir=tmp_path)
    missing = dm.load_dataset("nope", "train")
    assert isinstance(missing, pd.DataFrame) and missing.empty

    (dm.datasets_dir / "bad" / "train.csv").mkdir(parents=True)
    broken = dm.load_dataset("bad", "train")
    assert isinstance(broken, pd.DataFrame) and broken.empty


def test_get_dataset_stats_missing_and_error(tmp_path):
    dm = DatasetManager(data_dir=tmp_path)
    assert dm.get_dataset_stats("nope") == {}

    bad = dm.datasets_dir / "bad"
    bad.mkdir()
    (bad / "metadata.json").write_text("{invalid")
    assert dm.get_dataset_stats("bad") == {}


# ============================================================================
# MLflowTracker (file based, no server)
# ============================================================================


def test_mlflow_tracker_init(tmp_path):
    tracker = MLflowTracker(tracking_dir=tmp_path / "mlflow")
    assert tracker.tracking_dir.is_dir()
    assert tracker.mlflow_uri.startswith("file://")
    assert str((tmp_path / "mlflow").resolve()) in tracker.mlflow_uri


def test_mlflow_tracker_default_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        mlflow_tracker, "__file__", _fake_module_file(tmp_path, "mlflow_tracker.py")
    )
    tracker = MLflowTracker()
    assert tracker.tracking_dir == tmp_path / "repo" / "data" / "mlflow"
    assert tracker.tracking_dir.is_dir()


def test_mlflow_tracker_full_run(tmp_path):
    tracker = MLflowTracker(tracking_dir=tmp_path)
    params = {"lr": 0.001, "batch_size": 16}

    run_dir = tracker.start_experiment("exp", params)
    run_path = Path(run_dir)
    assert run_path.parent == tmp_path / "exp"
    assert json.loads((run_path / "params.json").read_text()) == params

    tracker.log_metrics(run_dir, {"accuracy": 0.5, "loss": 1.2}, step=0)
    tracker.log_metrics(run_dir, {"accuracy": 0.7, "loss": 0.8}, step=1)
    entries = [json.loads(line) for line in (run_path / "metrics.jsonl").read_text().splitlines()]
    assert [e["step"] for e in entries] == [0, 1]
    assert entries[1]["accuracy"] == 0.7
    assert "timestamp" in entries[0]

    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"\x00\x01")
    tracker.log_artifact(run_dir, model_file, "model.bin")
    assert (run_path / "artifacts" / "model.bin").read_bytes() == b"\x00\x01"

    src_dir = tmp_path / "vocab"
    src_dir.mkdir()
    (src_dir / "vocab.json").write_text("{}")
    tracker.log_artifact(run_dir, src_dir, "vocab_dir")
    assert (run_path / "artifacts" / "vocab_dir" / "vocab.json").exists()

    tracker.end_experiment(run_dir, status="failed")
    meta = json.loads((run_path / "metadata.json").read_text())
    assert meta["status"] == "failed"
    assert "end_time" in meta

    best = tracker.get_best_run("exp", "accuracy")
    assert best["run_dir"] == run_dir
    assert best["metric_value"] == 0.7


def _write_run(exp_dir: Path, name: str, lines: list[str]):
    run = exp_dir / name
    run.mkdir(parents=True)
    (run / "metrics.jsonl").write_text("".join(line + "\n" for line in lines))


def test_mlflow_get_best_run_selects_max_of_last_line(tmp_path):
    tracker = MLflowTracker(tracking_dir=tmp_path)
    exp = tmp_path / "exp"
    # Only the last line of each run counts
    _write_run(exp, "run_a", [json.dumps({"accuracy": 0.99}), json.dumps({"accuracy": 0.6})])
    _write_run(exp, "run_b", [json.dumps({"accuracy": 0.8})])
    _write_run(exp, "run_c", [json.dumps({"loss": 0.1})])  # metric absent
    (exp / "run_empty").mkdir()
    (exp / "run_empty" / "metrics.jsonl").write_text("")
    (exp / "run_no_metrics").mkdir()
    (exp / "stray_file.txt").write_text("not a run")

    best = tracker.get_best_run("exp", "accuracy")
    assert Path(best["run_dir"]).name == "run_b"
    assert best["metric_value"] == 0.8
    assert best["metrics"] == {"accuracy": 0.8}

    assert tracker.get_best_run("exp", "f1") is None
    assert tracker.get_best_run("missing_exp") is None


def test_mlflow_error_paths_are_swallowed(tmp_path):
    tracker = MLflowTracker(tracking_dir=tmp_path)

    # Experiment name clashing with a file -> mkdir fails -> None
    (tmp_path / "clash").write_text("x")
    assert tracker.start_experiment("clash", {}) is None

    missing_run = str(tmp_path / "no" / "such" / "run")
    tracker.log_metrics(missing_run, {"a": 1})
    tracker.end_experiment(missing_run)
    tracker.log_artifact(str(tmp_path), tmp_path / "does_not_exist", "x")
    assert not (tmp_path / "no").exists()
    assert not (tmp_path / "artifacts" / "x").exists()

    _write_run(tmp_path / "exp", "run_bad", ["{broken json"])
    assert tracker.get_best_run("exp", "accuracy") is None


# ============================================================================
# ONNX inference
# ============================================================================


class _FakeSession:
    """Minimal stand-in for onnxruntime.InferenceSession."""

    def __init__(self, logits, fail=False):
        self.logits = np.asarray(logits, dtype=np.float32)
        self.fail = fail
        self.feeds = None

    def get_inputs(self):
        return [SimpleNamespace(name="input_ids")]

    def run(self, output_names, feeds):
        self.feeds = feeds
        if self.fail:
            raise RuntimeError("inference failed")
        return [self.logits.reshape(1, -1)]


@pytest.fixture
def fake_ort_session(monkeypatch):
    """Patch onnxruntime.InferenceSession; returns the list of created sessions."""
    created = []
    state = {"logits": [0.1, 2.0, 0.3], "fail": False}

    def factory(path, sess_options=None, providers=None):
        session = _FakeSession(state["logits"], state["fail"])
        session.path = path
        session.sess_options = sess_options
        session.providers = providers
        created.append(session)
        return session

    monkeypatch.setattr(onnx_inference.ort, "InferenceSession", factory)
    return SimpleNamespace(created=created, state=state)


def test_onnx_service_without_model_uses_default(tmp_path):
    service = ONNXInferenceService(None)
    assert service.session is None
    assert service.predict("anything") == ("unknown", 0.5)

    service.set_vocab({"coton": 2}, ["6109", "6203"])
    assert service.vocab == {"coton": 2}
    assert service.predict("anything") == ("6109", 0.5)


def test_onnx_service_invalid_model_file(tmp_path):
    """The real onnxruntime rejects a garbage file; the service degrades gracefully."""
    bad = tmp_path / "bad.onnx"
    bad.write_bytes(b"this is not an onnx model")
    service = ONNXInferenceService(bad)
    assert service.model_path == bad
    assert service.session is None
    assert service.predict("t-shirt") == ("unknown", 0.5)


def test_onnx_service_loads_session_with_cpu_options(tmp_path, fake_ort_session):
    model = tmp_path / "model.onnx"
    service = ONNXInferenceService(model)
    sess = fake_ort_session.created[0]
    assert service.session is sess
    assert sess.path == str(model)
    assert sess.providers == ["CPUExecutionProvider"]
    ort = onnx_inference.ort
    assert sess.sess_options.graph_optimization_level == ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    assert sess.sess_options.execution_mode == ort.ExecutionMode.ORT_SEQUENTIAL


def test_onnx_service_predict(tmp_path, fake_ort_session):
    service = ONNXInferenceService(tmp_path / "model.onnx")
    service.set_vocab({"coton": 2, "tshirt": 3}, ["6109", "6203", "7318"])

    code, conf = service.predict("Coton T-shirt")
    probs = ONNXInferenceService._softmax(np.array([0.1, 2.0, 0.3]))
    assert code == "6203"
    assert conf == pytest.approx(float(probs[1]), rel=1e-5)

    feeds = fake_ort_session.created[0].feeds
    ids = feeds["input_ids"]
    assert ids.dtype == np.int64 and ids.shape == (1, 50)
    assert ids[0, :2].tolist() == [2, 3]
    assert ids[0, 2:].sum() == 0


def test_onnx_service_predict_index_out_of_range(tmp_path, fake_ort_session):
    service = ONNXInferenceService(tmp_path / "model.onnx")
    service.set_vocab({}, ["6109"])  # argmax is 1 -> no matching code
    assert service.predict("x") == ("unknown", 0.0)


def test_onnx_service_predict_runtime_error(tmp_path, fake_ort_session):
    fake_ort_session.state["fail"] = True
    service = ONNXInferenceService(tmp_path / "model.onnx")
    service.set_vocab({}, ["6109", "6203", "7318"])
    assert service.predict("x") == ("unknown", 0.0)


def test_onnx_service_respects_onnx_unavailable(tmp_path, fake_ort_session, monkeypatch):
    monkeypatch.setattr(onnx_inference, "ONNX_AVAILABLE", False)
    service = ONNXInferenceService(tmp_path / "model.onnx")
    assert service.session is None
    assert fake_ort_session.created == []


def test_encode_text_and_softmax():
    service = ONNXInferenceService(None)
    service.set_vocab({"coton": 5, "chemise": 6}, [])

    encoded = service._encode_text("Chemise, COTON! inconnu", max_len=5)
    assert encoded.tolist() == [[6, 5, 1, 0, 0]]
    assert encoded.dtype == np.int64

    truncated = service._encode_text("coton " * 10, max_len=3)
    assert truncated.tolist() == [[5, 5, 5]]

    probs = ONNXInferenceService._softmax(np.array([1000.0, 1000.0]))  # numerically stable
    assert probs.tolist() == pytest.approx([0.5, 0.5])
    probs = ONNXInferenceService._softmax(np.array([0.0, 1.0, 2.0]))
    assert probs.sum() == pytest.approx(1.0)
    assert np.argmax(probs) == 2


def test_svm_untrained_predict():
    svm = SVMFallbackClassifier()
    assert svm.model is None and svm.vectorizer is None
    assert svm.predict("anything") == ("unknown", 0.5)


def test_svm_train_predict(trained_svm):
    code, conf = trained_svm.predict("cotton t-shirt")
    assert code == "6109"
    assert 0.0 < conf <= 1.0
    code, _ = trained_svm.predict("steel bolt")
    assert code == "7318"


def test_svm_save_and_load_roundtrip(tmp_path, trained_svm):
    path = tmp_path / "nested" / "svm.pkl"
    trained_svm.save(path)
    assert path.exists()

    loaded = SVMFallbackClassifier(path)
    assert loaded.model is not None and loaded.vectorizer is not None
    assert loaded.predict("steel screw")[0] == "7318"


def test_svm_load_missing_file(tmp_path):
    svm = SVMFallbackClassifier(tmp_path / "missing.pkl")
    assert svm.model is None
    assert svm.predict("x") == ("unknown", 0.5)


def test_svm_save_error_is_swallowed(tmp_path, trained_svm):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    trained_svm.save(blocker / "svm.pkl")  # parent is a file -> mkdir fails
    assert not (blocker / "svm.pkl").exists()


def test_svm_train_error_then_predict_error():
    svm = SVMFallbackClassifier()
    svm.train(["only one description"], ["6109", "6203"])  # length mismatch
    # The (unfitted) SVC is kept, so predict hits its own error path
    assert svm.predict("x") == ("unknown", 0.5)


def test_hybrid_prefers_onnx(tmp_path, fake_ort_session, trained_svm):
    hybrid = HybridClassifier(onnx_path=tmp_path / "m.onnx")
    hybrid.onnx_service.set_vocab({}, ["6109", "6203", "7318"])
    hybrid.svm_classifier = trained_svm
    result = hybrid.predict("steel bolt")
    assert result["method"] == "onnx"
    assert result["hs_code"] == "6203"


def test_hybrid_falls_back_to_svm(tmp_path, fake_ort_session, trained_svm):
    hybrid = HybridClassifier(onnx_path=tmp_path / "m.onnx")
    # No hs_codes configured -> ONNX returns "unknown" -> SVM fallback
    hybrid.svm_classifier = trained_svm
    result = hybrid.predict("steel bolt")
    assert result == {"hs_code": "7318", "confidence": result["confidence"], "method": "svm"}


def test_hybrid_final_fallback(trained_svm, monkeypatch):
    hybrid = HybridClassifier()
    assert hybrid.onnx_service.session is None
    assert hybrid.predict("x") == {"hs_code": "unknown", "confidence": 0.0, "method": "fallback"}

    hybrid.svm_classifier = trained_svm
    monkeypatch.setattr(trained_svm, "predict", lambda d: ("unknown", 0.5))
    assert hybrid.predict("x")["method"] == "fallback"


def test_onnx_inference_import_without_onnxruntime(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    mod = _load_module_copy("onnx_inference.py", "_declado_test_onnx_inference_no_ort")
    assert mod.ONNX_AVAILABLE is False

    service = mod.ONNXInferenceService(tmp_path / "m.onnx")
    assert service.session is None
    service.set_vocab({}, ["6109"])
    assert service.predict("x") == ("6109", 0.5)
    assert mod.HybridClassifier().predict("x")["method"] == "fallback"


# ============================================================================
# HSClassifierService
# ============================================================================


@pytest.fixture
def capture_hybrid(monkeypatch):
    """Replace HybridClassifier in the service module and record its arguments."""
    calls = []

    class _StubHybrid:
        def __init__(self, onnx_path=None, svm_path=None):
            calls.append({"onnx_path": onnx_path, "svm_path": svm_path})

        def predict(self, description):
            return {"hs_code": "8471", "confidence": 0.9, "method": "onnx"}

    monkeypatch.setattr(hs_service, "HybridClassifier", _StubHybrid)
    return calls


def test_service_with_empty_model_dir(tmp_path):
    service = HSClassifierService(model_dir=tmp_path)
    assert service.model_dir == tmp_path
    assert service.ml_available is True
    assert isinstance(service.classifier, HybridClassifier)

    result = service.suggest_hs_code("t-shirt en coton")
    assert result == {
        "hs_code": "unknown",
        "confidence": 0.0,
        "method": "fallback",
        "alternatives": ["6109", "6105", "6104"],
        "model_version": "v1_quantized",
    }


def test_service_model_path_selection(tmp_path, capture_hybrid):
    HSClassifierService(model_dir=tmp_path)
    assert capture_hybrid[-1] == {"onnx_path": None, "svm_path": None}

    (tmp_path / "hs_classifier_v1.onnx").write_bytes(b"")
    (tmp_path / "hs_classifier_svm.pkl").write_bytes(b"")
    HSClassifierService(model_dir=tmp_path)
    assert capture_hybrid[-1] == {
        "onnx_path": tmp_path / "hs_classifier_v1.onnx",
        "svm_path": tmp_path / "hs_classifier_svm.pkl",
    }

    (tmp_path / "hs_classifier_v1_quantized.onnx").write_bytes(b"")
    service = HSClassifierService(model_dir=tmp_path)
    assert capture_hybrid[-1]["onnx_path"] == tmp_path / "hs_classifier_v1_quantized.onnx"

    result = service.suggest_hs_code("laptop")
    assert result["hs_code"] == "8471"
    assert result["confidence"] == 0.9
    assert result["method"] == "onnx"


def test_service_init_failure_uses_default_suggestion(tmp_path, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("cannot build classifier")

    monkeypatch.setattr(hs_service, "HybridClassifier", boom)
    service = HSClassifierService(model_dir=tmp_path)
    assert service.ml_available is False
    assert service.suggest_hs_code("x") == {
        "hs_code": "6109",
        "confidence": 0.5,
        "method": "default",
        "alternatives": ["6105", "6104"],
        "model_version": "none",
    }


def test_service_suggest_error(tmp_path):
    service = HSClassifierService(model_dir=tmp_path)
    service.classifier = SimpleNamespace(predict=lambda d: {"unexpected": "shape"})
    assert service.suggest_hs_code("x") == {
        "hs_code": "unknown",
        "confidence": 0.0,
        "method": "error",
        "alternatives": [],
        "model_version": "none",
    }


def test_service_alternatives_top_k(tmp_path):
    service = HSClassifierService(model_dir=tmp_path)
    assert service._get_alternatives("x") == ["6109", "6105", "6104"]
    assert service._get_alternatives("x", top_k=5) == ["6109", "6105", "6104", "6203", "6204"]
    assert service._get_alternatives("x", top_k=1) == ["6109"]


def test_service_train_classifier_then_predict_with_svm(tmp_path):
    service = HSClassifierService(model_dir=tmp_path)
    assert service.train_classifier(SVM_DESCRIPTIONS, SVM_CODES) is True
    assert (tmp_path / "hs_classifier_svm.pkl").exists()
    assert service.classifier.svm_classifier.model is not None

    result = service.suggest_hs_code("galvanized steel screw")
    assert result["hs_code"] == "7318"
    assert result["method"] == "svm"
    assert 0.0 < result["confidence"] <= 1.0


def test_service_train_classifier_failure(tmp_path, monkeypatch):
    def boom():
        raise RuntimeError("no svm")

    monkeypatch.setattr(onnx_inference, "SVMFallbackClassifier", boom)
    service = HSClassifierService(model_dir=tmp_path)
    assert service.train_classifier(["a"], ["6109"]) is False


def test_service_without_ml_modules(tmp_path, monkeypatch):
    monkeypatch.setattr(hs_service, "ML_AVAILABLE", False)
    service = HSClassifierService(model_dir=tmp_path)
    assert service.classifier is None
    assert service.ml_available is False
    assert service.suggest_hs_code("x")["method"] == "default"
    assert service.train_classifier(["a"], ["6109"]) is False


def test_service_module_import_without_onnx_inference(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "app.ml.onnx_inference", None)
    mod = _load_module_copy("hs_classifier_service.py", "_declado_test_hs_service_no_ml")
    assert mod.ML_AVAILABLE is False
    service = mod.HSClassifierService(model_dir=tmp_path)
    assert service.classifier is None
    assert service.suggest_hs_code("x")["method"] == "default"


def test_get_classifier_service_singleton(tmp_path, monkeypatch):
    monkeypatch.setattr(hs_service, "_classifier_service", None)
    monkeypatch.setattr(
        hs_service, "__file__", _fake_module_file(tmp_path, "hs_classifier_service.py")
    )
    first = get_classifier_service()
    second = get_classifier_service()
    assert first is second
    assert isinstance(first, HSClassifierService)
    # Default model directory is derived from the module location (under tmp_path here)
    assert first.model_dir.parts[-2:] == ("data", "models")
    assert tmp_path in first.model_dir.parents


# ============================================================================
# Transformer trainer (with a numpy-backed fake ``torch``)
# ============================================================================


class _FakeTensor(np.ndarray):
    """ndarray with the handful of torch.Tensor methods the trainer uses."""

    device = "cpu"

    def to(self, device):
        return self

    def size(self, dim=None):
        return self.shape if dim is None else self.shape[dim]

    def unsqueeze(self, dim):
        return _t(np.expand_dims(np.asarray(self), dim))

    def mean(self, dim=None, **kwargs):  # torch uses ``dim``
        return _t(np.asarray(self).mean(axis=dim))

    def backward(self):
        _FAKE_TORCH_CALLS["backward"] += 1


def _t(array) -> _FakeTensor:
    return np.asarray(array).view(_FakeTensor)


_FAKE_TORCH_CALLS = {"backward": 0}


def _build_fake_torch() -> dict:
    torch = types.ModuleType("torch")
    nn = types.ModuleType("torch.nn")
    optim = types.ModuleType("torch.optim")
    utils = types.ModuleType("torch.utils")
    data = types.ModuleType("torch.utils.data")
    onnx = types.ModuleType("torch.onnx")

    class Module:
        def __init__(self):
            self.training = True

        def __call__(self, *args, **kwargs):
            return self.forward(*args, **kwargs)

        def to(self, device):
            self.device = device
            return self

        def train(self, mode=True):
            self.training = mode
            return self

        def eval(self):
            return self.train(False)

        def parameters(self):
            return iter([])

        def state_dict(self):
            return {"weights": [0.0]}

    class Embedding(Module):
        def __init__(self, num_embeddings, embedding_dim, padding_idx=None):
            super().__init__()
            self.num_embeddings = num_embeddings
            self.embedding_dim = embedding_dim
            self.padding_idx = padding_idx

        def forward(self, ids):
            if np.asarray(ids).max() >= self.num_embeddings:
                raise IndexError("index out of range in self")
            return _t(np.zeros(np.shape(ids) + (self.embedding_dim,)))

    class Linear(Module):
        def __init__(self, in_features, out_features):
            super().__init__()
            self.in_features = in_features
            self.out_features = out_features

        def forward(self, x):
            assert x.shape[-1] == self.in_features
            return _t(np.zeros(x.shape[:-1] + (self.out_features,)))

    class _Identity(Module):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self.args, self.kwargs = args, kwargs

        def forward(self, x):
            return x

    class Sequential(Module):
        def __init__(self, *layers):
            super().__init__()
            self.layers = layers

        def forward(self, x):
            for layer in self.layers:
                x = layer(x)
            return x

    class TransformerEncoderLayer(_Identity):
        pass

    class TransformerEncoder(Module):
        def __init__(self, layer, num_layers):
            super().__init__()
            self.layer = layer
            self.num_layers = num_layers
            self.last_mask = None

        def forward(self, x, src_key_padding_mask=None):
            self.last_mask = src_key_padding_mask
            return x

    class CrossEntropyLoss:
        def __call__(self, logits, targets):
            logits = np.asarray(logits, dtype=float)
            targets = np.asarray(targets)
            shifted = logits - logits.max(axis=1, keepdims=True)
            log_probs = shifted - np.log(np.exp(shifted).sum(axis=1, keepdims=True))
            return _t(np.array(-log_probs[np.arange(len(targets)), targets].mean()))

    for cls in (Module, Embedding, Linear, Sequential, TransformerEncoder, CrossEntropyLoss):
        setattr(nn, cls.__name__, cls)
    nn.TransformerEncoderLayer = TransformerEncoderLayer
    nn.ReLU = type("ReLU", (_Identity,), {})
    nn.Dropout = type("Dropout", (_Identity,), {})
    nn.AdaptiveAvgPool1d = type("AdaptiveAvgPool1d", (_Identity,), {})

    class Adam:
        def __init__(self, params, lr=1e-3):
            self.params = list(params)
            self.lr = lr
            self.steps = 0

        def zero_grad(self):
            pass

        def step(self):
            self.steps += 1

    optim.Adam = Adam

    class Dataset:
        pass

    class DataLoader:
        def __init__(self, dataset, batch_size=1, shuffle=False):
            self.dataset = dataset
            self.batch_size = batch_size
            self.shuffle = shuffle  # ignored: deterministic order

        def __len__(self):
            return math.ceil(len(self.dataset) / self.batch_size)

        def __iter__(self):
            n = len(self.dataset)
            for start in range(0, n, self.batch_size):
                items = [self.dataset[i] for i in range(start, min(n, start + self.batch_size))]
                yield _t(np.stack([x for x, _ in items])), _t(np.stack([y for _, y in items]))

    data.Dataset = Dataset
    data.DataLoader = DataLoader
    utils.data = data

    onnx.calls = []

    def export(model, args, f, **kwargs):
        onnx.calls.append({"model": model, "args": args, "f": f, **kwargs})
        Path(f).write_bytes(b"fake-onnx")

    onnx.export = export

    def save(obj, path):
        Path(path).write_text(json.dumps(obj))

    def tensor(values, dtype=None):
        return _t(np.array(values, dtype=dtype))

    def torch_max(x, dim):
        arr = np.asarray(x)
        return _t(arr.max(axis=dim)), _t(arr.argmax(axis=dim))

    torch.long = np.int64
    torch.tensor = tensor
    torch.device = lambda name: name
    torch.cuda = SimpleNamespace(is_available=lambda: False)
    torch.arange = lambda n, device=None: _t(np.arange(n))
    torch.randint = lambda low, high, size: _t(
        np.random.default_rng(0).integers(low, high, size=size)
    )
    torch.max = torch_max
    torch.no_grad = contextlib.nullcontext
    torch.save = save
    torch.nn = nn
    torch.optim = optim
    torch.utils = utils
    torch.onnx = onnx

    return {
        "torch": torch,
        "torch.nn": nn,
        "torch.optim": optim,
        "torch.utils": utils,
        "torch.utils.data": data,
        "torch.onnx": onnx,
    }


@pytest.fixture
def trainer_mod(monkeypatch):
    """transformer_trainer loaded against the fake torch (real torch is never used)."""
    for name, module in _build_fake_torch().items():
        monkeypatch.setitem(sys.modules, name, module)
    _FAKE_TORCH_CALLS["backward"] = 0
    return _load_module_copy("transformer_trainer.py", "_declado_test_transformer_trainer")


def test_hs_dataset_vocab_mapping_and_items(trainer_mod):
    descs = ["Cotton T-Shirt", "cotton shirt!!", "steel bolt ???"]
    codes = ["6109", "6205", "6109"]
    ds = trainer_mod.HSDataset(descs, codes)

    assert ds.vocab == {
        "<PAD>": 0,
        "<UNK>": 1,
        "cotton": 2,
        "tshirt": 3,
        "shirt": 4,
        "steel": 5,
        "bolt": 6,
    }
    assert ds.hs_mapping == {"6109": 0, "6205": 1}
    assert ds.num_classes == 2
    assert len(ds) == 3

    encoded = ds.encode_text("cotton unknownword bolt", max_len=5)
    assert encoded == [2, 1, 6, 0, 0]
    assert ds.encode_text("cotton " * 60) == [2] * 50

    x, y = ds[1]
    assert x.shape == (50,) and x.dtype == np.int64
    assert x[:2].tolist() == [2, 4]
    assert int(y) == 1


def test_hs_dataset_vocab_size_limit(trainer_mod):
    ds = trainer_mod.HSDataset(["a b c d e f"], ["0101"], vocab_size=4)
    assert ds.vocab == {"<PAD>": 0, "<UNK>": 1, "a": 2, "b": 3}


def test_mini_transformer_forward(trainer_mod):
    model = trainer_mod.MiniTransformer(vocab_size=10, num_classes=3, hidden_dim=8, num_heads=2)
    assert model.transformer.num_layers == 2
    assert model.pos_encoding.num_embeddings == 50

    ids = _t(np.array([[2, 3, 0, 0], [4, 0, 0, 0]], dtype=np.int64))
    logits = model(ids)
    assert logits.shape == (2, 3)
    assert np.asarray(model.transformer.last_mask).tolist() == [
        [False, False, True, True],
        [False, True, True, True],
    ]


def test_trainer_default_model_dir(trainer_mod, tmp_path, monkeypatch):
    monkeypatch.setattr(
        trainer_mod, "__file__", _fake_module_file(tmp_path, "transformer_trainer.py")
    )
    trainer = trainer_mod.TransformerTrainer()
    assert trainer.model_dir == tmp_path / "repo" / "data" / "models"
    assert trainer.model_dir.is_dir()
    assert trainer.device == "cpu"


def test_trainer_train_loop(trainer_mod, tmp_path):
    trainer = trainer_mod.TransformerTrainer(model_dir=tmp_path)
    train_df = pd.DataFrame(
        {
            "description": [
                "cotton shirt",
                "cotton t-shirt",
                "steel bolt",
                "steel screw",
                "laptop computer",
                "desktop computer",
            ],
            "hs_code": ["6109", "6109", "7318", "7318", "8471", "8471"],
        }
    )
    val_df = pd.DataFrame(
        {
            "description": ["cotton tee", "steel nut", "zinc bolt"],
            "hs_code": ["6109", "7318", "7318"],
        }
    )

    model, metrics = trainer.train(train_df, val_df, epochs=2, batch_size=4, lr=0.01)

    assert isinstance(model, trainer_mod.MiniTransformer)
    assert model.training is False  # left in eval mode after validation
    assert set(metrics) == {"train_loss", "val_accuracy", "val_loss"}
    assert all(len(v) == 2 for v in metrics.values())
    # Fake model emits uniform logits over the 3 training classes
    assert metrics["train_loss"] == pytest.approx([math.log(3)] * 2)
    assert metrics["val_loss"] == pytest.approx([math.log(3)] * 2)
    # argmax of uniform logits is class 0; 1 of 3 validation labels is 0
    assert metrics["val_accuracy"] == pytest.approx([1 / 3] * 2)
    # 2 batches per epoch (6 samples, batch_size 4)
    assert _FAKE_TORCH_CALLS["backward"] == 4


def test_trainer_train_propagates_errors(trainer_mod, tmp_path):
    trainer = trainer_mod.TransformerTrainer(model_dir=tmp_path)
    bad = pd.DataFrame({"text": ["x"], "label": ["0101"]})
    with pytest.raises(KeyError):
        trainer.train(bad, bad, epochs=1)


def test_trainer_save_and_export(trainer_mod, tmp_path):
    trainer = trainer_mod.TransformerTrainer(model_dir=tmp_path)
    model = trainer_mod.MiniTransformer(vocab_size=20, num_classes=2, hidden_dim=8, num_heads=2)

    trainer.save_model(model, "hs_v1")
    assert json.loads((tmp_path / "hs_v1.pth").read_text()) == {"weights": [0.0]}

    onnx_path = trainer.export_onnx(model, vocab_size=20, output_name="hs_test")
    assert onnx_path == tmp_path / "hs_test.onnx"
    assert onnx_path.read_bytes() == b"fake-onnx"
    assert model.training is False

    call = sys.modules["torch.onnx"].calls[-1]
    assert call["model"] is model
    assert call["f"] == str(onnx_path)
    assert call["args"].shape == (1, 50)
    assert call["input_names"] == ["input_ids"]
    assert call["output_names"] == ["logits"]
    assert call["opset_version"] == 12
    assert call["do_constant_folding"] is True


def test_trainer_export_onnx_propagates_errors(trainer_mod, tmp_path, monkeypatch):
    def failing_export(*args, **kwargs):
        raise RuntimeError("export failed")

    monkeypatch.setattr(sys.modules["torch.onnx"], "export", failing_export)
    trainer = trainer_mod.TransformerTrainer(model_dir=tmp_path)
    model = trainer_mod.MiniTransformer(vocab_size=20, num_classes=2, hidden_dim=8, num_heads=2)
    with pytest.raises(RuntimeError, match="export failed"):
        trainer.export_onnx(model, vocab_size=20)
