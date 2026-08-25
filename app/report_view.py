"""Bouwt een ScoreReport-achtige weergave op uit een opgeslagen Scan, voor de
scan-detailpagina en de PDF-export — dezelfde GAP-/prioriteiten-logica als
een verse berekening, nu gevoed vanuit de database."""

from __future__ import annotations

from app.models import Scan
from app.scoring import CriterionResult, ScoreReport, PILLAR_GAP_KEY, PILLAR_ORDER, CRITERIA


def build_report_from_scan(scan: Scan) -> ScoreReport:
    results = [
        CriterionResult(
            code=cs.code,
            raw=cs.raw_score,
            source=cs.source.value if hasattr(cs.source, "value") else cs.source,
            rationale=cs.rationale,
        )
        for cs in sorted(scan.criterion_scores, key=lambda c: list(CRITERIA.keys()).index(c.code))
    ]

    gaps: dict[str, list[CriterionResult]] = {key: [] for key in PILLAR_GAP_KEY.values()}
    for r in results:
        if r.raw <= 6:
            gaps[PILLAR_GAP_KEY[r.pillar]].append(r)

    sortable = sorted(results, key=lambda r: (r.raw, -r.weight))
    quick_wins = [r for r in sortable if CRITERIA[r.code]["quick_win"] and r.raw < 8][:3]
    strategic = [r for r in sortable if not CRITERIA[r.code]["quick_win"] and r.raw < 8][:3]
    priorities = (quick_wins[:2] + strategic[:2])[:3]
    if not priorities:
        priorities = sortable[:3]

    pillars = {}
    for p in PILLAR_ORDER:
        pillar_results = [r for r in results if r.pillar == p]
        pillars[p] = {
            "results": pillar_results,
            "weight": sum(r.weight for r in pillar_results),
            "contribution": round(sum(r.contribution for r in pillar_results), 1),
        }

    return ScoreReport(
        knockout_pass=scan.knockout_pass,
        crawler_ok=scan.crawler_ok,
        ssr_ok=scan.ssr_ok,
        total_score=scan.total_score,
        classification=scan.classification,
        classification_desc=scan.classification_desc,
        results=results,
        pillars=pillars,
        gaps=gaps,
        priorities=priorities,
    )
