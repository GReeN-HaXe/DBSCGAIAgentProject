from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip())
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "slice"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 8 training/evaluation in batch across dataset slices.")
    parser.add_argument("--dataset", type=Path, required=True, help="Base Phase 7 dataset JSON path.")
    parser.add_argument("--slice-field", type=str, default="setup.archetype_pair", help="Nested field used for slicing before batch runs.")
    parser.add_argument("--model-type", choices=["frequency", "backoff"], default="backoff", help="Model type used for each batch run.")
    parser.add_argument("--target-field", choices=["action_type", "action_family"], default="action_type", help="Target field for each run.")
    parser.add_argument("--train-split", choices=["train", "validation", "all"], default="train", help="Train split for each run.")
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation", help="Eval split for each run.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase8_batch"), help="Output directory for batch artifacts.")
    args = parser.parse_args()

    slices_dir = args.artifacts_dir / "slices"
    _run(
        [
            sys.executable,
            "scripts/slice_phase8_dataset.py",
            "--dataset",
            str(args.dataset),
            "--slice-field",
            str(args.slice_field),
            "--output-dir",
            str(slices_dir),
        ]
    )
    manifest = _load_json(slices_dir / "slice_manifest.json")
    runs: list[dict[str, object]] = []
    for item in manifest.get("slices", []):
        if not isinstance(item, dict):
            continue
        slice_value = str(item.get("slice_value", "slice"))
        dataset_path = Path(str(item.get("path", "")))
        run_dir = args.artifacts_dir / f"run_{_safe_name(slice_value)}"
        _run(
            [
                sys.executable,
                "scripts/run_phase8_training_pipeline.py",
                "--dataset",
                str(dataset_path),
                "--run-name",
                slice_value,
                "--model-type",
                str(args.model_type),
                "--target-field",
                str(args.target_field),
                "--train-split",
                str(args.train_split),
                "--eval-split",
                str(args.eval_split),
                "--artifacts-dir",
                str(run_dir),
            ]
        )
        summary = _load_json(run_dir / "phase8_experiment_history_summary.json")
        manifest_json = _load_json(run_dir / "phase8_model_manifest.json")
        runs.append(
            {
                "slice_value": slice_value,
                "dataset_path": str(dataset_path),
                "artifacts_dir": str(run_dir),
                "model_name": manifest_json.get("model_name"),
                "top1_accuracy": manifest_json.get("metrics", {}).get("model_top1_accuracy", 0.0),
                "identity_resolved_example_count": manifest_json.get("metrics", {}).get("identity_resolved_example_count", 0),
                "identity_resolved_example_rate": manifest_json.get("metrics", {}).get("identity_resolved_example_rate", 0.0),
                "promotion_passed": manifest_json.get("metrics", {}).get("promotion_passed", False),
                "summary": summary,
            }
        )
    ranking = sorted(runs, key=lambda row: (-float(row.get("top1_accuracy", 0.0) or 0.0), str(row.get("slice_value", ""))))
    promoted_runs = [row for row in runs if bool(row.get("promotion_passed", False))]
    promoted_ranking = sorted(
        promoted_runs,
        key=lambda row: (-float(row.get("top1_accuracy", 0.0) or 0.0), str(row.get("slice_value", ""))),
    )
    payload = {
        "slice_field": str(args.slice_field),
        "run_count": len(runs),
        "identity_summary": {
            "avg_identity_resolved_example_rate": (
                sum(float(row.get("identity_resolved_example_rate", 0.0) or 0.0) for row in runs) / len(runs)
                if runs
                else 0.0
            ),
            "total_identity_resolved_examples": sum(int(row.get("identity_resolved_example_count", 0) or 0) for row in runs),
        },
        "runs": runs,
        "ranking": [{**row, "rank": idx + 1} for idx, row in enumerate(ranking)],
        "promotion_summary": {
            "promoted_run_count": len(promoted_runs),
            "best_promoted": (None if not promoted_ranking else {**promoted_ranking[0], "rank": 1}),
            "promoted_ranking": [{**row, "rank": idx + 1} for idx, row in enumerate(promoted_ranking)],
        },
    }
    out = args.artifacts_dir / "phase8_batch_summary.json"
    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()
