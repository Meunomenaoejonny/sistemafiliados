from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PhoneTopSeller:
    model: str
    rank: int
    source_label: str
    price_from_brl_hint: Optional[int] = None
    key_specs: list[str] = None  # type: ignore[assignment]


TOP_SELLERS_ML_DEC_2025 = [
    PhoneTopSeller(
        model="Motorola Moto G15 (128 GB)",
        rank=1,
        source_label="TechTudo / Mercado Livre (dez/2025)",
        price_from_brl_hint=594,
        key_specs=[
            "4 GB de RAM",
            "Tela 6,7\" Full HD+ (até ~1000 nits)",
            "Câmera traseira 50 MP",
            "Helio G81 Extreme (2,3 GHz)",
            "Bateria 5.200 mAh",
            "NFC",
        ],
    ),
    PhoneTopSeller(
        model="Samsung Galaxy A16 4G (128 GB)",
        rank=2,
        source_label="TechTudo / Mercado Livre (dez/2025)",
        price_from_brl_hint=785,
        key_specs=[
            "Câmera traseira 50 MP",
            "NFC",
            "4 GB de RAM",
            "MediaTek Helio G99 (2,0 GHz)",
            "Bateria 5.000 mAh",
            "Tela AMOLED Full HD+",
        ],
    ),
    PhoneTopSeller(
        model="Motorola Moto G05 (256 GB)",
        rank=3,
        source_label="TechTudo / Mercado Livre (dez/2025)",
        price_from_brl_hint=719,
        key_specs=[
            "Helio G81 (2,0 GHz)",
            "4 GB de RAM",
            "Câmera traseira 50 MP",
            "Bateria 5.200 mAh (até ~40h uso moderado)",
        ],
    ),
    PhoneTopSeller(
        model="Xiaomi Redmi 15C (256 GB)",
        rank=4,
        source_label="TechTudo / Mercado Livre (dez/2025)",
        price_from_brl_hint=850,
        key_specs=[
            "Bateria 6.000 mAh",
            "Câmera traseira 50 MP",
        ],
    ),
    PhoneTopSeller(
        model="Samsung Galaxy A07 (256 GB)",
        rank=5,
        source_label="TechTudo / Mercado Livre (dez/2025)",
        price_from_brl_hint=867,
        key_specs=[
            "8 GB de RAM",
            "Câmera traseira 50 MP",
            "Processador MediaTek (Helio G99)",
            "Tela 6,7\" HD+ (90 Hz)",
            "Bateria 5.000 mAh",
            "Sem NFC (em algumas versões)",
        ],
    ),
    PhoneTopSeller(
        model="Motorola Moto G35 (128 GB)",
        rank=6,
        source_label="TechTudo / Mercado Livre (dez/2025)",
        price_from_brl_hint=750,
        key_specs=[
            "4 GB de RAM (RAM Boost até 12 GB)",
            "Câmera traseira 50 MP",
            "Câmera frontal 16 MP",
            "NFC",
            "Processador (linha Moto G)",
            "Bateria 5.000 mAh",
        ],
    ),
    PhoneTopSeller(
        model="Samsung Galaxy A56 5G (128 GB)",
        rank=7,
        source_label="TechTudo / Mercado Livre (dez/2025)",
        price_from_brl_hint=1821,
        key_specs=[
            "Tela Super AMOLED 6,7\" (120 Hz)",
            "8 GB de RAM",
            "Exynos (linha A56 5G)",
            "Câmera principal 50 MP (OIS)",
            "Ultrawide 12 MP + macro 5 MP",
            "Bateria 5.000 mAh",
        ],
    ),
]


def _is_phone_query(product_query: str) -> bool:
    q = (product_query or "").lower()
    phone_markers = [
        "celular",
        "smartphone",
        "iphone",
        "samsung galaxy",
        "galaxy a",
        "galaxy m",
        "galaxy s",
        "redmi",
        "xiaomi",
        "poco",
        "motorola",
        "moto",
        "realme",
        "oppo",
        "oneplus",
        "pixel",
        "huawei",
        "honor",
        "tecno",
        "infinix",
        "nokia",
        "itel",
    ]
    return any(m in q for m in phone_markers)


def _normalize_for_match(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return " ".join(s.split())


def _match_top_seller(product_query: str) -> Optional[PhoneTopSeller]:
    q = _normalize_for_match(product_query)
    for item in TOP_SELLERS_ML_DEC_2025:
        model_norm = _normalize_for_match(item.model)
        # Match if query contains core brand/model terms.
        # Example: "Redmi 15" matches "redmi 15c".
        if any(token and token in q for token in model_norm.split(" ")):
            if "redmi 15c" in model_norm and "redmi 15" in q:
                return item
            if "moto g15" in model_norm and "g15" in q:
                return item
            if "a16" in model_norm and "a16" in q:
                return item
            if "a07" in model_norm and "a07" in q:
                return item
            if "g35" in model_norm and "g35" in q:
                return item
            if "a56" in model_norm and "a56" in q:
                return item

    return None


def match_phone_top_seller(product_query: str) -> Optional[PhoneTopSeller]:
    """
    API pública para usar na heuristica de estimativa (modo free).
    """
    return _match_top_seller(product_query)


def get_phone_market_context_markdown(product_query: str) -> Optional[str]:
    """
    Retorna uma seção markdown com contexto de mercado (top vendidos no Brasil).
    """
    if not _is_phone_query(product_query):
        return None

    matched = _match_top_seller(product_query)

    top_models = ", ".join([i.model.split(" (")[0] for i in sorted(TOP_SELLERS_ML_DEC_2025, key=lambda x: x.rank)])
    source = TOP_SELLERS_ML_DEC_2025[0].source_label

    lines: list[str] = []
    lines.append(f"#### Tendencia de mercado (Brasil)")
    if matched:
        lines.append(
            f"- O modelo mais proximo do seu termo aparece entre os mais vendidos no Mercado Livre: **{matched.model}**."
        )
        if matched.key_specs:
            lines.append(f"- Caracteristicas frequentemente valorizadas: {', '.join(matched.key_specs[:3])}.")
    else:
        lines.append(
            f"- No Brasil, modelos de entrada/intermediarios dominam: **{top_models}**. (Referencia: {source})"
        )
        lines.append(
            "- Em geral, esses aparelhos entregam bom custo-beneficio priorizando bateria (alto mAh), camera de 50 MP (em muitos modelos) e conectividade basica/5G em versões selecionadas."
        )

    return "\n".join(lines)

