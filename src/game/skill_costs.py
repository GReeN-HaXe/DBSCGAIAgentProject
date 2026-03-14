from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from src.game.state import CardInstance, PlayerState


@dataclass(frozen=True)
class SkillCostStep:
    kind: str
    amount: int = 1
    params: dict[str, int | str | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillCostSpec:
    steps: tuple[SkillCostStep, ...]

    @staticmethod
    def from_data(data: object) -> "SkillCostSpec":
        if isinstance(data, SkillCostSpec):
            return data
        if not isinstance(data, list):
            raise ValueError("Skill cost spec must be a list of step objects.")
        steps: list[SkillCostStep] = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("Each skill cost step must be an object.")
            kind = str(item.get("kind", "")).strip()
            amount = int(item.get("amount", 1))
            if not kind:
                raise ValueError("Skill cost step requires 'kind'.")
            if amount < 0:
                raise ValueError("Skill cost step amount must be non-negative.")
            params: dict[str, int | str | bool] = {}
            for key, value in item.items():
                if key in {"kind", "amount"}:
                    continue
                if not isinstance(key, str):
                    raise ValueError("Skill cost step keys must be strings.")
                if not isinstance(value, (int, str, bool)):
                    raise ValueError("Skill cost step values must be int/str/bool.")
                params[key] = value
            steps.append(SkillCostStep(kind=kind, amount=amount, params=params))
        return SkillCostSpec(steps=tuple(steps))


class SkillCostDsl:
    @staticmethod
    def _parse_param_set(raw: object) -> set[str]:
        text = str(raw or "").strip().lower()
        if not text:
            return set()
        normalized = text.replace("|", ",").replace("/", ",")
        return {part.strip() for part in normalized.split(",") if part.strip()}

    @staticmethod
    def _card_matches_filters(card: CardInstance, step: SkillCostStep) -> bool:
        allowed_colors = SkillCostDsl._parse_param_set(step.params.get("allowed_colors"))
        required_traits = SkillCostDsl._parse_param_set(step.params.get("required_traits"))
        required_characters = SkillCostDsl._parse_param_set(step.params.get("required_characters"))
        required_name_contains = str(step.params.get("required_name_contains", "")).strip().upper()
        if allowed_colors:
            card_colors = SkillCostDsl._parse_param_set(card.color)
            if card_colors.isdisjoint(allowed_colors):
                return False
        if required_traits:
            text = str(card.skill_text_raw or "").lower()
            if not any(trait in text for trait in required_traits):
                return False
        if required_characters:
            text = str(card.skill_text_raw or "").lower()
            if not any(char in text for char in required_characters):
                return False
        if required_name_contains and required_name_contains not in str(getattr(card, "card_name", "") or "").upper():
            return False
        return True

    @staticmethod
    def _owner_battle_candidates(player: PlayerState, source_card: CardInstance, step: SkillCostStep) -> list[CardInstance]:
        allow_self = bool(step.params.get("allow_self", False))
        return [
            c
            for c in player.battle_area
            if (allow_self or c.instance_id != source_card.instance_id) and not c.hidden_mode and SkillCostDsl._card_matches_filters(c, step)
        ]

    @staticmethod
    def _owner_battle_or_energy_candidates(player: PlayerState, source_card: CardInstance, step: SkillCostStep) -> list[CardInstance]:
        allow_self = bool(step.params.get("allow_self", False))
        battle = [
            c
            for c in player.battle_area
            if (allow_self or c.instance_id != source_card.instance_id) and not c.hidden_mode and SkillCostDsl._card_matches_filters(c, step)
        ]
        energy = [c for c in player.energy if not c.hidden_mode and SkillCostDsl._card_matches_filters(c, step)]
        return [*battle, *energy]

    @staticmethod
    def _owner_hidden_mode_battle_candidates(player: PlayerState, source_card: CardInstance, step: SkillCostStep) -> list[CardInstance]:
        allow_self = bool(step.params.get("allow_self", False))
        return [
            c
            for c in player.battle_area
            if (allow_self or c.instance_id != source_card.instance_id) and c.hidden_mode and SkillCostDsl._card_matches_filters(c, step)
        ]

    @staticmethod
    def _in_battle_or_unison(player: PlayerState, source_card: CardInstance) -> bool:
        in_battle = any(c.instance_id == source_card.instance_id for c in player.battle_area)
        in_unison = any(c.instance_id == source_card.instance_id for c in player.unison_area)
        return in_battle or in_unison

    @staticmethod
    def _remove_source_from_battle_or_unison(
        player: PlayerState,
        source_card: CardInstance,
        *,
        destination: str,
    ) -> bool:
        for i, card in enumerate(player.battle_area):
            if card.instance_id != source_card.instance_id:
                continue
            removed = player.battle_area.pop(i)
            if destination == "drop":
                player.drop.append(removed)
            elif destination == "warp":
                player.warp.append(removed)
            elif destination == "removed":
                player.removed_from_game.append(removed)
            else:
                raise ValueError(f"Unknown destination: {destination}")
            return True
        for i, card in enumerate(player.unison_area):
            if card.instance_id != source_card.instance_id:
                continue
            removed = player.unison_area.pop(i)
            if destination == "drop":
                player.drop.append(removed)
            elif destination == "warp":
                player.warp.append(removed)
            elif destination == "removed":
                player.removed_from_game.append(removed)
            else:
                raise ValueError(f"Unknown destination: {destination}")
            return True
        return False

    @staticmethod
    def can_pay(player: PlayerState, source_card: CardInstance, spec: SkillCostSpec) -> bool:
        for step in spec.steps:
            if step.kind == "discard_hand":
                if len(player.hand) < step.amount:
                    return False
                continue
            if step.kind == "add_markers":
                continue
            if step.kind == "remove_markers":
                if source_card.markers < step.amount:
                    return False
                continue
            if step.kind == "send_other_battle_to_drop":
                available = [c for c in player.battle_area if c.instance_id != source_card.instance_id]
                if len(available) < step.amount:
                    return False
                continue
            if step.kind == "send_self_to_drop":
                if step.amount != 1:
                    return False
                if not SkillCostDsl._in_battle_or_unison(player, source_card):
                    return False
                continue
            if step.kind == "send_other_battle_to_warp":
                available = [c for c in player.battle_area if c.instance_id != source_card.instance_id]
                if len(available) < step.amount:
                    return False
                continue
            if step.kind == "send_other_battle_to_removed":
                available = [c for c in player.battle_area if c.instance_id != source_card.instance_id]
                if len(available) < step.amount:
                    return False
                continue
            if step.kind == "send_self_to_warp":
                if step.amount != 1:
                    return False
                if not SkillCostDsl._in_battle_or_unison(player, source_card):
                    return False
                continue
            if step.kind == "send_self_to_removed":
                if step.amount != 1:
                    return False
                if not SkillCostDsl._in_battle_or_unison(player, source_card):
                    return False
                continue
            if step.kind == "switch_owner_battle_to_hidden":
                available = SkillCostDsl._owner_battle_candidates(player, source_card, step)
                if len(available) < step.amount:
                    return False
                continue
            if step.kind == "switch_owner_battle_or_energy_to_hidden":
                available = SkillCostDsl._owner_battle_or_energy_candidates(player, source_card, step)
                if len(available) < step.amount:
                    return False
                continue
            if step.kind == "send_owner_hidden_mode_battle_to_drop":
                available = SkillCostDsl._owner_hidden_mode_battle_candidates(player, source_card, step)
                if len(available) < step.amount:
                    return False
                continue
            raise ValueError(f"Unknown skill cost kind: {step.kind}")
        return True

    @staticmethod
    def pay(player: PlayerState, source_card: CardInstance, spec: SkillCostSpec) -> dict[str, int | str | None]:
        metadata: dict[str, int | str | None] = {}
        for step in spec.steps:
            if step.kind == "discard_hand":
                for _ in range(step.amount):
                    player.drop.append(player.hand.pop(0))
                continue
            if step.kind == "add_markers":
                source_card.markers += step.amount
                continue
            if step.kind == "remove_markers":
                source_card.markers -= step.amount
                continue
            if step.kind == "send_other_battle_to_drop":
                moved = 0
                i = 0
                while i < len(player.battle_area) and moved < step.amount:
                    card = player.battle_area[i]
                    if card.instance_id == source_card.instance_id:
                        i += 1
                        continue
                    player.drop.append(player.battle_area.pop(i))
                    moved += 1
                continue
            if step.kind == "send_self_to_drop":
                if not SkillCostDsl._remove_source_from_battle_or_unison(player, source_card, destination="drop"):
                    raise ValueError("Source card not found in battle/unison area for send_self_to_drop.")
                continue
            if step.kind == "send_other_battle_to_warp":
                moved = 0
                i = 0
                while i < len(player.battle_area) and moved < step.amount:
                    card = player.battle_area[i]
                    if card.instance_id == source_card.instance_id:
                        i += 1
                        continue
                    player.warp.append(player.battle_area.pop(i))
                    moved += 1
                continue
            if step.kind == "send_other_battle_to_removed":
                moved = 0
                i = 0
                while i < len(player.battle_area) and moved < step.amount:
                    card = player.battle_area[i]
                    if card.instance_id == source_card.instance_id:
                        i += 1
                        continue
                    player.removed_from_game.append(player.battle_area.pop(i))
                    moved += 1
                continue
            if step.kind == "send_self_to_warp":
                if not SkillCostDsl._remove_source_from_battle_or_unison(player, source_card, destination="warp"):
                    raise ValueError("Source card not found in battle/unison area for send_self_to_warp.")
                continue
            if step.kind == "send_self_to_removed":
                if not SkillCostDsl._remove_source_from_battle_or_unison(player, source_card, destination="removed"):
                    raise ValueError("Source card not found in battle/unison area for send_self_to_removed.")
                continue
            if step.kind == "switch_owner_battle_to_hidden":
                candidates = SkillCostDsl._owner_battle_candidates(player, source_card, step)
                moved = 0
                for card in candidates[: step.amount]:
                    card.hidden_mode = True
                    moved += 1
                    if moved == 1:
                        metadata["cost_target_instance_id"] = int(card.instance_id)
                        metadata["cost_target_card_id"] = int(card.card_id)
                        metadata["cost_target_zone"] = "battle"
                continue
            if step.kind == "switch_owner_battle_or_energy_to_hidden":
                candidates = SkillCostDsl._owner_battle_or_energy_candidates(player, source_card, step)
                moved = 0
                battle_ids = {c.instance_id for c in player.battle_area}
                for card in candidates[: step.amount]:
                    card.hidden_mode = True
                    moved += 1
                    if moved == 1:
                        metadata["cost_target_instance_id"] = int(card.instance_id)
                        metadata["cost_target_card_id"] = int(card.card_id)
                        metadata["cost_target_zone"] = "battle" if card.instance_id in battle_ids else "energy"
                continue
            if step.kind == "send_owner_hidden_mode_battle_to_drop":
                candidates = SkillCostDsl._owner_hidden_mode_battle_candidates(player, source_card, step)
                moved = 0
                candidate_ids = {card.instance_id for card in candidates[: step.amount]}
                i = 0
                while i < len(player.battle_area) and moved < step.amount:
                    card = player.battle_area[i]
                    if card.instance_id not in candidate_ids:
                        i += 1
                        continue
                    removed = player.battle_area.pop(i)
                    player.drop.append(removed)
                    moved += 1
                    if moved == 1:
                        metadata["cost_target_instance_id"] = int(removed.instance_id)
                        metadata["cost_target_card_id"] = int(removed.card_id)
                        metadata["cost_target_zone"] = "battle"
                continue
            raise ValueError(f"Unknown skill cost kind: {step.kind}")
        return metadata


def normalize_skill_cost_rules(
    raw_rules: dict[int, dict[str, object]] | None,
) -> dict[int, dict[str, SkillCostSpec]]:
    if not raw_rules:
        return {}
    normalized: dict[int, dict[str, SkillCostSpec]] = {}
    for card_id, context_map in raw_rules.items():
        if not isinstance(context_map, dict):
            raise ValueError("Each skill cost rule entry must be a context->spec mapping.")
        per_context: dict[str, SkillCostSpec] = {}
        for context, raw_spec in context_map.items():
            if not isinstance(context, str):
                raise ValueError("Skill cost context keys must be strings.")
            per_context[context] = SkillCostSpec.from_data(raw_spec)
        normalized[int(card_id)] = per_context
    return normalized


def serialize_skill_cost_rules(
    rules: dict[int, dict[str, SkillCostSpec | object]],
) -> dict[str, dict[str, list[dict[str, int | str | bool]]]]:
    payload: dict[str, dict[str, list[dict[str, int | str | bool]]]] = {}
    for card_id, context_map in rules.items():
        serialized_contexts: dict[str, list[dict[str, int | str | bool]]] = {}
        for context, raw_spec in context_map.items():
            spec = SkillCostSpec.from_data(raw_spec)
            serialized_contexts[context] = [
                {"kind": step.kind, "amount": step.amount, **dict(step.params)}
                for step in spec.steps
            ]
        payload[str(int(card_id))] = serialized_contexts
    return payload


def save_skill_cost_rules_json(
    path: str | Path,
    rules: dict[int, dict[str, SkillCostSpec | object]],
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(serialize_skill_cost_rules(rules), indent=2, sort_keys=True), encoding="utf-8")


def load_skill_cost_rules_json(path: str | Path) -> dict[int, dict[str, SkillCostSpec]]:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Skill cost catalog JSON must be an object keyed by card id.")
    mapped: dict[int, dict[str, object]] = {}
    for key, value in data.items():
        mapped[int(key)] = value
    return normalize_skill_cost_rules(mapped)
