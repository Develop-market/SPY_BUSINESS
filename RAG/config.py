"""
CONFIGURATION GLOBALE — LIT DEPUIS .env
=========================================
Source unique de vérité pour le RAG.
Tous les autres modules importent ce fichier.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

_env = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env)

# ── PostgreSQL ────────────────────────────────────────────────────────────────
DB_PARAMS = {
    "host"    : os.getenv("DB_HOST",     "localhost"),
    "port"    : int(os.getenv("DB_PORT", 5432)),
    "dbname"  : os.getenv("DB_NAME",     "intelligence_bancaire"),
    "user"    : os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# ── LLM — Gemini (principal) + Groq (backup) ─────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-2.0-flash"

GROQ_MODEL   = "llama-3.1-8b-instant"  # 70b quotas épuisés — repasser à llama-3.3-70b-versatile demain

# Toutes les clés Groq — rotation automatique sur quota épuisé (journalier OU budget par
# minute plein). Seules 4 clés sur les 12 disponibles dans .env étaient utilisées ici,
# limitant fortement la marge de manœuvre de la rotation en cas de 413/429.
GROQ_API_KEYS = [k for k in [os.getenv(f"GROQ_API_KEY{('_'+str(i)) if i>1 else ''}", "") for i in range(1, 13)] if k]
GROQ_API_KEY = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""

# LLM actif : "gemini" ou "groq"  (Gemini nécessite activation billing Google)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")

# ── Embedding (local — 768 dims, déjà vectorisé dans PostgreSQL) ──────────────
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
EMBEDDING_DIMS  = 768

# ── Paramètres retrieval ──────────────────────────────────────────────────────
RETRIEVER_K          = 6     # recherche sémantique générale (réduit pour les limites token llama-8b)
SIMILARITY_THRESHOLD = 0.30  # cosine similarity minimum (scores moyens : 0.68-0.71)
MAX_CHUNKS_GLOBAL    = 900   # au-delà → sémantique par banque
MAX_CHUNKS_BANQUE    = 950   # au-delà pour 1 banque → sémantique k=100

# ── Paramètres LLM ────────────────────────────────────────────────────────────
LLM_TEMPERATURE_FACTUEL    = 0.1   # CB + EF — précision max, zéro invention
LLM_TEMPERATURE_ANALYTIQUE = 0.7   # Multi + REGL + recommandations

# Groq free tier : 6000 TPM = INPUT + MAX_OUTPUT_TOKENS DEMANDÉ (Groq compte le budget de
# sortie réservé, pas seulement ce qui est réellement généré). Mesuré en direct après la
# vectorisation CB/EF (système prompt réel + contexte ≈ 4200 tok, bien au-dessus des 3100
# estimés dans le commentaire d'origine) : Requested 6207 pour Limit 6000. Les prompts de
# comparaison/analyse (niveau 3, plusieurs banques) ont un système prompt plus long que le
# prompt factuel simple → budget contexte réduit spécifiquement pour ce cas (voir
# MAX_CONTEXT_CHARS_COMPARAISON) plutôt que de pénaliser toutes les questions ici.
LLM_MAX_TOKENS  = 1500
SHOW_QUERY_DEBUG = os.getenv("SHOW_QUERY_DEBUG", "True").lower() == "true"

# Gemini 1M tokens → on envoie TOUT sans troncature (~200k chars).
# Groq (fournisseur actif par défaut, 6000 TPM INPUT+OUTPUT) : budget plus petit, mais le
# garde-fou RÉEL (chain.py, section 8b) mesure désormais la taille EXACTE du prompt assemblé
# (système + contexte + question) juste avant l'envoi et retronque si besoin — ces deux
# constantes ne sont donc plus qu'un PREMIER filtre grossier (évite de formatter un contexte
# énorme pour rien), pas plus. Elles peuvent être généreuses : au départ fixées à 5000/1500
# par précaution avant que 8b existe, ce qui étranglait à outrance les réponses (ex. "frais de
# virement SGCI" répondait "non disponible" alors que la donnée EXISTE — juste écartée par la
# troncature agressive) → relevées à 9000/6000, le garde-fou 8b reste le filet de sécurité final.
MAX_CONTEXT_CHARS = 200000 if LLM_PROVIDER == "gemini" else 9000
# Comparaisons multi-banques (7 banques × plusieurs domaines) : système prompt plus long
# que le prompt factuel simple → budget contexte plus serré pour ce cas précis uniquement
# (voir chain.py, branche "comparaison"), sans pénaliser les questions simples ci-dessus.
MAX_CONTEXT_CHARS_COMPARAISON = 200000 if LLM_PROVIDER == "gemini" else 6000

# ── Mémoire conversationnelle ─────────────────────────────────────────────────
MEMORY_MAX_TURNS = 5

# ── Référentiel banques ───────────────────────────────────────────────────────
BANQUES_OFFICIELLES = ["BACI", "BICICI", "BNI", "ECOBANK", "NSIA", "SIB", "SGCI"]
BANQUE_PRINCIPALE   = "SGCI"
BANQUES_CONSOLIDEES = {"BACI", "BNI"}   # EF consolidé multi-années, pas de filtre par annee

# ── Années disponibles EF par banque ─────────────────────────────────────────
ETATS_FINANCIERS_ANNEES = {
    "SGCI"    : [2023, 2024, 2025],
    "BICICI"  : [2023, 2024, 2025],
    "ECOBANK" : [2023, 2024, 2025],
    "NSIA"    : [2022, 2023, 2024],
    "SIB"     : [2022, 2023, 2024],
    "BACI"    : [2021, 2022, 2023],
    "BNI"     : [2021, 2022, 2023],
}

CONDITIONS_ANNEES = [2024, 2025, 2026]

# ── Aliases banques (détection dans les questions) ────────────────────────────
BANQUE_ALIASES = {
    "sgci"              : "SGCI",
    "société générale"  : "SGCI",
    "societe generale"  : "SGCI",
    "sg"                : "SGCI",
    "baci"              : "BACI",
    "banque atlantique" : "BACI",
    "atlantique"        : "BACI",
    "bicici"            : "BICICI",
    "bni"               : "BNI",
    "banque nationale"  : "BNI",
    "ecobank"           : "ECOBANK",
    "eco bank"          : "ECOBANK",
    "nsia"              : "NSIA",
    "sib"               : "SIB",
    "société ivoirienne": "SIB",
    "societe ivoirienne": "SIB",
}

# ── Mots-clés routing par domaine ─────────────────────────────────────────────
MOTS_REGLEMENTATION = [
    "loi", "juridique", "légal", "legal",
    "réglementation", "reglementation", "article", "décret", "decret",
    "bceao", "umoa", "uemoa", "instruction", "circulaire", "disposition",
    "conformité", "conformite", "obligation légale", "texte réglementaire",
]

MOTS_EF = [
    "résultat", "resultat", "bilan", "financier",
    "performance", "rentabilité", "rentabilite", "rentable",
    "pnb", "produit net bancaire",
    "actif", "passif", "fonds propres",
    "bénéfice", "benefice", "profit",
    "position financiere", "classement financier", "classement des banques",
    "solidite", "solidité", "solvabilite", "solvabilité",
    "la plus solide", "la plus performante", "la plus rentable",
    "roe", "roa", "ratio", "marge nette",
    "total bilan", "capitaux propres", "coefficient",
    "croissance", "expansion", "solidité financière", "plus fiable",
]

MOTS_CONDITIONS = [
    "frais", "tarif", "taux", "commission",
    "conditions", "coût", "cout", "tenue de compte",
    "virement", "tbb", "taux de base",
    "chere", "cher", "chère", "moins cher", "plus cher",
    "carte", "chequier", "retrait", "ouverture", "domiciliation",
    "cotisation", "abonnement", "grille tarifaire",
    "frais de dossier", "commission de mouvement", "agios",
    "pme", "entreprise", "avantage", "avantageuse", "exportat",
    "import", "international", "change", "devises",
    "quelle banque", "meilleure banque", "choisir", "recommande",
]


def verify_config() -> bool:
    errors = []
    if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY manquante dans .env")
    if LLM_PROVIDER == "groq" and not GROQ_API_KEY:
        errors.append("GROQ_API_KEY manquante dans .env")
    if not DB_PARAMS["password"]:
        errors.append("DB_PASSWORD manquant dans .env")
    if errors:
        for e in errors:
            print(f"[ERREUR CONFIG] {e}")
        return False
    llm_info = f"{LLM_PROVIDER}={GEMINI_MODEL if LLM_PROVIDER == 'gemini' else GROQ_MODEL}"
    print(f"[CONFIG OK] {llm_info} | DB={DB_PARAMS['dbname']}@{DB_PARAMS['host']} | Embed=mpnet-768")
    return True


if __name__ == "__main__":
    verify_config()
