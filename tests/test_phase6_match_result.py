from __future__ import annotations

from src.agent.match_result import build_compact_match_summary, evaluate_match_expectations
from src.game import RulesEngine


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def test_phase6_build_compact_match_summary_shape() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    summary = build_compact_match_summary(
        state=state,
        total_actions=0,
        human_player_id=1,
        ai_profile="balanced",
        setup_metadata={"seed": 5},
    )
    assert summary["human_player_id"] == 1
    assert summary["ai_profile"] == "balanced"
    assert "checkpoint_tail" in summary
    assert "effect_unresolved_count" in summary
    assert summary["setup"]["seed"] == 5


def test_phase6_evaluate_match_expectations_reports_failures() -> None:
    summary = {
        "winner_id": None,
        "final_turn_number": 2,
        "effect_unresolved_count": 3,
    }
    failures = evaluate_match_expectations(
        summary=summary,
        expect_winner=1,
        expect_final_turn=3,
        expect_completed=True,
        max_unresolved_effects=1,
    )
    assert len(failures) == 4
