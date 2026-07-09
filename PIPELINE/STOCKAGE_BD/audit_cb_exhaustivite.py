"""
AUDIT CB — Vérification exhaustivité et véracité post-stockage
==============================================================
Vérifie que pour chaque banque, les catégories principales retournent
TOUS les types de frais avec leurs prix.

Usage:
  python audit_cb_exhaustivite.py
  python audit_cb_exhaustivite.py --banque SGCI
"""

import sys, os, argparse
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE / ".env")

import psycopg2

DB_PARAMS = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME",     "intelligence_bancaire"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CATEGORIES_CLES = [
    ("TENUE DE COMPTE",  ["tenue de compte", "tenue du compte"]),
    ("OUVERTURE",        ["ouverture de compte", "ouverture du compte", "conditions ouverture"]),
    ("CARTE",            ["carte", "cartes bancaire", "visa", "mastercard"]),
    ("VIREMENT LOCAL",   ["virement", "virement local", "virement interne"]),
    ("RETRAIT",          ["retrait", "retrait guichet", "retrait gab"]),
    ("CHEQUE",           ["cheque", "carnet de cheque"]),
    ("TRANSFERT",        ["transfert", "transfert international", "western union"]),
    ("CLOTURE",          ["cloture", "fermeture de compte"]),
]


def run_audit(banque_filter: str | None = None):
    conn = psycopg2.connect(**DB_PARAMS)
    cur  = conn.cursor()

    # ── Bilan global ──────────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT banque) FROM cb_tarifs")
    total, n_banques = cur.fetchone()
    print(f"\n{'='*70}")
    print(f"  AUDIT EXHAUSTIVITÉ CB")
    print(f"  Total lignes : {total:,} | Banques : {n_banques}")
    print(f"{'='*70}")

    # ── Par banque ────────────────────────────────────────────────────────────
    cur.execute("""
        SELECT banque, annee, semestre, segment, COUNT(*) as n
        FROM cb_tarifs
        GROUP BY banque, annee, semestre, segment
        ORDER BY banque, annee, semestre, segment
    """)
    rows = cur.fetchall()
    print(f"\n  Lignes par banque/année/semestre/segment :")
    prev_banque = None
    for banque, annee, sem, seg, n in rows:
        if banque_filter and banque != banque_filter.upper():
            continue
        if banque != prev_banque:
            print(f"\n  ── {banque} ──")
            prev_banque = banque
        print(f"    {annee} {sem} {seg:<15} : {n:>5} lignes")

    # ── Analyse par catégorie clé ─────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print(f"  CATÉGORIES CLÉS — lignes par banque")
    print(f"{'─'*70}")

    cur.execute("SELECT DISTINCT banque FROM cb_tarifs ORDER BY banque")
    banques = [r[0] for r in cur.fetchall()]

    for cat_name, keywords in CATEGORIES_CLES:
        # Construire la condition LIKE
        conditions = " OR ".join(
            f"LOWER(contexte) LIKE '%{kw}%' OR LOWER(libelle) LIKE '%{kw}%'"
            for kw in keywords
        )
        cur.execute(f"""
            SELECT banque, COUNT(*) as n, COUNT(CASE WHEN type_valeur='MONTANT_FCFA' THEN 1 END) as n_montant
            FROM cb_tarifs
            WHERE ({conditions})
            AND is_header = FALSE
            GROUP BY banque
            ORDER BY banque
        """)
        cat_rows = cur.fetchall()
        cat_dict = {r[0]: (r[1], r[2]) for r in cat_rows}

        print(f"\n  {cat_name}")
        for b in banques:
            if banque_filter and b != banque_filter.upper():
                continue
            n, n_m = cat_dict.get(b, (0, 0))
            flag = "✅" if n >= 3 else ("⚠️" if n > 0 else "❌")
            print(f"    {b:<10} {flag}  {n:>4} lignes  ({n_m} avec montant FCFA)")

    # ── Détail tenue de compte ────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print(f"  DÉTAIL TENUE DE COMPTE — tous types par banque (2026 S1 Particuliers)")
    print(f"{'─'*70}")

    cur.execute("""
        SELECT banque, libelle, valeur_propre, type_valeur
        FROM cb_tarifs
        WHERE (LOWER(contexte) LIKE '%tenue de compte%' OR LOWER(libelle) LIKE '%tenue de compte%')
        AND is_header = FALSE
        AND annee = (SELECT MAX(annee) FROM cb_tarifs WHERE banque = cb_tarifs.banque)
        AND semestre = 'S1'
        AND segment = 'Particuliers'
        ORDER BY banque, libelle
    """)
    rows = cur.fetchall()
    prev_b = None
    for banque, libelle, valeur, tv in rows:
        if banque_filter and banque != banque_filter.upper():
            continue
        if banque != prev_b:
            print(f"\n  {banque}")
            prev_b = banque
        flag = "💰" if tv == "MONTANT_FCFA" else ("✓" if tv == "GRATUIT" else "·")
        print(f"    {flag}  {libelle[:55]:<55}  {valeur or ''}")

    # ── Lignes sans contexte ─────────────────────────────────────────────────
    cur.execute("""
        SELECT banque, COUNT(*) as n
        FROM cb_tarifs
        WHERE (contexte IS NULL OR contexte = '')
        AND is_header = FALSE
        GROUP BY banque ORDER BY banque
    """)
    no_ctx = cur.fetchall()
    if no_ctx:
        print(f"\n{'─'*70}")
        print(f"  ⚠️  Lignes SANS CONTEXTE (à améliorer)")
        for banque, n in no_ctx:
            if banque_filter and banque != banque_filter.upper():
                continue
            pct = n / max(1, total) * 100
            print(f"    {banque:<10} {n:>5} lignes ({pct:.1f}%)")

    cur.close()
    conn.close()
    print(f"\n{'='*70}")
    print("  Audit terminé.")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--banque", help="Filtrer une banque (ex: SGCI)")
    args = ap.parse_args()
    run_audit(args.banque)
