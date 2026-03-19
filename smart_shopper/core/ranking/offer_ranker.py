from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from core.search_engine import ProductOffer


@dataclass(frozen=True)
class RankedOffer:
    offer: ProductOffer
    value_score: float
    why_this: str
    potential_savings_label: Optional[str]


def _price_score(price: Optional[float], min_price: float, max_price: float) -> float:
    if price is None:
        return 0.0
    if max_price <= min_price:
        return 1.0
    # Smaller price => closer to 1.0
    return (max_price - price) / (max_price - min_price)


def _quality_score(rating: Optional[float], reviews_count: Optional[int]) -> float:
    if rating is None:
        return 0.0

    rating_norm = max(0.0, min(1.0, rating / 5.0))

    if reviews_count is None or reviews_count <= 0:
        reviews_norm = 0.0
    else:
        # log-scale to avoid domination by huge review counts
        # 0 (poucas reviews) -> 1 (muitas reviews)
        reviews_norm = 1.0 - math.exp(-math.log10(reviews_count + 1) / 2.8)
        reviews_norm = max(0.0, min(1.0, reviews_norm))

    # Weighted mix (tunable)
    return 0.75 * rating_norm + 0.25 * reviews_norm


def rank_offers(offers: list[ProductOffer]) -> list[RankedOffer]:
    """
    Score determinístico de "valor" para ordenar ofertas.

    - Quando `rating/reviews` não existirem, o score vira majoritariamente por preço.
    - `potential_savings_label` é comparativo (ex: vs média das ofertas).
    """
    if not offers:
        return []

    prices = [o.price for o in offers if o.price is not None]
    min_price = min(prices) if prices else 0.0
    max_price = max(prices) if prices else 0.0
    avg_price = (sum(prices) / len(prices)) if prices else None

    ranked: list[RankedOffer] = []
    for o in offers:
        ps = _price_score(o.price, min_price=min_price, max_price=max_price)
        qs = _quality_score(o.rating, o.reviews_count)

        # Se a oferta não tem preço ao vivo, ranking majoritariamente por preço (estimativa).
        if not o.is_live_price:
            value_score = ps
            why = "Oferta em modo gratuito (estimativa) e possível variação de preços."
            ranked.append(RankedOffer(o, value_score=value_score, why_this=why, potential_savings_label=None))
            continue

        # Pesos custo-benefício:
        # - preço ainda importa mais, mas qualidade (rating + reviews) pode virar o jogo.
        # - se não houver rating, cai automaticamente para "preço".
        if qs <= 0.0:
            value_score = ps
        else:
            value_score = 0.58 * ps + 0.42 * qs

        # Economia potencial comparativa
        savings_label: Optional[str] = None
        if avg_price is not None and o.price is not None:
            diff = avg_price - o.price
            if diff > 0:
                # sem formatação locale pesada
                savings_label = f"Possível economia vs média: R$ {diff:,.0f}".replace(",", ".")

        if o.rating is not None:
            rc = o.reviews_count or 0
            rating_part = f"{o.rating:.1f}/5 ({rc} reviews)"
        else:
            rating_part = "sem rating"

        why_this = f"Custo-benefício: preço (score {ps:.2f}) + qualidade ({rating_part})."
        if savings_label:
            why_this = f"{why_this} {savings_label}"

        ranked.append(
            RankedOffer(
                offer=o,
                value_score=value_score,
                why_this=why_this,
                potential_savings_label=savings_label,
            )
        )

    ranked.sort(key=lambda r: r.value_score, reverse=True)
    return ranked

