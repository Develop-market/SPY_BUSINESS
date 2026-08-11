# -*- coding: utf-8 -*-
"""
securite.py — Authentification, rôles et traçabilité
=====================================================
ÉCRIT LE 2026-08-07, après un audit du dispositif existant.

CE QU'IL Y AVAIT AVANT, ET POURQUOI CE N'ÉTAIT PAS UNE SÉCURITÉ

L'application affichait une page de connexion. La vérification se faisait dans app.main.js :

    const validPass = (pass === "spybusiness2026");

Trois conséquences, toutes vérifiées avant d'écrire ce module :

  1. Le mot de passe était EN CLAIR dans un fichier servi à tout visiteur. Un clic droit sur
     « afficher le code source » suffisait à le lire.
  2. Aucun contrôle côté serveur : les 21 endpoints /api/* répondaient à n'importe quelle
     requête, sans identifiant. Interrogés en curl toute une nuit, ils ont tous répondu 200.
  3. La porte se franchissait depuis la console du navigateur en appelant _gateUnlock().

Autrement dit, la page de connexion était un décor. Quatre endpoints d'ÉCRITURE
(/api/ajout/extraire, /api/ajout/stocker, /api/ajout/logo, /api/rafraichir_analyses)
étaient ouverts : quiconque atteignait le port pouvait injecter des données dans la base
d'analyse. Pour un outil dont toute la valeur tient à la fiabilité de ses chiffres, c'est le
risque le plus grave de la liste.

CE QUE FAIT CE MODULE

  CONFIDENTIALITÉ  L'authentification est vérifiée par le SERVEUR, contre une empreinte
                   stockée en base. Le mot de passe n'existe nulle part en clair — ni dans
                   le code, ni dans la base, ni dans les journaux.
  INTÉGRITÉ        Hachage scrypt (paramètres par défaut de werkzeug : N=32768, r=8, p=1),
                   avec SEL ALÉATOIRE par utilisateur intégré à l'empreinte. Deux comptes
                   partageant le même mot de passe n'ont pas la même empreinte — c'est
                   précisément l'objet du sel, et cela rend les tables arc-en-ciel inutiles.
  DISPONIBILITÉ    Limitation des tentatives : au-delà d'un seuil, le compte est temporisé.
                   Une attaque par force brute ne peut ni aboutir ni saturer le service.
  TRAÇABILITÉ      Chaque connexion, chaque refus et chaque écriture sont journalisés en base
                   avec l'horodatage, l'identifiant et l'adresse d'origine.

POURQUOI POSTGRESQL ET NON UN FICHIER

Les comptes vivent dans la même base que les données métier : une sauvegarde de la base
sauvegarde les comptes, et les droits d'accès au serveur PostgreSQL protègent les deux. Un
fichier JSON à côté du code aurait suivi le dépôt — donc le mot de passe aussi.
"""
import datetime
import os
import secrets
import threading

import db

# ── RÔLES ────────────────────────────────────────────────────────────────────────────
# Deux rôles suffisent, et deux rôles se défendent. En inventer davantage sans que le
# métier les distingue produit une hiérarchie décorative : la question n'est pas combien de
# rôles existent, mais quelle décision chacun autorise.
#
#   LECTURE   consulter les tableaux de bord et interroger l'assistant. C'est le directeur
#             qui lit une note : il ne modifie rien.
#   EDITION   tout ce que permet LECTURE, plus l'ajout de données (dépôt de grilles
#             tarifaires, d'états financiers, de textes réglementaires) et la régénération
#             des analyses. C'est le seul rôle qui peut changer ce que l'application affirme.
#
# ADMIN existe pour la gestion des comptes eux-mêmes, et hérite d'EDITION.
LECTURE, EDITION, ADMIN = "lecture", "edition", "admin"
ROLES = (LECTURE, EDITION, ADMIN)
# Qui peut écrire dans la base d'analyse.
ROLES_ECRITURE = (EDITION, ADMIN)

# Longueur minimale d'un mot de passe. Huit caractères est un plancher, pas une cible : c'est
# le minimum en deçà duquel une attaque hors ligne sur l'empreinte devient rapide, même avec
# scrypt. La temporisation après cinq échecs protège l'accès en ligne ; elle ne protège pas
# une empreinte volée. Un mot de passe long reste la meilleure défense.
LONGUEUR_MIN = 8

# ── DROITS PAR SECTION ───────────────────────────────────────────────────────────────
# Demande du directeur (2026-08-07) : « l'admin choisit l'utilisateur a accès à quoi et n'a
# pas accès à quoi ». Deux rôles ne suffisaient pas à cela — ils disent ce qu'on peut FAIRE
# (lire, écrire), pas SUR QUOI. Un directeur du marketing n'a aucune raison de consulter le
# détail des états financiers, et un stagiaire encore moins l'assistant qui interroge toute
# la base.
#
# Les droits sont donc attribués SECTION PAR SECTION, et par utilisateur. Les clés reprennent
# exactement les onglets de l'application : ce que l'administrateur coche est ce que
# l'utilisateur voit.
SECTIONS = {
    "apercu":    "Santé financière",
    "analyse":   "Analyse",
    "cb":        "Benchmark concurrentiel",
    "strategie": "Stratégie",
    "stratop":   "Stratégie opérationnelle",
    "chat":      "Assistant conversationnel",
    "ajout":     "Ajouter des données",
    "admin":     "Administration",
}

# ── DIRECTIONS VISIBLES DANS LA STRATÉGIE OPÉRATIONNELLE ─────────────────────────────
# Demande du directeur (2026-08-11) : un droit sur l'onglet ne suffit plus. La Direction des
# Risques doit voir ses quatre directives, pas les vingt — celles des autres directions ne la
# concernent pas, et les lui montrer dilue précisément ce qu'on lui demande de faire.
#
# Le filtrage est appliqué PAR LE SERVEUR, qui ne renvoie que les directions autorisées. Le
# masquer côté navigateur laisserait les vingt cartes transiter dans la réponse : il suffirait
# d'ouvrir les outils de développement pour lire celles des autres.
#
# Un compte sans aucune de ces cases cochées voit TOUTES les directions : c'est le cas de la
# Direction Générale, et c'est le comportement d'avant cette évolution — ne rien cocher ne
# doit jamais restreindre par surprise un compte créé auparavant.
DIRECTIONS_STRATOP = {
    "dir_fin": "Direction Financière",
    "dir_com": "Direction Commerciale",
    "dir_mkt": "Direction Marketing",
    "dir_inn": "Direction Innovation",
    "dir_ris": "Direction des Risques",
}

# Les directions rejoignent les sections cochables : l'écran d'administration les affiche donc
# sans modification, et un droit reste un droit, quelle que soit sa finesse.
SECTIONS.update(DIRECTIONS_STRATOP)

# Ce qu'un compte reçoit à sa création, selon son rôle. L'administrateur peut ensuite affiner.
_BASE_LECTURE = ["apercu", "analyse", "cb", "strategie", "stratop", "chat"]
DROITS_PAR_DEFAUT = {
    LECTURE: list(_BASE_LECTURE),
    EDITION: _BASE_LECTURE + ["ajout"],
    ADMIN:   list(SECTIONS),
}

# ── PROFILS PRÊTS À L'EMPLOI ─────────────────────────────────────────────────────────
# Cocher huit cases sans se tromper, pour chaque nouvel arrivant, est une invitation à
# l'erreur — et une case cochée de travers ouvre un écran qu'on ne voulait pas ouvrir.
# Ces profils traduisent l'arbitrage retenu : chaque direction voit la matière dont elle
# répond, et ses propres directives.
PROFILS = {
    "dg": ("Direction Générale",
           ["strategie", "stratop", "chat"] + list(DIRECTIONS_STRATOP)),
    "risques": ("Direction des Risques",
                ["apercu", "stratop", "dir_ris"]),
    "commerciale": ("Direction Commerciale",
                    ["cb", "stratop", "dir_com"]),
    "marketing": ("Direction Marketing",
                  ["cb", "stratop", "dir_mkt"]),
    "financiere": ("Direction Financière",
                   ["apercu", "stratop", "dir_fin"]),
    "innovation": ("Direction Innovation",
                   ["strategie", "stratop", "dir_inn"]),
}


def directions_autorisees(utilisateur):
    """Directions de la Stratégie opérationnelle visibles par ce compte.

    Rend None quand il n'y a AUCUNE restriction — l'appelant sert alors tout. On distingue
    volontairement « aucune case cochée » (= tout voir) de « une seule cochée » (= une seule
    direction) : sans cette distinction, l'évolution aurait vidé l'écran de tous les comptes
    existants du jour au lendemain.
    """
    if not utilisateur or utilisateur.get("role") == ADMIN:
        return None
    choisies = [DIRECTIONS_STRATOP[c] for c in (utilisateur.get("droits") or [])
                if c in DIRECTIONS_STRATOP]
    return choisies or None

# Rattachement des endpoints aux sections. Un chemin non listé relève du socle commun
# (banques, périodes, logos, état du service) : le refuser casserait l'application pour tout
# le monde sans rien protéger, puisque ces données ne disent rien de plus que la liste des
# onglets. Le contrôle porte sur ce qui a de la valeur : les chiffres et l'assistant.
_SECTION_PAR_PREFIXE = (
    ("/api/ajout/", "ajout"),
    ("/api/rafraichir_analyses", "ajout"),
    ("/api/admin/", "admin"),
    ("/api/journal_acces", "admin"),
    ("/api/chat", "chat"),
    ("/api/conv_history", "chat"),
    ("/api/approfondir", "chat"),
    ("/api/strategie_operationnelle", "stratop"),
    ("/api/strategie", "strategie"),
    ("/api/pestel", "strategie"),
    ("/api/vrist", "strategie"),
    ("/api/analyse_strategique", "strategie"),
    ("/api/cb", "cb"),
    ("/api/ef_", "apercu"),
    ("/api/kpis", "apercu"),
    ("/api/rn", "apercu"),
    ("/api/resilience", "apercu"),
    ("/api/radar_agent", "apercu"),
    ("/api/frais", "analyse"),
    ("/api/regl", "analyse"),
)


def section_du_chemin(chemin):
    """À quelle section appartient cet endpoint ? None quand il relève du socle commun."""
    for prefixe, section in _SECTION_PAR_PREFIXE:
        if chemin.startswith(prefixe):
            return section
    return None


def _droits(valeur, role):
    """Liste de droits depuis la colonne texte, avec repli sur le défaut du rôle."""
    if valeur:
        lot = [d.strip() for d in str(valeur).split(",") if d.strip() in SECTIONS]
        if lot:
            return lot
    return list(DROITS_PAR_DEFAUT.get(role, DROITS_PAR_DEFAUT[LECTURE]))


def a_le_droit(utilisateur, section):
    """L'utilisateur a-t-il accès à cette section ?"""
    if not utilisateur or not section:
        return True                      # socle commun : pas de section, pas de restriction
    if utilisateur.get("role") == ADMIN:
        return True                      # l'administrateur voit tout, par définition
    return section in (utilisateur.get("droits") or [])

# Limitation des tentatives — en mémoire, volontairement.
# Un compteur en base serait plus durable, mais l'écrire à CHAQUE tentative offrirait un
# levier de saturation à l'attaquant lui-même : il suffirait de marteler la page de connexion
# pour faire grossir une table. En mémoire, une tentative ne coûte rien au disque.
MAX_TENTATIVES = 5
DUREE_BLOCAGE_S = 300           # 5 minutes
_tentatives = {}                # identifiant -> [nombre, horodatage du dernier échec]
_verrou = threading.Lock()


def _maintenant():
    return datetime.datetime.now()


# ══════════════════════════════════════════════════════════════════════════════════════
#  SCHÉMA
# ══════════════════════════════════════════════════════════════════════════════════════

def initialiser():
    """Crée les tables de sécurité si elles manquent, et amorce le premier compte.

    Idempotent : appelée à chaque démarrage, elle ne fait rien quand tout est en place.
    """
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS utilisateurs (
                id                SERIAL PRIMARY KEY,
                identifiant       TEXT NOT NULL UNIQUE,
                empreinte         TEXT NOT NULL,
                role              TEXT NOT NULL DEFAULT 'lecture',
                actif             BOOLEAN NOT NULL DEFAULT TRUE,
                cree_le           TIMESTAMP NOT NULL DEFAULT NOW(),
                derniere_connexion TIMESTAMP
            )""")
        db.execute("""
            CREATE TABLE IF NOT EXISTS journal_acces (
                id           BIGSERIAL PRIMARY KEY,
                horodatage   TIMESTAMP NOT NULL DEFAULT NOW(),
                identifiant  TEXT,
                action       TEXT NOT NULL,
                ressource    TEXT,
                adresse_ip   TEXT,
                succes       BOOLEAN NOT NULL DEFAULT TRUE,
                detail       TEXT
            )""")
        # Index sur l'horodatage : un journal se consulte par période, et il grossit.
        db.execute("CREATE INDEX IF NOT EXISTS idx_journal_horodatage "
                   "ON journal_acces (horodatage DESC)")
        # Droits par section, ajoutés après coup : ADD COLUMN IF NOT EXISTS pour que les
        # bases déjà créées se mettent à niveau sans intervention ni perte de comptes.
        # Colonne TEXTE et non JSON : « apercu,cb,chat » se lit et se corrige directement en
        # psql, ce qui compte le jour où il faut débloquer quelqu'un sans passer par l'écran.
        db.execute("ALTER TABLE utilisateurs ADD COLUMN IF NOT EXISTS droits TEXT")
    except Exception as e:
        print("[securite] création du schéma impossible :", str(e)[:160])
        return False
    return _amorcer_admin()


def _amorcer_admin():
    """Crée le compte d'administration au premier démarrage, jamais ensuite.

    Le mot de passe initial vient de la variable d'environnement APP_ADMIN_PASSWORD. En son
    absence, on en TIRE UN AU HASARD et on l'affiche une seule fois dans la console : mettre
    un mot de passe par défaut dans le code reproduirait exactement le défaut qu'on corrige.
    """
    try:
        deja = db.query("SELECT COUNT(*) AS n FROM utilisateurs")[0]["n"]
    except Exception as e:
        print("[securite] lecture des comptes impossible :", str(e)[:160])
        return False
    if deja:
        return True

    identifiant = (os.getenv("APP_ADMIN_USER") or "admin").strip()
    mot_de_passe = os.getenv("APP_ADMIN_PASSWORD")
    genere = not mot_de_passe
    if genere:
        mot_de_passe = secrets.token_urlsafe(12)

    if not creer_utilisateur(identifiant, mot_de_passe, ADMIN):
        return False

    print("=" * 78)
    print("  COMPTE D'ADMINISTRATION CRÉÉ")
    print(f"    identifiant  : {identifiant}")
    if genere:
        print(f"    mot de passe : {mot_de_passe}")
        print("    Ce mot de passe est affiché UNE SEULE FOIS. Notez-le, puis définissez")
        print("    APP_ADMIN_PASSWORD dans le fichier .env pour le maîtriser.")
    else:
        print("    mot de passe : celui défini dans APP_ADMIN_PASSWORD")
    print("=" * 78)
    return True


# ══════════════════════════════════════════════════════════════════════════════════════
#  COMPTES
# ══════════════════════════════════════════════════════════════════════════════════════

def creer_utilisateur(identifiant, mot_de_passe, role=LECTURE, droits=None):
    """Crée un compte. Le mot de passe n'est jamais stocké — seule son empreinte l'est."""
    from werkzeug.security import generate_password_hash
    identifiant = (identifiant or "").strip().lower()
    if not identifiant or not mot_de_passe:
        return False
    if len(mot_de_passe) < LONGUEUR_MIN:
        print(f"[securite] mot de passe trop court ({LONGUEUR_MIN} caractères minimum).")
        return False
    if role not in ROLES:
        role = LECTURE
    lot = [d for d in (droits or DROITS_PAR_DEFAUT.get(role, [])) if d in SECTIONS]
    # generate_password_hash produit « scrypt:32768:8:1$<sel>$<empreinte> » : le sel est
    # tiré au hasard pour CHAQUE compte et voyage avec l'empreinte. C'est ce qui fait que
    # deux utilisateurs ayant choisi le même mot de passe n'ont pas la même empreinte.
    try:
        db.execute("INSERT INTO utilisateurs (identifiant, empreinte, role, droits) "
                   "VALUES (%s, %s, %s, %s)",
                   (identifiant, generate_password_hash(mot_de_passe), role, ",".join(lot)))
        return True
    except Exception as e:
        print("[securite] création de compte impossible :", str(e)[:160])
        return False


def changer_mot_de_passe(identifiant, nouveau):
    """Remplace le mot de passe d'un compte. Un nouveau sel est tiré à cette occasion.

    Utilisable en ligne de commande :
        python -c "import sys; sys.path.insert(0,'.'); import securite; \
                   securite.changer_mot_de_passe('admin', 'VotreNouveauMotDePasse')"
    """
    from werkzeug.security import generate_password_hash
    identifiant = (identifiant or "").strip().lower()
    if not identifiant or not nouveau or len(nouveau) < LONGUEUR_MIN:
        print(f"[securite] mot de passe trop court ({LONGUEUR_MIN} caractères minimum).")
        return False
    try:
        n = db.execute("UPDATE utilisateurs SET empreinte = %s WHERE identifiant = %s",
                       (generate_password_hash(nouveau), identifiant))
    except Exception as e:
        print("[securite] changement impossible :", str(e)[:160])
        return False
    if not n:
        print(f"[securite] aucun compte « {identifiant} ».")
        return False
    _succes(identifiant)          # lève une éventuelle temporisation en cours
    journaliser(identifiant, "changement_mot_de_passe", None, None, True)
    print(f"[securite] mot de passe de « {identifiant} » remplacé.")
    return True


def _bloque(identifiant):
    """Ce compte est-il temporisé après trop d'échecs ?"""
    with _verrou:
        etat = _tentatives.get(identifiant)
        if not etat:
            return 0
        n, dernier = etat
        if n < MAX_TENTATIVES:
            return 0
        reste = DUREE_BLOCAGE_S - (_maintenant() - dernier).total_seconds()
        if reste <= 0:
            _tentatives.pop(identifiant, None)
            return 0
        return int(reste)


def _echec(identifiant):
    with _verrou:
        n, _ = _tentatives.get(identifiant, (0, None))
        _tentatives[identifiant] = (n + 1, _maintenant())


def _succes(identifiant):
    with _verrou:
        _tentatives.pop(identifiant, None)


def verifier(identifiant, mot_de_passe, adresse_ip=None):
    """Authentifie un utilisateur.

    Renvoie (utilisateur, None) si l'identification réussit, (None, motif) sinon. Le motif
    renvoyé à l'appelant reste VOLONTAIREMENT vague sur la cause : distinguer « identifiant
    inconnu » de « mot de passe incorrect » indiquerait à un attaquant quels comptes existent.
    Le journal, lui, conserve le détail exact.
    """
    from werkzeug.security import check_password_hash
    identifiant = (identifiant or "").strip().lower()

    reste = _bloque(identifiant)
    if reste:
        journaliser(identifiant, "connexion", None, adresse_ip, False,
                    f"compte temporisé, {reste} s restantes")
        return None, f"Trop de tentatives. Réessayez dans {reste // 60 + 1} minute(s)."

    try:
        lignes = db.query(
            "SELECT id, identifiant, empreinte, role, actif, droits FROM utilisateurs "
            "WHERE identifiant = %s", (identifiant,))
    except Exception as e:
        print("[securite] lecture du compte impossible :", str(e)[:160])
        return None, "Service d'authentification indisponible."

    u = lignes[0] if lignes else None
    # On vérifie l'empreinte MÊME quand le compte n'existe pas, contre une empreinte factice.
    # Sans cela, un identifiant inconnu répondrait plus vite qu'un mot de passe faux, et le
    # simple temps de réponse révélerait quels comptes existent.
    empreinte = u["empreinte"] if u else (
        "scrypt:32768:8:1$" + "0" * 16 + "$" + "0" * 128)
    valide = check_password_hash(empreinte, mot_de_passe or "")

    if not u or not valide:
        _echec(identifiant)
        journaliser(identifiant, "connexion", None, adresse_ip, False,
                    "compte inconnu" if not u else "mot de passe incorrect")
        return None, "Identifiant ou mot de passe incorrect."
    if not u["actif"]:
        journaliser(identifiant, "connexion", None, adresse_ip, False, "compte désactivé")
        return None, "Ce compte est désactivé."

    _succes(identifiant)
    try:
        db.execute("UPDATE utilisateurs SET derniere_connexion = NOW() WHERE id = %s", (u["id"],))
    except Exception:
        pass          # une horloge de confort ne doit pas faire échouer une connexion valide
    journaliser(identifiant, "connexion", None, adresse_ip, True, f"rôle {u['role']}")
    return {"id": u["id"], "identifiant": u["identifiant"], "role": u["role"],
            "droits": _droits(u.get("droits"), u["role"])}, None


def peut_ecrire(role):
    return role in ROLES_ECRITURE


# ══════════════════════════════════════════════════════════════════════════════════════
#  TRAÇABILITÉ
# ══════════════════════════════════════════════════════════════════════════════════════

def journaliser(identifiant, action, ressource=None, adresse_ip=None, succes=True, detail=None):
    """Consigne un événement d'accès.

    Ne lève jamais : un défaut de journalisation ne doit pas empêcher l'application de
    fonctionner. Il s'affiche en console pour ne pas passer inaperçu.
    """
    try:
        db.execute(
            "INSERT INTO journal_acces (identifiant, action, ressource, adresse_ip, succes, detail) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (identifiant, action, ressource, adresse_ip, succes, detail))
    except Exception as e:
        print("[securite] journalisation impossible :", str(e)[:120])


def journal(limite=200):
    """Derniers événements d'accès, les plus récents d'abord."""
    try:
        return db.query(
            "SELECT horodatage, identifiant, action, ressource, adresse_ip, succes, detail "
            "FROM journal_acces ORDER BY horodatage DESC LIMIT %s", (limite,))
    except Exception:
        return []


def utilisateurs():
    """Comptes existants — sans les empreintes, qui n'ont à sortir de la base sous aucun motif."""
    try:
        lignes = db.query(
            "SELECT id, identifiant, role, actif, droits, cree_le, derniere_connexion "
            "FROM utilisateurs ORDER BY identifiant")
    except Exception:
        return []
    for u in lignes:
        u["droits"] = _droits(u.get("droits"), u.get("role"))
    return lignes


# ══════════════════════════════════════════════════════════════════════════════════════
#  ADMINISTRATION DES COMPTES
# ══════════════════════════════════════════════════════════════════════════════════════
# Toutes ces fonctions journalisent QUI a modifié QUOI. Un écran d'administration qui laisse
# changer les droits sans laisser de trace déplace le problème au lieu de le résoudre : on
# saurait qui a accès, sans savoir qui le lui a donné.

def modifier_utilisateur(identifiant, role=None, droits=None, actif=None, par=None):
    """Change le rôle, les droits ou l'état d'un compte."""
    identifiant = (identifiant or "").strip().lower()
    champs, valeurs, detail = [], [], []
    if role in ROLES:
        champs.append("role = %s"); valeurs.append(role); detail.append(f"rôle={role}")
    if droits is not None:
        lot = [d for d in droits if d in SECTIONS]
        champs.append("droits = %s"); valeurs.append(",".join(lot))
        detail.append(f"droits={'|'.join(lot) or 'aucun'}")
    if actif is not None:
        champs.append("actif = %s"); valeurs.append(bool(actif))
        detail.append("actif" if actif else "désactivé")
    if not champs:
        return False
    valeurs.append(identifiant)
    try:
        n = db.execute(f"UPDATE utilisateurs SET {', '.join(champs)} WHERE identifiant = %s",
                       tuple(valeurs))
    except Exception as e:
        print("[securite] modification impossible :", str(e)[:160])
        return False
    if n:
        journaliser(par, "modification_compte", identifiant, None, True, " · ".join(detail))
    return bool(n)


def supprimer_utilisateur(identifiant, par=None):
    """Supprime un compte. Le dernier administrateur ne peut pas l'être.

    Sans ce garde-fou, une fausse manœuvre rendrait l'administration définitivement
    inaccessible — il faudrait rouvrir la base à la main pour s'en sortir.
    """
    identifiant = (identifiant or "").strip().lower()
    try:
        cible = db.query("SELECT role FROM utilisateurs WHERE identifiant = %s", (identifiant,))
        if not cible:
            return False, "compte introuvable"
        if cible[0]["role"] == ADMIN:
            restants = db.query("SELECT COUNT(*) AS n FROM utilisateurs "
                                "WHERE role = %s AND actif = TRUE", (ADMIN,))[0]["n"]
            if restants <= 1:
                return False, "c'est le dernier administrateur actif"
        db.execute("DELETE FROM utilisateurs WHERE identifiant = %s", (identifiant,))
    except Exception as e:
        return False, str(e)[:120]
    journaliser(par, "suppression_compte", identifiant, None, True)
    return True, None
