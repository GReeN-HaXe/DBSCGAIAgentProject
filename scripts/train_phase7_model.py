from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import (
    evaluate_backoff_policy_model,
    evaluate_frequency_policy_model,
    train_backoff_policy_model,
    train_frequency_policy_model,
)


def _load_dataset(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected dataset JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a minimal Phase 7 frequency-based policy model from dataset examples.")
    parser.add_argument("--dataset", type=Path, required=True, help="Phase 7 dataset JSON path.")
    parser.add_argument("--model-type", choices=["frequency", "backoff"], default="frequency", help="Model family to train.")
    parser.add_argument("--target-field", choices=["action_type", "action_family"], default="action_type", help="Target label to train.")
    parser.add_argument("--train-split", choices=["train", "validation", "all"], default="train", help="Dataset split used for fitting.")
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation", help="Dataset split used for immediate evaluation.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase7_frequency_model.json"), help="Model output path.")
    parser.add_argument("--eval-output", type=Path, default=None, help="Optional evaluation output path.")
    args = parser.parse_args()

    dataset = _load_dataset(args.dataset)
    if args.model_type == "backoff":
        model = train_backoff_policy_model(
            dataset,
            split=str(args.train_split),
            target_field=str(args.target_field),
        )
    else:
        model = train_frequency_policy_model(
            dataset,
            split=str(args.train_split),
            target_field=str(args.target_field),
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")

    if args.eval_output is not None:
        if args.model_type == "backoff":
            payload = evaluate_backoff_policy_model(dataset, model, split=str(args.eval_split))
        else:
            payload = evaluate_frequency_policy_model(dataset, model, split=str(args.eval_split))
        args.eval_output.parent.mkdir(parents=True, exist_ok=True)
        args.eval_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote: {args.eval_output}")


if __name__ == "__main__":
    main()
