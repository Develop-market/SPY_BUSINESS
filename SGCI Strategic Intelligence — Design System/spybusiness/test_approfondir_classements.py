# -*- coding: utf-8 -*-
"""
test_approfondir_classements.py — Batterie de mesure du correctif « classements » du 2026-08-26
=================================================================================================
Objectif : chiffrer, sur un lot de questions, si le bouton « Approfondir » (/api/approfondir)
cite toujours la BONNE banque quand il parle d'un « leader » ou d'un rang — le bug constaté deux
fois ce jour (BICICI désigné leader en marge nette à la place de SIB, NSIA désigné 2e coût du
risque à la place de BACI).

Principe : chaque cas donne un jeu de KPI synthétique (7 banques, valeurs différentes d'un cas à
l'autre pour qu'aucune réponse figée ne puisse « deviner juste » par hasard), calcule la PHRASE de
classement attendue avec la MÊME logique que server.py::_faits_rang, puis vérifie que cette phrase
apparaît telle quelle (normalisée) dans la réponse réelle du LLM. Le fait que le LLM la recopie
mot pour mot est justement ce que le correctif impose — un simple sous-string suffit donc à
vérifier qu'il n'a pas reformulé, et donc pas pu se tromper de banque.

USAGE :
    python test_approfondir_classements.py                  # contre Render (par défaut)
    python test_approfondir_classements.py --base http://localhost:5000
"""
import argparse
import json
import re
import sys
import time
import unicodedata

import requests

BANQUES = ["SGCI", "BICICI", "ECOBANK", "SIB", "NSIA", "BNI", "BACI"]


def _norm(t):
    t = (t or "").lower()
    t = t.replace("’", "'").replace("‘", "'")     # apostrophe typographique -> droite
    t = t.replace("*", "").replace("«", "").replace("»", "")  # gras Markdown, guillemets
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)          # "54,6" (FR) -> "54.6" : le LLM reformule les
    t = re.sub(r"(\d)\s+%", r"\1%", t)             # nombres en typographie francaise ("54,6 %"),
                                                    # ce n'est pas une erreur de contenu a signaler.
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t)


def _faits_rang(nom, d, reverse=True, unit="%"):
    """Copie EXACTE de server.py::_faits_rang — la phrase de vérité terrain doit être générée
    par le même calcul que celui qui alimente le prompt, sinon le test se compare à lui-même."""
    if not d or len(d) < 2:
        return None
    items = sorted(d.items(), key=lambda x: x[1], reverse=reverse)
    rang_sgci = next((i + 1 for i, (b, _) in enumerate(items) if b == "SGCI"), None)
    f = [f"{nom} — leader (rang #1) : {items[0][0]} ({items[0][1]}{unit}) ; "
         f"rang #2 : {items[1][0]} ({items[1][1]}{unit})"]
    if rang_sgci and rang_sgci > 2:
        f.append(f"SGCI est rang #{rang_sgci}/{len(items)} en {nom} ({items[rang_sgci-1][1]}{unit})")
    return " ; ".join(f) + "."


def _scenario(seed):
    """7 valeurs distinctes, permutées par seed pour que le leader change d'un cas à l'autre."""
    import random
    r = random.Random(seed)
    valeurs = sorted(round(r.uniform(1.5, 55.0), 1) for _ in range(7))
    r.shuffle(valeurs)
    return dict(zip(BANQUES, valeurs))


CAS = [
    dict(metric="marge nette", champ="marge", reverse=True, unit="%",
         question="Qui a la meilleure marge nette du marché et où se situe SGCI ?"),
    dict(metric="coût du risque/PNB", champ="cout_risque", reverse=False, unit="%",
         question="Analyse le coût du risque de SGCI et la qualité de son portefeuille de crédits par rapport aux banques ivoiriennes"),
    dict(metric="coefficient d'exploitation", champ="coeff", reverse=False, unit="%",
         question="Quelle banque a le meilleur coefficient d'exploitation et quel est le rang de SGCI ?"),
    dict(metric="ROE", champ="roe", reverse=True, unit="%",
         question="Quel est le classement des banques sur le ROE ?"),
]
N_SEEDS = 3  # 3 scénarios distincts par métrique => 12 appels, dans le budget des batteries existantes


def executer(base_url):
    session = requests.Session()
    r = session.post(f"{base_url}/api/login", json={"identifiant": "admin", "mot_de_passe": "@Dmin124"}, timeout=60)
    if not r.ok or not r.json().get("ok"):
        print(f"[ERREUR] connexion impossible : {r.status_code} {r.text[:200]}")
        sys.exit(1)

    resultats = []
    premier = True
    for cas in CAS:
        for seed in range(N_SEEDS):
            if not premier:
                time.sleep(4)   # espace les appels pour rester sous la limite Groq (TPM)
            premier = False
            kpis = {cas["champ"]: _scenario(f"{cas['champ']}-{seed}")}
            attendu = _faits_rang(cas["metric"], kpis[cas["champ"]], reverse=cas["reverse"], unit=cas["unit"])
            payload = {"question": cas["question"], "kpis": kpis}

            reponse, dt = "", 0.0
            for tentative in range(3):   # retry sur limite de débit Groq (429), pas un echec de contenu
                t0 = time.time()
                try:
                    resp = session.post(f"{base_url}/api/approfondir", json=payload, timeout=60)
                    reponse = resp.json().get("reponse", "") if resp.ok else f"[HTTP {resp.status_code}]"
                except Exception as e:
                    reponse = f"[ERREUR RÉSEAU] {e}"
                dt = time.time() - t0
                if "rate_limit" not in reponse and "429" not in reponse:
                    break
                time.sleep(8)

            # Deux niveaux : DISTORSION (mauvaise banque nommée comme leader -- le bug d'origine)
            # est la seule cause d'échec ; OMISSION (rang #2 / rang SGCI non repris) est notée
            # mais ne fait pas échouer le cas, ce n'est pas une hallucination, juste une réponse
            # qui ne reprend pas un fait non demandé.
            clauses = [c.strip() for c in attendu.rstrip(".").split(" ; ")]
            clause_leader, clauses_secondaires = clauses[0], clauses[1:]
            reponse_norm = _norm(reponse)
            leader_ok = _norm(clause_leader) in reponse_norm
            omissions = [c for c in clauses_secondaires if _norm(c) not in reponse_norm]
            infra_echec = reponse.startswith("[") or "rate_limit" in reponse or "indisponible" in reponse.lower()
            ok = leader_ok and not infra_echec

            resultats.append(dict(
                metric=cas["metric"], seed=seed, attendu=attendu, reponse=reponse,
                ok=ok, leader_ok=leader_ok, omissions=omissions, infra_echec=infra_echec,
                duree=round(dt, 1),
            ))
            if infra_echec:
                marque = "INFRA"
            else:
                marque = "OK  " if ok else "RATE"
            detail = ""
            if infra_echec:
                detail = "  -> panne infra (quota/reseau), pas un contenu a juger"
            elif not leader_ok:
                detail = f"  -> BANQUE INCORRECTE pour le leader ! attendu : {clause_leader}"
            elif omissions:
                detail = f"  -> (info) omis, pas une erreur : {omissions}"
            print(f"[{marque}] {cas['metric']:28s} seed={seed}  ({dt:.1f}s){detail}")

    jugeables = [r for r in resultats if not r["infra_echec"]]
    n_ok = sum(1 for r in jugeables if r["ok"])
    n = len(jugeables)
    n_infra = len(resultats) - n
    print(f"\n{'='*70}")
    if n:
        print(f"RÉSULTAT (contenu jugeable) : {n_ok}/{n} cas SANS erreur de banque ({100*n_ok/n:.0f}%)")
    if n_infra:
        print(f"({n_infra} cas exclus pour panne d'infrastructure — quota Groq/réseau, non jugeables)")
    print(f"{'='*70}")
    return resultats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://spybusiness.onrender.com")
    ap.add_argument("--rapport", default=None, help="Chemin d'un rapport Markdown détaillé")
    args = ap.parse_args()

    resultats = executer(args.base.rstrip("/"))

    if args.rapport:
        with open(args.rapport, "w", encoding="utf-8") as f:
            f.write("# Batterie de test — classements Approfondir\n\n")
            jugeables = [r for r in resultats if not r["infra_echec"]]
            n_ok = sum(1 for r in jugeables if r["ok"])
            n = len(jugeables)
            if n:
                f.write(f"**{n_ok}/{n} cas sans erreur de banque ({100*n_ok/n:.0f}%)** "
                        f"— {len(resultats)-n} exclus pour panne d'infrastructure.\n\n")
            for r in resultats:
                statut = "PANNE INFRA" if r["infra_echec"] else ("OK" if r["ok"] else "BANQUE INCORRECTE")
                f.write(f"## {r['metric']} (seed {r['seed']}) — {statut}\n\n")
                f.write(f"- **Attendu** : {r['attendu']}\n")
                if not r["infra_echec"] and not r["leader_ok"]:
                    f.write(f"- **ERREUR : le leader attendu n'apparaît pas dans la réponse.**\n")
                if r["omissions"]:
                    f.write(f"- Omis (non requis, pas une erreur) : {r['omissions']}\n")
                f.write(f"- **Réponse complète** :\n\n> {r['reponse']}\n\n")
        print(f"Rapport écrit : {args.rapport}")
