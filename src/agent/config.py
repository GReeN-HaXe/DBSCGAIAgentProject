from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agent.heuristic import HeuristicPolicy, merge_action_weights


def load_policy_config(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Policy config must be a JSON object.")
    return raw


def build_heuristic_policy_from_config(path: str | Path) -> HeuristicPolicy:
    cfg = load_policy_config(path)
    profile = str(cfg.get("profile", "balanced"))
    prefer_attack = bool(cfg.get("prefer_attack", True))
    prefer_play = bool(cfg.get("prefer_play", True))
    weight_overrides_raw = cfg.get("weights", {})
    if weight_overrides_raw is None:
        weight_overrides_raw = {}
    if not isinstance(weight_overrides_raw, dict):
        raise ValueError("Policy config 'weights' must be an object when provided.")
    weight_overrides: dict[str, float] = {}
    for k, v in weight_overrides_raw.items():
        try:
            weight_overrides[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return HeuristicPolicy(
        profile=profile,
        action_weights=merge_action_weights(profile, weight_overrides),
        prefer_attack=prefer_attack,
        prefer_play=prefer_play,
    )
