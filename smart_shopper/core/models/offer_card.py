from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class OfferCard:
    title: str
    store: str
    affiliate_link: str

    thumbnail: Optional[str] = None
    original_link: Optional[str] = None

    price: Optional[float] = None
    currency: Optional[str] = None
    price_label: Optional[str] = None
    is_live_price: bool = True

    # Campo para enriquecer a análise (rating, reviews, score, etc.)
    metadata: Optional[dict[str, Any]] = None

