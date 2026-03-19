from __future__ import annotations

from typing import Optional

from huggingface_hub import InferenceClient

from .llm_provider import LLMProvider, LLMProviderError


class HFTextLLMProvider(LLMProvider):
    """
    Text-only LLM via Hugging Face Inference Providers (OpenAI-compatible chat).
    """

    def __init__(self, *, hf_token: str, model: str = "Qwen/Qwen2.5-7B-Instruct") -> None:
        if not (hf_token or "").strip():
            raise ValueError("HF_TOKEN vazio.")
        self._client = InferenceClient(token=hf_token)
        self._model = model

    @property
    def name(self) -> str:
        return "hf"

    def complete_text(
        self,
        *,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> str:
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=float(temperature),
                max_tokens=int(max_tokens),
            )
            text: Optional[str] = completion.choices[0].message.content  # type: ignore[assignment]
        except Exception as e:  # noqa: BLE001
            raise LLMProviderError("Falha ao consultar Hugging Face (texto).") from e

        if not text or not str(text).strip():
            raise LLMProviderError("HF não retornou conteúdo.")

        return str(text).strip()

