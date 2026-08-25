from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.charts import trend_chart_svg
from app.database import get_session
from app.models import Organization, TriggerType
from app.scan_service import run_scan
from app.templating import templates

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("")
def list_organizations(request: Request, session: Session = Depends(get_session)):
    organizations = session.exec(select(Organization).order_by(Organization.name)).all()
    return templates.TemplateResponse(
        request, "organizations_list.html", {"organizations": organizations}
    )


@router.get("/new")
def new_organization_form(request: Request):
    return templates.TemplateResponse(request, "organization_form.html", {"organization": None})


@router.post("/new")
def create_organization(
    name: str = Form(...),
    domain: str = Form(...),
    sector: str = Form(""),
    session: Session = Depends(get_session),
):
    org = Organization(name=name.strip(), domain=domain.strip(), sector=sector.strip() or None)
    session.add(org)
    session.commit()
    return RedirectResponse(url="/organizations", status_code=303)


@router.get("/{org_id}")
def organization_detail(org_id: int, request: Request, session: Session = Depends(get_session)):
    org = session.get(Organization, org_id)
    if org is None:
        return RedirectResponse(url="/organizations", status_code=303)
    scans = sorted(org.scans, key=lambda s: s.created_at)
    points = [(s.created_at.strftime("%d-%m"), s.total_score) for s in scans]
    chart_svg = trend_chart_svg(points)
    return templates.TemplateResponse(
        request,
        "organization_detail.html",
        {
            "organization": org,
            "scans": list(reversed(scans)),
            "chart_svg": chart_svg,
        },
    )


@router.get("/{org_id}/edit")
def edit_organization_form(org_id: int, request: Request, session: Session = Depends(get_session)):
    org = session.get(Organization, org_id)
    return templates.TemplateResponse(request, "organization_form.html", {"organization": org})


@router.post("/{org_id}/edit")
def update_organization(
    org_id: int,
    name: str = Form(...),
    domain: str = Form(...),
    sector: str = Form(""),
    is_active: bool | None = Form(None),
    session: Session = Depends(get_session),
):
    from app.models import utcnow

    org = session.get(Organization, org_id)
    if org is not None:
        org.name = name.strip()
        org.domain = domain.strip()
        org.sector = sector.strip() or None
        org.is_active = bool(is_active)
        org.updated_at = utcnow()
        session.add(org)
        session.commit()
    return RedirectResponse(url="/organizations", status_code=303)


@router.post("/{org_id}/delete")
def delete_organization(org_id: int, session: Session = Depends(get_session)):
    org = session.get(Organization, org_id)
    if org is not None:
        session.delete(org)
        session.commit()
    return RedirectResponse(url="/organizations", status_code=303)


@router.post("/{org_id}/scan")
def trigger_scan(org_id: int, session: Session = Depends(get_session)):
    org = session.get(Organization, org_id)
    if org is None:
        return RedirectResponse(url="/organizations", status_code=303)

    # Handmatige/LLM-scores van de vorige scan overnemen als startpunt, zodat
    # een nieuwe "Scan nu" niet alle nog-niet-geautomatiseerde criteria
    # terugzet naar 0 — gebruiker kan ze op de scan-detailpagina bijwerken.
    manual_scores: dict[str, float] = {}
    if org.scans:
        last_scan = max(org.scans, key=lambda s: s.created_at)
        for cs in last_scan.criterion_scores:
            if cs.source.value != "automated":
                manual_scores[cs.code] = cs.raw_score

    scan = run_scan(session, org, triggered_by=TriggerType.manual, manual_scores=manual_scores)
    return RedirectResponse(url=f"/scans/{scan.id}", status_code=303)
