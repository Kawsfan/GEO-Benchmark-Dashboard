import anthropic

from app.citation.detection import (
    CITED_WITH_LINK,
    MENTIONED,
    NOT_MENTIONED,
    _MentionClassification,
    detect_mention,
)


class _FakeParsedResponse:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output


class _FakeMessages:
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    def parse(self, **kwargs):
        if self._exc:
            raise self._exc
        return _FakeParsedResponse(self._result)


class _FakeClient:
    def __init__(self, result=None, exc=None):
        self.messages = _FakeMessages(result=result, exc=exc)


def test_no_stringmatch_hit_is_not_mentioned_and_skips_llm_call(monkeypatch):
    called = {"n": 0}

    def fail(*a, **kw):
        called["n"] += 1
        raise AssertionError("mag niet aangeroepen worden zonder stringmatch-treffer")

    monkeypatch.setattr(anthropic, "Anthropic", fail)

    result = detect_mention("Dit antwoord gaat over totaal iets anders.", "Voorbeeld BV", "voorbeeld.nl")

    assert result.cited is False
    assert result.citation_type == NOT_MENTIONED
    assert called["n"] == 0


def test_stringmatch_hit_triggers_llm_classification(monkeypatch):
    fake_client = _FakeClient(
        result=_MentionClassification(citation_type=CITED_WITH_LINK, sentiment="positief")
    )
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: fake_client)

    result = detect_mention(
        "Voor wandelschoenen kun je terecht bij Voorbeeld BV, zie https://voorbeeld.nl/schoenen.",
        "Voorbeeld BV",
        "voorbeeld.nl",
    )

    assert result.cited is True
    assert result.citation_type == CITED_WITH_LINK
    assert result.sentiment == "positief"


def test_domain_stringmatch_also_counts_as_hit(monkeypatch):
    fake_client = _FakeClient(result=_MentionClassification(citation_type=MENTIONED, sentiment="neutraal"))
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: fake_client)

    result = detect_mention("Kijk eens op voorbeeld.nl voor meer info.", "Een Heel Ander Merk", "voorbeeld.nl")

    assert result.cited is True


def test_classification_failure_falls_back_to_stringmatch_heuristic(monkeypatch):
    fake_client = _FakeClient(exc=RuntimeError("geen credentials"))
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: fake_client)

    result = detect_mention(
        "Voorbeeld BV is een goede keuze, zie [hun site](https://voorbeeld.nl).",
        "Voorbeeld BV",
        "voorbeeld.nl",
    )

    assert result.cited is True
    assert result.citation_type == CITED_WITH_LINK  # markdown-link met domein herkend
    assert result.note is not None


def test_classification_failure_without_link_falls_back_to_mentioned(monkeypatch):
    fake_client = _FakeClient(exc=RuntimeError("geen credentials"))
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: fake_client)

    result = detect_mention("Voorbeeld BV wordt hier genoemd zonder link.", "Voorbeeld BV", "voorbeeld.nl")

    assert result.cited is True
    assert result.citation_type == MENTIONED
