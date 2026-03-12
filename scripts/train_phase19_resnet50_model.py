from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import train_phase19_resnet50_model


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a Phase 19 ResNet50 classifier model.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--split", type=str, default="train")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--image-size", type=int, default=96)
    parser.add_argument("--max-examples", type=int, default=0)
    parser.add_argument("--weights-mode", choices=["default", "none"], default="default")
    parser.add_argument("--freeze-backbone-epochs", type=int, default=0)
    parser.add_argument("--progress-every", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = train_phase19_resnet50_model(
        _load_json(args.dataset),
        split=str(args.split),
        epochs=int(args.epochs),
        batch_size=int(args.batch_size),
        learning_rate=float(args.learning_rate),
        image_size=int(args.image_size),
        max_examples=int(args.max_examples),
        weights_mode=str(args.weights_mode),
        freeze_backbone_epochs=int(args.freeze_backbone_epochs),
        progress_every=int(args.progress_every),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
