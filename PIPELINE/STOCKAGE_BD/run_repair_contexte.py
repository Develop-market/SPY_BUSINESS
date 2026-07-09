"""
run_repair_contexte.py
======================
Post-processing DB : remplit contexte vide en reconstruisant
le fil d'ariane depuis les lignes is_header de la meme tranche.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE / ".env")
import psycopg2

DB = dict(host=os.getenv("DB_HOST","localhost"), port=int(os.getenv("DB_PORT",5432)),
          dbname=os.getenv("DB_NAME","intelligence_bancaire"),
          user=os.getenv("DB_USER","postgres"), password=os.getenv("DB_PASSWORD",""))

def _build_contexte(section: str, hmap: dict) -> str:
    if not section:
        return ""
    sec = section.strip().rstrip(".")
    parts = sec.split(".")
    ancestors = []
    for i in range(1, len(parts)):
        prefix = ".".join(parts[:i])
        lbl = hmap.get(prefix, "").strip()
        if lbl:
            ancestors.append(lbl)
    return " | ".join(ancestors)

def main():
    print("=" * 55)
    print("  REPARATION CONTEXTE")
    print("=" * 55)
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT banque, annee, semestre, segment FROM cb_tarifs ORDER BY 1,2,3,4")
    tranches = cur.fetchall()

    total = 0
    for banque, annee, semestre, segment in tranches:
        # Carte section→libelle depuis les headers de la tranche
        cur.execute("""
            SELECT section, libelle FROM cb_tarifs
            WHERE banque=%s AND annee=%s AND semestre=%s AND segment=%s
              AND is_header=TRUE AND section IS NOT NULL AND section!=''
        """, (banque, annee, semestre, segment))
        hmap = {r[0].strip().rstrip("."): r[1] for r in cur.fetchall() if r[0] and r[1]}
        if not hmap:
            continue

        cur.execute("""
            SELECT id, section FROM cb_tarifs
            WHERE banque=%s AND annee=%s AND semestre=%s AND segment=%s
              AND is_header=FALSE
              AND (contexte IS NULL OR contexte='')
              AND section IS NOT NULL AND section!=''
        """, (banque, annee, semestre, segment))
        rows = cur.fetchall()

        repaired = 0
        for rid, sec in rows:
            ctx = _build_contexte(sec, hmap)
            if ctx:
                cur.execute("UPDATE cb_tarifs SET contexte=%s WHERE id=%s", (ctx, rid))
                repaired += 1

        if repaired:
            conn.commit()
            print(f"  {banque} {annee} {semestre} {segment}: {repaired} contextes reconstruits")
        total += repaired

    print(f"\n  Total: {total} lignes reparees")
    conn.close()

if __name__ == "__main__":
    main()
