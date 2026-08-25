import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import scan_service
from app.automation.runner import AutomatedScanResult
from app.models import Organization, ScoreSource


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _fake_automation(*, crawler_ok=True, ssr_ok=True, c1=7.0, c2=6.0, c10=8.0):
    return AutomatedScanResult(
        crawler_ok=crawler_ok,
        ssr_ok=ssr_ok,
        knockout_detail="ok",
        criterion_scores={
            "c1_structured_data": c1,
            "c2_chunkability": c2,
            "c10_sentiment_freshness": c10,
        },
        criterion_sources={
            "c1_structured_data": "automated",
            "c2_chunkability": "automated",
            "c10_sentiment_freshness": "automated",
        },
        criterion_rationales={},
    )


def test_run_scan_persists_criterion_scores(session, monkeypatch):
    monkeypatch.setattr(scan_service, "run_phase1_automation", lambda domain: _fake_automation())

    org = Organization(name="Voorbeeld", domain="voorbeeld.nl")
    session.add(org)
    session.commit()
    session.refresh(org)

    scan = scan_service.run_scan(session, org, manual_scores={"c3_answerability": 5})

    assert scan.knockout_pass is True
    codes = {cs.code: cs for cs in scan.criterion_scores}
    assert codes["c1_structured_data"].source == ScoreSource.automated
    assert codes["c3_answerability"].source == ScoreSource.manual
    assert codes["c3_answerability"].raw_score == 5
    # 10 criteria totaal, ook de niet-ingevulde staan op 0
    assert len(codes) == 10


def test_run_scan_zero_score_on_knockout_fail(session, monkeypatch):
    monkeypatch.setattr(
        scan_service, "run_phase1_automation", lambda domain: _fake_automation(crawler_ok=False)
    )
    org = Organization(name="Geblokkeerd", domain="geblokkeerd.nl")
    session.add(org)
    session.commit()
    session.refresh(org)

    scan = scan_service.run_scan(session, org, manual_scores={code: 10 for code in [
        "c3_answerability", "c4_bluf", "c5_fact_density", "c6_entity_clarity",
        "c7_external_mentions", "c8_multimodal", "c9_share_of_model",
    ]})

    assert scan.knockout_pass is False
    assert scan.total_score == 0.0
    assert scan.classification == "Onzichtbaar"


def test_update_manual_scores_recomputes_total(session, monkeypatch):
    monkeypatch.setattr(scan_service, "run_phase1_automation", lambda domain: _fake_automation())
    org = Organization(name="Voorbeeld", domain="voorbeeld.nl")
    session.add(org)
    session.commit()
    session.refresh(org)

    scan = scan_service.run_scan(session, org)
    original_total = scan.total_score

    updated = scan_service.update_manual_scores(
        session, scan, {"c3_answerability": (9.0, "handmatig gecontroleerd")}
    )

    assert updated.total_score > original_total
    codes = {cs.code: cs for cs in updated.criterion_scores}
    assert codes["c3_answerability"].raw_score == 9.0
    assert codes["c3_answerability"].rationale == "handmatig gecontroleerd"


def test_update_manual_scores_never_overwrites_automated(session, monkeypatch):
    monkeypatch.setattr(scan_service, "run_phase1_automation", lambda domain: _fake_automation())
    org = Organization(name="Voorbeeld", domain="voorbeeld.nl")
    session.add(org)
    session.commit()
    session.refresh(org)

    scan = scan_service.run_scan(session, org)
    scan_service.update_manual_scores(session, scan, {"c1_structured_data": (0.0, "poging tot overschrijven")})

    codes = {cs.code: cs for cs in scan.criterion_scores}
    assert codes["c1_structured_data"].raw_score == 7.0  # ongewijzigd
    assert codes["c1_structured_data"].source == ScoreSource.automated
