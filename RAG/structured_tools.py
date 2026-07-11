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
EF_PATTERNS = {
    "pnb": "%produit net bancaire%", "produit net bancaire": "%produit net bancaire%",
    "résultat net": "%sultat net%", "resultat net": "%sultat net%", "rn": "%sultat net%",
    "capitaux propres": "%capitaux propres%", "fonds propres": "%capitaux propres%",
    "résultat d'exploitation": "%sultat d'exploitation%", "resultat d'exploitation": "%sultat d'exploitation%",
    "résultat brut": "%sultat brut d'exploitation%", "résultat brut d'exploitation": "%sultat brut d'exploitation%",
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
            cur.execute("""SELECT DISTINCT ROUND(montant::numeric,0) FROM ef_indicateurs
                           WHERE banque=%s AND annee_donnee=%s AND is_primary
                             AND libelle ILIKE %s AND montant IS NOT NULL""", (b, y, pat))
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
        cur.execute("""SELECT DISTINCT ROUND(montant::numeric,0) FROM ef_indicateurs
                       WHERE banque=%s AND annee_donnee=%s AND is_primary
                         AND libelle ILIKE %s AND montant IS NOT NULL""", (banque, y, pat))
        vals = [float(r[0]) for r in cur.fetchall()]
        return {"annee": y, "valeur": max(vals)} if vals else {}
    finally:
        cur.close(); cx.close()


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
            SELECT banque, segment, libelle, annee, semestre, valeur_propre, montant, est_gratuit
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
    for banque, segment, libelle, annee, semestre, valeur_propre, montant, gratuit in rows:
        periodes.add((annee, semestre))
        cle = (banque, segment)
        struct.setdefault(cle, {}).setdefault(libelle, {})
        val = "Gratuit" if gratuit else (valeur_propre or (f"{montant:,.0f} FCFA".replace(",", " ") if montant else None))
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
            tries = sorted(source.items(), key=lambda kv: (-len(kv[1]), len(kv[0])))[:max_libelles]
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
            cur.execute("""SELECT DISTINCT ROUND(montant::numeric,0) FROM ef_indicateurs
                           WHERE banque=%s AND annee_donnee=%s AND is_primary
                             AND libelle ILIKE %s AND montant IS NOT NULL""",
                        (b, y, "%sultat net%"))
            rn_vals = [float(r[0]) for r in cur.fetchall()]
            cur.execute("""SELECT DISTINCT ROUND(montant::numeric,0) FROM ef_indicateurs
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
            cur.execute("""SELECT DISTINCT ROUND(montant::numeric,0) FROM ef_indicateurs
                           WHERE banque=%s AND annee_donnee=%s AND is_primary
                             AND libelle ILIKE %s AND montant IS NOT NULL""",
                        (b, y, "%produit net bancaire%"))
            pnb_vals = [float(r[0]) for r in cur.fetchall()]
            cur.execute("""SELECT DISTINCT ROUND(montant::numeric,0) FROM ef_indicateurs
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
