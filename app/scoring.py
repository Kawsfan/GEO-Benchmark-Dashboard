"""
GEO Benchmark Model v2.0 — scoring-laag.

1-op-1 overgenomen uit het bestaande `geo_report_generator.py`: CRITERIA-dict
(wegingen, pijlers, quick-win/advies), classificatietabel, GAP-analyse en
top-3-prioriteiten-logica. Werkt hier op een lijst van (code, raw_score)
paren in plaats van een los JSON-dict, zodat dezelfde logica zowel de losse
CLI-generator als de dashboard-database kan voeden.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# CRITERIA-DEFINITIE (weging, pijler, quick_win, aanbeveling per laag-scorend criterium)
# ---------------------------------------------------------------------------

CRITERIA: dict[str, dict] = {
    "c1_structured_data": {
        "label": "Gestructureerde data & Feeds",
        "pillar": "Technische basis & Structuur",
        "weight": 8,
        "quick_win": True,
        "advice": "Vul Schema.org markup aan (Organization, Product, FAQ, Article) en zorg dat productfeeds actueel en volledig zijn.",
        "automatable_phase": 1,
    },
    "c2_chunkability": {
        "label": "Chunkability & Vector-geschiktheid",
        "pillar": "Technische basis & Structuur",
        "weight": 7,
        "quick_win": True,
        "advice": "Herstructureer content in zelfstandig leesbare alinea's van 150-300 woorden met duidelijke H2/H3-koppen, tabellen en lijsten.",
        "automatable_phase": 1,
    },
    "c3_answerability": {
        "label": "Answerability & Volledigheid",
        "pillar": "Content & Informatiedichtheid",
        "weight": 12,
        "quick_win": False,
        "advice": "Herschrijf kernpagina's zodat de daadwerkelijke gebruikersvraag direct en volledig wordt beantwoord met concrete cijfers en voorwaarden.",
        "automatable_phase": 2,
    },
    "c4_bluf": {
        "label": "Antwoord vooraan / BLUF",
        "pillar": "Content & Informatiedichtheid",
        "weight": 11,
        "quick_win": True,
        "advice": "Verplaats de kernconclusie naar de eerste 60 woorden van elke pagina; verwijder sfeeropbouw/vulling vooraan.",
        "automatable_phase": 2,
    },
    "c5_fact_density": {
        "label": "Feitelijke dichtheid & Bronnen",
        "pillar": "Content & Informatiedichtheid",
        "weight": 12,
        "quick_win": False,
        "advice": "Verhoog het aantal verifieerbare feiten en bronvermeldingen per 100 woorden; schrap holle marketingtaal.",
        "automatable_phase": 2,
    },
    "c6_entity_clarity": {
        "label": "Entiteits-helderheid / Knowledge Graph",
        "pillar": "Off-page Autoriteit & Entiteit",
        "weight": 10,
        "quick_win": False,
        "advice": "Claim/optimaliseer Wikidata- en KvK-vermeldingen en zorg voor consistente NAP/attributen over alle brancheregisters.",
        "automatable_phase": 3,
    },
    "c7_external_mentions": {
        "label": "Externe co-occurrence & Media",
        "pillar": "Off-page Autoriteit & Entiteit",
        "weight": 8,
        "quick_win": False,
        "advice": "Investeer in vakmedia-vermeldingen en aanwezigheid op platforms als Tweakers/Reddit waar RAG-systemen uit putten.",
        "automatable_phase": 3,
    },
    "c8_multimodal": {
        "label": "Multimodaal & Social Proof",
        "pillar": "Off-page Autoriteit & Entiteit",
        "weight": 7,
        "quick_win": True,
        "advice": "Verzamel gecertificeerde reviews (Trustpilot) en publiceer relevante video-/audiocontent op YouTube.",
        "automatable_phase": 3,
    },
    "c9_share_of_model": {
        "label": "Share of Model / Citation Rate",
        "pillar": "Output & Werkelijke Impact",
        "weight": 15,
        "quick_win": False,
        "advice": "Monitor en optimaliseer citaties in AI-antwoorden op categorie- en vergelijkingsvragen; structureer content specifiek rond die vraagpatronen.",
        "automatable_phase": 4,
    },
    "c10_sentiment_freshness": {
        "label": "Contextueel Sentiment & Actualiteit",
        "pillar": "Output & Werkelijke Impact",
        "weight": 10,
        "quick_win": True,
        "advice": "Voeg machine-leesbare datums toe (dateModified) en monitor/verbeter het sentiment rond merkvermeldingen in AI-antwoorden.",
        # Het freshness-deel is fase-1-automatiseerbaar, het sentiment-deel niet.
        # Zie ARCHITECTURE.md ("Afwijking van het bestaande script").
        "automatable_phase": 1,
    },
}

PILLAR_ORDER = [
    "Technische basis & Structuur",
    "Content & Informatiedichtheid",
    "Off-page Autoriteit & Entiteit",
    "Output & Werkelijke Impact",
]

PILLAR_GAP_KEY = {
    "Technische basis & Structuur": "Technical & Structural GAP",
    "Content & Informatiedichtheid": "Content Density GAP",
    "Off-page Autoriteit & Entiteit": "Authority & Entity GAP",
    "Output & Werkelijke Impact": "Model Visibility GAP",
}

CLASSIFICATION_TABLE = [
    (85, 100, "AI Category Leader", "Onbetwiste koploper. Optimaal voor RAG en domineert de werkelijke AI-antwoorden."),
    (70, 84, "Sterke AI-positie", "Goede hygiëne en vindbaarheid; kan op specifieke vergelijkingsvragen nog winnen."),
    (55, 69, "Op de goede weg", "Basisinfrastructuur staat, maar content bevat te veel marketingvulling voor LLM's."),
    (40, 54, "Kwetsbaar", "Nauwelijks geciteerd door AI-zoekmachines. Hoog risico bij zoekgedragverschuiving."),
    (0, 39, "Onzichtbaar", "Onbekend voor AI, of gefaald op de Knock-out fase."),
]

# Bron-typen voor per-criterium scores — bepaalt de UI-badge.
SOURCE_AUTOMATED = "automated"
SOURCE_LLM_ESTIMATE = "llm_estimate"
SOURCE_MANUAL = "manual"

SOURCE_LABELS = {
    SOURCE_AUTOMATED: "Automatisch gemeten",
    SOURCE_LLM_ESTIMATE: "LLM-schatting",
    SOURCE_MANUAL: "Handmatig ingevoerd",
}


def classify(score: float) -> tuple[str, str]:
    # CLASSIFICATION_TABLE staat aflopend gesorteerd op ondergrens; de eerste
    # band waar score >= lo geldt, wint. Let op: de originele CLI-tabel
    # gebruikte `lo <= score <= hi` met gehele grenzen (bv. 70-84, 85-100),
    # waardoor een fractionele score als 84.9 tussen wal en schip viel en
    # ten onrechte als "Onzichtbaar" werd geclassificeerd. Dit dashboard
    # gebruikt daarom alleen de ondergrens.
    for lo, _hi, label, desc in CLASSIFICATION_TABLE:
        if score >= lo:
            return label, desc
    return "Onzichtbaar", CLASSIFICATION_TABLE[-1][3]


@dataclass
class CriterionResult:
    code: str
    raw: float
    source: str
    rationale: str | None = None

    @property
    def label(self) -> str:
        return CRITERIA[self.code]["label"]

    @property
    def pillar(self) -> str:
        return CRITERIA[self.code]["pillar"]

    @property
    def weight(self) -> float:
        return CRITERIA[self.code]["weight"]

    @property
    def contribution(self) -> float:
        return round(self.weight * (self.raw / 10), 2)


@dataclass
class ScoreReport:
    knockout_pass: bool
    crawler_ok: bool
    ssr_ok: bool
    total_score: float
    classification: str
    classification_desc: str
    results: list[CriterionResult]
    pillars: dict = field(default_factory=dict)
    gaps: dict = field(default_factory=dict)
    priorities: list[CriterionResult] = field(default_factory=list)


def compute_score(
    criterion_scores: dict[str, float],
    crawler_ok: bool,
    ssr_ok: bool,
    sources: dict[str, str] | None = None,
    rationales: dict[str, str] | None = None,
) -> ScoreReport:
    """Bereken de volledige GEO-score, GAP-analyse en top-3-prioriteiten.

    `criterion_scores`: {code: raw 0-10}. Ontbrekende codes tellen als 0.
    `sources`: {code: SOURCE_*} — default SOURCE_MANUAL als niet opgegeven.
    """
    sources = sources or {}
    rationales = rationales or {}
    knockout_pass = bool(crawler_ok) and bool(ssr_ok)

    results: list[CriterionResult] = []
    total_score = 0.0
    for code in CRITERIA:
        raw = criterion_scores.get(code)
        raw = 0.0 if raw is None else max(0.0, min(10.0, float(raw)))
        result = CriterionResult(
            code=code,
            raw=raw,
            source=sources.get(code, SOURCE_MANUAL),
            rationale=rationales.get(code),
        )
        results.append(result)
        total_score += result.contribution

    if not knockout_pass:
        total_score = 0.0

    total_score = round(total_score, 1)
    if knockout_pass:
        classification, classification_desc = classify(total_score)
    else:
        classification, classification_desc = (
            "Onzichtbaar",
            "Onzichtbaar voor AI due to technical lockout.",
        )

    # GAP-analyse: criteria met score <= 6 op een schaal van 0-10 gelden als aandachtspunt
    gaps: dict[str, list[CriterionResult]] = {key: [] for key in PILLAR_GAP_KEY.values()}
    for r in results:
        if r.raw <= 6:
            gaps[PILLAR_GAP_KEY[r.pillar]].append(r)

    # Top 3 prioriteiten: laagst scorende criteria eerst, quick wins krijgen voorrang
    sortable = sorted(results, key=lambda r: (r.raw, -r.weight))
    quick_wins = [r for r in sortable if CRITERIA[r.code]["quick_win"] and r.raw < 8][:3]
    strategic = [r for r in sortable if not CRITERIA[r.code]["quick_win"] and r.raw < 8][:3]
    priorities = (quick_wins[:2] + strategic[:2])[:3]
    if not priorities:
        priorities = sortable[:3]

    pillars = {}
    for p in PILLAR_ORDER:
        pillar_results = [r for r in results if r.pillar == p]
        pillars[p] = {
            "results": pillar_results,
            "weight": sum(r.weight for r in pillar_results),
            "contribution": round(sum(r.contribution for r in pillar_results), 1),
        }

    return ScoreReport(
        knockout_pass=knockout_pass,
        crawler_ok=crawler_ok,
        ssr_ok=ssr_ok,
        total_score=total_score,
        classification=classification,
        classification_desc=classification_desc,
        results=results,
        pillars=pillars,
        gaps=gaps,
        priorities=priorities,
    )
