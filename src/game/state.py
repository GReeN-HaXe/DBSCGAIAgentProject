from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class TurnPhase(str, Enum):
    CHARGE = "charge"
    MAIN = "main"
    END = "end"


class BattleStep(str, Enum):
    OFFENSE = "offense"
    DEFENSE = "defense"
    DAMAGE = "damage"
    BATTLE_END = "battle_end"


@dataclass
class CardInstance:
    instance_id: int
    card_id: int
    owner_id: int
    card_number: str = ""
    resting: bool = False
    hidden_mode: bool = False
    attacked_this_turn: bool = False
    attack_count_this_turn: int = 0
    power: int = 15000
    card_type: str = "BATTLE"
    color: Optional[str] = None
    energy_cost_raw: Optional[str] = None
    energy_cost: Optional[int] = None
    combo_cost: Optional[int] = None
    combo_power: Optional[int] = None
    keywords: Tuple[str, ...] = ()
    has_counter: bool = False
    counter_modes: Tuple[str, ...] = ()
    has_counter_attack: bool = False
    has_counter_battle_card_attack: bool = False
    has_counter_play: bool = False
    has_counter_counter: bool = False
    has_activate_main: bool = False
    has_activate_battle: bool = False
    has_auto: bool = False
    has_permanent: bool = False
    has_draw: bool = False
    max_draw: Optional[int] = None
    auto_once_per_turn: bool = False
    auto_draw_on_play: bool = False
    auto_draw_on_attack: bool = False
    has_barrier: bool = False
    z_energy_cost: Optional[int] = None
    markers: int = 0
    specified_costs: Tuple[Tuple[str, int], ...] = ()
    skill_text_raw: Optional[str] = None
    has_awaken: bool = False
    awakened: bool = False
    activate_limit_once_per_turn: bool = False
    has_super_combo: bool = False
    sparking_threshold: Optional[int] = None
    temporary_keywords: Tuple[str, ...] = ()
    temporary_power_delta: int = 0
    battle_temporary_keywords: Tuple[str, ...] = ()
    battle_temporary_power_delta: int = 0
    delayed_temporary_keywords: Tuple[str, ...] = ()
    stacked_card_ids: Tuple[int, ...] = ()
    traits: Tuple[str, ...] = ()
    characters: Tuple[str, ...] = ()


@dataclass
class ZDeckCard:
    card_id: int
    owner_id: int
    face_up: bool = False
    card_name: str = ""
    card_type: str = "BATTLE"
    color: Optional[str] = None
    energy_cost: Optional[int] = None
    traits: Tuple[str, ...] = ()
    characters: Tuple[str, ...] = ()


@dataclass
class PlayerState:
    player_id: int
    leader_card_id: int
    leader_area: CardInstance
    deck: list[int] = field(default_factory=list)
    z_deck: list[ZDeckCard] = field(default_factory=list)
    hand: list[CardInstance] = field(default_factory=list)
    life: list[CardInstance] = field(default_factory=list)
    energy: list[CardInstance] = field(default_factory=list)
    z_energy: list[CardInstance] = field(default_factory=list)
    battle_area: list[CardInstance] = field(default_factory=list)
    unison_area: list[CardInstance] = field(default_factory=list)
    combo_area: list[CardInstance] = field(default_factory=list)
    drop: list[CardInstance] = field(default_factory=list)
    warp: list[CardInstance] = field(default_factory=list)
    removed_from_game: list[CardInstance] = field(default_factory=list)
    has_charged_this_turn: bool = False
    energy_markers: int = 0


@dataclass(frozen=True)
class CheckpointEvent:
    index: int
    turn_number: int
    phase: TurnPhase
    active_player: int
    name: str


@dataclass(frozen=True)
class AttackContext:
    attacker_player_id: int
    attacker_zone: str
    attacker_instance_id: int
    target_player_id: int
    target_zone: str
    target_instance_id: int


@dataclass(frozen=True)
class PendingAction:
    action_type: str
    actor_player_id: int
    payload: dict[str, int | str | None]


@dataclass(frozen=True)
class CounterWindow:
    kind: str
    responder_player_id: int
    pending_action: PendingAction


@dataclass(frozen=True)
class CounterMotion:
    motion_id: int
    player_id: int
    card_instance_id: int
    modes: Tuple[str, ...]
    payload: dict[str, int | str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class CounterResolution:
    motion_id: int
    player_id: int
    pending_action_type: str
    resolved: bool
    negated_motion_id: int | None
    resolution_order: int | None = None
    applied_effects: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CounterMotionTrace:
    motion_id: int
    turn_number: int
    phase: TurnPhase
    window_kind: str
    pending_action_type: str
    player_id: int
    card_instance_id: int
    modes: Tuple[str, ...]
    resolved: bool | None = None
    negated_motion_id: int | None = None
    resolution_order: int | None = None
    applied_effects: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EffectEvent:
    event_id: int
    turn_number: int
    phase: TurnPhase
    name: str
    actor_player_id: int | None
    payload: dict[str, int | str | None]


@dataclass(frozen=True)
class EffectRegistration:
    effect_id: int
    owner_player_id: int
    source_instance_id: int
    source_card_id: int
    source_zone: str
    trigger: str
    handler_id: str
    handler_params: dict[str, int | str | bool] = field(default_factory=dict)
    source_card_number: str = ""
    once_per_turn: bool = False
    limit_per_turn: int | None = None
    limit_scope: str = "card_number"
    triggers_this_turn: int = 0


@dataclass(frozen=True)
class PendingEffect:
    effect_id: int
    event_id: int


@dataclass(frozen=True)
class EffectResolution:
    effect_id: int
    event_id: int
    resolved: bool
    reason: str


@dataclass(frozen=True)
class DeferredSecretAuto:
    secret_auto_id: int
    owner_player_id: int
    source_instance_id: int
    source_card_id: int
    source_card_number: str
    source_zone: str
    trigger: str
    handler_id: str
    deferred_turn_number: int
    deferred_phase: TurnPhase
    origin_zone: str = ""
    handler_params: dict[str, int | str | bool] = field(default_factory=dict)
    once_per_turn: bool = False
    limit_per_turn: int | None = None
    limit_scope: str = "card_number"


@dataclass(frozen=True)
class SecretAutoOpportunity:
    opportunity_id: int
    secret_auto_id: int
    owner_player_id: int
    source_instance_id: int
    source_card_id: int
    source_card_number: str
    source_zone: str
    trigger: str
    handler_id: str
    event_id: int
    event_name: str
    created_turn_number: int
    created_phase: TurnPhase
    origin_zone: str = ""
    handler_params: dict[str, int | str | bool] = field(default_factory=dict)
    once_per_turn: bool = False
    limit_per_turn: int | None = None
    limit_scope: str = "card_number"
    status: str = "pending"


@dataclass(frozen=True)
class DelayedModeSwitch:
    owner_player_id: int
    target_instance_id: int
    trigger_kind: str
    trigger_player_id: int
    switch_to_hidden: bool


@dataclass(frozen=True)
class DelayedKeywordClear:
    owner_player_id: int
    target_instance_id: int
    trigger_player_id: int
    keyword: str


@dataclass
class GameState:
    players: dict[int, PlayerState]
    active_player: int
    first_player_id: int
    turn_number: int = 1
    phase: TurnPhase = TurnPhase.CHARGE
    winner_id: Optional[int] = None
    battle_step: Optional[BattleStep] = None
    attack_context: Optional[AttackContext] = None
    counter_window: Optional[CounterWindow] = None
    counter_chain: list[CounterMotion] = field(default_factory=list)
    counter_resolutions: list[CounterResolution] = field(default_factory=list)
    counter_motion_trace: list[CounterMotionTrace] = field(default_factory=list)
    next_counter_motion_id: int = 1
    next_instance_id: int = 1
    next_checkpoint_index: int = 1
    next_effect_id: int = 1
    next_effect_event_id: int = 1
    next_secret_auto_id: int = 1
    next_secret_auto_opportunity_id: int = 1
    log: list[str] = field(default_factory=list)
    checkpoints: list[CheckpointEvent] = field(default_factory=list)
    effect_registry: list[EffectRegistration] = field(default_factory=list)
    pending_effects: list[PendingEffect] = field(default_factory=list)
    effect_events: list[EffectEvent] = field(default_factory=list)
    effect_resolutions: list[EffectResolution] = field(default_factory=list)
    deferred_secret_autos: list[DeferredSecretAuto] = field(default_factory=list)
    secret_auto_opportunities: list[SecretAutoOpportunity] = field(default_factory=list)
    delayed_mode_switches: list[DelayedModeSwitch] = field(default_factory=list)
    delayed_keyword_clears: list[DelayedKeywordClear] = field(default_factory=list)
    activate_skill_usage: set[tuple[int, str, int]] = field(default_factory=set)
    attack_restricted_instance_ids: set[int] = field(default_factory=set)
    unison_marker_skill_usage: set[int] = field(default_factory=set)
    unison_growth_usage: set[int] = field(default_factory=set)
