from __future__ import annotations

from typing import Any

from src.agent.replay import compute_trace_hash


def extract_trace_payload_and_hash(trace_obj: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    payload = trace_obj.get("trace")
    trace_hash = str(trace_obj.get("trace_hash", ""))
    if isinstance(payload, dict):
        return payload, trace_hash
    if "actions" in trace_obj and isinstance(trace_obj.get("actions"), list):
        # Backward compatibility: older artifacts may store trace payload at root.
        return trace_obj, trace_hash
    return None, trace_hash


def check_phase6_artifact_consistency(
    *,
    play_trace: dict[str, Any],
    summary: dict[str, Any],
    play_result: dict[str, Any],
    replay: dict[str, Any],
    replay_result: dict[str, Any],
    strict_summary_trace_hash: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    checks: dict[str, Any] = {}

    play_payload, play_hash = extract_trace_payload_and_hash(play_trace)
    checks["play_trace_hash"] = play_hash
    if play_payload is None:
        failures.append("trace.trace missing object")
    else:
        recomputed = compute_trace_hash(play_payload)
        checks["play_trace_hash_recomputed"] = recomputed
        if play_hash and play_hash != recomputed:
            failures.append(f"play_trace_hash_mismatch expected={play_hash} actual={recomputed}")
        if not play_hash:
            checks["play_trace_hash"] = recomputed

    summary_hash = str(summary.get("trace_hash", ""))
    checks["summary_trace_hash"] = summary_hash
    if strict_summary_trace_hash and summary_hash and checks.get("play_trace_hash") and summary_hash != checks.get("play_trace_hash"):
        failures.append(f"summary_trace_hash_mismatch summary={summary_hash} trace={checks.get('play_trace_hash')}")

    replay_payload, replay_hash = extract_trace_payload_and_hash(replay)
    checks["replay_trace_hash"] = replay_hash
    if replay_payload is None:
        failures.append("replay.trace missing object")
    else:
        replay_recomputed = compute_trace_hash(replay_payload)
        checks["replay_trace_hash_recomputed"] = replay_recomputed
        if replay_hash and replay_hash != replay_recomputed:
            failures.append(f"replay_trace_hash_mismatch expected={replay_hash} actual={replay_recomputed}")
        if not replay_hash:
            checks["replay_trace_hash"] = replay_recomputed

    checks["play_result_ok"] = bool(play_result.get("ok", False))
    checks["replay_result_ok"] = bool(replay_result.get("ok", False))
    if not checks["play_result_ok"]:
        failures.append("play_result.ok is false")
    if not checks["replay_result_ok"]:
        failures.append("replay_result.ok is false")
    return failures, checks
