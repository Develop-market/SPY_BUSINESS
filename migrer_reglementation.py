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
            print("\n  (lecture seule)")
            return 0

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

        print()
        etat(src, "locale")
        n_dst, ne_dst, _ = etat(dst, "hébergeur")
        ok = (n_dst == n_src and ne_dst == ne_src)
        print(f"\n  {'identique' if ok else 'ÉCART — À REPRENDRE'}")
        return 0 if ok else 1
    except Exception:
        dst.rollback()
        raise
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    sys.exit(main())
