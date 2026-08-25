# Deployen naar Railway

Deze repo bevat alles wat Railway nodig heeft (`Dockerfile`, `railway.toml`)
— je hoeft alleen de onderstaande stappen in de Railway-UI te doorlopen.
Gebouwd en lokaal geverifieerd (zie onderaan); niet zelf op Railway getest,
dus loop de stappen rustig door.

## 1. Project aanmaken

1. Ga naar [railway.app](https://railway.app) en log in (GitHub-login is het snelst).
2. **New Project → Deploy from GitHub repo** → kies `Kawsfan/GEO-Benchmark-Dashboard`.
   - Eerste keer: Railway vraagt om de GitHub-app te autoriseren voor deze repo.
3. Railway detecteert de `Dockerfile` automatisch (dankzij `railway.toml`) en
   start een build. Die eerste build faalt nog — dat is verwacht, er ontbreken
   nog env vars en een volume (stap 2-3).

## 2. Persistente opslag (verplicht — anders ben je bij elke herstart je data kwijt)

1. In het project: **+ New → Volume**.
2. Mount path: `/data`.
3. Koppel het volume aan de service die je net aanmaakte.

## 3. Environment variables

Ga naar de service → **Variables** en zet:

**Verplicht:**

| Variabele | Waarde | Waarom |
|---|---|---|
| `GEO_DASHBOARD_DB_URL` | `sqlite:////data/geo_dashboard.db` | Laat de SQLite-database op het persistente volume staan (zie stap 2) — anders is elke deploy een lege database. |
| `GEO_DASHBOARD_AUTH_USERNAME` | zelf kiezen | Samen met onderstaande: voorkomt dat een toevallige bezoeker van de link kan rondklikken/scans starten. |
| `GEO_DASHBOARD_AUTH_PASSWORD` | een sterk wachtwoord | Zie boven. Deel dit apart met je collega's (niet via dezelfde link). |

**Aanbevolen (voor de Claude-onderdelen — Fase 2/3/4):**

| Variabele | Waarde |
|---|---|
| `ANTHROPIC_API_KEY` | jouw Anthropic API-key |

Zonder deze key blijft de rest van het dashboard gewoon werken; alleen de
LLM-beoordeelde criteria (C3-C5, C7, C9) blijven op hun laatst bekende/
handmatige waarde staan.

**Optioneel (kostenbeheersing / extra providers) — zie ook `ARCHITECTURE.md` § 4:**

- `GEO_DASHBOARD_LLM_MODEL` (default `claude-opus-5`) — goedkoper model voor
  Fase 2/C7, bv. `claude-haiku-4-5`.
- `GEO_DASHBOARD_DISABLE_LLM_ASSESSMENT=1` / `GEO_DASHBOARD_DISABLE_EXTERNAL_MENTIONS=1` /
  `GEO_DASHBOARD_DISABLE_PHASE3=1` / `GEO_DASHBOARD_DISABLE_CITATION_TRACKING=1` —
  schakel specifieke (kosten makende) onderdelen uit.
- `GEO_DASHBOARD_CITATION_PROVIDERS=claude` (default) — comma-lijst; voeg
  `chatgpt`/`perplexity`/`gemini` toe mits je ook `OPENAI_API_KEY` /
  `PERPLEXITY_API_KEY` / `GEMINI_API_KEY` zet én de service opnieuw bouwt met
  `requirements-citation-extra.txt` meegenomen (pas dan het `Dockerfile` aan
  om die ook te installeren, of voeg de twee extra pakketten toe aan
  `requirements.txt` als je die providers structureel wilt gebruiken).

`PORT` hoef je niet zelf te zetten — Railway doet dat automatisch en de
`Dockerfile` luistert daar al naar.

## 4. Deploy

Na het instellen van de variabelen en het volume: **Deploy** (of push een
nieuwe commit — Railway deployt automatisch bij elke push naar `main`).

Railway geeft je een `*.up.railway.app`-URL onder **Settings → Networking →
Generate Domain**. Dat is de link die je met collega's deelt (samen met het
wachtwoord, via een ander kanaal dan waar je de link zelf deelt).

## 5. Checken of het werkt

1. Open de gegenereerde URL → je krijgt een browser-inlogprompt (HTTP Basic
   Auth) → vul je `GEO_DASHBOARD_AUTH_USERNAME`/`PASSWORD` in.
2. Je komt op `/dashboard` (leeg, want nieuwe database) → voeg een
   organisatie toe → "Scan nu" → check of het rapport verschijnt.
3. Herstart de service handmatig (Railway → **Restart**) en controleer dat
   de organisatie er nog staat — dat bevestigt dat het volume werkt.

## Lokaal gebouwd/geverifieerd, wat niet

Lokaal bevestigd (deze sandbox kon geen Docker-daemon draaien, dus niet via
`docker build`, maar via een equivalente installatie):

- De exacte systeembibliotheken in de `Dockerfile` (WeasyPrint-dependencies)
  zijn correct — geverifieerd doordat dit sandbox-systeem exact diezelfde
  package-set had en PDF-export daarmee al werkte.
- De app start schoon met alleen `requirements.txt` (geen dev-dependencies)
  en met de exacte `Dockerfile`-opstartcommando
  (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`).
- De Basic Auth-middleware werkt end-to-end (401 zonder/met verkeerde
  credentials, 200 met de juiste) tegen een echt draaiende server.

Niet geverifieerd (kon ik vanuit deze sandbox niet testen): de daadwerkelijke
`docker build` van het `Dockerfile` zelf, en het Railway-platform (volume-
mount, env-var-UI, gegenereerde domeinen). Loop stap 1-5 hierboven door en
laat het weten als de build op Railway faalt — dan debug ik de foutmelding.
