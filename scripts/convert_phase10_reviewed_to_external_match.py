from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import reviewed_detections_to_external_match


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert reviewed Phase 10 detections into a Phase 9 external-match artifact.")
    parser.add_argument("--input", type=Path, required=True, help="Reviewed detection manifest JSON path.")
    parser.add_argument("--match-id", type=str, required=True, help="External match identifier.")
    parser.add_argument("--source-name", type=str, default="phase10_review", help="Source name to store on the external-match artifact.")
    parser.add_argument("--reviewer", type=str, default="phase10_system", help="Reviewer label for the external match.")
    parser.add_argument("--review-status", type=str, default="reviewed", help="Review status for the external match.")
    parser.add_argument("--notes", type=str, default="", help="Optional notes.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase10_external_match.json"), help="External match output path.")
    args = parser.parse_args()

    payload = reviewed_detections_to_external_match(
        _load_json(args.input),
        match_id=str(args.match_id),
        source_name=str(args.source_name),
        reviewer=str(args.reviewer),
        review_status=str(args.review_status),
        notes=str(args.notes),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
