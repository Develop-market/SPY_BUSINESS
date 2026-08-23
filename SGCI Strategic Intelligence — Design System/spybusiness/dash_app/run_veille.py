# -*- coding: utf-8 -*-
"""
run_veille.py — VEILLE WEB RÉELLE & reproductible (Agent WEB du RAG).
=====================================================================
Met à jour `web_facts.json` (faits sectoriels du dashboard / PESTEL) en allant chercher
les valeurs les PLUS RÉCENTES sur le web (Tavily), en EXTRAYANT le chiffre + sa source
via le LLM (Groq), puis en réécrivant le cache DATÉ.

REPRODUCTIBLE : relancer régénère le cache (mêmes requêtes, mêmes sources).
DYNAMIQUE : ramène du frais → fini les chiffres figés de 2024 dans le PESTEL.
HONNÊTE : on ne met à jour QUE si un chiffre clair + récent est trouvé (sanity-check) ;
          sinon on GARDE l'ancien et on le marque « à rafraîchir ». Jamais d'invention.
          Backup horodaté avant toute écriture.

Clé requise : TAVILY_API_KEY (.env). Sans clé → mode VÉRIF (ping des liens, comme avant).
Usage :  python run_veille.py   |   python run_veille.py --dry-run
"""
import os, sys, json, re, time, datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")   # console Windows (cp1252) → UTF-8
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
# Données de référence regroupées dans spybusiness/data/ (2026-07-30) : elles alimentent
# les analyses et se conservent, contrairement aux caches qui se régénèrent.
DOSSIER_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "data")
CACHE = os.path.join(DOSSIER_DATA, "web_facts.json")

# Indicateurs à rafraîchir : clé → (libellé humain pour le LLM, requête web, regex de PLAUSIBILITÉ
# SÉMANTIQUE — la valeur extraite doit matcher, sinon on rejette et on garde l'ancien).
INDICATEURS = {
    "politique_monetaire": ("Taux directeur de la BCEAO (politique monétaire UEMOA), en %",
                            "taux directeur BCEAO UEMOA actuel 2025 2026", r"%"),
    "croissance_macro":    ("Croissance du PIB et inflation en Côte d'Ivoire (en %)",
                            "Côte d'Ivoire croissance PIB inflation 2025 2026 prévision FMI BCEAO", r"(?i)pib"),
    "bancarisation":       ("Taux de bancarisation en Côte d'Ivoire (en %)",
                            "taux de bancarisation Côte d'Ivoire UEMOA 2025 2026", r"%"),
    "mobile_money":        ("Taux de pénétration du mobile money en Côte d'Ivoire (en %)",
                            "taux pénétration mobile money Côte d'Ivoire UEMOA 2025", r"%"),
    "cout_credit":         ("Taux débiteur moyen du crédit et taux d'usure (Côte d'Ivoire/UEMOA), en %",
                            "taux débiteur moyen crédit taux usure UEMOA BCEAO 2025 2026", r"%"),
    "npl_secteur":         ("Taux de créances en souffrance (NPL) des banques UEMOA (en %)",
                            "taux créances en souffrance NPL banques UEMOA 2025 BCEAO", r"%"),
    "solvabilite_secteur": ("Ratio de solvabilité du secteur bancaire UEMOA (en %)",
                            "ratio de solvabilité banques UEMOA 2025 BCEAO commission bancaire", r"%"),
    "structure_marche":    ("Nombre de banques agréées en Côte d'Ivoire (un nombre de banques, ex. '28 banques')",
                            "nombre de banques agréées Côte d'Ivoire 2025 secteur bancaire", r"(?i)banque"),
}


# ── SOURCES FIABLES (2026-07-30) ──────────────────────────────────────────────────
# Liste blanche transmise à Tavily (`include_domains`) : la recherche ne rapporte que des
# résultats issus de ces domaines. Objectif : supprimer le bruit du web ouvert sur des sujets
# où une valeur fausse contaminerait une recommandation à la Direction Générale.
# Tous vérifiés par résolution DNS le 2026-07-30. Note : bceao.int n'a pas d'enregistrement
# racine, seul www.bceao.int répond — Tavily filtrant par suffixe de domaine, la forme courte
# couvre bien le sous-domaine.
SOURCES_INSTITUTIONS = ["bceao.int", "finances.gouv.ci", "ins.ci",
                        "worldbank.org", "afdb.org", "imf.org"]
# LEÇON DE TERRAIN (2026-07-30) : restreindre les filières aux sites de leurs Conseils s'est
# révélé CONTRE-PRODUCTIF. Testé sur « prix garanti producteur cacao » : conseilcafecacao.ci
# remonte bien en tête, mais son contenu extractible se limite au menu de navigation
# (« Skip to content », « Nos Contacts ») — le prix vit dans un tableau que le moteur ne lit
# pas. La même requête en web ouvert trouve la valeur sur agriculture.gouv.ci (« le prix bord
# champ du cacao… ») et dans la presse. On garde donc les Conseils comme source de référence,
# mais on ajoute le ministère de tutelle et la presse spécialisée, qui PORTENT le chiffre en
# texte lisible. Une source d'autorité mal indexée ne vaut rien pour une extraction automatique.
SOURCES_FILIERES     = ["conseilcafecacao.ci", "conseilcotonanacarde.ci",
                        "agriculture.gouv.ci", "gouv.ci"]
SOURCES_PRESSE       = ["fratmat.info", "aip.ci", "abidjan.net", "rti.info",
                        "sikafinance.com", "financialafrik.com", "jeuneafrique.com",
                        "apanews.net", "rfi.fr"]
SOURCES_FIABLES      = SOURCES_INSTITUTIONS + SOURCES_FILIERES + SOURCES_PRESSE


# ── INDICATEURS DE FILIÈRE (2026-07-30) ───────────────────────────────────────────
# Les indicateurs macro ci-dessus disent où en est l'économie ; ceux-ci disent SUR QUOI une
# banque peut agir. Une campagne cacao, c'est un calendrier connu et des flux de paiement
# massifs vers des centaines de milliers de producteurs — donc un levier commercial daté.
# Filières retenues d'après les priorités du PND 2026-2030 (agro-industrie en tête).
# Chaque entrée porte SA liste de domaines : les filières interrogent leurs Conseils, les
# sujets réglementaires interrogent la BCEAO. Un domaine hors sujet ne fait que diluer.
INDICATEURS_FILIERES = {
    "cacao_prix":      ("Prix garanti au producteur de cacao en Côte d'Ivoire (FCFA/kg)",
                        "prix garanti producteur cacao Côte d'Ivoire campagne FCFA kg",
                        r"(?i)(fcfa|f/kg|kg)", SOURCES_FILIERES + SOURCES_PRESSE),
    "cacao_campagne":  ("Dates d'ouverture de la campagne cacao en Côte d'Ivoire",
                        "ouverture campagne principale cacao Côte d'Ivoire calendrier",
                        r"(?i)(campagne|octobre|avril|20\d{2})", SOURCES_FILIERES + SOURCES_PRESSE),
    "anacarde":        ("Production et prix de l'anacarde (noix de cajou) en Côte d'Ivoire",
                        "production prix anacarde noix de cajou Côte d'Ivoire campagne",
                        r"(?i)(tonne|fcfa|kg)", SOURCES_FILIERES + SOURCES_PRESSE),
    "coton":           ("Production et prix du coton graine en Côte d'Ivoire",
                        "production prix coton graine Côte d'Ivoire campagne producteur",
                        r"(?i)(tonne|fcfa|kg)", SOURCES_FILIERES + SOURCES_PRESSE),
    "seuil_especes":   ("Seuil de déclaration des transactions en espèces (LBC/FT, CENTIF/BCEAO), en FCFA",
                        "seuil déclaration transactions espèces CENTIF BCEAO Côte d'Ivoire FCFA",
                        r"(?i)(fcfa|million)", SOURCES_INSTITUTIONS + SOURCES_PRESSE),
    "financement_pme": ("Accès au financement des PME en Côte d'Ivoire (part du crédit ou taux d'accès)",
                        "financement PME Côte d'Ivoire accès crédit bancaire part",
                        r"(?i)(%|pme)", SOURCES_INSTITUTIONS + SOURCES_PRESSE),

    # ── Secteurs hors agriculture (2026-07-30) ───────────────────────────────────────────
    # Sur cinq secteurs suivis, deux étaient agricoles : l'onglet opérationnel produisait
    # deux fois la même décision de crédit de campagne, et ne disait rien des commerçants,
    # du transport ou du négoce — alors que le segment CLIPRO de la grille SGCI les couvre.
    # Un secteur n'est rendu que s'il dispose d'au moins un fait sourcé : ajouter les
    # secteurs sans ajouter leurs indicateurs les aurait laissés invisibles.
    "commerce_informel": ("Poids du secteur informel dans l'économie ou l'emploi en Côte d'Ivoire (%)",
                          "part secteur informel économie emploi Côte d'Ivoire pourcentage commerce",
                          r"(?i)(%|informel)", SOURCES_INSTITUTIONS + SOURCES_PRESSE),
    "commerce_tpe":     ("Nombre de terminaux de paiement électronique ou de commerçants acceptant la carte en Côte d'Ivoire",
                         "terminaux paiement électronique TPE commerçants acceptation carte Côte d'Ivoire nombre",
                         r"(?i)(tpe|terminaux|commerçants|\d)", SOURCES_INSTITUTIONS + SOURCES_PRESSE),
    "transport_port":   ("Trafic du Port autonome d'Abidjan (tonnes ou conteneurs par an)",
                         "trafic Port autonome Abidjan tonnes conteneurs volume annuel",
                         r"(?i)(tonne|evp|conteneur)", SOURCES_INSTITUTIONS + SOURCES_PRESSE),
    "transport_corridor": ("Volume de marchandises du corridor Abidjan-Ouagadougou ou transit routier ivoirien",
                           "corridor Abidjan Ouagadougou transit routier marchandises volume Côte d'Ivoire",
                           r"(?i)(tonne|camion|corridor)", SOURCES_INSTITUTIONS + SOURCES_PRESSE),
    "commerce_exterieur": ("Valeur des exportations ou importations de la Côte d'Ivoire (milliards FCFA)",
                           "exportations importations Côte d'Ivoire valeur milliards FCFA balance commerciale",
                           r"(?i)(milliard|fcfa)", SOURCES_INSTITUTIONS + SOURCES_PRESSE),
    "btp_logement":     ("Déficit de logements ou production de logements en Côte d'Ivoire",
                         "déficit logements Côte d'Ivoire besoin production logements sociaux nombre",
                         r"(?i)(logement|unité|\d)", SOURCES_INSTITUTIONS + SOURCES_PRESSE),
    "btp_investissement": ("Investissement public en infrastructures en Côte d'Ivoire (milliards FCFA)",
                           "investissement public infrastructures Côte d'Ivoire milliards FCFA budget",
                           r"(?i)(milliard|fcfa)", SOURCES_INSTITUTIONS + SOURCES_PRESSE),
    # « priorites_pnd » a été retiré (2026-07-30) : _extract() a pour contrat de renvoyer UN
    # CHIFFRE court et vérifiable ("valeur":"<chiffre COURT>"). Les priorités du PND sont une
    # LISTE QUALITATIVE de filières — l'extracteur ne peut structurellement pas la restituer, et
    # forcer le passage produirait une valeur tronquée sans signification. Ce besoin relève d'un
    # traitement distinct (extraction de liste), à traiter séparément plutôt que détourner un
    # mécanisme conçu pour les indicateurs numériques.
}


def _load_env():
    try:
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv(usecwd=True))
        load_dotenv(os.path.abspath(os.path.join(HERE, "..", "..", "..", ".env")))
    except Exception:
        pass


def _search(query, k=5, domaines=None):
    """Recherche Tavily. `domaines` restreint la recherche à une liste blanche (2026-07-30).

    Sans liste, le comportement reste celui d'origine — recherche sur le web ouvert — afin de
    ne rien changer aux indicateurs macro déjà en service. Seuls les indicateurs de filière,
    où une valeur erronée irait directement nourrir une recommandation chiffrée à une direction,
    imposent leurs sources."""
    tav = os.getenv("TAVILY_API_KEY")
    if not tav:
        return None
    try:
        import requests
        charge = {"api_key": tav, "query": query, "max_results": k,
                  "search_depth": "advanced"}
        if domaines:
            charge["include_domains"] = list(domaines)
        r = requests.post("https://api.tavily.com/search", json=charge, timeout=30)
        if r.ok:
            return [{"title": x.get("title", ""), "url": x.get("url", ""),
                     "content": (x.get("content") or "")[:500]} for x in r.json().get("results", [])]
    except Exception as e:
        print("   [tavily err]", str(e)[:90])
    return None


def _extract(libelle, snippets):
    """Groq extrait le chiffre RÉCENT + source depuis les extraits. None si rien de fiable."""
    keys = [k for k in [os.getenv("GROQ_API_KEY", "")] +
            [os.getenv(f"GROQ_API_KEY_{i}", "") for i in range(2, 13)] if k]
    if not keys:
        return None
    ctx = "\n".join(f"- {s.get('title','')} ({s.get('url','')}) : {s.get('content','')}" for s in snippets[:5])
    prompt = (
        f"Indicateur recherché : {libelle}.\nExtraits web récents :\n{ctx}\n\n"
        "Extrais la valeur la PLUS RÉCENTE et CLAIREMENT énoncée dans ces extraits, qui correspond EXACTEMENT "
        "à l'indicateur demandé (pas une autre statistique). JSON STRICT :\n"
        '{"valeur":"<chiffre COURT, ex. \'PIB +6,7% · inflation 1,2%\' ou \'3,00%\' ou \'28 banques\'>",'
        '"detail":"<une phrase factuelle de contexte, <=140 caractères, tirée des extraits>",'
        '"annee":"<année du chiffre, ex. 2025>","source":"<institution courte, ex. BCEAO, FMI, UMOA>",'
        '"url":"<url la plus pertinente>"}\n'
        "Si AUCUN chiffre clair, récent ET correspondant à CET indicateur n'apparaît, renvoie {\"valeur\":null}. "
        "N'invente JAMAIS un chiffre ; ne donne pas une statistique d'un autre sujet."
    )
    from groq import Groq
    for k in keys:
        try:
            r = Groq(api_key=k, timeout=30, max_retries=0).chat.completions.create(
                model="openai/gpt-oss-120b", messages=[{"role": "user", "content": prompt}],
                max_tokens=400, temperature=0.0, response_format={"type": "json_object"},
                reasoning_effort="low")
            return json.loads(r.choices[0].message.content)
        except Exception:
            continue
    return None


def _sanitize(cle, val):
    """Assainit/valide la valeur extraite selon des bornes plausibles. Renvoie la valeur
    nettoyée, ou None si aberrante (→ on garde l'ancienne). Évite déflation, % hors [0,100], etc."""
    v = str(val).strip()
    fl = lambda s: float(s.replace(",", ".").replace("+", ""))
    nums = re.findall(r"[+\-]?\d+(?:[.,]\d+)?", v)
    if cle == "croissance_macro":
        pib = re.search(r"(?i)pib[^0-9+\-]*([+\-]?\d+(?:[.,]\d+)?)", v)
        inf = re.search(r"(?i)inflation[^0-9+\-]*([+\-]?\d+(?:[.,]\d+)?)", v)
        if not pib or not (0 < fl(pib.group(1)) < 15):
            return None
        out = f"PIB +{pib.group(1).lstrip('+')}%".replace(".", ",")
        if inf and 0 <= fl(inf.group(1)) < 15:          # inflation négative = rejetée
            out += f" · inflation {inf.group(1).lstrip('+')}%".replace(".", ",")
        return out
    if cle == "structure_marche":
        for n in nums:
            if 5 <= fl(n) <= 80:
                return f"{int(fl(n))} banques"
        return None
    # INDICATEURS EXPRIMÉS EN VALEUR, PAS EN POURCENTAGE (2026-07-30).
    # La règle de repli ci-dessous suppose un pourcentage : « au moins un nombre dans [0,100] ».
    # Elle était juste tant que tous les indicateurs étaient des taux. Les indicateurs de filière
    # sont des PRIX en FCFA : un cacao à 2 800 F/kg, un anacarde à 400 F/kg, un seuil de
    # déclaration à 15 000 000 F. Tous rejetés comme aberrants, alors qu'ils étaient corrects —
    # l'extraction fonctionnait, c'est la validation qui les refusait. Chaque indicateur de
    # valeur porte donc désormais sa propre plage de plausibilité, ce qui conserve la protection
    # contre les valeurs absurdes sans présumer de l'unité.
    BORNES_VALEUR = {
        "cacao_prix":    (300, 6000),        # FCFA/kg bord champ
        "anacarde":      (100, 2000),        # FCFA/kg
        "coton":         (100, 1500),        # FCFA/kg graine
        "seuil_especes": (1_000_000, 200_000_000),   # FCFA
        # Secteurs hors agriculture — bornes larges mais suffisantes pour écarter l'aberration
        # (un « 3 » lu dans un numéro de page, un millésime pris pour un volume).
        "commerce_informel":   (10, 95),                  # % de l'économie ou de l'emploi
        "commerce_tpe":        (100, 500_000),            # nombre de terminaux ou de commerçants
        "transport_port":      (1_000, 100_000_000),      # tonnes ou EVP par an
        "transport_corridor":  (1_000, 100_000_000),      # tonnes
        "commerce_exterieur":  (100, 100_000),            # milliards FCFA
        "btp_logement":        (1_000, 10_000_000),       # unités de logement
        "btp_investissement":  (10, 100_000),             # milliards FCFA
    }
    if cle in BORNES_VALEUR:
        bas, haut = BORNES_VALEUR[cle]
        # Le montant peut être écrit avec des séparateurs (« 15 000 000 ») : on le reconstitue
        # avant de le comparer, sinon on ne lirait que « 15 ».
        # Separateurs de milliers : sans recollage on ne lirait que « 15 » dans « 15 000 000 »
        # et la borne basse rejetterait une valeur correcte. On retire espaces normaux et
        # insecables ; l'extraction des chiffres qui suit reste correcte sur « 310 FCFA/kg ».
        compact = v.replace(" ", "").replace(chr(160), "")
        for n in re.findall(r"\d+(?:[.,]\d+)?", compact):
            if bas <= fl(n) <= haut:
                return v
        return None

    # indicateurs en % : au moins un nombre dans [0,100]
    for n in nums:
        if 0 <= fl(n) <= 100:
            return v
    return None


def run(dry_run=False):
    _load_env()
    today = datetime.date.today().isoformat()
    try:
        data = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        data = {"secteur": [], "sources": []}

    if not os.getenv("TAVILY_API_KEY"):
        print("[veille] Pas de TAVILY_API_KEY → mode VÉRIF liens uniquement (pas de rafraîchissement de chiffres).")
        data["maj"] = today
        if not dry_run:
            json.dump(data, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return

    # Backup horodaté AVANT toute écriture
    if not dry_run:
        bak = os.path.join(HERE, f"web_facts_backup_{datetime.datetime.now():%Y%m%d_%H%M%S}.json")
        json.dump(data, open(bak, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"[veille] backup → {os.path.basename(bak)}")

    sec = {f.get("cle"): f for f in data.get("secteur", [])}
    maj_n = 0
    # Macro (web ouvert, comportement d'origine) PUIS filières (sources imposées).
    # Le 4e élément du tuple, quand il est présent, est la liste blanche de domaines.
    tous = list(INDICATEURS.items()) + list(INDICATEURS_FILIERES.items())
    for cle, spec in tous:
        libelle, query, plaus = spec[0], spec[1], spec[2]
        domaines = spec[3] if len(spec) > 3 else None
        snips = _search(query, domaines=domaines) or []
        res = _extract(libelle, snips) if snips else None
        raw_val = (res or {}).get("valeur")
        val = _sanitize(cle, raw_val) if raw_val else None
        if val and len(str(val)) < 90:
            fact = sec.setdefault(cle, {"cle": cle})
            src = (res.get("source") or "web").strip()[:35]
            ym = re.search(r"\b(20\d{2})\b", str(res.get("annee") or ""))
            annee = ym.group(1) if ym else ""
            det = (res.get("detail") or "").strip()
            fact["valeur"] = str(val).strip()
            # TITRE LISIBLE (2026-08-07). Les indicateurs seedés à la main en portaient un ;
            # ceux créés par une collecte n'en avaient aucun, et l'affichage retombait sur la
            # clé technique — « btp investissement » au lieu de « Investissement public en
            # infrastructures ». Le libellé déclaré juste au-dessus est la bonne source : on
            # le pose à la création, sans écraser un titre déjà rédigé.
            if not fact.get("titre"):
                fact["titre"] = libelle.split("(")[0].strip().rstrip(",")
            if det and 10 < len(det) <= 180:
                fact["detail"] = det
            fact["source"] = (src + (" " + annee if annee else "")).strip()
            fact["url"] = res.get("url") or fact.get("url", "")
            fact["date"] = today
            fact["_maj_auto"] = True
            fact.pop("_a_rafraichir", None)
            maj_n += 1
            print(f"   ✓ {cle:22} → {val}  [{src} {annee}]")
        else:
            if cle in sec:
                sec[cle]["_a_rafraichir"] = True   # gardé tel quel, signalé
            print(f"   – {cle:22} → pas de chiffre récent fiable (ancien gardé)")
        time.sleep(1.2)

    data["secteur"] = list(sec.values())
    data["maj"] = today
    data["_veille_maj_auto"] = today
    if not dry_run:
        json.dump(data, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[veille] {maj_n}/{len(tous)} indicateurs rafraîchis ({today}) "
          f"— dont {len(INDICATEURS_FILIERES)} de filière.")


# ══════════════════════════════════════════════════════════════════════════════════════
#  EXTRACTEUR D'ÉVÉNEMENTS (2026-07-30)
# ══════════════════════════════════════════════════════════════════════════════════════
# POURQUOI IL A FALLU EN ÉCRIRE UN SECOND
#
# `_extract()` a pour contrat de renvoyer UN CHIFFRE court correspondant à un indicateur précis
# (« 3,00 % », « 28 banques »). Ce contrat convient aux repères macro, il est inadapté à
# l'actualité sectorielle : testé sur cinq secteurs, il n'en a servi qu'un seul. Les sources
# répondaient pourtant — elles renvoyaient « CIFA's 2026 plan is structured around… »,
# « Ecobank a fait de l'agribusiness un pilier de son plan 2025 » — mais faute de chiffre isolé,
# tout partait à la poubelle.
#
# Or c'est précisément cette matière que cherche une direction de la stratégie : un ACTEUR qui
# FAIT quelque chose, éventuellement pour un MONTANT, à une DATE. « Le gouvernement lance un
# programme de 500 milliards pour l'agriculture » n'est pas un indicateur, c'est un événement —
# et c'est ce qui déclenche une décision commerciale.
#
# Les deux extracteurs coexistent donc, avec des contrats distincts :
#     _extract()            → un indicateur chiffré, pour les repères de cadrage
#     _extract_evenements() → une liste de faits datés, pour les signaux d'action

EVENEMENTS = {
    "agro": ("filière agricole ivoirienne (cacao, café, anacarde, coton)",
             "Côte d'Ivoire filière agricole investissement programme financement campagne"),
    "numerique": ("économie numérique et paiements en Côte d'Ivoire",
                  "Côte d'Ivoire numérique paiement mobile fintech lancement investissement"),
    "infrastructure": ("grands projets et investissements publics en Côte d'Ivoire",
                       "Côte d'Ivoire projet investissement public milliards FCFA infrastructure énergie"),
    "banque_concurrence": ("mouvements des banques concurrentes en Côte d'Ivoire",
                           "banque Côte d'Ivoire lance nouvelle offre partenariat BICICI Ecobank NSIA SIB BNI"),
    "reglementation": ("évolutions réglementaires bancaires UEMOA",
                       "BCEAO UEMOA nouvelle instruction réglementation bancaire décision"),
    # Ajoutés le 2026-07-30 : les axes Social et Environnemental du PESTEL n'avaient AUCUN
    # signal, non par absence d'actualité mais parce qu'aucune requête ne les couvrait. Un
    # PESTEL dont deux axes sur six restent muets décrit à moitié son environnement.
    "social": ("emploi, inclusion financière et formation en Côte d'Ivoire",
               "Côte d'Ivoire emploi jeunes inclusion financière formation programme social"),
    "environnement": ("transition énergétique et finance durable en Côte d'Ivoire",
                      "Côte d'Ivoire énergie renouvelable finance verte climat durable projet"),
}


def _extract_evenements(domaine, snippets):
    """Extrait une LISTE d'événements exploitables depuis des extraits web.

    Renvoie [] plutôt qu'un contenu approximatif : un événement mal daté ou sans acteur
    identifié n'oriente aucune décision et encombre la lecture. Mieux vaut trois faits solides
    que dix approximations.
    """
    keys = [k for k in [os.getenv("GROQ_API_KEY", "")] +
            [os.getenv(f"GROQ_API_KEY_{i}", "") for i in range(2, 13)] if k]
    if not keys or not snippets:
        return []
    ctx = "\n".join(f"- {s.get('title','')} ({s.get('url','')}) : {s.get('content','')}"
                    for s in snippets[:6])
    prompt = (
        f"Domaine surveillé : {domaine}.\n"
        f"Extraits web récents :\n{ctx}\n\n"
        "Relève les ÉVÉNEMENTS exploitables par la direction de la stratégie d'une banque "
        "ivoirienne : un acteur qui lance, investit, s'associe, ouvre, réglemente ou annonce.\n"
        "N'invente RIEN. N'extrais que ce qui est explicitement écrit dans les extraits.\n"
        "Ignore les menus de navigation, les mentions légales et les textes sans information.\n"
        "Réponds en JSON STRICT, un tableau de 0 à 4 objets, sans texte autour :\n"
        '[{"acteur":"<qui, ex. État de Côte d\'Ivoire, BICICI, BCEAO>",'
        '"fait":"<ce qui est annoncé ou fait, une phrase de 12 à 25 mots>",'
        '"montant":"<montant avec son unité si présent, sinon chaîne vide>",'
        '"date":"<date ou période citée, sinon chaîne vide>",'
        '"portee":"<opportunité|menace|contrainte>",'
        '"url":"<url de l\'extrait qui porte l\'information>"}]'
    )
    import random
    for k in random.sample(keys, min(3, len(keys))):
        try:
            from groq import Groq as _G
            r = _G(api_key=k).chat.completions.create(
                model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=900, temperature=0.2, reasoning_effort="low")
            txt = (r.choices[0].message.content or "").strip()
            deb, fin = txt.find("["), txt.rfind("]")
            if deb < 0 or fin < 0:
                continue
            lot = json.loads(txt[deb:fin + 1])
            out = []
            for e in lot if isinstance(lot, list) else []:
                fait = str(e.get("fait", "")).strip()
                acteur = str(e.get("acteur", "")).strip()
                # Un événement sans acteur ni fait n'est pas un événement.
                if len(fait) < 25 or not acteur:
                    continue
                # FRAÎCHEUR (2026-07-30) — la première collecte a remonté « 4 milliards USD
                # 2010-2015 » et « 132,8 millions USD 2019 » : des faits exacts, mais périmés.
                # Un événement de 2019 ne déclenche aucune décision aujourd'hui ; il occupe une
                # place que mérite un signal récent. On écarte donc toute date antérieure à
                # l'année précédente, quand une date est citée.
                _dt = str(e.get("date", ""))
                _ans = [int(a) for a in re.findall(r"(20\d{2})", _dt)]
                if _ans and max(_ans) < datetime.date.today().year - 1:
                    continue
                # Un fait sans verbe d'action décrit un état, pas un événement — « a des réseaux
                # politiques importants » n'appelle aucune décision commerciale.
                if not re.search(r"(?i)(lance|signe|invest|ouvre|adopte|annonce|met en |cr[ée]e|"
                                 r"d[ée]ploie|s.associe|acquiert|finance|approuve|autorise|"
                                 r"franchit|atteint|pr[ée]voit|construit|inaugure)", fait):
                    continue
                portee = str(e.get("portee", "")).lower()
                out.append({
                    "acteur": acteur[:60], "fait": fait[:220],
                    "montant": str(e.get("montant", "")).strip()[:40],
                    "date_citee": str(e.get("date", "")).strip()[:40],
                    "portee": portee if portee in ("opportunité", "menace", "contrainte") else "opportunité",
                    "url": str(e.get("url", "")).strip()[:300],
                })
            return out[:4]
        except Exception as e:
            print("   [evt err]", str(e)[:80])
            continue
    return []


def run_evenements(dry_run=False):
    """Collecte les événements de marché et les range dans web_facts.json.

    Conservés à part des indicateurs (`secteur`) : ce sont deux natures d'information. Un
    indicateur se remplace à chaque relevé ; un événement s'ACCUMULE et vieillit. On garde donc
    l'historique, en écartant les doublons et ce qui dépasse 120 jours — au-delà, un « lancement »
    n'est plus un signal d'action, c'est de l'histoire.
    """
    _load_env()
    if not os.getenv("TAVILY_API_KEY"):
        print("[veille-evt] Pas de TAVILY_API_KEY → collecte d'événements ignorée.")
        return
    today = datetime.date.today().isoformat()
    try:
        data = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        data = {"secteur": [], "sources": []}

    anciens = data.get("evenements", [])
    limite = (datetime.date.today() - datetime.timedelta(days=120)).isoformat()
    anciens = [e for e in anciens if (e.get("releve_le") or "") >= limite]
    vus = {(e.get("acteur", "") + e.get("fait", ""))[:90].lower() for e in anciens}

    nouveaux, n_dom = [], 0
    for cle, (domaine, requete) in EVENEMENTS.items():
        snips = _search(requete, k=6, domaines=SOURCES_FIABLES) or []
        evts = _extract_evenements(domaine, snips)
        for e in evts:
            sig = (e["acteur"] + e["fait"])[:90].lower()
            if sig in vus:
                continue
            vus.add(sig)
            e["domaine"] = cle
            e["releve_le"] = today
            nouveaux.append(e)
        n_dom += 1
        print(f"   {cle:20} → {len(evts)} événement(s)")
        time.sleep(1.2)

    data["evenements"] = (nouveaux + anciens)[:60]
    data["_evenements_maj"] = today
    if not dry_run:
        json.dump(data, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[veille-evt] {len(nouveaux)} nouveau(x) événement(s) sur {n_dom} domaines "
          f"({len(data['evenements'])} en mémoire, fenêtre 120 jours).")


if __name__ == "__main__":
    args = sys.argv[1:]
    dry = "--dry-run" in args
    # 1) Faits sectoriels (contexte macro / PESTEL / stratégie)
    run(dry_run=dry)
    # 2) Même agent web → exclusivités CB (sauf --no-excl). UN seul point d'entrée.
    if "--no-excl" not in args:
        try:
            import run_veille_exclusivites as _ex
            print("\n[veille] === Exclusivités CB (même moteur Tavily+Groq) ===")
            _ex.run(_ex.BANKS, dry_run=dry)
        except Exception as e:
            print("[veille] exclusivités ignorées:", str(e)[:140])
