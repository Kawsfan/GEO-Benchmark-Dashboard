"""
Orchestreert Fase 3 voor één organisatie: C6 (Wikidata), C7 (externe
vermeldingen via web-search-ondersteunde LLM-beoordeling), C8 (multimodaal/
social, uit de al opgehaalde homepage-HTML). Elke check faalt onafhankelijk
en gracieus — één mislukt criterium blokkeert de andere twee niet, en
blokkeert nooit de scan als geheel.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.automation.entity_clarity import analyze_entity_clarity
from app.automation.external_mentions import assess_external_mentions
from app.automation.multimodal import analyze_multimodal_presence
from app.scoring import SOURCE_AUTOMATED, SOURCE_LLM_ESTIMATE


@dataclass
class Phase3Result:
    criterion_scores: dict[str, float] = field(default_factory=dict)
    criterion_sources: dict[str, str] = field(default_factory=dict)
    criterion_rationales: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


def run_phase3_automation(
    brand_name: str,
    domain: str,
    html: str | None,
    sector: str | None = None,
) -> Phase3Result:
    result = Phase3Result()

    if os.environ.get("GEO_DASHBOARD_DISABLE_PHASE3") == "1":
        result.errors["c6_entity_clarity"] = "Fase 3 uitgeschakeld via GEO_DASHBOARD_DISABLE_PHASE3."
        result.errors["c7_external_mentions"] = "Fase 3 uitgeschakeld via GEO_DASHBOARD_DISABLE_PHASE3."
        result.errors["c8_multimodal"] = "Fase 3 uitgeschakeld via GEO_DASHBOARD_DISABLE_PHASE3."
        return result

    try:
        entity = analyze_entity_clarity(brand_name, domain)
        result.criterion_scores["c6_entity_clarity"] = entity.score
        result.criterion_sources["c6_entity_clarity"] = SOURCE_AUTOMATED
        result.criterion_rationales["c6_entity_clarity"] = entity.detail
    except Exception as exc:  # noqa: BLE001 - nooit de scan laten crashen op Fase 3
        result.errors["c6_entity_clarity"] = f"C6-beoordeling mislukt: {exc}"

    mentions = assess_external_mentions(brand_name, domain, sector=sector)
    if mentions.succeeded:
        result.criterion_scores["c7_external_mentions"] = mentions.score
        result.criterion_sources["c7_external_mentions"] = SOURCE_LLM_ESTIMATE
        sources_note = f" Bronnen: {', '.join(mentions.notable_sources)}." if mentions.notable_sources else ""
        result.criterion_rationales["c7_external_mentions"] = f"{mentions.rationale}{sources_note}"
    else:
        result.errors["c7_external_mentions"] = mentions.error or "Onbekende fout bij C7-beoordeling."

    if html:
        try:
            multimodal = analyze_multimodal_presence(html)
            result.criterion_scores["c8_multimodal"] = multimodal.score
            result.criterion_sources["c8_multimodal"] = SOURCE_AUTOMATED
            result.criterion_rationales["c8_multimodal"] = multimodal.detail
        except Exception as exc:  # noqa: BLE001
            result.errors["c8_multimodal"] = f"C8-beoordeling mislukt: {exc}"
    else:
        result.errors["c8_multimodal"] = "Geen homepage-HTML beschikbaar voor C8-analyse."

    return result
