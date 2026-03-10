from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import (
    HeuristicPolicy,
    HumanVsAiSession,
    build_compact_match_summary,
    compute_trace_hash,
    describe_action,
    evaluate_match_expectations,
    summarize_state_for_cli,
    validate_deck_legality,
)
from src.agent.deck_setup import (
    load_sample_game_setup_from_db,
    read_card_ids_file,
    validate_leader_and_deck,
)
from src.db import SQLiteCardRepository
from src.game import RulesEngine, load_game_state_json, save_game_state_json


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
) -> object:
    return engine.initialize_game(
        p1_leader_card_id=p1_leader,
        p1_deck_card_ids=p1_deck,
        p2_leader_card_id=p2_leader,
        p2_deck_card_ids=p2_deck,
        first_player=first_player,
        shuffle_decks=shuffle_decks,
        random_seed=random_seed,
    )


def _card_name_resolver(repo: SQLiteCardRepository | None):
    def _resolve(card_id: int) -> str:
        if repo is None:
            return f"card_id={card_id}"
        try:
            card = repo.get_by_id(int(card_id))
            tags: list[str] = []
            if card.has_counter:
                tags.append("Counter")
            if card.has_activate_main:
                tags.append("ActMain")
            if card.has_activate_battle:
                tags.append("ActBattle")
            if card.has_draw:
                tags.append("Draw")
            cost = card.energy_cost_int if card.energy_cost_int is not None else card.card_energy_cost or "-"
            power = card.power_int if card.power_int is not None else card.card_power or "-"
            combo = card.combo_power_int if card.combo_power_int is not None else card.card_combo_power or "-"
            tag_suffix = f" tags={','.join(tags)}" if tags else ""
            return f"{card.card_number} {card.card_name} cost={cost} power={power} combo={combo}{tag_suffix}"
        except Exception:
            return f"card_id={card_id}"

    return _resolve


def _print_human_actions(session: HumanVsAiSession, *, card_name_resolver) -> list[object]:
    legal = session.legal_actions_for_human()
    print("\nLegal actions:")
    for i, action in enumerate(legal):
        print(f"  [{i}] {describe_action(action, state=session.state, card_name_resolver=card_name_resolver)}")
    return legal


def _revealed_hand_players(*, human_player: int, reveal_ai_hand: bool, reveal_all_hands: bool) -> tuple[int, ...]:
    if reveal_all_hands:
        return (1, 2)
    if reveal_ai_hand:
        ai_player = 1 if int(human_player) == 2 else 2
        return (int(human_player), ai_player)
    return (int(human_player),)


def main() -> None:
    parser = argparse.ArgumentParser(description="Play DBS card game against heuristic AI in terminal.")
    parser.add_argument("--human-player", type=int, choices=[1, 2], default=1, help="Human player id (1 or 2).")
    parser.add_argument("--ai-profile", type=str, default="balanced", help="AI profile (balanced/aggressive/control).")
    parser.add_argument("--first-player", type=int, choices=[1, 2], default=1, help="Starting player id.")
    parser.add_argument("--shuffle-decks", action="store_true", help="Shuffle decks before opening draws.")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed used when shuffling decks.")
    parser.add_argument("--max-actions", type=int, default=300, help="Global action cap for the session.")
    parser.add_argument("--effect-catalog", type=Path, default=Path("dbdatabase/effect_catalog.json"), help="Path to effect catalog JSON.")
    parser.add_argument("--db-path", type=Path, default=Path("dbdatabase/dbs_masters.db"), help="Path to SQLite card database.")
    parser.add_argument("--p1-leader-id", type=int, default=None, help="Optional explicit P1 leader card id.")
    parser.add_argument("--p2-leader-id", type=int, default=None, help="Optional explicit P2 leader card id.")
    parser.add_argument("--p1-deck-file", type=Path, default=None, help="Optional P1 deck id file (comma/newline separated ids).")
    parser.add_argument("--p2-deck-file", type=Path, default=None, help="Optional P2 deck id file (comma/newline separated ids).")
    parser.add_argument(
        "--use-db-sample-decks",
        action="store_true",
        help="Use first two leaders and first available non-leader cards from DB to build two decks.",
    )
    parser.add_argument(
        "--scripted-actions-file",
        type=Path,
        default=None,
        help="Optional file with one human action index per line for non-interactive runs.",
    )
    parser.add_argument(
        "--trace-output",
        type=Path,
        default=Path("artifacts/human_vs_ai_trace.json"),
        help="JSON trace output path.",
    )
    parser.add_argument(
        "--load-state-input",
        type=Path,
        default=None,
        help="Optional path to load a previously saved game-state JSON and resume.",
    )
    parser.add_argument(
        "--save-state-output",
        type=Path,
        default=Path("artifacts/human_vs_ai_state.json"),
        help="Path to save game-state JSON on exit/finish.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("artifacts/human_vs_ai_summary.json"),
        help="Path to write compact match summary JSON.",
    )
    parser.add_argument("--result-output", type=Path, default=None, help="Optional path to write expectation result JSON.")
    parser.add_argument(
        "--ci-mode",
        action="store_true",
        help="Apply CI defaults for result outputs and strict expectation checks.",
    )
    parser.add_argument("--expect-winner", type=int, choices=[1, 2], default=None, help="Optional expected winner.")
    parser.add_argument("--expect-final-turn", type=int, default=None, help="Optional expected final turn number.")
    parser.add_argument(
        "--expect-completed",
        choices=["true", "false"],
        default=None,
        help="Optional expectation whether match should be completed (winner exists).",
    )
    parser.add_argument(
        "--max-unresolved-effects",
        type=int,
        default=None,
        help="Optional upper bound for unresolved effect resolutions.",
    )
    parser.add_argument(
        "--reveal-ai-hand",
        action="store_true",
        help="Debug mode: reveal the AI player's hand in terminal summaries.",
    )
    parser.add_argument(
        "--reveal-all-hands",
        action="store_true",
        help="Debug mode: reveal both players' hands in terminal summaries.",
    )
    args = parser.parse_args()

    if args.ci_mode:
        if args.result_output is None:
            args.result_output = Path("artifacts/human_vs_ai_result.json")
        if args.max_unresolved_effects is None:
            args.max_unresolved_effects = 100

    repo = SQLiteCardRepository(args.db_path) if args.db_path.exists() else None
    effect_catalog = args.effect_catalog if args.effect_catalog.exists() else None
    engine = RulesEngine(card_repository=repo, effect_rules_path=effect_catalog)

    if args.load_state_input is not None:
        if not args.load_state_input.exists():
            raise ValueError(f"--load-state-input path does not exist: {args.load_state_input}")
        state = load_game_state_json(args.load_state_input)
        setup_meta = {
            "mode": "resume",
            "load_state_input": str(args.load_state_input),
            "first_player": int(args.first_player),
            "shuffle_decks": bool(args.shuffle_decks),
            "seed": args.seed,
        }
    else:
        if args.use_db_sample_decks:
            if not args.db_path.exists():
                raise ValueError("--use-db-sample-decks requires --db-path to exist.")
            p1_leader, p1_deck, p2_leader, p2_deck = load_sample_game_setup_from_db(args.db_path, deck_size=60)
        elif all(x is not None for x in [args.p1_leader_id, args.p2_leader_id, args.p1_deck_file, args.p2_deck_file]):
            p1_leader = int(args.p1_leader_id)
            p2_leader = int(args.p2_leader_id)
            p1_deck = read_card_ids_file(args.p1_deck_file)
            p2_deck = read_card_ids_file(args.p2_deck_file)
            if not args.db_path.exists():
                raise ValueError("Deck validation requires --db-path to exist.")
            validate_leader_and_deck(db_path=args.db_path, leader_id=p1_leader, deck_ids=p1_deck, expected_deck_size=60)
            validate_leader_and_deck(db_path=args.db_path, leader_id=p2_leader, deck_ids=p2_deck, expected_deck_size=60)
            if repo is not None:
                validate_deck_legality(repo=repo, leader_id=p1_leader, deck_ids=p1_deck, expected_deck_size=60)
                validate_deck_legality(repo=repo, leader_id=p2_leader, deck_ids=p2_deck, expected_deck_size=60)
        else:
            p1_leader, p1_deck, p2_leader, p2_deck = 1, _build_deck(1000), 2, _build_deck(2000)
        setup_meta = {
            "mode": "fresh",
            "first_player": int(args.first_player),
            "shuffle_decks": bool(args.shuffle_decks),
            "seed": args.seed,
            "p1_leader_id": int(p1_leader),
            "p2_leader_id": int(p2_leader),
            "p1_deck_size": len(p1_deck),
            "p2_deck_size": len(p2_deck),
            "deck_source": (
                "db_sample"
                if args.use_db_sample_decks
                else ("deck_files" if all(x is not None for x in [args.p1_leader_id, args.p2_leader_id, args.p1_deck_file, args.p2_deck_file]) else "synthetic")
            ),
        }

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
    session = HumanVsAiSession(
        engine=engine,
        state=state,
        human_player_id=int(args.human_player),
        ai_policy=HeuristicPolicy(profile=args.ai_profile),
        setup_metadata=setup_meta,
    )
    card_name_resolver = _card_name_resolver(repo)
    revealed_hand_players = _revealed_hand_players(
        human_player=int(args.human_player),
        reveal_ai_hand=bool(args.reveal_ai_hand),
        reveal_all_hands=bool(args.reveal_all_hands),
    )

    scripted_inputs: list[str] = []
    if args.scripted_actions_file is not None and args.scripted_actions_file.exists():
        scripted_inputs = [line.strip() for line in args.scripted_actions_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    scripted_ptr = 0

    print("Human-vs-AI match started.")
    print("Commands: index number, s (state), q (quit)")
    last_summary_payload: dict[str, object] = {}

    def _write_outputs_and_exit_banner() -> None:
        nonlocal last_summary_payload
        trace_payload = session.to_trace_payload()
        trace_hash = compute_trace_hash(trace_payload)
        args.trace_output.parent.mkdir(parents=True, exist_ok=True)
        args.trace_output.write_text(
            json.dumps({"trace": trace_payload, "trace_hash": trace_hash}, indent=2),
            encoding="utf-8",
        )
        print(f"wrote: {args.trace_output}")
        if args.save_state_output is not None:
            save_game_state_json(session.state, args.save_state_output)
            print(f"wrote: {args.save_state_output}")
        if args.summary_output is not None:
            summary_payload = build_compact_match_summary(
                state=session.state,
                total_actions=session.total_actions,
                human_player_id=int(args.human_player),
                ai_profile=str(args.ai_profile),
                setup_metadata=dict(session.setup_metadata or {}),
            )
            summary_payload["trace_hash"] = trace_hash
            last_summary_payload = dict(summary_payload)
            args.summary_output.parent.mkdir(parents=True, exist_ok=True)
            args.summary_output.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
            print(f"wrote: {args.summary_output}")

    def _evaluate_expectations_and_exit_if_needed() -> None:
        nonlocal last_summary_payload
        if not last_summary_payload:
            last_summary_payload = build_compact_match_summary(
                state=session.state,
                total_actions=session.total_actions,
                human_player_id=int(args.human_player),
                ai_profile=str(args.ai_profile),
                setup_metadata=dict(session.setup_metadata or {}),
            )
        expectation_failures = evaluate_match_expectations(
            summary=last_summary_payload,
            expect_winner=args.expect_winner,
            expect_final_turn=args.expect_final_turn,
            expect_completed=(
                None if args.expect_completed is None else (str(args.expect_completed).strip().lower() == "true")
            ),
            max_unresolved_effects=args.max_unresolved_effects,
        )
        if args.result_output is not None:
            result_payload = {
                "ok": len(expectation_failures) == 0,
                "failures": expectation_failures,
                "summary": last_summary_payload,
                "trace_hash": last_summary_payload.get("trace_hash"),
            }
            args.result_output.parent.mkdir(parents=True, exist_ok=True)
            args.result_output.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")
            print(f"wrote: {args.result_output}")
        if expectation_failures:
            for failure in expectation_failures:
                print(f"match_expectation_failed:{failure}")
            sys.exit(6)

    while not session.is_over() and session.total_actions < max(1, int(args.max_actions)):
        ai_actions = session.step_ai_until_human_turn_with_context()
        for entry in ai_actions:
            action = entry["action"]
            state_before = entry["state_before"]
            print(
                "AI played: "
                + describe_action(
                    action,
                    state=state_before,
                    card_name_resolver=card_name_resolver,
                )
            )
        if session.is_over():
            break
        print(
            "\n"
            + summarize_state_for_cli(
                session.state,
                card_name_resolver=card_name_resolver,
                reveal_hand_player_ids=revealed_hand_players,
            )
        )
        legal = _print_human_actions(session, card_name_resolver=card_name_resolver)
        if not legal:
            print("No legal actions available for human. Ending session.")
            break
        while True:
            if scripted_ptr < len(scripted_inputs):
                raw = scripted_inputs[scripted_ptr].strip().lower()
                scripted_ptr += 1
                print(f"scripted_input: {raw}")
            else:
                raw = input("Choose action index (or s/q): ").strip().lower()
            if raw == "q":
                print("Session ended by user.")
                _write_outputs_and_exit_banner()
                _evaluate_expectations_and_exit_if_needed()
                return
            if raw == "s":
                print(
                    "\n"
                    + summarize_state_for_cli(
                        session.state,
                        card_name_resolver=card_name_resolver,
                        reveal_hand_player_ids=revealed_hand_players,
                    )
                )
                continue
            try:
                idx = int(raw)
            except ValueError:
                print("Invalid input. Enter an action index, s, or q.")
                continue
            if idx < 0 or idx >= len(legal):
                print(f"Index out of range. Valid range: 0..{len(legal)-1}")
                continue
            chosen = legal[idx]
            chosen_text = describe_action(chosen, state=session.state, card_name_resolver=card_name_resolver)
            session.apply_human_action_by_index(idx)
            print(f"You played: {chosen_text}")
            break

    print("\nMatch finished.")
    print(
        summarize_state_for_cli(
            session.state,
            card_name_resolver=card_name_resolver,
            reveal_hand_player_ids=revealed_hand_players,
        )
    )
    print(f"winner={session.state.winner_id} total_actions={session.total_actions}")
    _write_outputs_and_exit_banner()
    _evaluate_expectations_and_exit_if_needed()


if __name__ == "__main__":
    main()
