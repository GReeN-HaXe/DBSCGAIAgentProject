from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import uuid

from src.game.skill_cost_rule_extractor import extract_skill_cost_rules_from_card
from src.game.skill_costs import load_skill_cost_rules_json, save_skill_cost_rules_json
from src.game import Action, ActionType, CardInstance, RulesEngine, TurnPhase


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _to_main(engine: RulesEngine, state):
    while state.phase != TurnPhase.MAIN:
        state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=state.active_player))
    return state


def test_extract_counter_hidden_mode_skill_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Play][Limit 1] Choose 1 of your white Battle Cards and switch it to Hidden Mode: "
            "Play this card, then switch the card that was switched to Hidden Mode by this skill to Revealed Mode at the end of the turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_from_hand": [
            {
                "kind": "switch_owner_battle_to_hidden",
                "amount": 1,
                "allowed_colors": "white",
            }
        ]
    }


def test_extract_activate_hidden_mode_battle_or_energy_skill_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main][Limit 1] Choose 1 white card in your Battle Area or energy and switch it to Hidden Mode: "
            "Choose up to 1 of your opponent's Battle Cards, KO it, and your white Leader gets +20000 power for the turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "switch_owner_battle_or_energy_to_hidden",
                "amount": 1,
                "allowed_colors": "white",
            }
        ]
    }


def test_extract_activate_main_without_colon_hidden_mode_skill_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[activate main][once per turn] Choose 1 of your white Battle Cards and switch it to Hidden Mode: "
            "Draw 1 card."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "switch_owner_battle_to_hidden",
                "amount": 1,
                "allowed_colors": "white",
            }
        ]
    }


def test_extract_activate_battle_hidden_mode_skill_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Battle][Once per turn](1), choose 1 white card in your Battle Area and switch it to Hidden Mode: "
            "This card gets +10000 power and [Double Strike] for the battle."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_battle": [
            {
                "kind": "switch_owner_battle_to_hidden",
                "amount": 1,
                "allowed_colors": "white",
            }
        ]
    }


def test_extract_activate_battle_drop_hidden_mode_skill_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Battle][Limit 1] Choose 1 Hidden Mode card in your Battle Area and place it into its owner's Drop: "
            "Choose up to 1 of your opponent's Battle Cards and KO it."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_battle": [
            {
                "kind": "send_owner_hidden_mode_battle_to_drop",
                "amount": 1,
            }
        ]
    }


def test_extract_counter_alternate_rest_hidden_battle_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack] Negate the attack. "
            "[Permanent] If your Leader is white, you can activate this card's [Counter] skill from your hand by "
            "switching 1 Hidden Mode card in your Battle Area to Rest Mode instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "rest_owner_hidden_mode_battle",
                "amount": 1,
                "required_leader_colors": "white",
            }
        ]
    }


def test_extract_counter_alternate_life_to_hand_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack] Negate the attack. "
            "[Permanent][Sparking 5] You can activate this card's [Counter] skill from your hand by adding 1 card from your life to your hand "
            "instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "add_life_to_hand",
                "amount": 1,
                "requires_sparking": 5,
            }
        ]
    }


def _workspace_temp_catalog_path(name: str) -> Path:
    directory = Path("artifacts") / "_tmp" / f"{name}_{uuid.uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "skill_cost_catalog.json"


def test_engine_loads_skill_cost_catalog_from_path() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_catalog")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900302: {
                "counter_from_hand": [
                    {"kind": "switch_owner_battle_to_hidden", "amount": 1, "allowed_colors": "white"}
                ]
            }
        },
    )
    loaded = load_skill_cost_rules_json(catalog_path)
    assert 900302 in loaded
    assert loaded[900302]["counter_from_hand"].steps[0].kind == "switch_owner_battle_to_hidden"

    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=790001, card_id=601, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].battle_area.append(CardInstance(instance_id=790002, card_id=602, owner_id=2, card_type="BATTLE", color="White"))
    state.players[2].hand.append(
        CardInstance(
            instance_id=790003,
            card_id=900302,
            owner_id=2,
            card_type="BATTLE",
            color="White",
            energy_cost=0,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw="[Counter: Play] Choose 1 of your white Battle Cards and switch it to Hidden Mode: Play this card.",
        )
    )

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_engine_uses_catalog_for_counter_alternate_hidden_battle_cost() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_catalog")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900303: {
                "counter_alternate_from_hand": [
                    {"kind": "rest_owner_hidden_mode_battle", "amount": 1, "required_leader_colors": "white"}
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    state.players[2].leader_area.color = "White"
    state.players[1].hand = [CardInstance(instance_id=790021, card_id=621, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].battle_area.append(
        CardInstance(instance_id=790022, card_id=622, owner_id=2, card_type="BATTLE", color="White", hidden_mode=True)
    )
    state.players[2].hand.append(
        CardInstance(
            instance_id=790023,
            card_id=900303,
            owner_id=2,
            card_type="EXTRA",
            color="White",
            energy_cost=1,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Negate the attack.",
        )
    )

    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_runtime_infers_counter_capability_from_skill_text_when_db_flags_are_stale() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 900401:
                return SimpleNamespace(
                    card_name="Hidden Counter",
                    power_int=15000,
                    card_type="BATTLE",
                    card_color="White",
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
                    card_skill_unstyled="[Counter: Play] Play this card.",
                    card_traits_json="[]",
                    card_character_json="[]",
                )
            return SimpleNamespace(
                card_name="Card",
                power_int=15000,
                card_type="LEADER" if card_id in {1, 2} else "BATTLE",
                card_color="White",
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

    engine = RulesEngine(card_repository=Repo())
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=790011, card_id=611, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand = [engine._create_card_instance(next_instance_id=790012, card_id=900401, owner_id=2)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)
