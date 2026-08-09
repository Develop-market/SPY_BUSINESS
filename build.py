"""Installe les dépendances de production — appelé par Render (cf. render.yaml).

Même raison d'être que wsgi.py : le fichier d'inventaire vit dans « SGCI Strategic
Intelligence — Design System/spybusiness », un chemin qui contient des espaces et un tiret
cadratin. Passé à pip depuis la ligne de commande, il dépend du découpage opéré par
l'interpréteur — pip a d'ailleurs échoué à l'essai, en coupant le chemin au premier espace.
Résolu ici en Python, le problème disparaît.

Le fichier est CHERCHÉ, non écrit en dur : renommer le dossier ne cassera pas la construction.
"""
import glob
import os
import subprocess
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
trouves = glob.glob(os.path.join(RACINE, "*", "spybusiness", "requirements-deploy.txt"))
if not trouves:
    sys.exit("requirements-deploy.txt introuvable sous <dossier>/spybusiness/ à la racine.")

inventaire = trouves[0]
print(f"[build] inventaire : {os.path.relpath(inventaire, RACINE)}")
subprocess.check_call([sys.executable, "-m", "pip", "install",
                       "--no-cache-dir", "-r", inventaire])
print("[build] dépendances installées")
