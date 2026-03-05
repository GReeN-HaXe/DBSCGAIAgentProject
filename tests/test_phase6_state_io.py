from __future__ import annotations

from src.agent import HeuristicPolicy, HumanVsAiSession
from src.game import RulesEngine, game_state_from_dict, game_state_to_dict, load_game_state_json, save_game_state_json


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def test_phase6_game_state_dict_roundtrip_keeps_core_fields() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    legal = engine.get_legal_actions(state, state.active_player)
    state = engine.apply_action(state, legal[0])
    payload = game_state_to_dict(state)
    restored = game_state_from_dict(payload)
    assert restored.turn_number == state.turn_number
    assert restored.phase == state.phase
    assert restored.active_player == state.active_player
    assert len(restored.players[1].hand) == len(state.players[1].hand)
    assert len(restored.players[2].hand) == len(state.players[2].hand)


def test_phase6_game_state_json_file_roundtrip(tmp_path) -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    path = tmp_path / "state.json"
    save_game_state_json(state, path)
    loaded = load_game_state_json(path)
    assert loaded.turn_number == state.turn_number
    assert loaded.phase == state.phase


def test_phase6_session_save_and_load_state(tmp_path) -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    session = HumanVsAiSession(
        engine=engine,
        state=state,
        human_player_id=1,
        ai_policy=HeuristicPolicy(),
    )
    session.apply_human_action_by_index(0)
    path = tmp_path / "session_state.json"
    session.save_state(path)
    old_turn = session.state.turn_number
    session.load_state(path)
    assert session.state.turn_number == old_turn
