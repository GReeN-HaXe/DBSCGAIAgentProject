from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import query_phase15_production


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the promoted Phase 15 production model for top identity matches.")
    parser.add_argument("--query-index", type=int, required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--production-dir", type=Path, default=Path("artifacts/phase15_production"))
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--feature-cache", type=Path, default=None)
    parser.add_argument("--gallery-split", choices=["train", "validation", "all"], default="train")
    parser.add_argument("--query-split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase15_production/phase15_query_result.json"))
    args = parser.parse_args()

    payload = query_phase15_production(
        query_index=int(args.query_index),
        top_k=int(args.top_k),
        production_dir=args.production_dir,
        model_path=args.model,
        summary_path=args.summary,
        feature_cache_path=args.feature_cache,
        gallery_split=str(args.gallery_split),
        query_split=str(args.query_split),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
