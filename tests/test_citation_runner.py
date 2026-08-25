import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.citation import runner as runner_module
from app.citation.detection import DetectionResult
from app.citation.providers import ProviderResponse
from app.citation.runner import run_citation_check
from app.models import CitationPrompt, CitationRun, Organization


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _make_org(session, *, sector="Detailhandel", budget=5.0) -> Organization:
    org = Organization(name="Voorbeeld BV", domain="voorbeeld.nl", sector=sector, citation_budget_usd_per_month=budget)
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


def _make_prompts(session, sector: str, n: int) -> list[CitationPrompt]:
    prompts = [CitationPrompt(sector=sector, prompt_text=f"Vraag {i}") for i in range(n)]
    session.add_all(prompts)
    session.commit()
    for p in prompts:
        session.refresh(p)
    return prompts


def test_no_sector_skips_entirely(session, monkeypatch):
    org = _make_org(session, sector=None)
    monkeypatch.delenv("GEO_DASHBOARD_DISABLE_CITATION_TRACKING", raising=False)

    summary = run_citation_check(session, org)

    assert summary.no_prompts is True
    assert summary.runs_created == 0


def test_no_active_prompts_for_sector_skips(session, monkeypatch):
    org = _make_org(session, sector="Onbekende sector")
    monkeypatch.delenv("GEO_DASHBOARD_DISABLE_CITATION_TRACKING", raising=False)

    summary = run_citation_check(session, org)

    assert summary.no_prompts is True


def test_disabled_via_env_var_skips_without_touching_providers(session, monkeypatch):
    org = _make_org(session)
    _make_prompts(session, "Detailhandel", 2)
    monkeypatch.setenv("GEO_DASHBOARD_DISABLE_CITATION_TRACKING", "1")

    def fail(*a, **kw):
        raise AssertionError("providers mogen niet aangeroepen worden als uitgeschakeld")

    monkeypatch.setattr(runner_module, "enabled_providers", fail)

    summary = run_citation_check(session, org)

    assert summary.disabled is True
    assert summary.runs_created == 0


def test_successful_run_creates_citation_rows(session, monkeypatch):
    org = _make_org(session)
    _make_prompts(session, "Detailhandel", 2)
    monkeypatch.delenv("GEO_DASHBOARD_DISABLE_CITATION_TRACKING", raising=False)
    monkeypatch.setattr(runner_module, "enabled_providers", lambda: ["claude"])
    monkeypatch.setattr(
        runner_module,
        "PROVIDERS",
        {"claude": lambda prompt: ProviderResponse(text=f"antwoord op: {prompt}", cost_usd=0.1)},
    )
    monkeypatch.setattr(
        runner_module,
        "detect_mention",
        lambda text, brand, domain: DetectionResult(cited=True, citation_type="mentioned", sentiment="neutraal"),
    )

    summary = run_citation_check(session, org)

    assert summary.runs_created == 2
    assert summary.total_cost_usd == pytest.approx(0.2)
    rows = session.exec(select(CitationRun).where(CitationRun.organization_id == org.id)).all()
    assert len(rows) == 2
    assert all(r.citation_type == "mentioned" for r in rows)
    assert all(r.provider == "claude" for r in rows)


def test_budget_exhaustion_stops_further_calls(session, monkeypatch):
    org = _make_org(session, budget=0.15)
    _make_prompts(session, "Detailhandel", 3)
    monkeypatch.delenv("GEO_DASHBOARD_DISABLE_CITATION_TRACKING", raising=False)
    monkeypatch.setattr(runner_module, "enabled_providers", lambda: ["claude"])
    monkeypatch.setattr(
        runner_module, "PROVIDERS", {"claude": lambda prompt: ProviderResponse(text="x", cost_usd=0.1)}
    )
    monkeypatch.setattr(
        runner_module,
        "detect_mention",
        lambda text, brand, domain: DetectionResult(cited=False, citation_type="not_mentioned"),
    )

    summary = run_citation_check(session, org)

    # Budget 0.15: eerste call (spent 0.0 < 0.15) mag door, kost 0.1 -> spent=0.1.
    # Tweede call (spent 0.1 < 0.15) mag ook nog door -> spent=0.2.
    # Derde call (spent 0.2 >= 0.15) wordt geskipt.
    assert summary.runs_created == 2
    assert summary.skipped_due_to_budget == 1


def test_provider_error_does_not_block_other_combinations(session, monkeypatch):
    org = _make_org(session)
    _make_prompts(session, "Detailhandel", 2)
    monkeypatch.delenv("GEO_DASHBOARD_DISABLE_CITATION_TRACKING", raising=False)
    monkeypatch.setattr(runner_module, "enabled_providers", lambda: ["claude"])

    calls = {"n": 0}

    def flaky_provider(prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            return ProviderResponse(text=None, error="tijdelijke fout")
        return ProviderResponse(text="ok", cost_usd=0.05)

    monkeypatch.setattr(runner_module, "PROVIDERS", {"claude": flaky_provider})
    monkeypatch.setattr(
        runner_module,
        "detect_mention",
        lambda text, brand, domain: DetectionResult(cited=False, citation_type="not_mentioned"),
    )

    summary = run_citation_check(session, org)

    assert summary.runs_created == 1
    assert len(summary.provider_errors) == 1
