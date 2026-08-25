from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.citation.budget import budget_remaining, spent_this_month
from app.citation.runner import run_citation_check
from app.citation.scoring import compute_c9_score
from app.database import get_session
from app.models import CitationPrompt, CitationRun, Organization
from app.templating import templates

router = APIRouter(tags=["citations"])


# ---------------------------------------------------------------------------
# Promptset-beheer (per sector, gedeeld tussen organisaties in die sector)
# ---------------------------------------------------------------------------


@router.get("/promptsets")
def list_promptsets(request: Request, session: Session = Depends(get_session)):
    prompts = session.exec(select(CitationPrompt).order_by(CitationPrompt.sector, CitationPrompt.id)).all()
    by_sector: dict[str, list[CitationPrompt]] = {}
    for p in prompts:
        by_sector.setdefault(p.sector, []).append(p)
    return templates.TemplateResponse(
        request, "promptsets.html", {"by_sector": dict(sorted(by_sector.items()))}
    )


@router.post("/promptsets/new")
def create_promptset(
    sector: str = Form(...),
    prompt_text: str = Form(...),
    session: Session = Depends(get_session),
):
    prompt = CitationPrompt(sector=sector.strip(), prompt_text=prompt_text.strip())
    session.add(prompt)
    session.commit()
    return RedirectResponse(url="/promptsets", status_code=303)


@router.post("/promptsets/{prompt_id}/toggle")
def toggle_promptset(prompt_id: int, session: Session = Depends(get_session)):
    prompt = session.get(CitationPrompt, prompt_id)
    if prompt is not None:
        prompt.is_active = not prompt.is_active
        session.add(prompt)
        session.commit()
    return RedirectResponse(url="/promptsets", status_code=303)


@router.post("/promptsets/{prompt_id}/delete")
def delete_promptset(prompt_id: int, session: Session = Depends(get_session)):
    prompt = session.get(CitationPrompt, prompt_id)
    if prompt is not None:
        session.delete(prompt)
        session.commit()
    return RedirectResponse(url="/promptsets", status_code=303)


# ---------------------------------------------------------------------------
# Citatie-resultaten per organisatie
# ---------------------------------------------------------------------------


@router.get("/organizations/{org_id}/citations")
def organization_citations(org_id: int, request: Request, session: Session = Depends(get_session)):
    org = session.get(Organization, org_id)
    if org is None:
        return RedirectResponse(url="/organizations", status_code=303)

    runs = session.exec(
        select(CitationRun)
        .where(CitationRun.organization_id == org_id)
        .order_by(CitationRun.run_at.desc())
        .limit(50)
    ).all()

    prompt_ids = {r.prompt_id for r in runs}
    prompts_by_id = {}
    if prompt_ids:
        for p in session.exec(select(CitationPrompt).where(CitationPrompt.id.in_(prompt_ids))).all():
            prompts_by_id[p.id] = p

    c9 = compute_c9_score(session, org_id)
    spent = spent_this_month(session, org_id)
    remaining = budget_remaining(spent, org.citation_budget_usd_per_month)

    has_active_prompts = (
        org.sector is not None
        and session.exec(
            select(CitationPrompt).where(CitationPrompt.sector == org.sector, CitationPrompt.is_active == True)  # noqa: E712
        ).first()
        is not None
    )

    return templates.TemplateResponse(
        request,
        "citations.html",
        {
            "organization": org,
            "runs": runs,
            "prompts_by_id": prompts_by_id,
            "c9": c9,
            "spent_this_month": spent,
            "budget_remaining": remaining,
            "has_active_prompts": has_active_prompts,
        },
    )


@router.post("/organizations/{org_id}/citations/run")
def trigger_citation_check(org_id: int, session: Session = Depends(get_session)):
    org = session.get(Organization, org_id)
    if org is not None:
        run_citation_check(session, org)
    return RedirectResponse(url=f"/organizations/{org_id}/citations", status_code=303)
