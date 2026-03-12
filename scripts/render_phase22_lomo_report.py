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
    parser = argparse.ArgumentParser(description="Render a markdown report for Phase 22 leave-one-matchup-out evaluation.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = _load_json(args.input)
    folds = payload.get("folds", [])
    if not isinstance(folds, list):
        folds = []

    lines = [
        "# Phase 22 LOMO Report",
        "",
        f"- target field: `{payload.get('target_field', '')}`",
        f"- dataset count: `{payload.get('dataset_count', 0)}`",
        f"- overall example count: `{payload.get('overall_example_count', 0)}`",
        f"- weighted top1: `{payload.get('overall_top1_accuracy_weighted', 0.0):.6f}`",
        f"- macro top1: `{payload.get('overall_top1_accuracy_macro', 0.0):.6f}`",
        "",
        "## Folds",
        "",
        "| Fold | Examples | Top1 | Top3 | Top5 | Holdout |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in folds:
        if not isinstance(row, dict):
            continue
        top_k = row.get("top_k_accuracy", {})
        if not isinstance(top_k, dict):
            top_k = {}
        holdout = str(row.get("holdout_dataset", ""))
        lines.append(
            f"| {row.get('fold_name', '')} | {int(row.get('example_count', 0) or 0)} | "
            f"{float(row.get('top1_accuracy', 0.0) or 0.0):.6f} | "
            f"{float(top_k.get('3', 0.0) or 0.0):.6f} | "
            f"{float(top_k.get('5', 0.0) or 0.0):.6f} | `{holdout}` |"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
