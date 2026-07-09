"""
run_repair_canon_section.py
===========================
Calcule et stocke la colonne `canon_section` dans cb_tarifs.

Logique : vote majoritaire inter-éditions.
  Pour chaque groupe (norm_libelle, banque, segment), on détermine la section
  canonique BCEAO la plus fréquente à travers toutes les éditions disponibles,
  puis on l'applique à TOUTES les lignes du groupe — y compris celles dont le
  code section brut pointe vers une autre section (ex. SGCI 2024 qui avait
  11 sections non alignées BCEAO).

Résultat : `canon_section` est cohérente à 100% au sein d'un même groupe.
  Les lignes headers reçoivent leur valeur canonique brute (sans vote).

À relancer après chaque import de nouvelles conditions de banques :
  python run_repair_canon_section.py

Usage optionnel :
  python run_repair_canon_section.py --banques SGCI BNI   # recalculer une banque
  python run_repair_canon_section.py --reset              # recréer la colonne
"""
import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict, Counter
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE / ".env")

sys.path.insert(0, str(BASE / "SGCI Strategic Intelligence — Design System" / "spybusiness"))
from dash_app.cb_sections import canonical_section, _norm

import psycopg2
from psycopg2.extras import execute_values

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "intelligence_bancaire"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", ""),
)


def build_canon_section(banques=None):
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()

    # Créer la colonne si absente
    cur.execute("""
        ALTER TABLE cb_tarifs
        ADD COLUMN IF NOT EXISTS canon_section SMALLINT
    """)
    conn.commit()

    # Charger les lignes concernées
    if banques:
        placeholders = ",".join(["%s"] * len(banques))
        cur.execute(
            f"""SELECT id, banque, libelle, section, contexte, segment, is_header
                FROM cb_tarifs WHERE banque IN ({placeholders})""",
            banques,
        )
    else:
        cur.execute(
            "SELECT id, banque, libelle, section, contexte, segment, is_header FROM cb_tarifs"
        )
    all_rows = cur.fetchall()
    print(f"  Lignes chargées : {len(all_rows):,}")

    hdr_ids = {r[0] for r in all_rows if r[6]}

    # Phase A — calcul brut pour chaque ligne
    raw_canon = {}
    for rid, banque, lib, sec, ctx, seg, _ in all_rows:
        sid, _, _ = canonical_section(banque, sec or "", lib, ctx)
        raw_canon[rid] = (sid, _norm(lib or ""), banque, seg)

    # Phase B — vote majoritaire (lignes non-header seulement)
    groups = defaultdict(list)
    for rid, (sid, norm_lib, banque, seg) in raw_canon.items():
        if rid not in hdr_ids:
            groups[(norm_lib, banque, seg)].append((rid, sid))

    consensus = {}
    conflicts = 0
    fixed = 0
    for key, entries in groups.items():
        sec_ids = [e[1] for e in entries]
        if len(set(sec_ids)) == 1:
            for rid, sid in entries:
                consensus[rid] = sid
            continue
        conflicts += 1
        majority = Counter(sec_ids).most_common(1)[0][0]
        for rid, sid in entries:
            consensus[rid] = majority
            if sid != majority:
                fixed += 1

    # Phase C — mise à jour
    updates = []
    for rid, (sid, _, _, _) in raw_canon.items():
        if rid in hdr_ids:
            updates.append((sid, rid))
        else:
            updates.append((consensus.get(rid, sid), rid))

    execute_values(
        cur,
        "UPDATE cb_tarifs SET canon_section = v.sec "
        "FROM (VALUES %s) AS v(sec, id) "
        "WHERE cb_tarifs.id = v.id",
        updates,
        template="(%s::smallint, %s::int)",
    )
    conn.commit()

    print(f"  Groupes conflictuels résolus : {conflicts}")
    print(f"  Lignes corrigées par vote majoritaire : {fixed}")
    print(f"  canon_section mis à jour : {len(updates):,} lignes")

    # Vérification
    cur.execute("SELECT COUNT(*) FROM cb_tarifs WHERE canon_section IS NULL")
    nulls = cur.fetchone()[0]
    if nulls:
        print(f"  AVERTISSEMENT : {nulls} lignes sans canon_section")
    else:
        print("  Toutes les lignes ont une canon_section OK")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--banques", nargs="*", help="Recalculer certaines banques seulement")
    parser.add_argument("--reset", action="store_true", help="Supprimer et recréer la colonne")
    args = parser.parse_args()

    if args.reset:
        conn = psycopg2.connect(**DB)
        cur = conn.cursor()
        cur.execute("ALTER TABLE cb_tarifs DROP COLUMN IF EXISTS canon_section")
        conn.commit()
        conn.close()
        print("Colonne canon_section supprimée.")

    print("=" * 55)
    print("  CALCUL CANON_SECTION (vote majoritaire)")
    print("=" * 55)
    build_canon_section(banques=args.banques)
    print("=" * 55)
    print("  Terminé.")
    print("=" * 55)
