from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import slice_phase7_dataset


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "slice"


def main() -> None:
    parser = argparse.ArgumentParser(description="Slice a Phase 7 dataset into archetype-like subsets by a nested field.")
    parser.add_argument("--dataset", type=Path, required=True, help="Phase 7 dataset JSON path.")
    parser.add_argument("--slice-field", type=str, default="setup.profile_pair", help="Nested field path used for slicing.")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/phase8_dataset_slices"), help="Output directory for sliced datasets.")
    args = parser.parse_args()

    slices = slice_phase7_dataset(_load_json(args.dataset), slice_field=str(args.slice_field))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "slice_field": str(args.slice_field),
        "slice_count": len(slices),
        "slices": [],
    }
    for key, payload in sorted(slices.items()):
        path = args.output_dir / f"{_safe_name(key)}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        manifest["slices"].append({"slice_value": key, "example_count": payload.get("example_count", 0), "path": str(path)})
        print(f"wrote: {path}")
    manifest_path = args.output_dir / "slice_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote: {manifest_path}")


if __name__ == "__main__":
    main()
