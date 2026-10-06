from __future__ import annotations

import argparse

from .pipeline import run_batch


def main():
    parser = argparse.ArgumentParser(description="Run OCR pipeline on a directory of documents")
    parser.add_argument("input_dir", help="Folder containing PDFs/images")
    parser.add_argument("output_dir", help="Folder to write JSON outputs")
    parser.add_argument("--lang", default="eng+fra", help="Tesseract languages, e.g. 'eng+fra'")
    args = parser.parse_args()

    outs = run_batch(args.input_dir, args.output_dir, lang=args.lang)
    print(f"Wrote {len(outs)} outputs to {args.output_dir}")


if __name__ == "__main__":
    main()
