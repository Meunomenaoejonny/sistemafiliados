from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


_STORE_VERSION = 1


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def _workspace_root() -> Path:
    # smart_shopper/core/market/learning_store.py -> smart_shopper/
    return Path(__file__).resolve().parents[2]


def _store_path() -> Path:
    root = _workspace_root()
    data_dir = root / ".data"
    return data_dir / "market_learning.json"


@dataclass
class LearnedPrice:
    low: int
    high: int
    evidence_count: int
    updated_at: float


def _safe_parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text or "{}")
    except Exception:
        return {}


def _load_store() -> dict[str, Any]:
    path = _store_path()
    try:
        if not path.exists():
            return {"version": _STORE_VERSION, "entries": []}
        raw = path.read_text(encoding="utf-8")
        store = _safe_parse_json(raw)
        if not isinstance(store, dict):
            return {"version": _STORE_VERSION, "entries": []}
        if store.get("version") != _STORE_VERSION:
            return {"version": _STORE_VERSION, "entries": []}
        if not isinstance(store.get("entries"), list):
            store["entries"] = []
        return store
    except Exception:
        return {"version": _STORE_VERSION, "entries": []}


def _save_store(store: dict[str, Any]) -> None:
    path = _store_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # Aprendizado é incremental: falha não deve quebrar o app.
        return


def _extract_brl_range_from_label(price_label: Optional[str]) -> Optional[tuple[int, int]]:
    """
    Ex.: "Estimativa: R$ 200 - 3.000" ou "R$ 200 - 3.000".
    """
    if not price_label:
        return None
    s = price_label.strip()
    s = s.replace(".", "").replace("R$", "").replace("estimativa", "")
    m = re.search(r"(\d+)\s*-\s*(\d+)", s)
    if not m:
        return None
    low = int(m.group(1))
    high = int(m.group(2))
    if low <= 0 or high <= 0 or high < low:
        return None
    return low, high


def _observed_price_range_from_cards(query: str, cards: list[Any], live_mode: bool) -> Optional[tuple[int, int]]:
    """
    cards: lista de OfferCard (duck-typing).
    """
    observed_low: Optional[int] = None
    observed_high: Optional[int] = None

    for c in cards or []:
        try:
            if live_mode and getattr(c, "is_live_price", False):
                price = getattr(c, "price", None)
                currency = getattr(c, "currency", None)
                if price is None or not currency or str(currency).upper() != "BRL":
                    continue
                p = int(round(float(price)))
                observed_low = p if observed_low is None else min(observed_low, p)
                observed_high = p if observed_high is None else max(observed_high, p)
            else:
                # Também aprende com estimativa rotulada (melhora faixa para queries semelhantes).
                pl = getattr(c, "price_label", None)
                rng = _extract_brl_range_from_label(pl)
                if rng:
                    low, high = rng
                    observed_low = low if observed_low is None else min(observed_low, low)
                    observed_high = high if observed_high is None else max(observed_high, high)
        except Exception:
            continue

    if observed_low is None or observed_high is None:
        return None
    return observed_low, observed_high


def _find_best_entry(store: dict[str, Any], alias_norm: str) -> Optional[dict[str, Any]]:
    entries = store.get("entries") or []
    if not entries:
        return None

    def _tokens(s: str) -> set[str]:
        # Separa letras e números: "redmi15" -> {"redmi", "15"}
        parts = re.findall(r"[a-z]+|[0-9]+", s or "")
        return {p for p in parts if len(p) >= 2}

    alias_tokens = _tokens(alias_norm)

    # 1) Match exato do alias normalizado
    for e in entries:
        if e.get("alias_norm") == alias_norm:
            return e

    # Tokens que indicam variante de modelo: não normalizar "A1 mini" -> "A1".
    MODEL_SPECIFIC = {"mini", "pro", "max", "plus", "ultra", "lite", "se"}
    query_specific = alias_tokens & MODEL_SPECIFIC

    # 2) Match substring (quando o usuário varia a escrita)
    best: Optional[dict[str, Any]] = None
    best_score = 0
    for e in entries:
        a = str(e.get("alias_norm") or "")
        if not a:
            continue
        tokens_e = set(e.get("tokens") or []) if isinstance(e.get("tokens"), list) else _tokens(a)
        entry_specific = tokens_e & MODEL_SPECIFIC
        # Se a query tem variante (ex: mini) e a entrada não, não usar essa entrada.
        if query_specific and not entry_specific:
            continue
        overlap = len(alias_tokens.intersection(tokens_e))

        score = 0
        if a in alias_norm or alias_norm in a:
            score = len(a) + overlap * 10
        elif overlap >= 2:
            score = overlap * 25

        if score > best_score:
            best_score = score
            best = e

    return best if best_score > 0 else None


def learn_from_search(
    query: str,
    *,
    cards: list[Any],
    live_mode: bool,
    category: Optional[str] = None,
    matched_static_model: Optional[str] = None,
) -> None:
    """
    Atualiza um "catálogo aprendido" local (JSON) com:
      - alias normalizado (query)
      - modelo canônico (se existir match estático)
      - faixa observada (dos cards)
    """
    alias_norm = _norm(query)
    if not alias_norm or len(alias_norm) < 3:
        return

    tokens = re.findall(r"[a-z]+|[0-9]+", alias_norm)
    tokens = [t for t in tokens if len(t) >= 2]

    store = _load_store()
    if not store.get("entries"):
        store["entries"] = []

    entry = _find_best_entry(store, alias_norm)
    if entry is None:
        entry = {
            "alias_norm": alias_norm,
            "canonical_model": (matched_static_model or query).strip(),
            "category": category or "desconhecido",
            "price_low": None,
            "price_high": None,
            "evidence_count": 0,
            "live_evidence_count": 0,
            "free_evidence_count": 0,
            "updated_at": time.time(),
            "tokens": tokens,
        }
        store["entries"].append(entry)
    else:
        # Mantém tokens atuais (em caso de re-aprendizado com query semelhante).
        if isinstance(entry.get("tokens"), list):
            entry["tokens"] = list(sorted(set(entry["tokens"] + tokens)))

    entry["canonical_model"] = (matched_static_model or entry.get("canonical_model") or query).strip()
    if category:
        entry["category"] = category
    entry["updated_at"] = time.time()

    obs_rng = _observed_price_range_from_cards(query, cards=cards, live_mode=live_mode)
    if obs_rng:
        obs_low, obs_high = obs_rng
        old_low = entry.get("price_low")
        old_high = entry.get("price_high")

        if isinstance(old_low, int) and isinstance(old_high, int) and old_low > 0 and old_high > 0:
            # Atualização suave (evita oscilações grandes).
            new_low = int(old_low * 0.6 + obs_low * 0.4)
            new_high = int(old_high * 0.6 + obs_high * 0.4)
            entry["price_low"] = min(new_low, new_high)
            entry["price_high"] = max(new_low, new_high)
        else:
            entry["price_low"] = obs_low
            entry["price_high"] = obs_high

    entry["evidence_count"] = int(entry.get("evidence_count") or 0) + 1

    # Se conseguiu extrair faixa observada, isso conta como evidência.
    if obs_rng:
        if live_mode:
            entry["live_evidence_count"] = int(entry.get("live_evidence_count") or 0) + 1
        else:
            entry["free_evidence_count"] = int(entry.get("free_evidence_count") or 0) + 1
    _save_store(store)


def get_learned_price_range(query: str) -> Optional[tuple[int, int, int, int, int]]:
    """
    Retorna (low, high, evidence_count, live_evidence_count, free_evidence_count) ou None.
    """
    alias_norm = _norm(query)
    if not alias_norm:
        return None
    store = _load_store()
    entry = _find_best_entry(store, alias_norm)
    if not entry:
        return None
    low = entry.get("price_low")
    high = entry.get("price_high")
    if not isinstance(low, int) or not isinstance(high, int) or low <= 0 or high <= 0 or high < low:
        return None
    evidence_count = int(entry.get("evidence_count") or 0)
    live_evidence_count = int(entry.get("live_evidence_count") or 0)
    free_evidence_count = int(entry.get("free_evidence_count") or 0)
    return low, high, evidence_count, live_evidence_count, free_evidence_count


def get_learned_context_md(query: str) -> Optional[str]:
    alias_norm = _norm(query)
    if not alias_norm:
        return None
    store = _load_store()
    entry = _find_best_entry(store, alias_norm)
    if not entry:
        return None
    low = entry.get("price_low")
    high = entry.get("price_high")
    evidence_count = int(entry.get("evidence_count") or 0)
    model = entry.get("canonical_model") or query

    if isinstance(low, int) and isinstance(high, int) and low > 0 and high > 0 and high >= low:
        low_s = f"{low:,}".replace(",", ".")
        high_s = f"{high:,}".replace(",", ".")
        return "\n".join(
            [
                "#### Aprendizado recente (do uso)",
                f"- Para **{alias_norm}**, o sistema já observou esta faixa: **R$ {low_s} – R$ {high_s}**.",
                f"- Evidências acumuladas: **{evidence_count}**.",
                f"- Modelo canônico: **{model}**.",
            ]
        )

    # Sem faixa, ainda mostramos que o sistema reconheceu a query.
    return "\n".join(
        [
            "#### Aprendizado recente (do uso)",
            f"- Para **{alias_norm}**, o sistema reconheceu o modelo: **{model}**.",
            f"- Evidências acumuladas: **{evidence_count}**.",
        ]
    )


def get_learned_canonical_model(query: str) -> Optional[str]:
    """
    Retorna o "modelo canônico" aprendido para esta query (se existir).
    """
    alias_norm = _norm(query)
    if not alias_norm:
        return None
    store = _load_store()
    entry = _find_best_entry(store, alias_norm)
    if not entry:
        return None
    canonical_model = entry.get("canonical_model")
    if not isinstance(canonical_model, str) or not canonical_model.strip():
        return None
    return canonical_model.strip()


def normalize_query_with_learning(query: str) -> Optional[str]:
    """
    Normaliza a query com base no aprendizado local.
    Não retorna canonical que remova variante (mini/pro/...) — ex.: "a1 mini" não vira "A1".
    """
    canonical = get_learned_canonical_model(query)
    if not canonical:
        return None
    if _norm(canonical) == _norm(query):
        return None
    # Não normalizar para um modelo que perde variante (ex.: a1 mini -> A1 seria errado).
    q_tokens = set(re.findall(r"[a-z]+|[0-9]+", _norm(query)))
    can_tokens = set(re.findall(r"[a-z]+|[0-9]+", _norm(canonical)))
    variant = {"mini", "pro", "max", "plus", "ultra", "lite", "se"}
    if (q_tokens & variant) and not (can_tokens & variant):
        return None
    return canonical

