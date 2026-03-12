from __future__ import annotations

from types import SimpleNamespace
import pytest

from src.game import Action, ActionType, RulesEngine, RulesViolation, TurnPhase


def _deck(seed: int, size: int = 30) -> list[int]:
    return [seed + i for i in range(size)]


def test_initialize_game_sets_zones_and_phase() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1001,
        p1_deck_card_ids=_deck(10000),
        p2_leader_card_id=2001,
        p2_deck_card_ids=_deck(20000),
    )

    p1 = state.players[1]
    p2 = state.players[2]

    assert len(p1.life) == 8
    assert len(p1.hand) == 6
    assert len(p1.deck) == 16
    assert len(p2.life) == 8
    assert len(p2.hand) == 6
    assert len(p2.deck) == 16
    assert state.phase == TurnPhase.CHARGE
    assert state.active_player == 1
    assert p2.energy_markers == 1
    assert p1.leader_area.card_id == 1001
    assert p2.leader_area.card_id == 2001
    assert p1.z_deck == []
    assert p2.z_deck == []
    assert p1.drop == []
    assert p1.warp == []
    assert p1.removed_from_game == []
    assert p2.drop == []
    assert p2.warp == []
    assert p2.removed_from_game == []
    assert len(state.checkpoints) >= 1


def test_first_player_first_turn_skips_draw() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(10),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(100),
        shuffle_decks=False,
    )

    assert state.phase == TurnPhase.CHARGE
    assert len(state.players[1].hand) == 6


def test_charge_from_hand_moves_card_to_active_energy_and_main() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(10),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(100),
        shuffle_decks=False,
    )

    charged = engine.apply_action(
        state,
        Action(action_type=ActionType.CHARGE_FROM_HAND, player_id=1, hand_index=0),
    )
    p1 = charged.players[1]
    assert charged.phase == TurnPhase.MAIN
    assert p1.has_charged_this_turn is True
    assert len(p1.energy) == 1
    assert p1.energy[0].resting is False
    assert len(p1.hand) == 5


def test_charge_from_hand_allows_immediate_one_cost_play() -> None:
    class FakeRepo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 10:
                return SimpleNamespace(
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
                )
            if card_id == 11:
                return SimpleNamespace(
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
                )
            return SimpleNamespace(
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
            )

    engine = RulesEngine(card_repository=FakeRepo())
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[11, 10] + _deck(1000, 28),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )

    charged = engine.apply_action(
        state,
        Action(action_type=ActionType.CHARGE_FROM_HAND, player_id=1, hand_index=0),
    )
    legal = engine.get_legal_actions(charged, 1)
    assert any(action.action_type == ActionType.PLAY_CARD_FROM_HAND for action in legal)


def test_end_turn_switches_player_and_resets_to_draw() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(10),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(100),
        shuffle_decks=False,
    )
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=1))

    next_state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert next_state.active_player == 2
    assert next_state.turn_number == 2
    assert next_state.phase == TurnPhase.CHARGE
    assert len(next_state.players[2].hand) == 7


def test_illegal_action_rejected() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(10),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(100),
        shuffle_decks=False,
    )
    with pytest.raises(RulesViolation):
        engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))


def test_setup_order_draw_then_life() -> None:
    engine = RulesEngine()
    p1_deck = _deck(1000)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=p1_deck,
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )

    p1 = state.players[1]
    hand_ids = [c.card_id for c in p1.hand]
    life_ids = [c.card_id for c in p1.life]
    assert hand_ids == p1_deck[:6]
    assert life_ids == p1_deck[6:14]


def test_mulligan_replaces_opening_hand_once() -> None:
    engine = RulesEngine()
    p1_deck = _deck(3000)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=p1_deck,
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(4000),
        shuffle_decks=False,
        mulligan_by_player={1: True},
    )
    p1 = state.players[1]
    hand_ids = [c.card_id for c in p1.hand]
    assert hand_ids == p1_deck[6:12]


def test_initialize_supports_z_decks() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[9001, 9002, 9003],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        p2_z_deck_card_ids=[9101],
        shuffle_decks=False,
    )
    assert state.players[1].z_deck == [9001, 9002, 9003]
    assert state.players[2].z_deck == [9101]


def test_charge_phase_untaps_leader_energy_battle_unison() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    p2 = state.players[2]
    p2.energy.append(type(p2.hand[0])(instance_id=999001, card_id=111, owner_id=2, resting=True))
    p2.battle_area.append(type(p2.hand[0])(instance_id=999002, card_id=222, owner_id=2, resting=True, power=15000))
    p2.unison_area.append(type(p2.hand[0])(instance_id=999003, card_id=333, owner_id=2, resting=True, power=15000, markers=1))
    p2.combo_area.append(type(p2.hand[0])(instance_id=999004, card_id=444, owner_id=2, resting=True))
    p2.leader_area.resting = True

    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    p2_next = state.players[2]
    assert p2_next.leader_area.resting is False
    assert p2_next.energy[0].resting is False
    assert p2_next.battle_area[0].resting is False
    assert p2_next.unison_area[0].resting is False
    assert p2_next.combo_area == []


def test_checkpoints_capture_phase_progression() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    names = [c.name for c in state.checkpoints]
    assert "pregame_setup_complete" in names
    assert "charge_phase_begin" in names
    assert "charge_phase_after_untap" in names
    assert any(name.startswith("charge_phase_after_draw") for name in names)


def test_engine_uses_repository_power_for_leader_and_drawn_cards() -> None:
    class FakeRepo:
        def __init__(self) -> None:
            self.data = {
                1: SimpleNamespace(
                    power_int=10000,
                    card_type="LEADER",
                    card_color="Red",
                    energy_cost_int=0,
                    combo_cost_int=0,
                    combo_power_int=0,
                    keywords=("Awaken",),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=True,
                    has_permanent=True,
                    has_barrier=False,
                ),
                2: SimpleNamespace(power_int=15000, card_type="LEADER", card_color="Blue"),
                1000: SimpleNamespace(
                    power_int=5000,
                    card_type="EXTRA",
                    card_color="Yellow",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=0,
                    keywords=("Counter",),
                    has_counter=True,
                    has_activate_main=True,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                ),
                1001: SimpleNamespace(
                    power_int=35000,
                    card_type="BATTLE",
                    card_color="Green",
                    energy_cost_int=8,
                    combo_cost_int=1,
                    combo_power_int=10000,
                    keywords=("Barrier", "Dual Attack"),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=True,
                    has_auto=True,
                    has_permanent=False,
                    has_barrier=True,
                ),
            }

        def get_by_id(self, card_id: int, source_table: str = "cards"):
            return self.data[card_id]

    engine = RulesEngine(card_repository=FakeRepo())
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[1000, 1001] + _deck(2000, 58),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(3000),
        shuffle_decks=False,
    )

    assert state.players[1].leader_area.power == 10000
    assert state.players[2].leader_area.power == 15000
    assert state.players[1].leader_area.card_type == "LEADER"
    assert state.players[1].leader_area.color == "Red"
    assert state.players[1].leader_area.has_auto is True
    assert state.players[1].leader_area.has_permanent is True
    assert state.players[1].hand[0].power == 5000
    assert state.players[1].hand[1].power == 35000
    assert state.players[1].hand[0].card_type == "EXTRA"
    assert state.players[1].hand[0].color == "Yellow"
    assert state.players[1].hand[0].energy_cost == 1
    assert state.players[1].hand[0].has_counter is True
    assert state.players[1].hand[1].card_type == "BATTLE"
    assert state.players[1].hand[1].combo_power == 10000
    assert "Barrier" in state.players[1].hand[1].keywords
    assert state.players[1].hand[1].has_barrier is True


def test_engine_power_falls_back_when_repo_missing_id() -> None:
    class EmptyRepo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            raise KeyError(card_id)

    engine = RulesEngine(card_repository=EmptyRepo())
    state = engine.initialize_game(
        p1_leader_card_id=999001,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=999002,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )

    assert state.players[1].leader_area.power == 15000
    assert state.players[2].leader_area.power == 15000
    assert state.players[1].leader_area.card_type == "BATTLE"
    assert state.players[1].leader_area.color is None
    assert state.players[1].leader_area.keywords == ()
