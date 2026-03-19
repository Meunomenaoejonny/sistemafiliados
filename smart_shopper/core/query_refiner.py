from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from core.providers.llm.router import LLMRouter


@dataclass(frozen=True)
class QueryRefineResult:
    primary: str
    alternatives: list[str]
    provider_name: str = "deterministic"
    error: Optional[str] = None


def _normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def deterministic_refine(query: str) -> QueryRefineResult:
    """
    Refinamento gratuito (sem IA): melhora legibilidade e gera 2-3 variantes.
    """
    q = _normalize_space(query)
    if not q:
        return QueryRefineResult(primary=query, alternatives=[], provider_name="deterministic")

    # Remove URLs e trackers simples
    q2 = re.sub(r"https?://\\S+", "", q, flags=re.IGNORECASE).strip()
    q2 = _normalize_space(q2) or q

    # Normaliza capacidade comum: "256 gb" -> "256GB"
    q3 = re.sub(r"\\b(\\d{2,4})\\s*gb\\b", r"\\1GB", q2, flags=re.IGNORECASE)
    q3 = re.sub(r"\\b(\\d{1,3})\\s*tb\\b", r"\\1TB", q3, flags=re.IGNORECASE)
    q3 = _normalize_space(q3)

    alts: list[str] = []
    if q3 != q2:
        alts.append(q3)

    # Variante "clean" sem palavras comuns
    q_clean = re.sub(r"\\b(original|oficial|promo[cç][aã]o|barato|novo|lacrado)\\b", "", q3, flags=re.IGNORECASE)
    q_clean = _normalize_space(q_clean)
    if q_clean and q_clean != q3:
        alts.append(q_clean)

    # Variante com "modelo" destacado
    alts2 = []
    if re.search(r"\\b(pro|max|ultra|plus|mini)\\b", q3, flags=re.IGNORECASE):
        alts2.append(q3)
    if alts2:
        for a in alts2:
            if a not in alts:
                alts.append(a)

    # Limit to 3 unique alternatives
    uniq: list[str] = []
    for a in alts:
        if a and a not in uniq and a.lower() != q2.lower():
            uniq.append(a)
        if len(uniq) >= 3:
            break

    return QueryRefineResult(primary=q2, alternatives=uniq, provider_name="deterministic")


def refine_with_llm(query: str, router: Optional[LLMRouter]) -> QueryRefineResult:
    if not router:
        return deterministic_refine(query)

    base = _normalize_space(query)
    if not base:
        return QueryRefineResult(primary=query, alternatives=[])

    prompt = (
        "Você é um especialista em busca de e-commerce. Dado um termo de produto, gere 3 variações curtas "
        "para melhorar a busca (sinônimos, normalização de capacidade/modelo), sem inventar especificações.\n\n"
        f"TERMO:\n{base}\n\n"
        "Saída obrigatória em JSON estrito no formato:\n"
        "{\"primary\": \"...\", \"alternatives\": [\"...\", \"...\", \"...\"]}\n"
        "Regras: retorne SOMENTE o JSON (sem markdown, sem texto extra). "
        "NÃO altere o nome do modelo: se o usuário escreveu A1, mantenha A1 (não troque por A1 Mini). "
        "Se escreveu A1 Mini, mantenha A1 Mini. Não adicione Mini, Pro, Max etc. se o termo não tiver. "
        "NÃO troque a categoria do produto: se o termo contém 'fone/headphone/earbuds', não transforme em celular."
    )

    try:
        res = router.complete_text(prompt=prompt, temperature=0.1, max_tokens=220)
        text = res.text
    except Exception as e:  # noqa: BLE001
        return QueryRefineResult(
            primary=_normalize_space(query) or query,
            alternatives=[],
            provider_name="deterministic (LLM error)",
            error=str(e),
        )

    # Best-effort JSON parsing (avoid new dependency)
    import json

    raw = (text or "").strip()
    # Remove common markdown fences.
    cleaned = raw.replace("```json", "```").replace("```", "").strip()

    try:
        obj = json.loads(cleaned)
        primary = _normalize_space(str(obj.get("primary", base)))
        alternatives_raw = obj.get("alternatives") or []
        alternatives = []
        for a in alternatives_raw:
            a_s = _normalize_space(str(a))
            if a_s and a_s.lower() != primary.lower() and a_s not in alternatives:
                alternatives.append(a_s)
            if len(alternatives) >= 3:
                break
        return QueryRefineResult(primary=primary or base, alternatives=alternatives, provider_name=res.provider_name)
    except Exception:
        # If the model added text around the JSON, try extracting the first {...} block.
        try:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                obj = json.loads(cleaned[start : end + 1])
                primary = _normalize_space(str(obj.get("primary", base)))
                alternatives_raw = obj.get("alternatives") or []
                alternatives = []
                for a in alternatives_raw:
                    a_s = _normalize_space(str(a))
                    if a_s and a_s.lower() != primary.lower() and a_s not in alternatives:
                        alternatives.append(a_s)
                    if len(alternatives) >= 3:
                        break
                return QueryRefineResult(
                    primary=primary or base,
                    alternatives=alternatives,
                    provider_name=res.provider_name,
                )
        except Exception:
            pass

        return QueryRefineResult(
            primary=_normalize_space(query) or query,
            alternatives=[],
            provider_name="deterministic (json parse failed)",
            error=f"JSON inválido retornado pelo LLM: {raw[:120]}",
        )

