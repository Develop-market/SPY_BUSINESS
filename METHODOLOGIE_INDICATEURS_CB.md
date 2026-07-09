---
title: "Méthodologie des indicateurs — Dashboard Conditions de Banques (CB)"
subtitle: "Comment chaque indicateur est calculé · Garanties de fiabilité"
author: "SpyBusiness — Intelligence bancaire SGCI"
date: "2026"
output:
  pdf_document:
    toc: true
    number_sections: true
---

> **Objet du document.** Répondre précisément à la question des équipes financières :
> *« comment chaque indicateur du dashboard CB est-il calculé, et est-il fiable ? »*
> Chaque calcul ci-dessous est **déterministe et reproductible** : il provient d'une requête
> SQL sur la base `cb_tarifs` (PostgreSQL), pas d'une estimation d'IA.

---

# Principe général

- **Source unique** : table `cb_tarifs` (PostgreSQL) — 1 ligne = 1 service tarifé d'une banque, pour une période.
- **Filtre qualité standard** appliqué partout (élimine le bruit d'extraction OCR) :
  - `is_header = FALSE` (on exclut les en-têtes de section) ;
  - `section IS NOT NULL` (ligne réellement classée) ;
  - `LENGTH(TRIM(libelle)) BETWEEN 8 AND 110` (ni fragment, ni paragraphe fusionné) ;
  - `type_valeur ∈ {MONTANT_FCFA, GRATUIT, TAUX_%, SUR_DEMANDE, NUMERIQUE}` (vrais services).
- **Tout est dynamique** : chaque indicateur est recalculé pour le triplet de filtres
  **(année, semestre, segment)** sélectionné. Changer un filtre recalcule tout.

---

# Rang catalogue (ex. « #4 / 7 »)

**Définition.** Position de SGCI parmi les 7 banques, classées par **nombre de services tarifés
distincts** (largeur de catalogue).

**Calcul exact** (fonction `cb_analyse_q6`) :

```sql
n_services = COUNT(DISTINCT libelle)
             FILTER (WHERE is_header = FALSE
                       AND section IS NOT NULL
                       AND LENGTH(TRIM(libelle)) BETWEEN 8 AND 110)
-- parmi les lignes où type_valeur ∈ (MONTANT_FCFA, GRATUIT, TAUX_%, SUR_DEMANDE, NUMERIQUE)
-- pour (annee, semestre, segment) donnés
```

On classe les 7 banques par `n_services` décroissant ; le rang de SGCI = sa position.

**Valeurs 2026 S1 · Particuliers :** NSIA 445 (#1) · SIB 203 (#2) · BICICI 195 (#3) ·
**SGCI 184 (#4)** · ECOBANK 177 (#5) · BACI 165 (#6) · BNI 147 (#7).

**Fiabilité.** ✅ Calcul **100 % déterministe et reproductible**. Le `DISTINCT libelle` évite
de compter deux fois le même service.

**Limite à connaître (honnêteté).** Cet indicateur mesure la **largeur du catalogue publié et
correctement extrait** : il dépend donc aussi de la **qualité d'extraction** du PDF source.
Il répond à *« qui publie le plus de services ? »*, **pas** à *« qui est le moins cher ? »*
(c'est l'indicateur de prix qui répond à ça).

---

# Indicateur de prix

C'est l'indicateur le plus sensible : voici **exactement** comment il est construit.

## a) Prix moyen par banque (`montant_moyen`)

```sql
montant_moyen = ROUND(AVG(montant)
   FILTER (WHERE type_valeur = 'MONTANT_FCFA' AND montant >= 100
             AND is_header = FALSE AND section IS NOT NULL))
```

- **Uniquement des montants FCFA** (`type_valeur = 'MONTANT_FCFA'`) → on **n'additionne jamais
  un taux (%)** avec des francs. Règle absolue : *on ne mélange pas les unités*.
- **Seuil `montant >= 100`** → écarte les valeurs parasites (codes, quantités, « 0 »).

## b) Comparatif « par famille de service » (le tableau Q6)

Pour chaque service SGCI, on cherche le **service équivalent** chez chaque concurrent
(appariement sémantique), puis :

```
médiane_marché(service) = médiane des prix FCFA des concurrents
                          (uniquement MONTANT_FCFA, > 0, ≥ 2 concurrents présents)
écart SGCI = (prix_SGCI − médiane_marché) / médiane_marché × 100
   ↓ vert  si SGCI ≤ médiane − 10 %   (moins cher)
   ↑ rouge si SGCI ≥ médiane + 10 %   (plus cher)
```

**Garde-fous de fiabilité (essentiels) :**

1. **Jamais de mélange %/FCFA** : un service SGCI en **taux** (ex. « 2,4 % ») n'est **jamais**
   comparé à une médiane en francs. Affiché « 2,4 % », pas « 2,4 F ».
2. **Médiane, pas moyenne** : robuste aux valeurs extrêmes.
3. **Minimum 2 concurrents** pour calculer une médiane (sinon « — »).
4. **Écarts > 500 % masqués** : signature d'un artefact (fourchette Min/Max, OCR) → pas de badge trompeur.

**Fiabilité.** ✅ Déterministe. Les garde-fous ci-dessus éliminent les comparaisons absurdes
(ex. l'ancien « 2,4 F vs 70 754 F » a été corrigé par la règle n°1).

---

# Taux de gratuité (ex. « 19,7 % »)

```sql
pct_gratuit = 100 × (nb lignes gratuites) / (nb lignes totales)
-- est_gratuit = TRUE / total, sur lignes is_header=FALSE AND section IS NOT NULL
```

**Médiane marché** = valeur médiane des 7 taux de gratuité. SGCI 2026 S1 Part : **19,7 %**
contre une médiane marché ≈ 31 % → SGCI offre **moins de services gratuits** que le marché.

**Fiabilité.** ✅ Déterministe (ratio de comptages réels).

---

# Exclusivités SGCI & « Top 10 »

## Comment une exclusivité est déterminée

Un service SGCI est « exclusif » s'il **n'a aucun équivalent** chez les 6 concurrents :

1. **Pré-filtre déterministe** (`prefilter_candidates`, similarité textuelle < 0,70) :
   on garde les services SGCI sans correspondant évident chez un concurrent.
2. **Confirmation par l'IA** (par axe BCEAO) : élimine les variantes de nommage.
3. **Enrichissement** : on rattache le prix / contexte / devise réels depuis la base.

## Classement du Top 10 (corrigé)

Le Top 10 n'est **plus un simple tri par prix décroissant** (qui faisait remonter du bruit
type « Titulaire » et ratait des services stratégiques comme **CONNECT**). Nouveau **score de
distinction** :

| Priorité | Critère | Exemples |
|---|---|---|
| 1 | **Digital nommé** | CONNECT, mobile, retrait sans carte, MyBusiness, e-CNPS |
| 2 | **Produit nommé** | PACK DIASPORA, YACONFORT, SOGE-INVEST, Bourse/OPCVM, Assurances |
| 3 | Autre service tarifé réel | (le prix départage à l'intérieur de chaque catégorie) |
| — | **Exclu** | fragments / bruit OCR : « Titulaire », « Pour tout montant… », « Par série… », libellés < 14 caractères, commençant en minuscule |

→ Les **services digitaux distinctifs (CONNECT) remontent**, le **bruit disparaît**.

## ⚠️ Limite des exclusivités — faux positifs possibles

L'exclusivité repose sur une **comparaison sémantique** : un faux positif peut survenir quand
SGCI possède le service sous un **libellé légèrement différent** (ou dans un autre segment).
**Exemple vérifié** : « Attestation bancaire pour VISA » (BACI) ressemble à 0,80 à
« Attestation bancaire » (SGCI) → **ce n'est donc pas un vrai exclusif BACI**. Recommandation :
traiter les exclusivités comme **« à valider »** sur les libellés ambigus, et resserrer le seuil
d'appariement si nécessaire.

---

# VRIST — index qualitatif (5 axes)

**Nature.** VRIST est un **index qualitatif** d'avantage concurrentiel (cadre académique
Valuable / Rare / Inimitable / Sustainable / Transformative). Ce **n'est pas une mesure
financière** : c'est une **note /10 calculée par des règles transparentes** sur les données
réelles (nb d'exclusivités `n`, nb de domaines `nAxes`, sections couvertes `nSec`, gratuités
`nGrat`, présence d'axes régulés). Chaque règle est reproductible :

| Axe | Question | Règle de calcul (∈ [1..10]) |
|---|---|---|
| **V — Valeur** | Crée de la valeur ? | `2 + 8 × min(n, 50) / 50` (volume d'exclusivités) |
| **R — Rareté** | Introuvable ailleurs ? | `5 + 5 × min(n, 40) / 40` (socle 5, absent des 6 concurrents) |
| **I — Inimitable** | Difficile à copier ? | `(7 si axe régulé Assurances/Marchés, sinon 4) + 3 × min(nAxes,8)/8` |
| **S — Durable** | Tient sur 5 ans ? | `10 × nSec / 9` (sections BCEAO couvertes) |
| **T — Transformatif** | Transforme l'expérience ? | `3 + 7 × nGrat / n` (intensité gratuité/digital) |

**Score global** = moyenne des 5 axes.

**Fiabilité.** ✅ Les **5 formules sont explicites et reproductibles** (plus aucune constante
« magique »). ⚠️ Mais c'est un **index qualitatif**, pas un montant : il s'interprète comme un
**radar de positionnement**, à présenter comme tel (pas comme une valeur comptable).
*(Le commentaire stratégique sous le radar est, lui, généré par l'IA et reste indicatif.)*

---

# Garantie : tout est dynamique

Chaque indicateur, tableau et analyse est **paramétré par (année, semestre, segment)** et
recalculé à chaque changement de filtre. Les analyses IA sont **mises en cache par clé exacte**
incluant ces filtres (`…_2026_S1_Particuliers_…`) → une combinaison = son propre résultat.
Exemple vérifié : SGCI passe de **184 services (2026 S1 Part.)** à **178 (Entreprises)** —
les chiffres suivent le filtre.

---

# Synthèse de fiabilité

| Indicateur | Calcul | Fiabilité | Réserve |
|---|---|---|---|
| Rang catalogue | SQL `COUNT(DISTINCT libelle)` filtré | ✅ déterministe | dépend de la complétude d'extraction |
| Prix moyen / médian | SQL `AVG/MEDIAN` FCFA only, ≥100 | ✅ déterministe | garde-fous %/FCFA & >500 % |
| Taux de gratuité | SQL ratio | ✅ déterministe | — |
| Exclusivités / Top 10 | similarité + IA + score de distinction | ✅ + curé | faux positifs sur libellés voisins |
| VRIST | 5 règles linéaires documentées | ✅ reproductible | **index qualitatif**, pas comptable |

**En un mot pour les financiers :** les indicateurs **chiffrés** (rang, prix, gratuité) sont
**100 % déterministes et reproductibles depuis la base** ; les indicateurs **qualitatifs**
(exclusivités, VRIST) reposent sur des **règles transparentes** + une couche d'IA pour le
nommage/commentaire, à lire comme des **aides à la décision**, non comme des montants comptables.
