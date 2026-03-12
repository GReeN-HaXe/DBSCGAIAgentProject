from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ActionType(str, Enum):
    CHARGE_FROM_HAND = "charge_from_hand"
    END_CHARGE = "end_charge"
    PLAY_CARD_FROM_HAND = "play_card_from_hand"
    AWAKEN = "awaken"
    ACTIVATE_MAIN_SKILL = "activate_main_skill"
    ACTIVATE_BATTLE_SKILL = "activate_battle_skill"
    COMBO_FROM_HAND = "combo_from_hand"
    END_OFFENSE_STEP = "end_offense_step"
    END_DEFENSE_STEP = "end_defense_step"
    DECLARE_COUNTER_FROM_HAND = "declare_counter_from_hand"
    PASS_COUNTER_WINDOW = "pass_counter_window"
    DECLARE_ATTACK = "declare_attack"
    RESOLVE_BATTLE = "resolve_battle"
    END_TURN = "end_turn"


@dataclass(frozen=True)
class Action:
    action_type: ActionType
    player_id: int
    hand_index: Optional[int] = None
    source_zone: Optional[str] = None
    source_index: Optional[int] = None
    attacker_zone: Optional[str] = None
    attacker_index: Optional[int] = None
    target_player_id: Optional[int] = None
    target_zone: Optional[str] = None
    target_index: Optional[int] = None
