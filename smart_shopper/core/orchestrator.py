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
    """Produto destaque (mais barato) de uma plataforma específica."""
    store_key: str        # ex: "aliexpress"
    store_label: str      # ex: "AliExpress"
    store_icon: str       # ex: "🛒"
    card: OfferCard
    has_affiliate: bool
    value_score: float
    rank_price: Optional[float] = None


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
                    "result_origin": "live",
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
        Busca ofertas e retorna o produto MAIS BARATO de cada plataforma.
        Ordenação do ranking:
          1) preço crescente (quando disponível)
          2) value_score (desempate)
        """
        from core.affiliate_manager import ALL_STORES, store_search_url
        from core.market.price_estimator import estimate_brl_range, brl_label

        offers = self._search.search(query, max_results=max_results)
        ranked = rank_offers(offers)

        # Índice loja (key/label) para metadados e matching flexível.
        store_meta_by_key: dict[str, dict] = {s["key"]: s for s in ALL_STORES}

        def _store_key_from_name(name: str) -> str:
            n = (name or "").lower()
            if "aliexpress" in n:
                return "aliexpress"
            if "mercado livre" in n or "mercadolivre" in n:
                return "mercadolivre"
            if "amazon" in n:
                return "amazon"
            if "shopee" in n:
                return "shopee"
            if "magalu" in n or "magazine luiza" in n:
                return "magalu"
            if "shein" in n:
                return "shein"
            if "kabum" in n or "ka bum" in n:
                return "kabum"
            if "americanas" in n:
                return "americanas"
            if "casas bahia" in n:
                return "casasbahia"
            return n.replace(" ", "")

        # Agrupar por loja: manter o menor preço da plataforma.
        # Se não houver preço, usar maior value_score como fallback.
        best_by_store: dict[str, tuple[OfferCard, float, Optional[float]]] = {}
        for r in ranked:
            o = r.offer
            store_key = _store_key_from_name(o.store)
            affiliate_link = to_affiliate_link(o.original_link, o.store, self._affiliate_cfg)
            meta = asdict(o)
            meta.update(
                {
                    "value_score": r.value_score,
                    "why_this": r.why_this,
                    "potential_savings_label": r.potential_savings_label,
                }
            )
            card = OfferCard(
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
            cur = best_by_store.get(store_key)
            cur_price = float(o.price) if o.price is not None else None
            if cur is None:
                best_by_store[store_key] = (card, r.value_score, cur_price)
                continue
            old_card, old_score, old_price = cur
            if cur_price is not None and (old_price is None or cur_price < old_price):
                best_by_store[store_key] = (card, r.value_score, cur_price)
            elif cur_price is None and old_price is None and r.value_score > old_score:
                best_by_store[store_key] = (card, r.value_score, cur_price)

        # Montar resultados
        results: list[PlatformResult] = []
        for store_key, (card, vs, p) in best_by_store.items():
            meta = store_meta_by_key.get(store_key, {})
            store_label = meta.get("label", card.store)
            store_icon = meta.get("icon", "🛒")
            aff = has_affiliate(self._affiliate_cfg, store_key)
            results.append(
                PlatformResult(
                    store_key=store_key,
                    store_label=store_label,
                    store_icon=store_icon,
                    card=card,
                    has_affiliate=aff,
                    value_score=vs,
                    rank_price=p,
                )
            )

        # Completar plataformas faltantes:
        # 1) tenta busca direcionada por loja (modo live)
        # 2) se não achar, usa fallback por loja (estimativa)
        low, high = estimate_brl_range(query)
        fallback_label = brl_label(low, high)
        existing_keys = {r.store_key for r in results}
        has_live_any = any((r.card.is_live_price for r in results))
        for s in ALL_STORES:
            sk = s["key"]
            if sk in existing_keys:
                continue
            live_card: Optional[OfferCard] = None
            live_score: float = 0.0
            live_price: Optional[float] = None

            # Busca direcionada só quando já estamos em modo live.
            if has_live_any:
                try:
                    probe_query = f"{query} {s['label']}"
                    probe_offers = self._search.search(probe_query, max_results=8)
                    probe_ranked = rank_offers(probe_offers)
                    # Tenta casar pela própria loja; se não tiver, usa o melhor da probe.
                    picked = None
                    picked_score = 0.0
                    for pr in probe_ranked:
                        if _store_key_from_name(pr.offer.store) == sk:
                            picked = pr
                            picked_score = pr.value_score
                            break
                    if picked is None and probe_ranked:
                        picked = probe_ranked[0]
                        picked_score = picked.value_score

                    if picked is not None:
                        o = picked.offer
                        aff_link = to_affiliate_link(o.original_link, o.store, self._affiliate_cfg)
                        m = asdict(o)
                        m.update(
                            {
                                "value_score": picked.value_score,
                                "why_this": f"Busca direcionada para {s['label']}. {picked.why_this}",
                                "potential_savings_label": picked.potential_savings_label,
                                "result_origin": "probe",
                            }
                        )
                        live_card = OfferCard(
                            title=o.title,
                            store=s["label"],  # mostra a plataforma alvo no dashboard
                            affiliate_link=aff_link,
                            thumbnail=o.thumbnail,
                            original_link=o.original_link,
                            price=o.price,
                            currency=o.currency,
                            price_label=o.price_label,
                            is_live_price=o.is_live_price,
                            metadata=m,
                        )
                        live_score = picked_score
                        live_price = float(o.price) if o.price is not None else None
                except Exception:
                    live_card = None

            if live_card is not None:
                results.append(
                    PlatformResult(
                        store_key=sk,
                        store_label=s["label"],
                        store_icon=s["icon"],
                        card=live_card,
                        has_affiliate=has_affiliate(self._affiliate_cfg, sk),
                        value_score=live_score,
                        rank_price=live_price,
                    )
                )
                continue

            url = store_search_url(sk, query)
            if not url:
                continue
            aff_url = to_affiliate_link(url, s["label"], self._affiliate_cfg)
            fallback_card = OfferCard(
                title=query.strip(),
                store=s["label"],
                affiliate_link=aff_url,
                thumbnail=None,
                original_link=url,
                price=None,
                currency="BRL",
                price_label=fallback_label,
                is_live_price=False,
                metadata={
                    "value_score": 0.0,
                    "why_this": "Fallback por plataforma (sem preço ao vivo nesta loja para esta busca).",
                    "potential_savings_label": None,
                    "rating": None,
                    "reviews_count": None,
                    "result_origin": "estimated",
                },
            )
            results.append(
                PlatformResult(
                    store_key=sk,
                    store_label=s["label"],
                    store_icon=s["icon"],
                    card=fallback_card,
                    has_affiliate=has_affiliate(self._affiliate_cfg, sk),
                    value_score=0.0,
                    rank_price=None,
                )
            )

        # Ranking por menor preço por plataforma; desempate por score.
        results.sort(
            key=lambda r: (
                r.rank_price is None,
                r.rank_price if r.rank_price is not None else 10**12,
                -r.value_score,
            )
        )
        return results
