"""Extra coverage for app.hs_classifier (small synthetic corpora, tmp_path only)."""

from __future__ import annotations

import csv
import os
import runpy
import sys
import types

import numpy as np
import pytest
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from app.hs_classifier import model as hs_model
from app.hs_classifier import train as hs_train
from app.hs_classifier.preprocess import clean_text, prepare_corpus
from app.hs_classifier.types import Suggestion

CORPUS = [
    ("white cotton t-shirt", "6109"),
    ("cotton tee shirt knitted", "6109"),
    ("men cotton t-shirt short sleeve", "6109"),
    ("knitted cotton t-shirt for women", "6109"),
    ("laptop computer portable", "8471"),
    ("notebook computer with keyboard", "8471"),
    ("portable laptop processing unit", "8471"),
    ("desktop computer machine", "8471"),
    ("frozen fish fillets", "0304"),
    ("fresh fish fillet of salmon", "0304"),
    ("frozen tuna fish fillets", "0304"),
    ("fish fillets of tilapia", "0304"),
]
TEXTS = [t for t, _ in CORPUS]
LABELS = [label for _, label in CORPUS]


@pytest.fixture(scope="module")
def svc_pipe():
    return hs_model.build_pipeline().fit(TEXTS, LABELS)


class TestPreprocessAndTypes:
    def test_clean_text(self):
        assert clean_text("") == ""
        assert clean_text(None) == ""
        assert clean_text("  T-Shirt, 100% COTON!!  ") == "t-shirt 100 coton"

    def test_prepare_corpus(self):
        assert prepare_corpus(["A.B", "c  d"]) == ["a b", "c d"]

    def test_suggestion_to_dict(self):
        s = Suggestion("6109", np.float32(0.5), ["cotton"])
        assert s.score == 0.5 and isinstance(s.score, float)
        assert s.to_dict() == {"code": "6109", "score": 0.5, "keywords": ["cotton"]}


class TestModel:
    def test_build_pipeline(self):
        pipe = hs_model.build_pipeline(max_features=50)
        assert list(pipe.named_steps) == ["vect", "clf"]
        assert pipe.named_steps["vect"].max_features == 50
        assert pipe.named_steps["vect"].ngram_range == (1, 2)
        assert isinstance(pipe.named_steps["clf"], LinearSVC)

    def test_train_save_and_load_explicit_path(self, tmp_path):
        out = tmp_path / "nested" / "model.joblib"
        pipe = hs_model.train_and_save(TEXTS, LABELS, out_path=str(out))
        assert out.exists()
        loaded = hs_model.load_model(str(out))
        assert list(loaded.classes_) == list(pipe.classes_)
        assert loaded.predict(["cotton t-shirt"])[0] == "6109"

    def test_train_save_and_load_default_path(self, tmp_path, monkeypatch):
        target = tmp_path / "models" / "hs_classifier.joblib"
        monkeypatch.setattr(hs_model, "MODEL_PATH", str(target))
        hs_model.train_and_save(TEXTS, LABELS)
        assert target.exists()
        assert hs_model.load_model().predict(["frozen fish"])[0] == "0304"

    def test_predict_topk_decision_function(self, svc_pipe):
        assert not hasattr(svc_pipe, "predict_proba")
        res = hs_model.predict_topk(svc_pipe, ["laptop computer", "frozen fish"], k=2)
        assert len(res) == 2 and all(len(r) == 2 for r in res)
        assert res[0][0][0] == "8471"
        assert res[1][0][0] == "0304"
        assert res[0][0][1] >= res[0][1][1]
        assert all(isinstance(score, float) for _, score in res[0])

    def test_predict_topk_predict_proba(self):
        pipe = Pipeline([("vect", TfidfVectorizer()), ("clf", LogisticRegression())])
        pipe.fit(TEXTS, LABELS)
        res = hs_model.predict_topk(pipe, ["cotton t-shirt"], k=3)
        labels = [c for c, _ in res[0]]
        scores = [s for _, s in res[0]]
        assert labels[0] == "6109"
        assert sorted(labels) == ["0304", "6109", "8471"]
        assert scores == sorted(scores, reverse=True)
        assert sum(scores) == pytest.approx(1.0)

    def test_top_keywords_linear_svc(self, svc_pipe):
        kws = hs_model.top_keywords_for_label(svc_pipe, "0304", top_n=3)
        assert len(kws) == 3
        assert any("fish" in k or "fillet" in k for k in kws)

    def test_top_keywords_unknown_label(self, svc_pipe):
        assert hs_model.top_keywords_for_label(svc_pipe, "9999") == []

    def test_top_keywords_calibrated(self):
        pipe = Pipeline(
            [
                ("vect", TfidfVectorizer()),
                ("clf", CalibratedClassifierCV(LinearSVC(), cv=2)),
            ]
        ).fit(TEXTS, LABELS)
        kws = hs_model.top_keywords_for_label(pipe, "8471", top_n=4)
        # Keywords come from the first CV fold's LinearSVC coefficients.
        base = pipe.named_steps["clf"].calibrated_classifiers_[0].estimator
        coef = base.coef_[list(pipe.classes_).index("8471")]
        names = pipe.named_steps["vect"].get_feature_names_out()
        assert kws == [names[i] for i in np.argsort(coef)[::-1][:4]]

    def _fake_pipe(self, svc_pipe, clf):
        return types.SimpleNamespace(
            named_steps={"vect": svc_pipe.named_steps["vect"], "clf": clf},
            classes_=svc_pipe.classes_,
        )

    def test_top_keywords_base_estimator(self, svc_pipe):
        wrapper = types.SimpleNamespace(base_estimator=svc_pipe.named_steps["clf"])
        pipe = self._fake_pipe(svc_pipe, wrapper)
        assert hs_model.top_keywords_for_label(
            pipe, "6109", top_n=2
        ) == hs_model.top_keywords_for_label(svc_pipe, "6109", top_n=2)

    def test_top_keywords_without_coefficients(self, svc_pipe):
        pipe = self._fake_pipe(svc_pipe, types.SimpleNamespace())
        assert hs_model.top_keywords_for_label(pipe, "6109") == []


class TestTrain:
    def _write_csv(self, path):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["text", "hs_code"])
            writer.writeheader()
            for text, label in CORPUS:
                writer.writerow({"text": text.upper() + "!", "hs_code": label})
        return path

    def test_load_csv(self, tmp_path):
        rows = hs_train.load_csv(str(self._write_csv(tmp_path / "d.csv")))
        assert len(rows) == len(CORPUS)
        assert rows[0] == {"text": "WHITE COTTON T-SHIRT!", "hs_code": "6109"}

    def test_train_from_csv(self, tmp_path):
        csv_path = self._write_csv(tmp_path / "d.csv")
        out = tmp_path / "m.joblib"
        pipe = hs_train.train_from_csv(str(csv_path), out_path=str(out))
        assert out.exists()
        assert sorted(pipe.classes_) == ["0304", "6109", "8471"]
        assert pipe.predict(["laptop computer"])[0] == "8471"

    def test_module_entrypoint(self, tmp_path, monkeypatch):
        csv_path = self._write_csv(tmp_path / "d.csv")
        out = tmp_path / "cli.joblib"
        monkeypatch.setattr(sys, "argv", ["train", "--csv", str(csv_path), "--out", str(out)])
        monkeypatch.delitem(sys.modules, "app.hs_classifier.train", raising=False)
        runpy.run_module("app.hs_classifier.train", run_name="__main__")
        assert os.path.exists(out)
