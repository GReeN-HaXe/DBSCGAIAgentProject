from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


@dataclass(frozen=True)
class Phase13IdentityHistoryRow:
    timestamp_utc: str
    run_name: str
    top1_accuracy: float
    top5_accuracy: float
    top10_accuracy: float
    example_count: int
    manifest_path: str


def build_phase13_identity_history_row(
    *,
    run_name: str,
    top1_accuracy: float,
    top5_accuracy: float,
    top10_accuracy: float,
    example_count: int,
    manifest_path: str,
) -> Phase13IdentityHistoryRow:
    return Phase13IdentityHistoryRow(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        run_name=str(run_name),
        top1_accuracy=float(top1_accuracy),
        top5_accuracy=float(top5_accuracy),
        top10_accuracy=float(top10_accuracy),
        example_count=int(example_count),
        manifest_path=str(manifest_path),
    )


def phase13_identity_history_row_to_dict(row: Phase13IdentityHistoryRow) -> dict[str, str]:
    return {
        "timestamp_utc": row.timestamp_utc,
        "run_name": row.run_name,
        "top1_accuracy": str(row.top1_accuracy),
        "top5_accuracy": str(row.top5_accuracy),
        "top10_accuracy": str(row.top10_accuracy),
        "example_count": str(row.example_count),
        "manifest_path": row.manifest_path,
    }


def summarize_phase13_identity_history(rows: Iterable[dict[str, str]], *, recent_window: int = 20) -> dict[str, Any]:
    items = list(rows)
    recent = items[-max(1, int(recent_window)) :] if items else []

    def _f(item: dict[str, str], key: str) -> float:
        try:
            return float(item.get(key, "0"))
        except (TypeError, ValueError):
            return 0.0

    best = max(items, key=lambda item: (_f(item, "top1_accuracy"), _f(item, "top5_accuracy"), _f(item, "top10_accuracy")), default=None)
    latest = items[-1] if items else None
    recent_avg_top1 = (sum(_f(item, "top1_accuracy") for item in recent) / len(recent)) if recent else 0.0
    return {
        "total_runs": len(items),
        "recent_window": len(recent),
        "recent_avg_top1_accuracy": recent_avg_top1,
        "latest_run_name": "" if latest is None else str(latest.get("run_name", "")),
        "latest_top1_accuracy": 0.0 if latest is None else _f(latest, "top1_accuracy"),
        "latest_top5_accuracy": 0.0 if latest is None else _f(latest, "top5_accuracy"),
        "latest_top10_accuracy": 0.0 if latest is None else _f(latest, "top10_accuracy"),
        "best_run_name": "" if best is None else str(best.get("run_name", "")),
        "best_top1_accuracy": 0.0 if best is None else _f(best, "top1_accuracy"),
        "best_top5_accuracy": 0.0 if best is None else _f(best, "top5_accuracy"),
        "best_top10_accuracy": 0.0 if best is None else _f(best, "top10_accuracy"),
    }
