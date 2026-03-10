from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import (
    build_phase8_experiment_history_row,
    build_phase8_model_manifest,
    phase8_experiment_history_row_to_dict,
    summarize_phase8_experiment_history,
)


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the repeatable Phase 8 training/evaluation pipeline.")
    parser.add_argument("--dataset", type=Path, required=True, help="Phase 7 dataset JSON path.")
    parser.add_argument("--run-name", type=str, default="phase8_run", help="Logical run name for manifests/history.")
    parser.add_argument("--target-field", choices=["action_type", "action_family"], default="action_type", help="Target field for training.")
    parser.add_argument("--context-mode", choices=["baseline", "identity"], default="baseline", help="Context feature preset for training.")
    parser.add_argument("--train-split", choices=["train", "validation", "all"], default="train", help="Dataset split used for training.")
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation", help="Dataset split used for evaluation.")
    parser.add_argument("--profiles", nargs="+", default=["balanced", "aggressive", "control"], help="Heuristic profiles to compare against.")
    parser.add_argument("--model-type", choices=["frequency", "backoff"], default="backoff", help="Model family to train.")
    parser.add_argument("--min-top1-lift", type=float, default=0.0, help="Minimum top1 lift over best heuristic required for promotion.")
    parser.add_argument("--fail-on-no-promotion", action="store_true", help="Fail the pipeline if the trained model is not promoted.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase8_pipeline"), help="Output artifact directory.")
    parser.add_argument("--history-csv", type=Path, default=None, help="Optional experiment history CSV path.")
    parser.add_argument("--history-summary-json", type=Path, default=None, help="Optional experiment history summary output path.")
    args = parser.parse_args()

    artifacts_dir = args.artifacts_dir
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifacts_dir / "phase8_model.json"
    eval_path = artifacts_dir / "phase8_model_eval.json"
    compare_path = artifacts_dir / "phase8_model_vs_heuristic.json"
    manifest_path = artifacts_dir / "phase8_model_manifest.json"
    history_csv = args.history_csv or (artifacts_dir / "phase8_experiment_history.csv")
    history_summary_json = args.history_summary_json or (artifacts_dir / "phase8_experiment_history_summary.json")

    _run(
        [
            sys.executable,
            "scripts/train_phase7_model.py",
            "--dataset",
            str(args.dataset),
            "--model-type",
            str(args.model_type),
            "--target-field",
            str(args.target_field),
            "--context-mode",
            str(args.context_mode),
            "--train-split",
            str(args.train_split),
            "--eval-split",
            str(args.eval_split),
            "--output",
            str(model_path),
            "--eval-output",
            str(eval_path),
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/compare_phase7_model_vs_heuristic.py",
            "--dataset",
            str(args.dataset),
            "--model",
            str(model_path),
            "--split",
            str(args.eval_split),
            "--min-top1-lift",
            str(args.min_top1_lift),
            "--output",
            str(compare_path),
            "--profiles",
            *[str(p) for p in args.profiles],
        ]
    )

    model_payload = _load_json(model_path)
    eval_payload = _load_json(eval_path)
    compare_payload = _load_json(compare_path)
    manifest = build_phase8_model_manifest(
        run_name=str(args.run_name),
        dataset_path=str(args.dataset),
        model_path=str(model_path),
        eval_path=str(eval_path),
        compare_path=str(compare_path),
        target_field=str(args.target_field),
        context_mode=str(args.context_mode),
        train_split=str(args.train_split),
        eval_split=str(args.eval_split),
        model_payload=model_payload,
        eval_payload=eval_payload,
        compare_payload=compare_payload,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote: {manifest_path}")
    if bool(args.fail_on_no_promotion):
        promotion = compare_payload.get("promotion", {})
        promoted = bool(promotion.get("promoted", False)) if isinstance(promotion, dict) else False
        if not promoted:
            raise RuntimeError(
                "promotion gate failed: "
                f"model_top1={promotion.get('model_top1_accuracy')} "
                f"best_heuristic_top1={promotion.get('best_heuristic_top1_accuracy')} "
                f"min_top1_lift={promotion.get('min_top1_lift')}"
            )

    row = build_phase8_experiment_history_row(
        run_name=str(args.run_name),
        model_name=str(manifest.get("model_name", "")),
        target_field=str(args.target_field),
        context_mode=str(args.context_mode),
        train_split=str(args.train_split),
        eval_split=str(args.eval_split),
        example_count=int(eval_payload.get("example_count", 0) or 0),
        top1_accuracy=float(eval_payload.get("top1_accuracy", 0.0) or 0.0),
        family_accuracy=float(eval_payload.get("top1_accuracy", 0.0) or 0.0),
        identity_resolved_example_count=int(eval_payload.get("identity_resolved_example_count", 0) or 0),
        identity_resolved_example_rate=float(eval_payload.get("identity_resolved_example_rate", 0.0) or 0.0),
        status=str(manifest.get("status", "pass")),
        manifest_path=str(manifest_path),
    )
    row_out = phase8_experiment_history_row_to_dict(row)
    existing_rows: list[dict[str, str]] = []
    if history_csv.exists():
        with history_csv.open("r", encoding="utf-8", newline="") as fh:
            for item in csv.DictReader(fh):
                existing_rows.append(dict(item))
    with history_csv.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row_out.keys()))
        if not existing_rows:
            writer.writeheader()
        writer.writerow(row_out)
    print(f"appended: {history_csv}")

    summary = summarize_phase8_experiment_history([*existing_rows, row_out])
    history_summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote: {history_summary_json}")


if __name__ == "__main__":
    main()
