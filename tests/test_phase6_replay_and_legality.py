from __future__ import annotations

from dataclasses import dataclass

from src.agent import HeuristicPolicy, HumanVsAiSession
from src.agent.deck_legality import validate_deck_legality
from src.agent.replay import compute_trace_hash, run_scripted_replay
from src.game import RulesEngine


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


@dataclass(frozen=True)
class _CardStub:
    card_id: int
    card_type: str
    card_number: str
    is_banned: bool = False
    is_limited: bool = False
    limited_to: int | None = None


class _RepoStub:
    def __init__(self, cards: dict[int, _CardStub]) -> None:
        self.cards = cards

    def get_by_id(self, card_id: int, *, source_table: str = "cards") -> _CardStub:
        if card_id not in self.cards:
            raise KeyError(card_id)
        return self.cards[card_id]


def test_phase6_deck_legality_rejects_copy_limit_exceeded() -> None:
    cards = {
        1: _CardStub(card_id=1, card_type="LEADER", card_number="L-001"),
        100: _CardStub(card_id=100, card_type="BATTLE", card_number="BT-100"),
    }
    repo = _RepoStub(cards)
    deck = [100] * 60
    try:
        validate_deck_legality(repo=repo, leader_id=1, deck_ids=deck, expected_deck_size=60, max_copies_per_card_number=4)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "copy limit" in str(exc)


def test_phase6_deck_legality_rejects_banned_and_limited() -> None:
    cards = {
        1: _CardStub(card_id=1, card_type="LEADER", card_number="L-001"),
        101: _CardStub(card_id=101, card_type="BATTLE", card_number="BT-101", is_banned=True),
        102: _CardStub(card_id=102, card_type="BATTLE", card_number="BT-102", is_limited=True, limited_to=1),
    }
    filler_ids = list(range(200, 260))
    for cid in filler_ids:
        cards[cid] = _CardStub(card_id=cid, card_type="BATTLE", card_number=f"BT-{cid}")
    repo = _RepoStub(cards)
    banned_deck = [101] + filler_ids[:59]
    try:
        validate_deck_legality(repo=repo, leader_id=1, deck_ids=banned_deck, expected_deck_size=60)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "banned" in str(exc)
    limited_deck = [102, 102] + filler_ids[:58]
    try:
        validate_deck_legality(repo=repo, leader_id=1, deck_ids=limited_deck, expected_deck_size=60)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "limited" in str(exc)


def test_phase6_scripted_replay_is_deterministic_for_same_state_and_actions() -> None:
    engine1 = RulesEngine()
    state1 = engine1.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    s1 = HumanVsAiSession(engine=engine1, state=state1, human_player_id=1, ai_policy=HeuristicPolicy(profile="balanced"))
    r1 = run_scripted_replay(session=s1, human_action_indices=[0, 0], max_actions=20)

    engine2 = RulesEngine()
    state2 = engine2.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    s2 = HumanVsAiSession(engine=engine2, state=state2, human_player_id=1, ai_policy=HeuristicPolicy(profile="balanced"))
    r2 = run_scripted_replay(session=s2, human_action_indices=[0, 0], max_actions=20)

    assert r1.consumed_human_actions == r2.consumed_human_actions
    assert r1.final_turn_number == r2.final_turn_number
    assert r1.final_phase == r2.final_phase
    assert r1.winner_id == r2.winner_id
    t1 = [a["action_type"] for a in (s1.action_trace or [])]
    t2 = [a["action_type"] for a in (s2.action_trace or [])]
    assert t1 == t2
    h1 = compute_trace_hash(s1.to_trace_payload())
    h2 = compute_trace_hash(s2.to_trace_payload())
    assert h1 == h2


def test_phase6_trace_hash_ignores_timestamp_field() -> None:
    payload_a = {
        "total_actions": 1,
        "winner_id": None,
        "final_turn_number": 1,
        "final_phase": "charge",
        "human_player_id": 1,
        "actions": [
            {
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "actor_kind": "human",
                "player_id": 1,
                "turn_number": 1,
                "phase": "charge",
                "action": "end_charge",
                "action_type": "end_charge",
            }
        ],
    }
    payload_b = {
        **payload_a,
        "actions": [{**payload_a["actions"][0], "timestamp_utc": "2026-01-01T00:00:01Z"}],
    }
    assert compute_trace_hash(payload_a) == compute_trace_hash(payload_b)
