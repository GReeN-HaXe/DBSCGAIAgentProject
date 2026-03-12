from __future__ import annotations

from typing import Any

from src.game import GameState


def build_compact_match_summary(
    *,
    state: GameState,
    total_actions: int,
    human_player_id: int,
    ai_profile: str,
    checkpoint_tail_count: int = 20,
    setup_metadata: dict[str, Any] | None = None,
    turn_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cp_names = [cp.name for cp in state.checkpoints[-max(1, int(checkpoint_tail_count)) :]]
    unresolved = [r for r in state.effect_resolutions if not r.resolved]
    summary = {
        "winner_id": state.winner_id,
        "total_actions": int(total_actions),
        "human_player_id": int(human_player_id),
        "ai_profile": str(ai_profile),
        "final_turn_number": int(state.turn_number),
        "final_phase": state.phase.value,
        "checkpoint_count": len(state.checkpoints),
        "checkpoint_tail": cp_names,
        "effect_resolution_count": len(state.effect_resolutions),
        "effect_unresolved_count": len(unresolved),
        "setup": dict(setup_metadata or {}),
    }
    if turn_history is not None:
        summary["turn_history"] = list(turn_history)
    return summary


def evaluate_match_expectations(
    *,
    summary: dict[str, Any],
    expect_winner: int | None = None,
    expect_final_turn: int | None = None,
    expect_completed: bool | None = None,
    max_unresolved_effects: int | None = None,
) -> list[str]:
    failures: list[str] = []
    winner = summary.get("winner_id")
    final_turn = int(summary.get("final_turn_number", 0))
    unresolved = int(summary.get("effect_unresolved_count", 0))
    completed = winner is not None

    if expect_winner is not None and winner != int(expect_winner):
        failures.append(f"winner expected={expect_winner} actual={winner}")
    if expect_final_turn is not None and final_turn != int(expect_final_turn):
        failures.append(f"final_turn expected={expect_final_turn} actual={final_turn}")
    if expect_completed is not None and bool(expect_completed) != bool(completed):
        failures.append(f"completed expected={bool(expect_completed)} actual={bool(completed)}")
    if max_unresolved_effects is not None and unresolved > int(max_unresolved_effects):
        failures.append(f"effect_unresolved_count expected<={max_unresolved_effects} actual={unresolved}")
    return failures
