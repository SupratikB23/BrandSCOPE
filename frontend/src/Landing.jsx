import { useState, useEffect } from 'react';
import { Badge, TypewriterText } from './components';

// SVG flowing paths — GPU-efficient alternative to blurred gradient orbs
function FloatingPaths({ position }) {
  const paths = Array.from({ length: 36 }, (_, i) => ({
    id: i,
    d: `M-${380 - i * 5 * position} -${189 + i * 6}C-${380 - i * 5 * position} -${189 + i * 6} -${312 - i * 5 * position} ${216 - i * 6} ${152 - i * 5 * position} ${343 - i * 6}C${616 - i * 5 * position} ${470 - i * 6} ${684 - i * 5 * position} ${875 - i * 6} ${684 - i * 5 * position} ${875 - i * 6}`,
    width: 0.5 + i * 0.03,
    opacity: 0.08 + i * 0.022,
    duration: 22 + i * 0.45,
    delay: -(i * 0.72),
  }));

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      <svg
        style={{ width: "100%", height: "100%", color: "currentColor" }}
        viewBox="0 0 696 316"
        fill="none"
        preserveAspectRatio="xMidYMid slice"
      >
        {paths.map(p => (
          <path
            key={p.id}
            d={p.d}
            stroke="currentColor"
            strokeWidth={p.width}
            strokeOpacity={p.opacity}
            style={{
              strokeDasharray: 2200,
              strokeDashoffset: 2200,
              animation: `pathFlow ${p.duration}s linear ${p.delay}s infinite`,
            }}
          />
        ))}
      </svg>
    </div>
  );
}

// Per-character drop animation for the main headline
function AnimatedTitle({ title }) {
  const words = title.split(" ");
  return (
    <h1 style={{
      margin: "0 0 10px",
      lineHeight: 1.02,
      letterSpacing: "-0.04em",
      fontFamily: "var(--font-display)",
      fontWeight: 800,
    }}>
      {words.map((word, wi) => (
        <span key={wi} style={{ display: "inline-block", marginRight: "0.28em" }}>
          {word.split("").map((letter, li) => (
            <span
              key={`${wi}-${li}`}
              style={{
                display: "inline-block",
                animation: "letterDrop 0.65s cubic-bezier(0.22,1,0.36,1) both",
                animationDelay: `${wi * 0.12 + li * 0.032}s`,
                fontSize: "clamp(44px, 7vw, 80px)",
                background: "var(--title-gradient)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              {letter}
            </span>
          ))}
        </span>
      ))}
    </h1>
  );
}

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

      {/* SVG flowing paths — two mirrored layers for depth */}
      <div style={{ position: "absolute", inset: 0, color: "var(--text-4)", zIndex: 0 }}>
        <FloatingPaths position={1} />
        <FloatingPaths position={-1} />
      </div>

      {/* Atmospheric orbs — smaller + lighter blur than before */}
      <div style={{
        position: "absolute",
        top: "8%", left: "5%",
        width: 360, height: 360,
        borderRadius: "50%",
        background: "radial-gradient(circle, var(--orb-1) 0%, transparent 70%)",
        filter: "blur(40px)",
        animation: "float-a 10s ease-in-out infinite",
        pointerEvents: "none", zIndex: 0,
        willChange: "transform",
      }} />
      <div style={{
        position: "absolute",
        bottom: "5%", right: "3%",
        width: 300, height: 300,
        borderRadius: "50%",
        background: "radial-gradient(circle, var(--orb-2) 0%, transparent 70%)",
        filter: "blur(35px)",
        animation: "float-b 13s ease-in-out infinite",
        pointerEvents: "none", zIndex: 0,
        willChange: "transform",
      }} />

      {/* Main content */}
      <div style={{
        position: "relative",
        zIndex: 1,
        textAlign: "center",
        maxWidth: 700,
        width: "100%",
        padding: "60px 28px",
        opacity: vis ? 1 : 0,
        transition: "opacity 0.9s cubic-bezier(0.22,1,0.36,1)",
      }}>

        {/* Logo row */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "center",
          gap: 10, marginBottom: 52,
        }} className="fade-up">
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

        {/* Animated per-character headline */}
        <AnimatedTitle title="Personal Brand Search Optimizer" />

        {/* Typewriter subtitle */}
        <p style={{
          margin: "28px 0 0",
          fontSize: 17,
          color: "var(--text-2)",
          fontFamily: "var(--font-mono)",
          minHeight: 30,
          letterSpacing: "-0.01em",
          lineHeight: 1.5,
          opacity: vis ? 1 : 0,
          transition: "opacity 0.8s 0.4s",
        }}>
          <TypewriterText phrases={[
            "Writes articles that rank on Google.",
            "Structures answers for AI Overviews.",
            "Gets cited by ChatGPT & Perplexity.",
            "Sounds exactly like your brand.",
            "Zero API cost. Runs on your laptop.",
          ]} />
        </p>

        {/* CTA — glassmorphic wrapper */}
        <div style={{
          marginTop: 44,
          opacity: vis ? 1 : 0,
          transform: vis ? "none" : "translateY(16px)",
          transition: "opacity 0.7s 0.5s, transform 0.7s 0.5s",
        }}>
          <div style={{
            display: "inline-block",
            background: "linear-gradient(to bottom, rgba(255,255,255,0.1), rgba(255,255,255,0.04))",
            padding: "1px", borderRadius: 18,
            backdropFilter: "blur(12px)",
            boxShadow: "0 8px 32px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.08)",
          }}>
            <button
              onClick={onEnter}
              style={{
                borderRadius: 16, padding: "14px 36px",
                fontSize: 15, fontWeight: 700,
                letterSpacing: "-0.01em",
                fontFamily: "var(--font-display)",
                background: "var(--accent)",
                color: "#fff",
                border: "1px solid var(--accent-border)",
                cursor: "pointer",
                display: "inline-flex", alignItems: "center", gap: 11,
                transition: "all 0.25s cubic-bezier(0.22,1,0.36,1)",
              }}
              onMouseEnter={e => {
                e.currentTarget.style.transform = "translateY(-2px)";
                e.currentTarget.style.background = "var(--accent-hover)";
                e.currentTarget.style.boxShadow = "0 0 28px var(--accent-glow)";
              }}
              onMouseLeave={e => {
                e.currentTarget.style.transform = "";
                e.currentTarget.style.background = "var(--accent)";
                e.currentTarget.style.boxShadow = "";
              }}
            >
              Open the Engine
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
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
              <div style={{
                position: "absolute", top: 0, left: 0, right: 0,
                height: 1,
                background: `linear-gradient(90deg, transparent, ${f.color}44, transparent)`,
              }} />
              <div style={{
                fontSize: 9, fontWeight: 700,
                color: f.color,
                fontFamily: "var(--font-mono)",
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                opacity: 0.8,
                marginBottom: 8,
              }}>
                ENGINE {f.step}
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
          opacity: vis ? 1 : 0,
          transition: "opacity 0.6s 0.8s",
        }}>
          100% free · Gemini + Groq API · runs on localhost
        </p>
      </div>
    </div>
  );
}
