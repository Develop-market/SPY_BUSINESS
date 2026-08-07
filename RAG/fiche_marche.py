"""
fiche_marche.py — SOCLE DE FAITS PERMANENT DU CHAT (2026-07-27)
===============================================================
POURQUOI CE MODULE EXISTE (diagnostic du 2026-07-27, signalé par le directeur :
« les analyses des dashboards sont superbes MAIS le chat est nul, pas flexible ») :

Les analyses des dashboards et le chat utilisaient DEUX méthodes opposées, avec le
MÊME modèle (Groq llama-3.3-70b) et des prompts de qualité comparable :

  - Dashboard (server.py::api_approfondir, _resume_facts_strategie, api_ef_analyses_llm) :
    on DONNE d'abord au LLM tous les faits déjà calculés (7 banques, classées), PUIS on
    pose la question. Le LLM n'a plus qu'à rédiger → résultat excellent, jamais hors sujet.

  - Chat (chain.py::ask) : on reçoit la question, puis on ESSAIE DE DEVINER quels faits
    aller chercher (4 détecteurs regex + recherche vectorielle pgvector). Si la devinette
    rate — une faute de frappe suffit — le LLM reçoit des chunks au hasard du cosinus et
    rédige très bien... sur les mauvaises données.

Cas réel qui a déclenché ce module : « JE VEUX SAVOIR QELLE ST LA MEILLEUR BANQU » →
aucun détecteur ne matche (« QELLE » ≠ « quelle banque », « BANQU » ≠ « banque »), le RAG
générique part en recherche sémantique et remonte « Prêts subordonnés BICICI : 0 millions »
et « Primes liées au capital » — le LLM conclut honnêtement qu'il ne peut pas répondre.
La donnée nécessaire (ROE, coefficient d'exploitation, PNB, résultat net des 7 banques,
classés) existait pourtant, déjà calculée, à deux appels SQL de là.

CE QUE FAIT CE MODULE : produire ce socle de faits, compact et CLASSÉ, pour l'injecter
dans CHAQUE réponse du chat. Le RAG vectoriel redevient ce qu'il aurait toujours dû être —
un COMPLÉMENT pour le détail fin (une ligne tarifaire précise) — au lieu de la colonne
vertébrale. Les détecteurs déterministes restent : ils deviennent un bonus de précision,
plus un point de rupture unique.

CONTRAINTE DE TAILLE : le chat tourne sur Groq free tier (6000 tokens/minute, budget
d'entrée réel ≈ 4200 tokens après le prompt système et max_tokens — cf. chain.py garde-fou
8b). La fiche vise donc ~1000 caractères (≈300 tokens), soit moins de 8 % du budget, pour
ne JAMAIS être la cause d'un 413. C'est le meilleur rapport valeur/tokens de tout le
contexte : 7 banques × 5 indicateurs classés en 5 lignes.

Zéro invention possible : tout vient de structured_tools (même source SQL que le dashboard
EF et que les branches déterministes du chat) — les chiffres sont donc identiques à ceux
affichés à l'écran.
"""
import os
import sys
import time
import importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

config           = importlib.import_module("config")
structured_tools = importlib.import_module("structured_tools")

# Durée de vie du cache. La fiche demande ~35 requêtes SQL (5 indicateurs × 7 banques) —
# négligeable une fois, mais inutile de la refaire à chaque question du chat. 10 minutes :
# assez court pour qu'un ajout de données se voie vite, assez long pour que les questions
# d'une même session ne repaient jamais le coût. `invalider()` force le recalcul immédiat
# (appelé après un ajout de données, comme config.refresh_banque_aliases()).
_TTL_SECONDES = 600
_cache = {"texte": None, "ts": 0.0}


def invalider():
    """Force le recalcul de la fiche au prochain appel (après un ajout de données)."""
    _cache["texte"] = None
    _cache["ts"] = 0.0


def _ligne(titre: str, donnees: dict, unite: str, sens: str, diviser_par: float = 1.0) -> str:
    """Une ligne de classement compacte : 'Titre : SGCI 20,1 | BNI 18,3 | ...'.

    Le classement est fait ICI, en Python, par tri numérique exact — le LLM n'a jamais à
    déduire un ordre lui-même. Leçon du 2026-07-11 (déjà apprise dans chain.py::
    _executer_comparatif) : laissé libre, le LLM désignait la banque au coefficient
    d'exploitation le PLUS HAUT comme « la meilleure », ne saisissant pas qu'un ratio de
    coûts s'interprète à l'inverse d'un ROE. D'où le rappel explicite du sens dans le titre.
    """
    items = [(b, v.get("valeur")) for b, v in (donnees or {}).items() if v.get("valeur") is not None]
    if not items:
        return ""
    items.sort(key=lambda kv: kv[1], reverse=(sens == "max"))
    parties = []
    for banque, valeur in items:
        v = valeur / diviser_par
        txt = f"{v:,.1f}".replace(",", " ").replace(".", ",")
        # ANNÉE COLLÉE À CHAQUE VALEUR (corrigé le 2026-07-27, bug causé par ce module lui-même).
        # 1ʳᵉ version : une plage globale en fin de titre, « [2023-2025] ». Chaque banque ayant son
        # propre dernier exercice, cette plage ne disait à quelle année appartenait AUCUNE valeur.
        # Conséquence observée en test : à « Et en 2023 ? » (résultat net SGCI), le LLM a repris
        # le 101,4 Mds de la fiche — qui est la valeur 2025 — et l'a présenté comme celle de 2023.
        # Le socle de faits, censé fiabiliser, produisait une réponse fausse. Une valeur sans son
        # année n'est pas un fait : c'est un piège.
        annee = (donnees.get(banque) or {}).get("annee")
        parties.append(f"{banque} {txt}" + (f" ({annee})" if annee else ""))
    return f"{titre} : " + " | ".join(parties)


def construire(force: bool = False) -> str:
    """Construit (ou relit du cache) la fiche marché — 7 banques × 5 indicateurs, classés.

    Ne lève JAMAIS : en cas d'erreur SQL, retourne une chaîne vide. Le chat doit continuer
    à fonctionner exactement comme avant si la fiche est indisponible — ce module ne peut
    dégrader aucun chemin existant, il ne fait qu'ajouter du contexte fiable quand il peut.
    """
    if not force and _cache["texte"] is not None and (time.time() - _cache["ts"]) < _TTL_SECONDES:
        return _cache["texte"]

    try:
        lignes = [
            _ligne("ROE % (PLUS HAUT = plus rentable)",
                   structured_tools.comparer_roe("AN3"), "%", "max"),
            _ligne("Coefficient d'exploitation % (PLUS BAS = plus efficient)",
                   structured_tools.comparer_coefficient_exploitation("AN3"), "%", "min"),
            _ligne("PNB Mds FCFA (PLUS HAUT = plus gros)",
                   structured_tools.comparer_ef("pnb", "AN3"), "Mds", "max", 1000),
            _ligne("Résultat net Mds FCFA (PLUS HAUT = mieux)",
                   structured_tools.comparer_ef("résultat net", "AN3"), "Mds", "max", 1000),
            _ligne("Total bilan Mds FCFA (taille)",
                   structured_tools.comparer_ef("total bilan", "AN3"), "Mds", "max", 1000),
        ]
        lignes = [l for l in lignes if l]
        if not lignes:
            _cache["texte"], _cache["ts"] = "", time.time()
            return ""

        texte = (
            "═════ FICHE MARCHÉ — BANQUES IVOIRIENNES (source SQL exacte, dernier exercice "
            "disponible par banque, DÉJÀ CLASSÉ du meilleur au moins bon) ═════\n"
            + "\n".join(lignes)
            + "\n[Ces chiffres sont exacts et suffisent à répondre à toute question de CLASSEMENT, "
              "de PERFORMANCE ou de COMPARAISON entre banques. Utilise-les en priorité, ne les "
              "recalcule pas, ne les complète pas de mémoire.\n"
              " ATTENTION — chaque valeur vaut POUR SON ANNÉE, indiquée entre parenthèses juste "
              "après elle, et les banques n'ont pas toutes le même dernier exercice. Si la "
              "question porte sur une AUTRE année que celle indiquée, cette fiche ne répond PAS : "
              "cherche la valeur de l'année demandée dans les sources détaillées ci-dessous, et "
              "si elle n'y est pas, dis-le au lieu de reprendre le chiffre d'une autre année.]"
        )
        _cache["texte"], _cache["ts"] = texte, time.time()
        return texte
    except Exception as e:
        print(f"  [FICHE MARCHÉ] Indisponible ({e}) — le chat continue sans elle.")
        _cache["texte"], _cache["ts"] = "", time.time()
        return ""


def classement_multicritere() -> str:
    """Réponse déterministe à « quelle est la meilleure banque ? » — la question la plus
    naturelle que pose un dirigeant, et justement celle qui n'avait AUCUNE route avant le
    2026-07-27 (_detect_comparatif exige un indicateur nommé : PNB, ROE... ; sans ça, la
    question tombait dans le RAG générique, structurellement incapable d'y répondre puisque
    « la meilleure banque » n'est pas une information à retrouver dans un document mais une
    synthèse multicritère).

    Méthode : score normalisé de 0 à 100 par critère (100 = 1er du critère, 0 = dernier),
    puis moyenne des critères disponibles pour chaque banque. Les 4 critères ont un poids
    ÉGAL — choix arbitraire mais explicité dans le texte pour être contestable.

    POURQUOI UN SCORE NORMALISÉ ET NON UNE MOYENNE DE RANGS (corrigé le 2026-07-27, première
    version fausse) : les critères ne couvrent pas tous le même nombre de banques (le
    coefficient d'exploitation manque pour ECOBANK, faute de ligne « frais généraux » dans
    ses états financiers). Une moyenne de rangs bruts est alors incomparable d'une banque à
    l'autre — être 4e sur 4 (dernier) donnait un meilleur score qu'être 5e sur 7 (milieu de
    tableau). La normalisation ramène chaque critère sur la même échelle 0-100, quel que
    soit le nombre de banques qu'il couvre.

    Les valeurs brutes ne sont volontairement PAS moyennées entre elles : additionner des %
    (ROE) et des milliards FCFA (PNB) n'a aucun sens. Le rang normalisé est le seul agrégat
    honnête sans inventer un taux de conversion entre ces unités.
    """
    # Le libellé de chaque critère PORTE son sens de lecture. Sans ça (constaté en test le
    # 2026-07-27), le LLM voyait « efficience : SIB > SGCI > ... », citait correctement SIB en
    # tête, mais la justifiait à l'envers : « SIB présente le coefficient d'exploitation le plus
    # ÉLEVÉ » alors que c'est le plus BAS qui rend efficient. Une liste triée ne dit pas selon
    # quel sens elle l'a été — il faut l'écrire.
    criteres = [
        ("rentabilité — ROE, plus HAUT = meilleur",
         structured_tools.comparer_roe("AN3"), "max"),
        ("efficience — coefficient d'exploitation, plus BAS = meilleur (coûts/PNB)",
         structured_tools.comparer_coefficient_exploitation("AN3"), "min"),
        ("taille — PNB, plus HAUT = meilleur",
         structured_tools.comparer_ef("pnb", "AN3"), "max"),
        ("résultat net — plus HAUT = meilleur",
         structured_tools.comparer_ef("résultat net", "AN3"), "max"),
    ]
    scores = {}
    detail = []
    for nom, donnees, sens in criteres:
        items = [(b, v.get("valeur")) for b, v in (donnees or {}).items() if v.get("valeur") is not None]
        if len(items) < 2:
            continue
        items.sort(key=lambda kv: kv[1], reverse=(sens == "max"))
        detail.append(f"  {nom} [{len(items)} banques] : "
                      + " puis ".join(b for b, _ in items)
                      + "  (le 1er cité est LE MEILLEUR sur ce critère)")
        n = len(items)
        for position, (banque, _) in enumerate(items):
            scores.setdefault(banque, []).append(100.0 * (n - 1 - position) / (n - 1))

    if not scores:
        return ""

    n_criteres = len(detail)
    # Une banque évaluée sur un seul critère n'est pas comparable à une banque évaluée sur
    # 4 : on l'affiche à part plutôt que de la mêler au classement (ni de la cacher).
    seuil = max(2, n_criteres - 1)
    classables = {b: s for b, s in scores.items() if len(s) >= seuil}
    partiels   = {b: s for b, s in scores.items() if len(s) < seuil}
    if not classables:
        classables, partiels = scores, {}

    moyennes = sorted(((b, sum(s) / len(s), len(s)) for b, s in classables.items()),
                      key=lambda t: -t[1])
    lignes = [f"  {i}. {b} — score {m:.0f}/100 (sur {c} critère(s))"
              for i, (b, m, c) in enumerate(moyennes, 1)]

    txt = (
        f"CLASSEMENT MULTICRITÈRE DES BANQUES (calcul SQL déterministe, {n_criteres} critères "
        "de POIDS ÉGAL : rentabilité, efficience, taille, résultat net. Score 100 = 1er du "
        "critère, 0 = dernier ; moyenne des critères disponibles. LE PREMIER DE LA LISTE EST "
        "LA RÉPONSE) :\n"
        + "\n".join(lignes)
        + "\n\nClassement détaillé par critère :\n" + "\n".join(detail)
    )
    if partiels:
        # Formulation soignée (corrigée le 2026-07-27 après un test en direct) : la 1ʳᵉ version
        # disait seulement « trop peu de données », et le LLM en a conclu que ces banques
        # étaient invalides PARTOUT — il a écrit « pour l'efficience, SGCI se distingue » alors
        # que la ligne détaillée juste au-dessus classe SIB 1re sur ce critère. Une exclusion
        # du score GLOBAL n'invalide pas les critères où la banque est bel et bien mesurée :
        # il faut le dire explicitement, sinon le LLM sur-généralise l'avertissement.
        txt += ("\n\n(Écartées du SCORE GLOBAL seulement, faute d'être mesurées sur assez de "
                "critères : "
                + ", ".join(f"{b} ({len(s)} critère(s))" for b, s in sorted(partiels.items()))
                + ". ATTENTION : leurs positions dans les classements par critère ci-dessus "
                  "restent EXACTES et doivent être citées normalement.)")
    txt += ("\n\n[Il n'existe pas de « meilleure banque » dans l'absolu : le classement dépend "
            "des critères retenus et de leur pondération. Présente le podium, puis précise que "
            "le choix dépend de l'objectif (rentabilité, taille, efficience, prix).]")
    return txt


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    f = construire(force=True)
    print(f)
    print(f"\n>>> {len(f)} caractères (~{len(f)//3.3:.0f} tokens)\n")
    print("─" * 70)
    print(classement_multicritere())
