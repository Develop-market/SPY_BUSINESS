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
import json
import os
import statistics

from functools import lru_cache

import db

# Faits de veille — dossier data/, conservé (contrairement aux caches qui se régénèrent).
WEB_FACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                         "data", "web_facts.json")

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
def panier_compare(annee, semestre, segment=None):
    """Services où SGCI ET au moins deux concurrents affichent un montant comparable.

    Sans deux concurrents, la « médiane marché » n'est qu'un autre concurrent déguisé en
    marché. Renvoie des dictionnaires plats, plus faciles à trier que l'arborescence de
    cb_prix_par_libelle.

    SEGMENT FACULTATIF (2026-08-07, question du directeur : « pourquoi Particuliers
    seulement ? »). Les directives ne voyaient qu'un segment : 55 services Entreprises
    comparables — 46 % du catalogue comparable — n'entraient dans aucun raisonnement. Or
    aucune des cinq directions ne travaille sur un seul segment : la Financière suit un PNB
    consolidé, le Marketing tient une grille qui couvre les deux, les Risques répondent d'un
    portefeuille entier. Sans argument, le panier réunit donc TOUS les segments présents en
    base, chaque service gardant le sien pour qu'on sache toujours de quoi on parle.
    """
    if segment is None:
        out = []
        try:
            segments = [r["segment"] for r in db.query(
                "SELECT DISTINCT segment FROM cb_tarifs WHERE segment IS NOT NULL "
                "ORDER BY segment")]
        except Exception:
            segments = ["Particuliers", "Entreprises"]
        for seg in segments:
            out.extend(panier_compare(annee, semestre, seg))
        return out

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
                    # Le segment voyage avec le service : un tarif cité sans lui laisse croire
                    # qu'il vaut pour tout le monde, alors que la grille les distingue.
                    "segment": segment,
                    "sgci": prix, "median": med, "n_conc": len(concurrents),
                    "moins_cher": min(concurrents, key=lambda x: x[1]),
                    "ecart_pct": (100 * (prix - med) / med) if med else None,
                })
    return out


def cite(service):
    """Nom d'un service suivi de son segment — « X (Entreprises) ».

    Le panier réunit désormais les deux segments. Citer « Frais d'impayés à 34 650 F » sans
    dire de quelle grille il vient laisserait croire que le tarif vaut pour tout le monde,
    alors que les grilles Particuliers et Entreprises les distinguent.
    """
    lib = str((service or {}).get("libelle") or "").strip()
    seg = (service or {}).get("segment")
    return f"{lib} ({seg})" if seg else lib


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


def services_par_mots(panier, mots, n=3):
    """Services dont le LIBELLÉ contient l'un des mots donnés.

    Complément indispensable à services_de_section : les neuf sections canoniques BCEAO ne
    nomment aucun instrument. Aucune ne contient « carte » — la monétique est répartie dans
    « Services rattachés au fonctionnement du compte ». Chercher la gamme de cartes par
    section ne pouvait donc RIEN rendre, et la directive Marketing tombait invariablement en
    repli en annonçant qu'aucun service de monétique n'était comparable, alors que le
    catalogue en contient (défaut trouvé le 2026-08-07).
    """
    bas = tuple(m.lower() for m in mots)
    cand = [s for s in panier if any(m in (s.get("libelle") or "").lower() for m in bas)]
    return sorted(cand, key=lambda s: -abs(s["ecart_pct"] or 0))[:n]


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


# ── SIGNAL DE MARCHÉ RATTACHÉ À CHAQUE DIRECTIVE ─────────────────────────────────────
# AJOUTÉ LE 2026-08-07 après une remarque du directeur : « pas sur les données sectorielles,
# politiques ? »
#
# Il avait raison, et le sous-titre de la page le disait sans le vouloir : les directives se
# fondaient sur les grilles tarifaires et les états financiers, c'est-à-dire uniquement sur
# ce que la banque observe d'elle-même. Cinq indicateurs macro seulement entraient dans le
# raisonnement ; le prix du cacao, le calendrier de campagne, le coût du crédit, le poids de
# l'informel, les programmes publics et les décisions BCEAO n'y entraient pas du tout.
#
# Une directive purement interne retombe dans le travers déjà sanctionné une fois : l'audit
# tarifaire déguisé en stratégie. Une banque ne décide pas parce que son tarif dépasse la
# médiane, elle décide parce que le marché bouge ET que son tarif la dessert.
#
# Chaque directive porte donc désormais un SIGNAL EXTERNE — un indicateur sectoriel ou
# politique, ou un événement de marché daté — choisi dans le champ de la direction. Le signal
# ne remplace pas la mesure interne : il lui donne sa raison d'être maintenant.
#
# Rien n'est écrit en dur : on déclare quels indicateurs et quels domaines d'événements
# concernent chaque direction, et le contenu vient de la veille du jour.
SIGNAUX_PAR_DIRECTION = {
    "Direction Financière": {
        "faits": ["cout_credit", "politique_monetaire", "croissance_macro", "commerce_exterieur"],
        "domaines": ["reglementation", "banque_concurrence", "infrastructure"],
    },
    "Direction Commerciale": {
        "faits": ["cacao_prix", "cacao_campagne", "anacarde", "coton", "financement_pme"],
        "domaines": ["agro", "infrastructure", "banque_concurrence"],
    },
    "Direction Marketing": {
        "faits": ["bancarisation", "mobile_money", "commerce_informel", "structure_marche"],
        "domaines": ["social", "numerique", "banque_concurrence"],
    },
    "Direction Innovation": {
        "faits": ["mobile_money", "commerce_tpe", "bancarisation", "btp_investissement"],
        "domaines": ["numerique", "banque_concurrence", "infrastructure"],
    },
    "Direction des Risques": {
        "faits": ["npl_secteur", "solvabilite_secteur", "seuil_especes", "btp_logement"],
        "domaines": ["reglementation", "environnement", "agro"],
    },
}


def _titre_indicateur(cle, fait):
    """Nom lisible d'un indicateur de veille.

    Les indicateurs seedés à la main portent un `titre` ; ceux créés par une collecte n'en
    ont pas, et la carte affichait alors la clé technique (« btp investissement »). Plutôt
    qu'une table de correspondance à tenir à jour — qui serait périmée au prochain indicateur
    ajouté — on relit le libellé que la veille déclare elle-même pour cette clé. Import
    différé : run_veille tire Tavily et Groq, inutiles au simple affichage.
    """
    t = (fait.get("titre") or "").strip()
    if t:
        return t
    try:
        import run_veille as rv
        spec = (rv.INDICATEURS_FILIERES.get(cle) or rv.INDICATEURS.get(cle))
        if spec and spec[0]:
            # Le libellé de veille est une phrase de recherche (« Trafic du Port autonome
            # d'Abidjan (tonnes ou conteneurs par an) ») : on garde ce qui précède la
            # parenthèse d'unité, qui ferait doublon avec l'unité affichée juste après.
            brut = spec[0].split("(")[0].strip().rstrip(",")
            # « … en Côte d'Ivoire » est vrai de tous les indicateurs de ce tableau de bord :
            # le répéter sur chaque carte allonge sans informer.
            for suffixe in (" en Côte d'Ivoire", " de la Côte d'Ivoire", " en Cote d'Ivoire"):
                if brut.lower().endswith(suffixe.lower()):
                    brut = brut[: -len(suffixe)].rstrip()
                    break
            # Majuscule initiale SANS toucher au reste : .capitalize() aurait transformé
            # « Port autonome d'Abidjan » en « port autonome d'abidjan ».
            return (brut[:1].upper() + brut[1:]) if brut else cle.replace("_", " ")
    except Exception:
        pass
    return cle.replace("_", " ").capitalize()


def _valeur_indicateur(cle, valeur):
    """Valeur d'un indicateur suivie de son unité, sans doublon.

    La veille ne retient que le nombre : servi tel quel, « 2 962,7 » ne dit pas s'il s'agit de
    milliards ou de tonnes. L'unité est une propriété connue de l'indicateur — elle est
    déclarée une seule fois, dans strategie_operationnelle._UNITES, et lue ici.
    """
    v = str(valeur or "").strip()
    if not v:
        return "—"
    try:
        import strategie_operationnelle as so
        return so._avec_unite(cle, v)
    except Exception:
        return v


def _evenements_domaines(socle, domaines):
    """Événements de marché relevant des domaines suivis par une direction, récents d'abord.

    Les événements disent ce qui vient de BOUGER — un programme public lancé, une instruction
    publiée, un concurrent qui s'installe. C'est ce qui rend une directive urgente plutôt que
    seulement fondée.
    """
    evts = socle.get("evenements") or []
    lot = [e for e in evts if e.get("domaine") in domaines and e.get("fait")]
    return sorted(lot, key=lambda e: e.get("releve_le") or "", reverse=True)


def signaux_direction(socle, direction):
    """File de signaux externes disponibles pour une direction, indicateurs puis événements.

    Les indicateurs passent en premier : ils sont chiffrés et datés, donc plus solides qu'une
    annonce. Les événements complètent quand les indicateurs manquent — et souvent ils
    apportent ce qu'aucun indicateur ne donne : un acteur, une intention, une échéance.
    """
    spec = SIGNAUX_PAR_DIRECTION.get(direction) or {}
    out = []
    for cle in spec.get("faits", []):
        f = (socle.get("faits") or {}).get(cle) or {}
        if not f.get("valeur"):
            continue
        titre = _titre_indicateur(cle, f)
        valeur = _valeur_indicateur(cle, f.get("valeur"))
        detail = (f.get("detail") or "").strip()
        out.append({
            "nature": "indicateur",
            "texte": f"{titre} : {valeur}" + (f" — {detail}" if detail else ""),
            "source": f.get("source", ""), "url": f.get("url", ""),
        })
    for e in _evenements_domaines(socle, spec.get("domaines", [])):
        montant = f" ({e['montant']})" if e.get("montant") else ""
        quand = f" · {e['date_citee']}" if e.get("date_citee") else ""
        out.append({
            "nature": "événement",
            "texte": f"{e.get('acteur','')} {e.get('fait','')}{montant}{quand}".strip(),
            "source": e.get("domaine", ""), "url": e.get("url", ""),
            "portee": e.get("portee", ""),
        })
    return out


def socle_de_faits(annee, semestre, segment):
    """Tous les repères chiffrés dont les directives ont besoin, calculés une fois."""
    import strategie_operationnelle as so

    def sûr(fn, defaut):
        try:
            return fn() or defaut
        except Exception:
            return defaut

    return {
        # Panier SUR TOUS LES SEGMENTS (segment=None) : aucune des cinq directions ne travaille
        # sur un seul. Le paramètre `segment` reste utilisé plus bas pour les dossiers
        # sectoriels et la projection, qui ont besoin d'une base explicite.
        "panier": panier_compare(annee, semestre, None),
        "eco": sûr(so.economie_sgci, {}),
        "objectif": sûr(lambda: so.objectif_global(segment), {}),
        "competitivite": sûr(lambda: db.cb_prix_competitivite(annee, semestre, segment), {}),
        "faits": sûr(so._faits_web, {}),
        # Événements de marché : lus directement du fichier de veille plutôt que par secteur,
        # car une direction ne raisonne pas par filière mais par domaine (réglementaire,
        # concurrentiel, infrastructures…).
        "evenements": sûr(lambda: json.load(
            open(WEB_FACTS, encoding="utf-8")).get("evenements"), []),
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


_MOTS_VIDES = {
    "les", "des", "que", "qui", "pour", "avec", "dans", "sur", "par", "aux", "une", "son",
    "sa", "ses", "leur", "plus", "moins", "sous", "sans", "vers", "chez", "entre", "cette",
    "faire", "mettre", "porter", "tenir", "rendre", "ne", "pas", "est", "sont", "au", "et",
    "de", "du", "la", "le", "en", "un", "à", "d", "l", "n", "se", "y", "ou", "il",
    # MOTS TROP GÉNÉRAUX pour rattacher une directive à un secteur (2026-08-07). Ils
    # apparaissent partout et créent des liens faux : « coefficient d'exploitation du MARCHÉ »
    # s'accrochait à « cautions de MARCHÉ » du BTP, deux sens sans rapport. Les garder revenait
    # à apparier au hasard tout en ayant l'air de raisonner.
    "marché", "marche", "marchés", "banque", "banques", "bancaire", "bancaires", "client",
    "clients", "clientèle", "clientele", "service", "services", "compte", "comptes", "offre",
    "offres", "taux", "coût", "cout", "coûts", "prix", "montant", "nombre", "part", "parts",
    "niveau", "moyen", "moyenne", "total", "gestion", "mise", "place", "suivi", "cette",
}


def _mots_significatifs(texte):
    mots = "".join(c if c.isalnum() else " " for c in str(texte or "").lower()).split()
    return {m for m in mots if len(m) > 3 and m not in _MOTS_VIDES}


def _terrain_pertinent(directive, terrains, deja_pris):
    """Sur quel secteur cette directive s'exerce-t-elle vraiment ?

    Une rotation mécanique produisait des couples absurdes : « défendre le coefficient
    d'exploitation » rattaché à l'import-export, « sécuriser la déclaration des espèces »
    au financement des PME. Un directeur qui lit ça cesse de croire le reste de la carte.

    Deux critères, dans cet ordre :

      AFFINITÉ    mots partagés entre la directive (titre, action, cible) et le secteur
                  (nom, cibles, produits, indicateurs). C'est ce qui rattache « acceptation
                  de paiement » au numérique et « campagne » à l'agro-industrie.
      APPORT      à affinité comparable, le secteur qui rapporte le plus. Une directive de
                  revenus doit viser le terrain où il y a le plus à prendre — c'est
                  exactement ce que demande le comité : « pour augmenter ses commissions,
                  faire un focus sur le café-cacao ».

    Un secteur déjà retenu par une autre directive de la même direction est pénalisé, sans
    être exclu : quatre directives sur un seul terrain diraient quatre fois la même chose,
    mais forcer quatre terrains différents quand il n'y en a que deux serait pire.
    """
    mots_d = _mots_significatifs(
        f"{directive.get('titre','')} {directive.get('action','')} {directive.get('cible','')}")
    apport_max = max((float((s.get('business_case') or {}).get('commissions_max_fcfa') or 0)
                      for s in terrains), default=0.0)

    def affinite(s):
        mots_s = _mots_significatifs(
            f"{s.get('nom','')} {s.get('cibles','')} "
            f"{' '.join(s.get('produits') or [])} {' '.join(s.get('indicateurs') or [])}")
        return len(mots_d & mots_s)

    def score(s):
        apport = float((s.get("business_case") or {}).get("commissions_max_fcfa") or 0)
        apport_norm = (apport / apport_max) if apport_max else 0.0
        penalite = 0.6 if s.get("cle") in deja_pris else 0.0
        return affinite(s) * 2.0 + apport_norm - penalite

    meilleur = max(terrains, key=score)

    # AUCUNE AFFINITÉ MESURÉE : la directive ne parle d'aucun secteur en particulier. C'est le
    # cas des sujets transversaux — coefficient d'exploitation, bouclage du plan, cohérence de
    # la grille publiée. Leur coller un secteur produirait exactement le faux lien qu'on
    # cherche à éviter (« défendre le coefficient d'exploitation → BTP »).
    if affinite(meilleur) == 0:
        # Sauf si la directive vise explicitement des revenus ou de la conquête : là, désigner
        # le terrain qui rapporte le plus est une recommandation utile, et non un lien inventé.
        # C'est la demande du comité : « pour augmenter ses commissions, faire un focus sur le
        # café-cacao ». Le rendu le présente alors comme un terrain À PRIVILÉGIER, pas comme le
        # champ d'application de la directive.
        vise_revenus = bool(mots_d & {"commission", "commissions", "revenus", "conquête",
                                      "conquete", "clients", "volume", "volumes", "parts",
                                      "marge", "pnb"})
        if not vise_revenus:
            return None
        meilleur = dict(meilleur, _recommande=True)
    return meilleur


def _bloc_tarifs_chers(socle):
    """Services où SGCI s'écarte le plus de la médiane — décision de MARKETING.

    Ce bloc figurait sous la Direction Financière ; il relève du Marketing, qui fixe les
    conditions de banque. Un directeur financier arbitre une structure de revenus, pas le
    prix d'un service au guichet.
    """
    p = socle["panier"]
    chers = _plus_chers(p, 3)
    if not chers:
        return {
            "titre": "Tenir le niveau des tarifs sous surveillance",
            "constat": (f"Sur {len(p)} services réellement comparables, aucun ne dépasse nettement "
                        f"la médiane du marché."),
            "action": "Maintenir la revue à chaque parution de grille concurrente.",
            "cible": "Aucun tarif ne s'éloigne de la médiane sans décision explicite.",
            "indicateur": "Nombre de tarifs au-dessus de la médiane, et écart moyen.",
            "effort": "Faible", "horizon": "6 mois",
            "contribution": _lien_objectif(socle, "la défense des volumes sur les services exposés à la comparaison"),
        }
    t = chers[0]
    liste = ", ".join(f"{cite(x)} (+{x['ecart_pct']:.0f} %)" for x in chers)
    return {
        "titre": f"Réexaminer les {len(chers)} tarifs les plus éloignés du marché",
        "constat": (f"Sur {len(p)} services réellement comparables, « {cite(t)} » est facturé "
                    f"{_fmt(t['sgci'])} contre une médiane de {_fmt(t['median'])} chez "
                    f"{t['n_conc']} concurrents, soit +{t['ecart_pct']:.0f} %."),
        "action": (f"Statuer sur : {liste}. Pour chacun — aligner, justifier par un service "
                   f"associé, ou maintenir en assumant l'écart par écrit."),
        "cible": "Aucun tarif à plus du double de la médiane sans justification écrite.",
        "indicateur": "Nombre de tarifs au-dessus de la médiane, et écart moyen.",
        "effort": "Faible", "horizon": "3 mois",
        "contribution": _lien_objectif(socle, "la défense des volumes sur les services les plus exposés à la comparaison"),
    }


def _bloc_gamme_cartes(socle):
    """Positionnement de la gamme de cartes face au marché — décision de MARKETING.

    Déplacé de l'Innovation le 2026-08-07 : décider du prix et du contenu d'un niveau de
    carte est une décision d'offre. L'Innovation numérise les parcours, elle ne fixe pas la
    gamme.
    """
    # Recherche par LIBELLÉ : aucune des neuf sections canoniques ne nomme la carte (cf.
    # services_par_mots). L'appel précédent passait une expression régulière à un comparateur
    # de sous-chaîne et ne rendait jamais rien.
    monetique = services_par_mots(
        socle["panier"], ("carte", "monétique", "monetique", "tpe", "marchand"), 4)
    if not monetique:
        return {
            "titre": "Positionner la gamme de cartes face au marché",
            "constat": "Aucun service de monétique n'est aujourd'hui comparable au marché dans "
                       "le panier retenu.",
            "action": "Comparer la gamme niveau par niveau dès que les grilles concurrentes "
                      "correspondantes sont chargées.",
            "cible": "Une gamme lisible, chaque niveau justifié par un service associé.",
            "indicateur": "Nombre de cartes actives par niveau de gamme.",
            "effort": "Moyen", "horizon": "12 mois",
            "contribution": _lien_objectif(socle, "les commissions de monétique"),
        }
    t = monetique[0]
    return {
        "titre": "Positionner la gamme de cartes face au marché",
        "constat": (f"{_pluriel(len(monetique), 'service')} de monétique "
                    f"{'sont comparables' if len(monetique) > 1 else 'est comparable'}, dont "
                    f"« {cite(t)} » à {_fmt(t['sgci'])} contre {_fmt(t['median'])} de médiane "
                    f"({t['ecart_pct']:+.0f} %)."),
        "action": ("Positionner chaque niveau de carte face à l'offre concurrente équivalente, "
                   "du basique au haut de gamme, et rattacher un service à chaque palier."),
        "cible": "Une gamme lisible, chaque niveau justifié par un service associé.",
        "indicateur": "Nombre de cartes actives par niveau de gamme.",
        "effort": "Moyen", "horizon": "12 mois",
        "contribution": _lien_objectif(socle, "les commissions de monétique"),
    }


def _bloc_automatisation(socle):
    """Automatiser les opérations qui occupent le guichet — décision d'INNOVATION.

    On ne dispose pas des volumes d'opérations par canal : les inventer serait le contraire
    de ce que fait ce module. En revanche on sait quels services sont GRATUITS chez SGCI
    tout en étant facturés ailleurs — ce sont, mécaniquement, ceux qui font venir en agence
    sans rien rapporter. Ce sont donc les premiers candidats à l'automatisation : leur coût
    de traitement est intégralement supporté par la banque.
    """
    gratuits = _gratuits_distinctifs(socle["panier"], 4)
    if gratuits:
        t = gratuits[0]
        liste = ", ".join(x["libelle"] for x in gratuits[:3])
        constat = (f"{_pluriel(len(gratuits), 'service')} rendus gratuitement par SGCI sont facturés "
                   f"par les concurrents, dont « {t['libelle'] }» ({_fmt(t['median'])} de médiane). "
                   f"Leur coût de traitement est entièrement supporté par la banque.")
        action = (f"Porter en priorité ces opérations sur les canaux automatisés : {liste}. "
                  f"Le gain n'est pas tarifaire, il est dans le temps de guichet libéré.")
    else:
        constat = ("Aucun service gratuit distinctif n'est identifié dans le panier comparable : "
                   "les candidats à l'automatisation ne peuvent pas encore être classés par coût "
                   "supporté.")
        action = ("Recenser les opérations les plus fréquentes en agence et les porter sur les "
                  "canaux automatisés en commençant par les plus répétitives.")
    return {
        "titre": "Automatiser les opérations qui occupent le guichet sans rien rapporter",
        "constat": constat, "action": action,
        "cible": "Chaque opération répétitive disponible sans passage en agence.",
        "indicateur": "Part des opérations traitées sans intervention humaine.",
        "effort": "Élevé", "horizon": "18 mois",
        "contribution": _lien_objectif(socle, "la baisse du coût de traitement, qui améliore le coefficient d'exploitation"),
    }


def _derniere_valeur(serie_banque):
    """Dernière valeur d'une série annuelle {« 2023 »: 39.2, …}, et son année."""
    if not isinstance(serie_banque, dict) or not serie_banque:
        return None, None
    an = max(serie_banque, key=lambda a: str(a))
    return serie_banque.get(an), an


def _bloc_coefficient(socle):
    """Coefficient d'exploitation de SGCI face au marché — un objectif purement financier.

    Charges générales rapportées au PNB : c'est la mesure d'efficacité que suit un directeur
    financier, et elle ne doit rien à la grille tarifaire. Les valeurs viennent des états
    financiers publiés des banques, dernier exercice disponible pour chacune.
    """
    try:
        series = db.ef_coeff_series() or {}
    except Exception:
        series = {}
    sgci, an_sgci = _derniere_valeur(series.get("SGCI") or {})
    autres = []
    for b, s in series.items():
        if b == "SGCI":
            continue
        v, an = _derniere_valeur(s)
        if v is not None:
            autres.append((b, float(v), an))

    if sgci is None or not autres:
        # On ne fabrique pas de constat : on dit ce qu'on sait faire avec ce qu'on a.
        return {
            "titre": "Suivre le coefficient d'exploitation face au marché",
            "constat": "Le coefficient d'exploitation des concurrents n'est pas encore calculable "
                       "sur les états financiers chargés.",
            "action": "Piloter le ratio charges générales sur PNB trimestre par trimestre.",
            "cible": "Un coefficient tenu sous le seuil de 70 % retenu par la BCEAO.",
            "indicateur": "Charges générales ÷ PNB, par trimestre.",
            "effort": "Moyen", "horizon": "12 mois",
            "contribution": _lien_objectif(socle, "la maîtrise des charges, qui libère du résultat sans vendre un franc de plus"),
        }

    sgci = float(sgci)
    autres.sort(key=lambda x: x[1])
    meilleur, val_meilleur, an_meilleur = autres[0]
    rang = 1 + sum(1 for _, v, _ in autres if v < sgci)
    n = len(autres) + 1
    ecart = round(sgci - val_meilleur, 1)
    devant = rang == 1

    if devant:
        constat = (f"SGCI affiche le meilleur coefficient d'exploitation du marché : {sgci:.1f} % "
                   f"en {an_sgci}, devant {meilleur} à {val_meilleur:.1f} % ({an_meilleur}), "
                   f"sur {n} banques comparées.")
        action = ("Tenir l'avance : chaque point gagné sur le coefficient tombe directement au "
                  "résultat, sans dépendre de la conquête commerciale.")
        cible = "Rester sous le meilleur coefficient du marché à chaque arrêté."
    else:
        constat = (f"Le coefficient d'exploitation de SGCI s'établit à {sgci:.1f} % en {an_sgci}, "
                   f"au {rang}ᵉ rang sur {n} banques ; {meilleur} tient {val_meilleur:.1f} % "
                   f"({an_meilleur}), soit {ecart:.1f} points de mieux.")
        action = ("Identifier les postes de charges qui expliquent l'écart et fixer une "
                  "trajectoire de retour au niveau du mieux placé.")
        cible = f"Refermer les {ecart:.1f} points d'écart avec {meilleur}."

    return {
        "titre": "Ramener le coefficient d'exploitation au niveau du mieux placé"
                 if not devant else "Défendre le meilleur coefficient d'exploitation du marché",
        "constat": constat, "action": action, "cible": cible,
        "indicateur": "Charges générales ÷ PNB, comparé au meilleur du marché à chaque arrêté.",
        "effort": "Élevé", "horizon": "24 mois",
        "contribution": _lien_objectif(socle, "la maîtrise des charges, qui libère du résultat sans vendre un franc de plus"),
    }


def _bloc_cout_ressources(socle):
    """Coût des ressources et marge d'intermédiation — l'autre levier proprement financier.

    Le taux directeur de la BCEAO fixe le coût du refinancement ; le taux débiteur moyen du
    marché dit à quel prix les banques prêtent. L'écart entre les deux est la marge dans
    laquelle SGCI travaille, et il se pilote sans toucher à un seul tarif de service.
    """
    directeur = (socle.get("faits") or {}).get("politique_monetaire") or {}
    debiteur = (socle.get("faits") or {}).get("cout_credit") or {}
    v_dir = str(directeur.get("valeur") or "").strip()
    v_deb = str(debiteur.get("valeur") or "").strip()

    if v_dir and v_deb:
        constat = (f"Le refinancement BCEAO est à {v_dir} ({directeur.get('source','')}) tandis que "
                   f"le taux débiteur moyen du marché s'établit à {v_deb} "
                   f"({debiteur.get('source','')}) : c'est l'amplitude dans laquelle se joue la "
                   f"marge d'intermédiation.")
        action = ("Arbitrer la structure des ressources — dépôts à vue, comptes à terme, "
                  "refinancement — au regard de ce coût, et répercuter dans la tarification "
                  "du crédit plutôt que dans celle des services.")
    elif v_dir or v_deb:
        connu = f"taux directeur {v_dir}" if v_dir else f"taux débiteur moyen {v_deb}"
        constat = (f"Un seul repère de coût des ressources est disponible à ce jour : {connu}. "
                   f"La marge d'intermédiation ne peut donc pas être encadrée par les deux bouts.")
        action = "Piloter le coût moyen des ressources collectées, trimestre par trimestre."
    else:
        constat = "Les repères de taux du marché monétaire ne sont pas disponibles à ce jour."
        action = "Piloter le coût moyen des ressources collectées à partir des états internes."

    return {
        "titre": "Piloter le coût des ressources et la marge d'intermédiation",
        "constat": constat, "action": action,
        "cible": "Un coût moyen des ressources connu et arbitré à chaque comité de trésorerie.",
        "indicateur": "Coût moyen des ressources, et marge d'intermédiation nette.",
        "effort": "Moyen", "horizon": "12 mois",
        "contribution": _lien_objectif(socle, "la marge d'intérêt, qui pèse le plus lourd dans le PNB"),
    }


def _coherence_grille(socle):
    """Directive de contrôle sur la cohérence de la grille tarifaire publiée de SGCI.

    Deux anomalies sont comptées directement en base, sur les lignes SGCI de la période de
    référence :
      - un montant inférieur à 100 F sur une ligne dont le libellé commence par une
        numérotation de section : l'extraction a pris le numéro de chapitre pour un prix ;
      - un montant à zéro sur une ligne qui n'est pas marquée gratuite.

    Ces deux comptages sont recalculés à chaque appel : si la base est corrigée, la directive
    le dit d'elle-même et son urgence tombe.
    """
    annee, semestre, segment = socle["annee"], socle["semestre"], socle["segment"]
    try:
        r = db.query(
            """
            SELECT
              COUNT(*) FILTER (
                WHERE montant IS NOT NULL AND montant < 100 AND est_gratuit = FALSE
                  AND valeur_propre ~ '^[0-9]+[.][0-9]+[.][0-9]+') AS num_section,
              COUNT(*) FILTER (WHERE montant = 0 AND est_gratuit = FALSE) AS zero_non_gratuit,
              COUNT(*) FILTER (WHERE montant IS NOT NULL) AS chiffrees
            FROM cb_tarifs
            WHERE banque='SGCI' AND annee=%s AND semestre=%s AND LOWER(segment)=LOWER(%s)
              AND is_header = FALSE
            """, (annee, semestre, segment))[0]
    except Exception:
        r = {}
    n_sec = int(r.get("num_section") or 0)
    n_zero = int(r.get("zero_non_gratuit") or 0)
    total = int(r.get("chiffrees") or 0)
    n = n_sec + n_zero

    if not total:
        # Aucune ligne chiffrée : on ne fabrique pas un constat, on décrit l'état réel.
        constat = "Aucune ligne tarifaire chiffrée pour SGCI sur la période de référence."
        action = "Vérifier le chargement de la grille SGCI avant tout arbitrage tarifaire."
    elif n:
        part = 100 * n / total
        constat = (f"Sur {total} lignes tarifaires SGCI chiffrées, {_pluriel(n, 'ligne')} "
                   f"({_pct(part)}) portent une valeur incohérente : "
                   f"{n_sec} reprennent un numéro de section en guise de montant, "
                   f"{n_zero} affichent zéro sans être marquées gratuites.")
        action = ("Reprendre ces lignes à la source (brochure publiée) et corriger la base, "
                  "en priorité celles qui apparaissent dans les comparatifs de prix.")
    else:
        constat = (f"Les {total} lignes tarifaires SGCI chiffrées passent les deux contrôles "
                   f"de cohérence : aucun numéro de section pris pour un montant, aucun zéro "
                   f"non déclaré gratuit.")
        action = ("Maintenir le contrôle à chaque ingestion de grille : c'est le moment où "
                  "l'anomalie s'introduit.")

    return {
        "titre": "Garantir la cohérence de la grille tarifaire publiée",
        "constat": constat,
        "action": action,
        "cible": "Zéro ligne publiée dont la valeur est démentie par la brochure.",
        "indicateur": "Nombre de lignes en anomalie, mesuré à chaque ingestion.",
        "effort": "Faible" if n < 50 else "Moyen",
        "horizon": "3 mois",
        "contribution": ("L'instruction BCEAO n°2011-01 impose de publier et d'afficher les "
                         "conditions de banque : une valeur publiée fausse est une exposition "
                         "réglementaire, et elle fausse aussi les arbitrages tarifaires."),
    }


def _lien_objectif(socle, part=None):
    obj = socle.get("objectif") or {}
    e = obj.get("ecart_a_combler")
    if not e:
        return "Contribue au plan à trois ans de la stratégie globale."
    base = (f"L'objectif global demande {e} {obj.get('unite','Mds')} FCFA de PNB supplémentaire "
            f"en {obj.get('horizon_ans', 3)} ans")
    return base + (f" ; cette directive y contribue par {part}." if part else ".")


# ── RÉPARTITION DES COMPÉTENCES (2026-08-07, correction du directeur) ────────────────
# « Les conditions de banque, tarifs… sont gérées par la Direction Marketing et non
#   Financière. La Direction Financière met en place des stratégies pour atteindre des
#   objectifs financiers. Innovation, c'est bien plus dans une optique de digitaliser les
#   process de la banque, créer des solutions innovantes. Ne mélangeons pas les décisions. »
#
# La première version rangeait le repositionnement tarifaire sous la Financière et la revue
# de gamme de cartes sous l'Innovation. Deux erreurs d'attribution : un directeur financier à
# qui l'on demande d'arbitrer un prix de carte n'y reconnaît pas son métier, et la carte
# perd sa force d'exécution — c'est celui dont c'est la responsabilité qui agit, pas celui
# qui lit la note.
#
#   Financière   objectifs financiers, mesurés sur les états financiers : structure du PNB,
#                coefficient d'exploitation, coût des ressources, bouclage du plan.
#   Marketing    conditions de banque : niveau des tarifs, gamme, offre par segment.
#   Commerciale  conquête : secteurs, équipement des clients, arguments donnés au réseau.
#   Innovation   transformation digitale : numériser les parcours et les process internes.
#   Risques      exposition : coût du risque, conformité, solvabilité, cohérence publiée.

def _financiere(socle):
    """Objectifs financiers — lus dans les états financiers, jamais dans la grille tarifaire."""
    eco, obj = socle["eco"], socle.get("objectif") or {}
    d = []

    d.append(_bloc_coefficient(socle))

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

    d.append(_bloc_cout_ressources(socle))

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
        liste = ", ".join(f"« {cite(x)} » ({x['ecart_pct']:.0f} %)" for x in competitifs)
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
    # LE MARKETING TIENT LES CONDITIONS DE BANQUE (2026-08-07). Le niveau des tarifs et le
    # positionnement de la gamme lui reviennent : ils étaient rangés sous la Financière et
    # l'Innovation, qui n'en décident pas. Deux cartes leur sont donc réservées ici, et les
    # segments de particuliers se partagent les deux restantes.
    d = [_bloc_tarifs_chers(socle), _bloc_gamme_cartes(socle)]
    # Un même service ne doit pas illustrer deux segments : « Première carte VISA PLATINUM »
    # servait à la fois la Bonne gamme et les Patrimoniaux, et les deux directives se
    # confondaient. On retient donc ce qui a déjà été cité et on passe au suivant.
    deja_cites = set()
    for cle in ("GP", "BG"):
        seg = next(s for s in SEGMENTS if s["cle"] == cle)
        svc = [s for s in services_du_segment(p, cle, 12)
               if s["libelle"] not in deja_cites][:3]
        deja_cites.update(s["libelle"] for s in svc)
        if svc:
            t = svc[0]
            position = ("au-dessus" if (t["ecart_pct"] or 0) > 0 else "en dessous")
            constat = (f"{_pluriel(len(svc), 'service')} du panier concerne{'nt' if len(svc) > 1 else ''} ce segment. « {cite(t)} » "
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
        # Reformulé le 2026-08-07 : « offre de conquête » relève du Commercial. Ce qui est
        # d'Innovation, c'est de METTRE EN SERVICE la solution d'acceptation — terminaux,
        # paiement en ligne, rapprochement automatique — que le réseau vendra ensuite.
        "titre": "Mettre en service une solution d'acceptation de paiement pour les commerçants",
        "constat": ((f"Le paiement mobile atteint {mob['valeur']} de pénétration ({mob['source']}) alors "
                     f"que la bancarisation reste à {banc['valeur']} ({banc['source']}) : les flux existent "
                     f"hors du bilan bancaire.") if mob and banc else
                    "Les repères de paiement mobile et de bancarisation ne sont pas tous disponibles."),
        "action": ("Déployer terminal de paiement, acceptation en ligne et rapprochement "
                   "automatique des encaissements, avec un raccordement au compte professionnel "
                   "sans ressaisie."),
        "cible": "Une solution d'acceptation en production, raccordée au compte professionnel.",
        "indicateur": "Nombre de commerçants équipés en acceptation.",
        "effort": "Moyen", "horizon": "12 mois",
        "contribution": _lien_objectif(socle, "la captation de flux aujourd'hui hors du système bancaire"),
    })

    if distance:
        t = distance[0]
        d.append({
            # Reformulé le 2026-08-07 : la version précédente demandait d'ALIGNER LA
            # TARIFICATION du canal numérique — une décision de Marketing, pas d'Innovation.
            # Ce qui relève d'ici, c'est la couverture fonctionnelle : quelles opérations un
            # client peut-il réellement faire sans venir en agence.
            "titre": "Porter à distance toutes les opérations qui n'exigent pas le guichet",
            "constat": (f"{_pluriel(len(distance), 'service')} de banque à distance figure"
                        f"{'nt' if len(distance) > 1 else ''} au catalogue comparable, dont "
                        f"« {cite(t)} » — la couverture reste étroite au regard de ce qui "
                        f"se traite encore en agence."),
            "action": ("Recenser les opérations réalisables à distance, combler les manques par "
                       "ordre de fréquence, et rendre le parcours numérique complet de bout en bout."),
            "cible": "Toute opération sans obligation de présence disponible sur le canal numérique.",
            "indicateur": "Part des opérations réalisées hors agence.",
            "effort": "Moyen", "horizon": "12 mois",
            "contribution": _lien_objectif(socle, "la baisse du coût de traitement par opération"),
        })
    else:
        d.append(_lacune("Cartographier l'offre de banque à distance",
                         "un service de banque à distance comparable au marché",
                         "Compléter les grilles sur la section « Services de banque à distance ».",
                         "Nombre de services à distance comparables."))

    # La revue de gamme de cartes a rejoint le MARKETING (_bloc_gamme_cartes) : positionner
    # un niveau de carte face à la concurrence est une décision d'offre et de prix, pas de
    # transformation digitale. L'Innovation traite ici l'automatisation des opérations qui
    # occupent le guichet.
    d.append(_bloc_automatisation(socle))

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
            "constat": (f"{_pluriel(len(cautions), 'service')} d'engagement figure{'nt' if len(cautions) > 1 else ''} au panier, dont « {cite(t)} » "
                        f"à {_fmt(t['sgci'])} contre {_fmt(t['median'])} de médiane."),
            "action": "Fixer les limites par contrepartie et par secteur avant toute campagne sur les cautions.",
            "cible": "Un cadre d'engagement écrit, opposable au réseau.",
            "indicateur": "Encours d'engagements par signature, et concentration par contrepartie.",
            "effort": "Moyen", "horizon": "6 mois",
            "contribution": _lien_objectif(socle, "des commissions d'engagement prises sous contrôle"),
        })
    else:
        # PAS DE REPLI « DONNÉE MANQUANTE » ICI (2026-08-07, consigne du directeur : « si on
        # n'a pas de données on laisse ; le but est d'utiliser ce qui existe pour orienter plus
        # finement les décisions »). Réclamer une donnée absente occupe une carte sur vingt
        # sans rien apporter au comité. On se rabat donc sur un risque MESURÉ dans les données
        # dont on dispose : la cohérence de la grille tarifaire publiée.
        #
        # L'enjeu n'est pas cosmétique. L'instruction BCEAO n°2011-01 impose aux établissements
        # de publier leurs conditions et de les afficher à la clientèle. Une ligne publiée dont
        # la valeur est incohérente est une exposition réglementaire, et c'est la Direction des
        # Risques qui en répond.
        d.append(_coherence_grille(socle))

    if impayes:
        t = impayes[0]
        d.append({
            "titre": "Vérifier que la tarification des incidents reste dissuasive sans être punitive",
            "constat": (f"« {cite(t)} » est facturé {_fmt(t['sgci'])} contre {_fmt(t['median'])} de "
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
        # SIGNAL EXTERNE — un par directive, tous distincts tant que la veille en fournit
        # assez. Sans rotation, les quatre cartes d'une direction citeraient le même fait et
        # donneraient l'impression d'un seul argument répété quatre fois.
        signaux = signaux_direction(socle, nom)
        # Les indicateurs arrivent en premier dans la file : les servir dans l'ordre donnait
        # dix-neuf indicateurs et un seul événement sur vingt cartes. Or les deux ne disent pas
        # la même chose — un indicateur décrit un ÉTAT du marché, un événement dit ce qui vient
        # de BOUGER, et c'est lui qui justifie d'agir maintenant plutôt que dans six mois. On
        # réserve donc la dernière carte de chaque direction à un événement quand la veille en
        # a relevé un dans son champ.
        indics = [s for s in signaux if s.get("nature") == "indicateur"]
        evts = [s for s in signaux if s.get("nature") != "indicateur"]
        file = list(indics)
        if evts and len(file) >= PAR_DIRECTION:
            file[PAR_DIRECTION - 1] = evts[0]
        file += [s for s in evts if s not in file]
        # TERRAIN D'APPLICATION (2026-08-07, correction du directeur : « tu fais pas deux
        # trucs scindés comme cela »). Les dossiers sectoriels formaient une section séparée,
        # sous les directives : le lecteur devait faire lui-même le rapprochement entre
        # « augmenter la part des commissions » et « la campagne cacao ouvre le 1er septembre ».
        #
        # Le secteur entre donc DANS la directive, avec son apport chiffré et les concurrents
        # déjà installés. Une directive dit désormais quoi faire, sur quel terrain, et ce que
        # ce terrain peut rapporter — au lieu de renvoyer à une carte plus bas.
        terrains = [s for s in (socle.get("secteurs") or [])
                    if nom in (s.get("directions_imposees") or []) or s.get("direction") == nom]
        terrains.sort(key=lambda s: -(s.get("opportunite") or 0))
        pris = set()
        for i, x in enumerate(lot, 1):
            x["direction"], x["rang"] = nom, i
            if file:
                x["signal"] = file[(i - 1) % len(file)]
            s = _terrain_pertinent(x, terrains, pris) if terrains else None
            if s:
                pris.add(s.get("cle"))
                bc = s.get("business_case") or {}
                x["terrain"] = {
                    "cle": s.get("cle"), "nom": s.get("nom"), "cibles": s.get("cibles"),
                    "segment": s.get("segment"), "opportunite": s.get("opportunite"),
                    "priorite": s.get("priorite"), "delai": s.get("delai_libelle"),
                    "commissions_min": bc.get("commissions_min_fcfa"),
                    "commissions_max": bc.get("commissions_max_fcfa"),
                    "clients_min": bc.get("clients_min"), "clients_max": bc.get("clients_max"),
                    "concurrents": [c.get("banque") for c in (s.get("concurrence") or [])][:4],
                    # Vrai lien de contenu, ou simple recommandation de terrain à privilégier ?
                    # Le rendu ne dit pas la même chose dans les deux cas.
                    "recommande": bool(s.get("_recommande")),
                }
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
            # Le pied de page annonçait « segment Particuliers », ce qui était exact mais
            # décrivait une limite, pas un choix : 55 services Entreprises comparables
            # n'entraient dans aucun raisonnement. Le panier couvre désormais les deux, et
            # on liste ce qui a réellement été mobilisé plutôt qu'un segment unique.
            "segments": sorted({s.get("segment") for s in socle["panier"] if s.get("segment")}),
            "segment_dossiers": segment,
            "n_services_comparables": len(socle["panier"]),
            "n_par_segment": {
                seg: sum(1 for s in socle["panier"] if s.get("segment") == seg)
                for seg in sorted({s.get("segment") for s in socle["panier"] if s.get("segment")})
            },
            "n_banques": socle["n_banques"],
            "note": ("Directives composées à partir de l'ensemble des données chargées ; la période "
                     "de référence est la plus récente disponible en base et se déplace d'elle-même "
                     "à chaque ingestion."),
        },
    }
