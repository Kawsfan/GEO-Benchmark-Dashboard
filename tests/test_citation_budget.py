from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.citation.budget import budget_remaining, is_budget_exhausted, spent_this_month
from app.models import CitationRun


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_spent_this_month_sums_only_current_month(session):
    now = datetime.now(timezone.utc)
    last_month = now.replace(day=1) - timedelta(days=1)

    session.add_all(
        [
            CitationRun(organization_id=1, prompt_id=1, provider="claude", run_at=now, cost_usd=0.5),
            CitationRun(organization_id=1, prompt_id=1, provider="claude", run_at=now, cost_usd=0.25),
            CitationRun(organization_id=1, prompt_id=1, provider="claude", run_at=last_month, cost_usd=100.0),
            CitationRun(organization_id=2, prompt_id=1, provider="claude", run_at=now, cost_usd=9.0),
        ]
    )
    session.commit()

    assert spent_this_month(session, organization_id=1) == 0.75


def test_spent_this_month_zero_without_runs(session):
    assert spent_this_month(session, organization_id=999) == 0.0


def test_budget_remaining_none_means_unlimited():
    assert budget_remaining(spent=100.0, budget=None) is None


def test_budget_remaining_computes_difference():
    assert budget_remaining(spent=3.0, budget=5.0) == 2.0
    assert budget_remaining(spent=6.0, budget=5.0) == -1.0


def test_is_budget_exhausted():
    assert is_budget_exhausted(spent=5.0, budget=5.0) is True
    assert is_budget_exhausted(spent=4.99, budget=5.0) is False
    assert is_budget_exhausted(spent=1000.0, budget=None) is False
