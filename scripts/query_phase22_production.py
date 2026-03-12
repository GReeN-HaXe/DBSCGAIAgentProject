from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.phase22_runtime import query_phase22_production


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the promoted Phase 22 production model for top decision-class predictions.")
    parser.add_argument("--query-index", type=int, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--production-dir", type=Path, default=Path("artifacts/phase22_production"))
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase22_production/phase22_query_result.json"))
    args = parser.parse_args()

    payload = query_phase22_production(
        query_index=int(args.query_index),
        top_k=int(args.top_k),
        production_dir=args.production_dir,
        model_path=args.model,
        summary_path=args.summary,
        dataset_path=args.dataset,
        split=str(args.split),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
