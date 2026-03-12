from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import benchmark_detection_manifest


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark a Phase 10 detection manifest against a labeled reference manifest.")
    parser.add_argument("--predicted", type=Path, required=True, help="Predicted detection manifest JSON path.")
    parser.add_argument("--labeled", type=Path, required=True, help="Labeled/reference detection manifest JSON path.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase10_benchmark.json"), help="Benchmark output path.")
    args = parser.parse_args()

    payload = benchmark_detection_manifest(_load_json(args.predicted), _load_json(args.labeled))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
