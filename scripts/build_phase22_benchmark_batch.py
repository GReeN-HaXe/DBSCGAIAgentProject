from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_phase22_benchmark_dataset import (
    _convert_to_phase7_compatible_artifact,
    _load_json,
    _trace_stats,
)
from src.agent.dataset import build_phase7_dataset


def _parse_group(value: str) -> tuple[str, str]:
    text = str(value).strip()
    if "=" not in text:
        raise ValueError(f"invalid --group value {value!r}; expected name=glob")
    name, pattern = text.split("=", 1)
    name = name.strip()
    pattern = pattern.strip()
    if not name or not pattern:
        raise ValueError(f"invalid --group value {value!r}; expected name=glob")
    return name, pattern


def _collect_paths(pattern: str) -> list[Path]:
    matches = sorted(Path().glob(pattern))
    return [path for path in matches if path.is_file()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build multiple Phase 22 benchmark datasets from trace groups in one run.")
    parser.add_argument(
        "--group",
        action="append",
        required=True,
        help="Dataset group in the form name=glob_pattern. Repeat for multiple datasets.",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for generated benchmark datasets.")
    parser.add_argument("--summary-output", type=Path, default=None, help="Optional batch summary JSON path.")
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    parser.add_argument("--min-actions", type=int, default=2)
    parser.add_argument("--min-unique-action-types", type=int, default=2)
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_rows: list[dict[str, Any]] = []
    for raw_group in args.group:
        group_name, pattern = _parse_group(raw_group)
        paths = _collect_paths(pattern)
        artifacts: list[dict[str, object]] = []
        source_names: list[str] = []
        included: list[dict[str, object]] = []
        skipped: list[dict[str, object]] = []
        for path in paths:
            payload = _load_json(path)
            stats = _trace_stats(payload)
            row = {"path": str(path), **stats}
            if int(stats["action_count"]) < int(args.min_actions) or int(stats["unique_action_type_count"]) < int(args.min_unique_action_types):
                skipped.append(row)
                continue
            artifacts.append(_convert_to_phase7_compatible_artifact(payload))
            source_names.append(str(path))
            included.append(row)

        if not artifacts:
            dataset_rows.append(
                {
                    "group_name": group_name,
                    "pattern": pattern,
                    "input_count": len(paths),
                    "included_count": 0,
                    "skipped_count": len(skipped),
                    "dataset_path": "",
                    "summary_path": "",
                    "dataset_example_count": 0,
                }
            )
            continue

        dataset = build_phase7_dataset(
            artifacts,
            source_names=source_names,
            validation_ratio=float(args.validation_ratio),
        )
        dataset_path = output_dir / f"{group_name}.json"
        summary_path = output_dir / f"{group_name}_summary.json"
        dataset_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
        summary_payload = {
            "schema_version": "phase22.benchmark_dataset_summary.v1",
            "group_name": group_name,
            "pattern": pattern,
            "input_count": len(paths),
            "included_count": len(included),
            "skipped_count": len(skipped),
            "included_traces": included,
            "skipped_traces": skipped,
            "dataset_example_count": int(dataset.get("example_count", 0) or 0),
            "dataset_split_counts": dict(dataset.get("split_counts", {})) if isinstance(dataset.get("split_counts"), dict) else {},
        }
        summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
        print(f"wrote: {dataset_path}")
        print(f"wrote: {summary_path}")
        dataset_rows.append(
            {
                "group_name": group_name,
                "pattern": pattern,
                "input_count": len(paths),
                "included_count": len(included),
                "skipped_count": len(skipped),
                "dataset_path": str(dataset_path),
                "summary_path": str(summary_path),
                "dataset_example_count": int(dataset.get("example_count", 0) or 0),
            }
        )

    if args.summary_output is not None:
        batch_summary = {
            "schema_version": "phase22.benchmark_batch.v1",
            "dataset_count": len(dataset_rows),
            "datasets": dataset_rows,
            "min_actions": int(args.min_actions),
            "min_unique_action_types": int(args.min_unique_action_types),
            "validation_ratio": float(args.validation_ratio),
        }
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(batch_summary, indent=2), encoding="utf-8")
        print(f"wrote: {args.summary_output}")


if __name__ == "__main__":
    main()
