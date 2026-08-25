from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, select

from app.charts import sparkline_svg
from app.database import get_session
from app.models import Organization
from app.templating import templates

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(request: Request, session: Session = Depends(get_session)):
    organizations = session.exec(select(Organization).order_by(Organization.name)).all()

    rows = []
    for org in organizations:
        scans = sorted(org.scans, key=lambda s: s.created_at)
        latest = scans[-1] if scans else None
        history = [s.total_score for s in scans][-12:]
        previous = scans[-2] if len(scans) >= 2 else None
        delta = round(latest.total_score - previous.total_score, 1) if latest and previous else None
        rows.append(
            {
                "organization": org,
                "latest": latest,
                "delta": delta,
                "sparkline": sparkline_svg(history) if history else None,
                "scan_count": len(scans),
            }
        )

    # Vergelijking: hoogste score eerst.
    rows_sorted = sorted(
        rows, key=lambda r: r["latest"].total_score if r["latest"] else -1, reverse=True
    )

    return templates.TemplateResponse(
        request, "dashboard.html", {"rows": rows_sorted}
    )
