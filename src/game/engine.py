from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import random
import re
from typing import Any
from pathlib import Path

from src.game.actions import Action, ActionType
from src.game.effect_rules import (
    EffectRule,
    load_effect_rule_overrides_json,
    load_effect_rules_json,
    merge_effect_rule_overrides,
    normalize_effect_rule_overrides,
    normalize_effect_rules,
)
from src.game.skill_costs import SkillCostDsl, SkillCostSpec, load_skill_cost_rules_json, normalize_skill_cost_rules
from src.game.state import (
    AttackContext,
    BattleStep,
    CardInstance,
    CheckpointEvent,
    DelayedKeywordClear,
    DelayedModeSwitch,
    DeferredSecretAuto,
    EffectEvent,
    EffectRegistration,
    EffectResolution,
    SecretAutoOpportunity,
    CounterMotion,
    CounterMotionTrace,
    CounterResolution,
    CounterWindow,
    GameState,
    PendingEffect,
    PendingAction,
    PlayerState,
    TurnPhase,
    ZDeckCard,
)


class RulesViolation(ValueError):
    pass


@dataclass(frozen=True)
class CardRuntimeData:
    card_number: str = ""
    card_name: str = ""
    power: int = 15000
    card_type: str = "BATTLE"
    color: str | None = None
    energy_cost_raw: str | None = None
    energy_cost: int | None = None
    combo_cost: int | None = None
    combo_power: int | None = None
    keywords: tuple[str, ...] = ()
    has_counter: bool = False
    counter_modes: tuple[str, ...] = ()
    has_counter_attack: bool = False
    has_counter_battle_card_attack: bool = False
    has_counter_play: bool = False
    has_counter_counter: bool = False
    has_activate_main: bool = False
    has_activate_battle: bool = False
    has_auto: bool = False
    has_permanent: bool = False
    has_draw: bool = False
    max_draw: int | None = None
    auto_once_per_turn: bool = False
    auto_draw_on_play: bool = False
    auto_draw_on_attack: bool = False
    has_barrier: bool = False
    z_energy_cost: int | None = None
    specified_costs: tuple[tuple[str, int], ...] = ()
    skill_text_raw: str | None = None
    has_awaken: bool = False
    activate_limit_once_per_turn: bool = False
    has_super_combo: bool = False
    sparking_threshold: int | None = None
    traits: tuple[str, ...] = ()
    characters: tuple[str, ...] = ()


class RulesEngine:
    def __init__(
        self,
        card_repository: Any | None = None,
        life_card_chooser: Any | None = None,
        skill_cost_can_pay: Any | None = None,
        skill_cost_pay: Any | None = None,
        skill_cost_rules: dict[int, dict[str, object]] | None = None,
        skill_cost_rules_path: str | Path | None = None,
        effect_rules: dict[int, list[dict[str, object]] | list[EffectRule]] | None = None,
        effect_rules_path: str | Path | None = None,
        effect_rule_overrides: dict[int, object] | None = None,
        effect_rule_overrides_path: str | Path | None = None,
        effect_handlers: dict[str, Any] | None = None,
        effect_target_chooser: Any | None = None,
        effect_multi_target_chooser: Any | None = None,
    ) -> None:
        self._card_repository = card_repository
        self._card_cache: dict[tuple[int, str], CardRuntimeData] = {}
        # Signature: chooser(player_state, damage_index:int, max_index:int) -> selected_index:int
        self._life_card_chooser = life_card_chooser
        # Signature: can_pay(player_state, card_instance, context:str) -> bool
        self._skill_cost_can_pay = skill_cost_can_pay
        # Signature: pay(player_state, card_instance, context:str) -> None
        self._skill_cost_pay = skill_cost_pay
        # Mapping: card_id -> context -> list[{"kind": ..., "amount": ...}] | SkillCostSpec
        loaded_skill_cost_rules = load_skill_cost_rules_json(skill_cost_rules_path) if skill_cost_rules_path is not None else {}
        provided_skill_cost_rules = normalize_skill_cost_rules(skill_cost_rules)
        self._skill_cost_rules = self._merge_skill_cost_rule_maps(loaded_skill_cost_rules, provided_skill_cost_rules)
        # Mapping: card_id -> tuple[EffectRule, ...]
        loaded_rules = load_effect_rules_json(effect_rules_path) if effect_rules_path is not None else {}
        provided_rules = normalize_effect_rules(effect_rules)
        merged_rules = self._merge_effect_rule_maps(loaded_rules, provided_rules)
        loaded_overrides = load_effect_rule_overrides_json(effect_rule_overrides_path) if effect_rule_overrides_path is not None else {}
        provided_overrides = normalize_effect_rule_overrides(effect_rule_overrides)
        override_map = dict(loaded_overrides)
        override_map.update(provided_overrides)
        self._effect_rules = merge_effect_rule_overrides(merged_rules, override_map)
        self._effect_handlers: dict[str, Any] = {
            "noop_auto": self._handle_noop_effect,
            "auto_draw_on_play": self._handle_auto_draw_on_play,
            "auto_draw_on_attack": self._handle_auto_draw_on_attack,
            "auto_draw_n": self._handle_auto_draw_n,
            "auto_pay_life_on_attack_gain_power_and_keyword_for_turn": self._handle_auto_pay_life_on_attack_gain_power_and_keyword_for_turn,
            "auto_add_up_to_n_from_owner_hand_to_life_on_owner_leader_attack": self._handle_auto_add_up_to_n_from_owner_hand_to_life_on_owner_leader_attack,
            "auto_add_up_to_n_from_owner_hand_to_life_on_play": self._handle_auto_add_up_to_n_from_owner_hand_to_life_on_play,
            "auto_power_reduce_up_to_n_on_attack": self._handle_auto_power_reduce_up_to_n_on_attack,
            "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play": self._handle_auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play,
            "auto_add_n_life_to_hand_on_self_ko": self._handle_auto_add_n_life_to_hand_on_self_ko,
            "auto_gain_control_opponent_unison_on_play": self._handle_auto_gain_control_opponent_unison_on_play,
            "auto_power_reduce_opponent_unison_on_self_ko": self._handle_auto_power_reduce_opponent_unison_on_self_ko,
            "auto_play_up_to_n_from_owner_hand_on_self_combo": self._handle_auto_play_up_to_n_from_owner_hand_on_self_combo,
            "auto_play_up_to_n_from_owner_deck_on_play": self._handle_auto_play_up_to_n_from_owner_deck_on_play,
            "auto_switch_up_to_n_owner_energy_active_on_turn_end": self._handle_auto_switch_up_to_n_owner_energy_active_on_turn_end,
            "auto_switch_up_to_n_owner_energy_active_on_field_extra_placed": self._handle_auto_switch_up_to_n_owner_energy_active_on_field_extra_placed,
            "auto_rest_self_on_owner_opponent_skill_play_overcost_battle_reduce_power": self._handle_auto_rest_self_on_owner_opponent_skill_play_overcost_battle_reduce_power,
            "auto_rest_self_on_owner_opponent_skill_play_overcost_battle_switch_target_rest": self._handle_auto_rest_self_on_owner_opponent_skill_play_overcost_battle_switch_target_rest,
            "auto_look_top_add_up_to_one_to_hand_on_play": self._handle_auto_look_top_add_up_to_one_to_hand_on_play,
            "auto_add_up_to_n_from_owner_deck_to_hand_on_play": self._handle_auto_add_up_to_n_from_owner_deck_to_hand_on_play,
            "auto_play_up_to_n_from_owner_drop_on_play": self._handle_auto_play_up_to_n_from_owner_drop_on_play,
            "auto_add_markers_per_n_multicolor_energy_on_play": self._handle_auto_add_markers_per_n_multicolor_energy_on_play,
            "auto_add_top_deck_to_energy_rest_on_play": self._handle_auto_add_top_deck_to_energy_rest_on_play,
            "auto_gain_wormhole_on_owner_black_battle_played_from_warp": self._handle_auto_gain_wormhole_on_owner_black_battle_played_from_warp,
            "auto_top_deck_add_if_color_on_play": self._handle_auto_top_deck_add_if_color_on_play,
            "auto_switch_self_active_on_turn_end": self._handle_auto_switch_self_active_on_turn_end,
            "auto_switch_self_to_hidden_on_play": self._handle_auto_switch_self_to_hidden_on_play,
            "auto_switch_up_to_n_owner_board_to_revealed_on_play": self._handle_auto_switch_up_to_n_owner_board_to_revealed_on_play,
            "auto_switch_up_to_n_any_player_board_to_revealed_on_play": self._handle_auto_switch_up_to_n_any_player_board_to_revealed_on_play,
            "auto_switch_up_to_n_owner_battle_to_hidden_on_play": self._handle_auto_switch_up_to_n_owner_battle_to_hidden_on_play,
            "auto_self_gain_power_and_keyword_for_turn_on_switch": self._handle_auto_self_gain_power_and_keyword_for_turn_on_switch,
            "auto_buff_owner_leader_on_switch_until_opponent_turn_end": self._handle_auto_buff_owner_leader_on_switch_until_opponent_turn_end,
            "auto_buff_up_to_n_owner_cards_on_switch": self._handle_auto_buff_up_to_n_owner_cards_on_switch,
            "auto_ko_up_to_n_opponent_battle_on_switch": self._handle_auto_ko_up_to_n_opponent_battle_on_switch,
            "auto_buff_up_to_n_owner_cards_on_hidden_drop": self._handle_auto_buff_up_to_n_owner_cards_on_hidden_drop,
            "auto_play_self_from_combo_on_battle_end": self._handle_auto_play_self_from_combo_on_battle_end,
            "activate_play_self_from_hand": self._handle_activate_play_self_from_hand,
            "activate_draw_n_and_gain_keyword_for_turn": self._handle_activate_draw_n_and_gain_keyword_for_turn,
            "activate_draw_n_play_self_from_hand_and_gain_keyword_until_opponent_turn_end": self._handle_activate_draw_n_play_self_from_hand_and_gain_keyword_until_opponent_turn_end,
            "activate_gain_power_and_keyword_for_battle": self._handle_activate_gain_power_and_keyword_for_battle,
            "activate_ko_up_to_n_opponent_battle": self._handle_activate_ko_up_to_n_opponent_battle,
            "activate_switch_owner_battle_to_hidden_mode": self._handle_activate_switch_owner_battle_to_hidden_mode,
            "activate_switch_self_to_hidden_mode": self._handle_activate_switch_self_to_hidden_mode,
            "activate_gain_power_by_hidden_cost_target_original_power_for_turn": self._handle_activate_gain_power_by_hidden_cost_target_original_power_for_turn,
            "activate_ko_up_to_n_opponent_battle_and_buff_owner_leader_for_turn": self._handle_activate_ko_up_to_n_opponent_battle_and_buff_owner_leader_for_turn,
            "activate_send_up_to_n_opponent_battle_to_warp": self._handle_activate_send_up_to_n_opponent_battle_to_warp,
            "activate_switch_owner_board_to_revealed_mode": self._handle_activate_switch_owner_board_to_revealed_mode,
            "activate_switch_all_opponent_battle_to_revealed_then_ko_up_to_n": self._handle_activate_switch_all_opponent_battle_to_revealed_then_ko_up_to_n,
            "activate_drop_owner_hidden_mode_draw_n": self._handle_activate_drop_owner_hidden_mode_draw_n,
            "auto_switch_up_to_n_opponent_battle_to_hidden_then_reveal_on_opponent_turn_end": self._handle_auto_switch_up_to_n_opponent_battle_to_hidden_then_reveal_on_opponent_turn_end,
            "auto_switch_up_to_n_opponent_battle_to_hidden_then_reveal_on_turn_end": self._handle_auto_switch_up_to_n_opponent_battle_to_hidden_then_reveal_on_turn_end,
            "auto_ko_opponent_battle_on_play": self._handle_auto_ko_opponent_battle_on_play,
            "auto_ko_up_to_n_opponent_battle_on_play": self._handle_auto_ko_up_to_n_opponent_battle_on_play,
            "auto_power_reduce_up_to_n_on_play": self._handle_auto_power_reduce_up_to_n_on_play,
        }
        if effect_handlers:
            self._effect_handlers.update(effect_handlers)
        # Signature: chooser(state, registration, candidates, policy) -> selected_index
        self._effect_target_chooser = effect_target_chooser
        # Signature: chooser(state, registration, candidates, count, policy) -> list[int]
        self._effect_multi_target_chooser = effect_multi_target_chooser

    @staticmethod
    def _merge_skill_cost_rule_maps(
        base: dict[int, dict[str, SkillCostSpec]],
        overlay: dict[int, dict[str, SkillCostSpec]],
    ) -> dict[int, dict[str, SkillCostSpec]]:
        if not base:
            return {card_id: dict(contexts) for card_id, contexts in overlay.items()}
        if not overlay:
            return {card_id: dict(contexts) for card_id, contexts in base.items()}
        merged: dict[int, dict[str, SkillCostSpec]] = {}
        for card_id in set(base.keys()) | set(overlay.keys()):
            combined = dict(base.get(card_id, {}))
            combined.update(overlay.get(card_id, {}))
            merged[card_id] = combined
        return merged

    @staticmethod
    def _merge_effect_rule_maps(
        base: dict[int, tuple[EffectRule, ...]],
        overlay: dict[int, tuple[EffectRule, ...]],
    ) -> dict[int, tuple[EffectRule, ...]]:
        if not base:
            return dict(overlay)
        if not overlay:
            return dict(base)
        merged: dict[int, tuple[EffectRule, ...]] = {}
        all_keys = set(base.keys()) | set(overlay.keys())
        for card_id in all_keys:
            items = list(base.get(card_id, ())) + list(overlay.get(card_id, ()))
            seen: set[tuple[str, str, tuple[tuple[str, int | str | bool], ...], bool, int | None, str, str, str]] = set()
            uniq: list[EffectRule] = []
            for r in items:
                sig = (
                    r.trigger,
                    r.handler_id,
                    tuple(sorted(r.handler_params.items())),
                    r.once_per_turn,
                    r.limit_per_turn,
                    r.limit_scope,
                    r.family_id,
                    r.provenance,
                )
                if sig in seen:
                    continue
                seen.add(sig)
                uniq.append(r)
            merged[card_id] = tuple(uniq)
        return merged

    def initialize_game(
        self,
        *,
        p1_leader_card_id: int,
        p1_deck_card_ids: list[int],
        p1_z_deck_card_ids: list[int] | None = None,
        p2_leader_card_id: int,
        p2_deck_card_ids: list[int],
        p2_z_deck_card_ids: list[int] | None = None,
        opening_hand_size: int = 6,
        life_size: int = 8,
        first_player: int = 1,
        mulligan_by_player: dict[int, bool] | None = None,
        shuffle_decks: bool = True,
        random_seed: int | None = None,
    ) -> GameState:
        if first_player not in {1, 2}:
            raise ValueError("first_player must be 1 or 2.")
        if opening_hand_size < 0 or life_size < 0:
            raise ValueError("opening_hand_size and life_size must be non-negative.")

        rng = random.Random(random_seed)
        p1_leader = self._create_card_instance(next_instance_id=1, card_id=p1_leader_card_id, owner_id=1)
        p2_leader = self._create_card_instance(next_instance_id=2, card_id=p2_leader_card_id, owner_id=2)
        state = GameState(
            players={
                1: PlayerState(
                    player_id=1,
                    leader_card_id=p1_leader_card_id,
                    leader_area=p1_leader,
                    deck=list(p1_deck_card_ids),
                    z_deck=[self._create_z_deck_card(card_id=card_id, owner_id=1) for card_id in (p1_z_deck_card_ids or [])],
                ),
                2: PlayerState(
                    player_id=2,
                    leader_card_id=p2_leader_card_id,
                    leader_area=p2_leader,
                    deck=list(p2_deck_card_ids),
                    z_deck=[self._create_z_deck_card(card_id=card_id, owner_id=2) for card_id in (p2_z_deck_card_ids or [])],
                ),
            },
            active_player=first_player,
            first_player_id=first_player,
            next_instance_id=3,
        )
        for player_id in (1, 2):
            self._register_card_effects(state, player_id=player_id, source_zone="leader", card=state.players[player_id].leader_area)

        state.players[self._opponent_of(first_player)].energy_markers = 1
        self._checkpoint(state, "pregame_leaders_placed")
        self._checkpoint(state, "pregame_starting_player_decided")
        for player_id in (1, 2):
            if shuffle_decks:
                rng.shuffle(state.players[player_id].deck)
            self._draw_n_for_setup(state, player_id, opening_hand_size, zone="hand")
            if bool((mulligan_by_player or {}).get(player_id, False)):
                self._mulligan(state, player_id, opening_hand_size, rng=rng, shuffle_deck=shuffle_decks)
            self._draw_n_for_setup(state, player_id, life_size, zone="life")
        self._checkpoint(state, "pregame_setup_complete")
        self._start_charge_phase(state)
        state.log.append("Game initialized.")
        return state

    def get_legal_actions(self, state: GameState, player_id: int) -> list[Action]:
        if state.winner_id is not None:
            return []
        secret_auto = self._next_pending_secret_auto_opportunity(state)
        if secret_auto is not None:
            if player_id != secret_auto.owner_player_id:
                return []
            return [
                Action(
                    action_type=ActionType.DECLARE_SECRET_AUTO,
                    player_id=player_id,
                    opportunity_id=secret_auto.opportunity_id,
                ),
                Action(
                    action_type=ActionType.IGNORE_SECRET_AUTO,
                    player_id=player_id,
                    opportunity_id=secret_auto.opportunity_id,
                ),
            ]
        if state.counter_window is not None:
            return self._legal_counter_actions(state, player_id)
        if state.attack_context is not None:
            return self._legal_battle_step_actions(state, player_id)
        if player_id != state.active_player:
            return []

        player = state.players[player_id]
        if state.phase == TurnPhase.CHARGE:
            actions = [Action(action_type=ActionType.END_CHARGE, player_id=player_id)]
            if not player.has_charged_this_turn:
                actions.extend(Action(action_type=ActionType.CHARGE_FROM_HAND, player_id=player_id, hand_index=i) for i in range(len(player.hand)))
            return actions

        if state.phase == TurnPhase.MAIN:
            actions = [Action(action_type=ActionType.END_TURN, player_id=player_id)]
            if self._can_awaken_leader(state, player_id):
                actions.append(Action(action_type=ActionType.AWAKEN, player_id=player_id, source_zone="leader"))
            actions.extend(self._legal_play_actions(state, player_id))
            actions.extend(self._legal_unison_growth_actions(state, player_id))
            actions.extend(self._legal_activate_main_actions(state, player_id))
            actions.extend(self._legal_attack_actions(state, player_id))
            return actions
        return []

    def apply_action(self, state: GameState, action: Action) -> GameState:
        if action not in self.get_legal_actions(state, action.player_id):
            raise RulesViolation(f"Illegal action: {action}")
        ns = deepcopy(state)
        player = ns.players[action.player_id]

        if action.action_type == ActionType.DECLARE_SECRET_AUTO:
            self._declare_secret_auto(ns, action)
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.IGNORE_SECRET_AUTO:
            self._ignore_secret_auto(ns, action)
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.CHARGE_FROM_HAND:
            if action.hand_index is None:
                raise RulesViolation("CHARGE_FROM_HAND requires hand_index.")
            card = player.hand.pop(action.hand_index)
            card.resting = False
            player.energy.append(card)
            player.has_charged_this_turn = True
            ns.phase = TurnPhase.MAIN
            self._checkpoint(ns, "charge_phase_after_energy_placement")
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.END_CHARGE:
            ns.phase = TurnPhase.MAIN
            self._checkpoint(ns, "charge_phase_end")
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.PLAY_CARD_FROM_HAND:
            self._declare_play_card_from_hand(ns, action)
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.UNISON_GROWTH:
            self._apply_unison_growth(ns, action)
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.AWAKEN:
            self._awaken_leader(ns, action.player_id)
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.ACTIVATE_MAIN_SKILL:
            self._declare_activate_skill(ns, action, source_kind="main")
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.ACTIVATE_BATTLE_SKILL:
            self._declare_activate_skill(ns, action, source_kind="battle")
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.ACTIVATE_BLOCKER:
            self._activate_blocker(ns, action)
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.COMBO_FROM_HAND:
            self._combo_from_hand(ns, action)
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.END_OFFENSE_STEP:
            self._end_offense_step(ns, action.player_id)
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.END_DEFENSE_STEP:
            self._end_defense_step(ns, action.player_id)
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.DECLARE_ATTACK:
            self._declare_attack(ns, action)
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.DECLARE_COUNTER_FROM_HAND:
            self._declare_counter_from_hand(ns, action)
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.PASS_COUNTER_WINDOW:
            self._pass_counter_window(ns, action.player_id)
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.RESOLVE_BATTLE:
            self._resolve_battle(ns, action.player_id)
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.END_TURN:
            ns.phase = TurnPhase.END
            self._checkpoint(ns, "end_phase_begin")
            self._end_turn(ns)
            self._after_action(ns)
            return ns
        raise RulesViolation(f"Unhandled action: {action.action_type}")

    def _next_pending_secret_auto_opportunity(self, state: GameState) -> SecretAutoOpportunity | None:
        pending = [row for row in state.secret_auto_opportunities if str(row.status or "pending") == "pending"]
        if not pending:
            return None
        owner_order = [state.active_player, self._opponent_of(state.active_player)]
        for owner_id in owner_order:
            owner_pending = [row for row in pending if row.owner_player_id == owner_id]
            if owner_pending:
                return min(owner_pending, key=lambda row: (int(row.event_id), int(row.opportunity_id)))
        return min(pending, key=lambda row: (int(row.event_id), int(row.opportunity_id)))

    @staticmethod
    def _set_secret_auto_opportunity_status(state: GameState, *, opportunity_id: int, status: str) -> SecretAutoOpportunity | None:
        selected: SecretAutoOpportunity | None = None
        updated: list[SecretAutoOpportunity] = []
        for row in state.secret_auto_opportunities:
            if row.opportunity_id == opportunity_id:
                selected = SecretAutoOpportunity(
                    opportunity_id=row.opportunity_id,
                    secret_auto_id=row.secret_auto_id,
                    owner_player_id=row.owner_player_id,
                    source_instance_id=row.source_instance_id,
                    source_card_id=row.source_card_id,
                    source_card_number=row.source_card_number,
                    source_zone=row.source_zone,
                    trigger=row.trigger,
                    handler_id=row.handler_id,
                    event_id=row.event_id,
                    event_name=row.event_name,
                    created_turn_number=row.created_turn_number,
                    created_phase=row.created_phase,
                    origin_zone=row.origin_zone,
                    handler_params=dict(row.handler_params),
                    once_per_turn=row.once_per_turn,
                    limit_per_turn=row.limit_per_turn,
                    limit_scope=row.limit_scope,
                    status=status,
                )
                updated.append(selected)
                continue
            updated.append(row)
        state.secret_auto_opportunities = updated
        return selected

    def _declare_secret_auto(self, state: GameState, action: Action) -> None:
        if action.opportunity_id is None:
            raise RulesViolation("DECLARE_SECRET_AUTO requires opportunity_id.")
        opportunity = self._set_secret_auto_opportunity_status(
            state,
            opportunity_id=action.opportunity_id,
            status="declared",
        )
        if opportunity is None:
            raise RulesViolation("Unknown secret auto opportunity.")
        event = next((row for row in state.effect_events if row.event_id == opportunity.event_id), None)
        temp_effect_id = -int(opportunity.secret_auto_id)
        if event is None:
            state.effect_resolutions.append(
                EffectResolution(effect_id=temp_effect_id, event_id=opportunity.event_id, resolved=False, reason="missing_context")
            )
            state.log.append(
                "Secret-area auto declared without event context: "
                f"opportunity_id={opportunity.opportunity_id} source_instance_id={opportunity.source_instance_id}"
            )
            self._checkpoint(state, "secret_auto_declared")
            return
        source_context = self._find_card_anywhere_by_instance(
            state,
            owner_player_id=opportunity.owner_player_id,
            instance_id=opportunity.source_instance_id,
        )
        if source_context is None:
            state.effect_resolutions.append(
                EffectResolution(effect_id=temp_effect_id, event_id=event.event_id, resolved=False, reason="source_missing")
            )
            state.log.append(
                "Secret-area auto declared but source was missing: "
                f"opportunity_id={opportunity.opportunity_id} source_instance_id={opportunity.source_instance_id}"
            )
            self._checkpoint(state, "secret_auto_declared")
            return
        source_zone, _source = source_context
        handler = self._effect_handlers.get(opportunity.handler_id)
        if handler is None:
            state.effect_resolutions.append(
                EffectResolution(effect_id=temp_effect_id, event_id=event.event_id, resolved=False, reason="missing_handler")
            )
            state.log.append(
                "Secret-area auto declared without handler: "
                f"opportunity_id={opportunity.opportunity_id} handler_id={opportunity.handler_id}"
            )
            self._checkpoint(state, "secret_auto_declared")
            return
        temp_reg = EffectRegistration(
            effect_id=temp_effect_id,
            owner_player_id=opportunity.owner_player_id,
            source_instance_id=opportunity.source_instance_id,
            source_card_id=opportunity.source_card_id,
            source_zone=source_zone,
            trigger=opportunity.trigger,
            handler_id=opportunity.handler_id,
            handler_params=dict(opportunity.handler_params),
            source_card_number=opportunity.source_card_number,
            once_per_turn=opportunity.once_per_turn,
            limit_per_turn=opportunity.limit_per_turn,
            limit_scope=opportunity.limit_scope,
        )
        regs_by_id = self._effect_registrations_for_limit_counting(state)
        regs_by_id[temp_effect_id] = temp_reg
        events_by_id = {evt.event_id: evt for evt in state.effect_events}
        once_key = self._effect_once_per_turn_key(temp_reg)
        resolved_once_per_turn_counts = self._current_effect_once_per_turn_counts(state, regs_by_id=regs_by_id, events_by_id=events_by_id)
        if once_key is not None and resolved_once_per_turn_counts.get(once_key, 0) >= 1:
            self._set_secret_auto_opportunity_status(
                state,
                opportunity_id=opportunity.opportunity_id,
                status="blocked_once_per_turn",
            )
            state.effect_resolutions.append(
                EffectResolution(effect_id=temp_effect_id, event_id=event.event_id, resolved=False, reason="once_per_turn_used")
            )
            state.log.append(
                "Secret-area auto declaration blocked by once-per-turn: "
                f"opportunity_id={opportunity.opportunity_id} source_instance_id={opportunity.source_instance_id} "
                f"trigger={temp_reg.trigger} handler={temp_reg.handler_id}"
            )
            self._checkpoint(state, "secret_auto_declared_once_per_turn_blocked")
            self._checkpoint(state, "secret_auto_declared")
            return
        limit_key = self._effect_limit_key(temp_reg)
        resolved_limit_counts = self._current_effect_limit_counts(state, regs_by_id=regs_by_id, events_by_id=events_by_id)
        if limit_key is not None and resolved_limit_counts.get(limit_key, 0) >= int(temp_reg.limit_per_turn or 0):
            self._set_secret_auto_opportunity_status(
                state,
                opportunity_id=opportunity.opportunity_id,
                status="blocked_limit_per_turn",
            )
            state.effect_resolutions.append(
                EffectResolution(effect_id=temp_effect_id, event_id=event.event_id, resolved=False, reason="limit_per_turn_used")
            )
            state.log.append(
                "Secret-area auto declaration blocked by limit: "
                f"opportunity_id={opportunity.opportunity_id} source_instance_id={opportunity.source_instance_id} "
                f"limit_scope={temp_reg.limit_scope} limit_per_turn={temp_reg.limit_per_turn}"
            )
            self._checkpoint(state, "secret_auto_declared_limit_blocked")
            self._checkpoint(state, "secret_auto_declared")
            return
        handler(state, event, temp_reg)
        state.effect_resolutions.append(
            EffectResolution(effect_id=temp_effect_id, event_id=event.event_id, resolved=True, reason="ok")
        )
        state.log.append(
            "Secret-area auto declared: "
            f"opportunity_id={opportunity.opportunity_id} source_instance_id={opportunity.source_instance_id} "
            f"event_id={event.event_id} handler={opportunity.handler_id}"
        )
        self._checkpoint(state, "secret_auto_declared")

    def _ignore_secret_auto(self, state: GameState, action: Action) -> None:
        if action.opportunity_id is None:
            raise RulesViolation("IGNORE_SECRET_AUTO requires opportunity_id.")
        opportunity = self._set_secret_auto_opportunity_status(
            state,
            opportunity_id=action.opportunity_id,
            status="ignored",
        )
        if opportunity is None:
            raise RulesViolation("Unknown secret auto opportunity.")
        state.log.append(
            "Secret-area auto ignored: "
            f"opportunity_id={opportunity.opportunity_id} source_instance_id={opportunity.source_instance_id}"
        )
        self._checkpoint(state, "secret_auto_ignored")

    def apply_power_delta(
        self,
        state: GameState,
        *,
        player_id: int,
        zone: str,
        index: int | None,
        delta: int,
        reason: str = "effect",
    ) -> GameState:
        ns = deepcopy(state)
        card = self._resolve_zone_card(ns, player_id=player_id, zone=zone, index=index)
        self._modify_card_power(ns, card=card, delta=delta, reason=reason)
        self._after_action(ns)
        return ns

    def _draw_n_for_setup(self, state: GameState, player_id: int, count: int, *, zone: str) -> None:
        player = state.players[player_id]
        for _ in range(count):
            if not player.deck:
                raise RulesViolation(f"Player {player_id} deck too small for setup.")
            card = self._create_card_instance(next_instance_id=state.next_instance_id, card_id=player.deck.pop(0), owner_id=player_id)
            state.next_instance_id += 1
            if zone == "life":
                player.life.append(card)
            elif zone == "hand":
                player.hand.append(card)
            else:
                raise ValueError(f"Unknown setup zone: {zone}")

    def _draw_one(self, state: GameState, player_id: int) -> None:
        player = state.players[player_id]
        if not player.deck:
            state.winner_id = self._opponent_of(player_id)
            return
        card = self._create_card_instance(next_instance_id=state.next_instance_id, card_id=player.deck.pop(0), owner_id=player_id)
        state.next_instance_id += 1
        player.hand.append(card)

    def _mulligan(self, state: GameState, player_id: int, opening_hand_size: int, *, rng: random.Random, shuffle_deck: bool) -> None:
        player = state.players[player_id]
        while player.hand:
            player.deck.append(player.hand.pop().card_id)
        if shuffle_deck:
            rng.shuffle(player.deck)
        self._draw_n_for_setup(state, player_id, opening_hand_size, zone="hand")

    def _start_charge_phase(self, state: GameState) -> None:
        if state.winner_id is not None:
            return
        state.phase = TurnPhase.CHARGE
        state.attack_restricted_instance_ids.clear()
        state.unison_marker_skill_usage.clear()
        state.unison_growth_usage.clear()
        self._reset_once_per_turn_effect_counters(state, player_id=state.active_player)
        state.activate_skill_usage = {entry for entry in state.activate_skill_usage if entry[0] != state.active_player}
        self._emit_effect_event(state, name="turn_start", actor_player_id=state.active_player, payload={})
        self._checkpoint(state, "charge_phase_begin")
        player = state.players[state.active_player]
        player.leader_area.resting = False
        player.leader_area.attacked_this_turn = False
        player.leader_area.attack_count_this_turn = 0
        player.leader_area.temporary_keywords = ()
        for c in player.energy:
            c.resting = False
        for c in player.battle_area:
            c.resting = False
            c.attacked_this_turn = False
            c.attack_count_this_turn = 0
            c.temporary_keywords = ()
        for c in player.unison_area:
            c.resting = False
            c.attacked_this_turn = False
            c.attack_count_this_turn = 0
            c.temporary_keywords = ()
        player.combo_area.clear()
        player.has_charged_this_turn = False
        self._checkpoint(state, "charge_phase_after_untap")
        if not (state.turn_number == 1 and state.active_player == state.first_player_id):
            self._draw_one(state, state.active_player)
            self._checkpoint(state, "charge_phase_after_draw")
        else:
            self._checkpoint(state, "charge_phase_after_draw_skipped")
        self._check_loss_conditions(state)
        self._checkpoint(state, "charge_phase_charge_window")

    def _end_turn(self, state: GameState) -> None:
        ending_player = state.active_player
        self._emit_effect_event(state, name="turn_end", actor_player_id=ending_player, payload={})
        self._apply_due_delayed_mode_switches(state, trigger_kind="turn_end", trigger_player_id=ending_player)
        self._apply_due_delayed_keyword_clears(state, trigger_player_id=ending_player)
        self._clear_end_of_turn_modifiers(state.players[ending_player])
        state.active_player = self._opponent_of(ending_player)
        state.turn_number += 1
        self._start_charge_phase(state)

    def _check_loss_conditions(self, state: GameState) -> None:
        losers = [pid for pid, p in state.players.items() if len(p.life) == 0]
        if not losers:
            return
        if len(losers) == 2:
            state.winner_id = 0
            return
        state.winner_id = self._opponent_of(losers[0])

    def _can_awaken_leader(self, state: GameState, player_id: int) -> bool:
        player = state.players[player_id]
        leader = player.leader_area
        if leader.awakened or not leader.has_awaken:
            return False
        if len(player.life) <= 4:
            return True
        hidden_mode_threshold = self._parse_hidden_mode_awaken_threshold(leader.skill_text_raw)
        if hidden_mode_threshold is not None and sum(1 for card in player.battle_area if card.hidden_mode) >= hidden_mode_threshold:
            return True
        return any(
            unison.color == leader.color and sum(count for _code, count in unison.specified_costs) >= 3
            for unison in player.unison_area
        )

    def _awaken_leader(self, state: GameState, player_id: int) -> None:
        player = state.players[player_id]
        leader = player.leader_area
        if not self._can_awaken_leader(state, player_id):
            raise RulesViolation("Leader cannot awaken now.")
        for _ in range(2):
            self._draw_one(state, player_id)
        while len(player.life) > 6:
            player.hand.append(player.life.pop(0))
        self._apply_leader_back_side(leader)
        self._register_card_effects(state, player_id=player_id, source_zone="leader", card=leader)
        self._emit_effect_event(
            state,
            name="leader_awakened",
            actor_player_id=player_id,
            payload={"source_instance_id": leader.instance_id, "source_card_id": leader.card_id},
        )
        self._checkpoint(state, "leader_awakened")

    def _legal_play_actions(self, state: GameState, player_id: int) -> list[Action]:
        player = state.players[player_id]
        actions: list[Action] = []
        for i, card in enumerate(player.hand):
            if card.card_type not in {"BATTLE", "UNISON", "EXTRA", "Z-BATTLE", "Z-UNISON", "Z-EXTRA"}:
                continue
            effective_energy_cost = self._effective_hand_energy_cost(state, player_id=player_id, card=card)
            if self._can_pay_costs(
                player,
                energy_cost=effective_energy_cost,
                required_color=card.color,
                specified_costs=dict(card.specified_costs),
                z_cost=card.z_energy_cost or 0,
            ):
                actions.append(Action(action_type=ActionType.PLAY_CARD_FROM_HAND, player_id=player_id, hand_index=i))
        return actions

    def _legal_unison_growth_actions(self, state: GameState, player_id: int) -> list[Action]:
        player = state.players[player_id]
        if len(player.unison_area) != 1:
            return []
        current_unison = player.unison_area[0]
        if current_unison.instance_id in state.unison_growth_usage:
            return []
        actions: list[Action] = []
        for i, card in enumerate(player.hand):
            if card.card_type not in {"UNISON", "Z-UNISON"}:
                continue
            if not self._same_card_number(card, current_unison):
                continue
            actions.append(
                Action(
                    action_type=ActionType.UNISON_GROWTH,
                    player_id=player_id,
                    hand_index=i,
                    source_zone="unison",
                    source_index=0,
                )
            )
        return actions

    def _legal_activate_main_actions(self, state: GameState, player_id: int) -> list[Action]:
        player = state.players[player_id]
        actions: list[Action] = []
        if (
            player.leader_area.has_activate_main
            and self._can_pay_energy_cost(
                player,
                player.leader_area.energy_cost or 0,
                required_color=player.leader_area.color,
                specified_costs=dict(player.leader_area.specified_costs),
            )
            and not self._is_activate_limited_this_turn(state, player_id, "main", player.leader_area)
            and self._can_pay_skill_cost(player, player.leader_area, "activate_main")
            and self._activate_effect_requirements_met(state, player_id=player_id, source=player.leader_area, source_zone="leader", source_kind="main")
        ):
            actions.append(Action(action_type=ActionType.ACTIVATE_MAIN_SKILL, player_id=player_id, source_zone="leader"))
        for i, c in enumerate(player.battle_area):
            if (
                self._is_valid_skill_source_area(c, "battle")
                and
                c.has_activate_main
                and self._can_pay_energy_cost(
                    player,
                    c.energy_cost or 0,
                    required_color=c.color,
                    specified_costs=dict(c.specified_costs),
                )
                and not self._is_activate_limited_this_turn(state, player_id, "main", c)
                and self._can_pay_skill_cost(player, c, "activate_main")
                and self._activate_effect_requirements_met(state, player_id=player_id, source=c, source_zone="battle", source_kind="main")
            ):
                actions.append(Action(action_type=ActionType.ACTIVATE_MAIN_SKILL, player_id=player_id, source_zone="battle", source_index=i))
        for i, c in enumerate(player.unison_area):
            if (
                self._is_valid_skill_source_area(c, "unison")
                and
                c.has_activate_main
                and self._can_pay_energy_cost(
                    player,
                    c.energy_cost or 0,
                    required_color=c.color,
                    specified_costs=dict(c.specified_costs),
                )
                and not self._is_activate_limited_this_turn(state, player_id, "main", c)
                and not self._is_unison_marker_skill_limited_this_turn(state, c, "activate_main")
                and self._can_pay_skill_cost(player, c, "activate_main")
                and self._activate_effect_requirements_met(state, player_id=player_id, source=c, source_zone="unison", source_kind="main")
            ):
                actions.append(Action(action_type=ActionType.ACTIVATE_MAIN_SKILL, player_id=player_id, source_zone="unison", source_index=i))
        for i, c in enumerate(player.hand):
            if (
                self._is_valid_skill_source_area(c, "hand")
                and c.has_activate_main
                and self._can_pay_energy_cost(
                    player,
                    self._effective_hand_energy_cost(state, player_id=player_id, card=c),
                    required_color=c.color,
                    specified_costs=dict(c.specified_costs),
                )
                and not self._is_activate_limited_this_turn(state, player_id, "main", c)
                and self._can_pay_skill_cost(player, c, "activate_main")
                and self._activate_effect_requirements_met(state, player_id=player_id, source=c, source_zone="hand", source_kind="main")
            ):
                actions.append(Action(action_type=ActionType.ACTIVATE_MAIN_SKILL, player_id=player_id, source_zone="hand", source_index=i))
        return actions

    def _legal_attack_actions(self, state: GameState, player_id: int) -> list[Action]:
        if state.turn_number == 1 and player_id == state.first_player_id:
            return []
        player = state.players[player_id]
        opponent_id = self._opponent_of(player_id)
        opp = state.players[opponent_id]
        targets: list[tuple[str, int | None]] = [("leader", None)]
        targets.extend(("battle", i) for i, c in enumerate(opp.battle_area) if c.resting)
        targets.extend(("unison", i) for i, c in enumerate(opp.unison_area) if c.resting)
        actions: list[Action] = []
        if self._can_card_attack_this_turn(player.leader_area, state):
            actions.extend(
                Action(action_type=ActionType.DECLARE_ATTACK, player_id=player_id, attacker_zone="leader", target_player_id=opponent_id, target_zone=z, target_index=i)
                for z, i in targets
            )
        for zone_name, zone_cards in (("battle", player.battle_area), ("unison", player.unison_area)):
            for ai, attacker in enumerate(zone_cards):
                if not self._can_card_attack_this_turn(attacker, state):
                    continue
                for tz, ti in targets:
                    actions.append(
                        Action(
                            action_type=ActionType.DECLARE_ATTACK,
                            player_id=player_id,
                            attacker_zone=zone_name,
                            attacker_index=ai,
                            target_player_id=opponent_id,
                            target_zone=tz,
                            target_index=ti,
                        )
                    )
        return actions

    def _legal_activate_battle_actions(self, state: GameState, player_id: int) -> list[Action]:
        player = state.players[player_id]
        actions: list[Action] = []
        if (
            player.leader_area.has_activate_battle
            and self._can_pay_energy_cost(
                player,
                player.leader_area.energy_cost or 0,
                required_color=player.leader_area.color,
                specified_costs=dict(player.leader_area.specified_costs),
            )
            and not self._is_activate_limited_this_turn(state, player_id, "battle", player.leader_area)
            and self._can_pay_skill_cost(player, player.leader_area, "activate_battle")
            and self._activate_effect_requirements_met(state, player_id=player_id, source=player.leader_area, source_zone="leader", source_kind="battle")
        ):
            actions.append(Action(action_type=ActionType.ACTIVATE_BATTLE_SKILL, player_id=player_id, source_zone="leader"))
        for i, c in enumerate(player.battle_area):
            if (
                self._is_valid_skill_source_area(c, "battle")
                and
                c.has_activate_battle
                and self._can_pay_energy_cost(
                    player,
                    c.energy_cost or 0,
                    required_color=c.color,
                    specified_costs=dict(c.specified_costs),
                )
                and not self._is_activate_limited_this_turn(state, player_id, "battle", c)
                and self._can_pay_skill_cost(player, c, "activate_battle")
                and self._activate_effect_requirements_met(state, player_id=player_id, source=c, source_zone="battle", source_kind="battle")
            ):
                actions.append(Action(action_type=ActionType.ACTIVATE_BATTLE_SKILL, player_id=player_id, source_zone="battle", source_index=i))
        for i, c in enumerate(player.unison_area):
            if (
                self._is_valid_skill_source_area(c, "unison")
                and
                c.has_activate_battle
                and self._can_pay_energy_cost(
                    player,
                    c.energy_cost or 0,
                    required_color=c.color,
                    specified_costs=dict(c.specified_costs),
                )
                and not self._is_activate_limited_this_turn(state, player_id, "battle", c)
                and not self._is_unison_marker_skill_limited_this_turn(state, c, "activate_battle")
                and self._can_pay_skill_cost(player, c, "activate_battle")
                and self._activate_effect_requirements_met(state, player_id=player_id, source=c, source_zone="unison", source_kind="battle")
            ):
                actions.append(Action(action_type=ActionType.ACTIVATE_BATTLE_SKILL, player_id=player_id, source_zone="unison", source_index=i))
        return actions

    def _legal_combo_actions(self, state: GameState, player_id: int) -> list[Action]:
        player = state.players[player_id]
        actions: list[Action] = []
        for i, c in enumerate(player.hand):
            if c.card_type not in {"BATTLE", "Z-BATTLE"}:
                continue
            if not self._can_combo_card(state, player_id, c):
                continue
            if (c.combo_cost or 0) < 0 or (c.combo_power or 0) < 0:
                continue
            if self._can_pay_energy_cost(player, c.combo_cost or 0):
                actions.append(Action(action_type=ActionType.COMBO_FROM_HAND, player_id=player_id, hand_index=i))
        return actions

    def _legal_counter_actions(self, state: GameState, player_id: int) -> list[Action]:
        if state.counter_window is None or player_id != state.counter_window.responder_player_id:
            return []
        player = state.players[player_id]
        actions = [Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=player_id)]
        allowed_modes = self._allowed_counter_modes(state)
        for i, c in enumerate(player.hand):
            if not c.has_counter:
                continue
            if allowed_modes and not self._card_matches_counter_window(c, allowed_modes):
                continue
            effective_energy_cost = self._effective_hand_energy_cost(state, player_id=player_id, card=c)
            can_pay_energy = self._can_pay_energy_cost(
                player,
                effective_energy_cost,
                required_color=c.color,
                specified_costs=dict(c.specified_costs),
            )
            if (can_pay_energy or self._can_pay_alternate_counter_hand_cost(state, player, c)) and self._can_pay_skill_cost(player, c, "counter_from_hand"):
                actions.append(Action(action_type=ActionType.DECLARE_COUNTER_FROM_HAND, player_id=player_id, hand_index=i))
        return actions

    def _legal_battle_step_actions(self, state: GameState, player_id: int) -> list[Action]:
        ctx = state.attack_context
        if ctx is None or state.battle_step is None:
            return []
        if state.battle_step == BattleStep.OFFENSE:
            if player_id != ctx.attacker_player_id:
                return []
            acts = [Action(action_type=ActionType.END_OFFENSE_STEP, player_id=player_id)]
            acts.extend(self._legal_combo_actions(state, player_id))
            acts.extend(self._legal_activate_battle_actions(state, player_id))
            return acts
        if state.battle_step == BattleStep.DEFENSE:
            if player_id != ctx.target_player_id:
                return []
            acts = [Action(action_type=ActionType.END_DEFENSE_STEP, player_id=player_id)]
            acts.extend(self._legal_blocker_actions(state, player_id))
            acts.extend(self._legal_combo_actions(state, player_id))
            acts.extend(self._legal_activate_battle_actions(state, player_id))
            return acts
        if state.battle_step in {BattleStep.DAMAGE, BattleStep.BATTLE_END}:
            if player_id != ctx.attacker_player_id:
                return []
            return [Action(action_type=ActionType.RESOLVE_BATTLE, player_id=player_id)]
        return []

    def _legal_blocker_actions(self, state: GameState, player_id: int) -> list[Action]:
        ctx = state.attack_context
        if ctx is None or state.battle_step != BattleStep.DEFENSE or player_id != ctx.target_player_id:
            return []
        player = state.players[player_id]
        actions: list[Action] = []
        for i, card in enumerate(player.battle_area):
            if card.resting or not self._card_has_keyword(card, "Blocker"):
                continue
            if ctx.target_zone == "battle" and ctx.target_instance_id == card.instance_id:
                continue
            actions.append(
                Action(
                    action_type=ActionType.ACTIVATE_BLOCKER,
                    player_id=player_id,
                    source_zone="battle",
                    source_index=i,
                )
            )
        return actions

    def _declare_attack(self, state: GameState, action: Action) -> None:
        if action.attacker_zone not in {"leader", "battle", "unison"}:
            raise RulesViolation("Invalid attacker zone.")
        if action.target_zone not in {"leader", "battle", "unison"} or action.target_player_id is None:
            raise RulesViolation("Invalid target.")
        attacker = self._resolve_zone_card(state, player_id=action.player_id, zone=action.attacker_zone, index=action.attacker_index)
        target = self._resolve_zone_card(state, player_id=action.target_player_id, zone=action.target_zone, index=action.target_index)
        attacks_used = self._attacks_used_this_turn(attacker)
        attacker.resting = True
        attacker.attacked_this_turn = True
        attacker.attack_count_this_turn = attacks_used + 1
        state.attack_context = AttackContext(
            attacker_player_id=action.player_id,
            attacker_zone=action.attacker_zone,
            attacker_instance_id=attacker.instance_id,
            target_player_id=action.target_player_id,
            target_zone=action.target_zone,
            target_instance_id=target.instance_id,
        )
        state.battle_step = None
        self._open_counter_window(
            state,
            kind="attack",
            responder_player_id=action.target_player_id,
            pending_action=PendingAction(action_type="attack", actor_player_id=action.player_id, payload={}),
        )
        self._emit_effect_event(
            state,
            name="attack_declared",
            actor_player_id=action.player_id,
            payload={
                "attacker_instance_id": attacker.instance_id,
                "attacker_zone": action.attacker_zone,
                "target_player_id": action.target_player_id,
                "target_zone": action.target_zone,
            },
        )
        self._checkpoint(state, "counter_timing_attack")

    def _declare_play_card_from_hand(self, state: GameState, action: Action) -> None:
        player = state.players[action.player_id]
        if action.hand_index is None or not (0 <= action.hand_index < len(player.hand)):
            raise RulesViolation("Invalid hand index.")
        card = player.hand[action.hand_index]
        effective_energy_cost = self._effective_hand_energy_cost(state, player_id=action.player_id, card=card)
        paid_energy_cards, _ = self._pay_costs(
            player,
            energy_cost=effective_energy_cost,
            required_color=card.color,
            specified_costs=dict(card.specified_costs),
            z_cost=card.z_energy_cost or 0,
        )
        if card.card_type in {"EXTRA", "Z-EXTRA"}:
            declared = player.hand.pop(action.hand_index)
            player.drop.append(declared)
            self._open_counter_window(
                state,
                kind="activate_extra_from_hand",
                responder_player_id=self._opponent_of(action.player_id),
                pending_action=PendingAction(
                    action_type="activate_extra_from_hand",
                    actor_player_id=action.player_id,
                    payload={"card_instance_id": declared.instance_id},
                ),
            )
            self._checkpoint(state, "extra_moved_to_drop_on_declare")
            self._checkpoint(state, "counter_timing_activate_extra")
            return

        self._open_counter_window(
            state,
            kind="play",
            responder_player_id=self._opponent_of(action.player_id),
            pending_action=PendingAction(
                action_type="play_from_hand",
                actor_player_id=action.player_id,
                payload={"card_instance_id": card.instance_id, "paid_energy_cards": paid_energy_cards},
            ),
        )
        self._checkpoint(state, "counter_timing_play")

    def _declare_activate_skill(self, state: GameState, action: Action, *, source_kind: str) -> None:
        player = state.players[action.player_id]
        if action.source_zone not in {"leader", "battle", "unison", "hand"}:
            raise RulesViolation("Invalid source zone.")
        if action.source_zone == "leader":
            source = player.leader_area
        else:
            if action.source_index is None:
                raise RulesViolation("Missing source index.")
            zone = (
                player.battle_area
                if action.source_zone == "battle"
                else player.unison_area
                if action.source_zone == "unison"
                else player.hand
            )
            if not (0 <= action.source_index < len(zone)):
                raise RulesViolation("Source index out of range.")
            source = zone[action.source_index]
        if source_kind == "main" and not source.has_activate_main:
            raise RulesViolation("No Activate: Main.")
        if source_kind == "battle" and not source.has_activate_battle:
            raise RulesViolation("No Activate: Battle.")
        if not self._is_valid_skill_source_area(source, action.source_zone):
            raise RulesViolation("Skill source is in an invalid area for its card type.")
        if action.source_zone == "hand":
            self._register_card_effects(state, player_id=action.player_id, source_zone="hand", card=source)
        if self._is_activate_limited_this_turn(state, action.player_id, source_kind, source):
            raise RulesViolation("Activate skill limit already used this turn.")
        if self._is_unison_marker_skill_limited_this_turn(state, source, f"activate_{source_kind}"):
            raise RulesViolation("This Unison already used a marker-cost skill this turn.")
        if not self._activate_effect_requirements_met(
            state,
            player_id=action.player_id,
            source=source,
            source_zone=action.source_zone,
            source_kind=source_kind,
        ):
            raise RulesViolation("Activate skill requirements are not met.")
        if not self._can_pay_skill_cost(player, source, f"activate_{source_kind}"):
            raise RulesViolation("Cannot pay skill cost.")
        energy_cost = source.energy_cost or 0
        if action.source_zone == "hand":
            energy_cost = self._effective_hand_energy_cost(state, player_id=action.player_id, card=source)
        self._pay_energy_cost(
            player,
            energy_cost,
            required_color=source.color,
            specified_costs=dict(source.specified_costs),
        )
        skill_cost_payload = self._pay_skill_cost(state, player, source, f"activate_{source_kind}")
        self._open_counter_window(
            state,
            kind=f"activate_{source_kind}",
            responder_player_id=self._opponent_of(action.player_id),
            pending_action=PendingAction(
                action_type=f"activate_{source_kind}",
                actor_player_id=action.player_id,
                payload={
                    "source_zone": action.source_zone,
                    "source_index": action.source_index,
                    "source_instance_id": source.instance_id,
                    "source_card_id": source.card_id,
                    **dict(skill_cost_payload),
                },
            ),
        )
        self._checkpoint(state, f"counter_timing_activate_{source_kind}")

    @staticmethod
    def _activate_usage_key(player_id: int, source_kind: str, source: CardInstance) -> tuple[int, str, int]:
        return (player_id, f"activate_{source_kind}", int(source.card_id))

    def _is_activate_limited_this_turn(self, state: GameState, player_id: int, source_kind: str, source: CardInstance) -> bool:
        if not source.activate_limit_once_per_turn:
            return False
        return self._activate_usage_key(player_id, source_kind, source) in state.activate_skill_usage

    def _skill_cost_spec_has_marker_adjustment(self, card_id: int, context: str) -> bool:
        spec = self._resolve_skill_cost_spec(card_id, context)
        if spec is None:
            return False
        return any(step.kind in {"remove_markers", "add_markers"} for step in spec.steps)

    def _is_unison_marker_skill_limited_this_turn(self, state: GameState, source: CardInstance, context: str) -> bool:
        if source.card_type not in {"UNISON", "Z-UNISON"}:
            return False
        if not self._skill_cost_spec_has_marker_adjustment(source.card_id, context):
            return False
        return source.instance_id in state.unison_marker_skill_usage

    @staticmethod
    def _same_card_number(left: CardInstance, right: CardInstance) -> bool:
        if str(left.card_number or "").strip() and str(right.card_number or "").strip():
            return str(left.card_number).strip().upper() == str(right.card_number).strip().upper()
        return int(left.card_id) == int(right.card_id)

    def _apply_unison_growth(self, state: GameState, action: Action) -> None:
        player = state.players[action.player_id]
        if action.hand_index is None or not (0 <= action.hand_index < len(player.hand)):
            raise RulesViolation("UNISON_GROWTH requires a valid hand index.")
        if len(player.unison_area) != 1:
            raise RulesViolation("Unison Growth requires exactly one Unison in play.")
        if action.source_zone != "unison" or action.source_index not in {0, None}:
            raise RulesViolation("Unison Growth must target the active Unison.")
        current_unison = player.unison_area[0]
        if current_unison.instance_id in state.unison_growth_usage:
            raise RulesViolation("This Unison already used growth this turn.")
        growth_card = player.hand[action.hand_index]
        if growth_card.card_type not in {"UNISON", "Z-UNISON"}:
            raise RulesViolation("Only Unison cards can be used for growth.")
        if not self._same_card_number(growth_card, current_unison):
            raise RulesViolation("Unison Growth requires the same card number.")

        grown = player.hand.pop(action.hand_index)
        current_unison.markers += 1
        current_unison.stacked_card_ids = tuple(current_unison.stacked_card_ids) + (int(grown.card_id),)
        if grown.card_type.startswith("Z-"):
            player.removed_from_game.append(grown)
        else:
            player.drop.append(grown)
        state.unison_growth_usage.add(current_unison.instance_id)
        self._emit_effect_event(
            state,
            name="unison_grew",
            actor_player_id=action.player_id,
            payload={
                "source_instance_id": current_unison.instance_id,
                "source_card_id": current_unison.card_id,
                "growth_card_id": grown.card_id,
                "markers": current_unison.markers,
            },
        )
        self._checkpoint(state, "unison_growth")

    def _can_combo_card(self, state: GameState, player_id: int, card: CardInstance) -> bool:
        if not card.has_super_combo:
            return True
        player = state.players[player_id]
        if len(player.life) <= 4:
            return True
        if card.sparking_threshold is not None and len(player.drop) >= int(card.sparking_threshold):
            return True
        return False

    def _combo_from_hand(self, state: GameState, action: Action) -> None:
        ctx = state.attack_context
        if ctx is None or state.battle_step not in {BattleStep.OFFENSE, BattleStep.DEFENSE}:
            raise RulesViolation("Combo not legal now.")
        owner = ctx.attacker_player_id if state.battle_step == BattleStep.OFFENSE else ctx.target_player_id
        if action.player_id != owner:
            raise RulesViolation("Wrong combo player.")
        player = state.players[action.player_id]
        if action.hand_index is None or not (0 <= action.hand_index < len(player.hand)):
            raise RulesViolation("Invalid hand index.")
        card = player.hand[action.hand_index]
        if card.card_type not in {"BATTLE", "Z-BATTLE"}:
            raise RulesViolation("Only battle cards can combo.")
        if not self._can_combo_card(state, action.player_id, card):
            raise RulesViolation("This card cannot be comboed right now.")
        self._pay_energy_cost(player, card.combo_cost or 0)
        combo_card = player.hand.pop(action.hand_index)
        player.combo_area.append(combo_card)
        self._register_card_effects(state, player_id=action.player_id, source_zone="combo", card=combo_card)
        self._emit_effect_event(
            state,
            name="card_comboed",
            actor_player_id=action.player_id,
            payload={
                "source_instance_id": combo_card.instance_id,
                "source_card_id": combo_card.card_id,
                "source_zone": "combo",
            },
        )
        self._checkpoint(state, "combo_declared")

    def _activate_blocker(self, state: GameState, action: Action) -> None:
        ctx = state.attack_context
        if ctx is None or state.battle_step != BattleStep.DEFENSE:
            raise RulesViolation("Blocker cannot be activated now.")
        if action.player_id != ctx.target_player_id:
            raise RulesViolation("Wrong blocker player.")
        if action.source_zone != "battle" or action.source_index is None:
            raise RulesViolation("Blocker requires a battle card source.")
        blocker = self._resolve_zone_card(state, player_id=action.player_id, zone="battle", index=action.source_index)
        if blocker.resting:
            raise RulesViolation("Blocker must be active.")
        if not self._card_has_keyword(blocker, "Blocker"):
            raise RulesViolation("Selected card does not have Blocker.")
        if ctx.target_zone == "battle" and ctx.target_instance_id == blocker.instance_id:
            raise RulesViolation("Attack is already targeting this blocker.")
        blocker.resting = True
        state.attack_context = AttackContext(
            attacker_player_id=ctx.attacker_player_id,
            attacker_zone=ctx.attacker_zone,
            attacker_instance_id=ctx.attacker_instance_id,
            target_player_id=ctx.target_player_id,
            target_zone="battle",
            target_instance_id=blocker.instance_id,
        )
        self._emit_effect_event(
            state,
            name="blocker_activated",
            actor_player_id=action.player_id,
            payload={
                "source_instance_id": blocker.instance_id,
                "source_card_id": blocker.card_id,
                "redirected_attacker_instance_id": ctx.attacker_instance_id,
            },
        )
        self._checkpoint(state, "blocker_redirect")

    def _end_offense_step(self, state: GameState, player_id: int) -> None:
        ctx = state.attack_context
        if ctx is None or state.battle_step != BattleStep.OFFENSE or player_id != ctx.attacker_player_id:
            raise RulesViolation("Cannot end offense step now.")
        state.battle_step = BattleStep.DAMAGE if ctx.target_zone == "unison" else BattleStep.DEFENSE
        self._checkpoint(state, "battle_damage_step" if state.battle_step == BattleStep.DAMAGE else "battle_defense_step")

    def _end_defense_step(self, state: GameState, player_id: int) -> None:
        ctx = state.attack_context
        if ctx is None or state.battle_step != BattleStep.DEFENSE or player_id != ctx.target_player_id:
            raise RulesViolation("Cannot end defense step now.")
        state.battle_step = BattleStep.DAMAGE
        self._checkpoint(state, "battle_damage_step")

    def _resolve_battle(self, state: GameState, player_id: int) -> None:
        ctx = state.attack_context
        if ctx is None or state.battle_step is None:
            raise RulesViolation("No battle to resolve.")
        if player_id != ctx.attacker_player_id:
            raise RulesViolation("Only attacker resolves battle.")
        if state.battle_step == BattleStep.BATTLE_END:
            self._apply_due_delayed_mode_switches(
                state,
                trigger_kind="battle_end",
                trigger_player_id=ctx.target_player_id,
            )
            self._clear_battle_modifiers(state)
            self._cleanup_combo_areas(state)
            state.attack_context = None
            state.battle_step = None
            return
        if state.battle_step != BattleStep.DAMAGE:
            raise RulesViolation("Resolve battle only in damage/battle-end.")

        attacker = self._find_by_instance(state.players[ctx.attacker_player_id], ctx.attacker_zone, ctx.attacker_instance_id)
        guard = self._find_by_instance(state.players[ctx.target_player_id], ctx.target_zone, ctx.target_instance_id)
        if attacker is None or guard is None:
            state.battle_step = BattleStep.BATTLE_END
            self._emit_effect_event(
                state,
                name="battle_end",
                actor_player_id=ctx.attacker_player_id,
                payload={"attacker_player_id": ctx.attacker_player_id, "target_player_id": ctx.target_player_id},
            )
            if attacker is not None and self._card_has_keyword(attacker, "Dual Attack") and self._attacks_used_this_turn(attacker) < self._max_attacks_per_turn(attacker):
                attacker.resting = False
            self._checkpoint(state, "battle_end_step")
            return
        atk = attacker.power + sum(max(c.combo_power or 0, 0) for c in state.players[ctx.attacker_player_id].combo_area)
        gdp = guard.power + sum(max(c.combo_power or 0, 0) for c in state.players[ctx.target_player_id].combo_area)
        if atk >= gdp:
            if ctx.target_zone == "leader":
                self._deal_damage_to_player(state, ctx.target_player_id, self._strike_damage(attacker))
            elif ctx.target_zone == "battle":
                self._ko_card(state, ctx.target_player_id, "battle", ctx.target_instance_id)
            else:
                self._apply_unison_battle_damage(state, ctx.target_player_id, ctx.target_instance_id, attacker)
        self._check_loss_conditions(state)
        state.battle_step = BattleStep.BATTLE_END
        self._emit_effect_event(
            state,
            name="battle_end",
            actor_player_id=ctx.attacker_player_id,
            payload={"attacker_player_id": ctx.attacker_player_id, "target_player_id": ctx.target_player_id},
        )
        if self._card_has_keyword(attacker, "Dual Attack") and self._attacks_used_this_turn(attacker) < self._max_attacks_per_turn(attacker):
            attacker.resting = False
        self._checkpoint(state, "battle_end_step")

    def _declare_counter_from_hand(self, state: GameState, action: Action) -> None:
        win = state.counter_window
        if win is None or action.player_id != win.responder_player_id:
            raise RulesViolation("Counter not legal now.")
        player = state.players[action.player_id]
        if action.hand_index is None or not (0 <= action.hand_index < len(player.hand)):
            raise RulesViolation("Invalid hand index.")
        card = player.hand[action.hand_index]
        if not card.has_counter:
            raise RulesViolation("Card is not Counter.")
        allowed_modes = self._allowed_counter_modes(state)
        if allowed_modes and not self._card_matches_counter_window(card, allowed_modes):
            raise RulesViolation("Counter mode does not match current counter timing.")
        if not self._can_pay_skill_cost(player, card, "counter_from_hand"):
            raise RulesViolation("Cannot pay counter skill cost.")
        closed_pending_counter_ids = self._other_pending_counter_hand_instance_ids(
            state,
            player_id=action.player_id,
            chosen_hand_index=action.hand_index,
        )
        effective_energy_cost = self._effective_hand_energy_cost(state, player_id=action.player_id, card=card)
        if self._can_pay_energy_cost(
            player,
            effective_energy_cost,
            required_color=card.color,
            specified_costs=dict(card.specified_costs),
        ):
            self._pay_energy_cost(
                player,
                effective_energy_cost,
                required_color=card.color,
                specified_costs=dict(card.specified_costs),
            )
        elif not self._pay_alternate_counter_hand_cost(state, player, card):
            raise RulesViolation("Not enough resources to pay counter cost.")
        skill_cost_payload = self._pay_skill_cost(state, player, card, "counter_from_hand")
        declared = player.hand.pop(action.hand_index)
        player.drop.append(declared)
        self._checkpoint(state, "counter_declared")
        state.counter_chain.append(
            CounterMotion(
                motion_id=state.next_counter_motion_id,
                player_id=action.player_id,
                card_instance_id=declared.instance_id,
                modes=declared.counter_modes,
                payload=dict(skill_cost_payload),
            )
        )
        state.counter_motion_trace.append(
            CounterMotionTrace(
                motion_id=state.next_counter_motion_id,
                turn_number=state.turn_number,
                phase=state.phase,
                window_kind=win.kind,
                pending_action_type=win.pending_action.action_type,
                player_id=action.player_id,
                card_instance_id=declared.instance_id,
                modes=declared.counter_modes,
                resolved=None,
                negated_motion_id=None,
            )
        )
        self._checkpoint(state, f"counter_motion_declared_{state.next_counter_motion_id}")
        if closed_pending_counter_ids:
            state.log.append(
                "Counter pending choices closed: "
                f"player_id={action.player_id} hand_instance_ids={','.join(str(v) for v in closed_pending_counter_ids)} window_kind={win.kind}"
            )
            self._checkpoint(state, "counter_pending_choices_closed")
        state.next_counter_motion_id += 1

        pending = win.pending_action
        state.counter_window = None
        self._open_counter_window(
            state,
            kind="counter_chain",
            responder_player_id=self._opponent_of(action.player_id),
            pending_action=pending,
        )
        self._checkpoint(state, "counter_chain_timing")

    def _other_pending_counter_hand_instance_ids(
        self,
        state: GameState,
        *,
        player_id: int,
        chosen_hand_index: int,
    ) -> list[int]:
        win = state.counter_window
        if win is None or player_id != win.responder_player_id:
            return []
        player = state.players[player_id]
        allowed_modes = self._allowed_counter_modes(state)
        pending_ids: list[int] = []
        for index, card in enumerate(player.hand):
            if index == chosen_hand_index or not card.has_counter:
                continue
            if allowed_modes and not self._card_matches_counter_window(card, allowed_modes):
                continue
            effective_energy_cost = self._effective_hand_energy_cost(state, player_id=player_id, card=card)
            can_pay_energy = self._can_pay_energy_cost(
                player,
                effective_energy_cost,
                required_color=card.color,
                specified_costs=dict(card.specified_costs),
            )
            if not (can_pay_energy or self._can_pay_alternate_counter_hand_cost(state, player, card)):
                continue
            if not self._can_pay_skill_cost(player, card, "counter_from_hand"):
                continue
            pending_ids.append(int(card.instance_id))
        return pending_ids

    def _pass_counter_window(self, state: GameState, player_id: int) -> None:
        if state.counter_window is None or state.counter_window.responder_player_id != player_id:
            raise RulesViolation("No counter window to pass.")
        if state.counter_window.kind == "counter_chain":
            negated = self._resolve_counter_chain(state)
            self._resolve_pending_action(state, negated=negated)
            return
        self._resolve_pending_action(state, negated=False)

    def _open_counter_window(self, state: GameState, *, kind: str, responder_player_id: int, pending_action: PendingAction) -> None:
        if state.counter_window is not None:
            raise RulesViolation("Counter window already open.")
        state.counter_window = CounterWindow(kind=kind, responder_player_id=responder_player_id, pending_action=pending_action)

    def _allowed_counter_modes(self, state: GameState) -> set[str]:
        win = state.counter_window
        if win is None:
            return set()
        if win.kind == "counter_chain":
            return {"Counter: Counter"}
        if win.kind == "attack":
            modes = {"Counter: Attack"}
            ctx = state.attack_context
            if ctx is not None and ctx.attacker_zone == "battle":
                modes.add("Counter: Battle Card Attack")
            return modes
        if win.kind == "play":
            return {"Counter: Play"}
        if win.kind == "activate_extra_from_hand":
            return {"Counter: Counter"}
        if win.kind.startswith("activate_"):
            return {"Counter: Counter"}
        return set()

    @staticmethod
    def _card_matches_counter_window(card: CardInstance, allowed_modes: set[str]) -> bool:
        if not allowed_modes:
            return True
        if card.counter_modes:
            return any(mode in allowed_modes for mode in card.counter_modes)
        # Strict mode: no generic fallback; explicit mode/flags required.
        if "Counter: Attack" in allowed_modes and card.has_counter_attack:
            return True
        if "Counter: Play" in allowed_modes and card.has_counter_play:
            return True
        if "Counter: Counter" in allowed_modes and card.has_counter_counter:
            return True
        if "Counter: Battle Card Attack" in allowed_modes and card.has_counter_battle_card_attack:
            return True
        return False

    @staticmethod
    def _card_has_keyword(card: CardInstance, keyword: str) -> bool:
        needle = str(keyword).strip().lower()
        return any(
            str(item).strip().lower() == needle
            for item in (
                (card.keywords or ())
                + (card.temporary_keywords or ())
                + (card.battle_temporary_keywords or ())
                + (card.delayed_temporary_keywords or ())
            )
        )

    def _max_attacks_per_turn(self, card: CardInstance) -> int:
        return 2 if self._card_has_keyword(card, "Dual Attack") else 1

    def _attacks_used_this_turn(self, card: CardInstance) -> int:
        return max(int(getattr(card, "attack_count_this_turn", 0)), 1 if card.attacked_this_turn else 0)

    def _can_card_attack_this_turn(self, card: CardInstance, state: GameState) -> bool:
        if card.resting or card.hidden_mode or card.instance_id in state.attack_restricted_instance_ids:
            return False
        return self._attacks_used_this_turn(card) < self._max_attacks_per_turn(card)

    @staticmethod
    def _clear_end_of_turn_modifiers(player: PlayerState) -> None:
        player.leader_area.power -= int(getattr(player.leader_area, "temporary_power_delta", 0))
        player.leader_area.temporary_power_delta = 0
        player.leader_area.temporary_keywords = ()
        player.leader_area.power -= int(getattr(player.leader_area, "battle_temporary_power_delta", 0))
        player.leader_area.battle_temporary_power_delta = 0
        player.leader_area.battle_temporary_keywords = ()
        for c in player.battle_area:
            c.power -= int(getattr(c, "temporary_power_delta", 0))
            c.temporary_power_delta = 0
            c.temporary_keywords = ()
            c.power -= int(getattr(c, "battle_temporary_power_delta", 0))
            c.battle_temporary_power_delta = 0
            c.battle_temporary_keywords = ()
        for c in player.unison_area:
            c.power -= int(getattr(c, "temporary_power_delta", 0))
            c.temporary_power_delta = 0
            c.temporary_keywords = ()
            c.power -= int(getattr(c, "battle_temporary_power_delta", 0))
            c.battle_temporary_power_delta = 0
            c.battle_temporary_keywords = ()

    def _apply_temporary_power_delta(self, state: GameState, *, card: CardInstance, delta: int, reason: str) -> None:
        if delta == 0:
            return
        self._modify_card_power(state, card=card, delta=delta, reason=reason)
        card.temporary_power_delta = int(getattr(card, "temporary_power_delta", 0)) + delta

    def _apply_battle_temporary_power_delta(self, state: GameState, *, card: CardInstance, delta: int, reason: str) -> None:
        if delta == 0:
            return
        self._modify_card_power(state, card=card, delta=delta, reason=reason)
        card.battle_temporary_power_delta = int(getattr(card, "battle_temporary_power_delta", 0)) + delta

    @staticmethod
    def _append_temporary_keyword(card: CardInstance, keyword: str, *, duration: str) -> None:
        normalized = str(keyword).strip()
        if not normalized:
            return
        if duration == "battle":
            if any(str(item).strip().lower() == normalized.lower() for item in (card.battle_temporary_keywords or ())):
                return
            card.battle_temporary_keywords = tuple(list(card.battle_temporary_keywords) + [normalized])
            return
        if duration == "delayed":
            if any(str(item).strip().lower() == normalized.lower() for item in (card.delayed_temporary_keywords or ())):
                return
            card.delayed_temporary_keywords = tuple(list(card.delayed_temporary_keywords) + [normalized])
            return
        if any(str(item).strip().lower() == normalized.lower() for item in (card.temporary_keywords or ())):
            return
        card.temporary_keywords = tuple(list(card.temporary_keywords) + [normalized])

    def _clear_battle_modifiers(self, state: GameState) -> None:
        cleared = False
        for player in state.players.values():
            cards = [player.leader_area, *player.battle_area, *player.unison_area]
            for card in cards:
                battle_delta = int(getattr(card, "battle_temporary_power_delta", 0))
                if battle_delta:
                    card.power -= battle_delta
                    card.battle_temporary_power_delta = 0
                    cleared = True
                if card.battle_temporary_keywords:
                    card.battle_temporary_keywords = ()
                    cleared = True
        if cleared:
            self._checkpoint(state, "battle_modifiers_cleared")

    @staticmethod
    def _text_describes_counter_negate_play_self(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return "negate the attack" in text and "play this card" in text

    @staticmethod
    def _text_counter_negates_attack(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return "negate the attack" in text

    @staticmethod
    def _text_describes_counter_play_self(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return "play this card" in text

    @staticmethod
    def _text_requires_play_self_in_rest(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return "rest mode" in text or "in rest" in text

    @staticmethod
    def _text_restricts_leader_attacker(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return "if the attacking card was a leader card" in text and "can't attack for the turn" in text

    @staticmethod
    def _text_restricts_battle_attacker(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return "if the attacking card was a battle card" in text and "can't attack for the turn" in text

    @staticmethod
    def _text_reveals_hidden_cost_target_at_turn_end(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return "switch the card that was switched to hidden mode by this skill to revealed mode at the end of the turn" in text

    @staticmethod
    def _text_counter_switches_self_to_hidden(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return "play this card, then switch it to hidden mode" in text

    @staticmethod
    def _text_counter_switches_opponent_battle_to_hidden_then_reveal(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return (
            "choose any number of your opponent's battle cards up to the number of your hidden mode cards and switch them to hidden mode" in text
            and "switch all the cards switched to hidden mode by this skill to revealed mode at the end of the turn" in text
        )

    @staticmethod
    def _text_counter_switches_owner_energy_to_hidden_then_draw(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return "switch 1 of your white energy to hidden mode. if you do, draw 1 card" in text

    @staticmethod
    def _text_counter_discards_then_switches_owner_card_to_hidden(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return "discard 1 card from your hand. if you do, choose up to 1 of your white cards and switch it to hidden mode" in text

    @staticmethod
    def _text_counter_redirects_attack_to_self(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return "switch the target of attack to it" in text

    @staticmethod
    def _text_counter_switches_owner_battle_to_hidden_at_battle_end(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return "choose up to 1 of your white battle cards and switch it to hidden mode at the end of the battle" in text

    @staticmethod
    def _text_counter_can_rest_hidden_mode_battle_instead_of_energy_cost(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return "activate this card's [counter] skill from your hand by switching 1 hidden mode card in your battle area to rest mode instead of paying its energy cost" in text

    @staticmethod
    def _text_counter_can_add_life_to_hand_instead_of_energy_cost(card: CardInstance) -> bool:
        text = str(card.skill_text_raw or "").lower()
        return "activate this card's [counter] skill from your hand by adding 1 card from your life to your hand instead of paying its energy cost" in text

    @staticmethod
    def _owner_hidden_mode_count(player: PlayerState) -> int:
        return sum(
            1
            for card in [*player.battle_area, *player.unison_area, *player.energy]
            if getattr(card, "hidden_mode", False)
        )

    def _resolve_pending_action(self, state: GameState, *, negated: bool) -> None:
        win = state.counter_window
        if win is None:
            raise RulesViolation("No pending action.")
        pending = win.pending_action
        state.counter_window = None
        if pending.action_type == "attack":
            state.battle_step = BattleStep.BATTLE_END if negated else BattleStep.OFFENSE
            self._checkpoint(state, "battle_end_step" if negated else "battle_offense_step")
            if negated:
                state.attack_context = None
            return
        if pending.action_type == "play_from_hand":
            self._resolve_play_from_hand(state, pending, negated=negated)
            return
        if pending.action_type == "activate_extra_from_hand":
            self._resolve_extra_activation_from_hand(state, pending, negated=negated)
            return
        if pending.action_type in {"activate_main", "activate_battle"}:
            if negated:
                self._checkpoint(state, "skill_activation_negated")
                return
            source_zone = str(pending.payload.get("source_zone") or "")
            source_index_raw = pending.payload.get("source_index")
            source_index = None if source_index_raw in {None, -1} else int(source_index_raw)
            player = state.players[pending.actor_player_id]
            source_instance_id = int(pending.payload.get("source_instance_id") or -1)
            source = self._find_by_instance(player, source_zone, source_instance_id) if source_instance_id > 0 else None
            if source is None:
                source = self._resolve_zone_card(state, player_id=pending.actor_player_id, zone=source_zone, index=source_index)
            if source is not None and source.activate_limit_once_per_turn:
                source_kind = "main" if pending.action_type == "activate_main" else "battle"
                state.activate_skill_usage.add(self._activate_usage_key(pending.actor_player_id, source_kind, source))
            if (
                source is not None
                and source.card_type in {"UNISON", "Z-UNISON"}
                and self._skill_cost_spec_has_marker_adjustment(
                    int(pending.payload.get("source_card_id") or getattr(source, "card_id", -1)),
                    pending.action_type,
                )
            ):
                state.unison_marker_skill_usage.add(int(pending.payload.get("source_instance_id") or source.instance_id))
            self._emit_effect_event(
                state,
                name="skill_activated",
                actor_player_id=pending.actor_player_id,
                payload={
                    "source_zone": str(pending.payload.get("source_zone") or ""),
                    "source_index": int(pending.payload.get("source_index") or -1),
                    "source_instance_id": int(pending.payload.get("source_instance_id") or -1),
                    "source_card_id": int(pending.payload.get("source_card_id") or -1),
                    "skill_kind": pending.action_type,
                    **{
                        str(key): value
                        for key, value in pending.payload.items()
                        if str(key).startswith("cost_")
                    },
                },
            )
            matching_registered_effect = any(
                reg.source_instance_id == source_instance_id
                and reg.trigger == ("self_activate_main" if pending.action_type == "activate_main" else "self_activate_battle")
                for reg in state.effect_registry
            )
            if not matching_registered_effect:
                state.log.append(
                    f"Unsupported skill activation: source_card_id={int(pending.payload.get('source_card_id') or -1)} kind={pending.action_type}"
                )
                self._checkpoint(state, "skill_activation_no_registered_effect")
            self._checkpoint(state, "skill_activation_resolved")
            return
        raise RulesViolation(f"Unknown pending action type: {pending.action_type}")

    def _resolve_counter_chain(self, state: GameState) -> bool:
        motions = state.counter_chain
        if not motions:
            return False
        self._checkpoint(state, "counter_chain_resolution_begin")
        state.log.append(f"Counter chain resolution begin: motion_count={len(motions)}")

        motion_by_id = {motion.motion_id: motion for motion in motions}
        pending_action_type_by_motion = {
            trace.motion_id: trace.pending_action_type
            for trace in state.counter_motion_trace
            if trace.resolved is None
        }
        active: dict[int, bool] = {m.motion_id: True for m in motions}
        index_by_id = {m.motion_id: i for i, m in enumerate(motions)}

        resolutions: list[CounterResolution] = []
        for resolution_order, motion in enumerate(reversed(motions), start=1):
            if not active[motion.motion_id]:
                resolutions.append(
                    CounterResolution(
                        motion_id=motion.motion_id,
                        player_id=motion.player_id,
                        pending_action_type=pending_action_type_by_motion.get(motion.motion_id, "unknown"),
                        resolved=False,
                        negated_motion_id=None,
                        resolution_order=resolution_order,
                    )
                )
                continue

            prev_idx = index_by_id[motion.motion_id] - 1
            negated_id: int | None = None
            if prev_idx >= 0:
                prev_motion = motions[prev_idx]
                active[prev_motion.motion_id] = False
                negated_id = prev_motion.motion_id

            resolutions.append(
                CounterResolution(
                    motion_id=motion.motion_id,
                    player_id=motion.player_id,
                    pending_action_type=pending_action_type_by_motion.get(motion.motion_id, "unknown"),
                    resolved=True,
                    negated_motion_id=negated_id,
                    resolution_order=resolution_order,
                )
            )

        effect_tags_by_motion = self._apply_resolved_counter_motion_effects(state, motions, resolutions)
        enriched_resolutions = [
            CounterResolution(
                motion_id=r.motion_id,
                player_id=r.player_id,
                pending_action_type=r.pending_action_type,
                resolved=r.resolved,
                negated_motion_id=r.negated_motion_id,
                resolution_order=r.resolution_order,
                applied_effects=effect_tags_by_motion.get(r.motion_id, ()),
            )
            for r in resolutions
        ]
        state.counter_resolutions.extend(enriched_resolutions)
        for r in enriched_resolutions:
            self._checkpoint(state, f"counter_motion_resolved_{r.motion_id}")
            source = next(
                (t for t in reversed(state.counter_motion_trace) if t.motion_id == r.motion_id and t.resolved is None),
                None,
            )
            if source is None:
                continue
            state.counter_motion_trace.append(
                CounterMotionTrace(
                    motion_id=source.motion_id,
                    turn_number=source.turn_number,
                    phase=source.phase,
                    window_kind=source.window_kind,
                    pending_action_type=source.pending_action_type,
                    player_id=source.player_id,
                    card_instance_id=source.card_instance_id,
                    modes=source.modes,
                    resolved=r.resolved,
                    negated_motion_id=r.negated_motion_id,
                    resolution_order=r.resolution_order,
                    applied_effects=r.applied_effects,
                )
            )
        root_negated = any(r.resolved and r.negated_motion_id is None for r in enriched_resolutions)
        state.counter_chain = []
        state.log.append(
            "Counter chain resolution complete: "
            + ", ".join(
                f"motion_id={r.motion_id} order={r.resolution_order} resolved={r.resolved} "
                f"pending_action_type={r.pending_action_type} negated_motion_id={r.negated_motion_id} "
                f"effects={','.join(r.applied_effects) or 'none'}"
                for r in enriched_resolutions
            )
        )
        self._checkpoint(state, "counter_chain_resolution_complete")
        if not root_negated:
            return False
        top_resolution = next((r for r in enriched_resolutions if r.resolved and r.negated_motion_id is None), None)
        if top_resolution is None:
            return False
        top_motion = motion_by_id.get(top_resolution.motion_id)
        if top_motion is None:
            return False
        return self._counter_motion_negates_pending_action(state, top_motion)

    def _counter_motion_negates_pending_action(self, state: GameState, motion: CounterMotion) -> bool:
        win = state.counter_window
        if win is None:
            return False
        player = state.players.get(motion.player_id)
        if player is None:
            return False
        card = next(
            (
                c
                for c in [
                    *player.drop,
                    *player.battle_area,
                    *player.unison_area,
                    *player.energy,
                    *player.hand,
                    player.leader_area,
                ]
                if c.instance_id == motion.card_instance_id
            ),
            None,
        )
        if card is None:
            return False
        pending = win.pending_action
        if pending.action_type == "attack":
            text = str(card.skill_text_raw or "").strip()
            if self._text_counter_negates_attack(card):
                return True
            if not text:
                return card.has_counter_attack or "Counter: Attack" in (card.counter_modes or ())
            return False
        if pending.action_type == "play_from_hand":
            text = str(card.skill_text_raw or "").lower()
            return "negate the play" in text or "instead of being played" in text
        if pending.action_type in {"activate_main", "activate_battle", "activate_extra_from_hand"}:
            text = str(card.skill_text_raw or "").lower()
            return "negate the skill" in text or "counter the skill" in text
        return False

    def _apply_resolved_counter_motion_effects(
        self,
        state: GameState,
        motions: list[CounterMotion],
        resolutions: list[CounterResolution],
    ) -> dict[int, Tuple[str, ...]]:
        motion_by_id = {motion.motion_id: motion for motion in motions}
        effect_tags_by_motion: dict[int, Tuple[str, ...]] = {}
        for resolution in resolutions:
            if not resolution.resolved or resolution.negated_motion_id is not None:
                continue
            motion = motion_by_id.get(resolution.motion_id)
            if motion is None:
                continue
            player = state.players[motion.player_id]
            card = next((c for c in player.drop if c.instance_id == motion.card_instance_id), None)
            if card is None:
                continue
            handled = False
            effect_tags: list[str] = []
            if self._text_describes_counter_play_self(card):
                effect_tags.extend(self._resolve_counter_play_self_family(state, player, card, motion.payload))
                handled = True
            if self._apply_counter_hidden_then_reveal_family(state, player, card):
                handled = True
                effect_tags.append("hidden_then_reveal")
            if self._apply_counter_switch_owner_energy_hidden_then_draw_family(state, player, card):
                handled = True
                effect_tags.append("switch_owner_energy_hidden_then_draw")
            if self._apply_counter_discard_then_switch_owner_card_hidden_family(state, player, card):
                handled = True
                effect_tags.append("discard_then_switch_owner_card_hidden")
            if self._apply_counter_attack_restriction_family(state, card):
                handled = True
                effect_tags.append("attack_restriction")
            if not handled and str(card.skill_text_raw or "").strip():
                state.log.append(
                    f"Unsupported counter effect: source_card_id={card.card_id} modes={','.join(card.counter_modes or ()) or 'unknown'}"
                )
                self._checkpoint(state, "counter_effect_no_registered_family")
                effect_tags.append("unsupported")
            if effect_tags:
                effect_tags_by_motion[motion.motion_id] = tuple(effect_tags)
                state.log.append(
                    "Counter motion effects applied: "
                    f"motion_id={motion.motion_id} effects={','.join(effect_tags)}"
                )
        return effect_tags_by_motion

    def _resolve_counter_play_self_family(
        self,
        state: GameState,
        player: PlayerState,
        card: CardInstance,
        payload: dict[str, int | str | None],
    ) -> Tuple[str, ...]:
        effect_tags = ["play_self"]
        card.resting = self._text_requires_play_self_in_rest(card)
        if card in player.drop:
            player.drop.remove(card)
        player.battle_area.append(card)
        self._register_card_effects(state, player_id=player.player_id, source_zone="battle", card=card)
        self._emit_effect_event(
            state,
            name="counter_played_from_drop",
            actor_player_id=player.player_id,
            payload={
                "source_instance_id": card.instance_id,
                "source_card_id": card.card_id,
                "source_zone": "battle",
            },
        )
        if self._text_counter_switches_self_to_hidden(card):
            card.hidden_mode = True
            effect_tags.append("switch_self_hidden")
            self._emit_effect_event(
                state,
                name="card_switched_hidden_mode",
                actor_player_id=player.player_id,
                payload={
                    "source_instance_id": card.instance_id,
                    "source_card_id": card.card_id,
                    "source_zone": "battle",
                    "owner_player_id": player.player_id,
                },
            )
            self._checkpoint(state, "counter_effect_switch_self_hidden_resolved")
        target_instance_id = int(payload.get("cost_target_instance_id") or -1)
        if target_instance_id > 0 and self._text_reveals_hidden_cost_target_at_turn_end(card):
            effect_tags.append("delayed_reveal")
            self._schedule_delayed_mode_switch(
                state,
                owner_player_id=player.player_id,
                target_instance_id=target_instance_id,
                trigger_kind="turn_end",
                trigger_player_id=state.active_player,
                switch_to_hidden=False,
            )
            self._checkpoint(state, "counter_effect_delayed_reveal_scheduled")
        if self._apply_counter_redirect_to_self_family(state, player, card):
            effect_tags.append("redirect_to_self")
            self._checkpoint(state, "counter_effect_redirect_to_self_resolved")
        if self._apply_counter_switch_owner_battle_hidden_at_battle_end_family(state, player, card):
            effect_tags.append("delayed_hidden_battle_end")
            self._checkpoint(state, "counter_effect_delayed_hidden_battle_end_scheduled")
        self._checkpoint(state, "counter_effect_play_self_resolved")
        return tuple(effect_tags)

    def _apply_counter_redirect_to_self_family(self, state: GameState, player: PlayerState, card: CardInstance) -> bool:
        if not self._text_counter_redirects_attack_to_self(card):
            return False
        ctx = state.attack_context
        if ctx is None:
            return True
        state.attack_context = AttackContext(
            attacker_player_id=ctx.attacker_player_id,
            attacker_zone=ctx.attacker_zone,
            attacker_instance_id=ctx.attacker_instance_id,
            target_player_id=player.player_id,
            target_zone="battle",
            target_instance_id=card.instance_id,
        )
        if state.battle_step == BattleStep.DEFENSE:
            state.battle_step = BattleStep.OFFENSE
        return True

    def _apply_counter_switch_owner_battle_hidden_at_battle_end_family(self, state: GameState, player: PlayerState, card: CardInstance) -> bool:
        if not self._text_counter_switches_owner_battle_to_hidden_at_battle_end(card):
            return False
        candidates: list[CardInstance] = []
        if (
            card in player.battle_area
            and not card.hidden_mode
            and "white" in {part.strip().lower() for part in str(card.color or "").replace("/", ",").split(",") if part.strip()}
        ):
            candidates.append(card)
        candidates.extend(
            target
            for target in player.battle_area
            if target.instance_id != card.instance_id
            and not target.hidden_mode
            and "white" in {part.strip().lower() for part in str(target.color or "").replace("/", ",").split(",") if part.strip()}
        )
        if not candidates:
            return True
        target = candidates[0]
        self._schedule_delayed_mode_switch(
            state,
            owner_player_id=player.player_id,
            target_instance_id=target.instance_id,
            trigger_kind="battle_end",
            trigger_player_id=player.player_id,
            switch_to_hidden=True,
        )
        return True

    def _apply_counter_attack_restriction_family(self, state: GameState, card: CardInstance) -> bool:
        ctx = state.attack_context
        if ctx is None:
            return False
        if self._text_restricts_leader_attacker(card) and ctx.attacker_zone == "leader":
            state.attack_restricted_instance_ids.add(ctx.attacker_instance_id)
            self._checkpoint(state, "counter_effect_attack_restriction_applied")
            return True
        if self._text_restricts_battle_attacker(card) and ctx.attacker_zone == "battle":
            state.attack_restricted_instance_ids.add(ctx.attacker_instance_id)
            self._checkpoint(state, "counter_effect_attack_restriction_applied")
            return True
        return False

    def _apply_counter_hidden_then_reveal_family(self, state: GameState, player: PlayerState, card: CardInstance) -> bool:
        if not self._text_counter_switches_opponent_battle_to_hidden_then_reveal(card):
            return False
        opponent_id = self._opponent_of(player.player_id)
        opponent = state.players.get(opponent_id)
        if opponent is None:
            return False
        max_targets = self._owner_hidden_mode_count(player)
        if max_targets <= 0:
            return True
        candidates = [target for target in opponent.battle_area if not target.hidden_mode]
        if not candidates:
            return True
        indexes = list(range(min(max_targets, len(candidates))))
        if not indexes:
            return True
        for idx in indexes:
            target = candidates[idx]
            target.hidden_mode = True
            self._emit_effect_event(
                state,
                name="card_switched_hidden_mode",
                actor_player_id=player.player_id,
                payload={
                    "source_instance_id": target.instance_id,
                    "source_card_id": target.card_id,
                    "source_zone": "battle",
                    "owner_player_id": opponent_id,
                },
            )
            self._schedule_delayed_mode_switch(
                state,
                owner_player_id=opponent_id,
                target_instance_id=target.instance_id,
                trigger_kind="turn_end",
                trigger_player_id=state.active_player,
                switch_to_hidden=False,
            )
        self._checkpoint(state, "counter_effect_hidden_then_reveal_scheduled")
        return True

    def _apply_counter_switch_owner_energy_hidden_then_draw_family(self, state: GameState, player: PlayerState, card: CardInstance) -> bool:
        if not self._text_counter_switches_owner_energy_to_hidden_then_draw(card):
            return False
        target = next(
            (
                energy
                for energy in player.energy
                if not energy.hidden_mode and "white" in {part.strip().lower() for part in str(energy.color or "").replace("/", ",").split(",") if part.strip()}
            ),
            None,
        )
        if target is None:
            return True
        target.hidden_mode = True
        self._draw_one(state, player.player_id)
        self._checkpoint(state, "counter_effect_switch_owner_energy_hidden_then_draw")
        return True

    def _apply_counter_discard_then_switch_owner_card_hidden_family(self, state: GameState, player: PlayerState, card: CardInstance) -> bool:
        if not self._text_counter_discards_then_switches_owner_card_to_hidden(card):
            return False
        if not player.hand:
            return True
        player.drop.append(player.hand.pop(0))
        candidates = [
            target
            for target in [*player.battle_area, *player.unison_area, *player.energy]
            if not target.hidden_mode
            and "white" in {part.strip().lower() for part in str(target.color or "").replace("/", ",").split(",") if part.strip()}
        ]
        if not candidates:
            return True
        candidates[0].hidden_mode = True
        self._checkpoint(state, "counter_effect_discard_then_switch_owner_card_hidden")
        return True

    def _resolve_play_from_hand(self, state: GameState, pending: PendingAction, *, negated: bool) -> None:
        player = state.players[pending.actor_player_id]
        target_id = int(pending.payload.get("card_instance_id") or -1)
        idx = next((i for i, c in enumerate(player.hand) if c.instance_id == target_id), None)
        if idx is None:
            return
        card = player.hand.pop(idx)
        card.resting = bool(pending.payload.get("resting") or False)
        delayed_keyword = str(pending.payload.get("grant_keyword_after_play") or "").strip()
        keyword_clear_trigger_player_id = int(pending.payload.get("keyword_clear_trigger_player_id") or -1)
        if negated:
            player.drop.append(card)
            self._checkpoint(state, "play_negated")
            return
        if card.card_type in {"BATTLE", "Z-BATTLE"}:
            player.battle_area.append(card)
            if delayed_keyword:
                self._append_temporary_keyword(card, delayed_keyword, duration="delayed")
                if keyword_clear_trigger_player_id > 0:
                    state.delayed_keyword_clears.append(
                        DelayedKeywordClear(
                            owner_player_id=pending.actor_player_id,
                            target_instance_id=card.instance_id,
                            trigger_player_id=keyword_clear_trigger_player_id,
                            keyword=delayed_keyword,
                        )
                    )
            self._register_card_effects(state, player_id=pending.actor_player_id, source_zone="battle", card=card)
            self._emit_effect_event(
                state,
                name="card_played",
                actor_player_id=pending.actor_player_id,
                payload={
                    "source_instance_id": card.instance_id,
                    "source_card_id": card.card_id,
                    "source_zone": "battle",
                    "played_from": "hand",
                },
            )
            self._checkpoint(state, "main_play_battle")
            return
        if card.card_type in {"UNISON", "Z-UNISON"}:
            marker_override = pending.payload.get("marker_count")
            paid_energy = int(pending.payload.get("paid_energy_cards") or 0)
            card.markers = max(int(marker_override) if marker_override is not None else paid_energy, 0)
            self._replace_owner_unison_if_needed(state, player)
            player.unison_area.append(card)
            self._register_card_effects(state, player_id=pending.actor_player_id, source_zone="unison", card=card)
            self._emit_effect_event(
                state,
                name="card_played",
                actor_player_id=pending.actor_player_id,
                payload={
                    "source_instance_id": card.instance_id,
                    "source_card_id": card.card_id,
                    "source_zone": "unison",
                    "played_from": "hand",
                },
            )
            self._checkpoint(state, "main_play_unison")
            return
        player.drop.append(card)
        self._checkpoint(state, "main_play_extra")

    def _resolve_extra_activation_from_hand(self, state: GameState, pending: PendingAction, *, negated: bool) -> None:
        player = state.players[pending.actor_player_id]
        target_id = int(pending.payload.get("card_instance_id") or -1)
        # By rule timing, the Extra card is already in Drop when counter timing occurs.
        exists_in_drop = any(c.instance_id == target_id for c in player.drop)
        if not exists_in_drop:
            return
        if negated:
            self._checkpoint(state, "extra_activation_negated")
        else:
            source = next((c for c in player.drop if c.instance_id == target_id), None)
            if source is None:
                return
            if not self._can_pay_skill_cost(player, source, "activate_extra_from_hand"):
                self._checkpoint(state, "extra_activation_failed_skill_cost")
                return
            self._pay_skill_cost(state, player, source, "activate_extra_from_hand")
            if any(str(k).strip().lower() == "field" for k in (source.keywords or ())):
                self._emit_effect_event(
                    state,
                    name="field_extra_placed",
                    actor_player_id=pending.actor_player_id,
                    payload={
                        "source_instance_id": source.instance_id,
                        "source_card_id": source.card_id,
                    },
                )
            self._checkpoint(state, "extra_activation_resolved")

    def _resolve_zone_card(self, state: GameState, *, player_id: int, zone: str, index: int | None) -> CardInstance:
        player = state.players[player_id]
        if zone == "leader":
            return player.leader_area
        if zone == "hand":
            if index is None or not (0 <= index < len(player.hand)):
                raise RulesViolation("Invalid hand index.")
            return player.hand[index]
        if zone == "battle":
            if index is None or not (0 <= index < len(player.battle_area)):
                raise RulesViolation("Invalid battle index.")
            return player.battle_area[index]
        if zone == "unison":
            if index is None or not (0 <= index < len(player.unison_area)):
                raise RulesViolation("Invalid unison index.")
            return player.unison_area[index]
        raise RulesViolation(f"Unsupported zone: {zone}")

    def _find_by_instance(self, player: PlayerState, zone: str, instance_id: int) -> CardInstance | None:
        if zone == "leader":
            return player.leader_area if player.leader_area.instance_id == instance_id else None
        zone_cards = (
            player.hand
            if zone == "hand"
            else player.battle_area
            if zone == "battle"
            else player.unison_area
            if zone == "unison"
            else player.combo_area
            if zone == "combo"
            else []
        )
        for c in zone_cards:
            if c.instance_id == instance_id:
                return c
        return None

    def _find_card_anywhere_by_instance(
        self,
        state: GameState,
        *,
        owner_player_id: int,
        instance_id: int,
    ) -> tuple[str, CardInstance] | None:
        player = state.players.get(owner_player_id)
        if player is None:
            return None
        if player.leader_area.instance_id == instance_id:
            return ("leader", player.leader_area)
        zones: list[tuple[str, list[CardInstance]]] = [
            ("hand", player.hand),
            ("life", player.life),
            ("energy", player.energy),
            ("z_energy", player.z_energy),
            ("battle", player.battle_area),
            ("unison", player.unison_area),
            ("combo", player.combo_area),
            ("drop", player.drop),
            ("warp", player.warp),
            ("removed_from_game", player.removed_from_game),
        ]
        for zone_name, zone_cards in zones:
            for card in zone_cards:
                if card.instance_id == instance_id:
                    return (zone_name, card)
        return None

    def _find_board_card_by_instance(self, player: PlayerState, instance_id: int) -> CardInstance | None:
        for card in player.battle_area:
            if card.instance_id == instance_id:
                return card
        for card in player.unison_area:
            if card.instance_id == instance_id:
                return card
        return None

    def _schedule_delayed_mode_switch(
        self,
        state: GameState,
        *,
        owner_player_id: int,
        target_instance_id: int,
        trigger_kind: str,
        trigger_player_id: int,
        switch_to_hidden: bool,
    ) -> None:
        state.delayed_mode_switches.append(
            DelayedModeSwitch(
                owner_player_id=owner_player_id,
                target_instance_id=target_instance_id,
                trigger_kind=trigger_kind,
                trigger_player_id=trigger_player_id,
                switch_to_hidden=switch_to_hidden,
            )
        )

    def _apply_due_delayed_mode_switches(self, state: GameState, *, trigger_kind: str, trigger_player_id: int) -> None:
        if not state.delayed_mode_switches:
            return
        remaining: list[DelayedModeSwitch] = []
        changed = False
        for delayed in state.delayed_mode_switches:
            if delayed.trigger_kind != trigger_kind or delayed.trigger_player_id != trigger_player_id:
                remaining.append(delayed)
                continue
            owner = state.players.get(delayed.owner_player_id)
            if owner is None:
                continue
            target = self._find_board_card_by_instance(owner, delayed.target_instance_id)
            if target is None:
                continue
            target.hidden_mode = bool(delayed.switch_to_hidden)
            changed = True
            event_name = "card_switched_hidden_mode" if delayed.switch_to_hidden else "card_switched_revealed_mode"
            self._emit_effect_event(
                state,
                name=event_name,
                actor_player_id=delayed.owner_player_id,
                payload={
                    "source_instance_id": target.instance_id,
                    "source_card_id": target.card_id,
                    "source_zone": "unison" if target in owner.unison_area else "battle",
                    "owner_player_id": delayed.owner_player_id,
                },
            )
        state.delayed_mode_switches = remaining
        if changed:
            self._checkpoint(state, "delayed_mode_switch_resolved")

    def _apply_due_delayed_keyword_clears(self, state: GameState, *, trigger_player_id: int) -> None:
        if not state.delayed_keyword_clears:
            return
        remaining: list[DelayedKeywordClear] = []
        changed = False
        for delayed in state.delayed_keyword_clears:
            if delayed.trigger_player_id != trigger_player_id:
                remaining.append(delayed)
                continue
            owner = state.players.get(delayed.owner_player_id)
            if owner is None:
                continue
            target = self._find_board_card_by_instance(owner, delayed.target_instance_id)
            if target is None and owner.leader_area.instance_id == delayed.target_instance_id:
                target = owner.leader_area
            if target is None:
                continue
            filtered = tuple(
                item
                for item in (target.delayed_temporary_keywords or ())
                if str(item).strip().lower() != delayed.keyword.strip().lower()
            )
            if filtered != target.delayed_temporary_keywords:
                target.delayed_temporary_keywords = filtered
                changed = True
        state.delayed_keyword_clears = remaining
        if changed:
            self._checkpoint(state, "delayed_keyword_clear_resolved")

    def _ko_card(self, state: GameState, player_id: int, zone: str, instance_id: int) -> None:
        player = state.players[player_id]
        zone_cards = player.battle_area if zone == "battle" else player.unison_area
        for i, c in enumerate(zone_cards):
            if c.instance_id == instance_id:
                removed = zone_cards.pop(i)
                if removed.card_type.startswith("Z-"):
                    player.removed_from_game.append(removed)
                else:
                    player.drop.append(removed)
                    self._emit_board_card_placed_into_drop(state, owner_player_id=player_id, card=removed, source_zone=zone)
                self._emit_effect_event(
                    state,
                    name="card_koed",
                    actor_player_id=None,
                    payload={
                        "source_instance_id": removed.instance_id,
                        "source_card_id": removed.card_id,
                        "source_zone": zone,
                        "owner_player_id": player_id,
                    },
                )
                self._checkpoint(state, "ko_processing")
                return

    def _emit_board_card_placed_into_drop(self, state: GameState, *, owner_player_id: int, card: CardInstance, source_zone: str) -> None:
        self._emit_effect_event(
            state,
            name="card_placed_into_drop",
            actor_player_id=None,
            payload={
                "source_instance_id": card.instance_id,
                "source_card_id": card.card_id,
                "source_zone": source_zone,
                "owner_player_id": owner_player_id,
                "source_hidden_mode": bool(card.hidden_mode),
            },
        )

    def _replace_owner_unison_if_needed(self, state: GameState, player: PlayerState) -> CardInstance | None:
        if not player.unison_area:
            return None
        replaced = player.unison_area.pop()
        if replaced.card_type.startswith("Z-"):
            player.removed_from_game.append(replaced)
        else:
            player.drop.append(replaced)
        self._checkpoint(state, "unison_replaced")
        return replaced

    def _apply_unison_battle_damage(self, state: GameState, player_id: int, instance_id: int, attacker: CardInstance) -> None:
        player = state.players[player_id]
        for i, unison in enumerate(player.unison_area):
            if unison.instance_id != instance_id:
                continue
            if "Victory Strike" in attacker.keywords:
                remove = unison.markers
            elif any(k in attacker.keywords for k in ("Double Strike", "Triple Strike", "Quadruple Strike")):
                remove = self._strike_damage(attacker)
            else:
                remove = 1
            self._remove_unison_markers(state, unison=unison, amount=remove, reason="battle_damage")
            if unison.markers <= 0:
                removed = player.unison_area.pop(i)
                if removed.card_type.startswith("Z-"):
                    player.removed_from_game.append(removed)
                else:
                    player.drop.append(removed)
            self._checkpoint(state, "unison_marker_damage")
            return

    def _cleanup_combo_areas(self, state: GameState) -> None:
        for p in state.players.values():
            while p.combo_area:
                p.drop.append(p.combo_area.pop())
        self._checkpoint(state, "battle_combo_cleanup")

    def _deal_damage_to_player(self, state: GameState, player_id: int, amount: int) -> None:
        if amount <= 0:
            return
        player = state.players[player_id]
        for damage_index in range(amount):
            if not player.life:
                break
            chosen_index = self._choose_life_card_index(player, damage_index)
            player.hand.append(player.life.pop(chosen_index))
        self._checkpoint(state, "damage_processing")

    def _choose_life_card_index(self, player: PlayerState, damage_index: int) -> int:
        if not player.life:
            return 0
        max_index = len(player.life) - 1
        if self._life_card_chooser is None:
            return 0
        try:
            selected = int(self._life_card_chooser(player, damage_index, max_index))
        except Exception:
            return 0
        if selected < 0:
            return 0
        if selected > max_index:
            return max_index
        return selected

    def _after_action(self, state: GameState) -> None:
        self._run_confirmative_rule_processing(state)
        self._evaluate_continuous_effects(state)
        # Checkpoint-equivalent resolution is deferred while a counter window is open.
        if state.counter_window is None:
            self._resolve_pending_effects(state)
        self._check_loss_conditions(state)

    def _run_confirmative_rule_processing(self, state: GameState) -> None:
        self._prune_stale_deferred_secret_autos(state)
        self._prune_stale_secret_auto_opportunities(state)
        for player in state.players.values():
            i = 0
            while i < len(player.battle_area):
                if player.battle_area[i].power <= 0:
                    removed = player.battle_area.pop(i)
                    player.drop.append(removed)
                    self._emit_board_card_placed_into_drop(state, owner_player_id=player.player_id, card=removed, source_zone="battle")
                    self._checkpoint(state, "rule_battle_power_zero")
                    continue
                i += 1

            i = 0
            while i < len(player.unison_area):
                unison = player.unison_area[i]
                if "UNISON" not in (unison.card_type or "").upper():
                    i += 1
                    continue
                if unison.power <= 0:
                    self._remove_unison_markers(state, unison=unison, amount=1, reason="rule_power_zero")
                if unison.markers <= 0:
                    removed = player.unison_area.pop(i)
                    if removed.card_type.startswith("Z-"):
                        player.removed_from_game.append(removed)
                    else:
                        player.drop.append(removed)
                    self._checkpoint(state, "rule_unison_zero_markers")
                    continue
                if unison.power <= 0:
                    # Confirmative checks repeat until no zero-power unison remains.
                    continue
                i += 1

    def _prune_stale_deferred_secret_autos(self, state: GameState) -> None:
        retained: list[DeferredSecretAuto] = []
        removed_any = False
        for row in state.deferred_secret_autos:
            if self._deferred_secret_auto_source_exists(state, row):
                retained.append(row)
            else:
                removed_any = True
        if removed_any:
            state.deferred_secret_autos = retained
            self._checkpoint(state, "secret_auto_registration_pruned")

    def _prune_stale_secret_auto_opportunities(self, state: GameState) -> None:
        retained: list[SecretAutoOpportunity] = []
        removed_any = False
        for row in state.secret_auto_opportunities:
            if row.status != "pending":
                retained.append(row)
                continue
            if self._find_card_anywhere_by_instance(
                state,
                owner_player_id=row.owner_player_id,
                instance_id=row.source_instance_id,
            ) is not None:
                retained.append(row)
                continue
            removed_any = True
        if removed_any:
            state.secret_auto_opportunities = retained
            self._checkpoint(state, "secret_auto_opportunity_pruned")

    def _deferred_secret_auto_source_exists(self, state: GameState, row: DeferredSecretAuto) -> bool:
        player = state.players.get(row.owner_player_id)
        if player is None:
            return False
        zone = str(row.source_zone or "").strip().lower()
        if zone == "hand":
            return any(card.instance_id == row.source_instance_id for card in player.hand)
        if zone == "life":
            return any(card.instance_id == row.source_instance_id for card in player.life)
        if zone == "deck":
            return False
        return False

    def _modify_card_power(self, state: GameState, *, card: CardInstance, delta: int, reason: str) -> None:
        if delta == 0:
            return
        self._set_card_power(state, card=card, new_power=card.power + delta, reason=reason)

    def _set_card_power(self, state: GameState, *, card: CardInstance, new_power: int, reason: str) -> None:
        if card.power == new_power:
            return
        self._checkpoint(state, f"power_change_begin_{reason}")
        card.power = new_power
        self._checkpoint(state, f"power_changed_{reason}")

    def _can_pay_skill_cost(self, player: PlayerState, card: CardInstance, context: str) -> bool:
        if self._skill_cost_can_pay is None:
            spec = self._resolve_skill_cost_spec(card.card_id, context)
            if spec is None:
                return True
            try:
                return SkillCostDsl.can_pay(player, card, spec)
            except Exception:
                return False
        try:
            return bool(self._skill_cost_can_pay(player, card, context))
        except Exception:
            return False

    def _pay_skill_cost(self, state: GameState, player: PlayerState, card: CardInstance, context: str) -> dict[str, int | str | None]:
        if self._skill_cost_pay is None:
            spec = self._resolve_skill_cost_spec(card.card_id, context)
            if spec is None:
                return {}
            try:
                before_markers = card.markers
                metadata = SkillCostDsl.pay(player, card, spec)
                removed_markers = max(before_markers - card.markers, 0)
                if removed_markers > 0 and card.card_type in {"UNISON", "Z-UNISON"}:
                    self._checkpoint(state, "marker_remove_begin_skill_cost")
                    self._checkpoint(state, "marker_removed_skill_cost")
                self._emit_drop_event_from_skill_cost_metadata(state, player=player, metadata=metadata)
                return dict(metadata)
            except Exception as exc:
                raise RulesViolation(f"Skill cost payment failed: {exc}") from exc
        try:
            metadata = self._skill_cost_pay(player, card, context)
            if isinstance(metadata, dict):
                normalized = {str(k): v for k, v in metadata.items() if isinstance(k, str) and isinstance(v, (int, str, bool, type(None)))}
                self._emit_drop_event_from_skill_cost_metadata(state, player=player, metadata=normalized)
                return normalized
            return {}
        except Exception as exc:
            raise RulesViolation(f"Skill cost payment failed: {exc}") from exc

    def _emit_drop_event_from_skill_cost_metadata(
        self,
        state: GameState,
        *,
        player: PlayerState,
        metadata: dict[str, int | str | None],
    ) -> None:
        target_instance_id = int(metadata.get("cost_target_instance_id") or -1)
        target_zone = str(metadata.get("cost_target_zone") or "")
        if target_instance_id <= 0 or target_zone != "battle":
            return
        target = next((card for card in player.drop if card.instance_id == target_instance_id), None)
        if target is None:
            return
        self._emit_board_card_placed_into_drop(state, owner_player_id=player.player_id, card=target, source_zone="battle")

    def _remove_unison_markers(self, state: GameState, *, unison: CardInstance, amount: int, reason: str) -> None:
        if amount <= 0:
            return
        self._checkpoint(state, f"marker_remove_begin_{reason}")
        unison.markers -= amount
        self._checkpoint(state, f"marker_removed_{reason}")

    def _resolve_skill_cost_spec(self, card_id: int, context: str) -> SkillCostSpec | None:
        card_rules = self._skill_cost_rules.get(card_id)
        if not card_rules:
            return None
        raw = card_rules.get(context)
        if raw is None:
            return None
        return SkillCostSpec.from_data(raw)

    @staticmethod
    def _is_valid_skill_source_area(card: CardInstance, zone: str | None) -> bool:
        if zone == "leader":
            return True
        if card.hidden_mode:
            return False
        ctype = (card.card_type or "").upper()
        if zone == "hand":
            return ctype in {"BATTLE", "UNISON", "Z-BATTLE", "Z-UNISON"}
        if zone == "battle":
            return "BATTLE" in ctype
        if zone == "unison":
            return "UNISON" in ctype
        return False

    @staticmethod
    def _strike_damage(card: CardInstance) -> int:
        if "Victory Strike" in card.keywords:
            return 999
        if "Quadruple Strike" in card.keywords:
            return 4
        if "Triple Strike" in card.keywords:
            return 3
        if "Double Strike" in card.keywords:
            return 2
        return 1

    @staticmethod
    def _can_pay_energy_cost(
        player: PlayerState,
        cost: int,
        *,
        required_color: str | None = None,
        specified_costs: dict[str, int] | None = None,
    ) -> bool:
        if cost <= 0:
            return True
        active = [c for c in player.energy if not c.resting]
        if len(active) + player.energy_markers < cost:
            return False
        specified = {k: int(v) for k, v in (specified_costs or {}).items() if int(v) > 0}
        if specified:
            for color_code, needed in specified.items():
                matching_energy = sum(1 for c in active if RulesEngine._color_to_code(c.color) == color_code)
                if matching_energy + player.energy_markers < needed:
                    return False
            return True
        if not required_color:
            return True
        allowed = {x.strip().lower() for x in required_color.split("/")}
        if player.energy_markers > 0:
            return True
        return any((c.color or "").lower() in allowed for c in active)

    @staticmethod
    def _can_pay_z_energy_cost(player: PlayerState, z_cost: int) -> bool:
        return z_cost <= 0 or len(player.z_energy) >= z_cost

    @staticmethod
    def _can_pay_costs(
        player: PlayerState,
        *,
        energy_cost: int,
        required_color: str | None,
        specified_costs: dict[str, int] | None,
        z_cost: int,
    ) -> bool:
        return RulesEngine._can_pay_energy_cost(
            player,
            energy_cost,
            required_color=required_color,
            specified_costs=specified_costs,
        ) and RulesEngine._can_pay_z_energy_cost(player, z_cost)

    @staticmethod
    def _pay_energy_cost(
        player: PlayerState,
        cost: int,
        *,
        required_color: str | None = None,
        specified_costs: dict[str, int] | None = None,
    ) -> int:
        if cost <= 0:
            return 0
        if not RulesEngine._can_pay_energy_cost(
            player,
            cost,
            required_color=required_color,
            specified_costs=specified_costs,
        ):
            raise RulesViolation("Not enough active energy/markers to pay cost.")
        rem = cost
        paid_by_energy = 0
        specified = {k: int(v) for k, v in (specified_costs or {}).items() if int(v) > 0}

        if specified:
            # Pay specified pips first from matching active energy.
            for color_code, needed in specified.items():
                for c in player.energy:
                    if needed <= 0:
                        break
                    if c.resting:
                        continue
                    if RulesEngine._color_to_code(c.color) == color_code:
                        c.resting = True
                        needed -= 1
                        rem -= 1
                        paid_by_energy += 1
                if needed > 0:
                    player.energy_markers -= needed
                    rem -= needed

        for c in player.energy:
            if rem == 0:
                break
            if not c.resting:
                c.resting = True
                rem -= 1
                paid_by_energy += 1
        if rem > 0:
            player.energy_markers -= rem
        return paid_by_energy

    @staticmethod
    def _pay_z_energy_cost(player: PlayerState, z_cost: int) -> int:
        if z_cost <= 0:
            return 0
        if len(player.z_energy) < z_cost:
            raise RulesViolation("Not enough Z-energy.")
        for _ in range(z_cost):
            player.drop.append(player.z_energy.pop())
        return z_cost

    @staticmethod
    def _pay_costs(
        player: PlayerState,
        *,
        energy_cost: int,
        required_color: str | None,
        specified_costs: dict[str, int] | None,
        z_cost: int,
    ) -> tuple[int, int]:
        if not RulesEngine._can_pay_costs(
            player,
            energy_cost=energy_cost,
            required_color=required_color,
            specified_costs=specified_costs,
            z_cost=z_cost,
        ):
            raise RulesViolation("Not enough resources.")
        paid_energy = RulesEngine._pay_energy_cost(
            player,
            energy_cost,
            required_color=required_color,
            specified_costs=specified_costs,
        )
        paid_z = RulesEngine._pay_z_energy_cost(player, z_cost)
        return paid_energy, paid_z

    def _register_card_effects(self, state: GameState, *, player_id: int, source_zone: str, card: CardInstance) -> None:
        candidates: list[tuple[str, str, bool | None, dict[str, int | str | bool]]] = []
        deferred_secret_auto = False
        if not self._is_secret_zone(source_zone):
            self._promote_deferred_secret_autos_to_public_zone(
                state,
                source_instance_id=card.instance_id,
                source_zone=source_zone,
            )
        if card.has_auto:
            if source_zone in {"battle", "unison"}:
                candidates.append(("self_played", "noop_auto", None, {}))
                if card.auto_draw_on_play:
                    candidates.append(("self_played", "auto_draw_on_play", None, {}))
            if source_zone in {"leader", "battle", "unison"}:
                candidates.append(("self_attacks", "noop_auto", None, {}))
                if card.auto_draw_on_attack:
                    candidates.append(("self_attacks", "auto_draw_on_attack", None, {}))

        for rule in self._effect_rules.get(card.card_id, ()):
            params = dict(rule.handler_params)
            if rule.limit_per_turn is not None:
                params["limit_per_turn"] = int(rule.limit_per_turn)
                params["limit_scope"] = str(rule.limit_scope or "card_number")
            if not self._can_register_effect_trigger_from_zone(source_zone, rule.trigger):
                if self._is_secret_zone(source_zone):
                    deferred_secret_auto = True
                    self._record_deferred_secret_auto(
                        state,
                        owner_player_id=player_id,
                        card=card,
                        source_zone=source_zone,
                        trigger=rule.trigger,
                        handler_id=rule.handler_id,
                        handler_params=params,
                        once_per_turn=bool(rule.once_per_turn),
                        limit_per_turn=rule.limit_per_turn,
                        limit_scope=str(rule.limit_scope or "card_number"),
                    )
                    state.log.append(
                        "Deferred secret-area auto registration: "
                        f"source_instance_id={card.instance_id} zone={source_zone} trigger={rule.trigger}"
                    )
                continue
            candidates.append((rule.trigger, rule.handler_id, rule.once_per_turn, params))

        for trigger, handler_id, once_per_turn_override, handler_params in candidates:
            linked_secret = self._find_linked_deferred_secret_auto(
                state,
                source_instance_id=card.instance_id,
                trigger=trigger,
                handler_id=handler_id,
                handler_params=handler_params,
            )
            if linked_secret is not None and self._preserve_secret_auto_provenance_on_public_registration(
                linked_secret,
                source_zone=source_zone,
            ):
                continue
            exists = any(
                reg.source_instance_id == card.instance_id
                and reg.source_zone == source_zone
                and reg.trigger == trigger
                and reg.handler_id == handler_id
                for reg in state.effect_registry
            )
            if exists:
                continue
            state.effect_registry.append(
                EffectRegistration(
                    effect_id=state.next_effect_id,
                    owner_player_id=player_id,
                    source_instance_id=card.instance_id,
                    source_card_id=card.card_id,
                    source_zone=source_zone,
                    trigger=trigger,
                    handler_id=handler_id,
                    handler_params=dict(handler_params),
                    source_card_number=str(card.card_number or ""),
                    once_per_turn=card.auto_once_per_turn if once_per_turn_override is None else bool(once_per_turn_override),
                    limit_per_turn=self._resolve_effect_limit_per_turn(handler_params),
                    limit_scope=str(handler_params.get("limit_scope", "card_number") or "card_number"),
                )
            )
            state.next_effect_id += 1
        if deferred_secret_auto:
            self._checkpoint(state, "secret_auto_registration_deferred")

    @staticmethod
    def _can_register_effect_trigger_from_zone(source_zone: str, trigger: str) -> bool:
        normalized_zone = str(source_zone or "").strip().lower()
        if normalized_zone in {"hand", "life", "deck"}:
            return trigger in {"self_activate_main", "self_activate_battle"}
        return True

    @staticmethod
    def _is_secret_zone(source_zone: str) -> bool:
        return str(source_zone or "").strip().lower() in {"hand", "life", "deck"}

    @staticmethod
    def _clear_deferred_secret_autos_for_source(state: GameState, *, source_instance_id: int) -> None:
        state.deferred_secret_autos = [row for row in state.deferred_secret_autos if row.source_instance_id != source_instance_id]

    @staticmethod
    def _promote_deferred_secret_autos_to_public_zone(
        state: GameState,
        *,
        source_instance_id: int,
        source_zone: str,
    ) -> None:
        updated: list[DeferredSecretAuto] = []
        for row in state.deferred_secret_autos:
            if row.source_instance_id != source_instance_id:
                updated.append(row)
                continue
            updated.append(
                DeferredSecretAuto(
                    secret_auto_id=row.secret_auto_id,
                    owner_player_id=row.owner_player_id,
                    source_instance_id=row.source_instance_id,
                    source_card_id=row.source_card_id,
                    source_card_number=row.source_card_number,
                    source_zone=source_zone,
                    trigger=row.trigger,
                    handler_id=row.handler_id,
                    deferred_turn_number=row.deferred_turn_number,
                    deferred_phase=row.deferred_phase,
                    origin_zone=str(row.origin_zone or row.source_zone),
                    handler_params=dict(row.handler_params),
                    once_per_turn=row.once_per_turn,
                    limit_per_turn=row.limit_per_turn,
                    limit_scope=row.limit_scope,
                )
            )
        state.deferred_secret_autos = updated

    @staticmethod
    def _find_linked_deferred_secret_auto(
        state: GameState,
        *,
        source_instance_id: int,
        trigger: str,
        handler_id: str,
        handler_params: dict[str, int | str | bool],
    ) -> DeferredSecretAuto | None:
        return next(
            (
                row
                for row in state.deferred_secret_autos
                if row.source_instance_id == source_instance_id
                and row.trigger == trigger
                and row.handler_id == handler_id
                and dict(row.handler_params) == dict(handler_params)
            ),
            None,
        )

    @staticmethod
    def _preserve_secret_auto_provenance_on_public_registration(
        row: DeferredSecretAuto,
        *,
        source_zone: str,
    ) -> bool:
        trigger = str(row.trigger or "")
        origin_zone = str(row.origin_zone or row.source_zone)
        current_zone = str(source_zone or "")
        if trigger == "self_played":
            return origin_zone in {"hand", "life", "deck"} and current_zone in {"battle", "unison"}
        return (
            False
        )

    def _record_deferred_secret_auto(
        self,
        state: GameState,
        *,
        owner_player_id: int,
        card: CardInstance,
        source_zone: str,
        trigger: str,
        handler_id: str,
        handler_params: dict[str, int | str | bool],
        once_per_turn: bool,
        limit_per_turn: int | None,
        limit_scope: str,
    ) -> None:
        exists = any(
            row.owner_player_id == owner_player_id
            and row.source_instance_id == card.instance_id
            and row.source_zone == source_zone
            and row.trigger == trigger
            and row.handler_id == handler_id
            and dict(row.handler_params) == dict(handler_params)
            for row in state.deferred_secret_autos
        )
        if exists:
            return
        state.deferred_secret_autos.append(
            DeferredSecretAuto(
                secret_auto_id=state.next_secret_auto_id,
                owner_player_id=owner_player_id,
                source_instance_id=card.instance_id,
                source_card_id=card.card_id,
                source_card_number=str(card.card_number or ""),
                source_zone=source_zone,
                trigger=trigger,
                handler_id=handler_id,
                deferred_turn_number=state.turn_number,
                deferred_phase=state.phase,
                origin_zone=source_zone,
                handler_params=dict(handler_params),
                once_per_turn=bool(once_per_turn),
                limit_per_turn=limit_per_turn,
                limit_scope=str(limit_scope or "card_number"),
            )
        )
        state.next_secret_auto_id += 1

    def _emit_effect_event(
        self,
        state: GameState,
        *,
        name: str,
        actor_player_id: int | None,
        payload: dict[str, int | str | None],
    ) -> None:
        event = EffectEvent(
            event_id=state.next_effect_event_id,
            turn_number=state.turn_number,
            phase=state.phase,
            name=name,
            actor_player_id=actor_player_id,
            payload=dict(payload),
        )
        state.next_effect_event_id += 1
        state.effect_events.append(event)
        for reg in state.effect_registry:
            if self._effect_registration_matches_event(reg, event):
                state.pending_effects.append(PendingEffect(effect_id=reg.effect_id, event_id=event.event_id))
        self._record_secret_auto_opportunities(state, event)

    @staticmethod
    def _effect_registration_matches_event(reg: EffectRegistration, event: EffectEvent) -> bool:
        return RulesEngine._effect_trigger_matches_event(
            reg.trigger,
            source_instance_id=reg.source_instance_id,
            owner_player_id=reg.owner_player_id,
            event=event,
        )

    @staticmethod
    def _effect_trigger_matches_event(
        trigger: str,
        *,
        source_instance_id: int,
        owner_player_id: int,
        event: EffectEvent,
    ) -> bool:
        if trigger == "self_played":
            if event.name != "card_played":
                return False
            return int(event.payload.get("source_instance_id") or -1) == source_instance_id
        if trigger == "self_attacks":
            if event.name != "attack_declared":
                return False
            return int(event.payload.get("attacker_instance_id") or -1) == source_instance_id
        if trigger == "owner_leader_attacks":
            if event.name != "attack_declared":
                return False
            if event.actor_player_id != owner_player_id:
                return False
            return str(event.payload.get("attacker_zone") or "") == "leader"
        if trigger == "self_comboed":
            if event.name != "card_comboed":
                return False
            return int(event.payload.get("source_instance_id") or -1) == source_instance_id
        if trigger == "self_hidden_battle_to_drop":
            if event.name != "card_placed_into_drop":
                return False
            if str(event.payload.get("source_zone") or "") != "battle":
                return False
            if not bool(event.payload.get("source_hidden_mode") or False):
                return False
            return int(event.payload.get("source_instance_id") or -1) == source_instance_id
        if trigger == "self_switched_hidden":
            if event.name != "card_switched_hidden_mode":
                return False
            return int(event.payload.get("source_instance_id") or -1) == source_instance_id
        if trigger == "self_switched_revealed":
            if event.name != "card_switched_revealed_mode":
                return False
            return int(event.payload.get("source_instance_id") or -1) == source_instance_id
        if trigger == "self_activate_main":
            if event.name != "skill_activated":
                return False
            if str(event.payload.get("skill_kind") or "") != "activate_main":
                return False
            return int(event.payload.get("source_instance_id") or -1) == source_instance_id
        if trigger == "self_activate_battle":
            if event.name != "skill_activated":
                return False
            if str(event.payload.get("skill_kind") or "") != "activate_battle":
                return False
            return int(event.payload.get("source_instance_id") or -1) == source_instance_id
        if trigger == "self_koed":
            if event.name != "card_koed":
                return False
            return int(event.payload.get("source_instance_id") or -1) == source_instance_id
        if trigger == "owner_battle_played_from_warp":
            if event.name != "card_played":
                return False
            if event.actor_player_id != owner_player_id:
                return False
            if str(event.payload.get("source_zone") or "") != "battle":
                return False
            return str(event.payload.get("played_from") or "") == "warp"
        if trigger == "owner_field_extra_placed":
            return event.name == "field_extra_placed"
        if trigger == "owner_opponent_skill_plays_overcost_battle":
            if event.name != "card_played":
                return False
            if event.actor_player_id in {None, owner_player_id}:
                return False
            if str(event.payload.get("source_zone") or "") != "battle":
                return False
            return str(event.payload.get("played_from") or "").strip().lower() not in {"", "hand"}
        if trigger == "self_comboed_battle_end":
            return event.name == "battle_end"
        if trigger == "turn_start":
            return event.name == "turn_start" and event.actor_player_id == owner_player_id
        if trigger == "turn_end":
            return event.name == "turn_end" and event.actor_player_id == owner_player_id
        return False

    def _record_secret_auto_opportunities(self, state: GameState, event: EffectEvent) -> None:
        created = False
        preblocked = False
        regs_by_id = self._effect_registrations_for_limit_counting(state)
        events_by_id = {evt.event_id: evt for evt in state.effect_events}
        resolved_once_per_turn_counts = self._current_effect_once_per_turn_counts(state, regs_by_id=regs_by_id, events_by_id=events_by_id)
        resolved_limit_counts = self._current_effect_limit_counts(state, regs_by_id=regs_by_id, events_by_id=events_by_id)
        for row in state.deferred_secret_autos:
            if not self._effect_trigger_matches_event(
                row.trigger,
                source_instance_id=row.source_instance_id,
                owner_player_id=row.owner_player_id,
                event=event,
            ):
                continue
            exists = any(
                opp.secret_auto_id == row.secret_auto_id and opp.event_id == event.event_id
                for opp in state.secret_auto_opportunities
            )
            if exists:
                continue
            temp_reg = EffectRegistration(
                effect_id=-int(row.secret_auto_id),
                owner_player_id=row.owner_player_id,
                source_instance_id=row.source_instance_id,
                source_card_id=row.source_card_id,
                source_zone=row.source_zone,
                trigger=row.trigger,
                handler_id=row.handler_id,
                handler_params=dict(row.handler_params),
                source_card_number=row.source_card_number,
                once_per_turn=row.once_per_turn,
                limit_per_turn=row.limit_per_turn,
                limit_scope=row.limit_scope,
            )
            status = "pending"
            once_key = self._effect_once_per_turn_key(temp_reg)
            if once_key is not None and resolved_once_per_turn_counts.get(once_key, 0) >= 1:
                status = "blocked_once_per_turn"
            else:
                limit_key = self._effect_limit_key(temp_reg)
                if limit_key is not None and resolved_limit_counts.get(limit_key, 0) >= int(temp_reg.limit_per_turn or 0):
                    status = "blocked_limit_per_turn"
            state.secret_auto_opportunities.append(
                SecretAutoOpportunity(
                    opportunity_id=state.next_secret_auto_opportunity_id,
                    secret_auto_id=row.secret_auto_id,
                    owner_player_id=row.owner_player_id,
                    source_instance_id=row.source_instance_id,
                    source_card_id=row.source_card_id,
                    source_card_number=row.source_card_number,
                    source_zone=row.source_zone,
                    trigger=row.trigger,
                    handler_id=row.handler_id,
                    event_id=event.event_id,
                    event_name=event.name,
                    created_turn_number=state.turn_number,
                    created_phase=state.phase,
                    origin_zone=str(row.origin_zone or row.source_zone),
                    handler_params=dict(row.handler_params),
                    once_per_turn=row.once_per_turn,
                    limit_per_turn=row.limit_per_turn,
                    limit_scope=row.limit_scope,
                    status=status,
                    preblocked=(status != "pending"),
                )
            )
            state.next_secret_auto_opportunity_id += 1
            if status == "pending":
                state.log.append(
                    "Secret-area auto opportunity created: "
                    f"source_instance_id={row.source_instance_id} event_id={event.event_id} trigger={row.trigger}"
                )
            else:
                preblocked = True
                state.log.append(
                    "Secret-area auto opportunity preblocked: "
                    f"source_instance_id={row.source_instance_id} event_id={event.event_id} trigger={row.trigger} status={status}"
                )
            created = True
        if created:
            self._checkpoint(state, "secret_auto_opportunity_created")
        if preblocked:
            self._checkpoint(state, "secret_auto_opportunity_preblocked")

    def _reset_once_per_turn_effect_counters(self, state: GameState, *, player_id: int) -> None:
        updated: list[EffectRegistration] = []
        for reg in state.effect_registry:
            if reg.owner_player_id == player_id and reg.triggers_this_turn != 0:
                updated.append(
                    EffectRegistration(
                        effect_id=reg.effect_id,
                        owner_player_id=reg.owner_player_id,
                        source_instance_id=reg.source_instance_id,
                        source_card_id=reg.source_card_id,
                        source_zone=reg.source_zone,
                        trigger=reg.trigger,
                        handler_id=reg.handler_id,
                        handler_params=dict(reg.handler_params),
                        source_card_number=reg.source_card_number,
                        once_per_turn=reg.once_per_turn,
                        limit_per_turn=reg.limit_per_turn,
                        limit_scope=reg.limit_scope,
                        triggers_this_turn=0,
                    )
                )
            else:
                updated.append(reg)
        state.effect_registry = updated

    @staticmethod
    def _resolve_effect_limit_per_turn(handler_params: dict[str, int | str | bool]) -> int | None:
        raw = handler_params.get("limit_per_turn")
        return int(raw) if isinstance(raw, int) and raw > 0 else None

    @staticmethod
    def _effect_once_per_turn_key(reg: EffectRegistration) -> tuple[object, ...] | None:
        if not reg.once_per_turn:
            return None
        return (
            reg.owner_player_id,
            reg.source_instance_id,
            reg.trigger,
            reg.handler_id,
            tuple(sorted(reg.handler_params.items())),
        )

    def _current_effect_once_per_turn_counts(
        self,
        state: GameState,
        *,
        regs_by_id: dict[int, EffectRegistration],
        events_by_id: dict[int, EffectEvent],
    ) -> dict[tuple[object, ...], int]:
        counts: dict[tuple[object, ...], int] = {}
        for row in state.effect_resolutions:
            if not row.resolved:
                continue
            reg = regs_by_id.get(row.effect_id)
            evt = events_by_id.get(row.event_id)
            if reg is None or evt is None or evt.turn_number != state.turn_number:
                continue
            key = self._effect_once_per_turn_key(reg)
            if key is None:
                continue
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def _effect_limit_source_group(reg: EffectRegistration) -> str:
        scope = str(reg.limit_scope or "card_number").strip() or "card_number"
        if scope == "source_instance":
            return f"instance:{reg.source_instance_id}"
        if scope == "card_id":
            return f"card_id:{reg.source_card_id}"
        return str(reg.source_card_number or f"card_id:{reg.source_card_id}")

    @staticmethod
    def _effect_limit_key(reg: EffectRegistration) -> tuple[object, ...] | None:
        if reg.limit_per_turn is None or reg.limit_per_turn <= 0:
            return None
        scope = str(reg.limit_scope or "card_number").strip() or "card_number"
        source_group = RulesEngine._effect_limit_source_group(reg)
        return (
            reg.owner_player_id,
            scope,
            source_group,
            reg.trigger,
            reg.handler_id,
            tuple(sorted(reg.handler_params.items())),
        )

    def _current_effect_limit_counts(
        self,
        state: GameState,
        *,
        regs_by_id: dict[int, EffectRegistration],
        events_by_id: dict[int, EffectEvent],
    ) -> dict[tuple[object, ...], int]:
        counts: dict[tuple[object, ...], int] = {}
        for row in state.effect_resolutions:
            if not row.resolved:
                continue
            reg = regs_by_id.get(row.effect_id)
            evt = events_by_id.get(row.event_id)
            if reg is None or evt is None or evt.turn_number != state.turn_number:
                continue
            key = self._effect_limit_key(reg)
            if key is None:
                continue
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _effect_registrations_for_limit_counting(self, state: GameState) -> dict[int, EffectRegistration]:
        regs_by_id = {reg.effect_id: reg for reg in state.effect_registry}
        for opportunity in state.secret_auto_opportunities:
            if opportunity.status != "declared":
                continue
            effect_id = -int(opportunity.secret_auto_id)
            regs_by_id[effect_id] = EffectRegistration(
                effect_id=effect_id,
                owner_player_id=opportunity.owner_player_id,
                source_instance_id=opportunity.source_instance_id,
                source_card_id=opportunity.source_card_id,
                source_zone=opportunity.source_zone,
                trigger=opportunity.trigger,
                handler_id=opportunity.handler_id,
                handler_params=dict(opportunity.handler_params),
                source_card_number=opportunity.source_card_number,
                once_per_turn=opportunity.once_per_turn,
                limit_per_turn=opportunity.limit_per_turn,
                limit_scope=opportunity.limit_scope,
            )
        return regs_by_id

    def _pop_next_pending_effect(self, state: GameState) -> PendingEffect | None:
        if not state.pending_effects:
            return None
        regs_by_id = {reg.effect_id: reg for reg in state.effect_registry}
        owner_order = [state.active_player, self._opponent_of(state.active_player)]
        for owner_id in owner_order:
            matching: list[tuple[int, PendingEffect]] = []
            for idx, entry in enumerate(state.pending_effects):
                reg = regs_by_id.get(entry.effect_id)
                if reg is not None and reg.owner_player_id == owner_id:
                    matching.append((idx, entry))
            if matching:
                selected_idx = min(matching, key=lambda item: (int(item[1].event_id), int(item[1].effect_id), int(item[0])))[0]
                return state.pending_effects.pop(selected_idx)
        return state.pending_effects.pop(0)

    def _resolve_pending_effects(self, state: GameState) -> None:
        if not state.pending_effects:
            return
        regs_by_id = self._effect_registrations_for_limit_counting(state)
        events_by_id = {evt.event_id: evt for evt in state.effect_events}
        resolved_once_per_turn_counts = self._current_effect_once_per_turn_counts(state, regs_by_id=regs_by_id, events_by_id=events_by_id)
        resolved_limit_counts = self._current_effect_limit_counts(state, regs_by_id=regs_by_id, events_by_id=events_by_id)
        while state.pending_effects:
            entry = self._pop_next_pending_effect(state)
            if entry is None:
                break
            regs_by_id = self._effect_registrations_for_limit_counting(state)
            events_by_id = {evt.event_id: evt for evt in state.effect_events}
            reg = regs_by_id.get(entry.effect_id)
            evt = events_by_id.get(entry.event_id)
            if reg is None or evt is None:
                state.effect_resolutions.append(
                    EffectResolution(effect_id=entry.effect_id, event_id=entry.event_id, resolved=False, reason="missing_context")
                )
                continue
            once_key = self._effect_once_per_turn_key(reg)
            if once_key is not None and resolved_once_per_turn_counts.get(once_key, 0) >= 1:
                state.effect_resolutions.append(
                    EffectResolution(effect_id=reg.effect_id, event_id=evt.event_id, resolved=False, reason="once_per_turn_used")
                )
                state.log.append(
                    "Public effect blocked by once-per-turn: "
                    f"effect_id={reg.effect_id} source_instance_id={reg.source_instance_id} "
                    f"trigger={reg.trigger} handler={reg.handler_id}"
                )
                self._checkpoint(state, "effect_once_per_turn_blocked")
                continue
            limit_key = self._effect_limit_key(reg)
            if limit_key is not None and resolved_limit_counts.get(limit_key, 0) >= int(reg.limit_per_turn or 0):
                state.effect_resolutions.append(
                    EffectResolution(effect_id=reg.effect_id, event_id=evt.event_id, resolved=False, reason="limit_per_turn_used")
                )
                state.log.append(
                    "Public effect blocked by limit: "
                    f"effect_id={reg.effect_id} source_instance_id={reg.source_instance_id} "
                    f"limit_scope={reg.limit_scope} limit_per_turn={reg.limit_per_turn} "
                    f"trigger={reg.trigger} handler={reg.handler_id}"
                )
                self._checkpoint(state, "effect_limit_per_turn_blocked")
                continue
            if not self._is_effect_source_active(state, reg):
                state.effect_resolutions.append(
                    EffectResolution(effect_id=reg.effect_id, event_id=evt.event_id, resolved=False, reason="source_missing")
                )
                continue
            handler = self._effect_handlers.get(reg.handler_id)
            if handler is None:
                state.effect_resolutions.append(
                    EffectResolution(effect_id=reg.effect_id, event_id=evt.event_id, resolved=False, reason="missing_handler")
                )
                continue
            handler(state, evt, reg)
            next_reg = EffectRegistration(
                effect_id=reg.effect_id,
                owner_player_id=reg.owner_player_id,
                source_instance_id=reg.source_instance_id,
                source_card_id=reg.source_card_id,
                source_zone=reg.source_zone,
                trigger=reg.trigger,
                handler_id=reg.handler_id,
                handler_params=dict(reg.handler_params),
                source_card_number=reg.source_card_number,
                once_per_turn=reg.once_per_turn,
                limit_per_turn=reg.limit_per_turn,
                limit_scope=reg.limit_scope,
                triggers_this_turn=reg.triggers_this_turn + 1,
            )
            state.effect_registry = [next_reg if item.effect_id == reg.effect_id else item for item in state.effect_registry]
            if once_key is not None:
                resolved_once_per_turn_counts[once_key] = resolved_once_per_turn_counts.get(once_key, 0) + 1
            if limit_key is not None:
                resolved_limit_counts[limit_key] = resolved_limit_counts.get(limit_key, 0) + 1
            state.effect_resolutions.append(
                EffectResolution(effect_id=reg.effect_id, event_id=evt.event_id, resolved=True, reason="ok")
            )

    @staticmethod
    def _evaluate_continuous_effects(_state: GameState) -> None:
        # Phase 4.1: continuous/permanent effects will be evaluated here without entering pending status.
        return

    @staticmethod
    def _handle_noop_effect(state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        state.log.append(
            f"Effect resolved: effect_id={reg.effect_id} source={reg.source_instance_id} trigger={reg.trigger} event={event.name}"
        )

    def _handle_auto_draw_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        self._draw_one(state, reg.owner_player_id)
        self._checkpoint(state, "effect_auto_draw_on_play")

    def _handle_auto_draw_on_attack(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "attack_declared":
            return
        self._draw_one(state, reg.owner_player_id)
        self._checkpoint(state, "effect_auto_draw_on_attack")

    def _handle_auto_draw_n(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name not in {"card_played", "attack_declared", "card_comboed", "skill_activated", "turn_start", "turn_end"}:
            return
        amount = self._resolve_effect_int_param(state, reg, "amount", default=1)
        if amount <= 0:
            return
        for _ in range(amount):
            self._draw_one(state, reg.owner_player_id)
        self._checkpoint(state, "effect_auto_draw_n")

    def _handle_auto_pay_life_on_attack_gain_power_and_keyword_for_turn(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "attack_declared":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        source = self._find_by_instance(owner, reg.source_zone, reg.source_instance_id)
        if source is None:
            return
        life_to_hand = self._resolve_effect_int_param(state, reg, "life_to_hand", default=1)
        if life_to_hand > 0:
            if len(owner.life) < life_to_hand:
                return
            for _ in range(life_to_hand):
                owner.hand.append(owner.life.pop(0))
        delta = self._resolve_effect_int_param(state, reg, "power_delta", default=0)
        if delta != 0:
            self._apply_temporary_power_delta(state, card=source, delta=delta, reason="effect_self_attack_buff")
        grant_keyword = str(reg.handler_params.get("grant_keyword", "")).strip()
        if grant_keyword and not self._card_has_keyword(source, grant_keyword):
            source.temporary_keywords = tuple(list(source.temporary_keywords) + [grant_keyword])
        self._checkpoint(state, "effect_auto_pay_life_on_attack_gain_power_and_keyword_for_turn")

    def _handle_auto_add_up_to_n_from_owner_hand_to_life_on_owner_leader_attack(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "attack_declared":
            return
        if not self._effect_requirements_met(state, reg):
            return
        if event.actor_player_id != reg.owner_player_id:
            return
        if str(event.payload.get("attacker_zone") or "") != "leader":
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None or not owner.hand:
            return
        amount = self._resolve_effect_int_param(state, reg, "amount", default=1)
        if amount <= 0:
            return
        raw_colors = str(reg.handler_params.get("allowed_colors", "")).strip().lower()
        allowed_colors = {c.strip() for c in raw_colors.replace("/", ",").replace("|", ",").split(",") if c.strip()}
        chosen_indexes: list[int] = []
        for i, c in enumerate(owner.hand):
            if allowed_colors:
                colors = {p.strip().lower() for p in str(c.color or "").replace("/", ",").split(",") if p.strip()}
                if colors and colors.isdisjoint(allowed_colors):
                    continue
            chosen_indexes.append(i)
            if len(chosen_indexes) >= amount:
                break
        if not chosen_indexes:
            return
        removed = 0
        for idx in chosen_indexes:
            owner.life.append(owner.hand.pop(idx - removed))
            removed += 1
        self._checkpoint(state, "effect_auto_add_up_to_n_from_owner_hand_to_life_on_owner_leader_attack")

    def _handle_auto_add_up_to_n_from_owner_hand_to_life_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        required_from = str(reg.handler_params.get("requires_played_from", "")).strip().lower()
        if required_from:
            played_from = str(event.payload.get("played_from") or "").strip().lower()
            if played_from != required_from:
                return
        owner = state.players.get(reg.owner_player_id)
        if owner is None or not owner.hand:
            return
        amount = self._resolve_effect_int_param(state, reg, "amount", default=1)
        if amount <= 0:
            return
        raw_colors = str(reg.handler_params.get("allowed_colors", "")).strip().lower()
        allowed_colors = {c.strip() for c in raw_colors.replace("/", ",").replace("|", ",").split(",") if c.strip()}
        chosen_indexes: list[int] = []
        for i, c in enumerate(owner.hand):
            if allowed_colors:
                colors = {p.strip().lower() for p in str(c.color or "").replace("/", ",").split(",") if p.strip()}
                if colors and colors.isdisjoint(allowed_colors):
                    continue
            chosen_indexes.append(i)
            if len(chosen_indexes) >= amount:
                break
        if not chosen_indexes:
            return
        removed = 0
        for idx in chosen_indexes:
            owner.life.append(owner.hand.pop(idx - removed))
            removed += 1
        self._checkpoint(state, "effect_auto_add_up_to_n_from_owner_hand_to_life_on_play")

    def _handle_auto_gain_wormhole_on_owner_black_battle_played_from_warp(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        if event.actor_player_id != reg.owner_player_id:
            return
        if str(event.payload.get("source_zone") or "") != "battle":
            return
        if str(event.payload.get("played_from") or "") != "warp":
            return
        source_card_id = int(event.payload.get("source_card_id") or -1)
        if source_card_id <= 0:
            return
        runtime = self._resolve_card_runtime_data(source_card_id)
        if (runtime.color or "").strip().lower() != "black":
            return
        state.log.append(f"effect:wormhole_gain:source={reg.source_instance_id}")
        self._checkpoint(state, "effect_auto_gain_wormhole_on_owner_black_battle_played_from_warp")

    def _handle_auto_add_top_deck_to_energy_rest_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None or not owner.deck:
            return
        card = self._create_card_instance(next_instance_id=state.next_instance_id, card_id=owner.deck.pop(0), owner_id=reg.owner_player_id)
        state.next_instance_id += 1
        card.resting = True
        owner.energy.append(card)
        self._checkpoint(state, "effect_auto_add_top_deck_to_energy_rest_on_play")

    def _handle_auto_power_reduce_opponent_unison_on_self_ko(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_koed":
            return
        if not self._effect_requirements_met(state, reg):
            return
        delta = self._resolve_effect_int_param(state, reg, "power_delta", default=-10000)
        if delta == 0:
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        opponent_id = self._opponent_of(reg.owner_player_id)
        candidates = list(state.players[opponent_id].unison_area)
        if not candidates:
            return
        policy = str(reg.handler_params.get("target_policy", "first"))
        indexes = self._choose_effect_target_indexes(state, reg, candidates, max_targets, policy)
        for i in indexes:
            self._modify_card_power(state, card=candidates[i], delta=delta, reason="effect_unison_power_reduce")
        self._run_confirmative_rule_processing(state)
        self._checkpoint(state, "effect_auto_power_reduce_opponent_unison_on_self_ko")

    def _handle_auto_gain_control_opponent_unison_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        opponent_id = self._opponent_of(reg.owner_player_id)
        opponent = state.players.get(opponent_id)
        owner = state.players.get(reg.owner_player_id)
        if opponent is None or owner is None or not opponent.unison_area:
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        policy = str(reg.handler_params.get("target_policy", "first"))
        indexes = self._choose_effect_target_indexes(state, reg, list(opponent.unison_area), max_targets, policy)
        if not indexes:
            return
        # Current engine model allows one Unison in play; mirror play replacement semantics.
        self._replace_owner_unison_if_needed(state, owner)
        idx = sorted(indexes)[0]
        taken = opponent.unison_area.pop(idx)
        taken.owner_id = reg.owner_player_id
        owner.unison_area.append(taken)
        self._checkpoint(state, "effect_auto_gain_control_opponent_unison_on_play")

    def _handle_auto_add_n_life_to_hand_on_self_ko(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_koed":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None or not owner.life:
            return
        amount = self._resolve_effect_int_param(state, reg, "amount", default=1)
        if amount <= 0:
            return
        for _ in range(min(amount, len(owner.life))):
            owner.hand.append(owner.life.pop(0))
        self._checkpoint(state, "effect_auto_add_n_life_to_hand_on_self_ko")

    def _handle_auto_look_top_add_up_to_one_to_hand_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name not in {"card_played", "skill_activated", "attack_declared"}:
            return
        if not self._effect_requirements_met(state, reg):
            return
        required_from = str(reg.handler_params.get("requires_played_from", "")).strip().lower()
        if required_from:
            played_from = str(event.payload.get("played_from") or "").strip().lower()
            if played_from != required_from:
                return
        owner = state.players.get(reg.owner_player_id)
        if owner is None or not owner.deck:
            return
        look_count = self._resolve_effect_int_param(state, reg, "look_count", default=5)
        if look_count <= 0:
            return
        max_add = self._resolve_effect_int_param(state, reg, "max_add", default=1)
        if max_add <= 0:
            return
        top_n = min(look_count, len(owner.deck))
        max_cost = self._resolve_effect_int_param(state, reg, "max_cost", default=-1)
        raw_colors = str(reg.handler_params.get("allowed_colors", "")).strip().lower()
        allowed_colors = {c.strip() for c in raw_colors.replace("|", ",").split(",") if c.strip()}
        required_type = str(reg.handler_params.get("required_card_type", "")).strip().upper()
        raw_traits = str(reg.handler_params.get("required_traits", "")).strip().lower()
        required_traits = {t.strip() for t in raw_traits.replace("|", ",").split(",") if t.strip()}
        raw_characters = str(reg.handler_params.get("required_characters", "")).strip().lower()
        required_characters = {t.strip() for t in raw_characters.replace("|", ",").split(",") if t.strip()}
        required_name_contains = str(reg.handler_params.get("required_name_contains", "")).strip().upper()
        picked_indexes: list[int] = []
        for i in range(top_n):
            deck_card = owner.deck[i]
            deck_card_id = deck_card.card_id if isinstance(deck_card, CardInstance) else int(deck_card)
            runtime = self._resolve_card_runtime_data(deck_card_id)
            if required_type and required_type not in (runtime.card_type or "").upper():
                continue
            if max_cost >= 0:
                cost = runtime.energy_cost
                if cost is None or cost > max_cost:
                    continue
            if allowed_colors:
                runtime_colors = {
                    part.strip().lower()
                    for part in str(runtime.color or "").replace("/", ",").split(",")
                    if part.strip()
                }
                if runtime_colors and runtime_colors.isdisjoint(allowed_colors):
                    continue
            if required_traits:
                runtime_traits = {part.strip().lower() for part in (runtime.traits or ()) if part.strip()}
                if runtime_traits.isdisjoint(required_traits):
                    continue
            if required_characters:
                runtime_characters = {part.strip().lower() for part in (runtime.characters or ()) if part.strip()}
                if runtime_characters.isdisjoint(required_characters):
                    continue
            if required_name_contains:
                runtime_name = str(runtime.card_name or "").upper()
                if required_name_contains not in runtime_name:
                    continue
            picked_indexes.append(i)
            if len(picked_indexes) >= max_add:
                break
        if not picked_indexes:
            return
        move_unpicked_to_bottom = bool(reg.handler_params.get("move_unpicked_to_bottom", False))
        added = 0
        if move_unpicked_to_bottom:
            original_top = owner.deck[:top_n]
            remainder = owner.deck[top_n:]
            picked_set = set(picked_indexes)
            selected_cards = [card for i, card in enumerate(original_top) if i in picked_set]
            kept_top = [card for i, card in enumerate(original_top) if i not in picked_set]
            owner.deck = remainder + kept_top
            for deck_card in selected_cards:
                card_id = deck_card.card_id if isinstance(deck_card, CardInstance) else int(deck_card)
                card = self._create_card_instance(next_instance_id=state.next_instance_id, card_id=card_id, owner_id=reg.owner_player_id)
                state.next_instance_id += 1
                owner.hand.append(card)
                added += 1
        else:
            removed = 0
            for idx in picked_indexes:
                deck_card = owner.deck.pop(idx - removed)
                removed += 1
                card_id = deck_card.card_id if isinstance(deck_card, CardInstance) else int(deck_card)
                card = self._create_card_instance(next_instance_id=state.next_instance_id, card_id=card_id, owner_id=reg.owner_player_id)
                state.next_instance_id += 1
                owner.hand.append(card)
                added += 1
        discard_after_add = self._resolve_effect_int_param(state, reg, "discard_after_add", default=0)
        if added > 0 and discard_after_add > 0 and owner.hand:
            for _ in range(min(discard_after_add, len(owner.hand))):
                owner.drop.append(owner.hand.pop(0))
        bottom_deck_after_add = self._resolve_effect_int_param(state, reg, "bottom_deck_after_add", default=0)
        bottom_deck_after_add_exact = self._resolve_effect_int_param(state, reg, "bottom_deck_after_add_exact_add_count", default=-1)
        if (
            added > 0
            and bottom_deck_after_add > 0
            and owner.hand
            and (bottom_deck_after_add_exact < 0 or added == bottom_deck_after_add_exact)
        ):
            for _ in range(min(bottom_deck_after_add, len(owner.hand))):
                card = owner.hand.pop(0)
                owner.deck.append(card.card_id)
        self._checkpoint(state, "effect_auto_look_top_add_up_to_one_to_hand_on_play")

    def _handle_auto_add_up_to_n_from_owner_deck_to_hand_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        required_from = str(reg.handler_params.get("requires_played_from", "")).strip().lower()
        if required_from:
            played_from = str(event.payload.get("played_from") or "").strip().lower()
            if played_from != required_from:
                return
        owner = state.players.get(reg.owner_player_id)
        if owner is None or not owner.deck:
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        max_cost = self._resolve_effect_int_param(state, reg, "max_cost", default=-1)
        raw_colors = str(reg.handler_params.get("allowed_colors", "")).strip().lower()
        allowed_colors = {c.strip() for c in raw_colors.replace("|", ",").replace("/", ",").split(",") if c.strip()}
        required_type = str(reg.handler_params.get("required_card_type", "")).strip().upper()
        requires_skill_less = bool(reg.handler_params.get("requires_skill_less", False))
        raw_traits = str(reg.handler_params.get("required_traits", "")).strip().lower()
        required_traits = {t.strip() for t in raw_traits.replace("|", ",").split(",") if t.strip()}
        raw_characters = str(reg.handler_params.get("required_characters", "")).strip().lower()
        required_characters = {t.strip() for t in raw_characters.replace("|", ",").split(",") if t.strip()}
        chosen_indexes: list[int] = []
        for i, deck_card in enumerate(owner.deck):
            deck_card_id = deck_card.card_id if isinstance(deck_card, CardInstance) else int(deck_card)
            runtime = self._resolve_card_runtime_data(deck_card_id)
            if required_type and required_type not in (runtime.card_type or "").upper():
                continue
            if max_cost >= 0 and (runtime.energy_cost is None or runtime.energy_cost > max_cost):
                continue
            if allowed_colors:
                runtime_colors = {part.strip().lower() for part in str(runtime.color or "").replace("/", ",").split(",") if part.strip()}
                if runtime_colors and runtime_colors.isdisjoint(allowed_colors):
                    continue
            if required_traits:
                runtime_traits = {part.strip().lower() for part in (runtime.traits or ()) if part.strip()}
                if runtime_traits.isdisjoint(required_traits):
                    continue
            if required_characters:
                runtime_characters = {part.strip().lower() for part in (runtime.characters or ()) if part.strip()}
                if runtime_characters.isdisjoint(required_characters):
                    continue
            if requires_skill_less:
                kws = {k.strip().lower() for k in (runtime.keywords or ()) if k}
                if "skill-less" not in kws and "skill less" not in kws:
                    continue
            chosen_indexes.append(i)
            if len(chosen_indexes) >= max_targets:
                break
        if not chosen_indexes:
            return
        removed = 0
        for idx in chosen_indexes:
            deck_card = owner.deck.pop(idx - removed)
            removed += 1
            card_id = deck_card.card_id if isinstance(deck_card, CardInstance) else int(deck_card)
            card = self._create_card_instance(next_instance_id=state.next_instance_id, card_id=card_id, owner_id=reg.owner_player_id)
            state.next_instance_id += 1
            owner.hand.append(card)
        self._checkpoint(state, "effect_auto_add_up_to_n_from_owner_deck_to_hand_on_play")

    def _handle_auto_play_up_to_n_from_owner_drop_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        required_from = str(reg.handler_params.get("requires_played_from", "")).strip().lower()
        if required_from:
            played_from = str(event.payload.get("played_from") or "").strip().lower()
            if played_from != required_from:
                return
        owner = state.players.get(reg.owner_player_id)
        if owner is None or not owner.drop:
            return
        discard_before = self._resolve_effect_int_param(state, reg, "discard_from_hand_before", default=0)
        if discard_before > 0:
            if len(owner.hand) < discard_before:
                return
            for _ in range(discard_before):
                owner.drop.append(owner.hand.pop(0))
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        max_cost = self._resolve_effect_int_param(state, reg, "max_cost", default=-1)
        raw_colors = str(reg.handler_params.get("allowed_colors", "")).strip().lower()
        allowed_colors = {c.strip() for c in raw_colors.replace("|", ",").replace("/", ",").split(",") if c.strip()}
        required_type = str(reg.handler_params.get("required_card_type", "")).strip().upper()
        requires_skill_less = bool(reg.handler_params.get("requires_skill_less", False))
        rest_mode = bool(reg.handler_params.get("rest_mode", False))
        negate_skills = bool(reg.handler_params.get("negate_skills", False))
        chosen_indexes: list[int] = []
        for i, c in enumerate(owner.drop):
            if required_type and required_type not in (c.card_type or "").upper():
                continue
            if max_cost >= 0 and (c.energy_cost is None or c.energy_cost > max_cost):
                continue
            if allowed_colors:
                colors = {p.strip().lower() for p in str(c.color or "").replace("/", ",").split(",") if p.strip()}
                if colors and colors.isdisjoint(allowed_colors):
                    continue
            if requires_skill_less:
                kws = {k.strip().lower() for k in (c.keywords or ()) if k}
                if "skill-less" not in kws and "skill less" not in kws:
                    continue
            chosen_indexes.append(i)
            if len(chosen_indexes) >= max_targets:
                break
        if not chosen_indexes:
            return
        removed = 0
        for idx in chosen_indexes:
            card = owner.drop.pop(idx - removed)
            removed += 1
            card.resting = rest_mode
            if negate_skills:
                card.keywords = ()
                card.counter_modes = ()
                card.has_counter = False
                card.has_counter_attack = False
                card.has_counter_battle_card_attack = False
                card.has_counter_play = False
                card.has_counter_counter = False
                card.has_activate_main = False
                card.has_activate_battle = False
                card.has_auto = False
                card.has_permanent = False
                card.has_draw = False
                card.max_draw = None
                card.auto_once_per_turn = False
                card.auto_draw_on_play = False
                card.auto_draw_on_attack = False
                card.has_barrier = False
            target_zone = "battle"
            if "UNISON" in (card.card_type or "").upper():
                target_zone = "unison"
                self._replace_owner_unison_if_needed(state, owner)
                owner.unison_area.append(card)
            else:
                owner.battle_area.append(card)
            if not negate_skills:
                self._register_card_effects(state, player_id=reg.owner_player_id, source_zone=target_zone, card=card)
            self._emit_effect_event(
                state,
                name="card_played",
                actor_player_id=reg.owner_player_id,
                payload={
                    "source_instance_id": card.instance_id,
                    "source_card_id": card.card_id,
                    "source_zone": target_zone,
                    "played_from": "drop",
                },
            )
        self._checkpoint(state, "effect_auto_play_up_to_n_from_owner_drop_on_play")

    def _handle_auto_add_markers_per_n_multicolor_energy_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        source = self._find_by_instance(owner, reg.source_zone, reg.source_instance_id)
        if source is None:
            return
        min_source_markers = self._resolve_effect_int_param(state, reg, "min_source_markers", default=0)
        if min_source_markers > 0 and source.markers < min_source_markers:
            return
        per_n_energy = self._resolve_effect_int_param(state, reg, "per_n_energy", default=1)
        if per_n_energy <= 0:
            per_n_energy = 1
        multicolor_energy = 0
        for c in owner.energy:
            raw = str(c.color or "")
            if "/" in raw:
                multicolor_energy += 1
        gained = multicolor_energy // per_n_energy
        if gained <= 0:
            return
        source.markers += gained
        self._checkpoint(state, "effect_auto_add_markers_per_n_multicolor_energy_on_play")

    def _handle_auto_top_deck_add_if_color_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None or not owner.deck:
            return
        top_card_id = owner.deck[0]
        runtime = self._resolve_card_runtime_data(top_card_id)
        required_color = str(reg.handler_params.get("required_color", "")).strip().lower()
        matches = (runtime.color or "").strip().lower() == required_color if required_color else True
        if matches:
            self._draw_one(state, reg.owner_player_id)
            self._checkpoint(state, "effect_auto_top_deck_add_if_color_on_play")
            return
        if bool(reg.handler_params.get("move_to_bottom_on_fail", True)) and owner.deck:
            owner.deck.append(owner.deck.pop(0))
            self._checkpoint(state, "effect_auto_top_deck_bottom_on_fail")

    def _handle_auto_play_self_from_combo_on_battle_end(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "battle_end":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return

        source: CardInstance | None = None
        for i, c in enumerate(owner.combo_area):
            if c.instance_id == reg.source_instance_id:
                source = owner.combo_area.pop(i)
                break
        if source is None:
            for i, c in enumerate(owner.drop):
                if c.instance_id == reg.source_instance_id:
                    source = owner.drop.pop(i)
                    break
        if source is None:
            return

        source.resting = bool(reg.handler_params.get("resting", False))
        owner.battle_area.append(source)
        self._register_card_effects(state, player_id=reg.owner_player_id, source_zone="battle", card=source)
        self._emit_effect_event(
            state,
            name="card_played",
            actor_player_id=reg.owner_player_id,
            payload={
                "source_instance_id": source.instance_id,
                "source_card_id": source.card_id,
                "source_zone": "battle",
                "played_from": "drop",
            },
        )
        self._checkpoint(state, "effect_auto_play_self_from_combo_on_battle_end")

    def _handle_activate_play_self_from_hand(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "skill_activated":
            return
        if not self._effect_requirements_met(state, reg):
            return
        if str(event.payload.get("skill_kind") or "") != "activate_main":
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        source = self._find_by_instance(owner, "hand", reg.source_instance_id)
        if source is None:
            return
        if str(event.payload.get("source_zone") or "") != "hand":
            return
        self._open_counter_window(
            state,
            kind="play",
            responder_player_id=self._opponent_of(reg.owner_player_id),
            pending_action=PendingAction(
                action_type="play_from_hand",
                actor_player_id=reg.owner_player_id,
                payload={
                    "card_instance_id": source.instance_id,
                    "paid_energy_cards": 0,
                    "resting": bool(reg.handler_params.get("resting", False)),
                    "marker_count": int(reg.handler_params.get("markers", 0)) if "markers" in reg.handler_params else None,
                    "declared_via_effect": "activate_play_self_from_hand",
                    "declared_from_skill_kind": str(event.payload.get("skill_kind") or ""),
                },
            ),
        )
        self._checkpoint(state, "counter_timing_play_from_skill")

    def _handle_activate_draw_n_and_gain_keyword_for_turn(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "skill_activated":
            return
        if not self._effect_requirements_met(state, reg):
            return
        required_skill_kind = "activate_battle" if reg.trigger == "self_activate_battle" else "activate_main"
        if str(event.payload.get("skill_kind") or "") != required_skill_kind:
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        source = self._find_by_instance(owner, reg.source_zone, reg.source_instance_id)
        if source is None:
            return
        amount = self._resolve_effect_int_param(state, reg, "amount", default=1)
        for _ in range(max(amount, 0)):
            self._draw_one(state, reg.owner_player_id)
        grant_keyword = str(reg.handler_params.get("grant_keyword", "")).strip()
        if grant_keyword:
            self._append_temporary_keyword(source, grant_keyword, duration="turn")
        self._checkpoint(state, "effect_activate_draw_n_and_gain_keyword_for_turn")

    def _handle_activate_draw_n_play_self_from_hand_and_gain_keyword_until_opponent_turn_end(
        self,
        state: GameState,
        event: EffectEvent,
        reg: EffectRegistration,
    ) -> None:
        if event.name != "skill_activated":
            return
        if not self._effect_requirements_met(state, reg):
            return
        if str(event.payload.get("skill_kind") or "") != "activate_main":
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        source = self._find_by_instance(owner, "hand", reg.source_instance_id)
        if source is None:
            return
        amount = self._resolve_effect_int_param(state, reg, "amount", default=1)
        for _ in range(max(amount, 0)):
            self._draw_one(state, reg.owner_player_id)
        grant_keyword = str(reg.handler_params.get("grant_keyword", "")).strip()
        self._open_counter_window(
            state,
            kind="play",
            responder_player_id=self._opponent_of(reg.owner_player_id),
            pending_action=PendingAction(
                action_type="play_from_hand",
                actor_player_id=reg.owner_player_id,
                payload={
                    "card_instance_id": source.instance_id,
                    "paid_energy_cards": 0,
                    "declared_via_effect": "activate_draw_n_play_self_from_hand_and_gain_keyword_until_opponent_turn_end",
                    "declared_from_skill_kind": str(event.payload.get("skill_kind") or ""),
                    "grant_keyword_after_play": grant_keyword or None,
                    "keyword_clear_trigger_player_id": self._opponent_of(reg.owner_player_id) if grant_keyword else None,
                },
            ),
        )
        self._checkpoint(state, "counter_timing_play_from_skill")
        self._checkpoint(state, "effect_activate_draw_n_play_self_from_hand_and_gain_keyword_until_opponent_turn_end")

    def _handle_activate_gain_power_and_keyword_for_battle(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "skill_activated":
            return
        if not self._effect_requirements_met(state, reg):
            return
        if str(event.payload.get("skill_kind") or "") != "activate_battle":
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        source = self._find_by_instance(owner, reg.source_zone, reg.source_instance_id)
        if source is None:
            return
        delta = self._resolve_effect_int_param(state, reg, "power_delta", default=0)
        if delta:
            self._apply_battle_temporary_power_delta(state, card=source, delta=delta, reason="effect_activate_battle_buff")
        grant_keyword = str(reg.handler_params.get("grant_keyword", "")).strip()
        if grant_keyword:
            self._append_temporary_keyword(source, grant_keyword, duration="battle")
        self._checkpoint(state, "effect_activate_gain_power_and_keyword_for_battle")

    def _handle_activate_ko_up_to_n_opponent_battle(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "skill_activated":
            return
        if not self._effect_requirements_met(state, reg):
            return
        if str(event.payload.get("skill_kind") or "") != "activate_battle":
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        max_cost = self._resolve_effect_int_param(state, reg, "max_cost", default=-1)
        target_policy = str(reg.handler_params.get("target_policy", "first"))
        selected = self._select_opponent_battle_targets(
            state,
            reg,
            max_targets=max_targets,
            max_cost=max_cost,
            policy=target_policy,
        )
        if not selected:
            return
        opponent_id = self._opponent_of(reg.owner_player_id)
        for target in list({c.instance_id for c in selected}):
            self._ko_card(state, opponent_id, "battle", target)
        self._checkpoint(state, "effect_activate_ko_up_to_n_opponent_battle")

    def _handle_activate_switch_owner_battle_to_hidden_mode(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "skill_activated":
            return
        if not self._effect_requirements_met(state, reg):
            return
        if str(event.payload.get("skill_kind") or "") != "activate_main":
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        raw_colors = str(reg.handler_params.get("allowed_colors", "")).strip().lower()
        allowed_colors = {c.strip() for c in raw_colors.replace("|", ",").replace("/", ",").split(",") if c.strip()}
        raw_traits = str(reg.handler_params.get("required_traits", "")).strip().lower()
        required_traits = {t.strip() for t in raw_traits.replace("|", ",").split(",") if t.strip()}
        raw_characters = str(reg.handler_params.get("required_characters", "")).strip().lower()
        required_characters = {t.strip() for t in raw_characters.replace("|", ",").split(",") if t.strip()}
        required_name_contains = str(reg.handler_params.get("required_name_contains", "")).strip().upper()
        candidates = [
            card
            for card in owner.battle_area
            if not card.hidden_mode
            and self._card_matches_effect_filters(
                card,
                allowed_colors=allowed_colors,
                required_traits=required_traits,
                required_characters=required_characters,
                required_name_contains=required_name_contains,
            )
        ]
        if not candidates:
            return
        policy = str(reg.handler_params.get("target_policy", "first"))
        target = candidates[self._choose_effect_target_index(state, reg, candidates, policy)]
        target.hidden_mode = True
        self._emit_effect_event(
            state,
            name="card_switched_hidden_mode",
            actor_player_id=reg.owner_player_id,
            payload={
                "target_instance_id": target.instance_id,
                "target_card_id": target.card_id,
                "target_zone": "battle",
            },
        )
        self._checkpoint(state, "effect_activate_switch_owner_battle_to_hidden_mode")

    def _handle_activate_switch_self_to_hidden_mode(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "skill_activated":
            return
        if not self._effect_requirements_met(state, reg):
            return
        if str(event.payload.get("skill_kind") or "") != "activate_main":
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        source = self._find_by_instance(owner, reg.source_zone, reg.source_instance_id)
        if source is None or source.hidden_mode:
            return
        source.hidden_mode = True
        self._emit_effect_event(
            state,
            name="card_switched_hidden_mode",
            actor_player_id=reg.owner_player_id,
            payload={
                "source_instance_id": source.instance_id,
                "source_card_id": source.card_id,
                "source_zone": reg.source_zone,
                "owner_player_id": reg.owner_player_id,
            },
        )
        self._checkpoint(state, "effect_activate_switch_self_to_hidden_mode")

    def _handle_activate_gain_power_by_hidden_cost_target_original_power_for_turn(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "skill_activated":
            return
        if not self._effect_requirements_met(state, reg):
            return
        if str(event.payload.get("skill_kind") or "") != "activate_main":
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        source = self._find_by_instance(owner, reg.source_zone, reg.source_instance_id)
        if source is None:
            return
        cost_target_card_id = int(event.payload.get("cost_target_card_id") or -1)
        if cost_target_card_id <= 0:
            return
        delta = self._resolve_card_runtime_data(cost_target_card_id).power
        if delta == 0:
            return
        target_scope = str(reg.handler_params.get("target_scope", "self")).strip().lower()
        target: CardInstance | None = None
        if target_scope == "self":
            target = source
        elif target_scope == "owner_leader_or_matching_battle":
            candidates: list[CardInstance] = [owner.leader_area]
            raw_colors = str(reg.handler_params.get("target_allowed_colors", "")).strip().lower()
            allowed_colors = {c.strip() for c in raw_colors.replace("|", ",").replace("/", ",").split(",") if c.strip()}
            raw_traits = str(reg.handler_params.get("target_required_traits", "")).strip().lower()
            required_traits = {t.strip() for t in raw_traits.replace("|", ",").split(",") if t.strip()}
            raw_characters = str(reg.handler_params.get("target_required_characters", "")).strip().lower()
            required_characters = {t.strip() for t in raw_characters.replace("|", ",").split(",") if t.strip()}
            required_name_contains = str(reg.handler_params.get("target_required_name_contains", "")).strip().upper()
            candidates.extend(
                card
                for card in owner.battle_area
                if self._card_matches_effect_filters(
                    card,
                    allowed_colors=allowed_colors,
                    required_traits=required_traits,
                    required_characters=required_characters,
                    required_name_contains=required_name_contains,
                )
            )
            if not candidates:
                return
            target_policy = str(reg.handler_params.get("target_policy", "first"))
            target = candidates[self._choose_effect_target_index(state, reg, candidates, target_policy)]
        if target is None:
            return
        self._apply_temporary_power_delta(state, card=target, delta=delta, reason="effect_hidden_mode_power_copy")
        self._checkpoint(state, "effect_activate_gain_power_by_hidden_cost_target_original_power_for_turn")

    def _handle_activate_send_up_to_n_opponent_battle_to_warp(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "skill_activated":
            return
        if not self._effect_requirements_met(state, reg):
            return
        if str(event.payload.get("skill_kind") or "") != "activate_main":
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        max_cost = self._resolve_effect_int_param(state, reg, "max_cost", default=-1)
        target_policy = str(reg.handler_params.get("target_policy", "first"))
        selected = self._select_opponent_battle_targets(
            state,
            reg,
            max_targets=max_targets,
            max_cost=max_cost,
            policy=target_policy,
        )
        if not selected:
            return
        opponent_id = self._opponent_of(reg.owner_player_id)
        opponent = state.players.get(opponent_id)
        if opponent is None:
            return
        target_ids = {c.instance_id for c in selected}
        i = 0
        while i < len(opponent.battle_area):
            card = opponent.battle_area[i]
            if card.instance_id not in target_ids:
                i += 1
                continue
            opponent.warp.append(opponent.battle_area.pop(i))
        self._checkpoint(state, "effect_activate_send_up_to_n_opponent_battle_to_warp")

    def _handle_activate_ko_up_to_n_opponent_battle_and_buff_owner_leader_for_turn(
        self,
        state: GameState,
        event: EffectEvent,
        reg: EffectRegistration,
    ) -> None:
        if event.name != "skill_activated":
            return
        if not self._effect_requirements_met(state, reg):
            return
        if str(event.payload.get("skill_kind") or "") != "activate_main":
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets > 0:
            max_cost = self._resolve_effect_int_param(state, reg, "max_cost", default=-1)
            target_policy = str(reg.handler_params.get("target_policy", "first"))
            selected = self._select_opponent_battle_targets(
                state,
                reg,
                max_targets=max_targets,
                max_cost=max_cost,
                policy=target_policy,
            )
            if selected:
                opponent_id = self._opponent_of(reg.owner_player_id)
                for target in list({c.instance_id for c in selected}):
                    self._ko_card(state, opponent_id, "battle", target)
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        leader_delta = self._resolve_effect_int_param(state, reg, "leader_power_delta", default=0)
        if leader_delta != 0:
            self._apply_temporary_power_delta(state, card=owner.leader_area, delta=leader_delta, reason="effect_owner_leader_buff")
        self._checkpoint(state, "effect_activate_ko_up_to_n_opponent_battle_and_buff_owner_leader_for_turn")

    def _handle_activate_switch_owner_board_to_revealed_mode(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "skill_activated":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        candidates = [card for card in [*owner.battle_area, *owner.unison_area] if card.hidden_mode]
        if not candidates:
            return
        policy = str(reg.handler_params.get("target_policy", "first"))
        target = candidates[self._choose_effect_target_index(state, reg, candidates, policy)]
        target.hidden_mode = False
        self._emit_effect_event(
            state,
            name="card_switched_revealed_mode",
            actor_player_id=reg.owner_player_id,
            payload={
                "source_instance_id": target.instance_id,
                "source_card_id": target.card_id,
                "source_zone": "unison" if target in owner.unison_area else "battle",
                "owner_player_id": reg.owner_player_id,
            },
        )
        self._checkpoint(state, "effect_activate_switch_owner_board_to_revealed_mode")

    def _handle_activate_switch_all_opponent_battle_to_revealed_then_ko_up_to_n(
        self,
        state: GameState,
        event: EffectEvent,
        reg: EffectRegistration,
    ) -> None:
        if event.name != "skill_activated":
            return
        if not self._effect_requirements_met(state, reg):
            return
        if str(event.payload.get("skill_kind") or "") != "activate_main":
            return
        opponent_id = self._opponent_of(reg.owner_player_id)
        opponent = state.players.get(opponent_id)
        if opponent is None:
            return
        for target in opponent.battle_area:
            if not target.hidden_mode:
                continue
            target.hidden_mode = False
            self._emit_effect_event(
                state,
                name="card_switched_revealed_mode",
                actor_player_id=reg.owner_player_id,
                payload={
                    "source_instance_id": target.instance_id,
                    "source_card_id": target.card_id,
                    "source_zone": "battle",
                    "owner_player_id": opponent_id,
                },
            )
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets > 0:
            target_policy = str(reg.handler_params.get("target_policy", "first"))
            selected = self._select_opponent_battle_targets(
                state,
                reg,
                max_targets=max_targets,
                max_cost=-1,
                policy=target_policy,
            )
            for target in selected:
                self._ko_card(state, opponent_id, "battle", target.instance_id)
        self._checkpoint(state, "effect_activate_switch_all_opponent_battle_to_revealed_then_ko_up_to_n")

    def _handle_activate_drop_owner_hidden_mode_draw_n(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "skill_activated":
            return
        if not self._effect_requirements_met(state, reg):
            return
        if str(event.payload.get("skill_kind") or "") != "activate_main":
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        candidates = [card for card in owner.battle_area if card.hidden_mode]
        if not candidates:
            return
        policy = str(reg.handler_params.get("target_policy", "first"))
        target = candidates[self._choose_effect_target_index(state, reg, candidates, policy)]
        owner.battle_area.remove(target)
        owner.drop.append(target)
        self._emit_board_card_placed_into_drop(state, owner_player_id=reg.owner_player_id, card=target, source_zone="battle")
        amount = self._resolve_effect_int_param(state, reg, "amount", default=1)
        for _ in range(max(amount, 0)):
            self._draw_one(state, reg.owner_player_id)
        self._checkpoint(state, "effect_activate_drop_owner_hidden_mode_draw_n")

    def _handle_auto_switch_up_to_n_opponent_battle_to_hidden_then_reveal_on_opponent_turn_end(
        self, state: GameState, event: EffectEvent, reg: EffectRegistration
    ) -> None:
        if event.name != "attack_declared":
            return
        if not self._effect_requirements_met(state, reg):
            return
        opponent_id = self._opponent_of(reg.owner_player_id)
        opponent = state.players.get(opponent_id)
        if opponent is None:
            return
        candidates = [card for card in opponent.battle_area if not card.hidden_mode]
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0 or not candidates:
            return
        policy = str(reg.handler_params.get("target_policy", "first"))
        indexes = self._choose_effect_target_indexes(state, reg, candidates, max_targets, policy)
        if not indexes:
            return
        for idx in indexes:
            target = candidates[idx]
            target.hidden_mode = True
            self._emit_effect_event(
                state,
                name="card_switched_hidden_mode",
                actor_player_id=reg.owner_player_id,
                payload={
                    "source_instance_id": target.instance_id,
                    "source_card_id": target.card_id,
                    "source_zone": "battle",
                    "owner_player_id": opponent_id,
                },
            )
            self._schedule_delayed_mode_switch(
                state,
                owner_player_id=opponent_id,
                target_instance_id=target.instance_id,
                trigger_kind="turn_end",
                trigger_player_id=opponent_id,
                switch_to_hidden=False,
            )
        self._checkpoint(state, "effect_auto_switch_opponent_battle_hidden_then_reveal_on_opponent_turn_end")

    def _handle_auto_switch_up_to_n_opponent_battle_to_hidden_then_reveal_on_turn_end(
        self, state: GameState, event: EffectEvent, reg: EffectRegistration
    ) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        opponent_id = self._opponent_of(reg.owner_player_id)
        opponent = state.players.get(opponent_id)
        if opponent is None:
            return
        candidates = [card for card in opponent.battle_area if not card.hidden_mode]
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0 or not candidates:
            return
        policy = str(reg.handler_params.get("target_policy", "first"))
        indexes = self._choose_effect_target_indexes(state, reg, candidates, max_targets, policy)
        if not indexes:
            return
        for idx in indexes:
            target = candidates[idx]
            target.hidden_mode = True
            self._emit_effect_event(
                state,
                name="card_switched_hidden_mode",
                actor_player_id=reg.owner_player_id,
                payload={
                    "source_instance_id": target.instance_id,
                    "source_card_id": target.card_id,
                    "source_zone": "battle",
                    "owner_player_id": opponent_id,
                },
            )
            self._schedule_delayed_mode_switch(
                state,
                owner_player_id=opponent_id,
                target_instance_id=target.instance_id,
                trigger_kind="turn_end",
                trigger_player_id=reg.owner_player_id,
                switch_to_hidden=False,
            )
        self._checkpoint(state, "effect_auto_switch_opponent_battle_hidden_then_reveal_on_turn_end")

    def _handle_auto_switch_self_active_on_turn_end(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "turn_end":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        source = self._find_by_instance(owner, reg.source_zone, reg.source_instance_id)
        if source is None:
            return
        if source.resting:
            source.resting = False
        self._checkpoint(state, "effect_auto_switch_self_active_on_turn_end")

    def _handle_auto_switch_self_to_hidden_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        target = self._find_by_instance(owner, reg.source_zone, reg.source_instance_id)
        if target is None or target.hidden_mode:
            return
        target.hidden_mode = True
        self._emit_effect_event(
            state,
            name="card_switched_hidden_mode",
            actor_player_id=reg.owner_player_id,
            payload={
                "source_instance_id": target.instance_id,
                "source_card_id": target.card_id,
                "source_zone": reg.source_zone,
                "owner_player_id": reg.owner_player_id,
            },
        )
        self._checkpoint(state, "effect_auto_switch_self_to_hidden_on_play")

    def _handle_auto_switch_up_to_n_owner_board_to_revealed_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        raw_colors = str(reg.handler_params.get("allowed_colors", ""))
        allowed_colors = {c.strip() for c in raw_colors.replace("|", ",").replace("/", ",").split(",") if c.strip()}
        raw_traits = str(reg.handler_params.get("required_traits", ""))
        required_traits = {t.strip() for t in raw_traits.replace("|", ",").split(",") if t.strip()}
        raw_characters = str(reg.handler_params.get("required_characters", ""))
        required_characters = {t.strip() for t in raw_characters.replace("|", ",").split(",") if t.strip()}
        required_name_contains = str(reg.handler_params.get("required_name_contains", "")).strip().upper()
        candidates = [
            card
            for card in [*owner.battle_area, *owner.unison_area]
            if card.hidden_mode
            and self._card_matches_effect_filters(
                card,
                allowed_colors=allowed_colors,
                required_traits=required_traits,
                required_characters=required_characters,
                required_name_contains=required_name_contains,
            )
        ]
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0 or not candidates:
            return
        policy = str(reg.handler_params.get("target_policy", "first"))
        indexes = self._choose_effect_target_indexes(state, reg, candidates, max_targets, policy)
        if not indexes:
            return
        for idx in indexes:
            target = candidates[idx]
            target.hidden_mode = False
            self._emit_effect_event(
                state,
                name="card_switched_revealed_mode",
                actor_player_id=reg.owner_player_id,
                payload={
                    "source_instance_id": target.instance_id,
                    "source_card_id": target.card_id,
                    "source_zone": "unison" if target in owner.unison_area else "battle",
                    "owner_player_id": reg.owner_player_id,
                },
            )
        self._checkpoint(state, "effect_auto_switch_owner_board_to_revealed_on_play")

    def _handle_auto_switch_up_to_n_owner_battle_to_hidden_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        raw_colors = str(reg.handler_params.get("allowed_colors", ""))
        allowed_colors = {c.strip() for c in raw_colors.replace("|", ",").replace("/", ",").split(",") if c.strip()}
        raw_traits = str(reg.handler_params.get("required_traits", ""))
        required_traits = {t.strip() for t in raw_traits.replace("|", ",").split(",") if t.strip()}
        raw_characters = str(reg.handler_params.get("required_characters", ""))
        required_characters = {t.strip() for t in raw_characters.replace("|", ",").split(",") if t.strip()}
        required_name_contains = str(reg.handler_params.get("required_name_contains", "")).strip().upper()
        candidates = [
            card
            for card in owner.battle_area
            if not card.hidden_mode
            and self._card_matches_effect_filters(
                card,
                allowed_colors=allowed_colors,
                required_traits=required_traits,
                required_characters=required_characters,
                required_name_contains=required_name_contains,
            )
        ]
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0 or not candidates:
            return
        policy = str(reg.handler_params.get("target_policy", "first"))
        indexes = self._choose_effect_target_indexes(state, reg, candidates, max_targets, policy)
        if not indexes:
            return
        for idx in indexes:
            target = candidates[idx]
            target.hidden_mode = True
            self._emit_effect_event(
                state,
                name="card_switched_hidden_mode",
                actor_player_id=reg.owner_player_id,
                payload={
                    "source_instance_id": target.instance_id,
                    "source_card_id": target.card_id,
                    "source_zone": "battle",
                    "owner_player_id": reg.owner_player_id,
                },
            )
        self._checkpoint(state, "effect_auto_switch_owner_battle_to_hidden_on_play")

    def _handle_auto_switch_up_to_n_any_player_board_to_revealed_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        candidates: list[tuple[int, str, CardInstance]] = []
        for owner_player_id, owner in state.players.items():
            for card in owner.battle_area:
                if card.hidden_mode:
                    candidates.append((owner_player_id, "battle", card))
            for card in owner.unison_area:
                if card.hidden_mode:
                    candidates.append((owner_player_id, "unison", card))
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0 or not candidates:
            return
        raw_cards = [card for _, _, card in candidates]
        policy = str(reg.handler_params.get("target_policy", "first"))
        indexes = self._choose_effect_target_indexes(state, reg, raw_cards, max_targets, policy)
        if not indexes:
            return
        for idx in indexes:
            owner_player_id, zone_name, target = candidates[idx]
            target.hidden_mode = False
            self._emit_effect_event(
                state,
                name="card_switched_revealed_mode",
                actor_player_id=reg.owner_player_id,
                payload={
                    "source_instance_id": target.instance_id,
                    "source_card_id": target.card_id,
                    "source_zone": zone_name,
                    "owner_player_id": owner_player_id,
                },
            )
        self._checkpoint(state, "effect_auto_switch_any_player_board_to_revealed_on_play")

    def _handle_auto_self_gain_power_and_keyword_for_turn_on_switch(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name not in {"card_switched_hidden_mode", "card_switched_revealed_mode"}:
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        source = self._find_by_instance(owner, reg.source_zone, reg.source_instance_id)
        if source is None:
            return
        delta = self._resolve_effect_int_param(state, reg, "power_delta", default=0)
        if delta:
            self._apply_temporary_power_delta(state, card=source, delta=delta, reason="effect_switch_self_buff")
        grant_keyword = str(reg.handler_params.get("grant_keyword", "")).strip()
        if grant_keyword:
            self._append_temporary_keyword(source, grant_keyword, duration="turn")
        self._checkpoint(state, "effect_auto_self_gain_power_and_keyword_for_turn_on_switch")

    def _handle_auto_buff_owner_leader_on_switch_until_opponent_turn_end(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_switched_hidden_mode":
            return
        if bool(reg.handler_params.get("requires_owner_actor", False)) and event.actor_player_id != reg.owner_player_id:
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        delta = self._resolve_effect_int_param(state, reg, "power_delta", default=0)
        if delta:
            self._apply_temporary_power_delta(state, card=owner.leader_area, delta=delta, reason="effect_switch_owner_leader_buff")
        self._checkpoint(state, "effect_auto_buff_owner_leader_on_switch_until_opponent_turn_end")

    def _handle_auto_buff_up_to_n_owner_cards_on_switch(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name not in {"card_switched_hidden_mode", "card_switched_revealed_mode"}:
            return
        if bool(reg.handler_params.get("requires_owner_actor", False)) and event.actor_player_id != reg.owner_player_id:
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        raw_colors = str(reg.handler_params.get("allowed_colors", ""))
        allowed_colors = {c.strip() for c in raw_colors.replace("|", ",").replace("/", ",").split(",") if c.strip()}
        raw_traits = str(reg.handler_params.get("required_traits", ""))
        required_traits = {t.strip() for t in raw_traits.replace("|", ",").split(",") if t.strip()}
        raw_characters = str(reg.handler_params.get("required_characters", ""))
        required_characters = {t.strip() for t in raw_characters.replace("|", ",").split(",") if t.strip()}
        required_name_contains = str(reg.handler_params.get("required_name_contains", "")).strip().upper()
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        candidates = [
            card
            for card in [owner.leader_area, *owner.battle_area, *owner.unison_area]
            if self._card_matches_effect_filters(
                card,
                allowed_colors=allowed_colors,
                required_traits=required_traits,
                required_characters=required_characters,
                required_name_contains=required_name_contains,
            )
        ]
        if not candidates:
            return
        policy = str(reg.handler_params.get("target_policy", "first"))
        indexes = self._choose_effect_target_indexes(state, reg, candidates, max_targets, policy)
        if not indexes:
            return
        delta = self._resolve_effect_int_param(state, reg, "power_delta", default=0)
        grant_keyword = str(reg.handler_params.get("grant_keyword", "")).strip()
        keyword_duration = str(reg.handler_params.get("keyword_duration", "turn")).strip().lower()
        for idx in indexes:
            target = candidates[idx]
            if delta:
                self._apply_temporary_power_delta(state, card=target, delta=delta, reason="effect_switch_owner_target_buff")
            if grant_keyword:
                if keyword_duration == "opponent_turn":
                    self._append_temporary_keyword(target, grant_keyword, duration="delayed")
                    state.delayed_keyword_clears.append(
                        DelayedKeywordClear(
                            owner_player_id=reg.owner_player_id,
                            target_instance_id=target.instance_id,
                            trigger_player_id=self._opponent_of(reg.owner_player_id),
                            keyword=grant_keyword,
                        )
                    )
                else:
                    self._append_temporary_keyword(target, grant_keyword, duration="turn")
        self._checkpoint(state, "effect_auto_buff_up_to_n_owner_cards_on_switch")

    def _handle_auto_ko_up_to_n_opponent_battle_on_switch(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name not in {"card_switched_hidden_mode", "card_switched_revealed_mode"}:
            return
        if not self._effect_requirements_met(state, reg):
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        target_policy = str(reg.handler_params.get("target_policy", "first"))
        selected = self._select_opponent_battle_targets(
            state,
            reg,
            max_targets=max_targets,
            max_cost=-1,
            policy=target_policy,
        )
        if not selected:
            return
        opponent_id = self._opponent_of(reg.owner_player_id)
        for target in selected:
            self._ko_card(state, opponent_id, "battle", target.instance_id)
        self._checkpoint(state, "effect_auto_ko_up_to_n_opponent_battle_on_switch")

    def _handle_auto_buff_up_to_n_owner_cards_on_hidden_drop(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_placed_into_drop":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        raw_colors = str(reg.handler_params.get("allowed_colors", ""))
        allowed_colors = {c.strip() for c in raw_colors.replace("|", ",").replace("/", ",").split(",") if c.strip()}
        raw_traits = str(reg.handler_params.get("required_traits", ""))
        required_traits = {t.strip() for t in raw_traits.replace("|", ",").split(",") if t.strip()}
        raw_characters = str(reg.handler_params.get("required_characters", ""))
        required_characters = {t.strip() for t in raw_characters.replace("|", ",").split(",") if t.strip()}
        required_name_contains = str(reg.handler_params.get("required_name_contains", "")).strip().upper()
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        power_delta = self._resolve_effect_int_param(state, reg, "power_delta", default=0)
        if max_targets <= 0 or power_delta == 0:
            return
        candidates = [
            card
            for card in [owner.leader_area, *owner.battle_area, *owner.unison_area]
            if self._card_matches_effect_filters(
                card,
                allowed_colors=allowed_colors,
                required_traits=required_traits,
                required_characters=required_characters,
                required_name_contains=required_name_contains,
            )
        ]
        if not candidates:
            return
        policy = str(reg.handler_params.get("target_policy", "first"))
        indexes = self._choose_effect_target_indexes(state, reg, candidates, max_targets, policy)
        if not indexes:
            return
        for idx in indexes:
            self._apply_temporary_power_delta(state, card=candidates[idx], delta=power_delta, reason="effect_hidden_drop_owner_target_buff")
        self._checkpoint(state, "effect_auto_buff_up_to_n_owner_cards_on_hidden_drop")

    def _handle_auto_switch_up_to_n_owner_energy_active_on_turn_end(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "turn_end":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        raw_colors = str(reg.handler_params.get("allowed_colors", "")).strip().lower()
        allowed_colors = {c.strip() for c in raw_colors.replace("/", ",").replace("|", ",").split(",") if c.strip()}
        requires_multicolor = bool(reg.handler_params.get("requires_multicolor", False))
        candidates = [c for c in owner.energy if c.resting]
        if allowed_colors:
            filtered: list[CardInstance] = []
            for c in candidates:
                colors = {p.strip().lower() for p in str(c.color or "").replace("/", ",").split(",") if p.strip()}
                if colors and colors.isdisjoint(allowed_colors):
                    continue
                filtered.append(c)
            candidates = filtered
        if requires_multicolor:
            candidates = [c for c in candidates if "/" in str(c.color or "")]
        if not candidates:
            return
        for c in candidates[:max_targets]:
            c.resting = False
        self._checkpoint(state, "effect_auto_switch_up_to_n_owner_energy_active_on_turn_end")

    def _handle_auto_switch_up_to_n_owner_energy_active_on_field_extra_placed(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "field_extra_placed":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        raw_colors = str(reg.handler_params.get("allowed_colors", "")).strip().lower()
        allowed_colors = {c.strip() for c in raw_colors.replace("/", ",").replace("|", ",").split(",") if c.strip()}
        requires_multicolor = bool(reg.handler_params.get("requires_multicolor", False))
        candidates = [c for c in owner.energy if c.resting]
        if allowed_colors:
            filtered: list[CardInstance] = []
            for c in candidates:
                colors = {p.strip().lower() for p in str(c.color or "").replace("/", ",").split(",") if p.strip()}
                if colors and colors.isdisjoint(allowed_colors):
                    continue
                filtered.append(c)
            candidates = filtered
        if requires_multicolor:
            candidates = [c for c in candidates if "/" in str(c.color or "")]
        if not candidates:
            return
        for c in candidates[:max_targets]:
            c.resting = False
        self._checkpoint(state, "effect_auto_switch_up_to_n_owner_energy_active_on_field_extra_placed")

    def _handle_auto_rest_self_on_owner_opponent_skill_play_overcost_battle_reduce_power(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        actor_id = event.actor_player_id
        if actor_id in {None, reg.owner_player_id}:
            return
        if str(event.payload.get("source_zone") or "") != "battle":
            return
        played_from = str(event.payload.get("played_from") or "").strip().lower()
        if played_from in {"", "hand"}:
            return
        owner = state.players.get(reg.owner_player_id)
        opponent = state.players.get(actor_id)
        if owner is None or opponent is None:
            return
        source = self._find_by_instance(owner, reg.source_zone, reg.source_instance_id)
        if source is None or source.resting:
            return
        target_instance = int(event.payload.get("source_instance_id") or -1)
        target = self._find_by_instance(opponent, "battle", target_instance)
        if target is None:
            return
        target_cost = target.energy_cost
        if target_cost is None:
            target_cost = self._resolve_card_runtime_data(target.card_id).energy_cost
        if int(target_cost or 0) <= len(opponent.energy):
            return
        source.resting = True
        delta = self._resolve_effect_int_param(state, reg, "power_delta", default=-10000)
        if delta == 0:
            return
        self._modify_card_power(state, card=target, delta=delta, reason="effect_power_reduce")
        self._run_confirmative_rule_processing(state)
        self._checkpoint(state, "effect_auto_rest_self_on_owner_opponent_skill_play_overcost_battle_reduce_power")

    def _handle_auto_rest_self_on_owner_opponent_skill_play_overcost_battle_switch_target_rest(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        actor_id = event.actor_player_id
        if actor_id in {None, reg.owner_player_id}:
            return
        if str(event.payload.get("source_zone") or "") != "battle":
            return
        played_from = str(event.payload.get("played_from") or "").strip().lower()
        if played_from in {"", "hand"}:
            return
        owner = state.players.get(reg.owner_player_id)
        opponent = state.players.get(actor_id)
        if owner is None or opponent is None:
            return
        source = self._find_by_instance(owner, reg.source_zone, reg.source_instance_id)
        if source is None or source.resting:
            return
        target_instance = int(event.payload.get("source_instance_id") or -1)
        target = self._find_by_instance(opponent, "battle", target_instance)
        if target is None:
            return
        target_cost = target.energy_cost
        if target_cost is None:
            target_cost = self._resolve_card_runtime_data(target.card_id).energy_cost
        if int(target_cost or 0) <= len(opponent.energy):
            return
        source.resting = True
        target.resting = True
        self._checkpoint(state, "effect_auto_rest_self_on_owner_opponent_skill_play_overcost_battle_switch_target_rest")

    def _handle_auto_play_up_to_n_from_owner_deck_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        required_from = str(reg.handler_params.get("requires_played_from", "")).strip().lower()
        if required_from:
            played_from = str(event.payload.get("played_from") or "").strip().lower()
            if played_from != required_from:
                return
        owner = state.players.get(reg.owner_player_id)
        if owner is None or not owner.deck:
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        max_power = self._resolve_effect_int_param(state, reg, "max_power", default=-1)
        raw_colors = str(reg.handler_params.get("allowed_colors", "")).strip().lower()
        allowed_colors = {c.strip() for c in raw_colors.replace("|", ",").replace("/", ",").split(",") if c.strip()}
        rest_mode = bool(reg.handler_params.get("rest_mode", False))
        chosen_indexes: list[int] = []
        for i, card_id in enumerate(owner.deck):
            runtime = self._resolve_card_runtime_data(card_id)
            if "BATTLE" not in (runtime.card_type or "").upper():
                continue
            if max_power >= 0 and runtime.power > max_power:
                continue
            if allowed_colors:
                card_colors = {p.strip().lower() for p in str(runtime.color or "").replace("/", ",").split(",") if p.strip()}
                if card_colors and card_colors.isdisjoint(allowed_colors):
                    continue
            chosen_indexes.append(i)
            if len(chosen_indexes) >= max_targets:
                break
        if not chosen_indexes:
            return
        removed = 0
        for idx in chosen_indexes:
            card_id = owner.deck.pop(idx - removed)
            removed += 1
            card = self._create_card_instance(next_instance_id=state.next_instance_id, card_id=card_id, owner_id=reg.owner_player_id)
            state.next_instance_id += 1
            card.resting = rest_mode
            owner.battle_area.append(card)
            self._register_card_effects(state, player_id=reg.owner_player_id, source_zone="battle", card=card)
            self._emit_effect_event(
                state,
                name="card_played",
                actor_player_id=reg.owner_player_id,
                payload={
                    "source_instance_id": card.instance_id,
                    "source_card_id": card.card_id,
                    "source_zone": "battle",
                    "played_from": "deck",
                },
            )
        self._checkpoint(state, "effect_auto_play_up_to_n_from_owner_deck_on_play")

    def _handle_auto_play_up_to_n_from_owner_hand_on_self_combo(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_comboed":
            return
        if not self._effect_requirements_met(state, reg):
            return
        owner = state.players.get(reg.owner_player_id)
        if owner is None or not owner.hand:
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        max_cost = self._resolve_effect_int_param(state, reg, "max_cost", default=-1)
        raw_colors = str(reg.handler_params.get("allowed_colors", "")).strip().lower()
        allowed_colors = {c.strip() for c in raw_colors.replace("|", ",").replace("/", ",").split(",") if c.strip()}
        rest_mode = bool(reg.handler_params.get("rest_mode", False))
        chosen_indexes: list[int] = []
        for i, c in enumerate(owner.hand):
            if "BATTLE" not in (c.card_type or "").upper():
                continue
            if max_cost >= 0 and (c.energy_cost is None or c.energy_cost > max_cost):
                continue
            if allowed_colors:
                colors = {p.strip().lower() for p in str(c.color or "").replace("/", ",").split(",") if p.strip()}
                if colors and colors.isdisjoint(allowed_colors):
                    continue
            chosen_indexes.append(i)
            if len(chosen_indexes) >= max_targets:
                break
        if not chosen_indexes:
            return
        removed = 0
        for idx in chosen_indexes:
            card = owner.hand.pop(idx - removed)
            removed += 1
            card.resting = rest_mode
            owner.battle_area.append(card)
            self._register_card_effects(state, player_id=reg.owner_player_id, source_zone="battle", card=card)
            self._emit_effect_event(
                state,
                name="card_played",
                actor_player_id=reg.owner_player_id,
                payload={
                    "source_instance_id": card.instance_id,
                    "source_card_id": card.card_id,
                    "source_zone": "battle",
                    "played_from": "hand",
                },
            )
        self._checkpoint(state, "effect_auto_play_up_to_n_from_owner_hand_on_self_combo")

    def _handle_auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        required_from = str(reg.handler_params.get("requires_played_from", "")).strip().lower()
        if required_from:
            played_from = str(event.payload.get("played_from") or "").strip().lower()
            if played_from != required_from:
                return
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        markers = self._resolve_effect_int_param(state, reg, "markers", default=1)
        if markers < 0:
            markers = 0
        max_cost = self._resolve_effect_int_param(state, reg, "max_cost", default=-1)
        raw_colors = str(reg.handler_params.get("allowed_colors", "")).strip().lower()
        allowed_colors = {c.strip() for c in raw_colors.replace("|", ",").replace("/", ",").split(",") if c.strip()}
        required_type = str(reg.handler_params.get("required_card_type", "")).strip().upper()
        rest_mode = bool(reg.handler_params.get("rest_mode", False))
        source_pool = str(reg.handler_params.get("source_pool", "hand")).strip().lower()
        remaining = max_targets

        def _matches_runtime(runtime_card_type: str | None, runtime_color: str | None, runtime_cost: int | None) -> bool:
            if required_type and required_type not in (runtime_card_type or "").upper():
                return False
            if max_cost >= 0 and (runtime_cost is None or runtime_cost > max_cost):
                return False
            if allowed_colors:
                colors = {p.strip().lower() for p in str(runtime_color or "").replace("/", ",").split(",") if p.strip()}
                if colors and colors.isdisjoint(allowed_colors):
                    return False
            return True

        # Deterministic resolution: hand first, then deck when configured.
        pools: list[str] = []
        if source_pool in {"hand", "hand_or_deck"}:
            pools.append("hand")
        if source_pool in {"deck", "hand_or_deck"}:
            pools.append("deck")
        for pool in pools:
            while remaining > 0:
                card: CardInstance | None = None
                played_from = pool
                if pool == "hand":
                    chosen_index: int | None = None
                    for i, hand_card in enumerate(owner.hand):
                        if _matches_runtime(hand_card.card_type, hand_card.color, hand_card.energy_cost):
                            chosen_index = i
                            break
                    if chosen_index is None:
                        break
                    card = owner.hand.pop(chosen_index)
                else:
                    chosen_index = -1
                    for i, card_id in enumerate(owner.deck):
                        runtime = self._resolve_card_runtime_data(card_id)
                        if _matches_runtime(runtime.card_type, runtime.color, runtime.energy_cost):
                            chosen_index = i
                            break
                    if chosen_index < 0:
                        break
                    card_id = owner.deck.pop(chosen_index)
                    card = self._create_card_instance(next_instance_id=state.next_instance_id, card_id=card_id, owner_id=reg.owner_player_id)
                    state.next_instance_id += 1
                card.markers = markers
                card.resting = rest_mode
                target_zone = "battle"
                if "UNISON" in (card.card_type or "").upper():
                    target_zone = "unison"
                    self._replace_owner_unison_if_needed(state, owner)
                    owner.unison_area.append(card)
                else:
                    owner.battle_area.append(card)
                self._register_card_effects(state, player_id=reg.owner_player_id, source_zone=target_zone, card=card)
                self._emit_effect_event(
                    state,
                    name="card_played",
                    actor_player_id=reg.owner_player_id,
                    payload={
                        "source_instance_id": card.instance_id,
                        "source_card_id": card.card_id,
                        "source_zone": target_zone,
                        "played_from": played_from,
                    },
                )
                remaining -= 1
        if remaining < max_targets:
            self._checkpoint(state, "effect_auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play")

    def _handle_auto_ko_opponent_battle_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        max_cost = self._resolve_effect_int_param(state, reg, "max_cost", default=-1)
        target_policy = str(reg.handler_params.get("target_policy", "first"))
        selected = self._select_opponent_battle_targets(
            state,
            reg,
            max_targets=1,
            max_cost=max_cost,
            policy=target_policy,
        )
        if not selected:
            return
        opponent_id = self._opponent_of(reg.owner_player_id)
        self._ko_card(state, opponent_id, "battle", selected[0].instance_id)
        self._checkpoint(state, "effect_auto_ko_on_play")

    def _handle_auto_ko_up_to_n_opponent_battle_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        max_cost = self._resolve_effect_int_param(state, reg, "max_cost", default=-1)
        target_policy = str(reg.handler_params.get("target_policy", "first"))
        selected = self._select_opponent_battle_targets(
            state,
            reg,
            max_targets=max_targets,
            max_cost=max_cost,
            policy=target_policy,
        )
        if not selected:
            return
        opponent_id = self._opponent_of(reg.owner_player_id)
        target_ids = {c.instance_id for c in selected}
        for tid in list(target_ids):
            self._ko_card(state, opponent_id, "battle", tid)
        self._checkpoint(state, "effect_auto_ko_up_to_n_on_play")

    def _handle_auto_power_reduce_up_to_n_on_play(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "card_played":
            return
        if not self._effect_requirements_met(state, reg):
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        max_cost = self._resolve_effect_int_param(state, reg, "max_cost", default=-1)
        target_policy = str(reg.handler_params.get("target_policy", "first"))
        delta = self._resolve_effect_int_param(state, reg, "power_delta", default=-5000)
        if delta == 0:
            return
        selected = self._select_opponent_battle_targets(
            state,
            reg,
            max_targets=max_targets,
            max_cost=max_cost,
            policy=target_policy,
        )
        if not selected:
            return
        for target in selected:
            self._modify_card_power(state, card=target, delta=delta, reason="effect_power_reduce")
        self._run_confirmative_rule_processing(state)
        self._checkpoint(state, "effect_auto_power_reduce_up_to_n_on_play")

    def _handle_auto_power_reduce_up_to_n_on_attack(self, state: GameState, event: EffectEvent, reg: EffectRegistration) -> None:
        if event.name != "attack_declared":
            return
        if not self._effect_requirements_met(state, reg):
            return
        max_targets = self._resolve_effect_int_param(state, reg, "max_targets", default=1)
        if max_targets <= 0:
            return
        max_cost = self._resolve_effect_int_param(state, reg, "max_cost", default=-1)
        target_policy = str(reg.handler_params.get("target_policy", "first"))
        delta = self._resolve_effect_int_param(state, reg, "power_delta", default=-5000)
        if delta == 0:
            return
        selected = self._select_opponent_battle_targets(
            state,
            reg,
            max_targets=max_targets,
            max_cost=max_cost,
            policy=target_policy,
        )
        if not selected:
            return
        for target in selected:
            self._modify_card_power(state, card=target, delta=delta, reason="effect_power_reduce")
        self._run_confirmative_rule_processing(state)
        self._checkpoint(state, "effect_auto_power_reduce_up_to_n_on_attack")

    def _select_opponent_battle_targets(
        self,
        state: GameState,
        reg: EffectRegistration,
        *,
        max_targets: int,
        max_cost: int,
        policy: str,
    ) -> list[CardInstance]:
        if max_targets <= 0:
            return []
        opponent_id = self._opponent_of(reg.owner_player_id)
        candidates = list(state.players[opponent_id].battle_area)
        if max_cost >= 0:
            candidates = [c for c in candidates if (c.energy_cost or 0) <= max_cost]
        if bool(reg.handler_params.get("rest_mode_only", False)):
            candidates = [c for c in candidates if c.resting]
        if not bool(reg.handler_params.get("ignores_barrier", False)):
            candidates = [c for c in candidates if not c.has_barrier]
        if not candidates:
            return []
        indexes = self._choose_effect_target_indexes(state, reg, candidates, max_targets, policy)
        return [candidates[i] for i in indexes]

    def _effect_requirements_met(self, state: GameState, reg: EffectRegistration) -> bool:
        raw_req = reg.handler_params.get("requires_leader")
        leader_ok = True
        owner = state.players[reg.owner_player_id]
        leader = owner.leader_area
        leader_runtime = self._resolve_card_runtime_data(leader.card_id)
        if isinstance(raw_req, str) and raw_req.strip():
            req = raw_req.lower()
            leader_color = (leader.color or "").lower()
            if "red" in req and leader_color != "red":
                leader_ok = False
            if "blue" in req and leader_color != "blue":
                leader_ok = False
            if "green" in req and leader_color != "green":
                leader_ok = False
            if "yellow" in req and leader_color != "yellow":
                leader_ok = False
            if "black" in req and leader_color != "black":
                leader_ok = False
        if not leader_ok:
            return False
        required_leader_traits_raw = str(reg.handler_params.get("required_leader_traits", "")).strip().lower()
        if required_leader_traits_raw:
            required_leader_traits = {
                part.strip()
                for part in required_leader_traits_raw.replace("|", ",").split(",")
                if part.strip()
            }
            leader_traits = {part.strip().lower() for part in (leader_runtime.traits or ()) if part.strip()}
            if leader_traits.isdisjoint(required_leader_traits):
                return False
        min_owner_energy = self._resolve_effect_int_param(state, reg, "min_owner_energy", default=-1)
        if min_owner_energy >= 0 and len(owner.energy) < min_owner_energy:
            return False
        min_owner_hidden_mode_battle = self._resolve_effect_int_param(state, reg, "min_owner_hidden_mode_battle", default=-1)
        if min_owner_hidden_mode_battle >= 0:
            hidden_count = sum(1 for card in owner.battle_area if card.hidden_mode)
            if hidden_count < min_owner_hidden_mode_battle:
                return False
        if bool(reg.handler_params.get("requires_no_owner_battle", False)) and owner.battle_area:
            return False
        opponent = state.players.get(self._opponent_of(reg.owner_player_id))
        if bool(reg.handler_params.get("requires_no_opponent_battle", False)) and opponent is not None and opponent.battle_area:
            return False
        owner_battle_only_matching = bool(reg.handler_params.get("required_owner_battle_only_matching", False))
        owner_battle_allowed_colors = {
            part.strip()
            for part in str(reg.handler_params.get("required_owner_battle_allowed_colors", "")).strip().lower().replace("|", ",").split(",")
            if part.strip()
        }
        owner_battle_required_traits = {
            part.strip()
            for part in str(reg.handler_params.get("required_owner_battle_required_traits", "")).strip().lower().replace("|", ",").split(",")
            if part.strip()
        }
        owner_battle_required_characters = {
            part.strip()
            for part in str(reg.handler_params.get("required_owner_battle_required_characters", "")).strip().lower().replace("|", ",").split(",")
            if part.strip()
        }
        owner_battle_required_name_contains = str(reg.handler_params.get("required_owner_battle_required_name_contains", "")).strip().upper()
        if (
            owner_battle_only_matching
            or owner_battle_allowed_colors
            or owner_battle_required_traits
            or owner_battle_required_characters
            or owner_battle_required_name_contains
        ):
            if not owner.battle_area:
                return False
            for card in owner.battle_area:
                matches = self._card_matches_effect_filters(
                    card,
                    allowed_colors=owner_battle_allowed_colors,
                    required_traits=owner_battle_required_traits,
                    required_characters=owner_battle_required_characters,
                    required_name_contains=owner_battle_required_name_contains,
                )
                if owner_battle_only_matching and not matches:
                    return False
                if not owner_battle_only_matching and matches:
                    break
            else:
                return False
        mono = reg.handler_params.get("requires_mono_energy")
        if isinstance(mono, str) and mono.strip():
            required = mono.strip().lower()
            for e in owner.energy:
                color = (e.color or "").strip().lower()
                if color and color != required:
                    return False
        if bool(reg.handler_params.get("requires_owner_turn", False)) and state.active_player != reg.owner_player_id:
            return False
        if bool(reg.handler_params.get("requires_opponent_turn", False)) and state.active_player == reg.owner_player_id:
            return False
        return True

    def _activate_effect_requirements_met(
        self,
        state: GameState,
        *,
        player_id: int,
        source: CardInstance,
        source_zone: str,
        source_kind: str,
    ) -> bool:
        trigger = f"self_activate_{source_kind}"
        rules = [rule for rule in self._effect_rules.get(source.card_id, ()) if rule.trigger == trigger]
        if not rules:
            return True
        for rule in rules:
            reg = EffectRegistration(
                effect_id=0,
                owner_player_id=player_id,
                source_instance_id=source.instance_id,
                source_card_id=source.card_id,
                source_zone=source_zone,
                trigger=rule.trigger,
                handler_id=rule.handler_id,
                handler_params=dict(rule.handler_params),
                source_card_number=str(source.card_number or ""),
                once_per_turn=rule.once_per_turn,
                limit_per_turn=rule.limit_per_turn,
                limit_scope=rule.limit_scope,
            )
            if self._effect_requirements_met(state, reg):
                return True
        return False

    def _effective_hand_energy_cost(self, state: GameState, *, player_id: int, card: CardInstance) -> int:
        base_cost = int(card.energy_cost or 0)
        reduction = self._hand_cost_reduction_amount(state, player_id=player_id, card=card)
        return max(base_cost - reduction, 0)

    def _can_pay_alternate_counter_hand_cost(self, state: GameState, player: PlayerState, card: CardInstance) -> bool:
        spec = self._resolve_skill_cost_spec(card.card_id, "counter_alternate_from_hand")
        if spec is not None:
            try:
                return SkillCostDsl.can_pay(player, card, spec, opponent=state.players[self._opponent_of(player.player_id)])
            except Exception:
                return False
        text = str(card.skill_text_raw or "")
        if not text:
            return False
        leader_runtime = self._resolve_card_runtime_data(player.leader_area.card_id)
        if self._text_counter_can_rest_hidden_mode_battle_instead_of_energy_cost(card):
            if not self._text_hand_cost_reduction_requirements_met(text, owner=player, leader=player.leader_area, leader_runtime=leader_runtime):
                return False
            return any(target.hidden_mode and not target.resting for target in player.battle_area)
        if self._text_counter_can_add_life_to_hand_instead_of_energy_cost(card):
            sparking_threshold = self._parse_sparking_threshold(text) or getattr(card, "sparking_threshold", None)
            if sparking_threshold is not None and len(player.drop) < int(sparking_threshold):
                return False
            return bool(player.life)
        return False

    def _pay_alternate_counter_hand_cost(self, state: GameState, player: PlayerState, card: CardInstance) -> bool:
        spec = self._resolve_skill_cost_spec(card.card_id, "counter_alternate_from_hand")
        if spec is not None:
            try:
                metadata = SkillCostDsl.pay(player, card, spec, opponent=state.players[self._opponent_of(player.player_id)])
            except Exception:
                return False
            alt_kind = str(metadata.get("alternate_cost_kind") or "")
            if alt_kind == "rest_owner_hidden_mode_battle":
                self._checkpoint(state, "counter_alternate_cost_hidden_battle_rested")
            elif alt_kind == "add_life_to_hand":
                self._checkpoint(state, "counter_alternate_cost_life_to_hand")
            return True
        text = str(card.skill_text_raw or "")
        if self._text_counter_can_rest_hidden_mode_battle_instead_of_energy_cost(card):
            leader_runtime = self._resolve_card_runtime_data(player.leader_area.card_id)
            if not self._text_hand_cost_reduction_requirements_met(text, owner=player, leader=player.leader_area, leader_runtime=leader_runtime):
                return False
            target = next((battle for battle in player.battle_area if battle.hidden_mode and not battle.resting), None)
            if target is None:
                return False
            target.resting = True
            self._checkpoint(state, "counter_alternate_cost_hidden_battle_rested")
            return True
        if self._text_counter_can_add_life_to_hand_instead_of_energy_cost(card):
            sparking_threshold = self._parse_sparking_threshold(text) or getattr(card, "sparking_threshold", None)
            if sparking_threshold is not None and len(player.drop) < int(sparking_threshold):
                return False
            if not player.life:
                return False
            chosen_index = self._choose_life_card_index(player, 0)
            player.hand.append(player.life.pop(chosen_index))
            self._checkpoint(state, "counter_alternate_cost_life_to_hand")
            return True
        return False

    def _hand_cost_reduction_amount(self, state: GameState, *, player_id: int, card: CardInstance) -> int:
        text = str(card.skill_text_raw or "")
        if not text:
            return 0
        reduction = self._parse_hand_cost_reduction_amount(text)
        if reduction <= 0:
            return 0
        owner = state.players[player_id]
        leader = owner.leader_area
        leader_runtime = self._resolve_card_runtime_data(leader.card_id)
        if not self._text_hand_cost_reduction_requirements_met(text, owner=owner, leader=leader, leader_runtime=leader_runtime):
            return 0
        return reduction

    @staticmethod
    def _parse_hand_cost_reduction_amount(skill_text: object) -> int:
        text = str(skill_text or "").lower()
        match = re.search(r"reduce the energy cost of this card in your hand by (\d+)", text)
        if match is None:
            return 0
        try:
            return int(match.group(1))
        except ValueError:
            return 0

    def _text_hand_cost_reduction_requirements_met(
        self,
        skill_text: object,
        *,
        owner: PlayerState,
        leader: CardInstance,
        leader_runtime: CardRuntimeData,
    ) -> bool:
        text = str(skill_text or "").lower()
        leader_color = (leader.color or "").strip().lower()
        if "if your leader is a white" in text and leader_color != "white":
            return False
        if "if your leader is a red" in text and leader_color != "red":
            return False
        if "if your leader is a blue" in text and leader_color != "blue":
            return False
        if "if your leader is a green" in text and leader_color != "green":
            return False
        if "if your leader is a yellow" in text and leader_color != "yellow":
            return False
        if "if your leader is a black" in text and leader_color != "black":
            return False
        required_traits = {
            part.strip().lower()
            for part in re.findall(r"≪([^≫]+)≫", text)
            if part.strip()
        }
        if required_traits:
            leader_traits = {part.strip().lower() for part in (leader_runtime.traits or ()) if part.strip()}
            if leader_traits.isdisjoint(required_traits):
                return False
        hidden_threshold = self._parse_hidden_mode_awaken_threshold(text)
        if hidden_threshold is not None:
            hidden_count = sum(1 for board_card in owner.battle_area if board_card.hidden_mode)
            if hidden_count < hidden_threshold:
                return False
        elif "you have a hidden mode card in your battle area" in text:
            if not any(board_card.hidden_mode for board_card in owner.battle_area):
                return False
        return True

    def _card_matches_effect_filters(
        self,
        card: CardInstance,
        *,
        allowed_colors: set[str],
        required_traits: set[str],
        required_characters: set[str],
        required_name_contains: str,
    ) -> bool:
        runtime = self._resolve_card_runtime_data(card.card_id)
        normalized_allowed_colors = {part.strip().lower() for part in allowed_colors if part.strip()}
        normalized_required_traits = {part.strip().lower() for part in required_traits if part.strip()}
        normalized_required_characters = {part.strip().lower() for part in required_characters if part.strip()}
        runtime_colors = {
            part.strip().lower()
            for part in str(runtime.color or "").replace("/", ",").split(",")
            if part.strip()
        }
        if not runtime_colors and card.color:
            runtime_colors = {
                part.strip().lower()
                for part in str(card.color).replace("/", ",").split(",")
                if part.strip()
            }
        runtime_traits = {part.strip().lower() for part in (runtime.traits or ()) if part.strip()}
        runtime_characters = {part.strip().lower() for part in (runtime.characters or ()) if part.strip()}
        runtime_name = str(runtime.card_name or "").upper()
        if normalized_allowed_colors and runtime_colors.isdisjoint(normalized_allowed_colors):
            return False
        if normalized_required_traits and runtime_traits.isdisjoint(normalized_required_traits):
            return False
        if normalized_required_characters and runtime_characters.isdisjoint(normalized_required_characters):
            return False
        if required_name_contains and required_name_contains not in runtime_name:
            return False
        return True

    def _resolve_effect_int_param(self, state: GameState, reg: EffectRegistration, key: str, *, default: int) -> int:
        raw = reg.handler_params.get(key, default)
        if isinstance(raw, bool):
            return int(raw)
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str):
            txt = raw.strip().lower()
            if txt.lstrip("-").isdigit():
                return int(txt)
            if txt.startswith("expr:"):
                return self._eval_effect_int_expr(state, reg, txt[5:].strip(), default=default)
            return self._eval_effect_int_expr(state, reg, txt, default=default)
        return default

    def _eval_effect_int_expr(self, state: GameState, reg: EffectRegistration, expr: str, *, default: int) -> int:
        owner = state.players.get(reg.owner_player_id)
        if owner is None:
            return default
        opponent = state.players.get(self._opponent_of(reg.owner_player_id))
        source = self._find_by_instance(owner, reg.source_zone, reg.source_instance_id)
        values: dict[str, int] = {
            "owner_energy_count": len(owner.energy),
            "owner_drop_count": len(owner.drop),
            "owner_life_count": len(owner.life),
            "owner_battle_count": len(owner.battle_area),
            "owner_unison_count": len(owner.unison_area),
            "owner_energy_markers": int(owner.energy_markers),
            "owner_unison_markers_total": sum(max(c.markers, 0) for c in owner.unison_area),
            "opponent_battle_count": len(opponent.battle_area) if opponent is not None else 0,
            "opponent_unison_count": len(opponent.unison_area) if opponent is not None else 0,
            "source_markers": int(source.markers) if source is not None else 0,
            "source_power": int(source.power) if source is not None else 0,
            "x": int(source.markers) if source is not None else 0,
        }
        return int(values.get(expr, default))

    def _choose_effect_target_index(
        self,
        state: GameState,
        reg: EffectRegistration,
        candidates: list[CardInstance],
        policy: str,
    ) -> int:
        if not candidates:
            return 0
        if self._effect_target_chooser is not None:
            try:
                selected = int(self._effect_target_chooser(state, reg, candidates, policy))
                if selected < 0:
                    return 0
                if selected >= len(candidates):
                    return len(candidates) - 1
                return selected
            except Exception:
                pass
        if policy == "lowest_power":
            min_idx = 0
            min_key = (candidates[0].power, candidates[0].instance_id)
            for i, c in enumerate(candidates[1:], start=1):
                key = (c.power, c.instance_id)
                if key < min_key:
                    min_key = key
                    min_idx = i
            return min_idx
        return 0

    def _choose_effect_target_indexes(
        self,
        state: GameState,
        reg: EffectRegistration,
        candidates: list[CardInstance],
        count: int,
        policy: str,
    ) -> list[int]:
        if not candidates or count <= 0:
            return []
        limit = min(count, len(candidates))
        if self._effect_multi_target_chooser is not None:
            try:
                raw = self._effect_multi_target_chooser(state, reg, candidates, limit, policy)
                chosen: list[int] = []
                for value in list(raw):
                    idx = int(value)
                    if idx < 0:
                        idx = 0
                    if idx >= len(candidates):
                        idx = len(candidates) - 1
                    if idx not in chosen:
                        chosen.append(idx)
                    if len(chosen) >= limit:
                        break
                if chosen:
                    return chosen
            except Exception:
                pass
        if limit == 1:
            return [self._choose_effect_target_index(state, reg, candidates, policy)]

        if policy == "lowest_power":
            ordered = sorted(range(len(candidates)), key=lambda i: (candidates[i].power, candidates[i].instance_id))
            return ordered[:limit]
        return list(range(limit))

    @staticmethod
    def _is_effect_source_active(state: GameState, reg: EffectRegistration) -> bool:
        player = state.players.get(reg.owner_player_id)
        if player is None:
            return False
        if reg.trigger in {"self_koed", "self_hidden_battle_to_drop"}:
            return (
                any(c.instance_id == reg.source_instance_id for c in player.drop)
                or any(c.instance_id == reg.source_instance_id for c in player.removed_from_game)
                or any(c.instance_id == reg.source_instance_id for c in player.battle_area)
                or any(c.instance_id == reg.source_instance_id for c in player.unison_area)
            )
        if reg.source_zone == "leader":
            return player.leader_area.instance_id == reg.source_instance_id
        if reg.source_zone == "battle":
            return any(c.instance_id == reg.source_instance_id for c in player.battle_area)
        if reg.source_zone == "unison":
            return any(c.instance_id == reg.source_instance_id for c in player.unison_area)
        if reg.source_zone == "combo":
            return any(c.instance_id == reg.source_instance_id for c in player.combo_area)
        if reg.source_zone == "hand":
            return any(c.instance_id == reg.source_instance_id for c in player.hand)
        return False

    def _checkpoint(self, state: GameState, name: str) -> None:
        state.checkpoints.append(
            CheckpointEvent(
                index=state.next_checkpoint_index,
                turn_number=state.turn_number,
                phase=state.phase,
                active_player=state.active_player,
                name=name,
            )
        )
        state.next_checkpoint_index += 1

    def _create_card_instance(self, *, next_instance_id: int, card_id: int, owner_id: int) -> CardInstance:
        runtime = self._resolve_card_runtime_data(card_id)
        return CardInstance(
            instance_id=next_instance_id,
            card_id=card_id,
            owner_id=owner_id,
            card_number=runtime.card_number,
            power=runtime.power,
            card_type=runtime.card_type,
            color=runtime.color,
            energy_cost_raw=runtime.energy_cost_raw,
            energy_cost=runtime.energy_cost,
            combo_cost=runtime.combo_cost,
            combo_power=runtime.combo_power,
            keywords=runtime.keywords,
            has_counter=runtime.has_counter,
            counter_modes=runtime.counter_modes,
            has_counter_attack=runtime.has_counter_attack,
            has_counter_battle_card_attack=runtime.has_counter_battle_card_attack,
            has_counter_play=runtime.has_counter_play,
            has_counter_counter=runtime.has_counter_counter,
            has_activate_main=runtime.has_activate_main,
            has_activate_battle=runtime.has_activate_battle,
            has_auto=runtime.has_auto,
            has_permanent=runtime.has_permanent,
            has_draw=runtime.has_draw,
            max_draw=runtime.max_draw,
            auto_once_per_turn=runtime.auto_once_per_turn,
            auto_draw_on_play=runtime.auto_draw_on_play,
            auto_draw_on_attack=runtime.auto_draw_on_attack,
            has_barrier=runtime.has_barrier,
            z_energy_cost=runtime.z_energy_cost,
            specified_costs=runtime.specified_costs,
            skill_text_raw=runtime.skill_text_raw,
            has_awaken=runtime.has_awaken,
            activate_limit_once_per_turn=runtime.activate_limit_once_per_turn,
            has_super_combo=runtime.has_super_combo,
            sparking_threshold=runtime.sparking_threshold,
            traits=runtime.traits,
            characters=runtime.characters,
        )

    def _create_z_deck_card(self, *, card_id: int, owner_id: int) -> ZDeckCard:
        runtime = self._resolve_card_runtime_data(card_id)
        return ZDeckCard(
            card_id=card_id,
            owner_id=owner_id,
            face_up=False,
            card_name=runtime.card_name,
            card_type=runtime.card_type,
            color=runtime.color,
            energy_cost=runtime.energy_cost,
            traits=runtime.traits,
            characters=runtime.characters,
        )

    def _resolve_card_runtime_data(self, card_id: int, *, side: str = "front") -> CardRuntimeData:
        cache_key = (card_id, side)
        if cache_key in self._card_cache:
            return self._card_cache[cache_key]
        runtime = CardRuntimeData()
        if self._card_repository is not None:
            try:
                card = self._card_repository.get_by_id(card_id, source_table="cards")
                runtime = self._build_card_runtime_data(card, side=side)
            except Exception:
                runtime = CardRuntimeData()
        self._card_cache[cache_key] = runtime
        return runtime

    def _apply_leader_back_side(self, leader: CardInstance) -> None:
        runtime = self._resolve_card_runtime_data(leader.card_id, side="back")
        leader.power = runtime.power
        leader.energy_cost_raw = runtime.energy_cost_raw
        leader.energy_cost = runtime.energy_cost
        leader.combo_cost = runtime.combo_cost
        leader.combo_power = runtime.combo_power
        leader.keywords = runtime.keywords
        leader.has_counter = runtime.has_counter
        leader.counter_modes = runtime.counter_modes
        leader.has_counter_attack = runtime.has_counter_attack
        leader.has_counter_battle_card_attack = runtime.has_counter_battle_card_attack
        leader.has_counter_play = runtime.has_counter_play
        leader.has_counter_counter = runtime.has_counter_counter
        leader.has_activate_main = runtime.has_activate_main
        leader.has_activate_battle = runtime.has_activate_battle
        leader.has_auto = runtime.has_auto
        leader.has_permanent = runtime.has_permanent
        leader.has_draw = runtime.has_draw
        leader.max_draw = runtime.max_draw
        leader.auto_once_per_turn = runtime.auto_once_per_turn
        leader.auto_draw_on_play = runtime.auto_draw_on_play
        leader.auto_draw_on_attack = runtime.auto_draw_on_attack
        leader.has_barrier = runtime.has_barrier
        leader.z_energy_cost = runtime.z_energy_cost
        leader.specified_costs = runtime.specified_costs
        leader.skill_text_raw = runtime.skill_text_raw
        leader.has_awaken = False
        leader.activate_limit_once_per_turn = runtime.activate_limit_once_per_turn
        leader.has_super_combo = runtime.has_super_combo
        leader.sparking_threshold = runtime.sparking_threshold
        leader.traits = runtime.traits
        leader.characters = runtime.characters
        leader.awakened = True

    def _build_card_runtime_data(self, card: Any, *, side: str) -> CardRuntimeData:
        is_back = side == "back"
        power_raw = getattr(card, "card_back_power", None) if is_back else getattr(card, "power_int", None)
        skill_text = getattr(card, "card_back_skill_unstyled", None) if is_back else getattr(card, "card_skill_unstyled", None)
        keywords = tuple(getattr(card, "keywords", ()) or ())
        text_counter_modes = self._text_counter_modes(skill_text)
        merged_keywords = tuple(list(keywords) + [mode for mode in text_counter_modes if mode not in keywords])
        traits_raw = getattr(card, "card_back_traits_json", None) if is_back else getattr(card, "card_traits_json", None)
        characters_raw = getattr(card, "card_back_character_json", None) if is_back else getattr(card, "card_character_json", None)
        has_draw_flag = bool(getattr(card, "has_draw", False))
        return CardRuntimeData(
            card_number=str(getattr(card, "card_number", None) or ""),
            card_name=str(getattr(card, "card_name", None) or ""),
            power=int(power_raw) if power_raw is not None else 15000,
            card_type=str(getattr(card, "card_type", None) or "BATTLE"),
            color=getattr(card, "card_color", None),
            energy_cost_raw=getattr(card, "card_energy_cost", None),
            energy_cost=getattr(card, "energy_cost_int", None),
            combo_cost=getattr(card, "combo_cost_int", None),
            combo_power=getattr(card, "combo_power_int", None),
            keywords=merged_keywords,
            has_counter=bool(getattr(card, "has_counter", False)) or self._text_has_counter(skill_text),
            counter_modes=tuple(k for k in merged_keywords if str(k).startswith("Counter:")),
            has_counter_attack=bool(getattr(card, "has_counter_attack", False)) or self._text_has_counter_attack(skill_text),
            has_counter_battle_card_attack=any(str(k) == "Counter: Battle Card Attack" for k in merged_keywords),
            has_counter_play=bool(getattr(card, "has_counter_play", False)) or self._text_has_counter_play(skill_text),
            has_counter_counter=any(str(k) == "Counter: Counter" for k in merged_keywords) or self._text_has_counter_counter(skill_text),
            has_activate_main=bool(getattr(card, "has_activate_main", False)) or self._text_has_activate_main(skill_text),
            has_activate_battle=bool(getattr(card, "has_activate_battle", False)) or self._text_has_activate_battle(skill_text),
            has_auto=bool(getattr(card, "has_auto", False)) or self._text_has_auto(skill_text),
            has_permanent=bool(getattr(card, "has_permanent", False)) or self._text_has_permanent(skill_text),
            has_draw=has_draw_flag or self._text_has_draw(skill_text),
            max_draw=self._parse_optional_int(getattr(card, "max_draw", None)),
            auto_once_per_turn=self._has_once_per_turn(skill_text),
            auto_draw_on_play=self._has_auto_draw_on_play(skill_text, has_draw_flag or self._text_has_draw(skill_text)),
            auto_draw_on_attack=self._has_auto_draw_on_attack(skill_text, has_draw_flag or self._text_has_draw(skill_text)),
            has_barrier=bool(getattr(card, "has_barrier", False)) or self._text_has_barrier(skill_text),
            z_energy_cost=self._parse_optional_int(getattr(card, "z_energy_cost", None)),
            specified_costs=self._parse_specified_costs(getattr(card, "card_energy_cost", None), getattr(card, "card_color", None)),
            skill_text_raw=str(skill_text or "") if skill_text is not None else None,
            has_awaken=("[Awaken]" in str(skill_text or "")) if not is_back else False,
            activate_limit_once_per_turn=("[Limit 1]" in str(skill_text or "")) or self._has_once_per_turn(skill_text),
            has_super_combo=self._text_has_super_combo(skill_text),
            sparking_threshold=self._parse_sparking_threshold(skill_text),
            traits=self._parse_json_string_tuple(traits_raw),
            characters=self._parse_json_string_tuple(characters_raw),
        )

    @staticmethod
    def _parse_optional_int(value: object) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        text = str(value).strip()
        return int(text) if text.isdigit() else None

    @staticmethod
    def _parse_json_string_tuple(value: object) -> tuple[str, ...]:
        if value in (None, ""):
            return ()
        if isinstance(value, (list, tuple)):
            return tuple(str(item) for item in value if str(item).strip())
        try:
            parsed = json.loads(str(value))
        except Exception:
            return ()
        if isinstance(parsed, list):
            return tuple(str(item) for item in parsed if str(item).strip())
        return ()

    @staticmethod
    def _text_has_activate_main(skill_text: object) -> bool:
        text = str(skill_text or "").lower()
        return "[activate: main]" in text or "[activate main]" in text

    @staticmethod
    def _text_has_activate_battle(skill_text: object) -> bool:
        return "[activate: battle]" in str(skill_text or "").lower()

    @staticmethod
    def _parse_hidden_mode_awaken_threshold(skill_text: object) -> int | None:
        text = str(skill_text or "").lower()
        match = re.search(r"you have (\d+) or more hidden mode cards? in your battle area", text)
        if match is None:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _text_has_auto(skill_text: object) -> bool:
        return "[auto]" in str(skill_text or "").lower()

    @staticmethod
    def _text_has_permanent(skill_text: object) -> bool:
        return "[permanent]" in str(skill_text or "").lower()

    @staticmethod
    def _text_has_draw(skill_text: object) -> bool:
        return "draw" in str(skill_text or "").lower()

    @staticmethod
    def _text_has_barrier(skill_text: object) -> bool:
        return "[barrier]" in str(skill_text or "").lower()

    @staticmethod
    def _text_counter_modes(skill_text: object) -> tuple[str, ...]:
        lowered = str(skill_text or "").lower()
        modes: list[str] = []
        if "[counter: attack]" in lowered:
            modes.append("Counter: Attack")
        if "[counter: play]" in lowered:
            modes.append("Counter: Play")
        if "[counter: counter]" in lowered:
            modes.append("Counter: Counter")
        if "[counter: battle card attack]" in lowered:
            modes.append("Counter: Battle Card Attack")
        return tuple(modes)

    @classmethod
    def _text_has_counter(cls, skill_text: object) -> bool:
        return bool(cls._text_counter_modes(skill_text))

    @classmethod
    def _text_has_counter_attack(cls, skill_text: object) -> bool:
        return "Counter: Attack" in cls._text_counter_modes(skill_text)

    @classmethod
    def _text_has_counter_play(cls, skill_text: object) -> bool:
        return "Counter: Play" in cls._text_counter_modes(skill_text)

    @classmethod
    def _text_has_counter_counter(cls, skill_text: object) -> bool:
        return "Counter: Counter" in cls._text_counter_modes(skill_text)

    @staticmethod
    def _text_has_super_combo(skill_text: object) -> bool:
        return "[super combo]" in str(skill_text or "").lower()

    @staticmethod
    def _parse_sparking_threshold(skill_text: object) -> int | None:
        import re

        text = str(skill_text or "")
        match = re.search(r"\[sparking\s+(\d+)\]", text, flags=re.IGNORECASE)
        if not match:
            return None
        try:
            return int(match.group(1))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_specified_costs(raw_cost: object, fallback_color: object) -> tuple[tuple[str, int], ...]:
        if raw_cost is None:
            raw = ""
        else:
            raw = str(raw_cost).strip()
        if raw == "":
            return ()

        txt = raw.upper()
        for word, code in {
            "RED": "R",
            "BLUE": "B",
            "GREEN": "G",
            "YELLOW": "Y",
            "BLACK": "K",
        }.items():
            txt = txt.replace(word, code)

        counts: dict[str, int] = {}
        for ch in txt:
            if ch in {"R", "B", "G", "Y", "K"}:
                counts[ch] = counts.get(ch, 0) + 1

        if not counts and any(c.isdigit() for c in txt):
            return ()

        if not counts and fallback_color:
            code = RulesEngine._color_to_code(str(fallback_color))
            if code:
                counts[code] = 1
        return tuple(sorted(counts.items()))

    @staticmethod
    def _has_auto_draw_on_play(skill_text: object, has_draw_flag: bool) -> bool:
        if not has_draw_flag:
            return False
        text = str(skill_text or "").lower()
        return ("when this card is played" in text) or ("when you play this card" in text)

    @staticmethod
    def _has_once_per_turn(skill_text: object) -> bool:
        text = str(skill_text or "").lower()
        return "[once per turn]" in text or "once per turn" in text

    @staticmethod
    def _has_auto_draw_on_attack(skill_text: object, has_draw_flag: bool) -> bool:
        if not has_draw_flag:
            return False
        text = str(skill_text or "").lower()
        return "when this card attacks" in text

    @staticmethod
    def _color_to_code(color: str | None) -> str | None:
        if color is None:
            return None
        c = color.strip().lower()
        mapping = {"red": "R", "blue": "B", "green": "G", "yellow": "Y", "black": "K"}
        return mapping.get(c)

    @staticmethod
    def _opponent_of(player_id: int) -> int:
        if player_id == 1:
            return 2
        if player_id == 2:
            return 1
        raise ValueError(f"Unknown player_id: {player_id}")
