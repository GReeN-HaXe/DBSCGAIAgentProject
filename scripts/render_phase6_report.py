from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a markdown report from Phase 6 artifacts.")
    parser.add_argument("--summary", type=Path, required=True, help="Path to human_vs_ai_summary.json")
    parser.add_argument("--play-result", type=Path, default=None, help="Path to play result JSON.")
    parser.add_argument("--replay", type=Path, default=None, help="Path to replay_result JSON.")
    parser.add_argument("--replay-result", type=Path, default=None, help="Path to replay expectation result JSON.")
    parser.add_argument("--history-summary", type=Path, default=None, help="Path to history summary JSON.")
    parser.add_argument("--stage-timings", type=Path, default=None, help="Path to stage timings JSON.")
    parser.add_argument("--timing-regression", type=Path, default=None, help="Path to timing regression JSON.")
    parser.add_argument("--timing-history-summary", type=Path, default=None, help="Path to timing history summary JSON.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase6_report.md"), help="Markdown report path.")
    args = parser.parse_args()

    summary = _load_json(args.summary)
    play_result = _load_json(args.play_result) if args.play_result is not None else {}
    replay = _load_json(args.replay) if args.replay is not None else {}
    replay_result = _load_json(args.replay_result) if args.replay_result is not None else {}
    history_summary = _load_json(args.history_summary) if args.history_summary is not None else {}
    stage_timings = _load_json(args.stage_timings) if args.stage_timings is not None else {}
    timing_regression = _load_json(args.timing_regression) if args.timing_regression is not None else {}
    timing_history_summary = _load_json(args.timing_history_summary) if args.timing_history_summary is not None else {}

    lines: list[str] = []
    lines.append("# Phase 6 Run Report")
    lines.append("")
    lines.append("## Match Summary")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    for key in [
        "winner_id",
        "total_actions",
        "human_player_id",
        "ai_profile",
        "final_turn_number",
        "final_phase",
        "checkpoint_count",
        "effect_resolution_count",
        "effect_unresolved_count",
    ]:
        lines.append(f"| {key} | {summary.get(key, '')} |")
    lines.append("")

    setup = summary.get("setup", {})
    if isinstance(setup, dict) and setup:
        lines.append("## Setup")
        lines.append("")
        lines.append("| Key | Value |")
        lines.append("|---|---|")
        for k in sorted(setup.keys()):
            lines.append(f"| {k} | {setup.get(k)} |")
        lines.append("")

    lines.append("## Gates")
    lines.append("")
    lines.append(f"- play_ok: `{play_result.get('ok', '')}`")
    lines.append(f"- replay_ok: `{replay_result.get('ok', '')}`")
    lines.append(f"- replay_trace_hash: `{replay.get('trace_hash', '')}`")
    lines.append("")

    tail = summary.get("checkpoint_tail", [])
    if isinstance(tail, list) and tail:
        lines.append("## Checkpoint Tail")
        lines.append("")
        for cp in tail:
            lines.append(f"- {cp}")
        lines.append("")

    if history_summary:
        lines.append("## History Trend")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|---|---|")
        for key in [
            "total_runs",
            "recent_window",
            "pass_rate_total",
            "pass_rate_recent",
            "determinism_checks_recent",
            "determinism_pass_rate_recent",
            "overall_status",
            "is_ready",
            "recommended_action",
        ]:
            lines.append(f"| {key} | {history_summary.get(key, '')} |")
        lines.append("")

    if stage_timings:
        summary_block = stage_timings.get("summary", {})
        lines.append("## Pipeline Timings")
        lines.append("")
        if isinstance(summary_block, dict):
            lines.append(f"- total_seconds: `{summary_block.get('total_seconds', '')}`")
            lines.append(f"- slowest_stage: `{summary_block.get('slowest_stage', '')}`")
            lines.append(f"- slowest_seconds: `{summary_block.get('slowest_seconds', '')}`")
            lines.append("")
        rows = stage_timings.get("stages", [])
        if isinstance(rows, list) and rows:
            lines.append("| Stage | Duration (s) |")
            lines.append("|---|---|")
            for row in rows:
                if isinstance(row, dict):
                    lines.append(f"| {row.get('name', '')} | {row.get('duration_seconds', '')} |")
            lines.append("")

    if timing_regression:
        lines.append("## Timing Regression")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|---|---|")
        for key in [
            "has_baseline",
            "regressed",
            "current_total_seconds",
            "baseline_total_seconds",
            "ratio_current_over_baseline",
            "max_total_seconds_regression_ratio",
            "reason",
        ]:
            lines.append(f"| {key} | {timing_regression.get(key, '')} |")
        lines.append("")

    if timing_history_summary:
        lines.append("## Timing History Trend")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|---|---|")
        for key in [
            "total_runs",
            "recent_window",
            "avg_total_seconds_recent",
            "max_total_seconds_recent",
            "regression_rate_recent",
            "latest_total_seconds",
        ]:
            lines.append(f"| {key} | {timing_history_summary.get(key, '')} |")
        lines.append("")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
