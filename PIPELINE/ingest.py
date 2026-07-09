# -*- coding: utf-8 -*-
"""
ingest.py — Moteur d'ingestion d'UN document (feature « Ajouter des données »)
=============================================================================
Reçoit un document uploadé + ses métadonnées et déroule la pipeline COMPLÈTE
pour ce seul fichier, en deux temps :

  --mode extract : copie le fichier dans DATA/SOURCE → EXTRACTION → NETTOYAGE
                   → écrit le _clean → renvoie un APERÇU (aucune écriture en base).
  --mode store   : relit le _clean produit à l'étape extract → INSERT CIBLÉ en base
                   (supprime puis réinsère uniquement la clé concernée).
                   Gère l'ajout d'une NOUVELLE banque (insertion dans `banques`
                   avant cb_tarifs / ef_indicateurs à cause de la FK).

Types : CB (par banque, semestriel) · EF (par banque, annuel) · REGL · DOC.

Sortie : lignes de progression « @@STAGE:libellé » sur stdout + ligne finale
         « @@RESULT:{json} ». Le serveur Flask lit ces marqueurs pour la barre
         de progression et le résultat.

NB : aucun reset global — l'ingestion ne touche QUE la clé ciblée (banque/période),
     ce qui protège les données existantes (règle « ne pas régresser l'existant »).
"""

import sys
import os
import json
import shutil
import argparse
import traceback
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "PIPELINE" / "EXTRACTION"))
sys.path.insert(0, str(BASE / "PIPELINE" / "NETTOYAGE"))
sys.path.insert(0, str(BASE / "PIPELINE" / "STOCKAGE_BD"))

SOURCE      = BASE / "DATA" / "SOURCE"
EXTRAITES   = BASE / "DATA" / "DONNEES_EXTRAITES"
PRETRAITEES = BASE / "DATA" / "DONNEES_PRETRAITEES"

TYPE_DIR = {
    "CB":   "CONDITIONS_BANQUES",
    "EF":   "ETATS_FINANCIERS",
    "REGL": "REGLEMENTATION",
    "DOC":  "DOCUMENTS_SUPP",
}

CB_COLS = ["banque", "annee", "semestre", "segment", "section",
           "contexte", "libelle", "valeur_brute", "valeur_propre"]
EF_COLS = ["banque", "fichier", "libelle", "annee_label",
           "unite", "valeur_brute", "valeur_propre"]


def stage(msg: str):
    """Émet un marqueur de progression lu par le serveur."""
    print(f"@@STAGE:{msg}", flush=True)


def result(obj: dict):
    """Émet le résultat final (JSON) et termine."""
    print("@@RESULT:" + json.dumps(obj, ensure_ascii=False), flush=True)


# ── Chemins déterministes selon le type ───────────────────────────────────────
def cb_stem(semestre: str, segment: str) -> str:
    seg = "E" if (segment or "").strip().lower().startswith("e") else "P"
    return f"{semestre.upper()}_{seg}"


def paths_for(typ, banque, annee, stem, ext):
    """Renvoie (src, extrait, clean) pour le type donné."""
    tdir = TYPE_DIR[typ]
    if typ == "CB":
        src   = SOURCE / tdir / banque / str(annee) / f"{stem}{ext}"
        extr  = EXTRAITES / tdir / banque / str(annee) / f"{stem}.xlsx"
        clean = PRETRAITEES / tdir / banque / str(annee) / f"{stem}_clean.xlsx"
    elif typ == "EF":
        src   = SOURCE / tdir / banque / f"{stem}{ext}"
        extr  = EXTRAITES / tdir / banque / f"{stem}.xlsx"
        clean = PRETRAITEES / tdir / banque / f"{stem}_clean.xlsx"
    else:  # REGL / DOC
        src   = SOURCE / tdir / f"{stem}{ext}"
        extr  = EXTRAITES / tdir / f"{stem}.txt"
        clean = PRETRAITEES / tdir / f"{stem}_clean.txt"
    return src, extr, clean


# ════════════════════════════════════════════════════════════════════════════
#  MODE EXTRACT  (copie + extraction + nettoyage + aperçu — PAS de base)
# ════════════════════════════════════════════════════════════════════════════
def do_extract(a):
    ext = Path(a.fichier).suffix.lower()
    stem = a.stem
    src, extr, clean = paths_for(a.type, a.banque, a.annee, stem, ext)

    # 1) Sauvegarde du document dans DATA/SOURCE
    stage("Sauvegarde du document")
    src.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(a.fichier, src)

    if a.type == "CB":
        return _extract_cb(a, src, extr, clean, stem)
    if a.type == "EF":
        return _extract_ef(a, src, extr, clean, stem)
    return _extract_text(a, src, extr, clean, stem)   # REGL / DOC


def _extract_cb(a, src, extr, clean, stem):
    import run_extraction as EX
    import run_nettoyage as NT

    stage("Extraction du tableau (OCR / coordonnées)")
    if extr.exists():
        extr.unlink()                       # forcer une extraction fraîche
    extr.parent.mkdir(parents=True, exist_ok=True)
    EX.process_conditions(src, extr.parent)
    if not extr.exists():
        return result({"ok": False, "type": "CB",
                       "message": "Extraction impossible : le tableau n'a pas pu être lu "
                                  "(document à relire manuellement)."})

    stage("Nettoyage et normalisation")
    sem, seg = NT._parse_stem(stem)
    rows, stats = NT.clean_cb_xlsx(extr, a.banque, str(a.annee), sem, seg)
    clean.parent.mkdir(parents=True, exist_ok=True)
    NT._write_flat_xlsx(rows, clean, CB_COLS)

    stage("Aperçu prêt")
    avec_val = [r for r in rows if str(r.get("valeur_propre") or "").strip()]
    preview = [{"section": r.get("section") or "", "libelle": r.get("libelle") or "",
                "valeur": r.get("valeur_propre") or r.get("valeur_brute") or ""}
               for r in rows if r.get("libelle")][:20]
    return result({
        "ok": len(rows) > 0,
        "type": "CB", "banque": a.banque, "annee": a.annee,
        "semestre": sem, "segment": seg, "stem": stem,
        "lignes": len(rows), "avec_valeur": len(avec_val),
        "preview": preview,
        "message": (f"{len(rows)} lignes extraites ({len(avec_val)} avec valeur)."
                    if rows else "Aucune ligne exploitable extraite."),
    })


def _extract_ef(a, src, extr, clean, stem):
    import run_extraction as EX
    import run_nettoyage as NT

    stage("Extraction des tableaux financiers")
    if extr.exists():
        extr.unlink()
    extr.parent.mkdir(parents=True, exist_ok=True)
    EX.process_etats(src, extr.parent)
    if not extr.exists():
        return result({"ok": False, "type": "EF",
                       "message": "Extraction impossible des états financiers."})

    stage("Nettoyage et normalisation")
    rows, stats = NT._extract_ef_xlsx_rows(extr, a.banque, stem)
    # Règle BNI : montants en FCFA brut → millions FCFA (idem process_ef)
    if a.banque == "BNI":
        for r in rows:
            if not r.get("unite"):
                r["valeur_propre"] = NT._convert_fcfa_to_millions(r["valeur_propre"])
                r["valeur_brute"] = r["valeur_propre"]
                r["unite"] = "millions FCFA"
    clean.parent.mkdir(parents=True, exist_ok=True)
    NT._write_flat_xlsx(rows, clean, EF_COLS)

    stage("Aperçu prêt")
    preview = [{"section": r.get("annee_label") or "", "libelle": r.get("libelle") or "",
                "valeur": r.get("valeur_propre") or r.get("valeur_brute") or ""}
               for r in rows if r.get("libelle")][:20]
    return result({
        "ok": len(rows) > 0,
        "type": "EF", "banque": a.banque, "annee": a.annee, "fichier": stem, "stem": stem,
        "lignes": len(rows), "avec_valeur": len(preview),
        "preview": preview,
        "message": (f"{len(rows)} indicateurs extraits."
                    if rows else "Aucun indicateur exploitable extrait."),
    })


def _extract_text(a, src, extr, clean, stem):
    """REGL / DOC : extraction texte (Docling) → chunking."""
    import run_extraction as EX
    import run_nettoyage as NT

    stage("Extraction du texte (Docling/OCR)")
    if extr.exists():
        extr.unlink()
    extr.parent.mkdir(parents=True, exist_ok=True)
    EX.process_reglementation(src, extr.parent)
    if not extr.exists():
        return result({"ok": False, "type": a.type,
                       "message": "Extraction du texte impossible."})

    stage("Nettoyage du texte")
    texte = extr.read_text(encoding="utf-8", errors="ignore")
    clean.parent.mkdir(parents=True, exist_ok=True)
    clean.write_text(texte, encoding="utf-8")
    chunks = NT_chunks(texte)

    stage("Aperçu prêt")
    extrait = texte.strip().replace("\n", " ")
    return result({
        "ok": len(texte.strip()) > 0,
        "type": a.type, "fichier": stem, "stem": stem,
        "lignes": len(chunks), "caracteres": len(texte),
        "preview": [{"section": "", "libelle": f"Extrait ({len(chunks)} segments)",
                     "valeur": extrait[:600] + ("…" if len(extrait) > 600 else "")}],
        "message": (f"{len(chunks)} segments de texte préparés ({len(texte):,} caractères)."
                    .replace(",", " ") if texte.strip() else "Aucun texte extrait."),
    })


def NT_chunks(texte):
    import run_stockage as ST
    return ST._chunk_text(texte, ST.REGL_CHUNK_WORDS)


# ════════════════════════════════════════════════════════════════════════════
#  MODE STORE  (relit le _clean → INSERT CIBLÉ ; gère la nouvelle banque)
# ════════════════════════════════════════════════════════════════════════════
def ensure_banque(conn, code, nom=None, groupe=None):
    """Insère la banque dans le référentiel si absente (FK cb_tarifs/ef → banques)."""
    import run_stockage as ST
    ref = ST.BANQUES_REF.get(code.upper())
    if ref:
        nom_c, grp_c, seg_c = ref
    else:
        nom_c = nom or code
        grp_c = groupe or None
        seg_c = "Particuliers,Entreprises"
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO banques (code, nom_complet, groupe, segments)
               VALUES (%s,%s,%s,%s)
               ON CONFLICT (code) DO NOTHING""",
            (code.upper(), nom_c, grp_c, seg_c))
    conn.commit()


def do_store(a):
    import run_stockage as ST
    ext = Path(a.fichier).suffix.lower() if a.fichier else ".pdf"
    stem = a.stem
    _, _, clean = paths_for(a.type, a.banque, a.annee, stem, ext)
    if not clean.exists():
        return result({"ok": False, "message": f"Fichier préparé introuvable ({clean.name}). "
                                                "Relancez l'extraction."})

    stage("Connexion à la base")
    conn = ST.get_conn()

    if a.type == "CB":
        sem = a.semestre.upper()
        seg = "Entreprises" if (a.segment or "").lower().startswith("e") else "Particuliers"
        stage("Enregistrement de la banque")
        ensure_banque(conn, a.banque, a.banque_nom, a.banque_groupe)
        rows = ST._parse_cb_xlsx(clean, a.banque, int(a.annee), sem, seg)
        if not rows:
            return result({"ok": False, "message": "Aucune ligne à stocker."})
        stage("Insertion en base (CB)")
        with conn.cursor() as cur:
            cur.execute("""DELETE FROM cb_tarifs
                           WHERE banque=%s AND annee=%s AND semestre=%s AND segment=%s""",
                        (a.banque, int(a.annee), sem, seg))
            from psycopg2.extras import execute_values
            execute_values(cur,
                """INSERT INTO cb_tarifs
                   (banque,annee,semestre,segment,section,contexte,
                    libelle,valeur_brute,valeur_propre,montant,est_gratuit,
                    unite,is_header,type_valeur,rang) VALUES %s""", rows)
        conn.commit()
        n = len(rows)

    elif a.type == "EF":
        stage("Enregistrement de la banque")
        ensure_banque(conn, a.banque, a.banque_nom, a.banque_groupe)
        rows = ST._parse_ef_xlsx(clean, a.banque, stem)
        if not rows:
            return result({"ok": False, "message": "Aucun indicateur à stocker."})
        stage("Insertion en base (EF)")
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ef_indicateurs WHERE banque=%s AND fichier=%s",
                        (a.banque, stem))
            from psycopg2.extras import execute_values
            execute_values(cur,
                """INSERT INTO ef_indicateurs
                   (banque,fichier,libelle,annee_label,annee_donnee,annee_rapport,
                    is_primary,unite,valeur_brute,valeur_propre,montant) VALUES %s""", rows)
        conn.commit()
        n = len(rows)

    else:  # REGL / DOC → chunks dans regl_documents (upsert par fichier+chunk_index)
        texte = clean.read_text(encoding="utf-8", errors="ignore")
        chunks = NT_chunks(texte)
        fichier = ("DOC_" if a.type == "DOC" else "") + stem
        stage("Insertion en base (texte)")
        with conn.cursor() as cur:
            cur.execute("DELETE FROM regl_documents WHERE fichier=%s", (fichier,))
            from psycopg2.extras import execute_values
            execute_values(cur,
                """INSERT INTO regl_documents (fichier, chunk_index, contenu, tokens_count)
                   VALUES %s""",
                [(fichier, i, c, len(c.split())) for i, c in enumerate(chunks)])
        conn.commit()
        n = len(chunks)

    conn.close()
    stage("Terminé")
    return result({"ok": True, "type": a.type, "stem": a.stem, "stockees": n,
                   "message": f"{n} enregistrements stockés en base."})


# ════════════════════════════════════════════════════════════════════════════
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, choices=["extract", "store"])
    p.add_argument("--type", required=True, choices=["CB", "EF", "REGL", "DOC"])
    p.add_argument("--banque", default="")
    p.add_argument("--banque-nom", dest="banque_nom", default="")
    p.add_argument("--banque-groupe", dest="banque_groupe", default="")
    p.add_argument("--annee", default="")
    p.add_argument("--semestre", default="S1")
    p.add_argument("--segment", default="Particuliers")
    p.add_argument("--stem", default="")
    p.add_argument("--fichier", default="")
    a = p.parse_args()

    # stem par défaut selon le type
    if not a.stem:
        if a.type == "CB":
            a.stem = cb_stem(a.semestre, a.segment)
        elif a.type == "EF":
            a.stem = f"AN_{a.annee}" if a.annee else "ANS"
        else:
            a.stem = Path(a.fichier).stem if a.fichier else "document"

    try:
        if a.mode == "extract":
            do_extract(a)
        else:
            do_store(a)
    except Exception as e:
        traceback.print_exc()
        result({"ok": False, "message": f"Erreur : {str(e)[:300]}"})
        sys.exit(1)


if __name__ == "__main__":
    main()
