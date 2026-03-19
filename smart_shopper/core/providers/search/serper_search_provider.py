from __future__ import annotations

from typing import Any, Optional

import requests

from core.search_engine import ProductOffer

from .search_provider import SearchProvider


class SerperSearchProvider(SearchProvider):
    """
    Provider via Serper.dev (shopping endpoint).
    Usado como alternativa/fallback ao SerpApi.
    """

    def __init__(self, api_key: str, gl: str = "br", hl: str = "pt") -> None:
        self._key = (api_key or "").strip()
        self._gl = gl
        self._hl = hl

    def search(self, query: str, max_results: int = 3):
        if not self._key:
            return []
        q = (query or "").strip()
        if not q:
            return []

        url = "https://google.serper.dev/shopping"
        payload = {"q": q, "gl": self._gl, "hl": self._hl}
        headers = {"X-API-KEY": self._key, "Content-Type": "application/json"}

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []

        items = data.get("shopping") or data.get("results") or []
        offers: list[ProductOffer] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            title = str(it.get("title") or "").strip()
            store = str(it.get("source") or it.get("seller") or "").strip()
            link = str(it.get("link") or "").strip()
            thumb = it.get("imageUrl") or it.get("thumbnail")
            price = _to_float_price(it.get("price"))
            if not title or not store or not link or price is None:
                continue
            currency = "BRL"
            rating = _to_float(it.get("rating") or it.get("productRating"))
            reviews_count = _to_int(it.get("reviewCount") or it.get("reviews") or it.get("reviewsCount"))
            offers.append(
                ProductOffer(
                    title=title,
                    price=price,
                    currency=currency,
                    store=store,
                    thumbnail=thumb,
                    original_link=link,
                    is_live_price=True,
                    price_label=None,
                    rating=rating,
                    reviews_count=reviews_count,
                )
            )

        offers.sort(key=lambda o: o.price if o.price is not None else 10**12)
        return offers[: max_results or 3]


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except Exception:
        return None


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip().replace(".", "").replace(",", "")
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None


def _to_float_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value)
    s = s.replace("R$", "").replace("$", "").strip()
    s = s.replace("\u00a0", " ").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

