from __future__ import annotations

from src.agent.pipeline_regression import evaluate_timing_regression


def test_phase6_timing_regression_not_regressed_within_threshold() -> None:
    out = evaluate_timing_regression(
        current_timing_summary={"total_seconds": 12.0},
        baseline_timing_summary={"total_seconds": 10.0},
        max_total_seconds_regression_ratio=0.25,
    )
    assert out["regressed"] is False


def test_phase6_timing_regression_detected_above_threshold() -> None:
    out = evaluate_timing_regression(
        current_timing_summary={"total_seconds": 20.0},
        baseline_timing_summary={"total_seconds": 10.0},
        max_total_seconds_regression_ratio=0.50,
    )
    assert out["regressed"] is True
    assert "timing_regression_detected" in str(out["reason"])
