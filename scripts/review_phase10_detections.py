from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import apply_detection_review


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply human review corrections to a Phase 10 detection manifest.")
    parser.add_argument("--input", type=Path, required=True, help="Detection manifest JSON path.")
    parser.add_argument("--corrections", type=Path, required=True, help="JSON file with a list of corrections.")
    parser.add_argument("--reviewer", type=str, default="phase10_reviewer", help="Reviewer label.")
    parser.add_argument("--review-status", type=str, default="reviewed", help="Review status to stamp.")
    parser.add_argument("--notes", type=str, default="", help="Optional review notes.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase10_reviewed_detections.json"), help="Reviewed detection manifest output path.")
    args = parser.parse_args()

    corrections = json.loads(args.corrections.read_text(encoding="utf-8"))
    if not isinstance(corrections, list):
        raise ValueError("corrections JSON must be a list")
    payload = apply_detection_review(
        _load_json(args.input),
        corrections=corrections,
        reviewer=str(args.reviewer),
        review_status=str(args.review_status),
        notes=str(args.notes),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
