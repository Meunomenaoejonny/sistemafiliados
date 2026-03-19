from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

from core.affiliate_manager import AffiliateConfig, to_affiliate_link, has_affiliate
from core.models.offer_card import OfferCard
from core.ranking.offer_ranker import rank_offers
from core.providers.search.search_provider import SearchProvider
from core.providers.vision.vision_provider import VisionProvider


class OrchestratorError(RuntimeError):
    pass


@dataclass
class PlatformResult:
    """Melhor oferta de uma plataforma específica."""
    store_key: str        # ex: "aliexpress"
    store_label: str      # ex: "AliExpress"
    store_icon: str       # ex: "🛒"
    card: OfferCard
    has_affiliate: bool
    value_score: float


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

    def search_offers(self, query: str, max_results: int = 12) -> list[OfferCard]:
        """Retorna todas as ofertas ranqueadas (usado internamente)."""
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
                    price_label=o.price_label,
                    is_live_price=o.is_live_price,
                    metadata=meta,
                )
            )
        return cards

    def search_by_platform(self, query: str, max_results: int = 20) -> list[PlatformResult]:
        """
        Busca ofertas e retorna a MELHOR oferta de cada plataforma,
        ordenado por: (1) tem afiliado, (2) value_score desc.
        """
        from core.affiliate_manager import ALL_STORES

        all_cards = self.search_offers(query, max_results=max_results)

        # Índice loja label → store_key e meta
        store_meta: dict[str, dict] = {
            s["label"].lower(): s for s in ALL_STORES
        }

        # Agrupar por loja, guardar o de maior value_score
        best_per_store: dict[str, OfferCard] = {}
        for card in all_cards:
            store_low = card.store.lower()
            existing = best_per_store.get(store_low)
            if existing is None:
                best_per_store[store_low] = card
            else:
                new_score = (card.metadata or {}).get("value_score", 0.0)
                old_score = (existing.metadata or {}).get("value_score", 0.0)
                if new_score > old_score:
                    best_per_store[store_low] = card

        # Montar resultados
        results: list[PlatformResult] = []
        for store_low, card in best_per_store.items():
            meta = store_meta.get(store_low, {})
            store_key = meta.get("key", store_low.replace(" ", ""))
            store_label = meta.get("label", card.store)
            store_icon = meta.get("icon", "🛒")
            aff = has_affiliate(self._affiliate_cfg, store_key)
            vs = float((card.metadata or {}).get("value_score", 0.0))
            results.append(
                PlatformResult(
                    store_key=store_key,
                    store_label=store_label,
                    store_icon=store_icon,
                    card=card,
                    has_affiliate=aff,
                    value_score=vs,
                )
            )

        # Ordenar: afiliados primeiro, depois por value_score
        results.sort(key=lambda r: (not r.has_affiliate, -r.value_score))
        return results
