from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _fmt_float(value: object) -> str:
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return "0.000000"


def _secret_auto_lines(summary: object, *, heading: str) -> list[str]:
    if not isinstance(summary, dict):
        return []
    return [
        heading,
        f"- traces_with_secret_autos: `{summary.get('trace_count_with_secret_auto_opportunities', 0)}`",
        f"- total_opportunity_count: `{summary.get('total_opportunity_count', 0)}`",
        f"- total_pending_count: `{summary.get('total_pending_count', 0)}`",
        f"- total_blocked_count: `{summary.get('total_blocked_count', 0)}`",
        f"- total_preblocked_count: `{summary.get('total_preblocked_count', 0)}`",
        f"- status_counts: `{summary.get('status_counts', {})}`",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Phase 22 closeout markdown report.")
    parser.add_argument("--best-config", type=Path, required=True, help="Phase 22 best-config JSON path.")
    parser.add_argument("--generalization-batch-eval", type=Path, required=True, help="Phase 22 generalized batch-eval JSON path.")
    parser.add_argument("--lomo-summary", type=Path, required=True, help="Phase 22 leave-one-matchup-out summary JSON path.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase22_closeout_report.md"), help="Markdown output path.")
    args = parser.parse_args()

    best_config = _load_json(args.best_config)
    generalization = _load_json(args.generalization_batch_eval)
    lomo = _load_json(args.lomo_summary)

    best = best_config.get("best", {}) if isinstance(best_config.get("best"), dict) else {}
    datasets = generalization.get("datasets", []) if isinstance(generalization.get("datasets"), list) else []
    folds = lomo.get("folds", []) if isinstance(lomo.get("folds"), list) else []

    weakest_dataset = min(
        (row for row in datasets if isinstance(row, dict)),
        key=lambda row: float(row.get("top1_accuracy", 0.0) or 0.0),
        default=None,
    )
    weakest_fold = min(
        (row for row in folds if isinstance(row, dict)),
        key=lambda row: float(row.get("top1_accuracy", 0.0) or 0.0),
        default=None,
    )

    lines = [
        "# Phase 22 Closeout",
        "",
        "## Best Config",
        f"- target_field: `{best_config.get('target_field', '')}`",
        f"- config_name: `{best.get('config_name', '')}`",
        f"- hidden_dim: `{best.get('hidden_dim', 0)}`",
        f"- epochs: `{best.get('epochs', 0)}`",
        f"- learning_rate: `{best.get('learning_rate', 0.0)}`",
        f"- manifest_path: `{best.get('manifest_path', '')}`",
        "",
        "## Generalized Batch Evaluation",
        f"- dataset_count: `{generalization.get('dataset_count', 0)}`",
        f"- overall_example_count: `{generalization.get('overall_example_count', 0)}`",
        f"- overall_top1_accuracy: `{_fmt_float(generalization.get('overall_top1_accuracy', 0.0))}`",
    ]
    lines.extend(_secret_auto_lines(generalization.get("secret_auto_summary", {}), heading="- generalized_secret_auto_summary"))
    if weakest_dataset is not None:
        lines.extend(
            [
                f"- weakest_dataset: `{weakest_dataset.get('dataset_path', '')}`",
                f"- weakest_dataset_top1: `{_fmt_float(weakest_dataset.get('top1_accuracy', 0.0))}`",
            ]
        )

    lines.extend(
        [
            "",
            "## Leave-One-Matchup-Out",
            f"- dataset_count: `{lomo.get('dataset_count', 0)}`",
            f"- overall_top1_accuracy_weighted: `{_fmt_float(lomo.get('overall_top1_accuracy_weighted', 0.0))}`",
            f"- overall_top1_accuracy_macro: `{_fmt_float(lomo.get('overall_top1_accuracy_macro', 0.0))}`",
        ]
    )
    lines.extend(_secret_auto_lines(lomo.get("holdout_secret_auto_summary", {}), heading="- lomo_holdout_secret_auto_summary"))
    if weakest_fold is not None:
        lines.extend(
            [
                f"- weakest_fold: `{weakest_fold.get('fold_name', '')}`",
                f"- weakest_fold_top1: `{_fmt_float(weakest_fold.get('top1_accuracy', 0.0))}`",
            ]
        )

    lines.extend(
        [
            "",
            "## Decision",
            "- Freeze `artifacts/phase22_generalization_v2/production` as the canonical Phase 22 model for the current benchmark scope.",
            "- Do not spend more time tuning Phase 22 on the current four AI-vs-AI matchup groups.",
            "",
            "## Recommended Next Benchmarks",
            "1. Add normalized human-vs-AI traces into the benchmark family.",
            "2. Add more deck matchup families beyond the current four.",
            "3. Add identity-enriched gameplay decision datasets when available.",
            "4. Only revisit richer state architectures after those harder benchmarks exist.",
        ]
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
