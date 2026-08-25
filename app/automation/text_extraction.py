"""Gedeelde tekst-extractie uit ruwe HTML — gebruikt door de Fase 0 SSR-check
en de Fase 2 LLM-rubric (die de zichtbare pagina-tekst nodig heeft)."""

from __future__ import annotations

from bs4 import BeautifulSoup

# Tags die geen leesbare hoofdinhoud bevatten en de LLM-beoordeling alleen
# maar zouden vervuilen (navigatie, footer-links, cookiebanners e.d.).
NOISE_TAGS = ["script", "style", "noscript", "nav", "footer", "header", "svg"]


def extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)
