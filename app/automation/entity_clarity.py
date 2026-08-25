"""
C6 — Entiteits-helderheid / Knowledge Graph, geautomatiseerd via de publieke
Wikidata-API (`wbsearchentities` + `wbgetentities`, geen API-key nodig).

Zoekt een Wikidata-item op merknaam en probeert een confidente match te
maken via het `officiële website`-attribuut (P856) tegen het scan-domein.
Zonder domeinmatch valt de check terug op het eerste zoekresultaat als
onzekere kandidaat, met een lagere score en een expliciete markering in de
rationale — zodat een mens dat kan controleren.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from app.automation.http_client import build_client

WIKIDATA_API = "https://www.wikidata.org/w/api.php"

# Attributen die we als "volledig ingevuld Wikidata-item" beschouwen.
EXPECTED_PROPERTIES: dict[str, str] = {
    "P571": "oprichtingsdatum",
    "P17": "land",
    "P159": "hoofdkantoor",
    "P452": "branche/industrie",
    "P856": "officiële website",
    "P154": "logo",
}

CONFIDENT_MATCH_BASE_SCORE = 5.0
UNCERTAIN_MATCH_BASE_SCORE = 3.0
COMPLETENESS_MAX_SCORE = 5.0


@dataclass
class EntityClarityResult:
    score: float
    qid: str | None = None
    confident_match: bool = False
    properties_found: list[str] = field(default_factory=list)
    detail: str = ""


def _domain_host(value: str) -> str:
    value = (value or "").strip().lower()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    host = urlparse(value).netloc
    return host[4:] if host.startswith("www.") else host


def _search_candidates(client: httpx.Client, name: str) -> list[dict]:
    resp = client.get(
        WIKIDATA_API,
        params={
            "action": "wbsearchentities",
            "search": name,
            "language": "nl",
            "format": "json",
            "type": "item",
            "limit": 5,
        },
    )
    resp.raise_for_status()
    return resp.json().get("search", [])


def _fetch_entity_claims(client: httpx.Client, qid: str) -> dict:
    resp = client.get(
        WIKIDATA_API,
        params={"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"},
    )
    resp.raise_for_status()
    return resp.json().get("entities", {}).get(qid, {}).get("claims", {})


def _claim_string_values(claims: dict, prop: str) -> list[str]:
    values = []
    for claim in claims.get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, str):
            values.append(value)
    return values


def analyze_entity_clarity(brand_name: str, domain: str) -> EntityClarityResult:
    target_host = _domain_host(domain)

    try:
        with build_client() as client:
            candidates = _search_candidates(client, brand_name)
            if not candidates:
                return EntityClarityResult(
                    score=0.0, detail=f"Geen Wikidata-item gevonden voor '{brand_name}'."
                )

            matched_qid: str | None = None
            confident = False
            claims: dict = {}
            # Bewaar de claims van het eerste zoekresultaat tijdens de loop,
            # zodat we die bij geen confident match kunnen hergebruiken i.p.v.
            # nogmaals op te vragen.
            first_qid: str | None = None
            first_claims: dict | None = None

            for i, candidate in enumerate(candidates):
                qid = candidate.get("id")
                if not qid:
                    continue
                candidate_claims = _fetch_entity_claims(client, qid)
                if i == 0:
                    first_qid, first_claims = qid, candidate_claims
                websites = [_domain_host(u) for u in _claim_string_values(candidate_claims, "P856")]
                if target_host and target_host in websites:
                    matched_qid, claims, confident = qid, candidate_claims, True
                    break

            if matched_qid is None and first_qid is not None:
                # Geen bevestigde domeinmatch: het eerste zoekresultaat is een
                # onzekere kandidaat (lagere score, expliciet gemarkeerd).
                matched_qid, claims = first_qid, first_claims or {}
    except httpx.HTTPError as exc:
        # Een mislukte opzoeking is geen bevestigde afwezigheid — dit mag niet
        # als "automatisch gemeten: score 0" geregistreerd worden (dat zou een
        # meting suggereren die niet heeft plaatsgevonden). De caller
        # (phase3_runner) vangt dit op en laat C6 terugvallen op de
        # handmatige/overgenomen waarde, net als bij de andere Fase 3-checks.
        raise RuntimeError(f"Wikidata-opzoeking mislukt: {exc}") from exc

    if matched_qid is None:
        return EntityClarityResult(score=0.0, detail=f"Geen Wikidata-item gevonden voor '{brand_name}'.")

    properties_found = [p for p in EXPECTED_PROPERTIES if claims.get(p)]
    presence_score = CONFIDENT_MATCH_BASE_SCORE if confident else UNCERTAIN_MATCH_BASE_SCORE
    completeness_score = COMPLETENESS_MAX_SCORE * (len(properties_found) / len(EXPECTED_PROPERTIES))
    score = round(min(10.0, presence_score + completeness_score), 1)

    match_desc = (
        "bevestigd via een match op de officiële website (P856)"
        if confident
        else "ONBEVESTIGDE naam-match — controleer handmatig of dit het juiste Wikidata-item is"
    )
    found_labels = ", ".join(EXPECTED_PROPERTIES[p] for p in properties_found) or "geen"
    detail = f"Wikidata-item {matched_qid} ({match_desc}). Aanwezige attributen: {found_labels}."

    return EntityClarityResult(
        score=score,
        qid=matched_qid,
        confident_match=confident,
        properties_found=properties_found,
        detail=detail,
    )
