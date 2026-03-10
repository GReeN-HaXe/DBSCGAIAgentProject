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
    parser = argparse.ArgumentParser(description="Render a Phase 14 embedding sweep markdown report.")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase14_embedding_sweep_report.md"))
    args = parser.parse_args()

    summary = _load_json(args.summary)
    best = summary.get("best", {})
    if not isinstance(best, dict):
        best = {}
    ranking = summary.get("ranking", [])
    if not isinstance(ranking, list):
        ranking = []

    lines = [
        "# Phase 14 Embedding Sweep Report",
        "",
        "## Summary",
        f"- Profile: `{summary.get('profile', '')}`",
        f"- Gallery split: `{summary.get('gallery_split', '')}`",
        f"- Query split: `{summary.get('query_split', '')}`",
        f"- Config count: `{summary.get('config_count', 0)}`",
        f"- Best config: `{best.get('config_name', '')}`",
        f"- Best MRR: `{best.get('mean_reciprocal_rank', 0.0)}`",
        f"- Best recall@1: `{best.get('recall_at_1', 0.0)}`",
        f"- Best recall@5: `{best.get('recall_at_5', 0.0)}`",
        f"- Best recall@10: `{best.get('recall_at_10', 0.0)}`",
        "",
        "## Ranking",
        "| Config | Hidden | Epochs | LR | MRR | R@1 | R@5 | R@10 | Duration(s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in ranking:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| {config} | {hidden} | {epochs} | {lr} | {mrr:.6f} | {r1:.6f} | {r5:.6f} | {r10:.6f} | {duration:.2f} |".format(
                config=str(row.get("config_name", "")),
                hidden=int(row.get("hidden_dim", 0) or 0),
                epochs=int(row.get("epochs", 0) or 0),
                lr=float(row.get("learning_rate", 0.0) or 0.0),
                mrr=float(row.get("mean_reciprocal_rank", 0.0) or 0.0),
                r1=float(row.get("recall_at_1", 0.0) or 0.0),
                r5=float(row.get("recall_at_5", 0.0) or 0.0),
                r10=float(row.get("recall_at_10", 0.0) or 0.0),
                duration=float(row.get("duration_seconds", 0.0) or 0.0),
            )
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
