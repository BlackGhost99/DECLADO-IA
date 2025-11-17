from __future__ import annotations

import numpy as np

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover
    cv2 = None


def _require_cv2() -> None:
    if cv2 is None:
        raise RuntimeError(
            "OpenCV (cv2) n'est pas installé. Installez opencv-python pour les pré-traitements OCR."
        )


def to_gray(img: np.ndarray) -> np.ndarray:
    _require_cv2()
    if len(img.shape) == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def binarize(img: np.ndarray) -> np.ndarray:
    _require_cv2()
    gray = to_gray(img)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    return cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 31, 10)


def denoise(img: np.ndarray) -> np.ndarray:
    _require_cv2()
    return cv2.fastNlMeansDenoising(to_gray(img), h=10)


def deskew(img: np.ndarray) -> np.ndarray:
    _require_cv2()
    gray = to_gray(img)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.size == 0:
        return img
    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = img.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated


def enhance_contrast(img: np.ndarray) -> np.ndarray:
    _require_cv2()
    gray = to_gray(img)
    return cv2.equalizeHist(gray)


def preprocess_for_ocr(img: np.ndarray) -> np.ndarray:
    """Full preprocessing chain suitable for OCR."""
    _require_cv2()
    # Upscale small images to help OCR (target min dimension ~1200px)
    h, w = img.shape[:2]
    scale = 1.0
    target_min = 1200
    if min(h, w) < target_min:
        scale = target_min / float(min(h, w))
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    img1 = denoise(img)
    img2 = deskew(img1)
    img3 = enhance_contrast(img2)
    img4 = binarize(img3)
    return img4
