"""
C1 — Gestructureerde data & Feeds, geautomatiseerd.

Parseert <script type="application/ld+json"> (schema.org) en
DCTERMS/Dublin Core <meta>-tags. Scoort op aanwezigheid + volledigheid van
de voor GEO relevante types: Organization, Article, FAQPage, Product,
Dataset.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

RELEVANT_TYPES = {"Organization", "Article", "FAQPage", "Product", "Dataset"}

# Verwachte kernvelden per type, gebruikt om "volledigheid" te scoren.
EXPECTED_FIELDS = {
    "Organization": {"name", "url", "logo", "sameAs"},
    "Article": {"headline", "author", "datePublished", "dateModified"},
    "FAQPage": {"mainEntity"},
    "Product": {"name", "description", "offers"},
    "Dataset": {"name", "description", "license"},
}

DCTERMS_PREFIXES = ("dcterms.", "dc.")


@dataclass
class StructuredDataResult:
    score: float
    types_found: set[str] = field(default_factory=set)
    dcterms_fields: set[str] = field(default_factory=set)
    detail: str = ""


def _iter_jsonld_nodes(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            for item in data:
                yield from _flatten_node(item)
        else:
            yield from _flatten_node(data)


def _flatten_node(node):
    if not isinstance(node, dict):
        return
    if "@graph" in node and isinstance(node["@graph"], list):
        for sub in node["@graph"]:
            yield from _flatten_node(sub)
    else:
        yield node


def _node_types(node: dict) -> set[str]:
    t = node.get("@type")
    if t is None:
        return set()
    if isinstance(t, str):
        return {t}
    if isinstance(t, list):
        return {x for x in t if isinstance(x, str)}
    return set()


def _dcterms_meta_fields(html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    found = set()
    for meta in soup.find_all("meta"):
        name = (meta.get("name") or meta.get("property") or "").strip().lower()
        if not name:
            continue
        if name.startswith(DCTERMS_PREFIXES):
            found.add(name)
    return found


def analyze_structured_data(html: str) -> StructuredDataResult:
    types_found: set[str] = set()
    completeness_scores: list[float] = []

    for node in _iter_jsonld_nodes(html):
        node_types = _node_types(node)
        relevant = node_types & RELEVANT_TYPES
        if not relevant:
            continue
        types_found |= relevant
        for t in relevant:
            expected = EXPECTED_FIELDS.get(t, set())
            if not expected:
                continue
            present = {k for k in expected if node.get(k)}
            completeness_scores.append(len(present) / len(expected))

    dcterms_fields = _dcterms_meta_fields(html)

    # Scoreopbouw (0-10):
    #   0-4  aanwezigheid: 4 punten x (aantal gevonden relevante types / totaal relevante types, gecapt)
    #   0-4  volledigheid: gemiddelde veld-volledigheid van gevonden types
    #   0-2  DCTERMS/Dublin Core meta-tags aanwezig
    presence_score = 4.0 * min(1.0, len(types_found) / 2)  # 2+ relevante types = volle presence-score
    completeness_score = 4.0 * (sum(completeness_scores) / len(completeness_scores)) if completeness_scores else 0.0
    dcterms_score = 2.0 if dcterms_fields else 0.0

    score = round(min(10.0, presence_score + completeness_score + dcterms_score), 1)

    if not types_found and not dcterms_fields:
        detail = "Geen JSON-LD schema.org-markup of DCTERMS/Dublin Core meta-tags gevonden."
    else:
        parts = []
        if types_found:
            parts.append(f"schema.org-types gevonden: {', '.join(sorted(types_found))}")
        if dcterms_fields:
            parts.append(f"DCTERMS/DC meta-tags: {', '.join(sorted(dcterms_fields))}")
        detail = "; ".join(parts)

    return StructuredDataResult(
        score=score,
        types_found=types_found,
        dcterms_fields=dcterms_fields,
        detail=detail,
    )
