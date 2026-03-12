from __future__ import annotations

from typing import Any


def evaluate_timing_regression(
    *,
    current_timing_summary: dict[str, Any],
    baseline_timing_summary: dict[str, Any],
    max_total_seconds_regression_ratio: float,
) -> dict[str, Any]:
    current_total = float(current_timing_summary.get("total_seconds", 0.0) or 0.0)
    baseline_total = float(baseline_timing_summary.get("total_seconds", 0.0) or 0.0)
    ratio = None
    if baseline_total > 0.0:
        ratio = current_total / baseline_total
    threshold = max(0.0, float(max_total_seconds_regression_ratio))
    regressed = bool(ratio is not None and ratio > (1.0 + threshold))
    reason = ""
    if regressed:
        reason = (
            f"timing_regression_detected current_total={current_total:.6f} "
            f"baseline_total={baseline_total:.6f} ratio={ratio:.6f} "
            f"threshold={1.0 + threshold:.6f}"
        )
    return {
        "has_baseline": True,
        "current_total_seconds": current_total,
        "baseline_total_seconds": baseline_total,
        "ratio_current_over_baseline": ratio,
        "max_total_seconds_regression_ratio": threshold,
        "regressed": regressed,
        "reason": reason,
    }
