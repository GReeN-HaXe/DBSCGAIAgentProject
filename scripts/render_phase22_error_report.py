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
    parser = argparse.ArgumentParser(description="Render a Markdown report for Phase 22 error analysis.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = _load_json(args.input)
    lines = [
        "# Phase 22 Error Analysis",
        "",
        f"- dataset_path: `{payload.get('dataset_path', '')}`",
        f"- split: `{payload.get('split', '')}`",
        f"- example_count: `{payload.get('example_count', 0)}`",
        f"- top1_accuracy: `{payload.get('top1_accuracy', 0.0)}`",
        f"- top_k_accuracy: `{payload.get('top_k_accuracy', {})}`",
        f"- error_count: `{payload.get('error_count', 0)}`",
        "",
    ]

    top_confusions = payload.get("top_confusions", [])
    if isinstance(top_confusions, list) and top_confusions:
        lines.extend(["## Top Confusions", ""])
        for row in top_confusions[:10]:
            if not isinstance(row, dict):
                continue
            lines.append(f"- `{row.get('pair', '')}`: `{row.get('count', 0)}`")
        lines.append("")

    per_source = payload.get("per_source", [])
    if isinstance(per_source, list) and per_source:
        lines.extend(["## Per Source", ""])
        for row in per_source[:20]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- `{row.get('source_name', '')}`: top1=`{row.get('top1_accuracy', 0.0)}` "
                f"errors=`{row.get('error_count', 0)}` examples=`{row.get('example_count', 0)}`"
            )
        lines.append("")

    per_label = payload.get("per_actual_label", [])
    if isinstance(per_label, list) and per_label:
        lines.extend(["## Per Decision Class", ""])
        for row in per_label[:20]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- `{row.get('label', '')}`: top1=`{row.get('top1_accuracy', 0.0)}` "
                f"errors=`{row.get('error_count', 0)}` examples=`{row.get('example_count', 0)}`"
            )
        lines.append("")

    sample_errors = payload.get("sample_errors", [])
    if isinstance(sample_errors, list) and sample_errors:
        lines.extend(["## Sample Errors", ""])
        for row in sample_errors[:10]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- `{row.get('source_name', '')}` idx=`{row.get('example_index', '')}` "
                f"`{row.get('actual_label', '')}` -> `{row.get('predicted_label', '')}` "
                f"action=`{row.get('action_signature', '')}`"
            )
        lines.append("")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
