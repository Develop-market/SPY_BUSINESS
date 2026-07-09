"""
run_vectorisation.py — Calcul des embeddings locaux
=====================================================
Modèle : sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (768 dims)
Tables  : cb_tarifs | ef_indicateurs | regl_documents

Usage :
  python run_vectorisation.py          # tout vectoriser
  python run_vectorisation.py --cb     # CB seulement
  python run_vectorisation.py --ef     # EF seulement
  python run_vectorisation.py --regl   # REGL seulement
  python run_vectorisation.py --reset  # re-vectoriser même les déjà faits
"""

import sys, os, argparse
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE / ".env")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg2
from psycopg2.extras import execute_values

DB_PARAMS = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME",     "intelligence_bancaire"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
BATCH_SIZE = 64


def get_conn():
    return psycopg2.connect(**DB_PARAMS)


def load_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("[INSTALL] pip install sentence-transformers")
        sys.exit(1)
    print(f"  Chargement modèle {MODEL_NAME} …", end=" ", flush=True)
    model = SentenceTransformer(MODEL_NAME)
    print("OK")
    return model


def _batch_embed(model, texts: list[str]) -> list:
    """Retourne une liste de listes Python (pas numpy) pour psycopg2."""
    vecs = model.encode(texts, batch_size=BATCH_SIZE, show_progress_bar=False,
                        normalize_embeddings=True)
    return [v.tolist() for v in vecs]


# ── CB ────────────────────────────────────────────────────────────────────────────
def vectorise_cb(conn, model, reset: bool = False):
    print("\n  [CB] Vectorisation cb_tarifs …")

    where = "" if reset else "WHERE embedding IS NULL"
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, banque, annee, semestre, segment, section, contexte, libelle, valeur_propre
            FROM cb_tarifs
            {where}
            ORDER BY id
        """)
        rows = cur.fetchall()

    if not rows:
        print("  [CB] Rien à vectoriser.")
        return

    print(f"  [CB] {len(rows)} lignes à traiter …")
    ids, texts = [], []
    for r in rows:
        rid, banque, annee, sem, seg, section, contexte, libelle, valeur_propre = r
        # Texte riche pour le RAG : contexte + libellé + valeur
        parts = [
            f"[BANQUE:{banque}] [{annee} {sem} {seg}]",
            f"Section: {section or ''}",
            f"Contexte: {contexte or ''}",
            f"Service: {libelle or ''}",
            f"Valeur: {valeur_propre or ''}",
        ]
        texts.append(" | ".join(p for p in parts if p.split(': ', 1)[-1].strip()))
        ids.append(rid)

    updated = 0
    for i in range(0, len(ids), BATCH_SIZE):
        batch_ids   = ids[i:i+BATCH_SIZE]
        batch_texts = texts[i:i+BATCH_SIZE]
        vecs = _batch_embed(model, batch_texts)
        with conn.cursor() as cur:
            for rid, vec in zip(batch_ids, vecs):
                cur.execute(
                    "UPDATE cb_tarifs SET embedding = %s::vector WHERE id = %s",
                    (vec, rid)
                )
        conn.commit()
        updated += len(batch_ids)
        pct = updated / len(ids) * 100
        print(f"    {updated}/{len(ids)} ({pct:.1f}%) …", end="\r", flush=True)

    print(f"\n  [CB] {updated} embeddings calculés.          ")


# ── EF ────────────────────────────────────────────────────────────────────────────
def vectorise_ef(conn, model, reset: bool = False):
    print("\n  [EF] Vectorisation ef_indicateurs …")

    where = "" if reset else "WHERE embedding IS NULL"
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, banque, libelle, annee_label, valeur_propre, unite
            FROM ef_indicateurs
            {where}
            ORDER BY id
        """)
        rows = cur.fetchall()

    if not rows:
        print("  [EF] Rien à vectoriser.")
        return

    print(f"  [EF] {len(rows)} lignes à traiter …")
    ids, texts = [], []
    for r in rows:
        rid, banque, libelle, annee_label, valeur_propre, unite = r
        parts = [
            f"[BANQUE:{banque}] [{annee_label}]",
            f"Indicateur: {libelle or ''}",
            f"Valeur: {valeur_propre or ''} {unite or ''}",
        ]
        texts.append(" | ".join(p for p in parts if p.split(': ', 1)[-1].strip()))
        ids.append(rid)

    updated = 0
    for i in range(0, len(ids), BATCH_SIZE):
        batch_ids   = ids[i:i+BATCH_SIZE]
        batch_texts = texts[i:i+BATCH_SIZE]
        vecs = _batch_embed(model, batch_texts)
        with conn.cursor() as cur:
            for rid, vec in zip(batch_ids, vecs):
                cur.execute(
                    "UPDATE ef_indicateurs SET embedding = %s::vector WHERE id = %s",
                    (vec, rid)
                )
        conn.commit()
        updated += len(batch_ids)
        pct = updated / len(ids) * 100
        print(f"    {updated}/{len(ids)} ({pct:.1f}%) …", end="\r", flush=True)

    print(f"\n  [EF] {updated} embeddings calculés.          ")


# ── REGL ──────────────────────────────────────────────────────────────────────────
def vectorise_regl(conn, model, reset: bool = False):
    print("\n  [REGL] Vectorisation regl_documents …")

    where = "" if reset else "WHERE embedding IS NULL"
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, fichier, contenu
            FROM regl_documents
            {where}
            ORDER BY id
        """)
        rows = cur.fetchall()

    if not rows:
        print("  [REGL] Rien à vectoriser.")
        return

    print(f"  [REGL] {len(rows)} chunks à traiter …")
    ids, texts = [], []
    for rid, fichier, contenu in rows:
        texts.append(f"[DOC:{fichier}] {contenu or ''}")
        ids.append(rid)

    updated = 0
    for i in range(0, len(ids), BATCH_SIZE):
        batch_ids   = ids[i:i+BATCH_SIZE]
        batch_texts = texts[i:i+BATCH_SIZE]
        vecs = _batch_embed(model, batch_texts)
        with conn.cursor() as cur:
            for rid, vec in zip(batch_ids, vecs):
                cur.execute(
                    "UPDATE regl_documents SET embedding = %s::vector WHERE id = %s",
                    (vec, rid)
                )
        conn.commit()
        updated += len(batch_ids)
        pct = updated / len(ids) * 100
        print(f"    {updated}/{len(ids)} ({pct:.1f}%) …", end="\r", flush=True)

    print(f"\n  [REGL] {updated} embeddings calculés.          ")


# ── Main ──────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cb",    action="store_true")
    parser.add_argument("--ef",    action="store_true")
    parser.add_argument("--regl",  action="store_true")
    parser.add_argument("--reset", action="store_true",
                        help="Re-vectoriser même les lignes déjà embedées")
    args = parser.parse_args()

    do_all  = not (args.cb or args.ef or args.regl)
    do_cb   = args.cb   or do_all
    do_ef   = args.ef   or do_all
    do_regl = args.regl or do_all

    print("=" * 60)
    print("  VECTORISATION — paraphrase-multilingual-mpnet-base-v2")
    print("=" * 60)

    model = load_model()
    conn  = psycopg2.connect(**DB_PARAMS)

    try:
        if do_cb:
            vectorise_cb(conn, model, reset=args.reset)
        if do_ef:
            vectorise_ef(conn, model, reset=args.reset)
        if do_regl:
            vectorise_regl(conn, model, reset=args.reset)
    finally:
        conn.close()

    print("\n  Vectorisation terminée.")


if __name__ == "__main__":
    main()
