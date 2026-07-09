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
    - 429 TPM/RPM : attente 30s puis retry même clé
    - 429 TPD (journalier) : bascule sur clé suivante automatiquement
    """
    global _groq_key_index
    n_keys = len(config.GROQ_API_KEYS) if config.LLM_PROVIDER == "groq" else 1
    if max_retries is None:
        max_retries = max(4, n_keys * 2)

    current_llm = llm  # copie locale pour permettre la rotation

    for attempt in range(max_retries):
        try:
            return current_llm.invoke(messages).content
        except Exception as e:
            err = str(e)
            is_tpd      = "tokens per day" in err.lower() or "per day" in err.lower()
            is_tpm      = ("429" in err or "rate limit" in err.lower()) and not is_tpd
            is_resource = "RESOURCE_EXHAUSTED" in err or "resource_exhausted" in err.lower()

            if attempt >= max_retries - 1:
                return f"Erreur après {max_retries} tentatives : {err[:150]}"

            if (is_tpd or is_resource) and config.LLM_PROVIDER == "groq" and n_keys > 1:
                _groq_key_index = (_groq_key_index + 1) % n_keys
                new_key = config.GROQ_API_KEYS[_groq_key_index]
                print(f"  [ROTATION] TPD → clé K{_groq_key_index+1}")
                from langchain_groq import ChatGroq
                temp = getattr(current_llm, 'temperature', 0.1)
                current_llm = ChatGroq(model=config.GROQ_MODEL, groq_api_key=new_key,
                                       temperature=temp, max_tokens=config.LLM_MAX_TOKENS)
            elif is_tpm:
                wait = 30
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
    if question_retrieval != question:
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
        banque_det   = retriever.detect_banque(question_retrieval)
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
            # Comparaison multi-banques CB : 1 chunk/banque le plus pertinent
            k_par_banque = 1
            print(f"  Contexte {len(context):,} > {config.MAX_CONTEXT_CHARS} — comparaison k={k_par_banque}/banque...")
            chunks_cmp = []
            for td in [t for t in chunks_par_agent if t != "reglementation"]:
                for banque in config.BANQUES_OFFICIELLES:
                    filters = retriever.build_filters(banque=banque, annee=annee_det,
                                                      type_doc=td, semestre=semestre_det, cible=cible_det)
                    bank_chunks = retriever.search(
                        vectorstore, question_retrieval, k=k_par_banque, filters=filters)
                    chunks_cmp.extend(bank_chunks)
            chunks_par_agent_r = {td: chunks_cmp for td in chunks_par_agent if td != "reglementation"}
            if "reglementation" in chunks_par_agent:
                chunks_par_agent_r["reglementation"] = retriever.search_reglementation(
                    vectorstore, question, k=3)
            regl_r  = retriever.search_reglementation(vectorstore, question, k=2) if regl_chunks else []
            context = _formater_contexte_sections(chunks_par_agent_r, regl_r, niveau)

        print(f"  Contexte réduit : {len(context):,} chars")

    # 6c. Filet de sécurité final — truncature équitable par section
    if len(context) > config.MAX_CONTEXT_CHARS:
        SEP = "═" * 55
        sections = [s for s in context.split(SEP) if s.strip()]
        n_sections = max(1, len(sections))
        chars_par_section = config.MAX_CONTEXT_CHARS // n_sections
        context = "\n".join(SEP + s[:chars_par_section] for s in sections)
        print(f"  Contexte tronqué ({n_sections} sections × {chars_par_section} chars) : {len(context):,} chars")

    # 7. Prompt adaptatif
    type_prompt     = _choisir_prompt(types_actifs, niveau)
    prompt_template = prompts.get_prompt(type_prompt)
    if config.SHOW_QUERY_DEBUG:
        print(f"  Prompt : {type_prompt or 'defaut'} | Agents : {types_actifs} | Provider : {config.LLM_PROVIDER}")

    # 8. Génération LLM
    llm      = _get_llm(types_actifs)
    history  = mem.format_for_prompt()
    messages = prompt_template.format_messages(
        context  = context,
        history  = history,
        question = question,
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
            "capitaux propres", "résultat d'exploitation", "résultat brut")


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
            return {"kind": "ef", "indicateur": key, "mode": mode, "sens": sens}
    return None


def _executer_comparatif(chain: dict, question: str, spec: dict) -> str:
    """Exécute la comparaison via l'outil structuré SQL, puis fait phraser le LLM."""
    mem = chain["memory"]
    if spec["kind"] == "ef":
        d = structured_tools.comparer_ef(spec["indicateur"], spec["mode"])
        txt, winner = structured_tools.format_comparaison(d, "millions FCFA", spec["sens"])
    else:
        d = structured_tools.comparer_cb(spec["service"], spec["annee"], spec["semestre"], spec["segment"])
        txt, winner = structured_tools.format_comparaison(d, "FCFA", spec["sens"])

    if winner is None:
        rep = "Données insuffisantes dans la base pour cette comparaison."
        mem.add_user(question); mem.add_assistant(rep)
        return rep

    sysm = ("Tu réponds UNIQUEMENT à partir de la comparaison chiffrée fournie (source : base SQL exacte). "
            "Nomme clairement la banque gagnante et donne le classement avec les valeurs.")
    userm = f"Question : {question}\n\nComparaison :\n{txt}"
    llm = _get_llm(["etats_financiers"])     # température factuelle
    rep = _invoke_with_retry(llm, [("system", sysm), ("human", userm)])
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
            types_actifs = ["conditions_banque", "etats_financiers"]

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
