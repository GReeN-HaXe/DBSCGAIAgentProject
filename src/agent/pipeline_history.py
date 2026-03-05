from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class PipelineHistoryRow:
    timestamp_utc: str
    pipeline_profile: str
    play_ok: bool
    replay_ok: bool
    determinism_checked: bool
    determinism_ok: bool
    trace_hash_1: str
    trace_hash_2: str
    status: str


def build_pipeline_history_row(
    *,
    pipeline_profile: str,
    play_ok: bool,
    replay_ok: bool,
    determinism_checked: bool,
    determinism_ok: bool,
    trace_hash_1: str,
    trace_hash_2: str | None,
    status: str,
) -> PipelineHistoryRow:
    return PipelineHistoryRow(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        pipeline_profile=str(pipeline_profile),
        play_ok=bool(play_ok),
        replay_ok=bool(replay_ok),
        determinism_checked=bool(determinism_checked),
        determinism_ok=bool(determinism_ok),
        trace_hash_1=str(trace_hash_1),
        trace_hash_2="" if trace_hash_2 is None else str(trace_hash_2),
        status=str(status),
    )


def pipeline_history_row_to_dict(row: PipelineHistoryRow) -> dict[str, str]:
    return {
        "timestamp_utc": row.timestamp_utc,
        "pipeline_profile": row.pipeline_profile,
        "play_ok": "1" if row.play_ok else "0",
        "replay_ok": "1" if row.replay_ok else "0",
        "determinism_checked": "1" if row.determinism_checked else "0",
        "determinism_ok": "1" if row.determinism_ok else "0",
        "trace_hash_1": row.trace_hash_1,
        "trace_hash_2": row.trace_hash_2,
        "status": row.status,
    }


def summarize_pipeline_history(
    rows: Iterable[dict[str, str]],
    *,
    recent_window: int = 20,
    min_recent_pass_rate: float = 0.90,
    min_determinism_pass_rate: float = 1.00,
) -> dict[str, object]:
    items = list(rows)
    total = len(items)
    recent = items[-max(1, int(recent_window)) :] if items else []

    def _is_true(v: str) -> bool:
        return str(v).strip() in {"1", "true", "True", "yes", "YES"}

    pass_total = sum(1 for r in items if str(r.get("status", "")).strip().lower() == "pass")
    pass_recent = sum(1 for r in recent if str(r.get("status", "")).strip().lower() == "pass")
    det_checked_recent = [r for r in recent if _is_true(str(r.get("determinism_checked", "0")))]
    det_ok_recent = sum(1 for r in det_checked_recent if _is_true(str(r.get("determinism_ok", "0"))))
    pass_rate_total = (pass_total / total) if total else 0.0
    pass_rate_recent = (pass_recent / len(recent)) if recent else 0.0
    determinism_pass_rate_recent = (det_ok_recent / len(det_checked_recent)) if det_checked_recent else 0.0
    if total == 0:
        status = "unknown"
        recommended_action = "collect_more_runs"
    elif pass_rate_recent < float(min_recent_pass_rate):
        status = "critical"
        recommended_action = "investigate_pipeline_failures"
    elif det_checked_recent and determinism_pass_rate_recent < float(min_determinism_pass_rate):
        status = "warning"
        recommended_action = "investigate_determinism_drift"
    else:
        status = "healthy"
        recommended_action = "continue_phase6_or_move_next_phase"
    return {
        "total_runs": total,
        "recent_window": len(recent),
        "pass_rate_total": pass_rate_total,
        "pass_rate_recent": pass_rate_recent,
        "determinism_checks_recent": len(det_checked_recent),
        "determinism_pass_rate_recent": determinism_pass_rate_recent,
        "latest_status": "" if not items else str(items[-1].get("status", "")),
        "min_recent_pass_rate": float(min_recent_pass_rate),
        "min_determinism_pass_rate": float(min_determinism_pass_rate),
        "overall_status": status,
        "recommended_action": recommended_action,
        "is_ready": status == "healthy",
    }
