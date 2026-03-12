from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class Phase22ExperimentHistoryRow:
    timestamp_utc: str
    run_name: str
    model_name: str
    baseline_model_name: str
    target_field: str
    train_split: str
    eval_split: str
    example_count: int
    top1_accuracy: float
    baseline_top1_accuracy: float
    top1_lift: float
    wins: bool
    status: str
    manifest_path: str


def build_phase22_model_manifest(
    *,
    run_name: str,
    dataset_path: str,
    model_path: str,
    eval_path: str,
    baseline_model_path: str,
    baseline_eval_path: str,
    compare_path: str,
    target_field: str,
    train_split: str,
    eval_split: str,
    model_payload: dict[str, object],
    eval_payload: dict[str, object],
    baseline_eval_payload: dict[str, object],
    compare_payload: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "phase22.manifest.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "run_name": str(run_name),
        "status": "pass",
        "model_name": str(model_payload.get("model_name", "")),
        "baseline_model_name": str(compare_payload.get("baseline_model_name", baseline_eval_payload.get("model_name", ""))),
        "target_field": str(target_field),
        "train_split": str(train_split),
        "eval_split": str(eval_split),
        "dataset_path": str(dataset_path),
        "artifacts": {
            "phase22_model": str(model_path),
            "phase22_eval": str(eval_path),
            "baseline_model": str(baseline_model_path),
            "baseline_eval": str(baseline_eval_path),
            "compare": str(compare_path),
        },
        "metrics": {
            "phase22_top1_accuracy": float(compare_payload.get("phase22_top1_accuracy", 0.0) or 0.0),
            "baseline_top1_accuracy": float(compare_payload.get("baseline_top1_accuracy", 0.0) or 0.0),
            "top1_lift": float(compare_payload.get("top1_lift", 0.0) or 0.0),
            "phase22_wins": bool(compare_payload.get("phase22_wins", False)),
            "example_count": int(eval_payload.get("example_count", 0) or 0),
            "identity_resolved_example_rate": float(eval_payload.get("identity_resolved_example_rate", 0.0) or 0.0),
            "top_k_accuracy": dict(eval_payload.get("top_k_accuracy", {}))
            if isinstance(eval_payload.get("top_k_accuracy"), dict)
            else {},
        },
        "phase22_summary": {
            "schema_version": str(model_payload.get("schema_version", "")),
            "example_count": int(model_payload.get("example_count", 0) or 0),
            "hidden_dim": int(model_payload.get("hidden_dim", 0) or 0),
            "embedding_dim": int(model_payload.get("embedding_dim", 0) or 0),
            "epochs": int(model_payload.get("epochs", 0) or 0),
            "learning_rate": float(model_payload.get("learning_rate", 0.0) or 0.0),
        },
    }


def build_phase22_experiment_history_row(
    *,
    run_name: str,
    model_name: str,
    baseline_model_name: str,
    target_field: str,
    train_split: str,
    eval_split: str,
    example_count: int,
    top1_accuracy: float,
    baseline_top1_accuracy: float,
    top1_lift: float,
    wins: bool,
    status: str,
    manifest_path: str,
) -> Phase22ExperimentHistoryRow:
    return Phase22ExperimentHistoryRow(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        run_name=str(run_name),
        model_name=str(model_name),
        baseline_model_name=str(baseline_model_name),
        target_field=str(target_field),
        train_split=str(train_split),
        eval_split=str(eval_split),
        example_count=int(example_count),
        top1_accuracy=float(top1_accuracy),
        baseline_top1_accuracy=float(baseline_top1_accuracy),
        top1_lift=float(top1_lift),
        wins=bool(wins),
        status=str(status),
        manifest_path=str(manifest_path),
    )


def phase22_experiment_history_row_to_dict(row: Phase22ExperimentHistoryRow) -> dict[str, str]:
    return {
        "timestamp_utc": row.timestamp_utc,
        "run_name": row.run_name,
        "model_name": row.model_name,
        "baseline_model_name": row.baseline_model_name,
        "target_field": row.target_field,
        "train_split": row.train_split,
        "eval_split": row.eval_split,
        "example_count": str(row.example_count),
        "top1_accuracy": str(row.top1_accuracy),
        "baseline_top1_accuracy": str(row.baseline_top1_accuracy),
        "top1_lift": str(row.top1_lift),
        "wins": str(row.wins),
        "status": row.status,
        "manifest_path": row.manifest_path,
    }


def summarize_phase22_experiment_history(rows: Iterable[dict[str, str]], *, recent_window: int = 20) -> dict[str, object]:
    items = list(rows)
    recent = items[-max(1, int(recent_window)) :] if items else []

    def _f(item: dict[str, str], key: str) -> float:
        try:
            return float(item.get(key, "0"))
        except (TypeError, ValueError):
            return 0.0

    def _b(item: dict[str, str], key: str) -> bool:
        return str(item.get(key, "")).strip().lower() == "true"

    best = max(items, key=lambda item: (_f(item, "top1_lift"), _f(item, "top1_accuracy")), default=None)
    latest = items[-1] if items else None
    recent_avg_lift = (sum(_f(item, "top1_lift") for item in recent) / len(recent)) if recent else 0.0
    recent_avg_top1 = (sum(_f(item, "top1_accuracy") for item in recent) / len(recent)) if recent else 0.0
    win_rate = (sum(1 for item in items if _b(item, "wins")) / len(items)) if items else 0.0
    pass_rate = (
        sum(1 for item in items if str(item.get("status", "")).strip().lower() == "pass") / len(items)
        if items
        else 0.0
    )
    return {
        "total_runs": len(items),
        "recent_window": len(recent),
        "recent_avg_top1_lift": recent_avg_lift,
        "recent_avg_top1_accuracy": recent_avg_top1,
        "win_rate": win_rate,
        "pass_rate": pass_rate,
        "latest_run_name": "" if latest is None else str(latest.get("run_name", "")),
        "latest_target_field": "" if latest is None else str(latest.get("target_field", "")),
        "latest_top1_accuracy": 0.0 if latest is None else _f(latest, "top1_accuracy"),
        "latest_top1_lift": 0.0 if latest is None else _f(latest, "top1_lift"),
        "best_run_name": "" if best is None else str(best.get("run_name", "")),
        "best_target_field": "" if best is None else str(best.get("target_field", "")),
        "best_top1_accuracy": 0.0 if best is None else _f(best, "top1_accuracy"),
        "best_top1_lift": 0.0 if best is None else _f(best, "top1_lift"),
    }
