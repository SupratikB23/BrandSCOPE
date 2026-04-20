import { useState, useEffect } from 'react';
import { Badge, TypewriterText } from './components';

export default function LandingPage({ onEnter }) {
  const [vis, setVis] = useState(false);
  useEffect(() => { setTimeout(() => setVis(true), 80); }, []);

  const features = [
    { label: "Brand DNA", desc: "Deep company profiling via Playwright + spaCy NLP", step: "01" },
    { label: "Trend Research", desc: "Google News · DuckDuckGo · Reddit — live, free", step: "02" },
    { label: "Brief Builder", desc: "Gap analysis + SEO / AEO / GEO signal scoring", step: "03" },
    { label: "Article Writer", desc: "Gemini free tier — voice-matched output", step: "04" },
  ];

  return (
    <div style={{
      minHeight: "100vh", background: "var(--bg)",
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", padding: "48px 24px", position: "relative", overflow: "hidden",
    }}>
      <div style={{
        position: "absolute", top: "15%", left: "50%", transform: "translateX(-50%)",
        width: 700, height: 400, pointerEvents: "none", zIndex: 0,
        background: "radial-gradient(ellipse, var(--accent-glow-bg) 0%, transparent 65%)",
      }} />

      <div style={{
        position: "relative", zIndex: 1, textAlign: "center", maxWidth: 680,
        opacity: vis ? 1 : 0, transform: vis ? "none" : "translateY(20px)",
        transition: "opacity 0.7s ease, transform 0.7s ease",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10, marginBottom: 44 }}>
          <div style={{
            width: 34, height: 34, borderRadius: 9,
            background: "var(--accent)", display: "flex", alignItems: "center",
            justifyContent: "center", fontSize: 16, fontWeight: 800, color: "#fff",
          }}>S</div>
          <span style={{ fontSize: 16, fontWeight: 700, color: "var(--text)", letterSpacing: "-0.02em" }}>SearchOS</span>
          <Badge color="green">v1.0 Free</Badge>
        </div>

        <h1 style={{ margin: "0 0 6px", lineHeight: 1.06, letterSpacing: "-0.03em" }}>
          <span style={{ display: "block", fontSize: "clamp(36px,5.5vw,64px)", fontWeight: 800, color: "var(--text)" }}>
            Personal Brand
          </span>
          <span style={{
            display: "block", fontSize: "clamp(36px,5.5vw,64px)", fontWeight: 800,
            color: "var(--accent)",
          }}>
            Search Optimizer
          </span>
        </h1>

        <p style={{
          margin: "22px 0 0", fontSize: 18, color: "var(--text-2)",
          fontFamily: "var(--font-mono)", minHeight: 30, letterSpacing: "-0.01em",
        }}>
          <TypewriterText phrases={[
            "Writes articles that rank on Google.",
            "Structures answers for AI Overviews.",
            "Gets cited by ChatGPT & Perplexity.",
            "Sounds exactly like your brand.",
            "Zero API cost. Runs on your laptop.",
          ]} />
        </p>

        <div style={{ marginTop: 40 }}>
          <button onClick={onEnter} style={{
            background: "var(--accent)", color: "#fff",
            border: "none", borderRadius: 10, padding: "13px 32px",
            fontSize: 15, fontWeight: 700, cursor: "pointer",
            fontFamily: "var(--font-ui)", letterSpacing: "-0.01em",
            transition: "all 0.18s",
            boxShadow: "0 4px 20px var(--accent-glow)",
            display: "inline-flex", alignItems: "center", gap: 10,
          }}
            onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "0 8px 28px var(--accent-glow)"; }}
            onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = "0 4px 20px var(--accent-glow)"; }}
          >
            Open the Engine
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
              <path d="M2 7.5h11M9 3.5l4 4-4 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 52, textAlign: "left" }}>
          {features.map((f, i) => (
            <div key={f.step} style={{
              padding: "16px 18px", borderRadius: 10,
              background: "var(--surface)", border: "1px solid var(--border)",
              opacity: vis ? 1 : 0, transition: `opacity 0.5s ease ${0.3 + i * 0.1}s`,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: "var(--accent)", fontFamily: "var(--font-mono)", letterSpacing: "0.1em" }}>
                  ENGINE {f.step}
                </span>
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", marginBottom: 3 }}>{f.label}</div>
              <div style={{ fontSize: 12, color: "var(--text-3)", lineHeight: 1.5 }}>{f.desc}</div>
            </div>
          ))}
        </div>

        <p style={{ marginTop: 28, fontSize: 12, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>
          100% free · Gemini API key optional · runs on localhost
        </p>
      </div>
    </div>
  );
}
