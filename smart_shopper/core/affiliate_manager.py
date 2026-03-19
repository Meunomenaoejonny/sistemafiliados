from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import hashlib
import hmac
import time
from typing import Optional

import requests


# ─── Lojas suportadas ────────────────────────────────────────────────────────

ALL_STORES: list[dict] = [
    {"key": "aliexpress",    "label": "AliExpress",    "icon": "🛒", "url_tpl": "https://pt.aliexpress.com/wholesale?SearchText={q}"},
    {"key": "mercadolivre",  "label": "Mercado Livre", "icon": "🛍️",  "url_tpl": "https://lista.mercadolivre.com.br/{q}"},
    {"key": "amazon",        "label": "Amazon",        "icon": "📦", "url_tpl": "https://www.amazon.com.br/s?k={q}"},
    {"key": "shopee",        "label": "Shopee",        "icon": "🧡", "url_tpl": "https://shopee.com.br/search?keyword={q}"},
    {"key": "magalu",        "label": "Magalu",        "icon": "💛", "url_tpl": "https://www.magazineluiza.com.br/busca/{q}/"},
    {"key": "shein",         "label": "Shein",         "icon": "👗", "url_tpl": "https://www.shein.com.br/pdsearch/{q}/"},
    {"key": "kabum",         "label": "KaBuM!",        "icon": "🖥️",  "url_tpl": "https://www.kabum.com.br/busca/{q}"},
    {"key": "americanas",    "label": "Americanas",    "icon": "🔴", "url_tpl": "https://www.americanas.com.br/busca/{q}"},
    {"key": "casasbahia",    "label": "Casas Bahia",   "icon": "🏠", "url_tpl": "https://www.casasbahia.com.br/busca/{q}"},
]

def store_search_url(store_key: str, query: str) -> str:
    import urllib.parse
    enc = urllib.parse.quote(query.strip())
    for s in ALL_STORES:
        if s["key"] == store_key:
            return s["url_tpl"].format(q=enc)
    return ""


# ─── Configuração de afiliados ────────────────────────────────────────────────

@dataclass(frozen=True)
class AffiliateConfig:
    # AliExpress
    aliexpress_app_key: str = ""
    aliexpress_app_secret: str = ""
    aliexpress_tracking_id: str = ""
    aliexpress_admitad_campaign_code: str = ""
    # Amazon
    amazon_tag: str = ""
    # Mercado Livre (ML Affiliates / mlb)
    mercadolivre_affiliate_id: str = ""
    # Shopee
    shopee_affiliate_id: str = ""
    # Magalu (Lomadee ou direct)
    magalu_affiliate_id: str = ""
    # Shein (SheIn Affiliate Program)
    shein_affiliate_id: str = ""


def has_affiliate(cfg: AffiliateConfig, store_key: str) -> bool:
    """Retorna True se a loja tem chave de afiliado configurada."""
    if store_key == "aliexpress":
        return bool(
            (cfg.aliexpress_app_key and cfg.aliexpress_app_secret and cfg.aliexpress_tracking_id)
            or cfg.aliexpress_admitad_campaign_code
        )
    if store_key == "amazon":
        return bool(cfg.amazon_tag)
    if store_key == "mercadolivre":
        return bool(cfg.mercadolivre_affiliate_id)
    if store_key == "shopee":
        return bool(cfg.shopee_affiliate_id)
    if store_key == "magalu":
        return bool(cfg.magalu_affiliate_id)
    if store_key == "shein":
        return bool(cfg.shein_affiliate_id)
    return False


# ─── AliExpress deeplink ──────────────────────────────────────────────────────

def _aliexpress_official_deeplink(
    target_url: str,
    *,
    app_key: str,
    app_secret: str,
    tracking_id: str,
    promotion_link_type: int = 0,
    timeout_s: float = 12.0,
) -> Optional[str]:
    if not target_url.strip() or not app_key.strip() or not app_secret.strip() or not tracking_id.strip():
        return None

    endpoint = "https://api-sg.aliexpress.com/sync"
    ts_ms = str(int(time.time() * 1000))
    params: dict[str, str] = {
        "app_key": app_key.strip(),
        "method": "aliexpress.affiliate.link.generate",
        "timestamp": ts_ms,
        "format": "json",
        "v": "2.0",
        "sign_method": "sha256",
        "tracking_id": tracking_id.strip(),
        "source_values": target_url.strip(),
        "promotion_link_type": str(int(promotion_link_type)),
    }

    pieces: list[str] = []
    for k in sorted(params.keys()):
        pieces.append(k)
        pieces.append(str(params[k]))
    base = "".join(pieces).encode("utf-8")
    sign = hmac.new(app_secret.strip().encode("utf-8"), base, hashlib.sha256).hexdigest().upper()
    params["sign"] = sign

    try:
        resp = requests.get(endpoint, params=params, timeout=timeout_s)
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001
        return None

    root = None
    if isinstance(data, dict):
        for k in ("aliexpress_affiliate_link_generate_response", "aliexpress_ali_affiliate_link_generate_response"):
            if k in data and isinstance(data.get(k), dict):
                root = data.get(k)
                break
        if root is None:
            root = data

    def _dig(obj, keys):
        cur = obj
        for kk in keys:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(kk)
        return cur

    links = (
        _dig(root, ["resp_result", "result", "promotion_links"])
        or _dig(root, ["result", "promotion_links"])
        or _dig(root, ["promotion_links"])
    )
    if isinstance(links, list) and links:
        first = links[0]
        if isinstance(first, dict):
            for f in ("promotion_link", "promotionLink", "url", "link"):
                v = first.get(f)
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return None


# ─── UTM helpers ─────────────────────────────────────────────────────────────

def _add_utm_tracking(url: str, store_name: str) -> str:
    url = (url or "").strip()
    if not url:
        return url
    store_norm = (store_name or "").strip().lower() or "unknown_store"
    parts = urlparse(url)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q.setdefault("utm_source", "smart_shopper")
    q.setdefault("utm_medium", "afiliado")
    q.setdefault("utm_campaign", store_norm)
    new_query = urlencode(q, doseq=True)
    return urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, new_query, parts.fragment))


def _append_query_param(url: str, key: str, value: str) -> str:
    parts = urlparse(url)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q[key] = value
    new_query = urlencode(q, doseq=True)
    return urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, new_query, parts.fragment))


# ─── Conversão de link ────────────────────────────────────────────────────────

def to_affiliate_link(original_url: str, store_name: str, cfg: AffiliateConfig) -> str:
    url = (original_url or "").strip()
    store = (store_name or "").strip().lower()

    if not url:
        return original_url

    url = _add_utm_tracking(url, store_name=store_name)

    if "aliexpress" in store:
        if cfg.aliexpress_app_key and cfg.aliexpress_app_secret and cfg.aliexpress_tracking_id:
            deeplink = _aliexpress_official_deeplink(
                url,
                app_key=cfg.aliexpress_app_key,
                app_secret=cfg.aliexpress_app_secret,
                tracking_id=cfg.aliexpress_tracking_id,
            )
            if deeplink:
                return deeplink
        if cfg.aliexpress_admitad_campaign_code:
            import urllib.parse
            ulp = urllib.parse.quote(url, safe="")
            return f"https://ad.admitad.com/g/{cfg.aliexpress_admitad_campaign_code}/?ulp={ulp}"
        return url

    if "amazon" in store:
        if cfg.amazon_tag:
            return _append_query_param(url, "tag", cfg.amazon_tag)
        return url

    if "mercado livre" in store or "mercadolivre" in store:
        if cfg.mercadolivre_affiliate_id:
            return _append_query_param(url, "ref", cfg.mercadolivre_affiliate_id)
        return url

    if "shopee" in store:
        if cfg.shopee_affiliate_id:
            return _append_query_param(url, "af_id", cfg.shopee_affiliate_id)
        return url

    if "magalu" in store or "magazine" in store:
        if cfg.magalu_affiliate_id:
            return _append_query_param(url, "partner_id", cfg.magalu_affiliate_id)
        return url

    if "shein" in store:
        if cfg.shein_affiliate_id:
            return _append_query_param(url, "aff_id", cfg.shein_affiliate_id)
        return url

    return url
