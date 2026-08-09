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
import io
import os
import sys
import time
from urllib.parse import unquote, urlparse

import psycopg2
import psycopg2.extras

# La console Windows est en cp1252 : elle refuse les flèches et les tirets longs. Sans cette
# ligne, le script se tue sur ses PROPRES messages d'aide — y compris celui qui explique où
# trouver la chaîne de connexion, c'est-à-dire exactement quand on en a le plus besoin.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

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
    # LES EXTENSIONS SONT LUES SUR LA SOURCE, PAS ÉCRITES EN DUR (corrigé le 2026-08-09).
    # La première version ne créait que « vector », et la répétition sur une base d'essai a
    # montré ce qui manquait : « pg_trgm ». Sans lui, similarity() n'existe pas — et comme
    # db.query() avale l'erreur et rend une liste vide, les rapprochements de libellés
    # seraient revenus VIDES sans qu'aucun message ne le signale. Le tableau de bord aurait
    # affiché des comparaisons incomplètes, en production, sans erreur visible.
    with src.cursor() as cs:
        cs.execute("SELECT extname FROM pg_extension WHERE extname <> 'plpgsql' ORDER BY 1")
        extensions = [r[0] for r in cs.fetchall()]
    for e in extensions:
        try:
            with dst.cursor() as c:
                c.execute(f"CREATE EXTENSION IF NOT EXISTS {e}")
            dst.commit()
            print(f"  extension {e:12} prête")
        except Exception as err:
            dst.rollback()
            print(f"  extension {e:12} ÉCHEC — {str(err)[:90]}")
            print(f"     (à créer à la main sur l'hébergeur : CREATE EXTENSION {e};)")

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
            # TOUTES LES VALEURS PAR DÉFAUT SONT REPORTÉES (corrigé le 2026-08-09). La première
            # version ne traitait que « nextval » et « now() » : les sept autres — est_gratuit
            # false, is_header false, rang 1, is_primary true, succes true, role 'lecture',
            # actif true — étaient perdues. Conséquence constatée en ligne : le compte
            # d'administration créé au premier démarrage recevait actif = NULL au lieu de TRUE,
            # et la connexion était refusée sans que rien n'explique pourquoi. Une valeur par
            # défaut absente ne casse rien à la création de la table ; elle casse la première
            # écriture qui comptait sur elle, plus tard, ailleurs.
            if defaut and "nextval" in str(defaut):
                # Les séquences locales n'existent pas sur la destination : on recrée l'identité.
                sql = f"{nom} serial" if typ == "integer" else f"{nom} bigserial"
            elif defaut is not None:
                sql += f" DEFAULT {defaut}"
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
def copier(src, dst, table, sans_vecteurs, depuis, cible=None):
    cols = colonnes(src, table, sans_vecteurs)
    liste = ", ".join(cols)
    total = compter(src, table) or 0
    deja = compter(dst, table) or 0
    if deja >= total:
        print(f"  {table:16} déjà complète ({deja}/{total})")
        return deja, dst

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
        # Lots plus petits pour les tables porteuses de vecteurs : 768 nombres par ligne, le
        # pooler de l'hébergeur refuse les envois trop volumineux.
        pas = 100 if ("embedding" in cols and not sans_vecteurs) else LOT
        lot = []
        for ligne in cs:
            lot.append(ligne)
            if len(lot) >= pas:
                n, dst = _ecrire(dst, table, cols, lot, cible)
                ecrites += n
                lot = []
                fait = ecrites - depart
                reste = (total - ecrites)
                vitesse = fait / max(time.time() - t0, 0.1)
                print(f"    {ecrites}/{total}  ({vitesse:.0f} lignes/s, "
                      f"~{reste / max(vitesse, 0.1):.0f}s restantes)   ", end="\r")
        if lot:
            n, dst = _ecrire(dst, table, cols, lot, cible)
            ecrites += n
    print(f"    {ecrites}/{total} — terminé{' ' * 30}")
    return ecrites, dst


def _ecrire(dst, table, cols, lot, cible=None):
    """Écrit un lot, en se reconnectant si l'hébergeur a coupé la ligne.

    Supabase passe par un « pooler » qui ferme une connexion restée trop longtemps occupée ou
    ayant reçu une requête trop volumineuse — et une ligne de cb_tarifs porte un vecteur de 768
    nombres, ce qui pèse. Sans reprise, la migration s'arrêtait net au premier incident, après
    plusieurs minutes de transfert, et il fallait tout recommencer. On rouvre donc la connexion
    et on réessaie le même lot, en le coupant en deux à chaque échec : si 500 lignes passent
    mal, 250 passeront peut-être, et 125 sûrement.
    """
    liste = ", ".join(cols)

    def pousser(connexion, morceau):
        with connexion.cursor() as c:
            psycopg2.extras.execute_values(
                c, f"INSERT INTO {table} ({liste}) VALUES %s ON CONFLICT DO NOTHING",
                morceau, page_size=len(morceau))
        connexion.commit()

    taille = len(lot)
    for essai in range(5):
        try:
            for i in range(0, len(lot), taille):
                pousser(dst, lot[i:i + taille])
            return len(lot), dst
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            if cible is None:
                raise
            print(f"\n    ligne coupée ({str(e).strip()[:60]}) — reconnexion, "
                  f"lots de {max(taille // 2, 25)}")
            time.sleep(3)
            try:
                dst.close()
            except Exception:
                pass
            dst = psycopg2.connect(**params(cible))
            taille = max(taille // 2, 25)
    raise RuntimeError(f"échec répété sur {table} après reconnexions")


def verifier(src, dst):
    """Compare les décomptes ET les extensions.

    Compter les lignes ne suffit pas : la répétition sur une base d'essai a rendu « identique »
    sur les quatre tables alors que pg_trgm manquait, donc que similarity() n'existait pas et
    que des rapprochements revenaient vides. Une vérification qui dit « tout va bien » sur une
    base inutilisable est pire que pas de vérification du tout — elle donne confiance à tort.
    """
    print(f"\n  {'table':18} {'source':>10} {'destination':>13}   état")
    ok = True
    for t in TABLES:
        a, b = compter(src, t), compter(dst, t)
        etat = "identique" if a == b else ("MANQUE " + str((a or 0) - (b or 0)) if b is not None
                                          else "table absente")
        if a != b:
            ok = False
        print(f"  {t:18} {str(a):>10} {str(b):>13}   {etat}")

    def exts(cx):
        with cx.cursor() as c:
            c.execute("SELECT extname FROM pg_extension WHERE extname <> 'plpgsql'")
            return {r[0] for r in c.fetchall()}

    manquantes = exts(src) - exts(dst)
    print(f"\n  extensions source      : {', '.join(sorted(exts(src))) or 'aucune'}")
    print(f"  extensions destination : {', '.join(sorted(exts(dst))) or 'aucune'}")
    if manquantes:
        ok = False
        print(f"  MANQUANTES : {', '.join(sorted(manquantes))}")
        print("     À créer sur l'hébergeur, sans quoi certaines requêtes rendront des")
        print("     résultats vides SANS message d'erreur.")

    # Une extension présente peut rester inutilisable si elle n'est pas dans le search_path.
    # On l'éprouve donc pour de vrai, sur les deux fonctions dont l'application dépend.
    for sql, quoi in (("SELECT similarity('abc','abd')", "similarity() [pg_trgm]"),
                      ("SELECT '[1,0]'::vector <=> '[0,1]'::vector", "opérateur <=> [pgvector]")):
        try:
            with dst.cursor() as c:
                c.execute(sql)
                c.fetchone()
            print(f"  {quoi:26} utilisable")
        except Exception as e:
            dst.rollback()
            ok = False
            print(f"  {quoi:26} INUTILISABLE — {str(e)[:70]}")
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
            _, dst = copier(src, dst, t, a.sans_vecteurs, a.depuis, a.cible)
        print()
        verifier(src, dst)
    finally:
        src.close()
        dst.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
