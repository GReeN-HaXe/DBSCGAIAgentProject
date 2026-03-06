from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import apply_external_review, reconstruct_external_match


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct turn/phase info and apply review metadata to a Phase 9 external match.")
    parser.add_argument("--input", type=Path, required=True, help="Phase 9 external match JSON path.")
    parser.add_argument("--reviewer", type=str, default="system", help="Reviewer label.")
    parser.add_argument("--review-status", type=str, default="reviewed", help="Review status to stamp.")
    parser.add_argument("--notes", type=str, default="", help="Optional review notes.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase9_external_match_reviewed.json"), help="Output JSON path.")
    args = parser.parse_args()

    reconstructed = reconstruct_external_match(_load_json(args.input))
    reviewed = apply_external_review(
        reconstructed,
        reviewer=str(args.reviewer),
        review_status=str(args.review_status),
        notes=str(args.notes),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reviewed, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
