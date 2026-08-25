"""
C7 — Externe co-occurrence & Media, via web-search-ondersteunde LLM-beoordeling.

Eén Claude-call met de server-side `web_search`-tool: Claude zoekt zelf naar
recente (bij voorkeur laatste 6-12 maanden) vermeldingen van het merk in
onafhankelijke bronnen (vakmedia, nieuwswebsites, gerenommeerde platforms),
en beoordeelt aantal + kwaliteit daarvan tegen dezelfde 0-10-schaal als de
overige criteria — met een korte onderbouwing en de opvallendste bronnen.

Dit is de enige Fase 3-check met doorlopende externe kosten per scan (Claude
+ web-search-gebruik) en is daarom apart uitschakelbaar via
`GEO_DASHBOARD_DISABLE_EXTERNAL_MENTIONS=1`, los van C6/C8 die geen
API-kosten maken.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

LLM_MODEL = os.environ.get("GEO_DASHBOARD_LLM_MODEL", "claude-opus-5")
MAX_SEARCH_USES = 5

SYSTEM_PROMPT = """Je beoordeelt het criterium "Externe co-occurrence & Media" uit het GEO
Benchmark Model v2.0 voor een merk/organisatie: in hoeverre wordt dit merk
vermeld in externe, ONAFHANKELIJKE bronnen (vakmedia, nieuwswebsites,
gerenommeerde platforms zoals Tweakers/Reddit) — niet de eigen website of
eigen social-mediakanalen van het merk zelf.

Gebruik de web-search-tool om recente (bij voorkeur laatste 6-12 maanden)
vermeldingen te vinden. Baseer je score UITSLUITEND op externe, onafhankelijke
bronnen; tel de eigen website en eigen social-mediaprofielen van het merk
niet mee.

Scoreleidraad (0-10):
0-3 = vrijwel geen vermeldingen buiten eigen kanalen gevonden.
4-6 = incidentele vermeldingen in kleinere of minder gezaghebbende bronnen.
7-8 = regelmatige vermeldingen in relevante vakmedia of gerenommeerde platforms.
9-10 = prominente, veelvuldige vermeldingen in gezaghebbende bronnen.

Geef een geschat aantal vermeldingen, maximaal 5 opvallende bronnen
(domeinnamen, geen social media van het merk zelf), een score en een korte
(1-3 zinnen) onderbouwing in het Nederlands."""


class MentionsAssessment(BaseModel):
    mentions_count_estimate: int = Field(ge=0, le=100, description="Geschat aantal relevante externe vermeldingen.")
    notable_sources: list[str] = Field(
        default_factory=list,
        description="Max. 5 domeinnamen van de meest relevante gevonden bronnen (geen social media van het merk zelf).",
    )
    score: float = Field(ge=0, le=10)
    rationale: str = Field(description="Korte onderbouwing in het Nederlands (1-3 zinnen).")


@dataclass
class ExternalMentionsResult:
    score: float | None = None
    notable_sources: list[str] = field(default_factory=list)
    mentions_count_estimate: int | None = None
    rationale: str | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.score is not None


def assess_external_mentions(brand_name: str, domain: str, sector: str | None = None) -> ExternalMentionsResult:
    if os.environ.get("GEO_DASHBOARD_DISABLE_EXTERNAL_MENTIONS") == "1":
        return ExternalMentionsResult(error="C7-beoordeling uitgeschakeld via GEO_DASHBOARD_DISABLE_EXTERNAL_MENTIONS.")

    try:
        import anthropic
    except ImportError:
        return ExternalMentionsResult(error="Het 'anthropic'-pakket is niet geïnstalleerd — C7-beoordeling overgeslagen.")

    sector_line = f"\nSector/branche: {sector}" if sector else ""
    user_content = f"Merk: {brand_name}\nEigen domein (niet meetellen als externe bron): {domain}{sector_line}"

    try:
        client = anthropic.Anthropic()
        response = client.messages.parse(
            model=LLM_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_SEARCH_USES}],
            output_format=MentionsAssessment,
        )
    except anthropic.AuthenticationError:
        return ExternalMentionsResult(
            error="Geen geldige Anthropic API-toegang geconfigureerd (ANTHROPIC_API_KEY) — C7-beoordeling overgeslagen."
        )
    except anthropic.PermissionDeniedError:
        return ExternalMentionsResult(error="Anthropic API-toegang heeft onvoldoende rechten voor dit model of web search.")
    except anthropic.RateLimitError as exc:
        return ExternalMentionsResult(error=f"Rate limit bij de Anthropic API: {exc}")
    except anthropic.APIStatusError as exc:
        return ExternalMentionsResult(error=f"Anthropic API-fout ({exc.status_code}): {exc.message}")
    except anthropic.APIConnectionError as exc:
        return ExternalMentionsResult(error=f"Netwerkfout bij de Anthropic API: {exc}")
    except TypeError as exc:
        # Geen enkele credential-bron beschikbaar — zie app.automation.llm_rubric
        # voor waarom dit een TypeError is i.p.v. AuthenticationError.
        return ExternalMentionsResult(
            error=f"Geen Anthropic API-toegang geconfigureerd — C7-beoordeling overgeslagen ({exc})."
        )
    except Exception as exc:  # noqa: BLE001 - nooit de scan laten crashen op een C7-fout.
        return ExternalMentionsResult(error=f"Onverwachte fout bij C7-beoordeling: {exc}")

    parsed = response.parsed_output
    return ExternalMentionsResult(
        score=parsed.score,
        notable_sources=parsed.notable_sources[:5],
        mentions_count_estimate=parsed.mentions_count_estimate,
        rationale=parsed.rationale,
    )
