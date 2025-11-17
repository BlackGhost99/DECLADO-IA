import os
import tempfile

from app.hs_classifier.model import load_model, predict_topk
from app.hs_classifier.train import train_from_csv


def test_train_and_predict():
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    csv_path = os.path.join(base, "data", "hs", "dataset.csv")
    assert os.path.exists(csv_path)

    # train model to a temp file
    out = os.path.join(tempfile.gettempdir(), "hs_test_model.joblib")
    pipe = train_from_csv(csv_path, out_path=out)
    assert os.path.exists(out)

    # load and predict
    model = load_model(out)
    topk = predict_topk(model, ["white cotton t-shirt"], k=3)
    assert len(topk) == 1
    assert len(topk[0]) <= 3

    # check that top prediction is among known codes
    codes = [c for c, s in topk[0]]
    assert any(code in ["6109", "6205"] for code in codes)
