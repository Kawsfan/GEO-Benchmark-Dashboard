"""Servicelaag: een scan uitvoeren (automatisering + handmatige aanvulling)
en het resultaat wegschrijven als nieuwe historische rij (nooit overschrijven)."""

from __future__ import annotations

import os

from sqlmodel import Session

from app.automation.llm_rubric import assess_llm_criteria
from app.automation.phase3_runner import run_phase3_automation
from app.automation.runner import run_phase1_automation
from app.citation.scoring import compute_c9_score
from app.models import Organization, Scan, ScanCriterionScore, ScanStatus, ScoreSource, TriggerType, utcnow
from app.scoring import CRITERIA, SOURCE_LLM_ESTIMATE, SOURCE_MANUAL, classify, compute_score


def run_scan(
    session: Session,
    organization: Organization,
    triggered_by: TriggerType = TriggerType.manual,
    manual_scores: dict[str, float] | None = None,
    manual_rationales: dict[str, str] | None = None,
    run_llm_assessment: bool = True,
    run_phase3: bool = True,
    include_c9: bool = True,
) -> Scan:
    """Voer een scan uit voor `organization`.

    Fase 1-criteria (c1, c2, c10-freshness, + de knock-out) worden altijd
    automatisch gemeten. Fase 2-criteria (c3, c4, c5) worden — als
    `run_llm_assessment` True is en de pagina-tekst beschikbaar is — via één
    LLM-call per pagina beoordeeld (zie `app.automation.llm_rubric`). Fase
    3-criteria (c6 Wikidata, c7 externe vermeldingen via web-search, c8
    multimodaal/social) worden — als `run_phase3` True is — via
    `app.automation.phase3_runner` beoordeeld. C9 (Share of Model) wordt —
    als `include_c9` True is — puur uit al opgeslagen `CitationRun`-data
    gelezen (`app.citation.scoring.compute_c9_score`); dit start GEEN nieuwe
    provider-calls (die lopen los, via `app.citation.runner`, zie
    ARCHITECTURE.md). Lukt een van deze checks niet (geen credentials, rate
    limit, netwerkfout, geen match, of nog geen citatie-data) dan degradeert
    de scan gracieus naar de bestaande `manual_scores`/0-fallback voor dát
    criterium — nooit een mislukte scan. Voor de resterende criteria wordt
    `manual_scores` gebruikt indien opgegeven; anders blijft de score 0
    (zichtbaar als "handmatig ingevoerd, nog niet ingevuld" in de UI).
    """
    manual_scores = manual_scores or {}
    manual_rationales = manual_rationales or {}

    automated = run_phase1_automation(organization.domain)

    merged_scores: dict[str, float] = dict(automated.criterion_scores)
    sources: dict[str, str] = dict(automated.criterion_sources)
    rationales: dict[str, str] = dict(automated.criterion_rationales)
    automation_errors: list[str] = [automated.fetch_error] if automated.fetch_error else []

    llm_assessment_disabled = os.environ.get("GEO_DASHBOARD_DISABLE_LLM_ASSESSMENT") == "1"
    if run_llm_assessment and automated.page_text and not llm_assessment_disabled:
        llm_result = assess_llm_criteria(automated.page_text, organization.name, organization.domain)
        if llm_result.succeeded:
            merged_scores.update(llm_result.scores)
            sources.update({code: SOURCE_LLM_ESTIMATE for code in llm_result.scores})
            rationales.update(llm_result.rationales)
        elif llm_result.error:
            automation_errors.append(llm_result.error)
        # Bij een fout (llm_result.error) laten we c3/c4/c5 gewoon over aan
        # de manual_scores/0-fallback hieronder — geen scan-mislukking.

    if run_phase3:
        phase3 = run_phase3_automation(
            organization.name, organization.domain, automated.html, sector=organization.sector
        )
        merged_scores.update(phase3.criterion_scores)
        sources.update(phase3.criterion_sources)
        rationales.update(phase3.criterion_rationales)
        automation_errors.extend(phase3.errors.values())

    if include_c9 and organization.id is not None:
        c9 = compute_c9_score(session, organization.id)
        if c9 is not None:
            merged_scores["c9_share_of_model"] = c9.score
            sources["c9_share_of_model"] = SOURCE_LLM_ESTIMATE
            rationales["c9_share_of_model"] = c9.rationale

    for code in CRITERIA:
        if code in merged_scores:
            continue  # automatisch gemeten, niet overschrijven met handmatige invoer
        if code in manual_scores:
            merged_scores[code] = manual_scores[code]
            sources[code] = SOURCE_MANUAL
            if code in manual_rationales:
                rationales[code] = manual_rationales[code]

    report = compute_score(
        criterion_scores=merged_scores,
        crawler_ok=automated.crawler_ok,
        ssr_ok=automated.ssr_ok,
        sources=sources,
        rationales=rationales,
    )

    scan = Scan(
        organization_id=organization.id,
        triggered_by=triggered_by,
        knockout_pass=report.knockout_pass,
        crawler_ok=report.crawler_ok,
        ssr_ok=report.ssr_ok,
        total_score=report.total_score,
        classification=report.classification,
        classification_desc=report.classification_desc,
        status=ScanStatus.completed,
        error_message=" | ".join(automation_errors) if automation_errors else None,
    )
    session.add(scan)
    session.flush()  # scan.id beschikbaar maken zonder al te committen

    now = utcnow()
    for r in report.results:
        session.add(
            ScanCriterionScore(
                scan_id=scan.id,
                code=r.code,
                raw_score=r.raw,
                weight=r.weight,
                contribution=r.contribution,
                source=ScoreSource(r.source),
                rationale=r.rationale,
                measured_at=now if r.source in ("automated", "llm_estimate") else None,
            )
        )

    session.commit()
    session.refresh(scan)
    return scan


def update_manual_scores(
    session: Session,
    scan: Scan,
    updates: dict[str, tuple[float, str | None]],
) -> Scan:
    """Werk de handmatig invulbare criteria van een bestaande scan bij en
    herbereken totaalscore + classificatie. Automatisch gemeten criteria
    worden nooit overschreven via dit pad."""
    for cs in scan.criterion_scores:
        if cs.code not in updates:
            continue
        if cs.source == ScoreSource.automated:
            continue
        raw, rationale = updates[cs.code]
        cs.raw_score = max(0.0, min(10.0, float(raw)))
        cs.contribution = round(cs.weight * (cs.raw_score / 10), 2)
        cs.source = ScoreSource.manual
        if rationale is not None:
            cs.rationale = rationale
        session.add(cs)

    session.flush()
    total = sum(cs.contribution for cs in scan.criterion_scores)
    total = round(total, 1) if scan.knockout_pass else 0.0
    scan.total_score = total
    if scan.knockout_pass:
        classification, desc = classify(total)
    else:
        classification, desc = ("Onzichtbaar", "Onzichtbaar voor AI due to technical lockout.")
    scan.classification = classification
    scan.classification_desc = desc
    session.add(scan)
    session.commit()
    session.refresh(scan)
    return scan
