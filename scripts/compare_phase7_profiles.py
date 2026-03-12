from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_phase7_dataset import evaluate_phase7_dataset


def _load_dataset(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected dataset JSON object in {path}")
    return data


def compare_profiles(dataset: dict[str, object], *, profiles: list[str], split: str) -> dict[str, object]:
    results = [evaluate_phase7_dataset(dataset, profile=profile, split=split) for profile in profiles]
    ranked = sorted(
        results,
        key=lambda row: (-float(row.get("top1_accuracy", 0.0)), -float(row.get("family_accuracy", 0.0)), str(row.get("profile", ""))),
    )
    def _rank_for_slice(slice_name: str) -> list[dict[str, object]]:
        ranked_slice = sorted(
            results,
            key=lambda row: (
                -float(((row.get("identity_resolution_slices", {}) if isinstance(row.get("identity_resolution_slices"), dict) else {}).get(slice_name, {}) or {}).get("top1_accuracy", 0.0)),
                -float(((row.get("identity_resolution_slices", {}) if isinstance(row.get("identity_resolution_slices"), dict) else {}).get(slice_name, {}) or {}).get("family_accuracy", 0.0)),
                str(row.get("profile", "")),
            ),
        )
        return [
            {
                "rank": idx + 1,
                "profile": row.get("profile"),
                "top1_accuracy": (((row.get("identity_resolution_slices", {}) if isinstance(row.get("identity_resolution_slices"), dict) else {}).get(slice_name, {}) or {}).get("top1_accuracy")),
                "family_accuracy": (((row.get("identity_resolution_slices", {}) if isinstance(row.get("identity_resolution_slices"), dict) else {}).get(slice_name, {}) or {}).get("family_accuracy")),
                "example_count": (((row.get("identity_resolution_slices", {}) if isinstance(row.get("identity_resolution_slices"), dict) else {}).get(slice_name, {}) or {}).get("example_count")),
            }
            for idx, row in enumerate(ranked_slice)
        ]
    return {
        "split": split,
        "profiles": profiles,
        "ranking": [
            {
                "rank": idx + 1,
                "profile": row.get("profile"),
                "top1_accuracy": row.get("top1_accuracy"),
                "family_accuracy": row.get("family_accuracy"),
                "example_count": row.get("example_count"),
            }
            for idx, row in enumerate(ranked)
        ],
        "identity_resolution_rankings": {
            "with_identity": _rank_for_slice("with_identity"),
            "without_identity": _rank_for_slice("without_identity"),
        },
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare multiple heuristic profiles on a Phase 7 dataset.")
    parser.add_argument("--dataset", type=Path, required=True, help="Phase 7 dataset JSON path.")
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["balanced", "aggressive", "control"],
        help="Profiles to compare.",
    )
    parser.add_argument("--split", choices=["train", "validation", "all"], default="validation", help="Dataset split to score.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase7_profile_compare.json"), help="Comparison output path.")
    args = parser.parse_args()

    payload = compare_profiles(_load_dataset(args.dataset), profiles=[str(p) for p in args.profiles], split=str(args.split))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
