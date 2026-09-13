"""
GitHub Actions bridge for the UI's Run Workflow button.

Run Workflow = the same daily-article workflow as the "Run workflow" button on GitHub:
  1. commit the brand's DNA to clients/{slug}/01_brand_dna/company_dna.json
  2. dispatch .github/workflows/daily-article.yml with inputs.client = slug
  3. poll the run; when it finishes, read the committed run log + article back

backend/.env:
  GITHUB_TOKEN    fine-grained PAT for the repo: Contents (read/write) + Actions (read/write)
  GITHUB_REPO     owner/name, default SupratikB23/BrandSCOPE
  GITHUB_API_URL  optional, for tests
"""

import asyncio
import base64
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx

WORKFLOW_FILE = "daily-article.yml"
ARTICLE_TYPES = ("rotate", "educational", "listicle", "guide", "trend-report", "opinion", "case-study")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

_HINTS = {
    401: "GITHUB_TOKEN is invalid or expired.",
    403: "The token lacks permission (needs Contents: Read and write + Actions: Read and write) or hit a rate limit.",
    404: "Repo or workflow not found, or the token has no access to this repo.",
    422: "GitHub rejected the request. Is the latest daily-article.yml pushed to the default branch?",
}

_repo_cache: dict = {}


class GitHubError(RuntimeError):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def _config() -> dict:
    return {
        "token": os.environ.get("GITHUB_TOKEN", "").strip(),
        "repo": os.environ.get("GITHUB_REPO", "SupratikB23/BrandSCOPE").strip(),
        "api": os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/"),
    }


async def _request(method: str, path: str, *, json_body=None, params=None, raw=False, allow_404=False):
    cfg = _config()
    headers = {
        "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "BrandSCOPE",
    }
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
    async with httpx.AsyncClient(base_url=cfg["api"], headers=headers, timeout=30, follow_redirects=True) as c:
        r = await c.request(method, path, json=json_body, params=params)
    if r.status_code == 404 and allow_404:
        return None
    if r.status_code >= 400:
        try:
            msg = r.json().get("message", r.text)
        except Exception:
            msg = r.text
        raise GitHubError(f"GitHub {r.status_code} on {method} {path}: {msg}. {_HINTS.get(r.status_code, '')}".strip(),
                          r.status_code)
    if raw:
        return r.text
    if not r.content:
        return {}
    return r.json()


def _contents_path(repo: str, path: str) -> str:
    return f"/repos/{repo}/contents/{quote(path)}"


async def repo_context() -> dict:
    """Canonical repo name + default branch (cached for 5 minutes)."""
    if _repo_cache and time.time() - _repo_cache["at"] < 300:
        return _repo_cache["ctx"]
    repo = await _request("GET", f"/repos/{_config()['repo']}")
    ctx = {
        "repo": repo["full_name"],
        "branch": repo.get("default_branch", "main"),
        "repo_url": repo.get("html_url", f"https://github.com/{repo['full_name']}"),
    }
    ctx["actions_url"] = f"{ctx['repo_url']}/actions/workflows/{WORKFLOW_FILE}"
    _repo_cache.update(ctx=ctx, at=time.time())
    return ctx


async def connection_status() -> dict:
    cfg = _config()
    base = {"configured": bool(cfg["token"]), "repo": cfg["repo"], "workflow_file": WORKFLOW_FILE}
    if not cfg["token"]:
        return {**base, "ok": False,
                "message": "Add GITHUB_TOKEN to backend/.env and restart the server to enable Run Workflow."}
    try:
        ctx = await repo_context()
        wf = await _request("GET", f"/repos/{ctx['repo']}/actions/workflows/{WORKFLOW_FILE}")
    except (GitHubError, httpx.HTTPError) as e:
        return {**base, "ok": False, "message": str(e)}
    return {**base, **ctx, "ok": True, "workflow_state": wf.get("state", ""), "message": ""}


async def publish_dna(repo: str, branch: str, slug: str, dna: dict) -> dict:
    """Commit the DNA the workflow reads. Skips the commit when GitHub already has identical DNA."""
    path = f"clients/{slug}/01_brand_dna/company_dna.json"
    existing = await _request("GET", _contents_path(repo, path), params={"ref": branch}, allow_404=True)
    body = {
        "message": f"brand dna: {slug} (BrandSCOPE UI)",
        "content": base64.b64encode((json.dumps(dna, indent=2, ensure_ascii=False) + "\n").encode("utf-8")).decode(),
        "branch": branch,
    }
    if existing:
        body["sha"] = existing.get("sha")
        try:
            if json.loads(base64.b64decode(existing.get("content", "")).decode("utf-8")) == dna:
                return {"changed": False, "path": path, "commit_sha": "", "commit_url": ""}
        except (ValueError, UnicodeDecodeError):
            pass
    res = await _request("PUT", _contents_path(repo, path), json_body=body)
    commit = res.get("commit", {})
    return {"changed": True, "path": path, "commit_sha": commit.get("sha", ""), "commit_url": commit.get("html_url", "")}


async def dispatch_workflow(repo: str, branch: str, slug: str, article_type: str) -> dict:
    since = datetime.now(timezone.utc)
    res = await _request(
        "POST", f"/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/dispatches",
        json_body={"ref": branch, "inputs": {"client": slug, "article_type": article_type}},
    )
    run_id = res.get("workflow_run_id") if isinstance(res, dict) else None
    if not run_id:
        run_id = await find_dispatched_run(repo, branch, slug, since)
    return {"run_id": run_id, "dispatched_at": since.isoformat()}


async def find_dispatched_run(repo: str, branch: str, slug: str, since: datetime, attempts: int = 15) -> int | None:
    """The dispatch API returns no run id, so match the newest run created after the dispatch."""
    for _ in range(attempts):
        data = await _request(
            "GET", f"/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/runs",
            params={"event": "workflow_dispatch", "branch": branch, "per_page": 10},
        )
        fresh = [
            r for r in data.get("workflow_runs", [])
            if datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= since - timedelta(seconds=10)
        ]
        titled = [r for r in fresh if slug in (r.get("display_title") or "")]
        pick = (titled or fresh)
        if pick:
            return max(pick, key=lambda r: r["created_at"])["id"]
        await asyncio.sleep(3)
    return None


async def run_status(repo: str, run_id: int) -> dict:
    run = await _request("GET", f"/repos/{repo}/actions/runs/{run_id}")
    jobs = await _request("GET", f"/repos/{repo}/actions/runs/{run_id}/jobs")
    steps = []
    for job in jobs.get("jobs", []):
        for s in job.get("steps", []):
            if s["name"] in ("Set up job", "Complete job") or s["name"].startswith("Post "):
                continue
            steps.append({
                "name": s["name"], "status": s["status"], "conclusion": s.get("conclusion"),
                "started_at": s.get("started_at"), "completed_at": s.get("completed_at"),
            })
    return {
        "id": run["id"],
        "title": run.get("display_title", ""),
        "event": run.get("event", ""),
        "status": run["status"],
        "conclusion": run.get("conclusion"),
        "html_url": run.get("html_url", ""),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "steps": steps,
    }


def _split_frontmatter(md: str) -> tuple[dict, str]:
    meta: dict = {}
    m = re.match(r"^---\n(.*?)\n---\n+", md, re.S)
    if not m:
        return meta, md
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        if key.strip():
            meta[key.strip()] = value.strip()
    return meta, md[m.end():]


async def run_outputs(repo: str, branch: str, slug: str, run_id: int) -> dict:
    """Read back what the run committed: its run-log entries and the article."""
    log_text = await _request("GET", _contents_path(repo, f"clients/{slug}/runs/run_log.jsonl"),
                              params={"ref": branch}, raw=True, allow_404=True)
    if not log_text:
        return {"entries": [], "article": None, "message": "No run log committed for this client yet."}

    suffix = f"/actions/runs/{run_id}"
    entries = []
    for line in log_text.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if str(e.get("ci_run_url", "")).endswith(suffix):
            entries.append(e)

    article = None
    writer = next((e for e in entries if e.get("stage") == "04_article_writer" and e.get("status") == "success"), None)
    if writer:
        m = re.search(r"(clients/\S+?\.md)", writer.get("detail", ""))
        if m:
            path = m.group(1)
            md = await _request("GET", _contents_path(repo, path), params={"ref": branch}, raw=True, allow_404=True)
            meta, body = _split_frontmatter((md or "").replace("\r\n", "\n"))
            article = {"path": path, "url": f"https://github.com/{repo}/blob/{branch}/{path}", "meta": meta, "markdown": body}

    return {"entries": entries, "article": article,
            "message": "" if entries else "Run log for this run not found in the repo yet."}


async def recent_runs(repo: str, limit: int = 8) -> list[dict]:
    data = await _request("GET", f"/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/runs", params={"per_page": limit})
    return [
        {
            "id": r["id"], "title": r.get("display_title", ""), "event": r.get("event", ""),
            "status": r["status"], "conclusion": r.get("conclusion"),
            "html_url": r.get("html_url", ""), "created_at": r.get("created_at"),
        }
        for r in data.get("workflow_runs", [])
    ]
