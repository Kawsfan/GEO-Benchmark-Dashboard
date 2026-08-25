"""Fase 2 — LLM-rubric. Anthropic-calls worden gemockt: geen echte API-calls
in tests."""

import anthropic
import httpx2
import pytest

from app.automation import llm_rubric
from app.automation.llm_rubric import LLM_RUBRIC_CODES, RubricAssessment, _CriterionScore, assess_llm_criteria


def _fake_httpx_response(status_code: int) -> httpx2.Response:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx2.Response(status_code, request=request, json={"error": {"type": "error"}})


class _FakeParsedResponse:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output


class _FakeMessages:
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return _FakeParsedResponse(self._result)


class _FakeClient:
    def __init__(self, result=None, exc=None):
        self.messages = _FakeMessages(result=result, exc=exc)


def _sample_assessment() -> RubricAssessment:
    return RubricAssessment(
        c3_answerability=_CriterionScore(score=7.5, rationale="Beantwoordt de hoofdvraag grotendeels."),
        c4_bluf=_CriterionScore(score=4.0, rationale="Kernconclusie staat pas na drie alinea's marketingtekst."),
        c5_fact_density=_CriterionScore(score=8.0, rationale="Veel concrete cijfers en een bronvermelding."),
    )


def test_empty_page_text_skips_api_call(monkeypatch):
    called = {"n": 0}

    def fake_client_ctor(*args, **kwargs):
        called["n"] += 1
        return _FakeClient(result=_sample_assessment())

    monkeypatch.setattr(anthropic, "Anthropic", fake_client_ctor)

    result = assess_llm_criteria("   ", "Voorbeeld BV", "voorbeeld.nl")

    assert result.succeeded is False
    assert result.error is not None
    assert called["n"] == 0


def test_successful_assessment_maps_scores_and_rationales(monkeypatch):
    fake_client = _FakeClient(result=_sample_assessment())
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: fake_client)

    result = assess_llm_criteria("Dit is de paginatekst.", "Voorbeeld BV", "voorbeeld.nl")

    assert result.succeeded is True
    assert set(result.scores) == set(LLM_RUBRIC_CODES)
    assert result.scores["c3_answerability"] == 7.5
    assert result.scores["c4_bluf"] == 4.0
    assert result.scores["c5_fact_density"] == 8.0
    assert "hoofdvraag" in result.rationales["c3_answerability"]

    # De vaste rubric-prompt en de paginatekst moeten daadwerkelijk meegestuurd zijn.
    call = fake_client.messages.calls[0]
    assert "voorbeeld.nl" in call["messages"][0]["content"]
    assert "Dit is de paginatekst." in call["messages"][0]["content"]
    assert call["output_format"] is RubricAssessment


def test_truncates_long_page_text(monkeypatch):
    fake_client = _FakeClient(result=_sample_assessment())
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: fake_client)

    long_text = "x" * (llm_rubric.MAX_PAGE_TEXT_CHARS + 500)
    assess_llm_criteria(long_text, "Voorbeeld BV", "voorbeeld.nl")

    call = fake_client.messages.calls[0]
    content = call["messages"][0]["content"]
    assert "afgekapt" in content
    assert content.count("x") <= llm_rubric.MAX_PAGE_TEXT_CHARS


@pytest.mark.parametrize(
    "exc_factory",
    [
        lambda: anthropic.AuthenticationError("nope", response=_fake_httpx_response(401), body=None),
        lambda: anthropic.RateLimitError("slow down", response=_fake_httpx_response(429), body=None),
    ],
)
def test_api_errors_degrade_gracefully(monkeypatch, exc_factory):
    fake_client = _FakeClient(exc=exc_factory())
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: fake_client)

    result = assess_llm_criteria("Paginatekst.", "Voorbeeld BV", "voorbeeld.nl")

    assert result.succeeded is False
    assert result.error is not None
    assert result.scores == {}


def test_no_credentials_at_all_degrades_gracefully(monkeypatch):
    # Zonder ANTHROPIC_API_KEY/ant-profiel gooit de SDK al bij het opbouwen
    # van het request een TypeError (niet AuthenticationError, die komt pas
    # bij een 401-response) — dit mag nooit de scan laten crashen.
    def raise_type_error(**kwargs):
        raise TypeError(
            "Could not resolve authentication method. Expected one of api_key, "
            "auth_token, or credentials to be set."
        )

    fake_client = _FakeClient()
    fake_client.messages.parse = raise_type_error
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: fake_client)

    result = assess_llm_criteria("Paginatekst.", "Voorbeeld BV", "voorbeeld.nl")

    assert result.succeeded is False
    assert "credentials" in result.error.lower() or "geconfigureerd" in result.error.lower()
