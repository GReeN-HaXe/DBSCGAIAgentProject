from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.agent.heuristic import HeuristicPolicy
from src.game import Action, GameState, RulesEngine
from src.game.state_io import load_game_state_json, save_game_state_json


def snapshot_state_for_trace(state: GameState) -> dict[str, object]:
    players: dict[str, object] = {}
    for player_id, player in state.players.items():
        players[str(player_id)] = {
            "hand_size": len(player.hand),
            "life_size": len(player.life),
            "energy_size": len(player.energy),
            "energy_resting_count": sum(1 for card in player.energy if card.resting),
            "z_energy_size": len(player.z_energy),
            "battle_size": len(player.battle_area),
            "battle_resting_count": sum(1 for card in player.battle_area if card.resting),
            "unison_size": len(player.unison_area),
            "combo_size": len(player.combo_area),
            "drop_size": len(player.drop),
            "warp_size": len(player.warp),
            "removed_size": len(player.removed_from_game),
            "deck_size": len(player.deck),
            "has_charged_this_turn": bool(player.has_charged_this_turn),
        }
    return {
        "active_player": int(state.active_player),
        "turn_number": int(state.turn_number),
        "phase": state.phase.value,
        "battle_step": None if state.battle_step is None else state.battle_step.value,
        "winner_id": state.winner_id,
        "counter_window_kind": None if state.counter_window is None else state.counter_window.kind,
        "players": players,
    }


def describe_action(action: Action) -> str:
    parts = [action.action_type.value]
    if action.hand_index is not None:
        parts.append(f"hand_index={action.hand_index}")
    if action.source_zone is not None:
        parts.append(f"source_zone={action.source_zone}")
    if action.source_index is not None:
        parts.append(f"source_index={action.source_index}")
    if action.attacker_zone is not None:
        parts.append(f"attacker_zone={action.attacker_zone}")
    if action.attacker_index is not None:
        parts.append(f"attacker_index={action.attacker_index}")
    if action.target_player_id is not None:
        parts.append(f"target_player={action.target_player_id}")
    if action.target_zone is not None:
        parts.append(f"target_zone={action.target_zone}")
    if action.target_index is not None:
        parts.append(f"target_index={action.target_index}")
    return " ".join(parts)


def summarize_state_for_cli(state: GameState) -> str:
    p1 = state.players[1]
    p2 = state.players[2]
    lines = [
        f"turn={state.turn_number} phase={state.phase.value} active=P{state.active_player} winner={state.winner_id}",
        (
            "P1 "
            f"hand={len(p1.hand)} life={len(p1.life)} energy={len(p1.energy)} "
            f"battle={len(p1.battle_area)} unison={len(p1.unison_area)}"
        ),
        (
            "P2 "
            f"hand={len(p2.hand)} life={len(p2.life)} energy={len(p2.energy)} "
            f"battle={len(p2.battle_area)} unison={len(p2.unison_area)}"
        ),
    ]
    return "\n".join(lines)


@dataclass
class HumanVsAiSession:
    engine: RulesEngine
    state: GameState
    human_player_id: int
    ai_policy: HeuristicPolicy
    total_actions: int = 0
    action_trace: list[dict[str, object]] | None = None
    setup_metadata: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if self.action_trace is None:
            self.action_trace = []
        if self.setup_metadata is None:
            self.setup_metadata = {}

    def is_over(self) -> bool:
        return self.state.winner_id is not None

    def current_player(self) -> int:
        return self.state.active_player

    def legal_actions_for(self, player_id: int) -> list[Action]:
        return self.engine.get_legal_actions(self.state, player_id)

    def legal_actions_for_human(self) -> list[Action]:
        return self.legal_actions_for(self.human_player_id)

    def apply_human_action_by_index(self, action_index: int) -> Action:
        legal = self.legal_actions_for_human()
        if not legal:
            raise ValueError("Human player has no legal actions in current state.")
        if action_index < 0 or action_index >= len(legal):
            raise IndexError(f"Action index out of range: {action_index}")
        chosen = legal[action_index]
        self._record_action(chosen, actor_kind="human")
        self.state = self.engine.apply_action(self.state, chosen)
        self.total_actions += 1
        return chosen

    def step_ai_once(self) -> Action:
        ai_player_id = 1 if self.human_player_id == 2 else 2
        legal = self.legal_actions_for(ai_player_id)
        if not legal:
            raise ValueError("AI player has no legal actions in current state.")
        chosen = self.ai_policy.choose_action(self.state, legal)
        self._record_action(chosen, actor_kind="ai")
        self.state = self.engine.apply_action(self.state, chosen)
        self.total_actions += 1
        return chosen

    def step_ai_until_human_turn(self, *, max_ai_actions: int = 200) -> list[Action]:
        ai_player_id = 1 if self.human_player_id == 2 else 2
        actions: list[Action] = []
        while not self.is_over() and self.current_player() == ai_player_id:
            if len(actions) >= max_ai_actions:
                break
            if not self.legal_actions_for(ai_player_id):
                break
            actions.append(self.step_ai_once())
        return actions

    def _record_action(self, action: Action, *, actor_kind: str) -> None:
        assert self.action_trace is not None
        self.action_trace.append(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "actor_kind": actor_kind,
                "player_id": int(action.player_id),
                "turn_number": int(self.state.turn_number),
                "phase": self.state.phase.value,
                "action": describe_action(action),
                "action_type": action.action_type.value,
                "state_snapshot": snapshot_state_for_trace(self.state),
            }
        )

    def to_trace_payload(self) -> dict[str, object]:
        return {
            "total_actions": int(self.total_actions),
            "winner_id": self.state.winner_id,
            "final_turn_number": int(self.state.turn_number),
            "final_phase": self.state.phase.value,
            "human_player_id": int(self.human_player_id),
            "setup": dict(self.setup_metadata or {}),
            "actions": list(self.action_trace or []),
        }

    def save_state(self, path: Path) -> None:
        save_game_state_json(self.state, path)

    def load_state(self, path: Path) -> None:
        self.state = load_game_state_json(path)
