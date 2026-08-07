# SpyBusiness — Intelligence bancaire ivoirienne

Système de veille stratégique, de benchmarking concurrentiel et d'aide à la décision pour la
Société Générale Côte d'Ivoire. Il compare SGCI aux six autres principales banques du marché
ivoirien sur leurs conditions tarifaires et leurs états financiers publiés, et restitue des
analyses sourcées via quatre tableaux de bord et un assistant conversationnel.

---

## Lancer l'application

```bash
python server.py          # → http://localhost:5000
```

Prérequis : **PostgreSQL** avec l'extension **pgvector**, et une base alimentée par le pipeline
d'extraction (dossier `PIPELINE/` à la racine du dépôt).

```bash
pip install -r requirements-deploy.txt
```

`requirements-deploy.txt` ne contient que ce dont le serveur a besoin à l'exécution. Le
`requirements.txt` de la racine couvre en plus le pipeline d'extraction PDF (docling, OCR,
torch) — inutile pour faire tourner le dashboard, et beaucoup plus lourd.

### Variables d'environnement

Lues depuis un fichier `.env` à la racine du dépôt.

| Variable | Rôle |
|---|---|
| `DB_HOST` `DB_PORT` `DB_NAME` `DB_USER` `DB_PASSWORD` | Connexion PostgreSQL |
| `GROQ_API_KEY` … `GROQ_API_KEY_12` | Rédaction des analyses. Plusieurs clés = rotation automatique quand l'une atteint son quota |
| `OPENROUTER_API_KEY` | Accès à Claude, appelé en premier sur les analyses CB |
| `GEMINI_API_KEY` | Secours si Groq et Claude sont indisponibles |
| `TAVILY_API_KEY` | Agent de veille web (facultatif — sans elle, les faits sectoriels ne se rafraîchissent pas) |

Sans clé LLM, le dashboard fonctionne : les chiffres, classements et comparaisons sont
calculés en base. Seule la **rédaction** des analyses est indisponible, et un bandeau le signale.

---

## Arborescence

```
spybusiness/
├── server.py              API Flask + point d'entrée unique
├── app.html               page de l'application
├── app.main.js            rendu des pages et des graphiques
├── app.data.js            chargement des données au démarrage
├── app.styles.css         feuille de style
├── assets/logos/          logos des banques
│
├── cache/                 RÉGÉNÉRABLE — supprimable sans perte
├── data/                  À CONSERVER — alimente les analyses
├── archive/               sauvegardes horodatées, hors du chemin de lecture
│
└── dash_app/              modules métier (accès données, analyses, veille)
```

**La distinction `cache/` et `data/` structure tout le reste.** `cache/` contient des résultats
qui se recalculent à partir de la base : les vider ne fait que rallonger le prochain démarrage.
`data/` contient des informations qui ne se trouvent nulle part ailleurs — faits de veille web,
validations d'exclusivités, justifications — et dont la perte serait définitive.

### `cache/`

| Fichier | Contenu |
|---|---|
| `cb_analyses_cache.json` | Analyses rédigées des Conditions bancaires |
| `ef_analyses_cache.json` | Analyses rédigées de la Santé financière |
| `strategie_build_cache.json` | Construction complète de la Stratégie (~100 s à reconstruire) |
| `dashboard_resume_cache.json` | Résumés de section |
| `cb_repricing_cache.json` | Verdicts de repositionnement tarifaire |
| `chat_conversations.json` | Historique des conversations |
| `refresh_state.json` | État du dernier rafraîchissement |

### `data/`

| Fichier | Contenu |
|---|---|
| `web_facts.json` | Faits sectoriels et événements de marché, datés et sourcés (agent de veille) |
| `exclusivites_validation.json` | Exclusivités SGCI vérifiées face aux offres concurrentes |
| `gaps_validation.json` | Manques d'offre confirmés |
| `cb_justifications.json` | Justifications des écarts tarifaires |
| `cb_repricing_web.json` | Éléments de repositionnement issus du web |

### `dash_app/`

**Accès aux données et analyses**

| Module | Rôle |
|---|---|
| `db.py` | Toutes les requêtes PostgreSQL. Point d'entrée unique de la donnée |
| `agents.py` | Façade d'accès par domaine (`AGENTS["CB"]`, `AGENTS["EF"]`…) |
| `cb_sections.py` `cb_subsections.py` `cb_axes.py` | Classification canonique BCEAO des services bancaires |
| `strategie.py` | Diagnostic, SWOT, Porter, VRIST, PESTEL, projection à trois ans |
| `strategie_operationnelle.py` | Opportunités sectorielles notées, business case, décisions par direction |
| `web_facts.py` | Lecture des faits de veille |

**Veille web** — à exécuter périodiquement, pas au démarrage

| Script | Rôle |
|---|---|
| `run_veille.py` | Indicateurs macro et de filière, plus les événements de marché |
| `run_veille_exclusivites.py` | Vérifie que les exclusivités SGCI n'existent pas chez un concurrent |
| `run_veille_gaps.py` | Confirme les manques d'offre |
| `run_veille_repricing.py` | Éléments de contexte pour le repositionnement tarifaire |

```bash
cd dash_app && python run_veille.py            # tout
cd dash_app && python run_veille.py --dry-run  # simulation, aucune écriture
```

**Outils de correction** — ponctuels, jamais appelés par le serveur

`fix_ef_is_primary.py`, `fix_montants_milliers.py` : correctifs de données idempotents. Ils
tournent en **simulation par défaut** et n'écrivent qu'avec `--appliquer`, après sauvegarde.

---

## Principe de conception

Le système repose sur une séparation stricte, qui explique la structure du code :

> **Le déterministe établit, le LLM formule.**

Les chiffres, classements, écarts, notes et priorités sont **calculés en base**. Le modèle de
langage ne les produit pas : il les met en forme. Il ne peut ni inventer un montant, ni modifier
un rang, ni citer un produit absent du catalogue.

Trois conséquences :

- **Traçabilité** — chaque valeur affichée remonte à sa source : ligne de grille tarifaire, poste
  d'état financier, ou fait de veille avec sa date et son URL.
- **Reproductibilité** — à données inchangées, les calculs donnent le même résultat. Les textes
  rédigés sont mis en cache sous une clé dérivée des données injectées : mêmes données, même
  texte servi.
- **Fraîcheur** — un ajout de données invalide les caches concernés et déclenche la
  reconstruction des analyses affectées, sans intervention.

La veille web fait exception : le web change, on ne peut pas rejouer une collecte passée. Elle
est donc **auditable** plutôt que reproductible — chaque fait porte sa valeur, sa date de relevé,
sa source et son lien.

---

## Ajouter des données

Par l'interface, bouton **« Ajouter des données »** : dépôt d'un PDF (grille tarifaire, états
financiers, texte réglementaire), extraction, aperçu avant validation, puis stockage. Une banque
absente de la base est créée automatiquement.

Après l'ajout, **recharger la page** (`Ctrl+Shift+R`) : la liste des banques, les périodes
disponibles et les logos sont lus au chargement.
