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
    evaluate_match_expectations,
    parse_card_id_text,
    run_scripted_replay,
)
from src.game import RulesEngine, load_game_state_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay scripted human actions from a saved game state.")
    parser.add_argument("--state-input", type=Path, required=True, help="Saved game state JSON path.")
    parser.add_argument("--actions-file", type=Path, required=True, help="File with one human action index per line.")
    parser.add_argument("--human-player", type=int, choices=[1, 2], required=True, help="Human player id used for replay.")
    parser.add_argument("--ai-profile", type=str, default="balanced", help="AI profile for responder/opponent decisions.")
    parser.add_argument("--max-actions", type=int, default=400, help="Action cap for replay.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/replay_result.json"), help="Replay output JSON.")
    parser.add_argument("--expect-winner", type=int, choices=[1, 2], default=None, help="Optional expected winner check.")
    parser.add_argument("--expect-final-turn", type=int, default=None, help="Optional expected final turn number.")
    parser.add_argument(
        "--expect-completed",
        choices=["true", "false"],
        default=None,
        help="Optional expected completion state (winner exists).",
    )
    parser.add_argument(
        "--max-unresolved-effects",
        type=int,
        default=None,
        help="Optional upper bound for unresolved effect resolutions.",
    )
    parser.add_argument("--result-output", type=Path, default=None, help="Optional path to write expectation result JSON.")
    parser.add_argument("--expect-trace-hash", type=str, default=None, help="Optional expected normalized trace hash.")
    parser.add_argument(
        "--ci-mode",
        action="store_true",
        help="Apply CI defaults for result outputs and strict expectation checks.",
    )
    args = parser.parse_args()

    if args.ci_mode:
        if args.result_output is None:
            args.result_output = Path("artifacts/replay_expect_result.json")
        if args.max_unresolved_effects is None:
            args.max_unresolved_effects = 100

    if not args.state_input.exists():
        raise ValueError(f"--state-input not found: {args.state_input}")
    if not args.actions_file.exists():
        raise ValueError(f"--actions-file not found: {args.actions_file}")

    state = load_game_state_json(args.state_input)
    indices = parse_card_id_text(args.actions_file.read_text(encoding="utf-8"))
    session = HumanVsAiSession(
        engine=RulesEngine(),
        state=state,
        human_player_id=int(args.human_player),
        ai_policy=HeuristicPolicy(profile=args.ai_profile),
        setup_metadata={
            "mode": "replay",
            "state_input": str(args.state_input),
            "actions_file": str(args.actions_file),
            "ai_profile": str(args.ai_profile),
        },
    )
    result = run_scripted_replay(session=session, human_action_indices=indices, max_actions=max(1, int(args.max_actions)))
    summary = build_compact_match_summary(
        state=session.state,
        total_actions=session.total_actions,
        human_player_id=int(args.human_player),
        ai_profile=str(args.ai_profile),
        setup_metadata=dict(session.setup_metadata or {}),
    )
    payload = {
        "replay": {
            "consumed_human_actions": result.consumed_human_actions,
            "ai_actions": result.ai_actions,
            "completed": result.completed,
            "winner_id": result.winner_id,
            "final_turn_number": result.final_turn_number,
            "final_phase": result.final_phase,
        },
        "summary": summary,
        "trace": session.to_trace_payload(),
        "trace_hash": compute_trace_hash(session.to_trace_payload()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")

    failures = evaluate_match_expectations(
        summary=summary,
        expect_winner=args.expect_winner,
        expect_final_turn=args.expect_final_turn,
        expect_completed=(None if args.expect_completed is None else (str(args.expect_completed).lower() == "true")),
        max_unresolved_effects=args.max_unresolved_effects,
    )
    if args.expect_trace_hash is not None:
        actual_hash = str(payload.get("trace_hash", ""))
        expected_hash = str(args.expect_trace_hash).strip().lower()
        if actual_hash.lower() != expected_hash:
            failures.append(f"trace_hash expected={expected_hash} actual={actual_hash}")
    if args.result_output is not None:
        args.result_output.parent.mkdir(parents=True, exist_ok=True)
        args.result_output.write_text(
            json.dumps({"ok": len(failures) == 0, "failures": failures, "summary": summary}, indent=2),
            encoding="utf-8",
        )
        print(f"wrote: {args.result_output}")
    if failures:
        for failure in failures:
            print(f"replay_expectation_failed:{failure}")
        sys.exit(7)


if __name__ == "__main__":
    main()
