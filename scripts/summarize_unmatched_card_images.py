from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import summarize_unmatched_card_images


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


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
    parser = argparse.ArgumentParser(description="Summarize unmatched card images by true missing base card_number.")
    parser.add_argument("--index-json", type=Path, default=Path("artifacts/card_image_index.json"), help="Card image index JSON path.")
    parser.add_argument("--output-json", type=Path, default=Path("artifacts/card_image_missing_base_summary.json"), help="Missing-base summary JSON output path.")
    parser.add_argument("--output-missing-csv", type=Path, default=Path("artifacts/card_image_missing_bases.csv"), help="Missing bases CSV output path.")
    parser.add_argument("--output-junk-csv", type=Path, default=Path("artifacts/card_image_junk_files.csv"), help="Junk files CSV output path.")
    args = parser.parse_args()

    payload = summarize_unmatched_card_images(_load_json(args.index_json))
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_csv(args.output_missing_csv, list(payload.get("missing_bases", [])))
    _write_csv(args.output_junk_csv, list(payload.get("junk_files", [])))
    print(f"wrote: {args.output_json}")
    print(f"missing_base_count={payload.get('missing_base_count', 0)} junk_file_count={payload.get('junk_file_count', 0)}")


if __name__ == "__main__":
    main()
