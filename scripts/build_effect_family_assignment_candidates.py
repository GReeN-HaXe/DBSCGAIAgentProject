from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.game.effect_family_assignment_candidates import build_effect_family_assignment_candidates_from_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Build high-confidence effect-family assignment candidates from unmapped priority cards.")
    parser.add_argument(
        "--mapping-report",
        type=Path,
        default=ROOT / "artifacts" / "effect_family_mapping_report.json",
        help="Path to effect family mapping report JSON.",
    )
    parser.add_argument(
        "--family-report",
        type=Path,
        default=ROOT / "artifacts" / "effect_family_report.json",
        help="Path to effect family report JSON.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=ROOT / "dbdatabase" / "dbs_masters.db",
        help="Path to local SQLite card DB.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=50,
        help="Maximum number of candidates to report.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "effect_family_assignment_candidates.json",
        help="Path to output candidate report JSON.",
    )
    args = parser.parse_args()

    payload = build_effect_family_assignment_candidates_from_paths(
        mapping_report_path=args.mapping_report,
        family_report_path=args.family_report,
        db_path=args.db_path,
        top_n=int(args.top_n),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Candidates: {payload['summary']['candidate_count']}")
    print(f"Auto-apply-safe candidates: {payload['summary']['auto_apply_safe_count']}")
    print(f"Wrote report: {args.output}")


if __name__ == "__main__":
    main()
