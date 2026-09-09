# -*- coding: utf-8 -*-
"""
verifier.py — controle du diaporama dans le VRAI PowerPoint
============================================================
Le XML d animation est injecte a la main (cf. socle.py). PowerPoint est strict : un bloc mal
forme fait echouer l ouverture, ou pire, disparaitre l animation SANS message. Une generation
« sans erreur Python » ne prouve donc rien.

Ce script ouvre le fichier dans PowerPoint, interroge son modele objet — c est PowerPoint
lui-meme qui repond, pas notre XML relu — et exporte chaque vue en image.

    python PRESENTATION/verifier.py
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import win32com.client as win32

ICI = os.path.dirname(os.path.abspath(__file__))
PPTX = os.path.join(ICI, "soutenance_zongo.pptx")
VUES = os.path.join(ICI, "vues")
os.makedirs(VUES, exist_ok=True)

if not os.path.exists(PPTX):
    print("  fichier absent — lancer d'abord deck.py")
    sys.exit(1)

app = win32.Dispatch("PowerPoint.Application")
pres = None
try:
    pres = app.Presentations.Open(PPTX, WithWindow=False)
    print(f"  ouverture : OK — {pres.Slides.Count} diapositives\n")
    print(f"  {'#':>3}  {'formes':>7}  {'anim.':>6}  {'transition':<14}  premiere ligne")
    print("  " + "-" * 74)

    total_anim = 0
    for i in range(1, pres.Slides.Count + 1):
        sl = pres.Slides(i)

        # Nombre d effets d entree reellement reconnus par PowerPoint.
        try:
            n_anim = sl.TimeLine.MainSequence.Count
        except Exception:                                  # noqa: BLE001
            n_anim = -1
        total_anim += max(n_anim, 0)

        # Transition : EffectType != 0 signifie qu il y en a une.
        try:
            eff = sl.SlideShowTransition.EntryEffect
        except Exception:                                  # noqa: BLE001
            eff = 0
        trans = "aucune" if eff in (0, 513) else f"code {eff}"

        # Premier texte non vide, pour reconnaitre la diapositive d un coup d oeil.
        titre = ""
        for sh in sl.Shapes:
            if sh.HasTextFrame and sh.TextFrame.HasText:
                t = sh.TextFrame.TextRange.Text.strip().replace("\n", " ")
                if len(t) > 3:
                    titre = t[:38]
                    break

        print(f"  {i:>3}  {sl.Shapes.Count:>7}  {n_anim:>6}  {trans:<14}  {titre}")
        sl.Export(os.path.join(VUES, f"vue_{i:02d}.png"), "PNG", 1600, 900)

    print("  " + "-" * 74)
    print(f"  effets d'entree reconnus par PowerPoint : {total_anim}")
    print(f"  vues exportees dans : {VUES}")
finally:
    if pres is not None:
        pres.Close()
    app.Quit()
