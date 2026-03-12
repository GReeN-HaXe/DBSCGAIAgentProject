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
    parser = argparse.ArgumentParser(description="Render a Phase 14 embedding retrieval markdown report.")
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase14_embedding_report.md"))
    args = parser.parse_args()

    retrieval = _load_json(args.retrieval)
    recall = retrieval.get("recall_at_k", {})
    if not isinstance(recall, dict):
        recall = {}
    lines = [
        "# Phase 14 Embedding Retrieval Report",
        "",
        "## Summary",
        f"- Model: `{retrieval.get('model_name', '')}`",
        f"- Target type: `{retrieval.get('target_type', '')}`",
        f"- Gallery split: `{retrieval.get('gallery_split', '')}`",
        f"- Query split: `{retrieval.get('query_split', '')}`",
        f"- Example count: `{retrieval.get('example_count', 0)}`",
        f"- Mean reciprocal rank: `{retrieval.get('mean_reciprocal_rank', 0.0)}`",
        f"- Mean found rank: `{retrieval.get('mean_found_rank', 0.0)}`",
        "",
        "## Recall@K",
    ]
    for key, value in sorted(recall.items(), key=lambda item: int(item[0])):
        lines.append(f"- Recall@{key}: `{value}`")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
