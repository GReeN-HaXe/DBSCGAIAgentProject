from __future__ import annotations

from types import SimpleNamespace
import pytest

from src.game import Action, ActionType, AttackContext, BattleStep, CardInstance, RulesEngine, RulesViolation, TurnPhase


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


def test_sparking_super_combo_is_not_legal_without_life_or_drop_requirement() -> None:
    class FakeRepo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 10:
                return SimpleNamespace(
                    power_int=5000,
                    card_type="BATTLE",
                    card_color="Red",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=10000,
                    keywords=("Super Combo",),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=True,
                    has_permanent=False,
                    has_barrier=False,
                    card_skill_unstyled="[Super Combo][Sparking 5] When you combo with this card, if you have 5 or more cards in your Drop Area, this card gets +10000 combo power.",
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
        p1_deck_card_ids=[10] + _deck(1000, 29),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.attack_context = AttackContext(
        attacker_player_id=2,
        attacker_zone="leader",
        attacker_instance_id=state.players[2].leader_area.instance_id,
        target_player_id=1,
        target_zone="leader",
        target_instance_id=state.players[1].leader_area.instance_id,
    )
    state.battle_step = BattleStep.DEFENSE
    state.players[1].life = state.players[1].life[:5]
    state.players[1].drop = []

    legal = engine.get_legal_actions(state, 1)
    assert not any(
        action.action_type == ActionType.COMBO_FROM_HAND and action.hand_index == 0
        for action in legal
    )


def test_sparking_super_combo_is_legal_with_five_cards_in_drop() -> None:
    class FakeRepo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 10:
                return SimpleNamespace(
                    power_int=5000,
                    card_type="BATTLE",
                    card_color="Red",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=10000,
                    keywords=("Super Combo",),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=True,
                    has_permanent=False,
                    has_barrier=False,
                    card_skill_unstyled="[Super Combo][Sparking 5] When you combo with this card, if you have 5 or more cards in your Drop Area, this card gets +10000 combo power.",
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
        p1_deck_card_ids=[10] + _deck(1000, 29),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.attack_context = AttackContext(
        attacker_player_id=2,
        attacker_zone="leader",
        attacker_instance_id=state.players[2].leader_area.instance_id,
        target_player_id=1,
        target_zone="leader",
        target_instance_id=state.players[1].leader_area.instance_id,
    )
    state.battle_step = BattleStep.DEFENSE
    state.players[1].life = state.players[1].life[:5]
    state.players[1].drop = [
        state.players[1].hand.pop()
        for _ in range(5)
    ]

    legal = engine.get_legal_actions(state, 1)
    assert any(
        action.action_type == ActionType.COMBO_FROM_HAND and action.hand_index == 0
        for action in legal
    )


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


def test_leader_awaken_is_legal_at_four_life_and_flips_to_back_side() -> None:
    class FakeRepo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 1:
                return SimpleNamespace(
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
                    has_draw=True,
                    max_draw=1,
                    has_barrier=False,
                    card_skill_unstyled="[Auto] When this card attacks, draw 1 card.<br>[Awaken] When your life is at 4 or less: You may draw 2 cards, and flip this card over.",
                    card_back_name="Awakened Leader",
                    card_back_power=15000,
                    card_back_skill_unstyled="[Auto] When this card attacks, draw 1 card.<br>[Activate: Main][Once per turn] This card gets +5000 power for the turn.",
                )
            return SimpleNamespace(
                power_int=15000,
                card_type="LEADER",
                card_color="Blue",
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=0,
                keywords=(),
                has_counter=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                has_barrier=False,
                card_skill_unstyled="",
                card_back_skill_unstyled="",
            )

    engine = RulesEngine(card_repository=FakeRepo())
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000, 40),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000, 40),
        shuffle_decks=False,
    )
    state.players[1].life = state.players[1].life[:4]
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=1))
    legal = engine.get_legal_actions(state, 1)
    assert any(action.action_type == ActionType.AWAKEN for action in legal)
    awakened = engine.apply_action(state, next(action for action in legal if action.action_type == ActionType.AWAKEN))
    leader = awakened.players[1].leader_area
    assert leader.awakened is True
    assert leader.power == 15000
    assert leader.has_activate_main is True
    assert len(awakened.players[1].life) == 4
    assert any(cp.name == "leader_awakened" for cp in awakened.checkpoints)


def test_leader_awaken_is_legal_with_two_hidden_mode_cards_in_battle_area() -> None:
    class FakeRepo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 1:
                return SimpleNamespace(
                    power_int=10000,
                    card_type="LEADER",
                    card_color="White",
                    energy_cost_int=0,
                    combo_cost_int=0,
                    combo_power_int=0,
                    keywords=("Awaken",),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=True,
                    has_permanent=False,
                    has_draw=False,
                    max_draw=None,
                    has_barrier=False,
                    card_skill_unstyled=(
                        "[Auto] When this card attacks, draw 1 card.<br>"
                        "[Awaken] When your life is at 4 or less, or you have 2 or more Hidden Mode cards in your Battle Area: "
                        "Draw 2 cards and add cards from your life to your hand until you have 6 life left."
                    ),
                    card_back_name="Awakened Hidden Mode Leader",
                    card_back_power=15000,
                    card_back_skill_unstyled="[Auto] When this card attacks, draw 1 card.",
                )
            return SimpleNamespace(
                power_int=15000,
                card_type="LEADER",
                card_color="Blue",
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=0,
                keywords=(),
                has_counter=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                has_barrier=False,
                card_skill_unstyled="",
                card_back_skill_unstyled="",
            )

    engine = RulesEngine(card_repository=FakeRepo())
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000, 40),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000, 40),
        shuffle_decks=False,
    )
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=720001, card_id=101, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True),
            CardInstance(instance_id=720002, card_id=102, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True),
        ]
    )
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=1))
    legal = engine.get_legal_actions(state, 1)
    assert any(action.action_type == ActionType.AWAKEN for action in legal)
    awakened = engine.apply_action(state, next(action for action in legal if action.action_type == ActionType.AWAKEN))
    assert awakened.players[1].leader_area.awakened is True
    assert awakened.players[1].leader_area.power == 15000
    assert any(cp.name == "leader_awakened" for cp in awakened.checkpoints)


def test_hand_permanent_hidden_mode_cost_reduction_makes_play_legal() -> None:
    class FakeRepo:
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
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_draw=False,
                    max_draw=None,
                    has_barrier=False,
                    card_energy_cost="0",
                    card_skill_unstyled="",
                    card_traits_json='["Universe 7"]',
                    card_character_json="[]",
                )
            if card_id == 900901:
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
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=True,
                    has_draw=False,
                    max_draw=None,
                    has_barrier=False,
                    card_energy_cost="2",
                    card_skill_unstyled=(
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
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                card_energy_cost="0",
                card_skill_unstyled="",
                card_traits_json="[]",
                card_character_json="[]",
            )

    engine = RulesEngine(card_repository=FakeRepo())
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000, 40),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000, 40),
        shuffle_decks=False,
    )
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=1))
    state.players[1].energy = []
    state.players[1].hand = [engine._create_card_instance(next_instance_id=880901, card_id=900901, owner_id=1)]
    legal = engine.get_legal_actions(state, 1)
    assert all(a.action_type != ActionType.PLAY_CARD_FROM_HAND for a in legal)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880902, card_id=100, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True)
    )
    legal = engine.get_legal_actions(state, 1)
    assert any(a.action_type == ActionType.PLAY_CARD_FROM_HAND for a in legal)


def test_hand_permanent_hidden_mode_cost_reduction_makes_counter_legal() -> None:
    class FakeRepo:
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
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_draw=False,
                    max_draw=None,
                    has_barrier=False,
                    card_energy_cost="0",
                    card_skill_unstyled="",
                    card_traits_json='["Universe 7"]',
                    card_character_json="[]",
                )
            if card_id == 900903:
                return SimpleNamespace(
                    card_name="Hidden Counter Reducer",
                    power_int=15000,
                    card_type="BATTLE",
                    card_color="White",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=True,
                    has_counter_attack=False,
                    has_counter_play=True,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=True,
                    has_draw=False,
                    max_draw=None,
                    has_barrier=False,
                    card_energy_cost="2",
                    card_skill_unstyled=(
                        "[Counter: Play] Play this card.<br>"
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
                card_energy_cost="0",
                card_skill_unstyled="",
                card_traits_json="[]",
                card_character_json="[]",
            )

    engine = RulesEngine(card_repository=FakeRepo())
    state = engine.initialize_game(
        p1_leader_card_id=2,
        p1_deck_card_ids=_deck(1000, 40),
        p2_leader_card_id=1,
        p2_deck_card_ids=_deck(2000, 40),
        shuffle_decks=False,
    )
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=1))
    state.players[1].energy = []
    state.players[1].hand = [CardInstance(instance_id=880904, card_id=111, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].energy = []
    state.players[2].hand = [engine._create_card_instance(next_instance_id=880903, card_id=900903, owner_id=2)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    legal = engine.get_legal_actions(state, 2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)
    state.players[2].battle_area.append(
        CardInstance(instance_id=880905, card_id=112, owner_id=2, card_type="BATTLE", color="White", hidden_mode=True)
    )
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


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
