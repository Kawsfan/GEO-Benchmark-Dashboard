"""Provider-integraties. Claude wordt gemockt via de echte (geïnstalleerde)
anthropic-SDK, net als elders in de testsuite. OpenAI/Perplexity/Gemini
worden getest via een gefaked module in sys.modules — dat pakket hoeft dus
niet geïnstalleerd te zijn om de success-paden te testen, en het natuurlijke
ImportError-pad (pakket écht niet geïnstalleerd) wordt apart getest."""

from __future__ import annotations

import sys
import types

from app.citation.providers import (
    PROVIDERS,
    _estimate_cost,
    call_claude,
    call_gemini,
    call_openai,
    call_perplexity,
    enabled_providers,
)

# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeUsage:
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeClaudeResponse:
    def __init__(self, text, input_tokens=100, output_tokens=50):
        self.content = [_FakeTextBlock(text)]
        self.usage = _FakeUsage(input_tokens, output_tokens)


class _FakeClaudeMessages:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    def create(self, **kwargs):
        if self._exc:
            raise self._exc
        return self._response


class _FakeClaudeClient:
    def __init__(self, response=None, exc=None):
        self.messages = _FakeClaudeMessages(response=response, exc=exc)


def test_call_claude_success(monkeypatch):
    import anthropic

    fake_client = _FakeClaudeClient(response=_FakeClaudeResponse("Antwoord over het merk."))
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: fake_client)

    result = call_claude("Wat is het beste merk?")

    assert result.succeeded is True
    assert result.text == "Antwoord over het merk."
    assert result.cost_usd is not None and result.cost_usd > 0


def test_call_claude_failure_degrades_gracefully(monkeypatch):
    import anthropic

    fake_client = _FakeClaudeClient(exc=RuntimeError("boom"))
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: fake_client)

    result = call_claude("Wat is het beste merk?")

    assert result.succeeded is False
    assert "Claude-call mislukt" in result.error


# ---------------------------------------------------------------------------
# OpenAI / Perplexity (gedeelde openai-module, gefaked)
# ---------------------------------------------------------------------------


def _install_fake_openai_module(
    monkeypatch, *, content="Antwoord.", prompt_tokens=80, completion_tokens=40, raise_exc=None
):
    fake_module = types.ModuleType("openai")

    class _Choice:
        def __init__(self):
            self.message = types.SimpleNamespace(content=content)

    class _Usage:
        def __init__(self):
            self.prompt_tokens = prompt_tokens
            self.completion_tokens = completion_tokens

    class _Response:
        def __init__(self):
            self.choices = [_Choice()]
            self.usage = _Usage()

    class _Completions:
        def create(self, **kwargs):
            if raise_exc:
                raise raise_exc
            return _Response()

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = _Chat()
            self.init_kwargs = kwargs

    fake_module.OpenAI = _FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    return fake_module


def test_call_openai_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    _install_fake_openai_module(monkeypatch, content="ChatGPT-antwoord.")

    result = call_openai("Welk merk is het beste?")

    assert result.succeeded is True
    assert result.text == "ChatGPT-antwoord."
    assert result.cost_usd is not None


def test_call_openai_skips_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _install_fake_openai_module(monkeypatch)

    result = call_openai("Welk merk is het beste?")

    assert result.succeeded is False
    assert "OPENAI_API_KEY" in result.error


def test_call_openai_degrades_when_package_missing(monkeypatch):
    # None in sys.modules laat `import openai` een ImportError gooien, alsof
    # het pakket echt niet geïnstalleerd is.
    monkeypatch.setitem(sys.modules, "openai", None)

    result = call_openai("Welk merk is het beste?")

    assert result.succeeded is False
    assert "niet geïnstalleerd" in result.error


def test_call_openai_api_failure_degrades_gracefully(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    _install_fake_openai_module(monkeypatch, raise_exc=RuntimeError("rate limited"))

    result = call_openai("Welk merk is het beste?")

    assert result.succeeded is False
    assert "OpenAI-call mislukt" in result.error


def test_call_perplexity_success(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    fake_module = _install_fake_openai_module(monkeypatch, content="Perplexity-antwoord.")

    result = call_perplexity("Welk merk is het beste?")

    assert result.succeeded is True
    assert result.text == "Perplexity-antwoord."


def test_call_perplexity_skips_without_api_key(monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    _install_fake_openai_module(monkeypatch)

    result = call_perplexity("Welk merk is het beste?")

    assert result.succeeded is False
    assert "PERPLEXITY_API_KEY" in result.error


# ---------------------------------------------------------------------------
# Gemini (google.genai, gefaked)
# ---------------------------------------------------------------------------


def _install_fake_genai_module(
    monkeypatch, *, text="Gemini-antwoord.", prompt_tokens=60, candidates_tokens=30, raise_exc=None
):
    google_pkg = types.ModuleType("google")
    genai_module = types.ModuleType("google.genai")

    class _UsageMetadata:
        def __init__(self):
            self.prompt_token_count = prompt_tokens
            self.candidates_token_count = candidates_tokens

    class _Response:
        def __init__(self):
            self.text = text
            self.usage_metadata = _UsageMetadata()

    class _Models:
        def generate_content(self, **kwargs):
            if raise_exc:
                raise raise_exc
            return _Response()

    class _Client:
        def __init__(self, **kwargs):
            self.models = _Models()

    genai_module.Client = _Client
    google_pkg.genai = genai_module
    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.genai", genai_module)
    return genai_module


def test_call_gemini_success(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _install_fake_genai_module(monkeypatch, text="Gemini zegt iets over het merk.")

    result = call_gemini("Welk merk is het beste?")

    assert result.succeeded is True
    assert result.text == "Gemini zegt iets over het merk."
    assert result.cost_usd is not None


def test_call_gemini_skips_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    _install_fake_genai_module(monkeypatch)

    result = call_gemini("Welk merk is het beste?")

    assert result.succeeded is False
    assert "API_KEY" in result.error


def test_call_gemini_degrades_when_package_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "google.genai", None)
    monkeypatch.delitem(sys.modules, "google", raising=False)

    result = call_gemini("Welk merk is het beste?")

    assert result.succeeded is False
    assert "niet geïnstalleerd" in result.error


# ---------------------------------------------------------------------------
# Registry / kosten
# ---------------------------------------------------------------------------


def test_estimate_cost_uses_pricing_table():
    cost = _estimate_cost("claude-haiku-4-5", 1_000_000, 1_000_000)
    assert cost == 6.0  # 1.00 + 5.00 per 1M tokens


def test_estimate_cost_falls_back_for_unknown_model():
    assert _estimate_cost("onbekend-model-xyz", 1000, 1000) > 0


def test_estimate_cost_falls_back_without_usage():
    from app.citation.providers import FALLBACK_COST_PER_CALL_USD

    assert _estimate_cost("claude-haiku-4-5", None, None) == FALLBACK_COST_PER_CALL_USD


def test_enabled_providers_defaults_to_claude_only(monkeypatch):
    monkeypatch.delenv("GEO_DASHBOARD_CITATION_PROVIDERS", raising=False)
    assert enabled_providers() == ["claude"]


def test_enabled_providers_respects_env_var(monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_CITATION_PROVIDERS", "claude, chatgpt , onbekend")
    assert enabled_providers() == ["claude", "chatgpt"]


def test_providers_registry_has_all_four():
    assert set(PROVIDERS) == {"claude", "chatgpt", "perplexity", "gemini"}
