from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import random
from typing import Any, Iterable

from src.agent.phase14_torch import _feature_keys, _filtered_examples, _require_torch, _select_device
from src.agent.phase13_visual_learning import (
    PHASE13_TARGET_CARD_IDENTITY,
    PHASE13_TARGET_OBJECT_ROLE,
    build_phase13_feature_cache,
)


PHASE15_MODEL_SCHEMA_VERSION = "phase15.triplet_mlp.v1"
PHASE15_RETRIEVAL_SCHEMA_VERSION = "phase15.retrieval_eval.v1"
PHASE15_COMPARE_SCHEMA_VERSION = "phase15.compare.v1"


def has_torch_support() -> bool:
    return importlib.util.find_spec("torch") is not None


def _normalize_feature_cache(dataset: dict[str, Any]) -> dict[str, Any]:
    examples = dataset.get("examples", [])
    if isinstance(examples, list) and examples:
        first = examples[0]
        if isinstance(first, dict) and isinstance(first.get("visual_features"), dict):
            return dataset
    return build_phase13_feature_cache(dataset)


def _target_type(dataset: dict[str, Any]) -> str:
    target_type = str(dataset.get("target_type", "")).strip().lower()
    if target_type in {PHASE13_TARGET_CARD_IDENTITY, PHASE13_TARGET_OBJECT_ROLE}:
        return target_type
    return PHASE13_TARGET_CARD_IDENTITY


def _label_field(target_type: str) -> str:
    return "signature" if target_type == PHASE13_TARGET_CARD_IDENTITY else "label"


def _prepare_rows(dataset: dict[str, Any], *, split: str) -> dict[str, Any]:
    feature_cache = _normalize_feature_cache(dataset)
    examples = _filtered_examples(feature_cache, split)
    target_type = _target_type(feature_cache)
    label_field = _label_field(target_type)
    feature_keys = _feature_keys(feature_cache, examples)
    rows: list[dict[str, Any]] = []
    for row in examples:
        features = row.get("visual_features", {})
        label_value = str(row.get(label_field, "")).strip()
        if not isinstance(features, dict) or not feature_keys or not label_value:
            continue
        rows.append(
            {
                "label": label_value,
                "features": [float(features.get(key, 0.0) or 0.0) for key in feature_keys],
                "row": row,
            }
        )
    label_vocab = sorted({str(item["label"]) for item in rows})
    return {
        "target_type": target_type,
        "label_field": label_field,
        "feature_keys": feature_keys,
        "rows": rows,
        "label_vocab": label_vocab,
    }


def _serialize_state_dict(state_dict: Any) -> dict[str, Any]:
    return {str(key): value.detach().cpu().tolist() for key, value in state_dict.items()}


def _load_state_dict(torch: Any, state_dict_payload: dict[str, Any]) -> dict[str, Any]:
    return {str(key): torch.tensor(value, dtype=torch.float32) for key, value in state_dict_payload.items()}


def _build_triplet_model(torch_mods: Any, model_payload: dict[str, Any], *, device: str) -> Any:
    nn = torch_mods["nn"]
    model = nn.Sequential(
        nn.Linear(int(model_payload.get("input_dim", 0) or 0), int(model_payload.get("hidden_dim", 256) or 256)),
        nn.ReLU(),
        nn.Linear(int(model_payload.get("hidden_dim", 256) or 256), int(model_payload.get("embedding_dim", 128) or 128)),
    ).to(device)
    model.load_state_dict(_load_state_dict(torch_mods["torch"], dict(model_payload.get("state_dict", {}))))
    model.eval()
    return model


def train_phase15_triplet_model(
    dataset: dict[str, Any],
    *,
    split: str = "train",
    epochs: int = 20,
    steps_per_epoch: int = 200,
    batch_size: int = 128,
    hidden_dim: int = 256,
    embedding_dim: int = 128,
    learning_rate: float = 5e-4,
    margin: float = 0.2,
    negative_mining: str = "random",
    negative_pool_size: int = 16,
    seed: int = 13,
    device: str = "auto",
    progress_every: int = 0,
) -> dict[str, Any]:
    torch_mods = _require_torch()
    torch = torch_mods["torch"]
    nn = torch_mods["nn"]
    F = torch_mods["F"]

    prepared = _prepare_rows(dataset, split=split)
    rows = prepared["rows"]
    if not rows:
        raise ValueError(f"no training examples available for split={split!r}")

    by_label: dict[str, list[int]] = {}
    for index, item in enumerate(rows):
        by_label.setdefault(str(item["label"]), []).append(index)
    valid_anchor_labels = [label for label, indices in by_label.items() if len(indices) >= 2]
    negative_labels = list(by_label.keys())
    if len(valid_anchor_labels) < 2:
        raise ValueError("need at least 2 labels with multiple examples for triplet training")

    random.seed(seed)
    torch.manual_seed(seed)
    selected_device = _select_device(torch, device)
    model = nn.Sequential(
        nn.Linear(len(prepared["feature_keys"]), int(hidden_dim)),
        nn.ReLU(),
        nn.Linear(int(hidden_dim), int(embedding_dim)),
    ).to(selected_device)
    optimizer = torch.optim.Adam(model.parameters(), lr=float(learning_rate))
    loss_fn = nn.TripletMarginLoss(margin=float(margin), p=2.0)
    loss_curve: list[float] = []

    negative_mining = str(negative_mining or "random").strip().lower()
    if negative_mining not in {"random", "hard"}:
        raise ValueError("negative_mining must be 'random' or 'hard'")
    pool_size = max(2, int(negative_pool_size))

    for epoch in range(max(1, int(epochs))):
        model.train()
        epoch_loss = 0.0
        for _ in range(max(1, int(steps_per_epoch))):
            anchor_batch: list[list[float]] = []
            positive_batch: list[list[float]] = []
            negative_batch: list[list[float]] = []
            hard_candidate_batches: list[list[list[float]]] = []
            for _batch_index in range(max(1, int(batch_size))):
                anchor_label = random.choice(valid_anchor_labels)
                anchor_idx, positive_idx = random.sample(by_label[anchor_label], 2)
                anchor_batch.append(rows[anchor_idx]["features"])
                positive_batch.append(rows[positive_idx]["features"])
                if negative_mining == "random":
                    negative_label = random.choice([label for label in negative_labels if label != anchor_label])
                    negative_idx = random.choice(by_label[negative_label])
                    negative_batch.append(rows[negative_idx]["features"])
                else:
                    candidate_features: list[list[float]] = []
                    for _candidate_index in range(pool_size):
                        negative_label = random.choice([label for label in negative_labels if label != anchor_label])
                        negative_idx = random.choice(by_label[negative_label])
                        candidate_features.append(rows[negative_idx]["features"])
                    hard_candidate_batches.append(candidate_features)
            anchor_x = torch.tensor(anchor_batch, dtype=torch.float32, device=selected_device)
            positive_x = torch.tensor(positive_batch, dtype=torch.float32, device=selected_device)
            if negative_mining == "hard":
                with torch.no_grad():
                    anchor_probe = F.normalize(model(anchor_x), dim=1)
                chosen_negatives: list[list[float]] = []
                for batch_index, candidate_features in enumerate(hard_candidate_batches):
                    candidate_x = torch.tensor(candidate_features, dtype=torch.float32, device=selected_device)
                    with torch.no_grad():
                        candidate_emb = F.normalize(model(candidate_x), dim=1)
                        similarities = torch.matmul(candidate_emb, anchor_probe[batch_index].unsqueeze(1)).squeeze(1)
                        hardest_index = int(torch.argmax(similarities).item())
                    chosen_negatives.append(candidate_features[hardest_index])
                negative_batch = chosen_negatives
            negative_x = torch.tensor(negative_batch, dtype=torch.float32, device=selected_device)
            optimizer.zero_grad()
            anchor_emb = F.normalize(model(anchor_x), dim=1)
            positive_emb = F.normalize(model(positive_x), dim=1)
            negative_emb = F.normalize(model(negative_x), dim=1)
            loss = loss_fn(anchor_emb, positive_emb, negative_emb)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item())
        average_loss = epoch_loss / max(1, int(steps_per_epoch))
        loss_curve.append(average_loss)
        if progress_every > 0 and (((epoch + 1) % progress_every) == 0 or (epoch + 1) == int(epochs)):
            print(f"[phase15-train] epoch {epoch + 1}/{int(epochs)} loss={average_loss:.6f}")

    return {
        "schema_version": PHASE15_MODEL_SCHEMA_VERSION,
        "model_name": "phase15_triplet_mlp",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "train_split": str(split),
        "target_type": prepared["target_type"],
        "label_field": prepared["label_field"],
        "feature_keys": prepared["feature_keys"],
        "label_vocab": prepared["label_vocab"],
        "input_dim": len(prepared["feature_keys"]),
        "hidden_dim": int(hidden_dim),
        "embedding_dim": int(embedding_dim),
        "epochs": int(epochs),
        "steps_per_epoch": int(steps_per_epoch),
        "batch_size": int(batch_size),
        "learning_rate": float(learning_rate),
        "margin": float(margin),
        "negative_mining": negative_mining,
        "negative_pool_size": pool_size,
        "seed": int(seed),
        "device": selected_device,
        "example_count": len(rows),
        "loss_curve": loss_curve,
        "state_dict": _serialize_state_dict(model.state_dict()),
    }


def evaluate_phase15_triplet_retrieval(
    model_payload: dict[str, Any],
    dataset: dict[str, Any],
    *,
    gallery_split: str = "train",
    query_split: str = "validation",
    top_k_values: Iterable[int] = (1, 5, 10, 20),
    batch_size: int = 256,
) -> dict[str, Any]:
    torch_mods = _require_torch()
    torch = torch_mods["torch"]
    F = torch_mods["F"]
    gallery = _prepare_rows(dataset, split=gallery_split)
    queries = _prepare_rows(dataset, split=query_split)
    feature_keys = [str(key) for key in model_payload.get("feature_keys", [])]
    if feature_keys != gallery["feature_keys"] or feature_keys != queries["feature_keys"]:
        raise ValueError("feature-key mismatch between model and dataset")
    if not gallery["rows"]:
        raise ValueError(f"no gallery examples available for split={gallery_split!r}")
    if not queries["rows"]:
        raise ValueError(f"no query examples available for split={query_split!r}")

    selected_device = _select_device(torch, str(model_payload.get("device", "cpu")))
    embedder = _build_triplet_model(torch_mods, model_payload, device=selected_device)
    with torch.no_grad():
        gallery_x = torch.tensor([item["features"] for item in gallery["rows"]], dtype=torch.float32).to(selected_device)
        query_x = torch.tensor([item["features"] for item in queries["rows"]], dtype=torch.float32).to(selected_device)
        gallery_emb = F.normalize(embedder(gallery_x), dim=1).cpu()
        query_emb = F.normalize(embedder(query_x), dim=1).cpu()

    ks = sorted({int(k) for k in top_k_values if int(k) > 0})
    hit_counts = {k: 0 for k in ks}
    reciprocal_rank_sum = 0.0
    exact_rank_sum = 0.0
    rows: list[dict[str, Any]] = []
    max_k = max(ks, default=1)
    for start in range(0, len(queries["rows"]), max(1, int(batch_size))):
        end = min(len(queries["rows"]), start + max(1, int(batch_size)))
        scores = torch.matmul(query_emb[start:end], gallery_emb.T)
        top_scores, top_indices = torch.topk(scores, k=min(max_k, scores.shape[1]), dim=1)
        for offset in range(end - start):
            query_row = queries["rows"][start + offset]
            expected = str(query_row["label"]).strip()
            ranked_indices = [int(value) for value in top_indices[offset].tolist()]
            ranked_labels = [str(gallery["rows"][idx]["label"]).strip() for idx in ranked_indices]
            rank: int | None = None
            for position, signature in enumerate(ranked_labels, start=1):
                if signature == expected:
                    rank = position
                    break
            if rank is not None:
                reciprocal_rank_sum += 1.0 / rank
                exact_rank_sum += float(rank)
                for k in hit_counts:
                    if rank <= k:
                        hit_counts[k] += 1
            rows.append(
                {
                    "index": start + offset,
                    "expected_signature": expected,
                    "found_rank": rank,
                    "top_predictions": [
                        {
                            "signature": ranked_labels[position],
                            "score": float(top_scores[offset][position].item()),
                        }
                        for position in range(len(ranked_labels))
                    ],
                    "crop_image_path": str(query_row["row"].get("crop_image_path", "")),
                }
            )

    total = len(rows)
    found_count = sum(1 for row in rows if row.get("found_rank") is not None)
    return {
        "schema_version": PHASE15_RETRIEVAL_SCHEMA_VERSION,
        "model_name": str(model_payload.get("model_name", "")),
        "target_type": str(queries["target_type"]),
        "gallery_split": str(gallery_split),
        "query_split": str(query_split),
        "example_count": total,
        "found_count": found_count,
        "mean_reciprocal_rank": (reciprocal_rank_sum / total) if total else 0.0,
        "mean_found_rank": (exact_rank_sum / found_count) if found_count else 0.0,
        "recall_at_k": {str(k): ((hit_counts[k] / total) if total else 0.0) for k in ks},
        "rows": rows,
    }


def compare_phase15_vs_phase14_embedding(
    *,
    phase15_retrieval: dict[str, Any],
    phase14_retrieval: dict[str, Any],
) -> dict[str, Any]:
    if str(phase15_retrieval.get("target_type", "")).strip().lower() != str(
        phase14_retrieval.get("target_type", "")
    ).strip().lower():
        raise ValueError("target-type mismatch between phase15 and phase14 retrieval payloads")
    phase15_count = int(phase15_retrieval.get("example_count", 0) or 0)
    phase14_count = int(phase14_retrieval.get("example_count", 0) or 0)
    if phase15_count != phase14_count:
        raise ValueError("example-count mismatch between phase15 and phase14 retrieval payloads")
    phase15_recall = phase15_retrieval.get("recall_at_k", {})
    phase14_recall = phase14_retrieval.get("recall_at_k", {})
    if not isinstance(phase15_recall, dict):
        phase15_recall = {}
    if not isinstance(phase14_recall, dict):
        phase14_recall = {}
    phase15_mrr = float(phase15_retrieval.get("mean_reciprocal_rank", 0.0) or 0.0)
    phase14_mrr = float(phase14_retrieval.get("mean_reciprocal_rank", 0.0) or 0.0)
    phase15_r1 = float(phase15_recall.get("1", 0.0) or 0.0)
    phase14_r1 = float(phase14_recall.get("1", 0.0) or 0.0)
    phase15_r5 = float(phase15_recall.get("5", 0.0) or 0.0)
    phase14_r5 = float(phase14_recall.get("5", 0.0) or 0.0)
    phase15_r10 = float(phase15_recall.get("10", 0.0) or 0.0)
    phase14_r10 = float(phase14_recall.get("10", 0.0) or 0.0)
    return {
        "schema_version": PHASE15_COMPARE_SCHEMA_VERSION,
        "target_type": str(phase15_retrieval.get("target_type", "")),
        "example_count": phase15_count,
        "phase15_model_name": str(phase15_retrieval.get("model_name", "")),
        "phase14_model_name": str(phase14_retrieval.get("model_name", "")),
        "phase15_mean_reciprocal_rank": phase15_mrr,
        "phase14_mean_reciprocal_rank": phase14_mrr,
        "phase15_recall_at_1": phase15_r1,
        "phase14_recall_at_1": phase14_r1,
        "phase15_recall_at_5": phase15_r5,
        "phase14_recall_at_5": phase14_r5,
        "phase15_recall_at_10": phase15_r10,
        "phase14_recall_at_10": phase14_r10,
        "mrr_lift": phase15_mrr - phase14_mrr,
        "recall_at_1_lift": phase15_r1 - phase14_r1,
        "recall_at_5_lift": phase15_r5 - phase14_r5,
        "recall_at_10_lift": phase15_r10 - phase14_r10,
        "phase15_wins": (
            phase15_mrr > phase14_mrr
            or phase15_r1 > phase14_r1
            or phase15_r5 > phase14_r5
            or phase15_r10 > phase14_r10
        ),
    }
