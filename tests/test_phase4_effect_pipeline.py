from __future__ import annotations

from types import SimpleNamespace

from src.game import Action, ActionType, AttackContext, BattleStep, CardInstance, EffectRegistration, RulesEngine, TurnPhase
from src.game.effect_rules import EffectRule
from src.game.engine import CardRuntimeData


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _to_main(engine: RulesEngine, state):
    while state.phase != TurnPhase.MAIN:
        state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=state.active_player))
    return state


def _to_p1_main_where_attacks_are_legal(engine: RulesEngine, state):
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    return state


def test_phase4_bardock_the_tenacious_restricts_self_copies_from_hand_next_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            5531: (
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_restrict_self_copies_from_hand_next_turn_on_play",
                    handler_params={"restricted_card_id": 5531},
                    family_id="self_played:auto_restrict_self_copies_from_hand_next_turn_on_play",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=990001, card_id=5531, owner_id=1, card_type="BATTLE", color="Black", energy_cost=0, power=20000),
        CardInstance(instance_id=990002, card_id=5531, owner_id=1, card_type="BATTLE", color="Black", energy_cost=0, power=20000),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(cp.name == "effect_auto_restrict_self_copies_from_hand_next_turn_on_play" for cp in state.checkpoints)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    legal = engine.get_legal_actions(state, 1)
    assert any(cp.name == "scheduled_card_play_restrictions_activated" for cp in state.checkpoints)
    assert not any(a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0 for a in legal)


def test_phase4_prismatic_aegis_can_warp_opponent_battle_on_play_from_hand() -> None:
    engine = RulesEngine(
        effect_rules={
            49: (
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_send_up_to_n_opponent_battle_to_warp_on_play",
                    handler_params={"max_targets": 1, "max_cost": 4, "requires_played_from": "hand"},
                    family_id="self_played:auto_send_up_to_n_opponent_battle_to_warp_on_play",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=990010, card_id=49, owner_id=1, card_type="BATTLE", color="Green/Black", energy_cost=0, power=20000)
    ]
    state.players[2].battle_area = [
        CardInstance(instance_id=990011, card_id=701, owner_id=2, card_type="BATTLE", color="Red", energy_cost=4, power=15000),
        CardInstance(instance_id=990012, card_id=702, owner_id=2, card_type="BATTLE", color="Red", energy_cost=5, power=15000),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(card.instance_id == 990011 for card in state.players[2].warp)
    assert any(card.instance_id == 990012 for card in state.players[2].battle_area)
    assert any(cp.name == "effect_auto_send_up_to_n_opponent_battle_to_warp_on_play" for cp in state.checkpoints)


def test_phase4_prismatic_bardock_can_reduce_opponent_unison_for_turn_on_play() -> None:
    engine = RulesEngine(
        effect_rules={
            41: (
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_power_reduce_up_to_n_opponent_cards_for_turn_on_play",
                    handler_params={
                        "max_targets": 1,
                        "target_scope": "battle_or_unison",
                        "power_delta": "expr:owner_energy_color_count*-2000",
                        "requires_played_from": "hand",
                        "min_owner_matching_energy": 1,
                        "required_energy_colors": "black",
                        "requires_multicolor_energy": True,
                    },
                    family_id="self_played:auto_power_reduce_up_to_n_opponent_cards_for_turn_on_play",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=990013, card_id=801, owner_id=1, card_type="ENERGY", color="Black/Blue"),
        CardInstance(instance_id=990014, card_id=802, owner_id=1, card_type="ENERGY", color="Yellow"),
    ]
    target = CardInstance(instance_id=990015, card_id=803, owner_id=2, card_type="UNISON", color="Red", power=20000, markers=2)
    state.players[2].unison_area = [target]
    state.players[1].hand = [
        CardInstance(instance_id=990016, card_id=41, owner_id=1, card_type="BATTLE", color="Black/Red", energy_cost=0, power=20000)
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    reduced = state.players[2].unison_area[0]
    assert reduced.power == 14000
    assert reduced.temporary_power_delta == -6000
    assert any(cp.name == "effect_auto_power_reduce_up_to_n_opponent_cards_for_turn_on_play" for cp in state.checkpoints)


def test_phase4_prismatic_bardock_can_activate_battle_to_reduce_opponent_battle_for_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            41: (
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_power_reduce_up_to_n_opponent_battle_for_turn",
                    handler_params={"max_targets": 1, "power_delta": -5000},
                    family_id="self_activate_battle:activate_power_reduce_up_to_n_opponent_battle_for_turn",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=990017,
        card_id=41,
        owner_id=1,
        card_type="BATTLE",
        color="Black/Red",
        power=20000,
        has_activate_battle=True,
    )
    target = CardInstance(instance_id=990018, card_id=804, owner_id=2, card_type="BATTLE", color="Red", power=15000)
    state.players[1].battle_area.append(source)
    state.players[2].battle_area.append(target)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    state.battle_step = BattleStep.OFFENSE
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="leader",
        attacker_instance_id=state.players[1].leader_area.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    activate = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "battle"
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    reduced = state.players[2].battle_area[0]
    assert reduced.power == 10000
    assert reduced.temporary_power_delta == -5000
    assert any(cp.name == "effect_activate_power_reduce_up_to_n_opponent_battle_for_turn" for cp in state.checkpoints)


def test_phase4_next_level_gogeta_can_gain_marker_life_and_leader_power_when_other_matching_battle_is_played() -> None:
    engine = RulesEngine(
        effect_rules={
            7846: (
                EffectRule(
                    trigger="owner_other_battle_played",
                    handler_id="auto_add_life_to_hand_and_buff_owner_leader_on_owner_matching_battle_played",
                    handler_params={"marker_delta": 1},
                    family_id="owner_other_battle_played:auto_add_life_to_hand_and_buff_owner_leader_on_owner_matching_battle_played",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=990019, card_id=7846, owner_id=1, card_type="UNISON", color="Blue/Yellow", markers=2)
    state.players[1].unison_area.append(source)
    state.players[1].life = [
        CardInstance(instance_id=990020, card_id=805, owner_id=1, card_type="BATTLE", color="Blue", power=5000)
    ]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)
    played = CardInstance(
        instance_id=990021,
        card_id=806,
        owner_id=1,
        card_type="BATTLE",
        color="Red/Blue",
        power=15000,
        characters=("GT",),
    )
    state.players[1].battle_area.append(played)
    baseline = state.players[1].leader_area.power
    hand_before = len(state.players[1].hand)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={
            "source_instance_id": played.instance_id,
            "source_card_id": played.card_id,
            "source_zone": "battle",
            "played_from": "hand",
        },
    )
    engine._resolve_pending_effects(state)
    assert state.players[1].unison_area[0].markers == 3
    assert len(state.players[1].hand) == hand_before + 1
    assert state.players[1].leader_area.power == baseline + 5000
    assert state.players[1].leader_area.temporary_power_delta == 5000
    assert any(cp.name == "effect_auto_add_life_to_hand_and_buff_owner_leader_on_owner_matching_battle_played" for cp in state.checkpoints)


def test_phase4_temporal_darkness_demigra_can_warp_opponent_battle_and_play_from_warp() -> None:
    engine = RulesEngine(
        effect_rules={
            5826: (
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_send_up_to_n_opponent_battle_to_warp_and_play_up_to_n_from_owner_warp_on_play",
                    handler_params={"max_targets": 1, "play_count": 1, "max_play_cost": 4, "target_policy": "first"},
                    family_id="self_played:auto_send_up_to_n_opponent_battle_to_warp_and_play_up_to_n_from_owner_warp_on_play",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=990022, card_id=5826, owner_id=1, card_type="BATTLE", color="Black", energy_cost=0, power=15000)
    ]
    state.players[1].warp = [
        CardInstance(instance_id=990023, card_id=807, owner_id=1, card_type="BATTLE", color="Black", energy_cost=5, power=30000),
        CardInstance(instance_id=990024, card_id=808, owner_id=1, card_type="BATTLE", color="Black", energy_cost=4, power=20000),
    ]
    state.players[2].battle_area = [
        CardInstance(instance_id=990025, card_id=809, owner_id=2, card_type="BATTLE", color="Red", energy_cost=3, power=15000)
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(card.instance_id == 990025 for card in state.players[2].warp)
    assert any(card.instance_id == 990024 for card in state.players[1].battle_area)
    assert any(card.instance_id == 990023 for card in state.players[1].warp)
    assert any(cp.name == "effect_auto_send_up_to_n_opponent_battle_to_warp_and_play_up_to_n_from_owner_warp_on_play" for cp in state.checkpoints)


def test_phase4_accidental_wish_plus_two_can_reduce_opponent_battle_for_turn_and_gain_markers() -> None:
    engine = RulesEngine(
        effect_rules={
            7906: (
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_power_reduce_up_to_n_opponent_battle_for_turn",
                    handler_params={"max_targets": 1, "power_delta": -20000, "marker_delta": 2},
                    family_id="self_activate_main:activate_power_reduce_up_to_n_opponent_battle_for_turn",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=990026,
        card_id=7906,
        owner_id=1,
        card_type="Z-UNISON",
        color="Blue/Yellow",
        markers=3,
        has_activate_main=True,
    )
    target = CardInstance(instance_id=990027, card_id=810, owner_id=2, card_type="BATTLE", color="Red", power=25000)
    state.players[1].unison_area.append(source)
    state.players[2].battle_area.append(target)
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)
    activate = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].unison_area[0].markers == 5
    assert state.players[2].battle_area[0].temporary_power_delta == -20000
    assert state.players[2].battle_area[0].power == 5000
    assert any(cp.name == "effect_activate_power_reduce_up_to_n_opponent_battle_for_turn" for cp in state.checkpoints)


def test_phase4_guided_android_can_counter_play_with_power_wish_cost_and_rest_opponent_battle() -> None:
    engine = RulesEngine(
        skill_cost_rules={
            7940: {
                "counter_alternate_from_hand": [
                    {
                        "kind": "send_owner_drop_to_warp",
                        "amount": 2,
                        "required_leader_traits": "power wish",
                        "requires_life_at_most": 4,
                        "required_traits": "power wish",
                    }
                ]
            }
        },
        effect_rules={
            7940: (
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_switch_up_to_n_opponent_battle_rest_on_play",
                    handler_params={"max_targets": 1, "max_cost": 6},
                    family_id="self_played:auto_switch_up_to_n_opponent_battle_rest_on_play",
                    provenance="test",
                    limit_per_turn=1,
                ),
            )
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state.players[2].leader_area.traits = ("Power Wish",)
    state = _to_main(engine, state)
    while len(state.players[2].life) > 4:
        state.players[2].hand.append(state.players[2].life.pop(0))
    state.players[1].hand = [CardInstance(instance_id=990028, card_id=811, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand.append(
        CardInstance(
            instance_id=990029,
            card_id=7940,
            owner_id=2,
            card_type="BATTLE",
            color="Green",
            energy_cost=4,
            power=15000,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw="[Counter: Play][Limit 1] If your Leader is a ≪Power Wish≫ card: Play this card.",
        )
    )
    state.players[2].drop.extend(
        [
            CardInstance(instance_id=990030, card_id=812, owner_id=2, card_type="BATTLE", traits=("Power Wish",)),
            CardInstance(instance_id=990031, card_id=813, owner_id=2, card_type="BATTLE", traits=("Power Wish",)),
        ]
    )
    state.players[1].battle_area = [
        CardInstance(instance_id=990032, card_id=814, owner_id=1, card_type="BATTLE", color="Red", energy_cost=6, power=20000)
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    assert len(state.players[2].warp) == 2
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    assert any(card.card_id == 7940 for card in state.players[2].battle_area)
    assert state.players[1].battle_area[0].resting is True
    assert any(cp.name == "effect_auto_switch_up_to_n_opponent_battle_rest_on_play" for cp in state.checkpoints)


def test_phase4_broly_omen_of_evolution_can_activate_from_combo_and_drop_opponent_combo() -> None:
    engine = RulesEngine(
        effect_rules={
            27: (
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_send_up_to_n_opponent_combo_to_drop",
                    handler_params={"max_targets": 1, "max_combo_cost": 0, "target_policy": "first"},
                    family_id="self_activate_battle:activate_send_up_to_n_opponent_combo_to_drop",
                    provenance="test",
                ),
            )
        },
        skill_cost_rules={
            27: {
                "activate_battle_combo": [
                    {"kind": "send_self_from_combo_to_drop", "amount": 1},
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    combo_broly = CardInstance(
        instance_id=990041,
        card_id=27,
        owner_id=1,
        card_number="EX19-12",
        card_type="BATTLE",
        color="Green",
        combo_cost=1,
        combo_power=10000,
        has_activate_battle=True,
    )
    target_combo = CardInstance(
        instance_id=990042,
        card_id=900102,
        owner_id=2,
        card_type="BATTLE",
        color="Red",
        combo_cost=0,
        combo_power=5000,
    )
    untouched_combo = CardInstance(
        instance_id=990043,
        card_id=900103,
        owner_id=2,
        card_type="BATTLE",
        color="Red",
        combo_cost=1,
        combo_power=10000,
    )
    state.players[1].combo_area.append(combo_broly)
    state.players[2].combo_area.extend([target_combo, untouched_combo])
    engine._register_card_effects(state, player_id=1, source_zone="combo", card=combo_broly)
    state.battle_step = BattleStep.OFFENSE
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="leader",
        attacker_instance_id=state.players[1].leader_area.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    activate = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "combo"
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(card.instance_id == 990041 for card in state.players[1].drop)
    assert any(card.instance_id == 990042 for card in state.players[2].drop)
    assert all(card.instance_id != 990042 for card in state.players[2].combo_area)
    assert any(card.instance_id == 990043 for card in state.players[2].combo_area)
    assert any(cp.name == "effect_activate_send_up_to_n_opponent_combo_to_drop" for cp in state.checkpoints)


def test_phase4_koitsukai_can_activate_from_drop_and_punish_low_power_battle_play() -> None:
    engine = RulesEngine(
        effect_rules={
            7386: (
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_remove_self_from_drop_bottom_deck_hand_draw_and_punish_low_power_battle_play",
                    handler_params={
                        "required_source_zone": "drop",
                        "activate_total_cost": 1,
                        "max_bottom_deck_from_hand": 2,
                        "low_power_threshold": 20000,
                        "opponent_hand_to_warp": 2,
                    },
                    family_id="self_activate_main:activate_remove_self_from_drop_bottom_deck_hand_draw_and_punish_low_power_battle_play",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=990044, card_id=900104, owner_id=1, card_type="ENERGY", color="Black", resting=False)
    ]
    state.players[1].drop = [
        CardInstance(
            instance_id=990045,
            card_id=7386,
            owner_id=1,
            card_number="DB2-143",
            card_type="BATTLE",
            color="Black",
            power=5000,
            has_activate_main=True,
        )
    ]
    state.players[1].hand = [
        CardInstance(instance_id=990046, card_id=900105, owner_id=1, card_type="BATTLE", color="Black", power=5000),
        CardInstance(instance_id=990047, card_id=900106, owner_id=1, card_type="BATTLE", color="Black", power=5000),
        CardInstance(instance_id=990048, card_id=900107, owner_id=1, card_type="BATTLE", color="Black", power=5000),
    ]
    state.players[2].hand = [
        CardInstance(instance_id=990049, card_id=900108, owner_id=2, card_type="BATTLE", color="Red", power=5000),
        CardInstance(instance_id=990140, card_id=900109, owner_id=2, card_type="BATTLE", color="Red", power=5000),
        CardInstance(instance_id=990141, card_id=900110, owner_id=2, card_type="BATTLE", color="Red", power=5000),
    ]
    activate = next(
        action
        for action in engine.get_legal_actions(state, 1)
        if action.action_type == ActionType.ACTIVATE_MAIN_SKILL and action.source_zone == "drop"
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].energy[0].resting is True
    assert any(card.instance_id == 990045 for card in state.players[1].removed_from_game)
    assert len(state.players[1].hand) == 3
    assert len(state.low_power_battle_play_hand_warp_penalties) == 1
    played = CardInstance(
        instance_id=990142,
        card_id=900111,
        owner_id=2,
        card_type="BATTLE",
        color="Red",
        power=15000,
    )
    state.players[2].battle_area.append(played)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=2,
        payload={
            "source_instance_id": played.instance_id,
            "source_card_id": played.card_id,
            "source_zone": "battle",
            "played_from": "hand",
        },
    )
    assert len(state.players[2].hand) == 1
    assert len(state.players[2].warp) == 2
    assert any(cp.name == "effect_activate_remove_self_from_drop_bottom_deck_hand_draw_and_punish_low_power_battle_play" for cp in state.checkpoints)
    assert any(cp.name == "low_power_battle_play_hand_warp_penalty_applied" for cp in state.checkpoints)


def test_phase4_piccolo_jr_alliance_rests_matching_owner_battles_and_applies_attack_payoff() -> None:
    engine = RulesEngine(
        effect_rules={
            6299: (
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_alliance_rest_matching_owner_battles_gain_power_draw_n_and_deal_damage",
                    handler_params={
                        "requires_leader": "red",
                        "alliance_allowed_colors": "red,green",
                        "draw_count": 2,
                        "min_opponent_life_for_damage": 3,
                    },
                    family_id="self_attacks:auto_alliance_rest_matching_owner_battles_gain_power_draw_n_and_deal_damage",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Red"
    piccolo = CardInstance(instance_id=990150, card_id=6299, owner_id=1, card_type="BATTLE", color="Red/Green", power=16000)
    ally_red = CardInstance(instance_id=990151, card_id=900150, owner_id=1, card_type="BATTLE", color="Red", power=5000, resting=False)
    ally_green = CardInstance(instance_id=990152, card_id=900151, owner_id=1, card_type="BATTLE", color="Green", power=10000, resting=False)
    ally_blue = CardInstance(instance_id=990153, card_id=900152, owner_id=1, card_type="BATTLE", color="Blue", power=15000, resting=False)
    state.players[1].battle_area = [piccolo, ally_red, ally_green, ally_blue]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=piccolo)
    owner_hand_before = len(state.players[1].hand)
    opp_life_before = len(state.players[2].life)
    opp_hand_before = len(state.players[2].hand)
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={
            "attacker_instance_id": piccolo.instance_id,
            "attacker_zone": "battle",
            "target_player_id": 2,
            "target_zone": "leader",
        },
    )
    engine._resolve_pending_effects(state)
    assert ally_red.resting is True
    assert ally_green.resting is True
    assert ally_blue.resting is False
    assert piccolo.battle_temporary_power_delta == 15000
    assert len(state.players[1].hand) == owner_hand_before + 2
    assert len(state.players[2].life) == opp_life_before - 1
    assert len(state.players[2].hand) == opp_hand_before + 1
    assert any(cp.name == "effect_auto_alliance_rest_matching_owner_battles_gain_power_draw_n_and_deal_damage" for cp in state.checkpoints)


def test_phase4_goku_black_works_undone_can_add_marker_and_place_self_under_matching_unison() -> None:
    engine = RulesEngine(
        effect_rules={
            23: (
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_add_marker_to_matching_owner_unison_and_place_self_under_it",
                    handler_params={
                        "required_source_zone": "battle",
                        "requires_leader": "blue",
                        "target_card_id": 21,
                        "target_required_name_contains": "ZAMASU, TEAMWORK UNDYING",
                    },
                    limit_per_turn=1,
                    family_id="self_activate_main:activate_add_marker_to_matching_owner_unison_and_place_self_under_it",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Blue"
    source = CardInstance(instance_id=990160, card_id=23, owner_id=1, card_type="BATTLE", color="Blue", has_activate_main=True)
    target_unison = CardInstance(instance_id=990161, card_id=21, owner_id=1, card_type="UNISON", color="Blue", markers=2, has_activate_main=True)
    state.players[1].battle_area = [source]
    state.players[1].unison_area = [target_unison]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    activate = next(
        action
        for action in engine.get_legal_actions(state, 1)
        if action.action_type == ActionType.ACTIVATE_MAIN_SKILL and action.source_zone == "battle"
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].battle_area) == 0
    assert state.players[1].unison_area[0].markers == 3
    assert state.players[1].unison_area[0].stacked_card_ids == (23,)
    assert any(cp.name == "effect_activate_add_marker_to_matching_owner_unison_and_place_self_under_it" for cp in state.checkpoints)


def test_phase4_cell_can_capture_opponent_battles_under_self_then_drop_them_for_restand_and_keyword() -> None:
    engine = RulesEngine(
        effect_rules={
            1002: (
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_place_all_opponent_battles_up_to_cost_under_self_on_play",
                    handler_params={"max_cost": 5},
                    family_id="self_played:auto_place_all_opponent_battles_up_to_cost_under_self_on_play",
                    provenance="test",
                ),
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_drop_all_under_self_switch_self_active_and_gain_keyword_if_dropped_n",
                    handler_params={
                        "required_source_zone": "battle",
                        "grant_keyword": "Triple Strike",
                        "min_released_for_keyword": 4,
                    },
                    family_id="self_activate_main:activate_drop_all_under_self_switch_self_active_and_gain_keyword_if_dropped_n",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    cell = CardInstance(instance_id=990170, card_id=1002, owner_id=1, card_type="Z-BATTLE", color="Green", power=25000, has_activate_main=True, resting=True)
    state.players[1].battle_area = [cell]
    state.players[2].battle_area = [
        CardInstance(instance_id=990171, card_id=900160, owner_id=2, card_type="BATTLE", color="Red", energy_cost=1, power=10000),
        CardInstance(instance_id=990172, card_id=900161, owner_id=2, card_type="BATTLE", color="Blue", energy_cost=2, power=10000),
        CardInstance(instance_id=990173, card_id=900162, owner_id=2, card_type="BATTLE", color="Green", energy_cost=3, power=10000),
        CardInstance(instance_id=990174, card_id=900163, owner_id=2, card_type="BATTLE", color="Yellow", energy_cost=4, power=10000),
        CardInstance(instance_id=990175, card_id=900164, owner_id=2, card_type="BATTLE", color="Black", energy_cost=6, power=10000),
    ]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=cell)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={
            "source_instance_id": cell.instance_id,
            "source_card_id": cell.card_id,
            "source_zone": "battle",
            "played_from": "hand",
        },
    )
    engine._resolve_pending_effects(state)
    assert len(state.players[2].battle_area) == 1
    assert state.players[2].battle_area[0].instance_id == 990175
    assert len(state.players[1].battle_area[0].stacked_card_ids) == 4
    activate = next(
        action
        for action in engine.get_legal_actions(state, 1)
        if action.action_type == ActionType.ACTIVATE_MAIN_SKILL and action.source_zone == "battle"
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].battle_area[0].resting is False
    assert state.players[1].battle_area[0].stacked_card_ids == ()
    assert "Triple Strike" in state.players[1].battle_area[0].temporary_keywords
    assert len(state.players[2].drop) == 4
    assert any(cp.name == "effect_auto_place_all_opponent_battles_up_to_cost_under_self_on_play" for cp in state.checkpoints)
    assert any(cp.name == "effect_activate_drop_all_under_self_switch_self_active_and_gain_keyword_if_dropped_n" for cp in state.checkpoints)


def test_phase4_gigantic_meteor_can_ko_opponent_battles_up_to_total_power_budget() -> None:
    engine = RulesEngine(
        effect_rules={
            83: (
                EffectRule(
                    trigger="self_activate_extra_from_hand",
                    handler_id="activate_ko_opponent_battles_up_to_total_power",
                    handler_params={"max_total_power": 30000, "requires_owner_turn": True},
                    limit_per_turn=1,
                    family_id="self_activate_extra_from_hand:activate_ko_opponent_battles_up_to_total_power",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=990050, card_id=900110, owner_id=1, card_type="ENERGY", color="Red", resting=False),
        CardInstance(instance_id=990051, card_id=900111, owner_id=1, card_type="ENERGY", color="Red", resting=False),
        CardInstance(instance_id=990052, card_id=900112, owner_id=1, card_type="ENERGY", color="Red", resting=False),
    ]
    state.players[1].hand = [
        CardInstance(instance_id=990053, card_id=83, owner_id=1, card_number="BT15-030", card_type="EXTRA", color="Red", energy_cost=3)
    ]
    state.players[2].battle_area = [
        CardInstance(instance_id=990054, card_id=900113, owner_id=2, card_type="BATTLE", color="Blue", power=10000, energy_cost=1),
        CardInstance(instance_id=990055, card_id=900114, owner_id=2, card_type="BATTLE", color="Blue", power=20000, energy_cost=2),
        CardInstance(instance_id=990056, card_id=900115, owner_id=2, card_type="BATTLE", color="Blue", power=25000, energy_cost=3),
    ]
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    remaining_ids = {card.instance_id for card in state.players[2].battle_area}
    drop_ids = {card.instance_id for card in state.players[2].drop}
    assert 990054 in drop_ids
    assert 990055 in drop_ids
    assert 990056 in remaining_ids
    assert any(card.instance_id == 990053 for card in state.players[1].drop)
    assert any(cp.name == "effect_activate_ko_opponent_battles_up_to_total_power" for cp in state.checkpoints)


def test_phase4_prismatic_burst_adds_markers_on_play_then_warps_overcost_battle() -> None:
    engine = RulesEngine(
        effect_rules={
            36: (
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_add_markers_per_n_multicolor_energy_on_play",
                    handler_params={"per_n_energy": 2, "min_source_markers": 1},
                    limit_per_turn=1,
                    family_id="self_played:auto_add_markers_per_n_multicolor_energy_on_play",
                    provenance="test",
                ),
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_send_up_to_n_opponent_battle_to_warp",
                    handler_params={
                        "max_targets": 1,
                        "target_policy": "first",
                        "requires_cost_greater_than_opponent_current_energy": True,
                    },
                    family_id="self_activate_main:activate_send_up_to_n_opponent_battle_to_warp",
                    provenance="test",
                ),
            )
        },
        skill_cost_rules={
            36: {
                "activate_main_unison": [
                    {"kind": "remove_markers", "amount": 1},
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=990060, card_id=900120, owner_id=1, card_type="ENERGY", color="Red/Green", resting=False),
        CardInstance(instance_id=990061, card_id=900121, owner_id=1, card_type="ENERGY", color="Blue/Green", resting=False),
        CardInstance(instance_id=990062, card_id=900122, owner_id=1, card_type="ENERGY", color="Red/Yellow", resting=False),
        CardInstance(instance_id=990063, card_id=900123, owner_id=1, card_type="ENERGY", color="Blue/Yellow", resting=False),
    ]
    state.players[1].energy_markers = 1
    state.players[1].hand = [
        CardInstance(
            instance_id=990064,
            card_id=36,
            owner_id=1,
            card_number="EX19-21",
            card_type="UNISON",
            color="Green",
            energy_cost=1,
            has_activate_main=True,
        )
    ]
    state.players[2].energy = [
        CardInstance(instance_id=990065, card_id=900124, owner_id=2, card_type="ENERGY", color="Black", resting=False),
        CardInstance(instance_id=990066, card_id=900125, owner_id=2, card_type="ENERGY", color="Black", resting=False),
    ]
    state.players[2].battle_area = [
        CardInstance(instance_id=990067, card_id=900126, owner_id=2, card_type="BATTLE", color="Black", energy_cost=3, power=20000)
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].unison_area) == 1
    source = state.players[1].unison_area[0]
    assert source.markers == 3
    activate = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    source = state.players[1].unison_area[0]
    assert source.markers == 2
    assert not state.players[2].battle_area
    assert any(card.instance_id == 990067 for card in state.players[2].warp)
    assert any(cp.name == "effect_auto_add_markers_per_n_multicolor_energy_on_play" for cp in state.checkpoints)
    assert any(cp.name == "effect_activate_send_up_to_n_opponent_battle_to_warp" for cp in state.checkpoints)


def test_phase4_majin_buu_pure_destroyer_can_flip_leader_draw_and_remove_self() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id != 1603:
                return None
            return SimpleNamespace(
                card_name="Majin Buu Leader",
                power_int=15000,
                card_type="LEADER",
                card_color="Black",
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_barrier=False,
                has_draw=False,
                max_draw_count=None,
                z_energy_cost=None,
                card_energy_cost="",
                card_skill_unstyled="",
                card_traits=(),
                card_characters=(),
                source_table="cards",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            1603: (
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_flip_owner_leader_to_back_draw_n_and_send_self_to_removed",
                    handler_params={
                        "amount": 2,
                        "required_leader_back_name_contains": "MAJIN BUU, LEADER OF THE AGENTS OF DESTRUCTION",
                        "requires_leader_front_side_up": True,
                        "max_owner_life": 6,
                        "min_owner_energy": 2,
                    },
                    family_id="self_activate_main:activate_flip_owner_leader_to_back_draw_n_and_send_self_to_removed",
                    provenance="test",
                ),
            )
        },
    )
    engine._card_cache[(1, "back")] = CardRuntimeData(card_name="Majin Buu, Leader of the Agents of Destruction", power=20000)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].life = state.players[1].life[:6]
    state.players[1].energy = [
        CardInstance(instance_id=990070, card_id=900130, owner_id=1, card_type="ENERGY", color="Black", resting=False),
        CardInstance(instance_id=990071, card_id=900131, owner_id=1, card_type="ENERGY", color="Black", resting=False),
    ]
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990072,
            card_id=1603,
            owner_id=1,
            card_number="P-473",
            card_type="Z-BATTLE",
            color="Black",
            energy_cost=1,
            has_activate_main=True,
        )
    ]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    )
    hand_before = len(state.players[1].hand)
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].leader_area.awakened is True
    assert len(state.players[1].hand) == hand_before + 2
    assert not state.players[1].battle_area
    assert any(card.instance_id == 990072 for card in state.players[1].removed_from_game)
    assert any(cp.name == "effect_activate_flip_owner_leader_to_back_draw_n_and_send_self_to_removed" for cp in state.checkpoints)


def test_phase4_wish_can_add_desire_from_drop_and_flip_leader() -> None:
    engine = RulesEngine()
    engine._card_cache[(1, "back")] = CardRuntimeData(card_name="Wish Back", power=20000, card_type="LEADER", color="Red")
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.skill_text_raw = (
        "[Wish] When there are 7 [Dragon Ball] cards in your Drop Area: "
        "Choose up to 1 ≪Desire≫ card in your Drop Area, add it to your hand, and flip this card over."
    )
    state.players[1].leader_area.has_awaken = False
    state.players[1].leader_area.awakened = False
    state.players[1].drop = [
        *[
            CardInstance(instance_id=990073 + i, card_id=950000 + i, owner_id=1, card_type="EXTRA", traits=("Dragon Ball",))
            for i in range(7)
        ],
        CardInstance(instance_id=990081, card_id=950100, owner_id=1, card_type="EXTRA", traits=("Desire",)),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.awakened is True
    assert len(state.players[1].hand) == hand_before + 1
    assert any(card.card_id == 950100 for card in state.players[1].hand)
    assert any(card.card_id == 950000 for card in state.players[1].drop)
    assert any(cp.name == "leader_wished" for cp in state.checkpoints)


def test_phase4_wish_can_draw_recycle_dragon_balls_and_flip_leader() -> None:
    engine = RulesEngine()
    engine._card_cache[(1, "back")] = CardRuntimeData(card_name="Wish Back", power=20000, card_type="LEADER", color="Black")
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.skill_text_raw = (
        "[Wish] When your life is at 3 or less or there are 7 [Dragon Ball] cards in your Drop Area: "
        "Draw 1 card, then place all [Dragon Ball] cards from your Drop Area at the bottom of your deck in any order and flip this card over."
    )
    state.players[1].leader_area.has_awaken = False
    state.players[1].leader_area.awakened = False
    state.players[1].life = state.players[1].life[:3]
    dragon_ball_ids = [951000 + i for i in range(3)]
    state.players[1].drop = [
        *[
            CardInstance(instance_id=990082 + i, card_id=card_id, owner_id=1, card_type="EXTRA", traits=("Dragon Ball",))
            for i, card_id in enumerate(dragon_ball_ids)
        ],
        CardInstance(instance_id=990090, card_id=951100, owner_id=1, card_type="EXTRA", traits=("Desire",)),
    ]
    hand_before = len(state.players[1].hand)
    deck_before = len(state.players[1].deck)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.awakened is True
    assert len(state.players[1].hand) == hand_before + 1
    assert all(card.card_id not in dragon_ball_ids for card in state.players[1].drop)
    assert len(state.players[1].deck) == deck_before - 1 + len(dragon_ball_ids)
    assert state.players[1].deck[-len(dragon_ball_ids) :] == dragon_ball_ids
    assert any(cp.name == "leader_wished" for cp in state.checkpoints)


def test_phase4_owner_leader_wished_can_trigger_owner_auto_draw() -> None:
    engine = RulesEngine(
        effect_rules={
            952000: [
                {
                    "trigger": "owner_leader_wished",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    engine._card_cache[(1, "back")] = CardRuntimeData(card_name="Wish Back", power=20000, card_type="LEADER", color="Black")
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.skill_text_raw = (
        "[Wish] When your life is at 3 or less or there are 7 [Dragon Ball] cards in your Drop Area: "
        "Draw 1 card, then place all [Dragon Ball] cards from your Drop Area at the bottom of your deck in any order and flip this card over."
    )
    state.players[1].leader_area.has_awaken = False
    state.players[1].leader_area.awakened = False
    state.players[1].life = state.players[1].life[:3]
    watcher = CardInstance(instance_id=990091, card_id=952000, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].battle_area = [watcher]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=watcher)
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.awakened is True
    assert len(state.players[1].hand) == hand_before + 2
    assert any(cp.name == "leader_wished" for cp in state.checkpoints)
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_z_awaken_can_replace_awakened_leader_from_face_up_z_deck() -> None:
    engine = RulesEngine()
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="Vegeta Front", card_type="LEADER", color="Yellow", has_awaken=True)
    engine._card_cache[(1, "back")] = CardRuntimeData(
        card_name="SS Vegeta, Fighting Instincts",
        card_type="LEADER",
        color="Yellow",
        traits=("Saiyan",),
        characters=("Vegeta",),
    )
    engine._card_cache[(990201, "front")] = CardRuntimeData(
        card_name="SS Vegeta, Z-Awakened",
        card_type="Z-LEADER",
        color="Yellow",
        z_energy_cost=1,
        skill_text_raw="[Z-Awaken](Yellow), when your life is at 3 or less: {SS Vegeta, Fighting Instincts}.",
        traits=("Saiyan",),
        characters=("Vegeta",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[990201],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    engine._apply_leader_back_side(state.players[1].leader_area)
    state.players[1].life = state.players[1].life[:3]
    state.players[1].energy = [
        CardInstance(instance_id=990092, card_id=952100, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]
    state.players[1].z_energy = [
        CardInstance(instance_id=990093, card_id=952101, owner_id=1, card_type="Z-ENERGY", color="Yellow"),
    ]
    state.players[1].z_deck[0].face_up = True

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.Z_AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.card_id == 990201
    assert state.players[1].leader_area.card_type == "Z-LEADER"
    assert not state.players[1].z_deck
    assert len(state.players[1].z_energy) == 0
    assert any(cp.name == "leader_z_awakened" for cp in state.checkpoints)


def test_phase4_union_absorb_can_promote_from_deck_on_top_of_source() -> None:
    engine = RulesEngine(
        effect_rules={
            990302: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = (
        "[Union Absorb][Once per turn](2), if your Leader Card is a ≪Namekian≫ card, "
        "you have 3 or more energy, and you choose 1 ≪Namekian≫ card in your hand or Battle Area "
        "and place it under this card: Play up to 1 green <Piccolo> card with an energy cost of 4 "
        "on top of this card from your deck, then shuffle your deck."
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(
        card_name="Piccolo Leader",
        card_type="LEADER",
        color="Green",
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990300, "front")] = CardRuntimeData(
        card_name="Piccolo Host",
        card_type="BATTLE",
        color="Green",
        energy_cost=2,
        skill_text_raw=union_text,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990301, "front")] = CardRuntimeData(
        card_name="Namekian Material",
        card_type="BATTLE",
        color="Green",
        energy_cost=1,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990302, "front")] = CardRuntimeData(
        card_name="Piccolo Union",
        card_type="BATTLE",
        color="Green",
        energy_cost=4,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990310,
            card_id=990300,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            energy_cost=2,
            skill_text_raw=union_text,
            traits=("Namekian",),
            characters=("Piccolo",),
        )
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=990311,
            card_id=990301,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            energy_cost=1,
            traits=("Namekian",),
            characters=("Piccolo",),
        )
    ]
    state.players[1].deck = [991000, 990302, 991001, 991002]
    state.players[1].energy = [
        CardInstance(instance_id=990312, card_id=990400, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990313, card_id=990401, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990314, card_id=990402, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_ABSORB)
    state = engine.apply_action(state, action)

    promoted = state.players[1].battle_area[0]
    assert promoted.card_id == 990302
    assert promoted.stacked_card_ids == (990301, 990300)
    assert len(state.players[1].hand) == hand_before
    assert len(state.players[1].deck) == 2
    assert sum(1 for card in state.players[1].energy if card.resting) == 2
    assert any(cp.name == "union_absorb" for cp in state.checkpoints)
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)
    assert not any(a.action_type == ActionType.UNION_ABSORB for a in engine.get_legal_actions(state, 1))


def test_phase4_owner_union_absorb_activated_can_trigger_owner_auto_draw() -> None:
    engine = RulesEngine(
        effect_rules={
            990320: [
                {
                    "trigger": "owner_union_absorb_activated",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = (
        "[Union Absorb][Once per turn](2), if your Leader Card is a ≪Namekian≫ card, "
        "you have 3 or more energy, and you choose 1 ≪Namekian≫ card in your hand or Battle Area "
        "and place it under this card: Play up to 1 green <Piccolo> card with an energy cost of 4 "
        "on top of this card from your deck, then shuffle your deck."
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(
        card_name="Piccolo Leader",
        card_type="LEADER",
        color="Green",
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990300, "front")] = CardRuntimeData(
        card_name="Piccolo Host",
        card_type="BATTLE",
        color="Green",
        energy_cost=2,
        skill_text_raw=union_text,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990301, "front")] = CardRuntimeData(
        card_name="Namekian Material",
        card_type="BATTLE",
        color="Green",
        energy_cost=1,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990302, "front")] = CardRuntimeData(
        card_name="Piccolo Union",
        card_type="BATTLE",
        color="Green",
        energy_cost=4,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990320, "front")] = CardRuntimeData(
        card_name="Union Watcher",
        card_type="BATTLE",
        color="Green",
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    host = CardInstance(
        instance_id=990321,
        card_id=990300,
        owner_id=1,
        card_type="BATTLE",
        color="Green",
        energy_cost=2,
        skill_text_raw=union_text,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    watcher = CardInstance(instance_id=990322, card_id=990320, owner_id=1, card_type="BATTLE", color="Green")
    state.players[1].battle_area = [host, watcher]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=watcher)
    state.players[1].hand = [
        CardInstance(
            instance_id=990323,
            card_id=990301,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            energy_cost=1,
            traits=("Namekian",),
            characters=("Piccolo",),
        )
    ]
    state.players[1].deck = [991100, 990302, 991101, 991102]
    state.players[1].energy = [
        CardInstance(instance_id=990324, card_id=990410, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990325, card_id=990411, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990326, card_id=990412, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_ABSORB)
    state = engine.apply_action(state, action)

    assert len(state.players[1].hand) == hand_before
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_self_played_using_union_absorb_can_trigger_auto_draw() -> None:
    engine = RulesEngine(
        effect_rules={
            990343: [
                {
                    "trigger": "self_played_using_union_absorb",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = (
        "[Union Absorb][Once per turn](2), if your Leader Card is a ≪Namekian≫ card, "
        "you have 3 or more energy, and you choose 1 ≪Namekian≫ card in your hand or Battle Area "
        "and place it under this card: Play up to 1 green <Piccolo> card with an energy cost of 4 "
        "on top of this card from your deck, then shuffle your deck."
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(
        card_name="Piccolo Leader",
        card_type="LEADER",
        color="Green",
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990343, "front")] = CardRuntimeData(
        card_name="Absorb Trigger Body",
        card_type="BATTLE",
        color="Green",
        energy_cost=4,
        skill_text_raw=union_text,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990344, "front")] = CardRuntimeData(
        card_name="Absorb Host",
        card_type="BATTLE",
        color="Green",
        energy_cost=2,
        skill_text_raw=union_text,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990345, "front")] = CardRuntimeData(
        card_name="Namekian Material",
        card_type="BATTLE",
        color="Green",
        energy_cost=1,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990346,
            card_id=990344,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            energy_cost=2,
            skill_text_raw=union_text,
            traits=("Namekian",),
            characters=("Piccolo",),
        )
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=990347,
            card_id=990345,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            energy_cost=1,
            traits=("Namekian",),
            characters=("Piccolo",),
        )
    ]
    state.players[1].deck = [991200, 990343, 991201]
    state.players[1].energy = [
        CardInstance(instance_id=990348, card_id=990420, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990349, card_id=990421, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990350, card_id=990422, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_ABSORB)
    state = engine.apply_action(state, action)

    assert len(state.players[1].hand) == hand_before
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_owner_other_battle_played_using_union_absorb_can_trigger_owner_auto_draw() -> None:
    engine = RulesEngine(
        effect_rules={
            990351: [
                {
                    "trigger": "owner_other_battle_played_using_union_absorb",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = (
        "[Union Absorb][Once per turn](2), if your Leader Card is a ≪Namekian≫ card, "
        "you have 3 or more energy, and you choose 1 ≪Namekian≫ card in your hand or Battle Area "
        "and place it under this card: Play up to 1 green <Piccolo> card with an energy cost of 4 "
        "on top of this card from your deck, then shuffle your deck."
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(
        card_name="Piccolo Leader",
        card_type="LEADER",
        color="Green",
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990343, "front")] = CardRuntimeData(
        card_name="Absorb Union",
        card_type="BATTLE",
        color="Green",
        energy_cost=4,
        skill_text_raw=union_text,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990344, "front")] = CardRuntimeData(
        card_name="Absorb Host",
        card_type="BATTLE",
        color="Green",
        energy_cost=2,
        skill_text_raw=union_text,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990345, "front")] = CardRuntimeData(
        card_name="Namekian Material",
        card_type="BATTLE",
        color="Green",
        energy_cost=1,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990351, "front")] = CardRuntimeData(
        card_name="Absorb Watcher",
        card_type="BATTLE",
        color="Green",
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    host = CardInstance(
        instance_id=990352,
        card_id=990344,
        owner_id=1,
        card_type="BATTLE",
        color="Green",
        energy_cost=2,
        skill_text_raw=union_text,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    watcher = CardInstance(instance_id=990353, card_id=990351, owner_id=1, card_type="BATTLE", color="Green")
    state.players[1].battle_area = [host, watcher]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=watcher)
    state.players[1].hand = [
        CardInstance(
            instance_id=990354,
            card_id=990345,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            energy_cost=1,
            traits=("Namekian",),
            characters=("Piccolo",),
        )
    ]
    state.players[1].deck = [991300, 990343, 991301]
    state.players[1].energy = [
        CardInstance(instance_id=990355, card_id=990430, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990356, card_id=990431, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990357, card_id=990432, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_ABSORB)
    state = engine.apply_action(state, action)

    assert len(state.players[1].hand) == hand_before
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_owner_union_absorb_activated_can_place_top_deck_under_self_and_rest_opponent_battle() -> None:
    engine = RulesEngine(
        effect_rules={
            990360: [
                {
                    "trigger": "owner_union_absorb_activated",
                    "handler_id": "auto_place_top_deck_under_self_and_switch_up_to_n_opponent_battle_rest_on_union_absorb",
                    "handler_params": {
                        "max_targets": 1,
                        "trigger_required_traits": "Namekian",
                    },
                }
            ]
        }
    )
    union_text = (
        "[Union Absorb][Once per turn](2), if your Leader Card is a ≪Namekian≫ card, "
        "you have 3 or more energy, and you choose 1 ≪Namekian≫ card in your hand or Battle Area "
        "and place it under this card: Play up to 1 green <Piccolo> card with an energy cost of 4 "
        "on top of this card from your deck, then shuffle your deck."
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(
        card_name="Piccolo Leader",
        card_type="LEADER",
        color="Green",
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990360, "front")] = CardRuntimeData(
        card_name="Absorb Follow-up Watcher",
        card_type="UNISON",
        color="Yellow",
    )
    engine._card_cache[(990361, "front")] = CardRuntimeData(
        card_name="Absorb Host",
        card_type="BATTLE",
        color="Green",
        energy_cost=2,
        skill_text_raw=union_text,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990362, "front")] = CardRuntimeData(
        card_name="Namekian Material",
        card_type="BATTLE",
        color="Green",
        energy_cost=1,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990363, "front")] = CardRuntimeData(
        card_name="Piccolo Union",
        card_type="BATTLE",
        color="Green",
        energy_cost=4,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    engine._card_cache[(990364, "front")] = CardRuntimeData(
        card_name="Top Deck Follower",
        card_type="BATTLE",
        color="Yellow",
        energy_cost=1,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    host = CardInstance(
        instance_id=990365,
        card_id=990361,
        owner_id=1,
        card_type="BATTLE",
        color="Green",
        energy_cost=2,
        skill_text_raw=union_text,
        traits=("Namekian",),
        characters=("Piccolo",),
    )
    watcher = CardInstance(instance_id=990366, card_id=990360, owner_id=1, card_type="UNISON", color="Yellow", markers=1)
    opponent_target = CardInstance(instance_id=990367, card_id=990500, owner_id=2, card_type="BATTLE", color="Red", resting=False)
    state.players[1].battle_area = [host]
    state.players[1].unison_area = [watcher]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=watcher)
    state.players[1].hand = [
        CardInstance(
            instance_id=990368,
            card_id=990362,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            energy_cost=1,
            traits=("Namekian",),
            characters=("Piccolo",),
        )
    ]
    state.players[1].deck = [990364, 991400, 990363, 991401]
    state.players[1].energy = [
        CardInstance(instance_id=990369, card_id=990440, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990370, card_id=990441, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990371, card_id=990442, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]
    state.players[2].battle_area = [opponent_target]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_ABSORB)
    state = engine.apply_action(state, action)

    assert state.players[1].unison_area[0].stacked_card_ids == (990364,)
    assert state.players[2].battle_area[0].resting is True
    assert any(
        cp.name == "effect_auto_place_top_deck_under_self_and_switch_up_to_n_opponent_battle_rest_on_union_absorb"
        for cp in state.checkpoints
    )


def test_phase4_union_absorb_can_use_material_from_under_leader() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union Absorb][Once per turn] Choose 1 card under your ≪Majin≫ Leader Card and place it under this card: "
        "Play up to 1 mono-green <Majin Buu> card with an energy cost of 4 and 15000 power from your deck or Drop Area "
        "on top of this card, then shuffle your deck if you looked through it."
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(
        card_name="Majin Leader",
        card_type="LEADER",
        color="Green",
        traits=("Majin",),
        characters=("Majin Buu",),
    )
    engine._card_cache[(990340, "front")] = CardRuntimeData(
        card_name="Majin Host",
        card_type="BATTLE",
        color="Green",
        skill_text_raw=union_text,
        traits=("Majin",),
        characters=("Majin Buu",),
    )
    engine._card_cache[(990341, "front")] = CardRuntimeData(
        card_name="Leader Under Card",
        card_type="BATTLE",
        color="Green",
        energy_cost=2,
        traits=("Majin",),
        characters=("Majin Buu",),
    )
    engine._card_cache[(990342, "front")] = CardRuntimeData(
        card_name="Majin Union",
        card_type="BATTLE",
        color="Green",
        energy_cost=4,
        traits=("Majin",),
        characters=("Majin Buu",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.stacked_card_ids = (990341,)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990343,
            card_id=990340,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            skill_text_raw=union_text,
            traits=("Majin",),
            characters=("Majin Buu",),
        )
    ]
    state.players[1].drop = [
        CardInstance(
            instance_id=990344,
            card_id=990342,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            energy_cost=4,
            traits=("Majin",),
            characters=("Majin Buu",),
        )
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_ABSORB)
    state = engine.apply_action(state, action)

    promoted = state.players[1].battle_area[0]
    assert promoted.card_id == 990342
    assert promoted.stacked_card_ids == (990341, 990340)
    assert state.players[1].leader_area.stacked_card_ids == ()


def test_phase4_union_absorb_can_use_warp_material_and_promote_from_hand() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union Absorb](4), place 1 <Towa> from your Warp under this card: "
        "If your Leader Card is an ≪Android≫ or <Towa>, choose 1 <Mira> with an energy cost of 7 "
        "in your hand or Warp and play it on top of this card in Active Mode."
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(
        card_name="Android Leader",
        card_type="LEADER",
        color="Black",
        traits=("Android",),
        characters=("Towa",),
    )
    engine._card_cache[(990350, "front")] = CardRuntimeData(
        card_name="Union Host",
        card_type="BATTLE",
        color="Black",
        energy_cost=4,
        skill_text_raw=union_text,
        traits=("Android",),
        characters=("Mira",),
    )
    engine._card_cache[(990351, "front")] = CardRuntimeData(
        card_name="Towa Material",
        card_type="BATTLE",
        color="Black",
        energy_cost=2,
        characters=("Towa",),
    )
    engine._card_cache[(990352, "front")] = CardRuntimeData(
        card_name="Mira Union",
        card_type="BATTLE",
        color="Black",
        energy_cost=7,
        characters=("Mira",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990353,
            card_id=990350,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=4,
            skill_text_raw=union_text,
            traits=("Android",),
            characters=("Mira",),
        )
    ]
    state.players[1].warp = [
        CardInstance(
            instance_id=990354,
            card_id=990351,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=2,
            characters=("Towa",),
        )
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=990355,
            card_id=990352,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=7,
            characters=("Mira",),
        )
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990356, card_id=990420, owner_id=1, card_type="ENERGY", color="Black", resting=False),
        CardInstance(instance_id=990357, card_id=990421, owner_id=1, card_type="ENERGY", color="Black", resting=False),
        CardInstance(instance_id=990358, card_id=990422, owner_id=1, card_type="ENERGY", color="Black", resting=False),
        CardInstance(instance_id=990359, card_id=990423, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_ABSORB)
    state = engine.apply_action(state, action)

    promoted = state.players[1].battle_area[0]
    assert promoted.card_id == 990352
    assert promoted.resting is False
    assert promoted.stacked_card_ids == (990351, 990350)
    assert len(state.players[1].hand) == 0
    assert len(state.players[1].warp) == 0


def test_phase4_union_absorb_can_pay_extra_hand_discard_cost_before_promoting_from_deck() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union Absorb] Choose 1 <Towa> card in your Warp, place it under this card, "
        "then choose 1 card in your hand and discard it: "
        "Choose 1 <Mira> card with an energy cost of 6 in your deck, play it on top of this card, then shuffle your deck."
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(
        card_name="Android Leader",
        card_type="LEADER",
        color="Black",
        traits=("Android",),
        characters=("Towa",),
    )
    engine._card_cache[(990372, "front")] = CardRuntimeData(
        card_name="Discard Absorb Host",
        card_type="BATTLE",
        color="Black",
        energy_cost=4,
        skill_text_raw=union_text,
        traits=("Android",),
        characters=("Mira",),
    )
    engine._card_cache[(990373, "front")] = CardRuntimeData(
        card_name="Towa Material",
        card_type="BATTLE",
        color="Black",
        energy_cost=2,
        characters=("Towa",),
    )
    engine._card_cache[(990374, "front")] = CardRuntimeData(
        card_name="Mira Union",
        card_type="BATTLE",
        color="Black",
        energy_cost=6,
        characters=("Mira",),
    )
    engine._card_cache[(990375, "front")] = CardRuntimeData(
        card_name="Discard Fodder",
        card_type="BATTLE",
        color="Black",
        energy_cost=1,
        characters=("Fodder",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990376,
            card_id=990372,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=4,
            skill_text_raw=union_text,
            traits=("Android",),
            characters=("Mira",),
        )
    ]
    state.players[1].warp = [
        CardInstance(
            instance_id=990377,
            card_id=990373,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=2,
            characters=("Towa",),
        )
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=990378,
            card_id=990375,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=1,
            characters=("Fodder",),
        )
    ]
    state.players[1].deck = [990374, 991500, 991501]
    state.players[1].energy = [
        CardInstance(instance_id=990379, card_id=990450, owner_id=1, card_type="ENERGY", color="Black", resting=False),
        CardInstance(instance_id=990380, card_id=990451, owner_id=1, card_type="ENERGY", color="Black", resting=False),
        CardInstance(instance_id=990381, card_id=990452, owner_id=1, card_type="ENERGY", color="Black", resting=False),
        CardInstance(instance_id=990382, card_id=990453, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_ABSORB)
    state = engine.apply_action(state, action)

    promoted = state.players[1].battle_area[0]
    assert promoted.card_id == 990374
    assert promoted.stacked_card_ids == (990373, 990372)
    assert len(state.players[1].warp) == 0
    assert len(state.players[1].hand) == 0
    assert any(card.card_id == 990375 for card in state.players[1].drop)


def test_phase4_union_absorb_can_use_named_android_pair_from_drop_area() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union Absorb](Green)(Yellow), choose 1 <Android 14> card and 1 <Android 15> card in your Drop Area "
        "and place them under this card: Choose up to 1 <Android 13> "
        "card in your hand and play it on top of this card."
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(
        card_name="Android Leader",
        card_type="LEADER",
        color="Green/Yellow",
        traits=("Android",),
        characters=("Android Leader",),
    )
    engine._card_cache[(990383, "front")] = CardRuntimeData(
        card_name="Android Host",
        card_type="BATTLE",
        color="Green/Yellow",
        energy_cost=4,
        skill_text_raw=union_text,
        traits=("Android",),
        characters=("Absorb Host",),
    )
    engine._card_cache[(990384, "front")] = CardRuntimeData(
        card_name="Android 14 Material",
        card_type="BATTLE",
        color="Green",
        energy_cost=2,
        characters=("Android 14",),
    )
    engine._card_cache[(990385, "front")] = CardRuntimeData(
        card_name="Android 15 Material",
        card_type="BATTLE",
        color="Yellow",
        energy_cost=2,
        characters=("Android 15",),
    )
    engine._card_cache[(990386, "front")] = CardRuntimeData(
        card_name="Android 13 Union",
        card_type="BATTLE",
        color="Red",
        energy_cost=7,
        characters=("Android 13",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990387,
            card_id=990383,
            owner_id=1,
            card_type="BATTLE",
            color="Green/Yellow",
            energy_cost=4,
            skill_text_raw=union_text,
            traits=("Android",),
            characters=("Absorb Host",),
        )
    ]
    state.players[1].drop = [
        CardInstance(
            instance_id=990388,
            card_id=990384,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            energy_cost=2,
            characters=("Android 14",),
        ),
        CardInstance(
            instance_id=990389,
            card_id=990385,
            owner_id=1,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=2,
            characters=("Android 15",),
        ),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=990390,
            card_id=990386,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            energy_cost=7,
            characters=("Android 13",),
        )
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990391, card_id=990454, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990392, card_id=990455, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_ABSORB)
    state = engine.apply_action(state, action)

    promoted = state.players[1].battle_area[0]
    assert promoted.card_id == 990386
    assert promoted.stacked_card_ids == (990384, 990385, 990383)
    assert len(state.players[1].drop) == 0
    assert len(state.players[1].hand) == 0


def test_phase4_union_absorb_can_use_named_android_pair_from_hand_and_drop() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union Absorb](Green)(Yellow), choose 1 <Android 14> card and 1 <Android 15> card from your hand or Drop Area "
        "and place them under this card: Choose up to 1 <Android 13> "
        "card in your Drop Area and play it on top of this card."
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(
        card_name="Android Leader",
        card_type="LEADER",
        color="Green/Yellow",
        traits=("Android",),
        characters=("Android Leader",),
    )
    engine._card_cache[(990393, "front")] = CardRuntimeData(
        card_name="Mixed Android Host",
        card_type="BATTLE",
        color="Green/Yellow",
        energy_cost=4,
        skill_text_raw=union_text,
        traits=("Android",),
        characters=("Absorb Host",),
    )
    engine._card_cache[(990394, "front")] = CardRuntimeData(
        card_name="Android 14 Material",
        card_type="BATTLE",
        color="Green",
        energy_cost=2,
        characters=("Android 14",),
    )
    engine._card_cache[(990395, "front")] = CardRuntimeData(
        card_name="Android 15 Material",
        card_type="BATTLE",
        color="Yellow",
        energy_cost=2,
        characters=("Android 15",),
    )
    engine._card_cache[(990396, "front")] = CardRuntimeData(
        card_name="Android 13 Union",
        card_type="BATTLE",
        color="Red",
        energy_cost=7,
        characters=("Android 13",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990397,
            card_id=990393,
            owner_id=1,
            card_type="BATTLE",
            color="Green/Yellow",
            energy_cost=4,
            skill_text_raw=union_text,
            traits=("Android",),
            characters=("Absorb Host",),
        )
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=990398,
            card_id=990394,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            energy_cost=2,
            characters=("Android 14",),
        )
    ]
    state.players[1].drop = [
        CardInstance(
            instance_id=990399,
            card_id=990395,
            owner_id=1,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=2,
            characters=("Android 15",),
        ),
        CardInstance(
            instance_id=990400,
            card_id=990396,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            energy_cost=7,
            characters=("Android 13",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990401, card_id=990456, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990402, card_id=990457, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_ABSORB)
    state = engine.apply_action(state, action)

    promoted = state.players[1].battle_area[0]
    assert promoted.card_id == 990396
    assert promoted.stacked_card_ids == (990394, 990395, 990393)
    assert len(state.players[1].hand) == 0
    assert len(state.players[1].drop) == 0


def test_phase4_union_absorb_can_use_choose_one_each_materials_from_hand_and_battle() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union Absorb][Once per turn](Red), choose 1 each of <Bizu> and <Ribet> from your hand and/or Battle Area "
        "and place them under this card: Play up to 1 <Super Sigma> card from your deck or Drop Area on top of this card, "
        "then shuffle your deck if you looked through it."
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(
        card_name="Dr. Myuu",
        card_type="LEADER",
        color="Red",
        characters=("Dr. Myuu",),
    )
    engine._card_cache[(990403, "front")] = CardRuntimeData(
        card_name="Sigma Host",
        card_type="BATTLE",
        color="Red",
        energy_cost=3,
        skill_text_raw=union_text,
        characters=("Machine Mutant Host",),
    )
    engine._card_cache[(990404, "front")] = CardRuntimeData(
        card_name="Bizu",
        card_type="BATTLE",
        color="Red",
        energy_cost=2,
        characters=("Bizu",),
    )
    engine._card_cache[(990405, "front")] = CardRuntimeData(
        card_name="Ribet",
        card_type="BATTLE",
        color="Red",
        energy_cost=2,
        characters=("Ribet",),
    )
    engine._card_cache[(990406, "front")] = CardRuntimeData(
        card_name="Super Sigma",
        card_type="BATTLE",
        color="Red",
        energy_cost=6,
        characters=("Super Sigma",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990407,
            card_id=990403,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            energy_cost=3,
            skill_text_raw=union_text,
            characters=("Machine Mutant Host",),
        ),
        CardInstance(
            instance_id=990408,
            card_id=990405,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            energy_cost=2,
            characters=("Ribet",),
        ),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=990409,
            card_id=990404,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            energy_cost=2,
            characters=("Bizu",),
        )
    ]
    state.players[1].drop = [
        CardInstance(
            instance_id=990410,
            card_id=990406,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            energy_cost=6,
            characters=("Super Sigma",),
        )
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990411, card_id=990458, owner_id=1, card_type="ENERGY", color="Red", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_ABSORB)
    state = engine.apply_action(state, action)

    promoted = state.players[1].battle_area[0]
    assert promoted.card_id == 990406
    assert promoted.stacked_card_ids == (990404, 990405, 990403)
    assert len(state.players[1].hand) == 0
    assert len(state.players[1].drop) == 0
    assert len(state.players[1].battle_area) == 1


def test_phase4_union_absorb_can_choose_one_of_multiple_named_targets_from_deck_or_hand() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union Absorb](Yellow), choose 1 <Vegeta: GT> card in your hand or your Drop Area and place it under this card: "
        "Choose up to 1 {Baby Vegeta, an Unfair Choice} or {Super Baby 1, All-Consuming Terror} in your deck or hand, "
        "play it in Active Mode on top of this card, then shuffle your deck if you looked through it."
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(
        card_name="Baby Leader",
        card_type="LEADER",
        color="Yellow",
        characters=("Baby",),
    )
    engine._card_cache[(990412, "front")] = CardRuntimeData(
        card_name="Baby Host",
        card_type="BATTLE",
        color="Yellow",
        energy_cost=3,
        skill_text_raw=union_text,
        characters=("Baby",),
    )
    engine._card_cache[(990413, "front")] = CardRuntimeData(
        card_name="Vegeta: GT Material",
        card_type="BATTLE",
        color="Yellow",
        energy_cost=2,
        characters=("Vegeta: GT",),
    )
    engine._card_cache[(990414, "front")] = CardRuntimeData(
        card_name="Super Baby 1, All-Consuming Terror",
        card_type="BATTLE",
        color="Yellow",
        energy_cost=4,
        characters=("Baby",),
    )
    engine._card_cache[(990415, "front")] = CardRuntimeData(
        card_name="Baby Vegeta, an Unfair Choice",
        card_type="BATTLE",
        color="Yellow",
        energy_cost=4,
        characters=("Baby",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990416,
            card_id=990412,
            owner_id=1,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=3,
            skill_text_raw=union_text,
            characters=("Baby",),
            resting=True,
        )
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=990417,
            card_id=990413,
            owner_id=1,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=2,
            characters=("Vegeta: GT",),
        )
    ]
    state.players[1].deck = [990500, 990501]
    state.players[1].hand.append(
        CardInstance(
            instance_id=990418,
            card_id=990414,
            owner_id=1,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=4,
            characters=("Baby",),
        )
    )
    state.players[1].energy = [
        CardInstance(instance_id=990419, card_id=990459, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_ABSORB)
    state = engine.apply_action(state, action)

    promoted = state.players[1].battle_area[0]
    assert promoted.card_id == 990414
    assert promoted.resting is False
    assert promoted.stacked_card_ids == (990413, 990412)
    assert len(state.players[1].hand) == 0


def test_phase4_union_absorb_can_optionally_place_material_under_self_then_play_non_top_target() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union Absorb][Limit 1](Green)/(Yellow), if your Leader Card is an ≪Android≫ card and you have 4 or more energy: "
        "You may place up to 1 <Cell> card from your deck or Drop Area under this card. If you do, choose up to 1 "
        "{Super 17, Cell Absorbed} or {Super 17, Hell's Storm Unleashed} in your deck or hand, play it with its keyword "
        "skills negated for the turn, then shuffle your deck if you looked through it."
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(
        card_name="Android Leader",
        card_type="LEADER",
        color="Green/Yellow",
        traits=("Android",),
        characters=("Android Leader",),
    )
    engine._card_cache[(990420, "front")] = CardRuntimeData(
        card_name="Super 17 Host",
        card_type="BATTLE",
        color="Green/Yellow",
        energy_cost=4,
        skill_text_raw=union_text,
        traits=("Android",),
        characters=("Super 17 Host",),
    )
    engine._card_cache[(990421, "front")] = CardRuntimeData(
        card_name="Cell Material",
        card_type="BATTLE",
        color="Green",
        energy_cost=4,
        characters=("Cell",),
    )
    engine._card_cache[(990422, "front")] = CardRuntimeData(
        card_name="Super 17, Cell Absorbed",
        card_type="BATTLE",
        color="Green/Yellow",
        energy_cost=8,
        characters=("Super 17",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990423,
            card_id=990420,
            owner_id=1,
            card_type="BATTLE",
            color="Green/Yellow",
            energy_cost=4,
            skill_text_raw=union_text,
            traits=("Android",),
            characters=("Super 17 Host",),
        )
    ]
    state.players[1].drop = [
        CardInstance(
            instance_id=990424,
            card_id=990421,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            energy_cost=4,
            characters=("Cell",),
        )
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=990425,
            card_id=990422,
            owner_id=1,
            card_type="BATTLE",
            color="Green/Yellow",
            energy_cost=8,
            characters=("Super 17",),
        )
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990426, card_id=990460, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990427, card_id=990461, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
        CardInstance(instance_id=990428, card_id=990462, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990429, card_id=990463, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_ABSORB)
    state = engine.apply_action(state, action)

    host = next(card for card in state.players[1].battle_area if card.card_id == 990420)
    played = next(card for card in state.players[1].battle_area if card.card_id == 990422)
    assert host.stacked_card_ids == (990421,)
    assert played.instance_id != host.instance_id
    assert len(state.players[1].battle_area) == 2
    assert len(state.players[1].drop) == 0
    assert len(state.players[1].hand) == 0


def test_phase4_union_absorb_can_play_target_with_keyword_skills_negated_but_non_keyword_auto_still_works() -> None:
    engine = RulesEngine(
        effect_rules={
            990432: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = (
        "[Union Absorb][Limit 1](Green)/(Yellow), if your Leader Card is an ≪Android≫ card and you have 4 or more energy: "
        "You may place up to 1 <Cell> card from your deck or Drop Area under this card. If you do, choose up to 1 "
        "{Super 17, Cell Absorbed} or {Super 17, Hell's Storm Unleashed} in your deck or hand, play it with its keyword "
        "skills negated for the turn, then shuffle your deck if you looked through it."
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(
        card_name="Android Leader",
        card_type="LEADER",
        color="Green/Yellow",
        traits=("Android",),
        characters=("Android Leader",),
    )
    engine._card_cache[(990430, "front")] = CardRuntimeData(
        card_name="Super 17 Host",
        card_type="BATTLE",
        color="Green/Yellow",
        energy_cost=4,
        skill_text_raw=union_text,
        traits=("Android",),
        characters=("Super 17 Host",),
    )
    engine._card_cache[(990431, "front")] = CardRuntimeData(
        card_name="Cell Material",
        card_type="BATTLE",
        color="Green",
        energy_cost=4,
        characters=("Cell",),
    )
    engine._card_cache[(990432, "front")] = CardRuntimeData(
        card_name="Super 17, Hell's Storm Unleashed",
        card_type="BATTLE",
        color="Green/Yellow",
        energy_cost=8,
        characters=("Super 17",),
        keywords=("Barrier", "Deflect"),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990433,
            card_id=990430,
            owner_id=1,
            card_type="BATTLE",
            color="Green/Yellow",
            energy_cost=4,
            skill_text_raw=union_text,
            traits=("Android",),
            characters=("Super 17 Host",),
        )
    ]
    state.players[1].drop = [
        CardInstance(
            instance_id=990434,
            card_id=990431,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            energy_cost=4,
            characters=("Cell",),
        )
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=990435,
            card_id=990432,
            owner_id=1,
            card_type="BATTLE",
            color="Green/Yellow",
            energy_cost=8,
            characters=("Super 17",),
            keywords=("Barrier", "Deflect"),
        )
    ]
    state.players[1].deck = [990700, 990701]
    state.players[1].energy = [
        CardInstance(instance_id=990436, card_id=990464, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990437, card_id=990465, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
        CardInstance(instance_id=990438, card_id=990466, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990439, card_id=990467, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_ABSORB)
    state = engine.apply_action(state, action)

    played = next(card for card in state.players[1].battle_area if card.card_id == 990432)
    assert played.temporary_keyword_skills_negated is True
    assert engine._card_has_keyword(played, "Barrier") is False
    assert engine._card_has_keyword(played, "Deflect") is False
    assert played.temporary_skills_negated is False
    assert len(state.players[1].hand) == 1


def test_phase4_union_fusion_can_play_from_hand_using_matching_materials() -> None:
    engine = RulesEngine(
        effect_rules={
            990361: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = (
        "[Union-Fusion](Blue)(Blue): <Son Goten> and <Trunks: Youth> "
        "(Place 1 each of the specified card with the same power from your hand into your Drop Area and play this card.)"
    )
    engine._card_cache[(990361, "front")] = CardRuntimeData(
        card_name="Fusion Body",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Gotenks",),
    )
    engine._card_cache[(990362, "front")] = CardRuntimeData(
        card_name="Son Goten Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goten",),
    )
    engine._card_cache[(990363, "front")] = CardRuntimeData(
        card_name="Trunks Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Trunks: Youth",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990364,
            card_id=990361,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Gotenks",),
        ),
        CardInstance(
            instance_id=990365,
            card_id=990362,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goten",),
        ),
        CardInstance(
            instance_id=990366,
            card_id=990363,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Trunks: Youth",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990367, card_id=990430, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990368, card_id=990431, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION)
    state = engine.apply_action(state, action)

    assert state.players[1].battle_area[-1].card_id == 990361
    assert len(state.players[1].drop) == 2
    assert {card.card_id for card in state.players[1].drop} == {990362, 990363}
    assert len(state.players[1].hand) == hand_before - 3 + 1
    assert sum(1 for card in state.players[1].energy if card.resting) == 2
    assert any(cp.name == "union_fusion" for cp in state.checkpoints)
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_union_fusion_combo_support_can_bottom_deck_opponent_hand_and_negate_self_for_battle() -> None:
    engine = RulesEngine(
        effect_rules={
            8142: [
                {
                    "trigger": "owner_opponent_card_comboed",
                    "handler_id": "auto_pay_z_energy_bottom_deck_opponent_hand_on_opponent_combo_and_negate_self_for_battle",
                    "handler_params": {"amount": 1, "negate_self_skill_for_battle": True},
                }
            ]
        },
        skill_cost_rules={
            8142: {
                "auto_on_opponent_combo_battle": [
                    {"kind": "send_owner_z_energy_to_drop", "amount": 2},
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=991300, card_id=300, owner_id=1, card_type="BATTLE", color="Blue", power=15000),
            CardInstance(instance_id=991301, card_id=301, owner_id=1, card_type="BATTLE", color="Blue", power=15000),
            CardInstance(instance_id=991302, card_id=8142, owner_id=1, card_type="BATTLE", color="Blue", power=35000),
        ]
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[2])
    state.players[1].z_energy = [
        CardInstance(instance_id=991310 + i, card_id=9100 + i, owner_id=1, card_type="BATTLE", color="Blue")
        for i in range(4)
    ]
    state.players[2].hand = [
        CardInstance(instance_id=991320, card_id=9320, owner_id=2, card_type="BATTLE", combo_cost=0, combo_power=5000),
        CardInstance(instance_id=991321, card_id=9321, owner_id=2, card_type="EXTRA"),
        CardInstance(instance_id=991322, card_id=9322, owner_id=2, card_type="BATTLE", combo_cost=0, combo_power=5000),
    ]

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    combo = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.COMBO_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, combo)

    assert len(state.players[1].z_energy) == 2
    assert state.players[2].deck[-1] == 9321
    assert any(cp.name == "effect_battle_skill_activation_restriction_applied" for cp in state.checkpoints)

    combo = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.COMBO_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, combo)
    assert len(state.players[1].z_energy) == 2
    blocked = [row for row in state.effect_resolutions if row.reason == "temporary_skill_activation_restricted"]
    assert blocked

    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    assert not state.active_battle_skill_activation_restrictions

    state.players[1].z_energy = [
        CardInstance(instance_id=991330 + i, card_id=9130 + i, owner_id=1, card_type="BATTLE", color="Blue")
        for i in range(2)
    ]
    state.players[2].hand = [
        CardInstance(instance_id=991340, card_id=9340, owner_id=2, card_type="BATTLE", combo_cost=0, combo_power=5000),
        CardInstance(instance_id=991341, card_id=9341, owner_id=2, card_type="EXTRA"),
    ]
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 1 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    combo = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.COMBO_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, combo)

    assert len(state.players[1].z_energy) == 0
    assert state.players[2].deck[-1] == 9341
    assert sum(1 for cp in state.checkpoints if cp.name == "effect_auto_pay_z_energy_bottom_deck_opponent_hand_on_opponent_combo_and_negate_self_for_battle") >= 2


def test_phase4_self_combo_can_force_opponent_hand_to_bottom_deck() -> None:
    engine = RulesEngine(
        effect_rules={
            355844: [
                {
                    "trigger": "self_comboed",
                    "handler_id": "auto_opponent_bottom_decks_n_from_hand_on_combo",
                    "handler_params": {
                        "amount": 1,
                        "requires_comboed_from": "hand",
                        "requires_leader": "if your leader card is blue or green",
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].leader_area.color = "Blue"
    state.players[1].battle_area.append(
        CardInstance(instance_id=991350, card_id=350, owner_id=1, card_type="BATTLE", color="Blue", power=15000)
    )
    state.players[1].hand = [
        CardInstance(instance_id=991351, card_id=355844, owner_id=1, card_type="BATTLE", color="Blue/Green", combo_cost=0, combo_power=10000)
    ]
    state.players[2].hand = [
        CardInstance(instance_id=991360, card_id=9360, owner_id=2, card_type="EXTRA"),
        CardInstance(instance_id=991361, card_id=9361, owner_id=2, card_type="BATTLE", combo_cost=0, combo_power=5000),
    ]

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    combo = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, combo)

    assert state.effect_events[-1].name == "card_comboed"
    assert state.effect_events[-1].payload.get("comboed_from") == "hand"
    assert state.players[2].deck[-1] == 9360
    assert any(cp.name == "effect_auto_opponent_bottom_decks_n_from_hand_on_combo" for cp in state.checkpoints)


def test_phase4_self_combo_can_switch_opponent_leader_or_battle_to_rest() -> None:
    engine = RulesEngine(
        effect_rules={
            2049: [
                {
                    "trigger": "self_comboed",
                    "handler_id": "auto_switch_up_to_n_opponent_leader_or_battle_rest_on_combo",
                    "handler_params": {
                        "max_targets": 1,
                        "requires_comboed_from": "hand",
                        "target_policy": "first",
                        "requires_leader": "if your leader card is blue or yellow",
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].leader_area.color = "Yellow"
    state.players[1].battle_area.append(
        CardInstance(instance_id=991370, card_id=370, owner_id=1, card_type="BATTLE", color="Yellow", power=15000)
    )
    state.players[1].hand = [
        CardInstance(instance_id=991371, card_id=2049, owner_id=1, card_type="BATTLE", color="Blue/Yellow", combo_cost=0, combo_power=10000)
    ]
    state.players[2].battle_area.append(
        CardInstance(instance_id=991372, card_id=372, owner_id=2, card_type="BATTLE", color="Red", power=15000, resting=False)
    )
    state.players[2].leader_area.resting = False

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    combo = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, combo)

    assert state.players[2].leader_area.resting is True
    assert state.players[2].battle_area[0].resting is False
    assert any(cp.name == "effect_auto_switch_up_to_n_opponent_leader_or_battle_rest_on_combo" for cp in state.checkpoints)


def test_phase4_self_combo_can_switch_owner_multicolor_energy_to_active() -> None:
    engine = RulesEngine(
        effect_rules={
            171772: [
                {
                    "trigger": "self_comboed",
                    "handler_id": "auto_switch_up_to_n_owner_energy_active_on_combo",
                    "handler_params": {
                        "max_targets": 1,
                        "requires_comboed_from": "hand",
                        "allowed_colors": "blue,red",
                        "requires_multicolor": True,
                        "requires_leader": "if your leader card is red or blue and it's your opponent's turn",
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    attacker = CardInstance(instance_id=991380, card_id=380, owner_id=1, card_type="BATTLE", color="Red", power=15000)
    state.players[1].battle_area = [attacker]
    state.players[2].leader_area.color = "Red/Blue"
    state.players[2].hand = [
        CardInstance(instance_id=991381, card_id=171772, owner_id=2, card_type="BATTLE", color="Red/Blue", combo_cost=0, combo_power=10000)
    ]
    state.players[2].energy = [
        CardInstance(instance_id=991382, card_id=382, owner_id=2, card_type="BATTLE", color="Red/Blue", resting=True),
        CardInstance(instance_id=991383, card_id=383, owner_id=2, card_type="BATTLE", color="Blue", resting=True),
    ]
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.DEFENSE

    combo = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.COMBO_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, combo)

    assert state.effect_events[-1].name == "card_comboed"
    assert state.effect_events[-1].payload.get("comboed_from") == "hand"
    assert state.players[2].energy[0].resting is False
    assert state.players[2].energy[1].resting is True
    assert any(cp.name == "effect_auto_switch_up_to_n_owner_energy_active_on_combo" for cp in state.checkpoints)


def test_phase4_self_combo_can_place_matching_deck_card_in_drop() -> None:
    engine = RulesEngine(
        effect_rules={
            280084: [
                {
                    "trigger": "self_comboed",
                    "handler_id": "auto_place_up_to_n_from_owner_deck_into_drop_on_combo",
                    "handler_params": {
                        "max_targets": 1,
                        "requires_comboed_from": "hand",
                        "allowed_colors": "green,yellow",
                        "max_cost": 4,
                        "required_card_type": "BATTLE",
                        "requires_leader": "if your leader card is green or yellow",
                    },
                }
            ]
        }
    )
    engine._card_cache[(9401, "front")] = CardRuntimeData(card_type="BATTLE", color="Green", energy_cost=4, card_name="Match A")
    engine._card_cache[(9402, "front")] = CardRuntimeData(card_type="BATTLE", color="Blue", energy_cost=4, card_name="Miss B")
    engine._card_cache[(9403, "front")] = CardRuntimeData(card_type="BATTLE", color="Yellow", energy_cost=5, card_name="Miss C")
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].leader_area.color = "Green"
    state.players[1].battle_area.append(
        CardInstance(instance_id=991390, card_id=390, owner_id=1, card_type="BATTLE", color="Green", power=15000)
    )
    state.players[1].hand = [
        CardInstance(instance_id=991391, card_id=280084, owner_id=1, card_type="BATTLE", color="Green/Yellow", combo_cost=0, combo_power=10000)
    ]
    state.players[1].deck = [9402, 9401, 9403]

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    combo = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, combo)

    assert any(card.card_id == 9401 for card in state.players[1].drop)
    assert state.players[1].deck == [9402, 9403]
    assert any(cp.name == "effect_auto_place_up_to_n_from_owner_deck_into_drop_on_combo" for cp in state.checkpoints)


def test_phase4_owner_other_battle_played_using_union_can_trigger_owner_auto_draw() -> None:
    engine = RulesEngine(
        effect_rules={
            990370: [
                {
                    "trigger": "owner_other_battle_played_using_union",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = (
        "[Union-Fusion](Blue)(Blue): <Son Goten> and <Trunks: Youth> "
        "(Place 1 each of the specified card with the same power from your hand into your Drop Area and play this card.)"
    )
    engine._card_cache[(990361, "front")] = CardRuntimeData(
        card_name="Fusion Body",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Gotenks",),
    )
    engine._card_cache[(990362, "front")] = CardRuntimeData(
        card_name="Son Goten Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goten",),
    )
    engine._card_cache[(990363, "front")] = CardRuntimeData(
        card_name="Trunks Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Trunks: Youth",),
    )
    engine._card_cache[(990370, "front")] = CardRuntimeData(
        card_name="Union Watcher",
        card_type="BATTLE",
        color="Blue",
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    watcher = CardInstance(instance_id=990371, card_id=990370, owner_id=1, card_type="BATTLE", color="Blue")
    state.players[1].battle_area = [watcher]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=watcher)
    state.players[1].hand = [
        CardInstance(
            instance_id=990372,
            card_id=990361,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Gotenks",),
        ),
        CardInstance(
            instance_id=990373,
            card_id=990362,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goten",),
        ),
        CardInstance(
            instance_id=990374,
            card_id=990363,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Trunks: Youth",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990375, card_id=990440, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990376, card_id=990441, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION)
    state = engine.apply_action(state, action)

    assert len(state.players[1].hand) == hand_before - 3 + 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_self_played_using_union_fusion_can_trigger_auto_draw() -> None:
    engine = RulesEngine(
        effect_rules={
            990377: [
                {
                    "trigger": "self_played_using_union_fusion",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = (
        "[Union-Fusion](Blue)(Blue): <Son Goten> and <Trunks: Youth> "
        "(Place 1 each of the specified card with the same power from your hand into your Drop Area and play this card.)"
    )
    engine._card_cache[(990377, "front")] = CardRuntimeData(
        card_name="Fusion Trigger Body",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Gotenks",),
    )
    engine._card_cache[(990378, "front")] = CardRuntimeData(
        card_name="Son Goten Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goten",),
    )
    engine._card_cache[(990379, "front")] = CardRuntimeData(
        card_name="Trunks Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Trunks: Youth",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990430,
            card_id=990377,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Gotenks",),
        ),
        CardInstance(
            instance_id=990432,
            card_id=990378,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goten",),
        ),
        CardInstance(
            instance_id=990433,
            card_id=990379,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Trunks: Youth",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990434, card_id=990434, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990435, card_id=990435, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION)
    state = engine.apply_action(state, action)

    assert len(state.players[1].hand) == hand_before - 3 + 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_union_fusion_header_can_draw_two_cards_before_play_resolution() -> None:
    engine = RulesEngine()
    union_text = "[Union-Fusion](2), draw 2 cards: <Son Goku: Br> card and <Vegeta: Br> card."
    engine._card_cache[(990523, "front")] = CardRuntimeData(
        card_name="Fusion Draw Two",
        card_type="BATTLE",
        color="Blue",
        energy_cost=7,
        skill_text_raw=union_text,
        characters=("Gogeta: Br",),
    )
    engine._card_cache[(990524, "front")] = CardRuntimeData(
        card_name="Son Goku: Br Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goku: Br",),
    )
    engine._card_cache[(990525, "front")] = CardRuntimeData(
        card_name="Vegeta: Br Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Vegeta: Br",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990526,
            card_id=990523,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=7,
            skill_text_raw=union_text,
            characters=("Gogeta: Br",),
        ),
        CardInstance(
            instance_id=990527,
            card_id=990524,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goku: Br",),
        ),
        CardInstance(
            instance_id=990528,
            card_id=990525,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Vegeta: Br",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990529, card_id=990529, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990530, card_id=990530, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION)
    state = engine.apply_action(state, action)

    assert len(state.players[1].battle_area) == 1
    assert len(state.players[1].hand) == hand_before - 3 + 2


def test_phase4_union_fusion_header_can_draw_one_card_on_colored_material_line() -> None:
    engine = RulesEngine()
    union_text = "[Union-Fusion](Red)(Red)(Red)(Red), draw 1 card: Red <Son Goku: GT> and red <Vegeta: GT>."
    engine._card_cache[(990531, "front")] = CardRuntimeData(
        card_name="Fusion Draw One",
        card_type="BATTLE",
        color="Red",
        energy_cost=8,
        skill_text_raw=union_text,
        characters=("Gogeta: GT",),
    )
    engine._card_cache[(990532, "front")] = CardRuntimeData(
        card_name="Son Goku: GT Material",
        card_type="BATTLE",
        color="Red",
        power=25000,
        characters=("Son Goku: GT",),
    )
    engine._card_cache[(990533, "front")] = CardRuntimeData(
        card_name="Vegeta: GT Material",
        card_type="BATTLE",
        color="Red",
        power=25000,
        characters=("Vegeta: GT",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1100),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2100),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990534,
            card_id=990531,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            energy_cost=8,
            skill_text_raw=union_text,
            characters=("Gogeta: GT",),
        ),
        CardInstance(
            instance_id=990535,
            card_id=990532,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            power=25000,
            characters=("Son Goku: GT",),
        ),
        CardInstance(
            instance_id=990536,
            card_id=990533,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            power=25000,
            characters=("Vegeta: GT",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990537, card_id=990537, owner_id=1, card_type="ENERGY", color="Red", resting=False),
        CardInstance(instance_id=990538, card_id=990538, owner_id=1, card_type="ENERGY", color="Red", resting=False),
        CardInstance(instance_id=990539, card_id=990539, owner_id=1, card_type="ENERGY", color="Red", resting=False),
        CardInstance(instance_id=990540, card_id=990540, owner_id=1, card_type="ENERGY", color="Red", resting=False),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION)
    state = engine.apply_action(state, action)

    assert len(state.players[1].battle_area) == 1
    assert len(state.players[1].hand) == hand_before - 3 + 1


def test_phase4_owner_other_battle_played_using_union_fusion_can_trigger_owner_auto_draw() -> None:
    engine = RulesEngine(
        effect_rules={
            990436: [
                {
                    "trigger": "owner_other_battle_played_using_union_fusion",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = (
        "[Union-Fusion](Blue)(Blue): <Son Goten> and <Trunks: Youth> "
        "(Place 1 each of the specified card with the same power from your hand into your Drop Area and play this card.)"
    )
    engine._card_cache[(990437, "front")] = CardRuntimeData(
        card_name="Fusion Watched Body",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Gotenks",),
    )
    engine._card_cache[(990438, "front")] = CardRuntimeData(
        card_name="Son Goten Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goten",),
    )
    engine._card_cache[(990439, "front")] = CardRuntimeData(
        card_name="Trunks Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Trunks: Youth",),
    )
    engine._card_cache[(990436, "front")] = CardRuntimeData(
        card_name="Fusion Watcher",
        card_type="BATTLE",
        color="Blue",
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    watcher = CardInstance(instance_id=990440, card_id=990436, owner_id=1, card_type="BATTLE", color="Blue")
    state.players[1].battle_area = [watcher]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=watcher)
    state.players[1].hand = [
        CardInstance(
            instance_id=990441,
            card_id=990437,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Gotenks",),
        ),
        CardInstance(
            instance_id=990442,
            card_id=990438,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goten",),
        ),
        CardInstance(
            instance_id=990443,
            card_id=990439,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Trunks: Youth",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990444, card_id=990444, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990445, card_id=990445, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION)
    state = engine.apply_action(state, action)

    assert len(state.players[1].hand) == hand_before - 3 + 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_union_fusion_can_pay_circled_generic_cost() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Fusion]②: <Son Goten> and <Trunks: Youth> "
        "(Place 1 each of the specified card with the same power from your hand into your Drop Area and play this card.)"
    )
    engine._card_cache[(990446, "front")] = CardRuntimeData(
        card_name="Circled Cost Fusion",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Gotenks",),
    )
    engine._card_cache[(990447, "front")] = CardRuntimeData(
        card_name="Son Goten Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goten",),
    )
    engine._card_cache[(990448, "front")] = CardRuntimeData(
        card_name="Trunks Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Trunks: Youth",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990449,
            card_id=990446,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Gotenks",),
        ),
        CardInstance(
            instance_id=990450,
            card_id=990447,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goten",),
        ),
        CardInstance(
            instance_id=990451,
            card_id=990448,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Trunks: Youth",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990452, card_id=990452, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990453, card_id=990453, owner_id=1, card_type="ENERGY", color="Green", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION)
    state = engine.apply_action(state, action)

    assert state.players[1].battle_area[-1].card_id == 990446
    assert sum(1 for card in state.players[1].energy if card.resting) == 2


def test_phase4_union_fusion_can_pay_mixed_specified_and_circled_cost() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Fusion](Blue)(Blue)③: <Son Goten> and <Trunks: Youth> "
        "(Place 1 each of the specified card with the same power from your hand into your Drop Area and play this card.)"
    )
    engine._card_cache[(990454, "front")] = CardRuntimeData(
        card_name="Mixed Cost Fusion",
        card_type="BATTLE",
        color="Blue",
        energy_cost=8,
        skill_text_raw=union_text,
        characters=("Gotenks",),
    )
    engine._card_cache[(990455, "front")] = CardRuntimeData(
        card_name="Son Goten Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goten",),
    )
    engine._card_cache[(990456, "front")] = CardRuntimeData(
        card_name="Trunks Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Trunks: Youth",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990457,
            card_id=990454,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=8,
            skill_text_raw=union_text,
            characters=("Gotenks",),
        ),
        CardInstance(
            instance_id=990458,
            card_id=990455,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goten",),
        ),
        CardInstance(
            instance_id=990459,
            card_id=990456,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Trunks: Youth",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990460, card_id=990460, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990461, card_id=990461, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990462, card_id=990462, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990463, card_id=990463, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
        CardInstance(instance_id=990464, card_id=990464, owner_id=1, card_type="ENERGY", color="Black", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION)
    state = engine.apply_action(state, action)

    assert state.players[1].battle_area[-1].card_id == 990454
    assert sum(1 for card in state.players[1].energy if card.resting) == 5


def test_phase4_self_union_fusion_activated_can_trigger_auto_draw() -> None:
    engine = RulesEngine(
        effect_rules={
            990465: [
                {
                    "trigger": "self_union_fusion_activated",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = (
        "[Union-Fusion](Blue)(Blue): <Son Goten> and <Trunks: Youth> "
        "(Place 1 each of the specified card with the same power from your hand into your Drop Area and play this card.)"
    )
    engine._card_cache[(990465, "front")] = CardRuntimeData(
        card_name="Fusion Activation Watcher",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Gotenks",),
    )
    engine._card_cache[(990466, "front")] = CardRuntimeData(
        card_name="Son Goten Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goten",),
    )
    engine._card_cache[(990467, "front")] = CardRuntimeData(
        card_name="Trunks Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Trunks: Youth",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990468,
            card_id=990465,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Gotenks",),
        ),
        CardInstance(
            instance_id=990469,
            card_id=990466,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goten",),
        ),
        CardInstance(
            instance_id=990470,
            card_id=990467,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Trunks: Youth",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990471, card_id=990471, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990472, card_id=990472, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION)
    state = engine.apply_action(state, action)

    assert len(state.players[1].hand) == hand_before - 3 + 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_owner_union_fusion_activated_can_trigger_owner_auto_draw() -> None:
    engine = RulesEngine(
        effect_rules={
            990473: [
                {
                    "trigger": "owner_union_fusion_activated",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = (
        "[Union-Fusion](Blue)(Blue): <Son Goten> and <Trunks: Youth> "
        "(Place 1 each of the specified card with the same power from your hand into your Drop Area and play this card.)"
    )
    engine._card_cache[(990474, "front")] = CardRuntimeData(
        card_name="Fusion Body",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Gotenks",),
    )
    engine._card_cache[(990475, "front")] = CardRuntimeData(
        card_name="Son Goten Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goten",),
    )
    engine._card_cache[(990476, "front")] = CardRuntimeData(
        card_name="Trunks Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Trunks: Youth",),
    )
    engine._card_cache[(990473, "front")] = CardRuntimeData(
        card_name="Owner Fusion Activation Watcher",
        card_type="BATTLE",
        color="Blue",
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    watcher = CardInstance(instance_id=990477, card_id=990473, owner_id=1, card_type="BATTLE", color="Blue")
    state.players[1].battle_area = [watcher]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=watcher)
    state.players[1].hand = [
        CardInstance(
            instance_id=990478,
            card_id=990474,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Gotenks",),
        ),
        CardInstance(
            instance_id=990479,
            card_id=990475,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goten",),
        ),
        CardInstance(
            instance_id=990480,
            card_id=990476,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Trunks: Youth",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990481, card_id=990481, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990482, card_id=990482, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION)
    state = engine.apply_action(state, action)

    assert len(state.players[1].hand) == hand_before - 3 + 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_union_fusion_can_require_opponent_energy_threshold() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Fusion](Blue)(Blue), if your opponent has 4 or more energy: <Son Goten> and <Trunks: Youth> "
        "(Place 1 each of the specified card with the same power from your hand into your Drop Area and play this card.)"
    )
    engine._card_cache[(990483, "front")] = CardRuntimeData(
        card_name="Threshold Fusion",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Gotenks",),
    )
    engine._card_cache[(990484, "front")] = CardRuntimeData(
        card_name="Son Goten Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goten",),
    )
    engine._card_cache[(990485, "front")] = CardRuntimeData(
        card_name="Trunks Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Trunks: Youth",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990486,
            card_id=990483,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Gotenks",),
        ),
        CardInstance(
            instance_id=990487,
            card_id=990484,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goten",),
        ),
        CardInstance(
            instance_id=990494,
            card_id=990485,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Trunks: Youth",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990495, card_id=990495, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990496, card_id=990496, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]
    state.players[2].energy = [
        CardInstance(instance_id=990497, card_id=990497, owner_id=2, card_type="ENERGY", color="Yellow", resting=False),
        CardInstance(instance_id=990498, card_id=990498, owner_id=2, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990499, card_id=990499, owner_id=2, card_type="ENERGY", color="Red", resting=False),
    ]

    assert all(a.action_type != ActionType.UNION_FUSION for a in engine.get_legal_actions(state, 1))

    state.players[2].energy.append(
        CardInstance(instance_id=990500, card_id=990500, owner_id=2, card_type="ENERGY", color="Blue", resting=False)
    )
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION)
    state = engine.apply_action(state, action)

    assert state.players[1].battle_area[-1].card_id == 990483


def test_phase4_union_fusion_can_parse_db_style_limit_and_requirement_line_without_reminder_text() -> None:
    engine = RulesEngine()
    union_text = "[Union-Fusion] [Limit 1] If your opponent has 2 or more energy: Blue <Son Goku: Br> card and blue <Vegeta: Br> card."
    engine._card_cache[(990501, "front")] = CardRuntimeData(
        card_name="DB Style Fusion",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Gogeta: Br",),
    )
    engine._card_cache[(990502, "front")] = CardRuntimeData(
        card_name="Son Goku: Br Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goku: Br",),
    )
    engine._card_cache[(990503, "front")] = CardRuntimeData(
        card_name="Vegeta: Br Material",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Vegeta: Br",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990504,
            card_id=990501,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Gogeta: Br",),
        ),
        CardInstance(
            instance_id=990505,
            card_id=990502,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goku: Br",),
        ),
        CardInstance(
            instance_id=990506,
            card_id=990503,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Vegeta: Br",),
        ),
    ]
    state.players[2].energy = [
        CardInstance(instance_id=990507, card_id=990507, owner_id=2, card_type="ENERGY", color="Yellow", resting=False),
    ]

    assert all(a.action_type != ActionType.UNION_FUSION for a in engine.get_legal_actions(state, 1))

    state.players[2].energy.append(
        CardInstance(instance_id=990508, card_id=990508, owner_id=2, card_type="ENERGY", color="Green", resting=False)
    )
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION)
    state = engine.apply_action(state, action)

    assert state.players[1].battle_area[-1].card_id == 990501
    assert len(state.players[1].drop) == 2
    assert {card.card_id for card in state.players[1].drop} == {990502, 990503}


def test_phase4_union_fusion_limit_one_blocks_second_copy_same_turn() -> None:
    engine = RulesEngine()
    union_text = "[Union-Fusion] [Limit 1] If your opponent has 2 or more energy: Blue <Son Goku: Br> card and blue <Vegeta: Br> card."
    engine._card_cache[(990509, "front")] = CardRuntimeData(
        card_name="Limited Fusion",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Gogeta: Br",),
    )
    engine._card_cache[(990510, "front")] = CardRuntimeData(
        card_name="Son Goku: Br Material A",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goku: Br",),
    )
    engine._card_cache[(990511, "front")] = CardRuntimeData(
        card_name="Vegeta: Br Material A",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Vegeta: Br",),
    )
    engine._card_cache[(990512, "front")] = CardRuntimeData(
        card_name="Son Goku: Br Material B",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goku: Br",),
    )
    engine._card_cache[(990513, "front")] = CardRuntimeData(
        card_name="Vegeta: Br Material B",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Vegeta: Br",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990514,
            card_id=990509,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Gogeta: Br",),
        ),
        CardInstance(
            instance_id=990515,
            card_id=990509,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Gogeta: Br",),
        ),
        CardInstance(
            instance_id=990516,
            card_id=990510,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goku: Br",),
        ),
        CardInstance(
            instance_id=990517,
            card_id=990511,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Vegeta: Br",),
        ),
        CardInstance(
            instance_id=990518,
            card_id=990512,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goku: Br",),
        ),
        CardInstance(
            instance_id=990519,
            card_id=990513,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Vegeta: Br",),
        ),
    ]
    state.players[2].energy = [
        CardInstance(instance_id=990520, card_id=990520, owner_id=2, card_type="ENERGY", color="Yellow", resting=False),
        CardInstance(instance_id=990521, card_id=990521, owner_id=2, card_type="ENERGY", color="Green", resting=False),
    ]

    legal = [a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION]
    assert len(legal) == 2

    state = engine.apply_action(state, legal[0])

    remaining = [a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION]
    assert remaining == []


def test_phase4_union_fusion_on_play_can_pay_z_energy_and_grant_barrier_to_next_matching_union_play() -> None:
    engine = RulesEngine(
        effect_rules={
            990522: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_pay_z_energy_on_play_and_grant_next_matching_union_play_keyword",
                    "handler_params": {
                        "grant_keyword": "Barrier",
                        "allowed_colors": "blue",
                        "required_characters": "Gogeta: Br",
                    },
                }
            ]
        },
        skill_cost_rules={
            990522: {
                "auto_on_play_battle": [
                    {
                        "kind": "send_owner_z_energy_to_drop",
                        "amount": 2,
                    }
                ]
            }
        },
    )
    support_text = (
        "[Union-Fusion] [Limit 1] If your opponent has 2 or more energy: Blue <Son Goku: Br> card and blue <Vegeta: Br> card.\n"
        "[Auto] Place 2 of your Z-Energy into their owner's Drop: When this card is played, activate this skill. "
        "During this turn, the next time you play a blue <Gogeta: Br> card with [Union], it gains [Barrier] for the turn."
    )
    target_text = (
        "[Union-Fusion] [Limit 1] If your opponent has 2 or more energy: Blue <Son Goku: Br> card and blue <Vegeta: Br> card."
    )
    engine._card_cache[(990522, "front")] = CardRuntimeData(
        card_name="SS Gogeta, Overflowing Fighting Spirit",
        card_type="BATTLE",
        color="Blue",
        energy_cost=5,
        skill_text_raw=support_text,
        characters=("Gogeta: Br",),
    )
    engine._card_cache[(990523, "front")] = CardRuntimeData(
        card_name="Blue Gogeta Follow-Up",
        card_type="BATTLE",
        color="Blue",
        energy_cost=5,
        skill_text_raw=target_text,
        characters=("Gogeta: Br",),
    )
    engine._card_cache[(990524, "front")] = CardRuntimeData(
        card_name="Son Goku: Br Material A",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goku: Br",),
    )
    engine._card_cache[(990525, "front")] = CardRuntimeData(
        card_name="Vegeta: Br Material A",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Vegeta: Br",),
    )
    engine._card_cache[(990526, "front")] = CardRuntimeData(
        card_name="Son Goku: Br Material B",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Son Goku: Br",),
    )
    engine._card_cache[(990527, "front")] = CardRuntimeData(
        card_name="Vegeta: Br Material B",
        card_type="BATTLE",
        color="Blue",
        power=15000,
        characters=("Vegeta: Br",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[910001],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990528,
            card_id=990522,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=5,
            skill_text_raw=support_text,
            characters=("Gogeta: Br",),
        ),
        CardInstance(
            instance_id=990529,
            card_id=990523,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=5,
            skill_text_raw=target_text,
            characters=("Gogeta: Br",),
        ),
        CardInstance(
            instance_id=990530,
            card_id=990524,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goku: Br",),
        ),
        CardInstance(
            instance_id=990531,
            card_id=990525,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Vegeta: Br",),
        ),
        CardInstance(
            instance_id=990532,
            card_id=990526,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Son Goku: Br",),
        ),
        CardInstance(
            instance_id=990533,
            card_id=990527,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            characters=("Vegeta: Br",),
        ),
    ]
    state.players[1].z_energy = [
        CardInstance(instance_id=990534, card_id=990534, owner_id=1, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=990535, card_id=990535, owner_id=1, card_type="BATTLE", color="Blue"),
    ]
    state.players[2].energy = [
        CardInstance(instance_id=990536, card_id=990536, owner_id=2, card_type="ENERGY", color="Yellow", resting=False),
        CardInstance(instance_id=990537, card_id=990537, owner_id=2, card_type="ENERGY", color="Green", resting=False),
    ]

    first_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION)
    state = engine.apply_action(state, first_action)

    support_played = next(card for card in state.players[1].battle_area if card.card_id == 990522)
    assert len(state.players[1].z_energy) == 0
    assert not engine._card_has_keyword(support_played, "Barrier")
    assert any(cp.name == "effect_auto_pay_z_energy_on_play_and_grant_next_matching_union_play_keyword" for cp in state.checkpoints)

    second_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_FUSION)
    state = engine.apply_action(state, second_action)

    target_played = next(card for card in state.players[1].battle_area if card.card_id == 990523)
    assert engine._card_has_keyword(target_played, "Barrier")
    assert any(cp.name == "delayed_union_play_keyword_grant_applied" for cp in state.checkpoints)


def test_phase4_union_potara_can_play_from_hand_using_matching_materials() -> None:
    engine = RulesEngine(
        effect_rules={
            990381: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = "[Union-Potara](Black): <Son Goku: Xeno> card and <Vegeta: Xeno> card."
    engine._card_cache[(990381, "front")] = CardRuntimeData(
        card_name="Vegito, Xeno Body",
        card_type="BATTLE",
        color="Black",
        energy_cost=5,
        skill_text_raw=union_text,
        characters=("Vegito: Xeno",),
    )
    engine._card_cache[(990382, "front")] = CardRuntimeData(
        card_name="Son Goku: Xeno Material",
        card_type="BATTLE",
        color="Black",
        characters=("Son Goku: Xeno",),
    )
    engine._card_cache[(990383, "front")] = CardRuntimeData(
        card_name="Vegeta: Xeno Material",
        card_type="BATTLE",
        color="Black",
        characters=("Vegeta: Xeno",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990384,
            card_id=990381,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=5,
            skill_text_raw=union_text,
            characters=("Vegito: Xeno",),
        ),
        CardInstance(
            instance_id=990385,
            card_id=990382,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            characters=("Son Goku: Xeno",),
        ),
        CardInstance(
            instance_id=990386,
            card_id=990383,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            characters=("Vegeta: Xeno",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990387, card_id=990440, owner_id=1, card_type="ENERGY", color="Black", resting=False),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[-1]
    assert played.card_id == 990381
    assert played.stacked_card_ids == (990382, 990383)
    assert len(state.players[1].drop) == 0
    assert len(state.players[1].hand) == hand_before - 3 + 1
    assert sum(1 for card in state.players[1].energy if card.resting) == 1
    assert any(cp.name == "union_potara" for cp in state.checkpoints)
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_union_potara_can_move_hand_material_onto_battle_host_and_stack_both() -> None:
    engine = RulesEngine()
    union_text = "[Union-Potara](Blue): <Son Goku> and <Vegeta>."
    engine._card_cache[(990388, "front")] = CardRuntimeData(
        card_name="Battle Host Hand Material Potara",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Vegito",),
    )
    engine._card_cache[(990389, "front")] = CardRuntimeData(
        card_name="Battle Son Goku Material",
        card_type="BATTLE",
        color="Blue",
        characters=("Son Goku",),
    )
    engine._card_cache[(990380, "front")] = CardRuntimeData(
        card_name="Hand Vegeta Material",
        card_type="BATTLE",
        color="Blue",
        characters=("Vegeta",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990378,
            card_id=990389,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            characters=("Son Goku",),
        )
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=990379,
            card_id=990388,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Vegito",),
        ),
        CardInstance(
            instance_id=990377,
            card_id=990380,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            characters=("Vegeta",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990376, card_id=990376, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[0]
    assert played.card_id == 990388
    assert played.stacked_card_ids == (990380, 990389)
    assert len(state.players[1].hand) == 0
    assert len(state.players[1].drop) == 0


def test_phase4_owner_union_potara_activated_can_trigger_owner_auto_draw() -> None:
    engine = RulesEngine(
        effect_rules={
            990390: [
                {
                    "trigger": "owner_union_potara_activated",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = "[Union-Potara](Black): <Son Goku: Xeno> card and <Vegeta: Xeno> card."
    engine._card_cache[(990391, "front")] = CardRuntimeData(
        card_name="Potara Body",
        card_type="BATTLE",
        color="Black",
        energy_cost=5,
        skill_text_raw=union_text,
        characters=("Vegito: Xeno",),
    )
    engine._card_cache[(990392, "front")] = CardRuntimeData(
        card_name="Son Goku: Xeno Material",
        card_type="BATTLE",
        color="Black",
        characters=("Son Goku: Xeno",),
    )
    engine._card_cache[(990393, "front")] = CardRuntimeData(
        card_name="Vegeta: Xeno Material",
        card_type="BATTLE",
        color="Black",
        characters=("Vegeta: Xeno",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    watcher = CardInstance(instance_id=990394, card_id=990390, owner_id=1, card_type="BATTLE", color="Black")
    state.players[1].battle_area = [watcher]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=watcher)
    state.players[1].hand = [
        CardInstance(
            instance_id=990395,
            card_id=990391,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=5,
            skill_text_raw=union_text,
            characters=("Vegito: Xeno",),
        ),
        CardInstance(
            instance_id=990396,
            card_id=990392,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            characters=("Son Goku: Xeno",),
        ),
        CardInstance(
            instance_id=990397,
            card_id=990393,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            characters=("Vegeta: Xeno",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990398, card_id=990441, owner_id=1, card_type="ENERGY", color="Black", resting=False),
    ]
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    assert len(state.players[1].hand) == hand_before - 3 + 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_union_potara_can_play_on_top_of_stacked_together_materials() -> None:
    engine = RulesEngine(
        effect_rules={
            990401: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = (
        "[Union-Potara](Blue)(Blue): <Goku Black> and <Zamasu> "
        "(Place this card in Active Mode on top of the 2 specified cards stacked together)"
    )
    engine._card_cache[(990401, "front")] = CardRuntimeData(
        card_name="Merged Zamasu",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Fused Zamasu",),
    )
    engine._card_cache[(990402, "front")] = CardRuntimeData(
        card_name="Goku Black Host",
        card_type="BATTLE",
        color="Blue",
        characters=("Goku Black",),
    )
    engine._card_cache[(990403, "front")] = CardRuntimeData(
        card_name="Zamasu Under",
        card_type="BATTLE",
        color="Blue",
        characters=("Zamasu",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    host = CardInstance(
        instance_id=990404,
        card_id=990402,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        resting=True,
        stacked_card_ids=(990403,),
        characters=("Goku Black",),
    )
    state.players[1].battle_area = [host]
    state.players[1].hand = [
        CardInstance(
            instance_id=990405,
            card_id=990401,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Fused Zamasu",),
        )
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990406, card_id=990442, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990407, card_id=990443, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[0]
    assert played.card_id == 990401
    assert played.resting is False
    assert played.stacked_card_ids == (990403, 990402)
    assert len(state.players[1].hand) == 1
    assert sum(1 for card in state.players[1].energy if card.resting) == 2
    assert any(cp.name == "union_potara" for cp in state.checkpoints)
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_union_potara_header_can_draw_cards_before_play_followups() -> None:
    engine = RulesEngine()
    union_text = "[Union-Potara](1), draw 2 cards: Green <Zamasu> card and green <Goku Black> card."
    engine._card_cache[(990411, "front")] = CardRuntimeData(
        card_name="Header Draw Potara",
        card_type="BATTLE",
        color="Green",
        energy_cost=5,
        skill_text_raw=union_text,
        characters=("Fused Zamasu",),
    )
    engine._card_cache[(990412, "front")] = CardRuntimeData(
        card_name="Zamasu Material",
        card_type="BATTLE",
        color="Green",
        characters=("Zamasu",),
    )
    engine._card_cache[(990413, "front")] = CardRuntimeData(
        card_name="Goku Black Material",
        card_type="BATTLE",
        color="Green",
        characters=("Goku Black",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990414,
            card_id=990411,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            energy_cost=5,
            skill_text_raw=union_text,
            characters=("Fused Zamasu",),
        ),
        CardInstance(
            instance_id=990415,
            card_id=990412,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            characters=("Zamasu",),
        ),
        CardInstance(
            instance_id=990416,
            card_id=990413,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            characters=("Goku Black",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990417, card_id=990444, owner_id=1, card_type="ENERGY", color="Green", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    assert state.players[1].battle_area[-1].card_id == 990411
    assert len(state.players[1].hand) == 2
    assert sum(1 for card in state.players[1].energy if card.resting) == 1


def test_phase4_union_potara_header_can_draw_and_mill_top_opponent_deck() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Potara]{g}, if your Leader is a green <Zamasu> card, you draw 1 card, "
        "and place the top card of your opponent's deck into its owner's Drop: "
        "Green <Zamasu> card and green <Goku Black> card."
    )
    engine._card_cache[(990421, "front")] = CardRuntimeData(
        card_name="Header Draw Mill Potara",
        card_type="BATTLE",
        color="Green",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Fused Zamasu",),
    )
    engine._card_cache[(990422, "front")] = CardRuntimeData(
        card_name="Zamasu Material",
        card_type="BATTLE",
        color="Green",
        characters=("Zamasu",),
    )
    engine._card_cache[(990423, "front")] = CardRuntimeData(
        card_name="Goku Black Material",
        card_type="BATTLE",
        color="Green",
        characters=("Goku Black",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area = CardInstance(
        instance_id=990424,
        card_id=990450,
        owner_id=1,
        card_type="LEADER",
        color="Green",
        characters=("Zamasu",),
    )
    state.players[1].hand = [
        CardInstance(
            instance_id=990425,
            card_id=990421,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Fused Zamasu",),
        ),
        CardInstance(
            instance_id=990426,
            card_id=990422,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            characters=("Zamasu",),
        ),
        CardInstance(
            instance_id=990427,
            card_id=990423,
            owner_id=1,
            card_type="BATTLE",
            color="Green",
            characters=("Goku Black",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990428, card_id=990445, owner_id=1, card_type="ENERGY", color="Green", resting=False),
    ]
    state.players[2].deck = [990499, 2001, 2002]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    assert state.players[1].battle_area[-1].card_id == 990421
    assert len(state.players[1].hand) == 1
    assert state.players[2].drop[-1].card_id == 990499
    assert len(state.players[2].deck) == 2


def test_phase4_union_potara_can_pay_circled_generic_cost() -> None:
    engine = RulesEngine()
    union_text = "[Union-Potara]②: <Trunks: Xeno> and <Vegeta: Xeno>."
    engine._card_cache[(990431, "front")] = CardRuntimeData(
        card_name="Circled Potara",
        card_type="BATTLE",
        color="Black",
        energy_cost=5,
        skill_text_raw=union_text,
        characters=("Vegeks: Xeno",),
    )
    engine._card_cache[(990432, "front")] = CardRuntimeData(
        card_name="Trunks: Xeno Material",
        card_type="BATTLE",
        color="Black",
        characters=("Trunks: Xeno",),
    )
    engine._card_cache[(990433, "front")] = CardRuntimeData(
        card_name="Vegeta: Xeno Material",
        card_type="BATTLE",
        color="Black",
        characters=("Vegeta: Xeno",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990434,
            card_id=990431,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=5,
            skill_text_raw=union_text,
            characters=("Vegeks: Xeno",),
        ),
        CardInstance(
            instance_id=990435,
            card_id=990432,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            characters=("Trunks: Xeno",),
        ),
        CardInstance(
            instance_id=990436,
            card_id=990433,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            characters=("Vegeta: Xeno",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990437, card_id=990446, owner_id=1, card_type="ENERGY", color="Black", resting=False),
        CardInstance(instance_id=990438, card_id=990447, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    assert state.players[1].battle_area[-1].card_id == 990431
    assert sum(1 for card in state.players[1].energy if card.resting) == 2


def test_phase4_union_potara_can_pay_mixed_specified_and_circled_cost_on_stacked_host() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Potara](Blue)(Blue)③: <Son Goku> and <Vegeta> "
        "(Place this card in Active Mode on top of the 2 specified cards stacked together)"
    )
    engine._card_cache[(990441, "front")] = CardRuntimeData(
        card_name="Mixed Cost Potara",
        card_type="BATTLE",
        color="Blue",
        energy_cost=8,
        skill_text_raw=union_text,
        characters=("Vegito",),
    )
    engine._card_cache[(990442, "front")] = CardRuntimeData(
        card_name="Son Goku Host",
        card_type="BATTLE",
        color="Blue",
        characters=("Son Goku",),
    )
    engine._card_cache[(990443, "front")] = CardRuntimeData(
        card_name="Vegeta Under",
        card_type="BATTLE",
        color="Blue",
        characters=("Vegeta",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990444,
            card_id=990442,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            resting=True,
            stacked_card_ids=(990443,),
            characters=("Son Goku",),
        )
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=990445,
            card_id=990441,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=8,
            skill_text_raw=union_text,
            characters=("Vegito",),
        )
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990448, card_id=990448, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990449, card_id=990449, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990450, card_id=990450, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990451, card_id=990451, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
        CardInstance(instance_id=990452, card_id=990452, owner_id=1, card_type="ENERGY", color="Black", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[0]
    assert played.card_id == 990441
    assert played.resting is False
    assert played.stacked_card_ids == (990443, 990442)
    assert sum(1 for card in state.players[1].energy if card.resting) == 5


def test_phase4_self_played_using_union_potara_can_trigger_auto_draw() -> None:
    engine = RulesEngine(
        effect_rules={
            990461: [
                {
                    "trigger": "self_played_using_union_potara",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = "[Union-Potara](Red)(Red)(Red): <Caulifla> and <Kale>"
    engine._card_cache[(990461, "front")] = CardRuntimeData(
        card_name="Potara Self Trigger",
        card_type="BATTLE",
        color="Red",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Kefla",),
    )
    engine._card_cache[(990462, "front")] = CardRuntimeData(
        card_name="Caulifla Material",
        card_type="BATTLE",
        color="Red",
        characters=("Caulifla",),
    )
    engine._card_cache[(990463, "front")] = CardRuntimeData(
        card_name="Kale Material",
        card_type="BATTLE",
        color="Red",
        characters=("Kale",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990464,
            card_id=990461,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Kefla",),
        ),
        CardInstance(
            instance_id=990465,
            card_id=990462,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            characters=("Caulifla",),
        ),
        CardInstance(
            instance_id=990466,
            card_id=990463,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            characters=("Kale",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990467, card_id=990467, owner_id=1, card_type="ENERGY", color="Red", resting=False),
        CardInstance(instance_id=990468, card_id=990468, owner_id=1, card_type="ENERGY", color="Red", resting=False),
        CardInstance(instance_id=990469, card_id=990469, owner_id=1, card_type="ENERGY", color="Red", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    assert state.players[1].battle_area[-1].card_id == 990461
    assert len(state.players[1].hand) == 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_owner_other_battle_played_using_union_potara_can_trigger_owner_auto_draw() -> None:
    engine = RulesEngine(
        effect_rules={
            990470: [
                {
                    "trigger": "owner_other_battle_played_using_union_potara",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    union_text = "[Union-Potara](Red)(Red)(Red): <Caulifla> and <Kale>"
    engine._card_cache[(990471, "front")] = CardRuntimeData(
        card_name="Potara Body",
        card_type="BATTLE",
        color="Red",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Kefla",),
    )
    engine._card_cache[(990472, "front")] = CardRuntimeData(
        card_name="Caulifla Material",
        card_type="BATTLE",
        color="Red",
        characters=("Caulifla",),
    )
    engine._card_cache[(990473, "front")] = CardRuntimeData(
        card_name="Kale Material",
        card_type="BATTLE",
        color="Red",
        characters=("Kale",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    watcher = CardInstance(instance_id=990474, card_id=990470, owner_id=1, card_type="BATTLE", color="Red")
    state.players[1].battle_area = [watcher]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=watcher)
    state.players[1].hand = [
        CardInstance(
            instance_id=990475,
            card_id=990471,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Kefla",),
        ),
        CardInstance(
            instance_id=990476,
            card_id=990472,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            characters=("Caulifla",),
        ),
        CardInstance(
            instance_id=990477,
            card_id=990473,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            characters=("Kale",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990478, card_id=990478, owner_id=1, card_type="ENERGY", color="Red", resting=False),
        CardInstance(instance_id=990479, card_id=990479, owner_id=1, card_type="ENERGY", color="Red", resting=False),
        CardInstance(instance_id=990480, card_id=990480, owner_id=1, card_type="ENERGY", color="Red", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    assert len(state.players[1].hand) == 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_union_potara_header_can_warp_opponent_battle_and_draw() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Potara] Choose up to 1 of your opponent's Battle Cards, send it to its owner's Warp, and draw 1 card: "
        "<Son Goku> and <Vegeta>."
    )
    engine._card_cache[(990481, "front")] = CardRuntimeData(
        card_name="Warp Draw Potara",
        card_type="BATTLE",
        color="Black",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Vegito",),
    )
    engine._card_cache[(990482, "front")] = CardRuntimeData(
        card_name="Son Goku Material",
        card_type="BATTLE",
        color="Black",
        characters=("Son Goku",),
    )
    engine._card_cache[(990483, "front")] = CardRuntimeData(
        card_name="Vegeta Material",
        card_type="BATTLE",
        color="Black",
        characters=("Vegeta",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990484,
            card_id=990481,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Vegito",),
        ),
        CardInstance(
            instance_id=990485,
            card_id=990482,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            characters=("Son Goku",),
        ),
        CardInstance(
            instance_id=990486,
            card_id=990483,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            characters=("Vegeta",),
        ),
    ]
    state.players[2].battle_area = [
        CardInstance(instance_id=990487, card_id=990500, owner_id=2, card_type="BATTLE", color="Red")
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    assert state.players[1].battle_area[-1].card_id == 990481
    assert len(state.players[1].hand) == 1
    assert len(state.players[2].battle_area) == 0
    assert state.players[2].warp[-1].card_id == 990500


def test_phase4_union_potara_can_parse_colonless_material_line() -> None:
    engine = RulesEngine()
    union_text = "[Union-Potara] Blue <Son Goku> and blue <Vegeta>."
    engine._card_cache[(990488, "front")] = CardRuntimeData(
        card_name="Colonless Potara",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Vegito",),
    )
    engine._card_cache[(990489, "front")] = CardRuntimeData(
        card_name="Blue Son Goku Material",
        card_type="BATTLE",
        color="Blue",
        characters=("Son Goku",),
    )
    engine._card_cache[(990490, "front")] = CardRuntimeData(
        card_name="Blue Vegeta Material",
        card_type="BATTLE",
        color="Blue",
        characters=("Vegeta",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990491,
            card_id=990488,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Vegito",),
        ),
        CardInstance(
            instance_id=990492,
            card_id=990489,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            characters=("Son Goku",),
        ),
        CardInstance(
            instance_id=990493,
            card_id=990490,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            characters=("Vegeta",),
        ),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[-1]
    assert played.card_id == 990488
    assert played.stacked_card_ids == (990489, 990490)
    assert len(state.players[1].drop) == 0
    assert len(state.players[1].hand) == 0
    assert any(cp.name == "union_potara" for cp in state.checkpoints)


def test_phase4_union_potara_can_play_on_stacked_host_with_from_hand_wording() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Potara] ⑤: <Son Goku> and <Vegeta> "
        "(Place this card in Active Mode from your hand on top of the 2 specified cards stacked together)"
    )
    engine._card_cache[(990494, "front")] = CardRuntimeData(
        card_name="From Hand Stacked Potara",
        card_type="BATTLE",
        color="Red",
        energy_cost=8,
        skill_text_raw=union_text,
        characters=("Vegito",),
    )
    engine._card_cache[(990495, "front")] = CardRuntimeData(
        card_name="Son Goku Host",
        card_type="BATTLE",
        color="Red",
        characters=("Son Goku",),
    )
    engine._card_cache[(990496, "front")] = CardRuntimeData(
        card_name="Vegeta Under",
        card_type="BATTLE",
        color="Red",
        characters=("Vegeta",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990497,
            card_id=990495,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            resting=True,
            stacked_card_ids=(990496,),
            characters=("Son Goku",),
        )
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=990498,
            card_id=990494,
            owner_id=1,
            card_type="BATTLE",
            color="Red",
            energy_cost=8,
            skill_text_raw=union_text,
            characters=("Vegito",),
        )
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990501, card_id=990501, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990502, card_id=990502, owner_id=1, card_type="ENERGY", color="Green", resting=False),
        CardInstance(instance_id=990503, card_id=990503, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
        CardInstance(instance_id=990504, card_id=990504, owner_id=1, card_type="ENERGY", color="Black", resting=False),
        CardInstance(instance_id=990505, card_id=990505, owner_id=1, card_type="ENERGY", color="White", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[0]
    assert played.card_id == 990494
    assert played.resting is False
    assert played.stacked_card_ids == (990496, 990495)
    assert len(state.players[1].hand) == 0
    assert sum(1 for card in state.players[1].energy if card.resting) == 5


def test_phase4_union_potara_can_require_material_energy_cost_floor() -> None:
    engine = RulesEngine()
    union_text = "[Union-Potara] (Yellow): Blue <Kale> and yellow <Caulifla> with energy costs of 4 or more."
    engine._card_cache[(990506, "front")] = CardRuntimeData(
        card_name="Energy Floor Potara",
        card_type="BATTLE",
        color="Yellow",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Kefla",),
    )
    engine._card_cache[(990507, "front")] = CardRuntimeData(
        card_name="Low Cost Kale",
        card_type="BATTLE",
        color="Blue",
        energy_cost=3,
        characters=("Kale",),
    )
    engine._card_cache[(990508, "front")] = CardRuntimeData(
        card_name="High Cost Kale",
        card_type="BATTLE",
        color="Blue",
        energy_cost=4,
        characters=("Kale",),
    )
    engine._card_cache[(990509, "front")] = CardRuntimeData(
        card_name="High Cost Caulifla",
        card_type="BATTLE",
        color="Yellow",
        energy_cost=4,
        characters=("Caulifla",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990510,
            card_id=990506,
            owner_id=1,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Kefla",),
        ),
        CardInstance(
            instance_id=990511,
            card_id=990507,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=3,
            characters=("Kale",),
        ),
        CardInstance(
            instance_id=990512,
            card_id=990509,
            owner_id=1,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=4,
            characters=("Caulifla",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990513, card_id=990513, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]

    assert all(a.action_type != ActionType.UNION_POTARA for a in engine.get_legal_actions(state, 1))

    state.players[1].hand[1] = CardInstance(
        instance_id=990514,
        card_id=990508,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        energy_cost=4,
        characters=("Kale",),
    )
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[-1]
    assert played.card_id == 990506
    assert played.stacked_card_ids == (990508, 990509)
    assert len(state.players[1].drop) == 0


def test_phase4_union_potara_can_use_material_from_energy_when_permanent_allows_it() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Potara] Blue <Son Goku> and blue <Vegeta>\n"
        "[Permanent] If you have 4 or more energy, you can choose Battle Cards in your energy when choosing cards to use with this card's [Union] skill from your hand."
    )
    engine._card_cache[(990515, "front")] = CardRuntimeData(
        card_name="Energy Permission Potara",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Vegito",),
    )
    engine._card_cache[(990516, "front")] = CardRuntimeData(
        card_name="Energy Son Goku Material",
        card_type="BATTLE",
        color="Blue",
        energy_cost=3,
        characters=("Son Goku",),
    )
    engine._card_cache[(990517, "front")] = CardRuntimeData(
        card_name="Hand Vegeta Material",
        card_type="BATTLE",
        color="Blue",
        energy_cost=3,
        characters=("Vegeta",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990518,
            card_id=990515,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Vegito",),
        ),
        CardInstance(
            instance_id=990519,
            card_id=990517,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=3,
            characters=("Vegeta",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990520, card_id=990516, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=3, characters=("Son Goku",), resting=False),
        CardInstance(instance_id=990521, card_id=990521, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990522, card_id=990522, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]

    assert all(a.action_type != ActionType.UNION_POTARA for a in engine.get_legal_actions(state, 1))

    state.players[1].energy.append(
        CardInstance(instance_id=990523, card_id=990523, owner_id=1, card_type="ENERGY", color="Blue", resting=False)
    )
    state.players[1].energy.append(
        CardInstance(instance_id=990524, card_id=990524, owner_id=1, card_type="ENERGY", color="Green", resting=False)
    )

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[-1]
    assert played.card_id == 990515
    assert played.stacked_card_ids == (990517, 990516)
    assert len(state.players[1].drop) == 0


def test_phase4_union_potara_can_use_material_from_warp_when_permanent_allows_it() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Potara]③: <Trunks: Xeno> and <Vegeta: Xeno>.\n"
        "[Permanent] You can choose Battle Cards in your Warp when choosing cards to use with this card's [Union] skill from your hand."
    )
    engine._card_cache[(990525, "front")] = CardRuntimeData(
        card_name="Warp Permission Potara",
        card_type="BATTLE",
        color="Black",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Vegeks: Xeno",),
    )
    engine._card_cache[(990526, "front")] = CardRuntimeData(
        card_name="Warp Trunks Material",
        card_type="BATTLE",
        color="Black",
        energy_cost=3,
        characters=("Trunks: Xeno",),
    )
    engine._card_cache[(990527, "front")] = CardRuntimeData(
        card_name="Hand Vegeta Material",
        card_type="BATTLE",
        color="Black",
        energy_cost=3,
        characters=("Vegeta: Xeno",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990528,
            card_id=990525,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Vegeks: Xeno",),
        ),
        CardInstance(
            instance_id=990529,
            card_id=990527,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=3,
            characters=("Vegeta: Xeno",),
        ),
    ]
    state.players[1].warp = [
        CardInstance(instance_id=990530, card_id=990526, owner_id=1, card_type="BATTLE", color="Black", energy_cost=3, characters=("Trunks: Xeno",))
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990531, card_id=990531, owner_id=1, card_type="ENERGY", color="Black", resting=False),
        CardInstance(instance_id=990532, card_id=990532, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990533, card_id=990533, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[-1]
    assert played.card_id == 990525
    assert played.stacked_card_ids == (990527, 990526)
    assert len(state.players[1].drop) == 0
    assert not state.players[1].warp


def test_phase4_union_potara_can_use_material_from_under_black_z_unison_when_permanent_allows_it() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Potara][Limit 1](Black): <Son Goku> card and <Vegeta> card, both black.\n"
        "[Permanent] You can choose Battle Cards from under your black Z-Unison when choosing cards to use with a black card's [Union-Potara] skill from your hand."
    )
    engine._card_cache[(990534, "front")] = CardRuntimeData(
        card_name="Under Z-Unison Permission Potara",
        card_type="BATTLE",
        color="Black",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Vegito",),
    )
    engine._card_cache[(990535, "front")] = CardRuntimeData(
        card_name="Under Z-Unison Son Goku Material",
        card_type="BATTLE",
        color="Black",
        energy_cost=3,
        characters=("Son Goku",),
    )
    engine._card_cache[(990536, "front")] = CardRuntimeData(
        card_name="Hand Vegeta Material",
        card_type="BATTLE",
        color="Black",
        energy_cost=3,
        characters=("Vegeta",),
    )
    engine._card_cache[(990537, "front")] = CardRuntimeData(
        card_name="Black Z-Unison Host",
        card_type="Z-UNISON",
        color="Black",
        energy_cost=2,
        characters=("Towa",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990538,
            card_id=990534,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Vegito",),
        ),
        CardInstance(
            instance_id=990539,
            card_id=990536,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=3,
            characters=("Vegeta",),
        ),
    ]
    state.players[1].unison_area = [
        CardInstance(
            instance_id=990540,
            card_id=990537,
            owner_id=1,
            card_type="Z-UNISON",
            color="Black",
            energy_cost=2,
            markers=1,
            stacked_card_ids=(990535,),
            characters=("Towa",),
        )
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990541, card_id=990541, owner_id=1, card_type="ENERGY", color="Black", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[-1]
    assert played.card_id == 990534
    assert played.stacked_card_ids == (990536, 990535)
    assert len(state.players[1].drop) == 0
    assert state.players[1].unison_area[0].stacked_card_ids == ()


def test_phase4_union_potara_moves_energy_material_to_battle_then_stacks_under_source() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Potara] Blue <Son Goku> and blue <Vegeta>\n"
        "[Permanent] If you have 4 or more energy, you can choose Battle Cards in your energy when choosing cards to use with this card's [Union] skill from your hand."
    )
    engine._card_cache[(990542, "front")] = CardRuntimeData(
        card_name="Energy Fidelity Potara",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Vegito",),
    )
    engine._card_cache[(990543, "front")] = CardRuntimeData(
        card_name="Battle Son Goku Material",
        card_type="BATTLE",
        color="Blue",
        energy_cost=3,
        characters=("Son Goku",),
    )
    engine._card_cache[(990544, "front")] = CardRuntimeData(
        card_name="Energy Vegeta Material",
        card_type="BATTLE",
        color="Blue",
        energy_cost=3,
        characters=("Vegeta",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990545,
            card_id=990542,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Vegito",),
        )
    ]
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990546,
            card_id=990543,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=3,
            characters=("Son Goku",),
        )
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990547, card_id=990544, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=3, characters=("Vegeta",), resting=False),
        CardInstance(instance_id=990548, card_id=990548, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990549, card_id=990549, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990550, card_id=990550, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[0]
    assert played.card_id == 990542
    assert played.stacked_card_ids == (990544, 990543)
    assert not any(card.card_id == 990544 for card in state.players[1].drop)
    assert not any(card.card_id == 990543 for card in state.players[1].drop)


def test_phase4_union_potara_moves_hand_and_energy_materials_to_stack_under_source() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Potara] Blue <Son Goku> and blue <Vegeta>\n"
        "[Permanent] If you have 4 or more energy, you can choose Battle Cards in your energy when choosing cards to use with this card's [Union] skill from your hand."
    )
    engine._card_cache[(990568, "front")] = CardRuntimeData(
        card_name="Hand Energy Fidelity Potara",
        card_type="BATTLE",
        color="Blue",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Vegito",),
    )
    engine._card_cache[(990569, "front")] = CardRuntimeData(
        card_name="Hand Son Goku Material",
        card_type="BATTLE",
        color="Blue",
        energy_cost=3,
        characters=("Son Goku",),
    )
    engine._card_cache[(990570, "front")] = CardRuntimeData(
        card_name="Energy Vegeta Material",
        card_type="BATTLE",
        color="Blue",
        energy_cost=3,
        characters=("Vegeta",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990571,
            card_id=990568,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Vegito",),
        ),
        CardInstance(
            instance_id=990572,
            card_id=990569,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=3,
            characters=("Son Goku",),
        ),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990573, card_id=990570, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=3, characters=("Vegeta",), resting=False),
        CardInstance(instance_id=990574, card_id=990574, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990575, card_id=990575, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990576, card_id=990576, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[0]
    assert played.card_id == 990568
    assert played.stacked_card_ids == (990570, 990569)
    assert len(state.players[1].hand) == 0
    assert not any(card.card_id == 990570 for card in state.players[1].drop)
    assert not any(card.card_id == 990569 for card in state.players[1].drop)


def test_phase4_union_potara_moves_under_z_unison_material_to_battle_then_stacks_under_source() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Potara][Limit 1](Black): <Son Goku> card and <Vegeta> card, both black.\n"
        "[Permanent] You can choose Battle Cards from under your black Z-Unison when choosing cards to use with a black card's [Union-Potara] skill from your hand."
    )
    engine._card_cache[(990551, "front")] = CardRuntimeData(
        card_name="Under Z-Unison Fidelity Potara",
        card_type="BATTLE",
        color="Black",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Vegito",),
    )
    engine._card_cache[(990552, "front")] = CardRuntimeData(
        card_name="Battle Son Goku Material",
        card_type="BATTLE",
        color="Black",
        energy_cost=3,
        characters=("Son Goku",),
    )
    engine._card_cache[(990553, "front")] = CardRuntimeData(
        card_name="Under Z-Unison Vegeta Material",
        card_type="BATTLE",
        color="Black",
        energy_cost=3,
        characters=("Vegeta",),
    )
    engine._card_cache[(990554, "front")] = CardRuntimeData(
        card_name="Black Z-Unison Host",
        card_type="Z-UNISON",
        color="Black",
        energy_cost=2,
        characters=("Towa",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990555,
            card_id=990551,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Vegito",),
        )
    ]
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990556,
            card_id=990552,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=3,
            characters=("Son Goku",),
        )
    ]
    state.players[1].unison_area = [
        CardInstance(
            instance_id=990557,
            card_id=990554,
            owner_id=1,
            card_type="Z-UNISON",
            color="Black",
            energy_cost=2,
            markers=1,
            stacked_card_ids=(990553,),
            characters=("Towa",),
        )
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990558, card_id=990558, owner_id=1, card_type="ENERGY", color="Black", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[0]
    assert played.card_id == 990551
    assert played.stacked_card_ids == (990553, 990552)
    assert state.players[1].unison_area[0].stacked_card_ids == ()
    assert not any(card.card_id == 990553 for card in state.players[1].drop)


def test_phase4_union_potara_moves_warp_material_to_battle_then_stacks_under_source() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Potara]③: <Trunks: Xeno> and <Vegeta: Xeno>.\n"
        "[Permanent] You can choose Battle Cards in your Warp when choosing cards to use with this card's [Union] skill from your hand."
    )
    engine._card_cache[(990559, "front")] = CardRuntimeData(
        card_name="Warp Fidelity Potara",
        card_type="BATTLE",
        color="Black",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Vegeks: Xeno",),
    )
    engine._card_cache[(990560, "front")] = CardRuntimeData(
        card_name="Battle Trunks: Xeno Material",
        card_type="BATTLE",
        color="Black",
        energy_cost=3,
        characters=("Trunks: Xeno",),
    )
    engine._card_cache[(990561, "front")] = CardRuntimeData(
        card_name="Warp Vegeta: Xeno Material",
        card_type="BATTLE",
        color="Black",
        energy_cost=3,
        characters=("Vegeta: Xeno",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990562,
            card_id=990559,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Vegeks: Xeno",),
        )
    ]
    state.players[1].battle_area = [
        CardInstance(
            instance_id=990563,
            card_id=990560,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=3,
            characters=("Trunks: Xeno",),
        )
    ]
    state.players[1].warp = [
        CardInstance(
            instance_id=990564,
            card_id=990561,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=3,
            characters=("Vegeta: Xeno",),
        )
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990565, card_id=990565, owner_id=1, card_type="ENERGY", color="Black", resting=False),
        CardInstance(instance_id=990566, card_id=990566, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990567, card_id=990567, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[0]
    assert played.card_id == 990559
    assert played.stacked_card_ids == (990561, 990560)
    assert not state.players[1].warp
    assert not any(card.card_id == 990561 for card in state.players[1].drop)


def test_phase4_union_potara_moves_hand_and_warp_materials_to_stack_under_source() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Potara]③: <Trunks: Xeno> and <Vegeta: Xeno>.\n"
        "[Permanent] You can choose Battle Cards in your Warp when choosing cards to use with this card's [Union] skill from your hand."
    )
    engine._card_cache[(990577, "front")] = CardRuntimeData(
        card_name="Hand Warp Fidelity Potara",
        card_type="BATTLE",
        color="Black",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Vegeks: Xeno",),
    )
    engine._card_cache[(990578, "front")] = CardRuntimeData(
        card_name="Hand Trunks: Xeno Material",
        card_type="BATTLE",
        color="Black",
        energy_cost=3,
        characters=("Trunks: Xeno",),
    )
    engine._card_cache[(990579, "front")] = CardRuntimeData(
        card_name="Warp Vegeta: Xeno Material",
        card_type="BATTLE",
        color="Black",
        energy_cost=3,
        characters=("Vegeta: Xeno",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990580,
            card_id=990577,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Vegeks: Xeno",),
        ),
        CardInstance(
            instance_id=990581,
            card_id=990578,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=3,
            characters=("Trunks: Xeno",),
        ),
    ]
    state.players[1].warp = [
        CardInstance(
            instance_id=990582,
            card_id=990579,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=3,
            characters=("Vegeta: Xeno",),
        )
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990583, card_id=990583, owner_id=1, card_type="ENERGY", color="Black", resting=False),
        CardInstance(instance_id=990584, card_id=990584, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
        CardInstance(instance_id=990585, card_id=990585, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[0]
    assert played.card_id == 990577
    assert played.stacked_card_ids == (990579, 990578)
    assert len(state.players[1].hand) == 0
    assert not state.players[1].warp
    assert not any(card.card_id == 990579 for card in state.players[1].drop)
    assert not any(card.card_id == 990578 for card in state.players[1].drop)


def test_phase4_union_potara_moves_hand_and_under_z_unison_materials_to_stack_under_source() -> None:
    engine = RulesEngine()
    union_text = (
        "[Union-Potara][Limit 1](Black): <Son Goku> card and <Vegeta> card, both black.\n"
        "[Permanent] You can choose Battle Cards from under your black Z-Unison when choosing cards to use with a black card's [Union-Potara] skill from your hand."
    )
    engine._card_cache[(990586, "front")] = CardRuntimeData(
        card_name="Hand Under Z-Unison Fidelity Potara",
        card_type="BATTLE",
        color="Black",
        energy_cost=6,
        skill_text_raw=union_text,
        characters=("Vegito",),
    )
    engine._card_cache[(990587, "front")] = CardRuntimeData(
        card_name="Hand Son Goku Material",
        card_type="BATTLE",
        color="Black",
        energy_cost=3,
        characters=("Son Goku",),
    )
    engine._card_cache[(990588, "front")] = CardRuntimeData(
        card_name="Under Z-Unison Vegeta Material",
        card_type="BATTLE",
        color="Black",
        energy_cost=3,
        characters=("Vegeta",),
    )
    engine._card_cache[(990589, "front")] = CardRuntimeData(
        card_name="Black Z-Unison Host",
        card_type="Z-UNISON",
        color="Black",
        energy_cost=2,
        characters=("Towa",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(
            instance_id=990590,
            card_id=990586,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=6,
            skill_text_raw=union_text,
            characters=("Vegito",),
        ),
        CardInstance(
            instance_id=990591,
            card_id=990587,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            energy_cost=3,
            characters=("Son Goku",),
        ),
    ]
    state.players[1].unison_area = [
        CardInstance(
            instance_id=990592,
            card_id=990589,
            owner_id=1,
            card_type="Z-UNISON",
            color="Black",
            energy_cost=2,
            markers=1,
            stacked_card_ids=(990588,),
            characters=("Towa",),
        )
    ]
    state.players[1].energy = [
        CardInstance(instance_id=990593, card_id=990593, owner_id=1, card_type="ENERGY", color="Black", resting=False),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.UNION_POTARA)
    state = engine.apply_action(state, action)

    played = state.players[1].battle_area[0]
    assert played.card_id == 990586
    assert played.stacked_card_ids == (990588, 990587)
    assert len(state.players[1].hand) == 0
    assert state.players[1].unison_area[0].stacked_card_ids == ()
    assert not any(card.card_id == 990588 for card in state.players[1].drop)
    assert not any(card.card_id == 990587 for card in state.players[1].drop)


def test_phase4_z_awaken_can_require_combo_area_count_and_matching_awakened_leader() -> None:
    engine = RulesEngine()
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="Gotenks Front", card_type="LEADER", color="Green", has_awaken=True)
    engine._card_cache[(1, "back")] = CardRuntimeData(
        card_name="Gotenks, Back Side",
        card_type="LEADER",
        color="Green",
        traits=("Fusion",),
        characters=("Gotenks",),
    )
    engine._card_cache[(990202, "front")] = CardRuntimeData(
        card_name="Z Gotenks",
        card_type="Z-LEADER",
        color="Green",
        skill_text_raw="[Z-Awaken](Green), when you have 2 or more cards in your Combo Area: Mono-green <Gotenks>.",
        traits=("Fusion",),
        characters=("Gotenks",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[990202],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    engine._apply_leader_back_side(state.players[1].leader_area)
    state.players[1].energy = [
        CardInstance(instance_id=990094, card_id=952102, owner_id=1, card_type="ENERGY", color="Green", resting=False),
    ]
    state.players[1].z_deck[0].face_up = True
    state.players[1].combo_area = [CardInstance(instance_id=990095, card_id=952103, owner_id=1),]

    assert all(a.action_type != ActionType.Z_AWAKEN for a in engine.get_legal_actions(state, 1))

    state.players[1].combo_area.append(CardInstance(instance_id=990096, card_id=952104, owner_id=1))
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.Z_AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.card_id == 990202
    assert state.players[1].leader_area.card_type == "Z-LEADER"
    assert any(cp.name == "leader_z_awakened" for cp in state.checkpoints)


def test_phase4_z_awaken_can_require_matching_card_in_owner_drop() -> None:
    engine = RulesEngine()
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="King Piccolo Front", card_type="LEADER", color="Green", has_awaken=True)
    engine._card_cache[(1, "back")] = CardRuntimeData(
        card_name="King Piccolo, Back Side",
        card_type="LEADER",
        color="Green",
        traits=("Namekian",),
        characters=("King Piccolo",),
    )
    engine._card_cache[(990203, "front")] = CardRuntimeData(
        card_name="Piccolo Jr., Z-Awakened",
        card_type="Z-LEADER",
        color="Green",
        z_energy_cost=1,
        skill_text_raw="[Z-Awaken] When your life is at 2 or less and there are 1 or more <King Piccolo> cards in your Drop: Green <King Piccolo> or green <Piccolo Jr.>.",
        traits=("Namekian",),
        characters=("Piccolo Jr.",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[990203],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    engine._apply_leader_back_side(state.players[1].leader_area)
    state.players[1].life = state.players[1].life[:2]
    state.players[1].energy = [
        CardInstance(instance_id=990097, card_id=952105, owner_id=1, card_type="ENERGY", color="Green", resting=False),
    ]
    state.players[1].z_energy = [
        CardInstance(instance_id=990098, card_id=952106, owner_id=1, card_type="Z-ENERGY", color="Green"),
    ]
    state.players[1].z_deck[0].face_up = True

    assert all(a.action_type != ActionType.Z_AWAKEN for a in engine.get_legal_actions(state, 1))

    state.players[1].drop.append(
        CardInstance(instance_id=990099, card_id=952107, owner_id=1, card_type="BATTLE", color="Green", characters=("King Piccolo",))
    )
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.Z_AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.card_id == 990203
    assert state.players[1].leader_area.card_type == "Z-LEADER"
    assert any(cp.name == "leader_z_awakened" for cp in state.checkpoints)


def test_phase4_z_awaken_can_warp_required_matching_z_energy_cards() -> None:
    engine = RulesEngine()
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="Zamasu Front", card_type="LEADER", color="Yellow", has_awaken=True)
    engine._card_cache[(1, "back")] = CardRuntimeData(
        card_name="Zamasu, Back Side",
        card_type="LEADER",
        color="Yellow",
        traits=("God",),
        characters=("Goku Black",),
    )
    engine._card_cache[(990204, "front")] = CardRuntimeData(
        card_name="Fused Zamasu, Z-Awakened",
        card_type="Z-LEADER",
        color="Yellow",
        z_energy_cost=1,
        skill_text_raw="[Z-Awaken](Yellow), if your life is at 4 or less and you send 1 <Zamasu> card and 1 <Goku Black> card from your Z-Energy to your Warp: Yellow <Goku Black>.",
        traits=("God",),
        characters=("Fused Zamasu",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[990204],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    engine._apply_leader_back_side(state.players[1].leader_area)
    state.players[1].life = state.players[1].life[:4]
    state.players[1].energy = [
        CardInstance(instance_id=990100, card_id=952108, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]
    state.players[1].z_deck[0].face_up = True
    state.players[1].z_energy = [
        CardInstance(instance_id=990101, card_id=952109, owner_id=1, card_type="Z-ENERGY", color="Yellow", characters=("Zamasu",)),
        CardInstance(instance_id=990102, card_id=952110, owner_id=1, card_type="Z-ENERGY", color="Yellow", characters=("Goku Black",)),
    ]

    assert all(a.action_type != ActionType.Z_AWAKEN for a in engine.get_legal_actions(state, 1))

    filler = CardInstance(instance_id=990103, card_id=952111, owner_id=1, card_type="Z-ENERGY", color="Yellow", characters=("Other",))
    state.players[1].z_energy.append(filler)
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.Z_AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.card_id == 990204
    assert [card.instance_id for card in state.players[1].warp[-2:]] == [990102, 990101]
    assert all(card.instance_id != filler.instance_id for card in state.players[1].z_energy)
    assert any(card.instance_id == filler.instance_id for card in state.players[1].drop)
    assert any(cp.name == "leader_z_awakened" for cp in state.checkpoints)


def test_phase4_owner_leader_z_awakened_can_trigger_owner_auto_draw() -> None:
    engine = RulesEngine(
        effect_rules={
            952112: [
                {
                    "trigger": "owner_leader_z_awakened",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="Vegeta Front", card_type="LEADER", color="Yellow", has_awaken=True)
    engine._card_cache[(1, "back")] = CardRuntimeData(
        card_name="SS Vegeta, Fighting Instincts",
        card_type="LEADER",
        color="Yellow",
        traits=("Saiyan",),
        characters=("Vegeta",),
    )
    engine._card_cache[(990205, "front")] = CardRuntimeData(
        card_name="SS Vegeta, Z-Awakened",
        card_type="Z-LEADER",
        color="Yellow",
        z_energy_cost=1,
        skill_text_raw="[Z-Awaken](Yellow), when your life is at 3 or less: {SS Vegeta, Fighting Instincts}.",
        traits=("Saiyan",),
        characters=("Vegeta",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[990205],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    engine._apply_leader_back_side(state.players[1].leader_area)
    state.players[1].life = state.players[1].life[:3]
    state.players[1].energy = [
        CardInstance(instance_id=990104, card_id=952113, owner_id=1, card_type="ENERGY", color="Yellow", resting=False),
    ]
    state.players[1].z_energy = [
        CardInstance(instance_id=990105, card_id=952114, owner_id=1, card_type="Z-ENERGY", color="Yellow"),
    ]
    state.players[1].z_deck[0].face_up = True
    watcher = CardInstance(instance_id=990106, card_id=952112, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].battle_area = [watcher]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=watcher)
    hand_before = len(state.players[1].hand)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.Z_AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.card_id == 990205
    assert len(state.players[1].hand) == hand_before + 1
    assert any(cp.name == "leader_z_awakened" for cp in state.checkpoints)
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_z_awaken_can_pay_blue_brace_cost_symbol() -> None:
    engine = RulesEngine()
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="Majin Buu Front", card_type="LEADER", color="Blue", has_awaken=True)
    engine._card_cache[(1, "back")] = CardRuntimeData(
        card_name="Majin Buu, Shape-Shifter",
        card_type="LEADER",
        color="Blue",
        traits=("Majin",),
        characters=("Majin Buu, Shape-Shifter",),
    )
    engine._card_cache[(990206, "front")] = CardRuntimeData(
        card_name="Majin Buu, Z-Awakened",
        card_type="Z-LEADER",
        color="Blue",
        z_energy_cost=1,
        skill_text_raw="[Z-Awaken] {u}, when you have 2 or more cards in your Combo Area: {Majin Buu, Shape-Shifter}.",
        traits=("Majin",),
        characters=("Majin Buu",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[990206],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    engine._apply_leader_back_side(state.players[1].leader_area)
    state.players[1].energy = [
        CardInstance(instance_id=990107, card_id=952115, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]
    state.players[1].z_energy = [
        CardInstance(instance_id=990108, card_id=952116, owner_id=1, card_type="Z-ENERGY", color="Blue"),
    ]
    state.players[1].combo_area = [
        CardInstance(instance_id=990109, card_id=952117, owner_id=1),
        CardInstance(instance_id=990110, card_id=952118, owner_id=1),
    ]
    state.players[1].z_deck[0].face_up = True

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.Z_AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.card_id == 990206
    assert any(cp.name == "leader_z_awakened" for cp in state.checkpoints)


def test_phase4_activate_main_can_reduce_next_matching_z_awaken_cost_in_z_deck() -> None:
    engine = RulesEngine(
        effect_rules={
            952119: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_reduce_next_matching_z_awaken_cost_in_z_deck",
                    "handler_params": {
                        "target_required_name_contains": "SS VEGETA, Z-AWAKENED",
                        "reduction_cost_token": "Yellow",
                        "uses_remaining": 1,
                    },
                }
            ]
        }
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="Vegeta Front", card_type="LEADER", color="Yellow", has_awaken=True)
    engine._card_cache[(1, "back")] = CardRuntimeData(card_name="SS Vegeta, Fighting Instincts", card_type="LEADER", color="Yellow", characters=("Vegeta",))
    engine._card_cache[(990207, "front")] = CardRuntimeData(
        card_name="SS Vegeta, Z-Awakened",
        card_type="Z-LEADER",
        color="Yellow",
        z_energy_cost=0,
        skill_text_raw="[Z-Awaken](Yellow), when your life is at 3 or less: {SS Vegeta, Fighting Instincts}.",
        characters=("Vegeta",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[990207],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    engine._apply_leader_back_side(state.players[1].leader_area)
    state.players[1].life = state.players[1].life[:3]
    state.players[1].z_deck[0].face_up = True
    reducer = CardInstance(instance_id=990111, card_id=952119, owner_id=1, card_type="BATTLE", color="Yellow", has_activate_main=True)
    state.players[1].battle_area = [reducer]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=reducer)

    assert all(a.action_type != ActionType.Z_AWAKEN for a in engine.get_legal_actions(state, 1))

    activate = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle")
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert len(state.activate_z_awaken_cost_reductions) == 1
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.Z_AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.card_id == 990207
    assert not state.activate_z_awaken_cost_reductions
    assert any(cp.name == "effect_activate_reduce_next_matching_z_awaken_cost_in_z_deck" for cp in state.checkpoints)


def test_phase4_self_played_can_reduce_next_matching_z_awaken_cost_and_z_energy_in_z_deck() -> None:
    engine = RulesEngine(
        effect_rules={
            952120: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_reduce_next_matching_z_awaken_cost_in_z_deck_on_play",
                    "handler_params": {
                        "target_required_name_contains": "GOLDEN FRIEZA, SHINING EMPEROR",
                        "reduction_cost_token": "y",
                        "z_energy_reduction": 1,
                        "uses_remaining": 1,
                    },
                }
            ]
        }
    )
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="Frieza Front", card_type="LEADER", color="Yellow", has_awaken=True)
    engine._card_cache[(1, "back")] = CardRuntimeData(card_name="Frieza Back", card_type="LEADER", color="Yellow", characters=("Frieza",))
    engine._card_cache[(990208, "front")] = CardRuntimeData(
        card_name="Golden Frieza, Shining Emperor",
        card_type="Z-LEADER",
        color="Yellow",
        z_energy_cost=1,
        skill_text_raw="[Z-Awaken](Yellow), when your life is at 3 or less: Yellow <Frieza> card.",
        characters=("Frieza",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[990208],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    engine._apply_leader_back_side(state.players[1].leader_area)
    state.players[1].life = state.players[1].life[:3]
    state.players[1].z_deck[0].face_up = True
    state.players[1].hand = [
        CardInstance(instance_id=990112, card_id=952120, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=0, power=15000)
    ]

    assert all(a.action_type != ActionType.Z_AWAKEN for a in engine.get_legal_actions(state, 1))

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert len(state.activate_z_awaken_cost_reductions) == 1
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.Z_AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.card_id == 990208
    assert not state.activate_z_awaken_cost_reductions
    assert any(cp.name == "effect_auto_reduce_next_matching_z_awaken_cost_in_z_deck_on_play" for cp in state.checkpoints)


def test_phase4_z_awaken_can_require_all_energy_resting_and_skip_next_charge_phase() -> None:
    engine = RulesEngine()
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="GT Front", card_type="LEADER", color="Red", has_awaken=True)
    engine._card_cache[(1, "back")] = CardRuntimeData(
        card_name="SS4 Duo, Back Side",
        card_type="LEADER",
        color="Red",
        characters=("Son Goku: GT", "Vegeta: GT"),
    )
    engine._card_cache[(990209, "front")] = CardRuntimeData(
        card_name="SS4 Duo, Z-Awakened",
        card_type="Z-LEADER",
        color="Red",
        skill_text_raw=(
            "[Z-Awaken] when your life is at 4 or less, all of your energy is in Rest Mode, "
            "and you skip your Charge Phase during your next turn: Red <Son Goku: GT> <Vegeta: GT>."
        ),
        characters=("Son Goku: GT", "Vegeta: GT"),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[990209],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    engine._apply_leader_back_side(state.players[1].leader_area)
    state.players[1].life = state.players[1].life[:4]
    state.players[1].energy = [
        CardInstance(instance_id=990113, card_id=952121, owner_id=1, card_type="ENERGY", color="Red", resting=False),
        CardInstance(instance_id=990114, card_id=952122, owner_id=1, card_type="ENERGY", color="Red", resting=True),
    ]
    state.players[1].z_deck[0].face_up = True

    assert all(a.action_type != ActionType.Z_AWAKEN for a in engine.get_legal_actions(state, 1))

    state.players[1].energy[0].resting = True
    hand_before_skip_turn = len(state.players[1].hand)
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.Z_AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.card_id == 990209
    assert 1 in state.scheduled_charge_phase_skip_player_ids

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))

    assert state.active_player == 1
    assert state.phase == TurnPhase.MAIN
    assert len(state.players[1].hand) == hand_before_skip_turn
    assert all(card.resting for card in state.players[1].energy)
    assert 1 not in state.scheduled_charge_phase_skip_player_ids
    assert any(cp.name == "charge_phase_skipped" for cp in state.checkpoints)


def test_phase4_z_awaken_can_pay_spirit_boost_header_cost_without_colon_form() -> None:
    engine = RulesEngine()
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="Cooler Front", card_type="LEADER", color="Green", has_awaken=True)
    engine._card_cache[(1, "back")] = CardRuntimeData(
        card_name="Cooler Back",
        card_type="LEADER",
        color="Green",
        characters=("Cooler",),
    )
    engine._card_cache[(990210, "front")] = CardRuntimeData(
        card_name="Cooler, Z-Awakened",
        card_type="Z-LEADER",
        color="Green",
        skill_text_raw="[Z-Awaken][Spirit Boost 2] Green <Cooler> card.",
        characters=("Cooler",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[990210],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    engine._apply_leader_back_side(state.players[1].leader_area)
    state.players[1].z_deck[0].face_up = True
    state.players[1].unison_area = [
        CardInstance(instance_id=990115, card_id=952123, owner_id=1, card_type="UNISON", color="Green", markers=1),
        CardInstance(instance_id=990116, card_id=952124, owner_id=1, card_type="UNISON", color="Green", markers=1),
    ]

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.Z_AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.card_id == 990210
    assert sum(card.markers for card in state.players[1].unison_area) == 0
    assert any(cp.name == "marker_removed_z_awaken_spirit_boost" for cp in state.checkpoints)


def test_phase4_z_awaken_can_apply_first_z_stack_slice_from_z_deck() -> None:
    engine = RulesEngine()
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="Vegeta Front", card_type="LEADER", color="Yellow", has_awaken=True)
    engine._card_cache[(1, "back")] = CardRuntimeData(
        card_name="SS Vegeta, Fighting Instincts",
        card_type="LEADER",
        color="Yellow",
        characters=("Vegeta",),
    )
    engine._card_cache[(990211, "front")] = CardRuntimeData(
        card_name="SS Vegeta, Z-Stacked",
        card_type="Z-LEADER",
        color="Yellow",
        skill_text_raw=(
            "[Z-Awaken] When your life is at 3 or less: {SS Vegeta, Fighting Instincts}.\n"
            "[Z-Stack 1] Yellow Battle Card with energy cost of 3 or less. "
            "(When putting this card into play/on top of your Leader from your Z-Deck, place up to 1 of the specified cards from your Z-Deck under this card.)"
        ),
        characters=("Vegeta",),
    )
    engine._card_cache[(990212, "front")] = CardRuntimeData(
        card_name="Yellow Stack Target",
        card_type="BATTLE",
        color="Yellow",
        energy_cost=3,
    )
    engine._card_cache[(990213, "front")] = CardRuntimeData(
        card_name="Yellow Too Expensive",
        card_type="BATTLE",
        color="Yellow",
        energy_cost=4,
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[990211, 990212, 990213],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    engine._apply_leader_back_side(state.players[1].leader_area)
    state.players[1].life = state.players[1].life[:3]
    for row in state.players[1].z_deck:
        row.face_up = True

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.Z_AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.card_id == 990211
    assert state.players[1].leader_area.stacked_card_ids == (990212,)
    assert [row.card_id for row in state.players[1].z_deck] == [990213]
    assert any(cp.name == "leader_z_stack_applied" for cp in state.checkpoints)


def test_phase4_z_awaken_can_apply_z_stack_with_trait_and_different_character_names() -> None:
    engine = RulesEngine()
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="U7 Front", card_type="LEADER", color="Red", has_awaken=True)
    engine._card_cache[(1, "back")] = CardRuntimeData(
        card_name="Warriors of Universe 7 Back",
        card_type="LEADER",
        color="Red",
        traits=("Universe 7",),
        characters=("Son Goku",),
    )
    engine._card_cache[(990214, "front")] = CardRuntimeData(
        card_name="Universe 7 Z-Leader",
        card_type="Z-LEADER",
        color="Red",
        skill_text_raw=(
            "[Z-Awaken] When your life is at 3 or less: {Warriors of Universe 7 Back}.\n"
            "[Z-Stack 2] Red ≪Universe 7≫ Battle Cards with different character names. "
            "(When putting this card into play/on top of your Leader from your Z-Deck, place up to 2 of the specified cards from your Z-Deck under this card.)"
        ),
        traits=("Universe 7",),
        characters=("Son Goku",),
    )
    engine._card_cache[(990215, "front")] = CardRuntimeData(
        card_name="U7 Goku",
        card_type="BATTLE",
        color="Red",
        traits=("Universe 7",),
        characters=("Son Goku",),
    )
    engine._card_cache[(990216, "front")] = CardRuntimeData(
        card_name="U7 Goku Duplicate",
        card_type="BATTLE",
        color="Red",
        traits=("Universe 7",),
        characters=("Son Goku",),
    )
    engine._card_cache[(990217, "front")] = CardRuntimeData(
        card_name="U7 Vegeta",
        card_type="BATTLE",
        color="Red",
        traits=("Universe 7",),
        characters=("Vegeta",),
    )
    engine._card_cache[(990218, "front")] = CardRuntimeData(
        card_name="Wrong Trait Card",
        card_type="BATTLE",
        color="Red",
        traits=("Saiyan",),
        characters=("Gohan",),
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[990214, 990215, 990216, 990218, 990217],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    engine._apply_leader_back_side(state.players[1].leader_area)
    state.players[1].life = state.players[1].life[:3]
    for row in state.players[1].z_deck:
        row.face_up = True

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.Z_AWAKEN)
    state = engine.apply_action(state, action)

    assert state.players[1].leader_area.card_id == 990214
    assert state.players[1].leader_area.stacked_card_ids == (990215, 990217)
    assert [row.card_id for row in state.players[1].z_deck] == [990216, 990218]
    assert any(cp.name == "leader_z_stack_applied" for cp in state.checkpoints)


def test_phase4_self_played_can_place_from_drop_under_self() -> None:
    engine = RulesEngine(
        effect_rules={
            990219: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_place_up_to_n_from_owner_drop_under_self_on_play",
                    "handler_params": {"max_targets": 1, "required_traits": "Saiyan"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    host = CardInstance(instance_id=990120, card_id=990219, owner_id=1, card_type="BATTLE", color="Red", power=20000)
    drop_match = CardInstance(instance_id=990121, card_id=990220, owner_id=1, card_type="BATTLE", color="Red", traits=("Saiyan",))
    drop_other = CardInstance(instance_id=990122, card_id=990221, owner_id=1, card_type="BATTLE", color="Blue", traits=("Earthling",))
    state.players[1].hand = [host]
    state.players[1].drop = [drop_match, drop_other]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    in_play = state.players[1].battle_area[0]
    assert in_play.stacked_card_ids == (990220,)
    assert [card.card_id for card in state.players[1].drop] == [990221]
    assert any(cp.name == "effect_auto_place_up_to_n_from_owner_drop_under_self_on_play" for cp in state.checkpoints)


def test_phase4_self_played_can_place_from_deck_or_drop_under_self() -> None:
    class Repo:
        @staticmethod
        def get_by_id(card_id: int, source_table: str = "cards"):
            data = {
                990230: SimpleNamespace(
                    card_name="Drop Saiyan",
                    power_int=10000,
                    card_type="BATTLE",
                    card_color="Red",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="1",
                    card_skill_unstyled="",
                    has_awaken=False,
                        card_traits_json='["Saiyan"]',
                        card_character_json='["Son Goku"]',
                ),
                990231: SimpleNamespace(
                    card_name="Deck Saiyan",
                    power_int=15000,
                    card_type="BATTLE",
                    card_color="Red",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="2",
                    card_skill_unstyled="",
                    has_awaken=False,
                        card_traits_json='["Saiyan"]',
                        card_character_json='["Vegeta"]',
                ),
                990232: SimpleNamespace(
                    card_name="Deck Other",
                    power_int=15000,
                    card_type="BATTLE",
                    card_color="Blue",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="2",
                    card_skill_unstyled="",
                    has_awaken=False,
                        card_traits_json='["Earthling"]',
                        card_character_json='["Krillin"]',
                ),
            }
            return data.get(card_id)

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            990229: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_place_up_to_n_from_owner_deck_or_drop_under_self_on_play",
                    "handler_params": {
                        "max_targets": 2,
                        "allowed_colors": "Red",
                        "required_traits": "Saiyan",
                        "required_card_type": "BATTLE",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    host = CardInstance(instance_id=990129, card_id=990229, owner_id=1, card_type="BATTLE", color="Red", power=20000)
    drop_match = CardInstance(instance_id=990130, card_id=990230, owner_id=1, card_type="BATTLE", color="Red", traits=("Saiyan",))
    state.players[1].hand = [host]
    state.players[1].drop = [drop_match]
    state.players[1].deck = [990231, 990232, 1999]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    in_play = state.players[1].battle_area[0]
    assert in_play.stacked_card_ids == (990230, 990231)
    assert state.players[1].drop == []
    assert state.players[1].deck == [990232, 1999]
    assert any(cp.name == "effect_auto_place_up_to_n_from_owner_deck_or_drop_under_self_on_play" for cp in state.checkpoints)


def test_phase4_activate_main_can_play_from_under_self_and_place_self_under_played_card() -> None:
    class Repo:
        @staticmethod
        def get_by_id(card_id: int, source_table: str = "cards"):
            data = {
                990240: SimpleNamespace(
                    card_name="Universe 7 Gohan",
                    power_int=20000,
                    card_type="BATTLE",
                    card_color="Red",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="2",
                    card_skill_unstyled="",
                    has_awaken=False,
                    card_traits_json='["Universe 7"]',
                    card_character_json='["Son Gohan: Adolescence"]',
                ),
                990241: SimpleNamespace(
                    card_name="Wrong Card",
                    power_int=15000,
                    card_type="BATTLE",
                    card_color="Blue",
                    energy_cost_int=3,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="3",
                    card_skill_unstyled="",
                    has_awaken=False,
                    card_traits_json='["Universe 7"]',
                    card_character_json='["Piccolo"]',
                ),
            }
            return data.get(card_id)

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            990239: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_up_to_n_from_under_self_and_place_self_under_played_card",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "red",
                        "required_traits": "Universe 7",
                        "required_characters": "Son Gohan: Adolescence",
                        "max_cost": 2,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    host = CardInstance(
        instance_id=990139,
        card_id=990239,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        power=25000,
        has_activate_main=True,
        stacked_card_ids=(990240, 990241),
    )
    state.players[1].battle_area = [host]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=host)

    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert len(state.players[1].battle_area) == 1
    played = state.players[1].battle_area[0]
    assert played.card_id == 990240
    assert played.stacked_card_ids == (990239,)
    assert played.instance_id != 990139
    assert any(
        event.name == "card_played"
        and event.payload.get("played_from") == "under"
        and int(event.payload.get("source_card_id") or -1) == 990240
        for event in state.effect_events
    )
    assert any(cp.name == "effect_activate_play_up_to_n_from_under_self_and_place_self_under_played_card" for cp in state.checkpoints)


def test_phase4_card_played_from_under_by_skill_can_gain_power_and_keyword() -> None:
    class Repo:
        @staticmethod
        def get_by_id(card_id: int, source_table: str = "cards"):
            data = {
                990250: SimpleNamespace(
                    card_name="Universe 7 Gohan",
                    power_int=20000,
                    card_type="BATTLE",
                    card_color="Red",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="2",
                    card_skill_unstyled="",
                    has_awaken=False,
                    card_traits_json='["Universe 7"]',
                    card_character_json='["Son Gohan: Adolescence"]',
                ),
            }
            return data.get(card_id)

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            990249: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_up_to_n_from_under_self_and_place_self_under_played_card",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "red",
                        "required_traits": "Universe 7",
                        "required_characters": "Son Gohan: Adolescence",
                        "max_cost": 2,
                    },
                }
            ],
            990250: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_self_gain_power_for_turn_on_play",
                    "handler_params": {
                        "power_delta": 10000,
                        "grant_keyword": "Dual Attack",
                        "requires_played_from": "under",
                        "requires_played_via": "skill",
                        "min_owner_energy": 4,
                    },
                }
            ],
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=990260 + i, card_id=3000 + i, owner_id=1, card_type="ENERGY", color="Red", energy_cost=0, power=0)
        for i in range(4)
    ]
    host = CardInstance(
        instance_id=990149,
        card_id=990249,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        power=25000,
        has_activate_main=True,
        stacked_card_ids=(990250,),
    )
    state.players[1].battle_area = [host]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=host)

    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    played = state.players[1].battle_area[0]
    assert played.card_id == 990250
    assert played.power == 30000
    assert "Dual Attack" in played.temporary_keywords
    assert any(cp.name == "effect_auto_self_gain_power_for_turn_on_play" for cp in state.checkpoints)


def test_phase4_opponent_main_phase_start_can_play_from_under_self_and_place_self_under_played() -> None:
    class Repo:
        @staticmethod
        def get_by_id(card_id: int, source_table: str = "cards"):
            data = {
                990270: SimpleNamespace(
                    card_name="Universe 7 Gohan",
                    power_int=20000,
                    card_type="BATTLE",
                    card_color="Red",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="2",
                    card_skill_unstyled="",
                    has_awaken=False,
                    card_traits_json='["Universe 7"]',
                    card_character_json='["Son Gohan: Adolescence"]',
                ),
            }
            return data.get(card_id)

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            990269: [
                {
                    "trigger": "owner_opponent_main_phase_start",
                    "handler_id": "auto_play_up_to_n_from_under_self_and_place_self_under_played_card",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "red",
                        "required_traits": "Universe 7",
                        "max_cost": 2,
                        "requires_leader": "if your Leader is a red <Warriors of Universe 7> card",
                    },
                }
            ],
            990270: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_self_gain_power_for_turn_on_play",
                    "handler_params": {
                        "power_delta": 10000,
                        "grant_keyword": "Dual Attack",
                        "requires_played_from": "under",
                        "requires_played_via": "skill",
                    },
                }
            ],
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Red"
    state.players[1].leader_area.traits = ("Warriors of Universe 7",)
    host = CardInstance(
        instance_id=990169,
        card_id=990269,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        power=25000,
        stacked_card_ids=(990270,),
    )
    state.players[1].battle_area = [host]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=host)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))

    played = state.players[1].battle_area[0]
    assert state.phase == TurnPhase.MAIN
    assert played.card_id == 990270
    assert played.stacked_card_ids == (990269,)
    assert played.power == 30000
    assert "Dual Attack" in played.temporary_keywords
    assert any(event.name == "main_phase_start" and event.actor_player_id == 2 for event in state.effect_events)
    assert any(cp.name == "main_phase_begin" for cp in state.checkpoints)
    assert any(cp.name == "effect_auto_play_up_to_n_from_under_self_and_place_self_under_played_card" for cp in state.checkpoints)


def test_phase4_owner_main_phase_start_can_play_from_under_self_and_place_self_under_played() -> None:
    class Repo:
        @staticmethod
        def get_by_id(card_id: int, source_table: str = "cards"):
            data = {
                990272: SimpleNamespace(
                    card_name="Demon Clan Piccolo",
                    power_int=20000,
                    card_type="BATTLE",
                    card_color="Red",
                    energy_cost_int=3,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="3",
                    card_skill_unstyled="",
                    has_awaken=False,
                    card_traits_json='["Demon Clan"]',
                    card_character_json='["Piccolo Jr."]',
                ),
            }
            return data.get(card_id)

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            990271: [
                {
                    "trigger": "owner_main_phase_start",
                    "handler_id": "auto_play_up_to_n_from_under_self_and_place_self_under_played_card",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "red",
                        "required_traits": "Demon Clan",
                        "required_characters": "Piccolo Jr.",
                        "max_cost": 3,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    host = CardInstance(
        instance_id=990171,
        card_id=990271,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        power=25000,
        stacked_card_ids=(990272,),
    )
    state.players[1].battle_area = [host]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=host)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=1))

    played = state.players[1].battle_area[0]
    assert state.phase == TurnPhase.MAIN
    assert played.card_id == 990272
    assert played.stacked_card_ids == (990271,)
    assert any(event.name == "main_phase_start" and event.actor_player_id == 1 for event in state.effect_events)
    assert any(cp.name == "effect_auto_play_up_to_n_from_under_self_and_place_self_under_played_card" for cp in state.checkpoints)


def test_phase4_costed_opponent_main_phase_start_can_pay_energy_to_play_from_under_self() -> None:
    class Repo:
        @staticmethod
        def get_by_id(card_id: int, source_table: str = "cards"):
            data = {
                990274: SimpleNamespace(
                    card_name="Universe 7 Fighter",
                    power_int=20000,
                    card_type="BATTLE",
                    card_color="Red",
                    energy_cost_int=3,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="3",
                    card_skill_unstyled="",
                    has_awaken=False,
                    card_traits_json='["Universe 7"]',
                    card_character_json='["Son Goku"]',
                ),
            }
            return data.get(card_id)

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            990273: [
                {
                    "trigger": "owner_opponent_main_phase_start",
                    "handler_id": "auto_play_up_to_n_from_under_self_and_place_self_under_played_card",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "red",
                        "required_traits": "Universe 7",
                        "max_cost": 3,
                        "requires_leader": "if your Leader is a red <Warriors of Universe 7> card",
                        "min_opponent_energy": 2,
                        "auto_cost_header": "(red)",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Red"
    state.players[1].leader_area.traits = ("Warriors of Universe 7",)
    state.players[1].energy = [
        CardInstance(instance_id=990275, card_id=4001, owner_id=1, card_type="ENERGY", color="Red", energy_cost=0, power=0),
    ]
    state.players[2].energy = [
        CardInstance(instance_id=990276, card_id=4002, owner_id=2, card_type="ENERGY", color="Blue", energy_cost=0, power=0),
        CardInstance(instance_id=990277, card_id=4003, owner_id=2, card_type="ENERGY", color="Blue", energy_cost=0, power=0),
    ]
    host = CardInstance(
        instance_id=990173,
        card_id=990273,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        power=25000,
        stacked_card_ids=(990274,),
    )
    state.players[1].battle_area = [host]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=host)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))

    played = state.players[1].battle_area[0]
    assert played.card_id == 990274
    assert played.stacked_card_ids == (990273,)
    assert state.players[1].energy[0].resting is True
    assert any(cp.name == "effect_auto_header_cost_paid" for cp in state.checkpoints)


def test_phase4_opponent_main_phase_start_can_discard_from_hand_before_playing_from_under_self() -> None:
    class Repo:
        @staticmethod
        def get_by_id(card_id: int, source_table: str = "cards"):
            data = {
                990279: SimpleNamespace(
                    card_name="Universe 7 Support",
                    power_int=15000,
                    card_type="BATTLE",
                    card_color="Red",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="2",
                    card_skill_unstyled="",
                    has_awaken=False,
                    card_traits_json='["Universe 7"]',
                    card_character_json='["Son Goku"]',
                ),
            }
            return data.get(card_id)

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            990278: [
                {
                    "trigger": "owner_opponent_main_phase_start",
                    "handler_id": "auto_play_up_to_n_from_under_self_and_place_self_under_played_card",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "red",
                        "required_traits": "Universe 7",
                        "max_cost": 2,
                        "auto_discard_hand_before": 1,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    discard_card = CardInstance(instance_id=990280, card_id=5001, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1, power=5000)
    state.players[1].hand = [discard_card]
    host = CardInstance(
        instance_id=990178,
        card_id=990278,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        power=20000,
        stacked_card_ids=(990279,),
    )
    state.players[1].battle_area = [host]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=host)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))

    played = state.players[1].battle_area[0]
    assert played.card_id == 990279
    assert played.stacked_card_ids == (990278,)
    assert all(card.instance_id != 991023 for card in state.players[1].hand)
    assert any(card.instance_id == 990280 for card in state.players[1].drop)
    assert any(cp.name == "effect_auto_header_cost_paid" for cp in state.checkpoints)


def test_phase4_owner_main_phase_draw_auto_can_place_self_in_drop_before_resolution() -> None:
    engine = RulesEngine(
        effect_rules={
            990281: [
                {
                    "trigger": "owner_main_phase_start",
                    "handler_id": "auto_draw_n",
                    "handler_params": {
                        "amount": 1,
                        "auto_place_self_in_drop_before": True,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=990181, card_id=990281, owner_id=1, card_type="BATTLE", color="Blue", power=5000)
    state.players[1].battle_area = [source]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    before_hand = len(state.players[1].hand)
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=1))

    assert len(state.players[1].hand) == before_hand + 1
    assert not state.players[1].battle_area
    assert any(card.card_id == 990281 for card in state.players[1].drop)
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_opponent_main_phase_draw_switch_and_keyword_auto_can_pay_discard_and_plus_marker() -> None:
    engine = RulesEngine(
        effect_rules={
            990282: [
                {
                    "trigger": "owner_opponent_main_phase_start",
                    "handler_id": "auto_draw_n_switch_up_to_n_owner_leader_and_energy_active_and_grant_owner_leader_keyword_for_turn",
                    "handler_params": {
                        "amount": 1,
                        "max_leader_targets": 1,
                        "max_energy_targets": 1,
                        "grant_keyword": "Blocker",
                        "auto_discard_hand_before": 1,
                        "auto_marker_delta": 1,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.resting = True
    state.players[1].energy = [
        CardInstance(instance_id=990283, card_id=5002, owner_id=1, card_type="ENERGY", color="Yellow", energy_cost=0, power=0, resting=True),
    ]
    discard_card = CardInstance(instance_id=990284, card_id=5003, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=1, power=5000)
    state.players[1].hand = [discard_card]
    source = CardInstance(
        instance_id=990182,
        card_id=990282,
        owner_id=1,
        card_type="UNISON",
        color="Yellow",
        power=15000,
        markers=1,
    )
    state.players[1].unison_area = [source]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)
    before_hand = len(state.players[1].hand)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))

    assert len(state.players[1].hand) == before_hand
    assert state.players[1].leader_area.resting is False
    assert state.players[1].energy[0].resting is False
    assert "Blocker" in state.players[1].leader_area.temporary_keywords
    assert state.players[1].unison_area[0].markers == 2
    assert any(card.instance_id == 990284 for card in state.players[1].drop)
    assert any(
        cp.name == "effect_auto_draw_n_switch_up_to_n_owner_leader_and_energy_active_and_grant_owner_leader_keyword_for_turn"
        for cp in state.checkpoints
    )


def test_phase4_opponent_main_phase_draw_auto_can_bottom_deck_hand_before_resolution() -> None:
    engine = RulesEngine(
        effect_rules={
            990285: [
                {
                    "trigger": "owner_opponent_main_phase_start",
                    "handler_id": "auto_draw_n",
                    "handler_params": {
                        "amount": 1,
                        "auto_bottom_deck_hand_before": 1,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    moved = CardInstance(instance_id=990286, card_id=5004, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=1, power=5000)
    state.players[1].hand = [moved]
    source = CardInstance(instance_id=990183, card_id=990285, owner_id=1, card_type="BATTLE", color="Blue", power=5000)
    state.players[1].battle_area = [source]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    before_hand = len(state.players[1].hand)
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))

    assert len(state.players[1].hand) == before_hand
    assert state.players[1].deck[-1] == 5004
    assert any(cp.name == "effect_auto_header_cost_paid" for cp in state.checkpoints)


def test_phase4_opponent_main_phase_draw_auto_can_remove_self_from_game_before_resolution() -> None:
    engine = RulesEngine(
        effect_rules={
            990287: [
                {
                    "trigger": "owner_opponent_main_phase_start",
                    "handler_id": "auto_draw_n",
                    "handler_params": {
                        "amount": 1,
                        "auto_remove_self_before": True,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=990184, card_id=990287, owner_id=1, card_type="BATTLE", color="Black", power=5000)
    state.players[1].battle_area = [source]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    before_hand = len(state.players[1].hand)
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))

    assert len(state.players[1].hand) == before_hand + 1
    assert not state.players[1].battle_area
    assert any(card.card_id == 990287 for card in state.players[1].removed_from_game)
    assert any(event.name == "card_removed_from_game" and int(event.payload.get("source_card_id") or -1) == 990287 for event in state.effect_events)


def test_phase4_owner_main_phase_draw_auto_can_release_under_cards_to_drop_before_resolution() -> None:
    engine = RulesEngine(
        effect_rules={
            990288: [
                {
                    "trigger": "owner_main_phase_start",
                    "handler_id": "auto_draw_n",
                    "handler_params": {
                        "amount": 1,
                        "auto_release_under_to_drop_before": 2,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=990185,
        card_id=990288,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        power=5000,
        stacked_card_ids=(5005, 5006, 5007),
    )
    state.players[1].battle_area = [source]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    before_hand = len(state.players[1].hand)
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=1))

    assert len(state.players[1].hand) == before_hand + 1
    assert state.players[1].battle_area[0].stacked_card_ids == (5007,)
    released_ids = {card.card_id for card in state.players[1].drop}
    assert 5005 in released_ids
    assert 5006 in released_ids
    assert any(cp.name == "effect_auto_header_cost_paid" for cp in state.checkpoints)


def test_phase4_opponent_main_phase_start_can_play_from_owner_drop_after_placing_self_in_drop() -> None:
    class Repo:
        @staticmethod
        def get_by_id(card_id: int, source_table: str = "cards"):
            data = {
                991011: SimpleNamespace(
                    card_name="Blue Gogeta",
                    power_int=25000,
                    card_type="BATTLE",
                    card_color="Blue",
                    energy_cost_int=5,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="5",
                    card_skill_unstyled="[Union]",
                    has_awaken=False,
                    card_traits_json='["Saiyan"]',
                    card_character_json='["Gogeta"]',
                ),
            }
            return data.get(card_id)

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            991010: [
                {
                    "trigger": "owner_opponent_main_phase_start",
                    "handler_id": "auto_play_up_to_n_from_owner_drop_on_main_phase_start",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "blue",
                        "required_characters": "Gogeta",
                        "required_skill_text_contains": "[union]",
                        "max_cost": 5,
                        "auto_place_self_in_drop_before": True,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=991012, card_id=991010, owner_id=1, card_type="BATTLE", color="Blue", power=5000)
    played = CardInstance(instance_id=991013, card_id=991011, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=5, power=25000)
    state.players[1].battle_area = [source]
    state.players[1].drop = [played]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))

    assert any(card.card_id == 991010 for card in state.players[1].drop)
    assert any(card.instance_id == 991013 for card in state.players[1].battle_area)
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_drop_on_main_phase_start" for cp in state.checkpoints)


def test_phase4_owner_main_phase_start_can_play_from_owner_hand_in_rest_mode() -> None:
    class Repo:
        @staticmethod
        def get_by_id(card_id: int, source_table: str = "cards"):
            data = {
                991021: SimpleNamespace(
                    card_name="Frost Soldier",
                    power_int=15000,
                    card_type="BATTLE",
                    card_color="Blue",
                    energy_cost_int=4,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="4",
                    card_skill_unstyled="",
                    has_awaken=False,
                    card_traits_json='["Frieza Army"]',
                    card_character_json='["Frost"]',
                ),
            }
            return data.get(card_id)

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            991020: [
                {
                    "trigger": "owner_main_phase_start",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_on_main_phase_start",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "blue",
                        "required_characters": "Frost",
                        "max_cost": 4,
                        "rest_mode": True,
                        "auto_cost_header": "(blue)",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=991022, card_id=6001, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0, power=0),
    ]
    hand_card = CardInstance(instance_id=991023, card_id=991021, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=4, power=15000)
    source = CardInstance(instance_id=991024, card_id=991020, owner_id=1, card_type="BATTLE", color="Blue", power=5000)
    state.players[1].hand = [hand_card]
    state.players[1].battle_area = [source]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=1))

    assert all(card.instance_id != 991023 for card in state.players[1].hand)
    assert any(card.instance_id == 991023 and card.resting for card in state.players[1].battle_area)
    assert state.players[1].energy[0].resting is True
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_hand_on_main_phase_start" for cp in state.checkpoints)


def test_phase4_opponent_main_phase_start_can_switch_owner_multicolor_energy_active() -> None:
    engine = RulesEngine(
        effect_rules={
            991030: [
                {
                    "trigger": "owner_opponent_main_phase_start",
                    "handler_id": "auto_switch_up_to_n_owner_energy_active_on_main_phase_start",
                    "handler_params": {
                        "max_targets": 1,
                        "requires_multicolor": True,
                        "auto_discard_hand_before": 1,
                        "auto_marker_delta": 1,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    discard_card = CardInstance(instance_id=991031, card_id=6002, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=1, power=5000)
    source = CardInstance(instance_id=991032, card_id=991030, owner_id=1, card_type="UNISON", color="Yellow", power=15000, markers=1)
    mono_energy = CardInstance(instance_id=991033, card_id=6003, owner_id=1, card_type="ENERGY", color="Yellow", energy_cost=0, power=0, resting=True)
    multi_energy = CardInstance(instance_id=991034, card_id=6004, owner_id=1, card_type="ENERGY", color="Yellow/Blue", energy_cost=0, power=0, resting=True)
    state.players[1].hand = [discard_card]
    state.players[1].unison_area = [source]
    state.players[1].energy = [mono_energy, multi_energy]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))

    assert not state.players[1].hand
    assert any(card.instance_id == 991031 for card in state.players[1].drop)
    assert state.players[1].unison_area[0].markers == 2
    assert state.players[1].energy[0].resting is True
    assert state.players[1].energy[1].resting is False
    assert any(cp.name == "effect_auto_switch_up_to_n_owner_energy_active_on_main_phase_start" for cp in state.checkpoints)


def test_phase4_owner_main_phase_start_can_play_from_owner_deck_with_markers_in_rest_mode() -> None:
    class Repo:
        @staticmethod
        def get_by_id(card_id: int, source_table: str = "cards"):
            data = {
                992011: SimpleNamespace(
                    card_name="Frieza & Cell, a Match Made in Hell",
                    power_int=15000,
                    card_type="UNISON",
                    card_color="Blue",
                    energy_cost_int=4,
                    combo_cost_int=0,
                    combo_power_int=0,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="4",
                    card_skill_unstyled="",
                    has_awaken=False,
                    card_traits_json="[]",
                    card_character_json='["Frieza & Cell, a Match Made in Hell"]',
                ),
            }
            return data.get(card_id)

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            992010: [
                {
                    "trigger": "owner_main_phase_start",
                    "handler_id": "auto_play_up_to_n_from_owner_deck_on_main_phase_start",
                    "handler_params": {
                        "max_targets": 1,
                        "required_name_contains": "FRIEZA & CELL, A MATCH MADE IN HELL",
                        "markers": 2,
                        "rest_mode": True,
                        "auto_cost_header": "(blue)",
                        "auto_discard_hand_before": 1,
                        "requires_mono_energy": "blue",
                        "requires_leader": "if your leader card and energy are all mono-blue",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Blue"
    state.players[1].energy = [
        CardInstance(instance_id=992012, card_id=6101, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0, power=0),
    ]
    discard_card = CardInstance(instance_id=992013, card_id=6102, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=1, power=5000)
    source = CardInstance(instance_id=992014, card_id=992010, owner_id=1, card_type="BATTLE", color="Blue", power=5000)
    state.players[1].hand = [discard_card]
    state.players[1].deck = [6105, 992011] + state.players[1].deck
    state.players[1].battle_area = [source]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=1))

    assert any(card.instance_id == 992013 for card in state.players[1].drop)
    assert state.players[1].energy[0].resting is True
    assert state.players[1].unison_area
    played = state.players[1].unison_area[0]
    assert played.card_id == 992011
    assert played.markers == 2
    assert played.resting is True
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_deck_on_main_phase_start" for cp in state.checkpoints)


def test_phase4_opponent_main_phase_start_can_switch_self_active_and_gain_keyword_with_owner_battle_or_z_energy_requirement() -> None:
    engine = RulesEngine(
        effect_rules={
            992020: [
                {
                    "trigger": "owner_opponent_main_phase_start",
                    "handler_id": "auto_switch_self_active_and_gain_keyword_for_turn_on_main_phase_start",
                    "handler_params": {
                        "grant_keyword": "Blocker",
                        "required_owner_battle_or_z_energy_allowed_colors": "yellow",
                        "required_owner_battle_or_z_energy_required_characters": "Vegeta",
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=992021, card_id=992020, owner_id=1, card_type="BATTLE", color="Yellow", power=5000, resting=True)
    z_energy = CardInstance(instance_id=992022, card_id=6103, owner_id=1, card_type="Z-ENERGY", color="Yellow", power=0, characters=("Vegeta",))
    state.players[1].battle_area = [source]
    state.players[1].z_energy = [z_energy]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))

    assert state.players[1].battle_area[0].resting is False
    assert "Blocker" in state.players[1].battle_area[0].temporary_keywords
    assert any(cp.name == "effect_auto_switch_self_active_and_gain_keyword_for_turn_on_main_phase_start" for cp in state.checkpoints)


def test_phase4_owner_main_phase_start_can_play_from_owner_hand_on_top_of_self() -> None:
    class Repo:
        @staticmethod
        def get_by_id(card_id: int, source_table: str = "cards"):
            data = {
                992031: SimpleNamespace(
                    card_name="Frost Evolution",
                    power_int=20000,
                    card_type="BATTLE",
                    card_color="Blue",
                    energy_cost_int=4,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="4",
                    card_skill_unstyled="",
                    has_awaken=False,
                    card_traits_json="[]",
                    card_character_json='["Frost"]',
                ),
            }
            return data.get(card_id)

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            992030: [
                {
                    "trigger": "owner_main_phase_start",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_on_top_of_self_on_main_phase_start",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "blue",
                        "required_characters": "Frost",
                        "max_cost": 4,
                        "auto_cost_header": "(blue)(blue)",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=992032, card_id=6201, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0, power=0),
        CardInstance(instance_id=992033, card_id=6202, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0, power=0),
    ]
    source = CardInstance(
        instance_id=992034,
        card_id=992030,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        power=5000,
        stacked_card_ids=(6203,),
    )
    played = CardInstance(instance_id=992035, card_id=992031, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=4, power=20000)
    state.players[1].battle_area = [source]
    state.players[1].hand = [played]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=1))

    assert all(card.instance_id != 992035 for card in state.players[1].hand)
    assert state.players[1].energy[0].resting is True
    assert state.players[1].energy[1].resting is True
    assert state.players[1].battle_area[0].card_id == 992031
    assert state.players[1].battle_area[0].stacked_card_ids == (6203, 992030)
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_hand_on_top_of_self_on_main_phase_start" for cp in state.checkpoints)


def test_phase4_king_cold_combo_can_reduce_next_matching_red_extra_cost() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 2409:
                return SimpleNamespace(
                    card_name="Explosive Dance",
                    power_int=0,
                    card_type="EXTRA",
                    card_color="Red",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=0,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=True,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    z_energy_cost=None,
                    card_energy_cost="1",
                    card_skill_unstyled="",
                    card_traits_json="[]",
                    card_character_json="[]",
                )
            return None

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            20: (
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_reduce_next_matching_extra_skill_cost_from_hand_on_combo",
                    handler_params={
                        "amount": 1,
                        "required_card_type": "EXTRA",
                        "max_energy_cost": 3,
                        "require_mono_color": True,
                        "allowed_colors": "red",
                        "max_owner_life": 3,
                        "requires_opponent_turn": True,
                        "uses_remaining": 1,
                    },
                    limit_per_turn=1,
                    family_id="self_comboed:auto_reduce_next_matching_extra_skill_cost_from_hand_on_combo",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area = [
        CardInstance(instance_id=990020, card_id=720, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=1, power=10000)
    ]
    state.players[2].life = state.players[2].life[:3]
    state.players[2].energy = []
    state.players[2].hand = [
        CardInstance(instance_id=990021, card_id=20, owner_id=2, card_type="BATTLE", color="Red", combo_cost=0, combo_power=10000, power=10000),
        CardInstance(instance_id=990022, card_id=2409, owner_id=2, card_type="EXTRA", color="Red", energy_cost=1, has_activate_battle=True),
    ]
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    combo = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.COMBO_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, combo)
    assert any(cp.name == "effect_auto_reduce_next_matching_extra_skill_cost_from_hand_on_combo" for cp in state.checkpoints)
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0 for a in legal)


def test_phase4_auto_effect_registers_on_play_and_resolves() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880001, card_id=1, owner_id=1, card_type="BATTLE", energy_cost=0, has_auto=True)
    ]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    regs = [r for r in state.effect_registry if r.source_instance_id == 880001]
    assert regs
    assert any(r.trigger == "self_played" for r in regs)
    assert any(r.trigger == "self_attacks" for r in regs)
    assert any(res.resolved for res in state.effect_resolutions)


def test_phase4_activate_main_can_play_self_from_warp_with_marker_override() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            if card_id == 9729:
                return SimpleNamespace(
                    id=9729,
                    card_number="BT29-094",
                    card_name="Zamasu, Scheme",
                    card_type="UNISON",
                    card_color="black",
                    card_energy_cost="X",
                    energy_cost_int=None,
                    combo_cost_int=None,
                    combo_power_int=None,
                    power_int=15000,
                    card_skill_unstyled="[Activate: Main] placeholder",
                    has_activate_main=True,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Zamasu"]',
                )
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="black",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9729: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_warp",
                    "handler_params": {"markers": 0, "required_source_zone": "warp", "min_owner_energy": 2},
                }
            ]
        },
        skill_cost_rules={
            9729: {
                "activate_main_warp": [
                    {
                        "kind": "send_owner_z_energy_to_drop",
                        "amount": 1,
                    }
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[910001],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=700001, card_id=111, owner_id=1, card_type="BATTLE", color="black"),
        CardInstance(instance_id=700002, card_id=112, owner_id=1, card_type="BATTLE", color="black"),
    ]
    state.players[1].z_energy = [
        CardInstance(instance_id=700003, card_id=113, owner_id=1, card_type="BATTLE", color="black")
    ]
    warp_card = CardInstance(
        instance_id=700004,
        card_id=9729,
        owner_id=1,
        card_number="BT29-094",
        card_type="UNISON",
        color="black",
        has_activate_main=True,
        characters=("Zamasu",),
    )
    state.players[1].warp = [warp_card]
    engine._register_card_effects(state, player_id=1, source_zone="warp", card=warp_card)

    activate = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "warp"
    )
    state = engine.apply_action(state, activate)
    assert len(state.players[1].z_energy) == 0
    assert len(state.players[1].drop) == 1
    assert state.counter_window is not None
    assert state.counter_window.pending_action.action_type == "activate_main"

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None
    assert state.counter_window.pending_action.action_type == "play_from_warp"

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert not state.players[1].warp
    assert any(card.instance_id == 700004 for card in state.players[1].drop)
    assert any(cp.name == "main_play_unison" for cp in state.checkpoints)
    assert any(cp.name == "rule_unison_zero_markers" for cp in state.checkpoints)


def test_phase4_activate_main_can_play_battle_self_from_warp() -> None:
    engine = RulesEngine(
        effect_rules={
            9732: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_warp",
                    "handler_params": {"required_source_zone": "warp", "requires_leader": "black", "min_owner_energy": 3},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Black"
    state.players[1].energy = [
        CardInstance(instance_id=700101, card_id=211, owner_id=1, card_type="ENERGY", color="Black"),
        CardInstance(instance_id=700102, card_id=212, owner_id=1, card_type="ENERGY", color="Black"),
        CardInstance(instance_id=700103, card_id=213, owner_id=1, card_type="ENERGY", color="Black"),
    ]
    warp_card = CardInstance(
        instance_id=700104,
        card_id=9732,
        owner_id=1,
        card_number="BT29-097",
        card_type="BATTLE",
        color="Black",
        energy_cost=1,
        power=15000,
        has_activate_main=True,
    )
    state.players[1].warp = [warp_card]
    engine._register_card_effects(state, player_id=1, source_zone="warp", card=warp_card)

    activate = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "warp"
    )
    state = engine.apply_action(state, activate)
    assert state.counter_window is not None
    assert state.counter_window.pending_action.action_type == "activate_main"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None
    assert state.counter_window.pending_action.action_type == "play_from_warp"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert not state.players[1].warp
    assert any(card.instance_id == 700104 for card in state.players[1].battle_area)
    assert any(cp.name == "counter_timing_play_from_skill" for cp in state.checkpoints)
    assert any(cp.name == "main_play_battle" for cp in state.checkpoints)


def test_phase4_ex_evolve_can_play_matching_battle_from_hand_on_top_of_owner_battle() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            if card_id == 9637:
                return SimpleNamespace(
                    id=9637,
                    card_number="BT29-006",
                    card_name="SS Son Goten, Demon Resistance",
                    card_type="BATTLE",
                    card_color="red",
                    card_energy_cost="3",
                    energy_cost_int=3,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=20000,
                    card_skill_unstyled=(
                        "[Deflect][Double Strike]\n"
                        "[EX-Evolve][Limit 1]{r} : Red <Son Goten> card with an energy cost of 1.\n"
                        "[Auto] When this card is played, draw 1 card."
                    ),
                    has_activate_main=False,
                    has_auto=True,
                    has_draw=True,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=("Deflect", "Double Strike"),
                    card_traits_json='[]',
                    card_character_json='["Son Goten"]',
                )
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="red",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='["Son Goten"]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9637: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
                {"trigger": "self_played", "handler_id": "auto_switch_self_active_on_play", "handler_params": {}},
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=700120, card_id=301, owner_id=1, card_type="ENERGY", color="Red"),
    ]
    state.players[1].battle_area = [
        CardInstance(
            instance_id=700121,
            card_id=302,
            owner_id=1,
            card_number="BT29-007",
            card_type="BATTLE",
            color="Red",
            energy_cost=1,
            power=5000,
            resting=True,
            characters=("Son Goten",),
        )
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=700122,
            card_id=9637,
            owner_id=1,
            card_number="BT29-006",
            card_type="BATTLE",
            color="Red",
            energy_cost=3,
            power=20000,
            skill_text_raw=(
                "[Deflect][Double Strike]\n"
                "[EX-Evolve][Limit 1]{r} : Red <Son Goten> card with an energy cost of 1.\n"
                "[Auto] When this card is played, draw 1 card."
            ),
            characters=("Son Goten",),
        )
    ]
    deck_before = len(state.players[1].deck)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.EX_EVOLVE)
    state = engine.apply_action(state, action)

    evolved = state.players[1].battle_area[0]
    assert evolved.instance_id == 700122
    assert evolved.resting is False
    assert evolved.stacked_card_ids == (302,)
    assert all(card.instance_id != 700122 for card in state.players[1].hand)
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "ex_evolve" for cp in state.checkpoints)
    assert any(cp.name == "effect_auto_switch_self_active_on_play" for cp in state.checkpoints)
    assert any(res.resolved for res in state.effect_resolutions if res.reason == "ok")


def test_phase4_tiny_golden_warrior_can_enable_next_matching_ex_evolve_from_drop() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            rows = {
                9660: SimpleNamespace(
                    id=9660,
                    card_number="BT29-027",
                    card_name="Tiny Golden Warrior",
                    card_type="EXTRA",
                    card_color="red",
                    card_energy_cost="0",
                    energy_cost_int=0,
                    combo_cost_int=None,
                    combo_power_int=None,
                    power_int=0,
                    card_skill_unstyled=(
                        "[Permanent] This card gains ≪Earthling≫ in all areas.\n"
                        "[Activate: Main][Limit 1] If your Leader is a red <Krillin> card : "
                        "The next time you activate [EX-Evolve] on your red <Son Goten> or <Trunks : Youth> card during this turn, "
                        "it can also activate from its owner's Drop."
                    ),
                    has_activate_main=True,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=True,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='["Earthling"]',
                    card_character_json='[]',
                ),
                9639: SimpleNamespace(
                    id=9639,
                    card_number="BT29-008",
                    card_name="SS Trunks, Demon Resistance",
                    card_type="BATTLE",
                    card_color="red",
                    card_energy_cost="3",
                    energy_cost_int=3,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=20000,
                    card_skill_unstyled=(
                        "[Deflect][Blocker]\n"
                        "[EX-Evolve][Limit 1]{r} : Red <Trunks : Youth> card with an energy cost of 1.\n"
                        "[Auto] When this card is played, draw 1 card."
                    ),
                    has_activate_main=False,
                    has_auto=True,
                    has_draw=True,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=("Deflect", "Blocker"),
                    card_traits_json='[]',
                    card_character_json='["Trunks : Youth"]',
                ),
            }
            if card_id in rows:
                return rows[card_id]
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="red",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='["Trunks : Youth"]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9660: [
                {
                    "trigger": "self_activate_extra_from_hand",
                    "handler_id": "activate_grant_next_ex_evolve_from_owner_drop",
                    "handler_params": {
                        "uses_remaining": 1,
                        "allowed_colors": "red",
                        "required_characters": "Son Goten,Trunks : Youth",
                    },
                    "limit_per_turn": 1,
                }
            ],
            9639: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ],
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Red"
    state.players[1].leader_area.characters = ("Krillin",)
    state.players[1].energy = [
        CardInstance(instance_id=700130, card_id=401, owner_id=1, card_type="ENERGY", color="Red"),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=700131,
            card_id=9660,
            owner_id=1,
            card_number="BT29-027",
            card_type="EXTRA",
            color="Red",
            energy_cost=0,
        )
    ]
    play_extra = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play_extra)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert len(state.ex_evolve_permissions) == 1
    state.players[1].battle_area = [
        CardInstance(
            instance_id=700132,
            card_id=402,
            owner_id=1,
            card_number="BT29-009",
            card_type="BATTLE",
            color="Red",
            energy_cost=1,
            power=5000,
            resting=False,
            characters=("Trunks : Youth",),
        )
    ]
    state.players[1].drop = [
        CardInstance(instance_id=700131, card_id=9660, owner_id=1, card_type="EXTRA", color="Red"),
        CardInstance(
            instance_id=700133,
            card_id=9639,
            owner_id=1,
            card_number="BT29-008",
            card_type="BATTLE",
            color="Red",
            energy_cost=3,
            power=20000,
            skill_text_raw=(
                "[Deflect][Blocker]\n"
                "[EX-Evolve][Limit 1]{r} : Red <Trunks : Youth> card with an energy cost of 1.\n"
                "[Auto] When this card is played, draw 1 card."
            ),
            characters=("Trunks : Youth",),
        ),
    ]
    deck_before = len(state.players[1].deck)

    ex_evolve = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.EX_EVOLVE and a.source_zone == "drop"
    )
    state = engine.apply_action(state, ex_evolve)

    assert state.players[1].battle_area[0].instance_id == 700133
    assert state.players[1].battle_area[0].stacked_card_ids == (402,)
    assert len(state.players[1].deck) == deck_before - 1
    assert not state.ex_evolve_permissions
    assert any(cp.name == "effect_activate_grant_next_ex_evolve_from_owner_drop" for cp in state.checkpoints)
    assert any(cp.name == "ex_evolve" for cp in state.checkpoints)


def test_phase4_jaguars_island_challenge_stage_adds_marker_when_matching_extra_is_activated_from_hand() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            rows = {
                9633: SimpleNamespace(
                    id=9633,
                    card_number="BT29-003",
                    card_name="Jaguar's Island, Challenge Stage",
                    card_type="Z-UNISON",
                    card_color="red",
                    card_energy_cost="-",
                    energy_cost_int=None,
                    combo_cost_int=None,
                    combo_power_int=None,
                    power_int=0,
                    card_skill_unstyled=(
                        "[Auto] When you activate a red ≪Earthling≫ Extra from your hand, add 1 marker to this card. "
                        "[UNISON -3][Activate: Main/Battle] If your Leader is a red <Krillin> card and you place 4 red ≪Earthling≫ Extras from your Drop at the bottom of their owner's deck : "
                        "The next time you activate an [Activate] skill on a red Extra from your hand during this turn, reduce the skill cost by {1}."
                    ),
                    has_activate_main=True,
                    has_activate_battle=True,
                    has_auto=True,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=True,
                    has_barrier=True,
                    keywords=("Barrier",),
                    card_traits_json="[]",
                    card_character_json="[]",
                ),
                9634: SimpleNamespace(
                    id=9634,
                    card_number="BT29-004",
                    card_name="Red Earthling Extra",
                    card_type="EXTRA",
                    card_color="red",
                    card_energy_cost="0",
                    energy_cost_int=0,
                    combo_cost_int=None,
                    combo_power_int=None,
                    power_int=0,
                    card_skill_unstyled="[Activate: Main] Draw 1 card.",
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='["Earthling"]',
                    card_character_json="[]",
                ),
            }
            return rows.get(
                card_id,
                SimpleNamespace(
                    id=card_id,
                    card_number=f"T-{card_id}",
                    card_name=f"Card {card_id}",
                    card_type="BATTLE",
                    card_color="red",
                    card_energy_cost="0",
                    energy_cost_int=0,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=5000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json="[]",
                    card_character_json="[]",
                ),
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9633: [
                {
                    "trigger": "owner_activate_extra_from_hand",
                    "handler_id": "auto_add_markers_on_owner_activate_extra_from_hand",
                    "handler_params": {
                        "amount": 1,
                        "required_card_type": "EXTRA",
                        "allowed_colors": "red",
                        "required_traits": "Earthling",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    stage = CardInstance(instance_id=700140, card_id=9633, owner_id=1, card_number="BT29-003", card_type="Z-UNISON", color="Red", markers=1)
    state.players[1].unison_area = [stage]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=stage)
    state.players[1].hand = [
        CardInstance(instance_id=700141, card_id=9634, owner_id=1, card_number="BT29-004", card_type="EXTRA", color="Red", energy_cost=0)
    ]

    play_extra = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play_extra)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert state.players[1].unison_area[0].markers == 2
    assert any(cp.name == "effect_auto_add_markers_on_owner_activate_extra_from_hand" for cp in state.checkpoints)


def test_phase4_jaguars_island_challenge_stage_reduces_next_matching_extra_cost_from_hand() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            rows = {
                1: SimpleNamespace(
                    id=1,
                    card_number="BT29-001",
                    card_name="Krillin",
                    card_type="LEADER",
                    card_color="red",
                    card_energy_cost="-",
                    energy_cost_int=None,
                    combo_cost_int=None,
                    combo_power_int=None,
                    power_int=10000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json="[]",
                    card_character_json='["Krillin"]',
                ),
                9633: SimpleNamespace(
                    id=9633,
                    card_number="BT29-003",
                    card_name="Jaguar's Island, Challenge Stage",
                    card_type="Z-UNISON",
                    card_color="red",
                    card_energy_cost="-",
                    energy_cost_int=None,
                    combo_cost_int=None,
                    combo_power_int=None,
                    power_int=0,
                    card_skill_unstyled=(
                        "[Auto] When you activate a red ≪Earthling≫ Extra from your hand, add 1 marker to this card. "
                        "[UNISON -3][Activate: Main/Battle] If your Leader is a red <Krillin> card and you place 4 red ≪Earthling≫ Extras from your Drop at the bottom of their owner's deck : "
                        "The next time you activate an [Activate] skill on a red Extra from your hand during this turn, reduce the skill cost by {1}."
                    ),
                    has_activate_main=True,
                    has_activate_battle=True,
                    has_auto=True,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=True,
                    has_barrier=True,
                    keywords=("Barrier",),
                    card_traits_json="[]",
                    card_character_json="[]",
                ),
                9634: SimpleNamespace(
                    id=9634,
                    card_number="BT29-004",
                    card_name="Red Earthling Extra",
                    card_type="EXTRA",
                    card_color="red",
                    card_energy_cost="1",
                    energy_cost_int=1,
                    combo_cost_int=None,
                    combo_power_int=None,
                    power_int=0,
                    card_skill_unstyled="[Activate: Main] Draw 1 card.",
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='["Earthling"]',
                    card_character_json="[]",
                ),
            }
            return rows.get(
                card_id,
                SimpleNamespace(
                    id=card_id,
                    card_number=f"T-{card_id}",
                    card_name=f"Card {card_id}",
                    card_type="BATTLE",
                    card_color="red",
                    card_energy_cost="0",
                    energy_cost_int=0,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=5000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json="[]",
                    card_character_json="[]",
                ),
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9633: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_reduce_next_matching_extra_skill_cost_from_hand",
                    "handler_params": {
                        "amount": 1,
                        "uses_remaining": 1,
                        "required_card_type": "EXTRA",
                        "allowed_colors": "red",
                        "requires_leader": "red <Krillin>",
                    },
                }
            ],
        },
        skill_cost_rules={
            9633: {
                "activate_main_unison": [
                    {"kind": "remove_markers", "amount": 3},
                    {
                        "kind": "send_owner_drop_to_bottom_deck",
                        "amount": 4,
                        "required_card_types": "EXTRA",
                        "allowed_colors": "red",
                        "required_traits": "earthling",
                    },
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Red"
    state.players[1].leader_area.characters = ("Krillin",)
    state.players[1].unison_area = [
        CardInstance(
            instance_id=700150,
            card_id=9633,
            owner_id=1,
            card_number="BT29-003",
            card_type="Z-UNISON",
            color="Red",
            markers=4,
            has_activate_main=True,
        )
    ]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=state.players[1].unison_area[0])
    state.players[1].drop = [
        CardInstance(instance_id=700151 + i, card_id=9634, owner_id=1, card_type="EXTRA", color="Red", traits=("Earthling",))
        for i in range(4)
    ]
    state.players[1].hand = [
        CardInstance(instance_id=700160, card_id=9634, owner_id=1, card_number="BT29-004", card_type="EXTRA", color="Red", energy_cost=1)
    ]
    deck_before = len(state.players[1].deck)

    activate = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert len(state.activate_extra_cost_reductions) == 1
    assert state.players[1].unison_area[0].markers == 1
    assert not state.players[1].drop
    assert len(state.players[1].deck) == deck_before + 4

    play_extra = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play_extra)

    assert not state.activate_extra_cost_reductions
    assert state.counter_window is not None
    assert state.counter_window.kind == "activate_extra_from_hand"
    assert any(cp.name == "effect_activate_reduce_next_matching_extra_skill_cost_from_hand" for cp in state.checkpoints)


def test_phase4_activate_battle_can_reduce_next_matching_arrival_skill_cost_from_hand() -> None:
    engine = RulesEngine(
        effect_rules={
            999330: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "activate_reduce_next_matching_arrival_skill_cost_from_hand",
                    "handler_params": {
                        "uses_remaining": 1,
                        "required_arrival_colors": "red,green",
                        "required_characters": "Vegeta,Trunks: Future",
                        "max_energy_cost": 5,
                        "reduction_cost_token": "Red",
                    },
                }
            ],
            999331: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ],
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    source = CardInstance(
        instance_id=700180,
        card_id=999330,
        owner_id=1,
        card_type="BATTLE",
        color="Green",
        energy_cost=2,
        power=15000,
        has_activate_battle=True,
    )
    combo_card = CardInstance(
        instance_id=700181,
        card_id=9371,
        owner_id=1,
        card_type="BATTLE",
        color="Red/Green",
        combo_cost=0,
        combo_power=5000,
    )
    arrival = CardInstance(
        instance_id=700182,
        card_id=999331,
        owner_id=1,
        card_type="BATTLE",
        color="Red/Green",
        energy_cost=5,
        power=20000,
        characters=("Vegeta",),
        skill_text_raw="[Arrival Red/Green](Red)(Green)\n[Auto] When this card is played, draw 1 card.",
    )
    state.players[1].battle_area = [source]
    state.players[1].hand = [combo_card, arrival]
    state.players[1].energy = [CardInstance(instance_id=700183, card_id=9372, owner_id=1, card_type="BATTLE", color="Green")]
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=source.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.OFFENSE
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    deck_before = len(state.players[1].deck)

    combo_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo_action)
    assert not any(a.action_type == ActionType.ARRIVAL for a in engine.get_legal_actions(state, 1))

    activate = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert len(state.activate_arrival_cost_reductions) == 1
    assert any(cp.name == "effect_activate_reduce_next_matching_arrival_skill_cost_from_hand" for cp in state.checkpoints)

    arrival_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ARRIVAL)
    state = engine.apply_action(state, arrival_action)
    assert not state.activate_arrival_cost_reductions
    assert state.counter_window is not None
    assert state.players[1].energy[0].resting is True

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(card.instance_id == 700182 for card in state.players[1].battle_area)
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_pursuit_activate_main_can_discard_self_and_add_matching_ex_evolve_from_deck_to_hand() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            rows = {
                1: SimpleNamespace(
                    id=1,
                    card_number="BT29-001",
                    card_name="Krillin",
                    card_type="LEADER",
                    card_color="red",
                    card_energy_cost="-",
                    energy_cost_int=None,
                    combo_cost_int=None,
                    combo_power_int=None,
                    power_int=10000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Krillin"]',
                ),
                9638: SimpleNamespace(
                    id=9638,
                    card_number="BT29-007",
                    card_name="Son Goten, Pursuit",
                    card_type="BATTLE",
                    card_color="red",
                    card_energy_cost="1",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=4000,
                    card_skill_unstyled=(
                        "[Auto] When this card is played, draw 1 card.\n"
                        "[Activate: Main][Limit 1] If your Leader is a red <Krillin> card and you discard this card from your hand : "
                        "Add up to 1 red <Son Goten> card with an energy cost of 3 and [EX-Evolve] from your deck to your hand, then shuffle your deck."
                    ),
                    has_activate_main=True,
                    has_auto=True,
                    has_draw=True,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Son Goten"]',
                ),
                9637: SimpleNamespace(
                    id=9637,
                    card_number="BT29-006",
                    card_name="SS Son Goten, Demon Resistance",
                    card_type="BATTLE",
                    card_color="red",
                    card_energy_cost="3",
                    energy_cost_int=3,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=20000,
                    card_skill_unstyled=(
                        "[Deflect][Double Strike]\n"
                        "[EX-Evolve][Limit 1]{r} : Red <Son Goten> card with an energy cost of 1.\n"
                        "[Auto] When this card is played, draw 1 card and switch this card to Active Mode."
                    ),
                    has_activate_main=False,
                    has_auto=True,
                    has_draw=True,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=("Deflect", "Double Strike"),
                    card_traits_json='[]',
                    card_character_json='["Son Goten"]',
                ),
            }
            if card_id in rows:
                return rows[card_id]
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="red",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9638: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "limit_per_turn": 1},
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_add_up_to_n_from_owner_deck_to_hand",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "red",
                        "required_characters": "Son Goten",
                        "max_cost": 3,
                        "requires_leader": "if your leader is a red <krillin> card and you discard this card from your hand",
                    },
                    "limit_per_turn": 1,
                },
            ],
        },
        skill_cost_rules={
            9638: {
                "activate_main_hand": [
                    {"kind": "send_self_from_hand_to_drop", "amount": 1},
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Red"
    state.players[1].leader_area.characters = ("Krillin",)
    state.players[1].energy = [
        CardInstance(instance_id=700150, card_id=501, owner_id=1, card_type="ENERGY", color="Red"),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=700151,
            card_id=9638,
            owner_id=1,
            card_number="BT29-007",
            card_type="BATTLE",
            color="Red",
            energy_cost=1,
            power=4000,
            has_activate_main=True,
            skill_text_raw=(
                "[Auto] When this card is played, draw 1 card.\n"
                "[Activate: Main][Limit 1] If your Leader is a red <Krillin> card and you discard this card from your hand : "
                "Add up to 1 red <Son Goten> card with an energy cost of 3 and [EX-Evolve] from your deck to your hand, then shuffle your deck."
            ),
            characters=("Son Goten",),
        )
    ]
    state.players[1].deck = [9637, 1100, 1101]

    activate = next(
        action
        for action in engine.get_legal_actions(state, 1)
        if action.action_type == ActionType.ACTIVATE_MAIN_SKILL and action.source_zone == "hand"
    )
    state = engine.apply_action(state, activate)
    assert any(card.instance_id == 700151 for card in state.players[1].drop)
    assert not state.players[1].hand

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(card.card_id == 9637 for card in state.players[1].hand)
    assert any(cp.name == "effect_activate_add_up_to_n_from_owner_deck_to_hand" for cp in state.checkpoints)


def test_phase4_activate_main_search_can_negate_that_skill_for_game() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            if card_id == 9801:
                return SimpleNamespace(
                    id=9801,
                    card_number="T-9801",
                    card_name="Potara Test",
                    card_type="EXTRA",
                    card_color="Green",
                    card_energy_cost="1",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=0,
                    power_int=0,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json="[]",
                    card_character_json="[]",
                )
            return None

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            8039: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_add_up_to_n_from_owner_deck_to_hand",
                    "handler_params": {
                        "max_targets": 1,
                        "required_name_contains": "Potara",
                        "negate_self_skill_for_game": True,
                    },
                }
            ],
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=8039,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.has_activate_main = True
    state.players[1].deck = [9801, 9802]

    legal_before = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "leader"
    ]
    assert legal_before
    state = engine.apply_action(state, legal_before[0])
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(card.card_id == 9801 for card in state.players[1].hand)
    legal_after = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "leader"
    ]
    assert not legal_after
    assert any(cp.name == "effect_activate_add_up_to_n_from_owner_deck_to_hand" for cp in state.checkpoints)


def test_phase4_negate_self_skill_for_game_applies_to_non_search_activate_family() -> None:
    engine = RulesEngine(
        effect_rules={
            999001: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_switch_self_active_and_gain_power_for_turn",
                    "handler_params": {"power_delta": 5000, "negate_self_skill_for_game": True},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=9990011,
        card_id=999001,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        power=15000,
        resting=True,
        has_activate_main=True,
    )
    state.players[1].battle_area.append(source)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    legal_before = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    ]
    assert legal_before

    state = engine.apply_action(state, legal_before[0])
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    resolved = next(card for card in state.players[1].battle_area if card.instance_id == 9990011)
    assert resolved.resting is False
    assert resolved.power == 20000
    assert len(state.permanently_negated_skills) == 1
    assert any(cp.name == "effect_skill_negated_for_game" for cp in state.checkpoints)

    legal_after = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    ]
    assert not legal_after


def test_phase4_public_auto_can_permanently_restrict_matching_copy_auto_for_game() -> None:
    engine = RulesEngine(
        effect_rules={
            999011: [
                {
                    "trigger": "owner_leader_attacks",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    first = CardInstance(
        instance_id=9990111,
        card_id=999011,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        has_auto=True,
        skill_text_raw=(
            "[Auto] When your Leader Card attacks, draw 1 card. "
            "You can't activate the [Auto] skill on copies of this card for the game."
        ),
    )
    second = CardInstance(
        instance_id=9990112,
        card_id=999011,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        has_auto=True,
        skill_text_raw=(
            "[Auto] When your Leader Card attacks, draw 1 card. "
            "You can't activate the [Auto] skill on copies of this card for the game."
        ),
    )
    state.players[1].battle_area = [first]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=first)
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={
            "attacker_instance_id": state.players[1].leader_area.instance_id,
            "attacker_zone": "leader",
            "target_player_id": 2,
            "target_zone": "leader",
        },
    )
    engine._resolve_pending_effects(state)

    deck_after_first = len(state.players[1].deck)
    assert len(state.permanent_skill_activation_restrictions) == 1
    assert any(cp.name == "effect_auto_copies_restricted_for_game" for cp in state.checkpoints)

    state.players[1].battle_area.append(second)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=second)
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={
            "attacker_instance_id": state.players[1].leader_area.instance_id,
            "attacker_zone": "leader",
            "target_player_id": 2,
            "target_zone": "leader",
        },
    )
    engine._resolve_pending_effects(state)

    assert len(state.players[1].deck) == deck_after_first
    blocked = [
        row
        for row in state.effect_resolutions
        if row.reason == "permanent_skill_activation_restricted"
    ]
    assert blocked
    assert any(cp.name == "effect_permanent_skill_activation_restricted" for cp in state.checkpoints)


def test_phase4_secret_auto_opportunity_is_preblocked_after_permanent_auto_copy_lock() -> None:
    engine = RulesEngine(
        effect_rules={
            999012: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card1 = CardInstance(
        instance_id=9990121,
        card_id=999012,
        owner_id=1,
        card_type="BATTLE",
        has_auto=True,
        skill_text_raw=(
            "[Auto] When this card is played, draw 1 card. "
            "You can't activate the [Auto] skill on copies of this card for the game."
        ),
    )
    card2 = CardInstance(
        instance_id=9990122,
        card_id=999012,
        owner_id=1,
        card_type="BATTLE",
        has_auto=True,
        skill_text_raw=(
            "[Auto] When this card is played, draw 1 card. "
            "You can't activate the [Auto] skill on copies of this card for the game."
        ),
    )
    state.players[1].hand = [card1, card2]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card1)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 9990121, "source_card_id": 999012, "source_zone": "battle", "played_from": "hand"},
    )
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))

    assert len(state.permanent_skill_activation_restrictions) == 1
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card2)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 9990122, "source_card_id": 999012, "source_zone": "battle", "played_from": "hand"},
    )

    latest = state.secret_auto_opportunities[-1]
    assert latest.source_instance_id == 9990122
    assert latest.status == "blocked_permanent_restriction"
    assert all(row.action_type != ActionType.DECLARE_SECRET_AUTO for row in engine.get_legal_actions(state, 1))
    assert any(cp.name == "secret_auto_opportunity_preblocked" for cp in state.checkpoints)


def test_phase4_public_auto_copy_lock_for_turn_blocks_matching_copies_and_expires() -> None:
    def _mark_one(state, event, reg):
        state.log.append(f"mark_one:{reg.source_instance_id}")

    def _mark_two(state, event, reg):
        state.log.append(f"mark_two:{reg.source_instance_id}")

    engine = RulesEngine(
        effect_handlers={"mark_one": _mark_one, "mark_two": _mark_two},
        effect_rules={
            999013: (
                EffectRule(
                    trigger="owner_leader_attacks",
                    handler_id="mark_one",
                    handler_params={},
                    family_id="owner_leader_attacks:mark_one",
                    provenance="test",
                    source_text=(
                        "[Auto] When your Leader Card attacks, draw 1 card, and you can't activate copies of "
                        "this card for the turn."
                    ),
                ),
                EffectRule(
                    trigger="owner_leader_attacks",
                    handler_id="mark_two",
                    handler_params={},
                    family_id="owner_leader_attacks:mark_two",
                    provenance="test",
                    source_text="[Auto] When your Leader Card attacks, draw 2 cards.",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    first = CardInstance(
        instance_id=9990131,
        card_id=999013,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_auto=True,
        skill_text_raw="[Auto] Mixed test card.",
    )
    second = CardInstance(
        instance_id=9990132,
        card_id=999013,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_auto=True,
        skill_text_raw="[Auto] Mixed test card.",
    )
    state = _to_main(engine, state)
    state.players[1].battle_area = [first, second]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=first)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=second)

    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={
            "attacker_instance_id": state.players[1].leader_area.instance_id,
            "attacker_zone": "leader",
            "target_player_id": 2,
            "target_zone": "leader",
        },
    )
    engine._resolve_pending_effects(state)
    first_marks = [row for row in state.log if row.startswith("mark_")]
    assert first_marks == [
        "mark_one:9990131",
        "mark_two:9990131",
        "mark_one:9990132",
        "mark_two:9990132",
    ]
    assert any(cp.name == "effect_auto_copies_restricted_for_turn" for cp in state.checkpoints)

    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={
            "attacker_instance_id": state.players[1].leader_area.instance_id,
            "attacker_zone": "leader",
            "target_player_id": 2,
            "target_zone": "leader",
        },
    )
    engine._resolve_pending_effects(state)
    second_marks = [row for row in state.log if row.startswith("mark_")]
    assert second_marks == [
        "mark_one:9990131",
        "mark_two:9990131",
        "mark_one:9990132",
        "mark_two:9990132",
        "mark_two:9990131",
        "mark_two:9990132",
    ]
    blocked = [row for row in state.effect_resolutions if row.reason == "temporary_skill_activation_restricted"]
    assert len(blocked) == 2
    assert any(cp.name == "effect_temporary_skill_activation_restricted" for cp in state.checkpoints)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    state = _to_main(engine, state)

    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={
            "attacker_instance_id": state.players[1].leader_area.instance_id,
            "attacker_zone": "leader",
            "target_player_id": 2,
            "target_zone": "leader",
        },
    )
    engine._resolve_pending_effects(state)
    third_marks = [row for row in state.log if row.startswith("mark_")]
    assert third_marks == [
        "mark_one:9990131",
        "mark_two:9990131",
        "mark_one:9990132",
        "mark_two:9990132",
        "mark_two:9990131",
        "mark_two:9990132",
        "mark_one:9990131",
        "mark_two:9990131",
        "mark_one:9990132",
        "mark_two:9990132",
    ]


def test_phase4_secret_auto_opportunity_is_preblocked_after_temporary_auto_copy_lock() -> None:
    engine = RulesEngine(
        effect_rules={
            999014: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card1 = CardInstance(
        instance_id=9990141,
        card_id=999014,
        owner_id=1,
        card_type="BATTLE",
        has_auto=True,
        skill_text_raw=(
            "[Auto] When this card is played, draw 1 card. "
            "You can't activate the [Auto] skill on copies of this card for the turn."
        ),
    )
    card2 = CardInstance(
        instance_id=9990142,
        card_id=999014,
        owner_id=1,
        card_type="BATTLE",
        has_auto=True,
        skill_text_raw=(
            "[Auto] When this card is played, draw 1 card. "
            "You can't activate the [Auto] skill on copies of this card for the turn."
        ),
    )
    state.players[1].hand = [card1, card2]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card1)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 9990141, "source_card_id": 999014, "source_zone": "battle", "played_from": "hand"},
    )
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))

    assert any(cp.name == "effect_auto_copies_restricted_for_turn" for cp in state.checkpoints)
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card2)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 9990142, "source_card_id": 999014, "source_zone": "battle", "played_from": "hand"},
    )

    latest = state.secret_auto_opportunities[-1]
    assert latest.status == "blocked_temporary_restriction"
    assert latest.preblocked is True
    assert any(cp.name == "secret_auto_opportunity_preblocked" for cp in state.checkpoints)


def test_phase4_cross_dimensional_fighting_spirit_can_warp_on_play_and_buff_on_activate() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            rows = {
                2140: SimpleNamespace(
                    id=2140,
                    card_number="BT22-116",
                    card_name="SS4 Son Goku, Cross-Dimensional Fighting Spirit",
                    card_type="Z-BATTLE",
                    card_color="black",
                    card_energy_cost="1",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=10000,
                    power_int=15000,
                    card_skill_unstyled=(
                        "[Auto] When this card is played, choose up to 1 of your opponent's Battle Cards and send it to its owner's Warp.\n"
                        "[Activate: Main][Once per turn] If you have 3 or more energy and you remove 10 total cards in your Drop and Warp from the game: "
                        "This card gets +10000 power and [Double Strike] for the turn."
                    ),
                    has_activate_main=True,
                    has_auto=True,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Son Goku"]',
                ),
            }
            if card_id in rows:
                return rows[card_id]
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="black",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            2140: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_send_up_to_n_opponent_battle_to_warp_on_play",
                    "handler_params": {"max_targets": 1, "target_policy": "first"},
                },
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_gain_power_and_keyword_for_turn",
                    "handler_params": {"power_delta": 10000, "grant_keyword": "Double Strike", "min_owner_energy": 3},
                    "once_per_turn": True,
                },
            ]
        },
        skill_cost_rules={
            2140: {
                "activate_main": [
                    {"kind": "send_owner_drop_and_warp_to_removed", "amount": 10},
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=700200, card_id=601, owner_id=1, card_type="ENERGY", color="Black"),
        CardInstance(instance_id=700201, card_id=602, owner_id=1, card_type="ENERGY", color="Black"),
        CardInstance(instance_id=700202, card_id=603, owner_id=1, card_type="ENERGY", color="Black"),
        CardInstance(instance_id=700203, card_id=604, owner_id=1, card_type="ENERGY", color="Black"),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=700204,
            card_id=2140,
            owner_id=1,
            card_number="BT22-116",
            card_type="Z-BATTLE",
            color="Black",
            energy_cost=1,
            power=15000,
            has_activate_main=True,
            skill_text_raw=(
                "[Auto] When this card is played, choose up to 1 of your opponent's Battle Cards and send it to its owner's Warp.\n"
                "[Activate: Main][Once per turn] If you have 3 or more energy and you remove 10 total cards in your Drop and Warp from the game: "
                "This card gets +10000 power and [Double Strike] for the turn."
            ),
            characters=("Son Goku",),
        )
    ]
    state.players[1].drop = [
        CardInstance(instance_id=700210 + i, card_id=700 + i, owner_id=1, card_type="BATTLE", color="Black")
        for i in range(6)
    ]
    state.players[1].warp = [
        CardInstance(instance_id=700220 + i, card_id=800 + i, owner_id=1, card_type="BATTLE", color="Black")
        for i in range(4)
    ]
    state.players[2].battle_area = [
        CardInstance(instance_id=700230, card_id=900, owner_id=2, card_type="BATTLE", color="Red", energy_cost=4, power=20000)
    ]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert not state.players[2].battle_area
    assert any(card.instance_id == 700230 for card in state.players[2].warp)
    assert any(cp.name == "effect_auto_send_up_to_n_opponent_battle_to_warp_on_play" for cp in state.checkpoints)

    activate = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    source = next(card for card in state.players[1].battle_area if card.instance_id == 700204)
    assert source.power == 25000
    assert "Double Strike" in source.temporary_keywords
    assert len(state.players[1].drop) + len(state.players[1].warp) == 0
    assert len(state.players[1].removed_from_game) == 10
    assert any(cp.name == "effect_activate_gain_power_and_keyword_for_turn" for cp in state.checkpoints)

def test_phase4_kahseral_activate_battle_can_switch_matching_owner_battles_active() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            if card_id == 1:
                return SimpleNamespace(
                    id=1,
                    card_number="BT14-L",
                    card_name="Leader",
                    card_type="LEADER",
                    card_color="red",
                    card_energy_cost="-",
                    energy_cost_int=None,
                    combo_cost_int=None,
                    combo_power_int=None,
                    power_int=10000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='["Universe 11"]',
                    card_character_json='[]',
                )
            if card_id == 11:
                return SimpleNamespace(
                    id=11,
                    card_number="BT14-026",
                    card_name="Kahseral, Warrior of Universe 11",
                    card_type="BATTLE",
                    card_color="red",
                    card_energy_cost="2",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=15000,
                    card_skill_unstyled=(
                        "[Deflect][Blocker]\n"
                        "[Permanent] If this card would be removed from your Battle Area by an opponent's skill, you may add 1 card from your life to your hand instead.\n"
                        "[Activate: Battle][Once per turn] If your Leader Card is a red ≪Universe 11≫ card: "
                        "Choose up to 2 of your red ≪Universe 11≫ cards with energy costs of 1 and 10000 power or less in your Battle Area and switch them to Active Mode."
                    ),
                    has_activate_main=False,
                    has_activate_battle=True,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=True,
                    has_barrier=False,
                    keywords=("Deflect", "Blocker"),
                    card_traits_json='["Universe 11"]',
                    card_character_json='["Kahseral"]',
                )
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="red",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=10000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='["Universe 11"]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            11: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "activate_switch_up_to_n_owner_battle_active",
                    "handler_params": {
                        "max_targets": 2,
                        "max_cost": 1,
                        "max_power": 10000,
                        "allowed_colors": "red",
                        "required_traits": "Universe 11",
                        "requires_leader": "if your leader card is a red ≪universe 11≫ card",
                    },
                    "once_per_turn": True,
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Red"
    state.players[1].leader_area.traits = ("Universe 11",)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=700300,
            card_id=11,
            owner_id=1,
            card_number="BT14-026",
            card_type="BATTLE",
            color="Red",
            energy_cost=2,
            power=15000,
            resting=False,
            has_activate_battle=True,
            skill_text_raw=(
                "[Deflect][Blocker]\n"
                "[Permanent] If this card would be removed from your Battle Area by an opponent's skill, you may add 1 card from your life to your hand instead.\n"
                "[Activate: Battle][Once per turn] If your Leader Card is a red ≪Universe 11≫ card: "
                "Choose up to 2 of your red ≪Universe 11≫ cards with energy costs of 1 and 10000 power or less in your Battle Area and switch them to Active Mode."
            ),
            traits=("Universe 11",),
        ),
        CardInstance(instance_id=700301, card_id=701, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1, power=10000, resting=True, traits=("Universe 11",)),
        CardInstance(instance_id=700302, card_id=702, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1, power=9000, resting=True, traits=("Universe 11",)),
        CardInstance(instance_id=700303, card_id=703, owner_id=1, card_type="BATTLE", color="Red", energy_cost=2, power=9000, resting=True, traits=("Universe 11",)),
    ]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=700300,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.OFFENSE

    activate = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert state.players[1].battle_area[1].resting is False
    assert state.players[1].battle_area[2].resting is False
    assert state.players[1].battle_area[3].resting is True
    assert any(cp.name == "effect_activate_switch_up_to_n_owner_battle_active" for cp in state.checkpoints)

def test_phase4_activate_main_can_send_hand_to_warp_and_add_matching_zamasu_from_warp() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            if card_id == 9729:
                return SimpleNamespace(
                    id=9729,
                    card_number="BT29-094",
                    card_name="Zamasu, Scheme",
                    card_type="UNISON",
                    card_color="black",
                    card_energy_cost="X",
                    energy_cost_int=None,
                    combo_cost_int=None,
                    combo_power_int=None,
                    power_int=15000,
                    card_skill_unstyled="[UNISON +1][Activate: Main] placeholder",
                    has_activate_main=True,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Zamasu"]',
                )
            if card_id == 972907:
                return SimpleNamespace(
                    id=972907,
                    card_number="BT29-092",
                    card_name="Fused Zamasu, Fearsome God",
                    card_type="BATTLE",
                    card_color="black",
                    card_energy_cost="7",
                    energy_cost_int=7,
                    combo_cost_int=1,
                    combo_power_int=10000,
                    power_int=30000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Zamasu"]',
                )
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="black",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9729: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_add_up_to_n_from_owner_warp_to_hand",
                    "handler_params": {
                        "max_add": 1,
                        "allowed_colors": "black",
                        "required_characters": "Zamasu",
                        "max_cost": 7,
                        "required_source_zone": "unison",
                    },
                }
            ]
        },
        skill_cost_rules={
            9729: {
                "activate_main_unison": [
                    {
                        "kind": "send_owner_hand_to_warp",
                        "amount": 1,
                    }
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=700101,
        card_id=9729,
        owner_id=1,
        card_number="BT29-094",
        card_type="UNISON",
        color="black",
        has_activate_main=True,
        markers=1,
        characters=("Zamasu",),
    )
    state.players[1].unison_area = [source]
    state.players[1].hand = [
        CardInstance(instance_id=700102, card_id=211, owner_id=1, card_type="BATTLE", color="black")
    ]
    state.players[1].warp = [
        CardInstance(instance_id=700103, card_id=972907, owner_id=1, card_type="BATTLE", color="black")
    ]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)

    activate = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, activate)
    assert len(state.players[1].hand) == 0
    assert {card.instance_id for card in state.players[1].warp} == {700102, 700103}

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].hand) == 1
    assert state.players[1].hand[0].instance_id == 700103
    assert {card.instance_id for card in state.players[1].warp} == {700102}


def test_phase4_secret_auto_can_place_matching_deck_card_into_drop_after_hand_card_hits_drop() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            if card_id == 9732:
                return SimpleNamespace(
                    id=9732,
                    card_number="BT29-097",
                    card_name="SS2 Trunks, Pursuit",
                    card_type="BATTLE",
                    card_color="black",
                    card_energy_cost="1",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=15000,
                    card_skill_unstyled="",
                    has_activate_main=True,
                    has_auto=True,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=True,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Trunks"]',
                )
            if card_id == 97321:
                return SimpleNamespace(
                    id=97321,
                    card_number="BT29-098",
                    card_name="Black Target",
                    card_type="BATTLE",
                    card_color="black",
                    card_energy_cost="2",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=15000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='[]',
                )
            if card_id == 97322:
                return SimpleNamespace(
                    id=97322,
                    card_number="BT29-099",
                    card_name="Red Miss",
                    card_type="BATTLE",
                    card_color="red",
                    card_energy_cost="2",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=15000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='[]',
                )
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="black",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9732: [
                {
                    "trigger": "self_in_hand_sent_to_drop_or_warp",
                    "handler_id": "auto_place_up_to_n_from_owner_deck_to_destination_zone",
                    "handler_params": {
                        "max_targets": 1,
                        "max_power": 15000,
                        "required_card_type": "BATTLE",
                        "mirror_destination_zone": True,
                        "allowed_colors": "black,white",
                        "limit_per_turn": 1,
                        "limit_scope": "card_number",
                    },
                    "limit_per_turn": 1,
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[97322, 97321] + _deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].deck = [97322, 97321] + _deck(1100)
    source = CardInstance(
        instance_id=700105,
        card_id=9732,
        owner_id=1,
        card_number="BT29-097",
        card_type="BATTLE",
        color="Black",
        power=15000,
        has_auto=True,
    )
    state.players[1].hand = [source]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=source)

    moved = state.players[1].hand.pop(0)
    state.players[1].drop.append(moved)
    engine._emit_card_placed_into_drop(state, owner_player_id=1, card=moved, source_zone="hand")

    legal = engine.get_legal_actions(state, 1)
    assert [row.action_type for row in legal] == [ActionType.DECLARE_SECRET_AUTO, ActionType.IGNORE_SECRET_AUTO]
    state = engine.apply_action(state, legal[0])

    assert any(card.card_id == 97321 for card in state.players[1].drop)
    assert not any(card.card_id == 97322 for card in state.players[1].drop)
    assert any(cp.name == "effect_auto_place_up_to_n_from_owner_deck_to_destination_zone" for cp in state.checkpoints)


def test_phase4_secret_auto_can_place_matching_deck_card_into_warp_after_hand_card_hits_warp() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            if card_id == 9732:
                return SimpleNamespace(
                    id=9732,
                    card_number="BT29-097",
                    card_name="SS2 Trunks, Pursuit",
                    card_type="BATTLE",
                    card_color="black",
                    card_energy_cost="1",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=15000,
                    card_skill_unstyled="",
                    has_activate_main=True,
                    has_auto=True,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=True,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Trunks"]',
                )
            if card_id == 97323:
                return SimpleNamespace(
                    id=97323,
                    card_number="BT29-100",
                    card_name="White Target",
                    card_type="BATTLE",
                    card_color="white",
                    card_energy_cost="2",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=10000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='[]',
                )
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="red",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=20000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9732: [
                {
                    "trigger": "self_in_hand_sent_to_drop_or_warp",
                    "handler_id": "auto_place_up_to_n_from_owner_deck_to_destination_zone",
                    "handler_params": {
                        "max_targets": 1,
                        "max_power": 15000,
                        "required_card_type": "BATTLE",
                        "mirror_destination_zone": True,
                        "allowed_colors": "black,white",
                        "limit_per_turn": 1,
                        "limit_scope": "card_number",
                    },
                    "limit_per_turn": 1,
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[97323] + _deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].deck = [97323] + _deck(1200)
    source = CardInstance(
        instance_id=700106,
        card_id=9732,
        owner_id=1,
        card_number="BT29-097",
        card_type="BATTLE",
        color="Black",
        power=15000,
        has_auto=True,
    )
    state.players[1].hand = [source]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=source)

    moved = state.players[1].hand.pop(0)
    engine._append_to_owner_warp(state, owner_player_id=1, card=moved, source_zone="hand")

    legal = engine.get_legal_actions(state, 1)
    assert [row.action_type for row in legal] == [ActionType.DECLARE_SECRET_AUTO, ActionType.IGNORE_SECRET_AUTO]
    state = engine.apply_action(state, legal[0])

    assert any(card.card_id == 97323 for card in state.players[1].warp)
    assert any(cp.name == "effect_auto_place_up_to_n_from_owner_deck_to_destination_zone" for cp in state.checkpoints)


def test_phase4_secret_auto_can_play_self_from_drop_after_hand_card_hits_drop_by_opponent_skill() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            if card_id == 10005:
                return SimpleNamespace(
                    id=10005,
                    card_number="EX10-05",
                    card_name="Dr. Uiro, Cybernetic Rebirth",
                    card_type="BATTLE",
                    card_color="yellow",
                    card_energy_cost="3",
                    energy_cost_int=3,
                    combo_cost_int=1,
                    combo_power_int=5000,
                    power_int=19000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_auto=True,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Dr. Uiro"]',
                )
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="yellow",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            10005: [
                {
                    "trigger": "self_in_hand_sent_to_drop_or_warp",
                    "handler_id": "auto_play_self_from_drop_on_hand_drop",
                    "handler_params": {
                        "required_destination_zone": "drop",
                        "required_drop_causes": "opponent_skill,revive",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    source = CardInstance(
        instance_id=700107,
        card_id=10005,
        owner_id=1,
        card_number="EX10-05",
        card_type="BATTLE",
        color="Yellow",
        power=19000,
        has_auto=True,
    )
    state.players[1].hand = [source]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=source)

    moved = state.players[1].hand.pop(0)
    state.players[1].drop.append(moved)
    engine._emit_card_placed_into_drop(
        state,
        owner_player_id=1,
        card=moved,
        source_zone="hand",
        drop_cause="opponent_skill",
    )

    legal = engine.get_legal_actions(state, 1)
    assert [row.action_type for row in legal] == [ActionType.DECLARE_SECRET_AUTO, ActionType.IGNORE_SECRET_AUTO]
    state = engine.apply_action(state, legal[0])

    assert any(card.instance_id == 700107 for card in state.players[1].battle_area)
    assert not any(card.instance_id == 700107 for card in state.players[1].drop)
    assert any(cp.name == "effect_auto_play_self_from_drop_on_hand_drop" for cp in state.checkpoints)


def test_phase4_unison_activate_main_can_optionally_send_hand_to_warp_and_draw() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "Black", 0, "LEADER", "[]", "[]", False, False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False),
                6688: ("Mira, Dimensional Superpower", "Black", 0, "UNISON", "[]", "[]", True, True),
                910100: ("Warp Fodder", "Black", 1, "BATTLE", "[]", "[]", False, False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_activate_battle = data.get(
                card_id,
                ("Card", "Black", 0, "BATTLE", "[]", "[]", False, False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=has_activate_battle,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            6688: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_optional_send_owner_hand_to_warp_draw_n",
                    "handler_params": {"hand_to_warp": 1, "amount": 1, "marker_delta": 1},
                }
            ]
        },
        skill_cost_rules={
            6688: {
                "activate_main_unison": [
                    {
                        "kind": "add_markers",
                        "amount": 1,
                    }
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=710001,
        card_id=6688,
        owner_id=1,
        card_number="EX15-05",
        card_type="UNISON",
        color="Black",
        has_activate_main=True,
        markers=3,
    )
    state.players[1].unison_area = [source]
    state.players[1].hand = [
        CardInstance(instance_id=710002, card_id=910100, owner_id=1, card_type="BATTLE", color="Black")
    ]
    deck_before = len(state.players[1].deck)
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)

    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, action)
    assert state.players[1].unison_area[0].markers == 4
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].deck) == deck_before - 1
    assert {card.instance_id for card in state.players[1].warp} == {710002}
    assert any(cp.name == "effect_activate_optional_send_owner_hand_to_warp_draw_n" for cp in state.checkpoints)


def test_phase4_unison_activate_main_can_make_opponent_discard_from_hand() -> None:
    engine = RulesEngine(
        effect_rules={
            7909: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_opponent_discards_n_from_hand",
                    "handler_params": {"amount": 1},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=710011,
        card_id=7909,
        owner_id=1,
        card_number="BT25-141",
        card_type="UNISON",
        color="Yellow",
        has_activate_main=True,
        markers=1,
    )
    discarded = CardInstance(instance_id=710012, card_id=3001, owner_id=2, card_type="BATTLE", color="Red")
    kept = CardInstance(instance_id=710013, card_id=3002, owner_id=2, card_type="BATTLE", color="Blue")
    state.players[1].unison_area = [source]
    state.players[2].hand = [discarded, kept]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)

    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, action)
    assert state.counter_window is not None
    assert state.counter_window.pending_action.action_type == "activate_main"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert len(state.players[2].hand) == 1
    assert state.players[2].hand[0].instance_id == 710013
    assert any(card.instance_id == 710012 for card in state.players[2].drop)
    assert any(cp.name == "effect_activate_opponent_discards_n_from_hand" for cp in state.checkpoints)


def test_phase4_oolong_minus_seven_replaces_opponent_non_leader_skill_draw_next_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            7909: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_schedule_opponent_non_leader_skill_draw_replacement_next_turn",
                    "handler_params": {"restrict_activate_self_copies_next_turn": True},
                }
            ],
            999025: [
                {
                    "trigger": "owner_leader_attacks",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ],
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    oolong = CardInstance(
        instance_id=710021,
        card_id=7909,
        owner_id=1,
        card_number="BT25-141",
        card_type="UNISON",
        color="Yellow",
        has_activate_main=True,
        markers=8,
        skill_text_raw=(
            "[-7][Activate: Main] During your opponent's next turn, if your opponent would draw a card by the skill "
            "of a non-Leader Card, you place up to 1 Battle Card from your opponent's Drop at the top of its owner's deck instead. "
            "You can't activate skills on copies of this card during your next turn."
        ),
    )
    opponent_auto = CardInstance(
        instance_id=710022,
        card_id=999025,
        owner_id=2,
        card_type="BATTLE",
        color="Blue",
        has_auto=True,
        skill_text_raw="[Auto] When your Leader Card attacks, draw 1 card.",
    )
    replaced_drop = CardInstance(
        instance_id=710023,
        card_id=3999,
        owner_id=2,
        card_type="BATTLE",
        color="Red",
    )
    state.players[1].unison_area = [oolong]
    state.players[2].battle_area = [opponent_auto]
    state.players[2].drop = [replaced_drop]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=oolong)
    engine._register_card_effects(state, player_id=2, source_zone="battle", card=opponent_auto)

    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(
        cp.name == "effect_activate_schedule_opponent_non_leader_skill_draw_replacement_next_turn"
        for cp in state.checkpoints
    )
    assert len(state.active_skill_draw_replacements) == 1
    assert any(
        int(row.restricted_card_id) == 7909
        and str(row.trigger) == "self_activate_main"
        and str(row.handler_id) == "activate_schedule_opponent_non_leader_skill_draw_replacement_next_turn"
        for row in state.scheduled_activate_skill_restrictions
    )

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)

    hand_before = len(state.players[2].hand)
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=2,
        payload={
            "attacker_instance_id": state.players[2].leader_area.instance_id,
            "attacker_zone": "leader",
            "target_player_id": 1,
            "target_zone": "leader",
        },
    )
    engine._resolve_pending_effects(state)

    assert len(state.players[2].hand) == hand_before
    assert state.players[2].deck[0] == 3999
    assert not any(card.instance_id == 710023 for card in state.players[2].drop)
    assert any(cp.name == "skill_draw_replaced_from_drop_to_deck" for cp in state.checkpoints)


def test_phase4_bt25_137_choose_one_auto_prefers_discard_branch_when_it_has_higher_or_equal_value() -> None:
    engine = RulesEngine(
        effect_rules={
            7844: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_choose_discard_or_ko_rest_battles_and_gain_keyword_on_play",
                    "handler_params": {
                        "discard_amount": 2,
                        "discard_grant_keyword": "Double Strike",
                        "ko_max_targets": 2,
                        "rest_mode_only": True,
                        "ignores_barrier": True,
                        "ko_grant_keyword": "Dual Attack",
                        "requires_leader": "green,yellow",
                        "min_opponent_energy": 3,
                    },
                    "limit_per_turn": 1,
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].leader_area.color = "Green"
    state.players[2].energy = [
        CardInstance(instance_id=710031, card_id=5001, owner_id=2, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=710032, card_id=5002, owner_id=2, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=710033, card_id=5003, owner_id=2, card_type="BATTLE", color="Blue"),
    ]
    source = CardInstance(
        instance_id=710034,
        card_id=7844,
        owner_id=1,
        card_number="BT25-137",
        card_type="BATTLE",
        color="Green/Yellow",
        has_auto=True,
        skill_text_raw=(
            "[Auto][Limit 1] If your Leader is green or yellow and your opponent has 3 or more energy: "
            "When this card is played, choose one -- Your opponent discards 2 cards from their hand, and this card gains "
            "[Double Strike] for the turn. Choose up to 2 of your opponent's Rest Mode Battle Cards, ignoring [Barrier], "
            "and KO them, then this card gains [Dual Attack] for the turn."
        ),
    )
    discarded_a = CardInstance(instance_id=710035, card_id=5004, owner_id=2, card_type="BATTLE", color="Red")
    discarded_b = CardInstance(instance_id=710036, card_id=5005, owner_id=2, card_type="BATTLE", color="Yellow")
    rest_target = CardInstance(instance_id=710037, card_id=5006, owner_id=2, card_type="BATTLE", color="Blue", resting=True, power=15000)
    state.players[1].battle_area = [source]
    state.players[2].hand = [discarded_a, discarded_b]
    state.players[2].battle_area = [rest_target]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 710034, "source_card_id": 7844, "source_zone": "battle", "played_from": "hand"},
    )
    engine._resolve_pending_effects(state)

    source_after = next(card for card in state.players[1].battle_area if card.instance_id == 710034)
    assert len(state.players[2].hand) == 0
    assert any(card.instance_id == 710035 for card in state.players[2].drop)
    assert any(card.instance_id == 710036 for card in state.players[2].drop)
    assert any(card.instance_id == 710037 for card in state.players[2].battle_area)
    assert "Double Strike" in source_after.temporary_keywords
    assert "Dual Attack" not in source_after.temporary_keywords
    assert any(cp.name == "effect_auto_choose_discard_or_ko_rest_battles_and_gain_keyword_on_play" for cp in state.checkpoints)


def test_phase4_bt25_137_choose_one_auto_falls_back_to_ko_branch_when_it_has_higher_value() -> None:
    engine = RulesEngine(
        effect_rules={
            7844: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_choose_discard_or_ko_rest_battles_and_gain_keyword_on_play",
                    "handler_params": {
                        "discard_amount": 2,
                        "discard_grant_keyword": "Double Strike",
                        "ko_max_targets": 2,
                        "rest_mode_only": True,
                        "ignores_barrier": True,
                        "ko_grant_keyword": "Dual Attack",
                        "requires_leader": "green,yellow",
                        "min_opponent_energy": 3,
                    },
                    "limit_per_turn": 1,
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].leader_area.color = "Yellow"
    state.players[2].energy = [
        CardInstance(instance_id=710041, card_id=5101, owner_id=2, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=710042, card_id=5102, owner_id=2, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=710043, card_id=5103, owner_id=2, card_type="BATTLE", color="Blue"),
    ]
    source = CardInstance(
        instance_id=710044,
        card_id=7844,
        owner_id=1,
        card_number="BT25-137",
        card_type="BATTLE",
        color="Green/Yellow",
        has_auto=True,
    )
    rest_a = CardInstance(instance_id=710045, card_id=5104, owner_id=2, card_type="BATTLE", color="Red", resting=True, power=10000)
    rest_b = CardInstance(instance_id=710046, card_id=5105, owner_id=2, card_type="BATTLE", color="Blue", resting=True, power=12000, keywords=("Barrier",))
    active_other = CardInstance(instance_id=710047, card_id=5106, owner_id=2, card_type="BATTLE", color="Green", resting=False, power=15000)
    state.players[1].battle_area = [source]
    state.players[2].hand = []
    state.players[2].battle_area = [rest_a, rest_b, active_other]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 710044, "source_card_id": 7844, "source_zone": "battle", "played_from": "hand"},
    )
    engine._resolve_pending_effects(state)

    source_after = next(card for card in state.players[1].battle_area if card.instance_id == 710044)
    remaining_ids = {card.instance_id for card in state.players[2].battle_area}
    dropped_card_ids = {card.card_id for card in state.players[2].drop}
    assert 5104 in dropped_card_ids
    assert 5105 in dropped_card_ids
    assert 710047 in remaining_ids
    assert "Dual Attack" in source_after.temporary_keywords
    assert "Double Strike" not in source_after.temporary_keywords
    assert any(cp.name == "effect_auto_choose_discard_or_ko_rest_battles_and_gain_keyword_on_play" for cp in state.checkpoints)


def test_phase4_unison_activate_battle_can_gain_power_per_owner_warp_count() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "Black", 0, "LEADER", "[]", "[]", False, False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False),
                6688: ("Mira, Dimensional Superpower", "Black", 0, "UNISON", "[]", "[]", True, True),
                910101: ("Warp A", "Black", 1, "BATTLE", "[]", "[]", False, False),
                910102: ("Warp B", "Black", 1, "BATTLE", "[]", "[]", False, False),
                910103: ("Warp C", "Black", 1, "BATTLE", "[]", "[]", False, False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_activate_battle = data.get(
                card_id,
                ("Card", "Black", 0, "BATTLE", "[]", "[]", False, False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=has_activate_battle,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            6688: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "activate_gain_power_and_keyword_for_battle",
                    "handler_params": {"power_delta": "expr:owner_warp_count*5000"},
                }
            ]
        },
        skill_cost_rules={
            6688: {
                "activate_battle_unison": [
                    {
                        "kind": "remove_markers",
                        "amount": 2,
                    }
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    source = CardInstance(
        instance_id=710101,
        card_id=6688,
        owner_id=1,
        card_number="EX15-05",
        card_type="UNISON",
        color="Black",
        has_activate_battle=True,
        markers=4,
    )
    state.players[1].unison_area = [source]
    state.players[1].warp = [
        CardInstance(instance_id=710102, card_id=910101, owner_id=1, card_type="BATTLE", color="Black"),
        CardInstance(instance_id=710103, card_id=910102, owner_id=1, card_type="BATTLE", color="Black"),
        CardInstance(instance_id=710104, card_id=910103, owner_id=1, card_type="BATTLE", color="Black"),
    ]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)

    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="leader",
        attacker_instance_id=state.players[1].leader_area.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.OFFENSE

    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, action)
    assert state.players[1].unison_area[0].markers == 2
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].unison_area[0].battle_temporary_power_delta == 15000
    assert any(cp.name == "effect_activate_gain_power_and_keyword_for_battle" for cp in state.checkpoints)


def test_phase4_attack_declared_triggers_self_attack_effect() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880011, card_id=11, owner_id=1, card_type="BATTLE", energy_cost=0, has_auto=True)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0
    )
    state = engine.apply_action(state, attack)
    attack_effect_ids = {r.effect_id for r in state.effect_registry if r.source_instance_id == 880011 and r.trigger == "self_attacks"}
    assert attack_effect_ids
    # Auto-trigger should be pending until counter timing closes.
    assert any(pe.effect_id in attack_effect_ids for pe in state.pending_effects)
    assert all(not (res.effect_id in attack_effect_ids and res.resolved) for res in state.effect_resolutions)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(res.effect_id in attack_effect_ids and res.resolved for res in state.effect_resolutions)


def test_phase4_custom_effect_handler_is_used() -> None:
    def custom_handler(state, event, reg):
        state.log.append(f"custom:{reg.effect_id}:{event.name}")

    engine = RulesEngine(effect_handlers={"noop_auto": custom_handler})
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880021, card_id=21, owner_id=1, card_type="BATTLE", energy_cost=0, has_auto=True)
    ]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(entry.startswith("custom:") for entry in state.log)


def test_phase4_effect_catalog_registers_and_dispatches_handler() -> None:
    def catalog_handler(state, event, reg):
        state.log.append(f"catalog:{reg.effect_id}:{event.name}:{reg.source_card_id}")

    engine = RulesEngine(
        effect_rules={424242: [{"trigger": "self_played", "handler_id": "catalog_draw", "once_per_turn": True}]},
        effect_handlers={"catalog_draw": catalog_handler},
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880025, card_id=424242, owner_id=1, card_type="BATTLE", energy_cost=0, has_auto=False)
    ]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    reg = next(r for r in state.effect_registry if r.source_card_id == 424242 and r.handler_id == "catalog_draw")
    assert reg.once_per_turn is True
    assert any(entry.startswith("catalog:") for entry in state.log)


def test_phase4_catalog_auto_draw_n_uses_amount_param() -> None:
    engine = RulesEngine(
        effect_rules={
            424243: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 2},
                    "once_per_turn": False,
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    deck_before = len(state.players[1].deck)
    state.players[1].hand = [CardInstance(instance_id=880026, card_id=424243, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].deck) == deck_before - 2
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_catalog_auto_ko_on_play_uses_policy_and_max_cost() -> None:
    engine = RulesEngine(
        effect_rules={
            424244: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_opponent_battle_on_play",
                    "handler_params": {"max_cost": 5, "target_policy": "lowest_power"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880027, card_id=27, owner_id=2, card_type="BATTLE", energy_cost=4, power=15000),
        CardInstance(instance_id=880028, card_id=28, owner_id=2, card_type="BATTLE", energy_cost=6, power=5000),
        CardInstance(instance_id=880029, card_id=29, owner_id=2, card_type="BATTLE", energy_cost=3, power=10000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880030, card_id=424244, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    # Eligible by max_cost are 880027 and 880029; lowest power among them is 880029.
    assert all(c.instance_id != 880029 for c in state.players[2].battle_area)
    assert any(c.instance_id == 880029 for c in state.players[2].drop)
    assert any(cp.name == "effect_auto_ko_on_play" for cp in state.checkpoints)


def test_phase4_catalog_auto_ko_on_play_uses_target_chooser_override() -> None:
    def choose_second(_state, _reg, _candidates, _policy):
        return 1

    engine = RulesEngine(
        effect_rules={
            424245: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_opponent_battle_on_play",
                    "handler_params": {"max_cost": 5, "target_policy": "lowest_power"},
                }
            ]
        },
        effect_target_chooser=choose_second,
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    # Both are eligible (cost<=5); chooser should select second candidate order-wise.
    state.players[2].battle_area = [
        CardInstance(instance_id=880101, card_id=101, owner_id=2, card_type="BATTLE", energy_cost=3, power=5000),
        CardInstance(instance_id=880102, card_id=102, owner_id=2, card_type="BATTLE", energy_cost=4, power=1000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880103, card_id=424245, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert all(c.instance_id != 880102 for c in state.players[2].battle_area)
    assert any(c.instance_id == 880102 for c in state.players[2].drop)


def test_phase4_catalog_auto_ko_on_play_target_chooser_index_is_clamped() -> None:
    def choose_out_of_range(_state, _reg, _candidates, _policy):
        return 999

    engine = RulesEngine(
        effect_rules={
            424246: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_opponent_battle_on_play",
                    "handler_params": {"max_cost": 5},
                }
            ]
        },
        effect_target_chooser=choose_out_of_range,
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880111, card_id=111, owner_id=2, card_type="BATTLE", energy_cost=1, power=5000),
        CardInstance(instance_id=880112, card_id=112, owner_id=2, card_type="BATTLE", energy_cost=2, power=6000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880113, card_id=424246, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    # Clamped to last index.
    assert all(c.instance_id != 880112 for c in state.players[2].battle_area)
    assert any(c.instance_id == 880112 for c in state.players[2].drop)


def test_phase4_catalog_auto_ko_up_to_n_on_play_uses_multi_target_chooser() -> None:
    def choose_targets(_state, _reg, _candidates, _count, _policy):
        return [2, 0]

    engine = RulesEngine(
        effect_rules={
            424247: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_up_to_n_opponent_battle_on_play",
                    "handler_params": {"max_targets": 2, "max_cost": 5, "target_policy": "first"},
                }
            ]
        },
        effect_multi_target_chooser=choose_targets,
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880121, card_id=121, owner_id=2, card_type="BATTLE", energy_cost=1, power=10000),
        CardInstance(instance_id=880122, card_id=122, owner_id=2, card_type="BATTLE", energy_cost=2, power=9000),
        CardInstance(instance_id=880123, card_id=123, owner_id=2, card_type="BATTLE", energy_cost=3, power=8000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880124, card_id=424247, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    remaining = {c.instance_id for c in state.players[2].battle_area}
    assert 880121 not in remaining
    assert 880123 not in remaining
    assert any(cp.name == "effect_auto_ko_up_to_n_on_play" for cp in state.checkpoints)


def test_phase4_catalog_auto_ko_up_to_n_on_play_default_policy_lowest_power() -> None:
    engine = RulesEngine(
        effect_rules={
            424248: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_up_to_n_opponent_battle_on_play",
                    "handler_params": {"max_targets": 2, "max_cost": 5, "target_policy": "lowest_power"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880131, card_id=131, owner_id=2, card_type="BATTLE", energy_cost=1, power=7000),
        CardInstance(instance_id=880132, card_id=132, owner_id=2, card_type="BATTLE", energy_cost=2, power=3000),
        CardInstance(instance_id=880133, card_id=133, owner_id=2, card_type="BATTLE", energy_cost=3, power=5000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880134, card_id=424248, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    remaining = {c.instance_id for c in state.players[2].battle_area}
    # Lowest power two are 3000 and 5000.
    assert 880132 not in remaining
    assert 880133 not in remaining


def test_phase4_catalog_auto_power_reduce_up_to_n_on_play_uses_shared_selection() -> None:
    engine = RulesEngine(
        effect_rules={
            424249: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_power_reduce_up_to_n_on_play",
                    "handler_params": {
                        "max_targets": 1,
                        "max_cost": 5,
                        "target_policy": "lowest_power",
                        "power_delta": -6000,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880141, card_id=141, owner_id=2, card_type="BATTLE", energy_cost=3, power=5000),
        CardInstance(instance_id=880142, card_id=142, owner_id=2, card_type="BATTLE", energy_cost=2, power=9000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880143, card_id=424249, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    # Lowest-power target is reduced to <=0 and confirmative rule processing sends it to drop.
    assert all(c.instance_id != 880141 for c in state.players[2].battle_area)
    assert any(c.instance_id == 880141 for c in state.players[2].drop)
    assert any(cp.name == "effect_auto_power_reduce_up_to_n_on_play" for cp in state.checkpoints)


def test_phase4_catalog_auto_power_reduce_up_to_n_on_play_respects_multi_chooser() -> None:
    def choose_second(_state, _reg, _candidates, _count, _policy):
        return [1]

    engine = RulesEngine(
        effect_rules={
            424250: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_power_reduce_up_to_n_on_play",
                    "handler_params": {
                        "max_targets": 1,
                        "max_cost": 5,
                        "target_policy": "first",
                        "power_delta": -3000,
                    },
                }
            ]
        },
        effect_multi_target_chooser=choose_second,
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880151, card_id=151, owner_id=2, card_type="BATTLE", energy_cost=2, power=10000),
        CardInstance(instance_id=880152, card_id=152, owner_id=2, card_type="BATTLE", energy_cost=2, power=10000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880153, card_id=424250, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    p2_cards = {c.instance_id: c.power for c in state.players[2].battle_area}
    assert p2_cards[880151] == 10000
    assert p2_cards[880152] == 7000


def test_phase4_catalog_requires_leader_condition_blocks_when_unmet() -> None:
    engine = RulesEngine(
        effect_rules={
            424251: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_opponent_battle_on_play",
                    "handler_params": {"max_cost": 5, "requires_leader": "if your leader is blue card"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    # Owner leader is red; requirement says blue -> should not resolve.
    state.players[1].leader_area.color = "Red"
    state.players[2].battle_area = [
        CardInstance(instance_id=880161, card_id=161, owner_id=2, card_type="BATTLE", energy_cost=2, power=10000)
    ]
    state.players[1].hand = [CardInstance(instance_id=880162, card_id=424251, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(c.instance_id == 880161 for c in state.players[2].battle_area)
    assert all(c.instance_id != 880161 for c in state.players[2].drop)


def test_phase4_catalog_rest_mode_only_filters_targets() -> None:
    engine = RulesEngine(
        effect_rules={
            424252: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_opponent_battle_on_play",
                    "handler_params": {"max_cost": 5, "rest_mode_only": True},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880171, card_id=171, owner_id=2, card_type="BATTLE", energy_cost=2, power=10000, resting=False),
        CardInstance(instance_id=880172, card_id=172, owner_id=2, card_type="BATTLE", energy_cost=2, power=10000, resting=True),
    ]
    state.players[1].hand = [CardInstance(instance_id=880173, card_id=424252, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    remaining = {c.instance_id for c in state.players[2].battle_area}
    assert 880172 not in remaining
    assert 880171 in remaining


def test_phase4_dynamic_expr_max_targets_ko_up_to_n_uses_opponent_battle_count() -> None:
    engine = RulesEngine(
        effect_rules={
            424253: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_up_to_n_opponent_battle_on_play",
                    "handler_params": {"max_targets": "expr:opponent_battle_count", "max_cost": -1, "target_policy": "first"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880181, card_id=181, owner_id=2, card_type="BATTLE", energy_cost=1, power=10000),
        CardInstance(instance_id=880182, card_id=182, owner_id=2, card_type="BATTLE", energy_cost=1, power=10000),
        CardInstance(instance_id=880183, card_id=183, owner_id=2, card_type="BATTLE", energy_cost=1, power=10000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880184, card_id=424253, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[2].battle_area) == 0
    assert len([c for c in state.players[2].drop if c.instance_id in {880181, 880182, 880183}]) == 3


def test_phase4_dynamic_expr_max_targets_power_reduce_uses_owner_energy_count() -> None:
    engine = RulesEngine(
        effect_rules={
            424254: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_power_reduce_up_to_n_on_play",
                    "handler_params": {
                        "max_targets": "expr:owner_energy_count",
                        "max_cost": -1,
                        "target_policy": "first",
                        "power_delta": -2000,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880191, card_id=191, owner_id=1, card_type="BATTLE", energy_cost=0),
        CardInstance(instance_id=880192, card_id=192, owner_id=1, card_type="BATTLE", energy_cost=0),
    ]
    state.players[2].battle_area = [
        CardInstance(instance_id=880193, card_id=193, owner_id=2, card_type="BATTLE", energy_cost=1, power=10000),
        CardInstance(instance_id=880194, card_id=194, owner_id=2, card_type="BATTLE", energy_cost=1, power=10000),
        CardInstance(instance_id=880195, card_id=195, owner_id=2, card_type="BATTLE", energy_cost=1, power=10000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880196, card_id=424254, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    powers = {c.instance_id: c.power for c in state.players[2].battle_area}
    assert powers[880193] == 8000
    assert powers[880194] == 8000
    assert powers[880195] == 10000


def test_phase4_permanent_does_not_enter_pending_activation_flow() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880031, card_id=31, owner_id=1, card_type="BATTLE", energy_cost=0, has_permanent=True)
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    regs = [r for r in state.effect_registry if r.source_instance_id == 880031]
    assert regs == []
    assert all(
        not (evt.payload.get("source_instance_id") == 880031 and evt.name == "state_check")
        for evt in state.effect_events
    )


def test_phase4_once_per_turn_pending_batch_resolves_only_once() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    source = state.players[1].leader_area
    state.effect_registry.append(
        EffectRegistration(
            effect_id=state.next_effect_id,
            owner_player_id=1,
            source_instance_id=source.instance_id,
            source_card_id=source.card_id,
            source_zone="leader",
            trigger="turn_start",
            handler_id="noop_auto",
            once_per_turn=True,
            triggers_this_turn=0,
        )
    )
    effect_id = state.next_effect_id
    state.next_effect_id += 1

    # Two same-turn trigger events -> only one should resolve.
    engine._emit_effect_event(state, name="turn_start", actor_player_id=1, payload={})
    engine._emit_effect_event(state, name="turn_start", actor_player_id=1, payload={})
    engine._resolve_pending_effects(state)

    rows = [r for r in state.effect_resolutions if r.effect_id == effect_id]
    assert any(r.resolved for r in rows)
    assert any((not r.resolved) and r.reason == "once_per_turn_used" for r in rows)
    assert any(cp.name == "effect_once_per_turn_blocked" for cp in state.checkpoints)
    assert any("Public effect blocked by once-per-turn" in row and f"effect_id={effect_id}" in row for row in state.log)


def test_phase4_limit_one_pending_batch_resolves_only_once_across_same_card_number() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=880038, card_id=38, owner_id=1, card_number="TEST-038", card_type="BATTLE", has_auto=True),
            CardInstance(instance_id=880039, card_id=39, owner_id=1, card_number="TEST-038", card_type="BATTLE", has_auto=True),
        ]
    )
    state.effect_registry.extend(
        [
            EffectRegistration(
                effect_id=state.next_effect_id,
                owner_player_id=1,
                source_instance_id=880038,
                source_card_id=38,
                source_zone="battle",
                trigger="turn_start",
                handler_id="noop_auto",
                source_card_number="TEST-038",
                limit_per_turn=1,
            ),
            EffectRegistration(
                effect_id=state.next_effect_id + 1,
                owner_player_id=1,
                source_instance_id=880039,
                source_card_id=39,
                source_zone="battle",
                trigger="turn_start",
                handler_id="noop_auto",
                source_card_number="TEST-038",
                limit_per_turn=1,
            ),
        ]
    )
    effect_ids = {state.next_effect_id, state.next_effect_id + 1}
    state.next_effect_id += 2

    engine._emit_effect_event(state, name="turn_start", actor_player_id=1, payload={})
    engine._resolve_pending_effects(state)

    rows = [r for r in state.effect_resolutions if r.effect_id in effect_ids]
    assert sum(1 for r in rows if r.resolved and r.reason == "ok") == 1
    assert sum(1 for r in rows if (not r.resolved) and r.reason == "limit_per_turn_used") == 1
    assert any(cp.name == "effect_limit_per_turn_blocked" for cp in state.checkpoints)
    assert any("Public effect blocked by limit" in row and "limit_scope=card_number" in row for row in state.log)


def test_phase4_limit_scope_card_id_allows_distinct_card_ids_with_same_card_number() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=8800381, card_id=381, owner_id=1, card_number="TEST-381", card_type="BATTLE", has_auto=True),
            CardInstance(instance_id=8800382, card_id=382, owner_id=1, card_number="TEST-381", card_type="BATTLE", has_auto=True),
        ]
    )
    state.effect_registry.extend(
        [
            EffectRegistration(
                effect_id=state.next_effect_id,
                owner_player_id=1,
                source_instance_id=8800381,
                source_card_id=381,
                source_zone="battle",
                trigger="turn_start",
                handler_id="noop_auto",
                source_card_number="TEST-381",
                limit_per_turn=1,
                limit_scope="card_id",
            ),
            EffectRegistration(
                effect_id=state.next_effect_id + 1,
                owner_player_id=1,
                source_instance_id=8800382,
                source_card_id=382,
                source_zone="battle",
                trigger="turn_start",
                handler_id="noop_auto",
                source_card_number="TEST-381",
                limit_per_turn=1,
                limit_scope="card_id",
            ),
        ]
    )
    effect_ids = {state.next_effect_id, state.next_effect_id + 1}
    state.next_effect_id += 2

    engine._emit_effect_event(state, name="turn_start", actor_player_id=1, payload={})
    engine._resolve_pending_effects(state)

    rows = [r for r in state.effect_resolutions if r.effect_id in effect_ids]
    assert sum(1 for r in rows if r.resolved and r.reason == "ok") == 2
    assert sum(1 for r in rows if (not r.resolved) and r.reason == "limit_per_turn_used") == 0


def test_phase4_limit_scope_source_instance_allows_distinct_instances_same_card_id() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=8800391, card_id=391, owner_id=1, card_number="TEST-391", card_type="BATTLE", has_auto=True),
            CardInstance(instance_id=8800392, card_id=391, owner_id=1, card_number="TEST-391", card_type="BATTLE", has_auto=True),
        ]
    )
    state.effect_registry.extend(
        [
            EffectRegistration(
                effect_id=state.next_effect_id,
                owner_player_id=1,
                source_instance_id=8800391,
                source_card_id=391,
                source_zone="battle",
                trigger="turn_start",
                handler_id="noop_auto",
                source_card_number="TEST-391",
                limit_per_turn=1,
                limit_scope="source_instance",
            ),
            EffectRegistration(
                effect_id=state.next_effect_id + 1,
                owner_player_id=1,
                source_instance_id=8800392,
                source_card_id=391,
                source_zone="battle",
                trigger="turn_start",
                handler_id="noop_auto",
                source_card_number="TEST-391",
                limit_per_turn=1,
                limit_scope="source_instance",
            ),
        ]
    )
    effect_ids = {state.next_effect_id, state.next_effect_id + 1}
    state.next_effect_id += 2

    engine._emit_effect_event(state, name="turn_start", actor_player_id=1, payload={})
    engine._resolve_pending_effects(state)

    rows = [r for r in state.effect_resolutions if r.effect_id in effect_ids]
    assert sum(1 for r in rows if r.resolved and r.reason == "ok") == 2
    assert sum(1 for r in rows if (not r.resolved) and r.reason == "limit_per_turn_used") == 0


def test_phase4_auto_draw_on_play_resolves_after_counter_timing() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    p1 = state.players[1]
    p1.hand = [
        CardInstance(
            instance_id=880041,
            card_id=41,
            owner_id=1,
            card_type="BATTLE",
            energy_cost=0,
            has_auto=True,
            has_draw=True,
            auto_draw_on_play=True,
        )
    ]
    deck_before = len(p1.deck)
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    # Not resolved yet while counter timing is open.
    assert len(state.players[1].deck) == deck_before
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].hand) == 1
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_draw_on_play" for cp in state.checkpoints)


def test_phase4_nested_pending_auto_from_effect_resolves_in_same_checkpoint() -> None:
    engine = RulesEngine(
        effect_rules={
            990051: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_drop_on_play",
                    "handler_params": {"max_targets": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    source = CardInstance(instance_id=990051, card_id=990051, owner_id=1, card_type="BATTLE", has_auto=True)
    nested = CardInstance(
        instance_id=990052,
        card_id=990052,
        owner_id=1,
        card_type="BATTLE",
        has_auto=True,
        has_draw=True,
        auto_draw_on_play=True,
    )
    state.players[1].battle_area.append(source)
    state.players[1].drop.append(nested)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    deck_before = len(state.players[1].deck)
    hand_before = len(state.players[1].hand)

    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990051, "source_card_id": 990051, "source_zone": "battle", "played_from": "hand"},
    )
    engine._resolve_pending_effects(state)

    assert len(state.pending_effects) == 0
    assert any(card.instance_id == 990052 for card in state.players[1].battle_area)
    assert len(state.players[1].hand) == hand_before + 1
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_drop_on_play" for cp in state.checkpoints)
    assert any(cp.name == "effect_auto_draw_on_play" for cp in state.checkpoints)


def test_phase4_secret_area_registration_skips_auto_rules_but_keeps_activate_rules() -> None:
    engine = RulesEngine(
        effect_rules={
            990061: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
                {"trigger": "self_activate_main", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(
        instance_id=990061,
        card_id=990061,
        owner_id=1,
        card_type="BATTLE",
        has_auto=True,
        has_activate_main=True,
    )
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)

    regs = [r for r in state.effect_registry if r.source_instance_id == 990061]
    assert any(r.trigger == "self_activate_main" for r in regs)
    assert all(r.trigger != "self_played" for r in regs)
    deferred = [row for row in state.deferred_secret_autos if row.source_instance_id == 990061]
    assert len(deferred) == 1
    assert deferred[0].trigger == "self_played"
    assert deferred[0].handler_id == "auto_draw_n"
    assert any(cp.name == "secret_auto_registration_deferred" for cp in state.checkpoints)
    assert any("Deferred secret-area auto registration" in row for row in state.log)


def test_phase4_public_registration_preserves_secret_auto_provenance_for_same_source() -> None:
    engine = RulesEngine(
        effect_rules={
            990062: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(
        instance_id=990062,
        card_id=990062,
        owner_id=1,
        card_type="BATTLE",
        has_auto=False,
    )
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    assert any(row.source_instance_id == 990062 for row in state.deferred_secret_autos)

    engine._register_card_effects(state, player_id=1, source_zone="battle", card=card)
    deferred = [row for row in state.deferred_secret_autos if row.source_instance_id == 990062]
    assert len(deferred) == 1
    assert deferred[0].source_zone == "battle"
    assert deferred[0].origin_zone == "hand"
    assert all(not (r.source_instance_id == 990062 and r.trigger == "self_played") for r in state.effect_registry)


def test_phase4_preserved_secret_auto_provenance_suppresses_public_pending_duplicate() -> None:
    engine = RulesEngine(
        effect_rules={
            9900611: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=9900611, card_id=9900611, owner_id=1, card_type="BATTLE", has_auto=False)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=card)

    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 9900611, "source_card_id": 9900611, "source_zone": "battle", "played_from": "hand"},
    )

    assert not any(entry.effect_id > 0 and any(reg.effect_id == entry.effect_id and reg.source_instance_id == 9900611 for reg in state.effect_registry) for entry in state.pending_effects)
    opportunities = [row for row in state.secret_auto_opportunities if row.source_instance_id == 9900611]
    assert len(opportunities) == 1
    assert opportunities[0].origin_zone == "hand"


def test_phase4_stale_deferred_secret_auto_is_pruned_when_source_leaves_hand() -> None:
    engine = RulesEngine(
        effect_rules={
            990063: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990063, card_id=990063, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    assert any(row.source_instance_id == 990063 for row in state.deferred_secret_autos)

    state.players[1].hand.clear()
    engine._run_confirmative_rule_processing(state)

    assert all(row.source_instance_id != 990063 for row in state.deferred_secret_autos)
    assert any(cp.name == "secret_auto_registration_pruned" for cp in state.checkpoints)


def test_phase4_secret_auto_opportunity_is_created_when_matching_event_occurs() -> None:
    engine = RulesEngine(
        effect_rules={
            990064: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990064, card_id=990064, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)

    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990064, "source_card_id": 990064, "source_zone": "battle", "played_from": "hand"},
    )

    opportunities = [row for row in state.secret_auto_opportunities if row.source_instance_id == 990064]
    assert len(opportunities) == 1
    assert opportunities[0].trigger == "self_played"
    assert opportunities[0].handler_id == "auto_draw_n"
    assert opportunities[0].event_name == "card_played"
    assert any(cp.name == "secret_auto_opportunity_created" for cp in state.checkpoints)
    assert any("Secret-area auto opportunity created" in row for row in state.log)


def test_phase4_secret_auto_opportunity_is_not_created_for_unrelated_event() -> None:
    engine = RulesEngine(
        effect_rules={
            990065: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990065, card_id=990065, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)

    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": 123, "attacker_zone": "leader", "target_player_id": 2, "target_zone": "leader"},
    )

    assert all(row.source_instance_id != 990065 for row in state.secret_auto_opportunities)


def test_phase4_secret_auto_opportunity_exposes_declare_ignore_actions_and_declare_resolves() -> None:
    engine = RulesEngine(
        effect_rules={
            990066: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990066, card_id=990066, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990066, "source_card_id": 990066, "source_zone": "battle", "played_from": "hand"},
    )

    deck_before = len(state.players[1].deck)
    legal = engine.get_legal_actions(state, 1)
    assert [row.action_type for row in legal] == [ActionType.DECLARE_SECRET_AUTO, ActionType.IGNORE_SECRET_AUTO]
    assert engine.get_legal_actions(state, 2) == []

    state = engine.apply_action(state, legal[0])

    opportunity = next(row for row in state.secret_auto_opportunities if row.source_instance_id == 990066)
    assert opportunity.status == "declared"
    assert len(state.players[1].deck) == deck_before - 1
    assert any(row.effect_id == -opportunity.secret_auto_id and row.resolved for row in state.effect_resolutions)
    assert any(cp.name == "secret_auto_declared" for cp in state.checkpoints)
    assert any("Secret-area auto declared" in row for row in state.log)


def test_phase4_secret_auto_limit_one_declares_only_once_across_same_card_number() -> None:
    engine = RulesEngine(
        effect_rules={
            9900661: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "limit_per_turn": 1},
            ],
            9900662: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "limit_per_turn": 1},
            ],
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card_a = CardInstance(instance_id=9900661, card_id=9900661, owner_id=1, card_type="BATTLE", card_number="TEST-990066", has_auto=True)
    card_b = CardInstance(instance_id=9900662, card_id=9900662, owner_id=1, card_type="BATTLE", card_number="TEST-990066", has_auto=True)
    state.players[1].hand = [card_a, card_b]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card_a)
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card_b)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 9900661, "source_card_id": 9900661, "source_zone": "battle", "played_from": "hand"},
    )
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 9900662, "source_card_id": 9900662, "source_zone": "battle", "played_from": "hand"},
    )

    deck_before = len(state.players[1].deck)
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))

    opportunity_ids = {row.secret_auto_id for row in state.secret_auto_opportunities if row.source_instance_id in {9900661, 9900662}}
    rows = [r for r in state.effect_resolutions if r.effect_id in {-secret_auto_id for secret_auto_id in opportunity_ids}]
    assert sum(1 for r in rows if r.resolved and r.reason == "ok") == 1
    assert sum(1 for r in rows if (not r.resolved) and r.reason == "limit_per_turn_used") == 1
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "secret_auto_declared_limit_blocked" for cp in state.checkpoints)
    assert any(row.status == "blocked_limit_per_turn" for row in state.secret_auto_opportunities if row.source_instance_id in {9900661, 9900662})


def test_phase4_declared_secret_auto_counts_against_public_limit_key_same_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            9900663: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "limit_per_turn": 1},
            ],
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    secret_card = CardInstance(instance_id=9900663, card_id=9900663, owner_id=1, card_type="BATTLE", card_number="TEST-990067", has_auto=True)
    public_card = CardInstance(instance_id=9900664, card_id=9900664, owner_id=1, card_type="BATTLE", card_number="TEST-990067", has_auto=True)
    state.players[1].hand = [secret_card]
    state.players[1].battle_area.append(public_card)
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=secret_card)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 9900663, "source_card_id": 9900663, "source_zone": "battle", "played_from": "hand"},
    )
    declare = next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO)
    state = engine.apply_action(state, declare)

    public_effect_id = state.next_effect_id
    state.effect_registry.append(
        EffectRegistration(
            effect_id=public_effect_id,
            owner_player_id=1,
            source_instance_id=9900664,
            source_card_id=9900664,
                source_zone="battle",
                trigger="self_played",
                handler_id="auto_draw_n",
                handler_params={"amount": 1, "limit_per_turn": 1, "limit_scope": "card_number"},
                source_card_number="TEST-990067",
                limit_per_turn=1,
                limit_scope="card_number",
        )
    )
    state.next_effect_id += 1
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 9900664, "source_card_id": 9900664, "source_zone": "battle", "played_from": "battle"},
    )

    engine._resolve_pending_effects(state)

    row = next(r for r in state.effect_resolutions if r.effect_id == public_effect_id)
    assert row.resolved is False
    assert row.reason == "limit_per_turn_used"


def test_phase4_secret_auto_opportunity_is_preblocked_after_limit_is_already_used() -> None:
    engine = RulesEngine(
        effect_rules={
            99006631: [
                {"trigger": "owner_leader_attacks", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "limit_per_turn": 1},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=99006631, card_id=99006631, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    event_payload = {"attacker_instance_id": state.players[1].leader_area.instance_id, "attacker_zone": "leader", "target_player_id": 2, "target_zone": "leader"}
    engine._emit_effect_event(state, name="attack_declared", actor_player_id=1, payload=event_payload)
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))

    engine._emit_effect_event(state, name="attack_declared", actor_player_id=1, payload=event_payload)

    latest = state.secret_auto_opportunities[-1]
    assert latest.source_instance_id == 99006631
    assert latest.status == "blocked_limit_per_turn"
    assert all(row.action_type != ActionType.DECLARE_SECRET_AUTO for row in engine.get_legal_actions(state, 1))
    assert any(cp.name == "secret_auto_opportunity_preblocked" for cp in state.checkpoints)
    assert any("Secret-area auto opportunity preblocked" in row and "blocked_limit_per_turn" in row for row in state.log)


def test_phase4_secret_auto_once_per_turn_declares_only_once_for_same_source() -> None:
    engine = RulesEngine(
        effect_rules={
            9900671: [
                {"trigger": "owner_leader_attacks", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "once_per_turn": True},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=9900671, card_id=9900671, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": state.players[1].leader_area.instance_id, "attacker_zone": "leader", "target_player_id": 2, "target_zone": "leader"},
    )
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": state.players[1].leader_area.instance_id, "attacker_zone": "leader", "target_player_id": 2, "target_zone": "leader"},
    )

    deck_before = len(state.players[1].deck)
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))

    secret_auto_id = next(row.secret_auto_id for row in state.secret_auto_opportunities if row.source_instance_id == 9900671)
    rows = [r for r in state.effect_resolutions if r.effect_id == -secret_auto_id]
    assert sum(1 for r in rows if r.resolved and r.reason == "ok") == 1
    assert sum(1 for r in rows if (not r.resolved) and r.reason == "once_per_turn_used") == 1
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "secret_auto_declared_once_per_turn_blocked" for cp in state.checkpoints)
    assert any(row.status == "blocked_once_per_turn" for row in state.secret_auto_opportunities if row.source_instance_id == 9900671)


def test_phase4_secret_auto_opportunity_is_preblocked_after_once_per_turn_is_already_used() -> None:
    engine = RulesEngine(
        effect_rules={
            99006711: [
                {"trigger": "owner_leader_attacks", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "once_per_turn": True},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=99006711, card_id=99006711, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    event_payload = {"attacker_instance_id": state.players[1].leader_area.instance_id, "attacker_zone": "leader", "target_player_id": 2, "target_zone": "leader"}
    engine._emit_effect_event(state, name="attack_declared", actor_player_id=1, payload=event_payload)
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))

    engine._emit_effect_event(state, name="attack_declared", actor_player_id=1, payload=event_payload)

    latest = state.secret_auto_opportunities[-1]
    assert latest.source_instance_id == 99006711
    assert latest.status == "blocked_once_per_turn"
    assert all(row.action_type != ActionType.DECLARE_SECRET_AUTO for row in engine.get_legal_actions(state, 1))
    assert any(cp.name == "secret_auto_opportunity_preblocked" for cp in state.checkpoints)
    assert any("Secret-area auto opportunity preblocked" in row and "blocked_once_per_turn" in row for row in state.log)


def test_phase4_declared_secret_auto_counts_against_public_once_per_turn_same_source() -> None:
    engine = RulesEngine(
        effect_rules={
            9900672: [
                {"trigger": "owner_leader_attacks", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "once_per_turn": True},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=9900672, card_id=9900672, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": state.players[1].leader_area.instance_id, "attacker_zone": "leader", "target_player_id": 2, "target_zone": "leader"},
    )
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))

    public_effect_id = state.next_effect_id
    state.effect_registry.append(
        EffectRegistration(
            effect_id=public_effect_id,
            owner_player_id=1,
            source_instance_id=9900672,
            source_card_id=9900672,
            source_zone="hand",
            trigger="owner_leader_attacks",
            handler_id="auto_draw_n",
            handler_params={"amount": 1},
            source_card_number="",
            once_per_turn=True,
        )
    )
    state.next_effect_id += 1
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": state.players[1].leader_area.instance_id, "attacker_zone": "leader", "target_player_id": 2, "target_zone": "leader"},
    )

    engine._resolve_pending_effects(state)

    row = next(r for r in state.effect_resolutions if r.effect_id == public_effect_id)
    assert row.resolved is False
    assert row.reason == "once_per_turn_used"


def test_phase4_secret_auto_ignore_marks_status_without_resolving() -> None:
    engine = RulesEngine(
        effect_rules={
            990067: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990067, card_id=990067, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990067, "source_card_id": 990067, "source_zone": "battle", "played_from": "hand"},
    )

    deck_before = len(state.players[1].deck)
    ignore = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.IGNORE_SECRET_AUTO)
    state = engine.apply_action(state, ignore)

    opportunity = next(row for row in state.secret_auto_opportunities if row.source_instance_id == 990067)
    assert opportunity.status == "ignored"
    assert len(state.players[1].deck) == deck_before
    assert not any(row.effect_id == -opportunity.secret_auto_id for row in state.effect_resolutions)
    assert any(cp.name == "secret_auto_ignored" for cp in state.checkpoints)


def test_phase4_secret_auto_actions_are_ordered_turn_player_first() -> None:
    engine = RulesEngine(
        effect_rules={
            990068: [{"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}}],
            990069: [{"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}}],
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].hand = [CardInstance(instance_id=990068, card_id=990068, owner_id=1, card_type="BATTLE", has_auto=True)]
    state.players[2].hand = [CardInstance(instance_id=990069, card_id=990069, owner_id=2, card_type="BATTLE", has_auto=True)]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=state.players[1].hand[0])
    engine._register_card_effects(state, player_id=2, source_zone="hand", card=state.players[2].hand[0])

    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990068, "source_card_id": 990068, "source_zone": "battle", "played_from": "hand"},
    )
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=2,
        payload={"source_instance_id": 990069, "source_card_id": 990069, "source_zone": "battle", "played_from": "hand"},
    )

    legal_p1 = engine.get_legal_actions(state, 1)
    assert [row.action_type for row in legal_p1] == [ActionType.DECLARE_SECRET_AUTO, ActionType.IGNORE_SECRET_AUTO]
    assert engine.get_legal_actions(state, 2) == []

    state = engine.apply_action(state, next(a for a in legal_p1 if a.action_type == ActionType.IGNORE_SECRET_AUTO))
    legal_p2 = engine.get_legal_actions(state, 2)
    assert [row.action_type for row in legal_p2] == [ActionType.DECLARE_SECRET_AUTO, ActionType.IGNORE_SECRET_AUTO]


def test_phase4_stale_pending_secret_auto_opportunity_is_pruned_when_source_leaves_zone() -> None:
    engine = RulesEngine(
        effect_rules={
            990070: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990070, card_id=990070, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990070, "source_card_id": 990070, "source_zone": "battle", "played_from": "hand"},
    )
    assert any(row.source_instance_id == 990070 for row in state.secret_auto_opportunities)

    state.players[1].hand.clear()
    engine._run_confirmative_rule_processing(state)

    assert all(row.source_instance_id != 990070 for row in state.secret_auto_opportunities)
    assert any(cp.name == "secret_auto_opportunity_pruned" for cp in state.checkpoints)


def test_phase4_pending_effects_resolve_turn_player_first_for_simultaneous_public_triggers() -> None:
    def ordered_handler(state, event, reg):
        state.log.append(f"ordered:{reg.owner_player_id}:{event.event_id}")

    engine = RulesEngine(effect_handlers={"noop_auto": ordered_handler})
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].battle_area.append(CardInstance(instance_id=990071, card_id=71, owner_id=1, card_type="BATTLE"))
    state.players[2].battle_area.append(CardInstance(instance_id=990072, card_id=72, owner_id=2, card_type="BATTLE"))
    state.effect_registry.extend(
        [
            EffectRegistration(
                effect_id=state.next_effect_id,
                owner_player_id=1,
                source_instance_id=990071,
                source_card_id=71,
                source_zone="battle",
                trigger="owner_field_extra_placed",
                handler_id="noop_auto",
            ),
            EffectRegistration(
                effect_id=state.next_effect_id + 1,
                owner_player_id=2,
                source_instance_id=990072,
                source_card_id=72,
                source_zone="battle",
                trigger="owner_field_extra_placed",
                handler_id="noop_auto",
            ),
        ]
    )
    state.next_effect_id += 2

    engine._emit_effect_event(state, name="field_extra_placed", actor_player_id=1, payload={})
    engine._resolve_pending_effects(state)

    ordered = [row for row in state.log if row.startswith("ordered:")]
    assert ordered[0].startswith(f"ordered:{state.active_player}:")
    assert ordered[1].startswith(f"ordered:{engine._opponent_of(state.active_player)}:")


def test_phase4_auto_draw_on_play_empty_deck_causes_loss() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    p1 = state.players[1]
    p1.deck = []
    p1.hand = [
        CardInstance(
            instance_id=880051,
            card_id=51,
            owner_id=1,
            card_type="BATTLE",
            energy_cost=0,
            has_auto=True,
            has_draw=True,
            auto_draw_on_play=True,
        )
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.winner_id == 2


def test_phase4_auto_draw_on_attack_resolves_after_counter_timing() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.append(
        CardInstance(
            instance_id=880061,
            card_id=61,
            owner_id=1,
            card_type="BATTLE",
            energy_cost=0,
            has_auto=True,
            has_draw=True,
            auto_draw_on_attack=True,
        )
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    deck_before = len(state.players[1].deck)

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0
    )
    state = engine.apply_action(state, attack)
    # Pending during counter timing.
    assert len(state.players[1].deck) == deck_before
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_draw_on_attack" for cp in state.checkpoints)


def test_phase4_auto_draw_on_attack_empty_deck_causes_loss() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].deck = []
    state.players[1].battle_area.append(
        CardInstance(
            instance_id=880071,
            card_id=71,
            owner_id=1,
            card_type="BATTLE",
            energy_cost=0,
            has_auto=True,
            has_draw=True,
            auto_draw_on_attack=True,
        )
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.winner_id == 2


def test_phase4_combo_declared_triggers_self_comboed_draw_rule() -> None:
    engine = RulesEngine(
        effect_rules={
            424255: [
                {
                    "trigger": "self_comboed",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880201, card_id=201, owner_id=1, card_type="BATTLE", energy_cost=0, power=15000)
    )
    state.players[1].hand = [
        CardInstance(instance_id=880203, card_id=424255, owner_id=1, card_type="BATTLE", combo_cost=0, combo_power=5000)
    ]
    deck_before = len(state.players[1].deck)

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    combo = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo)

    assert len(state.players[1].deck) == deck_before - 1
    assert any(evt.name == "card_comboed" for evt in state.effect_events)
    assert any(res.resolved and res.reason == "ok" for res in state.effect_resolutions)


def test_phase4_combo_draw_rule_respects_leader_and_sparking_requirements() -> None:
    engine = RulesEngine(
        effect_rules={
            424256: [
                {
                    "trigger": "self_comboed",
                    "handler_id": "auto_draw_n",
                    "handler_params": {
                        "amount": 1,
                        "requires_leader": "if your leader card is red",
                        "min_owner_drop": 5,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].leader_area.color = "Red"
    state.players[1].battle_area.append(
        CardInstance(instance_id=880211, card_id=201, owner_id=1, card_type="BATTLE", energy_cost=0, power=15000)
    )
    state.players[1].hand = [
        CardInstance(instance_id=880212, card_id=424256, owner_id=1, card_type="BATTLE", combo_cost=0, combo_power=5000)
    ]
    deck_before = len(state.players[1].deck)

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    combo = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo)
    assert len(state.players[1].deck) == deck_before

    state.players[1].drop = [CardInstance(instance_id=880300 + i, card_id=300 + i, owner_id=1, card_type="BATTLE") for i in range(5)]
    state.players[1].hand = [
        CardInstance(instance_id=880213, card_id=424256, owner_id=1, card_type="BATTLE", combo_cost=0, combo_power=5000)
    ]
    combo = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo)
    assert len(state.players[1].deck) == deck_before - 1


def test_phase4_combo_can_reduce_opponent_battle_power_with_or_leader_requirement() -> None:
    engine = RulesEngine(
        effect_rules={
            5332: [
                {
                    "trigger": "self_comboed",
                    "handler_id": "auto_power_reduce_up_to_n_on_combo",
                    "handler_params": {
                        "max_targets": 1,
                        "power_delta": -10000,
                        "target_policy": "first",
                        "requires_leader": "if your leader card is red or yellow",
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].leader_area.color = "Yellow"
    state.players[1].battle_area.append(
        CardInstance(instance_id=880214, card_id=201, owner_id=1, card_type="BATTLE", energy_cost=0, power=15000)
    )
    state.players[1].hand = [
        CardInstance(instance_id=880215, card_id=5332, owner_id=1, card_type="BATTLE", combo_cost=0, combo_power=10000)
    ]
    state.players[2].battle_area.append(
        CardInstance(instance_id=880216, card_id=301, owner_id=2, card_type="BATTLE", energy_cost=2, power=15000)
    )

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    combo = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo)

    assert state.players[2].battle_area[0].power == 5000
    assert any(cp.name == "effect_auto_power_reduce_up_to_n_on_combo" for cp in state.checkpoints)


def test_phase4_play_can_gain_self_power_for_turn_with_opponent_drop_requirement() -> None:
    engine = RulesEngine(
        effect_rules={
            8051: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_self_gain_power_for_turn_on_play",
                    "handler_params": {"power_delta": 15000, "min_opponent_drop": 20},
                    "limit_per_turn": 1,
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=880217,
        card_id=8051,
        owner_id=1,
        card_type="BATTLE",
        color="Green",
        power=20000,
        energy_cost=0,
        has_auto=True,
    )
    state.players[1].hand = [source]
    state.players[2].drop = [
        CardInstance(instance_id=881000 + i, card_id=9000 + i, owner_id=2, card_type="BATTLE")
        for i in range(20)
    ]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    played = next(card for card in state.players[1].battle_area if card.instance_id == 880217)
    assert played.power == 35000
    assert any(cp.name == "effect_auto_self_gain_power_for_turn_on_play" for cp in state.checkpoints)


def test_phase4_activate_main_can_play_from_owner_z_deck_with_skills_negated() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "Green", 0, "LEADER", "[]", '["Fused Zamasu, Insanity From Justice"]', False, False, False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False, False),
                8050: ("Gowasu, Instructor", "Green", 0, "UNISON", "[]", "[]", True, False, False),
                910201: ("Zamasu Recruit", "Green", 1, "BATTLE", "[]", '["Zamasu"]', False, False, True),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_activate_battle, has_auto = data.get(
                card_id,
                ("Card", "Green", 1, "BATTLE", "[]", "[]", False, False, False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=has_activate_battle,
                has_auto=has_auto,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            8050: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_up_to_n_from_owner_z_deck_or_z_energy",
                    "handler_params": {
                        "max_targets": 1,
                        "source_pool": "z_deck_or_z_energy",
                        "allowed_colors": "green",
                        "required_characters": "zamasu,goku black",
                        "max_cost": 1,
                        "negate_skills": True,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[910201],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].z_deck[0].face_up = True
    source = CardInstance(
        instance_id=880218,
        card_id=8050,
        owner_id=1,
        card_number="BT26-065",
        card_type="UNISON",
        color="Green",
        has_activate_main=True,
        markers=1,
    )
    state.players[1].unison_area = [source]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)

    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert not state.players[1].z_deck
    played = next(card for card in state.players[1].battle_area if card.card_id == 910201)
    assert played.has_auto is False
    assert played.has_activate_main is False
    assert any(cp.name == "effect_activate_play_up_to_n_from_owner_z_deck_or_z_energy" for cp in state.checkpoints)


def test_phase4_activate_main_can_gain_multiple_keywords_for_turn_and_emit_skill_drop_cause() -> None:
    engine = RulesEngine(
        effect_rules={
            672: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_gain_power_and_keyword_for_turn",
                    "handler_params": {"grant_keywords": "Critical,Double Strike"},
                    "once_per_turn": True,
                }
            ]
        },
        skill_cost_rules={
            672: {
                "activate_main": [
                    {
                        "kind": "send_other_battle_to_drop",
                        "amount": 1,
                        "required_traits": "Red Ribbon Army",
                    }
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=880219,
        card_id=672,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        has_activate_main=True,
    )
    fodder = CardInstance(
        instance_id=880220,
        card_id=900220,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        traits=("Red Ribbon Army",),
    )
    state.players[1].battle_area = [source, fodder]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    source_after = next(card for card in state.players[1].battle_area if card.instance_id == 880219)
    assert "Critical" in source_after.temporary_keywords
    assert "Double Strike" in source_after.temporary_keywords
    assert any(card.instance_id == 880220 for card in state.players[1].drop)
    skill_drop_event = next(
        evt for evt in state.effect_events
        if evt.name == "card_placed_into_drop" and int(evt.payload.get("source_instance_id") or -1) == 880220
    )
    assert skill_drop_event.payload.get("drop_cause") == "skill"
    assert any(cp.name == "effect_activate_gain_power_and_keyword_for_turn" for cp in state.checkpoints)


def test_phase4_combo_battle_end_can_play_self_from_combo_to_battle_resting() -> None:
    engine = RulesEngine(
        effect_rules={
            424256: [
                {
                    "trigger": "self_comboed_battle_end",
                    "handler_id": "auto_play_self_from_combo_on_battle_end",
                    "handler_params": {"resting": True},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880211, card_id=211, owner_id=1, card_type="BATTLE", energy_cost=0, power=15000)
    )
    state.players[1].hand = [
        CardInstance(instance_id=880212, card_id=424256, owner_id=1, card_type="BATTLE", combo_cost=0, combo_power=5000)
    ]

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    combo = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo)
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))

    played = next((c for c in state.players[1].battle_area if c.instance_id == 880212), None)
    assert played is not None
    assert played.resting is True
    assert all(c.instance_id != 880212 for c in state.players[1].combo_area)
    assert any(cp.name == "effect_auto_play_self_from_combo_on_battle_end" for cp in state.checkpoints)


def test_phase4_turn_end_switch_self_active_handler() -> None:
    engine = RulesEngine(
        effect_rules={
            424257: [
                {
                    "trigger": "turn_end",
                    "handler_id": "auto_switch_self_active_on_turn_end",
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880221, card_id=424257, owner_id=1, card_type="BATTLE", energy_cost=0, resting=False)
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state.players[1].battle_area[0].resting = True

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert state.players[1].battle_area[0].resting is False
    assert any(cp.name == "effect_auto_switch_self_active_on_turn_end" for cp in state.checkpoints)


def test_phase4_play_top_deck_add_if_color_on_play_matches_and_adds_to_hand() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            color_map = {
                1: "Red",
                2: "Blue",
                900001: "Black",
                424258: "Black",
            }
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color=color_map.get(card_id, "Red"),
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424258: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_top_deck_add_if_color_on_play",
                    "handler_params": {"required_color": "black", "move_to_bottom_on_fail": True},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900001] + _deck(1000, 59),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].deck = [900001] + state.players[1].deck
    deck_before = len(state.players[1].deck)
    state.players[1].hand = [CardInstance(instance_id=880231, card_id=424258, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].deck) == deck_before - 1
    assert any(c.card_id == 900001 for c in state.players[1].hand)
    assert any(cp.name == "effect_auto_top_deck_add_if_color_on_play" for cp in state.checkpoints)


def test_phase4_play_top_deck_add_if_color_on_play_miss_moves_top_to_bottom() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            color_map = {
                1: "Red",
                2: "Blue",
                900002: "Red",
                900003: "Blue",
                424259: "Black",
            }
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color=color_map.get(card_id, "Red"),
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424259: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_top_deck_add_if_color_on_play",
                    "handler_params": {"required_color": "black", "move_to_bottom_on_fail": True},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900002, 900003] + _deck(1000, 58),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].deck = [900002, 900003] + state.players[1].deck
    first_before = state.players[1].deck[0]
    state.players[1].hand = [CardInstance(instance_id=880241, card_id=424259, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].deck[0] == 900003
    assert state.players[1].deck[-1] == first_before
    assert any(cp.name == "effect_auto_top_deck_bottom_on_fail" for cp in state.checkpoints)


def test_phase4_self_activate_main_draw_rule_resolves_on_skill_activation() -> None:
    engine = RulesEngine(
        effect_rules={
            1: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.has_activate_main = True
    deck_before = len(state.players[1].deck)
    act = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "leader")
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].deck) == deck_before - 1
    assert any(evt.name == "skill_activated" for evt in state.effect_events)
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_owner_black_battle_played_from_warp_triggers_wormhole_gain_handler() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            color_map = {1: "Black", 2: "Blue", 900100: "Black"}
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color=color_map.get(card_id, "Red"),
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            1: [
                {
                    "trigger": "owner_battle_played_from_warp",
                    "handler_id": "auto_gain_wormhole_on_owner_black_battle_played_from_warp",
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 999001, "source_card_id": 900100, "source_zone": "battle", "played_from": "warp"},
    )
    engine._resolve_pending_effects(state)
    assert any(cp.name == "effect_auto_gain_wormhole_on_owner_black_battle_played_from_warp" for cp in state.checkpoints)
    assert any("wormhole_gain" in line for line in state.log)


def test_phase4_self_activate_battle_draw_n_resolves_on_skill_activated_event() -> None:
    engine = RulesEngine(
        effect_rules={
            424287: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    src = CardInstance(instance_id=880105, card_id=424287, owner_id=1, card_type="BATTLE", energy_cost=0)
    state.players[1].battle_area.append(src)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=src)
    deck_before = len(state.players[1].deck)
    hand_before = len(state.players[1].hand)
    engine._emit_effect_event(
        state,
        name="skill_activated",
        actor_player_id=1,
        payload={"source_instance_id": 880105, "source_card_id": 424287, "source_zone": "battle", "skill_kind": "activate_battle"},
    )
    engine._resolve_pending_effects(state)
    assert len(state.players[1].deck) == deck_before - 1
    assert len(state.players[1].hand) == hand_before + 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_owner_other_battle_played_by_dark_over_realm_can_draw() -> None:
    engine = RulesEngine(
        effect_rules={
            8318: [
                {
                    "trigger": "owner_other_battle_played_by_dark_over_realm",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                    "limit_per_turn": 1,
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    putine = CardInstance(
        instance_id=881500,
        card_id=8318,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        power=15000,
        skill_text_raw=(
            "[Dark Over Realm 4]{b}, if your Leader is a <Mechikabura> card and you draw 1 card:\n"
            "[Auto][Limit 1] When your Battle Card other than this card is played by a [Dark Over Realm] skill, draw 1 card."
        ),
    )
    state.players[1].battle_area.append(putine)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=putine)
    hand_before = len(state.players[1].hand)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={
            "source_instance_id": 881501,
            "source_card_id": 8319,
            "source_zone": "battle",
            "played_via": "dark_over_realm",
        },
    )
    engine._resolve_pending_effects(state)
    assert len(state.players[1].hand) == hand_before + 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_owner_opponent_skill_plays_overcost_battle_can_rest_self_and_reduce_power() -> None:
    engine = RulesEngine(
        effect_rules={
            424285: [
                {
                    "trigger": "owner_opponent_skill_plays_overcost_battle",
                    "handler_id": "auto_rest_self_on_owner_opponent_skill_play_overcost_battle_reduce_power",
                    "handler_params": {"power_delta": -10000},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].battle_area.append(
        CardInstance(instance_id=880097, card_id=424285, owner_id=1, card_type="BATTLE", energy_cost=0, resting=False)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    state.players[2].energy = [
        CardInstance(instance_id=880098, card_id=920001, owner_id=2, color="Blue", resting=False),
        CardInstance(instance_id=880099, card_id=920002, owner_id=2, color="Blue", resting=False),
    ]
    state.players[2].battle_area.append(
        CardInstance(instance_id=880100, card_id=920003, owner_id=2, card_type="BATTLE", energy_cost=4, power=25000)
    )
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=2,
        payload={"source_instance_id": 880100, "source_card_id": 920003, "source_zone": "battle", "played_from": "deck"},
    )
    engine._resolve_pending_effects(state)
    assert state.players[1].battle_area[0].resting is True
    assert state.players[2].battle_area[0].power == 15000
    assert any(cp.name == "effect_auto_rest_self_on_owner_opponent_skill_play_overcost_battle_reduce_power" for cp in state.checkpoints)


def test_phase4_owner_opponent_skill_plays_overcost_battle_can_rest_self_and_switch_target_rest() -> None:
    engine = RulesEngine(
        effect_rules={
            424286: [
                {
                    "trigger": "owner_opponent_skill_plays_overcost_battle",
                    "handler_id": "auto_rest_self_on_owner_opponent_skill_play_overcost_battle_switch_target_rest",
                    "handler_params": {},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].battle_area.append(
        CardInstance(instance_id=880101, card_id=424286, owner_id=1, card_type="BATTLE", energy_cost=0, resting=False)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    state.players[2].energy = [
        CardInstance(instance_id=880102, card_id=920011, owner_id=2, color="Blue", resting=False),
        CardInstance(instance_id=880103, card_id=920012, owner_id=2, color="Blue", resting=False),
    ]
    state.players[2].battle_area.append(
        CardInstance(instance_id=880104, card_id=920013, owner_id=2, card_type="BATTLE", energy_cost=4, power=25000, resting=False)
    )
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=2,
        payload={"source_instance_id": 880104, "source_card_id": 920013, "source_zone": "battle", "played_from": "deck"},
    )
    engine._resolve_pending_effects(state)
    assert state.players[1].battle_area[0].resting is True
    assert state.players[2].battle_area[0].resting is True
    assert any(cp.name == "effect_auto_rest_self_on_owner_opponent_skill_play_overcost_battle_switch_target_rest" for cp in state.checkpoints)


def test_phase4_played_add_top_deck_to_energy_respects_requires_mono_energy() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            color_map = {1: "Blue", 2: "Blue", 900200: "Red", 424261: "Blue"}
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color=color_map.get(card_id, "Blue"),
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424261: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_add_top_deck_to_energy_rest_on_play",
                    "handler_params": {"requires_mono_energy": "blue"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900200] + _deck(1000, 59),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    # Break mono-blue requirement.
    state.players[1].energy = [CardInstance(instance_id=990301, card_id=900200, owner_id=1, card_type="BATTLE", color="Red")]
    energy_before = len(state.players[1].energy)
    state.players[1].hand = [CardInstance(instance_id=880251, card_id=424261, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].energy) == energy_before


def test_phase4_played_look_top_add_up_to_one_to_hand_on_play() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            payload = {
                1: ("Blue", 0),
                2: ("Blue", 0),
                900401: ("Green", 3),
                900402: ("Red", 2),
                900403: ("Yellow", 5),
                424262: ("Yellow", 2),
            }
            color, cost = payload.get(card_id, ("Blue", 0))
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424262: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_look_top_add_up_to_one_to_hand_on_play",
                    "handler_params": {
                        "look_count": 3,
                        "max_add": 1,
                        "max_cost": 4,
                        "allowed_colors": "green,yellow",
                        "required_card_type": "BATTLE",
                        "requires_played_from": "hand",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900402, 900401, 900403] + _deck(1000, 57),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].deck = [900402, 900401, 900403] + state.players[1].deck
    state.players[1].hand = [CardInstance(instance_id=880261, card_id=424262, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    # Green cost-3 match in top 3 should be added to hand.
    assert any(c.card_id == 900401 for c in state.players[1].hand)
    assert all(c.card_id != 424262 for c in state.players[1].hand)
    assert any(cp.name == "effect_auto_look_top_add_up_to_one_to_hand_on_play" for cp in state.checkpoints)


def test_phase4_played_look_top_add_up_to_two_to_hand_on_play() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            payload = {
                1: ("Blue", 0),
                2: ("Blue", 0),
                900411: ("Green", 3),
                900412: ("Yellow", 4),
                900413: ("Red", 2),
                424263: ("Yellow", 2),
            }
            color, cost = payload.get(card_id, ("Blue", 0))
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424263: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_look_top_add_up_to_one_to_hand_on_play",
                    "handler_params": {
                        "look_count": 4,
                        "max_add": 2,
                        "max_cost": 6,
                        "allowed_colors": "green,yellow",
                        "required_card_type": "BATTLE",
                        "requires_played_from": "hand",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900413, 900411, 900412] + _deck(1000, 57),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].deck = [900413, 900411, 900412] + state.players[1].deck
    state.players[1].hand = [CardInstance(instance_id=880271, card_id=424263, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    hand_ids = {c.card_id for c in state.players[1].hand}
    assert 900411 in hand_ids
    assert 900412 in hand_ids


def test_phase4_self_ko_trigger_reduces_opponent_unison_power() -> None:
    engine = RulesEngine(
        effect_rules={
            424264: [
                {
                    "trigger": "self_koed",
                    "handler_id": "auto_power_reduce_opponent_unison_on_self_ko",
                    "handler_params": {"max_targets": 1, "power_delta": -10000, "target_policy": "first"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880281, card_id=424264, owner_id=1, card_type="BATTLE", energy_cost=0)
    state.players[1].battle_area.append(source)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    state.players[2].unison_area = [
        CardInstance(instance_id=880282, card_id=282, owner_id=2, card_type="UNISON", energy_cost=3, power=12000, markers=2)
    ]

    engine._ko_card(state, player_id=1, zone="battle", instance_id=880281)
    engine._resolve_pending_effects(state)

    assert state.players[2].unison_area[0].power == 2000
    assert any(cp.name == "effect_auto_power_reduce_opponent_unison_on_self_ko" for cp in state.checkpoints)


def test_phase4_turn_end_switch_up_to_n_owner_energy_active() -> None:
    engine = RulesEngine(
        effect_rules={
            424265: [
                {
                    "trigger": "turn_end",
                    "handler_id": "auto_switch_up_to_n_owner_energy_active_on_turn_end",
                    "handler_params": {"max_targets": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=880291, card_id=424265, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state.players[1].energy = [
        CardInstance(instance_id=880292, card_id=292, owner_id=1, card_type="BATTLE", color="Blue", resting=True),
        CardInstance(instance_id=880293, card_id=293, owner_id=1, card_type="BATTLE", color="Blue", resting=True),
    ]
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert sum(1 for e in state.players[1].energy if not e.resting) == 1
    assert any(cp.name == "effect_auto_switch_up_to_n_owner_energy_active_on_turn_end" for cp in state.checkpoints)


def test_phase4_turn_end_switch_up_to_n_owner_energy_active_multicolor_filter() -> None:
    engine = RulesEngine(
        effect_rules={
            424266: [
                {
                    "trigger": "turn_end",
                    "handler_id": "auto_switch_up_to_n_owner_energy_active_on_turn_end",
                    "handler_params": {"max_targets": 2, "allowed_colors": "blue,yellow", "requires_multicolor": True},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=880301, card_id=424266, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state.players[1].energy = [
        CardInstance(instance_id=880302, card_id=302, owner_id=1, card_type="BATTLE", color="Blue/Yellow", resting=True),
        CardInstance(instance_id=880303, card_id=303, owner_id=1, card_type="BATTLE", color="Blue", resting=True),
        CardInstance(instance_id=880304, card_id=304, owner_id=1, card_type="BATTLE", color="Yellow/Blue", resting=True),
    ]
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    by_id = {e.instance_id: e.resting for e in state.players[1].energy}
    assert by_id[880302] is False
    assert by_id[880304] is False
    assert by_id[880303] is True


def test_phase4_self_played_can_play_matching_card_from_owner_deck() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", 15000),
                2: ("Blue", 15000),
                900501: ("Red", 9000),
                900502: ("Blue", 8000),
                900503: ("Red", 15000),
                424267: ("Blue", 15000),
            }
            color, power = data.get(card_id, ("Blue", 15000))
            return SimpleNamespace(
                power_int=power,
                card_type="BATTLE",
                card_color=color,
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424267: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_deck_on_play",
                    "handler_params": {
                        "max_targets": 1,
                        "max_power": 10000,
                        "allowed_colors": "red",
                        "requires_played_from": "hand",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900502, 900501, 900503] + _deck(1000, 57),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].deck = [900502, 900501, 900503] + state.players[1].deck
    state.players[1].hand = [CardInstance(instance_id=880311, card_id=424267, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(c.card_id == 900501 for c in state.players[1].battle_area)
    assert all(c.card_id != 900503 for c in state.players[1].battle_area)
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_deck_on_play" for cp in state.checkpoints)


def test_phase4_self_comboed_can_play_matching_card_from_owner_hand() -> None:
    engine = RulesEngine(
        effect_rules={
            424268: [
                {
                    "trigger": "self_comboed",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_on_self_combo",
                    "handler_params": {"max_targets": 1, "max_cost": 5, "allowed_colors": "blue", "rest_mode": True},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880321, card_id=321, owner_id=1, card_type="BATTLE", energy_cost=0, power=15000)
    )
    state.players[1].hand = [
        CardInstance(instance_id=880322, card_id=424268, owner_id=1, card_type="BATTLE", combo_cost=0, combo_power=5000),
        CardInstance(instance_id=880323, card_id=323, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=5),
        CardInstance(instance_id=880324, card_id=324, owner_id=1, card_type="BATTLE", color="Red", energy_cost=3),
    ]
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    combo = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, combo)

    played = next((c for c in state.players[1].battle_area if c.instance_id == 880323), None)
    assert played is not None and played.resting is True
    assert all(c.instance_id != 880324 for c in state.players[1].battle_area)
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_hand_on_self_combo" for cp in state.checkpoints)


def test_phase4_self_played_can_gain_control_of_opponent_unison() -> None:
    engine = RulesEngine(
        effect_rules={
            424269: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_gain_control_opponent_unison_on_play",
                    "handler_params": {"max_targets": 1, "target_policy": "first"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].unison_area = [
        CardInstance(instance_id=880331, card_id=331, owner_id=2, card_type="UNISON", markers=2)
    ]
    state.players[1].hand = [CardInstance(instance_id=880332, card_id=424269, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[2].unison_area) == 0
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].instance_id == 880331
    assert state.players[1].unison_area[0].owner_id == 2
    assert any(cp.name == "effect_auto_gain_control_opponent_unison_on_play" for cp in state.checkpoints)


def test_phase4_self_played_can_gain_control_of_opponent_battle() -> None:
    engine = RulesEngine(
        effect_rules={
            4715: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_gain_control_opponent_battle_on_play",
                    "handler_params": {"max_targets": 1, "max_cost": 3, "target_policy": "first"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    target = CardInstance(instance_id=880333, card_id=333, owner_id=2, card_type="BATTLE", energy_cost=3, power=15000, has_activate_main=True)
    state.players[2].battle_area = [target]
    state.players[1].hand = [CardInstance(instance_id=880334, card_id=4715, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[2].battle_area) == 0
    assert any(card.instance_id == 880333 and card.owner_id == 2 for card in state.players[1].battle_area)
    assert any(
        a.action_type == ActionType.ACTIVATE_MAIN_SKILL
        and a.source_zone == "battle"
        and state.players[1].battle_area[a.source_index].instance_id == 880333
        for a in engine.get_legal_actions(state, 1)
    )
    assert any(cp.name == "effect_auto_gain_control_opponent_battle_on_play" for cp in state.checkpoints)


def test_phase4_activate_main_can_transfer_self_control_to_opponent() -> None:
    engine = RulesEngine(
        effect_rules={
            1509: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_transfer_self_control_to_opponent",
                    "handler_params": {"requires_leader": "blue <Son Gohan: SH>"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Blue"
    state.players[1].leader_area.characters = ("Son Gohan: SH",)
    pan = CardInstance(
        instance_id=880335,
        card_id=1509,
        owner_id=1,
        card_type="BATTLE",
        energy_cost=1,
        power=4000,
        has_activate_main=True,
    )
    state.players[1].battle_area = [pan]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=pan)
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].battle_area) == 0
    assert any(card.instance_id == 880335 and card.owner_id == 1 for card in state.players[2].battle_area)
    assert any(cp.name == "effect_activate_transfer_self_control_to_opponent" for cp in state.checkpoints)


def test_phase4_self_played_can_draw_play_named_from_deck_then_transfer_self_control() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("LEADER", "Blue", "Leader One", (), ()),
                2: ("LEADER", "Blue", "Leader Two", (), ()),
                2461: ("BATTLE", "Green", "Paragus, Cunning Father", ("Saiyan", "Frieza's Army"), ("Paragus: Br",)),
                900701: ("BATTLE", "Green", "Energy Barrage Frieza", ("Frieza's Army",), ("Frieza",)),
                900702: ("BATTLE", "Green", "Wrong Target", ("Frieza's Army",), ("Frieza",)),
            }
            card_type, color, name, traits, characters = data.get(card_id, ("BATTLE", "Blue", f"Card {card_id}", (), ()))
            return SimpleNamespace(
                power_int=5000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=2,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="2",
                z_card=False,
                counter_modes=(),
                card_name=name,
                skill_text_raw="",
                card_number=str(card_id),
                traits=traits,
                characters=characters,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            2461: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                    "limit_per_turn": 1,
                },
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_deck_on_play",
                    "handler_params": {"max_targets": 1, "required_name_contains": "ENERGY BARRAGE FRIEZA"},
                    "limit_per_turn": 1,
                },
                {
                    "trigger": "self_played",
                    "handler_id": "auto_transfer_self_control_to_opponent_on_play",
                    "handler_params": {},
                    "limit_per_turn": 1,
                },
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900702, 900701] + _deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].deck = [900702, 900701] + _deck(1000)
    state.players[1].leader_area.traits = ("Paragus: Br",)
    state.players[1].hand = [CardInstance(instance_id=880336, card_id=2461, owner_id=1, card_type="BATTLE", energy_cost=0)]
    hand_before = len(state.players[1].hand)
    deck_before = list(state.players[1].deck)
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].hand) == hand_before
    assert 900701 not in state.players[1].deck
    assert any(card.card_id == 900702 for card in state.players[1].hand)
    assert any(card.card_id == 900701 for card in state.players[1].battle_area)
    assert all(card.card_id != 900702 for card in state.players[1].battle_area)
    assert any(card.instance_id == 880336 and card.owner_id == 1 for card in state.players[2].battle_area)
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_deck_on_play" for cp in state.checkpoints)
    assert any(cp.name == "effect_auto_transfer_self_control_to_opponent_on_play" for cp in state.checkpoints)
    assert state.players[1].deck != deck_before


def test_phase4_turn_start_and_end_can_transfer_self_control_to_opponent() -> None:
    engine = RulesEngine(
        effect_rules={
            6733: [
                {"trigger": "turn_start", "handler_id": "auto_transfer_self_control_to_opponent", "handler_params": {}},
                {"trigger": "turn_end", "handler_id": "auto_transfer_self_control_to_opponent", "handler_params": {}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    veku = CardInstance(instance_id=880337, card_id=6733, owner_id=1, card_type="BATTLE", energy_cost=5, power=1001)
    state.players[1].battle_area = [veku]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=veku)
    engine._emit_effect_event(state, name="turn_end", actor_player_id=1, payload={})
    engine._resolve_pending_effects(state)
    assert len(state.players[1].battle_area) == 0
    assert any(card.instance_id == 880337 and card.owner_id == 1 for card in state.players[2].battle_area)
    engine._emit_effect_event(state, name="turn_start", actor_player_id=2, payload={})
    engine._resolve_pending_effects(state)
    assert any(card.instance_id == 880337 and card.owner_id == 1 for card in state.players[1].battle_area)
    assert len(state.players[2].battle_area) == 0
    assert sum(1 for cp in state.checkpoints if cp.name == "effect_auto_transfer_self_control_to_opponent") == 2


def test_phase4_self_activate_main_search_add_then_discard() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", 0),
                2: ("Blue", 0),
                900601: ("Green/Yellow", 3),
                900602: ("Red", 2),
                900603: ("Yellow/Green", 4),
            }
            color, cost = data.get(card_id, ("Blue", 0))
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            1: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "auto_look_top_add_up_to_one_to_hand_on_play",
                    "handler_params": {
                        "look_count": 3,
                        "max_add": 1,
                        "allowed_colors": "green,yellow",
                        "discard_after_add": 1,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900602, 900601, 900603] + _deck(1000, 57),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.has_activate_main = True
    state.players[1].deck = [900602, 900601, 900603] + state.players[1].deck
    state.players[1].hand = [CardInstance(instance_id=880341, card_id=341, owner_id=1, card_type="BATTLE", energy_cost=0)]
    act = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "leader")
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    hand_ids = {c.card_id for c in state.players[1].hand}
    assert 900601 in hand_ids
    assert 341 not in hand_ids
    assert any(cp.name == "effect_auto_look_top_add_up_to_one_to_hand_on_play" for cp in state.checkpoints)


def test_phase4_self_activate_main_search_by_name_token_and_bottom_rest() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "Black", 0),
                2: ("Other Leader", "Blue", 0),
                900611: ("SS4 Son Goku", "Black", 3),
                900612: ("SS4 Vegeta", "Black", 4),
                900613: ("Regular Bardock", "Black", 2),
                990001: ("Bottom Me", "Red", 1),
            }
            name, color, cost = data.get(card_id, ("Card", "Black", 0))
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type="BATTLE",
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
                card_traits_json="[]",
                card_character_json="[]",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            1: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "auto_look_top_add_up_to_one_to_hand_on_play",
                    "handler_params": {
                        "look_count": 3,
                        "max_add": 2,
                        "allowed_colors": "black",
                        "required_name_contains": "SS4",
                        "move_unpicked_to_bottom": True,
                        "bottom_deck_after_add": 1,
                        "bottom_deck_after_add_exact_add_count": 2,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900611, 900613, 900612] + _deck(1000, 57),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.has_activate_main = True
    state.players[1].hand = [CardInstance(instance_id=880361, card_id=990001, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[1].deck = [900611, 900613, 900612] + state.players[1].deck
    act = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "leader")
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    hand_ids = [c.card_id for c in state.players[1].hand]
    assert 900611 in hand_ids
    assert 900612 in hand_ids
    assert 990001 not in hand_ids
    assert state.players[1].deck[-2:] == [900613, 990001]
    assert any(cp.name == "effect_auto_look_top_add_up_to_one_to_hand_on_play" for cp in state.checkpoints)


def test_phase4_activate_main_play_self_from_hand_with_requirements() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Power Wish Leader", "Blue", 0, '["Power Wish"]', "[]"),
                2: ("Other Leader", "Red", 0, "[]", "[]"),
                900701: ("Power Wish Body", "Blue", 3, '["Power Wish"]', '["Son Goku"]'),
            }
            name, color, cost, traits_json, characters_json = data.get(card_id, ("Card", "Blue", 0, "[]", "[]"))
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type="BATTLE",
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=card_id == 900701,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900701: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_hand",
                    "handler_params": {
                        "required_leader_traits": "Power Wish",
                        "min_owner_energy": 3,
                        "requires_no_owner_battle": True,
                        "requires_no_opponent_battle": True,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880701, card_id=1001, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880702, card_id=1002, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880703, card_id=1003, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
    ]
    state.players[1].hand = [
        CardInstance(instance_id=880704, card_id=900701, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=3, has_activate_main=True)
    ]
    state.players[1].leader_area.has_activate_main = False
    act = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand"
    )
    state = engine.apply_action(state, act)
    assert state.counter_window is not None
    assert state.counter_window.kind == "activate_main"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None
    assert state.counter_window.kind == "play"
    assert any(card.card_id == 900701 for card in state.players[1].hand)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert not state.players[1].hand
    assert any(card.card_id == 900701 for card in state.players[1].battle_area)
    assert any(cp.name == "counter_timing_play_from_skill" for cp in state.checkpoints)


def test_phase4_activate_main_play_self_from_hand_uses_hidden_mode_cost_reduction() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 1:
                return SimpleNamespace(
                    card_name="Universe 7 Leader",
                    power_int=10000,
                    card_type="LEADER",
                    card_color="White",
                    energy_cost_int=0,
                    combo_cost_int=0,
                    combo_power_int=0,
                    keywords=(),
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_draw=False,
                    max_draw=None,
                    has_barrier=False,
                    z_energy_cost=None,
                    card_energy_cost="0",
                    card_skill_unstyled="",
                    card_traits_json='["Universe 7"]',
                    card_character_json="[]",
                )
            if card_id == 900706:
                return SimpleNamespace(
                    card_name="Hidden Cost Reducer",
                    power_int=15000,
                    card_type="BATTLE",
                    card_color="White",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_activate_main=True,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=True,
                    has_draw=False,
                    max_draw=None,
                    has_barrier=False,
                    z_energy_cost=None,
                    card_energy_cost="2",
                    card_skill_unstyled=(
                        "[Activate: Main] Play this card from your hand.<br>"
                        "[Permanent] If your Leader is a white ≪Universe 7≫ card and you have a Hidden Mode card in your Battle Area, "
                        "reduce the energy cost of this card in your hand by 2."
                    ),
                    card_traits_json="[]",
                    card_character_json="[]",
                )
            return SimpleNamespace(
                card_name="Card",
                power_int=15000,
                card_type="LEADER" if card_id == 2 else "BATTLE",
                card_color="Blue",
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
                card_traits_json="[]",
                card_character_json="[]",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900706: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_hand",
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = []
    state.players[1].hand = [engine._create_card_instance(next_instance_id=880706, card_id=900706, owner_id=1)]
    state.players[1].battle_area.append(
        CardInstance(instance_id=880707, card_id=113, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True)
    )
    act = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand"
    )
    state = engine.apply_action(state, act)
    assert state.counter_window is not None
    assert state.counter_window.kind == "activate_main"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None
    assert state.counter_window.kind == "play"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert not state.players[1].hand
    assert any(card.card_id == 900706 for card in state.players[1].battle_area)


def test_phase4_activate_main_play_self_from_hand_unison_opens_second_counter_timing() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Power Wish Leader", "Blue", 0, "LEADER", '["Power Wish"]', "[]", False, False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False),
                900702: ("Power Wish Unison", "Blue", 3, "UNISON", "[]", "[]", True, True),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_auto = data.get(
                card_id,
                ("Card", "Blue", 0, "BATTLE", "[]", "[]", False, False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=has_auto,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900702: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_hand",
                    "handler_params": {
                        "required_leader_traits": "Power Wish",
                        "min_owner_energy": 3,
                        "markers": 1,
                    },
                },
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                },
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880711, card_id=1001, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880712, card_id=1002, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880713, card_id=1003, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
    ]
    deck_before = len(state.players[1].deck)
    state.players[1].hand = [
        CardInstance(instance_id=880714, card_id=900702, owner_id=1, card_type="UNISON", color="Blue", energy_cost=3, has_activate_main=True, has_auto=True)
    ]
    state.players[1].leader_area.has_activate_main = False
    act = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand"
    )
    state = engine.apply_action(state, act)
    assert state.counter_window is not None and state.counter_window.kind == "activate_main"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None and state.counter_window.kind == "play"
    assert any(card.card_id == 900702 for card in state.players[1].hand)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert all(card.card_id != 900702 for card in state.players[1].hand)
    assert any(card.card_id == 900702 for card in state.players[1].unison_area)
    assert state.players[1].unison_area[0].markers == 1
    secret_auto = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_SECRET_AUTO)
    state = engine.apply_action(state, secret_auto)
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "counter_timing_play_from_skill" for cp in state.checkpoints)
    assert any(cp.name == "main_play_unison" for cp in state.checkpoints)


def test_phase4_activate_main_play_self_from_hand_unison_replaces_existing_unison() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Power Wish Leader", "Blue", 0, "LEADER", '["Power Wish"]', "[]", False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False),
                900703: ("Power Wish Unison", "Blue", 3, "UNISON", "[]", "[]", True),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main = data.get(
                card_id,
                ("Card", "Blue", 0, "BATTLE", "[]", "[]", False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900703: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_hand",
                    "handler_params": {
                        "required_leader_traits": "Power Wish",
                        "min_owner_energy": 3,
                        "markers": 2,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880721, card_id=1001, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880722, card_id=1002, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880723, card_id=1003, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
    ]
    state.players[1].unison_area.append(CardInstance(instance_id=880724, card_id=901000, owner_id=1, card_type="UNISON", markers=1))
    state.players[1].hand = [
        CardInstance(instance_id=880725, card_id=900703, owner_id=1, card_type="UNISON", color="Blue", energy_cost=3, has_activate_main=True)
    ]
    act = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand"
    )
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None and state.counter_window.kind == "play"
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=state.counter_window.responder_player_id),
    )
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].card_id == 900703
    assert state.players[1].unison_area[0].markers == 2
    assert any(card.instance_id == 880724 for card in state.players[1].drop)
    assert any(cp.name == "unison_replaced" for cp in state.checkpoints)


def test_phase4_activate_main_play_self_from_hand_unison_replaces_hidden_mode_card_in_unison_area() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Power Wish Leader", "Blue", 0, "LEADER", '["Power Wish"]', "[]", False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False),
                900704: ("Power Wish Hidden Replacement Unison", "Blue", 3, "UNISON", "[]", "[]", True),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main = data.get(
                card_id,
                ("Card", "Blue", 0, "BATTLE", "[]", "[]", False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900704: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_hand",
                    "handler_params": {
                        "required_leader_traits": "Power Wish",
                        "min_owner_energy": 3,
                        "markers": 2,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880726, card_id=1001, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880727, card_id=1002, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880728, card_id=1003, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
    ]
    state.players[1].unison_area.append(CardInstance(instance_id=880729, card_id=901001, owner_id=1, card_type="BATTLE", hidden_mode=True))
    state.players[1].hand = [
        CardInstance(instance_id=880730, card_id=900704, owner_id=1, card_type="UNISON", color="Blue", energy_cost=3, has_activate_main=True)
    ]
    act = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand"
    )
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None and state.counter_window.kind == "play"
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=state.counter_window.responder_player_id),
    )
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].card_id == 900704
    assert state.players[1].unison_area[0].markers == 2
    assert any(card.instance_id == 880729 for card in state.players[1].drop)
    assert any(cp.name == "unison_replaced" for cp in state.checkpoints)


def test_phase4_activate_main_switch_owner_battle_to_hidden_mode() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "White", 0, "LEADER", "[]", "[]", False, False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False),
                900730: ("Hidden Switcher", "White", 2, "BATTLE", "[]", "[]", True, False),
                900731: ("Universe 7 Fighter", "White", 2, "BATTLE", '["Universe 7"]', "[]", False, False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_auto = data.get(
                card_id,
                ("Card", "White", 0, "BATTLE", "[]", "[]", False, False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=has_auto,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900730: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_switch_owner_battle_to_hidden_mode",
                    "handler_params": {
                        "allowed_colors": "white",
                        "required_traits": "Universe 7",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=880730, card_id=900730, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True),
            CardInstance(instance_id=880731, card_id=900731, owner_id=1, card_type="BATTLE", color="White"),
        ]
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].battle_area[1].hidden_mode is True
    assert any(cp.name == "effect_activate_switch_owner_battle_to_hidden_mode" for cp in state.checkpoints)


def test_phase4_activate_main_switch_self_to_hidden_mode() -> None:
    engine = RulesEngine(
        effect_rules={
            900760: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_switch_self_to_hidden_mode",
                    "handler_params": {},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880760, card_id=900760, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True)
    state.players[1].battle_area.append(source)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    act = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    )
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].battle_area[0].hidden_mode is True
    assert any(cp.name == "effect_activate_switch_self_to_hidden_mode" for cp in state.checkpoints)


def test_phase4_activate_main_switch_all_opponent_battle_to_revealed_then_ko() -> None:
    engine = RulesEngine(
        effect_rules={
            900761: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_switch_all_opponent_battle_to_revealed_then_ko_up_to_n",
                    "handler_params": {"max_targets": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880761, card_id=900761, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True)
    state.players[1].battle_area.append(source)
    state.players[2].battle_area.extend(
        [
            CardInstance(instance_id=880762, card_id=900762, owner_id=2, card_type="BATTLE", color="Red", hidden_mode=True, power=10000),
            CardInstance(instance_id=880763, card_id=900763, owner_id=2, card_type="BATTLE", color="Blue", hidden_mode=True, power=5000),
        ]
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    act = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[2].battle_area) == 1
    assert state.players[2].battle_area[0].instance_id == 880763
    assert state.players[2].battle_area[0].hidden_mode is False
    assert any(card.instance_id == 880762 for card in state.players[2].drop)
    assert any(cp.name == "effect_activate_switch_all_opponent_battle_to_revealed_then_ko_up_to_n" for cp in state.checkpoints)


def test_phase4_revealed_switch_can_grant_keyword_to_owner_card_for_turn() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "White", "LEADER", (), (), False),
                2: ("Other Leader", "Red", "LEADER", (), (), False),
                900764: ("Switch Source", "White", "BATTLE", (), (), False),
                900765: ("Baby Target", "White", "BATTLE", ("Baby",), (), False),
            }
            name, color, card_type, traits, characters, has_auto = data.get(
                card_id,
                ("Card", "White", "BATTLE", (), (), False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                    keywords=(),
                    card_traits_json=traits,
                    card_character_json=characters,
                    has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=has_auto,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900764: [
                {
                    "trigger": "self_switched_revealed",
                    "handler_id": "auto_buff_up_to_n_owner_cards_on_switch",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "white",
                        "required_traits": "Baby",
                        "grant_keyword": "Double Strike",
                        "keyword_duration": "turn",
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880764, card_id=900764, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True)
    target = CardInstance(instance_id=880765, card_id=900765, owner_id=1, card_type="BATTLE", color="White")
    state.players[1].battle_area.extend([source, target])
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    source.hidden_mode = False
    engine._emit_effect_event(
        state,
        name="card_switched_revealed_mode",
        actor_player_id=1,
        payload={"source_instance_id": source.instance_id, "source_card_id": source.card_id, "source_zone": "battle", "owner_player_id": 1},
    )
    engine._resolve_pending_effects(state)
    assert "Double Strike" in state.players[1].battle_area[1].temporary_keywords
    assert any(cp.name == "effect_auto_buff_up_to_n_owner_cards_on_switch" for cp in state.checkpoints)


def test_phase4_activate_main_hidden_mode_cost_can_send_opponent_battle_to_warp() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "White", 0, "LEADER", "[]", "[]", False, False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False),
                900750: ("Hidden Warper", "White", 2, "BATTLE", "[]", "[]", True, False),
                900751: ("White Ally", "White", 2, "BATTLE", "[]", "[]", False, False),
                900752: ("Target", "Red", 3, "BATTLE", "[]", "[]", False, False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_auto = data.get(
                card_id,
                ("Card", "White", 0, "BATTLE", "[]", "[]", False, False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=has_auto,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        skill_cost_rules={
            900750: {
                "activate_main": [
                    {"kind": "switch_owner_battle_to_hidden", "amount": 1, "allowed_colors": "white"}
                ]
            }
        },
        effect_rules={
            900750: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_send_up_to_n_opponent_battle_to_warp",
                    "handler_params": {"max_targets": 1},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=880750, card_id=900750, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True),
            CardInstance(instance_id=880751, card_id=900751, owner_id=1, card_type="BATTLE", color="White"),
        ]
    )
    state.players[2].battle_area.append(CardInstance(instance_id=880752, card_id=900752, owner_id=2, card_type="BATTLE", color="Red"))
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    assert state.players[1].battle_area[1].hidden_mode is True
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert all(card.instance_id != 880752 for card in state.players[2].battle_area)
    assert any(card.instance_id == 880752 for card in state.players[2].warp)
    assert any(cp.name == "effect_activate_send_up_to_n_opponent_battle_to_warp" for cp in state.checkpoints)


def test_phase4_leader_activate_main_can_look_top_and_send_matching_card_to_owner_warp() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "Black", 0, "LEADER", "[]", "[\"Goku Black\"]", True),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False),
                900770: ("Black Battle", "Black", 2, "BATTLE", "[]", "[]", False),
                900771: ("Red Battle", "Red", 2, "BATTLE", "[]", "[]", False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main = data.get(
                card_id,
                ("Card", "Black", 0, "BATTLE", "[]", "[]", False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            1: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_look_top_send_up_to_n_to_owner_warp",
                    "handler_params": {"look_count": 7, "max_send": 1, "allowed_colors": "black"},
                    "once_per_turn": True,
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.has_activate_main = True
    state.players[1].deck = [
        CardInstance(instance_id=880770, card_id=900771, owner_id=1, card_type="BATTLE", color="Red"),
        CardInstance(instance_id=880771, card_id=900770, owner_id=1, card_type="BATTLE", color="Black"),
        *state.players[1].deck,
    ]
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "leader"
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(card.card_id == 900770 for card in state.players[1].warp)
    assert all(card.card_id != 900771 for card in state.players[1].warp)
    assert any(cp.name == "effect_activate_look_top_send_up_to_n_to_owner_warp" for cp in state.checkpoints)


def test_phase4_unison_activate_main_can_send_top_deck_to_owner_warp_and_switch_self_active() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "Black", 0, "LEADER", "[]", "[]", False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False),
                900772: ("Warping Unison", "Black", 3, "UNISON", "[]", "[]", True),
                900773: ("Deck A", "Black", 1, "BATTLE", "[]", "[]", False),
                900774: ("Deck B", "Black", 1, "BATTLE", "[]", "[]", False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main = data.get(
                card_id,
                ("Card", "Black", 0, "BATTLE", "[]", "[]", False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900772: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_send_top_deck_to_owner_warp",
                    "handler_params": {"send_count": 2, "switch_self_active": True, "marker_delta": 1},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].unison_area.append(
        CardInstance(
            instance_id=880772,
            card_id=900772,
            owner_id=1,
            card_type="UNISON",
            color="Black",
            has_activate_main=True,
            markers=2,
            resting=True,
        )
    )
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=state.players[1].unison_area[0])
    state.players[1].deck = [
        CardInstance(instance_id=880773, card_id=900773, owner_id=1, card_type="BATTLE", color="Black"),
        CardInstance(instance_id=880774, card_id=900774, owner_id=1, card_type="BATTLE", color="Black"),
        *state.players[1].deck,
    ]
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    source = state.players[1].unison_area[0]
    assert source.resting is False
    assert source.markers == 3
    assert [card.card_id for card in state.players[1].warp][-2:] == [900773, 900774]
    assert any(cp.name == "effect_activate_send_top_deck_to_owner_warp" for cp in state.checkpoints)


def test_phase4_owner_opponent_battle_attack_can_pay_life_bottom_deck_and_play_self_from_drop_to_negate() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Black Leader", "Black", 0, "LEADER", "[]", "[]", False, False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False),
                900780: ("Reactive Gohan", "Black", 3, "BATTLE", "[]", "[]", False, True),
                900781: ("Attacker", "Red", 2, "BATTLE", "[]", "[]", False, False),
                900782: ("Hand Card", "Black", 1, "BATTLE", "[]", "[]", False, False),
                900783: ("Life Card", "Black", 1, "BATTLE", "[]", "[]", False, False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_auto = data.get(
                card_id,
                ("Card", "Black", 0, "BATTLE", "[]", "[]", False, False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=has_auto,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900780: [
                {
                    "trigger": "owner_opponent_battle_attacks",
                    "handler_id": "auto_pay_life_bottom_deck_play_self_from_drop_or_warp_negate_attack",
                    "handler_params": {
                        "life_to_hand": 1,
                        "bottom_deck_from_hand": 1,
                        "max_owner_life": 4,
                        "resting": True,
                        "negate_attack": True,
                        "requires_leader": "if your leader is black",
                    },
                    "limit_per_turn": 1,
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)
    reactive = CardInstance(instance_id=880780, card_id=900780, owner_id=1, card_type="BATTLE", color="Black", has_auto=True)
    state.players[1].drop.append(reactive)
    engine._register_card_effects(state, player_id=1, source_zone="drop", card=reactive)
    state.players[1].life = [
        CardInstance(instance_id=880783, card_id=900783, owner_id=1, card_type="BATTLE", color="Black"),
        CardInstance(instance_id=880784, card_id=900783, owner_id=1, card_type="BATTLE", color="Black"),
        CardInstance(instance_id=880785, card_id=900783, owner_id=1, card_type="BATTLE", color="Black"),
        CardInstance(instance_id=880786, card_id=900783, owner_id=1, card_type="BATTLE", color="Black"),
    ]
    state.players[1].hand = [
        CardInstance(instance_id=880782, card_id=900782, owner_id=1, card_type="BATTLE", color="Black")
    ]
    state.players[2].battle_area.append(
        CardInstance(instance_id=880781, card_id=900781, owner_id=2, card_type="BATTLE", color="Red", power=15000)
    )

    attack = next(
        a
        for a in engine.get_legal_actions(state, 2)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    assert state.attack_context is None
    assert state.counter_window is None
    assert len(state.players[1].life) == 3
    assert len(state.players[1].hand) == 1
    assert state.players[1].deck[-1] == 900782
    played = next(card for card in state.players[1].battle_area if card.instance_id == 880780)
    assert played.resting is True
    assert all(card.instance_id != 880780 for card in state.players[1].drop)
    assert any(cp.name == "effect_auto_pay_life_bottom_deck_play_self_from_drop_or_warp_negate_attack" for cp in state.checkpoints)


def test_phase4_unison_activate_main_can_send_opponent_drop_battle_to_warp() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "Yellow", 0, "LEADER", "[]", "[]", False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False),
                900790: ("Piccolo Unison", "Yellow", 3, "UNISON", "[]", "[]", True),
                900791: ("Drop Battle A", "Red", 2, "BATTLE", "[]", "[]", False),
                900792: ("Drop Battle B", "Blue", 2, "BATTLE", "[]", "[]", False),
                900793: ("Drop Extra", "Red", 1, "EXTRA", "[]", "[]", False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main = data.get(
                card_id,
                ("Card", "Yellow", 0, "BATTLE", "[]", "[]", False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900790: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_send_up_to_n_opponent_drop_battle_to_warp",
                    "handler_params": {"max_targets": 2, "marker_delta": -3},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].unison_area.append(
        CardInstance(
            instance_id=880790,
            card_id=900790,
            owner_id=1,
            card_type="UNISON",
            color="Yellow",
            has_activate_main=True,
            markers=4,
        )
    )
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=state.players[1].unison_area[0])
    state.players[2].drop.extend(
        [
            CardInstance(instance_id=880791, card_id=900791, owner_id=2, card_type="BATTLE", color="Red"),
            CardInstance(instance_id=880792, card_id=900792, owner_id=2, card_type="BATTLE", color="Blue"),
            CardInstance(instance_id=880793, card_id=900793, owner_id=2, card_type="EXTRA", color="Red"),
        ]
    )
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    source = state.players[1].unison_area[0]
    assert source.markers == 1
    assert [card.card_id for card in state.players[2].warp][-2:] == [900791, 900792]
    assert any(card.instance_id == 880793 for card in state.players[2].drop)
    assert any(cp.name == "effect_activate_send_up_to_n_opponent_drop_battle_to_warp" for cp in state.checkpoints)


def test_phase4_activate_main_gain_power_by_hidden_cost_target_original_power_for_turn() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "White", 0, "LEADER", "[]", "[]", False, False, 10000),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False, 10000),
                900760: ("Power Copier", "White", 2, "BATTLE", "[]", "[]", True, False, 15000),
                900761: ("White Ally", "White", 2, "BATTLE", "[]", "[]", False, False, 20000),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_auto, power = data.get(
                card_id,
                ("Card", "White", 0, "BATTLE", "[]", "[]", False, False, 15000),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=power,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=has_auto,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        skill_cost_rules={
            900760: {
                "activate_main": [
                    {"kind": "switch_owner_battle_to_hidden", "amount": 1, "allowed_colors": "white"}
                ]
            }
        },
        effect_rules={
            900760: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_gain_power_by_hidden_cost_target_original_power_for_turn",
                    "handler_params": {"target_scope": "self"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=880760, card_id=900760, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True, power=15000),
            CardInstance(instance_id=880761, card_id=900761, owner_id=1, card_type="BATTLE", color="White", power=20000),
        ]
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    assert state.players[1].battle_area[1].hidden_mode is True
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].battle_area[0].power == 35000
    assert state.players[1].battle_area[0].temporary_power_delta == 20000
    assert any(cp.name == "effect_activate_gain_power_by_hidden_cost_target_original_power_for_turn" for cp in state.checkpoints)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert state.players[1].battle_area[0].power == 15000
    assert state.players[1].battle_area[0].temporary_power_delta == 0


def test_phase4_activate_battle_hidden_mode_cost_can_gain_power_and_keyword_for_battle() -> None:
    engine = RulesEngine(
        skill_cost_rules={
            900765: {
                "activate_battle": [
                    {"kind": "switch_owner_battle_to_hidden", "amount": 1, "allowed_colors": "white"}
                ]
            }
        },
        effect_rules={
            900765: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "activate_gain_power_and_keyword_for_battle",
                    "handler_params": {"power_delta": 10000, "grant_keyword": "Double Strike"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.extend(
        [
            CardInstance(
                instance_id=880765,
                card_id=900765,
                owner_id=1,
                card_type="BATTLE",
                color="White",
                power=15000,
                has_activate_battle=True,
                activate_limit_once_per_turn=True,
                skill_text_raw=(
                    "[Activate: Battle][Once per turn](1), choose 1 white card in your Battle Area and switch it to Hidden Mode: "
                    "This card gets +10000 power and [Double Strike] for the battle."
                ),
            ),
            CardInstance(instance_id=880766, card_id=900766, owner_id=1, card_type="BATTLE", color="White", power=5000),
        ]
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    assert state.players[1].battle_area[1].hidden_mode is True
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    attacker = state.players[1].battle_area[0]
    assert attacker.power == 25000
    assert attacker.battle_temporary_power_delta == 10000
    assert "Double Strike" in attacker.battle_temporary_keywords
    assert any(cp.name == "effect_activate_gain_power_and_keyword_for_battle" for cp in state.checkpoints)
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    attacker = state.players[1].battle_area[0]
    assert attacker.power == 25000
    assert "Double Strike" in attacker.battle_temporary_keywords
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    attacker = state.players[1].battle_area[0]
    assert attacker.power == 15000
    assert attacker.battle_temporary_power_delta == 0
    assert "Double Strike" not in attacker.battle_temporary_keywords
    assert any(cp.name == "battle_modifiers_cleared" for cp in state.checkpoints)


def test_phase4_activate_battle_can_buff_owner_leader_for_battle() -> None:
    engine = RulesEngine(
        effect_rules={
            900786: [
                {
                    "trigger": "self_activate_extra_from_hand",
                    "handler_id": "activate_gain_power_and_keyword_for_battle",
                    "handler_params": {
                        "power_delta": 15000,
                        "grant_keyword": "Double Strike",
                        "target_scope": "owner_leader",
                        "requires_leader": "black",
                        "required_leader_traits": "Saiyan",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].leader_area.color = "Black"
    state.players[1].leader_area.traits = ("Saiyan",)
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="Leader", card_type="LEADER", color="Black", traits=("Saiyan",))
    state.players[1].hand = [
        CardInstance(
            instance_id=880790,
            card_id=900786,
            owner_id=1,
            card_type="EXTRA",
            color="Black",
            energy_cost=0,
            has_activate_battle=True,
            skill_text_raw=(
                "[Activate: Battle] If your Leader Card is a black ≪Saiyan≫ card, "
                "it gets +15000 power and [Double Strike] for the duration of the battle."
            ),
        )
    ]
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader" and a.target_zone == "leader"
    )
    leader_base_power = state.players[1].leader_area.power
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, action)
    leader = state.players[1].leader_area
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    leader = state.players[1].leader_area
    assert leader.power == leader_base_power + 15000
    assert leader.battle_temporary_power_delta == 15000
    assert "Double Strike" in leader.battle_temporary_keywords
    assert any(cp.name == "effect_activate_gain_power_and_keyword_for_battle" for cp in state.checkpoints)
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    leader = state.players[1].leader_area
    assert leader.power == leader_base_power
    assert leader.battle_temporary_power_delta == 0
    assert "Double Strike" not in leader.battle_temporary_keywords


def test_phase4_activate_battle_can_buff_matching_owner_cards_with_energy_drop_cost() -> None:
    engine = RulesEngine(
        skill_cost_rules={
            900787: {
                "activate_battle": [
                    {"kind": "send_owner_energy_to_drop", "amount": 1}
                ]
            }
        },
        effect_rules={
            900787: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "activate_gain_power_and_keyword_for_battle",
                    "handler_params": {
                        "power_delta": 10000,
                        "max_targets": 1,
                        "target_scope": "owner_cards",
                        "allowed_colors": "blue",
                        "required_traits": "Android",
                    },
                    "once_per_turn": True,
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].leader_area.color = "Blue"
    state.players[1].leader_area.traits = ("Android",)
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="Leader", card_type="LEADER", color="Blue", traits=("Android",))
    state.players[1].energy = [
        CardInstance(instance_id=880795, card_id=401, owner_id=1, card_type="ENERGY", color="Blue"),
    ]
    state.players[1].battle_area = [
        CardInstance(
            instance_id=880796,
            card_id=900787,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=15000,
            has_activate_battle=True,
            activate_limit_once_per_turn=True,
            traits=("Red Ribbon Army",),
            skill_text_raw=(
                "[Activate: Battle][Once per turn] Place 1 of your energy into its owner's Drop: "
                "Choose up to 1 of your blue â‰ªAndroidâ‰« cards and it gets +10000 power for the battle."
            ),
        ),
        CardInstance(
            instance_id=880797,
            card_id=900788,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            power=12000,
            resting=False,
            traits=("Android",),
        ),
    ]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    assert len(state.players[1].energy) == 0
    assert len(state.players[1].drop) == 1
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    leader = state.players[1].leader_area
    assert leader.battle_temporary_power_delta == 10000
    assert any(cp.name == "effect_activate_gain_power_and_keyword_for_battle" for cp in state.checkpoints)


def test_phase4_activate_battle_drop_hidden_mode_cost_can_ko_opponent_battle() -> None:
    engine = RulesEngine(
        skill_cost_rules={
            900767: {
                "activate_battle": [
                    {"kind": "send_owner_hidden_mode_battle_to_drop", "amount": 1}
                ]
            }
        },
        effect_rules={
            900767: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "activate_ko_up_to_n_opponent_battle",
                    "handler_params": {"max_targets": 1, "target_policy": "first"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.extend(
        [
            CardInstance(
                instance_id=880767,
                card_id=900767,
                owner_id=1,
                card_type="BATTLE",
                color="White",
                power=15000,
                has_activate_battle=True,
                activate_limit_once_per_turn=True,
                skill_text_raw=(
                    "[Activate: Battle][Limit 1] Choose 1 Hidden Mode card in your Battle Area and place it into its owner's Drop: "
                    "Choose up to 1 of your opponent's Battle Cards and KO it."
                ),
            ),
            CardInstance(instance_id=880768, card_id=900768, owner_id=1, card_type="BATTLE", color="White", power=5000, hidden_mode=True),
        ]
    )
    state.players[2].battle_area.append(
        CardInstance(instance_id=880769, card_id=900769, owner_id=2, card_type="BATTLE", color="Red", power=15000)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    assert all(card.instance_id != 880768 for card in state.players[1].battle_area)
    assert any(card.instance_id == 880768 for card in state.players[1].drop)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert all(card.instance_id != 880769 for card in state.players[2].battle_area)
    assert any(card.instance_id == 880769 for card in state.players[2].drop)
    assert any(cp.name == "effect_activate_ko_up_to_n_opponent_battle" for cp in state.checkpoints)


def test_phase4_activate_main_can_draw_play_self_and_gain_keyword_until_opponent_turn_end() -> None:
    engine = RulesEngine(
        effect_rules={
            900780: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_draw_n_play_self_from_hand_and_gain_keyword_until_opponent_turn_end",
                    "handler_params": {
                        "amount": 1,
                        "grant_keyword": "Barrier",
                        "min_owner_hidden_mode_battle": 2,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880781, card_id=901001, owner_id=1, card_type="BATTLE", color="White", resting=False),
        CardInstance(instance_id=880782, card_id=901002, owner_id=1, card_type="BATTLE", color="White", resting=False),
    ]
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=880783, card_id=901003, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True),
            CardInstance(instance_id=880784, card_id=901004, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True),
        ]
    )
    state.players[1].hand = [
        CardInstance(
            instance_id=880780,
            card_id=900780,
            owner_id=1,
            card_type="BATTLE",
            color="White",
            energy_cost=2,
            power=20000,
            has_activate_main=True,
            skill_text_raw=(
                "[Activate: Main]{w}(2), if you have 2 or more Hidden Mode cards in your Battle Area: "
                "Draw 1 card, play this card from your hand, and this card gains [Barrier] until the end of your opponent's turn."
            ),
        )
    ]
    legal = engine.get_legal_actions(state, 1)
    assert any(a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand" for a in legal)
    state.players[1].battle_area.pop()
    legal = engine.get_legal_actions(state, 1)
    assert all(not (a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand") for a in legal)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880784, card_id=901004, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True)
    )
    action = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand"
    )
    deck_before = len(state.players[1].deck)
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].deck) == deck_before - 1
    assert state.counter_window is not None and state.counter_window.kind == "play"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    played = next(card for card in state.players[1].battle_area if card.instance_id == 880780)
    assert "Barrier" in played.delayed_temporary_keywords
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))
    still_played = next(card for card in state.players[1].battle_area if card.instance_id == 880780)
    assert "Barrier" in still_played.delayed_temporary_keywords
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    expired = next(card for card in state.players[1].battle_area if card.instance_id == 880780)
    assert "Barrier" not in expired.delayed_temporary_keywords
    assert any(cp.name == "delayed_keyword_clear_resolved" for cp in state.checkpoints)


def test_phase4_activate_main_can_grant_keyword_to_all_matching_owner_battles_until_opponent_turn_end() -> None:
    engine = RulesEngine(
        effect_rules={
            900785: [
                {
                    "trigger": "self_activate_extra_from_hand",
                    "handler_id": "activate_buff_owner_battle_cards",
                    "handler_params": {
                        "target_policy": "all",
                        "target_scope": "owner_battle",
                        "grant_keyword": "Barrier",
                        "keyword_duration": "opponent_turn",
                        "allowed_colors": "red",
                        "required_traits": "Saiyan",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880791, card_id=901011, owner_id=1, card_type="ENERGY", color="Red", resting=False),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=880785,
            card_id=900785,
            owner_id=1,
            card_type="EXTRA",
            color="Red",
            energy_cost=1,
            has_activate_main=True,
            skill_text_raw=(
                "[Activate: Main] Choose all red ≪Saiyan≫ cards in your Battle Area. "
                "They gain [Barrier] until the end of your opponent's next turn."
            ),
        )
    ]
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=880786, card_id=901012, owner_id=1, card_type="BATTLE", color="Red", traits=("Saiyan",)),
            CardInstance(instance_id=880787, card_id=901013, owner_id=1, card_type="BATTLE", color="Red", traits=("Saiyan",)),
            CardInstance(instance_id=880788, card_id=901014, owner_id=1, card_type="BATTLE", color="Blue", traits=("Saiyan",)),
            CardInstance(instance_id=880789, card_id=901015, owner_id=1, card_type="BATTLE", color="Red", traits=("Earthling",)),
        ]
    )
    engine._card_cache[(901012, "front")] = CardRuntimeData(card_name="Red Saiyan A", card_type="BATTLE", color="Red", traits=("Saiyan",))
    engine._card_cache[(901013, "front")] = CardRuntimeData(card_name="Red Saiyan B", card_type="BATTLE", color="Red", traits=("Saiyan",))
    engine._card_cache[(901014, "front")] = CardRuntimeData(card_name="Blue Saiyan", card_type="BATTLE", color="Blue", traits=("Saiyan",))
    engine._card_cache[(901015, "front")] = CardRuntimeData(card_name="Red Earthling", card_type="BATTLE", color="Red", traits=("Earthling",))
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert "Barrier" in next(card for card in state.players[1].battle_area if card.instance_id == 880786).delayed_temporary_keywords
    assert "Barrier" in next(card for card in state.players[1].battle_area if card.instance_id == 880787).delayed_temporary_keywords
    assert "Barrier" not in next(card for card in state.players[1].battle_area if card.instance_id == 880788).delayed_temporary_keywords
    assert "Barrier" not in next(card for card in state.players[1].battle_area if card.instance_id == 880789).delayed_temporary_keywords
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))
    assert "Barrier" in next(card for card in state.players[1].battle_area if card.instance_id == 880786).delayed_temporary_keywords
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    assert "Barrier" not in next(card for card in state.players[1].battle_area if card.instance_id == 880786).delayed_temporary_keywords
    assert any(cp.name == "effect_activate_buff_owner_battle_cards" for cp in state.checkpoints)


def test_phase4_activate_battle_can_buff_matching_owner_cards_for_turn_with_energy_drop_cost() -> None:
    engine = RulesEngine(
        effect_rules={
            901200: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "activate_buff_owner_battle_cards",
                    "handler_params": {
                        "target_policy": "first",
                        "target_scope": "owner_cards",
                        "max_targets": 1,
                        "power_delta": 5000,
                        "allowed_colors": "blue",
                        "required_traits": "Red Ribbon Army",
                    },
                }
            ]
        },
        skill_cost_rules={
            901200: {
                "activate_battle": [
                    {"kind": "send_owner_energy_to_drop", "amount": 1}
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    source = CardInstance(
        instance_id=901201,
        card_id=901200,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        power=20000,
        has_activate_battle=True,
    )
    target = CardInstance(
        instance_id=901202,
        card_id=901201,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        power=15000,
        traits=("Red Ribbon Army",),
    )
    state.players[1].battle_area = [source, target]
    state.players[1].energy = [
        CardInstance(instance_id=901203, card_id=901202, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]
    engine._card_cache[(901201, "front")] = CardRuntimeData(card_name="Target", card_type="BATTLE", color="Blue", traits=("Red Ribbon Army",))
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="leader",
        attacker_instance_id=state.players[1].leader_area.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.OFFENSE

    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    assert len(state.players[1].energy) == 0
    assert len(state.players[1].drop) == 1
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert next(card for card in state.players[1].battle_area if card.instance_id == 901202).temporary_power_delta == 5000
    assert any(cp.name == "effect_activate_buff_owner_battle_cards" for cp in state.checkpoints)


def test_phase4_scheme_wish_minus_seven_grants_indestructible_and_restricts_copies_next_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            7910: (
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_buff_owner_battle_cards",
                    handler_params={
                        "target_scope": "owner_battle",
                        "max_targets": 1,
                        "grant_keyword": "Indestructible",
                        "keyword_duration": "opponent_turn",
                        "restrict_activate_self_copies_next_turn": True,
                    },
                    family_id="self_activate_main:activate_buff_owner_battle_cards",
                    provenance="test",
                ),
            )
        },
        skill_cost_rules={7910: {"activate_main_unison": [{"kind": "remove_owner_unison_markers", "amount": 7}]}},
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=991420,
        card_id=7910,
        owner_id=1,
        card_type="UNISON",
        color="Black",
        markers=8,
        has_activate_main=True,
        skill_text_raw=(
            "[-7][Activate: Main] Choose up to 1 of your Battle Cards and it gains [Indestructible] until the end of your opponent's turn. "
            "You can't activate skills on copies of this card during your next turn."
        ),
    )
    copy_in_hand = CardInstance(
        instance_id=991421,
        card_id=7910,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        energy_cost=0,
        has_activate_main=True,
        skill_text_raw="[Activate: Main] Test copy skill.",
    )
    target = CardInstance(instance_id=991422, card_id=991422, owner_id=1, card_type="BATTLE", color="Black", power=20000)
    state.players[1].unison_area = [source]
    state.players[1].hand = [copy_in_hand]
    state.players[1].battle_area = [target]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison")
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    target = next(card for card in state.players[1].battle_area if card.instance_id == 991422)
    source = next(card for card in state.players[1].unison_area if card.instance_id == 991420)
    assert source.markers == 1
    assert "Indestructible" in target.delayed_temporary_keywords
    assert any(cp.name == "effect_activate_buff_owner_battle_cards" for cp in state.checkpoints)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    target = next(card for card in state.players[1].battle_area if card.instance_id == 991422)
    assert "Indestructible" in target.delayed_temporary_keywords
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    assert any(cp.name == "scheduled_activate_skill_restrictions_activated" for cp in state.checkpoints)
    state = _to_main(engine, state)

    legal = engine.get_legal_actions(state, 1)
    assert not any(
        a.action_type == ActionType.ACTIVATE_MAIN_SKILL
        and (
            (a.source_zone == "hand" and state.players[1].hand[a.source_index].card_id == 7910)
            or (a.source_zone == "unison" and state.players[1].unison_area[a.source_index].card_id == 7910)
        )
        for a in legal
    )
    target = next(card for card in state.players[1].battle_area if card.instance_id == 991422)
    assert "Indestructible" not in target.delayed_temporary_keywords


def test_phase4_next_turn_activate_copy_restriction_is_specific_to_matching_activate_line() -> None:
    engine = RulesEngine(
        effect_rules={
            999013: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_buff_owner_battle_cards",
                    "handler_params": {
                        "target_policy": "first",
                        "target_scope": "owner_battle",
                        "max_targets": 1,
                        "grant_keyword": "Indestructible",
                        "keyword_duration": "opponent_turn_end",
                        "restrict_activate_self_copies_next_turn": True,
                    },
                },
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_switch_self_active_and_gain_power_for_turn",
                    "handler_params": {"power_delta": 5000},
                },
            ]
        },
        skill_cost_rules={999013: {"activate_main_unison": [{"kind": "remove_owner_unison_markers", "amount": 1}]}},
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=9990131,
        card_id=999013,
        owner_id=1,
        card_type="UNISON",
        color="Black",
        markers=3,
        has_activate_main=True,
        skill_text_raw=(
            "[-1][Activate: Main] Choose up to 1 of your Battle Cards and it gains [Indestructible] until the end of your opponent's turn. "
            "You can't activate skills on copies of this card during your next turn.\n"
            "[Activate: Main] Switch this card to Active Mode and it gets +5000 power for the turn."
        ),
    )
    target = CardInstance(instance_id=9990132, card_id=9990132, owner_id=1, card_type="BATTLE", color="Black", power=15000)
    state.players[1].unison_area = [source]
    state.players[1].battle_area = [target]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)

    restrict_reg = next(
        reg
        for reg in state.effect_registry
        if reg.source_instance_id == 9990131 and reg.handler_id == "activate_buff_owner_battle_cards"
    )
    other_reg = next(
        reg
        for reg in state.effect_registry
        if reg.source_instance_id == 9990131 and reg.handler_id == "activate_switch_self_active_and_gain_power_for_turn"
    )
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL
        and a.source_zone == "unison"
        and int(a.effect_choice or -1) == int(restrict_reg.effect_id)
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(
        int(row.restricted_card_id) == 999013
        and str(row.trigger) == "self_activate_main"
        and str(row.handler_id) == "activate_buff_owner_battle_cards"
        for row in state.scheduled_activate_skill_restrictions
    )

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    state = _to_main(engine, state)

    legal = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison"
    ]
    assert not any(int(a.effect_choice or -1) == int(restrict_reg.effect_id) for a in legal)
    assert legal
    matching_after = engine._public_activate_matching_registrations(
        state,
        player_id=1,
        source=state.players[1].unison_area[0],
        source_zone="unison",
        source_kind="main",
    )
    assert [reg.handler_id for reg in matching_after] == ["activate_switch_self_active_and_gain_power_for_turn"]


def test_phase4_activate_copy_lock_for_turn_blocks_matching_copies_and_expires() -> None:
    engine = RulesEngine(
        effect_rules={
            999015: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_switch_self_active_and_gain_power_for_turn",
                    "handler_params": {"power_delta": 5000},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    first = CardInstance(
        instance_id=9990151,
        card_id=999015,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_activate_main=True,
        skill_text_raw=(
            "[Activate: Main] Switch this card to Active Mode and it gets +5000 power for the turn. "
            "You can't activate the [Activate: Main] skill on copies of this card for the turn."
        ),
    )
    second = CardInstance(
        instance_id=9990152,
        card_id=999015,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_activate_main=True,
        skill_text_raw=(
            "[Activate: Main] Switch this card to Active Mode and it gets +5000 power for the turn. "
            "You can't activate the [Activate: Main] skill on copies of this card for the turn."
        ),
    )
    state.players[1].battle_area = [first, second]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=first)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=second)

    legal_before = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    ]
    assert len(legal_before) == 2

    state = engine.apply_action(state, legal_before[0])
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(cp.name == "effect_activate_copies_restricted_for_turn" for cp in state.checkpoints)

    legal_same_turn = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL
        and a.source_zone == "battle"
        and state.players[1].battle_area[a.source_index].card_id == 999015
    ]
    assert not legal_same_turn

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    state = _to_main(engine, state)

    legal_next_turn = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL
        and a.source_zone == "battle"
        and state.players[1].battle_area[a.source_index].card_id == 999015
    ]
    assert len(legal_next_turn) == 2


def test_phase4_activate_copy_lock_for_game_blocks_matching_copies_across_turns() -> None:
    engine = RulesEngine(
        effect_rules={
            999016: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_switch_self_active_and_gain_power_for_turn",
                    "handler_params": {"power_delta": 5000},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    first = CardInstance(
        instance_id=9990161,
        card_id=999016,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_activate_main=True,
        skill_text_raw=(
            "[Activate: Main] Switch this card to Active Mode and it gets +5000 power for the turn. "
            "You can't activate copies of this card for the game."
        ),
    )
    second = CardInstance(
        instance_id=9990162,
        card_id=999016,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_activate_main=True,
        skill_text_raw=(
            "[Activate: Main] Switch this card to Active Mode and it gets +5000 power for the turn. "
            "You can't activate copies of this card for the game."
        ),
    )
    state.players[1].battle_area = [first, second]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=first)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=second)

    legal_before = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    ]
    assert len(legal_before) == 2

    state = engine.apply_action(state, legal_before[0])
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(cp.name == "effect_activate_copies_restricted_for_game" for cp in state.checkpoints)
    assert len(state.permanent_skill_activation_restrictions) == 1

    legal_same_turn = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL
        and a.source_zone == "battle"
        and state.players[1].battle_area[a.source_index].card_id == 999016
    ]
    assert not legal_same_turn

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    state = _to_main(engine, state)

    legal_next_turn = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL
        and a.source_zone == "battle"
        and state.players[1].battle_area[a.source_index].card_id == 999016
    ]
    assert not legal_next_turn


def test_phase4_generic_all_skill_copy_lock_for_game_blocks_auto_and_activate_copies() -> None:
    def _mark_auto(state, event, reg):
        state.log.append(f"auto_mark:{reg.source_instance_id}")

    engine = RulesEngine(
        effect_handlers={"mark_auto": _mark_auto},
        effect_rules={
            999017: (
                EffectRule(
                    trigger="owner_leader_attacks",
                    handler_id="mark_auto",
                    handler_params={},
                    family_id="owner_leader_attacks:mark_auto",
                    provenance="test",
                    source_text="[Auto] When your Leader Card attacks, draw 1 card.",
                ),
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_switch_self_active_and_gain_power_for_turn",
                    handler_params={"power_delta": 5000},
                    family_id="self_activate_main:activate_switch_self_active_and_gain_power_for_turn",
                    provenance="test",
                    source_text=(
                        "[Activate: Main] Switch this card to Active Mode and it gets +5000 power for the turn. "
                        "You can't activate skills on copies of this card for the game."
                    ),
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    first = CardInstance(
        instance_id=9990171,
        card_id=999017,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_auto=True,
        has_activate_main=True,
        skill_text_raw="[Auto][Activate: Main] Mixed skills test card.",
    )
    second = CardInstance(
        instance_id=9990172,
        card_id=999017,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_auto=True,
        has_activate_main=True,
        skill_text_raw="[Auto][Activate: Main] Mixed skills test card.",
    )
    state.players[1].battle_area = [first, second]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=first)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=second)

    legal_before = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    ]
    assert len(legal_before) == 2

    state = engine.apply_action(state, legal_before[0])
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(cp.name == "effect_all_skill_copies_restricted_for_game" for cp in state.checkpoints)
    assert len(state.permanent_skill_activation_restrictions) == 1

    legal_after_activate = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL
        and a.source_zone == "battle"
        and state.players[1].battle_area[a.source_index].card_id == 999017
    ]
    assert not legal_after_activate

    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={
            "attacker_instance_id": state.players[1].leader_area.instance_id,
            "attacker_zone": "leader",
            "target_player_id": 2,
            "target_zone": "leader",
        },
    )
    engine._resolve_pending_effects(state)

    assert not [row for row in state.log if row.startswith("auto_mark:")]
    blocked = [row for row in state.effect_resolutions if row.reason == "permanent_skill_activation_restricted"]
    assert blocked
    assert any(cp.name == "effect_permanent_skill_activation_restricted" for cp in state.checkpoints)


def test_phase4_generic_all_skill_copy_lock_for_turn_blocks_auto_and_activate_copies_then_expires() -> None:
    def _mark_auto(state, event, reg):
        state.log.append(f"auto_mark_turn:{reg.source_instance_id}")

    engine = RulesEngine(
        effect_handlers={"mark_auto": _mark_auto},
        effect_rules={
            999018: (
                EffectRule(
                    trigger="owner_leader_attacks",
                    handler_id="mark_auto",
                    handler_params={},
                    family_id="owner_leader_attacks:mark_auto",
                    provenance="test",
                    source_text="[Auto] When your Leader Card attacks, draw 1 card.",
                ),
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_switch_self_active_and_gain_power_for_turn",
                    handler_params={"power_delta": 5000},
                    family_id="self_activate_main:activate_switch_self_active_and_gain_power_for_turn",
                    provenance="test",
                    source_text=(
                        "[Activate: Main] Switch this card to Active Mode and it gets +5000 power for the turn. "
                        "You can't activate skills on copies of this card for the turn."
                    ),
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    first = CardInstance(
        instance_id=9990181,
        card_id=999018,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_auto=True,
        has_activate_main=True,
        skill_text_raw="[Auto][Activate: Main] Mixed skills turn test card.",
    )
    second = CardInstance(
        instance_id=9990182,
        card_id=999018,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_auto=True,
        has_activate_main=True,
        skill_text_raw="[Auto][Activate: Main] Mixed skills turn test card.",
    )
    state.players[1].battle_area = [first, second]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=first)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=second)

    legal_before = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    ]
    assert len(legal_before) == 2

    state = engine.apply_action(state, legal_before[0])
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(cp.name == "effect_all_skill_copies_restricted_for_turn" for cp in state.checkpoints)
    assert len(state.active_temporary_skill_activation_restrictions) == 1

    legal_same_turn = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL
        and a.source_zone == "battle"
        and state.players[1].battle_area[a.source_index].card_id == 999018
    ]
    assert not legal_same_turn

    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={
            "attacker_instance_id": state.players[1].leader_area.instance_id,
            "attacker_zone": "leader",
            "target_player_id": 2,
            "target_zone": "leader",
        },
    )
    engine._resolve_pending_effects(state)

    assert not [row for row in state.log if row.startswith("auto_mark_turn:")]
    blocked = [row for row in state.effect_resolutions if row.reason == "temporary_skill_activation_restricted"]
    assert blocked
    assert any(cp.name == "effect_temporary_skill_activation_restricted" for cp in state.checkpoints)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    state = _to_main(engine, state)

    legal_next_turn = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL
        and a.source_zone == "battle"
        and state.players[1].battle_area[a.source_index].card_id == 999018
    ]
    assert len(legal_next_turn) == 2

    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={
            "attacker_instance_id": state.players[1].leader_area.instance_id,
            "attacker_zone": "leader",
            "target_player_id": 2,
            "target_zone": "leader",
        },
    )
    engine._resolve_pending_effects(state)
    assert len([row for row in state.log if row.startswith("auto_mark_turn:")]) == 2


def test_phase4_play_copy_text_does_not_trigger_activation_copy_lock() -> None:
    def _mark_auto(state, event, reg):
        state.log.append(f"auto_mark_playcopy:{reg.source_instance_id}")

    engine = RulesEngine(
        effect_handlers={"mark_auto": _mark_auto},
        effect_rules={
            999019: (
                EffectRule(
                    trigger="owner_leader_attacks",
                    handler_id="mark_auto",
                    handler_params={},
                    family_id="owner_leader_attacks:mark_auto",
                    provenance="test",
                    source_text="[Auto] When your Leader Card attacks, draw 1 card.",
                ),
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_switch_self_active_and_gain_power_for_turn",
                    handler_params={"power_delta": 5000},
                    family_id="self_activate_main:activate_switch_self_active_and_gain_power_for_turn",
                    provenance="test",
                    source_text=(
                        "[Activate: Main] Switch this card to Active Mode and it gets +5000 power for the turn. "
                        "You can't play copies of this card for the turn."
                    ),
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    first = CardInstance(
        instance_id=9990191,
        card_id=999019,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_auto=True,
        has_activate_main=True,
        skill_text_raw="[Auto][Activate: Main] Mixed play-copy test card.",
    )
    second = CardInstance(
        instance_id=9990192,
        card_id=999019,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_auto=True,
        has_activate_main=True,
        skill_text_raw="[Auto][Activate: Main] Mixed play-copy test card.",
    )
    hand_copy = CardInstance(
        instance_id=9990193,
        card_id=999019,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        energy_cost=0,
        power=15000,
        combo_power=5000,
    )
    state.players[1].battle_area = [first, second]
    state.players[1].hand = [hand_copy]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=first)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=second)

    legal_before = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    ]
    assert len(legal_before) == 2

    state = engine.apply_action(state, legal_before[0])
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert not any(
        cp.name in {"effect_all_skill_copies_restricted_for_turn", "effect_activate_copies_restricted_for_turn"}
        for cp in state.checkpoints
    )
    assert not state.active_temporary_skill_activation_restrictions
    assert any(cp.name == "effect_play_copies_restricted_for_turn" for cp in state.checkpoints)

    legal_same_turn = [
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL
        and a.source_zone == "battle"
        and state.players[1].battle_area[a.source_index].card_id == 999019
    ]
    assert len(legal_same_turn) == 2
    assert not any(
        a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0
        for a in engine.get_legal_actions(state, 1)
    )

    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={
            "attacker_instance_id": state.players[1].leader_area.instance_id,
            "attacker_zone": "leader",
            "target_player_id": 2,
            "target_zone": "leader",
        },
    )
    engine._resolve_pending_effects(state)
    assert len([row for row in state.log if row.startswith("auto_mark_playcopy:")]) == 2


def test_phase4_combo_copy_text_restricts_same_card_combos_for_turn_and_expires() -> None:
    engine = RulesEngine(
        effect_rules={
            999022: (
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_switch_self_active_and_gain_power_for_turn",
                    handler_params={"power_delta": 5000},
                    family_id="self_activate_main:activate_switch_self_active_and_gain_power_for_turn",
                    provenance="test",
                    source_text=(
                        "[Activate: Main] Switch this card to Active Mode and it gets +5000 power for the turn. "
                        "You can't use copies of this card in a combo for the turn."
                    ),
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=9990221,
        card_id=999022,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_activate_main=True,
        skill_text_raw="[Activate: Main] Combo restriction test source.",
    )
    hand_copy = CardInstance(
        instance_id=9990222,
        card_id=999022,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        combo_cost=0,
        combo_power=5000,
    )
    state.players[1].battle_area = [source]
    state.players[1].hand = [hand_copy]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    assert engine._can_combo_card(state, 1, hand_copy)

    activate = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(cp.name == "effect_combo_copies_restricted_for_turn" for cp in state.checkpoints)
    assert not engine._can_combo_card(state, 1, hand_copy)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    state = _to_main(engine, state)

    refreshed = state.players[1].hand[0]
    assert engine._can_combo_card(state, 1, refreshed)


def test_phase4_play_copy_text_restricts_same_card_plays_for_game() -> None:
    engine = RulesEngine(
        effect_rules={
            999023: (
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_switch_self_active_and_gain_power_for_turn",
                    handler_params={"power_delta": 5000},
                    family_id="self_activate_main:activate_switch_self_active_and_gain_power_for_turn",
                    provenance="test",
                    source_text=(
                        "[Activate: Main] Switch this card to Active Mode and it gets +5000 power for the turn. "
                        "You can't play copies of this card for the game."
                    ),
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=9990231,
        card_id=999023,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_activate_main=True,
        skill_text_raw="[Activate: Main] Play-copy restriction test source.",
    )
    hand_copy = CardInstance(
        instance_id=9990232,
        card_id=999023,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        energy_cost=0,
        power=15000,
    )
    state.players[1].battle_area = [source]
    state.players[1].hand = [hand_copy]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    assert any(a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0 for a in engine.get_legal_actions(state, 1))

    activate = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(cp.name == "effect_play_copies_restricted_for_game" for cp in state.checkpoints)
    assert not any(a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0 for a in engine.get_legal_actions(state, 1))

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    state = _to_main(engine, state)

    assert not any(a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0 for a in engine.get_legal_actions(state, 1))


def test_phase4_combo_copy_text_restricts_same_card_combos_for_game() -> None:
    engine = RulesEngine(
        effect_rules={
            999024: (
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_switch_self_active_and_gain_power_for_turn",
                    handler_params={"power_delta": 5000},
                    family_id="self_activate_main:activate_switch_self_active_and_gain_power_for_turn",
                    provenance="test",
                    source_text=(
                        "[Activate: Main] Switch this card to Active Mode and it gets +5000 power for the turn. "
                        "You can't use copies of this card in a combo for the game."
                    ),
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=9990241,
        card_id=999024,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_activate_main=True,
        skill_text_raw="[Activate: Main] Combo-copy restriction test source.",
    )
    hand_copy = CardInstance(
        instance_id=9990242,
        card_id=999024,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        combo_cost=0,
        combo_power=5000,
    )
    state.players[1].battle_area = [source]
    state.players[1].hand = [hand_copy]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    assert engine._can_combo_card(state, 1, hand_copy)

    activate = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(cp.name == "effect_combo_copies_restricted_for_game" for cp in state.checkpoints)
    assert not engine._can_combo_card(state, 1, hand_copy)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    state = _to_main(engine, state)

    refreshed = state.players[1].hand[0]
    assert not engine._can_combo_card(state, 1, refreshed)


def test_phase4_scheme_wish_plus_one_exchanges_control_and_negates_skills_for_game() -> None:
    engine = RulesEngine(
        effect_rules={
            7910: (
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_exchange_control_of_battle_cards_for_game",
                    handler_params={
                        "owner_target_max_cost": 3,
                        "owner_max_targets": 1,
                        "opponent_max_targets": 1,
                        "negate_owner_target_skills_for_game": True,
                        "marker_delta": 1,
                    },
                    family_id="self_activate_main:activate_exchange_control_of_battle_cards_for_game",
                    provenance="test",
                ),
            )
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=991430,
        card_id=7910,
        owner_id=1,
        card_type="UNISON",
        color="Black",
        markers=1,
        has_activate_main=True,
        skill_text_raw=(
            "[+1][Activate: Main] Choose 1 of your Battle Cards with an energy cost of 3 or less, "
            "negate its skills for the game, and your opponent gains control of it for the game: "
            "Choose up to 1 of your opponent's Battle Cards and gain control of it."
        ),
    )
    surrendered = CardInstance(
        instance_id=991431,
        card_id=991431,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        energy_cost=3,
        power=20000,
        has_activate_main=True,
        has_auto=True,
        has_barrier=True,
        keywords=("Blocker",),
    )
    stolen = CardInstance(
        instance_id=991432,
        card_id=991432,
        owner_id=2,
        card_type="BATTLE",
        color="Blue",
        energy_cost=4,
        power=20000,
        has_activate_main=True,
        skill_text_raw="[Activate: Main] Test.",
    )
    state.players[1].unison_area = [source]
    state.players[1].battle_area = [surrendered]
    state.players[2].battle_area = [stolen]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)

    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL
        and a.source_zone == "unison"
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    source = next(card for card in state.players[1].unison_area if card.instance_id == 991430)
    assert source.markers == 2
    assert any(card.instance_id == 991432 and card.owner_id == 2 for card in state.players[1].battle_area)
    moved = next(card for card in state.players[2].battle_area if card.instance_id == 991431)
    assert moved.owner_id == 1
    assert moved.permanent_skills_negated is True
    assert moved.has_activate_main is False
    assert moved.has_auto is False
    assert moved.has_barrier is False
    assert moved.keywords == ()
    assert not any(reg.source_instance_id == 991431 for reg in state.effect_registry)
    assert any(
        a.action_type == ActionType.ACTIVATE_MAIN_SKILL
        and a.source_zone == "battle"
        and state.players[1].battle_area[a.source_index].instance_id == 991432
        for a in engine.get_legal_actions(state, 1)
    )
    assert not any(
        a.action_type == ActionType.ACTIVATE_MAIN_SKILL
        and a.source_zone == "battle"
        and state.players[2].battle_area[a.source_index].instance_id == 991431
        for a in engine.get_legal_actions(state, 2)
    )
    assert any(cp.name == "effect_activate_exchange_control_of_battle_cards_for_game" for cp in state.checkpoints)


def test_phase4_activate_main_can_play_self_with_markers_from_hand_or_warp() -> None:
    engine = RulesEngine(
        effect_rules={
            900787: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_hand",
                    "handler_params": {"markers": 2, "required_source_zone": "hand", "min_opponent_energy": 3},
                },
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_warp",
                    "handler_params": {"markers": 2, "required_source_zone": "warp", "min_opponent_energy": 3},
                },
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].energy = [
        CardInstance(instance_id=880810, card_id=901110, owner_id=2, color="Black"),
        CardInstance(instance_id=880811, card_id=901111, owner_id=2, color="Black"),
        CardInstance(instance_id=880812, card_id=901112, owner_id=2, color="Black"),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=880801, card_id=901101, owner_id=1, color="Black"),
        CardInstance(instance_id=880802, card_id=901102, owner_id=1, color="Black"),
        CardInstance(instance_id=880803, card_id=901103, owner_id=1, color="Black"),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=880804,
            card_id=900787,
            owner_id=1,
            card_type="UNISON",
            color="Black",
            energy_cost=2,
            has_activate_main=True,
        )
    ]
    hand_action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand" and a.source_index == 0
    )
    state = engine.apply_action(state, hand_action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None and state.counter_window.kind == "play"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].instance_id == 880804
    assert state.players[1].unison_area[0].markers == 2
    assert any(cp.name == "counter_timing_play_from_skill" for cp in state.checkpoints)

    state.players[1].warp = [
        CardInstance(
            instance_id=880805,
            card_id=900787,
            owner_id=1,
            card_type="UNISON",
            color="Black",
            energy_cost=2,
            has_activate_main=True,
        )
    ]
    for energy in state.players[1].energy:
        energy.resting = False
    warp_action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "warp" and a.source_index == 0
    )
    state = engine.apply_action(state, warp_action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None and state.counter_window.kind == "play"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(card.instance_id == 880805 and card.markers == 2 for card in state.players[1].unison_area)
    assert any(cp.name == "counter_timing_play_from_skill" for cp in state.checkpoints)


def test_phase4_activate_battle_from_hand_can_play_self_then_discard_opponent_hand() -> None:
    engine = RulesEngine(
        effect_rules={
            901210: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "activate_play_self_from_hand",
                    "handler_params": {
                        "opponent_discards_after_play": 1,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=901211, card_id=901310, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=901212,
            card_id=901210,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=1,
            has_activate_battle=True,
        )
    ]
    state.players[2].hand = [
        CardInstance(instance_id=901213, card_id=901311, owner_id=2, card_type="BATTLE", color="Red"),
        CardInstance(instance_id=901214, card_id=901312, owner_id=2, card_type="BATTLE", color="Red"),
    ]

    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="leader",
        attacker_instance_id=state.players[1].leader_area.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.OFFENSE

    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "hand" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None and state.counter_window.kind == "play"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(card.instance_id == 901212 for card in state.players[1].battle_area)
    assert len(state.players[2].hand) == 1
    assert len(state.players[2].drop) == 1
    assert any(cp.name == "counter_timing_play_from_skill" for cp in state.checkpoints)


def test_phase4_play_can_grant_keyword_to_owner_battles_with_min_character_count_until_opponent_turn_end() -> None:
    engine = RulesEngine(
        effect_rules={
            901220: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_buff_up_to_n_owner_battles_on_play",
                    "handler_params": {
                        "max_targets": 2,
                        "min_character_count": 2,
                        "required_characters": "SH",
                        "grant_keyword": "Barrier",
                        "keyword_duration": "opponent_turn",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=901221, card_id=901320, owner_id=1, card_type="ENERGY", color="Blue", resting=False),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=901222,
            card_id=901220,
            owner_id=1,
            card_type="BATTLE",
            color="Blue",
            energy_cost=1,
            has_auto=True,
        )
    ]
    state.players[1].battle_area = [
        CardInstance(instance_id=901223, card_id=901321, owner_id=1, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=901224, card_id=901322, owner_id=1, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=901225, card_id=901323, owner_id=1, card_type="BATTLE", color="Blue"),
    ]
    engine._card_cache[(901321, "front")] = CardRuntimeData(card_name="Gamma Pair A", card_type="BATTLE", color="Blue", characters=("Gamma 1", "SH"))
    engine._card_cache[(901322, "front")] = CardRuntimeData(card_name="Gamma Pair B", card_type="BATTLE", color="Blue", characters=("Gamma 2", "SH"))
    engine._card_cache[(901323, "front")] = CardRuntimeData(card_name="Single SH", card_type="BATTLE", color="Blue", characters=("SH",))

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert "Barrier" in next(card for card in state.players[1].battle_area if card.instance_id == 901223).delayed_temporary_keywords
    assert "Barrier" in next(card for card in state.players[1].battle_area if card.instance_id == 901224).delayed_temporary_keywords
    assert "Barrier" not in next(card for card in state.players[1].battle_area if card.instance_id == 901225).delayed_temporary_keywords
    assert any(cp.name == "effect_auto_buff_up_to_n_owner_battles_on_play" for cp in state.checkpoints)


def test_phase4_attack_can_ko_up_to_n_opponent_battle() -> None:
    engine = RulesEngine(
        effect_rules={
            901230: [
                {
                    "trigger": "self_attacks",
                    "handler_id": "auto_ko_up_to_n_opponent_battle_on_attack",
                    "handler_params": {"max_targets": 1, "target_policy": "first"},
                    "once_per_turn": True,
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    attacker = CardInstance(instance_id=901231, card_id=901230, owner_id=1, card_type="BATTLE", color="Yellow", power=20000, has_auto=True)
    defender = CardInstance(instance_id=901232, card_id=901330, owner_id=2, card_type="BATTLE", color="Red", power=10000)
    state.players[1].battle_area = [attacker]
    state.players[2].battle_area = [defender]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=attacker)

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert not state.players[2].battle_area
    assert any(card.instance_id == 901232 for card in state.players[2].drop)
    assert any(cp.name == "effect_auto_ko_up_to_n_on_attack" for cp in state.checkpoints)


def test_phase4_self_ko_can_play_named_card_from_owner_drop() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            if card_id == 901240:
                return SimpleNamespace(
                    id=901240,
                    card_number="BT25-114",
                    card_name="Nuova Shenron, Blazing Blaster Meteor",
                    card_type="BATTLE",
                    card_color="Yellow",
                    card_energy_cost="5",
                    energy_cost_int=5,
                    combo_cost_int=1,
                    combo_power_int=5000,
                    power_int=30000,
                    card_skill_unstyled="",
                    has_auto=True,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_draw=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Nuova Shenron"]',
                )
            if card_id == 901241:
                return SimpleNamespace(
                    id=901241,
                    card_number="BT25-200",
                    card_name="Negative Energy Four-Star Ball",
                    card_type="EXTRA",
                    card_color="Yellow",
                    card_energy_cost="1",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=0,
                    power_int=0,
                    card_skill_unstyled="",
                    has_auto=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_draw=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='[]',
                )
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="Yellow",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_auto=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_draw=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            901240: [
                {
                    "trigger": "self_koed",
                    "handler_id": "auto_play_up_to_n_named_from_owner_drop_on_self_ko",
                    "handler_params": {
                        "max_targets": 1,
                        "required_name_contains": "NEGATIVE ENERGY FOUR-STAR BALL",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    source = CardInstance(instance_id=901242, card_id=901240, owner_id=1, card_type="BATTLE", color="Yellow", power=30000, has_auto=True)
    extra = CardInstance(instance_id=901243, card_id=901241, owner_id=1, card_type="EXTRA", color="Yellow")
    state.players[1].battle_area = [source]
    state.players[1].drop = [extra]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    engine._ko_card(state, 1, "battle", 901242)
    engine._run_confirmative_rule_processing(state)
    engine._resolve_pending_effects(state)
    assert any(card.instance_id == 901243 for card in state.players[1].battle_area)
    assert not any(card.instance_id == 901243 for card in state.players[1].drop)
    assert any(cp.name == "effect_auto_play_up_to_n_named_from_owner_drop_on_self_ko" for cp in state.checkpoints)


def test_phase4_activate_battle_unison_can_switch_self_active_and_gain_power_for_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            900788: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "activate_switch_self_active_and_gain_power_for_turn",
                    "handler_params": {"power_delta": 15000},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].unison_area = [
        CardInstance(
            instance_id=880806,
            card_id=900788,
            owner_id=1,
            card_type="UNISON",
            color="Black",
            power=20000,
            resting=True,
            has_activate_battle=True,
            markers=2,
        )
    ]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=state.players[1].unison_area[0])
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader" and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "unison" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    unison = state.players[1].unison_area[0]
    assert unison.resting is False
    assert unison.power == 35000
    assert unison.temporary_power_delta == 15000
    assert any(cp.name == "effect_activate_switch_self_active_and_gain_power_for_turn" for cp in state.checkpoints)
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert state.players[1].unison_area[0].power == 20000
    assert state.players[1].unison_area[0].temporary_power_delta == 0


def test_phase4_activate_main_hidden_mode_battle_or_energy_cost_can_ko_and_buff_leader_for_turn() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "White", 0, "LEADER", "[]", "[]", False, False, 10000),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False, 10000),
                900770: ("Leader Buffer", "White", 2, "BATTLE", "[]", "[]", True, False, 15000),
                900771: ("White Ally", "White", 2, "BATTLE", "[]", "[]", False, False, 15000),
                900772: ("Target", "Red", 3, "BATTLE", "[]", "[]", False, False, 15000),
                900773: ("Energy Card", "White", 1, "BATTLE", "[]", "[]", False, False, 5000),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_auto, power = data.get(
                card_id,
                ("Card", "White", 0, "BATTLE", "[]", "[]", False, False, 15000),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=power,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        skill_cost_rules={
            900770: {
                "activate_main": [
                    {"kind": "switch_owner_battle_or_energy_to_hidden", "amount": 1, "allowed_colors": "white"}
                ]
            }
        },
        effect_rules={
            900770: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_ko_up_to_n_opponent_battle_and_buff_owner_leader_for_turn",
                    "handler_params": {"max_targets": 1, "leader_power_delta": 20000, "target_policy": "first"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880770, card_id=900770, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True, power=15000)
    )
    state.players[1].energy.append(CardInstance(instance_id=880773, card_id=900773, owner_id=1, card_type="BATTLE", color="White", resting=False, power=5000))
    state.players[2].battle_area.append(CardInstance(instance_id=880772, card_id=900772, owner_id=2, card_type="BATTLE", color="Red", power=15000))
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    assert state.players[1].energy[0].hidden_mode is True
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert all(card.instance_id != 880772 for card in state.players[2].battle_area)
    assert any(card.instance_id == 880772 for card in state.players[2].drop)
    assert state.players[1].leader_area.power == 30000
    assert state.players[1].leader_area.temporary_power_delta == 20000
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert state.players[1].leader_area.power == 10000
    assert state.players[1].leader_area.temporary_power_delta == 0


def test_phase4_activate_main_drop_owner_hidden_mode_draw_n() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "White", 0, "LEADER", False),
                2: ("Other Leader", "Red", 0, "LEADER", False),
                900740: ("Hidden Recycler", "White", 2, "BATTLE", True),
                900741: ("Hidden Target", "White", 2, "BATTLE", False),
            }
            name, color, cost, card_type, has_activate_main = data.get(card_id, ("Card", "White", 0, "BATTLE", False))
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json="[]",
                card_character_json="[]",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900740: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_drop_owner_hidden_mode_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    hand_before = len(state.players[1].hand)
    deck_before = len(state.players[1].deck)
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=880740, card_id=900740, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True),
            CardInstance(instance_id=880741, card_id=900741, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True),
        ]
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert all(card.instance_id != 880741 for card in state.players[1].battle_area)
    assert any(card.instance_id == 880741 for card in state.players[1].drop)
    assert len(state.players[1].hand) == hand_before + 1
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_activate_drop_owner_hidden_mode_draw_n" for cp in state.checkpoints)


def test_phase4_play_switch_opponent_battle_to_hidden_then_reveal_on_turn_end() -> None:
    engine = RulesEngine(
        effect_rules={
            900742: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_switch_up_to_n_opponent_battle_to_hidden_then_reveal_on_turn_end",
                    "handler_params": {"max_targets": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880742, card_id=900742, owner_id=1, card_type="BATTLE", energy_cost=0)
    ]
    state.players[2].battle_area = [
        CardInstance(instance_id=880743, card_id=900743, owner_id=2, card_type="BATTLE", energy_cost=2, power=15000)
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[2].battle_area[0].hidden_mode is True
    assert any(cp.name == "effect_auto_switch_opponent_battle_hidden_then_reveal_on_turn_end" for cp in state.checkpoints)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert state.players[2].battle_area[0].hidden_mode is False
    assert any(cp.name == "delayed_mode_switch_resolved" for cp in state.checkpoints)


def test_phase4_play_switch_owner_board_to_revealed_on_play() -> None:
    engine = RulesEngine(
        effect_rules={
            900745: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_switch_up_to_n_owner_board_to_revealed_on_play",
                    "handler_params": {"max_targets": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [CardInstance(instance_id=880801, card_id=1001, owner_id=1, card_type="ENERGY", color="Red")]
    state.players[1].battle_area.append(
        CardInstance(instance_id=880802, card_id=900746, owner_id=1, card_type="BATTLE", color="Red", hidden_mode=True)
    )
    state.players[1].hand = [CardInstance(instance_id=880803, card_id=900745, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].battle_area[0].hidden_mode is False
    assert any(cp.name == "effect_auto_switch_owner_board_to_revealed_on_play" for cp in state.checkpoints)


def test_phase4_play_switch_any_player_board_to_revealed_on_play() -> None:
    engine = RulesEngine(
        effect_rules={
            900744: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_switch_up_to_n_any_player_board_to_revealed_on_play",
                    "handler_params": {"max_targets": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [CardInstance(instance_id=880809, card_id=1001, owner_id=1, card_type="ENERGY", color="Red")]
    state.players[2].battle_area.append(
        CardInstance(instance_id=880810, card_id=900750, owner_id=2, card_type="BATTLE", color="Blue", hidden_mode=True)
    )
    state.players[1].hand = [CardInstance(instance_id=880811, card_id=900744, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[2].battle_area[0].hidden_mode is False
    assert any(cp.name == "effect_auto_switch_any_player_board_to_revealed_on_play" for cp in state.checkpoints)


def test_phase4_play_switch_owner_battle_to_hidden_on_play() -> None:
    engine = RulesEngine(
        effect_rules={
            900747: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_switch_up_to_n_owner_battle_to_hidden_on_play",
                    "handler_params": {"max_targets": 1, "allowed_colors": "white"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [CardInstance(instance_id=880804, card_id=1001, owner_id=1, card_type="ENERGY", color="White")]
    state.players[1].battle_area.append(
        CardInstance(instance_id=880805, card_id=900748, owner_id=1, card_type="BATTLE", color="White", hidden_mode=False)
    )
    state.players[1].hand = [CardInstance(instance_id=880806, card_id=900747, owner_id=1, card_type="BATTLE", color="White", energy_cost=1)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].battle_area[0].hidden_mode is True
    assert any(cp.name == "effect_auto_switch_owner_battle_to_hidden_on_play" for cp in state.checkpoints)


def test_phase4_play_draw_and_switch_self_to_hidden_on_play() -> None:
    engine = RulesEngine(
        effect_rules={
            900749: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                },
                {
                    "trigger": "self_played",
                    "handler_id": "auto_switch_self_to_hidden_on_play",
                    "handler_params": {},
                },
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[3001, 3002] + _deck(1000, 58),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [CardInstance(instance_id=880807, card_id=1001, owner_id=1, card_type="ENERGY", color="White")]
    state.players[1].hand = [CardInstance(instance_id=880808, card_id=900749, owner_id=1, card_type="BATTLE", color="White", energy_cost=1)]
    hand_before = len(state.players[1].hand)
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    played = next(card for card in state.players[1].battle_area if card.card_id == 900749)
    assert played.hidden_mode is True
    assert len(state.players[1].hand) == hand_before
    assert any(cp.name == "effect_auto_switch_self_to_hidden_on_play" for cp in state.checkpoints)


def test_phase4_hidden_switch_can_buff_owner_leader_until_opponent_turn_end() -> None:
    engine = RulesEngine(
        effect_rules={
            900820: [
                {
                    "trigger": "self_switched_hidden",
                    "handler_id": "auto_buff_owner_leader_on_switch_until_opponent_turn_end",
                    "handler_params": {"power_delta": 5000, "requires_owner_actor": True},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880820, card_id=900820, owner_id=1, card_type="BATTLE", color="White")
    state.players[1].battle_area.append(source)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    baseline = state.players[1].leader_area.power
    source.hidden_mode = True
    engine._emit_effect_event(
        state,
        name="card_switched_hidden_mode",
        actor_player_id=1,
        payload={"source_instance_id": source.instance_id, "source_card_id": source.card_id, "source_zone": "battle", "owner_player_id": 1},
    )
    engine._resolve_pending_effects(state)
    assert state.players[1].leader_area.power == baseline + 5000
    assert any(cp.name == "effect_auto_buff_owner_leader_on_switch_until_opponent_turn_end" for cp in state.checkpoints)


def test_phase4_hidden_switch_can_grant_owner_card_keyword_until_opponent_turn_end() -> None:
    engine = RulesEngine(
        effect_rules={
            900821: [
                {
                    "trigger": "self_switched_hidden",
                    "handler_id": "auto_buff_up_to_n_owner_cards_on_switch",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "white",
                        "grant_keyword": "Barrier",
                        "keyword_duration": "opponent_turn",
                        "requires_owner_actor": True,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880821, card_id=900821, owner_id=1, card_type="BATTLE", color="Blue")
    target = CardInstance(instance_id=880822, card_id=900822, owner_id=1, card_type="BATTLE", color="White")
    state.players[1].battle_area.extend([source, target])
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    source.hidden_mode = True
    engine._emit_effect_event(
        state,
        name="card_switched_hidden_mode",
        actor_player_id=1,
        payload={"source_instance_id": source.instance_id, "source_card_id": source.card_id, "source_zone": "battle", "owner_player_id": 1},
    )
    engine._resolve_pending_effects(state)
    assert "Barrier" in target.delayed_temporary_keywords
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert "Barrier" in state.players[1].battle_area[1].delayed_temporary_keywords
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    assert "Barrier" not in state.players[1].battle_area[1].delayed_temporary_keywords


def test_phase4_revealed_switch_can_buff_self_for_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            900823: [
                {
                    "trigger": "self_switched_revealed",
                    "handler_id": "auto_self_gain_power_and_keyword_for_turn_on_switch",
                    "handler_params": {"power_delta": 5000, "grant_keyword": "Double Strike"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880823, card_id=900823, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True, power=10000)
    state.players[1].battle_area.append(source)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    source.hidden_mode = False
    engine._emit_effect_event(
        state,
        name="card_switched_revealed_mode",
        actor_player_id=1,
        payload={"source_instance_id": source.instance_id, "source_card_id": source.card_id, "source_zone": "battle", "owner_player_id": 1},
    )
    engine._resolve_pending_effects(state)
    assert source.power == 15000
    assert "Double Strike" in source.temporary_keywords


def test_phase4_switch_can_buff_owner_card_for_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            900824: [
                {
                    "trigger": "self_switched_revealed",
                    "handler_id": "auto_buff_up_to_n_owner_cards_on_switch",
                    "handler_params": {"max_targets": 1, "allowed_colors": "white", "power_delta": 10000, "requires_owner_turn": True},
                },
                {
                    "trigger": "self_switched_hidden",
                    "handler_id": "auto_buff_up_to_n_owner_cards_on_switch",
                    "handler_params": {"max_targets": 1, "allowed_colors": "white", "power_delta": 10000, "requires_owner_turn": True},
                },
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880824, card_id=900824, owner_id=1, card_type="BATTLE", color="Blue", hidden_mode=True)
    target = CardInstance(instance_id=880825, card_id=900825, owner_id=1, card_type="BATTLE", color="White", power=10000)
    state.players[1].battle_area.extend([source, target])
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    source.hidden_mode = False
    engine._emit_effect_event(
        state,
        name="card_switched_revealed_mode",
        actor_player_id=1,
        payload={"source_instance_id": source.instance_id, "source_card_id": source.card_id, "source_zone": "battle", "owner_player_id": 1},
    )
    engine._resolve_pending_effects(state)
    assert target.power == 20000


def test_phase4_switch_can_ko_opponent_battle_on_owner_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            900826: [
                {
                    "trigger": "self_switched_revealed",
                    "handler_id": "auto_ko_up_to_n_opponent_battle_on_switch",
                    "handler_params": {"max_targets": 1, "requires_owner_turn": True},
                },
                {
                    "trigger": "self_switched_hidden",
                    "handler_id": "auto_ko_up_to_n_opponent_battle_on_switch",
                    "handler_params": {"max_targets": 1, "requires_owner_turn": True},
                },
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880826, card_id=900826, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True)
    state.players[1].battle_area.append(source)
    state.players[2].battle_area.append(CardInstance(instance_id=880827, card_id=900827, owner_id=2, card_type="BATTLE", color="Red", power=5000))
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    source.hidden_mode = False
    engine._emit_effect_event(
        state,
        name="card_switched_revealed_mode",
        actor_player_id=1,
        payload={"source_instance_id": source.instance_id, "source_card_id": source.card_id, "source_zone": "battle", "owner_player_id": 1},
    )
    engine._resolve_pending_effects(state)
    assert not state.players[2].battle_area


def test_phase4_hidden_drop_can_buff_owner_card_on_ko_path() -> None:
    engine = RulesEngine(
        effect_rules={
            900830: [
                {
                    "trigger": "self_hidden_battle_to_drop",
                    "handler_id": "auto_buff_up_to_n_owner_cards_on_hidden_drop",
                    "handler_params": {"max_targets": 1, "allowed_colors": "white", "power_delta": 5000},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880830, card_id=900830, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True, power=5000)
    target = CardInstance(instance_id=880831, card_id=900831, owner_id=1, card_type="BATTLE", color="White", power=10000)
    state.players[1].battle_area.extend([source, target])
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    engine._ko_card(state, 1, "battle", source.instance_id)
    engine._resolve_pending_effects(state)
    assert target.power == 15000
    assert any(cp.name == "effect_auto_buff_up_to_n_owner_cards_on_hidden_drop" for cp in state.checkpoints)


def test_phase4_hidden_drop_can_buff_owner_card_on_non_ko_drop_path() -> None:
    engine = RulesEngine(
        effect_rules={
            900832: [
                {
                    "trigger": "self_hidden_battle_to_drop",
                    "handler_id": "auto_buff_up_to_n_owner_cards_on_hidden_drop",
                    "handler_params": {"max_targets": 1, "allowed_colors": "white", "power_delta": 5000},
                }
            ],
            900833: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "noop_auto",
                }
            ],
        },
        skill_cost_rules={
            900833: {
                "activate_main": [
                    {"kind": "send_owner_hidden_mode_battle_to_drop", "amount": 1}
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880832, card_id=900832, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True, power=5000)
    target = CardInstance(instance_id=880833, card_id=900834, owner_id=1, card_type="BATTLE", color="White", power=10000)
    activator = CardInstance(instance_id=880834, card_id=900833, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True)
    state.players[1].battle_area.extend([source, target, activator])
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=activator)
    act = Action(action_type=ActionType.ACTIVATE_MAIN_SKILL, player_id=1, source_zone="battle", source_index=2)
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    resolved_target = next(card for card in state.players[1].battle_area if card.instance_id == target.instance_id)
    assert resolved_target.power == 15000
    assert any(card.instance_id == source.instance_id for card in state.players[1].drop)
    assert any(cp.name == "effect_auto_buff_up_to_n_owner_cards_on_hidden_drop" for cp in state.checkpoints)


def test_phase4_activate_main_draw_and_gain_dual_attack_for_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            900710: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_draw_n_and_gain_keyword_for_turn",
                    "handler_params": {"amount": 1, "grant_keyword": "Dual Attack"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    deck_before = len(state.players[1].deck)
    state.players[1].battle_area.append(
        CardInstance(
            instance_id=880710,
            card_id=900710,
            owner_id=1,
            card_type="BATTLE",
            energy_cost=1,
            power=15000,
            has_activate_main=True,
        )
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    act = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    )
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    attacker = state.players[1].battle_area[0]
    assert len(state.players[1].deck) == deck_before - 1
    assert "Dual Attack" in attacker.temporary_keywords
    first_attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, first_attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    attacker = state.players[1].battle_area[0]
    assert attacker.resting is False
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    assert any(
        a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0
        for a in engine.get_legal_actions(state, 1)
    )


def test_phase4_self_attacks_power_reduce_up_to_n_rule() -> None:
    engine = RulesEngine(
        effect_rules={
            424270: [
                {
                    "trigger": "self_attacks",
                    "handler_id": "auto_power_reduce_up_to_n_on_attack",
                    "handler_params": {
                        "max_targets": 1,
                        "max_cost": -1,
                        "target_policy": "first",
                        "power_delta": -10000,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880351, card_id=424270, owner_id=1, card_type="BATTLE", energy_cost=0, power=15000)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    state.players[2].battle_area = [
        CardInstance(instance_id=880352, card_id=352, owner_id=2, card_type="BATTLE", energy_cost=1, power=9000)
    ]
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[2].battle_area) == 0
    assert any(c.instance_id == 880352 for c in state.players[2].drop)
    assert any(cp.name == "effect_auto_power_reduce_up_to_n_on_attack" for cp in state.checkpoints)


def test_phase4_self_attacks_can_pay_life_gain_power_and_keyword() -> None:
    engine = RulesEngine(
        effect_rules={
            424282: [
                {
                    "trigger": "self_attacks",
                    "handler_id": "auto_pay_life_on_attack_gain_power_and_keyword_for_turn",
                    "handler_params": {"life_to_hand": 1, "power_delta": 15000, "grant_keyword": "Double Strike"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880353, card_id=424282, owner_id=1, card_type="BATTLE", energy_cost=0, power=15000, keywords=())
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    life_before = len(state.players[1].life)
    hand_before = len(state.players[1].hand)
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    attacker = state.players[1].battle_area[0]
    assert len(state.players[1].life) == life_before - 1
    assert len(state.players[1].hand) == hand_before + 1
    assert attacker.power == 30000
    assert "Double Strike" in attacker.temporary_keywords
    assert any(cp.name == "effect_auto_pay_life_on_attack_gain_power_and_keyword_for_turn" for cp in state.checkpoints)


def test_phase4_owner_leader_attack_can_add_from_hand_to_life() -> None:
    engine = RulesEngine(
        effect_rules={
            424283: [
                {
                    "trigger": "owner_leader_attacks",
                    "handler_id": "auto_add_up_to_n_from_owner_hand_to_life_on_owner_leader_attack",
                    "handler_params": {"amount": 1, "allowed_colors": "yellow"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880354, card_id=424283, owner_id=1, card_type="BATTLE", energy_cost=0)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    state.players[1].hand = [
        CardInstance(instance_id=880355, card_id=900951, owner_id=1, card_type="BATTLE", color="Yellow"),
        CardInstance(instance_id=880356, card_id=900952, owner_id=1, card_type="BATTLE", color="Blue"),
    ]
    life_before = len(state.players[1].life)
    hand_before = len(state.players[1].hand)
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader" and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].life) == life_before + 1
    assert len(state.players[1].hand) == hand_before - 1
    assert any(c.instance_id == 880355 for c in state.players[1].life)
    assert any(c.instance_id == 880356 for c in state.players[1].hand)
    assert any(cp.name == "effect_auto_add_up_to_n_from_owner_hand_to_life_on_owner_leader_attack" for cp in state.checkpoints)


def test_phase4_owner_leader_attack_can_search_top_and_add_matching_card_to_hand() -> None:
    class FakeRepo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: SimpleNamespace(
                    card_name="Leader",
                    power_int=10000,
                    card_type="LEADER",
                    card_color="Red",
                    energy_cost_int=0,
                    combo_cost_int=0,
                    combo_power_int=0,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=True,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    card_skill_unstyled="[Auto] When your Leader Card attacks, look at up to 5 cards from the top of your deck, add up to 1 red Earthling card among them to your hand, then shuffle your deck.",
                    card_traits_json='["Earthling"]',
                    card_character_json='["Krillin"]',
                ),
                900961: SimpleNamespace(
                    card_name="Red Earthling",
                    power_int=5000,
                    card_type="BATTLE",
                    card_color="Red",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    card_skill_unstyled="",
                    card_traits_json='["Earthling"]',
                    card_character_json='["Krillin"]',
                ),
                900962: SimpleNamespace(
                    card_name="Blue Earthling",
                    power_int=5000,
                    card_type="BATTLE",
                    card_color="Blue",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    card_skill_unstyled="",
                    card_traits_json='["Earthling"]',
                    card_character_json='["Krillin"]',
                ),
            }
            return data[card_id]

    engine = RulesEngine(
        card_repository=FakeRepo(),
        effect_rules={
            424284: [
                {
                    "trigger": "owner_leader_attacks",
                    "handler_id": "auto_look_top_add_up_to_one_to_hand_on_play",
                    "handler_params": {
                        "look_count": 5,
                        "max_add": 1,
                        "allowed_colors": "red",
                        "required_traits": "Earthling",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880357, card_id=424284, owner_id=1, card_type="BATTLE", energy_cost=0)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    state.players[1].deck = [
        CardInstance(instance_id=880358, card_id=900962, owner_id=1, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=880359, card_id=900961, owner_id=1, card_type="BATTLE", color="Red"),
        *state.players[1].deck,
    ]
    hand_before = len(state.players[1].hand)
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader" and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].hand) == hand_before + 1
    assert any(c.card_id == 900961 for c in state.players[1].hand)
    assert any(c.card_id == 900962 for c in state.players[1].deck)
    assert any(cp.name == "effect_auto_look_top_add_up_to_one_to_hand_on_play" for cp in state.checkpoints)


def test_phase4_self_played_can_add_from_hand_to_life() -> None:
    engine = RulesEngine(
        effect_rules={
            424288: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_add_up_to_n_from_owner_hand_to_life_on_play",
                    "handler_params": {"amount": 1, "allowed_colors": "yellow", "requires_played_from": "hand"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880362, card_id=424288, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=0),
        CardInstance(instance_id=880363, card_id=900971, owner_id=1, card_type="BATTLE", color="Yellow"),
        CardInstance(instance_id=880364, card_id=900972, owner_id=1, card_type="BATTLE", color="Blue"),
    ]
    life_before = len(state.players[1].life)
    hand_before = len(state.players[1].hand)
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].life) == life_before + 1
    assert len(state.players[1].hand) == hand_before - 2
    assert any(c.instance_id == 880363 for c in state.players[1].life)
    assert any(c.instance_id == 880364 for c in state.players[1].hand)
    assert any(cp.name == "effect_auto_add_up_to_n_from_owner_hand_to_life_on_play" for cp in state.checkpoints)


def test_phase4_field_extra_placed_can_switch_owner_energy_active() -> None:
    engine = RulesEngine(
        effect_rules={
            424284: [
                {
                    "trigger": "owner_field_extra_placed",
                    "handler_id": "auto_switch_up_to_n_owner_energy_active_on_field_extra_placed",
                    "handler_params": {"max_targets": 2, "allowed_colors": "yellow"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880357, card_id=424284, owner_id=1, card_type="BATTLE", energy_cost=0)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    state.players[1].energy = [
        CardInstance(instance_id=880358, card_id=900961, owner_id=1, color="Yellow", resting=True),
        CardInstance(instance_id=880359, card_id=900962, owner_id=1, color="Yellow", resting=True),
        CardInstance(instance_id=880360, card_id=900963, owner_id=1, color="Blue", resting=True),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=880361,
            card_id=900964,
            owner_id=1,
            card_type="EXTRA",
            energy_cost=0,
            keywords=("Field",),
            has_counter=False,
        )
    ]
    play_extra = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play_extra)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].energy[0].resting is False
    assert state.players[1].energy[1].resting is False
    assert state.players[1].energy[2].resting is True
    assert any(evt.name == "field_extra_placed" for evt in state.effect_events)
    assert any(cp.name == "effect_auto_switch_up_to_n_owner_energy_active_on_field_extra_placed" for cp in state.checkpoints)


def test_phase4_self_played_can_play_from_hand_with_markers_and_rest() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE"),
                2: ("Blue", "BATTLE"),
                424271: ("Blue", "BATTLE"),
                900701: ("Blue", "UNISON"),
            }
            color, ctype = data.get(card_id, ("Blue", "BATTLE"))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424271: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play",
                    "handler_params": {
                        "max_targets": 1,
                        "markers": 1,
                        "source_pool": "hand",
                        "requires_played_from": "hand",
                        "rest_mode": True,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880361, card_id=424271, owner_id=1, card_type="BATTLE", energy_cost=0),
        CardInstance(instance_id=880362, card_id=900701, owner_id=1, card_type="UNISON", energy_cost=0),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].card_id == 900701
    assert state.players[1].unison_area[0].markers == 1
    assert state.players[1].unison_area[0].resting is True
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play" for cp in state.checkpoints)


def test_phase4_self_played_can_play_from_deck_with_markers_when_hand_pool_empty() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE"),
                2: ("Blue", "BATTLE"),
                424272: ("Blue", "BATTLE"),
                900702: ("Blue", "UNISON"),
            }
            color, ctype = data.get(card_id, ("Blue", "BATTLE"))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424272: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play",
                    "handler_params": {
                        "max_targets": 1,
                        "markers": 2,
                        "source_pool": "hand_or_deck",
                        "requires_played_from": "hand",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880371, card_id=424272, owner_id=1, card_type="BATTLE", energy_cost=0),
    ]
    state.players[1].deck = [900702]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].card_id == 900702
    assert state.players[1].unison_area[0].markers == 2
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play" for cp in state.checkpoints)


def test_phase4_self_played_can_play_multiple_from_hand_with_markers() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE"),
                2: ("Blue", "BATTLE"),
                424273: ("Blue", "BATTLE"),
                900711: ("Blue", "BATTLE"),
                900712: ("Blue", "BATTLE"),
            }
            color, ctype = data.get(card_id, ("Blue", "BATTLE"))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424273: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play",
                    "handler_params": {
                        "max_targets": 2,
                        "markers": 3,
                        "source_pool": "hand",
                        "requires_played_from": "hand",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880381, card_id=424273, owner_id=1, card_type="BATTLE", energy_cost=0),
        CardInstance(instance_id=880382, card_id=900711, owner_id=1, card_type="BATTLE", energy_cost=0),
        CardInstance(instance_id=880383, card_id=900712, owner_id=1, card_type="BATTLE", energy_cost=0),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].battle_area) == 3
    played = [c for c in state.players[1].battle_area if c.card_id in {900711, 900712}]
    assert len(played) == 2
    assert all(c.markers == 3 for c in played)
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play" for cp in state.checkpoints)


def test_phase4_self_played_can_fill_remaining_from_deck_after_hand() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE"),
                2: ("Blue", "BATTLE"),
                424274: ("Blue", "BATTLE"),
                900721: ("Blue", "BATTLE"),
                900722: ("Blue", "BATTLE"),
            }
            color, ctype = data.get(card_id, ("Blue", "BATTLE"))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424274: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play",
                    "handler_params": {
                        "max_targets": 2,
                        "markers": 2,
                        "source_pool": "hand_or_deck",
                        "requires_played_from": "hand",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880391, card_id=424274, owner_id=1, card_type="BATTLE", energy_cost=0),
        CardInstance(instance_id=880392, card_id=900721, owner_id=1, card_type="BATTLE", energy_cost=0),
    ]
    state.players[1].deck = [900722]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].battle_area) == 3
    played = [c for c in state.players[1].battle_area if c.card_id in {900721, 900722}]
    assert len(played) == 2
    assert all(c.markers == 2 for c in played)
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play" for cp in state.checkpoints)


def test_phase4_self_played_marker_multi_target_respects_cost_color_type_filters_in_hand() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE", 0),
                2: ("Blue", "BATTLE", 0),
                424275: ("Blue", "BATTLE", 0),
                900731: ("Red", "BATTLE", 1),
                900732: ("Blue", "BATTLE", 2),
                900733: ("Blue", "UNISON", 2),
                900734: ("Blue", "BATTLE", 3),
                900735: ("Blue", "BATTLE", 5),
            }
            color, ctype, cost = data.get(card_id, ("Blue", "BATTLE", 0))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424275: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play",
                    "handler_params": {
                        "max_targets": 2,
                        "markers": 4,
                        "source_pool": "hand",
                        "requires_played_from": "hand",
                        "max_cost": 3,
                        "allowed_colors": "blue",
                        "required_card_type": "BATTLE",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880401, card_id=424275, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=0),
        CardInstance(instance_id=880402, card_id=900731, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1),
        CardInstance(instance_id=880403, card_id=900732, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=2),
        CardInstance(instance_id=880404, card_id=900733, owner_id=1, card_type="UNISON", color="Blue", energy_cost=2),
        CardInstance(instance_id=880405, card_id=900735, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=5),
        CardInstance(instance_id=880406, card_id=900734, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=3),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    played = [c for c in state.players[1].battle_area if c.card_id in {900731, 900732, 900733, 900734, 900735}]
    assert [c.card_id for c in played] == [900732, 900734]
    assert all(c.markers == 4 for c in played)


def test_phase4_self_played_marker_multi_target_respects_filters_when_filling_from_deck() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE", 0),
                2: ("Blue", "BATTLE", 0),
                424276: ("Blue", "BATTLE", 0),
                900741: ("Blue", "BATTLE", 2),
                900742: ("Red", "BATTLE", 2),
                900743: ("Blue", "UNISON", 2),
                900744: ("Blue", "BATTLE", 1),
            }
            color, ctype, cost = data.get(card_id, ("Blue", "BATTLE", 0))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424276: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play",
                    "handler_params": {
                        "max_targets": 2,
                        "markers": 2,
                        "source_pool": "hand_or_deck",
                        "requires_played_from": "hand",
                        "max_cost": 2,
                        "allowed_colors": "blue",
                        "required_card_type": "BATTLE",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880411, card_id=424276, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=0),
        CardInstance(instance_id=880412, card_id=900741, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=2),
    ]
    state.players[1].deck = [900742, 900743, 900744]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    played = [c for c in state.players[1].battle_area if c.card_id in {900741, 900742, 900743, 900744}]
    assert [c.card_id for c in played] == [900741, 900744]
    assert all(c.markers == 2 for c in played)


def test_phase4_self_played_can_add_up_to_n_from_deck_to_hand() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE", 0, ()),
                2: ("Blue", "BATTLE", 0, ()),
                424277: ("Blue", "BATTLE", 0, ()),
                900751: ("Yellow", "EXTRA", 1, ()),
            }
            color, ctype, cost, keywords = data.get(card_id, ("Blue", "BATTLE", 0, ()))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=keywords,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424277: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_add_up_to_n_from_owner_deck_to_hand_on_play",
                    "handler_params": {"max_targets": 1},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=880421, card_id=424277, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[1].deck = [900751]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(c.card_id == 900751 for c in state.players[1].hand)
    assert len(state.players[1].deck) == 0
    assert any(cp.name == "effect_auto_add_up_to_n_from_owner_deck_to_hand_on_play" for cp in state.checkpoints)


def test_phase4_self_played_add_from_deck_to_hand_respects_filters() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE", 0, ()),
                2: ("Blue", "BATTLE", 0, ()),
                424278: ("Blue", "BATTLE", 0, ()),
                900761: ("Green", "BATTLE", 2, ("skill-less",)),
                900762: ("Green", "BATTLE", 4, ("skill-less",)),
                900763: ("Green", "UNISON", 2, ("skill-less",)),
                900764: ("Yellow", "BATTLE", 2, ("skill-less",)),
                900765: ("Green", "BATTLE", 1, ()),
                900766: ("Green", "BATTLE", 1, ("skill-less",)),
            }
            color, ctype, cost, keywords = data.get(card_id, ("Blue", "BATTLE", 0, ()))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=keywords,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424278: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_add_up_to_n_from_owner_deck_to_hand_on_play",
                    "handler_params": {
                        "max_targets": 2,
                        "max_cost": 3,
                        "allowed_colors": "green",
                        "required_card_type": "BATTLE",
                        "requires_skill_less": True,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=880431, card_id=424278, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[1].deck = [900762, 900763, 900764, 900765, 900761, 900766]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    added = [c.card_id for c in state.players[1].hand if c.card_id in {900761, 900762, 900763, 900764, 900765, 900766}]
    assert added == [900761, 900766]
    assert state.players[1].deck == [900762, 900763, 900764, 900765]


def test_phase4_self_played_adds_markers_per_multicolor_energy() -> None:
    engine = RulesEngine(
        effect_rules={
            424279: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_add_markers_per_n_multicolor_energy_on_play",
                    "handler_params": {"per_n_energy": 1},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880441, card_id=900801, owner_id=1, color="Blue"),
        CardInstance(instance_id=880442, card_id=900802, owner_id=1, color="Yellow"),
        CardInstance(instance_id=880443, card_id=900803, owner_id=1, color="Red/Blue"),
        CardInstance(instance_id=880445, card_id=900804, owner_id=1, color="Blue/Green"),
    ]
    state.players[1].hand = [
        CardInstance(instance_id=880444, card_id=424279, owner_id=1, card_type="UNISON", color="Blue", energy_cost=1, markers=1),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].markers == 3
    assert any(cp.name == "effect_auto_add_markers_per_n_multicolor_energy_on_play" for cp in state.checkpoints)


def test_phase4_self_played_adds_markers_requires_min_source_markers() -> None:
    engine = RulesEngine(
        effect_rules={
            424280: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_add_markers_per_n_multicolor_energy_on_play",
                    "handler_params": {"per_n_energy": 1, "min_source_markers": 2},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880451, card_id=900811, owner_id=1, color="Blue"),
        CardInstance(instance_id=880452, card_id=900812, owner_id=1, color="Red/Yellow"),
    ]
    state.players[1].hand = [
        CardInstance(instance_id=880453, card_id=424280, owner_id=1, card_type="UNISON", color="Blue", energy_cost=1, markers=1),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].markers == 1
    assert not any(cp.name == "effect_auto_add_markers_per_n_multicolor_energy_on_play" for cp in state.checkpoints)


def test_phase4_self_played_can_play_from_drop_rest_with_skills_negated_and_discard_cost() -> None:
    engine = RulesEngine(
        effect_rules={
            424281: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_drop_on_play",
                    "handler_params": {
                        "max_targets": 1,
                        "max_cost": 2,
                        "allowed_colors": "yellow",
                        "required_card_type": "BATTLE",
                        "rest_mode": True,
                        "negate_skills": True,
                        "discard_from_hand_before": 1,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880461, card_id=424281, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=0),
        CardInstance(instance_id=880462, card_id=900901, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=0),
    ]
    state.players[1].drop = [
        CardInstance(
            instance_id=880463,
            card_id=900902,
            owner_id=1,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=2,
            keywords=("Double Strike",),
            has_auto=True,
            has_activate_main=True,
            has_permanent=True,
        ),
        CardInstance(instance_id=880464, card_id=900903, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=4),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(c.instance_id == 880461 for c in state.players[1].battle_area)
    played = next(c for c in state.players[1].battle_area if c.instance_id == 880463)
    assert played.resting is True
    assert played.keywords == ()
    assert played.has_auto is False
    assert played.has_activate_main is False
    assert played.has_permanent is False
    assert all(r.source_instance_id != 880463 for r in state.effect_registry)
    assert any(c.instance_id == 880462 for c in state.players[1].drop)
    assert any(c.instance_id == 880464 for c in state.players[1].drop)
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_drop_on_play" for cp in state.checkpoints)


def test_phase4_activate_extra_from_hand_exposes_effect_choice_actions_and_selected_search_effect_resolves() -> None:
    engine = RulesEngine(
        effect_rules={
            424301: [
                {
                    "trigger": "self_activate_extra_from_hand",
                    "handler_id": "activate_play_up_to_n_each_named_from_owner_deck_or_drop",
                    "handler_params": {
                        "max_each": 1,
                        "required_name_contains_each": "SON GOTEN|TRUNKS : YOUTH",
                        "allowed_colors": "red",
                        "required_card_type": "BATTLE",
                        "max_cost": 1,
                        "rest_mode": True,
                        "discard_from_hand_before": 1,
                    },
                },
                {
                    "trigger": "self_activate_extra_from_hand",
                    "handler_id": "activate_add_up_to_n_from_owner_deck_to_hand",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "red",
                        "required_card_type": "EXTRA",
                        "max_cost": 1,
                    },
                    "limit_per_turn": 1,
                },
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [CardInstance(instance_id=880471, card_id=900911, owner_id=1, color="Red")]
    state.players[1].hand = [
        CardInstance(instance_id=880472, card_id=424301, owner_id=1, card_type="EXTRA", color="Red", energy_cost=1),
        CardInstance(instance_id=880473, card_id=900912, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1),
    ]
    state.players[1].deck = [900913, 900914]
    engine._card_cache[(900913, "front")] = CardRuntimeData(card_name="Search Extra", card_type="EXTRA", color="Red", energy_cost=1)
    legal = [a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0]
    assert len(legal) == 2
    assert {a.effect_choice for a in legal} == {0, 1}
    search_action = next(a for a in legal if a.effect_choice == 1)
    state = engine.apply_action(state, search_action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert [c.card_id for c in state.players[1].hand] == [900912, 900913]
    assert not state.players[1].battle_area
    assert any(cp.name == "effect_activate_add_up_to_n_from_owner_deck_to_hand" for cp in state.checkpoints)
    assert not any(cp.name == "effect_activate_play_up_to_n_each_named_from_owner_deck_or_drop" for cp in state.checkpoints)


def test_phase4_activate_extra_from_hand_selected_play_effect_discards_and_plays_each_named() -> None:
    engine = RulesEngine(
        effect_rules={
            424302: [
                {
                    "trigger": "self_activate_extra_from_hand",
                    "handler_id": "activate_play_up_to_n_each_named_from_owner_deck_or_drop",
                    "handler_params": {
                        "max_each": 1,
                        "required_name_contains_each": "SON GOTEN|TRUNKS : YOUTH",
                        "allowed_colors": "red",
                        "required_card_type": "BATTLE",
                        "max_cost": 1,
                        "rest_mode": True,
                        "discard_from_hand_before": 1,
                    },
                },
                {
                    "trigger": "self_activate_extra_from_hand",
                    "handler_id": "activate_add_up_to_n_from_owner_deck_to_hand",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "red",
                        "required_card_type": "EXTRA",
                        "max_cost": 1,
                    },
                },
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [CardInstance(instance_id=880481, card_id=900921, owner_id=1, color="Red")]
    state.players[1].hand = [
        CardInstance(instance_id=880482, card_id=424302, owner_id=1, card_type="EXTRA", color="Red", energy_cost=1),
        CardInstance(instance_id=880483, card_id=900922, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1),
    ]
    state.players[1].deck = [900923]
    state.players[1].drop = [
        CardInstance(instance_id=880484, card_id=900924, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1),
    ]
    engine._card_cache[(900923, "front")] = CardRuntimeData(card_name="Son Goten", card_type="BATTLE", color="Red", energy_cost=1)
    engine._card_cache[(900924, "front")] = CardRuntimeData(card_name="Trunks : Youth", card_type="BATTLE", color="Red", energy_cost=1)
    play_action = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0 and a.effect_choice == 0
    )
    state = engine.apply_action(state, play_action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].battle_area) == 2
    assert all(card.resting for card in state.players[1].battle_area)
    assert {card.card_id for card in state.players[1].battle_area} == {900923, 900924}
    assert any(card.instance_id == 880483 for card in state.players[1].drop)
    assert any(cp.name == "effect_activate_play_up_to_n_each_named_from_owner_deck_or_drop" for cp in state.checkpoints)


def test_phase4_once_per_turn_is_detected_from_skill_text() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 990001:
                return SimpleNamespace(
                    power_int=15000,
                    card_type="BATTLE",
                    card_color="Blue",
                    energy_cost_int=0,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=True,
                    has_permanent=False,
                    has_draw=True,
                    max_draw=1,
                    has_barrier=False,
                    z_energy_cost=None,
                    card_energy_cost="0",
                    card_skill_unstyled="[Auto][Once per turn] When this card attacks, draw 1 card.",
                )
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color="Red",
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=0,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
            )

    engine = RulesEngine(card_repository=Repo())
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[990001] + _deck(1000, 59),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    play = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0
    )
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    played_instance_id = next(c.instance_id for c in state.players[1].battle_area if c.card_id == 990001)
    regs = [r for r in state.effect_registry if r.source_instance_id == played_instance_id]
    assert any(r.handler_id == "auto_draw_on_attack" and r.once_per_turn for r in regs)


def test_phase4_once_per_turn_auto_draw_on_attack_triggers_once_same_turn() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    # Keep enough deck to draw and attach a once-per-turn attack draw auto.
    source = CardInstance(
        instance_id=990011,
        card_id=11,
        owner_id=1,
        card_type="BATTLE",
        has_auto=True,
        has_draw=True,
        auto_draw_on_attack=True,
        auto_once_per_turn=True,
    )
    state.players[1].battle_area.append(source)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    deck_before = len(state.players[1].deck)

    # Same checkpoint batch with two attack events: should resolve only once.
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": 990011, "attacker_zone": "battle", "target_player_id": 2, "target_zone": "leader"},
    )
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": 990011, "attacker_zone": "battle", "target_player_id": 2, "target_zone": "leader"},
    )
    engine._resolve_pending_effects(state)
    assert len(state.players[1].deck) == deck_before - 1
    rows = [r for r in state.effect_resolutions if r.reason in {"ok", "once_per_turn_used"}]
    assert any(r.resolved and r.reason == "ok" for r in rows)
    assert any((not r.resolved) and r.reason == "once_per_turn_used" for r in rows)


def test_phase4_son_gohan_misadventure_can_declare_secret_auto_after_field_extra_hits_drop() -> None:
    engine = RulesEngine(
        effect_rules={
            90: (
                EffectRule(
                    trigger="owner_field_extra_placed_into_drop",
                    handler_id="auto_play_self_from_hand_on_owner_field_extra_to_drop_switch_up_to_n_opponent_board_rest",
                    handler_params={"max_targets": 1, "ignores_barrier": True, "requires_leader": "yellow"},
                    family_id="owner_field_extra_placed_into_drop:auto_play_self_from_hand_on_owner_field_extra_to_drop_switch_up_to_n_opponent_board_rest",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Yellow"
    misadventure = CardInstance(
        instance_id=990900,
        card_id=90,
        owner_id=1,
        card_type="BATTLE",
        color="Yellow",
        power=15000,
        has_auto=True,
        keywords=("Blocker",),
    )
    field_extra = CardInstance(
        instance_id=990901,
        card_id=909001,
        owner_id=1,
        card_type="EXTRA",
        color="Yellow",
        keywords=("Field",),
    )
    target = CardInstance(
        instance_id=990902,
        card_id=909002,
        owner_id=2,
        card_type="BATTLE",
        color="Yellow",
        power=15000,
        has_barrier=True,
        keywords=("Barrier",),
        resting=False,
    )
    state.players[1].hand = [misadventure]
    state.players[1].battle_area.append(field_extra)
    state.players[2].battle_area.append(target)
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=misadventure)

    removed = state.players[1].battle_area.pop(0)
    state.players[1].drop.append(removed)
    engine._emit_board_card_placed_into_drop(state, owner_player_id=1, card=removed, source_zone="battle")

    legal = engine.get_legal_actions(state, 1)
    assert [row.action_type for row in legal] == [ActionType.DECLARE_SECRET_AUTO, ActionType.IGNORE_SECRET_AUTO]

    state = engine.apply_action(state, next(row for row in legal if row.action_type == ActionType.DECLARE_SECRET_AUTO))

    assert not state.players[1].hand
    assert any(card.card_id == 90 for card in state.players[1].battle_area)
    assert state.players[2].battle_area[0].resting is True
    assert any(cp.name == "effect_auto_play_self_from_hand_on_owner_field_extra_to_drop_switch_up_to_n_opponent_board_rest" for cp in state.checkpoints)


def test_phase4_son_goku_reclaiming_hope_activate_main_restricts_attack_next_opponent_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            86: (
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_restrict_up_to_n_opponent_battle_attack_until_opponent_turn_end",
                    handler_params={
                        "max_targets": 1,
                        "marker_delta": 1,
                        "requires_cost_greater_or_equal_opponent_current_energy": True,
                    },
                    family_id="self_activate_main:activate_restrict_up_to_n_opponent_battle_attack_until_opponent_turn_end",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    unison = CardInstance(
        instance_id=990910,
        card_id=86,
        owner_id=1,
        card_type="UNISON",
        color="Yellow",
        markers=1,
        has_activate_main=True,
    )
    target = CardInstance(
        instance_id=990911,
        card_id=86001,
        owner_id=2,
        card_type="BATTLE",
        color="Yellow",
        energy_cost=3,
        power=15000,
    )
    state.players[1].unison_area.append(unison)
    state.players[2].battle_area.append(target)
    state.players[2].energy = [
        CardInstance(instance_id=990912 + i, card_id=86100 + i, owner_id=2, card_type="BATTLE", color="Yellow", resting=True)
        for i in range(3)
    ]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=unison)

    activate = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison" and a.source_index == 0
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(row.target_instance_id == 990911 for row in state.scheduled_attack_restrictions)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)
    legal = engine.get_legal_actions(state, 2)
    assert any(cp.name == "scheduled_attack_restrictions_activated" for cp in state.checkpoints)
    assert not any(
        a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0
        for a in legal
    )


def test_phase4_son_goku_reclaiming_hope_blocker_auto_can_restand_self() -> None:
    engine = RulesEngine(
        effect_rules={
            86: (
                EffectRule(
                    trigger="self_blocker_activated",
                    handler_id="auto_rest_owner_battle_on_self_blocker_activated_switch_self_active",
                    handler_params={"rest_owner_battle_count": 1},
                    family_id="self_blocker_activated:auto_rest_owner_battle_on_self_blocker_activated_switch_self_active",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=990920,
        card_id=86,
        owner_id=1,
        card_type="BATTLE",
        color="Yellow",
        power=15000,
        has_auto=True,
        resting=True,
        keywords=("Blocker",),
    )
    other = CardInstance(
        instance_id=990921,
        card_id=86002,
        owner_id=1,
        card_type="BATTLE",
        color="Yellow",
        power=15000,
        resting=False,
    )
    state.players[1].battle_area.extend([source, other])
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    engine._emit_effect_event(
        state,
        name="blocker_activated",
        actor_player_id=1,
        payload={"source_instance_id": 990920, "source_card_id": 86},
    )
    engine._resolve_pending_effects(state)

    assert state.players[1].battle_area[0].resting is False
    assert state.players[1].battle_area[1].resting is True
    assert any(cp.name == "effect_auto_rest_owner_battle_on_self_blocker_activated_switch_self_active" for cp in state.checkpoints)


def test_phase4_android_18_unknown_threat_attack_auto_adds_matching_energy_to_hand() -> None:
    engine = RulesEngine(
        effect_rules={
            8372: (
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_add_up_to_n_matching_from_owner_energy_to_hand_on_attack",
                        handler_params={
                            "max_targets": 1,
                            "allowed_colors": "blue",
                            "required_characters": "Android",
                        },
                    family_id="self_attacks:auto_add_up_to_n_matching_from_owner_energy_to_hand_on_attack",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    attacker = CardInstance(
        instance_id=990930,
        card_id=8372,
        owner_id=1,
        card_type="UNISON",
        color="Blue",
        power=15000,
        markers=1,
        has_auto=True,
    )
    matching_energy = CardInstance(
        instance_id=990931,
        card_id=83721,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        characters=("Android",),
        resting=True,
    )
    state.players[1].unison_area.append(attacker)
    state.players[1].energy.append(matching_energy)
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=attacker)

    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": 990930, "attacker_zone": "unison", "target_player_id": 2, "target_zone": "leader"},
    )
    engine._resolve_pending_effects(state)

    assert any(card.instance_id == 990931 for card in state.players[1].hand)
    assert not any(card.instance_id == 990931 for card in state.players[1].energy)


def test_phase4_android_18_unknown_threat_activate_main_choices_resolve_separately() -> None:
    engine = RulesEngine(
        effect_rules={
            8372: (
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_bottom_deck_up_to_n_opponent_battle_then_switch_self_active_at_turn_end",
                    handler_params={"max_targets": 1, "marker_delta": 1},
                    family_id="self_activate_main:activate_bottom_deck_up_to_n_opponent_battle_then_switch_self_active_at_turn_end",
                    provenance="test",
                ),
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_opponent_bottom_decks_n_from_hand_and_switch_up_to_n_owner_energy_active_at_turn_end",
                    handler_params={"opponent_bottom_deck_from_hand": 1, "max_targets": 1, "allowed_colors": "blue"},
                    family_id="self_activate_main:activate_opponent_bottom_decks_n_from_hand_and_switch_up_to_n_owner_energy_active_at_turn_end",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    unison = CardInstance(
        instance_id=990940,
        card_id=8372,
        owner_id=1,
        card_type="UNISON",
        color="Blue",
        power=15000,
        markers=1,
        has_activate_main=True,
        resting=True,
    )
    opponent_battle = CardInstance(
        instance_id=990941,
        card_id=83722,
        owner_id=2,
        card_type="BATTLE",
        color="Yellow",
        power=15000,
    )
    blue_energy = CardInstance(
        instance_id=990942,
        card_id=83723,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        resting=True,
    )
    opponent_hand = CardInstance(
        instance_id=990943,
        card_id=83724,
        owner_id=2,
        card_type="BATTLE",
        color="Yellow",
    )
    state.players[1].unison_area.append(unison)
    state.players[1].energy.append(blue_energy)
    state.players[2].battle_area.append(opponent_battle)
    state.players[2].hand.append(opponent_hand)
    opponent_hand_before = len(state.players[2].hand)
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=unison)

    legal = [a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL]
    assert len(legal) == 2

    plus_action = next(
        a
        for a in legal
        if a.effect_choice
        and any(
            reg.effect_id == a.effect_choice
            and reg.handler_id == "activate_bottom_deck_up_to_n_opponent_battle_then_switch_self_active_at_turn_end"
            for reg in state.effect_registry
        )
    )
    state_plus = engine.apply_action(state, plus_action)
    state_plus = engine.apply_action(state_plus, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert not state_plus.players[2].battle_area
    state_plus = engine.apply_action(state_plus, Action(action_type=ActionType.END_TURN, player_id=1))
    assert state_plus.players[1].unison_area[0].resting is False

    zero_action = next(
        a
        for a in legal
        if a.effect_choice
        and any(
            reg.effect_id == a.effect_choice
            and reg.handler_id == "activate_opponent_bottom_decks_n_from_hand_and_switch_up_to_n_owner_energy_active_at_turn_end"
            for reg in state.effect_registry
        )
    )
    state_zero = engine.apply_action(state, zero_action)
    state_zero = engine.apply_action(state_zero, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state_zero.players[2].hand) == opponent_hand_before - 1
    state_zero = engine.apply_action(state_zero, Action(action_type=ActionType.END_TURN, player_id=1))
    assert state_zero.players[1].energy[0].resting is False


def test_phase4_frieza_unrestricted_power_activate_main_buffs_self_and_reduces_opponent() -> None:
    engine = RulesEngine(
        skill_cost_rules={
            8881: {
                "activate_main": [
                    {"kind": "discard_hand", "amount": 1},
                ]
            }
        },
        effect_rules={
            8881: (
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_self_gain_power_and_reduce_up_to_n_opponent_battle_for_turn",
                    handler_params={
                        "self_power_delta": 10000,
                        "target_power_delta": -20000,
                        "max_targets": 1,
                        "target_policy": "first",
                    },
                    family_id="self_activate_main:activate_self_gain_power_and_reduce_up_to_n_opponent_battle_for_turn",
                    provenance="test",
                ),
            )
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=991100,
        card_id=8881,
        owner_id=1,
        card_type="Z-BATTLE",
        color="Red",
        power=30000,
        has_activate_main=True,
    )
    fodder = CardInstance(instance_id=991101, card_id=88811, owner_id=1, card_type="BATTLE", color="Red")
    target = CardInstance(
        instance_id=991102,
        card_id=88812,
        owner_id=2,
        card_type="BATTLE",
        color="Yellow",
        power=20000,
    )
    state.players[1].battle_area.append(source)
    state.players[1].hand = [fodder]
    state.players[2].battle_area.append(target)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    activate = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert not state.players[1].hand
    assert state.players[1].battle_area[0].temporary_power_delta == 10000
    assert state.players[2].battle_area[0].temporary_power_delta == -20000
    assert any(cp.name == "effect_activate_self_gain_power_and_reduce_up_to_n_opponent_battle_for_turn" for cp in state.checkpoints)


def test_phase4_fused_zamasu_god_of_despair_activate_main_uses_spirit_boost_and_restands() -> None:
    engine = RulesEngine(
        skill_cost_rules={
            9720: {
                "activate_main": [
                    {"kind": "remove_owner_unison_markers", "amount": 1},
                    {"kind": "send_owner_drop_to_warp", "amount": 3},
                ]
            }
        },
        effect_rules={
            9720: (
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_switch_self_active_and_gain_power_for_turn",
                    handler_params={},
                    family_id="self_activate_main:activate_switch_self_active_and_gain_power_for_turn",
                    provenance="test",
                    limit_per_turn=1,
                ),
            )
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=991110,
        card_id=9720,
        owner_id=1,
        card_type="Z-BATTLE",
        color="Black",
        power=30000,
        resting=True,
        has_activate_main=True,
    )
    marker_source = CardInstance(
        instance_id=991111,
        card_id=97201,
        owner_id=1,
        card_type="UNISON",
        color="Black",
        markers=1,
    )
    state.players[1].battle_area.append(source)
    state.players[1].unison_area.append(marker_source)
    state.players[1].drop = [
        CardInstance(instance_id=991112 + i, card_id=97210 + i, owner_id=1, card_type="BATTLE", color="Black")
        for i in range(3)
    ]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)

    activate = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert state.players[1].battle_area[0].resting is False
    assert not state.players[1].unison_area
    assert any(cp.name == "rule_unison_zero_markers" for cp in state.checkpoints)
    assert len(state.players[1].drop) == 1
    assert len(state.players[1].warp) == 3
    assert any(cp.name == "effect_activate_switch_self_active_and_gain_power_for_turn" for cp in state.checkpoints)


def test_phase4_justice_impact_field_auto_and_activate_main_board_wipe() -> None:
    engine = RulesEngine(
        skill_cost_rules={
            8385: {
                "activate_main": [
                    {"kind": "send_owner_energy_to_drop", "amount": 2},
                ]
            }
        },
        effect_rules={
            8385: (
                EffectRule(
                    trigger="self_field_extra_placed",
                    handler_id="auto_switch_up_to_n_owner_leader_active_on_field_extra_placed",
                    handler_params={
                        "max_targets": 1,
                        "allowed_colors": "blue",
                        "required_traits": "red ribbon army",
                    },
                    family_id="self_field_extra_placed:auto_switch_up_to_n_owner_leader_active_on_field_extra_placed",
                    provenance="test",
                ),
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_remove_self_and_ko_all_opponent_battles",
                    handler_params={},
                    family_id="self_activate_main:activate_remove_self_and_ko_all_opponent_battles",
                    provenance="test",
                ),
            )
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Blue"
    state.players[1].leader_area.traits = ("Red Ribbon Army",)
    state.players[1].leader_area.resting = True
    stage = CardInstance(
        instance_id=991120,
        card_id=8385,
        owner_id=1,
        card_type="Z-EXTRA",
        color="Blue/Green",
        keywords=("Field",),
        has_activate_main=True,
    )
    state.players[1].battle_area.append(stage)
    state.players[1].energy = [
        CardInstance(instance_id=991121 + i, card_id=83850 + i, owner_id=1, card_type="BATTLE", color="Blue", resting=True)
        for i in range(2)
    ]
    state.players[2].battle_area = [
        CardInstance(instance_id=991130 + i, card_id=83860 + i, owner_id=2, card_type="BATTLE", color="Yellow", power=15000)
        for i in range(2)
    ]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=stage)

    engine._emit_effect_event(
        state,
        name="field_extra_placed",
        actor_player_id=1,
        payload={"source_instance_id": 991120, "source_card_id": 8385},
    )
    engine._resolve_pending_effects(state)
    assert state.players[1].leader_area.resting is False

    activate = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL)
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert not state.players[2].battle_area
    assert not state.players[1].battle_area
    assert any(card.instance_id == 991120 for card in state.players[1].removed_from_game)
    assert len(state.players[1].energy) == 0
    assert any(cp.name == "effect_activate_remove_self_and_ko_all_opponent_battles" for cp in state.checkpoints)


def test_phase4_self_attacks_can_combo_matching_card_from_warp_with_skills_negated() -> None:
    engine = RulesEngine(
        effect_rules={
            8326: (
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_combo_up_to_n_from_owner_zone_on_attack",
                    handler_params={
                        "max_targets": 1,
                        "source_zone": "warp",
                        "allowed_colors": "black",
                        "required_card_type": "BATTLE",
                        "exact_combo_power": 5000,
                        "negate_skills": True,
                        "target_policy": "first",
                    },
                    family_id="self_attacks:auto_combo_up_to_n_from_owner_zone_on_attack",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    shroom = CardInstance(instance_id=991140, card_id=8326, owner_id=1, card_type="BATTLE", color="Black", power=15000)
    state.players[1].battle_area.append(shroom)
    state.players[1].warp = [
        CardInstance(instance_id=991141, card_id=83260, owner_id=1, card_type="BATTLE", color="Black", combo_power=5000, power=5000),
        CardInstance(instance_id=991142, card_id=83261, owner_id=1, card_type="BATTLE", color="Blue", combo_power=5000, power=5000),
    ]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=shroom)

    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": 991140, "attacker_zone": "battle"},
    )
    engine._resolve_pending_effects(state)

    assert any(card.instance_id == 991141 for card in state.players[1].combo_area)
    assert all(card.instance_id != 991142 for card in state.players[1].combo_area)
    assert all(card.instance_id != 991141 for card in state.players[1].warp)
    assert state.players[1].combo_area[0].temporary_skills_negated is True
    assert any(cp.name == "effect_auto_combo_up_to_n_from_owner_zone_on_attack" for cp in state.checkpoints)


def test_phase4_self_attacks_can_gain_power_per_owner_warp_count() -> None:
    engine = RulesEngine(
        effect_rules={
            7029: (
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_self_gain_power_for_turn_on_attack",
                    handler_params={"power_delta": "expr:owner_warp_count*5000"},
                    family_id="self_attacks:auto_self_gain_power_for_turn_on_attack",
                    provenance="test",
                ),
            )
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    mira = CardInstance(instance_id=991150, card_id=7029, owner_id=1, card_type="BATTLE", color="Black", power=30000)
    state.players[1].battle_area.append(mira)
    state.players[1].warp = [
        CardInstance(instance_id=991151 + i, card_id=70290 + i, owner_id=1, card_type="BATTLE", color="Black")
        for i in range(3)
    ]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=mira)

    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": 991150, "attacker_zone": "battle"},
    )
    engine._resolve_pending_effects(state)

    assert state.players[1].battle_area[0].power == 45000
    assert state.players[1].battle_area[0].temporary_power_delta == 15000
    assert any(cp.name == "effect_auto_self_gain_power_for_turn_on_attack" for cp in state.checkpoints)


def test_phase4_no_challenge_for_the_strong_can_remove_self_and_prevent_leader_damage_for_battle() -> None:
    engine = RulesEngine(
        effect_rule_overrides={
            7839: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "owner_opponent_card_attacks",
                        "handler_id": "auto_remove_self_prevent_leader_damage_and_battle_ko_for_battle",
                        "handler_params": {},
                        "limit_per_turn": 1,
                        "limit_scope": "source_instance",
                    },
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].leader_area.characters = ("Gogeta: GT",)
    no_challenge = CardInstance(instance_id=991201, card_id=7839, owner_id=2, card_type="Z-EXTRA")
    attacker = CardInstance(instance_id=991202, card_id=9202, owner_id=1, card_type="BATTLE", power=20000)
    state.players[2].battle_area.append(no_challenge)
    state.players[1].battle_area.append(attacker)
    engine._register_card_effects(state, player_id=2, source_zone="battle", card=no_challenge)
    starting_life = len(state.players[2].life)
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=991202,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.DAMAGE
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={
            "attacker_instance_id": 991202,
            "attacker_zone": "battle",
            "target_player_id": 2,
            "target_zone": "leader",
        },
    )
    engine._resolve_pending_effects(state)
    assert any(card.instance_id == 991201 for card in state.players[2].removed_from_game)
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    assert len(state.players[2].life) == starting_life
    assert any(cp.name == "effect_auto_remove_self_prevent_leader_damage_and_battle_ko_for_battle" for cp in state.checkpoints)


def test_phase4_android_21_in_the_name_of_hunger_can_add_top_deck_to_energy_and_bottom_deck_opponent_battle(repo) -> None:
    engine = RulesEngine(
        card_repository=repo,
        effect_rule_overrides={
            1702: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "self_played",
                        "handler_id": "auto_add_top_deck_to_energy_rest_and_bottom_deck_up_to_n_opponent_battle_on_play",
                        "handler_params": {"max_targets": 1},
                    }
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[
            990301,
            990302,
            990303,
            990304,
            990305,
            990306,
            990307,
            990308,
            990309,
            990310,
            990311,
            990312,
            990313,
            990314,
            990315,
            990316,
        ],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=990304, card_id=1702, owner_id=1, card_type="Z-BATTLE", power=20000)
    target = CardInstance(instance_id=990305, card_id=9305, owner_id=2, card_type="BATTLE", power=15000, energy_cost=3)
    state.players[1].battle_area.append(source)
    state.players[2].battle_area.append(target)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990304, "source_card_id": 1702, "source_zone": "battle", "played_from": "hand"},
    )
    engine._resolve_pending_effects(state)

    assert state.players[1].energy and state.players[1].energy[0].card_id == 990315
    assert state.players[1].energy[0].resting is True
    assert all(card.instance_id != 990305 for card in state.players[2].battle_area)
    assert state.players[2].deck[-1] == 9305
    assert any(cp.name == "effect_auto_add_top_deck_to_energy_rest_and_bottom_deck_up_to_n_opponent_battle_on_play" for cp in state.checkpoints)


def test_phase4_android_21_in_the_name_of_hunger_can_gain_keyword_from_under_self(repo) -> None:
    engine = RulesEngine(
        card_repository=repo,
        effect_rule_overrides={
            1702: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "self_activate_main",
                        "handler_id": "activate_gain_keyword_from_under_self_until_opponent_turn_end",
                        "handler_params": {"min_source_stacked_cards": 1},
                        "once_per_turn": True,
                    }
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=990306, card_id=1702, owner_id=1, card_type="Z-BATTLE", power=20000, stacked_card_ids=(1702,))
    state.players[1].battle_area.append(source)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    engine._emit_effect_event(
        state,
        name="skill_activated",
        actor_player_id=1,
        payload={"source_instance_id": 990306, "source_card_id": 1702, "skill_kind": "activate_main"},
    )
    engine._resolve_pending_effects(state)

    assert "Blocker" in source.delayed_temporary_keywords
    assert any(row.target_instance_id == 990306 and row.keyword == "Blocker" for row in state.delayed_keyword_clears)
    assert any(cp.name == "effect_activate_gain_keyword_from_under_self_until_opponent_turn_end" for cp in state.checkpoints)


def test_phase4_stone_transformation_nightmare_can_negate_and_restrict_attacking_battle() -> None:
    engine = RulesEngine(
        effect_rule_overrides={
            7786: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "owner_opponent_card_attacks",
                        "handler_id": "auto_negate_skills_and_restrict_up_to_n_opponent_battle_on_attack",
                        "handler_params": {"max_targets": 1, "marker_delta": -1},
                    }
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=990307, card_id=7786, owner_id=2, card_type="Z-UNISON", markers=1, power=20000)
    attacker = CardInstance(instance_id=990308, card_id=9308, owner_id=1, card_type="BATTLE", power=20000)
    state.players[2].unison_area.append(source)
    state.players[1].battle_area.append(attacker)
    engine._register_card_effects(state, player_id=2, source_zone="unison", card=source)
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=990308,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": 990308, "attacker_zone": "battle", "target_player_id": 2, "target_zone": "leader"},
    )
    engine._resolve_pending_effects(state)

    assert source.markers == 0
    assert attacker.temporary_skills_negated is True
    assert 990308 in state.attack_restricted_instance_ids
    assert any(cp.name == "effect_auto_negate_skills_and_restrict_up_to_n_opponent_battle_on_attack" for cp in state.checkpoints)


def test_phase4_stone_transformation_nightmare_can_bottom_deck_opponent_battle_and_ready_mono_blue_energy() -> None:
    engine = RulesEngine(
        effect_rule_overrides={
            7786: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "self_activate_main",
                        "handler_id": "activate_bottom_deck_up_to_n_opponent_battle_then_switch_up_to_n_owner_energy_active_at_turn_end",
                        "handler_params": {
                            "max_targets": 1,
                            "ignores_barrier": True,
                            "owner_energy_targets": 1,
                            "allowed_colors": "blue",
                            "require_mono_color": True,
                            "marker_delta": -1,
                        },
                    }
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=990309, card_id=7786, owner_id=1, card_type="Z-UNISON", markers=1, power=20000)
    energy = CardInstance(instance_id=990310, card_id=9310, owner_id=1, card_type="BATTLE", color="Blue", resting=True)
    target = CardInstance(instance_id=990311, card_id=9311, owner_id=2, card_type="BATTLE", power=20000)
    state.players[1].unison_area.append(source)
    state.players[1].energy.append(energy)
    state.players[2].battle_area.append(target)
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)
    engine._emit_effect_event(
        state,
        name="skill_activated",
        actor_player_id=1,
        payload={"source_instance_id": 990309, "source_card_id": 7786, "skill_kind": "activate_main"},
    )
    engine._resolve_pending_effects(state)
    engine._apply_due_delayed_active_switches(state, trigger_player_id=1)

    assert source.markers == 0
    assert all(card.instance_id != 990311 for card in state.players[2].battle_area)
    assert state.players[2].deck[-1] == 9311
    assert energy.resting is False
    assert any(cp.name == "effect_activate_bottom_deck_up_to_n_opponent_battle_then_switch_up_to_n_owner_energy_active_at_turn_end" for cp in state.checkpoints)


def test_phase4_haze_shenron_can_rest_opponent_cards_on_play_and_attack_and_place_drop_under_assembled(repo) -> None:
    engine = RulesEngine(
        card_repository=repo,
        effect_rule_overrides={
            7848: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "self_played",
                        "handler_id": "auto_switch_up_to_n_opponent_board_rest",
                        "handler_params": {"max_targets": 1},
                    },
                    {
                        "trigger": "self_attacks",
                        "handler_id": "auto_switch_up_to_n_opponent_board_rest",
                        "handler_params": {"max_targets": 1, "prefer_attacker": True},
                    },
                    {
                        "trigger": "owner_card_comboed",
                        "handler_id": "auto_place_up_to_n_from_owner_drop_under_named_owner_battle_on_combo",
                        "handler_params": {
                            "max_targets": 1,
                            "host_name_contains": "7 SHADOW DRAGONS ASSEMBLED",
                            "allowed_colors": "yellow",
                            "required_traits": "shadow dragon",
                            "event_allowed_colors": "yellow",
                            "event_required_traits": "shadow dragon",
                            "requires_leader": "yellow <Nuova Shenron>",
                        },
                        "limit_per_turn": 1,
                    },
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=7845,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.characters = ("Nuova Shenron",)
    source = CardInstance(instance_id=990312, card_id=7848, owner_id=1, card_type="Z-BATTLE", color="Yellow", power=15000, traits=("Shadow Dragon",))
    host = CardInstance(instance_id=990313, card_id=7849, owner_id=1, card_type="Z-EXTRA", color="Yellow")
    combo_drop = CardInstance(instance_id=990314, card_id=7848, owner_id=1, card_type="Z-BATTLE", color="Yellow", traits=("Shadow Dragon",))
    combo_source = CardInstance(instance_id=990317, card_id=7848, owner_id=1, card_type="Z-BATTLE", color="Yellow", traits=("Shadow Dragon",))
    unison_target = CardInstance(instance_id=990315, card_id=9315, owner_id=2, card_type="UNISON", power=15000)
    battle_target = CardInstance(instance_id=990316, card_id=9316, owner_id=2, card_type="BATTLE", power=15000)
    state.players[1].battle_area.extend([source, host])
    state.players[1].drop.append(combo_drop)
    state.players[1].combo_area.append(combo_source)
    state.players[2].unison_area.append(unison_target)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990312, "source_card_id": 7848, "source_zone": "battle", "played_from": "hand"},
    )
    engine._resolve_pending_effects(state)
    assert unison_target.resting is True

    state.players[2].battle_area.append(battle_target)
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=990312,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": 990312, "attacker_zone": "battle", "target_player_id": 2, "target_zone": "leader"},
    )
    engine._resolve_pending_effects(state)
    assert battle_target.resting is True

    engine._emit_effect_event(
        state,
        name="card_comboed",
        actor_player_id=1,
        payload={"source_instance_id": 990317, "source_card_id": 7848, "source_zone": "combo"},
    )
    engine._resolve_pending_effects(state)

    assert host.stacked_card_ids == (7848,)
    assert all(card.instance_id != 990314 for card in state.players[1].drop)
    assert any(cp.name == "effect_auto_place_up_to_n_from_owner_drop_under_named_owner_battle_on_combo" for cp in state.checkpoints)


def test_phase4_nappa_demolition_man_can_play_self_at_battle_end_after_combo(repo) -> None:
    engine = RulesEngine(
        card_repository=repo,
        effect_rule_overrides={
            6947: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "self_comboed_battle_end",
                        "handler_id": "auto_play_self_from_combo_on_battle_end",
                        "handler_params": {"requires_leader": "red,green"},
                    }
                ],
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Red"
    combo_card = CardInstance(
        instance_id=990318,
        card_id=6947,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        power=10000,
        combo_power=10000,
    )
    state.players[1].combo_area.append(combo_card)
    engine._register_card_effects(state, player_id=1, source_zone="combo", card=combo_card)
    engine._emit_effect_event(
        state,
        name="card_comboed",
        actor_player_id=1,
        payload={"source_instance_id": 990318, "source_card_id": 6947, "source_zone": "combo"},
    )
    engine._resolve_pending_effects(state)
    engine._emit_effect_event(state, name="battle_end", actor_player_id=1, payload={})
    engine._resolve_pending_effects(state)

    assert any(card.instance_id == 990318 for card in state.players[1].battle_area)
    assert any(cp.name == "effect_auto_play_self_from_combo_on_battle_end" for cp in state.checkpoints)


def test_phase4_pan_buffs_played_battle_and_draws_if_threshold_reached() -> None:
    engine = RulesEngine(
        effect_rule_overrides={
            1063: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "owner_other_battle_played",
                        "handler_id": "auto_buff_played_battle_and_draw_if_power_at_least",
                        "handler_params": {"power_delta": 5000, "draw_if_power_at_least": 20000},
                        "once_per_turn": True,
                    }
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1063,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    played = CardInstance(instance_id=990319, card_id=9319, owner_id=1, card_type="BATTLE", color="Yellow", power=15000)
    state.players[1].battle_area.append(played)
    engine._register_card_effects(state, player_id=1, source_zone="leader", card=state.players[1].leader_area)
    starting_hand = len(state.players[1].hand)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990319, "source_card_id": 9319, "source_zone": "battle", "played_from": "hand"},
    )
    engine._resolve_pending_effects(state)

    assert played.power == 20000
    assert played.temporary_power_delta == 5000
    assert len(state.players[1].hand) == starting_hand + 1
    assert any(cp.name == "effect_auto_buff_played_battle_and_draw_if_power_at_least" for cp in state.checkpoints)


def test_phase4_krillin_wish_after_conflict_can_bottom_deck_small_opponent_battle() -> None:
    engine = RulesEngine(
        effect_rule_overrides={
            7908: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "self_activate_main",
                        "handler_id": "activate_bottom_deck_up_to_n_opponent_battle",
                        "handler_params": {"max_targets": 1, "max_cost": 5, "marker_delta": 2},
                    }
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=990320, card_id=7908, owner_id=1, card_type="Z-UNISON", markers=0, power=15000)
    target = CardInstance(instance_id=990321, card_id=9321, owner_id=2, card_type="BATTLE", power=15000, energy_cost=5)
    state.players[1].unison_area.append(source)
    state.players[2].battle_area.append(target)
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)
    engine._emit_effect_event(
        state,
        name="skill_activated",
        actor_player_id=1,
        payload={"source_instance_id": 990320, "source_card_id": 7908, "skill_kind": "activate_main"},
    )
    engine._resolve_pending_effects(state)

    assert source.markers == 2
    assert all(card.instance_id != 990321 for card in state.players[2].battle_area)
    assert state.players[2].deck[-1] == 9321
    assert any(cp.name == "effect_activate_bottom_deck_up_to_n_opponent_battle" for cp in state.checkpoints)


def test_phase4_demigras_wormhole_can_mill_on_play_and_removed_and_play_from_warp() -> None:
    engine = RulesEngine(
        effect_rule_overrides={
            8323: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "self_played",
                        "handler_id": "auto_place_top_n_from_owner_deck_into_drop",
                        "handler_params": {"amount": 2, "requires_leader": "black"},
                    },
                    {
                        "trigger": "self_removed_from_game",
                        "handler_id": "auto_place_top_n_from_owner_deck_into_drop",
                        "handler_params": {"amount": 2, "requires_leader": "black"},
                    },
                    {
                        "trigger": "self_activate_main",
                        "handler_id": "activate_play_up_to_n_from_owner_warp",
                        "handler_params": {
                            "max_targets": 1,
                            "allowed_colors": "black",
                            "required_card_type": "BATTLE",
                            "max_cost": 5,
                            "required_skill_text_contains": "dark over realm",
                            "required_owner_battle_skill_text_contains": "dark over realm",
                            "negate_skills": True,
                            "requires_leader": "black",
                        },
                        "limit_per_turn": 1,
                    },
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Black"
    source = CardInstance(instance_id=990410, card_id=8323, owner_id=1, card_type="Z-EXTRA", color="Black", skill_text_raw="[Auto][Activate: Main]")
    dark_over_realm_body = CardInstance(
        instance_id=990411,
        card_id=8324,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        energy_cost=4,
        skill_text_raw="[Dark Over Realm 4]",
    )
    warp_body = CardInstance(
        instance_id=990412,
        card_id=8325,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        energy_cost=5,
        skill_text_raw="[Dark Over Realm 5][Auto] test",
        has_auto=True,
    )
    state.players[1].battle_area.extend([source, dark_over_realm_body])
    state.players[1].warp.append(warp_body)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    deck_before = len(state.players[1].deck)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990410, "source_card_id": 8323, "source_zone": "battle"},
    )
    engine._resolve_pending_effects(state)
    assert len(state.players[1].deck) == deck_before - 2
    assert len(state.players[1].drop) >= 2

    removed_before = len(state.players[1].drop)
    engine._emit_effect_event(
        state,
        name="card_removed_from_game",
        actor_player_id=1,
        payload={"source_instance_id": 990410, "source_card_id": 8323, "source_zone": "battle", "owner_player_id": 1},
    )
    engine._resolve_pending_effects(state)
    assert len(state.players[1].drop) >= removed_before + 2

    engine._emit_effect_event(
        state,
        name="skill_activated",
        actor_player_id=1,
        payload={"source_instance_id": 990410, "source_card_id": 8323, "source_zone": "battle", "skill_kind": "activate_main"},
    )
    engine._resolve_pending_effects(state)
    played = next(card for card in state.players[1].battle_area if card.instance_id == 990412)
    assert played.has_auto is False
    assert any(cp.name == "effect_activate_play_up_to_n_from_owner_warp" for cp in state.checkpoints)


def test_phase4_dark_over_realm_action_can_play_from_hand_and_trigger_dark_over_realm_auto() -> None:
    engine = RulesEngine(
        effect_rules={
            999301: [
                {
                    "trigger": "owner_other_battle_played_by_dark_over_realm",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    watcher = CardInstance(
        instance_id=990430,
        card_id=999301,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_auto=True,
        skill_text_raw="[Auto] When your Battle Card other than this card is played by a [Dark Over Realm] skill, draw 1 card.",
    )
    arrival = CardInstance(
        instance_id=990431,
        card_id=999302,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        energy_cost=4,
        skill_text_raw="[Dark Over Realm 4]{b}",
    )
    state.players[1].battle_area = [watcher]
    state.players[1].hand = [arrival]
    state.players[1].energy = [CardInstance(instance_id=990432, card_id=9301, owner_id=1, card_type="BATTLE", color="Black")]
    state.players[1].drop = [
        CardInstance(instance_id=990433 + i, card_id=9310 + i, owner_id=1, card_type="BATTLE", color="Black")
        for i in range(4)
    ]
    deck_before = len(state.players[1].deck)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=watcher)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DARK_OVER_REALM)
    state = engine.apply_action(state, action)
    assert state.counter_window is not None
    assert any(cp.name == "dark_over_realm_declared" for cp in state.checkpoints)
    assert len(state.players[1].warp) == 4
    assert not state.players[1].drop
    assert state.players[1].energy[0].resting is True

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(card.instance_id == 990431 for card in state.players[1].battle_area)
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_over_realm_action_can_play_from_hand_and_trigger_over_realm_auto() -> None:
    engine = RulesEngine(
        effect_rule_overrides={
            999311: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "owner_other_battle_played_by_over_realm",
                        "handler_id": "auto_draw_n",
                        "handler_params": {"amount": 1},
                    }
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    watcher = CardInstance(
        instance_id=990440,
        card_id=999311,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        has_auto=True,
        skill_text_raw="[Auto] When your Battle Card other than this card is played by an [Over Realm] skill, draw 1 card.",
    )
    arrival = CardInstance(
        instance_id=990441,
        card_id=999312,
        owner_id=1,
        card_type="BATTLE",
        color="Black",
        energy_cost=5,
        skill_text_raw="[Over Realm 3](Black)(Black)",
    )
    state.players[1].battle_area = [watcher]
    state.players[1].hand = [arrival]
    state.players[1].energy = [
        CardInstance(instance_id=990442, card_id=9311, owner_id=1, card_type="BATTLE", color="Black"),
        CardInstance(instance_id=990443, card_id=9312, owner_id=1, card_type="BATTLE", color="Black"),
    ]
    state.players[1].drop = [
        CardInstance(instance_id=990444 + i, card_id=9320 + i, owner_id=1, card_type="BATTLE", color="Black")
        for i in range(3)
    ]
    deck_before = len(state.players[1].deck)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=watcher)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.OVER_REALM)
    state = engine.apply_action(state, action)
    assert state.counter_window is not None
    assert any(cp.name == "over_realm_declared" for cp in state.checkpoints)
    assert len(state.players[1].warp) == 3
    assert not state.players[1].drop
    assert all(card.resting is True for card in state.players[1].energy)

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(card.instance_id == 990441 for card in state.players[1].battle_area)
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_arrival_action_can_play_during_battle_after_matching_combo() -> None:
    engine = RulesEngine(
        effect_rules={
            999321: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    combo_card = CardInstance(
        instance_id=990450,
        card_id=9331,
        owner_id=1,
        card_type="BATTLE",
        color="Red/Green",
        combo_cost=0,
        combo_power=5000,
    )
    arrival = CardInstance(
        instance_id=990451,
        card_id=999321,
        owner_id=1,
        card_type="BATTLE",
        color="Red/Green",
        energy_cost=4,
        skill_text_raw="[Arrival Red/Green](Green)\n[Auto] When this card is played, draw 1 card.",
    )
    attacker = CardInstance(
        instance_id=990453,
        card_id=9333,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        energy_cost=1,
        power=15000,
    )
    state.players[1].hand = [combo_card, arrival]
    state.players[1].energy = [CardInstance(instance_id=990452, card_id=9332, owner_id=1, card_type="BATTLE", color="Green")]
    state.players[1].battle_area = [attacker]
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.OFFENSE
    deck_before = len(state.players[1].deck)
    assert not any(a.action_type == ActionType.ARRIVAL for a in engine.get_legal_actions(state, 1))

    combo_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo_action)
    arrival_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ARRIVAL)
    state = engine.apply_action(state, arrival_action)
    assert state.counter_window is not None
    assert any(cp.name == "arrival_declared" for cp in state.checkpoints)
    assert state.players[1].energy[0].resting is True

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert state.battle_step == BattleStep.OFFENSE
    assert state.attack_context is not None
    assert any(card.instance_id == 990451 for card in state.players[1].battle_area)
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_arrival_action_supports_slash_separated_cost_tokens() -> None:
    engine = RulesEngine(
        effect_rules={
            999322: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    combo_card = CardInstance(
        instance_id=990460,
        card_id=9341,
        owner_id=1,
        card_type="BATTLE",
        color="Red/Yellow",
        combo_cost=0,
        combo_power=5000,
    )
    arrival = CardInstance(
        instance_id=990461,
        card_id=999322,
        owner_id=1,
        card_type="BATTLE",
        color="Red/Yellow",
        energy_cost=4,
        skill_text_raw="[Arrival Red/Yellow](Red)/(Yellow)\n[Auto] When this card is played, draw 1 card.",
    )
    attacker = CardInstance(
        instance_id=990462,
        card_id=9342,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        energy_cost=1,
        power=15000,
    )
    state.players[1].hand = [combo_card, arrival]
    state.players[1].energy = [
        CardInstance(instance_id=990463, card_id=9343, owner_id=1, card_type="BATTLE", color="Red"),
        CardInstance(instance_id=990464, card_id=9344, owner_id=1, card_type="BATTLE", color="Yellow"),
    ]
    state.players[1].battle_area = [attacker]
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.OFFENSE
    deck_before = len(state.players[1].deck)

    combo_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo_action)
    arrival_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ARRIVAL)
    state = engine.apply_action(state, arrival_action)
    assert state.counter_window is not None
    assert any(cp.name == "arrival_declared" for cp in state.checkpoints)
    assert all(card.resting is True for card in state.players[1].energy)

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(card.instance_id == 990461 for card in state.players[1].battle_area)
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_arrival_action_supports_brace_color_cost_tokens() -> None:
    engine = RulesEngine(
        effect_rules={
            999323: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    combo_card = CardInstance(
        instance_id=990470,
        card_id=9351,
        owner_id=1,
        card_type="BATTLE",
        color="Red/Green",
        combo_cost=0,
        combo_power=5000,
    )
    arrival = CardInstance(
        instance_id=990471,
        card_id=999323,
        owner_id=1,
        card_type="BATTLE",
        color="Red/Green",
        energy_cost=4,
        skill_text_raw="[Arrival Red/Green]{r}\n[Auto] When this card is played, draw 1 card.",
    )
    attacker = CardInstance(
        instance_id=990472,
        card_id=9352,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        energy_cost=1,
        power=15000,
    )
    state.players[1].hand = [combo_card, arrival]
    state.players[1].energy = [CardInstance(instance_id=990473, card_id=9353, owner_id=1, card_type="BATTLE", color="Red")]
    state.players[1].battle_area = [attacker]
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.OFFENSE
    deck_before = len(state.players[1].deck)

    combo_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo_action)
    arrival_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ARRIVAL)
    state = engine.apply_action(state, arrival_action)
    assert state.counter_window is not None
    assert state.players[1].energy[0].resting is True

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(card.instance_id == 990471 for card in state.players[1].battle_area)
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_arrival_action_supports_mixed_specified_and_circled_numeric_cost() -> None:
    engine = RulesEngine(
        effect_rules={
            999324: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    combo_card = CardInstance(
        instance_id=990480,
        card_id=9361,
        owner_id=1,
        card_type="BATTLE",
        color="Green/Yellow",
        combo_cost=0,
        combo_power=5000,
    )
    arrival = CardInstance(
        instance_id=990481,
        card_id=999324,
        owner_id=1,
        card_type="BATTLE",
        color="Green/Yellow",
        energy_cost=5,
        skill_text_raw="[Arrival Green/Yellow](Yellow)②\n[Auto] When this card is played, draw 1 card.",
    )
    attacker = CardInstance(
        instance_id=990482,
        card_id=9362,
        owner_id=1,
        card_type="BATTLE",
        color="Green",
        energy_cost=1,
        power=15000,
    )
    state.players[1].hand = [combo_card, arrival]
    state.players[1].energy = [
        CardInstance(instance_id=990483, card_id=9363, owner_id=1, card_type="BATTLE", color="Yellow"),
        CardInstance(instance_id=990484, card_id=9364, owner_id=1, card_type="BATTLE", color="Green"),
        CardInstance(instance_id=990485, card_id=9365, owner_id=1, card_type="BATTLE", color="Black"),
    ]
    state.players[1].battle_area = [attacker]
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.OFFENSE
    deck_before = len(state.players[1].deck)

    combo_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo_action)
    arrival_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ARRIVAL)
    state = engine.apply_action(state, arrival_action)
    assert state.counter_window is not None
    assert all(card.resting is True for card in state.players[1].energy)

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(card.instance_id == 990481 for card in state.players[1].battle_area)
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_arrival_action_respects_header_level_leader_name_gate() -> None:
    engine = RulesEngine(
        effect_rules={
            999325: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    combo_card = CardInstance(
        instance_id=990490,
        card_id=9371,
        owner_id=1,
        card_type="BATTLE",
        color="Red/Yellow",
        combo_cost=0,
        combo_power=5000,
    )
    arrival = CardInstance(
        instance_id=990491,
        card_id=999325,
        owner_id=1,
        card_type="BATTLE",
        color="Red/Yellow",
        energy_cost=4,
        skill_text_raw="[Arrival Red/Yellow]{y}, if your Leader is {Super Baby 2, Awakened Malevolence} :\n[Auto] When this card is played, draw 1 card.",
    )
    attacker = CardInstance(
        instance_id=990492,
        card_id=9372,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        energy_cost=1,
        power=15000,
    )
    state.players[1].hand = [combo_card, arrival]
    state.players[1].energy = [CardInstance(instance_id=990493, card_id=9373, owner_id=1, card_type="BATTLE", color="Yellow")]
    state.players[1].battle_area = [attacker]
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.OFFENSE
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="Wrong Leader", color="Yellow")

    combo_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo_action)
    assert not any(a.action_type == ActionType.ARRIVAL for a in engine.get_legal_actions(state, 1))

    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="Super Baby 2, Awakened Malevolence", color="Yellow")
    arrival_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ARRIVAL)
    state = engine.apply_action(state, arrival_action)
    assert state.counter_window is not None
    assert any(cp.name == "arrival_declared" for cp in state.checkpoints)

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(card.instance_id == 990491 for card in state.players[1].battle_area)
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_arrival_action_respects_mixed_header_requirements() -> None:
    engine = RulesEngine(
        effect_rules={
            999326: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    attacker = CardInstance(
        instance_id=990500,
        card_id=9381,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        energy_cost=1,
        power=15000,
    )
    combo_card = CardInstance(
        instance_id=990501,
        card_id=9382,
        owner_id=2,
        card_type="BATTLE",
        color="Blue/Yellow",
        combo_cost=0,
        combo_power=5000,
    )
    arrival = CardInstance(
        instance_id=990502,
        card_id=999326,
        owner_id=2,
        card_type="BATTLE",
        color="Blue/Yellow",
        energy_cost=4,
        skill_text_raw="[Arrival Blue/Yellow](Yellow), if your Leader is {Zen-Oh, One Who Wipes Away} and your opponent has 3 or more energy and it's your opponent's turn :\n[Auto] When this card is played, draw 1 card.",
    )
    state.players[1].battle_area = [attacker]
    state.players[1].energy = [
        CardInstance(instance_id=990503, card_id=9383, owner_id=1, card_type="BATTLE", color="Red"),
        CardInstance(instance_id=990504, card_id=9384, owner_id=1, card_type="BATTLE", color="Blue"),
    ]
    state.players[2].hand = [combo_card, arrival]
    state.players[2].energy = [CardInstance(instance_id=990505, card_id=9385, owner_id=2, card_type="BATTLE", color="Yellow")]
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.DEFENSE
    engine._card_cache[(2, "front")] = CardRuntimeData(card_name="Zen-Oh, One Who Wipes Away", color="Blue")

    combo_action = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo_action)
    assert not any(a.action_type == ActionType.ARRIVAL for a in engine.get_legal_actions(state, 2))

    state.players[1].energy.append(CardInstance(instance_id=990506, card_id=9386, owner_id=1, card_type="BATTLE", color="Yellow"))
    arrival_action = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.ARRIVAL)
    state = engine.apply_action(state, arrival_action)
    assert state.counter_window is not None
    assert any(cp.name == "arrival_declared" for cp in state.checkpoints)

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    assert any(card.instance_id == 990502 for card in state.players[2].battle_area)
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_arrival_action_supports_parenthetical_reminder_text_variant() -> None:
    engine = RulesEngine(
        effect_rules={
            999327: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    combo_card = CardInstance(
        instance_id=990510,
        card_id=9391,
        owner_id=1,
        card_type="BATTLE",
        color="Blue/Yellow",
        combo_cost=0,
        combo_power=5000,
    )
    arrival = CardInstance(
        instance_id=990511,
        card_id=999327,
        owner_id=1,
        card_type="BATTLE",
        color="Blue/Yellow",
        energy_cost=4,
        skill_text_raw="[Arrival Blue/Yellow] (Yellow) (Play this card from your hand when you have blue and yellow cards in your Combo Area.)\n[Auto] When this card is played, draw 1 card.",
    )
    attacker = CardInstance(
        instance_id=990512,
        card_id=9392,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        energy_cost=1,
        power=15000,
    )
    state.players[1].hand = [combo_card, arrival]
    state.players[1].energy = [CardInstance(instance_id=990513, card_id=9393, owner_id=1, card_type="BATTLE", color="Yellow")]
    state.players[1].battle_area = [attacker]
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.OFFENSE
    deck_before = len(state.players[1].deck)

    combo_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo_action)
    arrival_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ARRIVAL)
    state = engine.apply_action(state, arrival_action)
    assert state.counter_window is not None
    assert state.players[1].energy[0].resting is True

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(card.instance_id == 990511 for card in state.players[1].battle_area)
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_arrival_action_can_apply_header_draw_before_counter_window() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    combo_card = CardInstance(
        instance_id=990520,
        card_id=9401,
        owner_id=1,
        card_type="BATTLE",
        color="Blue/Yellow",
        combo_cost=0,
        combo_power=5000,
    )
    arrival = CardInstance(
        instance_id=990521,
        card_id=999328,
        owner_id=1,
        card_type="BATTLE",
        color="Blue/Yellow",
        energy_cost=4,
        skill_text_raw="[Arrival Blue/Yellow]{y}, draw 1 card:\n[Auto] When this card is played, choose up to 1 of your opponent's Battle Cards or Unisons and switch it to Rest Mode.",
    )
    attacker = CardInstance(
        instance_id=990522,
        card_id=9402,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        energy_cost=1,
        power=15000,
    )
    state.players[1].hand = [combo_card, arrival]
    state.players[1].energy = [CardInstance(instance_id=990523, card_id=9403, owner_id=1, card_type="BATTLE", color="Yellow")]
    state.players[1].battle_area = [attacker]
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.OFFENSE
    deck_before = len(state.players[1].deck)

    combo_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo_action)
    arrival_action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ARRIVAL)
    state = engine.apply_action(state, arrival_action)

    assert state.counter_window is not None
    assert len(state.players[1].deck) == deck_before - 1
    assert len(state.players[1].hand) == 2
    assert state.players[1].energy[0].resting is True

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(card.instance_id == 990521 for card in state.players[1].battle_area)
    assert len(state.players[1].hand) == 1


def test_phase4_aegis_action_can_discard_matching_colors_restand_energy_and_trigger_auto() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    attacker = CardInstance(
        instance_id=990530,
        card_id=9411,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        energy_cost=1,
        power=15000,
    )
    aegis_card = CardInstance(
        instance_id=990531,
        card_id=999329,
        owner_id=2,
        card_type="BATTLE",
        color="Blue/Yellow",
        power=20000,
        skill_text_raw="[Aegis Blue/Yellow][Once per turn] (If it's your opponent's turn, you can activate this during the Defense Step by placing cards in your hand in your Drop Area that match all colors specified by [Aegis]: Choose up to 2 of your energy and switch them to Active Mode.)",
    )
    blue_cost = CardInstance(
        instance_id=990532,
        card_id=9412,
        owner_id=2,
        card_type="BATTLE",
        color="Blue",
        combo_cost=0,
        combo_power=5000,
    )
    yellow_cost = CardInstance(
        instance_id=990533,
        card_id=9413,
        owner_id=2,
        card_type="BATTLE",
        color="Yellow",
        combo_cost=0,
        combo_power=5000,
    )
    resting_energy_1 = CardInstance(instance_id=990534, card_id=9414, owner_id=2, card_type="BATTLE", color="Blue", resting=True)
    resting_energy_2 = CardInstance(instance_id=990535, card_id=9415, owner_id=2, card_type="BATTLE", color="Yellow", resting=True)
    state.players[1].battle_area = [attacker]
    state.players[2].battle_area = [aegis_card]
    state.players[2].hand = [blue_cost, yellow_cost]
    state.players[2].energy = [resting_energy_1, resting_energy_2]
    state.effect_registry.append(
        EffectRegistration(
            effect_id=state.next_effect_id,
            owner_player_id=2,
            source_instance_id=aegis_card.instance_id,
            source_card_id=aegis_card.card_id,
            source_zone="battle",
            trigger="self_aegis_activated",
            handler_id="auto_draw_n",
            handler_params={"amount": 1},
        )
    )
    state.next_effect_id += 1
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.DEFENSE
    deck_before = len(state.players[2].deck)

    aegis_action = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.AEGIS)
    state = engine.apply_action(state, aegis_action)

    assert all(card.resting is False for card in state.players[2].energy)
    assert len(state.players[2].hand) == 1
    assert len(state.players[2].drop) == 2
    assert len(state.players[2].deck) == deck_before - 1
    assert any(cp.name == "aegis_activated" for cp in state.checkpoints)
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)
    assert not any(a.action_type == ActionType.AEGIS for a in engine.get_legal_actions(state, 2))


def test_phase4_aegis_action_can_switch_opponent_energy_to_rest() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    attacker = CardInstance(
        instance_id=990540,
        card_id=9421,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        energy_cost=1,
        power=15000,
    )
    aegis_card = CardInstance(
        instance_id=990541,
        card_id=999330,
        owner_id=2,
        card_type="BATTLE",
        color="Blue/Yellow",
        power=20000,
        skill_text_raw="[Aegis Blue/Yellow][Once per turn] (If it's your opponent's turn, you can activate this during the Defense Step by placing cards in your hand in your Drop Area that match all colors specified by [Aegis]: Choose up to 2 of your energy and switch them to Active Mode.)",
    )
    state.players[1].battle_area = [attacker]
    state.players[1].energy = [
        CardInstance(instance_id=990542, card_id=9422, owner_id=1, card_type="BATTLE", color="Blue", resting=False),
        CardInstance(instance_id=990543, card_id=9423, owner_id=1, card_type="BATTLE", color="Yellow", resting=False),
        CardInstance(instance_id=990544, card_id=9424, owner_id=1, card_type="BATTLE", color="Red", resting=False),
    ]
    state.players[2].battle_area = [aegis_card]
    state.players[2].hand = [
        CardInstance(instance_id=990545, card_id=9425, owner_id=2, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=990546, card_id=9426, owner_id=2, card_type="BATTLE", color="Yellow"),
    ]
    state.players[2].energy = [
        CardInstance(instance_id=990547, card_id=9427, owner_id=2, card_type="BATTLE", color="Blue", resting=True),
        CardInstance(instance_id=990548, card_id=9428, owner_id=2, card_type="BATTLE", color="Yellow", resting=True),
    ]
    state.effect_registry.append(
        EffectRegistration(
            effect_id=state.next_effect_id,
            owner_player_id=2,
            source_instance_id=aegis_card.instance_id,
            source_card_id=aegis_card.card_id,
            source_zone="battle",
            trigger="self_aegis_activated",
            handler_id="auto_switch_up_to_n_opponent_energy_rest_on_aegis",
            handler_params={"max_targets": 3},
        )
    )
    state.next_effect_id += 1
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.DEFENSE

    aegis_action = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.AEGIS)
    state = engine.apply_action(state, aegis_action)

    assert sum(1 for card in state.players[1].energy if card.resting) == 3
    assert any(cp.name == "effect_auto_switch_up_to_n_opponent_energy_rest_on_aegis" for cp in state.checkpoints)


def test_phase4_aegis_action_can_draw_switch_self_active_and_rest_opponent_board() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    attacker = CardInstance(
        instance_id=990550,
        card_id=9431,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        energy_cost=1,
        power=15000,
    )
    target = CardInstance(
        instance_id=990551,
        card_id=9432,
        owner_id=1,
        card_type="BATTLE",
        color="Blue",
        energy_cost=2,
        power=15000,
        resting=False,
    )
    aegis_card = CardInstance(
        instance_id=990552,
        card_id=999331,
        owner_id=2,
        card_type="BATTLE",
        color="Blue/Yellow",
        power=20000,
        resting=True,
        skill_text_raw="[Aegis Blue/Yellow][Once per turn] (If it's your opponent's turn, you can activate this during the Defense Step by placing cards in your hand in your Drop Area that match all colors specified by [Aegis]: Choose up to 2 of your energy and switch them to Active Mode.)",
    )
    state.players[1].battle_area = [attacker, target]
    state.players[2].battle_area = [aegis_card]
    state.players[2].hand = [
        CardInstance(instance_id=990553, card_id=9433, owner_id=2, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=990554, card_id=9434, owner_id=2, card_type="BATTLE", color="Yellow"),
    ]
    state.players[2].energy = [
        CardInstance(instance_id=990555, card_id=9435, owner_id=2, card_type="BATTLE", color="Blue", resting=True),
        CardInstance(instance_id=990556, card_id=9436, owner_id=2, card_type="BATTLE", color="Yellow", resting=True),
    ]
    state.effect_registry.append(
        EffectRegistration(
            effect_id=state.next_effect_id,
            owner_player_id=2,
            source_instance_id=aegis_card.instance_id,
            source_card_id=aegis_card.card_id,
            source_zone="battle",
            trigger="self_aegis_activated",
            handler_id="auto_draw_n_switch_self_active_and_switch_up_to_n_opponent_board_rest_on_aegis",
            handler_params={"amount": 1, "max_targets": 1},
        )
    )
    state.next_effect_id += 1
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.DEFENSE
    deck_before = len(state.players[2].deck)

    aegis_action = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.AEGIS)
    state = engine.apply_action(state, aegis_action)

    assert len(state.players[2].deck) == deck_before - 1
    assert state.players[2].battle_area[0].resting is False
    assert sum(1 for card in state.players[1].battle_area if card.resting) >= 1
    assert any(cp.name == "effect_auto_draw_n_switch_self_active_and_switch_up_to_n_opponent_board_rest_on_aegis" for cp in state.checkpoints)


def test_phase4_aegis_action_can_discard_then_play_matching_card_from_drop() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    attacker = CardInstance(
        instance_id=990560,
        card_id=9441,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        energy_cost=1,
        power=15000,
    )
    aegis_card = CardInstance(
        instance_id=990561,
        card_id=999332,
        owner_id=2,
        card_type="BATTLE",
        color="Blue/Yellow",
        power=20000,
        resting=False,
        traits=("Universe 6",),
        skill_text_raw="[Aegis Blue/Yellow][Once per turn] (If it's your opponent's turn, you can activate this during the Defense Step by placing cards in your hand in your Drop Area that match all colors specified by [Aegis]: Choose up to 2 of your energy and switch them to Active Mode.)",
    )
    playable = CardInstance(
        instance_id=990562,
        card_id=9442,
        owner_id=2,
        card_type="BATTLE",
        color="Blue",
        energy_cost=2,
        power=15000,
        traits=("Universe 6",),
        keywords=(),
    )
    with_keyword = CardInstance(
        instance_id=990563,
        card_id=9443,
        owner_id=2,
        card_type="BATTLE",
        color="Yellow",
        energy_cost=2,
        power=15000,
        traits=("Universe 6",),
        keywords=("Blocker",),
    )
    state.players[1].battle_area = [attacker]
    state.players[2].battle_area = [aegis_card]
    state.players[2].drop = [with_keyword, playable]
    state.players[2].hand = [
        CardInstance(instance_id=990564, card_id=9444, owner_id=2, card_type="BATTLE", color="Red"),
        CardInstance(instance_id=990565, card_id=9445, owner_id=2, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=990566, card_id=9446, owner_id=2, card_type="BATTLE", color="Yellow"),
    ]
    state.players[2].energy = [
        CardInstance(instance_id=990567, card_id=9447, owner_id=2, card_type="BATTLE", color="Blue", resting=True),
        CardInstance(instance_id=990568, card_id=9448, owner_id=2, card_type="BATTLE", color="Yellow", resting=True),
    ]
    state.effect_registry.append(
        EffectRegistration(
            effect_id=state.next_effect_id,
            owner_player_id=2,
            source_instance_id=aegis_card.instance_id,
            source_card_id=aegis_card.card_id,
            source_zone="battle",
            trigger="self_aegis_activated",
            handler_id="auto_optional_discard_play_up_to_n_from_owner_drop_on_aegis",
            handler_params={
                "discard_from_hand_before": 1,
                "max_targets": 1,
                "max_cost": 2,
                "allowed_colors": "blue,yellow",
                "required_traits": "Universe 6",
                "requires_no_keywords": True,
            },
        )
    )
    state.next_effect_id += 1
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.DEFENSE

    aegis_action = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.AEGIS)
    state = engine.apply_action(state, aegis_action)

    assert any(card.instance_id == playable.instance_id for card in state.players[2].battle_area)
    assert not any(card.instance_id == playable.instance_id for card in state.players[2].drop)
    assert any(card.instance_id == 990564 for card in state.players[2].drop)
    assert any(cp.name == "effect_auto_optional_discard_play_up_to_n_from_owner_drop_on_aegis" for cp in state.checkpoints)


def test_phase4_aegis_action_can_mill_opponent_deck_if_no_other_matching_owner_battle_exists() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(910000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    attacker = CardInstance(
        instance_id=990570,
        card_id=9451,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        energy_cost=1,
        power=15000,
    )
    aegis_card = CardInstance(
        instance_id=990571,
        card_id=999333,
        owner_id=2,
        card_type="BATTLE",
        color="Blue/Yellow",
        power=15000,
        traits=("Evil Incarnate",),
        skill_text_raw="[Aegis Blue/Yellow][Once per turn] (If it's your opponent's turn, you can activate this during the Defense Step by placing cards in your hand in your Drop Area that match all colors specified by [Aegis]: Choose up to 2 of your energy and switch them to Active Mode.)",
    )
    other_matching = CardInstance(
        instance_id=990572,
        card_id=9452,
        owner_id=2,
        card_type="BATTLE",
        color="Blue",
        power=5000,
        traits=("Evil Incarnate",),
    )
    state.players[1].battle_area = [attacker]
    state.players[2].battle_area = [aegis_card, other_matching]
    state.players[2].hand = [
        CardInstance(instance_id=990573, card_id=9453, owner_id=2, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=990574, card_id=9454, owner_id=2, card_type="BATTLE", color="Yellow"),
    ]
    state.players[2].energy = [
        CardInstance(instance_id=990575, card_id=9455, owner_id=2, card_type="BATTLE", color="Blue", resting=True),
        CardInstance(instance_id=990576, card_id=9456, owner_id=2, card_type="BATTLE", color="Yellow", resting=True),
    ]
    state.effect_registry.append(
        EffectRegistration(
            effect_id=state.next_effect_id,
            owner_player_id=2,
            source_instance_id=aegis_card.instance_id,
            source_card_id=aegis_card.card_id,
            source_zone="battle",
            trigger="self_aegis_activated",
            handler_id="auto_place_top_n_from_opponent_deck_into_drop_on_aegis",
            handler_params={"amount": 1, "required_no_other_owner_traits": "Evil Incarnate"},
        )
    )
    state.next_effect_id += 1
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.DEFENSE

    aegis_action = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.AEGIS)
    blocked_state = engine.apply_action(state, aegis_action)

    deck_before = len(blocked_state.players[1].deck)
    assert len(blocked_state.players[1].drop) == 0

    blocked_state.players[2].battle_area = [aegis_card]
    blocked_state.players[2].hand = [
        CardInstance(instance_id=990577, card_id=9457, owner_id=2, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=990578, card_id=9458, owner_id=2, card_type="BATTLE", color="Yellow"),
    ]
    blocked_state.players[2].energy = [
        CardInstance(instance_id=990579, card_id=9459, owner_id=2, card_type="BATTLE", color="Blue", resting=True),
        CardInstance(instance_id=990580, card_id=9460, owner_id=2, card_type="BATTLE", color="Yellow", resting=True),
    ]
    blocked_state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=blocked_state.players[2].leader_area.instance_id,
    )
    blocked_state.battle_step = BattleStep.DEFENSE
    blocked_state.activate_skill_usage.clear()

    aegis_action = next(a for a in engine.get_legal_actions(blocked_state, 2) if a.action_type == ActionType.AEGIS)
    final_state = engine.apply_action(blocked_state, aegis_action)

    assert len(final_state.players[1].drop) == 1
    assert len(final_state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_place_top_n_from_opponent_deck_into_drop_on_aegis" for cp in final_state.checkpoints)


def test_phase4_aegis_action_can_use_matching_drop_card_in_combo_with_skills_negated() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    attacker = CardInstance(
        instance_id=990581,
        card_id=9461,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        energy_cost=1,
        power=15000,
    )
    aegis_card = CardInstance(
        instance_id=990582,
        card_id=999334,
        owner_id=2,
        card_type="BATTLE",
        color="Blue/Yellow",
        power=20000,
        skill_text_raw="[Aegis Blue/Yellow][Once per turn] (If it's your opponent's turn, you can activate this during the Defense Step by placing cards in your hand in your Drop Area that match all colors specified by [Aegis]: Choose up to 2 of your energy and switch them to Active Mode.)",
    )
    combo_card = CardInstance(
        instance_id=990583,
        card_id=9462,
        owner_id=2,
        card_type="BATTLE",
        color="Blue",
        combo_power=5000,
        power=5000,
        keywords=("Blocker",),
    )
    nonmatching = CardInstance(
        instance_id=990584,
        card_id=9463,
        owner_id=2,
        card_type="BATTLE",
        color="Green",
        combo_power=5000,
        power=5000,
    )
    state.players[1].battle_area = [attacker]
    state.players[2].battle_area = [aegis_card]
    state.players[2].drop = [nonmatching, combo_card]
    state.players[2].hand = [
        CardInstance(instance_id=990585, card_id=9464, owner_id=2, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=990586, card_id=9465, owner_id=2, card_type="BATTLE", color="Yellow"),
    ]
    state.players[2].energy = [
        CardInstance(instance_id=990587, card_id=9466, owner_id=2, card_type="BATTLE", color="Blue", resting=True),
        CardInstance(instance_id=990588, card_id=9467, owner_id=2, card_type="BATTLE", color="Yellow", resting=True),
    ]
    state.effect_registry.append(
        EffectRegistration(
            effect_id=state.next_effect_id,
            owner_player_id=2,
            source_instance_id=aegis_card.instance_id,
            source_card_id=aegis_card.card_id,
            source_zone="battle",
            trigger="self_aegis_activated",
            handler_id="auto_combo_up_to_n_from_owner_zone_on_aegis",
            handler_params={
                "source_zone": "drop",
                "max_targets": 1,
                "allowed_colors": "blue,yellow",
                "exact_combo_power": 5000,
                "negate_skills": True,
            },
        )
    )
    state.next_effect_id += 1
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.DEFENSE

    aegis_action = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.AEGIS)
    state = engine.apply_action(state, aegis_action)

    assert any(card.instance_id == combo_card.instance_id for card in state.players[2].combo_area)
    assert not any(card.instance_id == combo_card.instance_id for card in state.players[2].drop)
    comboed = next(card for card in state.players[2].combo_area if card.instance_id == combo_card.instance_id)
    assert comboed.temporary_skills_negated is True
    assert any(
        event.name == "card_comboed"
        and event.payload.get("source_instance_id") == combo_card.instance_id
        and event.payload.get("comboed_from") == "drop"
        for event in state.effect_events
    )
    assert any(cp.name == "effect_auto_combo_up_to_n_from_owner_zone_on_aegis" for cp in state.checkpoints)


def test_phase4_owner_aegis_activated_can_trigger_combo_follow_up_from_another_card() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    attacker = CardInstance(
        instance_id=990589,
        card_id=9468,
        owner_id=1,
        card_type="BATTLE",
        color="Red",
        energy_cost=1,
        power=15000,
    )
    activating_aegis = CardInstance(
        instance_id=990590,
        card_id=999335,
        owner_id=2,
        card_type="BATTLE",
        color="Blue/Yellow",
        power=20000,
        skill_text_raw="[Aegis Blue/Yellow][Once per turn] (If it's your opponent's turn, you can activate this during the Defense Step by placing cards in your hand in your Drop Area that match all colors specified by [Aegis]: Choose up to 2 of your energy and switch them to Active Mode.)",
    )
    watcher = CardInstance(
        instance_id=990591,
        card_id=9469,
        owner_id=2,
        card_type="BATTLE",
        color="Blue",
        power=5000,
    )
    combo_card = CardInstance(
        instance_id=990592,
        card_id=9470,
        owner_id=2,
        card_type="BATTLE",
        color="Yellow",
        combo_power=5000,
        power=5000,
    )
    state.players[1].battle_area = [attacker]
    state.players[2].battle_area = [activating_aegis, watcher]
    state.players[2].drop = [combo_card]
    state.players[2].hand = [
        CardInstance(instance_id=990593, card_id=9471, owner_id=2, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=990594, card_id=9472, owner_id=2, card_type="BATTLE", color="Yellow"),
    ]
    state.players[2].energy = [
        CardInstance(instance_id=990595, card_id=9473, owner_id=2, card_type="BATTLE", color="Blue", resting=True),
        CardInstance(instance_id=990596, card_id=9474, owner_id=2, card_type="BATTLE", color="Yellow", resting=True),
    ]
    state.effect_registry.append(
        EffectRegistration(
            effect_id=state.next_effect_id,
            owner_player_id=2,
            source_instance_id=watcher.instance_id,
            source_card_id=watcher.card_id,
            source_zone="battle",
            trigger="owner_aegis_activated",
            handler_id="auto_combo_up_to_n_from_owner_zone_on_aegis",
            handler_params={
                "source_zone": "drop",
                "max_targets": 1,
                "allowed_colors": "yellow",
                "exact_combo_power": 5000,
                "negate_skills": True,
            },
        )
    )
    state.next_effect_id += 1
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.DEFENSE

    aegis_action = next(
        a
        for a in engine.get_legal_actions(state, 2)
        if a.action_type == ActionType.AEGIS and a.source_index == 0
    )
    state = engine.apply_action(state, aegis_action)

    assert any(card.instance_id == combo_card.instance_id for card in state.players[2].combo_area)
    assert any(cp.name == "effect_auto_combo_up_to_n_from_owner_zone_on_aegis" for cp in state.checkpoints)


def test_phase4_demigra_wormhole_opened_can_draw_discard_gain_wormhole_and_grant_double_strike() -> None:
    engine = RulesEngine(
        effect_rule_overrides={
            7798: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "owner_other_battle_played_by_over_realm",
                        "handler_id": "auto_draw_n_discard_n",
                        "handler_params": {"amount": 2, "discard_amount": 2},
                        "once_per_turn": True,
                    },
                    {
                        "trigger": "self_activate_main",
                        "handler_id": "activate_send_up_to_n_from_owner_warp_to_drop_and_gain_keyword_for_turn",
                        "handler_params": {
                            "max_targets": 2,
                            "allowed_colors": "black",
                            "required_card_type": "BATTLE",
                            "grant_keyword": "Wormhole",
                            "marker_delta": 1,
                            "requires_leader": "black",
                        },
                    },
                    {
                        "trigger": "self_activate_main",
                        "handler_id": "activate_buff_owner_battle_cards",
                        "handler_params": {
                            "max_targets": 2,
                            "grant_keyword": "Double Strike",
                            "required_skill_text_contains": "over realm",
                            "marker_delta": -3,
                        },
                    },
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Black"
    source = CardInstance(instance_id=990420, card_id=7798, owner_id=1, card_type="Z-UNISON", color="Black", markers=3)
    warp_a = CardInstance(instance_id=990421, card_id=9421, owner_id=1, card_type="BATTLE", color="Black")
    warp_b = CardInstance(instance_id=990422, card_id=9422, owner_id=1, card_type="BATTLE", color="Black")
    over_realm_a = CardInstance(instance_id=990423, card_id=9423, owner_id=1, card_type="BATTLE", color="Black", skill_text_raw="[Over Realm 4]")
    over_realm_b = CardInstance(instance_id=990424, card_id=9424, owner_id=1, card_type="BATTLE", color="Black", skill_text_raw="[Over Realm 6]")
    state.players[1].unison_area.append(source)
    state.players[1].warp.extend([warp_a, warp_b])
    state.players[1].battle_area.extend([over_realm_a, over_realm_b])
    state.players[1].hand.extend(
        [
            CardInstance(instance_id=990425, card_id=9425, owner_id=1),
            CardInstance(instance_id=990426, card_id=9426, owner_id=1),
        ]
    )
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)
    registered = [reg for reg in state.effect_registry if reg.source_instance_id == 990420 and reg.trigger == "self_activate_main"]
    plus_effect_id = next(reg.effect_id for reg in registered if reg.handler_id == "activate_send_up_to_n_from_owner_warp_to_drop_and_gain_keyword_for_turn")
    minus_effect_id = next(reg.effect_id for reg in registered if reg.handler_id == "activate_buff_owner_battle_cards")

    hand_before = len(state.players[1].hand)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990499, "source_card_id": 9499, "source_zone": "battle", "played_via": "over_realm"},
    )
    engine._resolve_pending_effects(state)
    assert len(state.players[1].hand) == hand_before
    assert any(cp.name == "effect_auto_draw_n_discard_n" for cp in state.checkpoints)

    engine._emit_effect_event(
        state,
        name="skill_activated",
        actor_player_id=1,
        payload={"source_instance_id": 990420, "source_card_id": 7798, "source_zone": "unison", "skill_kind": "activate_main", "selected_effect_id": plus_effect_id},
    )
    engine._resolve_pending_effects(state)
    assert source.markers == 4
    assert len(state.players[1].warp) == 0
    assert "Wormhole" in source.temporary_keywords

    engine._emit_effect_event(
        state,
        name="skill_activated",
        actor_player_id=1,
        payload={"source_instance_id": 990420, "source_card_id": 7798, "source_zone": "unison", "skill_kind": "activate_main", "selected_effect_id": minus_effect_id},
    )
    engine._resolve_pending_effects(state)
    assert source.markers == 1
    assert "Double Strike" in over_realm_a.temporary_keywords
    assert "Double Strike" in over_realm_b.temporary_keywords


def test_phase4_jiren_climactic_battle_can_remove_marker_to_negate_attack() -> None:
    engine = RulesEngine(
        effect_rule_overrides={
            8448: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "owner_opponent_card_attacks",
                        "handler_id": "auto_negate_attack_on_opponent_attack",
                        "handler_params": {"marker_delta": -1},
                    }
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    source = CardInstance(instance_id=990430, card_id=8448, owner_id=1, card_type="Z-UNISON", color="Red", markers=2)
    attacker = CardInstance(instance_id=990431, card_id=9431, owner_id=2, card_type="BATTLE", color="Blue", power=15000)
    state.players[1].unison_area.append(source)
    state.players[2].battle_area.append(attacker)
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)
    state.attack_context = AttackContext(
        attacker_player_id=2,
        attacker_zone="battle",
        attacker_instance_id=990431,
        target_player_id=1,
        target_zone="leader",
        target_instance_id=state.players[1].leader_area.instance_id,
    )
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=2,
        payload={"attacker_instance_id": 990431, "attacker_zone": "battle"},
    )
    engine._resolve_pending_effects(state)
    assert source.markers == 1
    assert state.attack_context is None
    assert any(cp.name == "effect_auto_negate_attack_on_opponent_attack" for cp in state.checkpoints)


def test_phase4_oolong_greed_is_good_can_copy_battle_power_for_turn() -> None:
    engine = RulesEngine(
        effect_rule_overrides={
            892: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "self_activate_main",
                        "handler_id": "activate_copy_battle_power_to_self_for_turn",
                        "handler_params": {
                            "max_targets": 1,
                            "ignores_barrier": True,
                        },
                        "once_per_turn": True,
                    }
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    oolong = CardInstance(
        instance_id=990440,
        card_id=892,
        owner_id=1,
        card_type="BATTLE",
        color="Yellow",
        power=4000,
        has_activate_main=True,
    )
    target = CardInstance(
        instance_id=990441,
        card_id=9441,
        owner_id=2,
        card_type="BATTLE",
        color="Blue",
        power=25000,
        has_barrier=True,
    )
    state.players[1].battle_area.append(oolong)
    state.players[2].battle_area.append(target)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=oolong)
    engine._emit_effect_event(
        state,
        name="skill_activated",
        actor_player_id=1,
        payload={
            "source_instance_id": 990440,
            "source_card_id": 892,
            "source_zone": "battle",
            "skill_kind": "activate_main",
        },
    )
    engine._resolve_pending_effects(state)
    assert oolong.power == 25000
    assert oolong.temporary_power_delta == 21000
    assert any(cp.name == "effect_activate_copy_battle_power_to_self_for_turn" for cp in state.checkpoints)


def test_phase4_ss3_scramble_can_drop_life_damage_and_clear_opponent_combo() -> None:
    engine = RulesEngine(
        effect_rule_overrides={
            6820: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "self_played",
                        "handler_id": "auto_place_life_to_drop_and_deal_damage_on_play",
                        "handler_params": {"life_to_drop_count": 1, "damage_amount": 2},
                    },
                    {
                        "trigger": "owner_opponent_card_comboed",
                        "handler_id": "auto_send_up_to_n_opponent_combo_to_drop_on_opponent_combo",
                        "handler_params": {"max_targets": 1, "max_energy_cost": 2},
                    },
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=990450, card_id=6820, owner_id=1, card_type="BATTLE", color="Red/Green", power=40000)
    state.players[1].battle_area.append(source)
    starting_life = len(state.players[1].life)
    starting_opponent_life = len(state.players[2].life)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990450, "source_card_id": 6820, "source_zone": "battle", "played_from": "hand"},
    )
    engine._resolve_pending_effects(state)
    assert len(state.players[1].life) == starting_life - 1
    assert len(state.players[2].life) == starting_opponent_life - 2
    assert any(cp.name == "effect_auto_place_life_to_drop_and_deal_damage_on_play" for cp in state.checkpoints)

    combo_a = CardInstance(instance_id=990451, card_id=9451, owner_id=2, card_type="BATTLE", color="Blue", energy_cost=2, combo_cost=1)
    combo_b = CardInstance(instance_id=990452, card_id=9452, owner_id=2, card_type="BATTLE", color="Blue", energy_cost=4, combo_cost=1)
    state.players[2].combo_area.extend([combo_a, combo_b])
    engine._emit_effect_event(
        state,
        name="card_comboed",
        actor_player_id=2,
        payload={"source_instance_id": 990451, "source_card_id": 9451, "source_zone": "combo", "comboed_from": "hand"},
    )
    engine._resolve_pending_effects(state)
    assert any(card.instance_id == 990451 for card in state.players[2].drop)
    assert any(cp.name == "effect_auto_send_up_to_n_opponent_combo_to_drop_on_opponent_combo" for cp in state.checkpoints)


def test_phase4_ss4_gogeta_bold_arrival_can_pay_drop_to_warp_and_reduce_on_self_or_opponent_battle_play() -> None:
    engine = RulesEngine(
        effect_rule_overrides={
            8444: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "self_or_opponent_battle_played",
                        "handler_id": "auto_send_owner_drop_to_warp_and_reduce_up_to_n_opponent_battle_for_turn_on_self_or_opponent_battle_played",
                        "handler_params": {
                            "cost_amount": 1,
                            "cost_required_traits": "Saiyan",
                            "max_targets": 1,
                            "power_delta": -20000,
                        },
                        "once_per_turn": True,
                    }
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=990460, card_id=8444, owner_id=1, card_type="Z-BATTLE", color="Red/Black", power=25000)
    drop_saiyan = CardInstance(instance_id=990461, card_id=9461, owner_id=1, card_type="BATTLE", color="Black", traits=("Saiyan",))
    target = CardInstance(instance_id=990462, card_id=9462, owner_id=2, card_type="BATTLE", color="Blue", power=30000)
    state.players[1].battle_area.append(source)
    state.players[1].drop.append(drop_saiyan)
    state.players[2].battle_area.append(target)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990460, "source_card_id": 8444, "source_zone": "battle", "played_from": "z_deck"},
    )
    engine._resolve_pending_effects(state)
    assert any(card.instance_id == 990461 for card in state.players[1].warp)
    assert target.temporary_power_delta == -20000
    assert any(cp.name == "effect_auto_send_owner_drop_to_warp_and_reduce_up_to_n_opponent_battle_for_turn_on_self_or_opponent_battle_played" for cp in state.checkpoints)


def test_phase4_son_goku_stronger_together_can_trim_opponent_hand_and_buff_for_battle() -> None:
    engine = RulesEngine(
        skill_cost_rules={
            1480: {
                "activate_battle": [
                    {"kind": "send_self_to_removed", "amount": 1},
                ]
            }
        },
        effect_rule_overrides={
            1480: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "self_played",
                        "handler_id": "auto_opponent_bottom_decks_from_hand_until_n_on_play",
                        "handler_params": {"hand_limit": 10, "min_opponent_hand": 11, "requires_leader": "blue"},
                    },
                    {
                        "trigger": "self_activate_battle",
                        "handler_id": "activate_gain_power_and_keyword_for_battle",
                        "handler_params": {
                            "target_scope": "owner_battle",
                            "max_targets": 1,
                            "power_delta": 10000,
                            "grant_keyword": "Triple Strike",
                            "allowed_colors": "blue",
                            "min_character_count": 2,
                            "requires_leader": "<Son Gohan: SH>",
                            "min_owner_energy": 3,
                        },
                        "limit_per_turn": 1,
                    },
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Blue"
    state.players[1].leader_area.characters = ("Son Gohan: SH",)
    source = CardInstance(instance_id=990470, card_id=1480, owner_id=1, card_type="Z-BATTLE", color="Blue", power=4000, has_activate_battle=True)
    buff_target = CardInstance(instance_id=990471, card_id=9471, owner_id=1, card_type="BATTLE", color="Blue", power=20000, characters=("A", "B"))
    state.players[1].battle_area.extend([source, buff_target])
    state.players[1].energy = [
        CardInstance(instance_id=990472, card_id=9472, owner_id=1, color="Blue"),
        CardInstance(instance_id=990473, card_id=9473, owner_id=1, color="Blue"),
        CardInstance(instance_id=990474, card_id=9474, owner_id=1, color="Blue"),
    ]
    state.players[2].hand = [
        CardInstance(instance_id=990480 + i, card_id=9480 + i, owner_id=2, card_type="BATTLE")
        for i in range(11)
    ]
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990470, "source_card_id": 1480, "source_zone": "battle", "played_from": "hand"},
    )
    engine._resolve_pending_effects(state)
    assert len(state.players[2].hand) == 10
    assert any(cp.name == "effect_auto_opponent_bottom_decks_from_hand_until_n_on_play" for cp in state.checkpoints)

    engine._emit_effect_event(
        state,
        name="skill_activated",
        actor_player_id=1,
        payload={"source_instance_id": 990470, "source_card_id": 1480, "source_zone": "battle", "skill_kind": "activate_battle"},
    )
    engine._resolve_pending_effects(state)
    state.players[1].battle_area = [card for card in state.players[1].battle_area if card.instance_id != 990470]
    state.players[1].removed_from_game.append(source)
    assert any(card.instance_id == 990470 for card in state.players[1].removed_from_game)
    assert buff_target.battle_temporary_power_delta == 10000
    assert "Triple Strike" in buff_target.battle_temporary_keywords


def test_phase4_crimson_guardian_deity_minus_one_can_switch_self_active_and_reduce_opponent_battle() -> None:
    engine = RulesEngine(
        effect_rule_overrides={
            2481: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "self_activate_main",
                        "handler_id": "activate_switch_self_active_and_power_reduce_up_to_n_opponent_battle_for_turn",
                        "handler_params": {
                            "marker_delta": -1,
                            "max_targets": 1,
                            "power_delta": -25000,
                            "ignores_barrier": True,
                            "target_policy": "first",
                        },
                    }
                ],
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=991300, card_id=2481, owner_id=1, card_type="Z-UNISON", color="Red", power=20000, resting=True, markers=2, has_activate_main=True)
    target = CardInstance(instance_id=991301, card_id=9301, owner_id=2, card_type="BATTLE", color="Blue", power=30000, has_barrier=True)
    state.players[1].unison_area.append(source)
    state.players[2].battle_area.append(target)
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)
    engine._emit_effect_event(
        state,
        name="skill_activated",
        actor_player_id=1,
        payload={"source_instance_id": 991300, "source_card_id": 2481, "source_zone": "unison", "skill_kind": "activate_main"},
    )
    engine._resolve_pending_effects(state)

    assert source.resting is False
    assert source.markers == 1
    assert target.temporary_power_delta == -25000
    assert any(cp.name == "effect_activate_switch_self_active_and_power_reduce_up_to_n_opponent_battle_for_turn" for cp in state.checkpoints)


def test_phase4_special_beam_cannon_inherited_power_can_ko_and_buff_branch_b() -> None:
    engine = RulesEngine(
        skill_cost_rules={2064: {"activate_extra_from_hand": [{"kind": "send_self_to_removed", "amount": 1}]}},
        effect_rule_overrides={
            2064: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "self_activate_extra_from_hand",
                        "handler_id": "activate_ko_up_to_n_opponent_battle_and_buff_owner_cards_for_battle",
                        "handler_params": {
                            "max_targets": 1,
                            "max_power": 35000,
                            "ignores_barrier": True,
                            "target_policy": "first",
                            "target_scope": "owner_battle",
                            "prefer_owner_attacker": True,
                            "buff_max_targets": 1,
                            "buff_target_policy": "first",
                            "allowed_colors": "red",
                            "required_characters": "Son Gohan: SH",
                            "min_power": 30000,
                            "power_delta": 15000,
                            "grant_keyword": "Double Strike",
                            "required_owner_attacker_allowed_colors": "red",
                            "required_owner_attacker_required_characters": "Son Gohan: SH",
                        },
                    }
                ],
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    attacker = CardInstance(instance_id=991310, card_id=9919310, owner_id=1, card_type="BATTLE", color="Red", power=30000, characters=("Son Gohan: SH",))
    state.players[1].battle_area.append(attacker)
    state.players[1].hand.append(
        CardInstance(
            instance_id=991311,
            card_id=2064,
            owner_id=1,
            card_type="Z-EXTRA",
            color="Red",
            energy_cost=1,
            z_energy_cost=0,
            has_activate_battle=True,
        )
    )
    state.players[1].energy = [CardInstance(instance_id=991312, card_id=9919312, owner_id=1, color="Red")]
    target = CardInstance(instance_id=991313, card_id=9919313, owner_id=2, card_type="BATTLE", color="Blue", power=35000, has_barrier=True)
    state.players[2].battle_area.append(target)
    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="battle",
        attacker_instance_id=attacker.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.OFFENSE
    declared_index = next(i for i, card in enumerate(state.players[1].hand) if card.instance_id == 991311)
    declared = state.players[1].hand.pop(declared_index)
    state.players[1].drop.append(declared)
    engine._register_card_effects(state, player_id=1, source_zone="drop", card=declared)
    engine._pay_skill_cost(state, state.players[1], declared, "activate_extra_from_hand")
    engine._emit_effect_event(
        state,
        name="skill_activated",
        actor_player_id=1,
        payload={
            "source_instance_id": 991311,
            "source_card_id": 2064,
            "source_zone": "drop",
            "skill_kind": "activate_extra_from_hand",
        },
    )
    engine._resolve_pending_effects(state)

    assert not any(card.instance_id == 991313 for card in state.players[2].battle_area)
    assert any(card.instance_id == 991313 for card in state.players[2].drop)
    assert attacker.battle_temporary_power_delta == 15000
    assert "Double Strike" in attacker.battle_temporary_keywords
    assert any(card.instance_id == 991311 for card in state.players[1].removed_from_game)
    assert any(cp.name == "effect_activate_ko_up_to_n_opponent_battle_and_buff_owner_cards_for_battle" for cp in state.checkpoints)


def test_phase4_ss_vegito_overwhelming_might_applies_non_leader_attack_tax_and_schedules_self_warp() -> None:
    engine = RulesEngine(
        effect_rule_overrides={
            1632: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "self_played",
                        "handler_id": "auto_apply_non_leader_attack_rest_tax_warp_self_and_optionally_negate_opponent_strike",
                        "handler_params": {"rest_count": 1},
                        "limit_per_turn": 1,
                    },
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=991211, card_id=9211, owner_id=1, card_type="BATTLE", color="Yellow"),
        CardInstance(instance_id=991212, card_id=9212, owner_id=1, card_type="BATTLE", color="Yellow"),
    ]
    state.players[1].leader_area.resting = True
    attacker = CardInstance(instance_id=991213, card_id=9213, owner_id=1, card_type="BATTLE", color="Yellow", power=15000)
    state.players[1].battle_area.append(attacker)
    state.players[2].leader_area.color = "Yellow"
    state.players[2].z_energy = [
        CardInstance(instance_id=991214, card_id=9214, owner_id=2, card_type="Z-ENERGY"),
        CardInstance(instance_id=991215, card_id=9215, owner_id=2, card_type="Z-ENERGY"),
    ]
    state.players[2].energy = [CardInstance(instance_id=991216, card_id=9216, owner_id=2, card_type="BATTLE", color="Yellow")]
    state.players[2].battle_area.append(
        CardInstance(instance_id=991217, card_id=9217, owner_id=2, card_type="Z-BATTLE", color="Yellow", power=20000)
    )
    state.players[2].hand.append(
        CardInstance(
            instance_id=991218,
            card_id=1632,
            owner_id=2,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=8,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw=(
                "[Counter: Play] Play this card. "
                "[Permanent] During your opponent's turn, while your Leader is yellow, your opponent has 2 or more energy, and you have 2 or more Z-Energy, reduce the energy cost of this card in your hand by 7. "
                "[Auto] When this card is played from your hand, your opponent can't attack with non-Leaders unless they choose 1 of their Active Mode cards and switch it to Rest Mode each time, and at the end of the turn, send this card to its owner's Warp. "
                "Additionally, if your Leader is a Z-Leader, or you have a yellow Z-Battle Card in play, your Leader gains the following skill for the turn, "
                "\"[Permanent] Negate all of your opponent's [Strike] skills for the turn.\""
            ),
        )
    )
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.PLAY_CARD_FROM_HAND, player_id=1, hand_index=0),
    )
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    assert any(card.instance_id == 991218 for card in state.players[2].battle_area)
    assert len(state.non_leader_attack_rest_taxes) == 1
    assert len(state.delayed_warps) == 1
    assert 2 in state.negate_opponent_strike_for_player_ids
    legal_attacks = [
        action
        for action in engine.get_legal_actions(state, 1)
        if action.action_type == ActionType.DECLARE_ATTACK and action.attacker_zone == "battle"
    ]
    assert legal_attacks == []
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert any(card.instance_id == 991218 for card in state.players[2].warp)
    assert all(card.instance_id != 991218 for card in state.players[2].battle_area)
    assert any(cp.name == "effect_auto_apply_non_leader_attack_rest_tax_warp_self_and_optionally_negate_opponent_strike" for cp in state.checkpoints)
