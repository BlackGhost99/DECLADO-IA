from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import List, Tuple


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            dele = prev[j] + 1
            sub = prev[j - 1] + (ca != cb)
            cur.append(min(ins, dele, sub))
        prev = cur
    return prev[-1]


def compute_cer_from_outputs(outputs_dir: str) -> Tuple[int, List[float]]:
    exts = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
    cer_values: List[float] = []
    n = 0
    for fn in os.listdir(outputs_dir):
        if not fn.lower().endswith(".json"):
            continue
        src_base = Path(fn).with_suffix("").name
        json_path = os.path.join(outputs_dir, fn)
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        full_text = "\n".join(p.get("text", "") for p in data.get("pages", []))
        # find gt file by checking typical raw locations; assume sibling in data/raw or same folder
        candidates = []
        for raw_dir in (os.path.join("data", "raw"), os.path.dirname(outputs_dir)):
            for ext in exts:
                cand = os.path.join(raw_dir, src_base + ext)
                gt = os.path.splitext(cand)[0] + ".gt.txt"
                candidates.append(gt)
        gt_path = next((c for c in candidates if os.path.exists(c)), None)
        if gt_path is None:
            continue
        with open(gt_path, "r", encoding="utf-8", errors="ignore") as f:
            gt_text = f.read().strip()
        if not gt_text:
            continue
        dist = _levenshtein(full_text, gt_text)
        cer = dist / max(1, len(gt_text))
        cer_values.append(cer)
        n += 1
    return n, cer_values


def main():
    if len(sys.argv) < 3:
        print("Usage: python -m app.ocr_pipeline.eval <outputs_dir> <metrics_json>")
        sys.exit(2)
    outputs_dir = sys.argv[1]
    metrics_json = sys.argv[2]
    n, vals = compute_cer_from_outputs(outputs_dir)
    out = {
        "description": "Aggregate OCR Character Error Rate (CER) baseline computed from available ground truths (*.gt.txt).",
        "num_samples": n,
        "cer_mean": (sum(vals) / len(vals)) if vals else None,
        "cer_median": (sorted(vals)[len(vals)//2] if vals else None),
    }
    os.makedirs(os.path.dirname(metrics_json), exist_ok=True)
    with open(metrics_json, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
