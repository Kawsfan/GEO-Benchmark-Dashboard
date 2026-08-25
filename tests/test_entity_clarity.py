import httpx
import pytest

from app.automation import entity_clarity
from app.automation.entity_clarity import analyze_entity_clarity


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeWikidataClient:
    """Gedraagt zich als de context-manager die build_client() teruggeeft,
    maar antwoordt met vooraf ingestelde JSON i.p.v. echte netwerkcalls."""

    def __init__(self, search_result: list[dict], claims_by_qid: dict[str, dict]):
        self._search_result = search_result
        self._claims_by_qid = claims_by_qid
        self.calls: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, params=None):
        self.calls.append(params)
        if params["action"] == "wbsearchentities":
            return _FakeResponse({"search": self._search_result})
        if params["action"] == "wbgetentities":
            qid = params["ids"]
            return _FakeResponse({"entities": {qid: {"claims": self._claims_by_qid.get(qid, {})}}})
        raise AssertionError(f"onverwachte actie: {params['action']}")


def _url_claim(url: str) -> dict:
    return {"mainsnak": {"datavalue": {"value": url}}}


def test_no_search_results_scores_zero(monkeypatch):
    fake = _FakeWikidataClient(search_result=[], claims_by_qid={})
    monkeypatch.setattr(entity_clarity, "build_client", lambda: fake)

    result = analyze_entity_clarity("Onbestaand Merk XYZ", "onbestaand-xyz.nl")

    assert result.score == 0.0
    assert result.qid is None
    assert "Geen Wikidata-item gevonden" in result.detail


def test_network_failure_raises_instead_of_returning_a_soft_zero(monkeypatch):
    class _FailingClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(entity_clarity, "build_client", lambda: _FailingClient())

    # Een netwerkfout is geen bevestigde afwezigheid van een Wikidata-item —
    # dit moet NOOIT stilzwijgend als "automatisch gemeten: score 0" landen,
    # dus de functie propageert de fout i.p.v. een zacht nulresultaat terug
    # te geven (de caller, phase3_runner, vangt dit vervolgens op).
    with pytest.raises(RuntimeError, match="Wikidata-opzoeking mislukt"):
        analyze_entity_clarity("Voorbeeld BV", "voorbeeld.nl")


def test_confident_domain_match_scores_higher_than_uncertain(monkeypatch):
    search_result = [{"id": "Q1"}, {"id": "Q2"}]
    claims = {
        "Q1": {"P856": [_url_claim("https://ander-bedrijf.nl")]},
        "Q2": {
            "P856": [_url_claim("https://www.voorbeeld.nl")],
            "P571": [{"mainsnak": {"datavalue": {"value": {"time": "+2001-01-01T00:00:00Z"}}}}],
            "P17": [{"mainsnak": {"datavalue": {"value": {"id": "Q55"}}}}],
        },
    }
    fake = _FakeWikidataClient(search_result=search_result, claims_by_qid=claims)
    monkeypatch.setattr(entity_clarity, "build_client", lambda: fake)

    result = analyze_entity_clarity("Voorbeeld BV", "voorbeeld.nl")

    assert result.qid == "Q2"
    assert result.confident_match is True
    assert "P571" in result.properties_found or "oprichtingsdatum" in result.detail
    assert result.score > entity_clarity.UNCERTAIN_MATCH_BASE_SCORE


def test_uncertain_match_falls_back_to_top_result_without_extra_fetch(monkeypatch):
    # Q1 heeft bewust GEEN attributen (leeg), zodat de score hieronder puur
    # de UNCERTAIN_MATCH_BASE_SCORE meet, los van de completeness-bijdrage.
    search_result = [{"id": "Q1"}, {"id": "Q2"}]
    claims = {
        "Q1": {},
        "Q2": {"P856": [_url_claim("https://nog-een-ander-domein.nl")]},
    }
    fake = _FakeWikidataClient(search_result=search_result, claims_by_qid=claims)
    monkeypatch.setattr(entity_clarity, "build_client", lambda: fake)

    result = analyze_entity_clarity("Voorbeeld BV", "voorbeeld.nl")

    assert result.confident_match is False
    assert result.qid == "Q1"  # eerste zoekresultaat, geen domeinmatch gevonden
    assert result.score == entity_clarity.UNCERTAIN_MATCH_BASE_SCORE
    # Q1's claims mogen niet dubbel opgevraagd zijn (1x search + 1x per kandidaat).
    get_entities_calls = [c for c in fake.calls if c["action"] == "wbgetentities"]
    assert len(get_entities_calls) == 2  # Q1 en Q2, elk precies één keer
