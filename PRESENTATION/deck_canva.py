# -*- coding: utf-8 -*-
"""
deck_canva.py — Diaporama de soutenance SpyBusiness — Style Canva Pro
=====================================================================
ZONGO MESSOU Alphée Colombe — Master Data Science, Big Data et IA
Stage à la Société Générale Côte d'Ivoire, Direction Innovation.

Design inspiré des templates Canva « Orange Black White Modern Financial
Report » — géométrie audacieuse, blocs massifs, typographie Archivo/Poppins.

    python PRESENTATION/deck_canva.py  ->  PRESENTATION/soutenance_canva.pptx
"""
import os, sys, tempfile
from PIL import Image as _PILImage
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt
from pptx.dml.color import RGBColor
from pptx.oxml.ns import nsdecls, qn
from lxml import etree

# ═══════════════════════════════════════════════════════════════════════
#  CHARTE VISUELLE — ROUGE SGCI + NOIR PROFOND + ACCENTS MAGNIFIQUES
# ═══════════════════════════════════════════════════════════════════════
ROUGE       = RGBColor(0xE4, 0x00, 0x2B)   # Rouge SGCI — couleur directrice
ROUGE_VIF   = RGBColor(0xFF, 0x2D, 0x55)   # Accent vif
BORDEAUX    = RGBColor(0x7A, 0x00, 0x1E)   # Profondeur
CORAIL      = RGBColor(0xFF, 0x6B, 0x6B)   # Accent chaud doux

NOIR        = RGBColor(0x1A, 0x1A, 0x2E)   # Noir profond bleuté
NOIR_PUR    = RGBColor(0x10, 0x10, 0x14)
ANTHRACITE  = RGBColor(0x2C, 0x2C, 0x36)
ARDOISE     = RGBColor(0x16, 0x21, 0x3E)   # Bleu nuit profond

GRIS        = RGBColor(0x6B, 0x6B, 0x7B)
GRIS_CLAIR  = RGBColor(0xE8, 0xE8, 0xEE)
GRIS_FOND   = RGBColor(0xF5, 0xF5, 0xFA)

BLANC       = RGBColor(0xFF, 0xFF, 0xFF)
CREME       = RGBColor(0xFF, 0xF5, 0xF6)

OR          = RGBColor(0xF2, 0xC9, 0x4C)   # Accent doré chaud
ORANGE      = RGBColor(0xFF, 0x8C, 0x32)   # Accent énergie
EMERAUDE    = RGBColor(0x27, 0xAE, 0x60)   # Accent validation/succès
BLEU        = RGBColor(0x33, 0x4E, 0x6B)   # Ardoise doux
ROSE        = RGBColor(0xFF, 0xA9, 0xB8)   # Texte secondaire sur fond sombre

# Polices — Calibri est sur toutes les machines Windows
TITRE = "Calibri Light"
TEXTE = "Calibri"
MONO  = "Consolas"

# Format 16:9
L, H = Inches(13.333), Inches(7.5)
TOTAL = 15

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DOC = os.path.join(RACINE, "DOCUMENTATION", "img")
IMG_DESK = r"C:\Users\ALPHEE COLOMBE\Desktop\images"
IMG_NEW = r"C:\Users\ALPHEE COLOMBE\Desktop\Nouveau dossier"


def img_doc(nom):
    c = os.path.join(IMG_DOC, nom)
    return c if os.path.exists(c) else None

def img_desk(nom):
    c = os.path.join(IMG_DESK, nom)
    return c if os.path.exists(c) else None

def img_new(nom):
    c = os.path.join(IMG_NEW, nom)
    return c if os.path.exists(c) else None


# ═══════════════════════════════════════════════════════════════════════
#  PRIMITIVES DE MISE EN PAGE
# ═══════════════════════════════════════════════════════════════════════
def zone(slide, x, y, w, h, *, align=PP_ALIGN.LEFT, ancre=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(int(x), int(y), int(w), int(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = ancre
    tf.paragraphs[0].alignment = align
    return tb, tf


def para(tf, texte, *, taille=14, gras=False, couleur=NOIR, police=TEXTE,
         align=PP_ALIGN.LEFT, interligne=1.18, avant=0, premier=False,
         italique=False, espacement=None):
    p = tf.paragraphs[0] if premier else tf.add_paragraph()
    p.alignment = align
    p.line_spacing = interligne
    if avant:
        p.space_before = Pt(avant)
    r = p.add_run()
    r.text = texte
    f = r.font
    f.size, f.bold, f.italic, f.name = Pt(taille), gras, italique, police
    f.color.rgb = couleur
    if espacement is not None:
        r.font._rPr.set("spc", str(int(espacement * 100)))
    return p


def riche(tf, morceaux, *, taille=14, couleur=NOIR, police=TEXTE,
          align=PP_ALIGN.LEFT, interligne=1.18, avant=0, premier=False):
    p = tf.paragraphs[0] if premier else tf.add_paragraph()
    p.alignment = align
    p.line_spacing = interligne
    if avant:
        p.space_before = Pt(avant)
    for m in morceaux:
        t = m[0]
        gras = m[1] if len(m) > 1 else False
        col = m[2] if len(m) > 2 else couleur
        pol = m[3] if len(m) > 3 else police
        r = p.add_run()
        r.text = t
        r.font.size, r.font.bold, r.font.name = Pt(taille), gras, pol
        r.font.color.rgb = col
    return p


def rect(slide, x, y, w, h, couleur, *, forme=MSO_SHAPE.RECTANGLE,
         bord=None, ep=1.0, transparence=None, arrondi=False):
    f = MSO_SHAPE.ROUNDED_RECTANGLE if arrondi else forme
    s = slide.shapes.add_shape(f, int(x), int(y), int(w), int(h))
    s.shadow.inherit = False
    if couleur is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = couleur
        if transparence:
            _alpha(s.fill.fore_color, transparence)
    if bord is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = bord
        s.line.width = Pt(ep)
    s.text_frame.word_wrap = True
    return s


def _alpha(couleur, pct):
    el = couleur._xFill.find(qn("a:srgbClr"))
    if el is not None:
        a = etree.SubElement(el, qn("a:alpha"))
        a.set("val", str(int((1 - pct) * 100000)))


def degrade(slide, x, y, w, h, c1, c2, *, angle=45):
    s = rect(slide, x, y, w, h, RGBColor.from_string(c1))
    sp = s.fill._xPr
    xml = (f'<a:gradFill {nsdecls("a")} rotWithShape="1">'
           f'<a:gsLst>'
           f'<a:gs pos="0"><a:srgbClr val="{c1}"/></a:gs>'
           f'<a:gs pos="100000"><a:srgbClr val="{c2}"/></a:gs>'
           f'</a:gsLst><a:lin ang="{int(angle * 60000)}" scaled="0"/></a:gradFill>')
    grad = etree.fromstring(xml)
    ancien = sp.find(qn("a:solidFill"))
    if ancien is not None:
        sp.replace(ancien, grad)
    else:
        geom = sp.find(qn("a:prstGeom"))
        sp.insert(list(sp).index(geom) + 1 if geom is not None else 0, grad)
    return s


def ligne(slide, x1, y1, x2, y2, couleur=GRIS_CLAIR, ep=1.0, *, pointille=False):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                   int(x1), int(y1), int(x2), int(y2))
    c.line.color.rgb = couleur
    c.line.width = Pt(ep)
    if pointille:
        c.line._get_or_add_ln().append(
            etree.fromstring(f'<a:prstDash {nsdecls("a")} val="dash"/>'))
    return c


_WEBP_TMP = []  # garde les fichiers temporaires en vie le temps de la session

def _to_supported(chemin):
    """Convertit WEBP en PNG via Pillow si nécessaire."""
    if chemin is None or not os.path.exists(chemin):
        return None
    ext = os.path.splitext(chemin)[1].lower()
    if ext in (".webp",):
        try:
            img = _PILImage.open(chemin).convert("RGBA")
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            img.save(tmp.name, "PNG")
            tmp.close()
            _WEBP_TMP.append(tmp.name)
            return tmp.name
        except Exception:
            return None
    return chemin


def picture(slide, chemin, x, y, *, w=None, h=None, bord=False):
    chemin = _to_supported(chemin)
    if chemin is None:
        return None
    try:
        kwargs = {}
        if w: kwargs["width"] = int(w)
        if h: kwargs["height"] = int(h)
        p = slide.shapes.add_picture(chemin, int(x), int(y), **kwargs)
        if bord:
            rect(slide, p.left, p.top, p.width, p.height, None,
                 bord=GRIS_CLAIR, ep=0.75)
        return p
    except Exception as e:
        print(f"  [image ignorée] {chemin}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════
#  GABARITS CANVA-STYLE
# ═══════════════════════════════════════════════════════════════════════
def fond_blanc(slide):
    rect(slide, 0, 0, L, H, BLANC)

def fond_gris(slide):
    rect(slide, 0, 0, L, H, GRIS_FOND)

def motif_points(slide, x0, y0, nx, ny, couleur=BLANC, transp=0.72, esp=0.22):
    """Trame de points géométriques à la Canva."""
    for i in range(nx):
        for j in range(ny):
            if (i + j) % 2:
                rect(slide, Inches(x0 + i * esp), Inches(y0 + j * esp),
                     Inches(0.065), Inches(0.065), couleur, transparence=transp)


def bande_laterale(slide, couleur=ROUGE, largeur=0.45):
    """Bande verticale gauche signature — style Canva Financial Report."""
    rect(slide, 0, 0, Inches(largeur), H, couleur)


def bandeau_titre(slide, numero, titre, *, sous_titre=None, n_page=None):
    """Bandeau haut avec pastille numérotée — style géométrique."""
    # Bande fine rouge en haut
    rect(slide, 0, 0, L, Inches(0.06), ROUGE)
    # Pastille numérotée
    p = rect(slide, Inches(0.70), Inches(0.38), Inches(0.62), Inches(0.62),
             ROUGE, forme=MSO_SHAPE.OVAL)
    tf = p.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tf, str(numero), taille=18, gras=True, couleur=BLANC,
         align=PP_ALIGN.CENTER, premier=True)
    # Titre
    _, t = zone(slide, Inches(1.55), Inches(0.32), Inches(10.8), Inches(0.55))
    para(t, titre, taille=26, gras=True, couleur=NOIR, police=TITRE, premier=True)
    y = Inches(0.92)
    if sous_titre:
        _, s = zone(slide, Inches(1.55), y, Inches(10.8), Inches(0.32))
        para(s, sous_titre, taille=12.5, couleur=GRIS, italique=True, premier=True)
        y = Inches(1.30)
    # Numéro de page
    if n_page:
        pied(slide, n_page)
    return y


def pied(slide, n, *, sombre=False):
    couleur_n = BLANC if sombre else ROUGE
    couleur_t = ROSE if sombre else GRIS
    _, tf = zone(slide, Inches(11.8), Inches(6.96), Inches(1.3), Inches(0.32),
                 align=PP_ALIGN.RIGHT)
    riche(tf, [(f"{n}", True, couleur_n), (f" / {TOTAL}", False, couleur_t)],
          taille=10.5, premier=True, align=PP_ALIGN.RIGHT)


def carte_canva(slide, x, y, w, h, titre_txt, lignes, *, accent=ROUGE,
                fond_c=BLANC, taille_titre=16, taille_texte=12, arrondi=True):
    """Carte avec barre d'accent en haut — style Canva."""
    c = rect(slide, x, y, w, h, fond_c, arrondi=arrondi, bord=GRIS_CLAIR, ep=0.75)
    rect(slide, x + Inches(0.15), y, w - Inches(0.30), Inches(0.055), accent)
    tf = c.text_frame
    tf.margin_left = tf.margin_right = Inches(0.28)
    tf.margin_top = Inches(0.30)
    tf.margin_bottom = Inches(0.18)
    tf.vertical_anchor = MSO_ANCHOR.TOP
    para(tf, titre_txt, taille=taille_titre, gras=True, couleur=NOIR,
         police=TITRE, premier=True)
    for l in lignes:
        para(tf, l, taille=taille_texte, couleur=GRIS, avant=6, interligne=1.24)
    return c


def bloc_kpi(slide, x, y, w, valeur, libelle, *, couleur=ROUGE, fond_c=BLANC,
             taille_val=38, transp=None):
    """Bloc KPI visuel — gros chiffre + label dessous."""
    b = rect(slide, x, y, w, Inches(1.45), fond_c, arrondi=True,
             bord=GRIS_CLAIR if fond_c == BLANC else None, ep=0.75,
             transparence=transp)
    rect(slide, x + Inches(0.12), y, w - Inches(0.24), Inches(0.05), couleur)
    _, tf = zone(slide, x + Inches(0.22), y + Inches(0.26), w - Inches(0.44),
                 Inches(1.1))
    para(tf, valeur, taille=taille_val, gras=True, couleur=couleur, police=TITRE,
         premier=True, interligne=0.95)
    para(tf, libelle, taille=10.5, couleur=GRIS, avant=5, interligne=1.18)
    return b


def etape_canva(slide, x, y, w, h, n, titre_txt, texte, *, accent=ROUGE):
    """Étape numérotée avec pastille — style process flow."""
    c = rect(slide, x, y, w, h, BLANC, arrondi=True, bord=GRIS_CLAIR, ep=0.75)
    rect(slide, x, y, Inches(0.055), h, accent)
    d = Inches(0.48)
    p = rect(slide, x + Inches(0.22), y + (h - d) / 2, d, d, accent,
             forme=MSO_SHAPE.OVAL)
    tf = p.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tf, str(n), taille=14, gras=True, couleur=BLANC,
         align=PP_ALIGN.CENTER, premier=True)
    _, t = zone(slide, x + Inches(0.88), y + Inches(0.10),
                w - Inches(1.10), h - Inches(0.20), ancre=MSO_ANCHOR.MIDDLE)
    para(t, titre_txt, taille=13, gras=True, couleur=NOIR, police=TITRE,
         premier=True)
    if texte:
        para(t, texte, taille=10.5, couleur=GRIS, avant=3, interligne=1.20)
    return c


# ═══════════════════════════════════════════════════════════════════════
#  ANIMATIONS
# ═══════════════════════════════════════════════════════════════════════
_P14 = 'xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main"'

_EFFETS = {
    "fondu":    (10, "0",  "fade"),
    "balayage": (22, "4",  "wipe(up)"),
    "bandeau":  (22, "8",  "wipe(left)"),
    "store":    (3,  "10", "blinds(horizontal)"),
    "damier":   (5,  "10", "checkerboard(across)"),
    "dissoudre":(9,  "0",  "dissolve"),
}

_TIMING = """<p:timing {ns}>
<p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>
<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>
{groupes}
</p:childTnLst></p:cTn>
<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>
<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>
</p:seq></p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>"""

_GROUPE = """<p:par><p:cTn id="{a}" fill="hold"><p:stCondLst><p:cond delay="indefinite"/></p:stCondLst>
<p:childTnLst><p:par><p:cTn id="{b}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst>
<p:childTnLst>{effets}</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>"""

_EFFET = """<p:par><p:cTn id="{c}" presetID="{preset}" presetClass="entr" presetSubtype="{sub}"
 fill="hold" grpId="0" nodeType="{node}"><p:stCondLst><p:cond delay="{delai}"/></p:stCondLst>
<p:childTnLst>
<p:set><p:cBhvr><p:cTn id="{d}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>
<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>
<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>
<p:to><p:strVal val="visible"/></p:to></p:set>
<p:animEffect transition="in" filter="{filtre}"><p:cBhvr>
<p:cTn id="{e}" dur="{duree}"/><p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>
</p:childTnLst></p:cTn></p:par>"""


def transition(slide, type_="fade", duree_ms=700, **attrs):
    sup = "".join(f' {k}="{v}"' for k, v in attrs.items())
    xml = (f'<p:transition {nsdecls("p")} {_P14} spd="med" p14:dur="{duree_ms}">'
           f'<p:{type_}{sup}/></p:transition>')
    anc = slide.element.find(qn("p:transition"))
    if anc is not None:
        slide.element.remove(anc)
    slide.element.append(etree.fromstring(xml))


def animer(slide, sequences):
    groupes, i = [], 3
    for entree in sequences:
        formes = entree[0]
        nom = entree[1] if len(entree) > 1 else "fondu"
        decalage = entree[2] if len(entree) > 2 else 150
        duree = entree[3] if len(entree) > 3 else 500
        formes = [f for f in formes if f is not None]
        if not formes:
            continue
        preset, sub, filtre = _EFFETS.get(nom, _EFFETS["fondu"])
        a, b = i, i + 1
        i += 2
        effets = []
        for rang, f in enumerate(formes):
            effets.append(_EFFET.format(
                c=i, d=i + 1, e=i + 2,
                node="clickEffect" if rang == 0 else "afterEffect",
                delai=0 if rang == 0 else decalage,
                preset=preset, sub=sub, filtre=filtre, duree=duree,
                spid=f.shape_id))
            i += 3
        groupes.append(_GROUPE.format(a=a, b=b, effets="".join(effets)))
    if not groupes:
        return
    anc = slide.element.find(qn("p:timing"))
    if anc is not None:
        slide.element.remove(anc)
    slide.element.append(etree.fromstring(_TIMING.format(
        ns=nsdecls("p"), groupes="".join(groupes))))


# ═══════════════════════════════════════════════════════════════════════
#  CONSTRUCTION DU DIAPORAMA
# ═══════════════════════════════════════════════════════════════════════
prs = Presentation()
prs.slide_width, prs.slide_height = L, H
VIDE = prs.slide_layouts[6]

def page():
    return prs.slides.add_slide(VIDE)


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 1 — PAGE DE GARDE
# ══════════════════════════════════════════════════════════════════════
s = page()
# Fond noir profond avec dégradé
degrade(s, 0, 0, L, H, "1A1A2E", "E4002B", angle=140)

# Géométrie décorative — grands cercles translucides (style Canva)
rect(s, Inches(9.5), Inches(-1.5), Inches(5.0), Inches(5.0), BLANC,
     forme=MSO_SHAPE.OVAL, transparence=0.92)
rect(s, Inches(10.5), Inches(-0.5), Inches(3.5), Inches(3.5), BLANC,
     forme=MSO_SHAPE.OVAL, transparence=0.88)
rect(s, Inches(-2.0), Inches(5.0), Inches(4.0), Inches(4.0), ROUGE_VIF,
     forme=MSO_SHAPE.OVAL, transparence=0.85)

# Motif de points
motif_points(s, 10.8, 4.2, 8, 8, BLANC, 0.82, 0.22)

# Barre institutionnelle en haut
_, tf = zone(s, Inches(0.80), Inches(0.55), Inches(11.7), Inches(0.5),
             align=PP_ALIGN.LEFT)
para(tf, "RÉPUBLIQUE DE CÔTE D'IVOIRE   ·   UNION – DISCIPLINE – TRAVAIL",
     taille=10, couleur=ROSE, premier=True, espacement=1.6)
para(tf, "INTERNATIONAL DATASCIENCE INSTITUTE", taille=12, gras=True,
     couleur=BLANC, avant=5, espacement=1.2)

# Bloc THÈME
barre_theme = rect(s, Inches(0.80), Inches(1.85), Inches(1.90), Inches(1.80),
                   BLANC, arrondi=True)
tfb = barre_theme.text_frame
tfb.margin_left = tfb.margin_right = 0
tfb.vertical_anchor = MSO_ANCHOR.MIDDLE
para(tfb, "THÈME", taille=30, gras=True, couleur=NOIR, police=TITRE,
     align=PP_ALIGN.CENTER, premier=True)

bloc_titre = rect(s, Inches(2.70), Inches(1.85), Inches(8.80), Inches(1.80),
                  ROUGE, arrondi=True)
tft = bloc_titre.text_frame
tft.margin_left = Inches(0.45)
tft.margin_right = Inches(0.45)
tft.vertical_anchor = MSO_ANCHOR.MIDDLE
para(tft, "VEILLE STRATÉGIQUE ET AIDE\nÀ LA DÉCISION PAR UNE APPROCHE RAG",
     taille=22, gras=True, couleur=BLANC, police=TITRE,
     align=PP_ALIGN.LEFT, premier=True, interligne=1.22)

# Ligne de séparation
ligne(s, Inches(0.80), Inches(4.10), Inches(11.5), Inches(4.10), ROSE, 1.0)

# Présenté par
_, tf = zone(s, Inches(0.80), Inches(4.40), Inches(11.5), Inches(0.7))
riche(tf, [("Présenté par  ", False, ROSE),
           ("ZONGO MESSOU Alphée Colombe", True, BLANC)],
      taille=16, premier=True)
para(tf, "Direction de l'Innovation — Société Générale Côte d'Ivoire",
     taille=12, couleur=ROSE, avant=5)

# Encadrants
_, g = zone(s, Inches(0.80), Inches(5.50), Inches(5.0), Inches(1.0))
para(g, "ENCADREUR PÉDAGOGIQUE", taille=9, gras=True, couleur=ROSE,
     premier=True, espacement=1.2)
para(g, "M. MONSIA DOUGBAN", taille=14, gras=True, couleur=BLANC, avant=4)

_, d = zone(s, Inches(7.30), Inches(5.50), Inches(4.5), Inches(1.0),
            align=PP_ALIGN.RIGHT)
para(d, "MAÎTRE DE STAGE", taille=9, gras=True, couleur=ROSE,
     align=PP_ALIGN.RIGHT, premier=True, espacement=1.2)
para(d, "M. MOUAHA HANDY", taille=14, gras=True, couleur=BLANC,
     align=PP_ALIGN.RIGHT, avant=4)

# Année académique
_, tf = zone(s, Inches(0.80), Inches(6.80), Inches(11.5), Inches(0.4),
             align=PP_ALIGN.CENTER)
para(tf, "Année académique 2025 – 2026", taille=11, couleur=ROSE,
     align=PP_ALIGN.CENTER, premier=True)

# Logos
logo_sgci = img_desk("SGCI.png")
logo_ensea = img_desk("ENSEA.webp")
if logo_sgci:
    picture(s, logo_sgci, Inches(11.0), Inches(6.40), h=Inches(0.60))
if logo_ensea:
    picture(s, logo_ensea, Inches(0.80), Inches(6.40), h=Inches(0.55))

transition(s, "fade", 900)
animer(s, [([barre_theme, bloc_titre], "bandeau", 0, 700)])


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 2 — SOMMAIRE
# ══════════════════════════════════════════════════════════════════════
s = page()
fond_gris(s)
# Grande bande rouge à gauche
bande_laterale(s, ROUGE, 0.50)

_, tf = zone(s, Inches(0.85), Inches(0.55), Inches(6.0), Inches(1.2))
para(tf, "SOMMAIRE", taille=48, gras=True, couleur=BLANC, police=TITRE,
     premier=True)
ligne(s, Inches(0.85), Inches(1.55), Inches(2.50), Inches(1.55), BLANC, 4.0)

PLAN = [("Présentation de l'entreprise d'accueil", "3"),
        ("Contexte et problématique", "4 – 6"),
        ("Solution proposée", "7"),
        ("Implémentation de la solution", "8 – 11"),
        ("Évaluation et architecture retenue", "12 – 14"),
        ("Démonstration et chiffres clés", "15")]

barres = []
for i, (t, p) in enumerate(PLAN):
    y = Inches(2.00 + i * 0.82)
    # Barre principale
    b = rect(s, Inches(1.20), y, Inches(11.0), Inches(0.64), BLANC, arrondi=True)
    # Numéro
    n = rect(s, Inches(0.70), y + Inches(0.06), Inches(0.52), Inches(0.52),
             NOIR, forme=MSO_SHAPE.OVAL)
    tfn = n.text_frame
    tfn.margin_left = tfn.margin_right = 0
    tfn.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tfn, str(i + 1), taille=16, gras=True, couleur=BLANC,
         align=PP_ALIGN.CENTER, premier=True)
    # Texte
    _, z = zone(s, Inches(1.55), y + Inches(0.15), Inches(8.2), Inches(0.40))
    para(z, t, taille=16, gras=True, couleur=NOIR, police=TITRE, premier=True)
    # Pages
    pg = rect(s, Inches(10.30), y + Inches(0.06), Inches(1.80), Inches(0.52),
              ROUGE, arrondi=True)
    _, z2 = zone(s, Inches(10.30), y + Inches(0.16), Inches(1.80), Inches(0.40),
                 align=PP_ALIGN.CENTER)
    para(z2, p, taille=13, gras=True, couleur=BLANC,
         align=PP_ALIGN.CENTER, premier=True)
    barres.extend([b, n])

pied(s, 2)
transition(s, "push", 700, dir="u")
animer(s, [(barres, "bandeau", 110, 380)])


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 3 — PRÉSENTATION DE L'ENTREPRISE
# ══════════════════════════════════════════════════════════════════════
s = page()
fond_blanc(s)
# Bande latérale fine
rect(s, 0, 0, Inches(0.08), H, ROUGE)
bandeau_titre(s, 1, "La Société Générale Côte d'Ivoire",
              sous_titre="Leader du marché bancaire ivoirien — Direction Innovation",
              n_page=3)

# 3 cartes en colonnes
c1 = carte_canva(s, Inches(0.70), Inches(1.50), Inches(3.80), Inches(2.40),
    "Banque de premier rang",
    ["Filiale du groupe Société Générale, présente en Côte d'Ivoire depuis 1962.",
     "Banque universelle : particuliers, professionnels, grandes entreprises."],
    accent=ROUGE)

c2 = carte_canva(s, Inches(4.70), Inches(1.50), Inches(3.80), Inches(2.40),
    "Direction de l'Innovation",
    ["Structure d'accueil du stage, créée en 2022.",
     "Mission : outiller les métiers pour décider sur des faits."],
    accent=OR)

c3 = carte_canva(s, Inches(8.70), Inches(1.50), Inches(3.80), Inches(2.40),
    "Un marché disputé",
    ["Sept banques se partagent le marché ivoirien.",
     "Chacune publie ses tarifs et ses comptes : l'information est publique."],
    accent=ARDOISE)

# KPIs
kpi1 = bloc_kpi(s, Inches(0.70), Inches(4.15), Inches(2.75),
                "276 Mds", "de PNB (2025)\nN°1 du marché", couleur=ROUGE)
kpi2 = bloc_kpi(s, Inches(3.65), Inches(4.15), Inches(2.75),
                "101 Mds", "de Résultat Net\nN°1 en profitabilité", couleur=OR)
kpi3 = bloc_kpi(s, Inches(6.60), Inches(4.15), Inches(2.75),
                "27,8 %", "des bénéfices\ndu secteur", couleur=EMERAUDE)
kpi4 = bloc_kpi(s, Inches(9.55), Inches(4.15), Inches(2.75),
                "67/100", "score compétitif\nglobal", couleur=ROUGE_VIF)

# Fil conducteur
fil = rect(s, Inches(0.70), Inches(5.85), Inches(11.60), Inches(1.30),
           NOIR, arrondi=True)
rect(s, Inches(0.70), Inches(5.85), Inches(0.08), Inches(1.30), ROUGE)
_, tf = zone(s, Inches(1.10), Inches(6.02), Inches(10.8), Inches(1.0))
para(tf, "LE FIL CONDUCTEUR", taille=10, gras=True, couleur=ROUGE_VIF,
     premier=True, espacement=1.5)
riche(tf, [("La SGCI veut savoir ", False, BLANC),
           ("où elle se situe face à ses six concurrents", True, BLANC),
           (" — tarifs, finances, conformité. Les documents existent, "
            "mais personne ne les exploite. ", False, GRIS_CLAIR),
           ("C'est ce constat qui ouvre le sujet.", True, ROUGE_VIF)],
      taille=13.5, avant=7, interligne=1.30)

transition(s, "wipe", 650, dir="l")
animer(s, [([c1, c2, c3], "balayage", 150, 450),
           ([kpi1, kpi2, kpi3, kpi4], "fondu", 120, 350),
           ([fil], "fondu", 0, 550)])


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 4 — CONTEXTE : LA DONNÉE EXISTE, ELLE EST INEXPLOITABLE
# ══════════════════════════════════════════════════════════════════════
s = page()
fond_blanc(s)
rect(s, 0, 0, Inches(0.08), H, ROUGE)
bandeau_titre(s, 2, "La donnée existe. Elle est inexploitable.",
              sous_titre="Trois matières publiques, trois obstacles différents",
              n_page=4)

blocs = []
DATA = [("Grilles tarifaires", "semestrielles · 70 documents",
         "PDF de dizaines de pages, souvent scannés. Un même service change "
         "de nom d'une banque à l'autre.", ROUGE),
        ("États financiers", "annuels · 18 documents",
         "Des bilans sur deux colonnes, exercice N et N−1. Certains sont "
         "encodés en tracés — pas de texte extractible.", OR),
        ("Textes réglementaires", "BCEAO / UEMOA",
         "Prose juridique dense, où le mot exact fait le sens : usure, "
         "gratuité, agrément.", ARDOISE)]
for i, (t, st, d, col) in enumerate(DATA):
    x = Inches(0.70 + i * 4.05)
    b = rect(s, x, Inches(1.50), Inches(3.75), Inches(2.65), BLANC,
             arrondi=True, bord=GRIS_CLAIR, ep=0.75)
    rect(s, x + Inches(0.12), Inches(1.50), Inches(3.51), Inches(0.055), col)
    # Icône
    p = rect(s, x + Inches(0.28), Inches(1.78), Inches(0.62), Inches(0.62),
             col, forme=MSO_SHAPE.OVAL)
    tfp = p.text_frame
    tfp.margin_left = tfp.margin_right = tfp.margin_top = tfp.margin_bottom = 0
    tfp.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tfp, "PDF", taille=11, gras=True, couleur=BLANC,
         align=PP_ALIGN.CENTER, premier=True)
    _, z = zone(s, x + Inches(0.28), Inches(2.60), Inches(3.15), Inches(1.5))
    para(z, t, taille=17, gras=True, couleur=NOIR, police=TITRE, premier=True)
    para(z, st, taille=11, couleur=col, gras=True, avant=2)
    para(z, d, taille=11.5, couleur=GRIS, avant=7, interligne=1.24)
    blocs.append(b)

# Bloc bas
mur = rect(s, Inches(0.70), Inches(4.50), Inches(11.60), Inches(2.20),
           NOIR, arrondi=True)
_, tf = zone(s, Inches(1.15), Inches(4.78), Inches(7.0), Inches(1.5))
para(tf, "CE QUE COÛTE CETTE SITUATION", taille=10, gras=True,
     couleur=ROUGE_VIF, premier=True, espacement=1.5)
para(tf, "Comparer sept banques sur une seule question demandait\n"
         "de rouvrir chaque document, à la main.",
     taille=14, couleur=BLANC, avant=8, interligne=1.35)
riche(tf, [("Une analyse externe : ", False, GRIS_CLAIR),
           ("> 30 millions FCFA", True, ROUGE_VIF),
           (" par mission.", False, GRIS_CLAIR)],
      taille=14, avant=8, interligne=1.30)

# KPIs droite
bloc_kpi(s, Inches(8.60), Inches(4.75), Inches(1.65), "93", "documents\nà traiter",
         couleur=BLANC, fond_c=ANTHRACITE, taille_val=36)
bloc_kpi(s, Inches(10.45), Inches(4.75), Inches(1.65), "7", "banques\nà comparer",
         couleur=ROUGE_VIF, fond_c=ANTHRACITE, taille_val=36)

transition(s, "push", 700, dir="l")
animer(s, [(blocs, "balayage", 160, 450), ([mur], "fondu", 0, 600)])


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 5 — LE RAG ET SON ÉVOLUTION
# ══════════════════════════════════════════════════════════════════════
s = page()
fond_blanc(s)
rect(s, 0, 0, Inches(0.08), H, ROUGE)
bandeau_titre(s, 3, "La génération augmentée par récupération (RAG)",
              sous_titre="Quatre générations pour devenir gouvernable",
              n_page=5)

_, tf = zone(s, Inches(0.70), Inches(1.38), Inches(11.8), Inches(0.5))
riche(tf, [("Un modèle seul ", False, NOIR),
           ("n'a aucune source", True, ROUGE),
           (" : il produit la suite de mots la plus plausible. Le RAG lui "
            "impose de répondre à partir de documents.", False, NOIR)],
      taille=13.5, premier=True)

# Timeline
ligne(s, Inches(1.10), Inches(2.90), Inches(12.2), Inches(2.90),
      GRIS_CLAIR, 2.5)

GEN = [("RAG Naïf", "2020", "On cherche, on donne,\non rédige.",
        "Aucun contrôle.", GRIS),
       ("RAG Avancé", "2022", "On soigne la recherche\navant de rédiger.",
        "Meilleur mais une seule passe.", ARDOISE),
       ("RAG Modulaire", "2023", "Routeur à règles,\noutils spécialisés.",
        "Reproductible et auditable.", ROUGE),
       ("RAG Agentique", "2024", "Le modèle choisit\nses outils et boucle.",
        "Souple mais stochastique.", OR)]

etapes_list = []
for i, (t, annee, st, d, col) in enumerate(GEN):
    x = Inches(0.70 + i * 3.05)
    # Point sur la timeline
    pt = rect(s, x + Inches(1.25), Inches(2.74), Inches(0.32), Inches(0.32),
              col, forme=MSO_SHAPE.OVAL)
    # Année
    _, y_lbl = zone(s, x, Inches(2.28), Inches(2.75), Inches(0.4),
                    align=PP_ALIGN.CENTER)
    para(y_lbl, annee, taille=12, gras=True, couleur=col,
         align=PP_ALIGN.CENTER, premier=True)
    # Carte
    b = rect(s, x, Inches(3.28), Inches(2.75), Inches(2.30), BLANC,
             arrondi=True, bord=GRIS_CLAIR, ep=0.75)
    rect(s, x + Inches(0.08), Inches(3.28), Inches(2.59), Inches(0.05), col)
    _, z = zone(s, x + Inches(0.22), Inches(3.50), Inches(2.30), Inches(2.0))
    para(z, t, taille=15, gras=True, couleur=col, police=TITRE, premier=True)
    para(z, st, taille=11.5, gras=True, couleur=NOIR, avant=5, interligne=1.18)
    para(z, d, taille=10.5, couleur=GRIS, avant=5, interligne=1.22)
    etapes_list.extend([pt, b])

# Conclusion
cadre = rect(s, Inches(0.70), Inches(5.92), Inches(11.60), Inches(0.78),
             CREME, arrondi=True, bord=ROUGE, ep=1.5)
_, tf = zone(s, Inches(1.10), Inches(6.08), Inches(10.8), Inches(0.5))
riche(tf, [("Question centrale : ", False, NOIR),
           ("qui décide du chemin d'accès à l'information ?", True, ROUGE),
           (" Le code ou le modèle ?", False, GRIS)],
      taille=14, premier=True)

transition(s, "push", 700, dir="l")
animer(s, [(etapes_list, "fondu", 130, 400), ([cadre], "balayage", 0, 500)])


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 6 — PROBLÉMATIQUE
# ══════════════════════════════════════════════════════════════════════
s = page()
degrade(s, 0, 0, L, H, "1A1A2E", "7A001E", angle=30)
# Géométrie
rect(s, Inches(10.0), Inches(-1.0), Inches(4.5), Inches(4.5), ROUGE,
     forme=MSO_SHAPE.OVAL, transparence=0.88)
motif_points(s, 10.8, 4.5, 10, 6, BLANC, 0.80, 0.20)

_, tf = zone(s, Inches(1.00), Inches(0.80), Inches(10.7), Inches(0.4))
para(tf, "PROBLÉMATIQUE", taille=11, gras=True, couleur=ROUGE_VIF,
     premier=True, espacement=2.0)

q = rect(s, Inches(1.00), Inches(1.55), Inches(10.7), Inches(2.10), None)
tfq = q.text_frame
tfq.margin_left = tfq.margin_right = tfq.margin_top = 0
riche(tfq, [("Comment exploiter des documents publics, hétérogènes et "
             "non structurés pour produire une veille concurrentielle ", False, BLANC),
            ("dont chaque chiffre soit exact, reproductible et vérifiable",
             True, ROUGE_VIF),
            (" ?", False, BLANC)],
      taille=26, police=TITRE, interligne=1.28, premier=True)

ligne(s, Inches(1.00), Inches(3.85), Inches(4.00), Inches(3.85), ROUGE, 3.5)

sous = []
SOUS = [("LA DONNÉE", "Comment transformer 93 documents hétérogènes en une "
         "base interrogeable ?", ROUGE),
        ("L'ARCHITECTURE", "Quelle orchestration garantit qu'un chiffre "
         "affiché est un chiffre lu ?", OR),
        ("LA PREUVE", "Comment démontrer, et non affirmer, que la solution "
         "est fiable ?", EMERAUDE)]
for i, (t, d, col) in enumerate(SOUS):
    x = Inches(0.85 + i * 3.85)
    b = rect(s, x, Inches(4.30), Inches(3.60), Inches(1.95), BLANC,
             transparence=0.92, arrondi=True)
    rect(s, x, Inches(4.30), Inches(0.06), Inches(1.95), col)
    _, z = zone(s, x + Inches(0.30), Inches(4.55), Inches(3.05), Inches(1.6))
    para(z, t, taille=11, gras=True, couleur=col, premier=True, espacement=1.4)
    para(z, d, taille=13, couleur=BLANC, avant=7, interligne=1.28)
    sous.append(b)

pied(s, 6, sombre=True)
transition(s, "fade", 900)
animer(s, [([q], "fondu", 0, 800), (sous, "balayage", 180, 500)])


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 7 — SOLUTION PROPOSÉE
# ══════════════════════════════════════════════════════════════════════
s = page()
fond_blanc(s)
rect(s, 0, 0, Inches(0.08), H, ROUGE)
bandeau_titre(s, 4, "La solution proposée : SpyBusiness",
              sous_titre="Un principe unique, appliqué sans exception",
              n_page=7)

# Principe directeur
principe = rect(s, Inches(0.70), Inches(1.45), Inches(11.60), Inches(1.30),
                NOIR, arrondi=True)
rect(s, Inches(0.70), Inches(1.45), Inches(0.08), Inches(1.30), ROUGE)
_, tf = zone(s, Inches(1.20), Inches(1.60), Inches(10.7), Inches(1.0),
             ancre=MSO_ANCHOR.MIDDLE)
para(tf, "LE PRINCIPE DIRECTEUR", taille=10, gras=True, couleur=ROUGE_VIF,
     premier=True, espacement=1.6)
riche(tf, [("Le déterministe établit, ", True, BLANC),
           ("le modèle formule.", True, ROUGE_VIF)],
      taille=26, avant=5, police=TITRE)

_, tf = zone(s, Inches(0.70), Inches(2.95), Inches(11.6), Inches(0.45))
para(tf, "Aucun chiffre affiché ne vient d'un modèle. Montants, rangs, "
         "écarts et médianes sont calculés en SQL ; le modèle rédige autour "
         "de faits qu'on lui impose.",
     taille=13, couleur=GRIS, premier=True)

# 4 cartes
cartes = []
SOL = [("Une base unique", "Grilles tarifaires, états financiers et textes "
        "réglementaires réunis dans PostgreSQL + pgvector.", ROUGE),
       ("Deux modes d'accès", "Un tableau de bord pour la consultation guidée, "
        "un assistant pour la question libre.", OR),
       ("Vérification finale", "Chaque montant et chaque article cité est "
        "recherché dans les extraits avant affichage.", ARDOISE),
       ("Évaluation chiffrée", "Deux architectures construites, puis "
        "départagées sur 114 questions de référence.", EMERAUDE)]
for i, (t, d, col) in enumerate(SOL):
    x = Inches(0.70 + i * 3.00)
    c = carte_canva(s, x, Inches(3.55), Inches(2.72), Inches(2.10), t, [d],
                    accent=col, taille_titre=14, taille_texte=11.5)
    cartes.append(c)

# Bas
bas = rect(s, Inches(0.70), Inches(5.90), Inches(11.60), Inches(0.85),
           CREME, arrondi=True, bord=GRIS_CLAIR)
_, tf = zone(s, Inches(1.10), Inches(6.08), Inches(10.8), Inches(0.55))
riche(tf, [("Livré et déployé : ", False, GRIS),
           ("spybusiness.onrender.com", True, ROUGE),
           ("  —  cinq écrans, sept banques, un assistant.", False, GRIS)],
      taille=13.5, premier=True)

transition(s, "wipe", 650, dir="l")
animer(s, [([principe], "bandeau", 0, 650), (cartes, "balayage", 140, 420),
           ([bas], "fondu", 0, 400)])


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 8 — IMPLÉMENTATION 1 : SOURCES ET EXTRACTION
# ══════════════════════════════════════════════════════════════════════
s = page()
fond_blanc(s)
rect(s, 0, 0, Inches(0.08), H, ROUGE)
bandeau_titre(s, "5.1", "Des documents aux données : l'extraction",
              sous_titre="Trois méthodes comparées sur le corpus réel",
              n_page=8)

# Tableau comparatif
entetes = ["Méthode", "Ce qu'elle fait bien", "Où elle échoue", "Retenue pour"]
larg = [Inches(2.30), Inches(3.50), Inches(3.20), Inches(2.40)]
x = Inches(0.70)
for e, w in zip(entetes, larg):
    h_ = rect(s, x, Inches(1.78), w, Inches(0.46), NOIR, arrondi=False)
    tfh = h_.text_frame
    tfh.margin_left = Inches(0.14)
    tfh.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tfh, e.upper(), taille=10, gras=True, couleur=BLANC, premier=True,
         espacement=1.2)
    x += w

LIGNES = [("pdfplumber", "Lit directement les tableaux d'un PDF natif.",
           "Page blanche sur un document scanné.", "Grilles natives", ARDOISE),
          ("Docling + OCR", "Restitue texte et tableaux, lignes et colonnes "
           "conservées.", "Peine sur un scan très sombre.",
           "États financiers", ROUGE),
          ("Tesseract", "Relit caractère par caractère une image agrandie.",
           "Ignore la structure du tableau.", "Relais de secours", OR)]
rangs = []
for i, (m, bien, mal, ret, col) in enumerate(LIGNES):
    y = Inches(2.24 + i * 0.82)
    r = rect(s, Inches(0.70), y, Inches(11.40), Inches(0.82),
             BLANC if i % 2 == 0 else GRIS_FOND, bord=GRIS_CLAIR, ep=0.6)
    rect(s, Inches(0.70), y, Inches(0.055), Inches(0.82), col)
    x = Inches(0.70)
    for j, (txt, w) in enumerate(zip([m, bien, mal, ret], larg)):
        _, z = zone(s, x + Inches(0.16), y + Inches(0.12), w - Inches(0.28),
                    Inches(0.58), ancre=MSO_ANCHOR.MIDDLE)
        para(z, txt, taille=11.5 if j else 13,
             gras=(j == 0 or j == 3),
             couleur=col if j == 0 else (NOIR if j == 3 else GRIS),
             police=TITRE if j == 0 else TEXTE, premier=True, interligne=1.18)
        x += w
    rangs.append(r)

# Flux
_, tf = zone(s, Inches(0.70), Inches(4.88), Inches(5.0), Inches(0.4))
para(tf, "LE PROCESSUS RETENU", taille=10.5, gras=True, couleur=ROUGE,
     premier=True, espacement=1.5)

FLUX = [("PDF source", GRIS), ("Natif ou scanné ?", ANTHRACITE),
        ("Extraction", ROUGE), ("Contrôle", OR), ("Base PostgreSQL", EMERAUDE)]
flux = []
x = Inches(0.70)
for i, (t, col) in enumerate(FLUX):
    b = rect(s, x, Inches(5.35), Inches(2.10), Inches(0.72), col, arrondi=True)
    tfb = b.text_frame
    tfb.margin_left = tfb.margin_right = Inches(0.08)
    tfb.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tfb, t, taille=11.5, gras=True, couleur=BLANC,
         align=PP_ALIGN.CENTER, premier=True, interligne=1.1)
    flux.append(b)
    x += Inches(2.10)
    if i < len(FLUX) - 1:
        a = rect(s, x + Inches(0.05), Inches(5.55), Inches(0.28),
                 Inches(0.28), GRIS, forme=MSO_SHAPE.RIGHT_ARROW)
        flux.append(a)
        x += Inches(0.38)

_, tf = zone(s, Inches(0.70), Inches(6.25), Inches(11.6), Inches(0.5))
riche(tf, [("Seuils empiriques : ", False, GRIS),
           ("4 feuilles · 200 cellules", True, NOIR),
           (" pour les grilles, ", False, GRIS),
           ("2 Ko", True, NOIR),
           (" pour les états financiers.", False, GRIS)],
      taille=12, premier=True)

transition(s, "push", 700, dir="l")
animer(s, [(rangs, "bandeau", 150, 380), (flux, "fondu", 90, 300)])


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 9 — IMPLÉMENTATION 2 : LA BASE DE DONNÉES
# ══════════════════════════════════════════════════════════════════════
s = page()
fond_blanc(s)
rect(s, 0, 0, Inches(0.08), H, ROUGE)
bandeau_titre(s, "5.2", "Le modèle de données",
              sous_titre="PostgreSQL + pgvector — données structurées et recherche sémantique",
              n_page=9)

# Table de référence
ref = rect(s, Inches(0.70), Inches(1.55), Inches(2.90), Inches(1.60),
           NOIR, arrondi=True)
rect(s, Inches(0.82), Inches(1.55), Inches(2.66), Inches(0.055), OR)
_, z = zone(s, Inches(0.95), Inches(1.78), Inches(2.4), Inches(1.3))
para(z, "banques", taille=16, gras=True, couleur=BLANC, police=TITRE,
     premier=True)
para(z, "Le référentiel. 7 établissements. Toute table y fait clé étrangère.",
     taille=10.5, couleur=GRIS_CLAIR, avant=6, interligne=1.22)

TABLES = [("cb_tarifs", "~30 000 lignes\nConditions bancaires",
           "banque · période · segment\nsection · libellé · montant", ROUGE),
          ("ef_indicateurs", "~1 800 lignes\nÉtats financiers",
           "banque · exercice\nindicateur · montant", OR),
          ("regl_documents", "~200 chunks\nTextes réglementaires",
           "article · contenu\n+ vecteur 768 dim.", ARDOISE)]
tables = []
for i, (n, t, ch, col) in enumerate(TABLES):
    x = Inches(4.20 + i * 2.85)
    b = rect(s, x, Inches(1.55), Inches(2.60), Inches(2.40), BLANC,
             arrondi=True, bord=GRIS_CLAIR, ep=0.75)
    rect(s, x + Inches(0.08), Inches(1.55), Inches(2.44), Inches(0.055), col)
    _, z = zone(s, x + Inches(0.22), Inches(1.78), Inches(2.15), Inches(2.1))
    para(z, n, taille=13.5, gras=True, couleur=col, police=TITRE, premier=True)
    para(z, t, taille=10, couleur=NOIR, avant=4, interligne=1.22)
    para(z, ch, taille=10, couleur=GRIS, avant=6, interligne=1.28)
    ligne(s, Inches(3.60), Inches(2.40), x, Inches(2.40), GRIS_CLAIR, 1.0,
          pointille=True)
    tables.append(b)

# Extensions
ext = []
EXT = [("pgvector", "Recherche par similarité cosinus. Chaque fragment porte "
        "son vecteur 768 dimensions.", ROUGE),
       ("pg_trgm", "Rapprochement de libellés : un même service ne s'écrit "
        "pas pareil d'une banque à l'autre.", ARDOISE)]
for i, (n, d, col) in enumerate(EXT):
    x = Inches(0.70 + i * 5.95)
    b = rect(s, x, Inches(4.25), Inches(5.65), Inches(0.95), BLANC,
             arrondi=True, bord=col, ep=1.2)
    _, z = zone(s, x + Inches(0.28), Inches(4.42), Inches(5.1), Inches(0.7))
    riche(z, [("EXTENSION  ", False, GRIS), (n, True, col)], taille=11,
          premier=True)
    para(z, d, taille=11.5, couleur=NOIR, avant=3, interligne=1.22)
    ext.append(b)

# Volume total
vol = rect(s, Inches(0.70), Inches(5.50), Inches(11.60), Inches(1.20),
           NOIR, arrondi=True)
rect(s, Inches(0.70), Inches(5.50), Inches(0.08), Inches(1.20), ROUGE_VIF)
_, tf = zone(s, Inches(1.10), Inches(5.70), Inches(10.8), Inches(0.9))
para(tf, "VOLUMÉTRIE TOTALE", taille=10, gras=True, couleur=ROUGE_VIF,
     premier=True, espacement=1.5)
riche(tf, [("33 857 lignes structurées", True, BLANC),
           (" · ", False, GRIS_CLAIR),
           ("31 985 vecteurs 768 dim.", True, BLANC),
           (" · ", False, GRIS_CLAIR),
           ("7 banques", True, BLANC),
           (" · ", False, GRIS_CLAIR),
           ("93 documents", True, BLANC)],
      taille=14, avant=7)

transition(s, "push", 700, dir="l")
animer(s, [([ref], "fondu", 0, 450), (tables, "balayage", 140, 400),
           (ext, "fondu", 100, 350), ([vol], "bandeau", 0, 550)])


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 10 — SOCLE COMMUN ET DEUX MODES D'UTILISATION
# ══════════════════════════════════════════════════════════════════════
s = page()
fond_blanc(s)
rect(s, 0, 0, Inches(0.08), H, ROUGE)
bandeau_titre(s, "5.3", "Un socle commun, deux modes d'utilisation",
              sous_titre="Mêmes données, mêmes outils : ce qui change est qui décide du chemin",
              n_page=10)

# Image d'architecture si disponible
sc = img_doc("archi_globale.jpg")
if sc:
    picture(s, sc, Inches(0.70), Inches(1.45), w=Inches(6.30), bord=True)

d1 = carte_canva(s, Inches(7.30), Inches(1.45), Inches(5.00), Inches(2.30),
    "Le tableau de bord",
    ["L'écran consulté dit déjà quelle information est attendue.",
     "Le système exécute sans demander au modèle de choisir.",
     "écran → requête SQL → calcul → restitution"],
    accent=ROUGE, taille_titre=16)

d2 = carte_canva(s, Inches(7.30), Inches(3.90), Inches(5.00), Inches(2.45),
    "L'assistant conversationnel",
    ["Une zone de saisie reçoit toute question tarifaire, "
     "financière ou réglementaire.",
     "Le problème n'est plus de récupérer, mais de savoir "
     "QUELLE récupération faire.",
     "C'est là que les deux architectures s'opposent."],
    accent=OR, taille_titre=16)

bas = rect(s, Inches(0.70), Inches(6.45), Inches(11.60), Inches(0.62),
           CREME, arrondi=True, bord=GRIS_CLAIR)
_, tf = zone(s, Inches(1.10), Inches(6.56), Inches(10.8), Inches(0.4))
riche(tf, [("Même base, mêmes outils. ", False, GRIS),
           ("Une seule variable change : l'orchestration.", True, ROUGE)],
      taille=12.5, premier=True)

transition(s, "wipe", 650, dir="l")
animer(s, [([d1], "balayage", 0, 500), ([d2], "balayage", 0, 500),
           ([bas], "fondu", 0, 400)])


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 11 — LES DEUX ARCHITECTURES COMPARÉES
# ══════════════════════════════════════════════════════════════════════
s = page()
fond_blanc(s)
rect(s, 0, 0, Inches(0.08), H, ROUGE)
bandeau_titre(s, "5.4", "Les deux architectures comparées",
              sous_titre="Même socle, même modèle rédacteur — une seule variable change",
              n_page=11)

# Entêtes
ent1 = rect(s, Inches(0.70), Inches(1.38), Inches(5.75), Inches(0.58),
            ROUGE, arrondi=True)
tfe = ent1.text_frame
tfe.margin_left = Inches(0.22)
tfe.vertical_anchor = MSO_ANCHOR.MIDDLE
riche(tfe, [("A1  ", True, BLANC), ("MODULAIRE (DÉTERMINISTE)", True, BLANC)],
      taille=14, premier=True)

ent2 = rect(s, Inches(6.65), Inches(1.38), Inches(5.75), Inches(0.58),
            ARDOISE, arrondi=True)
tfe = ent2.text_frame
tfe.margin_left = Inches(0.22)
tfe.vertical_anchor = MSO_ANCHOR.MIDDLE
riche(tfe, [("A2  ", True, BLANC), ("AGENTIQUE (AUTONOME)", True, BLANC)],
      taille=14, premier=True)

A1 = [("Identifier les outils", "Un routeur à règles lit la question."),
      ("Récupérer", "Chaque outil lit directement ou cherche par similarité."),
      ("Fusionner", "Les extraits sont réunis en un seul contexte."),
      ("Rédiger", "Le modèle intervient UNE seule fois.")]
A2 = [("Choisir un outil", "Le modèle lit la question et sélectionne l'outil."),
      ("Exploiter", "L'outil répond ; le modèle analyse le retour."),
      ("Boucler ou s'arrêter", "S'il lui en faut un autre, il recommence (≤6 tours)."),
      ("Rédiger", "Quand il estime en savoir assez, il rédige.")]
g1, g2 = [], []
for i, ((t1, d1_), (t2, d2_)) in enumerate(zip(A1, A2)):
    y = Inches(2.18 + i * 1.02)
    g1.append(etape_canva(s, Inches(0.70), y, Inches(5.75), Inches(0.90),
                          i + 1, t1, d1_, accent=ROUGE))
    g2.append(etape_canva(s, Inches(6.65), y, Inches(5.75), Inches(0.90),
                          i + 1, t2, d2_, accent=ARDOISE))

f1 = rect(s, Inches(0.70), Inches(6.40), Inches(5.75), Inches(0.52),
           CREME, arrondi=True, bord=ROUGE, ep=1.0)
_, z = zone(s, Inches(0.95), Inches(6.50), Inches(5.2), Inches(0.35))
para(z, "1 appel  ·  chemin fixe  ·  auditable", taille=12, gras=True,
     couleur=ROUGE, premier=True)

f2 = rect(s, Inches(6.65), Inches(6.40), Inches(5.75), Inches(0.52),
           GRIS_FOND, arrondi=True, bord=ARDOISE, ep=1.0)
_, z = zone(s, Inches(6.90), Inches(6.50), Inches(5.2), Inches(0.35))
para(z, "2,36 appels  ·  chemin construit à chaque question", taille=12,
     gras=True, couleur=ARDOISE, premier=True)

transition(s, "push", 700, dir="l")
animer(s, [([ent1] + g1 + [f1], "balayage", 120, 350),
           ([ent2] + g2 + [f2], "balayage", 120, 350)])


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 12 — L'ÉVALUATION COMPARATIVE
# ══════════════════════════════════════════════════════════════════════
s = page()
fond_blanc(s)
rect(s, 0, 0, Inches(0.08), H, ROUGE)
bandeau_titre(s, 6, "L'évaluation comparative",
              sous_titre="114 questions de référence, mêmes questions pour les deux architectures",
              n_page=12)

# Composition du jeu
jeu = []
JEU = [("83", "questions factuelles", "vérité SQL sur tarifs et finances", ROUGE),
       ("8", "questions réglementaires", "fidélité aux textes BCEAO", ARDOISE),
       ("23", "synthèses et comparaisons", "fidélité, pertinence, couverture", OR)]
for i, (n, t, d, col) in enumerate(JEU):
    x = Inches(0.70 + i * 4.05)
    b = rect(s, x, Inches(1.45), Inches(3.75), Inches(1.20), BLANC,
             arrondi=True, bord=GRIS_CLAIR, ep=0.75)
    rect(s, x, Inches(1.45), Inches(0.06), Inches(1.20), col)
    _, z = zone(s, x + Inches(0.30), Inches(1.58), Inches(3.2), Inches(0.9))
    riche(z, [(n + "  ", True, col), (t, True, NOIR)], taille=17, premier=True)
    para(z, d, taille=10.5, couleur=GRIS, avant=4, interligne=1.20)
    jeu.append(b)

# Tableau de résultats
MES = [("Exactitude factuelle (101 q.)", "92,1 %", "89,1 %", True),
       ("Appels au modèle / question", "1", "2,36", True),
       ("Latence médiane", "2,87 s", "4,51 s", True),
       ("Reproductibilité (8 runs)", "65 %", "46 %", True),
       ("Fidélité jugée (synthèses)", "0,84", "0,85", None),
       ("Pertinence jugée (synthèses)", "0,79", "0,89", False)]

x0 = Inches(0.70)
w0, w1 = Inches(6.30), Inches(2.55)
h_ = rect(s, x0, Inches(2.88), Inches(11.40), Inches(0.46), NOIR, arrondi=False)
for lbl, x, w in [("MESURE", x0 + Inches(0.20), w0),
                   ("MODULAIRE", x0 + w0, w1), ("AGENTIQUE", x0 + w0 + w1, w1)]:
    _, z = zone(s, x, Inches(2.96), w, Inches(0.32),
                align=PP_ALIGN.LEFT if lbl == "MESURE" else PP_ALIGN.CENTER)
    para(z, lbl, taille=10, gras=True, couleur=BLANC, premier=True,
         espacement=1.3,
         align=PP_ALIGN.LEFT if lbl == "MESURE" else PP_ALIGN.CENTER)

rangs = []
for i, (m, a, b, gagne_a) in enumerate(MES):
    y = Inches(3.34 + i * 0.44)
    r = rect(s, x0, y, Inches(11.40), Inches(0.44),
             BLANC if i % 2 == 0 else GRIS_FOND, bord=GRIS_CLAIR, ep=0.5)
    _, z = zone(s, x0 + Inches(0.20), y + Inches(0.08), w0 - Inches(0.25),
                Inches(0.30))
    para(z, m, taille=12, couleur=NOIR, premier=True)
    for val, x, meilleur in [(a, x0 + w0, gagne_a is True),
                              (b, x0 + w0 + w1, gagne_a is False)]:
        _, z = zone(s, x, y + Inches(0.06), w1, Inches(0.32),
                    align=PP_ALIGN.CENTER)
        para(z, val, taille=12.5, gras=meilleur,
             couleur=ROUGE if meilleur else GRIS,
             align=PP_ALIGN.CENTER, premier=True)
    rangs.append(r)

# Lecture
lect = rect(s, Inches(0.70), Inches(6.10), Inches(11.60), Inches(0.72),
            CREME, arrondi=True, bord=GRIS_CLAIR)
_, tf = zone(s, Inches(1.10), Inches(6.24), Inches(10.8), Inches(0.5))
riche(tf, [("Les écarts de coût sont établis (", False, GRIS),
           ("p < 0,001", True, NOIR),
           ("). ", False, GRIS),
           ("L'exactitude ne départage pas (p = 0,63).", True, NOIR)],
      taille=12.5, premier=True)

transition(s, "push", 700, dir="l")
animer(s, [(jeu, "balayage", 140, 400), (rangs, "bandeau", 80, 280),
           ([lect], "fondu", 0, 420)])


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 13 — ARCHITECTURE RETENUE
# ══════════════════════════════════════════════════════════════════════
s = page()
fond_blanc(s)
rect(s, 0, 0, Inches(0.08), H, ROUGE)
bandeau_titre(s, 7, "L'architecture retenue : la modulaire",
              sous_titre="À qualité jugée équivalente, trois raisons départagent",
              n_page=13)

# Image architecture
ar = img_doc("archi_retenue.jpg")
if ar:
    picture(s, ar, Inches(0.70), Inches(1.50), w=Inches(7.20), bord=True)

rais = []
RAIS = [("La reproductibilité", "65 % de réponses identiques contre 46 %. "
         "Deux lectures ne doivent pas dire deux choses différentes.", ROUGE),
        ("Le coût", "Un seul appel au modèle par question, contre 2,36. "
         "Latence médiane divisée par deux.", OR),
        ("L'auditabilité", "Un chemin fixe est traçable. Le comité de direction "
         "peut remonter chaque chiffre à sa requête SQL.", ARDOISE)]
for i, (t, d, col) in enumerate(RAIS):
    y = Inches(1.50 + i * 1.40)
    c = carte_canva(s, Inches(8.20), y, Inches(4.20), Inches(1.25), t, [d],
                    accent=col, taille_titre=14, taille_texte=11)
    rais.append(c)

# Conclusion
concl = rect(s, Inches(0.70), Inches(5.65), Inches(11.60), Inches(1.10),
             NOIR, arrondi=True)
rect(s, Inches(0.70), Inches(5.65), Inches(0.08), Inches(1.10), ROUGE_VIF)
_, tf = zone(s, Inches(1.10), Inches(5.82), Inches(10.8), Inches(0.85))
riche(tf, [("Le modèle garde un rôle essentiel, mais il intervient ", False, BLANC),
           ("après la détermination du résultat", True, ROUGE_VIF),
           (". Dans un contexte bancaire, l'exactitude et la reproductibilité "
            "l'emportent sur la souplesse.", False, BLANC)],
      taille=13.5, premier=True, interligne=1.32)

transition(s, "wipe", 650, dir="l")
animer(s, [(rais, "balayage", 150, 420), ([concl], "fondu", 0, 550)])


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 14 — PROJECTION À TROIS ANS
# ══════════════════════════════════════════════════════════════════════
s = page()
fond_blanc(s)
rect(s, 0, 0, Inches(0.08), H, ROUGE)
bandeau_titre(s, 8, "La modélisation prospective à trois ans",
              sous_titre="Une logique métier traduite en règles de calcul reproductibles",
              n_page=14)

etapes_proj = []
ET = [("Référence", "Moyenne des 3 meilleures banques — un résultat isolé ne "
       "fait pas la norme.", "C = (B₁ + B₂ + B₃) / 3", ROUGE),
      ("Écart", "Différence entre la cible et la performance actuelle de la SGCI.",
       "E = max(0, C − V₀)", OR),
      ("Scénarios", "Trois niveaux d'exécution. Ce sont des hypothèses, non "
       "des probabilités.", "wₛ = 0,60 · 1,00 · 1,20", ARDOISE),
      ("Trajectoire", "L'écart est réparti linéairement sur trois exercices.",
       "Vₜ = V₀ + (Eₛ / 3) × t", EMERAUDE)]
for i, (t, d, f, col) in enumerate(ET):
    y = Inches(1.45 + i * 1.22)
    b = rect(s, Inches(0.70), y, Inches(7.50), Inches(1.08), BLANC,
             arrondi=True, bord=GRIS_CLAIR, ep=0.75)
    rect(s, Inches(0.70), y, Inches(0.055), Inches(1.08), col)
    p = rect(s, Inches(0.95), y + Inches(0.28), Inches(0.52), Inches(0.52),
             col, forme=MSO_SHAPE.OVAL)
    tfp = p.text_frame
    tfp.margin_left = tfp.margin_right = tfp.margin_top = tfp.margin_bottom = 0
    tfp.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tfp, str(i + 1), taille=14, gras=True, couleur=BLANC,
         align=PP_ALIGN.CENTER, premier=True)
    _, z = zone(s, Inches(1.68), y + Inches(0.12), Inches(6.3), Inches(0.85))
    para(z, t, taille=14, gras=True, couleur=NOIR, police=TITRE, premier=True)
    para(z, d, taille=11, couleur=GRIS, avant=3, interligne=1.20)
    # Formule
    fo = rect(s, Inches(8.50), y + Inches(0.20), Inches(3.80), Inches(0.65),
              NOIR, arrondi=True)
    tff = fo.text_frame
    tff.margin_left = tff.margin_right = Inches(0.12)
    tff.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tff, f, taille=12, gras=True, couleur=BLANC, police=MONO,
         align=PP_ALIGN.CENTER, premier=True)
    etapes_proj.extend([b, fo])

# Contrôle
ctrl = rect(s, Inches(0.70), Inches(6.40), Inches(11.60), Inches(0.58),
            CREME, arrondi=True, bord=GRIS_CLAIR)
_, tf = zone(s, Inches(1.10), Inches(6.50), Inches(10.8), Inches(0.38))
riche(tf, [("Contrôle de plausibilité : ", True, ROUGE),
           ("l'effort annuel est comparé au taux de croissance historique "
            "réellement observé.", False, GRIS)],
      taille=12, premier=True)

transition(s, "push", 700, dir="l")
animer(s, [(etapes_proj, "balayage", 110, 360), ([ctrl], "fondu", 0, 380)])


# ══════════════════════════════════════════════════════════════════════
#  SLIDE 15 — DÉMONSTRATION ET CHIFFRES CLÉS
# ══════════════════════════════════════════════════════════════════════
s = page()
degrade(s, 0, 0, L, H, "1A1A2E", "7A001E", angle=140)
# Géométrie
rect(s, Inches(-1.5), Inches(-1.5), Inches(5.0), Inches(5.0), ROUGE,
     forme=MSO_SHAPE.OVAL, transparence=0.90)
rect(s, Inches(10.0), Inches(5.0), Inches(4.5), Inches(4.5), BLANC,
     forme=MSO_SHAPE.OVAL, transparence=0.92)
motif_points(s, 10.5, 0.4, 10, 5, BLANC, 0.82, 0.22)

_, tf = zone(s, Inches(0.70), Inches(0.55), Inches(11.6), Inches(0.9))
para(tf, "DÉMONSTRATION ET CHIFFRES CLÉS", taille=11, gras=True,
     couleur=ROUGE_VIF, premier=True, espacement=2.0)
para(tf, "Ce que le projet a produit, et ce qu'il change", taille=28,
     gras=True, couleur=BLANC, police=TITRE, avant=5)

# KPIs
kpis = []
KPI = [("92,1 %", "d'exactitude factuelle\nsur 101 questions"),
       ("2,87 s", "de latence médiane\n(÷2 vs agentique)"),
       ("162 s → 3,8 s", "gain ×43 sur l'écran\nle plus lourd"),
       ("≥ 20 M FCFA", "d'économie annuelle\nvs cabinet externe")]
for i, (v, l) in enumerate(KPI):
    x = Inches(0.70 + i * 3.00)
    b = rect(s, x, Inches(2.10), Inches(2.72), Inches(1.55), BLANC,
             transparence=0.93, arrondi=True)
    rect(s, x + Inches(0.10), Inches(2.10), Inches(2.52), Inches(0.05),
         ROUGE_VIF)
    _, z = zone(s, x + Inches(0.24), Inches(2.35), Inches(2.3), Inches(1.2))
    para(z, v, taille=24 if len(v) < 10 else 18, gras=True, couleur=ROUGE_VIF,
         police=TITRE, premier=True, interligne=1.0)
    para(z, l, taille=10.5, couleur=NOIR, avant=5, interligne=1.22)
    kpis.append(b)

# Screenshot
sh = img_doc("u02_accueil.jpg")
if sh:
    picture(s, sh, Inches(0.70), Inches(3.95), h=Inches(2.30), bord=False)

# Livrables
livr = []
LIVR = [("L'application", "5 écrans, 7 banques, 1 assistant. En ligne sur "
         "spybusiness.onrender.com."),
        ("Le mémoire", "81 pages : conception, évaluation comparative, "
         "résultats chiffrés."),
        ("La documentation", "Vue technique et vue utilisateur, pour la "
         "reprise du projet.")]
for i, (t, d) in enumerate(LIVR):
    y = Inches(3.95 + i * 0.88)
    b = rect(s, Inches(7.10), y, Inches(5.30), Inches(0.78), BLANC,
             transparence=0.93, arrondi=True)
    rect(s, Inches(7.10), y, Inches(0.05), Inches(0.78), ROUGE_VIF)
    _, z = zone(s, Inches(7.38), y + Inches(0.10), Inches(4.8), Inches(0.58))
    para(z, t, taille=13, gras=True, couleur=BLANC, police=TITRE, premier=True)
    para(z, d, taille=10.5, couleur=ROSE, avant=2, interligne=1.18)
    livr.append(b)

_, tf = zone(s, Inches(0.70), Inches(6.85), Inches(11.6), Inches(0.4),
             align=PP_ALIGN.CENTER)
para(tf, "MERCI DE VOTRE ATTENTION", taille=14, gras=True, couleur=BLANC,
     align=PP_ALIGN.CENTER, premier=True, espacement=2.2)

transition(s, "fade", 900)
animer(s, [(kpis, "balayage", 130, 400), (livr, "fondu", 120, 350)])


# ═══════════════════════════════════════════════════════════════════════
#  SAUVEGARDE
# ═══════════════════════════════════════════════════════════════════════
SORTIE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "soutenance_canva.pptx")
prs.save(SORTIE)
n_slides = len(list(prs.slides))
print(f"  OK {n_slides} diapositives -> {SORTIE}")
