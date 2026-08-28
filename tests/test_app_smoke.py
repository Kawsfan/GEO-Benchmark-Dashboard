"""End-to-end smoke test van de FastAPI-app via TestClient, met de Fase
1-automatisering gemockt (geen echte netwerkcalls in tests)."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import scan_service
from app.automation.runner import AutomatedScanResult


def _fake_automation(domain: str):
    return AutomatedScanResult(
        crawler_ok=True,
        ssr_ok=True,
        knockout_detail="ok",
        criterion_scores={
            "c1_structured_data": 7.0,
            "c2_chunkability": 6.5,
            "c10_sentiment_freshness": 8.0,
        },
        criterion_sources={
            "c1_structured_data": "automated",
            "c2_chunkability": "automated",
            "c10_sentiment_freshness": "automated",
        },
        criterion_rationales={"c1_structured_data": "JSON-LD Organization gevonden"},
    )


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(scan_service, "run_phase1_automation", _fake_automation)
    from app.database import engine, init_db
    from app.main import app
    from app.models import Organization, Scan, ScanCriterionScore
    from sqlmodel import SQLModel

    # Schone lei per test: alles droppen en opnieuw aanmaken.
    SQLModel.metadata.drop_all(engine)
    init_db()
    with TestClient(app) as c:
        yield c


def test_dashboard_empty_state(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Nog geen organisaties" in resp.text


def test_full_flow_create_scan_view_and_pdf(client):
    resp = client.post(
        "/organizations/new",
        data={"name": "Test BV", "domain": "test-bv.nl", "sector": "Retail"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    resp = client.get("/organizations")
    assert "Test BV" in resp.text

    from app.database import engine
    with Session(engine) as session:
        from app.models import Organization
        org = session.exec(select(Organization).where(Organization.domain == "test-bv.nl")).one()

    resp = client.post(f"/organizations/{org.id}/scan", follow_redirects=False)
    assert resp.status_code == 303
    scan_url = resp.headers["location"]

    resp = client.get(scan_url)
    assert resp.status_code == 200
    assert "Automatisch gemeten" in resp.text
    assert "Handmatig ingevoerd" in resp.text
    # Regressie: de rapport-CSS moet daadwerkelijk op de pagina staan, niet
    # alleen in de PDF-export (zie tests/test_report_html.py).
    assert ".geo-report {" in resp.text
    assert ":root {" not in resp.text  # zou het lichte dashboard-thema overschrijven

    resp = client.get("/dashboard")
    assert "Test BV" in resp.text
    assert "pill" in resp.text

    scan_id = scan_url.rstrip("/").split("/")[-1]
    resp = client.post(
        f"/scans/{scan_id}/manual-scores",
        data={"c3_answerability": "8", "c3_answerability_rationale": "handmatig gecontroleerd"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    resp = client.get(scan_url)
    assert "handmatig gecontroleerd" in resp.text
