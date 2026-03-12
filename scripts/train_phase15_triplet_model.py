from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import train_phase15_triplet_model


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a Phase 15 explicit triplet embedding model.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--split", choices=["train", "validation", "all"], default="train")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--steps-per-epoch", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--hidden-dim", type=int, default=256)
    parser.add_argument("--embedding-dim", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=5e-4)
    parser.add_argument("--margin", type=float, default=0.2)
    parser.add_argument("--negative-mining", choices=["random", "hard"], default="random")
    parser.add_argument("--negative-pool-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--progress-every", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase15_triplet_model.json"))
    args = parser.parse_args()

    payload = train_phase15_triplet_model(
        _load_json(args.dataset),
        split=str(args.split),
        epochs=int(args.epochs),
        steps_per_epoch=int(args.steps_per_epoch),
        batch_size=int(args.batch_size),
        hidden_dim=int(args.hidden_dim),
        embedding_dim=int(args.embedding_dim),
        learning_rate=float(args.learning_rate),
        margin=float(args.margin),
        negative_mining=str(args.negative_mining),
        negative_pool_size=int(args.negative_pool_size),
        seed=int(args.seed),
        device=str(args.device),
        progress_every=int(args.progress_every),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
