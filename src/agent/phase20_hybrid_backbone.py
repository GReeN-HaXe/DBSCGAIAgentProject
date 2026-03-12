from __future__ import annotations

from datetime import datetime, timezone
import random
from typing import Any, Iterable

from src.agent.phase17_backbone import (
    _image_to_tensor,
    _load_state_dict,
    _prepare_examples,
    _require_torchvision,
    _select_device,
    _serialize_state_dict,
)


PHASE20_MODEL_SCHEMA_VERSION = "phase20.resnet18_hybrid.v1"
PHASE20_RETRIEVAL_SCHEMA_VERSION = "phase20.resnet18_hybrid_retrieval.v1"
PHASE20_COMPARE_SCHEMA_VERSION = "phase20.compare.v1"


def _build_resnet18_hybrid(mods: Any, *, label_count: int, embedding_dim: int, weights_mode: str) -> tuple[Any, bool]:
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
    classifier = nn.Linear(feature_dim, int(label_count))
    projector = nn.Linear(feature_dim, int(embedding_dim))
    model = nn.ModuleDict({"backbone": backbone, "classifier": classifier, "projector": projector})
    return model, weights_loaded


def _forward_hybrid(model: Any, batch_x: Any, *, F: Any) -> tuple[Any, Any]:
    features = model["backbone"](batch_x)
    logits = model["classifier"](features)
    embedding = F.normalize(model["projector"](features), dim=1)
    return logits, embedding


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


def train_phase20_resnet18_hybrid_model(
    dataset: dict[str, Any],
    *,
    split: str = "train",
    epochs: int = 3,
    steps_per_epoch: int = 50,
    batch_size: int = 16,
    image_size: int = 96,
    embedding_dim: int = 128,
    learning_rate: float = 1e-4,
    margin: float = 0.2,
    classification_weight: float = 1.0,
    triplet_weight: float = 1.0,
    weights_mode: str = "default",
    freeze_backbone_epochs: int = 0,
    max_examples: int = 0,
    seed: int = 13,
    device: str = "auto",
    progress_every: int = 1,
) -> dict[str, Any]:
    mods = _require_torchvision()
    torch = mods["torch"]
    nn = mods["nn"]
    F = mods["F"]
    prepared = _prepare_image_rows(dataset, split=split, max_examples=max_examples)
    rows = prepared["rows"]
    by_label = prepared["by_label"]
    if not rows:
        raise ValueError(f"no training examples available for split={split!r}")
    valid_anchor_labels = [label for label, indices in by_label.items() if len(indices) >= 2]
    if len(valid_anchor_labels) < 2:
        raise ValueError("need at least 2 labels with multiple examples for hybrid training")

    label_vocab = prepared["label_vocab"]
    label_to_id = {label: index for index, label in enumerate(label_vocab)}
    torch.manual_seed(int(seed))
    random.seed(int(seed))
    selected_device = _select_device(torch, device)
    model, weights_loaded = _build_resnet18_hybrid(
        mods,
        label_count=len(label_vocab),
        embedding_dim=int(embedding_dim),
        weights_mode=str(weights_mode),
    )
    model = model.to(selected_device)
    freeze_epochs = max(0, int(freeze_backbone_epochs))
    if freeze_epochs > 0:
        for name, param in model.named_parameters():
            if not (name.startswith("classifier.") or name.startswith("projector.")):
                param.requires_grad = False
    optimizer = torch.optim.Adam(model.parameters(), lr=float(learning_rate))
    ce_loss = nn.CrossEntropyLoss()
    triplet_loss = nn.TripletMarginLoss(margin=float(margin), p=2.0)
    mean = (0.485, 0.456, 0.406)
    std = (0.229, 0.224, 0.225)
    images_x = _tensorize_rows(rows, image_size=int(image_size), mean=mean, std=std, torch=torch)
    labels_y = torch.tensor([label_to_id[str(row.get("signature", row.get("label", ""))).strip()] for row in rows], dtype=torch.long)
    loss_curve: list[float] = []

    for epoch in range(max(1, int(epochs))):
        model.train()
        if freeze_epochs > 0 and epoch == freeze_epochs:
            for param in model.parameters():
                param.requires_grad = True
            optimizer = torch.optim.Adam(model.parameters(), lr=float(learning_rate))
        epoch_loss = 0.0
        for _ in range(max(1, int(steps_per_epoch))):
            batch_indices: list[int] = []
            anchor_idx: list[int] = []
            positive_idx: list[int] = []
            negative_idx: list[int] = []
            for _batch in range(max(1, int(batch_size))):
                anchor_label = random.choice(valid_anchor_labels)
                a_idx, p_idx = random.sample(by_label[anchor_label], 2)
                negative_label = random.choice([label for label in by_label.keys() if label != anchor_label])
                n_idx = random.choice(by_label[negative_label])
                batch_indices.append(a_idx)
                anchor_idx.append(a_idx)
                positive_idx.append(p_idx)
                negative_idx.append(n_idx)

            cls_x = images_x[batch_indices].to(selected_device).view(len(batch_indices), 3, int(image_size), int(image_size))
            cls_y = labels_y[batch_indices].to(selected_device)
            anchor_x = images_x[anchor_idx].to(selected_device).view(len(anchor_idx), 3, int(image_size), int(image_size))
            positive_x = images_x[positive_idx].to(selected_device).view(len(positive_idx), 3, int(image_size), int(image_size))
            negative_x = images_x[negative_idx].to(selected_device).view(len(negative_idx), 3, int(image_size), int(image_size))

            optimizer.zero_grad()
            logits, _cls_emb = _forward_hybrid(model, cls_x, F=F)
            _a_logits, anchor_emb = _forward_hybrid(model, anchor_x, F=F)
            _p_logits, positive_emb = _forward_hybrid(model, positive_x, F=F)
            _n_logits, negative_emb = _forward_hybrid(model, negative_x, F=F)
            loss = (float(classification_weight) * ce_loss(logits, cls_y)) + (
                float(triplet_weight) * triplet_loss(anchor_emb, positive_emb, negative_emb)
            )
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item())
        average_loss = epoch_loss / max(1, int(steps_per_epoch))
        loss_curve.append(average_loss)
        if progress_every > 0 and (((epoch + 1) % progress_every) == 0 or (epoch + 1) == int(epochs)):
            print(f"[phase20-train] epoch {epoch + 1}/{int(epochs)} loss={average_loss:.6f}")

    return {
        "schema_version": PHASE20_MODEL_SCHEMA_VERSION,
        "model_name": "phase20_resnet18_hybrid",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_type": "card_identity",
        "train_split": str(split),
        "label_vocab": label_vocab,
        "epochs": int(epochs),
        "steps_per_epoch": int(steps_per_epoch),
        "batch_size": int(batch_size),
        "image_size": int(image_size),
        "embedding_dim": int(embedding_dim),
        "learning_rate": float(learning_rate),
        "margin": float(margin),
        "classification_weight": float(classification_weight),
        "triplet_weight": float(triplet_weight),
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


def _build_model_from_payload(mods: Any, model_payload: dict[str, Any], *, device: str) -> Any:
    model, _weights_loaded = _build_resnet18_hybrid(
        mods,
        label_count=len(list(model_payload.get("label_vocab", []))),
        embedding_dim=int(model_payload.get("embedding_dim", 128) or 128),
        weights_mode=str(model_payload.get("weights_mode", "default")),
    )
    state = _load_state_dict(mods["torch"], dict(model_payload.get("state_dict", {})))
    model.load_state_dict(state, strict=True)
    model = model.to(device)
    model.eval()
    return model


def evaluate_phase20_resnet18_hybrid_retrieval(
    model_payload: dict[str, Any],
    dataset: dict[str, Any],
    *,
    gallery_split: str = "train",
    query_split: str = "validation",
    batch_size: int = 64,
    top_k_values: Iterable[int] = (1, 5, 10, 20),
    max_gallery_examples: int = 0,
    max_query_examples: int = 0,
) -> dict[str, Any]:
    mods = _require_torchvision()
    torch = mods["torch"]
    F = mods["F"]
    gallery = _prepare_examples(dataset, split=gallery_split, max_examples=max_gallery_examples)
    query = _prepare_examples(dataset, split=query_split, max_examples=max_query_examples)
    if not gallery["rows"] or not query["rows"]:
        raise ValueError("gallery/query split is empty")
    selected_device = _select_device(torch, str(model_payload.get("device", "cpu")))
    model = _build_model_from_payload(mods, model_payload, device=selected_device)
    image_size = int(model_payload.get("image_size", 96) or 96)
    mean = tuple(float(x) for x in model_payload.get("normalize_mean", [0.485, 0.456, 0.406]))
    std = tuple(float(x) for x in model_payload.get("normalize_std", [0.229, 0.224, 0.225]))

    def _tensorize(rows: list[dict[str, Any]]) -> Any:
        return torch.tensor(
            [
                _image_to_tensor(
                    str(row.get("crop_image_path", "")),
                    image_size=image_size,
                    reference_view=str(row.get("reference_view", "original")),
                    normalize_mean=mean,
                    normalize_std=std,
                )
                for row in rows
            ],
            dtype=torch.float32,
        )

    with torch.no_grad():
        gallery_x = _tensorize(gallery["rows"]).to(selected_device)
        query_x = _tensorize(query["rows"]).to(selected_device)
        _g_logits, gallery_emb = _forward_hybrid(model, gallery_x.view(gallery_x.shape[0], 3, image_size, image_size), F=F)
        _q_logits, query_emb = _forward_hybrid(model, query_x.view(query_x.shape[0], 3, image_size, image_size), F=F)
        gallery_emb = gallery_emb.cpu()
        query_emb = query_emb.cpu()

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
        "schema_version": PHASE20_RETRIEVAL_SCHEMA_VERSION,
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


def compare_phase20_vs_phase17_retrieval(*, phase20_retrieval: dict[str, Any], phase17_retrieval: dict[str, Any]) -> dict[str, Any]:
    phase20_count = int(phase20_retrieval.get("example_count", 0) or 0)
    phase17_count = int(phase17_retrieval.get("example_count", 0) or 0)
    if phase20_count != phase17_count:
        raise ValueError("example-count mismatch between phase20 and phase17 retrieval payloads")
    phase20_recall = phase20_retrieval.get("recall_at_k", {})
    phase17_recall = phase17_retrieval.get("recall_at_k", {})
    if not isinstance(phase20_recall, dict):
        phase20_recall = {}
    if not isinstance(phase17_recall, dict):
        phase17_recall = {}
    phase20_mrr = float(phase20_retrieval.get("mean_reciprocal_rank", 0.0) or 0.0)
    phase17_mrr = float(phase17_retrieval.get("mean_reciprocal_rank", 0.0) or 0.0)
    phase20_r1 = float(phase20_recall.get("1", 0.0) or 0.0)
    phase17_r1 = float(phase17_recall.get("1", 0.0) or 0.0)
    phase20_r5 = float(phase20_recall.get("5", 0.0) or 0.0)
    phase17_r5 = float(phase17_recall.get("5", 0.0) or 0.0)
    phase20_r10 = float(phase20_recall.get("10", 0.0) or 0.0)
    phase17_r10 = float(phase17_recall.get("10", 0.0) or 0.0)
    return {
        "schema_version": PHASE20_COMPARE_SCHEMA_VERSION,
        "target_type": "card_identity",
        "example_count": phase20_count,
        "phase20_model_name": str(phase20_retrieval.get("model_name", "")),
        "phase17_model_name": str(phase17_retrieval.get("model_name", "")),
        "phase20_mean_reciprocal_rank": phase20_mrr,
        "phase17_mean_reciprocal_rank": phase17_mrr,
        "phase20_recall_at_1": phase20_r1,
        "phase17_recall_at_1": phase17_r1,
        "phase20_recall_at_5": phase20_r5,
        "phase17_recall_at_5": phase17_r5,
        "phase20_recall_at_10": phase20_r10,
        "phase17_recall_at_10": phase17_r10,
        "mrr_lift": phase20_mrr - phase17_mrr,
        "recall_at_1_lift": phase20_r1 - phase17_r1,
        "recall_at_5_lift": phase20_r5 - phase17_r5,
        "recall_at_10_lift": phase20_r10 - phase17_r10,
        "phase20_wins": (
            phase20_mrr > phase17_mrr
            or phase20_r1 > phase17_r1
            or phase20_r5 > phase17_r5
            or phase20_r10 > phase17_r10
        ),
    }
