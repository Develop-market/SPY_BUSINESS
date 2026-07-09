"""
run_repair_sections.py
======================
Repare les lignes SANS_SECTION sans re-extraction.
3 couches successives, reproducible, safe (UPDATE ciblé).

COUCHE A — Inversion OCR (SIB) : libelle = code section → swap
COUCHE B — Cross-bank libelle matching : token Jaccard vs banques reference
COUCHE C — Backward fill via window SQL : section du predecesseur immédiat

Apres chaque couche : rebuild contexte des lignes reparees.

Banques cibles : BICICI, SIB (+ SGCI si SS% > 5%)
Banques reference : BACI, BNI, ECOBANK, NSIA, SGCI
"""

import os, re, unicodedata, psycopg2
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[2]
load_dotenv(BASE / ".env")

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "intelligence_bancaire"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "")
)

LOG = BASE / "run_repair_sections.log"

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    safe = msg.encode("ascii", errors="replace").decode("ascii")
    try:
        print(f"[{ts}] {safe}", flush=True)
    except Exception:
        pass
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")

def get_conn():
    return psycopg2.connect(**DB)

# ─── Normalisation libelle ────────────────────────────────────────────────────

_STOP = {"de", "du", "des", "le", "la", "les", "et", "ou", "en", "au", "aux",
         "un", "une", "sur", "par", "pour", "a", "d", "l", "s", "n"}

def normalize(text: str) -> set:
    """Token set pour Jaccard : lowercase, sans accents, sans stopwords."""
    if not text:
        return set()
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    tokens = {w for w in t.split() if len(w) > 2 and w not in _STOP}
    return tokens

def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0

# ─── Build contexte helper ────────────────────────────────────────────────────

def _build_contexte(section: str, hmap: dict) -> str:
    """Reconstruit contexte depuis la hiérarchie des headers."""
    if not section:
        return ""
    parts = re.split(r"[.\-/]", section.rstrip("."))
    parts = [p for p in parts if p]
    # Ancêtres stricts
    ancestors = []
    for i in range(1, len(parts)):
        ancestor_key = ".".join(parts[:i])
        lbl = hmap.get(ancestor_key, "").strip()
        if lbl:
            ancestors.append(lbl)
    if ancestors:
        return " | ".join(ancestors)
    # Longest prefix match
    sec = section.rstrip(".")
    best, best_len = "", 0
    for k, v in hmap.items():
        if sec.startswith(k) and len(k) > best_len:
            best = v.strip()
            best_len = len(k)
    if best:
        return best
    # Top level fallback
    top = parts[0] if parts else ""
    lbl = hmap.get(top, "").strip()
    return lbl if lbl else section  # section code as last resort

def rebuild_contexte_for_ids(cur, ids: list, banque: str, annee: int,
                              semestre: str, segment: str) -> int:
    """Reconstruit le contexte pour les IDs donnés en utilisant la hmap locale."""
    if not ids:
        return 0
    # Build hmap from is_header rows for this tranche
    cur.execute("""
        SELECT section, libelle FROM cb_tarifs
        WHERE banque=%s AND annee=%s AND semestre=%s AND segment=%s
          AND is_header AND section IS NOT NULL AND section!=''
    """, (banque, annee, semestre, segment))
    hmap = {}
    for sec, lib in cur.fetchall():
        if sec and lib:
            hmap[sec.strip().rstrip(".")] = lib.strip()

    updated = 0
    for row_id in ids:
        cur.execute("SELECT section FROM cb_tarifs WHERE id=%s", (row_id,))
        r = cur.fetchone()
        if not r or not r[0]:
            continue
        ctx = _build_contexte(r[0], hmap)
        if ctx:
            cur.execute("UPDATE cb_tarifs SET contexte=%s WHERE id=%s", (ctx, row_id))
            updated += 1
    return updated

# ══════════════════════════════════════════════════════════════════════════════
# COUCHE A — SIB : libelle = code section (inversion OCR)
# ══════════════════════════════════════════════════════════════════════════════

def couche_a_sib_section_as_libelle(conn) -> int:
    log("\n[A] Inversion OCR SIB : libelle = code section")
    cur = conn.cursor()

    # Pattern : chiffres et points uniquement (ex: "2.2.3.112", "8.1.1")
    cur.execute(r"""
        SELECT id, libelle, banque, annee, semestre, segment
        FROM cb_tarifs
        WHERE banque = 'SIB'
          AND NOT is_header
          AND (section IS NULL OR section = '')
          AND libelle ~ '^[0-9]+(\.[0-9]+)*\.?$'
    """)
    rows = cur.fetchall()
    log(f"  Candidats trouves : {len(rows)}")

    ids_repared = []
    for row_id, lib, banque, annee, semestre, segment in rows:
        section_code = lib.rstrip(".")
        cur.execute(
            "UPDATE cb_tarifs SET section=%s WHERE id=%s",
            (section_code, row_id)
        )
        ids_repared.append((row_id, banque, annee, semestre, segment))
        log(f"  [A] id={row_id} : section={section_code} (depuis libelle)")

    # Rebuild contexte
    ctx_updated = 0
    # Group by tranche
    tranches = {}
    for row_id, banque, annee, semestre, segment in ids_repared:
        key = (banque, annee, semestre, segment)
        tranches.setdefault(key, []).append(row_id)
    for (banque, annee, semestre, segment), ids in tranches.items():
        ctx_updated += rebuild_contexte_for_ids(cur, ids, banque, annee, semestre, segment)

    conn.commit()
    log(f"  [A] {len(ids_repared)} sections reparees, {ctx_updated} contextes mis a jour")
    return len(ids_repared)

# ══════════════════════════════════════════════════════════════════════════════
# COUCHE B — Cross-bank libelle matching (token Jaccard)
# ══════════════════════════════════════════════════════════════════════════════

REFERENCE_BANKS = ("BACI", "BNI", "ECOBANK", "NSIA", "SGCI")
TARGET_BANKS    = ("BICICI", "SIB", "SGCI")
JACCARD_THRESHOLD = 0.40

def couche_b_crossbank_matching(conn) -> int:
    log(f"\n[B] Cross-bank libelle matching (Jaccard >= {JACCARD_THRESHOLD})")
    cur = conn.cursor()

    # 1. Construire la reference : (libelle_tokens, section) depuis banques reference
    log("  Chargement reference...")
    cur.execute("""
        SELECT libelle, section FROM cb_tarifs
        WHERE banque = ANY(%s)
          AND NOT is_header
          AND section IS NOT NULL AND section != ''
          AND libelle IS NOT NULL AND libelle != ''
    """, (list(REFERENCE_BANKS),))
    ref_rows = cur.fetchall()
    log(f"  {len(ref_rows)} lignes de reference chargees")

    # Deduplique : (tokens_frozenset -> section le plus frequent)
    from collections import Counter
    token_to_sections: dict = {}  # token_key -> Counter(section)
    ref_list = []  # [(tokens_set, section)]
    for lib, sec in ref_rows:
        toks = frozenset(normalize(lib))
        if not toks:
            continue
        token_to_sections.setdefault(toks, Counter())[sec] += 1
        ref_list.append((toks, sec))

    # Consolider : pour chaque token key, prendre la section majoritaire
    ref_consolidated = []
    for toks, counter in token_to_sections.items():
        best_sec = counter.most_common(1)[0][0]
        ref_consolidated.append((toks, best_sec))
    log(f"  {len(ref_consolidated)} libelles reference uniques")

    # 2. Charger les lignes cibles sans section
    cur.execute("""
        SELECT id, libelle, banque, annee, semestre, segment
        FROM cb_tarifs
        WHERE banque = ANY(%s)
          AND NOT is_header
          AND (section IS NULL OR section = '')
          AND libelle IS NOT NULL AND libelle != ''
    """, (list(TARGET_BANKS),))
    targets = cur.fetchall()
    log(f"  {len(targets)} lignes cibles sans section")

    # 3. Matching
    n_matched = 0
    ids_per_tranche: dict = {}

    for row_id, lib, banque, annee, semestre, segment in targets:
        toks = normalize(lib)
        if not toks or len(toks) < 2:
            continue  # trop court pour matcher fiablement

        best_score = 0.0
        best_sec   = None
        for ref_toks, ref_sec in ref_consolidated:
            score = jaccard(toks, ref_toks)
            if score > best_score:
                best_score = score
                best_sec   = ref_sec

        if best_score >= JACCARD_THRESHOLD and best_sec:
            cur.execute(
                "UPDATE cb_tarifs SET section=%s WHERE id=%s",
                (best_sec, row_id)
            )
            key = (banque, annee, semestre, segment)
            ids_per_tranche.setdefault(key, []).append(row_id)
            n_matched += 1
            log(f"  [B] id={row_id} {banque} : '{lib[:40]}' -> sec={best_sec} (J={best_score:.2f})")

    # Rebuild contexte
    ctx_total = 0
    for (banque, annee, semestre, segment), ids in ids_per_tranche.items():
        ctx_total += rebuild_contexte_for_ids(cur, ids, banque, annee, semestre, segment)

    conn.commit()
    log(f"  [B] {n_matched} sections assignees par cross-bank, {ctx_total} contextes mis a jour")
    return n_matched

# ══════════════════════════════════════════════════════════════════════════════
# COUCHE C — Backward fill via SQL window function
# ══════════════════════════════════════════════════════════════════════════════

def couche_c_backward_fill(conn) -> int:
    log("\n[C] Backward fill (section du predecesseur dans meme tranche)")
    cur = conn.cursor()

    # Utiliser LAG() pour trouver la derniere section connue dans la meme tranche
    # On fait plusieurs passes pour propager sur des runs de NULL consecutifs
    total = 0

    for banque in ("BICICI", "SIB", "SGCI"):
        for _pass in range(5):  # max 5 passes pour propager les runs
            cur.execute("""
                WITH ordered AS (
                    SELECT id,
                           section,
                           is_header,
                           LAG(section, 1) OVER w AS prev1,
                           LAG(section, 2) OVER w AS prev2,
                           LAG(section, 3) OVER w AS prev3
                    FROM cb_tarifs
                    WHERE banque = %s
                    WINDOW w AS (PARTITION BY banque, annee, semestre, segment ORDER BY id)
                )
                UPDATE cb_tarifs
                SET section = COALESCE(o.prev1, o.prev2, o.prev3)
                FROM ordered o
                WHERE cb_tarifs.id = o.id
                  AND NOT cb_tarifs.is_header
                  AND (cb_tarifs.section IS NULL OR cb_tarifs.section = '')
                  AND COALESCE(o.prev1, o.prev2, o.prev3) IS NOT NULL
                  AND COALESCE(o.prev1, o.prev2, o.prev3) != ''
            """, (banque,))
            n = cur.rowcount
            conn.commit()
            if n == 0:
                break
            log(f"  [C] {banque} passe {_pass+1}: {n} lignes reparees")
            total += n

    # Rebuild contexte pour toutes les lignes desormais sectionnees (les nouvelles)
    cur.execute("""
        SELECT id, banque, annee, semestre, segment
        FROM cb_tarifs
        WHERE banque = ANY(%s)
          AND NOT is_header
          AND section IS NOT NULL AND section != ''
          AND (contexte IS NULL OR contexte = '')
    """, (["BICICI", "SIB", "SGCI"],))
    no_ctx = cur.fetchall()
    log(f"  {len(no_ctx)} lignes avec section mais sans contexte -> rebuild")

    # Group by tranche et rebuild
    tranches: dict = {}
    for row_id, banque, annee, semestre, segment in no_ctx:
        tranches.setdefault((banque, annee, semestre, segment), []).append(row_id)
    ctx_total = 0
    for (banque, annee, semestre, segment), ids in tranches.items():
        ctx_total += rebuild_contexte_for_ids(cur, ids, banque, annee, semestre, segment)
    conn.commit()
    log(f"  [C] {total} sections par backward fill, {ctx_total} contextes mis a jour")
    return total

# ══════════════════════════════════════════════════════════════════════════════
# AUDIT FINAL
# ══════════════════════════════════════════════════════════════════════════════

def audit_final(conn):
    log("\n" + "=" * 65)
    log("  AUDIT FINAL — SS% et SC% par banque")
    log("=" * 65)
    cur = conn.cursor()
    cur.execute("""
        SELECT banque,
          SUM(CASE WHEN NOT is_header AND (section IS NULL OR section='') THEN 1 ELSE 0 END) ss,
          SUM(CASE WHEN NOT is_header AND (contexte IS NULL OR contexte='') THEN 1 ELSE 0 END) sc,
          SUM(CASE WHEN NOT is_header THEN 1 ELSE 0 END) nh
        FROM cb_tarifs GROUP BY banque ORDER BY banque
    """)
    log(f"  {'BANQUE':8} {'SS':5} {'SC':5} {'NH':5}  {'SS%':6}  {'SC%':6}  VERDICT")
    log("  " + "-" * 55)
    for b, ss, sc, nh in cur.fetchall():
        if not nh:
            continue
        ss_p = ss / nh * 100
        sc_p = sc / nh * 100
        ok = ss_p < 5 and sc_p < 8
        verdict = "OK" if ok else ("SS !" if ss_p >= 5 else "SC !")
        log(f"  {b:8} {ss:5} {sc:5} {nh:5}  {ss_p:5.1f}%  {sc_p:5.1f}%  {verdict}")
    conn.close()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import time
    t0 = time.time()
    log("=" * 65)
    log("  RUN_REPAIR_SECTIONS — 3 couches sans re-extraction")
    log("=" * 65)

    conn = get_conn()

    # Ordre intentionnel :
    #   A d'abord : SIB codes evidents (exact, pas de conflit possible)
    #   C avant B : backward fill utilise les codes natifs de chaque banque
    #               cross-bank (B) seulement pour ce qui reste (orphelins sans predecesseur)
    n_a = couche_a_sib_section_as_libelle(conn)
    n_c = couche_c_backward_fill(conn)
    n_b = couche_b_crossbank_matching(conn)

    log(f"\n  TOTAL reparees : A={n_a} + C={n_c} + B={n_b} = {n_a+n_c+n_b}")
    log(f"  Duree : {(time.time()-t0):.1f}s")

    audit_final(conn)
    log(f"\n  Log : {LOG}")
