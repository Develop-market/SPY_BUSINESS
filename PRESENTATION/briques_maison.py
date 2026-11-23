# -*- coding: utf-8 -*-
"""
briques_maison.py — les 4 diapos trop specifiques pour un template generique
=============================================================================
Sommaire, evolution du RAG, socle commun (2 modes), deux architectures comparees :
aucune diapo des templates Canva n'a la bonne structure (comparaison precise, etapes
numerotees). Construites avec les briques socle.py, au format NATUREL de socle.py
(13.333x7.5in) -- elles seront importees a l'echelle x1.5 dans le document final
(20x11.25in, celui de tous les templates Canva retenus -- meme ratio 16:9, donc une
simple mise a l'echelle suffit, pas de recalcul de mise en page).

Sortie : maison.pptx (4 diapos, dans CET ordre : Sommaire, RAG, Socle, Architectures)
"""
import os
import sys

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from socle import (ARDOISE, BLANC, BLEU, CREME, GRIS, GRIS_CLAIR, H, L, MONO, NOIR, OR,
                   ROUGE, ROUGE_CLAIR, ROUGE_FONCE, TEXTE, TITRE, VERT, animer, carte,
                   cercle_chiffre, chiffre, degrade, etape, image, ligne, para, pied, puce,
                   rect, riche, transition, zone)
from pptx.util import Emu

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maison.pptx")
# Organigramme repris tel quel du memoire (assets/organigramme.png) : deja valide par la
# direction (voir 04_partie1.tex, commentaire au-dessus de la figure 1) -- on ne le
# redessine pas, un ecart avec l'original introduirait une inexactitude.
ORGANIGRAMME = r"C:\Users\ALPHEE COLOMBE\Desktop\MEMOIRE_LATEX\assets\organigramme.png"
# Illustration de banque fournie le 2026-09-15 pour cette diapo precisement (pas la garde).
BANQUE = r"C:\Users\ALPHEE COLOMBE\Desktop\PPTX\image\sgci.png"
prs = Presentation()
prs.slide_width, prs.slide_height = L, H
VIDE = prs.slide_layouts[6]


def page():
    return prs.slides.add_slide(VIDE)


# ══════════════════════════════════════════════════════════════════════════════════════
#  1 — SOMMAIRE
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
rect(s, 0, 0, L, H, BLANC)
_, tf = zone(s, Inches(0.95), Inches(0.55), Inches(6.0), Inches(1.1))
para(tf, "PLAN", taille=44, gras=True, couleur=NOIR, police=TITRE, premier=True)
ligne(s, Inches(0.95), Inches(1.50), Inches(2.05), Inches(1.50), ROUGE, 4.0)

PLAN = [("L'entreprise et la Direction de l'Innovation", "3"),
        ("Contexte, RAG et problematique", "4 – 6"),
        ("La solution proposee", "7"),
        ("Implementation : donnees, base, socle", "8 – 10"),
        ("Les deux architectures comparees", "11 – 13"),
        ("Projection et demonstration", "14 – 15")]
barres = []
for i, (t, p) in enumerate(PLAN):
    y = Inches(1.92 + i * 0.80)
    b = rect(s, Inches(1.55), y, Inches(10.3), Inches(0.60), GRIS_CLAIR)
    rect(s, Inches(9.55), y, Inches(2.30), Inches(0.60), ROUGE)
    n = rect(s, Inches(0.95), y, Inches(0.60), Inches(0.60), NOIR)
    tfn = n.text_frame
    tfn.margin_left = tfn.margin_right = 0
    tfn.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tfn, str(i + 1), taille=17, gras=True, couleur=BLANC, align=PP_ALIGN.CENTER,
         premier=True)
    _, z = zone(s, Inches(1.85), y + Inches(0.13), Inches(7.4), Inches(0.4))
    para(z, t, taille=14.5, gras=True, couleur=NOIR, police=TITRE, premier=True)
    _, z2 = zone(s, Inches(9.75), y + Inches(0.15), Inches(1.9), Inches(0.4),
                 align=PP_ALIGN.RIGHT)
    para(z2, p, taille=12, gras=True, couleur=BLANC, align=PP_ALIGN.RIGHT, premier=True)
    barres.append(b)
    barres.append(n)
transition(s, "push", 700, dir="u")
animer(s, [(barres, "bandeau", 110, 380)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  2 — L'ENTREPRISE, EN DEUX VUES SUR LA MEME DIAPO
#  Demande du 2026-09-15 : "slide 3/4 doit etre sur une seule slide", avec un bouton qui
#  fait passer d'une vue a l'autre au clic, comme une bascule d'ecran plutot qu'un
#  empilement. Vue 1 (chiffres SGCI, par defaut) SORT quand Vue 2 (Direction de
#  l'Innovation) ENTRE, au meme clic -- cf. le nouveau parametre `sens` de animer().
#  Chiffres verifies : PNB/RN/rang, 04_partie1.tex l.33-37. Texte Direction de
#  l'Innovation, organigramme reel : meme fichier, section "La Direction de l'Innovation".
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
rect(s, 0, 0, L, H, BLANC)

# ---- VUE 1 : L'ENTREPRISE, EN CHIFFRES (visible par defaut) ---------------------------
v1_titre, tf = zone(s, Inches(0.95), Inches(0.50), Inches(11.4), Inches(0.85))
riche(tf, [("L'ENTREPRISE  ", False, GRIS), ("SGCI", True, ROUGE)], taille=13, premier=True,
      espacement=1.5)
para(tf, "Filiale ivoirienne du groupe Societe Generale, presente depuis plus de 50 ans.",
     taille=13, couleur=NOIR, avant=6)

CHIFFRES = [("276,0", "PNB 2025 (Mds FCFA)"), ("101,4", "Resultat net (Mds FCFA)"),
            ("1er", "Rang du marche (PNB)"), ("20 %", "Part de marche")]
v1_cercles = [v1_titre]
for i, (val, lib) in enumerate(CHIFFRES):
    cx = Inches(1.75 + i * 1.78)
    cercle, etiquette = cercle_chiffre(s, cx, Inches(2.95), Inches(1.48), val, lib,
                                        couleur=ROUGE if i < 2 else ROUGE_FONCE,
                                        taille_valeur=24)
    v1_cercles += [cercle, etiquette]

v1_stats, tf = zone(s, Inches(0.95), Inches(4.55), Inches(7.55), Inches(0.75))
para(tf, "89 agences sur le territoire ivoirien  ·  plus de 1 306 collaborateurs, dont "
         "56 % de femmes  ·  environ 504 000 clients accompagnes.", taille=12.5,
         couleur=GRIS, interligne=1.35, premier=True)

v1_photo, v1_cadre = image(s, BANQUE, Inches(8.95), Inches(0.85), w=Inches(3.40),
                            h=Inches(3.40), bord=True)
v1_bouton = rect(s, Inches(8.95), Inches(4.45), Inches(3.40), Inches(0.62), ROUGE)
tfb = v1_bouton.text_frame
tfb.margin_left = Inches(0.20)
tfb.vertical_anchor = MSO_ANCHOR.MIDDLE
riche(tfb, [("LA DIRECTION DE L'INNOVATION   ", True, BLANC), (">", True, BLANC)],
      taille=11.5, premier=True)

vue1 = [v1_stats, v1_photo, v1_cadre, v1_bouton] + v1_cercles

# ---- VUE 2 : LA DIRECTION DE L'INNOVATION (cachee jusqu'au clic du bouton) -------------
v2_titre, tf = zone(s, Inches(0.95), Inches(0.50), Inches(11.4), Inches(0.9))
riche(tf, [("LA DIRECTION DE ", False, GRIS), ("L'INNOVATION", True, ROUGE)], taille=13,
      premier=True, espacement=1.5)
para(tf, "Creee en 2022 pour accelerer la transformation digitale de la SGCI et developper "
         "de nouvelles approches fondees sur l'exploitation des donnees.", taille=13,
         couleur=NOIR, avant=6)

v2_c1, v2_f1 = carte(s, Inches(0.95), Inches(1.95), Inches(5.62), Inches(1.55), "Service Data",
              ["Pole Front-End (interfaces et solutions applicatives), cellule Data "
               "Science (analyse et modeles) et cellule Data Engineering (collecte et "
               "infrastructures de donnees)."],
              accent=ROUGE, taille_titre=15, taille_texte=11.5)
v2_c2, v2_f2 = carte(s, Inches(6.82), Inches(1.95), Inches(5.62), Inches(1.55),
              "Service Gouvernance Projet",
              ["Cadrage, coordination, suivi et accompagnement des differents projets "
               "portes par la direction."],
              accent=OR, taille_titre=15, taille_texte=11.5)

v2_organis, tf = zone(s, Inches(0.95), Inches(3.62), Inches(11.4), Inches(0.4))
riche(tf, [("Organisation fonctionnelle, en squads pluridisciplinaires — approche agile : ",
            False, GRIS),
           ("le present travail a ete conduit au sein de la cellule Data Science.", True,
            NOIR)], taille=12, premier=True)

haut_img = Inches(3.15)
larg_img = Inches(3.15 * 1.6895)            # ratio reel de l'image (1676x992px) preserve
x_img = Inches(0.95) + (Inches(11.4) - larg_img) / 2
v2_img, v2_cadre = image(s, ORGANIGRAMME, x_img, Inches(4.10), w=larg_img, h=haut_img,
                          bord=True)

vue2 = [v2_titre, v2_c1, v2_f1, v2_c2, v2_f2, v2_organis, v2_img, v2_cadre]

transition(s, "wipe", 650, dir="r")
animer(s, [(vue1, "fondu", 90, 400),                       # 1er clic : vue 1 apparait
           [(vue1, "fondu", 0, 400, "sortie"),              # 2e clic : vue 1 sort...
            (vue2, "balayage", 110, 450, "entree")]])       #           ...vue 2 entre


# ══════════════════════════════════════════════════════════════════════════════════════
#  3 — EVOLUTION DU RAG
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
rect(s, 0, 0, L, H, BLANC)
_, tf = zone(s, Inches(0.95), Inches(0.55), Inches(9.0), Inches(0.9))
riche(tf, [("L'EVOLUTION DU ", False, GRIS), ("RAG", True, ROUGE)], taille=13, premier=True,
      espacement=1.5)
para(tf, "Un modele de langage seul n'a aucune source : le RAG lui impose de repondre a "
         "partir de documents fournis.", taille=13.5, couleur=NOIR, avant=6)

ligne(s, Inches(0.95), Inches(2.05), Inches(12.4), Inches(2.05), GRIS_CLAIR, 2.0)
GEN = [("Naif", "2020", "Recherche puis redaction. Aucun controle : si la recherche "
        "rate, le modele redige quand meme.", GRIS),
       ("Avance", "2022", "Reformulation, reclassement. Une seule passe reste fragile.",
        BLEU),
       ("Modulaire", "2023", "Routeur a regles, chemin fixe. Reproductible, auditable.",
        ROUGE),
       ("Agentique", "2024", "Le modele choisit ses outils et boucle. Souple, mais "
        "stochastique.", OR)]
blocs = []
for i, (t, an, d, col) in enumerate(GEN):
    x = Inches(0.95 + i * 2.92)
    pt = rect(s, x + Inches(1.16), Inches(2.00), Inches(0.28), Inches(0.28), col,
              forme=MSO_SHAPE.OVAL)
    b = rect(s, x, Inches(2.42), Inches(2.65), Inches(2.85), BLANC, bord=GRIS_CLAIR)
    rect(s, x, Inches(2.42), Inches(2.65), Inches(0.05), col)
    _, z = zone(s, x + Inches(0.20), Inches(2.62), Inches(2.25), Inches(2.5))
    para(z, t, taille=15, gras=True, couleur=col, police=TITRE, premier=True)
    para(z, an, taille=10.5, gras=True, couleur=GRIS, avant=2)
    para(z, d, taille=10.5, couleur=NOIR, avant=8, interligne=1.28)
    blocs.append(b)
    blocs.append(pt)

bas = rect(s, Inches(0.95), Inches(5.55), Inches(11.40), Inches(0.85), CREME,
           bord=ROUGE, ep=1.2)
_, tf = zone(s, Inches(1.30), Inches(5.74), Inches(10.7), Inches(0.5))
riche(tf, [("Les deux dernieres generations s'opposent sur une seule question : ", False, NOIR),
           ("qui decide du chemin d'acces a l'information ?", True, ROUGE)],
      taille=13.5, premier=True)
transition(s, "push", 700, dir="l")
animer(s, [(blocs, "fondu", 150, 420), ([bas], "balayage", 0, 550)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  3 — SOCLE COMMUN ET DEUX MODES
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
rect(s, 0, 0, L, H, BLANC)
_, tf = zone(s, Inches(0.95), Inches(0.55), Inches(11.0), Inches(0.9))
riche(tf, [("LE ", False, GRIS), ("SOCLE COMMUN", True, ROUGE),
           (" ET SES DEUX MODES", False, GRIS)], taille=13, premier=True, espacement=1.5)
para(tf, "Meme base, memes outils de recuperation, meme modele redacteur : ce qui change "
         "est qui decide du chemin.", taille=13.5, couleur=NOIR, avant=6)

d1, f1c = carte(s, Inches(0.95), Inches(2.55), Inches(5.55), Inches(3.15),
           "Le tableau de bord",
           ["L'ecran consulte dit deja quelle information est attendue.",
            "Le systeme execute sans demander au modele de choisir.",
            "ecran -> traitement -> recuperation -> calcul -> restitution"],
           accent=ROUGE, taille_titre=17)
d2, f2c = carte(s, Inches(6.90), Inches(2.55), Inches(5.55), Inches(3.15),
           "L'assistant conversationnel",
           ["Une meme zone de saisie recoit une question tarifaire, financiere ou "
            "reglementaire.",
            "Le probleme n'est plus de recuperer, mais de savoir QUELLE recuperation faire.",
            "C'est la que les deux architectures s'opposent."],
           accent=OR, taille_titre=17)

bas = rect(s, Inches(0.95), Inches(6.00), Inches(11.50), Inches(0.72), NOIR)
_, tf = zone(s, Inches(1.30), Inches(6.16), Inches(10.9), Inches(0.4))
riche(tf, [("7 banques comparees  ·  3 matieres (tarifs, comptes, reglementation)  ·  "
            "5 ecrans applicatifs", True, BLANC)], taille=13, premier=True,
      align=PP_ALIGN.CENTER)
transition(s, "wipe", 650, dir="l")
animer(s, [([d1, f1c], "balayage", 0, 500), ([d2, f2c], "balayage", 0, 500),
           ([bas], "fondu", 0, 400)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  4 — LES DEUX ARCHITECTURES COMPAREES
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
rect(s, 0, 0, L, H, BLANC)
_, tf = zone(s, Inches(0.95), Inches(0.42), Inches(11.4), Inches(0.55))
riche(tf, [("LES DEUX ", False, GRIS), ("ARCHITECTURES", True, ROUGE),
           (" COMPAREES", False, GRIS)], taille=13, premier=True, espacement=1.5)

ent1 = rect(s, Inches(0.95), Inches(1.30), Inches(5.55), Inches(0.55), ROUGE)
tfe = ent1.text_frame
tfe.margin_left = Inches(0.22)
tfe.vertical_anchor = MSO_ANCHOR.MIDDLE
riche(tfe, [("A1  ", True, BLANC), ("MODULAIRE", True, BLANC)], taille=13, premier=True)
ent2 = rect(s, Inches(6.90), Inches(1.30), Inches(5.55), Inches(0.55), ARDOISE)
tfe = ent2.text_frame
tfe.margin_left = Inches(0.22)
tfe.vertical_anchor = MSO_ANCHOR.MIDDLE
riche(tfe, [("A2  ", True, BLANC), ("AGENTIQUE", True, BLANC)], taille=13, premier=True)

A1 = [("Identifier les outils", "Un routeur a regles lit la question. Ni modele, ni vecteur."),
      ("Recuperer", "Chaque outil lit directement ou cherche par similarite."),
      ("Fusionner", "Les extraits sont reunis en un seul contexte."),
      ("Rediger", "Le modele intervient une seule fois, et ne decide de rien.")]
A2 = [("Choisir un outil", "Le modele lit la question et selectionne l'outil utile."),
      ("Exploiter", "L'outil repond ; le modele analyse ce qu'il a obtenu."),
      ("Poursuivre ou s'arreter", "S'il lui en faut un autre, il recommence — 6 tours max."),
      ("Rediger", "Quand il estime en savoir assez, il redige lui-meme.")]
g1, g2 = [], []
for i, ((t1, d1_), (t2, d2_)) in enumerate(zip(A1, A2)):
    y = Inches(2.35 + i * 0.90)
    g1.append(etape(s, Inches(0.95), y, Inches(5.55), Inches(0.76), i + 1, t1, d1_,
                    accent=ROUGE))
    g2.append(etape(s, Inches(6.90), y, Inches(5.55), Inches(0.76), i + 1, t2, d2_,
                    accent=ARDOISE))

f1 = rect(s, Inches(0.95), Inches(6.15), Inches(5.55), Inches(0.50), CREME, bord=GRIS_CLAIR)
_, z = zone(s, Inches(1.15), Inches(6.24), Inches(5.2), Inches(0.35))
para(z, "1 appel au modele  ·  chemin fixe  ·  auditable", taille=11, gras=True,
     couleur=ROUGE, premier=True)
f2 = rect(s, Inches(6.90), Inches(6.15), Inches(5.55), Inches(0.50), GRIS_CLAIR,
          bord=GRIS_CLAIR)
_, z = zone(s, Inches(7.10), Inches(6.24), Inches(5.2), Inches(0.35))
para(z, "2,4 appels en moyenne  ·  chemin construit a chaque question", taille=11,
     gras=True, couleur=ARDOISE, premier=True)
transition(s, "push", 700, dir="l")
animer(s, [([ent1] + g1 + [f1], "balayage", 130, 380),
           ([ent2] + g2 + [f2], "balayage", 130, 380)])


prs.save(OUT)
print(f"maison.pptx : {len(prs.slides)} diapos -> {OUT}")
