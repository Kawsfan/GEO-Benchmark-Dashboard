import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import scan_service
from app.automation.llm_rubric import LLMRubricResult
from app.automation.phase3_runner import Phase3Result
from app.automation.runner import AutomatedScanResult
from app.models import Organization, ScoreSource


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture(autouse=True)
def _noop_phase3(monkeypatch):
    """Fase 3 (Wikidata/web-search/multimodaal) doet netwerk-/LLM-calls die
    hier niets mee te maken hebben — standaard een lege no-op, expliciet
    overschreven in de tests die Fase 3-gedrag zelf testen."""
    monkeypatch.setattr(scan_service, "run_phase3_automation", lambda *a, **kw: Phase3Result())


def _fake_automation(*, crawler_ok=True, ssr_ok=True, c1=7.0, c2=6.0, c10=8.0, page_text=None):
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
        page_text=page_text,
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


def test_run_scan_merges_successful_llm_assessment(session, monkeypatch):
    monkeypatch.setattr(
        scan_service, "run_phase1_automation", lambda domain: _fake_automation(page_text="Pagina-tekst hier.")
    )
    monkeypatch.setattr(
        scan_service,
        "assess_llm_criteria",
        lambda page_text, brand, domain: LLMRubricResult(
            scores={"c3_answerability": 7.0, "c4_bluf": 5.0, "c5_fact_density": 6.0},
            rationales={"c3_answerability": "goed onderbouwd"},
        ),
    )
    org = Organization(name="Voorbeeld", domain="voorbeeld.nl")
    session.add(org)
    session.commit()
    session.refresh(org)

    # Handmatig meegegeven c3-waarde mag niet winnen van een geslaagde LLM-beoordeling.
    scan = scan_service.run_scan(session, org, manual_scores={"c3_answerability": 1.0})

    codes = {cs.code: cs for cs in scan.criterion_scores}
    assert codes["c3_answerability"].source == ScoreSource.llm_estimate
    assert codes["c3_answerability"].raw_score == 7.0
    assert codes["c3_answerability"].rationale == "goed onderbouwd"
    assert codes["c4_bluf"].source == ScoreSource.llm_estimate
    assert codes["c4_bluf"].raw_score == 5.0


def test_run_scan_falls_back_when_llm_assessment_fails(session, monkeypatch):
    monkeypatch.setattr(
        scan_service, "run_phase1_automation", lambda domain: _fake_automation(page_text="Pagina-tekst hier.")
    )
    monkeypatch.setattr(
        scan_service,
        "assess_llm_criteria",
        lambda page_text, brand, domain: LLMRubricResult(error="geen credentials"),
    )
    org = Organization(name="Voorbeeld", domain="voorbeeld.nl")
    session.add(org)
    session.commit()
    session.refresh(org)

    scan = scan_service.run_scan(session, org, manual_scores={"c3_answerability": 4.0})

    codes = {cs.code: cs for cs in scan.criterion_scores}
    assert codes["c3_answerability"].source == ScoreSource.manual
    assert codes["c3_answerability"].raw_score == 4.0


def test_run_scan_skips_llm_assessment_without_page_text(session, monkeypatch):
    monkeypatch.setattr(scan_service, "run_phase1_automation", lambda domain: _fake_automation(page_text=None))
    called = {"n": 0}

    def fake_assess(*args, **kwargs):
        called["n"] += 1
        return LLMRubricResult(scores={"c3_answerability": 9.0})

    monkeypatch.setattr(scan_service, "assess_llm_criteria", fake_assess)
    org = Organization(name="Voorbeeld", domain="voorbeeld.nl")
    session.add(org)
    session.commit()
    session.refresh(org)

    scan_service.run_scan(session, org)
    assert called["n"] == 0


def test_run_scan_merges_phase3_results(session, monkeypatch):
    monkeypatch.setattr(scan_service, "run_phase1_automation", lambda domain: _fake_automation())
    monkeypatch.setattr(
        scan_service,
        "run_phase3_automation",
        lambda brand, domain, html, sector=None: Phase3Result(
            criterion_scores={"c6_entity_clarity": 6.0, "c8_multimodal": 3.0},
            criterion_sources={"c6_entity_clarity": "automated", "c8_multimodal": "automated"},
            criterion_rationales={"c6_entity_clarity": "Wikidata-item gevonden"},
            errors={"c7_external_mentions": "geen credentials"},
        ),
    )
    org = Organization(name="Voorbeeld", domain="voorbeeld.nl")
    session.add(org)
    session.commit()
    session.refresh(org)

    # Handmatig meegegeven c6-waarde mag niet winnen van een geslaagde Fase 3-meting.
    scan = scan_service.run_scan(session, org, manual_scores={"c6_entity_clarity": 1.0, "c7_external_mentions": 4.0})

    codes = {cs.code: cs for cs in scan.criterion_scores}
    assert codes["c6_entity_clarity"].source == ScoreSource.automated
    assert codes["c6_entity_clarity"].raw_score == 6.0
    assert codes["c8_multimodal"].raw_score == 3.0
    # C7 mislukt in Fase 3 -> valt terug op de handmatige waarde.
    assert codes["c7_external_mentions"].source == ScoreSource.manual
    assert codes["c7_external_mentions"].raw_score == 4.0
    assert "geen credentials" in scan.error_message


def test_run_scan_skips_phase3_when_disabled(session, monkeypatch):
    monkeypatch.setattr(scan_service, "run_phase1_automation", lambda domain: _fake_automation())
    called = {"n": 0}

    def fake_phase3(*args, **kwargs):
        called["n"] += 1
        return Phase3Result()

    monkeypatch.setattr(scan_service, "run_phase3_automation", fake_phase3)
    org = Organization(name="Voorbeeld", domain="voorbeeld.nl")
    session.add(org)
    session.commit()
    session.refresh(org)

    scan_service.run_scan(session, org, run_phase3=False)
    assert called["n"] == 0


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
