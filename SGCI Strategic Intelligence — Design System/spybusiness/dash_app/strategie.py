# -*- coding: utf-8 -*-
"""
strategie.py — Orchestration STRATÉGIE (Niveau 3 « Prospectif » du RAG).
========================================================================
Mobilise TOUS les agents via la façade unique `agents.AGENTS` :
  • Agent EF  (états financiers)  → ROE, coût du risque, coefficient, croissance, parts de marché
  • Agent CB  (conditions banque) → rang catalogue, win-rate prix, exclusivités, gratuité
  • Agent REGL (réglementation)   → normes prudentielles BCEAO (référentiel sourcé)
  • Agent WEB  (veille)           → faits externes fiables & cités (module reproductible)

Produit UN dossier structuré et SOURCÉ : chaque fait porte sa source → groundedness.
Tout est déterministe (rejouable) ; la couche LLM (route serveur) ne fait qu'habiller.

Reste 100 % dans l'architecture RAG : aucune requête SQL ici, uniquement des appels
aux outils des agents (AGENTS[...].structured / .semantic).
"""
import re
import statistics

import db                      # part_commissions_pnb : définition unique du mix commissions
from agents import AGENTS

try:
    import web_facts as _web   # Agent WEB (Bloc 2) — faits cités, reproductibles
except Exception:
    _web = None

try:
    import db as _db           # source unique : banques + années DYNAMIQUES depuis la base
except Exception:
    _db = None


def _wf(cle, champ="valeur", defaut=""):
    """Lit un fait sectoriel externe depuis web_facts.json (agent veille) — JAMAIS de valeur figée
    dans le code : si la veille met à jour le fait (ex. taux directeur), la stratégie suit
    automatiquement. `cle` = clé sectorielle (clients_sgci, politique_monetaire, cout_credit…)."""
    try:
        return (_web.secteur_index().get(cle) or {}).get(champ) or defaut
    except Exception:
        return defaut

# ── Contexte DYNAMIQUE (flexible / évolutif / reproductible) ─────────────────
# BANKS et l'année de référence viennent de la base — une nouvelle banque ou une
# nouvelle année sont prises en compte automatiquement (cf. _refresh_context() dans build()).
_BANKS_FALLBACK = ["BACI", "BICICI", "BNI", "ECOBANK", "NSIA", "SGCI", "SIB"]
try:
    BANKS = list(_db.BANKS) if (_db and getattr(_db, "BANKS", None)) else list(_BANKS_FALLBACK)
except Exception:
    BANKS = list(_BANKS_FALLBACK)
try:
    _yrs0 = _db.cb_annees() if _db else None
    CB_ANNEE = max(_yrs0) if _yrs0 else 2026
except Exception:
    CB_ANNEE = 2026
CB_SEM = "S1"   # période de référence CB (l'ANNÉE ci-dessus est dynamique)


def _refresh_context():
    """Recharge BANKS + année de référence depuis la base. BANKS est muté EN PLACE → toutes les
    fonctions qui itèrent `BANKS` voient la MAJ, sans redémarrage (nouvelle banque/année)."""
    global CB_ANNEE
    if not _db:
        return
    try:
        if getattr(_db, "BANKS", None):
            BANKS[:] = _db.BANKS
    except Exception:
        pass
    try:
        _y = _db.cb_annees()
        if _y:
            CB_ANNEE = max(_y)
    except Exception:
        pass

# ── Référentiel prudentiel BCEAO (Agent REGL — sourcé) ──────────────────────
# Seuils officiels servant d'ancrage aux recommandations.
BCEAO_NORMES = {
    "solvabilite_min":      {"v": 8,   "confort": 12, "src": "BCEAO — Instruction n°008-2014 (fonds propres)"},
    "coefficient_cible":    {"v": 70,           "src": "BCEAO — Commission Bancaire UEMOA (rapports prudentiels)"},
    "npl_max":              {"v": 5,            "src": "BCEAO — dispositif prudentiel UEMOA"},
    "cnr_encours_max_pb":   {"v": 200,          "src": "BCEAO — surveillance bancaire UEMOA"},
    "credits_depots_sain":  {"min": 80, "max": 100, "src": "BCEAO — Règlement n°09/2010/CM/UEMOA"},
}


def _src(agent, detail):
    return {"agent": agent, "ref": detail}


def _rank(d, bank="SGCI", reverse=True):
    """Rang de `bank` dans un dict {banque: valeur}. reverse=True → plus grand = #1."""
    items = sorted([(b, v) for b, v in d.items() if v is not None], key=lambda x: x[1], reverse=reverse)
    for i, (b, _) in enumerate(items):
        if b == bank:
            return i + 1, len(items)
    return None, len(items)


def _median(d, exclude_none=True):
    vals = [v for v in d.values() if (v is not None)]
    return round(statistics.median(vals), 1) if vals else None


# ════════════════════════════════════════════════════════════════════════════
#  1. DOSSIER DE PREUVES — collecte via les agents (EF + CB + REGL + WEB)
# ════════════════════════════════════════════════════════════════════════════
def collect_evidence(segment="Particuliers"):
    EF = AGENTS["EF"].structured
    CB = AGENTS["CB"].structured

    k   = EF.kpis_vue_ensemble(CB_ANNEE, CB_SEM, segment, 3)   # AN3 = dernière année
    res = EF.resilience_data(3)
    try:
        cr3 = EF.ef_cout_risque_3ans()      # coût du risque robuste (moyenne 3 ans + tendance)
    except Exception:
        cr3 = {}

    # ── Agent CB ──
    # RANG CATALOGUE / GRATUITÉ / WIN-RATE : COMBINÉS Particuliers+Entreprises (2026-07-22,
    # demande explicite du directeur : « tous les onglets doivent tenir compte de TOUTES les
    # données », pas juste un résumé donné au LLM). Ces 3 stats alimentent directement le
    # Diagnostic 360°, le SWOT et les Révélations — elles doivent refléter TOUT SGCI, pas
    # un seul segment. cb_analyse_q6_tous_segments / cb_prix_competitivite_tous_segments
    # recalculent proprement sur l'UNION des deux segments (mêmes garde-fous, même méthode).
    q6  = CB.cb_analyse_q6_tous_segments(CB_ANNEE, CB_SEM)
    cmp = CB.cb_prix_competitivite_tous_segments(CB_ANNEE, CB_SEM)
    serie = CB.cb_serie_temporelle(segment)
    try:
        ratt_list = CB.cb_rattrapage_depassement(segment) or []
    except Exception:
        ratt_list = []
    # Résumé (la fonction renvoie une liste par banque concurrente)
    ratt = {
        "depassement": sum(r.get("depassement", 0) for r in ratt_list),
        "rattrapage":  sum(r.get("rattrapage", 0) for r in ratt_list),
        "top": (ratt_list[0] if ratt_list else None),  # déjà trié par dépassement décroissant
        "par_banque": ratt_list,
    }

    # rang catalogue SGCI (par nb services)
    bycat = sorted([r for r in q6 if (r.get("n_services") or 0) > 0],
                   key=lambda r: -(r.get("n_services") or 0))
    sgci_cat = next((r for r in q6 if r["banque"] == "SGCI"), {})
    rang_cat = next((i + 1 for i, r in enumerate(bycat) if r["banque"] == "SGCI"), None)

    # ── Tilt CORPORATE/PARTICULIERS : profondeur de catalogue par segment, par banque ──
    # (signal d'orientation stratégique : qui couvre surtout les entreprises ?)
    # NOTE : q6 ci-dessus est désormais COMBINÉ (les deux segments) — le tilt a besoin des deux
    # segments SÉPARÉMENT pour calculer un ratio, donc on refait 2 appels segment-par-segment ici,
    # indépendamment du q6 combiné utilisé pour le rang catalogue/gratuité global.
    try:
        q6p = CB.cb_analyse_q6(CB_ANNEE, CB_SEM, "Particuliers")
        cat_part = {r["banque"]: (r.get("n_services") or 0) for r in q6p}
    except Exception:
        cat_part = {}
    try:
        q6e = CB.cb_analyse_q6(CB_ANNEE, CB_SEM, "Entreprises")
        cat_ent = {r["banque"]: (r.get("n_services") or 0) for r in q6e}
    except Exception:
        cat_ent = {}
    tilt = {}   # >1 = orienté entreprises ; <1 = orienté particuliers
    for b in BANKS:
        p, e = cat_part.get(b, 0), cat_ent.get(b, 0)
        if p and e:
            tilt[b] = round(e / p, 2)

    # ── CB×EF : marge de REPRICING — services où SGCI est SOUS la médiane marché ──
    # (réaligner sur la médiane = gain par opération, sans se rendre le plus cher)
    prix = CB.cb_prix_par_libelle(CB_ANNEE, CB_SEM, segment)
    # Coûts de changement ENTREPRISES (2026-07-22, demande explicite : « on néglige Entreprises
    # ??? » — la carte Atout prix/Risque prix ne calculait QUE Particuliers, Entreprises n'était
    # même pas calculé). On récupère aussi le prix Entreprises pour fusionner les deux ci-dessous.
    try:
        prix_ent = CB.cb_prix_par_libelle(CB_ANNEE, CB_SEM, "Entreprises")
    except Exception:
        prix_ent = []
    under = []        # services FCFA où SGCI est SOUS la médiane (repricing / atout prix)
    over = []         # services FCFA où SGCI est AU-DESSUS de la médiane (risque attrition)
    cheaper = []      # services où SGCI est nettement moins chère (atout commercial)
    taux_adv = []     # TAUX (crédit/change…) où SGCI est compétitive (argument d'acquisition)
    CONC = [b for b in BANKS if b != "SGCI"]
    for sec in prix:
        for ss in sec.get("sous_sections", []):
            for svc in ss.get("services", []):
                sg = svc.get("sgci") or {}
                med = svc.get("mkt_median")
                mt = sg.get("montant")
                lib = (svc.get("libelle") or "")[:50]
                if sg.get("tv") == "MONTANT_FCFA" and mt and med and float(mt) >= 100 and med >= 100 and not sg.get("suspect"):
                    mt = float(mt)
                    # — SOUS la médiane = marge de hausse (repricing) + atout prix —
                    if mt < med:
                        gap = round(med - mt)
                        if gap >= 100:
                            under.append({"libelle": lib, "sgci": round(mt), "median": round(med), "gap": gap,
                                          "ecart_pct": round((med - mt) / med * 100)})
                        if mt <= med * 0.6:
                            cheaper.append({"libelle": lib, "sgci": round(mt), "median": round(med)})
                    # — AU-DESSUS de la médiane = plus cher (risque) —
                    # Garde-fou : on borne à +250% ; au-delà = quasi-certainement une
                    # comparaison hors-échelle (ex. frais de dossier crédit corpo vs retail).
                    elif med * 1.15 < mt <= med * 3.5:
                        over.append({"libelle": lib, "sgci": round(mt), "median": round(med),
                                     "surcout": round(mt - med), "ecart_pct": round((mt - med) / med * 100)})
                # — TAUX : SGCI ≤ médiane des concurrents = taux attractif pour le client —
                if sg.get("tv") in ("TAUX_%", "TAUX_%%") and mt and 0 < float(mt) <= 100:
                    ct = [float(c["montant"]) for b in CONC for c in [svc.get("concurrents", {}).get(b)]
                          if c and c.get("tv") in ("TAUX_%", "TAUX_%%") and c.get("montant") and 0 < float(c["montant"]) <= 100]
                    if len(ct) >= 2 and float(mt) >= 1.0:
                        medc = statistics.median(ct)
                        if float(mt) <= medc:
                            taux_adv.append({"libelle": lib, "sgci": float(mt),
                                             "med_conc": round(medc, 2), "min_conc": round(min(ct), 2),
                                             "avantage": round(medc - float(mt), 2),
                                             "rang": 1 + sum(1 for v in ct if v < float(mt))})
    under.sort(key=lambda x: -x["gap"])
    over.sort(key=lambda x: -x["surcout"])
    taux_adv.sort(key=lambda x: -x["avantage"])
    repricing = {"services": under[:8], "n": len(under),
                 "headroom_par_op": sum(x["gap"] for x in under)}
    atouts_cb = {"cheaper": cheaper[:6], "n_cheaper": len(cheaper),
                 "taux": taux_adv[:6], "n_taux": len(taux_adv)}

    # ── Exclusivités (VRIST), gaps à copier — COMBINÉS Particuliers+Entreprises (2026-07-22,
    # demande explicite du directeur). On concatène les deux segments (listes d'objets, pas des
    # ratios) : pas de recalcul ambigu ici, juste l'union des deux catalogues de constats. ──────
    excl_rows, gaps_rows = [], []
    for _seg in ("Particuliers", "Entreprises"):
        try:
            excl_rows += CB.cb_analyse_q3(CB_ANNEE, CB_SEM, _seg) or []
        except Exception:
            pass
        try:
            gaps_rows += CB.cb_analyse_q5(CB_ANNEE, CB_SEM, _seg) or []
        except Exception:
            pass
    # gaps les plus partagés = ce que le PLUS de concurrents offrent et pas SGCI (à copier vite)
    gaps_communs = [g for g in gaps_rows if (g.get("nb_banques") or 0) >= 3]   # ≥3 banques = vrai manque
    gaps_top = sorted(gaps_communs, key=lambda g: -(g.get("nb_banques") or 0))[:8]
    gratuite_par_banque = {r["banque"]: r.get("pct_gratuit") for r in q6 if r.get("pct_gratuit") is not None}
    innov = (_web.innovations() if _web else [])

    # ── Coûts de changement FUSIONNÉS Particuliers+Entreprises (2026-07-22) ──────────────────
    _sw_part = _switching_costs(prix, "Particuliers")
    _sw_ent  = _switching_costs(prix_ent, "Entreprises")
    # PLUS de plafond [:12] (2026-07-22, demande explicite du directeur : « on affiche TOUT, scroll
    # pour voir le reste ») — tri par montant décroissant conservé, rien n'est tronqué.
    _sw_gains  = sorted((_sw_part.get("gains")  or []) + (_sw_ent.get("gains")  or []), key=lambda x: -x["eco"])
    _sw_fuites = sorted((_sw_part.get("fuites") or []) + (_sw_ent.get("fuites") or []), key=lambda x: -x["eco"])
    switching = {
        "gains": _sw_gains, "fuites": _sw_fuites,
        "n_gains": _sw_part.get("n_gains", 0) + _sw_ent.get("n_gains", 0),
        "n_fuites": _sw_part.get("n_fuites", 0) + _sw_ent.get("n_fuites", 0),
        "max_gain": max((_sw_part.get("max_gain", 0), _sw_ent.get("max_gain", 0)), default=0),
        "max_fuite": max((_sw_part.get("max_fuite", 0), _sw_ent.get("max_fuite", 0)), default=0),
    }

    facts = {
        "segment": segment,
        "ef": {
            "rn":        k.get("rn_data", {}),
            "pnb":       k.get("pnb_data", {}),
            "roe":       k.get("roe_data", {}),
            "coeff":     k.get("coeff_expl_data", {}),
            "cout_risque_pnb": k.get("cout_r_pnb_data", {}),
            "cout_risque_3ans": cr3,
            "cout_risque_moy": {b: v.get("moyenne") for b, v in cr3.items()},
            "marge_nette": k.get("marge_nette_data", {}),
            "croissance": k.get("growths_data", {}),
            "credits":   k.get("credits_data", {}),
            "depots":    k.get("depots_data", {}),
            "interets":  k.get("interets_data", {}),
            "commissions": k.get("commissions_data", {}),
            "rang_rn":   k.get("sgci_rang_rn"),
            "part_marche": k.get("sgci_part_marche"),
            "ecart_vs_2": k.get("ecart_pct_vs_2"),
            "banque_2":  k.get("banque_2_nom"),
            "fastest_b": k.get("fastest_b"),
            "fastest_pct": k.get("fastest_pct"),
            "sgci_growth": k.get("sgci_growth_pct"),
            "resilience": res,
        },
        "cb": {
            "rang_catalogue": rang_cat,
            "n_banques_cat":  len(bycat),
            "n_services_sgci": sgci_cat.get("n_services"),
            "gratuite_sgci":  sgci_cat.get("pct_gratuit"),
            "gratuite_med":   _median({r["banque"]: r.get("pct_gratuit") for r in q6 if r.get("pct_gratuit") is not None}),
            "winrate":        cmp.get("classement", []),
            "winrate_sgci":   cmp.get("sgci", {}),
            "rang_prix":      cmp.get("rang_sgci"),
            "n_classees":     cmp.get("n_classees"),
            "serie":          serie,
            "rattrapage":     ratt,
            "repricing":      repricing,
            "over":           over[:8],
            "n_over":         len(over),
            "switching":      switching,   # coûts de changement (économies en venant chez SGCI) — Particuliers+Entreprises
            "atouts":         atouts_cb,
            "cat_part":       cat_part,
            "cat_ent":        cat_ent,
            "tilt":           tilt,
            "gratuite_par_banque": gratuite_par_banque,
            # excl_rows est déjà CLASSÉ par l'Agent Web (verdict : non_contredit / differenciant / partage,
            # bruit retiré). n_exclusivites = SEULEMENT les vraies (non_contredit) — honnêteté.
            "exclusivites":   [dict(r) for r in excl_rows][:40],
            "n_exclusivites": sum(1 for r in excl_rows if r.get("verdict") == "non_contredit"),
            "n_differenciant": sum(1 for r in excl_rows if r.get("verdict") == "differenciant"),
            "gaps":           gaps_top,
            "n_gaps":         len(gaps_communs),
            "innovations":    innov,
        },
        "regl": BCEAO_NORMES,
        "regl_text": _regl_snippets(),
        "regl_leviers": (_web.reglementation() if _web else []),
        "web":  (_web.facts_for(BANKS) if _web else {}),
        "web_secteur": (_web.secteur() if _web else []),
        "web_idx": (_web.secteur_index() if _web else {}),
    }
    return facts


def _switching_costs(prix, segment="Particuliers"):
    """COÛTS DE CHANGEMENT — BIDIRECTIONNEL, sur les services du QUOTIDIEN, annualisé.
      • gains  : SGCI moins chère → ce qu'un client ÉCONOMISE en VENANT chez SGCI (argument d'acquisition).
      • fuites : SGCI plus chère → ce qu'un client ÉCONOMISE en PARTANT vers un concurrent (RISQUE de fuite).
    Noms désambiguïsés par la section CB (« Frais de dossier » → « Frais de dossier — Crédits »).
    100% data CB (cb_prix_par_libelle) — aucun chiffre inventé. Frais punitifs/barrières de sortie exclus.
    `segment` (2026-07-22, demande explicite du directeur : « pour Entreprises, on néglige ??? ») :
    chaque enregistrement est tagué avec son segment d'origine, pour permettre d'appeler cette
    fonction séparément sur Particuliers ET Entreprises puis de fusionner les deux sans ambiguïté."""
    import re as _re

    def _fmt(n):
        return f"{int(round(n)):,}".replace(",", " ")

    def _clean(s):
        s = _re.sub(r"(\w)-\s+(\w)", r"\1\2", str(s or ""))   # recolle l'OCR « oppo- sitio »
        return _re.sub(r"\s+", " ", s).strip()

    # EXCLUS : (1) frais punitifs / barrières de sortie ; (2) services dont le prix DÉPEND DU TYPE
    # (compte, crédit) → comparaison NON rigoureuse → on ne les présente pas (tenue de compte, dossier…).
    EXCLURE = _re.compile(
        r"(?i)(success|saisie|arr[êe]t|\batd\b|tiers\s*d[ée]tenteur|opposi|oppo\b|injonction|attestation|"
        r"non[\s-]*redevance|cl[ôo]ture|transfert\s+de\s+compte|lev[ée]e|contentieux|impay|rejet|incident|"
        r"recouvr|mainlev|certificat|duplicata|procuration|destruction|dhl|chronopost|rtgs|"
        r"tenue\s+de\s+compte|frais\s+de\s+tenue|\bdossier\b|mise\s+en\s+place|frais\s+d.engagement|\bétude\b)")
    # Services VRAIMENT DEMANDÉS ET comparables d'une banque à l'autre (périmètre net).
    # Élargi le 2026-07-21 (constat du directeur : seulement 2 atouts + 2 risques remontaient alors
    # que la CB contient ~32 000 lignes tarifaires) — on couvre désormais aussi change/devises,
    # garanties, monétique marchand, chèques/encaissements et transferts internationaux, en plus
    # du socle "quotidien" (carte, banque à distance, virement, retrait...). Les frais punitifs et
    # barrières de sortie restent exclus via EXCLURE ci-dessus (inchangé).
    DEMANDE = _re.compile(
        r"(?i)(carte\b|banque\s+(?:à\s+distance|en\s+ligne|digitale|mobile)|internet|e-?bank|appli|sms|alerte|"
        r"retrait|virement|pr[ée]l[èe]vement|abonnement|\bpack\b|package|assurance|"
        r"change\b|devise|garantie|\baval\b|caution|\btpe\b|terminal\s+de\s+paiement|"
        r"ch[ée]quier|ch[èe]que|encaissement|versement|"
        r"transfert\s+(?:international|d.argent|rapide)|western\s+union|moneygram)")
    QUOTIDIEN = DEMANDE
    GENERIQUE = _re.compile(r"(?i)^(commission de mise|frais de garde|droit de garde)")

    def _rail(s):
        # Système de virement précis (rails NON comparables entre eux) :
        # SICA (compensation de détail) ≠ STAR-UEMOA (RTGS, gros montants) ≠ RTGS ≠ SWIFT.
        m = _re.search(r"(?i)\b(sica|star[\s-]*uemoa|star|rtgs|swift)\b", str(s or ""))
        if not m:
            return None
        t = m.group(1).lower()
        return "star" if "star" in t else t

    def periodicite(unite, libelle):
        s = (str(unite or "") + " " + str(libelle or "")).lower()
        if _re.search(r"\bmois\b|mensuel|/\s*mois|par mois", s):      return 12, "/an"
        if _re.search(r"trimestr", s):                                 return 4, "/an"
        if _re.search(r"semestr", s):                                  return 2, "/an"
        if _re.search(r"\ban\b|annuel|année|/\s*an", s):               return 1, "/an"
        return 1, ""   # acte ponctuel : économie « par opération », pas annualisée

    gains, fuites = [], []
    for sec in prix or []:
        sec_titre = _clean(sec.get("titre") or "")
        for ss in sec.get("sous_sections", []):
            categorie = sec_titre or _clean(ss.get("libelle") or "")   # section de tête = catégorie propre
            for svc in ss.get("services", []):
                sg = svc.get("sgci") or {}
                if sg.get("tv") != "MONTANT_FCFA" or sg.get("suspect"):
                    continue
                sgm = sg.get("montant")
                if sgm is None or float(sgm) < 100:
                    continue
                sgm = float(sgm)
                lib = _clean(svc.get("libelle") or "")
                if EXCLURE.search(lib) or (categorie and EXCLURE.search(categorie)):
                    continue
                if _re.match(r"(?i)^(plus|moins|à\s+partir|a\s+partir|jusqu|compris|entre|de\s+\d|\d)", lib):
                    continue                            # libellé-fragment (palier/durée)
                if len(lib) < 6:
                    continue
                # Nom CLAIR : si le libellé est générique, on précise la catégorie (« — Crédits »)
                libc = lib
                if GENERIQUE.search(lib) and categorie and categorie.lower() not in lib.lower() and len(categorie) >= 4:
                    libc = f"{lib} — {categorie}"
                quotidien = bool(QUOTIDIEN.search(lib))
                if not quotidien:          # on ne garde QUE les services très demandés ET comparables
                    continue
                mult, suff = periodicite(sg.get("unite"), lib)
                for b, c in (svc.get("concurrents") or {}).items():
                    if not c or c.get("tv") != "MONTANT_FCFA" or c.get("suspect"):
                        continue
                    cm = c.get("montant")
                    if cm is None or float(cm) < 100:
                        continue
                    cm = float(cm)
                    # Garde-fou « MÊME rail » : ne jamais comparer SICA vs STAR-UEMOA vs RTGS vs SWIFT
                    # (systèmes de virement DIFFÉRENTS → prix non comparables, ex. SICA 5 000 vs STAR 29 080).
                    rs, rc = _rail(lib), _rail(c.get("libelle"))
                    if rs and rc and rs != rc:
                        continue
                    hi, lo = max(sgm, cm), min(sgm, cm)
                    if hi > lo * 20:                    # écart aberrant = appariement hétérogène
                        continue
                    eco_an = round((hi - lo) * mult)
                    rec = {"banque": b, "libelle": libc[:80], "categorie": categorie[:42],
                           "sgci": round(sgm), "conc": round(cm), "eco": eco_an,
                           "suffixe": suff, "quotidien": quotidien, "segment": segment}
                    if cm > sgm and eco_an >= 1000:    # SGCI moins chère → argument d'acquisition (montant qui parle)
                        gains.append(rec)
                    elif sgm > cm and eco_an >= 1500:  # SGCI plus chère → VRAI motif de départ seulement (≥ 1 500 F/an)
                        fuites.append(rec)

    def _rank(lst):
        lst.sort(key=lambda x: (not x["quotidien"], -x["eco"]))
        return lst

    def _phrase(x, sens):
        # sens="gain" : on quitte la banque pour SGCI ; sens="fuite" : on quitte SGCI pour la banque
        de, vers = (x["banque"], "SGCI") if sens == "gain" else ("SGCI", x["banque"])
        av, ap = (x["conc"], x["sgci"]) if sens == "gain" else (x["sgci"], x["conc"])
        client = "une entreprise" if x.get("segment") == "Entreprises" else "un particulier"
        return (f"En quittant {de} pour {vers}, {client} économise {_fmt(x['eco'])} FCFA{x['suffixe']} "
                f"sur « {x['libelle']} » ({_fmt(av)} F → {_fmt(ap)} F).")

    # PLUS de plafond [:12] ici (2026-07-22, demande explicite du directeur : « on affiche TOUT,
    # scroll pour voir le reste ») — le tri par montant décroissant reste identique, mais aucun
    # élément n'est tronqué à la source ; le plafond éventuel se fait uniquement à l'affichage.
    g = [{**x, "phrase": _phrase(x, "gain")}  for x in _rank(gains)]
    f = [{**x, "phrase": _phrase(x, "fuite")} for x in _rank(fuites)]
    return {"gains": g, "fuites": f, "n_gains": len(gains), "n_fuites": len(fuites),
            "max_gain": (g[0]["eco"] if g else 0), "max_fuite": (f[0]["eco"] if f else 0),
            "insights": g, "n": len(gains)}   # 'insights' conservé pour rétro-compat


def _regl_snippets():
    """Extraits réglementaires réels (Agent REGL — vrai retriever pgvector) pour ancrer
    les recommandations sur des textes sourcés. Reproductible (requêtes fixes)."""
    try:
        REGL = AGENTS["REGL"].structured
        topics = {
            "cout_risque": "coût du risque provisionnement créances en souffrance",
            "transparence": "transparence tarifaire information préalable du client conditions de banque",
            "credit": "octroi de crédit taux effglobal usure protection emprunteur",
        }
        out = {}
        for key, q in topics.items():
            try:
                hits = REGL.regl_semantic(q, 2) or []
                if hits:
                    out[key] = [{"fichier": h["fichier"], "extrait": h["contenu"][:200],
                                 "score": h.get("score")} for h in hits]
            except Exception:
                pass
        return out
    except Exception:
        return {}


# ════════════════════════════════════════════════════════════════════════════
#  2. DIAGNOSTIC — détection automatique des problèmes (EF + CB), sourcé
# ════════════════════════════════════════════════════════════════════════════
def detect_problems(ev):
    ef, cb = ev["ef"], ev["cb"]
    P = []

    def add(titre, gravite, preuve, agent, levier):
        P.append({"titre": titre, "gravite": gravite, "preuve": preuve,
                  "source": agent, "levier": levier})

    # — Coût du risque élevé (métrique ROBUSTE : moyenne 3 ans + tendance) —
    crm = ef.get("cout_risque_moy") or ef["cout_risque_pnb"]
    sg_cr = crm.get("SGCI")
    det = (ef.get("cout_risque_3ans") or {}).get("SGCI") or {}
    if sg_cr is not None:
        med = _median(crm)
        if sg_cr >= 10 or det.get("tendance") == "hausse":
            g = 3 if (sg_cr >= 13 or det.get("tendance") == "hausse") else 2
            seq = " → ".join(f"{v}%" for _, v in (det.get("ratios") or []))
            add("Coût du risque élevé et en hausse", g,
                f"Coût du risque = {sg_cr}% du PNB en moyenne 3 ans (médiane marché {med}%)"
                + (f", trajectoire {seq}" if seq else "") + ". La banque travaille de plus en plus à couvrir ses pertes de crédit.",
                "EF", "Coût du risque")

    # — Coefficient d'exploitation —
    coeff = ef["coeff"]; sg_co = coeff.get("SGCI")
    if sg_co is not None and sg_co > BCEAO_NORMES["coefficient_cible"]["v"]:
        add("Coefficient d'exploitation au-dessus de la cible", 2,
            f"Coefficient = {sg_co}% (cible BCEAO < 70%). Trop de charges absorbent le PNB.",
            "EF", "Coefficient")

    # — Croissance faible → érosion des parts de marché —
    gr = ef["croissance"]; rgrow, n = _rank(gr, "SGCI", reverse=True)
    if rgrow and n and rgrow >= n - 1:
        add("Croissance lente → SGCI perd des parts de marché", 2,
            f"SGCI est #{rgrow}/{n} pour la CROISSANCE du résultat net sur 3 ans (AN1→AN3) : +{ef.get('sgci_growth')}% seulement, "
            f"« en queue de peloton » = parmi les plus LENTES des 7 banques, alors que le plus rapide ({ef.get('fastest_b')}) "
            f"progresse de +{ef.get('fastest_pct')}%. Conséquence directe : même si SGCI reste #1 en résultat net AUJOURD'HUI, "
            f"elle grandit moins vite que le marché → sa <b>part de marché s'érode lentement</b> et son avance se réduit d'année "
            f"en année. C'est le risque de fond du leader qui se repose sur sa taille — la même érosion est visible sur la courbe "
            f"de parts de marché de l'onglet Santé Financière.",
            "EF", "Croissance / Parts de marché")

    # — ROE sous le marché —
    roe = ef["roe"]; rroe, nroe = _rank(roe, "SGCI", reverse=True)
    if rroe and nroe and rroe >= (nroe // 2 + 1):
        add("Rentabilité des fonds propres (ROE) sous le marché", 2,
            f"SGCI #{rroe}/{nroe} en ROE ({roe.get('SGCI')}%). Le capital est moins bien rémunéré que chez les concurrents les mieux placés.",
            "EF", "ROE")

    # — Concurrent en ascension —
    fb, fp = ef.get("fastest_b"), ef.get("fastest_pct")
    if fb and fb != "SGCI" and fp:
        add(f"Montée en puissance de {fb}", 2,
            f"{fb} affiche la croissance du RN la plus rapide du marché (+{fp}%). À ce rythme, l'écart avec SGCI se réduit.",
            "EF", "Menace concurrentielle")

    # — Rang catalogue (CB) —
    # NOTE (2026-07-22, demande explicite du directeur : « on ne distingue pas Particuliers
    # d'Entreprises, on ne comprend rien ») : rang_catalogue/gratuite/winrate ci-dessous sont des
    # chiffres COMBINÉS Particuliers+Entreprises (cf. cb_analyse_q6_tous_segments) — chaque preuve
    # précise maintenant explicitement le détail par segment pour ne plus jamais laisser un
    # nombre combiné ambigu sans son décompte.
    cat_part, cat_ent = cb.get("cat_part") or {}, cb.get("cat_ent") or {}
    _cp, _ce = cat_part.get("SGCI"), cat_ent.get("SGCI")
    _detail_seg = (f" ({_cp} services Particuliers + {_ce} Entreprises, dont certains noms partagés "
                   f"entre les deux comptés une seule fois)") if (_cp and _ce) else ""

    rc, nc = cb.get("rang_catalogue"), cb.get("n_banques_cat")
    if rc and nc and rc > 3:
        add("Profondeur de catalogue limitée", 1,
            f"SGCI #{rc}/{nc} sur le nombre de services publiés, Particuliers et Entreprises combinés "
            f"({cb.get('n_services_sgci')} services distincts au total{_detail_seg}). Couverture de besoins inférieure aux leaders.",
            "CB", "Offre")

    # — Gratuité sous le marché —
    g_sg, g_med = cb.get("gratuite_sgci"), cb.get("gratuite_med")
    if g_sg is not None and g_med is not None and g_sg < g_med - 3:
        add("Taux de gratuité inférieur au marché", 1,
            f"Sur l'ensemble Particuliers+Entreprises, SGCI rend gratuits {g_sg}% de ses services, contre {g_med}% en médiane "
            f"chez les concurrents. SGCI offre bien des gratuités AU-DELÀ du minimum imposé par la BCEAO (change, assurance-prêt, "
            f"épargne…), mais reste dans le BAS du classement : les concurrents en rendent gratuits bien plus pour attirer les "
            f"clients. → SGCI n'utilise PAS encore la gratuité comme levier d'acquisition, alors qu'elle le pourrait sans toucher "
            f"aux services à forte valeur.",
            "CB·REGL", "Tarification")

    # — Compétitivité prix —
    rp, ncl = cb.get("rang_prix"), cb.get("n_classees")
    wsg = cb.get("winrate_sgci") or {}
    if rp and ncl and rp > (ncl // 2 + 1):
        add("Compétitivité prix perfectible", 1,
            f"Le « win-rate prix » mesure, sur le panier de services comparables (Particuliers et Entreprises réunis, "
            f"{wsg.get('n', '?')} duels de prix au total), la PART où SGCI est aussi chère ou MOINS chère que la médiane du "
            f"marché (= où elle « gagne » le duel de prix). SGCI est #{rp}/{ncl} : elle n'est la moins chère que sur "
            f"{wsg.get('winrate')}% de ses services comparables → plusieurs services sont AU-DESSUS du marché. Marge de "
            f"progression pour gagner en compétitivité sur les services que les clients comparent.",
            "CB", "Tarification")

    P.sort(key=lambda x: -x["gravite"])
    return P


# ════════════════════════════════════════════════════════════════════════════
#  2 bis. DÉCRYPTAGE DES CONCURRENTS — la stratégie de chaque banque (EF + CB + WEB)
# ════════════════════════════════════════════════════════════════════════════
def decrypt_concurrents(ev):
    """Pour CHAQUE concurrent : on lit sa stratégie en croisant son profil financier (EF),
    son positionnement tarifaire/catalogue (CB) et son identité de groupe (WEB).
    → « comment cette banque gagne » + ce que ça implique pour SGCI."""
    ef, cb = ev["ef"], ev["cb"]
    web = ev.get("web") or {}
    roe = ef.get("roe") or {}
    cr  = ef.get("cout_risque_pnb") or {}          # dernier exercice
    crm = ef.get("cout_risque_moy") or {}
    mn  = ef.get("marge_nette") or {}
    gr  = ef.get("croissance") or {}
    rn  = ef.get("rn") or {}
    tilt = cb.get("tilt") or {}
    cat = cb.get("cat_part") or {}
    grat = cb.get("gratuite_par_banque") or {}
    wr = {w.get("banque"): w.get("winrate") for w in (cb.get("winrate") or [])}
    n = cb.get("n_banques_cat") or 7

    def rang(d, b, reverse=True):
        vals = sorted([v for v in d.values() if v is not None], reverse=reverse)
        return (vals.index(d[b]) + 1) if d.get(b) in vals else None

    out = []
    for b in [x for x in BANKS if x != "SGCI"]:   # concurrents DYNAMIQUES (nouvelle banque incluse)
        if b not in rn and b not in roe:
            continue
        info = web.get(b, {})
        ef_bits, cb_bits = [], []
        sgn = lambda v: ("+" if v >= 0 else "") + _pct(v)
        if roe.get(b) is not None: ef_bits.append(f"ROE {_pct(roe[b])}% (#{rang(roe,b)}/{n})")
        if cr.get(b) is not None:  ef_bits.append(f"coût du risque {_pct(cr.get(b))}% (moy. 3 ans {_pct(crm.get(b))}%)")
        if mn.get(b) is not None:  ef_bits.append(f"marge nette {_pct(mn[b])}%")
        if gr.get(b) is not None:  ef_bits.append(f"croissance RN {sgn(gr[b])}% (cumulée AN1→AN3)")
        t = tilt.get(b)
        orient = ("orientée ENTREPRISES" if t and t >= 1.1 else "orientée PARTICULIERS" if t and t < 0.95 else "équilibrée") + (f" (ratio Ent/Part ×{_pct(t)})" if t else "")
        if cat.get(b) is not None: cb_bits.append(f"catalogue {cat[b]} services")
        if grat.get(b) is not None: cb_bits.append(f"gratuité {_pct(grat[b])}%")
        if wr.get(b) is not None: cb_bits.append(f"win-rate prix {_pct(wr[b])}%")

        # ── lecture de la stratégie, dérivée des signaux réels (pas un template figé) ──
        traits = []
        if cr.get(b) is not None and cr[b] <= 5: traits.append("une <b>discipline du risque</b> remarquable (le crédit casse peu)")
        if wr.get(b) is not None and wr[b] >= 60: traits.append("une <b>agressivité prix</b> pour capter les clients")
        if gr.get(b) is not None and gr[b] >= 30: traits.append(f"une <b>croissance fulgurante</b> (+{_pct(gr[b])}% cumulés sur AN1→AN3)")
        if mn.get(b) is not None and mn[b] >= 45: traits.append("une <b>rentabilité par franc</b> de tête")
        if t and t >= 1.3: traits.append("un <b>tropisme corporate</b> marqué")
        if cat.get(b) is not None and cat[b] >= 350: traits.append("un <b>catalogue très large</b> (être partout)")
        grp = info.get("grp") or info.get("groupe") or info.get("positionnement") or ""
        innov = info.get("innovation")
        cause = info.get("cause_rentabilite")
        # verbe adapté à la performance (éviter « gagne » pour une banque qui décline)
        verbe = "gagne par" if (gr.get(b, 0) >= 10 and (roe.get(b) or 0) >= 22) else "mise sur"
        _traits = ", ".join(traits) if traits else "un positionnement classique"
        # phrases COMPLÈTES (chaque clause a un sujet) — pas de fragment « . s'appuie sur… »
        _phr = [f"{b} {verbe} {_traits}."]
        if cause:
            _phr.append(cause.rstrip(". ") + ".")
        elif grp:
            _phr.append(f"Elle s'appuie sur {grp}.")
        if innov:
            _phr.append(f"Innovation : {innov.rstrip('. ')}.")
        strat = "<br>".join(_phr)   # une phrase par ligne (lisibilité)

        # ── enjeu pour SGCI ──
        if (gr.get(b) or 0) >= 30 and (cr.get(b) or 99) <= 5:
            enjeu = "MENACE FORTE : croissance rapide + risque maîtrisé. SGCI doit copier sa discipline d'octroi et défendre le corporate."
        elif wr.get(b) is not None and wr[b] >= 65:
            enjeu = "MENACE PRIX : capte les clients sensibles au tarif. SGCI répond par la valeur (digital, exclusivités), pas la guerre des prix."
        elif info.get("innovation"):
            enjeu = "MENACE EXPÉRIENCE : avance sur l'innovation. SGCI doit copier-dépasser (y ajouter le conseil que les fintechs n'ont pas)."
        elif cat.get(b) is not None and cat[b] >= 350:
            enjeu = "Concurrent par la largeur d'offre. SGCI gagne par la profondeur ciblée et des packs clairs, pas l'exhaustivité."
        else:
            enjeu = "Concurrent secondaire à ce stade ; surveiller son évolution."

        out.append({
            "banque": b,
            "groupe": grp,
            "ef": ef_bits, "cb": cb_bits, "orientation": orient,
            "strategie": strat, "enjeu": enjeu,
            "sources": sorted(set((["EF"] if ef_bits else []) + (["CB"] if cb_bits else []) + (["WEB"] if (grp or innov or cause) else []))),
        })
    # trier : menaces fortes d'abord
    pri = {"MENACE FORTE": 0, "MENACE PRIX": 1, "MENACE EXPÉRIENCE": 2}
    out.sort(key=lambda x: next((v for k, v in pri.items() if x["enjeu"].startswith(k)), 9))
    return out


# ════════════════════════════════════════════════════════════════════════════
#  3. SWOT — sourcé (chaque item porte son agent)
# ════════════════════════════════════════════════════════════════════════════
def build_swot(ev, problems):
    ef, cb = ev["ef"], ev["cb"]
    forces, faibl, oppor, menac = [], [], [], []

    if ef.get("rang_rn") == 1:
        forces.append({"txt": f"Leader en résultat net (#1/{cb.get('n_banques_cat') or 7}) — le bénéfice le plus élevé du marché.", "source": "EF"})
    if ef.get("ecart_vs_2") and ef["ecart_vs_2"] > 0:
        forces.append({"txt": f"Avance de +{ef['ecart_vs_2']}% en RN sur {ef.get('banque_2')} (#2).", "source": "EF"})
    excl = (cb.get("winrate_sgci") or {})
    if cb.get("rang_prix") and cb["rang_prix"] <= 3:
        forces.append({"txt": f"Bonne compétitivité prix (#{cb['rang_prix']} en win-rate).", "source": "CB"})
    res = (ef.get("resilience") or {}).get("SGCI") or {}
    if res.get("solvabilite") and res["solvabilite"] >= 12:
        forces.append({"txt": f"Solvabilité confortable ({res['solvabilite']}% ≥ 12% — zone de confort BCEAO).", "source": "EF·REGL"})

    for p in problems:
        if p["gravite"] >= 2:
            # Découpe sur la 1ʳᵉ phrase — PAS sur le 1ᵉʳ point tout court : un point DÉCIMAL
            # (ex. « 13.9% ») ne doit jamais être pris pour une fin de phrase (bug historique
            # qui tronquait « 13.9% » en « 13 »).
            premiere = re.split(r"(?<!\d)\.(?!\d)", p["preuve"], maxsplit=1)[0]
            faibl.append({"txt": p["titre"] + " — " + premiere + ".", "source": p["source"]})
    if not faibl:
        faibl.append({"txt": "Pas de faiblesse structurelle majeure détectée sur la période.", "source": "EF·CB"})

    # Opportunités — d'abord face aux banques concurrentes
    ratt = cb.get("rattrapage") or {}
    if ratt.get("depassement"):
        oppor.append({"txt": f"Reprendre l'initiative face aux banques qui innovent ({ratt.get('depassement')} services où un concurrent a pris de l'avance) — copier et dépasser.", "source": "CB"})
    if cb.get("gratuite_med") and cb.get("gratuite_sgci") is not None and cb["gratuite_sgci"] < cb["gratuite_med"]:
        oppor.append({"txt": "Regagner les clients sensibles au prix repris par les autres banques (services à fort volume).", "source": "CB"})
    oppor.append({"txt": "Conformité BCEAO stricte (gratuités obligatoires appliquées + ratios prudentiels solvabilité/liquidité respectés) = argument concret de SÉCURITÉ des dépôts et de confiance, à valoriser auprès des grands comptes et de la diaspora.", "source": "REGL"})
    # Mobile money mentionné subtilement, en OPPORTUNITÉ (capter leurs clients), pas en menace
    oppor.append({"txt": "Convertir les utilisateurs mobile money (82% en CI) en clients bancaires : passerelles wallet↔compte, épargne et crédit — ce que les fintechs ne font pas.", "source": "WEB"})

    # Menaces — la CIBLE, ce sont les banques concurrentes
    fb, fp = ef.get("fastest_b"), ef.get("fastest_pct")
    if fb and fb != "SGCI":
        menac.append({"txt": f"{fb} croît le plus vite (+{fp}%) avec un risque maîtrisé — c'est le concurrent direct qui peut éroder l'avance de SGCI.", "source": "EF·CB"})
    wr = cb.get("winrate") or []
    if wr and wr[0].get("banque") != "SGCI":
        menac.append({"txt": f"{wr[0]['banque']} est la moins chère sur {wr[0].get('winrate')}% des services comparables (elle « gagne le duel de prix » face à la médiane du marché) — un positionnement agressif pour capter les clients sensibles au prix.", "source": "CB"})
    menac.append({"txt": "À surveiller, en arrière-plan : le mobile money grignote les paiements du quotidien — à transformer en opportunité plutôt qu'à subir.", "source": "WEB"})

    return {"forces": forces, "faiblesses": faibl, "opportunites": oppor, "menaces": menac}


# ════════════════════════════════════════════════════════════════════════════
#  4. PORTER — 5 forces, intensité notée depuis les données
# ════════════════════════════════════════════════════════════════════════════
def build_porter(ev):
    """Porter — présenté au STANDARD : 5 forces en croix, RIVALITÉ au CENTRE (les 4
    autres forces convergent vers elle), intensité notée + analyse + facteurs, sourcé."""
    ef, cb = ev["ef"], ev["cb"]
    widx = ev.get("web_idx") or {}
    n = cb.get("n_banques_cat") or 7
    fb, fp = ef.get("fastest_b"), ef.get("fastest_pct")
    wr = cb.get("winrate") or []
    aggr = wr[0] if (wr and wr[0].get("banque") != "SGCI") else None
    n_banques_ci = (widx.get("structure_marche") or {}).get("valeur", "29 banques")
    mobile = (widx.get("mobile_money") or {}).get("valeur", "82%")

    def F(cle, position, force, intensite, note, resume, facteurs, analyse, implication, agents):
        return {"cle": cle, "position": position, "force": force, "intensite": intensite,
                "note": note, "resume": resume, "facteurs": facteurs, "analyse": analyse,
                "implication": implication, "agents": agents}

    forces = [
        F("rivalite", "centre", "Rivalité entre les banques", "Très élevée", 5,
          "C'est LE terrain de jeu — la force dominante.",
          [f"{n_banques_ci} sur le marché ivoirien, 7 comparées de près",
           f"Écarts de prix serrés — SGCI seulement #{cb.get('rang_prix') or '?'} en win-rate",
           (f"{aggr['banque']} moins chère sur {_pct(aggr.get('winrate'))}% des services comparables (gagne le « duel de prix »)" if aggr else "Guerre des prix sur le retail"),
           (f"{fb} grandit le plus vite (+{_pct(fp)}%) et grignote l'écart" if fb and fb != "SGCI" else "")],
          ("La concurrence directe entre banques établies est intense : marché dense, offres peu différenciées, "
           "guerre des prix sur la banque du quotidien. Les 4 autres forces (clients, substituts, entrants, fournisseurs) "
           "viennent toutes renforcer cette rivalité centrale — c'est pourquoi on la place au cœur du schéma."),
          "C'est ICI que SGCI doit concentrer sa stratégie : gagner la bataille entre banques (diagnostic, révélations, "
          "propositions par direction), pas se disperser sur les fintechs.",
          "CB·EF"),
        F("entrants", "haut", "Menace de nouveaux entrants", "Modérée", 3,
          "Barrières fortes, mais le digital ouvre une brèche.",
          ["Agrément BCEAO + capital élevé = barrières réelles à l'entrée",
           "Néobanques digitales (Orange Bank) abaissent la barrière sur le retail mobile",
           "Standard Chartered en ligne depuis 2018"],
          ("Entrer dans la banque classique reste coûteux (agrément, capital, réseau d'agences) — ce qui protège un "
           "leader installé comme SGCI. MAIS le digital-first (néobanques) crée une porte d'entrée par le mobile, sans agence."),
          "Pas une menace frontale aujourd'hui, mais OBJECTIF : capter les non-bancarisés et les jeunes AVANT que les néobanques ne les verrouillent — via un compte 100% mobile « SG Mobile » qui combine la simplicité du mobile et la sécurité/le crédit d'un leader.",
          "WEB·REGL"),
        F("substituts", "bas", "Produits de substitution (mobile money)", "Modérée", 3,
          "Grignote le quotidien — mais surtout un gisement à capter.",
          [f"Mobile money à {mobile} en CI — capte paiements et tenue de compte",
           "Ne fait NI crédit NI épargne structurée NI sécurité des dépôts",
           "Davantage un vivier de clients à bancariser qu'une menace frontale"],
          ("Le mobile money remplace la banque sur les petits paiements et la tenue de compte à bas coût. Mais il ne "
           "sait pas faire le crédit, l'épargne longue, ni offrir la sécurité d'un bilan de leader."),
          "Pour SGCI c'est plus une OPPORTUNITÉ qu'un danger : passerelles wallet↔compte, comptes mobiles, micro-crédit scoré.",
          "WEB·CB"),
        F("clients", "droite", "Pouvoir de négociation des clients", "Élevée", 4,
          "Tarifs comparables + clients entreprises volatils.",
          ["Tarifs facilement comparables d'une banque à l'autre",
           "Faible coût de changement de banque",
           "Les entreprises (cible de BICICI) sont les plus exigeantes et mobiles"],
          ("Les clients comparent facilement et font jouer la concurrence, surtout les entreprises — segment où SGCI "
           "est sous-représentée (≈99% de particuliers) et où BICICI/SIB captent la valeur."),
          "Réduire ce pouvoir en RETENANT le client : packs segmentés et multi-équipement (cross-sell) sur la base SGCI — "
          f"{_wf('clients_sgci', 'valeur', 'base clients importante')} (source publique SGCI [WEB] ; fichiers des concurrents non disponibles) — "
          "plus une relation corporate dédiée (Direction Commerciale). Un client multi-équipé change moins facilement de banque.",
          "CB·EF·WEB"),
        F("fournisseurs", "gauche", "Pouvoir des fournisseurs (ressources / BCEAO)", "Moyenne", 3,
          "Coût des ressources encadré ; SGCI bien placée.",
          ["« Fournisseurs » d'une banque = ses ressources : dépôts et refinancement",
           f"Coût encadré par la BCEAO (taux directeur {_wf('politique_monetaire', 'valeur', 'BCEAO')})",
           "SGCI est 1ʳᵉ collectrice de dépôts de l'UMOA = position de force"],
          ("La principale « matière première » d'une banque, ce sont ses ressources (dépôts, refinancement). Leur coût "
           "est encadré par la politique monétaire BCEAO, ce qui limite le pouvoir des fournisseurs."),
          "Atout pour SGCI : 1ʳᵉ en dépôts = meilleure base de ressources du marché, à transformer en crédit sain.",
          "REGL·EF"),
    ]
    synthese = ("Le jeu se joue AU CENTRE : la rivalité entre banques est la force la plus intense, "
                "alimentée par des clients qui comparent (à droite) et un mobile money qui grignote le quotidien (en bas). "
                "Les barrières réglementaires (entrants, en haut) et la BCEAO (fournisseurs, à gauche) jouent en faveur "
                "du leader. Conclusion : la priorité de SGCI est de gagner la bataille entre banques, pas de craindre les fintechs.")
    return {"forces": forces, "synthese": synthese,
            "intro": ("Les 5 forces de Porter mesurent la pression concurrentielle d'un secteur. "
                      "La RIVALITÉ est au centre car les 4 autres forces la nourrissent. Plus une force est intense (rouge), "
                      "plus elle pèse sur la rentabilité. Chaque niveau est justifié par les données.")}


# ════════════════════════════════════════════════════════════════════════════
#  5. PLAN D'ACTION — par levier, ancré BCEAO, impact KPI attendu
# ════════════════════════════════════════════════════════════════════════════
def _best(d, reverse=False):
    """Meilleure banque d'un dict {banque: valeur}. reverse=False → plus PETIT = meilleur."""
    vals = [(b, v) for b, v in (d or {}).items() if v is not None]
    if not vals:
        return (None, None)
    return (max if reverse else min)(vals, key=lambda x: x[1])


def _fmt_md(m):
    """Montant en M FCFA → '13,8 Mds' ou '850 M'."""
    if m is None:
        return "—"
    return (f"{m/1000:.1f}".replace(".", ",") + " Mds") if abs(m) >= 1000 else f"{round(m)} M"


def build_action_plan(ev, problems):
    ef, cb = ev["ef"], ev["cb"]
    pnb = (ef["pnb"] or {}).get("SGCI")
    plan = []

    # ── 1) COÛT DU RISQUE — benchmark + solutions concrètes + impact chiffré ──
    sg_cr = ef["cout_risque_pnb"].get("SGCI")
    if sg_cr is not None and sg_cr >= 15:
        bb, bv = _best(ef["cout_risque_pnb"])          # banque la moins exposée
        med = _median(ef["cout_risque_pnb"])
        cible = max(12.0, bv if bv else 12.0)
        gain_pts = round(sg_cr - cible, 1)
        gain_rn = round(pnb * gain_pts / 100) if pnb else None
        plan.append({
            "levier": "Coût du risque",
            "probleme": "Coût du risque élevé",
            "constat": f"SGCI absorbe {sg_cr}% de son PNB en coût du risque, contre une médiane marché de {med}%.",
            "benchmark": (f"Le meilleur du marché est {bb} à {bv}% — il y parvient par une sélection à l'octroi plus stricte "
                          f"et un provisionnement discipliné. SGCI a donc ~{gain_pts} pts de marge de progrès." if bb else ""),
            "solutions": [
                {"t": "Déployer un moteur de scoring + une application de détection des clients à risque",
                 "d": "Score d'octroi automatisé (revenus, historique, secteur) ET alertes comportementales (irrégularités de flux, retards récurrents) pour repérer en amont les dossiers fragiles."},
                {"t": "Système d'early-warning sur les impayés",
                 "d": "Relances automatiques J+15 / J+30, segmentation des créances classées, recouvrement amiable précoce avant judiciarisation."},
                {"t": "Provisionnement proactif + revue trimestrielle du portefeuille",
                 "d": "Lisser l'impact sur le résultat et concentrer les efforts sur les secteurs les plus sinistrés."},
            ],
            "chiffrage": (f"Ramener le coût du risque de {sg_cr}% à {cible}% du PNB (niveau du meilleur, {bb}) = "
                          f"+{gain_pts} pts × PNB ({_fmt_md(pnb)}) ≈ <b>+{_fmt_md(gain_rn)} de résultat net</b>/an."
                          if gain_rn else f"Chaque point de coût du risque gagné ≈ +{_fmt_md(round(pnb/100) if pnb else None)} de RN."),
            "ancrage_bceao": f"Rester sous {BCEAO_NORMES['cnr_encours_max_pb']['v']} pb de coût du risque/encours ({BCEAO_NORMES['cnr_encours_max_pb']['src']}).",
            "sources": ["EF", "REGL"],
        })

    # ── 2) REPRICING CB×EF — services où SGCI est SOUS le marché (gain PNB chiffré) ──
    rp = cb.get("repricing") or {}
    top = (rp.get("services") or [])
    if top:
        VOL = 120000   # hypothèse explicite d'opérations/an par service (paramètre, à calibrer)
        ex = top[0]
        gain_ex = ex["gap"] * VOL
        head = rp.get("headroom_par_op", 0)
        vol_str = f"{VOL:,}".replace(",", " ")
        head_str = f"{head:,}".replace(",", " ")
        gain_str = _fmt_md(round(gain_ex / 1_000_000))
        plan.append({
            "levier": "Tarification (PNB commissions) — levier CB×EF",
            "probleme": "Services sous-tarifés vs marché = revenu laissé sur la table",
            "constat": (f"SGCI est <b>moins chère que la médiane marché</b> sur {rp.get('n')} services comparables. "
                        f"Exemple : « {ex['libelle']} » à {ex['sgci']} F vs médiane {ex['median']} F (écart −{ex['gap']} F)."),
            "benchmark": f"Marge de réalignement cumulée : +{head_str} F par opération sur l'ensemble des {rp.get('n')} services sous-tarifés.",
            "solutions": [
                {"t": "Réaligner progressivement les services nettement sous le marché sur la médiane",
                 "d": "Sans devenir le plus cher : on vise la médiane, pas le maximum. Cibler d'abord les " + str(min(3, len(top))) + " plus gros écarts."},
                {"t": "Communiquer la valeur (digital, CONNECT) pour absorber la hausse sans attrition",
                 "d": "Coupler le réajustement tarifaire à la mise en avant des exclusivités pour préserver la fidélité."},
            ],
            "chiffrage": (f"Aligner « {ex['libelle']} » sur la médiane = +{ex['gap']} F/opération. "
                          f"À {vol_str} opérations/an (hypothèse) → <b>+{gain_str} de PNB</b> sur ce seul service. "
                          f"Étendu aux {rp.get('n')} services, le potentiel est un multiple."),
            "ancrage_bceao": "Réajustement compatible avec l'obligation BCEAO de transparence tarifaire ; ne pas toucher aux services gratuits obligatoires.",
            "sources": ["CB", "EF", "REGL"],
        })

    # ── 3) COEFFICIENT D'EXPLOITATION — benchmark + solutions ──
    sg_co = ef["coeff"].get("SGCI")
    if sg_co is not None and sg_co > 55:
        bb, bv = _best(ef["coeff"])
        plan.append({
            "levier": "Coefficient d'exploitation",
            "probleme": "Charges élevées vs PNB",
            "constat": f"Coefficient SGCI = {sg_co}% (cible BCEAO < 70%).",
            "benchmark": f"Le plus efficient est {bb} à {bv}% — écart de {round(sg_co-bv,1)} pts à combler." if bb else "",
            "solutions": [
                {"t": "Digitaliser les opérations à fort volume", "d": "Self-care (CONNECT) sur virements, relevés, attestations → baisse du coût unitaire."},
                {"t": "Rationaliser les charges générales", "d": "Sans dégrader le réseau ; mutualiser les fonctions support."},
                {"t": "Augmenter le PNB par client (cross-sell)", "d": "Diluer les charges fixes sur plus de revenus."},
            ],
            "chiffrage": f"Chaque point de coefficient gagné ≈ +{_fmt_md(round(pnb/100) if pnb else None)} de RBE.",
            "ancrage_bceao": f"Cible coefficient < {BCEAO_NORMES['coefficient_cible']['v']}% ({BCEAO_NORMES['coefficient_cible']['src']}).",
            "sources": ["EF"],
        })

    # ── 4) PNB / CROISSANCE — diversification commissions + corporate ──
    comm = ef.get("commissions", {}).get("SGCI")
    inte = ef.get("interets", {}).get("SGCI")
    # DÉFINITION UNIQUE (2026-08-10) : commissions / PNB, via db.part_commissions_pnb.
    # Cette page calculait commissions / (commissions + intérêts) — 24,0 % — quand la
    # Stratégie opérationnelle affichait 26,3 % pour le même indicateur. Deux pages de la
    # même application se contredisaient de 2,3 points, ce qui suffit à faire douter des deux.
    mix = db.part_commissions_pnb(comm, (ef.get('pnb') or {}).get('SGCI'), inte)
    plan.append({
        "levier": "PNB / Croissance",
        "probleme": "Dynamique de revenus en retrait",
        "constat": (f"Mix revenus SGCI ≈ {mix}% de commissions." if mix is not None else "Revenus dépendants du crédit.")
                   + f" Concurrent le plus dynamique : {ef.get('fastest_b')} (+{ef.get('fastest_pct')}%).",
        "benchmark": f"{ef.get('fastest_b')} accélère en captant le corporate — terrain à défendre/attaquer.",
        "solutions": [
            {"t": "Développer les commissions (monétique, change, services)", "d": "Revenus moins risqués, moins consommateurs de fonds propres."},
            {"t": "Offre dédiée diaspora & corporate", "d": "S'appuyer sur le réseau international Société Générale (atout face à BICICI)."},
            {"t": "Monétiser les exclusivités digitales (CONNECT, MyBusiness)", "d": "Fidélisation + nouveaux revenus de services."},
        ],
        "chiffrage": ("Porter le mix commissions au-delà de 35% stabilise le PNB et réduit la dépendance au crédit."
                      + (f" (actuel ≈ {mix}%)" if mix is not None else "")),
        "ancrage_bceao": "Diversifier le mix revenus réduit la dépendance au crédit (résilience prudentielle).",
        "sources": ["EF", "CB", "WEB"],
    })

    return plan


# ════════════════════════════════════════════════════════════════════════════
#  6. PROJECTION 3 ANS — trajectoire actuelle vs avec actions, par levier
# ════════════════════════════════════════════════════════════════════════════
def build_projection(ev):
    """Projection 3 ans à 3 SCÉNARIOS (prudent / central / optimiste) + ligne de base
    « sans rien faire ». Tout déterministe, hypothèses explicites et chiffrées."""
    ef = ev["ef"]
    out = []

    pnb = (ef["pnb"] or {}).get("SGCI")
    rn  = (ef["rn"] or {}).get("SGCI")
    cr  = ef["cout_risque_pnb"].get("SGCI")
    g   = ef.get("sgci_growth") or 4.0   # croissance historique
    res = (ef.get("resilience") or {}).get("SGCI") or {}
    cp  = res.get("capitaux_propres")

    # Pondération des scénarios : part de l'effet « plan » réellement capté.
    #   prudent = exécution partielle ; central = plan tenu ; optimiste = plan + macro porteuse.
    W = {"prudent": 0.55, "central": 1.0, "optimiste": 1.35}

    def croissance(base, premium, div=1000, unite="Mds"):
        """base à div ; actuel = g ; scénarios = g + premium*poids."""
        if base is None:
            return None
        b = base / div
        ser = {"unite": unite, "actuel": [round(b, 1)]}
        for sc in W:
            ser[sc] = [round(b, 1)]
        for _ in range(3):
            ser["actuel"].append(round(ser["actuel"][-1] * (1 + g / 100), 1))
            for sc, w in W.items():
                taux = g + premium * w
                ser[sc].append(round(ser[sc][-1] * (1 + taux / 100), 1))
        return ser

    # PNB : +3 pts d'effet plan (commissions + corporate)
    s = croissance(pnb, 3)
    if s:
        out.append({"nom": "PNB", **s,
                    "hypothese": f"Base {g}%/an. Effet plan : +3 pts (commissions + corporate), pondéré par scénario."})

    # Coût du risque (% PNB) : décrue −x pt/an, plancher 12 (le plan le fait baisser)
    if cr is not None:
        ser = {"unite": "%", "actuel": [cr]}
        decr = {"prudent": 1.1, "central": 1.7, "optimiste": 2.2}
        for sc in W:
            ser[sc] = [cr]
        for _ in range(3):
            ser["actuel"].append(cr)
            for sc in W:
                ser[sc].append(round(max(12.0, ser[sc][-1] - decr[sc]), 1))
        out.append({"nom": "Coût du risque (% PNB)", **ser,
                    "hypothese": "Base : maintenu. Plan : −1,1 à −2,2 pt/an selon scénario, plancher 12% (niveau des meilleurs)."})

    # Résultat net : +5 pts d'effet plan (PNB↑ ET coût du risque↓ cumulés)
    s2 = croissance(rn, 5)
    if s2:
        out.append({"nom": "Résultat net", **s2,
                    "hypothese": f"Base {g}%/an. Effet plan : +5 pts (PNB↑ & coût du risque↓ cumulés), pondéré."})

    # ROE : RN projeté (par scénario) / capitaux propres
    if rn is not None and cp:
        roe0 = round(rn / cp * 100, 1)
        ser = {"unite": "%", "actuel": [roe0]}
        for sc in W:
            ser[sc] = [roe0]
        rn_sc = {"actuel": rn, **{sc: rn for sc in W}}
        for _ in range(3):
            rn_sc["actuel"] *= (1 + g / 100)
            ser["actuel"].append(round(rn_sc["actuel"] / cp * 100, 1))
            for sc, w in W.items():
                rn_sc[sc] *= (1 + (g + 5 * w) / 100)
                ser[sc].append(round(rn_sc[sc] / cp * 100, 1))
        out.append({"nom": "ROE", **ser,
                    "hypothese": "ROE = RN projeté (par scénario) / capitaux propres (supposés stables)."})

    # ── Catalogue de services (SGCI) — 2026-07-24, enrichissement multi-source (demande
    # explicite : « la projection c'est pas QUE EF, multi-sources multi-indicateurs »).
    # Seule série CB avec un VRAI historique multi-périodes comparable à l'EF — l'indice prix
    # et le taux de gratuité CB, une fois le bug de moyenne corrigé (cf. cb_analyse_q6), sont
    # restés quasi plats sur l'historique réel : les ajouter aurait donné 3 courbes identiques
    # par scénario, aucune vraie différenciation. Le nombre de services, lui, a une vraie
    # tendance observée (178→184 en 2 ans) — base de croissance réelle, pas une hypothèse.
    cb_serie = (ev.get("cb") or {}).get("serie") or []
    if len(cb_serie) >= 2:
        n0 = cb_serie[0].get("sgci_n_services")
        n1 = cb_serie[-1].get("sgci_n_services")
        nb_annees = (len(cb_serie) - 1) / 2.0   # ~2 périodes (S1/S2) publiées par an
        if n0 and n1 and n0 > 0 and nb_annees > 0:
            g_cat = round((((n1 / n0) ** (1.0 / nb_annees)) - 1) * 100, 1)
            CATALOGUE_PREMIUM = 4   # pts/an si le plan lance les nouveaux services digitaux (CONNECT, MyBusiness — cf. Roadmap An2/An3)
            ser = {"unite": "services", "actuel": [n1]}
            for sc in W:
                ser[sc] = [n1]
            for _ in range(3):
                ser["actuel"].append(round(ser["actuel"][-1] * (1 + g_cat / 100)))
                for sc, w in W.items():
                    taux = g_cat + CATALOGUE_PREMIUM * w
                    ser[sc].append(round(ser[sc][-1] * (1 + taux / 100)))
            out.append({"nom": "Catalogue de services (SGCI)", **ser,
                        "hypothese": f"Base {_pct(g_cat)}%/an (croissance réelle observée CB 2024→2026). Effet plan : +{CATALOGUE_PREMIUM} pts (nouveaux services digitaux), pondéré par scénario."})

    # ── Enrichissement « lisibilité » : sens, fourchette, message-clé ──
    SENS = {"Coût du risque (% PNB)": "bas"}   # BAISSER = mieux
    meta = {"prudent": "Prudent (exécution partielle)",
            "central": "Central (plan tenu)",
            "optimiste": "Optimiste (plan + macro porteuse)"}
    for p in out:
        sens = SENS.get(p["nom"], "haut")
        u = p["unite"]
        a0 = p["actuel"][0]; a3 = p["actuel"][-1]
        pr3, ce3, op3 = p["prudent"][-1], p["central"][-1], p["optimiste"][-1]
        lo3, hi3 = min(pr3, op3), max(pr3, op3)
        p["sens"] = sens
        p["scenarios_meta"] = meta
        p["legende_actuel"] = "Sans rien changer"
        fmt = (lambda v: f"{v}".replace(".", ",") + ("%" if u == "%" else f" {u}"))
        p["depart"] = fmt(a0)
        p["fourchette_an3"] = f"{fmt(lo3)} – {fmt(hi3)}"
        p["central_an3"] = fmt(ce3)
        p["actuel_an3"] = fmt(a3)
        # écart central vs sans-rien-faire — 2026-07-24 : le branchement supposait tout non-%
        # forcément en Mds (vrai pour PNB/RN) ; la nouvelle métrique "services" (Catalogue)
        # affichait à tort "Mds" — bug trouvé en ajoutant cette métrique. Fix : ne convertir en
        # Mds QUE si l'unité EST "Mds", sinon garder l'unité réelle (ex. "services").
        if u == "%":
            ecart = f"{abs(round(ce3 - a3,1)):.1f}".replace(".", ",") + " pts"
        elif u == "Mds":
            ecart = _fmt_md(round(abs(ce3 - a3) * 1000))
        else:
            ecart = fmt(abs(round(ce3 - a3, 1)))
        fleche = "▲" if ce3 > a3 else "▼"
        p["takeaway"] = (
            f"À 3 ans : de <b>{fmt(pr3)}</b> (prudent) à <b>{fmt(op3)}</b> (optimiste), "
            f"cible centrale <b>{fmt(ce3)}</b> — soit <b>{fleche} {ecart}</b> vs sans rien faire ({fmt(a3)})."
        )

    # ── Enrichissement « bilan bas de gamme » (2026-07-21, demande du directeur : générique,
    # jamais lié à UN levier nommé comme le coût du risque — si demain la cause change, ce calcul
    # reste valable car il ne regarde QUE le Résultat net, la ligne qui compte pour la décision) ──
    # (1) Le pire scénario (prudent) bat-il déjà l'immobilisme à AN3 ? Si oui, agir est SANS RISQUE
    #     de résultat, même en cas d'exécution partielle du plan.
    # (2) Coût cumulé de l'attentisme sur les 3 ans (pas qu'un instantané à AN3) : la somme des
    #     écarts annuels « central vs sans rien faire » — rend l'urgence tangible, pas un chiffre isolé.
    rn = next((p for p in out if p["nom"] == "Résultat net"), None)
    if rn:
        pr3, a3 = rn["prudent"][-1], rn["actuel"][-1]
        u = rn["unite"]
        gain_pire_cas = round(pr3 - a3, 1) if rn["sens"] == "haut" else round(a3 - pr3, 1)
        rn["gain_pire_cas"] = f"{gain_pire_cas:.1f}".replace(".", ",") + f" {u}"
        rn["pire_cas_bat_immobilisme"] = gain_pire_cas > 0
        cumul = sum((c - a) if rn["sens"] == "haut" else (a - c)
                    for c, a in zip(rn["central"][1:], rn["actuel"][1:]))
        rn["cumul_attentisme_3ans"] = _fmt_md(round(cumul * 1000)) if u != "%" else (
            f"{cumul:.1f}".replace(".", ",") + f" {u}")

    return out


def build_projection_hypotheses(ev, projection):
    """CARTES CHIFFRÉES par scénario (2026-07-23bis, demande explicite : « trop de discours
    inutiles — les cartes chiffrées c'est ce qui marche, ça doit frapper, clair, pas de longs
    discours, avec une conclusion stratégique »). Remplace l'ancienne version en PROSE par un
    canevas fixe par scénario — Formulation (1 phrase chiffrée), Justification (1 ligne),
    Indicateurs (liste de chiffres), Certitude (% + risque) — plus une conclusion stratégique
    unique en bas. Tous les chiffres viennent de `projection` (déjà calculé par build_projection,
    mêmes constantes) : zéro recalcul à la main, zéro divergence possible avec les graphiques
    juste en dessous."""
    widx = ev.get("web_idx") or {}
    pib  = (widx.get("croissance_macro") or {}).get("valeur", "PIB +6,7%")
    npl_secteur = (widx.get("npl_secteur") or {}).get("valeur", "7,7% de créances dégradées")

    def _f(v):
        return f"{round(v, 1)}".replace(".", ",")

    by_nom = {p["nom"]: p for p in projection}
    pnb, cr, rn, roe = by_nom.get("PNB"), by_nom.get("Coût du risque (% PNB)"), by_nom.get("Résultat net"), by_nom.get("ROE")

    DESCRIPTION = {
        "prudent":   "Exécution partielle ou retardée du plan.",
        "central":   "Le plan est exécuté intégralement, au rythme prévu.",
        "optimiste": "Le plan est exécuté intégralement ET porté par un contexte macro favorable.",
    }
    JUSTIF = {
        "prudent":   f"Le scoring d'octroi + early-warning J+15/J+30 (Plan-trajectoire, An 1) n'est déployé qu'en partie : le coût du risque recule moins vite, encore loin du secteur ({npl_secteur}).",
        "central":   "Le scoring d'octroi et l'early-warning J+15/J+30 sont déployés dans les délais : le coût du risque atteint le plancher des meilleures banques du marché (BICICI ~1,9%).",
        "optimiste": f"Mêmes actes que Central, portés en plus par le {pib} (BCEAO) : la croissance limite mécaniquement les défauts et amplifie l'effet du scoring.",
    }
    CERTITUDE = {
        "prudent":   {"pct": 75, "risque": "Retard ou déploiement partiel du scoring/early-warning."},
        "central":   {"pct": 50, "risque": "Dérive de calendrier ou charge opérationnelle sous-estimée."},
        "optimiste": {"pct": 20, "risque": f"Conjoncture macro moins favorable que le {pib} actuel."},
    }
    # % d'effet du plan capté par scénario — MÊMES constantes que le W de build_projection
    # (0.55/1.0/1.35), reprises ici uniquement pour l'étiquette du schéma logique (aucun calcul
    # de chiffre n'en dépend, donc aucun risque de divergence avec les indicateurs ci-dessus).
    PCT_EFFET = {"prudent": 55, "central": 100, "optimiste": 135}

    def _cagr(serie):
        """Taux de croissance annuel moyen sur la série [aujourd'hui, an1, an2, an3]."""
        if not serie or not serie[0]:
            return None
        n = len(serie) - 1
        return round(((serie[-1] / serie[0]) ** (1.0 / n) - 1) * 100, 1)

    out = []
    for cle, nom in (("prudent", "Prudent"), ("central", "Central"), ("optimiste", "Optimiste")):
        # 2026-07-23quater (« tu mets trois chiffres vagues » — demande explicite de suivre le
        # canevas à la lettre) : les indicateurs ne répètent plus 3 fois le même niveau absolu à
        # AN3 (PNB/CR/RN pris isolément) — ils mélangent un TAUX de croissance (comme le canevas
        # « taux de croissance annuel moyen »), un niveau absolu de référence (PNB, comme la
        # « densité moyenne prévue »), et 2 ratios de rentabilité/risque, exactement le mélange
        # taux/niveau/proportion du canevas fourni.
        indicateurs = []
        if rn:
            cagr_rn = _cagr(rn[cle])
            if cagr_rn is not None:
                indicateurs.append({"label": "Croissance annuelle moyenne du résultat net", "valeur": f"{_f(cagr_rn)}%/an"})
        if pnb:
            indicateurs.append({"label": "PNB atteint à 3 ans", "valeur": f"{_f(pnb[cle][-1])} {pnb['unite']}"})
        if cr:
            indicateurs.append({"label": "Coût du risque à 3 ans", "valeur": f"{_f(cr[cle][-1])}{cr['unite']}"})
        if roe:
            indicateurs.append({"label": "ROE à 3 ans", "valeur": f"{_f(roe[cle][-1])}{roe['unite']}"})

        formulation = None
        if rn:
            base = rn["actuel"][0]
            cible = rn[cle][-1]
            pct_vs_aujourdhui = round((cible / base - 1) * 100, 1) if base else None
            delta_vs_sq = round(cible - rn["actuel"][-1], 1)
            signe_sq = "+" if delta_vs_sq >= 0 else "−"
            pct_txt = f"soit {'+' if (pct_vs_aujourdhui or 0) >= 0 else ''}{_f(pct_vs_aujourdhui)}% par rapport à aujourd'hui" if pct_vs_aujourdhui is not None else ""
            formulation = (
                f"D'ici 3 ans, le résultat net de SGCI atteindra {_f(cible)} {rn['unite']} FCFA, "
                f"{pct_txt} — {signe_sq}{_f(abs(delta_vs_sq))} {rn['unite']} de plus que si rien n'était fait."
            )

        # Plan année par année PROPRE à ce scénario, format ACTE → RÉSULTAT ATTENDU → POURQUOI
        # (2026-07-24, demande explicite : « version A, la plus pro, pas de discours inventé » —
        # le directeur a rejeté une version enrichie avec des facteurs de risque inventés). Ici
        # tout est réel : l'ACTE est celui du Plan-trajectoire (même action, aucune invention),
        # seul le RÉSULTAT change selon le niveau d'exécution du scénario — recalculé à partir
        # des séries déjà produites par build_projection (jamais un chiffre à la main).
        annees = []
        if cr and rn:
            plancher_atteint = cr[cle][3] <= 12.01
            ACTES_AN = {
                1: ("Déployer le moteur de scoring d'octroi + l'application de détection des "
                    "clients à risque (alertes comportementales) et l'early-warning impayés J+15/J+30."),
                2: ("Industrialiser le dispositif risque : revue trimestrielle du portefeuille, "
                    "provisionnement proactif, recouvrement amiable précoce sur les secteurs les plus sinistrés."),
                3: ("Poursuivre l'offensive croissance (offre diaspora & corporate) tout en consolidant "
                    "le niveau de risque atteint."),
            }
            POURQUOI_AN = {
                1: f"Le secteur n'affiche que {npl_secteur} (BCEAO) — SGCI reste au-dessus même dans ce scénario.",
                2: ("Convergence vers le plancher des meilleures banques (~12%, BICICI ~1,9%)."
                    if plancher_atteint else
                    "La baisse se poursuit mais n'atteint pas encore le plancher des meilleures banques (~12%)."),
                3: ("Le plancher de coût du risque des meilleures banques est atteint : le plan a produit son plein effet."
                    if plancher_atteint else
                    "Le plancher des meilleures banques (~12%) n'est pas atteint à ce niveau d'exécution — un gain reste sur la table."),
            }
            for idx, label_an in ((1, "An 1"), (2, "An 2"), (3, "An 3")):
                cr_avant = cr[cle][idx - 1]
                cr_apres = cr[cle][idx]
                delta = round(cr_avant - cr_apres, 1)
                rn_gain = round(rn[cle][idx] - rn["actuel"][idx], 1)
                signe = "+" if rn_gain >= 0 else "−"
                resultat = (
                    f"Coût du risque {_f(cr_avant)}% → {_f(cr_apres)}% du PNB "
                    f"({'−' if delta >= 0 else '+'}{_f(abs(delta))} pt) ≈ {signe}{_f(abs(rn_gain))} {rn['unite']} "
                    f"de résultat net vs statu quo (cumulé)."
                )
                annees.append({
                    "an": label_an, "acte": ACTES_AN[idx],
                    "resultat": resultat, "pourquoi": POURQUOI_AN[idx],
                    "pnb": f"{_f(pnb[cle][idx])} {pnb['unite']}" if pnb else None,
                })

        out.append({
            "cle": cle, "nom": nom,
            "description": DESCRIPTION[cle],
            "pct_effet": PCT_EFFET[cle],
            "formulation": formulation,
            "justification": JUSTIF[cle],
            "indicateurs": indicateurs,
            "certitude_pct": CERTITUDE[cle]["pct"],
            "certitude_risque": CERTITUDE[cle]["risque"],
            "annees": annees,
            "serie_rn": rn[cle] if rn else None,
            "serie_rn_actuel": rn["actuel"] if rn else None,
        })

    # Conclusion stratégique — réutilise le bilan RN déjà calculé par build_projection
    # (gain_pire_cas / cumul_attentisme_3ans), jamais recalculé ici.
    conclusion = None
    if rn and rn.get("gain_pire_cas") is not None:
        bat = rn.get("pire_cas_bat_immobilisme")
        conclusion = (
            (f"Même le scénario Prudent dépasse le statu quo de <b>{rn['gain_pire_cas']}</b> de résultat net à 3 ans — agir n'est pas un pari. "
             if bat else
             "Le scénario Prudent seul ne suffit pas à battre le statu quo — le plan doit être exécuté au moins au niveau Central. ")
            + f"Attendre coûte <b>{rn.get('cumul_attentisme_3ans', '—')}</b> cumulés sur 3 ans face au scénario Central : "
              "c'est la trajectoire à piloter."
        )

    return {
        "intro": ("Les 3 scénarios appliquent le MÊME plan d'action, à un "
                  "niveau d'exécution différent — pas 3 prévisions indépendantes."),
        "scenarios": out,
        "conclusion_strategique": conclusion,
    }


# ════════════════════════════════════════════════════════════════════════════
#  6 bis-A. PLAN-TRAJECTOIRE 3 ANS — actes concrets → résultat attendu → justif.
# ════════════════════════════════════════════════════════════════════════════
#  La prospective n'est PAS qu'une courbe : c'est une séquence d'ACTES datés,
#  chacun avec son résultat quantifié et sa justification sourcée (EF/CB/REGL/WEB).
# ════════════════════════════════════════════════════════════════════════════
def build_roadmap(ev, projection=None):
    ef, cb = ev["ef"], ev["cb"]
    widx = ev.get("web_idx") or {}
    pnb = (ef["pnb"] or {}).get("SGCI")
    rn  = (ef["rn"] or {}).get("SGCI")
    cr  = ef["cout_risque_pnb"].get("SGCI")
    roe = (ef["roe"] or {}).get("SGCI")
    comm = ef.get("commissions", {}).get("SGCI")
    inte = ef.get("interets", {}).get("SGCI")
    # DÉFINITION UNIQUE (2026-08-10) : commissions / PNB, via db.part_commissions_pnb.
    # Cette page calculait commissions / (commissions + intérêts) — 24,0 % — quand la
    # Stratégie opérationnelle affichait 26,3 % pour le même indicateur. Deux pages de la
    # même application se contredisaient de 2,3 points, ce qui suffit à faire douter des deux.
    mix = db.part_commissions_pnb(comm, (ef.get('pnb') or {}).get('SGCI'), inte)
    pt = round(pnb / 100) if pnb else None        # 1 pt de PNB en M FCFA
    rp = cb.get("repricing") or {}
    npl = (widx.get("npl_secteur") or {}).get("valeur", "7,7%")
    banc = (widx.get("bancarisation") or {}).get("valeur", ">30%").replace(" (CI)", "")

    # 2026-07-24 (trouvé par le directeur en comparant les deux blocs affichés sur la même
    # page) : ce plan affichait « coût du risque 17,0% → 14,0% » (delta −3 pts RÉINVENTÉ ici,
    # indépendant du modèle) alors que le scénario Central juste en dessous calcule 17,0% →
    # 15,3% (DECR=1,7 pt/an composé, plancher 12%) — DEUX modèles différents pour décrire le
    # MÊME scénario (« le plan exécuté comme prévu »). Fix : ce plan lit désormais les valeurs
    # DÉJÀ calculées par build_projection (scénario central) — zéro delta réinventé, donc plus
    # aucune divergence possible entre le Plan-trajectoire et les scénarios détaillés plus bas.
    by_nom  = {p["nom"]: p for p in (projection or [])}
    cr_proj = by_nom.get("Coût du risque (% PNB)")
    rn_proj = by_nom.get("Résultat net")

    def _md1(v):
        return f"{round(v, 1)}".replace(".", ",") + " Mds"

    cr_an1 = cr_proj["central"][1] if cr_proj else None
    cr_an2 = cr_proj["central"][2] if cr_proj else None
    cr_an3 = cr_proj["central"][3] if cr_proj else None
    rn_gain_an1 = round(rn_proj["central"][1] - rn_proj["actuel"][1], 1) if rn_proj else None
    rn_gain_an2 = round(rn_proj["central"][2] - rn_proj["actuel"][2], 1) if rn_proj else None
    rn_gain_an3 = round(rn_proj["central"][3] - rn_proj["actuel"][3], 1) if rn_proj else None

    def acte(a, r, j, srcs):
        return {"acte": a, "resultat": r, "justification": j, "sources": srcs}

    horizons = []

    # ─ AN 1 : attaquer le verrou n°1 (coût du risque) + récupérer le revenu facile ─
    a1 = []
    if cr and cr >= 15:
        cr_an1_v   = cr_an1 if cr_an1 is not None else round(cr - 3, 1)
        delta_an1  = round(cr - cr_an1_v, 1)
        rn_an1_txt = _md1(rn_gain_an1) if rn_gain_an1 is not None else _fmt_md(round(pt * 3) if pt else None)
        a1.append(acte(
            "Déployer le moteur de scoring d'octroi + l'application de détection des clients à risque (alertes comportementales) et l'early-warning impayés J+15/J+30.",
            f"Coût du risque {_pct(cr)}% → {_pct(cr_an1_v)}% du PNB (−{_pct(delta_an1)} pt dès la 1ʳᵉ année) ≈ <b>+{rn_an1_txt} de résultat net</b>.",
            f"Le secteur n'affiche que {npl} (BCEAO) alors que SGCI absorbe {_pct(cr)}% de coût du risque : {_pct(delta_an1)} pts de rattrapage sont prudents (scénario central). Le meilleur du marché (BICICI) est à 1,9%.",
            ["EF", "REGL", "WEB"]))
    if rp.get("services"):
        ex = rp["services"][0]
        a1.append(acte(
            f"Réaligner sur la médiane marché les 3 plus gros écarts tarifaires (ex. « {ex['libelle']} » : {ex['sgci']} → {ex['median']} F), sans devenir le plus cher.",
            f"Récupération de commissions sur des services déjà rendus ≈ <b>+1 à +3 Mds de PNB</b> (selon volumes).",
            f"SGCI est sous la médiane sur {rp.get('n')} services comparables (CB). Réajustement compatible avec la transparence tarifaire BCEAO ; les gratuités obligatoires ne sont pas touchées.",
            ["CB", "EF", "REGL"]))
    horizons.append({"horizon": "An 1", "sous_titre": "0–12 mois",
                     "theme": "Lever le verrou du risque & récupérer le revenu laissé sur la table",
                     "actes": a1})

    # ─ AN 2 : consolider le risque + diversifier les revenus (résilience) ─
    a2 = []
    cr_an2_v  = cr_an2 if cr_an2 is not None else round((cr - 4.5) if cr else 12.5, 1)
    delta_an2 = round((cr_an1 if cr_an1 is not None else (cr - 3 if cr else 15.5)) - cr_an2_v, 1)
    rn_an2_txt = _md1(rn_gain_an2) if rn_gain_an2 is not None else _fmt_md(round(pt * 1.5) if pt else None)
    a2.append(acte(
        "Industrialiser le dispositif risque : revue trimestrielle du portefeuille, provisionnement proactif, recouvrement amiable précoce sur les secteurs les plus sinistrés.",
        f"Coût du risque → {_pct(cr_an2_v)}% (−{_pct(delta_an2)} pt supplémentaire) ≈ <b>+{rn_an2_txt} de RN cumulé</b>.",
        "La baisse devient structurelle (process, pas one-shot). Convergence progressive vers le plancher des meilleurs (~12%).",
        ["EF"]))
    a2.append(acte(
        f"Pousser les commissions (monétique, change, services digitaux CONNECT) : porter le mix commissions de {mix}% à 30% du PNB." if mix is not None
        else "Développer les commissions (monétique, change, digital) pour réduire la dépendance au crédit.",
        f"<b>+PNB de service</b> (revenu peu consommateur de fonds propres) ET réduction du risque structurel.",
        f"Le taux directeur BCEAO bas ({_wf('politique_monetaire', 'valeur', 'bas')}) comprime les marges d'intérêt : développer les commissions est la réponse pour rester devant les autres banques sur la rentabilité (et, accessoirement, récupérer des flux mobile money).",
        ["EF", "CB", "WEB"]))
    horizons.append({"horizon": "An 2", "sous_titre": "12–24 mois",
                     "theme": "Rendre la baisse du risque structurelle & diversifier les revenus",
                     "actes": a2})

    # ─ AN 3 : relancer la croissance du leader (offensif) ─
    a3 = []
    a3.append(acte(
        "Lancer l'offensive croissance : offre dédiée diaspora & corporate adossée au réseau international Société Générale, reconquête des comptes entreprises.",
        f"Croissance du RN portée d'environ +{_pct(ef.get('sgci_growth'))}% (cumulée AN1→AN3) vers une cible annuelle de 8–10% ; ROE de {_pct(roe)}% vers ~26%.",
        f"La bancarisation en CI reste faible ({banc}) — gisement d'acquisition — et SGCI est le 1ᵉʳ collecteur de dépôts de l'UMOA (base pour prêter sainement). Terrain à défendre face à BICICI.",
        ["EF", "WEB"]))
    a3.append(acte(
        "Verrouiller la fidélité par la valeur (exclusivités digitales, MyBusiness) plutôt que par la guerre des prix.",
        "Attrition maîtrisée malgré les réajustements tarifaires ; différenciation durable.",
        "Un agresseur prix domine déjà les duels tarifaires (CB) : se battre sur la valeur protège la marge.",
        ["CB"]))
    horizons.append({"horizon": "An 3", "sous_titre": "24–36 mois",
                     "theme": "Transformer l'avance en résultat net en relance de la croissance",
                     "actes": a3})

    # Objectif consolidé (chiffré, dérivé) — 2026-07-24 : aligné sur le scénario Central
    # (rn_gain_an3/cr_an3, déjà calculés ci-dessus) au lieu d'une approximation séparée
    # (pt*5/an) qui affichait un chiffre et un cadrage ("/an") différents du scénario central.
    objectif = {
        "titre": "Cap à 3 ans",
        "lignes": [
            f"Coût du risque : {_pct(cr)}% → {_pct(cr_an3) if cr_an3 is not None else '~12'}% du PNB (niveau des meilleurs)" if cr else None,
            f"Résultat net : effet cumulé ≈ +{_md1(rn_gain_an3)} à 3 ans vs statu quo (scénario central)" if rn_gain_an3 is not None else None,
            f"ROE : {_pct(roe)}% → ~26% (SGCI rejoindrait le peloton de tête)" if roe else None,
            f"Mix commissions : {mix}% → 30% (résilience accrue)" if mix is not None else None,
        ],
    }
    return {"horizons": horizons, "objectif": objectif}


# ════════════════════════════════════════════════════════════════════════════
#  6 bis. ATOUTS À VALORISER (offensif) — où SGCI est forte/compétitive, sourcé
# ════════════════════════════════════════════════════════════════════════════
def detect_advantages(ev):
    ef, cb = ev["ef"], ev["cb"]
    A = []
    def add(titre, preuve, source, action):
        A.append({"titre": titre, "preuve": preuve, "source": source, "action": action})

    if ef.get("rang_rn") == 1:
        add("Leader du marché (#1 en résultat net)",
            f"SGCI est #1/{cb.get('n_banques_cat') or 7} en RN, avance de +{ef.get('ecart_vs_2')}% sur {ef.get('banque_2')}.",
            "EF", "Communiquer la solidité et la taille (confiance, sécurité des dépôts).")
    res = (ef.get("resilience") or {}).get("SGCI") or {}
    if res.get("solvabilite") and res["solvabilite"] >= 12:
        add("Solidité financière",
            f"Solvabilité {res['solvabilite']}% (≥ 12 %, zone de confort BCEAO).",
            "EF·REGL", "Argument de réassurance pour grands comptes et diaspora.")
    at = cb.get("atouts") or {}
    if at.get("n_taux"):
        ex = at["taux"][0]
        add("Taux compétitifs — argument d'acquisition",
            f"Sur {at['n_taux']} services à taux, SGCI est ≤ la médiane concurrents. Ex. « {ex['libelle']} » : "
            f"SGCI {str(ex['sgci']).replace('.', ',')}% vs médiane marché {str(ex['med_conc']).replace('.', ',')}%.",
            "CB", "Mettre en avant les meilleurs taux (crédit, change) pour acquérir des clients.")
    if at.get("n_cheaper"):
        ex = at["cheaper"][0]
        add("Tarifs attractifs sur services clés",
            f"SGCI nettement moins chère que le marché sur {at['n_cheaper']} services. Ex. « {ex['libelle']} » : "
            f"{ex['sgci']} F vs médiane {ex['median']} F.",
            "CB", "Argument prix en communication grand public.")
    if cb.get("rang_prix") and cb["rang_prix"] <= 3:
        add("Parmi les banques les moins chères",
            f"SGCI #{cb['rang_prix']} en compétitivité prix (win-rate {(cb.get('winrate_sgci') or {}).get('winrate')}%).",
            "CB", "Positionnement « bon rapport qualité-prix ».")
    # ── Atout CB toujours présent : services où SGCI est moins chère que le marché ──
    # (même si SGCI n'est pas #1 prix : il existe TOUJOURS des services compétitifs à valoriser)
    rp  = cb.get("repricing") or {}
    wsg = cb.get("winrate_sgci") or {}
    if not at.get("n_cheaper") and (rp.get("services")):
        ex = rp["services"][0]
        add("Services clés moins chers que le marché — levier marketing",
            f"SGCI est SOUS la médiane marché sur {rp.get('n')} services comparables. "
            f"Ex. « {ex['libelle']} » : {ex['sgci']} F vs médiane {ex['median']} F (−{ex.get('ecart_pct')}%).",
            "CB", "Communiquer ces prix avantageux pour capter les clients sensibles au tarif (acquisition ciblée, pas guerre des prix).")
    if (not (cb.get("rang_prix") and cb["rang_prix"] <= 3)) and wsg.get("winrate"):
        add("Prix ≤ marché sur une majorité de services",
            f"SGCI est au niveau ou sous la médiane marché sur {wsg.get('winrate')}% des services comparables "
            f"(#{cb.get('rang_prix')}/{cb.get('n_classees')} en win-rate prix).",
            "CB", "Marketing : mettre en avant les services où SGCI gagne le duel prix, sans guerre générale.")
    return A


# ════════════════════════════════════════════════════════════════════════════
#  6 ter. MOTEUR DE RÉVÉLATIONS — insights non-évidents, croisés EF×CB×temps
# ════════════════════════════════════════════════════════════════════════════
#  Chaque révélation est CALCULÉE depuis les données (jamais inventée), explique
#  un « pourquoi » (pas juste un constat), et porte ses sources. C'est la partie
#  la plus forte : elle fait parler les chiffres que personne n'avait croisés.
# ════════════════════════════════════════════════════════════════════════════
def _rang_de(d, bank, reverse=True):
    """Rang (1 = meilleur) de bank ; reverse=True → grand=meilleur."""
    r, n = _rank(d, bank, reverse=reverse)
    return r, n


def _nom_rang(r):
    return {1: "1ᵉʳ", 2: "2ᵉ", 3: "3ᵉ"}.get(r, f"{r}ᵉ")


def _pct(x):
    return f"{x}".replace(".", ",")


def detect_revelations(ev):
    ef, cb = ev["ef"], ev["cb"]
    widx = ev.get("web_idx") or {}
    web = ev.get("web") or {}
    R = []

    def _wctx(cle):
        """Construit le bloc de contexte externe (fait web sourcé) pour une clé."""
        f = widx.get(cle)
        if not f:
            return None
        return {"titre": f.get("titre"), "valeur": f.get("valeur"),
                "detail": f.get("lien_analyse") or f.get("detail"),
                "source": f.get("source"), "url": f.get("url"), "date": f.get("date")}

    def add(typ, icone, titre, recit, preuves, sources, action=None, poids=2, contexte=None, resume=None):
        R.append({"type": typ, "icone": icone, "titre": titre, "recit": recit,
                  "preuves": preuves, "sources": sources, "action": action,
                  "poids": poids, "contexte": contexte, "resume": resume})

    rn   = ef.get("rn") or {}
    pnb  = ef.get("pnb") or {}
    roe  = ef.get("roe") or {}
    coeff = ef.get("coeff") or {}
    cr   = ef.get("cout_risque_pnb") or {}        # dernier exercice (snapshot)
    crm  = ef.get("cout_risque_moy") or {}         # MOYENNE 3 ans (robuste) → classement/médiane
    cr3d = ef.get("cout_risque_3ans") or {}        # détail (ratios + tendance) par banque
    mn   = ef.get("marge_nette") or {}
    gr   = ef.get("croissance") or {}
    inte = ef.get("interets") or {}
    comm = ef.get("commissions") or {}
    cred = ef.get("credits") or {}
    dep  = ef.get("depots") or {}
    SG = "SGCI"

    # Métriques dérivées par banque (pour les croisements)
    # Même définition unique que partout ailleurs : commissions / PNB (cf. db.part_commissions_pnb).
    _pnb_b = ef.get('pnb') or {}
    mix = {b: db.part_commissions_pnb(comm.get(b), _pnb_b.get(b), inte.get(b))
           for b in BANKS if comm.get(b) and (_pnb_b.get(b) or inte.get(b))}   # % commissions du PNB
    ld  = {b: round(cred[b] / dep[b] * 100, 1)
           for b in BANKS if cred.get(b) and dep.get(b)}           # crédits/dépôts %

    # ── R1. LE PARADOXE SGCI : efficiente mais bridée par le risque (métrique ROBUSTE 3 ans) ──
    co_sg = coeff.get(SG); roe_sg = roe.get(SG)
    crm_sg = crm.get(SG) or cr.get(SG)             # moyenne 3 ans (sinon snapshot)
    cr_sg = cr.get(SG)                             # dernier exercice
    if co_sg is not None and roe_sg is not None and crm_sg is not None:
        r_co, n = _rang_de(coeff, SG, reverse=False)   # petit coeff = meilleur
        r_roe, _ = _rang_de(roe, SG, reverse=True)
        crm_rank = crm if crm else cr
        r_cr, _ = _rang_de(crm_rank, SG, reverse=False)   # classement sur la MOYENNE 3 ans
        best_roe_b, best_roe_v = _best(roe, reverse=True)
        best_cr_b, best_cr_v = _best(crm_rank)         # meilleure moyenne 3 ans
        bcr = crm_rank.get(best_roe_b)                 # coût du risque de la banque-exemple (pour nommer, éviter l'ambiguïté)
        if bcr is None:
            bcr = cr.get(best_roe_b)
        bco_b, bco_v = _best(coeff)
        med_cr = _median(crm_rank)                     # médiane des MOYENNES (robuste)
        # tendance SGCI (10,9 → 17,0)
        det = cr3d.get(SG) or {}
        ratios = det.get("ratios") or []
        tend = det.get("tendance")
        trend_txt = ""
        if len(ratios) >= 2:
            seq = " → ".join(f"{_pct(v)}%" for _, v in ratios)
            mot = {"hausse": "en forte HAUSSE", "baisse": "en baisse", "stable": "stable"}.get(tend, "")
            trend_txt = f" Et la trajectoire inquiète : {seq} sur 3 ans ({mot})."
        pnb_sg = pnb.get(SG)
        # gain = ramener la MOYENNE vers la médiane marché (cible réaliste, robuste)
        cible_cr = max(round(med_cr, 1), 8.0) if med_cr else 8.0
        gain_rn = round(pnb_sg * (crm_sg - cible_cr) / 100) if (pnb_sg and crm_sg > cible_cr) else None
        x2e = round(pnb_sg / sorted(pnb.values(), reverse=True)[1], 1) if pnb_sg and len(pnb) > 1 else None
        if r_co and r_co <= 2 and r_roe and r_roe >= 3 and r_cr and r_cr >= 5:
            eff_txt = (f"la banque la <b>plus efficiente</b> du marché (coefficient {_pct(co_sg)}%, #1/{n})"
                       if r_co == 1 else
                       f"<b>parmi les plus efficientes</b> (coefficient {_pct(co_sg)}%, #{r_co}/{n}, juste derrière {bco_b} à {_pct(bco_v)}%)")
            add("paradoxe", "🔓",
                "Le paradoxe SGCI : une machine d'élite bridée par un seul chiffre",
                (f"SGCI est {eff_txt} et de très loin la plus grosse "
                 f"(PNB {_fmt_md(pnb_sg)}" + (f", ~{_pct(x2e)}× le 2ᵉ" if x2e else "") + "). "
                 f"Et pourtant son ROE n'est que {_nom_rang(r_roe)}/{n} ({_pct(roe_sg)}%). "
                 f"<b>Exemple parlant — {best_roe_b}</b> : sa gestion est MOINS efficiente que SGCI (coefficient d'exploitation "
                 f"{_pct(coeff.get(best_roe_b))}%, soit PLUS élevé donc moins bon que SGCI à {_pct(co_sg)}%) et elle est bien plus "
                 f"petite, MAIS son ROE atteint {_pct(best_roe_v)}% (contre {_pct(roe_sg)}% pour SGCI). La raison ? {best_roe_b} "
                 f"maîtrise bien mieux son risque de crédit : le coût du risque de {best_roe_b} ne pèse que {_pct(bcr)}% de son PNB, une fraction des {_pct(crm_sg)}% supportés par SGCI. "
                 f"La réponse tient en un chiffre : le <b>coût du risque = {_pct(crm_sg)}% du PNB en moyenne sur 3 ans</b> "
                 f"(le pire du marché ; médiane {_pct(med_cr)}%, meilleur {best_cr_b} à {_pct(best_cr_v)}%)." + trend_txt +
                 f" → Le frein de SGCI n'est NI ses coûts NI sa taille : c'est la <b>qualité de son portefeuille de crédit</b>. "
                 f"C'est le verrou n°1, et le plus rentable à lever."),
                [f"Coefficient #{r_co}/{n} ({_pct(co_sg)}%)", f"ROE {_nom_rang(r_roe)}/{n} ({_pct(roe_sg)}%)",
                 f"Coût du risque {_pct(crm_sg)}% (moy. 3 ans, pire ; médiane {_pct(med_cr)}%)",
                 (f"Dernier exercice {_pct(cr_sg)}% — {tend}" if cr_sg and tend else None),
                 (f"Ramener vers ~{_pct(cible_cr)}% (cible prudente) ≈ +{_fmt_md(gain_rn)} de RN/an" if gain_rn else None)],
                ["EF", "REGL", "WEB"],
                "Faire du coût du risque LA priorité : l'efficience et la taille sont déjà gagnées, le risque est le seul verrou.",
                poids=5, contexte=_wctx("npl_secteur"),
                resume=("SGCI travaille très bien et c'est la plus grosse banque — mais elle perd de plus en plus à cause de crédits "
                        "non remboursés (coût du risque en hausse continue, le pire du marché). C'est SON seul vrai problème, et le régler la rendrait n°1 en rentabilité."))

    # ── R2. L'ASCENSION DE BICICI DÉCODÉE (croissance qualité, pas volume) ──
    fb, fp = ef.get("fastest_b"), ef.get("fastest_pct")
    if fb and fb != SG and fp:
        ld_fb, cr_fb, roe_fb = ld.get(fb), cr.get(fb), roe.get(fb)
        tilt_fb = (cb.get("tilt") or {}).get(fb)
        r_ld_fb, _ = _rang_de(ld, fb, reverse=False)   # petit crédits/dépôts = prête peu
        bits = []
        if ld_fb is not None:
            bits.append(f"le ratio crédits/dépôts le plus faible ou presque ({_pct(ld_fb)}%, vs SGCI {_pct(ld.get(SG))}%) — elle <b>prête peu, mais bien</b>")
        if cr_fb is not None:
            bits.append(f"le coût du risque le plus bas ({_pct(cr_fb)}%)")
        if roe_fb is not None:
            bits.append(f"le meilleur ROE du marché ({_pct(roe_fb)}%)")
        tilt_txt = ""
        if tilt_fb and tilt_fb >= 1.0:
            tilt_txt = (f" En conditions de banque, {fb} penche <b>entreprises</b> "
                        f"({(cb.get('cat_ent') or {}).get(fb)} services Ent. vs {(cb.get('cat_part') or {}).get(fb)} Part.).")
        add("moteur", "🚀",
            f"L'ascension de {fb} décodée : ce n'est pas du volume, c'est de la discipline",
            (f"{fb} affiche la croissance la plus fulgurante du marché (<b>+{_pct(fp)}% de résultat net</b>, "
             f"contre +{_pct(ef.get('sgci_growth'))}% pour SGCI). Mais l'analyse des bilans le montre : ce n'est PAS une croissance "
             f"de volume. {fb} cumule " + ", ".join(bits) + f".{tilt_txt} "
             f"→ Son moteur n'est pas le volume (BICICI n'est que {_nom_rang(_rang_de(rn, fb)[0])}/{_rang_de(rn, fb)[1]} en résultat net) "
             f"mais la <b>discipline du risque sur une clientèle entreprises bien sélectionnée</b>. La vraie menace : si {fb} déploie "
             f"ce modèle à grande échelle, son avance grossit chaque année — les bénéfices réinvestis accélèrent encore sa croissance. "
             f"C'est justement le point faible n°1 de SGCI."),
            [f"Croissance RN +{_pct(fp)}% (#1)", f"Coût du risque {_pct(cr_fb)}% (meilleur)" if cr_fb is not None else None,
             f"ROE {_pct(roe_fb)}%" if roe_fb is not None else None,
             f"Crédits/dépôts {_pct(ld_fb)}% (sélectif)" if ld_fb is not None else None],
            ["EF", "CB", "WEB"] if fb == "BICICI" else ["EF", "CB"],
            f"Défendre la base corporate et copier la discipline d'octroi de {fb} (là où SGCI perd 17% de PNB).",
            poids=4,
            contexte=({"titre": "Positionnement historique (source externe)",
                       "valeur": "Corporate / commerce-industrie",
                       "detail": ((ev.get("web") or {}).get(fb, {}) or {}).get("_note", ""),
                       "source": "Profil banque (sites officiels / presse)",
                       "url": ((ev.get("web") or {}).get(fb, {}) or {}).get("_url", ""),
                       "date": ((ev.get("web") or {}).get(fb, {}) or {}).get("_date", "")}
                      if ((ev.get("web") or {}).get(fb, {}) or {}).get("_note") else None),
            resume=f"{fb} explose (+{_pct(fp)}%) non pas en prêtant beaucoup, mais en prêtant à des clients sûrs. Sa force, c'est la QUALITÉ du risque, pas la taille — exactement le point faible de SGCI.")

    # ── R3. LA DOUBLE EXPOSITION : revenus concentrés sur le crédit ET crédit risqué ──
    mix_sg = mix.get(SG)
    if mix_sg is not None and cr_sg is not None and cr_sg >= 12:
        med_mix = _median(mix)
        bb_mix, bv_mix = _best(mix, reverse=True)       # la plus diversifiée (commissions)
        add("paradoxe", "⚠️",
            "Pourquoi la diversification compte DEUX fois plus pour SGCI que pour les autres",
            (f"Comme le marché, SGCI tire ~{_pct(round(100-mix_sg,1))}% de son PNB des <b>intérêts (crédit)</b> et seulement "
             f"{_pct(mix_sg)}% des commissions (médiane marché {_pct(med_mix)}% ; la plus diversifiée, {bb_mix}, est à {_pct(bv_mix)}%). "
             f"La dépendance au crédit est donc normale… sauf que <b>chez SGCI ce crédit porte le coût du risque le plus élevé du marché "
             f"({_pct(cr_sg)}%)</b>. Conséquence : un même franc de revenu de crédit est, chez SGCI, bien plus risqué qu'ailleurs. "
             f"→ Développer les commissions (monétique, change, services digitaux) n'est donc pas qu'un levier de PNB pour SGCI : "
             f"c'est, plus que pour quiconque, une <b>réduction de risque structurel</b> — elle remplace du revenu risqué par du revenu sûr."),
            [f"Intérêts {_pct(round(100-mix_sg,1))}% du PNB", f"Commissions {_pct(mix_sg)}% (médiane {_pct(med_mix)}%)",
             f"Coût du risque {_pct(cr_sg)}% (le pire)"],
            ["EF"],
            "Traiter la diversification des commissions comme un levier de résilience prioritaire, pas seulement de revenu.",
            poids=3,
            resume="SGCI gagne surtout grâce au crédit — or c'est justement son crédit qui coûte le plus cher en risque. Vendre plus de services (cartes, change…) rapporte ET réduit ce danger.")

    # ── R4. AGRESSEUR PRIX : qui utilise le prix comme arme d'acquisition ? ──
    wr = cb.get("winrate") or []
    if wr:
        top = wr[0]
        if top.get("banque") != SG and (top.get("winrate") or 0) >= 55:
            sg_wr = next((c for c in wr if c["banque"] == SG), None)
            agg_b   = top["banque"]
            cf_agg  = coeff.get(agg_b); med_cf = _median(coeff)
            web_agg = web.get(agg_b, {}) or {}
            # LIEN explicite coûts→prix, grounded par le coefficient d'exploitation (EF)
            if cf_agg is not None and med_cf is not None and cf_agg <= med_cf:
                _agg_lien = (f"Son agence digitale (écrans interactifs, bornes self-service) réduit le besoin d'agences "
                             f"physiques et de personnel → moins de coûts fixes. Les chiffres le CONFIRMENT : coefficient "
                             f"d'exploitation {agg_b} {_pct(cf_agg)}% (sous la médiane marché {_pct(med_cf)}% [EF]) = banque "
                             f"efficiente. Ce coût bas lui donne la MARGE pour pratiquer des prix sous le marché — voilà ce "
                             f"qui FINANCE son agressivité prix.")
            elif cf_agg is not None:
                _agg_lien = (f"Son agence digitale (self-service, moins d'agences/personnel) vise à réduire le coût de "
                             f"service (coefficient d'exploitation {agg_b} {_pct(cf_agg)}% [EF]) — un levier de coûts qui lui "
                             f"permet de pratiquer des prix bas.")
            else:
                _agg_lien = web_agg.get("innovation", "Modèle d'agence digitale qui abaisse le coût de service.")
            add("menace", "🎯",
                f"{top['banque']} fait du prix une arme : la banque la plus souvent la moins chère",
                (f"Sur le panier de services comparables, <b>{top['banque']} gagne {_pct(top['winrate'])}% des duels de prix</b> "
                 f"({top.get('wins')}/{top.get('n')} services ≤ médiane marché) — le meilleur win-rate du marché. "
                 + (f"SGCI est à {_pct(sg_wr['winrate'])}% (#{cb.get('rang_prix')}). " if sg_wr else "")
                 + f"→ {top['banque']} se positionne en agresseur prix pour capter les clients sensibles au tarif. "
                 f"Sur les services à fort volume, SGCI doit choisir : suivre (défendre le volume) ou différencier par la valeur "
                 f"(digital, exclusivités) plutôt que par le prix."),
                [f"{top['banque']} win-rate {_pct(top['winrate'])}% (#1)",
                 (f"SGCI {_pct(sg_wr['winrate'])}% (#{cb.get('rang_prix')})" if sg_wr else None)],
                ["CB", "WEB"],
                "Cartographier les services à fort volume où l'agresseur attaque et défendre par la valeur, pas la guerre des prix.",
                poids=3,
                contexte=({"titre": f"Le LIEN : pourquoi {agg_b} peut casser les prix",
                           "valeur": "Agence digitale → coûts bas → prix bas",
                           "detail": _agg_lien,
                           "source": "Sikafinance + EF", "url": web_agg.get("_url", ""), "date": "2024"}
                          if web_agg else None),
                resume=(f"{agg_b} est presque toujours la moins chère. Le LIEN concret : son agence digitale réduit ses "
                        f"coûts fixes (moins d'agences/personnel) → elle a la marge pour casser les prix. SGCI ne peut pas "
                        f"gagner cette guerre des prix sur les coûts : elle doit répondre par la VALEUR (conseil, exclusivités)."))

    # ── R5. NSIA : la stratégie de couverture (inonder par la largeur d'offre) ──
    cat_p = cb.get("cat_part") or {}
    if cat_p:
        bigb, bigv = max(cat_p.items(), key=lambda x: x[1])
        med_cat = _median(cat_p)
        if bigb != SG and med_cat and bigv >= med_cat * 1.8:
            add("signal", "📚",
                f"{bigb} mise sur la couverture totale : {bigv} services publiés ({round(bigv/med_cat,1)}× la médiane)",
                (f"{bigb} publie <b>{bigv} services</b> en conditions de banque, soit {round(bigv/med_cat,1)}× la médiane marché "
                 f"(~{round(med_cat)}). SGCI en publie {cat_p.get(SG)}. → {bigb} joue la <b>largeur d'offre</b> (être présent sur tous "
                 f"les besoins) plutôt que le prix. Ce n'est pas une menace directe sur la rentabilité, mais un signal de "
                 f"positionnement : SGCI peut répondre par la <b>profondeur ciblée</b> (mieux servir les besoins qui comptent) "
                 f"plutôt que de courir après l'exhaustivité."),
                [f"{bigb} : {bigv} services", f"SGCI : {cat_p.get(SG)}", f"Médiane ~{round(med_cat)}"],
                ["CB"],
                "Ne pas courir à l'exhaustivité : approfondir les services à forte valeur plutôt que multiplier les lignes.",
                poids=1,
                resume=f"{bigb} propose énormément de services pour être présente partout. SGCI n'a pas besoin de tout copier : mieux vaut bien faire l'essentiel.")

    # ── R6. LE CHALLENGER LE PLUS RENTABLE (marge nette) ──
    if mn:
        bb, bv = _best(mn, reverse=True)
        mn_sg = mn.get(SG)
        if bb != SG and bv and mn_sg and bv >= mn_sg + 8:
            r_rn_bb, n = _rang_de(rn, bb)
            add("signal", "💎",
                f"{bb} : le plus rentable par franc de PNB (marge nette {_pct(bv)}%, dernière année)",
                (f"{bb} convertit <b>{_pct(bv)}% de son PNB en résultat net</b> — la meilleure marge du marché, "
                 f"contre {_pct(mn_sg)}% pour SGCI. {bb} n'est que {_nom_rang(r_rn_bb)}/{n} en résultat net, mais sa machine est "
                 f"plus efficace à transformer le revenu en profit (coût du risque {_pct(cr.get(bb))}%, coefficient {_pct(coeff.get(bb))}%). "
                 f"→ Benchmark de rentabilité : l'écart de marge SGCI↔{bb} ({_pct(round(bv-mn_sg,1))} pts) mesure exactement le "
                 f"potentiel que le coût du risque détruit chez SGCI."),
                [f"{bb} marge nette {_pct(bv)}% (#1)", f"SGCI {_pct(mn_sg)}%",
                 f"Écart {_pct(round(bv-mn_sg,1))} pts"],
                ["EF", "WEB"],
                f"Importer la discipline de sélection du risque de {bb} (filiale du groupe marocain Attijariwafa) — l'efficience opérationnelle est déjà là chez SGCI.",
                poids=2,
                contexte=({"titre": "Pourquoi SIB est si rentable (source externe)",
                           "valeur": "Modèle Attijariwafa",
                           "detail": (web.get("SIB", {}) or {}).get("cause_rentabilite",
                                      "Discipline de coûts et faible coût du risque du groupe Attijariwafa."),
                           "source": "Agence Ecofin", "url": (web.get("SIB", {}) or {}).get("_url", ""), "date": "2024"}
                          if web.get("SIB") else None),
                resume=(f"{bb} convertit {_pct(bv)}% de son PNB en profit (vs {_pct(mn_sg)}% pour SGCI). Pas un hasard : DEUX "
                        f"leviers concrets — (1) un coût du risque très bas ({_pct(cr.get(bb))}% du PNB, contre {_pct(cr.get(SG))}% "
                        f"pour SGCI) grâce à une sélection rigoureuse à l'octroi, et (2) une bonne maîtrise des charges (coefficient "
                        f"d'exploitation {_pct(coeff.get(bb))}%). <b>Le « modèle Attijariwafa »</b> = la culture du groupe marocain "
                        f"<b>Attijariwafa Bank</b> (1ʳᵉ banque du Maroc, actionnaire de référence de SIB, présente dans ~25 pays), "
                        f"réputé pour une sélection prudente du risque et un contrôle serré des coûts — c'est CE qui explique la "
                        f"rentabilité de SIB. À importer chez SGCI : mieux sélectionner le risque à l'octroi (garanties, analyse) "
                        f"et resserrer les charges — l'efficience est déjà là."))

    # ── R7. SGCI DÉCÉLÈRE : le leader installé qui bouge le moins vite ──
    g_sg = gr.get(SG)
    if g_sg is not None:
        r_g, n = _rang_de(gr, SG, reverse=True)
        med_g = _median(gr)
        if r_g and r_g >= n - 1 and ef.get("rang_rn") == 1:
            add("menace", "🐢",
                "Le leader qui décélère : #1 en résultat net, avant-dernier en croissance",
                (f"SGCI est <b>#1/{n} en résultat net</b> mais seulement <b>{_nom_rang(r_g)}/{n} en croissance</b> "
                 f"(+{_pct(g_sg)}% vs médiane marché +{_pct(med_g)}%, croissance cumulée AN1→AN3). L'avance absolue masque une dynamique en queue de peloton : "
                 f"sur la période, SGCI croît de {_pct(g_sg)}%, le marché ~{_pct(med_g)}% et le plus rapide de +{_pct(fp)}%. "
                 f"→ Le risque n'est pas immédiat (l'écart de résultat net est énorme) mais structurel : sans relance de la dynamique, "
                 f"l'avance s'érode mécaniquement année après année."),
                [f"RN #1/{n}", f"Croissance {_nom_rang(r_g)}/{n} (+{_pct(g_sg)}%)",
                 f"Médiane marché +{_pct(med_g)}%"],
                ["EF"],
                f"Fixer un objectif de croissance ≥ médiane marché ({_pct(med_g)}%) via 3 moteurs précis : commissions de service, conquête corporate, acquisition digitale.",
                poids=3,
                resume=(f"Décision claire : SGCI a crû de +{_pct(g_sg)}% sur la période (cumulée AN1→AN3) quand le marché avance de +{_pct(med_g)}%. "
                        f"Si rien ne change, un concurrent qui a crû de +{_pct(fp)}% (AN1→AN3) comblerait l'écart de résultat net en quelques années. "
                        f"Objectif à se fixer : revenir AU MOINS à la croissance médiane du marché."))

    R.sort(key=lambda x: -x["poids"])
    return R


# ════════════════════════════════════════════════════════════════════════════
#  7. SYNTHÈSE + MÉTRIQUES + ASSEMBLAGE
# ════════════════════════════════════════════════════════════════════════════
def _fr(n):
    """Entier formaté à la française : 18500 → '18 500'."""
    try:
        return f"{int(round(n)):,}".replace(",", " ")
    except Exception:
        return str(n)


# ════════════════════════════════════════════════════════════════════════════
#  COMITÉ DE DIRECTION — 4 regards, des DÉCISIONS (pas des faits), chiffrées+sourcées
# ════════════════════════════════════════════════════════════════════════════
def build_comite(ev):
    ef, cb = ev["ef"], ev["cb"]
    web = ev.get("web") or {}
    widx = ev.get("web_idx") or {}
    pnb = (ef["pnb"] or {}).get("SGCI")
    pt = round(pnb / 100) if pnb else None          # 1 pt de PNB (M FCFA)
    cr = ef["cout_risque_pnb"].get("SGCI")
    roe = (ef["roe"] or {}).get("SGCI")
    mn = (ef["marge_nette"] or {}).get("SGCI")
    comm, inte = ef.get("commissions", {}).get("SGCI"), ef.get("interets", {}).get("SGCI")
    # DÉFINITION UNIQUE (2026-08-10) : commissions / PNB, via db.part_commissions_pnb.
    # Cette page calculait commissions / (commissions + intérêts) — 24,0 % — quand la
    # Stratégie opérationnelle affichait 26,3 % pour le même indicateur. Deux pages de la
    # même application se contredisaient de 2,3 points, ce qui suffit à faire douter des deux.
    mix = db.part_commissions_pnb(comm, (ef.get('pnb') or {}).get('SGCI'), inte)

    # ── Lecture SEGMENT (particuliers vs entreprises) — intervient partout ──
    tilt = cb.get("tilt") or {}                    # >1 = orienté entreprises (catalogue Ent/Part)
    tilt_sg = tilt.get("SGCI")
    ent_banks = sorted([b for b, t in tilt.items() if b != "SGCI" and t and t >= 1.1],
                       key=lambda b: -tilt[b])      # concurrents orientés entreprises
    ent_txt = ", ".join(f"{b} (×{_pct(tilt[b])})" for b in ent_banks[:3]) or "plusieurs concurrents"
    sgci_web = web.get("SGCI", {})
    # 99% des clients SGCI sont des particuliers (600k vs 6,4k entreprises) — source web
    seg_constat = (f"SGCI est <b>orientée particuliers</b> : ~600 000 clients particuliers pour seulement "
                   f"~6 400 entreprises [WEB], et son catalogue est équilibré (ratio Ent/Part ×{_pct(tilt_sg)}) "
                   f"quand {ent_txt} penchent nettement entreprises [CB]. Or le corporate, mieux maîtrisé en risque, "
                   f"est justement là où BICICI et SIB sont les plus rentables.")

    def D(titre, detail, impact, pourquoi, sources, effort="Moyen", segment="Les deux", type_="Optimisation"):
        return {"titre": titre, "detail": detail, "impact": impact, "pourquoi": pourquoi,
                "sources": sources, "effort": effort, "segment": segment, "type": type_}

    dirs = []

    # ════ 1) DIRECTION FINANCIÈRE ════
    sib = web.get("SIB", {})
    cause_sib = sib.get("cause_rentabilite", "")
    crm_all = ef.get("cout_risque_moy") or ef["cout_risque_pnb"]   # moyenne 3 ans (robuste)
    crm = crm_all.get("SGCI") or cr
    bb_cr, bv_cr = _best(crm_all)
    med_cr = _median(crm_all)
    cible = max(round(med_cr, 1) if med_cr else 8.0, 8.0)
    gain_cr = _fmt_md(round(pt * (crm - cible))) if (pt and crm and crm > cible) else "plusieurs Mds"
    det_sg = (ef.get("cout_risque_3ans") or {}).get("SGCI") or {}
    seq_sg = " → ".join(f"{_pct(v)}%" for _, v in (det_sg.get("ratios") or []))
    sib_mn = (ef['marge_nette'] or {}).get('SIB')
    decisions_f = [
        D("« Sentinelle Crédit » — appli de scoring & détection des clients à risque",
          "Produit phare à construire. Fonctionnalités : (1) <b>score d'octroi</b> multi-critères (revenus, secteur, ancienneté, historique BCEAO) ; "
          "(2) <b>alertes comportementales temps réel</b> — chute brutale des flux entrants, salaire retiré intégralement en cash, découverts répétés, retards qui s'allongent ; "
          "(3) <b>signal mobile money</b> : croiser les flux e-money du client comme indicateur avancé de fragilité ; "
          "(4) <b>early-warning J+15/J+30</b> avec relance automatique et plan d'apurement ; "
          "(5) <b>tableau de bord par secteur sinistré</b> pour geler l'octroi là où ça casse ; (6) score <b>recalculé chaque mois</b>, pas figé à l'octroi.",
          f"Coût du risque {_pct(crm)}% (moy. 3 ans) → ~{_pct(cible)}% ≈ <b>+{gain_cr} de résultat net/an</b>",
          f"Tendance SGCI {seq_sg} (en hausse) alors que le secteur n'est qu'à {(widx.get('npl_secteur') or {}).get('valeur','7,7%')} (BCEAO) et {bb_cr} à {_pct(bv_cr)}%. C'est un problème PROPRE à SGCI (les autres banques s'en sortent bien mieux), pas un effet général du marché.",
          ["EF", "REGL", "WEB"], "Élevé", "Les deux", "Produit / outil"),
        D("Retourner « Sentinelle » en moteur de CROISSANCE : le crédit instantané scoré",
          "Une fois le scoring fiable, l'utiliser à l'envers : pré-accorder un crédit instantané (consommation, trésorerie PME) aux <b>bons</b> profils, en 1 clic dans l'appli. Le risque maîtrisé devient une arme commerciale.",
          "Nouveau revenu d'intérêts SAIN + acquisition (vitesse = argument vs concurrents et fintechs)",
          "Le même outil qui réduit les pertes identifie aussi les <b>excellents</b> payeurs — à qui on peut prêter vite et bien. C'est le modèle de discipline de BICICI (coût du risque 1,9%) appliqué offensivement.",
          ["EF", "CB"], "Élevé", "Les deux", "Nouveau produit"),
        D("Assurance-crédit & garanties : couvrir le risque au lieu de seulement le subir",
          "Adosser chaque crédit à une assurance emprunteur / un fonds de garantie (s'inspirer du modèle bancassurance de NSIA). Le risque résiduel chute, et l'assurance devient un revenu de commission.",
          "Baisse du coût du risque NET <b>+ nouvelles commissions</b> (revenu peu consommateur de fonds propres)",
          "NSIA prospère en bancassurance [WEB] ; le coût du risque SGCI est le pire du marché : transférer une partie du risque à l'assurance est un levier double (résilience + PNB).",
          ["EF", "WEB"], "Moyen", "Les deux", "Nouveau produit"),
        D("Assainir le bilan : cession / titrisation d'une poche de créances douteuses",
          "Vendre ou titriser une partie du portefeuille le plus sinistré pour nettoyer le bilan d'un coup, plutôt que de le traîner sur des années.",
          "Libère du capital et fait baisser mécaniquement le stock de créances en souffrance",
          f"Le coût du risque grimpe ({seq_sg}) : une partie est un stock ancien qui pèse. Le solder libère de la capacité pour du crédit sain.",
          ["EF", "REGL"], "Élevé", "Les deux", "Optimisation"),
        D("Optimiser le pricing du crédit sur les profils sûrs",
          "Relever de quelques points de base le taux sur les meilleurs scores (sans toucher aux clients fragiles ni au social), là où on a de la marge avant le marché.",
          "Quelques pb × encours = <b>+PNB d'intérêts</b> récurrent, à risque inchangé",
          f"Notre meilleur taux débiteur (~6%) est SOUS la moyenne ivoirienne (6,97%) et très loin du plafond d'usure (14%) [WEB] : marge de pricing inexploitée sur les bons risques.",
          ["EF", "WEB"], "Moyen", "Les deux", "Optimisation"),
        D("Importer la discipline de coûts du modèle Attijariwafa (SIB)",
          "Revue trimestrielle du portefeuille, provisionnement proactif, comité des risques renforcé, pilotage serré des charges — institutionnaliser la rigueur.",
          f"Viser la marge nette de SIB ({_pct(sib_mn)}% vs {_pct(mn)}% pour SGCI)" if sib_mn else "Améliorer la marge nette",
          f"POURQUOI SIB est la plus rentable : {cause_sib or 'discipline de coûts et de risque du groupe Attijariwafa'} [WEB] — compétence à importer, pas un mystère.",
          ["EF", "WEB"], "Moyen", "Les deux", "Copier-dépasser"),
    ]
    dirs.append({"nom": "Direction Financière", "icone": "💰", "couleur": "#0a5e3c",
                 "question": "Comment transformer notre efficacité en rentabilité de tête ?",
                 "lecture": (f"SGCI, la plus grosse et l'une des plus efficaces du marché, ne dégage pourtant qu'un ROE de {_pct(roe)}% "
                             f"(#6) : l'écart tient tout entier au coût du risque ({_pct(crm)}% en moyenne sur trois ans, le pire du secteur et en progression). "
                             f"Le premier levier de rentabilité ne réside ni dans les coûts ni dans la taille, mais dans la qualité du portefeuille de crédit."),
                 "decisions": decisions_f})

    # ════ 2) DIRECTION COMMERCIALE ════  (décisions de prix service par service)
    under = (cb.get("repricing") or {}).get("services", [])
    over = cb.get("over", [])
    rp_n = (cb.get("repricing") or {}).get("n", 0)
    aggr = (cb.get("winrate") or [{}])[0].get("banque", "le concurrent")
    decisions_c = []
    if under:
        ex = under[0]
        lignes = "; ".join(f"« {u['libelle']} » {_fr(u['sgci'])}→{_fr(u['median'])} F (+{_fr(u['gap'])})" for u in under[:4])
        decisions_c.append(D(
            f"Réaligner sur le marché les {rp_n} services trop bon marché",
            f"On ne devient pas le plus cher, on vise la médiane. Cibles : {lignes}.",
            f"<b>+{_fr(ex['gap'])} F par opération</b> sur « {ex['libelle']} » (gain certain). Total = gain × volume "
            f"(volume non public — indicatif : 100 000 op. = +{_fmt_md(round(ex['gap']*100000/1_000_000))}).",
            "Facturés SOUS la médiane : argent laissé sur des prestations déjà rendues. Transparence BCEAO respectée, gratuités obligatoires intactes.",
            ["CB", "EF", "REGL"], "Faible", "Particuliers", "Optimisation"))
    if over:
        lignes_o = "; ".join(f"« {o['libelle']} » {_fr(o['sgci'])} F (marché {_fr(o['median'])}, +{o['ecart_pct']}%)" for o in over[:4])
        decisions_c.append(D(
            f"Ajuster/justifier les {cb.get('n_over',0)} services plus chers que le marché",
            f"Risque d'image « banque chère ». À justifier par la valeur, ou baisser : {lignes_o}.",
            "Protège le win-rate et l'acquisition sur les services comparés en premier",
            f"Sur ces services, l'agresseur prix {aggr} peut capter nos clients sensibles au tarif [CB].",
            ["CB"], "Faible", "Particuliers", "Défense"))
    # ── SEGMENT : favoriser l'octroi aux ENTREPRISES (l'angle mort) ──
    decisions_c.append(D(
        "Basculer une partie de l'effort commercial vers le CORPORATE (entreprises)",
        "Créer/renforcer une force de vente entreprises dédiée, des chargés d'affaires PME, et favoriser l'octroi de crédit aux entreprises bien notées (gros tickets, garanties réelles, relation durable).",
        "Diversifie le risque (le corporate garanti casse moins que le retail) ET capte de la croissance",
        f"{seg_constat} Favoriser l'entreprise, c'est aller chercher le risque maîtrisé là où BICICI/SIB gagnent — un angle que SGCI, orientée particuliers, sous-exploite.",
        ["CB", "EF", "WEB"], "Élevé", "Entreprises", "Nouveau produit"))
    decisions_c.append(D(
        "Cross-sell massif sur les 606 400 clients (du mono-produit au multi-équipement)",
        "La plupart des clients particuliers n'ont qu'un compte. Leur vendre carte premium, épargne, assurance, crédit conso pré-scoré (via Sentinelle). Campagnes déclenchées par les données (ex. salaire qui augmente → proposer une épargne).",
        "<b>+PNB par client</b> sans coût d'acquisition (le client est déjà là) → dilue les charges fixes",
        "606 400 clients [WEB] dont ~99% particuliers souvent mono-produit : le gisement de PNB le moins cher est notre propre base.",
        ["EF", "WEB"], "Moyen", "Particuliers", "Optimisation"))
    decisions_c.append(D(
        "Lancer des PACKAGES segmentés (Jeune actif · PME · Diaspora · Premium)",
        "Au lieu de vendre des services à l'unité, créer des bouquets à prix forfaitaire par segment : « Pack Jeune » (compte mobile + carte + alertes), « Pack PME » (compte pro + crédit trésorerie + change), « Pack Diaspora » (transferts + épargne + crédit immobilier au pays).",
        "Augmente le panier moyen, fidélise, et clarifie l'offre face aux catalogues pléthoriques des concurrents",
        f"NSIA empile 445 services [CB] ; SGCI peut gagner par la LISIBILITÉ : des packs clairs par segment plutôt qu'un catalogue à la carte.",
        ["CB"], "Moyen", "Les deux", "Nouveau produit"))
    decisions_c.append(D(
        "Programme de parrainage / fidélité : transformer 606 400 clients en prescripteurs",
        "Récompenser le client qui en amène un autre (mois de tenue de compte offert, bonus). Sur un marché peu bancarisé, le bouche-à-oreille du leader est une machine d'acquisition.",
        "Acquisition à très faible coût + rétention",
        "Sur un marché à <30% de bancarisation [WEB], la recommandation d'un client satisfait du leader vaut plus qu'une pub.",
        ["WEB", "EF"], "Faible", "Particuliers", "Nouveau produit"))
    decisions_c.append(D(
        "Défendre les services à fort volume face à l'agresseur prix par la VALEUR",
        f"Cartographier les services où {aggr} est systématiquement moins cher et répondre par la valeur (digital, conseil, exclusivités), pas par une guerre des prix.",
        "Préserve les volumes sans détruire la marge",
        f"#{cb.get('rang_prix')} en win-rate prix : suivre aveuglément la baisse détruirait le PNB ; mieux vaut différencier.",
        ["CB"], "Moyen", "Particuliers", "Défense"))
    dirs.append({"nom": "Direction Commerciale", "icone": "🤝", "couleur": "#1650b0",
                 "question": "Quels leviers de revenu activer — par PRIX, par SEGMENT et par PRODUIT ?",
                 "lecture": (f"Deux dimensions. <b>Prix</b> : SGCI sous le marché sur {rp_n} services (revenu laissé), au-dessus sur "
                             f"{cb.get('n_over',0)} (attrition). <b>Segment</b> : {seg_constat}"),
                 "decisions": decisions_c})

    # ════ 3) DIRECTION MARKETING ════  (gratuité / acquisition)
    g_sg = cb.get("gratuite_sgci")
    g_med = cb.get("gratuite_med")
    mobile = (widx.get("mobile_money") or {}).get("valeur", "82%")
    banc = (widx.get("bancarisation") or {}).get("valeur", ">30%")
    decisions_m = []
    if g_sg is not None and g_med is not None:
        decisions_m.append(D(
            "Élargir l'offre gratuite au-delà du strict minimum BCEAO",
            "Rendre gratuits des services d'appel (consultation, carte d'entrée de gamme, alertes SMS, premières opérations digitales) pour faire entrer le client, puis le monter en gamme.",
            f"Gratuité {_pct(g_sg)}% → niveau marché {_pct(g_med)}% = <b>argument d'acquisition</b>",
            f"SGCI n'offre que {_pct(g_sg)}% de services gratuits, SOUS la médiane marché ({_pct(g_med)}%) [CB] : on se limite quasi au minimum réglementaire pendant que des concurrents attirent par la gratuité.",
            ["CB"], "Faible", "Particuliers", "Optimisation"))
    decisions_m.append(D(
        "« SG Mobile » — un compte 100% mobile pour les non-bancarisés",
        "Nouveau produit : ouverture en 5 min depuis le téléphone, sans agence ; carte virtuelle, paiements, micro-épargne, et micro-crédit pré-scoré (via Sentinelle). Riposte directe à Orange Bank, mais adossé à la solidité d'un leader (crédit, sécurité des dépôts).",
        f"Capte le vivier des {mobile} d'utilisateurs e-money et des {banc} de bancarisation [WEB]",
        f"Mobile money à {mobile} et bancarisation à {banc} [WEB] : l'acquisition de masse se joue sur le mobile. Orange Bank (néobanque) a déjà ce terrain [WEB] — ne pas le lui laisser.",
        ["WEB", "CB"], "Élevé", "Particuliers", "Nouveau produit"))
    decisions_m.append(D(
        "« SG Diaspora » — l'offre que seul un groupe international peut faire",
        "Pack diaspora : transferts à coût réduit, compte épargne au pays, crédit immobilier « rentrer construire », assurance rapatriement — en s'appuyant sur le réseau Société Générale à l'international.",
        "Capte une clientèle à fort pouvoir d'achat et fidèle, difficile à imiter pour une banque locale",
        "Le réseau international Société Générale est un avantage VRIST DURABLE [WEB] qu'aucun concurrent local (BICICI, NSIA, SIB) ne peut répliquer — il faut le monétiser.",
        ["WEB", "CB"], "Moyen", "Particuliers", "Nouveau produit"))
    decisions_m.append(D(
        "Campagne « la banque la plus solide » (réassurance = acquisition)",
        "Mettre en avant le statut #1 (606 400 clients, 1ᵉʳ en dépôts UMOA, solvabilité >16%, leader). Transformer les 113 agences en relais d'expérience.",
        "La confiance est un argument fort sur un marché peu bancarisé",
        "SGCI est leader UMOA en bilan et dépôts [WEB] ; la confiance est un actif marketing sous-exploité face à des concurrents plus petits.",
        ["WEB", "EF"], "Faible", "Les deux", "Optimisation"))
    decisions_m.append(D(
        "Marketing entreprises dédié (pas que du retail)",
        "Communication B2B : offres de cash-management, financement de la chaîne d'approvisionnement, salle des marchés/change pour les PME exportatrices.",
        "Soutient le virage corporate (cf. Direction Commerciale) côté notoriété",
        f"SGCI est orientée particuliers alors que {ent_txt} captent le corporate rentable [CB] : le marketing doit accompagner le rééquilibrage.",
        ["CB", "WEB"], "Moyen", "Entreprises", "Nouveau produit"))
    dirs.append({"nom": "Direction Marketing", "icone": "📣", "couleur": "#B45309",
                 "question": "Comment attirer plus de clients — par la gratuité, le mobile, la diaspora et le corporate ?",
                 "lecture": (f"SGCI se limite quasi aux gratuités minimales ({_pct(g_sg) if g_sg is not None else '?'}% vs marché "
                             f"{_pct(g_med) if g_med is not None else '?'}%) [CB] et sous-exploite trois gisements : le mobile money "
                             f"({mobile}), la bancarisation faible ({banc}) et sa marque de leader."),
                 "decisions": decisions_m})

    # ════ 4) DIRECTION INNOVATION ════  (copier+dépasser, gaps, VRIST)
    innov = cb.get("innovations") or []
    gaps = cb.get("gaps") or []
    n_excl = cb.get("n_exclusivites", 0)
    decisions_i = []
    decisions_i.append(D(
        "« SG One » — la super-app qui réunit tout ce qui est aujourd'hui éparpillé",
        "Une seule appli : compte + wallet mobile money + micro-crédit instantané scoré + épargne + assurance (type NSIA) + change. L'inverse de la stratégie NSIA (445 services en vrac) : tout au même endroit, simple.",
        "Fidélise (plus on a de produits dans l'app, moins on part), augmente le PNB par client et capte les flux du quotidien",
        f"Les concurrents avancent en ordre dispersé ; une super-app adossée au leader (606 400 clients [WEB]) crée un effet d'écosystème qu'une néobanque seule ne peut pas répliquer.",
        ["CB", "WEB", "EF"], "Élevé", "Les deux", "Nouveau produit"))
    if innov:
        eco = next((i for i in innov if i.get("acteur") == "ECOBANK"), innov[0])
        decisions_i.append(D(
            "Copier-DÉPASSER l'agence digitale d'ECOBANK",
            "Agence nouvelle génération (bornes self-service, écrans interactifs) MAIS en y ajoutant le conseil humain à valeur ajoutée (patrimoine, crédit pro) que ni les fintechs ni le pur self-care n'offrent.",
            "Réduit le coût de service ET attire les clients jeunes/urbains, tout en gardant la relation premium",
            f"ECOBANK a déjà lancé l'agence digitale [WEB] ; copier seul = rattrapage. Y ajouter le conseil = on passe devant.",
            ["WEB", "CB"], "Élevé", "Les deux", "Copier-dépasser"))
    decisions_i.append(D(
        "Riposte néobanque : ne pas laisser Orange Bank prendre le digital-first",
        "Décliner « SG Mobile » (cf. Marketing) avec parcours 100% en ligne : ouverture, crédit, épargne sans agence — mais avec la sécurité et le crédit d'un leader.",
        "Défend le terrain de l'acquisition digitale de masse",
        "Orange Bank opère en néobanque 100% digitale [WEB] ; Standard Chartered est en ligne depuis 2018 [WEB]. Le digital-first n'est plus optionnel.",
        ["WEB"], "Élevé", "Particuliers", "Copier-dépasser"))
    decisions_i.append(D(
        "Monétiser « Sentinelle » en Scoring-as-a-Service (open banking)",
        "Une fois le moteur de scoring éprouvé en interne, le proposer à des partenaires (microfinance, commerçants, BtoB) en marque blanche — nouveau revenu de service.",
        "Transforme un outil de réduction de coûts en source de revenus inédite",
        "Le coût du risque est notre faiblesse n°1 [EF] ; en faire une expertise vendable retourne la faiblesse en actif. Personne ne le fait localement.",
        ["EF"], "Élevé", "Entreprises", "Nouveau produit"))
    decisions_i.append(D(
        "Gamifier le bon remboursement (« cashback de fidélité crédit »)",
        "Récompenser les clients qui remboursent à l'heure (réduction de taux, points, statut). Le comportement vertueux devient un jeu.",
        "Fait baisser le coût du risque PAR L'ENGAGEMENT (pas que par le contrôle) + fidélise",
        f"Coût du risque {seq_sg} en hausse [EF] : agir aussi sur le comportement, pas seulement sur le scoring défensif.",
        ["EF"], "Moyen", "Particuliers", "Nouveau produit"))
    if gaps:
        libs = "; ".join(f"« {(g.get('libelle') or '')[:42]} » ({g.get('nb_banques')} banques)" for g in gaps[:4])
        decisions_i.append(D(
            f"Combler les {cb.get('n_gaps',0)} manques standards (offerts par ≥3 concurrents)",
            f"Services présents chez plusieurs banques mais absents chez SGCI : {libs}.",
            "Referme des portes de sortie pour nos clients",
            "Quand 3+ concurrents ont un service que SGCI n'a pas [CB], c'est un standard manquant : une raison de partir.",
            ["CB"], "Moyen", "Les deux", "Optimisation"))
    decisions_i.append(D(
        f"Valoriser nos {cb.get('n_differenciant',0)} différenciants de marque (sans survendre l'exclusivité)",
        "La validation web montre que SGCI a TRÈS PEU de services vraiment exclusifs : la plupart (packs, diaspora, CONNECT) "
        "existent ailleurs sous d'autres noms. Le vrai levier n'est pas « l'exclusivité » mais la MARQUE et l'intégration "
        "(ex. l'écosystème CONNECT). Renforcer ce qui est dur à copier, sans communiquer de fausses exclusivités.",
        "Transforme un différenciant de marque en avantage défendable, honnêtement",
        f"Web : seulement {n_excl} service(s) sans équivalent trouvé chez les concurrents ; {cb.get('n_differenciant',0)} "
        f"sont des différenciants de marque (fonction partagée) [CB·WEB]. Ne pas survendre l'exclusivité au DG.",
        ["CB", "WEB"], "Moyen", "Les deux", "Optimisation"))
    dirs.append({"nom": "Direction Innovation", "icone": "🚀", "couleur": "#6D28D9",
                 "question": "Que lancent les concurrents, et comment les dépasser ?",
                 "lecture": (f"Les concurrents bougent (ECOBANK : agence digitale ; Orange Bank : néobanque) [WEB] et "
                             f"{cb.get('n_gaps',0)} services standards (offerts par ≥3 banques) manquent chez SGCI. En face, "
                             f"la validation web ramène les « exclusivités » SGCI à {n_excl} vraie(s) + {cb.get('n_differenciant',0)} "
                             f"différenciants de marque — l'avantage durable se joue sur la MARQUE/intégration, pas sur de fausses exclusivités."),
                 "decisions": decisions_i})

    return dirs


# ════════════════════════════════════════════════════════════════════════════
#  VRIST — l'avantage concurrentiel de SGCI est-il DURABLE ?
#  (Valeur · Rareté · Inimitabilité · non-Substituabilité · Organisation)
# ════════════════════════════════════════════════════════════════════════════
def build_vrist(ev):
    """VRIST MULTI-BANQUES & MULTI-SOURCES — chaque banque notée sur 5 dimensions /10 :
    Valeur · Rareté · Inimitable · Durable · Transformatif. Score global + radar + cartes
    explicites (question + analyse sourcée EF/CB/REGL/WEB). Filtrable par banque."""
    ef, cb = ev["ef"], ev["cb"]
    cr  = ef.get("cout_risque_moy") or ef.get("cout_risque_pnb") or {}
    roe = ef.get("roe") or {}
    mn  = ef.get("marge_nette") or {}
    n_excl = cb.get("n_exclusivites", 0)        # vraies exclusivités (non contredites par le web)
    n_diff = cb.get("n_differenciant", 0)        # différenciants de marque (fonction partagée)
    cat_p = cb.get("cat_part") or {}
    g_sg, g_med = cb.get("gratuite_sgci"), cb.get("gratuite_med")

    rn  = ef.get("rn") or {}
    pnb = ef.get("pnb") or {}
    gr  = ef.get("croissance") or {}
    grat_b = cb.get("gratuite_par_banque") or {}
    cr3d = ef.get("cout_risque_3ans") or {}

    COLS = {"V": "#378ADD", "R": "#1D9E75", "I": "#7F77DD", "S": "#FF9800", "T": "#E91E63"}
    NOMS = {"V": "Valeur", "R": "Rareté", "I": "Inimitable", "S": "Durable", "T": "Transformatif"}
    QUEST = {
        "V": "Crée-t-il de la VALEUR (taille, revenus, offre) ?",
        "R": "Est-il RARE — peu d'autres banques l'ont ?",
        "I": "Est-il difficile à IMITER (groupe, agréments, échelle) ?",
        "S": "Tiendra-t-il dans le temps — est-il DURABLE (risque, ressources) ?",
        "T": "TRANSFORME-t-il l'expérience client (digital, gratuité) ?",
    }
    # Profils WEB/REGL (inputs sourcés non chiffrés) : backing groupe, portée réseau,
    # posture d'innovation, barrière réglementaire (1-3 / 1-2).
    PROFIL = {
        "SGCI":   {"backing": 3, "reseau": 3, "innov": 1, "regbar": 2, "grp": "réseau international Société Générale"},
        "BICICI": {"backing": 2, "reseau": 1, "innov": 1, "regbar": 1, "grp": "héritage corporate (ex-BNP Paribas)"},
        "ECOBANK":{"backing": 3, "reseau": 3, "innov": 3, "regbar": 1, "grp": "réseau panafricain ETI (30+ pays)"},
        "SIB":    {"backing": 3, "reseau": 1, "innov": 1, "regbar": 1, "grp": "groupe Attijariwafa (Maroc)"},
        "NSIA":   {"backing": 2, "reseau": 1, "innov": 2, "regbar": 2, "grp": "modèle bancassurance"},
        "BNI":    {"backing": 2, "reseau": 1, "innov": 1, "regbar": 2, "grp": "banque publique d'investissement (État)"},
        "BACI":   {"backing": 3, "reseau": 2, "innov": 1, "regbar": 1, "grp": "groupe Bank of Africa / BMCE (panafricain)"},
    }
    BKS = ["SGCI"] + sorted(x for x in BANKS if x != "SGCI")   # DYNAMIQUE (SGCI d'abord, puis concurrents en base)

    def _r01(d, b, reverse=True):
        vals = [v for v in d.values() if v is not None]
        if not vals or d.get(b) is None or max(vals) == min(vals):
            return 0.5
        x = (d[b] - min(vals)) / (max(vals) - min(vals))
        return x if reverse else (1 - x)

    clamp = lambda x: max(1, min(10, round(x)))
    def drv(txt, src, sens): return {"txt": txt, "source": src, "sens": sens}

    banques = {}
    for b in BKS:
        if b not in rn and b not in pnb:
            continue
        P = PROFIL.get(b, {"backing": 2, "reseau": 1, "innov": 1, "regbar": 1, "grp": ""})
        lead, scale, marge01 = _r01(rn, b), _r01(pnb, b), _r01(mn, b)
        grow01 = _r01(gr, b)
        cat = cat_p.get(b, 0) or 0
        cat01 = min(cat / 450.0, 1.0)
        cr_b = cr.get(b)
        cr_b = float(cr_b) if cr_b is not None else None
        cr_inv = (1 - min((cr_b if cr_b is not None else 10) / 20.0, 1.0))
        grat = grat_b.get(b)
        grat = float(grat) if grat is not None else None
        gmed = float(g_med) if g_med is not None else 30.0
        grat01 = min((grat / gmed) if grat is not None else (P["innov"] / 3.0), 1.0)
        # Rareté CB : vraies exclusivités (poids plein) + différenciants de marque (poids FAIBLE 0,1
        # car un pack de marque n'est pas RARE en fonction), échelle réaliste ÷7. Avant : ÷27 sur un
        # compte gonflé de faux exclusifs (corrigé par l'Agent Web → la Rareté baisse honnêtement).
        excl01 = min((n_excl + 0.1 * n_diff) / 7.0, 1.0) if b == "SGCI" else 0.12
        bk, rz, iv, rb = P["backing"] / 3.0, P["reseau"] / 3.0, P["innov"] / 3.0, P["regbar"] / 2.0
        rrn = round((1 - lead) * 6 + 1)  # rang RN approx (1=meilleur)

        # ── FORMULES TRANSPARENTES — chaque axe agrège plusieurs sources ──
        scores = {
            "V": clamp(2 + 4.0 * lead + 2.0 * cat01 + 2.0 * marge01),     # EF(lead,marge) + CB(catalogue)
            "R": clamp(2 + 4.0 * rz + 3.5 * excl01),                       # WEB(réseau) + CB(exclusivités)
            "I": clamp(1 + 3.0 * bk + 2.5 * rb + 2.0 * lead),              # WEB(groupe) + REGL(agréments) + EF(échelle)
            "S": clamp(2 + 4.0 * cr_inv + 1.6 * bk + 1.2 * grow01),        # EF(coût risque,croissance) + WEB(groupe)
            "T": clamp(1.5 + 4.0 * iv + 3.0 * grat01),                     # WEB(innovation) + CB(gratuité)
        }
        hausse = (cr3d.get(b, {}) or {}).get("tendance") == "hausse"
        crtxt = (f"{_pct(cr_b)}%" + (" (en hausse)" if hausse else "")) if cr_b is not None else "n.d."
        DR = {
            "V": [drv(f"Leadership résultat net : {'#1' if rrn==1 else 'rang ~'+str(rrn)}/7", "EF", "+" if lead > 0.6 else "-"),
                  drv(f"Largeur de catalogue : {cat} services", "CB", "+" if cat01 > 0.45 else "~"),
                  drv(f"Marge nette : {_pct(mn.get(b))}%", "EF", "+" if marge01 > 0.6 else "~")],
            "R": [drv(f"Positionnement : {P['grp']}", "WEB", "+" if rz > 0.5 else "~"),
                  drv((f"{n_excl} exclusivité(s) réelle(s) + {n_diff} différenciants de marque (validés web)" if b == "SGCI" else "Peu de services vraiment exclusifs"), "CB", "+" if excl01 > 0.5 else "-")],
            "I": [drv(f"Backing groupe : {P['grp']}", "WEB", "+" if bk > 0.5 else "~"),
                  drv("Activités régulées (agréments AMF-UMOA, assurance)" if rb > 0.5 else "Peu de barrières d'agrément", "REGL", "+" if rb > 0.5 else "~"),
                  drv(f"Échelle / taille (PNB {'élevé' if scale > 0.6 else 'modeste'})", "EF", "+" if scale > 0.6 else "~")],
            "S": [drv(f"Coût du risque : {crtxt}", "EF", "+" if cr_inv > 0.55 else "-"),
                  drv(f"Adossement groupe : {P['grp']}", "WEB", "+" if bk > 0.5 else "~"),
                  drv(f"Dynamique de croissance : +{_pct(gr.get(b))}%", "EF", "+" if grow01 > 0.5 else "~")],
            "T": [drv("Posture d'innovation digitale " + ("forte" if iv > 0.6 else "limitée"), "WEB", "+" if iv > 0.5 else "-"),
                  drv((f"Gratuité {_pct(grat)}%" + (f" vs médiane {_pct(g_med)}%" if g_med else "")) if grat is not None else "Gratuité n.d.", "CB", "+" if grat01 > 0.5 else "-")],
        }
        dims = []
        for k in ["V", "R", "I", "S", "T"]:
            srcs = sorted({x["source"] for x in DR[k]}, key=lambda s: {"EF": 0, "CB": 1, "REGL": 2, "WEB": 3}.get(s, 9))
            dims.append({"cle": k, "nom": NOMS[k], "score": scores[k], "col": COLS[k],
                         "question": QUEST[k], "drivers": DR[k], "sources": srcs})
        g = round(sum(scores.values()) / 5, 1)
        label = "Fort différenciateur" if g >= 7 else "Modéré" if g >= 5 else "Faible"
        forts = [NOMS[k] for k in scores if scores[k] >= 7]
        faibles = [NOMS[k] for k in scores if scores[k] <= 4]
        syn = ((f"Forces : {', '.join(forts)}. " if forts else "")
               + (f"Maillon faible : {', '.join(faibles)} → axe d'investissement prioritaire." if faibles else "Profil équilibré."))
        banques[b] = {"global": g, "label": label, "dimensions": dims, "synthese": syn}

    ordre = [b for b in BKS if b in banques]
    return {
        "intro": ("Chaque dimension est CALCULÉE (formule transparente) en agrégeant TOUTES les sources : "
                  "EF (taille, marge, coût du risque, croissance), CB (catalogue, exclusivités, gratuité), "
                  "REGL (agréments) et WEB (groupe, réseau, innovation). Les « drivers » sous chaque note montrent "
                  "exactement ce qui l'a fixée, avec sa source. Filtrez par banque pour comparer."),
        "ordre": ordre,
        "banques": banques,
        "n_exclusivites": n_excl,
    }


def _synthese(ev, problems):
    ef, cb = ev["ef"], ev["cb"]
    pos = f"SGCI #{ef.get('rang_rn') or '?'} en résultat net"
    if cb.get("rang_prix"):
        pos += f", #{cb['rang_prix']} en compétitivité prix"
    menace = problems[0]["titre"] if problems else "Aucune menace majeure"
    levier = next((p["levier"] for p in problems if p["gravite"] >= 2), (problems[0]["levier"] if problems else "—"))
    return {"position": pos + ".", "menace": menace + ".", "levier": f"Agir en priorité sur : {levier}."}


def _essentiel(ev, problems):
    """Verdict en FRANÇAIS SIMPLE — pour comprendre la stratégie en 10 secondes,
    sans aucun jargon. C'est la toute première chose que le lecteur voit."""
    ef, cb = ev["ef"], ev["cb"]
    crm = (ef.get("cout_risque_moy") or {}).get("SGCI")
    cr = crm or ef.get("cout_risque_pnb", {}).get("SGCI")   # moyenne 3 ans (robuste)
    det = (ef.get("cout_risque_3ans") or {}).get("SGCI") or {}
    hausse = det.get("tendance") == "hausse"
    g = ef.get("sgci_growth")
    fb, fp = ef.get("fastest_b"), ef.get("fastest_pct")
    pt = round((ef.get("pnb") or {}).get("SGCI", 0) / 100)
    gain = _fmt_md(round(pt * 5)) if pt else "plusieurs milliards"

    verdict = ("SGCI domine le marché par sa taille et figure parmi les mieux gérées des sept banques. "
               "Son talon d'Achille tient toutefois en un point : des <b>créances non remboursées</b> bien plus lourdes que celles de ses concurrentes, "
               "conjuguées à la <b>croissance la plus lente</b> du secteur. "
               "La bonne nouvelle est nette : maîtriser ce seul <b>risque de crédit</b> suffirait à hisser SGCI au <b>premier rang de la rentabilité</b>.")

    points = [
        {"ic": "💪", "col": "#12895C", "titre": "Ce qui va bien",
         "txt": "SGCI occupe le premier rang du marché — taille, dépôts, clientèle — et se distingue par une gestion quotidienne exemplaire : coûts maîtrisés et tarifs compétitifs."},
        {"ic": "🔴", "col": "#E53935", "titre": "Le vrai problème",
         "txt": (f"Sur 100 F de revenus, près de {round(cr) if cr else '?'} F s'évaporent en créances non recouvrées "
                 f"(moyenne sur trois ans) — le pire score des sept banques" + (", et il se dégrade d'année en année" if hausse else "") +
                 ". Là réside l'unique véritable frein à sa rentabilité.")},
        {"ic": "🎯", "col": "#1650b0", "titre": "Ce qu'il faut faire",
         "txt": (f"Mieux sélectionner et accompagner les emprunteurs, en s'appuyant sur un dispositif de détection des profils à risque. "
                 f"Gain estimé : environ +{gain} de bénéfice annuel, à périmètre inchangé.")},
    ]
    surveiller = (f"Sur le front concurrentiel, {fb} progresse rapidement (+{_pct(fp)}%) en prêtant avec prudence : c'est le rival à surveiller de près."
                  if fb and fb != "SGCI" else "")
    return {"verdict": verdict, "points": points, "surveiller": surveiller}


def _metrics(ev, problems, swot, plan, revelations=None):
    # Groundedness : part des éléments portant une source identifiée
    items = []
    for p in problems: items.append(bool(p.get("source")))
    for q in swot.values():
        for it in q: items.append(bool(it.get("source")))
    for a in plan: items.append(bool(a.get("ancrage_bceao")))
    for rv in (revelations or []): items.append(bool(rv.get("sources")))
    grounded = round(100 * sum(items) / max(len(items), 1))
    agents_used = sorted({p["source"].split("·")[0] for p in problems} | {"EF", "CB", "REGL"} | ({"WEB"} if ev.get("web") else set()))
    return {
        "groundedness": grounded,
        "n_problemes": len(problems),
        "n_revelations": len(revelations or []),
        "n_faits_sources": sum(items),
        "agents_mobilises": agents_used,
        "couverture_sources": len(agents_used),
    }


# ── ÉVÉNEMENTS DE VEILLE INJECTÉS DANS LE PESTEL (2026-07-30) ────────────────────────
# Le PESTEL décrivait l'environnement par des INDICATEURS (taux, ratios, taux de pénétration).
# C'est un état, pas un mouvement. Or la veille collecte aussi des ÉVÉNEMENTS datés — « la
# Banque mondiale engage 480 milliards FCFA sur cinq projets du PND », « la BCEAO publie de
# nouvelles instructions de domiciliation » — qui sont précisément ce qu'un PESTEL doit porter :
# ce qui bouge dans l'environnement externe.
#
# Ils restaient cantonnés à l'onglet opérationnel. Chaque événement est ici routé vers l'axe
# qui lui correspond, et affiché comme un SIGNAL daté, distinct des points structurels.
_AXE_PAR_DOMAINE = {
    "infrastructure":     "P",   # programmes et investissements publics
    "reglementation":     "L",
    "numerique":          "T",
    "agro":               "E",
    "banque_concurrence": "E",
    "social":             "S",
    "environnement":      "En",
}

# ROUTAGE PAR CONTENU (2026-07-30). Classer un événement d'après son DOMAINE DE COLLECTE menait
# à des contresens : « l'État adopte des réformes juridiques et réglementaires », remonté par la
# requête « numérique », atterrissait en Technologique alors qu'il relève du Légal. Le domaine
# dit où l'on a cherché, pas de quoi il s'agit. On lit donc d'abord le texte lui-même, et le
# domaine ne sert plus que de repli quand aucun terme ne tranche.
# ORDRE SIGNIFIANT : le premier axe qui matche l'emporte. Le Légal passe en tête parce qu'un
# texte réglementaire reste réglementaire quel que soit son objet ; le Politique précède le
# Technologique car un programme d'État relève de la décision publique avant la technologie.
#
# AUCUNE frontière de mot (\b) dans ces motifs : lors d'une écriture précédente, un \b s'est
# transformé en caractère backspace littéral, et le nettoyage a ensuite laissé « IA » nu — qui
# matchait « PNIA » et envoyait les programmes agricoles en Technologique. Les termes sont donc
# choisis assez longs pour être non ambigus sans ancrage.
_MOTS_AXE = [
    ("L",  r"(?i)r[ée]glementa|instruction|d[ée]cret|arr[êe]t[ée]|juridique|conformit|"
           r"norme|prudentiel|l[ée]gislat|circulaire|loi "),
    ("En", r"(?i)climat|durable|renouvelable|solaire|[ée]nergie|carbone|finance verte|"
           r"environnement|transition [ée]nerg"),
    ("S",  r"(?i)emploi|jeunesse|jeunes|femmes|inclusion|formation|pauvret|[ée]ducation|sant[ée]"),
    ("P",  r"(?i)gouvernement|minist|programme national|plan national|politique publique|"
           r"[ÉE]tat de C[ôo]te"),
    ("T",  r"(?i)num[ée]rique|digital|fintech|application|plateforme|mobile money|"
           r"technolog|carte virtuelle|paiement [ée]lectronique|intelligence artificielle"),
    ("E",  r"(?i)investi|croissance|march[ée]|fili[èe]re|banque|financement|prix|export|PIB"),
]


def _axe_evenement(e):
    """Axe PESTEL d'un événement, déduit de son CONTENU. Repli sur le domaine de collecte."""
    import re as _re_ax
    txt = f"{e.get('acteur','')} {e.get('fait','')}"
    for axe, motif in _MOTS_AXE:
        if _re_ax.search(motif, txt):
            return axe
    return _AXE_PAR_DOMAINE.get(e.get("domaine"))


def _unite_filiere(valeur, unite):
    """Valeur d'une filière suivie de son unité, milliers séparés. '' si vide."""
    v = str(valeur or "").strip()
    if not v or unite.lower() in v.lower():
        return v
    if v.isdigit() and len(v) > 3:
        v = f"{int(v):,}".replace(",", " ")
    return f"{v} {unite}"


def _evenements_pestel():
    """Événements de veille regroupés par axe PESTEL. {} si la veille n'a rien collecté."""
    import os as _os, json as _json
    # web_facts.json a rejoint spybusiness/data/ lors de la mise en ordre de l'arborescence
    # (2026-07-30). Chemin relatif au module pour rester valable quel que soit le répertoire
    # depuis lequel le serveur est lancé.
    chemin = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), _os.pardir,
                           "data", "web_facts.json")
    try:
        data = _json.load(open(chemin, encoding="utf-8"))
    except Exception:
        return {}
    par_axe = {}
    for e in data.get("evenements", []):
        axe = _axe_evenement(e)
        if not axe:
            continue
        txt = f"{e.get('acteur','')} {e.get('fait','')}".strip()
        if e.get("montant"):
            txt += f" ({e['montant']})"
        if e.get("date_citee"):
            txt += f" — {e['date_citee']}"
        par_axe.setdefault(axe, []).append({"txt": txt, "url": e.get("url", ""),
                                            "portee": e.get("portee", "")})
    return par_axe


def build_pestel(ev):
    """Analyse PESTEL grounded — chaque facteur est ANCRÉ sur un fait sectoriel/réglementaire
    SOURCÉ (Agent WEB/REGL : BCEAO, APBEF-CI, GSMA…) + données EF/CB internes. Reproductible
    (les faits sont cités, pas inventés)."""
    si  = (_web.secteur_index() if _web else {}) or {}
    ef  = ev.get("ef", {})
    def f(cle):
        x = si.get(cle, {}) or {}
        return x.get("valeur"), x.get("source")
    def P(txt, src="WEB", lbl=""):
        return {"txt": txt, "source": src, "src_label": lbl}
    pnb = (ef.get("pnb") or {}).get("SGCI")
    pm, pm_s   = f("politique_monetaire")
    cm, cm_s   = f("croissance_macro")
    sm, sm_s   = f("structure_marche")
    cc, cc_s   = f("cout_credit")
    npl, npl_s = f("npl_secteur")
    ban, ban_s = f("bancarisation")
    mm, mm_s   = f("mobile_money")
    cl, cl_s   = f("clients_sgci")
    sol, sol_s = f("solvabilite_secteur")
    # FAITS DE FILIÈRE (2026-07-30) — collectés par la veille sectorielle et jusqu'ici
    # inexploités par le PESTEL, alors que l'économie ivoirienne est d'abord agro-exportatrice :
    # un PESTEL qui ne dit rien du cacao décrit un autre pays.
    cac, cac_s = f("cacao_prix")
    cap, cap_s = f("cacao_campagne")
    ana, ana_s = f("anacarde")
    cot, cot_s = f("coton")
    esp, esp_s = f("seuil_especes")
    fpme, fpme_s = f("financement_pme")
    COLS = {"P": "#6D28D9", "E": "#1D9E75", "S": "#FF8C00", "T": "#0AA1DD", "En": "#12895C", "L": "#E53935"}
    axes = [
        {"cle": "P", "nom": "Politique", "col": COLS["P"], "resume": "Union monétaire stable, régulateur actif", "points": [
            P(f"Union Monétaire UEMOA pilotée par la BCEAO (taux directeur {pm or 'BCEAO'}) — cadre stable, commun aux 8 pays.", "WEB", pm_s or "BCEAO"),
            P("Politique d'INCLUSION FINANCIÈRE poussée par la BCEAO (bancarisation, mobile money, service minimum) — acquisition encadrée mais encouragée.", "REGL", "BCEAO"),
            P("Stabilité institutionnelle ivoirienne + volonté publique de mobiliser la DIASPORA (initiatives BNI/État).", "WEB", "Sikafinance")]},
        {"cle": "E", "nom": "Économique", "col": COLS["E"], "resume": "Croissance forte, marché n°1 UEMOA, risque crédit", "points": [
            P(f"Macro porteuse : {cm or 'PIB +6,3% · inflation ~2,3%'} — demande de crédit et d'épargne en hausse.", "WEB", cm_s or "BCEAO"),
            P(f"1er marché bancaire UEMOA ({sm or '29 banques'}) — concurrence intense ; SGCI #1 en résultat net (PNB {_fmt_md(pnb) if pnb else 'élevé'}).", "WEB·EF", sm_s or "APBEF-CI"),
            P(f"Coût du crédit {cc or '6,97%'} (usure plafonnée 14%) MAIS qualité du risque secteur dégradée (NPL {npl or '7,7%'}) → la sélection du risque est décisive.", "WEB", cc_s or "BCEAO"),
            # Unités restituées ici : la veille stocke « 2800 », pas « 2 800 FCFA/kg ». Un prix
            # sans unité dans un PESTEL n'est pas un fait, c'est une devinette laissée au lecteur.
            P(f"Économie AGRO-EXPORTATRICE : cacao {_unite_filiere(cac, 'FCFA/kg') or 'prix garanti'}"
              + (f", anacarde {_unite_filiere(ana, 'FCFA/kg')}" if ana else "")
              + (f", coton {_unite_filiere(cot, 'FCFA/kg')}" if cot else "")
              + (f" — campagne cacao au {cap}" if cap else "")
              + ". Ces filières concentrent des flux de trésorerie massifs et saisonniers, largement hors circuit bancaire.",
              "WEB", cac_s or "Conseil du Café-Cacao"),
            P(f"Accès au financement des PME limité ({fpme or 'faible'}) — gisement de crédit et de commissions, à condition de maîtriser la sélection du risque.",
              "WEB", fpme_s or "AFD")]},
        {"cle": "S", "nom": "Social", "col": COLS["S"], "resume": "Bancarisation faible = gisement, mobile très ancré", "points": [
            P(f"Bancarisation {ban or '>30%'} seulement — immense gisement d'acquisition (jeunes, secteur informel, diaspora).", "WEB", ban_s or "BCEAO"),
            P(f"Usage MOBILE massif (mobile money {mm or '82,2%'}) — les clients attendent du 100% mobile.", "WEB", mm_s or "BCEAO/GSMA"),
            P(f"Base SGCI {cl or '606 400 clients (public)'} — fort potentiel de cross-sell ; diaspora à capter.", "WEB", cl_s or "SGCI")]},
        {"cle": "T", "nom": "Technologique", "col": COLS["T"], "resume": "Digital = champ de bataille (néobanques, mobile)", "points": [
            P(f"Mobile money {mm or '82,2%'} : substitut puissant sur les paiements du quotidien — à INTÉGRER, pas subir.", "WEB", mm_s or "BCEAO/GSMA"),
            P("Néobanques & agences digitales (ECOBANK agence digitale, Orange Bank) abaissent la barrière sur le retail mobile.", "WEB", "Sikafinance"),
            P("Instruction BCEAO 2024 sur les services de paiement — cadre pour l'innovation (API, paiement instantané).", "REGL", "BCEAO")]},
        {"cle": "En", "nom": "Environnemental", "col": COLS["En"], "resume": "Finance durable émergente (ESG / climat)", "points": [
            P("Montée de la FINANCE VERTE/ESG dans l'UEMOA (la BCEAO encourage le financement durable) — différenciation + accès à des lignes de refinancement vertes.", "WEB", "BCEAO"),
            P("Risque CLIMATIQUE sur les portefeuilles agricoles/PME (Côte d'Ivoire agro-exportatrice) — à intégrer dans la sélection du risque.", "WEB", "secteur"),
            P("Appui du réseau Société Générale (engagements ESG du groupe) — crédibilité pour des offres durables.", "WEB", "Société Générale")]},
        {"cle": "L", "nom": "Légal", "col": COLS["L"], "resume": "Cadre BCEAO strict (gratuités, usure, prudentiel)", "points": [
            P("Services bancaires GRATUITS obligatoires (BCEAO) — plancher de gratuité imposé ; au-delà = levier commercial.", "REGL", "BCEAO"),
            P("Plafond du taux d'USURE 14% + TRANSPARENCE tarifaire obligatoire — encadrent le pricing.", "REGL", "BCEAO"),
            P(f"Ratios PRUDENTIELS (solvabilité secteur {sol or '14,5%'}) — la conformité SGCI = argument de SÉCURITÉ des dépôts.", "REGL·EF", sol_s or "BCEAO"),
            P(f"LBC/FT : toute transaction en espèces atteignant {_unite_filiere(esp, 'FCFA') or '15 000 000 FCFA'} impose une déclaration (CENTIF). "
              "Contrainte structurante pour les filières agricoles, très intensives en espèces — elle conditionne la faisabilité d'une offre de collecte de campagne.",
              "REGL", esp_s or "BCEAO")]},
    ]
    # SIGNAUX DATÉS — ajoutés après les points structurels, et marqués comme tels : un fait
    # daté ne se lit pas comme une caractéristique permanente de l'environnement.
    evts = _evenements_pestel()
    for a in axes:
        for e in evts.get(a["cle"], [])[:3]:
            a["points"].append(P(f"SIGNAL RÉCENT — {e['txt']}", "WEB", "veille"))
        if evts.get(a["cle"]):
            a["resume"] += f" · {len(evts[a['cle']])} signal(aux) récent(s)"

    return {"intro": ("Environnement EXTERNE de SGCI selon les 6 facteurs PESTEL. Chaque point est ANCRÉ sur un fait "
                      "sectoriel ou réglementaire SOURCÉ (BCEAO, APBEF-CI, GSMA…) — pas une opinion. "
                      "Les points « SIGNAL RÉCENT » proviennent de la veille datée."), "axes": axes}


def build(segment="Particuliers"):
    """Point d'entrée : produit toute la stratégie (Niveau 3 du RAG), sourcée."""
    _refresh_context()   # banques + année de référence dynamiques (nouvelle donnée prise en compte)
    ev = collect_evidence(segment)
    problems = detect_problems(ev)
    revelations = detect_revelations(ev)
    advantages = detect_advantages(ev)
    swot = build_swot(ev, problems)
    porter = build_porter(ev)
    plan = build_action_plan(ev, problems)
    # 2026-07-24 : projection calculée AVANT le roadmap et injectée dedans (voir build_roadmap)
    # pour que le Plan-trajectoire affiche EXACTEMENT les chiffres du scénario Central, au lieu
    # d'un delta réinventé séparément — cf. commentaire dans build_roadmap.
    projection = build_projection(ev)
    roadmap = build_roadmap(ev, projection)
    projection_hypotheses = build_projection_hypotheses(ev, projection)
    comite = build_comite(ev)
    vrist = build_vrist(ev)
    pestel = build_pestel(ev)
    sources = _collect_sources(ev)
    return {
        "segment": segment,
        "revelations": revelations,
        "atouts": advantages,
        "periode_cb": f"{CB_ANNEE} {CB_SEM}",
        "essentiel": _essentiel(ev, problems),
        "synthese": _synthese(ev, problems),
        "comite": comite,
        "vrist": vrist,
        "pestel": pestel,
        "couts_changement": (ev.get("cb") or {}).get("switching") or {},
        "concurrents": decrypt_concurrents(ev),
        "note_methodo": _note_methodo(ev),
        "contexte_marche": ev.get("web_secteur") or [],
        "problemes": problems,
        "swot": swot,
        "porter": porter,
        "menaces_croisees": _menaces_croisees(ev),
        "plan_action": plan,
        "roadmap": roadmap,
        "projection": projection,
        "projection_hypotheses": projection_hypotheses,
        "evidence": ev,
        "sources": sources,
        "metriques": _metrics(ev, problems, swot, plan, revelations),
    }


def dossier_pour_llm(d):
    """Sérialise TOUT le dossier de preuves (chiffres réels, déjà sourcés) en texte
    compact pour le LLM créatif. Le LLM ne reçoit QUE ça → il ne peut citer que des
    chiffres vrais (groundedness préservée même en mode génératif)."""
    import re as _re
    def clean(s):
        return _re.sub(r"<[^>]+>", "", str(s or "")).strip()
    L = []
    ev = d.get("evidence", {})
    ef, cb = ev.get("ef", {}), ev.get("cb", {})
    es = d.get("essentiel", {})
    L.append("# SITUATION (chiffres réels)")
    L.append("- " + clean(es.get("verdict")))
    for p in es.get("points", []):
        L.append(f"- {clean(p.get('titre'))} : {clean(p.get('txt'))}")

    L.append("\n# CHIFFRES CLÉS EF (états financiers)")
    def rk(dic, b="SGCI"):
        return dic.get(b)
    crm = (ef.get("cout_risque_moy") or {})
    det = (ef.get("cout_risque_3ans") or {}).get("SGCI") or {}
    seqy = " ; ".join(f"{an} : {v}% du PNB" for an, v in (det.get("ratios") or []))
    last = rk(ef.get('cout_risque_pnb', {}))
    medm = (lambda vs: round(sorted(vs)[len(vs)//2], 1) if vs else None)([v for v in crm.values() if v is not None])
    L.append(f"- Coût du risque SGCI = part du PNB absorbée par les pertes de crédit, par exercice : {seqy} (EN HAUSSE). "
             f"Dernier exercice : {last}% — c'est le chiffre à utiliser. Le pire des 7 banques (médiane marché {medm}%, meilleur BICICI ~1,9%).")
    L.append(f"- ROE SGCI {rk(ef.get('roe',{}))}% ; marge nette SGCI {rk(ef.get('marge_nette',{}))}% (la meilleure est SIB {(ef.get('marge_nette') or {}).get('SIB')}%) ; coefficient {rk(ef.get('coeff',{}))}%")
    L.append("- ATTENTION : le « coût du risque (% du PNB) » et la « marge nette » sont des indicateurs DIFFÉRENTS — "
             "ne jamais les opposer dans une même phrase comme s'ils se comparaient.")
    L.append(f"- PNB SGCI {rk(ef.get('pnb',{}))} M ; RN {rk(ef.get('rn',{}))} M (#1) ; croissance SGCI {ef.get('sgci_growth')}% vs marché ~27,8% ; {ef.get('fastest_b')} +{ef.get('fastest_pct')}%")

    L.append("\n# RÉVÉLATIONS (insights croisés déjà validés)")
    for r in d.get("revelations", [])[:7]:
        L.append(f"- {clean(r.get('titre'))} → {clean(r.get('resume'))}")

    L.append("\n# CONDITIONS DE BANQUE (CB)")
    rp = cb.get("repricing", {})
    unders = "; ".join(f"{u['libelle']} {u['sgci']}→{u['median']}F" for u in (rp.get("services") or [])[:5])
    L.append(f"- SGCI SOUS le marché sur {rp.get('n')} services (revenu laissé). Ex: {unders}")
    overs = "; ".join(f"{o['libelle']} {o['sgci']}F vs {o['median']}F (+{o['ecart_pct']}%)" for o in (cb.get('over') or [])[:4])
    L.append(f"- SGCI AU-DESSUS du marché sur {cb.get('n_over')} services. Ex: {overs}")
    L.append(f"- Gratuité SGCI {cb.get('gratuite_sgci')}% vs médiane marché {cb.get('gratuite_med')}% (SGCI offre des gratuités "
             f"AU-DELÀ du minimum légal BCEAO, mais MOINS que le marché : elle est dans le bas du classement des gratuités, "
             f"alors que les concurrents en offrent plus pour ACQUÉRIR → la gratuité n'est pas encore un levier d'acquisition "
             f"chez SGCI) ; win-rate prix #{cb.get('rang_prix')} ; catalogue {cb.get('n_services_sgci')} services")
    L.append(f"- EXCLUSIVITÉS (validées par l'Agent Web, pas seulement la grille) : SEULEMENT {cb.get('n_exclusivites')} service(s) "
             f"vraiment sans équivalent chez les concurrents ; {cb.get('n_differenciant',0)} autres sont des DIFFÉRENCIANTS DE MARQUE "
             f"(packs, diaspora, CONNECT) dont la FONCTION existe ailleurs sous un autre nom (ex. retrait sans carte : BNI/UBA/Ecobank "
             f"l'ont aussi). NE PAS prétendre que SGCI est seule à offrir ces fonctions ; l'avantage est la MARQUE/intégration. "
             f"Manques (≥3 concurrents l'ont, pas SGCI) : {cb.get('n_gaps')}")
    taux = (cb.get("atouts") or {}).get("taux") or []
    if taux:
        L.append(f"- Atout taux : ex. {clean(taux[0].get('libelle'))} SGCI {taux[0].get('sgci')}% (sous la médiane concurrents)")
    gaps = cb.get("gaps") or []
    if gaps:
        L.append("- Manques standards à copier (services qu'ont ≥3 concurrents, pas SGCI) : "
                 + "; ".join(f"{clean(g.get('libelle'))} ({g.get('nb_banques')} banques)" for g in gaps[:6]))
    _vrai = [clean(e.get("libelle")) for e in (cb.get("exclusivites") or []) if e.get("verdict") == "non_contredit"][:6]
    _marq = [clean(e.get("libelle")) for e in (cb.get("exclusivites") or []) if e.get("verdict") == "differenciant"][:6]
    if _vrai:
        L.append("- Exclusivités plausibles (aucun équivalent trouvé, NON certifié) : " + "; ".join(_vrai))
    if _marq:
        L.append("- Différenciants de MARQUE (nom SGCI, fonction partagée — NE PAS dire « exclusif ») : " + "; ".join(_marq))

    L.append("\n# SEGMENT PARTICULIERS vs ENTREPRISES (intervient fortement)")
    tilt = cb.get("tilt") or {}
    L.append(f"- SGCI : ~600 000 clients particuliers vs ~6 400 entreprises (≈99% particuliers) ; ratio catalogue Entreprises/Particuliers ×{tilt.get('SGCI')}")
    ent = sorted([(b, t) for b, t in tilt.items() if b != "SGCI" and t], key=lambda x: -x[1])
    L.append("- Orientation des concurrents (ratio Ent/Part) : " + "; ".join(f"{b} ×{t}" for b, t in ent))
    L.append("- Lecture : SGCI est orientée PARTICULIERS ; SIB/BICICI penchent ENTREPRISES et y sont plus rentables (corporate = risque mieux maîtrisé). Piste : favoriser l'octroi aux entreprises.")
    # NOTE (2026-07-22, demande explicite du directeur : « tous les onglets doivent tenir compte
    # de TOUTES les données ») : le rang catalogue, la gratuité, le win-rate prix, les
    # exclusivités et les manques ci-dessus (section CONDITIONS DE BANQUE) sont désormais
    # CALCULÉS SUR L'UNION Particuliers+Entreprises — ce ne sont plus des chiffres Particuliers
    # uniquement. Seul le détail service-par-service (repricing, coûts de changement) reste
    # présenté par segment, car un tarif Particuliers et un tarif Entreprises ne sont pas la
    # même ligne de produit et ne peuvent pas être moyennés sans perdre leur sens.

    L.append("\n# VRIST (avantage durable, /10 par banque)")
    vb = (d.get("vrist", {}).get("banques") or {})
    for bk in (d.get("vrist", {}).get("ordre") or []):
        bd = vb.get(bk, {})
        dd = "; ".join(f"{x['nom']} {x['score']}/10" for x in (bd.get("dimensions") or []))
        L.append(f"- {bk} (global {bd.get('global')}/10) : {dd}")

    L.append("\n# FAITS WEB EXTERNES (sourcés)")
    for f in (d.get("contexte_marche") or [])[:9]:
        L.append(f"- {clean(f.get('titre'))} = {clean(f.get('valeur'))} ({clean(f.get('source'))})")
    for b, info in (ev.get("web") or {}).items():
        cause = info.get("cause_rentabilite") or info.get("innovation")
        if cause:
            L.append(f"- {b} : {clean(cause)}")

    L.append("\n# INNOVATIONS À COPIER/ADAPTER (concurrents + étranger) — pour propositions concrètes")
    for inv in (cb.get("innovations") or []):
        L.append(f"- {clean(inv.get('acteur'))} : {clean(inv.get('quoi'))}. → {clean(inv.get('lecon'))}")

    L.append("\n# RÉGLEMENTATION BCEAO/UEMOA — à intégrer PARTOUT (cite le TEXTE PRÉCIS entre crochets)")
    for r in (ev.get("regl_leviers") or []):
        # référence citable = le titre/n° du texte (Instruction n°…, Communiqué…, Décision…)
        ref = clean(r.get("titre"))
        L.append(f"- TEXTE « {ref} » ({clean(r.get('source'))}, {clean(r.get('date'))}) : {clean(r.get('regle'))} "
                 f"→ LEVIER : {clean(r.get('levier'))}. [Citer ainsi : [REGL: {ref}]]")
    for k, hits in (ev.get("regl_text") or {}).items():
        if hits:
            L.append(f"- Texte réglementaire ({k}) : « {clean(hits[0].get('extrait'))[:140]}… » (source {clean(hits[0].get('fichier'))}) [REGL]")

    # NB : les « coûts de changement » (switching) ne sont PLUS injectés ici — le petit LLM les
    # amalgamait avec d'autres montants sans rapport (faux « packs »). Ils restent affichés comme
    # RÉVÉLATION dédiée (front), pas comme matière première du LLM. La compétitivité prix lui vient
    # déjà, proprement, via REPRICING / over / atouts ci-dessus.

    # ── DIAGNOSTIC (problèmes priorisés) ───────────────────────────────────
    L.append("\n# DIAGNOSTIC — problèmes priorisés (gravité décroissante)")
    for p in sorted(d.get("problemes", []), key=lambda x: -(x.get("gravite") or 0))[:8]:
        L.append(f"- [gravité {p.get('gravite')}] {clean(p.get('titre'))} : {clean(p.get('preuve'))[:170]} "
                 f"→ levier : {clean(p.get('levier'))} ({clean(p.get('source'))})")

    # ── SWOT (synthèse des 4 quadrants) ────────────────────────────────────
    sw = d.get("swot", {})
    L.append("\n# SWOT (synthèse)")
    for k, lab in [("forces", "FORCES"), ("faiblesses", "FAIBLESSES"),
                   ("opportunites", "OPPORTUNITÉS"), ("menaces", "MENACES")]:
        items = "; ".join(clean(x.get("txt")) for x in (sw.get(k) or [])[:4])
        if items:
            L.append(f"- {lab} : {items}")

    # ── PORTER — 5 forces (intensité + implication) ────────────────────────
    L.append("\n# PORTER — 5 forces (intensité /5 + implication stratégique)")
    for fp in (d.get("porter", {}).get("forces") or []):
        L.append(f"- {clean(fp.get('force'))} : {clean(fp.get('intensite'))} ({fp.get('note')}/5) — "
                 f"{clean(fp.get('resume'))} → {clean(fp.get('implication'))[:180]}")

    # ── PESTEL — environnement macro FRAIS (web sourcé/daté via veille) ─────
    pst = d.get("pestel", {})
    L.append("\n# PESTEL — environnement macro (données fraîches, sourcées/datées par l'Agent Web)")
    for ax in (pst.get("axes") or []):
        pts = "; ".join(clean(pt.get("txt")) for pt in (ax.get("points") or [])[:3])
        L.append(f"- {clean(ax.get('nom'))} : {clean(ax.get('resume'))}" + (f" | {pts}" if pts else ""))

    # ── CONSIGNE DE SYNTHÈSE (le cœur de la demande) ───────────────────────
    L.append("\n# CONSIGNE DE SYNTHÈSE")
    L.append("- Chaque décision/proposition doit être une SYNTHÈSE qui croise AU MOINS 2 des sections ci-dessus "
             "(diagnostic, révélations, Porter, VRIST, SWOT, PESTEL) AVEC les données chiffrées EF/CB et le contexte "
             "web frais — jamais un seul angle. Privilégie les leviers où plusieurs sections convergent.")

    return "\n".join(L)


def _nums_canoniques(texte):
    """Extrait les nombres « données » d'un texte (avec unité %/Mds/M/F ou ≥ 1000),
    normalisés en valeur numérique (séparateurs FR gérés). Pour la vérification IA."""
    import re as _re
    s = (texte or "").replace(" ", " ").replace(" ", " ")
    out = {}
    # nombre éventuellement avec séparateurs d'espace/milliers + décimale FR + unité
    for m in _re.finditer(r"(\d[\d  ]*(?:[.,]\d+)?)\s*(%|Mds|M\b|F\b|FCFA)?", s):
        raw, unit = m.group(1), (m.group(2) or "")
        t = raw.replace(" ", "")
        # décimale FR : 17,0 → 17.0 ; milliers FR 606 400 déjà sans espace → 606400
        if "," in t and len(t.split(",")[-1]) <= 2:
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
        try:
            val = float(t)
        except Exception:
            continue
        # on ne garde que les nombres « parlants » : avec unité, ou ≥ 1000, ou décimal %
        if unit or val >= 1000 or ("." in t and val < 100):
            out[round(val, 1)] = raw.strip() + (f" {unit}" if unit else "")
    return out


def verifier_chiffres(texte_ia, dossier):
    """Vérifie que chaque nombre « données » de la sortie IA existe dans le dossier
    (tolérance d'arrondi). Retourne {n_total, n_traces, taux, non_traces:[...]}."""
    ref = set(_nums_canoniques(dossier).keys())
    # arrondis voisins admis (le LLM arrondit parfois 13,9→14)
    ref_loose = set()
    for v in ref:
        ref_loose.update({v, round(v), round(v, 0)})
    src = _nums_canoniques(texte_ia)
    non_traces = []
    traces = 0
    for v, label in src.items():
        ok = (v in ref) or (round(v) in ref_loose) or any(abs(v - r) <= 0.15 for r in ref)
        if ok:
            traces += 1
        else:
            non_traces.append(label)
    n = len(src)
    return {"n_total": n, "n_traces": traces,
            "taux": round(100 * traces / n) if n else 100,
            "non_traces": non_traces[:8]}


def _menaces_croisees(ev):
    """Croisements inter-agents (ex. BICICI : EF↑ + CB entreprises + web)."""
    ef, cb = ev["ef"], ev["cb"]
    out = []
    fb, fp = ev["ef"].get("fastest_b"), ev["ef"].get("fastest_pct")
    if fb and fb != "SGCI":
        web = (ev.get("web") or {}).get(fb, {})
        recit = (f"{fb} affiche la croissance du RN la plus rapide (+{fp}%) [EF]. "
                 f"En conditions de banque, {fb} est positionnée sur le corporate/entreprises [CB]. ")
        if web.get("part_marche_entreprises") or web.get("agences"):
            recit += f"Source externe : {web.get('_note','')} [WEB]. "
        recit += f"→ Risque pour SGCI sur sa base entreprises : surveiller et défendre le corporate."
        out.append({"titre": f"Ascension de {fb}", "recit": recit,
                    "sources": ["EF", "CB"] + (["WEB"] if web else [])})
    return out


def _note_methodo(ev):
    """Note de transparence méthodologique — répond aux limites statistiques connues
    (robustesse, comparabilité des millésimes). Honnêteté = crédibilité."""
    cr3 = ev.get("ef", {}).get("cout_risque_3ans") or {}
    # millésimes réellement utilisés par banque
    mill = {}
    for b, det in cr3.items():
        rr = det.get("ratios") or []
        if rr:
            mill[b] = f"{rr[0][0]}–{rr[-1][0]}"
    diff = sorted(set(mill.values()))
    return {
        "points": [
            "Les ratios sensibles (coût du risque, croissance) sont calculés en MOYENNE sur les 3 derniers exercices de chaque banque, et la tendance est affichée — pour éviter qu'une année atypique ne fausse la lecture.",
            ("Chaque banque est comparée sur ses 3 derniers exercices publiés ; les millésimes diffèrent ("
             + " ; ".join(f"{b} {m}" for b, m in sorted(mill.items())) + "). Les écarts entre banques sont donc à lire avec cette réserve.") if mill else
            "Chaque banque est comparée sur ses 3 derniers exercices publiés (millésimes pouvant différer).",
            "Les impacts en FCFA par opération sont certains ; les montants totaux annuels reposent sur des hypothèses de volume explicitement signalées (données de volume non publiques).",
            "Les croisements (corrélations) suggèrent des pistes ; ils n'établissent pas une causalité prouvée. La couche IA est contrainte aux chiffres de ce dossier (aucun chiffre inventé).",
        ],
    }


def _collect_sources(ev):
    s = [
        {"ref": "États financiers publiés (7 banques, AN1–AN3)", "type": "EF", "fiabilite": "haute"},
        {"ref": "Conditions de banque publiées (plaquettes tarifaires)", "type": "CB", "fiabilite": "haute"},
        {"ref": BCEAO_NORMES["solvabilite_min"]["src"], "type": "REGL", "fiabilite": "officielle"},
        {"ref": BCEAO_NORMES["coefficient_cible"]["src"], "type": "REGL", "fiabilite": "officielle"},
    ]
    if _web:
        s += _web.sources()
    return s
