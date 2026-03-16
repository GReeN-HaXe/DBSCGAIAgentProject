from __future__ import annotations

from dataclasses import asdict, dataclass

from src.agent.evaluator import evaluate_state
from src.agent.policy import AgentPolicy
from src.game import Action, ActionType, GameState
from src.game.state import CardInstance


@dataclass(frozen=True)
class ScoredAction:
    action: Action
    score: float
    reason: str


@dataclass(frozen=True)
class ActionWeights:
    declare_secret_auto: float = 210.0
    ignore_secret_auto: float = 15.0
    pass_counter: float = 200.0
    end_charge: float = 180.0
    charge_base: float = 205.0
    charge_skip_penalty: float = 140.0
    charge_duplicate_bonus: float = 15.0
    charge_high_cost_bonus: float = 12.0
    charge_low_cost_penalty: float = 18.0
    charge_combo_keep_penalty: float = 85.0
    charge_counter_keep_penalty: float = 70.0
    charge_skill_keep_penalty: float = 30.0
    charge_draw_keep_penalty: float = 25.0
    resolve_battle: float = 170.0
    end_step: float = 160.0
    play_base: float = 95.0
    play_energy_scale: float = 1.25
    play_unison_bonus: float = 4.0
    play_battle_bonus: float = 2.0
    play_curve_bonus: float = 16.0
    play_draw_bonus: float = 22.0
    play_zero_energy_penalty: float = 6.0
    attack_base: float = 90.0
    attack_leader_bonus: float = 8.0
    attack_leader_attacker_bonus: float = 1.0
    attack_battle_unison_attacker_bonus: float = 2.0
    activate_skill: float = 80.0
    combo: float = 65.0
    end_turn: float = 10.0


PROFILE_PRESETS: dict[str, ActionWeights] = {
    "balanced": ActionWeights(),
    "aggressive": ActionWeights(
        play_base=85.0,
        attack_base=115.0,
        attack_leader_bonus=10.0,
        combo=75.0,
        end_turn=5.0,
    ),
    "control": ActionWeights(
        play_base=108.0,
        attack_base=72.0,
        activate_skill=92.0,
        combo=55.0,
        end_turn=16.0,
    ),
}


def merge_action_weights(profile: str, overrides: dict[str, float] | None = None) -> ActionWeights:
    base = PROFILE_PRESETS.get(profile, PROFILE_PRESETS["balanced"])
    if not overrides:
        return base
    payload = asdict(base)
    for key, value in overrides.items():
        if key in payload:
            payload[key] = float(value)
    return ActionWeights(**payload)


@dataclass
class HeuristicPolicy(AgentPolicy):
    profile: str = "balanced"
    action_weights: ActionWeights | None = None
    prefer_attack: bool = True
    prefer_play: bool = True

    def _weights(self) -> ActionWeights:
        if self.action_weights is not None:
            return self.action_weights
        return merge_action_weights(self.profile)

    def choose_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        if not legal_actions:
            raise ValueError("No legal actions available for policy decision.")
        ranked = self.rank_actions(state, legal_actions)
        return ranked[0].action

    def rank_actions(self, state: GameState, legal_actions: list[Action]) -> list[ScoredAction]:
        if not legal_actions:
            return []
        player_id = legal_actions[0].player_id
        state_score = evaluate_state(state, player_id=player_id)
        scored: list[tuple[int, ScoredAction]] = []
        for i, action in enumerate(legal_actions):
            raw_score, reason = self.score_action_with_reason(state, action)
            score = raw_score + (state_score * 0.0001)
            scored.append((i, ScoredAction(action=action, score=score, reason=reason)))
        scored.sort(key=lambda x: (-x[1].score, x[0]))
        return [item for _, item in scored]

    def score_action(self, state: GameState, action: Action) -> float:
        score, _ = self.score_action_with_reason(state, action)
        return score

    def score_action_with_reason(self, state: GameState, action: Action) -> tuple[float, str]:
        w = self._weights()
        score = 0.0
        if action.action_type == ActionType.DECLARE_SECRET_AUTO:
            return w.declare_secret_auto, "declare_secret_auto"
        if action.action_type == ActionType.IGNORE_SECRET_AUTO:
            return w.ignore_secret_auto, "ignore_secret_auto"
        if action.action_type == ActionType.PASS_COUNTER_WINDOW:
            return w.pass_counter, "pass_counter_window"
        if action.action_type == ActionType.END_CHARGE:
            player = state.players[action.player_id]
            if not player.has_charged_this_turn and len(player.hand) > 0:
                return max(0.0, w.end_charge - w.charge_skip_penalty), "end_charge_without_charge_penalty"
            return w.end_charge, "end_charge_phase"
        if action.action_type == ActionType.RESOLVE_BATTLE:
            return w.resolve_battle, "resolve_battle_step"
        if action.action_type in {ActionType.END_OFFENSE_STEP, ActionType.END_DEFENSE_STEP}:
            return w.end_step, "advance_battle_step"
        if action.action_type == ActionType.CHARGE_FROM_HAND:
            player = state.players[action.player_id]
            if action.hand_index is None or not (0 <= action.hand_index < len(player.hand)):
                return 0.0, "charge_invalid"
            card = player.hand[action.hand_index]
            score = w.charge_base
            if not player.has_charged_this_turn:
                score += 20.0
            duplicate_count = sum(1 for candidate in player.hand if candidate.card_id == card.card_id)
            if duplicate_count > 1:
                score += w.charge_duplicate_bonus
            energy_cost = int(card.energy_cost or 0)
            if energy_cost >= 4:
                score += w.charge_high_cost_bonus
            elif energy_cost <= 1:
                score -= w.charge_low_cost_penalty
            if int(card.combo_power or 0) >= 10000:
                score -= w.charge_combo_keep_penalty
            elif int(card.combo_power or 0) >= 5000:
                score -= (w.charge_combo_keep_penalty * 0.35)
            if card.has_counter:
                score -= w.charge_counter_keep_penalty
            if card.has_activate_main or card.has_activate_battle:
                score -= w.charge_skill_keep_penalty
            if card.has_draw or card.auto_draw_on_play or card.auto_draw_on_attack:
                score -= w.charge_draw_keep_penalty
            if energy_cost <= max(1, len(player.energy) + 1):
                score -= 8.0
            return score, "charge_from_hand"

        if action.action_type == ActionType.PLAY_CARD_FROM_HAND:
            score = w.play_base if self.prefer_play else (w.play_base - 30.0)
            player = state.players[action.player_id]
            if action.hand_index is not None and 0 <= action.hand_index < len(player.hand):
                card = player.hand[action.hand_index]
                energy_cost = float(card.energy_cost or 0)
                active_energy = sum(1 for energy in player.energy if not energy.resting) + int(player.energy_markers)
                score += energy_cost * w.play_energy_scale
                ctype = (card.card_type or "").upper()
                if "UNISON" in ctype:
                    score += w.play_unison_bonus
                elif "BATTLE" in ctype:
                    score += w.play_battle_bonus
                if energy_cost > 0 and active_energy == int(energy_cost):
                    score += w.play_curve_bonus
                if energy_cost == 0:
                    score -= w.play_zero_energy_penalty
                if card.has_draw or card.auto_draw_on_play:
                    score += w.play_draw_bonus
                if card.has_activate_main or card.has_activate_battle:
                    score += 10.0
                if card.has_auto:
                    score += 8.0
                if card.has_permanent:
                    score += 6.0
                if card.has_counter:
                    score += 4.0
            return score, "play_card_from_hand"

        if action.action_type == ActionType.DECLARE_ATTACK:
            score = w.attack_base if self.prefer_attack else (w.attack_base - 30.0)
            if action.target_zone == "leader":
                score += w.attack_leader_bonus
            if action.attacker_zone == "leader":
                score += w.attack_leader_attacker_bonus
            else:
                score += w.attack_battle_unison_attacker_bonus
            return score, "declare_attack"

        if action.action_type in {ActionType.ACTIVATE_MAIN_SKILL, ActionType.ACTIVATE_BATTLE_SKILL}:
            score = w.activate_skill
            source = self._resolve_source_card(state, action)
            if source is not None:
                if source.energy_cost == 0:
                    score += 8.0
                if source.has_draw or source.auto_draw_on_play or source.auto_draw_on_attack:
                    score += 12.0
                if source.has_auto:
                    score += 6.0
                if source.has_permanent:
                    score += 4.0
                if source.card_type == "UNISON" and getattr(source, "markers", 0) > 0:
                    score += 6.0
            return score, "activate_skill"
        if action.action_type == ActionType.AWAKEN:
            return w.activate_skill + 25.0, "awaken_leader"
        if action.action_type == ActionType.COMBO_FROM_HAND:
            return w.combo, "combo_from_hand"
        if action.action_type == ActionType.END_TURN:
            return w.end_turn, "end_turn"
        return 0.0, "fallback"

    @staticmethod
    def _resolve_source_card(state: GameState, action: Action) -> CardInstance | None:
        player = state.players.get(action.player_id)
        if player is None:
            return None
        if action.source_zone == "leader":
            return player.leader_area
        if action.source_zone == "battle" and action.source_index is not None and 0 <= action.source_index < len(player.battle_area):
            return player.battle_area[action.source_index]
        if action.source_zone == "unison" and action.source_index is not None and 0 <= action.source_index < len(player.unison_area):
            return player.unison_area[action.source_index]
        return None
