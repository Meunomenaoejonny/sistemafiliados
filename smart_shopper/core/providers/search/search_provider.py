from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from core.search_engine import ProductOffer


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 3) -> List[ProductOffer]:
        """Busca ofertas para o termo de busca e retorna ofertas ordenadas/filtradas."""

