from __future__ import annotations

from dataclasses import dataclass

from src.game import GameState


@dataclass(frozen=True)
class StateWeights:
    life: float = 3.0
    hand: float = 1.5
    energy: float = 2.0
    battle: float = 2.5
    unison: float = 3.0


def evaluate_state(state: GameState, *, player_id: int, weights: StateWeights | None = None) -> float:
    w = weights or StateWeights()
    me = state.players[player_id]
    opp = state.players[1 if player_id == 2 else 2]
    my_score = (
        len(me.life) * w.life
        + len(me.hand) * w.hand
        + len(me.energy) * w.energy
        + len(me.battle_area) * w.battle
        + len(me.unison_area) * w.unison
    )
    opp_score = (
        len(opp.life) * w.life
        + len(opp.hand) * w.hand
        + len(opp.energy) * w.energy
        + len(opp.battle_area) * w.battle
        + len(opp.unison_area) * w.unison
    )
    return my_score - opp_score
