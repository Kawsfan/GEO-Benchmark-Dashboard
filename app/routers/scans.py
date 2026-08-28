from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlmodel import Session

from app.database import get_session
from app.models import Scan, ScoreSource
from app.pdf import render_scan_pdf
from app.report_html import render_report_body, render_report_css
from app.report_view import build_report_from_scan
from app.scan_service import update_manual_scores
from app.scoring import CRITERIA
from app.templating import templates

router = APIRouter(prefix="/scans", tags=["scans"])


@router.get("/{scan_id}")
def scan_detail(scan_id: int, request: Request, session: Session = Depends(get_session)):
    scan = session.get(Scan, scan_id)
    if scan is None:
        return RedirectResponse(url="/organizations", status_code=303)

    org = scan.organization
    report = build_report_from_scan(scan)
    generated_at = scan.created_at.strftime("%d-%m-%Y %H:%M")
    report_html = render_report_body(report, org.name, org.domain, generated_at)
    report_css = render_report_css(report)

    editable = [
        cs for cs in sorted(scan.criterion_scores, key=lambda c: list(CRITERIA.keys()).index(c.code))
        if cs.source != ScoreSource.automated
    ]

    return templates.TemplateResponse(
        request,
        "scan_detail.html",
        {
            "scan": scan,
            "organization": org,
            "report_html": report_html,
            "report_css": report_css,
            "editable_scores": editable,
            "criteria": CRITERIA,
        },
    )


@router.post("/{scan_id}/manual-scores")
async def save_manual_scores(scan_id: int, request: Request, session: Session = Depends(get_session)):
    scan = session.get(Scan, scan_id)
    if scan is None:
        return RedirectResponse(url="/organizations", status_code=303)

    form = await request.form()
    updates: dict[str, tuple[float, str | None]] = {}
    for code in CRITERIA:
        if code not in form:
            continue
        try:
            raw = float(form[code])
        except (TypeError, ValueError):
            continue
        rationale = form.get(f"{code}_rationale") or None
        updates[code] = (raw, rationale)

    update_manual_scores(session, scan, updates)
    return RedirectResponse(url=f"/scans/{scan_id}", status_code=303)


@router.get("/{scan_id}/pdf")
def scan_pdf(scan_id: int, session: Session = Depends(get_session)):
    scan = session.get(Scan, scan_id)
    if scan is None:
        return RedirectResponse(url="/organizations", status_code=303)
    org = scan.organization
    pdf_bytes = render_scan_pdf(scan, org)
    filename = f"geo-rapport-{org.domain.replace('.', '-')}-{scan.created_at.strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
