from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class Phase8ExperimentHistoryRow:
    timestamp_utc: str
    run_name: str
    model_name: str
    target_field: str
    context_mode: str
    train_split: str
    eval_split: str
    example_count: int
    top1_accuracy: float
    family_accuracy: float
    identity_resolved_example_count: int
    identity_resolved_example_rate: float
    status: str
    manifest_path: str


def build_phase8_model_manifest(
    *,
    run_name: str,
    dataset_path: str,
    model_path: str,
    eval_path: str,
    compare_path: str,
    target_field: str,
    context_mode: str,
    train_split: str,
    eval_split: str,
    model_payload: dict[str, object],
    eval_payload: dict[str, object],
    compare_payload: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "phase8.manifest.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "run_name": str(run_name),
        "status": "pass",
        "model_name": str(model_payload.get("model_name", "")),
        "target_field": str(target_field),
        "context_mode": str(context_mode),
        "train_split": str(train_split),
        "eval_split": str(eval_split),
        "dataset_path": str(dataset_path),
        "artifacts": {
            "model": str(model_path),
            "evaluation": str(eval_path),
            "comparison": str(compare_path),
        },
        "metrics": {
            "model_top1_accuracy": float(eval_payload.get("top1_accuracy", 0.0) or 0.0),
            "model_example_count": int(eval_payload.get("example_count", 0) or 0),
            "identity_resolved_example_count": int(eval_payload.get("identity_resolved_example_count", 0) or 0),
            "identity_resolved_example_rate": float(eval_payload.get("identity_resolved_example_rate", 0.0) or 0.0),
            "best_ranked_profile": (
                compare_payload.get("ranking", [{}])[0].get("profile")
                if isinstance(compare_payload.get("ranking"), list) and compare_payload.get("ranking")
                else ""
            ),
            "best_ranked_top1_accuracy": (
                float(compare_payload.get("ranking", [{}])[0].get("top1_accuracy", 0.0) or 0.0)
                if isinstance(compare_payload.get("ranking"), list) and compare_payload.get("ranking")
                else 0.0
            ),
            "promotion_passed": bool(compare_payload.get("promotion", {}).get("promoted", False))
            if isinstance(compare_payload.get("promotion"), dict)
            else False,
            "top1_lift_vs_best_heuristic": (
                float(compare_payload.get("promotion", {}).get("top1_lift_vs_best_heuristic", 0.0) or 0.0)
                if isinstance(compare_payload.get("promotion"), dict)
                else 0.0
            ),
        },
        "model_summary": {
            "schema_version": str(model_payload.get("schema_version", "")),
            "example_count": int(model_payload.get("example_count", 0) or 0),
            "context_fields": list(model_payload.get("context_fields", []))
            if isinstance(model_payload.get("context_fields"), list)
            else [],
            "global_majority_label": str(model_payload.get("global_majority_label", "")),
        },
    }


def build_phase8_experiment_history_row(
    *,
    run_name: str,
    model_name: str,
    target_field: str,
    context_mode: str,
    train_split: str,
    eval_split: str,
    example_count: int,
    top1_accuracy: float,
    family_accuracy: float,
    identity_resolved_example_count: int,
    identity_resolved_example_rate: float,
    status: str,
    manifest_path: str,
) -> Phase8ExperimentHistoryRow:
    return Phase8ExperimentHistoryRow(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        run_name=str(run_name),
        model_name=str(model_name),
        target_field=str(target_field),
        context_mode=str(context_mode),
        train_split=str(train_split),
        eval_split=str(eval_split),
        example_count=int(example_count),
        top1_accuracy=float(top1_accuracy),
        family_accuracy=float(family_accuracy),
        identity_resolved_example_count=int(identity_resolved_example_count),
        identity_resolved_example_rate=float(identity_resolved_example_rate),
        status=str(status),
        manifest_path=str(manifest_path),
    )


def phase8_experiment_history_row_to_dict(row: Phase8ExperimentHistoryRow) -> dict[str, str]:
    return {
        "timestamp_utc": row.timestamp_utc,
        "run_name": row.run_name,
        "model_name": row.model_name,
        "target_field": row.target_field,
        "context_mode": row.context_mode,
        "train_split": row.train_split,
        "eval_split": row.eval_split,
        "example_count": str(row.example_count),
        "top1_accuracy": str(row.top1_accuracy),
        "family_accuracy": str(row.family_accuracy),
        "identity_resolved_example_count": str(row.identity_resolved_example_count),
        "identity_resolved_example_rate": str(row.identity_resolved_example_rate),
        "status": row.status,
        "manifest_path": row.manifest_path,
    }


def summarize_phase8_experiment_history(rows: Iterable[dict[str, str]], *, recent_window: int = 20) -> dict[str, object]:
    items = list(rows)
    recent = items[-max(1, int(recent_window)) :] if items else []

    def _f(item: dict[str, str], key: str) -> float:
        try:
            return float(item.get(key, "0"))
        except (TypeError, ValueError):
            return 0.0

    best = max(items, key=lambda item: _f(item, "top1_accuracy"), default=None)
    latest = items[-1] if items else None
    recent_avg = (sum(_f(item, "top1_accuracy") for item in recent) / len(recent)) if recent else 0.0
    recent_identity_rate = (sum(_f(item, "identity_resolved_example_rate") for item in recent) / len(recent)) if recent else 0.0
    pass_rate = (
        sum(1 for item in items if str(item.get("status", "")).strip().lower() == "pass") / len(items)
        if items
        else 0.0
    )
    promoted_rate = (
        sum(1 for item in items if str(item.get("status", "")).strip().lower() == "pass" and _f(item, "top1_accuracy") > 0.0) / len(items)
        if items
        else 0.0
    )
    return {
        "total_runs": len(items),
        "recent_window": len(recent),
        "recent_avg_top1_accuracy": recent_avg,
        "recent_avg_identity_resolved_example_rate": recent_identity_rate,
        "pass_rate": pass_rate,
        "promoted_rate_proxy": promoted_rate,
        "latest_run_name": "" if latest is None else str(latest.get("run_name", "")),
        "latest_model_name": "" if latest is None else str(latest.get("model_name", "")),
        "latest_context_mode": "" if latest is None else str(latest.get("context_mode", "")),
        "latest_top1_accuracy": 0.0 if latest is None else _f(latest, "top1_accuracy"),
        "best_run_name": "" if best is None else str(best.get("run_name", "")),
        "best_model_name": "" if best is None else str(best.get("model_name", "")),
        "best_context_mode": "" if best is None else str(best.get("context_mode", "")),
        "best_top1_accuracy": 0.0 if best is None else _f(best, "top1_accuracy"),
    }
