from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Iterable


EFFECT_FAMILY_ASSIGNMENT_CANDIDATES_SCHEMA_VERSION = "effect_family_assignment_candidates.v1"


def _fetch_card_text_rows(db_path: Path, card_ids: Iterable[int]) -> dict[int, dict[str, object]]:
    resolved_ids = sorted({int(card_id) for card_id in card_ids if int(card_id) > 0})
    if not resolved_ids:
        return {}
    rows_by_id: dict[int, dict[str, object]] = {}
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        for offset in range(0, len(resolved_ids), 900):
            batch = resolved_ids[offset : offset + 900]
            placeholders = ", ".join("?" for _ in batch)
            rows = conn.execute(
                f"SELECT id, card_number, card_name, card_type, card_skill_unstyled FROM cards WHERE id IN ({placeholders})",
                [int(card_id) for card_id in batch],
            ).fetchall()
            for row in rows:
                rows_by_id[int(row["id"])] = {
                    "card_id": int(row["id"]),
                    "card_number": str(row["card_number"] or ""),
                    "card_name": str(row["card_name"] or ""),
                    "card_type": str(row["card_type"] or ""),
                    "card_skill_unstyled": str(row["card_skill_unstyled"] or ""),
                }
    finally:
        conn.close()
    return rows_by_id


def _propose_candidate(row: dict[str, object], known_family_ids: set[str]) -> dict[str, object] | None:
    text = str(row.get("card_skill_unstyled", "") or "").lower()
    card_type = str(row.get("card_type", "") or "").upper()

    def _candidate(
        *,
        family_id: str,
        trigger: str,
        handler_id: str,
        confidence: float,
        reason: str,
        auto_apply_safe: bool,
    ) -> dict[str, object]:
        return {
            "card_id": int(row["card_id"]),
            "card_number": str(row["card_number"]),
            "card_name": str(row["card_name"]),
            "card_type": card_type,
            "family_id": family_id,
            "trigger": trigger,
            "handler_id": handler_id,
            "confidence": float(confidence),
            "reason": reason,
            "family_already_in_catalog": family_id in known_family_ids,
            "auto_apply_safe": bool(auto_apply_safe),
            "suggested_override_mode": "replace",
        }

    if "[counter: attack]" in text and "negate the attack" in text and "play this card" in text:
        if "can't attack with their leader card for the turn" in text:
            return _candidate(
                family_id="counter_attack:counter_negate_attack_play_self_attack_restriction",
                trigger="counter_attack",
                handler_id="counter_negate_attack_play_self_attack_restriction",
                confidence=1.0,
                reason="Exact runtime-supported counter text match: negate, play self, and leader-attack restriction.",
                auto_apply_safe=True,
            )
        return _candidate(
            family_id="counter_attack:counter_negate_attack_play_self",
            trigger="counter_attack",
            handler_id="counter_negate_attack_play_self",
            confidence=0.98,
            reason="Exact runtime-supported counter text match: negate the attack, then play this card.",
            auto_apply_safe=True,
        )

    if "[counter: attack]" in text and "negate the attack" in text:
        return _candidate(
            family_id="counter_attack:counter_negate_attack",
            trigger="counter_attack",
            handler_id="counter_negate_attack",
            confidence=0.93,
            reason="High-confidence counter text match: negate the attack without play-self text.",
            auto_apply_safe=True,
        )

    if (
        card_type == "BATTLE"
        and "[super combo]" in text
        and "when you combo with this card" in text
        and "draw 1 card" in text
    ):
        return _candidate(
            family_id="self_comboed:auto_draw_n",
            trigger="self_comboed",
            handler_id="auto_draw_n",
            confidence=0.9,
            reason="High-confidence Super Combo draw family match, but condition support still needs explicit Sparking/leader gating.",
            auto_apply_safe=False,
        )

    return None


def build_effect_family_assignment_candidates(
    mapping_report: dict[str, object],
    *,
    db_path: Path,
    known_family_ids: Iterable[str],
    top_n: int = 50,
) -> dict[str, object]:
    unmapped = list(mapping_report.get("unmapped_priority_cards", []))
    rows_by_id = _fetch_card_text_rows(db_path, [int(row["card_id"]) for row in unmapped if isinstance(row, dict) and "card_id" in row])
    known = {str(family_id) for family_id in known_family_ids}

    candidates: list[dict[str, object]] = []
    for usage_row in unmapped:
        if not isinstance(usage_row, dict):
            continue
        card_id = int(usage_row.get("card_id", 0) or 0)
        source = rows_by_id.get(card_id)
        if source is None:
            continue
        candidate = _propose_candidate(source, known)
        if candidate is None:
            continue
        candidate["combined_count"] = int(usage_row.get("combined_count", 0) or 0)
        candidate["trace_count"] = int(usage_row.get("trace_count", 0) or 0)
        candidate["deck_count"] = int(usage_row.get("deck_count", 0) or 0)
        candidates.append(candidate)

    candidates.sort(
        key=lambda row: (
            -float(row["confidence"]),
            -int(row["combined_count"]),
            -int(row["trace_count"]),
            str(row["card_name"]),
            int(row["card_id"]),
        )
    )
    sliced = candidates[: max(int(top_n), 0)]

    return {
        "schema_version": EFFECT_FAMILY_ASSIGNMENT_CANDIDATES_SCHEMA_VERSION,
        "summary": {
            "candidate_count": len(candidates),
            "reported_candidate_count": len(sliced),
            "auto_apply_safe_count": sum(1 for row in sliced if bool(row["auto_apply_safe"])),
        },
        "candidates": sliced,
    }


def build_effect_family_assignment_candidates_from_paths(
    *,
    mapping_report_path: Path,
    family_report_path: Path,
    db_path: Path,
    top_n: int = 50,
) -> dict[str, object]:
    mapping_report = json.loads(mapping_report_path.read_text(encoding="utf-8-sig"))
    family_report = json.loads(family_report_path.read_text(encoding="utf-8-sig"))
    known_family_ids = [str(row["family_id"]) for row in family_report.get("families", []) if isinstance(row, dict) and "family_id" in row]
    return build_effect_family_assignment_candidates(
        mapping_report,
        db_path=db_path,
        known_family_ids=known_family_ids,
        top_n=top_n,
    )
