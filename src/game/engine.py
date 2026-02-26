from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import random
from typing import Any
from pathlib import Path

from src.game.actions import Action, ActionType
from src.game.effect_rules import EffectRule, load_effect_rules_json, normalize_effect_rules
from src.game.skill_costs import SkillCostDsl, SkillCostSpec
from src.game.state import (
    AttackContext,
    BattleStep,
    CardInstance,
    CheckpointEvent,
    EffectEvent,
    EffectRegistration,
    EffectResolution,
    CounterMotion,
    CounterMotionTrace,
    CounterResolution,
    CounterWindow,
    GameState,
    PendingEffect,
    PendingAction,
    PlayerState,
    TurnPhase,
)


class RulesViolation(ValueError):
    pass


@dataclass(frozen=True)
class CardRuntimeData:
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


class RulesEngine:
    def __init__(
        self,
        card_repository: Any | None = None,
        life_card_chooser: Any | None = None,
        skill_cost_can_pay: Any | None = None,
        skill_cost_pay: Any | None = None,
        skill_cost_rules: dict[int, dict[str, object]] | None = None,
        effect_rules: dict[int, list[dict[str, object]] | list[EffectRule]] | None = None,
        effect_rules_path: str | Path | None = None,
        effect_handlers: dict[str, Any] | None = None,
        effect_target_chooser: Any | None = None,
        effect_multi_target_chooser: Any | None = None,
    ) -> None:
        self._card_repository = card_repository
        self._card_cache: dict[int, CardRuntimeData] = {}
        # Signature: chooser(player_state, damage_index:int, max_index:int) -> selected_index:int
        self._life_card_chooser = life_card_chooser
        # Signature: can_pay(player_state, card_instance, context:str) -> bool
        self._skill_cost_can_pay = skill_cost_can_pay
        # Signature: pay(player_state, card_instance, context:str) -> None
        self._skill_cost_pay = skill_cost_pay
        # Mapping: card_id -> context -> list[{"kind": ..., "amount": ...}] | SkillCostSpec
        self._skill_cost_rules = skill_cost_rules or {}
        # Mapping: card_id -> tuple[EffectRule, ...]
        loaded_rules = load_effect_rules_json(effect_rules_path) if effect_rules_path is not None else {}
        provided_rules = normalize_effect_rules(effect_rules)
        self._effect_rules = self._merge_effect_rule_maps(loaded_rules, provided_rules)
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
            "auto_play_self_from_combo_on_battle_end": self._handle_auto_play_self_from_combo_on_battle_end,
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
            seen: set[tuple[str, str, tuple[tuple[str, int | str | bool], ...], bool]] = set()
            uniq: list[EffectRule] = []
            for r in items:
                sig = (r.trigger, r.handler_id, tuple(sorted(r.handler_params.items())), r.once_per_turn)
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
                    z_deck=list(p1_z_deck_card_ids or []),
                ),
                2: PlayerState(
                    player_id=2,
                    leader_card_id=p2_leader_card_id,
                    leader_area=p2_leader,
                    deck=list(p2_deck_card_ids),
                    z_deck=list(p2_z_deck_card_ids or []),
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
            actions.extend(self._legal_play_actions(state, player_id))
            actions.extend(self._legal_activate_main_actions(state, player_id))
            actions.extend(self._legal_attack_actions(state, player_id))
            return actions
        return []

    def apply_action(self, state: GameState, action: Action) -> GameState:
        if action not in self.get_legal_actions(state, action.player_id):
            raise RulesViolation(f"Illegal action: {action}")
        ns = deepcopy(state)
        player = ns.players[action.player_id]

        if action.action_type == ActionType.CHARGE_FROM_HAND:
            if action.hand_index is None:
                raise RulesViolation("CHARGE_FROM_HAND requires hand_index.")
            card = player.hand.pop(action.hand_index)
            card.resting = True
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
        if action.action_type == ActionType.ACTIVATE_MAIN_SKILL:
            self._declare_activate_skill(ns, action, source_kind="main")
            self._after_action(ns)
            return ns
        if action.action_type == ActionType.ACTIVATE_BATTLE_SKILL:
            self._declare_activate_skill(ns, action, source_kind="battle")
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
        self._reset_once_per_turn_effect_counters(state, player_id=state.active_player)
        self._emit_effect_event(state, name="turn_start", actor_player_id=state.active_player, payload={})
        self._checkpoint(state, "charge_phase_begin")
        player = state.players[state.active_player]
        player.leader_area.resting = False
        player.leader_area.attacked_this_turn = False
        for c in player.energy:
            c.resting = False
        for c in player.battle_area:
            c.resting = False
            c.attacked_this_turn = False
        for c in player.unison_area:
            c.resting = False
            c.attacked_this_turn = False
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
        self._emit_effect_event(state, name="turn_end", actor_player_id=state.active_player, payload={})
        state.active_player = self._opponent_of(state.active_player)
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

    def _legal_play_actions(self, state: GameState, player_id: int) -> list[Action]:
        player = state.players[player_id]
        actions: list[Action] = []
        for i, card in enumerate(player.hand):
            if card.card_type not in {"BATTLE", "UNISON", "EXTRA", "Z-BATTLE", "Z-UNISON", "Z-EXTRA"}:
                continue
            if self._can_pay_costs(
                player,
                energy_cost=card.energy_cost or 0,
                required_color=card.color,
                specified_costs=dict(card.specified_costs),
                z_cost=card.z_energy_cost or 0,
            ):
                actions.append(Action(action_type=ActionType.PLAY_CARD_FROM_HAND, player_id=player_id, hand_index=i))
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
            and self._can_pay_skill_cost(player, player.leader_area, "activate_main")
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
                and self._can_pay_skill_cost(player, c, "activate_main")
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
                and self._can_pay_skill_cost(player, c, "activate_main")
            ):
                actions.append(Action(action_type=ActionType.ACTIVATE_MAIN_SKILL, player_id=player_id, source_zone="unison", source_index=i))
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
        if not player.leader_area.resting and not player.leader_area.attacked_this_turn:
            actions.extend(
                Action(action_type=ActionType.DECLARE_ATTACK, player_id=player_id, attacker_zone="leader", target_player_id=opponent_id, target_zone=z, target_index=i)
                for z, i in targets
            )
        for zone_name, zone_cards in (("battle", player.battle_area), ("unison", player.unison_area)):
            for ai, attacker in enumerate(zone_cards):
                if attacker.resting or attacker.attacked_this_turn:
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
            and self._can_pay_skill_cost(player, player.leader_area, "activate_battle")
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
                and self._can_pay_skill_cost(player, c, "activate_battle")
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
                and self._can_pay_skill_cost(player, c, "activate_battle")
            ):
                actions.append(Action(action_type=ActionType.ACTIVATE_BATTLE_SKILL, player_id=player_id, source_zone="unison", source_index=i))
        return actions

    def _legal_combo_actions(self, state: GameState, player_id: int) -> list[Action]:
        player = state.players[player_id]
        actions: list[Action] = []
        for i, c in enumerate(player.hand):
            if c.card_type not in {"BATTLE", "Z-BATTLE"}:
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
            if self._can_pay_energy_cost(
                player,
                c.energy_cost or 0,
                required_color=c.color,
                specified_costs=dict(c.specified_costs),
            ):
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
            acts.extend(self._legal_combo_actions(state, player_id))
            acts.extend(self._legal_activate_battle_actions(state, player_id))
            return acts
        if state.battle_step in {BattleStep.DAMAGE, BattleStep.BATTLE_END}:
            if player_id != ctx.attacker_player_id:
                return []
            return [Action(action_type=ActionType.RESOLVE_BATTLE, player_id=player_id)]
        return []

    def _declare_attack(self, state: GameState, action: Action) -> None:
        if action.attacker_zone not in {"leader", "battle", "unison"}:
            raise RulesViolation("Invalid attacker zone.")
        if action.target_zone not in {"leader", "battle", "unison"} or action.target_player_id is None:
            raise RulesViolation("Invalid target.")
        attacker = self._resolve_zone_card(state, player_id=action.player_id, zone=action.attacker_zone, index=action.attacker_index)
        target = self._resolve_zone_card(state, player_id=action.target_player_id, zone=action.target_zone, index=action.target_index)
        attacker.resting = True
        attacker.attacked_this_turn = True
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
        paid_energy_cards, _ = self._pay_costs(
            player,
            energy_cost=card.energy_cost or 0,
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
        if action.source_zone not in {"leader", "battle", "unison"}:
            raise RulesViolation("Invalid source zone.")
        if action.source_zone == "leader":
            source = player.leader_area
        else:
            if action.source_index is None:
                raise RulesViolation("Missing source index.")
            zone = player.battle_area if action.source_zone == "battle" else player.unison_area
            if not (0 <= action.source_index < len(zone)):
                raise RulesViolation("Source index out of range.")
            source = zone[action.source_index]
        if source_kind == "main" and not source.has_activate_main:
            raise RulesViolation("No Activate: Main.")
        if source_kind == "battle" and not source.has_activate_battle:
            raise RulesViolation("No Activate: Battle.")
        if not self._is_valid_skill_source_area(source, action.source_zone):
            raise RulesViolation("Skill source is in an invalid area for its card type.")
        if not self._can_pay_skill_cost(player, source, f"activate_{source_kind}"):
            raise RulesViolation("Cannot pay skill cost.")
        self._pay_energy_cost(
            player,
            source.energy_cost or 0,
            required_color=source.color,
            specified_costs=dict(source.specified_costs),
        )
        self._pay_skill_cost(state, player, source, f"activate_{source_kind}")
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
                },
            ),
        )
        self._checkpoint(state, f"counter_timing_activate_{source_kind}")

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
        self._pay_energy_cost(
            player,
            card.energy_cost or 0,
            required_color=card.color,
            specified_costs=dict(card.specified_costs),
        )
        declared = player.hand.pop(action.hand_index)
        player.drop.append(declared)
        self._checkpoint(state, "counter_declared")
        state.counter_chain.append(
            CounterMotion(
                motion_id=state.next_counter_motion_id,
                player_id=action.player_id,
                card_instance_id=declared.instance_id,
                modes=declared.counter_modes,
            )
        )
        state.counter_motion_trace.append(
            CounterMotionTrace(
                motion_id=state.next_counter_motion_id,
                turn_number=state.turn_number,
                phase=state.phase,
                window_kind=win.kind,
                player_id=action.player_id,
                card_instance_id=declared.instance_id,
                modes=declared.counter_modes,
                resolved=None,
                negated_motion_id=None,
            )
        )
        self._checkpoint(state, f"counter_motion_declared_{state.next_counter_motion_id}")
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
                },
            )
            self._checkpoint(state, "skill_activation_resolved")
            return
        raise RulesViolation(f"Unknown pending action type: {pending.action_type}")

    def _resolve_counter_chain(self, state: GameState) -> bool:
        motions = state.counter_chain
        if not motions:
            return False

        active: dict[int, bool] = {m.motion_id: True for m in motions}
        index_by_id = {m.motion_id: i for i, m in enumerate(motions)}

        resolutions: list[CounterResolution] = []
        for motion in reversed(motions):
            if not active[motion.motion_id]:
                resolutions.append(
                    CounterResolution(
                        motion_id=motion.motion_id,
                        player_id=motion.player_id,
                        resolved=False,
                        negated_motion_id=None,
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
                    resolved=True,
                    negated_motion_id=negated_id,
                )
            )

        state.counter_resolutions.extend(resolutions)
        for r in resolutions:
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
                    player_id=source.player_id,
                    card_instance_id=source.card_instance_id,
                    modes=source.modes,
                    resolved=r.resolved,
                    negated_motion_id=r.negated_motion_id,
                )
            )
        root_negated = any(r.resolved and r.negated_motion_id is None for r in resolutions)
        state.counter_chain = []
        return root_negated

    def _resolve_play_from_hand(self, state: GameState, pending: PendingAction, *, negated: bool) -> None:
        player = state.players[pending.actor_player_id]
        target_id = int(pending.payload.get("card_instance_id") or -1)
        idx = next((i for i, c in enumerate(player.hand) if c.instance_id == target_id), None)
        if idx is None:
            return
        card = player.hand.pop(idx)
        if negated:
            player.drop.append(card)
            self._checkpoint(state, "play_negated")
            return
        if card.card_type in {"BATTLE", "Z-BATTLE"}:
            player.battle_area.append(card)
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
            paid_energy = int(pending.payload.get("paid_energy_cards") or 0)
            card.markers = max(paid_energy, 0)
            if player.unison_area:
                replaced = player.unison_area.pop()
                if replaced.card_type.startswith("Z-"):
                    player.removed_from_game.append(replaced)
                else:
                    player.drop.append(replaced)
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
            player.battle_area
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
        for player in state.players.values():
            i = 0
            while i < len(player.battle_area):
                if player.battle_area[i].power <= 0:
                    player.drop.append(player.battle_area.pop(i))
                    self._checkpoint(state, "rule_battle_power_zero")
                    continue
                i += 1

            i = 0
            while i < len(player.unison_area):
                unison = player.unison_area[i]
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

    def _pay_skill_cost(self, state: GameState, player: PlayerState, card: CardInstance, context: str) -> None:
        if self._skill_cost_pay is None:
            spec = self._resolve_skill_cost_spec(card.card_id, context)
            if spec is None:
                return
            try:
                before_markers = card.markers
                SkillCostDsl.pay(player, card, spec)
                removed_markers = max(before_markers - card.markers, 0)
                if removed_markers > 0 and card.card_type in {"UNISON", "Z-UNISON"}:
                    self._checkpoint(state, "marker_remove_begin_skill_cost")
                    self._checkpoint(state, "marker_removed_skill_cost")
                return
            except Exception as exc:
                raise RulesViolation(f"Skill cost payment failed: {exc}") from exc
        try:
            self._skill_cost_pay(player, card, context)
        except Exception as exc:
            raise RulesViolation(f"Skill cost payment failed: {exc}") from exc

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
        ctype = (card.card_type or "").upper()
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
            candidates.append((rule.trigger, rule.handler_id, rule.once_per_turn, dict(rule.handler_params)))

        for trigger, handler_id, once_per_turn_override, handler_params in candidates:
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
                    once_per_turn=card.auto_once_per_turn if once_per_turn_override is None else bool(once_per_turn_override),
                )
            )
            state.next_effect_id += 1

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

    @staticmethod
    def _effect_registration_matches_event(reg: EffectRegistration, event: EffectEvent) -> bool:
        if reg.trigger == "self_played":
            if event.name != "card_played":
                return False
            return int(event.payload.get("source_instance_id") or -1) == reg.source_instance_id
        if reg.trigger == "self_attacks":
            if event.name != "attack_declared":
                return False
            return int(event.payload.get("attacker_instance_id") or -1) == reg.source_instance_id
        if reg.trigger == "owner_leader_attacks":
            if event.name != "attack_declared":
                return False
            if event.actor_player_id != reg.owner_player_id:
                return False
            return str(event.payload.get("attacker_zone") or "") == "leader"
        if reg.trigger == "self_comboed":
            if event.name != "card_comboed":
                return False
            return int(event.payload.get("source_instance_id") or -1) == reg.source_instance_id
        if reg.trigger == "self_activate_main":
            if event.name != "skill_activated":
                return False
            if str(event.payload.get("skill_kind") or "") != "activate_main":
                return False
            return int(event.payload.get("source_instance_id") or -1) == reg.source_instance_id
        if reg.trigger == "self_activate_battle":
            if event.name != "skill_activated":
                return False
            if str(event.payload.get("skill_kind") or "") != "activate_battle":
                return False
            return int(event.payload.get("source_instance_id") or -1) == reg.source_instance_id
        if reg.trigger == "self_koed":
            if event.name != "card_koed":
                return False
            return int(event.payload.get("source_instance_id") or -1) == reg.source_instance_id
        if reg.trigger == "owner_battle_played_from_warp":
            if event.name != "card_played":
                return False
            if event.actor_player_id != reg.owner_player_id:
                return False
            if str(event.payload.get("source_zone") or "") != "battle":
                return False
            return str(event.payload.get("played_from") or "") == "warp"
        if reg.trigger == "owner_field_extra_placed":
            return event.name == "field_extra_placed"
        if reg.trigger == "owner_opponent_skill_plays_overcost_battle":
            if event.name != "card_played":
                return False
            if event.actor_player_id in {None, reg.owner_player_id}:
                return False
            if str(event.payload.get("source_zone") or "") != "battle":
                return False
            return str(event.payload.get("played_from") or "").strip().lower() not in {"", "hand"}
        if reg.trigger == "self_comboed_battle_end":
            return event.name == "battle_end"
        if reg.trigger == "turn_start":
            return event.name == "turn_start" and event.actor_player_id == reg.owner_player_id
        if reg.trigger == "turn_end":
            return event.name == "turn_end" and event.actor_player_id == reg.owner_player_id
        return False

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
                        once_per_turn=reg.once_per_turn,
                        triggers_this_turn=0,
                    )
                )
            else:
                updated.append(reg)
        state.effect_registry = updated

    def _resolve_pending_effects(self, state: GameState) -> None:
        if not state.pending_effects:
            return
        pending = list(state.pending_effects)
        state.pending_effects.clear()
        regs_by_id = {reg.effect_id: reg for reg in state.effect_registry}
        events_by_id = {evt.event_id: evt for evt in state.effect_events}

        # Rule-order alignment for checkpoint processing: turn player first, then non-turn player.
        ordered_pending: list[PendingEffect] = []
        owner_order = [state.active_player, self._opponent_of(state.active_player)]
        for owner_id in owner_order:
            ordered_pending.extend(
                entry
                for entry in pending
                if (regs_by_id.get(entry.effect_id) is not None and regs_by_id[entry.effect_id].owner_player_id == owner_id)
            )
        ordered_pending.extend(entry for entry in pending if entry not in ordered_pending)

        updated_registry: dict[int, EffectRegistration] = {}
        resolved_once_per_turn_in_checkpoint: set[int] = set()
        for entry in ordered_pending:
            reg = updated_registry.get(entry.effect_id, regs_by_id.get(entry.effect_id))
            evt = events_by_id.get(entry.event_id)
            if reg is None or evt is None:
                state.effect_resolutions.append(
                    EffectResolution(effect_id=entry.effect_id, event_id=entry.event_id, resolved=False, reason="missing_context")
                )
                continue
            if reg.once_per_turn and (reg.triggers_this_turn > 0 or reg.effect_id in resolved_once_per_turn_in_checkpoint):
                state.effect_resolutions.append(
                    EffectResolution(effect_id=reg.effect_id, event_id=evt.event_id, resolved=False, reason="once_per_turn_used")
                )
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
                once_per_turn=reg.once_per_turn,
                triggers_this_turn=reg.triggers_this_turn + 1,
            )
            updated_registry[reg.effect_id] = next_reg
            if reg.once_per_turn:
                resolved_once_per_turn_in_checkpoint.add(reg.effect_id)
            state.effect_resolutions.append(
                EffectResolution(effect_id=reg.effect_id, event_id=evt.event_id, resolved=True, reason="ok")
            )

        if updated_registry:
            final_registry: list[EffectRegistration] = []
            for reg in state.effect_registry:
                final_registry.append(updated_registry.get(reg.effect_id, reg))
            state.effect_registry = final_registry

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
            self._modify_card_power(state, card=source, delta=delta, reason="effect_self_attack_buff")
        grant_keyword = str(reg.handler_params.get("grant_keyword", "")).strip()
        if grant_keyword and grant_keyword not in source.keywords:
            source.keywords = tuple(list(source.keywords) + [grant_keyword])
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
        if owner.unison_area:
            replaced = owner.unison_area.pop()
            if replaced.card_type.startswith("Z-"):
                owner.removed_from_game.append(replaced)
            else:
                owner.drop.append(replaced)
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
        if event.name not in {"card_played", "skill_activated"}:
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
        picked_indexes: list[int] = []
        for i in range(top_n):
            card_id = owner.deck[i]
            runtime = self._resolve_card_runtime_data(card_id)
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
            picked_indexes.append(i)
            if len(picked_indexes) >= max_add:
                break
        if not picked_indexes:
            return
        added = 0
        removed = 0
        for idx in picked_indexes:
            card_id = owner.deck.pop(idx - removed)
            removed += 1
            card = self._create_card_instance(next_instance_id=state.next_instance_id, card_id=card_id, owner_id=reg.owner_player_id)
            state.next_instance_id += 1
            owner.hand.append(card)
            added += 1
        discard_after_add = self._resolve_effect_int_param(state, reg, "discard_after_add", default=0)
        if added > 0 and discard_after_add > 0 and owner.hand:
            for _ in range(min(discard_after_add, len(owner.hand))):
                owner.drop.append(owner.hand.pop(0))
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
        chosen_indexes: list[int] = []
        for i, card_id in enumerate(owner.deck):
            runtime = self._resolve_card_runtime_data(card_id)
            if required_type and required_type not in (runtime.card_type or "").upper():
                continue
            if max_cost >= 0 and (runtime.energy_cost is None or runtime.energy_cost > max_cost):
                continue
            if allowed_colors:
                runtime_colors = {part.strip().lower() for part in str(runtime.color or "").replace("/", ",").split(",") if part.strip()}
                if runtime_colors and runtime_colors.isdisjoint(allowed_colors):
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
            card_id = owner.deck.pop(idx - removed)
            removed += 1
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
                if owner.unison_area:
                    replaced = owner.unison_area.pop()
                    if replaced.card_type.startswith("Z-"):
                        owner.removed_from_game.append(replaced)
                    else:
                        owner.drop.append(replaced)
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
                    if owner.unison_area:
                        replaced = owner.unison_area.pop()
                        if replaced.card_type.startswith("Z-"):
                            owner.removed_from_game.append(replaced)
                        else:
                            owner.drop.append(replaced)
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
        if not candidates:
            return []
        indexes = self._choose_effect_target_indexes(state, reg, candidates, max_targets, policy)
        return [candidates[i] for i in indexes]

    @staticmethod
    def _effect_requirements_met(state: GameState, reg: EffectRegistration) -> bool:
        raw_req = reg.handler_params.get("requires_leader")
        leader_ok = True
        if isinstance(raw_req, str) and raw_req.strip():
            req = raw_req.lower()
            leader = state.players[reg.owner_player_id].leader_area
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
        mono = reg.handler_params.get("requires_mono_energy")
        if isinstance(mono, str) and mono.strip():
            required = mono.strip().lower()
            owner = state.players[reg.owner_player_id]
            for e in owner.energy:
                color = (e.color or "").strip().lower()
                if color and color != required:
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
        if reg.trigger == "self_koed":
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
        )

    def _resolve_card_runtime_data(self, card_id: int) -> CardRuntimeData:
        if card_id in self._card_cache:
            return self._card_cache[card_id]
        runtime = CardRuntimeData()
        if self._card_repository is not None:
            try:
                card = self._card_repository.get_by_id(card_id, source_table="cards")
                runtime = CardRuntimeData(
                    power=int(card.power_int) if getattr(card, "power_int", None) is not None else 15000,
                    card_type=str(getattr(card, "card_type", None) or "BATTLE"),
                    color=getattr(card, "card_color", None),
                    energy_cost_raw=getattr(card, "card_energy_cost", None),
                    energy_cost=getattr(card, "energy_cost_int", None),
                    combo_cost=getattr(card, "combo_cost_int", None),
                    combo_power=getattr(card, "combo_power_int", None),
                    keywords=tuple(getattr(card, "keywords", ()) or ()),
                    has_counter=bool(getattr(card, "has_counter", False)),
                    counter_modes=tuple(k for k in (tuple(getattr(card, "keywords", ()) or ())) if str(k).startswith("Counter:")),
                    has_counter_attack=bool(getattr(card, "has_counter_attack", False)),
                    has_counter_battle_card_attack=any(
                        str(k) == "Counter: Battle Card Attack" for k in (tuple(getattr(card, "keywords", ()) or ()))
                    ),
                    has_counter_play=bool(getattr(card, "has_counter_play", False)),
                    has_counter_counter=any(str(k) == "Counter: Counter" for k in (tuple(getattr(card, "keywords", ()) or ()))),
                    has_activate_main=bool(getattr(card, "has_activate_main", False)),
                    has_activate_battle=bool(getattr(card, "has_activate_battle", False)),
                    has_auto=bool(getattr(card, "has_auto", False)),
                    has_permanent=bool(getattr(card, "has_permanent", False)),
                    has_draw=bool(getattr(card, "has_draw", False)),
                    max_draw=self._parse_optional_int(getattr(card, "max_draw", None)),
                    auto_once_per_turn=self._has_once_per_turn(getattr(card, "card_skill_unstyled", None)),
                    auto_draw_on_play=self._has_auto_draw_on_play(getattr(card, "card_skill_unstyled", None), bool(getattr(card, "has_draw", False))),
                    auto_draw_on_attack=self._has_auto_draw_on_attack(getattr(card, "card_skill_unstyled", None), bool(getattr(card, "has_draw", False))),
                    has_barrier=bool(getattr(card, "has_barrier", False)),
                    z_energy_cost=self._parse_optional_int(getattr(card, "z_energy_cost", None)),
                    specified_costs=self._parse_specified_costs(getattr(card, "card_energy_cost", None), getattr(card, "card_color", None)),
                )
            except Exception:
                runtime = CardRuntimeData()
        self._card_cache[card_id] = runtime
        return runtime

    @staticmethod
    def _parse_optional_int(value: object) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        text = str(value).strip()
        return int(text) if text.isdigit() else None

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
