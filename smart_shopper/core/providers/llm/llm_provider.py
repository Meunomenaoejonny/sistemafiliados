from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProviderError(RuntimeError):
    pass


class LLMProvider(ABC):
    """
    Interface mínima para completar texto (chat-like).
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def complete_text(
        self,
        *,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> str: ...

