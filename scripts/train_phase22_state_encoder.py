from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.phase22_state_encoder import (
    evaluate_phase22_state_encoder,
    summarize_phase22_target_distribution,
    train_phase22_state_encoder,
)


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a Phase 22 structured-state encoder.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--train-split", choices=["train", "validation", "all"], default="train")
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--target-field", choices=["action_type", "action_family", "action_signature", "decision_class"], default="action_signature")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--embedding-dim", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--progress-every", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--eval-output", type=Path, default=None)
    args = parser.parse_args()

    dataset = _load_json(args.dataset)
    distribution = summarize_phase22_target_distribution(
        dataset,
        target_field=str(args.target_field),
        split=str(args.train_split),
    )
    if int(distribution.get("label_count", 0) or 0) < 2:
        raise ValueError(
            "need at least 2 classes to train a Phase 22 state encoder; "
            f"target_field={args.target_field} split={args.train_split} "
            f"label_count={distribution.get('label_count')} labels={distribution.get('labels')}"
        )
    model = train_phase22_state_encoder(
        dataset,
        split=str(args.train_split),
        target_field=str(args.target_field),
        epochs=int(args.epochs),
        batch_size=int(args.batch_size),
        hidden_dim=int(args.hidden_dim),
        embedding_dim=int(args.embedding_dim),
        learning_rate=float(args.learning_rate),
        device=str(args.device),
        progress_every=int(args.progress_every),
    )
    args.output.write_text(json.dumps(model, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")
    if args.eval_output is not None:
        evaluation = evaluate_phase22_state_encoder(
            model,
            dataset,
            split=str(args.eval_split),
            batch_size=int(args.batch_size),
            device=str(args.device),
        )
        args.eval_output.write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
        print(f"wrote: {args.eval_output}")


if __name__ == "__main__":
    main()
