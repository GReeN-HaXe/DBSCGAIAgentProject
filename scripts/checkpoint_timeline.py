from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db import SQLiteCardRepository
from src.game import Action, ActionType, RulesEngine, TurnPhase


def _build_deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _load_real_ids(db_path: Path) -> tuple[int, list[int], int, list[int]] | None:
    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    try:
        leader_rows = conn.execute(
            "SELECT id FROM cards WHERE UPPER(card_type)='LEADER' ORDER BY id LIMIT 2"
        ).fetchall()
        deck_rows = conn.execute(
            "SELECT id FROM cards WHERE UPPER(card_type)!='LEADER' ORDER BY id LIMIT 120"
        ).fetchall()
    finally:
        conn.close()

    if len(leader_rows) < 2 or len(deck_rows) < 120:
        return None
    p1_leader = int(leader_rows[0][0])
    p2_leader = int(leader_rows[1][0])
    p1_deck = [int(r[0]) for r in deck_rows[:60]]
    p2_deck = [int(r[0]) for r in deck_rows[60:120]]
    return p1_leader, p1_deck, p2_leader, p2_deck


def simulate(turns: int, db_path: Path) -> object:
    real_ids = _load_real_ids(db_path)
    repo = SQLiteCardRepository(db_path) if db_path.exists() else None
    engine = RulesEngine(
        card_repository=repo,
        skill_cost_rules_path=SKILL_COST_CATALOG_PATH if SKILL_COST_CATALOG_PATH else None,
        effect_rules_path=EFFECT_CATALOG_PATH if EFFECT_CATALOG_PATH else None,
        effect_rule_overrides_path=EFFECT_CATALOG_OVERRIDES_PATH if EFFECT_CATALOG_OVERRIDES_PATH else None,
    )

    if real_ids is None:
        p1_leader, p1_deck, p2_leader, p2_deck = 1001, _build_deck(10000), 2001, _build_deck(20000)
    else:
        p1_leader, p1_deck, p2_leader, p2_deck = real_ids

    state = engine.initialize_game(
        p1_leader_card_id=p1_leader,
        p1_deck_card_ids=p1_deck,
        p2_leader_card_id=p2_leader,
        p2_deck_card_ids=p2_deck,
        shuffle_decks=False,
    )

    while state.winner_id is None and state.turn_number <= turns:
        if state.phase == TurnPhase.CHARGE:
            state = engine.apply_action(state, Action(ActionType.END_CHARGE, state.active_player))
            continue
        if state.phase == TurnPhase.MAIN:
            state = engine.apply_action(state, Action(ActionType.END_TURN, state.active_player))
            continue
        break
    return state


def print_timeline(state: object) -> None:
    # Typed as object above to keep script decoupled from mypy setup; runtime object is GameState.
    checkpoints = getattr(state, "checkpoints")
    print("Checkpoint Timeline")
    print("===================")

    current_turn = None
    for cp in checkpoints:
        if cp.turn_number != current_turn:
            current_turn = cp.turn_number
            print(f"\nTurn {current_turn}")
        print(f"  #{cp.index:03d} P{cp.active_player} {cp.phase.value:<6} {cp.name}")

    counter_resolutions = getattr(state, "counter_resolutions", [])
    print("\nCounter Chain Trace")
    print("-------------------")
    if not counter_resolutions:
        print("  (none)")
    else:
        for cr in counter_resolutions:
            status = "resolved" if cr.resolved else "negated"
            negated = f" -> negated motion #{cr.negated_motion_id}" if cr.negated_motion_id is not None else ""
            print(f"  motion #{cr.motion_id:03d} by P{cr.player_id}: {status}{negated}")

    motion_trace = getattr(state, "counter_motion_trace", [])
    print("\nCounter Motion Detail")
    print("---------------------")
    if not motion_trace:
        print("  (none)")
    else:
        for mt in motion_trace:
            status = "declared" if mt.resolved is None else ("resolved" if mt.resolved else "negated")
            negated = f" -> negated motion #{mt.negated_motion_id}" if mt.negated_motion_id is not None else ""
            modes = ", ".join(mt.modes) if mt.modes else "-"
            print(
                f"  motion #{mt.motion_id:03d} T{mt.turn_number} {mt.phase.value:<6} "
                f"P{mt.player_id} [{status}] window={mt.window_kind} modes={modes}{negated}"
            )

    open_window = getattr(state, "counter_window", None)
    if open_window is not None:
        print("\nOpen Counter Window")
        print("-------------------")
        print(f"  kind: {open_window.kind}")
        print(f"  responder: P{open_window.responder_player_id}")
        print(f"  pending: {open_window.pending_action.action_type}")
        payload = dict(open_window.pending_action.payload)
        if payload:
            print("  payload:")
            for key in sorted(payload.keys()):
                print(f"    {key}: {payload[key]}")

    print("\nSummary")
    print("-------")
    print(f"Turn number: {getattr(state, 'turn_number')}")
    print(f"Active player: P{getattr(state, 'active_player')}")
    print(f"Phase: {getattr(state, 'phase').value}")
    print(f"Winner: {getattr(state, 'winner_id')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate turns and print checkpoint timeline.")
    parser.add_argument("--turns", type=int, default=3, help="Number of turns to simulate.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=ROOT / "dbdatabase" / "dbs_masters.db",
        help="Path to SQLite card database.",
    )
    parser.add_argument(
        "--effect-catalog",
        type=Path,
        default=ROOT / "dbdatabase" / "effect_catalog.json",
        help="Path to optional effect catalog JSON.",
    )
    parser.add_argument(
        "--effect-catalog-overrides",
        type=Path,
        default=ROOT / "dbdatabase" / "effect_catalog_overrides.json",
        help="Path to optional effect catalog overrides JSON.",
    )
    parser.add_argument(
        "--skill-cost-catalog",
        type=Path,
        default=ROOT / "dbdatabase" / "skill_cost_catalog.json",
        help="Path to optional skill cost catalog JSON.",
    )
    args = parser.parse_args()

    if args.turns < 1:
        raise ValueError("--turns must be >= 1")

    global EFFECT_CATALOG_PATH, EFFECT_CATALOG_OVERRIDES_PATH, SKILL_COST_CATALOG_PATH
    EFFECT_CATALOG_PATH = args.effect_catalog if args.effect_catalog.exists() else None
    EFFECT_CATALOG_OVERRIDES_PATH = args.effect_catalog_overrides if args.effect_catalog_overrides.exists() else None
    SKILL_COST_CATALOG_PATH = args.skill_cost_catalog if args.skill_cost_catalog.exists() else None
    state = simulate(args.turns, args.db_path)
    print_timeline(state)


EFFECT_CATALOG_PATH: Path | None = None
EFFECT_CATALOG_OVERRIDES_PATH: Path | None = None
SKILL_COST_CATALOG_PATH: Path | None = None


if __name__ == "__main__":
    main()
