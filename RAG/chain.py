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

    # Gemini (défaut)
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model              = config.GEMINI_MODEL,
        google_api_key     = config.GEMINI_API_KEY,
        temperature        = temp,
        max_output_tokens  = config.LLM_MAX_TOKENS,
    )


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
#  RETRY AVEC BACKOFF EXPONENTIEL
# ═══════════════════════════════════════════════════════════

_groq_key_index = 0  # index courant dans la rotation des clés

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

    for attempt in range(max_retries):
        try:
            return current_llm.invoke(messages).content
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

            if attempt >= max_retries - 1:
                return f"Erreur après {max_retries} tentatives : {err[:150]}"

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
            else:
                return f"Erreur : {err[:200]}"
    return "Erreur : nombre maximum de tentatives atteint."


# ═══════════════════════════════════════════════════════════
#  RÉSOLUTION DES QUESTIONS DE SUIVI
# ═══════════════════════════════════════════════════════════

def _resoudre_question_suivi(question: str, mem) -> str:
    q_low = question.strip().lower()
    mots  = q_low.split()
    has_banque = any(alias in q_low for alias in config.BANQUE_ALIASES)
    has_annee  = bool(re.search(r"\b202[0-9]\b", question))

    if len(mots) <= 10 and not has_banque and not has_annee:
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

def _formater_contexte_sections(chunks_par_agent: dict, regl_chunks: list, niveau: int) -> str:
    sections = [
        f"[NIVEAU DE CONFIANCE ANALYTIQUE : {niveau}]\n"
        f"1=Factuel | 2=Analytique | 3=Prospectif (ancrage régl. obligatoire) | 4=Refus propre"
    ]

    for type_doc, chunks in chunks_par_agent.items():
        if chunks:
            label = _AGENT_LABELS.get(type_doc, type_doc.upper())
            sep   = "═" * 50
            bloc  = retriever.format_context(chunks)
            sections.append(f"{sep}\n{label} ({len(chunks)} sources)\n{sep}\n{bloc}")

    if regl_chunks:
        sep  = "═" * 50
        bloc = retriever.format_context(regl_chunks)
        sections.append(
            f"{sep}\nTEXTES RÉGLEMENTAIRES APPLICABLES (enrichissement niveau 3)\n{sep}\n{bloc}"
        )

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
        lignes.append(f"  - {label} : {val_fmt} {unite} → rang {rang}/{len(items)} parmi les banques comparables")
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
            if len(context) > config.MAX_CONTEXT_CHARS_COMPARAISON:
                SEP = "═" * 55
                sections = [s for s in context.split(SEP) if s.strip()]
                n_sections = max(1, len(sections))
                chars_par_section = config.MAX_CONTEXT_CHARS_COMPARAISON // n_sections
                context = "\n".join(SEP + s[:chars_par_section] for s in sections)

        print(f"  Contexte réduit : {len(context):,} chars")

    # 6c. Filet de sécurité final — truncature équitable par section
    if len(context) > config.MAX_CONTEXT_CHARS:
        SEP = "═" * 55
        sections = [s for s in context.split(SEP) if s.strip()]
        n_sections = max(1, len(sections))
        chars_par_section = config.MAX_CONTEXT_CHARS // n_sections
        context = "\n".join(SEP + s[:chars_par_section] for s in sections)
        print(f"  Contexte tronqué ({n_sections} sections × {chars_par_section} chars) : {len(context):,} chars")

    # 6d. Question analytique sur UNE SEULE banque ("X est-elle solide/compétitive ?") :
    # injecter la fiche de synthèse chiffrée ET CLASSÉE (ROE, coefficient d'exploitation,
    # PNB, résultat net) en tête de contexte. Placé APRÈS toute réduction (6b/6c) — un essai
    # précédent l'injectait avant 6b, mais la branche "banque unique" y reconstruit le
    # contexte ENTIER à partir des chunks bruts, écrasant silencieusement la fiche. Ici,
    # elle survit forcément, et le garde-fou dynamique (8b) mesure la taille réelle après
    # coup — sans ça le LLM n'a que le bilan brut de CETTE banque, sans repère face aux 6
    # autres, et conclut à tort "impossible de juger la compétitivité" alors que ces
    # données comparatives (ROE, coefficient d'exploitation) existent déjà dans l'app.
    if niveau >= 2 and "etats_financiers" in types_actifs:
        banques_uniques = retriever.detect_banques(question_retrieval)
        if len(banques_uniques) == 1:
            fiche = _fiche_synthese_bancaire(banques_uniques[0])
            if fiche:
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
        for _ in range(3):
            total_chars = sum(len(m.content) for m in messages)
            est_tokens  = total_chars / CHARS_PAR_TOKEN
            if est_tokens <= BUDGET_INPUT:
                break
            chars_a_retirer = int((est_tokens - BUDGET_INPUT) * CHARS_PAR_TOKEN) + 200
            nouveau_contexte = context[:max(100, len(context) - chars_a_retirer)]
            print(f"  [GARDE-FOU] Prompt réel ≈{est_tokens:.0f} tok > budget {BUDGET_INPUT} — "
                  f"contexte {len(context):,} → {len(nouveau_contexte):,} chars")
            context  = nouveau_contexte
            messages = prompt_template.format_messages(
                context  = context,
                history  = history,
                question = question,
                disponibilite_ef = retriever.texte_disponibilite_ef(),
            )

    temp_used = (config.LLM_TEMPERATURE_FACTUEL
                 if all(t in {"conditions_banque", "etats_financiers"} for t in types_actifs)
                 else config.LLM_TEMPERATURE_ANALYTIQUE)
    print(f"  Génération ({config.LLM_PROVIDER} T={temp_used}) — {len(context):,} chars contexte...")

    reponse = _invoke_with_retry(llm, messages)

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
            "coefficient d'exploitation", "coefficient d exploitation")


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


def _executer_comparatif(chain: dict, question: str, spec: dict) -> str:
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
        mem.add_user(question); mem.add_assistant(rep)
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
    mem.add_user(question); mem.add_assistant(rep)
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
    if len(question.split()) > 14:
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
}


def _executer_factuel_ef_unique(chain: dict, question: str, spec: dict) -> str:
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
    mem.add_user(question); mem.add_assistant(rep)
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
    if len(banques) < 2:
        return None
    q = question.lower()
    if any(k in q for k in _EF_KEYS):
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


def _executer_comparaison_ef_banques(chain: dict, question: str, spec: dict):
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
    mem.add_user(question); mem.add_assistant(rep)
    return rep


def _executer_comparaison_cb_exhaustive(chain: dict, question: str, spec: dict):
    """Construit le tableau exhaustif par SQL direct, puis fait rédiger UNIQUEMENT la
    conclusion par un LLM avec un prompt minimal (pas le prompt système géant de l'agent
    Conditions Tarifaires, ~10 500 caractères — c'est lui qui, combiné à un tableau large,
    dépassait le budget Groq et forçait une troncature qui perdait des banques/segments
    entiers). Retourne None si aucune donnée trouvée (le RAG prend alors le relais)."""
    mem     = chain["memory"]
    termes  = spec["termes"]
    if len(termes) == 1:
        tableau = structured_tools.tableau_cb_exhaustif(spec["banques"], termes[0], max_libelles=8)
    else:
        tableau = structured_tools.tableau_cb_multi_service(spec["banques"], termes, max_libelles=4)
    if not tableau:
        return None

    sysm = ("Tu commentes UNIQUEMENT le tableau chiffré fourni ci-dessous (source : base SQL "
            "exacte, aucune approximation). Ne modifie AUCUN chiffre, ne recopie pas le tableau "
            "en entier (il est déjà affiché à l'utilisateur séparément) — écris seulement une "
            "conclusion de 3 à 5 lignes : nomme la banque la moins chère et la plus chère quand "
            "c'est déterminable, précise si le classement change selon le segment (Particuliers "
            "vs Entreprises), la catégorie de service ou la période, et signale les cas '—' "
            "(donnée non trouvée) sans en inventer la valeur.")
    userm = f"Question : {question}\n\nTableau :\n{tableau}"
    llm   = _get_llm(["conditions_banque"])
    conclusion = _invoke_with_retry(llm, [("system", sysm), ("human", userm)])

    titre = f"**Comparaison exhaustive — {' / '.join(termes)} ({', '.join(spec['banques'])})**"
    rep = f"{titre}\n{tableau}\n\n**Analyse**\n\n{conclusion}"
    mem.add_user(question); mem.add_assistant(rep)
    return rep


# ═══════════════════════════════════════════════════════════
#  POINT D'ENTRÉE — ROUTEUR MULTI-LABEL
# ═══════════════════════════════════════════════════════════

def ask(chain: dict, question: str) -> str:
    """Point d'entrée unique — routing multi-label automatique."""
    spec = _detect_comparatif(question)
    if spec:                                  # branche comparative déterministe
        return _executer_comparatif(chain, question, spec)

    spec_unique = _detect_factuel_ef_unique(question)
    if spec_unique:                           # branche factuelle mono-banque déterministe
        return _executer_factuel_ef_unique(chain, question, spec_unique)

    spec_ef_banques = _detect_comparaison_ef_banques(question)
    if spec_ef_banques:                       # branche comparaison EF par banques nommées
        rep = _executer_comparaison_ef_banques(chain, question, spec_ef_banques)
        if rep:
            return rep
        # Rien trouvé en base pour ces banques → fallback RAG normal ci-dessous

    spec_cb_exh = _detect_comparaison_cb_service(question)
    if spec_cb_exh:                           # branche comparaison CB exhaustive déterministe
        rep = _executer_comparaison_cb_exhaustive(chain, question, spec_cb_exh)
        if rep:
            return rep
        # Rien trouvé en base pour ce terme/ces banques → fallback RAG normal ci-dessous

    mem          = chain["memory"]
    types_actifs = retriever.detect_types_doc(question)

    # Essai avec contexte de suivi
    if not types_actifs:
        question_elargie = _resoudre_question_suivi(question, mem)
        if question_elargie != question:
            types_actifs = retriever.detect_types_doc(question_elargie)

    # Fallback : question générale bancaire → tous les domaines
    if not types_actifs:
        q = question.lower()
        banques_mentionnees = any(a in q for a in config.BANQUE_ALIASES)
        mots_bancaires = ["banque", "bancaire", "compte", "crédit", "credit",
                          "pret", "prêt", "investissement", "financement"]
        if banques_mentionnees or any(m in q for m in mots_bancaires):
            types_actifs = ["conditions_banque", "etats_financiers"]
        elif retriever.is_recommandation_ou_analyse(question) or retriever.is_comparaison(question):
            types_actifs = ["conditions_banque", "etats_financiers", "reglementation"]
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
            mem_ = chain["memory"]
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
