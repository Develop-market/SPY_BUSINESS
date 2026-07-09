# SpyBusiness Intelligence Platform

Interface professionnelle d'intelligence bancaire pour les 7 banques de Côte d'Ivoire
(BACI, BICICI, BNI, ECOBANK, NSIA, SGCI, SIB) — **Python Dash + Plotly + DMC + DBC**.

> Palette : noir `#0D0D0D` / surface `#1A1A1A` / cartes `#242424` / accent rouge `#CC2222`.

---

## Deux livrables dans ce dossier

| Dossier | Quoi | Pour |
|---|---|---|
| **`dash_app/`** | Le **vrai code Python Dash** — multi-pages, composants, callbacks, accès PostgreSQL + RAG. | À cloner dans `BACK/DASHBOARD/` et lancer. |
| **`preview.html` + `app.preview.js`** | Une **maquette HTML** statique avec vrais graphiques Plotly. | Visualiser le design sans rien installer. |

La maquette et le code Dash partagent **exactement la même palette, mise en page et charte graphique**.

---

## A. Lancer la maquette (aucune installation)

Ouvrez `preview.html` dans un navigateur. Vous y trouverez les 5 pages
(Dashboard, Chat IA, Conditions, Performance, Réglementation), la sidebar
repliable, le bouton chat flottant et les graphiques Plotly.

---

## B. Lancer la vraie application Dash

### 1. Placement
Copiez le contenu de `dash_app/` dans `C:\Users\…\BACK\DASHBOARD\` :

```
BACK/
├── .env                 ← vos identifiants PostgreSQL (voir .env.example)
├── RAG/
│   └── chain.py         ← votre RAG existant : init_chain(), ask(chain, question)
└── DASHBOARD/
    ├── app.py
    ├── theme.py
    ├── db.py
    ├── rag_bridge.py
    ├── conversations.py
    ├── charts.py
    ├── components/
    │   ├── sidebar.py · header.py · kpi.py · chat_widget.py
    ├── pages/
    │   ├── dashboard.py · chat.py · conditions.py · performance.py · reglementation.py
    ├── assets/
    │   ├── custom.css
    │   └── logos/       ← 7 logos de banques
    ├── data/            ← conversations.db (SQLite, auto-créé)
    └── requirements.txt
```

### 2. Installation
```bash
cd BACK/DASHBOARD
pip install -r requirements.txt
```

### 3. Configuration
Copiez `.env.example` → `BACK/.env` et renseignez `DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD`.

### 4. Lancement
```bash
python app.py
# → http://localhost:8050
```

---

## Architecture

- **`app.py`** — point d'entrée, routing manuel léger (`dcc.Location`), sidebar collapse + chat flottant en clientside callbacks.
- **`theme.py`** — tokens couleurs + `plotly_layout()` (thème sombre Plotly) + `red_scale()` (dégradé rouge selon montant) + métadonnées des 7 banques.
- **`db.py`** — accès PostgreSQL via `psycopg2`. Chaque helper essaie le SQL puis **retombe sur des données représentatives** si la base est absente (l'UI reste démontrable). ⚡ Les pages d'analyse utilisent le SQL direct, **pas** le RAG, pour la vitesse.
- **`rag_bridge.py`** — initialise `chain` **une seule fois au démarrage** (global), expose `ask_rag(question)`. Mode simulé si le RAG n'est pas joignable.
- **`conversations.py`** — historique SQLite (`conversations`, `messages`), auto-créé.
- **`charts.py`** — **détection auto-chart** : `detect_and_build(question, réponse)` parse les valeurs numériques d'une réponse RAG et génère la figure Plotly adaptée (bar / line / classement).
- **`pages/`** — une page = `layout()` + `register_callbacks(app)`.
- **`components/`** — sidebar, header, KPI cards, widget chat flottant.

## Détection auto-chart (logique demandée)

Dans `charts.py` :
```python
def detect_and_build(question, reponse):
    # mots-clés comparaison → parse valeurs banques → bar/line Plotly
    # affiché DANS la bulle de réponse du chat
```

---

## Ce qui est branché vs. à compléter

| Élément | État |
|---|---|
| Layout, palette, 5 pages, sidebar, header, chat flottant | ✅ complet |
| Graphiques Plotly (bar, radar, line, treemap, podium) | ✅ complet |
| Accès PostgreSQL avec fallback mock | ✅ branché (vérifier noms de colonnes réels : `cb_tarifs.service/montant/annee/semestre/segment`, `ef_indicateurs.indicateur/valeur/annee`) |
| Pont RAG (`init_chain` / `ask`) | ✅ branché (mode simulé si absent) |
| Historique conversations SQLite | ✅ complet |
| Détection auto-chart | ✅ version règle + parsing |
| Streaming mot-à-mot (SSE + dcc.Interval) | 🟡 squelette — à finaliser selon votre `chain` |
| Heatmap & vues Graphiques de la page Conditions | 🟡 vue Tableau complète, toggles présents |

> ⚠️ **Adaptez les requêtes SQL** dans `db.py` aux noms exacts de vos colonnes — je ne connais pas le schéma précis de `cb_tarifs` / `ef_indicateurs`. Les requêtes actuelles sont des hypothèses raisonnables avec fallback.
