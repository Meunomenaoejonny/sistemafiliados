from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


@dataclass(frozen=True)
class AffiliateConfig:
    amazon_tag: str = ""
    aliexpress_admitad_campaign_code: str = ""


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

