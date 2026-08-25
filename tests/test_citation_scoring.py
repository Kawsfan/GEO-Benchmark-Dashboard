from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.citation.scoring import compute_c9_score
from app.models import CitationRun


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_no_runs_returns_none(session):
    assert compute_c9_score(session, organization_id=1) is None


def test_all_cited_with_link_scores_ten(session):
    now = datetime.now(timezone.utc)
    session.add_all(
        [
            CitationRun(
                organization_id=1, prompt_id=1, provider="claude", run_at=now,
                cited=True, citation_type="cited_with_link",
            )
            for _ in range(3)
        ]
    )
    session.commit()

    result = compute_c9_score(session, organization_id=1)
    assert result.score == 10.0
    assert result.run_count == 3
    assert result.cited_count == 3


def test_mixed_results_weighted_by_citation_type(session):
    now = datetime.now(timezone.utc)
    session.add_all(
        [
            CitationRun(organization_id=1, prompt_id=1, provider="claude", run_at=now, cited=True, citation_type="cited_with_link"),
            CitationRun(organization_id=1, prompt_id=2, provider="claude", run_at=now, cited=True, citation_type="mentioned"),
            CitationRun(organization_id=1, prompt_id=3, provider="claude", run_at=now, cited=False, citation_type="not_mentioned"),
            CitationRun(organization_id=1, prompt_id=4, provider="claude", run_at=now, cited=False, citation_type="not_mentioned"),
        ]
    )
    session.commit()

    # credit = 1.0 + 0.5 + 0 + 0 = 1.5 / 4 runs = 0.375 -> score 3.75 -> afgerond 3.8
    result = compute_c9_score(session, organization_id=1)
    assert result.score == 3.8
    assert result.cited_count == 2


def test_runs_outside_window_are_excluded(session):
    old = datetime.now(timezone.utc) - timedelta(days=200)
    session.add(
        CitationRun(organization_id=1, prompt_id=1, provider="claude", run_at=old, cited=True, citation_type="cited_with_link")
    )
    session.commit()

    assert compute_c9_score(session, organization_id=1, window_days=90) is None


def test_runs_for_other_organization_are_excluded(session):
    now = datetime.now(timezone.utc)
    session.add(
        CitationRun(organization_id=2, prompt_id=1, provider="claude", run_at=now, cited=True, citation_type="cited_with_link")
    )
    session.commit()

    assert compute_c9_score(session, organization_id=1) is None
