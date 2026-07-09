"""
EXTRACTION TXT CB — Export Docling markdown pour CONDITIONS_BANQUES
===================================================================
Génère un fichier TXT (markdown Docling) pour chaque source CB,
placé à côté du XLSX dans DONNEES_EXTRAITES/CONDITIONS_BANQUES/.

Stratégie :
  PDF natif  → Docling sans OCR (rapide, très propre)
  PDF scanné → Docling + EasyOCR fr+en (plus lent, OCR)
  Image JPG  → Docling + EasyOCR fr+en

Le TXT est le complément du XLSX : il capture les footnotes, paragraphes
narratifs et tables manquées par l'extraction tableur.

Usage:
  python extract_cb_txt.py                      # manquants seulement
  python extract_cb_txt.py --force              # re-extraire tout
  python extract_cb_txt.py --banques SGCI BNI   # filtrer banques
"""

import sys, argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE    = Path(__file__).resolve().parent.parent.parent
SRC_DIR = BASE / "DATA" / "SOURCE"             / "CONDITIONS_BANQUES"
OUT_DIR = BASE / "DATA" / "DONNEES_EXTRAITES"  / "CONDITIONS_BANQUES"
IMG_EXT = {".jpg", ".jpeg", ".png"}
MIN_CH  = 500   # chars minimum pour considérer un TXT valide


# ── Détection natif / scanné ──────────────────────────────────────────────────

def _is_native(path: Path) -> bool:
    """True si PDF avec texte embarqué (densité > 100 chars/page)."""
    if path.suffix.lower() in IMG_EXT:
        return False
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            ch = sum(len(p.extract_text() or "") for p in pdf.pages)
            pg = len(pdf.pages)
        return (ch / pg if pg else 0) > 100
    except Exception:
        return False


# ── Converters Docling (lazy init) ────────────────────────────────────────────

_dcl_nat = None
_dcl_ocr = None


def _native_converter():
    global _dcl_nat
    if _dcl_nat is None:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        p = PdfPipelineOptions()
        p.do_ocr = False
        p.do_table_structure = True
        _dcl_nat = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=p)}
        )
    return _dcl_nat


def _ocr_converter():
    global _dcl_ocr
    if _dcl_ocr is None:
        print("  [OCR] Init Docling + EasyOCR fr+en ...", flush=True)
        from docling.document_converter import DocumentConverter, PdfFormatOption, ImageFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
        p = PdfPipelineOptions()
        p.do_ocr = True
        p.do_table_structure = True
        p.ocr_options = EasyOcrOptions(lang=["fr", "en"], use_gpu=False)
        _dcl_ocr = DocumentConverter(
            format_options={
                InputFormat.PDF:   PdfFormatOption(pipeline_options=p),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=p),
            }
        )
        print("  [OCR] Prêt.", flush=True)
    return _dcl_ocr


# ── Extraction d'un fichier ───────────────────────────────────────────────────

def extract_one(src: Path, out: Path) -> dict:
    """
    Extrait le TXT (markdown Docling) depuis src → out.
    Retourne {"chars": int, "native": bool}.
    """
    native = _is_native(src)
    conv   = _native_converter() if native else _ocr_converter()
    res    = conv.convert(str(src))
    md     = res.document.export_to_markdown()

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return {"chars": len(md), "native": native}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Extraction TXT Docling pour CB")
    ap.add_argument("--force",   action="store_true",
                    help="Re-extraire même les TXT existants")
    ap.add_argument("--banques", nargs="*",
                    help="Filtrer certaines banques (ex: SGCI BNI)")
    args = ap.parse_args()

    def _keep(name: str) -> bool:
        return args.banques is None or name.upper() in [b.upper() for b in args.banques]

    n_ok = n_skip = n_err = 0

    print("=" * 65)
    print("  EXTRACTION TXT CB — Docling markdown")
    print(f"  Source  : {SRC_DIR}")
    print(f"  Sortie  : {OUT_DIR}")
    print(f"  Seuil   : {MIN_CH} chars minimum")
    print("=" * 65)

    for bd in sorted(SRC_DIR.iterdir()):
        if not bd.is_dir() or not _keep(bd.name):
            continue
        print(f"\n  {bd.name}")

        for ad in sorted(bd.iterdir()):
            if not ad.is_dir():
                continue

            od = OUT_DIR / bd.name / ad.name
            od.mkdir(parents=True, exist_ok=True)

            srcs = sorted(
                f for f in ad.iterdir()
                if f.suffix.lower() in {".pdf"} | IMG_EXT
            )
            if not srcs:
                continue

            print(f"    {ad.name}/")

            for src in srcs:
                out = od / (src.stem + ".txt")

                # Skip si déjà existant et assez grand
                if out.exists() and not args.force:
                    sz = out.stat().st_size
                    if sz >= MIN_CH:
                        print(f"      [SKIP] {out.name}  ({sz:,} chars)")
                        n_skip += 1
                        continue
                    # Trop petit → re-extraire
                    out.unlink()
                    print(f"      [PETIT] {out.name} ({sz} chars) → re-extraction")

                print(f"      {src.name} ...", end=" ", flush=True)
                try:
                    info = extract_one(src, out)
                    mode = "natif" if info["native"] else "OCR"
                    print(f"OK  {info['chars']:,} chars ({mode})")
                    n_ok += 1
                except Exception as e:
                    print(f"ERR  {str(e)[:90]}")
                    n_err += 1

    print(f"\n{'=' * 65}")
    print(f"  Résultat : {n_ok} générés | {n_skip} skipped | {n_err} erreurs")
    print(f"{'=' * 65}")


def retry_small(min_kb: float = 1.0):
    """
    Retraite avec OCR tous les TXT existants dont la taille est < min_kb KB
    mais dont le PDF source fait > 200 KB (= le TXT est trop pauvre → PDF scanné).
    Utile quand un PDF est classé "natif" mais est en réalité scanné.
    """
    print(f"\n{'='*65}")
    print(f"  RETRY SMALL — OCR sur TXT < {min_kb} KB (PDF source > 200 KB)")
    print(f"{'='*65}")

    import pdfplumber  # noqa: imported here to keep module-level clean

    n_ok = n_skip = 0
    for bd in sorted(SRC_DIR.iterdir()):
        if not bd.is_dir():
            continue
        for ad in sorted(bd.iterdir()):
            if not ad.is_dir():
                continue
            od = OUT_DIR / bd.name / ad.name
            for src in sorted(f for f in ad.iterdir()
                               if f.suffix.lower() in {".pdf"} | IMG_EXT):
                out = od / (src.stem + ".txt")
                if not out.exists():
                    continue
                txt_kb = out.stat().st_size / 1024
                src_kb = src.stat().st_size / 1024
                if txt_kb >= min_kb or src_kb < 200:
                    n_skip += 1
                    continue
                print(f"  [{bd.name}/{ad.name}] {src.name} → TXT={txt_kb:.0f}KB, PDF={src_kb:.0f}KB → OCR...")
                try:
                    conv = _ocr_converter()
                    res  = conv.convert(str(src))
                    md   = res.document.export_to_markdown()
                    out.write_text(md, encoding="utf-8")
                    print(f"    OK  {len(md):,} chars")
                    n_ok += 1
                except Exception as e:
                    print(f"    ERR {str(e)[:80]}")

    print(f"\n  Retried: {n_ok} | Skipped: {n_skip}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--retry-small":
        retry_small()
    else:
        main()
