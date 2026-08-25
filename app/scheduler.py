"""Maandelijkse automatische scan van alle actieve organisaties.

Elke run voegt een nieuwe `Scan`-rij toe per actieve organisatie (historie,
geen overschrijving). Handmatige criteria van de vorige scan van diezelfde
organisatie worden overgenomen als startpunt (anders zou elke maandelijkse
run de niet-geautomatiseerde criteria terugzetten naar 0), zodat alleen de
Fase 1-criteria daadwerkelijk vers gemeten worden totdat Fase 2-4 leeft.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select

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


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    # 1e van elke maand, 03:00 UTC.
    scheduler.add_job(
        run_monthly_scans,
        trigger=CronTrigger(day=1, hour=3, minute=0),
        id="monthly_geo_scan",
        replace_existing=True,
    )
    return scheduler
