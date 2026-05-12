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
    life_reveal_energy_replacement_turn_number: Optional[int] = None
    attacked_this_turn: bool = False
    attack_count_this_turn: int = 0
    power: int = 15000
    card_type: str = "BATTLE"
    color: Optional[str] = None
    energy_cost_raw: Optional[str] = None
    energy_cost: Optional[int] = None
    combo_cost: Optional[int] = None
    combo_power: Optional[int] = None
    comboed_from: Optional[str] = None
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
    temporary_can_combo_from_battle_while_resting: bool = False
    temporary_keyword_skills_negated: bool = False
    temporary_skills_negated: bool = False
    permanent_skills_negated: bool = False
    temporary_cannot_switch_active: bool = False
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
    source_skill_text: str = ""
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
    source_skill_text: str = ""


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
    source_skill_text: str = ""
    status: str = "pending"
    preblocked: bool = False


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
    created_turn_number: int = 0
    require_next_turn: bool = False


@dataclass(frozen=True)
class DelayedActiveSwitch:
    owner_player_id: int
    target_instance_id: int
    trigger_player_id: int


@dataclass(frozen=True)
class DelayedDrawAndActiveSwitch:
    owner_player_id: int
    target_instance_id: int
    trigger_player_id: int
    amount: int = 1


@dataclass(frozen=True)
class DelayedDrawAndDropToEnergy:
    owner_player_id: int
    trigger_player_id: int
    amount: int = 1
    allowed_colors: str = ""
    requires_multicolor: bool = False


@dataclass(frozen=True)
class DelayedMainPhaseEnergySwitch:
    owner_player_id: int
    trigger_player_id: int
    max_targets: int = 1
    allowed_colors: str = ""
    requires_multicolor: bool = False


@dataclass(frozen=True)
class ExEvolvePermission:
    owner_player_id: int
    created_turn_number: int
    allowed_source_zones: Tuple[str, ...] = ("drop",)
    allowed_colors: str = ""
    required_traits: str = ""
    required_characters: str = ""
    required_name_contains: str = ""
    uses_remaining: int = 1


@dataclass(frozen=True)
class ActivateExtraCostReduction:
    owner_player_id: int
    created_turn_number: int
    amount: int = 1
    required_card_type: str = "EXTRA"
    max_energy_cost: int = -1
    require_mono_color: bool = False
    allowed_colors: str = ""
    required_traits: str = ""
    required_characters: str = ""
    required_name_contains: str = ""
    uses_remaining: int = 1


@dataclass(frozen=True)
class ActivateArrivalCostReduction:
    owner_player_id: int
    created_turn_number: int
    amount: int = 0
    specified_costs: Tuple[Tuple[str, int], ...] = ()
    required_arrival_colors: str = ""
    max_energy_cost: int = -1
    allowed_colors: str = ""
    required_traits: str = ""
    required_characters: str = ""
    required_name_contains: str = ""
    uses_remaining: int = 1


@dataclass(frozen=True)
class ActivateZAwakenCostReduction:
    owner_player_id: int
    created_turn_number: int
    amount: int = 0
    specified_costs: Tuple[Tuple[str, int], ...] = ()
    z_energy_reduction: int = 0
    allowed_colors: str = ""
    required_traits: str = ""
    required_characters: str = ""
    required_name_contains: str = ""
    uses_remaining: int = 1


@dataclass(frozen=True)
class DelayedUnionPlayKeywordGrant:
    owner_player_id: int
    created_turn_number: int
    grant_keyword: str
    allowed_colors: str = ""
    required_traits: str = ""
    required_characters: str = ""
    required_name_contains: str = ""
    uses_remaining: int = 1
    expires_on_turn_end_player_id: int = 1


@dataclass(frozen=True)
class DelayedCardPlayRestriction:
    owner_player_id: int
    restricted_card_id: int


@dataclass(frozen=True)
class PermanentCardRestriction:
    owner_player_id: int
    restricted_card_id: int


@dataclass(frozen=True)
class TemporaryComboRestriction:
    owner_player_id: int
    restricted_card_id: int
    expires_on_turn_end_player_id: int = 1


@dataclass(frozen=True)
class DelayedSkillDrawReplacement:
    owner_player_id: int
    affected_player_id: int
    expires_on_turn_end_player_id: int = 1


@dataclass(frozen=True)
class DelayedActivateSkillRestriction:
    owner_player_id: int
    restricted_card_id: int
    trigger: str = ""
    handler_id: str = ""
    handler_params_signature: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ScheduledAttackRestriction:
    active_player_id: int
    target_instance_id: int = -1
    required_name_contains: str = ""


@dataclass(frozen=True)
class DelayedBattleAttackNegate:
    affected_player_id: int
    created_turn_number: int
    min_cost: int = -1
    require_next_turn: bool = False


@dataclass(frozen=True)
class ScheduledCannotSwitchActiveRestriction:
    active_player_id: int
    target_instance_id: int = -1


@dataclass(frozen=True)
class LowPowerBattlePlayHandWarpPenalty:
    owner_player_id: int
    affected_player_id: int
    max_power: int = 20000
    hand_to_warp: int = 2
    expires_on_turn_end_player_id: int = 1


@dataclass(frozen=True)
class AttackPowerTax:
    owner_player_id: int
    affected_player_id: int
    power_delta: int = -5000
    expires_on_turn_end_player_id: int = 1


@dataclass(frozen=True)
class BattleAttackBottomDeckHandTax:
    owner_player_id: int
    affected_player_id: int
    min_cost_greater_than_current_energy: int = 1
    max_cost: int = -1
    hand_count: int = 2
    battle_count: int = 0
    payment_max_battle_cost: int = -1
    expires_on_turn_end_player_id: int = 1


@dataclass(frozen=True)
class BattleAttackDiscardHandTax:
    owner_player_id: int
    affected_player_id: int
    hand_count: int = 2
    expires_on_turn_end_player_id: int = 1


@dataclass(frozen=True)
class CounterHandActivationRestriction:
    owner_player_id: int
    restricted_card_id: int = 0
    restricted_mode: str = ""
    expires_on_turn_end_player_id: int = 1


@dataclass(frozen=True)
class NonKeywordSkillDamagePrevention:
    protected_player_id: int
    expires_on_turn_end_player_id: int = 1


@dataclass(frozen=True)
class TemporarySkillActivationRestriction:
    owner_player_id: int
    restricted_card_id: int
    scope: str = "auto"
    trigger: str = ""
    handler_id: str = ""
    handler_params_signature: Tuple[Tuple[str, str], ...] = ()
    expires_on_turn_end_player_id: int = 1


@dataclass(frozen=True)
class BattleSkillActivationRestriction:
    owner_player_id: int
    restricted_card_id: int
    scope: str = "auto"
    trigger: str = ""
    handler_id: str = ""
    handler_params_signature: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PermanentSkillActivationRestriction:
    owner_player_id: int
    restricted_card_id: int
    restricted_instance_id: int = -1
    source_instance_id: int = -1
    scope: str = "activate"
    trigger: str = ""
    handler_id: str = ""
    handler_params_signature: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PermanentlyNegatedSkill:
    source_instance_id: int
    trigger: str
    handler_id: str
    handler_params_signature: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class DelayedWarp:
    owner_player_id: int
    target_instance_id: int
    trigger_player_id: int


@dataclass(frozen=True)
class DelayedBottomDeckIfInPlay:
    owner_player_id: int
    target_instance_id: int
    trigger_player_id: int


@dataclass(frozen=True)
class DelayedPlaceUnderLeaderIfInPlay:
    owner_player_id: int
    target_instance_id: int
    trigger_player_id: int


@dataclass(frozen=True)
class DelayedReturnWarpedCardsToHand:
    owner_player_id: int
    affected_player_id: int
    source_instance_id: int
    trigger_player_id: int
    created_turn_number: int
    trigger_kind: str = "turn_end"
    require_next_turn: bool = True
    require_source_in_play: bool = False
    required_source_zone: str = ""


@dataclass(frozen=True)
class DelayedPlayWarpedCard:
    owner_player_id: int
    affected_player_id: int
    source_instance_id: int
    trigger_kind: str
    trigger_player_id: int
    created_turn_number: int
    resting: bool = False
    negate_skills: bool = False
    max_targets: int = 1
    require_next_turn: bool = True
    drop_instead_if_affected_deck_at_most: int = -1
    return_remaining_to_hand: bool = False
    add_to_z_energy_max_targets: int = 0
    first_allowed_colors: str = ""
    first_required_traits: str = ""
    first_required_characters: str = ""
    first_required_name_contains: str = ""
    second_allowed_colors: str = ""
    second_required_traits: str = ""
    second_required_characters: str = ""
    second_required_name_contains: str = ""
    min_cost: int = -1
    max_cost: int = -1


@dataclass(frozen=True)
class DelayedPlayToken:
    owner_player_id: int
    controller_player_id: int
    trigger_kind: str
    trigger_player_id: int
    created_turn_number: int
    token_name: str
    power: int
    combo_cost: int = 0
    combo_power: int = 0
    resting: bool = False
    require_next_turn: bool = True
    temporary_keywords: Tuple[str, ...] = ()
    created_by_source_instance_id: int = -1
    created_by_source_card_id: int = -1
    created_by_source_zone: str = ""
    created_by_source_card_type: str = ""


@dataclass(frozen=True)
class DelayedOpponentSkillDraw:
    owner_player_id: int
    affected_player_id: int
    trigger_player_id: int
    created_turn_number: int
    amount: int = 1
    require_next_turn: bool = True
    trigger_on_counter: bool = True
    required_skill_text_contains: str = ""


@dataclass(frozen=True)
class NonLeaderAttackRestTax:
    owner_player_id: int
    affected_player_id: int
    rest_count: int = 1
    expires_on_turn_end_player_id: int = 1


@dataclass(frozen=True)
class NonLeaderAttackHandAndZTax:
    owner_player_id: int
    affected_player_id: int
    hand_count: int = 1
    z_energy_count: int = 1
    expires_on_turn_end_player_id: int = 1


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
    delayed_active_switches: list[DelayedActiveSwitch] = field(default_factory=list)
    delayed_draw_and_active_switches: list[DelayedDrawAndActiveSwitch] = field(default_factory=list)
    delayed_draw_and_drop_to_energy: list[DelayedDrawAndDropToEnergy] = field(default_factory=list)
    delayed_main_phase_energy_switches: list[DelayedMainPhaseEnergySwitch] = field(default_factory=list)
    delayed_warps: list[DelayedWarp] = field(default_factory=list)
    delayed_bottom_decks_if_in_play: list[DelayedBottomDeckIfInPlay] = field(default_factory=list)
    delayed_place_under_leader_if_in_play: list[DelayedPlaceUnderLeaderIfInPlay] = field(default_factory=list)
    delayed_return_warped_cards_to_hand: list[DelayedReturnWarpedCardsToHand] = field(default_factory=list)
    delayed_play_warped_cards: list[DelayedPlayWarpedCard] = field(default_factory=list)
    delayed_play_tokens: list[DelayedPlayToken] = field(default_factory=list)
    delayed_opponent_skill_draws: list[DelayedOpponentSkillDraw] = field(default_factory=list)
    ex_evolve_permissions: list[ExEvolvePermission] = field(default_factory=list)
    activate_extra_cost_reductions: list[ActivateExtraCostReduction] = field(default_factory=list)
    activate_arrival_cost_reductions: list[ActivateArrivalCostReduction] = field(default_factory=list)
    activate_z_awaken_cost_reductions: list[ActivateZAwakenCostReduction] = field(default_factory=list)
    delayed_union_play_keyword_grants: list[DelayedUnionPlayKeywordGrant] = field(default_factory=list)
    scheduled_card_play_restrictions: list[DelayedCardPlayRestriction] = field(default_factory=list)
    active_card_play_restrictions: list[DelayedCardPlayRestriction] = field(default_factory=list)
    permanent_card_play_restrictions: list[PermanentCardRestriction] = field(default_factory=list)
    active_combo_restrictions: list[TemporaryComboRestriction] = field(default_factory=list)
    permanent_combo_restrictions: list[PermanentCardRestriction] = field(default_factory=list)
    active_skill_draw_replacements: list[DelayedSkillDrawReplacement] = field(default_factory=list)
    scheduled_activate_skill_restrictions: list[DelayedActivateSkillRestriction] = field(default_factory=list)
    active_activate_skill_restrictions: list[DelayedActivateSkillRestriction] = field(default_factory=list)
    scheduled_attack_restrictions: list[ScheduledAttackRestriction] = field(default_factory=list)
    delayed_battle_attack_negates: list[DelayedBattleAttackNegate] = field(default_factory=list)
    scheduled_cannot_switch_active_restrictions: list[ScheduledCannotSwitchActiveRestriction] = field(default_factory=list)
    scheduled_charge_phase_skip_player_ids: set[int] = field(default_factory=set)
    low_power_battle_play_hand_warp_penalties: list[LowPowerBattlePlayHandWarpPenalty] = field(default_factory=list)
    attack_power_taxes: list[AttackPowerTax] = field(default_factory=list)
    battle_attack_bottom_deck_taxes: list[BattleAttackBottomDeckHandTax] = field(default_factory=list)
    battle_attack_discard_hand_taxes: list[BattleAttackDiscardHandTax] = field(default_factory=list)
    non_leader_attack_rest_taxes: list[NonLeaderAttackRestTax] = field(default_factory=list)
    non_leader_attack_hand_z_taxes: list[NonLeaderAttackHandAndZTax] = field(default_factory=list)
    active_counter_hand_restrictions: list[CounterHandActivationRestriction] = field(default_factory=list)
    active_temporary_skill_activation_restrictions: list[TemporarySkillActivationRestriction] = field(default_factory=list)
    active_battle_skill_activation_restrictions: list[BattleSkillActivationRestriction] = field(default_factory=list)
    permanent_skill_activation_restrictions: list[PermanentSkillActivationRestriction] = field(default_factory=list)
    permanently_negated_skills: list[PermanentlyNegatedSkill] = field(default_factory=list)
    negate_opponent_strike_for_player_ids: set[int] = field(default_factory=set)
    battle_no_damage_player_ids: set[int] = field(default_factory=set)
    battle_ko_protected_instance_ids: set[int] = field(default_factory=set)
    nonkeyword_skill_damage_preventions: list[NonKeywordSkillDamagePrevention] = field(default_factory=list)
    activate_skill_usage: set[tuple[int, str, int]] = field(default_factory=set)
    attack_restricted_instance_ids: set[int] = field(default_factory=set)
    attack_restricted_name_contains: set[str] = field(default_factory=set)
    remaining_attack_declarations: dict[int, int] = field(default_factory=dict)
    unison_marker_skill_usage: set[int] = field(default_factory=set)
    unison_growth_usage: set[int] = field(default_factory=set)
