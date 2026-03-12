from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
import re

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import (
    command_hints_from_summary,
    command_hints_to_csv_row,
    command_hints_to_json_payload,
    format_history_summary,
    history_recent_runs_to_csv_rows,
    history_summary_to_csv_row,
    summarize_history_rows,
)

HISTORY_PROFILE_PRESETS: dict[str, dict[str, float | int]] = {
    "quick": {
        "recent_window": 5,
        "recent_runs_window": 5,
        "seat_bias_alert_threshold": 0.20,
        "decisive_rate_alert_threshold": 0.25,
        "min_runs_for_ready": 3,
    },
    "standard": {
        "recent_window": 5,
        "recent_runs_window": 10,
        "seat_bias_alert_threshold": 0.15,
        "decisive_rate_alert_threshold": 0.30,
        "min_runs_for_ready": 5,
    },
    "strict": {
        "recent_window": 20,
        "recent_runs_window": 20,
        "seat_bias_alert_threshold": 0.10,
        "decisive_rate_alert_threshold": 0.40,
        "min_runs_for_ready": 10,
    },
}

TIMESTAMPED_PROFILE_ARTIFACT_RE = re.compile(r".*profile_matchups_.*_\d{8}T\d{6}Z\.[^.]+$")


def _is_timestamped_profile_artifact(path: Path) -> bool:
    return bool(TIMESTAMPED_PROFILE_ARTIFACT_RE.fullmatch(path.name))


def _cleanup_ci_artifacts(ci_artifacts_dir: Path, *, retain_latest: int) -> list[Path]:
    retain = max(1, int(retain_latest))
    candidates = [p for p in ci_artifacts_dir.glob("*") if p.is_file() and _is_timestamped_profile_artifact(p)]
    ordered = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
    to_delete = ordered[retain:]
    removed: list[Path] = []
    for path in to_delete:
        path.unlink(missing_ok=True)
        removed.append(path)
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize historical profile matchup runs from history CSV.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("artifacts/profile_matchups_history.csv"),
        help="Path to history CSV.",
    )
    parser.add_argument(
        "--ci-mode",
        action="store_true",
        help="Apply CI defaults: strict profile, machine-readable output, and failure gates.",
    )
    parser.add_argument(
        "--ci-artifacts-dir",
        type=Path,
        default=None,
        help="Directory used for default output files in CI mode.",
    )
    parser.add_argument(
        "--ci-retain-latest",
        type=int,
        default=None,
        help="When used with --ci-artifacts-dir, keep only latest N timestamped profile artifacts and delete older ones.",
    )
    parser.add_argument(
        "--print-ci-summary",
        action="store_true",
        help="Print one-line JSON CI summary at the end.",
    )
    parser.add_argument(
        "--fail-on-low-readiness-score",
        type=float,
        default=None,
        help="Exit with code 4 if readiness_score is below this threshold (0.0-1.0).",
    )
    parser.add_argument(
        "--fail-on-blockers",
        action="store_true",
        help="Exit with code 5 if readiness_blocker_count is greater than zero.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write summary JSON.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress routine wrote:* logs.",
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="",
        help="Prefix added to provided output filenames.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory to place all provided output files.",
    )
    parser.add_argument(
        "--timestamped-artifacts",
        action="store_true",
        help="Append a single UTC timestamp suffix to provided output filenames.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved plan and exit without reading/writing files.",
    )
    parser.add_argument(
        "--recent-window",
        type=int,
        default=None,
        help="Number of most recent runs to compute trend metrics from.",
    )
    parser.add_argument(
        "--seat-bias-alert-threshold",
        type=float,
        default=None,
        help="Absolute seat-bias delta threshold to flag alert runs.",
    )
    parser.add_argument(
        "--decisive-rate-alert-threshold",
        type=float,
        default=None,
        help="Decisive-rate threshold to flag draw-heavy/inconclusive runs.",
    )
    parser.add_argument(
        "--min-runs-for-ready",
        type=int,
        default=None,
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
        default=None,
        help="How many latest runs to include in --recent-runs-csv.",
    )
    parser.add_argument(
        "--history-profile",
        choices=["quick", "standard", "strict"],
        default="standard",
        help="Preset for history windows/thresholds; explicit flags override preset values.",
    )
    parser.add_argument(
        "--commands-output",
        type=Path,
        default=None,
        help="Optional path to write prioritized command hints as plain text.",
    )
    parser.add_argument(
        "--commands-csv",
        type=Path,
        default=None,
        help="Optional path to write one-row command hints CSV.",
    )
    parser.add_argument(
        "--commands-json",
        type=Path,
        default=None,
        help="Optional path to write command hints JSON payload.",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=None,
        help="Optional path to write compact metrics JSON payload.",
    )
    parser.add_argument(
        "--bundle-output",
        type=Path,
        default=None,
        help="Optional path to write combined summary+commands+metrics JSON bundle.",
    )
    parser.add_argument(
        "--print-summary-json",
        action="store_true",
        help="Print summary JSON to stdout after computing summary.",
    )
    parser.add_argument(
        "--summary-format",
        choices=["text", "json", "both", "none"],
        default="text",
        help="Primary stdout summary format. Use print-* flags for additional machine outputs.",
    )
    parser.add_argument(
        "--print-commands-json",
        action="store_true",
        help="Print one-line JSON command hints to stdout.",
    )
    parser.add_argument(
        "--print-metrics-json",
        action="store_true",
        help="Print one-line JSON with compact history health metrics.",
    )
    parser.add_argument(
        "--fail-on-not-ready",
        action="store_true",
        help="Exit with code 2 when summary is not ready for next phase.",
    )
    parser.add_argument(
        "--fail-on-status",
        choices=["warning", "critical"],
        default=None,
        help="Exit with code 3 when overall_status is at or worse than this level.",
    )
    args = parser.parse_args()

    if args.ci_mode:
        args.history_profile = "strict"
        args.print_summary_json = True
        args.fail_on_not_ready = True
        args.fail_on_blockers = True
        if args.fail_on_status is None:
            args.fail_on_status = "warning"
        if args.fail_on_low_readiness_score is None:
            args.fail_on_low_readiness_score = 0.80
        if args.ci_artifacts_dir is not None and args.ci_retain_latest is None:
            args.ci_retain_latest = 20
        if args.ci_artifacts_dir is not None:
            if args.output is None:
                args.output = args.ci_artifacts_dir / "profile_matchups_history_summary.json"
            if args.csv_output is None:
                args.csv_output = args.ci_artifacts_dir / "profile_matchups_history_summary.csv"
            if args.recent_runs_csv is None:
                args.recent_runs_csv = args.ci_artifacts_dir / "profile_matchups_history_recent.csv"
            if args.commands_output is None:
                args.commands_output = args.ci_artifacts_dir / "profile_matchups_next_commands.txt"
            if args.commands_csv is None:
                args.commands_csv = args.ci_artifacts_dir / "profile_matchups_next_commands.csv"
            if args.commands_json is None:
                args.commands_json = args.ci_artifacts_dir / "profile_matchups_next_commands.json"
            if args.metrics_output is None:
                args.metrics_output = args.ci_artifacts_dir / "profile_matchups_metrics.json"
            if args.bundle_output is None:
                args.bundle_output = args.ci_artifacts_dir / "profile_matchups_bundle.json"
    timestamp_tag = ""
    if args.timestamped_artifacts:
        timestamp_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def _decorate_path(path: Path | None) -> Path | None:
        if path is None:
            return None
        prefix = str(args.output_prefix or "").strip()
        out = path
        if prefix:
            out = out.with_name(f"{prefix}{out.name}")
        if timestamp_tag:
            out = out.with_name(f"{out.stem}_{timestamp_tag}{out.suffix}")
        if args.output_dir is not None:
            out = args.output_dir / out.name
        return out

    args.output = _decorate_path(args.output)
    args.csv_output = _decorate_path(args.csv_output)
    args.recent_runs_csv = _decorate_path(args.recent_runs_csv)
    args.commands_output = _decorate_path(args.commands_output)
    args.commands_csv = _decorate_path(args.commands_csv)
    args.commands_json = _decorate_path(args.commands_json)
    args.metrics_output = _decorate_path(args.metrics_output)
    args.bundle_output = _decorate_path(args.bundle_output)

    def log(message: str) -> None:
        if not args.quiet:
            print(message)
    preset = HISTORY_PROFILE_PRESETS[args.history_profile]
    recent_window = max(1, int(args.recent_window if args.recent_window is not None else preset["recent_window"]))
    seat_bias_alert_threshold = float(
        args.seat_bias_alert_threshold
        if args.seat_bias_alert_threshold is not None
        else preset["seat_bias_alert_threshold"]
    )
    decisive_rate_alert_threshold = float(
        args.decisive_rate_alert_threshold
        if args.decisive_rate_alert_threshold is not None
        else preset["decisive_rate_alert_threshold"]
    )
    min_runs_for_ready = max(
        1,
        int(args.min_runs_for_ready if args.min_runs_for_ready is not None else preset["min_runs_for_ready"]),
    )
    recent_runs_window = max(
        1,
        int(args.recent_runs_window if args.recent_runs_window is not None else preset["recent_runs_window"]),
    )
    if args.dry_run:
        plan = {
            "input": str(args.input),
            "history_profile": args.history_profile,
            "recent_window": recent_window,
            "recent_runs_window": recent_runs_window,
            "seat_bias_alert_threshold": seat_bias_alert_threshold,
            "decisive_rate_alert_threshold": decisive_rate_alert_threshold,
            "min_runs_for_ready": min_runs_for_ready,
            "output_prefix": str(args.output_prefix or ""),
            "output_dir": "" if args.output_dir is None else str(args.output_dir),
            "timestamped_artifacts": bool(args.timestamped_artifacts),
            "outputs": {
                "output": "" if args.output is None else str(args.output),
                "csv_output": "" if args.csv_output is None else str(args.csv_output),
                "recent_runs_csv": "" if args.recent_runs_csv is None else str(args.recent_runs_csv),
                "commands_output": "" if args.commands_output is None else str(args.commands_output),
                "commands_csv": "" if args.commands_csv is None else str(args.commands_csv),
                "commands_json": "" if args.commands_json is None else str(args.commands_json),
                "metrics_output": "" if args.metrics_output is None else str(args.metrics_output),
                "bundle_output": "" if args.bundle_output is None else str(args.bundle_output),
            },
        }
        print("dry_run_plan_json:")
        print(json.dumps(plan, indent=2))
        return

    rows: list[dict[str, str]] = []
    with args.input.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(dict(row))

    summary = summarize_history_rows(
        rows,
        recent_window=recent_window,
        seat_bias_alert_threshold=seat_bias_alert_threshold,
        decisive_rate_alert_threshold=decisive_rate_alert_threshold,
        min_runs_for_ready=min_runs_for_ready,
    )
    if args.summary_format in {"text", "both"}:
        print(format_history_summary(summary))
    if args.summary_format in {"json", "both"}:
        print("summary_json:")
        print(json.dumps(summary, indent=2))

    is_ready = bool(summary.get("is_ready_for_next_phase", False))
    overall_status = str(summary.get("overall_status", "healthy")).strip().lower()
    readiness_score = float(summary.get("readiness_score", 0.0))
    readiness_blocker_count = int(summary.get("readiness_blocker_count", 0))
    status_order = {"healthy": 0, "warning": 1, "critical": 2}
    status_gate_failed = False
    if args.fail_on_status is not None:
        target = str(args.fail_on_status).strip().lower()
        status_gate_failed = status_order.get(overall_status, 0) >= status_order.get(target, 0)
    not_ready_failed = bool(args.fail_on_not_ready and not is_ready)
    readiness_score_failed = False
    if args.fail_on_low_readiness_score is not None:
        threshold = max(0.0, min(1.0, float(args.fail_on_low_readiness_score)))
        readiness_score_failed = readiness_score < threshold
    blockers_failed = bool(args.fail_on_blockers and readiness_blocker_count > 0)
    ci_failed = bool(status_gate_failed or not_ready_failed or readiness_score_failed or blockers_failed)
    if args.print_summary_json:
        print("summary_json:")
        print(json.dumps(summary, indent=2))
    if args.print_commands_json:
        command_payload = command_hints_to_json_payload(summary)
        print(f"commands_json: {json.dumps(command_payload, separators=(',', ':'))}")
    metrics_payload = {
        "total_runs": int(summary.get("total_runs", 0)),
        "overall_status": str(summary.get("overall_status", "")),
        "is_ready_for_next_phase": bool(summary.get("is_ready_for_next_phase", False)),
        "readiness_score": float(summary.get("readiness_score", 0.0)),
        "readiness_blocker_count": int(summary.get("readiness_blocker_count", 0)),
        "recommended_action": str(summary.get("recommended_action", "")),
        "stability_label": str(summary.get("stability_label", "")),
        "quality_alert_count": int(summary.get("quality_alert_count", 0)),
        "seat_bias_alert_count": int(summary.get("seat_bias_alert_count", 0)),
        "low_decisive_rate_alert_count": int(summary.get("low_decisive_rate_alert_count", 0)),
    }
    if args.print_metrics_json:
        print(f"metrics_json: {json.dumps(metrics_payload, separators=(',', ':'))}")
    if args.print_ci_summary:
        ci_summary = {
            "ci_mode": bool(args.ci_mode),
            "status": "fail" if ci_failed else "pass",
            "not_ready_failed": not_ready_failed,
            "status_gate_failed": status_gate_failed,
            "readiness_score_failed": readiness_score_failed,
            "blockers_failed": blockers_failed,
            "overall_status": overall_status,
            "is_ready_for_next_phase": is_ready,
            "readiness_score": readiness_score,
            "readiness_blocker_count": readiness_blocker_count,
            "fail_on_status": args.fail_on_status,
            "fail_on_not_ready": bool(args.fail_on_not_ready),
            "fail_on_low_readiness_score": args.fail_on_low_readiness_score,
            "fail_on_blockers": bool(args.fail_on_blockers),
        }
        print(f"ci_summary_json: {json.dumps(ci_summary, separators=(',', ':'))}")

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        log(f"wrote: {args.output}")
    if args.csv_output is not None:
        row = history_summary_to_csv_row(summary)
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_output.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)
        log(f"wrote: {args.csv_output}")
    if args.recent_runs_csv is not None:
        rows_out = history_recent_runs_to_csv_rows(rows, recent_window=recent_runs_window)
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
        log(f"wrote: {args.recent_runs_csv}")
    if args.commands_output is not None:
        hints = command_hints_from_summary(summary)
        lines = [
            f"prioritized_next_step: {hints.get('prioritized_next_step', '')}",
            f"next_command_hint: {hints.get('next_command_hint', '')}",
            f"followup_command_hint: {hints.get('followup_command_hint', '')}",
            f"next_command_sequence_shell: {hints.get('next_command_sequence_shell', '')}",
            f"next_command_sequence_powershell: {hints.get('next_command_sequence_powershell', '')}",
            f"next_command_sequence_bash: {hints.get('next_command_sequence_bash', '')}",
            "next_command_sequence_multiline:",
            str(hints.get("next_command_sequence_multiline", "")),
        ]
        args.commands_output.parent.mkdir(parents=True, exist_ok=True)
        args.commands_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log(f"wrote: {args.commands_output}")
    if args.commands_csv is not None:
        row = command_hints_to_csv_row(summary)
        args.commands_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.commands_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)
        log(f"wrote: {args.commands_csv}")
    if args.commands_json is not None:
        payload = command_hints_to_json_payload(summary)
        args.commands_json.parent.mkdir(parents=True, exist_ok=True)
        args.commands_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log(f"wrote: {args.commands_json}")
    if args.metrics_output is not None:
        args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
        args.metrics_output.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")
        log(f"wrote: {args.metrics_output}")
    if args.bundle_output is not None:
        bundle_payload = {
            "summary": summary,
            "commands": command_hints_to_json_payload(summary),
            "metrics": metrics_payload,
        }
        args.bundle_output.parent.mkdir(parents=True, exist_ok=True)
        args.bundle_output.write_text(json.dumps(bundle_payload, indent=2), encoding="utf-8")
        log(f"wrote: {args.bundle_output}")

    if args.ci_artifacts_dir is not None and args.ci_retain_latest is not None:
        removed = _cleanup_ci_artifacts(args.ci_artifacts_dir, retain_latest=max(1, int(args.ci_retain_latest)))
        log(f"ci_cleanup_removed_files: {len(removed)} (retain_latest={max(1, int(args.ci_retain_latest))})")

    if not_ready_failed:
        print("summary_failed_not_ready: True")
        sys.exit(2)
    if status_gate_failed:
        print(f"summary_failed_status_gate: {overall_status}")
        sys.exit(3)
    if readiness_score_failed:
        print(f"summary_failed_readiness_score: {readiness_score}")
        sys.exit(4)
    if blockers_failed:
        print(f"summary_failed_blockers: {readiness_blocker_count}")
        sys.exit(5)


if __name__ == "__main__":
    main()
