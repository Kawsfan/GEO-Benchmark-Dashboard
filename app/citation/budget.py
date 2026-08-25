"""Fase 4 — kostenlimiet per organisatie.

`Organization.citation_budget_usd_per_month` is een harde bovengrens op de
som van `CitationRun.cost_usd` binnen de lopende kalendermaand. De runner
checkt dit vóór elke provider-call; de laatste call die de limiet net
overschrijdt mag nog afronden (check-before-call, niet check-after), zodat
we nooit een lopende call afbreken."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models import CitationRun


def _start_of_current_month() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def spent_this_month(session: Session, organization_id: int) -> float:
    runs = session.exec(
        select(CitationRun).where(
            CitationRun.organization_id == organization_id,
            CitationRun.run_at >= _start_of_current_month(),
        )
    ).all()
    return round(sum(r.cost_usd or 0.0 for r in runs), 6)


def budget_remaining(spent: float, budget: float | None) -> float | None:
    """None betekent 'geen limiet'. Anders: hoeveel er nog over is (kan 0 of negatief zijn)."""
    if budget is None:
        return None
    return round(budget - spent, 6)


def is_budget_exhausted(spent: float, budget: float | None) -> bool:
    if budget is None:
        return False
    return spent >= budget
