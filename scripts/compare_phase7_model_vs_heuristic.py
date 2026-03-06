from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.compare_phase7_profiles import compare_profiles
from scripts.evaluate_phase7_dataset import evaluate_phase7_dataset
from src.agent import evaluate_frequency_policy_model


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare a trained Phase 7 model against heuristic profiles.")
    parser.add_argument("--dataset", type=Path, required=True, help="Phase 7 dataset JSON path.")
    parser.add_argument("--model", type=Path, required=True, help="Trained model JSON path.")
    parser.add_argument("--profiles", nargs="+", default=["balanced", "aggressive", "control"], help="Heuristic profiles to compare.")
    parser.add_argument("--split", choices=["train", "validation", "all"], default="validation", help="Dataset split to score.")
    parser.add_argument("--min-top1-lift", type=float, default=0.0, help="Minimum top1_accuracy lift required over best heuristic.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase7_model_vs_heuristic.json"), help="Comparison output path.")
    args = parser.parse_args()

    dataset = _load_json(args.dataset)
    model = _load_json(args.model)
    heuristic_payload = compare_profiles(dataset, profiles=[str(p) for p in args.profiles], split=str(args.split))
    model_eval = evaluate_frequency_policy_model(dataset, model, split=str(args.split))
    model_result = {
        "profile": str(model_eval.get("model_name", "frequency_policy")),
        "target_field": str(model_eval.get("target_field", "action_type")),
        "example_count": int(model_eval.get("example_count", 0) or 0),
        "top1_accuracy": float(model_eval.get("top1_accuracy", 0.0) or 0.0),
        "family_accuracy": float(model_eval.get("top1_accuracy", 0.0) or 0.0),
        "model_name": str(model_eval.get("model_name", "frequency_policy")),
    }
    results = [model_result, *[dict(item) for item in heuristic_payload.get("results", []) if isinstance(item, dict)]]
    ranking = sorted(
        (
            {
                "profile": str(item.get("profile", item.get("model_name", ""))),
                "target_field": str(item.get("target_field", "action_type")),
                "top1_accuracy": float(item.get("top1_accuracy", 0.0) or 0.0),
                "family_accuracy": float(item.get("family_accuracy", 0.0) or 0.0),
                "example_count": int(item.get("example_count", 0) or 0),
            }
            for item in results
        ),
        key=lambda row: (-row["top1_accuracy"], -row["family_accuracy"], row["profile"]),
    )
    best_heuristic = max(
        (
            item
            for item in results
            if str(item.get("profile", "")) != str(model_result.get("profile", ""))
        ),
        key=lambda item: (float(item.get("top1_accuracy", 0.0) or 0.0), float(item.get("family_accuracy", 0.0) or 0.0)),
        default=None,
    )
    model_top1 = float(model_result.get("top1_accuracy", 0.0) or 0.0)
    best_heuristic_top1 = 0.0 if best_heuristic is None else float(best_heuristic.get("top1_accuracy", 0.0) or 0.0)
    promotion = {
        "promoted": model_top1 >= (best_heuristic_top1 + float(args.min_top1_lift)),
        "min_top1_lift": float(args.min_top1_lift),
        "model_top1_accuracy": model_top1,
        "best_heuristic_profile": "" if best_heuristic is None else str(best_heuristic.get("profile", "")),
        "best_heuristic_top1_accuracy": best_heuristic_top1,
        "top1_lift_vs_best_heuristic": model_top1 - best_heuristic_top1,
    }
    payload = {
        "split": str(args.split),
        "profiles": [str(p) for p in args.profiles],
        "model_name": str(model_eval.get("model_name", "frequency_policy")),
        "promotion": promotion,
        "ranking": [{**row, "rank": idx + 1} for idx, row in enumerate(ranking)],
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
