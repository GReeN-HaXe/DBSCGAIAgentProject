from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import evaluate_phase13_identity_model


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a Phase 13 card-identity model against a card-identity dataset.")
    parser.add_argument("--model", type=Path, required=True, help="Phase 13 model JSON path.")
    parser.add_argument("--dataset", type=Path, required=True, help="Phase 13 reference-image dataset JSON path.")
    parser.add_argument("--split", choices=["train", "validation", "all"], default="validation", help="Evaluation split.")
    parser.add_argument("--progress-every", type=int, default=50, help="Print progress every N examples. Use 0 to disable.")
    parser.add_argument("--top-k", type=int, nargs="*", default=[1, 5, 10], help="Top-k cutoffs to report.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase13_identity_eval.json"), help="Evaluation output path.")
    args = parser.parse_args()

    payload = evaluate_phase13_identity_model(
        model=_load_json(args.model),
        crop_dataset=_load_json(args.dataset),
        split=str(args.split),
        progress_every=int(args.progress_every),
        top_k_values=[int(value) for value in args.top_k],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
