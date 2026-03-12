from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import evaluate_phase17_resnet18_retrieval


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Phase 17 ResNet18 retrieval.")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--gallery-split", choices=["train", "validation", "all"], default="train")
    parser.add_argument("--query-split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--top-k", nargs="*", type=int, default=[1, 5, 10, 20])
    parser.add_argument("--max-gallery-examples", type=int, default=0)
    parser.add_argument("--max-query-examples", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase17_resnet18_retrieval.json"))
    args = parser.parse_args()

    payload = evaluate_phase17_resnet18_retrieval(
        _load_json(args.model),
        _load_json(args.dataset),
        gallery_split=str(args.gallery_split),
        query_split=str(args.query_split),
        batch_size=int(args.batch_size),
        top_k_values=args.top_k,
        max_gallery_examples=int(args.max_gallery_examples),
        max_query_examples=int(args.max_query_examples),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
