<img width="2911" height="1262" alt="BrandSCOPE_generated" src="https://github.com/user-attachments/assets/c07f718f-ab80-42eb-a382-a5276a6c8eac" />


# BrandSCOPE – Brand Search Content Optimization & Publishing Engine

[![daily-article](https://github.com/SupratikB23/BrandSCOPE/actions/workflows/daily-article.yml/badge.svg)](https://github.com/SupratikB23/BrandSCOPE/actions/workflows/daily-article.yml)

**A 4-engine content pipeline that extracts a brand's DNA, tracks live industry and brand news, builds an SEO/AEO/GEO-structured brief, writes the article in the brand's voice, and delivers it — on a daily schedule with no human in the loop.**

Free end to end: GitHub Actions, Gemini free tier, Groq free tier, Gmail SMTP, SQLite.

---

## Table of Contents

- [Overview](#overview)
- [The Four Engines](#the-four-engines)
- [Automation (GitHub Actions)](#automation-github-actions)
- [Tech Stack](#tech-stack)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Project](#running-the-project)
- [Known Limits](#known-limits)

---

## Overview

BrandSCOPE runs as two layers over the same engine code:

| Layer | What it does | Where it runs |
|---|---|---|
| **Interactive UI** | React app that runs each engine on demand, with review at every step | Locally (FastAPI + React) |
| **Scheduled pipeline** | `backend/run_pipeline.py` runs Engine 02 → 03 → 04 → email → commit, unattended | GitHub Actions cron, daily 09:00 IST |

Every article is structured for:

- **SEO** — traditional search ranking signals
- **AEO** — Answer Engine Optimization (featured snippets, AI Overviews)
- **GEO** — Generative Engine Optimization (citation by ChatGPT, Perplexity, Claude)

---

## The Four Engines

**Engine 01 – Brand DNA Extractor** <br>
Crawls up to 60 pages with sitemap parsing + httpx BFS (depth 3), mines JSON-LD, renders with Playwright (accordion/tab expansion, shadow DOM, iframes, raw-HTML fallback), runs web searches, and synthesizes a structured brand profile with Gemini. Runs locally; its output is committed as the pipeline's input.

**Engine 02 – Live Trend Research** <br>
Pulls Google News RSS and DuckDuckGo for industry and brand-specific news, then uses Gemini to classify each item into `brand_news`, `brand_future`, `industry_trend`, or `competitive`, write a brand trajectory summary, and generate 10–14 article angles. DuckDuckGo failures degrade gracefully to RSS only.

**Engine 03 – Article Brief Builder** <br>
Rule-based (no LLM call): picks the primary keyword from brand keywords that overlap the angle, sets secondary keywords, audience, an outline per article type, CTA, and brand-reference rules.

**Engine 04 – Article Writer** <br>
Writes the article in the brand's voice from the brief + DNA. Model routing with fallback: Gemini 3.5 Flash → 3.5 Flash Lite → Flash (latest alias) → Groq Llama 3.3 70B, with retry on 429/503. Post-processing repairs missing structure, a banned-phrase filter catches AI clichés, and a deterministic rubric scores SEO/AEO/GEO (0–100). Output: Markdown + publish-ready HTML with Article and FAQPage JSON-LD.

---

## Automation (GitHub Actions)

Workflow: [`.github/workflows/daily-article.yml`](.github/workflows/daily-article.yml)

```
cron 03:30 UTC (09:00 IST)  or  manual "Run workflow"
  → 01 load committed company_dna.json
  → 02 trend research        (Google News RSS + DDGS + Gemini)
  → 03 article brief         (rule-based)
  → 04 article writer        (Gemini → Groq fallback, scored)
  → 05 email delivery        (Gmail SMTP, HTML body + .md attachment)
  → commit article, brief, trends and run log back to the repo
```

- **No browser in CI.** Engines 02–04 need only `backend/requirements-pipeline.txt`. Engine 01 stays local.
- **Run log.** Every stage records `run_id, stage, status, error, model_used, detail, started_at, finished_at` to the SQLite `runs` table and to `clients/{slug}/runs/run_log.jsonl`, which is committed so history survives the fresh runner. Each run also writes a stage table to the Actions job summary.
- **Failure handling.** A failed stage marks later stages `skipped`, exits non-zero (red run), and the run log is still committed.
- **Demo client.** `clients/sarvam-ai/` is the only client folder tracked in git. To schedule another, run Engine 01 locally and add `!clients/<slug>/` to `.gitignore`.

API calls per run: **2 LLM calls** (1 in Engine 02, 1 in Engine 04) when the primary model answers, ~9 Google News RSS requests, ~8 DuckDuckGo queries, 1 SMTP send.

---

## Tech Stack

**Backend**

| Package | Purpose |
|---|---|
| FastAPI + Uvicorn | REST API server, also serves the built frontend |
| Playwright | Full-render browser scraping (Engine 01 only) |
| httpx | Async HTTP for BFS crawling, RSS, fallbacks |
| spaCy (`en_core_web_sm`) | Noun-chunk keyword extraction (Engine 01 only) |
| DDGS | DuckDuckGo web search, no API key |
| google-genai | Gemini — DNA synthesis, trend classification, article writing |
| Groq | Final LLM fallback |
| aiosqlite | Async SQLite for records and the run log |
| smtplib (stdlib) | Email delivery |

**Frontend:** React 18, Vite 6, Framer Motion

**Storage**

| Layer | What lives here |
|---|---|
| `data/searchos.db` | Clients, DNA, trend reports, briefs, articles + scores, `runs` |
| `clients/{slug}/01_brand_dna/` | `company_dna.json` |
| `clients/{slug}/02_trend_research/` | `trends_{timestamp}.json` |
| `clients/{slug}/03_article_briefs/` | `brief_{timestamp}_{title}.json` |
| `clients/{slug}/04_articles/` | `{date}-{slug}.md` and `.html` |
| `clients/{slug}/runs/` | `run_log.jsonl` |

---

## Installation

Requires Python 3.11+ and Node.js 18+.

```bash
git clone https://github.com/SupratikB23/BrandSCOPE.git
cd BrandSCOPE

pip install -r backend/requirements.txt
playwright install chromium
python -m spacy download en_core_web_sm

cd frontend
npm install
npm run build
cd ..
```

---

## Configuration

```bash
cp backend/.env.example backend/.env
```

| Variable | Required | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` | Yes | Gemini — [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| `GROQ_API_KEY` | Recommended | Fallback LLM — [console.groq.com](https://console.groq.com) |
| `SMTP_USER` / `SMTP_PASS` | For email | Gmail address + [App Password](https://myaccount.google.com/apppasswords) |
| `EMAIL_TO` | No | Recipient(s), defaults to `SMTP_USER` |
| `GEMINI_MODELS` | No | Override the Gemini chain, comma-separated |
| `DISABLE_DDGS` | No | `1` = skip DuckDuckGo, Google News RSS only |

For GitHub Actions, add the same values under **Settings → Secrets and variables → Actions**.

---

## Running the Project

**UI (single process)**

```bash
npm run server        # FastAPI on http://localhost:8000, serves frontend/dist
```

**UI (hot reload)** — `cd backend && python run.py` in one terminal, `cd frontend && npm run dev` in another (http://localhost:5173).

**Headless pipeline (same as CI)**

```bash
python backend/run_pipeline.py --client sarvam-ai            # 02 → 03 → 04 → email
python backend/run_pipeline.py --client sarvam-ai --no-email --type listicle
```

**Run log:** `GET http://localhost:8000/api/runs`

---

## Known Limits

- **Engine 01 blocks its HTTP request** for the whole crawl (minutes). The right design is a job ID + background worker + status polling.
- **SEO/AEO/GEO scores are heuristic.** A deterministic rubric (keyword placement, headings, FAQ, stats, attributions) — not validated against real ranking or citation data.
- **Generated statistics must be fact-checked** before publishing; the model is instructed to cite sources but can invent them.
- **Scheduled runs are best effort.** GitHub may delay cron runs at peak load and disables schedules after 60 days without repository activity.
- **DuckDuckGo rate-limits datacenter IPs.** On CI, Engine 02 may run on Google News RSS alone.
- **Not deployed as a web app.** Playwright needs Chromium, so serverless hosts cannot run Engine 01; it needs a container.

---

## Documentation

Architecture, API reference, database schema and pipeline details: **[DOCS.md](./DOCS.md)**

## Architecture Diagram

<img width="1600" height="1529" alt="brandscope_architecture" src="https://github.com/user-attachments/assets/2fdeafc0-cc24-459d-8f50-eba254ecd105" />
