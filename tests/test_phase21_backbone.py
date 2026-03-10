from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.phase13_visual_learning import build_phase13_reference_image_dataset
from src.agent.phase17_backbone import has_torchvision_support
from src.agent.phase21_backbone import (
    PHASE21_COMPARE_SCHEMA_VERSION,
    PHASE21_MODEL_SCHEMA_VERSION,
    PHASE21_RETRIEVAL_SCHEMA_VERSION,
    compare_phase21_vs_phase17_retrieval,
    evaluate_phase21_efficientnet_b0_retrieval,
    train_phase21_efficientnet_b0_model,
)


def _reference_dataset(tmp_path: Path) -> dict[str, object]:
    images = []
    pixels = ["255 0 0", "0 255 0", "0 0 255"]
    for index, pixel in enumerate(pixels, start=1):
        path = tmp_path / f"BT1-00{index}.ppm"
        path.write_text(f"P3\n4 4\n255\n{(pixel + ' ') * 4}\n{(pixel + ' ') * 4}\n{(pixel + ' ') * 4}\n{(pixel + ' ') * 4}\n", encoding="utf-8")
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
    return build_phase13_reference_image_dataset(
        manifest,
        split_mode="paired_views",
        train_views=("original",),
        validation_views=("darken",),
    )


def test_phase21_efficientnet_train_and_eval_or_runtime_error(tmp_path: Path) -> None:
    dataset = _reference_dataset(tmp_path)
    if not has_torchvision_support():
        with pytest.raises(RuntimeError, match="requirements-torch.txt"):
            train_phase21_efficientnet_b0_model(dataset, epochs=1, batch_size=2, image_size=32, max_examples=3, weights_mode="none")
        return

    model = train_phase21_efficientnet_b0_model(
        dataset,
        epochs=1,
        batch_size=2,
        image_size=64,
        max_examples=3,
        weights_mode="none",
        freeze_backbone_epochs=1,
    )
    assert model["schema_version"] == PHASE21_MODEL_SCHEMA_VERSION
    retrieval = evaluate_phase21_efficientnet_b0_retrieval(
        model,
        dataset,
        gallery_split="train",
        query_split="validation",
        batch_size=2,
        max_gallery_examples=3,
        max_query_examples=3,
    )
    assert retrieval["schema_version"] == PHASE21_RETRIEVAL_SCHEMA_VERSION
    assert retrieval["example_count"] == 3


def test_phase21_compare_helper() -> None:
    payload = compare_phase21_vs_phase17_retrieval(
        phase21_retrieval={
            "example_count": 100,
            "model_name": "phase21_efficientnet_b0_classifier",
            "mean_reciprocal_rank": 0.8,
            "recall_at_k": {"1": 0.7, "5": 0.9, "10": 0.95},
        },
        phase17_retrieval={
            "example_count": 100,
            "model_name": "phase17_resnet18_classifier",
            "mean_reciprocal_rank": 0.6,
            "recall_at_k": {"1": 0.5, "5": 0.7, "10": 0.8},
        },
    )
    assert payload["schema_version"] == PHASE21_COMPARE_SCHEMA_VERSION
    assert payload["phase21_wins"] is True
