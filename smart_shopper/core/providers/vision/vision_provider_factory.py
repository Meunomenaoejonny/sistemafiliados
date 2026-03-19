from __future__ import annotations

from typing import Optional

from core.providers.vision.gemini_vision_provider import GeminiVisionProvider
from core.providers.vision.hf_vision_provider import HFVisionProvider
from core.providers.vision.vision_provider import VisionProvider


class VisionProviderFactoryError(RuntimeError):
    pass


def build_vision_provider(
    *,
    image_present: bool,
    gemini_api_key: str,
    hf_token: str,
    gemini_model: str = "gemini-1.5-flash",
    hf_model: str = "zai-org/GLM-4.5V",
) -> tuple[Optional[VisionProvider], Optional[str]]:
    """
    Retorna (provider, backend_name) para visão.

    - backend_name: "gemini" | "hf" | None
    """

    if not image_present:
        return None, None

    gemini_api_key = (gemini_api_key or "").strip()
    if gemini_api_key:
        return GeminiVisionProvider(api_key=gemini_api_key), "gemini"

    hf_token = (hf_token or "").strip()
    if hf_token:
        return HFVisionProvider(hf_token=hf_token, hf_model=hf_model), "hf"

    raise VisionProviderFactoryError(
        "Para usar identificação por imagem, defina `GEMINI_API_KEY` ou `HF_TOKEN` em `st.secrets`."
    )

