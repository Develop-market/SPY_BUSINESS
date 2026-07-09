// SGCI Strategic Intelligence — v2 components.
// Far richer visual personality: gradient hero, circular icon badges, mixed bar
// charts, donut, ranking rows with progress + status pills, hex pattern.

const { useState, useMemo, useRef, useEffect } = React;

/* =========================================================================
   ATOMS
   ========================================================================= */

const HexPattern = ({ opacity = 0.15, color = "#E4002B", size = 80, count = 8, style }) => (
  <svg viewBox={`0 0 ${size * count} ${size * 1.4}`} preserveAspectRatio="xMaxYMin slice"
    style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", opacity, ...style }}>
    <defs>
      <pattern id="hex" width={size * 0.866 * 2} height={size * 1.5} patternUnits="userSpaceOnUse">
        <polygon points={`${size*0.866},0 ${size*1.732},${size*0.5} ${size*1.732},${size*1.5} ${size*0.866},${size*2} 0,${size*1.5} 0,${size*0.5}`}
          fill="none" stroke={color} strokeWidth="1.2"/>
        <polygon points={`${size*0.866},${size*0.4} ${size*1.5},${size*0.75} ${size*1.5},${size*1.25} ${size*0.866},${size*1.6} ${size*0.232},${size*1.25} ${size*0.232},${size*0.75}`}
          fill="none" stroke={color} strokeWidth="1.2" opacity="0.6"/>
      </pattern>
    </defs>
    <rect width="100%" height="100%" fill="url(#hex)"/>
  </svg>
);

const BankLogo = ({ bank, size = 24 }) => (
  <span style={{
    width: size, height: size, background: "#fff",
    borderRadius: size <= 20 ? 4 : 6,
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    overflow: "hidden", flexShrink: 0,
    boxShadow: "0 1px 0 rgba(255,255,255,0.08), 0 2px 6px rgba(0,0,0,0.3)",
  }}>
    <img src={bank.logo} alt={bank.short}
      style={{ width: size * 0.78, height: size * 0.78, objectFit: "contain" }}/>
  </span>
);

const StatusPill = ({ kind, children }) => {
  const map = {
    leader:    { bg: "linear-gradient(135deg, #E4002B, #B11226)", fg: "#fff", glow: "rgba(228,0,43,0.45)" },
    follower:  { bg: "rgba(56,189,248,0.14)", fg: "#7DD3FC", glow: "rgba(56,189,248,0.20)" },
    pressure:  { bg: "rgba(245,158,11,0.16)", fg: "#FCD34D", glow: "rgba(245,158,11,0.20)" },
    risk:      { bg: "rgba(239,68,68,0.16)",  fg: "#FCA5A5", glow: "rgba(239,68,68,0.20)" },
    gain:      { bg: "rgba(34,197,94,0.16)",  fg: "#86EFAC", glow: "rgba(34,197,94,0.20)" },
    neutral:   { bg: "var(--bg-3)",           fg: "var(--fg-2)", glow: "transparent" },
  }[kind] || { bg: "var(--bg-3)", fg: "var(--fg-2)", glow: "transparent" };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      font: "600 10.5px/1 var(--font-sans)", letterSpacing: "0.04em",
      padding: "5px 9px", borderRadius: 999,
      background: map.bg, color: map.fg,
      boxShadow: map.glow !== "transparent" ? `0 0 0 1px ${map.glow}` : "none",
      textTransform: "uppercase",
    }}>{children}</span>
  );
};

const Sparkline = ({ values, color = "#E4002B", width = 84, height = 28, area = true }) => {
  if (!values || values.length < 2) return null;
  const max = Math.max(...values), min = Math.min(...values);
  const step = width / (values.length - 1);
  const y = v => height - ((v - min) / (max - min || 1)) * (height - 6) - 3;
  const path = values.map((v, i) => `${i === 0 ? "M" : "L"} ${i * step} ${y(v)}`).join(" ");
  const id = "spark-" + Math.random().toString(36).slice(2, 8);
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.50"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      {area && <path d={`${path} L ${width} ${height} L 0 ${height} Z`} fill={`url(#${id})`}/>}
      <path d={path} stroke={color} strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
      <circle cx={width} cy={y(values[values.length - 1])} r="3" fill={color} stroke="#0B1220" strokeWidth="1.5"/>
    </svg>
  );
};

const CircleIcon = ({ icon, tone = "red", size = 44 }) => {
  const tones = {
    red:   { bg: "rgba(228,0,43,0.18)",  ring: "rgba(228,0,43,0.40)",  fg: "#FCA5A5" },
    gold:  { bg: "rgba(245,158,11,0.18)", ring: "rgba(245,158,11,0.35)", fg: "#FCD34D" },
    green: { bg: "rgba(34,197,94,0.18)",  ring: "rgba(34,197,94,0.35)",  fg: "#86EFAC" },
    sky:   { bg: "rgba(56,189,248,0.18)", ring: "rgba(56,189,248,0.35)", fg: "#7DD3FC" },
    violet:{ bg: "rgba(167,139,250,0.18)", ring: "rgba(167,139,250,0.35)", fg: "#C4B5FD" },
  }[tone];
  return (
    <span style={{
      width: size, height: size, borderRadius: "50%",
      background: tones.bg, color: tones.fg,
      display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      boxShadow: `inset 0 0 0 1px ${tones.ring}, inset 0 1px 0 rgba(255,255,255,0.06)`,
    }}>
      <Icon name={icon} size={Math.round(size * 0.46)} />
    </span>
  );
};

const Chip = ({ tone = "neutral", children, dot = false, pulse = false }) => {
  const tones = {
    neutral: { bg: "var(--bg-2)",                  bd: "var(--border-1)",          fg: "var(--fg-2)" },
    live:    { bg: "rgba(34,197,94,0.10)",         bd: "rgba(34,197,94,0.35)",     fg: "#86EFAC" },
    warn:    { bg: "rgba(245,158,11,0.10)",        bd: "rgba(245,158,11,0.35)",    fg: "#FCD34D" },
    info:    { bg: "rgba(56,189,248,0.10)",        bd: "rgba(56,189,248,0.35)",    fg: "#7DD3FC" },
    brand:   { bg: "rgba(228,0,43,0.12)",          bd: "rgba(228,0,43,0.45)",      fg: "#FCA5A5" },
    solid:   { bg: "var(--sg-red-500)",            bd: "transparent",              fg: "#fff" },
  }[tone];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      font: "600 11.5px/1 var(--font-sans)",
      padding: "5px 10px", borderRadius: 999,
      background: tones.bg, border: `1px solid ${tones.bd}`, color: tones.fg,
    }}>
      {dot && <span style={{
        width: 7, height: 7, borderRadius: 999, background: "currentColor",
        animation: pulse ? "pulse 1.6s ease-out infinite" : "none",
      }}/>}
      {children}
    </span>
  );
};

const Button = ({ kind = "primary", size = "md", icon, children, onClick, disabled }) => {
  const sizes = { md: { p: "10px 16px", fs: 13, r: 8 }, sm: { p: "7px 11px", fs: 12, r: 6 } }[size];
  const kinds = {
    primary:     { bg: "linear-gradient(180deg, #FF1E45 0%, #E4002B 100%)", fg: "#fff",          bd: "transparent",
                   shadow: "0 8px 24px -8px rgba(228,0,43,0.55), inset 0 1px 0 rgba(255,255,255,0.22)" },
    secondary:   { bg: "var(--bg-3)",       fg: "var(--fg-1)",   bd: "var(--border-2)", shadow: "none" },
    ghost:       { bg: "transparent",       fg: "var(--fg-2)",   bd: "transparent",     shadow: "none" },
    glass:       { bg: "rgba(255,255,255,0.08)", fg: "#fff",     bd: "rgba(255,255,255,0.18)", shadow: "none" },
  }[kind];
  return (
    <button onClick={onClick} disabled={disabled} style={{
      display: "inline-flex", alignItems: "center", gap: 8,
      font: `700 ${sizes.fs}px/1 var(--font-sans)`,
      padding: sizes.p, borderRadius: sizes.r,
      background: kinds.bg, color: kinds.fg, border: `1px solid ${kinds.bd}`,
      boxShadow: kinds.shadow,
      opacity: disabled ? 0.45 : 1,
      cursor: disabled ? "not-allowed" : "pointer",
      transition: "transform 120ms var(--ease-standard), box-shadow 180ms var(--ease-standard)",
    }}>
      {icon && <Icon name={icon} size={sizes.fs + 2} />}
      {children}
    </button>
  );
};

const IconButton = ({ icon, size = 36, badge, onClick, title }) => (
  <button onClick={onClick} title={title} style={{
    position: "relative",
    width: size, height: size, borderRadius: 8,
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    background: "rgba(255,255,255,0.04)", border: "1px solid var(--border-1)",
    color: "var(--fg-2)", cursor: "pointer",
  }}>
    <Icon name={icon} size={16} />
    {badge && (
      <span style={{
        position: "absolute", top: -3, right: -3,
        minWidth: 16, height: 16, padding: "0 4px",
        borderRadius: 999,
        background: "linear-gradient(135deg, #FF1E45, #E4002B)",
        color: "#fff", font: "700 9px var(--font-mono)",
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        boxShadow: "0 0 0 2px var(--bg-1)",
      }}>{badge}</span>
    )}
  </button>
);

/* =========================================================================
   CARDS
   ========================================================================= */

const Card = ({ title, subtitle, action, eyebrow, children, padded = true, className = "", style = {} }) => (
  <div className={`kit-card ${className}`} style={{
    background: "var(--bg-2)",
    border: "1px solid var(--border-1)",
    borderRadius: 14,
    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.04), 0 1px 2px rgba(0,0,0,0.5), 0 24px 60px -32px rgba(0,0,0,0.6)",
    overflow: "hidden",
    ...style,
  }}>
    {(title || action || eyebrow) && (
      <div style={{
        display: "flex", alignItems: "flex-start", justifyContent: "space-between",
        padding: "16px 18px 12px", gap: 12,
      }}>
        <div style={{ minWidth: 0 }}>
          {eyebrow && <div className="kit-eyebrow" style={{ marginBottom: 5 }}>{eyebrow}</div>}
          {title && <div style={{ font: "600 15px/1.2 var(--font-display)", color: "var(--fg-1)", letterSpacing: "-0.01em" }}>{title}</div>}
          {subtitle && <div style={{ font: "500 12px var(--font-sans)", color: "var(--fg-3)", marginTop: 3 }}>{subtitle}</div>}
        </div>
        {action}
      </div>
    )}
    <div style={{ padding: padded ? "0 18px 18px" : 0 }}>{children}</div>
  </div>
);

const KpiCard = ({ label, value, unit, sub, delta, icon, tone = "red", sparkline, sparkColor }) => {
  const grad = {
    red:   "var(--grad-kpi-red)",
    gold:  "var(--grad-kpi-gold)",
    green: "var(--grad-kpi-green)",
    sky:   "var(--grad-kpi-sky)",
  }[tone] || "var(--grad-kpi-red)";
  const deltaToneMap = {
    gain: { bg: "rgba(34,197,94,0.16)",  fg: "#86EFAC" },
    loss: { bg: "rgba(239,68,68,0.16)",  fg: "#FCA5A5" },
    warn: { bg: "rgba(245,158,11,0.16)", fg: "#FCD34D" },
    info: { bg: "rgba(56,189,248,0.16)", fg: "#7DD3FC" },
  };
  const dt = delta ? deltaToneMap[delta.tone] : null;
  const sparkColorResolved = sparkColor || ({ red:"#E4002B", gold:"#FBBF24", green:"#34D399", sky:"#38BDF8" }[tone]);
  return (
    <div style={{
      position: "relative",
      background: `${grad}, var(--bg-2)`,
      border: "1px solid var(--border-1)",
      borderRadius: 14,
      padding: 18,
      boxShadow: "inset 0 1px 0 rgba(255,255,255,0.05), 0 1px 2px rgba(0,0,0,0.5)",
      overflow: "hidden",
      transition: "transform 180ms var(--ease-standard), box-shadow 180ms var(--ease-standard)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
        <CircleIcon icon={icon} tone={tone}/>
        {delta && (
          <span style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            font: "700 11px/1 var(--font-mono)",
            padding: "5px 9px", borderRadius: 999,
            background: dt.bg, color: dt.fg,
          }}>{delta.text}</span>
        )}
      </div>
      <div className="kit-eyebrow">{label}</div>
      <div className="t-num" style={{
        font: "700 30px/1.05 var(--font-display)",
        color: "var(--fg-1)", letterSpacing: "-0.025em",
        marginTop: 6,
        display: "flex", alignItems: "baseline", gap: 6,
      }}>
        {value}
        {unit && <span style={{ fontSize: 13, color: "var(--fg-3)", fontWeight: 600 }}>{unit}</span>}
      </div>
      {sub && <div style={{ font: "500 11.5px/1.3 var(--font-sans)", color: "var(--fg-3)", marginTop: 4 }}>{sub}</div>}
      {sparkline && (
        <div style={{ position: "absolute", right: 14, bottom: 12, opacity: 0.95 }}>
          <Sparkline values={sparkline} color={sparkColorResolved} width={84} height={28}/>
        </div>
      )}
    </div>
  );
};

/* =========================================================================
   HERO STRIP — gradient red welcome card with summary + decorative pattern
   ========================================================================= */

const HeroStrip = ({ user = "Direction Générale", date = "Mardi 20 mai 2026", summary, metric }) => (
  <div style={{
    position: "relative",
    background: "var(--grad-hero-red)",
    borderRadius: 16,
    padding: "26px 28px",
    color: "#fff",
    overflow: "hidden",
    boxShadow: "0 24px 60px -20px rgba(228,0,43,0.45), inset 0 1px 0 rgba(255,255,255,0.18)",
  }}>
    {/* hex pattern decoration on right */}
    <div style={{ position: "absolute", top: -20, right: -40, width: 380, height: 220, opacity: 0.20, pointerEvents: "none" }}>
      <HexPattern color="#FFFFFF" opacity={1} size={50}/>
    </div>
    {/* big SG mark watermark */}
    <div style={{
      position: "absolute", right: 28, top: 22, width: 96, height: 96, borderRadius: 12,
      background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.14)",
      display: "flex", alignItems: "center", justifyContent: "center",
      backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)",
    }}>
      <img src="../../assets/logos/SGCI.png" style={{ width: 70, height: 70, objectFit: "contain", borderRadius: 8, background: "#fff", padding: 8, boxSizing: "border-box" }}/>
    </div>

    <div style={{ display: "flex", flexDirection: "column", gap: 14, position: "relative", maxWidth: "70%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ font: "600 11px/1 var(--font-sans)", letterSpacing: "0.10em", textTransform: "uppercase", opacity: 0.85 }}>
          {date} · Lecture exécutive
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, font: "600 10.5px/1 var(--font-sans)", letterSpacing: "0.06em", textTransform: "uppercase", padding: "3px 8px", borderRadius: 999, background: "rgba(255,255,255,0.18)", border: "1px solid rgba(255,255,255,0.20)" }}>
          <span style={{ width: 6, height: 6, borderRadius: 999, background: "#86EFAC", boxShadow: "0 0 8px #86EFAC" }}/>
          Données AN3 disponibles
        </span>
      </div>
      <div>
        <h1 style={{ margin: 0, font: "700 30px/1.1 var(--font-display)", letterSpacing: "-0.02em", color: "#fff" }}>Bonjour, {user}.</h1>
        <div style={{ font: "500 14.5px/1.55 var(--font-sans)", color: "rgba(255,255,255,0.86)", marginTop: 6, maxWidth: 640 }}>
          {summary}
        </div>
      </div>
      {metric && (
        <div style={{ display: "flex", gap: 28, marginTop: 6 }}>
          {metric.map(m => (
            <div key={m.label} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={{ font: "600 10.5px/1 var(--font-sans)", letterSpacing: "0.08em", textTransform: "uppercase", opacity: 0.7 }}>{m.label}</span>
              <span className="t-num" style={{ font: "700 22px var(--font-display)", letterSpacing: "-0.02em" }}>
                {m.value}
                {m.unit && <span style={{ fontSize: 12, opacity: 0.7, fontWeight: 600, marginLeft: 4 }}>{m.unit}</span>}
              </span>
              {m.delta && (
                <span style={{ font: "600 11px/1 var(--font-mono)", color: m.deltaTone === "loss" ? "#FCA5A5" : "#86EFAC" }}>
                  {m.delta}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  </div>
);

/* =========================================================================
   CHARTS
   ========================================================================= */

// Mixed vertical bar chart — SGCI in red gradient, peers in slate gradient.
const MixedBarChart = ({ data, format = v => v.toLocaleString("fr-FR"), height = 260 }) => {
  const max = Math.max(...data.map(d => d.value));
  const W = 600, H = height;
  const PADB = 36, PADT = 28, PADL = 30, PADR = 16;
  const barW = (W - PADL - PADR) / data.length * 0.58;
  const step = (W - PADL - PADR) / data.length;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: "100%" }}>
      <defs>
        <linearGradient id="bar-red" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#FF1E45"/><stop offset="100%" stopColor="#B11226"/>
        </linearGradient>
        <linearGradient id="bar-slate" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#64748B"/><stop offset="100%" stopColor="#334155"/>
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75, 1].map((p, i) => (
        <line key={i} x1={PADL} x2={W - PADR} y1={H - PADB - p * (H - PADT - PADB)} y2={H - PADB - p * (H - PADT - PADB)} stroke="var(--viz-grid)"/>
      ))}
      {data.map((d, i) => {
        const h = (d.value / max) * (H - PADT - PADB);
        const x = PADL + i * step + (step - barW) / 2;
        const y = H - PADB - h;
        return (
          <g key={d.label}>
            <rect x={x} y={y} width={barW} height={h} rx={6}
              fill={d.focus ? "url(#bar-red)" : "url(#bar-slate)"}
              opacity={d.focus ? 1 : 0.9}/>
            <rect x={x} y={y} width={barW} height={3} rx={3}
              fill={d.focus ? "#FF6A82" : "#94A3B8"} opacity="0.6"/>
            <text x={x + barW / 2} y={y - 8} textAnchor="middle"
              fill={d.focus ? "#FCA5A5" : "var(--fg-2)"}
              style={{ font: `700 11px var(--font-mono)`, fontVariantNumeric: "tabular-nums" }}>
              {format(d.value)}
            </text>
            <text x={x + barW / 2} y={H - 14} textAnchor="middle"
              fill={d.focus ? "var(--sg-red-400)" : "var(--fg-3)"}
              style={{ font: `${d.focus ? 700 : 500} 11.5px var(--font-sans)` }}>
              {d.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

// Donut chart with center label.
const DonutChart = ({ data, centerLabel, centerSub, size = 220 }) => {
  const total = data.reduce((s, d) => s + d.value, 0);
  const R = size / 2 - 10, IR = R - 22;
  const cx = size / 2, cy = size / 2;
  let acc = 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {data.map((d, i) => {
        const start = (acc / total) * Math.PI * 2 - Math.PI / 2;
        acc += d.value;
        const end = (acc / total) * Math.PI * 2 - Math.PI / 2;
        const large = end - start > Math.PI ? 1 : 0;
        const x1 = cx + R * Math.cos(start), y1 = cy + R * Math.sin(start);
        const x2 = cx + R * Math.cos(end),   y2 = cy + R * Math.sin(end);
        const x3 = cx + IR * Math.cos(end),  y3 = cy + IR * Math.sin(end);
        const x4 = cx + IR * Math.cos(start),y4 = cy + IR * Math.sin(start);
        return (
          <path key={d.label} d={`M ${x1} ${y1} A ${R} ${R} 0 ${large} 1 ${x2} ${y2} L ${x3} ${y3} A ${IR} ${IR} 0 ${large} 0 ${x4} ${y4} Z`}
            fill={d.color} opacity={d.focus ? 1 : 0.78}
            style={{ filter: d.focus ? "drop-shadow(0 0 12px rgba(228,0,43,0.45))" : "none" }}/>
        );
      })}
      <text x={cx} y={cy - 6} textAnchor="middle" style={{ font: "700 28px var(--font-display)", fill: "var(--fg-1)", letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums" }}>
        {centerLabel}
      </text>
      <text x={cx} y={cy + 14} textAnchor="middle" style={{ font: "500 11px var(--font-sans)", letterSpacing: "0.08em", textTransform: "uppercase", fill: "var(--fg-3)" }}>
        {centerSub}
      </text>
    </svg>
  );
};

// Multi-line chart for trends
const LineChart = ({ series, xLabels, format = v => v, height = 230 }) => {
  const W = 600, H = height;
  const PADL = 40, PADR = 16, PADT = 14, PADB = 28;
  const all = series.flatMap(s => s.values);
  const max = Math.max(...all) * 1.1, min = 0;
  const xStep = (W - PADL - PADR) / (xLabels.length - 1);
  const y = v => H - PADB - ((v - min) / (max - min)) * (H - PADT - PADB);
  const x = i => PADL + i * xStep;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: "100%" }}>
      <defs>
        <linearGradient id="line-area" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#E4002B" stopOpacity="0.45"/>
          <stop offset="100%" stopColor="#E4002B" stopOpacity="0"/>
        </linearGradient>
      </defs>
      {[0, 0.25, 0.5, 0.75, 1].map((p, i) => (
        <g key={i}>
          <line x1={PADL} x2={W - PADR} y1={y(max * p)} y2={y(max * p)} stroke="var(--viz-grid)"/>
          <text x={PADL - 6} y={y(max * p) + 4} textAnchor="end"
            fill="var(--fg-3)" style={{ font: "500 10.5px var(--font-mono)", fontVariantNumeric: "tabular-nums" }}>
            {format(max * p)}
          </text>
        </g>
      ))}
      {xLabels.map((l, i) => (
        <text key={l} x={x(i)} y={H - 8} textAnchor="middle"
          fill="var(--fg-3)" style={{ font: "500 11px var(--font-sans)" }}>{l}</text>
      ))}
      {series.map(s => {
        const path = s.values.map((v, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(v)}`).join(" ");
        return (
          <g key={s.id}>
            {s.focus && (
              <path d={`${path} L ${x(s.values.length - 1)} ${H - PADB} L ${x(0)} ${H - PADB} Z`}
                fill="url(#line-area)"/>
            )}
            <path d={path} stroke={s.color} strokeWidth={s.focus ? 2.4 : 1.6}
              fill="none" strokeLinecap="round" opacity={s.focus ? 1 : 0.7}/>
            {s.values.map((v, i) => (
              <circle key={i} cx={x(i)} cy={y(v)} r={s.focus ? 4 : 2.5}
                fill="#0B1220" stroke={s.color} strokeWidth={s.focus ? 2 : 1.4}/>
            ))}
          </g>
        );
      })}
    </svg>
  );
};

/* =========================================================================
   BANK RANKING ROW — like boltstack "top pages" + John Hardward production line
   ========================================================================= */

const RankingRow = ({ rank, bank, segment, value, unit, valueRaw, max, status, sparkline }) => {
  const pct = Math.max(8, Math.min(100, (valueRaw / max) * 100));
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "32px 36px 1fr 100px 100px",
      gap: 14, alignItems: "center",
      padding: "12px 4px",
      borderBottom: "1px solid var(--divider)",
    }}>
      <div style={{
        font: "700 13px var(--font-mono)", color: rank === 1 ? "#FCA5A5" : "var(--fg-3)",
        textAlign: "center",
      }}>
        <span style={{
          display: "inline-flex", width: 26, height: 26, borderRadius: 8,
          background: rank === 1 ? "linear-gradient(135deg, rgba(228,0,43,0.25), rgba(228,0,43,0.12))" : "var(--bg-3)",
          border: rank === 1 ? "1px solid rgba(228,0,43,0.40)" : "1px solid var(--border-1)",
          alignItems: "center", justifyContent: "center",
        }}>{rank}</span>
      </div>
      <BankLogo bank={bank} size={32}/>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <span style={{ font: "600 13px var(--font-display)", color: bank.focus ? "var(--sg-red-400)" : "var(--fg-1)" }}>
            {bank.short}
          </span>
          <span style={{ font: "500 11px var(--font-sans)", color: "var(--fg-4)" }}>{segment}</span>
        </div>
        <div style={{
          height: 6, borderRadius: 999, background: "var(--bg-3)", overflow: "hidden",
          position: "relative",
        }}>
          <div style={{
            position: "absolute", inset: 0, width: pct + "%",
            background: bank.focus ? "var(--grad-progress-red)" : "var(--grad-progress-slate)",
            borderRadius: 999,
            boxShadow: bank.focus ? "0 0 10px rgba(228,0,43,0.45)" : "none",
          }}/>
        </div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div className="t-num" style={{ font: "700 15px var(--font-display)", color: bank.focus ? "var(--sg-red-400)" : "var(--fg-1)" }}>
          {value} <span style={{ fontSize: 11, color: "var(--fg-3)", fontWeight: 600 }}>{unit}</span>
        </div>
        {sparkline && (
          <div style={{ marginTop: 2 }}>
            <Sparkline values={sparkline} color={bank.focus ? "#E4002B" : "#64748B"} width={70} height={18} area={false}/>
          </div>
        )}
      </div>
      <div style={{ textAlign: "right" }}>
        <StatusPill kind={status.kind}>{status.label}</StatusPill>
      </div>
    </div>
  );
};

/* =========================================================================
   SIGNAL FEED ROW — John Hardward "Production Line Status" style
   ========================================================================= */

const SignalRow = ({ icon, tone, title, meta, status }) => (
  <div style={{
    display: "flex", alignItems: "center", gap: 14,
    padding: "12px 4px", borderBottom: "1px solid var(--divider)",
  }}>
    <CircleIcon icon={icon} tone={tone} size={38}/>
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ font: "600 13px/1.3 var(--font-sans)", color: "var(--fg-1)" }}>{title}</div>
      <div style={{ font: "500 11.5px var(--font-sans)", color: "var(--fg-3)", marginTop: 2 }}>{meta}</div>
    </div>
    <StatusPill kind={status.kind}>{status.label}</StatusPill>
  </div>
);

/* =========================================================================
   SHELL — Sidebar / Topbar
   ========================================================================= */

const Sidebar = ({ active, onChange, bankCount }) => {
  const nav = [
    { id: "dashboard",      label: "Tableau de bord", icon: "bar-chart" },
    { id: "positionnement", label: "Positionnement",  icon: "credit-card" },
    { id: "performance",    label: "Performance",     icon: "trending-up", count: "AN3" },
    { id: "synthese",       label: "Synthèse DG",     icon: "file-text" },
  ];
  const intel = [
    { id: "assistant",      label: "Assistant IA",    icon: "message", count: "RAG" },
    { id: "documents",      label: "Documents",       icon: "search" },
  ];
  const Item = ({ it }) => {
    const isActive = it.id === active;
    return (
      <div onClick={() => onChange(it.id)} style={{
        position: "relative",
        display: "flex", alignItems: "center", gap: 11,
        padding: "11px 14px", margin: "2px 10px", borderRadius: 8,
        color: isActive ? "#fff" : "rgba(203,213,225,0.78)",
        font: "600 13px var(--font-sans)",
        background: isActive ? "linear-gradient(135deg, #E4002B, #B11226)" : "transparent",
        boxShadow: isActive ? "0 8px 20px -10px rgba(228,0,43,0.55), inset 0 1px 0 rgba(255,255,255,0.18)" : "none",
        cursor: "pointer",
      }}>
        {isActive && <span style={{ position: "absolute", left: -10, top: "20%", bottom: "20%", width: 3, borderRadius: 999, background: "#fff" }}/>}
        <Icon name={it.icon} size={16}/>
        <span style={{ flex: 1 }}>{it.label}</span>
        {it.count && (
          <span style={{
            font: "700 9.5px var(--font-mono)",
            background: isActive ? "rgba(255,255,255,0.20)" : "rgba(255,255,255,0.08)",
            padding: "3px 6px", borderRadius: 4,
            color: isActive ? "#fff" : "rgba(255,255,255,0.65)",
          }}>{it.count}</span>
        )}
      </div>
    );
  };
  return (
    <aside style={{
      position: "fixed", top: 0, bottom: 0, left: 0, width: 252,
      background: "#080C16",
      borderRight: "1px solid var(--border-1)",
      display: "flex", flexDirection: "column",
      zIndex: 30, overflow: "hidden",
    }}>
      {/* hex decoration top-left of sidebar */}
      <div style={{ position: "absolute", top: -30, left: -40, width: 180, height: 180, opacity: 0.18, pointerEvents: "none" }}>
        <HexPattern color="#E4002B" opacity={1} size={42}/>
      </div>

      <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 11, padding: "20px 18px 18px" }}>
        <span style={{ width: 40, height: 40, background: "#fff", borderRadius: 9, display: "inline-flex", alignItems: "center", justifyContent: "center", overflow: "hidden", boxShadow: "0 6px 16px rgba(228,0,43,0.30)" }}>
          <img src="../../assets/logos/SGCI.png" style={{ width: 30, height: 30, objectFit: "contain" }}/>
        </span>
        <div>
          <div style={{ font: "700 15px/1 var(--font-display)", color: "#fff", letterSpacing: "-0.01em" }}>Strategic <span style={{ color: "var(--sg-red-400)" }}>Intel</span></div>
          <div style={{ font: "500 10.5px var(--font-sans)", color: "rgba(255,255,255,0.5)", marginTop: 3 }}>SGCI · DG Internal</div>
        </div>
      </div>

      <div style={{ padding: "10px 0 4px", font: "700 9.5px var(--font-sans)", letterSpacing: "0.12em", textTransform: "uppercase", color: "rgba(255,255,255,0.32)", paddingLeft: 22 }}>Analyse</div>
      {nav.map(it => <Item key={it.id} it={it}/>)}

      <div style={{ padding: "16px 0 4px", font: "700 9.5px var(--font-sans)", letterSpacing: "0.12em", textTransform: "uppercase", color: "rgba(255,255,255,0.32)", paddingLeft: 22 }}>Intelligence</div>
      {intel.map(it => <Item key={it.id} it={it}/>)}

      <div style={{ marginTop: "auto", padding: 14, position: "relative" }}>
        <div style={{
          position: "relative",
          padding: "16px",
          background: "linear-gradient(135deg, rgba(228,0,43,0.18), rgba(177,18,38,0.08))",
          border: "1px solid rgba(228,0,43,0.25)",
          borderRadius: 12,
          overflow: "hidden",
        }}>
          <div style={{ position: "absolute", top: -10, right: -20, width: 100, height: 100, opacity: 0.30, pointerEvents: "none" }}>
            <HexPattern color="#E4002B" opacity={1} size={32}/>
          </div>
          <div style={{ position: "relative" }}>
            <div style={{ font: "700 11px var(--font-sans)", letterSpacing: "0.08em", textTransform: "uppercase", color: "#FCA5A5" }}>Scope actuel</div>
            <div style={{ font: "700 22px var(--font-display)", color: "#fff", marginTop: 6, letterSpacing: "-0.02em" }}>{bankCount}<span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.6)", marginLeft: 4 }}>banques</span></div>
            <div style={{ font: "500 11px var(--font-sans)", color: "rgba(255,255,255,0.55)", marginTop: 4 }}>2024 — 2026 · AN1–AN3</div>
          </div>
        </div>
      </div>
    </aside>
  );
};

const Topbar = ({ title, sub, bankCount, onCommand }) => (
  <header style={{
    position: "sticky", top: 0, zIndex: 20,
    background: "rgba(8,12,22,0.78)", backdropFilter: "blur(18px)", WebkitBackdropFilter: "blur(18px)",
    borderBottom: "1px solid var(--border-1)",
    padding: "16px 30px",
    display: "flex", alignItems: "center", gap: 18,
  }}>
    <div style={{ flex: 1 }}>
      <h1 style={{ margin: 0, font: "700 22px/1.2 var(--font-display)", color: "var(--fg-1)", letterSpacing: "-0.02em" }}>{title}</h1>
      <div style={{ font: "500 12.5px var(--font-sans)", color: "var(--fg-3)", marginTop: 3 }}>{sub}</div>
    </div>
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      background: "var(--bg-inset)", border: "1px solid var(--border-1)",
      borderRadius: 10, padding: "10px 14px", color: "var(--fg-3)", minWidth: 280,
    }}>
      <Icon name="search" size={15}/>
      <span style={{ font: "500 12.5px var(--font-sans)" }}>Posez une question, cherchez un document…</span>
      <span style={{ marginLeft: "auto", font: "700 10px var(--font-mono)", background: "var(--bg-3)", padding: "3px 6px", borderRadius: 5, color: "var(--fg-3)" }}>⌘ K</span>
    </div>
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <Chip tone="live" dot pulse>Live</Chip>
      <IconButton icon="bell" badge="3"/>
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "5px 12px 5px 5px",
        background: "var(--bg-2)", border: "1px solid var(--border-1)",
        borderRadius: 999,
      }}>
        <div style={{
          width: 30, height: 30, borderRadius: 999,
          background: "linear-gradient(135deg, var(--sg-red-500), var(--sg-red-700))",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          color: "#fff", font: "700 11.5px var(--font-display)",
        }}>DG</div>
        <div>
          <div style={{ font: "600 12px/1 var(--font-display)", color: "var(--fg-1)" }}>Direction Générale</div>
          <div style={{ font: "500 10px var(--font-sans)", color: "var(--fg-3)", marginTop: 2 }}>SGCI · CI</div>
        </div>
      </div>
    </div>
  </header>
);

/* =========================================================================
   Export
   ========================================================================= */
Object.assign(window, {
  HexPattern, BankLogo, StatusPill, Sparkline, CircleIcon,
  Chip, Button, IconButton, Card, KpiCard, HeroStrip,
  MixedBarChart, DonutChart, LineChart,
  RankingRow, SignalRow,
  Sidebar, Topbar,
});
