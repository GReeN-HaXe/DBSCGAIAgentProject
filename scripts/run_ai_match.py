from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import HeuristicPolicy, run_ai_vs_ai
from src.agent.deck_setup import (
    import_deckplanet_deck_text,
    load_sample_game_setup_from_db,
    read_card_ids_file,
    validate_leader_and_deck,
)
from src.agent.deck_legality import validate_deck_legality
from src.agent.simulator import simulation_result_to_dict
from src.db import SQLiteCardRepository
from src.game import RulesEngine
from src.game.effect_rules import default_effect_catalog_path


def _build_deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _init_state(
    engine: RulesEngine,
    *,
    first_player: int,
    p1_leader: int,
    p1_deck: list[int],
    p2_leader: int,
    p2_deck: list[int],
    shuffle_decks: bool,
    random_seed: int | None,
):
    return engine.initialize_game(
        p1_leader_card_id=p1_leader,
        p1_deck_card_ids=p1_deck,
        p2_leader_card_id=p2_leader,
        p2_deck_card_ids=p2_deck,
        first_player=first_player,
        shuffle_decks=shuffle_decks,
        random_seed=random_seed,
    )


def _using_real_deck_source(args: argparse.Namespace) -> bool:
    if args.use_db_sample_decks:
        return True
    if args.p1_deckplanet_file is not None and args.p2_deckplanet_file is not None:
        return True
    return all(x is not None for x in [args.p1_leader_id, args.p2_leader_id, args.p1_deck_file, args.p2_deck_file])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI-vs-AI match and export decision trace JSON.")
    parser.add_argument("--max-actions", type=int, default=120, help="Maximum action count before stopping.")
    parser.add_argument("--trace-top-k", type=int, default=3, help="Number of ranked candidates to store per decision.")
    parser.add_argument("--p1-profile", type=str, default="balanced", help="Heuristic profile for player 1.")
    parser.add_argument("--p2-profile", type=str, default="balanced", help="Heuristic profile for player 2.")
    parser.add_argument("--first-player", type=int, choices=[1, 2], default=1, help="Starting player id.")
    parser.add_argument("--shuffle-decks", action="store_true", help="Shuffle decks before opening draws.")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed used when shuffling decks.")
    parser.add_argument("--effect-catalog", type=Path, default=default_effect_catalog_path(ROOT), help="Path to effect catalog merged JSON, shard manifest JSON, or shard directory.")
    parser.add_argument("--effect-catalog-overrides", type=Path, default=Path("dbdatabase/effect_catalog_overrides.json"), help="Optional path to effect catalog overrides JSON.")
    parser.add_argument("--skill-cost-catalog", type=Path, default=Path("dbdatabase/skill_cost_catalog.json"), help="Path to skill cost catalog JSON.")
    parser.add_argument("--db-path", type=Path, default=Path("dbdatabase/dbs_masters.db"), help="Path to SQLite card database.")
    parser.add_argument("--p1-leader-id", type=int, default=None, help="Optional explicit P1 leader card id.")
    parser.add_argument("--p2-leader-id", type=int, default=None, help="Optional explicit P2 leader card id.")
    parser.add_argument("--p1-deck-file", type=Path, default=None, help="Optional P1 deck id file.")
    parser.add_argument("--p2-deck-file", type=Path, default=None, help="Optional P2 deck id file.")
    parser.add_argument("--p1-deckplanet-file", type=Path, default=None, help="Optional DeckPlanet text export for player 1.")
    parser.add_argument("--p2-deckplanet-file", type=Path, default=None, help="Optional DeckPlanet text export for player 2.")
    parser.add_argument("--use-db-sample-decks", action="store_true", help="Use DB-derived sample leaders/decks.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/ai_match_trace.json"), help="Output JSON path.")
    args = parser.parse_args()

    repo = SQLiteCardRepository(args.db_path) if args.db_path.exists() else None
    effect_catalog = args.effect_catalog if args.effect_catalog.exists() else None
    effect_catalog_overrides = args.effect_catalog_overrides if args.effect_catalog_overrides.exists() else None
    skill_cost_catalog = args.skill_cost_catalog if args.skill_cost_catalog.exists() else None
    engine = RulesEngine(
        card_repository=repo,
        skill_cost_rules_path=skill_cost_catalog,
        effect_rules_path=effect_catalog,
        effect_rule_overrides_path=effect_catalog_overrides,
    )
    if args.use_db_sample_decks:
        if not args.db_path.exists():
            raise ValueError("--use-db-sample-decks requires --db-path to exist.")
        p1_leader, p1_deck, p2_leader, p2_deck = load_sample_game_setup_from_db(args.db_path, deck_size=60)
    elif args.p1_deckplanet_file is not None and args.p2_deckplanet_file is not None:
        if not args.db_path.exists():
            raise ValueError("DeckPlanet import requires --db-path to exist.")
        p1_payload = import_deckplanet_deck_text(
            db_path=args.db_path,
            raw=args.p1_deckplanet_file.read_text(encoding="utf-8"),
        )
        p2_payload = import_deckplanet_deck_text(
            db_path=args.db_path,
            raw=args.p2_deckplanet_file.read_text(encoding="utf-8"),
        )
        if p1_payload["unresolved_card_numbers"] or p2_payload["unresolved_card_numbers"]:
            raise ValueError(
                "DeckPlanet import has unresolved card numbers: "
                f"p1={p1_payload['unresolved_card_numbers'][:10]} "
                f"p2={p2_payload['unresolved_card_numbers'][:10]}"
            )
        p1_leader = int(p1_payload["leader_id"])
        p2_leader = int(p2_payload["leader_id"])
        p1_deck = list(p1_payload["deck_ids"])
        p2_deck = list(p2_payload["deck_ids"])
    elif all(x is not None for x in [args.p1_leader_id, args.p2_leader_id, args.p1_deck_file, args.p2_deck_file]):
        p1_leader = int(args.p1_leader_id)
        p2_leader = int(args.p2_leader_id)
        p1_deck = read_card_ids_file(args.p1_deck_file)
        p2_deck = read_card_ids_file(args.p2_deck_file)
        if not args.db_path.exists():
            raise ValueError("Deck validation requires --db-path to exist.")
        validate_leader_and_deck(db_path=args.db_path, leader_id=p1_leader, deck_ids=p1_deck, expected_deck_size=60)
        validate_leader_and_deck(db_path=args.db_path, leader_id=p2_leader, deck_ids=p2_deck, expected_deck_size=60)
    else:
        p1_leader, p1_deck, p2_leader, p2_deck = 1, _build_deck(1000), 2, _build_deck(2000)

    if repo is not None and _using_real_deck_source(args):
        validate_deck_legality(repo=repo, leader_id=p1_leader, deck_ids=p1_deck, expected_deck_size=60)
        validate_deck_legality(repo=repo, leader_id=p2_leader, deck_ids=p2_deck, expected_deck_size=60)

    state = _init_state(
        engine,
        first_player=int(args.first_player),
        p1_leader=p1_leader,
        p1_deck=p1_deck,
        p2_leader=p2_leader,
        p2_deck=p2_deck,
        shuffle_decks=bool(args.shuffle_decks),
        random_seed=args.seed,
    )
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
