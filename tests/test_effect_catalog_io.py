from __future__ import annotations

import json
from pathlib import Path
import shutil
import uuid

from src.game import Action, ActionType, CardInstance, RulesEngine, TurnPhase
from src.game.effect_rules import (
    EFFECT_CATALOG_KIND,
    EFFECT_CATALOG_OVERRIDE_KIND,
    EFFECT_CATALOG_OVERRIDE_SCHEMA_VERSION,
    EFFECT_CATALOG_SCHEMA_VERSION,
    EffectRule,
    load_effect_rule_overrides_json,
    load_effect_rules_json,
    merge_effect_rule_overrides,
    save_effect_rule_overrides_json,
    save_effect_rules_json,
)

OVERRIDES_PATH = Path("dbdatabase/effect_catalog_overrides.json")


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _to_main(engine: RulesEngine, state):
    while state.phase != TurnPhase.MAIN:
        state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=state.active_player))
    return state


def _scratch_dir() -> Path:
    path = Path("artifacts/test_tmp_effect_catalog_io") / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_effect_catalog_json_roundtrip() -> None:
    source = {
        101: (
            EffectRule(
                trigger="self_played",
                handler_id="auto_draw_n",
                handler_params={"amount": 2},
                once_per_turn=True,
                family_id="self_played:auto_draw_n",
                provenance="manual",
            ),
        ),
        202: (
            EffectRule(
                trigger="self_attacks",
                handler_id="auto_draw_n",
                handler_params={"amount": 1},
                once_per_turn=False,
                family_id="self_attacks:auto_draw_n",
                provenance="manual",
            ),
        ),
    }
    scratch = _scratch_dir()
    try:
        path = scratch / "catalog.json"
        save_effect_rules_json(path, source)
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["catalog_kind"] == EFFECT_CATALOG_KIND
        assert raw["schema_version"] == EFFECT_CATALOG_SCHEMA_VERSION
        assert raw["card_rule_count"] == 2
        assert raw["effect_rule_count"] == 2
        assert set(raw["rules"].keys()) == {"101", "202"}
        assert raw["rules"]["101"][0]["family_id"] == "self_played:auto_draw_n"
        assert raw["rules"]["101"][0]["provenance"] == "manual"
        loaded = load_effect_rules_json(path)
        assert set(loaded.keys()) == {101, 202}
        assert loaded[101][0].handler_params["amount"] == 2
        assert loaded[101][0].once_per_turn is True
        assert loaded[101][0].family_id == "self_played:auto_draw_n"
        assert loaded[101][0].provenance == "manual"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_effect_catalog_loader_accepts_legacy_plain_rule_map() -> None:
    scratch = _scratch_dir()
    try:
        path = scratch / "legacy_catalog.json"
        path.write_text(
            json.dumps(
                {
                    "303": [
                        {
                            "trigger": "self_played",
                            "handler_id": "auto_draw_n",
                            "handler_params": {"amount": 1},
                            "once_per_turn": False,
                            "limit_per_turn": None,
                            "limit_scope": "card_number",
                            "family_id": "self_played:auto_draw_n",
                            "provenance": "legacy-test",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        loaded = load_effect_rules_json(path)
        assert set(loaded.keys()) == {303}
        assert loaded[303][0].handler_id == "auto_draw_n"
        assert loaded[303][0].family_id == "self_played:auto_draw_n"
        assert loaded[303][0].provenance == "legacy-test"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_effect_catalog_override_json_roundtrip_and_merge_modes() -> None:
    overrides = {
        101: (
            "append",
            (
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_draw_n",
                    handler_params={"amount": 1},
                    family_id="self_attacks:auto_draw_n",
                    provenance="override",
                ),
            ),
        ),
        202: (
            "replace",
            (
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_ko_opponent_battle_on_play",
                    handler_params={"max_cost": -1},
                    family_id="self_played:auto_ko_opponent_battle_on_play",
                    provenance="override",
                ),
            ),
        ),
    }
    scratch = _scratch_dir()
    try:
        path = scratch / "catalog_overrides.json"
        save_effect_rule_overrides_json(path, overrides)
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["catalog_kind"] == EFFECT_CATALOG_OVERRIDE_KIND
        assert raw["schema_version"] == EFFECT_CATALOG_OVERRIDE_SCHEMA_VERSION
        assert raw["override_count"] == 2
        assert raw["overrides"]["101"]["mode"] == "append"
        loaded = load_effect_rule_overrides_json(path)
        assert loaded[101][0] == "append"
        assert loaded[202][0] == "replace"
        base = {
            101: (
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_draw_n",
                    handler_params={"amount": 2},
                    family_id="self_played:auto_draw_n",
                    provenance="base",
                ),
            ),
            202: (
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_draw_n",
                    handler_params={"amount": 1},
                    family_id="self_attacks:auto_draw_n",
                    provenance="base",
                ),
            ),
        }
        merged = merge_effect_rule_overrides(base, loaded)
        assert len(merged[101]) == 2
        assert merged[202][0].handler_id == "auto_ko_opponent_battle_on_play"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_checked_in_effect_catalog_overrides_cover_known_edge_cases() -> None:
    if not OVERRIDES_PATH.exists():
        return
    loaded = load_effect_rule_overrides_json(OVERRIDES_PATH)
    assert len(loaded) == 29
    assert loaded[6][0] == "replace"
    assert loaded[89][0] == "replace"
    assert loaded[2409][0] == "replace"
    assert loaded[5656][0] == "replace"
    assert loaded[7236][0] == "replace"
    assert loaded[7459][0] == "replace"
    assert loaded[8314][0] == "replace"
    assert loaded[4265][0] == "replace"
    assert loaded[5301][0] == "replace"
    assert loaded[8458][0] == "replace"
    assert loaded[6679][0] == "replace"
    dyspo_rule = loaded[6][1][0]
    steadfast_rule = loaded[89][1][0]
    explosive_rule = loaded[2409][1][0]
    cabba_rule = loaded[5656][1][0]
    supreme_kai_rule = loaded[7236][1][0]
    difference_rule = loaded[7459][1][0]
    mechikabura_rule = loaded[8314][1][0]
    petrification_rule = loaded[4265][1][0]
    yamcha_rule = loaded[5301][1][0]
    final_battle_rule = loaded[8458][1][0]
    toppo_rule = loaded[6679][1][0]
    assert dyspo_rule.handler_id == "counter_negate_attack_play_self_attack_restriction"
    assert dyspo_rule.trigger == "counter_attack"
    assert steadfast_rule.handler_id == "counter_force_pending_play_rest_play_self_draw_n"
    assert steadfast_rule.family_id == "counter_play:counter_force_pending_play_rest_play_self_draw_n"
    assert explosive_rule.handler_id == "counter_negate_attack"
    assert explosive_rule.trigger == "counter_attack"
    assert cabba_rule.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play"
    assert cabba_rule.trigger == "self_played"
    assert supreme_kai_rule.handler_id == "counter_negate_attack_play_self"
    assert supreme_kai_rule.trigger == "counter_attack"
    assert difference_rule.handler_id == "counter_spirit_boost_power_reduce_opponent_cards"
    assert difference_rule.family_id == "counter_attack:counter_spirit_boost_power_reduce_opponent_cards"
    assert mechikabura_rule.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play"
    assert mechikabura_rule.trigger == "self_activate_main"
    assert petrification_rule.handler_id == "counter_negate_attack"
    assert petrification_rule.family_id == "counter_attack:counter_negate_attack"
    assert yamcha_rule.handler_id == "counter_power_reduce_up_to_n_opponent_battle_for_turn_play_self"
    assert yamcha_rule.family_id == "counter_play:counter_power_reduce_up_to_n_opponent_battle_for_turn_play_self"
    assert final_battle_rule.handler_id == "counter_negate_attack"
    assert final_battle_rule.family_id == "counter_attack:counter_negate_attack"
    assert toppo_rule.handler_id == "counter_negate_attack_play_self"
    assert toppo_rule.family_id == "counter_attack:counter_negate_attack_play_self"


def test_engine_loads_effect_catalog_from_path() -> None:
    scratch = _scratch_dir()
    try:
        catalog_path = scratch / "catalog.json"
        save_effect_rules_json(
            catalog_path,
            {
                303: (
                    EffectRule(
                        trigger="self_played",
                        handler_id="auto_draw_n",
                        handler_params={"amount": 1},
                        once_per_turn=False,
                        family_id="self_played:auto_draw_n",
                        provenance="manual",
                    ),
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
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_engine_applies_effect_catalog_override_replace() -> None:
    scratch = _scratch_dir()
    try:
        catalog_path = scratch / "catalog.json"
        override_path = scratch / "catalog_overrides.json"
        save_effect_rules_json(
            catalog_path,
            {
                404: (
                    EffectRule(
                        trigger="self_played",
                        handler_id="auto_draw_n",
                        handler_params={"amount": 1},
                        family_id="self_played:auto_draw_n",
                        provenance="base",
                    ),
                )
            },
        )
        save_effect_rule_overrides_json(
            override_path,
            {
                404: (
                    "replace",
                    (
                        EffectRule(
                            trigger="self_played",
                            handler_id="auto_draw_n",
                            handler_params={"amount": 2},
                            family_id="self_played:auto_draw_n",
                            provenance="override",
                        ),
                    ),
                )
            },
        )
        engine = RulesEngine(effect_rules_path=catalog_path, effect_rule_overrides_path=override_path)
        state = engine.initialize_game(
            p1_leader_card_id=1,
            p1_deck_card_ids=_deck(1000),
            p2_leader_card_id=2,
            p2_deck_card_ids=_deck(2000),
            shuffle_decks=False,
        )
        state = _to_main(engine, state)
        deck_before = len(state.players[1].deck)
        state.players[1].hand = [CardInstance(instance_id=930002, card_id=404, owner_id=1, card_type="BATTLE", energy_cost=0)]

        play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
        state = engine.apply_action(state, play)
        state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
        assert len(state.players[1].deck) == deck_before - 2
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
