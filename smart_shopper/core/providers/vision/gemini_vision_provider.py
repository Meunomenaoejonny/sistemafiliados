from __future__ import annotations

from core.vision_agent import VisionAgent

from .vision_provider import VisionProvider


class GeminiVisionProvider(VisionProvider):
    def __init__(self, api_key: str) -> None:
        self._agent = VisionAgent(api_key=api_key, gemini_model="gemini-1.5-flash")

    def identify_product_from_image_bytes(self, image_bytes: bytes) -> str:
        return self._agent.identify_product_from_image_bytes(image_bytes).product_query

