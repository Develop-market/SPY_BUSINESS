"""
run_imputation.py — Imputation temporelle automatique
======================================================
Détecte les périodes CB à extraction insuffisante et les complète
avec les données de la période réelle la plus proche temporellement.

Règle : si n_lignes_réelles(banque, segment, annee, semestre) < seuil
        → imputer depuis la période réelle la plus récente disponible.

Usage :
    python run_imputation.py              # toutes banques / segments
    python run_imputation.py --dry-run    # simulation sans écriture DB
    python run_imputation.py --banque BACI
"""

import sys, argparse, statistics
from pathlib import Path
import psycopg2, psycopg2.extras

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "SGCI Strategic Intelligence — Design System" / "spybusiness"))

# ── Paramètres ──────────────────────────────────────────────────────────────
DB_PARAMS = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "intelligence_bancaire",
    "user":     "postgres",
    "password": "",
}

# Seuil absolu minimum : en-dessous = période mauvaise
THRESHOLD_ABS = 100
# Seuil relatif : mauvais si n_reel < THRESHOLD_REL × médiane des bonnes périodes
THRESHOLD_REL = 0.50

# Ordre des semestres pour tri chronologique
SEM_ORDER = {"S1": 1, "S2": 2}


def _period_key(annee, semestre):
    return (int(annee), SEM_ORDER.get(semestre, 0))


def get_conn():
    return psycopg2.connect(**DB_PARAMS)


def analyse_qualite(conn, banque_filter=None):
    """Retourne dict {(banque, seg): [period_info...]} trié chronologiquement."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if banque_filter:
        q = """
            SELECT banque, LOWER(segment) AS seg, annee, semestre,
                   COUNT(*) AS n_total,
                   COUNT(*) FILTER (WHERE source_imputation IS NULL) AS n_reel,
                   COUNT(*) FILTER (WHERE source_imputation IS NOT NULL) AS n_imputed,
                   SUM(CASE WHEN type_valeur='TAUX_%%' THEN 1 ELSE 0 END) AS n_taux
            FROM cb_tarifs WHERE banque=%%s
            GROUP BY banque, LOWER(segment), annee, semestre
        """
        cur.execute(q % "", (banque_filter,))
    else:
        q = """
            SELECT banque, LOWER(segment) AS seg, annee, semestre,
                   COUNT(*) AS n_total,
                   COUNT(*) FILTER (WHERE source_imputation IS NULL) AS n_reel,
                   COUNT(*) FILTER (WHERE source_imputation IS NOT NULL) AS n_imputed,
                   SUM(CASE WHEN type_valeur='TAUX_%' THEN 1 ELSE 0 END) AS n_taux
            FROM cb_tarifs
            GROUP BY banque, LOWER(segment), annee, semestre
        """
        cur.execute(q)
    rows = cur.fetchall()

    grouped = {}
    for r in rows:
        key = (r["banque"], r["seg"])
        grouped.setdefault(key, []).append(dict(r))

    for key in grouped:
        grouped[key].sort(key=lambda p: _period_key(p["annee"], p["semestre"]))

    return grouped


def compute_threshold(periods):
    """Seuil dynamique = max(THRESHOLD_ABS, THRESHOLD_REL × médiane des périodes réelles)."""
    reel_counts = [p["n_reel"] for p in periods if p["n_reel"] > 0]
    if not reel_counts:
        return THRESHOLD_ABS
    med = statistics.median(reel_counts)
    return max(THRESHOLD_ABS, med * THRESHOLD_REL)


def is_good(period, threshold):
    return period["n_reel"] >= threshold


def find_best_source(periods, target, threshold):
    """
    Trouve la période réelle la plus récente avant la cible,
    sinon la plus proche après.
    """
    good = [p for p in periods if is_good(p, threshold)
            and _period_key(p["annee"], p["semestre"]) != _period_key(target["annee"], target["semestre"])]

    target_key = _period_key(target["annee"], target["semestre"])

    prior = [p for p in good if _period_key(p["annee"], p["semestre"]) < target_key]
    after = [p for p in good if _period_key(p["annee"], p["semestre"]) > target_key]

    if prior:
        return prior[-1]   # la plus récente avant
    if after:
        return after[0]    # la plus proche après
    return None


def impute_period(conn, banque, segment, annee, semestre, source, dry_run=False):
    """
    Impute les libellés manquants dans (banque, segment, annee, semestre)
    depuis la période source. Ne touche pas les lignes réelles existantes.
    """
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur2 = conn.cursor()

    src_label = f"IMPUTATION_{source['semestre']}_{source['annee']}"

    # 1. Supprimer les anciennes lignes imputées (pour permettre re-run propre)
    cur2.execute("""DELETE FROM cb_tarifs
                    WHERE banque=%s AND annee=%s AND semestre=%s AND LOWER(segment)=%s
                    AND source_imputation IS NOT NULL""",
                 (banque, annee, semestre, segment.lower()))
    deleted = cur2.rowcount

    # 2. Libellés déjà présents en réel (à ne pas écraser)
    cur.execute("""SELECT LOWER(TRIM(libelle)) AS lib FROM cb_tarifs
                   WHERE banque=%s AND annee=%s AND semestre=%s AND LOWER(segment)=%s
                   AND source_imputation IS NULL""",
                (banque, annee, semestre, segment.lower()))
    existing = {r["lib"] for r in cur.fetchall()}

    # 3. Rows source
    cur.execute("""SELECT banque, segment, section, contexte, libelle,
                          valeur_brute, valeur_propre, montant, type_valeur,
                          rang, is_header, est_gratuit
                   FROM cb_tarifs
                   WHERE banque=%s AND annee=%s AND semestre=%s AND LOWER(segment)=%s""",
                (banque, source["annee"], source["semestre"], segment.lower()))
    src_rows = cur.fetchall()

    inserted = 0
    for r in src_rows:
        lib_key = (r["libelle"] or "").lower().strip()
        if lib_key in existing:
            continue
        if not dry_run:
            cur2.execute("""INSERT INTO cb_tarifs
                             (banque, annee, semestre, segment, section, contexte, libelle,
                              valeur_brute, valeur_propre, montant, type_valeur, rang,
                              is_header, est_gratuit, source_imputation)
                             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                         (banque, annee, semestre, r["segment"],
                          r["section"], r["contexte"], r["libelle"],
                          r["valeur_brute"], r["valeur_propre"], r["montant"],
                          r["type_valeur"], r["rang"], r["is_header"],
                          r["est_gratuit"], src_label))
        inserted += 1

    if not dry_run:
        conn.commit()

    return deleted, inserted, src_label


def run(banque_filter=None, dry_run=False):
    conn = get_conn()
    grouped = analyse_qualite(conn, banque_filter)

    print("=" * 70)
    print("  IMPUTATION TEMPORELLE — CB Tarifs")
    if dry_run:
        print("  [DRY-RUN — aucune écriture en base]")
    print("=" * 70)

    total_imputed = 0
    actions = []

    for (banque, seg), periods in sorted(grouped.items()):
        threshold = compute_threshold(periods)
        bad = [p for p in periods if not is_good(p, threshold)]

        if not bad:
            continue

        print(f"\n  {banque} / {seg.capitalize()} — seuil={threshold:.0f} lignes")

        for period in bad:
            source = find_best_source(periods, period, threshold)
            annee, sem = period["annee"], period["semestre"]

            if source is None:
                print(f"    ⚠ {annee} {sem} : {period['n_reel']} lignes réelles"
                      f" — AUCUNE période source disponible")
                continue

            deleted, inserted, label = impute_period(
                conn, banque, seg, annee, sem, source, dry_run=dry_run
            )
            verb = "SIMULÉ" if dry_run else "IMPUTÉ"
            print(f"    {verb} {annee} {sem} ({period['n_reel']} réels)"
                  f" ← {source['annee']} {source['semestre']}"
                  f" ({source['n_reel']} lignes) : +{inserted} lignes"
                  f" ({deleted} anciennes remplacées)")
            total_imputed += inserted
            actions.append((banque, seg, annee, sem, source["annee"], source["semestre"], inserted))

    # Bilan final
    print(f"\n{'='*70}")
    print(f"  BILAN : {len(actions)} période(s) imputée(s) | {total_imputed} lignes insérées")
    if actions:
        print(f"\n  Récapitulatif :")
        for b, s, a, sem, sa, ssem, n in actions:
            print(f"    {b:<10} {s:<12} {a} {sem} ← {sa} {ssem} (+{n})")
    print(f"{'='*70}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Imputation temporelle CB")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulation sans écriture en base")
    parser.add_argument("--banque", type=str, default=None,
                        help="Filtrer sur une banque (ex: BACI)")
    args = parser.parse_args()
    run(banque_filter=args.banque, dry_run=args.dry_run)
