# -*- coding: utf-8 -*-
"""
run_veille_gaps.py — AGENT WEB de validation des MANQUES (gaps) CB.
====================================================================
Pour chaque service d'un CONCURRENT flaggé « absent chez SGCI », l'agent VA SUR LE WEB :
  1) à QUOI sert ce service (rôle, 1 phrase) ;
  2) la Société Générale CI (SGCI) le propose-t-elle (ou un équivalent, même sous un autre nom) ?
→ écrit le verdict SOURCÉ dans gaps_validation.json. Un « manque » confirmé = SGCI ne l'a vraiment pas.

REPRODUCTIBLE (relancer ré-interroge le web) · DYNAMIQUE (nouveaux services validés) · IDEMPOTENT
(ne re-valide pas un service déjà présent dans services_auto, sauf --force).

Clés (.env) : TAVILY_API_KEY (recherche) + GROQ_API_KEY[_2..12] (classification). OPENAI_API_KEY en secours.

Usage :
  python run_veille_gaps.py --banques BACI --limit 15      # ciblé, borné
  python run_veille_gaps.py                                 # toutes les banques
  python run_veille_gaps.py --dry-run                       # liste seulement
"""
import os, sys, json, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
VALID_PATH = os.path.join(HERE, "gaps_validation.json")


def _charger_concurrents():
    """Concurrents de SGCI (toutes les banques sauf SGCI), chargés depuis db.BANKS (dynamique,
    table `banques`) — filet de sécurité figé seulement si la BD est indisponible."""
    try:
        import db as _db
        if _db.BANKS:
            return [b for b in _db.BANKS if b != "SGCI"]
    except Exception:
        pass
    return ["BICICI", "NSIA", "ECOBANK", "SIB", "BNI", "BACI"]


BANKS = _charger_concurrents()   # concurrents (pas SGCI)


def _load_env():
    try:
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv(usecwd=True))
        load_dotenv(os.path.abspath(os.path.join(HERE, "..", "..", "..", ".env")))
    except Exception:
        pass


# ── RECHERCHE WEB (Tavily, sinon OpenAI) ───────────────────────────────────────
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
    return None


_SGCI_DOMAINS = ("societegenerale.ci", "sgci", "société générale", "societe generale")


# ── CLASSIFICATION (Groq) : rôle + SGCI a-t-elle l'équivalent ? ─────────────────
def _classify(libelle, banque, snips_role, snips_sgci):
    keys = [k for k in [os.getenv("GROQ_API_KEY", "")] +
            [os.getenv(f"GROQ_API_KEY_{i}", "") for i in range(2, 13)] if k]
    if not keys:
        return None
    ctxR = "\n".join(f"- {s.get('title','')} : {s.get('content','')[:220]}" for s in snips_role[:4])
    ctxS = "\n".join(f"- {s.get('title','')} ({s.get('url','')}) : {s.get('content','')[:220]}" for s in snips_sgci[:5])
    sgci_hit = any(any(d in (s.get('url', '') + s.get('title', '')).lower() for d in _SGCI_DOMAINS) for s in snips_sgci)
    prompt = (
        f"Service bancaire en Côte d'Ivoire proposé par {banque} : « {libelle} ».\n\n"
        f"Extraits web sur CE service :\n{ctxR}\n\n"
        f"Extraits web sur l'offre de la Société Générale Côte d'Ivoire (SGCI) :\n{ctxS}\n\n"
        f"(Indice : une page du domaine SGCI est{' ' if sgci_hit else ' PAS '}présente dans les extraits SGCI.)\n\n"
        "Réponds en JSON STRICT :\n"
        '{"role":"à quoi sert ce service, 1 phrase simple et concrète",'
        '"sgci_a_equivalent":true|false,'
        '"equivalent_sgci":"nom du produit équivalent chez SGCI, ou \\"\\" si aucun",'
        '"note":"1 phrase sourcée justifiant le verdict"}\n'
        "RÈGLES : sgci_a_equivalent=true SEULEMENT si une preuve web montre que SGCI offre ce service "
        "ou un équivalent FONCTIONNEL (même sous un autre nom). En cas de doute → false. JSON uniquement."
    )
    from groq import Groq
    for k in keys:
        try:
            r = Groq(api_key=k, timeout=30, max_retries=0).chat.completions.create(
                model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}],
                max_tokens=320, temperature=0.1, response_format={"type": "json_object"})
            return json.loads(r.choices[0].message.content)
        except Exception:
            continue
    return None


import re as _re_g
def _meaningful(lib):
    """Garde UNIQUEMENT les vrais services NOMMÉS (comme le dashboard) — écarte les plages
    de prix, le bruit OCR (lettres espacées), les libellés commençant par un chiffre/point."""
    l = (lib or "").strip()
    if len(_re_g.findall(r"[A-Za-zÀ-ÿ]", l)) < 8:
        return False
    if _re_g.match(r"^[\d.\s•\-]", l):                      # commence par chiffre/point/puce
        return False
    if _re_g.search(r"\bFCFA\b.*\bà\b.*\bFCFA\b", l, _re_g.I):   # plage de prix
        return False
    if _re_g.search(r"(?:[A-Za-zÀ-ÿ]\s){4,}", l):          # lettres espacées = OCR cassé
        return False
    words = _re_g.findall(r"[A-Za-zÀ-ÿ]{3,}", l)
    return len(words) >= 2


def _candidates(banque):
    """Mêmes candidats NOMMÉS que le dashboard : produits {banque} sans équivalent canonique
    évident chez SGCI, filtrés du bruit (plages de prix, OCR)."""
    import db
    from cb_axes import prefilter_gaps
    all_data = db.cb_libelles_tous(2026, "S1", "Particuliers") or {}
    sgci = all_data.get("SGCI", [])
    bank = all_data.get(banque, [])
    if not bank:
        return []
    cands = prefilter_gaps(bank, sgci, cutoff=0.72)
    out, seen = [], set()
    for c in cands:
        lib = (c.get("libelle") or "").strip()
        if not _meaningful(lib) or lib.lower() in seen:
            continue
        seen.add(lib.lower())
        out.append(lib)
    return out


def run(banques, dry_run=False, limit=None, force=False):
    _load_env()
    val = json.load(open(VALID_PATH, encoding="utf-8")) if os.path.exists(VALID_PATH) else {}
    auto = val.setdefault("services_auto", {})

    candidates = {}   # sig -> (banque, libelle)
    for bk in banques:
        for lib in _candidates(bk):
            sig = lib.lower().strip()
            if force or sig not in auto:
                candidates[sig] = (bk, lib)
    print(f"[veille-gaps] {len(candidates)} service(s) à valider sur {len(banques)} banque(s).")

    has_backend = bool(os.getenv("TAVILY_API_KEY") or os.getenv("OPENAI_API_KEY"))
    if dry_run or not has_backend:
        if not has_backend:
            print("[veille-gaps] Aucune clé de recherche (.env) → mode LISTE.")
        for bk, lib in list(candidates.values())[:(limit or 999)]:
            print(f"   • {bk} : {lib[:64]}")
        return

    done = 0
    for sig, (bk, lib) in candidates.items():
        if limit and done >= limit:
            break
        snR = _search(f"« {lib} » service bancaire Côte d'Ivoire à quoi ça sert définition", k=4) or []
        snS = _search(f"{lib} Société Générale Côte d'Ivoire SGCI societegenerale.ci", k=5) or []
        v = _classify(lib, bk, snR, snS) if (snR or snS) else None
        if v and isinstance(v.get("sgci_a_equivalent"), bool):
            srcs = [s["url"] for s in (snR + snS) if s.get("url")][:4]
            auto[sig] = {
                "banque": bk, "_libelle": lib,
                "role": v.get("role", ""),
                "sgci_a_equivalent": v["sgci_a_equivalent"],
                "equivalent_sgci": v.get("equivalent_sgci", ""),
                "note": v.get("note", ""),
                "sources": srcs,
                "date": datetime.date.today().isoformat(),
            }
            done += 1
            tag = "SGCI L'A (pas un manque)" if v["sgci_a_equivalent"] else "VRAI MANQUE"
            print(f"   ✓ {bk} · {lib[:42]:42} → {tag} | {str(v.get('role',''))[:46]}")
        else:
            print(f"   – {bk} · {lib[:42]:42} → non concluant")
        time.sleep(1.2)

    val["services_auto"] = auto
    val["_veille_gaps_maj"] = datetime.date.today().isoformat()
    json.dump(val, open(VALID_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[veille-gaps] {done} service(s) validé(s) → gaps_validation.json")


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
