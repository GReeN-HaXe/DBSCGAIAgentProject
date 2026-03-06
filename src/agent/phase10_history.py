from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class Phase10BenchmarkHistoryRow:
    timestamp_utc: str
    run_name: str
    recognizer_name: str
    frame_count: int
    object_precision: float
    object_recall: float
    frame_exact_match_rate: float
    benchmark_path: str
    status: str


def build_phase10_benchmark_history_row(
    *,
    run_name: str,
    recognizer_name: str,
    frame_count: int,
    object_precision: float,
    object_recall: float,
    frame_exact_match_rate: float,
    benchmark_path: str,
    status: str,
) -> Phase10BenchmarkHistoryRow:
    return Phase10BenchmarkHistoryRow(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        run_name=str(run_name),
        recognizer_name=str(recognizer_name),
        frame_count=int(frame_count),
        object_precision=float(object_precision),
        object_recall=float(object_recall),
        frame_exact_match_rate=float(frame_exact_match_rate),
        benchmark_path=str(benchmark_path),
        status=str(status),
    )


def phase10_benchmark_history_row_to_dict(row: Phase10BenchmarkHistoryRow) -> dict[str, str]:
    return {
        "timestamp_utc": row.timestamp_utc,
        "run_name": row.run_name,
        "recognizer_name": row.recognizer_name,
        "frame_count": str(row.frame_count),
        "object_precision": str(row.object_precision),
        "object_recall": str(row.object_recall),
        "frame_exact_match_rate": str(row.frame_exact_match_rate),
        "benchmark_path": row.benchmark_path,
        "status": row.status,
    }


def summarize_phase10_benchmark_history(rows: Iterable[dict[str, str]], *, recent_window: int = 20) -> dict[str, object]:
    items = list(rows)
    recent = items[-max(1, int(recent_window)) :] if items else []

    def _f(item: dict[str, str], key: str) -> float:
        try:
            return float(item.get(key, "0"))
        except (TypeError, ValueError):
            return 0.0

    latest = items[-1] if items else None
    best = max(items, key=lambda item: _f(item, "frame_exact_match_rate"), default=None)
    recent_precision = (sum(_f(item, "object_precision") for item in recent) / len(recent)) if recent else 0.0
    recent_recall = (sum(_f(item, "object_recall") for item in recent) / len(recent)) if recent else 0.0
    recent_exact = (sum(_f(item, "frame_exact_match_rate") for item in recent) / len(recent)) if recent else 0.0
    pass_rate = (
        sum(1 for item in items if str(item.get("status", "")).strip().lower() == "pass") / len(items)
        if items
        else 0.0
    )
    return {
        "total_runs": len(items),
        "recent_window": len(recent),
        "recent_avg_object_precision": recent_precision,
        "recent_avg_object_recall": recent_recall,
        "recent_avg_frame_exact_match_rate": recent_exact,
        "pass_rate": pass_rate,
        "latest_run_name": "" if latest is None else str(latest.get("run_name", "")),
        "latest_recognizer_name": "" if latest is None else str(latest.get("recognizer_name", "")),
        "latest_frame_exact_match_rate": 0.0 if latest is None else _f(latest, "frame_exact_match_rate"),
        "best_run_name": "" if best is None else str(best.get("run_name", "")),
        "best_recognizer_name": "" if best is None else str(best.get("recognizer_name", "")),
        "best_frame_exact_match_rate": 0.0 if best is None else _f(best, "frame_exact_match_rate"),
    }
