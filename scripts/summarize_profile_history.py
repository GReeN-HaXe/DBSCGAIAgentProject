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
    format_history_summary,
    history_recent_runs_to_csv_rows,
    history_summary_to_csv_row,
    summarize_history_rows,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize historical profile matchup runs from history CSV.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("artifacts/profile_matchups_history.csv"),
        help="Path to history CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write summary JSON.",
    )
    parser.add_argument(
        "--recent-window",
        type=int,
        default=5,
        help="Number of most recent runs to compute trend metrics from.",
    )
    parser.add_argument(
        "--seat-bias-alert-threshold",
        type=float,
        default=0.15,
        help="Absolute seat-bias delta threshold to flag alert runs.",
    )
    parser.add_argument(
        "--decisive-rate-alert-threshold",
        type=float,
        default=0.30,
        help="Decisive-rate threshold to flag draw-heavy/inconclusive runs.",
    )
    parser.add_argument(
        "--min-runs-for-ready",
        type=int,
        default=5,
        help="Minimum history runs required before marking ready for next phase.",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=None,
        help="Optional path to write one-row summary CSV.",
    )
    parser.add_argument(
        "--recent-runs-csv",
        type=Path,
        default=None,
        help="Optional path to write latest N raw history rows as CSV.",
    )
    parser.add_argument(
        "--recent-runs-window",
        type=int,
        default=10,
        help="How many latest runs to include in --recent-runs-csv.",
    )
    args = parser.parse_args()

    rows: list[dict[str, str]] = []
    with args.input.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(dict(row))

    summary = summarize_history_rows(
        rows,
        recent_window=max(1, args.recent_window),
        seat_bias_alert_threshold=float(args.seat_bias_alert_threshold),
        decisive_rate_alert_threshold=float(args.decisive_rate_alert_threshold),
        min_runs_for_ready=max(1, args.min_runs_for_ready),
    )
    print(format_history_summary(summary))

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"wrote: {args.output}")
    if args.csv_output is not None:
        row = history_summary_to_csv_row(summary)
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_output.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)
        print(f"wrote: {args.csv_output}")
    if args.recent_runs_csv is not None:
        rows_out = history_recent_runs_to_csv_rows(rows, recent_window=max(1, args.recent_runs_window))
        args.recent_runs_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.recent_runs_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "timestamp_utc",
                    "recommended_profile",
                    "recommendation_reason",
                    "recommendation_reliable",
                    "seat_bias_p1_minus_p2",
                    "match_quality_decisive_rate",
                    "match_quality_draw_rate",
                    "match_quality_low_decisive_rate_alert",
                    "profiles",
                    "games_per_matchup",
                    "max_actions",
                    "shuffle_decks",
                    "seat_balanced",
                    "seed",
                    "source_json",
                ],
            )
            writer.writeheader()
            writer.writerows(rows_out)
        print(f"wrote: {args.recent_runs_csv}")


if __name__ == "__main__":
    main()
