from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Markdown report for Phase 8 baseline vs identity-context comparison.")
    parser.add_argument("--input", type=Path, required=True, help="Phase 8 identity context comparison JSON path.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase8_identity_context_report.md"), help="Markdown output path.")
    args = parser.parse_args()

    payload = _load_json(args.input)
    coverage = payload.get("dataset_identity_coverage", {})
    baseline = payload.get("baseline", {})
    identity = payload.get("identity", {})
    comparison = payload.get("comparison", {})

    lines = [
        "# Phase 8 Identity Context Compare",
        "",
        "## Dataset",
        f"- dataset_path: `{payload.get('dataset_path', '')}`",
        f"- example_count: `{coverage.get('example_count', 0)}`",
        f"- identity_resolved_example_count: `{coverage.get('identity_resolved_example_count', 0)}`",
        f"- identity_resolved_example_rate: `{coverage.get('identity_resolved_example_rate', 0.0)}`",
        "",
        "## Baseline",
        f"- top1_accuracy: `{baseline.get('top1_accuracy', 0.0)}`",
        "",
        "## Identity",
        f"- top1_accuracy: `{identity.get('top1_accuracy', 0.0)}`",
        "",
        "## Comparison",
        f"- top1_lift_identity_minus_baseline: `{comparison.get('top1_lift_identity_minus_baseline', 0.0)}`",
        f"- dataset_has_identity_signal: `{comparison.get('dataset_has_identity_signal', False)}`",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
