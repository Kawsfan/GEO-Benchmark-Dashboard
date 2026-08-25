"""Maandelijkse automatische scan + citatie-check van alle actieve organisaties.

Elke scan-run voegt een nieuwe `Scan`-rij toe per actieve organisatie
(historie, geen overschrijving). Handmatige/LLM-criteria van de vorige scan
van diezelfde organisatie worden overgenomen als startpunt, zodat een
mislukte automatische meting terugvalt op de laatst bekende waarde i.p.v.
terug te zakken naar 0.

De citatie-check (Fase 4, C9) draait als apart geplande job, vóór de
maandelijkse scan, zodat de scan van die dag de verse Share-of-Model-data
al kan meenemen (`run_scan()` leest C9 puur uit opgeslagen `CitationRun`-data,
zie `app.citation.scoring`).
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select

from app.citation.runner import run_citation_check
from app.database import engine
from app.models import Organization, ScoreSource, TriggerType
from app.scan_service import run_scan

logger = logging.getLogger("geo_dashboard.scheduler")


def _carry_forward_manual_scores(session: Session, organization: Organization) -> dict[str, float]:
    latest = session.exec(
        select(Organization)
        .where(Organization.id == organization.id)
    ).first()
    if latest is None or not latest.scans:
        return {}
    last_scan = max(latest.scans, key=lambda s: s.created_at)
    return {
        cs.code: cs.raw_score
        for cs in last_scan.criterion_scores
        if cs.source in (ScoreSource.manual, ScoreSource.llm_estimate)
    }


def run_monthly_scans() -> None:
    with Session(engine) as session:
        organizations = session.exec(select(Organization).where(Organization.is_active == True)).all()  # noqa: E712
        logger.info("Maandelijkse scan gestart voor %d actieve organisaties", len(organizations))
        for org in organizations:
            try:
                manual_scores = _carry_forward_manual_scores(session, org)
                run_scan(session, org, triggered_by=TriggerType.scheduled, manual_scores=manual_scores)
            except Exception:
                logger.exception("Maandelijkse scan mislukt voor organisatie %s (%s)", org.name, org.domain)


def run_monthly_citation_checks() -> None:
    with Session(engine) as session:
        organizations = session.exec(select(Organization).where(Organization.is_active == True)).all()  # noqa: E712
        logger.info("Maandelijkse citatie-check gestart voor %d actieve organisaties", len(organizations))
        for org in organizations:
            try:
                summary = run_citation_check(session, org)
                if summary.provider_errors:
                    logger.warning(
                        "Citatie-check voor %s had fouten: %s", org.name, "; ".join(summary.provider_errors)
                    )
            except Exception:
                logger.exception("Maandelijkse citatie-check mislukt voor organisatie %s (%s)", org.name, org.domain)


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    # 1e van elke maand: eerst de citatie-check (02:00 UTC), dan de reguliere
    # scan (03:00 UTC) — zodat die scan de verse C9-data al kan meenemen.
    scheduler.add_job(
        run_monthly_citation_checks,
        trigger=CronTrigger(day=1, hour=2, minute=0),
        id="monthly_citation_check",
        replace_existing=True,
    )
    scheduler.add_job(
        run_monthly_scans,
        trigger=CronTrigger(day=1, hour=3, minute=0),
        id="monthly_geo_scan",
        replace_existing=True,
    )
    return scheduler
