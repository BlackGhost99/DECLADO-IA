# HS Classifier V1 - Baseline Implementation

## Overview

This document describes the first iteration of the HS code classification system using a TF-IDF + SVM baseline approach.

## Architecture

### Pipeline Components

1. **Text Preprocessing** (`app/hs_classifier/preprocess.py`)
   - Lowercasing
   - Punctuation removal (preserving + and -)
   - Whitespace normalization

2. **Feature Extraction**
   - TF-IDF Vectorizer
   - max_features: 20,000
   - n-gram range: (1, 2) — unigrams and bigrams

3. **Classification Model**
   - LinearSVC (scikit-learn)
   - Wrapped in CalibratedClassifierCV for probability scores
   - CV folds: 2 (suitable for small datasets)

4. **Keyword Extraction**
   - Extracts top influencing words using SVM coefficients
   - Returns top N TF-IDF features per class

## Files Created

### Core Module
- `backend/app/hs_classifier/__init__.py` — Package initialization
- `backend/app/hs_classifier/types.py` — Suggestion dataclass
- `backend/app/hs_classifier/preprocess.py` — Text cleaning utilities
- `backend/app/hs_classifier/model.py` — Pipeline build, train, predict, keyword extraction
- `backend/app/hs_classifier/train.py` — CLI training script

### API
- `backend/app/api/hs_classification.py` — FastAPI route for `/hs/suggest`

### Data
- `data/hs/dataset.csv` — Synthetic training dataset (40 samples, 10 HS codes)

### Model Artifact
- `backend/models/hs_classifier.joblib` — Trained model (TF-IDF + calibrated SVM)

### Tests
- `backend/tests/test_hs_classifier.py` — Unit test for train/predict pipeline

## Dataset

### Synthetic Training Data
- **Total samples:** 40
- **Unique HS codes:** 10
- **Samples per class:** 4
- **HS codes included:**
  - 6109 — Cotton t-shirts
  - 6205 — Men's shirts
  - 1006 — Rice
  - 0306 — Frozen seafood (shrimp, prawns, lobster)
  - 8517 — Smartphones
  - 1701 — Sugar
  - 7113 — Jewelry (gold, silver, platinum)
  - 8467 — Electric drills/tools
  - 1806 — Chocolate
  - 4011 — Tires

## API Endpoint

### POST `/api/hs/suggest`

**Request Schema:**
```json
{
  "text": "product description here",
  "k": 3
}
```

**Response Schema:**
```json
{
  "suggestions": [
    {
      "code": "6109",
      "score": 0.5957,
      "keywords": ["cotton", "hoodie", "grey", "cotton hoodie", "hoodie grey"]
    },
    {
      "code": "6205",
      "score": 0.2725,
      "keywords": ["shirt", "linen", "short", "sleeve", "short sleeve"]
    },
    {
      "code": "1806",
      "score": 0.0708,
      "keywords": ["chocolate", "dark", "pralines", "white", "truffle"]
    }
  ]
}
```

**Parameters:**
- `text` (required): Product description to classify
- `k` (optional, default=3): Number of top predictions to return

**Returns:**
- Top-k HS code suggestions sorted by confidence score (descending)
- Each suggestion includes:
  - `code`: HS code (string)
  - `score`: Confidence score (0-1 float)
  - `keywords`: List of influential words for this prediction (top 5)

## Training

### Command Line

```bash
cd backend
python -m app.hs_classifier.train --csv ../data/hs/dataset.csv
```

### Programmatic

```python
from app.hs_classifier.train import train_from_csv

pipe = train_from_csv('data/hs/dataset.csv', out_path='models/hs_classifier.joblib')
```

## Testing

### Unit Tests

```bash
cd backend
python -m pytest backend/tests/test_hs_classifier.py -v
```

**Test Coverage:**
- Train model from CSV
- Save model to joblib
- Load model and predict top-k
- Verify correct HS code in top-3

### API Integration Test

```python
import requests

url = "http://127.0.0.1:8000/api/hs/suggest"
payload = {"text": "cotton t-shirt white large", "k": 3}
resp = requests.post(url, json=payload)

assert resp.status_code == 200
data = resp.json()
assert len(data["suggestions"]) == 3
assert data["suggestions"][0]["code"] == "6109"  # cotton t-shirt
```

## Performance Metrics

### Validation Results (Synthetic Dataset)

Given the small synthetic dataset, formal validation metrics are not yet available. The model was trained on all 40 samples for demonstration purposes.

**Next Steps for Evaluation:**
1. Split dataset into train/validation (80/20)
2. Calculate top-3 accuracy
3. Generate confusion matrix
4. Analyze error cases (misclassifications)
5. Compute precision/recall per class

### Expected Baseline Performance

For a production model with a larger real-world dataset:
- **Top-1 accuracy:** 60-75%
- **Top-3 accuracy:** 80-90%
- **Top-5 accuracy:** 90-95%

## Acceptance Criteria

✅ **Completed:**
- TF-IDF vectorizer with ngrams (1,2)
- LinearSVC with probability calibration
- Top-3 predictions with scores
- Keyword extraction from coefficients
- API endpoint `/hs/suggest` functional
- Model saved as joblib artifact
- Unit tests passing

⏳ **Pending (Next Iteration):**
- Real training dataset (product descriptions → HS codes)
- Train/validation split
- Top-3 accuracy measurement
- Confusion matrix analysis
- Error case documentation
- DVC pipeline integration

## Known Limitations

1. **Small Dataset:** Only 40 synthetic samples (not representative of real data)
2. **No Validation Split:** Model trained on all data (no held-out test set)
3. **Limited HS Code Coverage:** Only 10 codes (real taxonomy has thousands)
4. **No Hierarchical Structure:** Doesn't leverage HS code hierarchy (e.g., 6109 is a subclass of 61)
5. **Backend Restart Required:** After model updates, uvicorn must reload for changes to take effect

## Future Improvements

### Short-term (V2)
- [ ] Acquire real training dataset (min 1000 samples, 50+ HS codes)
- [ ] Add train/val/test split
- [ ] Implement proper evaluation metrics
- [ ] Add data versioning with DVC
- [ ] Document error cases and failure modes

### Medium-term (V3+)
- [ ] Hierarchical classification (predict at chapter → heading → subheading levels)
- [ ] Fine-tuned transformer model (e.g., DistilBERT, CamemBERT for French support)
- [ ] Active learning loop (flag low-confidence predictions for manual review)
- [ ] Multi-language support (English + French product descriptions)
- [ ] Integration with OCR pipeline (extract product text from invoices)

### Long-term
- [ ] Ensemble models (combine TF-IDF + transformer + rule-based)
- [ ] Context-aware classification (use full invoice context, not just product line)
- [ ] Integration with CEMAC tax calculation rules
- [ ] Automated retraining pipeline on feedback data

## DVC Integration (TODO)

Add to `dvc.yaml`:

```yaml
stages:
  hs_train:
    cmd: python -m app.hs_classifier.train --csv data/hs/train.csv --out models/hs_classifier.joblib
    deps:
      - data/hs/train.csv
      - app/hs_classifier/train.py
      - app/hs_classifier/model.py
    outs:
      - models/hs_classifier.joblib
    metrics:
      - metrics/hs_classifier_train.json:
          cache: false

  hs_evaluate:
    cmd: python -m app.hs_classifier.evaluate --model models/hs_classifier.joblib --test data/hs/test.csv --out metrics/hs_classifier_eval.json
    deps:
      - models/hs_classifier.joblib
      - data/hs/test.csv
    metrics:
      - metrics/hs_classifier_eval.json:
          cache: false
```

## References

- Scikit-learn TF-IDF: https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html
- LinearSVC: https://scikit-learn.org/stable/modules/generated/sklearn.svm.LinearSVC.html
- CalibratedClassifierCV: https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html
- HS Code taxonomy: https://www.wcoomd.org/en/topics/nomenclature/instrument-and-tools/hs-nomenclature-2022-edition.aspx

## Contact

For questions or issues, consult the main project README or create a GitHub issue.

---

**Version:** 1.0  
**Date:** 2025-11-15  
**Status:** ✅ Baseline Complete
