"""
Script pour réentraîner le classificateur HS avec un CSV fourni.

Usage:
  python scripts/retrain_hs_classifier.py --csv backend/data/hs_training_data.csv \
                                          --out backend/models/hs_classifier.joblib
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.hs_classifier.model import predict_topk  # noqa: E402
from app.hs_classifier.preprocess import prepare_corpus  # noqa: E402
from app.hs_classifier.train import train_from_csv  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrain HS classifier from CSV")
    parser.add_argument(
        "--csv",
        type=str,
        default=str(backend_dir / "data" / "hs_training_data.csv"),
        help="Path to training CSV with columns: text,hs_code",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(backend_dir / "models" / "hs_classifier.joblib"),
        help="Output path for trained joblib model",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    out_path = Path(args.out)

    print("📚 Training HS classifier...")
    print(f"   Dataset: {csv_path}")
    print(f"   Output: {out_path}")

    if not csv_path.exists():
        print(f"❌ Dataset not found: {csv_path}")
        return 1

    # Train
    pipe = train_from_csv(str(csv_path), str(out_path))

    print("✅ Model trained successfully!")
    print(f"   Classes: {len(pipe.classes_)}")
    print(f"   Examples: {list(pipe.classes_[:10])}")

    # Quick smoke test
    test_texts = [
        "T-shirt en coton",
        "Smartphone Samsung",
        "Café en grains",
    ]

    print("\n🧪 Testing predictions:")
    for text in test_texts:
        X = prepare_corpus([text])
        topk = predict_topk(pipe, X, k=3)[0]

        print(f"\n   '{text}':")
        for code, score in topk:
            print(f"      → {code} (confidence: {score:.2%})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
