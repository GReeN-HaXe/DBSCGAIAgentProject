from __future__ import annotations

from src.agent.pipeline_history import (
    build_pipeline_history_row,
    pipeline_history_row_to_dict,
    summarize_pipeline_history,
)


def test_phase6_build_pipeline_history_row_and_dict_shape() -> None:
    row = build_pipeline_history_row(
        pipeline_profile="standard",
        play_ok=True,
        replay_ok=True,
        determinism_checked=True,
        determinism_ok=True,
        trace_hash_1="abc",
        trace_hash_2="abc",
        status="pass",
    )
    payload = pipeline_history_row_to_dict(row)
    assert payload["pipeline_profile"] == "standard"
    assert payload["play_ok"] == "1"
    assert payload["status"] == "pass"


def test_phase6_summarize_pipeline_history_rates() -> None:
    rows = [
        {
            "timestamp_utc": "t1",
            "pipeline_profile": "quick",
            "play_ok": "1",
            "replay_ok": "1",
            "determinism_checked": "0",
            "determinism_ok": "1",
            "trace_hash_1": "a",
            "trace_hash_2": "",
            "status": "pass",
        },
        {
            "timestamp_utc": "t2",
            "pipeline_profile": "standard",
            "play_ok": "1",
            "replay_ok": "0",
            "determinism_checked": "1",
            "determinism_ok": "0",
            "trace_hash_1": "b",
            "trace_hash_2": "c",
            "status": "fail",
        },
    ]
    summary = summarize_pipeline_history(rows, recent_window=2)
    assert summary["total_runs"] == 2
    assert summary["pass_rate_total"] == 0.5
    assert summary["determinism_checks_recent"] == 1
    assert summary["determinism_pass_rate_recent"] == 0.0
    assert summary["overall_status"] in {"warning", "critical"}


def test_phase6_summarize_pipeline_history_healthy_status() -> None:
    rows = [
        {
            "timestamp_utc": "t1",
            "pipeline_profile": "standard",
            "play_ok": "1",
            "replay_ok": "1",
            "determinism_checked": "1",
            "determinism_ok": "1",
            "trace_hash_1": "a",
            "trace_hash_2": "a",
            "status": "pass",
        }
    ]
    summary = summarize_pipeline_history(rows, recent_window=5, min_recent_pass_rate=0.8, min_determinism_pass_rate=1.0)
    assert summary["overall_status"] == "healthy"
    assert summary["is_ready"] is True
