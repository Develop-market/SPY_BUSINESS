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


def comparer_ef(indicateur: str, mode: str = "AN3") -> dict:
    """Valeur d'un indicateur EF pour CHAQUE banque, à son AN3 (ou AN1).
    Retour : {banque: {'annee': y, 'valeur': v}} (millions FCFA)."""
    pat = EF_PATTERNS.get((indicateur or "").strip().lower(), f"%{(indicateur or '').strip()}%")
    out = {}
    cx = _conn(); cur = cx.cursor()
    try:
        for b in BANQUES:
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
        txt = "GRATUIT" if (d[k].get("gratuit")) else f"{val:,.0f} {unite}".replace(",", " ")
        an  = f" ({d[k]['annee']})" if "annee" in d[k] else ""
        lignes.append(f"  - {k}: {txt}{an}")
    entete = ("Comparaison (classée du plus élevé au plus faible) :" if sens == "max"
              else "Comparaison (classée du moins cher au plus cher) :")
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
