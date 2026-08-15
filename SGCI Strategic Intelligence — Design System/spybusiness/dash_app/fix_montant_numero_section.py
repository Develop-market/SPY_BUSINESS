"""
fix_montant_numero_section.py — quand le numero de rubrique a ete lu comme un prix (2026-08-15)
===============================================================================================
Les grilles tarifaires numerotent leurs rubriques : « 2.1.1.3 Commission de mouvement »,
« 2.2. Distributeurs Automatiques de Billets ». Quand l'extraction prend ce numero pour le
tarif, la ligne annonce un prix de 2,1 FCFA.

Ce n'est pas un montant approximatif, c'est un montant qui n'existe pas — et dans un
comparatif de prix, deux francs placent la banque en tete. Certaines de ces lignes sont
d'ailleurs de simples INTITULES de section, sans aucun tarif : « 2.2. Distributeurs
Automatiques de Billets » n'a pas de prix du tout.

METHODE. On ne devine pas le vrai tarif : il n'est pas dans la ligne. On efface un chiffre
faux, ce qui est different d'inventer un chiffre juste. Le montant passe a NULL — « inconnu »,
que l'application sait afficher — plutot que de rester a 2,1, qui se lit comme un prix.

SIGNATURE, exigee sur trois points :
  * le libelle COMMENCE par un numero pointe (« 2.1.1.3 », « 2,1.1.7 ») ;
  * le montant stocke vaut EXACTEMENT les deux premiers groupes de ce numero ;
  * le montant n'est PAS un entier. Un tarif en francs CFA est un entier : il n'existe pas de
    service facture 2,1 FCFA. Une valeur a decimale, egale au numero qui ouvre son propre
    libelle, ne peut etre qu'un numero de rubrique.

CE QUI EST EXCLU : les lignes de TAUX. Un taux de 2,1 % se stocke legitimement en 2,1, et un
libelle commencant par « 2.1 » en ferait une fausse victime.

UNE CLAUSE ECARTEE, ET POURQUOI (a ne pas reintroduire). La premiere version verifiait que le
montant n'apparaissait pas dans la valeur brute, en le formatant par to_char(). Deux defauts :
  * elle dependait de lc_numeric — « 2,1 » sur la base locale (fr-FR), « 2.1 » sur l'hebergeur
    (en_US). Le meme script rendait 18 lignes ici et 1 la-bas, sur des donnees IDENTIQUES ;
  * et elle se trompait de cible : « 2.1 » se retrouve evidemment dans « 2.1.1 .3 Commission… »,
    c'est-a-dire dans le numero de rubrique lui-meme, ce qui excluait precisement les lignes
    a corriger.
Un critere qui change de reponse selon la langue du serveur n'est pas un critere.

IDEMPOTENT : une ligne corrigee a montant NULL, elle ne presente plus la signature.

USAGE :
    python fix_montant_numero_section.py             # SIMULATION
    python fix_montant_numero_section.py --appliquer # ecrit, apres sauvegarde CSV
"""
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "..", "..", ".env"))
except Exception:
    pass

import psycopg2

APPLIQUER = "--appliquer" in sys.argv

DB = dict(
    host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "intelligence_bancaire"),
    user=os.getenv("DB_USER", "postgres"), password=os.getenv("DB_PASSWORD", ""),
)
if (os.getenv("DATABASE_URL") or "").strip():
    from urllib.parse import unquote, urlparse
    u = urlparse(os.environ["DATABASE_URL"])
    DB = dict(host=u.hostname, port=int(u.port or 5432),
              dbname=(u.path or "/postgres").lstrip("/"),
              user=unquote(u.username or ""), password=unquote(u.password or ""))
    if DB["host"] not in ("localhost", "127.0.0.1"):
        DB["sslmode"] = "require"

SQL = r"""
WITH num AS (
    SELECT id, banque, annee, semestre, libelle, valeur_propre, montant, type_valeur,
           (regexp_match(libelle, '^\s*(\d{1,2})[.,](\d{1,2})'))[1] AS g1,
           (regexp_match(libelle, '^\s*(\d{1,2})[.,](\d{1,2})'))[2] AS g2
    FROM cb_tarifs
    WHERE montant IS NOT NULL AND montant > 0 AND montant < 1000
)
SELECT id, banque, annee, semestre, montant, libelle, COALESCE(valeur_propre, '')
FROM num
WHERE g1 IS NOT NULL
  AND abs(montant - ((g1 || '.' || g2)::numeric)) < 0.001
  AND montant <> trunc(montant)                       -- un tarif en FCFA est entier
  -- CE QUI DISTINGUE UN NUMERO D'UN TAUX : le nombre de groupes.
  -- Un numero de rubrique en a au moins trois — « 2.1.1 », « 2.2.2.3.3 » — ou se termine par
  -- un point : « 2.2. Distributeurs Automatiques de Billets ». Un taux n'en a que deux et il
  -- est suivi d'un pour-cent : « 0,15% de la capitalisation fin de trimestre ».
  --
  -- Cette ligne-la existe vraiment, et une premiere version l'a EFFACEE A TORT : son montant
  -- de 0,15 est le vrai taux, pas un numero. C'est la sauvegarde CSV qui a permis de la
  -- retablir. Le filtrage par type_valeur, essaye ensuite, protegeait bien ce taux mais
  -- epargnait aussi quatre lignes « TAUX_% » dont le montant valait 2,1 alors que le taux
  -- annonce etait 0,05 %. Compter les groupes tranche les deux cas d'un seul critere.
  AND libelle ~ '^\s*\d{1,2}[.,]\d{1,2}[.,]'
ORDER BY banque, annee, semestre
"""

cx = psycopg2.connect(**DB)
print(f"\n  base : {DB['dbname']}@{DB['host']}")
with cx.cursor() as c:
    c.execute(SQL)
    lignes = c.fetchall()

print(f"  {len(lignes)} lignes où le montant est le numéro de rubrique du libellé\n")
for r in lignes:
    print(f"    {r[1]:8} {r[2]} {r[3]}  montant={r[4]:<6} « {r[5][:62]} »")
    print(f"                        valeur brute : « {r[6][:62]} »")

if not lignes:
    print("  rien à corriger.\n")
    cx.close()
    sys.exit()

if not APPLIQUER:
    print("\n  (simulation — relancer avec --appliquer pour écrire)\n")
    cx.close()
    sys.exit()

horo = datetime.now().strftime("%Y%m%d_%H%M%S")
sortie = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      f"backup_numero_section_{horo}.csv")
with open(sortie, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "banque", "annee", "semestre", "montant_avant", "libelle", "valeur_propre"])
    for r in lignes:
        w.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6]])
print(f"\n  sauvegarde : {os.path.basename(sortie)}")

with cx.cursor() as c:
    for r in lignes:
        c.execute("UPDATE cb_tarifs SET montant = NULL WHERE id = %s", [r[0]])
cx.commit()
print(f"  {len(lignes)} montants effacés (NULL — inconnu, et non plus « 2,1 FCFA »)")
cx.close()
print()
