"""
strategie_operationnelle.py — Veille stratégique augmentée : opportunités de marché
====================================================================================
RÉÉCRIT INTÉGRALEMENT le 2026-07-30 après un rejet net du directeur (« 0/20 ·
tu penses trop IA »).

CE QUE LA PREMIÈRE VERSION FAISAIT DE FAUX

Elle partait de l'INTÉRIEUR — « le tarif X de SGCI dépasse la médiane marché de 67 %,
réexaminez-le » — et sortait une liste d'écarts. Un rapport d'audit tarifaire, pas une
stratégie. Un directeur commercial n'ouvre pas son année là-dessus.

CE QUE FAIT CELLE-CI

Elle part de l'EXTÉRIEUR, comme le fait une direction de la stratégie dans une grande
banque : le marché bouge (une filière monte, l'État investit, une réglementation change),
donc la banque agit. L'enchaînement est :

    SIGNAL DE MARCHÉ  →  SECTEUR CONCERNÉ  →  CLIENTS VISÉS  →  PRODUITS À POUSSER
                      →  PRIORITÉ  →  OBJECTIF  →  INDICATEURS DE SUIVI

Le format de sortie reproduit celui demandé par le directeur, en toutes lettres :
un titre d'action, deux paragraphes rédigés (contexte de marché, puis ce qu'il faut faire),
une priorité, un objectif et les indicateurs à suivre. Pas de puces mécaniques.

CE MODULE NE RÉDIGE PAS — il constitue le DOSSIER DE FAITS de chaque secteur et le
note. La rédaction est confiée au LLM côté serveur, à partir de ces faits uniquement,
selon la même séparation que le reste de l'application : le déterministe établit,
le LLM met en forme.
"""
import os
import json
import datetime

from functools import lru_cache

import db

HERE = os.path.dirname(os.path.abspath(__file__))
# Données de référence regroupées dans spybusiness/data/ (2026-07-30) : elles alimentent
# les analyses et se conservent, contrairement aux caches qui se régénèrent.
DOSSIER_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "data")
WEB_FACTS = os.path.join(DOSSIER_DATA, "web_facts.json")


# ── SECTEURS SUIVIS ──────────────────────────────────────────────────────────────────
# Retenus parce que chacun réunit trois conditions : il pèse dans l'économie ivoirienne,
# il produit de l'information publique régulière (donc traçable), et il correspond à des
# produits bancaires identifiables. Un secteur sans source publique fiable ne serait qu'une
# opinion déguisée en analyse.
#
# `faits` : clés de web_facts.json qui ancrent le secteur. Un secteur dont aucun fait n'est
# disponible est écarté du rendu — mieux vaut sept recommandations sourcées que douze dont
# cinq inventées.
SECTEURS = [
    {
        # FUSION cacao + anacarde (2026-07-30). Les deux filières étaient suivies séparément et
        # produisaient la MÊME décision écrite deux fois — « financement de campagne pour les
        # coopératives » d'un côté, « crédit de campagne pour les producteurs d'anacarde » de
        # l'autre. Or elles partagent le cycle de campagne, les produits bancaires et le segment
        # CLIPRO : les séparer ne créait pas deux décisions, cela dupliquait la même. Réunies,
        # elles gardent leurs quatre faits distincts (prix cacao, calendrier, anacarde, coton)
        # sans dédoubler la recommandation.
        "cle": "agro",
        "leviers_marketing": ["campagne de notoriété en zones de production",
                              "offre packagée « campagne » identifiable",
                              "partenariats avec les faîtières de coopératives",
                              "argumentaire de domiciliation des recettes d'exportation"],
        "delai_mois": 6,
        "nom": "Agro-industrie — cacao, café, anacarde et coton",
        "segment": "CLIPRO / CLICOM",
        "cibles": "coopératives, exportateurs et unités de transformation",
        "faits": ["cacao_prix", "cacao_campagne", "anacarde", "coton"],
        "produits": ["financement de campagne", "garanties bancaires",
                     "domiciliation des recettes d'exportation",
                     "financement d'équipement", "gestion de trésorerie"],
        "indicateurs": ["Nombre de coopératives bancarisées",
                        "Encours de crédit de campagne",
                        "Volume de recettes domiciliées",
                        "PNB du segment agro-industrie"],
        "saisonnalite": "cacao_campagne",
        "risque_base": 30,   # filières encadrées, mais l'anacarde suit les cours mondiaux
    },
    {
        "cle": "commerce",
        "leviers_marketing": ["acquisition de terrain sur les marchés et zones commerçantes",
                              "offre d'entrée sur la monétique marchande",
                              "relais par les associations de commerçants"],
        "delai_mois": 9,
        "nom": "Commerce et distribution",
        "segment": "CLIPRO",
        "cibles": "commerçants, détaillants, grossistes et distributeurs",
        "faits": ["commerce_informel", "commerce_tpe", "mobile_money", "bancarisation"],
        "produits": ["compte professionnel", "acquisition monétique et terminaux de paiement",
                     "versements et remises d'espèces", "découvert de trésorerie",
                     "encaissement de chèques"],
        "indicateurs": ["Nombre de commerçants équipés en acceptation",
                        "Volume d'espèces traité en agence",
                        "Commissions monétique marchande",
                        "Taux d'équipement en compte professionnel"],
        "risque_base": 50,   # trésorerie irrégulière, comptabilité souvent informelle
    },
    {
        "cle": "transport",
        "leviers_marketing": ["présence sur les plateformes logistiques et portuaires",
                              "offre dédiée au financement de flotte",
                              "partenariats avec les syndicats de transporteurs"],
        "delai_mois": 12,
        "nom": "Transport et logistique",
        "segment": "CLIPRO / CLICOM",
        "cibles": "transporteurs, transitaires et opérateurs logistiques",
        "faits": ["transport_port", "transport_corridor"],
        "produits": ["financement d'équipement et de flotte", "crédit-bail",
                     "cautions en douane", "gestion de trésorerie"],
        "indicateurs": ["Encours de financement de flotte",
                        "Nombre de cautions en douane délivrées",
                        "PNB du segment transport"],
        "risque_base": 55,   # actifs mobiles, valeur de gage difficile à maîtriser
    },
    {
        "cle": "import_export",
        "leviers_marketing": ["argumentaire sur les délais de traitement des opérations",
                              "offre de couverture de change",
                              "relais via les chambres de commerce"],
        "delai_mois": 9,
        "nom": "Import-export et négoce",
        "segment": "CLICOM",
        "cibles": "importateurs, exportateurs et maisons de négoce",
        "faits": ["commerce_exterieur", "cout_credit"],
        "produits": ["crédit documentaire", "remise documentaire",
                     "opérations de change", "transferts internationaux",
                     "cautions et garanties internationales"],
        "indicateurs": ["Nombre de crédits documentaires traités",
                        "Volume de change intermédié",
                        "Commissions sur opérations avec l'étranger"],
        "risque_base": 45,
    },
    {
        "cle": "btp",
        "leviers_marketing": ["présence auprès des maîtres d'ouvrage publics",
                              "offre de cautionnement de marché",
                              "communication sur les délais de mise en place"],
        "delai_mois": 18,
        "nom": "BTP et immobilier",
        "segment": "CLIPRO / CLICOM",
        "cibles": "entreprises de construction, promoteurs et maîtres d'œuvre",
        "faits": ["btp_logement", "btp_investissement"],
        "produits": ["cautions de marché et de bonne fin", "crédit d'investissement",
                     "financement de promotion immobilière", "crédit immobilier"],
        "indicateurs": ["Encours de cautions de marché",
                        "Nombre de programmes immobiliers financés",
                        "Taux de sinistralité du portefeuille BTP"],
        "risque_base": 65,   # cycle long, dépendance à la commande publique
    },
    {
        "cle": "numerique", "leviers_marketing": ["acquisition digitale des commerçants", "offre de bienvenue sur la monétique marchande", "visibilité sur les places de marché en ligne"], "delai_mois": 3,
        "nom": "Économie numérique et paiements mobiles",
        "segment": "GP / BG et CLIPRO",
        "cibles": "startups, entreprises technologiques et commerçants",
        "faits": ["mobile_money", "bancarisation"],
        "produits": ["comptes et services digitaux", "acquisition monétique commerçants",
                     "passerelles de paiement", "crédit court terme scoré"],
        "indicateurs": ["Taux d'équipement en services digitaux",
                        "Commissions sur services de paiement",
                        "Nombre de commerçants équipés en acceptation"],
        "risque_base": 35,
    },
    {
        "cle": "pme", "leviers_marketing": ["parcours d'entrée simplifié pour les PME", "communication sur les garanties et cautions", "relais via les chambres consulaires"], "delai_mois": 18,
        "nom": "Financement des PME",
        "segment": "CLIPRO",
        "cibles": "petites et moyennes entreprises de tous secteurs",
        "faits": ["financement_pme", "cout_credit"],
        "produits": ["crédit d'investissement", "découvert de trésorerie",
                     "garanties et cautions", "affacturage"],
        "indicateurs": ["Nombre de PME financées",
                        "Encours de crédit PME",
                        "Taux de sinistralité du portefeuille PME"],
        "risque_base": 55,   # segment structurellement plus risqué
    },
    {
        "cle": "conformite", "leviers_marketing": ["pédagogie client sur les seuils de déclaration", "communication de conformité auprès des grands comptes"], "delai_mois": 6,
        "nom": "Conformité et maîtrise du risque",
        "segment": "Toutes directions",
        "cibles": "l'ensemble du portefeuille",
        "faits": ["seuil_especes", "npl_secteur", "solvabilite_secteur", "politique_monetaire"],
        "produits": ["dispositif de déclaration", "revue des limites d'engagement",
                     "politique de provisionnement"],
        "indicateurs": ["Taux de créances en souffrance",
                        "Ratio de solvabilité",
                        "Nombre de déclarations transmises"],
        "risque_base": 70,   # sujet défensif : l'enjeu est de ne pas subir
        "defensif": True,
    },
]


# UNITÉS D'AFFICHAGE — la veille stocke des valeurs brutes (« 2800 ») parce que l'extraction
# ne retient que le nombre. Servi tel quel au rédacteur, cela donnait « un prix garanti du cacao
# à 2800 », sans unité : une note de direction ne s'écrit pas ainsi. L'unité est une propriété
# de l'indicateur, connue à l'avance ; on la restitue ici plutôt que d'espérer que le modèle
# la devine — il l'inventerait aussi bien en dollars.
_UNITES = {
    "cacao_prix": "FCFA/kg", "anacarde": "FCFA/kg", "coton": "FCFA/kg",
    "seuil_especes": "FCFA",
    # Secteurs hors agriculture. Les indicateurs déjà exprimés en pourcentage par l'extraction
    # (« 48 % ») n'ont pas d'entrée ici : _avec_unite n'ajoute rien si l'unité y figure déjà.
    "commerce_tpe": "terminaux ou commerçants équipés",
    "transport_port": "tonnes par an",
    "transport_corridor": "tonnes",
    "commerce_exterieur": "milliards FCFA",
    "btp_logement": "logements",
    "btp_investissement": "milliards FCFA",
}


def _avec_unite(cle, valeur):
    """Valeur suivie de son unité, si l'unité n'y figure pas déjà."""
    v = str(valeur or "").strip()
    u = _UNITES.get(cle)
    if not u or not v or u.lower() in v.lower():
        return v
    # Espace fine entre milliers pour la lisibilité d'une note écrite (2800 → 2 800).
    if v.isdigit() and len(v) > 3:
        v = f"{int(v):,}".replace(",", " ")
    return f"{v} {u}"


def _faits_web():
    """Faits de veille indexés par clé. {} si le fichier manque — jamais d'exception."""
    try:
        data = json.load(open(WEB_FACTS, encoding="utf-8"))
        return {f.get("cle"): f for f in data.get("secteur", []) if f.get("cle")}
    except Exception:
        return {}


# ── URGENCE CALENDAIRE ───────────────────────────────────────────────────────────────
_MOIS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
         "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
         "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}


def _urgence_calendaire(valeur):
    """0-100 selon la proximité d'une échéance de campagne.

    Une campagne agricole n'a d'intérêt commercial que si la banque se positionne AVANT son
    ouverture : les comptes se créent au moment où l'argent arrive, pas après. Une échéance
    dans trois semaines vaut donc davantage qu'une échéance dans six mois — c'est le seul
    critère de priorité que les données publiques permettent d'établir honnêtement.
    """
    if not valeur:
        return 0
    txt = str(valeur).lower()
    mois = next((n for m, n in _MOIS.items() if m in txt), None)
    if not mois:
        return 0
    auj = datetime.date.today()
    cible = datetime.date(auj.year, mois, 1)
    if cible < auj:                                  # échéance passée → prochaine occurrence
        cible = datetime.date(auj.year + 1, mois, 1)
    jours = (cible - auj).days
    if jours <= 30:
        return 100
    if jours <= 90:
        return 70
    if jours <= 180:
        return 40
    return 20


def justification_secteur(sec, faits, annee, semestre, segment,
                          produits=None, concurrents=None):
    """Pourquoi CE secteur figure dans la liste — en pièces vérifiables, pas en opinion.

    Demande du directeur : « on ne choisit pas en désordre, faut justifier ». Un onglet qui
    affirme suivre huit secteurs sans dire pourquoi ceux-là invite légitimement la question
    « et pourquoi pas les autres ? ». La réponse ne peut pas être le goût de celui qui a écrit
    la liste : elle doit se compter.

    Trois preuves, toutes recalculées à chaque appel — donc susceptibles de retirer un secteur
    si les données cessent de le soutenir :

      1. FAITS SOURCÉS      combien d'indicateurs de veille datés et sourcés l'ancrent.
                            Zéro fait = le secteur ne serait qu'une intuition, il est écarté.
      2. CATALOGUE SGCI     combien de lignes tarifaires publiées par SGCI s'y rapportent.
                            La banque ne peut servir un secteur qu'avec des produits existants.
      3. TERRAIN CONCURRENT combien de banques du marché y sont déjà présentes.
                            Un terrain occupé est un terrain qui compte ; un terrain désert
                            est soit une ouverture, soit un mirage — dans les deux cas c'est
                            une information pour le comité.

    Ces trois nombres sortent respectivement de web_facts.json, de cb_tarifs et des grilles
    concurrentes. Aucun n'est écrit à la main.
    """
    # `produits` et `concurrents` sont passés par dossiers(), qui les a déjà calculés : les
    # recalculer ici doublait deux requêtes lourdes par secteur, soit seize requêtes inutiles
    # sur huit secteurs. Les paramètres restent facultatifs pour un appel isolé.
    n_faits = len([k for k in sec["faits"] if faits.get(k, {}).get("valeur")])
    if produits is None:
        try:
            produits = produits_sgci(sec["cle"], annee, semestre, segment, limite=200)
        except Exception:
            produits = []
    if concurrents is None:
        try:
            concurrents = _concurrence(sec, annee, semestre, segment)
        except Exception:
            concurrents = []
    n_produits, n_concurrents = len(produits), len(concurrents)

    motifs = []
    if n_faits:
        motifs.append(f"{n_faits} indicateur{'s' if n_faits > 1 else ''} de veille daté"
                      f"{'s' if n_faits > 1 else ''} et sourcé{'s' if n_faits > 1 else ''}")
    if n_produits:
        motifs.append(f"{n_produits} ligne{'s' if n_produits > 1 else ''} du catalogue SGCI "
                      f"mobilisable{'s' if n_produits > 1 else ''}")
    if n_concurrents:
        motifs.append(f"{n_concurrents} banque{'s' if n_concurrents > 1 else ''} concurrente"
                      f"{'s' if n_concurrents > 1 else ''} déjà présente"
                      f"{'s' if n_concurrents > 1 else ''} sur ce terrain")
    elif n_faits:
        motifs.append("aucun concurrent identifié sur ce terrain")

    return {
        "faits_sources": n_faits,
        "produits_catalogue": n_produits,
        "concurrents_presents": n_concurrents,
        "texte": "Suivi parce que : " + " · ".join(motifs) + "." if motifs else "",
        # Un secteur sans aucun fait n'est pas justifiable : le rendu doit pouvoir l'écarter.
        "retenu": n_faits > 0,
    }


def _score_secteur(sec, faits):
    """Note d'opportunité et de risque d'un secteur, chaque composante étant traçable.

    IMPORTANT — ce n'est PAS une prévision de revenus. Le système ne dispose ni des volumes
    clients ni des parts de marché : prétendre chiffrer un gain serait inventer. Le score
    mesure la FORCE DU SIGNAL disponible et la proximité de l'échéance, c'est-à-dire le degré
    d'attention que le secteur mérite aujourd'hui. Les composantes sont exposées telles quelles
    dans le rendu, afin qu'un directeur puisse contester la note plutôt que la subir.
    """
    presents = [k for k in sec["faits"] if faits.get(k, {}).get("valeur")]
    couverture = round(100 * len(presents) / max(1, len(sec["faits"])))

    urgence = 0
    if sec.get("saisonnalite"):
        urgence = _urgence_calendaire((faits.get(sec["saisonnalite"]) or {}).get("valeur"))

    # Fraîcheur : un fait de l'année en cours pèse plus qu'un fait de 2022.
    annee_courante = datetime.date.today().year
    annees = []
    for k in presents:
        src = str(faits[k].get("source", ""))
        an = next((int(m) for m in src.split() if m.isdigit() and 2000 < int(m) <= annee_courante + 1), None)
        if an:
            annees.append(an)
    fraicheur = 100 if not annees else max(0, 100 - (annee_courante - max(annees)) * 25)

    opportunite = round(0.45 * couverture + 0.30 * fraicheur + 0.25 * urgence)
    risque = sec.get("risque_base", 50)

    if sec.get("defensif"):
        priorite = "Élevée" if risque >= 60 else "Moyenne"
    else:
        ecart = opportunite - risque
        priorite = "Très élevée" if ecart >= 45 else "Élevée" if ecart >= 20 else \
                   "Moyenne" if ecart >= 0 else "Faible"

    return {
        "opportunite": opportunite, "risque": risque, "priorite": priorite,
        "detail_score": {"couverture_faits": couverture, "fraicheur": fraicheur,
                         "urgence_calendaire": urgence},
    }


# ── BUSINESS CASE ────────────────────────────────────────────────────────────────────
# Demande du directeur : « la vraie question d'un DG n'est pas *que dois-je faire* mais
# *quel sera le retour sur investissement* ». Une recommandation sans chiffrage reste
# descriptive ; un chiffrage inventé serait pire encore.
#
# La sortie de secours est le MODÈLE À HYPOTHÈSES EXPLICITES, celui qu'emploie un cabinet
# de conseil : on ne connaît pas les volumes internes, on pose des hypothèses, ON LES AFFICHE,
# et le lecteur peut les remplacer par les siennes. Un chiffre dont on voit la mécanique est
# un outil d'arbitrage ; un chiffre nu est une affirmation.
#
# Ce qui est CALCULÉ (donc non discutable) :
#   commission moyenne par client = commissions du compte de résultat / nombre de clients
#   contribution au PNB           = impact estimé / PNB publié
# Ce qui est HYPOTHÉTIQUE (donc affiché et modifiable) :
#   le nombre de clients captables sur le secteur.
#
# Correction d'ordre de grandeur relevée en construisant : une estimation « au doigt » donnait
# +350 M FCFA pour 400 nouveaux clients cacao. Le calcul réel donne ~48 M. Un facteur dix —
# exactement ce que le modèle sert à éviter.

def economie_sgci():
    """Repères économiques réels de SGCI, lus en base et dans la veille.

    Renvoie des None plutôt que des valeurs par défaut : un business case bâti sur un repère
    inventé serait moins utile qu'une absence de business case, qui au moins se voit.
    """
    out = {"commissions_m": None, "pnb_m": None, "clients": None,
           "commission_moyenne": None, "part_commissions_pnb": None,
           "meilleur_ratio": None, "meilleur_ratio_banque": None}
    try:
        k = db.kpis_vue_ensemble(2026, "S1", "Particuliers", 3) or {}
        comm, pnb = (k.get("commissions_data") or {}), (k.get("pnb_data") or {})
        out["commissions_m"] = comm.get("SGCI")
        out["pnb_m"] = pnb.get("SGCI")
        # Meilleure part de commissions du marché : la cible crédible d'un plan de
        # rééquilibrage, puisqu'une banque comparable l'atteint déjà.
        ratios = {b: 100 * comm[b] / pnb[b] for b in comm if comm.get(b) and pnb.get(b)}
        if ratios:
            out["part_commissions_pnb"] = round(ratios.get("SGCI", 0), 1)
            meilleur = max(ratios, key=ratios.get)
            out["meilleur_ratio"] = round(ratios[meilleur], 1)
            out["meilleur_ratio_banque"] = meilleur
    except Exception:
        pass

    # Nombre de clients : issu du rapport d'activité, collecté par la veille.
    f = _faits_web().get("clients_sgci") or {}
    import re as _re_cl
    m = _re_cl.search(r"(\d[\d\s ]{4,})", str(f.get("valeur") or ""))
    if m:
        try:
            out["clients"] = int(m.group(1).replace(" ", "").replace(" ", ""))
        except Exception:
            pass

    if out["commissions_m"] and out["clients"]:
        out["commission_moyenne"] = round(out["commissions_m"] * 1_000_000 / out["clients"])
    return out


# Nombre de clients captables par secteur — SEULE hypothèse du modèle, exposée comme telle.
# Fourchettes volontairement prudentes : une hypothèse optimiste non signalée est un mensonge
# à retardement. Le front les rend modifiables ; ces valeurs ne sont qu'un point de départ.
_CAPTATION = {
    # Fourchettes de clients captables. Ce sont des HYPOTHÈSES, affichées comme telles par
    # business_case() : la banque ne dispose pas de comptages de marché par secteur. Elles sont
    # ordonnées par taille de population adressable — il y a plus de commerçants que de maisons
    # de négoce — et non par appétence, qu'aucune donnée ne mesure ici.
    "agro":         (300, 550,  "coopératives, exportateurs et unités de transformation"),
    "commerce":     (900, 1800, "commerçants, détaillants et grossistes"),
    "transport":    (200, 400,  "transporteurs, transitaires et logisticiens"),
    "import_export": (80, 180,  "importateurs, exportateurs et maisons de négoce"),
    "btp":          (120, 250,  "entreprises de construction et promoteurs"),
    "numerique":    (800, 1500, "commerçants et entreprises technologiques"),
    "pme":          (300, 600,  "petites et moyennes entreprises"),
    "conformite":   (0,   0,    ""),   # secteur défensif : il évite une perte, il n'apporte pas de client
}


def business_case(sec, eco):
    """Impact estimé d'un secteur, avec ses hypothèses en clair.

    Le secteur défensif (conformité) ne produit pas de business case de conquête : son enjeu
    est d'éviter une sanction ou une perte, pas de gagner des clients. Lui inventer un gain
    commercial serait un contresens.
    """
    bas, haut, cible = _CAPTATION.get(sec["cle"], (0, 0, ""))
    cm = eco.get("commission_moyenne")
    if not bas or not cm:
        return None

    comm_bas, comm_haut = bas * cm, haut * cm          # FCFA/an
    pnb_f = (eco.get("pnb_m") or 0) * 1_000_000
    contrib = (round(100 * comm_bas / pnb_f, 3), round(100 * comm_haut / pnb_f, 3)) if pnb_f else None

    # Confiance : part des éléments CALCULÉS dans le total des éléments mobilisés.
    # Trois calculés (commission moyenne, PNB, faits de marché sourcés) contre une hypothèse.
    n_calc = sum(1 for x in (cm, eco.get("pnb_m"), sec.get("faits_sources")) if x)
    confiance = round(100 * n_calc / (n_calc + 1))

    return {
        "clients_min": bas, "clients_max": haut, "cible": cible,
        "commissions_min_fcfa": comm_bas, "commissions_max_fcfa": comm_haut,
        "contribution_pnb_pct": contrib,
        "confiance": confiance,
        "hypotheses": [
            {"libelle": f"Clients captables sur {cible}", "valeur": f"{bas} à {haut}",
             "nature": "hypothèse", "ajustable": True},
            {"libelle": "Commission moyenne par client et par an",
             "valeur": f"{cm:,} FCFA".replace(",", " "),
             "nature": "calculé", "detail": "commissions du compte de résultat / nombre de clients"},
            {"libelle": "PNB de référence", "valeur": f"{eco.get('pnb_m'):,.0f} M FCFA".replace(",", " ")
             if eco.get("pnb_m") else "—", "nature": "calculé"},
        ],
    }


def _concurrence(sec, annee, semestre, segment):
    """Quels concurrents proposent DÉJÀ des services liés à ce secteur.

    Tirée des catalogues tarifaires publiés — donc sourcée et vérifiable, contrairement à une
    veille d'annonces qui resterait déclarative. Répond à « la banque ne vit pas seule » :
    une opportunité déjà occupée par trois concurrents ne se traite pas comme un terrain vierge.
    """
    mots = {
        "agro":          r"(?i)campagne|agricole|export|warrant|mati[èe]res? premi",
        "commerce":      r"(?i)mon[ée]tique|marchand|TPE|versement|remise|esp[èe]ce|commer[çc]ant",
        "transport":     r"(?i)cr[ée]dit.bail|leasing|flotte|v[ée]hicule|douane|transit",
        "import_export": r"(?i)documentaire|change|transfert|[ée]tranger|devise|import|export",
        "btp":           r"(?i)caution|march[ée]|immobilier|construction|habitat|logement",
        "numerique":  r"(?i)mobile|digital|en ligne|internet|monetique|mon[ée]tique|\bTPE\b|marchand",
        "pme":        r"(?i)\bPME\b|profession|entreprise|caution|affacturage",
        "conformite": r"(?i)conformit|d[ée]claration|kyc",
    }.get(sec["cle"])
    if not mots:
        return []
    try:
        lignes = db.query(
            "SELECT banque, COUNT(*) n FROM cb_tarifs "
            "WHERE annee=%s AND semestre=%s AND is_header=FALSE AND banque<>'SGCI' "
            "AND libelle ~ %s GROUP BY banque ORDER BY n DESC LIMIT 4",
            (annee, semestre, mots))
        return [{"banque": r["banque"], "n_services": r["n"]} for r in lignes]
    except Exception:
        return []


# ── ARBITRAGE COMEX ──────────────────────────────────────────────────────────────────
# « Priorité élevée » ne suffit pas à arbitrer : deux secteurs prioritaires ne se valent pas
# si l'un rend en 3 mois et l'autre en 18. Le comité a besoin des trois mêmes colonnes que
# dans n'importe quel comité d'investissement — RENDEMENT, DÉLAI, DIFFICULTÉ — pour trancher
# en une lecture.
#
# Le ROI est exprimé en étoiles et NON en pourcentage : un pourcentage laisserait croire à une
# précision que le modèle n'a pas. Cinq étoiles disent « à traiter en premier », pas « 23,4 % ».

def arbitrage(sec):
    """ROI (1-5 étoiles), délai d'exécution et difficulté, pour le tableau d'arbitrage."""
    # Rendement = écart entre l'attrait du marché et le risque porté, pondéré par la rapidité :
    # un gain lointain vaut moins qu'un gain proche, à écart égal.
    delai = sec.get("delai_mois", 12)
    ecart = sec.get("opportunite", 0) - sec.get("risque", 50)
    bonus_rapidite = 15 if delai <= 6 else (5 if delai <= 12 else -10)
    note = ecart + bonus_rapidite

    etoiles = 5 if note >= 70 else 4 if note >= 45 else 3 if note >= 20 else 2 if note >= 0 else 1
    r = sec.get("risque", 50)
    difficulte = "Faible" if r < 35 else "Moyenne" if r < 60 else "Élevée"
    return {"roi_etoiles": etoiles, "roi_libelle": "★" * etoiles + "☆" * (5 - etoiles),
            "delai_mois": delai,
            "delai_libelle": f"{delai} mois",
            "difficulte": difficulte}


# Direction responsable par défaut d'un secteur. Le directeur commercial doit pouvoir ne voir
# que ce qui le concerne — une note qui s'adresse à tout le monde ne s'adresse à personne.
_DIRECTION_SECTEUR = {
    "agro": "Direction Commerciale", "commerce": "Direction Commerciale",
    "transport": "Direction Financière", "import_export": "Direction Financière",
    "btp": "Direction des Risques",
    "numerique": "Direction Innovation", "pme": "Direction Commerciale",
    "conformite": "Direction des Risques",
}
# Direction Générale volontairement ABSENTE (2026-07-30, demande du directeur) : l'onglet
# Stratégie lui est déjà destiné — il répond à « où en sommes-nous, où allons-nous ». Cet
# onglet-ci s'adresse aux directions qui EXÉCUTENT. Faire figurer la DG dans les deux revient
# à lui demander de trier elle-même ce qui la concerne, c'est-à-dire à ne rien trier.
DIRECTIONS = ["Direction Financière", "Direction Commerciale",
              "Direction Marketing", "Direction Innovation", "Direction des Risques"]


# ── ÉVÉNEMENTS DE MARCHÉ RATTACHÉS AUX SECTEURS ──────────────────────────────────────
# Les indicateurs disent l'état du marché ; les événements disent ce qui vient de bouger. Un
# accord signé par un concurrent ou un programme public de 480 milliards ne se lit pas dans un
# taux — c'est pourtant ce qui déclenche une décision. Collectés par run_veille.run_evenements().
#
# Le domaine « banque_concurrence » alimente TOUS les secteurs : un mouvement de concurrent
# concerne la banque quel que soit le terrain, et c'est précisément l'information qui manquait
# (« BICICI finance déjà les exportateurs » ne se déduit pas d'un catalogue tarifaire).
_DOMAINES_SECTEUR = {
    "agro":          ["agro", "environnement", "banque_concurrence"],
    "commerce":      ["numerique", "social", "banque_concurrence"],
    "transport":     ["infrastructure", "banque_concurrence"],
    "import_export": ["infrastructure", "reglementation", "banque_concurrence"],
    "btp":           ["infrastructure", "environnement", "banque_concurrence"],
    "numerique":     ["numerique", "banque_concurrence"],
    "pme":           ["infrastructure", "numerique", "banque_concurrence"],
    "conformite":    ["reglementation", "banque_concurrence"],
}


def _evenements_secteur(cle, limite=3):
    """Événements récents pertinents pour un secteur, les plus récents d'abord."""
    try:
        data = json.load(open(WEB_FACTS, encoding="utf-8"))
    except Exception:
        return []
    domaines = _DOMAINES_SECTEUR.get(cle, [])
    evts = [e for e in data.get("evenements", []) if e.get("domaine") in domaines]
    evts.sort(key=lambda e: e.get("releve_le", ""), reverse=True)
    return evts[:limite]


# ── PRODUITS SGCI RÉELS PAR SECTEUR ──────────────────────────────────────────────────
# Une décision qui dit « promouvoir le financement de campagne » reste une intention : personne
# ne sait quel produit vendre ni à quel prix. La banque possède pourtant son propre catalogue
# tarifaire en base — autant nommer les lignes existantes, avec leur tarif publié.
#
# Deux effets : la décision devient exécutable telle quelle par un chargé de clientèle, et le
# rédacteur cesse d'inventer des noms de produits qui n'existent pas chez SGCI.

# Motifs RESSERRÉS le 2026-07-30. La première version acceptait « domicili » seul, ce qui
# faisait remonter « domiciliation de salaires » sur la filière cacao — et le rédacteur écrivait
# « développer le crédit de campagne en utilisant la domiciliation de salaires », qui n'a aucun
# sens. On exige désormais le complément qui donne au terme son sens métier.
_MOTS_PRODUIT = {
    "agro":          r"(?i)campagne|agricole|export|warrant|domiciliation d.(effet|op[ée]ration)|caution|cr[ée]dit",
    "commerce":      r"(?i)mon[ée]tique|marchand|TPE|versement|remise|esp[èe]ce|commer[çc]ant|profession",
    "transport":     r"(?i)cr[ée]dit.bail|leasing|flotte|v[ée]hicule|caution|douane|transit",
    "import_export": r"(?i)cr[ée]dit documentaire|remise documentaire|change|transfert|[ée]tranger|import|export|devise",
    "btp":           r"(?i)caution|march[ée]|immobilier|construction|bonne fin|habitat|logement",
    "numerique":  r"(?i)mobile|digital|en ligne|internet|mon[ée]tique|marchand|TPE|carte",
    "pme":        r"(?i)PME|profession|entreprise|caution|affacturage|d[ée]couvert|cr[ée]dit",
    "conformite": r"(?i)attestation|d[ée]claration|opposition|saisie|conformit",
}


def produits_sgci(cle, annee, semestre, segment, limite=6):
    """Lignes du catalogue SGCI correspondant au secteur, avec leur tarif publié."""
    motif = _MOTS_PRODUIT.get(cle)
    if not motif:
        return []
    try:
        rows = db.query(
            "SELECT DISTINCT libelle, montant, est_gratuit, type_valeur FROM cb_tarifs "
            "WHERE banque='SGCI' AND annee=%s AND semestre=%s AND LOWER(segment)=LOWER(%s) "
            "AND is_header=FALSE AND libelle ~ %s "
            "AND LENGTH(TRIM(libelle)) BETWEEN 10 AND 80 "
            "ORDER BY montant DESC NULLS LAST LIMIT %s",
            (annee, semestre, segment, motif, limite))
    except Exception:
        return []
    out = []
    for r in rows:
        if r.get("est_gratuit"):
            prix = "gratuit"
        elif r.get("montant") and r.get("type_valeur") == "MONTANT_FCFA":
            prix = f"{int(r['montant']):,} F".replace(",", " ")
        elif r.get("montant") and r.get("type_valeur") == "TAUX_%":
            # Decimale a la francaise : « 3.5 % » sur une note de comite ivoirien se remarque
            # et fait douter du reste. Le nombre vient d'un calcul Python, pas de la brochure.
            prix = f"{r['montant']} %".replace(".", ",")
        else:
            prix = "tarif non chiffré"
        # Une ligne « tarif non chiffré » ne rend pas la décision plus exécutable : le chargé
        # de clientèle a besoin d'un prix à annoncer. On ne garde que le catalogue vendable.
        if prix == "tarif non chiffré":
            continue
        out.append({"libelle": str(r["libelle"]).strip(), "prix": prix})
    return out


# ── RÉPARTITION DES DIRECTIONS ───────────────────────────────────────────────────────
# Laissée au rédacteur, elle donnait 5 décisions au Marketing et 1 à l'Innovation : un directeur
# de l'Innovation ouvrant l'onglet n'y trouvait qu'une ligne. On impose donc à chaque secteur
# SES trois directions, choisies pour que chacune reçoive 2 à 4 décisions sur l'ensemble.
# Le choix suit la nature du secteur : le risque agricole concerne les Risques, le numérique
# concerne l'Innovation, la conformité ne concerne pas le Marketing.
DIRECTIONS_PAR_SECTEUR = {
    "agro":          ["Direction Commerciale", "Direction Marketing", "Direction des Risques"],
    "commerce":      ["Direction Commerciale", "Direction Marketing", "Direction Innovation"],
    "transport":     ["Direction Financière", "Direction des Risques", "Direction Commerciale"],
    "import_export": ["Direction Financière", "Direction Commerciale", "Direction Innovation"],
    "btp":           ["Direction des Risques", "Direction Financière", "Direction Commerciale"],
    "numerique":     ["Direction Innovation", "Direction Marketing", "Direction Commerciale"],
    "pme":           ["Direction Commerciale", "Direction Financière", "Direction des Risques"],
    "conformite":    ["Direction des Risques", "Direction Financière", "Direction Innovation"],
}
# Chaque direction est sollicitée par au moins quatre secteurs : Commerciale 8, Marketing 4,
# Financière 5, Risques 5, Innovation 4. Aucune ne repart les mains vides, et aucune n'est
# servie par un secteur qui ne la concerne pas — le rattachement suit le métier (le crédit
# documentaire relève de la Financière, la caution de marché du Risque), pas un quota.


# ── COHÉRENCE AVEC LA STRATÉGIE GLOBALE ──────────────────────────────────────────────
# Demande du directeur : « les décisions de toutes les directions doivent être cohérentes avec
# la stratégie globale ; si la globale dit +5 % de commissions, l'opérationnel dit COMMENT ».
#
# L'onglet Stratégie produit une projection à trois ans en trois scénarios (prudent, central,
# optimiste). L'écart entre le scénario CENTRAL et la trajectoire naturelle est l'effort que le
# plan doit produire — c'est l'objectif que les décisions opérationnelles servent à atteindre.
# Sans ce rattachement, les deux onglets racontent deux histoires sans lien.
#
# On rapporte donc la somme des impacts sectoriels à cet écart : le lecteur voit immédiatement
# quelle part de l'ambition les décisions couvrent réellement — et ce qu'il reste à trouver
# ailleurs (repricing du portefeuille existant, volumes, maîtrise du coût du risque).

DOSSIER_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cache")
STRAT_BUILD_FILE = os.path.join(DOSSIER_CACHE, "strategie_build_cache.json")


def _projection_depuis_cache(segment):
    """Projection à 3 ans lue dans le build Stratégie déjà calculé, ou None.

    MESURÉ le 2026-07-30 : reconstruire la projection ici coûte 546 secondes — collect_evidence
    puis build_projection repassent sur toute la base de preuves. Or l'onglet Stratégie a DÉJÀ
    fait ce calcul et l'a écrit sur disque : le refaire pour en extraire une seule métrique est
    du gaspillage pur, et c'est ce qui rendait le premier chargement de cet onglet interminable.

    On lit donc le résultat existant. S'il est absent — première ouverture après un vidage du
    cache, ou veille plus récente — l'appelant retombe sur le calcul complet : le chiffre reste
    juste, il coûte seulement son prix ce jour-là.
    """
    try:
        veille = os.path.getmtime(WEB_FACTS)
        cache_t = os.path.getmtime(STRAT_BUILD_FILE)
        if veille > cache_t:
            return None            # la veille a bougé : le build en cache est périmé
        with open(STRAT_BUILD_FILE, encoding="utf-8") as f:
            proj = (json.load(f).get(segment) or {}).get("projection")
        return proj if isinstance(proj, list) and proj else None
    except Exception:
        return None


@lru_cache(maxsize=8)
def objectif_global(segment="Particuliers"):
    """Cible de la Stratégie globale : scénario central à 3 ans, et écart à combler.

    MÉMORISÉ (2026-07-30) : cette fonction reconstruit toute la base de preuves de la Stratégie
    (collect_evidence + build_projection), ce qui portait la réponse de l'onglet à 81 secondes.
    La projection ne dépend que des données, pas de la requête : la calculer une fois par
    processus suffit. Le cache est purgé avec les autres par db.refresh_banks() à l'ingestion.
    """
    proj = _projection_depuis_cache(segment)
    if proj is None:
        try:
            import strategie as _st
            proj = _st.build_projection(_st.collect_evidence(segment)) or []
        except Exception:
            return None
    pnb = next((m for m in proj if str(m.get("nom", "")).upper().startswith("PNB")), None)
    if not pnb or not pnb.get("central") or not pnb.get("actuel"):
        return None
    central, naturel = pnb["central"][-1], pnb["actuel"][-1]
    return {
        "metrique": "PNB",
        "unite": pnb.get("unite", "Mds"),
        "depart": pnb["central"][0],
        "cible_centrale": central,
        "trajectoire_naturelle": naturel,
        "ecart_a_combler": round(central - naturel, 1),
        "horizon_ans": max(1, len(pnb["central"]) - 1),
        "hypothese": (pnb.get("hypothese") or "")[:180],
    }


def dossiers(annee=2026, semestre="S1", segment="Particuliers"):
    """Dossier de faits par secteur — matière première de la rédaction LLM.

    Chaque dossier réunit le signal externe (veille) et l'ancrage interne (position de SGCI
    sur les services concernés), pour que la recommandation rédigée ne soit ni une opinion
    générale sur l'économie ivoirienne, ni un audit tarifaire déconnecté du marché.
    """
    faits = _faits_web()
    eco = economie_sgci()
    out = []
    for sec in SECTEURS:
        f_dispo = [{"cle": k, "valeur": _avec_unite(k, faits[k].get("valeur")),
                    "detail": faits[k].get("detail", ""),
                    "source": faits[k].get("source", ""),
                    "date": faits[k].get("date", ""),
                    "url": faits[k].get("url", "")}
                   for k in sec["faits"] if faits.get(k, {}).get("valeur")]
        if not f_dispo:
            continue          # aucun fait → aucune recommandation. On n'invente pas un secteur.
        d = dict(sec)
        d["faits_sources"] = f_dispo
        d.update(_score_secteur(sec, faits))
        d["business_case"] = business_case(d, eco)
        d.update(arbitrage(d))
        d["direction"] = _DIRECTION_SECTEUR.get(sec["cle"], "Direction Commerciale")
        d["directions_imposees"] = DIRECTIONS_PAR_SECTEUR.get(sec["cle"], DIRECTIONS[:3])
        d["concurrence"] = _concurrence(sec, annee, semestre, segment)
        d["evenements"] = _evenements_secteur(sec["cle"])
        # Catalogue calculé UNE fois : la longueur sert de preuve dans la justification, les
        # premières lignes seulement sont affichées dans la fiche.
        prods = produits_sgci(sec["cle"], annee, semestre, segment, limite=200)
        d["produits_sgci"] = prods[:6]
        # Pourquoi ce secteur figure dans la liste — compté, pas affirmé (cf. justification_secteur).
        d["justification"] = justification_secteur(
            sec, faits, annee, semestre, segment,
            produits=prods, concurrents=d["concurrence"])
        out.append(d)

    out.sort(key=lambda d: -d["opportunite"])
    # Part de l'objectif global que les décisions sectorielles couvrent réellement.
    obj = objectif_global(segment)
    if obj and obj.get("ecart_a_combler"):
        total_fcfa = sum((d.get("business_case") or {}).get("commissions_max_fcfa") or 0 for d in out)
        obj["couvert_par_secteurs_mds"] = round(total_fcfa / 1e9, 2)
        obj["couverture_pct"] = round(100 * (total_fcfa / 1e9) / obj["ecart_a_combler"], 1)

    return {
        "annee": annee, "semestre": semestre, "segment": segment,
        "genere_le": datetime.date.today().isoformat(),
        "objectif_global": obj,
        "economie": eco,
        "directions": DIRECTIONS,
        "secteurs": out,
        "n_secteurs": len(out),
    }


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    d = dossiers()
    print(f"{d['n_secteurs']} secteurs notés · {d['genere_le']}\n")
    print(f"{'SECTEUR':40} {'OPP':>4} {'RISQ':>5}  PRIORITÉ")
    for s in d["secteurs"]:
        print(f"{s['nom'][:40]:40} {s['opportunite']:>4} {s['risque']:>5}  {s['priorite']}")
    print("\nFaits d'ancrage du premier secteur :")
    for f in d["secteurs"][0]["faits_sources"]:
        print(f"   {f['cle']:18} {str(f['valeur'])[:24]:26} [{f['source']}]")
