"""
Corrections de données manquantes dans cb_tarifs.
À exécuter APRÈS run_stockage.py --reset pour restaurer les lignes
manuellement vérifiées contre les PDFs sources.

Usage : python run_repair_donnees_manquantes.py
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..',
                                'SGCI Strategic Intelligence — Design System', 'spybusiness', 'dash_app'))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..',
                             'SGCI Strategic Intelligence — Design System', 'spybusiness', '.env'))
except Exception:
    pass

import psycopg2

DB = dict(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', '5432'),
    dbname=os.getenv('DB_NAME', 'intelligence_bancaire'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD', ''),
)

CORRECTIONS = [
    # Vérifiée sur PDF source DATA/SOURCE/CONDITIONS_BANQUES/SGCI/2024/S1_P.pdf
    # Section 8.1.3 — Achat et Vente de billets de banque en autre devise
    # Sub-item "Frais de dossier (uniquement par caisse)T2" = 15 000 FCFA
    # Non extrait lors du preprocessing OCR (OCR a assigné le prix header 15000
    # au row tob au lieu de créer un row séparé pour ce sub-item)
    {
        "banque": "SGCI", "annee": 2024, "semestre": "S1", "segment": "Particuliers",
        "section": "8.1.3",
        "contexte": "Achat et Vente de billets de banque en autre devise (par caisse/par compte)",
        "libelle": "Frais de dossier (uniquement par caisse)T2",
        "valeur_brute": "15 000", "valeur_propre": "15000",
        "montant": 15000.0,
        "est_gratuit": False, "is_header": False,
        "type_valeur": "MONTANT_FCFA", "canon_section": 7, "rang": 1,
    },
]


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    inserted = 0
    skipped = 0

    for c in CORRECTIONS:
        cur.execute("""
            SELECT id FROM cb_tarifs
            WHERE banque=%s AND annee=%s AND semestre=%s
              AND LOWER(segment)=LOWER(%s) AND section=%s
              AND LOWER(TRIM(libelle))=LOWER(TRIM(%s))
        """, (c["banque"], c["annee"], c["semestre"], c["segment"],
               c["section"], c["libelle"]))
        if cur.fetchone():
            print(f"  SKIP (existe): {c['banque']} {c['annee']} {c['section']} — {c['libelle'][:50]}")
            skipped += 1
            continue

        cur.execute("""
            INSERT INTO cb_tarifs
              (banque, annee, semestre, segment, section, contexte,
               libelle, valeur_brute, valeur_propre, montant,
               est_gratuit, is_header, type_valeur, canon_section, rang)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (c["banque"], c["annee"], c["semestre"], c["segment"],
               c["section"], c["contexte"], c["libelle"],
               c["valeur_brute"], c["valeur_propre"], c["montant"],
               c["est_gratuit"], c["is_header"], c["type_valeur"], c["canon_section"],
               c.get("rang", 1)))
        print(f"  INSERT: {c['banque']} {c['annee']} {c['section']} — {c['libelle'][:50]} ({c['montant']} FCFA)")
        inserted += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"\nTermine : {inserted} inseres, {skipped} deja presents.")


if __name__ == "__main__":
    main()
