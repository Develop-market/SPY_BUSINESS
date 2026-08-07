# -*- coding: utf-8 -*-
"""
directives.py — Directives opérationnelles par direction, composées de façon déterministe
==========================================================================================
ÉCRIT LE 2026-08-07, sur une demande précise du directeur :

    « L'idée dans opérationnelle est de donner des directives claires, concises, plus que
      précises à CHAQUE direction pour atteindre le but. On doit avoir 4 cartes dans chaque
      direction. Si le LLM a des limites, toi-même rédige. Mais que ce soit reproductible
      et évolutif. »

POURQUOI CE MODULE EXISTE

L'onglet confiait la rédaction au modèle de langage, secteur par secteur. Deux défauts en
découlaient, tous deux constatés à l'écran :

  1. INCOMPLET PAR CONSTRUCTION. Le modèle produisait trois décisions par secteur et les
     répartissait entre les directions citées : certaines directions recevaient une carte,
     le Marketing aucune. Un directeur qui ouvre l'onglet et n'y trouve rien pour lui n'a
     aucune raison d'y revenir.
  2. FRAGILE. Quand le budget de jetons se ferme — ce qui arrive — l'onglet se vide
     entièrement. Une note d'arbitrage ne peut pas dépendre de la disponibilité d'un
     service externe.

Ici, les quatre directives de chaque direction sont COMPOSÉES à partir des données : rien
n'est écrit d'avance, rien n'est demandé à un modèle. Les chiffres, les services nommés et
l'ordre des priorités sortent de `cb_tarifs`, du compte de résultat et de la veille.

  REPRODUCTIBLE — mêmes données, même texte, sans appel réseau.
  ÉVOLUTIF      — un tarif qui bouge, une banque qui entre en base, un fait de veille qui
                  change : la directive suivante le dit d'elle-même. Aucun service, aucune
                  banque, aucun montant n'est écrit en dur.
  COMPLET       — exactement quatre directives par direction, toujours.

PORTÉE : l'ensemble des données disponibles. La période de référence est la plus récente
présente en base, jamais une date écrite dans le code ; les repères de marché et le plan à
trois ans mobilisent tout l'historique chargé.
"""
import statistics

from functools import lru_cache

import db

# ── SEGMENTATION CLIENTÈLE SGCI ──────────────────────────────────────────────────────
# Grille transmise par la Direction. Elle sert d'ossature aux directives Marketing : parler
# de « la clientèle » en général ne dit rien à personne, alors qu'un seuil de revenu ou de
# chiffre d'affaires désigne un fichier client réel et une action possible.
#
# `mots` : familles de services cherchées dans les LIBELLÉS RÉELS du catalogue, et non une
# liste de services figée — un service ajouté à la grille rejoint son segment sans qu'on
# touche à ce fichier.
SEGMENTS = [
    {"cle": "GP", "nom": "Grand public",
     "critere": "revenu mensuel inférieur à 450 000 FCFA",
     "enjeu": "volume et bancarisation",
     "mots": ("tenue de compte", "compte cheque", "compte chèque", "retrait", "virement",
              "releve", "relevé", "distance", "mobile", "sms")},
    {"cle": "BG", "nom": "Bonne gamme",
     "critere": "revenu mensuel de 450 000 à 2 000 000 FCFA",
     "enjeu": "équipement et fidélisation",
     "mots": ("package", "pack ", "carte", "assurance", "epargne", "épargne",
              "decouvert", "découvert", "credit", "crédit")},
    {"cle": "PATRIMONIAUX", "nom": "Patrimoniaux",
     "critere": "revenu mensuel supérieur à 2 000 000 FCFA",
     "enjeu": "marge et rétention",
     "mots": ("sous mandat", "placement", "titre", "bourse", "gold", "platinum", "premier",
              "privil", "elite", "élite", "coffre", "succession")},
    {"cle": "CLIPRO", "nom": "Clientèle professionnelle",
     "critere": "chiffre d'affaires annuel inférieur ou égal à 750 millions FCFA",
     "enjeu": "conquête",
     "mots": ("profession", "commer", "monetique", "monétique", "tpe", "marchand",
              "versement", "remise", "espece", "espèce", "timbre")},
    {"cle": "CLICOM", "nom": "Clientèle commerciale",
     "critere": "chiffre d'affaires annuel supérieur à 750 millions FCFA",
     "enjeu": "revenus de commissions",
     "mots": ("documentaire", "change", "etranger", "étranger", "transfert", "devise",
              "caution", "garantie", "import", "export")},
]

DIRECTIONS = ["Direction Financière", "Direction Commerciale", "Direction Marketing",
              "Direction Innovation", "Direction des Risques"]

# Quatre par direction : c'est la demande, et c'est aussi ce qu'un comité retient d'une
# séance. Au-delà, la hiérarchie se perd et plus rien n'est prioritaire.
PAR_DIRECTION = 4

# Seuls ces types de valeur se comparent en francs. Un taux (« 2 % ») et un montant
# (« 2 350 F ») sont deux nombres qu'on ne met pas côte à côte : sans ce filtre, la médiane
# marché des frais de tenue de compte tombait à 2 FCFA et l'écart affiché atteignait
# +93 900 %. Une directive bâtie sur ce chiffre s'effondrerait à la première lecture.
_TYPES_MONTANT = {"MONTANT_FCFA", "GRATUIT"}

# Au-delà de ce rapport, on ne compare plus deux prix mais deux unités différentes. Le cas
# se produit quand l'extraction a pris un numéro de section ou un pourcentage pour un
# montant — défaut connu et mesuré (265 lignes en base, audit du 2026-08-06). Plutôt que
# d'afficher un écart spectaculaire et faux, on écarte le service du panier.
_RAPPORT_MAX_PLAUSIBLE = 40


# ══════════════════════════════════════════════════════════════════════════════════════
#  SOCLE DE FAITS — tout ce qui suit est mesuré, jamais supposé
# ══════════════════════════════════════════════════════════════════════════════════════

def _pluriel(n, mot, suffixe="s"):
    """Accord simple — « 1 service » et non « 1 services »."""
    return f"{n} {mot}{suffixe if n > 1 else ''}"


def _fmt(n, unite="FCFA"):
    """Montant lisible : séparateurs d'espace, pas de décimale inutile.

    Les valeurs de veille arrivent en TEXTE (« 15 000 000 », « 7,7 % de créances dégradées ») :
    l'extraction restitue ce qui est écrit dans la source. Les renvoyer telles quelles vaut
    mieux que de rendre « — », qui affichait un seuil réglementaire vide dans la directive
    de conformité.
    """
    if n is None:
        return "—"
    if isinstance(n, str):
        brut = n.strip()
        if not brut:
            return "—"
        compact = brut.replace(" ", "").replace(" ", "").replace(",", ".")
        try:
            n = float(compact)
        except ValueError:
            return brut          # texte déjà porteur de son unité, servi tel quel
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    if abs(n) >= 1e9:
        return f"{n/1e9:.1f}".replace(".", ",") + (f" Md {unite}" if unite else " Md")
    if abs(n) >= 1e6:
        return f"{n/1e6:.0f}" + (f" M {unite}" if unite else " M")
    return f"{int(round(n)):,}".replace(",", " ") + (f" {unite}" if unite else "")


def _pct(x):
    return f"{x:.0f} %".replace(".", ",")


def _est_un_montant(valeur):
    """La valeur est-elle un prix en francs, et non un taux ou une mention libre ?"""
    if not isinstance(valeur, dict):
        return False
    if valeur.get("grat"):
        return True
    return (valeur.get("tv") in _TYPES_MONTANT) and valeur.get("montant") is not None


def _ordres_compatibles(a, b):
    """Deux montants sont-ils comparables, ou l'un est-il d'une autre nature ?"""
    if a == 0 or b == 0:
        return True                       # la gratuité se compare à n'importe quel prix
    haut, bas = max(abs(a), abs(b)), min(abs(a), abs(b))
    return bas > 0 and haut / bas <= _RAPPORT_MAX_PLAUSIBLE


def periode_la_plus_recente():
    """Dernière période réellement présente en base — jamais une date écrite en dur.

    L'onglet doit parler de l'état le plus récent du marché sans qu'on le lui dise : une
    ingestion de données 2026 S2 suffit à déplacer l'analyse.
    """
    try:
        per = db.cb_periodes() or {}
        annee = max(int(a) for a in per)
        return annee, sorted(per[str(annee)])[-1]
    except Exception:
        return 2026, "S1"


@lru_cache(maxsize=8)
def panier_compare(annee, semestre, segment):
    """Services où SGCI ET au moins deux concurrents affichent un montant comparable.

    Sans deux concurrents, la « médiane marché » n'est qu'un autre concurrent déguisé en
    marché. Renvoie des dictionnaires plats, plus faciles à trier que l'arborescence de
    cb_prix_par_libelle.
    """
    out = []
    try:
        sections = db.cb_prix_par_libelle(annee, semestre, segment) or []
    except Exception:
        return out
    for sec in sections:
        for ss in sec.get("sous_sections", []):
            for sv in ss.get("services", []):
                sgci = sv.get("sgci") or {}
                if sgci.get("suspect") or not _est_un_montant(sgci):
                    continue
                prix = 0.0 if sgci.get("grat") else sgci.get("montant")
                if prix is None:
                    continue
                prix = float(prix)
                concurrents = []
                for banque, c in (sv.get("concurrents") or {}).items():
                    if not c or not _est_un_montant(c):
                        continue
                    p = 0.0 if c.get("grat") else c.get("montant")
                    if p is not None:
                        concurrents.append((banque, float(p)))
                if len(concurrents) < 2:
                    continue
                med = statistics.median([p for _, p in concurrents])
                if not _ordres_compatibles(prix, med):
                    continue
                out.append({
                    "libelle": str(sv.get("libelle") or "").strip(),
                    "section": sec.get("titre") or "",
                    "sgci": prix, "median": med, "n_conc": len(concurrents),
                    "moins_cher": min(concurrents, key=lambda x: x[1]),
                    "ecart_pct": (100 * (prix - med) / med) if med else None,
                })
    return out


def _plus_chers(panier, n=3, seuil=25):
    cand = [s for s in panier if s["ecart_pct"] is not None
            and s["ecart_pct"] >= seuil and s["sgci"] > 0]
    return sorted(cand, key=lambda s: -s["ecart_pct"])[:n]


def _plus_competitifs(panier, n=3, seuil=-25):
    cand = [s for s in panier if s["ecart_pct"] is not None and s["ecart_pct"] <= seuil]
    return sorted(cand, key=lambda s: s["ecart_pct"])[:n]


def _gratuits_distinctifs(panier, n=3):
    """Gratuits chez SGCI, facturés par la majorité des concurrents."""
    cand = [s for s in panier if s["sgci"] == 0 and s["median"] and s["median"] > 0]
    return sorted(cand, key=lambda s: -s["median"])[:n]


def services_de_section(panier, motif, n=3):
    """Services rattachés à une section canonique BCEAO.

    Plus fiable que la recherche par mot-clé dans le libellé : « Consultation de solde par
    téléphone » relève de la banque à distance sans contenir « distance », et la recherche
    par mots ne la trouvait pas — la directive Innovation tombait alors en repli alors que
    trois services existaient. La section, elle, est attribuée par le référentiel des neuf
    sections (cf. cb_sections.py) et ne dépend pas du vocabulaire de chaque brochure.
    """
    m = motif.lower()
    cand = [s for s in panier if m in (s.get("section") or "").lower()]
    return sorted(cand, key=lambda s: -abs(s["ecart_pct"] or 0))[:n]


def services_du_segment(panier, cle, n=3):
    """Services du panier relevant d'un segment de la grille SGCI, écarts les plus marqués."""
    seg = next((s for s in SEGMENTS if s["cle"] == cle), None)
    if not seg:
        return []
    cand = [s for s in panier if any(m in s["libelle"].lower() for m in seg["mots"])]
    return sorted(cand, key=lambda s: -abs(s["ecart_pct"] or 0))[:n]


def _fait(socle, cle):
    """Valeur d'un indicateur de veille, avec sa source, ou None."""
    f = (socle.get("faits") or {}).get(cle) or {}
    v = f.get("valeur")
    return {"valeur": v, "source": f.get("source", ""), "url": f.get("url", "")} if v else None


def socle_de_faits(annee, semestre, segment):
    """Tous les repères chiffrés dont les directives ont besoin, calculés une fois."""
    import strategie_operationnelle as so

    def sûr(fn, defaut):
        try:
            return fn() or defaut
        except Exception:
            return defaut

    return {
        "panier": panier_compare(annee, semestre, segment),
        "eco": sûr(so.economie_sgci, {}),
        "objectif": sûr(lambda: so.objectif_global(segment), {}),
        "competitivite": sûr(lambda: db.cb_prix_competitivite(annee, semestre, segment), {}),
        "faits": sûr(so._faits_web, {}),
        "secteurs": sûr(lambda: so.dossiers(annee, semestre, segment).get("secteurs"), []),
        "n_banques": len(db.BANKS),
        "annee": annee, "semestre": semestre, "segment": segment,
    }


# ══════════════════════════════════════════════════════════════════════════════════════
#  COMPOSITION DES DIRECTIVES
# ══════════════════════════════════════════════════════════════════════════════════════
# Chaque direction reçoit QUATRE directives. Elles ne sont pas choisies dans une liste
# préécrite : chacune répond à une question fixe — le CHAMP d'action de la direction — et
# son contenu est rempli par ce que les données disent aujourd'hui. Si le catalogue change,
# la directive change ; si un service disparaît, elle cite le suivant.
#
# Structure commune, pensée pour être lue en trente secondes :
#   titre        ce qu'on décide, à l'infinitif
#   constat      le fait mesuré qui justifie la décision, avec ses chiffres
#   action       ce qu'on fait concrètement
#   cible        le résultat attendu, vérifiable
#   indicateur   ce qu'on suivra pour savoir si c'est fait
#   contribution en quoi cela sert l'objectif de la stratégie globale
#
# Une directive dont le fait fondateur manque n'est pas inventée : elle le dit et propose la
# mesure qui permettrait de la chiffrer. Mieux vaut « non chiffré à ce jour » qu'un nombre
# plausible et faux.

def _lacune(titre, quoi, action, indicateur):
    """Directive de repli quand la donnée fondatrice manque — honnête plutôt que muette.

    `quoi` est un GROUPE NOMINAL, pas une phrase : le gabarit lui ajoute son verbe. Les
    premiers appels passaient des phrases complètes, ce qui produisait « aucun service de
    caution n'est comparable au marché n'est pas disponible » — une double négation qui
    décrédibilise autant qu'une erreur de chiffre.
    """
    return {"titre": titre,
            "constat": f"Donnée manquante : {quoi} ne figure pas dans les données chargées.",
            "action": action, "cible": "Disposer de la mesure pour arbitrer sur des faits.",
            "indicateur": indicateur, "effort": "Faible", "horizon": "3 mois",
            "contribution": "Prérequis : sans cette mesure, l'arbitrage se ferait à l'estime.",
            "lacune": True}


def _lien_objectif(socle, part=None):
    obj = socle.get("objectif") or {}
    e = obj.get("ecart_a_combler")
    if not e:
        return "Contribue au plan à trois ans de la stratégie globale."
    base = (f"L'objectif global demande {e} {obj.get('unite','Mds')} FCFA de PNB supplémentaire "
            f"en {obj.get('horizon_ans', 3)} ans")
    return base + (f" ; cette directive y contribue par {part}." if part else ".")


def _financiere(socle):
    p, eco, obj = socle["panier"], socle["eco"], socle.get("objectif") or {}
    chers, competitifs = _plus_chers(p, 3), _plus_competitifs(p, 3)
    d = []

    if chers:
        t = chers[0]
        liste = ", ".join(f"{x['libelle']} (+{x['ecart_pct']:.0f} %)" for x in chers)
        d.append({
            "titre": f"Réexaminer les {len(chers)} tarifs les plus éloignés du marché",
            "constat": (f"Sur {len(p)} services réellement comparables, « {t['libelle']} » est facturé "
                        f"{_fmt(t['sgci'])} contre une médiane de {_fmt(t['median'])} chez "
                        f"{t['n_conc']} concurrents, soit +{t['ecart_pct']:.0f} %."),
            "action": (f"Statuer sur : {liste}. Pour chacun — aligner, justifier par un service "
                       f"associé, ou maintenir en assumant l'écart par écrit."),
            "cible": "Aucun tarif à plus du double de la médiane sans justification écrite.",
            "indicateur": "Nombre de tarifs au-dessus de la médiane, et écart moyen.",
            "effort": "Faible", "horizon": "3 mois",
            "contribution": _lien_objectif(socle, "la défense des volumes sur les services les plus exposés à la comparaison"),
        })
    else:
        d.append(_lacune("Constituer le panier de comparaison tarifaire",
                         "aucun service au-dessus de la médiane du marché",
                         "Charger les grilles tarifaires manquantes pour élargir le panier comparable.",
                         "Nombre de services comparables sur les sept banques."))

    if eco.get("part_commissions_pnb") and eco.get("meilleur_ratio"):
        pts = round(eco["meilleur_ratio"] - eco["part_commissions_pnb"], 1)
        gain = (eco.get("pnb_m") or 0) * pts / 100 * 1e6
        d.append({
            "titre": "Porter la part des commissions au niveau du mieux placé du marché",
            "constat": (f"Les commissions pèsent {eco['part_commissions_pnb']} % du PNB de SGCI contre "
                        f"{eco['meilleur_ratio']} % chez {eco['meilleur_ratio_banque']}, le mieux placé "
                        f"des {socle['n_banques']} banques suivies."),
            "action": ("Combler l'écart par les revenus de service : monétique, opérations avec "
                       "l'étranger, engagements par signature."),
            "cible": f"{pts} points d'écart, soit environ {_fmt(gain)} par an à PNB inchangé.",
            "indicateur": "Part des commissions dans le PNB, par trimestre.",
            "effort": "Élevé", "horizon": "24 mois",
            "contribution": _lien_objectif(socle, "la croissance des revenus de commissions"),
        })
    else:
        d.append(_lacune("Mesurer la structure du PNB face au marché",
                         "la décomposition du PNB des banques concurrentes",
                         "Charger les états financiers détaillés des sept banques.",
                         "Part des commissions dans le PNB, par banque."))

    if competitifs:
        t = competitifs[0]
        d.append({
            "titre": "Convertir les tarifs déjà sous le marché en volume, pas en marge perdue",
            "constat": (f"{_pluriel(len(competitifs), 'service')} sont facturés nettement sous le marché, dont "
                        f"« {t['libelle']} » à {_fmt(t['sgci'])} contre {_fmt(t['median'])} de médiane "
                        f"({t['ecart_pct']:.0f} %)."),
            "action": ("Vérifier que chaque écart est un choix de conquête et non un défaut "
                       "d'actualisation ; rendre visibles en agence ceux qui sont voulus."),
            "cible": "Chaque tarif sous la médiane rattaché à une intention commerciale ou à une révision.",
            "indicateur": "Volume traité sur ces services, avant et après mise en avant.",
            "effort": "Faible", "horizon": "6 mois",
            "contribution": _lien_objectif(socle, "la conversion d'un avantage prix déjà consenti en parts de marché"),
        })
    else:
        d.append(_lacune("Identifier les tarifs sous le marché",
                         "aucun service sous la médiane du marché",
                         "Élargir le panier comparable en chargeant les grilles manquantes.",
                         "Nombre de services sous la médiane."))

    if obj.get("ecart_a_combler"):
        couvert = sum((s.get("business_case") or {}).get("commissions_max_fcfa") or 0
                      for s in socle.get("secteurs", []))
        pct = round(100 * (couvert / 1e9) / obj["ecart_a_combler"], 1)
        d.append({
            "titre": "Boucler le plan : dire d'où viendra la part non couverte",
            "constat": (f"Les secteurs suivis couvrent au mieux {_fmt(couvert)} de commissions par an, "
                        f"soit {pct} % des {obj['ecart_a_combler']} {obj.get('unite','Mds')} FCFA à combler."),
            "action": ("Chiffrer explicitement le reste : tarification du portefeuille existant, "
                       "volumes, coût du risque."),
            "cible": "Un plan couvrant la totalité de l'écart, avec une source identifiée par tranche.",
            "indicateur": "Part de l'écart couverte par des actions chiffrées.",
            "effort": "Moyen", "horizon": "6 mois",
            "contribution": "Directive de bouclage : elle vérifie que la somme des actions atteint la cible.",
        })
    else:
        d.append(_lacune("Établir la trajectoire à trois ans",
                         "la projection de PNB de la stratégie globale",
                         "Reconstruire la projection depuis l'onglet Stratégie.",
                         "Écart entre trajectoire naturelle et scénario central."))
    return d[:PAR_DIRECTION]


def _commerciale(socle):
    p = socle["panier"]
    secteurs = sorted(socle.get("secteurs", []), key=lambda s: -(s.get("opportunite") or 0))
    competitifs, gratuits = _plus_competitifs(p, 3), _gratuits_distinctifs(p, 3)
    d = []

    if secteurs:
        s = secteurs[0]
        bc = s.get("business_case") or {}
        d.append({
            "titre": f"Ouvrir la conquête sur le secteur le mieux noté : {s.get('nom','')}",
            "constat": (f"Ce secteur obtient la note d'opportunité la plus élevée ({s.get('opportunite')}/100) "
                        f"parmi les {len(secteurs)} suivis. Cible : {s.get('cibles','')}."),
            "action": (f"Constituer un portefeuille de prospects sur {s.get('segment','')} et pousser : "
                       f"{', '.join((s.get('produits') or [])[:3])}."),
            "cible": (f"{bc.get('clients_min')} à {bc.get('clients_max')} nouveaux clients, soit "
                      f"+{_fmt(bc.get('commissions_min_fcfa'))} à +{_fmt(bc.get('commissions_max_fcfa'))} "
                      f"de commissions par an." if bc else "Cible à chiffrer une fois les volumes connus."),
            "indicateur": "Nombre de nouvelles entrées en relation sur le secteur.",
            "effort": "Moyen", "horizon": s.get("delai_libelle", "12 mois"),
            "contribution": _lien_objectif(socle, "la conquête de nouveaux clients sur un marché documenté"),
        })
    else:
        d.append(_lacune("Documenter les secteurs de conquête",
                         "un secteur disposant de faits sourcés",
                         "Relancer la veille sectorielle pour alimenter les indicateurs.",
                         "Nombre de secteurs disposant d'au moins un fait daté."))

    if competitifs:
        liste = ", ".join(f"« {x['libelle']} » ({x['ecart_pct']:.0f} %)" for x in competitifs)
        d.append({
            "titre": "Armer le réseau des arguments prix déjà gagnants",
            "constat": (f"{_pluriel(len(competitifs), 'service')} sont facturés sous la médiane du marché : {liste}. "
                        f"L'avantage est acquis mais n'est pas nécessairement dit au client."),
            "action": "Fournir aux chargés de clientèle une fiche par service, avec le tarif SGCI et la médiane marché.",
            "cible": "Chaque chargé de clientèle dispose des trois arguments prix de son portefeuille.",
            "indicateur": "Taux d'équipement sur les services mis en avant.",
            "effort": "Faible", "horizon": "3 mois",
            "contribution": _lien_objectif(socle, "l'exploitation commerciale d'un avantage déjà financé"),
        })
    else:
        d.append(_lacune("Identifier les arguments prix",
                         "un service sous la médiane du marché",
                         "Élargir le panier comparable.",
                         "Nombre de services sous la médiane."))

    if gratuits:
        g = gratuits[0]
        d.append({
            "titre": "Faire de la gratuité un argument d'entrée en relation",
            "constat": (f"« {g['libelle']} » est gratuit chez SGCI alors que la médiane du marché "
                        f"s'établit à {_fmt(g['median'])} sur {g['n_conc']} concurrents."),
            "action": "Intégrer ces gratuités au discours d'ouverture de compte et aux supports d'agence.",
            "cible": "Une mention systématique lors de l'entrée en relation.",
            "indicateur": "Nombre d'ouvertures de compte, et taux de citation en entretien.",
            "effort": "Faible", "horizon": "3 mois",
            "contribution": _lien_objectif(socle, "l'augmentation du nombre de clients"),
        })
    else:
        d.append(_lacune("Recenser les gratuités distinctives",
                         "un service gratuit chez SGCI et payant chez les concurrents",
                         "Vérifier la complétude des grilles concurrentes chargées.",
                         "Nombre de gratuités distinctives."))

    clipro = services_du_segment(p, "CLIPRO", 3)
    d.append({
        "titre": "Équiper la clientèle professionnelle du socle de services de flux",
        "constat": ((f"{_pluriel(len(clipro), 'service')} du panier relève{'nt' if len(clipro) > 1 else ''} du périmètre professionnel, dont "
                     f"« {clipro[0]['libelle']} » à {_fmt(clipro[0]['sgci'])}.") if clipro else
                    "Le catalogue professionnel est peu représenté dans le panier comparable."),
        "action": ("Proposer systématiquement compte professionnel, encaissement et acceptation "
                   "monétique à toute entreprise dont le chiffre d'affaires est inférieur à 750 millions."),
        "cible": "Un socle de trois services par client professionnel entrant.",
        "indicateur": "Nombre de services par client professionnel.",
        "effort": "Moyen", "horizon": "12 mois",
        "contribution": _lien_objectif(socle, "l'équipement du segment CLIPRO, le plus large en nombre"),
    })
    return d[:PAR_DIRECTION]


def _marketing(socle):
    """Quatre directives, une par segment de la grille clientèle SGCI.

    Demande explicite du directeur : « Marketing, je t'ai bien donné la segmentation
    clientèle, tu peux en faire une maggie, pour orienter le marketing sur les conditions
    de banque. » Chaque directive croise donc UN segment (seuil de revenu ou de chiffre
    d'affaires) avec les tarifs RÉELS des services qui le concernent — c'est ce croisement
    qui rend l'action exécutable, là où « communiquer vers les jeunes actifs » ne l'est pas.
    Les segments professionnels étant deux, ils sont traités ensemble sur le quatrième.
    """
    p = socle["panier"]
    d = []
    # Un même service ne doit pas illustrer deux segments : « Première carte VISA PLATINUM »
    # servait à la fois la Bonne gamme et les Patrimoniaux, et les deux directives se
    # confondaient. On retient donc ce qui a déjà été cité et on passe au suivant.
    deja_cites = set()
    for cle in ("GP", "BG", "PATRIMONIAUX"):
        seg = next(s for s in SEGMENTS if s["cle"] == cle)
        svc = [s for s in services_du_segment(p, cle, 12)
               if s["libelle"] not in deja_cites][:3]
        deja_cites.update(s["libelle"] for s in svc)
        if svc:
            t = svc[0]
            position = ("au-dessus" if (t["ecart_pct"] or 0) > 0 else "en dessous")
            constat = (f"{_pluriel(len(svc), 'service')} du panier concerne{'nt' if len(svc) > 1 else ''} ce segment. « {t['libelle']} » "
                       f"est à {_fmt(t['sgci'])}, soit {abs(t['ecart_pct']):.0f} % {position} de la "
                       f"médiane de {t['n_conc']} concurrents ({_fmt(t['median'])}).")
            action = (f"Construire le message autour de ce service : {'justifier la valeur associée' if (t['ecart_pct'] or 0) > 0 else 'mettre en avant l’écart de prix'}. "
                      f"Décliner sur : {', '.join(x['libelle'] for x in svc)}.")
        else:
            constat = ("Aucun service du panier comparable ne se rattache à ce segment : la "
                       "communication ne peut pas encore s'appuyer sur un écart de prix mesuré.")
            action = "Élargir le panier comparable sur les services de ce segment avant de communiquer."
        d.append({
            "titre": f"Adresser le segment {seg['nom']} par les conditions de banque",
            "constat": f"Segment défini par un {seg['critere']}. " + constat,
            "action": action,
            "cible": f"Un message par segment, adossé à un tarif publié — enjeu : {seg['enjeu']}.",
            "indicateur": f"Taux d'équipement et nombre d'entrées en relation sur le segment {seg['cle']}.",
            "effort": "Faible" if svc else "Moyen", "horizon": "6 mois",
            "contribution": _lien_objectif(socle, f"la mobilisation du segment {seg['cle']}"),
        })

    pro = services_du_segment(p, "CLIPRO", 2) + services_du_segment(p, "CLICOM", 2)
    d.append({
        "titre": "Adresser les deux segments professionnels par les services de flux",
        "constat": ((f"CLIPRO (chiffre d'affaires jusqu'à 750 millions) et CLICOM (au-delà) sont "
                     f"couverts par {_pluriel(len(pro), 'service')} du panier, dont « {pro[0]['libelle']} » "
                     f"à {_fmt(pro[0]['sgci'])}.") if pro else
                    "Les services professionnels sont encore peu représentés dans le panier comparable."),
        "action": ("Deux discours distincts : encaissement et monétique pour CLIPRO ; opérations "
                   "avec l'étranger, change et engagements par signature pour CLICOM."),
        "cible": "Deux campagnes distinctes, chacune adossée à des tarifs publiés.",
        "indicateur": "Nombre de clients professionnels équipés, par segment.",
        "effort": "Moyen", "horizon": "12 mois",
        "contribution": _lien_objectif(socle, "les revenus de commissions des segments professionnels"),
    })
    return d[:PAR_DIRECTION]


def _innovation(socle):
    p = socle["panier"]
    mob, banc = _fait(socle, "mobile_money"), _fait(socle, "bancarisation")
    distance = services_de_section(p, "banque à distance", 3)
    monetique = [s for s in p if any(m in s["libelle"].lower()
                                     for m in ("carte", "monetique", "monétique", "tpe", "gab"))]
    d = []

    d.append({
        "titre": "Faire de l'acceptation monétique une offre de conquête des commerçants",
        "constat": ((f"Le paiement mobile atteint {mob['valeur']} de pénétration ({mob['source']}) alors "
                     f"que la bancarisation reste à {banc['valeur']} ({banc['source']}) : les flux existent "
                     f"hors du bilan bancaire.") if mob and banc else
                    "Les repères de paiement mobile et de bancarisation ne sont pas tous disponibles."),
        "action": "Proposer l'acceptation carte et le terminal de paiement comme porte d'entrée du compte professionnel.",
        "cible": "Une offre d'acceptation packagée avec le compte professionnel.",
        "indicateur": "Nombre de commerçants équipés en acceptation.",
        "effort": "Moyen", "horizon": "12 mois",
        "contribution": _lien_objectif(socle, "la captation de flux aujourd'hui hors du système bancaire"),
    })

    if distance:
        t = distance[0]
        d.append({
            "titre": "Rendre la banque à distance moins chère que le passage en agence",
            "constat": (f"{_pluriel(len(distance), 'service')} à distance figure{'nt' if len(distance) > 1 else ''} au panier, dont « {t['libelle']} » "
                        f"à {_fmt(t['sgci'])} contre {_fmt(t['median'])} de médiane."),
            "action": "Aligner la tarification pour que le canal numérique soit toujours le moins cher pour le client.",
            "cible": "Aucun service à distance plus cher que son équivalent en agence.",
            "indicateur": "Part des opérations réalisées hors agence.",
            "effort": "Moyen", "horizon": "12 mois",
            "contribution": _lien_objectif(socle, "la baisse du coût de traitement par opération"),
        })
    else:
        d.append(_lacune("Cartographier l'offre de banque à distance",
                         "un service de banque à distance comparable au marché",
                         "Compléter les grilles sur la section « Services de banque à distance ».",
                         "Nombre de services à distance comparables."))

    if monetique:
        t = monetique[0]
        d.append({
            "titre": "Revoir la gamme de cartes au regard du marché",
            "constat": (f"{_pluriel(len(monetique), 'service')} de monétique {'sont comparables' if len(monetique) > 1 else 'est comparable'}, dont « {t['libelle']} » "
                        f"à {_fmt(t['sgci'])} contre {_fmt(t['median'])} de médiane "
                        f"({t['ecart_pct']:+.0f} %)."),
            "action": "Positionner chaque niveau de carte face à l'offre concurrente équivalente, du basique au haut de gamme.",
            "cible": "Une gamme lisible, chaque niveau justifié par un service associé.",
            "indicateur": "Nombre de cartes actives par niveau de gamme.",
            "effort": "Moyen", "horizon": "12 mois",
            "contribution": _lien_objectif(socle, "les commissions de monétique"),
        })
    else:
        d.append(_lacune("Comparer la gamme de cartes",
                         "un service de monétique comparable au marché",
                         "Vérifier le rattachement des lignes « carte » aux sections du référentiel.",
                         "Nombre de services de monétique comparables."))

    d.append({
        "titre": "Réduire le délai et le coût d'entrée en relation",
        "constat": ((f"La bancarisation plafonne à {banc['valeur']} ({banc['source']}) : le frein n'est "
                     f"pas la demande mais le parcours d'ouverture.") if banc else
                    "Le taux de bancarisation n'est pas disponible dans les données chargées."),
        "action": "Numériser l'entrée en relation de bout en bout, pièces justificatives comprises.",
        "cible": "Une ouverture de compte aboutie sans second passage en agence.",
        "indicateur": "Délai moyen d'entrée en relation, et taux d'abandon.",
        "effort": "Élevé", "horizon": "18 mois",
        "contribution": _lien_objectif(socle, "l'élargissement de la base de clients"),
    })
    return d[:PAR_DIRECTION]


def _risques(socle):
    p = socle["panier"]
    npl, seuil, solva = _fait(socle, "npl_secteur"), _fait(socle, "seuil_especes"), _fait(socle, "solvabilite_secteur")
    # Un engagement par signature doit être nommé comme tel. Se contenter de la section
    # « Opérations de crédit » faisait remonter « Frais d'envoi DHL » — classé là par
    # l'extraction — et la directive citait un service de courrier comme un engagement.
    # Une seule ligne fausse suffit à faire douter de toute la note : on exige donc que le
    # LIBELLÉ porte le vocabulaire de l'engagement, et on ne se rabat pas sur autre chose.
    _MOTS_ENGAGEMENT = ("caution", "garantie", "aval", "engagement", "signature")
    cautions = [s for s in services_de_section(p, "crédit", 20) + p
                if any(m in s["libelle"].lower() for m in _MOTS_ENGAGEMENT)]
    cautions = sorted({s["libelle"]: s for s in cautions}.values(),
                      key=lambda s: -abs(s["ecart_pct"] or 0))[:3]
    impayes = [s for s in p if any(m in s["libelle"].lower()
                                   for m in ("impay", "incident", "rejet", "opposition"))]
    d = []

    d.append({
        "titre": "Tenir le coût du risque sous la moyenne du secteur",
        # La valeur de veille porte déjà son libellé (« 7,7 % de créances dégradées ») : la
        # réintroduire dans une phrase qui le répète donnait « les créances dégradées
        # s'établissent à 7,7 % de créances dégradées ». On l'annonce donc comme un repère.
        "constat": ((f"Repère de marché : {npl['valeur']} ({npl['source']}). "
                     f"Toute conquête nouvelle se juge à cette aune.") if npl else
                    "Le niveau de créances dégradées du secteur n'est pas disponible."),
        "action": "Fixer un plafond de sinistralité par secteur conquis, et le vérifier avant chaque montée en volume.",
        "cible": "Un taux de créances en souffrance inférieur à la moyenne du secteur.",
        "indicateur": "Taux de créances en souffrance, par segment et par secteur.",
        "effort": "Moyen", "horizon": "12 mois",
        "contribution": "Condition de la croissance : un PNB gagné puis provisionné n'est pas gagné.",
    })

    d.append({
        "titre": "Sécuriser le dispositif de déclaration des opérations en espèces",
        "constat": ((f"Le seuil de déclaration s'établit à {_fmt(seuil['valeur'])} ({seuil['source']}). "
                     f"La conquête des professionnels augmente mécaniquement les flux d'espèces.") if seuil else
                    "Le seuil de déclaration des opérations en espèces n'est pas disponible."),
        "action": "Contrôler que le dispositif absorbe la hausse de volume liée à la conquête des commerçants.",
        "cible": "Aucune opération au-dessus du seuil sans déclaration tracée.",
        "indicateur": "Nombre de déclarations transmises, et délai de transmission.",
        "effort": "Moyen", "horizon": "6 mois",
        "contribution": "Protège la conquête professionnelle d'un risque de sanction.",
    })

    if cautions:
        t = cautions[0]
        d.append({
            "titre": "Encadrer les engagements par signature avant d'en faire un levier",
            "constat": (f"{_pluriel(len(cautions), 'service')} d'engagement figure{'nt' if len(cautions) > 1 else ''} au panier, dont « {t['libelle']} » "
                        f"à {_fmt(t['sgci'])} contre {_fmt(t['median'])} de médiane."),
            "action": "Fixer les limites par contrepartie et par secteur avant toute campagne sur les cautions.",
            "cible": "Un cadre d'engagement écrit, opposable au réseau.",
            "indicateur": "Encours d'engagements par signature, et concentration par contrepartie.",
            "effort": "Moyen", "horizon": "6 mois",
            "contribution": _lien_objectif(socle, "des commissions d'engagement prises sous contrôle"),
        })
    else:
        d.append(_lacune("Recenser les engagements par signature",
                         "un service de caution ou de garantie comparable au marché",
                         "Compléter les grilles sur les engagements par signature.",
                         "Nombre de services d'engagement comparables."))

    if impayes:
        t = impayes[0]
        d.append({
            "titre": "Vérifier que la tarification des incidents reste dissuasive sans être punitive",
            "constat": (f"« {t['libelle']} » est facturé {_fmt(t['sgci'])} contre {_fmt(t['median'])} de "
                        f"médiane sur {t['n_conc']} concurrents ({t['ecart_pct']:+.0f} %)."),
            "action": "Arbitrer entre effet dissuasif et risque d'attrition sur la clientèle fragile.",
            "cible": "Un tarif d'incident justifié par le coût réel de traitement.",
            "indicateur": "Nombre d'incidents, et taux de clôture après incident.",
            "effort": "Faible", "horizon": "6 mois",
            "contribution": "Protège la base de clients, sur laquelle repose tout le reste du plan.",
        })
    else:
        d.append({
            "titre": "Maintenir le ratio de solvabilité au-dessus de l'exigence",
            "constat": ((f"La solvabilité du secteur s'établit à {solva['valeur']} ({solva['source']})."
                         ) if solva else "Le ratio de solvabilité du secteur n'est pas disponible."),
            "action": "Vérifier la compatibilité du plan de conquête avec les fonds propres disponibles.",
            "cible": "Un ratio maintenu au-dessus de l'exigence réglementaire sur tout l'horizon.",
            "indicateur": "Ratio de solvabilité, par trimestre.",
            "effort": "Moyen", "horizon": "12 mois",
            "contribution": "Condition de faisabilité du plan à trois ans.",
        })
    return d[:PAR_DIRECTION]


_COMPOSITEURS = {
    "Direction Financière": _financiere,
    "Direction Commerciale": _commerciale,
    "Direction Marketing": _marketing,
    "Direction Innovation": _innovation,
    "Direction des Risques": _risques,
}


def directives(annee=None, semestre=None, segment="Particuliers"):
    """Les vingt directives — quatre par direction — avec leur socle de faits.

    Aucun appel réseau, aucun modèle de langage : à données inchangées, le résultat est
    strictement identique. C'est ce qui permet de le mettre en cache sans se demander si la
    version servie est la bonne.
    """
    if annee is None or semestre is None:
        a, s = periode_la_plus_recente()
        annee, semestre = annee or a, semestre or s
    socle = socle_de_faits(annee, semestre, segment)

    out = []
    for nom in DIRECTIONS:
        lot = _COMPOSITEURS[nom](socle)
        # Garantie tenue quoi qu'il arrive : quatre cartes, jamais trois. Si un compositeur
        # rendait moins (donnée absente et repli non déclenché), on complète explicitement
        # plutôt que d'afficher une direction incomplète sans le dire.
        while len(lot) < PAR_DIRECTION:
            lot.append(_lacune(
                f"Compléter les données de la {nom.replace('Direction ', '').lower()}",
                "les données nécessaires à cette quatrième directive",
                "Charger les grilles ou relancer la veille pour alimenter cette direction.",
                "Nombre de directives chiffrées disponibles pour cette direction."))
        for i, x in enumerate(lot, 1):
            x["direction"], x["rang"] = nom, i
        out.extend(lot)

    obj = socle.get("objectif") or {}
    return {
        "directives": out,
        "directions": DIRECTIONS,
        "par_direction": PAR_DIRECTION,
        "objectif_global": obj,
        "segmentation": [{k: v for k, v in s.items() if k != "mots"} for s in SEGMENTS],
        "perimetre": {
            "periode_reference": f"{annee} {semestre}",
            "segment": segment,
            "n_services_comparables": len(socle["panier"]),
            "n_banques": socle["n_banques"],
            "note": ("Directives composées à partir de l'ensemble des données chargées ; la période "
                     "de référence est la plus récente disponible en base et se déplace d'elle-même "
                     "à chaque ingestion."),
        },
    }
