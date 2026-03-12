from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class Phase7EvalHistoryRow:
    timestamp_utc: str
    evaluator_name: str
    split: str
    target_field: str
    example_count: int
    top1_accuracy: float
    family_accuracy: float
    identity_resolved_example_count: int
    identity_resolved_example_rate: float


def build_phase7_eval_history_row(
    *,
    evaluator_name: str,
    split: str,
    target_field: str,
    example_count: int,
    top1_accuracy: float,
    family_accuracy: float = 0.0,
    identity_resolved_example_count: int = 0,
    identity_resolved_example_rate: float = 0.0,
) -> Phase7EvalHistoryRow:
    return Phase7EvalHistoryRow(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        evaluator_name=str(evaluator_name),
        split=str(split),
        target_field=str(target_field),
        example_count=int(example_count),
        top1_accuracy=float(top1_accuracy),
        family_accuracy=float(family_accuracy),
        identity_resolved_example_count=int(identity_resolved_example_count),
        identity_resolved_example_rate=float(identity_resolved_example_rate),
    )


def phase7_eval_history_row_to_dict(row: Phase7EvalHistoryRow) -> dict[str, str]:
    return {
        "timestamp_utc": row.timestamp_utc,
        "evaluator_name": row.evaluator_name,
        "split": row.split,
        "target_field": row.target_field,
        "example_count": str(row.example_count),
        "top1_accuracy": str(row.top1_accuracy),
        "family_accuracy": str(row.family_accuracy),
        "identity_resolved_example_count": str(row.identity_resolved_example_count),
        "identity_resolved_example_rate": str(row.identity_resolved_example_rate),
    }


def summarize_phase7_eval_history(rows: Iterable[dict[str, str]], *, recent_window: int = 20) -> dict[str, object]:
    items = list(rows)
    recent = items[-max(1, int(recent_window)) :] if items else []

    def _f(row: dict[str, str], key: str) -> float:
        try:
            return float(row.get(key, "0"))
        except (TypeError, ValueError):
            return 0.0

    latest = items[-1] if items else {}
    latest_top1 = _f(latest, "top1_accuracy")
    baseline_top1 = _f(items[0], "top1_accuracy") if items else 0.0
    recent_avg_top1 = (sum(_f(row, "top1_accuracy") for row in recent) / len(recent)) if recent else 0.0
    best_top1 = max((_f(row, "top1_accuracy") for row in items), default=0.0)
    latest_identity_rate = _f(latest, "identity_resolved_example_rate")
    recent_avg_identity_rate = (sum(_f(row, "identity_resolved_example_rate") for row in recent) / len(recent)) if recent else 0.0
    improving = latest_top1 >= baseline_top1 if items else False
    return {
        "total_runs": len(items),
        "recent_window": len(recent),
        "latest_evaluator_name": str(latest.get("evaluator_name", "")),
        "latest_split": str(latest.get("split", "")),
        "latest_target_field": str(latest.get("target_field", "")),
        "latest_top1_accuracy": latest_top1,
        "baseline_top1_accuracy": baseline_top1,
        "recent_avg_top1_accuracy": recent_avg_top1,
        "best_top1_accuracy": best_top1,
        "latest_identity_resolved_example_rate": latest_identity_rate,
        "recent_avg_identity_resolved_example_rate": recent_avg_identity_rate,
        "improving_vs_baseline": improving,
    }
