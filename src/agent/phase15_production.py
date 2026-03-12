from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


PHASE15_PRODUCTION_SUMMARY_SCHEMA_VERSION = "phase15.production_summary.v1"


def build_phase15_production_summary(
    *,
    phase15_manifest: dict[str, Any],
    phase15_retrieval: dict[str, Any],
    phase15_model: dict[str, Any] | None = None,
    comparison_payload: dict[str, Any] | None = None,
    feature_cache_path: str = "",
) -> dict[str, Any]:
    metrics = phase15_manifest.get("metrics", {})
    training = phase15_manifest.get("training", {})
    if not isinstance(metrics, dict):
        metrics = {}
    if not isinstance(training, dict):
        training = {}
    model_payload = phase15_model if isinstance(phase15_model, dict) else {}
    recall = phase15_retrieval.get("recall_at_k", {})
    if not isinstance(recall, dict):
        recall = {}
    comparison = comparison_payload if isinstance(comparison_payload, dict) else {}
    return {
        "schema_version": PHASE15_PRODUCTION_SUMMARY_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pass",
        "run_name": str(phase15_manifest.get("run_name", "")),
        "feature_cache_path": str(feature_cache_path),
        "target_type": str(metrics.get("target_type", "")),
        "gallery_split": str(metrics.get("gallery_split", "")),
        "query_split": str(metrics.get("query_split", "")),
        "example_count": int(metrics.get("example_count", 0) or 0),
        "mean_reciprocal_rank": float(metrics.get("mean_reciprocal_rank", 0.0) or 0.0),
        "mean_found_rank": float(metrics.get("mean_found_rank", 0.0) or 0.0),
        "recall_at_1": float(recall.get("1", metrics.get("recall_at_1", 0.0)) or 0.0),
        "recall_at_5": float(recall.get("5", metrics.get("recall_at_5", 0.0)) or 0.0),
        "recall_at_10": float(recall.get("10", metrics.get("recall_at_10", 0.0)) or 0.0),
        "recall_at_20": float(recall.get("20", metrics.get("recall_at_20", 0.0)) or 0.0),
        "training": {
            "epochs": int(training.get("epochs", model_payload.get("epochs", 0)) or 0),
            "steps_per_epoch": int(training.get("steps_per_epoch", model_payload.get("steps_per_epoch", 0)) or 0),
            "batch_size": int(training.get("batch_size", model_payload.get("batch_size", 0)) or 0),
            "hidden_dim": int(training.get("hidden_dim", model_payload.get("hidden_dim", 0)) or 0),
            "embedding_dim": int(training.get("embedding_dim", model_payload.get("embedding_dim", 0)) or 0),
            "learning_rate": float(training.get("learning_rate", model_payload.get("learning_rate", 0.0)) or 0.0),
            "margin": float(training.get("margin", model_payload.get("margin", 0.0)) or 0.0),
            "negative_mining": str(training.get("negative_mining", model_payload.get("negative_mining", ""))),
            "negative_pool_size": int(training.get("negative_pool_size", model_payload.get("negative_pool_size", 0)) or 0),
        },
        "phase14_comparison": comparison,
        "promoted_for_production": True,
    }
