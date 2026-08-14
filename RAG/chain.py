"""
chain.py — Orchestration RAG multi-agents
==========================================
Architecture :
  Question → Routeur detect_types_doc() [multi-label]
           → Retrieval PARALLÈLE par agent spécialisé (ThreadPool)
           → Fusion contextes sectionnés par domaine
           → Prompt adaptatif selon agents actifs
           → Gemini 2.0 Flash → Réponse

Agents spécialisés :
  - Agent Conditions Tarifaires  → conditions_banque
  - Agent États Financiers       → etats_financiers
  - Agent Réglementation         → reglementation

Niveaux de confiance :
  1 = Factuel       — 1 domaine, données directes
  2 = Analytique    — 2+ domaines ou comparaison cross-banques
  3 = Prospectif    — recommandation, ancrage réglementaire obligatoire
  4 = Insuffisant   — données absentes, refus propre
"""

import sys
import os
import re
import time
import importlib
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

config    = importlib.import_module("config")
retriever = importlib.import_module("retriever")
prompts   = importlib.import_module("prompts")
memory    = importlib.import_module("memory")
structured_tools = importlib.import_module("structured_tools")   # comparaison structurée SQL
agent_tools      = importlib.import_module("agent_tools")        # outils LangChain (agent de secours)
fiche_marche     = importlib.import_module("fiche_marche")       # socle de faits permanent (2026-07-27)


# ═══════════════════════════════════════════════════════════
#  NORMALISATION DES QUESTIONS — TOLÉRANCE AUX FAUTES DE FRAPPE
# ═══════════════════════════════════════════════════════════
# AJOUTÉ le 2026-07-27 après un test en direct du directeur : « JE VEUX SAVOIR QELLE ST LA
# MEILLEUR BANQU » a produit une réponse absurde sur les prêts subordonnés de la BICICI.
# Cause : TOUT le routage du chat compare des chaînes EXACTES (`"banque" in q`,
# `"meilleure banque" in q`...). Or « BANQU » ne contient pas « banque », « MEILLEUR » (sans e)
# ne contient pas « meilleure banque », « QELLE » ne contient pas « quelle ». Les 4 détecteurs
# déterministes ratent, is_comparaison/is_recommandation renvoient False — donc même l'agent de
# secours n'est jamais tenté — et la question finit dans le RAG générique, qui cherche
# sémantiquement une phrase pleine de fautes et remonte n'importe quel libellé de bilan.
#
# Un dirigeant tape vite, en majuscules, sans accents, avec des fautes. Le chat doit être
# robuste à ça : c'est la différence entre un outil utilisable et un outil « pas flexible ».
# Principe retenu : on ne corrige pas l'orthographe (illusoire), on compare sur des RACINES
# ("banqu" plutôt que "banque") et on normalise accents/casse avant tout test.
_ACCENTS = str.maketrans("àâäáãçéèêëíìîïñóòôöõúùûüýÿ", "aaaaaceeeeiiiinooooouuuuyy")


def _normaliser(question: str) -> str:
    """Minuscules + accents retirés + espaces normalisés. Base de tous les tests tolérants."""
    q = (question or "").lower().translate(_ACCENTS)
    return re.sub(r"\s+", " ", q).strip()


def _contient_racine(question: str, racines) -> bool:
    """Teste des RACINES de mots (ex. "banqu" attrape banque/banques/BANQU/banqu'). Volontairement
    en sous-chaîne et non en mot entier : c'est précisément la troncature et la faute de frappe
    qu'on veut rattraper. Les racines doivent donc être choisies assez longues pour ne pas
    produire de faux positifs (cf. la leçon de _contient_mot : "ratio" matchait
    "opérationnellement" — ici on utiliserait "ratio de" ou une racine plus spécifique)."""
    q = _normaliser(question)
    return any(r in q for r in racines)

_AGENT_LABELS = {
    "conditions_banque": "AGENT CONDITIONS TARIFAIRES",
    "etats_financiers" : "AGENT ÉTATS FINANCIERS",
    "reglementation"   : "AGENT RÉGLEMENTATION",
}

# ═══════════════════════════════════════════════════════════
#  INITIALISATION LLM — GEMINI (principal) + GROQ (backup)
# ═══════════════════════════════════════════════════════════

def _creer_llm(temperature: float = None):
    """Crée le LLM selon LLM_PROVIDER dans config."""
    temp = temperature if temperature is not None else config.LLM_TEMPERATURE_ANALYTIQUE

    if config.LLM_PROVIDER == "groq":
        try:
            from langchain_groq import ChatGroq
            return ChatGroq(
                model       = config.GROQ_MODEL,
                groq_api_key = config.GROQ_API_KEY,
                temperature  = temp,
                max_tokens   = config.LLM_MAX_TOKENS,
            )
        except ImportError:
            print("[WARN] langchain-groq non installé — bascule sur Gemini")

    return _creer_llm_gemini(temp)


def _creer_llm_gemini(temp: float):
    """Construit le modèle Gemini, RAISONNEMENT COUPÉ.

    Les modèles Gemini récents « réfléchissent » avant de répondre, et ce raisonnement se
    paie sur le MÊME budget de sortie que la réponse. Mesuré ici : sur 1 496 jetons produits,
    1 388 partaient en raisonnement et il en restait 108 pour la réponse — coupée en plein
    mot, comme l'a montré la question sur le taux de l'usure. Budget de raisonnement à zéro :
    la même réponse passe de 401 à 872 caractères, entière, et de 8,7 s à 2,8 s.

    Ce n'est pas une économie au détriment de la qualité, c'est le principe du projet appliqué
    au modèle : le déterministe établit, le LLM formule. Les montants, les rangs et les écarts
    sont déjà calculés en SQL et fournis dans le contexte ; faire raisonner le modèle sur des
    faits qu'on lui impose ne peut rien améliorer, seulement lui laisser moins de place pour
    les écrire.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI
    commun = dict(model=config.GEMINI_MODEL, google_api_key=config.GEMINI_API_KEY,
                  temperature=temp, max_output_tokens=config.LLM_MAX_TOKENS)
    try:
        return ChatGoogleGenerativeAI(thinking_budget=0, **commun)
    except Exception as e:
        # Tous les modèles n'acceptent pas ce réglage : mieux vaut un modèle bavard qu'aucun.
        print(f"  [GEMINI] raisonnement non réglable ({str(e)[:70]}) — réponses plus longues à venir")
        return ChatGoogleGenerativeAI(**commun)


# Singletons LLM (initialisés au premier appel)
_LLM_FACTUEL    = None
_LLM_ANALYTIQUE = None


def _get_llm(types_actifs: list):
    """
    Retourne le LLM adapté :
    - CB + EF seuls → température 0.1 (précision, zéro invention)
    - Multi / REGL / niveau 3 → température analytique (synthèse)
    """
    global _LLM_FACTUEL, _LLM_ANALYTIQUE
    agents_factuels = {"conditions_banque", "etats_financiers"}
    est_factuel = all(t in agents_factuels for t in types_actifs) and len(types_actifs) >= 1

    if est_factuel:
        if _LLM_FACTUEL is None:
            _LLM_FACTUEL = _creer_llm(temperature=config.LLM_TEMPERATURE_FACTUEL)
        return _LLM_FACTUEL
    else:
        if _LLM_ANALYTIQUE is None:
            _LLM_ANALYTIQUE = _creer_llm(temperature=config.LLM_TEMPERATURE_ANALYTIQUE)
        return _LLM_ANALYTIQUE


# ═══════════════════════════════════════════════════════════
#  INITIALISATION
# ═══════════════════════════════════════════════════════════

def init_chain() -> dict:
    """Initialise le RAG complet (vectorstore + mémoire)."""
    if not config.verify_config():
        raise RuntimeError("Configuration invalide — vérifier .env")
    print(f"Initialisation RAG SpyBusiness ({config.LLM_PROVIDER})...")
    vectorstore = retriever.init_retriever()
    mem         = memory.ConversationMemory()
    print(f"RAG prêt — {config.GEMINI_MODEL if config.LLM_PROVIDER == 'gemini' else config.GROQ_MODEL}")
    return {"vectorstore": vectorstore, "memory": mem}


init_agents = init_chain  # alias de compatibilité


# ═══════════════════════════════════════════════════════════
#  GARDE-FOU ANTI-INVENTION — CHAT LIBRE (audit 2026-07-25)
# ═══════════════════════════════════════════════════════════
# Trouvé lors de l'audit du chat : ce garde-fou existait déjà pour les analyses Stratégie/CB
# (server.py::_chiffres_inventes) mais PAS pour le chat libre (_executer ci-dessous) — c'est
# pourtant l'endroit le plus ouvert, donc le plus exposé. Reproduit ici en local (pas d'import
# croisé RAG↔server, RAG doit rester un module autonome) avec la MÊME logique : comparer les
# grands nombres (≥1000, montants FCFA) de la réponse à ceux réellement présents dans le
# contexte fourni. LEÇON du 2026-07-22 (retenue) : un blocage DUR sur le prompt EF complexe à 15
# blocs avait fait échouer TOUTE la génération (trop de faux positifs sur des chiffres dérivés
# légitimes, ex. "+12%" calculé à partir de 2 valeurs du contexte). Ici : on RETENTE une fois,
# et si ça persiste, on n'écrase PAS la réponse (elle reste utile) — on se contente d'un log
# serveur pour garder une trace, plutôt qu'un chat qui se met à répondre vide.
# Un nombre avec séparateurs de milliers (groupes de 3 chiffres séparés par espace, espace
# insécable ou POINT), sinon un entier nu. Le point n'est reconnu comme séparateur que devant
# exactement 3 chiffres — « 38.5 » (décimal) n'est donc pas transformé en 385.
_RE_NOMBRE = re.compile(r"\d{1,3}(?:[  .]\d{3})+|\d+")


def _grands_nombres_chat(text):
    """FAUX POSITIF CORRIGÉ le 2026-07-27 (vu dans la batterie de test) : l'ancienne regex
    `[\\d\\s]*\\d` ne connaissait que l'espace comme séparateur de milliers. Les grilles
    tarifaires écrivent « 200.000 » avec un POINT : le contexte donnait donc {200, 0} tandis
    que la réponse, qui écrit « 200 000 », donnait {200000} — un « chiffre inventé » signalé
    à tort sur une valeur pourtant recopiée du contexte. Chaque faux positif déclenchait une
    régénération complète inutile (latence doublée et quota Groq gaspillé, sur un budget déjà
    le facteur limitant)."""
    out = set()
    for m in _RE_NOMBRE.finditer(text or ""):
        raw = re.sub(r"[  .]", "", m.group(0))
        # Exclut les années calendaires (2000-2099) : toujours sûr de les répéter (elles
        # viennent de la question elle-même), les traiter comme un "chiffre inventé" ne fait
        # que déclencher des faux positifs — trouvé en testant (2026-07-25).
        if raw.isdigit() and int(raw) >= 1000 and not (len(raw) == 4 and raw.startswith("20")):
            out.add(int(raw))
    return out


def _chiffres_inventes_chat(reponse, contexte):
    return _grands_nombres_chat(reponse) - _grands_nombres_chat(contexte)


# ═══════════════════════════════════════════════════════════
#  RETRY AVEC BACKOFF EXPONENTIEL
# ═══════════════════════════════════════════════════════════

_groq_key_index = 0  # index courant dans la rotation des clés

def _autre_fournisseur_dispo() -> bool:
    """L'autre fournisseur a-t-il une clé ? Sans clé, annoncer une bascule serait mentir."""
    if config.LLM_PROVIDER == "groq":
        return bool(config.GEMINI_API_KEY)
    return bool(config.GROQ_API_KEY or config.GROQ_API_KEYS)


def _adapter_messages(messages, budget: int):
    """Ramène le contexte au budget de l'autre fournisseur.

    Le contexte est assemblé AVANT l'appel, à la taille du fournisseur en cours : 200 000
    caractères pour Gemini, 9 000 pour Groq. Basculer de Gemini vers Groq avec le contexte
    d'origine reviendrait à remplacer une panne de quota par un refus pour requête trop
    grosse — la bascule échouerait toujours, et donnerait l'illusion d'un filet qui n'attrape
    rien. On réduit donc le message porteur du contexte, avec le même partage sans gaspillage
    qu'ailleurs.
    """
    adaptes, change = [], False
    for m in messages:
        contenu = getattr(m, "content", None)
        if contenu is None and isinstance(m, dict):
            contenu = m.get("content")
        role = getattr(m, "type", None) or (m.get("role") if isinstance(m, dict) else "")
        if role in ("human", "user") and isinstance(contenu, str) and len(contenu) > budget:
            court = _tronquer_equitablement(contenu, budget)
            print(f"  [BASCULE] contexte ramené de {len(contenu):,} à {len(court):,} caractères")
            change = True
            if isinstance(m, dict):
                adaptes.append({**m, "content": court})
            else:
                adaptes.append(m.model_copy(update={"content": court}))
            continue
        adaptes.append(m)
    return adaptes if change else messages


def _creer_llm_autre(temp: float):
    """Construit le modèle de l'AUTRE fournisseur, ou None si c'est impossible."""
    try:
        if config.LLM_PROVIDER == "groq":
            return _creer_llm_gemini(temp)
        from langchain_groq import ChatGroq
        cle = (config.GROQ_API_KEYS or [config.GROQ_API_KEY])[0]
        return ChatGroq(model=config.GROQ_MODEL, groq_api_key=cle,
                        temperature=temp, max_tokens=config.LLM_MAX_TOKENS)
    except Exception as e:
        print(f"  [BASCULE] impossible — {type(e).__name__} {str(e)[:80]}")
        return None


def _invoke_with_retry(llm, messages, max_retries: int = None) -> str:
    """
    Appelle le LLM avec retry et rotation des clés Groq sur quota épuisé.
    - 429 TPD (quota journalier épuisé) : bascule sur clé suivante automatiquement
    - 413 / "Request too large" (TPM d'UNE requête, budget par minute partagé entre TOUS
      les appels récents sur cette même clé) : bascule aussi sur clé suivante — une clé
      différente a son propre budget, donc quasi toujours disponible immédiatement, plus
      rapide et plus fiable qu'attendre sur la même clé.
    - 429 TPM générique (sans indication clé alternative utile) : attente 30s puis retry.
    """
    global _groq_key_index
    n_keys = len(config.GROQ_API_KEYS) if config.LLM_PROVIDER == "groq" else 1
    if max_retries is None:
        max_retries = max(4, n_keys * 2)

    current_llm = llm  # copie locale pour permettre la rotation
    rotations_413_de_suite = 0  # compteur pour détecter un cycle complet épuisé
    bascule_faite = False       # on ne change de fournisseur qu'une fois par question

    for attempt in range(max_retries):
        try:
            return _texte_reponse(current_llm.invoke(messages))
        except Exception as e:
            err = str(e)
            err_low     = err.lower()
            is_tpd      = "tokens per day" in err_low or "per day" in err_low
            is_413      = ("413" in err or "request too large" in err_low
                           or "rate_limit_exceeded" in err_low or "reduce your message size" in err_low)
            is_tpm      = ("429" in err or "rate limit" in err_low) and not is_tpd and not is_413
            is_resource = "RESOURCE_EXHAUSTED" in err or "resource_exhausted" in err_low
            # Erreurs réseau transitoires (timeout, connexion coupée) : ni quota ni taille de
            # requête — vues dans le stress-test (2/8 appels, sans lien avec le contexte ni la
            # clé). Un simple retry sur la même clé suffit presque toujours.
            is_connexion = ("connection" in err_low or "timeout" in err_low or "timed out" in err_low)
            is_indispo   = "503" in err or "unavailable" in err_low or "high demand" in err_low

            if attempt >= max_retries - 1:
                return f"Erreur après {max_retries} tentatives : {err[:150]}"

            # BASCULE DE FOURNISSEUR quand celui en cours est à sec. Les deux paliers gratuits
            # sont étroits, mais ils ne comptent pas la même chose : Groq alloue 100 000 jetons
            # par jour, Gemini 20 REQUÊTES par jour et par modèle. Aucun des deux ne tient une
            # séance de travail à lui seul ; ensemble ils la tiennent. L'un s'épuise, l'autre
            # prend la suite — une seule fois, pour ne pas faire l'aller-retour entre deux
            # fournisseurs tous deux vides.
            if (is_tpd or is_resource) and not bascule_faite and _autre_fournisseur_dispo():
                bascule_faite = True
                autre = "gemini" if config.LLM_PROVIDER == "groq" else "groq"
                print(f"  [BASCULE] {config.LLM_PROVIDER} épuisé → {autre}")
                remplacant = _creer_llm_autre(getattr(current_llm, "temperature", 0.3))
                if remplacant is not None:
                    current_llm = remplacant
                    if autre == "groq":
                        messages = _adapter_messages(messages,
                                                     config.MAX_CONTEXT_CHARS_COMPARAISON)
                    continue

            if (is_tpd or is_resource or is_413) and config.LLM_PROVIDER == "groq" and n_keys > 1:
                _groq_key_index = (_groq_key_index + 1) % n_keys
                new_key = config.GROQ_API_KEYS[_groq_key_index]
                motif = "413 (budget minute plein)" if is_413 else "TPD"
                print(f"  [ROTATION] {motif} → clé K{_groq_key_index+1}")
                from langchain_groq import ChatGroq
                temp = getattr(current_llm, 'temperature', 0.1)
                current_llm = ChatGroq(model=config.GROQ_MODEL, groq_api_key=new_key,
                                       temperature=temp, max_tokens=config.LLM_MAX_TOKENS)
                # Même contexte/taille qui réussit pour une question et échoue pour une
                # autre juste après (observé le 2026-07-11) : ce n'est pas la taille de LA
                # requête qui pose problème mais le budget PAR MINUTE, partagé entre tous
                # les appels récents — en cas d'appels rapprochés (plusieurs questions à la
                # suite), les 12 clés/orgs peuvent être simultanément proches de saturation.
                # Faire le tour des 12 sans jamais attendre ne laisse aucune chance à la
                # fenêtre de minute de se libérer → on marque une pause après un cycle
                # complet (12 rotations) pour laisser le quota se reconstituer.
                if is_413:
                    rotations_413_de_suite += 1
                    if rotations_413_de_suite > 0 and rotations_413_de_suite % n_keys == 0:
                        print(f"  [PAUSE] Cycle complet de {n_keys} clés épuisé — pause 20s...")
                        time.sleep(20)
            elif is_connexion:
                print(f"  [CONNEXION] Erreur transitoire, retry immédiat (tentative {attempt+1})...")
                time.sleep(2)
            elif is_413 or is_tpm:
                wait = 15 if is_413 else 30
                print(f"  [RATE LIMIT] Attente {wait}s (tentative {attempt+1})...")
                time.sleep(wait)
            elif is_indispo:
                # 503 « high demand » : ni quota ni taille, seulement un modèle très
                # sollicité à cet instant. Cette erreur tombait dans le « sinon » et rendait
                # une erreur définitive à l'utilisateur, alors qu'un simple essai un peu plus
                # tard passe. Constaté sur « une banque doit-elle publier ses conditions
                # tarifaires ? », question qui réussit à l'essai suivant.
                print(f"  [MODÈLE SATURÉ] 503 — nouvelle tentative dans 8s ({attempt+1})...")
                time.sleep(8)
            else:
                return f"Erreur : {err[:200]}"
    return "Erreur : nombre maximum de tentatives atteint."


# ═══════════════════════════════════════════════════════════
#  RÉSOLUTION DES QUESTIONS DE SUIVI
# ═══════════════════════════════════════════════════════════

def _resoudre_question_suivi(question: str, mem) -> str:
    """BUG TROUVÉ le 2026-07-22 (testé en direct par le directeur, reproduit) : « Et pour
    ECOBANK ? » après une question sur les frais de tenue de compte partait sur le ROE/PNB/
    dépôts d'ECOBANK — sujet complètement différent. Cause : has_banque/has_annee EXCLUAIENT
    la question du statut « suivi », alors que « et pour BANQUE ? » ou « et en ANNÉE ? » SANS
    aucun mot d'indicateur précis est justement le cas le PLUS courant de suivi (on change une
    seule dimension, banque ou année, en gardant le même sujet). Fix : ce qui rend une question
    auto-suffisante, ce n'est PAS de nommer une banque/année, c'est de nommer un SUJET précis
    (indicateur EF ou service CB) — sans ça, elle continue forcément la question précédente."""
    q_low = question.strip().lower()
    mots  = q_low.split()
    has_topic = any(k in q_low for k in _EF_KEYS) or bool(retriever._extraire_terme_service(question))

    # 2026-07-25 (audit chat, problème #9) : seuil relevé de 10 à 20 mots. `has_topic` est déjà
    # le VRAI signal (une question qui nomme son propre sujet est indépendante) — le compte de
    # mots n'est qu'un garde-fou secondaire pour les questions SANS sujet reconnu. À 10 mots,
    # un suivi un peu plus détaillé ("Et pour la même période mais côté entreprises cette
    # fois ?" = 11 mots) perdait le contexte à tort. Une vraie question indépendante de cette
    # longueur nomme quasi toujours une banque/un indicateur/un service — donc relever le seuil
    # réduit les faux négatifs (suivis ratés) sans vraiment augmenter les faux positifs.
    if len(mots) <= 20 and not has_topic:
        last_q = mem.get_last_question()
        if last_q:
            return f"{question} [Contexte de la question précédente : {last_q}]"
    return question


# ═══════════════════════════════════════════════════════════
#  NIVEAU DE CONFIANCE ANALYTIQUE
# ═══════════════════════════════════════════════════════════

def _niveau_confiance(types_actifs: list, question: str) -> int:
    if retriever.is_recommandation_ou_analyse(question):
        return 3
    if len(types_actifs) >= 2:
        return 2
    if types_actifs:
        return 1
    return 4


# ═══════════════════════════════════════════════════════════
#  RETRIEVAL PARALLÈLE MULTI-AGENTS
# ═══════════════════════════════════════════════════════════

def _retrieval_parallele(vectorstore, question: str, types_actifs: list) -> dict:
    """
    Lance le retrieval de chaque agent en parallèle via ThreadPoolExecutor.
    Gain de latence : 3 agents en ~1× le temps d'un seul retrieval.
    """
    if not types_actifs:
        return {}

    if len(types_actifs) == 1:
        td     = types_actifs[0]
        chunks = retriever.search_auto(vectorstore, question, force_type_doc=td)
        print(f"  [{_AGENT_LABELS.get(td, td)}] {len(chunks)} chunks")
        return {td: chunks}

    resultats = {}

    def _fetch(type_doc: str):
        return type_doc, retriever.search_auto(vectorstore, question, force_type_doc=type_doc)

    with ThreadPoolExecutor(max_workers=min(len(types_actifs), 3)) as ex:
        futures = {ex.submit(_fetch, td): td for td in types_actifs}
        for future in as_completed(futures):
            try:
                td, chunks = future.result()
                resultats[td] = chunks
                print(f"  [{_AGENT_LABELS.get(td, td)}] {len(chunks)} chunks")
            except Exception as e:
                td = futures[future]
                print(f"  [{td}] ERREUR retrieval : {e}")
                resultats[td] = []

    return resultats


# ═══════════════════════════════════════════════════════════
#  FORMATAGE DU CONTEXTE SECTIONNÉ PAR AGENT
# ═══════════════════════════════════════════════════════════

_TYPES_TEXTE = {"INSTRUCTION": "Instruction", "DECISION": "Décision", "DÉCISION": "Décision",
                "LOI": "Loi", "CIRCULAIRE": "Circulaire", "ARRETE": "Arrêté"}
_EMETTEURS   = {"BCEAO", "UMOA", "UEMOA"}
_NUM_TEXTE   = re.compile(r"^\d{1,3}(-\d{2,4})+$")


def _titre_reglementaire(nom_fichier: str) -> str:
    """Rend le nom de fichier sous la forme d'une référence citable.

    Les en-têtes de section portent la provenance de chaque article, pour que le modèle
    puisse citer sa source. Y écrire le nom de fichier brut le lui faisait recopier tel
    quel — « selon l'article 2 de la BCEAO_INSTRUCTION_004-05-2015_TRANSPARENCE_TARIFAIRE » —
    alors que la consigne interdit toute référence technique interne. La transformation est
    entièrement déterministe : on ne demande pas au modèle de deviner la référence, on la
    lui donne déjà écrite.
    """
    if not nom_fichier:
        return "texte réglementaire"
    mots = [m for m in re.split(r"[_\s]+", nom_fichier.strip()) if m]
    emetteur = next((m for m in mots if m.upper() in _EMETTEURS), "")
    type_txt = next((_TYPES_TEXTE[m.upper()] for m in mots if m.upper() in _TYPES_TEXTE), "")
    numero   = next((m for m in mots if _NUM_TEXTE.match(m)), "")
    reste    = [m for m in mots
                if m.upper() not in _EMETTEURS and m.upper() not in _TYPES_TEXTE and m != numero]

    if not type_txt or not numero:
        # Nom hors convention (« LOI DE CONSOMMATION ») : le mettre entre parenthèses
        # donnerait « Loi (de consommation) ». On se contente de le rendre lisible.
        return " ".join(mots).replace("-", " ").capitalize()

    titre = type_txt
    if emetteur:
        titre += f" {emetteur.upper()}"
    if numero:
        titre += f" n° {numero}"
    if reste:
        titre += " (" + " ".join(reste).lower() + ")"
    return titre


def _tronquer_equitablement(context: str, budget: int) -> str:
    """Réduit le contexte au budget, en partageant la place SANS la gaspiller.

    Le partage précédent divisait le budget par le nombre de sections et coupait chacune à
    cette longueur. Une part égale n'est équitable qu'entre sections de taille comparable —
    or elles ne le sont pas du tout. Mesuré sur « la tenue de compte est-elle gratuite ? » :
    24 sections, 250 caractères chacune. Vingt en-têtes tarifaires de 49 caractères
    recevaient 250 places pour en occuper 49, gaspillant quatre cents caractères, pendant que
    l'annexe de la BCEAO — 1 519 caractères — était coupée à 250, juste avant la ligne
    « Tenue de compte sur livret d'épargne » qui répondait à la question.

    On sert donc d'abord les sections qui tiennent dans leur part, puis on redistribue ce
    qu'elles n'ont pas consommé à celles qui débordent, et on recommence jusqu'à ce que plus
    rien ne circule. Aucune section ne reçoit plus qu'elle ne demande, et le surplus va aux
    plus longues — les textes de loi, précisément. Personne n'est privilégié par une règle
    particulière : c'est la taille réelle qui décide.
    """
    SEP = "═" * 50
    sections = [s for s in context.split(SEP) if s.strip()]
    n = len(sections)
    if not n:
        return context

    reste = budget - n * len(SEP)      # les séparateurs seront réécrits, ils comptent
    if reste <= 0:
        return context[:max(0, budget)]

    tailles = [len(s) for s in sections]
    alloue  = [0] * n
    en_lice = list(range(n))
    while en_lice and reste > 0:
        part = reste // len(en_lice)
        if part <= 0:
            break
        tiennent = [i for i in en_lice if tailles[i] <= part]
        if not tiennent:                # toutes débordent : on partage à parts égales
            for i in en_lice:
                alloue[i] = part
            break
        for i in tiennent:
            alloue[i] = tailles[i]
            reste -= tailles[i]
        en_lice = [i for i in en_lice if i not in set(tiennent)]

    return "\n".join(SEP + s[:alloue[i]] for i, s in enumerate(sections))


def _texte_reponse(message) -> str:
    """Rend la réponse du modèle SOUS FORME DE TEXTE, quel que soit le fournisseur.

    `.content` valait une chaîne. Les modèles Gemini récents rendent une LISTE de blocs —
    `[{'type': 'text', 'text': '...', 'extras': {...}}]` — parce qu'un même message peut
    désormais mêler du texte, du raisonnement et des signatures. Tout ce qui suit dans cette
    chaîne attend une chaîne : les garde-fous qui traquent les chiffres inventés, les
    découpes, la mise en cache, et la réponse envoyée au navigateur. Une liste y passerait
    soit en exception, soit — pire — en `str(liste)`, et l'utilisateur lirait des accolades.

    On ne teste pas le nom du fournisseur mais la FORME de ce qu'on reçoit : le jour où un
    modèle changera encore de format, seule cette fonction sera à revoir.
    """
    contenu = getattr(message, "content", message)
    if isinstance(contenu, str):
        return contenu

    # On recolle les blocs de texte nous-mêmes AVANT d'essayer `.text`. Cette propriété est
    # la voie officielle, mais elle est méthode dans la version installée ici et l'appeler
    # émet un avertissement de dépréciation — à CHAQUE réponse, donc à chaque ligne du
    # journal de production. Un journal noyé sous un avertissement connu ne sert plus à
    # repérer celui qu'on ne connaît pas.
    if isinstance(contenu, list):
        morceaux = []
        for bloc in contenu:
            if isinstance(bloc, str):
                morceaux.append(bloc)
            elif isinstance(bloc, dict) and bloc.get("type") == "text":
                morceaux.append(bloc.get("text") or "")
        if any(m.strip() for m in morceaux):
            return "".join(morceaux)

    # Repli : une forme que l'on n'a pas prévue. `.text` s'en tire peut-être — propriété dans
    # les versions récentes, méthode dans les anciennes, on accepte les deux.
    txt = getattr(message, "text", None)
    if callable(txt):
        try:
            txt = txt()
        except Exception:
            txt = None
    if isinstance(txt, str) and txt.strip():
        return txt

    return "" if contenu is None else str(contenu)


def _texte_regl(chunk: dict) -> str:
    """Le texte de l'article, sans l'habillage prévu pour les tarifs.

    `format_context` regroupe par banque × période × cible et ajoute, pour chaque groupe,
    deux filets de 55 caractères et une ligne « (1 entrées) ». Un article réglementaire n'a
    ni banque ni période : cet habillage coûtait environ 180 caractères par article, sans
    rien apprendre à personne. C'est beaucoup quand le budget total est de 9 000 caractères
    partagés entre toutes les sections — assez pour que la phrase utile passe sous la coupe.
    Constaté sur « sous quel délai une banque doit-elle communiquer ses tarifs à la BCEAO ? » :
    l'article 2 arrivait en tête du classement, et « dans un délai d'une semaine » tombait
    quelques caractères au-delà de la limite.
    """
    lignes = [l for l in (chunk.get("texte") or "").strip().split("\n")
              if not (l.startswith("[") and l.endswith("]") and "|" in l)]
    return "\n".join(lignes).strip()


def _formater_contexte_sections(chunks_par_agent: dict, regl_chunks: list, niveau: int) -> str:
    sections = [
        f"[NIVEAU DE CONFIANCE ANALYTIQUE : {niveau}]\n"
        f"1=Factuel | 2=Analytique | 3=Prospectif (ancrage régl. obligatoire) | 4=Refus propre"
    ]

    # La réglementation passe EN TÊTE. Elle était écrite en dernier, parce que la branche de
    # comparaison la rattache après coup au dictionnaire des agents. Or deux réductions
    # coupent le contexte PAR LA FIN — la compensation de la fiche marché (6e) et celle de la
    # fiche mono-banque (6d) : la section réglementaire était donc la première sacrifiée.
    # Constaté sur « quel est le taux de l'usure applicable aux banques ? » : l'agent trouvait
    # bien la décision de l'UMOA, elle disparaissait avant le modèle, et le chat répondait
    # « non disponible » sur une donnée qu'il avait en main. Le droit est le cadre dans lequel
    # un tarif se lit, pas la chute d'un contexte trop long.
    ordre = (["reglementation"] if "reglementation" in chunks_par_agent else []) + \
            [t for t in chunks_par_agent if t != "reglementation"]

    for type_doc in ordre:
        chunks = chunks_par_agent[type_doc]
        if not chunks:
            continue
        label = _AGENT_LABELS.get(type_doc, type_doc.upper())
        sep   = "═" * 50

        if type_doc == "reglementation":
            # Un article, une section. Les fragments réglementaires n'ont ni banque ni
            # période : `format_context` les regroupe donc TOUS sous une seule et même
            # section, collés les uns aux autres. Or les réductions de contexte coupent
            # chaque section au caractère et gardent sa tête — le modèle recevait le premier
            # article et perdait les sept suivants, quel que soit leur classement.
            # Constaté sur « quelles obligations de transparence tarifaire pèsent sur les
            # banques ? » : il n'a reçu qu'un article sur l'agrément, pendant que
            # l'instruction de 2015, classée troisième, était jetée avec le reste.
            # Découpé ainsi, le partage équitable déjà en place donne sa part à CHAQUE
            # article, et un article court — la plupart le sont — survit entier.
            for i, c in enumerate(chunks, 1):
                titre = _titre_reglementaire(c.get("source"))
                sections.append(
                    f"{sep}\n{label} — source {i}/{len(chunks)} : {titre}\n{sep}\n"
                    f"{_texte_regl(c)}")
        else:
            bloc = retriever.format_context(chunks)
            sections.append(f"{sep}\n{label} ({len(chunks)} sources)\n{sep}\n{bloc}")

    # Même découpage pour l'enrichissement réglementaire, et pour la même raison.
    if regl_chunks:
        sep = "═" * 50
        for i, c in enumerate(regl_chunks, 1):
            titre = _titre_reglementaire(c.get("source"))
            sections.append(
                f"{sep}\nTEXTE RÉGLEMENTAIRE APPLICABLE {i}/{len(regl_chunks)} : {titre}\n"
                f"{sep}\n{_texte_regl(c)}")

    return "\n\n".join(sections)


# ═══════════════════════════════════════════════════════════
#  SÉLECTION DU PROMPT ADAPTATIF
# ═══════════════════════════════════════════════════════════

def _choisir_prompt(types_actifs: list, niveau: int):
    if niveau == 3 or len(types_actifs) > 1:
        return "multi"
    if len(types_actifs) == 1:
        return types_actifs[0]
    return None


def _fiche_synthese_bancaire(banque: str) -> str:
    """Fiche de synthèse chiffrée et CLASSÉE (rang exact sur les 7 banques, source SQL)
    pour UNE banque — ROE, coefficient d'exploitation, PNB, résultat net. Sert de
    grounding déterministe pour les questions analytiques ouvertes ("X est-elle solide
    et compétitive ?"). Trouvé le 2026-07-11 : sans ça, le LLM se noyait dans un dump
    brut de bilan et concluait "difficile de conclure sans données comparatives" — alors
    que ces mêmes données comparatives sont déjà calculées ailleurs dans l'app (ROE,
    coefficient d'exploitation), juste jamais transmises au LLM pour CE type de question."""
    indicateurs = [
        ("ROE", structured_tools.comparer_roe(), "%", "max"),
        ("Coefficient d'exploitation (plus BAS = plus efficient)",
         structured_tools.comparer_coefficient_exploitation(), "%", "min"),
        ("PNB", structured_tools.comparer_ef("pnb"), "millions FCFA", "max"),
        ("Résultat net", structured_tools.comparer_ef("résultat net"), "millions FCFA", "max"),
    ]
    lignes = [f"FICHE DE SYNTHÈSE CHIFFRÉE — {banque} (classement exact sur les 7 banques, source SQL exacte) :"]
    trouve = False
    for label, d, unite, sens in indicateurs:
        if banque not in d:
            continue
        trouve = True
        items = sorted(d.items(), key=lambda kv: kv[1]["valeur"], reverse=(sens == "max"))
        rang  = next(i for i, (k, _) in enumerate(items, 1) if k == banque)
        val   = d[banque]["valeur"]
        val_fmt = f"{val:,.1f}".replace(",", " ") if unite == "%" else f"{val:,.0f}".replace(",", " ")
        # ANNÉE OBLIGATOIRE (2026-07-27) : sans elle, le LLM en invente une. Constaté en test sur
        # « La BICICI est-elle solide ? » → « ROE de 30,3 % en 2022 », alors que ce ROE est celui
        # de 2025 ; le LLM avait attrapé une année au hasard dans le bilan brut qui suit la fiche.
        an = d[banque].get("annee")
        lignes.append(f"  - {label} : {val_fmt} {unite}" + (f" (exercice {an})" if an else "")
                      + f" → rang {rang}/{len(items)} parmi les banques comparables")
    return "\n".join(lignes) if trouve else ""


# ═══════════════════════════════════════════════════════════
#  MOTEUR D'EXÉCUTION PRINCIPAL
# ═══════════════════════════════════════════════════════════

def _executer(chain: dict, question: str, types_actifs: list) -> str:
    vectorstore = chain["vectorstore"]
    mem         = chain["memory"]

    label_agents = " + ".join(
        _AGENT_LABELS.get(t, t) for t in types_actifs
    ) if types_actifs else "général"

    print(f"\n{'='*65}")
    print(f"  {label_agents}")
    print(f"  Q : {question[:90]}")
    print(f"{'─'*65}")

    # 1. Résolution contexte de suivi
    question_retrieval = _resoudre_question_suivi(question, mem)
    est_suivi = question_retrieval != question
    if est_suivi:
        print(f"  [Suivi enrichi] {question_retrieval[:80]}...")

    # 2. Vérification disponibilité EF
    if "etats_financiers" in types_actifs:
        banque      = retriever.detect_banque(question_retrieval)
        annee       = retriever.detect_annee(question_retrieval)
        msg_indispo = retriever.check_disponibilite_ef(banque, annee)
        if msg_indispo:
            mem.add_user(question)
            mem.add_assistant(msg_indispo)
            return msg_indispo

    # 3. Retrieval PARALLÈLE par agent
    chunks_par_agent = _retrieval_parallele(vectorstore, question_retrieval, types_actifs)

    # 4. Enrichissement réglementaire si niveau prospectif
    niveau      = _niveau_confiance(types_actifs, question)
    regl_chunks = []
    if niveau == 3 and "reglementation" not in types_actifs:
        regl_chunks = retriever.search_reglementation(vectorstore, question, k=5)
        if regl_chunks:
            print(f"  + {len(regl_chunks)} chunk(s) réglementaire(s) — ancrage légal niveau 3")

    # 5. Vérification contenu total
    total_chunks = sum(len(c) for c in chunks_par_agent.values()) + len(regl_chunks)
    if total_chunks == 0:
        reponse = (
            "Données insuffisantes dans la base documentaire pour répondre à cette question. "
            "Vérifiez que les PDFs correspondants ont bien été indexés."
        )
        mem.add_user(question)
        mem.add_assistant(reponse)
        return reponse

    print(f"  Total : {total_chunks} chunks — niveau de confiance : {niveau}")

    # 6. Formatage du contexte sectionné par agent
    context = _formater_contexte_sections(chunks_par_agent, regl_chunks, niveau)
    _context_len_avant_troncature = len(context)   # cf. note de troncature ajoutée en 8b (audit 2026-07-25)

    # 6b. Réduction si contexte trop grand pour Groq free tier (6000 TPM)
    if len(context) > config.MAX_CONTEXT_CHARS:
        banques_det  = retriever.detect_banques(question_retrieval)
        # detect_banque() (singulier) ne renvoie QUE la 1ère banque citée — une question du
        # type "compare X entre SGCI et BICICI" perdait alors la 2e banque et empruntait à
        # tort le chemin "banque unique" (budget plus large, moins strict), ce qui dépassait
        # le TPM Groq même après rotation de clé. On ne traite donc "banque unique" que s'il
        # y en a réellement UNE SEULE citée.
        banque_det   = banques_det[0] if len(banques_det) == 1 else None
        annee_det    = retriever.detect_annee(question_retrieval)
        semestre_det = retriever.detect_semestre(question_retrieval)
        cible_det    = retriever.detect_cible(question_retrieval)

        types_actifs_set = set(chunks_par_agent.keys())

        if banque_det:
            # Banque précise : on trie les chunks EXISTANTS par score sémantique
            # (ne pas re-chercher — le NLP hybride a déjà trouvé les bons chunks)
            all_existing = [c for td_chunks in chunks_par_agent.values() for c in td_chunks]
            # Priorité : chunks avec vrai score sémantique > keyword (score=1.0)
            all_existing.sort(key=lambda x: x.get("score", 0.5), reverse=True)
            # Estimer combien de chunks tiennent dans MAX_CONTEXT_CHARS
            avg_chars = max(80, sum(len(c["texte"]) for c in all_existing[:50]) // max(1, min(50, len(all_existing))))
            k_keep = max(15, config.MAX_CONTEXT_CHARS // avg_chars)
            print(f"  Contexte {len(context):,} > {config.MAX_CONTEXT_CHARS} — top {k_keep} chunks par score ({banque_det})...")
            chunks_par_agent_r = {}
            start = 0
            for td in chunks_par_agent:
                n = len(chunks_par_agent[td])
                # Répartir proportionnellement parmi les agents actifs
                chunks_par_agent_r[td] = [c for c in all_existing[:k_keep] if c.get("type_doc") == td or c.get("metadata", {}).get("type_document") == td]
                if not chunks_par_agent_r[td]:
                    chunks_par_agent_r[td] = all_existing[:k_keep]
            regl_r  = retriever.search_reglementation(vectorstore, question, k=2) if regl_chunks else []
            context = _formater_contexte_sections(chunks_par_agent_r, regl_r, niveau)
            print(f"  Contexte réduit (top {k_keep} par score) : {len(context):,} chars")

        elif types_actifs_set == {"reglementation"} or (
                "reglementation" in types_actifs_set and "conditions_banque" not in types_actifs_set):
            # REGL seul ou EF+REGL : sémantique focused k=8
            k_reduit = 8
            print(f"  Contexte {len(context):,} > {config.MAX_CONTEXT_CHARS} — REGL sémantique k={k_reduit}...")
            chunks_par_agent_r = {}
            for td in chunks_par_agent:
                filters = retriever.build_filters(annee=annee_det, type_doc=td)
                chunks_par_agent_r[td] = retriever.search(
                    vectorstore, question_retrieval, k=k_reduit, filters=filters)
            regl_r  = retriever.search_reglementation(vectorstore, question, k=4) if regl_chunks else []
            context = _formater_contexte_sections(chunks_par_agent_r, regl_r, niveau)

        else:
            # Comparaison multi-banques CB : plusieurs chunks/banque (pas 1 seul — un seul
            # chunk par banque ratait presque tout : ex. "virement SGCI" a >15 variantes
            # (interne/STAR/international/...) en base, n'en garder qu'1 par similarité
            # sémantique renvoyait souvent une ligne non pertinente et le LLM répondait à
            # tort "non disponible" alors que la donnée existe. k adapté au nombre de
            # banques ciblées pour rester dans le budget Groq (le garde-fou 8b retronque
            # si le total dépasse malgré tout).
            # Si des banques précises sont citées (ex. "SGCI et BICICI"), on se limite à
            # CELLES-LÀ plutôt que les 7 — contexte bien plus petit pour une comparaison
            # ciblée, tout en gardant les 7 banques pour une question générale de classement.
            banques_cible = banques_det if len(banques_det) >= 2 else config.BANQUES_OFFICIELLES
            k_par_banque = max(2, 15 // max(1, len(banques_cible)))
            print(f"  Contexte {len(context):,} > {config.MAX_CONTEXT_CHARS} — comparaison k={k_par_banque}/banque ({len(banques_cible)} banques)...")
            # Terme de service extrait de la question (ex. "virement") : la recherche
            # sémantique seule ratait souvent le bon chunk pour UNE banque en particulier
            # (ex. "virement interne GRATUIT" chez SGCI n'était jamais dans le top-k
            # sémantique) → on ajoute le même boost mot-clé que la branche banque unique.
            # NOTE : le cas "service précis + 2+ banques nommées" est déjà intercepté PLUS
            # TÔT par _detect_comparaison_cb_service (tableau SQL exhaustif, sans LLM/RAG,
            # voir ask()) — cette branche ne sert donc que de FILET pour les cas où ce
            # détecteur ne s'est pas déclenché (ex. terme de service non reconnu).
            terme_service = retriever._extraire_terme_service(question_retrieval)
            chunks_cmp = []
            tds_a_traiter = [t for t in chunks_par_agent if t != "reglementation"]
            for td in tds_a_traiter:
                for banque in banques_cible:
                    filters = retriever.build_filters(banque=banque, annee=annee_det,
                                                      type_doc=td, semestre=semestre_det, cible=cible_det)
                    bank_chunks = retriever.search(
                        vectorstore, question_retrieval, k=k_par_banque, filters=filters)
                    if td == "conditions_banque" and terme_service:
                        kw_chunks = retriever.search_cb_keyword(
                            vectorstore, [terme_service], banque=banque, annee=annee_det,
                            semestre=semestre_det, cible=cible_det)
                        # search_cb_keyword trie par SECTION (alphabétique), pas par
                        # pertinence — pour "virement", les centaines de variantes
                        # internationales (étranger/SWIFT/devise) passent AVANT les
                        # virements domestiques génériques dans cet ordre, qui se
                        # faisaient donc toujours couper par le [:k_par_banque]. On
                        # priorise les libellés génériques/domestiques en tête, sauf si
                        # la question elle-même mentionne l'international/l'étranger.
                        veut_intl = any(m in question_retrieval.lower()
                                        for m in ("étranger", "etranger", "international", "devise", "swift"))
                        if not veut_intl:
                            EXCLUS = ("étranger", "etranger", "international", "devise", "swift", "eur")
                            kw_chunks = sorted(
                                kw_chunks,
                                key=lambda c: any(m in c["texte"].lower() for m in EXCLUS))
                        vus = {c["texte"] for c in bank_chunks}
                        bank_chunks.extend(c for c in kw_chunks[:k_par_banque] if c["texte"] not in vus)
                    # NOTE : une tentative de forcer la couverture par catégorie (tenue/
                    # virement/carte/retrait) pour les comparaisons LARGES sans service
                    # précis a été essayée puis RETIRÉE — le système prompt de l'agent
                    # Conditions Tarifaires est déjà énorme (~10 500 caractères), laissant
                    # une marge minuscule pour le contexte sur Groq (6000 TPM) ; ajouter ces
                    # catégories faisait systématiquement dépasser la limite (413 sur les
                    # 12 clés à chaque tentative). Le garde-fou 8b protège contre le crash,
                    # mais au prix d'une troncature encore plus sévère du contexte utile.
                    # Limitation assumée : sur une comparaison à 3+ banques SANS service
                    # précis nommé, certaines lignes factuelles courtes (ex. NSIA "Compte
                    # Courant : GRATUIT") peuvent ne pas remonter — le chat ne les invente
                    # pas, il dit honnêtement "non disponible dans le contexte fourni".
                    chunks_cmp.extend(bank_chunks)
            chunks_par_agent_r = {td: chunks_cmp for td in tds_a_traiter}
            if "reglementation" in chunks_par_agent:
                chunks_par_agent_r["reglementation"] = retriever.search_reglementation(
                    vectorstore, question, k=3)
            regl_r  = retriever.search_reglementation(vectorstore, question, k=2) if regl_chunks else []
            context = _formater_contexte_sections(chunks_par_agent_r, regl_r, niveau) if chunks_par_agent_r or regl_r else ""

            # Plafond spécifique et plus strict pour ce cas (jusqu'à 7 banques cumulées +
            # prompt de comparaison plus long) — le filet de sécurité général (6c) utilise
            # MAX_CONTEXT_CHARS, trop généreux ici et qui dépassait encore le TPM Groq.
            # BUG TROUVÉ le 2026-07-25 (audit chat) : SEP ici valait "═"*55 mais
            # _formater_contexte_sections() génère ses séparateurs en "═"*50 (cf. ligne ~319/324)
            # — aucune coupure de 55 caractères consécutifs n'existe jamais dans le texte réel
            # (une étiquette de section casse toujours la série avant), donc ce split ne
            # trouvait JAMAIS ses sections : tout le contexte tombait dans UNE seule "section",
            # rendant cette troncature "équitable par section" strictement équivalente à une
            # troncature brutale de la fin — exactement le problème qu'elle devait éviter.
            if len(context) > config.MAX_CONTEXT_CHARS_COMPARAISON:
                context = _tronquer_equitablement(context, config.MAX_CONTEXT_CHARS_COMPARAISON)

        print(f"  Contexte réduit : {len(context):,} chars")

    # 6c. Filet de sécurité final — même partage, sans gaspillage (voir _tronquer_equitablement)
    if len(context) > config.MAX_CONTEXT_CHARS:
        context = _tronquer_equitablement(context, config.MAX_CONTEXT_CHARS)
        print(f"  Contexte tronqué : {len(context):,} chars")

    # 6d. Question analytique sur UNE SEULE banque ("X est-elle solide/compétitive ?") :
    # injecter la fiche de synthèse chiffrée ET CLASSÉE (ROE, coefficient d'exploitation,
    # PNB, résultat net) en tête de contexte. Placé APRÈS toute réduction (6b/6c) — un essai
    # précédent l'injectait avant 6b, mais la branche "banque unique" y reconstruit le
    # contexte ENTIER à partir des chunks bruts, écrasant silencieusement la fiche. Ici,
    # elle survit forcément, et le garde-fou dynamique (8b) mesure la taille réelle après
    # coup — sans ça le LLM n'a que le bilan brut de CETTE banque, sans repère face aux 6
    # autres, et conclut à tort "impossible de juger la compétitivité" alors que ces
    # données comparatives (ROE, coefficient d'exploitation) existent déjà dans l'app.
    fiche_injectee = False
    if niveau >= 2 and "etats_financiers" in types_actifs:
        banques_uniques = retriever.detect_banques(question_retrieval)
        if len(banques_uniques) == 1:
            fiche = _fiche_synthese_bancaire(banques_uniques[0])
            if fiche:
                fiche_injectee = True
                # Ce cas (niveau≥2, multi-domaine, système-prompt déjà volumineux) est
                # DÉJÀ à la limite du budget Groq SANS la fiche (constaté : ~12 rotations
                # nécessaires). Ajouter la fiche telle quelle faisait passer l'échec de
                # "parfois après retries" à "toujours" (24/24) — donc on retire du contexte
                # BRUT l'équivalent de ce qu'on ajoute, pour un impact net quasi nul sur la
                # taille totale plutôt que de risquer un 413 systématique.
                context = context[:max(200, len(context) - len(fiche) - 2)]
                context = fiche + "\n\n" + context
                print(f"  [FICHE SYNTHÈSE] {banques_uniques[0]} — ROE/coeff. expl./PNB/RN classés injectés "
                      f"(contexte brut réduit de {len(fiche)+2:,} chars pour compenser)")

    # 6e. SOCLE DE FAITS PERMANENT (2026-07-27) — LE correctif de fond du chat.
    #
    # Diagnostic du directeur, mot pour mot : « les analyses des dashboards sont superbes MAIS
    # le chat est nul, pas flexible ». Les deux utilisent pourtant le MÊME modèle et des prompts
    # de qualité comparable. La différence est ailleurs, et elle est entière :
    #   - Dashboard : on DONNE les faits calculés, PUIS on pose la question → le LLM rédige.
    #   - Chat      : on DEVINE quels faits chercher (regex + vectoriel) → une devinette ratée
    #                 et le LLM rédige parfaitement sur des chunks tirés au hasard du cosinus.
    # Ici on aligne le chat sur le dashboard : les 7 banques × 5 indicateurs CLASSÉS sont
    # présents à CHAQUE réponse, quoi qu'ait donné le routage. Même si tous les détecteurs
    # ratent (faute de frappe, tournure inhabituelle), le LLM a de vraies données exactes en
    # main plutôt que rien. Le RAG vectoriel redevient un COMPLÉMENT pour le détail fin.
    #
    # Coût mesuré : ~1 000 caractères (~300 tokens), soit <8 % du budget d'entrée Groq — de
    # loin le meilleur rapport valeur/tokens du contexte. On compense malgré tout sur le
    # contexte brut (même précaution qu'en 6d) pour que l'ajout soit neutre en taille et ne
    # puisse JAMAIS déclencher un 413 sur un cas qui passait avant.
    # Sauté si la fiche mono-banque de 6d est déjà là : elle couvre le même besoin de façon
    # plus ciblée pour une question sur UNE banque, inutile de payer les deux.
    if not fiche_injectee:
        socle = fiche_marche.construire()
        if socle:
            context = context[:max(200, len(context) - len(socle) - 2)]
            context = socle + "\n\n" + context
            print(f"  [SOCLE FAITS] Fiche marché injectée ({len(socle):,} chars, "
                  f"contexte brut réduit d'autant)")

    # 7. Prompt adaptatif
    type_prompt = _choisir_prompt(types_actifs, niveau)
    prompt_template = prompts.get_prompt(type_prompt)
    if config.SHOW_QUERY_DEBUG:
        print(f"  Prompt : {type_prompt or 'defaut'} | Agents : {types_actifs} | Provider : {config.LLM_PROVIDER}")

    # 8. Génération LLM
    llm = _get_llm(types_actifs)
    # L'historique n'est transmis QUE si la question courante est un vrai suivi
    # (_resoudre_question_suivi l'a détecté : question courte, sans banque ni année
    # explicites — ex. "Et pour SGCI ?"). Sinon, une question autonome (nomme sa
    # propre banque/année) est indépendante et NE DOIT PAS voir l'historique : un
    # test a montré le LLM confondre PNB et Résultat Net d'une question à l'autre
    # en recopiant un chiffre de la question précédente (mémoire globale, non
    # filtrée) — chaque question autonome doit rester hermétique aux précédentes.
    history  = mem.format_for_prompt() if est_suivi else "Aucun historique — question indépendante."
    messages = prompt_template.format_messages(
        context  = context,
        history  = history,
        question = question,
        disponibilite_ef = retriever.texte_disponibilite_ef(),
    )

    # 8b. Garde-fou final basé sur la TAILLE RÉELLE du prompt assemblé (système + humain),
    # pas une estimation à plat de MAX_CONTEXT_CHARS. Les prompts systèmes varient beaucoup
    # en longueur selon l'agent (ex. conditions_banque ≈ 2x plus long que etats_financiers) —
    # un contexte sous MAX_CONTEXT_CHARS peut donc quand même dépasser le TPM Groq une fois
    # combiné à un long prompt système. Découvert le 2026-07-11 : une question simple avec
    # seulement 4 692 chars de contexte (< 5000, donc 6b/6c jamais déclenchés) a échoué en 413
    # sur les 12 clés — preuve que le seuil plat ne suffit pas, il faut mesurer le VRAI total.
    if config.LLM_PROVIDER == "groq":
        # Mesuré en direct le 2026-07-11 (question "Compare les conditions entre SGCI,
        # BICICI et NSIA") : système+humain = 13 636 chars, estimé à 4132 tok avec un
        # ratio de 3.3 chars/tok pour un budget de 4200 — sous le budget donc AUCUNE
        # troncature déclenchée, et pourtant Groq a quand même rejeté en 413 sur les 12
        # clés. Le contenu tabulaire (beaucoup de "|", chiffres, FCFA répétés) tokenise
        # moins bien que la prose estimée par ce ratio → resserré à 2.8 chars/tok + marge
        # de sécurité doublée (300→600), et on RE-VÉRIFIE après troncature (boucle) au
        # lieu de faire confiance à un seul calcul, pour être sûr de rester sous la limite
        # même si l'estimation reste imparfaite.
        CHARS_PAR_TOKEN = 3.3
        BUDGET_INPUT    = 6000 - config.LLM_MAX_TOKENS - 300
        SEP_8B = "═" * 50
        for _ in range(3):
            total_chars = sum(len(m.content) for m in messages)
            est_tokens  = total_chars / CHARS_PAR_TOKEN
            if est_tokens <= BUDGET_INPUT:
                break
            chars_a_retirer = int((est_tokens - BUDGET_INPUT) * CHARS_PAR_TOKEN) + 200
            cible_chars = max(100, len(context) - chars_a_retirer)
            # BUG TROUVÉ le 2026-07-25 (audit chat, reproduit en direct : "frais de tenue de
            # compte SGCI 2024" → le chunk keyword exact "Frais de tenue de compte : 2 350"
            # disparaissait, le LLM répondait "non disponible" alors que la donnée EXISTAIT
            # dans le contexte avant cette étape) : context[:N] coupe la fin du texte SANS
            # savoir quelle section s'y trouve — les chunks keyword (les plus fiables, ajoutés
            # en dernier dans l'union sémantique+keyword de search_auto) étaient justement les
            # premiers sacrifiés. Fix : même logique "équitable par section" que 6c au lieu
            # d'une coupe aveugle de la fin — chaque section perd le même NOMBRE de caractères,
            # aucune n'est rayée entièrement juste parce qu'elle est positionnée en dernier.
            sections = [s for s in context.split(SEP_8B) if s.strip()]
            if len(sections) > 1:
                chars_par_section = max(50, cible_chars // len(sections))
                nouveau_contexte = "\n".join(SEP_8B + s[:chars_par_section] for s in sections)
            else:
                nouveau_contexte = context[:cible_chars]
            print(f"  [GARDE-FOU] Prompt réel ≈{est_tokens:.0f} tok > budget {BUDGET_INPUT} — "
                  f"contexte {len(context):,} → {len(nouveau_contexte):,} chars "
                  f"({len(sections)} section(s), coupe équitable)")
            context  = nouveau_contexte
            messages = prompt_template.format_messages(
                context  = context,
                history  = history,
                question = question,
                disponibilite_ef = retriever.texte_disponibilite_ef(),
            )

    # 8c. Note de troncature (audit 2026-07-25) : le prompt (SYSTEM_BASE, règle EXHAUSTIVITÉ
    # STRICTE) exige de présenter TOUTES les entrées d'une section — mais si 6b/6c/8b ont réduit
    # le contexte pour tenir dans le budget Groq, le LLM ne reçoit alors qu'un SOUS-ENSEMBLE. Sans
    # signal, il ne peut pas savoir qu'il doit le dire au lieu de prétendre l'exhaustivité. On
    # ajoute cette note SEULEMENT si la réduction est significative (>15%, pas du bruit d'arrondi).
    if len(context) < _context_len_avant_troncature * 0.85:
        context = (context + "\n\n[NOTE SYSTÈME : contexte réduit pour respecter une limite "
                   "technique — certaines entrées existantes n'apparaissent peut-être pas "
                   "ci-dessus. Vois la règle EXHAUSTIVITÉ STRICTE.]")
        messages = prompt_template.format_messages(
            context  = context,
            history  = history,
            question = question,
            disponibilite_ef = retriever.texte_disponibilite_ef(),
        )
        print(f"  [NOTE TRONCATURE] Contexte réduit de {_context_len_avant_troncature:,} → "
              f"{len(context):,} chars — note ajoutée pour éviter une fausse promesse d'exhaustivité.")

    temp_used = (config.LLM_TEMPERATURE_FACTUEL
                 if all(t in {"conditions_banque", "etats_financiers"} for t in types_actifs)
                 else config.LLM_TEMPERATURE_ANALYTIQUE)
    print(f"  Génération ({config.LLM_PROVIDER} T={temp_used}) — {len(context):,} chars contexte...")

    reponse = _invoke_with_retry(llm, messages)

    # 8c. Garde-fou anti-invention (audit 2026-07-25) : si la réponse cite un grand nombre
    # absent du contexte fourni, on retente UNE fois une génération fraîche avant d'accepter
    # tel quel — pas de blocage dur (cf. leçon du 2026-07-22 sur le prompt EF), juste un log
    # pour garder trace des cas où ça persiste malgré la reprise.
    _invente = _chiffres_inventes_chat(reponse, context)
    if _invente:
        print(f"  [GARDE-FOU CHAT] Chiffre(s) absent(s) du contexte détecté(s) {_invente} — nouvelle tentative...")
        reponse_retry = _invoke_with_retry(llm, messages)
        if not _chiffres_inventes_chat(reponse_retry, context):
            reponse = reponse_retry
        else:
            print(f"  [GARDE-FOU CHAT] Persiste après reprise — réponse conservée telle quelle "
                  f"(chiffres à vérifier : {_chiffres_inventes_chat(reponse_retry, context)}).")
            reponse = reponse_retry

    # 9. Mémorisation
    mem.add_user(question)
    mem.add_assistant(reponse)
    print(f"  {mem.summary()}")

    return reponse

# ═══════════════════════════════════════════════════════════
#  BRANCHE COMPARATIVE — détection par RÈGLE → outil structuré SQL
#  (les comparaisons multi-banques sont des agrégations SQL, pas de
#   la récupération sémantique → on les route vers structured_tools)
# ═══════════════════════════════════════════════════════════

_COMP_KW = ("quelle banque", "laquelle", "la plus", "le plus", "la moins", "le moins",
            "moins cher", "moins chère", "plus gros", "plus élevé", "plus elevee",
            "meilleur", "plus faible", "la mieux", "classer")

_EF_KEYS = ("produit net bancaire", "pnb", "résultat net", "resultat net",
            "capitaux propres", "résultat d'exploitation", "résultat brut",
            "roe", "rentabilité", "rentabilite", "return on equity",
            "coefficient d'exploitation", "coefficient d exploitation",
            "total bilan", "total actif", "total de l'actif",
            "coût du risque", "cout du risque",
            "charges générales", "charges generales",
            "charges générales d'exploitation", "charges generales d'exploitation",
            "frais généraux", "frais generaux")


def _detect_comparatif(question: str):
    """Règle déterministe : détecte une question comparative + extrait ses paramètres."""
    q = question.lower()
    if not any(k in q for k in _COMP_KW):
        return None
    mserv = re.search(r"[«\"]\s*(.+?)\s*[»\"]", question)
    annee = re.search(r"\b(2024|2025|2026)\b", q)
    sem   = re.search(r"\bs([12])\b", q)
    if mserv and annee and sem:
        seg  = "Entreprises" if "entreprise" in q else "Particuliers"
        sens = "min" if ("moins" in q or "cher" in q) else "max"
        return {"kind": "cb", "service": mserv.group(1), "annee": int(annee.group(1)),
                "semestre": "S" + sem.group(1), "segment": seg, "sens": sens}
    for key in _EF_KEYS:
        if key in q:
            mode = "AN1" if ("an1" in q or "ancienne" in q or "plus ancienne" in q) else "AN3"
            sens = "min" if ("moins" in q or "plus faible" in q or "plus petit" in q) else "max"
            # ROE / coefficient d'exploitation = ratios CALCULÉS (résultat net/capitaux
            # propres, frais généraux/PNB) — pas des libellés bruts de la base.
            if key in ("roe", "rentabilité", "rentabilite", "return on equity"):
                return {"kind": "roe", "mode": mode, "sens": sens}
            if key in ("coefficient d'exploitation", "coefficient d exploitation"):
                # Pour ce ratio, "meilleur" = le PLUS BAS (plus efficient) sauf si "moins"
                # explicite inverse déjà le sens ci-dessus — ici on force le bon défaut :
                # un coefficient d'exploitation FAIBLE est la performance recherchée.
                sens = "min" if "plus élevé" not in q and "plus haut" not in q else "max"
                return {"kind": "coeff_expl", "mode": mode, "sens": sens}
            return {"kind": "ef", "indicateur": key, "mode": mode, "sens": sens}
    return None


def _executer_comparatif(chain: dict, question: str, spec: dict, question_memoire: str = None) -> str:
    """Exécute la comparaison via l'outil structuré SQL, puis fait phraser le LLM."""
    mem = chain["memory"]
    if spec["kind"] == "roe":
        d = structured_tools.comparer_roe(spec["mode"])
        txt, winner = structured_tools.format_comparaison(d, "%", spec["sens"])
    elif spec["kind"] == "coeff_expl":
        d = structured_tools.comparer_coefficient_exploitation(spec["mode"])
        txt, winner = structured_tools.format_comparaison(d, "%", spec["sens"])
    elif spec["kind"] == "ef":
        d = structured_tools.comparer_ef(spec["indicateur"], spec["mode"])
        txt, winner = structured_tools.format_comparaison(d, "millions FCFA", spec["sens"])
    else:
        d = structured_tools.comparer_cb(spec["service"], spec["annee"], spec["semestre"], spec["segment"])
        txt, winner = structured_tools.format_comparaison(d, "FCFA", spec["sens"])

    if winner is None:
        rep = "Données insuffisantes dans la base pour cette comparaison."
        mem.add_user(question_memoire or question); mem.add_assistant(rep)
        return rep

    # La bonne réponse (gagnant) est déjà calculée déterministiquement par
    # format_comparaison (tri numérique exact) — on la donne EXPLICITEMENT au LLM au
    # lieu de le laisser la redéduire du texte trié. Bug réel trouvé le 2026-07-11 :
    # pour "meilleur coefficient d'exploitation" (où PLUS BAS = meilleur), le LLM a
    # désigné à tort la banque avec la valeur la PLUS HAUTE comme "gagnante" — il ne
    # comprenait pas implicitement que ce ratio s'interprète à l'inverse d'un prix.
    sysm = (f"Tu réponds UNIQUEMENT à partir de la comparaison chiffrée fournie (source : base "
            f"SQL exacte, déjà triée). La bonne réponse est : {winner}. Confirme ce nom "
            f"explicitement dans ta première phrase, puis donne le classement complet avec "
            f"les valeurs telles qu'affichées (ne les réordonne pas, ne les réinterprète pas).")
    userm = f"Question : {question}\n\nComparaison :\n{txt}"
    llm = _get_llm(["etats_financiers"])     # température factuelle
    rep = _invoke_with_retry(llm, [("system", sysm), ("human", userm)])
    mem.add_user(question_memoire or question); mem.add_assistant(rep)
    return rep


# ═══════════════════════════════════════════════════════════
#  BRANCHE FACTUELLE MONO-BANQUE — 1 banque + 1 indicateur EF connu
#  (même source SQL que le dashboard EF → chiffre garanti exact, sans
#   dépendre du budget de contexte fragile du RAG sur Groq)
# ═══════════════════════════════════════════════════════════

def _detect_factuel_ef_unique(question: str):
    """Détecte 'Quel est le résultat net/PNB/... de BANQUE (en ANNEE) ?' — 1 seule
    banque nommée, aucun mot de comparaison, un indicateur EF reconnu. Question courte
    uniquement (≤ 14 mots) pour ne pas intercepter une question à la fois factuelle ET
    analytique (qui doit garder tout le contexte RAG pour son analyse)."""
    q = question.lower()
    if any(k in q for k in _COMP_KW):
        return None
    # Le plafond de mots ne compte QUE la question réellement tapée : l'annotation
    # « [Contexte de la question précédente : ...] » ajoutée aux suivis (cf.
    # _resoudre_question_suivi) faisait passer « Et en 2023 ? » de 4 à ~19 mots, au-dessus de la
    # limite — le détecteur factuel se désactivait donc pile sur les suivis, alors que ce sont
    # les questions les PLUS simples (1 banque, 1 indicateur, 1 année). Résultat mesuré le
    # 2026-07-27 : « Et en 2023 ? » après « résultat net de SGCI en 2024 » partait dans le RAG
    # et renvoyait 83 109 M — la colonne N-1 du rapport, soit l'exercice 2022 — au lieu des
    # 97 230 M de 2023. Un chiffre faux, présenté avec le même aplomb qu'un chiffre juste.
    q_utilisateur = re.split(r"\[contexte de la question", question, flags=re.I)[0]
    if len(q_utilisateur.split()) > 14:
        return None
    # Une question d'ÉVOLUTION attend une série (plusieurs années), pas un point. Sans ce
    # garde-fou, « Comment a évolué le PNB de SGCI ces dernières années ? » cochait toutes les
    # cases de cette branche (1 banque, 1 indicateur, ≤14 mots, aucun mot de comparaison) et
    # recevait une réponse d'UNE ligne sur la dernière année — techniquement exacte, et à côté
    # de la question. Trouvé le 2026-07-27 en sondant des formulations non encore testées.
    if retriever.is_evolution(question):
        return None
    banques = retriever.detect_banques(question)
    if len(banques) != 1:
        return None
    annee_m = re.search(r"\b(202[0-9]|2030)\b", q)
    annee = int(annee_m.group(1)) if annee_m else None
    for key in _EF_KEYS:
        if key in q:
            if key in ("roe", "rentabilité", "rentabilite", "return on equity"):
                return {"kind": "roe_unique", "banque": banques[0], "annee": annee}
            if key in ("coefficient d'exploitation", "coefficient d exploitation"):
                return {"kind": "coeff_expl_unique", "banque": banques[0], "annee": annee}
            return {"kind": "ef_unique", "banque": banques[0], "indicateur": key, "annee": annee}
    return None


_EF_LABELS = {
    "produit net bancaire": "produit net bancaire (PNB)", "pnb": "PNB",
    "résultat net": "résultat net", "resultat net": "résultat net",
    "capitaux propres": "capitaux propres", "résultat d'exploitation": "résultat d'exploitation",
    "résultat brut": "résultat brut d'exploitation",
    "total bilan": "total bilan", "total actif": "total bilan", "total de l'actif": "total bilan",
    "coût du risque": "coût du risque", "cout du risque": "coût du risque",
    "charges générales": "charges générales d'exploitation", "charges generales": "charges générales d'exploitation",
    "charges générales d'exploitation": "charges générales d'exploitation",
    "charges generales d'exploitation": "charges générales d'exploitation",
    "frais généraux": "charges générales d'exploitation", "frais generaux": "charges générales d'exploitation",
}


def _executer_factuel_ef_unique(chain: dict, question: str, spec: dict, question_memoire: str = None) -> str:
    """Lecture SQL directe (même requête que comparer_ef/comparer_roe) pour UNE banque."""
    mem    = chain["memory"]
    banque = spec["banque"]
    if spec["kind"] == "roe_unique":
        info = structured_tools.comparer_roe("AN3").get(banque)
        if not info:
            rep = f"Données insuffisantes dans la base pour calculer le ROE de {banque}."
        else:
            rep = f"Le ROE de {banque} est de {info['valeur']:.1f} % en {info['annee']}."
    elif spec["kind"] == "coeff_expl_unique":
        info = structured_tools.comparer_coefficient_exploitation("AN3").get(banque)
        if not info:
            rep = f"Données insuffisantes dans la base pour calculer le coefficient d'exploitation de {banque}."
        else:
            rep = f"Le coefficient d'exploitation de {banque} est de {info['valeur']:.1f} % en {info['annee']}."
    else:
        label = _EF_LABELS.get(spec["indicateur"], spec["indicateur"])
        info = structured_tools.valeur_ef(banque, spec["indicateur"], spec.get("annee"))
        if not info:
            rep = f"Données insuffisantes dans la base pour « {label} » de {banque}."
        else:
            valeur_fmt = f"{info['valeur']:,.0f}".replace(",", " ")
            rep = f"Le {label} de {banque} en {info['annee']} est de {valeur_fmt} millions FCFA."
    mem.add_user(question_memoire or question); mem.add_assistant(rep)
    return rep


# ═══════════════════════════════════════════════════════════
#  BRANCHE COMPARAISON CB EXHAUSTIVE — service précis + 2+ banques nommées
#  (tableau SQL direct, Particuliers ET Entreprises, toutes périodes — le RAG
#   échantillonne k chunks/banque pour tenir dans le budget Groq, ce qui produit
#   des trous "non disponible" sur des données qui EXISTENT et ne sépare pas
#   fiablement les segments/périodes. Ici : zéro perte, zéro invention.)
# ═══════════════════════════════════════════════════════════

# Catégorie(s) par défaut pour une comparaison GÉNÉRIQUE ("compare les conditions entre
# X et Y", sans service précis nommé). Testé avec les 4 catégories (tenue+virement+carte+
# retrait) empilées : le tableau atteint ~14 700 caractères pour 3 banques → dépasse le
# budget Groq même avec le prompt minimal (413 sur les 12 clés, 2 cycles complets). Réduit
# à UNE seule catégorie (tenue de compte — la plus demandée en pratique) pour rester
# fiable ; les autres catégories restent disponibles via une question plus précise
# ("compare les frais de virement entre X et Y").
_CATEGORIES_CB_DEFAUT = ["tenue"]
# "compar" retiré volontairement : il matche "Compare" dans N'IMPORTE QUELLE comparaison,
# y compris "Compare le PNB entre..." (un indicateur EF, pas CB) — bug réel trouvé le
# 2026-07-11 (batterie de questions variées) : la question PNB recevait un tableau CB
# "tenue de compte" complètement hors sujet. Les mots restants ("condition"/"frais"/
# "tarif"/"cher") sont des signaux SPÉCIFIQUES au domaine CB, pas de comparaison en général.
_MOTS_COMPARAISON_CB = ("condition", "frais", "tarif", "cher", "chère")


def _detect_comparaison_cb_service(question: str):
    """Détecte une comparaison CB entre 2+ banques nommées :
    - service précis reconnu (virement/tenue/carte/...) → tableau ciblé sur ce service
    - sinon, comparaison générique ("compare les conditions/frais entre X et Y") →
      tableau sur la catégorie par défaut (_CATEGORIES_CB_DEFAUT), plutôt que de laisser
      le RAG s'en charger (fragile, produisait des trous "non disponible" sur des
      données qui existent réellement).
    Retourne None si rien n'est détectable — le RAG prend le relais. Garde-fou : si la
    question contient un indicateur EF connu (PNB, résultat net, ROE...), ce n'est PAS
    une comparaison CB même si elle nomme 2+ banques — laisser _detect_comparatif (EF)
    ou le RAG gérer, jamais renvoyer un tableau CB hors sujet."""
    banques = retriever.detect_banques(question)
    q = question.lower()
    if any(k in q for k in _EF_KEYS):
        return None

    # QUESTION CROSS-BANQUES SANS BANQUE NOMMÉE (2026-07-27) : « Quelles banques offrent la
    # carte Visa Gold et à quel prix ? » ne nomme personne — la branche exhaustive ne se
    # déclenchait donc pas et la question partait en recherche sémantique sur les 7 banques,
    # dont le contexte (36 000 chars) était ensuite rogné à 3 700 : la réponse ne citait que
    # BACI, alors que SIX banques proposent une carte Gold. Dire « seule BACI » quand cinq
    # concurrents en proposent aussi, c'est pire qu'une réponse incomplète sur un outil
    # d'intelligence CONCURRENTIELLE. Ici, le tableau SQL exhaustif couvre les 7 sans perte.
    if not banques:
        terme_cross = retriever._extraire_terme_service(question)
        if terme_cross and _contient_racine(q, ("quelles banques", "quelle banque", "toutes les banques",
                                                "chaque banque", "les banques", "quels etablissements",
                                                "banques offrent", "banques proposent", "comparer les banques")):
            return {"banques": list(config.BANQUES_OFFICIELLES), "termes": [terme_cross]}
        return None

    if len(banques) < 2:
        return None
    terme = retriever._extraire_terme_service(question)
    if terme:
        return {"banques": banques, "termes": [terme]}
    if any(m in q for m in _MOTS_COMPARAISON_CB):
        return {"banques": banques, "termes": _CATEGORIES_CB_DEFAUT}
    return None


def _detect_comparaison_ef_banques(question: str):
    """Détecte 'Compare le PNB entre SGCI, ECOBANK et BICICI (en 2024)' : 2+ banques
    nommées + un indicateur EF reconnu, SANS mot superlatif ("meilleur"/"quelle banque"...
    déjà géré par _detect_comparatif). Bug réel trouvé le 2026-07-11 : cette phrasing
    tombait dans le RAG général (agent États Financiers, tri-domaine parfois), qui
    dépassait le budget Groq sur 3 banques et échouait en 413. Route directe vers
    comparer_ef/comparer_roe/comparer_coefficient_exploitation restreint aux banques
    nommées → même principe que _detect_comparaison_cb_service, côté EF."""
    banques = retriever.detect_banques(question)
    if len(banques) < 2:
        return None
    q = question.lower()
    for key in _EF_KEYS:
        if key in q:
            annee_m = re.search(r"\b(202[0-9]|2030)\b", q)
            annee = int(annee_m.group(1)) if annee_m else None
            if key in ("roe", "rentabilité", "rentabilite", "return on equity"):
                return {"kind": "roe", "banques": banques, "annee": annee}
            if key in ("coefficient d'exploitation", "coefficient d exploitation"):
                return {"kind": "coeff_expl", "banques": banques, "annee": annee}
            return {"kind": "ef", "indicateur": key, "banques": banques, "annee": annee}
    return None


def _executer_comparaison_ef_banques(chain: dict, question: str, spec: dict, question_memoire: str = None):
    """Comme _executer_comparatif mais restreint aux banques NOMMÉES (pas les 7), et sans
    exiger de mot superlatif. Prompt minimal comme pour le ROE/EF classique."""
    mem     = chain["memory"]
    banques = spec["banques"]
    mode    = "AN1" if spec.get("annee") and spec["annee"] < 2024 else "AN3"
    if spec["kind"] == "roe":
        d = structured_tools.comparer_roe(mode, banques=banques)
        txt, winner = structured_tools.format_comparaison(d, "%", "max")
    elif spec["kind"] == "coeff_expl":
        d = structured_tools.comparer_coefficient_exploitation(mode, banques=banques)
        txt, winner = structured_tools.format_comparaison(d, "%", "min")
    else:
        d = structured_tools.comparer_ef(spec["indicateur"], mode, banques=banques)
        txt, winner = structured_tools.format_comparaison(d, "millions FCFA", "max")

    if winner is None:
        return None  # rien trouvé pour ces banques → fallback RAG

    sysm = (f"Tu réponds UNIQUEMENT à partir de la comparaison chiffrée fournie (source : "
            f"base SQL exacte, déjà triée). La valeur la plus notable/en tête est : {winner}. "
            f"Présente clairement chaque banque avec sa valeur, dans l'ordre donné, sans "
            f"réordonner ni réinterpréter les chiffres.")
    userm = f"Question : {question}\n\nComparaison :\n{txt}"
    llm   = _get_llm(["etats_financiers"])
    rep   = _invoke_with_retry(llm, [("system", sysm), ("human", userm)])
    mem.add_user(question_memoire or question); mem.add_assistant(rep)
    return rep


def _executer_comparaison_cb_exhaustive(chain: dict, question: str, spec: dict, question_memoire: str = None):
    """Construit le tableau exhaustif par SQL direct, puis fait rédiger UNIQUEMENT la
    conclusion par un LLM avec un prompt minimal (pas le prompt système géant de l'agent
    Conditions Tarifaires, ~10 500 caractères — c'est lui qui, combiné à un tableau large,
    dépassait le budget Groq et forçait une troncature qui perdait des banques/segments
    entiers). Retourne None si aucune donnée trouvée (le RAG prend alors le relais)."""
    mem     = chain["memory"]
    termes  = spec["termes"]
    # PLAFOND ADAPTÉ AU NOMBRE DE BANQUES (2026-07-27). Il était fixe (8), calibré pour le pire
    # cas (7 banques) et donc inutilement sévère sur une comparaison à 2 banques : les 13 offres
    # tarifaires d'ECOBANK étaient coupées à 4, ce qui produit une réponse fausse et pas
    # seulement abrégée. Le tableau étant affiché ENTIER à l'utilisateur (le LLM n'en tire qu'une
    # conclusion de 3-5 lignes, cf. plus bas), le vrai coût d'une ligne supplémentaire est
    # l'affichage, pas le budget Groq — d'où un plafond calculé sur le nombre de banques.
    n_banques = max(1, len(spec["banques"]))
    if len(termes) == 1:
        tableau = structured_tools.tableau_cb_exhaustif(
            spec["banques"], termes[0], max_libelles=max(4, 28 // n_banques))
    else:
        tableau = structured_tools.tableau_cb_multi_service(
            spec["banques"], termes, max_libelles=max(3, 14 // n_banques))
    if not tableau:
        return None

    sysm = ("Tu commentes UNIQUEMENT le tableau chiffré fourni ci-dessous (source : base SQL "
            "exacte, aucune approximation). Ne modifie AUCUN chiffre, ne recopie pas le tableau "
            "en entier (il est déjà affiché à l'utilisateur séparément) — écris seulement une "
            "conclusion de 3 à 5 lignes : nomme la banque la moins chère et la plus chère quand "
            "c'est déterminable, précise si le classement change selon le segment (Particuliers "
            "vs Entreprises), la catégorie de service ou la période, et signale les cas '—' "
            "(donnée non trouvée) sans en inventer la valeur.")
    # L'utilisateur voit le tableau ENTIER ; seule la copie envoyée au LLM est plafonnée. Cette
    # dissociation (2026-07-27) évite le compromis absurde d'avant : rogner l'AFFICHAGE pour
    # tenir dans le budget d'un modèle qui n'écrit qu'une conclusion de 3 lignes. Si le tableau
    # dépasse, la conclusion portera sur un extrait — c'est dit explicitement au LLM pour qu'il
    # ne présente pas son commentaire comme couvrant l'ensemble.
    MAX_TABLEAU_LLM = 9000
    tableau_llm = tableau
    if len(tableau) > MAX_TABLEAU_LLM:
        tableau_llm = (tableau[:MAX_TABLEAU_LLM]
                       + "\n[...] (tableau tronqué ici pour ta lecture uniquement — l'utilisateur "
                         "voit la version complète ; commente ce que tu vois sans prétendre à "
                         "l'exhaustivité)")
        print(f"  [TABLEAU CB] {len(tableau):,} chars affichés, {MAX_TABLEAU_LLM:,} envoyés au LLM")
    userm = f"Question : {question}\n\nTableau :\n{tableau_llm}"
    llm   = _get_llm(["conditions_banque"])
    conclusion = _invoke_with_retry(llm, [("system", sysm), ("human", userm)])

    titre = f"**Comparaison exhaustive — {' / '.join(termes)} ({', '.join(spec['banques'])})**"
    rep = f"{titre}\n{tableau}\n\n**Analyse**\n\n{conclusion}"
    mem.add_user(question_memoire or question); mem.add_assistant(rep)
    return rep


# ═══════════════════════════════════════════════════════════
#  AGENT DE SECOURS — LangChain tool-calling (audit chat 2026-07-25)
# ═══════════════════════════════════════════════════════════
# N'intervient QUE quand les 4 détecteurs regex/mots-clés (_detect_comparatif,
# _detect_factuel_ef_unique, _detect_comparaison_ef_banques, _detect_comparaison_cb_service)
# ET la détection de domaine par mots-clés (detect_types_doc) ont TOUS échoué — c'est-à-dire
# exactement les cas qui finissaient auparavant en rejet "hors périmètre". Il ne peut donc
# JAMAIS dégrader un cas qui fonctionnait déjà (routage regex existant intouché) — il rattrape
# uniquement des cas 100% perdus avant. Si l'agent échoue ou ne trouve aucun outil pertinent,
# on retombe silencieusement sur le comportement d'avant (rejet normal).
def _agent_llm_pour_cle(groq_key: str):
    from langchain_groq import ChatGroq
    return ChatGroq(model=config.GROQ_MODEL, groq_api_key=groq_key,
                     temperature=0, max_tokens=600).bind_tools(agent_tools.ALL_TOOLS)


def _agent_llm_gemini():
    # Même raisonnement coupé qu'ailleurs, et pour la même raison : 600 jetons de sortie
    # seraient intégralement consommés par la réflexion, sans qu'il reste une phrase.
    return _creer_llm_gemini(0).bind_tools(agent_tools.ALL_TOOLS)


def _agent_invoke_avec_rotation(msgs):
    """BUG TROUVÉ en testant (2026-07-25) : la 1ʳᵉ version de l'agent utilisait une SEULE clé
    Groq figée (config.GROQ_API_KEY) — sans la rotation sur 12 clés que le reste de l'app
    utilise déjà (_invoke_with_retry). Résultat observé en direct : la clé par défaut avait déjà
    atteint son quota journalier (99 198/100 000 tokens) à force de tester ce soir, et l'agent
    échouait alors SYSTÉMATIQUEMENT (échec silencieux, sans casser le chat — mais rendant
    l'agent inutile) alors que d'autres clés avaient probablement encore du quota. Fix : même
    rotation que le reste du chat sur 429/quota."""
    # L'agent suit le FOURNISSEUR CHOISI, il n'est plus câblé sur Groq. Sinon, basculer
    # l'application sur Gemini ne serait qu'un demi-passage : cet agent continuerait à
    # consommer le quota Groq — celui-là même que l'on cherchait à quitter — et se tairait
    # une fois ce quota épuisé, sans que rien ne relie sa disparition à la bascule.
    last_err = None
    if config.LLM_PROVIDER == "gemini" and config.GEMINI_API_KEY:
        try:
            llm = _agent_llm_gemini()
            return llm, llm.invoke(msgs)
        except Exception as e:
            last_err = e
            print(f"  [AGENT SECOURS] Gemini indisponible ({str(e)[:80]}) — essai des clés Groq")

    # Repli sur Groq : les clés restent renseignées, autant s'en servir plutôt que de
    # renoncer. La rotation sur les 12 clés reste utile ici (voir plus bas).
    for key in (config.GROQ_API_KEYS or [config.GROQ_API_KEY]):
        if not key:
            continue
        try:
            llm = _agent_llm_pour_cle(key)
            return llm, llm.invoke(msgs)
        except Exception as e:
            last_err = e
            continue
    raise last_err or RuntimeError("Aucun modèle disponible pour l'agent de secours.")


def _agent_secours(question: str, mem) -> str | None:
    """Tente de répondre via un outil déterministe (structured_tools, même source SQL que le
    reste de l'app) quand aucun détecteur existant n'a reconnu la question. Retourne None si
    l'agent ne trouve aucun outil pertinent OU en cas d'erreur — jamais d'exception qui remonte
    à ask(), pour garantir zéro régression sur le chemin existant."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
        sysm = ("Tu choisis UNIQUEMENT parmi les outils fournis pour répondre à une question "
                "bancaire ivoirienne (7 banques : SGCI, BICICI, BNI, ECOBANK, NSIA, SIB, BACI). "
                "Si AUCUN outil ne correspond clairement à la question, NE FAIS AUCUN appel d'outil.")
        msgs = [SystemMessage(sysm), HumanMessage(question)]
        llm, resp = _agent_invoke_avec_rotation(msgs)
        if not getattr(resp, "tool_calls", None):
            return None   # aucun outil jugé pertinent → laisse ask() gérer le rejet normal

        appel = resp.tool_calls[0]
        outil = next((t for t in agent_tools.ALL_TOOLS if t.name == appel["name"]), None)
        if not outil:
            return None
        resultat = outil.invoke(appel["args"])

        # Synthèse finale : le LLM rédige UNIQUEMENT à partir du résultat de l'outil (même
        # discipline anti-invention que le reste de l'app — pas de calcul ni d'ajout personnel).
        # Même clé que celle qui a réussi l'appel précédent (déjà validée disponible à l'instant).
        msgs.append(resp)
        msgs.append(ToolMessage(content=str(resultat), tool_call_id=appel["id"]))
        msgs.append(HumanMessage("Rédige la réponse finale en français, UNIQUEMENT à partir du "
                                  "résultat de l'outil ci-dessus — ne recalcule rien, n'ajoute "
                                  "aucun chiffre absent de ce résultat."))
        try:
            final = llm.invoke(msgs)
        except Exception:
            _, final = _agent_invoke_avec_rotation(msgs)   # re-rotation si la clé a expiré entre-temps
        reponse = _texte_reponse(final).strip()
        if not reponse:
            return None
        print(f"  [AGENT SECOURS] Outil '{appel['name']}' utilisé (question non reconnue par les détecteurs existants).")
        mem.add_user(question); mem.add_assistant(reponse)
        return reponse
    except Exception as e:
        print(f"  [AGENT SECOURS] Échec silencieux ({e}) — retombe sur le comportement normal.")
        return None


# ═══════════════════════════════════════════════════════════
#  BRANCHE ÉVOLUTION EF — 1 banque + 1 indicateur, série annuelle (2026-07-27)
# ═══════════════════════════════════════════════════════════

def _detect_evolution_ef(question: str):
    """« Comment a évolué le PNB de SGCI ? » — 1 banque nommée + 1 indicateur EF + intention
    d'évolution. Sans cette branche, la question partait au RAG, qui a répondu avec une année
    tirée d'une colonne N-1, deux années réelles déclarées « non disponibles » et un chiffre
    arrondi. Une série annuelle est un GROUP BY : rien à deviner."""
    if not retriever.is_evolution(question):
        return None
    banques = retriever.detect_banques(question)
    if len(banques) != 1:
        return None
    q = _normaliser(question)
    for key in _EF_KEYS:
        # ROE et coefficient d'exploitation sont des ratios calculés, pas des lignes de bilan :
        # leur série demanderait de croiser deux indicateurs année par année. Laissés au RAG
        # pour l'instant plutôt que de renvoyer une série fausse.
        if key in q and key not in ("roe", "rentabilité", "rentabilite", "return on equity",
                                    "coefficient d'exploitation", "coefficient d exploitation"):
            return {"banque": banques[0], "indicateur": key}
    return None


def _executer_evolution_ef(chain: dict, question: str, spec: dict, question_memoire: str = None):
    """Série SQL exacte + rédaction LLM. None si la base n'a pas assez de points."""
    mem   = chain["memory"]
    serie = structured_tools.serie_ef(spec["banque"], spec["indicateur"])
    if len(serie) < 2:
        return None      # une évolution demande au moins 2 points → RAG en secours
    label   = _EF_LABELS.get(spec["indicateur"], spec["indicateur"])
    tableau = structured_tools.format_serie_ef(spec["banque"], label, serie)
    print(f"  [ÉVOLUTION EF] {spec['banque']} — {label} : {len(serie)} exercices (SQL exact).")
    sysm = ("Tu commentes UNIQUEMENT le tableau d'évolution fourni (source SQL exacte, variations "
            "déjà calculées). Ne recalcule rien, n'arrondis AUCUN chiffre, n'ajoute aucune année "
            "absente du tableau. Recopie le tableau tel quel, puis ajoute 3 à 5 lignes d'analyse : "
            "tendance générale, année la plus marquante, rythme de croissance.")
    llm = _get_llm(["etats_financiers"])
    rep = _invoke_with_retry(llm, [("system", sysm), ("human", f"Question : {question}\n\n{tableau}")])
    mem.add_user(question_memoire or question); mem.add_assistant(rep)
    return rep


# ═══════════════════════════════════════════════════════════
#  BRANCHE « MEILLEURE BANQUE » — SYNTHÈSE MULTICRITÈRE (2026-07-27)
# ═══════════════════════════════════════════════════════════
# La question la plus naturelle qu'un dirigeant pose — et justement la SEULE qui n'avait
# aucune route. _detect_comparatif() exige un indicateur nommé (PNB, ROE, résultat net...) ;
# « quelle est la meilleure banque ? » n'en nomme aucun, donc retournait None et tombait dans
# le RAG générique. Or « la meilleure banque » n'est pas une information à retrouver dans un
# document : c'est une SYNTHÈSE multicritère. Le retrieval sémantique ne peut structurellement
# pas y répondre — il cherche des chunks dont le texte ressemble à la question, et aucun
# libellé de bilan ne ressemble à « meilleure banque ». D'où les réponses au hasard.
# Même diagnostic et même remède que pour « propose une stratégie » le 2026-07-25 : router
# vers les données DÉJÀ CALCULÉES plutôt que vers le RAG.
_RACINES_SUPERLATIF = ("meilleur", "meilleure", "mieux", "plus performant", "plus solide",
                       "plus fiable", "numero 1", "numero un", "n°1", "top banque",
                       "laquelle choisir", "quelle choisir", "plus interessante",
                       "recommandes-tu", "recommande-tu", "conseilles-tu", "laquelle est la")
_RACINES_BANQUE_GEN = ("banqu", "etablissement bancaire", "banks")


def _detect_meilleure_banque(question: str) -> bool:
    """Superlatif + notion de banque, SANS indicateur précis nommé (sinon _detect_comparatif,
    qui passe avant, a déjà pris la main avec un classement mono-critère plus exact).
    Tolérant aux fautes via les racines : « MEILLEUR BANQU » matche comme « meilleure banque »."""
    q = _normaliser(question)
    if not _contient_racine(q, _RACINES_SUPERLATIF) or not _contient_racine(q, _RACINES_BANQUE_GEN):
        return False
    # Un indicateur explicitement nommé => question mono-critère, laisser les branches précises.
    if any(k in q for k in _EF_KEYS):
        return False
    # « meilleure banque pour une PME exportatrice » : question de recommandation CLIENT, qui
    # dépend des tarifs et du besoin, pas du classement de performance des banques. On la laisse
    # au chemin RAG/recommandation existant, qui sait croiser tarifs et réglementation.
    if _contient_racine(q, ("pour une pme", "pour mon entreprise", "pour une startup",
                            "pour un particulier", "pour une association", "pour importer",
                            "pour exporter", "pour un pret", "pour un credit")):
        return False
    return True


def _executer_meilleure_banque(chain: dict, question: str, question_memoire: str = None) -> str | None:
    """Classement multicritère déterministe (SQL) + rédaction LLM. Retourne None si la base
    ne permet aucun classement — on retombe alors sur le chemin normal, jamais d'échec dur."""
    mem = chain["memory"]
    try:
        classement = fiche_marche.classement_multicritere()
    except Exception as e:
        print(f"  [MEILLEURE BANQUE] Classement indisponible ({e}) — retour au chemin normal.")
        return None
    if not classement:
        return None

    print("  [MEILLEURE BANQUE] Classement multicritère SQL (déterministe) — sans RAG.")
    sysm = (
        "Tu es un analyste bancaire. Réponds à la question UNIQUEMENT à partir du classement "
        "chiffré fourni (source : base SQL exacte, déjà calculé et déjà trié). "
        "N'invente AUCUN chiffre, ne recalcule aucun classement. "
        "Structure : (1) la banque en tête et son score, (2) le podium complet, (3) une phrase "
        "par critère pour expliquer QUI domine sur QUOI, (4) la nuance finale : le meilleur "
        "choix dépend de l'objectif poursuivi. Réponds en français, clair et direct.\n"
        # Ajouté le 2026-07-27 après un test en direct : le LLM a écrit « pour l'efficience, SGCI
        # se distingue » alors que la ligne détaillée classait SIB 1re — il avait écarté SIB de
        # TOUS les critères parce qu'elle était signalée absente du score global. D'où cette
        # consigne explicite : le 1er d'une ligne de critère se recopie, il ne se déduit pas.
        "RÈGLE ABSOLUE pour le point (3) : pour chaque critère, la banque qui domine est celle "
        "écrite EN PREMIER sur la ligne de ce critère — recopie-la telle quelle, même si elle "
        "est absente du classement global (une banque écartée du score global reste exacte dans "
        "les critères où elle est mesurée)."
    )
    userm = f"Question : {question}\n\n{classement}"
    llm = _get_llm(["etats_financiers"])      # température factuelle
    rep = _invoke_with_retry(llm, [("system", sysm), ("human", userm)])
    mem.add_user(question_memoire or question); mem.add_assistant(rep)
    return rep


# ═══════════════════════════════════════════════════════════
#  POINT D'ENTRÉE — ROUTEUR MULTI-LABEL
# ═══════════════════════════════════════════════════════════

_SALUTATIONS = ("bonjour", "bonsoir", "salut", "hello", "hi", "coucou", "bsr", "cc",
                "bonne journee", "bonne soiree", "merci", "ok merci", "au revoir",
                # AJOUTÉ le 2026-07-27 : « bjr » se faisait rejeter "hors périmètre" alors que
                # « bsr » était bien dans la liste — une abréviation oubliée suffisait à donner
                # au directeur l'impression d'un outil cassé dès le premier message.
                "bjr", "slt", "cc les amis", "yo", "hey", "salutations", "bjr a tous",
                "bonjour a tous", "hello a tous", "ca va", "comment ca va", "merci beaucoup",
                "ok", "d accord", "parfait", "super", "a bientot", "bye", "bonne nuit")


def _est_salutation_seule(question: str) -> bool:
    """BUG TROUVÉ (2026-07-25, signalé par le directeur en testant) : « Bonjour » tout seul
    déclenchait le rejet "hors périmètre" — aucun mot-clé bancaire, aucune banque nommée, donc
    la question tombait dans la branche "hors sujet" alors qu'il ne s'agit que d'une salutation.
    Détection : la question ENTIÈRE (après nettoyage ponctuation) est une salutation courte —
    ne matche jamais une vraie question bancaire qui contiendrait aussi ces mots en début de
    phrase (ex. "Bonjour, quel est le PNB de SGCI ?" a bien plus de mots ET un mot-clé EF, donc
    passe par le chemin normal, pas celui-ci).

    2026-07-27 : liste élargie + comparaison APPROCHÉE. Une liste exacte est condamnée à être
    incomplète (« bjr » manquait), et chaque manque produit un rejet "hors périmètre" brutal
    sur un simple bonjour. difflib rattrape les variantes non prévues (« bnjour », « salu »,
    « bonsoirr ») sans risque de faux positif : on ne teste que des messages de 3 mots maximum,
    et une vraie question bancaire de 3 mots ne ressemble à aucune salutation (ratio 0.85)."""
    q = _normaliser(question).rstrip("!?. ").replace("'", " ").strip()
    if not q or len(q.split()) > 3:
        return False
    if q in _SALUTATIONS:
        return True
    import difflib
    return bool(difflib.get_close_matches(q, _SALUTATIONS, n=1, cutoff=0.85))


def ask(chain: dict, question: str) -> str:
    """Point d'entrée unique — routing multi-label automatique."""
    if _est_salutation_seule(question):
        # BUG TROUVÉ le 2026-07-27 (reproduit à partir d'une capture du directeur) : cette
        # branche écrivait la salutation dans la mémoire (mem.add_user/add_assistant), ce qui
        # en faisait un VRAI tour de conversation. Conséquence en cascade sur la question
        # SUIVANTE : _resoudre_question_suivi() voyait un historique non vide et transformait
        # « JE VEUX SAVOIR QELLE ST LA MEILLEUR BANQU » en « ... [Contexte de la question
        # précédente : bonjour] », ce qui activait est_suivi_scope, forçait les domaines
        # CB+EF et envoyait cette bouillie en recherche vectorielle — d'où la réponse sur les
        # prêts subordonnés BICICI. Un « bonjour » n'est pas un sujet : il ne doit RIEN laisser
        # dans la mémoire, sinon il pollue tout ce qui suit.
        return ("Bonjour ! Je suis l'assistant SpyBusiness — posez-moi une question sur les "
                "tarifs, la performance financière ou la réglementation des 7 banques ivoiriennes "
                "(BACI, BICICI, BNI, ECOBANK, NSIA, SIB, SGCI).")

    mem = chain["memory"]

    def _essayer_detecteurs(q_detect: str, q_mem: str = None):
        """Passe q_detect dans les 4 détecteurs déterministes (+ « meilleure banque »).
        Retourne la réponse, ou None si aucun ne s'applique / ne trouve de données.
        q_mem : ce qu'on écrit dans la mémoire (la question ORIGINALE de l'utilisateur, pour
        qu'un enrichissement de suivi ne s'empile pas d'un tour à l'autre)."""
        spec = _detect_comparatif(q_detect)
        if spec:
            return _executer_comparatif(chain, q_detect, spec, question_memoire=q_mem)

        if _detect_meilleure_banque(q_detect):
            rep = _executer_meilleure_banque(chain, q_detect, question_memoire=q_mem)
            if rep:
                return rep

        spec_evo = _detect_evolution_ef(q_detect)
        if spec_evo:
            rep = _executer_evolution_ef(chain, q_detect, spec_evo, question_memoire=q_mem)
            if rep:
                return rep

        spec_unique = _detect_factuel_ef_unique(q_detect)
        if spec_unique:
            return _executer_factuel_ef_unique(chain, q_detect, spec_unique, question_memoire=q_mem)

        spec_ef_banques = _detect_comparaison_ef_banques(q_detect)
        if spec_ef_banques:
            rep = _executer_comparaison_ef_banques(chain, q_detect, spec_ef_banques, question_memoire=q_mem)
            if rep:
                return rep
            # Rien trouvé en base pour ces banques → on laisse la suite décider

        spec_cb_exh = _detect_comparaison_cb_service(q_detect)
        if spec_cb_exh:
            rep = _executer_comparaison_cb_exhaustive(chain, q_detect, spec_cb_exh, question_memoire=q_mem)
            if rep:
                return rep
        return None

    rep = _essayer_detecteurs(question)
    if rep:
        return rep

    # 2ᵉ PASSE SUR LA QUESTION ENRICHIE (2026-07-27, trouvé par la batterie de test).
    # INCOHÉRENCE CONSTATÉE : « Frais de tenue de compte ECOBANK 2024 S1 ? » listait les 13
    # offres tarifaires ; la MÊME demande formulée en suivi (« Et pour ECOBANK ? » après une
    # question sur BNI) répondait « non disponible dans le contexte fourni ». Rien de plus
    # décrédibilisant qu'un outil qui affirme ne pas savoir ce qu'il vient d'afficher.
    # Cause : les détecteurs déterministes tournaient sur la question BRUTE. « Et pour
    # ECOBANK ? » ne nomme qu'une banque et aucun service → _detect_comparaison_cb_service
    # (qui exige un service + 2 banques) ne se déclenchait pas. La question partait donc dans
    # le RAG générique, qui pour 2 banques ne garde que 7 chunks chacune — insuffisant pour
    # 13 offres, d'où la réponse « non disponible » sur des données bien présentes.
    # Un suivi mérite exactement le même traitement déterministe qu'une question directe :
    # on rejoue donc les détecteurs sur le texte ENRICHI du contexte précédent.
    question_enrichie = _resoudre_question_suivi(question, mem)
    if question_enrichie != question:
        rep = _essayer_detecteurs(question_enrichie, q_mem=question)
        if rep:
            print("  [SUIVI DÉTERMINISTE] Détecteur déclenché sur la question enrichie.")
            return rep

    types_actifs = retriever.detect_types_doc(question)
    types_actifs = retriever.detect_types_doc(question)

    # Essai avec contexte de suivi
    est_suivi_scope = False
    if not types_actifs:
        question_elargie = _resoudre_question_suivi(question, mem)
        if question_elargie != question:
            types_actifs = retriever.detect_types_doc(question_elargie)
            # BUG TROUVÉ le 2026-07-22 (testé en direct, reproduit) : « Et en 2025 ? » après
            # « Et pour ECOBANK ? » — un suivi tout aussi légitime — se faisait rejeter comme
            # « hors périmètre » plus bas, car mem.get_last_question() ne remonte qu'À LA
            # QUESTION PRÉCÉDENTE (elle-même un suivi sans banque/sujet propre), donc le texte
            # enrichi ne contenait toujours aucun mot-clé CB/EF détectable. On retient ici qu'on
            # est dans un VRAI suivi (conversation bancaire déjà engagée) pour ne pas rejeter la
            # question plus bas juste parce qu'elle ne se suffit pas à elle-même.
            est_suivi_scope = True

    # Fallback : question générale bancaire → tous les domaines
    if not types_actifs:
        q = question.lower()
        # 2026-07-27 : comparaison sur la forme NORMALISÉE des deux côtés (casse + accents).
        # Avant, un directeur tapant « SOCIETE GENERALE » en majuscules sans accent ne matchait
        # pas l'alias « société générale » — sa banque n'était donc pas reconnue.
        q_norm = _normaliser(question)
        banques_mentionnees = any(_normaliser(a) in q_norm for a in config.BANQUE_ALIASES)

        # AVANT tout le reste (2026-07-25, audit chat #5) : si AUCUNE banque précise n'est
        # nommée et que la question ressemble à une comparaison/analyse cross-banques, tenter
        # l'agent LangChain d'abord. BUG TROUVÉ en testant : placer cet essai APRÈS le test
        # `mots_bancaires` (ex. "banque" substring de "banques") faisait que la quasi-totalité
        # des questions bancaires y étaient interceptées avant d'atteindre l'agent — puisque le
        # mot "banque(s)" est présent dans presque toute question du domaine. Reproduit : "Classe
        # les banques ivoiriennes... efficiente opérationnellement" partait dans le RAG générique
        # multi-banques, qui confondait "efficience" avec "Autres produits d'exploitation
        # bancaire" (mauvais indicateur, classement faux) — alors que l'agent choisit directement
        # l'outil coefficient d'exploitation (déterministe, exact). Les questions avec banque(s)
        # précise(s) nommée(s) NE PASSENT PAS ici (banques_mentionnees déjà géré ailleurs par les
        # détecteurs déterministes) — cette tentative ne concerne QUE le cas générique "toutes les
        # banques / classement / analyse" sans nom précis, avant de retomber sur le RAG existant.
        if not banques_mentionnees and (retriever.is_recommandation_ou_analyse(question)
                                         or retriever.is_comparaison(question)):
            rep_agent = _agent_secours(question, chain["memory"])
            if rep_agent:
                return rep_agent

        # 2026-07-27 : RACINES au lieu de mots entiers. « BANQU » (tronqué par une frappe
        # rapide) ne contenait pas « banque » et faisait basculer la question dans le rejet
        # "hors périmètre" — un caractère manquant suffisait à rendre le chat inutilisable.
        mots_bancaires = ["banqu", "bancaire", "compte", "credit", "pret",
                          "investissement", "financement", "tarif", "frais", "taux",
                          "epargne", "depot", "guichet", "agence", "carte"]
        if banques_mentionnees or _contient_racine(q_norm, mots_bancaires):
            types_actifs = ["conditions_banque", "etats_financiers"]
        elif retriever.is_recommandation_ou_analyse(question) or retriever.is_comparaison(question):
            types_actifs = ["conditions_banque", "etats_financiers", "reglementation"]
        elif est_suivi_scope:
            # Suivi court (« et en 2025 ? », « et pour telle banque ? ») dans une conversation
            # bancaire déjà engagée — reste bancaire même sans mot-clé propre à CETTE question.
            types_actifs = ["conditions_banque", "etats_financiers"]
        else:
            # AUCUN signal bancaire détecté (pas de banque nommée, pas de mot-clé
            # bancaire, pas une comparaison/recommandation) → question hors du domaine
            # de l'outil (ex. "quelle est la capitale de la Côte d'Ivoire ?"). Avant ce
            # garde-fou, ces questions tombaient quand même dans une recherche CB/EF (qui
            # ne trouvait rien de pertinent) et le LLM répondait de sa propre culture
            # générale, SANS grounding — constaté incohérent d'un appel à l'autre
            # (Abidjan puis Yamoussoukro pour la même question). Un outil d'intelligence
            # bancaire pro doit dire clairement qu'il sort de son périmètre plutôt que
            # de deviner une réponse non vérifiée.

            # DERNIER RECOURS (2026-07-25, audit chat #5) : avant de rejeter, tente l'agent
            # LangChain avec de vrais outils SQL déterministes — il rattrape les formulations
            # que les 4 détecteurs regex + detect_types_doc n'ont pas reconnues (ex. synonyme
            # non prévu, tournure inhabituelle). Ne peut jamais dégrader un cas qui marchait
            # déjà : on n'arrive ICI que quand tout le reste a déjà échoué.
            rep_agent = _agent_secours(question, chain["memory"])
            if rep_agent:
                return rep_agent

            mem_ = chain["memory"]
            # 2026-07-25 (audit chat, problème #12) : message différencié selon qu'une
            # conversation bancaire était déjà engagée ou non — dans le 1er cas, la question a
            # pu être mal formulée/mal reconnue plutôt que vraiment hors sujet ; le message le
            # signale et invite à reformuler au lieu d'un refus sec identique dans tous les cas.
            if mem_.get_last_question():
                rep = ("Je n'ai pas réussi à rattacher cette question au sujet bancaire en cours "
                       "(tarifs, finances ou réglementation des 7 banques). Peux-tu reformuler en "
                       "précisant la banque, l'indicateur ou le service concerné ?")
            else:
                rep = ("Cette question sort du périmètre de SpyBusiness (intelligence "
                       "concurrentielle bancaire ivoirienne — tarifs, performance financière, "
                       "réglementation des 7 banques). Je ne peux pas y répondre de façon fiable.")
            mem_.add_user(question); mem_.add_assistant(rep)
            return rep

    return _executer(chain, question, types_actifs)


# ═══════════════════════════════════════════════════════════
#  TEST RAPIDE
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 65)
    print("  TEST RAG SPYBUSINESS — AGENTS PARALLÈLES (Gemini)")
    print("=" * 65)

    chain = init_chain()

    questions_test = [
        "Quels sont les frais de tenue de compte SGCI pour les particuliers en 2024 S1 ?",
        "Quel est le résultat net de SGCI en 2024 ?",
        "Comparer les frais de virement entre toutes les banques en 2025",
        "Quelle banque est la plus avantageuse pour une PME exportatrice ?",
    ]

    for question in questions_test:
        print(f"\n❓ {question}")
        print("─" * 55)
        reponse = ask(chain, question)
        print(f"\nRÉPONSE :\n{reponse}")
        print("─" * 65)
