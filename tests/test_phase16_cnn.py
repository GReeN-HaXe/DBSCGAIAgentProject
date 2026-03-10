from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.phase13_visual_learning import build_phase13_reference_image_dataset
from src.agent.phase16_cnn import (
    PHASE16_MODEL_SCHEMA_VERSION,
    PHASE16_RETRIEVAL_SCHEMA_VERSION,
    evaluate_phase16_cnn_retrieval,
    has_torch_support,
    train_phase16_cnn_model,
)


def _reference_dataset(tmp_path: Path) -> dict[str, object]:
    images = []
    pixels = ["255 0 0", "0 255 0", "0 0 255"]
    for index, pixel in enumerate(pixels, start=1):
        path = tmp_path / f"BT1-00{index}.ppm"
        path.write_text(f"P3\n2 2\n255\n{pixel} {pixel}\n{pixel} {pixel}\n", encoding="utf-8")
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


def test_phase16_cnn_train_and_eval_or_runtime_error(tmp_path: Path) -> None:
    dataset = _reference_dataset(tmp_path)
    if not has_torch_support():
        with pytest.raises(RuntimeError, match="requirements-torch.txt"):
            train_phase16_cnn_model(dataset, epochs=1, batch_size=2, image_size=8, embedding_dim=8, max_examples=3)
        return

    model = train_phase16_cnn_model(dataset, epochs=1, batch_size=2, image_size=8, embedding_dim=8, max_examples=3)
    assert model["schema_version"] == PHASE16_MODEL_SCHEMA_VERSION
    retrieval = evaluate_phase16_cnn_retrieval(
        model,
        dataset,
        gallery_split="train",
        query_split="validation",
        batch_size=2,
        top_k_values=(1, 2),
        max_gallery_examples=3,
        max_query_examples=3,
    )
    assert retrieval["schema_version"] == PHASE16_RETRIEVAL_SCHEMA_VERSION
    assert retrieval["example_count"] == 3
