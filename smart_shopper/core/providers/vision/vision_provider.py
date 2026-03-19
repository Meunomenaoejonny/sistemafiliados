from __future__ import annotations

from abc import ABC, abstractmethod


class VisionProvider(ABC):
    @abstractmethod
    def identify_product_from_image_bytes(self, image_bytes: bytes) -> str:
        """Retorna o termo de busca (nome exato e modelo) para encontrar produtos."""

