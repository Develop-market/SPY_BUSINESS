# SpyBusiness — repères pour une nouvelle session

Projet de **ZONGO MESSOU Alphée Colombe**, mémoire de master à l'*International Datascience
Institute*, filière Data Science, Big Data et Intelligence Artificielle. Stage à la **Société
Générale Côte d'Ivoire (SGCI)**, avril → septembre 2026.
Encadrants : **M. MONSIA DOUGBAN** (académique), **M. MOUAHA HANDY** (maître de stage).

Deux livrables, à ne pas confondre :

| | Où | Quoi |
|---|---|---|
| **L'application** | ce dépôt | SpyBusiness — veille concurrentielle bancaire |
| **Le mémoire** | `C:\Users\ALPHEE COLOMBE\Desktop\MEMOIRE_LATEX` | document XeLaTeX, **81 pages maximum** |

---

## 1. Ce que fait l'application

Compare la SGCI à **six concurrents** (BACI, BICICI, BNI, ECOBANK, NSIA, SIB) sur trois
matières publiques : **grilles tarifaires** semestrielles, **états financiers** annuels,
**textes réglementaires** BCEAO/UEMOA.

Cinq écrans : Santé financière · Conditions bancaires · Stratégie · Stratégie opérationnelle ·
Assistant conversationnel.

**Le principe qui gouverne tout le code :

> *le déterministe établit, le LLM formule.*

Aucun chiffre ne vient d'un modèle de langage. Les montants, rangs, écarts et médianes sont
calculés en SQL ; le modèle ne fait que rédiger autour de faits qu'on lui impose. Toute
proposition qui reviendrait à faire produire un nombre par le LLM est à refuser.

---

## 2. Où sont les choses

```
BACK/
├── SGCI Strategic Intelligence — Design System/spybusiness/
│   ├── server.py            Flask — toutes les routes /api/*
│   ├── app.html             coquille ; app.main.js (~9 000 l.) ; app.data.js
│   └── dash_app/
│       ├── db.py            TOUT le SQL. query() rend [] en cas d'erreur, execute() PROPAGE
│       ├── securite.py      comptes, rôles, droits par section, journal
│       ├── directives.py    les 20 directives de la Stratégie opérationnelle
│       ├── strategie_operationnelle.py   dossiers sectoriels
│       └── cache/           analyses rédigées, versionnées par clé
├── RAG/                     chain.py · retriever.py · config.py  (chat)
├── PIPELINE/                extraction PDF→BD — NON déployé (dépendances énormes)
├── DATA/SOURCE/             plaquettes et états financiers d'origine
├── wsgi.py · build.py · render.yaml     déploiement
└── migrer_vers_supabase.py  transport de la base vers l'hébergeur
```

Le dossier de l'application contient **un tiret cadratin** (`—`) et des espaces. Ne jamais en
dépendre dans une ligne de commande : `pip` a réellement échoué dessus, coupant au premier
espace. `wsgi.py` et `build.py` résolvent le chemin en Python, et le CHERCHENT plutôt que de
l'écrire en dur.

---

## 3. Faire tourner

```bash
# Local — PostgreSQL 'intelligence_bancaire' + pgvector + pg_trgm
cd "SGCI Strategic Intelligence — Design System/spybusiness" && python server.py
# → http://localhost:5000   admin / @Dmin124
```

Secrets dans `BACK/.env` (**exclu de git, ne jamais l'y mettre**) : `DB_*`, `APP_SECRET_KEY`,
`APP_ADMIN_PASSWORD`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `HF_TOKEN`.

**En ligne : https://spybusiness.onrender.com** — Render (plan gratuit) + base **Supabase**.
`render.yaml` est lu par le Blueprint ; la branche déployée est `main`.

Le plan gratuit **endort le service après 15 minutes** : le premier accès prend ~1 minute.
Avant une démonstration, ouvrir la page cinq minutes avant.

---

## 4. Sécurité

Porte unique : `@app.before_request _controle_acces()` — aucun `/api/*` ne répond sans session.
Droits **par section**, pas seulement par rôle : l'administrateur coche ce que chaque compte
voit. Le rôle `admin` est un **second verrou** sur `/api/admin/*` — une case cochée par erreur
ne suffit pas.

Mots de passe : scrypt + sel, via `werkzeug.security`. Blocage 5 min après 5 échecs.
**Sans compte créé par l'administrateur, aucun accès** — vérifié par 11 contrôles.

L'administration vit **dans** l'application (onglet Administration), pas dans une interface
séparée. Une console à part a été construite puis **révoquée** : ce n'était pas la demande.

---

## 5. Pièges déjà rencontrés — ne pas les repayer

**`db.query()` avale les erreurs et rend `[]`.** C'est la source de presque tous les bugs
silencieux de ce projet : une requête invalide, un chemin mort, une extension manquante
donnent un écran vide sans le moindre message. Cinq chemins morts ont ainsi ignoré
1 240 validations sourcées pendant des semaines. Devant un écran vide, **toujours** vérifier
que la requête passe, avant de soupçonner les données.

**Tri non déterministe.** `DISTINCT ON` sans départage complet rendait des résultats
différents sur deux copies identiques de la base — un simple `VACUUM` déplaçait les chiffres.
Corrigé en ajoutant `o.libelle, o.id, s.id`. Tout nouveau `DISTINCT ON` doit être départagé
jusqu'à l'unicité.

**Serveurs zombies (rencontré 3 fois).** `TaskStop` ne tue pas le processus Python : le port
5000 reste tenu par un ancien serveur qui sert l'ANCIEN code. Avant de relancer :
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*server.py*' } | Stop-Process -Force
```

**Heredoc et antislashs.** Écrire un script Python par heredoc dans bash altère les `\n` et les
accents. Utiliser l'outil Write.

**Console Windows en cp1252.** Un script qui affiche « → » ou « — » meurt sur son propre
message. Mettre `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")`.

**`innerText` respecte `text-transform`.** Un libellé stylé en majuscules revient en
CAPITALES : comparer sans tenir compte de la casse, sinon le test échoue à tort.

---

## 6. Performance — ce qui a été mesuré

Sur l'instance hébergée, chaque requête traverse le réseau. Mesures réelles :

| | Avant | Après |
|---|---|---|
| Stratégie opérationnelle | 162 s | 0,7 s |
| Évolution sur 3 ans | 73 s | 0,9 s |

Deux causes, toutes deux non évidentes :

1. **Le préchauffage monopolisait le processeur.** Il calculait 12 combinaisons (3 ans × 2
   semestres × 2 segments) sur une instance à **0,1 CPU** : les requêtes de l'utilisateur
   attendaient derrière. Réduit à la période courante, avec une pause entre calculs.
2. **Le cache mémoire ne servait jamais le premier visiteur** — celui qui réveille le service.
   Les résultats coûteux vivent désormais dans la table **`cache_app`** (base), qui survit aux
   réveils *et* aux redéploiements. Vidée à chaque ingestion.

L'interface : un **écran de chargement** (cercle + pourcentage réel, page floutée) à chaque
changement d'onglet. Le taux ne redescend jamais et finit toujours à 100 %. Filet à 25 s.

---

## 7. Le mémoire

`C:\Users\ALPHEE COLOMBE\Desktop\MEMOIRE_LATEX` — XeLaTeX, compilé deux fois.

```bash
cd "C:/Users/ALPHEE COLOMBE/Desktop/MEMOIRE_LATEX"
xelatex -interaction=nonstopmode memoire.tex && xelatex -interaction=nonstopmode memoire.tex
cp memoire.pdf "C:/Users/ALPHEE COLOMBE/Desktop/MEMOIRE MASTER ZONGO COLOMBE.pdf"
```

**81 pages, plafond ferme.** Vérifier après chaque compilation, ainsi que
`grep -cE '^! '` (erreurs) et `Overfull \hbox` (débordements) — les deux doivent être à 0.

TinyTeX ne peut pas installer de paquets : `setspace`, `eso-pic`, `caption`, `enumitem` et
`babel-french` sont **absents**. Ne pas les utiliser.

Contraintes de forme demandées : cadre sur chaque page, titre de chapitre de la couleur de
l'intitulé, pas de mention « Soutenu publiquement », numéro de page bien dégagé du cadre
(réglé par `footskip=1.05cm` — il était traversé par le filet).

---

## 8. Manière de travailler attendue

- **Auditer avant de corriger.** Ne pas modifier la production sans validation.
- **Mesurer, ne pas supposer.** Chaque affirmation de performance de ce fichier vient d'un
  chronométrage sur le service réel.
- **Ne rien inventer.** Si une donnée manque, le dire — jamais un nombre plausible.
- **Commentaires en français**, expliquant le *pourquoi* et l'erreur évitée, pas le *quoi*.
- Messages de commit détaillés, sans accents (la console les altère).
- Le directeur écrit vite et en majuscules quand il est pressé : lire l'intention, et
  reformuler sa demande avant de coder si elle est ambiguë.

---

## 9. En cours

- **Stratégie opérationnelle sur 3 ans.** L'objectif global est une trajectoire à 3 ans
  (312,3 → 340 Mds, soit +27,7 Mds) ; l'opérationnel n'a aucun axe temporel. Chaque directive
  porte déjà un `horizon` réel (3 à 24 mois) : le grouper en AN1/AN2/AN3 plutôt que d'inventer
  une répartition. À noter — l'horizon le plus lointain est 24 mois, donc **AN3 serait vide**,
  ce qui est un constat sur le plan et mérite d'être montré.
- **PESTEL.** Les signaux récents de la veille arrivent bien au modèle, mais il ne les reprend
  pas dans sa prose. Défaut de consigne, pas de cache.
- **Bilan des directives.** 5 des 20 sont chiffrables : 15,45 Mds sur 27,7, soit 55,8 %.
  Les 15 autres sont des conditions ou des défenses d'acquis — elles ne s'additionnent pas.
- Le mémoire ne décrit pas encore la refonte des directives ni le déploiement.
