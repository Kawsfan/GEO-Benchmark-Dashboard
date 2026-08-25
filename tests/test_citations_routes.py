"""Smoke-tests voor de promptset- en citatie-routes via TestClient. De
citatie-check zelf wordt gemockt (geen echte provider-calls)."""

import pytest
from fastapi.testclient import TestClient

from app.citation import runner as runner_module


@pytest.fixture()
def client(monkeypatch):
    from app.database import engine, init_db
    from app.main import app
    from sqlmodel import SQLModel

    SQLModel.metadata.drop_all(engine)
    init_db()
    with TestClient(app) as c:
        yield c


def test_promptsets_crud_flow(client):
    resp = client.get("/promptsets")
    assert resp.status_code == 200
    assert "Nog geen prompts" in resp.text

    resp = client.post(
        "/promptsets/new",
        data={"sector": "Detailhandel", "prompt_text": "Welke winkelketen is het beste voor wandelschoenen?"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    resp = client.get("/promptsets")
    assert "Detailhandel" in resp.text
    assert "wandelschoenen" in resp.text

    # Prompt-id ophalen uit de DB om toggle/delete te testen.
    from sqlmodel import Session, select

    from app.database import engine
    from app.models import CitationPrompt

    with Session(engine) as session:
        prompt = session.exec(select(CitationPrompt)).one()

    resp = client.post(f"/promptsets/{prompt.id}/toggle", follow_redirects=False)
    assert resp.status_code == 303
    resp = client.get("/promptsets")
    assert "Inactief" in resp.text

    resp = client.post(f"/promptsets/{prompt.id}/delete", follow_redirects=False)
    assert resp.status_code == 303
    resp = client.get("/promptsets")
    assert "Nog geen prompts" in resp.text


def test_organization_citations_page_and_manual_trigger(client, monkeypatch):
    resp = client.post(
        "/organizations/new",
        data={"name": "Citatie Test BV", "domain": "citatietest.nl", "sector": "Detailhandel"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    from sqlmodel import Session, select

    from app.database import engine
    from app.models import Organization

    with Session(engine) as session:
        org = session.exec(select(Organization).where(Organization.domain == "citatietest.nl")).one()

    resp = client.get(f"/organizations/{org.id}/citations")
    assert resp.status_code == 200
    assert "Nog geen citatie-data" in resp.text
    assert "Geen actieve prompts" in resp.text  # nog geen prompts voor deze sector

    called = {"n": 0}

    def fake_run_citation_check(session, organization):
        called["n"] += 1
        from app.citation.runner import CitationCheckSummary

        return CitationCheckSummary(runs_created=0, no_prompts=True)

    monkeypatch.setattr("app.routers.citations.run_citation_check", fake_run_citation_check)

    resp = client.post(f"/organizations/{org.id}/citations/run", follow_redirects=False)
    assert resp.status_code == 303
    assert called["n"] == 1
