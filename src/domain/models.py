from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class CardData:
    # Identity
    id: int
    card_number: str
    card_name: str
    source_table: str
    base_id: Optional[int] = None

    # Core metadata
    card_series: Optional[str] = None
    card_rarity: Optional[str] = None
    card_type: Optional[str] = None
    card_color: Optional[str] = None

    # Numeric gameplay fields
    energy_cost_int: Optional[int] = None
    combo_cost_int: Optional[int] = None
    combo_power_int: Optional[int] = None
    power_int: Optional[int] = None

    # Raw text gameplay fields
    card_energy_cost: Optional[str] = None
    card_combo_cost: Optional[str] = None
    card_combo_power: Optional[str] = None
    card_power: Optional[str] = None
    card_skill_unstyled: Optional[str] = None
    card_skill_html: Optional[str] = None
    z_energy_cost: Optional[str] = None

    # Back side data
    card_back_name: Optional[str] = None
    card_back_power: Optional[str] = None
    card_back_skill_unstyled: Optional[str] = None
    card_back_skill_html: Optional[str] = None

    # Normalized JSON list fields
    traits: Tuple[str, ...] = ()
    character_tags: Tuple[str, ...] = ()
    era_tags: Tuple[str, ...] = ()
    keywords: Tuple[str, ...] = ()
    back_traits: Tuple[str, ...] = ()
    back_character_tags: Tuple[str, ...] = ()
    back_era_tags: Tuple[str, ...] = ()

    # Flags
    is_banned: bool = False
    is_limited: bool = False
    limited_to: Optional[int] = None
    has_counter: bool = False
    has_counter_attack: bool = False
    has_counter_play: bool = False
    has_activate_main: bool = False
    has_activate_battle: bool = False
    has_auto: bool = False
    has_permanent: bool = False
    ignores_barrier: bool = False
    grants_triple_strike: bool = False
    has_draw: bool = False
    max_draw: Optional[int] = None
    max_power_reduction: Optional[int] = None
    has_barrier: bool = False
