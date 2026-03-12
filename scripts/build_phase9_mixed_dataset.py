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
    parser = argparse.ArgumentParser(description="Build a mixed Phase 7 dataset from self-play traces and reviewed external matches.")
    parser.add_argument("--self-play-input", type=Path, nargs="*", default=[], help="Existing Phase 7/trace JSON files.")
    parser.add_argument("--external-input", type=Path, nargs="*", default=[], help="Reviewed Phase 9 external match JSON files.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase9_mixed_phase7_dataset.json"), help="Output dataset path.")
    parser.add_argument("--validation-ratio", type=float, default=0.2, help="Validation split ratio for exported dataset.")
    args = parser.parse_args()

    artifacts: list[dict[str, object]] = []
    source_names: list[str] = []
    existing_examples: list[dict[str, object]] = []
    existing_trajectories: list[dict[str, object]] = []
    existing_sources: list[str] = []
    for path in args.self_play_input:
        payload = _load_json(path)
        if str(payload.get("schema_version", "")) == "phase7.v1" and isinstance(payload.get("examples"), list):
            existing_examples.extend(dict(row) for row in payload.get("examples", []) if isinstance(row, dict))
            existing_trajectories.extend(dict(row) for row in payload.get("trajectories", []) if isinstance(row, dict))
            if isinstance(payload.get("sources"), list):
                existing_sources.extend(str(item) for item in payload.get("sources", []))
            else:
                existing_sources.append(str(path))
        else:
            artifacts.append(payload)
            source_names.append(str(path))
    for path in args.external_input:
        artifacts.append(external_match_to_phase7_trace_artifact(_load_json(path)))
        source_names.append(str(path))
    dataset = build_phase7_dataset(artifacts, source_names=source_names, validation_ratio=float(args.validation_ratio)) if artifacts else {
        "schema_version": "phase7.v1",
        "example_count": 0,
        "trajectory_count": 0,
        "validation_ratio": float(args.validation_ratio),
        "sources": [],
        "split_counts": {"train": 0, "validation": 0},
        "trajectories": [],
        "examples": [],
    }
    dataset["examples"] = [*existing_examples, *[dict(row) for row in dataset.get("examples", []) if isinstance(row, dict)]]
    dataset["trajectories"] = [*existing_trajectories, *[dict(row) for row in dataset.get("trajectories", []) if isinstance(row, dict)]]
    dataset["sources"] = [*existing_sources, *[str(item) for item in dataset.get("sources", []) if item]]
    dataset["example_count"] = len(dataset["examples"])
    dataset["trajectory_count"] = len(dataset["trajectories"])
    dataset["split_counts"] = {
        "train": sum(1 for row in dataset["examples"] if row.get("split") == "train"),
        "validation": sum(1 for row in dataset["examples"] if row.get("split") == "validation"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
