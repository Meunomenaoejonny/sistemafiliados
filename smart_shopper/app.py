from __future__ import annotations

import os
import re
import sys
import time
import hashlib
from dataclasses import asdict
from typing import Optional

# Garante que "core" seja encontrado ao rodar na Streamlit Cloud (raiz = repositório).
_app_dir = os.path.dirname(os.path.abspath(__file__))
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

import streamlit as st

from core.affiliate_manager import AffiliateConfig
from core.orchestrator import OrchestratorError
from core.analysis.product_analysis import build_product_analysis_result
from core.orchestrator_factory import build_orchestrator
from core.providers.llm.llm_provider_factory import build_llm_router
from core.query_refiner import refine_with_llm
from core.market.intelligence import analyze as market_analyze
from core.market.learning_store import learn_from_search
from core.market.learning_store import normalize_query_with_learning


APP_TITLE = "Smart Shopper Afiliado"


def _is_url(text: str) -> bool:
    t = (text or "").strip()
    return bool(re.match(r"^https?://", t, flags=re.IGNORECASE))


def _safe_get_secret(key: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(key, default) or default)
    except Exception:  # noqa: BLE001
        return str(os.environ.get(key, default) or default)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _format_price(price: Optional[float], currency: Optional[str]) -> Optional[str]:
    if price is None or not currency:
        return None

    cur = currency.strip().upper()
    if cur == "BRL":
        s = f"{price:,.2f}"  # 1,234.56
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")  # 1.234,56
        return f"R$ {s}"

    # Default: keep a generic formatting
    return f"{cur} {price:,.2f}"


def _strip_estimativa_prefix(price_label: Optional[str]) -> Optional[str]:
    if not price_label:
        return None
    # Ex: "Estimativa: R$ 2.500 - 9.000" -> "R$ 2.500 - 9.000"
    s = price_label.strip()
    if s.lower().startswith("estimativa:"):
        return s.split(":", 1)[1].strip()
    return s


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🛒", layout="wide")

    # Ajustes de estado só antes de o widget existir (evita StreamlitAPIException).
    if st.session_state.pop("_clear_cache_pending_input", False):
        st.session_state["product_search_input"] = ""
        st.rerun()
    # Após uma busca, sincronizar o campo com a query final usada (evita refiner_input desatualizado).
    sync_value = st.session_state.pop("_sync_search_input_to_query", None)
    if sync_value is not None and isinstance(sync_value, str):
        st.session_state["product_search_input"] = sync_value.strip() or ""
        st.rerun()

    st.title(APP_TITLE)
    st.caption(
        "Cole um link/descrição ou envie uma foto do produto. "
        "A IA identifica o produto (se houver imagem), buscamos os melhores preços em tempo real e "
        "geramos links de afiliado."
    )

    with st.container(border=True):
        user_text = st.text_input(
            "Descrição ou link do produto",
            placeholder="Ex: iPhone 15 Pro 256GB ou https://...",
            key="product_search_input",
        )
        uploaded = st.file_uploader("Upload de imagem (JPG/PNG)", type=["jpg", "jpeg", "png"])
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            search_clicked = st.button("Buscar Melhor Preço", type="primary", use_container_width=True)
        with col_btn2:
            clear_cache_clicked = st.button("Limpar cache e campo", use_container_width=True)

    # Estado: para permitir ações auxiliares (ex: "Registrar visita") sem precisar recomputar tudo
    st.session_state.setdefault("events", [])
    st.session_state.setdefault("vision_cache", {})
    st.session_state.setdefault("search_cache", {})
    st.session_state.setdefault("last_product_query", None)
    st.session_state.setdefault("cards", None)
    st.session_state.setdefault("analysis_cache", {})
    st.session_state.setdefault("last_search_ts", 0.0)
    st.session_state.setdefault("refinement_provider", None)
    st.session_state.setdefault("refined_query", None)
    st.session_state.setdefault("analysis_provider", None)
    st.session_state.setdefault("vision_gemini_present", None)
    st.session_state.setdefault("vision_hf_present", None)
    st.session_state.setdefault("vision_image_present", None)
    st.session_state.setdefault("vision_backend_used", None)
    st.session_state.setdefault("last_technical_error", None)
    st.session_state.setdefault("market_result", None)
    st.session_state.setdefault("learned_query_normalized", None)
    st.session_state.setdefault("refiner_input", None)

    # Limpar cache e campo: zera caches; o campo é limpo no próximo rerun (antes do widget ser criado).
    if clear_cache_clicked:
        st.session_state["vision_cache"] = {}
        st.session_state["search_cache"] = {}
        st.session_state["analysis_cache"] = {}
        st.session_state["cards"] = None
        st.session_state["last_product_query"] = None
        st.session_state["refined_query"] = None
        st.session_state["refinement_provider"] = None
        st.session_state["analysis_provider"] = None
        st.session_state["market_result"] = None
        st.session_state["learned_query_normalized"] = None
        st.session_state["refiner_input"] = None
        st.session_state["last_technical_error"] = None
        st.session_state["_clear_cache_pending_input"] = True
        st.rerun()

    # Se não houve nova busca, reutiliza os resultados anteriores (importante para tracking por botão)
    if not search_clicked:
        if not st.session_state.get("cards"):
            return

    gemini_key = _safe_get_secret("GEMINI_API_KEY")
    serpapi_key = _safe_get_secret("SERPAPI_KEY")
    hf_token = _safe_get_secret("HF_TOKEN")
    groq_key = _safe_get_secret("GROQ_API_KEY")

    st.session_state["vision_gemini_present"] = bool(gemini_key and gemini_key.strip())
    st.session_state["vision_hf_present"] = bool(hf_token and hf_token.strip())

    # Retrocompatível: se a Cloud estiver com cache parcial, evita quebrar em kwargs novos.
    try:
        affiliate_cfg = AffiliateConfig(
            amazon_tag=_safe_get_secret("AMAZON_TAG"),
            aliexpress_admitad_campaign_code=_safe_get_secret("ALIEXPRESS_ADMITAD_CAMPAIGN_CODE"),
            aliexpress_app_key=_safe_get_secret("ALIEXPRESS_APP_KEY"),
            aliexpress_app_secret=_safe_get_secret("ALIEXPRESS_APP_SECRET"),
            aliexpress_tracking_id=_safe_get_secret("ALIEXPRESS_TRACKING_ID"),
        )
    except TypeError:
        affiliate_cfg = AffiliateConfig(
            amazon_tag=_safe_get_secret("AMAZON_TAG"),
            aliexpress_admitad_campaign_code=_safe_get_secret("ALIEXPRESS_ADMITAD_CAMPAIGN_CODE"),
        )

    orchestrator = None
    vision_backend: Optional[str] = None
    live_mode: bool = False
    search_failed = False
    cards: list = []
    product_query: Optional[str] = None
    if search_clicked:
        try:
            build_result = build_orchestrator(
                affiliate_cfg=affiliate_cfg,
                image_present=uploaded is not None,
                gemini_api_key=gemini_key,
                hf_token=hf_token,
                serpapi_key=serpapi_key,
                serpapi_gl=_safe_get_secret("SERPAPI_GL", "br"),
                serpapi_hl=_safe_get_secret("SERPAPI_HL", "pt"),
            )
            orchestrator = build_result.orchestrator
            vision_backend = build_result.vision_backend
            live_mode = build_result.live_mode
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
            st.session_state["last_technical_error"] = str(e)
            st.session_state["cards"] = []
            st.session_state["last_product_query"] = None
            search_failed = True
        st.session_state["vision_image_present"] = uploaded is not None
        st.session_state["vision_backend_used"] = vision_backend

    # Rate limit (por sessão)
    now = time.time()
    if search_clicked and now - float(st.session_state.get("last_search_ts", 0.0)) < 8.0:
        st.warning("Aguarde alguns segundos antes de buscar novamente.")
        st.session_state["last_technical_error"] = "Rate limit: aguarde alguns segundos."
        st.session_state["cards"] = []
        st.session_state["last_product_query"] = None
        search_failed = True

    if search_clicked:
        if not orchestrator:
            st.error("Orquestrador não configurado.")
            st.session_state["last_technical_error"] = "Orquestrador não configurado."
            st.session_state["cards"] = []
            st.session_state["last_product_query"] = None
            search_failed = True
        # Persistir para reutilizar depois (sem recomputar)
        if not search_failed:
            st.session_state["last_search_ts"] = now
            cards = []
            product_query = None

        if not search_failed:
            with st.spinner("Analisando e buscando os melhores preços..."):
                try:
                    # 1) Identificação (com cache por sessão)
                    image_bytes = uploaded.getvalue() if uploaded is not None else None

                    if image_bytes is not None:
                        if not vision_backend:
                            st.session_state["last_technical_error"] = "Backend de visão não configurado."
                            st.session_state["cards"] = []
                            st.session_state["last_product_query"] = None
                            search_failed = True
                            raise OrchestratorError("Backend de visão não configurado para a imagem.")
                        image_hash = _sha256_hex(image_bytes)
                        vision_cache_key = (vision_backend, image_hash)
                        if vision_cache_key in st.session_state["vision_cache"]:
                            product_query = st.session_state["vision_cache"][vision_cache_key]
                        else:
                            product_query = orchestrator.identify_query(image_bytes=image_bytes, text_input=None)
                            st.session_state["vision_cache"][vision_cache_key] = product_query
                    else:
                        product_query = orchestrator.identify_query(image_bytes=None, text_input=user_text)

                    # Opcional: query refinement (sem custo se só determinístico; com Groq/Gemini/HF se disponível)
                    llm_router = build_llm_router(
                        groq_api_key=groq_key,
                        gemini_api_key=gemini_key,
                        hf_token=hf_token,
                        prefer=["groq", "gemini", "hf"],
                    )
                    st.session_state["refiner_input"] = product_query
                    refined = refine_with_llm(product_query, llm_router)
                    primary = refined.primary or product_query
                    # Preservar variante de modelo: não remover nem adicionar (ex.: A1 vs A1 Mini são produtos diferentes).
                    in_lower = (product_query or "").lower()
                    out_lower = (primary or "").lower()
                    variants = ["mini", " pro", " max", " plus", " ultra", " lite", " se"]
                    for v in variants:
                        v_clean = v.strip()
                        if v_clean in out_lower and v_clean not in in_lower:
                            primary = product_query
                            break
                        if v_clean in in_lower and v_clean not in out_lower:
                            primary = product_query
                            break
                    product_query = primary
                    # Aplica normalização aprendida; não remover variante (mini/pro/...) que o usuário digitou.
                    try:
                        learned_norm = normalize_query_with_learning(product_query)
                        if learned_norm:
                            q_lower = (product_query or "").lower()
                            norm_lower = learned_norm.lower()
                            variants = ["mini", "pro", "max", "plus", "ultra", "lite", "se"]
                            drop_variant = any(
                                v in q_lower and v not in norm_lower for v in variants
                            )
                            if not drop_variant:
                                product_query = learned_norm
                                st.session_state["learned_query_normalized"] = True
                            else:
                                st.session_state["learned_query_normalized"] = False
                        else:
                            st.session_state["learned_query_normalized"] = False
                    except Exception:
                        st.session_state["learned_query_normalized"] = False
                    st.session_state["refinement_provider"] = refined.provider_name
                    # Debug: mostrar a query final usada na busca (após refinamento + normalização).
                    st.session_state["refined_query"] = product_query
                    st.session_state["llm_refinement_error"] = refined.error

                    # 2) Busca (com cache por sessão)
                    affiliate_key = f"amazon:{affiliate_cfg.amazon_tag}|ali:{affiliate_cfg.aliexpress_admitad_campaign_code}"
                    search_cache_key = (
                        "live" if live_mode else "free",
                        product_query,
                        _safe_get_secret("SERPAPI_GL", "br"),
                        _safe_get_secret("SERPAPI_HL", "pt"),
                        affiliate_key,
                    )

                    if search_cache_key in st.session_state["search_cache"]:
                        cards = st.session_state["search_cache"][search_cache_key]
                    else:
                        cards = orchestrator.search_offers(product_query, max_results=3)
                        st.session_state["search_cache"][search_cache_key] = cards

                    # Tracking local (evento de submissão)
                    top_store = cards[0].store if cards else None
                    st.session_state["events"].append(
                        {
                            "type": "search_submitted",
                            "query": product_query,
                            "mode": "live" if live_mode else "free",
                            "top_store": top_store,
                            "ts": time.time(),
                        }
                    )

                    st.session_state["last_product_query"] = product_query
                    st.session_state["cards"] = cards
                    # Na próxima execução, o campo de busca mostrará a query final (evita "bambu lab a1 mini" no refiner_input).
                    st.session_state["_sync_search_input_to_query"] = product_query

                    # Análise de mercado
                    try:
                        st.session_state["market_result"] = market_analyze(product_query)
                    except Exception:
                        st.session_state["market_result"] = None

                    # Aprendizado incremental (persiste um "catálogo aprendido" local)
                    try:
                        _mr = st.session_state.get("market_result")
                        learn_from_search(
                            product_query,
                            cards=cards,
                            live_mode=live_mode,
                            category=_mr.category if _mr else None,
                            matched_static_model=_mr.product.model if (_mr and _mr.product) else None,
                        )
                    except Exception:
                        # Falhas de persistência de aprendizado não devem quebrar o app.
                        pass

                except OrchestratorError as e:
                    st.error(str(e))
                    st.session_state["last_technical_error"] = str(e)
                    search_failed = True
                except Exception as e:  # noqa: BLE001
                    st.error(
                        "Não consegui completar a busca. Tente outra foto (mais nítida) "
                        "ou um termo mais específico."
                    )
                    st.caption(f"Detalhes técnicos: {e}")
                    st.session_state["last_technical_error"] = str(e)
                    search_failed = True

        # Aviso se falhou: garante que existe para renderizar
        cards = st.session_state.get("cards") or []
        product_query = st.session_state.get("last_product_query")
    else:
        cards = st.session_state.get("cards") or []
        product_query = st.session_state.get("last_product_query")

    if not search_failed and product_query:
        market_result = st.session_state.get("market_result")
        is_top_seller = market_result and market_result.is_top_seller
        top_product = market_result.product if market_result else None

        # Badge de top vendido
        if is_top_seller and top_product:
            rank_label = f"#{top_product.rank}" if top_product.rank else ""
            st.success(
                f"🏆 **Top Vendido no Brasil (2025):** {top_product.model} {rank_label} — "
                f"{top_product.source_label}"
            )

        st.success(f"Produto identificado/buscado: **{product_query}**")
        st.subheader("Melhores ofertas (custo-benefício em lojas confiáveis)")

        # Cards já vêm ordenados por custo-benefício (value_score). Guardamos o vencedor.
        best_idx = 0

        # Grid 3-up (uma linha por vez)
        for i in range(0, len(cards), 3):
            row_cols = st.columns(3, vertical_alignment="top")
            for j, col in enumerate(row_cols):
                idx = i + j
                if idx >= len(cards):
                    break

                card = cards[idx]
                with col:
                    with st.container(border=True, key=f"card_{idx}"):
                        if idx == best_idx:
                            st.success("⭐ Melhor custo-benefício")
                        if card.thumbnail:
                            st.image(card.thumbnail, use_container_width=True)
                        else:
                            st.caption("Sem imagem")

                        st.subheader(card.title)
                        st.caption(card.store)

                        # Badge top vendido por card
                        if is_top_seller and top_product:
                            st.caption(f"🏆 Top Vendido BR #{top_product.rank}")

                        if card.is_live_price:
                            price_value = _format_price(card.price, card.currency) or card.price_label
                            if price_value:
                                st.metric("Preço", price_value)
                        else:
                            price_value = _strip_estimativa_prefix(card.price_label) or card.price_label
                            if price_value:
                                st.metric("Preço estimado", price_value)
                            st.caption("Sem preço ao vivo (modo gratuito).")

                        # Mostrar sinais de qualidade quando existirem (para custo-benefício)
                        meta = card.metadata or {}
                        rating = meta.get("rating")
                        reviews_count = meta.get("reviews_count")
                        if rating is not None:
                            try:
                                r = float(rating)
                                rc = int(reviews_count) if reviews_count is not None else 0
                                st.caption(f"Avaliação: {r:.1f}/5 • {rc} reviews")
                            except Exception:
                                pass

                        why = meta.get("why_this")
                        if isinstance(why, str) and why.strip():
                            st.caption(why.strip())

                        link_label = "Ver oferta (Afiliado)" if card.is_live_price else "Abrir busca"
                        st.link_button(
                            link_label,
                            card.affiliate_link,
                            use_container_width=True,
                        )

                        if st.button(
                            "Registrar visita",
                            key=f"visit_{idx}_{card.store}",
                            use_container_width=True,
                        ):
                            st.session_state["events"].append(
                                {
                                    "type": "card_visit",
                                    "store": card.store,
                                    "title": card.title,
                                    "ts": time.time(),
                                }
                            )
                            st.toast("Visita registrada (local).")

        # Análise explicável da pesquisa (por que esses cards)
        try:
            analysis_mode = "live" if any(c.is_live_price for c in cards) else "free"
            analysis_cache_key = (analysis_mode, product_query or "")
            if analysis_cache_key in st.session_state["analysis_cache"]:
                st.markdown(st.session_state["analysis_cache"][analysis_cache_key])
            else:
                analysis_res = build_product_analysis_result(
                    product_query or "",
                    cards,
                    gemini_api_key=gemini_key or None,
                    groq_api_key=groq_key or None,
                    hf_token=hf_token or None,
                )
                analysis_md = analysis_res.markdown
                st.session_state["analysis_provider"] = analysis_res.provider_name
                st.session_state["analysis_cache"][analysis_cache_key] = analysis_md
                st.markdown(analysis_md)
        except Exception as e:  # noqa: BLE001
            st.warning(f"Não foi possível gerar a análise completa. {e}")

    with st.expander("Dados (debug)"):
        _mr = st.session_state.get("market_result")
        st.json(
            {
                "query": product_query,
                "affiliate_config": asdict(affiliate_cfg),
                "cards": [asdict(c) for c in cards],
                "events": st.session_state.get("events", []),
                "refiner_input": st.session_state.get("refiner_input"),
                "refinement_provider": st.session_state.get("refinement_provider"),
                "refined_query": st.session_state.get("refined_query"),
                "llm_refinement_error": st.session_state.get("llm_refinement_error"),
                "analysis_provider": st.session_state.get("analysis_provider"),
                "vision_gemini_present": st.session_state.get("vision_gemini_present"),
                "vision_hf_present": st.session_state.get("vision_hf_present"),
                "vision_image_present": st.session_state.get("vision_image_present"),
                "vision_backend_used": st.session_state.get("vision_backend_used"),
                "last_technical_error": st.session_state.get("last_technical_error"),
                "market_category": _mr.category if _mr else None,
                "market_matched": _mr.matched if _mr else None,
                "market_is_top_seller": _mr.is_top_seller if _mr else None,
                "market_price_hint": (
                    f"R$ {_mr.price_hint_low} – R$ {_mr.price_hint_high}" if _mr else None
                ),
                "learned_query_normalized": st.session_state.get("learned_query_normalized"),
            }
        )


if __name__ == "__main__":
    main()

