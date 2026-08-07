"""
agents.py — Couche AGENTS : porte d'entrée UNIQUE de récupération du système RAG.
============================================================================
Chaque agent possède des outils de récupération sur la MÊME base de connaissance
PostgreSQL :
  • structuré  (SQL exact / agrégations → db.py)   — chiffres précis
  • sémantique (vecteurs pgvector → retriever)      — texte (réglementation, web)

TOUTES les sorties du système passent par cette couche :
  - Dashboards CB / EF   → AGENTS["CB"|"EF"].structured.<outil>(...)
  - Chat (chain.py)      → récupération multi-agents (sémantique)
  - Stratégie (Niveau 3) → mobilise tous les agents (CB + EF + REGL + WEB)

But : une seule architecture RAG, pas de pipeline parallèle. db.py n'est pas
« à côté » du RAG — c'est l'OUTIL STRUCTURÉ des agents CB et EF.
"""
import db


class _StructuredTools:
    """Proxy d'outils structurés d'un agent.
    Usage : AGENTS['CB'].structured.cb_analyse_q6(...)   (accès direct)
            AGENTS['CB'].structured('cb_analyse_q6', ...) (par nom)
    → délègue à la fonction db.* correspondante (récupération SQL).
    """
    def __init__(self, fnmap):
        object.__setattr__(self, "_fnmap", fnmap)

    def __getattr__(self, name):
        fn = object.__getattribute__(self, "_fnmap").get(name)
        if fn is None:
            raise AttributeError(f"Outil structuré inconnu : {name}")
        return fn

    def __call__(self, tool, *args, **kwargs):
        fn = object.__getattribute__(self, "_fnmap").get(tool)
        if fn is None:
            raise KeyError(f"Outil structuré inconnu : {tool}")
        return fn(*args, **kwargs)

    def tools(self):
        return sorted(object.__getattribute__(self, "_fnmap"))


class Agent:
    """Un agent du RAG = une base de connaissance + ses outils de récupération."""
    def __init__(self, name, label, structured_fnmap, semantic=None):
        self.name = name
        self.label = label
        self.structured = _StructuredTools(structured_fnmap)
        self._semantic = semantic

    def semantic(self, *args, **kwargs):
        if self._semantic is None:
            raise RuntimeError(f"Agent {self.name} : pas d'outil sémantique branché")
        return self._semantic(*args, **kwargs)


# ── Agent CB — Conditions de banque (outils structurés = fonctions cb_*/frais_* de db.py) ──
_CB_TOOLS = {n: getattr(db, n) for n in [
    "cb_periodes", "cb_analyse_q1", "cb_analyse_q2", "cb_analyse_q3", "cb_exclusivites_banque", "cb_analyse_q5", "cb_analyse_q6",
    "cb_analyse_q6_paired", "cb_evolution_details", "cb_all_evolutions_summary",
    "cb_serie_temporelle", "cb_rattrapage_depassement", "cb_innovation_vs_finance",
    "cb_prix_par_libelle", "cb_prix_competitivite", "cb_libelles_tous",
    "cb_analyse_q6_tous_segments", "cb_prix_competitivite_tous_segments",
    "cb_par_section", "cb_par_sous_section", "cb_imputations", "cb_exhaustif",
    "cb_all_for_period", "cb_annees", "cb_positionnement_bd", "frais_tenue_compte",
]}

# ── Agent EF — États financiers (outils structurés = fonctions ef_*/kpis/rn de db.py) ──
_EF_TOOLS = {n: getattr(db, n) for n in [
    "ef_pnb_series", "ef_roe_series", "ef_coeff_series", "ef_cnr_series",
    "kpis_vue_ensemble", "resilience_data", "resultat_net", "resultat_net_series",
    "rn_by_anx", "roe_by_anx", "croissance_series", "ef_series_all_for_agent",
    "ef_cout_risque_3ans",
]}

# ── Agent REGL — Réglementation (récupération SÉMANTIQUE réelle sur regl_documents) ──
# Outils structurés = recherche vectorielle pgvector (regl_semantic) + repli plein-texte
# (regl_keyword). C'est un VRAI retriever RAG : embedding de la requête → cosine sur les
# 88 chunks réglementaires → extraits sourcés (fichier + score).
_REGL_TOOLS = {n: getattr(db, n) for n in ["regl_semantic", "regl_keyword"]}

# ── Agent WEB — Veille externe (faits cités & reproductibles via run_veille.py) ──
try:
    import web_facts as _wf
    _WEB_TOOLS = {"facts_for": _wf.facts_for, "sources": _wf.sources, "maj": _wf.maj,
                  "secteur": _wf.secteur, "secteur_index": _wf.secteur_index,
                  "innovations": _wf.innovations, "reglementation": _wf.reglementation}
except Exception:
    _WEB_TOOLS = {}

AGENTS = {
    "CB":   Agent("CB",   "Conditions de banque", _CB_TOOLS),
    "EF":   Agent("EF",   "États financiers",     _EF_TOOLS),
    "REGL": Agent("REGL", "Réglementation",       _REGL_TOOLS,
                  semantic=getattr(db, "regl_semantic", None)),  # vrai retriever pgvector
    "WEB":  Agent("WEB",  "Veille web",           _WEB_TOOLS),  # Bloc 2 : module de veille reproductible
}
