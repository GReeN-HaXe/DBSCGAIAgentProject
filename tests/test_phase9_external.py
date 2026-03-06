from __future__ import annotations

import json
import subprocess
import sys

from src.agent.phase9_external import (
    PHASE9_EXTERNAL_MATCH_SCHEMA_VERSION,
    PHASE9_VIDEO_FRAMES_SCHEMA_VERSION,
    apply_external_review,
    build_phase9_review_queue,
    build_video_frame_manifest,
    external_match_to_phase7_trace_artifact,
    merge_frame_events_into_external_match,
    normalize_external_match,
    reconstruct_external_match,
    score_external_match_confidence,
    summarize_phase7_dataset_by_mode,
)


def test_phase9_normalize_external_match_shape() -> None:
    payload = normalize_external_match(
        {
            "participants": {
                "player_1": {"name": "Alice", "leader_name": "Son Goku"},
                "player_2": {"name": "Bob", "leader_name": "Vegeta"},
            },
            "winner_seat": 1,
            "events": [
                {
                    "timestamp_seconds": 3.5,
                    "turn_number": 1,
                    "phase": "main",
                    "actor_seat": 1,
                    "actor_name": "Alice",
                    "action_type": "play_card_from_hand",
                    "action_text": "plays battle card",
                    "confidence": 0.9,
                }
            ],
        },
        match_id="match_001",
        source_name="manual_test",
    )
    assert payload["schema_version"] == PHASE9_EXTERNAL_MATCH_SCHEMA_VERSION
    assert payload["match_id"] == "match_001"
    assert payload["annotations"][0]["sequence_index"] == 1
    assert payload["annotations"][0]["actor"]["seat"] == 1


def test_phase9_build_video_frame_manifest_shape(tmp_path) -> None:
    manifest = build_video_frame_manifest(
        video_path=tmp_path / "match.mp4",
        output_dir=tmp_path / "frames",
        every_n_seconds=2.0,
        frame_count=3,
        extracted=False,
        ffmpeg_path="ffmpeg",
    )
    assert manifest["schema_version"] == PHASE9_VIDEO_FRAMES_SCHEMA_VERSION
    assert manifest["frame_count"] == 3
    assert len(manifest["frames"]) == 3


def test_phase9_reconstruct_review_and_convert_to_phase7() -> None:
    payload = normalize_external_match(
        {
            "winner_seat": 2,
            "events": [
                {"timestamp_seconds": 1.0, "phase": "charge", "actor_seat": 1, "action_type": "charge_from_hand", "action_text": "charge"},
                {"timestamp_seconds": 2.0, "phase": "main", "actor_seat": 1, "action_type": "play_card_from_hand", "action_text": "play"},
                {"timestamp_seconds": 3.0, "phase": "charge", "actor_seat": 2, "action_type": "charge_from_hand", "action_text": "charge"},
            ],
        },
        match_id="m2",
        source_name="manual",
    )
    reconstructed = reconstruct_external_match(payload)
    assert reconstructed["reconstruction"]["annotation_count"] == 3
    confidence = score_external_match_confidence(reconstructed)
    assert "overall_confidence" in confidence
    reviewed = apply_external_review(reconstructed, reviewer="qa", review_status="reviewed", notes="ok")
    trace = external_match_to_phase7_trace_artifact(reviewed)
    assert "trace" in trace
    assert trace["trace"]["setup"]["mode"] == "external_import"
    assert trace["trace"]["winner_id"] == 2

    merged = merge_frame_events_into_external_match(
        reviewed,
        {"events": [{"timestamp_seconds": 4.0, "phase": "end", "actor_seat": 2, "action_type": "end_turn"}], "manifest_path": "frames.json"},
    )
    assert merged["frame_merge"]["merged_event_count"] == 1
    queue = build_phase9_review_queue([reviewed, merged])
    assert queue["match_count"] == 2


def test_phase9_import_and_extract_scripts(tmp_path) -> None:
    annotation_path = tmp_path / "annotation.json"
    imported_path = tmp_path / "external_match.json"
    manifest_path = tmp_path / "video_frames_manifest.json"
    video_path = tmp_path / "external_match.mp4"
    annotation_path.write_text(
        json.dumps(
            {
                "participants": {
                    "player_1": {"name": "Alice"},
                    "player_2": {"name": "Bob"},
                },
                "events": [
                    {
                        "timestamp_seconds": 1.0,
                        "turn_number": 1,
                        "phase": "main",
                        "actor_seat": 1,
                        "action_type": "play_card_from_hand",
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    video_path.write_text("stub", encoding="utf-8")

    import_result = subprocess.run(
        [
            sys.executable,
            "scripts/import_phase9_external_match.py",
            "--input",
            str(annotation_path),
            "--match-id",
            "match_a",
            "--output",
            str(imported_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert import_result.returncode == 0, import_result.stderr
    imported = json.loads(imported_path.read_text(encoding="utf-8"))
    assert imported["schema_version"] == PHASE9_EXTERNAL_MATCH_SCHEMA_VERSION

    extract_result = subprocess.run(
        [
            sys.executable,
            "scripts/extract_phase9_video_frames.py",
            "--video",
            str(video_path),
            "--output-dir",
            str(tmp_path / "frames_out"),
            "--every-n-seconds",
            "0.5",
            "--frame-count",
            "4",
            "--plan-only",
            "--manifest-output",
            str(manifest_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert extract_result.returncode == 0, extract_result.stderr
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == PHASE9_VIDEO_FRAMES_SCHEMA_VERSION
    assert manifest["frame_count"] == 4


def test_phase9_reconstruct_and_export_scripts(tmp_path) -> None:
    imported_path = tmp_path / "external_match.json"
    reviewed_path = tmp_path / "external_reviewed.json"
    dataset_path = tmp_path / "external_dataset.json"
    imported_path.write_text(
        json.dumps(
            normalize_external_match(
                {
                    "winner_seat": 1,
                    "events": [
                        {"timestamp_seconds": 1.0, "phase": "charge", "actor_seat": 1, "action_type": "charge_from_hand"},
                        {"timestamp_seconds": 2.0, "phase": "main", "actor_seat": 1, "action_type": "play_card_from_hand"},
                    ],
                },
                match_id="match_b",
                source_name="manual_b",
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    reconstruct_result = subprocess.run(
        [
            sys.executable,
            "scripts/reconstruct_phase9_external_match.py",
            "--input",
            str(imported_path),
            "--reviewer",
            "qa",
            "--output",
            str(reviewed_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert reconstruct_result.returncode == 0, reconstruct_result.stderr
    reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
    assert reviewed["review"]["review_status"] == "reviewed"

    export_result = subprocess.run(
        [
            sys.executable,
            "scripts/export_phase9_external_to_phase7.py",
            "--input",
            str(reviewed_path),
            "--output",
            str(dataset_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert export_result.returncode == 0, export_result.stderr
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert dataset["schema_version"] == "phase7.v1"
    assert dataset["example_count"] >= 1


def test_phase9_merge_mixed_dataset_and_eval_report_scripts(tmp_path) -> None:
    external_path = tmp_path / "external_reviewed.json"
    self_play_path = tmp_path / "self_play_trace.json"
    frame_events_path = tmp_path / "frame_events.json"
    merged_path = tmp_path / "external_merged.json"
    mixed_dataset_path = tmp_path / "mixed_dataset.json"
    report_path = tmp_path / "phase9_report.json"

    external_payload = apply_external_review(
        reconstruct_external_match(
            normalize_external_match(
                {
                    "winner_seat": 1,
                    "events": [
                        {"timestamp_seconds": 1.0, "phase": "charge", "actor_seat": 1, "action_type": "charge_from_hand"},
                        {"timestamp_seconds": 2.0, "phase": "main", "actor_seat": 1, "action_type": "play_card_from_hand"},
                    ],
                },
                match_id="mix_1",
                source_name="manual_mix",
            )
        ),
        reviewer="qa",
        review_status="reviewed",
    )
    external_path.write_text(json.dumps(external_payload, indent=2), encoding="utf-8")
    self_play_path.write_text(
        json.dumps(
            {
                "trace": {
                    "total_actions": 1,
                    "winner_id": 1,
                    "final_turn_number": 1,
                    "final_phase": "main",
                    "human_player_id": None,
                    "setup": {"mode": "self_play"},
                    "actions": [
                        {
                            "actor_kind": "ai",
                            "player_id": 1,
                            "turn_number": 1,
                            "phase": "main",
                            "action": "play_card_from_hand",
                            "action_type": "play_card_from_hand",
                            "state_snapshot": {"active_player": 1, "phase": "main", "players": {}},
                        }
                    ],
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    frame_events_path.write_text(
        json.dumps({"events": [{"timestamp_seconds": 3.0, "phase": "end", "actor_seat": 2, "action_type": "end_turn"}]}, indent=2),
        encoding="utf-8",
    )

    merge_result = subprocess.run(
        [
            sys.executable,
            "scripts/merge_phase9_frame_events.py",
            "--match",
            str(external_path),
            "--frame-events",
            str(frame_events_path),
            "--output",
            str(merged_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert merge_result.returncode == 0, merge_result.stderr

    mixed_result = subprocess.run(
        [
            sys.executable,
            "scripts/build_phase9_mixed_dataset.py",
            "--self-play-input",
            str(self_play_path),
            "--external-input",
            str(merged_path),
            "--output",
            str(mixed_dataset_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert mixed_result.returncode == 0, mixed_result.stderr
    mixed_dataset = json.loads(mixed_dataset_path.read_text(encoding="utf-8"))
    summary = summarize_phase7_dataset_by_mode(mixed_dataset)
    assert summary["mode_count"] >= 2

    report_result = subprocess.run(
        [
            sys.executable,
            "scripts/render_phase9_eval_report.py",
            "--dataset",
            str(mixed_dataset_path),
            "--output",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert report_result.returncode == 0, report_result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "dataset_mode_summary" in report


def test_phase9_review_queue_and_selfplay_vs_mixed_scripts(tmp_path) -> None:
    external_path = tmp_path / "external_reviewed.json"
    self_play_dataset = tmp_path / "self_play_dataset.json"
    queue_path = tmp_path / "review_queue.json"
    compare_dir = tmp_path / "compare"

    external_payload = apply_external_review(
        reconstruct_external_match(
            normalize_external_match(
                {
                    "winner_seat": 1,
                    "events": [
                        {"timestamp_seconds": 1.0, "phase": "charge", "actor_seat": 1, "action_type": "charge_from_hand"},
                        {"timestamp_seconds": 2.0, "phase": "main", "actor_seat": 1, "action_type": "play_card_from_hand"},
                    ],
                },
                match_id="queue_1",
                source_name="queue_source",
            )
        ),
        reviewer="qa",
        review_status="reviewed",
    )
    external_path.write_text(json.dumps(external_payload, indent=2), encoding="utf-8")
    self_play_dataset.write_text(
        json.dumps(
            {
                "schema_version": "phase7.v1",
                "example_count": 1,
                "trajectory_count": 1,
                "validation_ratio": 0.2,
                "sources": ["selfplay"],
                "split_counts": {"train": 1, "validation": 0},
                "trajectories": [],
                "examples": [
                    {
                        "schema_version": "phase7.v1",
                        "source_name": "selfplay",
                        "trace_hash": "abc",
                        "example_index": 0,
                        "actor_kind": "ai",
                        "player_id": 1,
                        "human_player_id": None,
                        "is_human_action": False,
                        "turn_number": 1,
                        "phase": "main",
                        "action_type": "play_card_from_hand",
                        "action_family": "resource_development",
                        "action_text": "play_card_from_hand",
                        "actor_role_bucket": "ai",
                        "winner_id": 1,
                        "did_player_win": True,
                        "terminal_reward": 1.0,
                        "value_target": 1.0,
                        "turns_to_end": 0,
                        "final_turn_number": 1,
                        "final_phase": "main",
                        "total_actions_in_match": 1,
                        "split": "train",
                        "setup": {"mode": "self_play"},
                        "state_features": {"active_player": 1},
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    queue_result = subprocess.run(
        [
            sys.executable,
            "scripts/build_phase9_review_queue.py",
            "--input",
            str(external_path),
            "--output",
            str(queue_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert queue_result.returncode == 0, queue_result.stderr
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert queue["match_count"] == 1

    compare_result = subprocess.run(
        [
            sys.executable,
            "scripts/compare_phase9_selfplay_vs_mixed.py",
            "--self-play-dataset",
            str(self_play_dataset),
            "--external-input",
            str(external_path),
            "--artifacts-dir",
            str(compare_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert compare_result.returncode == 0, compare_result.stderr
    payload = json.loads((compare_dir / "phase9_selfplay_vs_mixed_report.json").read_text(encoding="utf-8"))
    assert "top1_delta_mixed_minus_selfplay" in payload


def test_phase9_review_batch_mixed_series_and_closeout_scripts(tmp_path) -> None:
    imported_a = tmp_path / "imported_a.json"
    imported_b = tmp_path / "imported_b.json"
    self_play_dataset = tmp_path / "self_play_dataset.json"
    review_dir = tmp_path / "review_batch"
    mixed_dir = tmp_path / "mixed_series"
    closeout_path = tmp_path / "phase9_closeout.md"

    for path, match_id, seat in [(imported_a, "m_a", 1), (imported_b, "m_b", 2)]:
        path.write_text(
            json.dumps(
                normalize_external_match(
                    {
                        "winner_seat": seat,
                        "events": [
                            {"timestamp_seconds": 1.0, "phase": "charge", "actor_seat": 1, "action_type": "charge_from_hand"},
                            {"timestamp_seconds": 2.0, "phase": "main", "actor_seat": 1, "action_type": "play_card_from_hand"},
                        ],
                    },
                    match_id=match_id,
                    source_name=f"source_{match_id}",
                ),
                indent=2,
            ),
            encoding="utf-8",
        )

    self_play_dataset.write_text(
        json.dumps(
            {
                "schema_version": "phase7.v1",
                "example_count": 1,
                "trajectory_count": 1,
                "validation_ratio": 0.2,
                "sources": ["selfplay"],
                "split_counts": {"train": 1, "validation": 0},
                "trajectories": [],
                "examples": [
                    {
                        "schema_version": "phase7.v1",
                        "source_name": "selfplay",
                        "trace_hash": "abc",
                        "example_index": 0,
                        "actor_kind": "ai",
                        "player_id": 1,
                        "human_player_id": None,
                        "is_human_action": False,
                        "turn_number": 1,
                        "phase": "main",
                        "action_type": "play_card_from_hand",
                        "action_family": "resource_development",
                        "action_text": "play_card_from_hand",
                        "actor_role_bucket": "ai",
                        "winner_id": 1,
                        "did_player_win": True,
                        "terminal_reward": 1.0,
                        "value_target": 1.0,
                        "turns_to_end": 0,
                        "final_turn_number": 1,
                        "final_phase": "main",
                        "total_actions_in_match": 1,
                        "split": "train",
                        "setup": {"mode": "self_play"},
                        "state_features": {"active_player": 1},
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    review_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase9_review_batch.py",
            "--input",
            str(imported_a),
            str(imported_b),
            "--artifacts-dir",
            str(review_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert review_result.returncode == 0, review_result.stderr
    review_summary = json.loads((review_dir / "phase9_review_batch_summary.json").read_text(encoding="utf-8"))
    assert review_summary["reviewed_count"] == 2

    mixed_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase9_mixed_series.py",
            "--self-play-dataset",
            str(self_play_dataset),
            "--external-set",
            str(review_dir / "reviewed_1.json"),
            "--external-set",
            str(review_dir / "reviewed_2.json"),
            "--artifacts-dir",
            str(mixed_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert mixed_result.returncode == 0, mixed_result.stderr
    mixed_summary = json.loads((mixed_dir / "phase9_mixed_series_summary.json").read_text(encoding="utf-8"))
    assert mixed_summary["run_count"] == 2

    closeout_result = subprocess.run(
        [
            sys.executable,
            "scripts/render_phase9_closeout_report.py",
            "--review-batch-summary",
            str(review_dir / "phase9_review_batch_summary.json"),
            "--mixed-series-summary",
            str(mixed_dir / "phase9_mixed_series_summary.json"),
            "--output",
            str(closeout_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert closeout_result.returncode == 0, closeout_result.stderr
    assert "Phase 9 Closeout" in closeout_path.read_text(encoding="utf-8")
