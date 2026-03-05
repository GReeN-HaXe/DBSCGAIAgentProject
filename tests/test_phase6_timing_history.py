from __future__ import annotations

from src.agent.pipeline_metrics import (
    build_timing_history_row,
    summarize_timing_history,
    timing_history_row_to_dict,
)


def test_phase6_build_timing_history_row_and_dict() -> None:
    row = build_timing_history_row(
        pipeline_profile="standard",
        timing_summary={"total_seconds": 1.23, "slowest_stage": "play", "slowest_seconds": 0.8},
        regressed=False,
    )
    payload = timing_history_row_to_dict(row)
    assert payload["pipeline_profile"] == "standard"
    assert payload["regressed"] == "0"
    assert float(payload["total_seconds"]) > 1.2


def test_phase6_summarize_timing_history() -> None:
    rows = [
        {
            "timestamp_utc": "t1",
            "pipeline_profile": "quick",
            "total_seconds": "1.0",
            "slowest_stage": "a",
            "slowest_seconds": "0.5",
            "regressed": "0",
        },
        {
            "timestamp_utc": "t2",
            "pipeline_profile": "standard",
            "total_seconds": "2.0",
            "slowest_stage": "b",
            "slowest_seconds": "1.0",
            "regressed": "1",
        },
    ]
    summary = summarize_timing_history(rows, recent_window=2)
    assert summary["total_runs"] == 2
    assert summary["avg_total_seconds_recent"] == 1.5
    assert summary["max_total_seconds_recent"] == 2.0
    assert summary["regression_rate_recent"] == 0.5
