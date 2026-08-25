"""
HTML-rendering van een GEO-rapport — 1-op-1 dezelfde structuur/opmaak als
`geo_report_generator.py` (knock-out box, score-hero, breakdown-tabel,
GAP-analyse, top-3-prioriteiten), uitgebreid met een bron-badge per
criterium (automatisch gemeten / LLM-schatting / handmatig ingevoerd) —
zie ARCHITECTURE.md sectie 4.

`render_report_body()` levert een HTML-fragment (geen <html>/<head>) dat
zowel ingebed kan worden in de app-pagina (scan_detail.html) als, verpakt
door `render_full_report_html()`, gebruikt wordt voor de PDF-export.
"""

from __future__ import annotations

from app.scoring import CRITERIA, PILLAR_ORDER, SOURCE_LABELS, ScoreReport

REPORT_CSS = """
:root {
  --bg: #0f1115;
  --panel: #171a21;
  --panel-2: #1e222b;
  --border: #2a2f3a;
  --text: #e8e9ec;
  --text-dim: #9aa0ac;
  --accent: __ACCENT__;
}
.geo-report * { box-sizing: border-box; }
.geo-report {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
  padding: 32px 24px 56px;
  border-radius: 14px;
}
.geo-report .eyebrow { color: var(--text-dim); font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; }
.geo-report h1 { font-size: 28px; margin: 6px 0 4px; }
.geo-report .meta { color: var(--text-dim); font-size: 14px; margin-bottom: 24px; }

.geo-report .score-hero {
  display: flex; align-items: center; gap: 28px; flex-wrap: wrap;
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 14px; padding: 28px; margin: 24px 0 32px;
}
.geo-report .score-circle {
  width: 130px; height: 130px; border-radius: 50%;
  border: 8px solid var(--accent);
  display: flex; align-items: center; justify-content: center;
  flex-direction: column; flex-shrink: 0;
}
.geo-report .score-circle .num { font-size: 34px; font-weight: 700; }
.geo-report .score-circle .denom { font-size: 12px; color: var(--text-dim); }
.geo-report .score-hero .label { font-size: 22px; font-weight: 700; color: var(--accent); margin-bottom: 4px; }
.geo-report .score-hero .desc { color: var(--text-dim); font-size: 14px; max-width: 560px; }

.geo-report .knockout-box {
  display: flex; gap: 16px; align-items: flex-start;
  background: var(--panel); border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: 10px; padding: 18px 20px; margin-bottom: 32px;
}
.geo-report .badge { font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 999px; letter-spacing: 0.05em; white-space: nowrap; }
.geo-report .badge.pass { background: rgba(26,158,92,0.15); color: #3cd08a; }
.geo-report .badge.fail { background: rgba(192,57,43,0.15); color: #ff6b5c; }
.geo-report .knockout-box ul { margin: 8px 0 0; padding-left: 18px; color: var(--text-dim); font-size: 14px; }

.geo-report section { margin-bottom: 40px; }
.geo-report h2 { font-size: 19px; border-bottom: 1px solid var(--border); padding-bottom: 10px; margin-bottom: 18px; }

.geo-report table { width: 100%; border-collapse: collapse; font-size: 14px; }
.geo-report th { text-align: left; color: var(--text-dim); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; padding: 8px 10px; }
.geo-report td { padding: 10px; border-top: 1px solid var(--border); vertical-align: middle; }
.geo-report .code-cell { color: var(--text-dim); font-family: 'SF Mono', Consolas, monospace; font-size: 12px; }
.geo-report tr.pillar-row td { background: var(--panel-2); padding-top: 14px; padding-bottom: 8px; border-top: 1px solid var(--border); }
.geo-report .score-bar-track { display: inline-block; width: 90px; height: 6px; background: #2a2f3a; border-radius: 4px; overflow: hidden; vertical-align: middle; margin-right: 8px; }
.geo-report .score-bar-fill { height: 100%; border-radius: 4px; }
.geo-report .score-num { font-size: 12px; color: var(--text-dim); }

.geo-report .source-badge { display: inline-block; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 999px; letter-spacing: 0.03em; margin-left: 6px; white-space: nowrap; }
.geo-report .source-badge.automated { background: rgba(26,158,92,0.15); color: #3cd08a; }
.geo-report .source-badge.llm_estimate { background: rgba(155,89,182,0.18); color: #c890e8; }
.geo-report .source-badge.manual { background: rgba(154,160,172,0.18); color: #b7bcc6; }

.geo-report .gap-block { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; margin-bottom: 14px; }
.geo-report .gap-block h4 { margin: 0 0 8px; font-size: 14px; color: #ff9d7a; }
.geo-report .gap-block ul { margin: 0; padding-left: 18px; font-size: 14px; color: var(--text-dim); }
.geo-report .gap-block li { margin-bottom: 6px; }
.geo-report .gap-block strong { color: var(--text); }

.geo-report .priority-card {
  display: flex; gap: 16px; align-items: flex-start;
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 10px; padding: 16px 20px; margin-bottom: 12px;
}
.geo-report .priority-rank {
  width: 32px; height: 32px; border-radius: 50%; background: var(--accent);
  color: #0f1115; font-weight: 700; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.geo-report .priority-tag { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-dim); margin-bottom: 2px; }
.geo-report .priority-card p { margin: 6px 0 0; color: var(--text-dim); font-size: 14px; }

.geo-report footer { color: var(--text-dim); font-size: 12px; margin-top: 50px; border-top: 1px solid var(--border); padding-top: 16px; }
.geo-report .legend { font-size: 12px; color: var(--text-dim); margin-bottom: 20px; }
.geo-report .legend .source-badge { margin-left: 0; margin-right: 4px; }
"""


def score_color(raw: float) -> str:
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


def source_badge_html(source: str) -> str:
    label = SOURCE_LABELS.get(source, source)
    return f'<span class="source-badge {source}">{label}</span>'


def render_report_css(report: ScoreReport) -> str:
    return f"<style>{REPORT_CSS.replace('__ACCENT__', classification_color(report.classification))}</style>"


def render_report_body(report: ScoreReport, brand: str, domain: str, generated_at: str) -> str:
    if report.knockout_pass:
        knockout_html = f"""
        <div class="knockout-box pass">
          <span class="badge pass">PASS</span>
          <div>
            <strong>Knock-out check geslaagd</strong>
            <ul>
              <li>{"✅" if report.crawler_ok else "❌"} AI-crawler-toegang (GPTBot, PerplexityBot, ClaudeBot, Google-Extended)</li>
              <li>{"✅" if report.ssr_ok else "❌"} Server-side rendering van kerncontent</li>
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
              <li>{"✅" if report.crawler_ok else "❌"} AI-crawler-toegang (GPTBot, PerplexityBot, ClaudeBot, Google-Extended)</li>
              <li>{"✅" if report.ssr_ok else "❌"} Server-side rendering van kerncontent</li>
            </ul>
            <p>Status: <em>Onzichtbaar voor AI due to technical lockout</em></p>
          </div>
        </div>"""

    breakdown_rows = ""
    for pillar in PILLAR_ORDER:
        p = report.pillars[pillar]
        breakdown_rows += f"""
        <tr class="pillar-row">
          <td colspan="3"><strong>{pillar}</strong></td>
          <td><strong>{p['weight']} pt</strong></td>
          <td><strong>{p['contribution']} pt</strong></td>
        </tr>"""
        for r in p["results"]:
            bar_pct = r.raw * 10
            rationale = f'<div class="score-num" style="margin-top:4px;">{r.rationale}</div>' if r.rationale else ""
            breakdown_rows += f"""
        <tr>
          <td class="code-cell">{r.code}</td>
          <td>{r.label} {source_badge_html(r.source)}{rationale}</td>
          <td>
            <div class="score-bar-track">
              <div class="score-bar-fill" style="width:{bar_pct}%; background:{score_color(r.raw)};"></div>
            </div>
            <span class="score-num">{r.raw}/10</span>
          </td>
          <td>{r.weight} pt</td>
          <td>{r.contribution} pt</td>
        </tr>"""

    gap_html = ""
    any_gaps = False
    for gap_label, items in report.gaps.items():
        if not items:
            continue
        any_gaps = True
        items_html = "".join(
            f"<li><strong>{r.label}</strong> ({r.raw}/10) &mdash; {CRITERIA[r.code]['advice']}</li>"
            for r in items
        )
        gap_html += f"""
        <div class="gap-block">
          <h4>{gap_label}</h4>
          <ul>{items_html}</ul>
        </div>"""
    if not any_gaps:
        gap_html = "<p>Geen significante blinde vlekken gevonden &mdash; alle criteria scoren ruim voldoende.</p>"

    priorities_html = ""
    for i, r in enumerate(report.priorities, start=1):
        kind = "Quick Win" if CRITERIA[r.code]["quick_win"] else "Strategisch"
        priorities_html += f"""
        <div class="priority-card">
          <div class="priority-rank">{i}</div>
          <div>
            <div class="priority-tag">{kind}</div>
            <strong>{r.label}</strong> <span class="score-num">({r.raw}/10)</span>
            <p>{CRITERIA[r.code]['advice']}</p>
          </div>
        </div>"""

    legend_html = (
        '<div class="legend">Bronlegenda: '
        + "".join(f"{source_badge_html(code)} {label}&nbsp;&nbsp;" for code, label in SOURCE_LABELS.items())
        + "</div>"
    )

    return f"""
<div class="geo-report">
  <div class="eyebrow">GEO Benchmark Rapport &middot; v2.0</div>
  <h1>{brand}</h1>
  <div class="meta">{domain} &middot; gegenereerd op {generated_at}</div>

  {legend_html}
  {knockout_html}

  <div class="score-hero">
    <div class="score-circle">
      <div class="num">{report.total_score}</div>
      <div class="denom">/ 100</div>
    </div>
    <div>
      <div class="label">{report.classification}</div>
      <div class="desc">{report.classification_desc}</div>
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
"""


def render_full_report_html(report: ScoreReport, brand: str, domain: str, generated_at: str) -> str:
    css = render_report_css(report)
    body = render_report_body(report, brand, domain, generated_at)
    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<title>GEO Benchmark Rapport &mdash; {brand}</title>
{css}
<style>body {{ margin:0; background:#0f1115; }}</style>
</head>
<body>
{body}
</body>
</html>"""
