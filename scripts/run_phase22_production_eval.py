from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.phase22_runtime import evaluate_phase22_production


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the promoted Phase 22 production state encoder.")
    parser.add_argument("--production-dir", type=Path, default=Path("artifacts/phase22_production"))
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--top-k", nargs="*", type=int, default=[1, 3, 5])
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase22_production/phase22_production_eval.json"))
    args = parser.parse_args()

    payload = evaluate_phase22_production(
        production_dir=args.production_dir,
        model_path=args.model,
        summary_path=args.summary,
        dataset_path=args.dataset,
        split=str(args.split),
        batch_size=int(args.batch_size),
        top_k_values=tuple(int(value) for value in args.top_k),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
