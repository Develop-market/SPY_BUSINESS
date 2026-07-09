"""
PIPELINE 2 — Extraction scannée (PDF sans texte embarqué)

EF → TXT  : Docling (DocLayNet + EasyOCR fr+en) → TXT structuré avec [TABLEAUX DOCLING]
            Fallback Tesseract (PyMuPDF 300 DPI, fra+eng) si Docling < 100 chars
CB → XLSX : Docling uniquement → XLSX structuré (tableaux markdown → colonnes)
            Pas de fallback Tesseract (texte brut = inutilisable pour conditions bancaires)
"""

import sys
import warnings
warnings.filterwarnings("ignore")

from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSERACT_LANG = "fra+eng"
TESSERACT_DPI  = 300  # résolution de rendu PDF → image


# ─── Lazy init Docling OCR ────────────────────────────────────────────────────

_docling_ocr = None


def get_docling_ocr():
    global _docling_ocr
    if _docling_ocr is None:
        print("  [DOCLING] Init pipeline OCR (DocLayNet + EasyOCR fr+en)...")
        from docling.document_converter import DocumentConverter, PdfFormatOption, ImageFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions

        opts = PdfPipelineOptions()
        opts.do_ocr = True
        opts.do_table_structure = True
        opts.ocr_options = EasyOcrOptions(lang=["fr", "en"], use_gpu=False)

        _docling_ocr = DocumentConverter(
            format_options={
                InputFormat.PDF:   PdfFormatOption(pipeline_options=opts),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=opts),
            }
        )
        print("  [DOCLING] Pipeline OCR prêt.")
    return _docling_ocr


# ─── Tesseract OCR (fonctions conservées, non utilisées en production) ───────

def extract_tesseract(pdf_path: Path, out_path: Path) -> dict:
    """
    PyMuPDF → rendu 300 DPI → Tesseract fra+eng → TXT.
    Utilisé quand Docling EasyOCR n'arrive pas à lire le PDF.
    """
    import fitz
    import pytesseract
    from PIL import Image
    import io

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    doc = fitz.open(str(pdf_path))
    pages_data = []

    for i, page in enumerate(doc):
        mat  = fitz.Matrix(TESSERACT_DPI / 72, TESSERACT_DPI / 72)
        pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img  = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(img, lang=TESSERACT_LANG,
                                           config="--psm 6")
        pages_data.append({"page": i + 1, "text": text.strip(),
                            "nb_chars": len(text.strip())})

    doc.close()
    total_chars = sum(p["nb_chars"] for p in pages_data)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines_out = [
        "=" * 80,
        "  PIPELINE 2 — Tesseract OCR (PyMuPDF 300 DPI, fra+eng)",
        f"  Source  : {pdf_path.name}",
        f"  Pages   : {len(pages_data)}",
        f"  Méthode : tesseract_fra_eng",
        f"  Total chars : {total_chars:,}",
        "=" * 80,
        "",
    ]
    for p in pages_data:
        lines_out += [
            f"[PAGE {p['page']}]  [chars={p['nb_chars']} method=tesseract_fra_eng]",
            "",
            p["text"],
            "",
        ]

    out_path.write_text("\n".join(lines_out), encoding="utf-8")
    return {"method": "tesseract_fra_eng", "total_chars": total_chars,
            "pages": len(pages_data)}


# ─── Extraction principale ────────────────────────────────────────────────────

def extract_scanned(pdf_path: Path, out_path: Path) -> dict:
    """
    Docling OCR → TXT structuré avec [TABLEAUX DOCLING].
    out_path doit avoir l'extension .txt (fourni par run.py).
    """
    conv = get_docling_ocr()
    res  = conv.convert(str(pdf_path))
    doc  = res.document

    # Grouper items par page
    pages_items: dict[int, list] = {}
    for item, _ in doc.iterate_items():
        prov = getattr(item, "prov", None)
        if prov:
            pages_items.setdefault(prov[0].page_no, []).append(item)

    pages_data = []
    for pno in sorted(pages_items.keys()):
        lines     = []
        has_table = False
        tables_md = []

        for item in pages_items[pno]:
            typ = type(item).__name__
            if typ == "TableItem":
                has_table = True
                try:
                    md = item.export_to_markdown(doc)
                except TypeError:
                    md = item.export_to_markdown()
                tables_md.append(md)
            elif hasattr(item, "text") and item.text:
                lines.append(item.text)

        page_text = "\n".join(lines)
        if tables_md:
            page_text += "\n\n[TABLEAUX DOCLING]\n" + "\n\n".join(tables_md)

        pages_data.append({
            "page":       pno,
            "text":       page_text,
            "nb_chars":   len(page_text),
            "has_tables": has_table,
            "method":     "docling_easyocr",
        })

    total_chars = sum(p["nb_chars"] for p in pages_data)

    # Écriture TXT Docling structuré
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines_out = [
        "=" * 80,
        "  PIPELINE 2 — Docling OCR (EasyOCR fr+en)",
        f"  Source  : {pdf_path.name}",
        f"  Pages   : {len(pages_data)}",
        f"  Méthode : docling_easyocr",
        f"  Total chars : {total_chars:,}",
        "=" * 80,
        "",
    ]
    for p in pages_data:
        lines_out += [
            f"[PAGE {p['page']}]  "
            f"[chars={p['nb_chars']} tables={'OUI' if p['has_tables'] else 'NON'} method={p['method']}]",
            "",
            p["text"],
            "",
        ]

    out_path.write_text("\n".join(lines_out), encoding="utf-8")

    # Fallback Tesseract si Docling n'a rien extrait (PDF trop dégradé pour EasyOCR)
    if total_chars < 100:
        print(f"  [TESSERACT] Docling insuffisant ({total_chars} chars) → Tesseract fallback ...",
              end=" ", flush=True)
        try:
            info = extract_tesseract(pdf_path, out_path)
            print(f"OK ({info['total_chars']:,} chars)")
            return {"method": "tesseract_fra_eng", **info}
        except Exception as e:
            print(f"ERREUR: {str(e)[:60]}")

    return {
        "method": "docling_easyocr",
        "tables": sum(1 for p in pages_data if p["has_tables"]),
        "total_chars": total_chars,
    }


# ─── CONDITIONS scannées → Excel ──────────────────────────────────────────────

def _md_table_to_rows(md: str) -> list[list[str]]:
    """Parse un tableau markdown → liste de listes (colonnes Excel propres)."""
    rows = []
    for line in md.split("\n"):
        if not line.strip() or line.strip().startswith("|--") or line.strip().startswith("|:-"):
            continue
        if "|" in line:
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c != ""]  # retirer les cellules vides de bord
            if cells:
                rows.append(cells)
        else:
            stripped = line.strip()
            if stripped:
                rows.append([stripped])
    return rows


def extract_tesseract_to_excel(pdf_path: Path, out_path: Path) -> dict:
    """
    PyMuPDF 300 DPI → Tesseract fra+eng → Excel (1 feuille = 1 page).
    Utilisé quand Docling ne trouve rien dans un PDF scanné.
    """
    import fitz
    import pytesseract
    from PIL import Image
    import io
    from openpyxl import Workbook

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    fitz_doc = fitz.open(str(pdf_path))
    wb = Workbook()
    wb.remove(wb.active)
    total_chars = 0

    for i, page in enumerate(fitz_doc):
        mat  = fitz.Matrix(TESSERACT_DPI / 72, TESSERACT_DPI / 72)
        pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img  = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(img, lang=TESSERACT_LANG,
                                           config="--psm 6")
        ws = wb.create_sheet(f"P{i+1:02d}")
        ws.append([f"=== PAGE {i+1} ==="])
        ws.append([])
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped:
                # Détecter colonnes par tabulations ou espaces multiples
                parts = [p.strip() for p in stripped.replace("\t", "  ").split("  ") if p.strip()]
                ws.append(parts if len(parts) > 1 else [stripped])
                total_chars += len(stripped)

    n_pages = len(fitz_doc)
    fitz_doc.close()
    if not wb.sheetnames:
        wb.create_sheet("VIDE")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))
    return {"method": "tesseract_page_excel", "tables": n_pages,
            "total_chars": total_chars}


def extract_scanned_to_excel(pdf_path: Path, out_path: Path) -> dict:
    """
    Docling OCR → Excel (1 feuille = 1 page, tableaux markdown → colonnes).
    Docling OCR uniquement — pas de fallback Tesseract.
    """
    from openpyxl import Workbook
    from collections import defaultdict

    conv = get_docling_ocr()
    res  = conv.convert(str(pdf_path))
    doc  = res.document

    # Grouper les items par page
    pages_items: dict[int, list] = defaultdict(list)
    for item, _ in doc.iterate_items():
        prov = getattr(item, "prov", None)
        page_no = prov[0].page_no if prov else 0
        pages_items[page_no].append(item)

    total_tables = 0
    total_text_items = sum(
        1 for items in pages_items.values()
        for it in items if hasattr(it, "text") and it.text
    )
    total_items = total_tables + total_text_items

    if total_items < 5:
        print(f"  [DOCLING] Attention — seulement {total_items} items (PDF très dégradé ?)")

    wb = Workbook()
    wb.remove(wb.active)

    for pno in sorted(pages_items.keys()):
        ws = wb.create_sheet(f"P{pno:02d}")
        ws.append([f"=== PAGE {pno} ==="])
        ws.append([])

        for item in pages_items[pno]:
            typ = type(item).__name__
            if typ == "TableItem":
                total_tables += 1
                try:
                    md = item.export_to_markdown(doc)
                except TypeError:
                    md = item.export_to_markdown()
                rows = _md_table_to_rows(md)
                if rows:
                    for r in rows:
                        ws.append(r)
                else:
                    try:
                        df = item.export_to_dataframe()
                        ws.append(list(df.columns.astype(str)))
                        for _, row in df.iterrows():
                            ws.append([str(v).replace("\n", " ").strip() for v in row])
                    except Exception:
                        pass
                ws.append([])
            elif hasattr(item, "text") and item.text:
                ws.append([item.text])

    if not wb.sheetnames:
        ws = wb.create_sheet("TEXTE")
        for item, _ in doc.iterate_items():
            if hasattr(item, "text") and item.text:
                ws.append([item.text])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))

    meaningful = sum(
        1 for name in wb.sheetnames
        for row in wb[name].iter_rows()
        for c in row
        if c.value and str(c.value).strip()
        and not str(c.value).strip().startswith("=== PAGE")
    )
    if meaningful < 20:
        print(f"  [DOCLING] Attention — seulement {meaningful} cellules non-vides (PDF très dégradé ?)")

    return {"method": "docling_page_excel", "tables": total_tables, "cells": meaningful}
