# SGCI Strategic Intelligence — Design System

> Premium executive design system for an enterprise AI-powered banking intelligence platform built for **Société Générale Côte d'Ivoire (SGCI)** general management. Combines a Bloomberg-grade dark mode, Palantir-style information density, Power BI-grade dataviz discipline, and fintech polish.

---

## 1. Product context

### What we're designing for

The **SGCI Strategic Intelligence Platform** is an internal, executive-only tool that centralizes and analyzes:

- **Bank conditions & pricing grids** — fees, card costs, interest rates, payment incidents for 7 Ivorian banks (SGCI, BICICI, ECOBANK, NSIA, SIB, BACI, BNI)
- **Financial statements** — PNB, net result, ROE/ROA, exploitation ratios, NPL, capital ratios across 3 fiscal exercises (AN1 → AN3)
- **Activity & regulatory reports** — narrative documents consolidated and indexed
- **Competitive market data** — product/service presence matrices, segment positioning

…surfaced through five primary surfaces:

| Surface | Audience action |
|---|---|
| **Positionnement Commercial** | Compare tariffs, cards, savings rates, incidents pricing across the 7 banks. |
| **Performance Financière** | Read 3-year financial trends per bank and benchmark KPI ratios. |
| **Synthèse Stratégique** | DG-level executive summary, peer averages, leader rankings, strategic prompts. |
| **Assistant IA** | RAG-based conversational AI over the entire document corpus — ask in natural language, get cited, structured answers. |
| **Document / Search** | Multi-method extraction, document consolidation, vector search. |

### Audience & tone

- **General Management & C-suite of SGCI.** Designs need to read clearly in a 90-second executive scan and reward a 30-minute deep dive.
- Single-tenant, French-first (Côte d'Ivoire FR), with FCFA / UEMOA monetary conventions.
- Internal tool — no marketing surface. Every pixel earns its place.

### Sources

- **Codebase** (read-only, mounted): `b_PhMi4pmVgoC/` — Next.js 16 + React 19 + Tailwind v4 + Radix UI + Recharts. Components live under `b_PhMi4pmVgoC/components/dashboard/` (sidebar, kpi-card, positionnement-tab, performance-tab, synthese-tab, assistant-tab) and `b_PhMi4pmVgoC/components/ui/` (shadcn/Radix primitives).
- **Bank logos**: `b_PhMi4pmVgoC/LOGO/` and `uploads/` — 7 competitor banks.
- **Inspiration uploads**: dark-mode analytics dashboards (`uploads/0cd0…jpg`, `uploads/3300…jpg`) and a fitness-style premium dark UI (`uploads/Capture …151709.png`) supplied by the product owner to anchor the executive dark aesthetic.

> **Production target.** The brief specifies Python **Dash + Plotly + Dash Bootstrap Components**. The reference codebase is Next.js — its components are visual + semantic reference only. The CSS tokens here are framework-agnostic and ship with a `plotly_theme.py` template (see `assets/`).

---

## 2. Content fundamentals

### Language

- **French (fr-CI)** is the primary surface language. Avoid anglicisms unless they're industry standard (KPI, dashboard, ROE, ROA, NPL, RAG).
- Banking shorthand is welcome and expected: **PNB** (Produit Net Bancaire), **RBE**, **DAT**, **UEMOA**, **DAB/GIM**, **FCFA**, **AN1/AN2/AN3**, **MLT**.
- Use **non-breaking spaces** before `%`, `FCFA`, `Mds`, and inside large numbers (`12 450 FCFA`, not `12,450 FCFA`). Currency goes **after** the number.

### Voice

- **Authoritative, neutral, analyst-grade.** No marketing energy. No emojis in chrome/UI copy. (The legacy assistant uses ✅/💡/📊 in chat replies — those are *content*, not chrome. Treat them as legacy and prefer typographic emphasis going forward.)
- Address the executive in the **third person / impersonal** ("La DG peut…", "Cette analyse met en évidence…"). When direct, prefer **"vous"** (formal); never "tu".
- **Verb forward, no hedging.** "Comparer SGCI et BICICI" — not "Vous pouvez comparer".
- Headings are **noun phrases**, sentence-cased with French capitalization rules. Examples from the live product:
  - `Positionnement Commercial`
  - `Performance Financière`
  - `Synthèse Stratégique`
  - `Benchmark SGCI vs concurrents`
  - `Catalogue comparé (présence)`
  - `Que mettre en avant — entreprises`

### Numbers, units, deltas

- **Tabular numerics, always.** Every digit in the UI uses `font-variant-numeric: tabular-nums` (see `.t-num` and `.t-kpi`).
- **Currency**: `12 450 FCFA/mois`, `1,8 Mds FCFA`. Use the French decimal comma.
- **Percent**: one decimal max for ratios (`ROE 21,4 %`), zero for headline shares (`68 %`).
- **Deltas** carry a sign and a colour: `+2,3 pts` (gain green), `-1,1 pts` (loss red), `±0` (neutral grey). Never an isolated arrow without the value.
- **Time periods** are named explicitly: `AN1–AN3 (3 exercices)` or `2024–2026 (scénarios tarifaires)`. Never just "2024".

### Microcopy patterns (lifted from the codebase, keep them)

- Status pills: `Données actualisées`, `7 banques analysées`, `Réf. tableau : AN3`.
- Insight banners open with a **bolded lead** + colon: `**Positionnement Low-Cost:** BACI se positionne comme…`.
- Strategic prompts use a hyphenated em-dash format: `Lecture DG — croiser cette grille avec l'onglet Performance`.
- Assistant outputs are **structured** (markdown-like): bolded indicators, bulleted classements, a closing `💡` insight line. Keep replies under ~12 lines.

### Don't

- Don't write CTAs like "Cliquez ici" or "Découvrez nos". This isn't a website.
- Don't pad screens with motivational copy ("Bonjour 👋"). The legacy "Welcome!" pattern from the inspiration boards is **not** the target.
- Don't use emojis as chrome/iconography. Use the Lucide icon set instead.

---

## 3. Visual foundations

### Two themes, dark-first

The platform ships **premium dark mode by default** for daily executive use, and a **clean light mode** for projection, print, and PDF export. Both are first-class — they share the same tokens, layouts, and components.

- Theme is controlled by `<html data-theme="dark|light">`. All tokens (`--bg-1`, `--fg-1`, `--primary`, …) resolve per-theme.
- The dark theme is **deep navy-black, not pure black**: `--ink: #05070D` for the shell, layered up through `#0B1220 → #111A2C → #182438 → #1F2D45`. This is the Palantir/Bloomberg recipe — pure-black "OLED" backgrounds feel cheap and harsh under conference-room projectors.
- The light theme is **off-white with cool slate text** (`#F6F7FB / #0F172A`), not pure white. Matches the legacy in-product look.

### Colour

**Brand red is sacred, used sparingly.**

- `--sg-red-500 (#E4002B)` is the **accent** — used for the focused data series (SGCI in every chart), primary CTAs, the brand mark.
- `--sg-red-700 (#B11226)` is the **deep brand red** — sidebar active state, headers, hover surfaces on light mode.
- Red **never** colours both a CTA and a chart series at once on the same screen; the eye should know exactly what red means in that view.

**Peer/data palette** (chart-2 through chart-7) is intentionally cool — sky, emerald, amber, violet, rose, teal. SG red always pops as the protagonist.

**Semantic colours**:
- `--gain #22C55E` — green, up ticks, positive deltas, "Oui" presence.
- `--loss #EF4444` — red, down ticks, NPL spikes, incidents.
- `--warn #F59E0B` — amber, anomalies, capital ratio warnings, "écart" badges.
- `--info #38BDF8` — sky, neutral metadata.

### Typography

- **Display / UI**: **Inter Tight** (`--font-display`) — geometric humanist, premium executive feel, replaces Geist Sans from the codebase.
- **Body / UI**: **Inter** (`--font-sans`).
- **Data / mono**: **JetBrains Mono** (`--font-mono`) — KPIs, table cells, deltas, anything numeric.

> **Substitution flag.** The codebase loads **Geist** + **Geist Mono** via `next/font`. Those aren't on Google Fonts as a stable served family for non-Next projects, so the design system substitutes **Inter Tight / Inter / JetBrains Mono**. Visually they're within 2% — Inter Tight has tighter vertical metrics that match Geist almost identically at executive sizes. If you have licensed Geist `.woff2` files, drop them into `fonts/` and update the `@import` in `colors_and_type.css` — **please send them when convenient**.

### Spacing & rhythm

- 4 px base grid (`--space-1` … `--space-16`). Common rhythms: 8 / 12 / 16 / 24 / 32.
- KPI grids: 16 px gap. Section gap: 24 px. Page padding: 24–32 px.
- Tables: 12 px horizontal / 8 px vertical cell padding for dense rows, 16/12 for executive rows.

### Borders, dividers, shadows

- Borders are **whisper-thin and tinted** — `rgba(148, 163, 184, 0.12)` on dark, `rgba(15,23,42,0.08)` on light. No black hairlines.
- Cards rely on **border + faint inset highlight + soft drop**, not heavy box shadows. Pattern (dark):
  ```css
  background: var(--bg-2);
  border: 1px solid var(--border-1);
  border-radius: var(--radius-md);   /* 10px */
  box-shadow: var(--shadow-2);       /* inset top sheen + soft drop */
  ```
- A 1 px top-edge highlight (`inset 0 1px 0 rgba(255,255,255,0.04)`) gives cards the "glass plate" feel from the dark inspiration boards. **Don't** use coloured left-border accents — they read as bootcamp templates.

### Radii

- **10 px** is the working default (`--radius-md`) — cards, dropdowns, panels, charts.
- **6 px** for buttons, inputs, pills.
- **999 px pills** for status chips, ticker chips, segment toggles.
- Avoid the 16–20 px "fintech consumer" radii. We're enterprise.

### Backgrounds & gradients

- Shell uses a **two-vector radial gradient** of brand red (top-left) + sky (top-right) at very low opacity over a near-black base — adds depth without taste-of-2014 purple gradients.
- Cards: **flat fill** plus the inset-highlight sheen. No card gradients.
- Hero / cover slides (rare): radial vignette + 4% red ambient. Never the bluish-purple gradient cliché.
- Imagery is **rare** — this is a data product. When imagery appears it's full-bleed, cool-toned, slightly desaturated, treated with a 30% dark scrim. Avoid stock photography of "happy professionals shaking hands".

### Hover, press, focus

- **Hover** on dark: surface lifts one layer (`--bg-2 → --bg-3`), text snaps to `--fg-1`, border `--border-1 → --border-2`. ~180 ms ease.
- **Hover** on light: background tints `--primary-soft` for primary actions, otherwise lifts to `--bg-3`.
- **Press / active**: surface flattens (`--bg-3 → --bg-2`), no scale transform on most controls. Tiny `scale(0.98)` only on primary buttons.
- **Focus** is **always** visible — 2 px outline in `--primary-ring` plus a 1 px solid `--primary` border. Never `outline: none` without a replacement.
- Disabled: 40 % opacity, no pointer.

### Motion

- **Restrained.** This is an executive tool — no bouncy, no overshoot, no scroll-jacking.
- Standard easing: `cubic-bezier(0.2, 0, 0, 1)` for hover/press; `cubic-bezier(0.16, 1, 0.3, 1)` for entering panels.
- Durations: `120 ms` hovers, `180 ms` panel transitions, `320 ms` modal/route changes.
- Charts animate in once on mount (300 ms). They **do not** re-animate on filter change — values just snap. (Re-animating bars on every filter change is disorienting in dataviz.)
- Tickers and live-data pulses use a `1.4 s` ease-in-out opacity loop on a 6 px dot.

### Transparency & blur

- Used **only** on chrome that sits over scrollable content: the sticky header (`background: rgba(11,18,32,0.72); backdrop-filter: blur(14px)`), modals, popovers.
- Never on cards or data surfaces — translucency over a chart makes numbers unreadable.

### Layout rules

- Persistent **left sidebar** (264 px, deep slate `--slate-900`) anchors navigation.
- Sticky **header** (64 px, blurred) carries the active surface title + global status (data freshness, # of banks).
- Single content column up to 1440 px, with internal grids (1/2/3/4 col responsive).
- Filter bar is sticky just under the header (z-19), with the data filters and the scenario/year selector pinned at the top.
- **No floating action buttons.** No carousels. Tables can scroll horizontally inside cards.

### Charts (Plotly / Recharts)

Every chart in the system shares these defaults:

- `paper_bgcolor`, `plot_bgcolor` → transparent (cards own the background).
- `gridcolor` → `--viz-grid` (very faint). `zeroline` off.
- `axis` → `--viz-axis` (~55 % opacity slate), no axis lines on small charts.
- `font` → Inter, 12 px, `--fg-3`.
- `colorway` → `[--viz-1, --viz-2, … --viz-7]` — SGCI red always first.
- Tooltips: dark card with 1 px border, mono digits, no arrow.
- Legend: **inline chips below the chart**, not a boxed legend on the right.
- One series, one role. **No double-axes** without a clearly-labelled second axis title.

---

## 4. Iconography

### System

- **Lucide icons** (`lucide-react` in code, or the CDN `https://unpkg.com/lucide-static`) — the codebase already uses Lucide. Stroke-only, 1.5 px stroke, 24 px box, rounded joins. Same style across the whole platform.
- Common icons in use, lifted from the codebase: `BarChart3`, `TrendingUp`, `TrendingDown`, `FileText`, `MessageSquare`, `Send`, `Bot`, `User`, `Sparkles`, `Calculator`, `CreditCard`, `Wallet`, `Percent`, `PiggyBank`, `AlertTriangle`, `ShieldCheck`, `Target`, `Lightbulb`, `Menu`, `X`, `RefreshCw`, `HelpCircle`, `ArrowRight`, `CheckCircle2`, `XCircle`.
- Icon colour follows text colour (`currentColor`) except inside KPI cards, where the icon sits in a 32–40 px tinted square that picks up the KPI's semantic colour.
- **Icon sizes**: 14 px (in pills), 16 px (in buttons/menus), 20 px (in KPI cards), 24 px (nav and headers).

### Brand mark

- **`assets/logos/SGCI.png`** — the iconic SG red/black square. Place on white (or `#FFFFFF` rounded chip) when on a coloured background. Never recolour, never stretch. Min size 28 px.

### Competitor bank logos

All seven logos are in `assets/logos/`:

| File | Use |
|---|---|
| `SGCI.png` | SGCI (always highlighted) |
| `BACI.png` | BACI |
| `BICICI.png` | BICICI (BNP Paribas) |
| `BNI.jpg` | BNI |
| `ECOBANK.png` | ECOBANK |
| `NSIA.png` | NSIA |
| `SIB.png` | SIB (Attijariwafa) |

Render each on a **white 1 px rounded chip** (`background: #fff; border-radius: 6px; padding: 4px`) so dark and light themes both work. Don't try to invert or knock them out.

### Emojis & Unicode

- **No emoji** in chrome / icons / nav / buttons. Period.
- Emoji **may** appear inside Assistant-generated chat content (legacy pattern uses 📊 💡 🏦) — preserve when streaming from the model, but do not author them in static copy.
- Unicode glyphs (·, ‒, →, ↗, ↘, ●) are allowed in tables and dataviz labels when typographically appropriate.

---

## 5. File index (manifest)

```
.
├── README.md                       ← this file
├── SKILL.md                        ← agent skill entry point
├── colors_and_type.css             ← all design tokens + semantic type
│
├── assets/
│   └── logos/                      ← SGCI + 6 competitor bank logos (PNG/JPG)
│
├── preview/                        ← Design System tab cards (registered)
│   ├── colors-brand.html
│   ├── colors-neutrals.html
│   ├── colors-data-viz.html
│   ├── colors-semantic.html
│   ├── type-display.html
│   ├── type-body.html
│   ├── type-numeric.html
│   ├── spacing-radii.html
│   ├── spacing-elevation.html
│   ├── components-buttons.html
│   ├── components-kpi.html
│   ├── components-table.html
│   ├── components-chips.html
│   ├── components-inputs.html
│   ├── components-chart.html
│   ├── brand-logo.html
│   └── brand-banks.html
│
├── ui_kits/
│   └── sgci_intelligence/          ← the platform UI kit (clickable prototype)
│       ├── index.html              ← full hi-fi prototype, 5 screens
│       ├── README.md
│       ├── tokens.css              ← thin re-export of colors_and_type.css
│       ├── data.js                 ← mock dataset
│       ├── icons.jsx               ← inline Lucide-style icon set
│       ├── components.jsx          ← Sidebar, Topbar, FilterBar, KpiCard, Card,
│       │                             DataTable, ChartFrame, HBarChart, LineChart,
│       │                             Chip, Button, IconButton, BankLogo, Insight
│       └── screens.jsx             ← Positionnement / Performance / Synthèse /
│                                     Assistant / Documents screen compositions
│
└── dash_app/                       ← production Python module
    ├── app.py                      ← Dash entry — worked Positionnement view
    ├── components.py               ← sidebar, topbar, kpi_card, card, chip, insight_banner
    ├── plotly_theme.py             ← sgci_dark / sgci_light Plotly templates + color_for()
    └── README.md
```

---

## 6. Production guidance for Dash / Plotly

The platform ships in **Python Dash**. The CSS file works as-is:

```python
# app.py
app = Dash(__name__, external_stylesheets=[
    dbc.themes.BOOTSTRAP,
    "/assets/colors_and_type.css",
])
app.index_string = """<!doctype html>
<html lang="fr" data-theme="dark">
  <head>…{%css%}…</head>
  <body>…{%app_entry%}…</body>
</html>"""
```

Plotly figures should adopt the design tokens via a template:

```python
import plotly.graph_objects as go, plotly.io as pio
pio.templates["sgci_dark"] = go.layout.Template(layout=dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", size=12, color="#CBD5E1"),
    colorway=["#E4002B","#38BDF8","#34D399","#FBBF24","#A78BFA","#F472B6","#14B8A6"],
    xaxis=dict(gridcolor="rgba(148,163,184,0.14)", zeroline=False, linecolor="rgba(148,163,184,0.55)"),
    yaxis=dict(gridcolor="rgba(148,163,184,0.14)", zeroline=False, linecolor="rgba(148,163,184,0.55)"),
    margin=dict(l=40, r=20, t=20, b=40),
))
pio.templates.default = "sgci_dark"
```

dbc components inherit via Bootstrap variable overrides — see `ui_kits/sgci_intelligence/tokens.css` for the `--bs-*` bridge.

---

## 7. Open questions / caveats

- **Geist font files.** Substituted with Inter Tight + Inter + JetBrains Mono. If you can supply the licensed Geist `.woff2`, drop them into `fonts/` and we'll point `colors_and_type.css` at them.
- **Real document corpus.** The Assistant tab is mocked with simulated responses in the codebase. Production RAG citations format isn't shown anywhere — when you wire the real endpoint, share a sample citation block and we'll design it.
- **Branding latitude.** SGCI's parent brand (Société Générale group) has its own corporate guidelines we don't have access to. We've followed the in-product red/black usage from the codebase; if Group brand drops constraints (e.g. specific tints for charts), flag and we'll re-tune.
