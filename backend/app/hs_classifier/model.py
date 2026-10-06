from __future__ import annotations

import os

import numpy as np
from joblib import dump, load
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

MODEL_PATH = os.path.join(os.path.dirname(__file__), "../../models/hs_classifier.joblib")


def build_pipeline(max_features: int = 20000) -> Pipeline:
    vect = TfidfVectorizer(max_features=max_features, ngram_range=(1, 2))
    svc = LinearSVC(max_iter=5000)
    # Pour petits datasets: désactiver CV en utilisant l'estimateur de base directement
    # Alternative: utiliser CalibratedClassifierCV avec cv=2 pour datasets > 2 samples/class
    # clf = CalibratedClassifierCV(svc, method="sigmoid", cv=2)
    pipe = Pipeline([("vect", vect), ("clf", svc)])
    return pipe


def train_and_save(X: list[str], y: list[str], out_path: str = None) -> Pipeline:
    pipe = build_pipeline()
    pipe.fit(X, y)
    target = out_path or os.path.abspath(MODEL_PATH)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    dump(pipe, target)
    return pipe


def load_model(path: str = None) -> Pipeline:
    target = path or os.path.abspath(MODEL_PATH)
    return load(target)


def predict_topk(pipe: Pipeline, texts: list[str], k: int = 3) -> list[list[tuple[str, float]]]:
    """Return top-k (label, score) for each text."""
    # LinearSVC n'a pas predict_proba, utiliser decision_function
    if hasattr(pipe, "predict_proba"):
        probs = pipe.predict_proba(texts)
        classes = pipe.classes_
        topk = []
        for p in probs:
            idx = np.argsort(p)[::-1][:k]
            topk.append([(classes[i], float(p[i])) for i in idx])
        return topk
    else:
        # Fallback pour LinearSVC: utiliser decision_function scores
        scores = pipe.decision_function(texts)
        classes = pipe.classes_
        topk = []
        for s in scores:
            idx = np.argsort(s)[::-1][:k]
            # Normaliser les scores en "pseudo-probabilités" (softmax simplifié)
            topk.append([(classes[i], float(s[i])) for i in idx])
        return topk


def top_keywords_for_label(pipe: Pipeline, label: str, top_n: int = 6) -> list[str]:
    """Extract top features (words) for a given label using classifier coefficients.
    Works for linear models (LinearSVC wrapped in CalibratedClassifierCV).
    """
    vect = pipe.named_steps["vect"]
    clf = pipe.named_steps["clf"]

    # Get internal estimator coefficients from calibrated wrapper
    # CalibratedClassifierCV creates multiple calibrated classifiers (one per CV fold)
    # We'll use the first one's base estimator
    if hasattr(clf, "calibrated_classifiers_") and len(clf.calibrated_classifiers_) > 0:
        base = clf.calibrated_classifiers_[0].estimator
    elif hasattr(clf, "base_estimator"):
        base = clf.base_estimator
    else:
        base = clf

    try:
        coefs = base.coef_
    except Exception:
        # fallback: cannot extract
        return []

    feature_names = vect.get_feature_names_out()
    classes = pipe.classes_
    if label not in classes:
        return []
    idx = list(classes).index(label)
    coef = coefs[idx]
    top_idx = np.argsort(coef)[::-1][:top_n]
    return [feature_names[i] for i in top_idx]
