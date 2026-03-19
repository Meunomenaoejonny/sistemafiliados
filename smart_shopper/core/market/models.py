from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TopProduct:
    model: str
    category: str
    rank: int
    source_label: str
    price_from_brl: Optional[int] = None
    price_to_brl: Optional[int] = None
    key_specs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    is_top_seller: bool = True


@dataclass(frozen=True)
class MarketMatchResult:
    matched: bool
    product: Optional[TopProduct]
    category: str
    is_top_seller: bool
    price_hint_low: Optional[int]
    price_hint_high: Optional[int]
    market_context_md: str
