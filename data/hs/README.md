# HS Classification Dataset

## Overview

This directory contains training data for the HS (Harmonized System) code classification model.

## Files

### `dataset.csv`

**Format:** CSV with headers `text,hs_code`

**Columns:**
- `text`: Product description (string)
- `hs_code`: Harmonized System code (string, 4 digits)

**Statistics:**
- Total records: 40
- Unique HS codes: 10
- Samples per class: 4

**HS Code Distribution:**

| HS Code | Description | Count | Examples |
|---------|-------------|-------|----------|
| 6109 | Cotton t-shirts | 4 | "cotton t-shirt size m white", "cotton polo shirt navy" |
| 6205 | Men's shirts | 4 | "men's cotton shirt long sleeve", "women's cotton blouse" |
| 1006 | Rice | 4 | "rice white 25kg", "basmati rice premium" |
| 0306 | Frozen seafood | 4 | "frozen shrimp peeled 1kg", "frozen crab legs" |
| 8517 | Smartphones | 4 | "smartphone 6 inch 128gb", "5g smartphone 256gb" |
| 1701 | Sugar | 4 | "sugar refined 50kg bag", "cane sugar raw" |
| 7113 | Jewelry | 4 | "gold jewellery necklace", "platinum earrings" |
| 8467 | Electric tools | 4 | "electric drill 500w", "impact driver compact" |
| 1806 | Chocolate | 4 | "chocolate bar milk 100g", "white chocolate truffle" |
| 4011 | Tires | 4 | "tire car radial 16 inch", "truck tire all season" |

## Data Generation

This dataset is **synthetic** and was created manually for baseline model training. It is NOT representative of real-world product descriptions.

**Purpose:** Demonstrate the HS classification pipeline and API functionality.

## Usage

### Training

```bash
cd backend
python -m app.hs_classifier.train --csv ../data/hs/dataset.csv
```

### Loading in Python

```python
import pandas as pd

df = pd.read_csv('data/hs/dataset.csv')
print(df.head())
print(df['hs_code'].value_counts())
```

## Next Steps

For production use, this dataset should be replaced with:

1. **Real invoice data:** Extract product descriptions from actual customs declarations
2. **Larger scale:** Minimum 1000-10000 samples covering 50-200 HS codes
3. **Quality labels:** HS codes verified by customs experts
4. **Train/validation/test splits:** 70/15/15 or 80/10/10
5. **Balanced classes:** Ensure adequate representation of common product categories

## Data Collection Strategy

### Sources
- Historical customs declarations (with verified HS codes)
- E-commerce product catalogs (manually labeled)
- Public trade databases (WCO, national customs)

### Labeling Process
1. Export product descriptions from invoices
2. Manual HS code assignment by customs expert
3. Peer review and validation
4. Quality check (inter-annotator agreement)
5. Final dataset curation

### Recommended Format

```csv
text,hs_code,hs_description,source,confidence,reviewed_by,date
"cotton t-shirt white XL","6109.10","T-shirts and similar garments of cotton","invoice_2024_001",1.0,"expert_1","2024-11-01"
```

## Data Versioning

Use DVC to track dataset versions:

```bash
dvc add data/hs/dataset.csv
git add data/hs/dataset.csv.dvc
git commit -m "Add HS classification dataset v1"
dvc push
```

## Changelog

### v1.0 (2025-11-15)
- Initial synthetic dataset
- 40 samples, 10 HS codes
- 4 samples per class
- Created for baseline model training

---

**Status:** ⚠️ Synthetic Demo Data Only  
**Recommended Action:** Replace with real production data
