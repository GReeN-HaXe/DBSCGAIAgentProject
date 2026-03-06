from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_json(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Phase 9 closeout markdown report.")
    parser.add_argument("--review-batch-summary", type=Path, required=True, help="Phase 9 review-batch summary JSON path.")
    parser.add_argument("--mixed-series-summary", type=Path, required=True, help="Phase 9 mixed-series summary JSON path.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase9_closeout_report.md"), help="Markdown output path.")
    args = parser.parse_args()

    review = _load_json(args.review_batch_summary)
    mixed = _load_json(args.mixed_series_summary)
    queue_summary = review.get("queue_summary", {}) if isinstance(review.get("queue_summary"), dict) else {}
    best_run = mixed.get("best_run", {}) if isinstance(mixed.get("best_run"), dict) else {}

    lines = ["# Phase 9 Closeout", ""]
    lines.append("## Review Coverage")
    lines.append(f"- reviewed_count: `{review.get('reviewed_count', 0)}`")
    lines.append(f"- needs_review_count: `{queue_summary.get('needs_review_count', 0)}`")
    lines.append(f"- low_confidence_count: `{queue_summary.get('low_confidence_count', 0)}`")
    lines.append("")
    lines.append("## Mixed Training")
    lines.append(f"- run_count: `{mixed.get('run_count', 0)}`")
    lines.append(f"- avg_top1_delta_mixed_minus_selfplay: `{mixed.get('avg_top1_delta_mixed_minus_selfplay', 0.0)}`")
    if best_run:
        lines.append(f"- best_run_index: `{best_run.get('run_index', 0)}`")
        lines.append(f"- best_top1_delta_mixed_minus_selfplay: `{best_run.get('top1_delta_mixed_minus_selfplay', 0.0)}`")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
