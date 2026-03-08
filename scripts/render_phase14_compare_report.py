from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a markdown report comparing Phase 13 and Phase 14 identity models.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase14_compare_report.md"))
    args = parser.parse_args()

    manifest = _load_json(args.manifest)
    metrics = manifest.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    lines = [
        "# Phase 14 Compare Report",
        "",
        "## Summary",
        f"- Run: `{manifest.get('run_name', '')}`",
        f"- Target type: `{metrics.get('target_type', '')}`",
        f"- Split: `{metrics.get('split', '')}`",
        f"- Phase 14 top-1: `{metrics.get('phase14_top1_accuracy', 0.0)}`",
        f"- Phase 13 top-1: `{metrics.get('phase13_top1_accuracy', 0.0)}`",
        f"- Phase 14 top-5: `{metrics.get('phase14_top5_accuracy', 0.0)}`",
        f"- Phase 13 top-5: `{metrics.get('phase13_top5_accuracy', 0.0)}`",
        f"- Phase 14 top-10: `{metrics.get('phase14_top10_accuracy', 0.0)}`",
        f"- Phase 13 top-10: `{metrics.get('phase13_top10_accuracy', 0.0)}`",
        f"- Top-1 lift: `{metrics.get('top1_lift', 0.0)}`",
        f"- Top-5 lift: `{metrics.get('top5_lift', 0.0)}`",
        f"- Top-10 lift: `{metrics.get('top10_lift', 0.0)}`",
        f"- Phase 14 wins: `{metrics.get('phase14_wins', False)}`",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
