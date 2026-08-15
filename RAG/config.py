"""
CONFIGURATION GLOBALE — LIT DEPUIS .env
=========================================
Source unique de vérité pour le RAG.
Tous les autres modules importent ce fichier.
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

_env = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env)

# ── PostgreSQL ────────────────────────────────────────────────────────────────
# DATABASE_URL D'ABORD (2026-08-09, pour l'hébergement). Render et Supabase ne fournissent pas
# cinq variables mais une seule chaîne de connexion. Sans elle, le moteur de recherche déployé
# viserait « localhost » — où il n'y a pas de base — et le chat répondrait « aucun résultat »
# à toutes les questions, sans qu'aucune erreur ne le signale.
def _params_bd():
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return {
            "host"    : os.getenv("DB_HOST",     "localhost"),
            "port"    : int(os.getenv("DB_PORT", 5432)),
            "dbname"  : os.getenv("DB_NAME",     "intelligence_bancaire"),
            "user"    : os.getenv("DB_USER",     "postgres"),
            "password": os.getenv("DB_PASSWORD", ""),
        }
    from urllib.parse import unquote, urlparse
    u = urlparse(url)
    p = {
        "host"    : u.hostname or "localhost",
        "port"    : int(u.port or 5432),
        "dbname"  : (u.path or "/postgres").lstrip("/") or "postgres",
        "user"    : unquote(u.username or "postgres"),
        # Décodage indispensable : un « @ » ou un « / » dans le mot de passe est encodé dans
        # l'URL, et le passer tel quel produit un refus d'authentification inexplicable.
        "password": unquote(u.password or ""),
    }
    if p["host"] not in ("localhost", "127.0.0.1"):
        p["sslmode"] = "require"     # le mot de passe traverse l'internet public
    return p


DB_PARAMS = _params_bd()

# ── LLM — Gemini (principal) + Groq (backup) ─────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Le nom du modèle se PÉRIME. « gemini-2.0-flash » a été retiré par Google sans préavis
# utilisable : l'appel rend un 404 « This model is no longer available », et le chat meurt
# entier sur une ligne de configuration. On le rend donc réglable sans toucher au code, et
# l'on note comment retrouver la liste du jour :
#     https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

GROQ_MODEL   = "llama-3.3-70b-versatile"  # remis au modèle prévu le 2026-07-22 (le "demain" annoncé dans ce commentaire n'a jamais été fait — le chat tournait sur le petit 8b depuis)

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

# Vue LARGE sur la réglementation, pour une question générale qui ne vise ni une banque ni
# une période. Ce n'est plus la table entière : découpée par article, elle pèse 264 000
# caractères pour un contexte de 9 000.
#
# Six et non vingt-cinq : chaque article occupe désormais sa propre section, et le budget se
# partage entre elles. À vingt-cinq, chacune tombait à 360 caractères — un article coupé au
# tiers, dont le modèle ne pouvait citer que le début. Peu de sources bien servies valent
# mieux que beaucoup de sources amputées : mieux vaut six articles entiers que vingt-cinq
# débuts d'articles. Mesuré sur les huit questions réglementaires, le bon texte n'est jamais
# descendu au-delà du troisième rang — les rangs 7 à 25 ne servaient qu'à réduire la part
# des six premiers.
#
# Le chiffre suit le budget, il n'a pas de valeur en soi. Six articles sont ce que 9 000
# caractères peuvent servir entiers ; avec Gemini le budget passe à 200 000 et cette
# contrainte disparaît — s'y tenir reviendrait alors à s'interdire des textes pertinents
# pour une raison qui n'existe plus.
REGL_K_LARGE = 25 if LLM_PROVIDER == "gemini" else 6
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
#
# LE PLAFOND SUIT LE FOURNISSEUR (2026-08-15). 1 500 jetons est la contrainte de Groq, dont
# le budget par minute compte l'entrée ET la sortie RÉSERVÉE. Gemini n'a pas cette contrainte
# et accepte 65 536 jetons de sortie. Garder 1 500 avec Gemini coupait les réponses EN PLEIN
# MOT : la question « la SGCI est-elle plus chère que ses concurrents, et que prévoit la
# BCEAO ? » s'arrêtait sur « … et du Relevé ré », juste avant la citation réglementaire.
# 4 000 jetons laissent environ 12 000 caractères — largement de quoi conclure — sans partir
# dans des réponses interminables sur un écran de démonstration.
LLM_MAX_TOKENS_GROQ = 1500
# 2 500 et non 4 000 : une reponse de 400 mots pese environ 600 jetons, le plafond n'est
# donc jamais atteint et ne coupe plus rien. Il ne sert que de garde-fou si le modele
# s'emballe malgre la consigne de longueur.
LLM_MAX_TOKENS  = 2500 if LLM_PROVIDER == "gemini" else LLM_MAX_TOKENS_GROQ
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
# Chargé DEPUIS la table `banques` (source faisant autorité, utilisée aussi pour la
# contrainte FK à l'ingestion d'une nouvelle banque) plutôt qu'une liste figée en dur —
# trouvé le 2026-07-11 : le dashboard (dash_app/db.py, BANKS) est déjà dynamique et se
# recharge automatiquement après un ajout de données (refresh_banks()), mais CETTE liste
# ne l'était pas → une banque ajoutée via « Ajouter des données » n'apparaissait PAS
# automatiquement dans les comparaisons du chat (ROE, PNB, CB...) tant que ce fichier
# n'était pas édité à la main. Liste figée ci-dessous gardée UNIQUEMENT comme filet de
# sécurité si la base est indisponible au démarrage.
def _charger_banques_officielles():
    try:
        cx = psycopg2.connect(**DB_PARAMS)
        cur = cx.cursor()
        cur.execute("SELECT code FROM banques ORDER BY code")
        codes = [r[0] for r in cur.fetchall()]
        cur.close(); cx.close()
        if codes:
            return codes
    except Exception as e:
        print(f"[config] liste banques dynamique indisponible → filet de sécurité ({e})")
    return ["BACI", "BICICI", "BNI", "ECOBANK", "NSIA", "SIB", "SGCI"]


BANQUES_OFFICIELLES = _charger_banques_officielles()


def refresh_banques_officielles():
    """Recharge BANQUES_OFFICIELLES EN PLACE (mutation, pas réaffectation) — les modules qui
    ont fait `BANQUES = config.BANQUES_OFFICIELLES` (ex. structured_tools.py) pointent vers
    le MÊME objet liste et voient donc la mise à jour immédiatement, sans réimport ni
    redémarrage du process. Même principe que dash_app/db.py:refresh_banks() (`BANKS[:] = fresh`).
    Appelé automatiquement par server.py juste après un ajout de données réussi — pour que
    le chat, en production/déployé, n'ait JAMAIS besoin d'un redémarrage manuel du process
    pour voir apparaître une nouvelle banque dans ses comparaisons."""
    BANQUES_OFFICIELLES[:] = _charger_banques_officielles()
    return list(BANQUES_OFFICIELLES)


BANQUE_PRINCIPALE   = "SGCI"
BANQUES_CONSOLIDEES = {"BACI", "BNI"}   # EF consolidé multi-années, pas de filtre par annee

# ── Années disponibles EF par banque ─────────────────────────────────────────
# Chargé DEPUIS `ef_indicateurs` (même principe que BANQUES_OFFICIELLES ci-dessus) plutôt
# qu'une liste figée en dur — sinon une année ajoutée pour une banque (ex. SGCI 2026) ne
# serait jamais vue par check_disponibilite_ef(), qui continuerait de dire « dernière année
# disponible : 2025 ». Filet de sécurité (dernières valeurs connues) si la base est
# indisponible au démarrage.
def _charger_annees_ef():
    try:
        cx = psycopg2.connect(**DB_PARAMS)
        cur = cx.cursor()
        cur.execute("SELECT DISTINCT banque, annee_donnee FROM ef_indicateurs "
                    "WHERE is_primary=TRUE ORDER BY banque, annee_donnee")
        rows = cur.fetchall()
        cur.close(); cx.close()
        if rows:
            out = {}
            for b, a in rows:
                out.setdefault(b, []).append(a)
            return out
    except Exception as e:
        print(f"[config] années EF dynamiques indisponibles → filet de sécurité ({e})")
    return {
        "SGCI"    : [2023, 2024, 2025],
        "BICICI"  : [2023, 2024, 2025],
        "ECOBANK" : [2023, 2024, 2025],
        "NSIA"    : [2022, 2023, 2024],
        "SIB"     : [2022, 2023, 2024],
        "BACI"    : [2021, 2022, 2023],
        "BNI"     : [2021, 2022, 2023],
    }


ETATS_FINANCIERS_ANNEES = _charger_annees_ef()


def refresh_etats_financiers_annees():
    """Recharge ETATS_FINANCIERS_ANNEES EN PLACE (clear+update, pas réaffectation) — même
    principe que refresh_banques_officielles() : retriever.py fait
    `ETATS_FINANCIERS_ANNEES = config.ETATS_FINANCIERS_ANNEES` (même objet dict), donc la
    mise à jour est visible immédiatement, sans redémarrage. Appelé automatiquement par
    server.py juste après un ajout de données réussi."""
    fresh = _charger_annees_ef()
    ETATS_FINANCIERS_ANNEES.clear()
    ETATS_FINANCIERS_ANNEES.update(fresh)
    return dict(ETATS_FINANCIERS_ANNEES)

CONDITIONS_ANNEES = [2024, 2025, 2026]

# ── Aliases banques (détection dans les questions) ────────────────────────────
# PROBLÈME TROUVÉ (audit du 2026-07-12) : contrairement à BANQUES_OFFICIELLES et
# ETATS_FINANCIERS_ANNEES ci-dessus, ce dict était 100% figé et JAMAIS rafraîchi après un
# ajout de données. Conséquence concrète : une 8e banque ajoutée via « Ajouter des données »
# apparaît bien dans les comparaisons globales (BANQUES_OFFICIELLES), mais retriever.py::
# detect_banques() ne reconnaît AUCUN de ses noms dans une question du chat (« Quels sont
# les frais chez X ? ») tant que ce dict n'est pas mis à jour — le chat ne peut alors ni la
# citer, ni filtrer sur elle, ni résoudre une question de suivi. Corrigé : les alias courts/
# idiomatiques historiques (non déductibles automatiquement, ex. « sg », « atlantique »)
# restent curatés à la main ci-dessous, mais on complète TOUJOURS avec au minimum le code et
# le nom complet (en minuscules) de CHAQUE banque de la table `banques` — une banque toute
# juste ajoutée est donc reconnaissable via son code dès l'ajout, même sans alias court dédié.
_BANQUE_ALIASES_CURATED = {
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


def _construire_aliases_banques():
    aliases = dict(_BANQUE_ALIASES_CURATED)
    try:
        cx = psycopg2.connect(**DB_PARAMS)
        cur = cx.cursor()
        cur.execute("SELECT code, nom_complet FROM banques")
        for code, nom in cur.fetchall():
            if code:
                aliases.setdefault(code.lower(), code)
            if nom:
                aliases.setdefault(nom.lower(), code)
        cur.close(); cx.close()
    except Exception as e:
        print(f"[config] alias banques dynamiques indisponibles → alias curatés seuls ({e})")
    return aliases


BANQUE_ALIASES = _construire_aliases_banques()


def refresh_banque_aliases():
    """Recharge BANQUE_ALIASES EN PLACE (clear+update) — même principe que
    refresh_banques_officielles()/refresh_etats_financiers_annees() : retriever.py fait
    `BANQUE_ALIASES = config.BANQUE_ALIASES` (même objet dict), donc la mise à jour est
    visible immédiatement, sans redémarrage. Appelé automatiquement par server.py juste
    après un ajout de données réussi."""
    fresh = _construire_aliases_banques()
    BANQUE_ALIASES.clear()
    BANQUE_ALIASES.update(fresh)
    return dict(BANQUE_ALIASES)

# ── Mots-clés routing par domaine ─────────────────────────────────────────────
# Cette liste ne nommait que les CONTENANTS du droit — « loi », « décret », « article » —
# et aucune des NOTIONS qu'il porte. « Quel est le taux de l'usure applicable aux banques ? »
# n'y déclenchait rien, tandis que « taux » la rangeait dans les conditions tarifaires : la
# question partait au mauvais agent et le chat répondait « non disponible dans le document »
# alors que la décision de l'UMOA était en base. Or personne ne demande « que dit l'article
# 8 » : on demande l'usure, la gratuité, le plafond.
#
# Les mots ajoutés ont été comptés dans les deux corpus avant d'être retenus. « avis »,
# « décision » et « norme » ont été écartés malgré leur présence : trop courants en français
# ordinaire, ils réveilleraient l'agent à tout propos. Les formes fléchies sont écrites une
# à une, `_contient_mot` posant une frontière de mot : « gratuit » ne couvre pas « gratuité ».
MOTS_REGLEMENTATION = [
    "loi", "juridique", "légal", "legal",
    "réglementation", "reglementation", "article", "décret", "decret",
    "bceao", "umoa", "uemoa", "instruction", "circulaire", "disposition",
    "conformité", "conformite", "obligation légale", "texte réglementaire",

    # Notions réellement portées par les textes
    "usure", "usuraire", "taux d'usure", "taux de l'usure",
    "gratuit", "gratuits", "gratuite", "gratuites", "gratuité", "gratuite",
    "plafond", "plafonné", "plafonnement",
    "obligatoire", "obligatoires", "obligation", "obligations",
    "réglementaire", "reglementaire", "réglementaires", "reglementaires",
    "agrément", "agrement", "sanction", "sanctions", "amende",
    "banque centrale", "conseil des ministres",
    "établissement de crédit", "etablissement de credit",
    "systèmes financiers décentralisés", "systemes financiers decentralises",
    "consommateur", "consommateurs",
    "interdiction", "interdit", "interdite", "dérogation", "derogation",
    "infraction", "prescrit",
    # Les formes verbales autant que les substantifs : `_contient_mot` pose une frontière de
    # mot, « publication » ne couvre donc pas « publier ». « Une banque doit-elle publier ses
    # conditions tarifaires ? » partait ainsi chez l'agent tarifaire, qui a répondu de
    # mémoire — « conformément à la réglementation de la BCEAO » — sans citer aucun texte.
    # Une réponse juste mais non sourcée est un faux positif : c'est le modèle qui parle.
    "affichage", "afficher", "affiché", "affichées",
    "publication", "publier", "publié", "publiée", "publiées", "publient",
    # Vocabulaire du délai réglementaire. « Quel délai avant l'entrée en vigueur d'une
    # nouvelle tarification ? » ne réveillait aucun agent réglementaire : « délai » et
    # « tarification » appartiennent au tarifaire. « Entrée en vigueur » et « préavis », eux,
    # ne se disent pas d'autre chose que d'un texte.
    "entrée en vigueur", "entree en vigueur", "préavis", "preavis",
    # Demander si un service est facturé, c'est demander s'il figure sur la liste des
    # services que la BCEAO impose de rendre gratuits. La question paraît tarifaire ; sa
    # réponse est d'abord réglementaire, et le tarif ne vient qu'ensuite. Les deux agents
    # répondent alors ensemble, ce qui est exactement le cas d'usage de l'application.
    "facturation", "facturé", "facturée", "facturer", "facturés",
    # Absente du texte, qui dit « conditions de banque », mais c'est le mot de
    # l'utilisateur : l'aiguillage suit la question, la recherche suit le texte.
    "transparence", "transparence tarifaire",
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
    # « Facturer » est un mot de TARIF autant qu'un mot de droit. Il figure aussi dans
    # MOTS_REGLEMENTATION, et c'est voulu : « quels services la BCEAO impose-t-elle de rendre
    # gratuits, et les banques les FACTURENT-elles ? » appelle les deux agents. Il n'y était
    # que du côté réglementaire, si bien que la question recevait une réponse juridique
    # impeccable et pas un seul tarif — la moitié de la question restait sans réponse.
    "facturation", "facturé", "facturée", "facturés", "facturent", "facture", "facturer",
    "gratuit", "gratuits", "gratuite", "gratuites", "gratuité", "payant", "payante",
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
