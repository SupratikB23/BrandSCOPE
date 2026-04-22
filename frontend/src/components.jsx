import { useState, useEffect, useRef } from 'react';

export function Badge({ children, color = "blue", size = "sm" }) {
  const colors = {
    blue:   { bg: "var(--badge-blue-bg)",   color: "var(--badge-blue-fg)",   border: "var(--badge-blue-border)"   },
    amber:  { bg: "var(--badge-amber-bg)",  color: "var(--badge-amber-fg)",  border: "var(--badge-amber-border)"  },
    green:  { bg: "var(--badge-green-bg)",  color: "var(--badge-green-fg)",  border: "var(--badge-green-border)"  },
    red:    { bg: "var(--badge-red-bg)",    color: "var(--badge-red-fg)",    border: "var(--badge-red-border)"    },
    purple: { bg: "var(--badge-purple-bg)", color: "var(--badge-purple-fg)", border: "var(--badge-purple-border)" },
    gray:   { bg: "var(--badge-gray-bg)",   color: "var(--badge-gray-fg)",   border: "var(--badge-gray-border)"   },
  };
  const c = colors[color] || colors.gray;
  return (
    <span style={{
      background: c.bg, color: c.color, border: `1px solid ${c.border}`,
      borderRadius: 5, padding: size === "xs" ? "1px 6px" : "2px 8px",
      fontSize: size === "xs" ? 10 : 11, fontWeight: 600,
      fontFamily: "var(--font-mono)", letterSpacing: "0.02em",
      display: "inline-flex", alignItems: "center", gap: 4, whiteSpace: "nowrap",
    }}>{children}</span>
  );
}

export function Tag({ children, onClick, active }) {
  return (
    <span onClick={onClick} style={{
      background: active ? "var(--accent-subtle)" : "var(--surface-2)",
      color: active ? "var(--accent)" : "var(--text-3)",
      border: `1px solid ${active ? "var(--accent-border)" : "var(--border)"}`,
      borderRadius: 6, padding: "3px 10px", fontSize: 12, fontWeight: 500,
      cursor: onClick ? "pointer" : "default", transition: "all 0.15s",
      display: "inline-block", userSelect: "none",
    }}>{children}</span>
  );
}

export function Card({ children, style, onClick, hover, glass }) {
  const [hov, setHov] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => (hover || onClick) && setHov(true)}
      onMouseLeave={() => (hover || onClick) && setHov(false)}
      style={{
        background: glass ? "var(--glass-bg)" : "var(--surface)",
        border: `1px solid ${hov ? "var(--border-hover)" : "var(--border)"}`,
        borderRadius: 12, padding: 20,
        transition: "border-color 0.2s, box-shadow 0.2s, transform 0.2s",
        cursor: onClick ? "pointer" : "default",
        boxShadow: hov ? "var(--shadow-hover)" : "var(--shadow)",
        transform: hov && onClick ? "translateY(-2px)" : "none",
        backdropFilter: "var(--card-backdrop)",
        WebkitBackdropFilter: "var(--card-backdrop)",
        ...style,
      }}
    >{children}</div>
  );
}

export function ScoreRing({ score, label, variant = "blue", size = 90 }) {
  const r = size / 2 - 9;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;
  const colors = { blue: "var(--accent)", purple: "var(--purple)", amber: "var(--amber)" };
  const c = colors[variant] || colors.blue;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
          <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={7} />
          <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={c} strokeWidth={7}
            strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
            style={{ transition: "stroke-dasharray 1.2s cubic-bezier(.4,0,.2,1)" }} />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
          <span style={{ fontSize: 22, fontWeight: 800, color: c, lineHeight: 1, fontFamily: "var(--font-display)" }}>{score}</span>
          <span style={{ fontSize: 8, color: "var(--text-4)", marginTop: 2, fontFamily: "var(--font-mono)", letterSpacing: "0.05em" }}>/100</span>
        </div>
      </div>
      <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.1em", textTransform: "uppercase", fontFamily: "var(--font-mono)" }}>{label}</span>
    </div>
  );
}

export function Btn({ children, onClick, variant = "primary", disabled, style, size = "md" }) {
  const [hov, setHov] = useState(false);
  const pad = { sm: "5px 12px", md: "8px 16px", lg: "11px 24px" }[size] || "8px 16px";
  const fs  = { sm: 12, md: 13, lg: 14 }[size] || 13;
  const variants = {
    primary: { bg: hov ? "var(--accent-hover)" : "var(--accent)", color: "#fff", border: "transparent", shadow: hov ? "0 4px 16px var(--accent-glow)" : "none" },
    ghost:   { bg: hov ? "var(--surface-2)" : "transparent", color: hov ? "var(--text)" : "var(--text-2)", border: "var(--border)", shadow: "none" },
    danger:  { bg: hov ? "var(--red-subtle-hover)" : "var(--red-subtle)", color: "var(--red)", border: "var(--red-border)", shadow: "none" },
  };
  const v = variants[variant] || variants.primary;
  return (
    <button onClick={onClick} disabled={disabled}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{
        background: disabled ? "var(--surface-2)" : v.bg,
        color: disabled ? "var(--text-4)" : v.color,
        border: `1px solid ${v.border}`, borderRadius: 8,
        padding: pad, fontSize: fs, fontWeight: 600,
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "all 0.15s", display: "inline-flex", alignItems: "center",
        gap: 6, whiteSpace: "nowrap", fontFamily: "var(--font-ui)",
        boxShadow: disabled ? "none" : v.shadow, ...style,
      }}>{children}</button>
  );
}

export function Input({ value, onChange, placeholder, prefix, style, onKeyDown, type = "text" }) {
  const [focused, setFocused] = useState(false);
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8,
      background: "var(--input-bg)",
      border: `1px solid ${focused ? "var(--accent)" : "var(--border-strong)"}`,
      borderRadius: 8, padding: "9px 13px",
      transition: "border-color 0.15s", boxShadow: focused ? "0 0 0 3px var(--accent-ring)" : "none",
      ...style,
    }}>
      {prefix && <span style={{ color: "var(--text-4)", fontSize: 14, flexShrink: 0 }}>{prefix}</span>}
      <input value={value} onChange={e => onChange(e.target.value)}
        placeholder={placeholder} onKeyDown={onKeyDown} type={type}
        onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
        style={{ background: "none", border: "none", outline: "none", color: "var(--text)", fontSize: 14, flex: 1, fontFamily: "var(--font-ui)" }} />
    </div>
  );
}

export function ProgressBar({ value, variant = "blue", label, showPct }) {
  const colors = { blue: "var(--accent)", green: "var(--green)", amber: "var(--amber)" };
  const c = colors[variant] || colors.blue;
  return (
    <div>
      {(label || showPct) && (
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
          {label && <span style={{ fontSize: 12, color: "var(--text-2)" }}>{label}</span>}
          {showPct && <span style={{ fontSize: 11, color: c, fontFamily: "var(--font-mono)" }}>{value}%</span>}
        </div>
      )}
      <div style={{ background: "var(--surface-3)", borderRadius: 99, height: 4, overflow: "hidden" }}>
        <div style={{ width: `${value}%`, height: "100%", background: c, borderRadius: 99, transition: "width 0.8s ease" }} />
      </div>
    </div>
  );
}

export function Spinner({ size = 16, color }) {
  return (
    <div style={{
      width: size, height: size,
      border: `1.5px solid var(--surface-3)`,
      borderTopColor: color || "var(--accent)",
      borderRadius: "50%",
      animation: "spin 0.65s linear infinite",
      flexShrink: 0,
    }} />
  );
}

export function SectionHeader({ step, title, subtitle }) {
  return (
    <div className="fade-up" style={{ marginBottom: 32 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase",
          color: "var(--accent)", fontFamily: "var(--font-mono)",
        }}>Engine {step}</span>
        <div style={{ width: 28, height: 1, background: "var(--border-strong)", borderRadius: 99 }} />
      </div>
      <h1 className="gradient-text" style={{
        fontSize: 28, fontWeight: 800, margin: 0,
        lineHeight: 1.18, letterSpacing: "-0.03em",
        fontFamily: "var(--font-display)",
      }}>{title}</h1>
      {subtitle && <p style={{
        fontSize: 14, color: "var(--text-2)",
        margin: "10px 0 0", lineHeight: 1.7,
        maxWidth: 600, fontFamily: "var(--font-ui)",
      }}>{subtitle}</p>}
    </div>
  );
}

export function TypewriterText({ phrases, speed = 55, pause = 2400 }) {
  const [displayed, setDisplayed] = useState("");
  const [phraseIdx, setPhraseIdx] = useState(0);
  const [charIdx, setCharIdx]     = useState(0);
  const [deleting, setDeleting]   = useState(false);
  useEffect(() => {
    const phrase = phrases[phraseIdx];
    let t;
    if (!deleting) {
      if (charIdx < phrase.length) t = setTimeout(() => setCharIdx(i => i + 1), speed);
      else t = setTimeout(() => setDeleting(true), pause);
    } else {
      if (charIdx > 0) t = setTimeout(() => setCharIdx(i => i - 1), speed / 2.5);
      else { setDeleting(false); setPhraseIdx(i => (i + 1) % phrases.length); }
    }
    setDisplayed(phrase.slice(0, charIdx));
    return () => clearTimeout(t);
  }, [charIdx, deleting, phraseIdx, phrases, speed, pause]);
  return (
    <span>
      {displayed}
      <span style={{ display: "inline-block", width: 2, height: "0.9em", background: "var(--accent)", marginLeft: 1, verticalAlign: "text-bottom", animation: "blink 1s step-end infinite" }} />
    </span>
  );
}

export function Divider({ style }) {
  return <div style={{ height: 1, background: "var(--border)", ...style }} />;
}

export function StatRow({ label, value, color }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid var(--border)" }}>
      <span style={{ fontSize: 13, color: "var(--text-2)" }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 700, color: color || "var(--text)", fontFamily: "var(--font-mono)" }}>{value}</span>
    </div>
  );
}
