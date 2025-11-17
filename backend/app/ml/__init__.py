"""
ML Module - Machine Learning Pipeline for HS Classification

Submodules:
- dataset_manager: Data collection, versioning, and preparation
- mlflow_tracker: Experiment tracking and logging
- transformer_trainer: Model training and ONNX export
- onnx_inference: Optimized inference with SVM fallback
- hs_classifier_service: Integration service for backend
"""

import logging

logger = logging.getLogger(__name__)

# Version info
__version__ = "1.0"
__name__ = "declado_ml"

logger.info(f"ML Module v{__version__} loaded")
