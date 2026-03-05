from __future__ import annotations

from src.agent.artifact_checks import check_phase6_artifact_consistency, extract_trace_payload_and_hash
from src.agent.replay import compute_trace_hash


def _sample_trace_payload() -> dict[str, object]:
    return {
        "total_actions": 1,
        "winner_id": None,
        "final_turn_number": 1,
        "final_phase": "charge",
        "human_player_id": 1,
        "actions": [
            {
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "actor_kind": "human",
                "player_id": 1,
                "turn_number": 1,
                "phase": "charge",
                "action": "end_charge",
                "action_type": "end_charge",
            }
        ],
    }


def test_phase6_extract_trace_payload_and_hash_supports_wrapped_and_legacy() -> None:
    payload = _sample_trace_payload()
    h = compute_trace_hash(payload)
    wrapped = {"trace": payload, "trace_hash": h}
    p1, h1 = extract_trace_payload_and_hash(wrapped)
    assert p1 == payload
    assert h1 == h
    p2, h2 = extract_trace_payload_and_hash(payload)
    assert p2 == payload
    assert h2 == ""


def test_phase6_check_phase6_artifact_consistency_passes_on_valid_payloads() -> None:
    play_payload = _sample_trace_payload()
    replay_payload = _sample_trace_payload()
    play_hash = compute_trace_hash(play_payload)
    replay_hash = compute_trace_hash(replay_payload)
    failures, checks = check_phase6_artifact_consistency(
        play_trace={"trace": play_payload, "trace_hash": play_hash},
        summary={"trace_hash": play_hash},
        play_result={"ok": True},
        replay={"trace": replay_payload, "trace_hash": replay_hash},
        replay_result={"ok": True},
        strict_summary_trace_hash=True,
    )
    assert failures == []
    assert checks["play_result_ok"] is True
    assert checks["replay_result_ok"] is True
