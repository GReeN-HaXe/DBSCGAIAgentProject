from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import train_phase16_cnn_model


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a Phase 16 CNN model on real reference images.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--split", choices=["train", "validation", "all"], default="train")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--image-size", type=int, default=32)
    parser.add_argument("--embedding-dim", type=int, default=128)
    parser.add_argument("--max-examples", type=int, default=0)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--progress-every", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase16_cnn_model.json"))
    args = parser.parse_args()

    payload = train_phase16_cnn_model(
        _load_json(args.dataset),
        split=str(args.split),
        epochs=int(args.epochs),
        batch_size=int(args.batch_size),
        learning_rate=float(args.learning_rate),
        image_size=int(args.image_size),
        embedding_dim=int(args.embedding_dim),
        max_examples=int(args.max_examples),
        seed=int(args.seed),
        device=str(args.device),
        progress_every=int(args.progress_every),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
