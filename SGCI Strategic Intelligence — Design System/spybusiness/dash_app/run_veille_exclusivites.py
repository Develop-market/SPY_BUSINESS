# -*- coding: utf-8 -*-
"""
run_veille_exclusivites.py — AGENT DE VEILLE des EXCLUSIVITÉS CB (dynamique & reproductible).
==============================================================================================
Problème : « exclusif » est déduit des GRILLES tarifaires → faux positifs (« retrait sans carte »
que d'autres banques offrent). Cet agent VA CHERCHER SUR LE WEB si les concurrents proposent
chaque service candidat, puis CLASSE le verdict et l'écrit (sourcé) dans exclusivites_validation.json.

REPRODUCTIBLE : relancer ce script ré-interroge le web et régénère les verdicts (mêmes sources, daté).
DYNAMIQUE : à chaque actualisation des données CB, relancer met à jour les services NOUVEAUX/inconnus.
IDEMPOTENT : ne re-valide pas un service déjà présent dans `services_auto` (sauf --force).

Clés (.env) — au choix :
  • TAVILY_API_KEY=...    moteur de recherche GRATUIT (1000/mois) — recommandé (+ Groq déjà présent pour classer)
  • OPENAI_API_KEY=...    fait recherche WEB *et* classification (Responses API web_search) — PAYANT
  (Sans aucune clé de recherche → mode LISTE : affiche les services à valider, n'écrit rien.)

Usage :
  python run_veille_exclusivites.py                      # toutes les banques
  python run_veille_exclusivites.py --banques SGCI,NSIA  # ciblé
  python run_veille_exclusivites.py --dry-run            # liste seulement (n'écrit pas)
  python run_veille_exclusivites.py --limit 10           # borne le nombre de validations
"""
import os, sys, json, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
VALID_PATH = os.path.join(HERE, "exclusivites_validation.json")


def _charger_banks():
    """Toutes les banques, chargées depuis db.BANKS (dynamique, table `banques`) — filet de
    sécurité figé seulement si la BD est indisponible."""
    try:
        import db as _db
        if _db.BANKS:
            return list(_db.BANKS)
    except Exception:
        pass
    return ["SGCI", "BICICI", "NSIA", "ECOBANK", "SIB", "BNI", "BACI"]


BANKS = _charger_banks()


def _load_env():
    try:
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv(usecwd=True))
        load_dotenv(os.path.abspath(os.path.join(HERE, "..", "..", "..", ".env")))
    except Exception:
        pass


# ── RECHERCHE WEB (provider-agnostic : Tavily, sinon OpenAI) ────────────────────────────────
def _search(query, k=5):
    tav = os.getenv("TAVILY_API_KEY")
    if tav:
        try:
            import requests
            r = requests.post("https://api.tavily.com/search",
                              json={"api_key": tav, "query": query, "max_results": k,
                                    "search_depth": "basic"}, timeout=25)
            if r.ok:
                return [{"title": x.get("title", ""), "url": x.get("url", ""),
                         "content": (x.get("content") or "")[:400]} for x in r.json().get("results", [])]
            print("   [tavily]", r.status_code, r.text[:80])
        except Exception as e:
            print("   [tavily err]", str(e)[:90])
    oai = os.getenv("OPENAI_API_KEY")
    if oai:
        try:
            from openai import OpenAI
            resp = OpenAI(api_key=oai).responses.create(
                model="gpt-4o-mini", tools=[{"type": "web_search_preview"}],
                input=f"Recherche web et cite tes sources : {query}")
            txt = getattr(resp, "output_text", "") or ""
            urls = set()
            for item in (getattr(resp, "output", None) or []):
                for c in (getattr(item, "content", None) or []):
                    for a in (getattr(c, "annotations", None) or []):
                        u = getattr(a, "url", None) or (a.get("url") if isinstance(a, dict) else None)
                        if u:
                            urls.add(u)
            return [{"title": "openai", "url": u, "content": txt[:600]} for u in (urls or [""])]
        except Exception as e:
            print("   [openai err]", str(e)[:120])
    return None


# ── CLASSIFICATION (Groq, déjà configuré) ───────────────────────────────────────────────────
def _classify(libelle, snippets):
    keys = [k for k in [os.getenv("GROQ_API_KEY", "")] +
            [os.getenv(f"GROQ_API_KEY_{i}", "") for i in range(2, 13)] if k]
    if not keys:
        return None
    ctx = "\n".join(f"- {s.get('title','')} ({s.get('url','')}) : {s.get('content','')}" for s in snippets[:5])
    prompt = (
        f"Service bancaire (Côte d'Ivoire) : « {libelle} ».\n"
        f"Extraits web réels :\n{ctx}\n\n"
        "Des banques CONCURRENTES ivoiriennes (SGCI, BICICI, NSIA, Ecobank, SIB, BNI, BACI) proposent-elles "
        "ce service, même sous un autre nom ? Réponds en JSON STRICT :\n"
        '{"verdict":"partage|differenciant|non_contredit","concurrents":["..."],"note":"1 phrase sourcée"}\n'
        "• partage = ≥1 concurrent l'offre (liste-les). • differenciant = NOM de marque/produit propre à une banque "
        "(la fonction existe ailleurs). • non_contredit = aucune preuve web qu'un concurrent l'offre. JSON uniquement."
    )
    from groq import Groq
    for k in keys:
        try:
            r = Groq(api_key=k, timeout=30, max_retries=0).chat.completions.create(
                model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}],
                max_tokens=300, temperature=0.1, response_format={"type": "json_object"})
            return json.loads(r.choices[0].message.content)
        except Exception:
            continue
    return None


def run(banques, dry_run=False, limit=None, force=False):
    _load_env()
    import db, web_facts
    val = json.load(open(VALID_PATH, encoding="utf-8"))
    auto = val.setdefault("services_auto", {})

    # 1) Détecter les candidats « non vérifiés » (non_contredit) de chaque banque
    candidates = {}
    for bk in banques:
        for r in (db.cb_exclusivites_banque(bk, 2026, "S1", "Particuliers") or []):
            if r.get("verdict") == "non_contredit":
                sig = web_facts._sig_lib(r.get("libelle", ""))
                if sig and (force or sig not in auto):
                    candidates[sig] = r.get("libelle", "")
    print(f"[veille-excl] {len(candidates)} service(s) à valider sur {len(banques)} banque(s).")

    has_backend = bool(os.getenv("TAVILY_API_KEY") or os.getenv("OPENAI_API_KEY"))
    if dry_run or not has_backend:
        if not has_backend:
            print("[veille-excl] Aucune clé de recherche (TAVILY_API_KEY / OPENAI_API_KEY) dans .env → mode LISTE.")
        for lib in list(candidates.values())[:(limit or 999)]:
            print("   • à valider :", str(lib)[:70])
        return

    # 2) Mode AUTO : recherche web + classification, écriture sourcée
    done = 0
    for sig, lib in candidates.items():
        if limit and done >= limit:
            break
        q = (f"Quelles banques en Côte d'Ivoire proposent le service bancaire « {lib} » "
             f"(SGCI BICICI NSIA Ecobank SIB BNI BACI Banque Atlantique) ?")
        snips = _search(q) or []
        verdict = _classify(lib, snips) if snips else None
        if verdict and verdict.get("verdict") in ("partage", "differenciant", "non_contredit"):
            auto[sig] = {"verdict": verdict["verdict"], "concurrents": verdict.get("concurrents", []),
                         "note": verdict.get("note", ""), "sources": [s["url"] for s in snips if s.get("url")][:4],
                         "date": datetime.date.today().isoformat(), "_libelle": lib}
            done += 1
            print(f"   ✓ {str(lib)[:48]:48} → {verdict['verdict']}")
        else:
            print(f"   – {str(lib)[:48]:48} → non concluant (laissé 'non_contredit')")
        time.sleep(1.2)   # respect des quotas de recherche

    val["services_auto"] = auto
    val["_veille_excl_maj"] = datetime.date.today().isoformat()
    json.dump(val, open(VALID_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[veille-excl] {done} service(s) validé(s) et écrit(s) dans exclusivites_validation.json.")


if __name__ == "__main__":
    args = sys.argv[1:]
    banques = BANKS
    dry = "--dry-run" in args
    force = "--force" in args
    limit = None
    if "--banques" in args:
        banques = [b.strip().upper() for b in args[args.index("--banques") + 1].split(",")]
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    run(banques, dry_run=dry, limit=limit, force=force)
