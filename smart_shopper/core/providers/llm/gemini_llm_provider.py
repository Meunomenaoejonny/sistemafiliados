from __future__ import annotations

from typing import Optional

import google.generativeai as genai

from .llm_provider import LLMProvider, LLMProviderError


class GeminiLLMProvider(LLMProvider):
    def __init__(self, *, api_key: str, model: str = "gemini-1.5-flash") -> None:
        if not (api_key or "").strip():
            raise ValueError("GEMINI_API_KEY vazio.")
        self._api_key = api_key
        self._model_name = model
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)

    @property
    def name(self) -> str:
        return "gemini"

    def complete_text(
        self,
        *,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> str:
        try:
            resp = self._model.generate_content(
                prompt,
                generation_config={
                    "temperature": float(temperature),
                    "max_output_tokens": int(max_tokens),
                },
            )
            text: Optional[str] = getattr(resp, "text", None)
        except Exception as e:  # noqa: BLE001
            raise LLMProviderError("Falha ao consultar Gemini.") from e

        if not text or not text.strip():
            raise LLMProviderError("Gemini não retornou conteúdo.")

        return text.strip()

