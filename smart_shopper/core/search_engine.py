from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

# Import lazy: o app precisa iniciar mesmo sem `serpapi` no ambiente.
# O SerpApi é usado apenas para preços ao vivo.
try:
    from serpapi import GoogleSearch  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    GoogleSearch = None  # type: ignore[assignment]


TRUSTED_STORES = {
    "amazon",
    "mercado livre",
    "shopee",
    "aliexpress",
}


@dataclass(frozen=True)
class ProductOffer:
    title: str
    price: Optional[float]
    currency: Optional[str]
    store: str
    thumbnail: Optional[str]
    original_link: str
    is_live_price: bool = True
    price_label: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None


class SearchEngineError(RuntimeError):
    pass


def _parse_price_to_float(price_str: str) -> tuple[float, str]:
    s = (price_str or "").strip()
    currency = "BRL"

    if not s:
        raise ValueError("Preço vazio")

    if "R$" in s:
        currency = "BRL"
        s = s.replace("R$", "").strip()
    elif "$" in s:
        currency = "USD"
        s = s.replace("$", "").strip()

    s = s.replace("\u00a0", " ").replace(" ", "")

    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")

    return float(s), currency


def _is_trusted_store(store: str) -> bool:
    if not store:
        return False
    store_l = store.strip().lower()
    return any(t in store_l for t in TRUSTED_STORES)


class SearchEngine:
    def __init__(self, serpapi_key: Optional[str], gl: str = "br", hl: str = "pt") -> None:
        self._key = serpapi_key or None
        self._gl = gl
        self._hl = hl

    def search_google_shopping(self, query: str, max_results: int = 3) -> list[ProductOffer]:
        if not query or not query.strip():
            raise ValueError("Consulta vazia.")

        if not self._key:
            return self._search_free_fallback(query, max_results=max_results)

        if GoogleSearch is None:
            # Se as chaves/serpapi não estiverem instalados, caímos para o modo gratuito.
            return self._search_free_fallback(query, max_results=max_results)

        params = {
            "engine": "google_shopping",
            "q": query.strip(),
            "api_key": self._key,
            "gl": self._gl,
            "hl": self._hl,
        }

        try:
            data = GoogleSearch(params).get_dict()
        except Exception as e:  # noqa: BLE001
            raise SearchEngineError(
                "Falha ao buscar preços em tempo real. Tente novamente."
            ) from e

        results: Iterable[dict] = data.get("shopping_results") or []
        offers: list[ProductOffer] = []

        for item in results:
            title = (item.get("title") or "").strip()
            store = (item.get("source") or item.get("seller") or "").strip()
            link = (item.get("link") or item.get("product_link") or "").strip()
            thumbnail = item.get("thumbnail")

            price_raw = item.get("price") or ""
            if not title or not store or not link or not price_raw:
                continue

            if not _is_trusted_store(store):
                continue

            rating_raw = item.get("rating") or item.get("product_rating")
            reviews_raw = item.get("reviews") or item.get("reviews_count") or item.get("review_count")

            rating: Optional[float] = None
            if rating_raw is not None and str(rating_raw).strip():
                try:
                    rating = float(str(rating_raw).strip())
                except Exception:
                    rating = None

            reviews_count: Optional[int] = None
            if reviews_raw is not None and str(reviews_raw).strip():
                try:
                    # sometimes SerpApi may return "1,234" or similar
                    normalized = str(reviews_raw).strip().replace(",", "").replace(".", "")
                    reviews_count = int(normalized)
                except Exception:
                    reviews_count = None

            try:
                price, currency = _parse_price_to_float(str(price_raw))
            except Exception:  # noqa: BLE001
                continue

            offers.append(
                ProductOffer(
                    title=title,
                    price=price,
                    currency=currency,
                    store=store,
                    thumbnail=thumbnail,
                    original_link=link,
                    is_live_price=True,
                    price_label=None,
                    rating=rating,
                    reviews_count=reviews_count,
                )
            )

        if not offers:
            raise SearchEngineError(
                "Não encontrei ofertas confiáveis para esse termo. Tente refinar o nome/modelo."
            )

        offers.sort(key=lambda o: o.price)
        return offers[: max_results or 3]

    def _search_free_fallback(self, query: str, max_results: int = 3) -> list[ProductOffer]:
        """
        Modo 100% gratuito (sem SerpApi).
        Estimativa de preço via MarketIntelligence (catálogo de top vendidos BR 2025).
        """
        import urllib.parse
        from core.market.price_estimator import estimate_brl_range, brl_label

        low, high = estimate_brl_range(query)
        label = brl_label(low, high)
        enc_q = urllib.parse.quote(query.strip())

        candidate_stores = [
            ("AliExpress", f"https://pt.aliexpress.com/wholesale?SearchText={enc_q}"),
            ("Amazon", f"https://www.amazon.com.br/s?k={enc_q}"),
            ("Mercado Livre", f"https://lista.mercadolivre.com.br/{enc_q}"),
            ("Shopee", f"https://shopee.com.br/search?keyword={enc_q}"),
        ]

        offers: list[ProductOffer] = []
        for store_name, original_link in candidate_stores[: max_results or 3]:
            offers.append(
                ProductOffer(
                    title=f"{query.strip()} (busca por loja)",
                    price=None,
                    currency="BRL",
                    store=store_name,
                    thumbnail=None,
                    original_link=original_link,
                    is_live_price=False,
                    price_label=label,
                )
            )

        return offers

