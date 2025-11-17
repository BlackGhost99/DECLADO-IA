"""
Service de classification HS utilisant le modèle ML ONNX.

Intègre le transformer ONNX dans le pipeline HS classification.
Fallback SVM si ONNX indisponible.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Tentative import des modules ML
try:
    from app.ml.onnx_inference import HybridClassifier

    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    logger.warning("ML modules not available; using traditional SVM classifier")


class HSClassifierService:
    """Service de classification HS utilisant ML."""

    def __init__(self, model_dir: Path = None):
        """
        Initialise le service de classification.

        Args:
            model_dir: Répertoire contenant les modèles
        """
        if model_dir is None:
            backend_dir = Path(__file__).parent.parent
            model_dir = backend_dir.parent / "data" / "models"

        self.model_dir = Path(model_dir)
        self.classifier = None
        self.ml_available = False

        if ML_AVAILABLE:
            self._initialize_ml_classifier(model_dir)

    def _initialize_ml_classifier(self, model_dir: Path):
        """Initialise le classificateur ML."""
        try:
            onnx_path = model_dir / "hs_classifier_v1_quantized.onnx"
            if not onnx_path.exists():
                onnx_path = model_dir / "hs_classifier_v1.onnx"

            svm_path = model_dir / "hs_classifier_svm.pkl"

            self.classifier = HybridClassifier(
                onnx_path=onnx_path if onnx_path.exists() else None,
                svm_path=svm_path if svm_path.exists() else None,
            )

            self.ml_available = True
            logger.info("ML classifier initialized successfully")

        except Exception as e:
            logger.warning(f"Error initializing ML classifier: {e}")
            self.ml_available = False

    def suggest_hs_code(self, description: str) -> dict:
        """
        Suggère un code HS pour une description.

        Args:
            description: Description de la marchandise

        Returns:
            {
                'hs_code': str,           # Code HS suggéré
                'confidence': float,      # Confiance 0-1
                'method': str,            # 'onnx', 'svm', ou 'fallback'
                'alternatives': list,     # Alternatives possibles
                'model_version': str,     # Version du modèle
            }
        """
        try:
            if not self.ml_available or self.classifier is None:
                logger.warning("ML classifier not available; using default suggestion")
                return {
                    "hs_code": "6109",  # Default: textiles
                    "confidence": 0.5,
                    "method": "default",
                    "alternatives": ["6105", "6104"],
                    "model_version": "none",
                }

            result = self.classifier.predict(description)

            return {
                "hs_code": result["hs_code"],
                "confidence": result["confidence"],
                "method": result["method"],
                "alternatives": self._get_alternatives(description),
                "model_version": "v1_quantized",
            }

        except Exception as e:
            logger.error(f"Error suggesting HS code: {e}")
            return {
                "hs_code": "unknown",
                "confidence": 0.0,
                "method": "error",
                "alternatives": [],
                "model_version": "none",
            }

    def _get_alternatives(self, description: str, top_k: int = 3) -> list:
        """
        Retourne les alternatives de code HS.

        Pour une implémentation complète, on pourrait:
        1. Modifier HybridClassifier pour retourner top-k predictions
        2. Utiliser softmax probabilities du modèle
        3. Filtrer par confidence threshold

        Args:
            description: Description de la marchandise
            top_k: Nombre d'alternatives

        Returns:
            Liste des HS codes alternatifs
        """
        # TODO: Implémenter top-k predictions dans HybridClassifier
        # Pour maintenant, retourner quelques codes communs
        common_codes = ["6109", "6105", "6104", "6203", "6204"]
        return common_codes[:top_k]

    def train_classifier(self, descriptions: list, hs_codes: list):
        """
        Entraîne le classificateur (SVM fallback).

        Args:
            descriptions: Listes de descriptions
            hs_codes: Listes de codes HS correspondants
        """
        try:
            if not ML_AVAILABLE:
                logger.error("ML modules not available; cannot train classifier")
                return False

            from app.ml.onnx_inference import SVMFallbackClassifier

            svm = SVMFallbackClassifier()
            svm.train(descriptions, hs_codes)

            svm_path = self.model_dir / "hs_classifier_svm.pkl"
            svm.save(svm_path)

            logger.info(f"Trained SVM classifier: {svm_path}")

            # Reinitialize with new SVM
            self._initialize_ml_classifier(self.model_dir)

            return True

        except Exception as e:
            logger.error(f"Error training classifier: {e}")
            return False


# Singleton pour utilisation globale
_classifier_service: HSClassifierService = None


def get_classifier_service() -> HSClassifierService:
    """Retourne l'instance singleton du service de classification."""
    global _classifier_service

    if _classifier_service is None:
        _classifier_service = HSClassifierService()

    return _classifier_service
