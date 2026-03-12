from __future__ import annotations

from dataclasses import replace

from src.agent import HeuristicPolicy
from src.agent.session import (
    HumanVsAiSession,
    describe_action,
    format_full_board_for_cli,
    snapshot_state_for_trace,
    summarize_state_for_cli,
)
from src.game import RulesEngine
from src.game.actions import Action, ActionType
from src.game.state import CardInstance, GameState, PlayerState, TurnPhase


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


def test_phase6_cli_helpers_can_render_card_names() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    legal = engine.get_legal_actions(state, state.active_player)
    action_text = describe_action(
        legal[1],
        state=state,
        card_name_resolver=lambda card_id: f"CARD-{card_id}",
    )
    state_text = summarize_state_for_cli(
        state,
        card_name_resolver=lambda card_id: f"CARD-{card_id}",
        reveal_hand_player_id=1,
    )
    assert "card=CARD-" in action_text
    assert "P1 hand:" in state_text
    assert "[0] CARD-" in state_text


def test_phase6_cli_helpers_can_reveal_multiple_hands() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state_text = summarize_state_for_cli(
        state,
        card_name_resolver=lambda card_id: f"CARD-{card_id}",
        reveal_hand_player_ids=(1, 2),
    )
    assert "P1 hand:" in state_text
    assert "P2 hand:" in state_text


def test_phase6_cli_helpers_render_board_details() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].energy.append(CardInstance(instance_id=9001, card_id=9001, owner_id=1, resting=False))
    state.players[1].battle_area.append(CardInstance(instance_id=9002, card_id=9002, owner_id=1, resting=True))
    state_text = summarize_state_for_cli(
        state,
        card_name_resolver=lambda card_id: f"CARD-{card_id}",
        reveal_hand_player_id=1,
    )
    assert "P1 leader=" in state_text
    assert "P1 zones:" in state_text
    assert "Energy:" in state_text
    assert "Battle:" in state_text


def test_phase6_full_board_formatter_is_sectioned_and_readable() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].energy.append(CardInstance(instance_id=9001, card_id=9001, owner_id=1, resting=False))
    state.players[1].battle_area.append(CardInstance(instance_id=9002, card_id=9002, owner_id=1, resting=True))
    text = format_full_board_for_cli(
        state,
        card_name_resolver=lambda card_id: f"CARD-{card_id}",
        reveal_hand_player_ids=(1,),
    )
    assert "P1" in text
    assert "P2" in text
    assert "  Energy:" in text
    assert "  Battle:" in text
    assert "  Hand:" in text
    assert "    [0] CARD-" in text


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
    row = payload["actions"][0]
    assert isinstance(row["state_snapshot"], dict)
    assert row["state_snapshot"]["active_player"] == 1


def test_phase6_session_current_player_uses_counter_window_responder() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = engine.apply_action(state, next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.END_CHARGE))
    state = engine.apply_action(state, next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.END_TURN))
    state = engine.apply_action(state, next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.END_CHARGE))
    attack = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    session = HumanVsAiSession(
        engine=engine,
        state=state,
        human_player_id=1,
        ai_policy=HeuristicPolicy(profile="balanced"),
    )
    assert state.counter_window is not None
    assert session.current_player() == 1


def test_phase6_snapshot_state_for_trace_has_compact_zone_counts() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    snapshot = snapshot_state_for_trace(state)
    assert snapshot["phase"] == state.phase.value
    players = snapshot["players"]
    assert isinstance(players, dict)
    assert players["1"]["hand_size"] == 6
    assert players["1"]["life_size"] == 8
    assert players["1"]["deck_size"] == 46


def test_phase6_session_ai_loop_guard_prefers_fallback_action() -> None:
    class LoopPolicy:
        def choose_action(self, state: GameState, legal_actions: list[Action]) -> Action:
            for action in legal_actions:
                if action.action_type == ActionType.ACTIVATE_MAIN_SKILL:
                    return action
            return legal_actions[0]

        def rank_actions(self, state: GameState, legal_actions: list[Action]) -> list[object]:
            return [type("Ranked", (), {"action": action}) for action in legal_actions]

    class LoopEngine:
        def get_legal_actions(self, state: GameState, player_id: int) -> list[Action]:
            if state.winner_id is not None or player_id != state.active_player:
                return []
            return [
                Action(action_type=ActionType.ACTIVATE_MAIN_SKILL, player_id=player_id, source_zone="leader"),
                Action(action_type=ActionType.END_TURN, player_id=player_id),
            ]

        def apply_action(self, state: GameState, action: Action) -> GameState:
            if action.action_type == ActionType.ACTIVATE_MAIN_SKILL:
                return state
            ns = replace(state)
            ns.active_player = 1
            return ns

    leader_1 = CardInstance(instance_id=1, card_id=1, owner_id=1)
    leader_2 = CardInstance(instance_id=2, card_id=2, owner_id=2, has_activate_main=True)
    state = GameState(
        players={
            1: PlayerState(player_id=1, leader_card_id=1, leader_area=leader_1, life=[leader_1], hand=[], deck=[]),
            2: PlayerState(player_id=2, leader_card_id=2, leader_area=leader_2, life=[leader_2], hand=[], deck=[]),
        },
        active_player=2,
        first_player_id=1,
        phase=TurnPhase.MAIN,
    )
    session = HumanVsAiSession(
        engine=LoopEngine(),  # type: ignore[arg-type]
        state=state,
        human_player_id=1,
        ai_policy=LoopPolicy(),  # type: ignore[arg-type]
    )
    first = session.step_ai_once()
    second = session.step_ai_once()
    assert first.action_type == ActionType.ACTIVATE_MAIN_SKILL
    assert second.action_type == ActionType.END_TURN


def test_phase6_session_ai_action_context_uses_pre_action_state() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = engine.apply_action(state, next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.END_CHARGE))
    state = engine.apply_action(state, next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.END_TURN))
    session = HumanVsAiSession(
        engine=engine,
        state=state,
        human_player_id=1,
        ai_policy=HeuristicPolicy(profile="balanced"),
    )
    entries = session.step_ai_until_human_turn_with_context(max_ai_actions=1)
    assert len(entries) == 1
    action = entries[0]["action"]
    state_before = entries[0]["state_before"]
    if action.action_type == ActionType.CHARGE_FROM_HAND:
        rendered = describe_action(
            action,
            state=state_before,
            card_name_resolver=lambda card_id: f"CARD-{card_id}",
        )
        assert "card=CARD-" in rendered
