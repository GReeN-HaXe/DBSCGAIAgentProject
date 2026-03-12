from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.trace_summary import (
    compute_trace_kpis,
    decision_trace_to_csv_rows,
    per_phase_kpi_rows,
    per_turn_kpi_rows,
    summarize_trace,
)

def print_summary(summary: dict[str, object], kpis: dict[str, object]) -> None:
    print("AI Trace Summary")
    print("================")
    print(f"total_actions: {summary.get('total_actions')}")
    print(f"total_decisions: {summary.get('total_decisions')}")
    print(f"turn_number: {summary.get('turn_number')}")
    print(f"winner_id: {summary.get('winner_id')}")
    print("")
    print("KPIs")
    print(f"  avg_top1_score: {float(kpis.get('avg_top1_score', 0.0)):.3f}")
    print(f"  avg_candidate_count: {float(kpis.get('avg_candidate_count', 0.0)):.3f}")
    print(f"  attack_rate: {float(kpis.get('attack_rate', 0.0)):.3f}")
    print(f"  play_rate: {float(kpis.get('play_rate', 0.0)):.3f}")
    print(f"  end_turn_rate: {float(kpis.get('end_turn_rate', 0.0)):.3f}")
    print("")
    actions = summary.get("actions_by_player", {})
    reasons = summary.get("top_reasons_by_player", {})
    if isinstance(actions, dict):
        for pid in sorted(actions.keys()):
            print(f"Player {pid}")
            print(f"  actions: {actions[pid]}")
            if isinstance(reasons, dict) and pid in reasons:
                print(f"  top reasons: {reasons[pid]}")
            print("")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize AI match trace JSON.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("artifacts/ai_match_trace.json"),
        help="Path to AI trace JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write summary JSON.",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=None,
        help="Optional path to write per-decision CSV rows.",
    )
    parser.add_argument(
        "--turn-kpi-csv",
        type=Path,
        default=None,
        help="Optional path to write per-turn KPI CSV rows.",
    )
    parser.add_argument(
        "--phase-kpi-csv",
        type=Path,
        default=None,
        help="Optional path to write per-phase KPI CSV rows.",
    )
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    summary = summarize_trace(payload)
    kpis = compute_trace_kpis(payload)
    print_summary(summary, kpis)
    if args.output is not None:
        out_payload = dict(summary)
        out_payload["kpis"] = kpis
        out_payload["per_turn_kpis"] = per_turn_kpi_rows(payload)
        out_payload["per_phase_kpis"] = per_phase_kpi_rows(payload)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
        print(f"wrote: {args.output}")
    if args.csv_output is not None:
        rows = decision_trace_to_csv_rows(payload)
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_output.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["step", "player", "turn", "phase", "chosen", "top1_reason", "top1_score"],
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote: {args.csv_output}")
    if args.turn_kpi_csv is not None:
        rows = per_turn_kpi_rows(payload)
        args.turn_kpi_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.turn_kpi_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["turn", "decisions", "declare_attack", "play_card_from_hand", "end_turn", "attack_rate", "play_rate", "end_turn_rate"],
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote: {args.turn_kpi_csv}")
    if args.phase_kpi_csv is not None:
        rows = per_phase_kpi_rows(payload)
        args.phase_kpi_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.phase_kpi_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "phase",
                    "decisions",
                    "declare_attack",
                    "play_card_from_hand",
                    "end_turn",
                    "pass_counter_window",
                    "attack_rate",
                    "play_rate",
                    "end_turn_rate",
                    "counter_pass_rate",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote: {args.phase_kpi_csv}")


if __name__ == "__main__":
    main()
