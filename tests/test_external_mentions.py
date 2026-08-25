import anthropic
import httpx2

from app.automation.external_mentions import MentionsAssessment, assess_external_mentions


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


def _sample_assessment() -> MentionsAssessment:
    return MentionsAssessment(
        mentions_count_estimate=12,
        notable_sources=["tweakers.net", "nu.nl"],
        score=7.0,
        rationale="Regelmatig genoemd in vakmedia het afgelopen half jaar.",
    )


def test_successful_assessment_includes_web_search_tool(monkeypatch):
    fake_client = _FakeClient(result=_sample_assessment())
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: fake_client)
    monkeypatch.delenv("GEO_DASHBOARD_DISABLE_EXTERNAL_MENTIONS", raising=False)

    result = assess_external_mentions("Voorbeeld BV", "voorbeeld.nl", sector="Detailhandel")

    assert result.succeeded is True
    assert result.score == 7.0
    assert result.notable_sources == ["tweakers.net", "nu.nl"]
    assert result.mentions_count_estimate == 12

    call = fake_client.messages.calls[0]
    assert call["tools"] == [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}]
    assert call["output_format"] is MentionsAssessment
    assert "Detailhandel" in call["messages"][0]["content"]


def test_notable_sources_capped_at_five(monkeypatch):
    assessment = MentionsAssessment(
        mentions_count_estimate=20,
        notable_sources=[f"bron{i}.nl" for i in range(8)],
        score=8.0,
        rationale="Veel vermeldingen.",
    )
    fake_client = _FakeClient(result=assessment)
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: fake_client)
    monkeypatch.delenv("GEO_DASHBOARD_DISABLE_EXTERNAL_MENTIONS", raising=False)

    result = assess_external_mentions("Voorbeeld BV", "voorbeeld.nl")

    assert len(result.notable_sources) == 5


def test_disabled_via_env_var_skips_api_call(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Anthropic() zou niet aangeroepen moeten worden als C7 is uitgeschakeld")

    monkeypatch.setattr(anthropic, "Anthropic", fail)
    monkeypatch.setenv("GEO_DASHBOARD_DISABLE_EXTERNAL_MENTIONS", "1")

    result = assess_external_mentions("Voorbeeld BV", "voorbeeld.nl")

    assert result.succeeded is False
    assert "uitgeschakeld" in result.error


def test_rate_limit_degrades_gracefully(monkeypatch):
    exc = anthropic.RateLimitError("slow down", response=_fake_httpx_response(429), body=None)
    fake_client = _FakeClient(exc=exc)
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: fake_client)
    monkeypatch.delenv("GEO_DASHBOARD_DISABLE_EXTERNAL_MENTIONS", raising=False)

    result = assess_external_mentions("Voorbeeld BV", "voorbeeld.nl")

    assert result.succeeded is False
    assert "Rate limit" in result.error
