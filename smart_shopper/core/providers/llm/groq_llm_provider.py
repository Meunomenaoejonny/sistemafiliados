from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import requests

from .llm_provider import LLMProvider, LLMProviderError


@dataclass(frozen=True)
class GroqConfig:
    api_key: str
    model: str = "llama-3.1-8b-instant"
    base_url: str = "https://api.groq.com/openai/v1"
    timeout_s: float = 30.0


class GroqLLMProvider(LLMProvider):
    def __init__(self, cfg: GroqConfig) -> None:
        if not (cfg.api_key or "").strip():
            raise ValueError("GROQ_API_KEY vazio.")
        self._cfg = cfg

    @property
    def name(self) -> str:
        return "groq"

    def complete_text(
        self,
        *,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> str:
        url = f"{self._cfg.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._cfg.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self._cfg.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self._cfg.timeout_s)
        except Exception as e:  # noqa: BLE001
            raise LLMProviderError("Falha ao conectar no Groq.") from e

        if resp.status_code >= 400:
            raise LLMProviderError(f"Groq retornou HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            raise LLMProviderError("Groq retornou JSON inválido.") from e

        text: Optional[str] = None
        try:
            text = data["choices"][0]["message"]["content"]
        except Exception:
            text = None

        if not text or not str(text).strip():
            raise LLMProviderError("Groq não retornou conteúdo.")

        return str(text).strip()

