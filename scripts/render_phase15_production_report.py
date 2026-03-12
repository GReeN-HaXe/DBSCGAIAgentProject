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
    parser = argparse.ArgumentParser(description="Render a Markdown report for the promoted Phase 15 production artifact set.")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    summary = _load_json(args.summary.resolve())
    training = summary.get("training", {})
    if not isinstance(training, dict):
        training = {}
    compare = summary.get("phase14_comparison", {})
    if not isinstance(compare, dict):
        compare = {}
    report = "\n".join(
        [
            "# Phase 15 Production Report",
            "",
            f"- Run: `{summary.get('run_name', '')}`",
            f"- Target: `{summary.get('target_type', '')}`",
            f"- Gallery split: `{summary.get('gallery_split', '')}`",
            f"- Query split: `{summary.get('query_split', '')}`",
            f"- Example count: `{summary.get('example_count', 0)}`",
            "",
            "## Retrieval Metrics",
            f"- MRR: `{summary.get('mean_reciprocal_rank', 0.0)}`",
            f"- Mean found rank: `{summary.get('mean_found_rank', 0.0)}`",
            f"- Recall@1: `{summary.get('recall_at_1', 0.0)}`",
            f"- Recall@5: `{summary.get('recall_at_5', 0.0)}`",
            f"- Recall@10: `{summary.get('recall_at_10', 0.0)}`",
            f"- Recall@20: `{summary.get('recall_at_20', 0.0)}`",
            "",
            "## Training Config",
            f"- Epochs: `{training.get('epochs', 0)}`",
            f"- Steps/epoch: `{training.get('steps_per_epoch', 0)}`",
            f"- Batch size: `{training.get('batch_size', 0)}`",
            f"- Hidden dim: `{training.get('hidden_dim', 0)}`",
            f"- Embedding dim: `{training.get('embedding_dim', 0)}`",
            f"- Learning rate: `{training.get('learning_rate', 0.0)}`",
            f"- Margin: `{training.get('margin', 0.0)}`",
            f"- Negative mining: `{training.get('negative_mining', '')}`",
            "",
            "## Phase 14 Comparison",
            f"- MRR lift: `{compare.get('mrr_lift', 0.0)}`",
            f"- Recall@1 lift: `{compare.get('recall_at_1_lift', 0.0)}`",
            f"- Recall@5 lift: `{compare.get('recall_at_5_lift', 0.0)}`",
            f"- Recall@10 lift: `{compare.get('recall_at_10_lift', 0.0)}`",
            f"- Phase 15 wins: `{compare.get('phase15_wins', False)}`",
            "",
            "## Status",
            "- Promoted for production: `true`",
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report + "\n", encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
