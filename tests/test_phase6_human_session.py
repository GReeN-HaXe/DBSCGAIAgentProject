from __future__ import annotations

from src.agent import HeuristicPolicy
from src.agent.session import HumanVsAiSession, describe_action, summarize_state_for_cli
from src.game import RulesEngine


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def test_phase6_session_ai_steps_until_human_turn() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    session = HumanVsAiSession(
        engine=engine,
        state=state,
        human_player_id=2,
        ai_policy=HeuristicPolicy(profile="balanced"),
    )
    actions = session.step_ai_until_human_turn(max_ai_actions=20)
    assert actions
    assert bool(session.legal_actions_for_human()) or session.is_over()


def test_phase6_session_apply_human_action_by_index() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    session = HumanVsAiSession(
        engine=engine,
        state=state,
        human_player_id=1,
        ai_policy=HeuristicPolicy(profile="balanced"),
    )
    legal = session.legal_actions_for_human()
    assert legal
    chosen = session.apply_human_action_by_index(0)
    assert chosen == legal[0]
    assert session.total_actions == 1


def test_phase6_cli_helpers_render_non_empty_text() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    legal = engine.get_legal_actions(state, state.active_player)
    text = summarize_state_for_cli(state)
    action_text = describe_action(legal[0])
    assert "turn=" in text
    assert len(action_text) > 0


def test_phase6_session_trace_payload_collects_actions() -> None:
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
        ai_policy=HeuristicPolicy(profile="balanced"),
        setup_metadata={"seed": 123, "deck_source": "synthetic"},
    )
    session.apply_human_action_by_index(0)
    payload = session.to_trace_payload()
    assert payload["total_actions"] == 1
    assert isinstance(payload["actions"], list)
    assert len(payload["actions"]) == 1
    assert isinstance(payload["setup"], dict)
    assert payload["setup"]["seed"] == 123
