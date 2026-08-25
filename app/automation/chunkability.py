"""
C2 — Chunkability & Vector-geschiktheid, geautomatiseerd.

Heuristiek op basis van:
- gemiddelde paragraaflengte (in woorden) — ideaal zelfstandig leesbare
  chunks van ~150-300 woorden;
- aanwezigheid van H2/H3-koppen (structuur om op te knippen);
- aanwezigheid van lijsten (ul/ol) en tabellen.
"""

from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup

IDEAL_MIN_WORDS = 40
IDEAL_MAX_WORDS = 300


@dataclass
class ChunkabilityResult:
    score: float
    paragraph_count: int
    avg_paragraph_words: float
    heading_count: int
    list_count: int
    table_count: int
    detail: str


def _paragraph_word_lengths(soup: BeautifulSoup) -> list[int]:
    lengths = []
    for p in soup.find_all("p"):
        text = p.get_text(separator=" ", strip=True)
        words = len(text.split())
        if words >= 5:  # negeer lege/decoratieve <p>-tags
            lengths.append(words)
    return lengths


def analyze_chunkability(html: str) -> ChunkabilityResult:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    paragraph_lengths = _paragraph_word_lengths(soup)
    paragraph_count = len(paragraph_lengths)
    avg_words = sum(paragraph_lengths) / paragraph_count if paragraph_count else 0.0

    heading_count = len(soup.find_all(["h2", "h3"]))
    list_count = len(soup.find_all(["ul", "ol"]))
    table_count = len(soup.find_all("table"))

    # Paragraaflengte-score (0-5): hoe dichter bij het ideale bereik, hoe hoger.
    if paragraph_count == 0:
        length_score = 0.0
    elif IDEAL_MIN_WORDS <= avg_words <= IDEAL_MAX_WORDS:
        length_score = 5.0
    elif avg_words < IDEAL_MIN_WORDS:
        length_score = max(0.0, 5.0 * (avg_words / IDEAL_MIN_WORDS))
    else:
        overshoot = avg_words - IDEAL_MAX_WORDS
        length_score = max(0.0, 5.0 - (overshoot / IDEAL_MAX_WORDS) * 5.0)

    # Structuurscore (0-3): H2/H3 aanwezig en in redelijke hoeveelheid.
    structure_score = min(3.0, heading_count * 0.75)

    # Lijsten/tabellen-score (0-2)
    list_table_score = min(2.0, (1.0 if list_count else 0.0) + (1.0 if table_count else 0.0))

    score = round(min(10.0, length_score + structure_score + list_table_score), 1)

    detail = (
        f"{paragraph_count} alinea's (gem. {avg_words:.0f} woorden), "
        f"{heading_count} H2/H3-koppen, {list_count} lijsten, {table_count} tabellen."
    )

    return ChunkabilityResult(
        score=score,
        paragraph_count=paragraph_count,
        avg_paragraph_words=round(avg_words, 1),
        heading_count=heading_count,
        list_count=list_count,
        table_count=table_count,
        detail=detail,
    )
