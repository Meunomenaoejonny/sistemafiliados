from __future__ import annotations

from typing import Tuple

from core.providers.search.search_provider import SearchProvider
from core.providers.search.serpapi_search_provider import SerpApiSearchProvider


def build_search_provider(
    *,
    serpapi_key: str,
    gl: str = "br",
    hl: str = "pt",
) -> tuple[SearchProvider, bool]:
    """
    Retorna (provider, live_mode).

    live_mode:
    - True quando SERPAPI_KEY existe
    - False quando usamos fallback 100% gratuito
    """

    key_present = bool((serpapi_key or "").strip())
    serpapi_available = False
    if key_present:
        try:
            from serpapi import GoogleSearch  # type: ignore # noqa: F401
            serpapi_available = True
        except Exception:
            serpapi_available = False

    live_mode = key_present and serpapi_available
    provider = SerpApiSearchProvider(serpapi_key=(serpapi_key or "").strip(), gl=gl, hl=hl)
    return provider, live_mode

