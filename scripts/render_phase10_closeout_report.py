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
    parser = argparse.ArgumentParser(description="Render a Phase 10 closeout markdown report.")
    parser.add_argument("--pipeline-manifest", type=Path, required=True, help="Phase 10 pipeline manifest JSON path.")
    parser.add_argument("--history-summary", type=Path, default=None, help="Optional Phase 10 benchmark history summary JSON path.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase10_closeout_report.md"), help="Markdown output path.")
    args = parser.parse_args()

    manifest = _load_json(args.pipeline_manifest)
    history = _load_json(args.history_summary)
    benchmark = manifest.get("benchmark_summary", {}) if isinstance(manifest.get("benchmark_summary"), dict) else {}
    artifacts = manifest.get("artifacts", {}) if isinstance(manifest.get("artifacts"), dict) else {}

    lines = ["# Phase 10 Closeout", ""]
    lines.append("## Pipeline")
    lines.append(f"- status: `{manifest.get('status', 'unknown')}`")
    lines.append(f"- match_id: `{manifest.get('match_id', '')}`")
    lines.append(f"- source_name: `{manifest.get('source_name', '')}`")
    lines.append(f"- phase7_dataset: `{artifacts.get('phase7_dataset', '')}`")
    lines.append("")
    lines.append("## Benchmark")
    lines.append(f"- recognizer_name: `{benchmark.get('recognizer_name', '')}`")
    lines.append(f"- frame_count: `{benchmark.get('frame_count', 0)}`")
    lines.append(f"- object_precision: `{benchmark.get('object_precision', 0.0)}`")
    lines.append(f"- object_recall: `{benchmark.get('object_recall', 0.0)}`")
    lines.append(f"- frame_exact_match_rate: `{benchmark.get('frame_exact_match_rate', 0.0)}`")
    if history:
        lines.append("")
        lines.append("## Benchmark History")
        lines.append(f"- total_runs: `{history.get('total_runs', 0)}`")
        lines.append(f"- recent_avg_frame_exact_match_rate: `{history.get('recent_avg_frame_exact_match_rate', 0.0)}`")
        lines.append(f"- best_run_name: `{history.get('best_run_name', '')}`")
        lines.append(f"- best_frame_exact_match_rate: `{history.get('best_frame_exact_match_rate', 0.0)}`")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
