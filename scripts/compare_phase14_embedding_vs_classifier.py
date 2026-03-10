from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import compare_phase14_embedding_vs_classifier_retrieval


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Phase 14 classifier retrieval vs embedding retrieval.")
    parser.add_argument("--classifier-retrieval", type=Path, required=True)
    parser.add_argument("--embedding-retrieval", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase14_embedding_compare.json"))
    args = parser.parse_args()

    payload = compare_phase14_embedding_vs_classifier_retrieval(
        classifier_retrieval=_load_json(args.classifier_retrieval),
        embedding_retrieval=_load_json(args.embedding_retrieval),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
