#!/usr/bin/env python3
"""
GEO Benchmark Rapport Generator (v2.0) — oorspronkelijke standalone CLI.
========================================================================
Ongewijzigd bewaard voor wie los van het dashboard nog een eenmalig
HTML-rapport uit een handmatig JSON-bestand wil genereren. Het dashboard
zelf gebruikt dezelfde scoring-/classificatielogica via `app/scoring.py`
en `app/report_html.py` (zie ARCHITECTURE.md).

Gebruik:
    python scripts/legacy_geo_report_generator.py input.json output.html
    python scripts/legacy_geo_report_generator.py            # draait met ingebouwd voorbeeld
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# CRITERIA-DEFINITIE (weging, pijler, quick_win, aanbeveling per laag-scorend criterium)
# ---------------------------------------------------------------------------

CRITERIA = {
    "c1_structured_data": {
        "label": "Gestructureerde data & Feeds",
        "pillar": "Technische basis & Structuur",
        "weight": 8,
        "quick_win": True,
        "advice": "Vul Schema.org markup aan (Organization, Product, FAQ, Article) en zorg dat productfeeds actueel en volledig zijn.",
    },
    "c2_chunkability": {
        "label": "Chunkability & Vector-geschiktheid",
        "pillar": "Technische basis & Structuur",
        "weight": 7,
        "quick_win": True,
        "advice": "Herstructureer content in zelfstandig leesbare alinea's van 150-300 woorden met duidelijke H2/H3-koppen, tabellen en lijsten.",
    },
    "c3_answerability": {
        "label": "Answerability & Volledigheid",
        "pillar": "Content & Informatiedichtheid",
        "weight": 12,
        "quick_win": False,
        "advice": "Herschrijf kernpagina's zodat de daadwerkelijke gebruikersvraag direct en volledig wordt beantwoord met concrete cijfers en voorwaarden.",
    },
    "c4_bluf": {
        "label": "Antwoord vooraan / BLUF",
        "pillar": "Content & Informatiedichtheid",
        "weight": 11,
        "quick_win": True,
        "advice": "Verplaats de kernconclusie naar de eerste 60 woorden van elke pagina; verwijder sfeeropbouw/vulling vooraan.",
    },
    "c5_fact_density": {
        "label": "Feitelijke dichtheid & Bronnen",
        "pillar": "Content & Informatiedichtheid",
        "weight": 12,
        "quick_win": False,
        "advice": "Verhoog het aantal verifieerbare feiten en bronvermeldingen per 100 woorden; schrap holle marketingtaal.",
    },
    "c6_entity_clarity": {
        "label": "Entiteits-helderheid / Knowledge Graph",
        "pillar": "Off-page Autoriteit & Entiteit",
        "weight": 10,
        "quick_win": False,
        "advice": "Claim/optimaliseer Wikidata- en KvK-vermeldingen en zorg voor consistente NAP/attributen over alle brancheregisters.",
    },
    "c7_external_mentions": {
        "label": "Externe co-occurrence & Media",
        "pillar": "Off-page Autoriteit & Entiteit",
        "weight": 8,
        "quick_win": False,
        "advice": "Investeer in vakmedia-vermeldingen en aanwezigheid op platforms als Tweakers/Reddit waar RAG-systemen uit putten.",
    },
    "c8_multimodal": {
        "label": "Multimodaal & Social Proof",
        "pillar": "Off-page Autoriteit & Entiteit",
        "weight": 7,
        "quick_win": True,
        "advice": "Verzamel gecertificeerde reviews (Trustpilot) en publiceer relevante video-/audiocontent op YouTube.",
    },
    "c9_share_of_model": {
        "label": "Share of Model / Citation Rate",
        "pillar": "Output & Werkelijke Impact",
        "weight": 15,
        "quick_win": False,
        "advice": "Monitor en optimaliseer citaties in AI-antwoorden op categorie- en vergelijkingsvragen; structureer content specifiek rond die vraagpatronen.",
    },
    "c10_sentiment_freshness": {
        "label": "Contextueel Sentiment & Actualiteit",
        "pillar": "Output & Werkelijke Impact",
        "weight": 10,
        "quick_win": True,
        "advice": "Voeg machine-leesbare datums toe (dateModified) en monitor/verbeter het sentiment rond merkvermeldingen in AI-antwoorden.",
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


# ---------------------------------------------------------------------------
# SCORE-LOGICA
# ---------------------------------------------------------------------------

def classify(score: float) -> tuple[str, str]:
    for lo, hi, label, desc in CLASSIFICATION_TABLE:
        if lo <= score <= hi:
            return label, desc
    return "Onzichtbaar", CLASSIFICATION_TABLE[-1][3]


def compute_report_data(data: dict) -> dict:
    brand = data.get("brand_name", "Onbekend merk")
    domain = data.get("domain", "")
    phase0 = data.get("phase_0", {})
    crawler_ok = bool(phase0.get("ai_crawler_access", False))
    ssr_ok = bool(phase0.get("server_side_rendering", False))
    knockout_pass = crawler_ok and ssr_ok

    scores_in = data.get("scores", {})

    rows = []
    total_score = 0.0
    for code, meta in CRITERIA.items():
        raw = scores_in.get(code)
        raw = 0 if raw is None else max(0, min(10, raw))
        contribution = round(meta["weight"] * (raw / 10), 2)
        total_score += contribution
        rows.append({
            "code": code,
            "label": meta["label"],
            "pillar": meta["pillar"],
            "weight": meta["weight"],
            "raw": raw,
            "contribution": contribution,
        })

    if not knockout_pass:
        total_score = 0.0

    total_score = round(total_score, 1)
    classification, classification_desc = classify(total_score) if knockout_pass else (
        "Onzichtbaar", "Onzichtbaar voor AI due to technical lockout."
    )

    # GAP-analyse: criteria met score <= 6 op een schaal van 0-10 gelden als aandachtspunt
    gaps = {key: [] for key in PILLAR_GAP_KEY.values()}
    for row in rows:
        if row["raw"] <= 6:
            gap_key = PILLAR_GAP_KEY[row["pillar"]]
            gaps[gap_key].append(row)

    # Top 3 prioriteiten: laagst scorende criteria eerst, quick wins krijgen voorrang
    sortable = sorted(rows, key=lambda r: (r["raw"], -r["weight"]))
    quick_wins = [r for r in sortable if CRITERIA[r["code"]]["quick_win"] and r["raw"] < 8][:3]
    strategic = [r for r in sortable if not CRITERIA[r["code"]]["quick_win"] and r["raw"] < 8][:3]
    priorities = (quick_wins[:2] + strategic[:2])[:3]
    if not priorities:
        priorities = sortable[:3]

    pillars = {}
    for p in PILLAR_ORDER:
        pillar_rows = [r for r in rows if r["pillar"] == p]
        pillar_weight = sum(r["weight"] for r in pillar_rows)
        pillar_contribution = round(sum(r["contribution"] for r in pillar_rows), 1)
        pillars[p] = {
            "rows": pillar_rows,
            "weight": pillar_weight,
            "contribution": pillar_contribution,
        }

    return {
        "brand": brand,
        "domain": domain,
        "generated_at": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "knockout_pass": knockout_pass,
        "crawler_ok": crawler_ok,
        "ssr_ok": ssr_ok,
        "total_score": total_score,
        "classification": classification,
        "classification_desc": classification_desc,
        "rows": rows,
        "pillars": pillars,
        "gaps": gaps,
        "priorities": priorities,
    }


# ---------------------------------------------------------------------------
# HTML RENDERING
# ---------------------------------------------------------------------------

def score_color(raw: int) -> str:
    if raw >= 8:
        return "#1a9e5c"
    if raw >= 6:
        return "#d4a017"
    return "#c0392b"


def classification_color(label: str) -> str:
    return {
        "AI Category Leader": "#1a9e5c",
        "Sterke AI-positie": "#4caf7d",
        "Op de goede weg": "#d4a017",
        "Kwetsbaar": "#e07b39",
        "Onzichtbaar": "#c0392b",
    }.get(label, "#666")


def render_html(rd: dict) -> str:
    color = classification_color(rd["classification"])

    # Knock-out status block
    if rd["knockout_pass"]:
        knockout_html = f"""
        <div class="knockout-box pass">
          <span class="badge pass">PASS</span>
          <div>
            <strong>Knock-out check geslaagd</strong>
            <ul>
              <li>{"✅" if rd["crawler_ok"] else "❌"} AI-crawler-toegang (GPTBot, PerplexityBot, ClaudeBot, Google-Extended)</li>
              <li>{"✅" if rd["ssr_ok"] else "❌"} Server-side rendering van kerncontent</li>
            </ul>
          </div>
        </div>"""
    else:
        knockout_html = f"""
        <div class="knockout-box fail">
          <span class="badge fail">FAIL</span>
          <div>
            <strong>Knock-out check gefaald &mdash; Totale GEO Score = 0/100</strong>
            <ul>
              <li>{"✅" if rd["crawler_ok"] else "❌"} AI-crawler-toegang (GPTBot, PerplexityBot, ClaudeBot, Google-Extended)</li>
              <li>{"✅" if rd["ssr_ok"] else "❌"} Server-side rendering van kerncontent</li>
            </ul>
            <p>Status: <em>Onzichtbaar voor AI due to technical lockout</em></p>
          </div>
        </div>"""

    # Score breakdown table (per pijler)
    breakdown_rows = ""
    for pillar in PILLAR_ORDER:
        p = rd["pillars"][pillar]
        breakdown_rows += f"""
        <tr class="pillar-row">
          <td colspan="3"><strong>{pillar}</strong></td>
          <td><strong>{p['weight']} pt</strong></td>
          <td><strong>{p['contribution']} pt</strong></td>
        </tr>"""
        for r in p["rows"]:
            bar_pct = r["raw"] * 10
            breakdown_rows += f"""
        <tr>
          <td class="code-cell">{r['code']}</td>
          <td>{r['label']}</td>
          <td>
            <div class="score-bar-track">
              <div class="score-bar-fill" style="width:{bar_pct}%; background:{score_color(r['raw'])};"></div>
            </div>
            <span class="score-num">{r['raw']}/10</span>
          </td>
          <td>{r['weight']} pt</td>
          <td>{r['contribution']} pt</td>
        </tr>"""

    # GAP analyse
    gap_html = ""
    any_gaps = False
    for gap_label, items in rd["gaps"].items():
        if not items:
            continue
        any_gaps = True
        items_html = "".join(
            f"<li><strong>{r['label']}</strong> ({r['raw']}/10) &mdash; {CRITERIA[r['code']]['advice']}</li>"
            for r in items
        )
        gap_html += f"""
        <div class="gap-block">
          <h4>{gap_label}</h4>
          <ul>{items_html}</ul>
        </div>"""
    if not any_gaps:
        gap_html = "<p>Geen significante blinde vlekken gevonden &mdash; alle criteria scoren ruim voldoende.</p>"

    # Top 3 prioriteiten
    priorities_html = ""
    for i, r in enumerate(rd["priorities"], start=1):
        kind = "Quick Win" if CRITERIA[r["code"]]["quick_win"] else "Strategisch"
        priorities_html += f"""
        <div class="priority-card">
          <div class="priority-rank">{i}</div>
          <div>
            <div class="priority-tag">{kind}</div>
            <strong>{r['label']}</strong> <span class="score-num">({r['raw']}/10)</span>
            <p>{CRITERIA[r['code']]['advice']}</p>
          </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<title>GEO Benchmark Rapport &mdash; {rd['brand']}</title>
<style>
  :root {{
    --bg: #0f1115;
    --panel: #171a21;
    --panel-2: #1e222b;
    --border: #2a2f3a;
    --text: #e8e9ec;
    --text-dim: #9aa0ac;
    --accent: {color};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
  }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 40px 24px 80px; }}
  header {{ margin-bottom: 32px; }}
  header .eyebrow {{ color: var(--text-dim); font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; }}
  header h1 {{ font-size: 30px; margin: 6px 0 4px; }}
  header .meta {{ color: var(--text-dim); font-size: 14px; }}

  .score-hero {{
    display: flex; align-items: center; gap: 28px;
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 14px; padding: 28px; margin: 24px 0 32px;
  }}
  .score-circle {{
    width: 130px; height: 130px; border-radius: 50%;
    border: 8px solid var(--accent);
    display: flex; align-items: center; justify-content: center;
    flex-direction: column; flex-shrink: 0;
  }}
  .score-circle .num {{ font-size: 34px; font-weight: 700; }}
  .score-circle .denom {{ font-size: 12px; color: var(--text-dim); }}
  .score-hero .label {{ font-size: 22px; font-weight: 700; color: var(--accent); margin-bottom: 4px; }}
  .score-hero .desc {{ color: var(--text-dim); font-size: 14px; max-width: 560px; }}

  .knockout-box {{
    display: flex; gap: 16px; align-items: flex-start;
    background: var(--panel); border: 1px solid var(--border);
    border-left: 4px solid var(--accent);
    border-radius: 10px; padding: 18px 20px; margin-bottom: 32px;
  }}
  .badge {{ font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 999px; letter-spacing: 0.05em; }}
  .badge.pass {{ background: rgba(26,158,92,0.15); color: #3cd08a; }}
  .badge.fail {{ background: rgba(192,57,43,0.15); color: #ff6b5c; }}
  .knockout-box ul {{ margin: 8px 0 0; padding-left: 18px; color: var(--text-dim); font-size: 14px; }}

  section {{ margin-bottom: 40px; }}
  h2 {{ font-size: 19px; border-bottom: 1px solid var(--border); padding-bottom: 10px; margin-bottom: 18px; }}

  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{ text-align: left; color: var(--text-dim); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; padding: 8px 10px; }}
  td {{ padding: 10px; border-top: 1px solid var(--border); vertical-align: middle; }}
  .code-cell {{ color: var(--text-dim); font-family: 'SF Mono', Consolas, monospace; font-size: 12px; }}
  tr.pillar-row td {{ background: var(--panel-2); padding-top: 14px; padding-bottom: 8px; border-top: 1px solid var(--border); }}
  .score-bar-track {{ display: inline-block; width: 90px; height: 6px; background: #2a2f3a; border-radius: 4px; overflow: hidden; vertical-align: middle; margin-right: 8px; }}
  .score-bar-fill {{ height: 100%; border-radius: 4px; }}
  .score-num {{ font-size: 12px; color: var(--text-dim); }}

  .gap-block {{ background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; margin-bottom: 14px; }}
  .gap-block h4 {{ margin: 0 0 8px; font-size: 14px; color: #ff9d7a; }}
  .gap-block ul {{ margin: 0; padding-left: 18px; font-size: 14px; color: var(--text-dim); }}
  .gap-block li {{ margin-bottom: 6px; }}
  .gap-block strong {{ color: var(--text); }}

  .priority-card {{
    display: flex; gap: 16px; align-items: flex-start;
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 10px; padding: 16px 20px; margin-bottom: 12px;
  }}
  .priority-rank {{
    width: 32px; height: 32px; border-radius: 50%; background: var(--accent);
    color: #0f1115; font-weight: 700; display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
  }}
  .priority-tag {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-dim); margin-bottom: 2px; }}
  .priority-card p {{ margin: 6px 0 0; color: var(--text-dim); font-size: 14px; }}

  footer {{ color: var(--text-dim); font-size: 12px; margin-top: 50px; border-top: 1px solid var(--border); padding-top: 16px; }}
</style>
</head>
<body>
<div class="wrap">

  <header>
    <div class="eyebrow">GEO Benchmark Rapport &middot; v2.0</div>
    <h1>{rd['brand']}</h1>
    <div class="meta">{rd['domain']} &middot; gegenereerd op {rd['generated_at']}</div>
  </header>

  {knockout_html}

  <div class="score-hero">
    <div class="score-circle">
      <div class="num">{rd['total_score']}</div>
      <div class="denom">/ 100</div>
    </div>
    <div>
      <div class="label">{rd['classification']}</div>
      <div class="desc">{rd['classification_desc']}</div>
    </div>
  </div>

  <section>
    <h2>Score Breakdown</h2>
    <table>
      <thead>
        <tr><th>Code</th><th>Criterium</th><th>Score</th><th>Weging</th><th>Bijdrage</th></tr>
      </thead>
      <tbody>
        {breakdown_rows}
      </tbody>
    </table>
  </section>

  <section>
    <h2>GAP-Analyse &amp; Blinde Vlekken</h2>
    {gap_html}
  </section>

  <section>
    <h2>Top 3 Prioriteiten</h2>
    {priorities_html}
  </section>

  <footer>
    GEO Benchmark Model v2.0 &middot; Score = 0 bij falen van de Fase 0 knock-out check (AI-crawler-toegang + server-side rendering).
  </footer>

</div>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

EXAMPLE_DATA = {
    "brand_name": "VoorbeeldMerk",
    "domain": "voorbeeld.nl",
    "phase_0": {
        "ai_crawler_access": True,
        "server_side_rendering": True,
    },
    "scores": {
        "c1_structured_data": 8,
        "c2_chunkability": 7,
        "c3_answerability": 9,
        "c4_bluf": 6,
        "c5_fact_density": 8,
        "c6_entity_clarity": 7,
        "c7_external_mentions": 8,
        "c8_multimodal": 6,
        "c9_share_of_model": 7,
        "c10_sentiment_freshness": 8,
    },
}


def main():
    if len(sys.argv) >= 2:
        input_path = Path(sys.argv[1])
        data = json.loads(input_path.read_text(encoding="utf-8"))
    else:
        data = EXAMPLE_DATA

    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])
    else:
        slug = data.get("domain", data.get("brand_name", "geo-rapport")).replace(".", "-")
        output_path = Path(f"geo_rapport_{slug}.html")

    report_data = compute_report_data(data)
    html = render_html(report_data)
    output_path.write_text(html, encoding="utf-8")
    print(f"Rapport geschreven naar: {output_path.resolve()}")


if __name__ == "__main__":
    main()
