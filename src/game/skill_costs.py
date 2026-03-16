from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from src.game.state import CardInstance, PlayerState, ZDeckCard


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
    def _card_matches_filters(card: CardInstance | ZDeckCard, step: SkillCostStep) -> bool:
        allowed_colors = SkillCostDsl._parse_param_set(step.params.get("allowed_colors"))
        required_traits = SkillCostDsl._parse_param_set(step.params.get("required_traits"))
        required_characters = SkillCostDsl._parse_param_set(step.params.get("required_characters"))
        required_card_types = SkillCostDsl._parse_param_set(step.params.get("required_card_types"))
        required_name_contains = str(step.params.get("required_name_contains", "")).strip().upper()
        min_energy_cost = int(step.params.get("min_energy_cost", 0) or 0)
        requires_multicolor = bool(step.params.get("requires_multicolor", False))
        if allowed_colors:
            card_colors = SkillCostDsl._parse_param_set(card.color)
            if card_colors.isdisjoint(allowed_colors):
                return False
        if required_card_types and str(card.card_type or "").strip().lower() not in required_card_types:
            return False
        if required_traits:
            traits = {str(part).strip().lower() for part in getattr(card, "traits", ()) if str(part).strip()}
            if traits.isdisjoint(required_traits):
                return False
        if required_characters:
            characters = {str(part).strip().lower() for part in getattr(card, "characters", ()) if str(part).strip()}
            if characters.isdisjoint(required_characters):
                return False
        if required_name_contains and required_name_contains not in str(getattr(card, "card_name", "") or "").upper():
            return False
        if min_energy_cost > 0 and int(card.energy_cost or 0) < min_energy_cost:
            return False
        if requires_multicolor and len(SkillCostDsl._parse_param_set(card.color)) < 2:
            return False
        return True

    @staticmethod
    def _owner_has_matching_in_play_card(player: PlayerState, step: SkillCostStep) -> bool:
        if not bool(step.params.get("requires_owner_in_play", False)):
            return True
        lifted_step = SkillCostStep(
            kind=step.kind,
            amount=step.amount,
            params={
                "allowed_colors": step.params.get("owner_in_play_allowed_colors", ""),
                "required_traits": step.params.get("owner_in_play_required_traits", ""),
                "required_characters": step.params.get("owner_in_play_required_characters", ""),
                "required_card_types": step.params.get("owner_in_play_required_card_types", ""),
                "min_energy_cost": step.params.get("owner_in_play_min_energy_cost", 0),
                "requires_multicolor": step.params.get("owner_in_play_requires_multicolor", False),
            },
        )
        cards_in_play = [player.leader_area, *player.battle_area, *player.unison_area]
        return any(SkillCostDsl._card_matches_filters(card, lifted_step) for card in cards_in_play)

    @staticmethod
    def _owner_has_matching_battle_area_card(player: PlayerState, step: SkillCostStep) -> bool:
        if not bool(step.params.get("requires_owner_battle_area", False)):
            return True
        lifted_step = SkillCostStep(
            kind=step.kind,
            amount=step.amount,
            params={
                "allowed_colors": step.params.get("owner_battle_area_allowed_colors", ""),
                "required_traits": step.params.get("owner_battle_area_required_traits", ""),
                "required_characters": step.params.get("owner_battle_area_required_characters", ""),
                "required_card_types": step.params.get("owner_battle_area_required_card_types", ""),
                "min_energy_cost": step.params.get("owner_battle_area_min_energy_cost", 0),
                "requires_multicolor": step.params.get("owner_battle_area_requires_multicolor", False),
            },
        )
        return any(SkillCostDsl._card_matches_filters(card, lifted_step) for card in player.battle_area)

    @staticmethod
    def _owner_face_up_z_deck_matches_count(player: PlayerState, step: SkillCostStep) -> bool:
        required_count = int(step.params.get("requires_owner_face_up_z_deck_count_at_least", 0) or 0)
        if required_count <= 0:
            return True
        lifted_step = SkillCostStep(
            kind=step.kind,
            amount=step.amount,
            params={
                "allowed_colors": step.params.get("owner_face_up_z_deck_allowed_colors", ""),
                "required_traits": step.params.get("owner_face_up_z_deck_required_traits", ""),
                "required_characters": step.params.get("owner_face_up_z_deck_required_characters", ""),
                "required_card_types": step.params.get("owner_face_up_z_deck_required_card_types", ""),
            },
        )
        count = sum(1 for card in player.z_deck if card.face_up and SkillCostDsl._card_matches_filters(card, lifted_step))
        return count >= required_count

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
    def _owner_hidden_mode_active_battle_candidates(player: PlayerState, source_card: CardInstance, step: SkillCostStep) -> list[CardInstance]:
        allow_self = bool(step.params.get("allow_self", False))
        return [
            c
            for c in player.battle_area
            if (allow_self or c.instance_id != source_card.instance_id)
            and c.hidden_mode
            and not c.resting
            and SkillCostDsl._card_matches_filters(c, step)
        ]

    @staticmethod
    def _owner_drop_candidates(player: PlayerState, step: SkillCostStep) -> list[CardInstance]:
        return [c for c in player.drop if SkillCostDsl._card_matches_filters(c, step)]

    @staticmethod
    def _owner_battle_return_candidates(player: PlayerState, source_card: CardInstance, step: SkillCostStep) -> list[CardInstance]:
        allow_self = bool(step.params.get("allow_self", False))
        return [
            c
            for c in player.battle_area
            if (allow_self or c.instance_id != source_card.instance_id) and SkillCostDsl._card_matches_filters(c, step)
        ]

    @staticmethod
    def _leader_color_matches(player: PlayerState, step: SkillCostStep) -> bool:
        required = SkillCostDsl._parse_param_set(step.params.get("required_leader_colors"))
        if not required:
            return True
        leader_colors = SkillCostDsl._parse_param_set(player.leader_area.color)
        return not leader_colors.isdisjoint(required)

    @staticmethod
    def _leader_trait_matches(player: PlayerState, step: SkillCostStep) -> bool:
        required = SkillCostDsl._parse_param_set(step.params.get("required_leader_traits"))
        if not required:
            return True
        leader_traits = {str(part).strip().lower() for part in getattr(player.leader_area, "traits", ()) if str(part).strip()}
        leader_characters = {
            str(part).strip().lower() for part in getattr(player.leader_area, "characters", ()) if str(part).strip()
        }
        return not (leader_traits | leader_characters).isdisjoint(required)

    @staticmethod
    def _energy_color_count(player: PlayerState) -> int:
        colors: set[str] = set()
        for energy in player.energy:
            colors.update(SkillCostDsl._parse_param_set(energy.color))
        return len(colors)

    @staticmethod
    def _has_multicolor_energy(player: PlayerState) -> bool:
        return any(len(SkillCostDsl._parse_param_set(energy.color)) >= 2 for energy in player.energy)

    @staticmethod
    def _only_energy_colors_match(player: PlayerState, required_colors: set[str]) -> bool:
        if not required_colors:
            return True
        saw_any = False
        for energy in player.energy:
            colors = SkillCostDsl._parse_param_set(energy.color)
            if not colors:
                continue
            saw_any = True
            if not colors.issubset(required_colors):
                return False
        return saw_any

    @staticmethod
    def _all_energy_rested(player: PlayerState) -> bool:
        return bool(player.energy) and all(card.resting for card in player.energy)

    @staticmethod
    def _step_prereqs_met(player: PlayerState, step: SkillCostStep, opponent: PlayerState | None = None) -> bool:
        if not SkillCostDsl._leader_color_matches(player, step):
            return False
        if not SkillCostDsl._leader_trait_matches(player, step):
            return False
        requires_life_at_most = int(step.params.get("requires_life_at_most", 0) or 0)
        if requires_life_at_most > 0 and len(player.life) > requires_life_at_most:
            return False
        requires_energy_colors_at_least = int(step.params.get("requires_energy_colors_at_least", 0) or 0)
        if requires_energy_colors_at_least > 0 and SkillCostDsl._energy_color_count(player) < requires_energy_colors_at_least:
            return False
        if bool(step.params.get("requires_multicolor_in_energy", False)) and not SkillCostDsl._has_multicolor_energy(player):
            return False
        requires_only_energy_colors = SkillCostDsl._parse_param_set(step.params.get("requires_only_energy_colors"))
        if requires_only_energy_colors and not SkillCostDsl._only_energy_colors_match(player, requires_only_energy_colors):
            return False
        if bool(step.params.get("requires_all_energy_rested", False)) and not SkillCostDsl._all_energy_rested(player):
            return False
        if not SkillCostDsl._owner_has_matching_in_play_card(player, step):
            return False
        if not SkillCostDsl._owner_has_matching_battle_area_card(player, step):
            return False
        if not SkillCostDsl._owner_face_up_z_deck_matches_count(player, step):
            return False
        requires_z_energy_at_least = int(step.params.get("requires_z_energy_at_least", 0) or 0)
        if requires_z_energy_at_least > 0 and len(player.z_energy) < requires_z_energy_at_least:
            return False
        requires_opponent_energy_at_least = int(step.params.get("requires_opponent_energy_at_least", 0) or 0)
        if requires_opponent_energy_at_least > 0:
            if opponent is None or len(opponent.energy) < requires_opponent_energy_at_least:
                return False
        requires_sparking = int(step.params.get("requires_sparking", 0) or 0)
        if requires_sparking > 0 and len(player.drop) < requires_sparking:
            return False
        return True

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
    def can_pay(player: PlayerState, source_card: CardInstance, spec: SkillCostSpec, *, opponent: PlayerState | None = None) -> bool:
        for step in spec.steps:
            if not SkillCostDsl._step_prereqs_met(player, step, opponent):
                return False
            if step.kind == "discard_hand":
                if len(player.hand) < step.amount:
                    return False
                continue
            if step.kind == "rest_energy":
                if sum(1 for card in player.energy if not card.resting) < step.amount:
                    return False
                continue
            if step.kind == "rest_owner_leader":
                if player.leader_area.resting:
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
            if step.kind == "send_owner_drop_to_warp":
                available = SkillCostDsl._owner_drop_candidates(player, step)
                if len(available) < step.amount:
                    return False
                continue
            if step.kind == "send_owner_hand_to_warp":
                if len(player.hand) < step.amount:
                    return False
                continue
            if step.kind == "send_owner_z_energy_to_drop":
                if len(player.z_energy) < step.amount:
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
            if step.kind == "reduce_owner_battle_power_for_turn":
                available = SkillCostDsl._owner_battle_return_candidates(player, source_card, step)
                if len(available) < step.amount:
                    return False
                continue
            if step.kind == "return_owner_battle_to_hand":
                available = SkillCostDsl._owner_battle_return_candidates(player, source_card, step)
                if len(available) < step.amount:
                    return False
                continue
            if step.kind == "rest_owner_hidden_mode_battle":
                available = SkillCostDsl._owner_hidden_mode_active_battle_candidates(player, source_card, step)
                if len(available) < step.amount:
                    return False
                continue
            if step.kind == "add_life_to_hand":
                if len(player.life) < step.amount:
                    return False
                continue
            if step.kind == "send_all_owner_drop_to_warp":
                if len(player.drop) == 0:
                    return False
                continue
            raise ValueError(f"Unknown skill cost kind: {step.kind}")
        return True

    @staticmethod
    def pay(
        player: PlayerState,
        source_card: CardInstance,
        spec: SkillCostSpec,
        *,
        opponent: PlayerState | None = None,
    ) -> dict[str, int | str | None]:
        metadata: dict[str, int | str | None] = {}
        for step in spec.steps:
            if not SkillCostDsl._step_prereqs_met(player, step, opponent):
                raise ValueError(f"Skill cost prerequisites not met for: {step.kind}")
            if step.kind == "discard_hand":
                for _ in range(step.amount):
                    player.drop.append(player.hand.pop(0))
                continue
            if step.kind == "rest_energy":
                rested = 0
                for card in player.energy:
                    if card.resting:
                        continue
                    card.resting = True
                    rested += 1
                    if rested >= step.amount:
                        break
                metadata["alternate_cost_kind"] = "rest_energy"
                continue
            if step.kind == "rest_owner_leader":
                player.leader_area.resting = True
                metadata["alternate_cost_kind"] = "rest_owner_leader"
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
            if step.kind == "send_owner_drop_to_warp":
                candidate_ids = {card.instance_id for card in SkillCostDsl._owner_drop_candidates(player, step)[: step.amount]}
                moved = 0
                i = 0
                while i < len(player.drop) and moved < step.amount:
                    card = player.drop[i]
                    if card.instance_id not in candidate_ids:
                        i += 1
                        continue
                    player.warp.append(player.drop.pop(i))
                    moved += 1
                continue
            if step.kind == "send_owner_hand_to_warp":
                for _ in range(min(step.amount, len(player.hand))):
                    player.warp.append(player.hand.pop(0))
                continue
            if step.kind == "send_owner_z_energy_to_drop":
                for _ in range(min(step.amount, len(player.z_energy))):
                    player.drop.append(player.z_energy.pop(0))
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
            if step.kind == "reduce_owner_battle_power_for_turn":
                candidates = SkillCostDsl._owner_battle_return_candidates(player, source_card, step)
                power_delta = int(step.params.get("power_delta", 0) or 0)
                for card in candidates[: step.amount]:
                    card.temporary_power_delta += power_delta
                metadata["alternate_cost_kind"] = "reduce_owner_battle_power_for_turn"
                continue
            if step.kind == "return_owner_battle_to_hand":
                candidate_ids = {
                    card.instance_id for card in SkillCostDsl._owner_battle_return_candidates(player, source_card, step)[: step.amount]
                }
                moved = 0
                i = 0
                while i < len(player.battle_area) and moved < step.amount:
                    card = player.battle_area[i]
                    if card.instance_id not in candidate_ids:
                        i += 1
                        continue
                    player.hand.append(player.battle_area.pop(i))
                    moved += 1
                metadata["alternate_cost_kind"] = "return_owner_battle_to_hand"
                continue
            if step.kind == "rest_owner_hidden_mode_battle":
                candidates = SkillCostDsl._owner_hidden_mode_active_battle_candidates(player, source_card, step)
                rested = 0
                for card in candidates[: step.amount]:
                    card.resting = True
                    rested += 1
                    if rested == 1:
                        metadata["cost_target_instance_id"] = int(card.instance_id)
                        metadata["cost_target_card_id"] = int(card.card_id)
                        metadata["cost_target_zone"] = "battle"
                metadata["alternate_cost_kind"] = "rest_owner_hidden_mode_battle"
                continue
            if step.kind == "add_life_to_hand":
                moved = 0
                while moved < step.amount:
                    player.hand.append(player.life.pop(0))
                    moved += 1
                metadata["alternate_cost_kind"] = "add_life_to_hand"
                continue
            if step.kind == "send_all_owner_drop_to_warp":
                player.warp.extend(player.drop)
                player.drop = []
                metadata["alternate_cost_kind"] = "send_all_owner_drop_to_warp"
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
