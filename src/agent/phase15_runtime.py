from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agent.phase13_visual_learning import extract_phase13_visual_features
from src.agent.phase15_metric import (
    _build_triplet_model,
    _prepare_rows,
    _require_torch,
)
from src.agent.phase14_torch import _select_device


PHASE15_PRODUCTION_QUERY_SCHEMA_VERSION = "phase15.production_query.v1"

DEFAULT_PHASE15_PRODUCTION_DIR = Path("artifacts/phase15_production")
DEFAULT_PHASE15_PRODUCTION_MODEL = DEFAULT_PHASE15_PRODUCTION_DIR / "phase15_triplet_model.json"
DEFAULT_PHASE15_PRODUCTION_SUMMARY = DEFAULT_PHASE15_PRODUCTION_DIR / "phase15_production_summary.json"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def resolve_phase15_production_paths(
    *,
    production_dir: Path | None = None,
    model_path: Path | None = None,
    summary_path: Path | None = None,
    feature_cache_path: Path | None = None,
) -> dict[str, Path]:
    production_root = (production_dir or DEFAULT_PHASE15_PRODUCTION_DIR).resolve()
    resolved_summary = (summary_path or (production_root / DEFAULT_PHASE15_PRODUCTION_SUMMARY.name)).resolve()
    resolved_model = (model_path or (production_root / DEFAULT_PHASE15_PRODUCTION_MODEL.name)).resolve()
    if feature_cache_path is not None:
        resolved_feature_cache = feature_cache_path.resolve()
    else:
        summary = _load_json(resolved_summary)
        feature_cache_value = str(summary.get("feature_cache_path", "")).strip()
        if not feature_cache_value:
            raise ValueError("feature_cache_path missing from phase15 production summary")
        resolved_feature_cache = Path(feature_cache_value).resolve()
    return {
        "production_dir": production_root,
        "summary": resolved_summary,
        "model": resolved_model,
        "feature_cache": resolved_feature_cache,
    }


def evaluate_phase15_production(
    *,
    production_dir: Path | None = None,
    model_path: Path | None = None,
    summary_path: Path | None = None,
    feature_cache_path: Path | None = None,
    gallery_split: str = "train",
    query_split: str = "validation",
    top_k_values: tuple[int, ...] = (1, 5, 10, 20),
    batch_size: int = 256,
) -> dict[str, Any]:
    from src.agent import evaluate_phase15_triplet_retrieval

    paths = resolve_phase15_production_paths(
        production_dir=production_dir,
        model_path=model_path,
        summary_path=summary_path,
        feature_cache_path=feature_cache_path,
    )
    return evaluate_phase15_triplet_retrieval(
        _load_json(paths["model"]),
        _load_json(paths["feature_cache"]),
        gallery_split=str(gallery_split),
        query_split=str(query_split),
        top_k_values=top_k_values,
        batch_size=int(batch_size),
    )


def query_phase15_production(
    *,
    query_index: int,
    top_k: int = 10,
    production_dir: Path | None = None,
    model_path: Path | None = None,
    summary_path: Path | None = None,
    feature_cache_path: Path | None = None,
    gallery_split: str = "train",
    query_split: str = "validation",
) -> dict[str, Any]:
    paths = resolve_phase15_production_paths(
        production_dir=production_dir,
        model_path=model_path,
        summary_path=summary_path,
        feature_cache_path=feature_cache_path,
    )
    model_payload = _load_json(paths["model"])
    dataset = _load_json(paths["feature_cache"])
    gallery = _prepare_rows(dataset, split=query_split if gallery_split == "query" else gallery_split)
    queries = _prepare_rows(dataset, split=query_split)
    if not queries["rows"]:
        raise ValueError(f"no query examples available for split={query_split!r}")
    if not gallery["rows"]:
        raise ValueError(f"no gallery examples available for split={gallery_split!r}")
    index = int(query_index)
    if index < 0 or index >= len(queries["rows"]):
        raise IndexError(f"query_index out of range: {index}")

    torch_mods = _require_torch()
    torch = torch_mods["torch"]
    F = torch_mods["F"]
    selected_device = _select_device(torch, str(model_payload.get("device", "cpu")))
    embedder = _build_triplet_model(torch_mods, model_payload, device=selected_device)
    with torch.no_grad():
        gallery_x = torch.tensor([item["features"] for item in gallery["rows"]], dtype=torch.float32).to(selected_device)
        query_x = torch.tensor([queries["rows"][index]["features"]], dtype=torch.float32).to(selected_device)
        gallery_emb = F.normalize(embedder(gallery_x), dim=1).cpu()
        query_emb = F.normalize(embedder(query_x), dim=1).cpu()
        scores = torch.matmul(query_emb, gallery_emb.T)
        top_scores, top_indices = torch.topk(scores, k=min(max(1, int(top_k)), scores.shape[1]), dim=1)

    query_row = queries["rows"][index]
    ranked_indices = [int(value) for value in top_indices[0].tolist()]
    predictions = []
    found_rank: int | None = None
    expected = str(query_row["label"]).strip()
    for position, gallery_idx in enumerate(ranked_indices, start=1):
        gallery_row = gallery["rows"][gallery_idx]
        signature = str(gallery_row["label"]).strip()
        if found_rank is None and signature == expected:
            found_rank = position
        predictions.append(
            {
                "rank": position,
                "signature": signature,
                "score": float(top_scores[0][position - 1].item()),
                "crop_image_path": str(gallery_row["row"].get("crop_image_path", "")),
            }
        )
    return {
        "schema_version": PHASE15_PRODUCTION_QUERY_SCHEMA_VERSION,
        "query_index": index,
        "gallery_split": str(gallery_split),
        "query_split": str(query_split),
        "expected_signature": expected,
        "found_rank": found_rank,
        "query_crop_image_path": str(query_row["row"].get("crop_image_path", "")),
        "predictions": predictions,
    }


def query_phase15_production_crop(
    *,
    crop_image_path: Path,
    top_k: int = 10,
    production_dir: Path | None = None,
    model_path: Path | None = None,
    summary_path: Path | None = None,
    feature_cache_path: Path | None = None,
    gallery_split: str = "train",
) -> dict[str, Any]:
    paths = resolve_phase15_production_paths(
        production_dir=production_dir,
        model_path=model_path,
        summary_path=summary_path,
        feature_cache_path=feature_cache_path,
    )
    model_payload = _load_json(paths["model"])
    dataset = _load_json(paths["feature_cache"])
    gallery = _prepare_rows(dataset, split=gallery_split)
    if not gallery["rows"]:
        raise ValueError(f"no gallery examples available for split={gallery_split!r}")
    if not crop_image_path.exists():
        raise FileNotFoundError(crop_image_path)

    feature_config = model_payload.get("feature_config")
    sample_features = extract_phase13_visual_features(crop_image_path, feature_config=feature_config)
    feature_keys = [str(key) for key in model_payload.get("feature_keys", [])]
    query_features = [float(sample_features.get(key, 0.0) or 0.0) for key in feature_keys]

    torch_mods = _require_torch()
    torch = torch_mods["torch"]
    F = torch_mods["F"]
    selected_device = _select_device(torch, str(model_payload.get("device", "cpu")))
    embedder = _build_triplet_model(torch_mods, model_payload, device=selected_device)
    with torch.no_grad():
        gallery_x = torch.tensor([item["features"] for item in gallery["rows"]], dtype=torch.float32).to(selected_device)
        query_x = torch.tensor([query_features], dtype=torch.float32).to(selected_device)
        gallery_emb = F.normalize(embedder(gallery_x), dim=1).cpu()
        query_emb = F.normalize(embedder(query_x), dim=1).cpu()
        scores = torch.matmul(query_emb, gallery_emb.T)
        top_scores, top_indices = torch.topk(scores, k=min(max(1, int(top_k)), scores.shape[1]), dim=1)

    predictions = []
    for position, gallery_idx in enumerate([int(value) for value in top_indices[0].tolist()], start=1):
        gallery_row = gallery["rows"][gallery_idx]
        predictions.append(
            {
                "rank": position,
                "signature": str(gallery_row["label"]).strip(),
                "score": float(top_scores[0][position - 1].item()),
                "crop_image_path": str(gallery_row["row"].get("crop_image_path", "")),
            }
        )
    return {
        "schema_version": PHASE15_PRODUCTION_QUERY_SCHEMA_VERSION,
        "query_crop_image_path": str(crop_image_path),
        "gallery_split": str(gallery_split),
        "predictions": predictions,
    }
