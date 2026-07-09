# -*- coding: utf-8 -*-
"""
Rapprochement des lignes tarifaires CB vers les 9 sections canoniques du
référentiel BCEAO "Conditions Générales de Banque" (I à IX), commun aux
7 banques de Côte d'Ivoire (confirmé par lecture intégrale des brochures
SGCI et ECOBANK + vérification croisée des en-têtes des 7 banques en base).

Les 9 sections canoniques :
  I    Conditions générales du compte
  II   Services rattachés au fonctionnement du compte
  III  Services bancaires
  IV   Services de banque à distance
  V    Gestion des incidents de paiement
  VI   Opérations de change
  VII  Opérations de crédit
  VIII Opérations avec l'étranger
  IX   Autres services

Stratégie de classification — HYBRIDE, validée empiriquement sur les
~2 900 lignes tarifaires Particuliers 2026-S1 :

1) PRIORITÉ : le numéro de tête du champ `section` brut.
   Vérification croisée ligne par ligne des en-têtes de section de BICICI,
   BNI, ECOBANK, NSIA, SGCI et SIB : le premier chiffre de `section`
   correspond EXACTEMENT au numéro de la section canonique (1=I … 9=IX)
   dans 100% des cas observés (ex. NSIA section '5' = en-tête littéral
   "GESTION DES INCIDENTS DE PAIEMENTS" = canon V). C'est la numérotation
   du document lui-même : plus fiable que toute heuristique.

2) SECOURS (uniquement BACI, et toute ligne au format de section invalide) :
   classification par CONTENU (libellé + contexte) via un vocabulaire
   dérivé de la lecture directe des brochures. BACI est la seule banque
   dont la numérotation interne ne suit PAS la trame BCEAO (elle ne
   dépasse pas '4' et ses titres de tête ne correspondent à aucune
   section canonique — numérotation propre à son document).
"""
import re
import unicodedata

# ---------------------------------------------------------------------------
# Les 9 sections canoniques (ordre = numérotation BCEAO officielle I à IX)
# ---------------------------------------------------------------------------
CANONICAL_SECTIONS = [
    (1, "I",    "Conditions générales du compte"),
    (2, "II",   "Services rattachés au fonctionnement du compte"),
    (3, "III",  "Services bancaires"),
    (4, "IV",   "Services de banque à distance"),
    (5, "V",    "Gestion des incidents de paiement"),
    (6, "VI",   "Opérations de change"),
    (7, "VII",  "Opérations de crédit"),
    (8, "VIII", "Opérations avec l'étranger"),
    (9, "IX",   "Autres services"),
]
SECTION_ROMAN = {n: roman for n, roman, _ in CANONICAL_SECTIONS}
SECTION_TITLE = {n: title for n, _, title in CANONICAL_SECTIONS}

# Numérotation de section brute = fiable et alignée sur le canon BCEAO
# pour BICICI (vérifié ligne par ligne : 1=I … 9=IX, alignement parfait).
_BANKS_RELIABLE_NUMBERING = {"BICICI"}

# BNI, ECOBANK, NSIA et SGCI partagent une anomalie identique : un chapitre
# SUPPLÉMENTAIRE en position 6 ("Opérations sur titres" / "Frais de tenue et
# de gestion / Épargne salariale" — absent du référentiel BCEAO), qui décale
# tous les chapitres suivants d'un cran (vérifié ligne par ligne sur 2026-S1-E) :
#   chapitre 6 = hors-BCEAO (mixte : tenue de compte / titres / épargne)
#   chapitre 7 = Opérations de change   → BCEAO VI
#   chapitre 8 = Opérations de crédit   → BCEAO VII
#   chapitre 9 = Opérations à l'étranger→ BCEAO VIII
#   chapitre 10 = Autres services       → BCEAO IX
# Les chapitres 1-5 restent alignés 1:1 avec le canon (vérifié également).
#
# IMPORTANT : on corrige via la POSITION du chapitre (chiffre de tête), pas via
# le contenu — le champ `contexte` de ces banques contient parfois du texte
# parasite (cellules voisines mal alignées par l'extraction PDF, ex. "achat et
# vente de billets de banque" affublé d'un contexte "injonction" ou "bons de
# caisse"), ce qui pollue `classify_by_content`. La position de chapitre, elle,
# reflète fidèlement la structure réelle du document — bien plus fiable ici.
_BANKS_SHIFTED_NUMBERING = {
    "BNI":     {7: 6, 8: 7, 9: 8, 10: 9},
    "ECOBANK": {7: 6, 8: 7, 9: 8, 10: 9},
    "NSIA":    {7: 6, 8: 7, 9: 8, 10: 9},
    "SGCI":    {7: 6, 8: 7, 9: 8, 10: 9},
}

_SECTION_PREFIX_RE = re.compile(r"^([1-9])(?:[.\s]|$)")
# Capture le numéro de CHAPITRE (1 ou 2 chiffres, ex. '10.3' → 10) pour les
# banques à numérotation décalée — nécessaire pour distinguer chapitre 1 vs 10.
_SECTION_CHAPTER_RE = re.compile(r"^(\d{1,2})(?:[.\s]|$)")


def _norm(s):
    """minuscule + suppression des accents + collapse espaces + apostrophes canoniques.
    Robustesse OCR : supprime le tiret-mou (U+00AD) qui peut se glisser dans
    le texte OCR sans être visible."""
    s = (s or "").replace("­", "")  # soft hyphen invisible
    s = s.lower()
    s = s.replace("’", "’").replace("‘", "’")  # apostrophes typographiques → droites
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Vocabulaire de secours par contenu (utilisé pour BACI + lignes orphelines).
# Liste ordonnée (id_section, [regex...]) : la 1re règle qui matche l'emporte.
# Ordre = du jargon le plus spécifique (sections à vocabulaire propre :
# autres services, incidents, change, étranger, crédit, distance) vers le
# plus générique (conditions générales, services bancaires, rattachés).
# Pas de '\b' final sur les motifs multi-mots : l'OCR colle parfois les
# libellés ("...banqueAchat Euros...") et la frontière de mot disparaît.
# ---------------------------------------------------------------------------
_FALLBACK_RULES = [
    (9, [
        r"\brecherche[s]? de document",
        r"\bcoffre[s]?.?fort",
        r"\bsuccession",
        r"\bacte[s]? \(?garantie",
        r"\benregistrement.{0,10}droit",   # frais notariaux/fiscaux (droit simple, hors délai)
        r"\bquietis\b",                     # produit d'assurance SG (QUIETIS Plus)
        r"\bcompte[s]? inactif",
        r"\bautres? types? de service",
        r"\bsaisie[s]? conservatoire",
        r"\bavis a tiers detention",
        r"\bopposition[s]? administrative",
        r"\bsaisie.?arret",
        r"\bsaisie.?attribution",
        r"\bdemande[s]? de renseignement",
        r"\breproduction de cle",
        r"\btitres?\b.{0,15}(opcvm|bourse|marche financier)",
        # Section "Opérations sur titres" présente chez BNI, ECOBANK, NSIA, SGCI
        # (section 6 hors-BCEAO) — classée IX faute de section dédiée dans le référentiel
        r"\boperations? sur titres",
        r"\bvaleurs? mobilieres",
        r"\bactions? (et|ou|/) oblig",
        r"\bconservation.{0,15}titres",
        r"\bepargne salariale",
        r"\breleve[s]?.{0,8}titres",
        r"\bbon[s]? de caisse\b",
        r"\bmarche (primaire|secondaire)",
        r"\bbrvm\b",                        # Bourse Régionale des Valeurs Mobilières
    ]),
    (5, [
        r"\bincidents? de paiement",
        r"\bopposition[s]?.{0,30}banque centrale",
        r"\bdeclaration[s]? d.?opposition",
        r"\bmainlevee[s]? d.?opposition",
        r"\brejet[s]?.{0,15}cheque",
        r"\blettre[s]? de relance",
        r"\bcompte[s]? debiteur",
        r"\binjonction",
        r"\bcertificat[s]? de non.?paiement",
        r"\bdeclaration[s]?.{0,10}cip\b",
        r"\bcheque[s]?.{0,15}sans provision",
        r"\binformation[s]? prealable[s]? au rejet",
        r"\blettre[s]? d.?incident",
        r"\bavis avant rejet",
        r"\bcheques? en souffrance",
        r"\bavis de sort",
        r"\bfrais fixes? d.?impaye",
    ]),
    (6, [
        r"\boperations? de change",
        r"\bachat[s]? et vente[s]? de devises",
        r"\bachat[s]? et vente[s]? de billets? de banque",
        r"\bcheques? de voyage",
        r"\bcommission[s]? de change",
        r"\bcours de change",
    ]),
    (8, [
        r"\boperations? avec l.?etranger",
        r"\bzone[s]? uemoa",
        r"\btransferts? (emis|recus)",
        r"\bswift",
        r"\bcheques?.{0,20}payable.{0,20}etranger",
        r"\bcheques? et effets.{0,20}etranger",
        r"\bemission.{0,20}cheque[s]? de banque.{0,20}etranger",
        r"\bencaissement.{0,20}etranger",
        r"\bcheques? recus de l.?etranger",
        r"\bcheques? emis (a|vers) l.?etranger",
        r"\bhors compensation regionale",
        r"\bdomiciliation[s]? recettes? d.?(export|import)",
    ]),
    (7, [
        r"\boperations? de credit",
        r"\bcredit[s]? a (la consommation|l.?habitat)",
        r"\bcredit.?bail",
        r"\bdecouvert",
        r"\bavance[s]? sur",
        r"\btaux d.?interet",
        r"\b(mtd|teg)\b",
        r"\bassurance[s]?.{0,20}emprunteur",
        r"\bcaution[s]?\b",
        r"\baval[s]?\b",
        r"\bescompte",
        r"\bobligations? cautionnee",
        r"\bfrais de dossier\b",  # IX (succession) est vérifiée en priorité plus haut
        r"\boperations? connexes? aux credits",  # "Autres opérations connexes aux crédits"
        r"\btableau d.?amortissement",           # document de crédit
    ]),
    (4, [
        r"\bbanque[s]? a distance",
        r"\bbanque[s]? en ligne",
        r"\bbanque[s]? par telephone",
        r"\bvoie electronique",
        r"\bvirement[s]? electronique",
        r"\binfobank",
        r"\bmessalia",
        r"\balerte[s]?( sms)?\b",
        r"\bservices? sms\b",
        r"\bmobile ?banking",
        r"\bsite internet\b",
        r"\btelechargement[s]? de fichiers? web",
    ]),
    (1, [
        r"\bouverture[s]? de compte",
        r"\bcloture[s]? de compte",
        r"\bcompte[s]? courant",
        r"\bcompte[s]? (d.?)?(a vue|cheques?|epargnes?|joints?|indivis|de depot a terme)\b",
        r"\bconditions? generale[s]?.{0,15}(du|des) compte",
        r"\bconditions? d.?ouverture",
        r"\bchamp d.?application",
        r"\bdispositions? generale[s]?\b",
    ]),
    (3, [
        r"\bdates? de valeur",
        r"\bfrais lies aux services bancaires",
        r"\bmodification[s]? d.?intitule",
        r"\bservices? bancaires\b",
        r"\bdepot[s]? d.?especes",
    ]),
    (2, [
        r"\bgestion[s]? de compte",
        r"\btenue[s]? de compte",
        r"\breleves? de compte",
        r"\battestation",
        r"\bchequier",
        r"\bcarte[s]? (bancaire|visa|national|classique|basic)",
        r"\bvirement",
        r"\bprelevement",
        r"\bmoyens? de paiement",
        r"\b(rib|gab|dab)\b",
        r"\bopposition[s]? (sur|carte|chequier)",
        r"\bservices? rattaches?",
        r"\btimbre",
    ]),
]
_DEFAULT_SECTION = 2
_COMPILED_FALLBACK = [(sec_id, [re.compile(p) for p in patterns]) for sec_id, patterns in _FALLBACK_RULES]

# Règles testées sur le libellé seul, AVANT le test contexte+libellé.
# Empêche le contexte de contaminer la classification quand le libellé
# est lui-même suffisamment spécifique (ex. "attestation" → II même si le
# contexte contient "Caution sur marche" qui déclencherait VII).
_LIBELLE_PRIORITY_RULES = [
    (3, [r"\bdates? de valeur"]),          # III avant VIII (contexte "chèques étranger")
    (6, [                                   # VI — produits de change non ambigus : chez
         r"\boperations? de change\b",      # BNI/ECOBANK/NSIA/SGCI/SIB le `contexte` de
         r"\bachat[s]? et vente[s]? de (billets? de banque|devises)",  # ces lignes est
         r"\bcheques? de voyage",           # souvent du texte parasite sans rapport
         r"\bcommission[s]? de change",     # (ex. "Succession") qui ferait basculer en
         r"\bcours de change"]),            # IX/VII via classify_by_content — le libellé,
                                             # lui, est un signal stable et univoque.
    (9, [                                   # IX — "Opérations sur titres" : produit hors
         r"\boperations? sur titres",       # référentiel BCEAO (chapitre 6 supplémentaire
         r"\bvaleurs? mobilieres",          # chez ces mêmes banques), donc toujours classé
         r"\bcomptes? titres?\b",           # IX quel que soit son n° de chapitre — qui en
         r"\bnantissement.{0,12}titres?",   # plus VARIE d'une édition à l'autre (vu SGCI :
         r"\bmain ?levee.{0,15}titres?",    # 6.4.x / 7.4.x / 9.7.4.x pour le même produit).
         r"\b(vente|achat|placement|transfert|conservation|garde|certificat).{0,15}(de )?titres?\b",
         r"\battestation.{0,12}titres?",    # doit primer sur la règle "attestation"→II
         r"\bepargne salariale",
         r"\bbon[s]? de caisse\b",
         r"\bbrvm\b"]),
    (7, [r"\bcaution\b"]),                  # VII avant IX (contexte "coffre-fort")
    (5, [r"\binjonction\b"]),               # V avant IX (contexte "saisie-arrêt")
    (2, [r"\battestation\b",               # II avant VII (contexte "Caution sur marche")
         r"\bconfirmation bancaire",
         r"\breleve[s]? d.?identite"]),
]
_COMPILED_LIBELLE_PRIORITY = [
    (sec_id, [re.compile(p) for p in patterns])
    for sec_id, patterns in _LIBELLE_PRIORITY_RULES
]


def classify_by_content(libelle, contexte=None):
    """
    Classification de SECOURS par contenu (libellé + contexte), sans
    dépendre du champ `section`. Utilisée pour BACI (numérotation interne
    non conforme à la trame BCEAO) et toute ligne au champ `section`
    invalide/manquant.

    Retourne (id:int 1-9, roman:str 'I'-'IX', titre:str).
    """
    lib_text  = _norm(libelle or "")
    full_text = _norm(f"{contexte or ''} | {libelle or ''}")
    # Phase 1 : libellé seul — le libellé prime sur le contexte pour les
    # patterns ci-dessus (évite les contaminations cross-section).
    for sec_id, patterns in _COMPILED_LIBELLE_PRIORITY:
        for pat in patterns:
            if pat.search(lib_text):
                return sec_id, SECTION_ROMAN[sec_id], SECTION_TITLE[sec_id]
    # Phase 2 : contexte + libellé combinés
    for sec_id, patterns in _COMPILED_FALLBACK:
        for pat in patterns:
            if pat.search(full_text):
                return sec_id, SECTION_ROMAN[sec_id], SECTION_TITLE[sec_id]
    return _DEFAULT_SECTION, SECTION_ROMAN[_DEFAULT_SECTION], SECTION_TITLE[_DEFAULT_SECTION]


def canonical_section(banque, section, libelle=None, contexte=None):
    """
    Détermine la section canonique BCEAO (1-9 / I-IX) d'une ligne tarifaire.

    - BICICI : numérotation document = canon BCEAO, alignement parfait 1:1
      (vérifié ligne par ligne) → 1er chiffre du `section` brut fait foi.
    - BNI, ECOBANK, NSIA, SGCI : chapitres 1-5 alignés sur le canon, mais un
      chapitre SUPPLÉMENTAIRE en position 6 (hors BCEAO) décale 7→VI, 8→VII,
      9→VIII, 10→IX d'un cran → on corrige via `_BANKS_SHIFTED_NUMBERING`
      (position du chapitre = fiable ; le `contexte` de ces banques contient
      parfois du texte parasite qui pollue la classification par contenu).
    - BACI, SIB (numérotation interne non conforme au canon BCEAO) ou toute
      ligne dont le `section` est invalide/manquant ou tombe dans le chapitre
      supplémentaire : classification par contenu `classify_by_content`.

    Retourne (id:int 1-9, roman:str 'I'-'IX', titre:str).
    """
    if banque in _BANKS_RELIABLE_NUMBERING and section:
        m = _SECTION_PREFIX_RE.match(section.strip())
        if m:
            sec_id = int(m.group(1))
            return sec_id, SECTION_ROMAN[sec_id], SECTION_TITLE[sec_id]

    if banque in _BANKS_SHIFTED_NUMBERING:
        if section:
            m = _SECTION_CHAPTER_RE.match(section.strip())
            if m:
                chapter = int(m.group(1))
                if 1 <= chapter <= 5:
                    # Chapitres 1-5 : alignement direct 1:1 sur le canon BCEAO,
                    # numérotation stable entre éditions → position fait foi.
                    return chapter, SECTION_ROMAN[chapter], SECTION_TITLE[chapter]
                # Chapitres 6+ : numérotation instable entre éditions (ex. SGCI 2024
                # vs 2026 : crédit↔change permutent leurs n° de chapitre).
                # Pour les produits au libellé non ambigu, le libellé prime donc
                # sur la position de chapitre — signal plus stable que le n° brut.
                lib_text = _norm(libelle or "")
                for sec_id, patterns in _COMPILED_LIBELLE_PRIORITY:
                    for pat in patterns:
                        if pat.search(lib_text):
                            return sec_id, SECTION_ROMAN[sec_id], SECTION_TITLE[sec_id]
                remap = _BANKS_SHIFTED_NUMBERING[banque]
                if chapter in remap:
                    sec_id = remap[chapter]
                    return sec_id, SECTION_ROMAN[sec_id], SECTION_TITLE[sec_id]
                # chapitre 6 = chapitre supplémentaire hors-BCEAO (mixte tenue/titres/
                # épargne) → pas de correspondance directe, classification par contenu
        else:
            # Pas de section : libellé-priority en premier, puis fallback contenu
            lib_text = _norm(libelle or "")
            for sec_id, patterns in _COMPILED_LIBELLE_PRIORITY:
                for pat in patterns:
                    if pat.search(lib_text):
                        return sec_id, SECTION_ROMAN[sec_id], SECTION_TITLE[sec_id]

    return classify_by_content(libelle, contexte)


def section_id_to_roman(sec_id):
    return SECTION_ROMAN.get(sec_id, "?")


def section_id_to_title(sec_id):
    return SECTION_TITLE.get(sec_id, "")


def all_sections():
    """[(id, roman, titre), ...] dans l'ordre canonique I → IX."""
    return list(CANONICAL_SECTIONS)
