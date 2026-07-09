# SpyBusiness — Intelligence Bancaire Ivoirienne

Système complet d'extraction, nettoyage, stockage et analyse des données bancaires ivoiriennes.  
**Objectif** : alimenter un dashboard d'aide à la décision déployé à la SGCI (Direction Générale) — comparer les 7 grandes banques de Côte d'Ivoire sur leurs conditions tarifaires, états financiers et conformité réglementaire.

**Banques** : BACI · BICICI · BNI · ECOBANK · NSIA · SGCI · SIB  
**Période EF** : 2021 → 2025 (fenêtre glissante, 3 dernières années par banque)  
**Période CB** : 2024 → 2026 (S1 + S2 par banque et segment)  
**Base de données** : PostgreSQL 17 + pgvector 0.8.2

---

## Architecture générale

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         PIPELINE DE DONNÉES                                     │
│                                                                                 │
│  DATA/SOURCE/          PIPELINE/            DATA/DONNEES_       PostgreSQL      │
│  ┌────────────┐        ┌──────────────┐     PRETRAITEES/        ┌────────────┐  │
│  │ PDFs/JPGs  │──────▶ │ EXTRACTION   │──▶  ┌──────────────┐   │ cb_tarifs  │  │
│  │ CONDITIONS │        │ pdfplumber   │     │ *_clean.xlsx │──▶│ ef_indic.  │  │
│  │ BANQUES    │        │ Docling OCR  │     │ *_clean.txt  │   │ regl_docs  │  │
│  │ ETATS_FIN  │        │ Vision LLM   │     └──────────────┘   └─────┬──────┘  │
│  │ REGL       │        └──────┬───────┘                              │         │
│  └────────────┘               │         ┌──────────────┐             │         │
│                               ▼         │ NETTOYAGE    │             │         │
│                        ┌──────────────┐ │ layout detect│             │         │
│                        │ DONNEES_     │▶│ repair OCR   │             │         │
│                        │ EXTRAITES/   │ │ normalisation│             │         │
│                        └──────────────┘ └──────┬───────┘             │         │
│                                                │                     │         │
│                                                ▼         ┌───────────┘         │
│                                         ┌──────────────┐ │  STOCKAGE_BD        │
│                                         │ DONNEES_     │─┘  run_stockage.py    │
│                                         │ PRETRAITEES/ │    + pgvector embed.  │
│                                         └──────────────┘                       │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         DASHBOARD & RAG                                         │
│                                                                                 │
│  RAG/                          spybusiness/                                     │
│  ┌──────────────────┐          ┌────────────────────────────────────────────┐   │
│  │ chain.py         │          │ server.py  (Flask :5000)                   │   │
│  │ retriever.py     │◀────────▶│  ├── /api/kpis         KPIs dynamiques     │   │
│  │ prompts.py       │  Groq    │  ├── /api/rn_series    séries temporelles  │   │
│  │ memory.py        │  LLM     │  ├── /api/resilience   ratios solidité     │   │
│  │ config.py        │          │  ├── /api/cb           comparatif tarifs   │   │
│  └──────────────────┘          │  ├── /api/chat         RAG conversationnel │   │
│                                │  ├── /api/approfondir  analyse IA (Groq)   │   │
│                                │  └── /api/radar_agent  portrait IA         │   │
│                                │                                            │   │
│                                │ dash_app/db.py  (couche données)           │   │
│                                │  ├── kpis_vue_ensemble()  ← fenêtre ANx    │   │
│                                │  ├── resultat_net_series()  ← @lru_cache   │   │
│                                │  ├── resilience_data()                     │   │
│                                │  └── frais_tenue_compte()                  │   │
│                                │                                            │   │
│                                │ app.html + app.main.js + app.data.js       │   │
│                                │  Vue d'ensemble · CB · Analyse · Stratégie │   │
│                                └────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Structure complète du projet

```
BACK/
│
├── .env                              ← Credentials (PostgreSQL, DashScope, Groq, OpenAI)
├── .gitignore                        ← venv, __pycache__, captures Selenium, logs, .bak
├── requirements.txt                  ← Toutes les dépendances Python
├── README.md                         ← Ce fichier
├── FORMULES_ET_SOURCES.md            ← Formules OHADA/BCEAO utilisées dans les KPIs (EF)
├── FORMULES_ET_SOURCES_CB.md         ← Formules et sources des indicateurs CB
├── METHODOLOGIE_INDICATEURS_CB.md    ← Méthodologie de calcul des indicateurs CB
├── ARCHITECTURE_RAG_SPYBUSINESS.pdf  ← Document d'architecture (généré par architecture_pdf.py)
├── ARCHITECTURE_SYSTEME_RAG_COMPLET.html ← Schéma d'architecture (version HTML)
├── run_qualite_complete.py           ← Orchestrateur qualité CB (7 étapes)
├── architecture_pdf.py               ← Génère le PDF d'architecture (schémas vectoriels)
├── md_to_pdf.py                      ← Convertisseur Markdown → PDF (style RMarkdown)
│
├── DATA/
│   ├── SOURCE/                       ← Documents bruts originaux (JAMAIS modifiés)
│   │   ├── CONDITIONS_BANQUES/       ← Plaquettes tarifaires PDF/JPG par banque/année
│   │   ├── ETATS_FINANCIERS/         ← Bilans et comptes de résultat PDF par banque
│   │   └── REGLEMENTATION/           ← Textes de loi UEMOA (PDF)
│   │
│   ├── DONNEES_EXTRAITES/            ← Sortie brute de l'extraction
│   │   ├── CONDITIONS_BANQUES/       ← XLSX bruts par banque/année/semestre
│   │   ├── ETATS_FINANCIERS/         ← TXT Docling + XLSX camelot par banque
│   │   └── REGLEMENTATION/           ← TXT Docling par document
│   │
│   └── DONNEES_PRETRAITEES/          ← Fichiers _clean prêts pour la BD
│       ├── CONDITIONS_BANQUES/       ← *_clean.xlsx (10 colonnes normalisées)
│       ├── ETATS_FINANCIERS/         ← *_clean.xlsx format tall (7 colonnes)
│       └── REGLEMENTATION/           ← *_clean.txt (texte propre)
│
├── PIPELINE/
│   ├── EXTRACTION/                   ← Étape 1 : PDF → XLSX/TXT bruts
│   │   ├── run_extraction.py         ← Orchestrateur (--type, --banques)
│   │   ├── extract_native.py         ← PDF natifs → XLSX (pdfplumber + camelot)
│   │   ├── extract_scanned.py        ← PDF scannés → TXT/XLSX (Docling)
│   │   └── extract_cb_txt.py         ← CB non tabulaires → texte brut (regex CODE LIBELLE VALEUR)
│   │
│   ├── NETTOYAGE/                    ← Étape 2 : XLSX bruts → _clean normalisés
│   │   └── run_nettoyage.py          ← Détection layout + repair + normalisation
│   │
│   ├── STOCKAGE_BD/                  ← Étape 3 : _clean → PostgreSQL
│   │   ├── run_stockage.py           ← Chargement CB + EF + REGL + schéma pgvector
│   │   ├── run_repair_structure.py   ← Reclassification type_valeur AUTRE
│   │   ├── run_repair_sections.py    ← Réparation sections manquantes (3 couches)
│   │   └── run_repair_contexte.py    ← Reconstruction contexte hiérarchique
│   │
│   └── VECTORISATION/                ← Étape 4 : embeddings → colonnes vector(768)
│
├── RAG/                              ← Agent conversationnel et analyse IA
│   ├── chain.py                      ← Orchestration déterministe : routeur + branche comparative + génération
│   ├── config.py                     ← Paramètres LLM (modèle, température, tokens)
│   ├── main.py                       ← Point d'entrée CLI pour tester le RAG
│   ├── memory.py                     ← Gestion de l'historique de conversation
│   ├── prompts.py                    ← Templates de prompts (system, user, contexte)
│   ├── retriever.py                  ← PGVectorStore — recherche sémantique pgvector
│   └── structured_tools.py           ← Comparaison multi-banques par agrégation SQL (questions « quelle banque… »)
│
└── SGCI Strategic Intelligence — Design System/
    └── spybusiness/                  ← APPLICATION DE PRODUCTION
        │
        ├── server.py                 ← Serveur Flask (port 5000) — API + fichiers statiques
        │
        ├── app.html                  ← Shell HTML de la SPA (sidebar + header + ticker)
        ├── app.main.js               ← Logique UI : vues, graphiques Plotly, filtres ANx
        ├── app.data.js               ← Couche API : APERCU_FILTERS, reloadKpis(), fetch
        ├── app.styles.css            ← Design system (dark/light, variables CSS)
        │
        ├── assets/                   ← Logos banques (SGCI.png, BACI.png …) — SEULE copie servie
        │
        ├── cb_analyses_cache.json    ← Cache LLM : analyses CB + recommandations des 4 directions
        ├── ef_analyses_cache.json    ← Cache LLM : analyses Santé Financière (23 blocs / segment)
        ├── strategie_build_cache.json← Cache disque du build Stratégie (0 s au redémarrage)
        ├── strategie_narr_cache.json ← Cache LLM : verdict « L'essentiel » + lectures de sections
        ├── cb_repricing_cache.json   ← Cache LLM : verdicts tarifaires (colonne Action / Récap)
        ├── cb_justifications.json    ← Justifications CB pré-calculées
        ├── plotly-2.35.2.min.js      ← Bundle Plotly servi en statique
        ├── warmup_cache.py           ← Pré-chauffage du cache LLM (optionnel, après ingestion)
        │
        └── dash_app/                 ← COUCHE AGENTS / DONNÉES (importée par server.py)
            ├── agents.py             ← FAÇADE RAG — porte d'entrée unique (CB · EF · REGL · WEB)
            ├── db.py                 ← Outils structurés (SQL PostgreSQL) des agents CB/EF
            ├── strategie.py          ← Niveau 3 : orchestration stratégie (SWOT/Porter/VRIST/décrypt./roadmap)
            ├── web_facts.py          ← Accesseurs de la veille web (Agent WEB)
            ├── web_facts.json        ← Faits web cités & sourcés (secteur, banques, innovations, réglementation)
            ├── run_veille.py         ← Collecte reproductible de la veille web
            ├── cb_axes.py            ← Référentiel des axes d'analyse CB
            ├── cb_sections.py        ← Référentiel des sections CB
            └── cb_subsections.py     ← Référentiel des sous-sections CB
```

---

## Schéma du code — Flask + Frontend

```
┌─────────────────────────────────────────────────────────────────────┐
│  NAVIGATEUR                                                         │
│                                                                     │
│  app.html                                                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  <div id="view">  ←── go(page) injecte le HTML de la vue    │   │
│  │  ┌────────────────────────────────────────────────────────┐  │   │
│  │  │ Vues disponibles :                                     │  │   │
│  │  │  apercu    → Santé financière (KPIs + graphiques EF)   │  │   │
│  │  │  cb        → Conditions bancaires (tableau CB)         │  │   │
│  │  │  analyse   → Analyse approfondie                       │  │   │
│  │  │  strategie → Portrait radar + recommandations          │  │   │
│  │  │  rapports  → Export PDF                               │  │   │
│  │  │  chat      → RAG conversationnel                      │  │   │
│  │  └────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  app.data.js              app.main.js                               │
│  ┌──────────────────┐     ┌────────────────────────────────────┐    │
│  │ APERCU_FILTERS = │     │ go(page)    → charge la vue        │    │
│  │  frais_annee:2026│     │ reloadKpis()→ fetch /api/kpis      │    │
│  │  frais_sem: "S1" │────▶│ setApercuFilter(key, val)          │    │
│  │  frais_seg: "Par"│     │  → APERCU_FILTERS[key] = val       │    │
│  │  rn_anx: 3       │     │  → reloadKpis() → go("apercu")     │    │
│  └──────────────────┘     │                                    │    │
│                           │ Filtres ANx (boutons AN1/AN2/AN3)  │    │
│                           │  rn_anx=1 → AN1 de chaque banque  │    │
│                           │  rn_anx=2 → AN2 de chaque banque  │    │
│                           │  rn_anx=3 → AN3 (défaut)          │    │
│                           └────────────────────────────────────┘    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP GET/POST
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  server.py  (Flask :5000)                                           │
│                                                                     │
│  Routes statiques :                                                 │
│   GET /          → app.html                                         │
│   GET /<fichier> → app.main.js, app.styles.css, assets/…           │
│                                                                     │
│  Routes API :                                                       │
│   GET  /api/kpis          ?frais_annee&frais_sem&frais_seg&rn_anx  │
│   GET  /api/rn_series     → séries temporelles RN toutes banques   │
│   GET  /api/rn_anx        ?anx=1|2|3                               │
│   GET  /api/resilience    ?anx=1|2|3                               │
│   GET  /api/cb            ?annee&semestre&segment                  │
│   GET  /api/cb_annees     → années CB disponibles (dynamique)      │
│   GET  /api/frais         ?annee&semestre&segment                  │
│   GET  /api/frais_detail  ?annee&semestre&segment                  │
│   GET  /api/stats         → statistiques globales BD               │
│   GET  /api/regl          ?q=<recherche>                            │
│   POST /api/chat          {"question": "…"}  → RAG                │
│   POST /api/approfondir   {"question":"…","kpis":{…}} → Groq LLM  │
│   GET  /api/radar_agent   ?bank&annee&sem&seg&anx → portrait IA   │
│                                                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ import db
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  dash_app/db.py  — Couche données                                   │
│                                                                     │
│  @lru_cache(maxsize=1)                                              │
│  resultat_net_series()     ← SOURCE DE VÉRITÉ des années/banques   │
│    └── SELECT banque, annee_donnee, AVG(montant)                    │
│           FROM ef_indicateurs WHERE is_primary=TRUE                 │
│           AND libelle ILIKE '%résultat%net%'                        │
│    └── Retourne {banque: {annee: montant, …}, …}                    │
│    └── Cache invalidé uniquement au redémarrage du serveur          │
│                                                                     │
│  kpis_vue_ensemble(frais_annee, frais_sem, frais_seg, rn_anx)      │
│    ├── Appelle resultat_net_series() → fenêtre par banque           │
│    ├── bank_anx = {banque: {1: AN1, 2: AN2, 3: AN3}} (3 dernières) │
│    ├── cible = bank_anx[banque][rn_anx]  ← INDEX PER BANQUE        │
│    ├── SELECT ef_indicateurs WHERE annee = ANY([toutes cibles])     │
│    ├── Filtre Python : if annee != rn_year_map[banque]: skip        │
│    └── Retourne ~30 champs : rn, pnb, roe, marge, coeff_expl, …   │
│                                                                     │
│  resilience_data(anx)         → ratios solidité par ANx             │
│  rn_by_anx(anx)               → RN par banque à l'ANx donné        │
│  frais_tenue_compte(…)        → frais min non-zéro par banque       │
│  virements_locaux(…)          → tarifs virements par banque         │
│  cb_comparatif(…)             → tableau croisé services × banques   │
│  cb_annees()                  → années CB dispo (dynamique)         │
│  regl_search(q)               → recherche texte réglementaire       │
│  ef_series_all_for_agent()    → séries EF complètes pour radar IA  │
│  stats_globales()             → COUNT(*) par table                  │
│                                                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ psycopg2
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PostgreSQL 17 — intelligence_bancaire                              │
│                                                                     │
│   cb_tarifs       ~30 000 lignes  (conditions tarifaires CB)        │
│   ef_indicateurs  ~1 800 lignes   (états financiers EF)             │
│   regl_documents  ~200 chunks     (réglementation UEMOA)            │
│   banques         7 lignes        (référentiel banques)             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Logique des fenêtres ANx (per-bank)

Chaque banque a ses **3 dernières années disponibles** : AN1 = la plus ancienne, AN3 = la plus récente.

```
resultat_net_series()  ←  source de vérité (lru_cache)
        │
        ▼
 Pour chaque banque :
 bank_years = sorted(annees_disponibles)
 last3 = bank_years[-3:]      ← toujours les 3 dernières
        │
        ├── SGCI / BICICI / ECOBANK / NSIA / SIB
        │   → données 2021–2025 (5 ans disponibles)
        │   → last3 = [2023, 2024, 2025]
        │   → AN1=2023  AN2=2024  AN3=2025
        │
        └── BACI / BNI
            → données 2021–2023 (3 ans disponibles)
            → last3 = [2021, 2022, 2023]
            → AN1=2021  AN2=2022  AN3=2023

rn_anx=1  → requête à 2023 pour SGCI/… et à 2021 pour BACI/BNI
rn_anx=2  → requête à 2024 pour SGCI/… et à 2022 pour BACI/BNI
rn_anx=3  → requête à 2025 pour SGCI/… et à 2023 pour BACI/BNI

Future-proofing : quand 2026 sera ajouté pour SGCI,
resultat_net_series() (après restart) donnera last3=[2024,2025,2026]
→ AN3 devient 2026 automatiquement. Zéro modification de code.
```

---

## Schéma de la base de données

```sql
-- Référentiel des banques
CREATE TABLE banques (
    code        TEXT PRIMARY KEY,   -- 'SGCI'
    nom_complet TEXT,               -- 'Société Générale Côte d\'Ivoire'
    groupe      TEXT,               -- 'Société Générale'
    segments    TEXT                -- 'Particuliers,Entreprises'
);

-- Conditions tarifaires (CB)
CREATE TABLE cb_tarifs (
    id            SERIAL PRIMARY KEY,
    banque        TEXT    NOT NULL,  -- 'SGCI'
    annee         INTEGER NOT NULL,  -- 2024
    semestre      TEXT    NOT NULL,  -- 'S1'
    segment       TEXT    NOT NULL,  -- 'Entreprises' | 'Particuliers'
    feuille       TEXT,              -- 'T0'
    section       TEXT,              -- '1.1.1.1'
    contexte      TEXT,              -- fil d'ariane hiérarchique
    libelle       TEXT    NOT NULL,  -- 'Frais de tenue de compte'
    valeur_brute  TEXT,              -- '5 000 FCFA / mois'
    valeur_propre TEXT,              -- '5000'
    montant       REAL,              -- 5000.0
    est_gratuit   BOOLEAN,           -- TRUE si valeur = 'GRATUIT'
    unite         TEXT,              -- 'FCFA'
    embedding     vector(768)        -- NULL jusqu'à vectorisation
);

-- États financiers (EF)
CREATE TABLE ef_indicateurs (
    id            SERIAL PRIMARY KEY,
    banque        TEXT    NOT NULL,  -- 'ECOBANK'
    fichier       TEXT,              -- 'AN2' (nom fichier source)
    libelle       TEXT    NOT NULL,  -- 'Produit Net Bancaire'
    annee_label   TEXT    NOT NULL,  -- '2024' (tel qu'écrit dans le doc)
    annee_donnee  INTEGER,           -- 2024 (numérique)
    annee_rapport INTEGER,           -- 2024 (max des années du fichier)
    is_primary    BOOLEAN,           -- TRUE si annee_donnee == annee_rapport
    unite         TEXT,              -- 'millions FCFA'
    valeur_brute  TEXT,              -- '215 101'
    valeur_propre TEXT,              -- '215101'
    montant       REAL,              -- 215101.0
    embedding     vector(768)
);
-- NOTE : is_primary évite les doublons N/N-1
-- → WHERE is_primary=TRUE donne exactement 1 ligne par banque par année

-- Réglementation UEMOA (chunks pour RAG)
CREATE TABLE regl_documents (
    id           SERIAL PRIMARY KEY,
    fichier      TEXT    NOT NULL,   -- 'REGLEMENTATION JURIDIQUE BANCAIRE UEMOA'
    chunk_index  INTEGER NOT NULL,
    contenu      TEXT    NOT NULL,   -- ~500 mots
    tokens_count INTEGER,
    embedding    vector(768),
    UNIQUE (fichier, chunk_index)
);
```

---

## Les 3 types de données

### CONDITIONS DE BANQUES (CB)
Plaquettes tarifaires publiées chaque semestre par chaque banque.

- **Segments** : `E` = Entreprises · `P` = Particuliers
- **Semestres** : `S1` · `S2`
- **Couverture** : 70 fichiers _clean · ~30 000 lignes

| Banque | 2024 | 2025 | 2026 |
|--------|------|------|------|
| BACI | S1_E · S2_E · S1_P · S2_P | S1_E · S2_E · S1_P · S2_P | S1_E · S1_P |
| BICICI | S1_E · S2_E · S1_P · S2_P | S1_E · S2_E · S1_P · S2_P | S1_E · S1_P |
| BNI | S1_E · S2_E · S1_P · S2_P | S1_E · S2_E · S1_P · S2_P | S1_E · S1_P |
| ECOBANK | S1_E · S2_E · S1_P · S2_P | S1_E · S2_E · S1_P · S2_P | S1_E · S1_P |
| NSIA | S1_E · S2_E · S1_P · S2_P | S1_E · S2_E · S1_P · S2_P | S1_E · S1_P |
| SGCI | S1_E · S2_E · S1_P · S2_P | S1_E · S2_E · S1_P · S2_P | S1_E · S1_P |
| SIB | S1_E · S2_E · S1_P · S2_P | S1_E · S1_P | — |

### ÉTATS FINANCIERS (EF)
Bilans et comptes de résultat annuels — couverture 2021 → 2025.

- **is_primary** : chaque rapport contient N et N-1. `is_primary=TRUE` isole l'année principale (évite les doublons).
- **Fenêtre ANx** : analyse sur les 3 dernières années disponibles par banque (voir section ci-dessus).

### RÉGLEMENTATION (REGL)
Textes de loi UEMOA découpés en chunks pour recherche sémantique (RAG).

- `LOI DE CONSOMMATION` — protection des consommateurs bancaires
- `REGLEMENTATION JURIDIQUE BANCAIRE UEMOA` — cadre prudentiel BCEAO

---

## Lancer le dashboard

```bash
cd "SGCI Strategic Intelligence — Design System/spybusiness"
python server.py
# → http://localhost:5000
```

Le serveur :
1. Importe `db` depuis `dash_app/db.py` → connexion PostgreSQL
2. Essaie d'initialiser le RAG (`RAG/chain.py`) → optionnel
3. Sert `app.html` sur `/` + tous les assets statiques
4. Expose les routes `/api/*`

---

## Pipeline d'exécution

### Étape 1 — Extraction

Fallback automatique CB :
```
PDF natif → pdfplumber
    si < 200 cellules → Docling (OCR)
        si format non tabulaire → extract_cb_txt.py (texte brut, regex CODE LIBELLE VALEUR)
```
> Le fallback Vision LLM (qwen-vl-max) a été **retiré** (commit `18b3262`) : il était
> source d'hallucinations sur des données tarifaires. L'extraction CB est désormais
> 100 % déterministe (pdfplumber / Docling / texte brut).

Fallback automatique EF :
```
Docling TXT (tous types)
    si < 2 000 bytes → re-extraction
PDF natif → camelot XLSX (tableaux structurés)
    si < 20 cellules → re-extraction
```

```bash
cd PIPELINE/EXTRACTION
python run_extraction.py                    # tout traiter
python run_extraction.py --type conditions  # CB seulement
python run_extraction.py --type etats       # EF seulement
python run_extraction.py --banques SGCI SIB # filtrer des banques
```

### Étape 2 — Nettoyage

```bash
cd PIPELINE/NETTOYAGE
python run_nettoyage.py          # tout nettoyer
python run_nettoyage.py --cb     # CB seulement
python run_nettoyage.py --ef     # EF seulement
python run_nettoyage.py --regl   # REGL seulement
```

**Layouts CB détectés automatiquement** :
- `3col` standard · `4col_split` BICICI · `5col_dual` NSIA · `3col_wide` inconnu

### Étape 3 — Stockage BD

```bash
cd PIPELINE/STOCKAGE_BD

# Première fois :
python run_stockage.py --init    # crée extension vector + tables + index

# Chargement :
python run_stockage.py           # CB + EF + REGL
python run_stockage.py --cb      # CB seulement
python run_stockage.py --ef      # EF seulement
python run_stockage.py --reset   # vide et recharge tout
```

### Qualité CB — run_qualite_complete.py

Script central à lancer après chaque extraction ou ajout de données.

```bash
python run_qualite_complete.py
```

| # | Étape | Rôle |
|---|-------|------|
| 0 | Backup protégé | Sauvegarde fichiers imputés |
| 1 | run_nettoyage --cb | Nettoyage et homogénéisation |
| 1b | run_imputation_baci_s2 | Imputation BACI S2 2025 ← S1 2026 |
| 2 | Audit SQL | Vérification exhaustivité (seuil 200 lignes/tranche) |
| 3 | run_stockage --reset --cb | Reset + rechargement complet BD |
| 4 | SQL artefacts | Suppression doublons et headers résiduels |
| 5 | run_repair_structure | Reclassification type_valeur AUTRE |
| 5b | run_repair_sections | Réparation sections (3 couches : inversion OCR → backward fill → Jaccard) |
| 6 | run_repair_contexte | Reconstruction contexte hiérarchique |
| 7 | Audit final SQL | Verdict par banque (3 critères qualité) |

**Critères qualité cibles** :

| Critère | Seuil |
|---------|-------|
| Lignes par tranche | ≥ 200 |
| % type AUTRE | < 5% |
| % sans section | < 5% |
| % sans contexte | < 8% |

---

## Configuration

### Fichier `.env`
```
# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=intelligence_bancaire
DB_USER=postgres
DB_PASSWORD=<mot_de_passe>

# DashScope Vision LLM (extraction CB scannés)
ALIBABA_BASE_URL_INTL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
ALIBABA_API_KEY=<cle_1>
ALIBABA_API_KEY_2=<cle_2>
# … jusqu'à ALIBABA_API_KEY_18

# Groq (TOUTES les analyses LLM : EF, CB, Stratégie, radar — rotation multi-clés)
GROQ_API_KEY=<cle>
GROQ_API_KEY_2=<cle_2>
# … jusqu'à GROQ_API_KEY_12  (⚠ quota 100 000 tokens/jour PAR organisation Groq)

# Optionnels : GEMINI_API_KEY (repli), ANTHROPIC_API_KEY + CB_USE_CLAUDE=1 (repricing via Claude)
```

### Prérequis système
- Python 3.11+
- PostgreSQL 17 + extension pgvector 0.8.2
- `pip install -r requirements.txt`

### Création de la base (une seule fois)
```sql
-- Dans pgAdmin ou psql :
CREATE DATABASE intelligence_bancaire;
-- Puis :
python PIPELINE/STOCKAGE_BD/run_stockage.py --init
```

---

## Choix techniques clés

| Décision | Choix | Raison |
|----------|-------|--------|
| Base de données | PostgreSQL 17 + pgvector | SQL structuré + RAG vectoriel en une seule BD, accès concurrent multi-utilisateurs |
| Fenêtres ANx | Per-bank (3 dernières années dispo) | BACI/BNI n'ont que 2021–2023 ; imposer 2023–2025 à toutes serait faux |
| Cache RN | `@lru_cache(maxsize=1)` | `resultat_net_series()` est la source de vérité ; restart = invalidation |
| `is_primary` EF | Champ booléen | Chaque rapport EF contient N et N-1 → filtre pour éviter les doublons |
| `ANY(%s)` psycopg2 | Liste Python → tableau PG | Requête EF unifiée sur toutes les années cibles, filtrée en Python |
| temperature=0 | Tous appels LLM extraction | Zéro hallucination tolérée sur des données financières |
| Embeddings locaux | sentence-transformers | Données bancaires confidentielles, pas de quota API externe |
| Extraction CB | pdfplumber / Docling / texte brut (sans Vision LLM) | Déterminisme total : le fallback Vision LLM hallucinait des tarifs → retiré |
| Façade AGENTS | `dash_app/agents.py` (CB · EF · REGL · WEB) | Porte d'entrée RAG unique : une seule architecture, pas de pipeline parallèle |
| Groq LLM | llama-3.3-70b-versatile (repli Gemini) | Analyse approfondie, portrait radar, stratégie — rotation de clés + circuit breaker |

---

## Couche d'analyse LLM — 100 % des analyses affichées

**Principe** : le déterministe calcule les **FAITS** (chiffres, rangs, médianes — depuis PostgreSQL),
le **LLM rédige toute la prose** affichée (registre soutenu, ancré sur ces faits → zéro hallucination),
le résultat est **caché sur disque** (aucun appel répété), et le **fallback** calculé depuis la BD ne
s'affiche que si le LLM est indisponible au moment d'une régénération.

| Endpoint | Rôle | Cache |
|---|---|---|
| `/api/ef_analyses_llm` | Santé Financière : 23 blocs/segment (analyses sous chaque graphe, 4 Signaux Analytiques avec question de transition, bascule ROE/PNB) | `ef_analyses_cache.json` |
| `/api/strategie_narr` | Stratégie : verdict « L'essentiel » + points + surveiller | `strategie_narr_cache.json` |
| `/api/strategie_narr2` | Stratégie : lectures Diagnostic / SWOT / Porter / VRIST / Plan + récit « En clair » de chaque révélation | `strategie_narr_cache.json` |
| `/api/strategie_llm` | 4 directions × **exactement 4 recommandations** (auto-réparation si limite tokens/minute) | `cb_analyses_cache.json` |
| `/api/cb_repricing` | Verdicts tarifaires par service (colonne Action + Récap) | `cb_repricing_cache.json` |
| `/api/radar_agent` | Portrait compétitif : **scores 100 % math (BD)** + explications & synthèse LLM | `cb_analyses_cache.json` |

**Évolutivité (garantie mécanique)** — les clés de cache LLM sont dérivées d'un **hash des faits** :
de nouvelles données (banque, année, chiffres) ⇒ hash différent ⇒ **régénération automatique**.
L'ingestion (« Ajouter des données » dans l'app, `PIPELINE/ingest.py`) purge en plus
`ef_analyses_cache.json`, `strategie_build_cache.json`, `strategie_narr_cache.json` et rafraîchit la
liste des banques (`db.refresh_banks()`), lue dynamiquement partout (front `CB_BANKS`, radar, Stratégie).

---

## État actuel (juillet 2026)

| Étape | Statut |
|-------|--------|
| Extraction / nettoyage / stockage (CB 70 · EF 18 · REGL 2) | ✅ PostgreSQL ~30 000 cb_tarifs · ~1 800 ef_indicateurs |
| Dashboard Flask (Santé Financière · CB · Stratégie · chat RAG) | ✅ :5000, mode onglets |
| Analyses **100 % LLM** (EF · CB · Stratégie · radar) + caches évolutifs | ✅ (voir section ci-dessus) |
| Stratégie N3 (Essentiel+Diagnostic fusionnés · Révélations · Porter · VRIST · SWOT · PESTEL · 4×4 décisions) | ✅ |
| Repricing CB intelligent (barrières de sortie, PNB, garde-fous) | ✅ |
| Veille web sourcée (`web_facts.json` + `run_veille*.py`) — faits externes JAMAIS en dur | ✅ |
| Ingestion in-app (« Ajouter des données », nouvelle banque + logo) | ✅ |
| Vectorisation CB (embeddings) · rapports PDF | ⏳ À faire |

### Mise en production — points d'attention
1. `server.py` tourne sous le serveur de dev Flask (`threaded=True`) : derrière un reverse-proxy
   interne c'est acceptable ; sinon envisager `waitress-serve --port=5000 server:app`.
2. **Clés API dans `.env`** (jamais commitées) ; régénérer toute clé ayant transité en clair.
3. PostgreSQL doit être démarré avant le serveur (service Windows, ou `pg_ctl start -D C:\pgdata -w`).
4. Premier affichage d'un segment/banque non caché = 1 appel LLM (~10 s) puis instantané (cache disque).
5. Quota Groq : 100 K tokens/jour/organisation — les caches rendent l'usage courant quasi nul ;
   seules les ingestions déclenchent des régénérations.

---

## Ajouter de nouvelles données

### Nouvelle année EF (ex : 2026)
1. Déposer le PDF dans `DATA/SOURCE/ETATS_FINANCIERS/<BANQUE>/`
2. `python PIPELINE/EXTRACTION/run_extraction.py --type etats --banques <BANQUE>`
3. `python PIPELINE/NETTOYAGE/run_nettoyage.py --ef`
4. `python PIPELINE/STOCKAGE_BD/run_stockage.py --ef`
5. Redémarrer `server.py` → `resultat_net_series()` se recalcule → fenêtres ANx se décalent automatiquement

### Nouvelle banque
1. Déposer les PDFs dans `DATA/SOURCE/CONDITIONS_BANQUES/<NOM>/` et `ETATS_FINANCIERS/<NOM>/`
2. Ajouter le code banque dans `BANQUES_REF` de `run_stockage.py`
3. `python PIPELINE/EXTRACTION/run_extraction.py --banques <NOM>`
4. `python PIPELINE/NETTOYAGE/run_nettoyage.py --cb --banques <NOM>`
5. `python run_qualite_complete.py`

### Nouvelles clés API
- **DashScope** : coller dans `.env` (slots `ALIBABA_API_KEY` à `ALIBABA_API_KEY_18`)
- **Groq** : coller dans `.env` (slots `GROQ_API_KEY` à `GROQ_API_KEY_12`) — privilégier des clés d'organisations différentes (quota journalier par org)

### Ajouter des données SANS quitter le dashboard
Bouton **« Ajouter des données »** (sidebar) → upload CB/EF/REGL/DOC, aperçu, stockage ciblé,
création d'une **nouvelle banque** (avec logo, sinon badge à initiales généré). À l'issue :
banques rafraîchies + caches purgés → toutes les analyses se régénèrent sur les nouveaux chiffres.

---

## Problèmes résolus pendant le développement

**Filtres ANx statiques** — `rn_anx=N` signifiait "afficher les N dernières années" → `rn_anx=1` ne donnait qu'une seule année globale. Corrigé : `rn_anx` est maintenant un index dans la fenêtre propre de chaque banque, calculé depuis `resultat_net_series()`.

**BACI/BNI fenêtre incorrecte** — une fenêtre globale [2023, 2024, 2025] excluait les données 2021/2022 de BACI et BNI. Corrigé : fenêtre per-bank `last3 = bank_years[-3:]`.

**Duplication N/N-1 dans les EF** — chaque rapport EF contient l'année courante ET l'année précédente. Sans filtre, une requête "PNB 2024" retournait deux lignes par banque. Résolu : champ `is_primary` + `WHERE is_primary=TRUE`.

**ECOBANK PDFs scannés 10 MB** — PDFs dégradés haute résolution. Docling extrait 508–845 cellules brutes inutilisables. Résolu : Vision LLM (qwen-vl-max, double passe, 6 strips par page, DPI=300).

**BACI/SIB format CB non tabulaire** — `pdfplumber extract_tables()` retournait 18 colonnes garblées. Résolu : `extract_cb_text.py` lit le texte brut et détecte les patterns `CODE LIBELLE VALEUR` par regex.

**Texte vertical dans REGL** — Docling extrait les textes marginaux lettre par lettre (`A\nB\nC\n…`). Résolu : `_remove_vertical_text()` supprime les séquences de 4+ lettres isolées consécutives.

**`git mv PIPELINE_2 → EXTRACTION`** — `git mv` échouait car un fichier supprimé sur disque était encore tracké par git. Résolu : `git rm --cached` puis `git mv`.
