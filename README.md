# GEO Scan Dashboard

Dashboard-versie van het GEO Benchmark Model (v2.0): organisaties beheren,
scans uitvoeren (handmatig of maandelijks automatisch), trend per
organisatie volgen, en per scan hetzelfde HTML/PDF-rapport genereren als
het oorspronkelijke `geo_report_generator.py`-script.

Zie [`ARCHITECTURE.md`](./ARCHITECTURE.md) voor de MVP-scope, het
datamodel en de fasering van de automatisering (Fase 1 t/m 4).

## Wat werkt er nu (Fase 1 t/m 4 — alle 10 criteria op zijn minst deels geautomatiseerd)

- Organisaties beheren (toevoegen/bewerken/verwijderen), incl. een
  maandelijkse kostenlimiet voor Fase 4-citatiechecks.
- "Scan nu" per organisatie: voert automatisch de Fase 0 knock-out check,
  C1 (structured data), C2 (chunkability), het freshness-deel van C10, C6
  (Wikidata) en C8 (multimodaal/social-links) uit tegen de live pagina, laat
  C3/C4/C5 (Answerability, BLUF, Fact density) en C7 (externe vermeldingen,
  via web-search) door Claude beoordelen, leest C9 (Share of Model) uit de
  laatste citatie-data, en combineert dat met de laatst ingevulde handmatige
  scores voor wat nog ontbreekt.
- **Promptsets** (`/promptsets`): per sector een beheerbare set vragen voor
  de Fase 4-citatiecheck.
- **Citatiecheck** per organisatie (`/organizations/{id}/citations`):
  handmatig te starten ("Citatiecheck nu") of maandelijks automatisch; stuurt
  de promptset van de sector naar de ingeschakelde AI-providers (default:
  alleen Claude) en meet of/hoe het merk wordt genoemd — met een
  per-organisatie kostenlimiet.
- Maandelijkse automatische scan + citatiecheck van alle actieve
  organisaties (in-process via APScheduler, of extern via
  `scripts/run_monthly_scan.py` / `scripts/run_monthly_citation_check.py`).
- Dashboard-overzicht met score, classificatie, trendlijn en vergelijking
  tussen organisaties.
- Scan-detailpagina: score-breakdown, GAP-analyse, top-3-prioriteiten —
  met een bron-badge per criterium (**automatisch gemeten** /
  **LLM-schatting** / **handmatig ingevoerd**).
- Handmatige criteria én LLM-schattingen zijn direct op de scan-detailpagina
  te controleren/corrigeren; dat herberekent de totaalscore en classificatie
  van díe scan.
- PDF-export per scan.

### Claude-credentials (Fase 2, C7, Fase 4)

De LLM-rubric (C3-C5), de C7-check en de Fase 4-citatiecheck hebben toegang
tot de Claude API nodig: zet `ANTHROPIC_API_KEY`, of log in met
`ant auth login`. Zonder credentials degradeert elke scan/citatiecheck
gracieus (die criteria blijven op hun laatst bekende waarde staan, niets
mislukt) — C6 (Wikidata) en C8 (multimodaal-heuristiek) hebben geen Claude
nodig en blijven gewoon werken.

ChatGPT/Perplexity/Gemini als extra Fase 4-providers zijn optioneel: zet
`GEO_DASHBOARD_CITATION_PROVIDERS=claude,chatgpt,perplexity,gemini`, de
bijbehorende `OPENAI_API_KEY`/`PERPLEXITY_API_KEY`/`GEMINI_API_KEY`, en
installeer `pip install -r requirements-citation-extra.txt`. Zie
`app/citation/providers.py` voor het vertrouwensniveau per provider (Claude
volledig geverifieerd tegen de officiële SDK; de andere drie structureel
geverifieerd tegen de geïnstalleerde SDK's, maar controleer modelnamen/
pricing zelf voor productiegebruik).

Zie ARCHITECTURE.md § 4 voor de volledige kostenbeheersing
(`GEO_DASHBOARD_LLM_MODEL`, `GEO_DASHBOARD_DISABLE_LLM_ASSESSMENT`,
`GEO_DASHBOARD_DISABLE_EXTERNAL_MENTIONS`, `GEO_DASHBOARD_DISABLE_PHASE3`,
`GEO_DASHBOARD_DISABLE_CITATION_TRACKING`, en de per-organisatie
`citation_budget_usd_per_month`, default $5/maand).

## Installatie

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
# Optioneel, voor ChatGPT/Perplexity/Gemini als Fase 4-providers naast Claude:
# pip install -r requirements-citation-extra.txt
```

WeasyPrint (PDF-export) heeft op sommige systemen extra systeembibliotheken
nodig (Pango/Cairo). Zie de
[WeasyPrint-installatie-instructies](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation)
als `pip install` niet voldoende is. Zonder die bibliotheken werkt de rest
van het dashboard gewoon door — alleen de PDF-download faalt dan.

## Starten

```bash
uvicorn app.main:app --reload
```

Dashboard op <http://localhost:8000/dashboard>. De SQLite-database wordt bij
de eerste start automatisch aangemaakt in `data/geo_dashboard.db`.

Zet `GEO_DASHBOARD_DISABLE_SCHEDULER=1` om de in-process maandelijkse
scheduler uit te schakelen (bv. in tests, of als je liever een externe cron
gebruikt via `scripts/run_monthly_scan.py`).

## Tests

```bash
pytest
```

## Legacy CLI

Het oorspronkelijke losse script staat ongewijzigd in
[`scripts/legacy_geo_report_generator.py`](./scripts/legacy_geo_report_generator.py)
voor wie zonder dashboard een eenmalig rapport uit een JSON-bestand wil
genereren.
