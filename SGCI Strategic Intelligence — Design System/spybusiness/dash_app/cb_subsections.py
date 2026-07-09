# -*- coding: utf-8 -*-
"""
Rapprochement des lignes tarifaires CB vers des SOUS-SECTIONS, un niveau
sous les 9 sections canoniques BCEAO de `cb_sections` (I à IX).

Pourquoi ce module : la comparaison SGCI / concurrents au niveau de la
grande section (ex. Section I "Conditions générales du compte") mélange
des familles de tarifs hétérogènes que les documents sources, eux,
séparent clairement (ex. 1.1 "Ouverture de compte" vs 1.2 "Clôture de
compte" — deux gammes de prix sans rapport, noyées dans une médiane
commune). C'est exactement le type de problème structurel que le bug
"% vs F CFA" a révélé ailleurs dans le dashboard : un agrégat qui efface
une distinction réellement présente dans la donnée source.

Stratégie de classification — vérifiée empiriquement par requêtes directes
sur les ~2 900 lignes Particuliers 2026-S1 (les 6 banques à numérotation
fiable, BACI exclue comme dans `cb_sections`) :

Le champ `section` brut N'EST PAS exploitable pour la sous-section : sa
profondeur de numérotation diffère par banque (SGCI '1.1.1.1', BICICI
'1.1.1.1.', BNI/SIB regroupent parfois plusieurs sous-services sous un
même numéro). Le champ `contexte` (pipe-délimité) contient le bon
intitulé, mais PAS au même niveau de profondeur selon les banques (parfois
niveau 1 — ECOBANK "Conditions de clôture de compte" — parfois niveau 2 —
BNI "CONDITIONS D'OUVERTURE DE COMPTE | Ouverture de compte (...)").

→ Un split positionnel est donc impossible : la classification se fait
PAR CONTENU (regex sur texte normalisé), comme `cb_sections.classify_by_content`
le fait déjà pour BACI au niveau section — appliquée ici comme mécanisme
PRINCIPAL, un niveau plus bas. Aucun appel LLM (classification déterministe).

Cas particulier Section I — l'ambiguïté "ouverture et clôture" :
plusieurs banques (SGCI, BICICI, SIB) regroupent les deux sous une rubrique
ombrelle unique "Conditions d'ouverture ET de clôture de compte", de sorte
qu'une simple recherche plein-texte de "ouverture"/"clôture" sur le texte
combiné matche les DEUX mots à la fois et ne tranche rien. La fonction
`_ouverture_ou_cloture` résout ce cas en walkant les segments du plus
spécifique (libellé, puis derniers segments du contexte) vers le plus
générique, et retient le PREMIER segment qui ne mentionne qu'un seul des
deux mots — la classification réelle est toujours portée par l'intitulé le
plus profond/spécifique ("Conditions d'ouverture (...)" / "Comptes-jours" /
"Conditions de clôture du compte | Comptes-jours", etc.). Quand aucun
segment ne tranche (texte purement ombrelle + libellé neutre, ex. SGCI
contexte="Conditions d'ouverture et de clôture de compte" / libelle="Comptes
chèques"), la ligne n'est PAS forcée dans un des deux camps : elle tombe
dans "Types de comptes", un panier honnête plutôt qu'un classement inventé.
"""
import re
import unicodedata


_RE_CESURE = re.compile(r"(\w)-\s+(\w)")


def _norm(s):
    """minuscule + suppression des accents (même convention que cb_sections._norm),
    + recollage des césures de fin de ligne PDF ("ouvertu- res" -> "ouvertures"),
    sans quoi des regex comme \\bouvertur ratent des libellés réels (vérifié :
    29 lignes/2003 portent cet artefact d'extraction, ex. BICICI "Dépôts initiaux
    pour les ouvertu- res de compte" mal classé en "Types de comptes" sans ce fix)."""
    s = (s or "").lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return _RE_CESURE.sub(r"\1\2", s)


# ---------------------------------------------------------------------------
# Section I — traitement spécial Ouverture / Clôture (cf. docstring du module)
# ---------------------------------------------------------------------------
_RE_OUVERTURE = re.compile(r"\bouvertur")
_RE_CLOTURE = re.compile(r"\bclotur")
_RE_REOUVERTURE = re.compile(r"\breouvertur")

SUB_I_OUVERTURE = (101, "Ouverture de compte")
SUB_I_CLOTURE = (102, "Clôture de compte")
SUB_I_REOUVERTURE = (103, "Réouverture de compte")


def _ouverture_ou_cloture(libelle, contexte):
    """
    Tranche Ouverture / Clôture / Réouverture en examinant les segments du
    texte (libellé, puis contexte du plus profond au plus générique) un par
    un, et en retenant le premier qui ne mentionne qu'UN SEUL des deux mots.
    Renvoie None si aucun segment ne permet de trancher proprement (cf.
    docstring) — la ligne sera alors classée par les règles génériques de
    la section I (ex. "Types de comptes").
    """
    segments = [libelle or ""] + list(reversed((contexte or "").split("|")))
    for seg in segments:
        t = _norm(seg)
        if _RE_REOUVERTURE.search(t):
            return SUB_I_REOUVERTURE
        ouv = _RE_OUVERTURE.search(t)
        clo = _RE_CLOTURE.search(t)
        if ouv and not clo:
            return SUB_I_OUVERTURE
        if clo and not ouv:
            return SUB_I_CLOTURE
    return None


# ---------------------------------------------------------------------------
# Taxonomies par section canonique : { section_id: [(sub_id, libellé, [regex...]), ...] }
# Liste ORDONNÉE par section : la 1re règle qui matche l'emporte. Dernière
# entrée de chaque section = filet "Autres ..." (aucun regex, capte le reste).
# Vocabulaire dérivé des intitulés réels observés en base (requêtes directes
# par section, cf. investigation), avec la même tolérance à l'OCR que
# `cb_sections._FALLBACK_RULES` (motifs `\w*`/`.{0,n}` plutôt que mots stricts).
# ---------------------------------------------------------------------------
_TAXONOMY = {
    # I — Conditions générales du compte
    # Les 3 premières entrées (101-103) ne portent volontairement AUCUN regex :
    # elles sont toujours résolues en amont par `_ouverture_ou_cloture` (cf.
    # docstring du module). Elles figurent ici uniquement pour fixer l'ordre
    # d'affichage (Ouverture → Clôture → Réouverture, ordre du document
    # source) et pré-peupler l'agrégation de `cb_par_sous_section` avec les
    # bons identifiants/libellés — `classify_subsection` ne les atteindra
    # jamais par leurs règles (vides) pour la section I.
    1: [
        (101, "Ouverture de compte", []),
        (102, "Clôture de compte", []),
        (103, "Réouverture de compte", []),
        (105, "Frais par type de compte (compte joint, épargne, dépôt à terme...)", [
            r"\bcompte[s]?.?joint",
            r"\bcompte[s]? indivis",
            r"\bcompte[s]? courant",
            r"\bcompte[s]? (d.?)?epargne",
            r"\bdepot[s]? a terme",
            r"\bcompte[s]? a terme",
            r"\bcompte[s]? en devise",
            r"\bcompte[s]?.?jour",
            r"\bplan[s]? d.?epargne",
            r"\bautres? types? de comptes?",
            r"\bcompte[s]? cheques?\b",
            r"\bcomptes? d.?instruments? financier",
        ]),
        (106, "Conditions générales et dispositions du compte", [
            r"\bconditions? generale[s]?",
            r"\bdispositions? generale",
            r"\bchamp d.?application",
            r"\bconditions? (debitri|creditri)",
            r"\bgestion[s]? de compte",
            r"\btenue[s]? de compte",
            r"\bdroits? de tenue",
        ]),
    ],
    # II — Services rattachés au fonctionnement du compte
    2: [
        (201, "Cartes bancaires", [
            r"\bcarte[s]?\b",
        ]),
        (202, "Chèques et chéquiers", [
            r"\bcheque",
            r"\bcarnet",
            r"\bbarre\b",
        ]),
        (203, "Virements et prélèvements", [
            r"\bvirement",
            r"\bprelevement",
            r"\btransfert",
        ]),
        # 207 AVANT 204 : les libellés "Pack X" / "Package X" doivent matcher
        # en 1re passe sur le libellé seul, avant que le contexte parent
        # "Conditions débitrices" (en-tête de section) ne fasse basculer en 204.
        # SGCI range ses packs sous 2.1.1.2 sans intitulé "Frais de tenue" dans
        # le contexte → sans cette règle ils tombaient dans le panier par défaut.
        (207, "Frais de tenue de compte et packages", [
            r"\bpack[s]?\b",
            r"\bpackage[s]?\b",
            r"\btenue[s]? de compte",
            r"\bfrais de tenue",
            r"\bclient[s]? decede",
            r"\bcompte[s]?.{0,8}eco\b",
            r"\bivoiriens? residents? a l.?etranger",
        ]),
        # 208 AVANT 204 : intérêts créditeurs = taux/épargne, pas "conditions débitrices"
        (208, "Taux créditeurs et intérêts sur épargne", [
            r"\binteret[s]? crediteur",
            r"\btaux crediteur",
            r"\btombee[s]? anticipee",
            r"\bproduits? d.?epargne (contrac|salar|sim)",
            r"\bautres? depots? et produits? d.?epargne",
            r"\bplan.{0,8}epargne.{0,20}contrac",
        ]),
        (204, "Commissions et taux débiteurs (agios)", [
            r"\bconditions? debit",
            r"\bconditions? credit",
            r"\bdecouvert",
            r"\bagio",
            r"\bcommission.{0,20}mouvement",
            r"\btaux debiteur",
        ]),
        (205, "Relevés, attestations et RIB", [
            r"\breleve",
            r"\battestation",
            r"\b(rib)\b",
            r"\bidentite bancaire",
        ]),
        (206, "Gestion courante, procurations et services GAB/DAB", [
            r"\bgestion.{0,10}compte",
            r"\bopposition",
            r"\btimbre",
            r"\b(gab|dab)\b",
            r"\bdistributeur[s]? automatique",
            r"\bguichet[s]? automatique",
            r"\bmoyens? de paiement",
            r"\bprocuration",
            r"\bforcage",
        ]),
    ],
    # III — Services bancaires
    3: [
        (301, "Dates de valeur", [
            r"\bdates? de[s]? valeur",
            r"\btoute[s]? de valeur",
        ]),
        (302, "Frais de compensation", [
            r"\bcompensation",
        ]),
        (303, "Versements et retraits d'espèces", [
            r"\bversement[s]? (et|d.?)?(espece|retrait)",
            r"\bretrait[s]? d.?espece",
            r"\bdepot[s]? d.?espece",
        ]),
        (304, "Saisies, oppositions et avis à tiers détenteur (ATD)", [
            r"\bsaisie",
            r"\bavis a tiers detent",
            r"\b(atd)\b",
            r"\bopposition",
            r"\bincident sur le compte",
        ]),
        (305, "Frais généraux liés aux services bancaires", [
            r"\bfrais li[ée]s? aux services bancaires",
            r"\bservices? bancaires?\b",
            r"\bmodification[s]? d.?intitule",
            r"\bcarte[s]? bancaire",
            r"\bcheque",
        ]),
    ],
    # IV — Services de banque à distance
    4: [
        (401, "Banque en ligne, internet et mobile", [
            r"\bbanque[s]? en ligne",
            r"\bbanque[s]? par telephone",
            r"\bsite internet",
            r"\binternet",
            r"\bmobile",
            r"\bmessalia",
            r"\binfobank",
        ]),
        (402, "Alertes et notifications SMS", [
            r"\balerte",
            r"\bsms\b",
            r"\bavis de debit.{0,15}credit.{0,15}voie electronique",
        ]),
        (403, "Virements et prélèvements électroniques", [
            r"\bvirement",
            r"\bprelevement",
            r"\belectronique",
        ]),
        (404, "Solutions monétiques à distance (Sogecash, Swift, MT940...)", [
            r"\bsogecash",
            r"\bsogecommerce",
            r"\bglobal cash",
            r"\bswift",
            r"\bmt9\d{2}",
            r"\bsftp\b",
            r"\btelechargement[s]? de fichiers? web",
            r"\btelet?ransmission",
            r"\bsiam\b",
        ]),
        (405, "Location de coffre-fort et services annexes", [
            r"\bcoffre",
            r"\benregistrement",
        ]),
    ],
    # V — Gestion des incidents de paiement
    5: [
        (501, "Chèques impayés, rejets et incidents", [
            r"\brejet",
            r"\bcheques? sans provision",
            r"\bcheques? en souffrance",
            r"\bincident",
            r"\bcertificat[s]? de non.?paiement",
        ]),
        (502, "Oppositions et déclarations (CIP, Banque Centrale)", [
            r"\bopposition",
            r"\bdeclaration[s]? d.?opposition",
            r"\bmainlevee",
            r"\bcip\b",
            r"\binjonction",
        ]),
        (503, "Lettres de relance, d'information et avis", [
            r"\blettre",
            r"\bavis (de sort|avant rejet)",
            r"\binformation[s]? prealable",
        ]),
        (504, "Comptes débiteurs et découverts non autorisés", [
            r"\bcompte[s]? debiteur",
            r"\bdecouvert",
            r"\bfrais fixes? d.?impaye",
        ]),
    ],
    # VI — Opérations de change
    6: [
        (601, "Achat et vente de devises et billets de banque", [
            r"\bachat",
            r"\bvente",
            r"\bdevise",
            r"\bbillet[s]? de banque",
            r"\beuro",
        ]),
        (602, "Chèques de voyage", [
            r"\bcheques? de voyage",
        ]),
        (603, "Commissions et cours de change", [
            r"\bcommission[s]? de change",
            r"\bcours de change",
        ]),
        (604, "Opérations sur titres, placements et bons de caisse", [
            r"\btitres?\b",
            r"\bopcvm",
            r"\bbourse",
            r"\bmarche (financier|primaire|secondaire)",
            r"\bbons? de caisse",
            r"\bportefeuille",
            r"\bplacement",
            r"\bepargne salariale",
            r"\bsouscription",
            r"\bcommission[s]? de (gestion|conservation|structuration|placement)",
            r"\bintroduction en bourse",
        ]),
    ],
    # VII — Opérations de crédit
    7: [
        (701, "Découverts et avances de trésorerie", [
            r"\bdecouvert",
            r"\bavance[s]? sur",
            r"\bcredit[s]? de tresorerie",
            r"\brappel\b",
        ]),
        (702, "Crédits à la consommation, à l'habitat et crédit-bail", [
            r"\bcredit[s]? a la consommation",
            r"\bcredit[s]? conso",
            r"\bcredit[s]? a l.?habitat",
            r"\bcredit.?bail",
            r"\bcredit express",
        ]),
        (703, "Cautions, avals et garanties", [
            r"\bcaution",
            r"\baval",
            r"\bgarantie",
            r"\bobligations? cautionnee",
            r"\bassurance[s]?.{0,20}(emprunteur|prets?)",
            r"\bhypotheque",
        ]),
        (704, "Frais de dossier, d'engagement et de gestion du contrat", [
            r"\bfrais de dossier",
            r"\bmodification[s]?",
            r"\bavenant",
            r"\betat[s]? d.?engagement",
            r"\bcommission[s]? d.?engagement",
            r"\btableau[x]? d.?amortissement",
            r"\banticipation",
            r"\bimpaye[s]?.{0,15}remboursement",
            r"\boperations? connexes? (aux|de) (operation[s]? de )?credit",
        ]),
        (705, "Escompte et mobilisation de créances", [
            r"\bescompte",
            r"\bmobilisation",
            r"\beffets? de commerce",
        ]),
    ],
    # VIII — Opérations avec l'étranger
    8: [
        (801, "Transferts et virements internationaux (UEMOA, hors UEMOA, SWIFT)", [
            r"\btransfert",
            r"\bvirement",
            r"\bswift",
            r"\bzone[s]? uemoa",
            r"\bhors uemoa",
            r"\bhors compensation regionale",
        ]),
        (802, "Chèques et effets reçus ou émis de/vers l'étranger", [
            r"\bcheque",
            r"\beffet",
        ]),
        (803, "Crédits documentaires et remises documentaires", [
            r"\bcredit documentaire",
            r"\bremise documentaire",
            r"\bcredoc",
            r"\bnotification de credit",
            r"\bacceptation",
            r"\bdomiciliation",
        ]),
        (804, "Crédits, garanties et opérations connexes au financement", [
            r"\bcredit[s]? (de tresorerie|de mobilisation|par signature|-bail|bancaire)",
            r"\bcrechere",
            r"\bcommission[s]? d.?engagement",
            r"\boperations? connexes? .{0,25}credit",
            r"\bavenant",
            r"\bmainlevee",
            r"\bmodification",
            r"\btableau[x]? d.?amortissement",
            r"\bfrais[s]? (fixe[s]? )?d.?impaye",
        ]),
        (805, "Frais d'encaissement, de manipulation et d'envoi (courrier, DHL...)", [
            r"\bfrais d.?encaissement",
            r"\bfrais de manipulation",
            r"\bfrais de port de lettre",
            r"\bfrais d.?envoi",
            r"\bcourrier",
            r"\bavis de sort",
        ]),
    ],
    # IX — Autres services
    9: [
        (901, "Successions, actes et garanties", [
            r"\bsuccession",
            r"\bacte[s]? \(?garantie",
            r"\binscription[s]? des garanties",
            r"\benregistrement",
        ]),
        (902, "Coffres-forts et recherche de documents", [
            r"\bcoffre",
            r"\brecherche[s]? de document",
            r"\breproduction de cle",
            r"\bcopie de document",
            r"\bautres documents demande",
        ]),
        (906, "Demandes de renseignements et attestations", [
            r"\bdemande[s]? de renseignement",
            r"\battestation",
            r"\bcommissaire[s]? aux comptes",
            r"\boperations? diverses de secretariat",
            r"\brenseignement[s]? (commerciau|sur|financier|comptable)",
            r"\bfrais juridique",
        ]),
        (907, "Opérations documentaires et lettres de crédit (SBLC...)", [
            r"\boperations? documentaire",
            r"\blettre[s]? de credit",
            r"\bsblc\b",
            r"\bstand by letter",
            r"\bcredit documentaire",
            r"\bremise documentaire",
        ]),
        (903, "Comptes inactifs, saisies et oppositions administratives", [
            r"\bcompte[s]? inactif",
            r"\bsaisie",
            r"\bopposition[s]? administrative",
            r"\b(atd)\b",
            r"\bavis a tiers detention",
            r"\bsaisie.?arret",
            r"\bsaisie.?attribution",
        ]),
        (904, "Opérations sur titres, OPCVM et placements", [
            r"\btitres?\b",
            r"\bopcvm",
            r"\bbourse",
            r"\bfcp\b",
            r"\bplacement",
            r"\bportefeuille",
            r"\bmarche (financier|primaire|secondaire)",
            r"\bconservation",
        ]),
        (905, "Opérations de change et transferts en devises (autres services)", [
            r"\bdevise",
            r"\bvirement en (euro|autre)",
            r"\bcheque[s]? (de banque )?en (euro|autre devise)",
            r"\beuro\b",
        ]),
    ],
}

# Filet de sécurité si une section canonique n'a pas (encore) de taxonomie dédiée
_DEFAULT_SUBSECTION = {
    1: (109, "Autres opérations sur le compte"),
    2: (209, "Autres services rattachés au compte"),
    3: (309, "Autres services bancaires"),
    4: (409, "Autres services de banque à distance"),
    5: (509, "Autres frais liés aux incidents de paiement"),
    6: (609, "Autres opérations de change"),
    7: (709, "Autres opérations de crédit"),
    8: (809, "Autres opérations avec l'étranger"),
    9: (909, "Autres services divers"),
}

_COMPILED_TAXONOMY = {
    sid: [(sub_id, label, [re.compile(p) for p in patterns]) for sub_id, label, patterns in rules]
    for sid, rules in _TAXONOMY.items()
}


def classify_subsection(section_id, libelle=None, contexte=None):
    """
    Détermine la sous-section (id:int, libellé:str) d'une ligne tarifaire au
    sein de sa section canonique BCEAO.

    Ordre de recherche (du plus spécifique au plus générique) :
      1) Section I uniquement : tranchage spécial Ouverture/Clôture/Réouverture
         (cf. `_ouverture_ou_cloture` et docstring du module)
      2) Règles de la taxonomie contre le LIBELLÉ seul
      3) Segments du contexte du plus spécifique (profond) au plus générique :
         ex. pour un item BICICI "Package STARTER" dont le contexte pipe est
         "Conditions débitrices et frais | Frais de tenue de compte | Tarifs mensuels",
         on examine d'abord "Tarifs mensuels", puis "Frais de tenue de compte"
         (→ match rule 206 "tenue de compte"), puis "Conditions débitrices"
         (→ match rule 204) — le premier match gagne. Sans ce tri, la règle 204
         "conditions débitrices" capture tous les sous-items de tenue de compte
         BICICI avant même d'atteindre l'intitulé spécifique "Frais de tenue".
      4) Filet "Autres ..." de la section
    """
    if section_id == 1:
        special = _ouverture_ou_cloture(libelle, contexte)
        if special is not None:
            return special

    rules = _COMPILED_TAXONOMY.get(section_id)
    if not rules:
        return _DEFAULT_SUBSECTION.get(section_id, (0, "Non classé"))

    lib_text = _norm(libelle)

    # Pass 1 : libellé seul — signal le plus précis, immunisé aux en-têtes parents
    for sub_id, label, patterns in rules:
        for pat in patterns:
            if pat.search(lib_text):
                return sub_id, label

    # Pass 2 : segments du contexte du plus spécifique au plus générique,
    # puis libellé en dernier filet (garantit la complétude sans recombiner
    # les niveaux hiérarchiques dans un seul texte qui ferait gagner le niveau
    # le plus haut dès que ses mots-clés apparaissent dans les règles).
    for seg in list(reversed((contexte or "").split("|"))) + [libelle or ""]:
        seg_text = _norm(seg)
        if not seg_text.strip():
            continue
        for sub_id, label, patterns in rules:
            for pat in patterns:
                if pat.search(seg_text):
                    return sub_id, label

    return _DEFAULT_SUBSECTION.get(section_id, (0, "Non classé"))


def all_subsections(section_id):
    """[(id, libellé), ...] dans l'ordre de priorité de classification."""
    return [(sub_id, label) for sub_id, label, _ in _TAXONOMY.get(section_id, [])]
