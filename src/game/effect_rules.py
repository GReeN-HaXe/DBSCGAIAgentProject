from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass(frozen=True)
class EffectRule:
    trigger: str
    handler_id: str
    handler_params: dict[str, int | str | bool] = field(default_factory=dict)
    once_per_turn: bool = False
    limit_per_turn: int | None = None
    limit_scope: str = "card_number"


def normalize_effect_rules(raw_rules: dict[int, list[dict[str, object]] | list[EffectRule]] | None) -> dict[int, tuple[EffectRule, ...]]:
    if not raw_rules:
        return {}
    normalized: dict[int, tuple[EffectRule, ...]] = {}
    for card_id, rules in raw_rules.items():
        items: list[EffectRule] = []
        for rule in rules:
            if isinstance(rule, EffectRule):
                items.append(rule)
                continue
            if not isinstance(rule, dict):
                raise ValueError("Each effect rule must be a dict or EffectRule.")
            trigger = str(rule.get("trigger", "")).strip()
            handler_id = str(rule.get("handler_id", "")).strip()
            raw_params = rule.get("handler_params", {})
            if raw_params is None:
                raw_params = {}
            if not isinstance(raw_params, dict):
                raise ValueError("handler_params must be a dict when provided.")
            handler_params: dict[str, int | str | bool] = {}
            for key, value in raw_params.items():
                if not isinstance(key, str):
                    raise ValueError("handler_params keys must be strings.")
                if not isinstance(value, (int, str, bool)):
                    raise ValueError("handler_params values must be int/str/bool.")
                handler_params[key] = value
            once_per_turn = bool(rule.get("once_per_turn", False))
            raw_limit = rule.get("limit_per_turn")
            limit_per_turn = int(raw_limit) if isinstance(raw_limit, int) else None
            limit_scope = str(rule.get("limit_scope", "card_number") or "card_number").strip() or "card_number"
            if not trigger or not handler_id:
                raise ValueError("Effect rule requires trigger and handler_id.")
            items.append(
                EffectRule(
                    trigger=trigger,
                    handler_id=handler_id,
                    handler_params=handler_params,
                    once_per_turn=once_per_turn,
                    limit_per_turn=limit_per_turn,
                    limit_scope=limit_scope,
                )
            )
        normalized[int(card_id)] = tuple(items)
    return normalized


def serialize_effect_rules(rules: dict[int, list[EffectRule] | tuple[EffectRule, ...]]) -> dict[str, list[dict[str, object]]]:
    payload: dict[str, list[dict[str, object]]] = {}
    for card_id, entries in rules.items():
        payload[str(int(card_id))] = [
            {
                "trigger": rule.trigger,
                "handler_id": rule.handler_id,
                "handler_params": dict(rule.handler_params),
                "once_per_turn": bool(rule.once_per_turn),
                "limit_per_turn": int(rule.limit_per_turn) if rule.limit_per_turn is not None else None,
                "limit_scope": str(rule.limit_scope or "card_number"),
            }
            for rule in entries
        ]
    return payload


def save_effect_rules_json(path: str | Path, rules: dict[int, list[EffectRule] | tuple[EffectRule, ...]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = serialize_effect_rules(rules)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_effect_rules_json(path: str | Path) -> dict[int, tuple[EffectRule, ...]]:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Effect catalog JSON must be an object keyed by card id.")
    mapped: dict[int, list[dict[str, object]] | list[EffectRule]] = {}
    for key, value in data.items():
        mapped[int(key)] = value  # normalized/validated below
    return normalize_effect_rules(mapped)
