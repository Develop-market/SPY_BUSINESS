# Formules utilisées — SpyBusiness · Intelligence bancaire ivoirienne
> Toutes les formules sont issues des standards comptables OHADA et des normes BCEAO applicables aux banques de l'UEMOA.

---

## 1. Taux de croissance AN1 → AN3

**Formule :**
```
Taux de croissance (%) = (Valeur AN3 - Valeur AN1) / Valeur AN1 × 100
```

**Exemple BICICI :**
```
(36 520 - 16 700) / 16 700 × 100 = +118.8%
```

**Source :** Calcul standard de variation relative. Référence : BCEAO — Instructions de calcul des ratios prudentiels, Instruction n°026-11-2016.

---

## 2. Marge nette (Taux de conversion PNB → Résultat Net)

**Formule :**
```
Marge nette (%) = Résultat Net / PNB × 100
```

**Exemple SGCI AN3 :**
```
101 352 M / 276 000 M × 100 = 36.7%
```

**Source :** Norme BCEAO — Dispositif prudentiel applicable aux établissements de crédit de l'UEMOA (2018). Indicateur de rentabilité d'exploitation.

---

## 3. Produit Net Bancaire (PNB)

**Formule :**
```
PNB = (Intérêts et produits assimilés - Intérêts et charges assimilées)
    + (Commissions produits - Commissions charges)
    + Gains ou pertes nets sur portefeuilles
    + Autres produits d'exploitation bancaire
    - Autres charges d'exploitation bancaire
```

**Source :** Plan Comptable Bancaire de l'UEMOA (PCB-UEMOA), Article 60. Le PNB est l'équivalent bancaire du chiffre d'affaires net — il représente la marge brute d'activité.

---

## 4. Coefficient d'exploitation

**Formule :**
```
Coefficient d'exploitation (%) = Charges générales d'exploitation / PNB × 100
```

**Exemple SGCI AN3 :**
```
94 056 M / 276 000 M × 100 = 34.1%
```

**Interprétation :**
- < 40% = Excellence opérationnelle
- < 50% = Bon
- < 60% = Acceptable (norme sectorielle UEMOA)
- > 60% = Signal d'alerte

**Source :** BCEAO — Rapport annuel de la Commission Bancaire de l'UEMOA. Ratio utilisé dans les rapports prudentiels officiels.

---

## 5. Coût du risque / PNB

**Formule :**
```
Coût du risque / PNB (%) = |Coût net du risque| / PNB × 100
```

**Exemple SGCI AN3 :**
```
|−46 829 M| / 276 000 M × 100 = 17.0%
```

**Note :** Le coût net du risque est négatif dans les comptes (c'est une charge). On prend la valeur absolue pour exprimer le ratio en positif.

**Source :** PCB-UEMOA, Compte de résultat bancaire — Poste "Coût du risque" ou "Coût net du risque". Correspond aux dotations nettes aux provisions sur créances douteuses.

---

## 6. ROE — Return on Equity (Rentabilité des capitaux propres)

**Formule :**
```
ROE (%) = Résultat Net / Capitaux propres × 100
```

**Exemple BICICI AN3 :**
```
36 520 M / 120 570 M × 100 = 30.3%
```

**Source :** Norme internationale IAS/IFRS, reprise dans les instructions de la BCEAO. Mesure le rendement pour les actionnaires.

---

## 7. Ratio Crédits / Dépôts

**Formule :**
```
Ratio crédits/dépôts (%) = Créances sur la clientèle / Dettes à l'égard de la clientèle × 100
```

**Exemple SGCI AN3 :**
```
2 546 300 M / 2 907 700 M × 100 = 88%
```

**Interprétation :**
- 80–100% = Zone saine (norme prudentielle BCEAO)
- > 100% = Risque de liquidité (prête plus que collecte)
- < 80% = Sous-utilisation des dépôts

**Source :** BCEAO — Règlement n°09/2010/CM/UEMOA relatif aux relations financières extérieures. Indicateur de liquidité et de transformation bancaire.

---

## 8. Mix commercial (décomposition du PNB)

**Formule :**
```
Part intérêts (%) = Intérêts et produits assimilés / Total composantes PNB × 100
Part commissions (%) = Commissions (produits) / Total composantes PNB × 100
Part autres (%) = Autres produits nets / Total composantes PNB × 100
```

**Source :** PCB-UEMOA, Compte de résultat — Postes A1 (intérêts), A3 (commissions), A5 (autres produits).

---

## 9. Part de marché en bénéfices

**Formule :**
```
Part de marché (%) = Résultat Net banque / Σ Résultats Nets secteur × 100
```

**Source :** Calcul interne basé sur les EF publiés des 7 banques.

---

## 10. Efficience cascade P&L (PNB → RN)

**Formule :**
```
Efficience (%) = Résultat Net / PNB × 100
```
*(Identique à la marge nette — mesure combien du PNB initial survit jusqu'au résultat final)*

**Étapes de la cascade :**
1. PNB → RBE : PNB − Charges générales d'exploitation − DAP
2. RBE → RE : RBE − Coût net du risque
3. RE → RN : RE + Gains/pertes sur actifs immobilisés − Impôt sur bénéfices

**Source :** PCB-UEMOA, Structure du compte de résultat bancaire (Articles 60 à 65).

---

## 11. Ratio de Solvabilité (Section ⑤)

**Formule :**
```
Solvabilité (%) = Capitaux propres / Total Actif × 100
```

**Norme BCEAO :** ≥ 8% (Instruction n°008-2014 relative aux fonds propres)

**Exemple SGCI AN3 :**
```
495 100 M / 3 769 174 M × 100 = 13.1%
```

**Interprétation :**
- < 8% = Non conforme norme BCEAO
- 8–10% = Conforme mais sans marge de confort
- > 12% = Position confortable

**Source :** BCEAO — Instruction n°008-2014 portant composition et mode de calcul des fonds propres applicables aux établissements de crédit de l'UEMOA.

---

## 12. Couverture des Dépôts (Section ⑤)

**Formule :**
```
Couverture des dépôts (%) = Capitaux propres / Dettes à l'égard de la clientèle × 100
```

**Exemple SGCI AN3 :**
```
495 100 M / 2 907 700 M × 100 = 17.0%
```

**Source :** Calcul interne basé sur les EF. Indicateur complémentaire de protection des déposants.

---

## 13. Levier Crédit (Section ⑤)

**Formule :**
```
Levier crédit (×) = Créances sur la clientèle / Capitaux propres
```

**Exemple SGCI AN3 :**
```
2 546 300 M / 495 100 M = 5.14×
```

**Interprétation :**
- < 5× = Exposition faible
- 5–7× = Exposition modérée
- > 10× = Exposition élevée (signal d'alerte)

**Source :** Dérivé des ratios prudentiels BCEAO — Dispositif de surveillance bancaire UEMOA.

---

## 14. Portrait Compétitif — 5 dimensions du radar

> Le Portrait Compétitif convertit 5 métriques différentes (résultat, part de bénéfices, avance, croissance, ROE) en **scores sur une échelle 0–100 commune**, ce qui permet de les comparer visuellement sur un radar.
>
> **Règle universelle :** 100 = meilleur du marché · 50 = dans la moyenne · 0 = dernier du marché

---

### Dimension 1 — Résultat net

**Principe :** conversion du rang en score. Le #1 obtient 100, le #7 obtient ~14.

**Formule :**
```
Score = (N - rang + 1) / N × 100
```
où N = nombre de banques comparées (ici N = 7)

**Exemple SGCI AN3 :**
```
SGCI est #1/7 en résultat net absolu
Score = (7 - 1 + 1) / 7 × 100 = 7/7 × 100 = 100/100
```

**Table complète :**
| Rang | Calcul | Score |
|------|--------|-------|
| #1 (meilleur) | (7-1+1)/7 × 100 | **100** |
| #2 | (7-2+1)/7 × 100 | **86** |
| #3 | (7-3+1)/7 × 100 | **71** |
| #4 (médiane) | (7-4+1)/7 × 100 | **57** |
| #5 | (7-5+1)/7 × 100 | **43** |
| #6 | (7-6+1)/7 × 100 | **29** |
| #7 (dernier) | (7-7+1)/7 × 100 | **14** |

> Chaque rang vaut environ 14 points d'écart (= 100/7). Le score 50 sur le graphique représente la "moyenne de marché" dessinée sur le radar — la médiane réelle (#4) donne 57, ce qui est proche.

---

### Dimension 2 — Part des bénéfices sectoriels

**Principe :** si SGCI capte exactement sa part "équitable" (1/7 = 14.3%), il obtient 50 (moyenne). S'il capte le double (28.6%), il obtient 100.

**Formule :**
```
Score = min(100,  part_marché_% × N / 2)
```

**Pourquoi N/2 ?**
```
Part équitable = 100% / 7 = 14.3%
Score d'une part équitable = 14.3% × 7/2 = 14.3 × 3.5 = 50 ✓ (= moyenne)
Score pour 2× la part équitable = 28.6% × 3.5 = 100 (= maximum plafonné)
```

**Exemple SGCI AN3 :**
```
SGCI capte 27.8% des bénéfices des 7 banques
Score = min(100, 27.8 × 7/2) = min(100, 27.8 × 3.5) = min(100, 97.3) = 97/100
```

> Interprétation : SGCI capte presque 2× sa part "juste" — ce qui lui vaut un score proche de 100 sur cette dimension.

---

### Dimension 3 — Avance sur #2 (ou Écart vs leader)

**Principe :** 50 = à égalité parfaite avec le concurrent direct. Plus l'avance est grande, plus le score monte. Si SGCI est derrière, le score descend sous 50.

**Formule :**
```
Score = min(100, max(0,  50 + écart_% / 2))
```
où écart_% = (RN_SGCI - RN_concurrent_direct) / RN_concurrent_direct × 100

**Exemples :**
```
SGCI 60% au-dessus du #2  → 50 + 60/2  = 50 + 30 = 80/100
SGCI à égalité avec #2    → 50 + 0/2   = 50/100
SGCI 20% derrière le #1   → 50 + (-20)/2 = 50 - 10 = 40/100
SGCI 100% derrière        → 50 + (-100)/2 = 0/100 (plancher)
```

**Exemple SGCI AN3 :**
```
SGCI est #1 → concurrent direct = ECOBANK (2ème en RN)
Écart = +60% au-dessus d'ECOBANK
Score = min(100, max(0, 50 + 60/2)) = 80/100
```

---

### Dimension 4 — Dynamique AN1→AN3

**Principe :** même formule que Résultat net, mais appliquée au rang de croissance sur 3 ans.

**Formule :**
```
Score = (N - rang_croissance + 1) / N × 100
```

**Exemple SGCI AN3 :**
```
SGCI croît +4.2% sur 3 ans → #6/7 (6ème croissance du marché, BICICI est #1 à +119%)
Score = (7 - 6 + 1) / 7 × 100 = 2/7 × 100 = 29/100
```

> Un score de 29 signifie que SGCI croît moins vite que 5 banques sur 7. C'est le signal d'alerte structurel du portrait : la taille de SGCI est grande (#1 en absolu) mais sa dynamique est faible (#6 sur 7).

---

### Dimension 5 — ROE (Return on Equity)

**Principe :** même formule, appliquée au rang de ROE (rentabilité des capitaux propres).

**Formule :**
```
Score = (N - rang_ROE + 1) / N × 100
```

**Exemple SGCI AN3 :**
```
SGCI ROE = 20.5% → #6/7 (BICICI #1 à 30.3%, SIB #2 à 26.9%)
Score = (7 - 6 + 1) / 7 × 100 = 2/7 × 100 = 29/100
```

---

### Lecture du radar

```
Score 100 = Meilleur du marché sur cette dimension
Score  86 = 2ème du marché
Score  57 = 4ème du marché (médiane)
Score  29 = 6ème du marché
Score  14 = Dernier du marché (7ème)

Ligne "Moy. marché" tracée à 50 sur toutes les dimensions
→ Tout ce qui dépasse la ligne = au-dessus de la moyenne
→ Tout ce qui est en dessous = sous la moyenne
```

**Portrait SGCI AN3 — résumé :**
| Dimension | Score | Interprétation |
|-----------|-------|----------------|
| Résultat net | 100 | #1 absolu — imbattable |
| Part bénéfices | 97 | Capte 27.8% des profits sectoriels |
| Avance sur #2 | 80 | +60% devant ECOBANK — confort élevé |
| Dynamique AN1→AN3 | 29 | #6/7 — croissance trop lente |
| ROE | 29 | #6/7 — capital mal rémunéré |

> **Score global SGCI : 67/100** — leader en taille, mais fragilités structurelles sur la croissance et la rentabilité du capital.

**Source :** Calcul interne SpyBusiness — formules propriétaires de normalisation par rang et ratio. Données issues des états financiers publiés AN1–AN3 de 7 banques ivoiriennes.

---

## Sources de données

| Source | Description |
|--------|-------------|
| **États Financiers publiés** | Bilans et comptes de résultat annuels de chaque banque (SGCI, BICICI, ECOBANK, NSIA, SIB, BACI, BNI) — exercices 2021 à 2025 |
| **PCB-UEMOA** | Plan Comptable Bancaire de l'Union Économique et Monétaire Ouest Africaine |
| **BCEAO** | Banque Centrale des États de l'Afrique de l'Ouest — Instructions et circulaires prudentielles |
| **Commission Bancaire UEMOA** | Rapports annuels de supervision bancaire |

---

*Document généré automatiquement par SpyBusiness — Intelligence bancaire ivoirienne*
*Dernière mise à jour : Juin 2026*
