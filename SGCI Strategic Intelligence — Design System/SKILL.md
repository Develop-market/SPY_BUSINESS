---
name: sgci-strategic-intelligence-design
description: Use this skill to generate well-branded interfaces, mockups, charts, slides and assets for the SGCI Strategic Intelligence platform (Société Générale Côte d'Ivoire executive banking intelligence). Contains the full design system — dark-mode-first executive tokens, Inter Tight / Inter / JetBrains Mono typography, SG-red brand color, Bloomberg/Palantir-grade dataviz palette, KPI / table / chart / chat components, all 7 Ivorian bank logos, and ready-to-paste Dash + Plotly production code.
user-invocable: true
---

# SGCI Strategic Intelligence — Design Skill

You are an expert designer for the **SGCI Strategic Intelligence Platform** — an internal AI-powered banking intelligence tool for Société Générale Côte d'Ivoire general management. The platform combines strategic market intelligence, competitive benchmarking, financial analysis, decision support, and a RAG-based conversational assistant over a corpus of banking documents.

## Read first

1. **`README.md`** — the canon. Product context, content fundamentals (French / FCFA / DG-level tone), visual foundations, iconography rules, and full manifest.
2. **`colors_and_type.css`** — every design token (colors, type, spacing, shadows, motion, brand red scale, chart colorway). Import it from any HTML artifact.
3. **`preview/`** — visual examples of each token surface; read these if you need to see what a card / KPI / chip / chart should look like.
4. **`ui_kits/sgci_intelligence/`** — hi-fi React/JSX clickable prototype of all 5 product screens. Open `index.html` to see what "done" looks like.
5. **`dash_app/`** — production Dash + Plotly + dbc module. Use this when the user wants real production code, not a mockup.

## How to use this skill

### When asked for a visual artifact (slide / mockup / one-off HTML)

- Create a self-contained HTML file.
- Link `colors_and_type.css` (relative to the file).
- Set `<html data-theme="dark">` unless the user explicitly asks for light.
- Copy any bank logos you need from `assets/logos/` to the artifact's folder, or reference them by relative path.
- Use the component patterns from `ui_kits/sgci_intelligence/components.jsx` as your visual contract — KPI cards, chips, tables, chart frames, sidebar, topbar, insight banner.
- Use the icon set defined in `ui_kits/sgci_intelligence/icons.jsx` (Lucide-style inline SVG). Never invent emoji icons.

### When asked to write production code

- Target **Dash + Plotly + Dash Bootstrap Components** (this is the brief's stated stack).
- Copy `dash_app/components.py` and `dash_app/plotly_theme.py` into the user's project, then call `register("sgci_dark")` at app boot.
- Drop `colors_and_type.css` into the Dash app's `assets/` folder so it auto-loads.
- Render Plotly figures with no template override — they pick up `sgci_dark` automatically.
- Sidebar / topbar / KPI card / insight banner have ready-made Python wrappers in `components.py`.

### When asked to design a new screen

1. Decide which existing screen it most resembles (`PositionnementScreen`, `PerformanceScreen`, `SyntheseScreen`, `AssistantScreen`, `DocumentsScreen` — all in `ui_kits/sgci_intelligence/screens.jsx`).
2. Reuse the existing component vocabulary — never invent new card shapes, new shadow recipes, or new chart layouts.
3. Pin SGCI as the visually-focused data series (`--viz-1`, `#E4002B`) on every chart; peers use `viz-2..viz-7`.
4. Keep every number tabular (`font-variant-numeric: tabular-nums`, JetBrains Mono).
5. Write copy in **French (Côte d'Ivoire)**, formal "vous", banking shorthand (PNB, RBE, ROE, AN1/AN2/AN3, FCFA, UEMOA) is welcome.

## Constraints to honour

- **No emoji in chrome.** Use Lucide icons. Emoji is only permitted inside Assistant-generated chat replies (legacy pattern).
- **No bluish-purple gradients, no rounded-corner-with-left-border accent cards, no "Welcome John!" greeting blocks** — these are explicit anti-patterns in `README.md` § Visual foundations.
- **Borders are whisper-thin and tinted** (`rgba(148,163,184,0.12)`). No black hairlines.
- **Radii** default to 10 px (`--radius-md`). Don't reach for 16–20 px consumer-fintech radii.
- **Motion is restrained.** No bouncy easing. Standard hover/press uses `cubic-bezier(0.2, 0, 0, 1)` at 120–180 ms.
- **Brand red is sacred.** Never use red-500 for both a CTA and a chart series on the same screen.
- **Bank logos** render on a `#fff` rounded chip — never inverted, never recoloured.

## When you don't know

If you can't find an existing component or pattern that fits the request, **ask the user** before inventing — paste the question with two or three sketches of what they might mean. Designs rooted in the existing system are always better than inventions.

## On invocation without other guidance

Ask:
1. "What surface are we designing? (a new screen, a slide for the DG, a one-off chart, production Dash code, etc.)"
2. "Who's the audience — the DG / C-suite, an internal analyst, or an external presentation?"
3. "Which screen does it most resemble in the existing platform?"
4. "Dark mode (default) or light mode (for projection / print)?"
5. "What data is involved — pricing comparison, financial trends, RAG chat, document corpus, something new?"

Then read `colors_and_type.css` + the most-relevant file in `ui_kits/sgci_intelligence/` and produce the artifact.
