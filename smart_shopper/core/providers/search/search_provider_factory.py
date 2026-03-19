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

    # Live mode depende da chave; o engine faz fallback HTTP se módulo não existir.
    live_mode = bool((serpapi_key or "").strip())
    provider = SerpApiSearchProvider(serpapi_key=(serpapi_key or "").strip(), gl=gl, hl=hl)
    return provider, live_mode

