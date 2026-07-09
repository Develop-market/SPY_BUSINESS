# RÉFÉRENCE-OR — Orientation attendue par le DG pour les recommandations

> Cas pratique fictif rédigé par la Direction (Innovation Digitale, SGCI) — sert de
> GOLD STANDARD pour le style, la profondeur et l'orientation des propositions
> stratégiques générées par l'onglet Stratégie (Niveau 3). À injecter / respecter
> dans le prompt des recommandations (server.py, /api/strategie_llm).

## Titre
CAS PRATIQUE — IMPACT STRATÉGIQUE · Analyse concurrentielle et optimisation du PNB
Initiative « Repricing & Valeur Digitale » · Impact mesuré : **+3 % de PNB sur 12 mois**

## 1. Contexte de départ (DIAGNOSTIC grounded)
Analyse semestrielle des EF de 3 concurrents directs → 2 signaux d'alerte :
- Part des commissions dans le PNB des concurrents ≈ **38 %**, contre **24 %** pour SGCI → écart de 14 pts = **sous-monétisation des services**.
- Conditions de banque (réseau commercial) : SGCI pratique des taux débiteurs PME **inférieurs de 80 à 120 bps** au marché sur le crédit moyen terme, **sans gain de parts de marché**.
- **Diagnostic** : SGCI laisse de la marge sur la table — sur le crédit ET les services.

## 2. Les trois actions (chacune : justification grounded → sous-étapes concrètes → résultat chiffré)

### Action 1 — Repricing ciblé du crédit PME (Direction Financière + Commerciale)
- Repricing **progressif** sur segments à **FAIBLE élasticité-prix** (équipement, immobilier pro, trésorerie structurée).
- **+80 bps** sur les nouveaux dossiers.
- **MAINTIEN des conditions préférentielles** sur les clients stratégiques à fort volume.
- **Accompagnement commercial** renforcé (réactivité, conseil personnalisé, accès digital).
- **Résultat 12 mois : +1,4 % de PNB, sans perte significative de parts de marché.**

### Action 2 — Refonte de la grille tarifaire des services transactionnels (Innovation Digitale)
- Constat CB : SGCI ne facture pas des services tarifés ailleurs (alertes SMS, relevés papier, virements interbancaires en agence, certification de documents).
- **Tarification DIFFÉRENCIÉE** : **gratuit sur le canal digital** (appli/espace en ligne), **payant en agence** aligné sur le marché.
- Introduction de **4 nouvelles lignes de commissions** sur services jusqu'ici non facturés.
- **Réduction du coût de délivrance −22 %** ; adoption digitale **+31 %**.
- **Résultat 12 mois : +1,1 % de PNB** (commissions nettes + économies réaffectées en marge).

### Action 3 — Offre packagée Particuliers Premium (Squad : Innovation + Retail + Risque)
- Déclencheur CB/WEB : un concurrent a lancé un « compte tout-en-un » à 15 000 FCFA/mois (carte + assurance + virements illimités + conseiller dédié), adoption visible.
- Offre équivalente adaptée à la base SGCI, **mode Squad**, **3 agences pilotes → généralisation progressive**.
- Panier moyen Premium **+8 700 FCFA/mois** ; rétention **+6 pts**.
- **Résultat 12 mois : +0,5 % de PNB.**

## 3. Synthèse d'impact (toujours une table chiffrée)
| Action | Levier PNB | Contribution |
|---|---|---|
| Repricing crédit PME | Marge d'intérêt | +1,4 % |
| Tarification digitale différenciée | Commissions + coûts | +1,1 % |
| Offre packagée Premium | Commissions | +0,5 % |
| **Total** | — | **+3,0 %** |

## 4. Enseignements clés (la PHILOSOPHIE à appliquer)
1. **L'écart de commissions est le signal le plus actionnable** — pas besoin de refondre le bilan, juste tarifer ce qui a de la valeur.
2. **Le digital n'est pas qu'un canal, c'est un OUTIL DE MARGE** — réduire le coût de délivrance capture de la rentabilité **sans augmenter le prix perçu** par le client.
3. **Le repricing réussi est TOUJOURS ACCOMPAGNÉ** — sans amélioration perçue du service il génère de l'attrition ; couplé à une meilleure expérience, il fidélise.

## RÈGLES dérivées (garde-fous pour le prompt des recommandations)
1. **Ne JAMAIS inventer un chiffre de politique interne** (seuil de scoring « 700 », taux « 8%/12% »). Exprimer en DIRECTION/delta grounded (« +80 bps sur segments à faible élasticité »), jamais en prix absolu décrété.
2. **Comprendre l'INTENTION d'un prix avant de le toucher** : un prix élevé peut être une **barrière de sortie voulue** (attestation de non redevance, levée d'opposition) → NE PAS baisser. Un prix bas peut être une **arme d'acquisition** → NE PAS monter à la médiane (ça tue le « pourquoi SGCI »).
3. **Hausses MODÉRÉES + différenciées** : privilégier gratuit-digital / payant-agence ; jamais doubler un tarif.
4. **Tout repricing est ACCOMPAGNÉ** d'un gain d'expérience/service (anti-attrition).
5. **Profondeur niveau 5** : « fournir des garanties » → préciser lesquelles (hypothèque, nantissement, caution, domiciliation de salaire, assurance-crédit) ; expliquer le MÉCANISME (en quoi ça agit).
6. **Toujours finir par l'IMPACT chiffré** (levier PNB + contribution estimée) + réalisme opérationnel (pilote → généralisation, direction porteuse).
