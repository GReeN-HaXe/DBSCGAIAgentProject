from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge multiple Phase 22 benchmark datasets into one generalized training dataset.")
    parser.add_argument("--input", nargs="+", type=Path, required=True, help="Phase 22 benchmark dataset JSON paths.")
    parser.add_argument("--output", type=Path, required=True, help="Merged dataset JSON path.")
    parser.add_argument("--summary-output", type=Path, default=None, help="Optional merge summary JSON path.")
    args = parser.parse_args()

    merged_examples: list[dict[str, Any]] = []
    merged_trajectories: list[dict[str, Any]] = []
    merged_sources: list[str] = []
    split_counts = {"train": 0, "validation": 0}
    input_rows: list[dict[str, Any]] = []

    for dataset_path in args.input:
        payload = _load_json(dataset_path)
        examples = payload.get("examples", [])
        trajectories = payload.get("trajectories", [])
        sources = payload.get("sources", [])
        if not isinstance(examples, list):
            examples = []
        if not isinstance(trajectories, list):
            trajectories = []
        if not isinstance(sources, list):
            sources = []

        example_rows = [row for row in examples if isinstance(row, dict)]
        trajectory_rows = [row for row in trajectories if isinstance(row, dict)]
        source_rows = [str(row) for row in sources]

        merged_examples.extend(example_rows)
        merged_trajectories.extend(trajectory_rows)
        merged_sources.extend(source_rows)
        split_counts["train"] += sum(1 for row in example_rows if row.get("split") == "train")
        split_counts["validation"] += sum(1 for row in example_rows if row.get("split") == "validation")
        input_rows.append(
            {
                "dataset_path": str(dataset_path.resolve()),
                "example_count": len(example_rows),
                "trajectory_count": len(trajectory_rows),
                "source_count": len(source_rows),
            }
        )

    merged_payload = {
        "schema_version": "phase7.v1",
        "example_count": len(merged_examples),
        "trajectory_count": len(merged_trajectories),
        "validation_ratio": None,
        "sources": sorted(dict.fromkeys(merged_sources)),
        "split_counts": split_counts,
        "trajectories": merged_trajectories,
        "examples": merged_examples,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(merged_payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")

    if args.summary_output is not None:
        summary = {
            "schema_version": "phase22.merged_benchmark_summary.v1",
            "input_count": len(args.input),
            "inputs": input_rows,
            "merged_example_count": len(merged_examples),
            "merged_trajectory_count": len(merged_trajectories),
            "merged_source_count": len(merged_payload["sources"]),
            "split_counts": split_counts,
        }
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"wrote: {args.summary_output}")


if __name__ == "__main__":
    main()
