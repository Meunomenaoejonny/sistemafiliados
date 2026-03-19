from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from core.search_engine import ProductOffer

from .search_provider import SearchProvider


@dataclass
class _ProviderState:
    name: str
    provider: SearchProvider
    daily_limit: Optional[int] = None
    used_today: int = 0


class RouterSearchProvider(SearchProvider):
    """
    Router com fallback entre múltiplos providers.
    Ordem sugerida: serper -> serpapi -> fallback_free.
    """

    def __init__(self, providers: list[_ProviderState]) -> None:
        self._providers = providers
        self._day = date.today().isoformat()
        self.last_provider_used: Optional[str] = None
        self.last_attempt_chain: list[str] = []

    def _roll_day_if_needed(self) -> None:
        today = date.today().isoformat()
        if today != self._day:
            self._day = today
            for p in self._providers:
                p.used_today = 0

    def search(self, query: str, max_results: int = 3) -> list[ProductOffer]:
        self._roll_day_if_needed()
        self.last_provider_used = None
        self.last_attempt_chain = []
        last_exc: Optional[Exception] = None

        for p in self._providers:
            self.last_attempt_chain.append(p.name)
            if p.daily_limit is not None and p.used_today >= p.daily_limit:
                continue
            try:
                offers = p.provider.search(query, max_results=max_results)
                p.used_today += 1
                if offers:
                    self.last_provider_used = p.name
                    return offers
            except Exception as e:  # noqa: BLE001
                p.used_today += 1
                last_exc = e
                continue

        if last_exc is not None:
            raise last_exc
        return []

