from __future__ import annotations

from types import SimpleNamespace

from src.game import Action, ActionType, CardInstance, RulesEngine, TurnPhase


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _to_main(engine: RulesEngine, state):
    while state.phase != TurnPhase.MAIN:
        state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=state.active_player))
    return state


def test_play_from_hand_requires_payable_energy_cost() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 900001:
                return SimpleNamespace(
                    power_int=15000,
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
                )
            return SimpleNamespace(power_int=15000, card_type="BATTLE", card_color="Blue", energy_cost_int=0, keywords=())

    engine = RulesEngine(card_repository=Repo())
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900001] + _deck(1000, 59),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    legal = engine.get_legal_actions(state, player_id=1)
    assert all(not (a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0) for a in legal)


def test_play_from_hand_uses_energy_markers_for_cost() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 910001:
                return SimpleNamespace(
                    power_int=15000,
                    card_type="BATTLE",
                    card_color="Green",
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
                )
            return SimpleNamespace(power_int=15000, card_type="BATTLE", card_color="Blue", energy_cost_int=0, keywords=())

    engine = RulesEngine(card_repository=Repo())
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=[910001] + _deck(2000, 59),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)  # P2 main with 1 energy marker

    action = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))
    assert state.players[2].energy_markers == 0
    assert len(state.players[2].battle_area) == 1


def test_activate_main_requires_flag_and_cost_payment() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)

    activator = CardInstance(
        instance_id=888001,
        card_id=123,
        owner_id=1,
        power=15000,
        card_type="BATTLE",
        has_activate_main=True,
        energy_cost=1,
    )
    state.players[1].battle_area.append(activator)
    state.players[1].energy.append(CardInstance(instance_id=888002, card_id=456, owner_id=1, resting=False))

    legal = engine.get_legal_actions(state, player_id=1)
    activate = next(a for a in legal if a.action_type == ActionType.ACTIVATE_MAIN_SKILL)
    state = engine.apply_action(state, activate)
    assert state.players[1].energy[0].resting is True


def test_leader_activate_main_is_legal_and_pays_cost() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)

    state.players[1].leader_area.has_activate_main = True
    state.players[1].leader_area.energy_cost = 1
    state.players[1].energy.append(CardInstance(instance_id=777001, card_id=9, owner_id=1, resting=False))

    legal = engine.get_legal_actions(state, player_id=1)
    leader_activate = next(
        a for a in legal if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "leader"
    )
    state = engine.apply_action(state, leader_activate)
    assert state.players[1].energy[0].resting is True
