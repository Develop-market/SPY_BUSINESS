"""
fix_montants_milliers.py — corrige les montants divisés par 1000 (2026-07-28)
=============================================================================
TROUVÉ en enquêtant sur le signalement du directeur (« dans les PDF c'est inférieur à 10M »),
sur les frais d'introduction en bourse SGCI. La cause de CE signalement-là était ailleurs (le
prompt jetait le « <= », corrigé dans server.py::_valeur_qualifiee), mais la même requête a
révélé un second défaut, indépendant et silencieux :

    valeur_propre = "<= 10.625.000 Fcfa / Forfait"   →   montant = 10625.0   (au lieu de 10 625 000)

Le point est un séparateur de MILLIERS dans les grilles tarifaires ivoiriennes ; l'extraction
l'a lu comme un séparateur DÉCIMAL. « 10.625.000 » est devenu 10,625 puis 10625. Les valeurs
sont donc 1000 fois trop petites — et ce sont justement les lignes à gros montants (prêts,
introduction en bourse, dépôts minimums) qui se retrouvent à paraître dérisoires dans un
classement de prix.

PORTÉE MESURÉE le 2026-07-28 : 5 lignes sur 31 985 (BNI 2026 S1, SGCI 2024 S1 et S2,
BACI 2025 S1 et 2026 S1). Faible en volume, mais chaque ligne fausse un comparatif de prix.

MÉTHODE : on ne « devine » aucun montant. On relit la forme brute (valeur_propre), on en
extrait le nombre écrit avec des points de milliers, et on ne corrige QUE si le montant stocké
vaut exactement ce nombre divisé par 1000 (à l'unité près) — c'est-à-dire uniquement les cas où
la signature de l'erreur est certaine. Tout le reste est laissé intact.

IDEMPOTENT : relançable sans risque. Une ligne déjà corrigée ne présente plus la signature et
n'est donc plus touchée.

USAGE :
    python fix_montants_milliers.py            # SIMULATION : affiche, ne modifie rien
    python fix_montants_milliers.py --appliquer # écrit en base, après sauvegarde CSV
"""
import csv
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import db as _db   # même connexion que le dashboard

# DEUX groupes de milliers minimum (10.625.000, 5.000.000) — donc un nombre ≥ 1 000 000.
# La 1ʳᵉ version acceptait un seul groupe (« 2.000 ») : elle remontait 26 lignes dont 21 FAUX
# POSITIFS, et les aurait corrompues. Exemple vu en simulation : « 2% min. 2.000 » a un montant
# de 2 — qui est le TAUX de 2 %, pas un « 2 000 mal parsé » — mais 2 000/1000 = 2 satisfaisait
# le test. Même piège avec « 0,0553% / mois + 1.000 ». Sur un nombre à deux groupes, aucun taux
# bancaire plausible ne peut produire cette coïncidence.
_RE_POINTS = re.compile(r"\b(\d{1,3}(?:\.\d{3}){2,})\b")

# Plancher de sécurité : un montant légitimement inférieur à 1 000 FCFA n'est jamais le
# résultat d'une division par 1000 d'un nombre à 7 chiffres — c'est un taux ou un petit tarif.
_MONTANT_MIN = 1000.0


def _candidats(cur):
    cur.execute("""
        SELECT id, banque, annee, semestre, segment, libelle, valeur_propre, montant
        FROM cb_tarifs
        WHERE montant IS NOT NULL AND valeur_propre ~ '[0-9]+\\.[0-9]{3}\\.[0-9]{3}'
    """)
    out = []
    for cid, banque, annee, sem, seg, libelle, vp, montant in cur.fetchall():
        m = _RE_POINTS.search(vp or "")
        if not m:
            continue
        vrai    = float(m.group(1).replace(".", ""))
        montant = float(montant)
        # Signature CERTAINE : le montant stocké vaut exactement le vrai nombre / 1000,
        # il pèse au moins 1 000 FCFA, et il diffère réellement de la valeur correcte.
        if (montant >= _MONTANT_MIN
                and abs(vrai / 1000.0 - montant) < 1.0
                and vrai != montant):
            out.append(dict(id=cid, banque=banque, annee=annee, semestre=sem, segment=seg,
                            libelle=libelle, valeur_propre=vp,
                            montant_actuel=montant, montant_corrige=vrai))
    return out


def main(appliquer: bool):
    cx = _db.get_conn() if hasattr(_db, "get_conn") else _db._conn()
    cur = cx.cursor()
    lignes = _candidats(cur)

    print("=" * 78)
    print(f"  MONTANTS DIVISÉS PAR 1000 — {len(lignes)} ligne(s) détectée(s)")
    print("=" * 78)
    for l in lignes:
        print(f"  [{l['id']}] {l['banque']} {l['annee']}{l['semestre']} {l['segment'][:4]} · {l['libelle'][:44]}")
        print(f"        « {l['valeur_propre'][:56]} »")
        print(f"        {l['montant_actuel']:,.0f}  →  {l['montant_corrige']:,.0f}".replace(",", " "))

    if not lignes:
        print("  Rien à corriger — la base est saine sur ce point.")
        cur.close(); cx.close()
        return

    if not appliquer:
        print("\n  SIMULATION — aucune écriture. Relancer avec --appliquer pour corriger.")
        cur.close(); cx.close()
        return

    # Sauvegarde AVANT écriture : le CSV permet de revenir en arrière ligne par ligne.
    horo = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    sauv = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"backup_montants_milliers_{horo}.csv")
    with open(sauv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)
    print(f"\n  Sauvegarde : {sauv}")

    for l in lignes:
        cur.execute("UPDATE cb_tarifs SET montant=%s WHERE id=%s", (l["montant_corrige"], l["id"]))
    cx.commit()
    print(f"  {len(lignes)} ligne(s) corrigée(s) et validée(s) en base.")
    cur.close(); cx.close()


if __name__ == "__main__":
    main("--appliquer" in sys.argv)
