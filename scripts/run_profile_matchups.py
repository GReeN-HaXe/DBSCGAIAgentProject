from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import (
    build_head_to_head_matrix,
    build_history_csv_row,
    build_overview_csv_row,
    command_hints_from_summary,
    command_hints_to_csv_row,
    command_hints_to_json_payload,
    compute_match_quality,
    compute_seat_bias,
    head_to_head_to_csv_rows,
    history_recent_runs_to_csv_rows,
    history_summary_to_csv_row,
    merge_matchup_rows,
    matchup_rows_to_dict,
    profile_summary_to_csv_rows,
    seat_bias_to_csv_rows,
    recommend_profile,
    run_profile_matchup_matrix,
    summarize_history_rows,
    summarize_profile_strength,
)
from src.db import SQLiteCardRepository
from src.game import RulesEngine

HISTORY_PROFILE_PRESETS: dict[str, dict[str, float | int]] = {
    "quick": {
        "recent_window": 5,
        "recent_runs_window": 5,
        "seat_bias_alert_threshold": 0.20,
        "decisive_rate_alert_threshold": 0.25,
        "min_runs_for_ready": 3,
    },
    "standard": {
        "recent_window": 10,
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

PIPELINE_PROFILE_PRESETS: dict[str, dict[str, float | int]] = {
    "quick": {
        "games_per_matchup": 1,
        "max_actions": 80,
        "min_games_for_recommendation": 3,
        "decisive_rate_alert_threshold": 0.25,
        "seat_bias_alert_threshold": 0.20,
    },
    "standard": {
        "games_per_matchup": 2,
        "max_actions": 120,
        "min_games_for_recommendation": 6,
        "decisive_rate_alert_threshold": 0.30,
        "seat_bias_alert_threshold": 0.15,
    },
    "strict": {
        "games_per_matchup": 4,
        "max_actions": 160,
        "min_games_for_recommendation": 12,
        "decisive_rate_alert_threshold": 0.35,
        "seat_bias_alert_threshold": 0.10,
    },
}

TIMESTAMPED_PROFILE_ARTIFACT_RE = re.compile(r".*profile_matchups_.*_\d{8}T\d{6}Z\.[^.]+$")


def _build_deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _make_state_factory(*, shuffle_decks: bool, seed: int | None, first_player: int):
    game_index = 0

    def _state_factory(engine: RulesEngine):
        nonlocal game_index
        game_seed = None if seed is None else (seed + game_index)
        game_index += 1
        return engine.initialize_game(
            p1_leader_card_id=1,
            p1_deck_card_ids=_build_deck(1000),
            p2_leader_card_id=2,
            p2_deck_card_ids=_build_deck(2000),
            first_player=first_player,
            shuffle_decks=shuffle_decks,
            random_seed=game_seed,
        )

    return _state_factory


def _default_csv_path(output_json: Path, suffix: str) -> Path:
    return output_json.with_name(f"{output_json.stem}_{suffix}.csv")


def _default_json_path(output_json: Path, suffix: str) -> Path:
    return output_json.with_name(f"{output_json.stem}_{suffix}.json")


def _with_output_prefix(path: Path, output_prefix: str) -> Path:
    prefix = str(output_prefix or "").strip()
    if not prefix:
        return path
    return path.with_name(f"{prefix}{path.name}")


def _with_timestamp_suffix(path: Path, timestamp_tag: str) -> Path:
    tag = str(timestamp_tag or "").strip()
    if not tag:
        return path
    return path.with_name(f"{path.stem}_{tag}{path.suffix}")


def _decorate_generated_path(path: Path, *, output_prefix: str, timestamp_tag: str) -> Path:
    return _with_timestamp_suffix(_with_output_prefix(path, output_prefix), timestamp_tag)


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


def _default_history_artifact_path(history_csv: Path, suffix: str, extension: str) -> Path:
    stem = history_csv.stem
    if stem.endswith("_history"):
        base = stem
    else:
        base = f"{stem}_history"
    return history_csv.with_name(f"{base}_{suffix}.{extension}")


def _compute_history_ci_out(
    *,
    history_summary_payload: dict[str, object] | None,
    history_ci_status_threshold: str,
    history_ci_readiness_mode: str,
    history_ci_blockers_mode: str,
    history_ci_unknown_mode: str,
    history_ci_readiness_score_threshold: float | None,
) -> dict[str, object]:
    unknown_mode = str(history_ci_unknown_mode).strip().lower()
    status_threshold = str(history_ci_status_threshold).strip().lower()
    readiness_mode = str(history_ci_readiness_mode).strip().lower()
    blockers_mode = str(history_ci_blockers_mode).strip().lower()
    score_threshold = (
        None
        if history_ci_readiness_score_threshold is None
        else max(0.0, min(1.0, float(history_ci_readiness_score_threshold)))
    )
    if isinstance(history_summary_payload, dict):
        overall_status = str(history_summary_payload.get("overall_status", "healthy")).strip().lower()
        is_ready = bool(history_summary_payload.get("is_ready_for_next_phase", False))
        readiness_score = float(history_summary_payload.get("readiness_score", 0.0))
        blocker_count = int(history_summary_payload.get("readiness_blocker_count", 0))
        status_order = {"healthy": 0, "warning": 1, "critical": 2}
        status_failed = status_order.get(overall_status, 0) >= status_order.get(status_threshold, 1)
        blockers_failed = (blockers_mode == "required") and (blocker_count > 0)
        not_ready_failed = (readiness_mode == "required") and (not is_ready)
        readiness_score_failed = bool(score_threshold is not None and readiness_score < float(score_threshold))
        ci_failed = bool(status_failed or blockers_failed or not_ready_failed or readiness_score_failed)
        reasons: list[str] = []
        if status_failed:
            reasons.append("status_threshold_failed")
        if not_ready_failed:
            reasons.append("not_ready_failed")
        if blockers_failed:
            reasons.append("blockers_failed")
        if readiness_score_failed:
            reasons.append("readiness_score_failed")
        return {
            "status": "fail" if ci_failed else "pass",
            "overall_status": overall_status,
            "is_ready_for_next_phase": is_ready,
            "readiness_score": readiness_score,
            "readiness_blocker_count": blocker_count,
            "status_threshold": status_threshold,
            "readiness_mode": readiness_mode,
            "blockers_mode": blockers_mode,
            "readiness_score_threshold": score_threshold,
            "status_failed": status_failed,
            "not_ready_failed": not_ready_failed,
            "blockers_failed": blockers_failed,
            "readiness_score_failed": readiness_score_failed,
            "policy": {
                "status_threshold": status_threshold,
                "readiness_mode": readiness_mode,
                "blockers_mode": blockers_mode,
                "unknown_mode": unknown_mode,
                "readiness_score_threshold": score_threshold,
            },
            "reasons": reasons,
            "source": "history_summary",
        }
    return {
        "status": "pass" if unknown_mode == "pass" else "unknown",
        "unknown_mode": unknown_mode,
        "policy": {
            "status_threshold": status_threshold,
            "readiness_mode": readiness_mode,
            "blockers_mode": blockers_mode,
            "unknown_mode": unknown_mode,
            "readiness_score_threshold": score_threshold,
        },
        "reasons": [] if unknown_mode == "pass" else ["history_summary_unavailable"],
        "source": "unavailable",
    }


def _compute_pipeline_ci_failed(*, core_ci_failed: bool, include_history_ci: bool, history_ci_status: str) -> bool:
    history_failed = str(history_ci_status).strip().lower() != "pass"
    return bool(core_ci_failed or (bool(include_history_ci) and history_failed))


def _resolve_failure_exit_code(
    *,
    fail_on_ci_status_only: bool,
    fail_on_ci_status: bool,
    ci_status: str,
    fail_on_alerts: bool,
    low_decisive_rate_alert: bool,
    seat_bias_alert: bool,
    fail_on_unreliable_recommendation: bool,
    recommendation_reliable: bool,
    fail_on_history_ci: bool,
    history_ci_status: str,
) -> tuple[int | None, str | None]:
    ci_status_norm = str(ci_status).strip().lower()
    history_status_norm = str(history_ci_status).strip().lower()
    alerts_triggered = bool(low_decisive_rate_alert or seat_bias_alert)

    if fail_on_ci_status_only:
        if ci_status_norm != "pass":
            return 5, f"run_failed_on_ci_status: {ci_status_norm or 'fail'}"
        return None, None

    if fail_on_ci_status and ci_status_norm != "pass":
        return 5, f"run_failed_on_ci_status: {ci_status_norm or 'fail'}"
    if fail_on_alerts and alerts_triggered:
        return 2, "run_failed_on_alerts: True"
    if fail_on_unreliable_recommendation and not recommendation_reliable:
        return 3, "run_failed_on_unreliable_recommendation: True"
    if fail_on_history_ci and history_status_norm != "pass":
        return 4, f"run_failed_on_history_ci: {history_status_norm or 'unknown'}"
    return None, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run profile-vs-profile AI matchup matrix.")
    parser.add_argument(
        "--ci-mode",
        action="store_true",
        help="Apply CI defaults: strict profiles, fail-on-alerts, manifests, and history auto-refresh.",
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="",
        help="Prefix added to default-generated artifact filenames.",
    )
    parser.add_argument(
        "--timestamped-artifacts",
        action="store_true",
        help="Append a single UTC timestamp suffix to default-generated artifact filenames.",
    )
    parser.add_argument(
        "--ci-artifacts-dir",
        type=Path,
        default=None,
        help="Directory used for default CI artifacts (run manifest, recommendation, history and history exports).",
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
        help="Print one-line JSON CI summary at end of run.",
    )
    parser.add_argument(
        "--summary-format",
        choices=["text", "json", "both", "none"],
        default="text",
        help="Primary stdout summary format. Use print-* flags for additional machine outputs.",
    )
    parser.add_argument(
        "--print-metrics-json",
        action="store_true",
        help="Print one-line JSON with compact matchup metrics.",
    )
    parser.add_argument(
        "--print-commands-json",
        action="store_true",
        help="Print one-line JSON command hints (from history summary when available).",
    )
    parser.add_argument(
        "--pipeline-profile",
        choices=["quick", "standard", "strict"],
        default=None,
        help="Preset for simulation intensity; explicit flags override preset values.",
    )
    parser.add_argument("--profiles", type=str, default="balanced,aggressive,control", help="Comma-separated profile names.")
    parser.add_argument("--games-per-matchup", type=int, default=None, help="Number of games for each ordered profile pair.")
    parser.add_argument("--max-actions", type=int, default=None, help="Maximum actions before ending a game.")
    parser.add_argument("--effect-catalog", type=Path, default=Path("dbdatabase/effect_catalog.json"), help="Path to effect catalog JSON.")
    parser.add_argument("--skill-cost-catalog", type=Path, default=Path("dbdatabase/skill_cost_catalog.json"), help="Path to skill cost catalog JSON.")
    parser.add_argument("--db-path", type=Path, default=Path("dbdatabase/dbs_masters.db"), help="Path to SQLite card database.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/profile_matchups.json"), help="Output JSON path.")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress routine progress logs (keeps explicit print-* outputs and failure signals).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved execution plan and exit without running simulations or writing artifacts.",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=None,
        help="Optional path to write run metadata manifest JSON.",
    )
    parser.add_argument(
        "--recommendation-output",
        type=Path,
        default=None,
        help="Optional path to write recommendation snapshot JSON.",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=None,
        help="Optional path to write compact matchup metrics JSON.",
    )
    parser.add_argument(
        "--commands-output-json",
        type=Path,
        default=None,
        help="Optional path to write command hints JSON (history-derived when available).",
    )
    parser.add_argument(
        "--bundle-output",
        type=Path,
        default=None,
        help="Optional path to write combined run/recommendation/metrics/commands JSON bundle.",
    )
    parser.add_argument(
        "--bundle-output-compact",
        action="store_true",
        help="Write --bundle-output as compact single-line JSON instead of pretty JSON.",
    )
    parser.add_argument(
        "--bundle-include-history-summary",
        action="store_true",
        help="Include full history_summary in bundle payload when available.",
    )
    parser.add_argument(
        "--print-bundle-json",
        action="store_true",
        help="Print one-line JSON bundle payload to stdout.",
    )
    parser.add_argument(
        "--print-recommendation-only",
        action="store_true",
        help="Print only the recommended profile value as the final line.",
    )
    parser.add_argument(
        "--print-run-manifest",
        action="store_true",
        help="Print run metadata manifest JSON to stdout at the end of execution.",
    )
    parser.add_argument("--shuffle-decks", action="store_true", help="Shuffle decks at game start.")
    parser.add_argument("--seat-balanced", action="store_true", help="Run each matchup with first_player=1 and first_player=2, then merge.")
    parser.add_argument("--seed", type=int, default=None, help="Optional base RNG seed; if set, each game uses seed+game_index.")
    parser.add_argument(
        "--min-games-for-recommendation",
        type=int,
        default=None,
        help="Minimum games each profile must have before recommendation is considered reliable.",
    )
    parser.add_argument(
        "--decisive-rate-alert-threshold",
        type=float,
        default=None,
        help="Alert threshold for decisive-rate quality (below this means draw-heavy/inconclusive simulations).",
    )
    parser.add_argument(
        "--seat-bias-alert-threshold",
        type=float,
        default=None,
        help="Alert threshold for absolute seat-bias delta (|p1_minus_p2|).",
    )
    parser.add_argument(
        "--fail-on-alerts",
        action="store_true",
        help="Exit with code 2 if decisive-rate or seat-bias alerts are triggered.",
    )
    parser.add_argument(
        "--fail-on-unreliable-recommendation",
        action="store_true",
        help="Exit with code 3 if recommendation is not reliable.",
    )
    parser.add_argument(
        "--ci-status-include-history-ci",
        action="store_true",
        help="When set, ci_summary.status and run_manifest ci.status also fail if history CI is not pass.",
    )
    parser.add_argument(
        "--fail-on-ci-status",
        action="store_true",
        help="Exit with code 5 when final ci_summary.status is fail.",
    )
    parser.add_argument(
        "--fail-on-ci-status-only",
        action="store_true",
        help="Use only unified ci_summary.status gate (exit 5) and ignore legacy fail gates for this run.",
    )
    parser.add_argument("--rows-csv", type=Path, default=None, help="Optional rows CSV path. Defaults next to --output.")
    parser.add_argument("--summary-csv", type=Path, default=None, help="Optional profile summary CSV path. Defaults next to --output.")
    parser.add_argument("--h2h-csv", type=Path, default=None, help="Optional head-to-head CSV path. Defaults next to --output.")
    parser.add_argument("--seat-bias-csv", type=Path, default=None, help="Optional seat-bias by-matchup CSV path. Defaults next to --output.")
    parser.add_argument("--overview-csv", type=Path, default=None, help="Optional one-row overview CSV path. Defaults next to --output.")
    parser.add_argument("--history-csv", type=Path, default=None, help="Optional append-only history CSV path.")
    parser.add_argument(
        "--auto-refresh-history-artifacts",
        action="store_true",
        help="When set with --history-csv, writes default history summary/recent/commands artifacts automatically.",
    )
    parser.add_argument("--history-summary-json", type=Path, default=None, help="Optional path to write history summary JSON.")
    parser.add_argument("--history-summary-csv", type=Path, default=None, help="Optional path to write one-row history summary CSV.")
    parser.add_argument("--history-recent-runs-csv", type=Path, default=None, help="Optional path to write recent history runs CSV.")
    parser.add_argument("--history-commands-output", type=Path, default=None, help="Optional path to write history command hints text.")
    parser.add_argument("--history-commands-csv", type=Path, default=None, help="Optional path to write history command hints CSV.")
    parser.add_argument("--history-commands-json", type=Path, default=None, help="Optional path to write history command hints JSON.")
    parser.add_argument(
        "--history-metrics-output",
        type=Path,
        default=None,
        help="Optional path to write compact history metrics JSON.",
    )
    parser.add_argument(
        "--history-bundle-output",
        type=Path,
        default=None,
        help="Optional path to write combined history summary/commands/metrics JSON bundle.",
    )
    parser.add_argument(
        "--history-bundle-output-compact",
        action="store_true",
        help="Write --history-bundle-output as compact single-line JSON instead of pretty JSON.",
    )
    parser.add_argument(
        "--history-ci-output-json",
        type=Path,
        default=None,
        help="Optional path to write history CI summary JSON.",
    )
    parser.add_argument(
        "--print-history-ci-output-path",
        action="store_true",
        help="Print resolved history CI output path (if configured).",
    )
    parser.add_argument(
        "--history-ci-output-compact",
        action="store_true",
        help="Write --history-ci-output-json as compact single-line JSON instead of pretty JSON.",
    )
    parser.add_argument(
        "--history-artifact-manifest",
        type=Path,
        default=None,
        help="Optional path to write JSON manifest for generated history artifacts.",
    )
    parser.add_argument(
        "--history-profile",
        choices=["quick", "standard", "strict"],
        default=None,
        help="Preset for history windows/thresholds; explicit flags override preset values.",
    )
    parser.add_argument(
        "--print-history-next-commands",
        action="store_true",
        help="Print prioritized next-step command hints from the current history summary.",
    )
    parser.add_argument(
        "--print-history-summary-json",
        action="store_true",
        help="Print one-line JSON history summary when available.",
    )
    parser.add_argument(
        "--print-history-metrics-json",
        action="store_true",
        help="Print one-line JSON history metrics when history summary is available.",
    )
    parser.add_argument(
        "--print-history-ci-summary",
        action="store_true",
        help="Print one-line JSON CI-style history status summary when history summary is available.",
    )
    parser.add_argument(
        "--print-history-ci-policy-json",
        action="store_true",
        help="Print one-line JSON history CI policy configuration.",
    )
    parser.add_argument(
        "--print-history-bundle-json",
        action="store_true",
        help="Print one-line JSON history bundle (summary+commands+metrics) when available.",
    )
    parser.add_argument(
        "--fail-on-history-ci",
        action="store_true",
        help="Exit with code 4 when computed history CI status is fail or unknown.",
    )
    parser.add_argument(
        "--history-ci-status-threshold",
        choices=["warning", "critical"],
        default="warning",
        help="History CI status gate threshold used for pass/fail derivation.",
    )
    parser.add_argument(
        "--history-ci-readiness-mode",
        choices=["required", "ignore"],
        default="required",
        help="History CI readiness rule: require ready-for-next-phase or ignore readiness.",
    )
    parser.add_argument(
        "--history-ci-blockers-mode",
        choices=["required", "ignore"],
        default="required",
        help="History CI blocker rule: fail on readiness blockers or ignore blocker count.",
    )
    parser.add_argument(
        "--history-ci-unknown-mode",
        choices=["fail", "pass"],
        default="fail",
        help="History CI fallback when history summary is unavailable.",
    )
    parser.add_argument(
        "--history-ci-readiness-score-threshold",
        type=float,
        default=None,
        help="Optional history CI readiness_score floor (0.0-1.0); below threshold fails history CI.",
    )
    parser.add_argument(
        "--history-recent-window",
        type=int,
        default=None,
        help="Recent-window size used for history summary trends.",
    )
    parser.add_argument(
        "--history-recent-runs-window",
        type=int,
        default=None,
        help="Recent-window size for recent-runs CSV export.",
    )
    parser.add_argument(
        "--history-seat-bias-alert-threshold",
        type=float,
        default=None,
        help="Seat-bias alert threshold used by history summary.",
    )
    parser.add_argument(
        "--history-decisive-rate-alert-threshold",
        type=float,
        default=None,
        help="Decisive-rate alert threshold used by history summary.",
    )
    parser.add_argument(
        "--history-min-runs-for-ready",
        type=int,
        default=None,
        help="Minimum runs required for history readiness check.",
    )
    args = parser.parse_args()
    if args.fail_on_ci_status_only:
        args.fail_on_ci_status = True

    def log(message: str) -> None:
        if not args.quiet:
            print(message)

    timestamp_tag = ""
    if args.timestamped_artifacts:
        timestamp_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    ci_artifacts_dir = args.ci_artifacts_dir

    if args.ci_mode:
        if args.pipeline_profile is None:
            args.pipeline_profile = "strict"
        if args.history_profile is None:
            args.history_profile = "strict"
        args.fail_on_alerts = True
        args.fail_on_unreliable_recommendation = True
        args.fail_on_history_ci = True
        args.ci_status_include_history_ci = True
        args.auto_refresh_history_artifacts = True
        if ci_artifacts_dir is not None and args.ci_retain_latest is None:
            args.ci_retain_latest = 20

    if ci_artifacts_dir is not None:
        if args.run_manifest is None:
            args.run_manifest = _decorate_generated_path(
                ci_artifacts_dir / "profile_matchups_run_manifest.json",
                output_prefix=args.output_prefix,
                timestamp_tag=timestamp_tag,
            )
        if args.recommendation_output is None:
            args.recommendation_output = _decorate_generated_path(
                ci_artifacts_dir / "profile_matchups_recommendation.json",
                output_prefix=args.output_prefix,
                timestamp_tag=timestamp_tag,
            )
        if args.metrics_output is None:
            args.metrics_output = _decorate_generated_path(
                ci_artifacts_dir / "profile_matchups_metrics.json",
                output_prefix=args.output_prefix,
                timestamp_tag=timestamp_tag,
            )
        if args.commands_output_json is None:
            args.commands_output_json = _decorate_generated_path(
                ci_artifacts_dir / "profile_matchups_commands.json",
                output_prefix=args.output_prefix,
                timestamp_tag=timestamp_tag,
            )
        if args.bundle_output is None:
            args.bundle_output = _decorate_generated_path(
                ci_artifacts_dir / "profile_matchups_bundle.json",
                output_prefix=args.output_prefix,
                timestamp_tag=timestamp_tag,
            )
        if args.history_csv is None:
            args.history_csv = _decorate_generated_path(
                ci_artifacts_dir / "profile_matchups_history.csv",
                output_prefix=args.output_prefix,
                timestamp_tag=timestamp_tag,
            )

    if args.ci_mode:
        if args.history_csv is None:
            args.history_csv = _decorate_generated_path(
                Path("artifacts/profile_matchups_history.csv"),
                output_prefix=args.output_prefix,
                timestamp_tag=timestamp_tag,
            )
        if args.run_manifest is None:
            args.run_manifest = _decorate_generated_path(
                _default_json_path(args.output, "run_manifest"),
                output_prefix=args.output_prefix,
                timestamp_tag=timestamp_tag,
            )
        if args.recommendation_output is None:
            args.recommendation_output = _decorate_generated_path(
                _default_json_path(args.output, "recommendation"),
                output_prefix=args.output_prefix,
                timestamp_tag=timestamp_tag,
            )
        if args.metrics_output is None:
            args.metrics_output = _decorate_generated_path(
                _default_json_path(args.output, "metrics"),
                output_prefix=args.output_prefix,
                timestamp_tag=timestamp_tag,
            )
        if args.commands_output_json is None:
            args.commands_output_json = _decorate_generated_path(
                _default_json_path(args.output, "commands"),
                output_prefix=args.output_prefix,
                timestamp_tag=timestamp_tag,
            )
        if args.bundle_output is None:
            args.bundle_output = _decorate_generated_path(
                _default_json_path(args.output, "bundle"),
                output_prefix=args.output_prefix,
                timestamp_tag=timestamp_tag,
            )

    if args.pipeline_profile is None:
        args.pipeline_profile = "standard"
    if args.history_profile is None:
        args.history_profile = "standard"

    pipeline_profile = PIPELINE_PROFILE_PRESETS[args.pipeline_profile]
    games_per_matchup = max(
        1,
        int(args.games_per_matchup if args.games_per_matchup is not None else pipeline_profile["games_per_matchup"]),
    )
    max_actions = max(
        1,
        int(args.max_actions if args.max_actions is not None else pipeline_profile["max_actions"]),
    )
    min_games_for_recommendation = max(
        0,
        int(
            args.min_games_for_recommendation
            if args.min_games_for_recommendation is not None
            else pipeline_profile["min_games_for_recommendation"]
        ),
    )
    decisive_rate_alert_threshold = float(
        args.decisive_rate_alert_threshold
        if args.decisive_rate_alert_threshold is not None
        else pipeline_profile["decisive_rate_alert_threshold"]
    )
    seat_bias_alert_threshold = float(
        args.seat_bias_alert_threshold
        if args.seat_bias_alert_threshold is not None
        else pipeline_profile["seat_bias_alert_threshold"]
    )

    history_profile = HISTORY_PROFILE_PRESETS[args.history_profile]
    history_recent_window = max(
        1,
        int(args.history_recent_window if args.history_recent_window is not None else history_profile["recent_window"]),
    )
    history_recent_runs_window = max(
        1,
        int(
            args.history_recent_runs_window
            if args.history_recent_runs_window is not None
            else history_profile["recent_runs_window"]
        ),
    )
    history_seat_bias_alert_threshold = float(
        args.history_seat_bias_alert_threshold
        if args.history_seat_bias_alert_threshold is not None
        else history_profile["seat_bias_alert_threshold"]
    )
    history_decisive_rate_alert_threshold = float(
        args.history_decisive_rate_alert_threshold
        if args.history_decisive_rate_alert_threshold is not None
        else history_profile["decisive_rate_alert_threshold"]
    )
    history_min_runs_for_ready = max(
        1,
        int(
            args.history_min_runs_for_ready
            if args.history_min_runs_for_ready is not None
            else history_profile["min_runs_for_ready"]
        ),
    )

    if args.auto_refresh_history_artifacts and args.history_csv is None:
        parser.error("--history-csv is required when using --auto-refresh-history-artifacts.")

    if args.auto_refresh_history_artifacts and args.history_csv is not None:
        if args.history_summary_json is None:
            if ci_artifacts_dir is not None:
                args.history_summary_json = _decorate_generated_path(
                    ci_artifacts_dir / "profile_matchups_history_summary.json",
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
            else:
                args.history_summary_json = _decorate_generated_path(
                    _default_history_artifact_path(args.history_csv, "summary", "json"),
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
        if args.history_summary_csv is None:
            if ci_artifacts_dir is not None:
                args.history_summary_csv = _decorate_generated_path(
                    ci_artifacts_dir / "profile_matchups_history_summary.csv",
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
            else:
                args.history_summary_csv = _decorate_generated_path(
                    _default_history_artifact_path(args.history_csv, "summary", "csv"),
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
        if args.history_recent_runs_csv is None:
            if ci_artifacts_dir is not None:
                args.history_recent_runs_csv = _decorate_generated_path(
                    ci_artifacts_dir / "profile_matchups_history_recent.csv",
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
            else:
                args.history_recent_runs_csv = _decorate_generated_path(
                    _default_history_artifact_path(args.history_csv, "recent", "csv"),
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
        if args.history_commands_output is None:
            if ci_artifacts_dir is not None:
                args.history_commands_output = _decorate_generated_path(
                    ci_artifacts_dir / "profile_matchups_next_commands.txt",
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
            else:
                args.history_commands_output = _decorate_generated_path(
                    _default_history_artifact_path(args.history_csv, "next_commands", "txt"),
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
        if args.history_commands_csv is None:
            if ci_artifacts_dir is not None:
                args.history_commands_csv = _decorate_generated_path(
                    ci_artifacts_dir / "profile_matchups_next_commands.csv",
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
            else:
                args.history_commands_csv = _decorate_generated_path(
                    _default_history_artifact_path(args.history_csv, "next_commands", "csv"),
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
        if args.history_commands_json is None:
            if ci_artifacts_dir is not None:
                args.history_commands_json = _decorate_generated_path(
                    ci_artifacts_dir / "profile_matchups_next_commands.json",
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
            else:
                args.history_commands_json = _decorate_generated_path(
                    _default_history_artifact_path(args.history_csv, "next_commands", "json"),
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
        if args.history_metrics_output is None:
            if ci_artifacts_dir is not None:
                args.history_metrics_output = _decorate_generated_path(
                    ci_artifacts_dir / "profile_matchups_history_metrics.json",
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
            else:
                args.history_metrics_output = _decorate_generated_path(
                    _default_history_artifact_path(args.history_csv, "metrics", "json"),
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
        if args.history_bundle_output is None:
            if ci_artifacts_dir is not None:
                args.history_bundle_output = _decorate_generated_path(
                    ci_artifacts_dir / "profile_matchups_history_bundle.json",
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
            else:
                args.history_bundle_output = _decorate_generated_path(
                    _default_history_artifact_path(args.history_csv, "bundle", "json"),
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
        if args.history_ci_output_json is None:
            if ci_artifacts_dir is not None:
                args.history_ci_output_json = _decorate_generated_path(
                    ci_artifacts_dir / "profile_matchups_history_ci.json",
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
            else:
                args.history_ci_output_json = _decorate_generated_path(
                    _default_history_artifact_path(args.history_csv, "ci", "json"),
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
        if args.history_artifact_manifest is None:
            if ci_artifacts_dir is not None:
                args.history_artifact_manifest = _decorate_generated_path(
                    ci_artifacts_dir / "profile_matchups_history_artifacts_manifest.json",
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )
            else:
                args.history_artifact_manifest = _decorate_generated_path(
                    _default_history_artifact_path(args.history_csv, "artifacts_manifest", "json"),
                    output_prefix=args.output_prefix,
                    timestamp_tag=timestamp_tag,
                )

    history_post_outputs_requested = any(
        path is not None
        for path in (
            args.history_summary_json,
            args.history_summary_csv,
            args.history_recent_runs_csv,
            args.history_commands_output,
            args.history_commands_csv,
            args.history_commands_json,
            args.history_metrics_output,
            args.history_bundle_output,
            args.history_ci_output_json,
            args.history_artifact_manifest,
        )
    )
    history_summary_compute_requested = (
        history_post_outputs_requested
        or bool(args.print_history_next_commands)
        or bool(args.print_history_summary_json)
        or bool(args.print_history_metrics_json)
        or bool(args.print_history_ci_summary)
        or bool(args.print_history_bundle_json)
    )
    if history_summary_compute_requested and args.history_csv is None:
        parser.error("--history-csv is required when using history summary/commands output flags.")

    rows_csv = args.rows_csv or _decorate_generated_path(
        _default_csv_path(args.output, "rows"),
        output_prefix=args.output_prefix,
        timestamp_tag=timestamp_tag,
    )
    summary_csv = args.summary_csv or _decorate_generated_path(
        _default_csv_path(args.output, "summary"),
        output_prefix=args.output_prefix,
        timestamp_tag=timestamp_tag,
    )
    h2h_csv = args.h2h_csv or _decorate_generated_path(
        _default_csv_path(args.output, "h2h"),
        output_prefix=args.output_prefix,
        timestamp_tag=timestamp_tag,
    )
    seat_bias_csv = args.seat_bias_csv or _decorate_generated_path(
        _default_csv_path(args.output, "seat_bias"),
        output_prefix=args.output_prefix,
        timestamp_tag=timestamp_tag,
    )
    overview_csv = args.overview_csv or _decorate_generated_path(
        _default_csv_path(args.output, "overview"),
        output_prefix=args.output_prefix,
        timestamp_tag=timestamp_tag,
    )

    if args.dry_run:
        plan = {
            "pipeline_profile": args.pipeline_profile,
            "history_profile": args.history_profile,
            "effective_pipeline": {
                "games_per_matchup": games_per_matchup,
                "max_actions": max_actions,
                "min_games_for_recommendation": min_games_for_recommendation,
                "decisive_rate_alert_threshold": decisive_rate_alert_threshold,
                "seat_bias_alert_threshold": seat_bias_alert_threshold,
                "shuffle_decks": bool(args.shuffle_decks),
                "seat_balanced": bool(args.seat_balanced),
                "seed": args.seed,
            },
            "effective_history": {
                "history_csv": "" if args.history_csv is None else str(args.history_csv),
                "recent_window": history_recent_window,
                "recent_runs_window": history_recent_runs_window,
                "seat_bias_alert_threshold": history_seat_bias_alert_threshold,
                "decisive_rate_alert_threshold": history_decisive_rate_alert_threshold,
                "min_runs_for_ready": history_min_runs_for_ready,
                "auto_refresh_history_artifacts": bool(args.auto_refresh_history_artifacts),
            },
            "effective_gates": {
                "fail_on_alerts": bool(args.fail_on_alerts),
                "fail_on_unreliable_recommendation": bool(args.fail_on_unreliable_recommendation),
                "ci_mode": bool(args.ci_mode),
                "ci_retain_latest": None if args.ci_retain_latest is None else int(args.ci_retain_latest),
            },
            "planned_artifacts": {
                "output_json": str(args.output),
                "rows_csv": str(rows_csv),
                "summary_csv": str(summary_csv),
                "h2h_csv": str(h2h_csv),
                "seat_bias_csv": str(seat_bias_csv),
                "overview_csv": str(overview_csv),
                "run_manifest": "" if args.run_manifest is None else str(args.run_manifest),
                "recommendation_output": "" if args.recommendation_output is None else str(args.recommendation_output),
                "metrics_output": "" if args.metrics_output is None else str(args.metrics_output),
                "commands_output_json": "" if args.commands_output_json is None else str(args.commands_output_json),
                "bundle_output": "" if args.bundle_output is None else str(args.bundle_output),
                "history_summary_json": "" if args.history_summary_json is None else str(args.history_summary_json),
                "history_summary_csv": "" if args.history_summary_csv is None else str(args.history_summary_csv),
                "history_recent_runs_csv": "" if args.history_recent_runs_csv is None else str(args.history_recent_runs_csv),
                "history_commands_output": "" if args.history_commands_output is None else str(args.history_commands_output),
                "history_commands_csv": "" if args.history_commands_csv is None else str(args.history_commands_csv),
                "history_commands_json": "" if args.history_commands_json is None else str(args.history_commands_json),
                "history_metrics_output": "" if args.history_metrics_output is None else str(args.history_metrics_output),
                "history_bundle_output": "" if args.history_bundle_output is None else str(args.history_bundle_output),
                "history_ci_output_json": "" if args.history_ci_output_json is None else str(args.history_ci_output_json),
                "history_artifact_manifest": "" if args.history_artifact_manifest is None else str(args.history_artifact_manifest),
            },
        }
        print("dry_run_plan_json:")
        print(json.dumps(plan, indent=2))
        return

    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
    repo = SQLiteCardRepository(args.db_path) if args.db_path.exists() else None
    effect_catalog = args.effect_catalog if args.effect_catalog.exists() else None

    def _engine_factory() -> RulesEngine:
        skill_cost_catalog = args.skill_cost_catalog if args.skill_cost_catalog.exists() else None
        return RulesEngine(card_repository=repo, skill_cost_rules_path=skill_cost_catalog, effect_rules_path=effect_catalog)

    if args.seat_balanced:
        rows_fp1 = run_profile_matchup_matrix(
            engine_factory=_engine_factory,
            state_factory=_make_state_factory(shuffle_decks=bool(args.shuffle_decks), seed=args.seed, first_player=1),
            profiles=profiles,
            games_per_matchup=games_per_matchup,
            max_actions=max_actions,
        )
        seed2 = None if args.seed is None else (int(args.seed) + 1_000_000)
        rows_fp2 = run_profile_matchup_matrix(
            engine_factory=_engine_factory,
            state_factory=_make_state_factory(shuffle_decks=bool(args.shuffle_decks), seed=seed2, first_player=2),
            profiles=profiles,
            games_per_matchup=games_per_matchup,
            max_actions=max_actions,
        )
        rows = merge_matchup_rows([*rows_fp1, *rows_fp2])
    else:
        rows = run_profile_matchup_matrix(
            engine_factory=_engine_factory,
            state_factory=_make_state_factory(shuffle_decks=bool(args.shuffle_decks), seed=args.seed, first_player=1),
            profiles=profiles,
            games_per_matchup=games_per_matchup,
            max_actions=max_actions,
        )
    summary = summarize_profile_strength(rows)
    matrix = build_head_to_head_matrix(rows)
    seat_bias = compute_seat_bias(rows)
    match_quality = compute_match_quality(rows, decisive_rate_alert_threshold=decisive_rate_alert_threshold)
    recommendation = recommend_profile(summary, min_games_per_profile=min_games_for_recommendation)
    seat_bias_delta = float(seat_bias.get("p1_minus_p2", 0.0))
    seat_bias_alert = abs(seat_bias_delta) > float(seat_bias_alert_threshold)
    low_decisive_rate_alert = bool(match_quality.get("low_decisive_rate_alert", False))
    recommendation_reliable = bool(recommendation.get("reliable", False))
    ci_alert_failed = bool(low_decisive_rate_alert or seat_bias_alert)
    ci_recommendation_failed = not recommendation_reliable
    ci_failed = bool(ci_alert_failed or ci_recommendation_failed)
    payload = {
        "pipeline_profile": args.pipeline_profile,
        "profiles": profiles,
        "games_per_matchup": games_per_matchup,
        "max_actions": max_actions,
        "shuffle_decks": bool(args.shuffle_decks),
        "seat_balanced": bool(args.seat_balanced),
        "seed": args.seed,
        "min_games_for_recommendation": min_games_for_recommendation,
        "decisive_rate_alert_threshold": decisive_rate_alert_threshold,
        "seat_bias_alert_threshold": seat_bias_alert_threshold,
        "rows": matchup_rows_to_dict(rows),
        "profile_summary": summary,
        "seat_bias": seat_bias,
        "match_quality": match_quality,
        "recommendation": recommendation,
        "alerts": {
            "low_decisive_rate_alert": low_decisive_rate_alert,
            "seat_bias_alert": seat_bias_alert,
        },
        "ci": {
            "ci_mode": bool(args.ci_mode),
            "alert_failed": ci_alert_failed,
            "recommendation_failed": ci_recommendation_failed,
            "status": "fail" if ci_failed else "pass",
            "ci_retain_latest": None if args.ci_retain_latest is None else int(args.ci_retain_latest),
        },
    }
    primary_summary_text_lines = [
        f"rows: {len(rows)}",
        f"seat_bias_p1_minus_p2: {seat_bias.get('p1_minus_p2')}",
        f"decisive_rate: {match_quality.get('decisive_rate')}",
        f"low_decisive_rate_alert: {match_quality.get('low_decisive_rate_alert')}",
        f"seat_bias_alert: {seat_bias_alert}",
        f"recommended_profile: {recommendation.get('recommended_profile')}",
        f"recommendation_reason: {recommendation.get('reason')}",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log(f"wrote: {args.output}")
    rows_csv.parent.mkdir(parents=True, exist_ok=True)
    with rows_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "p1_profile",
                "p2_profile",
                "games",
                "p1_wins",
                "p2_wins",
                "draws",
                "avg_actions",
                "avg_turn",
            ],
        )
        writer.writeheader()
        writer.writerows(
            {
                "p1_profile": row.p1_profile,
                "p2_profile": row.p2_profile,
                "games": row.games,
                "p1_wins": row.p1_wins,
                "p2_wins": row.p2_wins,
                "draws": row.draws,
                "avg_actions": row.avg_actions,
                "avg_turn": row.avg_turn,
            }
            for row in rows
        )
    log(f"wrote: {rows_csv}")

    summary_rows = profile_summary_to_csv_rows(summary)
    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    with summary_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["profile", "points_per_game", "win_rate", "wins", "losses", "draws", "games", "points"],
        )
        writer.writeheader()
        writer.writerows(summary_rows)
    log(f"wrote: {summary_csv}")

    h2h_rows = head_to_head_to_csv_rows(matrix)
    h2h_csv.parent.mkdir(parents=True, exist_ok=True)
    with h2h_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["p1_profile", "p2_profile", "p1_win_rate"],
        )
        writer.writeheader()
        writer.writerows(h2h_rows)
    log(f"wrote: {h2h_csv}")

    seat_bias_rows = seat_bias_to_csv_rows(seat_bias)
    seat_bias_csv.parent.mkdir(parents=True, exist_ok=True)
    with seat_bias_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["p1_profile", "p2_profile", "games", "p1_win_rate", "p2_win_rate", "draw_rate"],
        )
        writer.writeheader()
        writer.writerows(seat_bias_rows)
    log(f"wrote: {seat_bias_csv}")

    overview_row = build_overview_csv_row(
        profiles=profiles,
        games_per_matchup=games_per_matchup,
        max_actions=max_actions,
        shuffle_decks=bool(args.shuffle_decks),
        seat_balanced=bool(args.seat_balanced),
        seed=args.seed,
        min_games_for_recommendation=min_games_for_recommendation,
        recommendation=recommendation,
        seat_bias=seat_bias,
        match_quality=match_quality,
    )
    overview_csv.parent.mkdir(parents=True, exist_ok=True)
    with overview_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "profiles",
                "games_per_matchup",
                "max_actions",
                "shuffle_decks",
                "seat_balanced",
                "seed",
                "min_games_for_recommendation",
                "recommended_profile",
                "recommendation_reason",
                "recommendation_reliable",
                "recommendation_clear_edge",
                "seat_bias_games",
                "seat_bias_p1_win_rate",
                "seat_bias_p2_win_rate",
                "seat_bias_draw_rate",
                "seat_bias_p1_minus_p2",
                "match_quality_draw_rate",
                "match_quality_decisive_rate",
                "match_quality_low_decisive_rate_alert",
            ],
        )
        writer.writeheader()
        writer.writerow(overview_row)
    log(f"wrote: {overview_csv}")
    run_manifest_payload: dict[str, object] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pipeline_profile": args.pipeline_profile,
        "pipeline_effective": {
            "profiles": profiles,
            "games_per_matchup": games_per_matchup,
            "max_actions": max_actions,
            "shuffle_decks": bool(args.shuffle_decks),
            "seat_balanced": bool(args.seat_balanced),
            "seed": args.seed,
            "min_games_for_recommendation": min_games_for_recommendation,
            "decisive_rate_alert_threshold": decisive_rate_alert_threshold,
            "seat_bias_alert_threshold": seat_bias_alert_threshold,
        },
        "artifacts": {
            "output_json": str(args.output),
            "rows_csv": str(rows_csv),
            "summary_csv": str(summary_csv),
            "h2h_csv": str(h2h_csv),
            "seat_bias_csv": str(seat_bias_csv),
            "overview_csv": str(overview_csv),
        },
        "result_snapshot": {
            "rows": len(rows),
            "seat_bias_p1_minus_p2": seat_bias.get("p1_minus_p2"),
            "seat_bias_alert": seat_bias_alert,
            "decisive_rate": match_quality.get("decisive_rate"),
            "low_decisive_rate_alert": match_quality.get("low_decisive_rate_alert"),
            "recommended_profile": recommendation.get("recommended_profile"),
            "recommendation_reason": recommendation.get("reason"),
        },
        "ci": {
            "ci_mode": bool(args.ci_mode),
            "alert_failed": ci_alert_failed,
            "recommendation_failed": ci_recommendation_failed,
            "status": "fail" if ci_failed else "pass",
        },
    }
    recommendation_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pipeline_profile": args.pipeline_profile,
        "history_profile": args.history_profile,
        "recommended_profile": recommendation.get("recommended_profile"),
        "recommendation_reason": recommendation.get("reason"),
        "recommendation_reliable": recommendation.get("reliable"),
        "recommendation_clear_edge": recommendation.get("clear_edge"),
        "min_games_for_recommendation": min_games_for_recommendation,
        "decisive_rate_alert_threshold": decisive_rate_alert_threshold,
        "seat_bias_alert_threshold": seat_bias_alert_threshold,
        "alerts": {
            "low_decisive_rate_alert": low_decisive_rate_alert,
            "seat_bias_alert": seat_bias_alert,
        },
    }

    if args.history_csv is not None:
        history_row = build_history_csv_row(
            overview_row,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            source_json=str(args.output),
        )
        args.history_csv.parent.mkdir(parents=True, exist_ok=True)
        file_exists = args.history_csv.exists()
        with args.history_csv.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(history_row.keys()))
            if not file_exists:
                writer.writeheader()
            writer.writerow(history_row)
        log(f"appended: {args.history_csv}")
        run_manifest_payload["history"] = {
            "history_csv": str(args.history_csv),
            "history_profile": args.history_profile,
            "history_effective": {
                "recent_window": history_recent_window,
                "recent_runs_window": history_recent_runs_window,
                "seat_bias_alert_threshold": history_seat_bias_alert_threshold,
                "decisive_rate_alert_threshold": history_decisive_rate_alert_threshold,
                "min_runs_for_ready": history_min_runs_for_ready,
            },
        }

    history_summary_payload: dict[str, object] | None = None
    history_bundle_payload: dict[str, object] | None = None
    if history_summary_compute_requested and args.history_csv is not None and args.history_csv.exists():
        history_rows: list[dict[str, str]] = []
        with args.history_csv.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                history_rows.append(dict(row))
        history_summary = summarize_history_rows(
            history_rows,
            recent_window=history_recent_window,
            seat_bias_alert_threshold=history_seat_bias_alert_threshold,
            decisive_rate_alert_threshold=history_decisive_rate_alert_threshold,
            min_runs_for_ready=history_min_runs_for_ready,
        )
        history_summary_payload = history_summary
        if args.print_history_next_commands:
            hints = command_hints_from_summary(history_summary)
            print(f"history_prioritized_next_step: {hints.get('prioritized_next_step', '')}")
            print(f"history_next_command_hint: {hints.get('next_command_hint', '')}")
            print(f"history_followup_command_hint: {hints.get('followup_command_hint', '')}")
            print(f"history_next_command_sequence_shell: {hints.get('next_command_sequence_shell', '')}")
            print(f"history_next_command_sequence_powershell: {hints.get('next_command_sequence_powershell', '')}")
            print(f"history_next_command_sequence_bash: {hints.get('next_command_sequence_bash', '')}")

        if args.history_summary_json is not None:
            args.history_summary_json.parent.mkdir(parents=True, exist_ok=True)
            args.history_summary_json.write_text(json.dumps(history_summary, indent=2), encoding="utf-8")
            log(f"wrote: {args.history_summary_json}")
        if args.history_summary_csv is not None:
            row = history_summary_to_csv_row(history_summary)
            args.history_summary_csv.parent.mkdir(parents=True, exist_ok=True)
            with args.history_summary_csv.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
                writer.writeheader()
                writer.writerow(row)
            log(f"wrote: {args.history_summary_csv}")
        if args.history_recent_runs_csv is not None:
            rows_out = history_recent_runs_to_csv_rows(
                history_rows,
                recent_window=history_recent_runs_window,
            )
            args.history_recent_runs_csv.parent.mkdir(parents=True, exist_ok=True)
            with args.history_recent_runs_csv.open("w", encoding="utf-8", newline="") as fh:
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
            log(f"wrote: {args.history_recent_runs_csv}")
        if args.history_commands_output is not None:
            hints = command_hints_from_summary(history_summary)
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
            args.history_commands_output.parent.mkdir(parents=True, exist_ok=True)
            args.history_commands_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
            log(f"wrote: {args.history_commands_output}")
        if args.history_commands_csv is not None:
            row = command_hints_to_csv_row(history_summary)
            args.history_commands_csv.parent.mkdir(parents=True, exist_ok=True)
            with args.history_commands_csv.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
                writer.writeheader()
                writer.writerow(row)
            log(f"wrote: {args.history_commands_csv}")
        if args.history_commands_json is not None:
            payload = command_hints_to_json_payload(history_summary)
            args.history_commands_json.parent.mkdir(parents=True, exist_ok=True)
            args.history_commands_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            log(f"wrote: {args.history_commands_json}")
        history_commands_payload = command_hints_to_json_payload(history_summary)
        if args.history_metrics_output is not None:
            history_metrics_payload = {
                "total_runs": int(history_summary.get("total_runs", 0)),
                "overall_status": str(history_summary.get("overall_status", "")),
                "is_ready_for_next_phase": bool(history_summary.get("is_ready_for_next_phase", False)),
                "readiness_score": float(history_summary.get("readiness_score", 0.0)),
                "readiness_blocker_count": int(history_summary.get("readiness_blocker_count", 0)),
                "recommended_action": str(history_summary.get("recommended_action", "")),
                "stability_label": str(history_summary.get("stability_label", "")),
                "quality_alert_count": int(history_summary.get("quality_alert_count", 0)),
                "seat_bias_alert_count": int(history_summary.get("seat_bias_alert_count", 0)),
                "low_decisive_rate_alert_count": int(history_summary.get("low_decisive_rate_alert_count", 0)),
            }
            args.history_metrics_output.parent.mkdir(parents=True, exist_ok=True)
            args.history_metrics_output.write_text(json.dumps(history_metrics_payload, indent=2), encoding="utf-8")
            log(f"wrote: {args.history_metrics_output}")
        else:
            history_metrics_payload = {
                "total_runs": int(history_summary.get("total_runs", 0)),
                "overall_status": str(history_summary.get("overall_status", "")),
                "is_ready_for_next_phase": bool(history_summary.get("is_ready_for_next_phase", False)),
                "readiness_score": float(history_summary.get("readiness_score", 0.0)),
                "readiness_blocker_count": int(history_summary.get("readiness_blocker_count", 0)),
                "recommended_action": str(history_summary.get("recommended_action", "")),
                "stability_label": str(history_summary.get("stability_label", "")),
                "quality_alert_count": int(history_summary.get("quality_alert_count", 0)),
                "seat_bias_alert_count": int(history_summary.get("seat_bias_alert_count", 0)),
                "low_decisive_rate_alert_count": int(history_summary.get("low_decisive_rate_alert_count", 0)),
            }
        history_bundle_payload = {
            "summary": history_summary,
            "commands": history_commands_payload,
            "metrics": history_metrics_payload,
        }
        if args.history_bundle_output is not None:
            args.history_bundle_output.parent.mkdir(parents=True, exist_ok=True)
            if args.history_bundle_output_compact:
                args.history_bundle_output.write_text(
                    json.dumps(history_bundle_payload, separators=(",", ":")),
                    encoding="utf-8",
                )
            else:
                args.history_bundle_output.write_text(json.dumps(history_bundle_payload, indent=2), encoding="utf-8")
            log(f"wrote: {args.history_bundle_output}")
        if args.history_artifact_manifest is not None:
            manifest = {
                "history_csv": str(args.history_csv),
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "history_profile": args.history_profile,
                "recent_window": history_recent_window,
                "recent_runs_window": history_recent_runs_window,
                "seat_bias_alert_threshold": history_seat_bias_alert_threshold,
                "decisive_rate_alert_threshold": history_decisive_rate_alert_threshold,
                "min_runs_for_ready": history_min_runs_for_ready,
                "artifacts": {
                    "history_summary_json": "" if args.history_summary_json is None else str(args.history_summary_json),
                    "history_summary_csv": "" if args.history_summary_csv is None else str(args.history_summary_csv),
                    "history_recent_runs_csv": "" if args.history_recent_runs_csv is None else str(args.history_recent_runs_csv),
                    "history_commands_output": "" if args.history_commands_output is None else str(args.history_commands_output),
                    "history_commands_csv": "" if args.history_commands_csv is None else str(args.history_commands_csv),
                    "history_commands_json": "" if args.history_commands_json is None else str(args.history_commands_json),
                    "history_metrics_output": "" if args.history_metrics_output is None else str(args.history_metrics_output),
                    "history_bundle_output": "" if args.history_bundle_output is None else str(args.history_bundle_output),
                    "history_ci_output_json": "" if args.history_ci_output_json is None else str(args.history_ci_output_json),
                },
            }
            args.history_artifact_manifest.parent.mkdir(parents=True, exist_ok=True)
            args.history_artifact_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            log(f"wrote: {args.history_artifact_manifest}")
            if isinstance(run_manifest_payload.get("history"), dict):
                run_manifest_payload["history"]["history_artifact_manifest"] = str(args.history_artifact_manifest)

    history_ci_out = _compute_history_ci_out(
        history_summary_payload=history_summary_payload,
        history_ci_status_threshold=str(args.history_ci_status_threshold),
        history_ci_readiness_mode=str(args.history_ci_readiness_mode),
        history_ci_blockers_mode=str(args.history_ci_blockers_mode),
        history_ci_unknown_mode=str(args.history_ci_unknown_mode),
        history_ci_readiness_score_threshold=(
            None
            if args.history_ci_readiness_score_threshold is None
            else float(args.history_ci_readiness_score_threshold)
        ),
    )

    if args.recommendation_output is not None:
        args.recommendation_output.parent.mkdir(parents=True, exist_ok=True)
        args.recommendation_output.write_text(json.dumps(recommendation_payload, indent=2), encoding="utf-8")
        log(f"wrote: {args.recommendation_output}")
    metrics_payload = {
        "rows": len(rows),
        "seat_bias_p1_minus_p2": seat_bias.get("p1_minus_p2"),
        "seat_bias_alert": seat_bias_alert,
        "decisive_rate": match_quality.get("decisive_rate"),
        "low_decisive_rate_alert": low_decisive_rate_alert,
        "recommended_profile": recommendation.get("recommended_profile"),
        "recommendation_reason": recommendation.get("reason"),
        "recommendation_reliable": recommendation_reliable,
    }
    if args.metrics_output is not None:
        args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
        args.metrics_output.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")
        log(f"wrote: {args.metrics_output}")
    ci_summary_payload = {
        "ci_mode": bool(args.ci_mode),
        "status": "fail" if ci_failed else "pass",
        "alert_failed": ci_alert_failed,
        "recommendation_failed": ci_recommendation_failed,
        "core_status": "fail" if ci_failed else "pass",
        "ci_status_include_history_ci": bool(args.ci_status_include_history_ci),
        "low_decisive_rate_alert": low_decisive_rate_alert,
        "seat_bias_alert": seat_bias_alert,
        "recommendation_reliable": recommendation_reliable,
        "recommended_profile": recommendation.get("recommended_profile"),
        "recommendation_reason": recommendation.get("reason"),
        "history_ci_policy": {
            "status_threshold": str(args.history_ci_status_threshold),
            "readiness_mode": str(args.history_ci_readiness_mode),
            "blockers_mode": str(args.history_ci_blockers_mode),
            "unknown_mode": str(args.history_ci_unknown_mode),
        },
    }
    if isinstance(history_summary_payload, dict):
        commands_payload = command_hints_to_json_payload(history_summary_payload)
        commands_payload["source"] = "history_summary"
    else:
        commands_payload = {
            "source": "unavailable",
            "prioritized_next_step": "",
            "next_command_hint": "",
            "followup_command_hint": "",
            "next_command_sequence": {
                "shell": "",
                "powershell": "",
                "bash": "",
                "multiline": "",
            },
        }
    if args.commands_output_json is not None:
        args.commands_output_json.parent.mkdir(parents=True, exist_ok=True)
        args.commands_output_json.write_text(json.dumps(commands_payload, indent=2), encoding="utf-8")
        log(f"wrote: {args.commands_output_json}")
    bundle_payload = {
        "run": payload,
        "recommendation": recommendation_payload,
        "metrics": metrics_payload,
        "ci_summary": ci_summary_payload,
        "history_ci": history_ci_out,
        "commands": commands_payload,
        "run_manifest": run_manifest_payload,
    }
    if args.bundle_include_history_summary and isinstance(history_summary_payload, dict):
        bundle_payload["history_summary"] = history_summary_payload

    cleanup_removed: list[Path] = []
    if ci_artifacts_dir is not None and args.ci_retain_latest is not None:
        cleanup_removed = _cleanup_ci_artifacts(
            ci_artifacts_dir,
            retain_latest=max(1, int(args.ci_retain_latest)),
        )
        log(
            f"ci_cleanup_removed_files: {len(cleanup_removed)} "
            f"(retain_latest={max(1, int(args.ci_retain_latest))})"
        )
        run_manifest_payload["ci_cleanup"] = {
            "retain_latest": max(1, int(args.ci_retain_latest)),
            "removed_count": len(cleanup_removed),
            "removed_files": [str(p) for p in cleanup_removed],
        }

    if args.summary_format in {"text", "both"}:
        for line in primary_summary_text_lines:
            print(line)
    if args.summary_format in {"json", "both"}:
        print("run_summary_json:")
        print(json.dumps(payload, indent=2))
    if args.print_metrics_json:
        print(f"metrics_json: {json.dumps(metrics_payload, separators=(',', ':'))}")
    if args.print_commands_json:
        print(f"commands_json: {json.dumps(commands_payload, separators=(',', ':'))}")
    if args.print_history_summary_json:
        payload_out = history_summary_payload if isinstance(history_summary_payload, dict) else {}
        print(f"history_summary_json: {json.dumps(payload_out, separators=(',', ':'))}")
    if args.print_history_metrics_json:
        if isinstance(history_summary_payload, dict):
            history_metrics_out = {
                "total_runs": int(history_summary_payload.get("total_runs", 0)),
                "overall_status": str(history_summary_payload.get("overall_status", "")),
                "is_ready_for_next_phase": bool(history_summary_payload.get("is_ready_for_next_phase", False)),
                "readiness_score": float(history_summary_payload.get("readiness_score", 0.0)),
                "readiness_blocker_count": int(history_summary_payload.get("readiness_blocker_count", 0)),
                "recommended_action": str(history_summary_payload.get("recommended_action", "")),
                "stability_label": str(history_summary_payload.get("stability_label", "")),
                "quality_alert_count": int(history_summary_payload.get("quality_alert_count", 0)),
                "seat_bias_alert_count": int(history_summary_payload.get("seat_bias_alert_count", 0)),
                "low_decisive_rate_alert_count": int(history_summary_payload.get("low_decisive_rate_alert_count", 0)),
                "source": "history_summary",
            }
        else:
            history_metrics_out = {"source": "unavailable"}
        print(f"history_metrics_json: {json.dumps(history_metrics_out, separators=(',', ':'))}")
    if args.print_history_bundle_json:
        if isinstance(history_bundle_payload, dict):
            history_bundle_out = history_bundle_payload
        else:
            history_bundle_out = {"source": "unavailable"}
        print(f"history_bundle_json: {json.dumps(history_bundle_out, separators=(',', ':'))}")
    if args.print_history_ci_summary:
        print(f"history_ci_summary_json: {json.dumps(history_ci_out, separators=(',', ':'))}")
    if args.print_bundle_json:
        print(f"bundle_json: {json.dumps(bundle_payload, separators=(',', ':'))}")
    history_ci_policy_payload = {
        "status_threshold": str(args.history_ci_status_threshold),
        "readiness_mode": str(args.history_ci_readiness_mode),
        "blockers_mode": str(args.history_ci_blockers_mode),
        "unknown_mode": str(args.history_ci_unknown_mode),
        "readiness_score_threshold": (
            None
            if args.history_ci_readiness_score_threshold is None
            else max(0.0, min(1.0, float(args.history_ci_readiness_score_threshold)))
        ),
    }
    if args.print_history_ci_policy_json:
        print(f"history_ci_policy_json: {json.dumps(history_ci_policy_payload, separators=(',', ':'))}")
    history_ci_status = str(history_ci_out.get("status", "unknown"))
    history_ci_failed = history_ci_status != "pass"
    pipeline_ci_failed = _compute_pipeline_ci_failed(
        core_ci_failed=ci_failed,
        include_history_ci=bool(args.ci_status_include_history_ci),
        history_ci_status=history_ci_status,
    )
    ci_summary_payload["history_ci_failed"] = history_ci_failed
    ci_summary_payload["status"] = "fail" if pipeline_ci_failed else "pass"
    ci_summary_payload["history_ci_status"] = history_ci_status
    ci_summary_payload["history_ci_source"] = str(history_ci_out.get("source", ""))
    ci_summary_payload["history_ci_reasons"] = history_ci_out.get("reasons", [])
    if args.history_ci_output_json is not None:
        args.history_ci_output_json.parent.mkdir(parents=True, exist_ok=True)
        if args.history_ci_output_compact:
            args.history_ci_output_json.write_text(
                json.dumps(history_ci_out, separators=(",", ":")),
                encoding="utf-8",
            )
        else:
            args.history_ci_output_json.write_text(json.dumps(history_ci_out, indent=2), encoding="utf-8")
        log(f"wrote: {args.history_ci_output_json}")
    run_manifest_payload.setdefault("ci", {})
    if isinstance(run_manifest_payload["ci"], dict):
        run_manifest_payload["ci"]["core_status"] = "fail" if ci_failed else "pass"
        run_manifest_payload["ci"]["ci_status_include_history_ci"] = bool(args.ci_status_include_history_ci)
        run_manifest_payload["ci"]["history_ci_failed"] = history_ci_failed
        run_manifest_payload["ci"]["status"] = "fail" if pipeline_ci_failed else "pass"
        run_manifest_payload["ci"]["history_ci_status"] = history_ci_status
        run_manifest_payload["ci"]["history_ci_source"] = str(history_ci_out.get("source", ""))
        run_manifest_payload["ci"]["history_ci_reasons"] = history_ci_out.get("reasons", [])
        run_manifest_payload["ci"]["history_ci_policy"] = history_ci_policy_payload
    bundle_payload["ci_summary"] = ci_summary_payload
    bundle_payload["history_ci"] = history_ci_out
    bundle_payload["run_manifest"] = run_manifest_payload
    if args.run_manifest is not None:
        args.run_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.run_manifest.write_text(json.dumps(run_manifest_payload, indent=2), encoding="utf-8")
        log(f"wrote: {args.run_manifest}")
    if args.bundle_output is not None:
        args.bundle_output.parent.mkdir(parents=True, exist_ok=True)
        if args.bundle_output_compact:
            args.bundle_output.write_text(json.dumps(bundle_payload, separators=(",", ":")), encoding="utf-8")
        else:
            args.bundle_output.write_text(json.dumps(bundle_payload, indent=2), encoding="utf-8")
        log(f"wrote: {args.bundle_output}")
    if args.print_run_manifest:
        print("run_manifest_json:")
        print(json.dumps(run_manifest_payload, indent=2))
    if args.print_ci_summary:
        print(f"ci_summary_json: {json.dumps(ci_summary_payload, separators=(',', ':'))}")
    if args.print_history_ci_output_path:
        path_out = "" if args.history_ci_output_json is None else str(args.history_ci_output_json)
        print(f"history_ci_output_path: {path_out}")
    if args.print_recommendation_only:
        print(str(recommendation.get("recommended_profile", "")))
    exit_code, exit_message = _resolve_failure_exit_code(
        fail_on_ci_status_only=bool(args.fail_on_ci_status_only),
        fail_on_ci_status=bool(args.fail_on_ci_status),
        ci_status=str(ci_summary_payload.get("status", "pass")),
        fail_on_alerts=bool(args.fail_on_alerts),
        low_decisive_rate_alert=bool(low_decisive_rate_alert),
        seat_bias_alert=bool(seat_bias_alert),
        fail_on_unreliable_recommendation=bool(args.fail_on_unreliable_recommendation),
        recommendation_reliable=bool(recommendation_reliable),
        fail_on_history_ci=bool(args.fail_on_history_ci),
        history_ci_status=str(history_ci_out.get("status", "unknown")),
    )
    if exit_code is not None:
        if exit_message:
            print(exit_message)
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
