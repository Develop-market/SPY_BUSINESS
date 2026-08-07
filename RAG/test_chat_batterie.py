"""
test_chat_batterie.py — BATTERIE DE TEST DU CHAT (2026-07-27)
=============================================================
Créé à la demande du directeur : « faisons tout notre possible pour tester et retester le chat
jusqu'à atteindre la perfection ». Jusqu'ici, chaque bug du chat était trouvé À LA MAIN, en
tapant une question au hasard — d'où des régressions invisibles et des corrections au cas par
cas. Cette batterie rejoue un jeu de questions représentatives et vérifie AUTOMATIQUEMENT ce
qui peut l'être, pour que « ça marche » cesse d'être une impression.

CE QU'ON VÉRIFIE AUTOMATIQUEMENT (`attendus`) :
  - `contient`      : la réponse doit contenir CHACUN de ces fragments (insensible casse/accents)
  - `contient_un`   : au moins UN de ces fragments
  - `interdit`      : aucun de ces fragments (ex. dire "non disponible" sur une donnée existante)
  - `min_chars`     : longueur plancher (une réponse d'une ligne à une question d'analyse = creux)

CE QU'ON NE PEUT PAS AUTOMATISER : la pertinence rédactionnelle. D'où le rapport Markdown
complet, à relire à l'œil — c'est là qu'on repère les réponses « bêtes » que les assertions
laissent passer.

USAGE :
    python test_chat_batterie.py                 # tout
    python test_chat_batterie.py --seulement cb  # une famille (cb/ef/regl/robustesse/suivi)
    python test_chat_batterie.py --rapport chemin.md

NOTE QUOTA : chaque question consomme des tokens Groq (budget partagé ~100 000/jour sur les 12
clés, qui appartiennent à la même organisation). La batterie complète ≈ 25 appels. En cas de
mur de quota, le script le signale explicitement au lieu de compter l'échec comme un défaut de
qualité — un test rouge pour cause de quota n'est pas une régression du chat.
"""
import argparse
import importlib
import os
import re
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

chain  = importlib.import_module("chain")
memory = importlib.import_module("memory")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t)


# ═══════════════════════════════════════════════════════════
#  JEU DE TEST
# ═══════════════════════════════════════════════════════════
# `suite` : les questions d'une même suite partagent une mémoire (pour tester les suivis).
# Une question sans `suite` part d'une mémoire vierge — indispensable pour que l'ordre des
# tests n'influence jamais leur résultat (leçon de la pollution par « bonjour »).

CAS = [
    # ── ROBUSTESSE : salutations, fautes de frappe, hors sujet ────────────────
    dict(famille="robustesse", q="bjr",
         attendus=dict(contient_un=["bonjour", "spybusiness"], interdit=["hors du perimetre", "sort du perimetre"])),
    dict(famille="robustesse", q="coucou",
         attendus=dict(contient_un=["bonjour", "spybusiness"], interdit=["sort du perimetre"])),
    dict(famille="robustesse", q="JE VEUX SAVOIR QELLE ST LA MEILLEUR BANQU",
         attendus=dict(contient_un=["sgci", "ecobank"], interdit=["sort du perimetre", "prets subordonnes"], min_chars=200)),
    dict(famille="robustesse", q="kel est le pnb de la SGCI ?",
         attendus=dict(contient=["sgci"], contient_un=["pnb", "produit net"], interdit=["sort du perimetre"])),
    dict(famille="robustesse", q="Quelle est la capitale de la Côte d'Ivoire ?",
         attendus=dict(contient_un=["perimetre", "ne peux pas"], interdit=["abidjan", "yamoussoukro"])),

    # ── CONDITIONS TARIFAIRES ─────────────────────────────────────────────────
    # Vérité terrain SQL (2026-07-27) : SGCI 2024 S1 particuliers n'a PAS de frais de tenue de
    # compte courant standard ; les 3 lignes "tenue" sont livret d'épargne (Gratuit),
    # SUCCESSIONS (2 350) et conservation de titres. Le piège : répondre "2 350 FCFA" sec.
    dict(famille="cb", q="Quels sont les frais de tenue de compte SGCI pour les particuliers en 2024 S1 ?",
         attendus=dict(contient_un=["succession", "livret", "epargne"], min_chars=150),
         note="Ne doit PAS présenter 2 350 comme le tarif courant : c'est la ligne SUCCESSIONS."),
    # BNI facture au REVENU : la réponse doit montrer les tranches, pas un chiffre unique.
    dict(famille="cb", q="Quels sont les frais de tenue de compte BNI pour les particuliers en 2024 S1 ?",
         attendus=dict(contient=["200", "700"], contient_un=["revenu", "tranche"], min_chars=150),
         note="BNI tarifie par TRANCHE DE REVENU (4 tranches) — un montant unique serait faux. "
              "Vérité SQL : <200.000→1.000 ; 200.000-699.999→2.000 ; 700.000-1.999.999→3.000 ; +."),
    # ECOBANK facture par OFFRE : la réponse doit nommer plusieurs offres, pas une seule.
    dict(famille="cb", q="Frais de tenue de compte ECOBANK particuliers 2024 S1 ?",
         attendus=dict(contient=["advantage", "classic"], contient_un=["premier", "evolution"], min_chars=150),
         note="ECOBANK tarifie par offre commerciale nommée (13 offres en base)."),
    dict(famille="cb", q="Compare les frais de tenue de compte entre SGCI et ECOBANK",
         attendus=dict(contient=["sgci", "ecobank"], min_chars=200)),

    # ── ÉTATS FINANCIERS ──────────────────────────────────────────────────────
    dict(famille="ef", q="Quel est le résultat net de SGCI en 2024 ?",
         attendus=dict(contient=["sgci"], contient_un=["millions", "fcfa"], interdit=["non disponible"])),
    dict(famille="ef", q="Quelle banque a le meilleur ROE ?",
         attendus=dict(contient_un=["bicici"], min_chars=100),
         note="Vérité SQL AN3 : BICICI 30,3 % est en tête."),
    dict(famille="ef", q="Quelle banque est la plus efficiente opérationnellement ?",
         attendus=dict(contient=["sib"], min_chars=100),
         note="Coefficient d'exploitation le plus BAS = SIB 38,5 %. Piège du sens inversé."),
    dict(famille="ef", q="Quel est le PNB de BNI en 2023 ?",
         attendus=dict(contient=["bni"], interdit=["non disponible", "donnees insuffisantes"])),
    dict(famille="ef", q="Compare le PNB entre SGCI et BICICI",
         attendus=dict(contient=["sgci", "bicici"], min_chars=120)),
    dict(famille="ef", q="La BICICI est-elle solide et compétitive ?",
         attendus=dict(contient=["bicici"], min_chars=300, interdit=["impossible de conclure"]),
         note="Doit s'appuyer sur la fiche de synthèse classée, pas se dire incapable de juger."),

    # ── RÉGLEMENTATION ────────────────────────────────────────────────────────
    dict(famille="regl", q="Que dit la réglementation BCEAO sur les taux d'intérêt ?",
         attendus=dict(min_chars=150, contient_un=["bceao", "uemoa", "instruction", "article"])),

    # ── SUIVIS (mémoire conversationnelle) ────────────────────────────────────
    dict(famille="suivi", suite="A", q="bjr", attendus=dict(contient_un=["bonjour"])),
    dict(famille="suivi", suite="A", q="Quels sont les frais de tenue de compte BNI pour les particuliers en 2024 S1 ?",
         attendus=dict(contient_un=["revenu", "tenue"])),
    dict(famille="suivi", suite="A", q="Et pour ECOBANK ?",
         attendus=dict(contient=["ecobank"], contient_un=["tenue", "offre", "advantage"],
                       interdit=["sort du perimetre",
                                 # Le pire défaut constaté : nier une donnée affichée juste avant.
                                 "ne sont pas disponibles dans le contexte"]),
         note="Suivi : doit garder le sujet 'tenue de compte' et changer de banque, avec les "
              "MÊMES données que la question posée directement."),
    dict(famille="suivi", suite="B", q="Quel est le résultat net de SGCI en 2024 ?",
         attendus=dict(contient=["sgci", "101 228"]),
         note="Vérité SQL : 101 228 millions FCFA."),
    # ── DIVERS : zones non couvertes par les familles ci-dessus ───────────────
    # Ajoutées après la 3ᵉ passe (2026-07-27) : les familles précédentes tournaient toutes au
    # vert, il fallait sonder AILLEURS pour continuer à trouver des défauts plutôt que de
    # confirmer indéfiniment ce qui marche déjà.
    dict(famille="divers", q="Combien coûte un virement dans l'UEMOA chez SGCI pour une entreprise ?",
         attendus=dict(contient=["sgci"], contient_un=["virement", "fcfa", "gratuit"], min_chars=100),
         note="Segment ENTREPRISES + service virement : filtre de cible peu testé."),
    dict(famille="divers", q="Quelles banques offrent la carte Visa Gold et à quel prix ?",
         attendus=dict(contient_un=["gold", "visa"], min_chars=150),
         note="Service carte, plusieurs banques, sans filtre de période."),
    dict(famille="divers", q="Comment a évolué le PNB de SGCI ces dernières années ?",
         attendus=dict(contient=["253 286", "263 207", "276 048"], min_chars=200,
                       interdit=["non disponible", "276 000"]),
         note="Évolution : série SQL exacte 2023→2025. Pièges constatés le 2026-07-27 — une "
              "année tirée d'une colonne N-1 (2021), des années réelles déclarées manquantes, "
              "et un arrondi (276 000 au lieu de 276 048)."),
    dict(famille="divers", q="Quelle banque a le total bilan le plus élevé ?",
         attendus=dict(contient=["nsia"], min_chars=80),
         note="Vérité SQL : NSIA 3 073,1 Mds. Indicateur ajouté tardivement aux EF_PATTERNS."),
    dict(famille="divers", q="frais de cloture de compte bici",
         attendus=dict(interdit=["sort du perimetre"], min_chars=80),
         note="Tout en minuscules, sans accent, alias tronqué « bici » et service clôture."),
    dict(famille="divers", q="C'est quoi le coefficient d'exploitation ?",
         attendus=dict(contient_un=["charges", "pnb", "cout", "efficience", "exploitation"], min_chars=100),
         note="Question de DÉFINITION, pas de donnée — ne doit pas être rejetée hors périmètre."),

    dict(famille="suivi", suite="B", q="Et en 2023 ?",
         attendus=dict(contient=["97 230"],
                       interdit=["sort du perimetre", "n'ai pas reussi a rattacher", "101,4", "101 352"]),
         note="Vérité SQL 2023 : 97 230 M FCFA. Piège : la fiche marché porte le RN 2025 "
              "(101 352 M ≈ 101,4 Mds) — le reprendre pour 2023 est l'erreur à ne pas commettre."),
]


# ═══════════════════════════════════════════════════════════
#  EXÉCUTION
# ═══════════════════════════════════════════════════════════

_MARQUEURS_QUOTA = ("erreur apres", "rate limit", "quota", "429", "413",
                    "nombre maximum de tentatives")


def _verifier(reponse: str, attendus: dict) -> list:
    """Retourne la liste des échecs (vide = tout bon)."""
    r = _norm(reponse)
    echecs = []
    for frag in attendus.get("contient", []):
        if _norm(frag) not in r:
            echecs.append(f"manque « {frag} »")
    un = attendus.get("contient_un", [])
    if un and not any(_norm(f) in r for f in un):
        echecs.append("aucun de « " + " / ".join(un) + " »")
    for frag in attendus.get("interdit", []):
        if _norm(frag) in r:
            echecs.append(f"INTERDIT présent : « {frag} »")
    mini = attendus.get("min_chars")
    if mini and len(reponse.strip()) < mini:
        echecs.append(f"trop court ({len(reponse.strip())} < {mini} chars)")
    return echecs


def lancer(familles=None, rapport_path=None):
    print("=" * 78)
    print("  BATTERIE DE TEST — CHAT SPYBUSINESS")
    print("=" * 78)
    ch = chain.init_chain()
    memoires = {}

    cas = [c for c in CAS if not familles or c["famille"] in familles]
    resultats = []

    for i, c in enumerate(cas, 1):
        suite = c.get("suite")
        # Mémoire partagée au sein d'une suite, vierge sinon : l'ordre des tests ne doit
        # jamais pouvoir influencer un résultat.
        if suite:
            memoires.setdefault(suite, memory.ConversationMemory())
            ch["memory"] = memoires[suite]
        else:
            ch["memory"] = memory.ConversationMemory()

        print(f"\n[{i}/{len(cas)}] ({c['famille']}) {c['q'][:70]}")
        t0 = time.time()
        try:
            reponse = chain.ask(ch, c["q"])
        except Exception as e:
            reponse = f"EXCEPTION : {type(e).__name__} : {e}"
        duree = time.time() - t0

        quota = any(m in _norm(reponse) for m in _MARQUEURS_QUOTA)
        echecs = [] if quota else _verifier(reponse, c.get("attendus", {}))
        statut = "QUOTA" if quota else ("OK" if not echecs else "ÉCHEC")
        print(f"      → {statut} ({duree:.1f}s, {len(reponse)} chars)"
              + ("" if not echecs else "  :: " + " | ".join(echecs)))

        resultats.append(dict(**c, reponse=reponse, echecs=echecs, statut=statut, duree=duree))

    # ── Bilan ────────────────────────────────────────────────────────────────
    n_ok    = sum(1 for r in resultats if r["statut"] == "OK")
    n_ko    = sum(1 for r in resultats if r["statut"] == "ÉCHEC")
    n_quota = sum(1 for r in resultats if r["statut"] == "QUOTA")
    print("\n" + "=" * 78)
    print(f"  BILAN : {n_ok} OK · {n_ko} ÉCHEC · {n_quota} quota (sur {len(resultats)})")
    print("=" * 78)
    for r in resultats:
        if r["statut"] == "ÉCHEC":
            print(f"  ÉCHEC ({r['famille']}) {r['q'][:60]}")
            for e in r["echecs"]:
                print(f"         - {e}")

    if rapport_path:
        _ecrire_rapport(resultats, rapport_path, n_ok, n_ko, n_quota)
        print(f"\n  Rapport détaillé (à relire à l'œil) : {rapport_path}")

    return resultats


def _ecrire_rapport(resultats, path, n_ok, n_ko, n_quota):
    lignes = [
        "# Batterie de test — chat SpyBusiness",
        f"\n**{n_ok} OK · {n_ko} ÉCHEC · {n_quota} quota** sur {len(resultats)} cas — "
        f"{time.strftime('%Y-%m-%d %H:%M')}\n",
        "> Les assertions ne jugent que le vérifiable. Relire les réponses ci-dessous pour "
        "repérer les réponses creuses, vagues ou hors sujet qu'aucune assertion n'attrape.\n",
    ]
    for r in resultats:
        icone = {"OK": "✅", "ÉCHEC": "❌", "QUOTA": "⏳"}[r["statut"]]
        lignes.append(f"\n---\n\n## {icone} [{r['famille']}] {r['q']}\n")
        if r.get("note"):
            lignes.append(f"*Attendu : {r['note']}*\n")
        if r["echecs"]:
            lignes.append("**Échecs :** " + " | ".join(r["echecs"]) + "\n")
        lignes.append(f"*{r['duree']:.1f}s · {len(r['reponse'])} caractères*\n")
        lignes.append("```\n" + r["reponse"].strip() + "\n```\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lignes))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seulement", help="familles séparées par des virgules (cb,ef,regl,robustesse,suivi)")
    ap.add_argument("--rapport", default=None, help="chemin du rapport Markdown")
    args = ap.parse_args()
    familles = [f.strip() for f in args.seulement.split(",")] if args.seulement else None
    res = lancer(familles, args.rapport)
    sys.exit(1 if any(r["statut"] == "ÉCHEC" for r in res) else 0)
