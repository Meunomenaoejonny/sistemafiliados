from __future__ import annotations

from typing import Optional

from core.providers.llm.groq_llm_provider import GroqConfig, GroqLLMProvider
from core.providers.llm.gemini_llm_provider import GeminiLLMProvider
from core.providers.llm.hf_text_llm_provider import HFTextLLMProvider
from core.providers.llm.llm_provider import LLMProvider
from core.providers.llm.router import LLMRouter


def build_llm_router(
    *,
    groq_api_key: str = "",
    gemini_api_key: str = "",
    hf_token: str = "",
    groq_model: str = "llama-3.1-8b-instant",
    hf_text_model: str = "Qwen/Qwen2.5-7B-Instruct",
    gemini_model: str = "gemini-1.5-flash",
    prefer: Optional[list[str]] = None,
) -> Optional[LLMRouter]:
    """
    Monta um router com providers disponíveis.

    prefer: ordem desejada de nomes ("groq", "gemini", "hf"). Se None, usa groq->gemini->hf.
    """

    providers: dict[str, LLMProvider] = {}

    if (groq_api_key or "").strip():
        providers["groq"] = GroqLLMProvider(GroqConfig(api_key=groq_api_key.strip(), model=groq_model))
    if (gemini_api_key or "").strip():
        providers["gemini"] = GeminiLLMProvider(api_key=gemini_api_key.strip(), model=gemini_model)
    if (hf_token or "").strip():
        providers["hf"] = HFTextLLMProvider(hf_token=hf_token.strip(), model=hf_text_model)

    if not providers:
        return None

    order = prefer or ["groq", "gemini", "hf"]
    ordered = [providers[n] for n in order if n in providers]
    # Append any remaining providers not listed (future-proof)
    for k, p in providers.items():
        if k not in order:
            ordered.append(p)

    return LLMRouter(ordered)

