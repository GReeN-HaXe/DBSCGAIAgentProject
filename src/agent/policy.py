from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.game import Action, GameState


class AgentPolicy(Protocol):
    def choose_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        ...


@dataclass(frozen=True)
class PolicyContext:
    player_id: int
