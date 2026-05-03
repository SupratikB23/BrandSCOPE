<img width="2911" height="1262" alt="BrandSCOPE_generated" src="https://github.com/user-attachments/assets/c07f718f-ab80-42eb-a382-a5276a6c8eac" />


# BrandSCOPE – Brand Search Content Optimization & Publishing Engine

**A 4-engine content intelligence platform that extracts a brand's DNA, tracks live industry trends, builds SEO/AEO/GEO-scored article briefs, and writes articles that sound exactly like the brand.**

Runs entirely on localhost. No subscriptions. Powered by Gemini (free tier) and Groq (free tier).

---

## Table of Contents

- [Overview](#overview)
- [The Four Engines](#the-four-engines)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Project](#running-the-project)

---

## Overview

SearchOS is a self-hosted brand content platform built around a sequential 4-engine pipeline. Each engine feeds the next one, producing articles that are simultaneously optimized for:

- **SEO** - Traditional search engine ranking signals
- **AEO** - Answer Engine Optimization for featured snippets and AI Overviews
- **GEO** - Generative Engine Optimization for citation by ChatGPT, Perplexity, and Claude

The system manages multiple clients. Each client's full pipeline output - DNA, trends, briefs, and articles - is stored locally in a structured directory layout and a SQLite database.

---

## The Four Engines

### Engine 01 - Brand DNA Extractor

Builds a complete intelligence profile of a brand from its website and the open web.

**Scraping pipeline:**

1. Sitemap XML parse - fast, no browser, most reliable source of URLs
2. BFS URL discovery via `httpx` - discovers up to 60 pages at depth 3 without a browser
3. JSON-LD structured data mining - extracts services, articles, locations from `<script type="application/ld+json">` blocks
4. Playwright full-render scraping with:
   - `networkidle` wait + `domcontentloaded` fallback + body text polling (8 s)
   - Accordion / `<details>` / Bootstrap collapse expansion
   - Tab panel clicking (up to 5 tabs)
   - Load More button clicking (up to 3 times)
   - Shadow DOM text piercing via `document.createTreeWalker`
   - Same-domain iframe content extraction
   - Raw HTML `httpx` fallback when JS yields fewer than 200 characters
5. Web search via DuckDuckGo DDGS - searches for brand services, differentiators, and published articles across the open web
6. Gemini AI synthesis - classifies all scraped and searched content into structured outputs

**Output fields:**

| Field | Description |
|---|---|
| `services` | Clean noun phrases (2-7 words each) - e.g. "Speech Recognition API", "Indic Language Models (Sarvam-1)" |
| `tone_adjectives` | AI-classified voice descriptors - e.g. "technical", "mission-driven", "confident" |
| `tone_sample` | Representative sentence extracted from actual page text |
| `uses_first_person` | Boolean derived from AI perspective classification |
| `usps` | Specific, factual differentiators with numbers and firsts where available |
| `existing_article_titles` | Merged from 4 sources: scraped links, JSON-LD, case-study metrics, internet search |
| `top_keywords` | AI brand keywords prepended to NLP-extracted noun chunks (up to 50) |
| `locations` | Cities and regions from JSON-LD + text pattern matching |

---

### Engine 02 - Live Trend Research

Pulls real-time signals from the open web and classifies them into four segments relative to the brand.

**Sources:**
- Google News RSS - zero cost, real-time headlines
- DuckDuckGo DDGS - broader web context, no API key required
- Brand-specific searches - what the brand has done recently and what it is planning

**Segments:**

| Segment | Description |
|---|---|
| `brand_news` | Recent launches, releases, and announcements by the brand |
| `brand_future` | Forward-looking signals - roadmap, upcoming features, stated plans |
| `industry_trend` | Broad market and technology trends in the brand's space |
| `competitive` | Competitor moves and market positioning signals |

**AI layer:** Gemini re-classifies every collected item into the correct segment, writes a 2-sentence brand trajectory summary, and generates 10-14 brand-specific article angles - not fill-in templates, but ready-to-write titles connecting brand activity to industry movement.

**Fallback:** All queries target 2026. If fewer than 8 results are returned, the engine automatically supplements with the same queries targeting 2025.

---

### Engine 03 - Article Brief Builder

Runs gap analysis between the brand's existing article coverage and the incoming trend signal. Produces a structured brief with SEO, AEO, and GEO scores assigned to each proposed angle before a word is written.

**Brief structure:**
- Working title and primary angle
- Target keyword cluster
- Recommended article type (educational / listicle / case study / opinion)
- SEO score, AEO score, GEO score (0-100 each)
- Suggested outline and talking points
- Brand voice guidance derived from Engine 01

---

### Engine 04 - Article Writer

Takes the brief and the full brand DNA and writes a complete article in the brand's voice.

**Model routing:**
- Primary: Gemini 2.0 Flash (`gemini-2.0-flash`)
- Fallback: Groq (when Gemini is rate-limited or unavailable)

**Quality controls:**
- Banned phrase filter - rejects output containing AI cliches ("in today's fast-paced", "delve into", "it goes without saying", etc.)
- SEO / AEO / GEO score computed on the final article
- All scores persisted to the database alongside the article

---

## Tech Stack

**Backend**

| Package | Purpose |
|---|---|
| FastAPI + Uvicorn | REST API server |
| Playwright | Full-render browser scraping |
| httpx | Async HTTP client for BFS crawling and fallback fetches |
| spaCy (`en_core_web_sm`) | NLP noun chunk extraction for keyword analysis |
| DDGS | DuckDuckGo web search - no API key |
| google-genai | Gemini 2.0 Flash - services, tone, USPs, classification, article writing |
| Groq | LLM fallback for article generation |
| aiosqlite | Async SQLite for metadata persistence |
| python-dotenv | Environment variable loading |

**Frontend**

| Package | Purpose |
|---|---|
| React 18 | UI framework |
| Vite 6 | Dev server and production bundler |
| Framer Motion | Animated landing page and transitions |

**Storage**

| Layer | What lives here |
|---|---|
| `data/searchos.db` | Client metadata, brief records, article metadata, SEO/AEO/GEO scores |
| `clients/{slug}/01_brand_dna/` | `company_dna.json` |
| `clients/{slug}/02_trend_research/` | `trends_{timestamp}.json` |
| `clients/{slug}/03_article_briefs/` | `brief_{timestamp}_{title}.json` |
| `clients/{slug}/04_articles/` | `{slug}.md` (final article in Markdown) |

---

## Prerequisites

- **Python** 3.11 or higher
- **Node.js** 18 or higher
- **Chromium** - installed automatically by Playwright on first run

**API keys required (both free):**

| Service | Free tier | Link |
|---|---|---|
| Google AI Studio (Gemini) | 1,500 requests/day on `gemini-2.0-flash` | aistudio.google.com/app/apikey |
| Groq | 14,400 requests/day | console.groq.com |

No other paid services, subscriptions, or cloud infrastructure required.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/search-optimization.git
cd "Search Optimization"
```

### 2. Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Install Playwright browsers

```bash
playwright install chromium
```

### 4. Download the spaCy language model

```bash
python -m spacy download en_core_web_sm
```

### 5. Install frontend dependencies

```bash
cd ../frontend
npm install
```

### 6. Build the frontend

```bash
npm run build
```

The built assets in `frontend/dist/` are served directly by the FastAPI server, so you do not need to run a separate dev server in production.

---

## Configuration

Copy the example environment file and fill in your keys:

```bash
cp backend/.env.example backend/.env
```

```env
# backend/.env

GOOGLE_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here
```

Both keys are used only on your local machine and are never sent anywhere except the respective APIs.

---

## Running the Project

### Production mode (single command)

```bash
# From the project root
npm run server
```

This starts the FastAPI server on `http://localhost:8000`. The frontend is served from `frontend/dist/` at the same origin - no separate frontend process needed.

### Development mode (hot reload)

Open two terminals:

```bash
# Terminal 1 - Backend
cd backend
python run.py

# Terminal 2 - Frontend (hot reload)
cd frontend
npm run dev
```

The Vite dev server runs on `http://localhost:5173` and proxies API calls to `http://localhost:8000`.

---

