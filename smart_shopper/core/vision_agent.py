from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Optional

import re

import google.generativeai as genai
from huggingface_hub import InferenceClient
from PIL import Image


VISION_PROMPT = (
    "Analise esta imagem e me retorne APENAS o nome exato e modelo deste produto "
    "para uma busca comercial. Seja direto."
)
VISION_PROMPT_WITH_OCR = (
    VISION_PROMPT
    + "\n\n"
    + "Se houver texto legível (marca/modelo/capacidade), priorize esses dados. "
    + "Retorne APENAS o termo final, sem explicações."
)
VISION_PROMPT_EMPTY_FALLBACK = (
    VISION_PROMPT
    + "\n\n"
    + "Se você não conseguir identificar com confiança, responda exatamente 'NAO_SEI'."
)


@dataclass(frozen=True)
class VisionResult:
    product_query: str


class VisionAgentError(RuntimeError):
    pass


class VisionAgent:
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        hf_token: Optional[str] = None,
        gemini_model: str = "gemini-1.5-flash",
        hf_model: str = "zai-org/GLM-4.5V",
    ) -> None:
        """
        Agente de visão com fallback:
        - Gemini quando `api_key` (GEMINI_API_KEY) existir
        - Caso contrário, Hugging Face Inference Providers com `hf_token`
        """
        self._gemini_model_name = gemini_model
        self._hf_model_name = hf_model
        self._backend: str

        if api_key:
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(gemini_model)
            self._backend = "gemini"
        elif hf_token:
            self._client = InferenceClient(token=hf_token)
            self._backend = "hf"
        else:
            raise ValueError("Informe GEMINI_API_KEY ou HF_TOKEN para usar visão.")

    def identify_product_from_image_bytes(self, image_bytes: bytes) -> VisionResult:
        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
        except Exception as e:  # noqa: BLE001
            raise VisionAgentError("Não consegui ler a imagem enviada.") from e

        # Optional local OCR: best-effort (no hard dependency).
        # If available, it can reduce ambiguity and sometimes avoids extra VLM attempts.
        ocr_text = _try_extract_text_from_image(image)
        prompt = VISION_PROMPT_WITH_OCR if ocr_text else VISION_PROMPT

        # If OCR exists and looks usable, prefer it as "best effort" to avoid VLM failures.
        if ocr_text:
            cleaned_query = _clean_ocr_to_query(ocr_text)
            if cleaned_query:
                return VisionResult(product_query=cleaned_query)

        if self._backend == "gemini":
            try:
                generation_config = {"temperature": 0.0, "max_output_tokens": 64}
                if ocr_text:
                    response = self._model.generate_content(
                        [prompt, f"TEXTO_OCR:\n{ocr_text}", image],
                        generation_config=generation_config,
                    )
                else:
                    response = self._model.generate_content(
                        [prompt, image],
                        generation_config=generation_config,
                    )
                text: Optional[str] = getattr(response, "text", None)
            except Exception as e:  # noqa: BLE001
                raise VisionAgentError(
                    "Falha ao consultar a IA de visão (Gemini). Tente novamente em instantes."
                ) from e
        else:
            # HF Inference Providers (Image-Text-to-Text via Chat Completion API)
            # Para evitar converter imagem para arquivo, usamos data URL em base64.
            import base64

            # Reencode as PNG to keep it uniform for the VLM
            buf = BytesIO()
            image.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            data_url = f"data:image/png;base64,{b64}"

            try:
                # First attempt
                completion = self._client.chat.completions.create(
                    model=self._hf_model_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (f"{prompt}\n\nTEXTO_OCR:\n{ocr_text}" if ocr_text else prompt),
                                },
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        }
                    ],
                    temperature=0.0,
                    max_tokens=96,
                )
                text = _extract_hf_text(completion)
            except Exception as e:  # noqa: BLE001
                raise VisionAgentError(
                    "Falha ao consultar a IA de visão (Hugging Face). Tente novamente em instantes."
                ) from e

            if not text or not text.strip():
                # Retry once with an alternate prompt + slightly more tokens.
                try:
                    completion2 = self._client.chat.completions.create(
                        model=self._hf_model_name,
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": VISION_PROMPT_EMPTY_FALLBACK},
                                    {"type": "image_url", "image_url": {"url": data_url}},
                                ],
                            }
                        ],
                        temperature=0.0,
                        max_tokens=120,
                    )
                    text = _extract_hf_text(completion2)
                except Exception:
                    # Keep original empty result -> later error message
                    pass

        if not text or not text.strip():
            raise VisionAgentError(
                f"A IA de visão não retornou um nome de produto (backend={self._backend}). "
                "Tente outra foto mais nítida."
            )

        if text.strip() == "NAO_SEI":
            raise VisionAgentError("A IA não conseguiu identificar o produto com confiança. Tente outra foto.")

        product_query = text.strip().strip('"').strip("'")
        if _is_generic_or_invalid_query(product_query):
            raise VisionAgentError(
                "A IA retornou um termo genérico para essa imagem. "
                "Tente outra foto (mais nítida e com o produto ocupando mais a imagem)."
            )
        return VisionResult(product_query=product_query)


def _try_extract_text_from_image(image: Image.Image) -> Optional[str]:
    """
    Best-effort OCR (CPU). Optional: if pytesseract isn't installed/configured,
    we silently return None.
    """

    try:
        import pytesseract  # type: ignore
    except Exception:
        return None

    try:
        # Light preprocessing helps a bit on screenshots/labels.
        gray = image.convert("L")
        text = pytesseract.image_to_string(gray)
    except Exception:
        return None

    text = (text or "").strip()
    if not text:
        return None

    # Keep it compact to avoid prompt bloat.
    text = " ".join(text.split())
    return text[:500]


def _extract_hf_text(completion: object) -> Optional[str]:
    """
    Best-effort extraction for OpenAI-compatible HF Inference responses.
    Sometimes the object shape differs (dict vs attribute-based).
    """

    try:
        choices = getattr(completion, "choices", None)
        if choices:
            first = choices[0]
            msg = getattr(first, "message", None)
            if msg is not None:
                content = getattr(msg, "content", None)
                if content:
                    return str(content).strip()
            # dict-like fallback
            if isinstance(first, dict):
                message = first.get("message") or {}
                content = message.get("content")
                if content:
                    return str(content).strip()
    except Exception:
        pass

    try:
        # Try dict conversion if supported
        data = completion  # type: ignore[assignment]
        if hasattr(completion, "model_dump"):
            data = completion.model_dump()  # type: ignore[assignment]
        if isinstance(data, dict):
            choices = data.get("choices") or []
            if choices:
                first = choices[0]
                message = first.get("message") or {}
                content = message.get("content")
                if content:
                    return str(content).strip()
    except Exception:
        pass

    return None


def _clean_ocr_to_query(ocr_text: str) -> Optional[str]:
    """
    Converts OCR text into a conservative query string.
    """

    if not ocr_text:
        return None
    s = ocr_text.strip()
    # Remove obvious noisy fragments
    s = re.sub(r"https?://\\S+", "", s, flags=re.IGNORECASE)
    s = " ".join(s.split())

    # Keep a reasonable size (avoid returning a whole receipt/manual).
    if not s or len(s) > 80:
        return None

    # Drop very short junk
    if len(s) < 6:
        return None

    return s


def _is_generic_or_invalid_query(product_query: str) -> bool:
    q = (product_query or "").strip()
    if not q:
        return True

    q_l = q.lower().strip()
    generic = {
        "produto",
        "produtо",  # common OCR typo variant
        "nao sei",
        "não sei",
        "indefinido",
        "indisponivel",
        "indisponível",
        "desconhecido",
        "unknown",
        "n/a",
        "nao_sei",
        "nao-identificado",
        "nao identificado",
        "nao identificado",
    }
    if q_l in generic:
        return True

    # Too short -> likely not useful for search.
    # Allow short but informative strings with digits (e.g., "S23", "256GB").
    words = [w for w in re.split(r"\\W+", q_l) if w]
    has_digits = any(ch.isdigit() for ch in q_l)
    if len(words) < 2 and not has_digits:
        return True
    if len(q_l) < 6 and not has_digits:
        return True

    return False

