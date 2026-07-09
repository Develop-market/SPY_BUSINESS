# SGCI Strategic Intelligence — UI kit

Hi-fi clickable prototype of the SGCI Strategic Intelligence platform — five screens, dark-mode by default, premium executive aesthetic.

## What's inside

```
sgci_intelligence/
├── index.html         ← entry — clickable prototype of all 5 screens
├── tokens.css         ← re-exports ../../colors_and_type.css + kit utility classes
├── data.js            ← mock banking data (7 banks, KPIs, pricing, PNB series, presence matrix)
├── icons.jsx          ← inline Lucide-style icons (no CDN dep)
├── components.jsx     ← Sidebar, Topbar, FilterBar, KpiCard, Card, DataTable,
│                       ChartFrame, HBarChart, LineChart, Sparkline, Chip, Button,
│                       IconButton, BankLogo, Insight
└── screens.jsx        ← PositionnementScreen, PerformanceScreen, SyntheseScreen,
                        AssistantScreen, DocumentsScreen
```

## Screens

| Screen | What it demonstrates |
|---|---|
| **Positionnement Commercial** | KPI strip · 2 ranked horizontal bar charts · benchmark table with SGCI row highlighted · presence matrix · DG insight banner |
| **Performance Financière** | Financial KPIs (PNB, RN, ROE, Coef. expl., NPL) · multi-line PNB chart over AN1→AN3 · ratio bars vs peer avg · financial table |
| **Synthèse Stratégique** | DG insight banner · Forces / Vigilance / Actions cards · ROE ranking chart |
| **Assistant IA** | RAG-style chat with bot/user bubbles, citation chips, ranked-list cards · simulator panel · suggested questions |
| **Documents** | Stub for the corpus + vector-search view (4-bucket counter + spec note) |

All screens share the persistent left **Sidebar** + blurred **Topbar** + sticky **FilterBar** (where applicable).

## Running it

It's static HTML — open `index.html` directly. The React 18 + Babel CDN tags are pinned with integrity hashes.

```bash
# from project root
python -m http.server 8000
# open http://localhost:8000/ui_kits/sgci_intelligence/
```

## Production target: Dash

The CSS tokens, type, spacing, motion, and component conventions in this kit are **the source of truth** for the Dash production app. Use them via:

```python
# app.py — Dash entry
import dash
import dash_bootstrap_components as dbc

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP, "/assets/colors_and_type.css"])
```

See `../../dash_app/` in this design system for a ready-to-paste production module with `app.py` + `plotly_theme.py` + `components.py` that mirrors the JSX kit.

## Caveats

- **Mock data.** All numbers in `data.js` are representative — wire to your real `lib/bank-data.ts` or your Dash data layer when integrating.
- **Charts are SVG, not Plotly.** The kit uses hand-rolled SVG to stay framework-free. Production charts swap to Plotly with the `sgci_dark` template (see `../../dash_app/plotly_theme.py`).
- **Assistant is faked.** The reply switcher in `screens.jsx > AssistantScreen` simulates a few canned answers. Replace `replyFor()` with your real RAG endpoint.
- **No light theme in the prototype.** The brief asked for "premium dark mode" — the design tokens fully support light (just flip `<html data-theme="light">`), but the prototype is dark-only for fidelity.
