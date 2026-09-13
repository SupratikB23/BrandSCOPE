# BrandSCOPE – Technical Documentation

Deep technical details for contributors and developers.
For setup and usage, see [README.md](./README.md).

---

## Table of Contents

- [The Four Engines](#the-four-engines)
- [Automation Pipeline](#automation-pipeline)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Data Storage](#data-storage)
- [How the Pipeline Works](#how-the-pipeline-works)
- [Development Notes](#development-notes)

---

## The Four Engines

### Engine 01 - Brand DNA Extractor

Builds an intelligence profile of a brand from its website and the open web. Runs locally only (needs Chromium).

**Scraping pipeline:**

1. Sitemap XML parse - fast, no browser, most reliable source of URLs
2. BFS URL discovery via `httpx` - up to 60 pages at depth 3 without a browser
3. JSON-LD structured data mining - services, articles, locations from `<script type="application/ld+json">`
4. Playwright full-render scraping with:
   - `networkidle` wait + `domcontentloaded` fallback + body text polling (8 s)
   - Accordion / `<details>` / Bootstrap collapse expansion
   - Tab panel clicking (up to 5 tabs)
   - Load More button clicking (up to 3 times)
   - Shadow DOM text piercing via `document.createTreeWalker`
   - Same-domain iframe content extraction
   - Raw HTML `httpx` fallback when JS yields fewer than 200 characters
5. Web search via DuckDuckGo DDGS - brand services, differentiators, published articles
6. Gemini synthesis (via `llm.gemini_generate`) - services, USPs, tone, brand keywords

**Output fields:**

| Field | Description |
|---|---|
| `services` | Clean noun phrases (2-7 words) - e.g. "Speech-to-Text Engine (Saaras)" |
| `tone_adjectives` | AI-classified voice descriptors - e.g. "visionary", "authoritative" |
| `tone_sample` | Representative sentence extracted from page text |
| `uses_first_person` | Boolean from AI perspective classification |
| `usps` | Specific, factual differentiators |
| `existing_article_titles` | Merged from scraped links, JSON-LD, case studies, internet search |
| `top_keywords` | AI brand keywords prepended to NLP noun chunks (up to 50) |
| `locations` | Cities and regions from JSON-LD + text patterns |

---

### Engine 02 - Live Trend Research

Pulls real-time signals and classifies them relative to the brand.

**Sources:**
- Google News RSS - 5 industry queries + 4 brand queries
- DuckDuckGo DDGS - 4 industry queries + 4 brand queries (every call wrapped; failures return empty)
- `DISABLE_DDGS=1` forces RSS only (used when DuckDuckGo rate-limits datacenter IPs)

**Segments:** `brand_news`, `brand_future`, `industry_trend`, `competitive`

**AI layer:** one Gemini call re-classifies every item, writes a 2-sentence brand trajectory summary, and generates 10-14 article angles. If every model fails, template angles are used and `model_used` is empty.

**Fallback:** if fewer than 8 results come back, the same queries are retried with 2025 in place of 2026.

---

### Engine 03 - Article Brief Builder

Rule-based, no LLM call. Given DNA + a trend + an angle:

- Primary keyword: first brand/top keyword (filler words excluded) that appears in the angle or trend title
- Secondary keywords, target audience, article type outline (educational / listicle / guide / trend-report / case-study / opinion)
- CTA and brand-reference instructions for the writer

---

### Engine 04 - Article Writer

Writes the full article from the brief + DNA with a scored master prompt.

**Model routing** (`backend/llm.py`, override with `GEMINI_MODELS`):

```
gemini-3.5-flash → gemini-3.5-flash-lite → gemini-flash-latest → groq/llama-3.3-70b-versatile
```

- Per-minute rate limits (429) wait and retry on the same model; daily quota / not found / 503 move to the next model
- Thinking tokens are capped so they cannot truncate the article
- The model that produced the content is stored as `model_used`

**Quality controls:**
- Post-processing repairs missing H1 keyword, question H2s, blockquote stat, Conclusion and FAQ
- Banned phrase filter ("delve into", "game-changer", "in today's fast-paced", ...)
- `quality_check()` - word count, brand mentions, keyword placement, FAQ, conclusion, H2 count
- `compute_seo_aeo_geo_scores()` - deterministic 0-100 rubric per dimension, computed on the final text. Heuristic, not validated against ranking data.

---

## Automation Pipeline

`backend/run_pipeline.py` runs the engines headless. `.github/workflows/daily-article.yml` runs it on a schedule.

| Stage | What happens | LLM calls |
|---|---|---|
| `01_load_dna` | Read committed `clients/{slug}/01_brand_dna/company_dna.json` | 0 |
| `02_trend_research` | Engine 02, save trends | 1 |
| `03_article_brief` | Pick first unwritten angle + best-matching trend (brand news first), rotate article type by day, Engine 03 | 0 |
| `04_article_writer` | Engine 04, score, save `.md` + `.html` | 1 |
| `05_email_delivery` | Gmail SMTP: HTML body with scores + `.md` attachment. Skipped if SMTP secrets are missing | 0 |

- A failed stage marks later stages `skipped` and the script exits 1.
- Every stage is logged to SQLite `runs` and appended to `clients/{slug}/runs/run_log.jsonl`.
- In Actions, the stage table is written to the job summary, outputs are uploaded as an artifact, and `clients/` is committed back with `git pull --rebase` before push.
- The workflow installs only `backend/requirements-pipeline.txt` (no Playwright, no spaCy). `company_scraper.py` imports Playwright lazily so `CompanyDNA` is importable without it.

**Workflow triggers:** `schedule` (`30 3 * * *` = 09:00 IST) and `workflow_dispatch` with inputs `client`, `article_type`, `send_email`, `disable_ddgs`.

**Secrets:** `GOOGLE_API_KEY`, `GROQ_API_KEY`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO` (optional).

---

## Architecture

```
                 ┌──────────── Interactive ────────────┐   ┌──────── Scheduled ─────────┐
Browser (React + Vite)                                     GitHub Actions cron / dispatch
        │ HTTP (JSON)                                              │
        v                                                          v
FastAPI backend (uvicorn, port 8000)                       backend/run_pipeline.py
        │                                                          │
        ├── Engine 01: company_scraper.py  (local only)            │
        │       ├── Playwright, httpx BFS, spaCy, DDGS             │
        │       └── Gemini (llm.py)                                │
        │                                                          │
        ├── Engine 02: trend_researcher.py  <──────────────────────┤
        │       ├── Google News RSS, DDGS                          │
        │       └── Gemini (llm.py)                                │
        │                                                          │
        ├── Engine 03: article_generator.build_brief  <────────────┤
        │                                                          │
        └── Engine 04: article_generator.write_article  <──────────┤
                ├── Gemini chain (llm.py)                          │
                └── Groq fallback                                  │
                                                                   └── delivery.py (SMTP)
Persistence
        ├── SQLite (aiosqlite)  →  data/searchos.db   (incl. runs table)
        └── File system         →  clients/{slug}/0{1-4}_*/, clients/{slug}/runs/
```

---

## Project Structure

```
BrandSCOPE/
|
|-- .github/workflows/
|   `-- daily-article.yml      # Scheduled pipeline
|
|-- backend/
|   |-- server.py              # FastAPI app - REST endpoints + static frontend
|   |-- run_pipeline.py        # Headless Engine 02 → 03 → 04 → email, with run log
|   |-- llm.py                 # Gemini model chain, retry, thinking config
|   |-- delivery.py            # SMTP email delivery
|   |-- company_scraper.py     # Engine 01 - Brand DNA extractor
|   |-- trend_researcher.py    # Engine 02 - Live trend research
|   |-- article_generator.py   # Engine 03 + 04 - Brief builder and article writer
|   |-- database.py            # aiosqlite storage + file storage helpers
|   |-- main.py                # Legacy CLI (scrape + generate in one command)
|   |-- run.py                 # Uvicorn entrypoint
|   |-- requirements.txt       # Full stack (UI + Engine 01)
|   |-- requirements-pipeline.txt  # CI pipeline only
|   `-- .env.example
|
|-- frontend/
|   |-- src/                   # App, Landing, BrandDNA, TrendResearch, BriefBuilder, ArticleWriter
|   `-- dist/                  # Production build (git-ignored, served by FastAPI)
|
|-- data/searchos.db           # SQLite (git-ignored, auto-created)
|
|-- clients/                   # Per-client storage (git-ignored except the demo client)
|   `-- sarvam-ai/
|       |-- 01_brand_dna/
|       |-- 02_trend_research/
|       |-- 03_article_briefs/
|       |-- 04_articles/
|       `-- runs/run_log.jsonl
|
`-- package.json               # Root convenience scripts
```

---

## API Reference

All endpoints accept and return JSON.

### Client Management

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/clients` | List all clients |
| `POST` | `/api/clients` | Create a new client from a URL |
| `GET` | `/api/clients/{id}` | Get a single client with full history |
| `DELETE` | `/api/clients/{id}` | Delete client and all associated data |

### Engine Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/extract-dna` | Engine 01 - Brand DNA extraction (blocks for the crawl) |
| `POST` | `/api/research-trends` | Engine 02 - Live trend research |
| `POST` | `/api/build-brief` | Engine 03 - Article brief |
| `POST` | `/api/write-article` | Engine 04 - Article writing (response includes `model_used`) |

### Persistence Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/clients/{id}/save-dna` | Persist brand DNA |
| `POST` | `/api/clients/{id}/save-trends` | Persist trend report |
| `POST` | `/api/clients/{id}/save-brief` | Persist article brief |
| `POST` | `/api/clients/{id}/save-article` | Persist final article with scores |
| `GET` | `/api/clients/{id}/articles/{article_id}` | Retrieve a saved article |
| `GET` | `/api/runs?limit=100` | Pipeline run log, newest first |

### Engine 01 - Request / Response

```json
// POST /api/extract-dna
{ "url": "https://example.com" }

// Response (CompanyDNA)
{
  "name": "Example Brand",
  "domain": "example.com",
  "services": ["Service Name (Detail)", "..."],
  "tone_adjectives": ["technical", "confident"],
  "tone_sample": "A representative sentence from the site.",
  "uses_first_person": false,
  "usps": ["Specific factual claim", "..."],
  "existing_article_titles": ["Article title", "..."],
  "top_keywords": ["keyword", "..."],
  "locations": ["City", "..."]
}
```

### Engine 02 - Request / Response

```json
// POST /api/research-trends
{
  "services": ["Service Name"],
  "top_keywords": ["keyword"],
  "existing_titles": ["Previously written title"],
  "brand_name": "Example Brand",
  "domain": "example.com"
}

// Response (TrendReport)
{
  "industry": "saas",
  "trends": [
    {
      "title": "Trend headline",
      "summary": "...",
      "source": "Google News",
      "segment": "brand_news",
      "relevance_score": 0.87,
      "published": "Mon, 28 Apr 2026"
    }
  ],
  "brand_summary": "Two-sentence brand trajectory summary.",
  "segments": { "brand_news": 4, "industry_trend": 12, "competitive": 3, "brand_future": 2 },
  "article_angles": ["Ready-to-write article title", "..."],
  "key_themes": ["theme", "..."]
}
```

---

## Data Storage

### SQLite Schema

```
clients
  id, name, domain, slug, url, created_at, updated_at

brand_dna
  id, client_id, dna_json, created_at

trend_reports
  id, client_id, report_json, created_at

article_briefs
  id, client_id, brief_json, article_type, title, created_at

generated_articles
  id, client_id, brief_id, title, article_slug, content_md, word_count,
  seo_title, meta_description, quality_passed,
  seo_score, aeo_score, geo_score, model_used, created_at

runs
  id, run_id, client_id, stage, status, error, model_used,
  detail, trigger, started_at, finished_at
```

### File System Layout

Every engine output is also written under `clients/{slug}/`. Timestamps in filenames are UTC, so runs accumulate instead of overwriting. Pipeline articles are named `{YYYY-MM-DD}-{slug}.md` / `.html`.

---

## How the Pipeline Works

```
1. Add a client (UI) - enter a website URL.

2. Engine 01 - Brand DNA (local)
   Crawl, render, mine JSON-LD, search, synthesize with Gemini.
   Output: services, tone, USPs, keywords, existing articles.

3. Engine 02 - Trend Research
   Google News RSS + DuckDuckGo for industry and brand news.
   Gemini classifies segments and writes brand-aware angles.

4. Engine 03 - Brief Builder
   UI: you pick the angle. Pipeline: first unwritten angle, best-matching trend.

5. Engine 04 - Article Writer
   Model chain writes the article; post-processing, banned-phrase check,
   SEO / AEO / GEO rubric. Saved as Markdown + HTML with JSON-LD.

6. Delivery (pipeline only)
   Email with the HTML article and Markdown attachment; outputs and run log
   committed to the repo.
```

---

## Development Notes

- After changing any `backend/*.py` file, restart the FastAPI server.
- After changing `frontend/src/`, run `npm run build` in `frontend/` (or use `npm run dev`).
- The SQLite database is created at `data/searchos.db` on first start by `init_db()`. New columns and the `runs` table are added non-destructively.
- `clients/` is git-ignored except `clients/sarvam-ai/`, the scheduled demo client. Add `!clients/<slug>/` to `.gitignore` to track another.
- Gemini retires model names without notice. If every Gemini call returns 404, set `GEMINI_MODELS` to a current model list (check `client.models.list()`).
