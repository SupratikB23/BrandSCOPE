"""
main.py — Article Engine Orchestrator
Run this to generate articles for a client.

Setup (one-time):
    pip install -r requirements.txt
    playwright install chromium
    python -m spacy download en_core_web_sm

Get a free Gemini API key at: https://aistudio.google.com/app/apikey
Then either:
    export GOOGLE_API_KEY=your_key_here          # recommended
    python main.py --url https://client.com --articles 3

    # OR pass inline:
    python main.py --url https://client.com --api-key YOUR_KEY --articles 3

Usage:
    # First run: scrape + research + generate 3 articles
    python main.py --url https://clientwebsite.com --articles 3

    # Subsequent runs (reuse saved DNA, fresh trends each time):
    python main.py --dna company_dna.json --articles 5

    # Force a specific article type:
    python main.py --dna company_dna.json --type listicle

    # Test pipeline without API key (placeholder content):
    python main.py --url https://clientwebsite.com --test

    # Use a specific Gemini model:
    python main.py --url https://client.com --model gemini-1.5-flash

    # Multi-client setup:
    python main.py --url https://client-a.com --output clients/client-a --articles 3
    python main.py --dna clients/client-a/company_dna.json --output clients/client-a --articles 3
"""

import asyncio
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# Fix Windows terminal Unicode (cp1252 → utf-8)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from company_scraper import CompanyDNA, extract_company_dna, save_dna, load_dna
from trend_researcher import TrendReport, research_trends
from article_generator import (
    ArticleBrief, GeneratedArticle,
    build_brief, write_article, save_article,
    ARTICLE_TYPES,
)


# Rotate types for variety across a batch
ARTICLE_TYPE_ROTATION = ["educational", "listicle", "guide", "trend-report", "educational"]


async def run_pipeline(
    url: str = None,
    dna_path: str = None,
    num_articles: int = 3,
    article_type: str = None,
    output_dir: str = "output",
    api_key: str = None,
    gemini_model: str = "gemini-2.0-flash",
    test_mode: bool = False,
):
    print("\n" + "═" * 60)
    print("  ARTICLE GENERATION ENGINE  (Gemini free tier)")
    print("═" * 60)

    # ── Step 1: Company DNA ───────────────────────────────────────────────────
    if dna_path and Path(dna_path).exists():
        print(f"\n[1/4] Loading saved company DNA from {dna_path}")
        dna = load_dna(dna_path)
    elif url:
        print(f"\n[1/4] Extracting company DNA from {url}")
        dna = await extract_company_dna(url)
        dna_save_path = Path(output_dir) / "company_dna.json"
        Path(output_dir).mkdir(exist_ok=True)
        save_dna(dna, str(dna_save_path))
        print(f"  DNA saved → {dna_save_path} (reuse with --dna on next run)")
    else:
        raise ValueError("Provide either --url or --dna")

    print(f"  Company:  {dna.name}")
    print(f"  Services: {len(dna.services)} found")
    print(f"  Tone:     {', '.join(dna.tone_adjectives)}")

    # ── Step 2: Live Trend Research ───────────────────────────────────────────
    print(f"\n[2/4] Researching latest industry trends...")
    trend_report: TrendReport = await research_trends(
        services=dna.services,
        top_keywords=dna.top_keywords,
        existing_titles=dna.existing_article_titles,
    )
    print(f"  Trends found:    {len(trend_report.trends)}")
    print(f"  Angles ready:    {len(trend_report.article_angles)}")

    # ── Step 3: Build Article Briefs ──────────────────────────────────────────
    print(f"\n[3/4] Building {num_articles} article brief(s)...")
    top_trends = trend_report.trends[:num_articles * 2]
    angles = trend_report.article_angles[:num_articles * 2]

    briefs = []
    for i in range(num_articles):
        trend = top_trends[i % len(top_trends)] if top_trends else _fallback_trend(dna)
        angle = angles[i] if i < len(angles) else f"{trend.title[:50]} — A Complete 2025 Guide"
        a_type = article_type or ARTICLE_TYPE_ROTATION[i % len(ARTICLE_TYPE_ROTATION)]
        brief = build_brief(dna, trend, angle, article_type=a_type)
        briefs.append((brief, trend))
        print(f"  Brief {i+1}: [{a_type}] {brief.title[:70]}")

    # ── Step 4: Generate Articles ─────────────────────────────────────────────
    effective_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
    if test_mode:
        print(f"\n[4/4] Writing articles... (TEST MODE — placeholder content)")
        effective_key = ""  # force placeholder path
    elif effective_key:
        print(f"\n[4/4] Writing articles with Gemini ({gemini_model})...")
    else:
        print(f"\n[4/4] No API key set — writing placeholder content.")
        print("  Set GOOGLE_API_KEY or use --api-key to generate real articles.")

    generated = []
    for i, (brief, trend) in enumerate(briefs):
        print(f"\n  Article {i+1}/{num_articles}: {brief.title[:65]}")
        article = await write_article(
            brief, dna, trend,
            api_key=effective_key,
            model=gemini_model,
        )
        if article:
            md_path, html_path = save_article(article, dna, output_dir)
            generated.append({
                "title":      article.seo_title,
                "word_count": article.word_count,
                "markdown":   md_path,
                "html":       html_path,
                "keyword":    brief.primary_keyword,
                "quality":    "PASS" if article.quality_passed else "REVIEW",
            })
            status = "PASS" if article.quality_passed else "REVIEW NEEDED"
            print(f"  {status} | {article.word_count} words | keyword: {brief.primary_keyword}")
        else:
            print(f"  FAILED — article {i+1} could not be generated")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print(f"  COMPLETE — {len(generated)}/{num_articles} articles generated")
    print("═" * 60)
    for g in generated:
        quality_icon = "OK" if g["quality"] == "PASS" else "!!"
        print(f"\n  [{quality_icon}] {g['title'][:65]}")
        print(f"       {g['word_count']} words | keyword: {g['keyword']}")
        print(f"       → {g['markdown']}")
        print(f"       → {g['html']}")

    # Save generation log
    log_path = f"{output_dir}/generation_log.json"
    Path(output_dir).mkdir(exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({
            "company":      dna.name,
            "domain":       dna.domain,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model":        gemini_model,
            "articles":     generated,
            "trends_used":  [t.title for t in top_trends[:num_articles]],
        }, f, indent=2)

    print(f"\n  Log → {log_path}")
    print("\nNext: open the .md files, review, light edit if needed, then publish.")
    return generated


def _fallback_trend(dna: CompanyDNA):
    """Generic trend when trend research returns nothing."""
    from trend_researcher import TrendItem
    industry = dna.top_keywords[0] if dna.top_keywords else "industry"
    return TrendItem(
        title=f"The Future of {industry.title()} in 2025",
        summary=f"New approaches are reshaping how {industry} professionals deliver value.",
        source="Industry Analysis",
        url="",
        trend_type="trend",
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AI Article Engine — Gemini free tier + zero paid tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --url https://myinteriors.com --articles 3
  python main.py --dna company_dna.json --articles 5 --type listicle
  python main.py --url https://example.com --test
  python main.py --url https://client.com --model gemini-1.5-flash --articles 3

Gemini models (all free tier):
  gemini-2.0-flash     — default, fastest, 1,500 req/day
  gemini-1.5-flash     — alternative, very similar quality
  gemini-1.5-pro       — highest quality, lower free tier limits
        """,
    )
    parser.add_argument("--url",      help="Brand website URL to scrape")
    parser.add_argument("--dna",      help="Path to saved company_dna.json (skips rescraping)")
    parser.add_argument("--articles", type=int, default=3,
                        help="Number of articles to generate (default: 3)")
    parser.add_argument("--type",     choices=list(ARTICLE_TYPES.keys()),
                        help="Force a specific article type for all articles")
    parser.add_argument("--model",    default="gemini-2.0-flash",
                        help="Gemini model to use (default: gemini-2.0-flash)")
    parser.add_argument("--api-key",  dest="api_key",
                        help="Google AI Studio API key (or set GOOGLE_API_KEY env var)")
    parser.add_argument("--output",   default="output",
                        help="Output directory (default: ./output)")
    parser.add_argument("--test",     action="store_true",
                        help="Test mode — use placeholder content, no API call needed")

    args = parser.parse_args()

    if not args.url and not args.dna:
        parser.print_help()
        print("\nERROR: Provide either --url or --dna\n")
        return

    asyncio.run(run_pipeline(
        url=args.url,
        dna_path=args.dna,
        num_articles=args.articles,
        article_type=args.type,
        output_dir=args.output,
        api_key=args.api_key,
        gemini_model=args.model,
        test_mode=args.test,
    ))


if __name__ == "__main__":
    main()
