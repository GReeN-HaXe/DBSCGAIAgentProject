from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import build_phase7_dataset


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Phase 7 training examples from Phase 6 trace artifacts.")
    parser.add_argument("--input", type=Path, nargs="+", required=True, help="One or more Phase 6 trace/replay JSON files.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase7_dataset.json"),
        help="Dataset output path. Uses JSON or JSONL based on --format.",
    )
    parser.add_argument("--format", choices=["json", "jsonl"], default="json", help="Output serialization format.")
    parser.add_argument(
        "--validation-ratio",
        type=float,
        default=0.2,
        help="Deterministic fraction of examples assigned to the validation split.",
    )
    args = parser.parse_args()

    artifacts = [_load_json(path) for path in args.input]
    dataset = build_phase7_dataset(
        artifacts,
        source_names=[str(path) for path in args.input],
        validation_ratio=float(args.validation_ratio),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.format == "jsonl":
        lines = [json.dumps(row, sort_keys=True) for row in dataset["examples"]]
        args.output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    else:
        args.output.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
