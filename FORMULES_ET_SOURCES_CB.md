# Formules utilisées — SpyBusiness · Conditions de Banques (CB)
> Document jumeau de **FORMULES_ET_SOURCES.md** (Santé Financière), appliqué au dashboard **Conditions de Banques**.
> Toutes les formules ci-dessous sont **déterministes et reproductibles** : elles proviennent d'une requête SQL sur la table `cb_tarifs` (PostgreSQL), pas d'une estimation d'IA.
> Les axes de classement suivent la **nomenclature BCEAO** des conditions de banque (Packages, Cartes, Épargne, Crédits, Assurances, Digital/Paiements, Marchés, Autres).

---

## Périmètre & filtre qualité standard

> Avant tout calcul, un **filtre qualité** est appliqué partout pour éliminer le bruit d'extraction OCR. Sans lui, des en-têtes, fragments ou paragraphes fusionnés fausseraient chaque indicateur.

**Filtre standard :**
```
is_header  = FALSE                              -- on exclut les titres de section
section    IS NOT NULL                          -- ligne réellement classée
LENGTH(TRIM(libelle)) BETWEEN 8 AND 110         -- ni fragment, ni paragraphe fusionné
type_valeur ∈ (MONTANT_FCFA, GRATUIT, TAUX_%,   -- uniquement de vrais services tarifés
               SUR_DEMANDE, NUMERIQUE)
```

**Source :** Table `cb_tarifs` — 1 ligne = 1 service tarifé d'une banque pour une période. Données extraites des **plaquettes tarifaires officielles** des 7 banques (SGCI, BACI, BICICI, BNI, ECOBANK, NSIA, SIB).

> **Tout est dynamique :** chaque indicateur est recalculé pour le triplet de filtres **(année, semestre, segment)** sélectionné. Changer un filtre recalcule tout.

---

## 1. Rang catalogue (ex. « #4 / 7 »)

**Principe :** position de SGCI parmi les 7 banques, classées par **nombre de services tarifés distincts** (largeur du catalogue publié).

**Formule :**
```sql
n_services = COUNT(DISTINCT libelle) FILTER (
               WHERE is_header = FALSE
                 AND section IS NOT NULL
                 AND LENGTH(TRIM(libelle)) BETWEEN 8 AND 110)
-- parmi type_valeur ∈ (MONTANT_FCFA, GRATUIT, TAUX_%, SUR_DEMANDE, NUMERIQUE)
-- pour (annee, semestre, segment) donnés
```
On classe les 7 banques par `n_services` décroissant ; le rang de SGCI = sa position.

**Exemple 2026 S1 · Particuliers :**
```
NSIA 445 (#1) · SIB 203 (#2) · BICICI 195 (#3) · SGCI 184 (#4)
ECOBANK 177 (#5) · BACI 165 (#6) · BNI 147 (#7)
→ SGCI = #4 / 7
```

**Interprétation :**
- Répond à *« qui publie le plus de services ? »* (largeur de l'offre).
- Ne répond **pas** à *« qui est le moins cher ? »* (c'est l'indicateur de prix).

**Source :** Fonction `cb_analyse_q6` (`dash_app/db.py`). Le `DISTINCT libelle` évite de compter deux fois le même service. ✅ 100 % déterministe. **Réserve :** dépend de la complétude d'extraction de la plaquette source.

---

## 2. Prix moyen par banque

**Formule :**
```sql
montant_moyen = ROUND(AVG(montant) FILTER (
                  WHERE type_valeur = 'MONTANT_FCFA' AND montant >= 100
                    AND is_header = FALSE AND section IS NOT NULL))
```

**Règles de fiabilité :**
- **Uniquement des montants FCFA** (`type_valeur = 'MONTANT_FCFA'`) → on **n'additionne jamais un taux (%)** avec des francs. Règle absolue : *on ne mélange pas les unités.*
- **Seuil `montant >= 100`** → écarte les valeurs parasites (codes, quantités, « 0 »).

**Source :** Fonction `cb_analyse_q6`. ✅ Déterministe.

---

## 3. Écart de prix par famille de service (comparatif Q6)

**Principe :** pour chaque service SGCI, on cherche le service équivalent chez chaque concurrent (appariement sémantique du libellé), puis on compare au marché.

**Formule :**
```
médiane_marché(service) = médiane des prix FCFA des concurrents
                          (MONTANT_FCFA uniquement, > 0, ≥ 2 concurrents présents)

écart SGCI (%) = (prix_SGCI − médiane_marché) / médiane_marché × 100
```

**Interprétation (badge) :**
```
↓ vert   si SGCI ≤ médiane − 10 %   → moins cher que le marché
=        si entre −10 % et +10 %    → aligné sur le marché
↑ rouge  si SGCI ≥ médiane + 10 %   → plus cher que le marché
```

**Garde-fous essentiels :**
1. **Jamais de mélange %/FCFA** : un service SGCI en taux (ex. « 2,4 % ») n'est jamais comparé à une médiane en francs. Affiché « 2,4 % », pas « 2,4 F ».
2. **Médiane, pas moyenne** : robuste aux valeurs extrêmes.
3. **Minimum 2 concurrents** pour calculer une médiane (sinon « — »).
4. **Écarts > 500 % masqués** : signature d'un artefact (fourchette Min/Max, OCR) → pas de badge trompeur.

**Source :** Fonction `cb_prix_par_libelle` (`statistics.median`, garde `len(conc_montants) >= 2`). ✅ Déterministe. La règle n°1 a corrigé l'ancien « 2,4 F vs 70 754 F ».

---

## 4. Taux de gratuité (ex. « 19,7 % »)

**Formule :**
```sql
pct_gratuit = 100 × COUNT(*) FILTER (WHERE est_gratuit = TRUE …)
                  / COUNT(*) FILTER (WHERE is_header = FALSE AND section IS NOT NULL)
```

**Exemple 2026 S1 · Particuliers :**
```
SGCI = 19,7 %   vs   médiane marché ≈ 31 %
→ SGCI offre MOINS de services gratuits que le marché
```

**Médiane marché** = valeur médiane des 7 taux de gratuité des banques.

**Source :** Fonction `cb_analyse_q6`. ✅ Déterministe (ratio de comptages réels).

---

## 5. Classement par axe BCEAO

**Principe :** chaque service est rattaché à **un des 8 axes BCEAO** selon son libellé et sa section, par règles de mots-clés.

**Formule (logique de classement) :**
```
classify_axe(libelle, section) →
   SI mots-clés {pack, bouquet, formule}        → Packages
   SINON SI {carte, visa, mastercard, gab}      → Cartes
   SINON SI {épargne, livret, dépôt à terme}    → Épargne
   SINON SI {crédit, prêt, découvert, escompte} → Crédits
   SINON SI {assurance, prévoyance, décès}      → Assurances
   SINON SI {en ligne, mobile, connect, sms}    → Digital / Paiements
   SINON SI {bourse, opcvm, titres, change}     → Marchés
   SINON                                         → Autres
```

**Interprétation :** un poids « Autres » trop élevé = mauvaise classification. La nomenclature a fait passer **Autres de 59 % → 24 %**, signe d'un rattachement correct.

**Source :** `cb_axes.py` (`classify_axe`, `AXES`/`AXE_COLORS`/`AXE_ICONS`). ✅ Déterministe (règles explicites, pas d'IA).

---

## 6. Exclusivités SGCI (et gaps concurrents)

**Principe :** un service SGCI est « exclusif » s'il **n'a aucun équivalent** chez les 6 concurrents (et inversement un « gap » est un service présent chez les concurrents mais absent chez SGCI).

**Chaîne de calcul :**
```
1. Pré-filtre déterministe : on garde les services SGCI sans correspondant
   évident chez un concurrent (similarité textuelle < 0,70).
2. Confirmation IA par axe BCEAO : élimine les variantes de nommage.
3. Enrichissement : prix / contexte / devise réels rattachés depuis la base.
4. GARDE-FOU FINAL DÉTERMINISTE (_garde_vrai_exclusif) :
      on garde un service comme exclusif UNIQUEMENT si
      AUCUN libellé d'en face n'a une similarité ≥ 0,72.
```

**Formule du garde-fou final :**
```
pour chaque service candidat (libellé normalisé n) :
   SI  max( SequenceMatcher(n, libellé_opposé) ) ≥ 0,72   → REJET (faux exclusif)
   SINON                                                   → GARDÉ (vrai exclusif)
```

**Exemple vérifié (faux positif corrigé) :**
```
« Attestation bancaire pour VISA » (BACI) ~ 0,80 avec « Attestation bancaire » (SGCI)
→ 0,80 ≥ 0,72 → REJETÉ : ce n'est PAS un vrai exclusif BACI
« PACK COOPERATIVES » : aucun équivalent ≥ 0,72 → GARDÉ : vrai exclusif
```

**Interprétation :** *exclusif = exclusif*. Le garde-fou s'applique à **toutes les banques** (SGCI, BACI, BNI, BICICI, NSIA, ECOBANK), sur les exclusivités **et** les gaps.

**Source :** `server.py` — `_norm_lib_excl`, `_garde_vrai_exclusif` (seuil 0,72), appliqués dans `api_cb_exclusivites_axes` et `api_cb_gaps_axes`. ✅ Déterministe après la couche IA.

---

## 7. Top 10 — score de distinction (pas un simple tri par prix)

**Principe :** le Top 10 ne classe **plus** du prix le plus élevé au plus bas (qui faisait remonter du bruit type « Titulaire » et ratait des services stratégiques comme **SGCONNECT**). Il utilise un **score de distinction** + une **exclusion du bruit OCR**.

**a) Exclusion du bruit (`_isJunkExcl`) :**
```
REJET si  longueur < 14 caractères
      OU  commence par « titulaire / pour tout montant / par série /
                          montant compris / coût / autres types / frais / pour les … »
      OU  commence par une minuscule (fragment de phrase)
```

**b) Score de distinction — Exclusivités (Q3) :**
```
px = log10(montant + 1)         (le prix départage à l'intérieur d'une catégorie)

score =  400 + px   si DIGITAL nommé  (connect, mobile, en ligne, application,
                                       sans carte, digital, e-CNPS, MyBusiness, web)
         300 + px   si PRODUIT nommé  (pack, soge, yaconfort, quietis, zenith,
                                       diaspora, horizon, elite, bourse, opcvm, titres,
                                       assurance, sogeprimo …)
         100 + px   si TAUX (type_valeur contient TAUX)
         200 + px   sinon
```

**c) Score de priorité — Gaps SGCI (Q5) :**
```
score =  500   si service concurrent GRATUIT  (priorité absolue = urgence)
         400   si DIGITAL nommé
         300   si PRODUIT nommé
         100   si TAUX
         200   sinon
(bruit OCR exclu au préalable)
```

**Interprétation :** les services **digitaux distinctifs (SGCONNECT) remontent**, les **gratuités concurrentes urgentes** sont priorisées dans les gaps, et le **bruit disparaît**.

**Source :** `app.main.js` — `_distScore` / `_isJunkExcl` (Q3), `_prioScore` / `_isJunkGap` (Q5). ✅ Déterministe et reproductible (mêmes données → même classement).

---

## 8. VRIST — index qualitatif de positionnement (5 axes)

> **Nature.** VRIST est un **index qualitatif** d'avantage concurrentiel (cadre académique **V**aluable / **R**are / **I**nimitable / **S**ustainable / **T**ransformative). Ce **n'est pas une mesure financière** : c'est une **note /10 par axe**, calculée par des **règles linéaires transparentes** sur les données réelles. À lire comme un **radar de positionnement**, pas comme un montant comptable.

**Variables d'entrée (toutes issues de la base, pour le filtre courant) :**
```
n      = nombre d'exclusivités SGCI
nAxes  = nombre de domaines/axes BCEAO couverts par les exclusivités
nSec   = nombre de sections BCEAO couvertes (sur 9)
nGrat  = nombre d'exclusivités gratuites
régulé = présence d'un axe régulé (Assurances / Marchés)
```

**Formules (chaque score est borné dans [1..10]) :**

| Axe | Question | Formule |
|-----|----------|---------|
| **V — Valeur** | Crée de la valeur ? | `V = clamp( 2 + 8 × min(n, 50) / 50 )` |
| **R — Rareté** | Introuvable ailleurs ? | `R = clamp( 5 + 5 × min(n, 40) / 40 )` |
| **I — Inimitable** | Difficile à copier ? | `I = clamp( (7 si régulé, sinon 4) + 3 × min(nAxes, 8) / 8 )` |
| **S — Durable** | Tient dans le temps ? | `S = clamp( 10 × nSec / 9 )` |
| **T — Transformatif** | Transforme l'expérience ? | `T = clamp( 3 + 7 × nGrat / max(n, 1) )` |

avec `clamp(x) = max(1, min(10, round(x)))`.

**Score global :**
```
VRIST global = (V + R + I + S + T) / 5
```

**Exemple de lecture :**
```
n = 50 exclusivités, nAxes = 8, nSec = 9, nGrat = 10, axe régulé présent
V = 2 + 8×50/50 = 10
R = 5 + 5×40/40 = 10
I = 7 + 3×8/8   = 10
S = 10×9/9      = 10
T = 3 + 7×10/50 = 4.4 → 4
Global = (10+10+10+10+4)/5 = 8.8 / 10
```

**Interprétation :**
- **V** monte avec le **volume** d'exclusivités (plafonné à 50).
- **R** part d'un socle 5 (être absent des 6 concurrents est déjà rare) et monte avec n.
- **I** récompense la **diversité d'axes** + la présence d'un domaine **régulé** (barrière réglementaire).
- **S** mesure la **couverture des 9 sections** BCEAO (présence structurelle = durable).
- **T** mesure l'**intensité de gratuité/digital** parmi les exclusivités.

**Source :** `app.main.js` — fonction `_renderQ4` (`_clampV`, formules V/R/I/S/T). ✅ Reproductible (plus aucune constante « magique » type √n). **Réserve :** index **qualitatif**, pas comptable. *(Le commentaire stratégique sous le radar est, lui, généré par l'IA et reste indicatif.)*

---

## 9. Évolution temporelle (apparus / disparus)

**Principe :** entre deux périodes, on détecte les services **apparus** (nouveautés) et **disparus** (retraits) d'une banque.

**Formule (logique d'appariement) :**
```
service "disparu"  = présent en N-1, ABSENT en N
service "apparu"   = présent en N,   ABSENT en N-1
   ABSENT ⟺ aucun libellé d'en face avec similarity(...) > 0,7   (pg_trgm)
   + filtre Python de recouvrement de mots-clés (_overlap)
```

**Interprétation :** un seuil trop bas (0,45) masquait de vrais retraits (ex. cartes ECLAIR). Relevé à **0,7**, l'appariement restitue les vrais mouvements (ex. 7 apparus / 2 retirés).

**Source :** Fonction `cb_evolution_details` (`dash_app/db.py`), `pg_trgm` + filtre `_overlap`. ✅ Déterministe.

---

## 10. Rattrapage vs Dépassement (innovation concurrentielle)

**Principe :** parmi les nouveautés des concurrents, on distingue :
- **Rattrapage** : le concurrent ajoute un service que **SGCI possède déjà** (il comble son retard).
- **Dépassement** : le concurrent ajoute un service que **SGCI n'a pas** (il prend de l'avance).

**Formule :**
```
pour chaque service "apparu" chez un concurrent :
   SI  difflib.ratio(service, catalogue_SGCI) ≥ seuil  → RATTRAPAGE
   SINON                                                → DÉPASSEMENT

taux_rattrapage (%) = rattrapage / total_apparus × 100
taux_dépassement (%) = dépassement / total_apparus × 100
```

**Interprétation :** un taux de **dépassement** élevé = les concurrents innovent sur des terrains où SGCI est absente → signal stratégique prioritaire.

**Source :** Fonction `cb_rattrapage_depassement(segment)` (`db.py`) via `cb_all_evolutions_summary` + `difflib` vs catalogue SGCI. ✅ Déterministe.

---

## Synthèse de fiabilité

| Indicateur | Calcul | Fiabilité | Réserve |
|------------|--------|-----------|---------|
| Rang catalogue | SQL `COUNT(DISTINCT libelle)` filtré | ✅ déterministe | dépend de la complétude d'extraction |
| Prix moyen / médian | SQL `AVG/MEDIAN` FCFA only, ≥ 100 | ✅ déterministe | garde-fous %/FCFA & > 500 % |
| Écart par famille | médiane marché ≥ 2 concurrents | ✅ déterministe | « — » si < 2 concurrents |
| Taux de gratuité | SQL ratio de comptages | ✅ déterministe | — |
| Classement par axe | règles mots-clés `classify_axe` | ✅ déterministe | dépend du libellé extrait |
| Exclusivités / gaps | similarité + IA + garde-fou 0,72 | ✅ + curé | libellés voisins gérés par le garde-fou |
| Top 10 | score de distinction + exclusion bruit | ✅ reproductible | priorise digital/produits nommés |
| VRIST | 5 règles linéaires bornées [1..10] | ✅ reproductible | **index qualitatif**, pas comptable |
| Évolution apparus/disparus | `pg_trgm` > 0,7 + `_overlap` | ✅ déterministe | seuil calibré à 0,7 |
| Rattrapage / dépassement | `difflib` vs catalogue SGCI | ✅ déterministe | dépend du seuil d'appariement |

> **En un mot pour les financiers :** les indicateurs **chiffrés** (rang, prix, gratuité, écarts) sont **100 % déterministes et reproductibles depuis la base** ; les indicateurs **qualitatifs** (exclusivités, VRIST, rattrapage) reposent sur des **règles transparentes** + une couche d'IA pour le nommage/commentaire — à lire comme des **aides à la décision**, non comme des montants comptables.

---

## Sources de données

| Source | Description |
|--------|-------------|
| **Plaquettes tarifaires** | Conditions de banque publiées par chaque banque (SGCI, BACI, BICICI, BNI, ECOBANK, NSIA, SIB) — par année / semestre / segment |
| **Table `cb_tarifs`** | Base PostgreSQL — 1 ligne = 1 service tarifé (banque, période, section, libellé, valeur, montant, gratuité, devise, type) |
| **Nomenclature BCEAO** | Axes de classement des conditions de banque (Packages, Cartes, Épargne, Crédits, Assurances, Digital/Paiements, Marchés, Autres) |
| **Cadre VRIST** | Modèle académique d'avantage concurrentiel (Valuable / Rare / Inimitable / Sustainable / Transformative) |

---

*Document généré par SpyBusiness — Intelligence bancaire ivoirienne*
*Jumeau de FORMULES_ET_SOURCES.md (Santé Financière), appliqué aux Conditions de Banques*
*Dernière mise à jour : Juin 2026*
