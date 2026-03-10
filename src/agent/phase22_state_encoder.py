from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.agent.phase14_torch import has_torch_support


PHASE22_MODEL_SCHEMA_VERSION = "phase22.state_encoder.v1"
PHASE22_EVAL_SCHEMA_VERSION = "phase22.state_eval.v1"
PHASE22_COMPARE_SCHEMA_VERSION = "phase22.compare.v1"
PHASE22_DISTRIBUTION_SCHEMA_VERSION = "phase22.target_distribution.v1"

DEFAULT_NUMERIC_FIELDS = (
    "turn_number",
    "state_features.active_player",
    "state_features.self_hand_size",
    "state_features.self_life_size",
    "state_features.self_energy_size",
    "state_features.self_energy_resting_count",
    "state_features.self_battle_size",
    "state_features.self_unison_size",
    "state_features.self_drop_size",
    "state_features.self_warp_size",
    "state_features.opponent_hand_size",
    "state_features.opponent_life_size",
    "state_features.opponent_energy_size",
    "state_features.opponent_battle_size",
    "state_features.opponent_unison_size",
    "state_features.opponent_drop_size",
    "state_features.opponent_warp_size",
    "state_features.self_identity_resolution_count",
    "state_features.opponent_identity_resolution_count",
)

DEFAULT_CATEGORICAL_FIELDS = (
    "phase",
    "actor_role_bucket",
    "action_family",
    "action_features.attacker_zone",
    "action_features.target_zone",
    "action_features.target_player",
    "action_features.source_zone",
    "action_features.is_leader_attack",
    "action_features.is_battle_attack",
    "action_features.is_leader_target",
    "action_features.is_battle_target",
    "action_features.turn_bucket",
    "action_features.self_energy_size_bucket",
    "action_features.self_battle_size_bucket",
    "action_features.opponent_battle_size_bucket",
    "action_features.opponent_life_bucket",
    "action_features.self_board_state",
    "action_features.opponent_board_state",
    "action_features.is_pressure_window",
    "action_features.is_curve_play",
    "action_features.is_existing_board_extension",
    "action_features.is_empty_board_setup",
    "action_features.has_other_attackers",
    "state_features.battle_step",
    "state_features.counter_window_kind",
    "state_features.self_has_identity_resolution",
    "state_features.opponent_has_identity_resolution",
    "state_features.self_primary_resolved_signature",
    "state_features.opponent_primary_resolved_signature",
)


def _require_torch() -> Any:
    if not has_torch_support():
        raise RuntimeError(
            "PyTorch is not installed. Install the dependencies in requirements-torch.txt, then rerun."
        )
    import torch
    import torch.nn as nn
    import torch.utils.data as torch_data

    return {
        "torch": torch,
        "nn": nn,
        "torch_data": torch_data,
    }


def _extract_path(data: dict[str, Any], path: str) -> object:
    current: object = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _filtered_examples(dataset: dict[str, Any], split: str) -> list[dict[str, Any]]:
    examples = dataset.get("examples", [])
    if not isinstance(examples, list):
        return []
    return [row for row in examples if isinstance(row, dict) and (split == "all" or row.get("split") == split)]


def summarize_phase22_target_distribution(
    dataset: dict[str, Any],
    *,
    target_field: str = "action_type",
    split: str = "train",
) -> dict[str, Any]:
    examples = _filtered_examples(dataset, split)
    counts: dict[str, int] = {}
    for row in examples:
        label = str(row.get(target_field, "")).strip()
        if not label:
            continue
        counts[label] = counts.get(label, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return {
        "schema_version": PHASE22_DISTRIBUTION_SCHEMA_VERSION,
        "target_field": str(target_field),
        "split": str(split),
        "example_count": len(examples),
        "label_count": len(counts),
        "labels": [{"label": label, "count": count} for label, count in ranked],
    }


def _as_float(value: object) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_token(value: object) -> str:
    if value is None:
        return "__missing__"
    text = str(value).strip()
    return text if text else "__missing__"


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
    loaded: dict[str, Any] = {}
    for key, value in state_dict_payload.items():
        tensor = torch.tensor(value)
        if key.endswith("num_batches_tracked"):
            tensor = tensor.to(dtype=torch.long)
        else:
            tensor = tensor.to(dtype=torch.float32)
        loaded[str(key)] = tensor
    return loaded


@dataclass
class _PreparedExamples:
    numeric_fields: list[str]
    categorical_fields: list[str]
    category_vocabs: dict[str, list[str]]
    label_vocab: list[str]
    numeric_rows: list[list[float]]
    categorical_rows: list[list[int]]
    label_ids: list[int]
    raw_rows: list[dict[str, Any]]


def _build_category_vocabs(
    examples: list[dict[str, Any]],
    categorical_fields: tuple[str, ...],
) -> dict[str, list[str]]:
    vocabs: dict[str, list[str]] = {}
    for field in categorical_fields:
        tokens = {"__missing__", "__unknown__"}
        for row in examples:
            tokens.add(_as_token(_extract_path(row, field)))
        ordered = ["__missing__", "__unknown__"] + [token for token in sorted(tokens) if token not in {"__missing__", "__unknown__"}]
        vocabs[field] = ordered
    return vocabs


def _prepare_examples(
    dataset: dict[str, Any],
    *,
    split: str,
    target_field: str,
    numeric_fields: tuple[str, ...],
    categorical_fields: tuple[str, ...],
    category_vocabs: dict[str, list[str]] | None = None,
    label_vocab: list[str] | None = None,
) -> _PreparedExamples:
    examples = _filtered_examples(dataset, split)
    training_style_examples = _filtered_examples(dataset, "train")
    if category_vocabs is None:
        category_vocabs = _build_category_vocabs(training_style_examples or examples, categorical_fields)
    numeric_rows: list[list[float]] = []
    categorical_rows: list[list[int]] = []
    labels: list[str] = []
    raw_rows: list[dict[str, Any]] = []
    for row in examples:
        target = str(row.get(target_field, "")).strip()
        if not target:
            continue
        numeric_rows.append([_as_float(_extract_path(row, field)) for field in numeric_fields])
        cat_ids: list[int] = []
        for field in categorical_fields:
            vocab = category_vocabs[field]
            token = _as_token(_extract_path(row, field))
            try:
                cat_ids.append(vocab.index(token))
            except ValueError:
                cat_ids.append(vocab.index("__unknown__"))
        categorical_rows.append(cat_ids)
        labels.append(target)
        raw_rows.append(row)
    if label_vocab is None:
        label_vocab = sorted(set(str(row.get(target_field, "")).strip() for row in (training_style_examples or examples) if str(row.get(target_field, "")).strip()))
    label_to_id = {label: idx for idx, label in enumerate(label_vocab)}
    filtered_numeric: list[list[float]] = []
    filtered_categorical: list[list[int]] = []
    filtered_label_ids: list[int] = []
    filtered_raw: list[dict[str, Any]] = []
    for numeric_row, categorical_row, label, raw_row in zip(numeric_rows, categorical_rows, labels, raw_rows):
        if label not in label_to_id:
            continue
        filtered_numeric.append(numeric_row)
        filtered_categorical.append(categorical_row)
        filtered_label_ids.append(label_to_id[label])
        filtered_raw.append(raw_row)
    return _PreparedExamples(
        numeric_fields=list(numeric_fields),
        categorical_fields=list(categorical_fields),
        category_vocabs={key: list(value) for key, value in category_vocabs.items()},
        label_vocab=list(label_vocab),
        numeric_rows=filtered_numeric,
        categorical_rows=filtered_categorical,
        label_ids=filtered_label_ids,
        raw_rows=filtered_raw,
    )


def train_phase22_state_encoder(
    dataset: dict[str, Any],
    *,
    split: str = "train",
    target_field: str = "action_type",
    numeric_fields: tuple[str, ...] = DEFAULT_NUMERIC_FIELDS,
    categorical_fields: tuple[str, ...] = DEFAULT_CATEGORICAL_FIELDS,
    epochs: int = 20,
    batch_size: int = 64,
    hidden_dim: int = 128,
    embedding_dim: int = 16,
    learning_rate: float = 1e-3,
    device: str = "auto",
    seed: int = 13,
    progress_every: int = 0,
) -> dict[str, Any]:
    torch_mods = _require_torch()
    torch = torch_mods["torch"]
    nn = torch_mods["nn"]
    torch_data = torch_mods["torch_data"]

    prepared = _prepare_examples(
        dataset,
        split=split,
        target_field=target_field,
        numeric_fields=numeric_fields,
        categorical_fields=categorical_fields,
    )
    if not prepared.numeric_rows:
        raise ValueError(f"no training examples available for split={split!r}")
    if len(prepared.label_vocab) < 2:
        raise ValueError("need at least 2 classes to train a Phase 22 state encoder")

    torch.manual_seed(int(seed))
    selected_device = _select_device(torch, device)

    class StateEncoder(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.embeddings = nn.ModuleList(
                [
                    nn.Embedding(
                        num_embeddings=max(2, len(prepared.category_vocabs[field])),
                        embedding_dim=min(int(embedding_dim), max(4, len(prepared.category_vocabs[field]))),
                    )
                    for field in prepared.categorical_fields
                ]
            )
            cat_width = sum(int(emb.embedding_dim) for emb in self.embeddings)
            self.net = nn.Sequential(
                nn.Linear(len(prepared.numeric_fields) + cat_width, int(hidden_dim)),
                nn.ReLU(),
                nn.Linear(int(hidden_dim), len(prepared.label_vocab)),
            )

        def forward(self, numeric_x: Any, categorical_x: Any) -> Any:
            embedded = []
            for index, emb in enumerate(self.embeddings):
                embedded.append(emb(categorical_x[:, index]))
            if embedded:
                x = torch.cat([numeric_x, *embedded], dim=1)
            else:
                x = numeric_x
            return self.net(x)

    model = StateEncoder().to(selected_device)
    x_num = torch.tensor(prepared.numeric_rows, dtype=torch.float32)
    x_cat = torch.tensor(prepared.categorical_rows, dtype=torch.long)
    y = torch.tensor(prepared.label_ids, dtype=torch.long)
    loader = torch_data.DataLoader(
        torch_data.TensorDataset(x_num, x_cat, y),
        batch_size=max(1, int(batch_size)),
        shuffle=True,
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=float(learning_rate))
    loss_fn = nn.CrossEntropyLoss()
    losses: list[float] = []
    for epoch in range(max(1, int(epochs))):
        model.train()
        epoch_loss = 0.0
        batch_count = 0
        for batch_num, batch_cat, batch_y in loader:
            batch_num = batch_num.to(selected_device)
            batch_cat = batch_cat.to(selected_device)
            batch_y = batch_y.to(selected_device)
            optimizer.zero_grad()
            logits = model(batch_num, batch_cat)
            loss = loss_fn(logits, batch_y)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item())
            batch_count += 1
        average_loss = epoch_loss / max(1, batch_count)
        losses.append(average_loss)
        if progress_every > 0 and (((epoch + 1) % progress_every) == 0 or (epoch + 1) == int(epochs)):
            print(f"[phase22-train] epoch {epoch + 1}/{int(epochs)} loss={average_loss:.6f}")

    return {
        "schema_version": PHASE22_MODEL_SCHEMA_VERSION,
        "model_name": "phase22_state_encoder",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "train_split": str(split),
        "target_field": str(target_field),
        "numeric_fields": list(prepared.numeric_fields),
        "categorical_fields": list(prepared.categorical_fields),
        "category_vocabs": prepared.category_vocabs,
        "label_vocab": prepared.label_vocab,
        "hidden_dim": int(hidden_dim),
        "embedding_dim": int(embedding_dim),
        "epochs": int(epochs),
        "batch_size": int(batch_size),
        "learning_rate": float(learning_rate),
        "seed": int(seed),
        "device": selected_device,
        "example_count": len(prepared.numeric_rows),
        "loss_curve": losses,
        "state_dict": _serialize_state_dict(model.state_dict()),
    }


def evaluate_phase22_state_encoder(
    model_payload: dict[str, Any],
    dataset: dict[str, Any],
    *,
    split: str = "validation",
    batch_size: int = 64,
    device: str = "auto",
    top_k_values: tuple[int, ...] = (1, 3, 5),
) -> dict[str, Any]:
    torch_mods = _require_torch()
    torch = torch_mods["torch"]
    nn = torch_mods["nn"]
    target_field = str(model_payload.get("target_field", "action_type"))
    numeric_fields = tuple(str(item) for item in model_payload.get("numeric_fields", []))
    categorical_fields = tuple(str(item) for item in model_payload.get("categorical_fields", []))
    category_vocabs = {str(key): [str(v) for v in value] for key, value in dict(model_payload.get("category_vocabs", {})).items()}
    label_vocab = [str(item) for item in model_payload.get("label_vocab", [])]
    prepared = _prepare_examples(
        dataset,
        split=split,
        target_field=target_field,
        numeric_fields=numeric_fields,
        categorical_fields=categorical_fields,
        category_vocabs=category_vocabs,
        label_vocab=label_vocab,
    )
    selected_device = _select_device(torch, device)

    class StateEncoder(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.embeddings = nn.ModuleList(
                [
                    nn.Embedding(
                        num_embeddings=max(2, len(category_vocabs[field])),
                        embedding_dim=min(int(model_payload.get("embedding_dim", 16) or 16), max(4, len(category_vocabs[field]))),
                    )
                    for field in prepared.categorical_fields
                ]
            )
            cat_width = sum(int(emb.embedding_dim) for emb in self.embeddings)
            self.net = nn.Sequential(
                nn.Linear(len(prepared.numeric_fields) + cat_width, int(model_payload.get("hidden_dim", 128) or 128)),
                nn.ReLU(),
                nn.Linear(int(model_payload.get("hidden_dim", 128) or 128), len(label_vocab)),
            )

        def forward(self, numeric_x: Any, categorical_x: Any) -> Any:
            embedded = []
            for index, emb in enumerate(self.embeddings):
                embedded.append(emb(categorical_x[:, index]))
            x = torch.cat([numeric_x, *embedded], dim=1) if embedded else numeric_x
            return self.net(x)

    model = StateEncoder().to(selected_device)
    model.load_state_dict(_load_state_dict(torch, dict(model_payload.get("state_dict", {}))))
    model.eval()

    x_num = torch.tensor(prepared.numeric_rows, dtype=torch.float32)
    x_cat = torch.tensor(prepared.categorical_rows, dtype=torch.long)
    y = torch.tensor(prepared.label_ids, dtype=torch.long)
    total = len(prepared.numeric_rows)
    normalized_top_k = tuple(sorted({max(1, int(value)) for value in top_k_values}))
    if total == 0:
        return {
            "schema_version": PHASE22_EVAL_SCHEMA_VERSION,
            "model_name": str(model_payload.get("model_name", "phase22_state_encoder")),
            "target_field": target_field,
            "split": str(split),
            "example_count": 0,
            "top1_accuracy": 0.0,
            "top_k_accuracy": {str(value): 0.0 for value in normalized_top_k},
            "rows": [],
        }
    correct = 0
    top_k_correct = {int(value): 0 for value in normalized_top_k}
    rows: list[dict[str, Any]] = []
    with torch.no_grad():
        for start in range(0, total, max(1, int(batch_size))):
            batch_num = x_num[start : start + int(batch_size)].to(selected_device)
            batch_cat = x_cat[start : start + int(batch_size)].to(selected_device)
            batch_y = y[start : start + int(batch_size)].to(selected_device)
            logits = model(batch_num, batch_cat)
            predictions = torch.argmax(logits, dim=1)
            max_k = min(max(normalized_top_k), logits.shape[1])
            top_scores, top_indices = torch.topk(logits, k=max_k, dim=1)
            for offset, (predicted_id, actual_id) in enumerate(zip(predictions.tolist(), batch_y.tolist())):
                example = prepared.raw_rows[start + offset]
                predicted = label_vocab[int(predicted_id)]
                actual = label_vocab[int(actual_id)]
                matched = predicted == actual
                correct += 1 if matched else 0
                ranked_ids = [int(value) for value in top_indices[offset].tolist()]
                ranked_labels = [label_vocab[idx] for idx in ranked_ids]
                for value in normalized_top_k:
                    if actual in ranked_labels[: min(int(value), len(ranked_labels))]:
                        top_k_correct[int(value)] += 1
                rows.append(
                    {
                        "example_index": int(example.get("example_index", start + offset) or (start + offset)),
                        "source_name": str(example.get("source_name", "")),
                        "trace_hash": str(example.get("trace_hash", "")),
                        "predicted_label": predicted,
                        "actual_label": actual,
                        "matched": matched,
                        "action_type": str(example.get("action_type", "")),
                        "action_signature": str(example.get("action_signature", "")),
                        "decision_class": str(example.get("decision_class", "")),
                        "top_predictions": [
                            {
                                "rank": rank + 1,
                                "label": label_vocab[int(label_id)],
                                "score": float(top_scores[offset][rank].item()),
                            }
                            for rank, label_id in enumerate(ranked_ids)
                        ],
                        "has_identity_resolution": bool(example.get("has_identity_resolution")),
                    }
                )
    return {
        "schema_version": PHASE22_EVAL_SCHEMA_VERSION,
        "model_name": str(model_payload.get("model_name", "phase22_state_encoder")),
        "target_field": target_field,
        "split": str(split),
        "example_count": total,
        "top1_accuracy": float(correct) / float(total),
        "top_k_accuracy": {str(value): (float(top_k_correct[int(value)]) / float(total)) for value in normalized_top_k},
        "rows": rows,
        "identity_resolved_example_count": sum(1 for row in prepared.raw_rows if bool(row.get("has_identity_resolution"))),
        "identity_resolved_example_rate": sum(1 for row in prepared.raw_rows if bool(row.get("has_identity_resolution"))) / float(total),
    }


def compare_phase22_vs_backoff(
    *,
    phase22_eval: dict[str, Any],
    baseline_eval: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": PHASE22_COMPARE_SCHEMA_VERSION,
        "phase22_model_name": str(phase22_eval.get("model_name", "phase22_state_encoder")),
        "baseline_model_name": str(baseline_eval.get("model_name", "backoff_frequency_policy")),
        "target_field": str(phase22_eval.get("target_field", baseline_eval.get("target_field", "action_type"))),
        "split": str(phase22_eval.get("split", baseline_eval.get("split", "validation"))),
        "phase22_top1_accuracy": float(phase22_eval.get("top1_accuracy", 0.0) or 0.0),
        "baseline_top1_accuracy": float(baseline_eval.get("top1_accuracy", 0.0) or 0.0),
        "top1_lift": float(phase22_eval.get("top1_accuracy", 0.0) or 0.0) - float(baseline_eval.get("top1_accuracy", 0.0) or 0.0),
        "phase22_wins": float(phase22_eval.get("top1_accuracy", 0.0) or 0.0) > float(baseline_eval.get("top1_accuracy", 0.0) or 0.0),
        "identity_resolved_example_rate": float(phase22_eval.get("identity_resolved_example_rate", 0.0) or 0.0),
    }
