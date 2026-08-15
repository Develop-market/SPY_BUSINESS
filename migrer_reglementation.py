"""Remplace le corpus reglementaire de l'hebergeur par celui de la base locale.

POURQUOI UN SCRIPT A PART. `migrer_vers_supabase.py` est REPRENABLE : il compte les lignes
deja presentes a destination et copie la suite. C'est ce qu'il faut quand on transporte une
table qui grandit — et c'est exactement ce qu'il ne faut pas ici. La distante contient
88 fragments decoupes par tranches de 500 mots ; la locale en contient 396 decoupes par
article. Ce ne sont pas les memes lignes : reprendre a la 89e melangerait les deux
decoupages, et `ON CONFLICT DO NOTHING` masquerait le probleme en silence.

On REMPLACE donc, en une transaction : on vide, on reecrit, on valide. Si quoi que ce soit
echoue, rien n'est ecrit et l'hebergeur garde son ancien corpus intact.

Les autres tables ne sont pas touchees : cb_tarifs et ef_indicateurs n'ont pas change.

USAGE
    python migrer_reglementation.py --verifier   compare les deux cotes, n'ecrit rien
    python migrer_reglementation.py              remplace

La destination est lue dans DATABASE_URL_CIBLE (.env), ou passee par --cible.
"""
import argparse

import os
import sys
import time

import psycopg2
import psycopg2.extras

# La console Windows est en cp1252 et refuse les tirets longs : le reglage est fait UNE FOIS,
# a l'import de migrer_vers_supabase plus bas. Le refaire ici emballait une seconde fois le
# meme flux, et le premier emballage, devenu inaccessible, fermait le tampon en disparaissant :
# le script mourait a l'arret sur « I/O operation on closed file », sans avoir rien affiche.
RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(RACINE, ".env"))
except Exception:
    pass

from migrer_vers_supabase import params, source          # noqa: E402  (apres load_dotenv)

LOT = 100    # un fragment porte un vecteur de 768 nombres : le pooler refuse les gros envois


def etat(cx, ou):
    with cx.cursor() as c:
        c.execute("SELECT count(*), count(embedding), count(DISTINCT fichier) FROM regl_documents")
        n, ne, nf = c.fetchone()
        c.execute("SELECT count(*) FROM regl_documents WHERE contenu ILIKE %s", ["%quatorze pour cent%"])
        usure = c.fetchone()[0]
        c.execute("SELECT count(*) FROM regl_documents WHERE contenu ILIKE %s",
                  ["%LISTE DES SERVICES BANCAIRES%"])
        gratuits = c.fetchone()[0]
    print(f"  {ou:14} {n:>5} fragments  {ne:>5} vectorises  {nf} documents"
          f"   usure:{usure}  liste des gratuits:{gratuits}")
    return n, ne, nf


def aptitudes(cx):
    """Éprouve, sur la destination, ce dont la recherche réglementaire dépend.

    Compter les lignes ne suffit pas. La recherche est hybride : un bras vectoriel et un bras
    lexical qui s'appuie sur le dictionnaire français de PostgreSQL. Si ce dictionnaire manque
    à l'hébergeur, le bras lexical tombe — l'application se replie alors sur le vectoriel
    seul, sans rien casser, mais elle perd ce qui a fait passer le MRR de 0,052 à 0,938. Mieux
    vaut le savoir ici, en une seconde, que le déduire de réponses médiocres dans un mois.
    """
    controles = [
        ("SELECT '[1,0]'::vector <=> '[0,1]'::vector", "opérateur <=> (pgvector)", True),
        ("SELECT to_tsvector('french', 'taux de l''usure')", "dictionnaire français", True),
        ("SELECT similarity('abc','abd')", "similarity() (pg_trgm)", False),
    ]
    tout_va = True
    for sql, quoi, indispensable in controles:
        try:
            with cx.cursor() as c:
                c.execute(sql)
                c.fetchone()
            print(f"  {quoi:28} utilisable")
        except Exception as e:
            cx.rollback()
            print(f"  {quoi:28} INDISPONIBLE — {str(e)[:60]}")
            if indispensable:
                tout_va = False
    return tout_va


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cible", default=os.getenv("DATABASE_URL_CIBLE"))
    ap.add_argument("--verifier", action="store_true")
    a = ap.parse_args()

    if not a.cible:
        print("\nDestination inconnue.")
        print("Ajoutez DATABASE_URL_CIBLE dans .env (le fichier est exclu de git), ou --cible.")
        print("Sur Supabase : Project Settings > Database > Connection string > Session pooler.")
        return 2

    src = source()
    dst = psycopg2.connect(**params(a.cible))
    try:
        print()
        n_src, ne_src, _ = etat(src, "locale")
        etat(dst, "hébergeur")

        if a.verifier:
            print()
            apte = aptitudes(dst)
            print("\n  (lecture seule)")
            return 0 if apte else 1

        if ne_src < n_src:
            print(f"\n  REFUS : {n_src - ne_src} fragments locaux n'ont pas de vecteur.")
            print("  Les copier rendrait ces articles introuvables en ligne.")
            return 1

        with src.cursor() as c:
            c.execute("""SELECT fichier, chunk_index, contenu, tokens_count, embedding
                         FROM regl_documents ORDER BY fichier, chunk_index""")
            lignes = c.fetchall()

        print(f"\n  remplacement de {len(lignes)} fragments...")
        t0 = time.time()
        # Une seule transaction : le vidage n'est definitif que si la reecriture aboutit.
        with dst.cursor() as c:
            c.execute("DELETE FROM regl_documents")
            for i in range(0, len(lignes), LOT):
                psycopg2.extras.execute_values(
                    c, """INSERT INTO regl_documents
                          (fichier, chunk_index, contenu, tokens_count, embedding) VALUES %s""",
                    lignes[i:i + LOT], page_size=LOT)
                print(f"    {min(i + LOT, len(lignes))}/{len(lignes)}   ", end="\r")
        dst.commit()
        print(f"    {len(lignes)}/{len(lignes)} — écrit en {time.time() - t0:.0f} s{' ' * 20}")

        # ── L'INDEX VECTORIEL APPROXIMATIF EST RETIRE DE CETTE TABLE ──────────────────
        # L'hebergeur portait un index ivfflat a 100 listes, avec ivfflat.probes = 1. Sur
        # 396 fragments, chaque liste en contient quatre : la recherche n'en examine qu'une,
        # soit 1 % du corpus, et rend cinq articles sans rapport. Verifie en direct — la
        # decision sur l'usure n'apparaissait pas dans les cinq premiers, alors qu'elle est
        # bien en base.
        #
        # Un index approximatif ne se justifie que lorsque parcourir tout coute cher. A 396
        # lignes, le parcours complet est immediat ET EXACT. On retire donc l'index plutot
        # que de le regler : moins de reglages, et le resultat cesse de dependre de la facon
        # dont les centroides sont tombes.
        #
        # En local la table portait un index HNSW, qui n'a pas ce defaut — c'est pourquoi les
        # mesures locales etaient excellentes et masquaient le probleme. Une verification en
        # production ne remplace pas une verification locale : elle en teste une autre.
        try:
            with dst.cursor() as c:
                c.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'regl_documents' "
                          "AND indexdef ILIKE '%ivfflat%'")
                for (nom,) in c.fetchall():
                    c.execute(f'DROP INDEX IF EXISTS "{nom}"')
                    print(f"  index approximatif {nom} retiré (parcours exact sur 396 lignes)")
            dst.commit()
        except Exception as e:
            dst.rollback()
            print(f"  index vectoriel : inchangé ({str(e)[:70]})")

        print()
        etat(src, "locale")
        n_dst, ne_dst, _ = etat(dst, "hébergeur")
        ok = (n_dst == n_src and ne_dst == ne_src)
        print(f"\n  {'identique' if ok else 'ÉCART — À REPRENDRE'}\n")
        ok = aptitudes(dst) and ok
        return 0 if ok else 1
    except Exception:
        dst.rollback()
        raise
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    sys.exit(main())
