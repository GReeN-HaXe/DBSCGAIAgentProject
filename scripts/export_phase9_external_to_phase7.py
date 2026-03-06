from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import build_phase7_dataset, external_match_to_phase7_trace_artifact


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert reviewed Phase 9 external matches into a Phase 7-compatible dataset.")
    parser.add_argument("--input", type=Path, nargs="+", required=True, help="One or more reviewed Phase 9 external match JSON files.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase9_external_phase7_dataset.json"), help="Output dataset path.")
    parser.add_argument("--validation-ratio", type=float, default=0.2, help="Validation split ratio for exported dataset.")
    args = parser.parse_args()

    artifacts = [external_match_to_phase7_trace_artifact(_load_json(path)) for path in args.input]
    dataset = build_phase7_dataset(
        artifacts,
        source_names=[str(path) for path in args.input],
        validation_ratio=float(args.validation_ratio),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
