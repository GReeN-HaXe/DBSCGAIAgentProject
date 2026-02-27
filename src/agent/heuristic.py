from __future__ import annotations

from dataclasses import asdict, dataclass

from src.agent.evaluator import evaluate_state
from src.agent.policy import AgentPolicy
from src.game import Action, ActionType, GameState


@dataclass(frozen=True)
class ScoredAction:
    action: Action
    score: float
    reason: str


@dataclass(frozen=True)
class ActionWeights:
    pass_counter: float = 200.0
    end_charge: float = 180.0
    resolve_battle: float = 170.0
    end_step: float = 160.0
    play_base: float = 95.0
    play_energy_scale: float = 1.25
    play_unison_bonus: float = 4.0
    play_battle_bonus: float = 2.0
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
        if action.action_type == ActionType.PASS_COUNTER_WINDOW:
            return w.pass_counter, "pass_counter_window"
        if action.action_type == ActionType.END_CHARGE:
            return w.end_charge, "end_charge_phase"
        if action.action_type == ActionType.RESOLVE_BATTLE:
            return w.resolve_battle, "resolve_battle_step"
        if action.action_type in {ActionType.END_OFFENSE_STEP, ActionType.END_DEFENSE_STEP}:
            return w.end_step, "advance_battle_step"

        if action.action_type == ActionType.PLAY_CARD_FROM_HAND:
            score = w.play_base if self.prefer_play else (w.play_base - 30.0)
            player = state.players[action.player_id]
            if action.hand_index is not None and 0 <= action.hand_index < len(player.hand):
                card = player.hand[action.hand_index]
                score += float(card.energy_cost or 0) * w.play_energy_scale
                ctype = (card.card_type or "").upper()
                if "UNISON" in ctype:
                    score += w.play_unison_bonus
                elif "BATTLE" in ctype:
                    score += w.play_battle_bonus
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
            return w.activate_skill, "activate_skill"
        if action.action_type == ActionType.COMBO_FROM_HAND:
            return w.combo, "combo_from_hand"
        if action.action_type == ActionType.END_TURN:
            return w.end_turn, "end_turn"
        return 0.0, "fallback"
