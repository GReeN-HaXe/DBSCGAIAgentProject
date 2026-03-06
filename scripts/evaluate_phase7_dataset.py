from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import PROFILE_PRESETS


def _load_dataset(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected dataset JSON object in {path}")
    return data


def _score_action_type(profile: str, action_type: str) -> float:
    weights = PROFILE_PRESETS.get(profile, PROFILE_PRESETS["balanced"])
    mapping = {
        "pass_counter_window": weights.pass_counter,
        "end_charge": weights.end_charge,
        "resolve_battle": weights.resolve_battle,
        "end_offense_step": weights.end_step,
        "end_defense_step": weights.end_step,
        "play_card_from_hand": weights.play_base,
        "declare_attack": weights.attack_base,
        "activate_main_skill": weights.activate_skill,
        "activate_battle_skill": weights.activate_skill,
        "combo_from_hand": weights.combo,
        "end_turn": weights.end_turn,
    }
    return float(mapping.get(action_type, 0.0))


def _predict_action_type(example: dict[str, object], profile: str) -> str:
    phase = str(example.get("phase", ""))
    state = example.get("state_features", {})
    if not isinstance(state, dict):
        state = {}
    candidates = ["play_card_from_hand", "declare_attack", "activate_main_skill", "end_turn"]
    if phase == "charge":
        candidates = ["charge_from_hand", "end_charge"]
    elif phase == "end":
        candidates = ["end_turn"]
    elif state.get("battle_step") is not None:
        candidates = ["combo_from_hand", "activate_battle_skill", "end_offense_step", "end_defense_step", "resolve_battle"]
    return max(candidates, key=lambda action_type: (_score_action_type(profile, action_type), action_type))


def _action_family(action_type: str) -> str:
    if action_type in {"play_card_from_hand", "charge_from_hand"}:
        return "resource_development"
    if action_type in {"declare_attack", "combo_from_hand", "resolve_battle"}:
        return "combat"
    if action_type in {"activate_main_skill", "activate_battle_skill"}:
        return "skill"
    if action_type in {"declare_counter_from_hand", "pass_counter_window"}:
        return "counter"
    if action_type in {"end_charge", "end_offense_step", "end_defense_step", "end_turn"}:
        return "progression"
    return "other"


def evaluate_phase7_dataset(dataset: dict[str, object], *, profile: str, split: str) -> dict[str, object]:
    examples = dataset.get("examples", [])
    if not isinstance(examples, list):
        examples = []
    filtered = [row for row in examples if isinstance(row, dict) and (split == "all" or row.get("split") == split)]
    total = len(filtered)
    matches = 0
    by_action: dict[str, dict[str, int | float | str]] = {}
    family_matches = 0
    by_family: dict[str, dict[str, int | float | str]] = {}
    for row in filtered:
        actual = str(row.get("action_type", "unknown"))
        predicted = _predict_action_type(row, profile)
        bucket = by_action.setdefault(actual, {"count": 0, "matched": 0})
        bucket["count"] = int(bucket["count"]) + 1
        if predicted == actual:
            matches += 1
            bucket["matched"] = int(bucket["matched"]) + 1
        actual_family = str(row.get("action_family", _action_family(actual)))
        predicted_family = _action_family(predicted)
        family_bucket = by_family.setdefault(actual_family, {"count": 0, "matched": 0})
        family_bucket["count"] = int(family_bucket["count"]) + 1
        if predicted_family == actual_family:
            family_matches += 1
            family_bucket["matched"] = int(family_bucket["matched"]) + 1
    for actual, bucket in by_action.items():
        count = int(bucket["count"])
        bucket["accuracy"] = 0.0 if count == 0 else float(bucket["matched"]) / float(count)
        bucket["action_type"] = actual
    for actual_family, bucket in by_family.items():
        count = int(bucket["count"])
        bucket["accuracy"] = 0.0 if count == 0 else float(bucket["matched"]) / float(count)
        bucket["action_family"] = actual_family
    return {
        "profile": profile,
        "split": split,
        "example_count": total,
        "top1_accuracy": 0.0 if total == 0 else float(matches) / float(total),
        "family_accuracy": 0.0 if total == 0 else float(family_matches) / float(total),
        "by_action_type": [by_action[key] for key in sorted(by_action.keys())],
        "by_action_family": [by_family[key] for key in sorted(by_family.keys())],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate heuristic action-type agreement on a Phase 7 dataset.")
    parser.add_argument("--dataset", type=Path, required=True, help="Phase 7 dataset JSON path.")
    parser.add_argument("--profile", type=str, default="balanced", help="Heuristic profile to evaluate.")
    parser.add_argument("--split", choices=["train", "validation", "all"], default="validation", help="Dataset split to score.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase7_dataset_eval.json"), help="Evaluation output path.")
    args = parser.parse_args()

    dataset = _load_dataset(args.dataset)
    payload = evaluate_phase7_dataset(dataset, profile=str(args.profile), split=str(args.split))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
