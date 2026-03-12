from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def _render_top_rows(eval_payload: dict[str, object], *, limit: int = 10) -> list[str]:
    rows = eval_payload.get("rows", [])
    if not isinstance(rows, list):
        return []
    lines: list[str] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        expected = str(row.get("expected_signature", ""))
        predicted = str(row.get("predicted_signature", ""))
        confidence = float(row.get("confidence", 0.0) or 0.0)
        top_predictions = row.get("top_predictions", [])
        top_preview = ", ".join(str(item.get("signature", "")) for item in top_predictions[:3] if isinstance(item, dict))
        lines.append(f"| {expected} | {predicted} | {confidence:.4f} | {top_preview} |")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a compact Phase 13 card-identity markdown report.")
    parser.add_argument("--manifest", type=Path, required=True, help="Reference identity manifest JSON path.")
    parser.add_argument("--evaluation", type=Path, required=True, help="Reference identity evaluation JSON path.")
    parser.add_argument("--ablation-summary", type=Path, default=None, help="Optional identity ablation summary JSON path.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase13_identity_report.md"), help="Markdown output path.")
    args = parser.parse_args()

    manifest = _load_json(args.manifest)
    evaluation = _load_json(args.evaluation)
    ablation = _load_json(args.ablation_summary) if args.ablation_summary is not None and args.ablation_summary.exists() else None

    lines = [
        "# Phase 13 Identity Report",
        "",
        "## Summary",
        f"- Run: `{manifest.get('run_name', '')}`",
        f"- Target type: `{manifest.get('metrics', {}).get('target_type', '')}`",
        f"- Split: `{manifest.get('metrics', {}).get('split', '')}`",
        f"- Top-1 accuracy: `{manifest.get('metrics', {}).get('top1_accuracy', 0.0)}`",
        f"- Top-5 accuracy: `{manifest.get('metrics', {}).get('top5_accuracy', 0.0)}`",
        f"- Top-10 accuracy: `{manifest.get('metrics', {}).get('top10_accuracy', 0.0)}`",
        "",
        "## Sample Predictions",
        "| Expected | Predicted | Confidence | Top-3 Preview |",
        "| --- | --- | ---: | --- |",
    ]
    lines.extend(_render_top_rows(evaluation))
    if ablation is not None:
        best = ablation.get("best", {})
        lines.extend(
            [
                "",
                "## Ablation",
                f"- Best config: `{best.get('config_name', '')}`",
                f"- Best top-1: `{best.get('top1_accuracy', 0.0)}`",
                f"- Best top-5: `{best.get('top5_accuracy', 0.0)}`",
                f"- Best top-10: `{best.get('top10_accuracy', 0.0)}`",
            ]
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
