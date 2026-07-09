"""
retriever.py — Recherche sémantique PostgreSQL + pgvector
=========================================================
Remplace ChromaDB par requêtes SQL directes sur intelligence_bancaire.
Logique de routing inchangée (detect_*, search_auto, format_context).
Embedding : sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (768 dims, local).
"""

import re
import sys
import os
from pathlib import Path
from collections import defaultdict
import importlib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
config = importlib.import_module("config")

BANQUE_ALIASES          = config.BANQUE_ALIASES
BANQUES_OFFICIELLES     = config.BANQUES_OFFICIELLES
BANQUES_CONSOLIDEES     = config.BANQUES_CONSOLIDEES
ETATS_FINANCIERS_ANNEES = config.ETATS_FINANCIERS_ANNEES
SHOW_QUERY_DEBUG        = config.SHOW_QUERY_DEBUG

# ═══════════════════════════════════════════════════════════
#  PGVECTORSTORE — REMPLACE CHROMADB
# ═══════════════════════════════════════════════════════════

class PGVectorStore:
    """
    Wrapper PostgreSQL + pgvector.
    Joue le rôle du vectorstore ChromaDB dans toute la chaîne RAG.
    """
    _model = None  # singleton — chargé une seule fois

    def __init__(self):
        self.db_params = config.DB_PARAMS

    def get_conn(self):
        import psycopg2
        return psycopg2.connect(**self.db_params)

    def embed_query(self, text: str) -> list:
        """Encode une question → vecteur 768 dims (normalisé)."""
        if PGVectorStore._model is None:
            print(f"  [EMBED] Chargement {config.EMBEDDING_MODEL}...", end=" ", flush=True)
            from sentence_transformers import SentenceTransformer
            PGVectorStore._model = SentenceTransformer(config.EMBEDDING_MODEL)
            print("OK")
        vec = PGVectorStore._model.encode([text], normalize_embeddings=True)[0]
        return vec.tolist()

    def vec_literal(self, text: str) -> str:
        """Retourne la représentation SQL littérale du vecteur pour pgvector."""
        v = self.embed_query(text)
        return "[" + ",".join(f"{x:.8f}" for x in v) + "]"


def init_retriever() -> PGVectorStore:
    """Initialise le retriever PostgreSQL. Appelé depuis chain.py."""
    store = PGVectorStore()
    try:
        with store.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM cb_tarifs WHERE embedding IS NOT NULL")
                n_cb = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM ef_indicateurs WHERE embedding IS NOT NULL")
                n_ef = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM regl_documents WHERE embedding IS NOT NULL")
                n_regl = cur.fetchone()[0]
        print(f"[RETRIEVER OK] cb_tarifs={n_cb} | ef_indicateurs={n_ef} | regl_documents={n_regl} embeddings")
    except Exception as e:
        print(f"[RETRIEVER ERREUR] Connexion PostgreSQL : {e}")
    return store


# ═══════════════════════════════════════════════════════════
#  HELPERS — CONVERSION LIGNE SQL → CHUNK DICT
# ═══════════════════════════════════════════════════════════

def _chunk_cb(row) -> dict:
    """Convertit une ligne cb_tarifs en chunk RAG."""
    banque   = row[0]
    annee    = row[1]
    semestre = row[2]
    segment  = row[3] or ""
    contexte = row[4] or ""
    libelle  = row[5] or ""
    valeur   = row[6] or ""
    score    = float(row[7]) if len(row) > 7 and row[7] is not None else 1.0

    texte = f"{contexte} > {libelle} : {valeur}".strip(" >:")

    return {
        "texte"   : texte,
        "score"   : score,
        "metadata": {
            "banque"          : banque,
            "banque_officiel" : banque,
            "annee"           : annee,
            "semestre"        : semestre,
            "cible_clientele" : segment.lower(),
            "type_document"   : "conditions_banque",
            "periode_label"   : f"{semestre} {annee}",
            "source"          : f"{banque}_{annee}_{semestre}",
        },
        "source"  : f"{banque}_{annee}_{semestre}",
        "banque"  : banque,
        "periode" : f"{semestre} {annee}",
        "type_doc": "conditions_banque",
    }


def _chunk_ef(row) -> dict:
    """Convertit une ligne ef_indicateurs en chunk RAG."""
    banque       = row[0]
    libelle      = row[1] or ""
    valeur_brute = row[2] or ""
    unite        = row[3] or ""
    annee_donnee = row[4] or 0
    is_primary   = row[5] if len(row) > 5 else True
    score        = float(row[6]) if len(row) > 6 and row[6] is not None else 1.0

    texte = f"{libelle} : {valeur_brute} {unite}".strip()

    return {
        "texte"   : texte,
        "score"   : score,
        "metadata": {
            "banque"          : banque,
            "banque_officiel" : banque,
            "annee"           : annee_donnee,
            "type_document"   : "etats_financiers",
            "est_consolide"   : banque in BANQUES_CONSOLIDEES,
            "periode_label"   : str(annee_donnee) if annee_donnee else "",
            "is_primary"      : is_primary,
            "cible_clientele" : "",
            "semestre"        : "",
        },
        "source"  : f"EF_{banque}",
        "banque"  : banque,
        "periode" : str(annee_donnee),
        "type_doc": "etats_financiers",
    }


def _chunk_regl(row) -> dict:
    """Convertit une ligne regl_documents en chunk RAG."""
    fichier = row[0] or ""
    contenu = row[1] or ""
    score   = float(row[2]) if len(row) > 2 and row[2] is not None else 1.0

    return {
        "texte"   : contenu,
        "score"   : score,
        "metadata": {
            "banque"          : "",
            "banque_officiel" : "",
            "type_document"   : "reglementation",
            "source"          : fichier,
            "periode_label"   : "",
            "cible_clientele" : "",
            "semestre"        : "",
            "annee"           : "",
        },
        "source"  : fichier,
        "banque"  : "",
        "periode" : "",
        "type_doc": "reglementation",
    }


# ═══════════════════════════════════════════════════════════
#  FILTRES SQL
# ═══════════════════════════════════════════════════════════

def build_filters(banque=None, annee=None, type_doc=None, semestre=None, cible=None) -> dict:
    """Retourne un dict de filtres — transmis à search()."""
    f = {}
    if banque:   f["banque"]   = banque
    if annee:    f["annee"]    = annee
    if type_doc: f["type_doc"] = type_doc
    if semestre: f["semestre"] = semestre
    if cible:    f["cible"]    = cible
    return f or None


def _sql_where_cb(banque=None, annee=None, semestre=None, cible=None):
    """Génère (clause WHERE, params) pour cb_tarifs."""
    parts, params = [], []
    if banque:
        parts.append("banque = %s"); params.append(banque)
    if annee:
        parts.append("annee = %s"); params.append(annee)
    if semestre:
        parts.append("semestre = %s"); params.append(semestre)
    if cible:
        parts.append("LOWER(segment) = LOWER(%s)"); params.append(cible)
    where = ("WHERE " + " AND ".join(parts)) if parts else ""
    return where, params


def _sql_where_ef(banque=None, annee=None, is_primary_only=True):
    """Génère (clause WHERE, params) pour ef_indicateurs."""
    parts, params = [], []
    if banque:
        parts.append("banque = %s"); params.append(banque)
    if annee:
        parts.append("annee_donnee = %s"); params.append(annee)
    if is_primary_only:
        parts.append("is_primary = TRUE")
    where = ("WHERE " + " AND ".join(parts)) if parts else ""
    return where, params


# ═══════════════════════════════════════════════════════════
#  RECHERCHE SÉMANTIQUE — pgvector
# ═══════════════════════════════════════════════════════════

def search(vectorstore: PGVectorStore, question: str, k: int = None, filters: dict = None) -> list:
    """
    Recherche sémantique par similarité cosine (pgvector <=>).
    Dispatche sur cb_tarifs, ef_indicateurs ou regl_documents selon type_doc.
    """
    if k is None:
        k = config.RETRIEVER_K

    f        = filters or {}
    banque   = f.get("banque")
    annee    = f.get("annee")
    type_doc = f.get("type_doc") or f.get("type_document")
    semestre = f.get("semestre")
    cible    = f.get("cible")
    threshold = config.SIMILARITY_THRESHOLD

    vec_lit = vectorstore.vec_literal(question)
    chunks  = []

    try:
        with vectorstore.get_conn() as conn:
            with conn.cursor() as cur:

                if type_doc == "etats_financiers":
                    where, params = _sql_where_ef(banque=banque, annee=annee, is_primary_only=bool(annee))
                    sql = f"""
                        SELECT banque, libelle, valeur_brute, unite, annee_donnee, is_primary,
                               1 - (embedding <=> %s::vector) AS score
                        FROM ef_indicateurs
                        {where}
                          {"AND" if where else "WHERE"} embedding IS NOT NULL
                          AND 1 - (embedding <=> %s::vector) >= {threshold}
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                    """
                    cur.execute(sql, [vec_lit] + params + [vec_lit, vec_lit, k])
                    chunks = [_chunk_ef(r) for r in cur.fetchall()]

                elif type_doc == "reglementation":
                    sql = f"""
                        SELECT fichier, contenu,
                               1 - (embedding <=> %s::vector) AS score
                        FROM regl_documents
                        WHERE embedding IS NOT NULL
                          AND 1 - (embedding <=> %s::vector) >= {threshold}
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                    """
                    cur.execute(sql, [vec_lit, vec_lit, vec_lit, k])
                    chunks = [_chunk_regl(r) for r in cur.fetchall()]

                else:
                    # conditions_banque (défaut)
                    where, params = _sql_where_cb(banque=banque, annee=annee, semestre=semestre, cible=cible)
                    sql = f"""
                        SELECT banque, annee, semestre, segment, contexte, libelle, valeur_brute,
                               1 - (embedding <=> %s::vector) AS score
                        FROM cb_tarifs
                        {where}
                          {"AND" if where else "WHERE"} embedding IS NOT NULL
                          AND 1 - (embedding <=> %s::vector) >= {threshold}
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                    """
                    cur.execute(sql, [vec_lit] + params + [vec_lit, vec_lit, k])
                    chunks = [_chunk_cb(r) for r in cur.fetchall()]

    except Exception as e:
        print(f"  [SEARCH ERREUR] {e}")

    return chunks


# ═══════════════════════════════════════════════════════════
#  RECHERCHE EXHAUSTIVE — SQL SELECT sans vecteur
# ═══════════════════════════════════════════════════════════

def _get_exhaustif_cb(vectorstore: PGVectorStore, banque=None, annee=None, semestre=None, cible=None) -> list:
    """
    Récupère TOUTES les lignes CB correspondant aux filtres.
    Fallback temporel : si 0 résultat pour une période, cherche la période la plus proche
    et ajoute une note de transparence dans les chunks retournés.
    """
    where, params = _sql_where_cb(banque=banque, annee=annee, semestre=semestre, cible=cible)
    sql = f"""
        SELECT banque, annee, semestre, segment, contexte, libelle, valeur_brute
        FROM cb_tarifs
        {where}
        ORDER BY banque, annee, semestre, segment, section
    """
    try:
        with vectorstore.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                if rows:
                    return [_chunk_cb(r) for r in rows]

                # Fallback temporel : données absentes → cherche la période la plus proche
                if annee and banque:
                    cur.execute("""
                        SELECT DISTINCT annee, semestre FROM cb_tarifs
                        WHERE banque=%s AND LOWER(segment)=LOWER(%s)
                        ORDER BY annee DESC, semestre DESC LIMIT 1
                    """, [banque, cible or "%"])
                    periode = cur.fetchone()
                    if periode:
                        annee_fb, sem_fb = periode
                        print(f"  [FALLBACK] {banque} {annee} {semestre} absent → utilise {annee_fb} {sem_fb}")
                        where_fb, params_fb = _sql_where_cb(banque=banque, annee=annee_fb,
                                                             semestre=sem_fb, cible=cible)
                        cur.execute(f"""
                            SELECT banque, annee, semestre, segment, contexte, libelle, valeur_brute
                            FROM cb_tarifs {where_fb}
                            ORDER BY banque, annee, semestre, segment, section
                        """, params_fb)
                        fb_rows = cur.fetchall()
                        if fb_rows:
                            chunks = [_chunk_cb(r) for r in fb_rows]
                            # Ajouter note de transparence sur le fallback
                            note = {
                                "texte"   : f"[NOTE TRANSPARENCE] Données pour {annee} {semestre} non disponibles. "
                                            f"Informations ci-dessous issues de {annee_fb} {sem_fb} — à vérifier en cas de changement tarifaire.",
                                "score"   : 1.0,
                                "metadata": {"banque": banque, "annee": annee_fb, "semestre": sem_fb,
                                             "type_document": "conditions_banque",
                                             "cible_clientele": (cible or "").lower(),
                                             "periode_label": f"{sem_fb} {annee_fb}"},
                                "source"  : f"{banque}_{annee_fb}_{sem_fb}_FALLBACK",
                                "banque"  : banque,
                                "periode" : f"{sem_fb} {annee_fb}",
                                "type_doc": "conditions_banque",
                            }
                            return [note] + chunks
                return []
    except Exception as e:
        print(f"  [EXHAUSTIF CB ERREUR] {e}")
        return []


# Synonymes bancaires ivoiriens — savoir domaine compact (libelle ↔ contexte)
# "convenance de comptes" = "tenue de compte" chez SIB/BICICI
_SYNONYMES_SERVICE = {
    "tenue"      : ["tenue", "convenance", "relevé", "frais fixe"],  # SGCI entr. = "relevés/mois"
    "virement"   : ["virement", "transfert"],
    "retrait"    : ["retrait", "espece"],
    "carte"      : ["carte"],
    "chequier"   : ["chequier", "chèquier", "cheque"],
    "domiciliation": ["domiciliation"],
    "decouvert"  : ["decouvert", "découvert", "agios"],
}


def _extraire_terme_service(question: str) -> str:
    """
    Extrait le terme de service principal de la question (NLP minimal).
    'frais de tenue de compte' → 'tenue'
    'frais de virement' → 'virement'
    """
    import re
    q = question.lower()
    patterns = [
        r"(?:frais|tarif|co[uû]t|commission|montant)\s+(?:de|du|des|d[''])\s+(\w+)",
        r"\b(virement|retrait|carte|chequier|chèquier|domiciliation|découvert|agios?)\b",
    ]
    for pat in patterns:
        m = re.search(pat, q)
        if m:
            return m.group(1)
    return None


def search_cb_keyword(vectorstore: PGVectorStore, termes: list,
                      banque=None, annee=None, semestre=None, cible=None) -> list:
    """
    Recherche SQL dans libelle ET contexte avec expansion synonymique.
    Cherche UNIQUEMENT les termes de service (pas les termes contextuels).
    Ex: ['tenue'] → cherche 'tenue' + 'convenance' dans libelle OU contexte
    """
    if not termes:
        return []

    # Expansion synonymique pour chaque terme
    termes_etendus = []
    for t in termes:
        for cle, synonymes in _SYNONYMES_SERVICE.items():
            if t.lower() == cle or t.lower() in synonymes:
                termes_etendus.extend(synonymes)
                break
        else:
            termes_etendus.append(t.lower())
    termes_etendus = list(dict.fromkeys(termes_etendus))  # dédoublonnage

    where_parts, params = [], []
    if banque:
        where_parts.append("banque = %s"); params.append(banque)
    if annee:
        where_parts.append("annee = %s"); params.append(annee)
    if semestre:
        where_parts.append("semestre = %s"); params.append(semestre)
    if cible:
        where_parts.append("LOWER(segment) = LOWER(%s)"); params.append(cible)

    # libelle OU contexte contient l'un des termes étendus
    kw_conds = " OR ".join(
        [f"(LOWER(libelle) LIKE %s OR LOWER(contexte) LIKE %s)" for _ in termes_etendus]
    )
    for t in termes_etendus:
        params.extend([f"%{t}%", f"%{t}%"])

    all_conds = " AND ".join(where_parts) if where_parts else "TRUE"
    sql = f"""
        SELECT banque, annee, semestre, segment, contexte, libelle, valeur_brute
        FROM cb_tarifs
        WHERE ({all_conds}) AND ({kw_conds})
        ORDER BY banque, annee, semestre, segment, section
    """
    try:
        with vectorstore.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                if rows:
                    print(f"  [KEYWORD+synonymes] {len(rows)} lignes ({'+'.join(termes_etendus)})")
                return [_chunk_cb(r) for r in rows]
    except Exception as e:
        print(f"  [KEYWORD ERREUR] {e}")
        return []


def _get_exhaustif_ef(vectorstore: PGVectorStore, banque=None, annee=None) -> list:
    """Récupère TOUTES les lignes EF (is_primary=TRUE quand annee précisée)."""
    primary_only = bool(annee)
    where, params = _sql_where_ef(banque=banque, annee=annee, is_primary_only=primary_only)
    sql = f"""
        SELECT banque, libelle, valeur_brute, unite, annee_donnee, is_primary
        FROM ef_indicateurs
        {where}
        ORDER BY banque, annee_donnee, libelle
    """
    try:
        with vectorstore.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [_chunk_ef(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"  [EXHAUSTIF EF ERREUR] {e}")
        return []


def _get_exhaustif_regl(vectorstore: PGVectorStore) -> list:
    """Récupère tous les chunks réglementaires."""
    sql = "SELECT fichier, contenu FROM regl_documents ORDER BY fichier, chunk_index"
    try:
        with vectorstore.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [_chunk_regl(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"  [EXHAUSTIF REGL ERREUR] {e}")
        return []


def get_semestres_disponibles(vectorstore: PGVectorStore, annee: int, type_doc: str = "conditions_banque") -> list:
    """Détecte dynamiquement les semestres disponibles dans la BD pour une année."""
    if type_doc != "conditions_banque":
        return []
    try:
        with vectorstore.get_conn() as conn:
            with conn.cursor() as cur:
                sql = "SELECT DISTINCT semestre FROM cb_tarifs WHERE annee = %s ORDER BY semestre"
                cur.execute(sql, [annee])
                rows = [r[0] for r in cur.fetchall() if r[0]]
                return rows or ["S1"]
    except Exception:
        return ["S1", "S2"]


# ═══════════════════════════════════════════════════════════
#  DÉTECTION DU CONTEXTE DANS LA QUESTION
# ═══════════════════════════════════════════════════════════

def detect_banque(question: str):
    banques = detect_banques(question)
    return banques[0] if banques else None


def detect_banques(question: str) -> list:
    q = question.lower()
    found, seen = [], set()
    for alias, code in BANQUE_ALIASES.items():
        if alias in q and code not in seen:
            found.append(code)
            seen.add(code)
    return found


def detect_annee(question: str):
    match = re.search(r"\b(202[0-9]|2030)\b", question)
    return int(match.group(1)) if match else None


def detect_annees(question: str) -> list:
    annees_brutes = [int(m) for m in re.findall(r"\b(202[0-9]|2030)\b", question)]
    q = question.lower()
    if len(annees_brutes) >= 2:
        if (re.search(r"entre\s+202[0-9]\s+et\s+202[0-9]", q)
                or re.search(r"de\s+202[0-9]\s+[àa]\s+202[0-9]", q)):
            a_min, a_max = min(annees_brutes), max(annees_brutes)
            if a_max - a_min <= 10:
                return list(range(a_min, a_max + 1))
    return annees_brutes


def is_evolution(question: str) -> bool:
    q = question.lower()
    mots = [
        "evolution", "évolué", "evolue", "évoluer",
        "entre", "de 2024 à", "de 2025 à", "de 2023 à",
        "comparaison annuelle", "par rapport à", "par rapport a",
        "avant", "après", "apres", "progression", "hausse", "baisse",
        "augmentation", "diminution", "changement",
    ]
    return any(m in q for m in mots)


def detect_types_doc(question: str) -> list:
    q = question.lower()
    types = []
    if any(m in q for m in config.MOTS_REGLEMENTATION):
        types.append("reglementation")
    if any(m in q for m in config.MOTS_EF):
        types.append("etats_financiers")
    if any(m in q for m in config.MOTS_CONDITIONS):
        types.append("conditions_banque")
    return types


def detect_type_doc(question: str):
    types = detect_types_doc(question)
    if not types:
        return None
    for prio in ["reglementation", "etats_financiers", "conditions_banque"]:
        if prio in types:
            return prio
    return types[0]


def detect_semestre(question: str):
    q = question.upper()
    if "S1" in q or "PREMIER SEMESTRE" in q or "1ER SEMESTRE" in q:
        return "S1"
    if "S2" in q or "DEUXIÈME SEMESTRE" in q or "2EME SEMESTRE" in q:
        return "S2"
    return None


def detect_cible(question: str):
    q = question.lower()
    if any(m in q for m in ["entreprise", "professionnel", "société", "corporate"]):
        return "entreprises"
    if any(m in q for m in ["particulier", "individuel", "personne physique", "retail"]):
        return "particuliers"
    return None


def is_comparaison(question: str) -> bool:
    q = question.lower()
    mots = [
        "comparer", "comparaison", "toutes les banques",
        "toutes les", "l'ensemble", "chaque banque",
        "banques en", "classement", "quelle banque",
        "les banques", "benchmark", "panorama",
        "plus cher", "moins cher", "plus chere", "moins chere",
        "la moins", "la plus", "meilleure banque", "meilleur taux",
        "entre les banques", "toutes banques",
    ]
    return any(m in q for m in mots)


def is_recommandation_ou_analyse(question: str) -> bool:
    q = question.lower()
    mots = [
        "recommande", "recommandation", "conseil", "conseille",
        "choisir", "dois-je", "devrais", "faut-il choisir",
        "meilleure option", "meilleur choix", "meilleure banque pour",
        "swot", "matrice", "analyse strateg",
        "point fort", "point faible", "opportunite", "menace",
        "avantage concurrentiel", "positionnement",
        "perspective", "prospective", "prevision", "tendance future",
        "ton avis", "votre avis", "que penses-tu",
        "est-ce conforme", "est autorise", "est interdit",
        "est reglementaire", "cadre legal", "legalement",
        # Recommandations implicites (PME, choix de banque)
        "avantageuse", "avantag", "la plus adapt", "pour une pme",
        "pour mon entreprise", "pour une startup", "quelle banque choisir",
        "meilleure banque", "la mieux adapt",
    ]
    return any(m in q for m in mots)


def check_disponibilite_ef(banque, annee):
    if not banque or not annee:
        return None
    annees_dispo = ETATS_FINANCIERS_ANNEES.get(banque)
    if annees_dispo is None:
        return None
    if annee not in annees_dispo:
        derniere = max(annees_dispo)
        premiere = min(annees_dispo)
        return (
            f"Les données des états financiers de {banque} pour {annee} ne sont pas disponibles.\n"
            f"Période couverte pour {banque} : {premiere} – {derniere}.\n"
            f"Dernière année disponible : {derniere}."
        )
    return None


def banques_disponibles_ef(annee: int):
    dispo, indispo = [], []
    for banque, annees in ETATS_FINANCIERS_ANNEES.items():
        (dispo if annee in annees else indispo).append(banque)
    return dispo, indispo


# ═══════════════════════════════════════════════════════════
#  RECHERCHE PAR BANQUE PRÉCISE — EXHAUSTIF
# ═══════════════════════════════════════════════════════════

def search_banque_specifique(vectorstore, banque, annee, type_doc, semestre, cible, question) -> list:
    """
    Récupération exhaustive pour une banque précise.
    Utilise SQL SELECT direct (pas de limite top-k, sauf si trop volumineux).
    """
    if type_doc == "etats_financiers":
        annee_q = None if banque in BANQUES_CONSOLIDEES else annee
        chunks  = _get_exhaustif_ef(vectorstore, banque=banque, annee=annee_q)
    elif type_doc == "reglementation":
        chunks = _get_exhaustif_regl(vectorstore)
    else:
        chunks = _get_exhaustif_cb(vectorstore, banque=banque, annee=annee, semestre=semestre, cible=cible)

    if len(chunks) > config.MAX_CHUNKS_BANQUE:
        print(f"  [{banque}] {len(chunks)} chunks > {config.MAX_CHUNKS_BANQUE} — sémantique k=100")
        filters = build_filters(banque=banque, annee=annee, type_doc=type_doc, semestre=semestre, cible=cible)
        return search(vectorstore, question, k=100, filters=filters)

    print(f"  Recherche ciblée {banque} : {len(chunks)} chunks (exhaustif)")
    return chunks


# ═══════════════════════════════════════════════════════════
#  COMPARAISON TOUTES BANQUES — EXHAUSTIF
# ═══════════════════════════════════════════════════════════

CIBLES = ["entreprises", "particuliers"]


def search_toutes_banques(vectorstore, question: str) -> list:
    """
    Récupère les données de TOUTES les banques de façon exhaustive.
    CB : boucle banques × cibles × semestres.
    EF / REGL : boucle banques.
    """
    annee    = detect_annee(question)
    type_doc = detect_type_doc(question) or "conditions_banque"
    cible_det = detect_cible(question)
    tous_chunks = []

    if type_doc == "conditions_banque":
        semestres        = get_semestres_disponibles(vectorstore, annee, type_doc) if annee else ["S1", "S2"]
        cibles_a_chercher = [cible_det] if cible_det else CIBLES
        print(f"  [COMPARAISON EXHAUSTIVE CB] {len(BANQUES_OFFICIELLES)} banques x {len(cibles_a_chercher)} cibles")
        print(f"     Annee:{annee or 'toutes'} | Semestres:{semestres} | Cible:{cible_det or 'toutes'}")

        for banque in BANQUES_OFFICIELLES:
            for cible in cibles_a_chercher:
                for semestre in semestres:
                    chunks = _get_exhaustif_cb(vectorstore, banque=banque, annee=annee,
                                               semestre=semestre, cible=cible)
                    if chunks:
                        tous_chunks.extend(chunks)
                        print(f"     OK {banque:<10} {cible:<15} {semestre} : {len(chunks)} lignes")
                    else:
                        print(f"     -- {banque:<10} {cible:<15} {semestre} : vide")

    elif type_doc == "etats_financiers":
        print(f"  [COMPARAISON EXHAUSTIVE EF] {len(BANQUES_OFFICIELLES)} banques | Annee:{annee or 'toutes'}")
        for banque in BANQUES_OFFICIELLES:
            annee_q = None if banque in BANQUES_CONSOLIDEES else annee
            chunks  = _get_exhaustif_ef(vectorstore, banque=banque, annee=annee_q)
            if chunks:
                tous_chunks.extend(chunks)
                print(f"     OK {banque:<10} : {len(chunks)} indicateurs")
            else:
                print(f"     -- {banque:<10} : vide")

    else:  # reglementation
        tous_chunks = _get_exhaustif_regl(vectorstore)
        print(f"  [REGL GLOBALE] {len(tous_chunks)} chunks")

    print(f"  Total : {len(tous_chunks)} chunks (exhaustif)")

    if len(tous_chunks) > config.MAX_CHUNKS_GLOBAL:
        print(f"  {len(tous_chunks)} > {config.MAX_CHUNKS_GLOBAL} — bascule sémantique k=30/banque")
        return _search_semantique_par_banque(vectorstore, question,
                                             annee=annee, type_doc=type_doc,
                                             cible=cible_det, k_par_banque=30)
    return tous_chunks


def _enrichir_requete(question: str) -> str:
    q = question.lower()
    if any(m in q for m in ["virement", "transfert"]):
        return question + " virement interne STAR SICA frais montant"
    if any(m in q for m in ["chere", "cher", "chère", "economique"]):
        return question + " frais tenue compte virement carte retrait commission"
    if any(m in q for m in ["carte", "visa", "mastercard"]):
        return question + " carte bancaire visa classic gold platinum cotisation"
    if any(m in q for m in ["tenue de compte"]):
        return question + " tenue compte frais mensuel trimestriel"
    if any(m in q for m in ["retrait", "dab"]):
        return question + " retrait especes DAB guichet frais"
    if any(m in q for m in ["resultat", "rentable", "pnb", "bilan"]):
        return question + " résultat net bénéfice PNB frais généraux"
    return question


def _search_semantique_par_banque(vectorstore, question, annee=None, type_doc=None,
                                   cible=None, semestre=None, k_par_banque=4) -> list:
    """Fallback sémantique : k chunks par banque pour les comparaisons trop volumineuses."""
    requete = _enrichir_requete(question)
    print(f"  [SEMANTIQUE PAR BANQUE] {len(BANQUES_OFFICIELLES)} banques x {k_par_banque} chunks/banque")
    tous_chunks = []

    for banque in BANQUES_OFFICIELLES:
        filters = build_filters(banque=banque, annee=annee, type_doc=type_doc,
                                semestre=semestre, cible=cible)
        bank_chunks = search(vectorstore, requete, k=k_par_banque, filters=filters)
        if bank_chunks:
            tous_chunks.extend(bank_chunks)
            print(f"    {banque:<10} : {len(bank_chunks)} chunks")
        else:
            filters_lax = build_filters(banque=banque, annee=annee, type_doc=type_doc)
            bank_chunks = search(vectorstore, requete, k=k_par_banque, filters=filters_lax)
            tous_chunks.extend(bank_chunks)
            print(f"    {banque:<10} : {len(bank_chunks)} chunks (filtre assoupli)")

    print(f"  Total : {len(tous_chunks)} chunks")
    return tous_chunks


def search_reglementation(vectorstore, question: str, k: int = 4) -> list:
    """Récupère les chunks réglementaires les plus pertinents."""
    filters = build_filters(type_doc="reglementation")
    chunks  = search(vectorstore, question, k=k, filters=filters)
    return [c for c in chunks if c["score"] >= 0.20]


# ═══════════════════════════════════════════════════════════
#  ROUTEUR PRINCIPAL — search_auto
# ═══════════════════════════════════════════════════════════

def search_auto(vectorstore, question: str, force_type_doc: str = None,
                force_type_docs: list = None) -> list:
    """
    Stratégie de recherche adaptée automatiquement au type de question.
    Même logique que la version ChromaDB, backends PostgreSQL.
    """
    # Multi-label : appel récursif par domaine puis fusion
    if force_type_docs and len(force_type_docs) > 1:
        tous, vus = [], set()
        for td in force_type_docs:
            for c in search_auto(vectorstore, question, force_type_doc=td):
                key = c.get("texte", "")[:80]
                if key not in vus:
                    vus.add(key)
                    tous.append(c)
        print(f"  [Multi-domaines] {force_type_docs} → {len(tous)} chunks fusionnés")
        return tous

    if force_type_docs and len(force_type_docs) == 1:
        force_type_doc = force_type_docs[0]

    banques  = detect_banques(question)
    banque   = banques[0] if len(banques) == 1 else None
    annee    = detect_annee(question)
    annees   = detect_annees(question)
    type_doc = force_type_doc or detect_type_doc(question)
    semestre = detect_semestre(question)
    cible    = detect_cible(question)

    # ── Cas 1 : évolution temporelle (plusieurs années explicites) ──
    if banque and is_evolution(question) and len(annees) >= 2:
        if banque in BANQUES_CONSOLIDEES and type_doc == "etats_financiers":
            print(f"  [EVOLUTION CONSOLIDEE {banque}] exhaustif toutes années")
            chunks = _get_exhaustif_ef(vectorstore, banque=banque, annee=None)
            print(f"  Total : {len(chunks)} chunks")
            return chunks

        MAX_EVO = 900
        # Estimation volume avant lancement
        total_prevu = 0
        for a in annees:
            if type_doc == "etats_financiers":
                c = _get_exhaustif_ef(vectorstore, banque=banque, annee=a)
            else:
                c = _get_exhaustif_cb(vectorstore, banque=banque, annee=a,
                                      semestre=semestre, cible=cible)
            total_prevu += len(c)

        if total_prevu > MAX_EVO:
            print(f"  [EVOLUTION] {total_prevu} chunks prévus > {MAX_EVO} — sémantique k=150/an")
            chunks = []
            requete_enrichie = _enrichir_requete(question)
            for a in annees:
                filters_an = build_filters(banque=banque, annee=a, type_doc=type_doc,
                                           semestre=semestre, cible=cible)
                an_chunks = search(vectorstore, requete_enrichie, k=150, filters=filters_an)
                chunks.extend(an_chunks)
                print(f"  → {a} : {len(an_chunks)} chunks (sémantique k=150)")
            return chunks

        chunks = []
        for a in annees:
            if type_doc == "etats_financiers":
                year_chunks = _get_exhaustif_ef(vectorstore, banque=banque, annee=a)
            else:
                year_chunks = _get_exhaustif_cb(vectorstore, banque=banque, annee=a,
                                                semestre=semestre, cible=cible)
            chunks.extend(year_chunks)
            print(f"  → {a} : {len(year_chunks)} chunks")
        print(f"  Total : {len(chunks)} chunks")
        return chunks

    # ── Cas 2a : 2+ banques explicitement nommées ──
    if len(banques) >= 2:
        print(f"  [2 BANQUES EXPLICITES] {banques}")
        chunks = []
        for b in banques:
            annee_b = None if (b in BANQUES_CONSOLIDEES and type_doc == "etats_financiers") else annee
            b_chunks = search_banque_specifique(vectorstore, b, annee=annee_b,
                                                type_doc=type_doc, semestre=semestre,
                                                cible=cible, question=question)
            chunks.extend(b_chunks)
            print(f"    {b:<10} : {len(b_chunks)} chunks")
        print(f"  Total : {len(chunks)} chunks")
        return chunks

    # ── Cas 2b : recommandation/analyse → sémantique ciblé par banque ──
    # Évite de charger 30k chunks pour une question de conseil
    if is_recommandation_ou_analyse(question) and not banques:
        cible_rec = cible
        q_low = question.lower()
        if any(m in q_low for m in ["pme", "entreprise", "corporate", "exportat", "import"]):
            cible_rec = "entreprises"
        print(f"  [RECOMMANDATION] sémantique k=5/banque | cible={cible_rec or 'toutes'}")
        return _search_semantique_par_banque(vectorstore, question,
                                             annee=annee, type_doc=type_doc,
                                             cible=cible_rec, k_par_banque=5)

    # ── Cas 2c : comparaison toutes banques (0 banque nommée) ──
    if is_comparaison(question) and not banques:
        if type_doc == "reglementation":
            chunks = _get_exhaustif_regl(vectorstore)
            print(f"  [REGL GLOBALE] {len(chunks)} chunks")
            return chunks
        return search_toutes_banques(vectorstore, question)

    # ── Cas 3 : banque précise ──
    if banque:
        annee_search = None if (banque in BANQUES_CONSOLIDEES and type_doc == "etats_financiers") else annee

        if type_doc != "etats_financiers":
            # Approche NLP hybride :
            # 1. Sémantique k=80 (embedding capture les synonymes en contexte)
            # 2. SQL ciblé sur le TERME DE SERVICE extrait de la question
            # 3. Fallback temporel si service absent pour la période demandée
            # 4. Union dédupliquée → exhaustivité maximale
            filters_prec = build_filters(banque=banque, annee=annee_search,
                                         semestre=semestre, cible=cible,
                                         type_doc="conditions_banque")
            semantic_chunks = search(vectorstore, question, k=80, filters=filters_prec)

            # Extraction du terme de service principal (NLP — pas de liste hardcodée)
            terme_service = _extraire_terme_service(question)
            keyword_chunks = []
            if terme_service:
                keyword_chunks = search_cb_keyword(
                    vectorstore, [terme_service],
                    banque=banque, annee=annee_search, semestre=semestre, cible=cible
                )

                # Fallback temporel service-niveau :
                # Filtre anti-faux-positifs : exclure les chunks où le terme est dans
                # "tenue de dossier", "tenue de portefeuille" etc. (pas "tenue de compte")
                SERVICE_SUFFIXES_EXCLUS = ["dossier", "portefeuille", "titre"]
                keyword_vrais = []
                for c in keyword_chunks:
                    txt = c["texte"].lower()
                    if terme_service not in txt:
                        continue  # chunk sans le terme → pas pertinent
                    pos = txt.find(terme_service)
                    apres = txt[pos:pos + 20]
                    if any(suf in apres for suf in SERVICE_SUFFIXES_EXCLUS):
                        continue  # tenue de DOSSIER / PORTEFEUILLE → faux positif
                    keyword_vrais.append(c)

                # Si 0 vrais résultats → chercher période la plus proche (fallback temporel)
                if len(keyword_vrais) == 0 and annee_search:
                    fallback_trouve = False
                    for annee_fb in sorted(range(2024, 2027), key=lambda x: abs(x - annee_search)):
                        if annee_fb == annee_search or fallback_trouve:
                            continue
                        for sem_fb in ["S2", "S1"]:  # S2 plus récent en priorité
                            fb = search_cb_keyword(
                                vectorstore, [terme_service],
                                banque=banque, annee=annee_fb, semestre=sem_fb, cible=cible
                            )
                            # Vérifier que les résultats sont vrais (pas dossier/portefeuille)
                            fb_vrais = [c for c in fb if not any(
                                terme_service in c["texte"].lower() and suf in
                                c["texte"].lower()[c["texte"].lower().find(terme_service):][:20]
                                for suf in SERVICE_SUFFIXES_EXCLUS
                            )]
                            if fb_vrais:
                                sem_orig = semestre or "S1/S2"
                                print(f"  [SERVICE FALLBACK] '{terme_service}' absent "
                                      f"{annee_search} {sem_orig} → utilise {annee_fb} {sem_fb}")
                                note_chunk = {
                                    "texte"   : (f"[NOTE TRANSPARENCE] Données '{terme_service}' non "
                                                 f"disponibles pour {annee_search} {sem_orig}. "
                                                 f"Valeurs ci-dessous issues de {annee_fb} {sem_fb} "
                                                 f"(période la plus proche disponible — à vérifier avant décision)."),
                                    "score"   : 1.0,
                                    "metadata": {"banque": banque, "annee": annee_fb, "semestre": sem_fb,
                                                 "type_document": "conditions_banque",
                                                 "cible_clientele": (cible or "").lower(),
                                                 "periode_label": f"APPROX {sem_fb} {annee_fb}"},
                                    "source"  : f"{banque}_FALLBACK_{annee_fb}_{sem_fb}",
                                    "banque"  : banque, "periode": f"{sem_fb} {annee_fb}",
                                    "type_doc": "conditions_banque",
                                }
                                keyword_chunks = [note_chunk] + fb_vrais
                                fallback_trouve = True
                                break

            # Union dédupliquée (sémantique en priorité)
            seen, chunks = set(), []
            for c in semantic_chunks + keyword_chunks:
                key = c["texte"][:100]
                if key not in seen:
                    seen.add(key)
                    chunks.append(c)

            if chunks:
                label = f"sémantique k=80" + (f" + keyword '{terme_service}'" if terme_service else "")
                print(f"  Total : {len(chunks)} chunks ({label})")
                return chunks

        # EF ou fallback
        chunks = search_banque_specifique(vectorstore, banque,
                                          annee=annee_search, type_doc=type_doc,
                                          semestre=semestre, cible=cible,
                                          question=question)
        print(f"  Total : {len(chunks)} chunks (exhaustif)")
        return chunks

    # ── Cas 4 : question générale — sémantique globale ──
    filters = build_filters(annee=annee, type_doc=type_doc, semestre=semestre, cible=cible)
    k       = config.RETRIEVER_K
    chunks  = search(vectorstore, question, k=k, filters=filters)

    if len(chunks) < 2 and filters:
        print(f"  Peu de résultats — recherche élargie sans filtres...")
        chunks = search(vectorstore, question, k=k, filters=None)

    print(f"  Total : {len(chunks)} chunks")
    return chunks


# ═══════════════════════════════════════════════════════════
#  FORMATAGE DU CONTEXTE POUR LE LLM
# ═══════════════════════════════════════════════════════════

def format_context(chunks: list) -> str:
    """
    Formate les chunks en sections structurées (banque × période × cible).
    Identique à la version ChromaDB — aucun changement.
    """
    if not chunks:
        return "Aucune information pertinente trouvée dans la base de données."

    groupes    = defaultdict(list)
    ordre_cles = []

    for chunk in chunks:
        meta          = chunk.get("metadata", {})
        banque        = chunk.get("banque", meta.get("banque", "?"))
        annee         = meta.get("annee", "")
        semestre      = meta.get("semestre", "")
        cible         = meta.get("cible_clientele", "")
        type_doc_meta = meta.get("type_document", "")
        est_consolide = meta.get("est_consolide", False)

        key = (banque, annee, semestre, cible, type_doc_meta, est_consolide)
        if key not in groupes:
            ordre_cles.append(key)
        groupes[key].append(chunk)

    sections = []
    SEP = "═" * 55

    for key in ordre_cles:
        banque, annee, semestre, cible, type_doc_meta, est_consolide = key
        group_chunks = groupes[key]

        parts = [banque]
        if semestre and annee:
            parts.append(f"{semestre} {annee}")
        elif annee:
            parts.append(str(annee))
        if cible:
            parts.append(cible)
        entete = " — ".join(parts)

        note_ef = ""
        if type_doc_meta == "etats_financiers" and not est_consolide and annee:
            try:
                annee_int = int(annee)
                annee_n1  = annee_int - 1
                note_ef   = (
                    f"\n[STRUCTURE 2 COLONNES] "
                    f"col.1=Déc-{str(annee_n1)[-2:]}({annee_n1}) [N-1] "
                    f"| col.2=Déc-{str(annee_int)[-2:]}({annee_int}) [N — UTILISER CELLE-CI]"
                )
            except (ValueError, TypeError):
                pass

        corps = []
        for c in group_chunks:
            texte = c.get("texte", "").strip()
            if not texte:
                continue
            lignes = [l for l in texte.split("\n")
                      if not (l.startswith("[") and l.endswith("]") and "|" in l)]
            corps.append("\n".join(lignes).strip())

        header = f"{SEP}\n{entete} ({len(group_chunks)} entrées){note_ef}\n{SEP}"
        sections.append(header + "\n" + "\n".join(corps))

    return "\n\n".join(sections)


# ═══════════════════════════════════════════════════════════
#  DEBUG
# ═══════════════════════════════════════════════════════════

def print_query_debug(mode, banque, annees, type_doc, semestre, cible, prompt="", k=None):
    if not SHOW_QUERY_DEBUG:
        return
    sep = "─" * 62
    print(f"\n{sep}")
    print(f"  REQUETE : {mode}")
    print(f"  Banque  : {banque or '(toutes)'} | Annee(s) : {annees or '(toutes)'}")
    print(f"  TypeDoc : {type_doc or '(tous)'} | Semestre : {semestre or '(tous)'} | Cible : {cible or '(toutes)'}")
    print(sep)


if __name__ == "__main__":
    store = init_retriever()
    questions = [
        "Quels sont les frais de tenue de compte BACI pour les entreprises en 2024 ?",
        "Quel est le résultat net de SGCI en 2024 ?",
        "Comparer les frais de virement entre toutes les banques en 2025",
    ]
    for q in questions:
        print(f"\n[TEST] {q}")
        chunks = search_auto(store, q)
        print(format_context(chunks[:3]))
