from __future__ import annotations

import json
import subprocess
import sys


def _write_trace(path) -> None:
    payload = {
        "trace": {
            "total_actions": 4,
            "winner_id": 1,
            "final_turn_number": 3,
            "final_phase": "main",
            "human_player_id": 1,
            "setup": {"seed": 23, "deck_source": "synthetic"},
            "actions": [
                {
                    "timestamp_utc": "2026-01-01T00:00:00Z",
                    "actor_kind": "human",
                    "player_id": 1,
                    "turn_number": 1,
                    "phase": "main",
                    "action": "play_card_from_hand hand_index=0",
                    "action_type": "play_card_from_hand",
                    "state_snapshot": {
                        "active_player": 1,
                        "turn_number": 1,
                        "phase": "main",
                        "battle_step": None,
                        "counter_window_kind": None,
                        "players": {
                            "1": {"hand_size": 6, "life_size": 8, "energy_size": 1, "energy_resting_count": 0, "battle_size": 0, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                            "2": {"hand_size": 6, "life_size": 8, "energy_size": 0, "energy_resting_count": 0, "battle_size": 0, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                        },
                    },
                },
                {
                    "timestamp_utc": "2026-01-01T00:00:01Z",
                    "actor_kind": "ai",
                    "player_id": 2,
                    "turn_number": 1,
                    "phase": "end",
                    "action": "end_turn",
                    "action_type": "end_turn",
                    "resolved_signatures_by_seat": {"1": ["BT1-001"], "2": ["BT1-002"]},
                    "has_identity_resolution": True,
                    "state_snapshot": {
                        "active_player": 2,
                        "turn_number": 1,
                        "phase": "end",
                        "battle_step": None,
                        "counter_window_kind": None,
                        "players": {
                            "1": {"hand_size": 5, "life_size": 8, "energy_size": 1, "energy_resting_count": 1, "battle_size": 1, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                            "2": {"hand_size": 6, "life_size": 8, "energy_size": 1, "energy_resting_count": 1, "battle_size": 0, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                        },
                    },
                },
                {
                    "timestamp_utc": "2026-01-01T00:00:02Z",
                    "actor_kind": "human",
                    "player_id": 1,
                    "turn_number": 2,
                    "phase": "main",
                    "action": "play_card_from_hand hand_index=0",
                    "action_type": "play_card_from_hand",
                    "state_snapshot": {
                        "active_player": 1,
                        "turn_number": 2,
                        "phase": "main",
                        "battle_step": None,
                        "counter_window_kind": None,
                        "players": {
                            "1": {"hand_size": 5, "life_size": 8, "energy_size": 2, "energy_resting_count": 0, "battle_size": 1, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                            "2": {"hand_size": 6, "life_size": 8, "energy_size": 1, "energy_resting_count": 0, "battle_size": 0, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                        },
                    },
                },
                {
                    "timestamp_utc": "2026-01-01T00:00:03Z",
                    "actor_kind": "ai",
                    "player_id": 2,
                    "turn_number": 2,
                    "phase": "end",
                    "action": "end_turn",
                    "action_type": "end_turn",
                    "state_snapshot": {
                        "active_player": 2,
                        "turn_number": 2,
                        "phase": "end",
                        "battle_step": None,
                        "counter_window_kind": None,
                        "players": {
                            "1": {"hand_size": 4, "life_size": 8, "energy_size": 2, "energy_resting_count": 1, "battle_size": 2, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                            "2": {"hand_size": 6, "life_size": 8, "energy_size": 2, "energy_resting_count": 1, "battle_size": 0, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                        },
                    },
                },
            ],
        }
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_phase8_training_pipeline_writes_manifest_and_history(tmp_path) -> None:
    trace_path = tmp_path / "trace.json"
    dataset_path = tmp_path / "dataset.json"
    artifacts_dir = tmp_path / "phase8"
    _write_trace(trace_path)

    export_result = subprocess.run(
        [sys.executable, "scripts/export_phase7_dataset.py", "--input", str(trace_path), "--output", str(dataset_path), "--validation-ratio", "0.25"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert export_result.returncode == 0, export_result.stderr

    run_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase8_training_pipeline.py",
            "--dataset",
            str(dataset_path),
            "--run-name",
            "phase8_test",
            "--model-type",
            "backoff",
            "--context-mode",
            "identity",
            "--artifacts-dir",
            str(artifacts_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run_result.returncode == 0, run_result.stderr

    manifest = json.loads((artifacts_dir / "phase8_model_manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((artifacts_dir / "phase8_experiment_history_summary.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "phase8.manifest.v1"
    assert manifest["run_name"] == "phase8_test"
    assert manifest["status"] == "pass"
    assert manifest["model_name"] == "backoff_frequency_policy"
    assert manifest["context_mode"] == "identity"
    assert "promotion_passed" in manifest["metrics"]
    assert "identity_resolved_example_count" in manifest["metrics"]
    assert "identity_resolved_example_rate" in manifest["metrics"]
    assert summary["total_runs"] == 1
    assert "best_top1_accuracy" in summary
    assert "recent_avg_identity_resolved_example_rate" in summary
    assert summary["latest_context_mode"] == "identity"


def test_phase8_identity_context_compare_runner(tmp_path) -> None:
    trace_path = tmp_path / "trace_compare.json"
    dataset_path = tmp_path / "dataset_compare.json"
    artifacts_dir = tmp_path / "phase8_identity_compare"
    report_path = tmp_path / "phase8_identity_compare.md"
    _write_trace(trace_path)

    export_result = subprocess.run(
        [sys.executable, "scripts/export_phase7_dataset.py", "--input", str(trace_path), "--output", str(dataset_path), "--validation-ratio", "0.25"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert export_result.returncode == 0, export_result.stderr

    compare_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase8_identity_context_compare.py",
            "--dataset",
            str(dataset_path),
            "--run-name",
            "phase8_identity_compare_test",
            "--artifacts-dir",
            str(artifacts_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert compare_result.returncode == 0, compare_result.stderr
    payload = json.loads((artifacts_dir / "phase8_identity_context_compare.json").read_text(encoding="utf-8"))
    assert payload["dataset_identity_coverage"]["identity_resolved_example_count"] >= 1
    assert "top1_lift_identity_minus_baseline" in payload["comparison"]

    report_result = subprocess.run(
        [
            sys.executable,
            "scripts/render_phase8_identity_context_report.py",
            "--input",
            str(artifacts_dir / "phase8_identity_context_compare.json"),
            "--output",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert report_result.returncode == 0, report_result.stderr
    assert "Phase 8 Identity Context Compare" in report_path.read_text(encoding="utf-8")
