from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import evaluate_phase18_resnet18_triplet_retrieval


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Phase 18 ResNet18 triplet retrieval.")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--gallery-split", type=str, default="train")
    parser.add_argument("--query-split", type=str, default="validation")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-gallery-examples", type=int, default=0)
    parser.add_argument("--max-query-examples", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = evaluate_phase18_resnet18_triplet_retrieval(
        _load_json(args.model),
        _load_json(args.dataset),
        gallery_split=str(args.gallery_split),
        query_split=str(args.query_split),
        batch_size=int(args.batch_size),
        max_gallery_examples=int(args.max_gallery_examples),
        max_query_examples=int(args.max_query_examples),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
