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
    parser = argparse.ArgumentParser(description="Render a Phase 13 closeout markdown report.")
    parser.add_argument("--manifest", type=Path, required=True, help="Phase 13 manifest JSON path.")
    parser.add_argument("--history-summary", type=Path, default=None, help="Optional Phase 13 history summary JSON path.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase13_closeout_report.md"), help="Markdown output path.")
    args = parser.parse_args()

    manifest = _load_json(args.manifest)
    history = _load_json(args.history_summary)
    metrics = manifest.get("metrics", {}) if isinstance(manifest.get("metrics"), dict) else {}
    artifacts = manifest.get("artifacts", {}) if isinstance(manifest.get("artifacts"), dict) else {}

    lines = ["# Phase 13 Closeout", ""]
    lines.append("## Real Crop Pipeline")
    lines.append(f"- status: `{manifest.get('status', 'unknown')}`")
    lines.append(f"- run_name: `{manifest.get('run_name', '')}`")
    lines.append(f"- real_crop_dataset: `{artifacts.get('real_crop_dataset', '')}`")
    lines.append(f"- reviewed_crop_dataset: `{artifacts.get('reviewed_crop_dataset', '')}`")
    lines.append(f"- model: `{artifacts.get('model', '')}`")
    lines.append(f"- trained_frame_exact_match_rate: `{metrics.get('trained_frame_exact_match_rate', 0.0)}`")
    lines.append(f"- baseline_frame_exact_match_rate: `{metrics.get('baseline_frame_exact_match_rate', 0.0)}`")
    lines.append(f"- frame_exact_match_lift: `{metrics.get('frame_exact_match_lift', 0.0)}`")
    lines.append(f"- promoted: `{metrics.get('promoted', False)}`")
    if history:
        lines.append("")
        lines.append("## Experiment History")
        lines.append(f"- total_runs: `{history.get('total_runs', 0)}`")
        lines.append(f"- promoted_rate: `{history.get('promoted_rate', 0.0)}`")
        lines.append(f"- best_run_name: `{history.get('best_run_name', '')}`")
        lines.append(f"- best_frame_exact_match_rate: `{history.get('best_frame_exact_match_rate', 0.0)}`")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
