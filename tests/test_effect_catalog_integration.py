from __future__ import annotations

import json
import pytest

from src.game import Action, ActionType, CardInstance, RulesEngine, TurnPhase
from src.game.effect_rules import default_effect_catalog_path, load_effect_rules_json, serialize_effect_catalog


CATALOG_PATH = default_effect_catalog_path()


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _to_main(engine: RulesEngine, state):
    while state.phase != TurnPhase.MAIN:
        state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=state.active_player))
    return state


def _load_catalog() -> dict[str, list[dict[str, object]]]:
    if not CATALOG_PATH.exists():
        pytest.skip(f"catalog file not found: {CATALOG_PATH}")
    payload = serialize_effect_catalog(load_effect_rules_json(CATALOG_PATH))
    rules = payload.get("rules")
    if isinstance(rules, dict):
        return rules
    raise AssertionError("effect catalog payload must expose serialized rules")


def test_generated_catalog_self_played_draw_rule_executes_end_to_end() -> None:
    catalog = _load_catalog()
    selected_card_id: int | None = None
    draw_amount = 1
    for key, rules in catalog.items():
        for rule in rules:
            if rule.get("trigger") == "self_played" and rule.get("handler_id") == "auto_draw_n":
                selected_card_id = int(key)
                params = rule.get("handler_params", {})
                if isinstance(params, dict):
                    raw = params.get("amount", 1)
                    if isinstance(raw, int) and raw > 0:
                        draw_amount = raw
                break
        if selected_card_id is not None:
            break
    if selected_card_id is None:
        pytest.skip("no self_played auto_draw_n rule found in generated catalog")

    engine = RulesEngine(effect_rules_path=CATALOG_PATH)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    p1 = state.players[1]
    deck_before = len(p1.deck)
    p1.hand = [CardInstance(instance_id=950001, card_id=selected_card_id, owner_id=1, card_type="BATTLE", energy_cost=0)]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].deck) == deck_before - draw_amount


def test_generated_catalog_self_played_ko_rule_executes_end_to_end() -> None:
    catalog = _load_catalog()
    selected_card_id: int | None = None
    max_cost = -1
    for key, rules in catalog.items():
        for rule in rules:
            if rule.get("trigger") == "self_played" and rule.get("handler_id") == "auto_ko_opponent_battle_on_play":
                params = rule.get("handler_params", {})
                if not isinstance(params, dict):
                    continue
                # Pick a simple non-gated KO rule for deterministic integration.
                allowed_keys = {"max_cost", "ignores_barrier"}
                if any(key not in allowed_keys for key in params.keys()) or bool(params.get("rest_mode_only", False)):
                    continue
                selected_card_id = int(key)
                raw = params.get("max_cost", -1)
                if isinstance(raw, int):
                    max_cost = raw
                break
        if selected_card_id is not None:
            break
    if selected_card_id is None:
        pytest.skip("no simple self_played auto_ko_opponent_battle_on_play rule found in generated catalog")

    engine = RulesEngine(effect_rules_path=CATALOG_PATH)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    p2 = state.players[2]
    if max_cost >= 0:
        eligible_cost = max_cost
        ineligible_cost = max_cost + 1
    else:
        eligible_cost = 3
        ineligible_cost = 4
    p2.battle_area = [
        CardInstance(instance_id=950011, card_id=11, owner_id=2, card_type="BATTLE", energy_cost=eligible_cost, power=10000),
        CardInstance(instance_id=950012, card_id=12, owner_id=2, card_type="BATTLE", energy_cost=ineligible_cost, power=10000),
    ]
    state.players[1].hand = [CardInstance(instance_id=950013, card_id=selected_card_id, owner_id=1, card_type="BATTLE", energy_cost=0)]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    remaining = {c.instance_id for c in state.players[2].battle_area}
    if max_cost >= 0:
        assert 950011 not in remaining
    assert any(c.instance_id == 950011 for c in state.players[2].drop) or any(c.instance_id == 950012 for c in state.players[2].drop)
