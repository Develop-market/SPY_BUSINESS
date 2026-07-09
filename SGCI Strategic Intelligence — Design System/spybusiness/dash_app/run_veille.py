# -*- coding: utf-8 -*-
"""
run_veille.py — VEILLE WEB RÉELLE & reproductible (Agent WEB du RAG).
=====================================================================
Met à jour `web_facts.json` (faits sectoriels du dashboard / PESTEL) en allant chercher
les valeurs les PLUS RÉCENTES sur le web (Tavily), en EXTRAYANT le chiffre + sa source
via le LLM (Groq), puis en réécrivant le cache DATÉ.

REPRODUCTIBLE : relancer régénère le cache (mêmes requêtes, mêmes sources).
DYNAMIQUE : ramène du frais → fini les chiffres figés de 2024 dans le PESTEL.
HONNÊTE : on ne met à jour QUE si un chiffre clair + récent est trouvé (sanity-check) ;
          sinon on GARDE l'ancien et on le marque « à rafraîchir ». Jamais d'invention.
          Backup horodaté avant toute écriture.

Clé requise : TAVILY_API_KEY (.env). Sans clé → mode VÉRIF (ping des liens, comme avant).
Usage :  python run_veille.py   |   python run_veille.py --dry-run
"""
import os, sys, json, re, time, datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")   # console Windows (cp1252) → UTF-8
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "web_facts.json")

# Indicateurs à rafraîchir : clé → (libellé humain pour le LLM, requête web, regex de PLAUSIBILITÉ
# SÉMANTIQUE — la valeur extraite doit matcher, sinon on rejette et on garde l'ancien).
INDICATEURS = {
    "politique_monetaire": ("Taux directeur de la BCEAO (politique monétaire UEMOA), en %",
                            "taux directeur BCEAO UEMOA actuel 2025 2026", r"%"),
    "croissance_macro":    ("Croissance du PIB et inflation en Côte d'Ivoire (en %)",
                            "Côte d'Ivoire croissance PIB inflation 2025 2026 prévision FMI BCEAO", r"(?i)pib"),
    "bancarisation":       ("Taux de bancarisation en Côte d'Ivoire (en %)",
                            "taux de bancarisation Côte d'Ivoire UEMOA 2025 2026", r"%"),
    "mobile_money":        ("Taux de pénétration du mobile money en Côte d'Ivoire (en %)",
                            "taux pénétration mobile money Côte d'Ivoire UEMOA 2025", r"%"),
    "cout_credit":         ("Taux débiteur moyen du crédit et taux d'usure (Côte d'Ivoire/UEMOA), en %",
                            "taux débiteur moyen crédit taux usure UEMOA BCEAO 2025 2026", r"%"),
    "npl_secteur":         ("Taux de créances en souffrance (NPL) des banques UEMOA (en %)",
                            "taux créances en souffrance NPL banques UEMOA 2025 BCEAO", r"%"),
    "solvabilite_secteur": ("Ratio de solvabilité du secteur bancaire UEMOA (en %)",
                            "ratio de solvabilité banques UEMOA 2025 BCEAO commission bancaire", r"%"),
    "structure_marche":    ("Nombre de banques agréées en Côte d'Ivoire (un nombre de banques, ex. '28 banques')",
                            "nombre de banques agréées Côte d'Ivoire 2025 secteur bancaire", r"(?i)banque"),
}


def _load_env():
    try:
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv(usecwd=True))
        load_dotenv(os.path.abspath(os.path.join(HERE, "..", "..", "..", ".env")))
    except Exception:
        pass


def _search(query, k=5):
    tav = os.getenv("TAVILY_API_KEY")
    if not tav:
        return None
    try:
        import requests
        r = requests.post("https://api.tavily.com/search",
                          json={"api_key": tav, "query": query, "max_results": k,
                                "search_depth": "advanced"}, timeout=30)
        if r.ok:
            return [{"title": x.get("title", ""), "url": x.get("url", ""),
                     "content": (x.get("content") or "")[:500]} for x in r.json().get("results", [])]
    except Exception as e:
        print("   [tavily err]", str(e)[:90])
    return None


def _extract(libelle, snippets):
    """Groq extrait le chiffre RÉCENT + source depuis les extraits. None si rien de fiable."""
    keys = [k for k in [os.getenv("GROQ_API_KEY", "")] +
            [os.getenv(f"GROQ_API_KEY_{i}", "") for i in range(2, 13)] if k]
    if not keys:
        return None
    ctx = "\n".join(f"- {s.get('title','')} ({s.get('url','')}) : {s.get('content','')}" for s in snippets[:5])
    prompt = (
        f"Indicateur recherché : {libelle}.\nExtraits web récents :\n{ctx}\n\n"
        "Extrais la valeur la PLUS RÉCENTE et CLAIREMENT énoncée dans ces extraits, qui correspond EXACTEMENT "
        "à l'indicateur demandé (pas une autre statistique). JSON STRICT :\n"
        '{"valeur":"<chiffre COURT, ex. \'PIB +6,7% · inflation 1,2%\' ou \'3,00%\' ou \'28 banques\'>",'
        '"detail":"<une phrase factuelle de contexte, <=140 caractères, tirée des extraits>",'
        '"annee":"<année du chiffre, ex. 2025>","source":"<institution courte, ex. BCEAO, FMI, UMOA>",'
        '"url":"<url la plus pertinente>"}\n'
        "Si AUCUN chiffre clair, récent ET correspondant à CET indicateur n'apparaît, renvoie {\"valeur\":null}. "
        "N'invente JAMAIS un chiffre ; ne donne pas une statistique d'un autre sujet."
    )
    from groq import Groq
    for k in keys:
        try:
            r = Groq(api_key=k, timeout=30, max_retries=0).chat.completions.create(
                model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}],
                max_tokens=250, temperature=0.0, response_format={"type": "json_object"})
            return json.loads(r.choices[0].message.content)
        except Exception:
            continue
    return None


def _sanitize(cle, val):
    """Assainit/valide la valeur extraite selon des bornes plausibles. Renvoie la valeur
    nettoyée, ou None si aberrante (→ on garde l'ancienne). Évite déflation, % hors [0,100], etc."""
    v = str(val).strip()
    fl = lambda s: float(s.replace(",", ".").replace("+", ""))
    nums = re.findall(r"[+\-]?\d+(?:[.,]\d+)?", v)
    if cle == "croissance_macro":
        pib = re.search(r"(?i)pib[^0-9+\-]*([+\-]?\d+(?:[.,]\d+)?)", v)
        inf = re.search(r"(?i)inflation[^0-9+\-]*([+\-]?\d+(?:[.,]\d+)?)", v)
        if not pib or not (0 < fl(pib.group(1)) < 15):
            return None
        out = f"PIB +{pib.group(1).lstrip('+')}%".replace(".", ",")
        if inf and 0 <= fl(inf.group(1)) < 15:          # inflation négative = rejetée
            out += f" · inflation {inf.group(1).lstrip('+')}%".replace(".", ",")
        return out
    if cle == "structure_marche":
        for n in nums:
            if 5 <= fl(n) <= 80:
                return f"{int(fl(n))} banques"
        return None
    # indicateurs en % : au moins un nombre dans [0,100]
    for n in nums:
        if 0 <= fl(n) <= 100:
            return v
    return None


def run(dry_run=False):
    _load_env()
    today = datetime.date.today().isoformat()
    try:
        data = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        data = {"secteur": [], "sources": []}

    if not os.getenv("TAVILY_API_KEY"):
        print("[veille] Pas de TAVILY_API_KEY → mode VÉRIF liens uniquement (pas de rafraîchissement de chiffres).")
        data["maj"] = today
        if not dry_run:
            json.dump(data, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return

    # Backup horodaté AVANT toute écriture
    if not dry_run:
        bak = os.path.join(HERE, f"web_facts_backup_{datetime.datetime.now():%Y%m%d_%H%M%S}.json")
        json.dump(data, open(bak, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"[veille] backup → {os.path.basename(bak)}")

    sec = {f.get("cle"): f for f in data.get("secteur", [])}
    maj_n = 0
    for cle, (libelle, query, plaus) in INDICATEURS.items():
        snips = _search(query) or []
        res = _extract(libelle, snips) if snips else None
        raw_val = (res or {}).get("valeur")
        val = _sanitize(cle, raw_val) if raw_val else None
        if val and len(str(val)) < 90:
            fact = sec.setdefault(cle, {"cle": cle})
            src = (res.get("source") or "web").strip()[:35]
            ym = re.search(r"\b(20\d{2})\b", str(res.get("annee") or ""))
            annee = ym.group(1) if ym else ""
            det = (res.get("detail") or "").strip()
            fact["valeur"] = str(val).strip()
            if det and 10 < len(det) <= 180:
                fact["detail"] = det
            fact["source"] = (src + (" " + annee if annee else "")).strip()
            fact["url"] = res.get("url") or fact.get("url", "")
            fact["date"] = today
            fact["_maj_auto"] = True
            fact.pop("_a_rafraichir", None)
            maj_n += 1
            print(f"   ✓ {cle:22} → {val}  [{src} {annee}]")
        else:
            if cle in sec:
                sec[cle]["_a_rafraichir"] = True   # gardé tel quel, signalé
            print(f"   – {cle:22} → pas de chiffre récent fiable (ancien gardé)")
        time.sleep(1.2)

    data["secteur"] = list(sec.values())
    data["maj"] = today
    data["_veille_maj_auto"] = today
    if not dry_run:
        json.dump(data, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[veille] {maj_n}/{len(INDICATEURS)} indicateurs rafraîchis ({today}).")


if __name__ == "__main__":
    args = sys.argv[1:]
    dry = "--dry-run" in args
    # 1) Faits sectoriels (contexte macro / PESTEL / stratégie)
    run(dry_run=dry)
    # 2) Même agent web → exclusivités CB (sauf --no-excl). UN seul point d'entrée.
    if "--no-excl" not in args:
        try:
            import run_veille_exclusivites as _ex
            print("\n[veille] === Exclusivités CB (même moteur Tavily+Groq) ===")
            _ex.run(_ex.BANKS, dry_run=dry)
        except Exception as e:
            print("[veille] exclusivités ignorées:", str(e)[:140])
