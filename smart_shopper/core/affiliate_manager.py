from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import hashlib
import hmac
import time
from typing import Optional

import requests


@dataclass(frozen=True)
class AffiliateConfig:
    amazon_tag: str = ""
    aliexpress_admitad_campaign_code: str = ""
    aliexpress_app_key: str = ""
    aliexpress_app_secret: str = ""
    aliexpress_tracking_id: str = ""


def _aliexpress_official_deeplink(
    target_url: str,
    *,
    app_key: str,
    app_secret: str,
    tracking_id: str,
    promotion_link_type: int = 0,
    timeout_s: float = 12.0,
) -> Optional[str]:
    """
    Gera deeplink de afiliado via AliExpress Open Platform (oficial).
    Método: aliexpress.affiliate.link.generate

    Retorna a URL de afiliado (promotion_link) ou None em falha.
    """
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

    # Assinatura: HMAC-SHA256(secret, concat(keys+values ordenados)) em hex upper
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

    # Estruturas variam: tentamos os caminhos mais comuns.
    # Ex: {"aliexpress_affiliate_link_generate_response": {"resp_result": {"result": {"promotion_links": [...]}}}}
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
            for field in ("promotion_link", "promotionLink", "url", "link"):
                v = first.get(field)
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return None


def _add_utm_tracking(url: str, store_name: str) -> str:
    """
    Adiciona UTMs para ajudar no tracking/attribution.

    Não substitui o tracking nativo dos programas de afiliados, mas melhora a medição
    quando os provedores suportam UTM ou quando você usa redirect/analytics próprios.
    """
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


def to_affiliate_link(original_url: str, store_name: str, cfg: AffiliateConfig) -> str:
    """
    Converte um link "normal" em link de afiliado.

    Preencha seus IDs no Streamlit Secrets e passe para `AffiliateConfig`.

    Exemplos:
    - Amazon: adiciona `tag=<AMAZON_TAG>` como query param.
    - AliExpress (Admitad): estrutura preparada para deep link por campaign code.
      Ajuste o formato conforme seu provedor/conta (Admitad, AWIN, Impact, etc).
    """
    url = (original_url or "").strip()
    store = (store_name or "").strip().lower()

    if not url:
        return original_url

    # Primeiro adicionamos UTMs (não quebra os links e ajuda na atribuição).
    url = _add_utm_tracking(url, store_name=store_name)

    if "amazon" in store:
        if cfg.amazon_tag:
            return _append_query_param(url, "tag", cfg.amazon_tag)
        return url

    if "aliexpress" in store:
        # 1) Oficial (AliExpress Affiliate API)
        if cfg.aliexpress_app_key and cfg.aliexpress_app_secret and cfg.aliexpress_tracking_id:
            deeplink = _aliexpress_official_deeplink(
                url,
                app_key=cfg.aliexpress_app_key,
                app_secret=cfg.aliexpress_app_secret,
                tracking_id=cfg.aliexpress_tracking_id,
            )
            if deeplink:
                return deeplink

        # 2) Fallback: Admitad (se existir)
        if cfg.aliexpress_admitad_campaign_code:
            # Exemplo de wrapper típico (pode variar por conta/integração):
            # https://ad.admitad.com/g/<campaign_code>/?ulp=<URL_ENCODED>
            # Aqui mantemos simples; você pode trocar por seu formato oficial.
            import urllib.parse

            ulp = urllib.parse.quote(url, safe="")
            return f"https://ad.admitad.com/g/{cfg.aliexpress_admitad_campaign_code}/?ulp={ulp}"
        return url

    # Mercado Livre / Shopee / outras lojas:
    # Deixe preparado para futura integração (ex: parâmetros ref, utm, deeplink networks).
    return url

