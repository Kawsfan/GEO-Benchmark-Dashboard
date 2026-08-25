"""SQLModel-datamodel — zie ARCHITECTURE.md voor het volledige ontwerp.

Let op: bewust GEEN `from __future__ import annotations` hier. In
combinatie met SQLAlchemy 2.x's annotation-based mapping laat dat
`Relationship`-velden met een forward-ref generic (`List["Scan"]`)
crashen ("seems to be using a generic class as the argument to
relationship()") omdat de string-annotatie dan als een Mapped[...]-stijl
annotatie geïnterpreteerd wordt. Zonder de future-import evalueert
SQLModel's metaclass de annotaties direct en werkt het gewoon.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List

from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TriggerType(str, Enum):
    manual = "manual"
    scheduled = "scheduled"


class ScanStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ScoreSource(str, Enum):
    automated = "automated"
    llm_estimate = "llm_estimate"
    manual = "manual"


class Organization(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    domain: str
    sector: str | None = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    # Fase 4 (Share of Model) kostenlimiet: harde bovengrens op de som van
    # CitationRun.cost_usd binnen de lopende kalendermaand voor deze
    # organisatie. None = geen limiet (bewust opt-in, niet de default).
    citation_budget_usd_per_month: float | None = Field(default=5.0)

    scans: List["Scan"] = Relationship(back_populates="organization")


class Scan(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    triggered_by: TriggerType = Field(default=TriggerType.manual)
    created_at: datetime = Field(default_factory=utcnow, index=True)

    knockout_pass: bool = False
    crawler_ok: bool = False
    ssr_ok: bool = False

    total_score: float = 0.0
    classification: str = ""
    classification_desc: str = ""

    status: ScanStatus = Field(default=ScanStatus.pending)
    error_message: str | None = None

    organization: Organization | None = Relationship(back_populates="scans")
    criterion_scores: List["ScanCriterionScore"] = Relationship(back_populates="scan")


class ScanCriterionScore(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    scan_id: int = Field(foreign_key="scan.id", index=True)
    code: str
    raw_score: float
    weight: float
    contribution: float
    source: ScoreSource = Field(default=ScoreSource.manual)
    rationale: str | None = None
    measured_at: datetime | None = None

    scan: Scan | None = Relationship(back_populates="criterion_scores")


class CitationPrompt(SQLModel, table=True):
    """Fase 4 (Share of Model) — beheerbare promptset per sector."""

    id: int | None = Field(default=None, primary_key=True)
    sector: str
    prompt_text: str
    is_active: bool = Field(default=True)


class CitationRun(SQLModel, table=True):
    """Fase 4 (Share of Model) — resultaat van één (prompt × provider)-combinatie."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    prompt_id: int = Field(foreign_key="citationprompt.id")
    provider: str
    run_at: datetime = Field(default_factory=utcnow, index=True)
    cited: bool = False
    citation_type: str = "not_mentioned"  # not_mentioned | mentioned | cited_with_link
    sentiment: str | None = None
    raw_response: str | None = None
    cost_usd: float | None = None
