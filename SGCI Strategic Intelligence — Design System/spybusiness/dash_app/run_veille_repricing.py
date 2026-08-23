# -*- coding: utf-8 -*-
"""
run_veille_repricing.py — AGENT WEB de validation des ACTIONS TARIFAIRES (repricing).
=====================================================================================
Pour chaque service où le repricing recommande une HAUSSE ou une BAISSE, l'agent VA
SUR LE WEB (Tavily) chercher le positionnement réel de ce frais sur le marché bancaire
ivoirien (UEMOA), puis un petit LLM (Groq) juge si la décision est CONFORTÉE par le web
et produit une note SOURCÉE (contexte + nuance + sources).

→ écrit dans cb_repricing_web.json, clé = libellé canonique. L'endpoint /api/cb_repricing
  fusionne cette validation dans chaque action (action["web"]).

REPRODUCTIBLE (relancer ré-interroge le web) · IDEMPOTENT (ne re-valide pas un service
déjà présent, sauf --force). Clés (.env) : TAVILY_API_KEY + GROQ_API_KEY[_2..12].

Usage :
  python run_veille_repricing.py                 # tous les services à action (tous filtres)
  python run_veille_repricing.py --limit 20      # borné
  python run_veille_repricing.py --dry-run       # liste seulement
  python run_veille_repricing.py --force         # revalide tout
"""
import os, sys, re, json, time, datetime, requests

HERE = os.path.dirname(os.path.abspath(__file__))
# Données de référence regroupées dans spybusiness/data/ (2026-07-30) : elles alimentent
# les analyses et se conservent, contrairement aux caches qui se régénèrent.
DOSSIER_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "data")
WEB_PATH = os.path.join(DOSSIER_DATA, "cb_repricing_web.json")
BASE = os.getenv("SB_BASE_URL", "http://localhost:5000")
COMBOS = [(a, s, seg) for seg in ("Particuliers", "Entreprises")
          for a in (2024, 2025, 2026) for s in ("S1", "S2")]


def _load_env():
    try:
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv(usecwd=True))
        load_dotenv(os.path.abspath(os.path.join(HERE, "..", "..", "..", ".env")))
    except Exception:
        pass


def _canon(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())[:90]


def _search(query, k=4):
    tav = os.getenv("TAVILY_API_KEY")
    if not tav:
        return []
    try:
        r = requests.post("https://api.tavily.com/search",
                          json={"api_key": tav, "query": query, "max_results": k,
                                "search_depth": "basic"}, timeout=25)
        if r.ok:
            return [{"title": x.get("title", ""), "url": x.get("url", ""),
                     "content": (x.get("content") or "")[:400]} for x in r.json().get("results", [])]
        print("   [tavily]", r.status_code, r.text[:80])
    except Exception as e:
        print("   [tavily err]", str(e)[:90])
    return []


def _classify(item, snips):
    keys = [k for k in [os.getenv("GROQ_API_KEY", "")] +
            [os.getenv(f"GROQ_API_KEY_{i}", "") for i in range(2, 13)] if k]
    if not keys:
        return None
    ctx = "\n".join(f"- {s.get('title','')} : {s.get('content','')[:220]}" for s in snips[:6])
    cible = item.get("cible")
    lib = item["libelle"]
    prompt = (
        f"Service bancaire en Côte d'Ivoire (marché UEMOA) : « {lib} » ({item.get('sous_section','')}).\n"
        f"Prix SGCI actuel : {item.get('sgci_prix')} F. Médiane marché (concurrents ivoiriens) : {item.get('mkt_median')} F.\n"
        f"Recommandation interne à valider : {item['verdict']}"
        + (f" vers {cible} F.\n\n" if cible else ".\n\n")
        + f"Extraits web sur ce type de frais dans les banques ivoiriennes (UEMOA) :\n{ctx}\n\n"
        "Réponds en JSON STRICT :\n"
        '{"contexte":"1 phrase FACTUELLE sur le positionnement de ce frais sur le marché ivoirien (pratique/fourchette)",'
        '"ok":true,'
        '"nuance":"1 phrase: confirmation OU prudence (risque PNB, élasticité, barrière de sortie)"}\n'
        "RÈGLES : \"ok\"=true si le web CONFORTE la recommandation ; false s'il invite à la prudence. "
        "Reste factuel et concis. JSON uniquement."
    )
    from groq import Groq
    for k in keys:
        try:
            r = Groq(api_key=k, timeout=30, max_retries=0).chat.completions.create(
                model="openai/gpt-oss-120b", messages=[{"role": "user", "content": prompt}],
                max_tokens=450, temperature=0.1, response_format={"type": "json_object"},
                reasoning_effort="low")
            return json.loads(r.choices[0].message.content)
        except Exception:
            continue
    return None


def _collect_items():
    """Interroge l'endpoint repricing pour TOUS les filtres → items d'action (hausse/baisse),
    dédupliqués par libellé canonique (on garde celui qui a un prix SGCI)."""
    uniq = {}
    for an, sem, seg in COMBOS:
        try:
            d = requests.get(f"{BASE}/api/cb_repricing",
                             params={"annee": an, "semestre": sem, "segment": seg}, timeout=180).json()
        except Exception as e:
            print(f"   [collect] {seg} {an} {sem} err: {str(e)[:70]}")
            continue
        for sec in d.get("recap", []):
            for it in sec.get("items", []):
                key = _canon(it.get("libelle"))
                if key and key not in uniq:
                    uniq[key] = {**it, "roman": sec.get("roman"), "titre": sec.get("titre")}
    return uniq


def run(dry_run=False, limit=None, force=False):
    _load_env()
    web = json.load(open(WEB_PATH, encoding="utf-8")) if os.path.exists(WEB_PATH) else {}
    services = web.setdefault("services", {})

    items = _collect_items()
    todo = {k: v for k, v in items.items() if force or k not in services}
    print(f"[veille-repricing] {len(items)} service(s) à action, {len(todo)} à valider.")

    if dry_run or not os.getenv("TAVILY_API_KEY"):
        if not os.getenv("TAVILY_API_KEY"):
            print("[veille-repricing] Pas de TAVILY_API_KEY (.env) → mode LISTE.")
        for k, v in list(todo.items())[:(limit or 999)]:
            print(f"   • {v['verdict']:9} {v['libelle'][:60]}")
        return

    done = 0
    for key, it in todo.items():
        if limit and done >= limit:
            break
        lib = it["libelle"]
        sn = (_search(f"frais « {lib} » banque Côte d'Ivoire tarif UEMOA", k=4)
              + _search(f"{lib} tarif banque Côte d'Ivoire", k=3))
        v = _classify(it, sn) if sn else None
        if v and isinstance(v.get("ok"), bool):
            srcs = [s["url"] for s in sn if s.get("url")][:3]
            services[key] = {
                "_libelle": lib, "verdict_ref": it["verdict"],
                "contexte": v.get("contexte", ""), "ok": v["ok"],
                "nuance": v.get("nuance", ""), "sources": srcs,
                "date": datetime.date.today().isoformat(),
            }
            done += 1
            tag = "CONFORTÉ" if v["ok"] else "PRUDENCE"
            print(f"   ✓ {it['verdict']:9} {lib[:40]:40} → {tag} | {str(v.get('contexte',''))[:50]}")
        else:
            print(f"   – {it['verdict']:9} {lib[:40]:40} → non concluant")
        time.sleep(1.2)

    web["services"] = services
    web["_maj"] = datetime.date.today().isoformat()
    json.dump(web, open(WEB_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[veille-repricing] {done} service(s) sourcé(s) → cb_repricing_web.json")


if __name__ == "__main__":
    args = sys.argv[1:]
    lim = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    run(dry_run="--dry-run" in args, limit=lim, force="--force" in args)
