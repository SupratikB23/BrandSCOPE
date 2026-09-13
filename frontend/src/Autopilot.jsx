import { useState, useEffect, useRef } from 'react';
import { Badge, Btn, Card, Input, Spinner, Tag } from './components';
import { renderMd } from './ArticleWriter';
import {
  startAutopilotScrape, getAutopilotJob, getClient,
  getGitHubStatus, runWorkflow, getWorkflowRun, getRecentRuns,
} from './api';

const ARTICLE_TYPES = [
  { id: "rotate",       label: "Rotate daily" },
  { id: "educational",  label: "Educational" },
  { id: "listicle",     label: "Listicle" },
  { id: "guide",        label: "Guide" },
  { id: "trend-report", label: "Trend report" },
  { id: "opinion",      label: "Opinion" },
  { id: "case-study",   label: "Case study" },
];

// Workflow step names in daily-article.yml → readable labels
const STEP_LABELS = {
  "Run actions/checkout@v4": "Checkout repo",
  "Run actions/setup-python@v5": "Set up Python",
  "Install pipeline dependencies (no Playwright / spaCy)": "Install dependencies",
  "Run pipeline": "Engine 02 → 03 → 04 → email",
  "Upload article and run log": "Upload artifact",
  "Commit outputs and run log": "Commit & push to repo",
};

const RUN_KEY = "bs_autopilot_run";

function escapeHtml(s) {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
}

function fmtDuration(seconds) {
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  return m ? `${m}m ${s % 60}s` : `${s}s`;
}

function readSavedRun() {
  try { return JSON.parse(localStorage.getItem(RUN_KEY) || "null"); } catch { return null; }
}

function Label({ children, style }) {
  return (
    <p style={{ margin: "0 0 12px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)", ...style }}>
      {children}
    </p>
  );
}

function StateIcon({ state, size = 20 }) {
  const styles = {
    done:    { bg: "var(--badge-green-bg)", border: "var(--badge-green-border)", fg: "var(--green)" },
    active:  { bg: "var(--badge-blue-bg)",  border: "var(--badge-blue-border)",  fg: "var(--accent)" },
    failed:  { bg: "var(--red-subtle)",     border: "var(--red-border)",         fg: "var(--red)" },
    skipped: { bg: "var(--surface-2)",      border: "var(--border)",             fg: "var(--text-4)" },
    idle:    { bg: "var(--surface-2)",      border: "var(--border)",             fg: "var(--text-4)" },
  };
  const s = styles[state] || styles.idle;
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%", flexShrink: 0,
      display: "flex", alignItems: "center", justifyContent: "center",
      background: s.bg, border: `1px solid ${s.border}`, color: s.fg, fontSize: size * 0.5,
    }}>
      {state === "done" ? "✓" : state === "failed" ? "✕" : state === "active" ? <Spinner size={size * 0.45} /> : state === "skipped" ? "–" : ""}
    </div>
  );
}

function stepState(step) {
  if (step.status !== "completed") return step.status === "in_progress" ? "active" : "idle";
  if (step.conclusion === "success") return "done";
  if (step.conclusion === "skipped") return "skipped";
  return "failed";
}

function stageState(status) {
  return { success: "done", failed: "failed", skipped: "skipped" }[status] || "idle";
}

function runBadge(run) {
  if (!run) return <Badge color="gray" size="xs">waiting</Badge>;
  if (run.status !== "completed") return <Badge color="blue" size="xs">{run.status.replace("_", " ")}</Badge>;
  return run.conclusion === "success"
    ? <Badge color="green" size="xs">success</Badge>
    : <Badge color="red" size="xs">{run.conclusion || "failed"}</Badge>;
}


// ── Pipeline overview strip ───────────────────────────────────────────────────

function PipelineStrip({ steps }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 10, marginBottom: 22 }}>
      {steps.map((s, i) => (
        <div key={i} style={{
          display: "flex", alignItems: "center", gap: 10, padding: "12px 14px",
          background: "var(--surface)", borderRadius: 10,
          border: `1px solid ${s.state === "active" ? "var(--accent-border)" : s.state === "failed" ? "var(--red-border)" : "var(--border)"}`,
        }}>
          <StateIcon state={s.state} size={24} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-4)", letterSpacing: "0.12em", fontFamily: "var(--font-mono)" }}>STEP {i + 1}</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", fontFamily: "var(--font-display)" }}>{s.label}</div>
            <div style={{ fontSize: 11, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.hint}</div>
          </div>
        </div>
      ))}
    </div>
  );
}


// ── Page ──────────────────────────────────────────────────────────────────────

export default function AutopilotPage({ initialClient, initialQuery, dark, setDark, onBack, onOpenClient }) {
  const [gh, setGh]                   = useState(null);
  const [query, setQuery]             = useState(initialQuery || "");
  const [job, setJob]                 = useState(null);
  const [scrapeError, setScrapeError] = useState(null);
  const [client, setClient]           = useState(null);
  const [articleType, setArticleType] = useState("rotate");
  const [dispatching, setDispatching] = useState(false);
  const [dispatchError, setDispatchError] = useState(null);
  const [dispatch, setDispatch]       = useState(null);
  const [run, setRun]                 = useState(null);
  const [runError, setRunError]       = useState(null);
  const [recent, setRecent]           = useState([]);
  const [tick, setTick]               = useState(0);

  const started      = useRef(false);
  const consoleRef   = useRef(null);
  const outputTries  = useRef(0);

  const dna      = client?.dna || null;
  const scraping = job?.status === "running";

  // ── Initial load ───────────────────────────────────────────────────────────
  useEffect(() => {
    getGitHubStatus().then(setGh).catch(e => setGh({ ok: false, message: e.message }));
    refreshRecent();
    if (started.current) return;
    started.current = true;
    if (initialClient?.id) loadClient(initialClient.id);
    else if (initialQuery) startScrape(initialQuery);
  }, []);

  function refreshRecent() {
    getRecentRuns().then(setRecent).catch(() => {});
  }

  async function loadClient(id) {
    try {
      const full = await getClient(id);
      setClient(full);
      setQuery(full.name || full.domain || "");
      const saved = readSavedRun();
      if (saved && saved.slug === full.slug) setDispatch(saved);   // resume a run started earlier
    } catch (e) {
      setScrapeError(e.message);
    }
  }

  async function startScrape(q) {
    const value = (q ?? query).trim();
    if (!value || scraping) return;
    setScrapeError(null); setJob(null); setClient(null);
    setDispatch(null); setRun(null); setDispatchError(null); setRunError(null);
    try {
      setJob(await startAutopilotScrape(value));
    } catch (e) {
      setScrapeError(e.message);
    }
  }

  // ── Poll the Engine 01 job ─────────────────────────────────────────────────
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setTimeout(async () => {
      try {
        const next = await getAutopilotJob(job.id);
        setJob(next);
        if (next.status === "success") setClient({ ...next.result.client, dna: next.result.dna });
        if (next.status === "failed")  setScrapeError(next.error);
      } catch (e) {
        setScrapeError(e.message);
        setJob(j => ({ ...j, status: "failed" }));
      }
    }, 1500);
    return () => clearTimeout(t);
  }, [job]);

  useEffect(() => {
    if (consoleRef.current) consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
  }, [job?.log_count]);

  // ── Run Workflow ───────────────────────────────────────────────────────────
  async function handleRunWorkflow() {
    if (!client?.id || dispatching) return;
    setDispatching(true); setDispatchError(null); setRunError(null); setRun(null);
    outputTries.current = 0;
    try {
      const res = await runWorkflow(client.id, articleType);
      const saved = { ...res, slug: res.client, clientId: client.id };
      setDispatch(saved);
      try { localStorage.setItem(RUN_KEY, JSON.stringify(saved)); } catch { /* storage unavailable */ }
      refreshRecent();
    } catch (e) {
      setDispatchError(e.message);
    } finally {
      setDispatching(false);
    }
  }

  // ── Poll the GitHub Actions run ────────────────────────────────────────────
  const runFinished = run?.status === "completed" &&
    (run.conclusion !== "success" || run.outputs?.entries?.length > 0 || outputTries.current >= 8);

  useEffect(() => {
    if (!dispatch || runFinished) return;
    const t = setTimeout(async () => {
      try {
        if (!dispatch.run_id) {
          // Dispatch accepted but the run was not visible yet: look for it
          const runs = await getRecentRuns();
          setRecent(runs);
          const since = Date.parse(dispatch.dispatched_at) - 15000;
          const fresh = runs.filter(r => Date.parse(r.created_at) >= since);
          const match = fresh.find(r => (r.title || "").includes(dispatch.slug)) || fresh.find(r => r.event === "workflow_dispatch");
          if (match) setDispatch(d => ({ ...d, run_id: match.id }));
        } else {
          const next = await getWorkflowRun(dispatch.run_id, dispatch.slug);
          if (next.status === "completed") {
            if (outputTries.current === 0) refreshRecent();
            outputTries.current += 1;
          }
          setRun(next);
          setRunError(null);
        }
      } catch (e) {
        setRunError(e.message);
      }
      setTick(n => n + 1);
    }, run ? 5000 : 1500);
    return () => clearTimeout(t);
  }, [dispatch, run, tick, runFinished]);

  // ── Derived view state ─────────────────────────────────────────────────────
  const outputs = run?.outputs;
  const article = outputs?.article;
  const runElapsed = run?.created_at
    ? ((run.status === "completed" ? Date.parse(run.updated_at) : Date.now()) - Date.parse(run.created_at)) / 1000
    : 0;

  const pipeline = [
    {
      label: "Find website",
      state: dna && !job ? "done"
        : !job ? "idle"
        : job.stage === "resolving" ? (job.status === "failed" ? "failed" : "active") : "done",
      hint: job?.url || client?.url || client?.domain || "brand name → official site",
    },
    {
      label: "Scrape brand DNA",
      state: dna ? "done"
        : scraping && job.stage !== "resolving" ? "active"
        : job?.status === "failed" && job.stage !== "resolving" ? "failed" : "idle",
      hint: scraping ? `${job.stage} · ${fmtDuration(job.elapsed)}` : dna ? `${dna.services?.length || 0} services · ${dna.top_keywords?.length || 0} keywords` : "Engine 01 · Playwright crawl",
    },
    {
      label: "Run GitHub workflow",
      state: dispatching ? "active"
        : !dispatch ? "idle"
        : !run || run.status !== "completed" ? "active"
        : run.conclusion === "success" ? "done" : "failed",
      hint: run ? `${run.status.replace("_", " ")} · ${fmtDuration(runElapsed)}` : dispatch ? "starting on GitHub Actions" : "Engines 02 → 04 on Actions",
    },
    {
      label: "Article committed",
      state: article ? "done"
        : run?.status === "completed" && run.conclusion !== "success" ? "failed"
        : run?.status === "completed" && !runFinished ? "active" : "idle",
      hint: article ? article.path.split("/").pop() : "pushed to repo + emailed",
    },
  ];

  const canRun = Boolean(dna && client?.id && gh?.ok && !dispatching && !scraping &&
    (!dispatch || runFinished));

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex", flexDirection: "column" }}>

      <header style={{
        height: 52, flexShrink: 0, background: "var(--sidebar-bg)",
        borderBottom: "1px solid var(--border)", backdropFilter: "var(--card-backdrop)",
        WebkitBackdropFilter: "var(--card-backdrop)",
        display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 28px", gap: 12,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 30, height: 30, borderRadius: 8, background: "var(--accent)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 14, fontWeight: 800, color: "#fff", fontFamily: "var(--font-display)",
            boxShadow: "0 0 12px var(--accent-glow)",
          }}>B</div>
          <span style={{ fontSize: 14, fontWeight: 800, color: "var(--text)", letterSpacing: "-0.03em", fontFamily: "var(--font-display)" }}>BrandSCOPE</span>
          <span style={{ color: "var(--border-strong)", fontSize: 15, margin: "0 2px" }}>/</span>
          <span style={{ fontSize: 12, color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>autopilot</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {gh === null
            ? <Badge color="gray" size="xs">GitHub · checking</Badge>
            : gh.ok
              ? <a href={gh.actions_url} target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>
                  <Badge color="green" size="xs">● GitHub · {gh.repo}@{gh.branch}</Badge>
                </a>
              : <Badge color="amber" size="xs">GitHub not connected</Badge>}
          <Btn variant="ghost" size="sm" onClick={onBack}>← Brands</Btn>
          <button onClick={() => setDark(d => !d)} title={dark ? "Switch to Light" : "Switch to Dark"} style={{
            width: 32, height: 32, borderRadius: 8, border: "1px solid var(--border)",
            background: "var(--surface-2)", cursor: "pointer", fontSize: 14, color: "var(--text-2)",
          }}>{dark ? "☀" : "☾"}</button>
        </div>
      </header>

      <main style={{ flex: 1, padding: "32px 28px 60px", maxWidth: 1060, margin: "0 auto", width: "100%" }}>

        <div className="fade-up" style={{ marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--accent)", fontFamily: "var(--font-mono)" }}>Brand Autopilot</span>
            <div style={{ width: 28, height: 1, background: "var(--border-strong)" }} />
          </div>
          <h1 className="gradient-text" style={{ fontSize: 30, fontWeight: 800, margin: 0, letterSpacing: "-0.03em", fontFamily: "var(--font-display)" }}>
            Type a brand. Get a published article.
          </h1>
          <p style={{ fontSize: 14, color: "var(--text-2)", margin: "10px 0 0", lineHeight: 1.7, maxWidth: 680 }}>
            BrandSCOPE finds the brand's website and scrapes its DNA here, then Run Workflow starts the same
            GitHub Actions pipeline as the Actions tab: trends, brief, article, email, and a commit back to the repo.
          </p>
        </div>

        <PipelineStrip steps={pipeline} />

        {/* ── Step 1: brand input ── */}
        <Card style={{ marginBottom: 16 }}>
          <Label>1 · Brand</Label>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Input
              value={query}
              onChange={setQuery}
              placeholder="Brand name (e.g. Zepto) or website"
              prefix="◎"
              style={{ flex: 1, minWidth: 240 }}
              onKeyDown={e => e.key === "Enter" && startScrape()}
            />
            <Btn onClick={() => startScrape()} disabled={!query.trim() || scraping} size="md">
              {scraping ? <><Spinner size={13} /> Scraping…</> : dna ? "Re-scrape" : "Scrape brand →"}
            </Btn>
          </div>
          <p style={{ margin: "9px 0 0", fontSize: 12, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>
            Name → DuckDuckGo + Gemini website lookup → Playwright crawl (up to 60 pages) → Gemini DNA synthesis · takes a few minutes
          </p>
          {scrapeError && (
            <div style={{ marginTop: 12, padding: "10px 12px", background: "var(--red-subtle)", border: "1px solid var(--red-border)", borderRadius: 8 }}>
              <p style={{ margin: 0, fontSize: 13, color: "var(--red)" }}>{scrapeError}</p>
            </div>
          )}
        </Card>

        {/* ── Live scrape log ── */}
        {job && (scraping || job.status === "failed") && (
          <Card style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, gap: 10, flexWrap: "wrap" }}>
              <Label style={{ margin: 0 }}>Engine 01 · live log</Label>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                {job.url && <Badge color="blue" size="xs">{job.url}</Badge>}
                <Badge color={job.status === "failed" ? "red" : "gray"} size="xs">{job.stage} · {fmtDuration(job.elapsed)}</Badge>
              </div>
            </div>
            <div ref={consoleRef} style={{
              background: "var(--surface-2)", borderRadius: 8, padding: "10px 12px",
              height: 240, overflowY: "auto", fontFamily: "var(--font-mono)", fontSize: 11,
              lineHeight: 1.6, color: "var(--text-2)", whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>
              {job.logs?.length ? job.logs.join("\n") : "Starting…"}
            </div>
          </Card>
        )}

        {/* ── DNA summary ── */}
        {dna && (
          <Card style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
              <div style={{ minWidth: 0 }}>
                <Label style={{ marginBottom: 6 }}>2 · Brand DNA</Label>
                <h2 className="gradient-text" style={{ margin: 0, fontSize: 26, fontWeight: 900, letterSpacing: "-0.03em", fontFamily: "var(--font-display)" }}>{dna.name || client.name}</h2>
                <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>
                  {dna.domain} · saved to clients/{client.slug}/01_brand_dna/
                </p>
                {dna.tagline && <p style={{ margin: "8px 0 0", fontSize: 14, color: "var(--text-2)", lineHeight: 1.5, maxWidth: 720 }}>{dna.tagline}</p>}
              </div>
              <Btn variant="ghost" size="sm" onClick={() => onOpenClient(client)}>Open in engines →</Btn>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 18, marginTop: 18 }}>
              <div>
                <Label>Services</Label>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                  {(dna.services || []).slice(0, 10).map(s => <Tag key={s}>{s}</Tag>)}
                  {!dna.services?.length && <span style={{ fontSize: 12, color: "var(--text-4)" }}>None found</span>}
                </div>
              </div>
              <div>
                <Label>Voice</Label>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                  {(dna.tone_adjectives || []).map(t => <Badge key={t} color="purple">{t}</Badge>)}
                  <Badge color="blue">{dna.uses_first_person ? "first person" : "third person"}</Badge>
                </div>
                <div style={{ display: "flex", gap: 16, marginTop: 14 }}>
                  {[
                    ["services", dna.services?.length || 0],
                    ["keywords", dna.top_keywords?.length || 0],
                    ["articles found", dna.existing_article_titles?.length || 0],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <div className="gradient-text" style={{ fontSize: 24, fontWeight: 800, fontFamily: "var(--font-display)", lineHeight: 1 }}>{value}</div>
                      <div style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>{label}</div>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <Label>USPs</Label>
                {(dna.usps || []).slice(0, 4).map((u, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, marginBottom: 6 }}>
                    <span style={{ color: "var(--amber)", fontSize: 12 }}>★</span>
                    <span style={{ fontSize: 12, color: "var(--text-2)", lineHeight: 1.5 }}>{u}</span>
                  </div>
                ))}
                {!dna.usps?.length && <span style={{ fontSize: 12, color: "var(--text-4)" }}>None found</span>}
              </div>
            </div>
          </Card>
        )}

        {/* ── Step 3: Run Workflow ── */}
        {dna && (
          <Card style={{ marginBottom: 16, borderColor: "var(--accent-border)" }}>
            <Label>3 · Run workflow on GitHub Actions</Label>
            <p style={{ margin: "0 0 14px", fontSize: 13, color: "var(--text-2)", lineHeight: 1.65 }}>
              Commits this DNA to <code>clients/{client.slug}/</code>, then triggers <code>daily-article.yml</code> with
              client <code>{client.slug}</code>. The run researches trends, builds the brief, writes and scores the article,
              emails it, and pushes every file back to the repo.
            </p>

            {gh && !gh.ok && (
              <div style={{ marginBottom: 14, padding: "12px 14px", background: "var(--surface-2)", border: "1px solid var(--border-strong)", borderRadius: 8 }}>
                <p style={{ margin: "0 0 6px", fontSize: 13, fontWeight: 600, color: "var(--amber)" }}>GitHub is not connected</p>
                <p style={{ margin: 0, fontSize: 12, color: "var(--text-2)", lineHeight: 1.6 }}>{gh.message}</p>
              </div>
            )}

            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <select
                value={articleType}
                onChange={e => setArticleType(e.target.value)}
                style={{
                  background: "var(--input-bg)", color: "var(--text)", border: "1px solid var(--border-strong)",
                  borderRadius: 8, padding: "9px 12px", fontSize: 13, fontFamily: "var(--font-ui)",
                }}
              >
                {ARTICLE_TYPES.map(t => <option key={t.id} value={t.id} style={{ color: "#000" }}>{t.label}</option>)}
              </select>
              <Btn onClick={handleRunWorkflow} disabled={!canRun} size="lg">
                {dispatching ? <><Spinner size={13} /> Starting…</> : "▶ Run Workflow"}
              </Btn>
              {gh?.ok && (
                <a href={gh.actions_url} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "var(--text-3)" }}>
                  Open Actions tab ↗
                </a>
              )}
            </div>

            {dispatchError && (
              <div style={{ marginTop: 12, padding: "10px 12px", background: "var(--red-subtle)", border: "1px solid var(--red-border)", borderRadius: 8 }}>
                <p style={{ margin: 0, fontSize: 13, color: "var(--red)" }}>{dispatchError}</p>
              </div>
            )}
          </Card>
        )}

        {/* ── Live run ── */}
        {dispatch && (
          <Card style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Label style={{ margin: 0 }}>Workflow run {dispatch.run_id ? `#${dispatch.run_id}` : ""}</Label>
                {runBadge(run)}
                {run && <Badge color="gray" size="xs">{fmtDuration(runElapsed)}</Badge>}
              </div>
              <div style={{ display: "flex", gap: 12 }}>
                {dispatch.publish?.commit_url && (
                  <a href={dispatch.publish.commit_url} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "var(--text-3)" }}>DNA commit ↗</a>
                )}
                {run?.html_url && (
                  <a href={run.html_url} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "var(--accent)", fontWeight: 600 }}>View on GitHub Actions ↗</a>
                )}
              </div>
            </div>

            <p style={{ margin: "0 0 12px", fontSize: 12, color: "var(--text-3)" }}>
              DNA {dispatch.publish?.changed ? "committed" : "already up to date"} on {dispatch.repo}@{dispatch.branch}
              {!dispatch.run_id && " · waiting for GitHub to start the run…"}
            </p>

            {run?.steps?.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {run.steps.map(s => (
                  <div key={s.name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <StateIcon state={stepState(s)} />
                    <span style={{ fontSize: 13, color: stepState(s) === "idle" ? "var(--text-3)" : "var(--text)" }}>{STEP_LABELS[s.name] || s.name}</span>
                    {s.started_at && s.completed_at && (
                      <span style={{ fontSize: 11, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>
                        {fmtDuration((Date.parse(s.completed_at) - Date.parse(s.started_at)) / 1000)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {runError && <p style={{ margin: "12px 0 0", fontSize: 12, color: "var(--red)" }}>{runError}</p>}
            {run?.status === "completed" && !runFinished && (
              <p style={{ margin: "12px 0 0", fontSize: 12, color: "var(--text-3)", display: "flex", gap: 8, alignItems: "center" }}>
                <Spinner size={12} /> Reading the committed run log from the repo…
              </p>
            )}
          </Card>
        )}

        {/* ── Results ── */}
        {outputs?.entries?.length > 0 && (
          <Card style={{ marginBottom: 16 }}>
            <Label>4 · Pipeline stages (from the committed run log)</Label>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "var(--text-3)", fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.06em" }}>
                    <th style={{ padding: "6px 8px" }}>STAGE</th>
                    <th style={{ padding: "6px 8px" }}>MODEL</th>
                    <th style={{ padding: "6px 8px" }}>DETAIL</th>
                  </tr>
                </thead>
                <tbody>
                  {outputs.entries.map(e => (
                    <tr key={e.stage} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: "8px", whiteSpace: "nowrap" }}>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                          <StateIcon state={stageState(e.status)} size={16} />
                          <span style={{ color: "var(--text)", fontFamily: "var(--font-mono)" }}>{e.stage}</span>
                        </span>
                      </td>
                      <td style={{ padding: "8px", color: "var(--text-2)", whiteSpace: "nowrap" }}>{e.model_used || "—"}</td>
                      <td style={{ padding: "8px", color: e.error ? "var(--red)" : "var(--text-2)", lineHeight: 1.5 }}>{e.detail || e.error}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {run?.status === "completed" && runFinished && !outputs?.entries?.length && (
          <Card style={{ marginBottom: 16, borderColor: run.conclusion === "success" ? "var(--border)" : "var(--red-border)" }}>
            <p style={{ margin: 0, fontSize: 13, color: run.conclusion === "success" ? "var(--text-2)" : "var(--red)" }}>
              {run.conclusion === "success"
                ? (outputs?.message || "Run finished, but its run log was not found in the repo.")
                : "The workflow run failed. Open it on GitHub Actions to see the log."}
            </p>
          </Card>
        )}

        {article && (
          <Card style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <Label style={{ margin: 0 }}>Article</Label>
                {article.meta.seo_score && <Badge color="blue">SEO {article.meta.seo_score}</Badge>}
                {article.meta.aeo_score && <Badge color="purple">AEO {article.meta.aeo_score}</Badge>}
                {article.meta.geo_score && <Badge color="amber">GEO {article.meta.geo_score}</Badge>}
                {article.meta.word_count && <Badge color="gray">{article.meta.word_count} words</Badge>}
                {article.meta.model_used && <Badge color="gray">{article.meta.model_used}</Badge>}
              </div>
              <a href={article.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "var(--accent)", fontWeight: 600 }}>View file on GitHub ↗</a>
            </div>
            <p style={{ margin: "0 0 12px", fontSize: 11, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>
              {article.path} · run <code>git pull</code> to get these files locally
            </p>
            <div
              className="art-body"
              style={{ maxHeight: 560, overflowY: "auto", padding: "4px 6px" }}
              dangerouslySetInnerHTML={{ __html: renderMd(escapeHtml(article.markdown)) }}
            />
          </Card>
        )}

        {/* ── Recent runs (same list as the Actions tab) ── */}
        {recent.length > 0 && (
          <Card>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <Label style={{ margin: 0 }}>Recent daily-article runs</Label>
              <Btn variant="ghost" size="sm" onClick={refreshRecent}>Refresh</Btn>
            </div>
            {recent.map(r => (
              <a key={r.id} href={r.html_url} target="_blank" rel="noreferrer" style={{
                display: "flex", alignItems: "center", gap: 10, padding: "8px 4px",
                borderTop: "1px solid var(--border)", textDecoration: "none",
              }}>
                {runBadge(r)}
                <span style={{ fontSize: 13, color: "var(--text)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.title}</span>
                <span style={{ fontSize: 11, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>{r.event}</span>
                <span style={{ fontSize: 11, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>{new Date(r.created_at).toLocaleString()}</span>
              </a>
            ))}
          </Card>
        )}
      </main>
    </div>
  );
}
