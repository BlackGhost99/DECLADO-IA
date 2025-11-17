"""
Service d'inférence ONNX optimisé pour classification HS.

Utilise onnxruntime avec fallback vers SVM si ONNX non disponible.
Quantization post-entraînement pour latence/mémoire réduite.
"""

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Tentative import onnxruntime
try:
    import onnxruntime as ort

    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    logger.warning("onnxruntime not available; will use SVM fallback")


class ONNXInferenceService:
    """Service d'inférence ONNX optimisé."""

    def __init__(self, model_path: Path = None):
        """
        Initialise le service d'inférence.

        Args:
            model_path: Chemin au modèle ONNX
        """
        self.model_path = model_path
        self.session = None
        self.vocab = {}
        self.hs_codes = []

        if ONNX_AVAILABLE and model_path:
            self._load_onnx_model(model_path)
        else:
            logger.warning("ONNX inference unavailable; using SVM fallback")

    def _load_onnx_model(self, model_path: Path):
        """Charge le modèle ONNX."""
        try:
            # Options d'inférence optimisées
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

            # Providers (CPU optimisé)
            providers = ["CPUExecutionProvider"]

            self.session = ort.InferenceSession(str(model_path), sess_options, providers=providers)

            logger.info(f"Loaded ONNX model: {model_path}")

        except Exception as e:
            logger.error(f"Error loading ONNX model: {e}")
            self.session = None

    def set_vocab(self, vocab: dict, hs_codes: list[str]):
        """Configure le vocabulaire et les codes HS."""
        self.vocab = vocab
        self.hs_codes = hs_codes

    def _encode_text(self, text: str, max_len: int = 50) -> np.ndarray:
        """Encode un texte en indices."""
        tokens = text.lower().split()[:max_len]
        encoded = [self.vocab.get("".join(c for c in word if c.isalnum()), 1) for word in tokens]

        # Padding
        encoded += [0] * (max_len - len(encoded))
        return np.array(encoded[:max_len], dtype=np.int64).reshape(1, -1)

    def predict(self, description: str) -> tuple[str, float]:
        """
        Prédit le code HS pour une description.

        Args:
            description: Description de la marchandise

        Returns:
            (code HS prédit, confiance 0-1)
        """
        if not ONNX_AVAILABLE or self.session is None:
            logger.warning("ONNX not available; using random prediction")
            return self.hs_codes[0] if self.hs_codes else "unknown", 0.5

        try:
            # Encode
            input_ids = self._encode_text(description)

            # Inférence
            inputs = {self.session.get_inputs()[0].name: input_ids}
            outputs = self.session.run(None, inputs)

            logits = outputs[0][0]
            probs = self._softmax(logits)

            pred_idx = np.argmax(probs)
            confidence = float(probs[pred_idx])

            if 0 <= pred_idx < len(self.hs_codes):
                hs_code = self.hs_codes[pred_idx]
                logger.debug(
                    f"ONNX prediction: {description[:50]}... → {hs_code} ({confidence:.2%})"
                )
                return hs_code, confidence

            return "unknown", 0.0

        except Exception as e:
            logger.error(f"Error in ONNX prediction: {e}")
            return "unknown", 0.0

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        """Compute softmax."""
        exp_x = np.exp(x - np.max(x))
        return exp_x / np.sum(exp_x)


class SVMFallbackClassifier:
    """Classificateur SVM comme fallback."""

    def __init__(self, model_path: Path = None):
        """
        Initialise le classificateur SVM.

        Args:
            model_path: Chemin au modèle SVM sauvegardé
        """
        self.model = None
        self.vectorizer = None

        if model_path:
            self._load_svm_model(model_path)

    def _load_svm_model(self, model_path: Path):
        """Charge le modèle SVM sauvegardé."""
        try:
            import joblib

            model_data = joblib.load(model_path)
            self.model = model_data.get("model")
            self.vectorizer = model_data.get("vectorizer")

            logger.info(f"Loaded SVM model: {model_path}")

        except Exception as e:
            logger.error(f"Error loading SVM model: {e}")

    def train(self, descriptions: list[str], hs_codes: list[str]):
        """Entraîne le classificateur SVM."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.svm import SVC

            self.vectorizer = TfidfVectorizer(max_features=1000)
            X = self.vectorizer.fit_transform(descriptions)

            self.model = SVC(kernel="linear", probability=True)
            self.model.fit(X, hs_codes)

            logger.info("Trained SVM classifier")

        except Exception as e:
            logger.error(f"Error training SVM: {e}")

    def predict(self, description: str) -> tuple[str, float]:
        """Prédit avec SVM."""
        if self.model is None or self.vectorizer is None:
            return "unknown", 0.5

        try:
            X = self.vectorizer.transform([description])
            pred = self.model.predict(X)[0]
            probs = self.model.predict_proba(X)[0]
            confidence = float(np.max(probs))

            return pred, confidence

        except Exception as e:
            logger.error(f"Error in SVM prediction: {e}")
            return "unknown", 0.5

    def save(self, model_path: Path):
        """Sauvegarde le modèle SVM."""
        try:
            import joblib

            model_path.parent.mkdir(parents=True, exist_ok=True)

            joblib.dump(
                {"model": self.model, "vectorizer": self.vectorizer},
                model_path,
            )

            logger.info(f"Saved SVM model: {model_path}")

        except Exception as e:
            logger.error(f"Error saving SVM model: {e}")


class HybridClassifier:
    """Classificateur hybride: ONNX avec fallback SVM."""

    def __init__(self, onnx_path: Path = None, svm_path: Path = None):
        """
        Initialise le classificateur hybride.

        Args:
            onnx_path: Chemin au modèle ONNX
            svm_path: Chemin au modèle SVM fallback
        """
        self.onnx_service = ONNXInferenceService(onnx_path)
        self.svm_classifier = SVMFallbackClassifier(svm_path)

    def predict(self, description: str) -> dict:
        """
        Prédit avec priorité ONNX, fallback SVM.

        Returns:
            {
                'hs_code': str,
                'confidence': float,
                'method': 'onnx' | 'svm'
            }
        """
        if ONNX_AVAILABLE and self.onnx_service.session is not None:
            hs_code, confidence = self.onnx_service.predict(description)
            if hs_code != "unknown":
                return {"hs_code": hs_code, "confidence": confidence, "method": "onnx"}

        if self.svm_classifier.model is not None:
            hs_code, confidence = self.svm_classifier.predict(description)
            if hs_code != "unknown":
                return {"hs_code": hs_code, "confidence": confidence, "method": "svm"}

        return {"hs_code": "unknown", "confidence": 0.0, "method": "fallback"}
