"""
Fase 2 — LLM-ondersteunde beoordeling.

Eén Claude-call per pagina, met een vaste beoordelingsprompt die exact de
criteriumomschrijving uit `app/scoring.CRITERIA` gebruikt, beoordeelt C3
(Answerability & Volledigheid), C4 (Antwoord vooraan / BLUF) en C5
(Feitelijke dichtheid & Bronnen) en geeft per criterium een score 0-10 +
korte onderbouwing terug. De onderbouwing wordt opgeslagen (`ScanCriterionScore.rationale`)
zodat een mens de LLM-schatting kan controleren of corrigeren op de
scan-detailpagina — zie ARCHITECTURE.md sectie 4.

Faalt dit (geen API-key, rate limit, netwerkfout) dan degradeert de scan
gracieus: de betreffende criteria blijven op hun laatst bekende/handmatige
waarde staan (zie `app/scan_service.run_scan`), er wordt geen scan geblokkeerd.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.scoring import CRITERIA

LLM_RUBRIC_CODES = ["c3_answerability", "c4_bluf", "c5_fact_density"]

# Overschrijfbaar voor kostenbeheersing (bv. terugschakelen naar een
# goedkoper model bij hoog scanvolume) — default volgt de aanbevolen
# Claude-modelkeuze.
LLM_MODEL = os.environ.get("GEO_DASHBOARD_LLM_MODEL", "claude-opus-5")
MAX_PAGE_TEXT_CHARS = 12000


class _CriterionScore(BaseModel):
    score: float = Field(ge=0, le=10, description="Score 0-10 (stappen van 0.5 zijn toegestaan).")
    rationale: str = Field(
        description="Korte onderbouwing in het Nederlands (1-3 zinnen); citeer waar mogelijk een concreet tekstfragment van de pagina ter onderbouwing."
    )


class RubricAssessment(BaseModel):
    c3_answerability: _CriterionScore
    c4_bluf: _CriterionScore
    c5_fact_density: _CriterionScore


def _criterion_rubric_text(code: str) -> str:
    meta = CRITERIA[code]
    return f"- **{meta['label']}** (`{code}`): {meta['advice']}"


def _build_system_prompt() -> str:
    criteria_block = "\n".join(_criterion_rubric_text(c) for c in LLM_RUBRIC_CODES)
    return f"""Je beoordeelt een webpagina volgens het GEO Benchmark Model v2.0, specifiek
voor de volgende drie criteria (elk 0-10, waarbij 0 = volledig afwezig/zeer
zwak en 10 = uitstekend uitgevoerd):

{criteria_block}

Scoreleidraad per criterium:

**c3_answerability (Answerability & Volledigheid)**: beantwoordt de pagina
de daadwerkelijke vraag van de bezoeker direct en volledig, inclusief
concrete cijfers, voorwaarden en uitzonderingen? 0-3 = vraag wordt niet of
nauwelijks beantwoord; 4-6 = deels beantwoord, mist concrete details; 7-8 =
grotendeels compleet; 9-10 = volledig en direct beantwoord met alle relevante
concrete informatie.

**c4_bluf (Antwoord vooraan / BLUF)**: staat de kernconclusie/het
belangrijkste antwoord in de eerste ~60 woorden van de pagina, zonder
sfeeropbouw of marketingvulling die daaraan voorafgaat? 0-3 = het antwoord
staat pas diep in de tekst of ontbreekt; 4-6 = deels vooraan, met ruis
ervoor; 7-8 = kernboodschap staat vroeg met beperkte ruis; 9-10 = eerste
zin(nen) geven het antwoord direct en compact.

**c5_fact_density (Feitelijke dichtheid & Bronnen)**: hoeveel verifieerbare
feiten, cijfers, data en bronvermeldingen bevat de tekst per ~100 woorden,
in verhouding tot holle marketingtaal? 0-3 = vrijwel uitsluitend
marketingtaal, geen verifieerbare feiten; 4-6 = enkele feiten, veel vulling;
7-8 = behoorlijke feitendichtheid met af en toe bronvermelding; 9-10 = hoge
dichtheid aan verifieerbare, specifieke feiten en/of bronvermeldingen.

Baseer je oordeel uitsluitend op de aangeleverde paginatekst. Wees kritisch:
marketingtaal, vage beloftes en sfeerbeschrijvingen verdienen een lage
score, ook als de pagina er "professioneel" uitziet. Geef voor elk criterium
een score en een korte (1-3 zinnen) onderbouwing in het Nederlands, waar
mogelijk met een citaat uit de tekst."""


RUBRIC_SYSTEM_PROMPT = _build_system_prompt()


@dataclass
class LLMRubricResult:
    scores: dict[str, float] = field(default_factory=dict)
    rationales: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and bool(self.scores)


def assess_llm_criteria(page_text: str, brand_name: str, domain: str) -> LLMRubricResult:
    """Beoordeel C3/C4/C5 voor één pagina via één Claude-call.

    Faalt altijd gracieus (nooit een exception naar de caller): elke
    faalroute (geen tekst, geen credentials, rate limit, netwerkfout, API-fout)
    resulteert in een `LLMRubricResult` met `error` gezet en lege scores/
    rationales, zodat `run_scan` de betreffende criteria simpelweg ongemoeid
    laat i.p.v. de scan te laten mislukken.
    """
    if not page_text or not page_text.strip():
        return LLMRubricResult(error="Geen paginatekst beschikbaar voor LLM-beoordeling.")

    truncated = page_text[:MAX_PAGE_TEXT_CHARS]
    truncated_note = (
        ""
        if len(page_text) <= MAX_PAGE_TEXT_CHARS
        else f"\n\n[Let op: paginatekst afgekapt na {MAX_PAGE_TEXT_CHARS} tekens.]"
    )

    try:
        import anthropic
    except ImportError:
        return LLMRubricResult(error="Het 'anthropic'-pakket is niet geïnstalleerd — LLM-beoordeling overgeslagen.")

    try:
        client = anthropic.Anthropic()
        response = client.messages.parse(
            model=LLM_MODEL,
            max_tokens=2048,
            system=RUBRIC_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Merk: {brand_name}\nDomein: {domain}\n\nPaginatekst:\n{truncated}{truncated_note}"
                    ),
                }
            ],
            output_format=RubricAssessment,
        )
    except anthropic.AuthenticationError:
        return LLMRubricResult(
            error="Geen geldige Anthropic API-toegang geconfigureerd (ANTHROPIC_API_KEY) — LLM-beoordeling overgeslagen."
        )
    except anthropic.PermissionDeniedError:
        return LLMRubricResult(error="Anthropic API-toegang heeft onvoldoende rechten voor dit model.")
    except anthropic.RateLimitError as exc:
        return LLMRubricResult(error=f"Rate limit bij de Anthropic API: {exc}")
    except anthropic.APIStatusError as exc:
        return LLMRubricResult(error=f"Anthropic API-fout ({exc.status_code}): {exc.message}")
    except anthropic.APIConnectionError as exc:
        return LLMRubricResult(error=f"Netwerkfout bij de Anthropic API: {exc}")
    except TypeError as exc:
        # Geen enkele credential-bron beschikbaar (geen ANTHROPIC_API_KEY, geen
        # ant-profiel): de SDK gooit dan al vóór het request een TypeError i.p.v.
        # AuthenticationError (die pas bij een 401-response van de server komt).
        return LLMRubricResult(
            error=f"Geen Anthropic API-toegang geconfigureerd — LLM-beoordeling overgeslagen ({exc})."
        )
    except Exception as exc:  # noqa: BLE001 - laatste vangnet: nooit de scan laten crashen op een LLM-fout.
        return LLMRubricResult(error=f"Onverwachte fout bij LLM-beoordeling: {exc}")

    parsed = response.parsed_output
    scores = {
        "c3_answerability": parsed.c3_answerability.score,
        "c4_bluf": parsed.c4_bluf.score,
        "c5_fact_density": parsed.c5_fact_density.score,
    }
    rationales = {
        "c3_answerability": parsed.c3_answerability.rationale,
        "c4_bluf": parsed.c4_bluf.rationale,
        "c5_fact_density": parsed.c5_fact_density.rationale,
    }
    return LLMRubricResult(scores=scores, rationales=rationales)
