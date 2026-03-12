from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.util
import random
from typing import Any, Iterable

from src.agent.phase13_visual_learning import (
    PHASE13_TARGET_CARD_IDENTITY,
    PHASE13_TARGET_OBJECT_ROLE,
    build_phase13_feature_cache,
)


PHASE14_MODEL_SCHEMA_VERSION = "phase14.torch_mlp.v1"
PHASE14_EVAL_SCHEMA_VERSION = "phase14.torch_eval.v1"
PHASE14_IDENTITY_HISTORY_SCHEMA_VERSION = "phase14.identity_history.v1"
PHASE14_COMPARE_SCHEMA_VERSION = "phase14.compare.v1"
PHASE14_COMPARE_HISTORY_SCHEMA_VERSION = "phase14.compare_history.v1"
PHASE14_RETRIEVAL_SCHEMA_VERSION = "phase14.retrieval_eval.v1"
PHASE14_EMBEDDING_RETRIEVAL_SCHEMA_VERSION = "phase14.embedding_retrieval.v1"
PHASE14_ERROR_ANALYSIS_SCHEMA_VERSION = "phase14.error_analysis.v1"
PHASE14_RETRIEVAL_COMPARISON_SCHEMA_VERSION = "phase14.retrieval_comparison.v1"
PHASE14_EMBEDDING_HISTORY_SCHEMA_VERSION = "phase14.embedding_history.v1"
PHASE14_EMBEDDING_COMPARE_SCHEMA_VERSION = "phase14.embedding_compare.v1"
PHASE14_EMBEDDING_ANALYSIS_SCHEMA_VERSION = "phase14.embedding_analysis.v1"


def has_torch_support() -> bool:
    return importlib.util.find_spec("torch") is not None


def _require_torch() -> Any:
    if not has_torch_support():
        raise RuntimeError(
            "PyTorch is not installed. Install the dependencies in requirements-torch.txt, then rerun."
        )
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import torch.utils.data as torch_data

    return {
        "torch": torch,
        "nn": nn,
        "F": F,
        "torch_data": torch_data,
    }


def _normalize_feature_cache(dataset: dict[str, Any]) -> dict[str, Any]:
    examples = dataset.get("examples", [])
    if isinstance(examples, list) and examples:
        first = examples[0]
        if isinstance(first, dict) and isinstance(first.get("visual_features"), dict):
            return dataset
    return build_phase13_feature_cache(dataset)


def _filtered_examples(dataset: dict[str, Any], split: str) -> list[dict[str, Any]]:
    examples = dataset.get("examples", [])
    if not isinstance(examples, list):
        return []
    return [row for row in examples if isinstance(row, dict) and (split == "all" or row.get("split") == split)]


def _feature_keys(dataset: dict[str, Any], examples: list[dict[str, Any]]) -> list[str]:
    keys = dataset.get("feature_keys", [])
    if isinstance(keys, list) and keys:
        return [str(key) for key in keys]
    found: set[str] = set()
    for row in examples:
        features = row.get("visual_features", {})
        if isinstance(features, dict):
            found.update(str(key) for key in features.keys())
    return sorted(found)


def _target_type(dataset: dict[str, Any]) -> str:
    target_type = str(dataset.get("target_type", "")).strip().lower()
    if target_type in {PHASE13_TARGET_CARD_IDENTITY, PHASE13_TARGET_OBJECT_ROLE}:
        return target_type
    return PHASE13_TARGET_CARD_IDENTITY


def _label_field(target_type: str) -> str:
    return "signature" if target_type == PHASE13_TARGET_CARD_IDENTITY else "label"


@dataclass
class _PreparedRows:
    feature_keys: list[str]
    label_vocab: list[str]
    feature_rows: list[list[float]]
    label_ids: list[int]
    raw_rows: list[dict[str, Any]]
    target_type: str
    label_field: str


def _prepare_rows(dataset: dict[str, Any], *, split: str) -> _PreparedRows:
    feature_cache = _normalize_feature_cache(dataset)
    examples = _filtered_examples(feature_cache, split)
    target_type = _target_type(feature_cache)
    label_field = _label_field(target_type)
    feature_keys = _feature_keys(feature_cache, examples)
    label_values: list[str] = []
    feature_rows: list[list[float]] = []
    raw_rows: list[dict[str, Any]] = []
    for row in examples:
        features = row.get("visual_features", {})
        label_value = str(row.get(label_field, "")).strip()
        if not isinstance(features, dict) or not feature_keys or not label_value:
            continue
        feature_rows.append([float(features.get(key, 0.0) or 0.0) for key in feature_keys])
        label_values.append(label_value)
        raw_rows.append(row)
    label_vocab = sorted(set(label_values))
    label_to_id = {label: index for index, label in enumerate(label_vocab)}
    label_ids = [label_to_id[label] for label in label_values]
    return _PreparedRows(
        feature_keys=feature_keys,
        label_vocab=label_vocab,
        feature_rows=feature_rows,
        label_ids=label_ids,
        raw_rows=raw_rows,
        target_type=target_type,
        label_field=label_field,
    )


def _select_device(torch: Any, requested: str) -> str:
    requested = str(requested or "auto").strip().lower()
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        return "cpu"
    return requested


def _serialize_state_dict(state_dict: Any) -> dict[str, Any]:
    return {str(key): value.detach().cpu().tolist() for key, value in state_dict.items()}


def _load_state_dict(torch: Any, state_dict_payload: dict[str, Any]) -> dict[str, Any]:
    return {str(key): torch.tensor(value, dtype=torch.float32) for key, value in state_dict_payload.items()}


def train_phase14_torch_model(
    dataset: dict[str, Any],
    *,
    split: str = "train",
    epochs: int = 20,
    batch_size: int = 64,
    hidden_dim: int = 128,
    learning_rate: float = 1e-3,
    seed: int = 13,
    device: str = "auto",
    progress_every: int = 0,
) -> dict[str, Any]:
    torch_mods = _require_torch()
    torch = torch_mods["torch"]
    nn = torch_mods["nn"]
    torch_data = torch_mods["torch_data"]

    prepared = _prepare_rows(dataset, split=split)
    if not prepared.feature_rows:
        raise ValueError(f"no training examples available for split={split!r}")
    if len(prepared.label_vocab) < 2:
        raise ValueError("need at least 2 classes to train a Phase 14 torch model")

    random.seed(seed)
    torch.manual_seed(seed)
    selected_device = _select_device(torch, device)
    x_train = torch.tensor(prepared.feature_rows, dtype=torch.float32)
    y_train = torch.tensor(prepared.label_ids, dtype=torch.long)
    loader = torch_data.DataLoader(
        torch_data.TensorDataset(x_train, y_train),
        batch_size=max(1, int(batch_size)),
        shuffle=True,
    )

    model = nn.Sequential(
        nn.Linear(len(prepared.feature_keys), int(hidden_dim)),
        nn.ReLU(),
        nn.Linear(int(hidden_dim), len(prepared.label_vocab)),
    ).to(selected_device)
    optimizer = torch.optim.Adam(model.parameters(), lr=float(learning_rate))
    loss_fn = nn.CrossEntropyLoss()
    losses: list[float] = []

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
        losses.append(average_loss)
        if progress_every > 0 and (((epoch + 1) % progress_every) == 0 or (epoch + 1) == int(epochs)):
            print(f"[phase14-train] epoch {epoch + 1}/{int(epochs)} loss={average_loss:.6f}")

    return {
        "schema_version": PHASE14_MODEL_SCHEMA_VERSION,
        "model_name": "phase14_torch_mlp",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "train_split": str(split),
        "target_type": prepared.target_type,
        "label_field": prepared.label_field,
        "feature_keys": prepared.feature_keys,
        "label_vocab": prepared.label_vocab,
        "input_dim": len(prepared.feature_keys),
        "output_dim": len(prepared.label_vocab),
        "hidden_dim": int(hidden_dim),
        "epochs": int(epochs),
        "batch_size": int(batch_size),
        "learning_rate": float(learning_rate),
        "seed": int(seed),
        "device": selected_device,
        "example_count": len(prepared.feature_rows),
        "loss_curve": losses,
        "state_dict": _serialize_state_dict(model.state_dict()),
    }


def _build_torch_model(torch_mods: Any, model_payload: dict[str, Any], *, device: str) -> Any:
    nn = torch_mods["nn"]
    model = nn.Sequential(
        nn.Linear(int(model_payload.get("input_dim", 0) or 0), int(model_payload.get("hidden_dim", 128) or 128)),
        nn.ReLU(),
        nn.Linear(int(model_payload.get("hidden_dim", 128) or 128), int(model_payload.get("output_dim", 0) or 0)),
    ).to(device)
    model.load_state_dict(_load_state_dict(torch_mods["torch"], dict(model_payload.get("state_dict", {}))))
    model.eval()
    return model


def _build_embedding_model(torch_mods: Any, model_payload: dict[str, Any], *, device: str) -> Any:
    nn = torch_mods["nn"]
    model = nn.Sequential(
        nn.Linear(int(model_payload.get("input_dim", 0) or 0), int(model_payload.get("hidden_dim", 128) or 128)),
        nn.ReLU(),
    ).to(device)
    full_state = _load_state_dict(torch_mods["torch"], dict(model_payload.get("state_dict", {})))
    embedding_state = {
        "0.weight": full_state["0.weight"],
        "0.bias": full_state["0.bias"],
    }
    model.load_state_dict(embedding_state)
    model.eval()
    return model


def evaluate_phase14_torch_model(
    model_payload: dict[str, Any],
    dataset: dict[str, Any],
    *,
    split: str = "validation",
    batch_size: int = 256,
    top_k_values: Iterable[int] = (1, 5, 10),
) -> dict[str, Any]:
    torch_mods = _require_torch()
    torch = torch_mods["torch"]
    F = torch_mods["F"]
    prepared = _prepare_rows(dataset, split=split)
    if not prepared.feature_rows:
        raise ValueError(f"no evaluation examples available for split={split!r}")

    feature_keys = [str(key) for key in model_payload.get("feature_keys", [])]
    label_vocab = [str(label) for label in model_payload.get("label_vocab", [])]
    if feature_keys != prepared.feature_keys:
        raise ValueError("feature-key mismatch between model and dataset")

    model_label_to_id = {label: index for index, label in enumerate(label_vocab)}
    unseen_expected_labels = sorted(set(prepared.label_vocab) - set(label_vocab))

    selected_device = _select_device(torch, str(model_payload.get("device", "cpu")))
    model = _build_torch_model(torch_mods, model_payload, device=selected_device)
    x_eval = torch.tensor(prepared.feature_rows, dtype=torch.float32)

    rows: list[dict[str, Any]] = []
    correct_top1 = 0
    top_k_hits: dict[int, int] = {int(k): 0 for k in top_k_values if int(k) > 0}
    unseen_example_count = 0

    with torch.no_grad():
        for start in range(0, len(prepared.feature_rows), max(1, int(batch_size))):
            end = min(len(prepared.feature_rows), start + max(1, int(batch_size)))
            logits = model(x_eval[start:end].to(selected_device))
            probabilities = F.softmax(logits, dim=1).cpu()
            max_k = max(top_k_hits.keys(), default=1)
            top_values, top_indices = torch.topk(probabilities, k=min(max_k, probabilities.shape[1]), dim=1)
            for offset in range(end - start):
                expected_signature = str(prepared.raw_rows[start + offset].get(prepared.label_field, "")).strip()
                expected_id = model_label_to_id.get(expected_signature)
                ranked_ids = [int(value) for value in top_indices[offset].tolist()]
                predicted_id = ranked_ids[0]
                if expected_id is not None and predicted_id == expected_id:
                    correct_top1 += 1
                for k in top_k_hits:
                    if expected_id is not None and expected_id in ranked_ids[:k]:
                        top_k_hits[k] += 1
                if expected_id is None:
                    unseen_example_count += 1
                rows.append(
                        {
                            "index": start + offset,
                            "expected_signature": expected_signature,
                            "predicted_signature": label_vocab[predicted_id],
                            "correct": expected_id is not None and predicted_id == expected_id,
                            "expected_seen_in_training": expected_id is not None,
                            "top_predictions": [
                                {
                                    "signature": label_vocab[label_id],
                                    "confidence": float(top_values[offset][rank].item()),
                                }
                                for rank, label_id in enumerate(ranked_ids)
                            ],
                        "crop_image_path": str(prepared.raw_rows[start + offset].get("crop_image_path", "")),
                    }
                )

    total_examples = len(prepared.feature_rows)
    return {
        "schema_version": PHASE14_EVAL_SCHEMA_VERSION,
        "model_name": str(model_payload.get("model_name", "")),
        "target_type": prepared.target_type,
        "split": str(split),
        "example_count": total_examples,
        "model_label_count": len(label_vocab),
        "dataset_label_count": len(prepared.label_vocab),
        "unseen_expected_label_count": len(unseen_expected_labels),
        "unseen_expected_labels": unseen_expected_labels,
        "unseen_example_count": unseen_example_count,
        "top1_accuracy": (correct_top1 / total_examples) if total_examples else 0.0,
        "top_k_accuracy": {str(k): ((hits / total_examples) if total_examples else 0.0) for k, hits in sorted(top_k_hits.items())},
        "correct_count": correct_top1,
        "rows": rows,
    }


def evaluate_phase14_retrieval(
    eval_payload: dict[str, Any],
    *,
    top_k_values: Iterable[int] = (1, 5, 10, 20),
) -> dict[str, Any]:
    rows = eval_payload.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    ks = sorted({int(k) for k in top_k_values if int(k) > 0})
    hit_counts = {k: 0 for k in ks}
    reciprocal_rank_sum = 0.0
    exact_rank_sum = 0.0
    found_count = 0
    rendered_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        expected = str(row.get("expected_signature", "")).strip()
        predictions = row.get("top_predictions", [])
        if not isinstance(predictions, list):
            predictions = []
        rank: int | None = None
        for position, item in enumerate(predictions, start=1):
            if not isinstance(item, dict):
                continue
            if str(item.get("signature", "")).strip() == expected:
                rank = position
                break
        if rank is not None:
            found_count += 1
            reciprocal_rank_sum += 1.0 / rank
            exact_rank_sum += float(rank)
            for k in ks:
                if rank <= k:
                    hit_counts[k] += 1
        rendered_rows.append(
            {
                "index": index,
                "expected_signature": expected,
                "predicted_signature": str(row.get("predicted_signature", "")),
                "found_rank": rank,
                "top_predictions": predictions,
                "crop_image_path": str(row.get("crop_image_path", "")),
            }
        )
    total = len(rendered_rows)
    return {
        "schema_version": PHASE14_RETRIEVAL_SCHEMA_VERSION,
        "model_name": str(eval_payload.get("model_name", "")),
        "target_type": str(eval_payload.get("target_type", "")),
        "split": str(eval_payload.get("split", "")),
        "example_count": total,
        "found_count": found_count,
        "mean_reciprocal_rank": (reciprocal_rank_sum / total) if total else 0.0,
        "mean_found_rank": (exact_rank_sum / found_count) if found_count else 0.0,
        "recall_at_k": {str(k): ((hit_counts[k] / total) if total else 0.0) for k in ks},
        "rows": rendered_rows,
    }


def evaluate_phase14_embedding_retrieval(
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
    if feature_keys != gallery.feature_keys or feature_keys != queries.feature_keys:
        raise ValueError("feature-key mismatch between model and dataset")
    selected_device = _select_device(torch, str(model_payload.get("device", "cpu")))
    embedder = _build_embedding_model(torch_mods, model_payload, device=selected_device)
    if not gallery.feature_rows:
        raise ValueError(f"no gallery examples available for split={gallery_split!r}")
    if not queries.feature_rows:
        raise ValueError(f"no query examples available for split={query_split!r}")

    with torch.no_grad():
        gallery_x = torch.tensor(gallery.feature_rows, dtype=torch.float32).to(selected_device)
        query_x = torch.tensor(queries.feature_rows, dtype=torch.float32).to(selected_device)
        gallery_emb = F.normalize(embedder(gallery_x), dim=1).cpu()
        query_emb = F.normalize(embedder(query_x), dim=1).cpu()

    ks = sorted({int(k) for k in top_k_values if int(k) > 0})
    hit_counts = {k: 0 for k in ks}
    reciprocal_rank_sum = 0.0
    exact_rank_sum = 0.0
    rows: list[dict[str, Any]] = []
    max_k = max(ks, default=1)
    for start in range(0, len(queries.feature_rows), max(1, int(batch_size))):
        end = min(len(queries.feature_rows), start + max(1, int(batch_size)))
        scores = torch.matmul(query_emb[start:end], gallery_emb.T)
        top_scores, top_indices = torch.topk(scores, k=min(max_k, scores.shape[1]), dim=1)
        for offset in range(end - start):
            query_row = queries.raw_rows[start + offset]
            expected = str(query_row.get(queries.label_field, "")).strip()
            ranked_indices = [int(value) for value in top_indices[offset].tolist()]
            ranked_labels = [str(gallery.raw_rows[idx].get(gallery.label_field, "")).strip() for idx in ranked_indices]
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
                    "crop_image_path": str(query_row.get("crop_image_path", "")),
                }
            )

    total = len(rows)
    found_count = sum(1 for row in rows if row.get("found_rank") is not None)
    return {
        "schema_version": PHASE14_EMBEDDING_RETRIEVAL_SCHEMA_VERSION,
        "model_name": str(model_payload.get("model_name", "")),
        "target_type": queries.target_type,
        "gallery_split": str(gallery_split),
        "query_split": str(query_split),
        "example_count": total,
        "found_count": found_count,
        "mean_reciprocal_rank": (reciprocal_rank_sum / total) if total else 0.0,
        "mean_found_rank": (exact_rank_sum / found_count) if found_count else 0.0,
        "recall_at_k": {str(k): ((hit_counts[k] / total) if total else 0.0) for k in ks},
        "rows": rows,
    }


def analyze_phase14_errors(
    eval_payload: dict[str, Any],
    *,
    top_confusions_limit: int = 20,
    hardest_rows_limit: int = 20,
) -> dict[str, Any]:
    rows = eval_payload.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    confusion_counts: dict[tuple[str, str], int] = {}
    hard_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        expected = str(row.get("expected_signature", "")).strip()
        predicted = str(row.get("predicted_signature", "")).strip()
        correct = bool(row.get("correct", False))
        if not expected or not predicted or correct:
            continue
        confusion_counts[(expected, predicted)] = confusion_counts.get((expected, predicted), 0) + 1
        top_predictions = row.get("top_predictions", [])
        top_confidence = 0.0
        if isinstance(top_predictions, list) and top_predictions:
            first = top_predictions[0]
            if isinstance(first, dict):
                top_confidence = float(first.get("confidence", first.get("score", 0.0)) or 0.0)
        hard_rows.append(
            {
                "expected_signature": expected,
                "predicted_signature": predicted,
                "top_confidence": top_confidence,
                "crop_image_path": str(row.get("crop_image_path", "")),
                "top_predictions": top_predictions[:10] if isinstance(top_predictions, list) else [],
            }
        )
    sorted_confusions = sorted(confusion_counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
    hardest = sorted(hard_rows, key=lambda row: (-float(row.get("top_confidence", 0.0) or 0.0), str(row.get("expected_signature", ""))))
    return {
        "schema_version": PHASE14_ERROR_ANALYSIS_SCHEMA_VERSION,
        "model_name": str(eval_payload.get("model_name", "")),
        "target_type": str(eval_payload.get("target_type", "")),
        "split": str(eval_payload.get("split", "")),
        "example_count": int(eval_payload.get("example_count", 0) or 0),
        "top_confusions": [
            {
                "expected_signature": expected,
                "predicted_signature": predicted,
                "count": count,
            }
            for (expected, predicted), count in sorted_confusions[: max(1, int(top_confusions_limit))]
        ],
        "hardest_errors": hardest[: max(1, int(hardest_rows_limit))],
    }


def compare_phase14_retrieval_runs(retrieval_payloads: Iterable[dict[str, Any]]) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for payload in retrieval_payloads:
        if not isinstance(payload, dict):
            continue
        recall = payload.get("recall_at_k", {})
        if not isinstance(recall, dict):
            recall = {}
        run_name = str(payload.get("run_name", payload.get("model_name", "")))
        runs.append(
            {
                "run_name": run_name,
                "example_count": int(payload.get("example_count", 0) or 0),
                "mean_reciprocal_rank": float(payload.get("mean_reciprocal_rank", 0.0) or 0.0),
                "mean_found_rank": float(payload.get("mean_found_rank", 0.0) or 0.0),
                "recall_at_1": float(recall.get("1", 0.0) or 0.0),
                "recall_at_5": float(recall.get("5", 0.0) or 0.0),
                "recall_at_10": float(recall.get("10", 0.0) or 0.0),
                "recall_at_20": float(recall.get("20", 0.0) or 0.0),
            }
        )
    ranking = sorted(runs, key=lambda row: (-row["mean_reciprocal_rank"], -row["recall_at_5"], str(row["run_name"])))
    best = ranking[0] if ranking else {}
    return {
        "schema_version": PHASE14_RETRIEVAL_COMPARISON_SCHEMA_VERSION,
        "run_count": len(runs),
        "best": best,
        "ranking": ranking,
    }


def build_phase14_embedding_history_row(
    *,
    run_name: str,
    mean_reciprocal_rank: float,
    recall_at_1: float,
    recall_at_5: float,
    recall_at_10: float,
    example_count: int,
    manifest_path: str,
) -> dict[str, Any]:
    return {
        "schema_version": PHASE14_EMBEDDING_HISTORY_SCHEMA_VERSION,
        "run_name": str(run_name),
        "mean_reciprocal_rank": float(mean_reciprocal_rank),
        "recall_at_1": float(recall_at_1),
        "recall_at_5": float(recall_at_5),
        "recall_at_10": float(recall_at_10),
        "example_count": int(example_count),
        "manifest_path": str(manifest_path),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def phase14_embedding_history_row_to_dict(row: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in row.items()}


def summarize_phase14_embedding_history(rows: Iterable[dict[str, str]], *, recent_window: int = 20) -> dict[str, Any]:
    parsed = list(rows)
    if not parsed:
        return {
            "run_count": 0,
            "best_mrr": 0.0,
            "best_recall_at_1": 0.0,
            "recent_mrr": 0.0,
        }
    recent = parsed[-max(1, int(recent_window)) :]

    def _f(item: dict[str, str], key: str) -> float:
        try:
            return float(item.get(key, "0") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    best = max(parsed, key=lambda row: (_f(row, "mean_reciprocal_rank"), _f(row, "recall_at_1")))
    return {
        "run_count": len(parsed),
        "best_mrr": _f(best, "mean_reciprocal_rank"),
        "best_recall_at_1": _f(best, "recall_at_1"),
        "best_run_name": str(best.get("run_name", "")),
        "recent_mrr": sum(_f(row, "mean_reciprocal_rank") for row in recent) / len(recent),
    }


def compare_phase14_embedding_vs_classifier_retrieval(
    *,
    classifier_retrieval: dict[str, Any],
    embedding_retrieval: dict[str, Any],
) -> dict[str, Any]:
    classifier_target = str(classifier_retrieval.get("target_type", "")).strip().lower()
    embedding_target = str(embedding_retrieval.get("target_type", "")).strip().lower()
    if classifier_target != embedding_target:
        raise ValueError("target-type mismatch between classifier and embedding retrieval payloads")

    classifier_count = int(classifier_retrieval.get("example_count", 0) or 0)
    embedding_count = int(embedding_retrieval.get("example_count", 0) or 0)
    if classifier_count != embedding_count:
        raise ValueError("example-count mismatch between classifier and embedding retrieval payloads")

    classifier_recall = classifier_retrieval.get("recall_at_k", {})
    embedding_recall = embedding_retrieval.get("recall_at_k", {})
    if not isinstance(classifier_recall, dict):
        classifier_recall = {}
    if not isinstance(embedding_recall, dict):
        embedding_recall = {}

    classifier_mrr = float(classifier_retrieval.get("mean_reciprocal_rank", 0.0) or 0.0)
    embedding_mrr = float(embedding_retrieval.get("mean_reciprocal_rank", 0.0) or 0.0)
    classifier_r1 = float(classifier_recall.get("1", 0.0) or 0.0)
    embedding_r1 = float(embedding_recall.get("1", 0.0) or 0.0)
    classifier_r5 = float(classifier_recall.get("5", 0.0) or 0.0)
    embedding_r5 = float(embedding_recall.get("5", 0.0) or 0.0)
    classifier_r10 = float(classifier_recall.get("10", 0.0) or 0.0)
    embedding_r10 = float(embedding_recall.get("10", 0.0) or 0.0)

    return {
        "schema_version": PHASE14_EMBEDDING_COMPARE_SCHEMA_VERSION,
        "target_type": classifier_target,
        "example_count": classifier_count,
        "classifier_model_name": str(classifier_retrieval.get("model_name", "")),
        "embedding_model_name": str(embedding_retrieval.get("model_name", "")),
        "classifier_mean_reciprocal_rank": classifier_mrr,
        "embedding_mean_reciprocal_rank": embedding_mrr,
        "classifier_recall_at_1": classifier_r1,
        "embedding_recall_at_1": embedding_r1,
        "classifier_recall_at_5": classifier_r5,
        "embedding_recall_at_5": embedding_r5,
        "classifier_recall_at_10": classifier_r10,
        "embedding_recall_at_10": embedding_r10,
        "mrr_lift": embedding_mrr - classifier_mrr,
        "recall_at_1_lift": embedding_r1 - classifier_r1,
        "recall_at_5_lift": embedding_r5 - classifier_r5,
        "recall_at_10_lift": embedding_r10 - classifier_r10,
        "embedding_wins": (
            embedding_mrr > classifier_mrr
            or embedding_r1 > classifier_r1
            or embedding_r5 > classifier_r5
            or embedding_r10 > classifier_r10
        ),
    }


def analyze_phase14_embedding_retrieval(
    retrieval_payload: dict[str, Any],
    *,
    hardest_rows_limit: int = 20,
    top_confusions_limit: int = 20,
) -> dict[str, Any]:
    rows = retrieval_payload.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    confusion_counts: dict[tuple[str, str], int] = {}
    hardest_rows: list[dict[str, Any]] = []
    perfect_hits = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        expected = str(row.get("expected_signature", "")).strip()
        rank_value = row.get("found_rank")
        found_rank = int(rank_value) if isinstance(rank_value, int) else None
        predictions = row.get("top_predictions", [])
        if not isinstance(predictions, list):
            predictions = []
        first_prediction = predictions[0] if predictions and isinstance(predictions[0], dict) else {}
        predicted = str(first_prediction.get("signature", "")).strip()
        score = float(first_prediction.get("score", 0.0) or 0.0) if isinstance(first_prediction, dict) else 0.0
        if found_rank == 1:
            perfect_hits += 1
        elif expected and predicted:
            confusion_counts[(expected, predicted)] = confusion_counts.get((expected, predicted), 0) + 1
        hardest_rows.append(
            {
                "expected_signature": expected,
                "predicted_signature": predicted,
                "found_rank": found_rank,
                "top_score": score,
                "crop_image_path": str(row.get("crop_image_path", "")),
                "top_predictions": predictions[:10],
            }
        )
    sorted_confusions = sorted(confusion_counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
    sorted_hardest = sorted(
        hardest_rows,
        key=lambda item: (
            -(int(item.get("found_rank", 10**9)) if item.get("found_rank") is not None else 10**9),
            -float(item.get("top_score", 0.0) or 0.0),
            str(item.get("expected_signature", "")),
        ),
    )
    total = len(hardest_rows)
    return {
        "schema_version": PHASE14_EMBEDDING_ANALYSIS_SCHEMA_VERSION,
        "model_name": str(retrieval_payload.get("model_name", "")),
        "target_type": str(retrieval_payload.get("target_type", "")),
        "gallery_split": str(retrieval_payload.get("gallery_split", "")),
        "query_split": str(retrieval_payload.get("query_split", "")),
        "example_count": total,
        "perfect_hit_count": perfect_hits,
        "perfect_hit_rate": (perfect_hits / total) if total else 0.0,
        "top_confusions": [
            {
                "expected_signature": expected,
                "predicted_signature": predicted,
                "count": count,
            }
            for (expected, predicted), count in sorted_confusions[: max(1, int(top_confusions_limit))]
        ],
        "hardest_rows": sorted_hardest[: max(1, int(hardest_rows_limit))],
    }


def build_phase14_identity_history_row(
    *,
    run_name: str,
    top1_accuracy: float,
    top5_accuracy: float,
    top10_accuracy: float,
    example_count: int,
    manifest_path: str,
) -> dict[str, Any]:
    return {
        "schema_version": PHASE14_IDENTITY_HISTORY_SCHEMA_VERSION,
        "run_name": str(run_name),
        "top1_accuracy": float(top1_accuracy),
        "top5_accuracy": float(top5_accuracy),
        "top10_accuracy": float(top10_accuracy),
        "example_count": int(example_count),
        "manifest_path": str(manifest_path),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def phase14_identity_history_row_to_dict(row: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in row.items()}


def summarize_phase14_identity_history(rows: Iterable[dict[str, str]], *, recent_window: int = 20) -> dict[str, Any]:
    parsed = list(rows)
    if not parsed:
        return {
            "run_count": 0,
            "best_top1_accuracy": 0.0,
            "best_top5_accuracy": 0.0,
            "best_top10_accuracy": 0.0,
            "recent_top1_accuracy": 0.0,
            "recent_top5_accuracy": 0.0,
            "recent_top10_accuracy": 0.0,
        }
    recent = parsed[-max(1, int(recent_window)) :]
    top1_values = [float(row.get("top1_accuracy", 0.0) or 0.0) for row in parsed]
    top5_values = [float(row.get("top5_accuracy", 0.0) or 0.0) for row in parsed]
    top10_values = [float(row.get("top10_accuracy", 0.0) or 0.0) for row in parsed]
    recent_top1 = [float(row.get("top1_accuracy", 0.0) or 0.0) for row in recent]
    recent_top5 = [float(row.get("top5_accuracy", 0.0) or 0.0) for row in recent]
    recent_top10 = [float(row.get("top10_accuracy", 0.0) or 0.0) for row in recent]
    return {
        "run_count": len(parsed),
        "best_top1_accuracy": max(top1_values),
        "best_top5_accuracy": max(top5_values),
        "best_top10_accuracy": max(top10_values),
        "recent_top1_accuracy": sum(recent_top1) / len(recent_top1),
        "recent_top5_accuracy": sum(recent_top5) / len(recent_top5),
        "recent_top10_accuracy": sum(recent_top10) / len(recent_top10),
    }


def compare_phase14_vs_phase13_identity(
    *,
    phase14_eval: dict[str, Any],
    phase13_eval: dict[str, Any],
) -> dict[str, Any]:
    phase14_target = str(phase14_eval.get("target_type", "")).strip().lower()
    phase13_target = str(phase13_eval.get("target_type", "")).strip().lower()
    if phase14_target != phase13_target:
        raise ValueError(f"target-type mismatch: {phase14_target!r} vs {phase13_target!r}")
    phase14_split = str(phase14_eval.get("split", "")).strip().lower()
    phase13_split = str(phase13_eval.get("split", "")).strip().lower()
    if phase14_split != phase13_split:
        raise ValueError(f"split mismatch: {phase14_split!r} vs {phase13_split!r}")

    def _topk(payload: dict[str, Any], key: str) -> float:
        top_k = payload.get("top_k_accuracy", {})
        if isinstance(top_k, dict):
            return float(top_k.get(key, 0.0) or 0.0)
        return 0.0

    phase14_top1 = float(phase14_eval.get("top1_accuracy", 0.0) or 0.0)
    phase13_top1 = float(phase13_eval.get("top1_accuracy", 0.0) or 0.0)
    phase14_top5 = _topk(phase14_eval, "5")
    phase13_top5 = _topk(phase13_eval, "5")
    phase14_top10 = _topk(phase14_eval, "10")
    phase13_top10 = _topk(phase13_eval, "10")
    return {
        "schema_version": PHASE14_COMPARE_SCHEMA_VERSION,
        "target_type": phase14_target,
        "split": phase14_split,
        "phase14_model_name": str(phase14_eval.get("model_name", "")),
        "phase13_model_name": str(phase13_eval.get("model_name", "")),
        "phase14_top1_accuracy": phase14_top1,
        "phase13_top1_accuracy": phase13_top1,
        "phase14_top5_accuracy": phase14_top5,
        "phase13_top5_accuracy": phase13_top5,
        "phase14_top10_accuracy": phase14_top10,
        "phase13_top10_accuracy": phase13_top10,
        "top1_lift": phase14_top1 - phase13_top1,
        "top5_lift": phase14_top5 - phase13_top5,
        "top10_lift": phase14_top10 - phase13_top10,
        "phase14_example_count": int(phase14_eval.get("example_count", 0) or 0),
        "phase13_example_count": int(phase13_eval.get("example_count", 0) or 0),
        "phase14_wins": (
            (phase14_top1 > phase13_top1)
            or (phase14_top1 == phase13_top1 and phase14_top5 > phase13_top5)
            or (phase14_top1 == phase13_top1 and phase14_top5 == phase13_top5 and phase14_top10 >= phase13_top10)
        ),
    }


def build_phase14_compare_history_row(
    *,
    run_name: str,
    top1_lift: float,
    top5_lift: float,
    top10_lift: float,
    phase14_wins: bool,
    manifest_path: str,
) -> dict[str, Any]:
    return {
        "schema_version": PHASE14_COMPARE_HISTORY_SCHEMA_VERSION,
        "run_name": str(run_name),
        "top1_lift": float(top1_lift),
        "top5_lift": float(top5_lift),
        "top10_lift": float(top10_lift),
        "phase14_wins": bool(phase14_wins),
        "manifest_path": str(manifest_path),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def phase14_compare_history_row_to_dict(row: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in row.items()}


def summarize_phase14_compare_history(rows: Iterable[dict[str, str]], *, recent_window: int = 20) -> dict[str, Any]:
    parsed = list(rows)
    if not parsed:
        return {
            "run_count": 0,
            "phase14_win_rate_recent": 0.0,
            "best_top1_lift": 0.0,
            "latest_top1_lift": 0.0,
        }
    recent = parsed[-max(1, int(recent_window)) :]

    def _f(item: dict[str, str], key: str) -> float:
        try:
            return float(item.get(key, "0") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _b(item: dict[str, str], key: str) -> bool:
        return str(item.get(key, "")).strip().lower() == "true"

    best = max(parsed, key=lambda row: _f(row, "top1_lift"))
    latest = parsed[-1]
    return {
        "run_count": len(parsed),
        "phase14_win_rate_recent": (sum(1 for row in recent if _b(row, "phase14_wins")) / len(recent)),
        "best_top1_lift": _f(best, "top1_lift"),
        "best_run_name": str(best.get("run_name", "")),
        "latest_top1_lift": _f(latest, "top1_lift"),
        "latest_run_name": str(latest.get("run_name", "")),
    }
