from __future__ import annotations

import argparse
import json
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


def _per_source_metrics(dataset: dict[str, Any], evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    rows = evaluation.get("rows", [])
    if not isinstance(rows, list):
        return []
    grouped: dict[str, dict[str, int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_name = str(row.get("source_name", "unknown"))
        bucket = grouped.setdefault(source_name, {"example_count": 0, "matched_count": 0})
        bucket["example_count"] += 1
        bucket["matched_count"] += 1 if bool(row.get("matched")) else 0
    ranked = []
    for source_name, counts in grouped.items():
        total = int(counts["example_count"])
        matched = int(counts["matched_count"])
        ranked.append(
            {
                "source_name": source_name,
                "example_count": total,
                "top1_accuracy": (float(matched) / float(total)) if total else 0.0,
            }
        )
    return sorted(ranked, key=lambda item: (-float(item["top1_accuracy"]), item["source_name"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-evaluate the promoted Phase 22 production model across datasets.")
    parser.add_argument("--dataset", nargs="+", type=Path, required=True)
    parser.add_argument("--production-dir", type=Path, default=Path("artifacts/phase22_production"))
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--top-k", nargs="*", type=int, default=[1, 3, 5])
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase22_production/phase22_batch_eval.json"))
    args = parser.parse_args()

    dataset_rows: list[dict[str, Any]] = []
    for dataset_path in args.dataset:
        dataset = _load_json(dataset_path)
        evaluation = evaluate_phase22_production(
            production_dir=args.production_dir,
            model_path=args.model,
            summary_path=args.summary,
            dataset_path=dataset_path,
            split=str(args.split),
            batch_size=int(args.batch_size),
            top_k_values=tuple(int(value) for value in args.top_k),
        )
        dataset_rows.append(
            {
                "dataset_path": str(dataset_path.resolve()),
                "example_count": int(evaluation.get("example_count", 0) or 0),
                "top1_accuracy": float(evaluation.get("top1_accuracy", 0.0) or 0.0),
                "top_k_accuracy": dict(evaluation.get("top_k_accuracy", {}))
                if isinstance(evaluation.get("top_k_accuracy"), dict)
                else {},
                "identity_resolved_example_rate": float(evaluation.get("identity_resolved_example_rate", 0.0) or 0.0),
                "per_source": _per_source_metrics(dataset, evaluation),
            }
        )

    overall_example_count = sum(int(row["example_count"]) for row in dataset_rows)
    overall_top1 = (
        sum(float(row["top1_accuracy"]) * int(row["example_count"]) for row in dataset_rows) / float(overall_example_count)
        if overall_example_count
        else 0.0
    )
    payload = {
        "schema_version": "phase22.batch_eval.v1",
        "production_dir": str(args.production_dir.resolve()),
        "split": str(args.split),
        "dataset_count": len(dataset_rows),
        "overall_example_count": overall_example_count,
        "overall_top1_accuracy": overall_top1,
        "datasets": dataset_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
