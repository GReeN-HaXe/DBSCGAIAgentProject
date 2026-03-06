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
    parser = argparse.ArgumentParser(description="Render a Phase 8 closeout markdown report.")
    parser.add_argument("--batch-summary", type=Path, required=True, help="Phase 8 batch summary JSON path.")
    parser.add_argument("--batch-series-summary", type=Path, default=None, help="Optional repeated batch-series summary JSON path.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase8_closeout_report.md"), help="Markdown output path.")
    args = parser.parse_args()

    batch = _load_json(args.batch_summary)
    series = _load_json(args.batch_series_summary)
    lines = ["# Phase 8 Closeout", ""]
    lines.append("## Batch Summary")
    lines.append(f"- slice_field: `{batch.get('slice_field', '')}`")
    lines.append(f"- run_count: `{batch.get('run_count', 0)}`")
    promotion = batch.get("promotion_summary", {})
    if isinstance(promotion, dict):
        lines.append(f"- promoted_run_count: `{promotion.get('promoted_run_count', 0)}`")
        best = promotion.get("best_promoted")
        if isinstance(best, dict):
            lines.append(
                f"- best_promoted: `{best.get('slice_value', '')}` top1=`{best.get('top1_accuracy', 0.0)}` model=`{best.get('model_name', '')}`"
            )
    if series:
        lines.append("")
        lines.append("## Batch Series")
        lines.append(f"- run_count: `{series.get('run_count', 0)}`")
        lines.append(f"- total_promoted_runs: `{series.get('total_promoted_runs', 0)}`")
        best_overall = series.get("best_promoted_overall")
        if isinstance(best_overall, dict):
            lines.append(
                f"- best_promoted_overall: `{best_overall.get('slice_value', '')}` top1=`{best_overall.get('top1_accuracy', 0.0)}` model=`{best_overall.get('model_name', '')}`"
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
