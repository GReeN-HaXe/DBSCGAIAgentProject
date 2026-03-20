from __future__ import annotations

from src.game import Action, ActionType, BattleStep, CardInstance, RulesEngine, TurnPhase
from src.game.state import NonLeaderAttackRestTax


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _to_main(engine: RulesEngine, state):
    while state.phase != TurnPhase.MAIN:
        state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=state.active_player))
    return state


def _to_p2_main(engine: RulesEngine, state):
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    return state


def _resolve_simple_battle(engine: RulesEngine, state, attacker: int, defender: int):
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=defender))
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=attacker))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=defender))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=attacker))
    if state.winner_id is None:
        state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=attacker))
    return state


def test_unison_can_attack() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)  # now p1 main
    state.players[1].unison_area.append(CardInstance(instance_id=700001, card_id=11, owner_id=1, card_type="UNISON", markers=2))
    legal = engine.get_legal_actions(state, player_id=1)
    assert any(a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "unison" for a in legal)


def test_equal_power_attacker_wins_on_battle_card() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area.append(CardInstance(instance_id=700011, card_id=11, owner_id=1, power=15000))
    state.players[2].battle_area.append(CardInstance(instance_id=700012, card_id=12, owner_id=2, power=15000, resting=True))
    state = engine.apply_action(
        state,
        Action(
            action_type=ActionType.DECLARE_ATTACK,
            player_id=1,
            attacker_zone="battle",
            attacker_index=0,
            target_player_id=2,
            target_zone="battle",
            target_index=0,
        ),
    )
    state = _resolve_simple_battle(engine, state, attacker=1, defender=2)
    assert len(state.players[2].battle_area) == 0


def test_lower_attacker_does_not_get_ko_from_battle_result() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area.append(CardInstance(instance_id=700021, card_id=21, owner_id=1, power=10000))
    state.players[2].battle_area.append(CardInstance(instance_id=700022, card_id=22, owner_id=2, power=15000, resting=True))
    state = engine.apply_action(
        state,
        Action(
            action_type=ActionType.DECLARE_ATTACK,
            player_id=1,
            attacker_zone="battle",
            attacker_index=0,
            target_player_id=2,
            target_zone="battle",
            target_index=0,
        ),
    )
    state = _resolve_simple_battle(engine, state, attacker=1, defender=2)
    assert len(state.players[1].battle_area) == 1
    assert len(state.players[2].battle_area) == 1


def test_unison_guard_loses_markers_not_immediate_ko() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area.append(CardInstance(instance_id=700031, card_id=31, owner_id=1, power=20000))
    state.players[2].unison_area.append(CardInstance(instance_id=700032, card_id=32, owner_id=2, card_type="UNISON", power=10000, resting=True, markers=2))
    state = engine.apply_action(
        state,
        Action(
            action_type=ActionType.DECLARE_ATTACK,
            player_id=1,
            attacker_zone="battle",
            attacker_index=0,
            target_player_id=2,
            target_zone="unison",
            target_index=0,
        ),
    )
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    assert state.players[2].unison_area[0].markers == 1


def test_unison_attack_skips_defense_step() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area.append(CardInstance(instance_id=700033, card_id=33, owner_id=1, power=20000))
    state.players[2].unison_area.append(CardInstance(instance_id=700034, card_id=34, owner_id=2, card_type="UNISON", power=10000, resting=True, markers=2))
    state = engine.apply_action(
        state,
        Action(
            action_type=ActionType.DECLARE_ATTACK,
            player_id=1,
            attacker_zone="battle",
            attacker_index=0,
            target_player_id=2,
            target_zone="unison",
            target_index=0,
        ),
    )
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    assert state.battle_step == BattleStep.DAMAGE
    legal = engine.get_legal_actions(state, player_id=2)
    assert all(a.action_type != ActionType.END_DEFENSE_STEP for a in legal)
    assert any(cp.name == "battle_damage_step" for cp in state.checkpoints)


def test_double_strike_removes_two_unison_markers() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=700035, card_id=35, owner_id=1, power=20000, keywords=("Double Strike",))
    )
    state.players[2].unison_area.append(CardInstance(instance_id=700036, card_id=36, owner_id=2, card_type="UNISON", power=10000, resting=True, markers=3))
    state = engine.apply_action(
        state,
        Action(
            action_type=ActionType.DECLARE_ATTACK,
            player_id=1,
            attacker_zone="battle",
            attacker_index=0,
            target_player_id=2,
            target_zone="unison",
            target_index=0,
        ),
    )
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    assert len(state.players[2].unison_area) == 1
    assert state.players[2].unison_area[0].markers == 1
    assert any(cp.name == "unison_marker_damage" for cp in state.checkpoints)


def test_victory_strike_removes_all_unison_markers_and_drops_unison() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=700037, card_id=37, owner_id=1, power=25000, keywords=("Victory Strike",))
    )
    state.players[2].unison_area.append(CardInstance(instance_id=700038, card_id=38, owner_id=2, card_type="UNISON", power=10000, resting=True, markers=4))
    state = engine.apply_action(
        state,
        Action(
            action_type=ActionType.DECLARE_ATTACK,
            player_id=1,
            attacker_zone="battle",
            attacker_index=0,
            target_player_id=2,
            target_zone="unison",
            target_index=0,
        ),
    )
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    assert len(state.players[2].unison_area) == 0
    assert any(card.instance_id == 700038 for card in state.players[2].drop)


def test_counter_can_negate_attack() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[2].hand.append(
        CardInstance(instance_id=700041, card_id=41, owner_id=2, has_counter=True, counter_modes=("Counter: Attack",), energy_cost=0)
    )
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=1, attacker_zone="leader", target_player_id=2, target_zone="leader"),
    )
    state = engine.apply_action(state, Action(action_type=ActionType.DECLARE_COUNTER_FROM_HAND, player_id=2, hand_index=len(state.players[2].hand) - 1))
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    assert state.attack_context is None


def test_counter_mode_restriction_blocks_wrong_counter_type() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[2].hand.append(
        CardInstance(instance_id=700045, card_id=45, owner_id=2, has_counter=True, counter_modes=("Counter: Play",), energy_cost=0)
    )
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=1, attacker_zone="leader", target_player_id=2, target_zone="leader"),
    )
    legal = engine.get_legal_actions(state, player_id=2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_counter_battle_card_attack_only_legal_vs_battle_attacks() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    # Defender has only Counter: Battle Card Attack.
    state.players[2].hand.append(
        CardInstance(
            instance_id=701001,
            card_id=101,
            owner_id=2,
            has_counter=True,
            has_counter_battle_card_attack=True,
            counter_modes=("Counter: Battle Card Attack",),
            energy_cost=0,
        )
    )

    # Leader attack: should not be legal.
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=1, attacker_zone="leader", target_player_id=2, target_zone="leader"),
    )
    legal = engine.get_legal_actions(state, player_id=2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    if state.winner_id is None:
        state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))

    # Add battle attacker and create new attack where counter becomes legal.
    state.players[1].battle_area.append(CardInstance(instance_id=701002, card_id=102, owner_id=1, power=15000))
    state = engine.apply_action(
        state,
        Action(
            action_type=ActionType.DECLARE_ATTACK,
            player_id=1,
            attacker_zone="battle",
            attacker_index=0,
            target_player_id=2,
            target_zone="leader",
        ),
    )
    legal = engine.get_legal_actions(state, player_id=2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_counter_chain_counter_counter_restores_attack() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[2].hand.append(
        CardInstance(instance_id=700046, card_id=46, owner_id=2, has_counter=True, counter_modes=("Counter: Attack",), energy_cost=0)
    )
    state.players[1].hand.append(
        CardInstance(instance_id=700047, card_id=47, owner_id=1, has_counter=True, counter_modes=("Counter: Counter",), energy_cost=0)
    )
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=1, attacker_zone="leader", target_player_id=2, target_zone="leader"),
    )
    state = engine.apply_action(state, Action(action_type=ActionType.DECLARE_COUNTER_FROM_HAND, player_id=2, hand_index=len(state.players[2].hand) - 1))
    state = engine.apply_action(state, Action(action_type=ActionType.DECLARE_COUNTER_FROM_HAND, player_id=1, hand_index=len(state.players[1].hand) - 1))
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.attack_context is not None
    assert state.battle_step == BattleStep.OFFENSE
    # Latest counter resolves and negates previous counter; previous one is unresolved.
    assert len(state.counter_resolutions) >= 2
    last_two = state.counter_resolutions[-2:]
    assert [r.resolution_order for r in last_two] == [1, 2]
    assert any(r.resolved and r.negated_motion_id is not None for r in last_two)
    assert any((not r.resolved) for r in last_two)
    assert all(r.pending_action_type == "attack" for r in last_two)
    # Trace includes declaration and resolution records.
    assert len(state.counter_motion_trace) >= 4
    assert any(t.resolved is None for t in state.counter_motion_trace)
    assert any(t.resolved is True for t in state.counter_motion_trace)
    assert any(t.resolved is False for t in state.counter_motion_trace)
    resolved_trace = [t for t in state.counter_motion_trace if t.resolved is not None][-2:]
    assert [t.resolution_order for t in resolved_trace] == [1, 2]
    assert resolved_trace[0].motion_id == 2
    assert resolved_trace[1].motion_id == 1
    assert all(t.pending_action_type == "attack" for t in resolved_trace)
    assert any(cp.name == "counter_chain_timing" for cp in state.checkpoints)
    assert any(cp.name == "counter_chain_resolution_begin" for cp in state.checkpoints)
    assert any(cp.name == "counter_chain_resolution_complete" for cp in state.checkpoints)
    assert any("Counter chain resolution begin" in row for row in state.log)
    assert any("Counter chain resolution complete" in row and "order=1" in row for row in state.log)


def test_almighty_resistance_can_counter_counter_by_discarding_yellow_hand_card() -> None:
    engine = RulesEngine(
        skill_cost_rules={
            4949: {
                "counter_from_hand": [
                    {"kind": "discard_hand", "amount": 1, "allowed_colors": "yellow", "required_leader_colors": "red"},
                ]
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state.players[1].leader_area.color = "Red"
    state = _to_p2_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=700055, card_id=855, owner_id=1, card_type="ENERGY", color="Red"),
        CardInstance(instance_id=700056, card_id=856, owner_id=1, card_type="ENERGY", color="Yellow"),
    ]
    state.players[2].hand.append(
        CardInstance(instance_id=700048, card_id=48, owner_id=2, has_counter=True, counter_modes=("Counter: Attack",), energy_cost=0)
    )
    state.players[1].hand.extend(
        [
            CardInstance(
                instance_id=700049,
                card_id=4949,
                owner_id=1,
                card_type="EXTRA",
                color="Red/Yellow",
                energy_cost=2,
                has_counter=True,
                has_counter_counter=True,
                counter_modes=("Counter: Counter",),
                skill_text_raw="[Counter: Counter] If your Leader Card is red and you choose 1 yellow card in your hand and place it in your Drop Area: Negate the [Counter: Attack] skill.",
            ),
            CardInstance(instance_id=700050, card_id=850, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=1),
        ]
    )
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=1, attacker_zone="leader", target_player_id=2, target_zone="leader"),
    )
    state = engine.apply_action(state, Action(action_type=ActionType.DECLARE_COUNTER_FROM_HAND, player_id=2, hand_index=len(state.players[2].hand) - 1))
    legal = engine.get_legal_actions(state, 1)
    almighty_action = next(a for a in legal if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND and state.players[1].hand[a.hand_index].card_id == 4949)
    state = engine.apply_action(state, almighty_action)
    assert any(card.instance_id == 700050 for card in state.players[1].drop)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.attack_context is not None
    last_two = state.counter_resolutions[-2:]
    assert any(r.resolved and r.negated_motion_id is not None for r in last_two)


def test_almighty_resistance_is_not_legal_against_non_attack_counter_motion() -> None:
    engine = RulesEngine(
        skill_cost_rules={
            4949: {
                "counter_from_hand": [
                    {"kind": "discard_hand", "amount": 1, "allowed_colors": "yellow", "required_leader_colors": "red"},
                ]
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=1, shuffle_decks=False
    )
    state.players[1].leader_area.color = "Red"
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=700051, card_id=851, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[1].energy = [
        CardInstance(instance_id=700057, card_id=857, owner_id=1, card_type="ENERGY", color="Red"),
        CardInstance(instance_id=700058, card_id=858, owner_id=1, card_type="ENERGY", color="Yellow"),
    ]
    state.players[2].hand = [
        CardInstance(instance_id=700052, card_id=852, owner_id=2, card_type="BATTLE", energy_cost=0, has_counter=True, has_counter_play=True, counter_modes=("Counter: Play",)),
    ]
    state.players[1].hand.extend(
        [
        CardInstance(
            instance_id=700053,
            card_id=4949,
            owner_id=1,
            card_type="EXTRA",
            color="Red/Yellow",
            energy_cost=2,
            has_counter=True,
            has_counter_counter=True,
            counter_modes=("Counter: Counter",),
            skill_text_raw="[Counter: Counter] If your Leader Card is red and you choose 1 yellow card in your hand and place it in your Drop Area: Negate the [Counter: Attack] skill.",
        ),
        CardInstance(instance_id=700054, card_id=853, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=1),
        ]
    )
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    first_counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, first_counter)
    legal = engine.get_legal_actions(state, 1)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_declaring_counter_closes_other_pending_counters_in_same_hand() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[2].hand.extend(
        [
            CardInstance(instance_id=700048, card_id=48, owner_id=2, has_counter=True, counter_modes=("Counter: Attack",), energy_cost=0),
            CardInstance(instance_id=700049, card_id=49, owner_id=2, has_counter=True, counter_modes=("Counter: Attack",), energy_cost=0),
        ]
    )
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=1, attacker_zone="leader", target_player_id=2, target_zone="leader"),
    )

    legal = engine.get_legal_actions(state, 2)
    counter_actions = [a for a in legal if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND]
    assert len(counter_actions) == 2

    state = engine.apply_action(state, counter_actions[0])

    assert any(cp.name == "counter_pending_choices_closed" for cp in state.checkpoints)
    assert any("Counter pending choices closed" in row and "700049" in row for row in state.log)


def test_counter_chain_three_motions_resolve_in_descending_order() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[2].hand.extend(
        [
            CardInstance(instance_id=700061, card_id=61, owner_id=2, has_counter=True, counter_modes=("Counter: Attack",), energy_cost=0),
            CardInstance(instance_id=700062, card_id=62, owner_id=2, has_counter=True, counter_modes=("Counter: Counter",), energy_cost=0),
        ]
    )
    state.players[1].hand.append(
        CardInstance(instance_id=700063, card_id=63, owner_id=1, has_counter=True, counter_modes=("Counter: Counter",), energy_cost=0)
    )
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=1, attacker_zone="leader", target_player_id=2, target_zone="leader"),
    )
    state = engine.apply_action(state, Action(action_type=ActionType.DECLARE_COUNTER_FROM_HAND, player_id=2, hand_index=len(state.players[2].hand) - 2))
    state = engine.apply_action(state, Action(action_type=ActionType.DECLARE_COUNTER_FROM_HAND, player_id=1, hand_index=len(state.players[1].hand) - 1))
    state = engine.apply_action(state, Action(action_type=ActionType.DECLARE_COUNTER_FROM_HAND, player_id=2, hand_index=len(state.players[2].hand) - 1))
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    last_three = state.counter_resolutions[-3:]
    assert [r.motion_id for r in last_three] == [3, 2, 1]
    assert [r.resolution_order for r in last_three] == [1, 2, 3]
    assert all(r.pending_action_type == "attack" for r in last_three)
    assert last_three[0].resolved is True and last_three[0].negated_motion_id == 2
    assert last_three[1].resolved is False
    assert last_three[2].resolved is True and last_three[2].negated_motion_id is None
    assert state.attack_context is None


def test_counter_chain_on_play_window_keeps_pending_action_type_in_diagnostics() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=700084, card_id=84, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand.append(
        CardInstance(instance_id=700085, card_id=85, owner_id=2, has_counter=True, counter_modes=("Counter: Play",), energy_cost=0)
    )
    state.players[1].hand.append(
        CardInstance(instance_id=700086, card_id=86, owner_id=1, has_counter=True, counter_modes=("Counter: Counter",), energy_cost=0)
    )

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    play_counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, play_counter)
    chain_counter = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, chain_counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    last_two = state.counter_resolutions[-2:]
    assert [r.pending_action_type for r in last_two] == ["play_from_hand", "play_from_hand"]
    resolved_trace = [t for t in state.counter_motion_trace if t.resolved is not None][-2:]
    assert [t.pending_action_type for t in resolved_trace] == ["play_from_hand", "play_from_hand"]
    assert any("pending_action_type=play_from_hand" in row for row in state.log)
    assert any(card.instance_id == 700084 for card in state.players[1].battle_area)


def test_counter_chain_on_activate_main_window_keeps_pending_action_type_in_diagnostics() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=700087, card_id=87, owner_id=1, card_type="BATTLE", has_activate_main=True, energy_cost=0)
    )
    state.players[2].hand.append(
        CardInstance(instance_id=700088, card_id=88, owner_id=2, has_counter=True, counter_modes=("Counter: Counter",), energy_cost=0)
    )
    state.players[1].hand.append(
        CardInstance(instance_id=700089, card_id=89, owner_id=1, has_counter=True, counter_modes=("Counter: Counter",), energy_cost=0)
    )

    activate = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, activate)
    first_counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, first_counter)
    second_counter = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, second_counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    last_two = state.counter_resolutions[-2:]
    assert [r.pending_action_type for r in last_two] == ["activate_main", "activate_main"]
    resolved_trace = [t for t in state.counter_motion_trace if t.resolved is not None][-2:]
    assert [t.pending_action_type for t in resolved_trace] == ["activate_main", "activate_main"]
    assert any("pending_action_type=activate_main" in row for row in state.log)
    assert any(cp.name == "skill_activation_no_registered_effect" for cp in state.checkpoints)


def test_counter_chain_on_activate_battle_window_keeps_pending_action_type_in_diagnostics() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=700090, card_id=90, owner_id=1, card_type="BATTLE", power=15000, has_activate_battle=True, energy_cost=0)
    )
    state.players[2].hand.append(
        CardInstance(instance_id=700091, card_id=91, owner_id=2, has_counter=True, counter_modes=("Counter: Counter",), energy_cost=0)
    )
    state.players[1].hand.append(
        CardInstance(instance_id=700092, card_id=92, owner_id=1, has_counter=True, counter_modes=("Counter: Counter",), energy_cost=0)
    )

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    activate = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL)
    state = engine.apply_action(state, activate)
    first_counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, first_counter)
    second_counter = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, second_counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    last_two = state.counter_resolutions[-2:]
    assert [r.pending_action_type for r in last_two] == ["activate_battle", "activate_battle"]
    resolved_trace = [t for t in state.counter_motion_trace if t.resolved is not None][-2:]
    assert [t.pending_action_type for t in resolved_trace] == ["activate_battle", "activate_battle"]
    assert any("pending_action_type=activate_battle" in row for row in state.log)
    assert any(cp.name == "skill_activation_no_registered_effect" for cp in state.checkpoints)


def test_counter_chain_on_activate_extra_from_hand_window_keeps_pending_action_type_in_diagnostics() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=700093, card_id=93, owner_id=1, card_type="EXTRA", energy_cost=0),
        CardInstance(instance_id=700094, card_id=94, owner_id=1, has_counter=True, counter_modes=("Counter: Counter",), energy_cost=0),
    ]
    state.players[2].hand.append(
        CardInstance(instance_id=700095, card_id=95, owner_id=2, has_counter=True, counter_modes=("Counter: Counter",), energy_cost=0)
    )

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    first_counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, first_counter)
    second_counter = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, second_counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    last_two = state.counter_resolutions[-2:]
    assert [r.pending_action_type for r in last_two] == ["activate_extra_from_hand", "activate_extra_from_hand"]
    resolved_trace = [t for t in state.counter_motion_trace if t.resolved is not None][-2:]
    assert [t.pending_action_type for t in resolved_trace] == ["activate_extra_from_hand", "activate_extra_from_hand"]
    assert any("pending_action_type=activate_extra_from_hand" in row for row in state.log)
    assert any(card.instance_id == 700093 and card.card_type == "EXTRA" for card in state.players[1].drop)


def test_combo_power_applies_in_damage_step() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area.append(CardInstance(instance_id=700051, card_id=51, owner_id=1, power=10000))
    state.players[2].battle_area.append(CardInstance(instance_id=700052, card_id=52, owner_id=2, power=15000, resting=True))
    state.players[1].hand.append(CardInstance(instance_id=700053, card_id=53, owner_id=1, combo_cost=0, combo_power=10000, card_type="BATTLE"))
    state = engine.apply_action(
        state,
        Action(
            action_type=ActionType.DECLARE_ATTACK,
            player_id=1,
            attacker_zone="battle",
            attacker_index=0,
            target_player_id=2,
            target_zone="battle",
            target_index=0,
        ),
    )
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.COMBO_FROM_HAND, player_id=1, hand_index=len(state.players[1].hand) - 1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))


def test_counter_negate_attack_can_play_self_in_rest_mode() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[2].hand.append(
        CardInstance(
            instance_id=702001,
            card_id=201,
            owner_id=2,
            has_counter=True,
            counter_modes=("Counter: Attack",),
            energy_cost=0,
            skill_text_raw="[Counter: Attack][Limit 1] If your Leader Card is red: Negate the attack, then play this card in Rest Mode.",
        )
    )
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=1, attacker_zone="leader", target_player_id=2, target_zone="leader"),
    )
    state = engine.apply_action(state, Action(action_type=ActionType.DECLARE_COUNTER_FROM_HAND, player_id=2, hand_index=len(state.players[2].hand) - 1))
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    assert state.attack_context is None
    assert len(state.players[2].battle_area) == 1
    assert state.players[2].battle_area[0].instance_id == 702001
    assert state.players[2].battle_area[0].resting is True
    assert all(card.instance_id != 702001 for card in state.players[2].drop)
    assert any(cp.name == "counter_effect_play_self_resolved" for cp in state.checkpoints)
    assert state.counter_resolutions[-1].applied_effects == ("play_self",)
    assert any("Counter motion effects applied" in row and "effects=play_self" in row for row in state.log)


def test_counter_attack_can_play_self_and_buff_owner_card_for_battle() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[2].leader_area.color = "Red"
    state.players[2].leader_area.traits = ("Earthling",)
    state.players[2].hand.append(
        CardInstance(
            instance_id=702006,
            card_id=8896,
            owner_id=2,
            has_counter=True,
            counter_modes=("Counter: Attack",),
            energy_cost=1,
            skill_text_raw=(
                "[Counter: Attack] Play this card, then choose up to 1 of your cards and it gets +20000 power for the battle. "
                "[Permanent] If your Leader is a red ≪Earthling≫, ≪Namekian≫, or ≪Shenron≫ card, you can activate this card's [Counter] skill "
                "from your hand by adding 1 card from your life to your hand instead of paying its energy cost."
            ),
        )
    )
    starting_life = len(state.players[2].life)
    starting_leader_power = state.players[2].leader_area.power

    state = engine.apply_action(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=1, attacker_zone="leader", target_player_id=2, target_zone="leader"),
    )
    state = engine.apply_action(state, Action(action_type=ActionType.DECLARE_COUNTER_FROM_HAND, player_id=2, hand_index=len(state.players[2].hand) - 1))
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    assert len(state.players[2].life) == starting_life - 1
    assert any(card.instance_id == 702006 for card in state.players[2].battle_area)
    assert state.players[2].leader_area.power == starting_leader_power + 20000
    assert state.players[2].leader_area.battle_temporary_power_delta == 20000
    assert any(cp.name == "counter_effect_play_self_battle_buff_resolved" for cp in state.checkpoints)
    assert state.counter_resolutions[-1].applied_effects == ("play_self", "battle_buff")


def test_counter_can_mark_battle_attacker_as_unable_to_attack_again_this_turn() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    attacker = CardInstance(instance_id=702010, card_id=210, owner_id=1, power=15000)
    state.players[1].battle_area.append(attacker)
    state.players[2].hand.append(
        CardInstance(
            instance_id=702011,
            card_id=211,
            owner_id=2,
            has_counter=True,
            counter_modes=("Counter: Attack",),
            energy_cost=0,
            skill_text_raw=(
                "[Counter: Attack] Negate the attack, then play this card in Rest Mode. "
                "If the attacking card was a battle card, it can't attack for the turn."
            ),
        )
    )
    state = engine.apply_action(
        state,
        Action(
            action_type=ActionType.DECLARE_ATTACK,
            player_id=1,
            attacker_zone="battle",
            attacker_index=0,
            target_player_id=2,
            target_zone="leader",
        ),
    )
    state = engine.apply_action(state, Action(action_type=ActionType.DECLARE_COUNTER_FROM_HAND, player_id=2, hand_index=len(state.players[2].hand) - 1))
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    assert 702010 in state.attack_restricted_instance_ids
    state.players[1].battle_area[0].attacked_this_turn = False
    state.players[1].battle_area[0].resting = False
    legal = engine.get_legal_actions(state, player_id=1)
    assert all(
        not (
            action.action_type == ActionType.DECLARE_ATTACK
            and action.attacker_zone == "battle"
            and action.attacker_index == 0
        )
        for action in legal
    )
    assert any(cp.name == "counter_effect_attack_restriction_applied" for cp in state.checkpoints)


def test_counter_play_can_reduce_up_to_two_opponent_battles_for_turn_then_play_self() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=790001, card_id=601, owner_id=1, card_type="BATTLE", power=20000),
            CardInstance(instance_id=790002, card_id=602, owner_id=1, card_type="BATTLE", power=15000),
        ]
    )
    state.players[1].hand = [
        CardInstance(instance_id=790003, card_id=603, owner_id=1, card_type="BATTLE", color="Red", energy_cost=0, power=15000)
    ]
    state.players[2].energy = [CardInstance(instance_id=790004, card_id=604, owner_id=2, color="Red")]
    state.players[2].hand = [
        CardInstance(
            instance_id=790005,
            card_id=5301,
            owner_id=2,
            card_type="BATTLE",
            color="Red",
            energy_cost=1,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw=(
                "[Counter: Play] You can't activate the [Counter: Play] skills of other cards for the turn: "
                "Choose up to 2 of your opponent's Battle Cards, they get -15000 power for the turn, then play this card."
                ),
        )
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    assert any(card.instance_id == 790005 for card in state.players[2].battle_area)
    assert next(card for card in state.players[1].battle_area if card.instance_id == 790001).power == 5000
    reduced_two = next((card for card in state.players[1].battle_area if card.instance_id == 790002), None)
    assert reduced_two is None or reduced_two.power <= 0
    assert any(cp.name == "counter_effect_power_reduce_resolved" for cp in state.checkpoints)


def test_counter_play_can_restrict_other_counter_play_skills_for_the_turn() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=790101, card_id=701, owner_id=1, card_type="BATTLE", color="Red", energy_cost=0, power=15000),
        CardInstance(instance_id=790102, card_id=702, owner_id=1, card_type="BATTLE", color="Red", energy_cost=0, power=15000),
    ]
    state.players[2].energy = []
    state.players[2].hand = [
        CardInstance(
            instance_id=790103,
            card_id=5301,
            owner_id=2,
            card_type="BATTLE",
            color="Red",
            energy_cost=0,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw=(
                "[Counter: Play] You can't activate the [Counter: Play] skills of other cards for the turn: "
                "Choose up to 2 of your opponent's Battle Cards, they get -15000 power for the turn, then play this card."
            ),
        ),
        CardInstance(
            instance_id=790104,
            card_id=703,
            owner_id=2,
            card_type="EXTRA",
            color="Red",
            energy_cost=0,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw="[Counter: Play] Play this card.",
        ),
        CardInstance(
            instance_id=790105,
            card_id=704,
            owner_id=2,
            card_type="EXTRA",
            color="Blue",
            energy_cost=0,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Negate the attack.",
        ),
    ]

    first_play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, first_play)
    first_counter = next(
        a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND and a.hand_index == 0
    )
    state = engine.apply_action(state, first_counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    assert any(cp.name == "counter_effect_other_counter_mode_restriction_applied" for cp in state.checkpoints)
    assert any(
        row.owner_player_id == 2 and row.restricted_mode == "Counter: Play" for row in state.active_counter_hand_restrictions
    )

    second_play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, second_play)
    legal_play_window = engine.get_legal_actions(state, 2)
    assert not any(
        a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND and state.players[2].hand[a.hand_index].instance_id == 790104
        for a in legal_play_window
    )
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    state.players[1].leader_area.resting = False
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    legal_attack_window = engine.get_legal_actions(state, 2)
    assert any(
        a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND and state.players[2].hand[a.hand_index].instance_id == 790105
        for a in legal_attack_window
    )


def test_counter_play_alternate_cost_can_be_free_with_red_unison_markers() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=790011, card_id=611, owner_id=1, card_type="BATTLE", color="Red", energy_cost=0, power=15000)
    ]
    state.players[2].energy = []
    state.players[2].energy_markers = 0
    state.players[2].unison_area = [
        CardInstance(instance_id=790012, card_id=612, owner_id=2, card_type="UNISON", color="Red", markers=2)
    ]
    state.players[2].hand = [
        CardInstance(
            instance_id=790013,
            card_id=5301,
            owner_id=2,
            card_type="BATTLE",
            color="Red",
            energy_cost=1,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw=(
                "[Counter: Play] You can't activate the [Counter: Play] skills of other cards for the turn: "
                "Choose up to 2 of your opponent's Battle Cards, they get -15000 power for the turn, then play this card."
                "[Permanent] If you have a red Unison Card with 2 or more markers in play, you can activate this card's [Counter] skill from your hand without paying its energy cost."
                ),
        )
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)
    counter = next(a for a in legal if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    assert any(cp.name == "counter_alternate_cost_red_unison_markers_free" for cp in state.checkpoints)


def test_counter_attack_can_ko_opponent_battles_up_to_total_cost_and_limit_future_attacks() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(instance_id=790014, card_id=614, owner_id=1, card_type="BATTLE", color="Green", energy_cost=1, power=5000),
        CardInstance(instance_id=790015, card_id=615, owner_id=1, card_type="BATTLE", color="Green", energy_cost=1, power=5000),
        CardInstance(instance_id=790016, card_id=616, owner_id=1, card_type="BATTLE", color="Green", energy_cost=1, power=5000),
    ]
    state.players[1].leader_area.resting = True
    state.players[2].energy = [
        CardInstance(instance_id=790017, card_id=617, owner_id=2, color="Green", resting=False),
    ]
    state.players[2].hand = [
        CardInstance(instance_id=790018, card_id=618, owner_id=2, card_type="BATTLE", color="Green", energy_cost=0, power=5000),
        CardInstance(
            instance_id=790019,
            card_id=7358,
            owner_id=2,
            card_type="EXTRA",
            color="Green",
            energy_cost=1,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack] If your Leader Card is mono-green: Choose any number of your opponent's Battle Cards "
                "that add up to a total energy cost of 2 or less and KO them. Additionally, you may choose 1 green card "
                "in your hand and discard it. If you do, your opponent can only attack once more this turn."
            ),
        ),
    ]
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0
    )
    state = engine.apply_action(state, attack)
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    assert len(state.players[1].battle_area) == 1
    assert len(state.players[1].drop) == 2
    assert len(state.players[2].hand) == 0
    assert state.remaining_attack_declarations.get(1) == 1
    assert any(cp.name == "counter_effect_ko_total_cost_resolved" for cp in state.checkpoints)
    assert any(cp.name == "counter_effect_attack_limit_applied" for cp in state.checkpoints)


def test_counter_attack_alternate_cost_can_be_free_with_green_unison_in_play() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(instance_id=790024, card_id=624, owner_id=1, card_type="BATTLE", color="Green", energy_cost=1, power=5000),
    ]
    state.players[2].energy = []
    state.players[2].unison_area = [
        CardInstance(instance_id=790025, card_id=625, owner_id=2, card_type="UNISON", color="Green", markers=1),
    ]
    state.players[2].hand = [
        CardInstance(
            instance_id=790026,
            card_id=7358,
            owner_id=2,
            card_type="EXTRA",
            color="Green",
            energy_cost=1,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack] If your Leader Card is mono-green: Choose any number of your opponent's Battle Cards "
                "that add up to a total energy cost of 2 or less and KO them. Additionally, you may choose 1 green card "
                "in your hand and discard it. If you do, your opponent can only attack once more this turn."
                "[Permanent] If you have a green Unison Card in play, you can activate this card's [Counter] skill from your hand without paying its energy cost."
            ),
        ),
    ]
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0
    )
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    counter = next(a for a in legal if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    assert any(cp.name == "counter_alternate_cost_green_unison_free" for cp in state.checkpoints)


def test_counter_attack_can_negate_attacker_skills_and_prevent_switch_active_with_yellow_unison_free_cost() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=790027,
            card_id=626,
            owner_id=1,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=2,
            power=20000,
            keywords=("Dual Attack",),
            has_barrier=True,
            has_activate_battle=True,
        )
    ]
    state.players[2].energy = []
    state.players[2].leader_area.color = "Yellow"
    state.players[2].unison_area = [
        CardInstance(instance_id=790028, card_id=627, owner_id=2, card_type="UNISON", color="Yellow", markers=1)
    ]
    state.players[2].hand = [
        CardInstance(
            instance_id=790029,
            card_id=4226,
            owner_id=2,
            card_type="EXTRA",
            color="Yellow",
            energy_cost=1,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack] If your Leader Card is mono-yellow: Choose the attacking card, ignoring [Barrier], "
                "negate its skills for the turn, and it can't be switched to Active Mode until the start of your next turn."
                "[Permanent] If you have a yellow Unison Card in play, you can activate this card's [Counter] skill from your hand without paying its energy cost."
            ),
        )
    ]
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0
    )
    state = engine.apply_action(state, attack)
    legal_counter = engine.get_legal_actions(state, 2)
    counter = next(a for a in legal_counter if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    assert any(cp.name == "counter_alternate_cost_yellow_unison_free" for cp in state.checkpoints)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    attacker = state.players[1].battle_area[0]
    assert attacker.temporary_skills_negated is True
    assert attacker.temporary_cannot_switch_active is True
    offense_actions = engine.get_legal_actions(state, 1)
    assert not any(
        a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "battle" and a.source_index == 0
        for a in offense_actions
    )
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    assert state.players[1].battle_area[0].resting is True
    assert any(cp.name == "counter_effect_attacker_skills_negated" for cp in state.checkpoints)
    assert any(cp.name == "counter_effect_attacker_cannot_switch_active" for cp in state.checkpoints)


def test_dabura_counter_protection_prevents_opponent_skill_negation_on_owner_battle_cards() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=790030,
            card_id=8492,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            power=20000,
            has_permanent=True,
            skill_text_raw=(
                "[Dark Over Realm 4] [Blocker]\n"
                "[Permanent] Skills on your Battle Cards can't be negated by your opponent's skills.\n"
                "[Permanent] Your cards can't be switched to Rest Mode by your opponent's skills."
            ),
        ),
        CardInstance(
            instance_id=790031,
            card_id=628,
            owner_id=1,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=2,
            power=20000,
            keywords=("Dual Attack",),
            has_barrier=True,
            has_activate_battle=True,
        ),
    ]
    state.players[2].energy = []
    state.players[2].leader_area.color = "Yellow"
    state.players[2].unison_area = [
        CardInstance(instance_id=790032, card_id=629, owner_id=2, card_type="UNISON", color="Yellow", markers=1)
    ]
    state.players[2].hand = [
        CardInstance(
            instance_id=790033,
            card_id=4226,
            owner_id=2,
            card_type="EXTRA",
            color="Yellow",
            energy_cost=1,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack] If your Leader Card is mono-yellow: Choose the attacking card, ignoring [Barrier], "
                "negate its skills for the turn, and it can't be switched to Active Mode until the start of your next turn."
                "[Permanent] If you have a yellow Unison Card in play, you can activate this card's [Counter] skill from your hand without paying its energy cost."
            ),
        )
    ]
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 1
    )
    state = engine.apply_action(state, attack)
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    attacker = state.players[1].battle_area[1]
    assert attacker.temporary_skills_negated is False
    assert attacker.temporary_cannot_switch_active is True
    assert any(cp.name == "counter_effect_attacker_skill_negation_prevented" for cp in state.checkpoints)


def test_dabura_counter_protection_prevents_opponent_rest_tax_from_resting_owner_cards() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area = [
        CardInstance(
            instance_id=790034,
            card_id=8492,
            owner_id=1,
            card_type="BATTLE",
            color="Black",
            power=20000,
            has_permanent=True,
            skill_text_raw=(
                "[Dark Over Realm 4] [Blocker]\n"
                "[Permanent] Skills on your Battle Cards can't be negated by your opponent's skills.\n"
                "[Permanent] Your cards can't be switched to Rest Mode by your opponent's skills."
            ),
        ),
        CardInstance(instance_id=790035, card_id=630, owner_id=1, card_type="BATTLE", color="Black", power=15000),
        CardInstance(instance_id=790036, card_id=631, owner_id=1, card_type="BATTLE", color="Black", power=10000),
    ]
    state.non_leader_attack_rest_taxes.append(
        NonLeaderAttackRestTax(owner_player_id=2, affected_player_id=1, rest_count=1, expires_on_turn_end_player_id=2)
    )
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 1
    )
    state = engine.apply_action(state, attack)
    assert state.players[1].battle_area[0].resting is False
    assert state.players[1].battle_area[2].resting is False
    assert state.attack_context is not None
    assert any(cp.name == "non_leader_attack_rest_tax_prevented_by_protection" for cp in state.checkpoints)


def test_counter_play_can_force_pending_battle_play_rest_then_play_self_and_draw() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=790021, card_id=621, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=0, power=15000)
    ]
    state.players[2].energy = [
        CardInstance(instance_id=790022, card_id=622, owner_id=2, color="Yellow", resting=False)
    ]
    state.players[2].hand = [
        CardInstance(
            instance_id=790023,
            card_id=89,
            owner_id=2,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=1,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw=(
                "[Blocker]"
                "[Counter: Play] The Battle Card being played is played in Rest Mode, then play this card and draw 1 card."
            ),
        )
    ]
    deck_before = len(state.players[2].deck)
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    played = next(card for card in state.players[1].battle_area if card.instance_id == 790021)
    assert played.resting is True
    assert any(card.instance_id == 790023 for card in state.players[2].battle_area)
    assert len(state.players[2].deck) == deck_before - 1
    assert any(cp.name == "counter_effect_force_pending_play_rest_applied" for cp in state.checkpoints)
    assert any(cp.name == "counter_effect_play_self_draw_resolved" for cp in state.checkpoints)


def test_counter_attack_spirit_boost_can_reduce_attacker_and_remove_red_unison_marker() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[2].energy = [
        CardInstance(instance_id=790025, card_id=625, owner_id=2, color="Red", resting=False)
    ]
    state.players[2].unison_area = [
        CardInstance(instance_id=790026, card_id=626, owner_id=2, card_type="UNISON", color="Red", markers=1)
    ]
    state.players[2].hand = [
        CardInstance(
            instance_id=790027,
            card_id=7459,
            owner_id=2,
            card_type="EXTRA",
            color="Red",
            energy_cost=0,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack][Spirit Boost X] If your Leader Card is mono-red: "
                "Choose up to 1 of your opponent's cards and it gets -5000 power for the turn. "
                "If you removed a marker from one of your red Unison Cards using this skill, choose up to 1 of your opponent's cards "
                "and it gets -5000 power for the turn for each marker you removed using this skill."
            ),
        )
    ]
    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader")
    state = engine.apply_action(state, attack)
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    attacker = state.players[1].leader_area
    assert attacker.power == 5000
    assert not state.players[2].unison_area
    assert any(cp.name == "counter_effect_spirit_boost_power_reduce_resolved" for cp in state.checkpoints)
    assert any(cp.name == "counter_effect_spirit_boost_bonus_resolved" for cp in state.checkpoints)


def test_hand_cost_reduction_counts_matching_cards_across_battle_energy_and_drop() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].energy = []
    state.players[2].battle_area = [
        CardInstance(instance_id=790031, card_id=107, owner_id=2, card_type="EXTRA", color="Yellow")
    ]
    state.players[2].energy = [
        CardInstance(instance_id=790032, card_id=108, owner_id=2, card_type="EXTRA", color="Yellow", resting=False)
    ]
    state.players[2].drop = [
        CardInstance(instance_id=790033, card_id=109, owner_id=2, card_type="EXTRA", color="Yellow")
    ]
    state.players[2].hand = [
        CardInstance(
            instance_id=790034,
            card_id=89,
            owner_id=2,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=3,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw=(
                "[Counter: Play] The Battle Card being played is played in Rest Mode, then play this card and draw 1 card."
                "[Permanent] When activating this card's [Counter] skill from your hand, "
                "reduce this card's energy cost by 1 for each yellow Extra Card in your Battle Area, Energy Area, and Drop Area."
            ),
        )
    ]
    state.players[1].hand = [
        CardInstance(instance_id=790035, card_id=634, owner_id=1, card_type="BATTLE", color="Red", energy_cost=0, power=15000)
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_color_and_z_cost_gate_play_legality() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    player = state.players[1]
    player.hand = [CardInstance(instance_id=700061, card_id=61, owner_id=1, card_type="Z-BATTLE", energy_cost=1, z_energy_cost=1, color="Red")]
    player.energy = [CardInstance(instance_id=700062, card_id=62, owner_id=1, resting=False, color="Blue")]
    legal = engine.get_legal_actions(state, player_id=1)
    assert all(a.action_type != ActionType.PLAY_CARD_FROM_HAND for a in legal)
    player.energy[0].color = "Red"
    player.z_energy.append(CardInstance(instance_id=700063, card_id=63, owner_id=1))
    legal = engine.get_legal_actions(state, player_id=1)
    assert any(a.action_type == ActionType.PLAY_CARD_FROM_HAND for a in legal)


def test_damage_default_takes_first_life_card() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    p1 = state.players[1]
    p1.life = [
        CardInstance(instance_id=710001, card_id=1, owner_id=1),
        CardInstance(instance_id=710002, card_id=2, owner_id=1),
    ]
    engine._deal_damage_to_player(state, player_id=1, amount=1)
    assert [c.instance_id for c in p1.hand[-1:]] == [710001]


def test_damage_uses_life_card_chooser_callback() -> None:
    def choose_last(_player, _damage_index, max_index):
        return max_index

    engine = RulesEngine(life_card_chooser=choose_last)
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    p1 = state.players[1]
    p1.life = [
        CardInstance(instance_id=710011, card_id=11, owner_id=1),
        CardInstance(instance_id=710012, card_id=12, owner_id=1),
        CardInstance(instance_id=710013, card_id=13, owner_id=1),
    ]
    engine._deal_damage_to_player(state, player_id=1, amount=1)
    assert p1.hand[-1].instance_id == 710013


def test_activate_main_blocked_when_skill_cost_unpayable() -> None:
    def cannot_pay(_player, _card, context):
        return context != "activate_main"

    engine = RulesEngine(skill_cost_can_pay=cannot_pay)
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=710021, card_id=21, owner_id=1, has_activate_main=True, energy_cost=0, card_type="BATTLE")
    )
    legal = engine.get_legal_actions(state, player_id=1)
    assert all(a.action_type != ActionType.ACTIVATE_MAIN_SKILL for a in legal)


def test_activate_main_pays_skill_cost_via_callback() -> None:
    calls: list[tuple[int, str]] = []

    def can_pay(_player, _card, _context):
        return True

    def pay(_player, card, context):
        calls.append((card.instance_id, context))

    engine = RulesEngine(skill_cost_can_pay=can_pay, skill_cost_pay=pay)
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=710031, card_id=31, owner_id=1, has_activate_main=True, energy_cost=0, card_type="BATTLE")
    )
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL)
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert calls == [(710031, "activate_main")]


def test_activate_main_limit_one_is_not_legal_twice_in_same_turn() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(
            instance_id=710032,
            card_id=32,
            owner_id=1,
            has_activate_main=True,
            activate_limit_once_per_turn=True,
            skill_text_raw="[Activate: Main][Limit 1] Draw 1 card.",
            energy_cost=0,
            card_type="BATTLE",
        )
    )
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL)
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    legal = engine.get_legal_actions(state, 1)
    assert all(
        not (
            a.action_type == ActionType.ACTIVATE_MAIN_SKILL
            and a.source_zone == "battle"
            and a.source_index == 0
        )
        for a in legal
    )


def test_activate_main_without_registered_effect_emits_diagnostic_checkpoint() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(
            instance_id=710033,
            card_id=33,
            owner_id=1,
            has_activate_main=True,
            energy_cost=0,
            card_type="BATTLE",
            skill_text_raw="[Activate: Main] Do something unsupported.",
        )
    )
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL)
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(cp.name == "skill_activation_no_registered_effect" for cp in state.checkpoints)
    assert any("Unsupported skill activation" in line for line in state.log)


def test_counter_without_registered_family_emits_diagnostic_checkpoint() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[2].hand.append(
        CardInstance(
            instance_id=710034,
            card_id=34,
            owner_id=2,
            has_counter=True,
            counter_modes=("Counter: Attack",),
            energy_cost=0,
            skill_text_raw="[Counter: Attack] Do something unsupported.",
        )
    )
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=1, attacker_zone="leader", target_player_id=2, target_zone="leader"),
    )
    state = engine.apply_action(state, Action(action_type=ActionType.DECLARE_COUNTER_FROM_HAND, player_id=2, hand_index=len(state.players[2].hand) - 1))
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    assert any(cp.name == "counter_effect_no_registered_family" for cp in state.checkpoints)
    assert any("Unsupported counter effect" in line for line in state.log)
    assert state.counter_resolutions[-1].applied_effects == ("unsupported",)


def test_extra_activation_fails_when_skill_cost_unpayable() -> None:
    def can_pay(_player, _card, context):
        return context != "activate_extra_from_hand"

    engine = RulesEngine(skill_cost_can_pay=can_pay)
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=710041, card_id=41, owner_id=1, card_type="EXTRA", energy_cost=0)]
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(cp.name == "extra_activation_failed_skill_cost" for cp in state.checkpoints)


def test_skill_cost_dsl_discard_hand_blocks_and_pays() -> None:
    rules = {900001: {"activate_main": [{"kind": "discard_hand", "amount": 1}]}}
    engine = RulesEngine(skill_cost_rules=rules)
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=720001, card_id=900001, owner_id=1, has_activate_main=True, energy_cost=0, card_type="BATTLE")
    )
    state.players[1].hand = []

    # No hand card to discard -> activation illegal.
    legal = engine.get_legal_actions(state, player_id=1)
    assert all(
        not (
            a.action_type == ActionType.ACTIVATE_MAIN_SKILL
            and a.source_zone == "battle"
            and a.source_index == 0
        )
        for a in legal
    )

    # Add one hand card -> activation legal, and pay discards it immediately.
    state.players[1].hand.append(CardInstance(instance_id=720002, card_id=2, owner_id=1))
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL)
    state = engine.apply_action(state, action)
    assert len(state.players[1].hand) == 0
    assert any(c.instance_id == 720002 for c in state.players[1].drop)


def test_skill_cost_dsl_remove_markers_for_unison_activate_main() -> None:
    rules = {900002: {"activate_main": [{"kind": "remove_markers", "amount": 2}]}}
    engine = RulesEngine(skill_cost_rules=rules)
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    unison = CardInstance(
        instance_id=720011,
        card_id=900002,
        owner_id=1,
        card_type="UNISON",
        has_activate_main=True,
        energy_cost=0,
        markers=1,
    )
    state.players[1].unison_area.append(unison)

    # Not enough markers -> activation illegal.
    legal = engine.get_legal_actions(state, player_id=1)
    assert all(a.action_type != ActionType.ACTIVATE_MAIN_SKILL for a in legal)

    # Enough markers -> activation legal and markers are paid.
    state.players[1].unison_area[0].markers = 2
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL)
    state = engine.apply_action(state, action)
    assert len(state.players[1].unison_area) == 0
    assert any(c.instance_id == 720011 for c in state.players[1].drop)
    names = [cp.name for cp in state.checkpoints]
    assert "marker_remove_begin_skill_cost" in names
    assert "marker_removed_skill_cost" in names


def test_skill_cost_dsl_send_self_to_drop_for_battle_source() -> None:
    rules = {900003: {"activate_main": [{"kind": "send_self_to_drop", "amount": 1}]}}
    engine = RulesEngine(skill_cost_rules=rules)
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=720021, card_id=900003, owner_id=1, has_activate_main=True, energy_cost=0, card_type="BATTLE")
    )
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle")
    state = engine.apply_action(state, action)
    assert len(state.players[1].battle_area) == 0
    assert any(c.instance_id == 720021 for c in state.players[1].drop)


def test_skill_cost_dsl_send_self_to_drop_for_unison_source() -> None:
    rules = {900004: {"activate_main": [{"kind": "send_self_to_drop", "amount": 1}]}}
    engine = RulesEngine(skill_cost_rules=rules)
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].unison_area.append(
        CardInstance(instance_id=720031, card_id=900004, owner_id=1, has_activate_main=True, energy_cost=0, card_type="UNISON", markers=2)
    )
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison")
    state = engine.apply_action(state, action)
    assert len(state.players[1].unison_area) == 0
    assert any(c.instance_id == 720031 for c in state.players[1].drop)


def test_activate_main_rejects_invalid_card_type_for_zone() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    # Put a UNISON-typed card in battle area: Activate should not be offered from battle.
    state.players[1].battle_area.append(
        CardInstance(instance_id=725001, card_id=1, owner_id=1, card_type="UNISON", has_activate_main=True, energy_cost=0)
    )
    legal = engine.get_legal_actions(state, player_id=1)
    assert all(
        not (a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0)
        for a in legal
    )


def test_activate_main_pending_payload_contains_source_snapshot() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=725011, card_id=1111, owner_id=1, card_type="BATTLE", has_activate_main=True, energy_cost=0)
    )
    action = next(
        a
        for a in engine.get_legal_actions(state, player_id=1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    assert state.counter_window is not None
    payload = state.counter_window.pending_action.payload
    assert payload["source_zone"] == "battle"
    assert payload["source_index"] == 0
    assert payload["source_instance_id"] == 725011
    assert payload["source_card_id"] == 1111


def test_rule_processing_battle_card_power_zero_goes_to_drop() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(CardInstance(instance_id=730001, card_id=1, owner_id=1, power=0))
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert len(state.players[1].battle_area) == 0
    assert any(c.instance_id == 730001 for c in state.players[1].drop)
    assert any(cp.name == "rule_battle_power_zero" for cp in state.checkpoints)


def test_rule_processing_unison_power_zero_removes_marker_then_drops_at_zero() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].unison_area.append(
        CardInstance(instance_id=730011, card_id=11, owner_id=1, card_type="UNISON", power=0, markers=1)
    )
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert len(state.players[1].unison_area) == 0
    assert any(c.instance_id == 730011 for c in state.players[1].drop)
    names = [cp.name for cp in state.checkpoints]
    assert "marker_remove_begin_rule_power_zero" in names
    assert "marker_removed_rule_power_zero" in names
    assert "rule_unison_zero_markers" in names


def test_power_change_checkpoints_and_battle_zero_power_processing() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(CardInstance(instance_id=740001, card_id=1, owner_id=1, power=1000))
    state = engine.apply_power_delta(state, player_id=1, zone="battle", index=0, delta=-1000, reason="test_effect")
    names = [cp.name for cp in state.checkpoints]
    assert "power_change_begin_test_effect" in names
    assert "power_changed_test_effect" in names
    assert "rule_battle_power_zero" in names
    assert len(state.players[1].battle_area) == 0


def test_power_change_checkpoints_and_unison_rule_processing() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].unison_area.append(
        CardInstance(instance_id=740011, card_id=11, owner_id=1, card_type="UNISON", power=1000, markers=1)
    )
    state = engine.apply_power_delta(state, player_id=1, zone="unison", index=0, delta=-1000, reason="test_effect")
    names = [cp.name for cp in state.checkpoints]
    assert "power_change_begin_test_effect" in names
    assert "power_changed_test_effect" in names
    assert "marker_remove_begin_rule_power_zero" in names
    assert "marker_removed_rule_power_zero" in names
    assert "rule_unison_zero_markers" in names
    assert len(state.players[1].unison_area) == 0


def test_unison_markers_equal_energy_cards_rested_not_total_cost() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    p1 = state.players[1]
    p1.hand = [CardInstance(instance_id=700071, card_id=71, owner_id=1, card_type="UNISON", energy_cost=2)]
    p1.energy = [CardInstance(instance_id=700072, card_id=72, owner_id=1, resting=False)]
    p1.energy_markers = 1

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].markers == 1


def test_playing_unison_from_hand_replaces_existing_unison() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    p1 = state.players[1]
    p1.unison_area.append(CardInstance(instance_id=700073, card_id=73, owner_id=1, card_type="UNISON", markers=2))
    p1.hand = [CardInstance(instance_id=700074, card_id=74, owner_id=1, card_type="UNISON", energy_cost=1)]
    p1.energy = [CardInstance(instance_id=700075, card_id=75, owner_id=1, resting=False)]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].card_id == 74
    assert any(card.instance_id == 700073 for card in state.players[1].drop)
    assert any(cp.name == "unison_replaced" for cp in state.checkpoints)


def test_playing_unison_from_hand_replaces_hidden_mode_card_in_unison_area() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    p1 = state.players[1]
    p1.unison_area.append(CardInstance(instance_id=700074, card_id=740, owner_id=1, card_type="BATTLE", hidden_mode=True))
    p1.hand = [CardInstance(instance_id=700075, card_id=75, owner_id=1, card_type="UNISON", energy_cost=1)]
    p1.energy = [CardInstance(instance_id=700076, card_id=76, owner_id=1, resting=False)]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].card_id == 75
    assert any(card.instance_id == 700074 for card in state.players[1].drop)
    assert any(cp.name == "unison_replaced" for cp in state.checkpoints)


def test_unison_growth_adds_marker_once_per_turn_for_same_card_number() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].unison_area.append(
        CardInstance(instance_id=700075, card_id=75, owner_id=1, card_type="UNISON", markers=2)
    )
    state.players[1].hand = [
        CardInstance(instance_id=700076, card_id=75, owner_id=1, card_type="UNISON"),
        CardInstance(instance_id=700077, card_id=76, owner_id=1, card_type="UNISON"),
    ]
    legal = engine.get_legal_actions(state, player_id=1)
    growth_actions = [a for a in legal if a.action_type == ActionType.UNISON_GROWTH]
    assert len(growth_actions) == 1
    state = engine.apply_action(state, growth_actions[0])
    assert state.players[1].unison_area[0].markers == 3
    assert state.players[1].unison_area[0].stacked_card_ids == (75,)
    assert len(state.players[1].hand) == 1
    assert all(a.action_type != ActionType.UNISON_GROWTH for a in engine.get_legal_actions(state, player_id=1))
    assert any(cp.name == "unison_growth" for cp in state.checkpoints)


def test_unison_growth_accepts_matching_card_number_across_different_card_ids() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].unison_area.append(
        CardInstance(instance_id=700078, card_id=175, owner_id=1, card_number="BT99-001", card_type="UNISON", markers=1)
    )
    state.players[1].hand = [
        CardInstance(instance_id=700079, card_id=275, owner_id=1, card_number="BT99-001", card_type="UNISON"),
        CardInstance(instance_id=700080, card_id=276, owner_id=1, card_number="BT99-002", card_type="UNISON"),
    ]

    growth_actions = [a for a in engine.get_legal_actions(state, player_id=1) if a.action_type == ActionType.UNISON_GROWTH]
    assert len(growth_actions) == 1
    assert growth_actions[0].hand_index == 0
    state = engine.apply_action(state, growth_actions[0])
    assert state.players[1].unison_area[0].markers == 2
    assert state.players[1].unison_area[0].stacked_card_ids == (275,)


def test_unison_marker_cost_skill_locks_after_one_resolution() -> None:
    rules = {900101: {"activate_main": [{"kind": "remove_markers", "amount": 1}]}}
    engine = RulesEngine(skill_cost_rules=rules)
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].unison_area.append(
        CardInstance(
            instance_id=700078,
            card_id=900101,
            owner_id=1,
            card_type="UNISON",
            has_activate_main=True,
            energy_cost=0,
            markers=3,
        )
    )
    action = next(
        a
        for a in engine.get_legal_actions(state, player_id=1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert 700078 in state.unison_marker_skill_usage
    legal = engine.get_legal_actions(state, player_id=1)
    assert all(
        not (
            a.action_type == ActionType.ACTIVATE_MAIN_SKILL
            and a.source_zone == "unison"
            and a.source_index == 0
        )
        for a in legal
    )


def test_skill_cost_dsl_add_markers_for_unison_activate_main() -> None:
    rules = {900102: {"activate_main": [{"kind": "add_markers", "amount": 2}]}}
    engine = RulesEngine(skill_cost_rules=rules)
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].unison_area.append(
        CardInstance(
            instance_id=700079,
            card_id=900102,
            owner_id=1,
            card_type="UNISON",
            has_activate_main=True,
            energy_cost=0,
            markers=1,
        )
    )
    action = next(
        a
        for a in engine.get_legal_actions(state, player_id=1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].unison_area[0].markers == 3


def test_unison_add_marker_skill_locks_after_one_resolution() -> None:
    rules = {900103: {"activate_main": [{"kind": "add_markers", "amount": 1}]}}
    engine = RulesEngine(skill_cost_rules=rules)
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].unison_area.append(
        CardInstance(
            instance_id=700080,
            card_id=900103,
            owner_id=1,
            card_type="UNISON",
            has_activate_main=True,
            energy_cost=0,
            markers=1,
        )
    )
    action = next(
        a
        for a in engine.get_legal_actions(state, player_id=1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].unison_area[0].markers == 2
    assert 700080 in state.unison_marker_skill_usage
    legal = engine.get_legal_actions(state, player_id=1)
    assert all(
        not (
            a.action_type == ActionType.ACTIVATE_MAIN_SKILL
            and a.source_zone == "unison"
            and a.source_index == 0
        )
        for a in legal
    )


def test_hidden_mode_battle_card_cannot_attack_or_activate_skill() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(
            instance_id=700081,
            card_id=81,
            owner_id=1,
            card_type="BATTLE",
            hidden_mode=True,
            has_activate_main=True,
        )
    )
    legal = engine.get_legal_actions(state, player_id=1)
    assert all(
        not (
            a.action_type == ActionType.DECLARE_ATTACK
            and a.attacker_zone == "battle"
            and a.attacker_index == 0
        )
        for a in legal
    )


def test_counter_play_can_hide_exact_owner_battle_as_cost_and_reveal_it_at_turn_end() -> None:
    rules = {
        900301: {
            "counter_from_hand": [
                {
                    "kind": "switch_owner_battle_to_hidden",
                    "amount": 1,
                    "allowed_colors": "white",
                }
            ]
        }
    }
    engine = RulesEngine(skill_cost_rules=rules)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=780001, card_id=501, owner_id=1, card_type="BATTLE", energy_cost=0)
    ]
    state.players[2].battle_area.extend(
        [
            CardInstance(instance_id=780002, card_id=502, owner_id=2, card_type="BATTLE", color="White"),
            CardInstance(instance_id=780003, card_id=503, owner_id=2, card_type="BATTLE", color="Red"),
        ]
    )
    state.players[2].hand.append(
        CardInstance(
            instance_id=780004,
            card_id=900301,
            owner_id=2,
            card_type="BATTLE",
            color="White",
            energy_cost=0,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw=(
                "[Counter: Play][Limit 1] Choose 1 of your white Battle Cards and switch it to Hidden Mode: "
                "Play this card, then switch the card that was switched to Hidden Mode by this skill to Revealed Mode at the end of the turn."
            ),
        )
    )

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    assert state.players[2].battle_area[0].hidden_mode is True
    assert state.players[2].battle_area[1].hidden_mode is False
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    assert any(card.instance_id == 780004 for card in state.players[2].battle_area)
    assert any(cp.name == "counter_effect_delayed_reveal_scheduled" for cp in state.checkpoints)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert state.players[2].battle_area[0].hidden_mode is False
    assert any(cp.name == "delayed_mode_switch_resolved" for cp in state.checkpoints)


def test_counter_play_self_can_switch_self_to_hidden_mode() -> None:
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
        CardInstance(instance_id=780010, card_id=510, owner_id=1, card_type="BATTLE", energy_cost=0)
    ]
    state.players[2].hand.append(
        CardInstance(
            instance_id=780011,
            card_id=910011,
            owner_id=2,
            card_type="BATTLE",
            color="White",
            energy_cost=0,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw="[Counter: Play][Limit 1] Play this card, then switch it to Hidden Mode.",
        )
    )

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    played = next(card for card in state.players[2].battle_area if card.instance_id == 780011)
    assert played.hidden_mode is True
    assert any(cp.name == "counter_effect_switch_self_hidden_resolved" for cp in state.checkpoints)


def test_counter_attack_can_switch_opponent_battle_to_hidden_then_reveal_on_turn_end() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=780020, card_id=520, owner_id=1, card_type="BATTLE", power=15000),
            CardInstance(instance_id=780021, card_id=521, owner_id=1, card_type="BATTLE", power=10000),
        ]
    )
    state.players[2].battle_area.extend(
        [
            CardInstance(instance_id=780022, card_id=522, owner_id=2, card_type="BATTLE", hidden_mode=True),
            CardInstance(instance_id=780023, card_id=523, owner_id=2, card_type="BATTLE", hidden_mode=True),
        ]
    )
    state.players[2].hand.append(
        CardInstance(
            instance_id=780024,
            card_id=910024,
            owner_id=2,
            card_type="EXTRA",
            color="White",
            energy_cost=0,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack][Limit 1] Negate the attack, choose any number of your opponent's Battle Cards "
                "up to the number of your Hidden Mode cards and switch them to Hidden Mode, then switch all the cards "
                "switched to Hidden Mode by this skill to Revealed Mode at the end of the turn."
            ),
        )
    )

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    assert state.players[1].battle_area[0].hidden_mode is True
    assert state.players[1].battle_area[1].hidden_mode is True
    assert any(cp.name == "counter_effect_hidden_then_reveal_scheduled" for cp in state.checkpoints)

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))

    assert state.players[1].battle_area[0].hidden_mode is False
    assert state.players[1].battle_area[1].hidden_mode is False
    assert any(cp.name == "delayed_mode_switch_resolved" for cp in state.checkpoints)


def test_counter_attack_can_switch_owner_energy_to_hidden_then_draw() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[2].energy.append(CardInstance(instance_id=780030, card_id=530, owner_id=2, card_type="EXTRA", color="White"))
    deck_before = len(state.players[2].deck)
    hand_before = len(state.players[2].hand)
    state.players[2].hand.append(
        CardInstance(
            instance_id=780031,
            card_id=910031,
            owner_id=2,
            card_type="EXTRA",
            color="White",
            energy_cost=0,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack] Negate the attack. Additionally, you may switch 1 of your white energy to Hidden Mode. "
                "If you do, draw 1 card."
            ),
        )
    )

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    assert state.players[2].energy[0].hidden_mode is True
    assert len(state.players[2].deck) == deck_before - 1
    assert len(state.players[2].hand) == hand_before + 1
    assert any(cp.name == "counter_effect_switch_owner_energy_hidden_then_draw" for cp in state.checkpoints)


def test_counter_attack_can_discard_then_switch_owner_card_to_hidden() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[2].battle_area.append(CardInstance(instance_id=780040, card_id=540, owner_id=2, card_type="BATTLE", color="White"))
    state.players[2].hand = [
        CardInstance(instance_id=780041, card_id=541, owner_id=2, card_type="BATTLE", color="Blue"),
        CardInstance(
            instance_id=780042,
            card_id=910042,
            owner_id=2,
            card_type="EXTRA",
            color="White",
            energy_cost=0,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack] Negate the attack. Additionally, you may discard 1 card from your hand. "
                "If you do, choose up to 1 of your white cards and switch it to Hidden Mode."
            ),
        ),
    ]

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    assert state.players[2].battle_area[0].hidden_mode is True
    assert any(card.card_id == 541 for card in state.players[2].drop)
    assert any(cp.name == "counter_effect_discard_then_switch_owner_card_hidden" for cp in state.checkpoints)


def test_counter_play_self_can_redirect_attack_to_self_and_hide_white_battle_at_battle_end() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[2].hand.append(
        CardInstance(
            instance_id=780043,
            card_id=910043,
            owner_id=2,
            card_type="BATTLE",
            color="White",
            power=20000,
            energy_cost=0,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack][Limit 1] Play this card, switch the target of attack to it, "
                "then choose up to 1 of your white Battle Cards and switch it to Hidden Mode at the end of the battle."
            ),
        )
    )

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    jiren = next(card for card in state.players[2].battle_area if card.instance_id == 780043)
    assert state.battle_step == BattleStep.OFFENSE
    assert state.attack_context is not None
    assert state.attack_context.target_player_id == 2
    assert state.attack_context.target_zone == "battle"
    assert state.attack_context.target_instance_id == jiren.instance_id
    assert any(cp.name == "counter_effect_redirect_to_self_resolved" for cp in state.checkpoints)
    assert any(cp.name == "counter_effect_delayed_hidden_battle_end_scheduled" for cp in state.checkpoints)
    assert state.counter_resolutions[-1].applied_effects == ("play_self", "redirect_to_self", "delayed_hidden_battle_end")

    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))

    jiren = next(card for card in state.players[2].battle_area if card.instance_id == 780043)
    assert jiren.hidden_mode is True
    assert any(cp.name == "delayed_mode_switch_resolved" for cp in state.checkpoints)


def test_counter_attack_can_use_hidden_mode_battle_rest_as_alternate_cost() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[2].leader_area.color = "White"
    state.players[2].battle_area.append(
        CardInstance(instance_id=780044, card_id=544, owner_id=2, card_type="BATTLE", color="White", hidden_mode=True, resting=False)
    )
    state.players[2].hand.append(
        CardInstance(
            instance_id=780045,
            card_id=8943,
            owner_id=2,
            card_type="EXTRA",
            color="White",
            energy_cost=1,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack] Negate the attack. Additionally, you may switch 1 of your white energy to Hidden Mode. If you do, draw 1 card. "
                "[Permanent] If your Leader is white, you can activate this card's [Counter] skill from your hand by switching 1 Hidden Mode card in your Battle Area to Rest Mode instead of paying its energy cost."
            ),
        )
    )

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)
    counter = next(a for a in legal if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    assert state.players[2].battle_area[0].resting is True
    assert any(cp.name == "counter_alternate_cost_hidden_battle_rested" for cp in state.checkpoints)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    assert state.attack_context is None


def test_counter_attack_can_use_sparking_life_to_hand_as_alternate_cost() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[2].drop.extend(
        [CardInstance(instance_id=780050 + i, card_id=550 + i, owner_id=2, card_type="BATTLE") for i in range(5)]
    )
    life_before = len(state.players[2].life)
    state.players[2].battle_area.append(CardInstance(instance_id=780056, card_id=556, owner_id=2, card_type="BATTLE", color="White"))
    state.players[2].hand = [
        CardInstance(instance_id=780057, card_id=557, owner_id=2, card_type="BATTLE", color="Blue"),
        CardInstance(
            instance_id=780058,
            card_id=9775,
            owner_id=2,
            card_type="EXTRA",
            color="White",
            energy_cost=1,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack] Negate the attack. Additionally, you may discard 1 card from your hand. If you do, choose up to 1 of your white cards and switch it to Hidden Mode. "
                "[Permanent][Sparking 5] You can activate this card's [Counter] skill from your hand by adding 1 card from your life to your hand instead of paying its energy cost."
            ),
        ),
    ]

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)
    counter = next(a for a in legal if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    assert len(state.players[2].life) == life_before - 1
    assert any(cp.name == "counter_alternate_cost_life_to_hand" for cp in state.checkpoints)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    assert state.attack_context is None
    assert state.players[2].battle_area[0].hidden_mode is True


def test_extra_from_hand_uses_activate_extra_counter_window() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    p1 = state.players[1]
    p2 = state.players[2]
    p1.hand = [CardInstance(instance_id=700081, card_id=81, owner_id=1, card_type="EXTRA", energy_cost=0)]
    p2.hand.append(
        CardInstance(instance_id=700082, card_id=82, owner_id=2, has_counter=True, counter_modes=("Counter: Play",), energy_cost=0)
    )
    p2.hand.append(
        CardInstance(instance_id=700083, card_id=83, owner_id=2, has_counter=True, counter_modes=("Counter: Counter",), energy_cost=0)
    )

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    # Extra card moves to Drop immediately on declaration.
    assert len(state.players[1].drop) == 1
    assert state.players[1].drop[0].card_type == "EXTRA"
    legal = engine.get_legal_actions(state, 2)
    # Counter:Play should not be legal in extra activation window.
    play_counter_indexes = {i for i, c in enumerate(state.players[2].hand) if "Counter: Play" in c.counter_modes}
    legal_counter_indexes = {a.hand_index for a in legal if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND}
    assert play_counter_indexes.isdisjoint(legal_counter_indexes)

    # Passing resolves extra activation, card goes to drop.
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].drop) == 1
    assert state.players[1].drop[0].card_type == "EXTRA"
    assert any(cp.name == "extra_moved_to_drop_on_declare" for cp in state.checkpoints)


def test_specified_cost_blocks_play_without_required_color() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    p1 = state.players[1]
    p1.hand = [
        CardInstance(
            instance_id=760001,
            card_id=6001,
            owner_id=1,
            card_type="BATTLE",
            energy_cost=2,
            color="Red",
            specified_costs=(("R", 1),),
        )
    ]
    p1.energy = [
        CardInstance(instance_id=760002, card_id=2, owner_id=1, color="Blue", resting=False),
        CardInstance(instance_id=760003, card_id=3, owner_id=1, color="Blue", resting=False),
    ]
    legal = engine.get_legal_actions(state, player_id=1)
    assert all(a.action_type != ActionType.PLAY_CARD_FROM_HAND for a in legal)


def test_specified_cost_allows_marker_substitution() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    p1 = state.players[1]
    p1.hand = [
        CardInstance(
            instance_id=760011,
            card_id=6011,
            owner_id=1,
            card_type="BATTLE",
            energy_cost=2,
            color="Red",
            specified_costs=(("R", 1),),
        )
    ]
    p1.energy = [CardInstance(instance_id=760012, card_id=12, owner_id=1, color="Blue", resting=False)]
    p1.energy_markers = 1
    legal = engine.get_legal_actions(state, player_id=1)
    assert any(a.action_type == ActionType.PLAY_CARD_FROM_HAND for a in legal)


def test_specified_cost_payment_uses_matching_energy_first() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    p1 = state.players[1]
    p1.hand = [
        CardInstance(
            instance_id=760021,
            card_id=6021,
            owner_id=1,
            card_type="BATTLE",
            energy_cost=2,
            color="Red",
            specified_costs=(("R", 1),),
        )
    ]
    # Blue first, then red: payment should still rest red to satisfy specified pip.
    p1.energy = [
        CardInstance(instance_id=760022, card_id=22, owner_id=1, color="Blue", resting=False),
        CardInstance(instance_id=760023, card_id=23, owner_id=1, color="Red", resting=False),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    assert state.players[1].energy[1].resting is True


def test_zero_deck_does_not_lose_until_draw_is_required() -> None:
    engine = RulesEngine()
    # 14 cards are fully consumed by setup (6 hand + 8 life).
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000, 14),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000, 14),
        first_player=1,
        shuffle_decks=False,
    )
    assert state.players[1].deck == []
    assert state.winner_id is None

    # First player's first turn skips draw, still no loss.
    state = _to_main(engine, state)
    assert state.winner_id is None

    # If opponent must draw with empty deck, that player loses.
    state.players[2].deck = []
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert state.winner_id == 1


def test_rule_processing_repeats_zero_power_unison_until_it_leaves() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].unison_area.append(
        CardInstance(instance_id=770001, card_id=1, owner_id=1, card_type="UNISON", power=0, markers=3)
    )
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert len(state.players[1].unison_area) == 0
    assert any(c.instance_id == 770001 for c in state.players[1].drop)
    marker_removed = [cp for cp in state.checkpoints if cp.name == "marker_removed_rule_power_zero"]
    assert len(marker_removed) >= 3


def test_skill_cost_dsl_send_other_battle_to_warp() -> None:
    rules = {900005: {"activate_main": [{"kind": "send_other_battle_to_warp", "amount": 1}]}}
    engine = RulesEngine(skill_cost_rules=rules)
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=770011, card_id=900005, owner_id=1, has_activate_main=True, energy_cost=0, card_type="BATTLE")
    )
    state.players[1].battle_area.append(CardInstance(instance_id=770012, card_id=2, owner_id=1, card_type="BATTLE", energy_cost=0))
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    assert any(c.instance_id == 770012 for c in state.players[1].warp)
    assert all(c.instance_id != 770012 for c in state.players[1].battle_area)


def test_skill_cost_dsl_send_self_to_removed() -> None:
    rules = {900006: {"activate_main": [{"kind": "send_self_to_removed", "amount": 1}]}}
    engine = RulesEngine(skill_cost_rules=rules)
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), shuffle_decks=False
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=770021, card_id=900006, owner_id=1, has_activate_main=True, energy_cost=0, card_type="BATTLE")
    )
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    )
    state = engine.apply_action(state, action)
    assert len(state.players[1].battle_area) == 0
    assert any(c.instance_id == 770021 for c in state.players[1].removed_from_game)


def test_ss_vegito_power_release_can_counter_with_life_and_drop_to_warp_and_buff_for_battle() -> None:
    engine = RulesEngine(
        skill_cost_rules={
            8233: {
                "counter_alternate_from_hand": [
                    {"kind": "add_life_to_hand", "amount": 1, "required_leader_colors": "red"},
                    {"kind": "send_owner_drop_to_warp", "amount": 2, "required_traits": "saiyan"},
                ]
            }
        },
        effect_rule_overrides={
            8233: {
                "mode": "replace",
                "rules": [
                    {
                        "trigger": "counter_attack",
                        "handler_id": "counter_play_self_buff_owner_cards_for_battle",
                        "handler_params": {"max_targets": 1, "power_delta": 30000, "target_scope": "owner_cards"},
                        "limit_per_turn": 1,
                    },
                ],
            }
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1, p1_deck_card_ids=_deck(1000), p2_leader_card_id=2, p2_deck_card_ids=_deck(2000), first_player=2, shuffle_decks=False
    )
    state = _to_p2_main(engine, state)
    state.players[2].leader_area.color = "Red"
    starting_life = len(state.players[2].life)
    starting_leader_power = state.players[2].leader_area.power
    state.players[2].drop = [
        CardInstance(instance_id=770031, card_id=9301, owner_id=2, card_type="BATTLE", color="Red", traits=("Saiyan",), characters=("Goku",)),
        CardInstance(instance_id=770032, card_id=9302, owner_id=2, card_type="BATTLE", color="Blue", traits=("Saiyan",), characters=("Vegeta",)),
    ]
    state.players[2].hand = [
        CardInstance(
            instance_id=770033,
            card_id=8233,
            owner_id=2,
            card_type="BATTLE",
            color="Red",
            energy_cost=6,
            has_counter=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Blocker][Counter: Attack][Limit 1] Play this card, then choose up to 1 of your cards and it gets +30000 power for the battle. "
                "[Permanent] If your Leader is red, you can activate this card's [Counter] skill from your hand by adding 1 card from your life to your hand and sending 2 â‰ªSaiyanâ‰« cards from your Drop to their owner's Warp instead of paying its energy cost."
            ),
        )
    ]
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=1, attacker_zone="leader", target_player_id=2, target_zone="leader"),
    )
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    assert len(state.players[2].life) == starting_life - 1
    assert len(state.players[2].warp) == 2
    assert len(state.players[2].drop) == 0
    assert any(card.instance_id == 770033 for card in state.players[2].battle_area)
    assert state.players[2].leader_area.power == starting_leader_power + 30000
    assert state.players[2].leader_area.battle_temporary_power_delta == 30000
    assert any(cp.name == "counter_effect_play_self_battle_buff_resolved" for cp in state.checkpoints)


def test_super_kamehameha_can_send_pending_play_to_warp_if_cost_at_most() -> None:
    engine = RulesEngine()
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
        CardInstance(instance_id=780201, card_id=98201, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=0, power=20000)
    ]
    state.players[2].leader_area.color = "Black"
    state.players[2].life = state.players[2].life[:4]
    state.players[2].energy = [
        CardInstance(instance_id=780202, card_id=98202, owner_id=2, card_type="ENERGY", color="Black", energy_cost=0)
    ]
    state.players[2].hand = [
        CardInstance(
            instance_id=780203,
            card_id=6997,
            owner_id=2,
            card_type="EXTRA",
            color="Black",
            energy_cost=0,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw=(
                "[Counter: Play] If your Leader Card is black and your life is at 4 or less: "
                "If the Battle Card being played has an energy cost of 3 or less, it is sent to its owner's Warp instead of being played. "
                "[Permanent] If you have only black cards in your energy and your life is at 4 or less, "
                "you can activate this card's [Counter] skill from your hand by adding a card from your life to your hand instead of paying its energy cost."
            ),
        )
    ]

    state = engine.apply_action(state, Action(action_type=ActionType.PLAY_CARD_FROM_HAND, player_id=1, hand_index=0))
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    assert any(card.instance_id == 780201 for card in state.players[1].warp)
    assert all(card.instance_id != 780201 for card in state.players[1].battle_area)
    assert any(cp.name == "counter_effect_pending_play_to_warp_scheduled" for cp in state.checkpoints)
    assert any(cp.name == "play_replaced_to_warp" for cp in state.checkpoints)


def test_king_vegeta_counter_applies_attack_power_tax_and_restricts_hand_copies_for_turn() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=780001, card_id=9801, owner_id=2, card_type="BATTLE", color="Blue", power=20000),
        CardInstance(instance_id=780002, card_id=9802, owner_id=2, card_type="BATTLE", color="Blue", power=15000),
    ]
    state.players[1].leader_area.color = "Red"
    state.players[1].leader_area.traits = ("Saiyan",)
    state.players[1].hand = [
        CardInstance(
            instance_id=780003,
            card_id=6581,
            owner_id=1,
            card_type="EXTRA",
            color="Red",
            energy_cost=0,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack] If your Leader Card is a mono-red ≪Saiyan≫ card: You may choose the attacking card, ignoring [Barrier], "
                "and it gets -10000 power for the turn; your opponent can't attack with cards for the turn unless they give the attacking card -5000 power for the turn each time. "
                "You can't activate copies of this card from your hand for the turn."
            ),
        ),
        CardInstance(
            instance_id=780004,
            card_id=6581,
            owner_id=1,
            card_type="EXTRA",
            color="Red",
            energy_cost=0,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack] If your Leader Card is a mono-red ≪Saiyan≫ card: You may choose the attacking card, ignoring [Barrier], "
                "and it gets -10000 power for the turn; your opponent can't attack with cards for the turn unless they give the attacking card -5000 power for the turn each time. "
                "You can't activate copies of this card from your hand for the turn."
            ),
        ),
    ]
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=2, attacker_zone="battle", attacker_index=0, target_player_id=1, target_zone="leader"),
    )
    counter = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    first_attacker = state.players[2].battle_area[0]
    assert first_attacker.temporary_power_delta == -10000
    assert len(state.attack_power_taxes) == 1
    assert len(state.active_counter_hand_restrictions) == 1
    assert any(cp.name == "counter_effect_attacker_power_reduce_applied" for cp in state.checkpoints)
    assert any(cp.name == "counter_effect_attack_power_tax_applied" for cp in state.checkpoints)
    assert any(cp.name == "counter_effect_hand_counter_restriction_applied" for cp in state.checkpoints)

    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=2))
    state.phase = TurnPhase.MAIN
    state.attack_context = None
    state.battle_step = None
    state.players[2].leader_area.resting = False
    engine._declare_attack(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=2, attacker_zone="leader", target_player_id=1, target_zone="leader"),
    )
    second_attacker = state.players[2].leader_area
    assert second_attacker.temporary_power_delta == -5000
    assert any(cp.name == "attack_power_tax_applied" for cp in state.checkpoints)
    legal_counter = engine.get_legal_actions(state, 1)
    assert not any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal_counter)


def test_counter_can_permanently_restrict_hand_copies_for_game() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_p2_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=780011, card_id=9811, owner_id=2, card_type="BATTLE", color="Blue", power=20000),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=780012,
            card_id=6591,
            owner_id=1,
            card_type="EXTRA",
            color="Blue",
            energy_cost=0,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack] Negate the attack. "
                "You can't activate the [Counter: Attack] skill on copies of this card for the game."
            ),
        ),
        CardInstance(
            instance_id=780013,
            card_id=6591,
            owner_id=1,
            card_type="EXTRA",
            color="Blue",
            energy_cost=0,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw=(
                "[Counter: Attack] Negate the attack. "
                "You can't activate the [Counter: Attack] skill on copies of this card for the game."
            ),
        ),
    ]

    state = engine.apply_action(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=2, attacker_zone="battle", attacker_index=0, target_player_id=1, target_zone="leader"),
    )
    counter = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert len(state.permanent_skill_activation_restrictions) == 1
    assert any(cp.name == "counter_effect_permanent_copy_counter_restriction_applied" for cp in state.checkpoints)
    assert engine._is_counter_hand_activation_restricted(state, player_id=1, card=state.players[1].hand[0])

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)
    state.attack_context = None
    state.battle_step = None
    state.players[2].leader_area.resting = False
    engine._declare_attack(
        state,
        Action(action_type=ActionType.DECLARE_ATTACK, player_id=2, attacker_zone="leader", target_player_id=1, target_zone="leader"),
    )

    legal_counter = engine.get_legal_actions(state, 1)
    assert not any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal_counter)


def test_prismatic_burst_counter_play_can_replace_small_pending_play_with_drop() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = []
    state.players[1].hand = [
        CardInstance(instance_id=780011, card_id=9811, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=0, power=20000)
    ]
    state.players[2].energy = []
    state.players[2].hand = [
        CardInstance(
            instance_id=780012,
            card_id=40,
            owner_id=2,
            card_type="BATTLE",
            color="Black",
            energy_cost=0,
            power=15000,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw=(
                "[Counter: Play] Play this card, and if the Battle Card being played has 20000 power or less, "
                "place it in its owner's Drop Area instead."
            ),
        )
    ]
    state = engine.apply_action(state, Action(action_type=ActionType.PLAY_CARD_FROM_HAND, player_id=1, hand_index=0))
    counter = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, counter)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    assert any(card.instance_id == 780012 for card in state.players[2].battle_area)
    assert any(card.instance_id == 780011 for card in state.players[1].drop)
    assert all(card.instance_id != 780011 for card in state.players[1].battle_area)
    assert any(cp.name == "counter_effect_pending_play_to_drop_scheduled" for cp in state.checkpoints)
    assert any(cp.name == "play_replaced_to_drop" for cp in state.checkpoints)
