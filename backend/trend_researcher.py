"""
Engine 2 — Live Trend Researcher
Finds what's happening RIGHT NOW in any industry.
Uses only free tools: DuckDuckGo search + Google News RSS + Reddit.
No API keys. No cost. Fresh data every run.
"""

import asyncio
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
    relevance_score: float = 0.0   # How relevant to the company (0–1)
    trend_type: str = "news"        # "news" | "update" | "trend" | "stat"


@dataclass
class TrendReport:
    industry: str
    query_used: str
    generated_at: str
    trends: list[TrendItem] = field(default_factory=list)
    key_themes: list[str] = field(default_factory=list)     # Common threads
    emerging_keywords: list[str] = field(default_factory=list)
    article_angles: list[str] = field(default_factory=list)  # Suggested article ideas


# ── Industry keyword map ──────────────────────────────────────────────────────
# Maps service keywords → richer search terms for that industry

INDUSTRY_SEARCH_TERMS = {
    "interior": [
        "interior design trends 2025",
        "home interior new ideas latest",
        "modular furniture trends India 2025",
        "smart home interior technology",
        "sustainable interior design",
        "biophilic design trend",
        "interior design AI tools 2025",
    ],
    "digital marketing": [
        "digital marketing trends 2025",
        "SEO algorithm update 2025",
        "AI marketing tools latest",
        "social media marketing trends",
        "Google ads update 2025",
        "Meta ads new features 2025",
        "content marketing strategy 2025",
    ],
    "meta ads": [
        "Meta ads update 2025",
        "Facebook ads new features",
        "Instagram ads performance 2025",
        "Meta advantage plus campaigns",
        "Meta AI ad targeting",
    ],
    "ppc": [
        "Google Ads updates 2025",
        "PPC trends 2025",
        "Performance Max campaigns tips",
        "smart bidding Google Ads",
        "PPC cost reduction strategies",
    ],
    "seo": [
        "Google algorithm update 2025",
        "SEO trends 2025",
        "Google AI overview SEO",
        "core web vitals 2025",
        "search generative experience optimization",
        "E-E-A-T SEO guide",
    ],
    "real estate": [
        "real estate market trends 2025",
        "property investment India 2025",
        "smart homes real estate",
        "real estate technology trends",
    ],
    "ecommerce": [
        "ecommerce trends 2025",
        "online shopping behavior 2025",
        "D2C brand strategy",
        "ecommerce AI tools",
    ],
    "saas": [
        "SaaS trends 2025",
        "B2B SaaS growth strategies",
        "product-led growth SaaS",
        "SaaS pricing models 2025",
    ],
    "healthcare": [
        "healthcare technology trends 2025",
        "digital health innovations",
        "telemedicine growth 2025",
        "health tech India 2025",
    ],
}

# Default for unknown industries
DEFAULT_SEARCH_TERMS = [
    "{industry} trends 2025",
    "{industry} latest news",
    "{industry} new developments",
    "{industry} industry update 2025",
    "best practices {industry} 2025",
]


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


async def search_reddit_rss(subreddit: str, client: httpx.AsyncClient) -> list[TrendItem]:
    """Reddit RSS — free, community-driven discussions."""
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=10"
    results = []
    try:
        r = await client.get(
            url,
            headers={"User-Agent": "ContentBot/1.0"},
            timeout=10
        )
        if r.status_code != 200:
            return results

        data = r.json()
        posts = data.get("data", {}).get("children", [])
        for post in posts[:5]:
            d = post.get("data", {})
            if d.get("score", 0) > 50:  # Only popular posts
                results.append(TrendItem(
                    title=d.get("title", ""),
                    summary=d.get("selftext", "")[:200],
                    source=f"r/{subreddit}",
                    url=f"https://reddit.com{d.get('permalink', '')}",
                    trend_type="community",
                ))
    except Exception as e:
        print(f"[trends] Reddit error for r/{subreddit}: {e}")
    return results


# ── Relevance scoring ─────────────────────────────────────────────────────────

def score_relevance(item: TrendItem, company_keywords: list[str]) -> float:
    """Score how relevant a trend is to the company (0.0–1.0)."""
    text = (item.title + " " + item.summary).lower()
    hits = sum(1 for kw in company_keywords if kw.lower() in text)
    return min(hits / max(len(company_keywords) * 0.2, 1), 1.0)


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
        angle = f"The Complete {theme.title()} Guide for 2025"
        if not any(theme.lower() in e for e in existing_lower):
            angles.append(angle)

    # Pattern: "Why X is changing" — forward-looking
    for trend in trends[:3]:
        headline_words = trend.title.split()[:6]
        topic = " ".join(headline_words)
        angles.append(f"Why {topic} Is Changing Everything in 2025")

    # Return top 10 unique angles
    seen = set()
    unique = []
    for a in angles:
        key = a.lower()[:40]
        if key not in seen:
            seen.add(key)
            unique.append(a)

    return unique[:10]


# ── Main orchestrator ─────────────────────────────────────────────────────────

async def research_trends(
    services: list[str],
    top_keywords: list[str],
    existing_titles: list[str],
    max_trends: int = 20,
) -> TrendReport:
    """
    Main entry point. Returns a TrendReport with trends, themes, and article angles.
    """
    industry = detect_industry(services, top_keywords)
    print(f"\n[trends] Detected industry: {industry}")

    # Get search queries for this industry
    search_queries = INDUSTRY_SEARCH_TERMS.get(industry, [])
    if not search_queries:
        search_queries = [t.format(industry=industry) for t in DEFAULT_SEARCH_TERMS]

    all_trends: list[TrendItem] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 ContentResearcher/1.0"},
        follow_redirects=True,
        timeout=20,
    ) as client:

        # ── Google News RSS (most reliable, real-time) ────────────────────────
        for query in search_queries[:4]:
            print(f"[trends] Google News: {query}")
            results = await search_google_news_rss(query, client)
            all_trends.extend(results)
            await asyncio.sleep(0.5)

        # ── DuckDuckGo web search ─────────────────────────────────────────────
        for query in search_queries[:3]:
            print(f"[trends] DuckDuckGo: {query}")
            results = search_duckduckgo(query, max_results=4)
            all_trends.extend(results)

        # ── Reddit discussions ────────────────────────────────────────────────
        reddit_subs = {
            "interior":          ["interiordesign", "HomeImprovement", "malelivingspace"],
            "digital marketing": ["PPC", "SEO", "digital_marketing", "FacebookAds"],
            "seo":               ["SEO", "bigseo", "TechSEO"],
            "meta ads":          ["FacebookAds", "PPC", "advertising"],
            "ecommerce":         ["ecommerce", "Entrepreneur", "shopify"],
            "real estate":       ["realestateinvesting", "india", "RealEstate"],
        }
        subs = reddit_subs.get(industry, ["business", "entrepreneur"])
        for sub in subs[:2]:
            print(f"[trends] Reddit r/{sub}")
            results = await search_reddit_rss(sub, client)
            all_trends.extend(results)

    # ── Deduplicate by title ──────────────────────────────────────────────────
    seen_titles: set[str] = set()
    unique_trends = []
    for t in all_trends:
        key = t.title.lower()[:50]
        if key not in seen_titles and t.title:
            seen_titles.add(key)
            unique_trends.append(t)

    # ── Score relevance ───────────────────────────────────────────────────────
    all_keywords = top_keywords + [s.lower() for s in services]
    for t in unique_trends:
        t.relevance_score = score_relevance(t, all_keywords)

    # Sort: most relevant first
    unique_trends.sort(key=lambda t: t.relevance_score, reverse=True)
    top_trends = unique_trends[:max_trends]

    # ── Build report ──────────────────────────────────────────────────────────
    themes = extract_themes(top_trends)
    angles = generate_article_angles(themes, top_trends, services, existing_titles)

    report = TrendReport(
        industry=industry,
        query_used=", ".join(search_queries[:3]),
        generated_at=datetime.now(timezone.utc).isoformat(),
        trends=top_trends,
        key_themes=themes[:8],
        emerging_keywords=themes[:12],
        article_angles=angles,
    )

    print(f"\n[trends] Found {len(top_trends)} relevant trends")
    print(f"[trends] Key themes: {', '.join(themes[:5])}")
    print(f"[trends] Article angles generated: {len(angles)}")

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
