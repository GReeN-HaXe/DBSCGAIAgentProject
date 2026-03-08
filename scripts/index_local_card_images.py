from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import index_local_card_images


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Index local card images by matching filename card numbers to dbs_masters.db.")
    parser.add_argument("--image-dir", type=Path, required=True, help="Directory containing local card image files.")
    parser.add_argument("--db-path", type=Path, default=Path("dbdatabase/dbs_masters.db"), help="SQLite DB path.")
    parser.add_argument("--output-json", type=Path, default=Path("artifacts/card_image_index.json"), help="Output JSON manifest path.")
    parser.add_argument("--output-matched-csv", type=Path, default=Path("artifacts/card_image_index_matched.csv"), help="Matched rows CSV output path.")
    parser.add_argument("--output-unmatched-csv", type=Path, default=Path("artifacts/card_image_index_unmatched.csv"), help="Unmatched rows CSV output path.")
    args = parser.parse_args()

    payload = index_local_card_images(args.image_dir, args.db_path)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_csv(args.output_matched_csv, list(payload.get("matched", [])))
    _write_csv(args.output_unmatched_csv, list(payload.get("unmatched", [])))
    print(f"wrote: {args.output_json}")
    print(f"matched_count={payload.get('matched_count', 0)} unmatched_count={payload.get('unmatched_count', 0)}")


if __name__ == "__main__":
    main()
