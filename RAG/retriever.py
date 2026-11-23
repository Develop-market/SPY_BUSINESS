"""
retriever.py — Recherche sémantique PostgreSQL + pgvector
=========================================================
Remplace ChromaDB par requêtes SQL directes sur intelligence_bancaire.
Logique de routing inchangée (detect_*, search_auto, format_context).
Embedding : sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (768 dims, local).
"""

import re
import unicodedata
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
    _model = None    # singleton — chargé une seule fois
    # Adresse d'inférence qui a répondu, retenue pour ne pas retâtonner à chaque question.
    _url_ok = None

    def __init__(self):
        self.db_params = config.DB_PARAMS

    def get_conn(self):
        """Ouvre une connexion, et ÉLARGIT LA FENÊTRE DE L'INDEX APPROXIMATIF.

        Mesuré le 2026-08-15, en comparant les deux bases : le poste de développement indexe
        `cb_tarifs` et `ef_indicateurs` en HNSW, l'hébergeur en ivfflat à 100 listes. Or
        PostgreSQL n'explore par défaut qu'UNE liste — `ivfflat.probes = 1` —, soit environ
        1 % des 31 985 lignes tarifaires. Sur douze lignes tirées au hasard et cherchées par
        leur propre libellé, la base locale en retrouve quatre et l'hébergeur deux : l'index
        approximatif coûte la moitié du rappel. Toutes les mesures faites en local étaient
        donc flattées, et le chat en ligne trouvait une banque là où le local en trouvait six.

        Dix sondes au lieu d'une, c'est la racine du nombre de listes — le réglage usuel. Le
        `SET` est LOCAL à la session : il ne modifie rien de façon durable, ne demande aucune
        reconstruction d'index, et reste sans effet sur une base indexée en HNSW, qui ignore
        ce paramètre. On l'applique donc partout sans condition.
        """
        import psycopg2
        conn = psycopg2.connect(**self.db_params)
        try:
            with conn.cursor() as c:
                c.execute("SET ivfflat.probes = 10")
            conn.commit()
        except Exception:
            # pgvector absent ou trop ancien : la connexion reste utilisable telle quelle.
            conn.rollback()
        return conn

    def embed_query(self, text: str) -> list:
        """Encode une question → vecteur 768 dims (normalisé).

        DEUX CHEMINS, LE MÊME MODÈLE (2026-08-09, pour l'hébergement).

        En local, le modèle est chargé en mémoire : rien ne bat cela en rapidité, et le poste
        de développement l'a déjà sur disque. En production, l'embarquer coûterait 1,9 Go
        (torch 509 Mo + dépendances 292 Mo + poids 1 126 Mo) — plus que toute la mémoire d'une
        instance gratuite. On appelle alors l'API d'inférence de Hugging Face, qui exécute LE
        MÊME modèle et ne nous fait transporter que la question.

        Ce n'est légitime que parce que les vecteurs sont les mêmes, et cela a été MESURÉ, pas
        supposé : sur quatre questions réelles, la similarité cosinus entre le vecteur local et
        le vecteur distant vaut 1,000000. Les 31 985 vecteurs déjà en base restent donc
        comparables, sans aucun ré-encodage. Si un jour l'API changeait de méthode d'agrégation
        ou de normalisation, ce serait invisible ici mais fatal aux résultats : refaire cette
        mesure est la première chose à faire si le chat se met à répondre à côté.
        """
        # Le modèle local, quand il est là, reste prioritaire : pas de réseau, pas de quota.
        if PGVectorStore._model is not None:
            return PGVectorStore._model.encode([text], normalize_embeddings=True)[0].tolist()

        if not os.getenv("EMBEDDINGS_DISTANTES"):
            try:
                print(f"  [EMBED] Chargement {config.EMBEDDING_MODEL}...", end=" ", flush=True)
                from sentence_transformers import SentenceTransformer
                PGVectorStore._model = SentenceTransformer(config.EMBEDDING_MODEL)
                print("OK")
                return PGVectorStore._model.encode(
                    [text], normalize_embeddings=True)[0].tolist()
            except ImportError:
                print("absent — bascule sur l'API d'inférence")

        return self._embed_distant(text)

    @staticmethod
    def _embed_distant(text: str) -> list:
        """Vectorise la question via l'API d'inférence Hugging Face.

        L'ancienne adresse « api-inference.huggingface.co » ne résout MÊME PLUS en DNS depuis
        que Hugging Face l'a remplacée par un routeur ; on essaie donc les formes connues dans
        l'ordre plutôt que d'en figer une seule et de revivre la même panne au prochain
        changement. La première qui répond est mémorisée pour les questions suivantes.
        """
        import json
        import urllib.request

        jeton = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN") or ""
        if not jeton:
            raise RuntimeError(
                "Vectorisation impossible : ni modèle local, ni HF_TOKEN. "
                "Renseignez HF_TOKEN (droit d'inférence) pour activer le chat.")

        m = config.EMBEDDING_MODEL
        adresses = [PGVectorStore._url_ok] if PGVectorStore._url_ok else [
            f"https://router.huggingface.co/hf-inference/models/{m}/pipeline/feature-extraction",
            f"https://router.huggingface.co/hf-inference/pipeline/feature-extraction/{m}",
            f"https://router.huggingface.co/hf-inference/models/{m}",
        ]
        corps = json.dumps({"inputs": text,
                            "options": {"wait_for_model": True}}).encode()
        dernier = "aucun essai"
        for url in adresses:
            for essai in range(3):
                try:
                    r = urllib.request.Request(
                        url, data=corps,
                        headers={"Authorization": f"Bearer {jeton}",
                                 "Content-Type": "application/json"})
                    v = json.loads(urllib.request.urlopen(r, timeout=60).read())
                    # La réponse est [768] ou [[768]] selon la forme de l'adresse ; si le
                    # modèle rend un vecteur PAR JETON, on moyenne — c'est ce que fait le
                    # pooling de sentence-transformers.
                    while isinstance(v, list) and v and isinstance(v[0], list):
                        v = v[0] if len(v) == 1 else [sum(c) / len(c) for c in zip(*v)]
                    # Normalisation L2, pour rendre exactement ce que rend le chemin local.
                    n = sum(x * x for x in v) ** 0.5
                    if n:
                        v = [x / n for x in v]
                    PGVectorStore._url_ok = url
                    return v
                except Exception as e:
                    dernier = f"{type(e).__name__} — {str(e)[:110]}"
                    code = getattr(e, "code", None)
                    if code in (503, 429) and essai < 2:
                        import time as _t
                        _t.sleep(8)          # modèle froid ou quota momentané
                        continue
                    break
        raise RuntimeError(f"API d'inférence injoignable : {dernier}")

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

# ═══════════════════════════════════════════════════════════
#  CHEMIN HIÉRARCHIQUE DES SECTIONS CB (2026-07-27)
# ═══════════════════════════════════════════════════════════
# BUG MAJEUR TROUVÉ le 2026-07-27 (le directeur : « 2 350 FCFA, justement c'est problématique
# car ça dépend du type de compte ») — bien pire que « vague », c'était FAUX DE SENS :
#
#   Question : « frais de tenue de compte SGCI particuliers 2024 S1 ? » → réponse « 2 350 FCFA ».
#   Réalité en base : cette ligne porte la section 4.5.3, et la section 4.5 s'intitule
#   « SUCCESSIONS ». Ce sont donc les frais de tenue d'un compte de SUCCESSION (compte d'une
#   personne décédée), pas le tarif courant d'un particulier.
#
# Cause : la grille tarifaire est hiérarchique (« 4 » > « 4.5 Successions » > « 4.5.3 Frais de
# tenue de compte »), mais chaque ligne était envoyée au LLM SEULE, sans ses parents. La colonne
# `contexte` ne comble le trou que quand elle est renseignée — elle est NULL sur 5 679 lignes
# (18 % de la base), et précisément NULL sur celle-ci. Le LLM recevait « Frais de tenue de
# compte : 2350 » sans aucun moyen de savoir de quel compte il s'agit : il ne pouvait QUE
# répondre à côté, quelles que soient les consignes du prompt (qui exige pourtant déjà
# « jamais de montant sans préciser le type », cf. prompts.py — une consigne inapplicable si
# l'information n'est pas dans le contexte).
#
# Correctif : reconstruire le chemin des ancêtres à partir de la numérotation et le préfixer au
# texte du chunk → « Successions > Frais de tenue de compte : 2350 ». Le LLM voit enfin de quoi
# il parle, et l'utilisateur aussi.
_SECTIONS_CB = None


def _charger_sections_cb() -> dict:
    """Charge une fois par process {(banque,annee,semestre,segment,section): titre}.

    Coût : une requête, ~32 000 lignes, quelques Mo — négligeable face à un rechargement par
    question. Les titres ne changent qu'à l'ingestion de nouvelles données (cf. invalider())."""
    global _SECTIONS_CB
    if _SECTIONS_CB is not None:
        return _SECTIONS_CB
    d = {}
    try:
        vs = init_retriever()
        with vs.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT banque, annee, semestre, segment, section, libelle, is_header
                               FROM cb_tarifs
                               WHERE section IS NOT NULL AND libelle IS NOT NULL AND libelle <> ''""")
                for banque, annee, semestre, segment, section, libelle, is_header in cur.fetchall():
                    cle = (banque, annee, semestre, segment, section)
                    # Une même section peut porter plusieurs lignes (un titre + des valeurs).
                    # On privilégie l'en-tête déclaré ; à défaut le libellé le plus COURT, qui
                    # est presque toujours l'intitulé de rubrique plutôt qu'une ligne de détail.
                    ancien = d.get(cle)
                    if ancien is None or (is_header and not ancien[1]) or \
                       (bool(is_header) == bool(ancien[1]) and len(libelle) < len(ancien[0])):
                        d[cle] = (libelle, bool(is_header))
        _SECTIONS_CB = {k: v[0] for k, v in d.items()}
    except Exception as e:
        print(f"  [SECTIONS CB] Chargement impossible ({e}) — chemins de section désactivés.")
        _SECTIONS_CB = {}
    return _SECTIONS_CB


def invalider_sections_cb():
    """Force le rechargement des titres de section (après un ajout de données)."""
    global _SECTIONS_CB
    _SECTIONS_CB = None


# Titres d'ancêtre trop génériques pour apporter la moindre information : les afficher
# n'ajoute que du bruit dans un contexte au budget serré. Comparaison sur forme normalisée.
_ANCETRES_INUTILES = {"", "-", "n/a", "divers", "autres", "autres services", "services",
                      "tarifs", "tarif", "conditions", "libelle", "libellé", "designation",
                      "désignation", "rubrique", "operations", "opérations"}


def _chemin_section_cb(banque, annee, semestre, segment, section) -> str:
    """Chemin des sections ANCÊTRES ('4.5.3' → titre de '4' puis de '4.5').

    N'inclut PAS le titre de la section de la ligne elle-même : c'est déjà son libellé, le
    répéter doublerait la taille du chunk sans rien apporter."""
    if not section or "." not in str(section):
        return ""
    parts = str(section).split(".")
    titres = []
    table = _charger_sections_cb()
    for i in range(1, len(parts)):
        titre = table.get((banque, annee, semestre, segment, ".".join(parts[:i])))
        if titre and titre.strip().lower() not in _ANCETRES_INUTILES:
            t = titre.strip()
            # Un ancêtre qui répète déjà ce qu'un ancêtre plus proche dit n'apporte rien.
            if not any(t.lower() in d.lower() or d.lower() in t.lower() for d in titres):
                titres.append(t)
    return " > ".join(titres)


def _chunk_cb(row) -> dict:
    """Convertit une ligne cb_tarifs en chunk RAG.

    Ordre des colonnes (2026-07-27, `section` ajoutée en 5ᵉ position dans les 4 requêtes qui
    alimentent cette fonction) :
      0=banque 1=annee 2=semestre 3=segment 4=section 5=contexte 6=libelle 7=valeur_brute [8=score]
    """
    banque   = row[0]
    annee    = row[1]
    semestre = row[2]
    segment  = row[3] or ""
    section  = row[4]
    contexte = row[5] or ""
    libelle  = row[6] or ""
    valeur   = row[7] or ""
    score    = float(row[8]) if len(row) > 8 and row[8] is not None else 1.0

    # chemin > contexte > libellé : valeur, en écartant les répétitions. `contexte` reprend
    # souvent le titre d'un ancêtre ("Gestions des comptes > ... > Gestions des comptes >
    # Frais de tenue de compte") : redondant à lire, et payé deux fois en tokens sur un
    # budget déjà serré. Déduplication par inclusion (insensible à la casse) plutôt que par
    # égalité stricte, car les variantes sont fréquentes ("Gestion des comptes" au singulier).
    chemin = _chemin_section_cb(banque, annee, semestre, segment, section)
    morceaux = []
    for p in [*(chemin.split(" > ") if chemin else []), contexte, libelle]:
        p = (p or "").strip()
        if not p:
            continue
        p_low = p.lower()
        if any(p_low in d.lower() or d.lower() in p_low for d in morceaux):
            continue
        morceaux.append(p)
    texte = f"{' > '.join(morceaux)} : {valeur}".strip(" >:")

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
    # montant/annee_rapport : colonnes numeriques canoniques, portees uniquement pour
    # departager les doublons (_desambiguiser_ef_chunks), jamais affichees au LLM (le texte
    # lisible reste valeur_brute + unite, inchange).
    montant       = float(row[7]) if len(row) > 7 and row[7] is not None else None
    annee_rapport = row[8] if len(row) > 8 else None

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
            "montant"         : montant,
            "annee_rapport"   : annee_rapport,
        },
        "source"  : f"EF_{banque}",
        "banque"  : banque,
        "periode" : str(annee_donnee),
        "type_doc": "etats_financiers",
    }


# Cf. structured_tools._SEUIL_ECART_AMBIGU — meme seuil, meme justification, calibre sur les
# memes cas reels (revisions inter-rapports legitimes sous 5 %, vraies anomalies bien au-dela).
_SEUIL_ECART_AMBIGU = 0.05


def _desambiguiser_ef_chunks(chunks: list) -> list:
    """Neutralise les doublons contradictoires (OCR) avant qu'ils n'atteignent le LLM.

    ef_indicateurs contient des lignes marquées is_primary=TRUE en double pour un même
    (banque, année, libellé) — ex. ECOBANK PNB 2023 : 110 189 ET 710 189 (rapports 2023 et
    2024), toutes deux is_primary=TRUE, texte quasi identique -> les DEUX remontent en tête
    d'une recherche sémantique sur « PNB ECOBANK 2023 » (vérifié le 2026-09-03), sans aucun
    signal qu'elles se contredisent. Le LLM recevait alors deux chiffres opposés dans son
    contexte et pouvait en choisir un au hasard, ou pire, les mélanger, sans le dire au
    lecteur. Ce filtre existait déjà côté SQL-comparaison (structured_tools._resoudre_valeur_ef)
    mais jamais côté récupération sémantique — les deux chemins alimentent le même chat.

    DEUX cas distincts :
    1. Vraie contradiction (écart > 5 %, ex. ci-dessus 84 %) — aucune des deux valeurs n'est
       fiable → exclue, remplacée par un chunk qui le dit explicitement.
    2. Révision mineure entre deux rapports annuels qui se recouvrent (écart < 5 %, ex. SGCI
       « autres actifs » 2024 : 17 708 vs 17 709) — pas une contradiction, on garde la valeur
       du rapport le plus récent (annee_rapport le plus élevé), jamais une moyenne ou un
       maximum muet."""
    par_cle = defaultdict(list)
    autres = []
    for c in chunks:
        md = c.get("metadata", {})
        # Seules les lignes is_primary=TRUE sont regroupées : une ligne is_primary=FALSE est
        # déjà, par construction de la base, écartée au profit d'une autre — la confondre ici
        # avec la primaire ferait passer une valeur ÉTABLIE pour "ambiguë" si l'ancienne
        # extraction superseded portait un chiffre différent (régression, pas un correctif).
        if md.get("type_document") != "etats_financiers" or md.get("is_primary") is not True:
            autres.append(c)
            continue
        libelle = (c.get("texte") or "").split(" : ", 1)[0].strip().lower()
        cle = (c.get("banque"), md.get("annee"), libelle)
        par_cle[cle].append(c)

    out = list(autres)
    for (banque, annee, libelle), groupe in par_cle.items():
        # Comparaison sur `montant` (colonne numérique canonique), pas sur le texte affiché :
        # deux lignes peuvent porter la même valeur avec un habillage différent sans être
        # réellement contradictoires — seul le nombre canonique tranche.
        vus = {}
        for c in groupe:
            md = c.get("metadata", {})
            m = md.get("montant")
            if m is not None:
                vus.setdefault(round(m, 0), md.get("annee_rapport"))
        montants = sorted(vus)
        if len(montants) <= 1:
            out.extend(groupe)
            continue

        ecart_relatif = (max(montants) - min(montants)) / max(abs(max(montants)), 1)
        if ecart_relatif < _SEUIL_ECART_AMBIGU:
            valeur_retenue = max(vus, key=lambda v: (vus[v] or 0, v))
            print(f"  [EF RÉVISION] {banque} {annee} « {libelle} » : "
                  f"{', '.join(f'{v:,.0f}'.replace(',', ' ') for v in montants)} "
                  f"(écart {ecart_relatif:.1%}, rapports différents) — retenu : "
                  f"{valeur_retenue:,.0f}".replace(",", " "))
            for c in groupe:
                if round((c.get("metadata", {}).get("montant") or -1), 0) == valeur_retenue:
                    out.append(c)
                    break
            continue

        vals_txt = ', '.join(f"{v:,.0f}".replace(',', ' ') for v in montants)
        print(f"  [EF AMBIGU] {banque} {annee} « {libelle} » : {len(montants)} valeurs "
              f"contradictoires en base ({vals_txt}, écart {ecart_relatif:.1%}) — exclu, non fiable")
        out.append({
            "texte": (f"{libelle} ({banque}, {annee}) : donnée AMBIGUË en base — plusieurs "
                      f"valeurs contradictoires enregistrées, aucune ne peut être citée comme "
                      f"fiable sans vérification de la source."),
            "score": groupe[0].get("score", 1.0),
            "metadata": {**groupe[0].get("metadata", {}), "ambigu": True},
            "source": groupe[0].get("source", ""),
            "banque": banque,
            "periode": str(annee),
            "type_doc": "etats_financiers",
        })
    return out


# Marqueurs techniques du pipeline d'extraction présents dans 85 des 88 chunks réglementaires
# (« [PAGE 4] », « [METRICS chars=2803 density=5.59 ocr_pct=0.0 tables=NON ocr_conf=N/A] »).
# Ils partaient jusqu'ici DANS le contexte transmis au LLM : du bruit pur, qui consomme du
# budget de tokens sur une fenêtre déjà serrée et brouille la lecture des articles de loi.
# Nettoyage à la lecture, la base reste intacte. (2026-07-30)
_RE_MARQUEURS_EXTRACTION = re.compile(r"\[(?:PAGE\s+\d+|METRICS[^\]]{0,200})\]\s*")


def _chunk_regl(row) -> dict:
    """Convertit une ligne regl_documents en chunk RAG."""
    fichier = row[0] or ""
    contenu = _RE_MARQUEURS_EXTRACTION.sub(" ", row[1] or "").strip()
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
                               1 - (embedding <=> %s::vector) AS score, montant, annee_rapport
                        FROM ef_indicateurs
                        {where}
                          {"AND" if where else "WHERE"} embedding IS NOT NULL
                          AND 1 - (embedding <=> %s::vector) >= {threshold}
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                    """
                    cur.execute(sql, [vec_lit] + params + [vec_lit, vec_lit, k])
                    # Doublons contradictoires is_primary=TRUE (ex. ECOBANK PNB 2023 : 110 189
                    # vs 710 189) neutralises AVANT le LLM, pas apres — cf. _desambiguiser_ef_chunks.
                    chunks = _desambiguiser_ef_chunks([_chunk_ef(r) for r in cur.fetchall()])

                elif type_doc == "reglementation":
                    # Recherche HYBRIDE — mesure à l'appui : sur ce corpus, la similarité
                    # seule couvrait 98 % des cas mais avec un MRR de 0,052, autrement dit
                    # elle retrouvait le bon fragment et le classait quarantième. Vérifié
                    # sur « quel est le taux de l'usure » : la décision qui porte le chiffre
                    # n'entrait pas dans les trois premiers résultats.
                    #
                    # Le vocabulaire juridique est rare et précis — « usure », « gratuité »,
                    # « agrément » —, donc idéal pour une recherche par mots, là où un
                    # vecteur confond « gratuité » avec « tarification » ou « exonération ».
                    # On interroge donc les deux voies et on fusionne les CLASSEMENTS (rang
                    # réciproque) plutôt que les scores, qui ne sont pas comparables entre
                    # eux : un fragment bien placé par l'une OU par l'autre remonte.
                    #
                    # Le bras lexical interroge en OU, pas en ET. `plainto_tsquery` exige que
                    # TOUS les mots de la question figurent dans le fragment : « quel est le
                    # taux de l'usure applicable aux banques » ne ramenait rien, faute du mot
                    # « applicable » dans la décision. On convertit donc la question en ses
                    # lexèmes et on les joint par « | » ; c'est `ts_rank` qui départage, un
                    # fragment portant plus de mots de la question passant devant.
                    #
                    # PROFONDEUR et CONSTANTE réglées par balayage sur huit questions
                    # réglementaires, pas reprises par habitude. Les valeurs usuelles
                    # (40 candidats, C = 60) visent des corpus de millions de documents ;
                    # le nôtre en compte 408. Mesuré : 40/60 place 6 bonnes réponses sur 8
                    # dans les trois premières pour un MRR de 0,688 ; 30/5 en place 7 pour
                    # 0,762. À refaire si le corpus change d'ordre de grandeur — le réglage
                    # dépend de sa taille, la même mesure sur 104 fragments donnait 10/1.
                    prof = max(30, k)
                    sql = """
                        WITH q AS (
                            SELECT array_to_string(
                                       tsvector_to_array(to_tsvector('french', %s)), ' | '
                                   )::tsquery AS tsq
                        ),
                        vect AS (
                            SELECT id, fichier, contenu,
                                   ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) AS rang
                            FROM regl_documents
                            WHERE embedding IS NOT NULL
                            ORDER BY embedding <=> %s::vector
                            LIMIT %s
                        ),
                        lex AS (
                            SELECT r.id, r.fichier, r.contenu,
                                   ROW_NUMBER() OVER (
                                       ORDER BY ts_rank(to_tsvector('french', r.contenu),
                                                        q.tsq) DESC
                                   ) AS rang
                            FROM regl_documents r, q
                            WHERE to_tsvector('french', r.contenu) @@ q.tsq
                            LIMIT %s
                        )
                        SELECT COALESCE(v.fichier, l.fichier),
                               COALESCE(v.contenu, l.contenu),
                               COALESCE(1.0 / (5 + v.rang), 0)
                             + COALESCE(1.0 / (5 + l.rang), 0) AS score
                        FROM vect v
                        FULL OUTER JOIN lex l ON v.id = l.id
                        ORDER BY score DESC
                        LIMIT %s
                    """
                    # REPLI SUR LE VECTORIEL SEUL si le bras lexical est indisponible.
                    # Les deux bras tiennent dans une seule requête : si le dictionnaire
                    # français de PostgreSQL manque à l'hébergeur, ce n'est pas la moitié
                    # lexicale qui se perd, c'est TOUTE la requête — et `search()` rendrait
                    # une liste vide, donc un chat muet sur la réglementation, alors que la
                    # recherche vectorielle seule fonctionnait avant. Un correctif ne doit
                    # jamais pouvoir rendre l'application pire qu'avant lui. Le repli est
                    # ANNONCÉ : sans message, une dégradation silencieuse se découvre des
                    # semaines plus tard, comme les cinq chemins morts de ce projet.
                    try:
                        cur.execute(sql, [question, vec_lit, vec_lit, prof, prof, k])
                        chunks = [_chunk_regl(r) for r in cur.fetchall()]
                    except Exception as e:
                        conn.rollback()
                        print(f"  [REGL] recherche lexicale indisponible ({str(e)[:80]}) — "
                              f"repli sur le vectoriel seul")
                        cur.execute(f"""
                            SELECT fichier, contenu, 1 - (embedding <=> %s::vector) AS score
                            FROM regl_documents
                            WHERE embedding IS NOT NULL
                              AND 1 - (embedding <=> %s::vector) >= {threshold}
                            ORDER BY embedding <=> %s::vector
                            LIMIT %s
                        """, [vec_lit, vec_lit, vec_lit, k])
                        chunks = [_chunk_regl(r) for r in cur.fetchall()]

                else:
                    # conditions_banque (défaut)
                    where, params = _sql_where_cb(banque=banque, annee=annee, semestre=semestre, cible=cible)
                    sql = f"""
                        SELECT banque, annee, semestre, segment, section, contexte, libelle, valeur_brute,
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
        SELECT banque, annee, semestre, segment, section, contexte, libelle, valeur_brute
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
                            SELECT banque, annee, semestre, segment, section, contexte, libelle, valeur_brute
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
# 2026-07-25 (audit chat, problème #6) : élargi de 7 à 20 catégories en réutilisant le
# vocabulaire déjà VALIDÉ empiriquement dans dash_app/cb_sections.py (lu sur les vraies
# brochures des 7 banques pour classer les tarifs par section BCEAO) — pas de synonymes
# inventés, uniquement des termes déjà confirmés présents dans les données réelles.
_SYNONYMES_SERVICE = {
    "tenue"        : ["tenue", "convenance", "relevé", "relevé de compte", "frais fixe"],  # SGCI entr. = "relevés/mois"
    "virement"     : ["virement", "transfert"],
    "retrait"      : ["retrait", "espece", "dab", "gab"],
    "carte"        : ["carte", "visa", "mastercard", "classic", "gold", "platinum", "premier", "infinite"],
    "chequier"     : ["chequier", "chèquier", "cheque"],
    "domiciliation": ["domiciliation"],
    "decouvert"    : ["decouvert", "découvert", "agios", "avance sur"],
    "credit"       : ["credit", "prêt", "pret", "credit-bail", "credit bail", "taux d'interet",
                       "teg", "assurance emprunteur", "caution", "aval", "escompte", "amortissement"],
    "dossier"      : ["frais de dossier", "dossier"],
    "change"       : ["change", "devise", "devises", "cours de change", "cheque de voyage", "billets de banque"],
    "etranger"     : ["etranger", "étranger", "swift", "uemoa", "transfert emis", "transfert recu"],
    "incident"     : ["incident de paiement", "rejet de cheque", "rejet cheque", "opposition",
                       "sans provision", "injonction", "impaye", "impayé", "compte debiteur"],
    "banque_distance": ["banque a distance", "banque en ligne", "internet", "sms", "alerte sms",
                         "mobile banking", "messalia", "infobank"],
    "titres"       : ["titres", "bourse", "opcvm", "valeurs mobilieres", "brvm", "bon de caisse",
                       "epargne salariale"],
    "succession"   : ["succession", "coffre-fort", "coffre fort"],
    "ouverture"    : ["ouverture de compte", "ouverture"],
    "cloture"      : ["cloture de compte", "clôture de compte", "cloture", "clôture"],
    "attestation"  : ["attestation", "confirmation bancaire", "releve d'identite", "rib"],
    "prelevement"  : ["prelevement", "prélèvement"],
    "commission"   : ["commission d'intervention", "commission de mouvement"],
}


def _extraire_terme_service(question: str) -> str:
    """
    Extrait le terme de service principal de la question (NLP minimal).
    'frais de tenue de compte' → 'tenue'
    'frais de virement' → 'virement'

    2026-07-25 : élargi la 2e regex (liste fixe) à toutes les catégories connues de
    _SYNONYMES_SERVICE (avant : seulement 6 mots) — une question comme "quel est le
    coût du découvert" passait déjà, mais "les frais d'incident de paiement" ou "le
    coût du change" ne matchaient RIEN avant cet élargissement.
    """
    import re
    q = question.lower()
    mots_directs = "|".join(sorted({
        m for syns in _SYNONYMES_SERVICE.values() for m in syns if " " not in m
    }, key=len, reverse=True))
    # 2026-07-25 : le vocabulaire fermé (mots_directs) passe EN PREMIER, pas en dernier — la
    # regex générique "frais/tarif/coût + de/du/des + (mot suivant)" capture parfois un mot de
    # liaison sans rapport (ex. "tarif DU SERVICE SMS banking" → capturait "service" au lieu de
    # "sms", bug trouvé lors de l'audit). Le vocabulaire fermé, lui, ne peut pas se tromper de
    # mot puisqu'il ne connaît QUE de vrais termes de service.
    patterns = [
        rf"\b({mots_directs})\b",
        r"(?:frais|tarif|co[uû]t|commission|montant)\s+(?:de|du|des|d[''])\s+(\w+)",
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
        SELECT banque, annee, semestre, segment, section, contexte, libelle, valeur_brute
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
        SELECT banque, libelle, valeur_brute, unite, annee_donnee, is_primary, NULL, montant, annee_rapport
        FROM ef_indicateurs
        {where}
        ORDER BY banque, annee_donnee, libelle
    """
    try:
        with vectorstore.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return _desambiguiser_ef_chunks([_chunk_ef(r) for r in cur.fetchall()])
    except Exception as e:
        print(f"  [EXHAUSTIF EF ERREUR] {e}")
        return []


def _get_exhaustif_regl(vectorstore: PGVectorStore, question: str, k: int = None) -> list:
    """Rend une LARGE sélection réglementaire, classée par pertinence.

    Cette fonction versait auparavant la table entière, dans l'ordre des fichiers. C'était
    tenable tant que le corpus tenait en 88 fragments ; découpé par article il en compte
    près de 400, soit 264 000 caractères là où le modèle en reçoit 9 000. Le contexte était
    donc rogné juste après, et cette réduction garde la TÊTE de ce qu'on lui donne : le
    modèle recevait le début du premier fichier par ordre alphabétique, sans aucun rapport
    avec la question. Constaté sur « quelles obligations de transparence tarifaire pèsent
    sur les banques ? » — l'instruction de 2015 était en base, bien classée par la recherche,
    et le chat répondait « non disponible dans le contexte fourni ».

    On garde l'intention — une question générale mérite une vue large, pas trois fragments —
    mais dans un ORDRE qui a un sens, pour que ce soit le plus pertinent qui survive à la
    réduction et non le premier par ordre alphabétique.
    """
    if k is None:
        k = config.REGL_K_LARGE
    return search(vectorstore, question, k=k,
                  filters=build_filters(type_doc="reglementation"))


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

_TABLE_ACCENTS = str.maketrans("àâäáãçéèêëíìîïñóòôöõúùûüýÿ", "aaaaaceeeeiiiinooooouuuuyy")


def _sans_accents(t: str) -> str:
    return (t or "").translate(_TABLE_ACCENTS)


def detect_banque(question: str):
    banques = detect_banques(question)
    return banques[0] if banques else None


def detect_banques(question: str) -> list:
    # Accents retirés des DEUX côtés : « SOCIETE GENERALE » tapé sans accent ne matchait pas
    # l'alias « société générale » (2026-07-27).
    q = _sans_accents(question.lower())
    found, seen = [], set()
    for alias, code in BANQUE_ALIASES.items():
        if _sans_accents(alias) in q and code not in seen:
            found.append(code)
            seen.add(code)
    if found:
        return found

    # RATTRAPAGE PAR PRÉFIXE (2026-07-27) — uniquement si AUCUN alias exact n'a matché, donc
    # sans aucun risque pour les cas qui fonctionnaient déjà. Motif : « frais de cloture de
    # compte bici » ne détectait aucune banque (« bici » n'est pas un alias, « bicici » oui) et
    # partait en recherche sans filtre, pour finir sur « Non disponible dans le document » —
    # alors que BICICI a 28 lignes de clôture en base. Un dirigeant abrège en tapant vite ;
    # l'outil doit suivre.
    # Garde-fou anti-faux-positif : on n'accepte un préfixe que s'il désigne UNE SEULE banque.
    # « banque » préfixe à la fois « banque atlantique » (BACI) et « banque nationale » (BNI) —
    # ambigu, donc ignoré, alors que « eco » ne désigne qu'ECOBANK et « bici » que BICICI.
    for mot in set(re.findall(r"[a-z]{4,}", q)):
        codes = {code for alias, code in BANQUE_ALIASES.items()
                 if _sans_accents(alias).startswith(mot)}
        if len(codes) == 1:
            code = codes.pop()
            if code not in seen:
                found.append(code)
                seen.add(code)
                print(f"  [BANQUE PAR PRÉFIXE] « {mot} » → {code}")
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


_RE_CACHE_MOTS = {}


def _sans_accents(t: str) -> str:
    """Minuscules sans signes diacritiques : « Gratuité » et « gratuite » deviennent le même
    mot. Sert uniquement à COMPARER — le texte affiché ou envoyé au modèle n'est pas touché."""
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _contient_mot(q: str, mots) -> bool:
    """Vérifie qu'un mot-clé apparaît comme un VRAI mot (frontière \\b), pas comme simple
    sous-chaîne. BUG TROUVÉ le 2026-07-25 (en testant l'agent de secours) : "efficiente
    opéRATIOnnellement" déclenchait à tort le domaine États Financiers via le mot-clé "ratio"
    — simple sous-chaîne, sans rapport avec le sens. `m in q` matchait "ratio" dans
    "opérationnellement" comme dans "ratio de solvabilité". Remplacé par une frontière de mot
    (fonctionne aussi pour les expressions à espaces comme "total bilan" : \\b s'applique au
    premier et dernier caractère de toute la sous-chaîne)."""
    key = tuple(mots)
    compiled = _RE_CACHE_MOTS.get(key)
    if compiled is None:
        # Comparaison SANS ACCENTS, des deux côtés. Les listes de mots-clés dédoublaient
        # jusqu'ici chaque entrée à la main — « rentabilité » et « rentabilite »,
        # « conformité » et « conformite » — ce qui n'attrape que les cas auxquels on a
        # pensé : « gratuité », « agrément », « préavis » ou « entrée en vigueur » restaient
        # muets pour qui tape vite et sans accents, ce que fait tout le monde. Le repli est
        # fait une fois ici plutôt que répété dans trois listes, et les doublons déjà
        # présents deviennent inoffensifs.
        motifs = sorted({_sans_accents(m) for m in mots}, key=len, reverse=True)
        # PLURIELS (2026-09-07). La frontiere de FIN excluait « tarifs », « cartes »,
        # « virements », « commissions » : seul le singulier exact matchait, et « compare
        # les tarifs des cartes » n activait AUCUN domaine — la question partait en
        # recherche vectorielle generique, sans filtre. Un « s » ou « x » optionnel avant
        # la frontiere suffit. On ne RETIRE pas cette frontiere : sans elle « ratio »
        # matcherait « rationalisation », ce qui rejouerait le bug du 2026-07-25 en miroir.
        compiled = re.compile(r"\b(?:" + "|".join(re.escape(m) for m in motifs) + r")(?:s|x)?\b")
        _RE_CACHE_MOTS[key] = compiled
    return compiled.search(_sans_accents(q)) is not None


# Signaux risque/CNR : le mot « coût » de MOTS_CONDITIONS ne doit PAS tirer ces
# questions vers les grilles tarifaires (bug 2026-10-19 : reco CNR = monter les frais
# de dossier). On retire conditions_banque si le seul déclencheur tarifaire est ce « coût ».
_MOTS_RISQUE_EF = (
    "cnr", "cout du risque", "coût du risque", "cout net du risque", "coût net du risque",
    "cout risque", "coût risque", "provisionnement", "creances douteuses",
    "créances douteuses", "npl", "impaye", "impayé",
)


def detect_types_doc(question: str) -> list:
    q = question.lower()
    types = []
    if _contient_mot(q, config.MOTS_REGLEMENTATION):
        types.append("reglementation")
    if _contient_mot(q, config.MOTS_EF):
        types.append("etats_financiers")
    if _contient_mot(q, config.MOTS_CONDITIONS):
        types.append("conditions_banque")
    if _contient_mot(q, config.MOTS_VEILLE):
        types.append("veille")

    # Garde-fou CNR/risque : ne garder les tarifs que si la question parle AUSSI
    # explicitement de frais/tarifs/commissions (hors le seul mot « coût » du CNR).
    if "conditions_banque" in types and any(m in q for m in _MOTS_RISQUE_EF):
        q_sans_risque = q
        for m in _MOTS_RISQUE_EF:
            q_sans_risque = q_sans_risque.replace(m, " ")
        # « coût » / « cout » restants après retrait du CNR ne suffisent pas seuls.
        mots_tarif_nets = [m for m in config.MOTS_CONDITIONS
                           if m not in ("coût", "cout", "coût", "conditions")]
        if not _contient_mot(q_sans_risque, mots_tarif_nets):
            types.remove("conditions_banque")
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
        # Trajectoire / cible opérationnelle (2026-10-19)
        "passer a", "passer à", "reduire", "réduire", "baisser", "abaisser",
        "atteindre", "cible", "horizon", "prochains mois", "plan d action",
        "plan d'action", "operationnel", "opérationnel", "operationnelle",
        "comment faire pour", "que faire pour", "leviers",
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


def texte_disponibilite_ef() -> str:
    """Construit la liste « quelle banque a quelles années » injectée dans le prompt LLM
    EF — RECALCULÉE à chaque appel depuis ETATS_FINANCIERS_ANNEES (dynamique, cf. config.py),
    au lieu d'un texte figé recopiant un instantané des années au moment où le prompt a été
    écrit. Regroupe les banques qui partagent EXACTEMENT les mêmes années (évite de répéter
    la même plage 7 fois)."""
    groupes = {}
    for banque, annees in ETATS_FINANCIERS_ANNEES.items():
        cle = tuple(sorted(annees))
        groupes.setdefault(cle, []).append(banque)
    lignes = []
    for annees, banques in sorted(groupes.items(), key=lambda kv: -max(kv[0])):
        plage = "-".join(str(a) for a in annees)
        lignes.append(f"  {plage} : {', '.join(sorted(banques))}")
    return "\n".join(lignes) if lignes else "  (aucune donnée EF disponible)"


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
        chunks = _get_exhaustif_regl(vectorstore, question)
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


def search_toutes_banques(vectorstore, question: str, type_doc: str = None) -> list:
    """
    Récupère les données de TOUTES les banques de façon exhaustive.
    CB : boucle banques × cibles × semestres.
    EF / REGL : boucle banques.

    LE DOMAINE EST IMPOSÉ PAR L'APPELANT quand il le connaît. Cette fonction le redéduisait
    de la question, et `detect_type_doc` donne la priorité à la réglementation : appelée pour
    l'agent Conditions Tarifaires sur « la SGCI est-elle plus chère que ses concurrents, et
    que prévoit la BCEAO ? », elle rendait des articles de loi. Les DEUX agents recevaient
    alors la même matière réglementaire, aucun n'avait les grilles, et le modèle répondait
    « les grilles tarifaires des concurrents ne sont pas disponibles » — ce qui était vrai
    de ce qu'on lui avait donné. Un agent doit chercher dans SON domaine, pas dans celui que
    la question évoque le plus fort.
    """
    annee    = detect_annee(question)
    type_doc = type_doc or detect_type_doc(question) or "conditions_banque"
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
        tous_chunks = _get_exhaustif_regl(vectorstore, question)
        print(f"  [REGL VUE LARGE] {len(tous_chunks)} articles classes")

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
                key = c.get("texte", "")   # texte ENTIER — cf. note ligne ~1175
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

    # ── Cas 2c : comparaison sur TOUTES les banques ──
    #
    # La condition exigeait qu'AUCUNE banque ne soit nommée. C'était confondre « nommer une
    # banque » et « ne parler que d'elle ». « La SGCI est-elle plus chère que ses
    # CONCURRENTS ? » nomme la SGCI et demande pourtant les six autres : la question tombait
    # dans « banque précise », on n'allait chercher que la SGCI, et le modèle répondait — avec
    # raison — « les documents fournis ne contiennent pas les grilles des concurrents ». Il
    # disait vrai : on ne lui avait donné qu'une banque. Le défaut était dans la récupération,
    # pas dans la rédaction.
    #
    # Une banque nommée DANS une question comparative est le SUJET de la comparaison, pas son
    # périmètre. Deux banques ou plus étaient déjà traitées ailleurs ; c'est le cas d'UNE
    # seule qui manquait.
    comparaison_ouverte = is_comparaison(question) and len(banques) <= 1
    if comparaison_ouverte:
        if type_doc == "reglementation":
            chunks = _get_exhaustif_regl(vectorstore, question)
            print(f"  [REGL VUE LARGE] {len(chunks)} articles classes")
            return chunks
        return search_toutes_banques(vectorstore, question, type_doc=type_doc)

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

            # Union dédupliquée — KEYWORD EN PREMIER (2026-07-25, bug trouvé en testant : « frais
            # de tenue de compte SGCI 2024 » ne remontait jamais le vrai chiffre "Frais de tenue
            # de compte : 2 350", pourtant bien trouvé par search_cb_keyword). Cause : l'union
            # mettait le sémantique EN PREMIER, et chain.py._executer() tronque le contexte par
            # SECTION (banque×période) dans l'ORDRE D'APPARITION — les chunks keyword, positionnés
            # en dernier dans leur section, étaient donc les premiers sacrifiés, alors que ce sont
            # justement les correspondances EXACTES (le filet de sécurité censé pallier les trous
            # du sémantique). Le dédoublonnage garde la 1ʳᵉ occurrence : mettre keyword_chunks en
            # tête leur donne la priorité de survie sans perdre le sémantique (toujours inclus
            # ensuite, dédupliqué).
            # PLAFOND DU SÉMANTIQUE QUAND LE KEYWORD A RÉPONDU (2026-07-27, trouvé par la
            # batterie de test). Symptôme : « frais de tenue de compte BNI particuliers 2024 S1 »
            # ne citait qu'UNE des 4 tranches de revenu — réponse fausse, pas seulement partielle.
            # Cause : l'union produisait ~70 chunks (34 keyword exacts + 80 sémantiques dédupés)
            # pour une question qui en demande une dizaine. Le contexte atteignait 8 400 chars,
            # dépassait le budget Groq, et la troncature « équitable par section » rabotait chaque
            # section à ~930 chars — emportant les tranches 3 et 4 au passage. Le sémantique large
            # est un FILET (rattraper un libellé formulé autrement), pas la réponse : quand des
            # correspondances EXACTES existent, il n'a pas à occuper la moitié du budget et à
            # faire tomber la réponse elle-même. Plafonné, le contexte tient sans troncature.
            plafond_sem = 20 if keyword_chunks else len(semantic_chunks)
            seen, chunks = set(), []
            for c in keyword_chunks + semantic_chunks[:plafond_sem]:
                # CLÉ = TEXTE ENTIER (2026-07-27). Elle valait `texte[:100]`, approximation
                # devenue destructrice depuis que le chemin de section préfixe les chunks :
                # les 4 tranches de revenu BNI commencent toutes par les mêmes 100 caractères
                # (« GESTION DE COMPTE > Conditions débitrices et frais > Frais de tenue de
                # compte (tarif mensuel) > Reven|u... ») — le dédoublonnage n'en gardait donc
                # qu'UNE et supprimait silencieusement les 3 autres. Symptôme côté utilisateur :
                # « les frais sont de 1 000 FCFA », faux, au lieu des 4 tranches. Deux lignes ne
                # sont identiques que si leur texte l'est ENTIÈREMENT.
                key = c["texte"]
                if key not in seen:
                    seen.add(key)
                    chunks.append(c)

            if chunks:
                label = (f"sémantique k={plafond_sem}"
                         + (f" + keyword '{terme_service}'" if terme_service else ""))
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
