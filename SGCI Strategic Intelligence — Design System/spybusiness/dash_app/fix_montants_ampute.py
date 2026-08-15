"""
fix_montants_ampute.py — repare les montants coupes sur leur espace de milliers (2026-08-15)
============================================================================================
TROUVE en auditant les « 339 lignes a 0 non marquees gratuites » annoncees comme un defaut de
GRATUITE. Ce n'en est pas un. Les marquer gratuites aurait invente des services gratuits :

    libelle « Mainlevee d'hypotheque: 40 »   valeur_propre « 000 FCFA »   montant 0
                                                        le vrai tarif est 40 000 FCFA

L'extraction a coupe « 40 000 FCFA » sur son espace de milliers. La tete du nombre est restee
collee a la fin du LIBELLE, la queue est devenue la VALEUR, et le montant s'est effondre a 0.

POURQUOI C'EST GRAVE. Un tarif a 0 n'est pas une valeur approximative : dans un comparatif de
prix, c'est le MOINS CHER du marche. Ces lignes placent donc artificiellement une banque en
tete sur des services qu'elle facture en realite des dizaines de milliers de francs.

METHODE — on ne devine aucun montant, on le RECOLLE.
La signature doit etre certaine sur les deux moities :
  * la valeur brute n'est QUE des zeros, eventuellement suivis de FCFA (« 000 », « 000 FCFA »,
    « 000000 ») — donc une queue de nombre, jamais un prix ;
  * le libelle se TERMINE par un nombre — donc une tete de nombre.
On rend alors tete x 10^(nombre de zeros). Tout le reste est laisse intact.

CE QUI EST EXCLU, ET POURQUOI :
  * « 0 » seul : rien ne dit que c'est une troncature ; ce peut etre un vrai zero.
  * « Taux : 0% » : un taux de zero pour cent est une valeur REELLE, pas une amputation.
  * « 00:04 » : une duree, pas un montant. Traitee a part (montant mis a NULL).
  * les lignes dont le libelle ne finit pas par un nombre : la tete est introuvable, on ne
    fabrique rien.

IDEMPOTENT : une ligne reparee n'a plus la signature (sa valeur brute est reecrite), elle
n'est donc plus reprise au passage suivant.

USAGE :
    python fix_montants_ampute.py             # SIMULATION : affiche, n'ecrit rien
    python fix_montants_ampute.py --appliquer # ecrit en base, apres sauvegarde CSV
"""
import csv
import os
import re
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

# Queue de nombre : EXACTEMENT un groupe de milliers perdu, eventuellement suivi de la devise.
#
# Pourquoi exactement trois zeros. Les formes « 000000 » ont ete essayees puis ECARTEES : deux
# groupes manquants laissent le raccord ambigu, et la simulation a produit des montants
# absurdes — « Gratuit a 500 » + « 000000 » donnait 500 000 000 FCFA de frais bancaires.
# Devant une ambiguite, on ne repare pas : on laisse la ligne telle quelle.
QUEUE = re.compile(r"^\s*0{3}\s*(?:F\s?CFA|FCFA|F)?\s*$", re.I)

# Duree deguisee en montant : « 00:04 ».
DUREE = re.compile(r"^\s*\d{1,2}\s*:\s*\d{2}\s*$")

# Plafond de vraisemblance. Ces lignes sont des tarifs unitaires ou des seuils ; au-dela, le
# raccord est plus probablement une erreur de lecture qu'un tarif reel. On ne corrige pas ce
# qu'on ne peut pas croire.
PLAFOND = 2_000_000


def recoller(libelle, brute):
    """Rend le montant reconstitue, ou None si la signature n'est pas certaine.

    La tete doit etre un nombre COURT et AUTONOME en fin de libelle. Trois refus, chacun
    verifie sur des cas reels de la base :
      * une tete de plus de trois chiffres, ou porteuse de son propre separateur, signifie que
        le libelle contient DEJA le montant entier — « Maximum 150 000 » suivi de « 000 » est
        un doublon d'extraction, pas une queue manquante. Recoller aurait donne 150 000 000.
      * une tete faite de zeros (« ...150 000 » dont on ne lit que « 000 ») ne dit rien.
      * une tete precedee d'un chiffre ou d'un separateur prolonge un nombre plus grand.
    """
    if not QUEUE.match(brute or ""):
        return None

    lib = (libelle or "").rstrip()
    t = re.search(r"(\d+)\s*$", lib)
    if not t:
        return None
    tete = t.group(1)
    if len(tete) > 3 or set(tete) == {"0"}:
        return None

    avant = lib[:t.start(1)]
    if avant and (avant[-1].isdigit() or avant[-1] in ".,"):
        return None
    if re.search(r"\d[\s.,]$", avant):          # « 150 » + espace + « 000 » : meme nombre
        return None

    valeur = float(tete) * 1000
    return valeur if valeur <= PLAFOND else None


cx = psycopg2.connect(**DB)
print(f"\n  base : {DB['dbname']}@{DB['host']}")

with cx.cursor() as c:
    c.execute("""SELECT id, banque, annee, semestre, libelle, valeur_propre, montant
                 FROM cb_tarifs
                 WHERE montant = 0 AND COALESCE(est_gratuit, FALSE) = FALSE
                 ORDER BY banque, annee, semestre""")
    lignes = c.fetchall()

reparables, durees, laissees = [], [], []
for rid, banque, annee, sem, libelle, brute, montant in lignes:
    if DUREE.match(brute or ""):
        durees.append((rid, banque, annee, sem, libelle, brute))
        continue
    v = recoller(libelle, brute)
    if v is not None:
        reparables.append((rid, banque, annee, sem, libelle, brute, v))
    else:
        laissees.append((rid, banque, annee, sem, libelle, brute))

print(f"  {len(lignes)} lignes à 0 examinées")
print(f"    {len(reparables):>4} montants reconstituables (tête dans le libellé)")
print(f"    {len(durees):>4} durées prises pour un montant → montant mis à NULL")
print(f"    {len(laissees):>4} laissées intactes (signature non certaine)\n")

for r in reparables[:10]:
    print(f"    {r[1]:8} {r[2]} {r[3]}  « {r[5][:12]:14} » + « …{r[4][-34:]} »  →  {r[6]:,.0f}"
          .replace(",", " "))
if len(reparables) > 10:
    print(f"    … et {len(reparables)-10} autres")

# Repartition des montants reconstitues : un ordre de grandeur aberrant se verrait ici.
if reparables:
    vals = sorted(r[6] for r in reparables)
    print(f"\n    montants reconstitués — min {vals[0]:,.0f} | médiane {vals[len(vals)//2]:,.0f} "
          f"| max {vals[-1]:,.0f}".replace(",", " "))

print("\n  échantillon de ce qui est LAISSÉ INTACT :")
for r in laissees[:6]:
    print(f"    {r[1]:8} « {r[5][:40]:42} »  {r[4][:40]}")

if not APPLIQUER:
    print("\n  (simulation — relancer avec --appliquer pour écrire)\n")
    cx.close()
    sys.exit()

# Sauvegarde AVANT ecriture : l'extraction n'est pas rejouable a l'identique sans le pipeline.
horo = datetime.now().strftime("%Y%m%d_%H%M%S")
sortie = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      f"backup_montants_ampute_{horo}.csv")
with open(sortie, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "banque", "annee", "semestre", "libelle", "valeur_propre",
                "montant_avant", "montant_apres"])
    for r in reparables:
        w.writerow([r[0], r[1], r[2], r[3], r[4], r[5], 0, r[6]])
    for r in durees:
        w.writerow([r[0], r[1], r[2], r[3], r[4], r[5], 0, "NULL"])
print(f"\n  sauvegarde : {os.path.basename(sortie)}")

with cx.cursor() as c:
    for r in reparables:
        c.execute("UPDATE cb_tarifs SET montant = %s WHERE id = %s", [r[6], r[0]])
    for r in durees:
        c.execute("UPDATE cb_tarifs SET montant = NULL WHERE id = %s", [r[0]])
cx.commit()
print(f"  {len(reparables)} montants reconstitués, {len(durees)} durées neutralisées")
cx.close()
print()
