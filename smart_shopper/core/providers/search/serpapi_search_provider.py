from __future__ import annotations

from core.search_engine import SearchEngine

from .search_provider import SearchProvider


class SerpApiSearchProvider(SearchProvider):
    def __init__(self, serpapi_key: str, gl: str = "br", hl: str = "pt") -> None:
        self._engine = SearchEngine(serpapi_key=serpapi_key, gl=gl, hl=hl)

    def search(self, query: str, max_results: int = 3):
        return self._engine.search_google_shopping(query, max_results=max_results)

