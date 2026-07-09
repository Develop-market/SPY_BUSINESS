"""
STOCKAGE_BD — Chargement des données nettoyées dans PostgreSQL
==============================================================
Lit les fichiers _clean depuis DATA/DONNEES_PRETRAITEES/
et les charge dans la base intelligence_bancaire (PostgreSQL + pgvector).

Schema :
  banques         : referentiel des banques connues
  cb_tarifs       : conditions de banques (tarifs par banque/annee/semestre/segment)
  ef_indicateurs  : etats financiers (indicateurs avec annee_donnee / is_primary)
  regl_documents  : reglementation (chunks de 500 mots, prets pour RAG)

Usage :
  python run_stockage.py --init          # creer le schema (premiere fois)
  python run_stockage.py                 # tout charger (CB + EF + REGL)
  python run_stockage.py --cb            # charger CB uniquement
  python run_stockage.py --ef            # charger EF uniquement
  python run_stockage.py --regl          # charger REGL uniquement
  python run_stockage.py --reset         # vider les tables puis recharger tout
  python run_stockage.py --reset --cb    # vider CB puis recharger CB
"""

import sys
import os
import re
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE / ".env")

import psycopg2
from psycopg2.extras import execute_values
import openpyxl

# ── Parametres de connexion ───────────────────────────────────────────────────
DB_PARAMS = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME",     "intelligence_bancaire"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

PRETRAITEES  = BASE / "DATA" / "DONNEES_PRETRAITEES"
CB_DIR       = PRETRAITEES / "CONDITIONS_BANQUES"
EF_DIR       = PRETRAITEES / "ETATS_FINANCIERS"
REGL_DIR     = PRETRAITEES / "REGLEMENTATION"

REGL_CHUNK_WORDS = 500   # mots par chunk REGL

# Referentiel banques (nom complet, groupe, segments)
BANQUES_REF = {
    "BACI":    ("Banque Atlantique Cote d'Ivoire",                            "Atlantic Business International", "Particuliers,Entreprises"),
    "BICICI":  ("Banque Internationale pour le Commerce et l'Industrie de CI","BNP Paribas",                    "Particuliers,Entreprises"),
    "BNI":     ("Banque Nationale d'Investissement",                          "Etat de Cote d'Ivoire",          "Particuliers,Entreprises"),
    "ECOBANK": ("Ecobank Cote d'Ivoire",                                      "Ecobank Transnational",          "Particuliers,Entreprises"),
    "NSIA":    ("NSIA Banque",                                                "NSIA Participations",            "Particuliers,Entreprises"),
    "SGCI":    ("Societe Generale Cote d'Ivoire",                             "Societe Generale",               "Particuliers,Entreprises"),
    "SIB":     ("Societe Ivoirienne de Banque",                               "Attijariwafa Bank",              "Particuliers,Entreprises"),
}


# ── Connexion ─────────────────────────────────────────────────────────────────
def get_conn():
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        return conn
    except psycopg2.OperationalError as e:
        print(f"\n[ERREUR CONNEXION] Impossible de se connecter a PostgreSQL :")
        print(f"  {e}")
        print(f"\n  Verifier dans .env : DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD")
        sys.exit(1)


# ── Parsing montant ───────────────────────────────────────────────────────────
_RE_NUM = re.compile(r"[\d]+(?:[\s ][\d]+)*(?:[.,]\d+)?")
_RE_MINMAX = re.compile(r'min[:\s]+([\d\s\xa0,.]+).*?max[:\s]+([\d\s\xa0,.]+)', re.IGNORECASE)

def parse_montant(valeur_propre: str | None) -> float | None:
    if not valeur_propre:
        return None
    v = str(valeur_propre).strip().upper()
    if v in ("GRATUIT", "FREE", "NEANT", "N/A", "NC", "-", ""):
        return None
    # Supprimer tous les espaces (insecables inclus)
    cleaned = v.replace(" ", "").replace(" ", "").replace(" ", "")
    # Format milliers francais : X.000 ou X.000.000 (ex: BNI "50.000" = 50 000 FCFA)
    if re.fullmatch(r"[1-9]\d{0,2}(?:\.\d{3})+", cleaned):
        return float(cleaned.replace(".", ""))
    cleaned = cleaned.replace(",", ".")
    m = re.search(r"\d+\.?\d*", cleaned)
    if not m:
        return None
    try:
        matched = m.group()
        if re.fullmatch(r"[1-9]\d{0,2}(?:\.\d{3})+", matched):
            return float(matched.replace(".", ""))
        trunc = re.fullmatch(r"([1-9]\d{0,2})\.0{4,}", matched)
        if trunc:
            return float(trunc.group(1)) * 1000
        return float(matched)
    except ValueError:
        return None



def parse_montant_multi(valeur_brute, valeur_propre):
    """Detecte Min:X Max:Y et retourne [(montant, rang), ...].
    rang=1 = valeur unique ou Min, rang=2 = Max."""
    for raw in (str(valeur_brute or ''), str(valeur_propre or '')):
        m = _RE_MINMAX.search(raw)
        if m:
            v1 = parse_montant(m.group(1))
            # Tronquer le modificateur de taux trailing : "350 000 2,4" → "350 000"
            # Evite de parser "350 000 2,4" comme 3 500 002,4
            max_raw = re.sub(r'\s+\d{1,3}[,\.]\d+\s*$', '', m.group(2)).strip()
            v2 = parse_montant(max_raw or m.group(2))
            if v1 is not None and v2 is not None and v1 != v2:
                return [(v1, 1), (v2, 2)]
    return [(parse_montant(valeur_propre), 1)]


def _detect_cb_unite(valeur_brute: str, libelle: str = "") -> str | None:
    """Detecte la devise/unite depuis valeur_brute CB : '%', 'EUR', 'USD' ou 'FCFA'.
    Respecte la source : aucune conversion, on tague juste la devise telle qu'ecrite.
    Le libelle sert d'indice secondaire pour les produits explicitement en devises
    (ex. 'Pack Saving O PAYS Euro', comptes Diaspora) ou l'OCR a perdu le symbole."""
    if not valeur_brute:
        return None
    vb = str(valeur_brute).strip()
    if re.search(r'%', vb):
        return '%'
    if re.search(r'€|\bEUR\b|\bEUROS?\b', vb, re.I):
        return 'EUR'
    if re.search(r'\$|\bUSD\b|\bDOLLARS?\b', vb, re.I):
        return 'USD'
    if re.search(r'\bFCFA\b|\bCFA\b|\bXOF\b', vb, re.I):
        return 'FCFA'
    # Indice libelle : produit libelle en euros mais symbole perdu a l'extraction
    if libelle and re.search(r'\bEUROS?\b|/an EUR|diaspora', str(libelle), re.I):
        return 'EUR'
    return None


def _classify_cb_valeur(vb: str, vp: str, est_gratuit: bool, unite: str | None, is_header: bool = False, libelle: str = '', contexte: str = '') -> str:
    """Classifie le type de valeur CB :
    MONTANT_FCFA | TAUX_% | GRATUIT | NON_APPLICABLE | SUR_DEMANDE
    NUMERIQUE | ENTETE_SECTION | AUTRE"""
    if is_header:
        return 'ENTETE_SECTION'
    if est_gratuit:
        return 'GRATUIT'
    vp_up = str(vp or '').strip().upper()
    vb_up = str(vb or '').strip().upper()
    # Gratuit etendu
    if re.search(r'SERVICE NON FACTUR|AUCUN FRAIS|SANS FRAIS|OFFERT', vp_up):
        return 'GRATUIT'
    # Non applicable
    if re.fullmatch(
            r'N/?A|NON.?APPLICABLE|NON.?INDIQU.|N.ANT|NEANT|AUCUN.?', vp_up):
        return 'NON_APPLICABLE'
    # Sur demande / negociable / reference
    if re.search(
            r'CONSULT|CON.SULT|N.GOCI|SUR DEVIS|AU R.EL|TBB'
            r'|.NEGOCIER|TAUX VARIABLE|SUR DEMANDE|PRIX DE LA CARTE'
            r'|.PR.CISER|.LA SOUSCRI|^CF\.?\s|^VOIR |FRAIS DE DOSSIER$'
            r'|COMMISSION PAR |^A\+$', vp_up):
        return 'SUR_DEMANDE'
    if unite == '%':
        return 'TAUX_%'
    if unite in ('FCFA', 'EUR', 'USD'):
        return 'MONTANT_FCFA'  # montant monetaire (la devise reelle est dans la colonne `unite`)
    # Nombre avec TTC ou HT → montant FCFA (ex: '16500 TTC', '5500 HT')
    if re.search(r'\d', vb_up) and re.search(r'\bTTC\b|\bHT\b', vb_up):
        return 'MONTANT_FCFA'
    # Nombre avec /page, /mois, /an etc. → tarif unitaire FCFA
    if re.search(r'\d', vb_up) and re.search(r'/(?:PAGE|MOIS|AN\b|LA |LIGNE|VIREMENT)', vb_up):
        return 'MONTANT_FCFA'
    # Nombre pur sans unite : distinguer montant FCFA vs quantite via libelle OU contexte
    _KW = re.compile(
        r'FRAIS|COMMISSION|TARIF|COTISATION|REJET|IMPAY|OPPOSITION'
        r'|ATTESTATION|TIMBRE|PROCURATION|INCIDENT|CL.TURE|RETRAIT'
        r'|VIREMENT|TRANSFERT|CH.QUE|CARTE|LOCATION|SUCCESSION'
        r'|NANTISSEMENT|PENALI|FORFAIT|ABONNEMENT|D.PASSEMENT|TENUE', re.I)
    lib_up = str(libelle).upper()
    ctx_up = str(contexte).upper()
    is_montant_kw = bool(_KW.search(lib_up) or _KW.search(ctx_up))
    vp_clean = vp_up.replace(' ', '').replace(' ', '').replace(',', '.')
    if vp_clean and re.fullmatch(r'\d+([.]\d+)?', vp_clean):
        return 'MONTANT_FCFA' if is_montant_kw else 'NUMERIQUE'
    vb_clean = vb_up.replace(' ', '').replace(' ', '').replace(',', '.')
    if vb_clean and re.fullmatch(r'\d+([.]\d+)?', vb_clean):
        return 'MONTANT_FCFA' if is_montant_kw else 'NUMERIQUE'
    return 'AUTRE'


# ── Schema PostgreSQL ─────────────────────────────────────────────────────────
SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS banques (
    code        TEXT PRIMARY KEY,
    nom_complet TEXT,
    groupe      TEXT,
    segments    TEXT
);

CREATE TABLE IF NOT EXISTS cb_tarifs (
    id            SERIAL PRIMARY KEY,
    banque        TEXT    NOT NULL REFERENCES banques(code),
    annee         INTEGER NOT NULL,
    semestre      TEXT    NOT NULL,
    segment       TEXT    NOT NULL,
    section       TEXT,
    contexte      TEXT,
    libelle       TEXT    NOT NULL,
    valeur_brute  TEXT,
    valeur_propre TEXT,
    montant       REAL,
    est_gratuit   BOOLEAN DEFAULT FALSE,
    unite         TEXT,
    is_header     BOOLEAN DEFAULT FALSE,
    type_valeur   TEXT,
    embedding     vector(768)
);

CREATE TABLE IF NOT EXISTS ef_indicateurs (
    id            SERIAL PRIMARY KEY,
    banque        TEXT    NOT NULL REFERENCES banques(code),
    fichier       TEXT,
    libelle       TEXT    NOT NULL,
    annee_label   TEXT    NOT NULL,
    annee_donnee  INTEGER,
    annee_rapport INTEGER,
    is_primary    BOOLEAN DEFAULT TRUE,
    unite         TEXT,
    valeur_brute  TEXT,
    valeur_propre TEXT,
    montant       REAL,
    embedding     vector(768)
);

CREATE TABLE IF NOT EXISTS regl_documents (
    id           SERIAL PRIMARY KEY,
    fichier      TEXT    NOT NULL,
    chunk_index  INTEGER NOT NULL,
    contenu      TEXT    NOT NULL,
    tokens_count INTEGER,
    embedding    vector(768),
    UNIQUE (fichier, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_cb_banque_annee ON cb_tarifs  (banque, annee, semestre, segment);
CREATE INDEX IF NOT EXISTS idx_cb_libelle      ON cb_tarifs  (libelle);
CREATE INDEX IF NOT EXISTS idx_ef_banque       ON ef_indicateurs (banque, annee_donnee);
CREATE INDEX IF NOT EXISTS idx_ef_primary      ON ef_indicateurs (annee_donnee, is_primary);
CREATE INDEX IF NOT EXISTS idx_ef_libelle      ON ef_indicateurs (libelle);
CREATE INDEX IF NOT EXISTS idx_regl_fichier    ON regl_documents (fichier);
"""

def init_schema(conn):
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()
    print("  [SCHEMA OK] pgvector + tables + index crees.")


# ── BANQUES — referentiel ──────────────────────────────────────────────────────
def load_banques(conn):
    codes = set()
    for d in CB_DIR.iterdir():
        if d.is_dir():
            codes.add(d.name.upper())
    for d in EF_DIR.iterdir():
        if d.is_dir():
            codes.add(d.name.upper())

    rows = []
    for code in sorted(codes):
        ref = BANQUES_REF.get(code, (None, None, "Particuliers,Entreprises"))
        rows.append((code, ref[0], ref[1], ref[2]))

    with conn.cursor() as cur:
        execute_values(cur,
            """INSERT INTO banques (code, nom_complet, groupe, segments) VALUES %s
               ON CONFLICT (code) DO UPDATE
               SET nom_complet = EXCLUDED.nom_complet,
                   groupe      = EXCLUDED.groupe,
                   segments    = EXCLUDED.segments""",
            rows
        )
    conn.commit()
    print(f"  [BANQUES] {len(rows)} banques : {', '.join(r[0] for r in rows)}")


# ── CB — Conditions de banques ────────────────────────────────────────────────
def load_cb(conn, reset=False):
    # Migration idempotente : ajouter colonnes si absentes
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE cb_tarifs ADD COLUMN IF NOT EXISTS is_header BOOLEAN DEFAULT FALSE")
        cur.execute("ALTER TABLE cb_tarifs ADD COLUMN IF NOT EXISTS type_valeur TEXT")
        cur.execute("ALTER TABLE cb_tarifs ADD COLUMN IF NOT EXISTS rang INTEGER NOT NULL DEFAULT 1")
    conn.commit()

    if reset:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cb_tarifs")
        conn.commit()
        print("  [CB RESET] Table cb_tarifs videe.")

    total = 0
    for banque_dir in sorted(CB_DIR.iterdir()):
        if not banque_dir.is_dir():
            continue
        banque = banque_dir.name
        for annee_dir in sorted(banque_dir.iterdir()):
            if not annee_dir.is_dir():
                continue
            try:
                annee = int(annee_dir.name)
            except ValueError:
                continue
            for xlsx in sorted(annee_dir.glob("*_clean.xlsx")):
                stem   = xlsx.stem.replace("_clean", "")
                parts  = stem.split("_")
                semestre     = parts[0] if parts else "?"
                segment_code = parts[1].upper() if len(parts) > 1 else "?"
                segment = "Entreprises" if segment_code == "E" else "Particuliers"

                rows = _parse_cb_xlsx(xlsx, banque, annee, semestre, segment)
                if not rows:
                    continue
                with conn.cursor() as cur:
                    execute_values(cur,
                        """INSERT INTO cb_tarifs
                           (banque,annee,semestre,segment,section,contexte,
                            libelle,valeur_brute,valeur_propre,montant,est_gratuit,
                            unite,is_header,type_valeur,rang)
                           VALUES %s""",
                        rows
                    )
                conn.commit()
                total += len(rows)
                print(f"    [CB] {banque}/{annee}/{xlsx.name} : {len(rows)} lignes")

    print(f"  [CB] Total : {total} lignes inserees.")


def _parse_cb_xlsx(path: Path, banque, annee, semestre, segment) -> list:
    rows = []
    seen = set()  # deduplication : (libelle, valeur_brute, contexte)
    try:
        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb.active
        headers = None
        for row in ws.iter_rows(values_only=True):
            if headers is None:
                headers = [str(h).strip() if h else "" for h in row]
                continue
            d = dict(zip(headers, row))
            libelle = str(d.get("Libelle") or "").strip()
            if not libelle:
                continue
            # Filtre INVERSIONS (libelle = code pur, ex. "1.1.4", "300", "40.000") :
            # artefact d'extraction (colonnes desappariees sur docs scannes/multi-colonnes)
            # → ligne dechet (jamais un vrai service). On l'ecarte au chargement → la
            # base reste propre meme apres un reload complet (reproductible) et le bouton
            # « Ajouter des donnees » en beneficie aussi.
            if re.fullmatch(r'\d+[\d.]*', libelle):
                continue
            # Eliminer les doublons exacts (meme feuille + libelle + valeur + contexte)
            key = (
                libelle,
                str(d.get("Valeur_brute") or ""),
                str(d.get("Contexte") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            vp = str(d.get("Valeur_propre") or "").strip()
            vb = str(d.get("Valeur_brute")  or "").strip()
            # is_header : ligne structurelle emise par nettoyage (vb="" et vp="")
            is_header = (vb == "" and vp == "")
            # Filtre residuel : entier seul 1-9 sur lignes non-header (layouts 4col/5col)
            if not is_header and re.fullmatch(r'[1-9]', vb):
                continue
            est_gratuit = vp.upper() in ("GRATUIT", "FREE")
            unite       = _detect_cb_unite(vb, libelle) if not is_header else None
            contexte_val = str(d.get("Contexte") or "").strip()
            type_valeur = _classify_cb_valeur(vb, vp, est_gratuit, unite, is_header, libelle, contexte_val)
            # Normaliser toutes les variantes N/A → "Non applicable"
            if type_valeur == 'NON_APPLICABLE':
                vp = "Non applicable"
            section_raw = str(d.get("Section") or "").strip()
            # Normaliser le code section : OCR l→1, filtrer codes garblés
            section_clean = re.sub(r'(?<=[0-9.])l(?=[0-9.]|$)', '1', section_raw)
            section_clean = re.sub(r'^l(?=[0-9.])', '1', section_clean)
            if section_clean and not re.match(r'^\d[\d.]*$', section_clean) and section_clean.upper() != 'NOTE':
                section_clean = ''
            # Detecte Min:X Max:Y -> 2 lignes (rang=1 Min, rang=2 Max) ; valeur unique -> rang=1
            ranges = parse_montant_multi(vb, vp) if not is_header else [(None, 1)]
            # Délai PUR (« J+30 ») ou montant en DEVISE étrangère PUR (« 8 EUROS ») : le
            # « montant » extrait n'est PAS un prix FCFA comparable → on le neutralise (la
            # ligne et son libellé restent). On GARDE les vrais prix FCFA accompagnés d'une
            # note de délai (« 8 000 FCFA J+2 » → 8000 conservé). Reproductible au chargement.
            _vb_s = (vb or "").strip()
            _pure_delai = bool(re.fullmatch(r'(?:gratuit\s+)?J\s*[+\-]\s*\d+', _vb_s, re.I))
            _pure_eur   = bool(re.fullmatch(r'\d[\d ,.]*\s*euros?(?:/an)?', _vb_s, re.I)) \
                          or (unite or "").upper() in ("EUR", "EUROS")
            for (montant, rang) in ranges:
                if montant is not None and ((_pure_delai and montant < 100) or _pure_eur):
                    montant = None
                if montant is not None and montant > 1_000_000 and not _detect_cb_unite(vb):
                    montant = None
                # Garde-fou : un TAUX_% avec montant > 100 est une brute mixte mal classée
                # (ex. "Min:350 000 Max:2,4%" → 350000 étiqueté %). On RÉCUPÈRE le vrai taux
                # présent dans la brute (le % réel) plutôt que de fabriquer un faux pourcentage.
                if type_valeur == 'TAUX_%' and montant is not None and montant > 100:
                    _m = re.search(r'(\d{1,3}(?:[.,]\d{1,3})?)\s*%', vb)
                    _taux = float(_m.group(1).replace(',', '.')) if _m else None
                    if _taux is not None and 0 < _taux <= 100:
                        montant = _taux                       # vrai taux récupéré
                    else:
                        type_valeur = 'SUR_DEMANDE'            # irrécupérable
                        montant = None
                        unite = None
                rows.append((
                    banque, annee, semestre, segment,
                    section_clean or None,
                    str(d.get("Contexte") or "").strip() or None,
                    libelle,
                    vb or None,
                    vp or None,
                    montant,
                    est_gratuit,
                    unite,
                    is_header,
                    type_valeur,
                    rang,
                ))
        wb.close()
    except Exception as e:
        print(f"    [CB ERREUR] {path.name} : {e}")
    return rows


# ── EF — Etats financiers ─────────────────────────────────────────────────────
def load_ef(conn, reset=False):
    if reset:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ef_indicateurs")
        conn.commit()
        print("  [EF RESET] Table ef_indicateurs videe.")

    total = 0
    for banque_dir in sorted(EF_DIR.iterdir()):
        if not banque_dir.is_dir():
            continue
        banque = banque_dir.name
        for xlsx in sorted(banque_dir.glob("*_clean.xlsx")):
            fichier  = xlsx.stem.replace("_clean", "")
            rows     = _parse_ef_xlsx(xlsx, banque, fichier)
            if not rows:
                continue
            with conn.cursor() as cur:
                execute_values(cur,
                    """INSERT INTO ef_indicateurs
                       (banque,fichier,libelle,annee_label,annee_donnee,annee_rapport,
                        is_primary,unite,valeur_brute,valeur_propre,montant)
                       VALUES %s""",
                    rows
                )
            conn.commit()
            total += len(rows)
            n_primary = sum(1 for r in rows if r[6])
            print(f"    [EF] {banque}/{xlsx.name} : {len(rows)} lignes ({n_primary} is_primary)")

    print(f"  [EF] Total : {total} lignes inserees.")


def _parse_ef_xlsx(path: Path, banque: str, fichier: str) -> list:
    rows_out = []
    try:
        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb.active
        headers  = None
        raw_rows = []
        for row in ws.iter_rows(values_only=True):
            if headers is None:
                headers = [str(h).strip() if h else "" for h in row]
                continue
            d = dict(zip(headers, row))
            if not str(d.get("Libelle") or "").strip():
                continue
            raw_rows.append(d)
        wb.close()

        # annee_rapport = max des annees numeriques dans ce fichier
        annees_num = []
        for d in raw_rows:
            try:
                annees_num.append(int(str(d.get("Annee_label") or "").strip()))
            except (ValueError, TypeError):
                pass
        annee_rapport = max(annees_num) if annees_num else None

        for d in raw_rows:
            # Rejeter les libellés qui sont des nombres purs (artefacts OCR mono-colonne)
            libelle_check = str(d.get("Libelle") or "").strip()
            if re.fullmatch(r'\d+', libelle_check):
                continue

            annee_label = str(d.get("Annee_label") or "").strip()
            try:
                annee_donnee = int(annee_label)
            except (ValueError, TypeError):
                annee_donnee = None

            is_primary = (annee_donnee is not None
                          and annee_rapport is not None
                          and annee_donnee == annee_rapport)

            vp = str(d.get("Valeur_propre") or "").strip()
            vb = str(d.get("Valeur_brute")  or "").strip()
            unite = str(d.get("Unite") or "").strip() or None

            # Standardisation automatique : milliards FCFA → millions FCFA
            # Deux cas dans les rapports UEMOA :
            #   1. Valeur genuinement en milliards (montant < 10 000) → multiplier x1000
            #      ex: SIB "Total Bilan = 1 685 milliards" → 1 685 000 millions
            #   2. Label errone : le PDF dit "milliards" mais les chiffres sont en millions (montant >= 10 000)
            #      ex: ECOBANK AN1 "Total Passif = 1 901 235 milliards" → impossible, c est en millions
            #      → corriger uniquement le label, ne pas multiplier
            montant = parse_montant(vp)
            if unite and "milliard" in unite.lower() and montant is not None:
                if montant < 10_000:
                    montant = montant * 1000
                    vb = f"{vb} milliards (= {int(montant):,} millions FCFA)".replace(",", " ")
                unite = "millions FCFA"

            rows_out.append((
                banque,
                fichier,
                str(d.get("Libelle") or "").strip(),
                annee_label,
                annee_donnee,
                annee_rapport,
                is_primary,
                unite,
                vb or None,
                vp or None,
                montant,
            ))
    except Exception as e:
        print(f"    [EF ERREUR] {path.name} : {e}")
    return rows_out


# ── REGL — Reglementation ─────────────────────────────────────────────────────
def load_regl(conn, reset=False):
    if reset:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM regl_documents")
        conn.commit()
        print("  [REGL RESET] Table regl_documents videe.")

    total = 0
    for txt in sorted(REGL_DIR.glob("*_clean.txt")):
        fichier = txt.stem.replace("_clean", "")
        texte   = txt.read_text(encoding="utf-8")
        chunks  = _chunk_text(texte, REGL_CHUNK_WORDS)
        rows    = [
            (fichier, i, chunk, len(chunk.split()))
            for i, chunk in enumerate(chunks)
        ]
        with conn.cursor() as cur:
            execute_values(cur,
                """INSERT INTO regl_documents (fichier, chunk_index, contenu, tokens_count)
                   VALUES %s
                   ON CONFLICT (fichier, chunk_index) DO UPDATE
                   SET contenu = EXCLUDED.contenu, tokens_count = EXCLUDED.tokens_count""",
                rows
            )
        conn.commit()
        total += len(rows)
        print(f"    [REGL] {txt.name} : {len(chunks)} chunks (~{REGL_CHUNK_WORDS} mots/chunk)")

    print(f"  [REGL] Total : {total} chunks inseres.")


def _chunk_text(text: str, words_per_chunk: int) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, current, current_words = [], [], 0
    for para in paragraphs:
        w = len(para.split())
        if current_words + w > words_per_chunk and current:
            chunks.append("\n\n".join(current))
            current, current_words = [], 0
        current.append(para)
        current_words += w
    if current:
        chunks.append("\n\n".join(current))
    return chunks


# ── Verification post-chargement ──────────────────────────────────────────────
def print_summary(conn):
    print(f"\n{'─'*70}")
    print("  RESUME DE LA BASE")
    print(f"{'─'*70}")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM banques")
        print(f"  banques         : {cur.fetchone()[0]}")
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT banque), MIN(annee), MAX(annee) FROM cb_tarifs")
        r = cur.fetchone()
        print(f"  cb_tarifs       : {r[0]} lignes | {r[1]} banques | annees {r[2]}–{r[3]}")
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT banque), MIN(annee_donnee), MAX(annee_donnee) FROM ef_indicateurs")
        r = cur.fetchone()
        print(f"  ef_indicateurs  : {r[0]} lignes | {r[1]} banques | annees {r[2]}–{r[3]}")
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT fichier) FROM regl_documents")
        r = cur.fetchone()
        print(f"  regl_documents  : {r[0]} chunks | {r[1]} documents")
        cur.execute("SELECT COUNT(*) FROM ef_indicateurs WHERE is_primary = TRUE")
        print(f"  ef is_primary   : {cur.fetchone()[0]} lignes (donnees annee principale)")
    print(f"{'─'*70}")


# ── Main ──────────────────────────────────────────────────────────────────────
def _lancer_veille():
    """AGENT WEB — veille dynamique, déclenchée APRÈS chaque stockage de nouvelles données.
    Nouvelles données en base → on relance la recherche web (faits sectoriels/PESTEL frais
    + exclusivités CB) et on régénère le cache `web_facts.json`. Ainsi tout se rafraîchit en
    UN SEUL geste (extraction+stockage → veille). NON BLOQUANT : un échec (réseau/quota) n'interrompt
    pas le pipeline — le cache existant est simplement conservé."""
    import subprocess
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    veille = os.path.join(root, "SGCI Strategic Intelligence — Design System",
                          "spybusiness", "dash_app", "run_veille.py")
    if not os.path.exists(veille):
        print(f"  [veille] script introuvable ({veille}) — étape ignorée.")
        return
    print(f"\n{'─'*70}\n  AGENT WEB — veille dynamique (rafraîchissement du cache web)\n{'─'*70}")
    try:
        subprocess.run([sys.executable, veille], cwd=root, timeout=600, check=False)
    except Exception as e:
        print(f"  [veille] non effectuée ({str(e)[:140]}) — cache existant conservé.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Chargement PostgreSQL — intelligence_bancaire")
    parser.add_argument("--init",  action="store_true", help="Creer le schema (pgvector + tables + index)")
    parser.add_argument("--cb",    action="store_true", help="Charger CB uniquement")
    parser.add_argument("--ef",    action="store_true", help="Charger EF uniquement")
    parser.add_argument("--regl",  action="store_true", help="Charger REGL uniquement")
    parser.add_argument("--reset", action="store_true", help="Vider les tables avant de charger")
    parser.add_argument("--no-veille", action="store_true", help="Ne PAS relancer la veille web après le chargement")
    args = parser.parse_args()

    load_all = not (args.cb or args.ef or args.regl or args.init)

    print("=" * 70)
    print("  STOCKAGE_BD — Chargement PostgreSQL")
    print(f"  Base    : {DB_PARAMS['dbname']} @ {DB_PARAMS['host']}:{DB_PARAMS['port']}")
    print(f"  Donnees : {PRETRAITEES}")
    print("=" * 70)

    conn = get_conn()

    # Schema toujours execute si --init ou chargement complet
    if args.init or load_all:
        print(f"\n{'─'*70}\n  SCHEMA\n{'─'*70}")
        init_schema(conn)
        print(f"\n{'─'*70}\n  REFERENTIEL BANQUES\n{'─'*70}")
        load_banques(conn)

    if args.cb or load_all:
        print(f"\n{'─'*70}\n  CONDITIONS DE BANQUES (CB)\n{'─'*70}")
        load_cb(conn, reset=args.reset)

    if args.ef or load_all:
        print(f"\n{'─'*70}\n  ETATS FINANCIERS (EF)\n{'─'*70}")
        load_ef(conn, reset=args.reset)

    if args.regl or load_all:
        print(f"\n{'─'*70}\n  REGLEMENTATION (REGL)\n{'─'*70}")
        load_regl(conn, reset=args.reset)

    print_summary(conn)
    conn.close()
    print(f"\n{'='*70}\n  STOCKAGE_BD termine — base prete.\n{'='*70}")

    # Données fraîchement stockées → on rafraîchit le contexte web (sauf --no-veille).
    if not args.no_veille:
        _lancer_veille()


if __name__ == "__main__":
    main()
