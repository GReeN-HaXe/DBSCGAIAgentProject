from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.trace_summary import build_human_review_trace_payload, build_human_training_trace_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize raw human-vs-AI trace into review/training formats.")
    parser.add_argument("--input", type=Path, required=True, help="Raw human trace JSON path.")
    parser.add_argument("--review-output", type=Path, required=True, help="Filtered review JSON output path.")
    parser.add_argument("--training-output", type=Path, required=True, help="Training JSONL output path.")
    parser.add_argument("--include-bookkeeping", action="store_true", help="Keep pass/end-step/resolve bookkeeping actions.")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    review_payload = build_human_review_trace_payload(payload, include_bookkeeping=bool(args.include_bookkeeping))
    training_rows = build_human_training_trace_rows(payload, include_bookkeeping=bool(args.include_bookkeeping))

    args.review_output.parent.mkdir(parents=True, exist_ok=True)
    args.review_output.write_text(json.dumps(review_payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.review_output}")

    args.training_output.parent.mkdir(parents=True, exist_ok=True)
    with args.training_output.open("w", encoding="utf-8") as fh:
        for row in training_rows:
            fh.write(json.dumps(row) + "\n")
    print(f"wrote: {args.training_output}")


if __name__ == "__main__":
    main()
