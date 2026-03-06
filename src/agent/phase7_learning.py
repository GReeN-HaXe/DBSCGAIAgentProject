from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


FREQUENCY_MODEL_SCHEMA_VERSION = "phase7.frequency.v1"
BACKOFF_MODEL_SCHEMA_VERSION = "phase8.backoff_frequency.v1"
DEFAULT_CONTEXT_FIELDS = (
    "phase",
    "actor_role_bucket",
    "action_family",
    "state_features.battle_step",
    "state_features.self_energy_size",
    "state_features.self_battle_size",
    "state_features.opponent_life_size",
)


def _extract_path(data: dict[str, Any], path: str) -> object:
    current: object = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _filtered_examples(dataset: dict[str, object], split: str) -> list[dict[str, Any]]:
    examples = dataset.get("examples", [])
    if not isinstance(examples, list):
        return []
    return [row for row in examples if isinstance(row, dict) and (split == "all" or row.get("split") == split)]


def build_frequency_context_key(example: dict[str, Any], context_fields: tuple[str, ...] = DEFAULT_CONTEXT_FIELDS) -> str:
    parts: list[str] = []
    for field in context_fields:
        value = _extract_path(example, field)
        parts.append(f"{field}={value}")
    return "|".join(parts)


def _ranked_majority(counts: Counter[str]) -> str:
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return "" if not ranked else ranked[0][0]


def train_frequency_policy_model(
    dataset: dict[str, object],
    *,
    split: str = "train",
    target_field: str = "action_type",
    context_fields: tuple[str, ...] = DEFAULT_CONTEXT_FIELDS,
) -> dict[str, Any]:
    examples = _filtered_examples(dataset, split)
    global_counts: Counter[str] = Counter()
    context_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in examples:
        target = str(row.get(target_field, "unknown"))
        global_counts[target] += 1
        context_counts[build_frequency_context_key(row, context_fields)][target] += 1

    global_majority = ""
    if global_counts:
        global_majority = sorted(global_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]

    contexts_payload: dict[str, dict[str, Any]] = {}
    for key, counts in context_counts.items():
        contexts_payload[key] = {
            "counts": dict(counts),
            "majority_label": _ranked_majority(counts),
        }

    return {
        "schema_version": FREQUENCY_MODEL_SCHEMA_VERSION,
        "model_name": "frequency_policy",
        "target_field": str(target_field),
        "train_split": str(split),
        "context_fields": list(context_fields),
        "example_count": len(examples),
        "global_counts": dict(global_counts),
        "global_majority_label": global_majority,
        "contexts": contexts_payload,
    }


def train_backoff_policy_model(
    dataset: dict[str, object],
    *,
    split: str = "train",
    target_field: str = "action_type",
    context_fields: tuple[str, ...] = DEFAULT_CONTEXT_FIELDS,
) -> dict[str, Any]:
    examples = _filtered_examples(dataset, split)
    global_counts: Counter[str] = Counter()
    level_contexts: list[dict[str, Counter[str]]] = [defaultdict(Counter) for _ in range(len(context_fields))]
    for row in examples:
        target = str(row.get(target_field, "unknown"))
        global_counts[target] += 1
        for level in range(len(context_fields)):
            subset = context_fields[: len(context_fields) - level]
            key = build_frequency_context_key(row, subset)
            level_contexts[level][key][target] += 1
    levels_payload: list[dict[str, object]] = []
    for level, context_map in enumerate(level_contexts):
        subset = context_fields[: len(context_fields) - level]
        payload_contexts: dict[str, dict[str, object]] = {}
        for key, counts in context_map.items():
            payload_contexts[key] = {
                "counts": dict(counts),
                "majority_label": _ranked_majority(counts),
            }
        levels_payload.append(
            {
                "level_index": level,
                "context_fields": list(subset),
                "contexts": payload_contexts,
            }
        )
    return {
        "schema_version": BACKOFF_MODEL_SCHEMA_VERSION,
        "model_name": "backoff_frequency_policy",
        "target_field": str(target_field),
        "train_split": str(split),
        "context_fields": list(context_fields),
        "example_count": len(examples),
        "global_counts": dict(global_counts),
        "global_majority_label": _ranked_majority(global_counts),
        "levels": levels_payload,
    }


def predict_frequency_policy(model: dict[str, Any], example: dict[str, Any]) -> str:
    context_fields = tuple(str(item) for item in model.get("context_fields", []) if item)
    if not context_fields:
        context_fields = DEFAULT_CONTEXT_FIELDS
    key = build_frequency_context_key(example, context_fields)
    contexts = model.get("contexts", {})
    if isinstance(contexts, dict):
        payload = contexts.get(key)
        if isinstance(payload, dict):
            label = payload.get("majority_label")
            if isinstance(label, str) and label:
                return label
    label = model.get("global_majority_label")
    return str(label) if label is not None else ""


def predict_backoff_policy(model: dict[str, Any], example: dict[str, Any]) -> str:
    levels = model.get("levels", [])
    if isinstance(levels, list):
        for level in levels:
            if not isinstance(level, dict):
                continue
            context_fields = tuple(str(item) for item in level.get("context_fields", []) if item)
            if not context_fields:
                continue
            key = build_frequency_context_key(example, context_fields)
            contexts = level.get("contexts", {})
            if not isinstance(contexts, dict):
                continue
            payload = contexts.get(key)
            if isinstance(payload, dict):
                label = payload.get("majority_label")
                if isinstance(label, str) and label:
                    return label
    label = model.get("global_majority_label")
    return str(label) if label is not None else ""


def evaluate_frequency_policy_model(
    dataset: dict[str, object],
    model: dict[str, Any],
    *,
    split: str = "validation",
) -> dict[str, Any]:
    target_field = str(model.get("target_field", "action_type"))
    examples = _filtered_examples(dataset, split)
    total = len(examples)
    correct = 0
    by_target: dict[str, dict[str, int | float | str]] = {}
    for row in examples:
        actual = str(row.get(target_field, "unknown"))
        predicted = predict_frequency_policy(model, row)
        bucket = by_target.setdefault(actual, {"count": 0, "matched": 0})
        bucket["count"] = int(bucket["count"]) + 1
        if predicted == actual:
            correct += 1
            bucket["matched"] = int(bucket["matched"]) + 1
    for actual, bucket in by_target.items():
        count = int(bucket["count"])
        bucket["accuracy"] = 0.0 if count == 0 else float(bucket["matched"]) / float(count)
        bucket["target_label"] = actual
    return {
        "model_name": str(model.get("model_name", "frequency_policy")),
        "target_field": target_field,
        "split": str(split),
        "example_count": total,
        "top1_accuracy": 0.0 if total == 0 else float(correct) / float(total),
        "by_target_label": [by_target[key] for key in sorted(by_target.keys())],
    }


def evaluate_backoff_policy_model(
    dataset: dict[str, object],
    model: dict[str, Any],
    *,
    split: str = "validation",
) -> dict[str, Any]:
    target_field = str(model.get("target_field", "action_type"))
    examples = _filtered_examples(dataset, split)
    total = len(examples)
    correct = 0
    by_target: dict[str, dict[str, int | float | str]] = {}
    for row in examples:
        actual = str(row.get(target_field, "unknown"))
        predicted = predict_backoff_policy(model, row)
        bucket = by_target.setdefault(actual, {"count": 0, "matched": 0})
        bucket["count"] = int(bucket["count"]) + 1
        if predicted == actual:
            correct += 1
            bucket["matched"] = int(bucket["matched"]) + 1
    for actual, bucket in by_target.items():
        count = int(bucket["count"])
        bucket["accuracy"] = 0.0 if count == 0 else float(bucket["matched"]) / float(count)
        bucket["target_label"] = actual
    return {
        "model_name": str(model.get("model_name", "backoff_frequency_policy")),
        "target_field": target_field,
        "split": str(split),
        "example_count": total,
        "top1_accuracy": 0.0 if total == 0 else float(correct) / float(total),
        "by_target_label": [by_target[key] for key in sorted(by_target.keys())],
    }
