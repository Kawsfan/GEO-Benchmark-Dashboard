"""
Fase 4 — detectie of/hoe een merk in een AI-antwoord wordt genoemd.

Twee stappen, kostenbewust:
1. Simpele stringmatch (gratis) op merknaam/domein — bepaalt alleen of het
   merk überhaupt voorkomt.
2. Alleen als stap 1 een treffer geeft: één korte Claude-classificatiecall
   om onderscheid te maken tussen "mentioned" en "cited_with_link", plus
   sentiment. Bij geen treffer in stap 1 wordt stap 2 overgeslagen — dat is
   linksom of rechtsom altijd "not_mentioned", geen reden om te betalen voor
   een classificatiecall.

Lukt de classificatiecall niet (geen credentials, rate limit), dan valt de
detectie terug op een conservatieve stringmatch-gebaseerde classificatie
i.p.v. de hele detectie te laten mislukken.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

CLASSIFIER_MODEL = os.environ.get("GEO_DASHBOARD_CITATION_CLAUDE_MODEL", "claude-haiku-4-5")

NOT_MENTIONED = "not_mentioned"
MENTIONED = "mentioned"
CITED_WITH_LINK = "cited_with_link"


@dataclass
class DetectionResult:
    cited: bool
    citation_type: str
    sentiment: str | None = None
    note: str | None = None


def _domain_root(domain: str) -> str:
    return domain.strip().lower().removeprefix("www.").split("/")[0]


def _stringmatch_hit(response_text: str, brand_name: str, domain: str) -> bool:
    text_lower = response_text.lower()
    name_hit = bool(brand_name) and brand_name.strip().lower() in text_lower
    domain_hit = bool(domain) and _domain_root(domain) in text_lower
    return name_hit or domain_hit


def _looks_like_link(response_text: str, domain: str) -> bool:
    root = _domain_root(domain)
    if not root:
        return False
    # Markdown-link ([tekst](url)) of een kale URL die het domein bevat.
    pattern = re.compile(rf"(\[[^\]]*\]\([^)]*{re.escape(root)}[^)]*\)|https?://[^\s)]*{re.escape(root)}[^\s)]*)")
    return bool(pattern.search(response_text))


class _MentionClassification(BaseModel):
    citation_type: str = Field(description="'mentioned' of 'cited_with_link'.")
    sentiment: str = Field(description="'positief', 'neutraal' of 'negatief'.")


def _classify_mention(response_text: str, brand_name: str) -> _MentionClassification | None:
    try:
        import anthropic
    except ImportError:
        return None

    try:
        client = anthropic.Anthropic()
        response = client.messages.parse(
            model=CLASSIFIER_MODEL,
            max_tokens=256,
            system=(
                "Je krijgt de tekst van een AI-antwoord waarin het merk hieronder al "
                "via stringmatch is aangetroffen. Classificeer:\n"
                "- citation_type: 'cited_with_link' als het antwoord een daadwerkelijke "
                "klikbare link/URL naar het merk bevat, anders 'mentioned'.\n"
                "- sentiment: de toon waarin het merk wordt besproken — 'positief', "
                "'neutraal' of 'negatief'."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Merk: {brand_name}\n\nAI-antwoord:\n{response_text[:4000]}",
                }
            ],
            output_format=_MentionClassification,
        )
        return response.parsed_output
    except Exception:  # noqa: BLE001 - classificatie is een verrijking, geen harde eis
        return None


def detect_mention(response_text: str, brand_name: str, domain: str) -> DetectionResult:
    if not response_text or not _stringmatch_hit(response_text, brand_name, domain):
        return DetectionResult(cited=False, citation_type=NOT_MENTIONED)

    classification = _classify_mention(response_text, brand_name)
    if classification is not None:
        citation_type = CITED_WITH_LINK if classification.citation_type == CITED_WITH_LINK else MENTIONED
        return DetectionResult(cited=True, citation_type=citation_type, sentiment=classification.sentiment)

    # Classificatie niet beschikbaar: conservatieve stringmatch-gebaseerde fallback.
    citation_type = CITED_WITH_LINK if _looks_like_link(response_text, domain) else MENTIONED
    return DetectionResult(
        cited=True,
        citation_type=citation_type,
        sentiment=None,
        note="LLM-classificatie niet beschikbaar; type bepaald via stringmatch-fallback.",
    )
