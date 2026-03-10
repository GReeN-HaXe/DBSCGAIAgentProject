from __future__ import annotations

import json
from pathlib import Path

from src.agent.phase13_visual_learning import build_phase13_feature_cache, build_phase13_reference_image_dataset
from src.agent.phase15_metric import train_phase15_triplet_model, evaluate_phase15_triplet_retrieval, has_torch_support
from src.agent.phase15_runtime import (
    PHASE15_PRODUCTION_QUERY_SCHEMA_VERSION,
    evaluate_phase15_production,
    query_phase15_production,
)


def _build_production_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
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
    dataset = build_phase13_feature_cache(
        build_phase13_reference_image_dataset(
            manifest,
            split_mode="paired_views",
            train_views=("original", "flip_h"),
            validation_views=("darken",),
        )
    )
    if not has_torch_support():
        raise RuntimeError("torch required for phase15 runtime test")
    model = train_phase15_triplet_model(dataset, epochs=1, steps_per_epoch=2, batch_size=2, hidden_dim=8, embedding_dim=4)
    retrieval = evaluate_phase15_triplet_retrieval(model, dataset, gallery_split="train", query_split="validation", top_k_values=(1, 2))
    production_dir = tmp_path / "phase15_production"
    production_dir.mkdir(parents=True, exist_ok=True)
    model_path = production_dir / "phase15_triplet_model.json"
    summary_path = production_dir / "phase15_production_summary.json"
    feature_cache_path = tmp_path / "feature_cache.json"
    model_path.write_text(json.dumps(model, indent=2), encoding="utf-8")
    feature_cache_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    summary_path.write_text(
        json.dumps({"feature_cache_path": str(feature_cache_path)}, indent=2),
        encoding="utf-8",
    )
    _ = retrieval
    return production_dir, model_path, feature_cache_path


def test_phase15_runtime_eval_and_query(tmp_path: Path) -> None:
    if not has_torch_support():
        return
    production_dir, _model_path, _feature_cache_path = _build_production_fixture(tmp_path)
    payload = evaluate_phase15_production(production_dir=production_dir, gallery_split="train", query_split="validation", top_k_values=(1, 2))
    assert payload["example_count"] == 3
    query_payload = query_phase15_production(production_dir=production_dir, query_index=0, top_k=2)
    assert query_payload["schema_version"] == PHASE15_PRODUCTION_QUERY_SCHEMA_VERSION
    assert len(query_payload["predictions"]) == 2
