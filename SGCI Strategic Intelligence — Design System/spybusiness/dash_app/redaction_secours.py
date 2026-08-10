"""Rédaction de secours — quand le modèle de langage est indisponible.

POURQUOI CE MODULE EXISTE
    Les analyses rédigées de l'application passent par Groq. Le quota est journalier : une
    fois épuisé, l'appel échoue et le front vidait purement et simplement le bloc
    (`div.innerHTML = ''`). L'utilisateur voyait un TROU à l'endroit d'une analyse, sans rien
    qui l'explique. Un jour de quota épuisé, l'application paraissait cassée alors que tous
    ses chiffres étaient là.

CE QUE CE MODULE N'EST PAS
    Ce ne sont pas des phrases toutes faites rangées dans une liste. Une phrase figée
    devient fausse à la première ingestion de données, et personne ne s'en aperçoit — c'est
    exactement le défaut que ce projet combat partout ailleurs.

    Chaque texte d'ici est CALCULÉ à partir des mêmes faits que ceux envoyés au modèle :
    mêmes nombres, mêmes banques, mêmes classements. Si les données changent, le texte change.
    Si SGCI passe de la cinquième à la troisième place, la phrase le dit — sans qu'on y touche.

    C'est le principe du projet, appliqué jusqu'au bout : *le déterministe établit, le LLM
    formule*. Quand le LLM ne peut plus formuler, le déterministe formule à sa place — plus
    sèchement, mais sans jamais se tromper.

CE QUI DISTINGUE CES TEXTES
    Ils sont signalés comme tels au lecteur (`source = "deterministe"`), afin que personne ne
    prenne une rédaction de secours pour l'analyse complète. Mieux vaut une phrase juste et
    annoncée modeste qu'un blanc inexpliqué.
"""


def _fr(x):
    """Nombre à la française : séparateur de milliers en espace, virgule décimale."""
    if isinstance(x, float) and x != int(x):
        return f"{x:,.1f}".replace(",", " ").replace(".", ",")
    return f"{int(x):,}".replace(",", " ")


def _pl(n, mot, pluriel=None):
    """« 1 service » / « 3 services » — l'accord se fait, il ne se signale pas.

    Écrire « 3 service(s) » dans une note destinée à un comité revient à lui montrer la
    couture du gabarit. Le nombre est connu au moment où l'on écrit : il n'y a aucune raison
    de laisser le lecteur faire l'accord.
    """
    return f"{_fr(n)} {mot if abs(n) < 2 else (pluriel or mot + 's')}"


def _liste(elements, lien="et"):
    """« A, B et C » — une énumération lisible plutôt qu'une liste à virgules."""
    elements = [e for e in elements if e]
    if not elements:
        return ""
    if len(elements) == 1:
        return elements[0]
    return ", ".join(elements[:-1]) + f" {lien} " + elements[-1]


# ══════════════════════════════════════════════════════════════════════════════════════
#  Q1 — POSITION DANS LES CATALOGUES DU MARCHÉ
# ══════════════════════════════════════════════════════════════════════════════════════

def q1_classement(banques, segment="Particuliers", periode=""):
    """Position de SGCI dans le mouvement des catalogues — trois constats, aucun jugement.

    `banques` : [{b, ajouts, retraits, catalogue}, …] — exactement ce que reçoit le modèle.
    """
    banques = [b for b in (banques or []) if b.get("b")]
    if not banques:
        return None
    sgci = next((b for b in banques if b["b"] == "SGCI"), None)
    if not sgci:
        return None

    par_ajouts = sorted(banques, key=lambda b: -(b.get("ajouts") or 0))
    actifs = [b for b in par_ajouts if b["b"] != "SGCI" and (b.get("ajouts") or 0) > 0][:3]
    rang = 1 + sum(1 for b in banques if (b.get("ajouts") or 0) > (sgci.get("ajouts") or 0))
    par_taille = sorted(banques, key=lambda b: -(b.get("catalogue") or 0))
    rang_taille = 1 + sum(1 for b in banques
                          if (b.get("catalogue") or 0) > (sgci.get("catalogue") or 0))

    phrases = []

    if actifs:
        detail = _liste([f"{b['b']} (+{b['ajouts']})" for b in actifs])
        phrases.append(
            f"Sur la période{' ' + periode if periode else ''}, les catalogues les plus "
            f"mouvants sont ceux de {detail} ; SGCI ajoute {_pl(sgci.get('ajouts', 0), 'service')} "
            f"et se place au {rang}ᵉ rang sur {len(banques)} pour le rythme d'enrichissement.")
    else:
        phrases.append(
            f"Aucun concurrent n'a enrichi son catalogue sur la période ; SGCI ajoute "
            f"{_pl(sgci.get('ajouts', 0), 'service')}.")

    # Le plus menaçant : celui qui combine un catalogue large et un rythme d'ajout élevé.
    menace = None
    for b in par_ajouts:
        if b["b"] != "SGCI" and (b.get("ajouts") or 0) > 0:
            menace = b
            break
    if menace:
        ecart = (menace.get("catalogue") or 0) - (sgci.get("catalogue") or 0)
        situation = (f"son catalogue compte {_pl(abs(ecart), 'service')} de plus que celui de "
                     f"SGCI" if ecart > 0 else
                     f"son catalogue reste inférieur de {_pl(abs(ecart), 'service')} à celui de "
                     f"SGCI" if ecart < 0 else
                     "les deux catalogues sont de taille identique")
        phrases.append(
            f"{menace['b']} est le concurrent à surveiller de près : il ajoute "
            f"{_pl(menace['ajouts'], 'service')} et {situation}. "
            f"SGCI occupe pour sa part le {rang_taille}ᵉ rang par la taille du catalogue "
            f"({_fr(sgci.get('catalogue', 0))} services).")

    # Objectif chiffré, dérivé des seuls nombres présents — jamais d'objectif « rond » inventé.
    if actifs:
        tete = actifs[0]
        manque = (tete.get("ajouts") or 0) - (sgci.get("ajouts") or 0)
        if manque > 0:
            phrases.append(
                f"Pour égaler le rythme de {tete['b']}, il manque {_pl(manque, 'service')} "
                f"nouveaux sur la période, soit {_fr(round(manque / 2))} par semestre si "
                f"l'écart doit être comblé en un an.")
        else:
            phrases.append(
                f"Le rythme de SGCI ({sgci.get('ajouts', 0)} ajouts) est déjà au niveau du "
                f"plus actif du marché : l'enjeu se déplace vers le contenu de l'offre plutôt "
                f"que vers son volume.")

    return " ".join(phrases)


# ══════════════════════════════════════════════════════════════════════════════════════
#  Q1 — SYNTHÈSE DU MOUVEMENT PROPRE À SGCI
# ══════════════════════════════════════════════════════════════════════════════════════

def q1_synthese(n_app, n_dis, n_hausses, n_baisses, apparus, marche, segment="Particuliers"):
    """Lecture du mouvement de catalogue de SGCI face au marché."""
    marche = sorted([b for b in (marche or []) if b.get("b")],
                    key=lambda b: -(b.get("delta") or 0))
    actifs = [b for b in marche if (b.get("delta") or 0) > 0][:3]
    phrases = []

    if actifs:
        moyenne = sum(b.get("delta") or 0 for b in actifs) / len(actifs)
        position = ("au-dessus" if n_app > moyenne else
                    "au niveau" if abs(n_app - moyenne) < 1 else "en retrait")
        plus_actifs = _liste([f"{b['b']} (+{b['delta']})" for b in actifs])
        # « ces trois-là » était écrit en dur : avec un seul concurrent actif, la phrase
        # annonçait trois banques et n'en citait qu'une.
        tete_phrase = ("le concurrent le plus actif est" if len(actifs) == 1
                       else "les concurrents les plus actifs sont")
        renvoi = ("de celui-là" if len(actifs) == 1 else f"de ces {'deux' if len(actifs) == 2 else 'trois'}-là")
        phrases.append(
            f"SGCI ajoute {_pl(n_app, 'service')} et en retire {n_dis}, quand {tete_phrase} "
            f"{plus_actifs} : le rythme se situe {position} {renvoi}.")
    else:
        phrases.append(f"SGCI ajoute {_pl(n_app, 'service')} et en retire {n_dis} sur la période.")

    # Ce que les nouveautés révèlent : on compte, on ne devine pas.
    gratuits = sum(1 for r in (apparus or []) if r.get("est_gratuit"))
    if apparus:
        sections = {}
        for r in apparus:
            s = (r.get("section") or "").strip()
            if s:
                sections[s] = sections.get(s, 0) + 1
        dominante = max(sections, key=sections.get) if sections else None
        bout = ("une de ces nouveautés est gratuite" if gratuits == 1 else
                f"{_fr(gratuits)} de ces nouveautés sont gratuites" if gratuits else
                "aucune de ces nouveautés n'est gratuite")
        if dominante:
            phrases.append(
                f"Elles se concentrent sur « {dominante} » ({_pl(sections[dominante], 'service')}), "
                f"et {bout} — c'est la priorité que révèle le catalogue, indépendamment de "
                f"tout discours.")
        else:
            phrases.append(f"Parmi elles, {bout}.")

    if n_hausses or n_baisses:
        sens = ("davantage de hausses que de baisses" if n_hausses > n_baisses else
                "davantage de baisses que de hausses" if n_baisses > n_hausses else
                "autant de hausses que de baisses")
        phrases.append(
            f"Côté prix, la période compte {_pl(n_hausses, 'hausse')} et {_pl(n_baisses, 'baisse')}, "
            f"soit {sens} : le mouvement tarifaire accompagne l'évolution du catalogue.")

    if actifs:
        tete = actifs[0]
        phrases.append(
            f"Le risque à surveiller vient de {tete['b']}, dont les {tete['delta']} nouveaux "
            f"services élargissent l'écart de couverture si SGCI n'ajuste pas son rythme.")

    return " ".join(phrases)


# ══════════════════════════════════════════════════════════════════════════════════════
#  MENTION AFFICHÉE AU LECTEUR
# ══════════════════════════════════════════════════════════════════════════════════════
# On ne fait jamais passer une rédaction de secours pour l'analyse complète. Le lecteur doit
# savoir ce qu'il lit — et pourquoi le texte est plus sec que d'habitude.
MENTION = ("Rédaction automatique à partir des données — l'analyse développée reprendra "
           "au renouvellement du quota.")
