# -*- coding: utf-8 -*-
"""
Correction REPRODUCTIBLE des trous `is_primary` dans ef_indicateurs.

Contexte
--------
L'app n'affiche/n'utilise QUE les lignes `is_primary=TRUE` (voir db.py, requête
kpis : `WHERE is_primary=TRUE`). Or certaines lignes de CRÉDITS / DÉPÔTS clientèle
ont bien été extraites (le montant EST en base) mais aucune n'a été marquée
primaire pour cette (banque, année) → la donnée existe mais reste invisible
(ex. dépôts BICICI 2023 = 778 Mds → pas de barre sur le graphique Crédits vs Dépôts).

Ce que fait ce script
---------------------
- Détecte AUTOMATIQUEMENT (pas en dur) chaque couple (banque, année) où la famille
  CRÉDITS clientèle ou DÉPÔTS clientèle a au moins une ligne MAIS aucune `is_primary`.
- Promeut la ligne représentative (montant agrégé = le plus grand de la famille,
  tie-break : id le plus petit) en `is_primary=TRUE`.
- AUCUN montant n'est modifié : on ne fait que « cocher la case ».
- Idempotent : relancer ne refait rien si tout est déjà corrigé.
- Sauvegarde JSON horodatée des lignes touchées AVANT modification.

Usage
-----
    python dash_app/fix_ef_is_primary.py            # applique (avec backup)
    python dash_app/fix_ef_is_primary.py --dry-run  # montre sans modifier
"""
import os, sys, json, datetime
import psycopg2
import psycopg2.extras

DB = dict(host="localhost", dbname="intelligence_bancaire", user="postgres", password="12341234")

# Mêmes familles que db.py (requête kpis vue d'ensemble)
DEPOTS = ("(LOWER(libelle) LIKE '%%depot%%' "
          "OR (LOWER(libelle) LIKE '%%dette%%' AND LOWER(libelle) LIKE '%%clientele%%')) "
          "AND LOWER(libelle) NOT LIKE '%%interbancaire%%'")
CREDITS = ("(LOWER(libelle) LIKE '%%credit%%' OR LOWER(libelle) LIKE '%%creance%%') "
           "AND LOWER(libelle) LIKE '%%clientele%%' AND LOWER(libelle) NOT LIKE '%%interbancaire%%'")
FAMILLES = {"DÉPÔTS": DEPOTS, "CRÉDITS": CREDITS}


def trouver_trous(cur):
    """Retourne la liste des lignes à promouvoir (une par couple banque/année/famille en trou)."""
    a_promouvoir = []
    for nom, cond in FAMILLES.items():
        # couples (banque, année) qui ont des lignes mais AUCUNE primaire
        cur.execute(f"""
            SELECT banque, annee_donnee
            FROM ef_indicateurs
            WHERE ({cond}) AND montant IS NOT NULL
            GROUP BY banque, annee_donnee
            HAVING COUNT(*) FILTER (WHERE is_primary) = 0
        """)
        trous = cur.fetchall()
        for banque, annee in trous:
            # ligne représentative = montant le plus grand (agrégat clientèle), id mini en cas d'égalité
            cur.execute(f"""
                SELECT id, banque, annee_donnee, libelle, montant, is_primary
                FROM ef_indicateurs
                WHERE banque=%s AND annee_donnee=%s AND ({cond}) AND montant IS NOT NULL
                ORDER BY montant DESC, id ASC
                LIMIT 1
            """, (banque, annee))
            row = cur.fetchone()
            if row:
                a_promouvoir.append({"famille": nom, "id": row[0], "banque": row[1],
                                     "annee_donnee": row[2], "libelle": row[3], "montant": row[4]})
    return a_promouvoir


def main():
    dry = "--dry-run" in sys.argv
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cibles = trouver_trous(cur)

    if not cibles:
        print("✅ Aucun trou is_primary détecté — rien à corriger (idempotent).")
        conn.close(); return

    print(f"{'[DRY-RUN] ' if dry else ''}{len(cibles)} ligne(s) à promouvoir en is_primary=TRUE :\n")
    for c in cibles:
        print(f"  {c['famille']:8} {c['banque']:8} {c['annee_donnee']} | id={c['id']:>6} | "
              f"{(c['libelle'] or '')[:40]:40} = {round(c['montant']) if c['montant'] is not None else None} M")

    if dry:
        print("\n(DRY-RUN : aucune modification effectuée.)")
        conn.close(); return

    # Sauvegarde AVANT modification
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"ef_is_primary_backup_{stamp}.json")
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump([{**c, "montant": float(c["montant"]) if c["montant"] is not None else None,
                    "is_primary_avant": False} for c in cibles], f, ensure_ascii=False, indent=2)
    print(f"\n💾 Backup écrit : {backup_path}")

    ids = [c["id"] for c in cibles]
    cur.execute("UPDATE ef_indicateurs SET is_primary=TRUE WHERE id = ANY(%s)", (ids,))
    conn.commit()
    print(f"✅ {cur.rowcount} ligne(s) mises à jour (is_primary=TRUE). Aucun montant modifié.")
    conn.close()


if __name__ == "__main__":
    main()
