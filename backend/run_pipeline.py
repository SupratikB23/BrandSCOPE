"""
Headless pipeline — Engine 02 → 03 → 04 → email delivery, no UI, no HTTP.
Runs daily on GitHub Actions (.github/workflows/daily-article.yml) or locally.

Engine 01 (Playwright crawl) is deliberately NOT run here. It runs locally once,
and its output clients/{slug}/01_brand_dna/company_dna.json is committed, so the
scheduled job needs no browser, no Chromium and no spaCy.

Every stage is written to the run log in two places:
  • SQLite `runs` table            (local UI: GET /api/runs)
  • clients/{slug}/runs/run_log.jsonl  (committed by CI — survives the fresh runner)

Usage (from repo root):
    python backend/run_pipeline.py --client sarvam-ai
    python backend/run_pipeline.py --client sarvam-ai --no-email --type listicle

Exit code: 0 when every stage succeeded or was skipped, 1 when any stage failed.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import traceback
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from company_scraper import CompanyDNA
from trend_researcher import TrendReport, TrendItem, research_trends
import trend_researcher
from article_generator import (
    ARTICLE_TYPES, build_brief, write_article,
    compute_seo_aeo_geo_scores, markdown_to_html,
)
import database as db
from delivery import mask_email, send_article_email, smtp_configured


ARTICLE_TYPE_ROTATION = ["educational", "listicle", "guide", "trend-report", "opinion"]
SEGMENT_PRIORITY = {"brand_news": 0, "brand_future": 1, "industry_trend": 2, "competitive": 3}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower())[:60].strip("-")


def _seconds(start: str, end: str) -> float:
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


# ── Run log ───────────────────────────────────────────────────────────────────

class RunLog:
    def __init__(self, slug: str, client_id: int):
        self.slug = slug
        self.client_id = client_id
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
        self.trigger = os.environ.get("GITHUB_EVENT_NAME") or "local"
        self.ci_run_url = ""
        if os.environ.get("GITHUB_RUN_ID"):
            self.ci_run_url = (
                f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
                f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
            )
        self.entries: list[dict] = []
        self.failed = False
        self.path = db.CLIENTS_DIR / slug / "runs" / "run_log.jsonl"

    async def stage(self, name: str, fn) -> None:
        """Run one stage. Once a stage fails, later stages are recorded as skipped."""
        rec = {"stage": name, "status": "success", "model_used": "", "detail": "", "error": ""}
        started = _now()
        print(f"\n[run] ── {name} " + "─" * max(0, 50 - len(name)))
        if self.failed:
            rec.update(status="skipped", detail="upstream stage failed")
        else:
            try:
                await fn(rec)
            except Exception as e:
                traceback.print_exc()
                rec.update(status="failed", error=f"{type(e).__name__}: {e}"[:500])
                self.failed = True
        rec.update(
            run_id=self.run_id, client=self.slug, client_id=self.client_id,
            trigger=self.trigger, ci_run_url=self.ci_run_url,
            started_at=started, finished_at=_now(),
        )
        self.entries.append(rec)
        print(f"[run] {name}: {rec['status'].upper()} "
              f"({_seconds(started, rec['finished_at']):.1f}s) {rec['detail'] or rec['error']}")
        await self._persist(rec)

    async def _persist(self, rec: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        try:
            await db.log_run_stage(rec)
        except Exception as e:
            print(f"[run] SQLite run log write failed (JSONL still written): {e}")

    def write_github_summary(self, article_info: dict) -> None:
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        lines = [
            f"## BrandSCOPE run — `{self.slug}`",
            f"Run `{self.run_id}` · trigger `{self.trigger}` · "
            f"result **{'FAILED' if self.failed else 'SUCCESS'}**",
            "",
            "| Stage | Status | Model | Seconds | Detail |",
            "|---|---|---|---|---|",
        ]
        for e in self.entries:
            detail = (e["detail"] or e["error"]).replace("|", "\\|")[:180]
            lines.append(
                f"| {e['stage']} | {e['status']} | {e['model_used'] or '—'} | "
                f"{_seconds(e['started_at'], e['finished_at']):.1f} | {detail} |"
            )
        if article_info:
            lines += [
                "",
                f"### {article_info['title']}",
                f"{article_info['word_count']} words · SEO {article_info['seo']} · "
                f"AEO {article_info['aeo']} · GEO {article_info['geo']} · `{article_info['path']}`",
            ]
        text = "\n".join(lines) + "\n"
        print("\n" + text)
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(text)


# ── Selection logic ───────────────────────────────────────────────────────────

def pick_angle_and_trend(report: TrendReport, dna: CompanyDNA, written_slugs: set[str]) -> tuple[str, TrendItem]:
    """
    Angle: first AI-generated angle not already written (by slug) and not an existing brand title.
    Trend: the trend that shares the most words with that angle; ties broken by
    segment (brand news first) then relevance score.
    """
    written = written_slugs | {_slugify(t) for t in dna.existing_article_titles}
    angle = next((a for a in report.article_angles if _slugify(a) not in written), "")

    ranked = sorted(
        report.trends,
        key=lambda t: (SEGMENT_PRIORITY.get(t.segment, 9), -t.relevance_score),
    )
    if not angle:
        top = ranked[0]
        return f"{top.title} — What It Means for {dna.name}", top

    angle_words = {w for w in re.findall(r"[a-z0-9]{4,}", angle.lower())}

    def overlap(t: TrendItem) -> int:
        return len(angle_words & set(re.findall(r"[a-z0-9]{4,}", t.title.lower())))

    best = max(ranked[:15], key=overlap)  # max() keeps the first (highest priority) on ties
    return angle, best


def written_article_slugs(slug: str) -> set[str]:
    art_dir = db.CLIENTS_DIR / slug / "04_articles"
    if not art_dir.is_dir():
        return set()
    return {re.sub(r"^\d{4}-\d{2}-\d{2}-", "", p.stem) for p in art_dir.glob("*.md")}


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def run(slug: str, article_type: str | None, send_email: bool) -> int:
    dna_path = db.CLIENTS_DIR / slug / "01_brand_dna" / "company_dna.json"
    if not dna_path.exists():
        print(f"[run] {dna_path} not found. Run Engine 01 locally for this client and commit the file.")
        return 2

    raw = json.loads(dna_path.read_text(encoding="utf-8"))
    dna = CompanyDNA(**{k: v for k, v in raw.items() if k in CompanyDNA.__dataclass_fields__})

    await db.init_db()
    client = await db.get_or_create_client_by_slug(slug, f"https://{dna.domain}", dna.name)
    log = RunLog(slug, client["id"])
    ctx: dict = {}
    print(f"[run] {dna.name} ({dna.domain}) | run {log.run_id} | trigger {log.trigger}")

    async def load_dna(rec):
        rec["detail"] = f"{len(dna.services)} services, {len(dna.top_keywords)} keywords from {dna_path.name}"

    async def trends(rec):
        report = await research_trends(
            services=dna.services,
            top_keywords=dna.top_keywords,
            existing_titles=dna.existing_article_titles,
            brand_name=dna.name,
            domain=dna.domain,
        )
        if not report.trends:
            raise RuntimeError("No trends returned from Google News RSS or DuckDuckGo")
        await db.save_trends(client["id"], asdict(report))
        ctx["report"] = report
        rec["model_used"] = report.model_used or "template-fallback"
        rec["detail"] = (
            f"{len(report.trends)} trends {report.segments} | {len(report.article_angles)} angles | "
            f"ddgs={'on' if trend_researcher.DDGS_AVAILABLE else 'off'}"
        )

    async def brief(rec):
        angle, trend = pick_angle_and_trend(ctx["report"], dna, written_article_slugs(slug))
        a_type = article_type or ARTICLE_TYPE_ROTATION[
            datetime.now(timezone.utc).timetuple().tm_yday % len(ARTICLE_TYPE_ROTATION)
        ]
        b = build_brief(dna, trend, angle, article_type=a_type)
        ctx.update(brief=b, trend=trend, brief_id=await db.save_brief(client["id"], asdict(b)))
        rec["model_used"] = "rule-based"
        rec["detail"] = f"[{a_type}] {b.title} | keyword '{b.primary_keyword}' | hook: {trend.title[:80]}"

    async def article(rec):
        b, trend = ctx["brief"], ctx["trend"]
        art = await write_article(b, dna, trend)
        if not art:
            raise RuntimeError("Every model in the fallback chain failed")
        if art.model_used == "placeholder":
            raise RuntimeError("No GOOGLE_API_KEY or GROQ_API_KEY — refusing to publish placeholder content")

        scores = compute_seo_aeo_geo_scores(art.content, dna, b)
        art_slug = f"{_now()[:10]}-{b.slug}"
        await db.save_article(client["id"], ctx["brief_id"], {
            "content": art.content,
            "word_count": art.word_count,
            "seo_title": art.seo_title,
            "meta_description": art.meta_description,
            "quality_passed": art.quality_passed,
            "primary_keyword": b.primary_keyword,
            "slug": art_slug,
            "seo_score": scores["seo"],
            "aeo_score": scores["aeo"],
            "geo_score": scores["geo"],
            "model_used": art.model_used,
        })
        art_dir = db.CLIENTS_DIR / slug / "04_articles"
        html = markdown_to_html(art, dna)
        (art_dir / f"{art_slug}.html").write_text(html, encoding="utf-8")

        md_path = art_dir / f"{art_slug}.md"
        ctx.update(article=art, html=html, md_path=md_path, scores=scores)
        rec["model_used"] = art.model_used
        rec["detail"] = (
            f"{art.word_count} words | SEO {scores['seo']} AEO {scores['aeo']} GEO {scores['geo']} | "
            f"quality {'pass' if art.quality_passed else 'review'} | {md_path.relative_to(db.BASE_DIR).as_posix()}"
        )

    async def deliver(rec):
        if not send_email:
            rec.update(status="skipped", detail="email disabled for this run")
            return
        if not smtp_configured():
            rec.update(status="skipped", detail="SMTP_USER / SMTP_PASS not set")
            return
        art, scores = ctx["article"], ctx["scores"]
        banner = (
            f'<p style="font-family:sans-serif;color:#555;border-bottom:1px solid #ddd;padding-bottom:8px">'
            f"BrandSCOPE automated run <code>{log.run_id}</code> · {dna.name} · "
            f"SEO {scores['seo']} · AEO {scores['aeo']} · GEO {scores['geo']} · model {art.model_used}"
            + (f' · <a href="{log.ci_run_url}">Actions log</a>' if log.ci_run_url else "")
            + "</p>"
        )
        html = ctx["html"].replace("<body>", "<body>\n" + banner, 1)
        to = await asyncio.to_thread(
            send_article_email,
            f"[BrandSCOPE] {dna.name}: {art.seo_title}",
            html,
            ctx["md_path"].read_text(encoding="utf-8"),
            ctx["md_path"].name,
        )
        rec["detail"] = f"sent to {mask_email(to)}"

    await log.stage("01_load_dna", load_dna)
    await log.stage("02_trend_research", trends)
    await log.stage("03_article_brief", brief)
    await log.stage("04_article_writer", article)
    await log.stage("05_email_delivery", deliver)

    article_info = {}
    if "article" in ctx:
        article_info = {
            "title": ctx["article"].seo_title,
            "word_count": ctx["article"].word_count,
            "seo": ctx["scores"]["seo"], "aeo": ctx["scores"]["aeo"], "geo": ctx["scores"]["geo"],
            "path": ctx["md_path"].relative_to(db.BASE_DIR).as_posix(),
        }
    log.write_github_summary(article_info)
    return 1 if log.failed else 0


def main():
    parser = argparse.ArgumentParser(description="BrandSCOPE headless pipeline (Engine 02 → 03 → 04 → email)")
    parser.add_argument("--client", default=os.environ.get("BRANDSCOPE_CLIENT", "sarvam-ai"),
                        help="Client folder name under clients/ (default: sarvam-ai)")
    parser.add_argument("--type", choices=list(ARTICLE_TYPES.keys()),
                        help="Article type (default: rotates daily)")
    parser.add_argument("--no-email", action="store_true", help="Skip the email delivery stage")
    args = parser.parse_args()

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.client):
        parser.error("--client must be a folder slug like 'sarvam-ai'")

    sys.exit(asyncio.run(run(args.client, args.type, not args.no_email)))


if __name__ == "__main__":
    main()
