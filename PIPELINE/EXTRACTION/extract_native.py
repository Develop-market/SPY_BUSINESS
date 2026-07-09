"""
PIPELINE 2 — Extraction native (PDF avec texte embarqué)
  CONDITIONS_BANQUES : pdfplumber → camelot stream fallback
  ETATS_FINANCIERS   : camelot lattice → stream fallback
Sortie : fichier Excel .xlsx — 1 feuille par tableau extrait
"""

import warnings
warnings.filterwarnings("ignore")

import re
import statistics
from pathlib import Path
from openpyxl import Workbook

# Seuil minimum de lignes de données réelles pour considérer pdfplumber suffisant
_MIN_ROWS_PDFPLUMBER = 10

# ── Reconstruction CB « par coordonnées » (secours plaquettes denses multi-blocs) ──
# Quand pdfplumber.extract_tables() ne détecte pas la grille (PDF sans bordures, ou
# plusieurs blocs code|libellé|valeur côte à côte, ex. BACI), on reconstruit le tableau
# à partir des POSITIONS (x,y) des mots : blocs par colonnes-code, colonne valeur par
# médiane X, lignes par regroupement Y. Déterministe — n'invente rien.
_CB_CODE_RE = re.compile(r'^\d+(?:\.\d+)*\.?$')


def _cb_is_val(t: str) -> bool:
    t = (t or "").strip().lower()
    return bool(re.search(r'gratuit|n/?a|n[ée]ant|fcfa|\bht\b|\bttc\b|%|^[\d][\d .,]*$', t))


def _reconstruct_by_coords(pdf_path: Path) -> list:
    """PDF natif → liste de (code, libellé, valeur) reconstruite par coordonnées."""
    import pdfplumber
    rows = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            W = page.width
            words = page.extract_words(keep_blank_chars=False)
            if not words:
                continue
            # 1) blocs = clusters des x0 des mots-code (≥3 codes = vrai bloc), fusion si <250px
            cx = sorted(w['x0'] for w in words if _CB_CODE_RE.match(w['text'].strip()))
            cl = []
            for x in cx:
                if not cl or x - cl[-1][-1] > 50:
                    cl.append([x])
                else:
                    cl[-1].append(x)
            starts = sorted(statistics.median(c) for c in cl if len(c) >= 3)
            if not starts:
                starts = [min(w['x0'] for w in words)]
            mst = []
            for s in starts:
                if not mst or s - mst[-1] >= 250:
                    mst.append(s)
            starts = mst
            bounds = [(starts[i] - 8, (starts[i + 1] - 8 if i + 1 < len(starts) else W + 1))
                      for i in range(len(starts))]
            # 2) chaque bloc, en lecture haut→bas
            for (bx0, bx1) in bounds:
                bw = [w for w in words if bx0 <= w['x0'] < bx1]
                if len(bw) < 3:
                    continue
                valx = [w['x0'] for w in bw if _cb_is_val(w['text']) and not _CB_CODE_RE.match(w['text'].strip())]
                vcol = statistics.median(valx) if len(valx) >= 3 else bx0 + (bx1 - bx0) * 0.62
                bw.sort(key=lambda w: (w['top'], w['x0']))
                lines, cur, cy = [], [], None
                for w in bw:
                    if cy is None or w['top'] - cy <= 10:
                        cur.append(w)
                    else:
                        lines.append(cur); cur = [w]
                    cy = w['top']
                if cur:
                    lines.append(cur)
                for ln in lines:
                    ln.sort(key=lambda w: w['x0'])
                    code, rest = '', ln
                    if _CB_CODE_RE.match(ln[0]['text'].strip()):
                        code = ln[0]['text'].strip(); rest = ln[1:]
                    lib = ' '.join(w['text'] for w in rest if w['x0'] < vcol - 12).strip()
                    val = ' '.join(w['text'] for w in rest if w['x0'] >= vcol - 12).strip()
                    # dédoublonne les mots consécutifs ("de de compte compte" → "de compte")
                    lib = re.sub(r'\b(\w+)(?:\s+\1\b)+', r'\1', lib, flags=re.IGNORECASE)
                    # ignore les lignes de PRÉAMBULE (pas un service tarifé)
                    if not code and re.match(
                        r'(?i)^(tbb\b|au titre|les conditions|le pr[ée]sent|a-?\s*tarif|b-?\s*tarif|'
                        r'services offerts|recueil|bar[èe]me|n/?a\b|conditions g[ée]n[ée]rales? de banque)', lib):
                        continue
                    rows.append([code, lib, val, round(bx0)])
    # fusion des lignes de continuation (sans code ni valeur) → libellé précédent du MÊME bloc
    merged = []
    for code, lib, val, bx0 in rows:
        if (not code) and (not val) and lib and merged and merged[-1][3] == bx0 and merged[-1][1]:
            merged[-1][1] = (merged[-1][1] + ' ' + lib).strip()
        else:
            merged.append([code, lib, val, bx0])
    return [(c, l, v) for c, l, v, _ in merged]


def _wb_from_coords(coord_rows: list) -> Workbook:
    """Construit un Workbook 3 colonnes [code, libellé, valeur] — détecté « 3col » par le nettoyage."""
    wb = Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("COORDS")
    for code, lib, val in coord_rows:
        ws.append([code, lib, val])
    return wb


# ── Reconstruction CB « SCANNÉE » par coordonnées OCR (Tesseract) ─────────────
# Les CB scannées (image JPG/PNG, ou PDF sans texte) passent par Docling qui
# SÉRIALISE le tableau PAR COLONNE (tous les codes, puis tous les libellés, puis
# toutes les valeurs) → libellé↔valeur DÉSAPPARIÉS (cas SIB : 282 lignes inversées).
# On reconstruit par POSITIONS (x,y) des mots OCR : colonnes principales = clusters
# X des codes ; frontière = vallée de couverture (gouttière) ; colonne valeur =
# médiane X des valeurs à droite ; lignes = regroupement Y. Déterministe.
_TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# Code STRICT pour le scan : groupes de 1-2 chiffres séparés par des points, AU MOINS
# un point (« 1.1.4 », « 2.2.2.7 »). Différent de _CB_CODE_RE (natif BACI, trop large :
# « ^\d+(\.\d+)*$ » matche les PRIX « 10.000 » → polluait colonnes et colonne-valeur).
_CB_CODE_STRICT = re.compile(r'^\d{1,2}(?:\.\d{1,2}){1,5}\.?$')


def _cb_norm_code(t: str) -> str:
    # l'OCR lit parfois "." comme ":" ou "," dans les codes (« 1:1:1 » → « 1.1.1 »)
    return re.sub(r'[,:]', '.', t.strip()).rstrip('.')


def _cb_ocr_words(pil_img):
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD
    d = pytesseract.image_to_data(pil_img, lang="fra", config="--oem 1 --psm 11",
                                  output_type=pytesseract.Output.DICT)
    ws = []
    for i in range(len(d["text"])):
        t = (d["text"][i] or "").strip()
        try:
            conf = float(d["conf"][i])
        except (ValueError, TypeError):
            conf = -1
        if not t or conf < 25:
            continue
        x0, y0, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        ws.append({"t": t, "x0": x0, "x1": x0 + w, "cx": x0 + w / 2,
                   "top": y0, "cy": y0 + h / 2, "h": h})
    return ws, pil_img.width


def _cb_find_columns(words, W):
    """Colonnes principales = clusters X des mots-code ; frontière = vallée de
    couverture entre deux colonnes-code (gouttière, côté droit).
    On utilise le regex STRICT (pas le tolérant) pour ne PAS confondre les valeurs
    numériques (« 0,15 », « 12 000) ») avec des codes → évite une 4e colonne fantôme."""
    code_x = sorted(w["cx"] for w in words if _CB_CODE_STRICT.match(w["t"].strip()))
    cl = []
    for x in code_x:
        if not cl or x - cl[-1][-1] > 300:
            cl.append([x])
        else:
            cl[-1].append(x)
    starts = [statistics.median(c) for c in cl if len(c) >= 4]
    if len(starts) < 2:
        return [(0, W)]
    BIN = 20
    nb = W // BIN + 2
    cov = [0] * nb
    for w in words:
        for b in range(int(w["x0"]) // BIN, int(w["x1"]) // BIN + 1):
            if 0 <= b < nb:
                cov[b] += 1
    bounds = []
    for i in range(len(starts) - 1):
        a, b = int(starts[i]), int(starts[i + 1])
        lo = max(a + 200, b - 700) // BIN
        hi = (b - 30) // BIN
        seg = [k for k in range(lo, hi) if 0 <= k < nb]
        if seg:
            bounds.append(min(seg, key=lambda k: cov[k]) * BIN)
    edges = [0] + bounds + [W]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def _cb_reconstruct_block(bw, bx0, bx1):
    if len(bw) < 4:
        return []
    mid = bx0 + (bx1 - bx0) * 0.45
    # colonne valeur = médiane X des valeurs de la moitié DROITE. On exclut les
    # codes STRICTS uniquement (pas les nombres « 0,15 » / « 12.000 » qui SONT des
    # valeurs : les exclure décalait la colonne-valeur et cassait l'appariement).
    valx = [w["x0"] for w in bw
            if _cb_is_val(w["t"]) and not _CB_CODE_STRICT.match(w["t"].strip()) and w["x0"] > mid]
    vcol = statistics.median(valx) if len(valx) >= 4 else bx0 + (bx1 - bx0) * 0.70
    bw.sort(key=lambda w: (w["cy"], w["x0"]))
    tol = max(14, statistics.median([w["h"] for w in bw]) * 0.6)
    lines, cur, cy = [], [], None
    for w in bw:
        if cy is None or abs(w["cy"] - cy) <= tol:
            cur.append(w); cy = w["cy"] if cy is None else (cy + w["cy"]) / 2
        else:
            lines.append(cur); cur = [w]; cy = w["cy"]
    if cur:
        lines.append(cur)
    rows = []
    for ln in lines:
        ln.sort(key=lambda w: w["x0"])
        code, rest = "", ln
        if _CB_CODE_STRICT.match(ln[0]["t"].strip()):
            code = _cb_norm_code(ln[0]["t"]); rest = ln[1:]
        lib = " ".join(w["t"] for w in rest if w["x0"] < vcol - 30).strip()
        val = " ".join(w["t"] for w in rest if w["x0"] >= vcol - 30).strip()
        lib = re.sub(r'\b(\w+)(?:\s+\1\b)+', r'\1', lib, flags=re.IGNORECASE)
        rows.append([code, lib, val, round(bx0)])
    return rows


def _cb_images_from_source(src_path: Path):
    from PIL import Image
    suffix = src_path.suffix.lower()
    if suffix in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"):
        return [Image.open(str(src_path))]
    imgs = []
    try:
        import fitz  # PyMuPDF — rendu des PDF scannés en images
        doc = fitz.open(str(src_path))
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            imgs.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        doc.close()
    except Exception:
        pass
    return imgs


def reconstruct_scanned_cb(src_path: Path) -> list:
    """Image/PDF scanné CB → liste (code, libellé, valeur) par coordonnées OCR."""
    HDR = re.compile(r'(?i)^(code|libell[ée]|montant ou valeur|tarifs des|taux de base)$')
    out = []
    for img in _cb_images_from_source(Path(src_path)):
        words, W = _cb_ocr_words(img)
        if not words:
            continue
        rows = []
        for (cx0, cx1) in _cb_find_columns(words, W):
            bw = [w for w in words if cx0 <= w["cx"] < cx1]
            rows += _cb_reconstruct_block(bw, cx0, cx1)
        merged = []
        for code, lib, val, bx in rows:
            if (not code) and (not val) and lib and merged and merged[-1][3] == bx and merged[-1][1]:
                merged[-1][1] = (merged[-1][1] + " " + lib).strip()
            else:
                merged.append([code, lib, val, bx])
        for code, lib, val, _ in merged:
            l = (lib or "").strip()
            if HDR.match(l) and not val:
                continue
            # parasite : fragments de l'encadré « TEG » (symboles mathématiques)
            if not code and re.search(r'[=□]', l):
                continue
            out.append((code, l, val))
    return out


def extract_conditions_scanned_coords(src_path: Path, out_path: Path) -> dict:
    """Reconstruit un CB scanné par coordonnées OCR → xlsx 3 colonnes [code,libellé,valeur]."""
    rows = reconstruct_scanned_cb(src_path)
    if not rows:
        return {"method": "scanned_coords", "tables": 0, "rows": 0}
    wb = _wb_from_coords(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))
    return {"method": "scanned_coords", "tables": 1, "rows": len(rows)}


def _count_real_rows(wb: Workbook) -> int:
    """Compte les lignes non vides dans tous les sheets."""
    total = 0
    for sheet in wb.sheetnames:
        ws = wb[sheet]
        for row in ws.iter_rows():
            if any(cell.value for cell in row):
                total += 1
    return total


def _wb_from_camelot_stream(pdf_path: Path) -> tuple:
    """camelot stream → Workbook. Retourne (wb, nb_tables)."""
    import camelot
    wb = Workbook()
    wb.remove(wb.active)
    tables = camelot.read_pdf(str(pdf_path), pages="all", flavor="stream")
    for idx, table in enumerate(tables):
        ws = wb.create_sheet(f"T{idx}")
        for row in table.data:
            ws.append([str(c).replace("\n", " ").strip() for c in row])
    if len(tables) == 0:
        wb.create_sheet("VIDE")
    return wb, len(tables)


# ─── CONDITIONS DE BANQUES → pdfplumber puis camelot stream si insuffisant ───

def extract_conditions(pdf_path: Path, out_path: Path) -> dict:
    import pdfplumber

    wb = Workbook()
    wb.remove(wb.active)
    table_count = 0

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    ws = wb.create_sheet(f"T{table_count}")
                    for row in table:
                        cleaned = [
                            str(cell).replace("\n", " ").strip() if cell is not None else ""
                            for cell in row
                        ]
                        ws.append(cleaned)
                    table_count += 1

    real_rows = _count_real_rows(wb)

    def _cells(w):
        return sum(1 for sh in w.sheetnames for r in w[sh].iter_rows() for c in r if c.value)

    # SECOURS « par coordonnées » : si pdfplumber n'a pas détecté la grille (< 200 cellules,
    # critère de la pipeline) → reconstruction par positions X/Y (plaquettes denses multi-blocs,
    # ex. BACI). On l'adopte si elle est NETTEMENT plus riche que pdfplumber.
    if _cells(wb) < 200:
        try:
            coord_rows = _reconstruct_by_coords(pdf_path)
            wb_co = _wb_from_coords(coord_rows)
            if len(coord_rows) >= max(real_rows, 20) and _cells(wb_co) > _cells(wb):
                out_path.parent.mkdir(parents=True, exist_ok=True)
                wb_co.save(str(out_path))
                return {"method": "coords", "tables": 1, "rows": len(coord_rows)}
        except Exception:
            pass

    # pdfplumber insuffisant → on essaie camelot stream
    if real_rows < _MIN_ROWS_PDFPLUMBER:
        try:
            wb_cs, n = _wb_from_camelot_stream(pdf_path)
            rows_cs = _count_real_rows(wb_cs)
            if rows_cs > real_rows:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                wb_cs.save(str(out_path))
                return {"method": "camelot_stream_fallback", "tables": n, "rows": rows_cs}
        except Exception:
            pass

    # pdfplumber était suffisant ou camelot n'a pas mieux fait
    if table_count == 0:
        # Dernier recours : texte brut
        ws = wb.create_sheet("TEXTE")
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.split("\n"):
                    if line.strip():
                        ws.append([line.strip()])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))
    return {"method": "pdfplumber", "tables": table_count, "rows": real_rows}


# ─── ETATS FINANCIERS → camelot ──────────────────────────────────────────────

def extract_etats_financiers(pdf_path: Path, out_path: Path) -> dict:
    import camelot

    wb = Workbook()
    wb.remove(wb.active)
    table_count = 0
    method_used = "camelot_lattice"

    # Lattice d'abord (tableaux avec lignes visibles)
    try:
        tables = camelot.read_pdf(str(pdf_path), pages="all", flavor="lattice")
        if len(tables) == 0:
            raise ValueError("Lattice : 0 tableaux")
    except Exception:
        # Fallback stream (tableaux sans lignes)
        try:
            tables = camelot.read_pdf(str(pdf_path), pages="all", flavor="stream")
            method_used = "camelot_stream"
        except Exception as e:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            wb.create_sheet("VIDE")
            wb.save(str(out_path))
            return {"method": "camelot_failed", "tables": 0, "error": str(e)}

    for idx, table in enumerate(tables):
        ws = wb.create_sheet(f"T{idx}")
        for row in table.data:
            cleaned = [str(cell).replace("\n", " ").strip() for cell in row]
            ws.append(cleaned)
        table_count += 1

    if table_count == 0:
        wb.create_sheet("VIDE")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))
    return {"method": method_used, "tables": table_count}
