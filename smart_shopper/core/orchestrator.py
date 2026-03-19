from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from core.affiliate_manager import AffiliateConfig, to_affiliate_link
from core.models.offer_card import OfferCard
from core.ranking.offer_ranker import rank_offers
from core.providers.search.search_provider import SearchProvider
from core.providers.vision.vision_provider import VisionProvider


class OrchestratorError(RuntimeError):
    pass


class Orchestrator:
    def __init__(
        self,
        vision_provider: Optional[VisionProvider],
        search_provider: SearchProvider,
        affiliate_cfg: AffiliateConfig,
    ) -> None:
        self._vision = vision_provider
        self._search = search_provider
        self._affiliate_cfg = affiliate_cfg

    def identify_query(
        self, *, image_bytes: Optional[bytes], text_input: Optional[str]
    ) -> str:
        if image_bytes is not None:
            if not self._vision:
                raise OrchestratorError("Provider de visão não configurado.")
            return self._vision.identify_product_from_image_bytes(image_bytes)

        if not text_input or not text_input.strip():
            raise OrchestratorError("Digite uma descrição/link ou envie uma imagem.")

        return text_input.strip()

    def search_offers(self, query: str, max_results: int = 3) -> list[OfferCard]:
        offers = self._search.search(query, max_results=max_results)
        ranked = rank_offers(offers)
        cards: list[OfferCard] = []
        for r in ranked:
            o = r.offer
            affiliate_link = to_affiliate_link(o.original_link, o.store, self._affiliate_cfg)
            meta = asdict(o)
            meta.update(
                {
                    "value_score": r.value_score,
                    "why_this": r.why_this,
                    "potential_savings_label": r.potential_savings_label,
                }
            )
            cards.append(
                OfferCard(
                    title=o.title,
                    store=o.store,
                    affiliate_link=affiliate_link,
                    thumbnail=o.thumbnail,
                    original_link=o.original_link,
                    price=o.price,
                    currency=o.currency,
                    price_label=o.price_label,  # pode ser estimativa no modo gratuito
                    is_live_price=o.is_live_price,
                    metadata=meta,
                )
            )
        return cards

