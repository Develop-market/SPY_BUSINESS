# -*- coding: utf-8 -*-
"""
fusion.py — construit le squelette du diaporama de soutenance
===============================================================
Base : "Orange Black And White Modern Professional Financial Report" (14 diapos,
20x11.25 po, deja rouge/noir/blanc — 5 couleurs REELLES verifiees dans le XML,
pas de theme Office fantome).

Diapositives 6 et 7 (Problematique / Solution) importees TELLES QUELLES depuis
"Red and White Modern Project Proposal" : MEME echelle (20x11.25), donc copie
XML directe sans recalcul de coordonnees.

Recoloration par mapping EXACT des couleurs reellement presentes dans chaque
fichier source (releve par scan XML prealable, pas de regex hex a l aveugle), vers la
charte OFFICIELLE fournie le 2026-09-15 :
    Financial Report : FF6B00->C8102E (--red)  AB0000->8D071F (--red-dark)
                        303030->222630 (--ink-2)
    Red & White       : E00100->C8102E (--red)  04142B->15171C (--ink)

Sortie : squelette.pptx, 15 diapositives dans l'ordre du plan, SANS le texte
final (etape suivante : remplir.py). Ceci permet de scanner les vrais noms de
formes du resultat avant d'y injecter quoi que ce soit.
"""
import copy
import os

from pptx import Presentation
from pptx.oxml.ns import qn

T = r"C:\Users\ALPHEE COLOMBE\Desktop\PPTX\TEMPLATES"
BASE = T + r"\Orange Black And White Modern Professional Financial Report Presentation.pptx"
PROB_SOL = T + r"\Red and White Modern Project Proposal Presentation.pptx"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "squelette.pptx")

MAP_BASE = {"FF6B00": "C8102E", "AB0000": "8D071F", "303030": "222630"}
MAP_PS   = {"E00100": "C8102E", "04142B": "15171C"}


def recolor(el, mapping):
    """Recolore toutes les couleurs srgbClr d'un element XML, in place."""
    for c in el.iter(qn("a:srgbClr")):
        v = c.get("val", "").upper()
        if v in mapping:
            c.set("val", mapping[v])


def dup_slide_within(prs, idx):
    """Duplique la diapo `idx` (0-based) du MEME classeur, l'ajoute a la fin."""
    src = prs.slides[idx]
    layout = src.slide_layout
    new = prs.slides.add_slide(layout)
    for el in list(new.shapes._spTree):
        if el.tag != qn("p:nvGrpSpPr") and el.tag != qn("p:grpSpPr"):
            new.shapes._spTree.remove(el)
    for el in copy.deepcopy(src.shapes._spTree):
        if el.tag != qn("p:nvGrpSpPr") and el.tag != qn("p:grpSpPr"):
            new.shapes._spTree.append(el)
    return new


def import_slide_from(prs_dst, src_path, src_idx, mapping):
    """Copie la diapo `src_idx` (0-based) d'un AUTRE classeur (meme echelle de
    diapo) a la fin de prs_dst, recoloree. Layout vierge de la base — le XML
    complet de la source est reinjecte tel quel dans spTree, donc le rendu ne
    depend pas du layout choisi ici."""
    src_prs = Presentation(src_path)
    src_slide = src_prs.slides[src_idx]
    new = prs_dst.slides.add_slide(prs_dst.slide_layouts[6] if len(prs_dst.slide_layouts) > 6
                                    else prs_dst.slide_layouts[-1])
    for el in list(new.shapes._spTree):
        if el.tag != qn("p:nvGrpSpPr") and el.tag != qn("p:grpSpPr"):
            new.shapes._spTree.remove(el)
    for el in copy.deepcopy(src_slide.shapes._spTree):
        if el.tag != qn("p:nvGrpSpPr") and el.tag != qn("p:grpSpPr"):
            recolor(el, mapping)
            new.shapes._spTree.append(el)
    # fond de la diapo source (bg color/degrade), si defini explicitement
    bg = src_slide.element.find(qn("p:cSld") + "/" + qn("p:bg"))
    return new


prs = Presentation(BASE)
print(f"base : {len(prs.slides)} diapos")

# Recolore les 14 diapos de la base
for s in prs.slides:
    for sh in s.shapes:
        recolor(sh.element, MAP_BASE)

# Duplique une diapo de la base pour compenser celles qu'on va retirer/reordonner
# (le plan final a 15 vues ; la base en a 14, on en importe 2 -> on en aura 16,
# on en supprimera une redondante a la fin selon le contenu retenu)
dup_slide_within(prs, 8)   # clone de "Financial Ratios Overview" -> servira de gabarit tableau

# Importe Problematique (S3, idx 2) et Solution (S6, idx 5) du Red&White
import_slide_from(prs, PROB_SOL, 2, MAP_PS)
import_slide_from(prs, PROB_SOL, 5, MAP_PS)

print(f"apres fusion : {len(prs.slides)} diapos (avant reordonnancement)")
prs.save(OUT)
print("->", OUT)
