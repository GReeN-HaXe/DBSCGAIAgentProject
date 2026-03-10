from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.phase13_visual_learning import build_phase13_feature_cache, build_phase13_reference_image_dataset
from src.agent.phase15_metric import (
    PHASE15_COMPARE_SCHEMA_VERSION,
    PHASE15_MODEL_SCHEMA_VERSION,
    PHASE15_RETRIEVAL_SCHEMA_VERSION,
    compare_phase15_vs_phase14_embedding,
    has_torch_support,
    evaluate_phase15_triplet_retrieval,
    train_phase15_triplet_model,
)


def _reference_dataset(tmp_path: Path) -> dict[str, object]:
    images = []
    pixels = ["255 0 0", "0 255 0", "0 0 255"]
    for index, pixel in enumerate(pixels, start=1):
        path = tmp_path / f"BT1-00{index}.ppm"
        path.write_text(f"P3\n1 1\n255\n{pixel}\n", encoding="utf-8")
        images.append(path)
    manifest = {
        "schema_version": "card_image_reference_manifest.v1",
        "cards": [
            {
                "card_number": f"BT1-00{index}",
                "primary_image_path": str(path),
                "card_name": f"Card {index}",
                "table_name": "cards",
                "record_id": index,
                "image_count": 1,
                "match_type": "exact_stem",
            }
            for index, path in enumerate(images, start=1)
        ],
    }
    dataset = build_phase13_reference_image_dataset(
        manifest,
        split_mode="paired_views",
        train_views=("original", "flip_h"),
        validation_views=("darken",),
    )
    return build_phase13_feature_cache(dataset)


def test_phase15_triplet_train_and_eval_or_runtime_error(tmp_path: Path) -> None:
    dataset = _reference_dataset(tmp_path)
    if not has_torch_support():
        with pytest.raises(RuntimeError, match="requirements-torch.txt"):
            train_phase15_triplet_model(dataset, epochs=1, steps_per_epoch=1, batch_size=2)
        return

    model = train_phase15_triplet_model(
        dataset,
        epochs=2,
        steps_per_epoch=4,
        batch_size=2,
        hidden_dim=8,
        embedding_dim=4,
        negative_mining="hard",
        negative_pool_size=4,
    )
    assert model["schema_version"] == PHASE15_MODEL_SCHEMA_VERSION
    assert model["negative_mining"] == "hard"
    retrieval = evaluate_phase15_triplet_retrieval(model, dataset, gallery_split="train", query_split="validation", top_k_values=(1, 2))
    assert retrieval["schema_version"] == PHASE15_RETRIEVAL_SCHEMA_VERSION
    assert retrieval["example_count"] == 3


def test_phase15_compare_helper() -> None:
    payload = compare_phase15_vs_phase14_embedding(
        phase15_retrieval={
            "target_type": "card_identity",
            "example_count": 100,
            "model_name": "phase15_triplet_mlp",
            "mean_reciprocal_rank": 0.9,
            "recall_at_k": {"1": 0.8, "5": 0.95, "10": 0.99},
        },
        phase14_retrieval={
            "target_type": "card_identity",
            "example_count": 100,
            "model_name": "phase14_torch_mlp",
            "mean_reciprocal_rank": 0.8,
            "recall_at_k": {"1": 0.7, "5": 0.9, "10": 0.95},
        },
    )
    assert payload["schema_version"] == PHASE15_COMPARE_SCHEMA_VERSION
    assert payload["phase15_wins"] is True
    assert payload["mrr_lift"] > 0.0
