"""
Orchestreert de Fase 1-automatisering voor één domein: knock-out check,
C1 structured data, C2 chunkability, C10-freshness. Retourneert een
dict {code: (raw_score, source, rationale)} klaar om samen te voegen met
handmatige/LLM-scores voor de overige criteria.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.automation.chunkability import analyze_chunkability
from app.automation.freshness import analyze_freshness
from app.automation.http_client import build_client, normalize_domain
from app.automation.phase0_knockout import run_knockout_check
from app.automation.structured_data import analyze_structured_data
from app.automation.text_extraction import extract_visible_text
from app.scoring import SOURCE_AUTOMATED


@dataclass
class AutomatedScanResult:
    crawler_ok: bool
    ssr_ok: bool
    knockout_detail: str
    criterion_scores: dict[str, float]
    criterion_sources: dict[str, str]
    criterion_rationales: dict[str, str]
    fetch_error: str | None = None
    # Zichtbare pagina-tekst, hergebruikt door de Fase 2 LLM-rubric zodat
    # die de pagina niet nogmaals hoeft op te halen. None als de fetch faalde.
    page_text: str | None = None
    # Ruwe HTML, hergebruikt door de Fase 3 C8-multimodaal-check (heeft de
    # <a href>-links nodig, die page_text niet meer bevat). None als de fetch faalde.
    html: str | None = None


def run_phase1_automation(domain: str) -> AutomatedScanResult:
    knockout = run_knockout_check(domain)

    criterion_scores: dict[str, float] = {}
    criterion_sources: dict[str, str] = {}
    criterion_rationales: dict[str, str] = {}
    fetch_error: str | None = None

    # C1/C2/C10 hebben de pagina-HTML nodig; als de knock-out al faalt op
    # bereikbaarheid proberen we de content toch op te halen voor zover
    # mogelijk (een SSR-fail betekent niet per se een fetch-fail).
    base_url = normalize_domain(domain)
    html: str | None = None
    try:
        with build_client() as client:
            resp = client.get(base_url)
            html = resp.text
    except httpx.HTTPError as exc:
        fetch_error = f"Kon pagina niet ophalen voor C1/C2/C10-analyse: {exc}"

    page_text: str | None = None
    if html is not None:
        page_text = extract_visible_text(html)

        sd = analyze_structured_data(html)
        criterion_scores["c1_structured_data"] = sd.score
        criterion_sources["c1_structured_data"] = SOURCE_AUTOMATED
        criterion_rationales["c1_structured_data"] = sd.detail

        chunk = analyze_chunkability(html)
        criterion_scores["c2_chunkability"] = chunk.score
        criterion_sources["c2_chunkability"] = SOURCE_AUTOMATED
        criterion_rationales["c2_chunkability"] = chunk.detail

        fresh = analyze_freshness(html)
        criterion_scores["c10_sentiment_freshness"] = fresh.score
        criterion_sources["c10_sentiment_freshness"] = SOURCE_AUTOMATED
        criterion_rationales["c10_sentiment_freshness"] = (
            f"[Alleen freshness-deel automatisch] {fresh.detail}"
        )

    return AutomatedScanResult(
        crawler_ok=knockout.crawler_ok,
        ssr_ok=knockout.ssr_ok,
        knockout_detail=knockout.detail,
        criterion_scores=criterion_scores,
        criterion_sources=criterion_sources,
        criterion_rationales=criterion_rationales,
        fetch_error=fetch_error,
        page_text=page_text,
        html=html,
    )
