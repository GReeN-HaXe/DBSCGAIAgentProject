from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import (
    evaluate_backoff_policy_model,
    evaluate_frequency_policy_model,
    predict_backoff_policy,
    predict_frequency_policy,
)


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def _filtered_examples(dataset: dict[str, object], split: str) -> list[dict[str, object]]:
    examples = dataset.get("examples", [])
    if not isinstance(examples, list):
        return []
    return [row for row in examples if isinstance(row, dict) and (split == "all" or row.get("split") == split)]


def _predict(model: dict[str, object], example: dict[str, object]) -> str:
    model_name = str(model.get("model_name", ""))
    if model_name == "backoff_frequency_policy":
        return predict_backoff_policy(model, example)
    return predict_frequency_policy(model, example)


def _evaluate(dataset: dict[str, object], model: dict[str, object], split: str) -> dict[str, object]:
    model_name = str(model.get("model_name", ""))
    if model_name == "backoff_frequency_policy":
        return evaluate_backoff_policy_model(dataset, model, split=split)
    return evaluate_frequency_policy_model(dataset, model, split=split)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Phase 8 model errors and simple context ablations.")
    parser.add_argument("--dataset", type=Path, required=True, help="Phase 7 dataset JSON path.")
    parser.add_argument("--model", type=Path, required=True, help="Trained model JSON path.")
    parser.add_argument("--split", choices=["train", "validation", "all"], default="validation", help="Dataset split to analyze.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase8_error_analysis.json"), help="Analysis output path.")
    args = parser.parse_args()

    dataset = _load_json(args.dataset)
    model = _load_json(args.model)
    target_field = str(model.get("target_field", "action_type"))
    examples = _filtered_examples(dataset, str(args.split))
    mismatches: list[dict[str, object]] = []
    confusion: Counter[str] = Counter()
    phase_mismatch: Counter[str] = Counter()
    for row in examples:
        actual = str(row.get(target_field, "unknown"))
        predicted = _predict(model, row)
        if predicted != actual:
            mismatches.append(
                {
                    "example_index": row.get("example_index"),
                    "phase": row.get("phase"),
                    "actual": actual,
                    "predicted": predicted,
                    "action_family": row.get("action_family"),
                }
            )
            confusion[f"{actual}->{predicted}"] += 1
            phase_mismatch[str(row.get("phase", ""))] += 1

    ablations: list[dict[str, object]] = []
    context_fields = [str(item) for item in model.get("context_fields", []) if item]
    for field in context_fields:
        count = sum(1 for row in examples if row.get("state_features", {}).get(field.split(".")[-1]) is None) if field.startswith("state_features.") else 0
        ablations.append({"field": field, "missing_count": count})

    baseline_eval = _evaluate(dataset, model, str(args.split))
    payload = {
        "model_name": str(model.get("model_name", "")),
        "target_field": target_field,
        "split": str(args.split),
        "baseline_top1_accuracy": float(baseline_eval.get("top1_accuracy", 0.0) or 0.0),
        "error_count": len(mismatches),
        "top_confusions": [{"pair": key, "count": value} for key, value in confusion.most_common(10)],
        "phase_mismatch_counts": dict(phase_mismatch),
        "ablations": ablations,
        "sample_errors": mismatches[:10],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
