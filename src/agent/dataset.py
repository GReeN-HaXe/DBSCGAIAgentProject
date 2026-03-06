from __future__ import annotations

import hashlib
from typing import Any

from src.agent.artifact_checks import extract_trace_payload_and_hash


DATASET_SCHEMA_VERSION = "phase7.v1"


def _coerce_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_trace_source(artifact: dict[str, Any]) -> tuple[dict[str, Any], str]:
    payload, trace_hash = extract_trace_payload_and_hash(artifact)
    if payload is not None:
        return payload, trace_hash
    if isinstance(artifact.get("trace"), dict):
        return dict(artifact["trace"]), str(artifact.get("trace_hash", ""))
    raise ValueError("artifact does not contain a Phase 6 trace payload")


def _extract_state_features(snapshot: object, player_id: int | None) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {}
    players = snapshot.get("players", {})
    if not isinstance(players, dict):
        players = {}
    player_key = None if player_id is None else str(player_id)
    opponent_key = None
    if player_key is not None:
        for key in players.keys():
            if key != player_key:
                opponent_key = str(key)
                break
    player_state = players.get(player_key, {}) if player_key is not None and isinstance(players.get(player_key), dict) else {}
    opponent_state = players.get(opponent_key, {}) if opponent_key is not None and isinstance(players.get(opponent_key), dict) else {}
    return {
        "active_player": _coerce_int(snapshot.get("active_player")),
        "battle_step": snapshot.get("battle_step"),
        "counter_window_kind": snapshot.get("counter_window_kind"),
        "self_hand_size": _coerce_int(player_state.get("hand_size")),
        "self_life_size": _coerce_int(player_state.get("life_size")),
        "self_energy_size": _coerce_int(player_state.get("energy_size")),
        "self_energy_resting_count": _coerce_int(player_state.get("energy_resting_count")),
        "self_battle_size": _coerce_int(player_state.get("battle_size")),
        "self_unison_size": _coerce_int(player_state.get("unison_size")),
        "self_drop_size": _coerce_int(player_state.get("drop_size")),
        "self_warp_size": _coerce_int(player_state.get("warp_size")),
        "opponent_hand_size": _coerce_int(opponent_state.get("hand_size")),
        "opponent_life_size": _coerce_int(opponent_state.get("life_size")),
        "opponent_energy_size": _coerce_int(opponent_state.get("energy_size")),
        "opponent_battle_size": _coerce_int(opponent_state.get("battle_size")),
        "opponent_unison_size": _coerce_int(opponent_state.get("unison_size")),
        "opponent_drop_size": _coerce_int(opponent_state.get("drop_size")),
        "opponent_warp_size": _coerce_int(opponent_state.get("warp_size")),
    }


def _stable_fraction(key: str) -> float:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / float(0xFFFFFFFF)


def _assign_split(trace_hash: str, example_index: int, validation_ratio: float) -> str:
    ratio = max(0.0, min(1.0, float(validation_ratio)))
    key = f"{trace_hash}:{example_index}"
    return "validation" if _stable_fraction(key) < ratio else "train"


def _action_family(action_type: str) -> str:
    if action_type in {"play_card_from_hand", "charge_from_hand"}:
        return "resource_development"
    if action_type in {"declare_attack", "combo_from_hand", "resolve_battle"}:
        return "combat"
    if action_type in {"activate_main_skill", "activate_battle_skill"}:
        return "skill"
    if action_type in {"declare_counter_from_hand", "pass_counter_window"}:
        return "counter"
    if action_type in {"end_charge", "end_offense_step", "end_defense_step", "end_turn"}:
        return "progression"
    return "other"


def _actor_role_bucket(actor_kind: str, human_player_id: int | None, player_id: int | None) -> str:
    if actor_kind == "human":
        return "human"
    if actor_kind == "ai":
        return "ai"
    if human_player_id is not None and player_id is not None:
        return "human" if player_id == human_player_id else "ai"
    return "unknown"


def build_phase7_examples_from_trace_artifact(
    artifact: dict[str, Any],
    *,
    source_name: str = "unknown",
    validation_ratio: float = 0.2,
) -> list[dict[str, Any]]:
    trace_payload, trace_hash = _normalize_trace_source(artifact)
    actions = trace_payload.get("actions", [])
    if not isinstance(actions, list):
        actions = []

    winner_id = _coerce_int(trace_payload.get("winner_id"))
    human_player_id = _coerce_int(trace_payload.get("human_player_id"))
    final_turn_number = _coerce_int(trace_payload.get("final_turn_number"))
    final_phase = str(trace_payload.get("final_phase", ""))
    total_actions = _coerce_int(trace_payload.get("total_actions")) or len(actions)
    setup = trace_payload.get("setup", {})
    if not isinstance(setup, dict):
        setup = {}

    examples: list[dict[str, Any]] = []
    for idx, row in enumerate(actions):
        if not isinstance(row, dict):
            continue
        player_id = _coerce_int(row.get("player_id"))
        actor_kind = str(row.get("actor_kind", "unknown"))
        action_type = str(row.get("action_type", "unknown"))
        state_features = _extract_state_features(row.get("state_snapshot"), player_id)
        did_player_win = (player_id == winner_id) if (player_id is not None and winner_id is not None) else None
        turn_number = _coerce_int(row.get("turn_number"))
        turns_to_end = (
            max(0, int(final_turn_number) - int(turn_number))
            if final_turn_number is not None and turn_number is not None
            else None
        )
        example = {
            "schema_version": DATASET_SCHEMA_VERSION,
            "source_name": source_name,
            "trace_hash": trace_hash,
            "example_index": idx,
            "actor_kind": actor_kind,
            "player_id": player_id,
            "human_player_id": human_player_id,
            "is_human_action": actor_kind == "human",
            "turn_number": turn_number,
            "phase": str(row.get("phase", "")),
            "action_type": action_type,
            "action_family": _action_family(action_type),
            "action_text": str(row.get("action", "")),
            "actor_role_bucket": _actor_role_bucket(actor_kind, human_player_id, player_id),
            "winner_id": winner_id,
            "did_player_win": did_player_win,
            "terminal_reward": 1.0 if did_player_win is True else (-1.0 if did_player_win is False else 0.0),
            "value_target": 1.0 if did_player_win is True else (0.0 if did_player_win is False else None),
            "turns_to_end": turns_to_end,
            "final_turn_number": final_turn_number,
            "final_phase": final_phase,
            "total_actions_in_match": total_actions,
            "split": _assign_split(trace_hash, idx, validation_ratio),
            "setup": dict(setup),
            "state_features": state_features,
        }
        examples.append(example)
    return examples


def build_phase7_trajectories(
    artifacts: list[dict[str, Any]],
    *,
    source_names: list[str] | None = None,
    validation_ratio: float = 0.2,
) -> list[dict[str, Any]]:
    names = list(source_names or [])
    trajectories: list[dict[str, Any]] = []
    for idx, artifact in enumerate(artifacts):
        source_name = names[idx] if idx < len(names) else f"artifact_{idx}"
        trace_payload, trace_hash = _normalize_trace_source(artifact)
        examples = build_phase7_examples_from_trace_artifact(
            artifact,
            source_name=source_name,
            validation_ratio=validation_ratio,
        )
        action_types = [str(row.get("action_type", "unknown")) for row in examples]
        trajectories.append(
            {
                "schema_version": DATASET_SCHEMA_VERSION,
                "source_name": source_name,
                "trace_hash": trace_hash,
                "winner_id": _coerce_int(trace_payload.get("winner_id")),
                "human_player_id": _coerce_int(trace_payload.get("human_player_id")),
                "final_turn_number": _coerce_int(trace_payload.get("final_turn_number")),
                "final_phase": str(trace_payload.get("final_phase", "")),
                "total_actions": _coerce_int(trace_payload.get("total_actions")) or len(examples),
                "setup": dict(trace_payload.get("setup", {})) if isinstance(trace_payload.get("setup"), dict) else {},
                "action_types": action_types,
                "splits_present": sorted({str(row.get("split", "")) for row in examples if row.get("split")}),
                "examples": examples,
            }
        )
    return trajectories


def build_phase7_dataset(
    artifacts: list[dict[str, Any]],
    *,
    source_names: list[str] | None = None,
    validation_ratio: float = 0.2,
) -> dict[str, Any]:
    names = list(source_names or [])
    examples: list[dict[str, Any]] = []
    for idx, artifact in enumerate(artifacts):
        source_name = names[idx] if idx < len(names) else f"artifact_{idx}"
        examples.extend(
            build_phase7_examples_from_trace_artifact(
                artifact,
                source_name=source_name,
                validation_ratio=validation_ratio,
            )
        )
    split_counts = {
        "train": sum(1 for row in examples if row.get("split") == "train"),
        "validation": sum(1 for row in examples if row.get("split") == "validation"),
    }
    trajectories = build_phase7_trajectories(
        artifacts,
        source_names=names if names else None,
        validation_ratio=validation_ratio,
    )
    return {
        "schema_version": DATASET_SCHEMA_VERSION,
        "example_count": len(examples),
        "trajectory_count": len(trajectories),
        "validation_ratio": float(validation_ratio),
        "sources": names if names else [f"artifact_{idx}" for idx in range(len(artifacts))],
        "split_counts": split_counts,
        "trajectories": trajectories,
        "examples": examples,
    }
