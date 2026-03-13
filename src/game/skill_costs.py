from __future__ import annotations

from dataclasses import dataclass

from src.game.state import CardInstance, PlayerState


@dataclass(frozen=True)
class SkillCostStep:
    kind: str
    amount: int = 1


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
            steps.append(SkillCostStep(kind=kind, amount=amount))
        return SkillCostSpec(steps=tuple(steps))


class SkillCostDsl:
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
            raise ValueError(f"Unknown skill cost kind: {step.kind}")
        return True

    @staticmethod
    def pay(player: PlayerState, source_card: CardInstance, spec: SkillCostSpec) -> None:
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
            raise ValueError(f"Unknown skill cost kind: {step.kind}")
