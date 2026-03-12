from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Markdown report from a Phase 22 batch evaluation artifact.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = _load_json(args.input)
    lines = [
        "# Phase 22 Batch Evaluation",
        "",
        f"- split: `{payload.get('split', '')}`",
        f"- dataset_count: `{payload.get('dataset_count', 0)}`",
        f"- overall_example_count: `{payload.get('overall_example_count', 0)}`",
        f"- overall_top1_accuracy: `{payload.get('overall_top1_accuracy', 0.0)}`",
        "",
    ]
    datasets = payload.get("datasets", [])
    if isinstance(datasets, list) and datasets:
        lines.extend(["## Datasets", ""])
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            lines.extend(
                [
                    f"### `{dataset.get('dataset_path', '')}`",
                    "",
                    f"- example_count: `{dataset.get('example_count', 0)}`",
                    f"- top1_accuracy: `{dataset.get('top1_accuracy', 0.0)}`",
                    f"- top_k_accuracy: `{dataset.get('top_k_accuracy', {})}`",
                    f"- identity_resolved_example_rate: `{dataset.get('identity_resolved_example_rate', 0.0)}`",
                    "",
                ]
            )
            per_source = dataset.get("per_source", [])
            if isinstance(per_source, list) and per_source:
                lines.extend(["Per-source:", ""])
                for row in per_source[:10]:
                    if not isinstance(row, dict):
                        continue
                    lines.append(
                        f"- `{row.get('source_name', '')}`: top1=`{row.get('top1_accuracy', 0.0)}` "
                        f"examples=`{row.get('example_count', 0)}`"
                    )
                lines.append("")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
