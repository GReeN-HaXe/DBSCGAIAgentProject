from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import summarize_pipeline_history


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Phase 6 pipeline history CSV.")
    parser.add_argument("--history-csv", type=Path, required=True, help="Path to phase6 pipeline history CSV.")
    parser.add_argument("--recent-window", type=int, default=20, help="Recent window size.")
    parser.add_argument("--min-recent-pass-rate", type=float, default=0.90, help="Minimum recent pass-rate threshold.")
    parser.add_argument("--min-determinism-pass-rate", type=float, default=1.00, help="Minimum determinism pass-rate threshold.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase6_pipeline_history_summary.json"), help="Summary JSON output path.")
    args = parser.parse_args()

    if not args.history_csv.exists():
        raise ValueError(f"history CSV not found: {args.history_csv}")
    rows: list[dict[str, str]] = []
    with args.history_csv.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append(dict(row))
    summary = summarize_pipeline_history(
        rows,
        recent_window=max(1, int(args.recent_window)),
        min_recent_pass_rate=float(args.min_recent_pass_rate),
        min_determinism_pass_rate=float(args.min_determinism_pass_rate),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
