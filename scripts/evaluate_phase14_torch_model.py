from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import evaluate_phase14_torch_model


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a Phase 14 PyTorch model against a cached feature dataset.")
    parser.add_argument("--model", type=Path, default=Path("artifacts/phase14_torch_model.json"))
    parser.add_argument("--dataset", type=Path, default=Path("artifacts/phase13_reference_identity_feature_cache.json"))
    parser.add_argument("--split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase14_torch_eval.json"))
    args = parser.parse_args()

    payload = evaluate_phase14_torch_model(
        _load_json(args.model),
        _load_json(args.dataset),
        split=str(args.split),
        batch_size=int(args.batch_size),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
