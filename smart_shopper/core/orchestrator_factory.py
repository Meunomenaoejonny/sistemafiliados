from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.affiliate_manager import AffiliateConfig
from core.orchestrator import Orchestrator
from core.providers.search.search_provider_factory import build_search_provider
from core.providers.vision.vision_provider_factory import build_vision_provider


@dataclass(frozen=True)
class OrchestratorBuildResult:
    orchestrator: Orchestrator
    vision_backend: Optional[str]
    live_mode: bool


def build_orchestrator(
    *,
    affiliate_cfg: AffiliateConfig,
    image_present: bool,
    gemini_api_key: str,
    hf_token: str,
    serpapi_key: str,
    serper_api_key: str = "",
    serpapi_gl: str = "br",
    serpapi_hl: str = "pt",
) -> OrchestratorBuildResult:
    vision_provider, vision_backend = build_vision_provider(
        image_present=image_present,
        gemini_api_key=gemini_api_key,
        hf_token=hf_token,
    )
    search_provider, live_mode = build_search_provider(
        serpapi_key=serpapi_key,
        serper_api_key=serper_api_key,
        gl=serpapi_gl,
        hl=serpapi_hl,
    )

    return OrchestratorBuildResult(
        orchestrator=Orchestrator(
            vision_provider=vision_provider,
            search_provider=search_provider,
            affiliate_cfg=affiliate_cfg,
        ),
        vision_backend=vision_backend,
        live_mode=live_mode,
    )

