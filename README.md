# GEO Scan Dashboard

Dashboard-versie van het GEO Benchmark Model (v2.0): organisaties beheren,
scans uitvoeren (handmatig of maandelijks automatisch), trend per
organisatie volgen, en per scan hetzelfde HTML/PDF-rapport genereren als
het oorspronkelijke `geo_report_generator.py`-script.

Zie [`ARCHITECTURE.md`](./ARCHITECTURE.md) voor de MVP-scope, het
datamodel en de fasering van de automatisering (Fase 1 t/m 4).

## Wat werkt er nu (Fase 1 + Fase 2)

- Organisaties beheren (toevoegen/bewerken/verwijderen).
- "Scan nu" per organisatie: voert automatisch de Fase 0 knock-out check,
  C1 (structured data), C2 (chunkability) en het freshness-deel van C10 uit
  tegen de live pagina, laat C3/C4/C5 (Answerability, BLUF, Fact density)
  door Claude beoordelen tegen een vaste rubric, en combineert dat met de
  laatst ingevulde handmatige scores voor de overige criteria.
- Maandelijkse automatische scan van alle actieve organisaties
  (in-process via APScheduler, of extern via `scripts/run_monthly_scan.py`).
- Dashboard-overzicht met score, classificatie, trendlijn en vergelijking
  tussen organisaties.
- Scan-detailpagina: score-breakdown, GAP-analyse, top-3-prioriteiten —
  met een bron-badge per criterium (**automatisch gemeten** /
  **LLM-schatting** / **handmatig ingevoerd**).
- Handmatige criteria én LLM-schattingen zijn direct op de scan-detailpagina
  te controleren/corrigeren; dat herberekent de totaalscore en classificatie
  van díe scan.
- PDF-export per scan.

Fase 3 (Wikidata/mentions/social-API's) en Fase 4 (Share of Model / citation
tracking) zijn nog niet geautomatiseerd — zie ARCHITECTURE.md voor waarom en
wat er al aan datamodel klaarstaat.

### Fase 2 — Claude-credentials

De LLM-rubric heeft toegang tot de Claude API nodig: zet `ANTHROPIC_API_KEY`,
of log in met `ant auth login`. Zonder credentials degradeert elke scan
gracieus (C3-C5 blijven op hun laatst bekende waarde staan, de scan mislukt
niet). Zie ARCHITECTURE.md § 4 voor kostenbeheersing
(`GEO_DASHBOARD_LLM_MODEL`, `GEO_DASHBOARD_DISABLE_LLM_ASSESSMENT`).

## Installatie

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
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
