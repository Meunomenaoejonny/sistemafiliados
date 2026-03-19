from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .llm_provider import LLMProvider


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider_name: str


class LLMRouter:
    """
    Tenta providers em ordem até obter resposta.
    """

    def __init__(self, providers: list[LLMProvider]) -> None:
        self._providers = providers

    @property
    def providers(self) -> list[LLMProvider]:
        return list(self._providers)

    def complete_text(
        self,
        *,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> LLMResult:
        last_error: Optional[Exception] = None
        for p in self._providers:
            try:
                text = p.complete_text(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return LLMResult(text=text, provider_name=p.name)
            except Exception as e:  # noqa: BLE001
                last_error = e
                continue

        raise RuntimeError(f"Nenhum provider de LLM respondeu. Último erro: {last_error}")

