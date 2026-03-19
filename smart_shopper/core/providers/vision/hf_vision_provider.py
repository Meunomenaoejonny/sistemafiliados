from __future__ import annotations

from core.vision_agent import VisionAgent

from .vision_provider import VisionProvider


class HFVisionProvider(VisionProvider):
    def __init__(self, hf_token: str, hf_model: str = "zai-org/GLM-4.5V") -> None:
        self._agent = VisionAgent(hf_token=hf_token, hf_model=hf_model)

    def identify_product_from_image_bytes(self, image_bytes: bytes) -> str:
        return self._agent.identify_product_from_image_bytes(image_bytes).product_query

