"""
FastAPI server — exposes the 4 engines as REST endpoints + client management.
Run: python backend/run.py   (or: uvicorn server:app --reload --port 8000)
"""

import os
import sys
from pathlib import Path
from dataclasses import asdict

# Fix Windows console encoding so Unicode in print() doesn't crash uvicorn
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("cp1252", "charmap"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() in ("cp1252", "charmap"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from company_scraper import CompanyDNA, extract_company_dna
from trend_researcher import research_trends, TrendItem
from article_generator import (
    build_brief, write_article, ArticleBrief,
    quality_check, has_banned_phrases, compute_seo_aeo_geo_scores,
)
import httpx

import database as db
import dna_jobs
import github_actions as gh
from database import get_article
from llm import GEMINI_MODEL


app = FastAPI(title="BrandSCOPE API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.init_db()
    print("[brandscope] Database ready at", db.DB_PATH)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _filter(dc_class, data: dict) -> dict:
    """Strip keys not present in a dataclass so extra frontend fields don't crash init."""
    known = {f.name for f in dc_class.__dataclass_fields__.values()}
    return {k: v for k, v in data.items() if k in known}


# ── Request models ────────────────────────────────────────────────────────────

class ExtractDNARequest(BaseModel):
    url: str

class ResearchTrendsRequest(BaseModel):
    services: list[str]
    top_keywords: list[str]
    existing_titles: list[str] = []
    brand_name: str = ""
    domain: str = ""

class BuildBriefRequest(BaseModel):
    dna: dict
    trend: dict
    angle: str
    article_type: str = "educational"

class WriteArticleRequest(BaseModel):
    brief: dict
    dna: dict
    trend: dict
    model: str = GEMINI_MODEL
    api_key: str | None = None

# ── Client management models ──────────────────────────────────────────────────

class CreateClientRequest(BaseModel):
    url: str

class SaveDNARequest(BaseModel):
    dna: dict

class SaveTrendsRequest(BaseModel):
    report: dict

class SaveBriefRequest(BaseModel):
    brief: dict

class SaveArticleRequest(BaseModel):
    article: dict
    brief_id: int | None = None


# ── Engine endpoints (unchanged) ──────────────────────────────────────────────

@app.post("/api/extract-dna")
async def api_extract_dna(req: ExtractDNARequest):
    try:
        dna = await extract_company_dna(req.url)
        return asdict(dna)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/research-trends")
async def api_research_trends(req: ResearchTrendsRequest):
    try:
        report = await research_trends(
            services=req.services,
            top_keywords=req.top_keywords,
            existing_titles=req.existing_titles,
            brand_name=req.brand_name,
            domain=req.domain,
        )
        return {
            "industry":          report.industry,
            "query_used":        report.query_used,
            "generated_at":      report.generated_at,
            "trends":            [asdict(t) for t in report.trends],
            "key_themes":        report.key_themes,
            "emerging_keywords": report.emerging_keywords,
            "article_angles":    report.article_angles,
            "brand_summary":     report.brand_summary,
            "segments":          report.segments,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/build-brief")
async def api_build_brief(req: BuildBriefRequest):
    try:
        dna   = CompanyDNA(**_filter(CompanyDNA,   req.dna))
        trend = TrendItem(**_filter(TrendItem,     req.trend))
        brief = build_brief(dna, trend, req.angle, article_type=req.article_type)
        return asdict(brief)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/write-article")
async def api_write_article(req: WriteArticleRequest):
    try:
        dna   = CompanyDNA(**_filter(CompanyDNA,    req.dna))
        trend = TrendItem(**_filter(TrendItem,      req.trend))
        brief = ArticleBrief(**_filter(ArticleBrief, req.brief))
        api_key = req.api_key or os.environ.get("GOOGLE_API_KEY", "")

        article = await write_article(brief, dna, trend, api_key=api_key, model=req.model)
        if not article:
            raise HTTPException(status_code=500, detail="Article generation failed")

        checks = quality_check(article.content, dna, brief)
        banned = has_banned_phrases(article.content)
        scores = compute_seo_aeo_geo_scores(article.content, dna, brief)

        return {
            "content":          article.content,
            "word_count":       article.word_count,
            "seo_title":        article.seo_title,
            "meta_description": article.meta_description,
            "schema_faq":       article.schema_faq,
            "quality_passed":   article.quality_passed,
            "generated_at":     article.generated_at,
            "quality_checks":   [{"label": k.replace("_", " "), "pass": v} for k, v in checks.items()],
            "banned_phrases":   banned,
            "seo_score":        scores["seo"],
            "aeo_score":        scores["aeo"],
            "geo_score":        scores["geo"],
            "model_used":       article.model_used,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Client management endpoints ───────────────────────────────────────────────

@app.get("/api/clients")
async def api_list_clients():
    try:
        return await db.list_clients()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/clients")
async def api_create_client(req: CreateClientRequest):
    try:
        return await db.create_client(req.url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clients/{client_id}")
async def api_get_client(client_id: int):
    try:
        client = await db.get_client(client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        return client
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/clients/{client_id}")
async def api_delete_client(client_id: int):
    try:
        ok = await db.delete_client(client_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Client not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Save endpoints (auto-called by frontend after each engine) ────────────────

@app.post("/api/clients/{client_id}/save-dna")
async def api_save_dna(client_id: int, req: SaveDNARequest):
    try:
        updated = await db.save_dna(client_id, req.dna)
        return {"ok": True, "client": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/clients/{client_id}/save-trends")
async def api_save_trends(client_id: int, req: SaveTrendsRequest):
    try:
        record_id = await db.save_trends(client_id, req.report)
        return {"ok": True, "id": record_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/clients/{client_id}/save-brief")
async def api_save_brief(client_id: int, req: SaveBriefRequest):
    try:
        record_id = await db.save_brief(client_id, req.brief)
        return {"ok": True, "id": record_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/clients/{client_id}/save-article")
async def api_save_article(client_id: int, req: SaveArticleRequest):
    try:
        record_id = await db.save_article(client_id, req.brief_id, req.article)
        return {"ok": True, "id": record_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clients/{client_id}/articles/{article_id}")
async def api_get_article(client_id: int, article_id: int):
    try:
        article = await get_article(client_id, article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        return article
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Run log (written by backend/run_pipeline.py) ──────────────────────────────

@app.get("/api/runs")
async def api_list_runs(limit: int = 100):
    try:
        return await db.list_runs(limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Brand Autopilot: brand name → Engine 01 job → GitHub Actions workflow ─────

class AutopilotScrapeRequest(BaseModel):
    query: str

class RunWorkflowRequest(BaseModel):
    client_id: int
    article_type: str = "rotate"


@app.post("/api/autopilot/scrape")
async def api_autopilot_scrape(req: AutopilotScrapeRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Enter a brand name or website")
    try:
        job = dna_jobs.start_job(req.query.strip())
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return job.to_dict()


@app.get("/api/autopilot/jobs/{job_id}")
async def api_autopilot_job(job_id: str):
    job = dna_jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found (the server may have restarted)")
    return job.to_dict()


@app.get("/api/github/status")
async def api_github_status():
    return await gh.connection_status()


@app.post("/api/github/run-workflow")
async def api_run_workflow(req: RunWorkflowRequest):
    if req.article_type not in gh.ARTICLE_TYPES:
        raise HTTPException(status_code=400, detail=f"article_type must be one of {', '.join(gh.ARTICLE_TYPES)}")
    client = await db.get_client(req.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    slug = client["slug"]
    if not gh.SLUG_RE.match(slug):
        raise HTTPException(status_code=400, detail=f"Client slug '{slug}' is not a valid folder name")
    if not client.get("dna"):
        raise HTTPException(status_code=400, detail="This brand has no DNA yet. Scrape it first.")

    status = await gh.connection_status()
    if not status["ok"]:
        raise HTTPException(status_code=400, detail=status["message"])
    try:
        publish = await gh.publish_dna(status["repo"], status["branch"], slug, client["dna"])
        dispatch = await gh.dispatch_workflow(status["repo"], status["branch"], slug, req.article_type)
    except (gh.GitHubError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {
        "client": slug,
        "repo": status["repo"],
        "branch": status["branch"],
        "actions_url": status["actions_url"],
        "publish": publish,
        **dispatch,
    }


@app.get("/api/github/runs")
async def api_github_recent_runs(limit: int = 8):
    try:
        ctx = await gh.repo_context()
        return await gh.recent_runs(ctx["repo"], min(max(limit, 1), 30))
    except (gh.GitHubError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/github/runs/{run_id}")
async def api_github_run(run_id: int, client: str = ""):
    """Live status of one workflow run; once completed, also what it committed."""
    try:
        ctx = await gh.repo_context()
        run = await gh.run_status(ctx["repo"], run_id)
        if run["status"] == "completed" and gh.SLUG_RE.match(client):
            run["outputs"] = await gh.run_outputs(ctx["repo"], ctx["branch"], client, run_id)
        return run
    except (gh.GitHubError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Serve the built frontend (npm run build) at the same origin ───────────────
# Mounted last so /api/* routes above take precedence.

_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
