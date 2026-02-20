from __future__ import annotations

from src.game import Action, ActionType, CardInstance, RulesEngine, TurnPhase


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _to_main_phase_for_active_player(engine: RulesEngine, state):
    while state.phase != TurnPhase.MAIN:
        if state.phase == TurnPhase.CHARGE:
            state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=state.active_player))
        else:
            raise AssertionError(f"Unexpected phase: {state.phase}")
    return state


def _to_next_player_main(engine: RulesEngine, state):
    state = _to_main_phase_for_active_player(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main_phase_for_active_player(engine, state)
    return state


def _resolve_battle_without_combos(engine: RulesEngine, state, attacker_player: int, defender_player: int):
    # Counter timing after attack declaration.
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=defender_player))
    # Offense step -> Defense step.
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=attacker_player))
    # Defense step -> Damage step.
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=defender_player))
    # Damage resolution then battle-end cleanup.
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=attacker_player))
    if state.winner_id is None:
        state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=attacker_player))
    return state


def test_first_player_cannot_attack_on_first_turn() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main_phase_for_active_player(engine, state)
    legal = engine.get_legal_actions(state, player_id=1)
    assert all(action.action_type != ActionType.DECLARE_ATTACK for action in legal)


def test_leader_attack_declares_and_resolves_damage() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_next_player_main(engine, state)  # P2 main, can attack.
    attacker = state.players[2].leader_area
    attacker.power = 20000
    target_life_before = len(state.players[1].life)

    declare = Action(
        action_type=ActionType.DECLARE_ATTACK,
        player_id=2,
        attacker_zone="leader",
        target_player_id=1,
        target_zone="leader",
    )
    state = engine.apply_action(state, declare)
    assert state.attack_context is not None
    assert state.battle_step is None
    assert state.players[2].leader_area.resting is True

    state = _resolve_battle_without_combos(engine, state, attacker_player=2, defender_player=1)
    assert state.attack_context is None
    assert state.battle_step is None
    assert len(state.players[1].life) == target_life_before - 1


def test_battle_vs_rest_battle_kos_target_to_drop() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_next_player_main(engine, state)  # P1 main and allowed to attack.

    p1 = state.players[1]
    p2 = state.players[2]
    attacker = CardInstance(instance_id=900001, card_id=11, owner_id=1, resting=False, power=25000)
    defender = CardInstance(instance_id=900002, card_id=22, owner_id=2, resting=True, power=10000)
    p1.battle_area.append(attacker)
    p2.battle_area.append(defender)

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
    state = _resolve_battle_without_combos(engine, state, attacker_player=1, defender_player=2)

    assert len(state.players[2].battle_area) == 0
    assert len(state.players[2].drop) == 1
    assert state.players[2].drop[0].instance_id == 900002


def test_life_zero_sets_winner() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_next_player_main(engine, state)  # P2 main.
    state.players[2].leader_area.power = 30000
    state.players[1].life = [state.players[1].life[0]]

    state = engine.apply_action(
        state,
        Action(
            action_type=ActionType.DECLARE_ATTACK,
            player_id=2,
            attacker_zone="leader",
            target_player_id=1,
            target_zone="leader",
        ),
    )
    state = _resolve_battle_without_combos(engine, state, attacker_player=2, defender_player=1)
    assert state.winner_id == 2
