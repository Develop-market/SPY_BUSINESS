"""
EXTRACTION — Extraction reproductible des documents sources
============================================================
Lit les PDFs depuis DATA/SOURCE/ et produit des fichiers bruts dans DATA/DONNEES_EXTRAITES/.

Règles strictes (par ordre de priorité décroissante) :
  EF  (tous)     → Docling TXT
  EF  (natifs)   → camelot Excel (complement uniquement)
                   Seuil qualité : EF_TXT_MIN_WORDS=400 + ancrage "résultat net" / EF_XLSX_MIN_CELLS=40

  CB  (natifs)   → pdfplumber Excel
                   si résultat < CB_MIN_TABLES ou CB_MIN_CELLS → Docling+EasyOCR

  CB  (scannés)  → Docling+EasyOCR Excel

  REGL (tous)    → Docling TXT

IMPORTANT — CB n'utilise JAMAIS de LLM génératif (vision ou texte).
Un LLM-vision (qwen-vl-max) a halluciné des centaines de lignes lors d'une
extraction antérieure (énumérations inventées du type "Compte King/Emperor/
Legend" ou "Compte d'épargne <nom abstrait>" — cf. nettoyage du 2026-06-07,
865 lignes fabriquées supprimées de cb_tarifs). Un OCR déterministe
(pdfplumber/Docling+EasyOCR) ne peut PAS inventer du texte : il transcrit
seulement ce qui est physiquement présent sur la page. Si l'extraction
déterministe est insuffisante, le fichier est marqué [REVISION MANUELLE]
plutôt que d'être complété par une génération de texte.

Détection entièrement automatique — aucune liste à maintenir.
Pour ajouter un fichier : déposer dans DATA/SOURCE/, relancer run_extraction.py.

Usage:
  python run_extraction.py                              # tout traiter
  python run_extraction.py --type etats                 # EF seulement
  python run_extraction.py --type conditions            # CB seulement
  python run_extraction.py --type reglementations       # REGL seulement
  python run_extraction.py --banques SIB ECOBANK        # filtrer des banques
"""

import sys
from pathlib import Path
import pdfplumber

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Chemins ───────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent.parent
DATA_DIR   = BASE_DIR / "DATA" / "SOURCE"
OUTPUT_DIR = BASE_DIR / "DATA" / "DONNEES_EXTRAITES"

ETATS_SRC  = DATA_DIR / "ETATS_FINANCIERS"
COND_SRC   = DATA_DIR / "CONDITIONS_BANQUES"
REGL_SRC   = DATA_DIR / "REGLEMENTATION"

DENSITY_THRESHOLD = 100   # chars/page — en dessous = scanne
IMAGE_EXTS        = {".jpg", ".jpeg", ".png"}
CB_MIN_TABLES     = 4     # pdfplumber insuffisant si < 4 feuilles → Docling auto
CB_MIN_CELLS      = 200   # pdfplumber insuffisant si < 200 cellules non-vides → Docling auto
# EF_TXT_MIN_BYTES remplacé le 2026-10-26 : la taille en octets n'est pas fiable (gonflée par
# l'encodage des accents, ne mesure pas le contenu). Remplacé par un seuil en nombre de mots,
# calibré sur les 17 états financiers du corpus réel (le plus petit cas valide en compte 500),
# combiné à un ancrage de contenu qui confirme qu'il s'agit bien d'un état financier.
EF_TXT_MIN_WORDS  = 400   # TXT EF insuffisant si < 400 mots → re-extraction Docling
EF_REQUIRED_TERMS = ("résultat net", "pnb")  # un seul suffit ; "résultat net" présent dans 17/17
EF_XLSX_MIN_CELLS = 40    # XLSX EF insuffisant si < 40 cellules → re-extraction camelot


# ── Detection PDF natif / scanne ──────────────────────────────────────────────
def detect(src_path: Path) -> str:
    if src_path.suffix.lower() in IMAGE_EXTS:
        return "scanned"
    try:
        with pdfplumber.open(src_path) as pdf:
            chars   = sum(len(p.extract_text() or "") for p in pdf.pages)
            pages   = len(pdf.pages)
            density = chars / pages if pages else 0
        return "native" if density > DENSITY_THRESHOLD else "scanned"
    except Exception:
        return "scanned"


def _count_sheets(path: Path) -> tuple[int, int]:
    """
    Retourne (nb_feuilles_non_vides, total_cellules_non_vides) d'un xlsx.
    Détecte les extractions Docling dégénérées : si > 50 feuilles avec moyenne
    < 3 lignes par feuille, considéré comme extraction échouée (retourne 0,0).
    """
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True)
    n_sheets = len(wb.sheetnames)
    sheets, cells = 0, 0
    rows_per_sheet = []
    for name in wb.sheetnames:
        ws = wb[name]
        row_list = list(ws.iter_rows(values_only=True))
        sheet_cells = sum(1 for row in row_list for c in row if c and str(c).strip())
        sheet_rows  = sum(1 for row in row_list if any(c and str(c).strip() for c in row))
        if sheet_cells:
            sheets += 1
            cells  += sheet_cells
            rows_per_sheet.append(sheet_rows)
    wb.close()
    # Extraction dégénérée : trop de feuilles quasi-vides (artefact Docling)
    if n_sheets > 50 and rows_per_sheet:
        avg_rows = sum(rows_per_sheet) / len(rows_per_sheet)
        if avg_rows < 3:
            return 0, 0  # forcer re-extraction
    return sheets, cells


def _sans_accents(s: str) -> str:
    """Retire les accents (les extractions OCR en MAJUSCULES les perdent souvent)."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _text_quality(path: Path) -> tuple[int, bool]:
    """
    Retourne (nb_mots, ancrage_present) d'un TXT d'état financier.
    L'ancrage (un des EF_REQUIRED_TERMS) confirme qu'il s'agit bien d'un état financier
    et non d'un texte insuffisant qui dépasserait le seuil de mots par hasard.
    Comparaison sans accents~: certaines extractions OCR en majuscules les perdent
    ("RESULTAT NET"), d'autres (rapports narratifs) les conservent ("Résultat net").
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    words = len(text.split())
    texte_norm = _sans_accents(text).lower()
    anchor = any(_sans_accents(terme) in texte_norm for terme in EF_REQUIRED_TERMS)
    return words, anchor


# ── ETATS FINANCIERS ──────────────────────────────────────────────────────────
def process_etats(src_path: Path, out_dir: Path):
    """
    1. TXT  : Docling depuis DATA/SOURCES/ (skip si déjà présent)
    2. Excel: camelot si PDF natif (complement uniquement)
    """
    stem     = src_path.stem
    txt_out  = out_dir / (stem + ".txt")
    xlsx_out = out_dir / (stem + ".xlsx")
    pdf_type = detect(src_path)

    # --- 1. TXT (source primaire) ---
    if txt_out.exists():
        words, anchor = _text_quality(txt_out)
        if words >= EF_TXT_MIN_WORDS and anchor:
            print(f"    [TXT OK   ] {txt_out.name}  ({words} mots, ancrage trouvé — existe)")
        else:
            txt_out.unlink()
            print(f"    [QUALITE  ] {txt_out.name} insuffisant ({words} mots, "
                  f"ancrage={'oui' if anchor else 'non'}) → re-extraction ...", flush=True)

    if not txt_out.exists():
        print(f"    [DOCLING  ] {src_path.name} ...", end=" ", flush=True)
        try:
            from extract_scanned import extract_scanned
            info = extract_scanned(src_path, txt_out)
            print(f"OK  ({info.get('tables','?')} blocs, {info.get('total_chars',0):,} chars)")
        except Exception as e:
            print(f"ERREUR: {str(e)[:70]}")

    # --- 2. Excel natif (complement) ---
    if pdf_type == "native":
        if xlsx_out.exists():
            _, cells = _count_sheets(xlsx_out)
            if cells >= EF_XLSX_MIN_CELLS:
                print(f"    [XLSX OK  ] {xlsx_out.name}  ({cells} cellules — existe)")
            else:
                xlsx_out.unlink()
                print(f"    [QUALITE  ] {xlsx_out.name} insuffisant ({cells} cellules) → re-extraction ...",
                      flush=True)

        if not xlsx_out.exists():
            print(f"    [CAMELOT  ] {src_path.name} ...", end=" ", flush=True)
            try:
                from extract_native import extract_etats_financiers
                info = extract_etats_financiers(src_path, xlsx_out)
                print(f"OK  ({info.get('tables','?')} tableaux — {info.get('method','?')})")
            except Exception as e:
                print(f"ERREUR: {str(e)[:70]}")


# ── REGLEMENTATION ───────────────────────────────────────────────────────────
def process_reglementation(src_path: Path, out_dir: Path):
    """
    TXT uniquement (pas de tableaux) : Docling+Tesseract depuis DATA/SOURCES/.
    Ajouter un nouveau PDF dans DATA/SOURCES/REGLEMENTATION/ suffit.
    """
    stem    = src_path.stem
    txt_out = out_dir / (stem + ".txt")

    if txt_out.exists():
        print(f"    [TXT OK   ] {txt_out.name}  ({txt_out.stat().st_size:,} bytes — existe)")
        return

    print(f"    [DOCLING  ] {src_path.name} ...", end=" ", flush=True)
    try:
        from extract_scanned import extract_scanned
        info = extract_scanned(src_path, txt_out)
        print(f"OK  ({info.get('total_chars', 0):,} chars)")
    except Exception as e:
        print(f"ERREUR: {str(e)[:70]}")


# ── Marquage pour révision manuelle (remplace l'ancien fallback Vision LLM) ───
def _flag_for_manual_review(src_path: Path, out_dir: Path, reason: str):
    """
    Si pdfplumber ET Docling+EasyOCR sont insuffisants, on NE complète PAS
    avec un LLM génératif (risque d'hallucination — cf. note en tête de
    fichier). On consigne le cas dans REVISION_MANUELLE.txt pour qu'un humain
    relise le PDF source et complète la table à la main si besoin.
    """
    flag_file = out_dir / "REVISION_MANUELLE.txt"
    line = f"{src_path.name} : {reason}\n"
    existing = flag_file.read_text(encoding="utf-8") if flag_file.exists() else ""
    if src_path.name not in existing:
        flag_file.write_text(existing + line, encoding="utf-8")
    print(f"    [REVISION MANUELLE] {src_path.name} — {reason} (voir {flag_file.name})")


# ── CONDITIONS DE BANQUES ─────────────────────────────────────────────────────
def process_conditions(src_path: Path, out_dir: Path):
    """
    Natif   → pdfplumber ; si < CB_MIN_TABLES/CB_MIN_CELLS → Docling+EasyOCR
                         ; si encore insuffisant            → REVISION_MANUELLE
    Scanné  → Docling+EasyOCR ; si < CB_MIN_CELLS           → REVISION_MANUELLE

    Aucun LLM génératif (vision ou texte) n'intervient sur les CB : seules des
    méthodes déterministes (pdfplumber, Docling+EasyOCR) transcrivent le texte
    physiquement présent. Aucune liste de banques à maintenir : le seuil
    CB_MIN_CELLS est le seul critère.
    """
    out_path = out_dir / (src_path.stem + ".xlsx")
    if out_path.exists():
        _, cells = _count_sheets(out_path)
        if cells >= CB_MIN_CELLS:
            print(f"    [OK       ] {out_path.name}  (existe, {cells} cellules)")
            return
        # Fichier existant insuffisant → supprimer et re-extraire
        out_path.unlink()
        print(f"    [QUALITE  ] {out_path.name} insuffisant ({cells} cellules) → re-extraction ...",
              flush=True)

    pdf_type = detect(src_path)

    if pdf_type == "native":
        print(f"    [NATIF    ] {src_path.name} ...", end=" ", flush=True)
        try:
            from extract_native import extract_conditions
            info          = extract_conditions(src_path, out_path)
            sheets, cells = _count_sheets(out_path)
            if sheets >= CB_MIN_TABLES and cells >= CB_MIN_CELLS:
                print(f"OK  ({sheets} feuilles, {cells} cellules — pdfplumber)")
                return
            out_path.unlink(missing_ok=True)
            print(f"faible ({sheets} feuilles, {cells} cellules) → Docling ...",
                  end=" ", flush=True)
        except Exception:
            out_path.unlink(missing_ok=True)
            print(f"pdfplumber echec → Docling ...", end=" ", flush=True)

    else:
        print(f"    [SCANNE   ] {src_path.name} ...", end=" ", flush=True)
        # Reconstruction par COORDONNÉES OCR (Tesseract) d'abord : répare les
        # plaquettes scannées que Docling sérialise par colonne (libellé↔valeur
        # désappariés, ex. SIB). Adoptée si suffisamment riche, sinon Docling.
        try:
            from extract_native import extract_conditions_scanned_coords
            info = extract_conditions_scanned_coords(src_path, out_path)
            if out_path.exists():
                _, cells = _count_sheets(out_path)
                if cells >= CB_MIN_CELLS:
                    print(f"OK  ({info.get('rows','?')} lignes, {cells} cellules — OCR coords)")
                    return
                out_path.unlink(missing_ok=True)
                print(f"OCR coords faible ({cells}) → Docling ...", end=" ", flush=True)
            else:
                print(f"OCR coords vide → Docling ...", end=" ", flush=True)
        except Exception as e:
            out_path.unlink(missing_ok=True)
            print(f"OCR coords échec ({str(e)[:40]}) → Docling ...", end=" ", flush=True)

    # Docling+EasyOCR (scanné direct OU fallback natif insuffisant) — déterministe
    docling_ok = False
    try:
        from extract_scanned import extract_scanned_to_excel
        info = extract_scanned_to_excel(src_path, out_path)
        if out_path.exists():
            _, cells = _count_sheets(out_path)
            if cells >= CB_MIN_CELLS:
                print(f"OK  ({info.get('tables','?')} feuilles, {cells} cellules — docling)")
                docling_ok = True
            else:
                out_path.unlink(missing_ok=True)
                print(f"Docling insuffisant ({cells} cellules)", flush=True)
                _flag_for_manual_review(src_path, out_dir,
                    f"pdfplumber et Docling+EasyOCR insuffisants ({cells} cellules)")
        else:
            print(f"Docling: pas de sortie", flush=True)
            _flag_for_manual_review(src_path, out_dir, "Docling n'a produit aucune sortie")
    except Exception as e:
        out_path.unlink(missing_ok=True)
        print(f"Docling echec ({str(e)[:50]})", flush=True)
        _flag_for_manual_review(src_path, out_dir, f"Docling en echec : {str(e)[:80]}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main(banques=None, type_="all"):
    sys.path.insert(0, str(Path(__file__).parent))

    def _keep(name):
        return banques is None or name.upper() in [b.upper() for b in banques]

    print("=" * 70)
    print("  PIPELINE_2 — Extraction reproductible")
    print("  EF   : Docling TXT + camelot Excel (natifs)")
    print(f"  CB   : pdfplumber → Docling+EasyOCR (seuil : {CB_MIN_CELLS} cellules)")
    print("         si insuffisant → REVISION_MANUELLE.txt (aucun LLM génératif)")
    print("  REGL : Docling TXT")
    print(f"  OUT  : {OUTPUT_DIR}")
    if banques:
        print(f"  Banques filtrees : {', '.join(banques)}")
    print("=" * 70)

    # ── ETATS FINANCIERS ─────────────────────────────────────────────────────
    if type_ in ("all", "etats"):
        print(f"\n{'─'*70}\n  ETATS FINANCIERS\n{'─'*70}")
        for banque_dir in sorted(ETATS_SRC.iterdir()):
            if not banque_dir.is_dir() or not _keep(banque_dir.name):
                continue
            pdfs = sorted(banque_dir.glob("*.pdf"))
            if not pdfs:
                continue
            print(f"\n  {banque_dir.name}")
            out_dir = OUTPUT_DIR / "ETATS_FINANCIERS" / banque_dir.name
            out_dir.mkdir(parents=True, exist_ok=True)
            for pdf in pdfs:
                process_etats(pdf, out_dir)

    # ── CONDITIONS DE BANQUES ─────────────────────────────────────────────────
    if type_ in ("all", "conditions"):
        print(f"\n{'─'*70}\n  CONDITIONS DE BANQUES\n{'─'*70}")
        for banque_dir in sorted(COND_SRC.iterdir()):
            if not banque_dir.is_dir() or not _keep(banque_dir.name):
                continue
            print(f"\n  {banque_dir.name}")
            for annee_dir in sorted(banque_dir.iterdir()):
                if not annee_dir.is_dir():
                    continue
                fichiers = sorted(
                    f for f in annee_dir.iterdir()
                    if f.suffix.lower() in ({".pdf"} | IMAGE_EXTS)
                )
                if not fichiers:
                    continue
                print(f"    {annee_dir.name}")
                out_dir = (OUTPUT_DIR / "CONDITIONS_BANQUES"
                           / banque_dir.name / annee_dir.name)
                out_dir.mkdir(parents=True, exist_ok=True)
                for f in fichiers:
                    process_conditions(f, out_dir)

    # ── REGLEMENTATION ───────────────────────────────────────────────────────
    if type_ in ("all", "reglementations"):
        print(f"\n{'─'*70}\n  REGLEMENTATION\n{'─'*70}")
        if REGL_SRC.exists():
            out_dir = OUTPUT_DIR / "REGLEMENTATION"
            out_dir.mkdir(parents=True, exist_ok=True)
            fichiers = sorted(
                f for f in REGL_SRC.iterdir()
                if f.suffix.lower() in ({".pdf"} | IMAGE_EXTS)
            )
            if fichiers:
                for f in fichiers:
                    process_reglementation(f, out_dir)
            else:
                print("  (aucun fichier PDF/image trouvé)")
        else:
            print(f"  (dossier source absent : {REGL_SRC})")

    print(f"\n{'='*70}\n  PIPELINE_2 termine.\n{'='*70}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PIPELINE_2 extraction")
    parser.add_argument("--banques", nargs="*",
                        help="Banques a traiter (defaut: toutes)")
    parser.add_argument("--type", choices=["all", "etats", "conditions", "reglementations"],
                        default="all", dest="type_")
    args = parser.parse_args()
    main(banques=args.banques, type_=args.type_)
