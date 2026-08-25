"""
C8 — Multimodaal & Social Proof, geautomatiseerd.

Heuristiek: scant de al opgehaalde homepage-HTML (van de Fase 1-fetch, geen
extra request nodig) op links naar bekende video-/social-/reviewplatformen.
Meet uitsluitend de *aanwezigheid* van een link — niet de daadwerkelijke
activiteit/frequentie op dat kanaal, wat per-platform OAuth/API-toegang zou
vereisen (zie ARCHITECTURE.md, buiten scope voor deze automatisering).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup

PLATFORM_PATTERNS: dict[str, tuple[str, ...]] = {
    "YouTube": ("youtube.com/", "youtu.be/"),
    "Instagram": ("instagram.com/",),
    "TikTok": ("tiktok.com/",),
    "Facebook": ("facebook.com/",),
    "LinkedIn": ("linkedin.com/company/", "linkedin.com/in/"),
    "X/Twitter": ("twitter.com/", "x.com/"),
    "Trustpilot": ("trustpilot.com/review",),
}

POINTS_PER_PLATFORM = 1.5
# Video-content weegt zwaarder in het framework ("publiceer relevante
# video-/audiocontent op YouTube") — vandaar de bonus.
YOUTUBE_BONUS = 2.0


@dataclass
class MultimodalResult:
    score: float
    platforms_found: list[str] = field(default_factory=list)
    detail: str = ""


def analyze_multimodal_presence(html: str) -> MultimodalResult:
    soup = BeautifulSoup(html, "html.parser")
    hrefs_lower = " ".join(a.get("href", "") for a in soup.find_all("a", href=True)).lower()

    found = [platform for platform, patterns in PLATFORM_PATTERNS.items() if any(p in hrefs_lower for p in patterns)]

    score = POINTS_PER_PLATFORM * len(found)
    if "YouTube" in found:
        score += YOUTUBE_BONUS
    score = round(min(10.0, score), 1)

    if not found:
        detail = "Geen links naar bekende video-/social-/reviewplatformen gevonden op de homepage."
    else:
        detail = (
            f"Links gevonden naar: {', '.join(found)}. Let op: dit meet alleen aanwezigheid van "
            "een link, niet de daadwerkelijke activiteit/frequentie op dat kanaal."
        )

    return MultimodalResult(score=score, platforms_found=found, detail=detail)
