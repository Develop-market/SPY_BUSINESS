# -*- coding: utf-8 -*-
"""
corriger_slide3.py — corrige la diapo ajoutee a la main par l'utilisateur le 2026-09-16
==========================================================================================
IMPORTANT : ce script modifie SpyBusiness_Soutenance.pptx EN PLACE, comme
injecter_texte.py / remplacer_visuels.py -- il ne relance JAMAIS construire_soutenance.py,
qui ecraserait la diapo que l'utilisateur a inseree a la main dans PowerPoint (elle
n'existe dans AUCUN script source, seulement dans le fichier .pptx lui-meme).

Ce qui est corrige, diapo 3 (« Financial Ratios Overview », collee depuis le template
d'origine, donc encore en orange) :
  1. Recoloration orange -> rouge SGCI (memes 3 couleurs que MAP_BASE dans
     construire_soutenance.py : FF6B00/AB0000/303030).
  2. Titre traduit ("Chiffres cles").
  3. Les 4 anciens cercles (en realite des OVALES deformes par une mise a l'echelle de
     groupe non uniforme, cf. Groupe 177/176/72 imbriques) sont retires et remplaces par
     4 VRAIS cercles ronds (meme brique cercle_chiffre-like que la diapo Entreprise),
     avec les VRAIES unites : "276 M"/"101 M" etaient en MILLIONS alors que les chiffres
     verifies du memoire sont en MILLIARDS -> "276,0 Mds" / "101,4 Mds"
     (04_partie1.tex l.33-37). 4e cercle confirme par l'utilisateur : 606 000 clients
     (remplace 504 000, harmonise aussi sur la diapo "Entreprise").
  4. Animation "compteur" (le chiffre defile rapidement avant de se figer sur la valeur
     finale, comme dans l'application SpyBusiness) : PowerPoint n'anime pas un texte qui
     s'incremente tout seul (pas sans macro VBA, fragile et deconseille) -- on simule
     l'effet avec un FLIPBOOK : plusieurs plaques (fond colore + chiffre) superposees au
     meme endroit, qui apparaissent l'une apres l'autre tres vite (~110ms d'ecart), la
     derniere restant affichee. Deja verifie fonctionnel dans un vrai PowerPoint (le
     mecanisme d'entrees chainees d'animer() a ete teste en direct le 2026-09-15).
"""
import io
import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from lxml import etree
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from socle import BLANC, GRIS, NOIR, ROUGE, ROUGE_FONCE, TEXTE, TITRE, animer, para, rect, riche, transition, zone

ICI = os.path.dirname(os.path.abspath(__file__))
FICHIER = os.path.join(ICI, "SpyBusiness_Soutenance.pptx")

MAP_ORANGE_ROUGE = {"FF6B00": "C8102E", "AB0000": "8D071F", "303030": "222630"}


def recolor(el, mapping):
    for c in el.iter(qn("a:srgbClr")):
        v = c.get("val", "").upper()
        if v in mapping:
            c.set("val", mapping[v])


def texte(shape, contenu):
    """Meme technique qu'injecter_texte.py : clone le XML du premier paragraphe (garde
    degrade/police/espacement), ne change que le texte."""
    tf = shape.text_frame
    tf.word_wrap = True
    txBody = tf._txBody
    paras = txBody.findall(qn("a:p"))
    if not paras:
        tf.text = contenu
        return
    modele = deepcopy(paras[0])
    runs_modele = modele.findall(qn("a:r"))
    for r in runs_modele[1:]:
        modele.remove(r)
    for p in list(paras):
        txBody.remove(p)
    for ligne_txt in contenu.split("\n"):
        p_new = deepcopy(modele)
        r_new = p_new.find(qn("a:r"))
        if r_new is None:
            r_new = etree.SubElement(p_new, qn("a:r"))
        t = r_new.find(qn("a:t"))
        if t is None:
            t = etree.SubElement(r_new, qn("a:t"))
        t.text = ligne_txt
        txBody.append(p_new)


prs = Presentation(FICHIER)
S = list(prs.slides)
s3 = S[2]   # diapo 3 (0-based 2) : celle ajoutee a la main

# ── 1. Recoloration orange -> rouge sur TOUTE la diapo ──────────────────────────────────
recolor(s3.shapes._spTree, MAP_ORANGE_ROUGE)

# ── 2. Titre traduit, style (degrade) conserve ───────────────────────────────────────────
formes = {sh.name: sh for sh in s3.shapes}
texte(formes["TextBox 52"], "Chiffres")
texte(formes["TextBox 53"], "clés")

# ── 3. Retrait de l'ancien cluster de 4 ovales deformes (ou d'un panneau deja reconstruit
#      par un run precedent de ce script -- le nom du groupe rend ce script rejouable) ────
for nom in ("Groupe 177", "PanneauChiffresCles"):
    ancien = formes.get(nom)
    if ancien is not None:
        ancien._element.getparent().remove(ancien._element)
        formes = {sh.name: sh for sh in s3.shapes}

# ── 4. 4 VRAIS cercles ronds, chiffres verifies, avec effet compteur ────────────────────
# (valeur finale, unite affichee dans le cercle, libelle sous le cercle, liste des paliers
#  intermediaires du compteur -- SANS l'unite, ajoutee seulement sur la valeur finale)
METRIQUES = [
    ("+50",       "",     "Ans d'existence",      ["0", "18", "34", "+50"]),
    ("276,0",     " Mds", "PNB 2025 (FCFA)",       ["0,0", "92,0", "184,0", "276,0"]),
    ("101,4",     " Mds", "Resultat net (FCFA)",   ["0,0", "34,0", "68,0", "101,4"]),
    ("606 000",   "",     "Clients",               ["0", "200 000", "404 000", "606 000"]),
]

DIAM = Inches(2.22)
CY = Inches(6.30)
CX0 = Inches(7.55)
PAS = Inches(2.85)
COULEURS = [ROUGE, ROUGE, ROUGE_FONCE, ROUGE_FONCE]

toutes_les_plaques = []     # pour l'entree normale (1er clic, cascade classique)
groupes_compteur = []       # les groupes du COMPTEUR proprement dit (2e clic)

for i, (valeur, unite, libelle, paliers) in enumerate(METRIQUES):
    cx = Emu(int(CX0) + i * int(PAS))
    r = Emu(int(DIAM) // 2)
    couleur = COULEURS[i]

    # le cercle plein, fond de la "plaque" -- reste a l'ecran, seul le texte au-dessus
    # change pendant le compteur (immobile, pas de re-fondu du cercle a chaque palier :
    # plus proche d'un vrai compteur, qui ne re-anime jamais son fond).
    cercle = rect(s3, Emu(int(cx) - int(r)), Emu(int(CY) - int(r)), DIAM, DIAM, couleur,
                  forme=MSO_SHAPE.OVAL)
    cercle.text_frame.margin_left = cercle.text_frame.margin_right = 0

    # etiquette sous le cercle
    zone_sh, z = zone(s3, Emu(int(cx) - int(DIAM)), Emu(int(CY) + int(r) + int(Inches(0.16))),
                       Emu(int(DIAM) * 2), Inches(0.55), align=PP_ALIGN.CENTER)
    para(z, libelle, taille=13, gras=True, couleur=NOIR, align=PP_ALIGN.CENTER, premier=True,
         interligne=1.1)

    # les paliers du compteur : une plaque de texte par palier, toutes superposees pile au
    # centre du cercle (meme taille que le cercle, fond TRANSPARENT -- le cercle en-dessous
    # assure deja le fond colore -- seul le texte importe ici).
    plaques = []
    for j, palier in enumerate(paliers):
        texte_affiche = palier + (unite if j == len(paliers) - 1 else "")
        p = rect(s3, Emu(int(cx) - int(r)), Emu(int(CY) - int(r)), DIAM, DIAM, None,
                 forme=MSO_SHAPE.OVAL)
        tf = p.text_frame
        tf.margin_left = tf.margin_right = Inches(0.06)
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        para(tf, texte_affiche, taille=26, gras=True, couleur=BLANC, police=TITRE,
             align=PP_ALIGN.CENTER, premier=True, interligne=0.95)
        plaques.append(p)

    toutes_les_plaques.append(cercle)
    toutes_les_plaques.append(zone_sh)
    # 1er palier : entre normalement avec le reste (1er clic) ; les suivants forment le
    # compteur (2e clic), chacun QUI ENTRE alors que le precedent SORT, tres vite.
    toutes_les_plaques.append(plaques[0])
    for j in range(1, len(plaques)):
        groupes_compteur.append((plaques[j - 1], plaques[j], j == len(plaques) - 1))

transition(s3, "fade", 600)

# 1er clic : le panneau (cercles + etiquettes + 1ere plaque "0") apparait normalement.
sequence = [(toutes_les_plaques, "fondu", 90, 400)]

# 2e clic : le compteur defile -- chaque palier sort pendant que le suivant entre, sur les
# 4 cercles a la fois (memes indices j en parallele) -- on reconstitue les paliers par
# "rang" (1er palier de chaque cercle ensemble, puis 2e...). Ralenti le 2026-09-16 : la
# 1ere version (90ms/palier, 110ms d'ecart) verifiee en direct dans PowerPoint terminait
# en moins de 350ms -- trop rapide pour se voir "compter", ca ressemblait a un flash. Des
# paliers plus longs et plus espaces se VOIENT defiler, comme le compteur de l'appli.
DUREE_PALIER = 260
ECART_RANGS = 230
rangs = {}
idx = 0
for i, (valeur, unite, libelle, paliers) in enumerate(METRIQUES):
    for j in range(1, len(paliers)):
        rangs.setdefault(j, []).append((groupes_compteur[idx][0], groupes_compteur[idx][1]))
        idx += 1

instructions_compteur = []
for rang in sorted(rangs):
    precs = [pr for pr, su in rangs[rang]]
    suivs = [su for pr, su in rangs[rang]]
    decalage = 0 if rang == min(rangs) else ECART_RANGS
    instructions_compteur.append((precs, "fondu", decalage, DUREE_PALIER, "sortie"))
    instructions_compteur.append((suivs, "fondu", 0, DUREE_PALIER, "entree"))
sequence.append(instructions_compteur)

animer(s3, sequence)

# Regroupees sous UN nom stable : un futur passage de ce script les retrouve et les
# reconstruit proprement, au lieu de les empiler par-dessus (cf. etape 3 ci-dessus).
panneau = s3.shapes.add_group_shape(toutes_les_plaques + [p for _, p, _ in groupes_compteur])
panneau.name = "PanneauChiffresCles"

# ── 5. Harmonisation 504 000 -> 606 000 sur la diapo "Entreprise" (clients) ─────────────
s_entreprise = S[3]
for sh in s_entreprise.shapes:
    if sh.has_text_frame and "504 000" in sh.text_frame.text:
        texte(sh, sh.text_frame.text.replace("504 000", "606 000"))
        print("harmonise sur la diapo Entreprise :", sh.name)

prs.save(FICHIER)
print(f"diapo 3 corrigee -> {FICHIER}")
