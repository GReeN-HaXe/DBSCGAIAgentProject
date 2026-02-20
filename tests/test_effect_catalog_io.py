from __future__ import annotations

from src.game import Action, ActionType, CardInstance, RulesEngine, TurnPhase
from src.game.effect_rules import EffectRule, load_effect_rules_json, save_effect_rules_json


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _to_main(engine: RulesEngine, state):
    while state.phase != TurnPhase.MAIN:
        state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=state.active_player))
    return state


def test_effect_catalog_json_roundtrip(tmp_path) -> None:
    source = {
        101: (
            EffectRule(trigger="self_played", handler_id="auto_draw_n", handler_params={"amount": 2}, once_per_turn=True),
        ),
        202: (
            EffectRule(trigger="self_attacks", handler_id="auto_draw_n", handler_params={"amount": 1}, once_per_turn=False),
        ),
    }
    path = tmp_path / "catalog.json"
    save_effect_rules_json(path, source)
    loaded = load_effect_rules_json(path)
    assert set(loaded.keys()) == {101, 202}
    assert loaded[101][0].handler_params["amount"] == 2
    assert loaded[101][0].once_per_turn is True


def test_engine_loads_effect_catalog_from_path(tmp_path) -> None:
    catalog_path = tmp_path / "catalog.json"
    save_effect_rules_json(
        catalog_path,
        {
            303: (
                EffectRule(trigger="self_played", handler_id="auto_draw_n", handler_params={"amount": 1}, once_per_turn=False),
            )
        },
    )

    engine = RulesEngine(effect_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    deck_before = len(state.players[1].deck)
    state.players[1].hand = [CardInstance(instance_id=930001, card_id=303, owner_id=1, card_type="BATTLE", energy_cost=0)]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].deck) == deck_before - 1

