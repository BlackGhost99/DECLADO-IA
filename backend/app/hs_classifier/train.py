"""Train script for HS classifier baseline."""

import csv
from pathlib import Path

from .model import build_pipeline, train_and_save
from .preprocess import prepare_corpus


def load_csv(path: str):
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(r)
    return rows


def train_from_csv(csv_path: str, out_path: str = None):
    rows = load_csv(csv_path)
    texts = [r["text"] for r in rows]
    labels = [r["hs_code"] for r in rows]
    X = prepare_corpus(texts)
    import numpy as np

    labels_arr = np.array(labels)  # ensure numpy array for sklearn
    pipe = train_and_save(X, labels_arr, out_path=out_path)
    return pipe


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--out", required=False)
    args = parser.parse_args()
    train_from_csv(args.csv, args.out)
