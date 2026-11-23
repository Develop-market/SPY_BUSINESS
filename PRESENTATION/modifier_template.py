"""
modifier_template.py
====================
Copie le template "Orange Black And White Modern Construction Company.pptx",
remplace TOUT le texte slide par slide avec le contenu SpyBusiness,
et change la couleur orange (FF6B35 / F07B00 etc.) en rouge SGCI (E4002B).

On NE TOUCHE PAS aux formes, images, fonds, dispositions : seul le texte change.
"""
import copy, os, shutil, re
from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Pt
from pptx.oxml.ns import qn

# ── chemins ───────────────────────────────────────────────────────────
TPL  = r'C:\Users\ALPHEE COLOMBE\Downloads\Orange Black And White Modern Construction Company.pptx'
OUT  = r'C:\Users\ALPHEE COLOMBE\Desktop\BACK\PRESENTATION\SpyBusiness_Soutenance.pptx'

shutil.copy2(TPL, OUT)          # on travaille sur la copie
prs  = Presentation(OUT)

# ── couleurs ──────────────────────────────────────────────────────────
ROUGE_SGCI = RGBColor(0xE4, 0x00, 0x2B)
# hexs orange du template à remplacer
ORANGE_HEX = {"FF6B35", "F07B00", "FF6600", "FF8C32", "F97316",
               "F59E0B", "EA580C", "D97706", "F97316", "FF7700",
               "E85D04", "FB923C", "FDBA74"}   # large filet

NOIR_SGCI  = RGBColor(0x1A, 0x1A, 0x2E)
BLANC      = RGBColor(0xFF, 0xFF, 0xFF)
GRIS       = RGBColor(0x4B, 0x5B, 0x6C)

# ── utilitaires texte ─────────────────────────────────────────────────
def set_run_text(run, txt):
    run.text = txt

def clear_para(para):
    """Vide tous les runs d'un paragraphe sauf le premier."""
    runs = para.runs
    for r in runs[1:]:
        r.text = ""
    if runs:
        runs[0].text = ""

def replace_slide_text(slide, mapping):
    """
    mapping = {shape_name: {"para_index": (ligne, ...)} }
    OU shape_name: "texte direct"
    """
    for sh in slide.shapes:
        if sh.name not in mapping:
            continue
        val = mapping[sh.name]
        if not hasattr(sh, 'text_frame'):
            continue
        tf = sh.text_frame
        if isinstance(val, str):
            # texte simple : on écrit dans le premier para, premier run
            _write_para(tf.paragraphs[0], val)
        elif isinstance(val, list):
            # liste de strings : une par paragraphe
            for i, txt in enumerate(val):
                if i < len(tf.paragraphs):
                    _write_para(tf.paragraphs[i], txt)
                else:
                    p = tf.add_paragraph()
                    if tf.paragraphs[0].runs:
                        # clone la police du premier
                        src = tf.paragraphs[0].runs[0]
                        r = p.add_run()
                        r.text = txt
                        r.font.size = src.font.size
                        r.font.bold = src.font.bold
                        r.font.name = src.font.name
                        r.font.color.rgb = src.font.color.rgb
                    else:
                        p.text = txt


def _write_para(para, txt):
    """Écrit txt dans le premier run du paragraphe, vide les autres."""
    runs = para.runs
    if not runs:
        r = para.add_run()
        r.text = txt
        return
    runs[0].text = txt
    for r in runs[1:]:
        r.text = ""


# ── recoloration globale orange → rouge SGCI ─────────────────────────
def recolor_shape_orange(sh):
    """Cherche dans le XML du shape tout srgbClr orange et le remplace."""
    xml = etree.tostring(sh.element, encoding="unicode")
    changed = False
    for ohex in ORANGE_HEX:
        if ohex.upper() in xml.upper():
            # remplacement insensible à la casse
            pattern = re.compile(re.escape(ohex), re.IGNORECASE)
            xml, n = pattern.subn("E4002B", xml)
            if n:
                changed = True
    if changed:
        new_el = etree.fromstring(xml)
        sh.element.getparent().replace(sh.element, new_el)


def recolor_slide(slide):
    for sh in slide.shapes:
        try:
            recolor_shape_orange(sh)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════
#  CONTENU PAR SLIDE
# ═══════════════════════════════════════════════════════════════════════
slides = list(prs.slides)

# ─────────────────────────────────────────────────────────────────────
# SLIDE 1  — PAGE DE GARDE
# Original: CONSTRUCTION / COMPANY / PRESENTATION / 2026 / Ingoude Company
# ─────────────────────────────────────────────────────────────────────
s = slides[0]
recolor_slide(s)
replace_slide_text(s, {
    "TextBox 31": "VEILLE",
    "TextBox 40": "STRATÉGIQUE",
    "TextBox 42": "PRESENTATION",
    "TextBox 43": "2025 - 2026",
    "TextBox 39": "Société Générale Côte d'Ivoire",
    "TextBox 41": "ZONGO MESSOU Alphée Colombe",
})

# ─────────────────────────────────────────────────────────────────────
# SLIDE 2  — WELCOME / INTRO → PLAN DE LA PRÉSENTATION
# Original: WELCOME TO / OUR COMPANY / lorem...
# ─────────────────────────────────────────────────────────────────────
s = slides[1]
recolor_slide(s)
replace_slide_text(s, {
    "TextBox 22": "PLAN DE",
    "TextBox 23": "PRÉSENTATION",
    "TextBox 24": (
        "1. Présentation de la SGCI\n"
        "2. Contexte et problématique\n"
        "3. Solution proposée : SpyBusiness\n"
        "4. Implémentation de la solution\n"
        "5. Évaluation et architecture retenue\n"
        "6. Démonstration et chiffres clés"
    ),
})

# ─────────────────────────────────────────────────────────────────────
# SLIDE 3  — VISION & MISSION → LA SGCI
# Original: VISION & / MISSION / OUR VISION / OUR MISSION / lorem...
# ─────────────────────────────────────────────────────────────────────
s = slides[2]
recolor_slide(s)
replace_slide_text(s, {
    "TextBox 48": "LA SGCI &",
    "TextBox 49": "SON CONTEXTE",
    "TextBox 50": "BANQUE DE PREMIER RANG",
    "TextBox 51": "DIRECTION INNOVATION",
    "TextBox 52": (
        "Filiale du groupe Société Générale, présente depuis 1962. "
        "1er rang en PNB : 276 Mds FCFA (2025). "
        "Résultat Net : 101 Mds FCFA — 27,8 % des profits du secteur."
    ),
    "TextBox 53": (
        "Créée en 2022. Structure d'accueil du stage. "
        "Mission : outiller les directions pour décider sur des données, "
        "pas sur des impressions. Cellule Data Science."
    ),
})

# ─────────────────────────────────────────────────────────────────────
# SLIDE 4  — WHY CHOOSE US → CONTEXTE / PROBLÈME
# Original: WHY SHOULD / YOU CHOOSE US? / Proven Experience / ...
# ─────────────────────────────────────────────────────────────────────
s = slides[3]
recolor_slide(s)
replace_slide_text(s, {
    "TextBox 22": "LA DONNÉE",
    "TextBox 23": "EXISTE. ELLE EST INEXPLOITABLE.",
    "TextBox 24": (
        "La SGCI dispose de données concurrentielles publiques "
        "— tarifs, bilans, réglementation — mais ne peut les traiter "
        "faute d'outils. 93 documents, 7 banques, des formats hétérogènes."
    ),
    "TextBox 37": "Grilles tarifaires",
    "TextBox 38": "États financiers",
    "TextBox 39": "Textes réglementaires",
    "TextBox 40": "Veille sectorielle",
})

# ─────────────────────────────────────────────────────────────────────
# SLIDE 5  — (slide 5 du template) → ÉVOLUTION DU RAG
# ─────────────────────────────────────────────────────────────────────
s = slides[4]
recolor_slide(s)
# Récupérons les shapes disponibles
for sh in s.shapes:
    if hasattr(sh, 'text_frame'):
        try:
            t = sh.text_frame.text.strip()
            if t:
                print(f"  S5 {sh.name}: '{t[:50]}'")
        except:
            pass

# ─────────────────────────────────────────────────────────────────────
# SLIDE 6  → PROBLÉMATIQUE
# ─────────────────────────────────────────────────────────────────────
s = slides[5]
recolor_slide(s)
for sh in s.shapes:
    if hasattr(sh, 'text_frame'):
        try:
            t = sh.text_frame.text.strip()
            if t:
                print(f"  S6 {sh.name}: '{t[:50]}'")
        except:
            pass

# ─────────────────────────────────────────────────────────────────────
# SLIDE 7  → SOLUTION SpyBusiness
# ─────────────────────────────────────────────────────────────────────
s = slides[6]
recolor_slide(s)
for sh in s.shapes:
    if hasattr(sh, 'text_frame'):
        try:
            t = sh.text_frame.text.strip()
            if t:
                print(f"  S7 {sh.name}: '{t[:50]}'")
        except:
            pass

# ─────────────────────────────────────────────────────────────────────
# SLIDE 8  → EXTRACTION DES DONNÉES
# ─────────────────────────────────────────────────────────────────────
s = slides[7]
recolor_slide(s)
for sh in s.shapes:
    if hasattr(sh, 'text_frame'):
        try:
            t = sh.text_frame.text.strip()
            if t:
                print(f"  S8 {sh.name}: '{t[:50]}'")
        except:
            pass

# ─────────────────────────────────────────────────────────────────────
# slides 9–12 : on recolore et on listera les shapes disponibles
# ─────────────────────────────────────────────────────────────────────
for i in range(8, len(slides)):
    recolor_slide(slides[i])

# sauvegarde
prs.save(OUT)
print(f"\nFICHIER SAUVEGARDE : {OUT}")
