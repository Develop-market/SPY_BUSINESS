"""
structured_tools.py — Outils de COMPARAISON STRUCTURÉE (agrégation SQL sur les 7 banques)
==========================================================================================
Ajouté en v2 après le diagnostic : comparer une valeur sur toutes les banques est une
opération ANALYTIQUE (SQL), pas de la récupération sémantique. Ce module fait partie du
SOCLE COMMUN → il est branché dans les DEUX architectures (l'agentique l'expose comme
outil ; le déterministe l'appelle via une règle). On reste « toutes choses égales ».
"""
import os
import sys
import importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
config = importlib.import_module("config")
import psycopg2

BANQUES = config.BANQUES_OFFICIELLES

# Indicateurs EF : nom courant → motif ILIKE
# BUG TROUVÉ (2026-07-13, en testant l'ajout de BNI 2024) : le motif PNB "%produit net
# bancaire%" (singulier) ne matchait PAS "PRODUITS NET BANCAIRE" (pluriel) — libellé utilisé
# par BACI et BNI depuis toujours (donnée déjà en base, pas propre à mon ajout). "Quel est le
# PNB de BNI en 2023 ?" échouait déjà silencieusement avant ce correctif. Motif élargi avec des
# jokers entre les mots pour couvrir singulier/pluriel ET la variante SIB sans espaces
# ("PRODUITNETBANCAIRE").
EF_PATTERNS = {
    "pnb": "%produit%net%bancaire%", "produit net bancaire": "%produit%net%bancaire%",
    "résultat net": "%sultat net%", "resultat net": "%sultat net%", "rn": "%sultat net%",
    "capitaux propres": "%capitaux propres%", "fonds propres": "%capitaux propres%",
    "résultat d'exploitation": "%sultat d'exploitation%", "resultat d'exploitation": "%sultat d'exploitation%",
    "résultat brut": "%sultat brut d'exploitation%", "résultat brut d'exploitation": "%sultat brut d'exploitation%",
    # Ajoutés le 2026-07-14 — trou trouvé en testant : ces indicateurs existent bien en base
    # mais n'avaient pas d'entrée ici, donc une question dessus ratait le chemin SQL rapide
    # (valeur_ef/comparer_ef) et tombait dans le RAG générique, plus fragile (a échoué en
    # 413 Groq sur "total bilan de BNI en 2024" alors que la donnée existe et est correcte).
    "total bilan": "%total%actif%", "total actif": "%total%actif%", "total de l'actif": "%total%actif%",
    "coût du risque": "%cout du risque%", "cout du risque": "%cout du risque%",
    "charges générales": "%charges generales%exploitation%",
    "charges generales": "%charges generales%exploitation%",
    "charges générales d'exploitation": "%charges generales%exploitation%",
    "charges generales d'exploitation": "%charges generales%exploitation%",
    "frais généraux": "%charges generales%exploitation%",
    "frais generaux": "%charges generales%exploitation%",
}


def _conn():
    return psycopg2.connect(**config.DB_PARAMS)


# Ecart relatif au-dela duquel deux valeurs pour le meme (banque, annee, indicateur) sont
# une VRAIE contradiction (exclue) plutot qu'une simple revision entre deux rapports
# annuels qui se recouvrent sur cette annee (ex. le rapport 2024 ET le rapport 2025 donnent
# tous deux une valeur pour 2024, la seconde revisant legerement la premiere). Trouve et
# calibre le 2026-09-03 en auditant EVAL_RAG_MEMOIRE (meme base, meme colonne ef_indicateurs)
# : revisions legitimes observees sous 5 % (ex. 17 708 vs 17 709 = 0,006 %) ; vraies anomalies
# — tres probablement des erreurs d'OCR — bien au-dela (ex. 110 189 vs 710 189 = 84 %).
_SEUIL_ECART_AMBIGU = 0.05


def _resoudre_valeur_ef(rows):
    """rows : [(montant, annee_rapport), ...] pour un (banque, annee, indicateur) donne.
    AVANT ce correctif : `max(vals)` etait pris sans condition — un chiffre invente/errone
    (une des deux valeurs contradictoires) passait pour une valeur « representative », sans
    jamais etre signale. Meme politique que le juge/gold-set : jamais une valeur choisie au
    hasard parmi plusieurs contradictoires. Retour (valeur, ambigu:bool)."""
    montants = sorted({round(m, 0) for m, _ in rows})
    if len(montants) == 1:
        return montants[0], False
    ecart_relatif = (max(montants) - min(montants)) / max(abs(max(montants)), 1)
    if ecart_relatif < _SEUIL_ECART_AMBIGU:
        # Revision mineure entre deux rapports : valeur du rapport le plus RECENT
        # (annee_rapport la plus haute), jamais une moyenne ou un max muet.
        # BUG CORRIGE (2026-09-03, trouve en testant SIB) : `_, plus_recent = max(rows, ...)`
        # depaquetait le tuple gagnant (montant, annee_rapport) A L'ENVERS — `plus_recent`
        # recevait l'ANNEE (ex. 2025) au lieu du MONTANT, faisant passer un coefficient
        # d'exploitation calcule avec "2025" comme chiffre a la place de 108700 (SIB :
        # 2069 % au lieu de ~38 %). Detecte car ce cas precis (deux valeurs PROCHES, pas
        # une seule) n'avait jamais ete exerce par les tests de cette nuit sur BNI.
        plus_recent, _ = max(rows, key=lambda mr: (mr[1] or 0, mr[0]))
        return plus_recent, False
    return None, True


def _an_year(cur, banque, mode):
    """Année AN1 (la + ancienne des 3 dernières) ou AN3 (la + récente) pour une banque."""
    cur.execute("""SELECT DISTINCT annee_donnee FROM ef_indicateurs
                   WHERE banque=%s AND is_primary AND annee_donnee IS NOT NULL
                   ORDER BY annee_donnee""", (banque,))
    ys = [r[0] for r in cur.fetchall()]
    if not ys:
        return None
    last3 = ys[-3:]
    return last3[-1] if str(mode).upper() == "AN3" else last3[0]


def comparer_ef(indicateur: str, mode: str = "AN3", banques: list = None) -> dict:
    """Valeur d'un indicateur EF pour CHAQUE banque (toutes par défaut, ou une liste
    précise si fournie — ex. "Compare le PNB entre SGCI et BICICI"), à son AN3 (ou AN1).
    Retour : {banque: {'annee': y, 'valeur': v}} (millions FCFA)."""
    pat = EF_PATTERNS.get((indicateur or "").strip().lower(), f"%{(indicateur or '').strip()}%")
    out = {}
    cx = _conn(); cur = cx.cursor()
    try:
        for b in (banques or BANQUES):
            y = _an_year(cur, b, mode)
            if not y:
                continue
            cur.execute("""SELECT ROUND(montant::double precision::numeric,0), annee_rapport
                           FROM ef_indicateurs
                           WHERE banque=%s AND annee_donnee=%s AND is_primary
                             AND libelle ILIKE %s AND libelle NOT ILIKE %s
                             AND montant IS NOT NULL""", (b, y, pat, "%avant%"))
            rows = [(float(r[0]), r[1]) for r in cur.fetchall()]
            if not rows:
                # BUG TROUVÉ le 2026-09-19 (le directeur, testant « capitaux propres les plus
                # faibles » : SIB manquait du classement, SANS AUCUNE TRACE — même défaut que
                # « db.query() avale les erreurs et rend [] », ici au niveau de l'agrégation.
                # Cause réelle : SIB a un AN3 = 2025 (elle a d'autres indicateurs 2025), mais
                # AUCUNE ligne « capitaux propres » n'existe pour son rapport 2025 en base (elle
                # s'arrête à 2024) — un vrai trou de donnée, pas une erreur de requête. Jusqu'ici
                # `continue` faisait disparaître la banque sans un mot, alors que le cas voisin
                # « valeur ambiguë » (juste en dessous) est lui bien signalé. Même traitement :
                # la banque reste dans `out`, marquée absente, pour que format_comparaison()
                # le dise au lieu de le taire.
                out[b] = {"annee": y, "valeur": None, "manquant": True}
                continue
            valeur, ambigu = _resoudre_valeur_ef(rows)
            if ambigu:
                out[b] = {"annee": y, "valeur": None, "ambigu": True,
                          "valeurs_conflictuelles": sorted({m for m, _ in rows})}
            else:
                out[b] = {"annee": y, "valeur": valeur}
    finally:
        cur.close(); cx.close()
    return out


def valeur_ef(banque: str, indicateur: str, annee: int = None) -> dict:
    """Valeur d'UN indicateur EF pour UNE SEULE banque, à une année précise (ou AN3 par
    défaut si non précisée). Même source SQL que le dashboard (dash_app) et que
    comparer_ef — garantit un chiffre identique à celui affiché dans le dashboard,
    sans passer par le RAG (retrieval sémantique fragile sur les questions factuelles
    simples type "quel est le résultat net de X en Y ?").
    Retour : {'annee': y, 'valeur': v} (millions FCFA) ou {} si rien trouvé."""
    pat = EF_PATTERNS.get((indicateur or "").strip().lower(), f"%{(indicateur or '').strip()}%")
    cx = _conn(); cur = cx.cursor()
    try:
        y = annee or _an_year(cur, banque, "AN3")
        if not y:
            return {}
        cur.execute("""SELECT ROUND(montant::double precision::numeric,0), annee_rapport
                       FROM ef_indicateurs
                       WHERE banque=%s AND annee_donnee=%s AND is_primary
                         AND libelle ILIKE %s AND libelle NOT ILIKE %s
                         AND montant IS NOT NULL""", (banque, y, pat, "%avant%"))
        rows = [(float(r[0]), r[1]) for r in cur.fetchall()]
        if not rows:
            return {}
        valeur, ambigu = _resoudre_valeur_ef(rows)
        if ambigu:
            return {"annee": y, "valeur": None, "ambigu": True,
                    "valeurs_conflictuelles": sorted({m for m, _ in rows})}
        return {"annee": y, "valeur": valeur}
    finally:
        cur.close(); cx.close()


def serie_ef(banque: str, indicateur: str) -> list:
    """Série ANNUELLE complète d'un indicateur EF pour une banque : [(annee, valeur), ...].

    Ajouté le 2026-07-27 après un test de la batterie. « Comment a évolué le PNB de SGCI ces
    dernières années ? » passait par le RAG et répondait : 2021 = 215 101, « 2022 et 2023 non
    disponibles », 2025 = 276 000. Trois défauts d'un coup : une année (2021) tirée d'une
    colonne N-1 non primaire, deux années pourtant PRÉSENTES déclarées manquantes, et un
    chiffre ARRONDI (276 000 au lieu de 276 048) alors que le prompt interdit tout arrondi.
    Vérité SQL : 2023 = 253 286, 2024 = 263 207, 2025 = 276 048. Une évolution est une
    agrégation triviale en SQL — la faire deviner au retrieval sémantique n'a aucun intérêt.

    `is_primary` filtre les colonnes N-1 des rapports à 2 colonnes (source classique de
    confusion d'exercice) ; NOT ILIKE '%avant%' écarte « RESULTAT NET AVANT IMPOTS ».
    """
    # 2026-09-03 : `MAX(...) GROUP BY annee_donnee` avait exactement le meme defaut que
    # comparer_ef/valeur_ef avant leur correctif — un MAX SQL muet plutot qu'un Python, mais
    # le meme risque (deux valeurs contradictoires pour la meme annee, la plus grande —
    # potentiellement une erreur d'OCR — gagne sans jamais etre signalee). Remplace par la
    # meme resolution (_resoudre_valeur_ef, seuil 5 %) : une annee dont les valeurs sont
    # ambigues est EXCLUE de la serie plutot que d'afficher un chiffre invente dans un
    # graphique d'evolution — la meme politique que partout ailleurs dans ce fichier.
    pat = EF_PATTERNS.get((indicateur or "").strip().lower(), f"%{(indicateur or '').strip()}%")
    cx = _conn(); cur = cx.cursor()
    try:
        cur.execute("""SELECT annee_donnee, ROUND(montant::double precision::numeric,0), annee_rapport
                       FROM ef_indicateurs
                       WHERE banque=%s AND is_primary AND annee_donnee IS NOT NULL
                         AND libelle ILIKE %s AND libelle NOT ILIKE %s AND montant IS NOT NULL
                       ORDER BY annee_donnee""",
                    (banque, pat, "%avant%"))
        par_annee = {}
        for a, m, ar in cur.fetchall():
            par_annee.setdefault(int(a), []).append((float(m), ar))
        serie = []
        for annee in sorted(par_annee):
            valeur, ambigu = _resoudre_valeur_ef(par_annee[annee])
            if ambigu:
                print(f"  [EF SERIE AMBIGUË] {banque} {annee} « {indicateur} » exclue "
                      f"(valeurs contradictoires : {sorted({m for m, _ in par_annee[annee]})})")
                continue
            serie.append((annee, valeur))
        return serie
    finally:
        cur.close(); cx.close()


def format_serie_ef(banque: str, label: str, serie: list) -> str:
    """Tableau markdown Année | Valeur | Var. absolue | Var. %, variations pré-calculées.

    Les variations sont calculées ICI, pas par le LLM : une division faite par un modèle de
    langue se présente avec le même aplomb qu'un chiffre exact, y compris quand elle est fausse
    (même raison qui interdit déjà au LLM de calculer le ROE, cf. prompts.py)."""
    if not serie:
        return ""
    lignes = [f"ÉVOLUTION — {label} de {banque} (source SQL exacte, millions FCFA) :",
              "| Année | Valeur | Var. absolue | Var. % |", "|---|---|---|---|"]
    for i, (annee, val) in enumerate(serie):
        if i == 0:
            va, vp = "—", "—"
        else:
            prec = serie[i - 1][1]
            delta = val - prec
            va = f"{delta:+,.0f}".replace(",", " ")
            vp = f"{(delta / prec * 100):+.1f} %" if prec else "—"
        lignes.append(f"| {annee} | {val:,.0f} |".replace(",", " ") + f" {va} | {vp} |")
    total = ""
    if len(serie) >= 2 and serie[0][1]:
        delta_tot = serie[-1][1] - serie[0][1]
        var_tot = delta_tot / serie[0][1] * 100
        # Variation ABSOLUE en plus du pourcentage (2026-09-04) : sans elle, « de combien a
        # évolué X ? » forçait le modèle à faire la soustraction lui-même — ce que ce projet
        # interdit partout ailleurs. Le calcul appartient au déterministe.
        total = (f"\nVariation totale {serie[0][0]}→{serie[-1][0]} : "
                 f"{delta_tot:+,.0f} millions FCFA ({var_tot:+.1f} %)".replace(",", " "))
    return "\n".join(lignes) + total


def valeur_cb(banque: str, service: str, annee, semestre: str, segment: str) -> dict:
    """Tarif EXACT d'un service pour UNE banque à une période — pendant CB de `valeur_ef`.

    Ajouté le 2026-09-04. Sans lui, « quel est le tarif du Compte courant chez SIB en 2024
    S1 ? » partait au RAG : mesuré, la bonne ligne était bien récupérée mais classée 62ᵉ sur
    80 passages. Gemini la retrouve, un modèle plus modeste non — et rien ne justifie de faire
    chercher une aiguille quand la valeur se lit en une requête. Même départage que
    `comparer_cb` (`_resoudre_ligne_cb`), donc une valeur factuelle et une valeur comparée ne
    peuvent pas diverger.
    Retour : {'montant': m, 'gratuit': bool} | {'ambigu': True, ...} | {}."""
    cx = _conn(); cur = cx.cursor()
    try:
        cur.execute("""SELECT montant, est_gratuit, type_valeur, libelle FROM cb_tarifs
                       WHERE banque=%s AND annee=%s AND semestre=%s AND segment ILIKE %s
                         AND COALESCE(is_header,false)=false AND libelle ILIKE %s
                         AND type_valeur IN ('MONTANT_FCFA','GRATUIT')""",
                    (banque, annee, semestre, f"%{segment}%", f"%{service}%"))
        rows = cur.fetchall()
        if not rows:
            return {}
        return _resoudre_ligne_cb(rows, (service or "").strip().lower())
    finally:
        cur.close(); cx.close()


def _resoudre_ligne_cb(rows, terme_norm: str) -> dict:
    """Départage UNIQUE des lignes cb_tarifs matchées par un terme.
    rows : [(montant, est_gratuit, type_valeur, libelle), ...]

    ORDRE DES RÈGLES (il vient de bugs réels, ne pas réordonner) :
      1. Correspondance EXACTE au terme, évaluée sur TOUTES les lignes, GRATUITES COMPRISES.
         Bug trouvé le 2026-09-04 en validant contre le jeu de test : chercher l'exactitude
         seulement parmi les lignes payantes fait renvoyer un tarif payant quand la ligne
         exactement demandée existe mais est gratuite (NSIA « Compte chèque » : gratuit en
         base, mais « Compte chèque classique » et « ... formule package » sont payants).
      2. Plusieurs montants distincts restants -> terme trop vague, signalé, jamais deviné
         (ex. « carte » matche 15 produits SGCI de 1 000 à 280 000 FCFA).
      3. Un seul montant -> réponse directe ; sinon gratuité si une ligne l'atteste.
    """
    exactes = [r for r in rows if (r[3] or "").strip().lower() == terme_norm]
    if exactes:
        rows = exactes
    payantes = [(r[3], float(r[0])) for r in rows if r[0] is not None and r[2] == 'MONTANT_FCFA']
    montants_distincts = {round(m, 0) for _, m in payantes}
    if len(montants_distincts) > 1:
        return {"montant": None, "gratuit": False, "ambigu": True,
                "libelles_conflictuels": sorted({lib for lib, _ in payantes})}
    if payantes:
        return {"montant": payantes[0][1], "gratuit": False}
    if any(r[1] or r[2] == 'GRATUIT' for r in rows):
        return {"montant": 0.0, "gratuit": True}
    return {}


def comparer_cb(service: str, annee, semestre: str, segment: str) -> dict:
    """Tarif d'un service CB pour CHAQUE banque (annee/semestre/segment donnés).
    Retour : {banque: {'montant': m, 'gratuit': bool}} — ou {'montant': None, 'ambigu': True,
    'libelles_conflictuels': [...]} si le terme est trop large et matche PLUSIEURS services
    réellement distincts, sans qu'aucun ne se distingue clairement (ex. "carte" matche 15
    libellés différents pour SGCI, de 1 000 à 280 000 FCFA — vérifié en base le 2026-09-03).
    Avant ce correctif, min(mts) prenait aveuglément le moins cher parmi TOUS les libellés
    matchés, sans savoir s'ils désignaient le même service.

    Deux départages AVANT de conclure à l'ambiguïté (raffiné le 2026-09-03 en testant contre
    le jeu de test EVAL_RAG_MEMOIRE, qui a révélé ces deux cas réels) :
      1. Tous les libellés matchés partagent le MÊME montant (ex. BICICI "Attestation de
         solde" : "Attestation de solde" et "Autres types d'attestationAttestation de solde"
         [artefact de concaténation d'en-tête OCR] valent tous deux 30 000 FCFA) -> pas une
         vraie ambiguïté, peu importe le libellé exact.
      2. Un SEUL des libellés matchés correspond EXACTEMENT (mot pour mot) au terme cherché,
         les autres étant des variantes/fusions plus longues (ex. NSIA "Attestation de non
         engagement" = 20 000 FCFA EXACT vs "Attestation de non engagement — Attestation de
         non-redevance" = 30 000 FCFA, un produit combiné différent) -> on retient la
         correspondance exacte, qui est la lecture la plus littérale de la demande.
    Seulement si le désaccord persiste après ces deux départages -> terme trop vague, signalé
    au lieu de deviné (même principe que `_resoudre_valeur_ef`)."""
    terme_norm = (service or "").strip().lower()
    out = {}
    cx = _conn(); cur = cx.cursor()
    try:
        for b in BANQUES:
            cur.execute("""SELECT montant, est_gratuit, type_valeur, libelle FROM cb_tarifs
                           WHERE banque=%s AND annee=%s AND semestre=%s AND segment ILIKE %s
                             AND COALESCE(is_header,false)=false AND libelle ILIKE %s
                             AND type_valeur IN ('MONTANT_FCFA','GRATUIT')""",
                        (b, annee, semestre, f"%{segment}%", f"%{service}%"))
            rows = cur.fetchall()
            if not rows:
                continue
            info = _resoudre_ligne_cb(rows, terme_norm)
            if info:
                out[b] = info
    finally:
        cur.close(); cx.close()
    return out


def tableau_cb_exhaustif(banques: list, terme_service: str, max_libelles: int = 6) -> str:
    """Tableau markdown COMPLET et EXACT (lecture SQL directe, pas de RAG/embedding) pour un
    service CB donné, sur les banques demandées, séparé Particuliers/Entreprises, TOUTES
    les périodes (années × semestres) disponibles en colonnes.

    Pourquoi cette fonction existe : le RAG (retrieval sémantique + LLM) ne garde qu'un
    sous-ensemble de chunks par banque pour tenir dans le budget de contexte Groq (6000
    TPM) — pour un tableau qui doit croiser N banques × 2 segments × plusieurs semestres,
    ce sous-échantillonnage produit systématiquement des trous ("Non disponible" sur des
    données qui existent réellement) et mélange parfois les segments. Ici, la table est
    construite par SQL exhaustif — aucune perte, aucune invention possible.
    """
    import importlib, re
    retriever = importlib.import_module("retriever")
    termes = retriever._SYNONYMES_SERVICE.get(terme_service, [terme_service])
    _DUP_RE = re.compile(r"(.{4,}?)\1")  # détecte les doublons OCR ("Frais XFrais X")

    cx = _conn(); cur = cx.cursor()
    try:
        kw_conds = " OR ".join("(LOWER(libelle) LIKE %s OR LOWER(contexte) LIKE %s)" for _ in termes)
        kw_params = []
        for t in termes:
            kw_params.extend([f"%{t}%", f"%{t}%"])
        placeholders = ",".join(["%s"] * len(banques))
        cur.execute(f"""
            SELECT banque, segment, libelle, annee, semestre, valeur_propre, montant, est_gratuit,
                   section
            FROM cb_tarifs
            WHERE banque IN ({placeholders}) AND segment IN ('Particuliers','Entreprises')
              AND COALESCE(is_header,false)=false AND ({kw_conds})
            ORDER BY banque, segment, libelle, annee, semestre
        """, list(banques) + kw_params)
        rows = cur.fetchall()
    finally:
        cur.close(); cx.close()

    if not rows:
        return ""

    # Structure : {(banque,segment): {libelle: {(annee,semestre): valeur_affichee}}}
    struct = {}
    periodes = set()
    for banque, segment, libelle, annee, semestre, valeur_propre, montant, gratuit, section in rows:
        # CHEMIN DE SECTION (2026-07-27) : même correctif que retriever._chunk_cb, appliqué ici
        # car ce tableau est un chemin de code DISTINCT (comparaison CB exhaustive) qui souffrait
        # du même défaut. Sans lui, la comparaison SGCI/ECOBANK affichait une ligne « Frais de
        # tenue de compte : 2350 » qui laisse croire à un tarif courant, alors que cette ligne
        # appartient à la rubrique « Successions ». Le libellé seul est ambigu ; le chemin lève
        # l'ambiguïté pour le LLM comme pour le lecteur du tableau.
        chemin = retriever._chemin_section_cb(banque, annee, semestre, segment, section)
        if chemin and chemin.lower() not in (libelle or "").lower():
            libelle = f"{chemin} > {libelle}"
        periodes.add((annee, semestre))
        cle = (banque, segment)
        struct.setdefault(cle, {}).setdefault(libelle, {})
        val = "Gratuit" if gratuit else (valeur_propre or (f"{montant:,.0f} FCFA".replace(",", " ") if montant else None))
        # Le pipe est le séparateur de colonnes Markdown : une valeur qui en contient (arrive sur
        # les lignes mal découpées à l'OCR, ex. BNI Entreprises « Frais de tenue et de gestion »)
        # décale toutes les colonnes suivantes et rend la ligne — voire le tableau — illisible.
        # Constaté dans la batterie du 2026-07-27. On neutralise le caractère sans perdre la donnée.
        if val and "|" in str(val):
            val = str(val).replace("|", " / ")
        if val:
            struct[cle][libelle][(annee, semestre)] = val

    periodes = sorted(periodes, key=lambda p: (p[0], p[1]))
    if not periodes:
        return ""
    cols = [f"{s} {a}" for a, s in periodes]

    lignes_md = []
    for banque in banques:
        for segment in ("Particuliers", "Entreprises"):
            libelles = struct.get((banque, segment))
            if not libelles:
                continue
            # Écarter les libellés OCR dupliqués ("Frais XFrais X") puis garder les MIEUX
            # renseignés (le plus de périodes remplies), les plus courts/propres en priorité.
            propres = {k: v for k, v in libelles.items() if not _DUP_RE.search(k)}
            source = propres if propres else libelles
            # PRIORITÉ AU TERME PRINCIPAL (2026-07-27, trouvé par la batterie de test).
            # Les synonymes sont volontairement larges — « tenue » embarque « relevé » et
            # « frais fixe » parce que SGCI/SIB/BICICI nomment ainsi leur tenue de compte. Mais
            # tous les synonymes pesaient PAREIL au moment de couper à max_libelles : sur une
            # comparaison BNI/ECOBANK des frais de tenue, le tableau se remplissait de « Demande
            # de solde au guichet » et « Frais fixe d'impayés » (captés par « relevé » et « frais
            # fixe ») pendant que les VRAIES lignes — les tranches de revenu BNI, cœur de la
            # réponse — se faisaient couper. On classe donc d'abord les libellés qui contiennent
            # le terme demandé lui-même ; les synonymes larges ne servent plus qu'à COMPLÉTER.
            primaires = [t for t in (termes[:2] if termes else []) if t]
            def _est_primaire(lib):
                return any(t in lib.lower() for t in primaires)
            def _rang(kv):
                return (0 if _est_primaire(kv[0]) else 1, -len(kv[1]), len(kv[0]))
            ordonnes = sorted(source.items(), key=_rang)
            # Les libellés PRIMAIRES ont droit à une marge supplémentaire : ils forment souvent
            # une famille indissociable (les 4 tranches de revenu BNI, les 13 offres ECOBANK) et
            # n'en montrer qu'une partie donne une réponse fausse, pas une réponse abrégée.
            # Les synonymes larges, eux, restent plafonnés — c'est du complément, pas la réponse.
            prim = [kv for kv in ordonnes if _est_primaire(kv[0])][:max_libelles + 6]
            sec  = [kv for kv in ordonnes if not _est_primaire(kv[0])]
            tries = prim + sec[:max(0, max_libelles - len(prim))]
            lignes_md.append(f"\n#### {banque} — {segment}\n")
            lignes_md.append("| Service | " + " | ".join(cols) + " |")
            lignes_md.append("|---" * (len(cols) + 1) + "|")
            for libelle, vals in tries:
                row = [vals.get(p, "—") for p in periodes]
                lignes_md.append(f"| {libelle} | " + " | ".join(row) + " |")

    return "\n".join(lignes_md)


def tableau_cb_multi_service(banques: list, termes: list, max_libelles: int = 4) -> str:
    """Comme tableau_cb_exhaustif mais pour PLUSIEURS catégories de service à la fois
    (ex. tenue + virement + carte + retrait) — pour les comparaisons génériques
    ("compare les conditions/frais entre X et Y") où aucun service précis n'est nommé.
    max_libelles réduit (4 au lieu de 8) pour garder une taille raisonnable vu qu'on
    empile plusieurs catégories."""
    blocs = []
    for terme in termes:
        t = tableau_cb_exhaustif(banques, terme, max_libelles=max_libelles)
        if t:
            blocs.append(f"\n### Service : {terme.upper()}\n{t}")
    return "\n".join(blocs)


def comparer_roe(mode: str = "AN3", banques: list = None) -> dict:
    """ROE (%) = Résultat net / Capitaux propres × 100, pour CHAQUE banque (toutes par
    défaut, ou une liste précise), même année.
    Retour : {banque: {'annee': y, 'valeur': roe_pct}}."""
    out = {}
    cx = _conn(); cur = cx.cursor()
    try:
        for b in (banques or BANQUES):
            y = _an_year(cur, b, mode)
            if not y:
                continue
            # NOT ILIKE '%avant%' : exclut "RESULTAT NET AVANT IMPOTS" que '%sultat net%' matchait
            # aussi — bug trouvé le 2026-07-14 (BACI/BNI en avaient les deux, max() prenait à tort
            # le résultat AVANT impôt, gonflant le ROE affiché par le chat, ex. BNI 2024 : 22,7%
            # au lieu de 21,5%).
            # 2026-09-03 : max() restait pris SANS CONDITION quand plusieurs valeurs subsistent
            # apres ce premier filtre (deux rapports annuels qui se recouvrent, ou une vraie
            # anomalie OCR) — meme classe de bug, cf. _resoudre_valeur_ef. Un ratio dont l'un
            # des deux termes est ambigu n'est pas fiable : la banque est omise plutot que de
            # publier un ROE calcule sur un chiffre invente/errone.
            cur.execute("""SELECT ROUND(montant::double precision::numeric,0), annee_rapport
                           FROM ef_indicateurs
                           WHERE banque=%s AND annee_donnee=%s AND is_primary
                             AND libelle ILIKE %s AND libelle NOT ILIKE '%%avant%%' AND montant IS NOT NULL""",
                        (b, y, "%sultat net%"))
            rn_rows = [(float(r[0]), r[1]) for r in cur.fetchall()]
            cur.execute("""SELECT ROUND(montant::double precision::numeric,0), annee_rapport
                           FROM ef_indicateurs
                           WHERE banque=%s AND annee_donnee=%s AND is_primary
                             AND libelle ILIKE %s AND montant IS NOT NULL""",
                        (b, y, "%capitaux propres%"))
            cp_rows = [(float(r[0]), r[1]) for r in cur.fetchall()]
            if not rn_rows or not cp_rows:
                continue
            rn, rn_ambigu = _resoudre_valeur_ef(rn_rows)
            cp, cp_ambigu = _resoudre_valeur_ef(cp_rows)
            if rn_ambigu or cp_ambigu or not cp:
                continue
            roe = rn / cp * 100
            out[b] = {"annee": y, "valeur": round(roe, 1)}
    finally:
        cur.close(); cx.close()
    return out


def comparer_coefficient_exploitation(mode: str = "AN3", banques: list = None) -> dict:
    """Coefficient d'exploitation (%) = Frais généraux / PNB × 100, pour CHAQUE banque
    (toutes par défaut, ou une liste précise), même année. Plus bas = plus efficient.
    N'existe PAS comme ligne directe en base (pas de libellé "coefficient d'exploitation")
    → calculé, comme le ROE.
    Retour : {banque: {'annee': y, 'valeur': coeff_pct}}."""
    out = {}
    cx = _conn(); cur = cx.cursor()
    try:
        for b in (banques or BANQUES):
            y = _an_year(cur, b, mode)
            if not y:
                continue
            # BUG TROUVÉ le 2026-07-27 (en construisant la fiche marché) : le motif était
            # "%produit net bancaire%" (singulier, espaces figés) — exactement celui déjà
            # corrigé dans EF_PATTERNS le 2026-07-13, mais la correction n'avait jamais été
            # reportée ICI. Conséquence silencieuse : BACI et BNI libellent "PRODUITS NET
            # BANCAIRE" (pluriel) → aucun PNB trouvé → aucun coefficient d'exploitation
            # calculé pour ces 2 banques dans TOUT le chat (comparaisons, classements,
            # fiche de synthèse), alors que le dashboard l'affiche correctement puisque
            # dash_app/db.py:805 utilise déjà le motif à jokers. Le chat disait donc
            # "donnée non trouvée" sur une donnée présente et affichée à l'écran.
            # 2026-09-03 : meme correctif que comparer_roe — max() sans condition remplace par
            # _resoudre_valeur_ef (seuil 5%, sinon banque omise plutot qu'un ratio invente).
            cur.execute("""SELECT ROUND(montant::double precision::numeric,0), annee_rapport
                           FROM ef_indicateurs
                           WHERE banque=%s AND annee_donnee=%s AND is_primary
                             AND libelle ILIKE %s AND montant IS NOT NULL""",
                        (b, y, EF_PATTERNS["pnb"]))
            pnb_rows = [(float(r[0]), r[1]) for r in cur.fetchall()]
            if not pnb_rows:
                continue
            pnb, pnb_ambigu = _resoudre_valeur_ef(pnb_rows)
            if pnb_ambigu or not pnb:
                continue

            # MÉTHODE 1, PRIORITAIRE — (PNB − RBE) / PNB, exactement comme le tableau de bord
            # (db.py::ef_coeff_series). Ajoutée le 2026-09-07 : le chat omettait SGCI et
            # ECOBANK d'un classement que l'écran affiche pourtant. Cause — SGCI porte DEUX
            # libellés de charges de périmètres différents (« Charges générales
            # d'exploitation » 94 052 et « Frais Généraux » 106 974 pour 2025, cf. db.py) ;
            # _resoudre_valeur_ef les juge contradictoires et omet la banque. Le résultat brut
            # d'exploitation est une ligne NON AMBIGUË : il supprime le problème à la source.
            # Motif sans « resultat » : NSIA écrit « Résultat Brut d'Exploitation » quand SGCI
            # écrit « RESULTAT BRUTD'EXPLOITATION », en capitales, sans accent ni espace.
            cur.execute("""SELECT ROUND(montant::double precision::numeric,0), annee_rapport
                           FROM ef_indicateurs
                           WHERE banque=%s AND annee_donnee=%s AND is_primary
                             AND libelle ILIKE %s AND montant IS NOT NULL AND montant > 0""",
                        (b, y, "%brut%exploitation%"))
            rbe_rows = [(float(r[0]), r[1]) for r in cur.fetchall()]
            if rbe_rows:
                rbe, rbe_ambigu = _resoudre_valeur_ef(rbe_rows)
                if not rbe_ambigu and rbe is not None:
                    out[b] = {"annee": y, "valeur": round((pnb - rbe) / pnb * 100, 1)}
                    continue

            # MÉTHODE 2, REPLI — libellé direct des charges, seulement quand le RBE manque.
            cur.execute("""SELECT ROUND(montant::double precision::numeric,0), annee_rapport
                           FROM ef_indicateurs
                           WHERE banque=%s AND annee_donnee=%s AND is_primary
                             AND (libelle ILIKE %s OR libelle ILIKE %s) AND montant IS NOT NULL""",
                        (b, y, "%frais g%raux%", "%charges g%rales d%exploitation%"))
            fg_rows = [(float(r[0]), r[1]) for r in cur.fetchall()]
            if not fg_rows:
                continue
            fg, fg_ambigu = _resoudre_valeur_ef(fg_rows)
            if fg_ambigu:
                continue
            out[b] = {"annee": y, "valeur": round(fg / pnb * 100, 1)}
    finally:
        cur.close(); cx.close()
    return out


def format_comparaison(d: dict, unite="FCFA", sens="max") -> tuple:
    """Formate la comparaison en texte trié + renvoie (texte, banque_gagnante)."""
    items = [(k, v.get("valeur", v.get("montant"))) for k, v in d.items()]
    items = [(k, val) for k, val in items if val is not None]
    ambigus = [k for k, v in d.items() if v.get("ambigu")]
    # 2026-09-19 : « manquant » (comparer_ef) — banque avec une année de référence (AN3) mais
    # SANS aucune ligne pour l'indicateur demandé (trou de donnée réel, pas une ambiguïté) —
    # même traitement que "ambigus" ci-dessous : dit, jamais tu.
    manquants = [k for k, v in d.items() if v.get("manquant")]
    if not items:
        msg = "Aucune donnée comparable trouvée dans la base."
        if ambigus:
            msg += (f" ({', '.join(ambigus)} : valeurs contradictoires en base, "
                    f"exclues plutôt que devinées.)")
            for k in ambigus:
                libs = d[k].get("libelles_conflictuels")
                if libs:
                    msg += f"\n  {k} : plusieurs services matchent ce terme — {' / '.join(libs)}"
        if manquants:
            msg += f" ({', '.join(manquants)} : donnée absente en base pour l'année la plus récente.)"
        return msg, None
    items.sort(key=lambda x: x[1], reverse=(sens == "max"))
    gagnant = items[0][0]
    lignes = []
    for k, val in items:
        if d[k].get("gratuit"):
            txt = "GRATUIT"
        elif unite == "%":
            txt = f"{val:,.1f} {unite}".replace(",", " ")
        else:
            txt = f"{val:,.0f} {unite}".replace(",", " ")
        an  = f" ({d[k]['annee']})" if "annee" in d[k] else ""
        lignes.append(f"  - {k}: {txt}{an}")
    entete = ("Comparaison (classée du plus élevé au plus faible — le PREMIER de la liste "
              "est la bonne réponse) :" if sens == "max"
              else "Comparaison (classée du plus faible au plus élevé — le PREMIER de la "
              "liste est la bonne réponse) :")
    texte = entete + "\n" + "\n".join(lignes)
    if ambigus:
        texte += f"\n  [NON INCLUS — valeur ambiguë en base, ne pas deviner] {', '.join(ambigus)}"
        # Cas comparer_cb() : le terme demandé matche PLUSIEURS services distincts (ex.
        # "carte" -> 15 produits de 1 000 à 280 000 FCFA) — donner les libellés en cause
        # plutot qu'un simple "ambigu" muet, pour que le LLM puisse demander a l'utilisateur
        # de preciser le produit au lieu de deviner.
        for k in ambigus:
            libs = d[k].get("libelles_conflictuels")
            if libs:
                texte += f"\n      {k} : plusieurs services matchent ce terme — {' / '.join(libs)}"
    if manquants:
        texte += (f"\n  [NON INCLUS — donnée absente en base pour l'année la plus récente, "
                   f"ne pas deviner] {', '.join(manquants)}")
    return texte, gagnant


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("EF — PNB AN3 :")
    txt, g = format_comparaison(comparer_ef("PNB", "AN3"), "millions FCFA", "max")
    print(txt, "\n  >>> GAGNANT :", g)
    print("\nCB — Attestation de clôture de compte 2025 S1 Particuliers :")
    txt, g = format_comparaison(comparer_cb("Attestation de clôture de compte", 2025, "S1", "Particuliers"), "FCFA", "min")
    print(txt, "\n  >>> MOINS CHER :", g)
