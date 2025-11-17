# OCR Pipeline (Base)

This module provides a local, robust OCR and table extraction pipeline for PDFs and images.

## Components

- Preprocessing: OpenCV (deskew, denoise, binarize, contrast)
- OCR: Tesseract via pytesseract (languages: eng+fra by default)
- PDF handling: pdfplumber (digital PDFs), pdf2image (scanned PDFs)
- Table detection: simple contour-based detection (OpenCV)
- Normalization: dates (ISO), amounts (floats), currencies (CEMAC mapping)
- Metrics: Character Error Rate (CER) baseline when ground truth exists (`*.gt.txt`)

## Installation prerequisites (Windows)

- Tesseract OCR:
  - Installed automatically by `scripts/setup.ps1` (winget)
  - Verify: `tesseract --version`
- Poppler (for pdf2image rasterization, optional):
  - Download: https://github.com/oschwartz10612/poppler-windows/releases/
  - Extract and add `poppler-xx/bin` to PATH
  - Or skip rasterization if your PDFs are digital (text layer present)

## Usage (CLI)

```
# Process all documents under data/raw and write JSON to data/outputs
cd backend
./venv/Scripts/Activate.ps1
python -m app.ocr_pipeline.cli ..\data\raw ..\data\outputs --lang eng+fra
```

## DVC Integration

`dvc.yaml` defines two stages:
- `ocr_pipeline`: runs the OCR pipeline over `data/raw` ⇒ `data/outputs`
- `ocr_eval`: computes the aggregate CER baseline at `data/metrics/cer.json`

```
dvc repro ocr_eval
```

## API Endpoint

- `POST /api/ocr/process`
  - multipart upload: `file` (PDF/PNG/JPG/TIFF)
  - form fields: `lang` (default `eng+fra`)
  - alternative: `local_path` form field (for Electron dev), mutually exclusive with `file`

Response example (truncated):
```
{
  "source": "data/raw/invoice1.pdf",
  "num_pages": 2,
  "pages": [
    { "page_index": 0, "text": "...", "words": [...], "tables": [...] },
    { "page_index": 1, "text": "...", "words": [...], "tables": [...] }
  ],
  "normalized": { "dates": ["2024-01-12"], "amounts": [1500.5], "currencies": ["XAF"] },
  "cer": 0.18,
  "warnings": []
}
```

## Ground Truth & CER

To compute CER for a sample, place a file with the same basename next to the input named `*.gt.txt` containing the expected plain text.

Example:
```
# Input
data/raw/sample1.png
# Ground truth
data/raw/sample1.gt.txt
```

The evaluation stage aggregates per-sample CER into `data/metrics/cer.json`.
