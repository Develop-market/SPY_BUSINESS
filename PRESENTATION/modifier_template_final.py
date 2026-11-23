# -*- coding: utf-8 -*-
"""
modifier_template_final.py
==========================
Prend le template Canva "Orange Black And White Modern Construction Company",
copie ses 12 slides, en duplique 3 pour arriver à 15, remplace le texte
et recolore l'orange -> Rouge SGCI (E4002B).

Résultat : PRESENTATION/SpyBusiness_Soutenance.pptx
"""
import copy, os, re, shutil
from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn

# ── Chemins ───────────────────────────────────────────────────────────
TPL = r'C:\Users\ALPHEE COLOMBE\Downloads\Orange Black And White Modern Construction Company.pptx'
OUT = r'C:\Users\ALPHEE COLOMBE\Desktop\BACK\PRESENTATION\SpyBusiness_Soutenance.pptx'
shutil.copy2(TPL, OUT)
prs = Presentation(OUT)

# ── Couleurs ──────────────────────────────────────────────────────────
# Toutes les variantes d'orange utilisées par Canva dans ce template
ORANGE_VARIANTS = [
    "FF6B35","F07B00","FF6600","FF8C32","F97316",
    "EA580C","D97706","FB923C","FDBA74","E85D04",
    "FF7700","FF5500","F59E0B","CC4400","FF4500",
    # couleur exacte Canva "Orange Black" = souvent EC6C2D ou similaire
    "EC6C2D","E86A2E","F56A00","F5760A","F5700A",
    "F5720A","F5740A","F5760A",
]

def recolor_xml(xml_str):
    """Remplace dans le XML toute couleur orange par Rouge SGCI."""
    changed = False
    for ohex in ORANGE_VARIANTS:
        for variant in [ohex.upper(), ohex.lower()]:
            if variant in xml_str:
                xml_str = xml_str.replace(variant, "E4002B")
                changed = True
    return xml_str, changed

def recolor_slide(slide):
    """Recolore toutes les formes d'une slide."""
    for sh in slide.shapes:
        try:
            xml = etree.tostring(sh.element, encoding="unicode")
            new_xml, changed = recolor_xml(xml)
            if changed:
                new_el = etree.fromstring(new_xml)
                sh.element.getparent().replace(sh.element, new_el)
        except Exception:
            pass

# ── Écriture de texte ─────────────────────────────────────────────────
def set_text(slide, shape_name, text, *, bold=None, size_pt=None):
    """
    Remplace le texte d'une shape par name.
    Préserve la police et la couleur d'origine du premier run.
    Si text contient '\n', chaque partie va dans un paragraphe distinct.
    """
    for sh in slide.shapes:
        if sh.name != shape_name:
            continue
        if not hasattr(sh, 'text_frame'):
            continue
        tf = sh.text_frame
        tf.word_wrap = True

        # snapshot style du premier run existant
        font_name = None
        font_size = None
        font_bold = None
        font_color = None
        if tf.paragraphs and tf.paragraphs[0].runs:
            r0 = tf.paragraphs[0].runs[0]
            font_name  = r0.font.name
            font_size  = r0.font.size
            font_bold  = r0.font.bold
            try:
                font_color = r0.font.color.rgb
            except Exception:
                font_color = None

        # vide tout le text frame
        for p in tf.paragraphs:
            for r in p.runs:
                r.text = ""

        lines = text.split('\n')
        for li, line in enumerate(lines):
            if li == 0:
                p = tf.paragraphs[0]
            else:
                p = tf.add_paragraph()
                # clone l'alignement du premier para
                if tf.paragraphs[0].alignment:
                    p.alignment = tf.paragraphs[0].alignment

            if not p.runs:
                r = p.add_run()
            else:
                r = p.runs[0]

            r.text = line

            # restaure la police
            if font_name:  r.font.name  = font_name
            if font_size:  r.font.size  = font_size
            if font_bold is not None: r.font.bold = font_bold
            if font_color:
                try:  r.font.color.rgb = font_color
                except Exception: pass

            # surcharges
            if bold is not None:    r.font.bold  = bold
            if size_pt is not None:
                from pptx.util import Pt
                r.font.size = Pt(size_pt)
        return
    # shape not found — log silencieux
    pass


# ── Duplication d'une slide ───────────────────────────────────────────
def duplicate_slide(prs, slide_index):
    """
    Duplique la slide à slide_index et l'ajoute à la fin du diaporama.
    Renvoie la nouvelle slide.
    """
    template = prs.slides[slide_index]
    blank_layout = template.slide_layout

    new_slide = prs.slides.add_slide(blank_layout)

    # Copie les éléments XML de la slide source dans la nouvelle
    for el in new_slide.element.spTree:
        new_slide.element.spTree.remove(el)

    for el in copy.deepcopy(template.element).spTree:
        new_slide.element.spTree.append(el)

    return new_slide


# ═══════════════════════════════════════════════════════════════════════
#  MAPPING SLIDE PAR SLIDE
#  Le template a 12 slides. On duplique 3 slides pour avoir 15.
#  Plan :
#   1 → garde (S1 original)
#   2 → sommaire (S2)
#   3 → SGCI (S3 vision/mission)
#   4 → Contexte (S4 why choose us)
#   5 → RAG évolution (S5 services)
#   6 → Problématique (S6 advantages)
#   7 → Solution (S7 team) — adapté
#   8 → Implem 1 : Sources (S8 building for society)
#   9 → Implem 2 : Base de données (S9 portfolio) — DUPLIQUÉE DE S3
#   10 → Socle commun (S10 testimonials)
#   11 → Les deux architectures (S11 contact)
#   12 → Évaluation (S4 dupliqué)
#   13 → Architecture retenue (S6 dupliqué)
#   14 → Projection 3 ans (S5 dupliqué)
#   15 → Démo + Merci (S12 thank you)
# ═══════════════════════════════════════════════════════════════════════

# ── 1. On duplique 3 slides avant de modifier quoi que ce soit ────────
s9_extra  = duplicate_slide(prs, 2)   # clone de S3  → slide 13 (idx 12)
s12_extra = duplicate_slide(prs, 3)   # clone de S4  → slide 14 (idx 13)
s14_extra = duplicate_slide(prs, 4)   # clone de S5  → slide 15 (idx 14)

# Maintenant prs.slides a 15 slides (idx 0..14)
all_slides = list(prs.slides)

# ── 2. Recoloration de toutes les slides ─────────────────────────────
for sl in all_slides:
    recolor_slide(sl)

# ─────────────────────────────────────────────────────────────────────
# SLIDE 1  — PAGE DE GARDE
# ─────────────────────────────────────────────────────────────────────
s = all_slides[0]
set_text(s, "TextBox 31", "SPYBUSINESS")
set_text(s, "TextBox 40", "PRÉSENTATION")
set_text(s, "TextBox 42", "SOUTENANCE")
set_text(s, "TextBox 43", "2025 – 2026")
set_text(s, "TextBox 39", "ZONGO MESSOU Alphée Colombe")
set_text(s, "TextBox 41", "Société Générale Côte d'Ivoire")

# ─────────────────────────────────────────────────────────────────────
# SLIDE 2  — PLAN / SOMMAIRE
# ─────────────────────────────────────────────────────────────────────
s = all_slides[1]
set_text(s, "TextBox 22", "PLAN DE LA")
set_text(s, "TextBox 23", "PRÉSENTATION")
set_text(s, "TextBox 24",
    "01 — Présentation de la SGCI\n"
    "02 — Contexte et défaillances\n"
    "03 — L'évolution du RAG\n"
    "04 — Problématique centrale\n"
    "05 — La solution : SpyBusiness\n"
    "06 — Extraction et base de données\n"
    "07 — Le socle commun et ses deux modes\n"
    "08 — Les deux architectures\n"
    "09 — L'évaluation comparative\n"
    "10 — Architecture retenue\n"
    "11 — Projection à 3 ans\n"
    "12 — Démonstration et chiffres clés"
)

# ─────────────────────────────────────────────────────────────────────
# SLIDE 3  — LA SGCI
# Shapes : TextBox 48/49 = grand titre ; 50/51 = sous-titres ; 52/53 = corps
# ─────────────────────────────────────────────────────────────────────
s = all_slides[2]
set_text(s, "TextBox 48", "LA SGCI &")
set_text(s, "TextBox 49", "SON MARCHÉ")
set_text(s, "TextBox 50", "BANQUE LEADER")
set_text(s, "TextBox 51", "DIRECTION INNOVATION")
set_text(s, "TextBox 52",
    "1er rang du marché ivoirien en PNB (276 Mds FCFA).\n"
    "Résultat Net : 101 Mds — 27,8 % des profits du secteur.\n"
    "Banque universelle depuis 1962. 7 concurrents directs."
)
set_text(s, "TextBox 53",
    "Structure d'accueil du stage (Cellule Data Science).\n"
    "Créée en 2022. Mission : décider sur des données réelles.\n"
    "Aucun outil de veille concurrentielle structuré n'existait."
)

# ─────────────────────────────────────────────────────────────────────
# SLIDE 4  — CONTEXTE : LA DONNÉE EXISTE MAIS EST INEXPLOITABLE
# Shapes : TextBox 22/23 = grand titre ; 24 = corps ; 37/38/39/40 = 4 items
# ─────────────────────────────────────────────────────────────────────
s = all_slides[3]
set_text(s, "TextBox 22", "LA DONNÉE")
set_text(s, "TextBox 23", "EST INEXPLOITABLE")
set_text(s, "TextBox 24",
    "Les 7 banques publient tarifs, bilans et rapports — mais "
    "ces 93 documents sont hétérogènes, mal structurés. "
    "Une analyse externe coûte > 30 millions FCFA. Délai : plusieurs semaines."
)
set_text(s, "TextBox 37", "Grilles tarifaires semestrielles (70 docs)")
set_text(s, "TextBox 38", "États financiers annuels (18 docs)")
set_text(s, "TextBox 39", "Textes réglementaires BCEAO/UEMOA")
set_text(s, "TextBox 40", "Veille sectorielle (presse, institutions)")

# ─────────────────────────────────────────────────────────────────────
# SLIDE 5  — ÉVOLUTION DU RAG
# Shapes : TextBox 53/54 = grand titre ; 55/56/57/58 = 4 rubriques ; 59/60/61/62 = descriptions
# ─────────────────────────────────────────────────────────────────────
s = all_slides[4]
set_text(s, "TextBox 53", "ÉVOLUTION")
set_text(s, "TextBox 54", "DU RAG")
set_text(s, "TextBox 55", "RAG NAÏF (2020)")
set_text(s, "TextBox 56", "RAG AVANCÉ (2022)")
set_text(s, "TextBox 57", "RAG MODULAIRE (2023)")
set_text(s, "TextBox 58", "RAG AGENTIQUE (2024)")
set_text(s, "TextBox 59",
    "Séquence linéaire. Aucun contrôle de qualité. "
    "Le LLM hallucine si la recherche est imprécise."
)
set_text(s, "TextBox 60",
    "Réécriture de requête, reranking, compression. "
    "Meilleur — mais une seule passe, toujours fragile."
)
set_text(s, "TextBox 61",
    "Routeur à règles. Briques indépendantes. Chemin fixe. "
    "Reproductible, auditable, économique."
)
set_text(s, "TextBox 62",
    "Le LLM choisit ses outils et boucle (≤6 tours). "
    "Très souple — mais stochastique et coûteux."
)

# ─────────────────────────────────────────────────────────────────────
# SLIDE 6  — PROBLÉMATIQUE
# Shapes : TextBox 22/23 = grand titre ; 24 = corps ; 37/38/39/40 = 4 points
# ─────────────────────────────────────────────────────────────────────
s = all_slides[5]
set_text(s, "TextBox 22", "LA")
set_text(s, "TextBox 23", "PROBLÉMATIQUE")
set_text(s, "TextBox 24",
    "Comment concevoir un système IA capable de produire, à partir de "
    "données bancaires publiques hétérogènes, des analyses concurrentielles "
    "dont chaque chiffre est exact, reproductible et vérifiable ?"
)
set_text(s, "TextBox 37", "L'ingénierie des données")
set_text(s, "TextBox 38", "L'architecture du système")
set_text(s, "TextBox 39", "La preuve expérimentale")
set_text(s, "TextBox 40", "Le déploiement en production")

# ─────────────────────────────────────────────────────────────────────
# SLIDE 7  — SOLUTION : SpyBusiness
# Shapes : TextBox 32/33 = titre ; 34/35/36 = noms équipe ; 37/38/39 = rôles
# → On adapte : 3 piliers de SpyBusiness
# ─────────────────────────────────────────────────────────────────────
s = all_slides[6]
set_text(s, "TextBox 32", "LA SOLUTION :")
set_text(s, "TextBox 33", "SPYBUSINESS")
set_text(s, "TextBox 34", "PRINCIPE DIRECTEUR")
set_text(s, "TextBox 35", "PILIER 1 : INGESTION")
set_text(s, "TextBox 36", "PILIER 2 : BASE")
set_text(s, "TextBox 37",
    "« Le déterministe établit, le modèle formule. »\n"
    "Aucun chiffre ne vient du LLM."
)
set_text(s, "TextBox 38",
    "Extraction hybride : pdfplumber, Docling+EasyOCR, Tesseract. "
    "93 documents traités."
)
set_text(s, "TextBox 39",
    "PostgreSQL + pgvector. 33 857 lignes. "
    "31 985 vecteurs 768 dim."
)

# ─────────────────────────────────────────────────────────────────────
# SLIDE 8  — EXTRACTION DES DONNÉES
# Shapes : TextBox 41/42 = titre ; 43/44/45/46 = corps ; 47/48/49 = 3 items
# ─────────────────────────────────────────────────────────────────────
s = all_slides[7]
set_text(s, "TextBox 41", "EXTRACTION")
set_text(s, "TextBox 42", "DES DONNÉES")
set_text(s, "TextBox 43",
    "pdfplumber : lit les tableaux d'un PDF natif sans perte. "
    "Échoue sur les pages scannées."
)
set_text(s, "TextBox 44",
    "Docling + EasyOCR : restitue texte et tableaux dans un même passage. "
    "Retenu pour les états financiers et les grilles scannées."
)
set_text(s, "TextBox 45",
    "Tesseract : relecture caractère par caractère sur image agrandie. "
    "Relais de secours sur scans très dégradés."
)
set_text(s, "TextBox 46",
    "Seuils de validation empiriques : ≥ 4 feuilles · ≥ 200 cellules "
    "pour une grille. ≥ 2 Ko pour un état financier."
)
set_text(s, "TextBox 47", "Grilles tarifaires\n→ pdfplumber ou Docling")
set_text(s, "TextBox 48", "États financiers\n→ Docling + EasyOCR")
set_text(s, "TextBox 49", "Réglementation\n→ Docling seul")

# ─────────────────────────────────────────────────────────────────────
# SLIDE 9  — BASE DE DONNÉES (clone de S3 - VISION/MISSION)
# Shapes : TextBox 48/49/50/51/52/53
# ─────────────────────────────────────────────────────────────────────
s = all_slides[8]
set_text(s, "TextBox 48", "BASE DE")
set_text(s, "TextBox 49", "DONNÉES")
set_text(s, "TextBox 50", "POSTGRESQL + PGVECTOR")
set_text(s, "TextBox 51", "EXTENSIONS ACTIVÉES")
set_text(s, "TextBox 52",
    "4 tables : banques (référentiel), cb_tarifs, ef_indicateurs, regl_documents.\n"
    "33 857 lignes · 31 985 vecteurs 768 dimensions.\n"
    "Chaque fragment porte son vecteur calculé par Sentence-Transformers."
)
set_text(s, "TextBox 53",
    "pgvector : recherche par similarité cosinus (seuil 0,30).\n"
    "pg_trgm : rapprochement flou de libellés divergents.\n"
    "cache_app : calculs lourds pré-agrégés, survit aux redémarrages."
)

# ─────────────────────────────────────────────────────────────────────
# SLIDE 10  — SOCLE COMMUN ET DEUX MODES
# Shapes : TextBox 43/44 = grand titre ; 45/46 = noms ; 47/48 = descriptions
# ─────────────────────────────────────────────────────────────────────
s = all_slides[9]
set_text(s, "TextBox 43", "SOCLE")
set_text(s, "TextBox 44", "COMMUN")
set_text(s, "TextBox 45", "MODE 1 : TABLEAU DE BORD")
set_text(s, "TextBox 46", "MODE 2 : ASSISTANT RAG")
set_text(s, "TextBox 47",
    "L'écran cliqué dicte la question. Le système exécute "
    "sans demander au modèle de choisir. "
    "5 dashboards : santé financière, tarifs, stratégie, "
    "stratop, administration."
)
set_text(s, "TextBox 48",
    "Une zone de saisie reçoit toute question en langage naturel. "
    "Le routeur détermine QUEL outil activer — SQL, vecteur ou web. "
    "C'est ici que les deux architectures s'opposent."
)

# ─────────────────────────────────────────────────────────────────────
# SLIDE 11  — LES DEUX ARCHITECTURES
# Shapes : TextBox 25/26 = grand titre ; 27 = corps ; 35/36/37/38 = 4 contacts
# ─────────────────────────────────────────────────────────────────────
s = all_slides[10]
set_text(s, "TextBox 25", "DEUX")
set_text(s, "TextBox 26", "ARCHITECTURES")
set_text(s, "TextBox 27",
    "Même socle, même modèle rédacteur, même vérification finale. "
    "Une seule variable change : qui décide du chemin d'accès à l'information ?"
)
set_text(s, "TextBox 35", "A1 · MODULAIRE\nRouteur à règles\n1 appel LLM\nAuditable")
set_text(s, "TextBox 36", "A2 · AGENTIQUE\nLLM choisit ses outils\n2,36 appels moy.\nBoucle jusqu'à 6 tours")
set_text(s, "TextBox 37", "Chemin fixe → reproductible → 65 % identique")
set_text(s, "TextBox 38", "Chemin variable → 46 % identique → stochastique")

# ─────────────────────────────────────────────────────────────────────
# SLIDE 12  — ÉVALUATION (clone de S4 - WHY CHOOSE US)
# Shapes : TextBox 22/23 = grand titre ; 24 = corps ; 37/38/39/40 = 4 items
# ─────────────────────────────────────────────────────────────────────
s = all_slides[11]
set_text(s, "TextBox 22", "L'ÉVALUATION")
set_text(s, "TextBox 23", "COMPARATIVE")
set_text(s, "TextBox 24",
    "114 questions de référence construites par requêtes SQL certifiées. "
    "Même jeu, mêmes conditions pour A1 et A2. "
    "Tests statistiques : McNemar (p = 0,63) · Wilcoxon."
)
set_text(s, "TextBox 37", "Exactitude : 92,1 % (A1) vs 89,1 % (A2)")
set_text(s, "TextBox 38", "Latence : 2,87 s (A1) vs 4,51 s (A2)")
set_text(s, "TextBox 39", "Reproductibilité : 65 % (A1) vs 46 % (A2)")
set_text(s, "TextBox 40", "Stabilité des montants : 100 % (A1) vs 90 % (A2)")

# ─────────────────────────────────────────────────────────────────────
# SLIDE 13  — ARCHITECTURE RETENUE (clone de S3 - VISION/MISSION)
# Shapes : TextBox 48/49/50/51/52/53
# ─────────────────────────────────────────────────────────────────────
s = all_slides[12]
set_text(s, "TextBox 48", "ARCHITECTURE")
set_text(s, "TextBox 49", "RETENUE")
set_text(s, "TextBox 50", "MODULAIRE — POURQUOI ?")
set_text(s, "TextBox 51", "DÉCISION DÉFINITIVE")
set_text(s, "TextBox 52",
    "REPRODUCTIBILITÉ : 100 % des montants cités sont identiques d'un run à l'autre.\n"
    "COÛT : 1 seul appel API (vs 2,36). Latence divisée par deux.\n"
    "AUDITABILITÉ : chemin fixe, traçable jusqu'à la requête SQL source."
)
set_text(s, "TextBox 53",
    "« Le modèle garde un rôle essentiel, mais il intervient après\n"
    "la détermination du résultat. »\n"
    "Dans un contexte bancaire, un chiffre doit être justifiable — pas plausible."
)

# ─────────────────────────────────────────────────────────────────────
# SLIDE 14  — PROJECTION À 3 ANS (clone de S5 - SERVICES)
# Shapes : TextBox 53/54 = titre ; 55/56/57/58 = rubriques ; 59/60/61/62 = descriptions
# ─────────────────────────────────────────────────────────────────────
s = all_slides[13]
set_text(s, "TextBox 53", "PROJECTION")
set_text(s, "TextBox 54", "À 3 ANS")
set_text(s, "TextBox 55", "RÉFÉRENCE")
set_text(s, "TextBox 56", "ÉCART")
set_text(s, "TextBox 57", "SCÉNARIOS")
set_text(s, "TextBox 58", "TRAJECTOIRE")
set_text(s, "TextBox 59",
    "C = (B₁+B₂+B₃)/3\nMoyenne des 3 meilleures banques pour chaque ratio."
)
set_text(s, "TextBox 60",
    "E = max(0, C − V₀)\nSi SGCI dépasse la cible, aucun rattrapage imposé."
)
set_text(s, "TextBox 61",
    "wₛ = 0,60 · 1,00 · 1,20\nPrudent / Central / Offensif."
)
set_text(s, "TextBox 62",
    "Vₜ = V₀ + (Eₛ/3) × t\nDistribution linéaire sur 3 exercices."
)

# ─────────────────────────────────────────────────────────────────────
# SLIDE 15  — MERCI / DÉMO
# Shapes : TextBox 6/7 = THANK YOU ; 39/40/41/42 = infos bas
# ─────────────────────────────────────────────────────────────────────
s = all_slides[14]
set_text(s, "TextBox 6",  "MERCI")
set_text(s, "TextBox 7",  "!")
set_text(s, "TextBox 39", "ZONGO MESSOU Alphée Colombe")
set_text(s, "TextBox 40", "spybusiness.onrender.com")
set_text(s, "TextBox 41", "SOUTENANCE")
set_text(s, "TextBox 42", "2026")

# ─────────────────────────────────────────────────────────────────────
# SAUVEGARDE
# ─────────────────────────────────────────────────────────────────────
prs.save(OUT)
print(f"SLIDES : {len(list(prs.slides))}")
print(f"FICHIER : {OUT}")
