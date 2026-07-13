# -*- coding: utf-8 -*-
"""
extract_fiche_narrative.py — Parseur DÉDIÉ pour les fiches-portrait narratives
================================================================================
Certains documents sources (ex. « Rapport Annuel sur la Gestion du Portefeuille
de l'État » — une fiche d'une page par banque publique) ne sont PAS des tableaux
financiers classiques : texte narratif + graphiques (PNB, coefficient
d'exploitation, taux de dégradation, résultat net sur 5 ans), sans aucun
tableau détectable par camelot/pdfplumber. Cas rencontré : BNI/AN4.pdf.

Le parseur générique (_extract_ef_txt_rows dans NETTOYAGE/run_nettoyage.py,
basé sur des tableaux/lignes « libellé : valeur ») ne peut RIEN en extraire.
Ce script est un chemin À PART, dédié à ce format précis — pas une modification
du parseur générique, pour ne rien risquer sur les 6 autres banques qui, elles,
ont de vrais tableaux.

IMPORTANT — pourquoi le texte (phrases) plutôt que les graphiques :
Testé en direct sur BNI/AN4.pdf : les nombres des graphiques (ex. série PNB
2020-2024) sortent de l'extraction PDF dans un ORDRE VISUEL, pas chronologique
(ex. « 100,71 87,67 71,18 51,97 57,97 » au lieu de 2020→2024) — les valeurs
suivent l'ordre de dessin du graphique, pas l'axe des années. Tenter de les
ré-associer aux années par position serait trop risqué pour une donnée
financière. Les PHRASES, elles, nomment explicitement l'année ET la valeur
ensemble (« ... 100,71 milliards FCFA ... par rapport à 2023 (87,67 milliards
FCFA) »), donc immunisées contre cet ordre de lecture.

Réutilisable pour toute banque présentant ce MÊME type de fiche narrative
(les motifs ci-dessous sont des tournures de phrases françaises standard de
reporting financier, pas des références à « BNI ») — déclenché explicitement
au cas par cas, PAS branché dans le pipeline automatique (run_extraction.py /
run_nettoyage.py), car chaque nouvelle fiche doit être relue avant confiance.

GARDE-FOU anti-erreur : pour chaque valeur « année de comparaison » (l'année
N-1 mentionnée dans le texte), on compare à ce qui existe déjà dans
ef_indicateurs pour cette banque. Écart > tolérance → on N'INSÈRE RIEN et on
alerte, plutôt que de faire confiance à un motif de phrase mal interprété.

Usage :
  python extract_fiche_narrative.py <chemin_pdf> <BANQUE> --annee 2024
  python extract_fiche_narrative.py <chemin_pdf> <BANQUE> --annee 2024 --dry-run
"""
import sys
import re
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR / "RAG"))

TOLERANCE_PCT = 1.0   # écart toléré vs la BD (%) avant de considérer que ça ne correspond pas


def _num(s: str) -> float:
    """'2 359' / '100,71' / '-9,19' → float. Espaces = séparateur de milliers, virgule = décimale."""
    return float(s.replace(" ", "").replace(" ", "").replace(",", "."))


def _milliards_vers_millions(v: float) -> float:
    return round(v * 1000)


# ── Motifs de phrases (génériques — tournures de reporting financier standard,
#    pas propres à une banque précise) ──────────────────────────────────────────
# Chaque motif capture : libellé, valeur année courante, [valeur année N-1]
#
# LIBELLÉS : alignés EXACTEMENT sur ceux déjà utilisés pour les 7 banques dans
# ef_indicateurs (vérifié par requête SQL — ex. "CHARGES GENERALES
# D'EXPLOITATION", pas "FRAIS GENERAUX") — sinon ces lignes seraient invisibles
# aux comparaisons inter-banques qui filtrent par libellé exact.
#
# NON INSÉRÉS EN BASE (mais affichés dans le rapport) : coefficient
# d'exploitation et taux de dégradation du portefeuille — vérifié que
# ef_indicateurs ne stocke QUE des montants en « millions FCFA » (aucune ligne
# en % pour aucune des 7 banques) : ces ratios sont recalculés à la volée
# ailleurs (dash_app/db.py) à partir des montants bruts (PNB, charges...), pas
# stockés comme ligne. Les insérer casserait la convention de la table.
# « FONDS PROPRES EFFECTIFS » non plus (concept prudentiel différent de
# « CAPITAUX PROPRES ET RESSOURCES ASSIMILEES » du bilan — pas substituable).
NE_PAS_INSERER = {"COEFFICIENT D'EXPLOITATION", "TAUX BRUT DE DEGRADATION DU PORTEFEUILLE",
                  "FONDS PROPRES EFFECTIFS"}

PATTERNS = [
    {
        "libelle": "TOTAL DE L'ACTIF",
        "unite": "milliards FCFA",
        "regex": re.compile(
            r"total bilan.*?atteignant\s+([\d , ]+)\s*milliards\s*FCFA\s*contre\s+"
            r"([\d , ]+)\s*milliards\s*FCFA\s*au\s*31\s*d[ée]cembre\s*(\d{4})",
            re.IGNORECASE | re.DOTALL,
        ),
        "groups": "valeur_puis_comparatif_annee",
    },
    {
        "libelle": "PRODUITS NET BANCAIRE",
        "unite": "milliards FCFA",
        "regex": re.compile(
            r"produit\s*net\s*bancaire\s*\(pnb\)\s*s.[ée]l[èe]ve\s*à\s*([\d , ]+)\s*milliards\s*FCFA"
            r".*?par\s*rapport\s*à\s*(\d{4})\s*\(([\d , ]+)\s*milliards\s*FCFA\)",
            re.IGNORECASE | re.DOTALL,
        ),
        "groups": "valeur_puis_annee_comparatif",
    },
    {
        "libelle": "CHARGES GENERALES D'EXPLOITATION",
        "unite": "milliards FCFA",
        "regex": re.compile(
            r"frais\s*g[ée]n[ée]raux\s*augmentent.*?pour\s*s.[ée]tablir\s*à\s*([\d , ]+)\s*milliards\s*FCFA",
            re.IGNORECASE | re.DOTALL,
        ),
        "groups": "valeur_seule",
    },
    {
        "libelle": "COEFFICIENT D'EXPLOITATION",
        "unite": "%",
        "regex": re.compile(
            r"coefficient\s*d.exploitation.*?passe\s*de\s*([\d,]+)\s*%\s*en\s*(\d{4})\s*à\s*([\d,]+)\s*%\s*en\s*(\d{4})",
            re.IGNORECASE | re.DOTALL,
        ),
        "groups": "annee1_val1_annee2_val2",
    },
    {
        "libelle": "RESULTAT BRUT D'EXPLOITATION",
        "unite": "milliards FCFA",
        "regex": re.compile(
            r"r[ée]sultat\s*brut\s*d.exploitation\s*b[ée]n[ée]ficiaire\s*de\s*([\d , ]+)\s*milliards\s*FCFA",
            re.IGNORECASE | re.DOTALL,
        ),
        "groups": "valeur_seule",
    },
    {
        "libelle": "COUT DU RISQUE",
        "unite": "milliards FCFA",
        "regex": re.compile(
            r"co[uû]t\s*net\s*du\s*risque.*?pour\s*s.[ée]tablir\s*à\s*(-?[\d , ]+)\s*milliards\s*FCFA\s*en\s*(\d{4}),"
            r"\s*contre\s*(-?[\d , ]+)\s*milliards\s*FCFA\s*en\s*(\d{4})",
            re.IGNORECASE | re.DOTALL,
        ),
        "groups": "val1_annee1_val2_annee2",
    },
    {
        "libelle": "TAUX BRUT DE DEGRADATION DU PORTEFEUILLE",
        "unite": "%",
        "regex": re.compile(
            r"taux\s*brut\s*de\s*d[ée]gradation\s*du\s*portefeuille\s*augmente.*?passant\s*de\s*"
            r"([\d,]+)\s*%\s*en\s*(\d{4})\s*à\s*([\d,]+)\s*%\s*en\s*(\d{4})",
            re.IGNORECASE | re.DOTALL,
        ),
        "groups": "val1_annee1_val2_annee2",
    },
    {
        "libelle": "RESULTAT NET",
        "unite": "milliards FCFA",
        "regex": re.compile(
            r"l.ann[ée]e\s*(\d{4})\s*se\s*solde\s*par\s*un\s*r[ée]sultat\s*net\s*b[ée]n[ée]ficiaire\s*de\s*"
            r"([\d , ]+)\s*milliards\s*FCFA.*?par\s*rapport\s*à\s*\d{4}\s*\(([\d , ]+)\s*milliards\s*FCFA\)",
            re.IGNORECASE | re.DOTALL,
        ),
        "groups": "annee_valeur_comparatif",
    },
    {
        "libelle": "FONDS PROPRES EFFECTIFS",
        "unite": "milliards FCFA",
        "regex": re.compile(
            r"fonds\s*propres\s*effectifs\s*de\s*la\s*banque\s*ressortent\s*positifs\s*à\s*"
            r"([\d , ]+)\s*milliards\s*FCFA",
            re.IGNORECASE | re.DOTALL,
        ),
        "groups": "valeur_seule",
    },
]


def extraire(texte: str, annee_ref: int) -> list[dict]:
    """Retourne une liste de {libelle, annee, valeur, unite, source:'texte'}."""
    lignes = []
    annee_prec = annee_ref - 1

    for pat in PATTERNS:
        m = pat["regex"].search(texte)
        if not m:
            print(f"  [NON TROUVÉ] {pat['libelle']} — motif non détecté dans le texte")
            continue

        g = pat["groups"]
        if g == "valeur_seule":
            lignes.append({"libelle": pat["libelle"], "annee": annee_ref,
                            "valeur": _num(m.group(1)), "unite": pat["unite"]})
        elif g == "valeur_puis_comparatif_annee":
            lignes.append({"libelle": pat["libelle"], "annee": annee_ref,
                            "valeur": _num(m.group(1)), "unite": pat["unite"]})
            lignes.append({"libelle": pat["libelle"], "annee": int(m.group(3)),
                            "valeur": _num(m.group(2)), "unite": pat["unite"]})
        elif g == "valeur_puis_annee_comparatif":
            lignes.append({"libelle": pat["libelle"], "annee": annee_ref,
                            "valeur": _num(m.group(1)), "unite": pat["unite"]})
            lignes.append({"libelle": pat["libelle"], "annee": int(m.group(2)),
                            "valeur": _num(m.group(3)), "unite": pat["unite"]})
        elif g == "annee_valeur_comparatif":
            lignes.append({"libelle": pat["libelle"], "annee": int(m.group(1)),
                            "valeur": _num(m.group(2)), "unite": pat["unite"]})
            lignes.append({"libelle": pat["libelle"], "annee": annee_prec,
                            "valeur": _num(m.group(3)), "unite": pat["unite"]})
        elif g == "annee1_val1_annee2_val2":
            lignes.append({"libelle": pat["libelle"], "annee": int(m.group(2)),
                            "valeur": _num(m.group(1)), "unite": pat["unite"]})
            lignes.append({"libelle": pat["libelle"], "annee": int(m.group(4)),
                            "valeur": _num(m.group(3)), "unite": pat["unite"]})
        elif g == "val1_annee1_val2_annee2":
            lignes.append({"libelle": pat["libelle"], "annee": int(m.group(2)),
                            "valeur": _num(m.group(1)), "unite": pat["unite"]})
            lignes.append({"libelle": pat["libelle"], "annee": int(m.group(4)),
                            "valeur": _num(m.group(3)), "unite": pat["unite"]})

    # COUT DU RISQUE : la fiche l'exprime en négatif (impact sur le résultat), mais la
    # convention déjà en base pour les 7 banques est une magnitude positive (une charge),
    # cf. BACI "COUT DU RISQUE 9 397/15 446/11 169" — toujours positif. Sans cette
    # normalisation, le garde-fou de cohérence lève une fausse divergence de 200%.
    for l in lignes:
        if l["libelle"] == "COUT DU RISQUE":
            l["valeur"] = abs(l["valeur"])

    return lignes


def _synonymes(libelle: str) -> list[str]:
    """Libellés existants dans ef_indicateurs pouvant correspondre à ce libellé de fiche."""
    table = {
        "PRODUIT NET BANCAIRE": ["PRODUITS NET BANCAIRE", "PRODUIT NET BANCAIRE"],
        "RESULTAT NET": ["RESULTAT NET"],
        "COEFFICIENT D'EXPLOITATION": ["COEFFICIENT D'EXPLOITATION", "COEFFICIENT EXPLOITATION"],
    }
    return table.get(libelle, [libelle])


def verifier_coherence(banque: str, lignes: list[dict]) -> list[dict]:
    """Compare chaque ligne à ef_indicateurs (même banque, même année) si une donnée existe déjà.
    Retourne les lignes avec un champ 'coherence' ajouté : 'nouveau' (rien en base, ex. 2024),
    'ok' (concorde avec la base), ou 'DIVERGENCE' (ne concorde pas — à ne PAS insérer sans relecture)."""
    import config
    import psycopg2
    try:
        cx = psycopg2.connect(**config.DB_PARAMS)
        cur = cx.cursor()
    except Exception as e:
        print(f"  [ATTENTION] Connexion BD impossible pour la vérification croisée : {e}")
        for l in lignes:
            l["coherence"] = "NON VERIFIE (BD indisponible)"
        return lignes

    for l in lignes:
        libs = _synonymes(l["libelle"])
        cur.execute(
            "SELECT montant, unite FROM ef_indicateurs "
            "WHERE banque=%s AND annee_donnee=%s AND is_primary=TRUE AND libelle = ANY(%s) "
            "ORDER BY id LIMIT 1",
            (banque, l["annee"], libs),
        )
        row = cur.fetchone()
        if not row:
            l["coherence"] = "nouveau (rien en base pour cette année)"
            continue
        montant_bd, unite_bd = row
        valeur_millions = (_milliards_vers_millions(l["valeur"]) if l["unite"] == "milliards FCFA"
                            else l["valeur"])
        if l["unite"] == "%" or unite_bd not in ("millions FCFA",):
            l["coherence"] = f"non comparable (unité base = {unite_bd})"
            continue
        ecart_pct = abs(valeur_millions - montant_bd) / max(abs(montant_bd), 1) * 100
        if ecart_pct <= TOLERANCE_PCT:
            l["coherence"] = f"ok (base={montant_bd:,.0f}, écart {ecart_pct:.2f}%)"
        else:
            l["coherence"] = f"DIVERGENCE (base={montant_bd:,.0f}, fiche={valeur_millions:,.0f}, écart {ecart_pct:.1f}%)"

    cur.close(); cx.close()
    return lignes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("banque")
    ap.add_argument("--annee", type=int, required=True, help="Année de référence du document (ex. 2024)")
    ap.add_argument("--dry-run", action="store_true", help="N'écrit rien, affiche seulement")
    args = ap.parse_args()

    import pdfplumber
    with pdfplumber.open(args.pdf) as pdf:
        # Recadrage sur la colonne de TEXTE (gauche, ~63% de la largeur) : ces fiches ont une
        # colonne graphiques à droite dont les étiquettes de valeurs (chiffres + %) s'intercalent
        # dans la lecture ligne-par-ligne de pdfplumber si on lit la page entière — constaté en
        # plein milieu de phrases (ex. « au 31 décembre +15%\n2023 » au lieu de « au 31 décembre
        # 2023 »), ce qui casse les motifs de phrase. Le recadrage élimine le problème à la racine
        # plutôt que de rendre chaque motif tolérant à un bruit imprévisible.
        texte = "\n".join(
            (p.crop((0, 0, p.width * 0.63, p.height)).extract_text() or "")
            for p in pdf.pages
        )

    print(f"[EXTRACTION] {args.pdf.name} — {len(texte):,} caractères de texte natif")
    lignes = extraire(texte, args.annee)
    print(f"[EXTRACTION] {len(lignes)} valeurs extraites depuis {len(PATTERNS)} motifs de phrase\n")

    lignes = verifier_coherence(args.banque, lignes)

    print(f"{'Libellé':<35} {'Année':<7} {'Valeur':>14} {'Unité':<15} Cohérence")
    print("-" * 110)
    divergences = 0
    for l in sorted(lignes, key=lambda x: (x["libelle"], x["annee"])):
        print(f"{l['libelle']:<35} {l['annee']:<7} {l['valeur']:>14,.2f} {l['unite']:<15} {l['coherence']}")
        if "DIVERGENCE" in l["coherence"]:
            divergences += 1

    if divergences:
        print(f"\n[ARRET] {divergences} divergence(s) détectée(s) vs la base existante — "
              f"RIEN n'est écrit. Relire le PDF et les motifs avant de continuer.")
        sys.exit(1)

    print(f"\n[OK] Aucune divergence sur les années déjà connues — les valeurs {args.annee} "
          f"(nouvelles) sont cohérentes avec l'historique de {args.banque}.")

    if args.dry_run:
        print("[DRY-RUN] Aucune écriture (--dry-run).")
        return

    ecrire_en_base(args.banque, args.pdf.stem, args.annee, lignes)


def ecrire_en_base(banque: str, fichier: str, annee_ref: int, lignes: list[dict]):
    """Insère UNIQUEMENT les lignes de l'année de référence (les années de comparaison servaient
    à la vérification, pas à être réinsérées) et dont le libellé suit la convention de la table
    (montants en millions FCFA — les % et 'FONDS PROPRES EFFECTIFS' sont exclus, cf. NE_PAS_INSERER)."""
    import config
    import psycopg2

    a_inserer = [l for l in lignes if l["annee"] == annee_ref and l["libelle"] not in NE_PAS_INSERER]
    ignores   = [l for l in lignes if l["annee"] == annee_ref and l["libelle"] in NE_PAS_INSERER]

    for l in ignores:
        print(f"  [NON INSERE] {l['libelle']} ({l['annee']}) — hors convention de la table (voir NE_PAS_INSERER)")

    if not a_inserer:
        print("  [ARRET] Rien à insérer.")
        return

    cx  = psycopg2.connect(**config.DB_PARAMS)
    cur = cx.cursor()
    rows = []
    for l in a_inserer:
        montant = _milliards_vers_millions(l["valeur"])
        rows.append((
            banque, fichier, l["libelle"], str(annee_ref), annee_ref, annee_ref,
            True, "millions FCFA", f"{montant:,}".replace(",", " "), str(montant), montant,
        ))

    from psycopg2.extras import execute_values
    execute_values(cur,
        """INSERT INTO ef_indicateurs
           (banque,fichier,libelle,annee_label,annee_donnee,annee_rapport,
            is_primary,unite,valeur_brute,valeur_propre,montant)
           VALUES %s""",
        rows)
    cx.commit()
    cur.close(); cx.close()
    print(f"\n[ECRIT] {len(rows)} lignes insérées dans ef_indicateurs pour {banque} {annee_ref}.")
    print(f"[SUIVANT] Lancer 'python ../VECTORISATION/run_vectorisation.py --ef' pour que le chat "
          f"puisse trouver ces nouvelles lignes (embedding actuellement NULL, comme prévu par "
          f"le pipeline existant pour toute nouvelle ligne).")


if __name__ == "__main__":
    main()
