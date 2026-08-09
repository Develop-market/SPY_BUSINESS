"""Point d'entrée WSGI — c'est ce fichier que gunicorn charge en production.

POURQUOI IL EXISTE. L'application vit dans « SGCI Strategic Intelligence — Design System/
spybusiness », un chemin qui contient des espaces ET un tiret cadratin. Faire démarrer le
serveur par un `cd` vers ce dossier, depuis la ligne de commande d'un hébergeur, revient à
parier que son interpréteur de commandes traitera ces octets exactement comme le nôtre. C'est
généralement vrai ; ce n'est pas garanti, et un échec se produirait au démarrage, en
production, avec un message obscur.

Python, lui, manipule les chemins sans passer par un interpréteur de commandes. On localise
donc le dossier ICI, et gunicorn n'a plus qu'à charger « wsgi:app » depuis la racine du dépôt.

Le dossier est CHERCHÉ plutôt qu'écrit en dur : le jour où il sera renommé — et son nom
actuel invite au renommage — le déploiement continuera de fonctionner.
"""
import os
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))


def _dossier_application():
    """Chemin du dossier contenant server.py, quel que soit le nom du dossier parent."""
    direct = os.path.join(RACINE, "SGCI Strategic Intelligence — Design System", "spybusiness")
    if os.path.isfile(os.path.join(direct, "server.py")):
        return direct
    # Repli : on balaie la racine. Deux niveaux suffisent et évitent de parcourir DATA/,
    # qui contient des milliers de fichiers.
    for entree in sorted(os.listdir(RACINE)):
        candidat = os.path.join(RACINE, entree, "spybusiness")
        if os.path.isfile(os.path.join(candidat, "server.py")):
            return candidat
    raise RuntimeError(
        "server.py introuvable : ni sous « SGCI Strategic Intelligence — Design System/"
        "spybusiness », ni ailleurs à la racine du dépôt.")


APPLICATION = _dossier_application()

# server.py importe ses voisins par leur nom seul (db, securite, directives…) : son dossier et
# son sous-dossier dash_app doivent donc être sur le chemin de recherche, comme lorsqu'on le
# lance directement.
for chemin in (APPLICATION, os.path.join(APPLICATION, "dash_app"), os.path.join(RACINE, "RAG")):
    if os.path.isdir(chemin) and chemin not in sys.path:
        sys.path.insert(0, chemin)

# Certains chemins internes se calculent à partir du répertoire courant : on s'y place, comme
# le ferait un démarrage local.
os.chdir(APPLICATION)

from server import app          # noqa: E402  (l'import doit suivre la préparation du chemin)

# Nom attendu par gunicorn : « wsgi:app ».
application = app
