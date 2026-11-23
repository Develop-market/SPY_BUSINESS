# -*- coding: utf-8 -*-
"""
injecter_texte.py — remplace le Lorem ipsum par le contenu verifie de la soutenance.
=====================================================================================
Ouvre SpyBusiness_Soutenance.pptx (deja assemble par construire_soutenance.py, images
corrigees) et injecte, diapo par diapo, UNIQUEMENT des faits verifies dans le memoire
final (C:\\Users\\ALPHEE COLOMBE\\Desktop\\MEMOIRE_LATEX) -- jamais un chiffre plausible.
Sources exactes citees en commentaire a cote de chaque chiffre.

Regle du chantier (deja rencontree avec Erreur 3) : plusieurs titres Canva a deux
segments colores se chevauchent physiquement DES le template d'origine (verifie en
inspectant les positions/tailles XML, pas seulement a l'oeil) -- ce n'est pas un defaut
introduit ici. Mitigation : mots courts + reduction de la taille de police la ou la
geometrie XML (boites qui se recouvrent, hauteur de ligne > hauteur de boite) le montre
necessaire, avant toute verification visuelle -- pas seulement apres.

Diapo 4 (Direction de l'Innovation) est construite dans briques_maison.py avec son
texte final deja en place : rien a injecter ici pour elle.
"""
import io
import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from lxml import etree
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Pt

ICI = os.path.dirname(os.path.abspath(__file__))
FICHIER = os.path.join(ICI, "SpyBusiness_Soutenance.pptx")


def par_nom(slide):
    return {sh.name: sh for sh in slide.shapes}


def texte(slide, nom, contenu):
    """Remplace le texte d'une forme nommee EN CONSERVANT le XML du tout premier
    paragraphe (rPr complet -- degrade colore compris, un a:gradFill n'est pas une
    couleur RGB simple et se perdait silencieusement avec la premiere version qui
    copiait juste font.color.rgb, cf. "Financial"->"SPYBUSINESS" reste noir uni au
    lieu du degrade rouge d'origine). On clone ce paragraphe une fois par ligne du
    nouveau texte, et on ne garde que son PREMIER run a chaque fois (les modeles
    Canva ici n'ont jamais plus d'un run par ligne de remplacement)."""
    formes = par_nom(slide)
    sh = formes.get(nom)
    if sh is None or not sh.has_text_frame:
        print(f"  ATTENTION forme absente : {nom!r}")
        return
    tf = sh.text_frame
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


def taille(slide, nom, pt):
    formes = par_nom(slide)
    sh = formes.get(nom)
    if sh is None or not sh.has_text_frame:
        return
    for p in sh.text_frame.paragraphs:
        for r in p.runs:
            r.font.size = Pt(pt)


prs = Presentation(FICHIER)
S = list(prs.slides)

# ═════════════════════════════════════════════════════════════════════════════════════
# 1 — GARDE
# ═════════════════════════════════════════════════════════════════════════════════════
s = S[0]
texte(s, "TextBox 27", "SGCI")
texte(s, "TextBox 28",
      "SpyBusiness : un systeme de veille concurrentielle bancaire fonde sur un RAG, "
      "concu pour la Direction de l'Innovation de la Societe Generale Cote d'Ivoire.")
texte(s, "TextBox 29", "spybusiness.onrender.com")   # URL reelle deployee (section 3, CLAUDE.md)
texte(s, "TextBox 30", "En ligne")
taille(s, "TextBox 29", 20)   # 28pt d'origine : boite 30 (etiquette) empietait deja dessus
texte(s, "TextBox 31", "SPYBUSINESS")
texte(s, "TextBox 32", "SOUTENANCE")
taille(s, "TextBox 31", 52)   # titre 138pt d'origine : boites qui se chevauchent (voir en-tete)
taille(s, "TextBox 32", 52)
texte(s, "TextBox 36", "A. ZONGO MESSOU")
taille(s, "TextBox 36", 22)   # 32pt d'origine dimensionne pour "PERIODE 2025 - 2026" (2 lignes)

# Diapo 3 (Entreprise + Direction de l'Innovation) est construite a la main dans
# briques_maison.py, texte final deja en place : rien a injecter ici pour elle.

# ═════════════════════════════════════════════════════════════════════════════════════
# 4 — CONTEXTE : donnee inexploitee -- 04_partie1.tex l.168-219 (Tableau 1)
# ═════════════════════════════════════════════════════════════════════════════════════
s = S[3]
texte(s, "TextBox 15", "Une donnee")
texte(s, "TextBox 16", "inexploitee")
taille(s, "TextBox 15", 40)   # 80pt d'origine : une ligne depasse deja la boite (1,33in > 1,02in)
taille(s, "TextBox 16", 40)
texte(s, "TextBox 17",
      "33 etablissements de credit dont 29 banques publient chacune leurs tarifs "
      "chaque semestre et leurs etats financiers chaque annee, sous le controle de la "
      "BCEAO et de l'UEMOA.")
texte(s, "TextBox 18",
      "Ces donnees sont publiques mais dispersees et heterogenes (PDF scannes, mises "
      "en page denses) : jamais consolidees ni comparees en continu.")
texte(s, "TextBox 31", "Information dispersee")
texte(s, "TextBox 32", "Aucun comparatif")
texte(s, "TextBox 33", "Analyse manuelle")
texte(s, "TextBox 34", "Suivi externalise")

# ═════════════════════════════════════════════════════════════════════════════════════
# 6 — PROBLEMATIQUE -- 01_liminaires.tex l.80-88, 04_partie1.tex l.212-228
# ═════════════════════════════════════════════════════════════════════════════════════
s = S[5]
# TextBox23 est la boite du HAUT, TextBox22 celle du BAS (geometrie XML verifiee -- pas
# l'ordre du scan) : "LE" doit donc aller dans 23 et "PROBLEME" dans 22, sinon le titre
# se lit a l'envers ("PROBLEME LE").
texte(s, "TextBox 23", "LE")
texte(s, "TextBox 22", "PROBLEME")
texte(s, "TextBox 28", "SGCI")
texte(s, "TextBox 24",
      "Comparaison interne impossible : seul recours, un prestataire externe, "
      "~10 M FCFA par analyse, 2 mois de delai.")
texte(s, "TextBox 25",
      "Analyse financiere manuelle sur 7 etablissements, indicateur par indicateur, "
      "limitee au dernier exercice publie.")
texte(s, "TextBox 26",
      "Aucune capitalisation interne : l'historique des analyses reste detenu par "
      "les cabinets sollicites.")
for n in ("TextBox 24", "TextBox 25", "TextBox 26"):
    taille(s, n, 16)   # 24pt d'origine dimensionne pour 2 lignes de lorem ipsum tres court
texte(s, "TextBox 29",
      "Une information disponible, mais jamais transformee en decision rapide.")

# ═════════════════════════════════════════════════════════════════════════════════════
# 7 — SOLUTION PROPOSEE -- 04_partie1.tex l.256-273 (cahier des charges, 3 briques)
# ═════════════════════════════════════════════════════════════════════════════════════
s = S[6]
texte(s, "TextBox 23", "LA")
texte(s, "TextBox 22", "SOLUTION")
texte(s, "TextBox 28", "SGCI")
texte(s, "TextBox 24",
      "Une chaine d'ingestion documentaire : extraction, nettoyage et structuration "
      "des documents bancaires.")
texte(s, "TextBox 25",
      "Une base centralisee PostgreSQL + pgvector : donnees structurees et recherche "
      "semantique sur le meme socle.")
texte(s, "TextBox 26",
      "Une application d'analyse : tableaux de bord et assistant conversationnel, "
      "sourcees et verifiables.")
for n in ("TextBox 24", "TextBox 25", "TextBox 26"):
    taille(s, n, 16)
texte(s, "TextBox 29",
      "Objectif : transformer une information disponible mais eparse en un outil de "
      "veille strategique et d'aide a la decision.")

# ═════════════════════════════════════════════════════════════════════════════════════
# 8 — IMPLEMENTATION 1 : extraction -- cahier des charges (3 chaines specialisees)
# ═════════════════════════════════════════════════════════════════════════════════════
s = S[7]
texte(s, "TextBox 27", "Lire")        # boite 27 large de 2,19in seulement : mot court obligatoire
texte(s, "TextBox 28", "la donnee")
texte(s, "TextBox 29",
      "Trois chaines d'extraction specialisees transforment les documents bancaires "
      "(tarifs, etats financiers, reglementation) en donnees structurees, avant "
      "chargement en base.")
texte(s, "TextBox 30", "Grilles tarifaires")
texte(s, "TextBox 31", "Etats financiers")
texte(s, "TextBox 32", "Textes reglementaires")
texte(s, "TextBox 33", "PDF semestriels, mise en page dense : extraction par Vision LLM.")
texte(s, "TextBox 34", "Rapports annuels : indicateurs cles releves par banque et exercice.")
texte(s, "TextBox 35", "Corpus BCEAO/UEMOA, decoupe par article pour la recherche vectorielle.")

# ═════════════════════════════════════════════════════════════════════════════════════
# 9 — IMPLEMENTATION 2 : base de donnees -- 04_partie1.tex l.266-273
# ═════════════════════════════════════════════════════════════════════════════════════
s = S[8]
texte(s, "TextBox 37", "Base de")     # boite 38 large de 3,81in : "de donnees" (10 car.) y deborde
texte(s, "TextBox 38", "donnees")
texte(s, "TextBox 39",
      "PostgreSQL centralise, enrichi de l'extension pgvector : une seule base "
      "reunit donnees chiffrees et representations vectorielles.")
texte(s, "TextBox 40",
      "Deux voies d'acces sur le meme socle : la requete SQL pour une valeur exacte, "
      "la similarite cosinus pour un contenu textuel.")
texte(s, "TextBox 41", "Voie SQL")
texte(s, "TextBox 42", "Similarite")
texte(s, "TextBox 43", "Veille sourcee")

# ═════════════════════════════════════════════════════════════════════════════════════
# 12 — EVALUATION -- 08b_evaluation.tex (Tableau 5, tests McNemar/Wilcoxon)
# ═════════════════════════════════════════════════════════════════════════════════════
s = S[11]
texte(s, "TextBox 15", "")        # boite droite chevauchant deja la suivante des l'origine
texte(s, "TextBox 16", "L'EVALUATION")
taille(s, "TextBox 16", 28)       # 70pt d'origine : boite large de 2,54in seulement (deborde a 40pt)
texte(s, "TextBox 17",
      "Quatre mesures opposent les deux orchestrations sur le meme jeu de 169 "
      "questions : exactitude, cout d'execution, reproductibilite, qualite jugee.")
texte(s, "TextBox 30", "Exactitude")
texte(s, "TextBox 31", "Cout et latence")
texte(s, "TextBox 32", "Reproductibilite")
texte(s, "TextBox 33", "Qualite jugee")
texte(s, "TextBox 34",
      "Modulaire 100,0 % contre 99,1 % (109 questions, McNemar p = 1,000).")
texte(s, "TextBox 35",
      "1 appel au modele contre 2,4 en moyenne ; latence mediane 2,1 s contre 4,4 s.")
texte(s, "TextBox 36",
      "Meme question posee 8 fois : 100 % de stabilite factuelle contre 90 % pour "
      "l'agentique.")
texte(s, "TextBox 37",
      "Notee par un juge d'une autre famille (GPT), a l'aveugle : aucun ecart "
      "significatif etabli (test de Wilcoxon).")

# ═════════════════════════════════════════════════════════════════════════════════════
# 13 — ARCHITECTURE RETENUE -- 08b_evaluation.tex l.350-373 (Tableau 5 + 3 raisons)
# ═════════════════════════════════════════════════════════════════════════════════════
s = S[12]
texte(s, "TextBox 27", "La")          # boite 27 large de 2,19in seulement : mot court obligatoire
texte(s, "TextBox 28", "modulaire")
texte(s, "TextBox 29",
      "Trois raisons emportent la decision : la reproductibilite, la latence "
      "mediane, et l'auditabilite d'un chemin fixe et verifiable.")
texte(s, "TextBox 30", "Stable")
texte(s, "TextBox 31", "Rapide")
texte(s, "TextBox 32", "Auditable")
texte(s, "TextBox 33", "8 repetitions de la meme question : 100 % de montants identiques cites.")
texte(s, "TextBox 34", "Latence mediane 2,1 s, deux fois plus rapide que l'agentique (4,4 s).")
texte(s, "TextBox 35", "Un seul chemin, fixe, verifiable a chaque etape.")

# ═════════════════════════════════════════════════════════════════════════════════════
# 14 — PROJECTION A 3 ANS -- 08d_logique_projection.tex (methode + exemple chiffre reel)
# ═════════════════════════════════════════════════════════════════════════════════════
s = S[13]
texte(s, "TextBox 37", "Projection")
texte(s, "TextBox 38", "a 3 ans")
taille(s, "TextBox 37", 38)   # 80pt d'origine : hauteur de ligne > hauteur de boite
taille(s, "TextBox 38", 38)
texte(s, "TextBox 39",
      "Diagnostic -> Benchmark -> Projection -> Controle de plausibilite -> Action : "
      "le modele de langage n'intervient qu'en aval, pour formuler.")
texte(s, "TextBox 40", "Reference")
texte(s, "TextBox 41", "Ecart")
texte(s, "TextBox 42", "3 scenarios")
texte(s, "TextBox 43", "Effet mesure")
texte(s, "TextBox 44", "Cible = moyenne des 3 meilleures banques du panel.")
texte(s, "TextBox 45", "Rattrapage nul si la SGCI depasse deja la reference.")
texte(s, "TextBox 46", "Prudent, cible, ambitieux : ponderation 0,60 / 1,00 / 1,20.")
texte(s, "TextBox 47",
      "Cout du risque cible 2,47 % (contre 17 % en 2025) : ~36,6 Mds FCFA "
      "d'effet estime sur le resultat net.")

# ═════════════════════════════════════════════════════════════════════════════════════
# 15 — MERCI -- remerciements reels (CLAUDE.md, encadrants) + chiffres cles du memoire
# ═════════════════════════════════════════════════════════════════════════════════════
s = S[14]
texte(s, "TextBox 27", "SGCI")
texte(s, "TextBox 28",
      "Merci a mes encadrants, M. MONSIA DOUGBAN et M. MOUAHA HANDY, et a la "
      "Direction de l'Innovation de la SGCI.  169 questions evaluees, 100,0 % "
      "d'exactitude, architecture modulaire retenue.")
texte(s, "TextBox 29", "spybusiness.onrender.com")
texte(s, "TextBox 30", "En ligne")
taille(s, "TextBox 29", 20)
texte(s, "TextBox 31", "MERCI")
texte(s, "TextBox 32", "A TOUS")
taille(s, "TextBox 31", 52)   # meme bug d'origine que la diapo 1 (titre 138pt)
taille(s, "TextBox 32", 52)

prs.save(FICHIER)
print(f"texte injecte -> {FICHIER}")
