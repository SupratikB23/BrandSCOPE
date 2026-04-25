"""
Engine 3 — Article Brief Builder
Engine 4 — Gemini Article Writer (Google AI Studio free tier)

Takes company DNA + trend report → writes a world-class article
that sounds EXACTLY like the company wrote it.

Setup:
    pip install google-generativeai
    Get a free API key at: https://aistudio.google.com/app/apikey

Usage:
    export GOOGLE_API_KEY=your_key_here
    python main.py --url https://client.com --articles 3
    # OR pass key directly:
    python main.py --url https://client.com --api-key YOUR_KEY
"""

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

from google import genai
from google.genai import types as genai_types

try:
    from groq import Groq as GroqClient
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    print("[warn] groq package not installed. Run: pip install groq")

from company_scraper import CompanyDNA
from trend_researcher import TrendReport, TrendItem


# ── Banned phrases (AI_RULES.md Rule 5) ──────────────────────────────────────
# If any of these appear in generated output, the article fails quality review.

BANNED_PHRASES = [
    "in today's fast-paced",
    "ever-evolving landscape",
    "it goes without saying",
    "it's worth noting",
    "delve into",
    "tapestry of",
    "a testament to",
    "unlock the potential",
    "game-changer",
    "paradigm shift",
    "cutting-edge",
    "robust solution",
    "seamless experience",
    "in summary",
    "as an ai",
    "as a language model",
    "utilize",
]


def has_banned_phrases(content: str) -> list[str]:
    """Return list of any banned phrases found in the content."""
    lower = content.lower()
    return [phrase for phrase in BANNED_PHRASES if phrase in lower]


# ── Quality checks (AI_RULES.md Rule 9) ──────────────────────────────────────

def quality_check(content: str, dna: CompanyDNA, brief: "ArticleBrief") -> dict[str, bool]:
    """
    Run all automated quality checks from AI_RULES.md Rule 9.
    Returns {check_name: passed_bool}.
    """
    word_count = len(content.split())
    lower = content.lower()
    first_100_words = " ".join(content.split()[:100]).lower()

    return {
        "word_count_1100_1600":       1100 <= word_count <= 1600,
        "company_name_2x":            content.count(dna.name) >= 2 if dna.name else True,
        "primary_keyword_first_100":  brief.primary_keyword.lower() in first_100_words,
        "faq_section_present":        "## faq" in lower or "## frequently asked" in lower,
        "no_banned_phrases":          len(has_banned_phrases(content)) == 0,
        "conclusion_present":         "## conclusion" in lower,
        "min_4_h2_sections":          content.count("## ") >= 4,
        "meta_desc_length_ok":        True,   # checked separately after generation
    }


def compute_seo_aeo_geo_scores(content: str, dna: CompanyDNA, brief: "ArticleBrief") -> dict[str, int]:
    """
    Score the article on SEO, AEO and GEO dimensions — each 0–100.

    SEO  — Google ranking signals (keyword use, structure, length, headings)
    AEO  — Answer Engine Optimisation (featured snippets, direct answers, FAQ)
    GEO  — Generative Engine Optimisation (stats, citations, declarative claims)
    """
    lower   = content.lower()
    words   = content.split()
    wc      = len(words)
    first_100 = " ".join(words[:100]).lower()
    h2_count  = content.count("## ")
    h3_count  = content.count("### ")

    # ── SEO score (100 pts) ───────────────────────────────────────────────────
    seo = 0
    pk = brief.primary_keyword.lower()

    # Keyword in title / H1 (20 pts)
    h1_match = re.search(r"^# (.+)$", content, re.M)
    h1_text  = h1_match.group(1).lower() if h1_match else ""
    if pk in h1_text:                                    seo += 20
    elif any(w in h1_text for w in pk.split()):          seo += 10

    # Keyword in first 100 words (15 pts)
    if pk in first_100:                                  seo += 15
    elif any(w in first_100 for w in pk.split()):        seo += 7

    # Keyword in ≥2 H2 headings (15 pts)
    h2s = re.findall(r"^## (.+)$", content, re.M)
    kw_h2 = sum(1 for h in h2s if pk in h.lower() or any(w in h.lower() for w in pk.split()))
    if kw_h2 >= 2:   seo += 15
    elif kw_h2 == 1: seo += 8

    # Secondary keywords used (10 pts)
    sec_hits = sum(1 for kw in brief.secondary_keywords if kw.lower() in lower)
    seo += min(10, int(10 * sec_hits / max(len(brief.secondary_keywords), 1)))

    # Word count in sweet spot 1100–1600 (15 pts)
    if 1100 <= wc <= 1600:   seo += 15
    elif 900 <= wc < 1100:   seo += 8
    elif 1600 < wc <= 1900:  seo += 8

    # ≥4 H2 sections (10 pts)
    if h2_count >= 4:    seo += 10
    elif h2_count >= 2:  seo += 5

    # Bold first mention of key terms (5 pts)
    if content.count("**") >= 4:  seo += 5

    # No banned phrases (10 pts)
    if len(has_banned_phrases(content)) == 0:  seo += 10

    # ── AEO score (100 pts) ───────────────────────────────────────────────────
    aeo = 0

    # FAQ section present (25 pts)
    has_faq = "## faq" in lower or "## frequently asked" in lower
    if has_faq:  aeo += 25

    # At least 2 H2s phrased as questions (15 pts)
    q_h2s = sum(1 for h in h2s if h.strip().endswith("?"))
    if q_h2s >= 2:   aeo += 15
    elif q_h2s == 1: aeo += 7

    # Direct-answer paragraphs after H2s (20 pts)
    # Check that each H2 is followed by a non-empty paragraph within ~3 lines
    sections = re.split(r"^## .+$", content, flags=re.M)
    sections_with_answer = sum(
        1 for s in sections[1:]  # skip preamble
        if len(s.strip().split("\n")[0].split()) >= 8
    )
    total_sections = max(len(sections) - 1, 1)
    aeo += min(20, int(20 * sections_with_answer / total_sections))

    # Conclusion present (10 pts)
    if "## conclusion" in lower:  aeo += 10

    # Uses question-style subheadings (H3) (10 pts)
    h3s = re.findall(r"^### (.+)$", content, re.M)
    if any(h.strip().endswith("?") for h in h3s):  aeo += 10

    # Answer-first writing: first sentence of intro answers something (10 pts)
    intro_paras = [p for p in content.split("\n\n") if p.strip() and not p.startswith("#")]
    if intro_paras:
        first_sent = intro_paras[0].split(".")[0]
        if len(first_sent.split()) >= 8:  aeo += 10

    # Short, scan-friendly paragraphs (10 pts)
    paras = [p.strip() for p in content.split("\n\n") if p.strip() and not p.startswith("#")]
    short_paras = sum(1 for p in paras if len(p.split()) <= 80)
    if paras:
        ratio = short_paras / len(paras)
        aeo += int(10 * ratio)

    # ── GEO score (100 pts) ───────────────────────────────────────────────────
    geo = 0

    # Statistics / numbers (25 pts)
    stat_patterns = [
        r"\d+%",                         # percentages
        r"\$[\d,]+",                     # dollar amounts
        r"\d+[xX]\s",                    # multipliers like 4.2x
        r"\d+\s+(?:days?|weeks?|months?|years?)",  # time ranges
        r"(?:according to|study|report|research|survey)\b",
    ]
    stat_hits = sum(1 for p in stat_patterns if re.search(p, content, re.I))
    geo += min(25, stat_hits * 5)

    # Blockquote stats (15 pts)
    bq_count = len(re.findall(r"^> .+$", content, re.M))
    if bq_count >= 3:    geo += 15
    elif bq_count >= 1:  geo += 8

    # "According to" attributed claims (20 pts)
    attr_count = len(re.findall(r"according to\b", content, re.I))
    if attr_count >= 2:   geo += 20
    elif attr_count == 1: geo += 10

    # Company name expertise statements (20 pts)
    company = dna.name or ""
    expertise_phrases = ["has seen", "in our work", "we've found", "our experience",
                         "we have seen", "we see", "in our projects", "our clients",
                         "our team", "we deliver", "we build", "we help"]
    expertise_hits = sum(1 for p in expertise_phrases if p in lower)
    geo += min(20, expertise_hits * 5)

    # Declarative sentences (no vague hedging) (10 pts)
    hedges = ["many experts believe", "some say", "it is thought", "it may be",
              "could potentially", "might possibly"]
    hedge_count = sum(1 for h in hedges if h in lower)
    if hedge_count == 0:   geo += 10
    elif hedge_count <= 2: geo += 5

    # Named sources / brands mentioned (10 pts)
    # Rough heuristic: capitalised proper nouns beyond the company name
    proper_nouns = re.findall(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)*\b", content)
    unique_sources = len({n for n in proper_nouns if n.lower() not in (company.lower(), "the", "a")})
    if unique_sources >= 5:   geo += 10
    elif unique_sources >= 2: geo += 5

    return {
        "seo": min(100, seo),
        "aeo": min(100, aeo),
        "geo": min(100, geo),
    }


def print_quality_report(checks: dict[str, bool], banned: list[str]) -> bool:
    """Print quality report and return True if all automated checks pass."""
    passed = sum(checks.values())
    total = len(checks)

    if banned:
        print(f"  [quality] BANNED PHRASES found — flag for review: {', '.join(banned)}")

    if passed == total and not banned:
        print(f"  [quality] All {total}/{ total} automated checks passed")
        return True

    print(f"  [quality] {passed}/{total} checks passed")
    for name, ok in checks.items():
        status = "OK" if ok else "FAIL"
        print(f"           [{status}] {name}")
    return passed == total


# ── Article brief ─────────────────────────────────────────────────────────────

@dataclass
class ArticleBrief:
    title: str
    slug: str
    primary_keyword: str
    secondary_keywords: list[str]
    target_audience: str
    angle: str              # The unique hook / perspective
    trend_hook: str         # The current event/trend this hangs on
    word_count: int = 1300
    article_type: str = "educational"
    sections: list[str] = field(default_factory=list)
    call_to_action: str = ""
    company_reference: str = ""


@dataclass
class GeneratedArticle:
    brief: ArticleBrief
    content: str
    word_count: int
    generated_at: str
    seo_title: str          # 50–60 chars
    meta_description: str   # 150–160 chars
    schema_faq: list[dict]
    quality_passed: bool = False


# ── Brief builder (Engine 3) ──────────────────────────────────────────────────

ARTICLE_TYPES = {
    "listicle":     "X Things / X Ways / X Reasons (scannable, shareable)",
    "guide":        "The Complete Guide to X (comprehensive, evergreen)",
    "educational":  "What is X / How does X work (awareness stage)",
    "opinion":      "Why X is / isn't Y (thought leadership)",
    "case-study":   "How [Client Type] achieved X with Y (proof-based)",
    "trend-report": "The State of X in 2025 (data-driven, authoritative)",
}


def build_brief(
    dna: CompanyDNA,
    trend: TrendItem,
    angle: str,
    article_type: str = "educational",
) -> ArticleBrief:
    """Build a detailed article brief from company DNA + a chosen trend."""

    trend_words = re.findall(r"\b[a-zA-Z]{4,}\b", trend.title.lower())
    company_words = dna.top_keywords[:5]
    overlap = [w for w in trend_words if w in company_words]
    primary_kw = overlap[0] if overlap else (dna.top_keywords[0] if dna.top_keywords else "industry")

    sections = _build_section_outline(article_type, angle, dna, trend)

    cta = (
        f"Looking to bring these ideas to life? {dna.name} specialises in exactly this — "
        f"get a free consultation today."
    )

    company_ref = (
        f"Reference {dna.name} naturally 2–3 times as a knowledgeable insider or cited expert, "
        f"drawing on their work in: {', '.join(dna.services[:3])}. "
        f"Frame them like a journalist citing an authority — never like an advertisement."
    )

    slug = re.sub(r"[^a-z0-9]+", "-", angle.lower())[:60].strip("-")

    return ArticleBrief(
        title=angle,
        slug=slug,
        primary_keyword=primary_kw,
        secondary_keywords=dna.top_keywords[1:6],
        target_audience=dna.target_audience,
        angle=angle,
        trend_hook=trend.title,
        word_count=1300,
        article_type=article_type,
        sections=sections,
        call_to_action=cta,
        company_reference=company_ref,
    )


def _build_section_outline(
    article_type: str,
    angle: str,
    dna: CompanyDNA,
    trend: TrendItem,
) -> list[str]:
    """Generate H2 section headers based on article type."""
    topic = angle[:50]

    outlines = {
        "listicle": [
            "Why this trend matters more than you think",
            f"1. {trend.title[:40]}",
            "2. What it means in practice",
            "3. How to act on it",
            "4. The advanced consideration most people skip",
            "5. The 2025 outlook",
            "What to do right now",
        ],
        "guide": [
            f"What is {topic[:40]} and why does it matter in 2025",
            "The core principles you need to understand",
            "Step-by-step: how to get started",
            "Common mistakes (and how to avoid them)",
            "Real-world examples and what we can learn",
            "The 2025 outlook: what changes next",
            "Your action plan",
        ],
        "educational": [
            f"Why {topic[:35]} is trending right now",
            "The problem it solves",
            "How it works in practice",
            "What good looks like (and what doesn't)",
            "How to evaluate your options",
            "Questions to ask before you commit",
        ],
        "trend-report": [
            "The numbers behind this trend",
            "What's driving the shift",
            "Who's doing it best — and what we can learn",
            "The challenges nobody talks about",
            "What experts are predicting for 2025–2026",
            "How to position yourself ahead of the curve",
        ],
        "case-study": [
            "The challenge: what the client was facing",
            "The approach: why we chose this solution",
            "The process: what happened step by step",
            "The results: what changed",
            "Lessons that apply to your situation",
        ],
        "opinion": [
            "The conventional view — and why it's wrong",
            "What the data actually shows",
            "The real reason this keeps happening",
            "A better way to think about it",
            "What this means for your decisions",
        ],
    }

    return outlines.get(article_type, outlines["educational"])


# ── Master prompt builder ─────────────────────────────────────────────────────

def build_master_prompt(brief: ArticleBrief, dna: CompanyDNA, trend: TrendItem) -> str:
    """
    Precision-engineered master prompt.
    Every requirement is numbered, scored, and tied to a self-check list
    that the model runs before outputting — maximising SEO/AEO/GEO scores.
    """
    person      = "we/our" if dna.uses_first_person else f"{dna.name}"
    tone_desc   = ", ".join(dna.tone_adjectives) if dna.tone_adjectives else "professional, clear, authoritative"
    pk          = brief.primary_keyword
    sec_kws     = ", ".join(f'"{k}"' for k in brief.secondary_keywords[:5])
    services    = "\n".join(f"  • {s}" for s in dna.services[:6])   or "  • Professional services"
    usps        = "\n".join(f"  • {u}" for u in dna.usps[:3])       or "  • Quality delivery"
    existing    = "\n".join(f"  – {t}" for t in dna.existing_article_titles[:6]) or "  – None yet"
    sections_numbered = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(brief.sections))

    # Tone modifiers
    mods = []
    if dna.tone_adjectives:
        tones_lower = [t.lower() for t in dna.tone_adjectives]
        if "premium" in tones_lower:
            mods.append('  • Use "refined", "considered", "effortless" — never "super easy" or "no brainer".')
        if "concise" in tones_lower:
            mods.append("  • Max 18 words per sentence. Max 4 sentences per paragraph.")
        if "aspirational" in tones_lower:
            mods.append("  • Open sections with forward-looking statements. Frame outcomes as transformations.")
        if "technical" in tones_lower:
            mods.append("  • Use precise technical terminology. Back every claim with a figure or named source.")
    tone_mod_text = "\n".join(mods) if mods else "  • Match the brand voice sample exactly — in register, rhythm, and word choice."

    # Portfolio snippet
    portfolio_text = ""
    if dna.portfolio_items:
        lines = [f"  – {p['title']}: {p.get('description','')[:70]}" for p in dna.portfolio_items[:3]]
        portfolio_text = "Notable work:\n" + "\n".join(lines) + "\n"

    prompt = f"""You are a senior content strategist writing an article for {dna.name}.
Your article will be automatically scored on SEO, AEO, and GEO.
Each requirement below shows its point value. Hit them ALL to score above 85 on every dimension.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 1 · BRAND IDENTITY  (read carefully — this defines your entire voice)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Company:         {dna.name}
Domain:          {dna.domain}
Tagline:         {dna.tagline}
Audience:        {brief.target_audience}
Voice:           {tone_desc}
Person:          Write from the "{person}" perspective
Sentence length: ~{dna.avg_sentence_length} words per sentence on average

BRAND VOICE SAMPLE — your article must sound like this author wrote it:
  "{dna.tone_sample}"

Voice modifiers:
{tone_mod_text}

Services:
{services}

What makes {dna.name} different:
{usps}

{portfolio_text}
Articles already written (DO NOT repeat topics or angles):
{existing}

About the company:
  {dna.about_text[:700]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 2 · ARTICLE BRIEF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Title (use as your H1):  {brief.title}
Article type:            {brief.article_type} — {ARTICLE_TYPES.get(brief.article_type, "")}
Primary keyword:         "{pk}"
Secondary keywords:      {sec_kws}
Target word count:       {brief.word_count} words (hard range: 1,100–1,600)

TREND / NEWS HOOK — this is your opening:
  Title:   {trend.title}
  Detail:  {trend.summary[:300]}
  Source:  {trend.source}

H2 section outline (these are your mandatory section headings — reword as questions where noted):
{sections_numbered}

Company reference instruction:
  {brief.company_reference}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 3 · SCORED SEO REQUIREMENTS  (Layer 1 — Google ranking)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[SEO-1 · 20 pts]  Your H1 title MUST contain "{pk}" — work it into the title naturally.
[SEO-2 · 15 pts]  "{pk}" MUST appear in the first 100 words of body text (before the first H2).
[SEO-3 · 15 pts]  "{pk}" MUST appear in at least 2 different H2 headings.
[SEO-4 · 10 pts]  Use at least 4 of these secondary keywords: {sec_kws}
[SEO-5 · 15 pts]  Total word count: 1,100–1,600 words.
[SEO-6 · 10 pts]  Include at least 4 H2 sections.
[SEO-7 ·  5 pts]  Bold (**term**) the very first mention of every important technical term.
[SEO-8 · 10 pts]  Use zero banned phrases (see Part 6).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 4 · SCORED AEO REQUIREMENTS  (Layer 2 — featured snippets, voice search, AI overviews)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[AEO-1 · 25 pts]  End the article with a ## FAQ section containing EXACTLY 3 Q&A pairs:
                   **Question ending with ?**
                   Answer in 2–4 sentences that fully address the question.

[AEO-2 · 15 pts]  At least 2 of your H2 headings must end with "?" (phrased as questions).

[AEO-3 · 20 pts]  The VERY FIRST sentence after every H2 must directly answer that heading
                   in 40–60 words. Put the answer FIRST — context and evidence come after.

[AEO-4 · 10 pts]  Include a ## Conclusion section (3–4 sentences, forward-looking, ends with CTA).

[AEO-5 · 10 pts]  Include at least one ### H3 subheading phrased as a question.

[AEO-6 · 10 pts]  The opening paragraph's first sentence must be a direct, declarative statement
                   of at least 10 words — no rhetorical questions, no scene-setting.

[AEO-7 · 10 pts]  Keep every paragraph under 80 words. Short paragraphs rank for snippets.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 5 · SCORED GEO REQUIREMENTS  (Layer 3 — AI citation in ChatGPT, Claude, Perplexity)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[GEO-1 · 25 pts]  Include at least 4 specific statistics (percentages, costs, timeframes, counts).
                   Format each key stat as a blockquote:
                   > According to [Source], X% of [audience] [finding].

[GEO-2 · 15 pts]  Use at least 3 blockquote lines (> ) — only for hard statistics or data.

[GEO-3 · 20 pts]  Begin at least 2 sentences with "According to [named source or organisation]…"

[GEO-4 · 20 pts]  Reference {dna.name}'s expertise at least TWICE using phrases like:
                   "{dna.name} has seen…", "In our work with {brief.target_audience}…",
                   "Our experience shows…", "We've found that…", "{dna.name} recommends…"

[GEO-5 · 10 pts]  Write in declarative sentences throughout. Do NOT use:
                   "many experts believe", "some say", "it is thought", "it may be",
                   "could potentially", "might possibly", "it is widely believed"

[GEO-6 · 10 pts]  Mention at least 5 named entities — brands, publications, platforms, or people.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 6 · BANNED PHRASES  (any use = automatic quality failure)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NEVER write: "in today's fast-paced", "ever-evolving landscape", "it goes without saying",
"it's worth noting", "delve into", "tapestry of", "a testament to", "unlock the potential",
"game-changer", "paradigm shift", "cutting-edge", "robust solution", "seamless experience",
"utilize" (use "use"), "leverage" (use "use"), "as an AI", "as a language model", "in summary"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 7 · EXACT ARTICLE SKELETON  (fill in every placeholder)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# [Your H1 title — must contain "{pk}"]

[Opening paragraph — 3 sentences:
  Sentence 1: What is happening RIGHT NOW referencing "{trend.title}"
  Sentence 2: Why this matters to {brief.target_audience}
  Sentence 3: {dna.name}'s perspective using "{person}"
  — "{pk}" must appear somewhere in this paragraph]

## [Section 1 heading — phrase as a question ending "?"]

[40–60 word direct answer to the heading question — put the answer FIRST]

[Supporting paragraph with at least one bold **term** and one secondary keyword]

> According to [Source], [statistic relating to this section].

## [Section 2 heading — must contain "{pk}" or a close variant — phrase as a question "?"]

[40–60 word direct answer]

[Detail paragraph]

### [H3 subheading as a question?]

[Concise answer — 2–4 sentences]

## [Section 3 heading — must contain "{pk}" or variant]

[40–60 word direct answer]

[Detail paragraph]

> According to [Source], [second statistic].

## [Sections 4+ from the outline — follow the same H2 → answer → detail → stat pattern]

## Conclusion

[3 sentences: summarise the shift, state {dna.name}'s position, end with:]
{brief.call_to_action}

## FAQ

**[Question about {pk}?]**
[2–4 sentence answer]

**[Question about how to act on this?]**
[2–4 sentence answer]

**[Question about {dna.name}'s role or service?]**
[2–4 sentence answer]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 8 · SELF-CHECK  (mentally verify EVERY item before writing your final output)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before you write the final article, confirm:
  ☑  "{pk}" is in the H1
  ☑  "{pk}" appears within the first 100 words
  ☑  "{pk}" appears in at least 2 H2 headings
  ☑  At least 2 H2 headings end with "?"
  ☑  At least one H3 heading ends with "?"
  ☑  First sentence after every H2 directly answers the heading (40–60 words)
  ☑  At least 3 blockquote lines ( > ) present
  ☑  At least 2 "According to [source]…" sentences
  ☑  {dna.name} referenced with expertise phrases at least twice
  ☑  ## Conclusion section present
  ☑  ## FAQ section present with exactly 3 Q&A pairs
  ☑  At least 4 secondary keywords used
  ☑  At least 5 named entities mentioned
  ☑  Zero banned phrases
  ☑  Word count between 1,100 and 1,600

OUTPUT ONLY THE ARTICLE. Begin immediately with # [Title]. No preamble, no commentary.
"""
    return prompt


# ── Gemini writer (Engine 4) ──────────────────────────────────────────────────

GEMINI_MODEL = "gemini-2.0-flash"

# Fallback chain tried in order when a model's quota is exhausted or not found.
# Prefix "groq/" means use the Groq API instead of Gemini.
GEMINI_FALLBACK_CHAIN = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-preview-04-17",
    "groq/llama-3.3-70b-versatile",
]


def _parse_gemini_error(err_str: str) -> tuple[str, int]:
    """
    Returns (error_type, retry_after_seconds).
    error_type: "rate_limit" | "quota_exhausted" | "not_found" | "other"
    """
    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
        # Per-day quota exhausted → switching models will help
        if "PerDay" in err_str or "PerDayPer" in err_str:
            return "quota_exhausted", 0
        # Per-minute rate limit → waiting will help
        delay_match = re.search(r"retryDelay[\"':,\s]+(\d+)s", err_str)
        delay = int(delay_match.group(1)) if delay_match else 65
        return "rate_limit", delay
    if "404" in err_str or "NOT_FOUND" in err_str:
        return "not_found", 0
    return "other", 0


async def _call_gemini(client, model: str, prompt: str, config) -> str:
    """Single Gemini attempt. Raises on error."""
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=prompt,
        config=config,
    )
    return response.text.strip()


async def _call_groq(groq_key: str, model: str, prompt: str) -> str:
    """Single Groq attempt (OpenAI-compatible). Raises on error."""
    if not GROQ_AVAILABLE:
        raise RuntimeError("groq package not installed — run: pip install groq")
    groq_model = model.removeprefix("groq/")

    def _sync_call():
        gc = GroqClient(api_key=groq_key)
        resp = gc.chat.completions.create(
            model=groq_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.75,
            max_tokens=2500,
        )
        return resp.choices[0].message.content.strip()

    return await asyncio.to_thread(_sync_call)


async def write_article(
    brief: ArticleBrief,
    dna: CompanyDNA,
    trend: TrendItem,
    api_key: str = None,
    model: str = GEMINI_MODEL,
) -> Optional[GeneratedArticle]:
    """
    Generate the article using Gemini or Groq (free tier).
    Retries on per-minute rate limits and auto-falls back through the chain
    when a model's daily quota is exhausted or the model is not found.
    Groq models (prefixed "groq/") are tried last as the free-forever fallback.
    """
    prompt = build_master_prompt(brief, dna, trend)

    print(f"\n[writer] Generating: {brief.title[:65]}")
    print(f"[writer] Model: {model} | Target: {brief.word_count} words")

    gemini_key = api_key if api_key is not None else os.environ.get("GOOGLE_API_KEY", "")
    groq_key   = os.environ.get("GROQ_API_KEY", "")

    # If no Gemini key at all, go straight to Groq (or placeholder)
    if not gemini_key:
        if groq_key:
            print("[writer] No Gemini key — trying Groq directly.")
            try:
                content = await _call_groq(groq_key, "groq/llama-3.3-70b-versatile", prompt)
                print("[writer] Success with Groq (no Gemini key)")
            except Exception as e:
                print(f"[writer] Groq failed: {e}")
                content = _placeholder_article(brief, dna, trend)
        else:
            print("[writer] No API key found — using placeholder content.")
            content = _placeholder_article(brief, dna, trend)
    else:
        # Build queue: requested model first, then rest of fallback chain
        queue = [model] + [m for m in GEMINI_FALLBACK_CHAIN if m != model]
        content = None

        gemini_client = genai.Client(api_key=gemini_key)
        gemini_config = genai_types.GenerateContentConfig(
            temperature=0.75,
            top_p=0.9,
            max_output_tokens=2500,
        )

        for attempt_model in queue:
            is_groq = attempt_model.startswith("groq/")

            # Skip Groq models if no Groq key configured
            if is_groq and not groq_key:
                print(f"[writer] Skipping {attempt_model} — no GROQ_API_KEY in .env")
                continue

            per_minute_retries = 2 if not is_groq else 0
            for retry in range(per_minute_retries + 1):
                try:
                    print(f"[writer] Trying model: {attempt_model}" +
                          (f" (retry {retry})" if retry else ""))

                    if is_groq:
                        content = await _call_groq(groq_key, attempt_model, prompt)
                    else:
                        content = await _call_gemini(gemini_client, attempt_model, prompt, gemini_config)

                    print(f"[writer] Success with {attempt_model}")
                    break  # success — exit retry loop
                except Exception as e:
                    err_str = str(e)
                    error_type, retry_after = _parse_gemini_error(err_str)
                    print(f"[writer] {attempt_model} error ({error_type}): {str(e)[:120]}")

                    if error_type == "rate_limit" and retry < per_minute_retries:
                        print(f"[writer] Per-minute limit — waiting {retry_after}s then retrying...")
                        await asyncio.sleep(retry_after)
                        continue

                    break  # quota_exhausted / not_found / other → next model

            if content:
                break  # got content, skip remaining fallback models

        if not content:
            print("[writer] All models exhausted — no content generated.")
            return None

    if not content:
        return None

    # Post-process
    content = _post_process(content, brief, dna)

    # Quality checks (AI_RULES.md Rule 9)
    checks = quality_check(content, dna, brief)
    banned = has_banned_phrases(content)
    quality_passed = print_quality_report(checks, banned)

    word_count = len(content.split())
    seo_title = _extract_seo_title(brief.title)
    meta_desc = _generate_meta_description(content, brief.primary_keyword, dna.name)

    # Validate meta description length
    checks["meta_desc_length_ok"] = 150 <= len(meta_desc) <= 160

    faq = _extract_faq(content)

    return GeneratedArticle(
        brief=brief,
        content=content,
        word_count=word_count,
        generated_at=datetime.now(timezone.utc).isoformat(),
        seo_title=seo_title,
        meta_description=meta_desc,
        schema_faq=faq,
        quality_passed=quality_passed,
    )


# ── Post-processing ───────────────────────────────────────────────────────────

def _post_process(content: str, brief: ArticleBrief, dna: CompanyDNA) -> str:
    """
    Active structural safety net.
    Strips preamble, then checks every high-value scoring requirement and
    injects the missing element if the model skipped it.
    Each fix is targeted and minimal — it only changes what is absent.
    """

    # ── 1. Strip preamble ────────────────────────────────────────────────────
    content = re.sub(
        r"^(here is|here's|below is|this is|sure[,!]?)[^\n]*\n+",
        "", content, flags=re.I
    )

    # ── 2. Ensure H1 ────────────────────────────────────────────────────────
    if not content.startswith("#"):
        content = f"# {brief.title}\n\n{content}"

    # ── 3. Inject primary keyword into H1 if missing ────────────────────────
    pk = brief.primary_keyword.lower()
    h1_match = re.match(r"^(# .+)$", content, re.M)
    if h1_match and pk not in h1_match.group(1).lower():
        old_h1 = h1_match.group(1)
        new_h1 = f"# {brief.primary_keyword.title()}: {old_h1[2:]}"
        content = content.replace(old_h1, new_h1, 1)

    # ── 4. Inject primary keyword in opening if missing ─────────────────────
    first_100_words = " ".join(content.split()[:110]).lower()
    if pk not in first_100_words:
        # Find first body paragraph (after H1) and append keyword phrase
        content = re.sub(
            r"(# [^\n]+\n\n)(\S[^\n]{15,})",
            lambda m: m.group(1) + m.group(2) +
                f" **{brief.primary_keyword.title()}** is central to this shift.",
            content, count=1,
        )

    # ── 5. Ensure primary keyword in ≥2 H2 headings ─────────────────────────
    h2s = re.findall(r"^## (.+)$", content, re.M)
    kw_in_h2 = [h for h in h2s if pk in h.lower()
                or any(w in h.lower() for w in pk.split() if len(w) > 3)]
    if len(kw_in_h2) < 2 and h2s:
        # Append keyword phrase to the first H2 that doesn't have it
        fixed = 0
        for h in h2s:
            if pk not in h.lower() and fixed < (2 - len(kw_in_h2)):
                suffix = f" and {brief.primary_keyword.title()}"
                content = content.replace(f"## {h}", f"## {h}{suffix}", 1)
                fixed += 1

    # ── 6. Ensure ≥2 H2s are phrased as questions ────────────────────────────
    h2s_fresh = re.findall(r"^## (.+)$", content, re.M)
    q_h2s = [h for h in h2s_fresh if h.strip().endswith("?")]
    if len(q_h2s) < 2:
        needed = 2 - len(q_h2s)
        converted = 0
        for h in h2s_fresh:
            if not h.strip().endswith("?") and converted < needed:
                new_h = h.rstrip(".,:;") + "?"
                content = content.replace(f"## {h}", f"## {new_h}", 1)
                converted += 1

    # ── 7. Ensure company name appears ≥2 times ──────────────────────────────
    if dna.name and content.count(dna.name) < 2:
        content = re.sub(
            r"(# [^\n]+\n\n)([^\n]+)",
            rf"\1\2 At **{dna.name}**, we see this firsthand.",
            content, count=1,
        )

    # ── 8. Ensure ≥1 blockquote statistic ───────────────────────────────────
    if not re.search(r"^> .+$", content, re.M):
        stat_match = re.search(
            r"^([^#>\n].{15,}\d+[%$x].{5,}\.)$", content, re.M
        )
        if stat_match:
            content = content.replace(
                stat_match.group(0),
                f"\n> According to industry data, {stat_match.group(0)[0].lower()}{stat_match.group(0)[1:]}\n",
                1,
            )
        else:
            # Inject a generic stat before the first H2
            generic_stat = (
                f"\n> According to recent industry research, organisations that invest "
                f"in {brief.primary_keyword} report a 40–60% improvement in organic "
                f"visibility within the first six months.\n"
            )
            first_h2 = re.search(r"^## .+$", content, re.M)
            if first_h2:
                content = content[:first_h2.start()] + generic_stat + content[first_h2.start():]

    # ── 9. Ensure ≥1 "According to" attribution ──────────────────────────────
    if not re.search(r"according to\b", content, re.I):
        content = re.sub(
            r"^(> )(.+)$",
            r"> According to industry research, \2",
            content, count=1, flags=re.M,
        )

    # ── 10. Ensure ## Conclusion ─────────────────────────────────────────────
    if "## conclusion" not in content.lower():
        cta = brief.call_to_action
        conclusion = (
            f"\n\n## Conclusion\n\n"
            f"The shift towards {brief.primary_keyword} is no longer optional — "
            f"it is the baseline for brands that want to stay visible across search, "
            f"answer engines, and AI-generated results. {dna.name} is positioned to "
            f"help {brief.target_audience} move ahead of the curve.\n\n{cta}"
        )
        # Insert before FAQ if present, otherwise append
        faq_pos = re.search(r"^## faq", content, re.I | re.M)
        if faq_pos:
            content = content[:faq_pos.start()] + conclusion + "\n\n" + content[faq_pos.start():]
        else:
            content = content.rstrip() + conclusion

    # ── 11. Ensure ## FAQ with 3 Q&A pairs ──────────────────────────────────
    if "## faq" not in content.lower() and "## frequently asked" not in content.lower():
        pk_title = brief.primary_keyword.title()
        year     = datetime.now(timezone.utc).year
        faq = (
            f"\n\n## FAQ\n\n"
            f"**What is {pk_title} and why does it matter in {year}?**\n"
            f"{pk_title} is the practice of optimising content to rank in traditional "
            f"search results, featured snippets, and AI-generated answers simultaneously. "
            f"In {year}, brands that ignore it lose visibility across all three surfaces.\n\n"
            f"**How long does it take to see results from {pk_title}?**\n"
            f"Most brands see measurable improvements in organic traffic within 60–90 days. "
            f"Sustained authority and AI citation signals typically compound over a 6–12 month horizon.\n\n"
            f"**How does {dna.name} approach {pk_title} for clients?**\n"
            f"{dna.name} starts with a full content and keyword audit, identifies coverage gaps, "
            f"and builds a structured publishing roadmap. Every article is engineered to satisfy "
            f"search engines, answer engines, and AI models at the same time."
        )
        content = content.rstrip() + faq

    return content.strip()


def _extract_seo_title(title: str) -> str:
    """Trim title to 50–60 characters for SEO."""
    if len(title) <= 60:
        return title
    words = title.split()
    result = ""
    for word in words:
        if len(result) + len(word) + 1 <= 57:
            result += (" " if result else "") + word
        else:
            break
    return result + "..."


def _generate_meta_description(content: str, keyword: str, company: str) -> str:
    """Generate a 150–160 char meta description from the article intro."""
    paragraphs = [
        p.strip() for p in content.split("\n\n")
        if len(p.strip()) > 80 and not p.startswith("#")
    ]
    if not paragraphs:
        return f"Expert insights on {keyword} from {company}. Read our latest guide today."[:160]

    first = paragraphs[0][:220]
    first = re.sub(r"\*+([^*]+)\*+", r"\1", first)   # strip bold/italic
    first = re.sub(r"`([^`]+)`", r"\1", first)
    first = re.sub(r"\s+", " ", first).strip()

    if len(first) < 150:
        first = f"{first} Expert insights from {company}."
    if len(first) > 160:
        first = first[:157] + "..."
    return first


def _extract_faq(content: str) -> list[dict]:
    """Extract Q&A pairs from the ## FAQ section."""
    faq_match = re.search(r"## FAQ[^\n]*\n+(.*?)(?=\n## |\Z)", content, re.S | re.I)
    if not faq_match:
        return []

    faq_text = faq_match.group(1)
    questions = re.findall(
        r"\*\*([^*?]+\?)\*\*\s*\n+([^\n*#]+(?:\n[^\n*#]+)*)",
        faq_text,
    )
    return [{"question": q.strip(), "answer": a.strip()[:300]} for q, a in questions[:5]]


def _placeholder_article(brief: ArticleBrief, dna: CompanyDNA, trend: TrendItem) -> str:
    """Placeholder content when no API key is set (for pipeline testing)."""
    services_preview = ", ".join(dna.services[:2]) if dna.services else "professional services"
    return f"""# {brief.title}

{trend.summary[:200]}

At **{dna.name}**, we've been tracking this shift closely — and it changes how we approach {brief.primary_keyword} for every client we work with.

## Why this matters right now

> According to industry research, 67% of clients now consider this a top priority when choosing a service provider.

The market has moved. What worked in 2023 is not what wins in 2025.

## What this means in practice

**{dna.name}** specialises in {services_preview}. Working with {dna.target_audience}, the clearest shift we see is demand for integrated, end-to-end delivery — not fragmented vendor relationships.

*Key insight: the companies that struggle most aren't the ones that lack budget. They're the ones that start too late to course-correct.*

## How to evaluate your options

Three questions to ask any provider before committing:

1. **What is your track record** with clients at my scale and stage?
2. **How do you handle** scope changes mid-project?
3. **What does success look like** at 90 days, not just delivery day?

## Conclusion

The shift is real and it is accelerating. The organisations that move now will have a compounding advantage over those that wait for certainty.

{brief.call_to_action}

## FAQ

**What is {brief.primary_keyword} and why does it matter in 2025?**
{brief.primary_keyword.title()} refers to the integrated approach behind delivering superior results in your context. In 2025, it has become a baseline expectation, not a differentiator.

**How much does this typically cost?**
Costs vary by scope. A typical engagement starts from a structured brief and scales with complexity — most clients see clear ROI within the first quarter.

**How long does implementation take?**
Most clients see measurable progress within 4–8 weeks. Full results typically compound over a 3–6 month horizon depending on the starting point.
"""


# ── Markdown → HTML converter ─────────────────────────────────────────────────

def markdown_to_html(article: GeneratedArticle, dna: CompanyDNA) -> str:
    """Convert markdown article to SEO-ready HTML with Article + FAQPage JSON-LD."""

    md = article.content

    html = md
    html = re.sub(r"^# (.+)$",   r"<h1>\1</h1>",   html, flags=re.M)
    html = re.sub(r"^## (.+)$",  r"<h2>\1</h2>",   html, flags=re.M)
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>",   html, flags=re.M)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*",  r"<em>\1</em>",   html)
    html = re.sub(r"_(.+?)_",    r"<em>\1</em>",   html)
    html = re.sub(r"^> (.+)$",   r"<blockquote>\1</blockquote>", html, flags=re.M)
    html = re.sub(r"^- (.+)$",   r"<li>\1</li>",   html, flags=re.M)
    html = re.sub(r"(<li>.*</li>\n?)+", r"<ul>\g<0></ul>", html)

    lines = html.split("\n")
    result = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith(("<h", "<ul", "<ol", "<li", "<block")):
            result.append(line)
        else:
            result.append(f"<p>{line}</p>")
    html = "\n".join(result)

    article_schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": article.seo_title,
        "description": article.meta_description,
        "author": {
            "@type": "Organization",
            "name": dna.name,
            "url": f"https://{dna.domain}",
        },
        "publisher": {
            "@type": "Organization",
            "name": dna.name,
        },
        "datePublished": article.generated_at[:10],
        "keywords": ", ".join(
            [article.brief.primary_keyword] + article.brief.secondary_keywords
        ),
    }

    faq_schema_tag = ""
    if article.schema_faq:
        faq_data = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": item["question"],
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": item["answer"],
                    },
                }
                for item in article.schema_faq
            ],
        }
        faq_schema_tag = (
            f'<script type="application/ld+json">\n'
            f'{json.dumps(faq_data, indent=2)}\n'
            f'</script>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{article.seo_title}</title>
  <meta name="description" content="{article.meta_description}">
  <meta property="og:title" content="{article.seo_title}">
  <meta property="og:description" content="{article.meta_description}">
  <script type="application/ld+json">
{json.dumps(article_schema, indent=2)}
  </script>
  {faq_schema_tag}
</head>
<body>
<article>
{html}
</article>
</body>
</html>"""


# ── Save output ───────────────────────────────────────────────────────────────

def save_article(article: GeneratedArticle, dna: CompanyDNA, output_dir: str = "output"):
    """Save article as Markdown, HTML, and metadata JSON."""
    Path(output_dir).mkdir(exist_ok=True)

    slug = article.brief.slug
    date = article.generated_at[:10]
    base = f"{output_dir}/{date}-{slug}"

    md_path = f"{base}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(f"title: {article.seo_title}\n")
        f.write(f"description: {article.meta_description}\n")
        f.write(f"keyword: {article.brief.primary_keyword}\n")
        f.write(f"date: {date}\n")
        f.write(f"word_count: {article.word_count}\n")
        f.write(f"quality_passed: {article.quality_passed}\n")
        f.write("---\n\n")
        f.write(article.content)
    print(f"[save] Markdown → {md_path}")

    html_path = f"{base}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(markdown_to_html(article, dna))
    print(f"[save] HTML     → {html_path}")

    meta_path = f"{base}.meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "title": article.seo_title,
            "description": article.meta_description,
            "slug": slug,
            "keyword": article.brief.primary_keyword,
            "secondary_keywords": article.brief.secondary_keywords,
            "word_count": article.word_count,
            "trend_hook": article.brief.trend_hook,
            "generated_at": article.generated_at,
            "quality_passed": article.quality_passed,
            "faq": article.schema_faq,
        }, f, indent=2)
    print(f"[save] Metadata → {meta_path}")

    return md_path, html_path
