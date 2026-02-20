from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol, Set

from src.domain.models import CardData


class CardNotFoundError(KeyError):
    pass


class InvalidCardRecordError(ValueError):
    pass


@dataclass(frozen=True)
class CardQuery:
    name_contains: Optional[str] = None
    card_number: Optional[str] = None
    colors: Optional[Set[str]] = None
    card_types: Optional[Set[str]] = None
    include_variants: bool = True
    include_banned: bool = False
    limit: int = 100


class CardRepository(Protocol):
    def get_by_id(self, card_id: int, *, source_table: str = "cards") -> CardData:
        ...

    def get_by_number(self, card_number: str, *, include_variants: bool = True) -> list[CardData]:
        ...

    def search(self, query: CardQuery) -> list[CardData]:
        ...

    def list_by_ids(self, ids: Iterable[int], *, source_table: str = "cards") -> list[CardData]:
        ...
