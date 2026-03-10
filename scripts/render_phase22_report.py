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
    parser = argparse.ArgumentParser(description="Render a compact Markdown report for a Phase 22 compare or sweep artifact.")
    parser.add_argument("--compare", type=Path, default=None)
    parser.add_argument("--sweep-summary", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    lines = ["# Phase 22 Report", ""]
    if args.compare is not None:
        compare = _load_json(args.compare)
        lines.extend(
            [
                "## Comparison",
                "",
                f"- target_field: `{compare.get('target_field', '')}`",
                f"- phase22_top1_accuracy: `{compare.get('phase22_top1_accuracy', 0.0)}`",
                f"- baseline_top1_accuracy: `{compare.get('baseline_top1_accuracy', 0.0)}`",
                f"- top1_lift: `{compare.get('top1_lift', 0.0)}`",
                f"- phase22_wins: `{compare.get('phase22_wins', False)}`",
                "",
            ]
        )
    if args.sweep_summary is not None:
        summary = _load_json(args.sweep_summary)
        best = summary.get("best", {})
        lines.extend(
            [
                "## Sweep",
                "",
                f"- profile: `{summary.get('profile', '')}`",
                f"- target_field: `{summary.get('target_field', '')}`",
                f"- config_count: `{summary.get('config_count', 0)}`",
                f"- best_config: `{best.get('config_name', '')}`",
                f"- best_top1_lift: `{best.get('top1_lift', 0.0)}`",
                f"- best_top1_accuracy: `{best.get('top1_accuracy', 0.0)}`",
                "",
            ]
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
