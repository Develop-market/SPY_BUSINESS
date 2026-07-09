"""
run_repair_structure.py
=======================
Reparations avancees de structure pour TOUTES les banques.

Problemes traites :
  A. type_valeur AUTRE restant -> reclassification elargie (v3)
     v2 : GRATUIT, NON_APPLICABLE, SUR_DEMANDE, TAUX_%, MONTANT_FCFA, NUMERIQUE
     v3 : + delais bancaires (J+1, 60 a 90 jours)
          + montants avec separateur milliers (10.000 / 10 000 / 3 850)
          + "Label : montant" (Timbre : 550, Abonnement mensuel : 10.000)
          + gratuit conditionnel (gratuit en ligne, gratuit dans la banque)
          + selon taux / tbe / selon avis
          + qualificateurs courts sans valeur numerique
          Aussi : mise a jour colonne montant (real) pour MONTANT_FCFA reclassifie
                  mise a jour est_gratuit pour GRATUIT reclassifie

  B. Propagation de section aux lignes orphelines
     - Si une ligne n'a pas de section mais ses voisines ont la meme section
       -> on propage
     - Heuristique : fenetre de 3 lignes precedentes / 3 suivantes

  C. Reconstruction contexte apres propagation de section
"""
import os, re, unicodedata
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE / ".env")
import psycopg2

DB = dict(host=os.getenv("DB_HOST","localhost"), port=int(os.getenv("DB_PORT",5432)),
          dbname=os.getenv("DB_NAME","intelligence_bancaire"),
          user=os.getenv("DB_USER","postgres"), password=os.getenv("DB_PASSWORD",""))

# ── Normalisation OCR ─────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """Normalise valeur_propre avant matching :
    - supprime accents
    - repare tirets OCR de coupure ("con- sulter" -> "consulter")
    - espace unique, minuscule
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFD", text)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"(\w)\s*-\s+(\w)", r"\1\2", t)   # "con- sulter" -> "consulter"
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)  # retour ligne
    t = re.sub(r"\s+", " ", t.lower()).strip()
    return t

# ── Patterns type_valeur — version 3 ─────────────────────────────────────────

# GRATUIT : gratuit (avec parentheses et asterisques), franco, sans frais, 0 fcfa
_PAT_GRATUIT = re.compile(
    r'^(?:'
    r'gratuit\s*(?:\*+|\([^)]{0,60}\)|(?:en\s+ligne|dans\s+la\s+banque|pour\s+les?\b|interne\b)[^,]{0,60})?'
    r'|offert\s*(?:\([^)]{0,40}\))?'
    r'|sans\s+frais?\s*(?:\([^)]{0,40}\))?'
    r'|0\s*(?:fcfa|cfa|f\b|xof|franc)?'
    r'|neante?'
    r'|rien'
    r'|inclus(?:e)?\s*(?:\([^)]{0,40}\))?'
    r'|compris(?:e)?'
    r'|exonere(?:e)?'
    r'|exempte(?:e)?'
    r'|pas\s+de\s+frais?'
    r'|free'
    r'|franco\b'
    r'|pas\s+de\s+facturation'
    r')\s*$',
    re.I | re.UNICODE
)

# NON_APPLICABLE strict : la cellule ENTIERE est un indicateur d'absence de valeur
_PAT_NON_APP = re.compile(
    r'^(?:'
    r'n/?a'
    r'|sans\s+objet'
    r'|non\s+applicable'
    r'|non\s+concerne'
    r'|non\s+requis'
    r'|offre\s+non\s+existante'
    r'|indefini'
    r'|\[illisible\]'
    r'|illisible'
    r'|ne\s+s.applique\s+pas'
    r'|-{1,5}'                   # tirets seuls (ex: "---")
    r'|/{2,}'
    r'|s/?o'
    r')\s*$',                    # strict : rien apres
    re.I | re.UNICODE
)

# NON_APPLICABLE qualificateur : note de contexte sans valeur numerique
# (ex: "Zone Euro", "Toutes les cartes sont VISA", "Au sein de la banque")
_PAT_QUALIFIER = re.compile(
    r'^(?:'
    r'uniquement\s+(?:carte|zone|en\s+ligne|pour\b)'
    r'|toutes?\s+les?\s+cartes?\s+sont\b'
    r'|au\s+sein\s+de\s+la\s+banque'
    r'|en\s+zone\s+\w+'
    r'|zone\s+(?:euro|uemoa|cemac|cedeao|afrique)\b'
    r'|uniquement\s+zone\b'
    r')\s*(?:.*)?$',             # peut avoir du texte apres (ex: "Toutes les cartes sont VISA")
    re.I | re.UNICODE
)

# SUR_DEMANDE : sur demande, nous consulter, frais reels, tarif asservi...
_PAT_SUR_DEM = re.compile(
    r'^(?:'
    r'sur\s+demande'
    r'|sur\s+devis'
    r'|[a]\s+convenir'
    r'|[a]\s+negocier'
    r'|[a]\s+definir'
    r'|[a]\s+determiner'
    r'|variable'
    r'|selon\s+(?:accord|negociation|bareme|conditions?|tarif|assurance|devis'
    r'|convention|modalite|facture|avis|profil|type|categorie|taux|dossier|cas|grille)'
    r'|aux\s+frais\s+du\s+client'
    r'|frais\s+reels?'
    r'|frais\s+au\s+reel'
    r'|reglement[e]?'
    r'|taux\s+du\s+marche'
    r'|taux\s+(?:annuel|mensuel|journalier|contractuel|de\s+base)\b'  # "taux annuel" seul = SUR_DEMANDE
    r'|tbe\b|tbr\b'                      # Taux de Base Effectif / Bancaire de Reference
    r'|tarif\s+asserv\w*'
    r'|tarif\s+assur\w*'
    r'|nous\s+consul\w*'
    r'|droit\s+d.ouverture.*'
    r'|cf\.?\s*(?:tarif|bareme)'
    r'|idem\s+commission'
    r'|selon\s+grille'
    r'|a\s+la\s+grille'
    r'|se\s+conformer'
    r'|tarif\s+en\s+vigueur'
    r'|selon\s+conditions?\s+liees'
    r')\s*(?:.*)?$',
    re.I | re.UNICODE
)

# TAUX_% : X%, TIB+, taux variable...
_PAT_TAUX = re.compile(
    r'^(?:'
    r'\d[\d\s]*[,.]?\d*\s*%'
    r'|(?:0[,.])?[0-9]+\s*p\.?\s*cent'
    r'|tib\s*[+-]\s*\d'
    r'|taux\s+standard\s*[+-]\d'
    r'|[\d,./]+\s*pour\s*mille'
    r')',
    re.I | re.UNICODE
)

# MONTANT_FCFA : patterns numeriques directs (v2)
_PAT_MONTANT_EXT = re.compile(
    r'^(?:'
    r'(?:[a]\s+partir\s+de|mini?\s*:?|maxi?m?\s*:?|minimum\s*:?|maximum\s*:?|jusqu.[a]|'
    r'forfait\s*:?|environ|<=?\s*|>=?\s*)\s*[\d][\d\s.,]*[\d]'
    r'|[\d][\d\s.,]*\s*(?:/\s*(?:page|ligne|feuillet|op[e]ration|virement|an\b|mois\b|trimestre\b|acte\b|b[e]n[e]ficiaire|ecriture|effet|cheque|prelev\w+))'
    r'|[\d][\d\s.,]*\s*(?:fcfa|cfa|f\b|xof)'
    r'|[\d][\d\s.,]*\s*(?:eur\b|usd\b|gbp\b|dollar\b)'
    r'|[\d][\d\s.,]*\s*\((?:an|mois|trimestre|semestre)\)'
    r'|[\d][\d\s.,]*\s+mini\b'
    r'|[1-9][\d\s]{2,}\d'
    r')',
    re.I | re.UNICODE
)

# NUMERIQUE : durees, quantites (N jours, N mois, N cheques...)
_PAT_NUMERIQUE = re.compile(
    r'^(?:'
    r'\d+\s*[aà]\s*\d+\s*(?:jours?|semaines?|mois|ans?|trimestres?)'  # 60 a 90 jours
    r'|\d+\s+(?:jours?|semaines?|mois|ans?|annee|trimestres?)'
    r'|\d+\s+(?:cheques?|effets?|feuillets?|pages?|operations?)'
    r')\s*$',
    re.I | re.UNICODE
)

# ── Patterns v3 — nouveaux ────────────────────────────────────────────────────

# Delais de valeur bancaire (J+1, J-1 ouvres, 60 a 90 jours, quinzaine...)
_PAT_DELAI = re.compile(
    r'^(?:'
    # J seul, J+N, J-N (avec ou sans "ouvres")
    r'[jJ]\s*[+\-]?\s*\d*\s*(?:ouvr\w*)?'
    # "Debit J+1 ouvres", "Credit J-1", "Versement J"
    r'|(?:debit|credit|versement|retrait|encaissement|escompte|virement)\s*(?:de\s+)?'
    r':?\s*[jJ]\s*[+\-]?\s*\d*\s*(?:ouvr\w*)?'
    # "60 a 90 jours"
    r'|\d+\s*[aà]\s*\d+\s*jours?'
    # "quinzaine", "fin de mois", "premier jour de..."
    r'|quinzaine\b'
    r'|fin\s+(?:de\s+)?(?:mois|periode|quinzaine)'
    r'|premier\s+(?:jour\s+)?(?:de|du|ouvr\w*)'
    r')',
    re.I | re.UNICODE
)

# Nombre avec separateur milliers : 3 850 / 10.000 / 1 500 000
# Capture le PREMIER nombre milliers-separe dans le texte (re.search)
_PAT_MILLIERS = re.compile(
    r'(?<!\d)'                         # pas precede d'un chiffre
    r'[1-9]\d{0,2}'                    # 1 a 3 chiffres de tete
    r'(?:[\s.]\d{3})+'                 # un ou plusieurs groupes de 3 chiffres
    r'(?!\d)',                          # pas suivi d'un chiffre
    re.I
)

# "Label texte : montant" — "Abonnement mensuel : 10.000" / "Timbre : 550"
# Le montant en fin peut etre petit (550) ou grand (10.000)
_PAT_LABEL_MONTANT = re.compile(
    r'^[\w\s,\'\(\)/\-]{2,70}'        # label (lettres, espaces, ponctuation simple)
    r':\s*'                            # deux-points separateur
    r'\d[\d\s.,]*'                     # montant numerique
    r'(?:\s*\([^)]{0,30}\))?'         # contexte optionnel entre parentheses
    r'\s*$',
    re.I | re.UNICODE
)

# ── Extraction montant numerique ──────────────────────────────────────────────

def _extract_montant(vp: str) -> float | None:
    """Extrait le montant numerique principal d'une valeur (pour colonne montant).
    Priorite : plus grand nombre milliers-separe, puis 4+ chiffres, puis apres ':'.
    """
    # 1. Tous les nombres avec separateur milliers
    candidates = []
    for m in _PAT_MILLIERS.finditer(vp):
        raw = m.group(0).replace(" ", "").replace(".", "")
        try:
            candidates.append(float(raw))
        except ValueError:
            pass
    if candidates:
        return max(candidates)  # prendre le plus grand (representatif)

    # 2. Nombre 4+ chiffres seul
    m2 = re.search(r'\b(\d{4,})\b', vp)
    if m2:
        try:
            return float(m2.group(1))
        except ValueError:
            pass

    # 3. Montant apres ":" (label: montant court)
    m3 = re.search(r':\s*(\d[\d\s.,]*\d|\d)\s*(?:\([^)]{0,30}\))?\s*$', vp)
    if m3:
        raw = m3.group(1).replace(" ", "").replace(".", "").replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            pass

    return None

# ── Classification AUTRE ──────────────────────────────────────────────────────

def classify_autre(libelle: str, valeur_propre: str) -> tuple[str | None, float | None]:
    """Retourne (nouveau_type_valeur, montant_extrait) ou (None, None).

    Applique une normalisation OCR sur valeur_propre avant matching.
    montant_extrait n'est renseigne que pour MONTANT_FCFA.
    """
    raw_vp = (valeur_propre or "").strip()
    if not raw_vp:
        return None, None

    # Supprimer guillemets typographiques et parentheses en debut/fin
    raw_stripped = raw_vp.strip('“”‘’"\'()')
    vp = _norm(raw_stripped or raw_vp)
    if not vp:
        return None, None

    # ── Patterns v2 (ordre conserve) ─────────────────────────────────────────
    if _PAT_GRATUIT.match(vp):      return "GRATUIT",        None
    if _PAT_NON_APP.match(vp):      return "NON_APPLICABLE", None
    if _PAT_SUR_DEM.match(vp):      return "SUR_DEMANDE",    None
    if _PAT_TAUX.match(vp):         return "TAUX_%",         None
    if _PAT_NUMERIQUE.match(vp):    return "NUMERIQUE",      None
    if _PAT_MONTANT_EXT.match(vp):
        return "MONTANT_FCFA", _extract_montant(vp)

    # ── Patterns v3 ──────────────────────────────────────────────────────────

    # Delai de valeur bancaire (J+1, 60 a 90 jours, quinzaine...)
    if _PAT_DELAI.match(vp):
        return "NUMERIQUE", None

    # Delai compose dans le texte (meme si ne commence pas par J)
    if re.search(r'\b(?:quinzaine|premier\s+jour|fin\s+de\s+(?:la\s+)?(?:quinzaine|mois|periode))\b', vp, re.I):
        return "NUMERIQUE", None

    # "N ans/jours/mois avec ..." — duree avec explication
    if re.match(r'^\d+\s+(?:ans?|jours?|mois|semaines?|trimestres?)\b', vp, re.I):
        return "NUMERIQUE", None

    # (min/max) ou "min/max" dans le texte -> valeur variable
    if re.search(r'\(min[./]max\)|min\s*/\s*max', vp, re.I):
        return "SUR_DEMANDE", None

    # "cf :" ou "cf tarif" -> reference a un autre tarif
    if re.match(r'^cf\s*[:\']', vp, re.I):
        return "SUR_DEMANDE", None

    # Formule de calcul (montant x N, formule proportionnelle)
    if re.search(r'\bmontant\b.{0,50}\bx\s*\d', vp, re.I):
        return "SUR_DEMANDE", None

    # "variable" + texte -> SUR_DEMANDE (ex: "Taux d'escompte variable...")
    if re.search(r'\bvariable\b', vp, re.I) and not re.search(r'\d', vp):
        return "SUR_DEMANDE", None

    # Presence de "gratuit" dans le texte
    has_gratuit  = bool(re.search(r'\bgratuit\b', vp, re.I))
    # Presence d'un nombre avec separateur milliers (10.000, 3 850, 110 000)
    has_milliers = bool(_PAT_MILLIERS.search(vp))

    # Gratuit conditionnel pur (pas de montant milliers dans la meme cellule)
    if has_gratuit and not has_milliers:
        return "GRATUIT", None

    # Montant avec separateur milliers — fonctionne meme en texte compose
    if has_milliers:
        return "MONTANT_FCFA", _extract_montant(vp)

    # "Label : montant court" (Timbre : 550, GIM UEMOA : 455)
    if _PAT_LABEL_MONTANT.match(vp):
        return "MONTANT_FCFA", _extract_montant(vp)

    # Nombre 4-7 chiffres sans separateur milliers (3000, 5500, 18700...)
    # Courant dans valeur_propre ECOBANK/SIB ou les espaces ont ete supprimes
    m4 = re.search(r'\b([1-9]\d{3,6})\b', vp)
    if m4:
        val = int(m4.group(1))
        if val <= 9_999_999:
            return "MONTANT_FCFA", float(val)

    # ── NON_APPLICABLE : labels, fragments, notes sans valeur numerique ───────
    if not re.search(r'\d', vp):

        # Qualificateurs de contexte (Zone Euro, Toutes les cartes sont...)
        if _PAT_QUALIFIER.match(vp):
            return "NON_APPLICABLE", None

        # "Offre non existante dans..." (avec texte supplementaire)
        if re.match(r'^offre\s+non\s+existante\b', vp, re.I):
            return "NON_APPLICABLE", None

        # "Toutes les cartes [X] sont..." (ex: "Toutes les cartes BICICI sont VISA")
        if re.match(r'^toutes?\s+les?\s+cartes?\b', vp, re.I):
            return "NON_APPLICABLE", None

        # Nom de produit carte (Privilege Corporate, Elite Corporate...)
        if re.match(r'^(?:privilege|elite|premier|classic|gold|platinum|silver|prestige|corporate)\b', vp, re.I):
            return "NON_APPLICABLE", None

        # "La facturation des cartes est..." — note de facturation
        if re.match(r'^la\s+facturation\b', vp, re.I):
            return "NON_APPLICABLE", None

        # Labels courts sans valeur (< 35 chars) : "Minimum", "OUVERTURE",
        # "Frais de suivi", "Trimestre indivisible", "B / GAB)", "f)"...
        if len(vp) < 35:
            return "NON_APPLICABLE", None

    return None, None


_KW_MONTANT = re.compile(
    r'FRAIS|COMMISSION|TARIF|COTISATION|REJET|IMPAYE|OPPOSITION'
    r'|ATTESTATION|TIMBRE|PROCURATION|INCIDENT|CLOTURE|RETRAIT'
    r'|VIREMENT|TRANSFERT|CHEQUE|CARTE|LOCATION|SUCCESSION'
    r'|NANTISSEMENT|PENALI|FORFAIT|ABONNEMENT|DEPASSEMENT|TENUE'
    r'|OUVERTURE|OPERATION|FRAIS\s+FIXE|MISE\s+A\s+DISPOSITION'
    r'|DROITS?|HONORAIRES?|PROVISION|AGIOS?|DOSSIER|GESTION'
    r'|LETTRE|SWIFT|TELEX|CAUTION|AVAL|GARANTIE|SIGNATURE',
    re.I
)


def _build_contexte(section, hmap):
    if not section:
        return ""
    sec = section.strip().rstrip(".")
    parts = sec.split(".")
    ancestors = []
    for i in range(1, len(parts)):
        prefix = ".".join(parts[:i])
        lbl = hmap.get(prefix, "").strip()
        if lbl:
            ancestors.append(lbl)
    return " > ".join(ancestors)


def main():
    print("=" * 60)
    print("  REPARATION STRUCTURE — 3 criteres")
    print("=" * 60)
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()

    # ── A. Reclassification type_valeur AUTRE elargie ─────────────────────────
    print("\n[A] Reclassification AUTRE elargie...")
    cur.execute("""
        SELECT id, libelle, valeur_brute, valeur_propre
        FROM cb_tarifs
        WHERE type_valeur = 'AUTRE' AND NOT is_header
          AND valeur_propre IS NOT NULL AND valeur_propre != ''
    """)
    rows = cur.fetchall()
    print(f"    {len(rows)} lignes AUTRE a evaluer")

    counts = {}
    for rid, lib, vb, vp in rows:
        new_type, montant_val = classify_autre(lib, vp)
        if new_type:
            if new_type == "MONTANT_FCFA" and montant_val is not None:
                cur.execute(
                    "UPDATE cb_tarifs SET type_valeur=%s, montant=%s WHERE id=%s",
                    (new_type, montant_val, rid)
                )
            elif new_type == "GRATUIT":
                cur.execute(
                    "UPDATE cb_tarifs SET type_valeur=%s, est_gratuit=TRUE WHERE id=%s",
                    (new_type, rid)
                )
            else:
                cur.execute(
                    "UPDATE cb_tarifs SET type_valeur=%s WHERE id=%s",
                    (new_type, rid)
                )
            counts[new_type] = counts.get(new_type, 0) + 1

    conn.commit()
    total_reclassif = sum(counts.values())
    for tv, n in sorted(counts.items()):
        if n:
            print(f"    {tv:20} : +{n}")
    print(f"    Total reclassifie : {total_reclassif}")

    # ── B. Propagation section aux lignes orphelines ───────────────────────────
    print("\n[B] Propagation section aux lignes orphelines...")
    cur.execute("SELECT DISTINCT banque, annee, semestre, segment FROM cb_tarifs ORDER BY 1,2,3,4")
    tranches = cur.fetchall()
    total_prop = 0

    for banque, annee, semestre, segment in tranches:
        # Recuperer toutes les lignes non-header ordonnees par id
        cur.execute("""
            SELECT id, section, libelle, contexte
            FROM cb_tarifs
            WHERE banque=%s AND annee=%s AND semestre=%s AND segment=%s
              AND is_header=FALSE
            ORDER BY id
        """, (banque, annee, semestre, segment))
        rows = cur.fetchall()
        if not rows:
            continue

        ids     = [r[0] for r in rows]
        sections= [r[1] for r in rows]

        repaired = 0
        for i, (rid, sec, lib, ctx) in enumerate(rows):
            if sec and sec.strip():
                continue  # deja une section

            # Chercher une section dominante dans les 3 voisines avant + 3 apres
            neighbors = []
            for j in range(max(0, i-3), min(len(rows), i+4)):
                if j != i and rows[j][1] and rows[j][1].strip():
                    neighbors.append(rows[j][1].strip())

            if not neighbors:
                continue

            # Section la plus frequente dans le voisinage
            from collections import Counter
            dominant = Counter(neighbors).most_common(1)[0]
            if dominant[1] >= 2:  # au moins 2 voisins avec la meme section
                cur.execute("UPDATE cb_tarifs SET section=%s WHERE id=%s", (dominant[0], rid))
                repaired += 1

        if repaired:
            conn.commit()
            print(f"    {banque} {annee} {semestre} {segment}: {repaired} sections propagees")
        total_prop += repaired

    print(f"    Total propagations : {total_prop}")

    # ── C. Reconstruction contexte (apres propagation) ────────────────────────
    print("\n[C] Reconstruction contexte (apres propagation)...")
    cur.execute("SELECT DISTINCT banque, annee, semestre, segment FROM cb_tarifs ORDER BY 1,2,3,4")
    tranches = cur.fetchall()
    total_ctx = 0

    for banque, annee, semestre, segment in tranches:
        cur.execute("""
            SELECT section, libelle FROM cb_tarifs
            WHERE banque=%s AND annee=%s AND semestre=%s AND segment=%s
              AND is_header=TRUE AND section IS NOT NULL AND section!=''
        """, (banque, annee, semestre, segment))
        hmap = {r[0].strip().rstrip("."): r[1] for r in cur.fetchall() if r[0] and r[1]}
        if not hmap:
            continue

        cur.execute("""
            SELECT id, section FROM cb_tarifs
            WHERE banque=%s AND annee=%s AND semestre=%s AND segment=%s
              AND is_header=FALSE
              AND (contexte IS NULL OR contexte='')
              AND section IS NOT NULL AND section!=''
        """, (banque, annee, semestre, segment))
        rows = cur.fetchall()

        repaired = 0
        for rid, sec in rows:
            ctx = _build_contexte(sec, hmap)
            if ctx:
                cur.execute("UPDATE cb_tarifs SET contexte=%s WHERE id=%s", (ctx, rid))
                repaired += 1

        if repaired:
            conn.commit()
            total_ctx += repaired

    print(f"    Total contextes reconstruits : {total_ctx}")

    # ── Rapport final ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  AUDIT QUALITE FINAL")
    print("=" * 60)

    print("\n--- EXHAUSTIVITE (nb lignes par tranche) ---")
    cur.execute("""
        SELECT banque, annee, semestre, segment, COUNT(*) n
        FROM cb_tarifs
        GROUP BY banque, annee, semestre, segment
        ORDER BY banque, annee, semestre, segment
    """)
    prev = None
    for b, y, sem, seg, n in cur.fetchall():
        if b != prev:
            print(f"  {b}"); prev = b
        flag = "  *** FAIBLE (<150)" if n < 150 else ""
        print(f"    {y} {sem} {seg}: {n}{flag}")

    print("\n--- STRUCTURE (sans section / sans contexte) ---")
    cur.execute("""
        SELECT banque,
          COUNT(*) tot,
          SUM(CASE WHEN NOT is_header AND (section IS NULL OR section='') THEN 1 ELSE 0 END) ss,
          SUM(CASE WHEN NOT is_header AND (contexte IS NULL OR contexte='') THEN 1 ELSE 0 END) sc
        FROM cb_tarifs GROUP BY banque ORDER BY banque
    """)
    print(f"  {'BANQUE':8} {'TOTAL':6} {'SANS_SEC':9} {'SS%':6} {'SANS_CTX':9} {'SC%':6}")
    print("  " + "-" * 52)
    for b, tot, ss, sc in cur.fetchall():
        non_h = tot - 0  # approximation
        cur2 = conn.cursor()
        cur2.execute("SELECT COUNT(*) FROM cb_tarifs WHERE banque=%s AND NOT is_header", (b,))
        nh = cur2.fetchone()[0]
        ss_p = ss/nh*100 if nh else 0
        sc_p = sc/nh*100 if nh else 0
        flag_s = " <--" if ss_p > 10 else ""
        flag_c = " <--" if sc_p > 10 else ""
        print(f"  {b:8} {tot:6} {ss:8} {ss_p:5.1f}%{flag_s}  {sc:8} {sc_p:5.1f}%{flag_c}")

    print("\n--- VERACITE (type_valeur distribution) ---")
    cur.execute("""
        SELECT banque, type_valeur, COUNT(*) n
        FROM cb_tarifs WHERE NOT is_header
        GROUP BY banque, type_valeur ORDER BY banque, n DESC
    """)
    rows = cur.fetchall()
    cur.execute("SELECT banque, COUNT(*) FROM cb_tarifs WHERE NOT is_header GROUP BY banque")
    totaux = {b: t for b, t in cur.fetchall()}
    prev = None
    for b, tv, n in rows:
        if b != prev:
            print(f"  {b}"); prev = b
        pct = n / totaux[b] * 100 if totaux[b] else 0
        flag = "  <<<" if tv == "AUTRE" and pct > 5 else ""
        print(f"    {tv:22} {n:5} ({pct:5.1f}%){flag}")

    conn.close()
    print("\n  Reparations terminees.")
    print("  Qualite cible : AUTRE < 5%, SANS_SECTION < 10%, SANS_CONTEXTE < 10%")
    print("  Si OK : lancer vectorisation.")


if __name__ == "__main__":
    main()
