# Data directories

- raw/: Place input documents here (PDF, TIFF, JPG, PNG). For OCR baseline metrics, you can place ground truth text files next to inputs using the same basename and suffix `.gt.txt`.
- processed/: Intermediate artifacts if needed by future stages.
- outputs/: OCR pipeline outputs (JSON) will be written here by the CLI or DVC stage.
- exports/: Final export artifacts (PDF/XML) for other modules.
- referentials/: Reference data (e.g., HS codes, currency tables).
