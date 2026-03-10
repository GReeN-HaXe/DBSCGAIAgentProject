from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.phase22_production import build_phase22_production_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote the best Phase 22 config into a production artifact bundle.")
    parser.add_argument("--best-config", type=Path, default=Path("artifacts/phase22_best_config.json"))
    parser.add_argument("--production-dir", type=Path, default=Path("artifacts/phase22_production"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase22_production/phase22_production_summary.json"))
    args = parser.parse_args()

    summary = build_phase22_production_summary(
        best_config_path=args.best_config,
        production_dir=args.production_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
