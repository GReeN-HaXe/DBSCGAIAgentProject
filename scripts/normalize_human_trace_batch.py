from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.trace_summary import build_human_review_trace_payload, build_human_training_trace_rows


def _is_raw_trace_candidate(path: Path) -> bool:
    name = path.name.lower()
    if not name.endswith(".json"):
        return False
    if "_review" in name or "_training" in name or "_summary" in name:
        return False
    return True


def _derive_outputs(path: Path, output_dir: Path | None) -> tuple[Path, Path]:
    base_dir = output_dir if output_dir is not None else path.parent
    stem = path.stem
    return (
        base_dir / f"{stem}_review.json",
        base_dir / f"{stem}_training.jsonl",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-normalize raw human-vs-AI traces into review/training artifacts.")
    parser.add_argument(
        "--input-glob",
        type=str,
        default="artifacts/phase22_source/human_vs_ai_trace_*.json",
        help="Glob pattern for raw human trace JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory to write all normalized outputs. Defaults to each source file directory.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("artifacts/phase22_source/human_trace_normalization_summary.json"),
        help="Summary JSON path.",
    )
    parser.add_argument(
        "--include-bookkeeping",
        action="store_true",
        help="Keep pass/end-step/resolve bookkeeping actions in normalized outputs.",
    )
    args = parser.parse_args()

    candidates = [Path(match) for match in sorted(glob.glob(args.input_glob)) if _is_raw_trace_candidate(Path(match))]
    outputs: list[dict[str, object]] = []
    for source_path in candidates:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        review_payload = build_human_review_trace_payload(payload, include_bookkeeping=bool(args.include_bookkeeping))
        training_rows = build_human_training_trace_rows(payload, include_bookkeeping=bool(args.include_bookkeeping))
        review_output, training_output = _derive_outputs(source_path, args.output_dir)
        review_output.parent.mkdir(parents=True, exist_ok=True)
        review_output.write_text(json.dumps(review_payload, indent=2), encoding="utf-8")
        training_output.parent.mkdir(parents=True, exist_ok=True)
        with training_output.open("w", encoding="utf-8") as fh:
            for row in training_rows:
                fh.write(json.dumps(row) + "\n")
        print(f"wrote: {review_output}")
        print(f"wrote: {training_output}")
        outputs.append(
            {
                "source": str(source_path),
                "review_output": str(review_output),
                "training_output": str(training_output),
                "decision_count": int(review_payload.get("decision_count", 0)),
                "winner_id": review_payload.get("winner_id"),
                "stop_reason": review_payload.get("stop_reason"),
            }
        )

    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(
        json.dumps(
            {
                "schema_version": "human_trace_normalization_batch.v1",
                "input_glob": args.input_glob,
                "include_bookkeeping": bool(args.include_bookkeeping),
                "processed_count": len(outputs),
                "outputs": outputs,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote: {args.summary_output}")


if __name__ == "__main__":
    main()
