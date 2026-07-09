# -*- coding: utf-8 -*-
"""
web_facts.py — Agent WEB (veille externe reproductible & citée).
================================================================
Quatrième agent du RAG. Fournit des faits externes (parts de marché, réseau,
notations…) UNIQUEMENT depuis un cache alimenté par un module de veille
reproductible (`run_veille.py`) à partir d'un REGISTRE DE SOURCES FIABLES.

Règles :
  • Le dashboard ne fait JAMAIS d'appel web en direct → il lit le cache.
  • Chaque fait porte sa source (URL) + sa date + son niveau de fiabilité.
  • Un fait sans source fiable n'entre pas → on n'invente jamais.
  • Reproductible : relancer `run_veille.py` régénère le cache (mêmes sources).
"""
import os, json

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE = os.path.join(_HERE, "web_facts.json")

# ── Registre de sources fiables (autorités) — utilisé par run_veille.py ──────
SOURCE_REGISTRY = {
    "BCEAO": "https://www.bceao.int/",                       # Commission Bancaire UEMOA, rapports
    "APBEF_CI": "https://www.apbef-ci.org/",                  # Assoc. pro. des banques CI — stats secteur
    "SGCI": "https://societegenerale.ci/",                    # site officiel SGCI
    "BICICI": "https://www.bicici.com/",                      # site officiel BICICI
    "BLOOMFIELD": "https://www.bloomfield-investment.com/",   # notations financières régionales
}

_FACTS = None
_FACTS_MTIME = None


def _load():
    """Charge web_facts.json — et le RECHARGE automatiquement si le fichier a été modifié depuis
    (ex. run_veille.py relancé pendant que le serveur tourne) : plus besoin de redémarrer pour que
    la veille web se reflète (bug du même type que le lru_cache non invalidé, corrigé le 2026-07-08)."""
    global _FACTS, _FACTS_MTIME
    try:
        mtime = os.path.getmtime(_CACHE)
    except Exception:
        mtime = None
    if _FACTS is None or mtime != _FACTS_MTIME:
        try:
            with open(_CACHE, encoding="utf-8") as f:
                _FACTS = json.load(f)
            _FACTS_MTIME = mtime
        except Exception:
            if _FACTS is None:
                _FACTS = {"banques": {}, "sources": [], "maj": None}
    return _FACTS


# ════════════════════════════════════════════════════════════════════════════
# VALIDATION DES EXCLUSIVITÉS CB (Agent Web) — corrige les FAUX exclusifs.
# cb_analyse_q3 déduit l'exclusivité des GRILLES publiées ; or « absent de la grille
# d'un concurrent » ≠ « le concurrent ne l'offre pas ». Ici on (1) retire le BRUIT
# (lignes de grille ≠ services) et (2) reclasse chaque service avec sources web.
# ════════════════════════════════════════════════════════════════════════════
_EXCL_VAL = None
_EXCL_VAL_MTIME = None
_EXCL_VAL_PATH = os.path.join(_HERE, "exclusivites_validation.json")


def _load_excl_validation():
    global _EXCL_VAL, _EXCL_VAL_MTIME
    try:
        mtime = os.path.getmtime(_EXCL_VAL_PATH)
    except Exception:
        mtime = None
    if _EXCL_VAL is None or mtime != _EXCL_VAL_MTIME:
        try:
            with open(_EXCL_VAL_PATH, encoding="utf-8") as f:
                _EXCL_VAL = json.load(f)
            _EXCL_VAL_MTIME = mtime
        except Exception:
            if _EXCL_VAL is None:
                _EXCL_VAL = {"bruit_patterns": [], "regles": []}
    return _EXCL_VAL


import re as _re_excl


def _norm_lib(s):
    """Normalise un libellé pour matcher malgré l'OCR : minuscule, recolle les coupures
    « con- nect » → « connect », « inva- lidité » → « invalidité », espaces tassés."""
    s = (s or "").lower().replace("’", "'").replace("’", "'")
    s = _re_excl.sub(r"-\s+", "", s)        # coupure OCR : « con- nect » → « connect »
    s = _re_excl.sub(r"\s+", " ", s).strip()
    return s


def est_bruit(libelle):
    """True si le libellé est une ligne de grille (tranche de montant, vignette, fragment OCR) ≠ service."""
    lib = _norm_lib(libelle)
    if any(p in lib for p in _load_excl_validation().get("bruit_patterns", [])):
        return True
    # Heuristiques OCR : fragments de grille (plusieurs « gratuit », ou ≥2 gros nombres collés).
    if lib.count("gratuit") >= 2:
        return True
    if len(_re_excl.findall(r"\d[\d  .]{3,}", lib)) >= 2:
        return True
    # Tranches de MONTANT (ex. « 0 <=M <= 1 Mos », « 500 Mios < M », « Mos <M <= 5 Mos ») et
    # DIMENSIONS (ex. « Hauteur 14,8 cm ») = lignes de grille, pas des services.
    if _re_excl.search(r"\bm\b\s*<|<\s*\bm\b|\bm\b\s*<=|<=\s*\bm\b|\bmios\b|\bmos\b|et maximum|hauteur.*cm", lib):
        return True
    return False


def _sig_lib(s):
    """Signature normalisée (sans accents/ponctuation) — clé des services AUTO-validés."""
    import unicodedata as _u
    s = _u.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return _re_excl.sub(r"[^a-z0-9]+", " ", s).strip()


def valider_exclusivite(libelle):
    """Verdict web {verdict, concurrents, note, sources} pour un service, ou None (→ non_contredit).
    Priorité : (1) services AUTO-validés par l'agent `run_veille_exclusivites.py` (recherche web
    réelle, clé = signature du libellé), puis (2) règles CURÉES par patterns. Les deux sourcés."""
    val = _load_excl_validation()
    auto = val.get("services_auto", {})
    if auto:
        sig = _sig_lib(libelle)
        if sig in auto:
            return auto[sig]
    lib = _norm_lib(libelle)
    for r in val.get("regles", []):
        if any(p in lib for p in r.get("patterns", [])):
            return r
    return None


def classer_exclusivites(rows):
    """Candidats exclusifs (cb_analyse_q3) → RETIRE le bruit + tague chaque service réel d'un verdict
    web : 'partage' (concurrent confirmé) | 'differenciant' (nom de marque SGCI) | 'non_contredit'
    (grille seule, non réfuté). Retourne la liste classée (dicts enrichis)."""
    out = []
    for r in rows:
        d = dict(r)
        lib = d.get("libelle", "")
        if est_bruit(lib):
            continue
        v = valider_exclusivite(lib)
        if v:
            d["verdict"] = v["verdict"]
            d["concurrents"] = v.get("concurrents", [])
            d["verdict_note"] = v.get("note", "")
            d["verdict_sources"] = v.get("sources", [])
        else:
            d["verdict"] = "non_contredit"
            d["concurrents"] = []
            d["verdict_note"] = ("Présent chez SGCI, aucun concurrent trouvé dans les grilles "
                                 "(non vérifié au web). Exclusivité plausible, NON certifiée.")
            d["verdict_sources"] = []
        out.append(d)
    return out


def facts_for(banks):
    """Retourne {banque: {fait: valeur, ..., _note}} pour les banques demandées."""
    d = _load().get("banques", {})
    return {b: d[b] for b in banks if b in d}


def secteur():
    """Faits de CONTEXTE sectoriel (BCEAO, APBEF-CI, classements) — complémentaires
    aux données internes EF/CB, chacun cité+daté avec son lien d'analyse."""
    return _load().get("secteur", [])


def secteur_index():
    """Faits sectoriels indexés par clé (accès direct depuis la stratégie)."""
    return {f.get("cle"): f for f in _load().get("secteur", [])}


def innovations():
    """Innovations des concurrents à copier/dépasser (regard Directeur Innovation)."""
    return _load().get("innovations", [])


def reglementation():
    """Dispositions réglementaires BCEAO/UEMOA exploitables (leviers + contraintes), sourcées."""
    return _load().get("reglementation", [])


def sources():
    """Liste des sources web (citées) pour la transparence."""
    out = []
    for s in _load().get("sources", []):
        out.append({"ref": s.get("ref", ""), "type": "WEB",
                    "fiabilite": s.get("fiabilite", "à vérifier"),
                    "url": s.get("url", ""), "date": s.get("date", "")})
    return out


def maj():
    return _load().get("maj")
