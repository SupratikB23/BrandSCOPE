"""
Engine 2 — Live Trend Researcher  (v2)
Finds what's happening RIGHT NOW in any industry AND about the brand itself.

Sources:
  • Google News RSS   — real-time headlines (no key needed)
  • DuckDuckGo DDGS   — broader web context (no key needed)
  • Gemini 2.0 Flash  — segment classification + brand-aware article angles

Segments produced:
  brand_news      — recent launches / announcements by the brand
  brand_future    — roadmap / stated plans / forward-looking signals
  industry_trend  — broad market trends in their space
  competitive     — competitor moves / market positioning
"""

import asyncio
import os
import re
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

import httpx

# ddgs library — pip install ddgs (free, no key)
try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS   # fallback for older installs
        DDGS_AVAILABLE = True
    except ImportError:
        DDGS_AVAILABLE = False
        print("[warn] ddgs not installed. Run: pip install ddgs")


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class TrendItem:
    title: str
    summary: str
    source: str
    url: str
    published: Optional[str] = None
    relevance_score: float = 0.0
    trend_type: str = "news"        # "news" | "trend"
    segment: str = "industry_trend" # "brand_news" | "brand_future" | "industry_trend" | "competitive"


@dataclass
class TrendReport:
    industry: str
    query_used: str
    generated_at: str
    trends: list[TrendItem] = field(default_factory=list)
    key_themes: list[str] = field(default_factory=list)
    emerging_keywords: list[str] = field(default_factory=list)
    article_angles: list[str] = field(default_factory=list)
    brand_summary: str = ""         # 2-sentence summary of brand's current trajectory
    segments: dict = field(default_factory=dict)  # {segment: count}


# ── Industry keyword map ──────────────────────────────────────────────────────
# Maps service keywords → richer search terms for that industry

INDUSTRY_SEARCH_TERMS = {
    "interior": [
        "interior design trends 2026",
        "home interior new ideas latest",
        "modular furniture trends India 2026",
        "smart home interior technology",
        "sustainable interior design",
        "biophilic design trend",
        "interior design AI tools 2026",
    ],
    "digital marketing": [
        "digital marketing trends 2026",
        "SEO algorithm update 2026",
        "AI marketing tools latest",
        "social media marketing trends",
        "Google ads update 2026",
        "Meta ads new features 2026",
        "content marketing strategy 2026",
    ],
    "meta ads": [
        "Meta ads update 2026",
        "Facebook ads new features",
        "Instagram ads performance 2026",
        "Meta advantage plus campaigns",
        "Meta AI ad targeting",
    ],
    "ppc": [
        "Google Ads updates 2026",
        "PPC trends 2026",
        "Performance Max campaigns tips",
        "smart bidding Google Ads",
        "PPC cost reduction strategies",
    ],
    "seo": [
        "Google algorithm update 2026",
        "SEO trends 2026",
        "Google AI overview SEO",
        "core web vitals 2026",
        "search generative experience optimization",
        "E-E-A-T SEO guide",
    ],
    "real estate": [
        "real estate market trends 2026",
        "property investment India 2026",
        "smart homes real estate",
        "real estate technology trends",
    ],
    "ecommerce": [
        "ecommerce trends 2026",
        "online shopping behavior 2026",
        "D2C brand strategy",
        "ecommerce AI tools",
    ],
    "saas": [
        "SaaS trends 2026",
        "B2B SaaS growth strategies",
        "product-led growth SaaS",
        "SaaS pricing models 2026",
    ],
    "healthcare": [
        "healthcare technology trends 2026",
        "digital health innovations",
        "telemedicine growth 2026",
        "health tech India 2026",
    ],
}

# Default for unknown industries (used only if dynamic builder also fails)
DEFAULT_SEARCH_TERMS = [
    "{industry} trends 2026",
    "{industry} latest news",
    "{industry} industry update 2026",
]


def build_dynamic_queries(services: list[str], keywords: list[str]) -> list[str]:
    """
    Build targeted search queries directly from the company's own service
    descriptions and keywords.  Used for any industry not in the preset map —
    handles plumbers, electricians, lawyers, florists, or anything else.
    """
    queries = []

    # Extract the first 3 meaningful words from each service description
    for service in services[:4]:
        # Strip trailing notes after ":" or "–"
        core = re.split(r"[:\-–]", service)[0].strip()
        core = " ".join(core.split()[:4])
        if len(core) > 5:
            queries.append(f"{core} trends 2026")
            queries.append(f"{core} industry news")

    # Use top keywords directly
    for kw in keywords[:3]:
        if len(kw) > 3:
            queries.append(f"{kw} latest news 2026")
            queries.append(f"{kw} market trends")

    # Deduplicate (case-insensitive, first 30 chars as key)
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        key = q.lower()[:30]
        if key not in seen:
            seen.add(key)
            unique.append(q)

    return unique[:6]


# ── Free search tools ─────────────────────────────────────────────────────────

def detect_industry(services: list[str], keywords: list[str]) -> str:
    """Detect which industry bucket the company belongs to."""
    all_text = " ".join(services + keywords).lower()

    industry_signals = {
        "interior":          ["interior", "furnish", "decor", "renovation", "modular",
                              "kitchen", "bedroom", "living", "false ceiling", "wardrobe",
                              "flooring", "lighting", "residential design", "turnkey",
                              "design", "craftsmanship", "workmanship", "spaces"],
        "digital marketing": ["seo", "ppc", "google ads", "social media", "content",
                              "digital marketing", "meta ads", "email marketing"],
        "real estate":       ["real estate", "property", "apartment", "villa", "plot",
                              "realty", "builder", "developer"],
        "ecommerce":         ["ecommerce", "e-commerce", "online store", "shopify",
                              "d2c", "direct to consumer"],
        "saas":              ["saas", "software", "platform", "api", "cloud", "app"],
        "healthcare":        ["health", "medical", "clinic", "hospital", "wellness"],
    }

    scores = {industry: 0 for industry in industry_signals}
    for industry, signals in industry_signals.items():
        for signal in signals:
            if signal in all_text:
                scores[industry] += 1

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general business"


def search_duckduckgo(query: str, max_results: int = 5) -> list[TrendItem]:
    """Search DuckDuckGo — free, no API key."""
    if not DDGS_AVAILABLE:
        return []
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(TrendItem(
                    title=r.get("title", ""),
                    summary=r.get("body", "")[:300],
                    source=r.get("href", "").split("/")[2] if r.get("href") else "web",
                    url=r.get("href", ""),
                    trend_type="news",
                ))
    except Exception as e:
        print(f"[trends] DuckDuckGo error for '{query}': {e}")
    return results


async def search_google_news_rss(query: str, client: httpx.AsyncClient) -> list[TrendItem]:
    """
    Google News RSS — completely free, real-time.
    Returns actual news headlines and summaries.
    """
    encoded = quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"

    results = []
    try:
        r = await client.get(url, timeout=15)
        if r.status_code != 200:
            return results

        root = ET.fromstring(r.text)
        items = root.findall(".//item")

        for item in items[:6]:
            title = item.findtext("title", "").strip()
            description = item.findtext("description", "").strip()
            link = item.findtext("link", "").strip()
            pub_date = item.findtext("pubDate", "").strip()

            # Clean HTML tags from description
            description = re.sub(r"<[^>]+>", " ", description)
            description = re.sub(r"\s+", " ", description).strip()[:300]

            if title:
                results.append(TrendItem(
                    title=title,
                    summary=description,
                    source="Google News",
                    url=link,
                    published=pub_date[:16] if pub_date else None,
                    trend_type="news",
                ))
    except Exception as e:
        print(f"[trends] Google News RSS error for '{query}': {e}")

    return results



# ── Relevance scoring ─────────────────────────────────────────────────────────

def score_relevance(item: TrendItem, company_keywords: list[str]) -> float:
    """
    Multi-factor relevance scoring.

    Factors (each normalised to 0–1 before weighting):
      Title exact match   × 3.0  — keyword appears in the headline
      Full-text match     × 1.0  — keyword appears in title + summary
      Partial word match  × 0.5  — any individual word of a multi-word kw matches
    Max raw score = 4.5  → divided to get 0–1.
    """
    if not company_keywords:
        return 0.5

    title_text = item.title.lower()
    full_text  = (item.title + " " + item.summary).lower()
    total      = len(company_keywords)

    title_hits   = sum(1 for kw in company_keywords if kw.lower() in title_text)
    full_hits    = sum(1 for kw in company_keywords if kw.lower() in full_text)
    partial_hits = sum(
        1 for kw in company_keywords
        if any(part in full_text for part in kw.lower().split() if len(part) > 3)
    )

    raw = (title_hits / total) * 3.0 + (full_hits / total) * 1.0 + (partial_hits / total) * 0.5
    return min(raw / 4.5, 1.0)


def normalize_scores(trends: list[TrendItem]) -> None:
    """
    Redistribute scores across [0.05, 1.0] so the displayed range is always
    progressive — no wall of zeros.  Assumes the list is already sorted by
    relevance_score descending (or will be sorted after this call).

    Strategy: min-max normalization into [0.05, 1.0].
    If all items have the same raw score, spread them evenly by rank.
    """
    if not trends:
        return

    scores = [t.relevance_score for t in trends]
    lo, hi = min(scores), max(scores)

    if hi == lo:
        # All tied — spread evenly by position
        n = len(trends)
        for i, t in enumerate(trends):
            t.relevance_score = round(1.0 - (0.95 * i / max(n - 1, 1)), 2)
        return

    for t in trends:
        normalised = 0.05 + 0.95 * (t.relevance_score - lo) / (hi - lo)
        t.relevance_score = round(normalised, 2)


# ── Theme extraction ──────────────────────────────────────────────────────────

def extract_themes(trends: list[TrendItem]) -> list[str]:
    """Find common themes across all collected trends."""
    from collections import Counter
    all_words = []
    for t in trends:
        words = re.findall(r"\b[a-zA-Z]{4,}\b", t.title + " " + t.summary)
        all_words.extend(w.lower() for w in words)

    stopwords = {"that", "with", "from", "this", "have", "will", "they", "their",
                 "what", "about", "more", "also", "into", "over", "after", "than",
                 "news", "latest", "update", "report", "says", "says", "according"}
    counts = Counter(w for w in all_words if w not in stopwords and len(w) > 4)
    return [w for w, _ in counts.most_common(15)]


def generate_article_angles(
    themes: list[str],
    trends: list[TrendItem],
    company_services: list[str],
    existing_titles: list[str],
) -> list[str]:
    """
    Generate specific article angle ideas that:
    - Connect a trend to a company service
    - Haven't been written before (avoids existing titles)
    - Have a clear unique hook
    """
    angles = []
    existing_lower = [t.lower() for t in existing_titles]

    # Pattern: Trend + Service overlap
    for trend in trends[:5]:
        for service in company_services[:3]:
            # Clean service to a short noun
            service_short = service.split(":")[0].strip()[:40]
            angle = f"{trend.title[:60]} — What It Means for {service_short}"
            if not any(angle.lower()[:30] in e for e in existing_lower):
                angles.append(angle)

    # Pattern: "The X Guide" using top themes
    for theme in themes[:5]:
        angle = f"The Complete {theme.title()} Guide for 2026"
        if not any(theme.lower() in e for e in existing_lower):
            angles.append(angle)

    # Pattern: "Why X is changing" — forward-looking
    for trend in trends[:3]:
        headline_words = trend.title.split()[:6]
        topic = " ".join(headline_words)
        angles.append(f"Why {topic} Is Changing Everything in 2026")

    # Return top 10 unique angles
    seen = set()
    unique = []
    for a in angles:
        key = a.lower()[:40]
        if key not in seen:
            seen.add(key)
            unique.append(a)

    return unique[:10]


# ── Brand-specific searches ────────────────────────────────────────────────────

async def _search_brand_activity(
    brand_name: str,
    domain: str,
    client: httpx.AsyncClient,
) -> list[TrendItem]:
    """
    Search for what the brand has DONE and what it's planning.
    Returns TrendItems pre-tagged with segment brand_news / brand_future.
    """
    if not brand_name:
        return []

    items: list[TrendItem] = []

    # Brand news / recent activity
    news_queries = [
        f'"{brand_name}" launch release announcement 2025 2026',
        f'"{brand_name}" new product update partnership',
    ]
    # Brand future / forward-looking
    future_queries = [
        f'"{brand_name}" roadmap plans future 2026',
        f'"{brand_name}" next launch coming soon upcoming',
    ]

    async def _rss(q: str, seg: str) -> list[TrendItem]:
        encoded = quote_plus(q)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            r = await client.get(url, timeout=15)
            if r.status_code != 200:
                return []
            root = ET.fromstring(r.text)
            out = []
            for item in root.findall(".//item")[:6]:
                title = item.findtext("title", "").strip()
                desc  = re.sub(r"<[^>]+>", " ", item.findtext("description", "")).strip()[:300]
                link  = item.findtext("link", "").strip()
                pub   = item.findtext("pubDate", "").strip()
                if title:
                    out.append(TrendItem(
                        title=title, summary=desc, source="Google News",
                        url=link, published=pub[:16] if pub else None,
                        trend_type="news", segment=seg,
                    ))
            return out
        except Exception:
            return []

    def _ddg(q: str, seg: str) -> list[TrendItem]:
        if not DDGS_AVAILABLE:
            return []
        out = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(q, max_results=5):
                    out.append(TrendItem(
                        title=r.get("title", ""),
                        summary=r.get("body", "")[:300],
                        source=r.get("href", "").split("/")[2] if r.get("href") else "web",
                        url=r.get("href", ""),
                        trend_type="news",
                        segment=seg,
                    ))
        except Exception:
            pass
        return out

    # Fire all searches concurrently
    rss_tasks = (
        [_rss(q, "brand_news") for q in news_queries]
        + [_rss(q, "brand_future") for q in future_queries]
    )
    rss_results = await asyncio.gather(*rss_tasks)
    for batch in rss_results:
        items.extend(batch)

    # DDG is sync — run in thread pool
    def _all_ddg():
        out = []
        for q in news_queries:
            out.extend(_ddg(q, "brand_news"))
        for q in future_queries:
            out.extend(_ddg(q, "brand_future"))
        return out

    try:
        ddg_items = await asyncio.to_thread(_all_ddg)
        items.extend(ddg_items)
    except Exception:
        pass

    # Filter: only keep results that actually mention the brand name
    brand_first_word = brand_name.lower().split()[0] if brand_name else ""
    filtered = [
        t for t in items
        if brand_first_word and brand_first_word in (t.title + " " + t.summary).lower()
    ]
    print(f"[trends] Brand activity search: {len(filtered)} items for '{brand_name}'")
    return filtered


# ── AI classification + angle generation ──────────────────────────────────────

async def _ai_classify_and_angle(
    all_trends: list[TrendItem],
    brand_name: str,
    services: list[str],
    api_key: str,
) -> dict:
    """
    Send ALL collected trends to Gemini.
    Returns: segment classifications per index + brand_summary + article_angles.
    """
    if not api_key or not all_trends:
        return {"classified": [], "brand_summary": "", "angles": []}

    # Build a compact trends list for the prompt (index + title + summary)
    trends_text = "\n".join(
        f"[{i}] ({t.segment}) {t.title} — {t.summary[:120]}"
        for i, t in enumerate(all_trends)
    )

    prompt = f"""You are a content strategist for the brand "{brand_name}".

BRAND SERVICES: {', '.join(services[:8])}

COLLECTED TRENDS (pre-labelled with initial segment guess):
{trends_text[:4000]}

Do the following and return ONLY a single valid JSON object (no markdown):

1. Re-classify each trend into the most accurate segment:
   - "brand_news":      about {brand_name} specifically — recent launches, releases, announcements, partnerships
   - "brand_future":    forward-looking signals about {brand_name}'s plans, roadmap, upcoming features
   - "industry_trend":  broad market/technology trend in their space (NOT brand-specific)
   - "competitive":     about rival brands, alternatives, or market positioning moves in the same space

2. Write a brand_summary: 2 sentences capturing what {brand_name} has been doing recently and what signals suggest they're headed toward.

3. Generate 10-14 article_angles (ready-to-publish titles) that:
   - Connect SPECIFIC brand activity to SPECIFIC industry trends
   - Use the brand's actual positioning (from brand_news/brand_future items)
   - Include at least 3 "brand narrative" angles (explaining what the brand is doing and why it matters)
   - Include at least 2 "competitive context" angles (how the brand stacks up)
   - Are punchy, specific — NOT generic fill-in-the-blank titles

{{
  "classified": [{{"index": 0, "segment": "industry_trend"}}, ...],
  "brand_summary": "string",
  "angles": ["title 1", "title 2", ...]
}}"""

    try:
        from google import genai as _genai
        client = _genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        raw = (resp.text or "").strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.M).rstrip("`").strip()
        data = json.loads(raw)
        print(f"[trends] AI classified {len(data.get('classified', []))} trends, "
              f"{len(data.get('angles', []))} angles")
        return data
    except Exception as e:
        print(f"[trends] AI classify failed: {e}")
        return {"classified": [], "brand_summary": "", "angles": []}


# ── Main orchestrator ─────────────────────────────────────────────────────────

async def research_trends(
    services: list[str],
    top_keywords: list[str],
    existing_titles: list[str],
    brand_name: str = "",
    domain: str = "",
    max_trends: int = 25,
) -> TrendReport:
    """
    Main entry point. Returns a TrendReport with trends segmented and brand-aware angles.

    Sources:
      • Brand-specific searches  — what the brand has done and is planning
      • Google News RSS          — real-time industry headlines
      • DuckDuckGo DDGS          — broader web context
      • Gemini 2.0 Flash         — segment classification + article angle generation
    """
    industry = detect_industry(services, top_keywords)
    print(f"\n[trends] Detected industry: {industry} | Brand: '{brand_name or '—'}'")

    # ── Choose industry search queries ─────────────────────────────────────────
    search_queries = INDUSTRY_SEARCH_TERMS.get(industry)
    if not search_queries:
        print(f"[trends] Industry '{industry}' not in preset map — building queries from company data")
        search_queries = build_dynamic_queries(services, top_keywords)
        if not search_queries:
            search_queries = [t.format(industry=industry) for t in DEFAULT_SEARCH_TERMS]

    all_trends: list[TrendItem] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 ContentResearcher/1.0"},
        follow_redirects=True,
        timeout=20,
    ) as client:

        # ── Brand activity (parallel with industry searches) ──────────────────
        brand_task = asyncio.create_task(
            _search_brand_activity(brand_name, domain, client)
        )

        # ── Google News RSS — real-time industry headlines ────────────────────
        for query in search_queries[:5]:
            print(f"[trends] Google News: {query}")
            results = await search_google_news_rss(query, client)
            for r in results:
                r.segment = "industry_trend"
            all_trends.extend(results)
            await asyncio.sleep(0.3)

        # ── DuckDuckGo — broader industry context ─────────────────────────────
        def _run_ddg():
            out = []
            for query in search_queries[:4]:
                out.extend(search_duckduckgo(query, max_results=5))
            return out
        try:
            ddg_results = await asyncio.to_thread(_run_ddg)
            for r in ddg_results:
                r.segment = "industry_trend"
            all_trends.extend(ddg_results)
        except Exception as e:
            print(f"[trends] DDG industry search error: {e}")

        # Collect brand activity results
        brand_items = await brand_task
        # Brand items go FIRST so they get prioritised in dedup/sort
        all_trends = brand_items + all_trends

        # ── Fallback: if results are thin, supplement with 2025 queries ───────
        THIN_THRESHOLD = 8
        if len(all_trends) < THIN_THRESHOLD:
            print(f"[trends] Only {len(all_trends)} results with 2026 queries — supplementing with 2025…")
            fallback_queries = [q.replace("2026", "2025") for q in search_queries[:3]]
            for query in fallback_queries:
                print(f"[trends] Fallback Google News: {query}")
                results = await search_google_news_rss(query, client)
                for r in results:
                    r.segment = "industry_trend"
                all_trends.extend(results)
            def _fb_ddg():
                out = []
                for q in fallback_queries[:2]:
                    out.extend(search_duckduckgo(q, max_results=4))
                return out
            try:
                fb_ddg = await asyncio.to_thread(_fb_ddg)
                for r in fb_ddg:
                    r.segment = "industry_trend"
                all_trends.extend(fb_ddg)
            except Exception:
                pass
            print(f"[trends] After fallback: {len(all_trends)} total results")

    # ── Deduplicate by normalised title ───────────────────────────────────────
    seen_titles: set[str] = set()
    unique_trends: list[TrendItem] = []
    for t in all_trends:
        key = re.sub(r"\W+", " ", t.title.lower()).strip()[:50]
        if key and key not in seen_titles:
            seen_titles.add(key)
            unique_trends.append(t)

    # ── Score relevance ───────────────────────────────────────────────────────
    all_keywords = top_keywords + [s.lower() for s in services]
    if brand_name:
        all_keywords.append(brand_name.lower())
    for t in unique_trends:
        base = score_relevance(t, all_keywords)
        # Boost brand-specific items so they always surface
        if t.segment in ("brand_news", "brand_future"):
            t.relevance_score = min(base + 0.3, 1.0)
        else:
            t.relevance_score = base

    unique_trends.sort(key=lambda t: t.relevance_score, reverse=True)
    top_trends = unique_trends[:max_trends]
    normalize_scores(top_trends)

    # ── AI: re-classify segments + generate brand-aware article angles ─────────
    api_key = os.getenv("GOOGLE_API_KEY", "")
    ai_result: dict = {}
    if api_key:
        ai_result = await _ai_classify_and_angle(top_trends, brand_name, services, api_key)

        # Apply segment re-classifications from AI
        classification_map = {
            c["index"]: c["segment"]
            for c in ai_result.get("classified", [])
            if isinstance(c.get("index"), int) and c.get("segment")
        }
        for i, t in enumerate(top_trends):
            if i in classification_map:
                t.segment = classification_map[i]

    # ── Fall back to template angles if AI didn't produce them ─────────────────
    ai_angles = ai_result.get("angles", [])
    if ai_angles:
        angles = ai_angles
    else:
        themes_fb = extract_themes(top_trends)
        angles = generate_article_angles(themes_fb, top_trends, services, existing_titles)

    # ── Build segment summary counts ───────────────────────────────────────────
    from collections import Counter
    seg_counts = dict(Counter(t.segment for t in top_trends))

    # ── Build report ──────────────────────────────────────────────────────────
    themes = extract_themes(top_trends)
    brand_summary = ai_result.get("brand_summary", "")

    report = TrendReport(
        industry=industry,
        query_used=", ".join(search_queries[:3]),
        generated_at=datetime.now(timezone.utc).isoformat(),
        trends=top_trends,
        key_themes=themes[:8],
        emerging_keywords=themes[:12],
        article_angles=angles[:14],
        brand_summary=brand_summary,
        segments=seg_counts,
    )

    print(f"\n[trends] {len(top_trends)} trends | segments: {seg_counts}")
    print(f"[trends] Key themes: {', '.join(themes[:5])}")
    print(f"[trends] Article angles: {len(angles)}")
    if brand_summary:
        print(f"[trends] Brand summary: {brand_summary[:100]}...")

    return report


if __name__ == "__main__":
    async def test():
        # Test with interior design example
        services = [
            "Modular kitchen design and installation",
            "Living room interior design",
            "False ceiling and lighting design",
            "Bedroom wardrobes and storage",
            "Full home interior packages",
        ]
        keywords = ["interior", "furnished", "modular", "renovation", "home design"]
        existing = ["5 Interior Design Trends for 2024", "How to Choose the Right Color Palette"]

        report = await research_trends(services, keywords, existing)

        print("\n── Trend Report ─────────────────────────────")
        print(f"Industry:  {report.industry}")
        print(f"Themes:    {', '.join(report.key_themes[:5])}")
        print("\nTop Trends:")
        for t in report.trends[:5]:
            print(f"  [{t.relevance_score:.1f}] {t.title}")
        print("\nArticle Angles:")
        for a in report.article_angles[:5]:
            print(f"  → {a}")

    asyncio.run(test())
