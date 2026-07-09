"""
Classification 8 axes BCEAO pour l'analyse d'exclusivités Q3/Q5.

L'approche SQL trigram échoue sur les synonymes bancaires (ex. "Virement FCFA"
≡ "Virement UEMOA"). Ce module classe d'abord chaque libellé dans un axe, puis
le LLM valide sémantiquement les candidats exclusifs dans chaque axe.
"""
import re
import unicodedata
from difflib import get_close_matches
from functools import lru_cache

AXES = {
    1: "Packages & Comptes",
    2: "Cartes Bancaires",
    3: "Produits d'Épargne",
    4: "Crédits & Financements",
    5: "Assurances",
    6: "Services Digitaux & Paiements",
    7: "Services aux Marchés Financiers",
    8: "Autres Services Distinctifs",
}

AXE_COLORS = {
    1: "#7F77DD", 2: "#378ADD", 3: "#1D9E75", 4: "#FF9800",
    5: "#E91E63", 6: "#06B6D4", 7: "#8B5CF6", 8: "#6B7280",
}

AXE_ICONS = {
    1: "📦", 2: "💳", 3: "💰", 4: "🏦", 5: "🛡", 6: "📱", 7: "📈", 8: "🔧",
}

def _norm(text):
    """Normalise : minuscules + suppression accents."""
    text = unicodedata.normalize("NFD", (text or "").lower())
    return " ".join("".join(c for c in text if unicodedata.category(c) != "Mn").split())


# ── Normalisation CANONIQUE des libellés de service ─────────────────────────
# Objectif : deux libellés qui désignent le MÊME service (même but) produisent
# la même forme canonique, même s'ils sont écrits différemment d'une banque à
# l'autre. Corrige les faux exclusifs (« tenue de compte » vs « gestion de
# compte ») ET les doublons (« compte chèque » vs « compte chèques »).
_STOP = {"de", "du", "des", "d", "l", "la", "le", "les", "un", "une", "pour", "par",
         "en", "et", "ou", "a", "au", "aux", "sur", "sous", "avec", "sans", "of", "the"}
# Mots génériques de tarification : ils n'identifient pas le service lui-même.
_GENERIC = {"frais", "commission", "cout", "tarif", "montant", "prix", "mensuel",
            "mensuelle", "annuel", "annuelle", "trimestriel", "trimestrielle",
            "mois", "an", "annee", "ligne", "minimum", "forfait", "forfaitaire"}
# Familles de synonymes (forme SINGULIÈRE) → jeton canonique unique.
_SYN = {
    "tenue": "gestion", "convenance": "gestion", "fonctionnement": "gestion",
    "administration": "gestion", "maintien": "gestion",
    "transfert": "virement", "vir": "virement",
    "souscription": "abonnement", "adhesion": "abonnement", "cotisation": "abonnement",
}

def _singular(tok):
    return tok[:-1] if len(tok) > 3 and tok.endswith("s") else tok

@lru_cache(maxsize=16384)
def canon_lib(text):
    """Forme canonique d'un libellé (chaîne) : minuscules, sans accents, sans mots
    vides ni mots de tarification, singularisée, synonymes unifiés. Sert à
    comparer/dédupliquer des services de banques différentes.
    Mémoïsée : appelée des milliers de fois par le pré-filtre d'exclusivités."""
    base = re.sub(r"[^a-z0-9 ]", " ", _norm(text))
    toks = []
    for t in base.split():
        if t in _STOP or t in _GENERIC:
            continue
        t = _SYN.get(_singular(t), _singular(t))
        if len(t) >= 2:
            toks.append(t)
    return " ".join(toks)

@lru_cache(maxsize=16384)
def canon_key(text):
    """Clé d'égalité (jetons uniques triés) — pour dédupliquer des variantes."""
    return " ".join(sorted(set(canon_lib(text).split())))


# Règles ordonnées : premier match gagne.
_RULES = [
    (1, [
        r"\bpack\b", r"\bpackage\b", r"\bprestibad\b", r"\bhorizon\b", r"\bstarter\b",
        r"\bclassic\b", r"\bpremier\b", r"\binfinite\b", r"\bdiaspora\b",
        r"eleve.{0,10}fonctionnaire", r"\bfonctionnaire\b",
        r"ouverture.{0,15}compte", r"cloture.{0,15}compte", r"fermeture.{0,15}compte",
        r"\bsuccession\b", r"compte.{0,15}courant", r"compte.{0,10}cheque",
        r"compte.{0,10}pro\b", r"compte.{0,10}special",
        r"\bflex\b.{0,10}compte", r"first.{0,5}compte", r"\bfree.{0,5}(plus|bank|compte)\b",
        # Fonctionnement & administration du compte (réduit le fourre-tout "Autres")
        r"tenue.{0,8}de.{0,5}compte", r"frais.{0,8}de.{0,5}compte", r"gestion.{0,8}de.{0,5}compte",
        r"fonctionnement.{0,10}compte", r"arrete.{0,10}compte", r"releve.{0,15}compte",
        r"releve.{0,10}identite", r"\brib\b", r"\bprocuration\b", r"domiciliation",
        r"changement.{0,18}(signature|adresse|intitule|titulaire)",
        r"attestation.{0,20}(solde|cloture|compte|redevance|propriete|irvm|non.?paiement)",
        r"\bavis.{0,10}tiers.{0,10}detenteur\b", r"\batd\b", r"saisie", r"opposition.{0,15}compte",
    ]),
    (2, [
        r"\bcarte\b", r"\bvisa\b", r"\bmastercard\b", r"\bflexicard\b",
        r"prepay", r"carte.{0,15}salaire", r"carte.{0,15}epargne",
        r"carte.{0,15}gold", r"carte.{0,15}platine",
        r"carte.{0,10}debit", r"carte.{0,10}credit",
        r"\bgab\b", r"distributeur.{0,10}automatique",
    ]),
    (3, [
        r"\bepargne\b", r"plan.{0,10}epargne", r"\bpel\b", r"\bper\b", r"\bpep\b",
        r"\bsogeprimo\b", r"\blivret\b", r"depot.{0,10}terme", r"bon.{0,10}caisse",
        r"interets?.{0,15}crediteurs", r"\bremunere", r"\bsogetudes\b",
        r"compte.{0,10}epargne",
    ]),
    (4, [
        r"\bcredit\b", r"\bpret\b", r"\bloan\b", r"facilite.{0,10}caisse",
        r"\bdecouvert\b", r"avance.{0,15}salaire", r"rappel.{0,10}plus",
        r"credit.{0,10}express", r"credit.{0,10}immo",
        r"\bcaution\b", r"\baval\b", r"\bnantissement\b", r"\bhypotheque\b",
        r"financement.{0,15}immob", r"\bmicrocredit\b", r"credit.{0,10}bail",
    ]),
    (5, [
        r"\bassurance\b", r"\byaconfort\b", r"\bquietis\b", r"\bzenith\b",
        r"soge.invest", r"plan.{0,10}retraite", r"assurance.{0,10}vie",
        r"protection.{0,10}paiement", r"multirisque", r"prevoyance",
        r"couverture.{0,15}risque", r"garantie.{0,10}infortune",
    ]),
    (6, [
        r"banque.{0,10}mobile", r"\bdigital\b", r"\bsms.{0,5}(bank|alerte)\b",
        r"\bmessalia\b", r"\binfobank\b", r"my.{0,5}bicici",
        r"retrait.{0,15}sans.{0,10}carte", r"\bqr.{0,5}code\b",
        r"virement.{0,10}mobile", r"paiement.{0,10}mobile",
        r"e.banking", r"internet.{0,10}banque",
        r"\bconnect\b", r"sgconnect", r"sogeconnect",
        # Moyens de paiement, virements, transferts & change (gros bloc opérationnel)
        r"\bvirement", r"\btransfert", r"prelevement", r"\bcheque", r"chequier", r"\beffet",
        r"encaissement", r"mise.{0,10}disposition", r"\bswift\b", r"\bsica\b", r"\bstar.?uemoa\b",
        r"\brtgs\b", r"\bchange\b", r"\bdevise", r"monetique", r"\bgim\b", r"\btthu\b",
        r"remise.{0,10}cheque", r"avis.{0,10}(de.{0,5})?(prelevement|sort)", r"\bdhl\b",
        r"transferts?.{0,15}(emis|recus|uemoa|hors)", r"mandat.{0,10}(cash|express)",
    ]),
    (7, [
        r"\bbourse\b", r"\bopcvm\b", r"valeurs?.{0,10}mobilier",
        r"marche.{0,10}primaire", r"marche.{0,10}secondaire",
        r"introduction.{0,10}bourse", r"placement.{0,10}titre",
        r"\bobligation\b", r"\bfcp\b", r"\bsicav\b",
    ]),
]


def classify_axe(libelle, contexte=""):
    """Retourne l'id d'axe (1-8) pour un libellé donné.
    Le libellé prime sur le contexte : on tente d'abord le match libellé seul,
    puis on élargit au contexte si aucune règle n'a matché (évite qu'un contexte
    "Distributeurs Automatiques" écrase un libellé "Assurance…").
    """
    lib_text = _norm(libelle or "")
    for axe_id, patterns in _RULES:
        for pat in patterns:
            if re.search(pat, lib_text):
                return axe_id
    # Fallback : libellé + contexte ensemble
    full_text = lib_text + " " + _norm(contexte or "")
    for axe_id, patterns in _RULES:
        for pat in patterns:
            if re.search(pat, full_text):
                return axe_id
    return 8


def prefilter_candidates(sgci_products, competitor_products, cutoff=0.72):
    """
    Pré-filtre Python : élimine les produits SGCI qui ont un équivalent
    évident chez un concurrent (correspondance textuelle haute).
    Retourne la liste des candidats à soumettre au LLM.

    Algorithme : SequenceMatcher via difflib.get_close_matches (O(n×m) mais
    sur des chaînes courtes, << 1 s pour 500 produits).
    """
    comp_norms = [canon_lib(p["libelle"]) for p in competitor_products]
    comp_keys  = {canon_key(p["libelle"]) for p in competitor_products}
    candidates = []
    for p in sgci_products:
        n = canon_lib(p["libelle"])
        if not n or len(n) < 3:
            continue
        # 1) égalité canonique stricte (synonymes/pluriels unifiés) → équivalent certain
        if canon_key(p["libelle"]) in comp_keys:
            continue
        # 2) proximité textuelle sur la forme canonique
        if get_close_matches(n, comp_norms, n=1, cutoff=cutoff):
            continue
        candidates.append(p)
    return candidates


def prefilter_gaps(competitor_products, sgci_products, cutoff=0.72):
    """
    Pré-filtre pour Q5 : produits d'un concurrent sans équivalent évident chez SGCI.
    """
    sgci_norms = [canon_lib(p["libelle"]) for p in sgci_products]
    sgci_keys  = {canon_key(p["libelle"]) for p in sgci_products}
    candidates = []
    for p in competitor_products:
        n = canon_lib(p["libelle"])
        if not n or len(n) < 3:
            continue
        if canon_key(p["libelle"]) in sgci_keys:
            continue
        if get_close_matches(n, sgci_norms, n=1, cutoff=cutoff):
            continue
        candidates.append(p)
    return candidates


def group_by_axe(products):
    """Groupe une liste de produits par axe. Retourne dict {axe_id: [products]}."""
    groups = {i: [] for i in range(1, 9)}
    for p in products:
        axe = classify_axe(p.get("libelle", ""), p.get("contexte", ""))
        groups[axe].append(p)
    return groups
