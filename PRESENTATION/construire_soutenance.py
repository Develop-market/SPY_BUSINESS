# -*- coding: utf-8 -*-
"""
construire_soutenance.py — assemble le diaporama final
========================================================
Base : "Orange Black And White Modern Professional Financial Report" (14 diapos,
20x11.25in), recoloree vers la charte SGCI officielle (#C8102E).

Plan des 15 vues -- revu le 2026-09-15 : "Entreprise" et "Direction de l'Innovation"
tenaient sur 2 diapos distinctes (Risk Management + organigramme importes du template) ;
fusionnees en UNE seule diapo a deux vues bascule-au-clic (chiffres SGCI en cercles <->
Direction de l'Innovation), entierement construite a la main (briques_maison.py) --
le gabarit "Risk Management" ne permettait ni les chiffres en cercle demandes, ni une
seconde vue cachee. Verifie diapo par diapo dans le vrai PowerPoint avant d'ecrire ce
mapping :
    1  Garde                          <- base s1
    2  Sommaire                       <- maison (construite, socle.py)
    3  Entreprise + Direction Innov.  <- maison (construite, 2 vues au clic, organigramme reel)
    4  Contexte (donnee inexploitee)  <- base s4  (Business Environment, 4 pilules)
    5  Evolution du RAG               <- maison (construite)
    6  Problematique                  <- Red&White s3 (STATEMENT PROBLEM), meme echelle
    7  Solution proposee              <- Red&White s6 (SOLUTION PROPOSED), meme echelle
    8  Implementation 1 (extraction)  <- base s5  (Cost Structure, 3 cercles)
    9  Implementation 2 (base donn.)  <- base s7  (Financial Position, 2 photos+3 pilules)
    10 Socle commun, 2 modes          <- maison (construite)
    11 Les deux architectures         <- maison (construite)
    12 Evaluation (4 mesures)         <- base s11 (Financial Control, grille 2x2)
    13 Architecture retenue           <- base s5  DUPLIQUEE (3 cercles, autre theme)
    14 Projection a 3 ans             <- base s13 (Future Projections, 4 pilules icone)
    15 Merci                         <- base s14 (Thank You)

Chiffres utilises : UNIQUEMENT ceux verifies dans le memoire (Tableau 5, chapitre
evaluation) -- jamais une valeur plausible. Note explicite la ou un chiffre du script
precedent (modifier_template_final.py, abandonne) etait FAUX :
    - 169 questions de reference (pas 114)
    - Exactitude 100,0% / 99,1%, appels 1 / 2,4, latence mediane 2,1s / 4,4s (Tableau 5)
    - McNemar exactitude p = 1,000 (ecart NON etabli)
    - Cout prestataire externe ~10 M FCFA/analyse, 2 mois de delai (pas 30 M)
"""
import copy
import os
import sys

from lxml import etree
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.packuri import PackURI
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ICI = os.path.dirname(os.path.abspath(__file__))
T = r"C:\Users\ALPHEE COLOMBE\Desktop\PPTX\TEMPLATES"
BASE = T + r"\Orange Black And White Modern Professional Financial Report Presentation.pptx"
PROB_SOL = T + r"\Red and White Modern Project Proposal Presentation.pptx"
MAISON = os.path.join(ICI, "maison.pptx")
OUT = os.path.join(ICI, "SpyBusiness_Soutenance.pptx")

MAP_BASE = {"FF6B00": "C8102E", "AB0000": "8D071F", "303030": "222630"}
MAP_PS   = {"E00100": "C8102E", "04142B": "15171C"}

# echelle maison.pptx (13.333x7.5in) -> format retenu (20x11.25in) : meme ratio 16:9
ECH_MAISON = 20.0 / 13.333


def recolor(el, mapping):
    for c in el.iter(qn("a:srgbClr")):
        v = c.get("val", "").upper()
        if v in mapping:
            c.set("val", mapping[v])


def scale_shape(sp_el, k):
    """Multiplie par k le a:xfrm (off + ext) de CETTE forme de premier niveau seulement.
    Ne PAS descendre dans les groupes : chOff/chExt gere deja la mise a l'echelle interne
    -- toucher aux enfants en plus doublerait l'effet et deformerait tout."""
    # xfrm direct de la forme (pas d'un enfant de groupe) : spPr (formes simples) ou
    # grpSpPr (groupes), jamais les deux -- on itere sur des shapes de PREMIER NIVEAU
    # seulement (voir appelant), donc pas d'ambiguite avec un xfrm imbrique.
    spPr = sp_el.find(qn("p:spPr"))
    if spPr is None:
        spPr = sp_el.find(qn("p:grpSpPr"))
    if spPr is None:
        return
    xfrm = spPr.find(qn("a:xfrm"))
    if xfrm is None:
        return
    off = xfrm.find(qn("a:off"))
    ext = xfrm.find(qn("a:ext"))
    if off is not None:
        off.set("x", str(int(int(off.get("x")) * k)))
        off.set("y", str(int(int(off.get("y")) * k)))
    if ext is not None:
        ext.set("cx", str(int(int(ext.get("cx")) * k)))
        ext.set("cy", str(int(int(ext.get("cy")) * k)))


NIVEAU1 = {qn(t) for t in ("p:sp", "p:grpSp", "p:pic", "p:cxnSp", "p:graphicFrame")}

# Attributs qui portent un rId vers une image. BUG TROUVE en verifiant visuellement
# (vue 3, 6) : copier le XML d'une shape avec copy.deepcopy() copie bien l'attribut
# r:embed="rIdXX", mais PAS la relation elle-meme (le lien vers le fichier image dans
# ppt/media/ du classeur SOURCE) -- ce rId n'existe pas dans le classeur de DESTINATION,
# donc PowerPoint affiche "Nous ne pouvons pas afficher l'image.". Il faut recreer la
# relation manuellement pour chaque rId rencontre. On se limite a embed/link (toujours
# des images en pratique dans ces templates) : r:id generique sert a bien d'autres
# choses (hyperliens, theme...) et melanger les types de relation serait plus risque
# que de laisser un hyperlien externe intact.
ATTRS_RID = (qn("r:embed"), qn("r:link"))

# BUG 2 (decouvert juste apres le fix du bug 1) : 3 classeurs source distincts (base,
# Red&White, maison) ont chacun leurs propres images numerotees a partir de zero par
# Canva/python-pptx ("image9.png", "image10.svg"...). Une fois reliees dans le classeur
# de DESTINATION, deux images DIFFERENTES peuvent hereter du meme partname d'origine ->
# collision silencieuse a l'ecriture du zip (avertissement "Duplicate name", classeur
# corrompu, une des deux images perdue). Compteur global : chaque image importee recoit
# un partname garanti unique dans le classeur final, quelle que soit sa source.
_compteur_images = [0]


def _nom_unique(partname_src):
    _compteur_images[0] += 1
    ext = str(partname_src).rsplit(".", 1)[-1]
    return PackURI(f"/ppt/media/imp{_compteur_images[0]:04d}.{ext}")


def _reporter_images(el, slide_src, slide_dst, cache):
    """Pour chaque r:embed/r:link trouve dans `el`, copie l'image de slide_src vers
    slide_dst (avec un partname neuf, garanti unique) et reecrit le rId. `cache` evite
    de dupliquer la meme image plusieurs fois dans une diapo qui la reutilise (logos,
    motifs decoratifs repetes)."""
    for noeud in el.iter():
        for attr in ATTRS_RID:
            ancien_rid = noeud.get(attr)
            if not ancien_rid:
                continue
            try:
                part_source = slide_src.part.related_part(ancien_rid)
            except KeyError:
                continue   # rId orphelin dans la source -- rien a reporter
            cle = id(part_source)
            if cle not in cache:
                part_source.partname = _nom_unique(part_source.partname)
                cache[cle] = slide_dst.part.relate_to(part_source, RT.IMAGE)
            noeud.set(attr, cache[cle])


def import_slide(prs_dst, src_prs, src_idx, mapping, echelle=1.0):
    """Copie la diapo `src_idx` (0-based) de src_prs a la fin de prs_dst, recoloree,
    mise a l'echelle si besoin, AVEC ses images correctement reliees. Retourne la
    nouvelle diapo."""
    src_slide = src_prs.slides[src_idx]
    new = prs_dst.slides.add_slide(prs_dst.slide_layouts[6])
    for el in list(new.shapes._spTree):
        if el.tag not in (qn("p:nvGrpSpPr"), qn("p:grpSpPr")):
            new.shapes._spTree.remove(el)
    cache_images = {}
    for el in copy.deepcopy(src_slide.shapes._spTree):
        if el.tag in NIVEAU1:
            recolor(el, mapping)
            if echelle != 1.0:
                scale_shape(el, echelle)
            _reporter_images(el, src_slide, new, cache_images)
            new.shapes._spTree.append(el)
    return new


def dup_slide_within(prs, idx):
    """Duplique la diapo `idx` (0-based) du MEME classeur, deja recoloree."""
    src = prs.slides[idx]
    new = prs.slides.add_slide(prs.slide_layouts[6])
    for el in list(new.shapes._spTree):
        if el.tag not in (qn("p:nvGrpSpPr"), qn("p:grpSpPr")):
            new.shapes._spTree.remove(el)
    for el in copy.deepcopy(src.shapes._spTree):
        if el.tag not in (qn("p:nvGrpSpPr"), qn("p:grpSpPr")):
            new.shapes._spTree.append(el)
    return new


def par_nom(slide):
    """Dict {nom_de_forme: shape} pour cette diapo -- cible les formes par leur nom Canva
    plutot que par position, plus lisible et plus sur."""
    return {sh.name: sh for sh in slide.shapes}


def texte(slide, nom, contenu):
    """Remplace le texte d'une forme nommee, EN GARDANT la police/couleur du premier
    run existant (celle du designer). Coupe sur les '\\n' -> un paragraphe par ligne."""
    formes = par_nom(slide)
    sh = formes.get(nom)
    if sh is None or not sh.has_text_frame:
        print(f"  ATTENTION forme absente : {nom!r}")
        return
    tf = sh.text_frame
    tf.word_wrap = True
    p0 = tf.paragraphs[0]
    style = None
    if p0.runs:
        r0 = p0.runs[0]
        style = (r0.font.name, r0.font.size, r0.font.bold)
        try:
            style += (r0.font.color.rgb,)
        except Exception:
            style += (None,)
    for p in list(tf.paragraphs):
        for r in list(p.runs):
            r.text = ""
    lignes = contenu.split("\n")
    for i, ligne_txt in enumerate(lignes):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        if i > 0 and tf.paragraphs[0].alignment:
            p.alignment = tf.paragraphs[0].alignment
        r = p.runs[0] if p.runs else p.add_run()
        r.text = ligne_txt
        if style:
            nom_f, taille_f, gras_f, coul_f = style
            if nom_f:
                r.font.name = nom_f
            if taille_f:
                r.font.size = taille_f
            if gras_f is not None:
                r.font.bold = gras_f
            if coul_f:
                try:
                    r.font.color.rgb = coul_f
                except Exception:
                    pass


def taille(slide, nom, pt):
    """Force la taille de police (utile quand le texte francais est plus long que
    l'anglais d'origine et deborde -- reduit AVANT que ca ne devienne un probleme,
    plutot que de le decouvrir a la verification visuelle)."""
    formes = par_nom(slide)
    sh = formes.get(nom)
    if sh is None or not sh.has_text_frame:
        return
    for p in sh.text_frame.paragraphs:
        for r in p.runs:
            r.font.size = Pt(pt)


def masquer(slide, nom):
    """Retire une forme (ex. le graphique-image generique 'Item1-4/Series1-3' qui ne
    correspond a aucune donnee reelle -- on ne montre pas un graphique invente)."""
    formes = par_nom(slide)
    sh = formes.get(nom)
    if sh is not None:
        sh._element.getparent().remove(sh._element)


# ═════════════════════════════════════════════════════════════════════════════════════
#  ASSEMBLAGE
# ═════════════════════════════════════════════════════════════════════════════════════
base_prs = Presentation(BASE)
ps_prs = Presentation(PROB_SOL)
maison_prs = Presentation(MAISON)

prs = Presentation(BASE)   # on part de la base pour heriter slideMaster/layouts/theme
# on vide toutes les diapos existantes : on va les reimporter nous-memes, dans l'ordre.
for i in range(len(prs.slides) - 1, -1, -1):
    rId = prs.slides._sldIdLst[i].get(qn("r:id"))
    prs.part.drop_rel(rId)
    del prs.slides._sldIdLst[i]

ordre = [
    ("base", 0),    # 1  Garde
    ("maison", 0),  # 2  Sommaire
    ("maison", 1),  # 3  Entreprise + Direction de l'Innovation (2 vues au clic)
    ("base", 3),    # 4  Contexte
    ("maison", 2),  # 5  RAG
    ("ps", 2),      # 6  Problematique
    ("ps", 5),      # 7  Solution
    ("base", 4),    # 8  Implementation 1
    ("base", 6),    # 9  Implementation 2
    ("maison", 3),  # 10 Socle commun
    ("maison", 4),  # 11 Deux architectures
    ("base", 10),   # 12 Evaluation
    ("base", 4),    # 13 Architecture retenue (meme source que 8, reutilisee)
    ("base", 12),   # 14 Projection
    ("base", 13),   # 15 Merci
]

slides_finales = []
for src, idx in ordre:
    if src == "base":
        sl = import_slide(prs, base_prs, idx, MAP_BASE, echelle=1.0)
    elif src == "ps":
        sl = import_slide(prs, ps_prs, idx, MAP_PS, echelle=1.0)
    else:
        sl = import_slide(prs, maison_prs, idx, {}, echelle=ECH_MAISON)
    slides_finales.append(sl)

print(f"assemblage : {len(prs.slides)} diapositives")
prs.save(OUT)
print("->", OUT, "(squelette, texte pas encore injecte)")
