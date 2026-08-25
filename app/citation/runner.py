"""Fase 4 — orchestreert een citatie-check voor één organisatie: alle actieve
prompts voor haar sector × alle ingeschakelde providers, met budgetbewaking
en per-(prompt,provider)-graceful degradation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.citation.budget import is_budget_exhausted, spent_this_month
from app.citation.detection import detect_mention
from app.citation.providers import PROVIDERS, enabled_providers
from app.models import CitationPrompt, CitationRun, Organization, utcnow


@dataclass
class CitationCheckSummary:
    runs_created: int = 0
    skipped_due_to_budget: int = 0
    provider_errors: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    disabled: bool = False
    no_prompts: bool = False


def run_citation_check(session: Session, organization: Organization) -> CitationCheckSummary:
    summary = CitationCheckSummary()

    if os.environ.get("GEO_DASHBOARD_DISABLE_CITATION_TRACKING") == "1":
        summary.disabled = True
        return summary

    if not organization.sector:
        summary.no_prompts = True
        return summary

    prompts = session.exec(
        select(CitationPrompt).where(
            CitationPrompt.sector == organization.sector,
            CitationPrompt.is_active == True,  # noqa: E712
        )
    ).all()
    if not prompts:
        summary.no_prompts = True
        return summary

    providers = enabled_providers()
    spent = spent_this_month(session, organization.id)
    budget = organization.citation_budget_usd_per_month

    for prompt in prompts:
        for provider_code in providers:
            if is_budget_exhausted(spent, budget):
                summary.skipped_due_to_budget += 1
                continue

            call = PROVIDERS[provider_code]
            response = call(prompt.prompt_text)
            if not response.succeeded:
                summary.provider_errors.append(f"{provider_code} ({prompt.id}): {response.error}")
                continue

            detection = detect_mention(response.text, organization.name, organization.domain)
            cost = response.cost_usd or 0.0
            spent += cost
            summary.total_cost_usd += cost
            summary.runs_created += 1

            session.add(
                CitationRun(
                    organization_id=organization.id,
                    prompt_id=prompt.id,
                    provider=provider_code,
                    run_at=utcnow(),
                    cited=detection.cited,
                    citation_type=detection.citation_type,
                    sentiment=detection.sentiment,
                    raw_response=(response.text or "")[:2000],
                    cost_usd=cost,
                )
            )

    session.commit()
    return summary
