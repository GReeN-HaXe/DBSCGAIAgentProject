from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import HeuristicPolicy, merge_phase7_trace_artifacts, run_ai_vs_ai, simulation_result_to_phase7_trace_artifact, validate_deck_legality
from src.agent.deck_setup import load_sample_game_setup_from_db, read_card_ids_file, validate_leader_and_deck
from src.db import SQLiteCardRepository
from src.game import RulesEngine


def _build_deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _leader_meta(repo, leader_id: int) -> dict[str, object]:
    if repo is None:
        return {"leader_id": int(leader_id), "leader_name": f"leader_{leader_id}"}
    try:
        card = repo.get_by_id(int(leader_id), source_table="cards")
        return {
            "leader_id": int(leader_id),
            "leader_name": str(getattr(card, "card_name", "") or f"leader_{leader_id}"),
            "leader_color": str(getattr(card, "card_color", "") or ""),
            "leader_number": str(getattr(card, "card_number", "") or ""),
        }
    except Exception:
        return {"leader_id": int(leader_id), "leader_name": f"leader_{leader_id}"}


def _resolve_game_setup(
    *,
    db_path: Path,
    repo,
    use_db_sample_decks: bool,
    p1_leader_id: int | None,
    p2_leader_id: int | None,
    p1_deck_file: Path | None,
    p2_deck_file: Path | None,
) -> tuple[int, list[int], int, list[int], str]:
    if use_db_sample_decks:
        if not db_path.exists():
            raise ValueError("--use-db-sample-decks requires --db-path to exist.")
        p1_leader, p1_deck, p2_leader, p2_deck = load_sample_game_setup_from_db(db_path, deck_size=60)
        return p1_leader, p1_deck, p2_leader, p2_deck, "db_sample"
    if all(x is not None for x in [p1_leader_id, p2_leader_id, p1_deck_file, p2_deck_file]):
        p1_leader = int(p1_leader_id)
        p2_leader = int(p2_leader_id)
        p1_deck = read_card_ids_file(p1_deck_file)
        p2_deck = read_card_ids_file(p2_deck_file)
        if not db_path.exists():
            raise ValueError("Deck validation requires --db-path to exist.")
        validate_leader_and_deck(db_path=db_path, leader_id=p1_leader, deck_ids=p1_deck, expected_deck_size=60)
        validate_leader_and_deck(db_path=db_path, leader_id=p2_leader, deck_ids=p2_deck, expected_deck_size=60)
        if repo is not None:
            validate_deck_legality(repo=repo, leader_id=p1_leader, deck_ids=p1_deck, expected_deck_size=60)
            validate_deck_legality(repo=repo, leader_id=p2_leader, deck_ids=p2_deck, expected_deck_size=60)
        return p1_leader, p1_deck, p2_leader, p2_deck, "deck_files"
    return 1, _build_deck(1000), 2, _build_deck(2000), "synthetic"


def _init_state(
    engine: RulesEngine,
    *,
    p1_leader_id: int,
    p1_deck: list[int],
    p2_leader_id: int,
    p2_deck: list[int],
    shuffle_decks: bool,
    random_seed: int | None,
):
    return engine.initialize_game(
        p1_leader_card_id=p1_leader_id,
        p1_deck_card_ids=p1_deck,
        p2_leader_card_id=p2_leader_id,
        p2_deck_card_ids=p2_deck,
        shuffle_decks=shuffle_decks,
        random_seed=random_seed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Phase 7-compatible self-play dataset from repeated AI-vs-AI matches.")
    parser.add_argument("--games", type=int, default=4, help="Number of self-play matches to generate.")
    parser.add_argument("--max-actions", type=int, default=120, help="Maximum action count per game.")
    parser.add_argument("--validation-ratio", type=float, default=0.2, help="Validation split ratio for exported dataset.")
    parser.add_argument("--seed", type=int, default=11, help="Base random seed for shuffled self-play runs.")
    parser.add_argument("--shuffle-decks", action="store_true", help="Shuffle decks before draws.")
    parser.add_argument("--p1-profile", type=str, default="balanced", help="Heuristic profile for player 1.")
    parser.add_argument("--p2-profile", type=str, default="balanced", help="Heuristic profile for player 2.")
    parser.add_argument("--p1-leader-id", type=int, default=None, help="Leader card id for player 1.")
    parser.add_argument("--p2-leader-id", type=int, default=None, help="Leader card id for player 2.")
    parser.add_argument("--p1-deck-file", type=Path, default=None, help="Optional P1 deck id file.")
    parser.add_argument("--p2-deck-file", type=Path, default=None, help="Optional P2 deck id file.")
    parser.add_argument("--use-db-sample-decks", action="store_true", help="Use DB-derived sample leaders/decks.")
    parser.add_argument("--effect-catalog", type=Path, default=Path("dbdatabase/effect_catalog.json"), help="Path to effect catalog JSON.")
    parser.add_argument("--skill-cost-catalog", type=Path, default=Path("dbdatabase/skill_cost_catalog.json"), help="Path to skill cost catalog JSON.")
    parser.add_argument("--db-path", type=Path, default=Path("dbdatabase/dbs_masters.db"), help="Path to SQLite card database.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase8_self_play_dataset.json"), help="Output dataset path.")
    args = parser.parse_args()

    repo = SQLiteCardRepository(args.db_path) if args.db_path.exists() else None
    effect_catalog = args.effect_catalog if args.effect_catalog.exists() else None
    skill_cost_catalog = args.skill_cost_catalog if args.skill_cost_catalog.exists() else None
    engine = RulesEngine(card_repository=repo, skill_cost_rules_path=skill_cost_catalog, effect_rules_path=effect_catalog)
    p1_leader_id, p1_deck, p2_leader_id, p2_deck, deck_source = _resolve_game_setup(
        db_path=args.db_path,
        repo=repo,
        use_db_sample_decks=bool(args.use_db_sample_decks),
        p1_leader_id=args.p1_leader_id,
        p2_leader_id=args.p2_leader_id,
        p1_deck_file=args.p1_deck_file,
        p2_deck_file=args.p2_deck_file,
    )
    p1_meta = _leader_meta(repo, int(p1_leader_id))
    p2_meta = _leader_meta(repo, int(p2_leader_id))
    archetype_pair = (
        f"{args.p1_profile}:{p1_meta.get('leader_name', p1_meta.get('leader_id'))}"
        f"_vs_"
        f"{args.p2_profile}:{p2_meta.get('leader_name', p2_meta.get('leader_id'))}"
    )

    artifacts: list[dict[str, object]] = []
    source_names: list[str] = []
    for i in range(max(1, int(args.games))):
        state = _init_state(
            engine,
            p1_leader_id=int(p1_leader_id),
            p1_deck=p1_deck,
            p2_leader_id=int(p2_leader_id),
            p2_deck=p2_deck,
            shuffle_decks=bool(args.shuffle_decks),
            random_seed=(int(args.seed) + i) if args.shuffle_decks else None,
        )
        result = run_ai_vs_ai(
            engine=engine,
            state=state,
            p1_policy=HeuristicPolicy(profile=str(args.p1_profile)),
            p2_policy=HeuristicPolicy(profile=str(args.p2_profile)),
            max_actions=max(1, int(args.max_actions)),
            capture_trace=True,
        )
        source_name = f"self_play_game_{i+1}"
        artifacts.append(
            simulation_result_to_phase7_trace_artifact(
                result,
                p1_profile=str(args.p1_profile),
                p2_profile=str(args.p2_profile),
                source_name=source_name,
                setup_metadata={
                    "p1_leader": p1_meta,
                    "p2_leader": p2_meta,
                    "archetype_pair": archetype_pair,
                    "deck_source": deck_source,
                    "p1_deck_size": len(p1_deck),
                    "p2_deck_size": len(p2_deck),
                },
            )
        )
        source_names.append(source_name)

    dataset = merge_phase7_trace_artifacts(
        artifacts,
        source_names=source_names,
        validation_ratio=float(args.validation_ratio),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
