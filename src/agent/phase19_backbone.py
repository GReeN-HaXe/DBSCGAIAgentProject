from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from src.agent.phase17_backbone import (
    _image_to_tensor,
    _load_state_dict,
    _prepare_examples,
    _require_torchvision,
    _select_device,
    _serialize_state_dict,
)


PHASE19_MODEL_SCHEMA_VERSION = "phase19.resnet50_classifier.v1"
PHASE19_RETRIEVAL_SCHEMA_VERSION = "phase19.resnet50_retrieval.v1"
PHASE19_COMPARE_SCHEMA_VERSION = "phase19.compare.v1"


def _build_resnet50(torchvision_mods: Any, *, label_count: int, weights_mode: str) -> tuple[Any, bool]:
    models = torchvision_mods["models"]
    mode = str(weights_mode or "default").strip().lower()
    if mode not in {"default", "none"}:
        raise ValueError("weights_mode must be 'default' or 'none'")
    if mode == "default":
        model = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
        weights_loaded = True
    else:
        model = models.resnet50(weights=None)
        weights_loaded = False
    in_features = int(model.fc.in_features)
    model.fc = torchvision_mods["nn"].Linear(in_features, int(label_count))
    return model, weights_loaded


def _build_feature_extractor(torchvision_mods: Any, model_payload: dict[str, Any], *, device: str) -> Any:
    torch = torchvision_mods["torch"]
    nn = torchvision_mods["nn"]
    models = torchvision_mods["models"]
    base = models.resnet50(weights=None)
    feature_dim = int(base.fc.in_features)
    base.fc = nn.Identity()
    state_dict = _load_state_dict(torch, dict(model_payload.get("state_dict", {})))
    filtered_state = {key: value for key, value in state_dict.items() if not key.startswith("fc.")}
    base.load_state_dict(filtered_state, strict=False)
    base.to(device)
    base.eval()
    return base, feature_dim


def train_phase19_resnet50_model(
    dataset: dict[str, Any],
    *,
    split: str = "train",
    epochs: int = 3,
    batch_size: int = 16,
    learning_rate: float = 1e-4,
    image_size: int = 96,
    max_examples: int = 0,
    weights_mode: str = "default",
    freeze_backbone_epochs: int = 0,
    seed: int = 13,
    device: str = "auto",
    progress_every: int = 1,
) -> dict[str, Any]:
    mods = _require_torchvision()
    torch = mods["torch"]
    nn = mods["nn"]
    prepared = _prepare_examples(dataset, split=split, max_examples=max_examples)
    rows = prepared["rows"]
    if not rows:
        raise ValueError(f"no training examples available for split={split!r}")
    label_vocab = prepared["label_vocab"]
    label_to_id = {label: index for index, label in enumerate(label_vocab)}
    selected_device = _select_device(torch, device)
    torch.manual_seed(int(seed))
    model, weights_loaded = _build_resnet50(mods, label_count=len(label_vocab), weights_mode=str(weights_mode))
    model = model.to(selected_device)
    freeze_epochs = max(0, int(freeze_backbone_epochs))
    if freeze_epochs > 0:
        for name, param in model.named_parameters():
            if not name.startswith("fc."):
                param.requires_grad = False
    optimizer = torch.optim.Adam(model.parameters(), lr=float(learning_rate))
    loss_fn = nn.CrossEntropyLoss()
    mean = (0.485, 0.456, 0.406)
    std = (0.229, 0.224, 0.225)

    x_train = torch.tensor(
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
    y_train = torch.tensor([label_to_id[str(row.get("signature", row.get("label", ""))).strip()] for row in rows], dtype=torch.long)
    loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(x_train, y_train),
        batch_size=max(1, int(batch_size)),
        shuffle=True,
        drop_last=(len(rows) > 1 and (len(rows) % max(1, int(batch_size))) == 1),
    )
    loss_curve: list[float] = []
    for epoch in range(max(1, int(epochs))):
        model.train()
        if freeze_epochs > 0 and epoch == freeze_epochs:
            for param in model.parameters():
                param.requires_grad = True
            optimizer = torch.optim.Adam(model.parameters(), lr=float(learning_rate))
        epoch_loss = 0.0
        batch_count = 0
        for batch_x, batch_y in loader:
            batch_x = batch_x.to(selected_device)
            batch_y = batch_y.to(selected_device)
            optimizer.zero_grad()
            logits = model(batch_x.view(batch_x.shape[0], 3, int(image_size), int(image_size)))
            loss = loss_fn(logits, batch_y)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item())
            batch_count += 1
        average_loss = epoch_loss / max(1, batch_count)
        loss_curve.append(average_loss)
        if progress_every > 0 and (((epoch + 1) % progress_every) == 0 or (epoch + 1) == int(epochs)):
            print(f"[phase19-train] epoch {epoch + 1}/{int(epochs)} loss={average_loss:.6f}")

    return {
        "schema_version": PHASE19_MODEL_SCHEMA_VERSION,
        "model_name": "phase19_resnet50_classifier",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_type": "card_identity",
        "train_split": str(split),
        "label_vocab": label_vocab,
        "epochs": int(epochs),
        "batch_size": int(batch_size),
        "learning_rate": float(learning_rate),
        "image_size": int(image_size),
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


def evaluate_phase19_resnet50_retrieval(
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
    extractor, _feature_dim = _build_feature_extractor(mods, model_payload, device=selected_device)
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
        gallery_emb = F.normalize(extractor(gallery_x.view(gallery_x.shape[0], 3, image_size, image_size)), dim=1).cpu()
        query_emb = F.normalize(extractor(query_x.view(query_x.shape[0], 3, image_size, image_size)), dim=1).cpu()

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
        "schema_version": PHASE19_RETRIEVAL_SCHEMA_VERSION,
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


def compare_phase19_vs_phase17_retrieval(*, phase19_retrieval: dict[str, Any], phase17_retrieval: dict[str, Any]) -> dict[str, Any]:
    phase19_count = int(phase19_retrieval.get("example_count", 0) or 0)
    phase17_count = int(phase17_retrieval.get("example_count", 0) or 0)
    if phase19_count != phase17_count:
        raise ValueError("example-count mismatch between phase19 and phase17 retrieval payloads")
    phase19_recall = phase19_retrieval.get("recall_at_k", {})
    phase17_recall = phase17_retrieval.get("recall_at_k", {})
    if not isinstance(phase19_recall, dict):
        phase19_recall = {}
    if not isinstance(phase17_recall, dict):
        phase17_recall = {}
    phase19_mrr = float(phase19_retrieval.get("mean_reciprocal_rank", 0.0) or 0.0)
    phase17_mrr = float(phase17_retrieval.get("mean_reciprocal_rank", 0.0) or 0.0)
    phase19_r1 = float(phase19_recall.get("1", 0.0) or 0.0)
    phase17_r1 = float(phase17_recall.get("1", 0.0) or 0.0)
    phase19_r5 = float(phase19_recall.get("5", 0.0) or 0.0)
    phase17_r5 = float(phase17_recall.get("5", 0.0) or 0.0)
    phase19_r10 = float(phase19_recall.get("10", 0.0) or 0.0)
    phase17_r10 = float(phase17_recall.get("10", 0.0) or 0.0)
    return {
        "schema_version": PHASE19_COMPARE_SCHEMA_VERSION,
        "target_type": "card_identity",
        "example_count": phase19_count,
        "phase19_model_name": str(phase19_retrieval.get("model_name", "")),
        "phase17_model_name": str(phase17_retrieval.get("model_name", "")),
        "phase19_mean_reciprocal_rank": phase19_mrr,
        "phase17_mean_reciprocal_rank": phase17_mrr,
        "phase19_recall_at_1": phase19_r1,
        "phase17_recall_at_1": phase17_r1,
        "phase19_recall_at_5": phase19_r5,
        "phase17_recall_at_5": phase17_r5,
        "phase19_recall_at_10": phase19_r10,
        "phase17_recall_at_10": phase17_r10,
        "mrr_lift": phase19_mrr - phase17_mrr,
        "recall_at_1_lift": phase19_r1 - phase17_r1,
        "recall_at_5_lift": phase19_r5 - phase17_r5,
        "recall_at_10_lift": phase19_r10 - phase17_r10,
        "phase19_wins": (
            phase19_mrr > phase17_mrr
            or phase19_r1 > phase17_r1
            or phase19_r5 > phase17_r5
            or phase19_r10 > phase17_r10
        ),
    }
