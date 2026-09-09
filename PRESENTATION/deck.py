# -*- coding: utf-8 -*-
"""
deck.py — diaporama de soutenance SpyBusiness (15 diapositives)
================================================================
ZONGO MESSOU Alphée Colombe — Master Data Science, Big Data et IA
Stage a la Societe Generale Cote d Ivoire, Direction Innovation.

Chaque chiffre de ce diaporama vient du memoire ou d une mesure relevee sur le service.
Aucun n est arrondi « pour faire joli » : c est le principe du projet, et un jury verifie.

    python PRESENTATION/deck.py        -> PRESENTATION/soutenance_zongo.pptx
    python PRESENTATION/verifier.py    -> ouvre dans le VRAI PowerPoint et exporte les vues
"""
import os
import sys

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from socle import (ANTHRACITE, ARDOISE, BLANC, BORDEAUX, CREME, GRIS, GRIS_CLAIR, H, L,
                   NOIR, OR, ROSE, ROUGE, ROUGE_VIF, TEXTE, TITRE, VERT, animer, bandeau, carte,
                   chiffre, degrade, etape, filigrane, fond, image, ligne, para, pied,
                   puce, rect, riche, separateur, transition, zone)

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(RACINE, "DOCUMENTATION", "img")
TOTAL = 15


def img(nom):
    c = os.path.join(IMG, nom)
    return c if os.path.exists(c) else None


prs = Presentation()
prs.slide_width, prs.slide_height = L, H
VIDE = prs.slide_layouts[6]


def page():
    return prs.slides.add_slide(VIDE)


# ══════════════════════════════════════════════════════════════════════════════════════
#  1 — PAGE DE GARDE
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
degrade(s, 0, 0, L, H, "12121A", "5E0018", angle=30)
for i in range(14):
    for j in range(7):
        if (i + j) % 3:
            rect(s, Inches(0.35 + i * 0.20), Inches(0.45 + j * 0.20),
                 Inches(0.062), Inches(0.062), ROUGE, transparence=0.55)
for i in range(10):
    for j in range(6):
        if (i * j) % 4:
            rect(s, Inches(11.45 + i * 0.20), Inches(3.30 + j * 0.20),
                 Inches(0.062), Inches(0.062), BLANC, transparence=0.72)

_, tf = zone(s, Inches(1.0), Inches(0.62), Inches(11.3), Inches(0.7), align=PP_ALIGN.CENTER)
para(tf, "RÉPUBLIQUE DE CÔTE D'IVOIRE   ·   UNION – DISCIPLINE – TRAVAIL", taille=10.5,
     couleur=ROSE,
     align=PP_ALIGN.CENTER, premier=True, espacement=1.6)
para(tf, "INTERNATIONAL DATASCIENCE INSTITUTE", taille=12.5, gras=True, couleur=BLANC,
     align=PP_ALIGN.CENTER, avant=6, espacement=1.2)

_, tf = zone(s, Inches(1.0), Inches(1.62), Inches(11.3), Inches(0.5), align=PP_ALIGN.CENTER)
para(tf, "SOUTENANCE DE MÉMOIRE DE FIN D'ÉTUDES", taille=13, gras=True, couleur=BLANC,
     align=PP_ALIGN.CENTER, premier=True, espacement=1.0)
para(tf, "Master Data Science · Big Data · Intelligence Artificielle", taille=12,
     couleur=ROSE, align=PP_ALIGN.CENTER, avant=3)

barre = rect(s, Inches(1.55), Inches(2.60), Inches(1.85), Inches(1.62), GRIS_CLAIR)
tfb = barre.text_frame
tfb.margin_left = tfb.margin_right = 0
tfb.vertical_anchor = MSO_ANCHOR.MIDDLE
para(tfb, "THEME", taille=27, gras=True, couleur=NOIR, police=TITRE,
     align=PP_ALIGN.CENTER, premier=True)
theme = rect(s, Inches(3.40), Inches(2.60), Inches(8.40), Inches(1.62), ROUGE)
tft = theme.text_frame
tft.margin_left = Inches(0.42)
tft.margin_right = Inches(0.42)
tft.vertical_anchor = MSO_ANCHOR.MIDDLE
para(tft, "VEILLE STRATÉGIQUE ET AIDE À LA DÉCISION\nPAR UNE APPROCHE RAG", taille=19,
     gras=True, couleur=BLANC, police=TITRE, align=PP_ALIGN.CENTER, premier=True,
     interligne=1.22)

_, tf = zone(s, Inches(1.0), Inches(4.52), Inches(11.3), Inches(0.6), align=PP_ALIGN.CENTER)
riche(tf, [("Présenté par  ", False, ROSE),
           ("ZONGO MESSOU Alphée Colombe", True, BLANC)],
      taille=15, align=PP_ALIGN.CENTER, premier=True)
para(tf, "Direction Innovation — Société Générale Côte d'Ivoire", taille=11.5,
     couleur=ROSE, align=PP_ALIGN.CENTER, avant=4)

ligne(s, Inches(4.4), Inches(5.36), Inches(8.9), Inches(5.36), ROUGE, 1.4)

_, g = zone(s, Inches(1.15), Inches(5.60), Inches(4.9), Inches(1.1))
para(g, "ENCADREUR PÉDAGOGIQUE", taille=9.5, gras=True, couleur=ROSE, premier=True,
     espacement=1.2)
para(g, "M. MONSIA DOUGBAN", taille=13, gras=True, couleur=BLANC, avant=4)

_, d = zone(s, Inches(7.30), Inches(5.60), Inches(4.9), Inches(1.1), align=PP_ALIGN.RIGHT)
para(d, "MAÎTRE DE STAGE", taille=9.5, gras=True, couleur=ROSE, align=PP_ALIGN.RIGHT,
     premier=True, espacement=1.2)
para(d, "M. MOUAHA HANDY", taille=13, gras=True, couleur=BLANC, align=PP_ALIGN.RIGHT, avant=4)

_, tf = zone(s, Inches(1.0), Inches(6.85), Inches(11.3), Inches(0.4), align=PP_ALIGN.CENTER)
para(tf, "Année académique 2025 – 2026", taille=10.5, couleur=ROSE,
     align=PP_ALIGN.CENTER, premier=True)

transition(s, "fade", 900)
animer(s, [([barre, theme], "bandeau", 0, 700)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  2 — SOMMAIRE
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
fond(s)
filigrane(s)
_, tf = zone(s, Inches(0.95), Inches(0.70), Inches(6.0), Inches(1.2))
para(tf, "PLAN", taille=46, gras=True, couleur=NOIR, police=TITRE, premier=True)
ligne(s, Inches(0.95), Inches(1.72), Inches(2.05), Inches(1.72), ROUGE, 4.0)

PLAN = [("Présentation de l'entreprise d'accueil", "3"),
        ("Contexte et problématique", "4 – 6"),
        ("Solution proposée", "7"),
        ("Implémentation de la solution", "8 – 11"),
        ("Évaluation et architecture retenue", "12 – 14"),
        ("Démonstration et chiffres clés", "15")]
barres = []
for i, (t, p) in enumerate(PLAN):
    y = Inches(2.20 + i * 0.78)
    b = rect(s, Inches(1.55), y, Inches(10.3), Inches(0.60), GRIS_CLAIR)
    rect(s, Inches(9.55), y, Inches(2.30), Inches(0.60), ROUGE)
    n = rect(s, Inches(0.95), y, Inches(0.60), Inches(0.60), NOIR)
    tfn = n.text_frame
    tfn.margin_left = tfn.margin_right = 0
    tfn.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tfn, str(i + 1), taille=17, gras=True, couleur=BLANC, align=PP_ALIGN.CENTER,
         premier=True)
    _, z = zone(s, Inches(1.85), y + Inches(0.13), Inches(7.4), Inches(0.4))
    para(z, t, taille=15, gras=True, couleur=NOIR, police=TITRE, premier=True)
    _, z2 = zone(s, Inches(9.75), y + Inches(0.15), Inches(1.9), Inches(0.4),
                 align=PP_ALIGN.RIGHT)
    para(z2, p, taille=12.5, gras=True, couleur=BLANC, align=PP_ALIGN.RIGHT, premier=True)
    barres.append(b)
    barres.append(n)

pied(s, 2, TOTAL)
transition(s, "push", 700, dir="u")
animer(s, [(barres, "bandeau", 110, 380)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  3 — L'ENTREPRISE
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
fond(s)
filigrane(s)
bandeau(s, "1", "La Société Générale Côte d'Ivoire",
        sous_titre="Une banque de référence, une direction qui cherche à décider plus vite",
        n_page=3, total=TOTAL)

c1 = carte(s, Inches(0.95), Inches(1.45), Inches(3.75), Inches(2.35),
           "Une banque de premier rang",
           ["Filiale du groupe Société Générale, implantée en Côte d'Ivoire depuis 1962.",
            "Banque universelle : particuliers, professionnels, grandes entreprises."],
           accent=ROUGE)
c2 = carte(s, Inches(4.90), Inches(1.45), Inches(3.75), Inches(2.35),
           "La Direction Innovation",
           ["Structure d'accueil du stage.",
            "Mission : outiller les métiers pour qu'ils décident sur des faits, et non sur des impressions."],
           accent=OR)
c3 = carte(s, Inches(8.85), Inches(1.45), Inches(3.50), Inches(2.35),
           "Un marché disputé",
           ["Sept banques se partagent le marché ivoirien.",
            "Chacune publie ses tarifs et ses comptes : l'information est là, publique."],
           accent=ARDOISE)

fil = rect(s, Inches(0.95), Inches(4.15), Inches(11.40), Inches(2.05), CREME,
           bord=GRIS_CLAIR)
rect(s, Inches(0.95), Inches(4.15), Inches(0.075), Inches(2.05), ROUGE)
_, tf = zone(s, Inches(1.35), Inches(4.42), Inches(10.6), Inches(1.6))
para(tf, "LE FIL CONDUCTEUR", taille=10.5, gras=True, couleur=ROUGE, premier=True,
     espacement=1.5)
riche(tf, [("La SGCI veut savoir ", False, NOIR),
           ("où elle se situe face à ses six concurrents", True, NOIR),
           (" — sur les tarifs, sur les comptes, sur la conformité. Les documents existent, "
            "ils sont publics, et personne ne peut les lire assez vite pour en tirer une "
            "decision. ", False, NOIR),
           ("C'est ce constat qui ouvre le sujet.", True, ROUGE)],
      taille=14, avant=8, interligne=1.35)

transition(s, "wipe", 650, dir="l")
animer(s, [([c1, c2, c3], "balayage", 160, 460), ([fil], "fondu", 0, 550)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  4 — CONTEXTE
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
fond(s)
filigrane(s)
bandeau(s, "2", "La donnée existe. Elle est inexploitable.",
        sous_titre="Trois matières publiques, trois obstacles différents",
        n_page=4, total=TOTAL)

blocs = []
DATA = [("Grilles tarifaires", "semestrielles",
         "Des PDF de dizaines de pages, souvent scannés, où un même service change de nom "
         "d'une banque a l'autre.", ROUGE),
        ("États financiers", "annuels",
         "Des tableaux sur deux colonnes, exercice N et N−1, que rien ne distingue "
         "visuellement.", OR),
        ("Textes réglementaires", "BCEAO / UEMOA",
         "Une prose juridique dense, où le mot exact fait le sens : usure, gratuité, "
         "agrement.", ARDOISE)]
for i, (t, st, d, col) in enumerate(DATA):
    x = Inches(0.95 + i * 3.90)
    b = rect(s, x, Inches(1.50), Inches(3.60), Inches(2.55), BLANC, bord=GRIS_CLAIR)
    rect(s, x, Inches(1.50), Inches(3.60), Inches(0.055), col)
    p = rect(s, x + Inches(0.28), Inches(1.78), Inches(0.62), Inches(0.62), col,
             forme=MSO_SHAPE.OVAL)
    tfp = p.text_frame
    tfp.margin_left = tfp.margin_right = tfp.margin_top = tfp.margin_bottom = 0
    tfp.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tfp, "PDF", taille=11, gras=True, couleur=BLANC, align=PP_ALIGN.CENTER, premier=True)
    _, z = zone(s, x + Inches(0.28), Inches(2.58), Inches(3.05), Inches(1.4))
    para(z, t, taille=15.5, gras=True, couleur=NOIR, police=TITRE, premier=True)
    para(z, st, taille=11, couleur=col, gras=True, avant=1)
    para(z, d, taille=11.5, couleur=GRIS, avant=7, interligne=1.26)
    blocs.append(b)

mur = rect(s, Inches(0.95), Inches(4.42), Inches(11.40), Inches(1.80), NOIR)
_, tf = zone(s, Inches(1.45), Inches(4.72), Inches(6.6), Inches(1.3))
para(tf, "CE QUE COÛTE CETTE SITUATION", taille=10.5, gras=True, couleur=ROUGE_VIF,
     premier=True, espacement=1.5)
para(tf, "Comparer sept banques sur une seule question demandait de rouvrir chaque\n"
         "document, à la main. Une analyse externe était facturée environ\n"
         "dix millions de FCFA.", taille=13.5, couleur=BLANC, avant=8, interligne=1.35)
chiffre(s, Inches(8.55), Inches(4.72), Inches(1.8), "93", "documents\na traiter", taille=40,
        couleur=BLANC)
chiffre(s, Inches(10.35), Inches(4.72), Inches(1.9), "7", "banques\na comparer", taille=40,
        couleur=ROUGE_VIF)

transition(s, "push", 700, dir="l")
animer(s, [(blocs, "balayage", 170, 480), ([mur], "fondu", 0, 600)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  5 — LE RAG ET SON EVOLUTION
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
fond(s)
filigrane(s)
bandeau(s, "3", "En parallèle : la génération augmentée par récupération",
        sous_titre="Une technologie qui a mis quatre générations à devenir gouvernable",
        n_page=5, total=TOTAL)

_, tf = zone(s, Inches(0.95), Inches(1.42), Inches(11.4), Inches(0.5))
riche(tf, [("Un modèle de langage seul ", False, NOIR),
           ("n'a aucune source", True, ROUGE),
           (" : il produit la suite de mots la plus plausible. Le RAG lui impose de "
            "répondre à partir de documents qu'on lui fournit.", False, NOIR)],
      taille=13.5, premier=True)

ligne(s, Inches(1.35), Inches(3.05), Inches(12.0), Inches(3.05), GRIS_CLAIR, 2.0)
GEN = [("Naive RAG", "On cherche, on donne, on rédige.",
        "Aucun contrôle : si la recherche rate, le modèle rédige quand même.", GRIS),
       ("Advanced RAG", "On soigne la recherche.",
        "Reformulation, reclassement. La qualité dépend encore d'une seule passe.", ARDOISE),
       ("Modular RAG", "Des outils spécialisés, un routeur.",
        "Le chemin est écrit à l'avance. Reproductible et auditable.", ROUGE),
       ("Agentic RAG", "Le modèle choisit lui-même ses outils.",
        "Souple, mais le chemin change d'une exécution à l'autre.", OR)]
etapes = []
for i, (t, st, d, col) in enumerate(GEN):
    x = Inches(0.95 + i * 2.95)
    pt = rect(s, x + Inches(1.20), Inches(2.90), Inches(0.30), Inches(0.30), col,
              forme=MSO_SHAPE.OVAL)
    b = rect(s, x, Inches(3.42), Inches(2.65), Inches(1.95), BLANC, bord=GRIS_CLAIR)
    rect(s, x, Inches(3.42), Inches(2.65), Inches(0.05), col)
    _, z = zone(s, x + Inches(0.22), Inches(3.62), Inches(2.2), Inches(2.0))
    para(z, t, taille=14.5, gras=True, couleur=col, police=TITRE, premier=True)
    para(z, st, taille=11.5, gras=True, couleur=NOIR, avant=5, interligne=1.2)
    para(z, d, taille=10.5, couleur=GRIS, avant=5, interligne=1.24)
    _, y = zone(s, x, Inches(2.42), Inches(2.65), Inches(0.4), align=PP_ALIGN.CENTER)
    para(y, ["2020", "2022", "2023", "2024"][i], taille=12, gras=True, couleur=col,
         align=PP_ALIGN.CENTER, premier=True)
    etapes.append(b)
    etapes.append(pt)

cadre = rect(s, Inches(0.95), Inches(6.02), Inches(11.40), Inches(0.72), CREME,
             bord=ROUGE, ep=1.2)
_, tf = zone(s, Inches(1.30), Inches(6.18), Inches(10.7), Inches(0.5))
riche(tf, [("Les deux dernières générations s'opposent sur une seule question : ", False, NOIR),
           ("qui décide du chemin d'accès à l'information ?", True, ROUGE)],
      taille=13.5, premier=True)

transition(s, "push", 700, dir="l")
animer(s, [(etapes, "fondu", 150, 420), ([cadre], "balayage", 0, 550)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  6 — PROBLÉMATIQUE
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
degrade(s, 0, 0, L, H, "12121A", "5E0018", angle=30)
for i in range(12):
    for j in range(4):
        if (i + j) % 3:
            rect(s, Inches(10.6 + i * 0.20), Inches(0.40 + j * 0.20),
                 Inches(0.06), Inches(0.06), BLANC, transparence=0.78)

_, tf = zone(s, Inches(1.30), Inches(0.85), Inches(10.7), Inches(0.6))
para(tf, "PROBLÉMATIQUE", taille=11, gras=True, couleur=ROUGE_VIF, premier=True,
     espacement=2.0)

q = rect(s, Inches(1.30), Inches(1.60), Inches(10.7), Inches(1.95), None)
tfq = q.text_frame
tfq.margin_left = tfq.margin_right = tfq.margin_top = 0
riche(tfq, [("Comment exploiter des documents publics, hétérogènes et non structurés "
             "pour produire une veille concurrentielle ", False, BLANC),
            ("dont chaque chiffre soit exact, reproductible et vérifiable", True, ROUGE_VIF),
            (" ?", False, BLANC)],
      taille=25, police=TITRE, interligne=1.28, premier=True)

ligne(s, Inches(1.30), Inches(3.78), Inches(4.10), Inches(3.78), ROUGE, 3.5)

sous = []
SOUS = [("La donnée", "Comment transformer 93 documents hétérogènes en une base interrogeable ?"),
        ("L'architecture", "Quelle orchestration garantit qu'un chiffre affiché est un chiffre lu ?"),
        ("La preuve", "Comment démontrer, et non affirmer, que la solution est fiable ?")]
for i, (t, d) in enumerate(SOUS):
    x = Inches(1.20 + i * 3.72)
    b = rect(s, x, Inches(4.20), Inches(3.50), Inches(1.85), BLANC, transparence=0.92,
             bord=None)
    rect(s, x, Inches(4.20), Inches(0.055), Inches(1.85), ROUGE_VIF)
    _, z = zone(s, x + Inches(0.30), Inches(4.44), Inches(3.00), Inches(1.5))
    para(z, t.upper(), taille=11, gras=True, couleur=ROUGE_VIF, premier=True, espacement=1.4)
    para(z, d, taille=12.5, couleur=BLANC, avant=7, interligne=1.30)
    sous.append(b)

pied(s, 6, TOTAL, sombre=True)
transition(s, "fade", 900)
animer(s, [([q], "fondu", 0, 800), (sous, "balayage", 200, 500)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  7 — SOLUTION PROPOSEE
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
fond(s)
filigrane(s)
bandeau(s, "4", "La solution proposée : SpyBusiness",
        sous_titre="Un principe unique, appliqué sans exception à tout le système",
        n_page=7, total=TOTAL)

principe = rect(s, Inches(0.95), Inches(1.45), Inches(11.40), Inches(1.25), NOIR)
rect(s, Inches(0.95), Inches(1.45), Inches(0.09), Inches(1.25), ROUGE)
_, tf = zone(s, Inches(1.45), Inches(1.62), Inches(10.6), Inches(1.0),
             ancre=MSO_ANCHOR.MIDDLE)
para(tf, "LE PRINCIPE DIRECTEUR", taille=10, gras=True, couleur=ROUGE_VIF, premier=True,
     espacement=1.6)
riche(tf, [("Le déterminisme établit, ", True, BLANC),
           ("le modèle de langage formule.", True, ROUGE_VIF)],
      taille=24, avant=4)

_, tf = zone(s, Inches(0.95), Inches(2.88), Inches(11.4), Inches(0.45))
para(tf, "Aucun chiffre affiché ne vient d'un modèle. Montants, rangs, écarts et médianes "
         "sont calculés en SQL ; le modèle rédige autour de faits qu'on lui impose.",
     taille=13, couleur=GRIS, premier=True)

cartes = []
SOL = [("Une base unique", "Grilles tarifaires, états financiers et textes réglementaires "
        "réunis dans une seule base PostgreSQL.", ROUGE),
       ("Deux modes d'accès", "Un tableau de bord pour la consultation guidée, un assistant "
        "pour la question libre.", OR),
       ("Une vérification finale", "Chaque chiffre et chaque article cité est recherché dans "
        "les extraits avant affichage.", ARDOISE),
       ("Une évaluation chiffrée", "Deux architectures construites, puis départagées sur "
        "169 questions de référence.", VERT)]
for i, (t, d, col) in enumerate(SOL):
    x = Inches(0.95 + i * 2.92)
    c = carte(s, x, Inches(3.48), Inches(2.62), Inches(2.05), t, [d], accent=col,
              taille_titre=14, taille_texte=11.5)
    cartes.append(c)

bas = rect(s, Inches(0.95), Inches(5.82), Inches(11.40), Inches(0.92), CREME, bord=GRIS_CLAIR)
_, tf = zone(s, Inches(1.35), Inches(6.02), Inches(10.6), Inches(0.6))
riche(tf, [("Livré et déployé : ", False, GRIS),
           ("spybusiness.onrender.com", True, ROUGE),
           ("   —   cinq écrans, sept banques, trois matières, un assistant.", False, GRIS)],
      taille=13, premier=True)

transition(s, "wipe", 650, dir="l")
animer(s, [([principe], "bandeau", 0, 650), (cartes, "balayage", 150, 450),
           ([bas], "fondu", 0, 450)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  8 — IMPLEMENTATION 1 : SOURCES ET EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
fond(s)
filigrane(s)
bandeau(s, "5.1", "Des documents aux données : le choix d'extraction",
        sous_titre="Trois méthodes comparées sur le corpus réel, une retenue par type de document",
        n_page=8, total=TOTAL)

_, tf = zone(s, Inches(0.95), Inches(1.38), Inches(11.4), Inches(0.4))
para(tf, "Aucune méthode ne gagne partout : le choix dépend de la nature du fichier.",
     taille=12.5, couleur=GRIS, italique=True, premier=True)

entetes = ["Méthode", "Ce qu'elle fait bien", "Où elle échoue", "Retenue pour"]
larg = [Inches(2.35), Inches(3.55), Inches(3.20), Inches(2.30)]
x = Inches(0.95)
for e, w in zip(entetes, larg):
    h_ = rect(s, x, Inches(1.86), w, Inches(0.46), NOIR)
    tfh = h_.text_frame
    tfh.margin_left = Inches(0.16)
    tfh.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tfh, e.upper(), taille=10, gras=True, couleur=BLANC, premier=True, espacement=1.2)
    x += w

LIGNES = [("pdfplumber", "Lit directement les tableaux d'un PDF natif, sans perte.",
           "Rend une page blanche sur un document scanné.", "Grilles natives", ARDOISE),
          ("Docling + EasyOCR", "Restitue texte et tableaux dans un même passage, lignes "
           "et colonnes conservées.", "Peine sur un scan très sombre.",
           "États financiers", ROUGE),
          ("Tesseract", "Relit caractère par caractère une page reconvertie en image "
           "agrandie.", "Ignore la structure du tableau.", "Relais de secours", OR)]
rangs = []
for i, (m, bien, mal, ret, col) in enumerate(LIGNES):
    y = Inches(2.32 + i * 0.86)
    r = rect(s, Inches(0.95), y, Inches(11.40), Inches(0.86),
             BLANC if i % 2 == 0 else CREME, bord=GRIS_CLAIR, ep=0.75)
    rect(s, Inches(0.95), y, Inches(0.055), Inches(0.86), col)
    x = Inches(0.95)
    for j, (txt, w) in enumerate(zip([m, bien, mal, ret], larg)):
        _, z = zone(s, x + Inches(0.18), y + Inches(0.13), w - Inches(0.30), Inches(0.62),
                    ancre=MSO_ANCHOR.MIDDLE)
        para(z, txt, taille=11.5 if j else 13,
             gras=(j == 0 or j == 3), couleur=col if j == 0 else (NOIR if j == 3 else GRIS),
             police=TITRE if j == 0 else TEXTE, premier=True, interligne=1.20)
        x += w
    rangs.append(r)

_, tf = zone(s, Inches(0.95), Inches(5.06), Inches(5.6), Inches(0.4))
para(tf, "LE PROCESSUS RETENU", taille=10.5, gras=True, couleur=ROUGE, premier=True,
     espacement=1.5)

FLUX = [("PDF source", GRIS), ("Natif ou scanné ?", ANTHRACITE), ("Extraction", ROUGE),
        ("Contrôle de taille", OR), ("Base PostgreSQL", VERT)]
flux = []
x = Inches(0.95)
for i, (t, col) in enumerate(FLUX):
    b = rect(s, x, Inches(5.50), Inches(2.00), Inches(0.74), col)
    tfb = b.text_frame
    tfb.margin_left = tfb.margin_right = Inches(0.08)
    tfb.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tfb, t, taille=11.5, gras=True, couleur=BLANC, align=PP_ALIGN.CENTER, premier=True,
         interligne=1.1)
    flux.append(b)
    x += Inches(2.00)
    if i < len(FLUX) - 1:
        a = rect(s, x + Inches(0.06), Inches(5.72), Inches(0.30), Inches(0.30), GRIS,
                 forme=MSO_SHAPE.RIGHT_ARROW)
        flux.append(a)
        x += Inches(0.42)

_, tf = zone(s, Inches(0.95), Inches(6.42), Inches(11.4), Inches(0.5))
riche(tf, [("Deux seuils, relevés sur le corpus : ", False, GRIS),
           ("4 feuilles et 200 cellules", True, NOIR),
           (" valident une grille tarifaire, ", False, GRIS),
           ("2 Ko", True, NOIR),
           (" un état financier. Sous ces seuils, l'extraction est refaite autrement.",
            False, GRIS)],
      taille=12, premier=True)

transition(s, "push", 700, dir="l")
animer(s, [(rangs, "bandeau", 170, 420), (flux, "fondu", 90, 300)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  9 — IMPLEMENTATION 2 : LA BASE
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
fond(s)
filigrane(s)
bandeau(s, "5.2", "Le modèle de données",
        sous_titre="PostgreSQL, étendu par pgvector pour la recherche par le sens",
        n_page=9, total=TOTAL)

ref = rect(s, Inches(0.95), Inches(1.62), Inches(2.85), Inches(1.55), NOIR)
rect(s, Inches(0.95), Inches(1.62), Inches(2.85), Inches(0.055), OR)
_, z = zone(s, Inches(1.20), Inches(1.86), Inches(2.4), Inches(1.2))
para(z, "banques", taille=16, gras=True, couleur=BLANC, police=TITRE, premier=True)
para(z, "Le référentiel. Toute nouvelle banque commence ici : les autres tables y font "
        "clé étrangère.", taille=10.5, couleur=GRIS_CLAIR, avant=6, interligne=1.24)

TABLES = [("cb_tarifs", "Grilles tarifaires", "banque · période · segment\nsection · sous-section", ROUGE),
          ("ef_indicateurs", "États financiers", "banque · exercice\nindicateur · montant", OR),
          ("regl_documents", "Textes réglementaires", "article · contenu\n+ vecteur 768 dimensions", ARDOISE)]
tables = []
for i, (n, t, ch, col) in enumerate(TABLES):
    x = Inches(4.45 + i * 2.72)
    b = rect(s, x, Inches(1.62), Inches(2.50), Inches(2.28), BLANC, bord=GRIS_CLAIR)
    rect(s, x, Inches(1.62), Inches(2.50), Inches(0.055), col)
    _, z = zone(s, x + Inches(0.22), Inches(1.86), Inches(2.06), Inches(2.0))
    para(z, n, taille=13.5, gras=True, couleur=col, police=TITRE, premier=True)
    para(z, t, taille=11, couleur=NOIR, gras=True, avant=3)
    para(z, ch, taille=10, couleur=GRIS, avant=6, interligne=1.30)
    ligne(s, Inches(3.80), Inches(2.40), x, Inches(2.40), GRIS_CLAIR, 1.2, pointille=True)
    tables.append(b)

cache = rect(s, Inches(0.95), Inches(3.34), Inches(2.85), Inches(0.56), CREME,
             bord=GRIS_CLAIR)
_, z = zone(s, Inches(1.20), Inches(3.46), Inches(2.4), Inches(0.4))
riche(z, [("cache_app", True, ROUGE), ("  résultats coûteux", False, GRIS)], taille=11.5,
      premier=True)

ext = []
EXT = [("pgvector", "Recherche par similarité cosinus. Chaque fragment porte son vecteur.",
        ROUGE),
       ("pg_trgm", "Rapprochement de libellés : un même service ne s'écrit pas pareil d'une "
        "banque a l'autre.", ARDOISE)]
for i, (n, d, col) in enumerate(EXT):
    x = Inches(0.95 + i * 5.85)
    b = rect(s, x, Inches(4.22), Inches(5.55), Inches(1.00), BLANC, bord=col, ep=1.2)
    _, z = zone(s, x + Inches(0.28), Inches(4.40), Inches(5.0), Inches(0.8))
    riche(z, [("EXTENSION  ", False, GRIS), (n, True, col)], taille=11, premier=True)
    para(z, d, taille=11.5, couleur=NOIR, avant=4, interligne=1.24)
    ext.append(b)

garde = rect(s, Inches(0.95), Inches(5.50), Inches(11.40), Inches(1.20), NOIR)
rect(s, Inches(0.95), Inches(5.50), Inches(0.075), Inches(1.20), ROUGE_VIF)
_, tf = zone(s, Inches(1.35), Inches(5.70), Inches(10.6), Inches(0.9))
para(tf, "UN PIÈGE QUI A COÛTÉ DES SEMAINES", taille=10, gras=True, couleur=ROUGE_VIF,
     premier=True, espacement=1.5)
para(tf, "La fonction de lecture interceptait les erreurs SQL et rendait une liste vide : "
         "un écran restait blanc sans le moindre message. Cinq chemins morts ont ainsi\n"
         "ignoré 1 240 validations sourcées. Depuis, devant un écran vide, on vérifie "
         "d'abord que la requête passe.", taille=12, couleur=BLANC, avant=6, interligne=1.30)

transition(s, "push", 700, dir="l")
animer(s, [([ref], "fondu", 0, 450), (tables, "balayage", 150, 420),
           (ext + [cache], "fondu", 120, 380), ([garde], "bandeau", 0, 550)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  10 — LE SOCLE COMMUN ET SES DEUX MODES
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
fond(s)
filigrane(s)
bandeau(s, "5.3", "Un socle commun, deux modes d'utilisation",
        sous_titre="Mêmes données, mêmes outils : ce qui change est qui décide du chemin",
        n_page=10, total=TOTAL)

sc = img("archi_globale.jpg")
if sc:
    image(s, sc, Inches(0.95), Inches(1.45), w=Inches(6.30))

d1 = carte(s, Inches(7.55), Inches(1.45), Inches(4.80), Inches(2.20),
           "Le tableau de bord",
           ["L'écran consulté dit déjà quelle information est attendue.",
            "Le système sait quoi exécuter sans demander au modèle de choisir.",
            "écran → traitement → récupération → calcul → restitution"],
           accent=ROUGE, taille_titre=16)
d2 = carte(s, Inches(7.55), Inches(3.80), Inches(4.80), Inches(2.35),
           "L'assistant conversationnel",
           ["Une même zone de saisie reçoit une question tarifaire, financière ou "
            "réglementaire.",
            "Le problème n'est plus de récupérer, mais de savoir QUELLE récupération faire.",
            "C'est là que les deux architectures s'opposent."],
           accent=OR, taille_titre=16)

bas = rect(s, Inches(0.95), Inches(6.28), Inches(11.40), Inches(0.62), CREME,
           bord=GRIS_CLAIR)
_, tf = zone(s, Inches(1.30), Inches(6.40), Inches(10.7), Inches(0.4))
riche(tf, [("Même base, mêmes outils de récupération, même modèle rédacteur. ", False, GRIS),
           ("Une seule variable change : l'orchestration.", True, ROUGE)],
      taille=12.5, premier=True)

transition(s, "wipe", 650, dir="l")
animer(s, [([d1], "balayage", 0, 500), ([d2], "balayage", 0, 500), ([bas], "fondu", 0, 400)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  11 — LES DEUX ARCHITECTURES
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
fond(s)
filigrane(s)
bandeau(s, "5.4", "Les deux architectures comparées",
        sous_titre="Même socle, même modèle rédacteur, même vérification finale",
        n_page=11, total=TOTAL)

ent1 = rect(s, Inches(0.95), Inches(1.42), Inches(5.55), Inches(0.62), ROUGE)
tfe = ent1.text_frame
tfe.margin_left = Inches(0.25)
tfe.vertical_anchor = MSO_ANCHOR.MIDDLE
riche(tfe, [("A1  ", True, BLANC), ("ARCHITECTURE MODULAIRE", True, BLANC)], taille=14,
      premier=True)
ent2 = rect(s, Inches(6.80), Inches(1.42), Inches(5.55), Inches(0.62), ARDOISE)
tfe = ent2.text_frame
tfe.margin_left = Inches(0.25)
tfe.vertical_anchor = MSO_ANCHOR.MIDDLE
riche(tfe, [("A2  ", True, BLANC), ("ARCHITECTURE AGENTIQUE", True, BLANC)], taille=14,
      premier=True)

A1 = [("Identifier les outils", "Un routeur à règles lit la question. Ni modèle, ni vecteur."),
      ("Récupérer", "Chaque outil lit directement ou cherche par similarité."),
      ("Fusionner", "Les extraits sont réunis en un seul contexte."),
      ("Rédiger", "Le modèle intervient une seule fois, et ne décide de rien.")]
A2 = [("Choisir un outil", "Le modèle lit la question et sélectionne l'outil qu'il juge utile."),
      ("Exploiter", "L'outil répond ; le modèle analyse ce qu'il a obtenu."),
      ("Poursuivre ou s'arrêter", "S'il lui en faut un autre, il recommence — jusqu'à six tours."),
      ("Rédiger", "Quand il estime en savoir assez, il rédige lui-même.")]
g1, g2 = [], []
for i, ((t1, d1_), (t2, d2_)) in enumerate(zip(A1, A2)):
    y = Inches(2.28 + i * 1.05)
    g1.append(etape(s, Inches(0.95), y, Inches(5.55), Inches(0.92), i + 1, t1, d1_,
                    accent=ROUGE))
    g2.append(etape(s, Inches(6.80), y, Inches(5.55), Inches(0.92), i + 1, t2, d2_,
                    accent=ARDOISE))

f1 = rect(s, Inches(0.95), Inches(6.55), Inches(5.55), Inches(0.52), CREME, bord=GRIS_CLAIR)
_, z = zone(s, Inches(1.20), Inches(6.65), Inches(5.1), Inches(0.35))
para(z, "1 appel au modèle  ·  chemin fixe  ·  auditable", taille=11.5, gras=True,
     couleur=ROUGE, premier=True)
f2 = rect(s, Inches(6.80), Inches(6.55), Inches(5.55), Inches(0.52), GRIS_CLAIR,
          bord=GRIS_CLAIR)
_, z = zone(s, Inches(7.05), Inches(6.65), Inches(5.1), Inches(0.35))
para(z, "2,36 appels en moyenne  ·  chemin construit à chaque question", taille=11.5,
     gras=True, couleur=ARDOISE, premier=True)

transition(s, "push", 700, dir="l")
animer(s, [([ent1] + g1 + [f1], "balayage", 130, 380),
           ([ent2] + g2 + [f2], "balayage", 130, 380)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  12 — L'EVALUATION
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
fond(s)
filigrane(s)
bandeau(s, "6", "L'évaluation comparative",
        sous_titre="169 questions de référence, mêmes questions pour les deux architectures",
        n_page=12, total=TOTAL)

jeu = []
JEU = [("109", "questions à réponse unique", "vérité tirée de la base par requête SQL", ROUGE),
       ("30", "questions réglementaires", "jugées sur leur fidélité aux textes", ARDOISE),
       ("30", "synthèses", "jugées sur fidélité, pertinence et couverture", OR)]
for i, (n, t, d, col) in enumerate(JEU):
    x = Inches(0.95 + i * 3.90)
    b = rect(s, x, Inches(1.45), Inches(3.60), Inches(1.28), BLANC, bord=GRIS_CLAIR)
    rect(s, x, Inches(1.45), Inches(0.06), Inches(1.28), col)
    _, z = zone(s, x + Inches(0.30), Inches(1.60), Inches(3.1), Inches(1.0))
    riche(z, [(n + "  ", True, col), (t, True, NOIR)], taille=17, premier=True)
    para(z, d, taille=11, couleur=GRIS, avant=4, interligne=1.22)
    jeu.append(b)

MES = [("Exactitude", "100,0 %", "99,1 %", True),
       ("Appels au modèle par question", "1", "2,36", True),
       ("Latence médiane", "2,05 s", "4,42 s", True),
       ("Stabilité des montants cités", "100 %", "90 %", True),
       ("Fidélité jugée", "0,68", "0,67", None),
       ("Couverture des synthèses", "0,74", "0,84", False)]
x0, w0, w1 = Inches(0.95), Inches(6.30), Inches(2.55)
h_ = rect(s, x0, Inches(2.98), Inches(11.40), Inches(0.48), NOIR)
for lbl, x, w in [("MESURE", x0 + Inches(0.22), w0),
                  ("MODULAIRE", x0 + w0, w1), ("AGENTIQUE", x0 + w0 + w1, w1)]:
    _, z = zone(s, x, Inches(3.08), w, Inches(0.32),
                align=PP_ALIGN.LEFT if lbl == "MESURE" else PP_ALIGN.CENTER)
    para(z, lbl, taille=10, gras=True, couleur=BLANC, premier=True, espacement=1.3,
         align=PP_ALIGN.LEFT if lbl == "MESURE" else PP_ALIGN.CENTER)

rangs = []
for i, (m, a, b, gagne_a) in enumerate(MES):
    y = Inches(3.46 + i * 0.44)
    r = rect(s, x0, y, Inches(11.40), Inches(0.44), BLANC if i % 2 == 0 else CREME,
             bord=GRIS_CLAIR, ep=0.6)
    _, z = zone(s, x0 + Inches(0.22), y + Inches(0.09), w0 - Inches(0.3), Inches(0.3))
    para(z, m, taille=12, couleur=NOIR, premier=True)
    for val, x, meilleur in [(a, x0 + w0, gagne_a is True),
                             (b, x0 + w0 + w1, gagne_a is False)]:
        _, z = zone(s, x, y + Inches(0.08), w1, Inches(0.32), align=PP_ALIGN.CENTER)
        para(z, val, taille=12.5, gras=meilleur, couleur=ROUGE if meilleur else GRIS,
             align=PP_ALIGN.CENTER, premier=True)
    rangs.append(r)

lect = rect(s, Inches(0.95), Inches(6.20), Inches(11.40), Inches(0.72), CREME,
            bord=GRIS_CLAIR)
_, tf = zone(s, Inches(1.30), Inches(6.34), Inches(10.7), Inches(0.5))
riche(tf, [("Les écarts de coût sont établis. ", False, GRIS),
           ("Sur la qualité jugée, aucun écart n'est statistiquement significatif",
            True, NOIR),
           (" — tests appariés de McNemar et de Wilcoxon.", False, GRIS)],
      taille=12.5, premier=True)

transition(s, "push", 700, dir="l")
animer(s, [(jeu, "balayage", 150, 420), (rangs, "bandeau", 90, 300),
           ([lect], "fondu", 0, 450)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  13 — L'ARCHITECTURE RETENUE
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
fond(s)
filigrane(s)
bandeau(s, "7", "L'architecture retenue : la modulaire",
        sous_titre="À qualité jugée équivalente, trois raisons départagent",
        n_page=13, total=TOTAL)

ar = img("archi_retenue.jpg")
if ar:
    image(s, ar, Inches(0.95), Inches(1.50), w=Inches(7.05))

rais = []
RAIS = [("La reproductibilité", "100 % des répétitions citent les mêmes montants, contre "
         "90 % pour l'agentique.", ROUGE),
        ("Le coût", "Un seul appel au modèle par question, contre 2,36 — et une latence "
         "médiane divisée par deux.", OR),
        ("L'auditabilité", "Un chemin fixe permet de savoir quels outils ont été appelés, "
         "et pourquoi.", ARDOISE)]
for i, (t, d, col) in enumerate(RAIS):
    y = Inches(1.50 + i * 1.32)
    c = carte(s, Inches(8.30), y, Inches(4.05), Inches(1.18), t, [d], accent=col,
              taille_titre=14, taille_texte=11)
    rais.append(c)

concl = rect(s, Inches(0.95), Inches(5.62), Inches(11.40), Inches(1.10), NOIR)
rect(s, Inches(0.95), Inches(5.62), Inches(0.075), Inches(1.10), ROUGE_VIF)
_, tf = zone(s, Inches(1.35), Inches(5.82), Inches(10.6), Inches(0.8))
riche(tf, [("Le modèle garde un rôle essentiel, mais il intervient ", False, BLANC),
           ("après la détermination du résultat", True, ROUGE_VIF),
           (". Dans un contexte bancaire, l'exactitude, la reproductibilité et "
            "l'auditabilité\nl'emportent sur la souplesse d'une architecture pilotée "
            "par le modèle.", False, BLANC)],
      taille=13, premier=True, interligne=1.32)

transition(s, "wipe", 650, dir="l")
animer(s, [(rais, "balayage", 160, 450), ([concl], "fondu", 0, 550)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  14 — LA PROJECTION A TROIS ANS
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
fond(s)
filigrane(s)
bandeau(s, "8", "La modélisation prospective à trois ans",
        sous_titre="Une logique métier traduite en règles de calcul reproductibles",
        n_page=14, total=TOTAL)

etapes = []
ET = [("Référence", "La cible est la moyenne des trois meilleures banques du panel — pour "
       "qu'un résultat exceptionnel isolé ne fasse pas la norme.", "C = (B1 + B2 + B3) / 3",
       ROUGE),
      ("Écart", "La différence entre la cible et la performance actuelle. Déjà au-dessus, "
       "aucun rattrapage artificiel n'est imposé.", "E = max(0, C - V0)", OR),
      ("Scénarios", "Trois niveaux d'exécution simulés. Ce sont des hypothèses, non des "
       "probabilités.", "Es = ws × E     ws = 0,60 · 1,00 · 1,20", ARDOISE),
      ("Trajectoire", "L'écart est réparti linéairement sur trois exercices.",
       "Vt = V0 + (Es / 3) × t", VERT)]
for i, (t, d, f, col) in enumerate(ET):
    y = Inches(1.50 + i * 1.24)
    b = rect(s, Inches(0.95), y, Inches(7.35), Inches(1.10), BLANC, bord=GRIS_CLAIR)
    rect(s, Inches(0.95), y, Inches(0.055), Inches(1.10), col)
    p = rect(s, Inches(1.18), y + Inches(0.28), Inches(0.54), Inches(0.54), col,
             forme=MSO_SHAPE.OVAL)
    tfp = p.text_frame
    tfp.margin_left = tfp.margin_right = tfp.margin_top = tfp.margin_bottom = 0
    tfp.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tfp, str(i + 1), taille=15, gras=True, couleur=BLANC, align=PP_ALIGN.CENTER,
         premier=True)
    _, z = zone(s, Inches(1.92), y + Inches(0.16), Inches(6.2), Inches(0.85))
    para(z, t, taille=14, gras=True, couleur=NOIR, police=TITRE, premier=True)
    para(z, d, taille=11, couleur=GRIS, avant=4, interligne=1.22)
    fo = rect(s, Inches(8.55), y + Inches(0.22), Inches(3.80), Inches(0.66), NOIR)
    tff = fo.text_frame
    tff.margin_left = tff.margin_right = Inches(0.14)
    tff.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tff, f, taille=12, gras=True, couleur=BLANC, police="Consolas",
         align=PP_ALIGN.CENTER, premier=True)
    etapes.append(b)
    etapes.append(fo)

ctrl = rect(s, Inches(0.95), Inches(6.42), Inches(11.40), Inches(0.62), CREME,
            bord=GRIS_CLAIR)
_, tf = zone(s, Inches(1.30), Inches(6.54), Inches(10.7), Inches(0.4))
riche(tf, [("Contrôle de plausibilité : ", True, ROUGE),
           ("l'effort annuel requis est comparé à la dynamique historique réellement "
            "observée. Il n'altère pas la trajectoire, il l'apprécie.", False, GRIS)],
      taille=12, premier=True)

transition(s, "push", 700, dir="l")
animer(s, [(etapes, "balayage", 120, 380), ([ctrl], "fondu", 0, 400)])


# ══════════════════════════════════════════════════════════════════════════════════════
#  15 — DÉMONSTRATION ET CHIFFRES CLÉS
# ══════════════════════════════════════════════════════════════════════════════════════
s = page()
degrade(s, 0, 0, L, H, "12121A", "5E0018", angle=30)
for i in range(11):
    for j in range(4):
        if (i + j) % 3:
            rect(s, Inches(10.9 + i * 0.20), Inches(0.40 + j * 0.20),
                 Inches(0.06), Inches(0.06), BLANC, transparence=0.78)

_, tf = zone(s, Inches(0.95), Inches(0.62), Inches(11.4), Inches(0.9))
para(tf, "DÉMONSTRATION ET CHIFFRES CLÉS", taille=11, gras=True, couleur=ROUGE_VIF,
     premier=True, espacement=2.0)
para(tf, "Ce que le projet a produit, et ce qu'il change", taille=27, gras=True,
     couleur=BLANC, police=TITRE, avant=4)

kpis = []
KPI = [("100,0 %", "d'exactitude sur les\n109 questions chiffrées"),
       ("2,05 s", "de latence médiane\ncontre 4,42 s"),
       ("162 s → 3,8 s", "sur l'écran le plus lourd\naprès optimisation"),
       ("20 M FCFA", "d'économie annuelle\npotentielle")]
for i, (v, l) in enumerate(KPI):
    x = Inches(0.95 + i * 2.92)
    b = rect(s, x, Inches(2.20), Inches(2.62), Inches(1.55), BLANC, transparence=0.92)
    rect(s, x, Inches(2.20), Inches(2.62), Inches(0.05), ROUGE_VIF)
    _, z = zone(s, x + Inches(0.24), Inches(2.44), Inches(2.2), Inches(1.2))
    para(z, v, taille=25 if len(v) < 10 else 19, gras=True, couleur=ROUGE_VIF,
         police=TITRE, premier=True, interligne=1.0)
    para(z, l, taille=10.5, couleur=BLANC, avant=5, interligne=1.24)
    kpis.append(b)

sh = img("u02_accueil.jpg")
if sh:
    # Contrainte en HAUTEUR et non en largeur : reglee sur la largeur, la capture
    # descendait jusqu a recouvrir « MERCI DE VOTRE ATTENTION ». Vu sur la vue exportee.
    image(s, sh, Inches(0.95), Inches(4.05), h=Inches(2.30), bord=False)

livr = []
LIVR = [("L'application", "Cinq écrans, sept banques, un assistant. En ligne sur "
         "spybusiness.onrender.com."),
        ("Le mémoire", "88 pages : conception, évaluation comparative, résultats."),
        ("La documentation", "Vue technique et vue utilisateur, pour la reprise du projet.")]
for i, (t, d) in enumerate(LIVR):
    y = Inches(4.05 + i * 0.92)
    b = rect(s, Inches(7.30), y, Inches(5.05), Inches(0.80), BLANC, transparence=0.93)
    rect(s, Inches(7.30), y, Inches(0.05), Inches(0.80), ROUGE_VIF)
    _, z = zone(s, Inches(7.58), y + Inches(0.11), Inches(4.6), Inches(0.6))
    para(z, t, taille=13, gras=True, couleur=BLANC, police=TITRE, premier=True)
    para(z, d, taille=10.5, couleur=ROSE, avant=2, interligne=1.20)
    livr.append(b)

_, tf = zone(s, Inches(0.95), Inches(6.90), Inches(11.4), Inches(0.4),
             align=PP_ALIGN.CENTER)
para(tf, "MERCI DE VOTRE ATTENTION", taille=13, gras=True, couleur=BLANC,
     align=PP_ALIGN.CENTER, premier=True, espacement=2.2)

transition(s, "fade", 900)
animer(s, [(kpis, "balayage", 140, 420), (livr, "fondu", 130, 380)])


# ══════════════════════════════════════════════════════════════════════════════════════
SORTIE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "soutenance_zongo.pptx")
prs.save(SORTIE)
print(f"  {len(prs.slides.__iter__.__self__._sldIdLst)} diapositives -> {SORTIE}")
