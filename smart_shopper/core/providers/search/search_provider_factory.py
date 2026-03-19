from __future__ import annotations

from core.providers.search.search_provider import SearchProvider
from core.providers.search.router_search_provider import RouterSearchProvider, _ProviderState
from core.providers.search.serper_search_provider import SerperSearchProvider
from core.providers.search.serpapi_search_provider import SerpApiSearchProvider


def build_search_provider(
    *,
    serpapi_key: str,
    serper_api_key: str = "",
    gl: str = "br",
    hl: str = "pt",
) -> tuple[SearchProvider, bool]:
    """
    Retorna (provider, live_mode).

    live_mode:
    - True quando SERPAPI_KEY existe
    - False quando usamos fallback 100% gratuito
    """

    serpapi_key = (serpapi_key or "").strip()
    serper_api_key = (serper_api_key or "").strip()

    providers: list[_ProviderState] = []

    # 1) Serper first (free-tier usually larger)
    if serper_api_key:
        providers.append(
            _ProviderState(
                name="serper",
                provider=SerperSearchProvider(api_key=serper_api_key, gl=gl, hl=hl),
                daily_limit=None,  # pode ser controlado por variável depois
            )
        )

    # 2) SerpApi second
    if serpapi_key:
        providers.append(
            _ProviderState(
                name="serpapi",
                provider=SerpApiSearchProvider(serpapi_key=serpapi_key, gl=gl, hl=hl),
                daily_limit=None,
            )
        )

    # 3) fallback gratuito sempre disponível
    providers.append(
        _ProviderState(
            name="free_fallback",
            provider=SerpApiSearchProvider(serpapi_key="", gl=gl, hl=hl),
            daily_limit=None,
        )
    )

    live_mode = bool(serpapi_key or serper_api_key)
    return RouterSearchProvider(providers), live_mode

