from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.models.offer_card import OfferCard
from core.providers.llm.llm_provider_factory import build_llm_router
from core.market.intelligence import get_market_context_md


@dataclass(frozen=True)
class ProductAnalysisResult:
    markdown: str
    provider_name: str  # "deterministic" | "groq" | "gemini" | "hf" | "deterministic (llm error)"


def _deterministic_analysis(product_query: str, cards: list[OfferCard]) -> str:
    if not product_query:
        product_query = "produto"

    if not cards:
        return "Não foi possível gerar uma análise porque nenhuma oferta foi retornada."

    live_cards = [c for c in cards if c.is_live_price]
    top = cards[0]
    mode_desc = (
        "com preços ao vivo (modo SerpApi)"
        if live_cards
        else "em modo gratuito (sem preços ao vivo)"
    )

    top_why = (top.metadata or {}).get("why_this") if top.metadata else None
    top_savings = (top.metadata or {}).get("potential_savings_label") if top.metadata else None
    top_reason = top_why or "por apresentar bom custo-benefício dentro das ofertas retornadas."

    if live_cards:
        savings_line = f"\n- {top_savings}" if top_savings else ""
    else:
        savings_line = "\n- Exibimos apenas links e uma faixa estimada (rotulada) para orientar a decisão."

    reasons_lines = []
    for c in cards[:3]:
        why = (c.metadata or {}).get("why_this") if c.metadata else None
        price_label = c.price_label
        if c.is_live_price and price_label:
            reasons_lines.append(f"- **{c.store}**: {why or 'oferta selecionada'}")
        elif not c.is_live_price and price_label:
            reasons_lines.append(f"- **{c.store}**: {price_label} ({why or 'estimativa e link de busca'})")
        else:
            reasons_lines.append(f"- **{c.store}**: {why or 'oferta selecionada'}")

    md = [
        f"### Análise da pesquisa ({mode_desc})",
        f"**Produto/termo:** {product_query}",
        "",
        "#### Melhor custo-benefício",
        f"- **{top.title}** na **{top.store}**",
        f"- Por quê: {top_reason}{savings_line}",
        "",
        # Contexto de mercado multi-categoria
        get_market_context_md(product_query) or "",
        "",
        "#### Como interpretamos os cards",
        "A IA normaliza o termo, busca ofertas e aplica um score de valor combinando preço e (quando disponível) reputação (rating/reviews).",
        "",
        "#### Justificativa por loja",
        *reasons_lines,
        "",
        "Nota: preços podem variar e o link afiliado deve ser usado no momento da compra. Quando o app estiver em modo gratuito, tratamos preços apenas como estimativa rotulada.",
    ]
    return "\n".join(md)


def build_product_analysis_result(
    product_query: str,
    cards: list[OfferCard],
    *,
    gemini_api_key: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    hf_token: Optional[str] = None,
) -> ProductAnalysisResult:
    base = _deterministic_analysis(product_query, cards)

    router = build_llm_router(
        groq_api_key=groq_api_key or "",
        gemini_api_key=gemini_api_key or "",
        hf_token=hf_token or "",
        prefer=["groq", "gemini", "hf"],
    )
    if not router:
        return ProductAnalysisResult(markdown=base, provider_name="deterministic")

    try:
        prompt = (
            "Você é um assistente de e-commerce. Reescreva a análise abaixo de forma profissional, "
            "mantendo as mesmas conclusoes e avisos. Saída em markdown, curta e objetiva.\n\n"
            f"ANALISE_DE_BASE:\n{base}\n\n"
            "Regras: não invente dados (preço/rating). Se houver modo gratuito sem preço ao vivo, "
            "mantenha o aviso explicitamente."
        )
        res = router.complete_text(prompt=prompt, temperature=0.2, max_tokens=420)
        text = res.text
        if text and text.strip():
            return ProductAnalysisResult(markdown=text.strip(), provider_name=res.provider_name)
    except Exception:
        pass

    return ProductAnalysisResult(markdown=base, provider_name="deterministic (llm error)")


def build_product_analysis(
    product_query: str,
    cards: list[OfferCard],
    *,
    gemini_api_key: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    hf_token: Optional[str] = None,
) -> str:
    """
    Gera um resumo explicável do resultado.

    - Primeiro gera uma explicação determinística (sempre).
    - Se existir alguma IA configurada (Groq/Gemini/HF), tentamos refinar com LLM mantendo o mesmo conteúdo/legibilidade.
    """
    return build_product_analysis_result(
        product_query,
        cards,
        gemini_api_key=gemini_api_key,
        groq_api_key=groq_api_key,
        hf_token=hf_token,
    ).markdown

