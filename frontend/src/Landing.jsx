import { useState, useEffect } from 'react';
import { Badge, TypewriterText } from './components';

export default function LandingPage({ onEnter }) {
  const [vis, setVis] = useState(false);
  useEffect(() => { const t = setTimeout(() => setVis(true), 60); return () => clearTimeout(t); }, []);

  const features = [
    { label: "Brand DNA",      desc: "Playwright + spaCy NLP — deep voice profiling",          step: "01", color: "#7C3AED" },
    { label: "Trend Research", desc: "Google News · DuckDuckGo · Reddit — zero API cost",       step: "02", color: "#00E5FF" },
    { label: "Brief Builder",  desc: "Gap analysis + SEO / AEO / GEO signal scoring",           step: "03", color: "#FFB020" },
    { label: "Article Writer", desc: "Gemini + Groq fallback — sounds exactly like your brand", step: "04", color: "#00FF88" },
  ];

  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--bg)",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      padding: "48px 24px",
      position: "relative",
      overflow: "hidden",
    }}>

      {/* ── Floating orbs (dramatic in dark, subtle in light) ── */}
      <div style={{
        position: "absolute",
        top: "8%", left: "5%",
        width: 500, height: 500,
        borderRadius: "50%",
        background: `radial-gradient(circle, var(--orb-1) 0%, transparent 70%)`,
        filter: "blur(60px)",
        animation: "float-slow 9s ease-in-out infinite",
        pointerEvents: "none", zIndex: 0,
      }} />
      <div style={{
        position: "absolute",
        bottom: "5%", right: "3%",
        width: 420, height: 420,
        borderRadius: "50%",
        background: `radial-gradient(circle, var(--orb-2) 0%, transparent 70%)`,
        filter: "blur(50px)",
        animation: "float-medium 12s ease-in-out infinite",
        pointerEvents: "none", zIndex: 0,
      }} />
      <div style={{
        position: "absolute",
        top: "45%", right: "18%",
        width: 280, height: 280,
        borderRadius: "50%",
        background: `radial-gradient(circle, var(--orb-3) 0%, transparent 70%)`,
        filter: "blur(45px)",
        animation: "float-fast 7s ease-in-out infinite",
        pointerEvents: "none", zIndex: 0,
      }} />

      {/* ── Content ── */}
      <div style={{
        position: "relative",
        zIndex: 1,
        textAlign: "center",
        maxWidth: 700,
        width: "100%",
        opacity: vis ? 1 : 0,
        transform: vis ? "none" : "translateY(24px)",
        transition: "opacity 0.8s cubic-bezier(0.22,1,0.36,1), transform 0.8s cubic-bezier(0.22,1,0.36,1)",
      }}>

        {/* Logo row */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "center",
          gap: 10, marginBottom: 52,
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: "var(--accent)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 17, fontWeight: 800, color: "#fff",
            fontFamily: "var(--font-display)",
            boxShadow: "0 0 20px var(--accent-glow)",
          }}>S</div>
          <span style={{
            fontSize: 17, fontWeight: 700,
            color: "var(--text)",
            letterSpacing: "-0.03em",
            fontFamily: "var(--font-display)",
          }}>SearchOS</span>
          <Badge color="green">v1.0 Free</Badge>
        </div>

        {/* Main headline */}
        <h1 style={{
          margin: "0 0 8px",
          lineHeight: 1.02,
          letterSpacing: "-0.04em",
          fontFamily: "var(--font-display)",
        }}>
          <span style={{
            display: "block",
            fontSize: "clamp(44px, 7vw, 80px)",
            fontWeight: 800,
            color: "var(--text)",
          }}>
            Personal Brand
          </span>
          <span
            className="gradient-text"
            style={{
              display: "block",
              fontSize: "clamp(44px, 7vw, 80px)",
              fontWeight: 800,
            }}
          >
            Search Optimizer
          </span>
        </h1>

        {/* Typewriter subtitle */}
        <p style={{
          margin: "28px 0 0",
          fontSize: 17,
          color: "var(--text-2)",
          fontFamily: "var(--font-mono)",
          minHeight: 30,
          letterSpacing: "-0.01em",
          lineHeight: 1.5,
        }}>
          <TypewriterText phrases={[
            "Writes articles that rank on Google.",
            "Structures answers for AI Overviews.",
            "Gets cited by ChatGPT & Perplexity.",
            "Sounds exactly like your brand.",
            "Zero API cost. Runs on your laptop.",
          ]} />
        </p>

        {/* CTA Button */}
        <div style={{ marginTop: 44 }}>
          <button
            onClick={onEnter}
            className="glow-btn"
            style={{
              background: "var(--accent)",
              color: "#fff",
              border: "1px solid var(--accent-border)",
              borderRadius: 12,
              padding: "14px 36px",
              fontSize: 15,
              fontWeight: 700,
              cursor: "pointer",
              fontFamily: "var(--font-display)",
              letterSpacing: "-0.01em",
              transition: "all 0.2s cubic-bezier(0.22,1,0.36,1)",
              boxShadow: "0 4px 24px var(--accent-glow)",
              display: "inline-flex",
              alignItems: "center",
              gap: 11,
            }}
            onMouseEnter={e => {
              e.currentTarget.style.transform = "translateY(-3px) scale(1.02)";
              e.currentTarget.style.boxShadow = "0 8px 40px var(--accent-glow), 0 0 60px rgba(124,58,237,0.2)";
              e.currentTarget.style.background = "var(--accent-hover)";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.transform = "";
              e.currentTarget.style.boxShadow = "0 4px 24px var(--accent-glow)";
              e.currentTarget.style.background = "var(--accent)";
            }}
          >
            Open the Engine
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>

        {/* Feature cards */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 10,
          marginTop: 56,
          textAlign: "left",
        }}>
          {features.map((f, i) => (
            <div
              key={f.step}
              style={{
                padding: "18px 20px",
                borderRadius: 14,
                background: "var(--surface)",
                border: "1px solid var(--border)",
                backdropFilter: "var(--card-backdrop)",
                WebkitBackdropFilter: "var(--card-backdrop)",
                opacity: vis ? 1 : 0,
                transform: vis ? "none" : "translateY(12px)",
                transition: `opacity 0.6s cubic-bezier(0.22,1,0.36,1) ${0.28 + i * 0.07}s, transform 0.6s cubic-bezier(0.22,1,0.36,1) ${0.28 + i * 0.07}s, border-color 0.2s`,
                cursor: "default",
                position: "relative",
                overflow: "hidden",
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = "var(--border-hover)";
                e.currentTarget.style.boxShadow = "var(--shadow-hover)";
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = "var(--border)";
                e.currentTarget.style.boxShadow = "none";
              }}
            >
              {/* Subtle accent line at top */}
              <div style={{
                position: "absolute", top: 0, left: 0, right: 0,
                height: 1,
                background: `linear-gradient(90deg, transparent, ${f.color}44, transparent)`,
              }} />

              <div style={{
                display: "flex", alignItems: "center", gap: 7, marginBottom: 8,
              }}>
                <span style={{
                  fontSize: 9, fontWeight: 700,
                  color: f.color,
                  fontFamily: "var(--font-mono)",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  opacity: 0.8,
                }}>
                  ENGINE {f.step}
                </span>
              </div>
              <div style={{
                fontSize: 13, fontWeight: 700,
                color: "var(--text)",
                marginBottom: 4,
                fontFamily: "var(--font-display)",
                letterSpacing: "-0.01em",
              }}>{f.label}</div>
              <div style={{
                fontSize: 11,
                color: "var(--text-3)",
                lineHeight: 1.55,
                fontFamily: "var(--font-ui)",
              }}>{f.desc}</div>
            </div>
          ))}
        </div>

        <p style={{
          marginTop: 32,
          fontSize: 11,
          color: "var(--text-4)",
          fontFamily: "var(--font-mono)",
          letterSpacing: "0.03em",
        }}>
          100% free · Gemini + Groq API · runs on localhost
        </p>
      </div>
    </div>
  );
}
