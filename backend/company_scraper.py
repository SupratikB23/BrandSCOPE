"""
Engine 1 — Company DNA Extractor
Scrapes a brand website and builds a deep profile:
tone, services, projects, audience, writing style, keywords used.
This is what makes every generated article sound like IT came from THEM.
"""

import asyncio
import re
import json
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import urljoin, urlparse
from collections import Counter

import httpx
from playwright.async_api import async_playwright

# ── spaCy for NLP (free, local) ──────────────────────────────────────────────
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
    NLP_AVAILABLE = True
except Exception:
    NLP_AVAILABLE = False
    print("[warn] spaCy not available — keyword extraction will use simple method")


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class CompanyDNA:
    """Everything the article writer needs to know about the company."""

    name: str = ""
    domain: str = ""
    tagline: str = ""
    description: str = ""

    # What they do
    services: list[str] = field(default_factory=list)
    industries_served: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)

    # Who they are
    tone_adjectives: list[str] = field(default_factory=list)   # e.g. ["professional", "warm", "technical"]
    tone_sample: str = ""          # A real sentence from their site showing their voice
    avg_sentence_length: int = 15  # Words per sentence in their writing
    uses_first_person: bool = True # "We deliver..." vs "Our team delivers..."

    # Their audience
    target_audience: str = ""      # e.g. "homeowners in Bangalore planning renovation"
    pain_points: list[str] = field(default_factory=list)

    # Their content
    existing_article_titles: list[str] = field(default_factory=list)
    existing_article_topics: list[str] = field(default_factory=list)  # Broader themes
    top_keywords: list[str] = field(default_factory=list)
    brand_keywords: list[str] = field(default_factory=list)  # Words unique to this brand

    # Projects / case studies / portfolio
    portfolio_items: list[dict] = field(default_factory=list)  # {"title": ..., "description": ...}

    # Social proof
    testimonials: list[str] = field(default_factory=list)
    notable_clients: list[str] = field(default_factory=list)

    # USPs (what makes them different)
    usps: list[str] = field(default_factory=list)

    # Raw pages for context
    about_text: str = ""
    homepage_text: str = ""


# ── Page paths to try for each section ───────────────────────────────────────

SECTION_PATHS = {
    "about":      ["/about", "/about-us", "/our-story", "/who-we-are", "/company"],
    "services":   ["/services", "/what-we-do", "/solutions", "/offerings", "/work"],
    "portfolio":  ["/portfolio", "/projects", "/case-studies", "/gallery", "/work", "/our-work"],
    "blog":       ["/blog", "/insights", "/articles", "/news", "/resources", "/stories"],
    "contact":    ["/contact", "/contact-us"],
}

ARTICLE_PATTERNS = re.compile(
    r"/(blog|insights|articles|news|resources|stories|posts|guides)/[^/]+$",
    re.IGNORECASE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Remove excessive whitespace and non-printable characters."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\x20-\x7E\n]", "", text)
    return text.strip()


def extract_keywords_spacy(texts: list[str], top_n: int = 30) -> list[str]:
    """Extract meaningful noun phrases and entities using spaCy."""
    if not NLP_AVAILABLE or not texts:
        return extract_keywords_simple(texts, top_n)

    combined = " ".join(texts[:10])[:50000]
    doc = nlp(combined)

    # Noun chunks — 1-3 words, must not start with an article/determiner
    _det = {"the", "a", "an", "our", "your", "their", "this", "that",
            "its", "my", "we", "all", "each", "every", "more"}
    phrases = [chunk.text.lower().strip() for chunk in doc.noun_chunks
               if 1 <= len(chunk.text.split()) <= 3
               and chunk.text.split()[0].lower() not in _det]
    entities = [ent.text.lower().strip() for ent in doc.ents
                if ent.label_ not in ("DATE", "TIME", "CARDINAL", "ORDINAL")]

    all_terms = phrases + entities
    counts = Counter(all_terms)

    # Extended stopwords: includes common UI/nav words that pollute website scrapes
    stopwords = {
        "the", "a", "an", "this", "that", "our", "your", "we", "they",
        "it", "its", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can", "need",
        "more", "most", "also", "just", "very", "all", "any", "both",
        "each", "few", "other", "some", "such", "than", "too",
        "one", "two", "three", "way", "ways",
        # UI / navigation words found on websites
        "view", "skip", "content", "click", "explore", "read", "learn",
        "find", "know", "back", "next", "prev", "menu", "home", "page",
        "contact", "about", "work", "more", "less", "show", "hide",
        "submit", "send", "close", "open", "link", "button",
    }

    return [term for term, _ in counts.most_common(top_n * 2)
            if term not in stopwords and len(term) > 3
            and not term.startswith(("http", "www"))][:top_n]


def extract_keywords_simple(texts: list[str], top_n: int = 30) -> list[str]:
    """Fallback keyword extraction without spaCy."""
    combined = " ".join(texts).lower()
    words = re.findall(r"\b[a-z]{4,}\b", combined)
    stopwords = {
        "this", "that", "with", "from", "have", "been", "will", "they",
        "their", "what", "when", "where", "which", "your", "about",
        "more", "also", "into", "over", "after", "some", "than", "then",
        "these", "those", "such", "each", "both", "many", "most", "much",
        # UI words
        "view", "skip", "content", "click", "explore", "read", "learn",
        "find", "know", "back", "next", "prev", "menu", "home", "page",
        "contact", "submit", "send", "close", "open", "link",
    }
    counts = Counter(w for w in words if w not in stopwords)
    return [w for w, _ in counts.most_common(top_n)]


def infer_tone(texts: list[str]) -> tuple[list[str], str, int, bool]:
    """
    Analyse writing style.
    Returns: (tone_adjectives, sample_sentence, avg_words_per_sentence, uses_first_person)
    """
    combined = " ".join(texts)
    sentences = re.split(r"[.!?]+", combined)
    sentences = [s.strip() for s in sentences if len(s.split()) > 5]

    if not sentences:
        return ["professional"], "", 15, True

    # Average sentence length
    avg_len = int(sum(len(s.split()) for s in sentences) / max(len(sentences), 1))

    # First person detection
    fp_count = sum(1 for s in sentences if re.search(r"\bwe\b|\bour\b|\bus\b", s, re.I))
    uses_first_person = fp_count > len(sentences) * 0.3

    # Tone adjectives (heuristic)
    tone = []
    if avg_len < 14:
        tone.append("concise")
    elif avg_len > 22:
        tone.append("detailed")

    technical_terms = re.findall(
        r"\b(ROI|strategy|solution|architecture|framework|methodology|"
        r"innovation|expertise|premium|bespoke|crafted|curated|luxury|"
        r"affordable|budget|transform|reimagine|elevate)\b",
        combined, re.I
    )
    if any(t.lower() in ("premium", "bespoke", "luxury", "curated", "crafted")
           for t in technical_terms):
        tone.append("premium")
    if any(t.lower() in ("affordable", "budget") for t in technical_terms):
        tone.append("value-focused")
    if any(t.lower() in ("transform", "reimagine", "elevate", "innovation")
           for t in technical_terms):
        tone.append("aspirational")

    if not tone:
        tone = ["professional", "helpful"]

    # Pick a sample sentence that best shows their voice
    good_samples = [s for s in sentences
                    if 10 < len(s.split()) < 30 and not s.lower().startswith("cookie")]
    sample = good_samples[0] if good_samples else (sentences[0] if sentences else "")

    return tone, sample.strip(), avg_len, uses_first_person


def extract_usps(texts: list[str]) -> list[str]:
    """Look for USP-style sentences: years of experience, awards, guarantees, etc."""
    patterns = [
        r"(\d+\+?\s+years?\s+(?:of\s+)?(?:experience|expertise)[^.!?]*[.!?])",
        r"(over\s+\d+\s+(?:projects?|clients?|homes?|spaces?)[^.!?]*[.!?])",
        r"(trusted\s+by[^.!?]*[.!?])",
        r"(award[^.!?]*[.!?])",
        r"(guarantee[^.!?]*[.!?])",
        r"(only\s+(?:company|firm|studio)[^.!?]*[.!?])",
        r"(certified[^.!?]*[.!?])",
        r"(ISO[^.!?]*[.!?])",
    ]
    usps = []
    combined = " ".join(texts)
    for pattern in patterns:
        matches = re.findall(pattern, combined, re.I)
        usps.extend(m.strip() for m in matches[:2])
    return list(set(usps))[:6]


# ── Core scraping function ────────────────────────────────────────────────────

async def extract_company_dna(base_url: str) -> CompanyDNA:
    """
    Main entry point. Scrapes the brand website and returns a CompanyDNA object.
    """
    base_url = base_url.rstrip("/")
    domain = urlparse(base_url).netloc
    dna = CompanyDNA(domain=domain)

    print(f"\n[DNA] Extracting company profile from: {base_url}")

    page_contents: dict[str, str] = {}  # section_name → text
    article_titles: list[str] = []
    article_texts: list[str] = []
    portfolio_items: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        # Block images/media for speed
        await context.route("**/*", lambda route: route.abort()
            if route.request.resource_type in ("image", "media", "font")
            else route.continue_())

        page = await context.new_page()

        async def scrape_url(url: str, label: str = "") -> str:
            """Scrape a single URL and return its visible text."""
            try:
                await asyncio.sleep(0.8)
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                if not resp or resp.status >= 400:
                    return ""
                # Get all visible text, exclude nav/footer noise
                text = await page.evaluate("""() => {
                    const remove = ['nav', 'footer', 'header', 'script',
                                    'style', 'noscript', '.cookie', '#cookie'];
                    remove.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => el.remove());
                    });
                    return document.body ? document.body.innerText : '';
                }""")
                return clean_text(text)
            except Exception as e:
                print(f"[DNA] Could not scrape {url}: {e}")
                return ""

        # ── Homepage ──────────────────────────────────────────────────────────
        print("[DNA] Scraping homepage...")
        homepage_text = await scrape_url(base_url, "homepage")
        dna.homepage_text = homepage_text[:3000]
        page_contents["homepage"] = homepage_text

        # Try to extract company name from title
        try:
            title = await page.title()
            dna.name = title.split("|")[0].split("–")[0].split("-")[0].strip()
        except Exception:
            dna.name = domain.replace("www.", "").split(".")[0].title()

        # ── Section pages ─────────────────────────────────────────────────────
        for section, paths in SECTION_PATHS.items():
            for path in paths:
                url = urljoin(base_url, path)
                print(f"[DNA] Trying {section}: {url}")
                text = await scrape_url(url, section)
                if len(text) > 200:
                    page_contents[section] = text
                    print(f"[DNA]   OK Got {len(text)} chars for {section}")
                    break

        # ── Blog articles (grab top 5 for style analysis) ─────────────────────
        blog_text = page_contents.get("blog", "")
        if blog_text:
            # Extract article links from blog page
            links = await page.eval_on_selector_all(
                "a[href]", "els => els.map(e => ({href: e.href, text: e.innerText}))"
            )
            article_links = [
                l for l in links
                if ARTICLE_PATTERNS.search(l["href"])
                and urlparse(l["href"]).netloc == domain
                and len(l["text"].strip()) > 15
            ][:8]

            for link in article_links[:5]:
                print(f"[DNA] Reading article: {link['text'][:60]}")
                article_titles.append(link["text"].strip())
                text = await scrape_url(link["href"], "article")
                if text:
                    article_texts.append(text[:2000])

        # ── Portfolio / projects ──────────────────────────────────────────────
        portfolio_text = page_contents.get("portfolio", "")
        if portfolio_text:
            # Extract project mentions (simple heuristic)
            lines = [l.strip() for l in portfolio_text.split("\n")
                     if 10 < len(l.strip()) < 150]
            for i, line in enumerate(lines[:20]):
                if any(w in line.lower() for w in
                       ["project", "home", "office", "apartment", "villa",
                        "bedroom", "kitchen", "living", "commercial", "sqft",
                        "designed", "delivered", "completed", "client"]):
                    desc = lines[i+1] if i+1 < len(lines) else ""
                    portfolio_items.append({"title": line, "description": desc})

        await browser.close()

    # ── Build the DNA profile ─────────────────────────────────────────────────
    all_texts = [v for v in page_contents.values() if v]

    # Tone analysis
    dna.tone_adjectives, dna.tone_sample, dna.avg_sentence_length, dna.uses_first_person = \
        infer_tone(all_texts)

    # Keywords
    dna.top_keywords = extract_keywords_spacy(all_texts, top_n=40)

    # Services — try services page first, then parse sentences from homepage + about
    services_raw = page_contents.get(
        "services",
        page_contents.get("homepage", "") + " " + page_contents.get("about", "")
    )

    # Split by both newlines AND sentences so single-block sites still work
    service_candidates = []
    for chunk in re.split(r"[\n.!]", services_raw):
        chunk = chunk.strip()
        if 8 < len(chunk) < 120:
            service_candidates.append(chunk)

    service_keywords = [
        "design", "install", "deliver", "service", "solution", "interior",
        "furnish", "renovate", "build", "construct", "consult", "manage",
        "develop", "create", "provide", "modular", "kitchen", "bedroom",
        "living", "wardrobe", "ceiling", "flooring", "lighting", "residential",
        "commercial", "hospitality", "turnkey", "execution", "workmanship",
        "craftsmanship", "approach", "innovation", "creativity", "excellence",
        "spaces", "aesthet", "functional", "luxury", "bespoke",
    ]
    ui_noise = ["view more", "click", "skip", "instagram", "facebook",
                "youtube", "linkedin", "whatsapp", "pinterest", "explore"]
    dna.services = [
        c for c in service_candidates
        if any(w in c.lower() for w in service_keywords)
        and not any(u in c.lower() for u in ui_noise)
    ][:10]

    # USPs
    dna.usps = extract_usps(all_texts)

    # About
    dna.about_text = page_contents.get("about", "")[:2000]

    # Tagline (first meaningful line of homepage)
    lines = [l for l in dna.homepage_text.split("\n") if 10 < len(l) < 100]
    dna.tagline = lines[0] if lines else ""

    # Articles
    dna.existing_article_titles = article_titles
    dna.portfolio_items = portfolio_items[:10]

    # Infer audience from about + services text
    audience_clues = []
    combined = " ".join(all_texts[:3])
    if re.search(r"homeowner|home owner|residential|families", combined, re.I):
        audience_clues.append("homeowners")
    if re.search(r"corporate|office|commercial|business", combined, re.I):
        audience_clues.append("businesses")
    if re.search(r"startup|co-working|coworking", combined, re.I):
        audience_clues.append("startups")
    if re.search(r"luxury|premium|high-end|bespoke", combined, re.I):
        audience_clues.append("premium segment buyers")
    dna.target_audience = ", ".join(audience_clues) if audience_clues else "professionals and homeowners"

    # Pain points (what their clients worry about)
    pain_patterns = [
        r"(without[^.!?]{10,60}[.!?])",
        r"(no more[^.!?]{5,50}[.!?])",
        r"(never worry[^.!?]{5,50}[.!?])",
        r"(stress[^.!?]{5,50}[.!?])",
        r"(hassle[^.!?]{5,50}[.!?])",
        r"(time[^.!?]{5,50}overwhelm[^.!?]{5,30}[.!?])",
    ]
    for pattern in pain_patterns:
        matches = re.findall(pattern, combined, re.I)
        dna.pain_points.extend(m.strip() for m in matches[:1])

    if not dna.pain_points:
        dna.pain_points = [
            "Managing vendors and timelines is overwhelming",
            "Uncertainty about costs spiraling beyond budget",
            "Getting quality finishes without constant supervision"
        ]

    print(f"\n[DNA] Profile built for: {dna.name}")
    print(f"  Services found:  {len(dna.services)}")
    print(f"  Articles found:  {len(dna.existing_article_titles)}")
    print(f"  Portfolio items: {len(dna.portfolio_items)}")
    print(f"  Top keywords:    {', '.join(dna.top_keywords[:8])}")
    print(f"  Tone:            {', '.join(dna.tone_adjectives)}")

    return dna


def save_dna(dna: CompanyDNA, path: str = "company_dna.json"):
    with open(path, "w") as f:
        json.dump(asdict(dna), f, indent=2)
    print(f"[DNA] Saved to {path}")


def load_dna(path: str = "company_dna.json") -> CompanyDNA:
    with open(path) as f:
        data = json.load(f)
    return CompanyDNA(**data)


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"

    async def main():
        dna = await extract_company_dna(url)
        save_dna(dna)
        print("\n── Company DNA ──────────────────────────────")
        print(f"Name:     {dna.name}")
        print(f"Tagline:  {dna.tagline}")
        print(f"Audience: {dna.target_audience}")
        print(f"Tone:     {', '.join(dna.tone_adjectives)}")
        print(f"Services: {', '.join(dna.services[:5])}")
        print(f"USPs:     {chr(10).join(dna.usps[:3])}")

    asyncio.run(main())
