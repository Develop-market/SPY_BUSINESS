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
import re
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
    # Doublons stricts écartés (2026-08-09). « Frais de dossier (Entreprises) » remontait trois
    # fois de la section « Opérations avec l'étranger » : deux lignes rigoureusement identiques
    # — même tarif SGCI, même médiane — plus une troisième à un tarif différent. Les deux
    # premières gonflaient le décompte de services comparables et la Direction Commerciale
    # citait le même service deux fois dans une liste de trois. On ne garde qu'un exemplaire
    # de chaque quadruplet identique ; la ligne au tarif distinct, elle, est conservée, car
    # rien ne permet d'affirmer que c'est la même prestation.
    vus, uniques = set(), []
    for s in out:
        cle = (s["libelle"], s["segment"], s["sgci"], s["median"])
        if cle not in vus:
            vus.add(cle)
            uniques.append(s)
    return uniques


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
    """Services FACTURÉS nettement sous la médiane du marché.

    LES GRATUITÉS SONT EXCLUES (correction du 2026-08-09). Un service gratuit ressort
    mécaniquement à −100 %, si bien qu'il occupait les trois premières places : la Direction
    Commerciale recevait comme « arguments prix déjà gagnants » trois lignes à −100 %,
    c'est-à-dire trois gratuités — que la directive SUIVANTE traite déjà. La carte disait donc
    deux fois la même chose, et « facturé 100 % sous la médiane » est une manière obscure de
    dire « gratuit ». Un argument de prix suppose un prix : on exige un tarif strictement
    positif, ce qui fait remonter les vrais écarts commerciaux (attestation bancaire à
    10 000 F contre 43 000 F de médiane, virement CONNECT à 1 000 F contre 3 300 F).
    """
    cand = [s for s in panier if s["ecart_pct"] is not None
            and s["ecart_pct"] <= seuil and (s.get("sgci") or 0) > 0]
    return sorted(cand, key=lambda s: s["ecart_pct"])[:n]


def _gratuits_distinctifs(panier, n=3):
    """Gratuits chez SGCI et facturés par au moins la moitié des concurrents.

    TRI CORRIGÉ le 2026-08-09. Le classement se faisait par médiane décroissante : il
    remontait donc le service le plus CHER, qui est aussi le plus rare. En tête arrivait
    « reproduction de clé » — une clé de COFFRE, facturée 250 000 F par la SIB mais relevée
    chez deux concurrents seulement — et la carte invitait le réseau à en faire un argument
    d'entrée en relation. Personne n'ouvre un compte pour une clé de coffre.
    Ce qui fait un argument, ce n'est pas le montant : c'est que le service soit COURANT et
    facturé par le plus grand nombre. On classe donc par nombre de concurrents qui le
    facturent, la médiane ne départageant qu'à égalité, et on exige la moitié du marché.
    On déduplique aussi par libellé : le même service figurant dans les deux grilles, la liste
    d'automatisation affichait « Reproduction de clé, Reproduction de clé, Frais dossier ».
    """
    seuil = max(2, (len(db.BANKS) - 1) // 2)
    vus, cand = set(), []
    for s in sorted(panier, key=lambda s: (-(s.get("n_conc") or 0), -(s["median"] or 0))):
        if s["sgci"] != 0 or not s["median"] or s["median"] <= 0:
            continue
        if (s.get("n_conc") or 0) < seuil or s["libelle"] in vus:
            continue
        vus.add(s["libelle"])
        cand.append(s)
    return cand[:n]


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
    # Le rang de compétitivité prix est LE problème que cette carte traite. Sans lui, « trois
    # tarifs s'écartent de la médiane » est une observation ; avec lui, c'est la cause d'un
    # classement. On compte aussi les duels perdus : chacun est un service sur lequel le client
    # a une raison chiffrée de préférer un concurrent.
    comp = socle.get("competitivite") or {}
    sg = comp.get("sgci") or {}
    rang, n_cl = comp.get("rang_sgci"), comp.get("n_classees")
    wr, wins, duels = sg.get("winrate"), sg.get("wins"), sg.get("n")
    tete = (comp.get("classement") or [{}])[0]
    perdus = (duels - wins) if (duels and wins is not None) else None
    wr_tete = tete.get("winrate")
    ref = f"{_fr(f'{wr_tete:.1f}')} % pour {tete.get('banque')}" if wr_tete else ""
    enjeu = _enjeu(rang=rang, sur=n_cl,
                   valeur=(f"{_fr(f'{wr:.1f}')} % de duels prix gagnés" if wr is not None else ""),
                   reference=ref)
    situation = (f"SGCI se classe {rang}ᵉ sur {n_cl} en compétitivité prix : elle perd {perdus} "
                 f"des {duels} duels où le client peut comparer. "
                 if (rang and perdus) else "")

    if not chers:
        return {
            "titre": "Tenir le niveau des tarifs sous surveillance",
            "enjeu": enjeu,
            "constat": (situation + f"Sur {len(p)} services réellement comparables, aucun ne "
                        f"dépasse nettement la médiane du marché."),
            "action": "Maintenir la revue à chaque parution de grille concurrente.",
            "cible": "Aucun tarif ne s'éloigne de la médiane sans décision explicite.",
            "indicateur": "Nombre de tarifs au-dessus de la médiane, et écart moyen.",
            "effort": "Faible", "horizon": "6 mois",
            "contribution": _contribution(
                socle, nature="defense",
                texte="un positionnement prix que rien ne dégrade aujourd'hui"),
        }
    t = chers[0]
    liste = ", ".join(f"{cite(x)} (+{x['ecart_pct']:.0f} %)" for x in chers)
    return {
        "titre": f"Réexaminer les {len(chers)} tarifs les plus éloignés du marché",
        "enjeu": enjeu,
        "constat": (situation + f"Sur {len(p)} services réellement comparables, « {cite(t)} » est "
                    f"facturé {_fmt(t['sgci'])} contre une médiane de {_fmt(t['median'])} chez "
                    f"{t['n_conc']} concurrents, soit +{t['ecart_pct']:.0f} %."),
        "action": (f"Statuer sur : {liste}. Pour chacun — aligner, justifier par un service "
                   f"associé, ou maintenir en assumant l'écart par écrit."),
        "cible": (f"Aucun tarif à plus du double de la médiane sans justification écrite, et un "
                  f"rang de compétitivité prix ramené dans la première moitié du marché."),
        "indicateur": "Nombre de tarifs au-dessus de la médiane, et rang de compétitivité prix.",
        "effort": "Faible", "horizon": "3 mois",
        "contribution": _contribution(
            socle, nature="defense",
            texte=(f"les volumes des services les plus exposés à la comparaison ; ces écarts "
                   f"n'apportent aucun revenu supplémentaire tant qu'ils font perdre le duel")),
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
            "contribution": _contribution(socle, texte="les commissions de monétique"),
        }
    t = monetique[0]
    # La monétique est nommément l'un des trois relais cités par la directive des commissions.
    # Le rappeler ici n'est pas une redite : c'est ce qui rattache une décision d'offre au seul
    # écart du dossier qui pèse l'ordre de grandeur de l'objectif.
    eco = socle.get("eco") or {}
    pts = None
    if eco.get("meilleur_ratio") and eco.get("part_commissions_pnb"):
        pts = round(eco["meilleur_ratio"] - eco["part_commissions_pnb"], 1)
    return {
        "titre": "Positionner la gamme de cartes face au marché",
        "enjeu": _enjeu(valeur=f"{len(monetique)} niveaux de carte comparables au marché",
                        reference=(f"écart le plus marqué {t['ecart_pct']:+.0f} % sur "
                                   f"« {t['libelle']} »"),
                        nature="retard" if (t["ecart_pct"] or 0) > 0 else "avance"),
        "constat": (f"{_pluriel(len(monetique), 'service')} de monétique "
                    f"{'sont comparables' if len(monetique) > 1 else 'est comparable'}, dont "
                    f"« {cite(t)} » à {_fmt(t['sgci'])} contre {_fmt(t['median'])} de médiane "
                    f"({t['ecart_pct']:+.0f} %)."
                    + (f" La monétique est l'un des trois relais désignés pour combler les "
                       f"{_fr(f'{pts:.1f}')} points de commissions qui séparent SGCI de "
                       f"{eco.get('meilleur_ratio_banque')}." if pts else "")),
        "action": ("Positionner chaque niveau de carte face à l'offre concurrente équivalente, "
                   "du basique au haut de gamme, et rattacher un service à chaque palier."),
        "cible": "Une gamme lisible, chaque niveau justifié par un service associé.",
        "indicateur": "Nombre de cartes actives par niveau de gamme, et commissions de monétique.",
        "effort": "Moyen", "horizon": "12 mois",
        "contribution": _contribution(
            socle, nature="condition",
            texte=("elle rend exécutable le relais monétique de la directive sur les commissions ; "
                   "une gamme qu'on ne sait pas positionner ne se vend pas")),
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
        "enjeu": _enjeu(valeur=(f"{len(gratuits)} services gratuits mais coûteux à traiter"
                                if gratuits else ""),
                        reference="leur coût de guichet est intégralement supporté par la banque",
                        nature="retard"),
        "constat": constat, "action": action,
        "cible": "Chaque opération répétitive disponible sans passage en agence.",
        "indicateur": "Part des opérations traitées sans intervention humaine.",
        "effort": "Élevé", "horizon": "18 mois",
        "contribution": _contribution(
            socle, nature="defense",
            texte=("le coefficient d'exploitation, meilleur du marché : c'est lui que la montée "
                   "en volume dégradera d'abord si le traitement reste manuel")),
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
            "contribution": _contribution(
                socle, nature="condition",
                texte=("la maîtrise des charges libère du résultat sans vendre un franc de plus, "
                       "mais elle ne se pilote pas tant que le repère du marché manque")),
        }

    sgci = float(sgci)
    autres.sort(key=lambda x: x[1])
    meilleur, val_meilleur, an_meilleur = autres[0]
    rang = 1 + sum(1 for _, v, _ in autres if v < sgci)
    n = len(autres) + 1
    ecart = round(sgci - val_meilleur, 1)
    devant = rang == 1

    # Un point de coefficient vaut un point de PNB en charges : c'est ce qui rend la carte
    # comparable aux autres, où tout est exprimé en milliards.
    pnb_mds = (socle.get("eco") or {}).get("pnb_m") or 0
    point = pnb_mds / 1000 / 100          # millions -> milliards, puis 1 %

    if devant:
        constat = (f"SGCI affiche le meilleur coefficient d'exploitation du marché : {sgci:.1f} % "
                   f"en {an_sgci}, devant {meilleur} à {val_meilleur:.1f} % ({an_meilleur}), "
                   f"sur {n} banques comparées.")
        action = ("Tenir l'avance : chaque point gagné sur le coefficient tombe directement au "
                  "résultat, sans dépendre de la conquête commerciale.")
        cible = "Rester sous le meilleur coefficient du marché à chaque arrêté."
        enjeu = _enjeu(rang=1, sur=n, valeur=f"coefficient d'exploitation {_fr(f'{sgci:.1f}')} %",
                       # L'accord se fait ici : « 1,4 point(s) » montre la couture du gabarit
                       # dans une note destinée à un comité de direction.
                       reference=(f"{_fr(f'{abs(ecart):.1f}')} "
                                  f"{'point' if abs(ecart) < 2 else 'points'} devant {meilleur}"),
                       nature="avance")
        contribution = _contribution(
            socle, nature="defense",
            texte=(f"une structure de charges déjà la meilleure des {n} banques ; chaque point "
                   f"de coefficient représente {_fr(f'{point:.1f}')} Mds FCFA de charges"))
    else:
        constat = (f"Le coefficient d'exploitation de SGCI s'établit à {sgci:.1f} % en {an_sgci}, "
                   f"au {rang}ᵉ rang sur {n} banques ; {meilleur} tient {val_meilleur:.1f} % "
                   f"({an_meilleur}), soit {ecart:.1f} points de mieux.")
        action = ("Identifier les postes de charges qui expliquent l'écart et fixer une "
                  "trajectoire de retour au niveau du mieux placé.")
        cible = f"Refermer les {ecart:.1f} points d'écart avec {meilleur}."
        enjeu = _enjeu(rang=rang, sur=n, valeur=f"coefficient d'exploitation {_fr(f'{sgci:.1f}')} %",
                       reference=f"{_fr(f'{ecart:.1f}')} points derrière {meilleur}")
        contribution = _contribution(socle, mds=ecart * point)

    return {
        "titre": "Ramener le coefficient d'exploitation au niveau du mieux placé"
                 if not devant else "Défendre le meilleur coefficient d'exploitation du marché",
        "enjeu": enjeu,
        "constat": constat, "action": action, "cible": cible,
        "indicateur": "Charges générales ÷ PNB, comparé au meilleur du marché à chaque arrêté.",
        "effort": "Élevé", "horizon": "24 mois",
        "contribution": contribution,
        "contribution_mds": None if devant else ecart * point,
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

    # Ce que pèse réellement la marge d'intérêt : tout ce que le PNB n'est pas commission.
    # Le chiffre est le plus lourd du dossier, et c'est précisément ce que la carte doit dire —
    # sans lui, « piloter le coût des ressources » reste un vœu de comité.
    eco = socle.get("eco") or {}
    pnb, com = (eco.get("pnb_m") or 0) / 1000, (eco.get("commissions_m") or 0) / 1000
    marge = pnb - com
    if marge > 0:
        part = 100 * marge / pnb if pnb else 0
        # L'HYPOTHÈSE EST DITE (2026-08-09). Le montant venait d'un « 1 % de la marge » que rien
        # dans le texte n'annonçait : le lecteur voyait un chiffre sans savoir d'où il sortait,
        # ce qui est exactement le reproche fait aux anciennes cartes. Un pour cent de marge
        # gagné sur le coût des ressources est une hypothèse modeste et vérifiable — on l'écrit.
        mds_ressources = marge * 0.01
        contribution = _contribution(socle, mds=mds_ressources, nature="revenu") + (
            f" Hypothèse : 1 % gagné sur une marge d'intérêt de {_fr(f'{marge:.1f}')} Mds, "
            f"soit {_fr(f'{part:.0f}')} % du PNB. C'est la plus lourde masse du dossier — devant "
            f"toute la conquête sectorielle documentée.")
        enjeu = _enjeu(valeur=f"marge d'intérêt {_fr(f'{marge:.1f}')} Mds FCFA",
                       reference=f"{_fr(f'{part:.0f}')} % du PNB, contre "
                                 f"{_fr(f'{100 - part:.0f}')} % pour les commissions",
                       nature="masse")
    else:
        contribution = _contribution(socle, texte="la marge d'intérêt, la plus lourde composante du PNB")
        enjeu, mds_ressources = None, None

    return {
        "titre": "Piloter le coût des ressources et la marge d'intermédiation",
        "enjeu": enjeu,
        "constat": constat, "action": action,
        "cible": "Un coût moyen des ressources connu et arbitré à chaque comité de trésorerie.",
        "indicateur": "Coût moyen des ressources, et marge d'intermédiation nette.",
        "effort": "Moyen", "horizon": "12 mois",
        "contribution": contribution,
        "contribution_mds": mds_ressources if marge > 0 else None,
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
        "enjeu": _enjeu(valeur=(f"{_pluriel(n, 'ligne')} publiées en anomalie sur {total}" if total else ""),
                        reference=("instruction BCEAO n°2011-01 : obligation de publier et "
                                   "d'afficher les conditions"),
                        nature="alerte" if n else "avance"),
        "constat": constat,
        "action": action,
        "cible": "Zéro ligne publiée dont la valeur est démentie par la brochure.",
        "indicateur": "Nombre de lignes en anomalie, mesuré à chaque ingestion.",
        "effort": "Faible" if n < 50 else "Moyen",
        "horizon": "3 mois",
        "contribution": _contribution(
            socle, nature="condition",
            texte=("une valeur publiée fausse est une exposition réglementaire au titre de "
                   "l'instruction BCEAO n°2011-01, et elle fausse aussi les arbitrages "
                   "tarifaires décidés sur cette base")),
    }


def _fr(texte):
    """Décimales à la française : « 37.2 % » devient « 37,2 % ».

    Les nombres viennent de calculs Python, qui écrivent le point. Sur une note destinée à un
    comité ivoirien, un point décimal se remarque immédiatement et fait douter du reste. La
    conversion ne touche QUE les motifs chiffre-point-chiffre : aucune date, aucune URL et
    aucun numéro de version n'apparaît dans ces champs.
    """
    import re as _r
    return _r.sub(r"(\d)\.(\d)", r"\1,\2", str(texte or ""))


# Premier pas selon la NATURE de la directive, reconnue à ses mots. On ne demande pas un
# résultat en trente jours — on demande d'avoir commencé, par un geste vérifiable qui ne
# dépend de personne d'autre que la direction concernée.
#
# L'ordre compte : le premier motif qui correspond gagne, du plus spécifique au plus général.
_PREMIERS_PAS = [
    # ORDRE DU PLUS SPECIFIQUE AU PLUS GENERAL, et motifs faits de plusieurs mots quand le mot
    # seul est ambigu. Trois faux amis ont ete corriges ici le 2026-08-07 :
    #   « Bonne gamme » (un segment de clientele) attrapait la regle de la gamme de CARTES ;
    #   « moyenne du secteur » attrapait celle de la conquete SECTORIELLE ;
    #   « tarification des incidents » attrapait celle des ecarts TARIFAIRES.
    # C'est la meme lecon que le mot « marche », qui rattachait le coefficient d'exploitation
    # aux cautions de marche du BTP : un mot isole ne porte pas son sens.
    (("coût du risque", "sinistralité", "créances", "portefeuille dégradé"),
     "Isoler les dossiers dégradés du trimestre et en analyser l'origine."),
    (("engagement par signature", "engagements par signature", "caution", "garantie"),
     "Recenser les engagements par signature en cours et leur couverture."),
    (("incident", "impayé", "dissuasif"),
     "Rapprocher le tarif de l'incident de son coût réel de traitement."),
    (("déclaration", "espèces", "conformité", "seuil"),
     "Vérifier que le seuil en vigueur est bien celui appliqué par les agences."),
    (("cohérence", "grille publiée", "grille tarifaire publiée"),
     "Reprendre les lignes signalées à la source et corriger la base."),
    (("adresser le segment", "segment grand public", "segment bonne gamme",
      "segment patrimoniaux", "segments professionnels"),
     "Extraire du fichier client la population de ce segment et son équipement actuel."),
    (("gamme de carte", "gamme de cartes", "monétique"),
     "Mettre à plat la gamme actuelle en face de celle des concurrents, palier par palier."),
    (("tarifs les plus éloignés", "réexaminer les", "médiane du marché"),
     "Réunir le comité tarifaire et statuer, service par service, sur les écarts listés."),
    (("coefficient d'exploitation", "charges générales"),
     "Isoler les trois postes de charges qui pèsent le plus, et leur évolution sur douze mois."),
    (("part des commissions", "revenus de commissions"),
     "Décomposer les commissions par ligne de service et repérer les trois plus faibles."),
    (("coût des ressources", "intermédiation", "refinancement"),
     "Établir le coût moyen des ressources collectées sur le dernier trimestre."),
    (("boucler le plan", "part non couverte", "écart à combler"),
     "Convoquer un comité de bouclage et affecter chaque tranche de l'écart à un responsable."),
    (("ouvrir la conquête", "conquête sur le secteur"),
     "Constituer la liste nominative des prospects du secteur et l'affecter au réseau."),
    (("armer le réseau", "argument", "gratuité"),
     "Rédiger l'argumentaire d'une page et le diffuser aux chargés de clientèle."),
    (("équiper la clientèle", "socle de services", "services de flux"),
     "Recenser les clients professionnels non équipés du socle et les répartir par agence."),
    (("acceptation de paiement", "solution d'acceptation", "terminal"),
     "Choisir la solution d'acceptation et lancer un pilote sur une dizaine de commerçants."),
    (("porter à distance", "banque à distance", "canal numérique"),
     "Lister les opérations encore impossibles à distance et les classer par fréquence."),
    (("automatiser", "occupent le guichet"),
     "Chronométrer les opérations les plus répétitives en agence pendant une semaine."),
    (("entrée en relation", "délai d'ouverture"),
     "Mesurer le délai réel d'ouverture d'un compte, de la demande à la première opération."),
]


def _premier_pas_depuis(directive):
    """Premier geste à trente jours, déduit de la nature de la directive.

    LE TITRE D'ABORD, l'action seulement ensuite. Chercher dans les deux à la fois donnait des
    contresens : « piloter le coût des ressources » recevait « réunir le comité tarifaire »
    parce que son action mentionne la tarification du crédit, et « porter la part des
    commissions » recevait « mettre à plat la gamme » parce qu'elle cite la monétique parmi
    les leviers. Le titre dit ce que la directive EST ; l'action ne fait que la détailler, et
    elle cite au passage des termes qui appartiennent à d'autres sujets.
    """
    titre = (directive.get("titre") or "").lower()
    for motifs, pas in _PREMIERS_PAS:
        if any(m in titre for m in motifs):
            return pas
    action = (directive.get("action") or "").lower()
    for motifs, pas in _PREMIERS_PAS:
        if any(m in action for m in motifs):
            return pas
    # Repli honnête : on ne fabrique pas un geste qui n'aurait rien à voir avec la directive.
    return "Désigner le responsable de cette directive et fixer la date du premier point."


def _mois(horizon):
    """Nombre de mois porté par un horizon (« 3 mois », « 24 mois »), pour pouvoir trier.

    Un horizon illisible est renvoyé loin derrière plutôt qu'en tête : une directive dont on
    ne sait pas quand elle s'exécute n'a rien à faire en première position d'une note
    d'arbitrage. Mieux vaut la voir en fin de liste et s'en étonner.
    """
    m = re.search(r"(\d+)", str(horizon or ""))
    return int(m.group(1)) if m else 999


def _mds(fcfa):
    """Un montant en francs, rendu en milliards — l'unité dans laquelle l'objectif est fixé."""
    return _fr(f"{(fcfa or 0) / 1e9:,.1f}".replace(",", " ")) + " Mds FCFA"


def _contribution(socle, mds=None, nature="revenu", texte=""):
    """Ce que la directive apporte à l'objectif — CHIFFRÉ, et rapporté à l'écart à combler.

    RÉÉCRIT le 2026-08-09, sur la critique du directeur : « je ne vois en rien le lien avec la
    stratégie et les problèmes de la SGCI ». La version précédente rendait une étiquette —
    « levier vers l'objectif : la mobilisation du segment GP », « la maîtrise des charges » —
    qui nommait une catégorie sans jamais dire combien. Vingt cartes portaient ainsi vingt
    formules interchangeables, dont aucune ne permettait de savoir si le plan tenait.

    Trois formes, et trois seulement, car toutes les directives ne rapportent pas de l'argent
    et prétendre le contraire serait pire que se taire :

      revenu     un montant annuel, converti en part de l'écart de 27,7 Mds. C'est le seul cas
                 où l'on additionne : la somme des cartes « revenu » doit approcher l'objectif,
                 et si elle ne l'approche pas, le plan le dit lui-même.
      condition  la directive ne produit rien mais sans elle une autre ne tient pas. On nomme
                 laquelle, sinon « condition » n'est qu'un mot poli pour « hors sujet ».
      defense    elle protège un acquis déjà au bilan. On chiffre l'acquis, pas un gain.
    """
    obj = socle.get("objectif") or {}
    ecart = obj.get("ecart_a_combler")
    if nature == "condition":
        return f"Ne produit pas de PNB par elle-même : {texte}."
    if nature == "defense":
        return f"Défend l'acquis : {texte}."
    if mds is None:
        return f"Contribue à l'objectif par {texte}." if texte else \
            "Contribue au plan à trois ans de la stratégie globale."
    if not ecart:
        return f"Apport estimé : {_fr(f'{mds:.1f}')} Mds FCFA par an."
    part = 100 * mds / ecart
    # Un apport réel mais faible ne doit pas s'afficher « 0 % » : arrondi à l'entier, la
    # contribution de la conquête sectorielle — 0,066 Md sur 27,7 — devenait un zéro, et une
    # carte qui annonce zéro se lit comme une carte inutile. Elle ne l'est pas : elle est
    # petite, ce qui est une information différente et qu'il faut donner telle quelle.
    if 0 < part < 1:
        pc = "moins de 1 %"
    else:
        pc = _fr(f"{part:.0f}") + " %"
    montant = _fr(f"{mds:.2f}" if mds < 1 else f"{mds:.1f}")
    return (f"Apport estimé {montant} Mds FCFA par an, soit "
            f"{pc} des {_fr(str(ecart))} Mds à combler.")


def _annee_du_plan(horizon):
    """Année du plan à trois ans dans laquelle tombe une directive, d'après son horizon.

    AJOUTÉ LE 2026-08-10. La stratégie globale est une trajectoire à TROIS ANS, découpée en
    An 1 / An 2 / An 3 avec un thème et des actes chiffrés pour chacune. Les directives, elles,
    n'avaient aucun axe temporel : impossible de répondre à la première question d'un comité —
    « qu'est-ce qu'on fait cette année, et sommes-nous dans les temps ? ».

    ON NE RÉPARTIT RIEN À LA MAIN. Chaque directive porte déjà un horizon d'exécution réel,
    déduit de la nature de l'action (3 à 24 mois). Il suffit de le lire. Inventer une
    répartition annuelle aurait été exactement ce que ce module s'interdit partout ailleurs.

    Conséquence à assumer, et à AFFICHER plutôt qu'à masquer : l'horizon le plus lointain des
    directives est de 24 mois, donc l'An 3 ressort VIDE. Ce n'est pas un défaut de calcul,
    c'est un constat sur le plan — il ne va pas jusqu'au bout de la trajectoire qu'il sert.
    """
    mois = 12
    m = re.search(r"(\d+)", str(horizon or ""))
    if m:
        mois = int(m.group(1))
    if mois <= 12:
        return 1
    if mois <= 24:
        return 2
    return 3


def _enjeu(rang=None, sur=None, valeur="", reference="", nature="retard"):
    """L'écart MESURÉ qui justifie la directive — première ligne lue de la carte.

    Champ ajouté le 2026-08-09. Les cartes ouvraient sur un constat descriptif (« 3 services
    sont facturés sous la médiane ») sans jamais dire OÙ SE SITUE LA SGCI. Le lecteur voyait
    une observation, pas un problème, et n'avait aucune raison d'agir. On place donc en tête
    le rang de la banque et l'écart à celui qui fait mieux — ou, quand la SGCI est devant, on
    le dit aussi : une directive qui défend une avance n'est pas une directive au rabais, et
    la présenter comme un retard serait faux.
    """
    tete = ""
    if rang and sur:
        tete = f"SGCI {rang}ᵉ sur {sur}" if rang > 1 else f"SGCI 1ʳᵉ sur {sur}"
    morceaux = [m for m in (tete, valeur, reference) if m]
    txt = " · ".join(morceaux)
    return {"texte": txt, "nature": nature} if txt else None


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
        # LA CARTE PIVOT DU PLAN. L'écart de commissions à lui seul dépasse l'objectif à trois
        # ans : le dire explicitement change la nature de la note. Tant que la carte se
        # contentait d'annoncer « 12,5 points d'écart », le comité pouvait la lire comme une
        # observation parmi vingt. Rapportée aux 27,7 Mds, elle devient le sujet principal — et
        # les dix-neuf autres directives se lisent comme les moyens d'en obtenir une fraction.
        # On ne prétend pas pour autant combler la totalité de l'écart en trois ans : on chiffre
        # ce que vaudrait le quart du chemin, seule hypothèse que l'on assume.
        obj_ecart = (socle.get("objectif") or {}).get("ecart_a_combler") or 0
        gain_mds = gain / 1e9
        quart = gain_mds / 4
        couverture = (100 * gain_mds / obj_ecart) if obj_ecart else 0
        d.append({
            "titre": "Porter la part des commissions au niveau du mieux placé du marché",
            "enjeu": _enjeu(valeur=f"commissions {_fr(str(eco['part_commissions_pnb']))} % du PNB",
                            reference=(f"{_fr(f'{pts:.1f}')} points derrière "
                                       f"{eco['meilleur_ratio_banque']} "
                                       f"({_fr(str(eco['meilleur_ratio']))} %)")),
            "constat": (f"Les commissions pèsent {eco['part_commissions_pnb']} % du PNB de SGCI contre "
                        f"{eco['meilleur_ratio']} % chez {eco['meilleur_ratio_banque']}, le mieux placé "
                        f"des {socle['n_banques']} banques suivies. À PNB inchangé, ces {pts} points "
                        f"valent {_mds(gain)} par an — "
                        + (f"soit {_fr(f'{couverture:.0f}')} % de l'objectif à trois ans à eux seuls. "
                           f"Aucune autre directive du dossier n'approche cet ordre de grandeur."
                           if couverture >= 100 else
                           f"soit {_fr(f'{couverture:.0f}')} % de l'objectif à trois ans.")),
            "action": ("Combler l'écart par les revenus de service : monétique, opérations avec "
                       "l'étranger, engagements par signature."),
            "cible": (f"Reprendre le quart de l'écart en trois ans, soit {_fr(f'{pts / 4:.1f}')} points "
                      f"de PNB — hypothèse volontairement prudente, l'écart total valant {_mds(gain)}."),
            "indicateur": "Part des commissions dans le PNB, par trimestre.",
            "effort": "Élevé", "horizon": "24 mois",
            "contribution": _contribution(socle, mds=quart), "contribution_mds": quart,
        })
    else:
        d.append(_lacune("Mesurer la structure du PNB face au marché",
                         "la décomposition du PNB des banques concurrentes",
                         "Charger les états financiers détaillés des sept banques.",
                         "Part des commissions dans le PNB, par banque."))

    d.append(_bloc_cout_ressources(socle))

    if obj.get("aucun_ecart_concurrentiel"):
        # 2026-08-22 : depuis que la cible PNB est mesurée (moyenne des 3 meilleures banques du
        # panel), la SGCI la dépasse déjà — ecart_a_combler vaut 0, une valeur FALSY en Python
        # que l'ancien `if obj.get("ecart_a_combler")` confondait avec une donnée absente,
        # déclenchant à tort la directive de repli « donnée manquante ». Ce n'est pas un manque :
        # c'est le résultat. On le dit, sans reproduire un chiffre à zéro comme s'il fallait
        # « boucler un plan » sur un écart qui n'existe pas.
        d.append({
            "titre": "Consolider l'avance plutôt que rattraper un retard",
            "constat": (f"Le PNB de la SGCI ({_fr(str(obj.get('trajectoire_naturelle')))} "
                        f"{obj.get('unite','Mds')} FCFA en {obj.get('horizon_ans',3)} ans, "
                        f"trajectoire naturelle) dépasse déjà la cible du panel (moyenne des 3 "
                        f"meilleures banques concurrentes) : aucun écart concurrentiel à combler "
                        f"sur cet indicateur."),
            "action": ("Les directives sectorielles ci-dessous visent à amplifier l'avance, pas à "
                       "rattraper un retard."),
            "cible": "Maintenir le PNB au-dessus de la cible du panel à chaque arrêté.",
            "indicateur": "PNB de la SGCI vs moyenne des 3 meilleures banques du panel.",
            "effort": "Faible", "horizon": "3 mois",
            "contribution": _contribution(
                socle, nature="condition",
                texte="elle confirme que le socle du plan (le PNB) part d'une position déjà favorable"),
        })
    elif obj.get("ecart_a_combler"):
        couvert = sum((s.get("business_case") or {}).get("commissions_max_fcfa") or 0
                      for s in socle.get("secteurs", []))
        pct = round(100 * (couvert / 1e9) / obj["ecart_a_combler"], 1)
        d.append({
            "titre": "Boucler le plan : dire d'où viendra la part non couverte",
            "enjeu": _enjeu(valeur=f"{_fr(str(pct))} % de l'objectif couvert par des actions chiffrées",
                            reference=f"{_fr(f'{100 - pct:.1f}')} % encore sans source identifiée",
                            nature="alerte"),
            "constat": (f"Les secteurs suivis couvrent au mieux {_fmt(couvert)} de commissions par an, "
                        f"soit {pct} % des {obj['ecart_a_combler']} {obj.get('unite','Mds')} FCFA à combler. "
                        f"Le reste du chemin repose aujourd'hui sur la structure du PNB — c'est la "
                        f"directive sur les commissions qui le porte, pas la conquête sectorielle."),
            "action": ("Chiffrer explicitement le reste : tarification du portefeuille existant, "
                       "volumes, coût du risque."),
            "cible": "Un plan couvrant la totalité de l'écart, avec une source identifiée par tranche.",
            "indicateur": "Part de l'écart couverte par des actions chiffrées.",
            "effort": "Moyen", "horizon": "6 mois",
            "contribution": _contribution(
                socle, nature="condition",
                texte=("elle vérifie que la somme des dix-neuf autres directives atteint bien "
                       "l'objectif, et interdit d'annoncer un plan dont le chemin n'est pas chiffré")),
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
        # On dit la vérité sur l'ordre de grandeur. Le dossier sectoriel le mieux noté vaut
        # quelques dizaines de millions ; l'objectif est en milliards. Laisser croire que la
        # conquête sectorielle porte le plan serait le rendre invérifiable — et le comité s'en
        # apercevrait au premier arrêté. Ce que ce secteur apporte vraiment, c'est une méthode
        # démontrée sur un marché documenté, réplicable aux six autres.
        gain = (bc.get("commissions_max_fcfa") or 0) / 1e9
        d.append({
            "titre": f"Ouvrir la conquête sur le secteur le mieux noté : {s.get('nom','')}",
            "enjeu": _enjeu(valeur=f"note d'opportunité {s.get('opportunite')}/100",
                            reference=f"la plus élevée des {len(secteurs)} secteurs documentés",
                            nature="opportunite"),
            "constat": (f"Ce secteur obtient la note d'opportunité la plus élevée ({s.get('opportunite')}/100) "
                        f"parmi les {len(secteurs)} suivis. Cible : {s.get('cibles','')}."),
            "action": (f"Constituer un portefeuille de prospects sur {s.get('segment','')} et pousser : "
                       f"{', '.join((s.get('produits') or [])[:3])}."),
            "cible": (f"{bc.get('clients_min')} à {bc.get('clients_max')} nouveaux clients, soit "
                      f"+{_fmt(bc.get('commissions_min_fcfa'))} à +{_fmt(bc.get('commissions_max_fcfa'))} "
                      f"de commissions par an." if bc else "Cible à chiffrer une fois les volumes connus."),
            "indicateur": "Nombre de nouvelles entrées en relation sur le secteur.",
            "effort": "Moyen", "horizon": s.get("delai_libelle", "12 mois"),
            "contribution_mds": gain or None,
            "contribution": (_contribution(socle, mds=gain) +
                             " Ordre de grandeur modeste, et c'est un fait à retenir : la conquête "
                             "sectorielle prouve la méthode, elle ne porte pas le plan à elle seule."
                             ) if gain else _contribution(
                socle, texte="la conquête de nouveaux clients sur un marché documenté"),
        })
    else:
        d.append(_lacune("Documenter les secteurs de conquête",
                         "un secteur disposant de faits sourcés",
                         "Relancer la veille sectorielle pour alimenter les indicateurs.",
                         "Nombre de secteurs disposant d'au moins un fait daté."))

    # Le rang de compétitivité prix est la mesure la plus directe du problème commercial de la
    # SGCI : sur les services que le client peut comparer, combien de fois est-elle la moins
    # chère ? C'est ce rang, et non le nombre de services, qui donne son enjeu à la carte.
    comp = socle.get("competitivite") or {}
    sg = comp.get("sgci") or {}
    rang_prix, n_classees = comp.get("rang_sgci"), comp.get("n_classees")
    winrate, wins, duels = sg.get("winrate"), sg.get("wins"), sg.get("n")
    tete = (comp.get("classement") or [{}])[0]

    if competitifs:
        liste = ", ".join(f"« {cite(x)} » à {_fmt(x['sgci'])} contre {_fmt(x['median'])} "
                          f"de médiane ({x['ecart_pct']:.0f} %)" for x in competitifs)
        perdus = (duels - wins) if (duels and wins is not None) else None
        wr_tete = tete.get("winrate")
        ref_tete = f"{_fr(f'{wr_tete:.1f}')} % pour {tete.get('banque')}" if wr_tete else ""
        d.append({
            "titre": "Armer le réseau des arguments prix déjà gagnants",
            "enjeu": _enjeu(rang=rang_prix, sur=n_classees,
                            valeur=(f"{_fr(f'{winrate:.1f}')} % de duels prix gagnés"
                                    if winrate is not None else ""),
                            reference=ref_tete),
            "constat": ((f"Sur {duels} services réellement comparés, SGCI est la moins chère "
                         f"{wins} fois et se classe {rang_prix}ᵉ sur {n_classees}. "
                         if duels and rang_prix else "")
                        + f"Les écarts les plus favorables sont : {liste}. "
                        + ("L'avantage est acquis et déjà financé, mais rien ne garantit qu'il "
                           "soit dit au client.")),
            "action": "Fournir aux chargés de clientèle une fiche par service, avec le tarif SGCI et la médiane marché.",
            "cible": "Chaque chargé de clientèle dispose des trois arguments prix de son portefeuille.",
            "indicateur": "Taux d'équipement sur les services mis en avant.",
            "effort": "Faible", "horizon": "3 mois",
            "contribution": _contribution(
                socle, nature="condition",
                texte=(f"elle transforme un avantage déjà payé en argument de vente ; "
                       f"sans elle, les {len(competitifs)} écarts favorables restent invisibles du client"
                       + (f", alors que {perdus} des {duels} duels sont perdus par ailleurs"
                          if perdus else ""))),
        })
    else:
        d.append(_lacune("Identifier les arguments prix",
                         "un service facturé sous la médiane du marché",
                         "Élargir le panier comparable.",
                         "Nombre de services sous la médiane."))

    if gratuits:
        # LES TROIS SONT CITÉES, PAS SEULEMENT LA PLUS CHÈRE (2026-08-09). La carte ne retenait
        # que le montant le plus élevé et bâtissait tout son argumentaire dessus. Comme le tri
        # privilégiait le tarif, elle proposait au réseau de faire de la reproduction d'une clé
        # de COFFRE l'argument d'ouverture de compte. Un argument commercial se juge à la
        # fréquence d'usage, pas au prix affiché : on cite donc l'ensemble des gratuités que la
        # moitié du marché facture, et on laisse le réseau retenir celles qui parlent à ses
        # clients — c'est lui qui les connaît, pas la base de données.
        # On ne cumule PAS les médianes. Additionner le prix d'une clé de coffre et celui de
        # frais de dossier donnerait un « 72 000 FCFA cumulés » qui n'est le prix de rien : nul
        # client ne paie les trois, et le total ne mesure ni une économie ni un manque à gagner.
        # Ce qui compte est le nombre de concurrents qui facturent, déjà dans le libellé.
        liste = ", ".join(f"« {g['libelle']} » ({_fmt(g['median'])} de médiane chez "
                          f"{g['n_conc']} concurrents)" for g in gratuits)
        d.append({
            "titre": "Faire des gratuités un argument d'entrée en relation",
            "enjeu": _enjeu(valeur=f"{len(gratuits)} services gratuits chez SGCI",
                            reference=f"chacun facturé par au moins {gratuits[-1]['n_conc']} "
                                      f"concurrents sur {socle['n_banques'] - 1}",
                            nature="avance"),
            "constat": (f"{_pluriel(len(gratuits), 'service')} du panier "
                        f"{'sont gratuits' if len(gratuits) > 1 else 'est gratuit'} chez SGCI alors "
                        f"qu'au moins la moitié du marché les facture : {liste}."),
            "action": ("Intégrer ces gratuités au discours d'ouverture de compte et aux supports "
                       "d'agence, en commençant par celles que le réseau rencontre le plus souvent."),
            "cible": "Une mention systématique lors de l'entrée en relation.",
            "indicateur": "Nombre d'ouvertures de compte, et taux de citation en entretien.",
            "effort": "Faible", "horizon": "3 mois",
            "contribution": _contribution(
                socle, nature="condition",
                texte=("elle donne au réseau de quoi ouvrir une relation sans concession de prix ; "
                       "le gain se lit en nombre de clients, pas en commissions immédiates")),
        })
    else:
        d.append(_lacune("Recenser les gratuités distinctives",
                         "un service gratuit chez SGCI et facturé par la moitié du marché",
                         "Vérifier la complétude des grilles concurrentes chargées.",
                         "Nombre de gratuités distinctives."))

    # CONSTAT RECONSTRUIT (2026-08-09). L'ancienne version justifiait l'équipement des
    # professionnels par « 2 services du panier relèvent du périmètre professionnel, dont
    # "Frais de timbre pour versement d'espèces" à 100 FCFA ». Un timbre à cent francs
    # n'établit rien sur l'équipement d'un client professionnel : le constat et l'action ne
    # parlaient pas du même sujet, et une carte dont la prémisse ne soutient pas la conclusion
    # est pire qu'une carte absente. On la fonde donc sur ce que les données disent vraiment —
    # la commission moyenne par client, qui mesure exactement ce que l'équipement fait bouger.
    eco = socle.get("eco") or {}
    moy, clients = eco.get("commission_moyenne"), eco.get("clients")
    pro = [s for s in p if (s.get("segment") or "").lower().startswith("entrep")]
    if moy and clients:
        # Trois services supplémentaires par client professionnel, sur 5 % de la base : une
        # hypothèse basse, énoncée comme telle, plutôt qu'un chiffre décidé au doigt mouillé.
        vise = int(clients * 0.05)
        gain = vise * moy * 0.30 / 1e9
        constat = (f"Chaque client rapporte en moyenne {_fmt(moy)} de commissions par an, sur "
                   f"{_fr(f'{clients:,}'.replace(',', ' '))} clients. Le catalogue Entreprises "
                   f"compte {len(pro)} services comparables au marché : la matière existe pour "
                   f"élargir l'équipement, ce qui déplace directement cette moyenne.")
        mds_clipro = gain
        contribution = _contribution(socle, mds=gain) + (
            f" Hypothèse : {_fr(f'{vise:,}'.replace(',', ' '))} clients professionnels — 5 % de la "
            f"base — dont la commission moyenne progresse de 30 %.")
    else:
        constat = (f"Le catalogue Entreprises compte {len(pro)} services comparables au marché, "
                   f"mais la commission moyenne par client n'est pas disponible : l'apport de "
                   f"l'équipement ne peut pas encore être chiffré.")
        contribution, mds_clipro = _contribution(
            socle, texte="l'équipement des clients professionnels"), None
    d.append({
        "titre": "Équiper la clientèle professionnelle du socle de services de flux",
        "enjeu": _enjeu(valeur=(f"commission moyenne {_fmt(moy)} par client" if moy else ""),
                        reference=(f"sur {_fr(f'{clients:,}'.replace(',', ' '))} clients"
                                   if clients else ""),
                        nature="masse"),
        "constat": constat,
        "action": ("Proposer systématiquement compte professionnel, encaissement et acceptation "
                   "monétique à toute entreprise dont le chiffre d'affaires est inférieur à 750 millions."),
        "cible": "Un socle de trois services par client professionnel entrant.",
        "indicateur": "Nombre de services par client professionnel, et commission moyenne du segment.",
        "effort": "Moyen", "horizon": "12 mois",
        "contribution": contribution,
        "contribution_mds": mds_clipro,
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
        # Le sens de l'écart décide du levier, et donc de ce que la carte apporte : au-dessus de
        # la médiane, le segment est exposé et la directive DÉFEND des volumes ; en dessous, la
        # banque a un avantage financé qu'elle n'exploite pas encore.
        au_dessus = bool(svc) and (svc[0]["ecart_pct"] or 0) > 0
        d.append({
            "titre": f"Adresser le segment {seg['nom']} par les conditions de banque",
            "enjeu": _enjeu(
                valeur=(f"{_pluriel(len(svc), 'service')} tarifés sur le segment {seg['cle']}" if svc else
                        f"aucun tarif comparable sur le segment {seg['cle']}"),
                reference=(f"écart de {abs(svc[0]['ecart_pct']):.0f} % "
                           f"{'au-dessus' if au_dessus else 'en dessous'} du marché" if svc else ""),
                nature="retard" if au_dessus else "avance"),
            "constat": f"Segment défini par un {seg['critere']}. " + constat,
            "action": action,
            "cible": f"Un message par segment, adossé à un tarif publié — enjeu : {seg['enjeu']}.",
            "indicateur": f"Taux d'équipement et nombre d'entrées en relation sur le segment {seg['cle']}.",
            "effort": "Faible" if svc else "Moyen", "horizon": "6 mois",
            "contribution": _contribution(
                socle,
                nature="defense" if au_dessus else "condition",
                texte=(f"les volumes du segment {seg['cle']}, exposé sur un tarif supérieur au marché"
                       if au_dessus else
                       f"elle donne au segment {seg['cle']} un message adossé à un prix publié, "
                       f"seule façon de transformer un avantage tarifaire en entrées en relation")),
        })

    pro = services_du_segment(p, "CLIPRO", 2) + services_du_segment(p, "CLICOM", 2)
    d.append({
        "titre": "Adresser les deux segments professionnels par les services de flux",
        "enjeu": _enjeu(valeur=f"{_pluriel(len(pro), 'service')} de flux comparables sur les segments "
                               f"professionnels",
                        reference="encaissement et monétique pour CLIPRO, étranger et change "
                                  "pour CLICOM",
                        nature="opportunite"),
        "constat": ((f"CLIPRO (chiffre d'affaires jusqu'à 750 millions) et CLICOM (au-delà) sont "
                     f"couverts par {_pluriel(len(pro), 'service')} du panier, dont « {pro[0]['libelle']} » "
                     f"à {_fmt(pro[0]['sgci'])}.") if pro else
                    "Les services professionnels sont encore peu représentés dans le panier comparable."),
        "action": ("Deux discours distincts : encaissement et monétique pour CLIPRO ; opérations "
                   "avec l'étranger, change et engagements par signature pour CLICOM."),
        "cible": "Deux campagnes distinctes, chacune adossée à des tarifs publiés.",
        "indicateur": "Nombre de clients professionnels équipés, par segment.",
        "effort": "Moyen", "horizon": "12 mois",
        "contribution": _contribution(
            socle, nature="condition",
            texte=("elle porte au marché les deux relais de la directive sur les commissions — "
                   "monétique et opérations avec l'étranger — qui sans campagne restent au catalogue")),
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
        "enjeu": _enjeu(valeur=(f"paiement mobile {mob['valeur']}" if mob else ""),
                        reference=(f"bancarisation {banc['valeur']} : "
                                   f"les flux sont hors du bilan bancaire" if banc else ""),
                        nature="opportunite"),
        "cible": "Une solution d'acceptation en production, raccordée au compte professionnel.",
        "indicateur": "Nombre de commerçants équipés en acceptation.",
        "effort": "Moyen", "horizon": "12 mois",
        "contribution": _contribution(
            socle, nature="condition",
            texte=("elle fournit l'outil que la Direction Commerciale vendra aux commerçants ; "
                   "sans solution d'acceptation, la conquête des professionnels n'a rien à "
                   "raccorder au compte")),
    })

    if distance:
        t = distance[0]
        # « La couverture reste étroite » était une appréciation, pas une mesure : la carte
        # affirmait une insuffisance sans jamais la chiffrer (2026-08-09). On la remplace par ce
        # que les données établissent — la part du catalogue comparable accessible à distance —
        # en disant honnêtement ce que cette part mesure et ce qu'elle ne mesure pas : elle
        # compte des lignes de grille tarifaire, pas des opérations réelles.
        tous = len(p) or 1
        a_dist = len([s for s in p if "distance" in (s.get("section") or "").lower()])
        part = 100 * a_dist / tous
        d.append({
            # Reformulé le 2026-08-07 : la version précédente demandait d'ALIGNER LA
            # TARIFICATION du canal numérique — une décision de Marketing, pas d'Innovation.
            # Ce qui relève d'ici, c'est la couverture fonctionnelle : quelles opérations un
            # client peut-il réellement faire sans venir en agence.
            "titre": "Porter à distance toutes les opérations qui n'exigent pas le guichet",
            "enjeu": _enjeu(valeur=f"{_fr(f'{part:.0f}')} % du catalogue comparable accessible "
                                   f"à distance",
                            reference=f"{a_dist} services sur {tous}",
                            nature="retard"),
            "constat": (f"{a_dist} des {tous} services comparables relèvent de la banque à distance, "
                        f"soit {_fr(f'{part:.0f}')} % du catalogue — dont « {cite(t)} ». La mesure "
                        f"porte sur les lignes de la grille tarifaire, non sur les volumes traités : "
                        f"elle dit ce que le client PEUT faire à distance, pas ce qu'il fait."),
            "action": ("Recenser les opérations réalisables à distance, combler les manques par "
                       "ordre de fréquence, et rendre le parcours numérique complet de bout en bout."),
            "cible": "Toute opération sans obligation de présence disponible sur le canal numérique.",
            "indicateur": "Part des opérations réalisées hors agence.",
            "effort": "Moyen", "horizon": "12 mois",
            "contribution": _contribution(
                socle, nature="condition",
                texte=("elle allège le coût de traitement par opération, seul levier qui protège "
                       "le coefficient d'exploitation pendant que les volumes augmentent")),
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

    # Ce que vaut un client, la banque le sait : la commission moyenne est au dossier. On peut
    # donc chiffrer l'apport d'un élargissement de la base plutôt que d'invoquer « la conquête ».
    eco = socle.get("eco") or {}
    moy, clients = eco.get("commission_moyenne"), eco.get("clients")
    if moy and clients:
        vise = int(clients * 0.05)
        gain_ouv = vise * moy / 1e9
        mds_ouverture = gain_ouv
        contribution = _contribution(socle, mds=gain_ouv) + (
            f" Hypothèse : {_fr(f'{vise:,}'.replace(',', ' '))} clients de plus — 5 % de la base "
            f"actuelle — à {_fmt(moy)} de commissions par an chacun.")
    else:
        contribution, mds_ouverture = _contribution(
            socle, texte="l'élargissement de la base de clients"), None
    d.append({
        "titre": "Réduire le délai et le coût d'entrée en relation",
        "enjeu": _enjeu(valeur=(f"bancarisation {banc['valeur']}" if banc else ""),
                        reference=(f"base actuelle {_fr(f'{clients:,}'.replace(',', ' '))} clients"
                                   if clients else ""),
                        nature="opportunite"),
        "constat": ((f"La bancarisation plafonne à {banc['valeur']} ({banc['source']}) : le frein n'est "
                     f"pas la demande mais le parcours d'ouverture.") if banc else
                    "Le taux de bancarisation n'est pas disponible dans les données chargées."),
        "action": "Numériser l'entrée en relation de bout en bout, pièces justificatives comprises.",
        "cible": "Une ouverture de compte aboutie sans second passage en agence.",
        "indicateur": "Délai moyen d'entrée en relation, et taux d'abandon.",
        "effort": "Élevé", "horizon": "18 mois",
        "contribution": contribution,
        "contribution_mds": mds_ouverture,
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
    # ET ON EXCLUT LES ATTESTATIONS (2026-08-09). Le filtre par vocabulaire laissait passer
    # « Attestation de NON engagement » — un document qui certifie précisément que le client
    # n'a AUCUN engagement. La carte fondait donc l'encadrement des engagements par signature
    # sur la preuve de leur absence. C'est le même piège que « Frais d'envoi DHL » qu'on avait
    # écarté : un mot juste dans une phrase qui dit le contraire.
    _CONTRE = ("non engagement", "non-engagement", "sans engagement", "attestation")
    cautions = [s for s in services_de_section(p, "crédit", 20) + p
                if any(m in s["libelle"].lower() for m in _MOTS_ENGAGEMENT)
                and not any(c in s["libelle"].lower() for c in _CONTRE)]
    cautions = sorted({s["libelle"]: s for s in cautions}.values(),
                      key=lambda s: -abs(s["ecart_pct"] or 0))[:3]
    impayes = [s for s in p if any(m in s["libelle"].lower()
                                   for m in ("impay", "incident", "rejet", "opposition"))]
    d = []

    # Ce que la sinistralité du marché coûterait sur le PNB visé : c'est la seule façon de
    # rendre cette carte comparable aux dix-neuf autres, toutes exprimées en milliards.
    obj = socle.get("objectif") or {}
    cible_pnb = obj.get("cible_centrale")
    d.append({
        "titre": "Tenir le coût du risque sous la moyenne du secteur",
        # La valeur de veille porte déjà son propre libellé (« 7,7 % de créances dégradées ») :
        # la préfixer donnait « créances dégradées du secteur 7,7 % de créances dégradées ».
        # C'est le même piège qu'au constat, où il avait été traité — pas ici.
        "enjeu": _enjeu(valeur=(f"marché : {npl['valeur']}" if npl else ""),
                        reference="repère auquel se juge toute conquête nouvelle",
                        nature="alerte"),
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
        "contribution": _contribution(
            socle, nature="condition",
            texte=("un PNB gagné puis provisionné n'est pas gagné ; elle conditionne la totalité "
                   + (f"des {_fr(str(cible_pnb))} Mds visés à trois ans" if cible_pnb
                      else "de la trajectoire à trois ans"))),
    })

    d.append({
        "titre": "Sécuriser le dispositif de déclaration des opérations en espèces",
        "enjeu": _enjeu(valeur=(f"seuil de déclaration {_fmt(seuil['valeur'])}" if seuil else ""),
                        reference="obligation opposable, indépendante du volume conquis",
                        nature="alerte"),
        "constat": ((f"Le seuil de déclaration s'établit à {_fmt(seuil['valeur'])} ({seuil['source']}). "
                     f"La conquête des professionnels augmente mécaniquement les flux d'espèces.") if seuil else
                    "Le seuil de déclaration des opérations en espèces n'est pas disponible."),
        "action": "Contrôler que le dispositif absorbe la hausse de volume liée à la conquête des commerçants.",
        "cible": "Aucune opération au-dessus du seuil sans déclaration tracée.",
        "indicateur": "Nombre de déclarations transmises, et délai de transmission.",
        "effort": "Moyen", "horizon": "6 mois",
        "contribution": _contribution(
            socle, nature="condition",
            texte=("elle protège d'une sanction la conquête des professionnels, sur laquelle "
                   "reposent les relais monétique et encaissement")),
    })

    if cautions:
        t = cautions[0]
        d.append({
            "titre": "Encadrer les engagements par signature avant d'en faire un levier",
            "enjeu": _enjeu(valeur=f"{_pluriel(len(cautions), 'service')} d'engagement comparables",
                            reference=("troisième relais désigné pour combler l'écart de "
                                       "commissions"),
                            nature="opportunite"),
            "constat": (f"{_pluriel(len(cautions), 'service')} d'engagement figure{'nt' if len(cautions) > 1 else ''} au panier, dont « {cite(t)} » "
                        f"à {_fmt(t['sgci'])} contre {_fmt(t['median'])} de médiane. Les engagements "
                        f"par signature sont l'un des trois relais retenus pour les commissions : "
                        f"ils ne peuvent être poussés qu'une fois leurs limites écrites."),
            "action": "Fixer les limites par contrepartie et par secteur avant toute campagne sur les cautions.",
            "cible": "Un cadre d'engagement écrit, opposable au réseau.",
            "indicateur": "Encours d'engagements par signature, et concentration par contrepartie.",
            "effort": "Moyen", "horizon": "6 mois",
            "contribution": _contribution(
                socle, nature="condition",
                texte=("elle autorise le troisième relais de la directive sur les commissions ; "
                       "sans cadre écrit, la campagne cautions est un risque, pas un revenu")),
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
        eco = socle.get("eco") or {}
        clients, moy = eco.get("clients"), eco.get("commission_moyenne")
        # Ce que coûte l'attrition : un point de clients perdus, valorisé à la commission
        # moyenne. La carte cesse d'être un principe de prudence et devient un arbitrage chiffré.
        cout = (clients * 0.01 * moy / 1e9) if (clients and moy) else None
        d.append({
            "titre": "Vérifier que la tarification des incidents reste dissuasive sans être punitive",
            "enjeu": _enjeu(valeur=f"tarif d'incident {t['ecart_pct']:+.0f} % face au marché",
                            reference=(f"1 % de la base perdue vaut {_fr(f'{cout:.1f}')} Mds FCFA "
                                       f"de commissions" if cout else
                                       "arbitrage entre dissuasion et attrition"),
                            nature="alerte"),
            "constat": (f"« {cite(t)} » est facturé {_fmt(t['sgci'])} contre {_fmt(t['median'])} de "
                        f"médiane sur {t['n_conc']} concurrents ({t['ecart_pct']:+.0f} %)."
                        + (f" À {_fmt(moy)} de commissions par client et par an, perdre 1 % de la "
                           f"base coûte {_fr(f'{cout:.1f}')} Mds — davantage que ce que ce tarif "
                           f"peut rapporter." if cout else "")),
            "action": "Arbitrer entre effet dissuasif et risque d'attrition sur la clientèle fragile.",
            "cible": "Un tarif d'incident justifié par le coût réel de traitement.",
            "indicateur": "Nombre d'incidents, et taux de clôture après incident.",
            "effort": "Faible", "horizon": "6 mois",
            "contribution": _contribution(
                socle, nature="defense",
                texte=("la base de clients, dont dépend chaque franc de commission du plan"
                       + (f" ; 1 % de cette base vaut {_fr(f'{cout:.1f}')} Mds par an" if cout else ""))),
        })
    else:
        d.append({
            "titre": "Maintenir le ratio de solvabilité au-dessus de l'exigence",
            "enjeu": _enjeu(valeur=(f"solvabilité du secteur {solva['valeur']}" if solva else ""),
                            reference="plafond de fait à toute montée en volume",
                            nature="alerte"),
            "constat": ((f"La solvabilité du secteur s'établit à {solva['valeur']} ({solva['source']})."
                         ) if solva else "Le ratio de solvabilité du secteur n'est pas disponible."),
            "action": "Vérifier la compatibilité du plan de conquête avec les fonds propres disponibles.",
            "cible": "Un ratio maintenu au-dessus de l'exigence réglementaire sur tout l'horizon.",
            "indicateur": "Ratio de solvabilité, par trimestre.",
            "effort": "Moyen", "horizon": "12 mois",
            "contribution": _contribution(
                socle, nature="condition",
                texte="sans fonds propres disponibles, la trajectoire à trois ans est inatteignable"),
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
        # ── ORDRE DE LECTURE : LE PLUS PROCHE D'ABORD (2026-08-11) ──────────────────
        # Chaque direction présentait ses quatre directives dans l'ordre où le compositeur les
        # avait écrites. La Direction Financière ouvrait donc sur deux actions à VINGT-QUATRE
        # MOIS et refermait sur celle à six — exactement l'inverse de ce qu'un comité doit
        # lire. Ce qu'on attend d'une note d'arbitrage, c'est ce qu'on fait MAINTENANT ;
        # l'horizon lointain vient ensuite, quand la première année est engagée.
        #
        # On trie donc par horizon croissant. À horizon égal, on conserve l'ordre d'écriture,
        # qui porte la logique du compositeur (le constat fondateur avant ses déclinaisons) :
        # `sorted` est stable, et c'est précisément ce qu'on lui demande ici.
        lot.sort(key=lambda x: _mois(x.get("horizon")))
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

    # ── FINITION (2026-08-07) ────────────────────────────────────────────────────────
    # Deux passes appliquées à TOUTES les directives, pour ne pas dépendre de la vigilance
    # de chaque compositeur :
    #
    #   1. Décimales à la française. Les nombres viennent de f-strings Python, qui écrivent
    #      « 37.2 % ». Sur une note de comité, le point décimal saute aux yeux.
    #   2. Premier pas à trente jours. Une directive sans premier pas reste une intention :
    #      « ramener le coefficient au niveau du marché » ne dit pas ce qu'on fait lundi.
    #      Il se déduit de l'action, en la ramenant à son geste initial.
    for x in out:
        for champ in ("titre", "constat", "action", "cible", "indicateur", "contribution"):
            if x.get(champ):
                x[champ] = _fr(x[champ])
        if not x.get("premier_pas"):
            x["premier_pas"] = _premier_pas_depuis(x)
        x["annee_plan"] = _annee_du_plan(x.get("horizon"))

    # ── BILAN : LES VINGT DIRECTIVES ATTEIGNENT-ELLES L'OBJECTIF ? ───────────────────
    # Ajouté le 2026-08-09. Une note qui recommande vingt actions sans jamais les additionner
    # laisse au lecteur le soin de vérifier qu'elle tient debout — et personne ne le fait. On
    # somme donc les seules cartes qui annoncent un montant, et on affiche le reste À DÉCOUVERT.
    # Si le compte n'y est pas, la page le dit d'elle-même : c'est la fonction de la directive
    # de bouclage de la Direction Financière, et elle serait vaine si le total restait caché.
    obj = socle.get("objectif") or {}
    ecart = obj.get("ecart_a_combler")
    chiffrees = [x for x in out if x.get("contribution_mds")]
    somme = sum(x["contribution_mds"] for x in chiffrees)
    bilan = {
        "n_chiffrees": len(chiffrees),
        "n_total": len(out),
        "somme_mds": round(somme, 2),
        "ecart_mds": ecart,
        "couverture_pct": round(100 * somme / ecart, 1) if ecart else None,
        "reste_mds": round(ecart - somme, 2) if ecart else None,
        # UNITÉ DITE EXPLICITEMENT (2026-08-10). La stratégie globale chiffre certains de ses
        # actes en RÉSULTAT NET (« +5,0 Mds de RN »), cette page en PNB. Les deux grandeurs ne
        # s'additionnent pas, et rien ne le signalait : un lecteur pouvait de bonne foi
        # rapprocher un « +5 Mds » d'un « +8,6 Mds » qui ne parlent pas de la même chose.
        "unite": "PNB",
    }

    # ── PHASAGE SUR LA TRAJECTOIRE À TROIS ANS ───────────────────────────────────────
    # La stratégie globale est un plan An 1 / An 2 / An 3. Ces directives servent ce plan :
    # elles doivent donc se lire dans le même découpage, sinon on ne peut pas répondre à la
    # question que le comité pose en premier — « qu'est-ce qu'on fait cette année ? ».
    phasage = []
    for an in (1, 2, 3):
        lot = [x for x in out if x.get("annee_plan") == an]
        mds = sum(x.get("contribution_mds") or 0 for x in lot)
        phasage.append({
            "annee": an,
            "libelle": f"An {an}",
            "intervalle": {1: "0–12 mois", 2: "12–24 mois", 3: "24–36 mois"}[an],
            "n_directives": len(lot),
            "somme_mds": round(mds, 2),
            "part_pct": round(100 * mds / ecart, 1) if ecart else None,
            "directions": sorted({x["direction"] for x in lot}),
        })
    bilan["phasage"] = phasage
    # Ce que le phasage révèle et qu'il ne faut PAS masquer : l'horizon le plus lointain des
    # directives est de 24 mois. La troisième année du plan ne reçoit donc aucune directive.
    # C'est un constat sur le plan lui-même — il ne va pas jusqu'au bout de la trajectoire
    # qu'il sert — et le comité doit le voir plutôt qu'un tableau qui l'escamote.
    bilan["annees_sans_directive"] = [p["annee"] for p in phasage if not p["n_directives"]]
    return {
        "directives": out,
        "directions": DIRECTIONS,
        "par_direction": PAR_DIRECTION,
        "objectif_global": obj,
        "bilan": bilan,
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
