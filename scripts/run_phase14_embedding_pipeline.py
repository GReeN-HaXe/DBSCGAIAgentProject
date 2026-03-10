from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import (
    build_phase14_embedding_history_row,
    compare_phase14_embedding_vs_classifier_retrieval,
    has_torch_support,
    phase14_embedding_history_row_to_dict,
    summarize_phase14_embedding_history,
)


def _run(cmd: list[str], *, stage_name: str, timeout_seconds: int) -> float:
    print(f"[phase14-embedding] start: {stage_name}")
    print(f"[phase14-embedding] cmd: {' '.join(cmd)}")
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        raise RuntimeError(f"stage timed out after {elapsed:.1f}s: {stage_name}") from exc
    elapsed = time.perf_counter() - started
    print(f"[phase14-embedding] done: {stage_name} ({elapsed:.1f}s)")
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")
    return elapsed


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _append_history_csv(path: Path, row: dict[str, str]) -> list[dict[str, str]]:
    existing: list[dict[str, str]] = []
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as handle:
            existing = list(csv.DictReader(handle))
    rows = [*existing, row]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 14 embedding-retrieval pipeline.")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--feature-cache", type=Path, required=True)
    parser.add_argument("--run-name", type=str, default="phase14_embedding_run")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase14_embedding_pipeline"))
    parser.add_argument("--gallery-split", choices=["train", "validation", "all"], default="train")
    parser.add_argument("--query-split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--top-k", nargs="*", type=int, default=[1, 5, 10, 20])
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--stage-timeout-seconds", type=int, default=1800)
    parser.add_argument("--history-csv", type=Path, default=None)
    parser.add_argument("--history-summary-output", type=Path, default=None)
    args = parser.parse_args()

    if not has_torch_support():
        raise RuntimeError("PyTorch is not installed. Install requirements-torch.txt first.")

    model = args.model.resolve()
    feature_cache = args.feature_cache.resolve()
    artifacts_dir = args.artifacts_dir.resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    embedding_eval_path = artifacts_dir / "phase14_embedding_retrieval.json"
    embedding_report_path = artifacts_dir / "phase14_embedding_report.md"
    classifier_model_eval_path = artifacts_dir / "phase14_classifier_eval.json"
    classifier_eval_path = artifacts_dir / "phase14_classifier_retrieval.json"
    compare_path = artifacts_dir / "phase14_embedding_compare.json"
    manifest_path = artifacts_dir / "phase14_embedding_manifest.json"
    history_csv = args.history_csv.resolve() if args.history_csv else (artifacts_dir / "phase14_embedding_history.csv")
    history_summary_output = (
        args.history_summary_output.resolve()
        if args.history_summary_output
        else (artifacts_dir / "phase14_embedding_history_summary.json")
    )

    stage_timings = [
        {
            "stage": "evaluate_embedding_retrieval",
            "duration_seconds": _run(
                [
                    sys.executable,
                    str((ROOT / "scripts" / "evaluate_phase14_embedding_retrieval.py").resolve()),
                    "--model",
                    str(model),
                    "--dataset",
                    str(feature_cache),
                    "--gallery-split",
                    str(args.gallery_split),
                    "--query-split",
                    str(args.query_split),
                    "--top-k",
                    *[str(int(value)) for value in args.top_k],
                    "--output",
                    str(embedding_eval_path),
                ],
                stage_name="evaluate_embedding_retrieval",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        },
        {
            "stage": "render_embedding_report",
            "duration_seconds": _run(
                [
                    sys.executable,
                    str((ROOT / "scripts" / "render_phase14_embedding_report.py").resolve()),
                    "--retrieval",
                    str(embedding_eval_path),
                    "--output",
                    str(embedding_report_path),
                ],
                stage_name="render_embedding_report",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        },
    ]

    embedding_eval = _load_json(embedding_eval_path)
    recall = embedding_eval.get("recall_at_k", {})
    if not isinstance(recall, dict):
        recall = {}

    history_row = build_phase14_embedding_history_row(
        run_name=str(args.run_name),
        mean_reciprocal_rank=float(embedding_eval.get("mean_reciprocal_rank", 0.0) or 0.0),
        recall_at_1=float(recall.get("1", 0.0) or 0.0),
        recall_at_5=float(recall.get("5", 0.0) or 0.0),
        recall_at_10=float(recall.get("10", 0.0) or 0.0),
        example_count=int(embedding_eval.get("example_count", 0) or 0),
        manifest_path=str(manifest_path),
    )
    history_rows = _append_history_csv(history_csv, phase14_embedding_history_row_to_dict(history_row))
    history_summary = summarize_phase14_embedding_history(history_rows)
    history_summary_output.write_text(json.dumps(history_summary, indent=2), encoding="utf-8")

    classifier_compare: dict[str, object] = {}
    comparison_warning = ""
    stage_timings.append(
        {
            "stage": "evaluate_classifier_model",
            "duration_seconds": _run(
                [
                    sys.executable,
                    str((ROOT / "scripts" / "evaluate_phase14_torch_model.py").resolve()),
                    "--model",
                    str(model),
                    "--dataset",
                    str(feature_cache),
                    "--split",
                    str(args.query_split),
                    "--batch-size",
                    str(max(64, int(args.batch_size))),
                    "--output",
                    str(classifier_model_eval_path),
                ],
                stage_name="evaluate_classifier_model",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        }
    )
    stage_timings.append(
        {
            "stage": "evaluate_classifier_retrieval",
            "duration_seconds": _run(
                [
                    sys.executable,
                    str((ROOT / "scripts" / "evaluate_phase14_retrieval.py").resolve()),
                    "--evaluation",
                    str(classifier_model_eval_path),
                    "--top-k",
                    *[str(int(value)) for value in args.top_k],
                    "--output",
                    str(classifier_eval_path),
                ],
                stage_name="evaluate_classifier_retrieval",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        }
    )
    classifier_retrieval = _load_json(classifier_eval_path)
    try:
        classifier_compare = compare_phase14_embedding_vs_classifier_retrieval(
            classifier_retrieval=classifier_retrieval,
            embedding_retrieval=embedding_eval,
        )
    except ValueError as exc:
        comparison_warning = str(exc)
    else:
        compare_path.write_text(json.dumps(classifier_compare, indent=2), encoding="utf-8")

    manifest = {
        "schema_version": "phase14.embedding_manifest.v1",
        "status": "pass",
        "run_name": str(args.run_name),
        "artifacts": {
            "model": str(model),
            "feature_cache": str(feature_cache),
            "embedding_retrieval": str(embedding_eval_path),
            "embedding_report": str(embedding_report_path),
            "classifier_model_eval": str(classifier_model_eval_path),
            "embedding_history_csv": str(history_csv),
            "embedding_history_summary": str(history_summary_output),
        },
        "metrics": {
            "target_type": str(embedding_eval.get("target_type", "")),
            "gallery_split": str(embedding_eval.get("gallery_split", "")),
            "query_split": str(embedding_eval.get("query_split", "")),
            "example_count": int(embedding_eval.get("example_count", 0) or 0),
            "mean_reciprocal_rank": float(embedding_eval.get("mean_reciprocal_rank", 0.0) or 0.0),
            "mean_found_rank": float(embedding_eval.get("mean_found_rank", 0.0) or 0.0),
            "recall_at_1": float(recall.get("1", 0.0) or 0.0),
            "recall_at_5": float(recall.get("5", 0.0) or 0.0),
            "recall_at_10": float(recall.get("10", 0.0) or 0.0),
            "recall_at_20": float(recall.get("20", 0.0) or 0.0),
        },
        "classifier_comparison": classifier_compare,
        "comparison_warning": comparison_warning,
        "stage_timings": stage_timings,
        "history": history_summary,
    }
    manifest["artifacts"]["classifier_retrieval"] = str(classifier_eval_path)
    if compare_path.exists():
        manifest["artifacts"]["classifier_comparison"] = str(compare_path)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote: {manifest_path}")


if __name__ == "__main__":
    main()
