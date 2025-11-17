"""
Configuration pour Phase 9: ML Pipeline

Paramètres de training, inference, et deployment.
"""

from pathlib import Path

# ============================================================================
# DATASET CONFIGURATION
# ============================================================================

# Répertoire de base pour les données ML
ML_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "ml"

# Sources d'annotations à collecter
ANNOTATION_SOURCES = ["user", "system", "external"]

# Confiance minimale pour inclure une annotation
MIN_ANNOTATION_CONFIDENCE = 0.5

# Splits dataset
TRAIN_SPLIT = 0.70
VAL_SPLIT = 0.15
TEST_SPLIT = 0.15

# ============================================================================
# TRANSFORMER MODEL CONFIGURATION
# ============================================================================

# Architecture
VOCAB_SIZE = 5000
EMBEDDING_DIM = 128
NUM_TRANSFORMER_HEADS = 4
NUM_TRANSFORMER_LAYERS = 2
FEEDFORWARD_DIM = 256
MAX_SEQUENCE_LENGTH = 50
DROPOUT = 0.1

# Training
BATCH_SIZE = 32
NUM_EPOCHS = 10
LEARNING_RATE = 0.001
WEIGHT_DECAY = 0.01
OPTIMIZER = "adam"  # 'adam' or 'sgd'

# Validation
VALIDATION_FREQUENCY = 1  # Validate every N epochs
EARLY_STOPPING_PATIENCE = 3  # Stop if no improvement for N epochs

# ============================================================================
# ONNX EXPORT CONFIGURATION
# ============================================================================

# ONNX export settings
ONNX_OPSET_VERSION = 12
ONNX_DO_CONSTANT_FOLDING = True

# Quantization settings
QUANTIZATION_ENABLED = True
QUANTIZATION_TYPE = "QUInt8"  # 'QUInt8' or 'QInt8'
QUANTIZATION_TARGET_SIZE_MB = 5  # Target size for quantized model

# ============================================================================
# INFERENCE CONFIGURATION
# ============================================================================

# ONNX Runtime settings
ONNX_OPTIMIZATION_LEVEL = "all"  # 'disable', 'basic', 'extended', 'all'
ONNX_EXECUTION_MODE = "sequential"  # 'sequential' or 'parallel'
ONNX_PROVIDERS = ["CPUExecutionProvider"]  # Add 'CUDAExecutionProvider' for GPU

# Inference timeouts
INFERENCE_TIMEOUT_MS = 5000  # Max time for prediction

# Confidence thresholds
MIN_CONFIDENCE_THRESHOLD = 0.4  # Minimum confidence to accept prediction
HIGH_CONFIDENCE_THRESHOLD = 0.8  # High confidence level

# ============================================================================
# SVM FALLBACK CONFIGURATION
# ============================================================================

# SVM parameters
SVM_KERNEL = "linear"  # 'linear', 'rbf', 'poly'
SVM_C = 1.0  # Regularization parameter
SVM_GAMMA = "scale"

# Text vectorization
TF_IDF_MAX_FEATURES = 1000
TF_IDF_NGRAM_RANGE = (1, 2)

# ============================================================================
# MLFLOW CONFIGURATION
# ============================================================================

# MLflow tracking
MLFLOW_TRACKING_DIR = Path(__file__).parent.parent.parent.parent / "data" / "mlflow"
MLFLOW_EXPERIMENT_NAME = "hs_transformer"
MLFLOW_BACKEND = "file"  # 'file' or 'http'

# Metrics to track
TRACKED_METRICS = [
    "train_loss",
    "val_loss",
    "val_accuracy",
    "val_f1_score",
]

# ============================================================================
# PERFORMANCE TARGETS
# ============================================================================

# Performance acceptance criteria
PERFORMANCE_TARGETS = {
    "accuracy_min": 0.60,  # Minimum 60% accuracy
    "latency_mean_max_ms": 100,  # Maximum 100ms average latency
    "latency_p95_max_ms": 200,  # Maximum 200ms at P95
    "memory_max_mb": 500,  # Maximum 500MB memory
    "model_size_max_mb": 10,  # Maximum 10MB model size
}

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

ML_LOG_LEVEL = "INFO"
ML_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# ============================================================================
# MODEL VERSIONING
# ============================================================================

# Current model versions
CURRENT_PYTORCH_MODEL_VERSION = "v1"
CURRENT_ONNX_MODEL_VERSION = "v1_quantized"
CURRENT_SVM_MODEL_VERSION = "v1"

# Model directories
PYTORCH_MODEL_DIR = ML_DATA_DIR / "models" / "pytorch"
ONNX_MODEL_DIR = ML_DATA_DIR / "models" / "onnx"
SVM_MODEL_DIR = ML_DATA_DIR / "models" / "svm"

# ============================================================================
# DATA AUGMENTATION
# ============================================================================

# Enable data augmentation
DATA_AUGMENTATION_ENABLED = False

# Augmentation strategies
AUGMENTATION_STRATEGIES = [
    "paraphrase",  # Reformulate descriptions
    "translate",  # Translate to other languages
    "synonym",  # Replace with synonyms
]

# ============================================================================
# HYPERPARAMETER TUNING
# ============================================================================

# Grid search for hyperparameters
HYPERPARAMETER_GRID = {
    "hidden_dim": [64, 128, 256],
    "num_heads": [2, 4, 8],
    "num_layers": [1, 2, 3],
    "batch_size": [16, 32, 64],
    "learning_rate": [0.0001, 0.001, 0.01],
}

# ============================================================================
# A/B TESTING
# ============================================================================

# A/B test configuration
A_B_TESTING_ENABLED = True
NEW_MODEL_TRAFFIC_PERCENTAGE = 10  # Route 10% traffic to new model
IMPROVEMENT_THRESHOLD = 0.05  # 5% improvement required to promote

# ============================================================================
# MONITORING & ALERTS
# ============================================================================

# Monitoring thresholds
ACCURACY_ALERT_THRESHOLD = 0.50  # Alert if accuracy drops below 50%
LATENCY_ALERT_THRESHOLD_MS = 150  # Alert if latency > 150ms
ERROR_RATE_ALERT_THRESHOLD = 0.05  # Alert if error rate > 5%

# ============================================================================
# FEATURE ENGINEERING
# ============================================================================

# Text preprocessing
LOWERCASE = True
REMOVE_SPECIAL_CHARS = True
REMOVE_NUMBERS = False
MIN_WORD_LENGTH = 2
MAX_WORD_LENGTH = 50

# Tokenization
TOKENIZER_TYPE = "split"  # 'split', 'nltk', 'spacy'

# ============================================================================
# EXPORT & DEPLOYMENT
# ============================================================================

# Export configuration
EXPORT_FORMAT = "onnx"  # 'onnx', 'tensorflow', 'jit'
EXPORT_WITH_METADATA = True

# Deployment
DEPLOYMENT_PLATFORM = "cpu"  # 'cpu', 'gpu', 'tpu'
DEPLOYMENT_BATCH_SIZE = 1  # Batch size for inference

# ============================================================================
