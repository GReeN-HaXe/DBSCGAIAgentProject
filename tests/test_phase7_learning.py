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
            "setup": {"seed": 17, "deck_source": "synthetic"},
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


def test_phase7_train_model_and_compare_against_heuristics(tmp_path) -> None:
    trace_path = tmp_path / "trace.json"
    dataset_path = tmp_path / "dataset.json"
    model_path = tmp_path / "model.json"
    model_eval_path = tmp_path / "model_eval.json"
    compare_path = tmp_path / "compare.json"
    history_csv = tmp_path / "history.csv"
    history_summary = tmp_path / "history_summary.json"
    _write_trace(trace_path)

    export_result = subprocess.run(
        [sys.executable, "scripts/export_phase7_dataset.py", "--input", str(trace_path), "--output", str(dataset_path), "--validation-ratio", "0.25"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert export_result.returncode == 0, export_result.stderr

    train_result = subprocess.run(
        [
            sys.executable,
            "scripts/train_phase7_model.py",
            "--dataset",
            str(dataset_path),
            "--context-mode",
            "identity",
            "--output",
            str(model_path),
            "--eval-output",
            str(model_eval_path),
            "--eval-split",
            "all",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert train_result.returncode == 0, train_result.stderr
    model_payload = json.loads(model_path.read_text(encoding="utf-8"))
    assert model_payload["model_name"] == "frequency_policy"
    assert model_payload["context_mode"] == "identity"
    assert "state_features.self_primary_resolved_signature" in model_payload["context_fields"]

    compare_result = subprocess.run(
        [
            sys.executable,
            "scripts/compare_phase7_model_vs_heuristic.py",
            "--dataset",
            str(dataset_path),
            "--model",
            str(model_path),
            "--split",
            "all",
            "--output",
            str(compare_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert compare_result.returncode == 0, compare_result.stderr
    compare_payload = json.loads(compare_path.read_text(encoding="utf-8"))
    assert len(compare_payload["ranking"]) == 4
    assert compare_payload["ranking"][0]["rank"] == 1
    assert "identity_resolution_rankings" in compare_payload
    assert compare_payload["results"][0]["identity_resolved_example_count"] >= 1

    history_result = subprocess.run(
        [
            sys.executable,
            "scripts/update_phase7_eval_history.py",
            "--input",
            str(compare_path),
            "--history-csv",
            str(history_csv),
            "--summary-output",
            str(history_summary),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert history_result.returncode == 0, history_result.stderr
    summary_payload = json.loads(history_summary.read_text(encoding="utf-8"))
    assert summary_payload["total_runs"] == 4
    assert "best_top1_accuracy" in summary_payload
    assert "latest_identity_resolved_example_rate" in summary_payload


def test_phase8_backoff_model_and_error_analysis(tmp_path) -> None:
    trace_path = tmp_path / "trace.json"
    dataset_path = tmp_path / "dataset.json"
    model_path = tmp_path / "backoff_model.json"
    eval_path = tmp_path / "backoff_eval.json"
    analysis_path = tmp_path / "analysis.json"
    _write_trace(trace_path)

    export_result = subprocess.run(
        [sys.executable, "scripts/export_phase7_dataset.py", "--input", str(trace_path), "--output", str(dataset_path), "--validation-ratio", "0.25"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert export_result.returncode == 0, export_result.stderr

    train_result = subprocess.run(
        [
            sys.executable,
            "scripts/train_phase7_model.py",
            "--dataset",
            str(dataset_path),
            "--model-type",
            "backoff",
            "--context-mode",
            "identity",
            "--output",
            str(model_path),
            "--eval-output",
            str(eval_path),
            "--eval-split",
            "all",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert train_result.returncode == 0, train_result.stderr
    model_payload = json.loads(model_path.read_text(encoding="utf-8"))
    assert model_payload["model_name"] == "backoff_frequency_policy"
    assert model_payload["context_mode"] == "identity"

    analysis_result = subprocess.run(
        [
            sys.executable,
            "scripts/analyze_phase8_errors.py",
            "--dataset",
            str(dataset_path),
            "--model",
            str(model_path),
            "--split",
            "all",
            "--output",
            str(analysis_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert analysis_result.returncode == 0, analysis_result.stderr
    analysis_payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert analysis_payload["model_name"] == "backoff_frequency_policy"
    assert "top_confusions" in analysis_payload
    assert "ablations" in analysis_payload
    assert "identity_resolution_slices" in analysis_payload
