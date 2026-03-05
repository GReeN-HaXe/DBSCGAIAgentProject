from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class TimingHistoryRow:
    timestamp_utc: str
    pipeline_profile: str
    total_seconds: float
    slowest_stage: str
    slowest_seconds: float
    regressed: bool


def summarize_stage_timings(stages: Iterable[dict[str, object]]) -> dict[str, object]:
    items = list(stages)
    total = 0.0
    slowest_name = ""
    slowest_seconds = 0.0
    for item in items:
        secs = float(item.get("duration_seconds", 0.0) or 0.0)
        total += secs
        if secs > slowest_seconds:
            slowest_seconds = secs
            slowest_name = str(item.get("name", ""))
    return {
        "stage_count": len(items),
        "total_seconds": total,
        "slowest_stage": slowest_name,
        "slowest_seconds": slowest_seconds,
    }


def build_timing_history_row(
    *,
    pipeline_profile: str,
    timing_summary: dict[str, object],
    regressed: bool,
) -> TimingHistoryRow:
    return TimingHistoryRow(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        pipeline_profile=str(pipeline_profile),
        total_seconds=float(timing_summary.get("total_seconds", 0.0) or 0.0),
        slowest_stage=str(timing_summary.get("slowest_stage", "")),
        slowest_seconds=float(timing_summary.get("slowest_seconds", 0.0) or 0.0),
        regressed=bool(regressed),
    )


def timing_history_row_to_dict(row: TimingHistoryRow) -> dict[str, str]:
    return {
        "timestamp_utc": row.timestamp_utc,
        "pipeline_profile": row.pipeline_profile,
        "total_seconds": f"{row.total_seconds:.6f}",
        "slowest_stage": row.slowest_stage,
        "slowest_seconds": f"{row.slowest_seconds:.6f}",
        "regressed": "1" if row.regressed else "0",
    }


def summarize_timing_history(rows: Iterable[dict[str, str]], *, recent_window: int = 20) -> dict[str, object]:
    items = list(rows)
    total_runs = len(items)
    recent = items[-max(1, int(recent_window)) :] if items else []
    if not recent:
        return {
            "total_runs": total_runs,
            "recent_window": 0,
            "avg_total_seconds_recent": 0.0,
            "max_total_seconds_recent": 0.0,
            "regression_rate_recent": 0.0,
            "latest_total_seconds": 0.0,
        }

    totals = [float(r.get("total_seconds", "0") or 0.0) for r in recent]
    regressed = [
        1
        for r in recent
        if str(r.get("regressed", "0")).strip() in {"1", "true", "True", "yes", "YES"}
    ]
    latest_total = float(recent[-1].get("total_seconds", "0") or 0.0)
    return {
        "total_runs": total_runs,
        "recent_window": len(recent),
        "avg_total_seconds_recent": (sum(totals) / len(totals)),
        "max_total_seconds_recent": max(totals),
        "regression_rate_recent": (len(regressed) / len(recent)),
        "latest_total_seconds": latest_total,
    }
