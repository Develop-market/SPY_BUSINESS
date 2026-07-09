"""
run_repair_tenue_compte.py
==========================
Réparation des frais de tenue de compte dans cb_tarifs — BD UNIQUEMENT.

Ce script NE TOUCHE PAS aux fichiers xlsx (le nettoyage les gère).
Il corrige uniquement la BD après chaque chargement :

1. Supprime les montants=0 résiduels (valeur brute "0") qui ne sont pas des
   gratuités réelles (les vraies gratuités sont "Gratuit", jamais le chiffre 0)

2. Propage le label du header "Frais de tenue de compte" vers ses sous-items
   pour qu'ils soient reconnus par les requêtes de frais_tenue_compte() :
   Ex : NSIA Entreprises → ONG/Asso, SARL/PME, Entreprise Individuelle
   ont le bon contexte mais pas "tenue de compte" dans leur libellé.

Reproductible et idempotent — peut être relancé sans risque.

Usage :
    python run_repair_tenue_compte.py
"""

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE / ".env")

import psycopg2

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "intelligence_bancaire"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", ""),
)


def step1_supprimer_zeros(conn) -> int:
    """
    Supprime les lignes avec valeur_brute='0' qui ne sont pas des gratuités.
    Les vraies gratuités bancaires sont toujours 'Gratuit', 'Gratuit', 'N/A',
    jamais le chiffre '0' — ce dernier indique une hallucination LLM.
    """
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM cb_tarifs
        WHERE valeur_brute IN ('0', '0.0', '0,0', '0 FCFA', '0 F')
          AND est_gratuit = FALSE
          AND type_valeur NOT IN ('GRATUIT', 'NON_APPLICABLE', 'SUR_DEMANDE')
    """)
    n = cur.rowcount
    conn.commit()
    cur.close()
    return n


def step2_propager_contexte_tenue(conn) -> int:
    """
    Pour chaque header is_header=TRUE dont le libellé contient 'tenue de compte',
    enrichit le contexte des sous-items directs (section LIKE header.section + '.')
    afin qu'ils soient reconnus par frais_tenue_compte() via la colonne contexte.

    Idempotent : ne double-ajoute pas si déjà présent.
    """
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT DISTINCT banque, annee, semestre, segment, section, libelle
        FROM cb_tarifs
        WHERE is_header = TRUE
          AND section IS NOT NULL AND section != ''
          AND (LOWER(libelle) LIKE '%tenue%compte%'
               OR LOWER(libelle) LIKE '%compte%tenue%')
        ORDER BY banque, annee, semestre, segment, section
    """)
    headers = cur.fetchall()

    total = 0
    for h in headers:
        cur.execute("""
            UPDATE cb_tarifs
            SET contexte = CASE
                WHEN contexte IS NULL OR contexte = '' THEN %s
                WHEN LOWER(contexte) LIKE '%%tenue%%compte%%' THEN contexte
                ELSE contexte || ' > ' || %s
            END
            WHERE banque = %s AND annee = %s AND semestre = %s AND segment = %s
              AND is_header = FALSE
              AND section IS NOT NULL AND section != ''
              AND section LIKE %s
              AND NOT (LOWER(contexte) LIKE '%%tenue%%compte%%')
        """, (
            h["libelle"], h["libelle"],
            h["banque"], h["annee"], h["semestre"], h["segment"],
            h["section"] + ".%",
        ))
        n = cur.rowcount
        if n > 0:
            total += n
            print(f"  [CTX] {h['banque']} {h['annee']} {h['semestre']} "
                  f"{h['segment']} sec={h['section']}: {n} sous-items enrichis")

    conn.commit()
    cur.close()
    return total


def rapport(conn):
    """Résumé post-réparation : frais de tenue de compte par banque/tranche."""
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    print("\n  Verification frais tenue de compte (2026 S1) :")
    for seg in ("Particuliers", "Entreprises"):
        cur.execute("""
            SELECT banque, MIN(montant) AS min_f, COUNT(*) AS n
            FROM cb_tarifs
            WHERE annee=2026 AND semestre='S1'
              AND LOWER(segment) LIKE %s
              AND is_header=FALSE
              AND type_valeur='MONTANT_FCFA' AND montant >= 100
              AND (LOWER(libelle) LIKE '%%tenue%%compte%%'
                   OR LOWER(libelle) LIKE '%%compte%%tenue%%'
                   OR LOWER(libelle) LIKE '%%convenance%%'
                   OR LOWER(contexte) LIKE '%%tenue%%compte%%')
              AND NOT (LOWER(libelle) LIKE '%%epargne%%'
                       OR LOWER(libelle) LIKE '%%épargne%%')
              AND NOT LOWER(libelle) LIKE '%%annuel%%'
              AND NOT LOWER(libelle) LIKE '%%devise%%'
            GROUP BY banque ORDER BY banque
        """, ("%" + seg[:6].lower() + "%",))
        rows = cur.fetchall()
        print(f"    {seg}:")
        for r in rows:
            print(f"      {r['banque']:8} min={r['min_f']:>8,.0f} F  ({r['n']} lignes)")
    cur.close()


def main():
    print("=" * 60)
    print("  REPAIR TENUE DE COMPTE (BD uniquement)")
    print("=" * 60)

    conn = psycopg2.connect(**DB)

    print("\n[1/2] Suppression montants=0 hallucinés...")
    n1 = step1_supprimer_zeros(conn)
    print(f"  -> {n1} lignes supprimées")

    print("\n[2/2] Propagation contexte 'tenue de compte' vers sous-items...")
    n2 = step2_propager_contexte_tenue(conn)
    print(f"  -> {n2} sous-items enrichis")

    rapport(conn)
    conn.close()

    print("\n" + "=" * 60)
    print(f"  Terminé. Zeros: -{n1} | Contextes: +{n2}")
    print("=" * 60)


if __name__ == "__main__":
    main()
