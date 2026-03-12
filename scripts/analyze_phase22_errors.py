from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.phase22_runtime import evaluate_phase22_production


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Phase 22 production errors by dataset, source, and decision class.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--production-dir", type=Path, default=Path("artifacts/phase22_production"))
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--top-k", nargs="*", type=int, default=[1, 3, 5])
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase22_production/phase22_error_analysis.json"))
    args = parser.parse_args()

    evaluation = evaluate_phase22_production(
        production_dir=args.production_dir,
        model_path=args.model,
        summary_path=args.summary,
        dataset_path=args.dataset,
        split=str(args.split),
        batch_size=int(args.batch_size),
        top_k_values=tuple(int(value) for value in args.top_k),
    )
    rows = evaluation.get("rows", [])
    if not isinstance(rows, list):
        rows = []

    confusion = Counter()
    by_source: dict[str, dict[str, int]] = defaultdict(lambda: {"example_count": 0, "error_count": 0})
    by_actual: dict[str, dict[str, int]] = defaultdict(lambda: {"example_count": 0, "error_count": 0})
    sample_errors: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        source_name = str(row.get("source_name", "unknown"))
        actual = str(row.get("actual_label", ""))
        predicted = str(row.get("predicted_label", ""))
        matched = bool(row.get("matched"))

        by_source[source_name]["example_count"] += 1
        by_actual[actual]["example_count"] += 1
        if not matched:
            by_source[source_name]["error_count"] += 1
            by_actual[actual]["error_count"] += 1
            confusion[f"{actual}->{predicted}"] += 1
            if len(sample_errors) < 20:
                sample_errors.append(
                    {
                        "source_name": source_name,
                        "example_index": row.get("example_index"),
                        "action_type": row.get("action_type"),
                        "action_signature": row.get("action_signature"),
                        "actual_label": actual,
                        "predicted_label": predicted,
                        "top_predictions": row.get("top_predictions", []),
                    }
                )

    payload = {
        "schema_version": "phase22.error_analysis.v1",
        "dataset_path": str(args.dataset.resolve()),
        "split": str(args.split),
        "example_count": int(evaluation.get("example_count", 0) or 0),
        "top1_accuracy": float(evaluation.get("top1_accuracy", 0.0) or 0.0),
        "top_k_accuracy": dict(evaluation.get("top_k_accuracy", {}))
        if isinstance(evaluation.get("top_k_accuracy"), dict)
        else {},
        "error_count": sum(1 for row in rows if isinstance(row, dict) and not bool(row.get("matched"))),
        "top_confusions": [{"pair": key, "count": value} for key, value in confusion.most_common(20)],
        "per_source": [
            {
                "source_name": source_name,
                "example_count": stats["example_count"],
                "error_count": stats["error_count"],
                "top1_accuracy": (
                    float(stats["example_count"] - stats["error_count"]) / float(stats["example_count"])
                    if stats["example_count"]
                    else 0.0
                ),
            }
            for source_name, stats in sorted(by_source.items())
        ],
        "per_actual_label": [
            {
                "label": label,
                "example_count": stats["example_count"],
                "error_count": stats["error_count"],
                "top1_accuracy": (
                    float(stats["example_count"] - stats["error_count"]) / float(stats["example_count"])
                    if stats["example_count"]
                    else 0.0
                ),
            }
            for label, stats in sorted(by_actual.items())
        ],
        "sample_errors": sample_errors,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
