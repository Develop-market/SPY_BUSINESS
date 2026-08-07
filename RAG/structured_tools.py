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
            cur.execute("""SELECT DISTINCT ROUND(montant::double precision::numeric,0) FROM ef_indicateurs
                           WHERE banque=%s AND annee_donnee=%s AND is_primary
                             AND libelle ILIKE %s AND libelle NOT ILIKE %s
                             AND montant IS NOT NULL""", (b, y, pat, "%avant%"))
            vals = [float(r[0]) for r in cur.fetchall()]
            if vals:
                out[b] = {"annee": y, "valeur": max(vals)}   # valeur représentative
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
        cur.execute("""SELECT DISTINCT ROUND(montant::double precision::numeric,0) FROM ef_indicateurs
                       WHERE banque=%s AND annee_donnee=%s AND is_primary
                         AND libelle ILIKE %s AND libelle NOT ILIKE %s
                         AND montant IS NOT NULL""", (banque, y, pat, "%avant%"))
        vals = [float(r[0]) for r in cur.fetchall()]
        return {"annee": y, "valeur": max(vals)} if vals else {}
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
    pat = EF_PATTERNS.get((indicateur or "").strip().lower(), f"%{(indicateur or '').strip()}%")
    cx = _conn(); cur = cx.cursor()
    try:
        cur.execute("""SELECT annee_donnee, MAX(ROUND(montant::double precision::numeric,0))
                       FROM ef_indicateurs
                       WHERE banque=%s AND is_primary AND annee_donnee IS NOT NULL
                         AND libelle ILIKE %s AND libelle NOT ILIKE %s AND montant IS NOT NULL
                       GROUP BY annee_donnee ORDER BY annee_donnee""",
                    (banque, pat, "%avant%"))
        return [(int(a), float(v)) for a, v in cur.fetchall() if v is not None]
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
        var_tot = (serie[-1][1] - serie[0][1]) / serie[0][1] * 100
        total = (f"\nVariation totale {serie[0][0]}→{serie[-1][0]} : {var_tot:+.1f} %")
    return "\n".join(lignes) + total


def comparer_cb(service: str, annee, semestre: str, segment: str) -> dict:
    """Tarif d'un service CB pour CHAQUE banque (annee/semestre/segment donnés).
    Retour : {banque: {'montant': m, 'gratuit': bool}}."""
    out = {}
    cx = _conn(); cur = cx.cursor()
    try:
        for b in BANQUES:
            cur.execute("""SELECT montant, est_gratuit, type_valeur FROM cb_tarifs
                           WHERE banque=%s AND annee=%s AND semestre=%s AND segment ILIKE %s
                             AND COALESCE(is_header,false)=false AND libelle ILIKE %s
                             AND type_valeur IN ('MONTANT_FCFA','GRATUIT')""",
                        (b, annee, semestre, f"%{segment}%", f"%{service}%"))
            rows = cur.fetchall()
            mts  = [float(r[0]) for r in rows if r[0] is not None and r[2] == 'MONTANT_FCFA']
            grat = any(r[1] or r[2] == 'GRATUIT' for r in rows)
            if mts:
                out[b] = {"montant": min(mts), "gratuit": False}
            elif grat:
                out[b] = {"montant": 0.0, "gratuit": True}
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
            cur.execute("""SELECT DISTINCT ROUND(montant::double precision::numeric,0) FROM ef_indicateurs
                           WHERE banque=%s AND annee_donnee=%s AND is_primary
                             AND libelle ILIKE %s AND libelle NOT ILIKE '%%avant%%' AND montant IS NOT NULL""",
                        (b, y, "%sultat net%"))
            rn_vals = [float(r[0]) for r in cur.fetchall()]
            cur.execute("""SELECT DISTINCT ROUND(montant::double precision::numeric,0) FROM ef_indicateurs
                           WHERE banque=%s AND annee_donnee=%s AND is_primary
                             AND libelle ILIKE %s AND montant IS NOT NULL""",
                        (b, y, "%capitaux propres%"))
            cp_vals = [float(r[0]) for r in cur.fetchall()]
            if rn_vals and cp_vals and max(cp_vals) != 0:
                roe = max(rn_vals) / max(cp_vals) * 100
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
            cur.execute("""SELECT DISTINCT ROUND(montant::double precision::numeric,0) FROM ef_indicateurs
                           WHERE banque=%s AND annee_donnee=%s AND is_primary
                             AND libelle ILIKE %s AND montant IS NOT NULL""",
                        (b, y, EF_PATTERNS["pnb"]))
            pnb_vals = [float(r[0]) for r in cur.fetchall()]
            cur.execute("""SELECT DISTINCT ROUND(montant::double precision::numeric,0) FROM ef_indicateurs
                           WHERE banque=%s AND annee_donnee=%s AND is_primary
                             AND (libelle ILIKE %s OR libelle ILIKE %s) AND montant IS NOT NULL""",
                        (b, y, "%frais g%raux%", "%charges g%rales d%exploitation%"))
            fg_vals = [float(r[0]) for r in cur.fetchall()]
            if pnb_vals and fg_vals and max(pnb_vals) != 0:
                coeff = max(fg_vals) / max(pnb_vals) * 100
                out[b] = {"annee": y, "valeur": round(coeff, 1)}
    finally:
        cur.close(); cx.close()
    return out


def format_comparaison(d: dict, unite="FCFA", sens="max") -> tuple:
    """Formate la comparaison en texte trié + renvoie (texte, banque_gagnante)."""
    items = [(k, v.get("valeur", v.get("montant"))) for k, v in d.items()]
    items = [(k, val) for k, val in items if val is not None]
    if not items:
        return "Aucune donnée comparable trouvée dans la base.", None
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
    return entete + "\n" + "\n".join(lignes), gagnant


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("EF — PNB AN3 :")
    txt, g = format_comparaison(comparer_ef("PNB", "AN3"), "millions FCFA", "max")
    print(txt, "\n  >>> GAGNANT :", g)
    print("\nCB — Attestation de clôture de compte 2025 S1 Particuliers :")
    txt, g = format_comparaison(comparer_cb("Attestation de clôture de compte", 2025, "S1", "Particuliers"), "FCFA", "min")
    print(txt, "\n  >>> MOINS CHER :", g)
