"""
Brand name → official website.

"Zepto" → https://www.zepto.com
Order: direct URL/domain → DuckDuckGo search → Gemini guess. Every candidate is
verified with a real HTTP request before it is accepted.
"""

import asyncio
import json
import os
import re
from urllib.parse import urlparse

import httpx

try:
    from ddgs import DDGS
    DDGS_AVAILABLE = os.environ.get("DISABLE_DDGS", "").lower() not in ("1", "true", "yes")
except ImportError:
    DDGS_AVAILABLE = False

# Aggregators, social networks, app stores and news sites are never the brand's own site
BLOCKED_DOMAINS = (
    "wikipedia.org", "linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "play.google.com", "apps.apple.com", "crunchbase.com", "glassdoor.",
    "ambitionbox.com", "tracxn.com", "zaubacorp.com", "justdial.com", "indeed.", "naukri.com",
    "medium.com", "quora.com", "reddit.com", "amazon.", "flipkart.com", "bloomberg.com",
    "reuters.com", "forbes.com", "livemint.com", "moneycontrol.com", "inc42.com", "yourstory.com",
    "techcrunch.com", "signalhire.com", "zoominfo.com", "owler.com", "pitchbook.com", "github.com",
    "wellfound.com", "g2.com", "trustpilot.com", "economictimes.", "timesofindia.", "ndtv.com",
)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _token(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def looks_like_url(query: str) -> bool:
    q = query.strip().lower()
    return q.startswith(("http://", "https://")) or (" " not in q and re.search(r"\.[a-z]{2,}(/|$)", q) is not None)


def _origin(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def rank_candidates(urls: list[str], brand: str) -> list[str]:
    """Keep non-blocked hosts that contain the brand token; exact label match ranks first."""
    token = _token(brand)
    scored: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for i, url in enumerate(urls):
        host = _host(url)
        if not host or host in seen or any(b in host for b in BLOCKED_DOMAINS):
            continue
        seen.add(host)
        label = host.split(".")[0].replace("-", "")
        if label == token:
            score = 0
        elif label.startswith(token):
            score = 1
        elif token and token in host.replace("-", "").replace(".", ""):
            score = 2
        else:
            continue
        scored.append((score, i, _origin(url)))
    return [u for _, _, u in sorted(scored)]


async def _search(brand: str) -> list[str]:
    if not DDGS_AVAILABLE:
        return []

    def _run() -> list[str]:
        hrefs: list[str] = []
        for q in (f"{brand} official website", brand):
            try:
                with DDGS() as d:
                    hrefs += [r.get("href", "") for r in d.text(q, max_results=10)]
            except Exception as e:
                print(f"[resolve] DuckDuckGo failed for '{q}': {e}")
        return hrefs

    return await asyncio.to_thread(_run)


async def _gemini_guess(brand: str) -> str:
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        return ""
    from llm import gemini_generate, strip_json_fences
    prompt = (
        f'What is the official homepage URL of the company or brand "{brand}"? '
        'Return ONLY JSON: {"url": "https://..."} or {"url": ""} if you are not sure.'
    )
    try:
        raw, _ = await gemini_generate(prompt, api_key, temperature=0.0)
        return (json.loads(strip_json_fences(raw)).get("url") or "").strip()
    except Exception as e:
        print(f"[resolve] Gemini guess failed: {e}")
        return ""


async def verify(url: str) -> str | None:
    """Return the final origin after redirects if the site answers, else None."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15, headers={"User-Agent": _UA}) as c:
            r = await c.get(url)
    except Exception as e:
        print(f"[resolve] {url} unreachable: {type(e).__name__}")
        return None
    # 401/403/429/503 usually mean bot protection on a real site, not a missing one
    if r.status_code < 400 or r.status_code in (401, 403, 429, 503):
        return _origin(str(r.url))
    return None


async def resolve_brand(query: str) -> dict:
    query = query.strip()
    if not query:
        raise ValueError("Enter a brand name or website")

    if looks_like_url(query):
        url = await verify(_origin(query))
        if not url:
            raise ValueError(f"Could not reach {query}")
        return {"query": query, "url": url, "source": "direct", "candidates": [url]}

    candidates = rank_candidates(await _search(query), query)
    print(f"[resolve] Search candidates for '{query}': {candidates[:5]}")
    for cand in candidates[:3]:
        url = await verify(cand)
        if url:
            return {"query": query, "url": url, "source": "search", "candidates": candidates[:5]}

    guess = await _gemini_guess(query)
    if guess:
        url = await verify(_origin(guess))
        if url:
            return {"query": query, "url": url, "source": "gemini", "candidates": candidates[:5] + [guess]}

    raise ValueError(f"Could not find an official website for '{query}'. Enter the website URL instead.")
