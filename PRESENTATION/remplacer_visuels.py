# -*- coding: utf-8 -*-
"""
remplacer_visuels.py — vrai logo SGCI + illustration banque a la place des stocks-photos
==========================================================================================
Demande du 2026-09-15 : "TU VAS METTRE LE LOGO DE LA SGCI... que de mettre photo de
blanc ou autre chose", puis precision le meme jour : "l'image de banque que j'ai donne
la n'est pas pour la page de garde mais la slide 3" -- la page de garde n'a donc PLUS
droit a l'illustration banque (ses deux cadres photo sont retires, cadre/ombre gardes,
juste sans photo dedans) ; la slide 3 recoit desormais sa propre image, posee directement
dans briques_maison.py (elle est hors gabarit Canva, construite a la main).

Deux traitements, tous deux post-assemblage (apres construire_soutenance.py +
injecter_texte.py) :

1. Les VRAIES photos de personnes restantes (stock Canva, .jpeg, diapos 6/7/8/9/12/13/15)
   -> l'illustration generique de banque fournie. Distinguees des textures/icones
   decoratives (fonds degrades, motifs, ombres) par le format de fichier : verifie en
   extrayant chaque a:blip et en les regardant -- toutes les .png rencontrees dans ces
   diapos sont des textures/ombres, toutes les .jpeg sont des photos de personnes. Le
   blob est remplace EN PLACE (meme forme, meme decoupe/masque d'origine).

2. L'icone generique (Freeform ~0.75x0.75in, a cote du texte "SGCI") sur les diapos 1, 6,
   7, 15 -> le vrai logo SGCI (image fournie). L'icone et le texte "SGCI" adjacent sont
   retires, remplaces par UNE image contenant deja le nom complet.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.opc.packuri import PackURI
from pptx.util import Emu, Inches

ICI = os.path.dirname(os.path.abspath(__file__))
FICHIER = os.path.join(ICI, "SpyBusiness_Soutenance.pptx")

ILLUSTRATION_BANQUE = r"C:\Users\ALPHEE COLOMBE\Desktop\PPTX\image\sgci.png"
LOGO_SGCI = r"C:\Users\ALPHEE COLOMBE\Desktop\images\SGCI.png"

prs = Presentation(FICHIER)
S = list(prs.slides)

# ── 0. Page de garde (diapo 1) : on retire les 2 photos, on garde cadre/ombre ───────────
GARDE_PHOTOS = ("Group 21", "Group 43")
n_retires = 0
formes_garde = {sh.name: sh for sh in S[0].shapes}
for nom in GARDE_PHOTOS:
    sh = formes_garde.get(nom)
    if sh is not None:
        sh._element.getparent().remove(sh._element)
        n_retires += 1
print(f"{n_retires} photo(s) retiree(s) de la page de garde (cadre/ombre conserves)")

# ── 1. Photos de personnes restantes -> illustration banque ─────────────────────────────
with open(ILLUSTRATION_BANQUE, "rb") as f:
    nouveau_blob = f.read()

traites = set()
n_photos = 0
for s in S[1:]:   # jamais la page de garde (retiree ci-dessus, plus rien a y remplacer)
    for sh in s.shapes:
        for b in sh._element.findall(".//" + qn("a:blip")):
            rid = b.get(qn("r:embed"))
            if not rid:
                continue
            try:
                part = s.part.related_part(rid)
            except KeyError:
                continue
            ext = str(part.partname).rsplit(".", 1)[-1].lower()
            if ext not in ("jpg", "jpeg"):
                continue   # jamais les .png : ce sont des textures/ombres, pas des photos
            if id(part) in traites:
                continue
            traites.add(id(part))
            part._blob = nouveau_blob
            part._content_type = "image/png"
            base = str(part.partname).rsplit(".", 1)[0]
            part.partname = PackURI(base + ".png")   # extension coherente avec le contenu
            n_photos += 1
print(f"{n_photos} photo(s) de personnes remplacees par l'illustration banque")

# ── 2. Icone generique + texte "SGCI" -> vrai logo SGCI ─────────────────────────────────
# (slide 0-based, nom de l'icone, nom du texte, position/taille du logo)
SPOTS = [
    (0,  "Freeform 26", "TextBox 27", Inches(16.55), Inches(1.05), Inches(2.30)),
    (5,  "Freeform 27", "TextBox 28", Inches(2.03),  Inches(1.00), Inches(2.30)),
    (6,  "Freeform 27", "TextBox 28", Inches(2.03),  Inches(1.00), Inches(2.30)),
    (14, "Freeform 26", "TextBox 27", Inches(16.55), Inches(1.05), Inches(2.30)),
]
RATIO = 200 / 320   # hauteur/largeur reelles du fichier logo (320x200 px)

n_logos = 0
for idx, nom_icone, nom_texte, x, y, larg in SPOTS:
    s = S[idx]
    formes = {sh.name: sh for sh in s.shapes}
    icone = formes.get(nom_icone)
    if icone is not None:
        icone._element.getparent().remove(icone._element)
    texte_sh = formes.get(nom_texte)
    if texte_sh is not None:
        texte_sh._element.getparent().remove(texte_sh._element)
    haut = Emu(int(larg * RATIO))
    s.shapes.add_picture(LOGO_SGCI, x, y, width=larg, height=haut)
    n_logos += 1
print(f"{n_logos} logo(s) SGCI poses (icone generique + texte retires)")

prs.save(FICHIER)
print(f"-> {FICHIER}")
