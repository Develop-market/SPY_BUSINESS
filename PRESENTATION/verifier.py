# -*- coding: utf-8 -*-
"""
verifier.py — ouvre un .pptx dans le VRAI PowerPoint et exporte chaque diapo en PNG.
=====================================================================================
Un fichier .pptx qui "compile" sans exception Python ne prouve rien : un bloc XML mal
forme (transition, timing, gradFill mal insere) fait soit echouer l'ouverture, soit
disparaitre silencieusement l'element concerne. La seule verification qui compte est
visuelle, dans PowerPoint reel.

    python verifier.py <fichier.pptx> [dossier_sortie]
"""
import os
import sys
import time

import win32com.client as w

fichier = sys.argv[1] if len(sys.argv) > 1 else "squelette.pptx"
fichier = os.path.abspath(fichier)
dossier = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else "vues")
os.makedirs(dossier, exist_ok=True)
for f in os.listdir(dossier):
    os.remove(os.path.join(dossier, f))

app = w.Dispatch("PowerPoint.Application")
app.Visible = True   # certaines versions exigent une fenetre pour l'export image fiable
try:
    pres = app.Presentations.Open(fichier, WithWindow=True)
    time.sleep(1.0)
    n = pres.Slides.Count
    print(f"ouvert : {n} diapositives")
    for i in range(1, n + 1):
        cible = os.path.join(dossier, f"vue_{i:02d}.png")
        pres.Slides(i).Export(cible, "PNG", 1920, 1080)
    pres.Close()
    print(f"exporte {n} images -> {dossier}")
finally:
    app.Quit()
