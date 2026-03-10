from __future__ import annotations

from datetime import datetime, timezone
import random
from typing import Any, Iterable

from src.agent.phase17_backbone import (
    _image_to_tensor,
    _prepare_examples,
    _require_torchvision,
    _select_device,
)


PHASE18_MODEL_SCHEMA_VERSION = "phase18.resnet18_triplet.v1"
PHASE18_RETRIEVAL_SCHEMA_VERSION = "phase18.resnet18_triplet_retrieval.v1"
PHASE18_COMPARE_SCHEMA_VERSION = "phase18.compare.v1"


def _serialize_state_dict(state_dict: Any) -> dict[str, Any]:
    return {str(key): value.detach().cpu().tolist() for key, value in state_dict.items()}


def _load_state_dict(torch: Any, state_dict_payload: dict[str, Any]) -> dict[str, Any]:
    return {str(key): torch.tensor(value, dtype=torch.float32) for key, value in state_dict_payload.items()}


def _build_resnet18_metric_model(
    mods: Any,
    *,
    embedding_dim: int,
    weights_mode: str,
) -> tuple[Any, bool]:
    nn = mods["nn"]
    models = mods["models"]
    mode = str(weights_mode or "default").strip().lower()
    if mode not in {"default", "none"}:
        raise ValueError("weights_mode must be 'default' or 'none'")
    if mode == "default":
        backbone = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
        weights_loaded = True
    else:
        backbone = models.resnet18(weights=None)
        weights_loaded = False
    feature_dim = int(backbone.fc.in_features)
    backbone.fc = nn.Identity()
    head = nn.Linear(feature_dim, int(embedding_dim))
    model = nn.ModuleDict({"backbone": backbone, "head": head})
    return model, weights_loaded


def _forward_embedding(model: Any, batch_x: Any, *, normalize: bool, F: Any) -> Any:
    embedding = model["head"](model["backbone"](batch_x))
    if normalize:
        embedding = F.normalize(embedding, dim=1)
    return embedding


def _prepare_image_rows(dataset: dict[str, Any], *, split: str, max_examples: int = 0) -> dict[str, Any]:
    prepared = _prepare_examples(dataset, split=split, max_examples=max_examples)
    rows = prepared["rows"]
    label_vocab = prepared["label_vocab"]
    by_label: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        label = str(row.get("signature", row.get("label", ""))).strip()
        if label:
            by_label.setdefault(label, []).append(index)
    return {"rows": rows, "label_vocab": label_vocab, "by_label": by_label}


def _tensorize_rows(rows: list[dict[str, Any]], *, image_size: int, mean: tuple[float, float, float], std: tuple[float, float, float], torch: Any) -> Any:
    return torch.tensor(
        [
            _image_to_tensor(
                str(row.get("crop_image_path", "")),
                image_size=int(image_size),
                reference_view=str(row.get("reference_view", "original")),
                normalize_mean=mean,
                normalize_std=std,
            )
            for row in rows
        ],
        dtype=torch.float32,
    )


def train_phase18_resnet18_triplet_model(
    dataset: dict[str, Any],
    *,
    split: str = "train",
    epochs: int = 5,
    steps_per_epoch: int = 100,
    batch_size: int = 32,
    image_size: int = 96,
    embedding_dim: int = 128,
    learning_rate: float = 1e-4,
    margin: float = 0.2,
    weights_mode: str = "default",
    freeze_backbone_epochs: int = 0,
    max_examples: int = 0,
    seed: int = 13,
    device: str = "auto",
    progress_every: int = 1,
) -> dict[str, Any]:
    mods = _require_torchvision()
    torch = mods["torch"]
    F = mods["F"]
    prepared = _prepare_image_rows(dataset, split=split, max_examples=max_examples)
    rows = prepared["rows"]
    by_label = prepared["by_label"]
    valid_anchor_labels = [label for label, indices in by_label.items() if len(indices) >= 2]
    negative_labels = [label for label in by_label if label not in set()]
    if len(valid_anchor_labels) < 2:
        raise ValueError("need at least 2 labels with multiple examples for triplet training")

    torch.manual_seed(int(seed))
    random.seed(int(seed))
    selected_device = _select_device(torch, device)
    model, weights_loaded = _build_resnet18_metric_model(mods, embedding_dim=int(embedding_dim), weights_mode=str(weights_mode))
    model = model.to(selected_device)
    freeze_epochs = max(0, int(freeze_backbone_epochs))
    if freeze_epochs > 0:
        for name, param in model.named_parameters():
            if not name.startswith("head."):
                param.requires_grad = False
    optimizer = torch.optim.Adam(model.parameters(), lr=float(learning_rate))
    loss_fn = torch.nn.TripletMarginLoss(margin=float(margin), p=2.0)
    mean = (0.485, 0.456, 0.406)
    std = (0.229, 0.224, 0.225)
    images_x = _tensorize_rows(rows, image_size=int(image_size), mean=mean, std=std, torch=torch)
    loss_curve: list[float] = []

    for epoch in range(max(1, int(epochs))):
        model.train()
        if freeze_epochs > 0 and epoch == freeze_epochs:
            for param in model.parameters():
                param.requires_grad = True
            optimizer = torch.optim.Adam(model.parameters(), lr=float(learning_rate))
        epoch_loss = 0.0
        for _ in range(max(1, int(steps_per_epoch))):
            anchor_idx: list[int] = []
            positive_idx: list[int] = []
            negative_idx: list[int] = []
            for _batch in range(max(1, int(batch_size))):
                anchor_label = random.choice(valid_anchor_labels)
                a_idx, p_idx = random.sample(by_label[anchor_label], 2)
                negative_label = random.choice([label for label in by_label.keys() if label != anchor_label])
                n_idx = random.choice(by_label[negative_label])
                anchor_idx.append(a_idx)
                positive_idx.append(p_idx)
                negative_idx.append(n_idx)
            anchor_x = images_x[anchor_idx].to(selected_device).view(len(anchor_idx), 3, int(image_size), int(image_size))
            positive_x = images_x[positive_idx].to(selected_device).view(len(positive_idx), 3, int(image_size), int(image_size))
            negative_x = images_x[negative_idx].to(selected_device).view(len(negative_idx), 3, int(image_size), int(image_size))
            optimizer.zero_grad()
            anchor_emb = _forward_embedding(model, anchor_x, normalize=True, F=F)
            positive_emb = _forward_embedding(model, positive_x, normalize=True, F=F)
            negative_emb = _forward_embedding(model, negative_x, normalize=True, F=F)
            loss = loss_fn(anchor_emb, positive_emb, negative_emb)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item())
        average_loss = epoch_loss / max(1, int(steps_per_epoch))
        loss_curve.append(average_loss)
        if progress_every > 0 and (((epoch + 1) % progress_every) == 0 or (epoch + 1) == int(epochs)):
            print(f"[phase18-train] epoch {epoch + 1}/{int(epochs)} loss={average_loss:.6f}")

    return {
        "schema_version": PHASE18_MODEL_SCHEMA_VERSION,
        "model_name": "phase18_resnet18_triplet",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_type": "card_identity",
        "train_split": str(split),
        "label_vocab": prepared["label_vocab"],
        "epochs": int(epochs),
        "steps_per_epoch": int(steps_per_epoch),
        "batch_size": int(batch_size),
        "image_size": int(image_size),
        "embedding_dim": int(embedding_dim),
        "learning_rate": float(learning_rate),
        "margin": float(margin),
        "weights_mode": str(weights_mode),
        "weights_loaded": bool(weights_loaded),
        "freeze_backbone_epochs": freeze_epochs,
        "seed": int(seed),
        "device": selected_device,
        "example_count": len(rows),
        "max_examples": int(max_examples),
        "normalize_mean": list(mean),
        "normalize_std": list(std),
        "loss_curve": loss_curve,
        "state_dict": _serialize_state_dict(model.state_dict()),
    }


def _build_metric_model_from_payload(mods: Any, model_payload: dict[str, Any], *, device: str) -> Any:
    model, _weights_loaded = _build_resnet18_metric_model(
        mods,
        embedding_dim=int(model_payload.get("embedding_dim", 128) or 128),
        weights_mode=str(model_payload.get("weights_mode", "default")),
    )
    state = _load_state_dict(mods["torch"], dict(model_payload.get("state_dict", {})))
    model.load_state_dict(state, strict=True)
    model = model.to(device)
    model.eval()
    return model


def evaluate_phase18_resnet18_triplet_retrieval(
    model_payload: dict[str, Any],
    dataset: dict[str, Any],
    *,
    gallery_split: str = "train",
    query_split: str = "validation",
    batch_size: int = 32,
    top_k_values: Iterable[int] = (1, 5, 10, 20),
    max_gallery_examples: int = 0,
    max_query_examples: int = 0,
) -> dict[str, Any]:
    mods = _require_torchvision()
    torch = mods["torch"]
    F = mods["F"]
    gallery = _prepare_image_rows(dataset, split=gallery_split, max_examples=max_gallery_examples)
    query = _prepare_image_rows(dataset, split=query_split, max_examples=max_query_examples)
    if not gallery["rows"] or not query["rows"]:
        raise ValueError("gallery/query split is empty")
    selected_device = _select_device(torch, str(model_payload.get("device", "cpu")))
    model = _build_metric_model_from_payload(mods, model_payload, device=selected_device)
    image_size = int(model_payload.get("image_size", 96) or 96)
    mean = tuple(float(x) for x in model_payload.get("normalize_mean", [0.485, 0.456, 0.406]))
    std = tuple(float(x) for x in model_payload.get("normalize_std", [0.229, 0.224, 0.225]))

    with torch.no_grad():
        gallery_x = _tensorize_rows(gallery["rows"], image_size=image_size, mean=mean, std=std, torch=torch).to(selected_device)
        query_x = _tensorize_rows(query["rows"], image_size=image_size, mean=mean, std=std, torch=torch).to(selected_device)
        gallery_emb = F.normalize(
            _forward_embedding(model, gallery_x.view(gallery_x.shape[0], 3, image_size, image_size), normalize=False, F=F),
            dim=1,
        ).cpu()
        query_emb = F.normalize(
            _forward_embedding(model, query_x.view(query_x.shape[0], 3, image_size, image_size), normalize=False, F=F),
            dim=1,
        ).cpu()

    ks = sorted({int(k) for k in top_k_values if int(k) > 0})
    hit_counts = {k: 0 for k in ks}
    reciprocal_rank_sum = 0.0
    exact_rank_sum = 0.0
    rows: list[dict[str, Any]] = []
    max_k = max(ks, default=1)
    for start in range(0, len(query["rows"]), max(1, int(batch_size))):
        end = min(len(query["rows"]), start + max(1, int(batch_size)))
        scores = torch.matmul(query_emb[start:end], gallery_emb.T)
        top_scores, top_indices = torch.topk(scores, k=min(max_k, scores.shape[1]), dim=1)
        for offset in range(end - start):
            query_row = query["rows"][start + offset]
            expected = str(query_row.get("signature", query_row.get("label", ""))).strip()
            ranked_indices = [int(value) for value in top_indices[offset].tolist()]
            ranked_labels = [str(gallery["rows"][idx].get("signature", gallery["rows"][idx].get("label", ""))).strip() for idx in ranked_indices]
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
                        {"signature": ranked_labels[pos], "score": float(top_scores[offset][pos].item())}
                        for pos in range(len(ranked_labels))
                    ],
                    "crop_image_path": str(query_row.get("crop_image_path", "")),
                }
            )
    total = len(rows)
    found_count = sum(1 for row in rows if row.get("found_rank") is not None)
    return {
        "schema_version": PHASE18_RETRIEVAL_SCHEMA_VERSION,
        "model_name": str(model_payload.get("model_name", "")),
        "target_type": "card_identity",
        "gallery_split": str(gallery_split),
        "query_split": str(query_split),
        "example_count": total,
        "found_count": found_count,
        "mean_reciprocal_rank": (reciprocal_rank_sum / total) if total else 0.0,
        "mean_found_rank": (exact_rank_sum / found_count) if found_count else 0.0,
        "recall_at_k": {str(k): ((hit_counts[k] / total) if total else 0.0) for k in ks},
        "rows": rows,
    }


def compare_phase18_vs_phase17_retrieval(*, phase18_retrieval: dict[str, Any], phase17_retrieval: dict[str, Any]) -> dict[str, Any]:
    phase18_count = int(phase18_retrieval.get("example_count", 0) or 0)
    phase17_count = int(phase17_retrieval.get("example_count", 0) or 0)
    if phase18_count != phase17_count:
        raise ValueError("example-count mismatch between phase18 and phase17 retrieval payloads")
    phase18_recall = phase18_retrieval.get("recall_at_k", {})
    phase17_recall = phase17_retrieval.get("recall_at_k", {})
    if not isinstance(phase18_recall, dict):
        phase18_recall = {}
    if not isinstance(phase17_recall, dict):
        phase17_recall = {}
    phase18_mrr = float(phase18_retrieval.get("mean_reciprocal_rank", 0.0) or 0.0)
    phase17_mrr = float(phase17_retrieval.get("mean_reciprocal_rank", 0.0) or 0.0)
    phase18_r1 = float(phase18_recall.get("1", 0.0) or 0.0)
    phase17_r1 = float(phase17_recall.get("1", 0.0) or 0.0)
    phase18_r5 = float(phase18_recall.get("5", 0.0) or 0.0)
    phase17_r5 = float(phase17_recall.get("5", 0.0) or 0.0)
    phase18_r10 = float(phase18_recall.get("10", 0.0) or 0.0)
    phase17_r10 = float(phase17_recall.get("10", 0.0) or 0.0)
    return {
        "schema_version": PHASE18_COMPARE_SCHEMA_VERSION,
        "target_type": "card_identity",
        "example_count": phase18_count,
        "phase18_model_name": str(phase18_retrieval.get("model_name", "")),
        "phase17_model_name": str(phase17_retrieval.get("model_name", "")),
        "phase18_mean_reciprocal_rank": phase18_mrr,
        "phase17_mean_reciprocal_rank": phase17_mrr,
        "phase18_recall_at_1": phase18_r1,
        "phase17_recall_at_1": phase17_r1,
        "phase18_recall_at_5": phase18_r5,
        "phase17_recall_at_5": phase17_r5,
        "phase18_recall_at_10": phase18_r10,
        "phase17_recall_at_10": phase17_r10,
        "mrr_lift": phase18_mrr - phase17_mrr,
        "recall_at_1_lift": phase18_r1 - phase17_r1,
        "recall_at_5_lift": phase18_r5 - phase17_r5,
        "recall_at_10_lift": phase18_r10 - phase17_r10,
        "phase18_wins": (
            phase18_mrr > phase17_mrr
            or phase18_r1 > phase17_r1
            or phase18_r5 > phase17_r5
            or phase18_r10 > phase17_r10
        ),
    }
