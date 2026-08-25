"""
Fase 4 — provider-integraties voor Share of Model (C9).

Stuurt één prompt naar één AI-provider en geeft het antwoord + een
kostenschatting terug. Elke provider degradeert onafhankelijk en gracieus:
geen key, een importfout (pakket niet geïnstalleerd) of een API-fout levert
een `ProviderResponse` met `error` gezet, nooit een exception die de hele
citatie-run laat crashen.

BELANGRIJK — vertrouwensniveau per provider:
- **Claude**: volledig op basis van de officiële Anthropic Python-SDK
  (`anthropic`), zoals ook gebruikt in `app/automation/llm_rubric.py` en
  `app/automation/external_mentions.py`.
- **OpenAI / Perplexity / Gemini**: de aanroeppaden hieronder
  (`openai.OpenAI().chat.completions.create(...)`,
  `response.usage.prompt_tokens`/`completion_tokens`,
  `google.genai.Client().models.generate_content(...)`,
  `response.text`/`response.usage_metadata.prompt_token_count`/
  `candidates_token_count`) zijn geverifieerd tegen de daadwerkelijk
  geïnstalleerde `openai`- en `google-genai`-pakketten (attributen bestaan,
  juiste vorm) — geen educated guess. Wat NIET geverifieerd is: de exacte
  modelnamen (`gpt-4o-mini`, `sonar`, `gemini-2.0-flash` — providers
  hernoemen/deprecaten modellen regelmatig) en de actuele pricing in
  `PRICING` hieronder. Controleer die twee tegen de actuele documentatie van
  elke provider voor productiegebruik; overschrijf modelnamen desgewenst via
  `GEO_DASHBOARD_CITATION_*_MODEL`. Faalt een integratie alsnog door een
  API-wijziging, dan degradeert dat automatisch gracieus (die provider wordt
  overgeslagen) — het breekt de rest niet.

Kostenschattingen zijn ruwe indicaties op basis van gepubliceerde
$/1M-token-tarieven (zie PRICING hieronder) — geen exacte facturatie.
Werk de tarieven bij als een provider zijn prijzen wijzigt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

# Ruwe $/1M-token-tarieven (input, output) — schattingen, geen gegarandeerde
# actuele prijzen. Claude-tarieven zijn overgenomen uit de Anthropic-pricing
# t.b.v. dit project (peildatum 2026-06-24); OpenAI/Perplexity/Gemini zijn
# publiek bekende indicatieve tarieven — controleer voor productiegebruik.
PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "sonar": (1.00, 1.00),
    "gemini-2.0-flash": (0.10, 0.40),
}
# Als een model niet in PRICING staat, of usage niet beschikbaar is: een
# vlakke schatting per call, zodat kostenbewaking nooit stilzwijgend "gratis"
# aanneemt.
FALLBACK_COST_PER_CALL_USD = 0.01


def _estimate_cost(model: str, input_tokens: int | None, output_tokens: int | None) -> float:
    if input_tokens is None or output_tokens is None:
        return FALLBACK_COST_PER_CALL_USD
    price_in, price_out = PRICING.get(model, (None, None))
    if price_in is None:
        return FALLBACK_COST_PER_CALL_USD
    return round((input_tokens / 1_000_000) * price_in + (output_tokens / 1_000_000) * price_out, 6)


@dataclass
class ProviderResponse:
    text: str | None
    model: str | None = None
    cost_usd: float | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.text is not None


def call_claude(prompt: str) -> ProviderResponse:
    model = os.environ.get("GEO_DASHBOARD_CITATION_CLAUDE_MODEL", "claude-haiku-4-5")
    try:
        import anthropic
    except ImportError:
        return ProviderResponse(text=None, error="Het 'anthropic'-pakket is niet geïnstalleerd.")

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # noqa: BLE001 - nooit de citatie-run laten crashen op één provider
        return ProviderResponse(text=None, error=f"Claude-call mislukt: {exc}")

    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    usage = getattr(response, "usage", None)
    cost = _estimate_cost(model, getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None))
    return ProviderResponse(text=text, model=model, cost_usd=cost)


def call_openai(prompt: str) -> ProviderResponse:
    model = os.environ.get("GEO_DASHBOARD_CITATION_OPENAI_MODEL", "gpt-4o-mini")
    try:
        import openai
    except ImportError:
        return ProviderResponse(text=None, error="Het 'openai'-pakket is niet geïnstalleerd.")

    if not os.environ.get("OPENAI_API_KEY"):
        return ProviderResponse(text=None, error="Geen OPENAI_API_KEY geconfigureerd.")

    try:
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # noqa: BLE001
        return ProviderResponse(text=None, error=f"OpenAI-call mislukt: {exc}")

    text = response.choices[0].message.content if response.choices else None
    usage = getattr(response, "usage", None)
    cost = _estimate_cost(
        model, getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)
    )
    return ProviderResponse(text=text, model=model, cost_usd=cost)


def call_perplexity(prompt: str) -> ProviderResponse:
    """Perplexity biedt een OpenAI-compatibele chat-completions-endpoint aan;
    dit hergebruikt daarom het `openai`-pakket met een andere `base_url`."""
    model = os.environ.get("GEO_DASHBOARD_CITATION_PERPLEXITY_MODEL", "sonar")
    try:
        import openai
    except ImportError:
        return ProviderResponse(text=None, error="Het 'openai'-pakket is niet geïnstalleerd (nodig voor Perplexity).")

    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        return ProviderResponse(text=None, error="Geen PERPLEXITY_API_KEY geconfigureerd.")

    try:
        client = openai.OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
        response = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # noqa: BLE001
        return ProviderResponse(text=None, error=f"Perplexity-call mislukt: {exc}")

    text = response.choices[0].message.content if response.choices else None
    usage = getattr(response, "usage", None)
    cost = _estimate_cost(
        model, getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)
    )
    return ProviderResponse(text=text, model=model, cost_usd=cost)


def call_gemini(prompt: str) -> ProviderResponse:
    model = os.environ.get("GEO_DASHBOARD_CITATION_GEMINI_MODEL", "gemini-2.0-flash")
    try:
        from google import genai
    except ImportError:
        return ProviderResponse(text=None, error="Het 'google-genai'-pakket is niet geïnstalleerd.")

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return ProviderResponse(text=None, error="Geen GEMINI_API_KEY/GOOGLE_API_KEY geconfigureerd.")

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model, contents=prompt)
    except Exception as exc:  # noqa: BLE001
        return ProviderResponse(text=None, error=f"Gemini-call mislukt: {exc}")

    text = getattr(response, "text", None)
    usage = getattr(response, "usage_metadata", None)
    input_tokens = getattr(usage, "prompt_token_count", None) if usage else None
    output_tokens = getattr(usage, "candidates_token_count", None) if usage else None
    cost = _estimate_cost(model, input_tokens, output_tokens)
    return ProviderResponse(text=text, model=model, cost_usd=cost)


# Registry: provider-code (zoals opgeslagen in CitationRun.provider) -> call-functie.
PROVIDERS: dict[str, Callable[[str], ProviderResponse]] = {
    "claude": call_claude,
    "chatgpt": call_openai,
    "perplexity": call_perplexity,
    "gemini": call_gemini,
}


def enabled_providers() -> list[str]:
    """Welke providers deze installatie probeert, op basis van
    GEO_DASHBOARD_CITATION_PROVIDERS (komma-lijst; default: alleen Claude,
    aangezien dat de enige provider is met een geverifieerde integratie)."""
    raw = os.environ.get("GEO_DASHBOARD_CITATION_PROVIDERS", "claude")
    codes = [c.strip() for c in raw.split(",") if c.strip()]
    return [c for c in codes if c in PROVIDERS]
