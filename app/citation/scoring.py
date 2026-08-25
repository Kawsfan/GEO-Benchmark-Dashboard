"""Fase 4 — C9 Share of Model-score, afgeleid uit opgeslagen `CitationRun`-rijen.

Dit is een pure DB-read: het triggert NOOIT nieuwe provider-calls. De
citatie-checks zelf lopen los (maandelijks via de scheduler, of handmatig via
"Citatiecheck nu"); `run_scan()` leest hier gewoon de meest recente
aggregatie van, zodat een reguliere scan snel en gratis blijft.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.citation.detection import CITED_WITH_LINK, MENTIONED
from app.models import CitationRun

DEFAULT_WINDOW_DAYS = 90

# Gewicht per citatie-type in de Share-of-Model-score: een citatie mét link
# telt zwaarder dan een kale naamsvermelding.
TYPE_CREDIT = {CITED_WITH_LINK: 1.0, MENTIONED: 0.5}


@dataclass
class C9ScoreResult:
    score: float
    rationale: str
    run_count: int
    cited_count: int


def compute_c9_score(
    session: Session, organization_id: int, window_days: int = DEFAULT_WINDOW_DAYS
) -> C9ScoreResult | None:
    """Geeft None als er nog geen citatie-runs zijn binnen het venster —
    dan blijft C9 in `run_scan()` gewoon op de handmatige/overgenomen waarde
    staan, net als elk ander nog-niet-gemeten criterium."""
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    runs = session.exec(
        select(CitationRun).where(
            CitationRun.organization_id == organization_id,
            CitationRun.run_at >= since,
        )
    ).all()

    if not runs:
        return None

    total_credit = sum(TYPE_CREDIT.get(r.citation_type, 0.0) for r in runs)
    score = round(min(10.0, 10.0 * (total_credit / len(runs))), 1)
    cited_count = sum(1 for r in runs if r.cited)

    by_provider: dict[str, list[CitationRun]] = {}
    for r in runs:
        by_provider.setdefault(r.provider, []).append(r)
    provider_summary = ", ".join(
        f"{provider}: {sum(1 for r in provider_runs if r.cited)}/{len(provider_runs)}"
        for provider, provider_runs in sorted(by_provider.items())
    )

    rationale = (
        f"Op basis van {len(runs)} citatie-checks in de laatste {window_days} dagen: "
        f"{cited_count} keer genoemd ({provider_summary})."
    )

    return C9ScoreResult(score=score, rationale=rationale, run_count=len(runs), cited_count=cited_count)
