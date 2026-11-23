# -*- coding: utf-8 -*-
"""
socle.py — briques de mise en page du diaporama de soutenance SpyBusiness
=========================================================================
Charte OFFICIELLE fournie le 2026-09-15 (rouge SGCI #C8102E + neutres + 3 accents),
reprise telle quelle -- ce n'est plus une palette inventee.

Polices demandees : Fraunces (titres), DM Sans (texte), JetBrains Mono (technique).
AUCUNE des trois n'est installee sur ce poste (verifie via
System.Drawing.Text.InstalledFontCollection le 2026-09-15) -- PowerPoint les remplacerait
silencieusement par une police par defaut a l'ouverture, ce qui casserait le rendu.
Remplacees par des equivalents Windows fiables et visuellement proches :
    Fraunces (serif elegante)          -> Cambria
    DM Sans (sans-serif geometrique)   -> Segoe UI
    JetBrains Mono (monospace)         -> Consolas
Si les vraies polices sont installees plus tard, changer TITRE/TEXTE/MONO ci-dessous suffit
-- aucune autre ligne du diaporama n'a la police en dur.

Format 16:9, 13,33 x 7,5 pouces — celui du modele « Inspection Drone » fourni.

POURQUOI CE MODULE EXISTE SEPAREMENT : python-pptx ne connait ni bandeau, ni separateur de
partie, ni carte. Chaque diapositive les redessinerait avec des coordonnees recopiees, et une
valeur qui derive quelque part suffit a decaler tout le diaporama. Les gabarits sont ecrits
UNE fois ici.

ANIMATIONS : python-pptx ne sait pas les ecrire. Un .pptx etant une archive de XML, on injecte
<p:transition> (passage d une diapositive a l autre) et <p:timing> (apparition des elements).
PowerPoint est strict : un bloc mal forme fait echouer l ouverture ou disparaitre l animation
en silence. D ou la verification obligatoire dans le VRAI PowerPoint (verifier.py).
"""
from lxml import etree
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import nsdecls, qn
from pptx.util import Emu, Inches, Pt

# ── Charte officielle SGCI (fournie le 2026-09-15) ────────────────────────────────────
ROUGE       = RGBColor(0xC8, 0x10, 0x2E)   # --red : rouge SGCI, couleur directrice
ROUGE_FONCE = RGBColor(0x8D, 0x07, 0x1F)   # --red-dark : profondeur des fonds pleins
ROUGE_CLAIR = RGBColor(0xEC, 0x31, 0x50)   # --red-light : eclat, chiffre ou pictogramme
ROUGE_VIF   = ROUGE_CLAIR                  # alias — code existant
BORDEAUX    = ROUGE_FONCE                  # alias — code existant
NOIR        = RGBColor(0x15, 0x17, 0x1C)   # --ink
ANTHRACITE  = RGBColor(0x22, 0x26, 0x30)   # --ink-2
GRIS        = RGBColor(0x69, 0x6D, 0x76)   # --muted
GRIS_CLAIR  = RGBColor(0xE4, 0xE5, 0xE9)   # dérivé neutre, pour bordures/fonds legers
CREME       = RGBColor(0xF7, 0xF4, 0xED)   # --cream
PAPIER      = RGBColor(0xFF, 0xFD, 0xFA)   # --paper
BLANC       = RGBColor(0xFF, 0xFF, 0xFF)   # --white
VERT        = RGBColor(0x18, 0x79, 0x4E)   # --green : ce qui est retenu, valide
OR          = RGBColor(0x9A, 0x67, 0x00)   # --amber : accent chaud
BLEU        = RGBColor(0x2F, 0x5F, 0xCE)   # --blue : « l'autre » objet dans une comparaison
ARDOISE     = BLEU                         # alias — code existant
ROSE        = RGBColor(0xF4, 0xA8, 0xB8)   # texte secondaire SUR fond rouge fonce (derive)

TITRE = "Cambria"      # Fraunces demandee, absente du poste -> equivalent serif Windows
TEXTE = "Segoe UI"      # DM Sans demandee, absente du poste -> equivalent Windows moderne
MONO  = "Consolas"      # JetBrains Mono demandee, absente du poste -> equivalent Windows

L, H = Inches(13.333), Inches(7.5)


# ══════════════════════════════════════════════════════════════════════════════════════
#  TEXTE
# ══════════════════════════════════════════════════════════════════════════════════════
def zone(slide, x, y, w, h, *, align=PP_ALIGN.LEFT, ancre=MSO_ANCHOR.TOP):
    """Zone de texte sans marge ni ajustement automatique : la mise en page reste celle
    decidee ici, PowerPoint ne la reflowe pas dans notre dos."""
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = ancre
    tf.paragraphs[0].alignment = align
    return tb, tf


def para(tf, texte, *, taille=14, gras=False, couleur=NOIR, police=TEXTE,
         align=PP_ALIGN.LEFT, interligne=1.18, avant=0, premier=False, italique=False,
         espacement=None):
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
    if espacement is not None:                       # interlettrage, en points
        r.font._rPr.set("spc", str(int(espacement * 100)))
    return p


def riche(tf, morceaux, *, taille=14, couleur=NOIR, police=TEXTE, align=PP_ALIGN.LEFT,
          interligne=1.18, avant=0, premier=False, espacement=None):
    """Un paragraphe fait de plusieurs fragments (texte, gras, couleur) — pour mettre un
    chiffre en avant SANS couper la phrase en trois zones de texte."""
    p = tf.paragraphs[0] if premier else tf.add_paragraph()
    p.alignment = align
    p.line_spacing = interligne
    if avant:
        p.space_before = Pt(avant)
    for m in morceaux:
        t = m[0]
        gras = m[1] if len(m) > 1 else False
        col = m[2] if len(m) > 2 else couleur
        r = p.add_run()
        r.text = t
        r.font.size, r.font.bold, r.font.name = Pt(taille), gras, police
        r.font.color.rgb = col
        if espacement is not None:
            r.font._rPr.set("spc", str(int(espacement * 100)))
    return p


# ══════════════════════════════════════════════════════════════════════════════════════
#  FORMES
# ══════════════════════════════════════════════════════════════════════════════════════
def rect(slide, x, y, w, h, couleur, *, forme=MSO_SHAPE.RECTANGLE, bord=None, ep=1.0,
         transparence=None):
    s = slide.shapes.add_shape(forme, int(x), int(y), int(w), int(h))
    s.shadow.inherit = False
    if couleur is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = couleur
        if transparence:
            _transparence(s.fill.fore_color, transparence)
    if bord is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = bord
        s.line.width = Pt(ep)
    s.text_frame.word_wrap = True
    return s


def _transparence(couleur, pct):
    """python-pptx n expose pas l alpha : on l ecrit dans le XML de la couleur."""
    el = couleur._xFill.find(qn("a:srgbClr"))
    if el is not None:
        a = etree.SubElement(el, qn("a:alpha"))
        a.set("val", str(int((1 - pct) * 100000)))


def degrade(slide, x, y, w, h, c1, c2, *, angle=45):
    """Fond en degrade — ce qui distingue immediatement une diapositive composee d une
    diapositive par defaut. python-pptx ne le propose pas : on ecrit le gradFill."""
    # rect() attend un RGBColor ; on passe donc une couleur reelle, puis on remplace le
    # remplissage uni par le degrade. Passer directement la chaine hexadecimale levait
    # « assigned value must be type RGBColor ».
    s = rect(slide, x, y, w, h, RGBColor.from_string(c1))
    sp = s.fill._xPr                       # <a:spPr> de la forme
    xml = (f'<a:gradFill {nsdecls("a")} rotWithShape="1">'
           f'<a:gsLst>'
           f'<a:gs pos="0"><a:srgbClr val="{c1}"/></a:gs>'
           f'<a:gs pos="100000"><a:srgbClr val="{c2}"/></a:gs>'
           f'</a:gsLst><a:lin ang="{int(angle * 60000)}" scaled="0"/></a:gradFill>')
    grad = etree.fromstring(xml)
    # L ORDRE DES ENFANTS DE <a:spPr> EST IMPOSE PAR LE SCHEMA : xfrm, prstGeom, remplissage,
    # ln... Une insertion a l aveugle (index 1) plantait le gradFill ENTRE xfrm et prstGeom :
    # PowerPoint rejetait alors le remplissage sans le moindre message, et la diapositive
    # restait BLANCHE — tous les textes blancs devenaient invisibles. On remplace donc le
    # solidFill existant, a sa place exacte.
    ancien = sp.find(qn("a:solidFill"))
    if ancien is not None:
        sp.replace(ancien, grad)
    else:
        geom = sp.find(qn("a:prstGeom"))
        sp.insert(list(sp).index(geom) + 1 if geom is not None else 0, grad)
    return s


def ligne(slide, x1, y1, x2, y2, couleur=GRIS_CLAIR, ep=1.0, *, pointille=False):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, int(x1), int(y1), int(x2), int(y2))
    c.line.color.rgb = couleur
    c.line.width = Pt(ep)
    if pointille:
        c.line._get_or_add_ln().append(
            etree.fromstring(f'<a:prstDash {nsdecls("a")} val="dash"/>'))
    return c


def fleche(slide, x, y, w, h, couleur=ROUGE):
    s = rect(slide, x, y, w, h, couleur, forme=MSO_SHAPE.RIGHT_ARROW)
    return s


# ══════════════════════════════════════════════════════════════════════════════════════
#  GABARITS
# ══════════════════════════════════════════════════════════════════════════════════════
def fond(slide, couleur=BLANC):
    rect(slide, 0, 0, L, H, couleur)


def filigrane(slide):
    """Deux aplats rouges tres pales en diagonale : la page respire au lieu d etre un
    rectangle blanc. Discret — il ne doit jamais concurrencer le contenu."""
    b = rect(slide, Emu(int(L * 0.72)), Emu(int(-H * 0.22)), Emu(int(L * 0.55)),
             Emu(int(H * 0.62)), ROUGE, transparence=0.965)
    b.rotation = 18
    c = rect(slide, Emu(int(-L * 0.10)), Emu(int(H * 0.76)), Emu(int(L * 0.42)),
             Emu(int(H * 0.42)), ROUGE, transparence=0.975)
    c.rotation = 12
    return b, c


def bandeau(slide, numero, titre, *, sous_titre=None, n_page=None, total=15):
    """Bandeau superieur : pastille numerotee puis titre. Repere constant d une diapositive
    a l autre — c est ce qui donne au jury le sentiment d un document, pas d une suite
    d ecrans."""
    rect(slide, Inches(0.0), Inches(0.34), Inches(0.52), Inches(0.44), GRIS_CLAIR)
    b = rect(slide, Inches(0.40), Inches(0.34), Inches(0.66), Inches(0.44), ROUGE)
    tf = b.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tf, numero, taille=14, gras=True, couleur=BLANC, align=PP_ALIGN.CENTER, premier=True)

    _, t = zone(slide, Inches(1.28), Inches(0.30), Inches(11.3), Inches(0.52))
    para(t, titre, taille=24, gras=True, couleur=NOIR, police=TITRE, premier=True)
    y = Inches(0.86)
    if sous_titre:
        _, s = zone(slide, Inches(1.28), y, Inches(11.3), Inches(0.32))
        para(s, sous_titre, taille=12.5, couleur=GRIS, italique=True, premier=True)
        y = Inches(1.18)
    if n_page:
        pied(slide, n_page, total)
    return y


def pied(slide, n, total, *, sombre=False):
    couleur = RGBColor(0xFF, 0xB8, 0xC4) if sombre else GRIS
    _, tf = zone(slide, Inches(11.5), Inches(6.98), Inches(1.6), Inches(0.3),
                 align=PP_ALIGN.RIGHT)
    riche(tf, [(f"{n}", True, ROUGE if not sombre else BLANC), (f" / {total}", False, couleur)],
          taille=10.5, premier=True, align=PP_ALIGN.RIGHT)


def separateur(slide, numero, titre, sous_titre=None):
    """Page de partie : fond rouge profond, grand chiffre, carte blanche decalee."""
    degrade(slide, 0, 0, L, H, "E4002B", "7A001E", angle=35)
    # trame de points, comme la page de garde du modele fourni
    for i in range(9):
        for j in range(5):
            rect(slide, Inches(10.9 + i * 0.24), Inches(0.75 + j * 0.24),
                 Inches(0.075), Inches(0.075), BLANC, transparence=0.72)

    _, n = zone(slide, Inches(1.25), Inches(1.95), Inches(2.5), Inches(3.6),
                align=PP_ALIGN.CENTER, ancre=MSO_ANCHOR.MIDDLE)
    para(n, str(numero), taille=185, gras=True, couleur=BLANC, police=TITRE,
         align=PP_ALIGN.CENTER, premier=True)

    rect(slide, Inches(4.00), Inches(2.42), Inches(9.9), Inches(2.24), BORDEAUX,
         forme=MSO_SHAPE.ROUNDED_RECTANGLE)
    c = rect(slide, Inches(3.88), Inches(2.30), Inches(9.9), Inches(2.24), BLANC,
             forme=MSO_SHAPE.ROUNDED_RECTANGLE)
    tf = c.text_frame
    tf.margin_left = Inches(0.62)
    tf.margin_right = Inches(0.45)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tf, titre.upper(), taille=30, gras=True, couleur=NOIR, police=TITRE, premier=True)
    if sous_titre:
        para(tf, sous_titre, taille=14.5, couleur=ROUGE, italique=True, avant=4)
    return c


def carte(slide, x, y, w, h, titre, lignes, *, accent=ROUGE, fond_carte=BLANC,
          taille_titre=15, taille_texte=12):
    """Bloc encadre, filet d accent en haut. La brique des diapositives en colonnes.
    Renvoie (carte, filet) -- LE FILET EST UNE FORME A PART, distincte de la carte
    elle-meme : un appelant qui n'anime que la valeur de retour (comme avant) laisse le
    filet TOUJOURS visible, meme quand la carte est cachee en attente d'un clic. Bug
    trouve le 2026-09-15 par capture d'ecran d'un vrai diaporama (pas juste un export
    statique, qui ne le montrait pas) : le filet rouge/or de "Service Data" restait
    visible AVANT son clic, sur la diapositive Entreprise a deux vues."""
    c = rect(slide, x, y, w, h, fond_carte, bord=GRIS_CLAIR, ep=1.0)
    filet = rect(slide, x, y, w, Inches(0.06), accent)
    tf = c.text_frame
    tf.margin_left = tf.margin_right = Inches(0.24)
    tf.margin_top = Inches(0.30)
    tf.margin_bottom = Inches(0.18)
    tf.vertical_anchor = MSO_ANCHOR.TOP
    para(tf, titre, taille=taille_titre, gras=True, couleur=NOIR, police=TITRE, premier=True)
    for l in lignes:
        para(tf, l, taille=taille_texte, couleur=GRIS, avant=7, interligne=1.24)
    return c, filet


def chiffre(slide, x, y, w, valeur, libelle, *, taille=42, couleur=ROUGE, align=PP_ALIGN.LEFT):
    _, tf = zone(slide, x, y, w, Inches(1.05), align=align)
    para(tf, valeur, taille=taille, gras=True, couleur=couleur, police=TITRE,
         align=align, premier=True, interligne=0.95)
    para(tf, libelle, taille=11, couleur=GRIS, avant=3, align=align, interligne=1.15)


def cercle_chiffre(slide, cx, cy, diametre, valeur, libelle, *, couleur=ROUGE,
                    taille_valeur=26, taille_libelle=11.5):
    """Le chiffre ECRIT DANS le cercle plein, pas une icone generique a cote -- c est la
    demande explicite du 2026-09-15 ("les chiffres doivent etre dans des cercles comme
    cela"), en reponse a la premiere version qui reutilisait les pictogrammes generiques
    du template (une roue dentee, une cible...) sans rapport avec le chiffre annonce.
    `cx, cy` est le CENTRE du cercle (pas le coin) -- plus simple pour aligner une rangee."""
    r = Emu(int(diametre / 2))
    c = rect(slide, Emu(int(cx - r)), Emu(int(cy - r)), diametre, diametre, couleur,
             forme=MSO_SHAPE.OVAL)
    tf = c.text_frame
    tf.margin_left = tf.margin_right = Inches(0.08)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tf, valeur, taille=taille_valeur, gras=True, couleur=BLANC, police=TITRE,
         align=PP_ALIGN.CENTER, premier=True, interligne=0.95)
    larg_etiquette = Emu(int(diametre * 1.32))   # > diametre mais < l'ecart entre cercles,
    zone_sh, z = zone(slide, Emu(int(cx - larg_etiquette / 2)), Emu(int(cy + r + Inches(0.14))),
                       larg_etiquette, Inches(0.52), align=PP_ALIGN.CENTER)
    para(z, libelle, taille=taille_libelle, gras=True, couleur=NOIR, align=PP_ALIGN.CENTER,
         premier=True, interligne=1.1)
    return c, zone_sh


def puce(slide, x, y, w, texte, *, taille=13, couleur=NOIR, gras=False, accent=ROUGE,
         h=Inches(0.42)):
    rect(slide, x, y + Inches(0.055), Inches(0.105), Inches(0.105), accent)
    _, tf = zone(slide, x + Inches(0.27), y, w - Inches(0.27), h)
    para(tf, texte, taille=taille, couleur=couleur, gras=gras, interligne=1.24, premier=True)


def etape(slide, x, y, w, h, n, titre, texte, *, accent=ROUGE):
    """Une etape numerotee : pastille ronde + titre + explication. Sert aux deux
    architectures et au processus d extraction."""
    c = rect(slide, x, y, w, h, BLANC, bord=GRIS_CLAIR)
    rect(slide, x, y, Inches(0.05), h, accent)
    # PASTILLE A L INTERIEUR, centree verticalement. Posee au-dessus du cadre (y - 0,20)
    # elle mordait sur la carte precedente, et le texte, coince sous elle, debordait par le
    # bas. Constate sur la vue exportee de PowerPoint, pas devine.
    d = Inches(0.50)
    p = rect(slide, x + Inches(0.26), y + (h - d) / 2, d, d, accent, forme=MSO_SHAPE.OVAL)
    tf = p.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tf, str(n), taille=15, gras=True, couleur=BLANC, align=PP_ALIGN.CENTER, premier=True)
    _, t = zone(slide, x + Inches(0.92), y + Inches(0.10), w - Inches(1.14), h - Inches(0.20),
                ancre=MSO_ANCHOR.MIDDLE)
    para(t, titre, taille=13, gras=True, couleur=NOIR, police=TITRE, premier=True)
    if texte:
        para(t, texte, taille=10.5, couleur=GRIS, avant=3, interligne=1.20)
    return c


def image(slide, chemin, x, y, *, w=None, h=None, bord=True):
    """Renvoie (image, cadre) si bord=True, sinon juste l'image seule (pas de tuple) --
    LE CADRE EST UNE FORME A PART. Meme bug que carte() (trouve en meme temps, meme
    capture d'ecran) : un appelant qui n'anime que l'image renvoyee laisse le cadre
    TOUJOURS visible, meme apres la sortie de l'image elle-meme."""
    p = slide.shapes.add_picture(chemin, int(x), int(y), width=w, height=h)
    if bord:
        cadre = rect(slide, p.left, p.top, p.width, p.height, None, bord=GRIS_CLAIR, ep=0.75)
        return p, cadre
    return p


# ══════════════════════════════════════════════════════════════════════════════════════
#  ANIMATIONS — XML injecte dans la diapositive
# ══════════════════════════════════════════════════════════════════════════════════════
_P14 = 'xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main"'


def transition(slide, type_="fade", duree_ms=700, **attrs):
    """<p:transition> — le passage d une diapositive a la suivante. C est de la que vient
    l essentiel de l allure « pro » : les deux modeles fournis en portent sur plus de vingt
    diapositives sur vingt-huit, pour tres peu d animations d elements."""
    sup = "".join(f' {k}="{v}"' for k, v in attrs.items())
    xml = (f'<p:transition {nsdecls("p")} {_P14} spd="med" p14:dur="{duree_ms}">'
           f'<p:{type_}{sup}/></p:transition>')
    anc = slide.element.find(qn("p:transition"))
    if anc is not None:
        slide.element.remove(anc)
    # <p:transition> doit venir APRES <p:clrMapOvr> : place en fin, l ordre du schema
    # met timing en dernier, on reinsere donc avant lui si besoin.
    slide.element.append(etree.fromstring(xml))


# Effets d entree, par identifiant de preset PowerPoint. On s en tient a ceux qui reposent
# sur <p:animEffect> (un filtre), les plus surs : les effets a mouvement demandent un
# <p:animMotion> avec un chemin, ou la moindre erreur fait disparaitre l animation.
_EFFETS = {
    "fondu":      (10, "0",  "fade"),
    "balayage":   (22, "4",  "wipe(up)"),
    "bandeau":    (22, "8",  "wipe(left)"),
    "store":      (3,  "10", "blinds(horizontal)"),
    "damier":     (5,  "10", "checkerboard(across)"),
    "dissoudre":  (9,  "0",  "dissolve"),
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

# Effet de SORTIE (miroir de _EFFET) : necessaire pour une "bascule de vue" sur une meme
# diapo (ex. les chiffres SGCI qui laissent place a l'organigramme au clic) -- sans lui,
# animer() ne pouvait QUE faire apparaitre des elements, jamais en faire disparaitre un
# pour le remplacer par un autre. Le <p:set> passe a "hidden" APRES l'animation (delai =
# sa duree), pas avant : la forme doit rester visible pendant tout le fondu de sortie.
_EFFET_SORTIE = """<p:par><p:cTn id="{c}" presetID="{preset}" presetClass="exit" presetSubtype="{sub}"
 fill="hold" grpId="0" nodeType="{node}"><p:stCondLst><p:cond delay="{delai}"/></p:stCondLst>
<p:childTnLst>
<p:animEffect transition="out" filter="{filtre}"><p:cBhvr>
<p:cTn id="{d}" dur="{duree}"/><p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>
<p:set><p:cBhvr><p:cTn id="{e}" dur="1" fill="hold"><p:stCondLst><p:cond delay="{duree}"/></p:stCondLst></p:cTn>
<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>
<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>
<p:to><p:strVal val="hidden"/></p:to></p:set>
</p:childTnLst></p:cTn></p:par>"""


def animer(slide, sequences):
    """Anime la diapositive.

    `sequences` est une liste de groupes ; CHAQUE groupe part au clic, et les formes qu il
    contient s enchainent toutes seules. L orateur avance donc a son rythme sans avoir a
    cliquer vingt fois.

        animer(slide, [
            ([titre],            "fondu",    0),      # 1er clic
            (cartes,             "balayage", 140),    # 2e clic, cartes en cascade
        ])

    Un groupe peut aussi etre une LISTE d instructions qui partagent le meme clic --
    utile pour une bascule de vue, ou une premiere vue doit SORTIR pendant qu une seconde
    ENTRE au meme clic. Chaque instruction accepte un 5e element, `sens` ("entree" par
    defaut, ou "sortie") :

        animer(slide, [
            ([titre], "fondu", 0),                              # 1er clic : normal
            [(vue1, "fondu", 0, 400, "sortie"),                 # 2e clic : vue1 sort...
             (vue2, "balayage", 100, 450, "entree")],           #           ...vue2 entre
        ])

    Les identifiants de noeud doivent etre uniques et croissants dans la diapositive : une
    collision fait ignorer TOUT le bloc, sans le moindre message.
    """
    groupes, i = [], 3
    for entree in sequences:
        instructions = entree if isinstance(entree, list) else [entree]
        effets, formes_vues = [], []
        for instr in instructions:
            formes = instr[0]
            nom = instr[1] if len(instr) > 1 else "fondu"
            decalage = instr[2] if len(instr) > 2 else 150
            duree = instr[3] if len(instr) > 3 else 500
            sens = instr[4] if len(instr) > 4 else "entree"
            formes = [f for f in formes if f is not None]
            if not formes:
                continue
            preset, sub, filtre = _EFFETS.get(nom, _EFFETS["fondu"])
            gabarit = _EFFET if sens == "entree" else _EFFET_SORTIE
            for rang, f in enumerate(formes):
                premier = rang == 0 and not formes_vues
                effets.append(gabarit.format(
                    c=i, d=i + 1, e=i + 2,
                    node="clickEffect" if premier else "afterEffect",
                    delai=0 if premier else decalage,
                    preset=preset, sub=sub, filtre=filtre, duree=duree,
                    spid=f.shape_id))
                i += 3
            formes_vues.extend(formes)
        if not formes_vues:
            continue
        a, b = i, i + 1
        i += 2
        groupes.append(_GROUPE.format(a=a, b=b, effets="".join(effets)))
    if not groupes:
        return
    anc = slide.element.find(qn("p:timing"))
    if anc is not None:
        slide.element.remove(anc)
    slide.element.append(etree.fromstring(_TIMING.format(ns=nsdecls("p"),
                                                         groupes="".join(groupes))))
