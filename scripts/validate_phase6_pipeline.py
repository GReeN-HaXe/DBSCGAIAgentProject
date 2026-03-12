from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import (
    build_pipeline_history_row,
    build_timing_history_row,
    compute_trace_hash,
    evaluate_timing_regression,
    pipeline_history_row_to_dict,
    summarize_pipeline_history,
    summarize_stage_timings,
    summarize_timing_history,
    timing_history_row_to_dict,
)


def _run(cmd: list[str]) -> float:
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip())
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")
    return max(0.0, float(time.perf_counter() - t0))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 6 scripted play+replay validation pipeline.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase6_pipeline"), help="Output artifacts directory.")
    parser.add_argument("--history-csv", type=Path, default=None, help="Optional append-only Phase 6 pipeline history CSV.")
    parser.add_argument("--history-summary-json", type=Path, default=None, help="Optional output for history summary JSON.")
    parser.add_argument("--history-recent-window", type=int, default=20, help="History summary recent-window size.")
    parser.add_argument("--min-recent-pass-rate", type=float, default=0.90, help="Minimum recent pass-rate threshold.")
    parser.add_argument("--min-determinism-pass-rate", type=float, default=1.00, help="Minimum determinism pass-rate threshold.")
    parser.add_argument("--fail-on-history-status", choices=["warning", "critical"], default=None, help="Fail pipeline when history overall_status reaches threshold.")
    parser.add_argument("--timing-baseline-json", type=Path, default=None, help="Optional baseline stage-timing summary JSON.")
    parser.add_argument("--update-timing-baseline-json", type=Path, default=None, help="Optional path to overwrite/create timing baseline from current run.")
    parser.add_argument(
        "--max-total-seconds-regression-ratio",
        type=float,
        default=0.50,
        help="Maximum allowed total-seconds regression ratio over baseline (0.50 means +50%).",
    )
    parser.add_argument(
        "--fail-on-timing-regression",
        action="store_true",
        help="Fail pipeline when timing regression exceeds threshold and baseline is provided.",
    )
    parser.add_argument(
        "--max-recent-regression-rate",
        type=float,
        default=None,
        help="Optional threshold for timing_history_summary.regression_rate_recent (0.0-1.0).",
    )
    parser.add_argument(
        "--fail-on-timing-history",
        action="store_true",
        help="Fail pipeline when recent timing regression rate exceeds --max-recent-regression-rate.",
    )
    parser.add_argument("--human-player", type=int, choices=[1, 2], default=1, help="Human player id.")
    parser.add_argument("--ai-profile", type=str, default="balanced", help="AI profile.")
    parser.add_argument("--max-actions", type=int, default=None, help="Max actions for scripted play.")
    parser.add_argument("--seed", type=int, default=7, help="Seed used for shuffled runs.")
    parser.add_argument("--shuffle-decks", action="store_true", help="Enable shuffled decks for play run.")
    parser.add_argument(
        "--pipeline-profile",
        choices=["quick", "standard", "strict"],
        default="standard",
        help="Validation profile that sets defaults for max-actions and determinism checks.",
    )
    parser.add_argument(
        "--check-determinism",
        action="store_true",
        help="Run replay twice and assert identical trace hashes.",
    )
    args = parser.parse_args()

    profile_defaults = {
        "quick": {"max_actions": 10, "check_determinism": False},
        "standard": {"max_actions": 20, "check_determinism": True},
        "strict": {"max_actions": 40, "check_determinism": True},
    }
    defaults = profile_defaults[str(args.pipeline_profile)]
    if args.max_actions is None:
        args.max_actions = int(defaults["max_actions"])
    if not args.check_determinism and bool(defaults["check_determinism"]):
        args.check_determinism = True

    artifacts = args.artifacts_dir
    artifacts.mkdir(parents=True, exist_ok=True)
    actions_play = artifacts / "actions_play.txt"
    actions_replay = artifacts / "actions_replay.txt"
    actions_play.write_text("0\nq\n", encoding="utf-8")
    actions_replay.write_text("0\n", encoding="utf-8")

    trace_path = artifacts / "human_vs_ai_trace.json"
    state_path = artifacts / "human_vs_ai_state.json"
    summary_path = artifacts / "human_vs_ai_summary.json"
    result_path = artifacts / "human_vs_ai_result.json"
    replay_out = artifacts / "replay_result.json"
    replay_result = artifacts / "replay_expect_result.json"
    replay_out_2 = artifacts / "replay_result_2.json"
    replay_result_2 = artifacts / "replay_expect_result_2.json"
    report_md = artifacts / "phase6_report.md"
    manifest_json = artifacts / "phase6_pipeline_manifest.json"
    integrity_json = artifacts / "phase6_integrity_result.json"
    stage_timings_json = artifacts / "phase6_stage_timings.json"
    timing_regression_json = artifacts / "phase6_timing_regression.json"
    timing_history_csv = artifacts / "phase6_timing_history.csv"
    timing_history_summary_json = artifacts / "phase6_timing_history_summary.json"
    history_csv = args.history_csv or (artifacts / "phase6_pipeline_history.csv")
    history_summary_json = args.history_summary_json or (artifacts / "phase6_pipeline_history_summary.json")
    play_ok = False
    replay_ok = False
    h1 = ""
    h2: str | None = None
    stage_timings: list[dict[str, object]] = []

    def _write_manifest(*, status: str, failure_reason: str = "") -> None:
        manifest = {
            "status": str(status),
            "failure_reason": str(failure_reason),
            "pipeline_profile": str(args.pipeline_profile),
            "play_ok": bool(play_ok),
            "replay_ok": bool(replay_ok),
            "determinism_checked": bool(args.check_determinism),
            "trace_hash_1": h1,
            "trace_hash_2": h2,
            "history_recent_window": int(args.history_recent_window),
            "min_recent_pass_rate": float(args.min_recent_pass_rate),
            "min_determinism_pass_rate": float(args.min_determinism_pass_rate),
            "max_recent_regression_rate": args.max_recent_regression_rate,
            "artifacts": {
                "trace": str(trace_path),
                "state": str(state_path),
                "summary": str(summary_path),
                "play_result": str(result_path),
                "replay_result": str(replay_out),
                "replay_expect_result": str(replay_result),
                "report_md": str(report_md),
                "integrity_result": str(integrity_json),
                "history_csv": str(history_csv),
                "history_summary_json": str(history_summary_json),
                "stage_timings_json": str(stage_timings_json),
                "timing_regression_json": str(timing_regression_json),
                "timing_history_csv": str(timing_history_csv),
                "timing_history_summary_json": str(timing_history_summary_json),
            },
        }
        manifest_json.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"wrote: {manifest_json}")

    def _run_or_fail(stage_name: str, cmd: list[str]) -> None:
        try:
            elapsed = _run(cmd)
            stage_timings.append({"name": str(stage_name), "duration_seconds": float(elapsed)})
        except Exception as exc:
            _write_manifest(status="fail", failure_reason=str(exc))
            raise

    play_cmd = [
        sys.executable,
        "scripts/play_vs_ai.py",
        "--human-player",
        str(args.human_player),
        "--ai-profile",
        str(args.ai_profile),
        "--max-actions",
        str(max(1, int(args.max_actions or 20))),
        "--scripted-actions-file",
        str(actions_play),
        "--trace-output",
        str(trace_path),
        "--save-state-output",
        str(state_path),
        "--summary-output",
        str(summary_path),
        "--result-output",
        str(result_path),
        "--ci-mode",
        "--expect-completed",
        "false",
        "--seed",
        str(args.seed),
    ]
    if args.shuffle_decks:
        play_cmd.append("--shuffle-decks")
    _run_or_fail("play_vs_ai", play_cmd)

    replay_cmd = [
        sys.executable,
        "scripts/replay_human_vs_ai.py",
        "--state-input",
        str(state_path),
        "--actions-file",
        str(actions_replay),
        "--human-player",
        str(args.human_player),
        "--ai-profile",
        str(args.ai_profile),
        "--output",
        str(replay_out),
        "--result-output",
        str(replay_result),
        "--ci-mode",
        "--expect-completed",
        "false",
    ]
    _run_or_fail("replay_human_vs_ai", replay_cmd)

    if args.check_determinism:
        replay_cmd_2 = [
            sys.executable,
            "scripts/replay_human_vs_ai.py",
            "--state-input",
            str(state_path),
            "--actions-file",
            str(actions_replay),
            "--human-player",
            str(args.human_player),
            "--ai-profile",
            str(args.ai_profile),
            "--output",
            str(replay_out_2),
            "--result-output",
            str(replay_result_2),
            "--ci-mode",
            "--expect-completed",
            "false",
        ]
        _run_or_fail("replay_human_vs_ai_second", replay_cmd_2)

    play_ok = json.loads(result_path.read_text(encoding="utf-8")).get("ok", False)
    replay_ok = json.loads(replay_result.read_text(encoding="utf-8")).get("ok", False)
    if not play_ok or not replay_ok:
        reason = f"pipeline expectations failed: play_ok={play_ok} replay_ok={replay_ok}"
        _write_manifest(status="fail", failure_reason=reason)
        raise RuntimeError(reason)

    replay_1 = json.loads(replay_out.read_text(encoding="utf-8"))
    h1 = compute_trace_hash(replay_1.get("trace", {}))
    h2 = None
    if args.check_determinism:
        replay_2 = json.loads(replay_out_2.read_text(encoding="utf-8"))
        h2 = compute_trace_hash(replay_2.get("trace", {}))
        if h1 != h2:
            reason = f"determinism_check_failed: trace_hash_1={h1} trace_hash_2={h2}"
            _write_manifest(status="fail", failure_reason=reason)
            raise RuntimeError(reason)

    _run_or_fail(
        "check_phase6_artifacts",
        [
            sys.executable,
            "scripts/check_phase6_artifacts.py",
            "--trace",
            str(trace_path),
            "--summary",
            str(summary_path),
            "--play-result",
            str(result_path),
            "--replay",
            str(replay_out),
            "--replay-result",
            str(replay_result),
            "--manifest-status",
            "pass",
            "--strict-summary-trace-hash",
            "--output",
            str(integrity_json),
        ]
    )
    row = build_pipeline_history_row(
        pipeline_profile=str(args.pipeline_profile),
        play_ok=bool(play_ok),
        replay_ok=bool(replay_ok),
        determinism_checked=bool(args.check_determinism),
        determinism_ok=(True if not args.check_determinism else bool(h1 == h2)),
        trace_hash_1=str(h1),
        trace_hash_2=h2,
        status="pass",
    )
    history_csv.parent.mkdir(parents=True, exist_ok=True)
    existing_rows: list[dict[str, str]] = []
    if history_csv.exists():
        with history_csv.open("r", encoding="utf-8", newline="") as fh:
            for item in csv.DictReader(fh):
                existing_rows.append(dict(item))
    row_out = pipeline_history_row_to_dict(row)
    with history_csv.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row_out.keys()))
        if not existing_rows:
            writer.writeheader()
        writer.writerow(row_out)
    print(f"appended: {history_csv}")
    merged = [*existing_rows, row_out]
    history_summary = summarize_pipeline_history(
        merged,
        recent_window=max(1, int(args.history_recent_window)),
        min_recent_pass_rate=float(args.min_recent_pass_rate),
        min_determinism_pass_rate=float(args.min_determinism_pass_rate),
    )
    history_summary_json.parent.mkdir(parents=True, exist_ok=True)
    history_summary_json.write_text(json.dumps(history_summary, indent=2), encoding="utf-8")
    print(f"wrote: {history_summary_json}")
    timing_summary = summarize_stage_timings(stage_timings)
    stage_timings_json.write_text(
        json.dumps({"stages": stage_timings, "summary": timing_summary}, indent=2),
        encoding="utf-8",
    )
    print(f"wrote: {stage_timings_json}")
    timing_regression_payload: dict[str, object] = {
        "has_baseline": False,
        "regressed": False,
        "reason": "",
    }
    if args.timing_baseline_json is not None and args.timing_baseline_json.exists():
        baseline_obj = json.loads(args.timing_baseline_json.read_text(encoding="utf-8"))
        baseline_summary = (
            baseline_obj.get("summary", {})
            if isinstance(baseline_obj, dict)
            else {}
        )
        if not isinstance(baseline_summary, dict):
            baseline_summary = {}
        timing_regression_payload = evaluate_timing_regression(
            current_timing_summary=timing_summary,
            baseline_timing_summary=baseline_summary,
            max_total_seconds_regression_ratio=float(args.max_total_seconds_regression_ratio),
        )
    timing_regression_json.write_text(json.dumps(timing_regression_payload, indent=2), encoding="utf-8")
    print(f"wrote: {timing_regression_json}")
    timing_row = build_timing_history_row(
        pipeline_profile=str(args.pipeline_profile),
        timing_summary=timing_summary,
        regressed=bool(timing_regression_payload.get("regressed", False)),
    )
    timing_history_csv.parent.mkdir(parents=True, exist_ok=True)
    timing_existing: list[dict[str, str]] = []
    if timing_history_csv.exists():
        with timing_history_csv.open("r", encoding="utf-8", newline="") as fh:
            for item in csv.DictReader(fh):
                timing_existing.append(dict(item))
    timing_row_out = timing_history_row_to_dict(timing_row)
    with timing_history_csv.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(timing_row_out.keys()))
        if not timing_existing:
            writer.writeheader()
        writer.writerow(timing_row_out)
    print(f"appended: {timing_history_csv}")
    timing_merged = [*timing_existing, timing_row_out]
    timing_history_summary = summarize_timing_history(timing_merged, recent_window=20)
    if args.max_recent_regression_rate is not None:
        threshold = max(0.0, min(1.0, float(args.max_recent_regression_rate)))
        rate = float(timing_history_summary.get("regression_rate_recent", 0.0) or 0.0)
        timing_history_summary["max_recent_regression_rate"] = threshold
        timing_history_summary["regression_rate_failed"] = rate > threshold
    timing_history_summary_json.write_text(json.dumps(timing_history_summary, indent=2), encoding="utf-8")
    print(f"wrote: {timing_history_summary_json}")
    if args.update_timing_baseline_json is not None:
        args.update_timing_baseline_json.parent.mkdir(parents=True, exist_ok=True)
        args.update_timing_baseline_json.write_text(
            json.dumps({"summary": timing_summary, "stages": stage_timings}, indent=2),
            encoding="utf-8",
        )
        print(f"wrote: {args.update_timing_baseline_json}")
    _run_or_fail(
        "render_phase6_report",
        [
            sys.executable,
            "scripts/render_phase6_report.py",
            "--summary",
            str(summary_path),
            "--play-result",
            str(result_path),
            "--replay",
            str(replay_out),
            "--replay-result",
            str(replay_result),
            "--history-summary",
            str(history_summary_json),
            "--stage-timings",
            str(stage_timings_json),
            "--timing-regression",
            str(timing_regression_json),
            "--timing-history-summary",
            str(timing_history_summary_json),
            "--output",
            str(report_md),
        ]
    )
    if bool(args.fail_on_timing_regression) and bool(timing_regression_payload.get("regressed", False)):
        reason = str(timing_regression_payload.get("reason", "timing regression detected"))
        print(f"timing_regression_failed: {reason}")
        _write_manifest(status="fail", failure_reason=reason)
        raise SystemExit(10)
    if bool(args.fail_on_timing_history) and args.max_recent_regression_rate is not None:
        rate = float(timing_history_summary.get("regression_rate_recent", 0.0) or 0.0)
        threshold = max(0.0, min(1.0, float(args.max_recent_regression_rate)))
        if rate > threshold:
            reason = f"timing_history_failed: regression_rate_recent={rate:.6f} threshold={threshold:.6f}"
            print(reason)
            _write_manifest(status="fail", failure_reason=reason)
            raise SystemExit(11)
    if args.fail_on_history_status is not None:
        order = {"healthy": 0, "warning": 1, "critical": 2, "unknown": 3}
        got = str(history_summary.get("overall_status", "unknown")).strip().lower()
        threshold = str(args.fail_on_history_status).strip().lower()
        if order.get(got, 3) >= order.get(threshold, 2):
            print(f"history_status_failed: expected_below={threshold} actual={got}")
            _write_manifest(status="fail", failure_reason=f"history_status_failed: expected_below={threshold} actual={got}")
            raise SystemExit(9)
    _write_manifest(status="pass")
    print("phase6_pipeline_validation: PASS")


if __name__ == "__main__":
    main()
