from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import (
    build_phase10_benchmark_history_row,
    phase10_benchmark_history_row_to_dict,
    summarize_phase10_benchmark_history,
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


def _append_history_csv(path: Path, row: dict[str, str]) -> list[dict[str, str]]:
    existing: list[dict[str, str]] = []
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as handle:
            existing = list(csv.DictReader(handle))
    rows = [*existing, row]
    fieldnames = list(row.keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 10 end-to-end pipeline from frames to a Phase 7 dataset.")
    parser.add_argument("--frame-manifest", type=Path, required=True, help="Phase 9 frame manifest JSON path.")
    parser.add_argument("--corrections", type=Path, required=True, help="Detection correction JSON list.")
    parser.add_argument("--match-id", type=str, required=True, help="Match identifier for external artifact conversion.")
    parser.add_argument("--source-name", type=str, default="phase10_pipeline", help="Source name for the converted external match.")
    parser.add_argument("--labeled-detections", type=Path, default=None, help="Optional labeled detection manifest for benchmarking.")
    parser.add_argument("--validation-ratio", type=float, default=0.2, help="Validation ratio for the exported Phase 7 dataset.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase10_pipeline"), help="Output artifact directory.")
    parser.add_argument("--history-csv", type=Path, default=None, help="Optional benchmark history CSV path.")
    parser.add_argument("--history-summary-output", type=Path, default=None, help="Optional benchmark history summary JSON path.")
    args = parser.parse_args()

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    detections_path = args.artifacts_dir / "phase10_detections.json"
    reviewed_path = args.artifacts_dir / "phase10_reviewed_detections.json"
    external_match_path = args.artifacts_dir / "phase10_external_match.json"
    dataset_path = args.artifacts_dir / "phase10_phase7_dataset.json"
    benchmark_path = args.artifacts_dir / "phase10_benchmark.json"
    manifest_path = args.artifacts_dir / "phase10_pipeline_manifest.json"

    _run(
        [
            sys.executable,
            "scripts/run_phase10_mock_recognizer.py",
            "--frame-manifest",
            str(args.frame_manifest),
            "--output",
            str(detections_path),
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/review_phase10_detections.py",
            "--input",
            str(detections_path),
            "--corrections",
            str(args.corrections),
            "--reviewer",
            "phase10_pipeline",
            "--output",
            str(reviewed_path),
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/convert_phase10_reviewed_to_external_match.py",
            "--input",
            str(reviewed_path),
            "--match-id",
            str(args.match_id),
            "--source-name",
            str(args.source_name),
            "--reviewer",
            "phase10_pipeline",
            "--output",
            str(external_match_path),
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/export_phase9_external_to_phase7.py",
            "--input",
            str(external_match_path),
            "--validation-ratio",
            str(args.validation_ratio),
            "--output",
            str(dataset_path),
        ]
    )

    benchmark_payload: dict[str, object] = {}
    history_summary: dict[str, object] = {}
    if args.labeled_detections is not None:
        _run(
            [
                sys.executable,
                "scripts/benchmark_phase10_recognizer.py",
                "--predicted",
                str(reviewed_path),
                "--labeled",
                str(args.labeled_detections),
                "--output",
                str(benchmark_path),
            ]
        )
        benchmark_payload = _load_json(benchmark_path)
        history_csv = args.history_csv or (args.artifacts_dir / "phase10_benchmark_history.csv")
        history_summary_output = args.history_summary_output or (args.artifacts_dir / "phase10_benchmark_history_summary.json")
        history_row = build_phase10_benchmark_history_row(
            run_name=str(args.match_id),
            recognizer_name=str(benchmark_payload.get("recognizer_name", "")),
            frame_count=int(benchmark_payload.get("frame_count", 0) or 0),
            object_precision=float(benchmark_payload.get("object_precision", 0.0) or 0.0),
            object_recall=float(benchmark_payload.get("object_recall", 0.0) or 0.0),
            frame_exact_match_rate=float(benchmark_payload.get("frame_exact_match_rate", 0.0) or 0.0),
            benchmark_path=str(benchmark_path),
            status="pass",
        )
        history_rows = _append_history_csv(history_csv, phase10_benchmark_history_row_to_dict(history_row))
        history_summary = summarize_phase10_benchmark_history(history_rows)
        history_summary_output.write_text(json.dumps(history_summary, indent=2), encoding="utf-8")

    manifest = {
        "schema_version": "phase10.pipeline.v1",
        "status": "pass",
        "match_id": str(args.match_id),
        "source_name": str(args.source_name),
        "artifacts": {
            "detections": str(detections_path),
            "reviewed_detections": str(reviewed_path),
            "external_match": str(external_match_path),
            "phase7_dataset": str(dataset_path),
            "benchmark": str(benchmark_path) if benchmark_payload else "",
        },
        "benchmark_summary": benchmark_payload,
        "history_summary": history_summary,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote: {manifest_path}")


if __name__ == "__main__":
    main()
