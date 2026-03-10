from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import evaluate_phase15_production


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the promoted Phase 15 production identity model.")
    parser.add_argument("--production-dir", type=Path, default=Path("artifacts/phase15_production"))
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--feature-cache", type=Path, default=None)
    parser.add_argument("--gallery-split", choices=["train", "validation", "all"], default="train")
    parser.add_argument("--query-split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--top-k", nargs="*", type=int, default=[1, 5, 10, 20])
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase15_production/phase15_production_eval.json"))
    args = parser.parse_args()

    payload = evaluate_phase15_production(
        production_dir=args.production_dir,
        model_path=args.model,
        summary_path=args.summary,
        feature_cache_path=args.feature_cache,
        gallery_split=str(args.gallery_split),
        query_split=str(args.query_split),
        top_k_values=tuple(int(value) for value in args.top_k),
        batch_size=int(args.batch_size),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
