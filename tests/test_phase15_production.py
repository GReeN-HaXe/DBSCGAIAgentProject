from __future__ import annotations

from src.agent.phase15_production import (
    PHASE15_PRODUCTION_SUMMARY_SCHEMA_VERSION,
    build_phase15_production_summary,
)


def test_build_phase15_production_summary() -> None:
    summary = build_phase15_production_summary(
        phase15_manifest={
            "run_name": "phase15_triplet_8192",
            "metrics": {
                "target_type": "card_identity",
                "gallery_split": "train",
                "query_split": "validation",
                "example_count": 2025,
                "mean_reciprocal_rank": 0.999,
                "mean_found_rank": 1.001,
                "recall_at_1": 0.999,
                "recall_at_5": 1.0,
                "recall_at_10": 1.0,
                "recall_at_20": 1.0,
            },
            "training": {
                "epochs": 20,
                "steps_per_epoch": 200,
                "batch_size": 128,
                "hidden_dim": 256,
                "embedding_dim": 128,
                "learning_rate": 0.0005,
                "margin": 0.2,
                "negative_mining": "random",
                "negative_pool_size": 16,
            },
        },
        phase15_retrieval={"recall_at_k": {"1": 0.999, "5": 1.0, "10": 1.0, "20": 1.0}},
        comparison_payload={"mrr_lift": 0.01, "phase15_wins": True},
        feature_cache_path="artifacts/phase13_reference_identity_feature_cache_v3_8192.json",
    )
    assert summary["schema_version"] == PHASE15_PRODUCTION_SUMMARY_SCHEMA_VERSION
    assert summary["promoted_for_production"] is True
    assert summary["phase14_comparison"]["phase15_wins"] is True
