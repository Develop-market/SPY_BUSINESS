"""Transporte la base locale vers l'hébergeur (Supabase), table par table.

POURQUOI PAS pg_dump. Le vidage classique produit un fichier de 310 Mo qu'il faut ensuite
rejouer d'un bloc : à la moindre coupure — et une liaison domestique en coupe — on recommence
tout, sans savoir ce qui était déjà passé. Ici on copie par lots, table par table, et le script
est REPRENABLE : relancé, il reprend là où il s'était arrêté au lieu de tout refaire.

CE QUI EST TRANSPORTÉ, ET CE QUI NE L'EST PAS
    cb_tarifs        31 985 lignes, dont les vecteurs — c'est le gros du volume
    ef_indicateurs    1 784 lignes
    regl_documents       88 lignes
    banques              référentiel
    utilisateurs      LES COMPTES NE SONT PAS COPIÉS. Volontairement : les empreintes de mots
                      de passe n'ont pas à voyager, et l'application recrée seule le compte
                      d'administration au premier démarrage sur une base vide. Les autres accès
                      seront créés depuis l'écran Administration, ce qui est justement son rôle.
    journal_acces     NON COPIÉ : c'est un journal local, il n'a pas de sens sur un autre hôte.

USAGE
    python migrer_vers_supabase.py --verifier      compte les lignes des deux côtés, n'écrit rien
    python migrer_vers_supabase.py --structure     crée l'extension, les tables et les index
    python migrer_vers_supabase.py                 copie les données (reprenable)
    python migrer_vers_supabase.py --sans-vecteurs copie sans les embeddings (~32 Mo au lieu de 310)

La destination est lue dans DATABASE_URL_CIBLE (ou --cible). La source est le .env local.
"""
import argparse
import os
import sys
import time
from urllib.parse import unquote, urlparse

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "SGCI Strategic Intelligence — Design System",
                                "spybusiness", "dash_app"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

# Ordre imposé par les clés étrangères : les banques d'abord, ce qui s'y rattache ensuite.
TABLES = ["banques", "cb_tarifs", "ef_indicateurs", "regl_documents"]
LOT = 500          # lignes par transaction — au-delà, une coupure fait perdre trop de travail


def params(url):
    u = urlparse(url)
    p = dict(host=u.hostname, port=int(u.port or 5432),
             dbname=(u.path or "/postgres").lstrip("/") or "postgres",
             user=unquote(u.username or ""), password=unquote(u.password or ""))
    if p["host"] not in ("localhost", "127.0.0.1"):
        p["sslmode"] = "require"
    return p


def source():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "intelligence_bancaire"),
        user=os.getenv("DB_USER", "postgres"), password=os.getenv("DB_PASSWORD", ""))


def colonnes(cx, table, sans_vecteurs=False):
    with cx.cursor() as c:
        c.execute("""SELECT column_name, data_type FROM information_schema.columns
                     WHERE table_name = %s ORDER BY ordinal_position""", (table,))
        cols = c.fetchall()
    if sans_vecteurs:
        cols = [x for x in cols if x[0] != "embedding"]
    return [x[0] for x in cols]


def compter(cx, table):
    try:
        with cx.cursor() as c:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            return c.fetchone()[0]
    except Exception:
        return None


# ── STRUCTURE ────────────────────────────────────────────────────────────────────────
def creer_structure(src, dst):
    """Recrée l'extension, les tables et les index sur la destination.

    On lit la structure RÉELLE de la source plutôt que d'écrire un schéma à la main : un schéma
    recopié à la main diverge dès la première migration oubliée, et la divergence ne se voit
    qu'au moment où une requête échoue en production.
    """
    with dst.cursor() as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
        dst.commit()
        print("  extension pgvector : prête")

    for t in TABLES + ["utilisateurs", "journal_acces"]:
        with src.cursor() as cs:
            cs.execute("""SELECT column_name, data_type, character_maximum_length,
                                 is_nullable, column_default, udt_name
                          FROM information_schema.columns WHERE table_name = %s
                          ORDER BY ordinal_position""", (t,))
            cols = cs.fetchall()
        if not cols:
            print(f"  {t:16} absente de la source — ignorée")
            continue

        morceaux = []
        for nom, typ, longueur, nullable, defaut, udt in cols:
            if udt == "vector":
                # information_schema ne rend pas la dimension : on la relit sur une ligne.
                with src.cursor() as cs:
                    cs.execute(f"SELECT vector_dims({nom}) FROM {t} "
                               f"WHERE {nom} IS NOT NULL LIMIT 1")
                    r = cs.fetchone()
                d = r[0] if r else 768
                sql = f"{nom} vector({d})"
            elif typ == "USER-DEFINED":
                sql = f"{nom} text"
            elif typ == "character varying" and longueur:
                sql = f"{nom} varchar({longueur})"
            elif typ == "ARRAY":
                sql = f"{nom} text[]"
            else:
                sql = f"{nom} {typ}"
            # Les séquences locales n'existent pas sur la destination : on recrée l'identité.
            if defaut and "nextval" in str(defaut):
                sql = f"{nom} serial" if typ == "integer" else f"{nom} bigserial"
            elif defaut and "now()" in str(defaut).lower():
                sql += " DEFAULT now()"
            morceaux.append(sql)

        with dst.cursor() as c:
            c.execute(f"CREATE TABLE IF NOT EXISTS {t} ({', '.join(morceaux)})")
        dst.commit()
        print(f"  {t:16} structure créée ({len(cols)} colonnes)")

    # Index de recherche vectorielle. Sans lui, chaque question du chat parcourt les 31 985
    # lignes : la réponse arrive quand même, mais après plusieurs secondes.
    with dst.cursor() as c:
        for t in ("cb_tarifs", "ef_indicateurs", "regl_documents"):
            try:
                c.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_vec ON {t} "
                          f"USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")
                dst.commit()
                print(f"  index vectoriel {t} : créé")
            except Exception as e:
                dst.rollback()
                print(f"  index vectoriel {t} : ignoré ({str(e)[:70]})")


# ── DONNÉES ──────────────────────────────────────────────────────────────────────────
def copier(src, dst, table, sans_vecteurs, depuis):
    cols = colonnes(src, table, sans_vecteurs)
    liste = ", ".join(cols)
    total = compter(src, table) or 0
    deja = compter(dst, table) or 0
    if deja >= total:
        print(f"  {table:16} déjà complète ({deja}/{total})")
        return deja

    # Reprise : on saute ce qui est passé. L'ordre par clé primaire rend la reprise fiable —
    # sans ORDER BY, deux exécutions ne voient pas forcément les lignes dans le même ordre et
    # le décompte ne veut plus rien dire.
    tri = "id" if "id" in cols else cols[0]
    depart = deja if depuis is None else depuis
    print(f"  {table:16} {total} lignes à copier, reprise à {depart}")

    ecrites, t0 = depart, time.time()
    with src.cursor(name=f"lecture_{table}") as cs:
        cs.itersize = LOT
        cs.execute(f"SELECT {liste} FROM {table} ORDER BY {tri} OFFSET {depart}")
        lot = []
        for ligne in cs:
            lot.append(ligne)
            if len(lot) >= LOT:
                ecrites += _ecrire(dst, table, cols, lot)
                lot = []
                fait = ecrites - depart
                reste = (total - ecrites)
                vitesse = fait / max(time.time() - t0, 0.1)
                print(f"    {ecrites}/{total}  ({vitesse:.0f} lignes/s, "
                      f"~{reste / max(vitesse, 0.1):.0f}s restantes)", end="\r")
        if lot:
            ecrites += _ecrire(dst, table, cols, lot)
    print(f"    {ecrites}/{total} — terminé{' ' * 30}")
    return ecrites


def _ecrire(dst, table, cols, lot):
    liste = ", ".join(cols)
    with dst.cursor() as c:
        psycopg2.extras.execute_values(
            c, f"INSERT INTO {table} ({liste}) VALUES %s ON CONFLICT DO NOTHING", lot,
            page_size=LOT)
    dst.commit()
    return len(lot)


def verifier(src, dst):
    print(f"\n  {'table':18} {'source':>10} {'destination':>13}   état")
    ok = True
    for t in TABLES:
        a, b = compter(src, t), compter(dst, t)
        etat = "identique" if a == b else ("MANQUE " + str((a or 0) - (b or 0)) if b is not None
                                          else "table absente")
        if a != b:
            ok = False
        print(f"  {t:18} {str(a):>10} {str(b):>13}   {etat}")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cible", default=os.getenv("DATABASE_URL_CIBLE"),
                    help="chaîne de connexion de destination")
    ap.add_argument("--structure", action="store_true", help="créer tables et index seulement")
    ap.add_argument("--verifier", action="store_true", help="comparer les décomptes, sans écrire")
    ap.add_argument("--sans-vecteurs", action="store_true",
                    help="ne pas copier les embeddings (~32 Mo au lieu de 310)")
    ap.add_argument("--table", help="ne traiter qu'une table")
    ap.add_argument("--depuis", type=int, help="forcer le point de reprise")
    a = ap.parse_args()

    if not a.cible:
        print("Destination inconnue. Renseignez DATABASE_URL_CIBLE dans .env, ou --cible.")
        print("Sur Supabase : Project Settings → Database → Connection string → Session pooler.")
        return 2

    print(f"\nSource      : {os.getenv('DB_NAME', 'intelligence_bancaire')}@"
          f"{os.getenv('DB_HOST', 'localhost')}")
    p = params(a.cible)
    print(f"Destination : {p['dbname']}@{p['host']}")

    src = source()
    dst = psycopg2.connect(**p)
    try:
        if a.verifier:
            return 0 if verifier(src, dst) else 1
        if a.structure:
            print("\nCréation de la structure :")
            creer_structure(src, dst)
            return 0
        print("\nCopie des données"
              + (" (sans les vecteurs)" if a.sans_vecteurs else "") + " :")
        for t in ([a.table] if a.table else TABLES):
            copier(src, dst, t, a.sans_vecteurs, a.depuis)
        print()
        verifier(src, dst)
    finally:
        src.close()
        dst.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
