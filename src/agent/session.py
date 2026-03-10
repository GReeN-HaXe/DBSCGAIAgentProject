from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Callable

from src.agent.heuristic import HeuristicPolicy
from src.game import Action, CardInstance, GameState, RulesEngine
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


CardNameResolver = Callable[[int], str]


def decision_owner_for_state(state: GameState) -> int:
    if state.counter_window is not None:
        return int(state.counter_window.responder_player_id)
    if state.attack_context is not None and state.battle_step is not None:
        if state.battle_step.value == "offense":
            return int(state.attack_context.attacker_player_id)
        if state.battle_step.value == "defense":
            return int(state.attack_context.target_player_id)
        if state.battle_step.value in {"damage", "battle_end"}:
            return int(state.attack_context.attacker_player_id)
    return int(state.active_player)


def _resolve_zone_card_for_action(state: GameState, *, player_id: int, zone: str | None, index: int | None) -> CardInstance | None:
    if zone is None:
        return None
    player = state.players.get(player_id)
    if player is None:
        return None
    if zone == "leader":
        return player.leader_area
    if zone == "battle" and index is not None and 0 <= index < len(player.battle_area):
        return player.battle_area[index]
    if zone == "unison" and index is not None and 0 <= index < len(player.unison_area):
        return player.unison_area[index]
    return None


def _card_label(card: CardInstance | None, card_name_resolver: CardNameResolver | None = None) -> str:
    if card is None:
        return "unknown-card"
    if card_name_resolver is not None:
        try:
            label = str(card_name_resolver(int(card.card_id))).strip()
            if label:
                return label
        except Exception:
            pass
    return f"card_id={card.card_id}"


def describe_action(
    action: Action,
    *,
    state: GameState | None = None,
    card_name_resolver: CardNameResolver | None = None,
) -> str:
    parts = [action.action_type.value]
    if action.hand_index is not None:
        parts.append(f"hand_index={action.hand_index}")
        if state is not None:
            player = state.players.get(action.player_id)
            if player is not None and 0 <= action.hand_index < len(player.hand):
                parts.append(f"card={_card_label(player.hand[action.hand_index], card_name_resolver)}")
    if action.source_zone is not None:
        parts.append(f"source_zone={action.source_zone}")
    if action.source_index is not None:
        parts.append(f"source_index={action.source_index}")
    if state is not None and action.source_zone is not None:
        source_card = _resolve_zone_card_for_action(state, player_id=action.player_id, zone=action.source_zone, index=action.source_index)
        if source_card is not None:
            parts.append(f"source_card={_card_label(source_card, card_name_resolver)}")
    if action.attacker_zone is not None:
        parts.append(f"attacker_zone={action.attacker_zone}")
    if action.attacker_index is not None:
        parts.append(f"attacker_index={action.attacker_index}")
    if state is not None and action.attacker_zone is not None:
        attacker_card = _resolve_zone_card_for_action(state, player_id=action.player_id, zone=action.attacker_zone, index=action.attacker_index)
        if attacker_card is not None:
            parts.append(f"attacker_card={_card_label(attacker_card, card_name_resolver)}")
    if action.target_player_id is not None:
        parts.append(f"target_player={action.target_player_id}")
    if action.target_zone is not None:
        parts.append(f"target_zone={action.target_zone}")
    if action.target_index is not None:
        parts.append(f"target_index={action.target_index}")
    if state is not None and action.target_player_id is not None and action.target_zone is not None:
        target_card = _resolve_zone_card_for_action(state, player_id=action.target_player_id, zone=action.target_zone, index=action.target_index)
        if target_card is not None:
            parts.append(f"target_card={_card_label(target_card, card_name_resolver)}")
    return " ".join(parts)


def summarize_state_for_cli(
    state: GameState,
    *,
    card_name_resolver: CardNameResolver | None = None,
    reveal_hand_player_id: int | None = None,
    reveal_hand_player_ids: tuple[int, ...] | None = None,
) -> str:
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
    players_to_reveal: list[int] = []
    if reveal_hand_player_ids is not None:
        players_to_reveal.extend(int(player_id) for player_id in reveal_hand_player_ids if player_id in state.players)
    elif reveal_hand_player_id in state.players:
        players_to_reveal.append(int(reveal_hand_player_id))
    for player_id in players_to_reveal:
        player = state.players[player_id]
        rendered_hand = ", ".join(
            f"[{index}] {_card_label(card, card_name_resolver)}"
            for index, card in enumerate(player.hand)
        )
        lines.append(f"P{player_id} hand_cards={rendered_hand}")
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
    _last_ai_signature: str = ""
    _last_ai_repeat_count: int = 0

    def __post_init__(self) -> None:
        if self.action_trace is None:
            self.action_trace = []
        if self.setup_metadata is None:
            self.setup_metadata = {}

    def is_over(self) -> bool:
        return self.state.winner_id is not None

    def current_player(self) -> int:
        return decision_owner_for_state(self.state)

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
        _, chosen = self.step_ai_once_with_context()
        return chosen

    def step_ai_once_with_context(self) -> tuple[GameState, Action]:
        ai_player_id = 1 if self.human_player_id == 2 else 2
        legal = self.legal_actions_for(ai_player_id)
        if not legal:
            raise ValueError("AI player has no legal actions in current state.")
        chosen = self._choose_ai_action_with_loop_guard(legal)
        state_before = self.state
        self._record_action(chosen, actor_kind="ai")
        self.state = self.engine.apply_action(self.state, chosen)
        self.total_actions += 1
        return state_before, chosen

    def step_ai_until_human_turn(self, *, max_ai_actions: int = 200) -> list[Action]:
        return [entry["action"] for entry in self.step_ai_until_human_turn_with_context(max_ai_actions=max_ai_actions)]

    def step_ai_until_human_turn_with_context(self, *, max_ai_actions: int = 200) -> list[dict[str, object]]:
        ai_player_id = 1 if self.human_player_id == 2 else 2
        actions: list[dict[str, object]] = []
        while not self.is_over() and self.current_player() == ai_player_id:
            if len(actions) >= max_ai_actions:
                break
            if not self.legal_actions_for(ai_player_id):
                break
            state_before, action = self.step_ai_once_with_context()
            actions.append({"state_before": state_before, "action": action})
        return actions

    def _choose_ai_action_with_loop_guard(self, legal: list[Action]) -> Action:
        chosen = self.ai_policy.choose_action(self.state, legal)
        signature = self._action_loop_signature(chosen)
        if signature == self._last_ai_signature:
            self._last_ai_repeat_count += 1
        else:
            self._last_ai_signature = signature
            self._last_ai_repeat_count = 1
        if self._last_ai_repeat_count < 2:
            return chosen

        fallback = self._find_ai_fallback_action(legal, chosen)
        if fallback is None:
            return chosen
        fallback_signature = self._action_loop_signature(fallback)
        self._last_ai_signature = fallback_signature
        self._last_ai_repeat_count = 1
        return fallback

    def _find_ai_fallback_action(self, legal: list[Action], chosen: Action) -> Action | None:
        ranked = legal
        rank_actions = getattr(self.ai_policy, "rank_actions", None)
        if callable(rank_actions):
            try:
                ranked = [item.action for item in rank_actions(self.state, legal)]
            except Exception:
                ranked = legal
        preferred_types = {
            "end_turn",
            "end_charge",
            "end_offense_step",
            "end_defense_step",
            "resolve_battle",
            "declare_attack",
            "play_card_from_hand",
            "charge_from_hand",
        }
        chosen_desc = describe_action(chosen)
        for action in ranked:
            if describe_action(action) == chosen_desc:
                continue
            if action.action_type.value in preferred_types:
                return action
        for action in ranked:
            if describe_action(action) != chosen_desc:
                return action
        return None

    def _action_loop_signature(self, action: Action) -> str:
        payload = snapshot_state_for_trace(self.state)
        return json.dumps(payload, sort_keys=True) + "|" + describe_action(action)

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
