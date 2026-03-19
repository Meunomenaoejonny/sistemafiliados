"""
PriceEstimator: estimativa de faixa de preço centralizada.
Substitui a heurística espalhada no search_engine.py.
Usa MarketIntelligence como fonte primária; fallback para regras de categoria.
"""
from __future__ import annotations

from core.market.intelligence import analyze


def estimate_brl_range(query: str) -> tuple[int, int]:
    """
    Retorna (low, high) em BRL para o modo free (sem SerpApi).
    """
    result = analyze(query)
    return result.price_hint_low or 200, result.price_hint_high or 3000


def brl_label(low: int, high: int) -> str:
    s_low = f"{low:,}".replace(",", ".")
    s_high = f"{high:,}".replace(",", ".")
    return f"Estimativa: R$ {s_low} - {s_high}"
