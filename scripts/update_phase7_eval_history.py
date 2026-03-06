from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import (
    build_phase7_eval_history_row,
    phase7_eval_history_row_to_dict,
    summarize_phase7_eval_history,
)


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def _rows_from_payload(payload: dict[str, object]) -> list[dict[str, str]]:
    if isinstance(payload.get("results"), list):
        rows: list[dict[str, str]] = []
        split = str(payload.get("split", ""))
        for item in payload["results"]:
            if not isinstance(item, dict):
                continue
            row = build_phase7_eval_history_row(
                evaluator_name=str(item.get("profile", item.get("model_name", "unknown"))),
                split=split,
                target_field=str(item.get("target_field", "action_type")),
                example_count=int(item.get("example_count", 0) or 0),
                top1_accuracy=float(item.get("top1_accuracy", 0.0) or 0.0),
                family_accuracy=float(item.get("family_accuracy", 0.0) or 0.0),
            )
            rows.append(phase7_eval_history_row_to_dict(row))
        return rows
    row = build_phase7_eval_history_row(
        evaluator_name=str(payload.get("profile", payload.get("model_name", "unknown"))),
        split=str(payload.get("split", "")),
        target_field=str(payload.get("target_field", "action_type")),
        example_count=int(payload.get("example_count", 0) or 0),
        top1_accuracy=float(payload.get("top1_accuracy", 0.0) or 0.0),
        family_accuracy=float(payload.get("family_accuracy", 0.0) or 0.0),
    )
    return [phase7_eval_history_row_to_dict(row)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Append Phase 7 evaluation results to history CSV and write a summary JSON.")
    parser.add_argument("--input", type=Path, required=True, help="Evaluation or comparison JSON path.")
    parser.add_argument("--history-csv", type=Path, default=Path("artifacts/phase7_eval_history.csv"), help="History CSV path.")
    parser.add_argument("--summary-output", type=Path, default=Path("artifacts/phase7_eval_history_summary.json"), help="Summary JSON output path.")
    parser.add_argument("--recent-window", type=int, default=20, help="Recent window size for summary.")
    args = parser.parse_args()

    rows_to_add = _rows_from_payload(_load_json(args.input))
    existing_rows: list[dict[str, str]] = []
    if args.history_csv.exists():
        with args.history_csv.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                existing_rows.append(dict(row))
    args.history_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.history_csv.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows_to_add[0].keys()))
        if not existing_rows:
            writer.writeheader()
        for row in rows_to_add:
            writer.writerow(row)
    print(f"appended: {args.history_csv}")

    merged = [*existing_rows, *rows_to_add]
    summary = summarize_phase7_eval_history(merged, recent_window=max(1, int(args.recent_window)))
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote: {args.summary_output}")


if __name__ == "__main__":
    main()
