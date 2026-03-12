from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import random
from typing import Any, Iterable

from PIL import Image, ImageEnhance, ImageOps


PHASE16_MODEL_SCHEMA_VERSION = "phase16.cnn_classifier.v1"
PHASE16_EVAL_SCHEMA_VERSION = "phase16.cnn_eval.v1"
PHASE16_RETRIEVAL_SCHEMA_VERSION = "phase16.cnn_retrieval.v1"


def has_torch_support() -> bool:
    return importlib.util.find_spec("torch") is not None


def _require_torch() -> Any:
    if not has_torch_support():
        raise RuntimeError("PyTorch is not installed. Install requirements-torch.txt, then rerun.")
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import torch.utils.data as torch_data

    return {"torch": torch, "nn": nn, "F": F, "torch_data": torch_data}


def _apply_reference_view_pil(image: Image.Image, reference_view: str) -> Image.Image:
    view = str(reference_view or "original").strip().lower()
    if view == "original":
        return image
    if view == "flip_h":
        return ImageOps.mirror(image)
    if view == "brighten":
        return ImageEnhance.Brightness(image).enhance(1.15)
    if view == "darken":
        return ImageEnhance.Brightness(image).enhance(0.85)
    return image


def _load_image_tensor(path: str, *, image_size: int, reference_view: str) -> list[float]:
    image = Image.open(path).convert("RGB")
    image = _apply_reference_view_pil(image, reference_view)
    image = image.resize((int(image_size), int(image_size)))
    pixels = list(image.getdata())
    values: list[float] = []
    for r, g, b in pixels:
        values.extend([r / 255.0, g / 255.0, b / 255.0])
    return values


def _prepare_reference_examples(dataset: dict[str, Any], *, split: str, max_examples: int = 0) -> dict[str, Any]:
    examples = dataset.get("examples", [])
    if not isinstance(examples, list):
        examples = []
    rows: list[dict[str, Any]] = []
    for row in examples:
        if not isinstance(row, dict):
            continue
        if split != "all" and str(row.get("split", "")) != split:
            continue
        label = str(row.get("signature", row.get("label", ""))).strip()
        image_path = str(row.get("crop_image_path", "")).strip()
        if not label or not image_path:
            continue
        rows.append(row)
    if max_examples > 0:
        rows = rows[: int(max_examples)]
    label_vocab = sorted({str(row.get("signature", row.get("label", ""))).strip() for row in rows})
    return {"rows": rows, "label_vocab": label_vocab}


def _serialize_state_dict(state_dict: Any) -> dict[str, Any]:
    return {str(key): value.detach().cpu().tolist() for key, value in state_dict.items()}


def _load_state_dict(torch: Any, state_dict_payload: dict[str, Any]) -> dict[str, Any]:
    return {str(key): torch.tensor(value, dtype=torch.float32) for key, value in state_dict_payload.items()}


def _select_device(torch: Any, requested: str) -> str:
    requested = str(requested or "auto").strip().lower()
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        return "cpu"
    return requested


def _build_cnn(torch_mods: Any, *, image_size: int, embedding_dim: int, label_count: int) -> Any:
    nn = torch_mods["nn"]
    pooled = max(1, int(image_size) // 4)
    flattened = 32 * pooled * pooled
    return nn.Sequential(
        nn.Unflatten(1, (3, int(image_size), int(image_size))),
        nn.Conv2d(3, 16, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(16, 32, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Flatten(),
        nn.Linear(flattened, int(embedding_dim)),
        nn.ReLU(),
        nn.Linear(int(embedding_dim), int(label_count)),
    )


def _build_embedding_model(torch_mods: Any, model_payload: dict[str, Any], *, device: str) -> Any:
    nn = torch_mods["nn"]
    image_size = int(model_payload.get("image_size", 32) or 32)
    embedding_dim = int(model_payload.get("embedding_dim", 128) or 128)
    pooled = max(1, image_size // 4)
    flattened = 32 * pooled * pooled
    model = nn.Sequential(
        nn.Unflatten(1, (3, image_size, image_size)),
        nn.Conv2d(3, 16, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(16, 32, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Flatten(),
        nn.Linear(flattened, embedding_dim),
        nn.ReLU(),
    ).to(device)
    full_state = _load_state_dict(torch_mods["torch"], dict(model_payload.get("state_dict", {})))
    embedding_state = {key: value for key, value in full_state.items() if not key.startswith("10.")}
    model.load_state_dict(embedding_state)
    model.eval()
    return model


def train_phase16_cnn_model(
    dataset: dict[str, Any],
    *,
    split: str = "train",
    epochs: int = 10,
    batch_size: int = 32,
    learning_rate: float = 1e-3,
    image_size: int = 32,
    embedding_dim: int = 128,
    max_examples: int = 0,
    seed: int = 13,
    device: str = "auto",
    progress_every: int = 0,
) -> dict[str, Any]:
    torch_mods = _require_torch()
    torch = torch_mods["torch"]
    torch_data = torch_mods["torch_data"]
    nn = torch_mods["nn"]

    prepared = _prepare_reference_examples(dataset, split=split, max_examples=max_examples)
    rows = prepared["rows"]
    if not rows:
        raise ValueError(f"no training examples available for split={split!r}")
    label_vocab = prepared["label_vocab"]
    label_to_id = {label: index for index, label in enumerate(label_vocab)}

    random.seed(seed)
    torch.manual_seed(seed)
    selected_device = _select_device(torch, device)
    x_train = torch.tensor(
        [
            _load_image_tensor(
                str(row.get("crop_image_path", "")),
                image_size=int(image_size),
                reference_view=str(row.get("reference_view", "original")),
            )
            for row in rows
        ],
        dtype=torch.float32,
    )
    y_train = torch.tensor([label_to_id[str(row.get("signature", row.get("label", ""))).strip()] for row in rows], dtype=torch.long)
    loader = torch_data.DataLoader(torch_data.TensorDataset(x_train, y_train), batch_size=max(1, int(batch_size)), shuffle=True)

    model = _build_cnn(torch_mods, image_size=int(image_size), embedding_dim=int(embedding_dim), label_count=len(label_vocab)).to(
        selected_device
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=float(learning_rate))
    loss_fn = nn.CrossEntropyLoss()
    loss_curve: list[float] = []

    for epoch in range(max(1, int(epochs))):
        model.train()
        epoch_loss = 0.0
        batch_count = 0
        for batch_x, batch_y in loader:
            batch_x = batch_x.to(selected_device)
            batch_y = batch_y.to(selected_device)
            optimizer.zero_grad()
            logits = model(batch_x)
            loss = loss_fn(logits, batch_y)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item())
            batch_count += 1
        average_loss = epoch_loss / max(1, batch_count)
        loss_curve.append(average_loss)
        if progress_every > 0 and (((epoch + 1) % progress_every) == 0 or (epoch + 1) == int(epochs)):
            print(f"[phase16-train] epoch {epoch + 1}/{int(epochs)} loss={average_loss:.6f}")

    return {
        "schema_version": PHASE16_MODEL_SCHEMA_VERSION,
        "model_name": "phase16_cnn_classifier",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_type": "card_identity",
        "train_split": str(split),
        "image_size": int(image_size),
        "embedding_dim": int(embedding_dim),
        "input_dim": 3 * int(image_size) * int(image_size),
        "label_vocab": label_vocab,
        "epochs": int(epochs),
        "batch_size": int(batch_size),
        "learning_rate": float(learning_rate),
        "seed": int(seed),
        "device": selected_device,
        "example_count": len(rows),
        "max_examples": int(max_examples),
        "loss_curve": loss_curve,
        "state_dict": _serialize_state_dict(model.state_dict()),
    }


def evaluate_phase16_cnn_retrieval(
    model_payload: dict[str, Any],
    dataset: dict[str, Any],
    *,
    gallery_split: str = "train",
    query_split: str = "validation",
    batch_size: int = 128,
    top_k_values: Iterable[int] = (1, 5, 10, 20),
    max_gallery_examples: int = 0,
    max_query_examples: int = 0,
) -> dict[str, Any]:
    torch_mods = _require_torch()
    torch = torch_mods["torch"]
    F = torch_mods["F"]
    image_size = int(model_payload.get("image_size", 32) or 32)
    gallery = _prepare_reference_examples(dataset, split=gallery_split, max_examples=max_gallery_examples)
    query = _prepare_reference_examples(dataset, split=query_split, max_examples=max_query_examples)
    if not gallery["rows"] or not query["rows"]:
        raise ValueError("gallery/query split is empty")
    selected_device = _select_device(torch, str(model_payload.get("device", "cpu")))
    embedder = _build_embedding_model(torch_mods, model_payload, device=selected_device)

    def _tensorize(rows: list[dict[str, Any]]) -> Any:
        return torch.tensor(
            [
                _load_image_tensor(
                    str(row.get("crop_image_path", "")),
                    image_size=image_size,
                    reference_view=str(row.get("reference_view", "original")),
                )
                for row in rows
            ],
            dtype=torch.float32,
        )

    with torch.no_grad():
        gallery_x = _tensorize(gallery["rows"]).to(selected_device)
        query_x = _tensorize(query["rows"]).to(selected_device)
        gallery_emb = F.normalize(embedder(gallery_x), dim=1).cpu()
        query_emb = F.normalize(embedder(query_x), dim=1).cpu()

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
        "schema_version": PHASE16_RETRIEVAL_SCHEMA_VERSION,
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
