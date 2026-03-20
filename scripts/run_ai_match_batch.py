from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import HeuristicPolicy, build_review_trace_payload, build_training_trace_rows, run_ai_vs_ai
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


def _resolve_decks(args: argparse.Namespace) -> tuple[int, list[int], int, list[int]]:
    if args.use_db_sample_decks:
        if not args.db_path.exists():
            raise ValueError("--use-db-sample-decks requires --db-path to exist.")
        return load_sample_game_setup_from_db(args.db_path, deck_size=60)
    if args.p1_deckplanet_file is not None and args.p2_deckplanet_file is not None:
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
        return (
            int(p1_payload["leader_id"]),
            list(p1_payload["deck_ids"]),
            int(p2_payload["leader_id"]),
            list(p2_payload["deck_ids"]),
        )
    if all(x is not None for x in [args.p1_leader_id, args.p2_leader_id, args.p1_deck_file, args.p2_deck_file]):
        p1_leader = int(args.p1_leader_id)
        p2_leader = int(args.p2_leader_id)
        p1_deck = read_card_ids_file(args.p1_deck_file)
        p2_deck = read_card_ids_file(args.p2_deck_file)
        if not args.db_path.exists():
            raise ValueError("Deck validation requires --db-path to exist.")
        validate_leader_and_deck(db_path=args.db_path, leader_id=p1_leader, deck_ids=p1_deck, expected_deck_size=60)
        validate_leader_and_deck(db_path=args.db_path, leader_id=p2_leader, deck_ids=p2_deck, expected_deck_size=60)
        return p1_leader, p1_deck, p2_leader, p2_deck
    return 1, _build_deck(1000), 2, _build_deck(2000)


def _using_real_deck_source(args: argparse.Namespace) -> bool:
    if args.use_db_sample_decks:
        return True
    if args.p1_deckplanet_file is not None and args.p2_deckplanet_file is not None:
        return True
    return all(x is not None for x in [args.p1_leader_id, args.p2_leader_id, args.p1_deck_file, args.p2_deck_file])


def _output_path(output_dir: Path, prefix: str, index: int, digits: int) -> Path:
    return output_dir / f"{prefix}{index:0{digits}d}.json"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate many AI-vs-AI traces for benchmark building.")
    parser.add_argument("--count", type=int, default=10, help="Number of matches to generate.")
    parser.add_argument("--start-index", type=int, default=1, help="Starting numeric suffix.")
    parser.add_argument("--digits", type=int, default=3, help="Filename zero-padding width.")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/phase22_source"), help="Directory for raw trace outputs.")
    parser.add_argument("--filename-prefix", type=str, default="ai_match_trace_", help="Trace filename prefix.")
    parser.add_argument("--summary-output", type=Path, default=Path("artifacts/phase22_source/ai_match_batch_summary.json"), help="Batch summary JSON path.")
    parser.add_argument("--resume-skip-existing", action=argparse.BooleanOptionalAction, default=True, help="Skip raw trace files that already exist.")
    parser.add_argument("--normalize", action="store_true", help="Also write normalized review/training artifacts for each trace.")
    parser.add_argument("--normalized-output-dir", type=Path, default=Path("artifacts/phase22_normalized"), help="Directory for normalized outputs when --normalize is set.")
    parser.add_argument("--include-bookkeeping", action="store_true", help="Keep bookkeeping actions in normalized outputs.")
    parser.add_argument("--max-actions", type=int, default=120, help="Maximum action count before stopping.")
    parser.add_argument("--trace-top-k", type=int, default=3, help="Number of ranked candidates to store per decision.")
    parser.add_argument("--p1-profile", type=str, default="balanced", help="Heuristic profile for player 1.")
    parser.add_argument("--p2-profile", type=str, default="balanced", help="Heuristic profile for player 2.")
    parser.add_argument("--alternate-first-player", action=argparse.BooleanOptionalAction, default=True, help="Alternate first player across runs.")
    parser.add_argument("--first-player", type=int, choices=[1, 2], default=1, help="Base starting player id.")
    parser.add_argument("--shuffle-decks", action=argparse.BooleanOptionalAction, default=True, help="Shuffle decks before opening draws.")
    parser.add_argument("--seed", type=int, default=1, help="Base random seed used when shuffling decks.")
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
    p1_leader, p1_deck, p2_leader, p2_deck = _resolve_decks(args)
    if repo is not None and _using_real_deck_source(args):
        validate_deck_legality(repo=repo, leader_id=p1_leader, deck_ids=p1_deck, expected_deck_size=60)
        validate_deck_legality(repo=repo, leader_id=p2_leader, deck_ids=p2_deck, expected_deck_size=60)

    outputs: list[dict[str, object]] = []
    for offset in range(max(1, int(args.count))):
        run_index = int(args.start_index) + offset
        raw_output = _output_path(args.output_dir, args.filename_prefix, run_index, int(args.digits))
        if bool(args.resume_skip_existing) and raw_output.exists():
            outputs.append(
                {
                    "index": run_index,
                    "raw_output": str(raw_output),
                    "status": "skipped_existing",
                }
            )
            continue
        first_player = int(args.first_player)
        if bool(args.alternate_first_player) and offset % 2 == 1:
            first_player = 2 if first_player == 1 else 1
        seed = (int(args.seed) + offset) if bool(args.shuffle_decks) else None
        state = _init_state(
            engine,
            first_player=first_player,
            p1_leader=p1_leader,
            p1_deck=p1_deck,
            p2_leader=p2_leader,
            p2_deck=p2_deck,
            shuffle_decks=bool(args.shuffle_decks),
            random_seed=seed,
        )
        result = run_ai_vs_ai(
            engine=engine,
            state=state,
            p1_policy=HeuristicPolicy(profile=args.p1_profile),
            p2_policy=HeuristicPolicy(profile=args.p2_profile),
            max_actions=max(1, int(args.max_actions)),
            capture_trace=True,
            trace_top_k=max(1, int(args.trace_top_k)),
        )
        payload = simulation_result_to_dict(result)
        _write_json(raw_output, payload)
        print(f"wrote: {raw_output}")
        row: dict[str, object] = {
            "index": run_index,
            "raw_output": str(raw_output),
            "status": "generated",
            "seed": seed,
            "first_player": first_player,
            "total_actions": result.total_actions,
            "winner_id": result.final_state.winner_id,
            "stop_reason": result.stop_reason,
        }
        if bool(args.normalize):
            review_output = args.normalized_output_dir / f"{raw_output.stem}_review.json"
            training_output = args.normalized_output_dir / f"{raw_output.stem}_training.jsonl"
            review_payload = build_review_trace_payload(payload, include_bookkeeping=bool(args.include_bookkeeping))
            training_rows = build_training_trace_rows(payload, include_bookkeeping=bool(args.include_bookkeeping))
            _write_json(review_output, review_payload)
            _write_jsonl(training_output, training_rows)
            print(f"wrote: {review_output}")
            print(f"wrote: {training_output}")
            row.update(
                {
                    "review_output": str(review_output),
                    "training_output": str(training_output),
                    "decision_count": int(review_payload.get("decision_count", 0)),
                }
            )
        outputs.append(row)

    summary = {
        "schema_version": "ai_match_batch.v1",
        "count": int(args.count),
        "start_index": int(args.start_index),
        "shuffle_decks": bool(args.shuffle_decks),
        "seed": int(args.seed),
        "alternate_first_player": bool(args.alternate_first_player),
        "p1_profile": args.p1_profile,
        "p2_profile": args.p2_profile,
        "normalize": bool(args.normalize),
        "outputs": outputs,
    }
    _write_json(args.summary_output, summary)
    print(f"wrote: {args.summary_output}")


if __name__ == "__main__":
    main()
