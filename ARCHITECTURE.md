# GEO Scan Dashboard — MVP-scope & architectuur

Dit document beantwoordt de vier vragen uit de bouwprompt: MVP-scope, datamodel,
bouwvolgorde, en de manier waarop de UI onderscheid maakt tussen automatisch
gemeten, LLM-geschatte en handmatig ingevoerde scores.

## 1. MVP-scope: wat nu, wat later

**Nu gebouwd (dit pakket):**

- Organisaties beheren (CRUD): naam, domein, sector, actief/inactief.
- Scans: "Scan nu"-actie per organisatie, resultaat met tijdstempel toegevoegd
  aan de historie (nooit overschrijven).
- Fase 0 knock-out, geautomatiseerd:
  - `robots.txt` ophalen, `Disallow` checken voor `GPTBot`, `PerplexityBot`,
    `ClaudeBot`, `Google-Extended`.
  - Raw HTML-fetch (geen JS) vs. een simpele tekstlengte-heuristiek als proxy
    voor SSR-afhankelijkheid (zie beperking hieronder).
- C1 Structured data, geautomatiseerd: JSON-LD (`schema.org`) parsen +
  DCTERMS/Dublin Core meta-tags, score op aanwezigheid/volledigheid van
  Organization/Article/FAQPage/Product/Dataset.
- C2 Chunkability, geautomatiseerd: heuristiek op gem. paragraaflengte,
  H2/H3-gebruik, lijsten/tabellen.
- C10 Freshness-deel, geautomatiseerd: `dateModified` (JSON-LD),
  `article:modified_time`, `DCTERMS.modified` uit de pagina parsen.
- C3 Answerability, C4 BLUF, C5 Fact density, **Fase 2, geautomatiseerd**:
  één Claude-call per pagina (`app/automation/llm_rubric.py`), met een vaste
  beoordelingsprompt die exact de criteriumomschrijving uit `app/scoring.py`
  gebruikt. Retourneert score 0-10 + korte onderbouwing per criterium,
  opgeslagen als bron `llm_estimate` met de onderbouwing in `rationale` zodat
  een mens het op de scan-detailpagina kan controleren/corrigeren. Faalt de
  LLM-call (geen credentials, rate limit, netwerkfout) dan degradeert de scan
  gracieus naar de laatst bekende handmatige/LLM-waarde voor die criteria —
  nooit een mislukte scan.
- C6 Entity clarity, **Fase 3, geautomatiseerd**: publieke Wikidata-API
  (`app/automation/entity_clarity.py`, geen API-key nodig). Zoekt een item op
  merknaam; een confidente match wordt gemaakt via het officiële-website-
  attribuut (P856) tegen het scan-domein, anders valt de check terug op het
  eerste zoekresultaat als onzekere kandidaat (lagere score, expliciet
  gemarkeerd in de rationale). Score = aanwezigheid/confidence + volledigheid
  van kernattributen (oprichtingsdatum, land, hoofdkantoor, branche, website,
  logo).
- C7 External mentions, **Fase 3, geautomatiseerd**: één Claude-call met de
  server-side `web_search`-tool (`app/automation/external_mentions.py`) zoekt
  zelf naar recente vermeldingen in onafhankelijke bronnen en beoordeelt
  aantal + kwaliteit tegen dezelfde 0-10-schaal. Enige Fase 3-check met
  doorlopende externe kosten per scan (Claude + web-search) — zie sectie 4.
- C8 Multimodaal, **Fase 3, geautomatiseerd**: heuristiek
  (`app/automation/multimodal.py`) op links naar bekende video-/social-/
  reviewplatformen (YouTube, Instagram, TikTok, Facebook, LinkedIn,
  X/Twitter, Trustpilot) in de al opgehaalde homepage-HTML — geen extra
  request. Meet alleen link-aanwezigheid, niet daadwerkelijke activiteit
  (dat vereist per-platform OAuth/API-toegang, buiten scope).
- C9 Share of Model, **Fase 4, geautomatiseerd**: een beheerbare promptset
  per sector (`/promptsets`) wordt maandelijks (of handmatig via
  "Citatiecheck nu") tegen de ingeschakelde providers uitgevoerd
  (`app/citation/`). Detectie: gratis stringmatch op merknaam/domein,
  gevolgd door — alleen bij een treffer — één korte Claude-classificatiecall
  voor "genoemd" vs. "geciteerd met link" + sentiment. Resultaat per
  (prompt × provider) opgeslagen in `citation_runs`; C9 in `run_scan()` is
  een pure DB-read van de laatste 90 dagen (géén nieuwe provider-calls per
  scan). Kostenlimiet per organisatie (`citation_budget_usd_per_month`,
  default $5/maand) — zie sectie 4.
- Het **sentiment-deel van C10**: nog niet geautomatiseerd (dat is
  inhoudelijk hetzelfde AI-antwoorden-sentiment als C9 meet, maar dan per
  scan-pagina i.p.v. per sector-promptset — geen aparte bouwstap waard).
  Blijft **handmatige JSON/UI-invoer**, zodat het dashboard nu al bruikbaar
  is met een compleet rapport.
- Dashboard-overzicht: huidige score + classificatie + trendlijn per
  organisatie, en een vergelijkingsview van meerdere organisaties naast elkaar.
- Detailrapport per scan: score-breakdown per pijler/criterium, GAP-analyse,
  top-3-prioriteiten — 1-op-1 dezelfde structuur en styling als
  `geo_report_generator.py`, nu gerenderd vanuit de database in plaats van een
  los JSON-bestand.
- PDF-export per scan.
- Maandelijkse scheduler (APScheduler) die alle actieve organisaties opnieuw
  scant, alsook (los, vóór de scan) een maandelijkse citatie-check draait
  (Fase 4) en een nieuwe scan-rij toevoegt (geen overschrijving).

Met Fase 4 is elk van de 10 criteria nu op zijn minst gedeeltelijk
geautomatiseerd — de resterende "niet-automatische" delen zijn bewuste
scope-keuzes (zie hieronder), geen doorgeschoven fases.

**Bekende beperking Fase 0 SSR-check:** een echte diff tussen raw HTML en een
headless-browser-render (Playwright) is nauwkeuriger dan de tekstlengte-
heuristiek die nu gebruikt wordt. De heuristiek is een pragmatische MVP-keuze
(geen headless-browserafhankelijkheid in de scan-worker); de check is
gebouwd als vervangbare strategie (`app/automation/phase0_knockout.py`) zodat
een Playwright-render er later naast of voor in de plaats kan.

**Afwijking van het bestaande script:** `geo_report_generator.py` noemt C10
"Contextueel Sentiment & Actualiteit" (twee dingen in één criterium). Alleen
het freshness-deel (datum) is Fase-1-automatiseerbaar; het sentiment-deel
(toon van AI-antwoorden) hoort inhoudelijk bij Fase 4 (citation tracking) en
blijft tot die tijd handmatig/LLM-schatting.

## 2. Datamodel

SQLite voor de MVP (via SQLModel/SQLAlchemy), makkelijk later naar Postgres
te migreren (zelfde ORM-laag, alleen de connection string wijzigt).

```
organizations
  id                  PK
  name                text, verplicht
  domain              text, verplicht (bv. "voorbeeld.nl", zonder protocol)
  sector              text, vrij veld       -- koppelt aan citation_prompts.sector
  is_active           bool, default true   -- meegenomen in maandelijkse scan
  citation_budget_usd_per_month  float, nullable, default 5.0  -- Fase 4-kostenlimiet, null = geen limiet
  created_at          datetime
  updated_at          datetime

scans
  id                  PK
  organization_id     FK -> organizations.id
  triggered_by        enum: manual | scheduled
  created_at          datetime            -- scan-tijdstempel (historie, nooit update)
  knockout_pass        bool
  crawler_ok           bool
  ssr_ok                bool
  total_score          float              -- 0 als knockout faalt
  classification        text
  classification_desc   text
  status                 enum: pending | running | completed | failed
  error_message           text, nullable

scan_criterion_scores
  id                  PK
  scan_id             FK -> scans.id
  code                text   -- c1_structured_data ... c10_sentiment_freshness
  raw_score            float  (0-10)
  weight                float (snapshot van de weging t.t.v. scan, i.v.m. toekomstige modelwijzigingen)
  contribution          float  (afgeleid, weight * raw/10)
  source                enum: automated | llm_estimate | manual
  rationale             text, nullable   -- LLM-onderbouwing of handmatige toelichting
  measured_at            datetime, nullable  -- wanneer de automatische meting liep

citation_prompts        -- Fase 4, beheerd via /promptsets
  id                  PK
  sector               text
  prompt_text           text
  is_active              bool

citation_runs            -- Fase 4, één rij per (prompt × provider)-combinatie
  id                  PK
  organization_id      FK -> organizations.id
  prompt_id             FK -> citation_prompts.id
  provider               text  (chatgpt | perplexity | claude | gemini)
  run_at                 datetime
  cited                   bool
  citation_type            enum: not_mentioned | mentioned | cited_with_link
  sentiment                 text, nullable
  raw_response               text, nullable
  cost_usd                    float, nullable  -- t.b.v. kostenraming/limiet per organisatie
```

Indexen: `scans(organization_id, created_at)` voor trendlijnen,
`scan_criterion_scores(scan_id)`, `citation_runs(organization_id, run_at)`.

## 3. Bouwvolgorde (dit pakket)

1. Scoring-laag (`app/scoring.py`) — 1-op-1 overgenomen `CRITERIA`, `classify`,
   GAP- en top-3-logica uit `geo_report_generator.py`, nu werkend op
   ORM-objecten i.p.v. een los JSON-dict.
2. Datamodel + SQLite (`app/models.py`, `app/database.py`).
3. Fase 1 automatisering (`app/automation/`): knock-out, C1, C2, C10-freshness.
4. FastAPI-routers: organisaties CRUD, scan starten (handmatige aanvulling +
   automatische criteria), dashboardoverzicht + vergelijking, scandetail,
   PDF-export.
5. Server-rendered templates (Jinja2) hergebruiken de bestaande rapport-CSS/opmaak.
6. APScheduler-job voor de maandelijkse scan van alle actieve organisaties.
7. Fase 4 (`app/citation/`): promptset-beheer, provider-integraties
   (Claude/OpenAI/Perplexity/Gemini), stringmatch+LLM-detectie, kostenlimiet
   per organisatie, en een aparte maandelijkse scheduler-job die vóór de
   reguliere scan draait zodat C9 met verse data gevoed wordt.

## 4. Fase 2/3/4 — kosten & configuratie

Drie soorten checks maken externe (Claude-)kosten: de Fase 2-rubric
(`app/automation/llm_rubric.py`, per scan, mits paginatekst beschikbaar), de
Fase 3-C7-check (`app/automation/external_mentions.py`, per scan, gebruikt de
`web_search`-tool), en de Fase 4-citatie-check (`app/citation/`, **los van
de scan-cadans** — maandelijks via de scheduler, of handmatig via
"Citatiecheck nu"). Dat laatste schaalt met
`organisaties × actieve prompts × providers × frequentie` — precies de
kostenwaarschuwing uit de bouwprompt — en heeft daarom een eigen,
per-organisatie kostenlimiet (zie hieronder), los van de globale env-var-
schakelaars voor Fase 2/3.

**Fase 2/3:**

- `ANTHROPIC_API_KEY` (of een `ant auth login`-profiel) moet geconfigureerd
  zijn; zonder credentials degradeert elke scan gracieus naar de laatst
  bekende handmatige/LLM-waarde voor de betreffende criteria (geen mislukte
  scan, geen crash) — C6 (Wikidata) en C8 (multimodaal-heuristiek) maken geen
  API-kosten en blijven gewoon draaien.
- `GEO_DASHBOARD_LLM_MODEL` — modelkeuze voor Fase 2 en C7, default
  `claude-opus-5`. Zet dit naar bv. `claude-sonnet-5` of `claude-haiku-4-5`
  om de kosten per scan te verlagen bij hoog volume.
- `GEO_DASHBOARD_DISABLE_LLM_ASSESSMENT=1` — schakelt Fase 2 (C3-C5) uit.
- `GEO_DASHBOARD_DISABLE_EXTERNAL_MENTIONS=1` — schakelt alleen C7 uit (de
  enige Fase 3-check met externe kosten); C6/C8 blijven actief.
- `GEO_DASHBOARD_DISABLE_PHASE3=1` — schakelt C6, C7 én C8 in één keer uit.

**Ontwerpkeuze C7**: de bouwprompt noemt zowel "een SEO-tool met
backlink-/mentions-data" als "periodieke gerichte web-search-queries" als
optie. Dit pakket implementeert de tweede optie via Claude's server-side
`web_search`-tool — geen losse SEO-tool-integratie/API-key nodig, wel
onderhevig aan de nauwkeurigheid van wat een web-search-doorsnede oplevert.
Een SEO-tool-koppeling kan later als alternatieve/aanvullende bron naast
`assess_external_mentions()` toegevoegd worden zonder het datamodel te
wijzigen (zelfde `llm_estimate`/`rationale`-opslag).

**Fase 4 — kostenbeheersing (de expliciete "waarschuwing voor mezelf als
bouwer" uit de bouwprompt):**

- `Organization.citation_budget_usd_per_month` — harde bovengrens op de som
  van `CitationRun.cost_usd` binnen de lopende kalendermaand, **default $5**
  per organisatie. De runner checkt dit vóór elke provider-call
  (check-before-call, dus de laatste toegestane call mag nog afronden i.p.v.
  halverwege afgebroken te worden); resterende (prompt × provider)-
  combinaties worden geskipt zodra de limiet bereikt is. Bewerkbaar op de
  organisatiepagina; leeg = geen limiet.
- Kostenschatting per call: token-gebaseerd waar `usage`-data beschikbaar is
  (Claude/OpenAI/Perplexity/Gemini geven dit terug), anders een vlakke
  fallback (`FALLBACK_COST_PER_CALL_USD`) zodat kostenbewaking nooit
  stilzwijgend "gratis" aanneemt. Tarieven in `app/citation/providers.py`
  (`PRICING`) zijn schattingen — controleer/actualiseer ze periodiek.
- `GEO_DASHBOARD_CITATION_PROVIDERS` — komma-lijst welke providers de
  citatie-check probeert, default **alleen `claude`** (de enige provider met
  een tegen de echte SDK geverifieerde integratie — zie
  `app/citation/providers.py` voor het vertrouwensniveau per provider).
  Uitbreiden naar `claude,chatgpt,perplexity,gemini` vereist ook
  `OPENAI_API_KEY`/`PERPLEXITY_API_KEY`/`GEMINI_API_KEY` en de extra
  dependencies uit `requirements-citation-extra.txt`.
- `GEO_DASHBOARD_DISABLE_CITATION_TRACKING=1` — schakelt Fase 4 volledig uit
  (geen citatie-runs, C9 blijft op de laatst bekende handmatige waarde).
- Detectie is kostenbewust ontworpen: de gratis stringmatch bepaalt eerst
  of het merk überhaupt voorkomt; alleen bij een treffer volgt de (goedkope)
  Claude-classificatiecall voor het onderscheid "genoemd" vs. "geciteerd met
  link" + sentiment — geen classificatiekosten voor het merendeel van de
  "niet genoemd"-uitkomsten.
- **C9 in `run_scan()` doet géén nieuwe provider-calls**: het is een pure
  lezing van `citation_runs` uit de laatste 90 dagen
  (`app/citation/scoring.py`). De citatie-checks zelf lopen op hun eigen
  maandelijkse schema (of handmatig via "Citatiecheck nu" op de
  organisatiepagina), zodat een gewone scan snel en gratis blijft.

## 5. Bronvermelding in de UI

Elke criteriumscore toont een badge:

- 🟢 **Automatisch gemeten** — Fase 1/3-heuristiek/parsing/API, met tijdstip
  van meting.
- 🟣 **LLM-schatting** — modelbeoordeling met onderbouwing (Fase 2/3-C7/
  Fase 4-C9), markeerbaar als "gecontroleerd door mens" na handmatige
  correctie op de scan-detailpagina.
- ⚪ **Handmatig ingevoerd** — door een gebruiker in de UI ingevuld, of nog
  geen automatische meting beschikbaar (bv. C9 zonder citatie-data).

Dit onderscheid staat zowel op de scan-detailpagina (per criterium-rij) als
in de PDF-export, zodat het rapport nooit ten onrechte overkomt als volledig
geautomatiseerd gemeten.
