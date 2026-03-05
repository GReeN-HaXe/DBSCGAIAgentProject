from __future__ import annotations

from src.agent.pipeline_metrics import summarize_stage_timings


def test_phase6_summarize_stage_timings_basic() -> None:
    summary = summarize_stage_timings(
        [
            {"name": "play", "duration_seconds": 0.4},
            {"name": "replay", "duration_seconds": 0.2},
            {"name": "check", "duration_seconds": 0.6},
        ]
    )
    assert summary["stage_count"] == 3
    assert abs(float(summary["total_seconds"]) - 1.2) < 1e-6
    assert summary["slowest_stage"] == "check"
