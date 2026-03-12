from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import summarize_phase7_dataset_by_mode


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Phase 9 evaluation report separating self-play and external data.")
    parser.add_argument("--dataset", type=Path, required=True, help="Mixed Phase 7 dataset JSON path.")
    parser.add_argument("--phase7-eval", type=Path, default=None, help="Optional Phase 7 evaluation JSON path.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase9_eval_report.json"), help="Output report path.")
    args = parser.parse_args()

    dataset = _load_json(args.dataset)
    summary = summarize_phase7_dataset_by_mode(dataset)
    payload: dict[str, object] = {
        "dataset_mode_summary": summary,
    }
    if args.phase7_eval is not None and args.phase7_eval.exists():
        payload["phase7_eval"] = _load_json(args.phase7_eval)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
