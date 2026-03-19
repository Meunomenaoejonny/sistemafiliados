"""
MarketIntelligence: motor de busca/match no catálogo de top vendidos.
Centraliza toda a lógica de:
  - detecção de categoria
  - match de produto
  - geração de contexto de mercado (markdown)
  - sugestão de faixa de preço
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from core.market.catalog import ALL_PRODUCTS, TopProduct
from core.market.models import MarketMatchResult
from core.market.learning_store import get_learned_context_md, get_learned_price_range


# ─── Normalização ─────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()

def _marker_in_query(q_norm: str, marker: str) -> bool:
    """
    Match robusto para marcador:
    - marcador com espaço: exige substring exata (ex.: "redmi note")
    - marcador de 1 token: exige token exato (evita "fila" casar com "filamento")
    """
    m = _norm(marker)
    if not m:
        return False
    if " " in m:
        return m in q_norm
    q_tokens = set(re.findall(r"[a-z]+|[0-9]+", q_norm))
    return m in q_tokens


# ─── Detecção de categoria ────────────────────────────────────────────────────

_CATEGORY_MARKERS: dict[str, list[str]] = {
    "smartphone": [
        "iphone", "samsung galaxy", "galaxy a", "galaxy m", "galaxy s",
        "redmi", "xiaomi", "poco", "motorola", "moto", "realme", "oppo",
        "oneplus", "pixel", "huawei", "honor", "tecno", "infinix", "nokia",
        "itel", "celular", "smartphone",
    ],
    "tv": [
        "smart tv", "tv 4k", "qled", "oled", "nanocell", "tcl tv", "lg tv",
        "samsung tv", "televisao", "televisor", "tv 50", "tv 55", "tv 65",
    ],
    "notebook": [
        "notebook", "laptop", "ideapad", "inspiron", "aspire", "galaxy book",
        "macbook", "vivobook", "zenbook", "thinkpad", "chromebook", "lenovo",
        "dell", "acer", "asus", "hp", "samsung book",
    ],
    "audio": [
        "fone", "headphone", "earphone", "earbuds", "airpods", "buds",
        "jbl", "sony wh", "sony wf", "galaxy buds", "quantum", "tune ",
        "wave buds", "endurance peak",
    ],
    "games": [
        "ps5", "playstation", "xbox", "nintendo switch", "switch oled",
        "switch 2", "console", "game", "series s", "series x",
    ],
    "sneaker": [
        "tenis", "air jordan", "jordan", "air force", "air max", "dunk",
        "ultraboost", "ultra boost", "nike", "adidas", "olympikus",
        "mizuno", "fila", "sneaker", "hoka", "on running",
    ],
    "eletrodomestico": [
        "air fryer", "lavadora", "geladeira", "maquina lavar", "aspirador",
        "robo aspirador", "microondas", "fogao", "cooktop", "ventilador",
        "ar condicionado",
    ],
    "3d_printer": [
        "impressora 3d",
        "3d printer",
        "bambu lab",
        "bambu",
        "ender 3",
        "prus a",
        "prusa",
    ],
}


def detect_category(query: str) -> Optional[str]:
    q = _norm(query)
    # Marcadores de tipo (ex.: "fone") devem ter prioridade sobre marca (ex.: "redmi"),
    # para evitar classificar "fone redmi" como smartphone.
    audio_intent = {"fone", "fones", "headphone", "earphone", "earbuds", "headset", "airpods", "buds"}
    q_tokens = set(re.findall(r"[a-z]+|[0-9]+", q))
    if q_tokens & audio_intent:
        return "audio"

    for category, markers in _CATEGORY_MARKERS.items():
        if any(_marker_in_query(q, m) for m in markers):
            return category
    return None


# ─── Match de produto ─────────────────────────────────────────────────────────

# Variantes de modelo: query com "mini" deve casar com produto que tenha "mini", não com o genérico.
_MODEL_VARIANT_TOKENS = {"mini", "pro", "max", "plus", "ultra", "lite", "se"}


def match_product(query: str) -> Optional[TopProduct]:
    q = _norm(query)
    q_tokens = set(re.findall(r"[a-z]+|[0-9]+", q))
    q_variants = q_tokens & _MODEL_VARIANT_TOKENS

    best: Optional[TopProduct] = None
    best_score = 0

    for product in ALL_PRODUCTS:
        score = 0
        for tag in product.tags:
            t = _norm(tag)
            if t and _marker_in_query(q, t):
                score += len(t.split())
        if score == 0:
            continue
        # Desempate: preferir produto cuja tag cobre a query por completo (ex.: "bambu lab a1 mini" > "bambu lab a1").
        product_tag_tokens = set(re.findall(r"[a-z]+|[0-9]+", " ".join(product.tags)))
        product_variants = product_tag_tokens & _MODEL_VARIANT_TOKENS
        if q_variants and not product_variants:
            continue
        if q_variants and product_variants != q_variants:
            continue
        if score > best_score:
            best_score = score
            best = product

    return best if best_score > 0 else None


# ─── Estimativa de preço ──────────────────────────────────────────────────────

_CATEGORY_GENERIC_RANGES: dict[str, tuple[int, int]] = {
    "smartphone": (500, 3500),
    "tv": (1200, 8000),
    "notebook": (2000, 8000),
    "audio": (80, 2000),
    "games": (1200, 6500),
    "sneaker": (150, 2500),
    "eletrodomestico": (200, 4000),
    "3d_printer": (1500, 15000),
}


def estimate_price_range(query: str) -> tuple[int, int]:
    """
    Retorna (low, high) em BRL.
    Prioridade:
      1) aprendizado recente (quando houver evidência)
      2) catálogo estático (top vendidos) / categorias genéricas
    Se existir aprendizado, a faixa retornada será blendada (suave) com o catálogo.
    """
    matched = match_product(query)
    learned = get_learned_price_range(query)

    if matched and matched.price_from_brl and matched.price_to_brl:
        static_low = matched.price_from_brl
        static_high = matched.price_to_brl

        if learned:
            low_l, high_l, _ec, live_ec, _free_ec = learned
            # Só dá peso ao aprendizado quando há evidência de preço real (modo live).
            # Sem live_evidence, prioriza o catálogo estático para resposta mais precisa.
            w = min(0.7, 0.15 + (max(0, live_ec) * 0.15)) if live_ec else 0.0
            if w > 0:
                blended_low = int(static_low * (1 - w) + low_l * w)
                blended_high = int(static_high * (1 - w) + high_l * w)
                blended_low = min(blended_low, blended_high)
                return blended_low, blended_high
            return static_low, static_high

        return static_low, static_high

    if learned:
        low, high, _ec, live_ec, _free_ec = learned
        # Sem match estático: usa aprendizado. Se só tiver evidência grátis, ainda assim
        # retorna a faixa aprendida (melhor que genérico).
        return low, high

    category = detect_category(query)
    if category and category in _CATEGORY_GENERIC_RANGES:
        return _CATEGORY_GENERIC_RANGES[category]

    return 200, 3000


# ─── Contexto de mercado (markdown) ──────────────────────────────────────────

def get_market_context_md(query: str) -> Optional[str]:
    """
    Retorna bloco markdown com contexto de mercado relevante para a query.
    Retorna None se não houver contexto útil (catálogo/learn) para a query.
    """
    category = detect_category(query)
    matched = match_product(query)
    learned_md = get_learned_context_md(query)

    # Se não reconhecemos categoria e também não temos match/catálogo,
    # ainda assim podemos mostrar aprendizado recente.
    if not category and not matched and not learned_md:
        return None

    lines: list[str] = ["#### Tendência de mercado (Brasil 2025)"]

    if matched:
        badge = " 🏆 Top Vendido" if matched.rank <= 3 else ""
        lines.append(
            f"- Produto identificado entre os **mais vendidos no Brasil**: "
            f"**{matched.model}**{badge} (#{matched.rank} – {matched.source_label})."
        )
        if matched.key_specs:
            lines.append(
                f"- Características valorizadas pelos compradores: "
                f"{', '.join(matched.key_specs[:4])}."
            )
        if matched.price_from_brl and matched.price_to_brl:
            low_s = f"{matched.price_from_brl:,}".replace(",", ".")
            high_s = f"{matched.price_to_brl:,}".replace(",", ".")
            lines.append(
                f"- Faixa de preço de referência (BR): **R$ {low_s} – R$ {high_s}**."
            )
    elif category:
        cat_label = {
            "smartphone": "smartphones",
            "tv": "Smart TVs",
            "notebook": "notebooks",
            "audio": "fones/headphones",
            "games": "consoles",
            "sneaker": "tênis/sneakers",
            "eletrodomestico": "eletrodomésticos",
            "3d_printer": "impressoras 3D",
        }.get(category, category)

        top3 = sorted(
            [p for p in ALL_PRODUCTS if p.category == category],
            key=lambda p: p.rank,
        )[:3]
        if top3:
            top_names = ", ".join(p.model for p in top3)
            lines.append(
                f"- Categoria: **{cat_label}**. "
                f"Top vendidos no Brasil (2025): {top_names}."
            )

        low, high = _CATEGORY_GENERIC_RANGES.get(category, (200, 3000))
        low_s = f"{low:,}".replace(",", ".")
        high_s = f"{high:,}".replace(",", ".")
        lines.append(
            f"- Faixa típica de preço para {cat_label} no Brasil: "
            f"**R$ {low_s} – R$ {high_s}** (varia por modelo/tier)."
        )

    if learned_md:
        lines.append(learned_md)

    return "\n".join(lines)


# ─── API principal ────────────────────────────────────────────────────────────

def analyze(query: str) -> MarketMatchResult:
    """
    Ponto de entrada único para análise de mercado.
    """
    category = detect_category(query) or "desconhecido"
    matched = match_product(query)
    low, high = estimate_price_range(query)
    context_md = get_market_context_md(query) or ""

    return MarketMatchResult(
        matched=matched is not None,
        product=matched,
        category=category,
        is_top_seller=matched is not None and matched.is_top_seller,
        price_hint_low=low,
        price_hint_high=high,
        market_context_md=context_md,
    )
