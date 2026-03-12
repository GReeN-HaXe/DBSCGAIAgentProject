from __future__ import annotations

from typing import Any

from src.agent.dataset import build_phase7_dataset
from src.agent.simulator import SimulationResult, simulation_result_to_dict


def simulation_result_to_phase7_trace_artifact(
    result: SimulationResult,
    *,
    p1_profile: str,
    p2_profile: str,
    source_name: str,
    setup_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    trace_rows: list[dict[str, object]] = []
    for item in simulation_result_to_dict(result).get("decision_trace", []):
        if not isinstance(item, dict):
            continue
        player_id = int(item.get("actor_player_id", 0) or 0)
        trace_rows.append(
            {
                "actor_kind": "ai",
                "player_id": player_id,
                "turn_number": int(item.get("turn_number", 0) or 0),
                "phase": str(item.get("phase", "")),
                "action": str(item.get("chosen_action_text", item.get("chosen_action_type", ""))),
                "action_type": str(item.get("chosen_action_type", "")),
                "state_snapshot": dict(item.get("state_snapshot", {})) if isinstance(item.get("state_snapshot"), dict) else {},
            }
        )
    payload = {
        "total_actions": int(result.total_actions),
        "winner_id": result.final_state.winner_id,
        "final_turn_number": int(result.final_state.turn_number),
        "final_phase": result.final_state.phase.value,
        "human_player_id": None,
        "setup": {
            "mode": "self_play",
            "source_name": str(source_name),
            "p1_profile": str(p1_profile),
            "p2_profile": str(p2_profile),
            "profile_pair": f"{p1_profile}_vs_{p2_profile}",
            **(dict(setup_metadata) if isinstance(setup_metadata, dict) else {}),
        },
        "actions": trace_rows,
    }
    return {"trace": payload}


def slice_phase7_dataset(dataset: dict[str, object], *, slice_field: str) -> dict[str, dict[str, object]]:
    examples = dataset.get("examples", [])
    if not isinstance(examples, list):
        examples = []

    def _extract(row: dict[str, Any], path: str) -> object:
        current: object = row
        for part in path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    grouped: dict[str, list[dict[str, object]]] = {}
    for row in examples:
        if not isinstance(row, dict):
            continue
        value = _extract(row, slice_field)
        key = "unknown" if value in {None, ""} else str(value)
        grouped.setdefault(key, []).append(dict(row))

    out: dict[str, dict[str, object]] = {}
    for key, rows in grouped.items():
        out[key] = {
            "schema_version": str(dataset.get("schema_version", "")),
            "source_dataset_schema_version": str(dataset.get("schema_version", "")),
            "slice_field": str(slice_field),
            "slice_value": str(key),
            "example_count": len(rows),
            "examples": rows,
        }
    return out


def merge_phase7_trace_artifacts(
    artifacts: list[dict[str, object]],
    *,
    source_names: list[str],
    validation_ratio: float = 0.2,
) -> dict[str, object]:
    return build_phase7_dataset(
        [dict(item) for item in artifacts],
        source_names=[str(item) for item in source_names],
        validation_ratio=float(validation_ratio),
    )
