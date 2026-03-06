from __future__ import annotations

import json
import subprocess
import sys


def test_phase8_self_play_generation_and_batch_runs(tmp_path) -> None:
    dataset_path = tmp_path / "self_play_dataset.json"
    slices_dir = tmp_path / "slices"
    series_dir = tmp_path / "series"
    batch_dir = tmp_path / "batch"
    closeout_path = tmp_path / "phase8_closeout.md"

    generate_result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_phase8_self_play_dataset.py",
            "--games",
            "2",
            "--max-actions",
            "12",
            "--output",
            str(dataset_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert generate_result.returncode == 0, generate_result.stderr
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert dataset["schema_version"] == "phase7.v1"
    assert dataset["example_count"] > 0
    assert "archetype_pair" in dataset["examples"][0]["setup"]

    slice_result = subprocess.run(
        [
            sys.executable,
            "scripts/slice_phase8_dataset.py",
            "--dataset",
            str(dataset_path),
            "--slice-field",
            "setup.archetype_pair",
            "--output-dir",
            str(slices_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert slice_result.returncode == 0, slice_result.stderr
    slice_manifest = json.loads((slices_dir / "slice_manifest.json").read_text(encoding="utf-8"))
    assert slice_manifest["slice_count"] >= 1

    series_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase8_self_play_series.py",
            "--runs",
            "2",
            "--games-per-run",
            "1",
            "--max-actions",
            "10",
            "--artifacts-dir",
            str(series_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert series_result.returncode == 0, series_result.stderr
    series_summary = json.loads((series_dir / "phase8_self_play_series_summary.json").read_text(encoding="utf-8"))
    assert series_summary["run_count"] == 2

    batch_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase8_batch_experiments.py",
            "--dataset",
            str(dataset_path),
            "--slice-field",
            "setup.archetype_pair",
            "--artifacts-dir",
            str(batch_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert batch_result.returncode == 0, batch_result.stderr
    batch_summary = json.loads((batch_dir / "phase8_batch_summary.json").read_text(encoding="utf-8"))
    assert batch_summary["run_count"] >= 1
    assert len(batch_summary["ranking"]) >= 1
    assert "promotion_summary" in batch_summary

    batch_series_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase8_batch_series.py",
            "--runs",
            "2",
            "--games-per-run",
            "1",
            "--max-actions",
            "10",
            "--artifacts-dir",
            str(tmp_path / "batch_series"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert batch_series_result.returncode == 0, batch_series_result.stderr
    batch_series_summary = json.loads((tmp_path / "batch_series" / "phase8_batch_series_summary.json").read_text(encoding="utf-8"))
    assert batch_series_summary["run_count"] == 2

    closeout_result = subprocess.run(
        [
            sys.executable,
            "scripts/render_phase8_closeout_report.py",
            "--batch-summary",
            str(batch_dir / "phase8_batch_summary.json"),
            "--batch-series-summary",
            str(tmp_path / "batch_series" / "phase8_batch_series_summary.json"),
            "--output",
            str(closeout_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert closeout_result.returncode == 0, closeout_result.stderr
    assert "Phase 8 Closeout" in closeout_path.read_text(encoding="utf-8")
