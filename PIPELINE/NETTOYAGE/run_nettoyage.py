"""
NETTOYAGE — Nettoyage et structuration SANS LLM
=================================================
Lit les fichiers bruts de DATA/DONNEES_EXTRAITES/ et produit des _clean dans DATA/DONNEES_PRETRAITEES/.
Traite : CONDITIONS_BANQUES (CB) | ETATS_FINANCIERS (EF) | REGLEMENTATIONS (REGL)

Sorties :
  DATA/DONNEES_PRETRAITEES/CONDITIONS_BANQUES/{banque}/{annee}/{stem}_clean.xlsx
  DATA/DONNEES_PRETRAITEES/ETATS_FINANCIERS/{banque}/{stem}_clean.xlsx
  DATA/DONNEES_PRETRAITEES/REGLEMENTATION/{nom}_clean.txt
  DATA/DONNEES_PRETRAITEES/rapport.xlsx

Usage:
  python run_nettoyage.py               # tout traiter
  python run_nettoyage.py --cb          # CB seulement
  python run_nettoyage.py --ef          # EF seulement
  python run_nettoyage.py --regl        # REGL seulement
"""

import re, sys, json, unicodedata, argparse
from pathlib import Path
from collections import defaultdict

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
except ImportError:
    sys.exit("[ERR] pip install openpyxl")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Chemins ────────────────────────────────────────────────────────────────────
BASE   = Path(__file__).resolve().parent.parent.parent
P2_CB   = BASE / "DATA" / "DONNEES_EXTRAITES"   / "CONDITIONS_BANQUES"
PRET_CB = BASE / "DATA" / "DONNEES_PRETRAITEES" / "CONDITIONS_BANQUES"
SRC_CB  = BASE / "DATA" / "SOURCE"              / "CONDITIONS_BANQUES"
SRC_EF  = BASE / "DATA" / "DONNEES_EXTRAITES"   / "ETATS_FINANCIERS"
OUT     = BASE / "DATA" / "DONNEES_PRETRAITEES"

# ── Constantes de nettoyage ────────────────────────────────────────────────────
GRATUIT_VALS = {"GRATUIT", "NEANT", "NÉANT", "N/A", "NA", "NON APPLICABLE",
                "EXONERE", "EXONÉRÉ", "EXONEREE", "FREE", "NIL", "-", "0"}
UNIT_SKIP   = {"FCFA", "FCFA / HT", "FCFA/HT", "HT", "TTC", "%",
               "MONTANT", "VALEUR", "XOF", "CFA", "MONTANTS NETS",
               "En Millions de FCFA", "Millions de francs CFA"}
SECTION_RE  = re.compile(r'^\d{1,2}[\.,]\d{1,2}([\.,]\d{1,4})*\s*$')
# Codes courts ambigus : A1, P2, HB1, C10, A11 — RÈGLE : "SI AMBIGUE NE MET PAS"
_AMBIGUOUS_CODE_RE = re.compile(r'^[A-Z]{1,3}\d{1,3}([._]\d{1,3})?$')
# Libellés sous-produit génériques (même label réutilisé dans plusieurs produits)
# Ex : "Première carte" ECLAIR vs VISA HORIZON — nécessite enrichissement avec parent
_GENERIC_SUBITEM_RE = re.compile(
    r'^(?:1[eè]re?|[Pp]remi[eè]re?)\s+carte\b'
    r'|^(?:2[eè]me?|[Ss]econde?|[Dd]euxi[eè]me?)\s+carte\b'
    r'|^(?:3[eè]me?|[Tt]roisi[eè]me?)\s+carte\b'
    r'|^(?:4[eè]me?|[Qq]uatri[eè]me?)\s+carte\b'
    r'|^(?:5[eè]me?|[Cc]inqui[eè]me?)\s+carte\b',
    re.I
)
YEAR_RE     = re.compile(
    r'(20\d{2}|19\d{2}|Dec\.?\-?\s*\d{2,4}|31/12/\d{4}|Déc\.?\-?\s*\d{2,4}|'
    r'Décembre\s*\d{4}|AN\d|AN\s?\d)',
    re.I
)

# ── Nettoyage de base ─────────────────────────────────────────────────────────

def _str(v) -> str:
    if v is None:
        return ""
    s = str(v).replace("\xa0", " ").replace("-\r\n", "").replace("-\n", "")
    s = s.replace("\n", " ").replace("\r", " ")
    return " ".join(s.split()).strip()


def is_section_code(v: str) -> bool:
    return bool(SECTION_RE.match(v.strip()))


def is_pure_text(v: str) -> bool:
    up = v.strip().upper()
    for g in GRATUIT_VALS:
        if up == g.upper():
            return False
    return not bool(re.search(r'\d', v))


def is_garbage(v: str) -> bool:
    """Séquences OCR type '1  2  3  4  5' ou '>FCFA HT' seuls."""
    stripped = v.strip()
    # Séquence de petits nombres séparés par espaces
    nums = stripped.split()
    if len(nums) >= 4 and all(re.fullmatch(r'\d{1,3}', n) for n in nums):
        return True
    # Que des caractères de ponctuation/symboles sans signification
    if re.fullmatch(r'[^a-zA-Z0-9FCFA%,.\-/]*', stripped):
        return True
    return False


def is_multi_concat(v: str) -> bool:
    """Plusieurs montants concaténés : '34 912 7 128 142 19 404'."""
    groups = re.findall(r'\d[\d ]*\d|\d', v)
    # Cherche plusieurs "blocs numériques" séparés par espaces
    number_groups = re.findall(r'\d+', v.replace(",", "."))
    if len(number_groups) >= 5:
        # Vérifie que ce ne sont pas juste des décimales
        long_groups = [g for g in number_groups if len(g) >= 3]
        if len(long_groups) >= 4:
            return True
    return False


def normalize_number(v: str) -> str:
    """
    Supprime les espaces entre chiffres (séparateur milliers FR).
    '1 870 883' → '1870883', '2 350' → '2350'.
    Préserve les décimales : '1,8%' reste '1,8%'.

    CORRECTION OCR (chiffre parasite = renvoi/note de bas de page) :
    Les PDF scannés produisent parfois '<nombre> <chiffre isolé>' (ex. '29080 2',
    '800 3', '30 000 8') où le DERNIER token est UN seul chiffre. C'est un renvoi
    de note de bas de page collé au montant. La VRAIE valeur = le nombre SANS ce
    chiffre ('29080 2' → 29080, '800 3' → 800). Un nombre FR bien groupé finit
    TOUJOURS par un groupe de 3 chiffres (jamais par un chiffre isolé), donc on ne
    touche jamais un nombre bien formé (ex. '1 870 883' reste intact).
    """
    parts = v.split()
    # (1) Chiffre parasite final isolé : '29080 2' → 29080, '800 3' → 800.
    if (len(parts) >= 2 and len(parts[-1]) == 1 and parts[-1].isdigit()
            and all(p.isdigit() for p in parts[:-1])):
        base = ''.join(parts[:-1])
        if base.isdigit() and len(base) >= 2:
            return base
    # (2) Résidu mal groupé après un nombre FR bien formé : '10 000 000 2005' → 10000000.
    #     On consomme le plus long préfixe valide (1-3 chiffres puis groupes de 3),
    #     tout résidu après (année, note, fragment) est ignoré.
    if parts and parts[0].isdigit() and len(parts[0]) <= 3:
        grouped = [parts[0]]
        for t in parts[1:]:
            if t.isdigit() and len(t) == 3:
                grouped.append(t)
            else:
                break
        if len(grouped) >= 2:                # au moins un groupe de milliers
            return ''.join(grouped)
    result = v
    prev = None
    while prev != result:
        prev = result
        result = re.sub(r'(\d) (\d)', r'\1\2', result)
    return result


def clean_val(v) -> tuple[str, str]:
    """
    Retourne (valeur_brute, valeur_propre).
    valeur_propre = '' si la valeur doit être ignorée.
    """
    raw = _str(v)
    if not raw:
        return raw, ""
    up = raw.upper().strip()
    # Valeurs spéciales à conserver telles quelles
    for g in GRATUIT_VALS:
        if up == g.upper():
            return raw, g.upper() if g.upper() in ("GRATUIT", "NÉANT", "NEANT", "N/A") else raw
    if up in {u.upper() for u in UNIT_SKIP}:
        return raw, ""
    if is_section_code(raw):
        return raw, ""
    if is_garbage(raw):
        return raw, ""
    if is_multi_concat(raw):
        return raw, ""
    clean = normalize_number(raw)
    return raw, clean


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 1 — CONDITIONS_BANQUES
# ══════════════════════════════════════════════════════════════════════════════

def _best_xlsx_dir_cb(banque: str, annee: str) -> Path:
    cf = PRET_CB / banque / annee / "CLEAN_FINAL"
    if cf.exists() and any(cf.glob("*.xlsx")):
        return cf
    return P2_CB / banque / annee


def _parse_stem(stem: str):
    parts = stem.upper().split("_")
    sem = parts[0] if parts else "S?"
    seg = "Entreprises" if len(parts) > 1 and parts[1] == "E" else "Particuliers"
    return sem, seg


def _is_header(section: str, libelle: str) -> bool:
    """Vrai si le libellé est un en-tête de section (pas un fragment de continuation).
    Règle: au moins 10 chars et commence par une majuscule, ou section non vide.
    Exclusions : puces, fragments se terminant par ')' ou ',' (continuation).
    """
    if section:
        return True
    stripped = libelle.strip()
    # Puces et tirets → sub-items, jamais des en-têtes
    if re.match(r'^[•\-\u2013\u25aa\u25e6\*·]\s', stripped):
        return False
    # Fragment de continuation : se termine par ')' ou ',' → pas un header
    if stripped.endswith((')', ',')):
        return False
    return len(stripped) >= 10 and stripped[0].isupper()


def _detect_layout(ws) -> str:
    """
    Détecte le layout d'un onglet en échantillonnant les premières lignes.
    Retourne: '3col' | '4col_split' | '5col_dual'
    """
    sample = []
    for row in ws.iter_rows(values_only=True):
        cells = [_str(c) for c in row]
        if any(cells):
            sample.append(cells)
        if len(sample) >= 15:
            break

    max_cols = max((len(r) for r in sample), default=3)
    if max_cols < 4:
        return "3col"

    # Compter combien de lignes ont col[3] qui ressemble à un code de section
    dual_count = sum(
        1 for r in sample
        if len(r) > 3 and r[3] and is_section_code(r[3])
    )
    if dual_count >= 3:
        return "5col_dual"

    # Compter combien de lignes ont col[2] sans chiffre (= suite du libellé)
    split_count = sum(
        1 for r in sample
        if len(r) > 2 and r[2] and not re.search(r'\d', r[2])
        and r[2].upper() not in {u.upper() for u in UNIT_SKIP | GRATUIT_VALS}
    )
    if split_count >= 3:
        return "4col_split"

    # Layout large non reconnu (> 5 colonnes) : extraction 3col sans repair automatique
    if max_cols > 5:
        return "3col_wide"

    return "3col"


def _clean_section(s: str) -> str:
    """Normalise un code section issu de pdfplumber.
    - Corrige le bug OCR l→1 (ex. 4.4.l → 4.4.1)
    - Vide les codes garblés (phrases, chiffres romains, caractères non-numériques)
    """
    if not s:
        return s
    s = s.strip()
    # OCR : 'l' minuscule entre chiffres/points ou en fin de code → '1'
    s = re.sub(r'(?<=[0-9.])l(?=[0-9.]|$)', '1', s)
    s = re.sub(r'^l(?=[0-9.])', '1', s)   # en début de code
    # Code valide : uniquement chiffres et points, commençant par un chiffre
    if re.match(r'^\d[\d.]*$', s):
        return s
    if s.upper() == 'NOTE':
        return s
    return ''   # garblé → vide


def clean_libelle(lib: str) -> str:
    """Nettoyage COSMÉTIQUE et conservateur d'un nom de service (jamais d'invention).
    Corrige les artefacts d'extraction OCR sans inventer de contenu :
      - guillemets parasites issus de fusions de colonnes ('Cartes privatives "Carte KORA')
      - puces et codes de section en tête ('2.2.2.3 ...', '- ...')
      - parenthèse ouverte incomplète en fin ('Transfert d'argent (5', '(5000 –')
      - ponctuation de fin orpheline (':', '–', '"')
    Ce qui n'est PAS récupérable automatiquement (nom réellement tronqué) est laissé
    en l'état après nettoyage cosmétique — à signaler pour revue manuelle.
    """
    if not lib:
        return lib
    s = str(lib).strip()
    # 1. Puces / tirets de tête
    s = re.sub(r'^[\s•\-–▪◦*·]+', '', s)
    # 2. Code de section en tête (ex. '2.2.2.3 ', '7.1 ', '2 ') — exige un point
    #    OU un nombre ≤2 chiffres, pour ne pas confondre avec un montant ('100 FCFA').
    s = re.sub(r'^(?:\d{1,2}(?:\.\d+)+|\d{1,2})\s+(?=[A-Za-zÀ-ÿ«"])', '', s)
    # 3. Guillemets droits parasites (fusion de colonnes) → espace
    s = s.replace('"', ' ')
    # 4. Parenthèse ouverte incomplète en fin : '(', '(5', '(5000 –' (que chiffres/espaces/tirets)
    s = re.sub(r'\s*\([\d\s–\-]*$', '', s)
    # 5. Ponctuation de fin orpheline
    s = re.sub(r'[\s:;,–\-«»]+$', '', s)
    # 6. Espaces multiples
    s = re.sub(r'\s{2,}', ' ', s).strip()
    return s or str(lib).strip()


def _emit_row(banque, annee, sem, seg, sheet_title, section, libelle, v_raw, clean_rows, stats, contexte=""):
    """Nettoie une valeur et ajoute la ligne si valide."""
    section = _clean_section(section or '')
    libelle = clean_libelle(libelle)
    if not libelle and not v_raw:
        stats["empty"] += 1
        return
    brute, propre = clean_val(v_raw)
    if not propre:
        stats["filtre"] += 1
        return
    clean_rows.append({
        "banque": banque, "annee": annee, "semestre": sem, "segment": seg,
        "section": section,
        "contexte": contexte, "libelle": libelle,
        "valeur_brute": brute, "valeur_propre": propre,
    })
    stats["ok"] += 1


def _repair_docling_rows(raw_rows: list) -> list:
    """
    Répare les artefacts Docling courants dans les lignes brutes d'un onglet CB 3col.
    Appliquée AVANT le parsing principal sur la liste de tuples openpyxl.

    Patterns corrigés :
    A. Orphelin valeur  : (None, None, VAL) → fusionne dans la ligne précédente
    B. Cascade Min/Max  : libA|Min:X / libB|Max:Y / None|Z
                          → libA|"Min:X / Max:Y" / libB|Z
    C. Fragment valeur  : (None, None, texte_sans_chiffre) → concat à la valeur précédente
    D. Continuation lib : (None, texte_minuscule_court, None) → concat au libellé précédent
    """
    def s(v):
        if v is None:
            return ""
        return str(v).replace("\xa0", " ").strip()

    result = []   # list of [code, lib, val] (mutables)

    for row in raw_rows:
        code = s(row[0]) if len(row) > 0 else ""
        lib  = s(row[1]) if len(row) > 1 else ""
        val  = s(row[2]) if len(row) > 2 else ""

        # Ignorer les lignes complètement vides
        if not code and not lib and not val:
            continue

        # Garder les lignes d'en-tête telles quelles
        if (lib.upper() in ("LIBELLE", "CODE") or
                val.upper() in ("VALEUR", "FCFA / HT", "FCFA/HT", "FCFA/TTC", "FCFA / TTC")):
            result.append([code, lib, val])
            continue

        if not result:
            result.append([code, lib, val])
            continue

        prev = result[-1]
        prev_code, prev_lib, prev_val = prev[0], prev[1], prev[2]

        # ── PATTERN A+B : ligne orpheline (pas de code, pas de libellé, a une valeur) ──
        if not code and not lib and val:
            # PATTERN B — cascade Min/Max :
            # result[-2]=libA|Min:X  /  result[-1]=libB|Max:Y  /  courant=None|Z
            # Max:Y a été volé à libA ; Z est la vraie valeur de libB
            if (len(result) >= 2 and
                    re.match(r'Min\s*:', result[-2][2], re.I) and
                    re.match(r'Max\s*:', prev_val, re.I) and
                    prev_lib and result[-2][1] != prev_lib):
                result[-2][2] = f"{result[-2][2]} / {prev_val}"  # libA : Min:X / Max:Y
                result[-1][2] = val                               # libB : récupère Z
                continue

            # PATTERN A — orphelin simple : attacher à la ligne précédente
            if prev_val:
                result[-1][2] = f"{prev_val} / {val}"
            else:
                result[-1][2] = val
            continue

        # ── PATTERN C : fragment de valeur textuel (pas de chiffres, orphelin) ────────
        if not code and not lib and val and not re.search(r'\d', val) and prev_val:
            result[-1][2] = f"{prev_val} {val}"
            continue

        # ── PATTERN D : continuation de libellé (minuscule, court, sans valeur) ──────
        if (not code and lib and not val and prev_lib and len(lib) < 45 and
                not lib.startswith(("•", "–", "-")) and
                not re.match(r'^\d', lib)):
            first = lib[0] if lib else ""
            if (first.islower() or
                    lib.lower().startswith(("le ", "la ", "les ", "de ", "du ", "des ",
                                            "l'", "d'", "et ", "ou ", "en ", "sur ", "aux "))):
                result[-1][1] = f"{prev_lib} {lib}"
                continue

        result.append([code, lib, val])

    # Reconvertir en tuples (compatibles avec le code aval)
    return [tuple(r) for r in result]


def _section_sort_key(row) -> list:
    """Cle de tri pour codes section style '1.1.7.2' → [1,1,7,2]."""
    code = str(row[0] if row else '').strip()
    parts = re.findall(r'\d+', code)
    return [int(p) for p in parts] if parts else [999999]


def _sort_rows_preserving_bullets(rows: list) -> list:
    """
    Trie les lignes par code section SANS déplacer les lignes bullet/continuation.
    Un bloc = une ligne de section + toutes les lignes sans code qui la suivent.
    Les blocs sont triés par code, mais les lignes sans code restent collées
    à leur section parente → les frais bullet héritent du bon contexte.

    Sans ce tri, les lignes bullet (• Compte chèque) se retrouveraient en fin
    de tableau avec le contexte de la dernière section vue, pas de leur vraie section.
    """
    # Séparer en-têtes tableau (LIBELLE/CODE) et données
    hdr = [r for r in rows if _str(r[1] if len(r) > 1 else '').upper() in ('LIBELLE', 'CODE')]
    dat = [r for r in rows if _str(r[1] if len(r) > 1 else '').upper() not in ('LIBELLE', 'CODE')]

    # Grouper : chaque bloc commence à une ligne avec un code section
    blocks: list[tuple[list, list]] = []   # (sort_key, rows_in_block)
    current_key: list = []
    current_block: list = []

    for row in dat:
        code = _str(row[0] if len(row) > 0 else '')
        has_code = bool(code) and code != ''
        if has_code:
            if current_block:
                blocks.append((current_key, current_block))
            parts = re.findall(r'\d+', code)
            current_key  = [int(p) for p in parts] if parts else [999999]
            current_block = [row]
        else:
            current_block.append(row)

    if current_block:
        blocks.append((current_key, current_block))

    blocks.sort(key=lambda b: b[0])
    flat = [r for _, blk in blocks for r in blk]
    return hdr + flat


def clean_cb_xlsx(src: Path, banque: str, annee: str, sem: str, seg: str) -> tuple[list, dict]:
    """Lit un XLSX CB → lignes nettoyées + stats.
    Gère 3 layouts : 3col standard, 4col libellé splitté (BICICI),
    5col double-tableau côte à côte (NSIA).
    Applique _repair_docling_rows sur le layout 3col avant parsing.
    """
    try:
        from openpyxl import load_workbook
        wb = load_workbook(src, data_only=True)
    except Exception as e:
        return [], {"error": str(e)}

    clean_rows, stats = [], defaultdict(int)
    seen = set()   # pour dédoublonner (utile quand T2=T3 identiques)

    for ws in wb.worksheets:
        layout = _detect_layout(ws)

        # Collecter toutes les lignes brutes et appliquer la réparation Docling
        raw_rows = list(ws.iter_rows(values_only=True))
        if layout == "3col":
            raw_rows = _repair_docling_rows(raw_rows)
            # Trier par code section en préservant les lignes bullet collées à leur parent
            raw_rows = _sort_rows_preserving_bullets(raw_rows)
        elif layout == "3col_wide":
            print(f"      [LAYOUT ?] {ws.title} — {ws.max_column} colonnes, layout non reconnu → extraction 3col sans repair")

        ctx_stack = []        # list de (section_code: str, label: str)
        last_section_code = ''  # dernier code section vu (pour hériter aux puces)

        for row in raw_rows:
            r = [_str(c) for c in row]
            while r and not r[-1]:
                r.pop()

            def _update_ctx(section, libelle):
                if not libelle or not _is_header(section, libelle):
                    return
                if section:
                    if section and section[0].isdigit():
                        # Section décimale : nettoyer les non-ancêtres
                        ctx_stack[:] = [(c, l) for (c, l) in ctx_stack
                                        if c and section.startswith(c + '.')]
                    # Section non-décimale (ex: "II", "III") : juste ajouter sans effacer
                    ctx_stack.append((section, libelle))
                else:
                    ctx_stack.append(('', libelle))

            def _get_ctx():
                return " | ".join(l for c, l in ctx_stack if c) if ctx_stack else ""

            def _get_ctx_for(sec):
                if not sec:
                    return _get_ctx()
                # Inclure les ancêtres (préfixe) ET la section exacte elle-même
                matching = [l for c, l in ctx_stack
                            if c and (sec.startswith(c + '.') or sec == c)]
                # Retourner "" si aucun ancêtre trouvé — ne pas propager un contexte
                # périmé d'une section sans rapport (ex. "Coffre Fort" pour section 5)
                return " | ".join(matching)

            if layout == "4col_split":
                section = r[0] if r else ""
                p1 = r[1] if len(r) > 1 else ""
                p2 = r[2] if len(r) > 2 else ""
                libelle = (p1 + p2).strip()
                v_raw   = r[3] if len(r) > 3 else ""

                if not v_raw:
                    _update_ctx(section, libelle)
                else:
                    key = (section, libelle, v_raw)
                    if key not in seen:
                        seen.add(key)
                        _emit_row(banque, annee, sem, seg, ws.title, section, libelle, v_raw, clean_rows, stats, _get_ctx())

            elif layout == "5col_dual":
                section_l = r[0] if r else ""
                libelle_l = r[1] if len(r) > 1 else ""
                v_raw_l   = r[2] if len(r) > 2 else ""

                if not v_raw_l:
                    _update_ctx(section_l, libelle_l)
                else:
                    key_l = (section_l, libelle_l, v_raw_l)
                    if key_l not in seen:
                        seen.add(key_l)
                        _emit_row(banque, annee, sem, seg, ws.title, section_l, libelle_l, v_raw_l, clean_rows, stats, _get_ctx())

                if len(r) > 4:
                    section_r = r[3]
                    v_raw_r   = r[4]
                    key_r = (section_r, "", v_raw_r)
                    if key_r not in seen:
                        seen.add(key_r)
                        _emit_row(banque, annee, sem, seg, ws.title, section_r, "", v_raw_r, clean_rows, stats, _get_ctx())

            else:  # 3col standard
                section = r[0] if r else ""
                libelle = r[1] if len(r) > 1 else ""
                v_raw   = r[2] if len(r) > 2 else ""
                if not v_raw and len(r) > 3:
                    v_raw = r[3]

                # Puces (•, –, -, ▪) sans code section → hériter du parent
                _BPAT = re.compile(r'^[•\-\u2013\u25aa\u25e6\*·]\s*')
                if _BPAT.match(libelle) and not section:
                    libelle = _BPAT.sub('', libelle).strip()
                    section = last_section_code
                # Mettre à jour le dernier code section connu
                if section and not _BPAT.match(r[1] if len(r) > 1 else ''):
                    last_section_code = _clean_section(section)

                # Puces (•, –, -, ▪) sans code section → hériter du parent
                _BPAT = re.compile(r'^[•\-\u2013\u25aa\u25e6\*·]\s*')
                if _BPAT.match(libelle) and not section:
                    libelle = _BPAT.sub('', libelle).strip()
                    section = last_section_code
                # Mettre à jour le dernier code section connu
                if section and not _BPAT.match(r[1] if len(r) > 1 else ''):
                    last_section_code = _clean_section(section)

                # Puces (•, –, -, ▪) sans code section → hériter du parent
                _BPAT = re.compile(r'^[•\-\u2013\u25aa\u25e6\*·]\s*')
                if _BPAT.match(libelle) and not section:
                    libelle = _BPAT.sub('', libelle).strip()
                    section = last_section_code
                # Mettre à jour le dernier code section connu
                if section and not _BPAT.match(r[1] if len(r) > 1 else ''):
                    last_section_code = _clean_section(section)

                # Valeur = entier seul 1-9 : distinguer numero de page vs vrai compte
                if re.fullmatch(r'[1-9]', v_raw):
                    lib_up = libelle.upper()
                    # Si le libelle suggere un vrai nombre (quantite, limite, plafond...)
                    if re.search(
                            r'NOMBRE|LIMITE|MAXIMUM|MINIMUM|\bMAX\b|\bMIN\b'
                            r'|QUOTA|PLAFOND|PERSONNE|MEMBRE|JOUR|MOIS', lib_up):
                        v_eff = v_raw   # conserver → NUMERIQUE
                    else:
                        v_eff = ""      # page DOCLING → ENTETE_SECTION
                else:
                    v_eff = v_raw

                if not v_eff:
                    _update_ctx(section, libelle)
                    # Emettre aussi comme ligne structurelle (is_header detecte en stockage via vb=vp="")
                    if libelle and _is_header(section, libelle):
                        hdr_key = ('HDR', ws.title, section, libelle)
                        if hdr_key not in seen:
                            seen.add(hdr_key)
                            clean_rows.append({
                                "banque": banque, "annee": annee, "semestre": sem, "segment": seg,
                                "section": _clean_section(section or ''),
                                "contexte": _get_ctx_for(section),
                                "libelle": libelle,
                                "valeur_brute": "",
                                "valeur_propre": "",
                            })
                            stats["ok"] += 1
                else:
                    key = (section, libelle, v_eff)
                    if key not in seen:
                        seen.add(key)
                        _emit_row(banque, annee, sem, seg, ws.title, section, libelle, v_eff, clean_rows, stats, _get_ctx_for(section))

    wb.close()
    clean_rows = _enrich_generic_labels(clean_rows)
    return clean_rows, dict(stats)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE CB — Enrichissement TXT Docling
# ══════════════════════════════════════════════════════════════════════════════

def _find_txt_cb(banque: str, annee: str, stem: str) -> Path | None:
    """
    Cherche le TXT Docling correspondant au stem CB.
    Cherche d'abord {stem}.txt, puis {stem}_docling.txt.
    """
    base = P2_CB / banque / annee
    for suffix in (stem + ".txt", stem + "_docling.txt"):
        p = base / suffix
        if p.exists() and p.stat().st_size >= 200:
            return p
    return None


def _detect_parallel_columns(raw: str) -> bool:
    """
    Détecte le format Docling "colonnes parallèles" : codes section puis libellés
    puis valeurs listés en blocs séquentiels (typique des PDFs multi-colonnes NSIA).
    Heuristique : ≥5 codes section consécutifs dans les 300 premières lignes non-vides.
    """
    SECT = re.compile(r'^\d+\.\d[\d\.]*$')
    consec = 0
    count  = 0
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        count += 1
        if count > 600:
            break
        if SECT.match(s):
            consec += 1
            if consec >= 5:
                return True
        else:
            consec = 0
    return False


def _parse_parallel_txt_cb(raw: str, banque: str, annee: str,
                            sem: str, seg: str) -> tuple[list, dict]:
    """
    Parse le format Docling "colonnes parallèles" (NSIA) :
    bloc 1 = codes section / bloc 2 = libellés / bloc 3 = valeurs, répété par table PDF.

    Stratégie en 3 étapes :
    1. Trouver les "runs" de codes section (blocs column-1).
    2. Pour chaque run : séparer libellés (column-2) et valeurs (column-3) par heuristique.
    3. Aligner les trois blocs avec deux corrections critiques :
       A) Libellés sous-titres intermédiaires (ex. "Packages sur …") → aucune valeur.
       B) Lignes feuilles sans valeur dans le PDF (détectées par incompatibilité de type)
          → la valeur suivante ne doit pas être consommée par cette feuille.
    """
    SECT_RE = re.compile(r'^\d+\.\d[\d\.]*$')
    VAL_RE  = re.compile(
        r'\d[\d\s]*(?:FCFA|XOF|%)|'
        r'^(?:Gratuit|Non ind|Non Appl|Aucun|Nous cons|Voir|APPLICABLE|Renégoc)',
        re.I)

    lines     = raw.splitlines()
    non_empty = [(i + 1, l.strip()) for i, l in enumerate(lines) if l.strip()]

    # ── Trouver tous les runs de codes section ──────────────────────────────────
    runs: list     = []
    cur_run:  list = []
    cur_start      = None
    for idx, (lineno, line) in enumerate(non_empty):
        if SECT_RE.match(line):
            if cur_start is None:
                cur_start = idx
            cur_run.append(line)
        else:
            if len(cur_run) >= 5:
                runs.append((cur_start, idx - 1, list(cur_run)))
            cur_run   = []
            cur_start = None
    if len(cur_run) >= 5:
        runs.append((cur_start, len(non_empty) - 1, list(cur_run)))

    if not runs:
        return [], {}

    rows:  list = []
    stats: dict = defaultdict(int)
    seen:  set  = set()

    # Mapping section_code → libellé pour les sections non-feuilles (titre de rubrique).
    # Alimenté au fur et à mesure des runs (les parents précèdent toujours leurs enfants).
    global_sect_to_lib: dict[str, str] = {}

    def _ctx_for_sect(sect: str) -> str:
        """Reconstruit le contexte d'une feuille depuis ses sections parentes."""
        parts = sect.split('.')
        ctx = []
        for depth in range(1, len(parts)):
            parent = '.'.join(parts[:depth])
            if parent in global_sect_to_lib:
                ctx.append(global_sect_to_lib[parent])
        return ' | '.join(ctx)

    def _is_extra_subheader(lib: str) -> bool:
        """
        Retourne True si le libellé est un sous-titre intermédiaire sans tarif individuel.
        Ces libellés regroupent des produits (ex. "Packages sur compte chèque") et n'ont
        pas de valeur propre dans le PDF — ils décalent l'alignement s'ils sont traités
        comme des lignes de données.
        """
        return lib.lower().startswith('packages ')

    def _type_mismatch(lib: str, val: str) -> bool:
        """
        Retourne True si le type de valeur est incompatible avec le libellé.
        Permet de détecter les feuilles dont la cellule PDF est vide (aucune valeur
        extraite dans le bloc valeurs) : la valeur suivante appartient à une autre feuille.
        Cas identifié : libellé "Commission …" attend un taux (%), mais reçoit un montant
        en FCFA → incompatibilité → cette feuille n'a pas de valeur, ne pas la consommer.
        """
        ll = lib.lower()
        vl = val.lower()
        if 'commission' in ll:
            if 'fcfa' in vl and '%' not in vl:
                return True  # Commission sans % → cellule vide dans le PDF
        return False

    for run_idx, (start_idx, end_idx, sections) in enumerate(runs):
        next_start = runs[run_idx + 1][0] if run_idx + 1 < len(runs) else len(non_empty)
        between    = [line for _, line in non_empty[end_idx + 1: next_start]]
        if not between:
            continue

        # Sections feuilles (aucun enfant dans la liste)
        is_leaf = {s: not any(o.startswith(s + '.') for o in sections) for s in sections}

        # ── Séparer libellés / valeurs ───────────────────────────────────────────
        split_at = None
        for i, item in enumerate(between):
            if VAL_RE.search(item):
                split_at = i
                break
        if split_at is None:
            continue

        libelles_raw = between[:split_at]
        values_raw   = between[split_at:]

        # ── Fusionner continuations libellés ─────────────────────────────────────
        libelles: list = []
        for l in libelles_raw:
            if not libelles:
                libelles.append(l)
                continue
            first = l[0] if l else ''
            if first.islower() or l.startswith(('(', 'bancaires ', 'au sein ')):
                libelles[-1] += ' ' + l
            else:
                libelles.append(l)

        # ── Fusionner continuations valeurs ──────────────────────────────────────
        values: list = []
        for v in values_raw:
            if not values:
                values.append(v)
                continue
            if re.match(r'^(?:De |>=|<=|>|<|\*|•|Dont|dont|avec un|et max|et min)', v):
                values[-1] += ' | ' + v
            elif VAL_RE.search(v) or re.match(
                    r'^(?:Gratuit|Non|Aucun|Nous|Voir|APPLICABLE|Renégoc)', v, re.I):
                values.append(v)
            else:
                values[-1] += ' ' + v

        # ── Zip naïf sections ↔ libellés ─────────────────────────────────────────
        paired = [
            (sections[i], libelles[i] if i < len(libelles) else "")
            for i in range(len(sections))
        ]

        # Enregistrer les non-feuilles comme titres de contexte (parents avant enfants)
        for s, l in paired:
            if l and not is_leaf.get(s, True):
                global_sect_to_lib[s] = _str(l)

        # ── Assigner valeurs avec corrections A et B ──────────────────────────────
        val_idx = 0
        for sect, lib in paired:
            # A. Non-feuille → pas de valeur
            if not is_leaf.get(sect, True):
                continue

            lib_clean = _str(lib)
            if not lib_clean:
                continue

            # A. Sous-titre intermédiaire de groupe → pas de tarif individuel
            if _is_extra_subheader(lib_clean):
                continue

            if val_idx >= len(values):
                break

            v_raw = values[val_idx]

            # B. Incompatibilité de type → feuille sans valeur dans le PDF
            #    (ne pas consommer la valeur : elle appartient à la feuille suivante)
            if _type_mismatch(lib_clean, v_raw):
                continue

            val_idx += 1  # consommer la valeur

            # Filtre qualité libellé
            alpha = sum(1 for c in lib_clean if c.isalpha())
            if alpha < 3 or len(lib_clean) < 4:
                stats["filtre_qualite"] += 1
                continue
            if lib_clean[0] in ':;|–—•►▶*#@!()[]{}<>':
                stats["filtre_qualite"] += 1
                continue

            brute, propre = clean_val(v_raw)
            if not propre:
                continue

            lib_n = re.sub(r'\s+', ' ', lib_clean.lower())[:60]
            val_n = re.sub(r'\s+', ' ', propre.lower())[:30]
            key   = (lib_n, val_n)
            if key in seen:
                stats["dedup"] += 1
                continue
            seen.add(key)

            rows.append({
                "banque":        banque,
                "annee":         annee,
                "semestre":      sem,
                "segment":       seg,
                "section":       sect,
                "contexte":      _ctx_for_sect(sect),
                "libelle":       lib_clean,
                "valeur_brute":  brute,
                "valeur_propre": propre,
            })
            stats["ok"] += 1

    return rows, dict(stats)


def _parse_txt_cb(txt_path: Path, banque: str, annee: str,
                  sem: str, seg: str) -> tuple[list, dict]:
    """
    Parse un TXT markdown Docling de CB → lignes dans le même format que clean_cb_xlsx.
    Capture :
      • Lignes de tableaux markdown (code | libelle | valeur)
      • Footnotes (* Note: NB:)
      • Lignes narratives avec montant FCFA inline
    Retourne (rows, stats).
    """
    try:
        raw = txt_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [], {"error": str(e)}

    rows  = []
    stats = defaultdict(int)
    seen  = set()   # (lib_norm, val_norm)

    # ── Colonnes parallèles Docling (NSIA-style) ──────────────────────────────
    if _detect_parallel_columns(raw):
        par_rows, par_stats = _parse_parallel_txt_cb(raw, banque, annee, sem, seg)
        rows.extend(par_rows)
        for k, v in par_stats.items():
            stats[k] += v
        # Peupler seen avec les clés déjà ajoutées
        for r in par_rows:
            lib_n = re.sub(r'\s+', ' ', _str(r.get("libelle", "")).lower())[:60]
            val_n = re.sub(r'\s+', ' ', _str(r.get("valeur_propre", "")).lower())[:30]
            seen.add((lib_n, val_n))

    # Context stack: sections détectées dans le markdown
    ctx_parts: list[str] = []   # pile de labels de sections

    in_table      = False
    col_code      = -1
    col_libelle   = -1
    col_valeur    = -1

    _FOOTNOTE_RE = re.compile(
        r'^[\*†‡•]\s+|^Note\s*[:\-]\s*|^N\.?B\.?\s*[:\-]\s*|^Remarque\s*[:\-]\s*',
        re.I
    )
    # Montant inline: "Service XYZ : 5 000 FCFA" ou "XYZ................5000 FCFA"
    _INLINE_RE = re.compile(
        r'^(.{5,60}?)\s*[:\.\-]{1,3}\s*([\d][\d\s]*[\d])\s*(?:FCFA|XOF|CFA)?\s*$',
        re.I
    )

    def _ctx_str() -> str:
        return " | ".join(ctx_parts[-3:]) if ctx_parts else ""

    def _add_row(section: str, libelle: str, v_raw: str, source: str = "TXT"):
        nonlocal rows, stats, seen
        libelle = _str(libelle)
        if not libelle or libelle.upper() in {u.upper() for u in UNIT_SKIP}:
            return
        # Filtre qualité libellé : rejeter les OCR garbled
        # 1. Au moins 3 lettres
        alpha_count = sum(1 for c in libelle if c.isalpha())
        if alpha_count < 3:
            stats["filtre_qualite"] += 1
            return
        # 2. Pas plus de 60% de non-alpha (hors espaces)
        non_alpha = sum(1 for c in libelle if not c.isalpha() and not c.isspace())
        if len(libelle) > 5 and non_alpha / len(libelle) > 0.6:
            stats["filtre_qualite"] += 1
            return
        # 3. Ne commence pas par un caractère de ponctuation ou structurel
        if libelle and libelle[0] in ':;|–—•►▶*#@!()[]{}<>':
            stats["filtre_qualite"] += 1
            return
        # 4. Longueur minimale raisonnable
        if len(libelle) < 4:
            stats["filtre_qualite"] += 1
            return
        brute, propre = clean_val(v_raw)
        if not propre:
            return
        lib_n = re.sub(r'\s+', ' ', libelle.lower())[:60]
        val_n = re.sub(r'\s+', ' ', propre.lower())[:30]
        key   = (lib_n, val_n)
        if key in seen:
            stats["dedup"] += 1
            return
        seen.add(key)
        rows.append({
            "banque":       banque,
            "annee":        annee,
            "semestre":     sem,
            "segment":      seg,
            "section":      section,
            "contexte":     _ctx_str(),
            "libelle":      libelle,
            "valeur_brute": brute,
            "valeur_propre": propre,
        })
        stats["ok"] += 1

    def _add_note(note_text: str):
        nonlocal rows, stats, seen
        text = _str(note_text)
        if len(text) < 15:
            return
        key = ("note", text.lower()[:50])
        if key in seen:
            return
        seen.add(key)
        rows.append({
            "banque":       banque,
            "annee":        annee,
            "semestre":     sem,
            "segment":      seg,
            "section":      "NOTE",
            "contexte":     _ctx_str(),
            "libelle":      "Note",
            "valeur_brute": text,
            "valeur_propre": text,
        })
        stats["ok"] += 1

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # ── Markdown headers → mise à jour du contexte ────────────────────────
        m_hdr = re.match(r'^(#{1,4})\s+(.+)', stripped)
        if m_hdr:
            level  = len(m_hdr.group(1))
            text   = m_hdr.group(2).strip()
            # Tronquer le stack au niveau courant
            ctx_parts[:] = ctx_parts[:level - 1]
            # Enlever le code section préfixe si présent (ex: "1.2 Frais" → "Frais")
            label = re.sub(r'^\d[\d\.]*\s+', '', text).strip() or text
            ctx_parts.append(label)
            in_table = False
            col_code = col_libelle = col_valeur = -1
            continue

        # ── Lignes de tableaux markdown ──────────────────────────────────────
        if stripped.startswith("|") and "|" in stripped[1:]:
            cells = [c.strip() for c in stripped.split("|")[1:-1]]

            # Séparateur (---) → ignorer
            if all(re.fullmatch(r'[-=:\s]+', c) or not c for c in cells):
                continue

            cells_up = [c.upper() for c in cells]

            # Détection ligne d'en-tête : contient LIBELLE, DESIGNATION, SERVICE…
            _LIB_KW  = {"LIBELLE", "LIBELLÉ", "DESIGNATION", "DÉSIGNATION",
                        "SERVICE", "OPÉRATION", "OPERATION", "PRESTATION"}
            _VAL_KW  = {"VALEUR", "MONTANT", "FCFA", "TARIF", "PRIX",
                        "FRAIS", "FCFA/HT", "FCFA / HT", "TAUX"}
            _CODE_KW = {"CODE", "N°", "NUM", "REF", "RÉFÉRENCE"}

            has_lib = any(any(k in c for k in _LIB_KW) for c in cells_up)
            has_val = any(any(k in c for k in _VAL_KW) for c in cells_up)

            if has_lib or has_val:
                col_code = col_libelle = col_valeur = -1
                for i, cu in enumerate(cells_up):
                    if col_code == -1 and any(k in cu for k in _CODE_KW):
                        col_code = i
                    elif col_libelle == -1 and any(k in cu for k in _LIB_KW):
                        col_libelle = i
                    elif col_valeur == -1 and any(k in cu for k in _VAL_KW):
                        col_valeur = i
                # Defaults si non détectés
                if col_libelle == -1:
                    col_libelle = 1 if len(cells) > 1 else 0
                if col_valeur == -1:
                    col_valeur = len(cells) - 1
                if col_valeur == col_libelle:
                    col_valeur = len(cells) - 1
                in_table = True
                continue

            # Ligne de données dans un tableau
            if in_table:
                if col_libelle < 0:
                    # Pas d'en-tête détecté : col0=code, col1=libelle, col-1=valeur
                    col_code    = 0 if len(cells) >= 3 else -1
                    col_libelle = 1 if len(cells) >= 2 else 0
                    col_valeur  = len(cells) - 1

                code    = cells[col_code]    if col_code    >= 0 and col_code    < len(cells) else ""
                libelle = cells[col_libelle] if col_libelle >= 0 and col_libelle < len(cells) else ""
                v_raw   = cells[col_valeur]  if col_valeur  >= 0 and col_valeur  < len(cells) else ""

                # Essayer aussi col -2 si v_raw vide (tableaux avec colonne unité)
                if not v_raw and len(cells) >= 3:
                    v_raw = cells[-2]

                if libelle and v_raw:
                    _add_row(code, libelle, v_raw)
                elif libelle and not v_raw and _is_header(code, libelle):
                    # En-tête de section dans le tableau → mise à jour contexte
                    label = re.sub(r'^\d[\d\.]*\s+', '', libelle).strip() or libelle
                    if label and label not in ctx_parts[-2:]:
                        ctx_parts.append(label)
                continue

            # Table non précédée d'en-tête : heuristique sur nb de colonnes
            # Si 3 colonnes et col-1 ressemble à un montant → traiter
            if len(cells) >= 2:
                v_raw = cells[-1]
                libelle = cells[1] if len(cells) >= 3 else cells[0]
                code    = cells[0] if len(cells) >= 3 else ""
                if libelle and v_raw and re.search(r'\d', v_raw):
                    _add_row(code, libelle, v_raw)
            continue

        # Fin de tableau
        in_table = False

        # ── Footnotes ─────────────────────────────────────────────────────────
        if _FOOTNOTE_RE.match(stripped):
            note = _FOOTNOTE_RE.sub("", stripped).strip()
            _add_note(note)
            continue

        # ── Lignes narratives avec montant inline ────────────────────────────
        m_inline = _INLINE_RE.match(stripped)
        if m_inline:
            lib_part = m_inline.group(1).strip()
            val_part = m_inline.group(2).strip()
            # Rejeter si lib_part trop courte ou ressemble à un code
            if len(lib_part) >= 8 and not re.fullmatch(r'[\d\.]+', lib_part):
                _add_row("", lib_part, val_part + " FCFA")

    return rows, dict(stats)


def _merge_cb_rows(xlsx_rows: list, txt_rows: list) -> list:
    """
    Fusionne lignes TXT dans les lignes XLSX :
    1. CORRIGE : si TXT a même libelle qu'une ligne XLSX mais une valeur différente,
       met à jour la valeur XLSX (véracité).
    2. AJOUTE   : si TXT a une lignes absente de XLSX (libelle+valeur inconnues),
       l'ajoute (exhaustivité).
    Retourne (xlsx_rows modifiées in-place, nouvelles lignes à ajouter).
    """
    if not txt_rows:
        return []

    def _lib_n(r):
        return re.sub(r'\s+', ' ', _str(r.get("libelle", "")).lower())[:60]

    def _val_n(r):
        return re.sub(r'\s+', ' ', _str(r.get("valeur_propre", "")).lower())[:30]

    # Index XLSX par libelle normalisé → liste d'indices (une libelle peut être dupliquée)
    xlsx_by_lib: dict[str, list[int]] = {}
    for i, r in enumerate(xlsx_rows):
        ln = _lib_n(r)
        xlsx_by_lib.setdefault(ln, []).append(i)

    xlsx_keys = set()
    for r in xlsx_rows:
        xlsx_keys.add((_lib_n(r), _val_n(r)))

    corrections = 0
    fills       = 0
    added = []
    added_keys = set()

    def _first_num(val: str) -> float | None:
        """Extrait le premier nombre d'une valeur monétaire pour comparaison."""
        m = re.search(r'(\d[\d\s]*\d|\d)', val.replace(',', '.'))
        if m:
            try:
                return float(m.group(0).replace(' ', ''))
            except ValueError:
                pass
        return None

    for txt_r in txt_rows:
        t_lib = _lib_n(txt_r)
        t_val = _val_n(txt_r)
        key   = (t_lib, t_val)

        if key in xlsx_keys or key in added_keys:
            continue

        if t_lib in xlsx_by_lib:
            # Même libelle mais valeur différente → correction SEULEMENT si les montants
            # sont proches (ratio ≤ 1.20) → correction d'un chiffre mal lu par pdfplumber.
            # Les grandes différences (ratio > 1.20) indiquent un désalignement TXT → ignorer.
            idx = xlsx_by_lib[t_lib][0]
            xlsx_val_propre = xlsx_rows[idx].get("valeur_propre", "")
            txt_val_propre  = txt_r.get("valeur_propre", "")

            # Cas 0 : valeur XLSX vide → remplir depuis TXT (pas de ratio, pas de risque)
            if not xlsx_val_propre.strip() and txt_val_propre.strip():
                old_val = _val_n(xlsx_rows[idx])   # "" en général
                xlsx_rows[idx]["valeur_brute"]  = txt_r.get("valeur_brute", "")
                xlsx_rows[idx]["valeur_propre"] = txt_val_propre
                xlsx_keys.discard((t_lib, old_val))
                xlsx_keys.add(key)
                fills += 1
                continue

            n_xlsx = _first_num(xlsx_val_propre)
            n_txt  = _first_num(txt_val_propre)

            if n_xlsx and n_txt and n_xlsx > 0:
                ratio = n_txt / n_xlsx
                if 0.84 <= ratio <= 1.20 and n_xlsx != n_txt:
                    # Montants proches mais différents → CORRECTION (ex. 15500→16500)
                    old_val = _val_n(xlsx_rows[idx])
                    xlsx_rows[idx]["valeur_brute"]  = txt_r.get("valeur_brute", "")
                    xlsx_rows[idx]["valeur_propre"] = txt_val_propre
                    xlsx_keys.discard((t_lib, old_val))
                    xlsx_keys.add(key)
                    corrections += 1
                    continue

            # Ratio hors plage (désalignement TXT) → traiter comme absent → AJOUT
            xlsx_keys.add(key)
            added_keys.add(key)
            added.append(txt_r)
        else:
            # Libelle absente de XLSX → AJOUT
            xlsx_keys.add(key)
            added_keys.add(key)
            added.append(txt_r)

    if fills:
        print(f"      [TXT→XLSX] {fills} valeur(s) vide(s) remplie(s) depuis TXT Docling")
    if corrections:
        print(f"      [TXT→XLSX] {corrections} valeur(s) corrigée(s) par TXT Docling (ratio ±20%)")

    return added


def _enrich_generic_labels(rows: list) -> list:
    """
    Enrichit les libellés sous-produit ambigus en leur suffixant le produit parent.

    Trois cas traités :
    1. Libellés explicitement génériques (regex _GENERIC_SUBITEM_RE) : "Première carte",
       "Seconde carte", etc.
    2. Libellés qui apparaissent sous PLUSIEURS parents différents dans le même fichier
       (détection automatique, 2 passes) : "Titulaire", "Co-titulaire", "Frais de dossier"...
    3. Fusion header+data par l'extraction : quand un libellé X apparaît à la fois
       comme en-tête (sans valeur) ET comme ligne de tarif (avec valeur), ET que la
       ligne suivante est une "Seconde/Troisième carte", la ligne de tarif est en réalité
       "Première carte" que l'extraction a collée au nom du produit parent.
       Ex : "Carte privative (ECLAIR)" 9 900 F → "Première carte (Carte privative (ECLAIR))"

    Règle commune :
    - last_named = dernier libellé non-générique et non-ambigu vu dans le fichier.
    - Si libellé générique/ambigu + valeur présente → ajouter " (last_named)".
    - Les en-têtes (valeur_propre vide) ne sont PAS enrichis mais PEUVENT servir
      de last_named.
    - Idempotent : un suffixe déjà présent ne sera pas ajouté à nouveau.
    """
    from collections import defaultdict

    # Passe 0 : détecter la fusion OCR "product header + Première carte"
    # L'extraction colle parfois le nom du produit parent avec "Première carte X F" :
    # PDF : "Carte privative (ECLAIR)  Première carte 9 900  Seconde carte 7 000"
    # Extraction : libellé="Carte privative (ECLAIR)" valeur=9900  +  libellé="Seconde carte" valeur=7000
    # Règle : si un libellé non-générique AVEC valeur est suivi (≤4 lignes) d'une
    # "Seconde/Troisième carte" avec valeur, c'est en réalité "Première carte (libellé)".
    # _passe0_originals : index → nom original, pour que Passe 2 utilise le nom
    # original comme last_named (et ne re-suffixe pas la ligne déjà traitée).
    result = list(rows)
    _passe0_originals: dict = {}
    for i, row in enumerate(result):
        lib = (row.get("libelle") or "").strip()
        vp  = (row.get("valeur_propre") or "").strip()
        if not vp or not lib or _GENERIC_SUBITEM_RE.match(lib):
            continue
        for j in range(i + 1, min(i + 5, len(result))):
            next_lib = (result[j].get("libelle") or "").strip()
            next_vp  = (result[j].get("valeur_propre") or "").strip()
            if next_lib and next_vp and _GENERIC_SUBITEM_RE.match(next_lib):
                _passe0_originals[i] = lib
                result[i] = {**row, "libelle": f"Première carte ({lib})"}
                break

    # Passe 1 : détecter les libellés avec valeur qui apparaissent sous 2+ parents distincts
    _lib_parents: dict = defaultdict(set)
    _last = ""
    for row in result:
        lib = (row.get("libelle") or "").strip()
        vp  = (row.get("valeur_propre") or "").strip()
        if lib and not _GENERIC_SUBITEM_RE.match(lib):
            _last = lib
        if vp and _last:
            _lib_parents[lib].add(_last)
    _multi_parent = {lib for lib, parents in _lib_parents.items() if len(parents) > 1}

    # Passe 2 : enrichir génériques + multi-parents
    # Les lignes déjà traitées par Passe 0 sont skippées ; leur nom ORIGINAL
    # est utilisé comme last_named pour les sous-libellés suivants (Seconde carte, etc.)
    last_named = ""
    for i, row in enumerate(result):
        lib = (row.get("libelle") or "").strip()
        vp  = (row.get("valeur_propre") or "").strip()

        if i in _passe0_originals:
            last_named = _passe0_originals[i]
            continue

        is_generic = bool(_GENERIC_SUBITEM_RE.match(lib)) or lib in _multi_parent
        if lib and not is_generic:
            last_named = lib

        if vp and is_generic and last_named:
            suffix = f" ({last_named})"
            if suffix.lower() not in lib.lower():
                result[i] = {**row, "libelle": lib + suffix}

    return result


# ══════════════════════════════════════════════════════════════════════════════

def process_cb() -> list[dict]:
    """Traite tous les XLSX CONDITIONS_BANQUES, enrichis par TXT Docling si disponible."""
    out_dir = OUT / "CONDITIONS_BANQUES"
    all_stats = []

    print("\n" + "="*70)
    print("  MODULE CB — CONDITIONS_BANQUES  (XLSX + TXT Docling)")
    print("="*70)

    for banque_dir in sorted(P2_CB.iterdir()):
        if not banque_dir.is_dir():
            continue
        banque = banque_dir.name
        print(f"\n  {banque}")

        for annee_dir in sorted(banque_dir.iterdir()):
            if not annee_dir.is_dir():
                continue
            annee = annee_dir.name

            xlsx_dir = _best_xlsx_dir_cb(banque, annee)
            stems = {x.stem for x in xlsx_dir.glob("*.xlsx")
                     if not x.stem.startswith("~$") and not x.stem.endswith("_clean")} \
                    if xlsx_dir.exists() else set()

            for stem in sorted(stems):
                sem, seg = _parse_stem(stem)
                src = xlsx_dir / (stem + ".xlsx")
                rows, stats = clean_cb_xlsx(src, banque, annee, sem, seg)

                # ── Enrichissement TXT ──────────────────────────────────────
                txt_path = _find_txt_cb(banque, annee, stem)
                n_txt = 0
                source_label = "XLSX"
                if txt_path:
                    txt_rows, _ = _parse_txt_cb(txt_path, banque, annee, sem, seg)
                    added = _merge_cb_rows(rows, txt_rows)
                    if added:
                        rows  += added
                        n_txt  = len(added)
                        source_label = "XLSX+TXT"

                dest_dir = out_dir / banque / annee
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / (stem + "_clean.xlsx")
                _write_flat_xlsx(rows, dest,
                    ["banque","annee","semestre","segment","section","contexte","libelle","valeur_brute","valeur_propre"])

                n_ok = stats.get("ok", 0)
                n_f  = stats.get("filtre", 0)
                txt_info = f" +{n_txt} TXT" if n_txt else ""
                total_raw = n_ok + n_f
                perte_pct = (n_f * 100 // total_raw) if total_raw > 0 else 0
                warn_perte = total_raw > 10 and perte_pct > 15
                print(f"    [{stem}] {n_ok} XLSX | {n_f} filtrées{txt_info} → {dest.name} [{source_label}]")
                if warn_perte:
                    print(f"    ⚠ PERTE ÉLEVÉE : {n_f}/{total_raw} lignes filtrées ({perte_pct}%) — vérifier clean_val / SECTION_RE")
                all_stats.append({"type":"CB","banque":banque,"annee":annee,
                                   "fichier":stem,"ok":n_ok + n_txt,"filtre":n_f,
                                   "perte_pct":perte_pct,"warn_perte":warn_perte,
                                   "source":source_label})

    return all_stats


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 2 — ETATS_FINANCIERS
# ══════════════════════════════════════════════════════════════════════════════

_FAKE_YEAR_LABELS = re.compile(
    r'^(valeur|variation|var\.|%|ecart|écart|évolution|evolution|montant|solde)$', re.I
)


_YEAR_RANGE = (2015, 2030)  # plage valide pour les rapports bancaires du projet


def _is_year_cell(cell: str) -> bool:
    """
    True si la cellule EST un label d'année (année seule, date, abrév. mois+année).
    False si l'année apparaît comme SUFFIXE d'un nombre : '12029' n'est PAS '2029'.
    Règle : le caractère précédant le match YEAR_RE ne doit pas être un chiffre.
    """
    c = cell.strip()
    if not c:
        return False
    m = YEAR_RE.search(c)
    if not m:
        return False
    start = m.start()
    if start > 0 and c[start - 1].isdigit():
        return False  # '12029' → '2029' est un faux positif
    return True


def _normalize_year_label(label: str) -> str:
    """
    Normalise tout label d'année vers 'AAAA' (4 chiffres).
    '31/12/2022' → '2022'  |  'Dec.-22' → '2022'  |  'Déc-23' → '2023'
    'Déc 202 4' → '2024'  (espace OCR collé)  |  '2023' → '2023'
    RÈGLE OBLIGATOIRE : annee_label est toujours au format AAAA.
    Retourne label original si aucune année valide trouvée.
    """
    s = label.strip()
    # Coller les chiffres séparés par espaces (OCR fragmente parfois "2024" en "202 4")
    s_clean = re.sub(r'(\d)\s+(\d)', r'\1\2', s)
    s_clean = re.sub(r'(\d)\s+(\d)', r'\1\2', s_clean)  # 2e passe pour "2 0 2 4"
    # Priorité 1 : année 4 chiffres (20xx ou 19xx)
    m4 = re.search(r'(20\d{2}|19\d{2})', s_clean)
    if m4:
        return m4.group(1)
    # Priorité 2 : deux chiffres avec préfixe mois (Dec.-22, Déc-23, juin-24…)
    m2 = re.search(
        r'(?:jan|f[eé]v|feb|mar|avr|apr|mai|may|jun|juin|juil?|ao[uû]|aug|sep|oct|nov|d[eé]c)'
        r'\.?\s*[-]?\s*(\d{2})\b',
        s_clean, re.I
    )
    if m2:
        yy = int(m2.group(1))
        return str(2000 + yy if yy < 50 else 1900 + yy)
    return s


def _detect_year_cols(ws) -> dict[int, str]:
    """Cherche la ligne d'en-tête avec des années → {col_idx: label_annee}.
    Scrute jusqu'à la ligne 15 (certains tableaux ont des titres longs avant
    les en-têtes de colonnes). Filtre les colonnes 'Valeur', 'Variations', '%'.
    annee_label est TOUJOURS normalisé en 'AAAA' via _normalize_year_label.
    RÈGLE : col 0 est TOUJOURS un libellé, jamais une année (évite les faux
    positifs sur les titres type "BILAN AU 31/12/2025"). Exige ≥ 2 années pour
    valider une ligne d'en-tête (protège contre les titres mono-année).
    """
    for row in ws.iter_rows(max_row=15, values_only=True):
        found = {}
        for i, cell in enumerate(row):
            if i == 0:  # col 0 = libellé, jamais une année
                continue
            if cell:
                label = _str(cell).strip()
                if not label or _FAKE_YEAR_LABELS.match(label):
                    continue
                m = YEAR_RE.search(label)
                if m and _is_year_cell(label):
                    norm = _normalize_year_label(m.group().strip())
                    try:
                        if _YEAR_RANGE[0] <= int(norm) <= _YEAR_RANGE[1]:
                            found[i] = norm
                    except (ValueError, TypeError):
                        pass  # label non convertible en entier → ignorer
        if len(found) >= 1:
            return found
    return {}





_UNITE_RE = re.compile(
    r'(millions?|milliards?|milliers?)\s*(?:de\s*)?(?:FCFA|CFA|XOF|francs?)', re.I
)

def _detect_unite(ws) -> str:
    """Détecte l'unité des montants depuis les premières lignes de la feuille.
    Passe 1 : 30 premières lignes, cellules courtes (<= 35 chars).
    Passe 2 : toute la feuille si pas trouvé en passe 1.
    Émet un avertissement si aucune unité détectée — cela signale un problème
    dans le PDF source (en-tête absent ou mal extrait).
    """
    def _match_unite(label: str) -> str:
        m = _UNITE_RE.search(label)
        if m:
            unit = m.group(1).lower()
            if 'milliard' in unit:
                return 'milliards FCFA'
            if 'millier' in unit:
                return 'milliers FCFA'
            return 'millions FCFA'
        return ''

    # Passe 1 : 30 premières lignes, cellules courtes
    for row in ws.iter_rows(max_row=30, values_only=True):
        for cell in row:
            if cell:
                label = _str(cell).strip()
                if len(label) > 35:
                    continue
                u = _match_unite(label)
                if u:
                    return u

    # Passe 2 : toute la feuille (texte narratif inclus)
    for row in ws.iter_rows(values_only=True):
        for cell in row:
            if cell:
                label = _str(cell).strip()
                u = _match_unite(label)
                if u:
                    return u

    return ''


def _is_clean_number(v: str) -> bool:
    """True si v est un nombre simple (montant financier unique)."""
    v = v.strip()
    if not v or v == "0":
        return True
    # Supprimer espaces milliers provisoirement pour tester
    test = re.sub(r'(\d) (\d)', r'\1\2', v)
    test = re.sub(r'(\d) (\d)', r'\1\2', test)
    return bool(re.fullmatch(r'[-−]?\s*[\d\s,\.]+', test))


def _extract_ef_xlsx_rows(path: Path, banque: str, stem: str) -> tuple[list, dict]:
    """
    Extrait les données EF depuis un XLSX large → format tall.
    Gère : tableau simple | double côté (ACTIF/PASSIF) | multi-lignes.
    Déduplication inter-feuilles : même (libelle, annee_label) → une seule ligne.
    """
    try:
        from openpyxl import load_workbook
        wb = load_workbook(path, data_only=True)
    except Exception as e:
        return [], {"error": str(e)}

    rows, stats = [], defaultdict(int)
    seen = set()  # (libelle_norm, annee_label) — évite doublons T1/T3/T5

    for ws in wb.worksheets:
        # Détecter format mono-colonne : données OCR non structurées (tout en colonne A)
        # Ce format ne peut pas être parsé correctement → ignorer avec avertissement
        if ws.max_column == 1:
            print(f"  [WARN] {path.name} / {ws.title} : format mono-colonne (données OCR concaténées) → feuille ignorée")
            continue

        year_cols = _detect_year_cols(ws)
        unite = _detect_unite(ws)

        if not unite:
            print(f"  [WARN] {path.name} / {ws.title} : aucune unité détectée dans le fichier source — vérifier le PDF")

        # Table double-côté (ACTIF col 0-2, PASSIF col 3-5) : SGCI T3, BICICI T0
        has_right = ws.max_column >= 5 and any(
            ws.cell(r, 4).value for r in range(1, min(ws.max_row, 6))
        )

        # Déterminer la colonne du libellé : colonne juste avant la 1ère année
        # Format "Libellé | Année1 | Année2" → label_col=0
        # Format "Code | Libellé | Année1 | Année2" → label_col=1 (min_year=2)
        label_col = (min(year_cols.keys()) - 1) if year_cols and min(year_cols.keys()) >= 2 else 0

        for row in ws.iter_rows(values_only=True):
            _extract_ef_row(row, label_col, year_cols, ws.title, banque, stem, unite, seen, rows, stats)
            if has_right and ws.max_column >= 6:
                right = list(row[3:])
                right_year_cols = {k-3: v for k, v in year_cols.items() if k >= 3}
                r_label_col = (min(right_year_cols.keys()) - 1) if right_year_cols and min(right_year_cols.keys()) >= 2 else 0
                _extract_ef_row(right, r_label_col, right_year_cols, ws.title, banque, stem, unite, seen, rows, stats)

    wb.close()
    return rows, dict(stats)


def _extract_ef_row(row, label_col: int, year_cols: dict,
                    sheet: str, banque: str, stem: str, unite: str,
                    seen: set, rows: list, stats: dict):
    """Extrait une ligne EF vers le format tall.
    `seen` déduplique (libelle_norm, annee_label) pour éviter doublons T1/T3/T5.
    """
    if not row:
        return
    libelle_raw = _str(row[label_col]) if label_col < len(row) else ""
    if not libelle_raw:
        return
    lb, lp = clean_val(libelle_raw)
    if not lp:
        stats["skip_libelle"] += 1
        return
    # RÈGLE : codes courts ambigus (A1, P2, HB1…) ne sont pas des libellés
    if _is_ambiguous_code(lp):
        stats["skip_libelle"] += 1
        return

    # Rejeter les libellés qui contiennent "CFA" ou "FCFA" — signe d'un fragment de
    # phrase OCR (ex: "francs CFA, portant son capital social à") pas d'un indicateur
    if re.search(r'\bFCFA\b|\bCFA\b', lp, re.I):
        stats["skip_libelle"] += 1
        return

    lib_norm = re.sub(r'\s+', ' ', lp.strip().lower())

    def _norm_year(label: str) -> str:
        """Normalise pour déduplication : 'Déc-22' == 'Dec.-22' == 'dec22'."""
        s = unicodedata.normalize('NFD', label.strip().lower())
        s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
        return re.sub(r'[^\w]', '', s)  # garde lettres+chiffres uniquement

    if year_cols:
        for col_idx, year_label in year_cols.items():
            if col_idx < len(row) and row[col_idx] is not None:
                v_raw = _str(row[col_idx])
                # Ne découper que sur les vrais retours à la ligne (cellule multi-ligne)
                candidates = v_raw.splitlines() if "\n" in v_raw else [v_raw]
                for candidate in candidates:
                    candidate = candidate.strip()
                    if not candidate:
                        continue
                    brute, propre = clean_val(candidate)
                    if propre and _is_clean_number(propre):
                        key = (lib_norm, _norm_year(year_label))
                        if key in seen:
                            stats["dedup"] += 1
                            break
                        seen.add(key)
                        rows.append({
                            "banque": banque, "fichier": stem, "feuille": sheet,
                            "libelle": lp, "annee_label": year_label, "unite": unite,
                            "valeur_brute": brute, "valeur_propre": normalize_number(propre),
                        })
                        stats["ok"] += 1
                        break
    else:
        # Pas d'en-tête année trouvé : essayer cols 1, 2, 3
        for ci in range(1, min(len(row), 5)):
            if row[ci] is not None:
                brute, propre = clean_val(_str(row[ci]))
                if propre and _is_clean_number(propre):
                    key = (lib_norm, _norm_year(f"col{ci}"))
                    if key in seen:
                        stats["dedup"] += 1
                        continue
                    seen.add(key)
                    rows.append({
                        "banque": banque, "fichier": stem, "feuille": sheet,
                        "libelle": lp, "annee_label": f"col{ci}", "unite": unite,
                        "valeur_brute": brute, "valeur_propre": normalize_number(propre),
                    })
                    stats["ok"] += 1


def _extract_ef_txt_rows(txt_path: Path, banque: str, stem: str) -> tuple[list, dict]:
    """
    Parse un TXT Docling (DATA/PRETRAITES/ETATS_FINANCIERS/) pour extraire des données EF.
    Cherche les tableaux markdown et les lignes 'libellé : valeur'.
    Détecte l'unité depuis le texte (Millions / Milliards / Milliers de francs CFA).
    """
    try:
        raw = txt_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [], {"error": str(e)}

    # Détecter l'unité dans les premières lignes du TXT (même règle que _detect_unite XLSX)
    # Ignorer les lignes narratives > 35 chars pour éviter de capter "X milliards dans une phrase"
    global_unit = ""
    for _line in raw[:3000].splitlines():
        _label = _line.strip()
        if _label and len(_label) <= 35:
            _mu = _UNITE_RE.search(_label)
            if _mu:
                _u = _mu.group(1).lower()
                global_unit = ('milliards FCFA' if 'milliard' in _u
                               else 'milliers FCFA' if 'millier' in _u
                               else 'millions FCFA')
                break

    # Supprimer l'en-tête pipeline
    sep = raw.find("[PAGE ")
    if sep > 0:
        raw = raw[sep:]

    rows, stats = [], defaultdict(int)
    seen = set()  # (libelle_norm, annee_label) — évite doublons pdfminer/docling
    current_page = "p1"
    current_year = None
    table_year_cols: dict[int, str] = {}  # col_idx → year_label pour table markdown en cours
    table_libelle_col: int = 0           # col_idx du libellé dans la table courante

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        # Détecter page → réinitialise l'état de la table
        m = re.match(r'\[PAGE\s+(\d+)\]', line)
        if m:
            current_page = f"p{m.group(1)}"
            table_year_cols = {}
            table_libelle_col = 0
            continue

        # Mise à jour dynamique de l'unité depuis les lignes texte standalone
        # CRITIQUE SIB : "En Millions de FCFA" apparaît APRES "Données (en Milliards FCFA)"
        # → les tableaux ACTIF/PASSIF/HB/RESULTAT sont en millions, pas milliards
        if not line.startswith("|") and len(line) <= 40:
            mu_dyn = _UNITE_RE.search(line)
            if mu_dyn:
                _u_dyn = mu_dyn.group(1).lower()
                global_unit = ('milliards FCFA' if 'milliard' in _u_dyn
                               else 'milliers FCFA' if 'millier' in _u_dyn
                               else 'millions FCFA')
                continue

        # ── Tableaux markdown Docling (format | libellé | val1 | val2 |) ────────
        if line.startswith("|") and "|" in line[1:]:
            # Découper en gardant l'alignement des colonnes (cellules vides incluses)
            all_cells = line.split("|")
            cells = [c.strip() for c in all_cells[1:-1]]  # ignorer le "" avant/après

            # Ligne séparateur (---, ===) → ignorer
            if all(re.fullmatch(r'[-=\s]+', c) or not c for c in cells):
                continue

            # Ligne en-tête : AU MOINS UNE cellule après la 1ère est un vrai label d'année
            # (couvre : 1ère cellule vide comme BNI, ou descriptive comme SGCI)
            # _is_year_cell évite les faux positifs comme '12029' → '2029'
            non_empty_rest = [c for c in cells[1:] if c]
            has_year_in_rest = any(_is_year_cell(c) for c in non_empty_rest)
            if has_year_in_rest:
                table_year_cols = {}
                for i, c in enumerate(cells[1:], start=1):
                    if c and _is_year_cell(c):
                        norm = _normalize_year_label(c)
                        try:
                            if _YEAR_RANGE[0] <= int(norm) <= _YEAR_RANGE[1]:
                                table_year_cols[i] = norm
                        except (ValueError, TypeError):
                            pass
                # Colonne du libellé = colonne juste avant la 1ère année
                # Format "Libellé | Année1 | Année2" → col 0
                # Format "Code | Libellé | Année1 | Année2" → col 1 (min_year=2)
                if table_year_cols:
                    min_yr_col = min(table_year_cols.keys())
                    table_libelle_col = min_yr_col - 1  # 0 ou 1 selon le format
                else:
                    table_libelle_col = 0
                # Si la cellule du libellé contient une mention d'unité, la capturer
                if cells and cells[0]:
                    mu0 = _UNITE_RE.search(cells[0])
                    if mu0:
                        u = mu0.group(1).lower()
                        global_unit = ('milliards FCFA' if 'milliard' in u
                                       else 'milliers FCFA' if 'millier' in u
                                       else 'millions FCFA')
                continue

            # Ligne unité (toutes valeurs = mentions d'unité) → mise à jour global_unit
            if non_empty_rest and all(_UNITE_RE.search(c) for c in non_empty_rest):
                for c in non_empty_rest:
                    mu = _UNITE_RE.search(c)
                    if mu:
                        u = mu.group(1).lower()
                        global_unit = ('milliards FCFA' if 'milliard' in u
                                       else 'milliers FCFA' if 'millier' in u
                                       else 'millions FCFA')
                        break
                continue

            # Ligne de données
            if not cells:
                continue
            libelle_raw = cells[table_libelle_col] if table_libelle_col < len(cells) else cells[0]
            if not libelle_raw:
                continue
            lb, lp = clean_val(libelle_raw)
            if not lp:
                continue
            # RÈGLE : codes courts ambigus (A1, P2, HB1…) ne sont pas des libellés
            if _is_ambiguous_code(lp):
                continue
            # Rejeter les fragments OCR contenant CFA/FCFA dans le libellé
            if re.search(r'\bFCFA\b|\bCFA\b', lp, re.I):
                continue
            lib_norm = re.sub(r'\s+', ' ', lp.strip().lower())

            if table_year_cols:
                for col_i, year_label in table_year_cols.items():
                    if col_i < len(cells) and cells[col_i]:
                        brute, propre = clean_val(cells[col_i])
                        if propre and _is_clean_number(propre):
                            key = (lib_norm, year_label)
                            if key in seen:
                                stats["dedup"] = stats.get("dedup", 0) + 1
                                continue
                            seen.add(key)
                            rows.append({
                                "banque": banque, "fichier": stem, "feuille": current_page,
                                "libelle": lp, "annee_label": year_label,
                                "unite": global_unit, "valeur_brute": brute,
                                "valeur_propre": normalize_number(propre),
                            })
                            stats["ok"] += 1
            else:
                for val_cell in cells[1:]:
                    if not val_cell:
                        continue
                    brute, propre = clean_val(val_cell)
                    if propre and _is_clean_number(propre):
                        key = (lib_norm, current_year or "?")
                        if key in seen:
                            stats["dedup"] = stats.get("dedup", 0) + 1
                            continue
                        seen.add(key)
                        rows.append({
                            "banque": banque, "fichier": stem, "feuille": current_page,
                            "libelle": lp, "annee_label": current_year or "?",
                            "unite": global_unit, "valeur_brute": brute,
                            "valeur_propre": normalize_number(propre),
                        })
                        stats["ok"] += 1
            continue

        # ── Détecter année seule (hors tableau) → normalisée AAAA ───────────────
        ym = YEAR_RE.search(line)
        if ym and not re.search(r'[^\d\s/]', line.replace(ym.group(), '')):
            norm_y = _normalize_year_label(ym.group().strip())
            try:
                if _YEAR_RANGE[0] <= int(norm_y) <= _YEAR_RANGE[1]:
                    current_year = norm_y
            except (ValueError, TypeError):
                pass
            continue

        # ── Ligne texte : "LIBELLE    1 234    5 678" ────────────────────────────
        WORD_PAT = r"^([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 \(\)\-',\.]{3,50}?)"
        m2 = re.match(
            WORD_PAT + r'\s{2,}([\d\s,\.]+(?:\s{2,}[\d\s,\.]+)*)$',
            line
        )
        if m2:
            libelle = m2.group(1).strip()
            # Rejeter les fragments OCR contenant CFA/FCFA (ex: "francs CFA, portant...")
            if re.search(r'\bFCFA\b|\bCFA\b', libelle, re.I):
                continue
            vals_part = m2.group(2)
            vals = re.split(r'\s{2,}', vals_part.strip())
            lib_norm2 = re.sub(r'\s+', ' ', libelle.strip().lower())
            for val in vals:
                brute, propre = clean_val(val)
                if propre and _is_clean_number(propre):
                    key2 = (lib_norm2, current_year or "?")
                    if key2 in seen:
                        stats["dedup"] = stats.get("dedup", 0) + 1
                        continue
                    seen.add(key2)
                    rows.append({
                        "banque": banque, "fichier": stem, "feuille": current_page,
                        "libelle": libelle, "annee_label": current_year or "?",
                        "unite": global_unit, "valeur_brute": brute,
                        "valeur_propre": normalize_number(propre),
                    })
                    stats["ok"] += 1

    return rows, dict(stats)


def _convert_fcfa_to_millions(propre: str) -> str:
    """
    RÈGLE BNI (CRITIQUE) : BNI stocke les montants en FCFA brut.
    Divise par 1 000 000 pour aligner toutes les banques en millions FCFA.
    '15234567890' → '15234.568'  |  '-5000000' → '-5'
    """
    try:
        num_str = propre.strip()
        neg = num_str.startswith('-') or num_str.startswith('−')
        if neg:
            num_str = num_str[1:]
        num_str = num_str.replace(' ', '').replace(' ', '').replace(',', '.')
        val = float(num_str) / 1_000_000
        if neg:
            val = -val
        if val == int(val):
            return str(int(val))
        return f"{val:.3f}".rstrip('0').rstrip('.')
    except (ValueError, TypeError):
        return propre


def _is_ambiguous_code(libelle: str) -> bool:
    """Retourne True si le libellé est un code court ambigu (A1, P2, HB1, C10…).
    RÈGLE : 'SI AMBIGUE NE MET PAS' — rejeter ces codes comme libellés."""
    return bool(_AMBIGUOUS_CODE_RE.match(libelle.strip()))


def _repair_ef_missing_an1(dest_dir: Path, banque: str) -> None:
    """
    Si AN1_clean.xlsx a moins de 30 lignes (extraction OCR insuffisante),
    récupère les données de l'année la plus ancienne présente dans AN2_clean.xlsx
    et les écrit dans AN1_clean.xlsx.
    Règle métier : les rapports multi-années (AN2=N+N-1) contiennent N-1 = données AN1.
    Automatique et reproductible : si AN2 évolue plus tard, AN1 reste inchangé.
    """
    an1_path = dest_dir / "AN1_clean.xlsx"
    an2_path = dest_dir / "AN2_clean.xlsx"
    if not an2_path.exists():
        return

    # Compter lignes AN1 existant
    n_an1 = 0
    if an1_path.exists():
        try:
            wb1 = openpyxl.load_workbook(an1_path, read_only=True, data_only=True)
            n_an1 = max(0, wb1.active.max_row - 1)
            wb1.close()
        except Exception:
            n_an1 = 0

    if n_an1 >= 30:
        return  # AN1 correct, rien à faire

    # Lire AN2
    try:
        wb2 = openpyxl.load_workbook(an2_path, read_only=True, data_only=True)
        ws2 = wb2.active
        headers2 = None
        an2_data = []
        for row in ws2.iter_rows(values_only=True):
            if headers2 is None:
                headers2 = [str(h).strip() if h else "" for h in row]
                continue
            an2_data.append(dict(zip(headers2, row)))
        wb2.close()
    except Exception:
        return

    # Trouver l'année la plus ancienne dans AN2
    years = set()
    for r in an2_data:
        y = str(r.get("Annee_label") or "").strip()
        if y.isdigit():
            years.add(int(y))
    if not years:
        return
    oldest_year = str(min(years))

    repair_rows = [
        {"banque": banque, "fichier": "AN1",
         "libelle":       str(r.get("Libelle")       or "").strip(),
         "annee_label":   str(r.get("Annee_label")   or "").strip(),
         "unite":         str(r.get("Unite")          or "").strip(),
         "valeur_brute":  str(r.get("Valeur_brute")  or "").strip(),
         "valeur_propre": str(r.get("Valeur_propre") or "").strip()}
        for r in an2_data
        if str(r.get("Annee_label") or "").strip() == oldest_year
        and str(r.get("Libelle") or "").strip()
    ]
    if not repair_rows:
        return

    print(f"    [REPAIR AN1] {banque} : {n_an1} lignes → copie {len(repair_rows)} lignes ({oldest_year}) depuis AN2")
    _write_flat_xlsx(repair_rows, an1_path,
        ["banque","fichier","libelle","annee_label","unite","valeur_brute","valeur_propre"])


def process_ef() -> list[dict]:
    """Traite tous les fichiers ETATS_FINANCIERS (XLSX prioritaire, TXT fallback)."""
    out_dir = OUT / "ETATS_FINANCIERS"
    all_stats = []

    print("\n" + "="*70)
    print("  MODULE EF — ETATS_FINANCIERS")
    print("="*70)

    ef_txt_dir = SRC_EF

    for banque_dir in sorted(SRC_EF.iterdir()):
        if not banque_dir.is_dir():
            continue
        banque = banque_dir.name
        print(f"\n  {banque}")

        # Collecter tous les stems EF (XLSX + TXT)
        stems: dict[str, dict] = {}  # stem → {"xlsx": Path, "txt": Path}

        for p in banque_dir.glob("*.xlsx"):
            stem = p.stem
            if stem.startswith("~$"):
                continue
            # Préférer _DOCLING si disponible et non vide
            if stem.endswith("_DOCLING"):
                base = stem.replace("_DOCLING", "")
                if base not in stems:
                    stems[base] = {}
                if p.stat().st_size > 5000:
                    stems[base]["xlsx_docling"] = p
            else:
                if stem not in stems:
                    stems[stem] = {}
                stems[stem]["xlsx"] = p

        txt_bank = ef_txt_dir / banque
        if txt_bank.exists():
            for p in txt_bank.glob("*.txt"):
                stem = p.stem
                if stem not in stems:
                    stems[stem] = {}
                if p.stat().st_size > 1000:
                    stems[stem]["txt"] = p

        for stem, sources in sorted(stems.items()):
            rows, stats, src_label = [], {}, "?"

            # Choix de la source
            xlsx_src = sources.get("xlsx_docling") or sources.get("xlsx")
            txt_src  = sources.get("txt")

            if xlsx_src and xlsx_src.stat().st_size > 3000:
                rows, stats = _extract_ef_xlsx_rows(xlsx_src, banque, stem)
                src_label = "XLSX"
                # Si XLSX insuffisant (<30 lignes propres) → compléter avec TXT
                if len(rows) < 30 and txt_src:
                    txt_rows, txt_stats = _extract_ef_txt_rows(txt_src, banque, stem)
                    if len(txt_rows) > len(rows):
                        rows, stats, src_label = txt_rows, txt_stats, "TXT"
                    else:
                        rows += txt_rows
                        src_label = "XLSX+TXT"
            elif txt_src:
                rows, stats = _extract_ef_txt_rows(txt_src, banque, stem)
                src_label = "TXT"

            # RÈGLE BNI (CRITIQUE) : montants en FCFA brut → convertir en millions FCFA
            # Ne convertir que les lignes sans unité détectée (= FCFA brut non déclaré)
            if banque == "BNI":
                for r in rows:
                    if not r.get("unite"):
                        r["valeur_propre"] = _convert_fcfa_to_millions(r["valeur_propre"])
                        r["valeur_brute"]  = r["valeur_propre"]
                        r["unite"] = "millions FCFA"

            if not rows:
                print(f"    [{stem}] AUCUNE DONNEE ({src_label})")
                all_stats.append({"type":"EF","banque":banque,"annee":"-","fichier":stem,
                                   "ok":0,"filtre":0,"source":src_label})
                continue

            dest_dir = out_dir / banque
            dest_dir.mkdir(parents=True, exist_ok=True)

            # ── Fichier ANS (multi-années) → éclater en ANx ─────────────────────
            # Règle : si stem="ANS", regrouper les lignes par année et écrire un
            # fichier séparé par année : AN1=plus ancienne, AN2=suivante, etc.
            # Si demain BACI ajoute 2024, on obtiendra AN4 automatiquement.
            if stem.upper() == "ANS":
                year_groups: dict[str, list] = defaultdict(list)
                for r in rows:
                    year_groups[r.get("annee_label", "?")].append(r)
                sorted_years = sorted(
                    year_groups.keys(),
                    key=lambda y: int(y) if str(y).isdigit() else 9999
                )
                for i, year in enumerate(sorted_years, 1):
                    an_stem   = f"AN{i}"
                    year_rows = [{**r, "fichier": an_stem} for r in year_groups[year]]
                    dest      = dest_dir / (an_stem + "_clean.xlsx")
                    _write_flat_xlsx(year_rows, dest,
                        ["banque","fichier","libelle","annee_label","unite","valeur_brute","valeur_propre"])
                    n_ok = len(year_rows)
                    print(f"    [{stem}→{an_stem}] {year} : {n_ok} lignes → {dest.name}")
                    all_stats.append({"type":"EF","banque":banque,"annee":year,"fichier":an_stem,
                                       "ok":n_ok,"filtre":stats.get("skip_libelle",0),"source":src_label})
                # Supprimer l'ancien ANS_clean.xlsx s'il existe (résidu d'un run précédent)
                old_clean = dest_dir / (stem + "_clean.xlsx")
                if old_clean.exists():
                    old_clean.unlink()
                    print(f"    [CLEANUP] {old_clean.name} supprimé")

            else:
                # Comportement normal : un fichier → un _clean.xlsx
                dest = dest_dir / (stem + "_clean.xlsx")
                _write_flat_xlsx(rows, dest,
                    ["banque","fichier","libelle","annee_label","unite","valeur_brute","valeur_propre"])
                n_ok = stats.get("ok", len(rows))
                print(f"    [{stem}] {n_ok} lignes propres ({src_label}) → {dest.name}")
                all_stats.append({"type":"EF","banque":banque,"annee":"-","fichier":stem,
                                   "ok":n_ok,"filtre":stats.get("skip_libelle",0),"source":src_label})

        # Réparer AN1 si extraction insuffisante (ex: SIB AN1 OCR pauvre → copie depuis AN2)
        _repair_ef_missing_an1(out_dir / banque, banque)

    return all_stats


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 3 — REGLEMENTATIONS
# ══════════════════════════════════════════════════════════════════════════════

def _remove_vertical_text(lines: list[str]) -> list[str]:
    """
    Supprime les séquences de texte vertical (1 lettre/ligne) que Docling extrait
    des PDF officiels qui ont du texte imprimé verticalement dans les marges.
    Exemple : S / E / R / V / I / C / E / S → supprimé.
    Règle : 4+ lignes consécutives contenant chacune exactement 1 lettre.
    """
    result = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if len(s) == 1 and s.isalpha():
            j = i + 1
            while j < len(lines) and len(lines[j].strip()) == 1 and lines[j].strip().isalpha():
                j += 1
            if j - i >= 4:
                i = j
                continue
        result.append(lines[i])
        i += 1
    return result


def _clean_regl_txt(raw: str) -> str:
    """Nettoie un TXT de réglementation."""
    lines = raw.splitlines()
    clean = []
    in_header = True

    for line in lines:
        # Supprimer l'en-tête pipeline
        if in_header:
            if line.strip().startswith("[PAGE "):
                in_header = False
            else:
                continue

        stripped = line.rstrip()

        # Supprimer lignes de métriques
        if re.match(r'\s*\[METRICS\s', stripped):
            continue
        if re.match(r'\s*\[PAGE\s+\d+\]', stripped):
            clean.append(stripped)
            continue

        # Supprimer les tirets de césure en fin de ligne
        if stripped.endswith("-"):
            stripped = stripped[:-1]

        # Normaliser les espaces multiples internes (mais garder les indentations)
        # Ne pas toucher aux indentations (tableaux, listes)
        lead = len(stripped) - len(stripped.lstrip())
        indent = stripped[:lead]
        content = " ".join(stripped[lead:].split())
        clean.append(indent + content)

    # Supprimer les textes verticaux (1 lettre/ligne = marges PDF officiels)
    clean = _remove_vertical_text(clean)

    # Supprimer les lignes vides consécutives (max 1)
    result = []
    prev_empty = False
    for l in clean:
        if not l.strip():
            if not prev_empty:
                result.append("")
            prev_empty = True
        else:
            result.append(l)
            prev_empty = False

    return "\n".join(result)


def process_regl() -> list[dict]:
    """Nettoie les TXT de réglementation."""
    regl_dir = BASE / "DATA" / "DONNEES_EXTRAITES" / "REGLEMENTATION"
    out_dir  = OUT / "REGLEMENTATION"
    all_stats = []

    print("\n" + "="*70)
    print("  MODULE REGL — REGLEMENTATIONS")
    print("="*70)

    if not regl_dir.exists():
        print("  (dossier REGLEMENTATION introuvable dans DATA/PRETRAITES)")
        return all_stats

    for txt_path in sorted(regl_dir.glob("*.txt")):
        if txt_path.stem.endswith("_clean"):
            continue
        raw = txt_path.read_text(encoding="utf-8", errors="replace")
        clean = _clean_regl_txt(raw)
        chars_before = len(raw)
        chars_after  = len(clean)
        pct = round((1 - chars_after / chars_before) * 100, 1) if chars_before else 0

        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / (txt_path.stem + "_clean.txt")
        dest.write_text(clean, encoding="utf-8")
        print(f"  [{txt_path.name}] {chars_before:,} → {chars_after:,} chars (-{pct}%) → {dest.name}")
        all_stats.append({"type":"REGL","banque":"-","annee":"-","fichier":txt_path.stem,
                           "ok":chars_after,"filtre":chars_before - chars_after,"source":"TXT"})

    return all_stats


# ══════════════════════════════════════════════════════════════════════════════
# UTILITAIRES EXCEL
# ══════════════════════════════════════════════════════════════════════════════

HDR_FILL  = PatternFill("solid", fgColor="1F3864")
HDR_FONT  = Font(color="FFFFFF", bold=True, size=9)
ALT_FILL  = PatternFill("solid", fgColor="EBF5FB")
TYPE_COLORS = {
    "CB":   "D6EAF8",
    "EF":   "D5F5E3",
    "REGL": "FEF9E7",
}
BANK_COLORS = {
    "SGCI":"D6EAF8","BNI":"D5F5E3","BICICI":"FDEBD0",
    "NSIA":"E8DAEF","BACI":"FADBD8","SIB":"D5EEF5","ECOBANK":"FEF9E7",
}


def _write_flat_xlsx(rows: list[dict], path: Path, columns: list[str]):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Données"
    ws.row_dimensions[1].height = 22

    for col, h in enumerate(columns, 1):
        c = ws.cell(1, col, h.capitalize())
        c.fill = HDR_FILL
        c.font = HDR_FONT
        c.alignment = Alignment(horizontal="center")

    for r_idx, row in enumerate(rows, 2):
        fill = ALT_FILL if r_idx % 2 == 0 else None
        for c_idx, key in enumerate(columns, 1):
            cell = ws.cell(r_idx, c_idx, row.get(key, ""))
            if fill:
                cell.fill = fill
            cell.alignment = Alignment(wrap_text=False)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(rows)+1}"
    for i in range(1, len(columns) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 18
    wb.save(path)


def write_rapport(all_stats: list[dict]):
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "rapport.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rapport"
    ws.row_dimensions[1].height = 22

    COLS = ["Type", "Banque", "Fichier", "Source", "Lignes propres", "Filtrées", "Qualité", "Alerte perte"]
    for col, h in enumerate(COLS, 1):
        c = ws.cell(1, col, h)
        c.fill = HDR_FILL
        c.font = HDR_FONT
        c.alignment = Alignment(horizontal="center")

    WARN_FILL = PatternFill("solid", fgColor="FFCCCC")
    for r_idx, s in enumerate(sorted(all_stats, key=lambda x: (x["type"], x["banque"])), 2):
        total = s["ok"] + s.get("filtre", 0)
        qualite = f'{round(s["ok"]/total*100)}%' if total > 0 else "?"
        warn_txt = f"⚠ {s.get('perte_pct',0)}% filtrées" if s.get("warn_perte") else ""
        for c_idx, val in enumerate([
            s["type"], s["banque"], s["fichier"], s["source"], s["ok"], s.get("filtre",0), qualite, warn_txt
        ], 1):
            cell = ws.cell(r_idx, c_idx, val)
            if s.get("warn_perte"):
                cell.fill = WARN_FILL
            else:
                color = TYPE_COLORS.get(s["type"], "FFFFFF")
                cell.fill = PatternFill("solid", fgColor=color)

    for i, w in enumerate([8, 12, 20, 12, 16, 10, 10], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    wb.save(dest)
    print(f"\n  Rapport : {dest}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cb",   action="store_true")
    parser.add_argument("--ef",   action="store_true")
    parser.add_argument("--regl", action="store_true")
    args = parser.parse_args()

    run_all = not (args.cb or args.ef or args.regl)

    print("=" * 70)
    print("  PRETRAITEMENT — Nettoyage sans LLM")
    print("=" * 70)

    all_stats = []
    if run_all or args.cb:
        all_stats += process_cb()
    if run_all or args.ef:
        all_stats += process_ef()
    if run_all or args.regl:
        all_stats += process_regl()

    write_rapport(all_stats)

    # Bilan console
    by_type = defaultdict(list)
    for s in all_stats:
        by_type[s["type"]].append(s)

    print(f"\n{'='*70}\n  BILAN FINAL\n{'='*70}")
    for t, lst in sorted(by_type.items()):
        total_ok = sum(s["ok"] for s in lst)
        print(f"  {t}: {len(lst)} fichiers | {total_ok} lignes propres")
    print(f"\n  Sorties dans : {OUT}")

    # Résumé des alertes perte élevée
    alertes = [s for s in all_stats if s.get("warn_perte")]
    if alertes:
        print(f"\n{'='*70}")
        print(f"  ⚠ ALERTES PERTE > 15% ({len(alertes)} fichier(s))")
        print(f"{'='*70}")
        for s in alertes:
            print(f"  {s['banque']:10} {s.get('annee',''):5} {s['fichier']:8} → {s.get('perte_pct',0)}% filtrées ({s['fichier']})")
        print(f"  → Investiguer clean_val / SECTION_RE / is_garbage pour ces fichiers")
    else:
        print(f"\n  ✓ Aucune alerte de perte — taux de filtrage normal sur tous les fichiers")


if __name__ == "__main__":
    main()
