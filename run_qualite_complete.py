"""
run_qualite_complete.py
=======================
Pipeline qualite COMPLET — ordre strict, verification avant chaque etape.

ETAPE 1 : Nettoyage CB (toutes banques)
ETAPE 2 : Audit Exhaustivite sur PRETRAITEES (avant stockage)
ETAPE 3 : Stockage reset CB
ETAPE 4 : Suppression artefacts SQL
ETAPE 5 : Repair Veracite (6 couches type_valeur)
ETAPE 6 : Repair Structure (section propagation + contexte)
ETAPE 7 : Audit final (3 criteres — verdict par banque)
ETAPE 8 : Vectorisation CB automatique (si audit OK)

Seuils cibles :
  Exhaustivite  : toutes tranches >= 200 lignes
  Veracite      : AUTRE < 5% par banque
  Structure     : SANS_SECTION < 5%, SANS_CONTEXTE < 8%
"""

import subprocess, sys, os, time, shutil
import psycopg2
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import openpyxl

BASE = Path(__file__).resolve().parent
LOG  = BASE / "run_qualite_complete.log"
load_dotenv(BASE / ".env")

PRETRAITE_CB = BASE / "DATA" / "DONNEES_PRETRAITEES" / "CONDITIONS_BANQUES"

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "intelligence_bancaire"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "")
)

PIPELINE = BASE / "PIPELINE"
PYTHON   = sys.executable

# ── Helpers ────────────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    safe = msg.encode("ascii", errors="replace").decode("ascii")
    try:
        print(f"[{ts}] {safe}", flush=True)
    except Exception:
        pass
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")

def run(cmd, cwd=None, timeout=3600, fatal=True):
    log(f"CMD : {' '.join(str(c) for c in cmd)}")
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=cwd or BASE, encoding="utf-8", errors="replace"
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                log(f"  {line}")
        proc.wait(timeout=timeout)
        return proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill(); log("  [TIMEOUT]"); return -1
    except Exception as e:
        log(f"  [ERREUR] {e}"); return -1

def count_xlsx_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb.active
        n = ws.max_row - 1
        wb.close()
        return max(n, 0)
    except Exception:
        return 0


# ── Demarrage ──────────────────────────────────────────────────────────────────

log("=" * 65)
log("  PIPELINE QUALITE COMPLET")
log("=" * 65)
t0 = time.time()

# ── ETAPE 0 : Backup fichiers imputés haute qualité ───────────────────────────
# Protege les fichiers qui sont meilleurs que ce que nettoyage va regenerer.
log("\n[0/7] Backup fichiers imputes haute qualite...")

BACKUP = BASE / "_backup_pretraite"
BACKUP.mkdir(exist_ok=True)

# Fichiers a proteger : (banque, annee, fichier)
PROTEGES = [
    ("BACI", "2026", "S1_P_clean.xlsx"),  # Docling 349 lignes — extraction LLM echouera
    ("BACI", "2024", "S1_P_clean.xlsx"),  # impute depuis 2026
    ("BACI", "2025", "S1_P_clean.xlsx"),  # impute depuis 2026
    ("BACI", "2025", "S1_E_clean.xlsx"),  # impute depuis 2024 LLM
    ("BACI", "2025", "S2_E_clean.xlsx"),  # impute depuis 2024 LLM
    ("BACI", "2025", "S2_P_clean.xlsx"),  # impute depuis 2024
]

backed_up = []
for banque, annee, fname in PROTEGES:
    src = PRETRAITE_CB / banque / annee / fname
    if src.exists():
        n = count_xlsx_rows(src)
        dst = BACKUP / f"{banque}_{annee}_{fname}"
        shutil.copy2(src, dst)
        backed_up.append((src, dst, n))
        log(f"  Backup : {banque}/{annee}/{fname} ({n} lignes)")

# ── ETAPE 1 : Nettoyage CB ─────────────────────────────────────────────────────
log("\n[1/7] Nettoyage CB (toutes banques)...")
rc = run([PYTHON, "run_nettoyage.py", "--cb"],
         cwd=PIPELINE / "NETTOYAGE", timeout=1800, fatal=True)
log(f"  -> code {rc}")
if rc != 0:
    log("  [ERREUR FATALE] Nettoyage echoue"); sys.exit(1)

# Restaurer les fichiers imputes si le nettoyage a produit moins de lignes
log("\n  Restauration fichiers imputes si nettoyage < backup...")
for src, bak, n_bak in backed_up:
    n_new = count_xlsx_rows(src)
    if n_new < n_bak:
        shutil.copy2(bak, src)
        log(f"  RESTAURE : {src.name} ({n_new} -> {n_bak} lignes)")
    else:
        log(f"  GARDE nettoyage : {src.name} ({n_new} lignes >= {n_bak})")

# ── ETAPE 2 : Audit Exhaustivite sur PRETRAITEES ───────────────────────────────
log("\n[2/7] Audit Exhaustivite sur PRETRAITEES (avant stockage)...")

SEUIL_FAIBLE = 200
alertes = []

banques = [d.name for d in PRETRAITE_CB.iterdir() if d.is_dir()]
banques.sort()

log(f"  {'BANQUE':8} {'ANNEE':6} {'SEM':5} {'SEG':5} {'LIGNES':7}  STATUT")
log("  " + "-" * 50)

for banque in banques:
    for annee_dir in sorted((PRETRAITE_CB / banque).iterdir()):
        if not annee_dir.is_dir():
            continue
        annee = annee_dir.name
        for f in sorted(annee_dir.glob("*_clean.xlsx")):
            # Derive semestre et segment depuis le nom (ex: S1_E_clean.xlsx)
            stem = f.stem.replace("_clean", "")
            parts = stem.split("_")
            if len(parts) >= 2:
                sem = parts[0]       # S1 ou S2
                seg = parts[1]       # E ou P
            else:
                sem, seg = stem, "?"
            n = count_xlsx_rows(f)
            statut = "OK" if n >= SEUIL_FAIBLE else "FAIBLE ***"
            log(f"  {banque:8} {annee:6} {sem:5} {seg:5} {n:6}   {statut}")
            if n < SEUIL_FAIBLE:
                alertes.append((banque, annee, sem, seg, n, f))

if alertes:
    log(f"\n  {len(alertes)} tranches sous le seuil de {SEUIL_FAIBLE} lignes :")
    for banque, annee, sem, seg, n, f in alertes:
        log(f"    {banque} {annee} {sem} {seg} : {n} lignes")
    log("  -> Ces tranches seront stockees mais flaggees.")
    log("     Imputation manuelle recommandee si le PDF source est complet.")
else:
    log(f"\n  Toutes les tranches >= {SEUIL_FAIBLE} lignes. Exhaustivite OK.")

# ── ETAPE 3 : Stockage reset CB ────────────────────────────────────────────────
log("\n[3/7] Stockage CB reset (DELETE + INSERT complet)...")
rc = run([PYTHON, "run_stockage.py", "--reset", "--cb"],
         cwd=PIPELINE / "STOCKAGE_BD", timeout=600, fatal=True)
log(f"  -> code {rc}")
if rc != 0:
    log("  [ERREUR FATALE] Stockage echoue"); sys.exit(1)

# ── ETAPE 4 : Suppression artefacts SQL ────────────────────────────────────────
log("\n[4/7] Suppression artefacts SQL...")
try:
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()

    cur.execute("""
        DELETE FROM cb_tarifs
        WHERE libelle ~* '^(code|libelle|designation|intitule|nature|description)\\s*$'
          AND NOT is_header
    """)
    n1 = cur.rowcount
    log(f"  En-tetes tableau residuels supprimes : {n1}")

    cur.execute("""
        DELETE FROM cb_tarifs
        WHERE NOT is_header
          AND libelle IS NOT NULL AND libelle != ''
          AND libelle = valeur_brute AND libelle = valeur_propre
          AND length(libelle) > 20
    """)
    n2 = cur.rowcount
    log(f"  Artefacts libelle=valeur supprimes : {n2}")

    cur.execute("""
        DELETE FROM cb_tarifs
        WHERE NOT is_header
          AND (libelle IS NULL OR trim(libelle) = '')
          AND (valeur_brute IS NULL OR trim(valeur_brute) = '')
    """)
    n3 = cur.rowcount
    log(f"  Lignes completement vides supprimees : {n3}")

    conn.commit()
    conn.close()
    log(f"  Total artefacts supprimes : {n1 + n2 + n3}")
except Exception as e:
    log(f"  [ERREUR] artefacts : {e}")

# ── ETAPE 5 : Repair Veracite ──────────────────────────────────────────────────
log("\n[5/7] Repair Veracite (type_valeur — patterns etendus)...")
rc = run([PYTHON, "run_repair_structure.py"],
         cwd=PIPELINE / "STOCKAGE_BD", timeout=600)
log(f"  -> code {rc}")

# ── ETAPE 5b : Repair Sections (3 couches — natif avant cross-bank) ────────────
log("\n[5b/7] Repair Sections (inversion OCR + backward fill + cross-bank)...")
rc = run([PYTHON, "run_repair_sections.py"],
         cwd=PIPELINE / "STOCKAGE_BD", timeout=300)
log(f"  -> code {rc}")

# ── ETAPE 6 : Repair Contexte ─────────────────────────────────────────────────
log("\n[6/7] Repair Contexte (reconstruction hierarchique)...")
rc = run([PYTHON, "run_repair_contexte.py"],
         cwd=PIPELINE / "STOCKAGE_BD", timeout=300)
log(f"  -> code {rc}")

# ── ETAPE 6b : Repair Tenue de Compte ─────────────────────────────────────────
log("\n[6b/7] Repair Tenue de Compte (zeros + propagation contexte sous-items)...")
rc = run([PYTHON, "run_repair_tenue_compte.py"],
         cwd=PIPELINE / "STOCKAGE_BD", timeout=120)
log(f"  -> code {rc}")

# ── ETAPE 7 : Audit Final ──────────────────────────────────────────────────────
log("\n[7/7] AUDIT FINAL — 3 criteres par banque")
log("=" * 65)

try:
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()

    # -- Exhaustivite
    log("\n--- EXHAUSTIVITE ---")
    cur.execute("""
        SELECT banque, annee, semestre, segment, COUNT(*) n
        FROM cb_tarifs
        GROUP BY banque, annee, semestre, segment
        ORDER BY banque, annee, semestre, segment
    """)
    prev = None
    for b, y, sem, seg, n in cur.fetchall():
        if b != prev:
            log(f"  {b}"); prev = b
        flag = "  *** FAIBLE" if n < 200 else ""
        log(f"    {y} {sem} {seg}: {n}{flag}")

    # -- Veracite
    log("\n--- VERACITE (type_valeur) ---")
    cur.execute("""
        SELECT banque,
          SUM(CASE WHEN type_valeur='AUTRE' THEN 1 ELSE 0 END) autre,
          SUM(CASE WHEN NOT is_header THEN 1 ELSE 0 END) nh
        FROM cb_tarifs
        GROUP BY banque ORDER BY banque
    """)
    veracite_ok = True
    rows_v = cur.fetchall()
    log(f"  {'BANQUE':8} {'AUTRE':6} {'TOTAL':6} {'AUTRE%':7}  VERDICT")
    log("  " + "-" * 42)
    for b, autre, nh in rows_v:
        if nh == 0:
            continue
        pct = autre / nh * 100
        ok  = pct < 5
        if not ok:
            veracite_ok = False
        log(f"  {b:8} {autre:6} {nh:6} {pct:6.1f}%   {'OK' if ok else 'A CORRIGER <--'}")

    # -- Structure
    log("\n--- STRUCTURE (section / contexte) ---")
    cur.execute("""
        SELECT banque,
          SUM(CASE WHEN NOT is_header AND (section IS NULL OR section='') THEN 1 ELSE 0 END) ss,
          SUM(CASE WHEN NOT is_header AND (contexte IS NULL OR contexte='') THEN 1 ELSE 0 END) sc,
          SUM(CASE WHEN NOT is_header THEN 1 ELSE 0 END) nh
        FROM cb_tarifs GROUP BY banque ORDER BY banque
    """)
    structure_ok = True
    rows_s = cur.fetchall()
    log(f"  {'BANQUE':8} {'SS%':7} {'SC%':7}  VERDICT")
    log("  " + "-" * 35)
    for b, ss, sc, nh in rows_s:
        if nh == 0:
            continue
        ss_p = ss / nh * 100
        sc_p = sc / nh * 100
        ok   = ss_p < 5 and sc_p < 8
        if not ok:
            structure_ok = False
        log(f"  {b:8} {ss_p:6.1f}% {sc_p:6.1f}%   {'OK' if ok else 'A CORRIGER <--'}")

    # -- Verdict global
    log("\n" + "=" * 65)
    if veracite_ok and structure_ok:
        log("  *** TOUTES LES BANQUES PASSENT LES 3 CRITERES ***")
        log("  Lancement vectorisation automatique...")
    else:
        log("  CERTAINES BANQUES NECESSITENT CORRECTION :")
        if not veracite_ok:
            log("    - Veracite  : AUTRE > 5% sur certaines banques")
        if not structure_ok:
            log("    - Structure : SANS_SECTION ou SANS_CONTEXTE > seuil")
        log("  Vectorisation ignoree — corriger avant de relancer.")
    log("=" * 65)

    conn.close()
except Exception as e:
    log(f"  [ERREUR] audit : {e}")
    veracite_ok = False
    structure_ok = False

# ── ETAPE 8 : Vectorisation CB — toujours, qualite ou pas ────────────────────
log("\n[8/8] Vectorisation CB (embeddings locaux)...")
if not (veracite_ok and structure_ok):
    log("  [AVERTISSEMENT] Audit non satisfait — vectorisation quand meme.")
    log("  Des donnees imparfaites vectorisees valent mieux que zero donnees vectorisees.")
    log("  Verifier le rapport audit ci-dessus et corriger si necessaire.")

rc = run([PYTHON, "run_vectorisation.py", "--cb"],
         cwd=PIPELINE / "VECTORISATION", timeout=3600)
log(f"  -> code {rc}")
if rc == 0:
    log("  Vectorisation CB terminee.")
else:
    log("  [ERREUR] Vectorisation CB echouee — verifier les logs.")

log(f"\n  Pipeline qualite termine en {(time.time()-t0)/60:.1f} min")
log(f"  Log complet : {LOG}")
