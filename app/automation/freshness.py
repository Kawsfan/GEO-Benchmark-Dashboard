"""
C10 (freshness-deel) — Actualiteit, geautomatiseerd.

Parseert `dateModified` uit JSON-LD, `article:modified_time` (OpenGraph)
en `DCTERMS.modified`/`DC.date.modified` meta-tags, en scoort op recentheid.

Let op (zie ARCHITECTURE.md): dit dekt alleen het freshness-deel van C10
"Contextueel Sentiment & Actualiteit". Het sentiment-deel blijft
handmatig/LLM-schatting tot Fase 4.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

# (max_dagen_geleden, score)
RECENCY_BANDS = [
    (31, 10.0),
    (92, 8.0),
    (182, 6.0),
    (365, 4.0),
    (730, 2.0),
]


@dataclass
class FreshnessResult:
    score: float
    modified_at: datetime | None
    source_field: str | None
    detail: str


def _parse_date(value: str) -> datetime | None:
    try:
        dt = dateutil_parser.parse(value)
    except (ValueError, OverflowError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _from_jsonld(html: str) -> tuple[datetime | None, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            candidates = [node] + (node.get("@graph") if isinstance(node.get("@graph"), list) else [])
            for c in candidates:
                if not isinstance(c, dict):
                    continue
                value = c.get("dateModified")
                if value:
                    dt = _parse_date(str(value))
                    if dt:
                        return dt, "jsonld:dateModified"
    return None, None


def _from_meta(html: str) -> tuple[datetime | None, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    meta_names = [
        ("property", "article:modified_time"),
        ("name", "DCTERMS.modified"),
        ("name", "dcterms.modified"),
        ("name", "DC.date.modified"),
    ]
    for attr, name in meta_names:
        tag = soup.find("meta", attrs={attr: name})
        if tag and tag.get("content"):
            dt = _parse_date(tag["content"])
            if dt:
                return dt, f"meta:{name}"
    return None, None


def analyze_freshness(html: str) -> FreshnessResult:
    modified_at, source_field = _from_jsonld(html)
    if modified_at is None:
        modified_at, source_field = _from_meta(html)

    if modified_at is None:
        return FreshnessResult(
            score=0.0,
            modified_at=None,
            source_field=None,
            detail="Geen dateModified/article:modified_time/DCTERMS.modified gevonden.",
        )

    age_days = (datetime.now(timezone.utc) - modified_at).days
    score = 0.0
    for max_days, band_score in RECENCY_BANDS:
        if age_days <= max_days:
            score = band_score
            break

    return FreshnessResult(
        score=score,
        modified_at=modified_at,
        source_field=source_field,
        detail=f"Laatst gewijzigd {age_days} dagen geleden ({source_field}).",
    )
