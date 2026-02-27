from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import HeuristicPolicy, run_ai_vs_ai
from src.agent.simulator import simulation_result_to_dict
from src.db import SQLiteCardRepository
from src.game import RulesEngine


def _build_deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _init_state(engine: RulesEngine):
    return engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_build_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_build_deck(2000),
        shuffle_decks=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI-vs-AI match and export decision trace JSON.")
    parser.add_argument("--max-actions", type=int, default=120, help="Maximum action count before stopping.")
    parser.add_argument("--trace-top-k", type=int, default=3, help="Number of ranked candidates to store per decision.")
    parser.add_argument("--p1-profile", type=str, default="balanced", help="Heuristic profile for player 1.")
    parser.add_argument("--p2-profile", type=str, default="balanced", help="Heuristic profile for player 2.")
    parser.add_argument("--effect-catalog", type=Path, default=Path("dbdatabase/effect_catalog.json"), help="Path to effect catalog JSON.")
    parser.add_argument("--db-path", type=Path, default=Path("dbdatabase/dbs_masters.db"), help="Path to SQLite card database.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/ai_match_trace.json"), help="Output JSON path.")
    args = parser.parse_args()

    repo = SQLiteCardRepository(args.db_path) if args.db_path.exists() else None
    effect_catalog = args.effect_catalog if args.effect_catalog.exists() else None
    engine = RulesEngine(card_repository=repo, effect_rules_path=effect_catalog)
    state = _init_state(engine)
    result = run_ai_vs_ai(
        engine=engine,
        state=state,
        p1_policy=HeuristicPolicy(profile=args.p1_profile),
        p2_policy=HeuristicPolicy(profile=args.p2_profile),
        max_actions=max(1, args.max_actions),
        capture_trace=True,
        trace_top_k=max(1, args.trace_top_k),
    )
    payload = simulation_result_to_dict(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")
    print(f"actions: {result.total_actions} winner: {result.final_state.winner_id}")


if __name__ == "__main__":
    main()
