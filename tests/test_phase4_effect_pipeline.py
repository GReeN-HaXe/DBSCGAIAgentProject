from __future__ import annotations

from types import SimpleNamespace

from src.game import Action, ActionType, CardInstance, EffectRegistration, RulesEngine, TurnPhase


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
    assert state.players[1].unison_area[0].owner_id == 1
    assert any(cp.name == "effect_auto_gain_control_opponent_unison_on_play" for cp in state.checkpoints)


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
