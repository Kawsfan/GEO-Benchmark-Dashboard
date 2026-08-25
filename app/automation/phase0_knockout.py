"""
Fase 0 knock-out check, geautomatiseerd.

1. robots.txt ophalen en controleren op Disallow-regels voor de bekende
   AI-crawlers (GPTBot, PerplexityBot, ClaudeBot, Google-Extended).
2. Een SSR-heuristiek: hoeveel leestekst zit er in de raw HTML-response
   (zonder JS-executie)? Een pagina die vrijwel leeg is zonder JS is
   waarschijnlijk clientside-rendered en dus een risico voor AI-crawlers die
   geen JS uitvoeren.

Beperking (zie ARCHITECTURE.md): dit is een tekstlengte-proxy, geen echte
diff met een headless-browser-render. De functie is bewust als vervangbare
strategie opgezet zodat een Playwright-render er later naast/i.p.v. kan.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.automation.http_client import build_client, normalize_domain

AI_CRAWLER_USER_AGENTS = ["GPTBot", "PerplexityBot", "ClaudeBot", "Google-Extended"]

# Onder deze verhouding (zichtbare tekst raw-HTML / totale HTML-bytes) wordt
# de pagina als vermoedelijk clientside-rendered beschouwd.
SSR_TEXT_RATIO_THRESHOLD = 0.02
SSR_MIN_TEXT_CHARS = 200


@dataclass
class KnockoutResult:
    crawler_ok: bool
    ssr_ok: bool
    robots_txt_found: bool
    disallowed_agents: list[str]
    raw_text_chars: int
    detail: str


def _robots_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def _parse_robots_groups(text: str) -> list[tuple[list[str], bool]]:
    """Parseer robots.txt naar (agents, disallow_all)-groepen, in volgorde.

    Een nieuwe group start bij elke aaneengesloten reeks User-agent-regels;
    `disallow_all` is True zodra die groep een `Disallow: /` bevat.
    """
    groups: list[tuple[list[str], bool]] = []
    current_agents: list[str] = []
    current_disallow_all = False
    group_open = False

    def flush():
        if group_open and current_agents:
            groups.append((list(current_agents), current_disallow_all))

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if not group_open:
                current_agents = [value]
                group_open = True
                current_disallow_all = False
            else:
                # Opeenvolgende User-agent-regels horen bij dezelfde groep
                # (robots.txt-conventie), zolang er nog geen Disallow tussen zat.
                current_agents.append(value)
        elif key == "disallow":
            if value == "/":
                current_disallow_all = True
            flush()
            group_open = False
            current_agents = []
        elif key == "allow":
            flush()
            group_open = False
            current_agents = []

    flush()
    return groups


def check_robots_txt(client: httpx.Client, base_url: str) -> tuple[bool, bool, list[str]]:
    """Return (found, crawler_ok, disallowed_agents).

    Volgt de robots.txt-conventie dat een groep voor een specifieke
    user-agent voorrang heeft boven een `User-agent: *`-groep voor diezelfde
    bot — een expliciete "Allow" voor GPTBot na een blokkerende wildcard
    telt dus terecht als toegestaan.
    """
    try:
        resp = client.get(_robots_url(base_url))
    except httpx.HTTPError:
        # robots.txt niet bereikbaar -> geen aantoonbare blokkade, telt als OK
        return False, True, []

    if resp.status_code != 200:
        return False, True, []

    groups = _parse_robots_groups(resp.text)

    disallowed: list[str] = []
    for agent in AI_CRAWLER_USER_AGENTS:
        specific = [g for g in groups if agent in g[0]]
        if specific:
            # Laatste specifieke groep voor deze bot wint.
            if specific[-1][1]:
                disallowed.append(agent)
            continue
        wildcard = [g for g in groups if "*" in g[0]]
        if wildcard and wildcard[-1][1]:
            disallowed.append(agent)

    crawler_ok = len(disallowed) == 0
    return True, crawler_ok, disallowed


def check_ssr(client: httpx.Client, base_url: str) -> tuple[bool, int, str]:
    try:
        resp = client.get(base_url)
    except httpx.HTTPError as exc:
        return False, 0, f"Kon pagina niet ophalen: {exc}"

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text_chars = len(text)
    html_bytes = max(len(resp.content), 1)
    ratio = text_chars / html_bytes

    if text_chars < SSR_MIN_TEXT_CHARS and ratio < SSR_TEXT_RATIO_THRESHOLD:
        return False, text_chars, (
            f"Slechts {text_chars} tekens leestekst in raw HTML "
            f"(ratio {ratio:.4f}) — pagina lijkt sterk clientside-gerenderd."
        )
    return True, text_chars, f"{text_chars} tekens leestekst in raw HTML (ratio {ratio:.4f})."


def run_knockout_check(domain: str) -> KnockoutResult:
    base_url = normalize_domain(domain)
    with build_client() as client:
        robots_found, crawler_ok, disallowed = check_robots_txt(client, base_url)
        ssr_ok, text_chars, ssr_detail = check_ssr(client, base_url)

    detail_parts = [ssr_detail]
    if disallowed:
        detail_parts.append(f"robots.txt blokkeert: {', '.join(disallowed)}")
    elif robots_found:
        detail_parts.append("robots.txt geeft geen blokkade voor AI-crawlers.")
    else:
        detail_parts.append("robots.txt niet gevonden of niet bereikbaar.")

    return KnockoutResult(
        crawler_ok=crawler_ok,
        ssr_ok=ssr_ok,
        robots_txt_found=robots_found,
        disallowed_agents=disallowed,
        raw_text_chars=text_chars,
        detail=" ".join(detail_parts),
    )
