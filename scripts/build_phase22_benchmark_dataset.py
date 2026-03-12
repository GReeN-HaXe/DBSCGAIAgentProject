from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.dataset import build_phase7_dataset


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def _normalize_trace_actions(payload: dict[str, object]) -> list[dict[str, object]]:
    if isinstance(payload.get("decision_trace"), list):
        rows: list[dict[str, object]] = []
        for row in payload["decision_trace"]:
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "action_type": row.get("chosen_action_type"),
                    "action": row.get("chosen_action_text", ""),
                    "phase": row.get("phase", ""),
                    "actor_kind": "ai",
                    "player_id": row.get("actor_player_id"),
                    "turn_number": row.get("turn_number"),
                    "state_snapshot": row.get("state_snapshot", {}),
                }
            )
        return rows
    if isinstance(payload.get("trace"), dict):
        trace = payload["trace"]
        if isinstance(trace, dict) and isinstance(trace.get("actions"), list):
            return [row for row in trace["actions"] if isinstance(row, dict)]
    actions = payload.get("actions", [])
    if isinstance(actions, list):
        return [row for row in actions if isinstance(row, dict)]
    return []


def _trace_stats(payload: dict[str, object]) -> dict[str, object]:
    actions = _normalize_trace_actions(payload)
    counts = Counter(str(row.get("action_type", "")).strip() for row in actions if str(row.get("action_type", "")).strip())
    return {
        "action_count": len(actions),
        "unique_action_type_count": len(counts),
        "top_action_types": [{"action_type": label, "count": count} for label, count in counts.most_common(10)],
    }


def _convert_to_phase7_compatible_artifact(payload: dict[str, object]) -> dict[str, object]:
    actions = _normalize_trace_actions(payload)
    if isinstance(payload.get("decision_trace"), list):
        return {
            "trace": {
                "actions": actions,
                "winner_id": payload.get("winner_id"),
                "final_turn_number": payload.get("turn_number"),
                "final_phase": payload.get("phase"),
                "total_actions": payload.get("total_actions", len(actions)),
                "setup": {
                    "mode": "ai_match_review_trace",
                    "stop_reason": payload.get("stop_reason"),
                },
            }
        }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Phase 22 benchmark dataset from gameplay trace artifacts.")
    parser.add_argument("--input", nargs="+", type=Path, required=True, help="Trace artifact JSON paths.")
    parser.add_argument("--output", type=Path, required=True, help="Output Phase 7 dataset JSON path.")
    parser.add_argument("--summary-output", type=Path, default=None, help="Optional benchmark summary JSON path.")
    parser.add_argument("--validation-ratio", type=float, default=0.2, help="Validation split ratio.")
    parser.add_argument("--min-actions", type=int, default=2, help="Minimum action count for a trace to be included.")
    parser.add_argument("--min-unique-action-types", type=int, default=2, help="Minimum unique action types for a trace to be included.")
    args = parser.parse_args()

    artifacts: list[dict[str, object]] = []
    source_names: list[str] = []
    included: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for path in args.input:
        payload = _load_json(path)
        stats = _trace_stats(payload)
        row = {
            "path": str(path),
            **stats,
        }
        if int(stats["action_count"]) < int(args.min_actions) or int(stats["unique_action_type_count"]) < int(args.min_unique_action_types):
            skipped.append(row)
            continue
        artifacts.append(_convert_to_phase7_compatible_artifact(payload))
        source_names.append(str(path))
        included.append(row)

    if not artifacts:
        raise ValueError(
            "no eligible trace artifacts found; "
            f"min_actions={args.min_actions} min_unique_action_types={args.min_unique_action_types}"
        )

    dataset = build_phase7_dataset(
        artifacts,
        source_names=source_names,
        validation_ratio=float(args.validation_ratio),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")

    if args.summary_output is not None:
        summary = {
            "schema_version": "phase22.benchmark_dataset_summary.v1",
            "input_count": len(args.input),
            "included_count": len(included),
            "skipped_count": len(skipped),
            "included_traces": included,
            "skipped_traces": skipped,
            "dataset_example_count": int(dataset.get("example_count", 0) or 0),
            "dataset_split_counts": dict(dataset.get("split_counts", {})) if isinstance(dataset.get("split_counts"), dict) else {},
        }
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"wrote: {args.summary_output}")


if __name__ == "__main__":
    main()
