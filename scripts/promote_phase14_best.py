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
    parser = argparse.ArgumentParser(description="Promote a Phase 14 sweep best result into a canonical best-config artifact.")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase14_best_config.json"))
    args = parser.parse_args()

    summary = _load_json(args.summary)
    best = summary.get("best", {})
    if not isinstance(best, dict) or not best:
        raise ValueError("sweep summary does not contain a best config")

    payload = {
        "schema_version": "phase14.best_config.v1",
        "source_summary": str(args.summary.resolve()),
        "profile": str(summary.get("profile", "")),
        "best": best,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
