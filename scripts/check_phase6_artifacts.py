from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import check_phase6_artifact_consistency


def _load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Check integrity/consistency of Phase 6 artifacts.")
    parser.add_argument("--trace", type=Path, required=True, help="play trace JSON path")
    parser.add_argument("--summary", type=Path, required=True, help="play summary JSON path")
    parser.add_argument("--play-result", type=Path, required=True, help="play result JSON path")
    parser.add_argument("--replay", type=Path, required=True, help="replay result JSON path")
    parser.add_argument("--replay-result", type=Path, required=True, help="replay expectation result JSON path")
    parser.add_argument("--manifest-status", type=str, default="pass", help="expected manifest status label")
    parser.add_argument(
        "--strict-summary-trace-hash",
        action="store_true",
        help="Enforce summary.trace_hash equality with play trace hash when present.",
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase6_integrity_result.json"), help="result JSON path")
    args = parser.parse_args()

    trace = _load(args.trace)
    summary = _load(args.summary)
    play_result = _load(args.play_result)
    replay = _load(args.replay)
    replay_result = _load(args.replay_result)

    failures, checks = check_phase6_artifact_consistency(
        play_trace=trace,
        summary=summary,
        play_result=play_result,
        replay=replay,
        replay_result=replay_result,
        strict_summary_trace_hash=bool(args.strict_summary_trace_hash),
    )
    if str(args.manifest_status).strip().lower() != "pass":
        failures.append(f"unexpected_manifest_status {args.manifest_status}")

    payload = {
        "ok": len(failures) == 0,
        "failures": failures,
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")
    if failures:
        for f in failures:
            print(f"integrity_failed:{f}")
        sys.exit(8)


if __name__ == "__main__":
    main()
