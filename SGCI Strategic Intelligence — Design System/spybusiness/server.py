"""
SpyBusiness — Serveur Flask.
Sert l'app.html (design intact) + API PostgreSQL réelle + RAG.

Lancement :
    cd "C:/Users/ALPHEE COLOMBE/Downloads/SGCI Strategic Intelligence — Design System/spybusiness"
    python server.py
    → http://localhost:5000
"""

import sys, os, json, re
import secrets          # cle de session, mots de passe amorces (module securite)
import re as _re      # alias module (2026-07-28) : plusieurs helpers l'utilisaient alors qu'il
                      # n'était importé QUE dans le corps de certaines fonctions — toute nouvelle
                      # regex écrite au niveau module levait un NameError au démarrage du serveur.
import datetime as _dt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE     = os.path.dirname(os.path.abspath(__file__))
# BACK_DIR = racine du dépôt (2 niveaux au-dessus de spybusiness/), pas ~/Desktop/BACK —
# reste correct quel que soit l'utilisateur/OS/conteneur tant que la structure du repo est préservée.
BACK_DIR = os.environ.get("BACK_DIR") or os.path.dirname(os.path.dirname(HERE))
RAG_DIR  = os.path.join(BACK_DIR, "RAG")

# ── ARBORESCENCE (2026-07-30) ────────────────────────────────────────────────────────
# La racine mélangeait le code, le front, huit caches JSON et onze sauvegardes horodatées.
# Deux dossiers séparent désormais ce qui se régénère de ce qui se conserve :
#   cache/ — caches d'analyses et d'état, supprimables sans perte (ils se reconstruisent)
#   data/  — données de référence alimentant les analyses, à conserver et à versionner
# Les chemins restent des constantes uniques : un déplacement futur ne touche que ces deux
# lignes, jamais les vingt endroits qui lisent un fichier.
DOSSIER_CACHE = os.path.join(HERE, "cache")
DOSSIER_DATA  = os.path.join(HERE, "data")
os.makedirs(DOSSIER_CACHE, exist_ok=True)
os.makedirs(DOSSIER_DATA, exist_ok=True)

# Charger .env depuis BACK_DIR (contient les clés Groq, DB, etc.) — en local uniquement.
# En prod (Cloud Run, etc.), les variables sont injectées directement par la plateforme
# et ce fichier n'existe pas : os.environ.setdefault ne fait alors rien, sans erreur.
_env_file = os.path.join(BACK_DIR, ".env")
if os.path.isfile(_env_file):
    with open(_env_file, encoding="utf-8") as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                if _k.strip() and _v.strip():
                    os.environ.setdefault(_k.strip(), _v.strip())

# Expose db module
sys.path.insert(0, os.path.join(HERE, "dash_app"))
# Expose RAG chain
if os.path.isdir(RAG_DIR):
    sys.path.insert(0, RAG_DIR)

from flask import Flask, jsonify, request, send_from_directory, session

try:
    from flask_cors import CORS
    _cors_ok = True
except ImportError:
    _cors_ok = False

app = Flask(__name__, static_folder=HERE, static_url_path="")

# ── CORS RESTREINT (2026-08-07) ──────────────────────────────────────────────────────
# CORS(app) sans argument émet « Access-Control-Allow-Origin: * » : n'importe quel site
# visité par un utilisateur connecté pouvait interroger cette API depuis son navigateur, avec
# son cookie de session. On limite aux origines réellement servies ; supports_credentials est
# nécessaire pour que le cookie de session voyage, et il est INCOMPATIBLE avec le joker « * »
# — raison de plus pour énumérer les origines.
_ORIGINES = [o.strip() for o in (os.getenv("APP_ORIGINES") or
             "http://localhost:5000,http://127.0.0.1:5000").split(",") if o.strip()]
if _cors_ok:
    CORS(app, origins=_ORIGINES, supports_credentials=True)

import db
import securite             # authentification, rôles et journal d'accès (cf. dash_app/securite.py)
from agents import AGENTS   # façade : porte d'entrée unique de récupération (RAG multi-agents)
import strategie            # orchestration Stratégie (Niveau 3 du RAG, via les agents)

print(f"[CONFIG] DB={db.DB['dbname']}@{db.DB['host']} | BACK={BACK_DIR}")

# ══════════════════════════════════════════════════════════════════════════════════════
#  SÉCURITÉ — authentification, rôles, traçabilité
# ══════════════════════════════════════════════════════════════════════════════════════
# AJOUTÉ LE 2026-08-07. Avant cela, la page de connexion était vérifiée dans app.main.js,
# avec le mot de passe écrit en clair dans un fichier servi à tout visiteur, et AUCUN
# contrôle côté serveur : les vingt-et-un endpoints répondaient à n'importe quelle requête.
# Vérifié en curl, sans identifiant, sur la totalité de l'API.
#
# La clé de session signe le cookie : sans elle, un cookie peut être forgé. Elle est lue dans
# l'environnement ; à défaut on en tire une au hasard, ce qui invalide les sessions à chaque
# redémarrage — comportement volontaire, une clé écrite en dur dans le dépôt serait publique.
app.secret_key = os.getenv("APP_SECRET_KEY") or secrets.token_hex(32)
if not os.getenv("APP_SECRET_KEY"):
    print("[securite] APP_SECRET_KEY absente du .env — clé de session temporaire : "
          "les utilisateurs seront déconnectés à chaque redémarrage.")

# Le cookie de session ne doit pas être lisible par JavaScript (vol par script injecté), ni
# transmis lors d'une requête déclenchée par un autre site (CSRF).
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.getenv("APP_HTTPS")),
    PERMANENT_SESSION_LIFETIME=_dt.timedelta(hours=12),
)

securite.initialiser()

# Chemins accessibles SANS être authentifié : la page elle-même, ses ressources statiques et
# le point d'entrée de connexion. Tout le reste exige une session.
_LIBRES = {"/", "/api/login", "/api/moi", "/favicon.ico"}


@app.before_request
def _controle_acces():
    """Porte unique : aucun endpoint /api/* ne répond sans session valide.

    Placer le contrôle ICI plutôt que sur chaque route est délibéré : une route ajoutée
    demain est protégée par défaut. L'inverse — décorer chaque route — laisse fatalement
    passer celle qu'on oublie, et c'est toujours celle-là qui est trouvée.
    """
    chemin = request.path or "/"
    if request.method == "OPTIONS" or chemin in _LIBRES:
        return None
    # Ressources statiques (js, css, images, polices) : la page de connexion en a besoin.
    if not chemin.startswith("/api/"):
        return None

    utilisateur = session.get("utilisateur")
    if not utilisateur:
        return jsonify({"error": "authentification requise", "code": "non_authentifie"}), 401

    # DROITS PAR SECTION. Chaque endpoint appartient à une section de l'application ; on
    # vérifie que l'utilisateur y a accès. C'est plus fin qu'un rôle : deux personnes peuvent
    # être toutes deux en lecture seule et ne pas voir les mêmes chiffres.
    section = securite.section_du_chemin(chemin)
    if not securite.a_le_droit(utilisateur, section):
        securite.journaliser(utilisateur.get("identifiant"), "acces_refuse", chemin,
                             request.remote_addr, False, f"section « {section} » non autorisée")
        return jsonify({"error": f"accès non autorisé à la section « {section} »",
                        "code": "droit_manquant", "section": section}), 403

    # Les endpoints qui MODIFIENT la base d'analyse exigent en plus le rôle d'édition : ce
    # sont eux qui décident de ce que l'application affirme. Et chaque écriture est tracée.
    if section == "ajout":
        if not securite.peut_ecrire(utilisateur.get("role")):
            securite.journaliser(utilisateur.get("identifiant"), "acces_refuse", chemin,
                                 request.remote_addr, False, "rôle insuffisant")
            return jsonify({"error": "droits insuffisants pour modifier les données",
                            "code": "role_insuffisant"}), 403
        securite.journaliser(utilisateur.get("identifiant"), "ecriture", chemin,
                             request.remote_addr, True, None)
    return None


# ── ADMINISTRATION DES COMPTES ───────────────────────────────────────────────────────
# Réservée au rôle administrateur. La garde ci-dessus filtre déjà /api/admin/ par la section
# « admin », mais on revérifie le RÔLE ici : un droit de section coché par erreur ne doit pas
# suffire à créer des comptes. Deux verrous valent mieux qu'un sur la porte du trousseau.

def _exige_admin():
    u = session.get("utilisateur") or {}
    if u.get("role") != securite.ADMIN:
        return None, (jsonify({"error": "réservé à l'administration"}), 403)
    return u, None


@app.route("/api/admin/utilisateurs")
def api_admin_utilisateurs():
    u, refus = _exige_admin()
    if refus:
        return refus
    return jsonify({"utilisateurs": securite.utilisateurs(),
                    "sections": securite.SECTIONS,
                    "roles": list(securite.ROLES),
                    "droits_par_defaut": securite.DROITS_PAR_DEFAUT,
                    "longueur_min": securite.LONGUEUR_MIN})


@app.route("/api/admin/utilisateur", methods=["POST"])
def api_admin_creer():
    u, refus = _exige_admin()
    if refus:
        return refus
    c = request.get_json(force=True, silent=True) or {}
    ok = securite.creer_utilisateur(c.get("identifiant"), c.get("mot_de_passe"),
                                    c.get("role") or securite.LECTURE, c.get("droits"))
    if not ok:
        return jsonify({"ok": False,
                        "error": f"création impossible : identifiant déjà pris, ou mot de "
                                 f"passe de moins de {securite.LONGUEUR_MIN} caractères."}), 400
    securite.journaliser(u.get("identifiant"), "creation_compte",
                         (c.get("identifiant") or "").strip().lower(),
                         request.remote_addr, True, f"rôle {c.get('role')}")
    return jsonify({"ok": True})


@app.route("/api/admin/utilisateur", methods=["PATCH"])
def api_admin_modifier():
    u, refus = _exige_admin()
    if refus:
        return refus
    c = request.get_json(force=True, silent=True) or {}
    cible = (c.get("identifiant") or "").strip().lower()
    # Se retirer à soi-même le rôle d'administrateur, c'est se verrouiller dehors.
    if cible == u.get("identifiant") and c.get("role") and c["role"] != securite.ADMIN:
        return jsonify({"ok": False, "error": "vous ne pouvez pas retirer votre propre rôle "
                                              "d'administrateur."}), 400
    if c.get("mot_de_passe"):
        if not securite.changer_mot_de_passe(cible, c["mot_de_passe"]):
            return jsonify({"ok": False,
                            "error": f"mot de passe de moins de {securite.LONGUEUR_MIN} "
                                     f"caractères, ou compte introuvable."}), 400
        securite.journaliser(u.get("identifiant"), "reinitialisation_mot_de_passe", cible,
                             request.remote_addr, True)
    ok = securite.modifier_utilisateur(cible, c.get("role"), c.get("droits"),
                                       c.get("actif"), par=u.get("identifiant"))
    return jsonify({"ok": bool(ok or c.get("mot_de_passe"))})


@app.route("/api/admin/utilisateur", methods=["DELETE"])
def api_admin_supprimer():
    u, refus = _exige_admin()
    if refus:
        return refus
    c = request.get_json(force=True, silent=True) or {}
    cible = (c.get("identifiant") or "").strip().lower()
    if cible == u.get("identifiant"):
        return jsonify({"ok": False, "error": "vous ne pouvez pas supprimer votre propre compte."}), 400
    ok, motif = securite.supprimer_utilisateur(cible, par=u.get("identifiant"))
    return jsonify({"ok": ok, "error": motif}) if not ok else jsonify({"ok": True})


@app.route("/api/login", methods=["POST"])
def api_login():
    """Authentifie contre l'empreinte stockée en base — jamais contre une chaîne du code."""
    corps = request.get_json(force=True, silent=True) or {}
    utilisateur, motif = securite.verifier(
        corps.get("identifiant"), corps.get("mot_de_passe"), request.remote_addr)
    if not utilisateur:
        # 401 et message volontairement identique quelle que soit la cause : distinguer
        # « compte inconnu » de « mot de passe faux » révélerait quels comptes existent.
        return jsonify({"ok": False, "error": motif}), 401
    session.permanent = True
    session["utilisateur"] = utilisateur
    return jsonify({"ok": True, "utilisateur": utilisateur})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    u = session.get("utilisateur") or {}
    securite.journaliser(u.get("identifiant"), "deconnexion", None, request.remote_addr, True)
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/moi")
def api_moi():
    """Qui suis-je ? Sert au front à savoir s'il doit afficher la porte de connexion."""
    u = session.get("utilisateur")
    return jsonify({"authentifie": bool(u), "utilisateur": u,
                    "peut_ecrire": bool(u and securite.peut_ecrire(u.get("role"))),
                    # Le front masque les onglets non autorisés : le serveur refuserait de
                    # toute façon, mais proposer une porte qui se ferme au nez est une
                    # mauvaise manière de faire respecter un droit.
                    "droits": (u or {}).get("droits") or [],
                    "sections": securite.SECTIONS})


@app.route("/api/journal_acces")
def api_journal_acces():
    """Journal d'accès — réservé à l'administration."""
    u = session.get("utilisateur") or {}
    if u.get("role") != securite.ADMIN:
        return jsonify({"error": "réservé à l'administration"}), 403
    return jsonify({"entrees": securite.journal(200)})

# ── RAG (init une seule fois) ──────────────────────────────────────────
_chain  = None
_RAG_OK = False
try:
    from chain import init_chain, ask
    _chain  = init_chain()
    _RAG_OK = True
    print("[RAG] ✓ opérationnel")
except Exception as e:
    print(f"[RAG] indisponible ({e})")

print(f"RAG dir : {RAG_DIR} {'✓' if os.path.isdir(RAG_DIR) else '✗ non trouvé'}")


# ══════════════════════════════════════════════════════════════════════
# Pages HTML — app.html exact, tous les assets servis statiquement
# ══════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return send_from_directory(HERE, "app.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(HERE, filename)


@app.after_request
def _no_cache(resp):
    """Empêche le navigateur de servir un app.main.js / CSS périmé (sinon les
    corrections n'apparaissent pas sans hard-refresh)."""
    ct = resp.headers.get("Content-Type", "")
    if any(t in ct for t in ("javascript", "text/css", "text/html")):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


# ══════════════════════════════════════════════════════════════════════
# API — données réelles PostgreSQL
# ══════════════════════════════════════════════════════════════════════

@app.route("/api/frais")
def api_frais():
    """Frais de tenue de compte par banque — 'à partir de' (min non-zéro)."""
    annee    = int(request.args.get("annee", 2026))
    semestre = request.args.get("semestre", "S1")
    segment  = request.args.get("segment", "Particuliers")
    data = AGENTS["CB"].structured.frais_tenue_compte(annee, semestre, segment)
    return jsonify(data)


@app.route("/api/frais_detail")
def api_frais_detail():
    """Tous les tarifs de tenue de compte par banque × type de compte."""
    annee    = int(request.args.get("annee", 2026))
    semestre = request.args.get("semestre", "S1")
    segment  = request.args.get("segment", "Particuliers")
    return jsonify(db.frais_detail(annee, semestre, segment))


@app.route("/api/cb_serie_temporelle")
def api_cb_serie_temporelle():
    """Série temporelle SGCI (rang, gratuité, indice prix) sur toutes les périodes."""
    segment = request.args.get("segment", "Particuliers")
    return jsonify(servir_avec_cache(
        f"cb_serie_temporelle:{segment}",
        lambda: AGENTS["CB"].structured.cb_serie_temporelle(segment)))


@app.route("/api/cb_innovation_vs_finance")
def api_cb_innovation_vs_finance():
    """Croisement innovation (CB) × force financière (EF) par banque — dynamique."""
    segment = request.args.get("segment", "Particuliers")
    return jsonify(servir_avec_cache(
        f"cb_innovation_vs_finance:{segment}",
        lambda: AGENTS["CB"].structured.cb_innovation_vs_finance(segment)))


@app.route("/api/cb_rattrapage_depassement")
def api_cb_rattrapage_depassement():
    """Par concurrent : nouveaux services déjà chez SGCI (rattrapage) vs absents (dépassement).

    Mesuré à 79,3 s au premier appel sur le service hébergé, 0,3 s ensuite : le @lru_cache qui
    le protège meurt avec le processus, et l'hébergeur en redémarre un neuf à chaque réveil.
    """
    segment = request.args.get("segment", "Particuliers")
    return jsonify(servir_avec_cache(
        f"cb_rattrapage_depassement:{segment}",
        lambda: AGENTS["CB"].structured.cb_rattrapage_depassement(segment)))


@app.route("/api/rn")
def api_rn():
    """Résultat net par banque — meilleure donnée disponible par banque."""
    # Fusionner toutes les années (la plus récente par banque prime)
    result = dict(db.MOCK_RN_2025)      # base = mocks pour les 7 banques
    for annee in [2023, 2024, 2025]:   # oldest first → newest overwrites
        data = AGENTS["EF"].structured.resultat_net(annee)
        result.update(data)            # données réelles écrasent les mocks
    return jsonify({"annee": 2025, "data": result})


@app.route("/api/rn_series")
def api_rn_series():
    """Séries temporelles du résultat net par banque."""
    series = AGENTS["EF"].structured.resultat_net_series()
    out = {}
    for b, yr_map in series.items():
        years = sorted(yr_map.keys())
        out[b] = {"years": years, "values": [yr_map[y] for y in years]}
    return jsonify(out)


@app.route("/api/cb")
def api_cb():
    """Table comparative des services CB (tarifs par banque × service)."""
    annee    = int(request.args.get("annee", 2026))
    semestre = request.args.get("semestre", "S1")
    segment  = request.args.get("segment", "Particuliers")
    return jsonify(db.cb_comparatif(annee, semestre, segment))


@app.route("/api/stats")
def api_stats():
    """Statistiques globales de la base."""
    return jsonify(db.stats_globales())


@app.route("/api/strategie_operationnelle")
def api_strategie_operationnelle():
    """Veille stratégique augmentée — les six questions d'un comité de direction.

    Cadrage donné par le directeur : une recommandation n'atteint le niveau d'un cabinet de
    conseil que si elle répond systématiquement à SIX questions, et pas seulement aux trois
    premières que produisait la version précédente :

        1. Que se passe-t-il ?              le fait de marché          → LECTURE
        2. Pourquoi est-ce important ?      l'enjeu stratégique       → ENJEU
        3. Que doit faire la banque ?       les actions               → DECISION (avec direction)
        4. Combien cela peut rapporter ?    le business case          → calculé, pas rédigé
        5. Quels risques, quelles conditions ?                        → RISQUES + SIRIEN
        6. Pourquoi agir maintenant ?       la fenêtre de tir         → MAINTENANT

    La question 4 n'est PAS confiée au LLM : elle est calculée dans
    dash_app/strategie_operationnelle.py à partir de la commission moyenne réelle
    (commissions du compte de résultat / nombre de clients). Faire rédiger un montant serait
    rouvrir la porte à l'invention, précisément là où le lecteur est le plus exigeant.
    """
    annee    = int(request.args.get("annee", 2026))
    semestre = (request.args.get("semestre") or "S1").strip()
    segment  = (request.args.get("segment") or "Particuliers").strip()

    # RÉPONSE SERVIE DEPUIS LE DISQUE QUAND ELLE EXISTE (2026-08-10).
    # Mesuré sur le service hébergé : 162 secondes au premier appel, 6 au second. Le cache
    # mémoire fonctionne donc — mais l'offre gratuite endort le service après quinze minutes
    # d'inactivité, et au réveil le processus repart à vide. La requête de l'utilisateur double
    # alors le fil de préchauffage et paie le calcul complet. Autrement dit : le cache mémoire
    # ne sert JAMAIS le premier visiteur, qui est précisément celui qu'il fallait servir.
    # Sur disque, il survit au redémarrage.
    depuis_disque = _stratop_lire(annee, semestre, segment)
    if depuis_disque is not None:
        return jsonify(depuis_disque)

    try:
        import strategie_operationnelle as _so
        d = _so.dossiers(annee, semestre, segment)
    except Exception as e:
        import traceback as _tb
        print("[strat-op]", _tb.format_exc()[:600])
        return jsonify({"error": str(e)[:200], "secteurs": [], "n_secteurs": 0}), 200

    eco = d.get("economie") or {}
    for sec in d.get("secteurs", []):
        faits_txt = chr(10).join(
            f"  - {f['valeur']}" + (f" ({f['detail']})" if f.get('detail') else "")
            + f" [source : {f['source']}]"
            for f in sec.get("faits_sources", []))
        conc = sec.get("concurrence") or []
        conc_txt = (", ".join(f"{c['banque']} ({c['n_services']} services liés à ce secteur)"
                              for c in conc)
                    if conc else "aucun concurrent identifié sur ce terrain")
        dirs = sec.get("directions_imposees") or _so.DIRECTIONS[:3]
        prods = sec.get("produits_sgci") or []
        prod_txt = (chr(10).join(f"  - {x['libelle']} : {x['prix']}" for x in prods)
                    if prods else "  (aucune ligne tarifaire identifiée sur ce secteur)")
        evts = sec.get("evenements") or []
        evt_txt = (chr(10).join(
            f"  - {e.get('acteur','')} {e.get('fait','')}"
            + (f" ({e['montant']})" if e.get('montant') else "")
            + (f" [{e['date_citee']}]" if e.get('date_citee') else "")
            for e in evts) if evts else "  aucun événement récent relevé sur ce secteur")
        bc = sec.get("business_case") or {}
        bc_txt = (f"{bc['clients_min']} à {bc['clients_max']} nouveaux clients, soit "
                  f"+{bc['commissions_min_fcfa']/1e6:.0f} à +{bc['commissions_max_fcfa']/1e6:.0f} M FCFA "
                  f"de commissions annuelles" if bc else "non chiffrable sur ce secteur")

        prompt = f"""Tu es le directeur de la stratégie de la Société Générale Côte d'Ivoire.
Tu prépares une note d'arbitrage pour le comité de direction sur un secteur du marché ivoirien.

SECTEUR : {sec['nom']}
POURQUOI CE SECTEUR EST SUIVI (comptage réel, ne le contredis pas) : {(sec.get('justification') or {}).get('texte') or 'non documenté'}
CLIENTS VISÉS : {sec['cibles']} (segment {sec['segment']})
PRODUITS BANCAIRES MOBILISABLES : {', '.join(sec.get('produits', []))}
CATALOGUE SGCI RÉEL SUR CE SECTEUR (libellé exact et tarif publié — cite-les tels quels) :
{prod_txt}
LEVIERS MARKETING MOBILISABLES : {', '.join(sec.get('leviers_marketing', [])) or 'aucun'}
DÉLAI D'EXÉCUTION ESTIMÉ : {sec.get('delai_libelle', '12 mois')}

FAITS DE MARCHÉ RELEVÉS (les seuls dont tu disposes) :
{faits_txt}

CONCURRENCE DÉJÀ EN PLACE (relevée dans les grilles tarifaires publiées) :
{conc_txt}

ÉVÉNEMENTS RÉCENTS DU MARCHÉ (veille datée et sourcée — appuie-toi dessus pour « pourquoi
maintenant » et « si la banque ne fait rien ») :
{evt_txt}

IMPACT DÉJÀ CHIFFRÉ (ne le recalcule pas, ne le contredis pas) :
{bc_txt}

REPÈRES SGCI : commissions {eco.get('part_commissions_pnb')}% du PNB, contre
{eco.get('meilleur_ratio')}% pour {eco.get('meilleur_ratio_banque')}, le mieux placé du marché.

Produis EXACTEMENT ce format, une ligne par bloc, sans rien ajouter :

LECTURE: <55 à 80 mots. Ce que montrent ces informations sur le secteur. Intègre les chiffres
DANS des phrases construites, avec leur unité. Prose de note interne.>
ENJEU: <30 à 50 mots. Pourquoi c'est important POUR LA BANQUE — ce que ça change à sa position,
à ses revenus ou à son exposition. Pas une répétition de la lecture.>
DECISION: <titre de 6 à 10 mots, verbe à l'infinitif, nommant le produit ET la cible> | <détail : ce qu'il faut faire, en citant le LIBELLÉ EXACT et le TARIF d'une ligne du catalogue SGCI ci-dessus, 20 à 35 mots> | <effort : Faible, Moyen ou Élevé> | {dirs[0]} | <PREMIER PAS : l'action à engager sous 30 jours, 8 à 16 mots, verbe à l'infinitif>
DECISION: <deuxième décision, même format, direction imposée> | ... | {dirs[1]} | ...
DECISION: <troisième décision, même format, direction imposée> | ... | {dirs[2]} | ...
RISQUES: <30 à 50 mots. Les risques d'exécution ET les conditions à réunir pour réussir.>
SIRIEN: <25 à 40 mots. Ce qui se passe si la banque ne fait rien — perte de parts de marché,
captation par la concurrence, érosion des commissions. Appuie-toi sur la concurrence ci-dessus.>
MAINTENANT: <25 à 40 mots. Pourquoi agir maintenant plutôt que dans six mois — échéance de
campagne, fenêtre avant intensification concurrentielle, cycle réglementaire.>
SYNTHESE: <40 à 60 mots. La lecture d'ensemble pour le comité : pourquoi ce dossier mérite ou
non d'être traité en priorité, en une respiration.>

RÈGLES ABSOLUES :
- N'invente AUCUN chiffre. N'utilise que ceux fournis ci-dessus, avec leur unité exacte.
- N'annonce JAMAIS un gain autre que celui déjà chiffré plus haut. Aucun pourcentage de PNB,
  aucun montant supplémentaire : la banque ne dispose pas des volumes clients par segment.
- Les trois décisions doivent être DIFFÉRENTES et relever de TROIS DIRECTIONS DISTINCTES.
- Les directions des trois décisions sont IMPOSÉES, dans cet ordre : {dirs[0]}, puis {dirs[1]},
  puis {dirs[2]}. N'en change aucune. Adapte le contenu de la décision à la direction qui la porte.
  Si l'une d'elles est la Direction Marketing, appuie-toi sur un levier marketing de la liste.
- Les autres décisions s'appuient sur le CATALOGUE SGCI RÉEL ci-dessus : cite le libellé exact
  et son tarif. Une décision qui invente un nom de produit inexistant chez SGCI est inutilisable
  par un chargé de clientèle.
- Le PREMIER PAS doit être exécutable sous 30 jours et vérifiable, jamais une intention. Les
  TROIS premiers pas doivent être DIFFÉRENTS entre eux et propres à ce secteur : ne réutilise
  pas une formule passe-partout applicable à n'importe quelle filière.
- Ne cite une ligne du catalogue QUE si elle correspond réellement à la décision. Écrire
  « développer le crédit de campagne en utilisant la domiciliation de salaires » discrédite
  la note entière. Si aucune ligne ne convient, décris l'action sans citer de produit : une
  décision sans référence tarifaire vaut mieux qu'une référence hors sujet.
- Aucune puce, aucun gras, aucun texte hors du format ci-dessus."""
        try:
            # v11 : fusion cacao+anacarde en « agro », quatre secteurs non agricoles ajoutés, et
            # la justification chiffrée du secteur entre dans le prompt. Les textes de la v10
            # portaient sur des secteurs qui n'existent plus — la clé doit changer, sinon le
            # cache resservirait l'ancienne rédaction sous un nouveau nom de secteur.
            r = _groq_call_cb(prompt, f"stratop_v11_{sec['cle']}_{segment}_{annee}_{semestre}",
                              max_tokens=1400, temperature=0.35, prefer_claude=True)
            brut = (r or {}).get("analyse") or ""
        except Exception as e:
            print(f"[strat-op] rédaction {sec['cle']} : {str(e)[:110]}")
            brut = ""

        # ── Analyse de la réponse ────────────────────────────────────────────────────
        # Format à blocs nommés plutôt que prose libre : le rendu attend des champs séparés.
        # Une réponse partielle n'invalide pas la carte — les blocs absents sont simplement
        # omis, et les données calculées (business case, arbitrage) restent affichées.
        champs = {"LECTURE": "lecture", "ENJEU": "enjeu", "RISQUES": "risques",
                  "SIRIEN": "si_rien", "MAINTENANT": "maintenant", "SYNTHESE": "synthese"}
        decisions = []
        for ligne in brut.splitlines():
            l = ligne.strip()
            if not l:
                continue
            cle_bloc = l.split(":", 1)[0].strip().upper()
            if cle_bloc in champs:
                sec[champs[cle_bloc]] = l.split(":", 1)[1].strip()
            elif cle_bloc == "DECISION":
                parts = [x.strip().lstrip("<").rstrip(">") for x in l.split(":", 1)[1].split("|")]
                if len(parts) >= 2 and parts[0]:
                    eff = parts[2] if len(parts) > 2 else "Moyen"
                    if eff not in ("Faible", "Moyen", "Élevé"):
                        eff = "Moyen"
                    dirn = parts[3] if len(parts) > 3 else sec.get("direction", "Direction Générale")
                    if dirn not in _so.DIRECTIONS:
                        dirn = sec.get("direction", "Direction Générale")
                    decisions.append({"titre": parts[0], "detail": parts[1],
                                      "effort": eff, "direction": dirn,
                                      "premier_pas": parts[4] if len(parts) > 4 else ""})
        sec["decisions"] = decisions[:3]
        import re as _re_src
        sec["sources_txt"] = " · ".join(sorted({
            _re_src.sub(r"\s*\b(19|20)\d{2}\b\s*$", "", (f.get("source") or "")).strip()
            for f in sec.get("faits_sources", []) if f.get("source")}))
    # ── DIRECTIVES PAR DIRECTION (2026-08-07) ────────────────────────────────────────
    # Le cœur de l'onglet. Composées par dash_app/directives.py SANS appel au modèle : le
    # directeur reprochait à cette page d'être incomplète — une carte pour certaines
    # directions, aucune pour le Marketing — et de se vider entièrement dès que le budget
    # de jetons se fermait. Quatre directives par direction, toujours, quoi qu'il arrive
    # du côté du fournisseur.
    #
    # Elles sont ajoutées APRÈS les dossiers sectoriels et ne dépendent pas d'eux : une
    # panne de rédaction laisse les dossiers sans texte, jamais les directives.
    try:
        d["directives"] = _directives_en_cache(segment)
    except Exception as e:
        import traceback as _tb
        print("[strat-op] directives :", _tb.format_exc()[:500])
        d["directives"] = {"directives": [], "erreur": str(e)[:200]}
    _stratop_ecrire(annee, semestre, segment, d)
    return jsonify(d)


# ── PERSISTANCE DE L'ONGLET STRATÉGIE OPÉRATIONNELLE — DANS LA BASE ──────────────────
# EN BASE, PAS SUR LE DISQUE (2026-08-10). La première version écrivait un fichier par
# (année, semestre, segment). C'était déjà mieux qu'un cache en mémoire, mais insuffisant :
# l'hébergeur repart d'une machine vierge à CHAQUE redéploiement, et le disque part avec.
# Le premier visiteur suivant repayait les 162 secondes de calcul.
#
# La base, elle, est le seul endroit qui survit à tout — réveil, redéploiement, changement de
# machine. Et elle est déjà là : aucune dépendance nouvelle, aucun service de plus à surveiller.
#
# La table est volontairement GÉNÉRIQUE : d'autres calculs coûteux voudront s'y ranger, et une
# table par cache finirait en collection de tables jumelles.
_CACHE_TABLE_PRETE = False


def _cache_table():
    """Crée la table de cache au premier besoin, une seule fois par processus."""
    global _CACHE_TABLE_PRETE
    if _CACHE_TABLE_PRETE:
        return True
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS cache_app (
                cle      text PRIMARY KEY,
                contenu  jsonb NOT NULL,
                maj      timestamptz NOT NULL DEFAULT now()
            )""")
        _CACHE_TABLE_PRETE = True
    except Exception as e:
        # Sans la table, l'application fonctionne — elle recalcule, c'est tout. On le dit une
        # fois plutôt que de laisser croire que le cache opère.
        print(f"[cache] table cache_app indisponible ({str(e)[:80]}) — recalcul à chaque appel")
    return _CACHE_TABLE_PRETE


def _cache_lire(cle):
    """Contenu mémorisé pour cette clé, ou None."""
    if not _cache_table():
        return None
    try:
        r = db.query("SELECT contenu FROM cache_app WHERE cle = %s", (cle,))
        return r[0]["contenu"] if r else None
    except Exception as e:
        print(f"[cache] lecture impossible ({str(e)[:70]}) — recalcul")
        return None


def servir_avec_cache(cle, producteur):
    """Sert depuis la base si la clé existe, sinon calcule, enregistre et sert.

    POURQUOI CE HELPER (2026-08-10). Plusieurs calculs sont protégés par un @lru_cache : très
    efficace, mais le cache vit DANS LE PROCESSUS. Or l'hébergeur endort le service après
    quinze minutes et le redémarre à chaque mise à jour : le processus repart à vide, et le
    premier visiteur paie le calcul entier. Mesuré sur le service en ligne :

        cb_rattrapage_depassement    79,3 s au premier appel, 0,3 s ensuite
        cb_repricing                 48,7 s au premier appel, 0,6 s ensuite

    Le cache mémoire ne sert donc JAMAIS celui qu'il faudrait servir. La base, elle, survit.

    Rien n'est enregistré si le résultat est vide : resservir indéfiniment une réponse vide
    masquerait une panne au lieu de la signaler.
    """
    garde = _cache_lire(cle)
    if garde is not None:
        return garde
    resultat = producteur()
    if resultat:
        _cache_ecrire(cle, resultat)
    return resultat


def _cache_ecrire(cle, contenu):
    if not _cache_table():
        return
    try:
        db.execute("""
            INSERT INTO cache_app (cle, contenu, maj) VALUES (%s, %s::jsonb, now())
            ON CONFLICT (cle) DO UPDATE SET contenu = EXCLUDED.contenu, maj = now()""",
                   (cle, json.dumps(contenu, ensure_ascii=False, default=str)))
    except Exception as e:
        print(f"[cache] écriture impossible : {str(e)[:90]}")


def _stratop_cle(annee, semestre, segment):
    return f"stratop:{annee}:{semestre}:{segment}"


def _stratop_lire(annee, semestre, segment):
    return _cache_lire(_stratop_cle(annee, semestre, segment))


def _stratop_ecrire(annee, semestre, segment, d):
    # On n'enregistre pas un résultat incomplet : servir indéfiniment une page amputée serait
    # pire que la recalculer. Vingt directives ou rien.
    if len(((d or {}).get("directives") or {}).get("directives") or []) < 20:
        return
    _cache_ecrire(_stratop_cle(annee, semestre, segment), d)


def _stratop_vider():
    """Vide TOUT le cache calculé — pas seulement la stratégie opérationnelle.

    Chaque entrée de cette table dérive de la base. Une ingestion change la base, donc les
    rend toutes fausses. N'en effacer qu'une partie reviendrait à laisser des écrans afficher
    l'état d'avant l'ajout, indéfiniment et sans le signaler : le défaut est d'autant plus
    pernicieux qu'il ne touche QUE certains écrans, ce qui fait douter des données plutôt que
    du cache.
    """
    if not _cache_table():
        return
    try:
        n = db.execute("DELETE FROM cache_app")
        print(f"[cache] {n} entrée(s) de cache effacée(s)")
    except Exception as e:
        print(f"[cache] vidage impossible : {str(e)[:90]}")


# ── CACHE DES DIRECTIVES (2026-08-09, pour l'hébergement) ────────────────────────────
# Mesuré en conditions réelles, l'application pointée sur la base hébergée : la composition
# des vingt directives a demandé 495 SECONDES. Elle enchaîne des centaines de requêtes, et ce
# qui coûte des millisecondes sur une base locale coûte un aller-retour réseau chacune.
# Aucun serveur ne laisse une requête durer huit minutes : le worker aurait été tué et la page
# n'aurait jamais fini de charger.
#
# La mise en cache est SANS RISQUE ICI, et le module le dit lui-même : « aucun appel réseau,
# aucun modèle de langage : à données inchangées, le résultat est strictement identique ».
# Rien n'est rédigé, tout est calculé — deux exécutions sur la même base donnent la même
# empreinte, ce qui a été vérifié. Le cache est vidé à l'ajout de données, comme les autres.
_SO_DIRECTIVES = {}


def _directives_en_cache(segment):
    if segment not in _SO_DIRECTIVES:
        import directives as _dir
        d = _dir.directives(segment=segment)
        _joindre_themes_globale(d, segment)
        _SO_DIRECTIVES[segment] = d
    return _SO_DIRECTIVES[segment]


def _joindre_themes_globale(d, segment):
    """Rattache chaque année du phasage au THÈME de la stratégie globale correspondante.

    AJOUTÉ LE 2026-08-10. Les deux pages travaillaient côte à côte sans se parler : la
    Stratégie globale porte déjà une feuille de route An 1 / An 2 / An 3, avec un thème et des
    actes chiffrés pour chacune, et la Stratégie opérationnelle recommandait vingt directives
    sans jamais dire à quelle année elles servaient. Trois directives font pourtant EXACTEMENT
    ce que la globale demande — réexaminer les tarifs éloignés (An 1), tenir le coût du risque
    (An 1), porter la part des commissions (An 2). Le lien existait ; il n'était écrit nulle part.

    On lit la feuille de route depuis le cache de la Stratégie (déjà rempli par le
    préchauffage), et on ne fait qu'y ATTACHER le thème : aucun recalcul, aucune duplication —
    si la globale change de thème, cette page suit.
    """
    try:
        feuille = ((_strat_get(segment) or {}).get("roadmap") or {}).get("horizons") or []
    except Exception as e:
        print(f"[strat-op] thèmes de la globale indisponibles : {str(e)[:80]}")
        return
    # `d` EST DÉJÀ la charge utile des directives : son bilan est à la racine, pas sous une
    # clé « directives » — celle-ci contient la LISTE des vingt cartes. La confusion a coûté
    # un « 'list' object has no attribute 'get' » qui vidait toute la page.
    for p in ((d or {}).get("bilan") or {}).get("phasage") or []:
        i = p.get("annee", 0) - 1
        if 0 <= i < len(feuille):
            p["theme_globale"] = feuille[i].get("theme")
            p["actes_globale"] = [a.get("acte") for a in (feuille[i].get("actes") or [])]


@app.route("/api/cb_periodes")
def api_cb_periodes():
    """Semestres disponibles par année — {"2024": ["S1","S2"], "2026": ["S1"]}.
    Alimente le sélecteur de période du dashboard, qui proposait S1/S2 en dur."""
    return jsonify(AGENTS["CB"].structured.cb_periodes())


@app.route("/api/cb_annees")
def api_cb_annees():
    """Années CB disponibles — dynamique, se met à jour si de nouvelles données sont ajoutées."""
    return jsonify(AGENTS["CB"].structured.cb_annees())


@app.route("/api/cb_banks")
def api_cb_banks():
    """Liste DYNAMIQUE des banques (SELECT DISTINCT en base) — SOURCE UNIQUE pour le front.
    Une banque ajoutée via « Ajouter des données » apparaît ici, donc partout dans l'UI."""
    try:
        banks = list(db.BANKS)
        return jsonify(banks if banks else ["BACI", "BICICI", "BNI", "ECOBANK", "NSIA", "SGCI", "SIB"])
    except Exception:
        return jsonify(["BACI", "BICICI", "BNI", "ECOBANK", "NSIA", "SGCI", "SIB"])


@app.route("/api/kpis")
def api_kpis():
    """KPIs dynamiques Vue d'ensemble — calculés depuis la BD."""
    frais_annee = int(request.args.get("frais_annee", 2026))
    frais_sem   = request.args.get("frais_sem",   "S1")
    frais_seg   = request.args.get("frais_seg",   "Particuliers")
    rn_anx      = int(request.args.get("rn_anx",  3))
    return jsonify(AGENTS["EF"].structured.kpis_vue_ensemble(frais_annee, frais_sem, frais_seg, rn_anx))


@app.route("/api/rn_anx")
def api_rn_anx():
    """Résultat net par ANx (relatif à chaque banque)."""
    anx  = int(request.args.get("anx", 3))
    data = AGENTS["EF"].structured.rn_by_anx(anx)
    return jsonify({b: {"annee": v["annee"], "montant": v["montant"]} for b, v in data.items()})


@app.route("/api/ef_series")
def api_ef_series():
    """Séries temporelles EF (PNB, ROE) pour le graphique filtre ligne."""
    return jsonify({
        "pnb":   AGENTS["EF"].structured.ef_pnb_series(),
        "roe":   AGENTS["EF"].structured.ef_roe_series(),
        "coeff": AGENTS["EF"].structured.ef_coeff_series(),
        "cnr":   AGENTS["EF"].structured.ef_cnr_series(),
    })


@app.route("/api/regl")
def api_regl():
    """Recherche dans les textes réglementaires (sémantique pgvector, repli mots-clés).

    ENDPOINT RÉPARÉ le 2026-07-30 — il renvoyait une erreur 500 sur toute requête, pour deux
    raisons cumulées :
      1. `db.regl_search` et `db.regl_all` n'existent pas dans dash_app/db.py ; les fonctions
         réellement disponibles sont `regl_semantic(q, k)` (avec repli mots-clés intégré) et
         `regl_keyword(q, k)` → AttributeError, donc 500.
      2. même sans cette erreur, la réponse aurait été vide : le mapping lisait `r["texte"]`
         alors que ces fonctions renvoient le champ `contenu`.
    Aucun écran ne consomme cet endpoint aujourd'hui, ce qui explique que la panne soit passée
    inaperçue — mais il aurait échoué au premier branchement.
    """
    q = request.args.get("q", "").strip()
    k = max(1, min(int(request.args.get("k", 6) or 6), 20))
    try:
        if len(q) >= 3:
            rows = db.regl_semantic(q, k)
        else:
            # Requête vide ou trop courte : on présente un échantillon du corpus plutôt que rien.
            rows = db.query(
                "SELECT fichier, contenu FROM regl_documents "
                "WHERE contenu IS NOT NULL AND LENGTH(TRIM(contenu)) > 80 "
                "ORDER BY fichier, chunk_index LIMIT %s", (k,))
    except Exception as e:
        return jsonify({"error": str(e)[:200], "resultats": []}), 200
    return jsonify([
        {"fichier": r.get("fichier", ""),
         "texte":   (r.get("contenu") or "").strip(),
         "score":   r.get("score")}
        for r in rows
    ])


# ══════════════════════════════════════════════════════════════════════
# Chat — RAG réel
# ══════════════════════════════════════════════════════════════════════


# GARDE-FOU (2026-07-22, demande explicite du directeur : « il ne retient pas le contexte,
# trop de problèmes ») — BUG TROUVÉ : chain["memory"] était un objet ConversationMemory UNIQUE
# et GLOBAL, jamais réinitialisé (mem.clear() n'était appelé nulle part dans tout server.py).
# Résultat : TOUTES les conversations (même différentes, même sans lien) partageaient la MÊME
# mémoire — soit elle se mélangeait avec du contexte d'une conversation précédente sans rapport,
# soit une vraie question de suivi n'avait pas le bon historique si une autre question s'était
# glissée entre-temps. Fix : une ConversationMemory PAR conversation (conv_id envoyé par le
# front), jamais partagée. `_chain["memory"]` reste le slot que `chain.ask()` lit déjà — on le
# fait juste pointer vers la bonne mémoire AVANT chaque appel, sans toucher à chain.py.
# 2026-07-25 (audit chat, problème #11) : dict simple → grossit indéfiniment (un conv_id par
# conversation, jamais supprimé) — fuite mémoire lente sur un serveur qui tourne des jours.
# OrderedDict avec éviction LRU : dès que le nombre de conversations en mémoire dépasse
# _CONV_MEMORIES_MAX, la moins récemment utilisée est supprimée (elle repart de zéro si l'
# utilisateur y revient — pas grave, l'historique de conversation redevient juste vide).
from collections import OrderedDict as _OrderedDict
_CONV_MEMORIES = _OrderedDict()
_CONV_MEMORIES_MAX = 200

def _memoire_pour(conv_id):
    global _CONV_MEMORIES
    key = conv_id or "default"
    if key in _CONV_MEMORIES:
        _CONV_MEMORIES.move_to_end(key)
        return _CONV_MEMORIES[key]
    from memory import ConversationMemory
    _CONV_MEMORIES[key] = ConversationMemory()
    if len(_CONV_MEMORIES) > _CONV_MEMORIES_MAX:
        _CONV_MEMORIES.popitem(last=False)
    return _CONV_MEMORIES[key]


# BUG TROUVÉ le 2026-07-23 (signalé par le directeur : "je lui pose des questions il répond
# bête même") — /api/approfondir (boutons "Demander à l'IA" sous les sections dashboard) et
# /api/chat (zone de texte libre) s'affichent dans LA MÊME fenêtre de chat côté front, mais
# ne partageaient AUCUNE mémoire côté serveur : approfondir n'écrivait jamais dans
# _CONV_MEMORIES. Résultat : une question de suivi tapée après un clic "Demander à l'IA"
# (ex. "Quelles sont les hypothèses d'analyse ?" après une analyse de Projection) arrivait
# dans chain.ask() avec une mémoire VIDE pour cette conversation → aucun mot-clé bancaire
# détectable dans une question aussi générale → rejet "hors périmètre", alors qu'elle
# continue une conversation bancaire déjà bien engagée, juste visible plus haut dans le
# même fil. Fix : chaque échange approfondir est aussi versé dans _memoire_pour(conv_id),
# pour que chain.py._resoudre_question_suivi() retrouve un vrai contexte de suivi.
def _bridge_vers_memoire_chat(conv_id, question, reponse):
    try:
        mem = _memoire_pour(conv_id)
        mem.add_user(question)
        mem.add_assistant(reponse)
    except Exception:
        pass


_MOTS_DEMANDE_STRATEGIE = (
    "propose une strategie", "propose une stratégie", "propose la strategie", "propose la stratégie",
    "quelle strategie", "quelle stratégie", "quelle est la strategie", "quelle est la stratégie",
    "recommande une strategie", "recommande une stratégie", "que recommandes-tu comme strategie",
    "que recommandes-tu comme stratégie", "strategie sur la base de", "stratégie sur la base de",
    "strategie a adopter", "stratégie à adopter", "strategie pour sgci", "stratégie pour sgci",
    "que recommandes tu comme strategie", "que recommandes tu comme stratégie",
)


def _est_demande_strategie_globale(question: str) -> bool:
    q = question.strip().lower()
    return any(m in q for m in _MOTS_DEMANDE_STRATEGIE)


# BUG TROUVÉ le 2026-07-25 (signalé par le directeur, testé en direct : "Propose une stratégie
# sur base de mes données" a produit une réponse creuse et non pertinente — le RAG générique
# (retrieval sémantique par embedding) est allé chercher des lignes d'états financiers dont le
# LIBELLÉ ressemblait sémantiquement à "stratégie" ("Effets publics et valeurs assimilées",
# "Gains ou pertes nets sur opérations de négociation") au lieu des VRAIS indicateurs
# stratégiques (PNB, résultat net, ROE, coût du risque, SWOT, Porter, VRIST) que le module
# Stratégie du dashboard (dash_app/strategie.py) calcule déjà, de façon déterministe et
# validée. Le RAG chunk-retrieval n'est simplement PAS le bon outil pour une demande de
# stratégie ouverte — ce n'est pas une info ponctuelle à retrouver dans un document, c'est une
# synthèse déjà construite ailleurs dans l'app. Fix : router ce type de question vers les VRAIES
# données déjà calculées (même fonction `_resume_facts_strategie` que le PDF), au lieu du RAG.
def _repondre_strategie_chat(question: str, segment: str = "Particuliers") -> str:
    from groq import Groq as _Groq
    facts = _resume_facts_strategie(segment)
    system_prompt = (
        "Tu es un conseiller stratégique pour SGCI (banque ivoirienne). Réponds à la question de "
        "l'utilisateur en t'appuyant UNIQUEMENT sur les données stratégiques fournies ci-dessous "
        "(déjà calculées et validées par l'app — diagnostic, SWOT, Porter, VRIST, plan 3 ans, "
        "projection à 3 scénarios). N'invente AUCUN chiffre absent de ces données. Structure ta "
        "réponse en français, claire et actionnable : le problème prioritaire, la recommandation, "
        "les chiffres qui la justifient."
    )
    user_prompt = f"=== DONNÉES STRATÉGIQUES SGCI (segment {segment}) ===\n{facts}\n\n=== QUESTION ===\n{question}"
    groq_keys = [k for k in [
        os.getenv("GROQ_API_KEY_11", ""), os.getenv("GROQ_API_KEY_12", ""),
        os.getenv("GROQ_API_KEY_9", ""), os.getenv("GROQ_API_KEY_10", ""),
        os.getenv("GROQ_API_KEY_8", ""), os.getenv("GROQ_API_KEY_6", ""),
        os.getenv("GROQ_API_KEY_7", ""), os.getenv("GROQ_API_KEY_5", ""),
        os.getenv("GROQ_API_KEY", ""),   os.getenv("GROQ_API_KEY_2", ""),
        os.getenv("GROQ_API_KEY_3", ""), os.getenv("GROQ_API_KEY_4", ""),
    ] if k]
    for key in groq_keys:
        try:
            client = _Groq(api_key=key)
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_prompt}],
                temperature=0.3, max_tokens=1200,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            continue
    return ("Le module stratégie n'est temporairement pas disponible (quota IA). Consulte "
            "l'onglet Stratégie du dashboard pour l'analyse complète.")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    body     = request.get_json(force=True, silent=True) or {}
    question = (body.get("question") or "").strip()
    conv_id  = body.get("conv_id")
    if not question:
        return jsonify({"error": "question manquante"}), 400

    if _est_demande_strategie_globale(question):
        try:
            reponse = _repondre_strategie_chat(question)
            _bridge_vers_memoire_chat(conv_id, question, reponse)
            return jsonify({"reponse": reponse, "source": "strategie"})
        except Exception as e:
            return jsonify({"reponse": f"⚠️ Erreur stratégie : {e}", "source": "error"})

    if _RAG_OK and _chain:
        try:
            _chain["memory"] = _memoire_pour(conv_id)
            reponse = ask(_chain, question)
            return jsonify({"reponse": reponse, "source": "rag"})
        except Exception as e:
            return jsonify({"reponse": f"⚠️ Erreur RAG : {e}", "source": "error"})

    return jsonify({
        "reponse": "💬 Le chat IA n'est pas disponible sur cet environnement (ressources insuffisantes pour le modèle de recherche sémantique). Le reste du dashboard fonctionne normalement.",
        "source": "offline",
    })


# Historique des conversations — persisté CÔTÉ SERVEUR (en plus du localStorage navigateur).
# Raison : localStorage est isolé PAR ORIGINE (protocole+hôte+port) — un même serveur Flask
# accédé tantôt via http://localhost:5000, tantôt via http://127.0.0.1:5000 ou l'IP LAN
# (192.168.x.x:5000, cf. logs serveur montrant les deux) donne 3 historiques localStorage
# DIFFÉRENTS et isolés, ce qui se manifeste pour l'utilisateur comme un historique qui
# « disparaît ». Le fichier ci-dessous est commun à toutes les origines puisqu'il vit sur
# le serveur, pas dans le navigateur — la source de vérité ne dépend donc plus de l'URL
# utilisée pour accéder à l'app.
_CONV_HISTORY_FILE = os.path.join(DOSSIER_CACHE, "chat_conversations.json")


@app.route("/api/conv_history", methods=["GET"])
def api_conv_history_get():
    try:
        with open(_CONV_HISTORY_FILE, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify([])


@app.route("/api/conv_history", methods=["POST"])
def api_conv_history_post():
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, list):
        return jsonify({"ok": False, "error": "payload doit être une liste"}), 400
    try:
        with open(_CONV_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(body[:100], f, ensure_ascii=False, indent=2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/cb_bd")
def api_cb_bd():
    """Positionnement CB réel — tarif minimum par banque pour chaque service clé."""
    annee   = int(request.args.get("annee",   2026))
    sem     = request.args.get("semestre", "S1")
    seg     = request.args.get("segment",  "Particuliers")
    data    = AGENTS["CB"].structured.cb_positionnement_bd(annee, sem, seg)
    return jsonify(data)


@app.route("/api/cb_exhaustif")
def api_cb_exhaustif():
    """Tous les tarifs CB exhaustifs — aucun agrégat, toutes banques, tous services."""
    annee = int(request.args.get("annee",   2026))
    sem   = request.args.get("semestre", "S1")
    seg   = request.args.get("segment",  "Particuliers")
    return jsonify(AGENTS["CB"].structured.cb_exhaustif(annee, sem, seg))


@app.route("/api/cb_par_section")
def api_cb_par_section():
    """Comparatif CB par GRANDE SECTION CANONIQUE BCEAO (I à IX) — axe de
    rapprochement entre banques aux libellés différents (cf. cb_sections.py)."""
    annee = int(request.args.get("annee",   2026))
    sem   = request.args.get("semestre", "S1")
    seg   = request.args.get("segment",  "Particuliers")
    return jsonify(AGENTS["CB"].structured.cb_par_section(annee, sem, seg))


@app.route("/api/cb_par_sous_section")
def api_cb_par_sous_section():
    """Comparatif CB par SOUS-SECTION (un niveau sous les 9 grandes sections
    BCEAO, cf. cb_subsections.py) — sépare les familles de tarifs hétérogènes
    qu'une comparaison au niveau section mélange (ex. I "Ouverture de compte"
    vs "Clôture de compte")."""
    annee = int(request.args.get("annee",   2026))
    sem   = request.args.get("semestre", "S1")
    seg   = request.args.get("segment",  "Particuliers")
    return jsonify(AGENTS["CB"].structured.cb_par_sous_section(annee, sem, seg))


@app.route("/api/cb_imputations")
def api_cb_imputations():
    """Transparence d'imputation CB : par banque, période demandée vs utilisée
    (règle métier S1<->S2 même année si donnée absente/insuffisante)."""
    annee = int(request.args.get("annee",   2026))
    sem   = request.args.get("semestre", "S1")
    seg   = request.args.get("segment",  "Particuliers")
    return jsonify(AGENTS["CB"].structured.cb_imputations(annee, sem, seg))


@app.route("/api/resilience")
def api_resilience():
    """Ratios de résilience / solidité bancaire — Section ⑤."""
    anx = int(request.args.get("anx", 3))
    return jsonify(AGENTS["EF"].structured.resilience_data(anx))


@app.route("/api/approfondir", methods=["POST"])
def api_approfondir():
    """
    Analyse approfondie contextualisée — reçoit la question + les KPIs live du dashboard.
    Construit un prompt riche avec les vraies données et appelle le LLM directement.
    """
    from groq import Groq as _Groq
    body     = request.get_json(force=True, silent=True) or {}
    question = (body.get("question") or "").strip()
    kpis     = body.get("kpis", {})   # données live envoyées par le front
    section_facts = body.get("section_facts")   # 2026-07-22 : vrais chiffres DÉJÀ CALCULÉS de la section cliquée
    conv_id  = body.get("conv_id")    # 2026-07-23 : pour verser cet échange dans la mémoire du chat (voir _bridge_vers_memoire_chat)

    if not question:
        return jsonify({"error": "question manquante"}), 400

    # ── Construire le contexte chiffré depuis les données live ────────────
    ctx_lines = ["=== DONNÉES RÉELLES DU MARCHÉ BANCAIRE IVOIRIEN (7 banques) ==="]

    if kpis.get("pnb"):
        pnb = kpis["pnb"]
        ctx_lines.append(f"PNB (Produit Net Bancaire, AN3) : " +
            ", ".join(f"{b}={round(v/1000,1)} Mds FCFA" for b,v in sorted(pnb.items(), key=lambda x:-x[1])))

    if kpis.get("rn"):
        rn = kpis["rn"]
        ctx_lines.append(f"Résultat Net (AN3) : " +
            ", ".join(f"{b}={round(v/1000,1)} Mds FCFA" for b,v in sorted(rn.items(), key=lambda x:-x[1])))

    if kpis.get("marge"):
        ctx_lines.append(f"Marge nette = RN/PNB (%) : " +
            ", ".join(f"{b}={v}%" for b,v in sorted(kpis["marge"].items(), key=lambda x:-x[1])))

    if kpis.get("cout_risque"):
        ctx_lines.append(f"Coût du risque/PNB (%) : " +
            ", ".join(f"{b}={v}%" for b,v in sorted(kpis["cout_risque"].items(), key=lambda x:x[1])))

    if kpis.get("coeff"):
        ctx_lines.append(f"Coefficient d'exploitation (%) : " +
            ", ".join(f"{b}={v}%" for b,v in sorted(kpis["coeff"].items(), key=lambda x:x[1])))

    if kpis.get("roe"):
        ctx_lines.append(f"ROE - Return on Equity (%) : " +
            ", ".join(f"{b}={v}%" for b,v in sorted(kpis["roe"].items(), key=lambda x:-x[1])))

    if kpis.get("growths"):
        ctx_lines.append(f"Croissance AN1→AN3 (%) : " +
            ", ".join(f"{b}={v:+.1f}%" for b,v in sorted(kpis["growths"].items(), key=lambda x:-x[1])))

    ctx_lines += [
        "",
        "=== CONTEXTE SGCI ===",
        "SGCI est la plus grande banque du marché ivoirien.",
        "Paradoxe identifié : #1 en PNB et en maîtrise des charges, mais dernière en marge nette à cause du coût du risque crédit le plus élevé du marché (17%).",
        "Concurrent à surveiller : BICICI (+119% en 3 ans, coût du risque 1.9%).",
        "Formules : Marge nette = RN/PNB×100 | Coût du risque = |Provisions|/PNB×100 | ROE = RN/Capitaux propres×100",
    ]

    # GARDE-FOU (2026-07-22, bug trouvé : un clic « Approfondir » sur la Projection avait fait
    # inventer au LLM sa PROPRE projection à 3 ans — cible de coût du risque à 10%, calcul même
    # faux (21 Mds au lieu de 19,32) — car il ne recevait QUE les KPIs génériques ci-dessus,
    # jamais les vrais scénarios prudent/central/optimiste déjà calculés pour CETTE section)
    # section_facts contient les VRAIS chiffres déjà calculés de la section précise cliquée —
    # prioritaires sur toute extrapolation du LLM.
    section_facts_txt = ""
    if section_facts:
        try:
            section_facts_txt = json.dumps(section_facts, ensure_ascii=False, indent=1)
        except Exception:
            section_facts_txt = ""
    if section_facts_txt:
        ctx_lines += [
            "",
            "=== DONNÉES RÉELLES DE LA SECTION PRÉCISE DEMANDÉE (source de vérité PRIORITAIRE, "
            "déjà calculées par le dashboard — ne recalcule rien, ne remplace ces chiffres par "
            "aucune estimation personnelle) ===",
            section_facts_txt,
        ]

    system_prompt = (
        "Tu es un expert en analyse financière bancaire pour le marché ivoirien (UEMOA). "
        "Tu réponds toujours en français, avec précision et pédagogie. "
        "Tu t'appuies UNIQUEMENT sur les données chiffrées fournies — pas d'invention. "
        # STRUCTURE REVUE le 2026-07-28 (le directeur : « on ne peut pas fournir une meilleure
        # structure ? »). L'ancienne consigne — « explication, chiffres, implications métier,
        # recommandation » — imposait QUATRE blocs à toute question, même la plus simple : on
        # obtenait un paragraphe d'introduction générique avant d'arriver à la réponse, puis les
        # mêmes chiffres répétés dans trois sections. Un dirigeant veut la réponse en premier.
        # Le nombre de sections s'adapte désormais à la question, et la 1ʳᵉ phrase répond.
        "FORME DE LA RÉPONSE :\n"
        "1. Commence par LA RÉPONSE en une ou deux phrases — jamais de préambule, jamais de "
        "rappel de la question, jamais « il est essentiel de considérer plusieurs facteurs ».\n"
        "2. Puis les chiffres qui la justifient, en liste à puces courtes (« - »), un fait par "
        "puce, le chiffre en gras.\n"
        "3. Termine par « ### Ce que ça implique » : 2 à 4 phrases actionnables.\n"
        "N'ajoute une section « ### » que si la réponse en a réellement besoin : 2 sections "
        "valent mieux que 4 sections à moitié vides. Titres en « ### » uniquement (jamais « # » "
        "ni « ## »), courts, sans numérotation. Pas de conclusion qui répète l'introduction. "
        "350 mots maximum. "
        + ("GARDE-FOU ABSOLU : la section « DONNÉES RÉELLES DE LA SECTION PRÉCISE DEMANDÉE » ci-dessous "
           "est la SEULE source pour tout chiffre de projection/scénario/cible future — si tu dois "
           "chiffrer un objectif à 3 ans, une cible de réduction, ou tout calcul dérivé, utilise "
           "EXCLUSIVEMENT ces valeurs déjà calculées (jamais un pourcentage cible inventé comme "
           "'10%' ou '45%'). Si l'information n'y figure pas, dis-le explicitement au lieu d'estimer."
           if section_facts_txt else "")
    )

    user_prompt = ("\n".join(ctx_lines) + f"\n\n=== QUESTION ===\n{question}\n\n"
                   "Réponds de façon dense et actionnable : la réponse d'abord, les chiffres "
                   "ensuite. Aucune phrase de remplissage.")

    # ── Appel LLM Groq ────────────────────────────────────────────────────
    groq_keys = [k for k in [
        os.getenv("GROQ_API_KEY_11",""), os.getenv("GROQ_API_KEY_12",""),
        os.getenv("GROQ_API_KEY_9",""), os.getenv("GROQ_API_KEY_10",""),
        os.getenv("GROQ_API_KEY_8",""), os.getenv("GROQ_API_KEY_6",""),
        os.getenv("GROQ_API_KEY_7",""), os.getenv("GROQ_API_KEY_5",""),
        os.getenv("GROQ_API_KEY",""),   os.getenv("GROQ_API_KEY_2",""),
        os.getenv("GROQ_API_KEY_3",""), os.getenv("GROQ_API_KEY_4",""),
    ] if k]

    last_err = None
    for key in groq_keys:
        try:
            client = _Groq(api_key=key)
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=1200,
            )
            answer = resp.choices[0].message.content.strip()
            _bridge_vers_memoire_chat(conv_id, question, answer)
            return jsonify({"reponse": answer, "source": "approfondir"})
        except Exception as e:
            last_err = str(e)
            continue

    # Fallback RAG si Groq indisponible
    if _RAG_OK and _chain:
        try:
            from rag_bridge import ask
            answer = ask(_chain, question)
            _bridge_vers_memoire_chat(conv_id, question, answer)
            return jsonify({"reponse": answer, "source": "rag_fallback"})
        except Exception:
            pass

    return jsonify({
        "reponse": f"⚠️ Service IA temporairement indisponible. ({last_err or 'Vérifiez les clés Groq dans .env'})",
        "source": "offline"
    })


@app.route("/api/radar_agent")
def api_radar_agent():
    """
    Portrait compétitif intelligent — l'agent LLM reçoit TOUTES les données
    EF + CB et choisit librement ses 5 dimensions + scores + explications.
    Aucune métrique imposée côté serveur.
    """
    import json as _json
    from groq import Groq as _Groq

    bank  = request.args.get("bank",  "SGCI")
    annee = int(request.args.get("annee", 2026))
    sem   = request.args.get("sem",   "S1")
    seg   = request.args.get("seg",   "Particuliers")
    anx   = int(request.args.get("anx", 3))

    try:
        # ── 1. Données EF ──────────────────────────────────────────────────
        ef_all  = AGENTS["EF"].structured.ef_series_all_for_agent()
        ef_lines = []
        for b, d in ef_all.items():
            pts = " → ".join(
                f"AN{s['anx']}={s['annee']}({s['montant']:,.0f}M)" for s in d["series"]
            )
            g   = d.get("croissance_an1_an3")
            sgn = "+" if g and g >= 0 else ""
            g_s = f"{sgn}{g:.1f}%" if g is not None else "N/D"
            ef_lines.append(f"{b:8}: {pts} | Δ AN1→AN3: {g_s}")

        # ── 2. Données CB — sémantique si vectorisé, SQL sinon ────────────
        from retriever import (PGVectorStore as _PGVectorStore,
                               search as _rag_search,
                               build_filters as _build_filters)

        _vs = _chain["vectorstore"] if _RAG_OK and _chain else _PGVectorStore()

        # Vérifier si CB est vectorisé
        with _vs.get_conn() as _c:
            with _c.cursor() as _cur:
                _cur.execute("SELECT COUNT(*) FROM cb_tarifs WHERE embedding IS NOT NULL")
                _cb_vect = _cur.fetchone()[0] > 0

        # LA RECHERCHE SEMANTIQUE EXIGE LE MODELE LOCAL (2026-08-07).
        # `_cb_vect` dit seulement que les lignes PORTENT un vecteur en base ; il ne dit rien
        # de la capacite a encoder la QUESTION, qui reclame sentence-transformers. Or
        # requirements-deploy.txt exclut deliberement torch et sentence-transformers (2+ Go,
        # hors des 512 Mo du plan gratuit) : le chat le gere via _RAG_OK, mais ce radar-ci ne
        # le consultait pas. Sur un deploiement allege, il serait tombe sur un ImportError
        # alors qu'un repli SQL complet existe juste en dessous.
        _cb_vect = _cb_vect and _RAG_OK

        cb_lines   = []
        # Liste DYNAMIQUE des banques (SGCI d'abord, puis les autres depuis la base) → une nouvelle
        # banque ajoutée est automatiquement prise en compte par le radar. Plus aucune liste figée.
        _banks_ord = ["SGCI"] + [b for b in db.BANKS if b != "SGCI"]
        _source    = "sémantique" if _cb_vect else "SQL fallback"
        cb_lines.append(f"[Source CB : {_source} — {annee} {sem} {seg}]")

        if _cb_vect:
            # Recherche sémantique : chunks les plus représentatifs par banque
            _query = f"frais commissions tarifs services bancaires {seg}"
            for b in _banks_ord:
                _filters = _build_filters(banque=b, annee=annee,
                                          semestre=sem, type_doc="conditions_banque")
                _chunks  = _rag_search(_vs, _query, k=30, filters=_filters)
                if not _chunks:
                    cb_lines.append(f"\n=== {b} ===\n(Données non disponibles {annee} {sem})")
                    continue
                cb_lines.append(f"\n=== {b} ({len(_chunks)} entrées) ===")
                _seen = set()
                for _ch in _chunks:
                    _t = (_ch.get("texte") or "").strip()
                    if not _t or _t[:40] in _seen:
                        continue
                    _seen.add(_t[:40])
                    cb_lines.append(f"  {_t[:130]}")
        else:
            # Fallback SQL jusqu'à vectorisation complète
            cb_all = AGENTS["CB"].structured.cb_all_for_period(annee, sem, seg)
            for b in _banks_ord:
                rows = cb_all.get(b, [])
                if not rows:
                    cb_lines.append(f"\n=== {b} ===\n(Données non disponibles)")
                    continue
                cb_lines.append(f"\n=== {b} ({len(rows)} services) ===")
                seen, shown = set(), 0
                for r in rows:
                    key = r["libelle"][:50].lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    cb_lines.append(f"  {r['libelle'][:65]}: {r['valeur']}")
                    shown += 1
                    if shown >= 50:
                        cb_lines.append(f"  ...({len(rows)-shown} autres)")
                        break

        # ── 3. Axes 1-5 : tous calculés depuis la BD (dynamique) ─────────────
        growths    = AGENTS["EF"].structured.croissance_series()
        rn_an3     = AGENTS["EF"].structured.rn_by_anx(anx)
        roe_data   = AGENTS["EF"].structured.roe_by_anx(anx)
        rn_sorted  = sorted(rn_an3.items(), key=lambda x: x[1]["montant"], reverse=True)
        grw_sorted = sorted(growths.items(),  key=lambda x: x[1], reverse=True)
        roe_sorted = sorted(roe_data.items(), key=lambda x: x[1], reverse=True)
        n_banks    = len(rn_sorted)
        n_grw      = len(grw_sorted)
        n_roe      = len(roe_sorted)

        bank_rn_val   = rn_an3.get(bank, {}).get("montant", 0)
        bank_rn_annee = rn_an3.get(bank, {}).get("annee", "")
        bank_rn_rank  = next((i+1 for i,(b,_) in enumerate(rn_sorted)  if b==bank), n_banks)
        bank_grw_rank = next((i+1 for i,(b,_) in enumerate(grw_sorted) if b==bank), n_grw)
        bank_roe_rank = next((i+1 for i,(b,_) in enumerate(roe_sorted) if b==bank), n_roe)
        bank_grw_val  = growths.get(bank)
        bank_roe_val  = roe_data.get(bank)
        sgn_grw       = "+" if bank_grw_val and bank_grw_val >= 0 else ""

        total_rn   = sum(v["montant"] for v in rn_an3.values())
        bank_share = round(bank_rn_val / total_rn * 100, 1) if total_rn else 0

        bank_idx = next((i for i,(b,_) in enumerate(rn_sorted) if b==bank), 0)
        if bank_idx == 0 and n_banks > 1:
            v_direct, nom_direct = rn_sorted[1][1]["montant"], rn_sorted[1][0]
        else:
            v_direct, nom_direct = rn_sorted[0][1]["montant"], rn_sorted[0][0]
        ecart_direct = round((bank_rn_val - v_direct) / v_direct * 100, 1) if v_direct else 0

        s_rn  = round((n_banks - bank_rn_rank + 1) / n_banks * 100)
        s_pdm = min(100, round(bank_share * n_banks / 2))
        s_pos = min(100, max(0, round(50 + ecart_direct / 2)))
        s_dyn = round((n_grw - bank_grw_rank + 1) / n_grw * 100)
        s_roe = round((n_roe - bank_roe_rank + 1) / n_roe * 100) if n_roe else 50

        grw_top3 = [(b, g) for b, g in grw_sorted[:3]]
        rn_top3  = [(b, v["montant"]) for b, v in rn_sorted[:3]]
        roe_top3 = [(b, r) for b, r in roe_sorted[:3]]

        pos_label = "Avance sur #2" if bank_idx == 0 else "Écart vs leader"
        pos_info  = (f"{'+' if ecart_direct>=0 else ''}{ecart_direct:.0f}% "
                     f"{'au-dessus de' if bank_idx==0 else 'derrière'} {nom_direct}")
        roe_expl  = (f"{bank} : {bank_roe_val:.1f}% ROE — #{bank_roe_rank}/{n_roe}. "
                     f"Top 3 : {', '.join(f'{b}={r:.1f}%' for b,r in roe_top3)}."
                     ) if bank_roe_val else f"Données ROE non disponibles pour {bank}."

        final_dims = [
            {"label": "Résultat net",
             "score": s_rn,
             "explication": (
                 f"{bank} : {bank_rn_val:,.0f} M FCFA ({bank_rn_annee}), #{bank_rn_rank}/{n_banks}. "
                 f"Top 3 : {', '.join(f'{b}={v:,.0f}M' for b,v in rn_top3)}. "
                 f"→ Mesure la performance financière absolue.")},
            {"label": "Part bénéfices",
             "score": s_pdm,
             "explication": (
                 f"{bank} génère {bank_share:.1f}% des bénéfices cumulés des {n_banks} banques "
                 f"(moyenne = {100/n_banks:.1f}%). "
                 f"→ Mesure l'emprise sectorielle sur les profits : qui capte le plus de valeur.")},
            {"label": pos_label,
             "score": s_pos,
             "explication": (
                 f"{bank} {pos_info}. Score 50 = à égalité avec le concurrent direct. "
                 f"→ Mesure le confort concurrentiel : distance de sécurité.")},
            {"label": "Dynamique AN1→AN3",
             "score": s_dyn,
             "explication": (
                 f"{bank} : {sgn_grw}{bank_grw_val:.1f}% sur 3 ans, #{bank_grw_rank}/{n_grw}. "
                 f"Plus rapide : {grw_top3[0][0]} ({grw_top3[0][1]:+.1f}%). "
                 f"→ Mesure la trajectoire : qui accélère ou décroche.")},
            {"label": "ROE",
             "score": s_roe,
             "explication": (
                 f"{roe_expl} "
                 f"→ Mesure l'efficacité du capital : combien chaque franc investi rapporte.")},
        ]

        # SCORES 100% math depuis la BD (dynamique) ; les EXPLICATIONS + la SYNTHÈSE sont
        # RÉDIGÉES PAR LE LLM à partir de ces faits (registre soutenu, zéro hallucination).
        # ÉVOLUTIF : clé de cache = hash des faits → nouvelles données ⇒ régénération auto.
        # Fallback : les explications factuelles déterministes si le LLM est indisponible.
        try:
            import hashlib as _hl3
            _facts_rad = "\n".join(f"- {x['label']} : score {x['score']}/100 — {x['explication']}" for x in final_dims)
            _rk = f"radar_llm_v1_{bank}_{_hl3.md5(_facts_rad.encode('utf-8')).hexdigest()[:10]}"
            _marks = "\n".join(f"@@d{i+1}@@\n… (2 phrases : le fait + son implication pour {bank})" for i in range(len(final_dims)))
            _pr = (f"Tu es analyste financier senior du secteur bancaire ivoirien. Portrait compétitif de {bank} "
                   f"(score 50 = moyenne du marché, 100 = meilleur) — FAITS RÉELS :\n{_facts_rad}\n\n"
                   f"Pour CHAQUE dimension, rédige 2 phrases en français SOUTENU (une par ligne, point puis « <br> ») : "
                   f"le constat chiffré, puis l'implication concrète pour {bank}. Puis @@syn@@ : 2 phrases de synthèse "
                   f"d'ensemble (le profil de {bank} en un regard : où elle excelle, où elle est vulnérable). "
                   f"N'invente AUCUN chiffre. INTERDIT : « cela signifie que », « il est important de ».\n\n"
                   f"FORMAT (marqueurs, PAS de JSON) :\n{_marks}\n@@syn@@\n…")
            _r = _groq_call_cb(_pr, _rk, max_tokens=900, temperature=0.3)
            _tx = (_r.get("analyse") or "")
            if _tx:
                _sg = _re_rp.split(r"@@\s*([a-zA-Z0-9_]+)\s*@@", _tx)
                _pd = {}
                for _i in range(1, len(_sg) - 1, 2):
                    _k2, _v2 = _sg[_i].strip(), _sg[_i + 1].strip().strip("`").strip()
                    if _v2 and not _v2.startswith("…"):
                        _pd[_k2] = _llm_polish(_llm_br(_v2))
                for _i, _dim in enumerate(final_dims):
                    if _pd.get(f"d{_i+1}"):
                        _dim["explication"] = _pd[f"d{_i+1}"]
                _syn = _pd.get("syn", "")
            else:
                _syn = ""
        except Exception:
            _syn = ""
        return jsonify({
            "ok":   True,
            "bank": bank,
            "data": {"dimensions": final_dims, "synthese": _syn},
        })

        # (ancien chemin LLM inatteignable supprimé — remplacé par le bloc LLM caché ci-dessus)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


def _concurrents_txt():
    """Liste des concurrents de SGCI (toutes les banques sauf SGCI), dynamique — voir
    db.BANKS/refresh_banks(). Utilisé dans les prompts LLM CB qui énuméraient auparavant les
    6 concurrents en dur (« absents de BICICI, SIB, BACI, NSIA, ECOBANK et BNI »), ce qui
    aurait omis silencieusement toute banque ajoutée après les 7 historiques."""
    return ", ".join(b for b in db.BANKS if b != "SGCI") or "BACI, BICICI, BNI, ECOBANK, NSIA, SIB"


def _fmt_strategic_ctx(q_id, data, annee, semestre, segment):
    """Formate les données SQL en texte structuré pour le LLM stratégique."""
    lines = []

    if q_id == 1:
        # Pivot : par banque, montrer l'évolution des 3 indicateurs clés. Itère sur les
        # banques RÉELLEMENT présentes dans `data` (pas une liste figée) : une banque
        # nouvellement ajoutée dont la requête SQL en amont renvoie des lignes doit
        # apparaître ici sans qu'on ait à éditer ce fichier.
        pivot = {}
        for r in data:
            pivot.setdefault(r["banque"], []).append(r)
        for b in sorted(pivot.keys()):
            pts = pivot.get(b, [])
            if not pts:
                continue
            lines.append(f"\n{b} :")
            for p in pts:
                n   = p.get("n_services") or 0
                ng  = p.get("n_gratuit") or 0
                moy = int(p.get("montant_moyen") or 0)
                pct = round(100 * ng / n, 1) if n else 0
                lines.append(
                    f"  {p['annee']} {p['semestre']} — "
                    f"{n} services | {ng} gratuits ({pct}%) | "
                    f"prix moyen {moy:,} F CFA"
                )

    elif q_id == 2:
        if not data:
            return f"Aucun nouveau service SGCI détecté entre 2024 et {annee} {semestre}."
        by_sec = {}
        for r in data:
            by_sec.setdefault(r.get("section", "Autre"), []).append(r)
        lines.append(f"NOUVEAUX SERVICES SGCI ({segment}) :\n")
        for sec, items in by_sec.items():
            lines.append(f"Section : {sec}")
            for it in items:
                val = "GRATUIT" if it.get("est_gratuit") else (it.get("valeur_propre") or "")
                lines.append(f"  + [{it['annee_apparition']}] {it['libelle']} — {val}")

    elif q_id in (3, 4):
        if not data:
            return "Aucun service exclusivement SGCI détecté — les libellés sont présents chez au moins un concurrent."
        by_sec = {}
        for r in data:
            by_sec.setdefault(r.get("section", "Autre"), []).append(r)
        n_gratuit = sum(1 for r in data if r.get("est_gratuit"))
        lines.append(
            f"SERVICES EXCLUSIFS SGCI — {annee} {semestre} {segment} "
            f"({len(data)} services, dont {n_gratuit} GRATUITS) :\n"
        )
        for sec, items in by_sec.items():
            lines.append(f"\nSection : {sec}")
            for it in items:
                val = "GRATUIT" if it.get("est_gratuit") else (it.get("valeur_propre") or "N/A")
                lines.append(f"  ★ {it['libelle']} — {val}")
        if q_id == 4:
            lines.append(
                f"\nRÉSUMÉ DIFFÉRENCIATION : {len(data)} services uniques SGCI, "
                f"{n_gratuit} offerts gratuitement quand les concurrents les facturent."
            )

    elif q_id == 5:
        if not data:
            return "Aucun gap détecté — SGCI couvre tous les services proposés par ses concurrents."
        by_sec = {}
        for r in data:
            by_sec.setdefault(r.get("section", "Autre"), []).append(r)
        lines.append(
            f"GAPS SGCI — Services présents chez les concurrents, absents chez SGCI "
            f"({annee} {semestre} {segment}) :\n"
        )
        for sec, items in by_sec.items():
            lines.append(f"\nSection : {sec}")
            for it in items[:20]:
                nb    = it.get("nb_banques", 1)
                banqs = it.get("banques_concurrentes", "")
                val   = "GRATUIT" if it.get("est_gratuit") else (it.get("valeur_propre") or "")
                lines.append(
                    f"  ✗ {it['libelle']} — {val} "
                    f"[{nb} banque(s) : {banqs}]"
                )

    elif q_id == 6:
        lines.append(
            f"CLASSEMENT MARCHÉ — {segment} {semestre} {annee}\n"
            f"{'#':<3} {'Banque':<10} {'Services':>9} {'%Gratuit':>9} "
            f"{'Moy.F':>10} {'Min.F':>10} {'Max.F':>12}"
        )
        lines.append("-" * 68)
        for i, r in enumerate(data, 1):
            b    = r.get("banque", "?")
            n    = r.get("n_services") or 0
            pct  = r.get("pct_gratuit") or 0
            moy  = int(r.get("montant_moyen") or 0)
            mn   = int(r.get("montant_min") or 0)
            mx   = int(r.get("montant_max") or 0)
            mark = " ★" if b == "SGCI" else ""
            lines.append(
                f"{i:<3} {b+mark:<12} {n:>9} {pct:>8.1f}% "
                f"{moy:>10,} {mn:>10,} {mx:>12,}"
            )

    return "\n".join(lines)


def _QUESTIONS_STRATEGIQUES(annee=2026, semestre="S1"):
    return {
    1: f"Sur la période 2024 → {annee} {semestre}, qu'est-ce qui a globalement changé chez SGCI par rapport à ses concurrents ? Analyser l'évolution du volume de services et des prix.",
    2: f"Quels sont les nouveaux produits et services développés par SGCI depuis 2024 jusqu'à {annee} {semestre} ? Identifier les innovations réelles.",
    3: "Qu'avons-nous chez SGCI que les concurrents n'ont pas, en termes de services ou produits ?",
    4: "SGCI a-t-il un facteur différenciant fort (type VRIST) par rapport au marché ? Lequel, et est-il stratégiquement défendable ?",
    5: "Qu'est-ce que les concurrents ont que SGCI n'a pas ? Identifier et prioriser les gaps par criticité marché.",
    6: "Faire une analyse statistique synthétique du marché : qui est le plus cher, le moins cher, où et pourquoi ?",
}


@app.route("/api/cb_strat_data")
def api_cb_strat_data():
    """Données brutes CB pour les 6 axes stratégiques — SANS LLM, zéro hallucination."""
    q_id     = int(request.args.get("q", 6))
    annee    = int(request.args.get("annee",    2026))
    semestre = request.args.get("semestre", "S1")
    segment  = request.args.get("segment",  "Particuliers")
    banque   = request.args.get("banque", "SGCI")

    # MIS EN CACHE EN BASE (2026-08-10). C'est l'appel qui porte le contenu de l'écran
    # « Conditions bancaires » — cinq requêtes, une par axe. Mesuré après un redéploiement,
    # caches vidés : le texte n'apparaissait qu'à la 24ᵉ seconde. Les @lru_cache qui protègent
    # ces calculs meurent avec le processus, et l'hébergeur en redémarre un neuf à chaque
    # réveil comme à chaque mise à jour : le premier visiteur payait tout.
    cle = f"cb_strat_data:{q_id}:{annee}:{semestre}:{segment}" + (f":{banque}" if q_id == 1 else "")

    def _calculer():
        if q_id == 1:
            return {
                "banques":        AGENTS["CB"].structured.cb_analyse_q1(segment),
                "evolution":      AGENTS["CB"].structured.cb_evolution_details(segment, banque),
                # evolutions_all chargé séparément via /api/cb_evolutions_all (trop lent pour le bundle Q1)
            }
        if q_id == 2:      return AGENTS["CB"].structured.cb_analyse_q2(annee, semestre, segment)
        if q_id in (3, 4): return AGENTS["CB"].structured.cb_analyse_q3(annee, semestre, segment)
        if q_id == 5:      return AGENTS["CB"].structured.cb_analyse_q5(annee, semestre, segment)
        if q_id == 6:      return AGENTS["CB"].structured.cb_analyse_q6(annee, semestre, segment)
        return None

    try:
        if q_id not in (1, 2, 3, 4, 5, 6):
            return jsonify({"error": "q invalide (1-6)"}), 400
        data = servir_avec_cache(cle, _calculer)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(data)


@app.route("/api/cb_prix_par_libelle")
def api_cb_prix_par_libelle():
    """Comparaison prix service par service : chaque libellé SGCI → prix chez chaque concurrent."""
    annee    = int(request.args.get("annee",    2026))
    semestre = request.args.get("semestre", "S1")
    segment  = request.args.get("segment",  "Particuliers")
    try:
        data = AGENTS["CB"].structured.cb_prix_par_libelle(annee, semestre, segment)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(data)


@app.route("/api/cb_prix_competitivite")
def api_cb_prix_competitivite():
    """Indice de compétitivité tarifaire (win-rate) : classe les banques par fréquence
    où elles sont les moins chères sur un panier de services comparables."""
    annee    = int(request.args.get("annee",    2026))
    semestre = request.args.get("semestre", "S1")
    segment  = request.args.get("segment",  "Particuliers")
    try:
        data = AGENTS["CB"].structured.cb_prix_competitivite(annee, semestre, segment)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(data)


# ══════════════════════════════════════════════════════════════════════════════
# REPRICING — « quelle action tarifaire pour ce service ? »
# Faits déterministes (prix SGCI vs concurrents/médiane, tirés de cb_prix_par_libelle)
# + verdict STRATÉGIQUE généré par LLM (Groq maintenant, Claude dès crédit) PUIS STOCKÉ.
# Le verdict n'est PAS une règle figée : l'IA juge produit par produit (un prix bas peut
# être une arme d'acquisition à préserver ; un autre peut monter sans perdre de part de marché).
# ══════════════════════════════════════════════════════════════════════════════
import re as _re_rp

_REPRICING_CACHE_FILE = os.path.join(DOSSIER_CACHE, "cb_repricing_cache.json")
_REPRICING_CACHE: dict = {}
_REPRICING_LOADED = False


def _rp_load():
    global _REPRICING_LOADED
    if _REPRICING_LOADED:
        return
    try:
        if os.path.exists(_REPRICING_CACHE_FILE):
            with open(_REPRICING_CACHE_FILE, "r", encoding="utf-8") as f:
                _REPRICING_CACHE.update(json.load(f))
    except Exception as e:
        print(f"[repricing] cache load: {e}")
    _REPRICING_LOADED = True


def _rp_persist():
    try:
        with open(_REPRICING_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_REPRICING_CACHE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[repricing] cache persist: {e}")


def _rp_price(cell):
    """Prix comparable d'une cellule : 0.0 si gratuit, FCFA si montant fixe plausible, sinon None."""
    if not cell or cell.get("suspect"):
        return None
    if cell.get("grat"):
        return 0.0
    if cell.get("tv") == "MONTANT_FCFA" and cell.get("montant") and float(cell["montant"]) > 0:
        return float(cell["montant"])
    return None


def _rp_facts(svc):
    """Faits déterministes d'un service : prix SGCI, prix concurrents comparables,
    médiane/min/max marché, nb concurrents au-dessus / en-dessous, position SGCI."""
    sgci_p = _rp_price(svc.get("sgci"))
    conc = {}
    for b, cell in (svc.get("concurrents") or {}).items():
        p = _rp_price(cell)
        if p is not None:
            conc[b] = p
    if sgci_p is None or len(conc) < 2:
        return {"comparable": False}
    conc_fcfa = sorted([p for p in conc.values() if p > 0])
    median = svc.get("mkt_median")
    if median is None and conc_fcfa:
        n = len(conc_fcfa)
        median = conc_fcfa[n // 2] if n % 2 else (conc_fcfa[n // 2 - 1] + conc_fcfa[n // 2]) / 2
    n_above = sum(1 for p in conc.values() if p > sgci_p)
    n_below = sum(1 for p in conc.values() if p < sgci_p)
    # FIABILITÉ : besoin d'≥2 prix FCFA concurrents dont la DISPERSION reste plausible (max ≤ 6× min).
    # Au-delà = appariement hétérogène / valeur aberrante (ex. « Port lettre » : SIB 1000 vs NSIA 20000)
    # → la médiane est trompeuse, on ne recommande RIEN dessus.
    unreliable = (len(conc_fcfa) < 2) or (conc_fcfa[-1] > conc_fcfa[0] * 6)
    return {
        "comparable": True,
        "sgci": sgci_p,
        "conc": conc,
        "median": float(median) if median else (sgci_p or 0),
        "mkt_min": min(conc.values()),
        "mkt_max": max(conc.values()),
        "n_above": n_above,
        "n_below": n_below,
        "grat": sgci_p == 0,
        "unreliable": unreliable,
    }


# ── INTELLIGENCE MÉTIER : comprendre l'INTENTION d'un prix avant d'agir ───────
# (règle-or DG : REFERENCE_OR_recommandations.md · réutilise la logique EXCLURE de _switching_costs)
_RP_BARRIERE = _re_rp.compile(
    r"(?i)(attestation|non[\s-]*redevance|mainlev|lev[ée]e\s+d.?\s*(opposi|hypoth|gage)|"
    r"opposi(?:tion)?|cl[ôo]ture\s+de\s+compte|transfert\s+de\s+compte|r[ée]sili|"
    r"certificat\s+de\s+non[\s-]*gage|solde\s+de\s+tout\s+compte|radiation|domiciliation)")
_RP_PUNITIF = _re_rp.compile(
    r"(?i)(impay|rejet|incident|saisie|\batd\b|tiers\s*d[ée]tenteur|injonction|contentieux|"
    r"recouvr|p[ée]nalit|for[çc]age|agios|d[ée]passement|d[ée]couvert\s+non\s+autoris)")
_RP_REGL = _re_rp.compile(
    r"(?i)(autorisation\s+de\s+change|\bchange\b|r[ée]glementation|conformit|\bswift\b|western\s+union|"
    r"transfert\s+d.?argent\s+internation)")
_RP_TYPE = _re_rp.compile(
    r"(?i)(tenue\s+de\s+compte|frais\s+de\s+tenue|frais\s+de\s+dossier|\bdossier\b|mise\s+en\s+place|"
    r"montage|\b[ée]tude\b|frais\s+d.?engagement|droit\s+de\s+garde|frais\s+de\s+garde)")
_RP_CREDIT = _re_rp.compile(
    r"(?i)(cr[ée]dit|pr[êe]t\b|\bescompte\b|d[ée]couvert|avance\b|affacturage|leasing|cr[ée]dit-?bail|"
    r"taux\s+d.?int[ée]r[êe]t|d[ée]caissement)")


def _rp_intent(libelle, categorie=""):
    """Intention métier d'un prix → protège des baisses naïves. Retourne None ou
    {kind, hard, verdict, explain}. `hard`=True → verdict imposé (on ne consulte pas le LLM)."""
    s = f"{categorie} {libelle}"
    if _RP_BARRIERE.search(s):
        return {"kind": "barriere_sortie", "hard": True, "verdict": "NE_PAS_TOUCHER",
                "explain": "Barrière de sortie : tarif élevé volontaire pour retenir le client / dissuader le départ — surtout pas baisser."}
    if _RP_PUNITIF.search(s):
        return {"kind": "punitif", "hard": True, "verdict": "NE_PAS_TOUCHER",
                "explain": "Frais de sanction (incident/impayé) : dissuasif par nature — le baisser encouragerait le comportement pénalisé."}
    if _RP_REGL.search(s):
        return {"kind": "reglementaire", "hard": False, "verdict": "MAINTENIR",
                "explain": "Encadré par la réglementation (change/international) — marge de manœuvre limitée."}
    if _RP_TYPE.search(s):
        return {"kind": "type_dependant", "hard": False, "verdict": "MAINTENIR",
                "explain": "Prix variable selon le type de compte/crédit — comparaison directe non fiable."}
    if _RP_CREDIT.search(s):
        return {"kind": "pnb_credit", "hard": False, "verdict": "MAINTENIR",
                "explain": "Cœur du PNB (marge d'intérêt) — repricing seulement progressif sur faible élasticité, jamais de baisse générale."}
    return None


# Règles-or du DG (condensé de REFERENCE_OR_recommandations.md) — orientation PNB.
_RP_DG_RULES = (
    "RÈGLES DG (initiative « Repricing & Valeur Digitale », objectif = protéger et augmenter le PNB) :\n"
    "1. Comprendre l'INTENTION d'un prix avant d'agir. Un prix BAS peut être une ARME D'ACQUISITION → NE PAS le monter à la médiane (ça tue le « pourquoi SGCI »).\n"
    "2. Hausses MODÉRÉES et différenciées, JAMAIS doubler un tarif. Idéal : « gratuit sur le digital / payant en agence ».\n"
    "3. Le PNB prime : NE JAMAIS baisser en masse. Une baisse ne se justifie QUE pour reconquérir des clients sensibles au prix sur un service d'acquisition concurrentiel, quand le volume regagné compense la marge perdue.\n"
    "4. Toute hausse est ACCOMPAGNÉE d'un gain de service/expérience (sinon attrition).\n"
    "5. Contexte marché (agent web) : la marge d'intérêt se comprime (taux BCEAO orienté à la baisse) → priorité à MONÉTISER les services à valeur, pas à casser les prix."
)

_RP_WEB_CTX = None


def _rp_web_context():
    """Contexte marché sourcé (agent web / web_facts.json) injecté dans le raisonnement."""
    global _RP_WEB_CTX
    if _RP_WEB_CTX is not None:
        return _RP_WEB_CTX
    txt = ""
    try:
        # Chemin corrigé le 2026-08-07 (cf. WEB_FACTS_FILE) : il visait encore dash_app/, laissé
        # derrière par le rangement du dépôt. Le fichier absent, le `except` plus bas renvoyait
        # une chaîne vide — le contexte de marché disparaissait du prompt sans le moindre signe.
        with open(WEB_FACTS_FILE, encoding="utf-8") as f:
            wf = json.load(f)
        keep = {"politique_monetaire", "mobile_money", "bancarisation", "npl_secteur"}
        lignes = []
        for item in wf.get("secteur", []):
            if item.get("cle") in keep:
                lignes.append(f"- {item.get('titre')}: {item.get('valeur')} ({item.get('source')})")
        if lignes:
            txt = "Faits marché sourcés (agent web) :\n" + "\n".join(lignes)
    except Exception:
        txt = ""
    _RP_WEB_CTX = txt
    return txt


def _rp_apply(verdict, cible, f, justif, src, intent=None):
    """Normalise un verdict LLM/estimation en action affichable (flèche, montant delta, cible).
    `intent` (soft) interdit les baisses sur services réglementaires / dépendants du type / crédit PNB."""
    verdict = (verdict or "MAINTENIR").upper().strip()
    if verdict not in ("AUGMENTER", "MAINTENIR", "BAISSER", "NE_PAS_TOUCHER"):
        verdict = "MAINTENIR"
    sgci = f["sgci"]
    montant = None
    # Intention métier (soft) : jamais de baisse sur réglementaire / dépendant du type / crédit PNB.
    if intent and not intent.get("hard") and verdict == "BAISSER":
        verdict = "MAINTENIR"
        justif = intent.get("explain", justif)
    try:
        cible = float(cible) if cible not in (None, "", "null") else None
    except Exception:
        cible = None
    # Garde-fou : jamais au-dessus du concurrent le plus cher.
    if cible is not None:
        cible = min(cible, f["mkt_max"])
    # DG règle 2 : hausse MODÉRÉE — ne jamais doubler un tarif existant.
    if cible is not None and verdict == "AUGMENTER" and sgci > 0:
        cible = min(cible, sgci * 1.8)
    incoherent = False
    if verdict == "AUGMENTER":
        # cohérence : la cible doit être > prix actuel
        if cible is None or cible <= sgci:
            incoherent = True
        else:
            montant = round((cible - sgci) / 50) * 50
            cible = round(cible / 50) * 50
            if montant < 50:
                incoherent = True
    elif verdict == "BAISSER":
        # cohérence : cible entre 0 (gratuit) et le prix actuel ; on ne baisse jamais de plus que le prix
        if cible is None or cible >= sgci or cible < 0:
            incoherent = True
        else:
            montant = min(round((sgci - cible) / 50) * 50, int(round(sgci)))
            cible = round(cible / 50) * 50
            if montant < 50:
                incoherent = True
    if incoherent:
        verdict = "MAINTENIR"; cible = None; montant = None
        justif = "Positionnement déjà cohérent — pas de mouvement pertinent."
    if verdict in ("MAINTENIR", "NE_PAS_TOUCHER"):
        cible = None; montant = None
    fleche = {"AUGMENTER": "up", "BAISSER": "down", "NE_PAS_TOUCHER": "lock", "MAINTENIR": "flat"}[verdict]
    return {
        "verdict": verdict,
        "fleche": fleche,
        "montant": int(montant) if montant else None,
        "cible": int(cible) if cible else None,
        "justif": (justif or "").strip()[:120],
        "src": src,
    }


def _rp_fallback(f, intent=None):
    """Estimation déterministe (secours quand le LLM est indisponible). Prudente + intention métier."""
    if intent and intent.get("hard"):
        return _rp_apply(intent["verdict"], None, f, intent["explain"], "regle_metier", intent)
    sgci, med, mx = f["sgci"], f["median"], f["mkt_max"]
    if f["grat"]:
        return _rp_apply("NE_PAS_TOUCHER", None, f,
                         "Gratuité — levier d'acquisition à préserver.", "estimation", intent)
    if f["n_above"] >= 1 and sgci < med:
        # marge vers la médiane, en restant sous le concurrent le moins cher parmi ceux au-dessus
        au_dessus = [p for p in f["conc"].values() if p > sgci]
        plafond = min(med, min(au_dessus) * 0.95) if au_dessus else med
        cible = max(sgci, plafond)
        if cible - sgci >= 50:
            return _rp_apply("AUGMENTER", cible, f,
                             f"Sous la médiane marché ({int(med)} F) — marge de hausse sans perte de rang.", "estimation", intent)
    if sgci > mx and mx > 0:
        return _rp_apply("BAISSER", mx, f,
                         "Nettement le plus cher du marché — risque de fuite.", "estimation", intent)
    return _rp_apply("MAINTENIR", None, f, "Prix déjà bien positionné.", "estimation", intent)


def _rp_key(roman, libelle):
    return f"{roman}||{(libelle or '').strip().lower()[:90]}"


def _rp_generate_chunk(roman, titre, chunk):
    """Génère les verdicts LLM d'un lot de services (une famille). Retourne {n: (verdict,cible,justif)}, engine."""
    lines = []
    for i, svc in enumerate(chunk):
        f = svc["_f"]
        conc = ", ".join(
            f"{b}={'gratuit' if p == 0 else str(int(p)) + 'F'}" for b, p in f["conc"].items()
        )
        sg = "gratuit" if f["sgci"] == 0 else f"{int(f['sgci'])}F"
        it = svc.get("_intent")
        hint = f"  [⚠ intention {it['kind']} — {it['explain']}]" if it else ""
        lines.append(f'{i + 1}. "{svc["libelle"][:70]}" | SGCI={sg} | concurrents: {conc} | médiane marché={int(f["median"])}F{hint}')

    prompt = f"""Tu es directeur de la tarification de SGCI (Société Générale Côte d'Ivoire), marché bancaire ivoirien (UEMOA).
{_RP_DG_RULES}

{_rp_web_context()}

Voici des services de la famille « {roman}. {titre} », avec le prix SGCI et ceux des concurrents ({_concurrents_txt()}).
Pour CHAQUE service, décide l'action tarifaire pour SGCI EN APPLIQUANT LES RÈGLES DG ci-dessus. RAISONNE PRODUIT PAR PRODUIT (jamais une règle uniforme), et EXPLIQUE l'intention :
- "NE_PAS_TOUCHER" : prix stratégique à préserver — soit une ARME D'ACQUISITION à bas prix (le monter tue le « pourquoi SGCI »), soit une BARRIÈRE DE SORTIE à prix élevé (retenir le client). Dis lequel.
- "AUGMENTER" : seulement si SGCI peut monter SANS perdre en compétitivité ET sans casser son avantage. Hausse MODÉRÉE (jamais doubler). Donne un prix cible réaliste.
- "BAISSER" : UNIQUEMENT si SGCI est nettement le plus cher sur un service d'ACQUISITION concurrentiel où un client sensible au prix partirait ET où le volume regagné compense la marge perdue (protéger le PNB). Sinon, ne propose PAS de baisse.
- "MAINTENIR" : prix déjà bien positionné.
Les services marqués [⚠ intention …] ont une intention métier particulière : respecte-la (ne baisse pas un frais réglementaire, un frais dépendant du type, ou du crédit — cœur du PNB).

SERVICES :
{chr(10).join(lines)}

Réponds UNIQUEMENT par un tableau JSON, un objet par service dans le même ordre :
[{{"n":1,"verdict":"AUGMENTER|MAINTENIR|BAISSER|NE_PAS_TOUCHER","cible":<prix cible en F entier, ou null>,"justif":"<=90 caractères, concret, EXPLIQUE le raisonnement (intention du prix / PNB), cite un concurrent si utile>"}}]
Aucun texte hors du JSON."""

    txt, engine = _rp_llm_json(prompt, max_tokens=3000, prefer_claude=True)
    parsed = _rp_parse_json(txt)
    out = {}
    if isinstance(parsed, list):
        for obj in parsed:
            try:
                n = int(obj.get("n"))
            except Exception:
                continue
            out[n] = (obj.get("verdict"), obj.get("cible"), obj.get("justif"))
    return out, (engine if out else None)


def _claude_call(prompt, max_tokens, temperature):
    """Appel Claude via OpenRouter, avec RETRY sur erreur réseau transitoire.

    Cause réelle trouvée le 2026-07-16 (diagnostic avec logs non bufferisés) : sur des rafales
    d'appels séquentiels (ex. repricing par lots), une partie des requêtes échoue avec
    `ConnectionResetError(10054)` — un reset réseau TRANSITOIRE côté connexion (pas une panne
    Claude, pas un problème de prompt/JSON). Sans retry, ces lots basculaient sur Groq alors que
    Claude aurait répondu correctement à la tentative suivante. 1 retry après une courte pause
    suffit dans la quasi-totalité des cas observés.

    IMPORTANT — clé OpenRouter (2026-07-15), PAS la clé Anthropic native (ANTHROPIC_API_KEY,
    restée à 0 crédit) : OpenRouter expose Claude via une API compatible OpenAI, à une adresse
    et avec un format différents de l'API Anthropic directe. `reasoning:{enabled:False}` est
    OBLIGATOIRE — sans lui, Claude Sonnet 5 consomme tout `max_tokens` en « raisonnement »
    interne invisible et ne produit AUCUN texte final (bug réel trouvé en testant : content=None,
    finish_reason="length" avant même le début de la vraie réponse).

    Retourne le texte brut, ou "" si Claude est indisponible après retry (l'appelant bascule Groq).

    COUPE-CIRCUIT (2026-07-21, demande explicite du directeur — le warmup automatique du serveur
    (_warm(), déclenché à CHAQUE redémarrage, sans aucun prompt humain) consommait le budget
    OpenRouter en arrière-plan, malgré l'instruction « ne touche pas à mon quota Claude sous aucun
    prétexte »). Si CLAUDE_DISABLED=1 dans .env, retourne "" IMMÉDIATEMENT, avant tout appel réseau
    — bloque TOUS les chemins (warmup inclus), quel que soit qui/quoi déclenche l'appel. Mettre 0
    ou retirer la ligne pour réactiver, une fois le plafond de la clé relevé sur OpenRouter."""
    if os.getenv("CLAUDE_DISABLED") == "1":
        return ""
    import requests as _rq
    import time as _t
    or_key = os.getenv("OPENROUTER_API_KEY", "")
    last_err = None
    for attempt in range(2):
        try:
            resp = _rq.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json"},
                json={
                    "model": os.getenv("EF_CLAUDE_MODEL", "anthropic/claude-sonnet-5"),
                    "max_tokens": max_tokens, "temperature": temperature,
                    "reasoning": {"enabled": False},
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=90,
            )
            d = resp.json()
            txt = (d.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            if txt:
                return txt
            print(f"[claude] réponse vide ({resp.status_code}) : {str(d)[:200].encode('ascii','backslashreplace').decode()}")
            return ""
        except Exception as e:
            last_err = e
            if attempt == 0:
                print(f"[claude] erreur réseau ({str(e).encode('ascii','backslashreplace').decode()}) → retry")
                _t.sleep(1.5)
                continue
    print(f"[claude] indispo après retry ({str(last_err).encode('ascii','backslashreplace').decode()}) → Groq")
    return ""


def _rp_llm_json(prompt, max_tokens=1500, temperature=0.4, prefer_claude=False):
    """Texte brut du LLM pour parsing JSON. Claude (via OpenRouter, avec retry — cf. `_claude_call`)
    si prefer_claude=True (appel explicite par le site d'appel) OU CB_USE_CLAUDE=1 (bascule globale
    historique), sinon Groq (rotation). temperature basse (~0.15) recommandée pour les tâches
    factuelles."""
    # NOTE (2026-07-22) : pas de garde-fou _chiffres_inventes générique ICI — testé, et trop
    # strict pour des prompts longs/complexes à chiffres dérivés (ex. EF, 15 blocs) : rejette la
    # réponse ENTIÈRE pour un seul chiffre calculé légitimement absent du prompt (pire que le
    # risque qu'il corrige). Le garde-fou reste appliqué explicitement au cas par cas côté
    # appelant (Stratégie switch/projection/roadmap) où il a été validé sans faux positifs.
    if prefer_claude or os.getenv("CB_USE_CLAUDE") == "1":
        _txt = _claude_call(prompt, max_tokens, temperature)
        if _txt:
            return _txt, "claude"
    try:
        from groq import Groq as _Groq
        import time as _t
        keys = [k for k in (
            [os.getenv("GROQ_API_KEY_11", ""), os.getenv("GROQ_API_KEY_12", "")]
            + [os.getenv(f"GROQ_API_KEY_{i}", "") for i in range(5, 11)]
            + [os.getenv("GROQ_API_KEY", "")]
            + [os.getenv(f"GROQ_API_KEY_{i}", "") for i in range(2, 5)]
        ) if k]
        last_err = None
        for key in keys:
            try:
                c = _Groq(api_key=key, timeout=60.0, max_retries=0)
                resp = c.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens, temperature=temperature,
                )
                _llm_mark_up()
                return resp.choices[0].message.content, "groq"
            except Exception as e:
                last_err = str(e)
                _t.sleep(0.2); continue
        _llm_mark_down(last_err)
    except Exception as e:
        print(f"[repricing] Groq indispo : {e}")
        _llm_mark_down(str(e))
    return None, None


def _rp_parse_json(txt):
    if not txt:
        return None
    m = _re_rp.search(r"\[.*\]", txt, _re_rp.S)
    if not m:
        return None
    frag = m.group(0)
    for candidate in (frag, _re_rp.sub(r",\s*([\]}])", r"\1", frag)):
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def _rp_web_canon(s):
    return _re_rp.sub(r"\s+", " ", (s or "").strip().lower())[:90]


def _rp_web_validation():
    """Validation web sourcée par service (agent Tavily+Groq, run_veille_repricing.py).
    Lu à chaque build (fichier léger) → une régénération de l'agent est visible sans redémarrage."""
    try:
        # Chemin corrigé le 2026-08-07 : visait dash_app/, le fichier est dans data/.
        p = os.path.join(DOSSIER_DATA, "cb_repricing_web.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return (json.load(f) or {}).get("services", {}) or {}
    except Exception:
        pass
    return {}


def _repricing_build(annee, semestre, segment):
    """Retourne (sections+action, recap, engine). Génère les verdicts manquants (LLM) puis cache.
    Fusionne la validation web sourcée (agent Tavily) sur les actions de hausse/baisse."""
    _rp_load()
    webval = _rp_web_validation()
    sections = AGENTS["CB"].structured.cb_prix_par_libelle(annee, semestre, segment)
    ckey = f"{annee}_{semestre}_{segment}"
    cache = _REPRICING_CACHE.setdefault(ckey, {})
    engine = "estimation"
    dirty = False
    recap = []

    for sec in sections:
        comp = []
        for ss in sec["sous_sections"]:
            for svc in ss["services"]:
                f = _rp_facts(svc)
                if not f.get("comparable"):
                    svc["action"] = None
                    continue
                svc["_f"] = f
                svc["_ss"] = ss["libelle"]
                svc["_key"] = _rp_key(sec["roman"], svc["libelle"])
                svc["_intent"] = _rp_intent(svc["libelle"], sec["titre"])
                comp.append(svc)

        missing = [s for s in comp if s["_key"] not in cache]
        # 1) Intentions FORTES (barrière de sortie / frais punitif) → verdict métier imposé, sans LLM.
        llm_todo = []
        for svc in missing:
            it = svc["_intent"]
            if it and it.get("hard"):
                cache[svc["_key"]] = _rp_apply(it["verdict"], None, svc["_f"], it["explain"], "regle_metier", it)
                dirty = True
            else:
                llm_todo.append(svc)
        # 2) Le reste → génération LLM par lots de 18 services (une famille)
        for i in range(0, len(llm_todo), 18):
            chunk = llm_todo[i:i + 18]
            verdicts, eng = _rp_generate_chunk(sec["roman"], sec["titre"], chunk)
            if eng:
                engine = eng
            for j, svc in enumerate(chunk):
                v = verdicts.get(j + 1)
                if v:
                    cache[svc["_key"]] = _rp_apply(v[0], v[1], svc["_f"], v[2], eng, svc["_intent"])
                else:
                    cache[svc["_key"]] = _rp_fallback(svc["_f"], svc["_intent"])
                dirty = True

        # Attacher l'action (+ validation web sourcée sur les hausses/baisses) + construire le récap
        items = []
        for svc in comp:
            action = cache.get(svc["_key"]) or _rp_fallback(svc["_f"], svc.get("_intent"))
            sgci_v = svc["_f"]["sgci"]
            # INTELLIGENCE anti-mouvement brutal (vaut pour TOUS les filtres, Particuliers ET Entreprises) :
            if action.get("verdict") == "AUGMENTER" and sgci_v == 0:
                # Gratuité = arme d'acquisition → coller un tarif d'un coup fait fuir les clients.
                # (Priorité sur « non fiable » : pour un service gratuit, la dispersion concurrente est sans objet.)
                action = {**action, "verdict": "NE_PAS_TOUCHER", "fleche": "lock", "montant": None, "cible": None,
                          "justif": "Gratuité = arme d'acquisition — la facturer brutalement génère de l'attrition ; à préserver (monétisation seulement via une offre différenciée digital/agence)."}
            elif svc["_f"].get("unreliable") and action.get("verdict") in ("AUGMENTER", "BAISSER"):
                # Reco de hausse/baisse sur une comparaison NON FIABLE (prix concurrents trop dispersés /
                # valeur aberrante, ex. « Port lettre » NSIA 20000 vs SIB 1000) → on la SUPPRIME.
                action = {**action, "verdict": "NE_PAS_TOUCHER", "fleche": "lock", "montant": None, "cible": None,
                          "justif": "Comparaison marché non fiable — prix concurrents trop dispersés (valeur aberrante probable). À ne pas exploiter tel quel."}
            elif action.get("verdict") == "BAISSER" and not action.get("cible") and 0 < sgci_v < 2000:
                # Frais déjà bas (ex. Compte ECO 990 F) → le rendre gratuit sacrifie le PNB pour un gain marginal.
                action = {**action, "verdict": "MAINTENIR", "fleche": "flat", "montant": None, "cible": None,
                          "justif": "Frais déjà bas — la gratuité totale sacrifierait le revenu (PNB) pour un gain marginal."}
            elif action.get("verdict") in ("NE_PAS_TOUCHER", "MAINTENIR") and sgci_v > 0 \
                    and not _rp_intent(svc["libelle"]):
                # MARGE SUR LA TABLE (diagnostic DG) : SGCI TRÈS en-dessous du marché (≤ 40% de la médiane)
                # sur un service dont le LIBELLE n'a aucune intention métier (on juge le libellé seul, PAS la
                # section : « Port lettre » listé sous « crédit » n'est pas du crédit). Exclut barrière/punitif,
                # réglementaire, dépendant du type (« frais de dossier »), crédit. Hausse MODÉRÉE, cible ≤ 50%
                # de la médiane (jamais doubler), en restant de loin le moins cher. Ex. Port lettre 1100 → 2000.
                _med = svc["_f"]["median"] or 0
                # Corroboration : au moins 2 concurrents RÉELLEMENT plus chers (pas un seul outlier),
                # et SGCI moins cher que la majorité — sinon ce n'est pas une vraie sous-tarification.
                if _med and sgci_v <= _med * 0.4 and svc["_f"]["n_above"] >= 2 \
                        and svc["_f"]["n_above"] > svc["_f"]["n_below"]:
                    _cible = round(min(sgci_v * 1.8, _med * 0.5) / 50) * 50
                    _mt = round((_cible - sgci_v) / 50) * 50
                    if _mt >= 50:
                        action = {**action, "verdict": "AUGMENTER", "fleche": "up",
                                  "montant": int(_mt), "cible": int(_cible),
                                  "justif": f"Très en-dessous du marché (médiane {int(_med)} F) — marge à capturer par une hausse modérée, en restant de loin le moins cher."}
            # COHÉRENCE DE DIRECTION vs marché : on n'augmente que si SGCI < médiane, on ne baisse que
            # si SGCI > médiane (sinon le verdict LLM contredit les chiffres, ex. « augmenter » à 17500
            # alors que SGCI 16500 est déjà au-dessus de la médiane 13500).
            _medd = svc["_f"]["median"] or 0
            if action.get("verdict") == "AUGMENTER" and _medd and sgci_v >= _medd:
                action = {**action, "verdict": "MAINTENIR", "fleche": "flat", "montant": None, "cible": None,
                          "justif": "Déjà au niveau / au-dessus de la médiane marché — pas de marge de hausse pertinente."}
            elif action.get("verdict") == "BAISSER" and _medd and 0 < sgci_v <= _medd:
                action = {**action, "verdict": "MAINTENIR", "fleche": "flat", "montant": None, "cible": None,
                          "justif": "Déjà au niveau / en-dessous de la médiane marché — pas de baisse justifiée."}
            if action.get("verdict") in ("AUGMENTER", "BAISSER"):
                w = webval.get(_rp_web_canon(svc["libelle"]))
                if w:
                    action = {**action, "web": {
                        "contexte": w.get("contexte", ""), "ok": bool(w.get("ok")),
                        "nuance": w.get("nuance", ""), "sources": w.get("sources", []),
                    }}
                items.append({
                    "libelle": svc["libelle"],
                    "sous_section": svc["_ss"],
                    "verdict": action["verdict"],
                    "montant": action.get("montant"),
                    "cible": action.get("cible"),
                    "justif": action.get("justif"),
                    "sgci_prix": int(svc["_f"]["sgci"]),
                    "mkt_median": int(svc["_f"]["median"]),
                    "web": action.get("web"),
                })
            svc["action"] = action
            svc["unreliable"] = bool(svc["_f"].get("unreliable"))
            svc.pop("_f", None); svc.pop("_ss", None); svc.pop("_key", None); svc.pop("_intent", None)
        if items:
            items.sort(key=lambda x: -(x.get("montant") or 0))
            recap.append({"roman": sec["roman"], "titre": sec["titre"], "items": items})

    if dirty:
        _rp_persist()
    n_actions = sum(len(r["items"]) for r in recap)
    # Corrige le faux-positif « IA indisponible » : `engine` ne reflétait que le TRAVAIL FAIT
    # PENDANT CET APPEL (restait à "estimation" par défaut dès que tout était déjà en cache,
    # même si le cache avait été rempli par une vraie IA plus tôt) — trouvé le 2026-07-16 après
    # une question du directeur sur ce bandeau affiché à tort. On recalcule depuis la VRAIE
    # provenance de chaque verdict caché (`src`, posé par _rp_apply) : le bandeau ne doit
    # s'afficher que si AUCUN verdict affiché ne vient réellement d'une IA.
    if any((v or {}).get("src") in ("claude", "groq") for v in cache.values()):
        engine = "claude" if any((v or {}).get("src") == "claude" for v in cache.values()) else "groq"
    return sections, recap, engine, n_actions


@app.route("/api/cb_repricing")
def api_cb_repricing():
    """Actions tarifaires stratégiques service par service (faits déterministes + verdict IA).
    Généré (Groq/Claude) puis stocké dans cb_repricing_cache.json — servi instantanément ensuite."""
    annee    = int(request.args.get("annee",    2026))
    semestre = request.args.get("semestre", "S1")
    segment  = request.args.get("segment",  "Particuliers")

    # MIS EN CACHE EN BASE LE 2026-08-10. La docstring ci-dessus dit « servi instantanément
    # ensuite » : c'était vrai des seuls VERDICTS rédigés, stockés dans un fichier. Les faits
    # déterministes, eux, étaient recalculés à chaque appel — mesuré à 48,7 s puis 47,2 s sur
    # le service en ligne, deux appels de suite. C'est le plus long appel restant de
    # l'application, et il bloquait l'écran « Conditions bancaires » jusqu'au filet de 25 s.
    cle = f"cb_repricing:{annee}:{semestre}:{segment}"
    garde = _cache_lire(cle)
    if garde is not None:
        return jsonify(garde)
    try:
        sections, recap, engine, n_actions = _repricing_build(annee, semestre, segment)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    charge = {"sections": sections, "recap": recap, "engine": engine, "n_actions": n_actions}
    # On n'enregistre pas une réponse vide : la resservir indéfiniment masquerait une panne.
    if sections:
        _cache_ecrire(cle, charge)
    return jsonify(charge)


# ══════════════════════════════════════════════════════════════════════════════
# EF — HABILLAGE LLM des analyses Santé Financière.
# Le template reste la BASE FACTUELLE (chiffres garantis) ; le LLM voit TOUS les
# indicateurs d'un coup et rédige une analyse COMPLÉMENTAIRE par bloc (jamais répéter,
# histoire cohérente, cohérence temporelle). Généré puis STOCKÉ (ef_analyses_cache.json).
# ══════════════════════════════════════════════════════════════════════════════
_EF_LLM_CACHE_FILE = os.path.join(DOSSIER_CACHE, "ef_analyses_cache.json")
_EF_LLM_CACHE = None

# Chaque bloc = un graphique. On dit au LLM l'ANGLE UNIQUE de chacun → pas de répétition.
_EF_BLOCKS = {
    "signal":      "POSITION globale de SGCI (rang par résultat net, part des bénéfices). Vue d'ensemble.",
    "podium":      "LE PODIUM : NOMME les 3 premières banques AVEC leurs montants exacts (ex. « SGCI 101,4 Mds, ECOBANK 63,5 Mds, SIB 55,6 Mds ») puis la part des bénéfices qu'elles réunissent à elles trois. Concret et chiffré, PAS de mot savant.",
    "growth":      "DYNAMIQUE de croissance. RAISONNEMENT ATTENDU (pas une simple liste) : la croissance lente de SGCI n'est PAS une faiblesse, c'est l'EFFET DE BASE — progresser sur un énorme socle exige un effort absolu que les petits n'ont pas à fournir. Le vrai signal = le concurrent qui ACCÉLÈRE le plus vite (multiple ×) en partant de petit : c'est sa VÉLOCITÉ qu'il faut surveiller sur 2-3 ans, pas son niveau absolu.",
    "bump":        "TRAJECTOIRE DE CLASSEMENT (RANGS, pas montants) : qui grimpe, qui recule sur la période. Un concurrent qui gagne des places est un signal précoce (il transforme mieux son risque/ses charges). Nomme celui qui bouge le plus. N'UTILISE QUE les rangs du bloc de facts « TRAJECTOIRE DE CLASSEMENT » ci-dessous — JAMAIS un chiffre d'un autre bloc (montant, %, points de base) pour compenser si ce bloc est incomplet. Si une banque est notée [hors comparaison], ne l'inclus PAS dans ton analyse.",
    "line":        "TRAJECTOIRE pluriannuelle du résultat net : régularité de SGCI, et surtout comment l'ÉCART au n°2 évolue (se creuse ou se réduit) — c'est ça qui dit si l'avance est solide ou grignotée.",
    "tree":        "AMPLEUR de la domination en volume — le MULTIPLE : SGCI pèse combien de fois le n°2, combien de fois le dernier. Angle 'écart absolu', PAS le pourcentage donné ailleurs.",
    "share":       "LEVIER DE MARGE inexploité : à part de marché égale, ce que SGCI gagnerait (en Mds) en alignant sa marge nette sur la meilleure banque. Angle 'potentiel dormant', PAS la part actuelle.",
    "pnb":         "REVENUS (PNB) : la taille du moteur commercial. RAISONNEMENT : avoir le plus gros PNB est un atout, mais le PNB n'est que la matière première — TOUT l'enjeu est de le convertir en profit (renvoie vers l'efficacité). Dis les revenus, pas le profit.",
    "cd":          "TRANSFORMATION dépôts→crédits (ratio crédits/dépôts). RAISONNEMENT : la zone idéale BCEAO est ~80-100% (ni trop prudent = dépôts qui dorment, ni >100% = risque de liquidité). Situe SGCI dans/hors de cette zone et dis qui mobilise le mieux ses dépôts.",
    "mix":         "MIX commercial (intérêts vs commissions). RAISONNEMENT : une part d'intérêts très élevée = dépendance au crédit et VULNÉRABILITÉ à une baisse des taux ; les commissions sont un revenu plus stable. Dis si SGCI est diversifiée ou dépendante, et le risque que ça implique.",
    "cascade":     "CASCADE PNB→RBE→RE→RN : à chaque étage, combien du PNB est CONSERVÉ. RAISONNEMENT : montre OÙ fuit le profit — d'abord les charges d'exploitation (→RBE), PUIS le coût du risque (→RE). Pointe l'étage qui fait le plus mal.",
    "marge":       "MARGE nette. RAISONNEMENT (le PARADOXE) : SGCI a le plus gros PNB mais une marge parmi les plus FAIBLES — donc son problème n'est PAS de générer du revenu, mais d'en garder le profit. Chiffre l'écart au meilleur.",
    "coeff":       "COEFFICIENT d'exploitation (charges/PNB, BAS=mieux). RAISONNEMENT-CLÉ : si SGCI a un TRÈS BON coefficient (charges bien maîtrisées) MAIS une marge faible, alors le frein n'est PAS les charges — il est ailleurs (le coût du risque). Dis-le explicitement.",
    "roe":         "ROE (rendement pour l'actionnaire). RAISONNEMENT (le PARADOXE, à expliquer) : SGCI peut être n°1 en résultat net ABSOLU tout en ayant un ROE plus faible — non par sous-performance, mais parce que sa base de CAPITAUX PROPRES est bien plus lourde (capital accumulé). C'est un coût d'opportunité pour l'actionnaire, pas une faiblesse d'exploitation.",
    "cnr":         "COÛT DU RISQUE en % du PNB (le % affiché) : combien de Mds partent en provisions, l'écart au meilleur, et le GAIN de résultat net si SGCI s'alignait. C'est LE levier principal du bilan.",
    "coeff_line":  "ÉVOLUTION du COEFFICIENT D'EXPLOITATION dans le temps (plus BAS = mieux) — utilise les chiffres du bloc de facts « COEFFICIENT … ÉVOLUTION ». Phrase 1 : la trajectoire de SGCI « de X% à Y% » et l'écart en points (baisse = progrès), + rang + zone BCEAO. Phrase 2 : la banque qui s'AMÉLIORE le plus (forte baisse), dont l'écart avec SGCI se resserre — angle « avantage d'efficacité de SGCI grignoté ». Phrase 3 : ce que cela implique (l'avance opérationnelle n'est pas acquise). 3 phrases, en %.",
    "cnr_line":    "ÉVOLUTION du coût du risque en POINTS DE BASE (pb) — utilise UNIQUEMENT les chiffres en pb du bloc de facts « ÉVOLUTION » (JAMAIS les % de l'autre bloc risque). Phrase 1 : la trajectoire de SGCI « de X pb (année0) à Y pb (année1) » et surtout l'AUGMENTATION = Y − X (ex. +68pb) — ne confonds JAMAIS l'augmentation avec le niveau Y ; ajoute le rang et la médiane. Phrase 2 : le CONTRE-EXEMPLE fourni (banque passée de A pb à B pb, ÷ combien) qui prouve que l'amélioration est atteignable. Phrase 3 : l'alerte zone de surveillance BCEAO (>200pb) si SGCI s'en approche. 3 phrases, tout en pb.",
    # ── SIGNAUX ANALYTIQUES de section : constat-clé de LA section + QUESTION de transition qui introduit la SUIVANTE (le fil narratif). ──
    "s1":          "SIGNAL de « Résultat net & position ». STRUCTURE OBLIGATOIRE : (1) le constat-clé de cette section — SGCI est n°X en résultat net (montant, part du secteur) + 1 nuance ; (2) puis UNE question de transition qui introduit la section suivante « Puissance commerciale », du type « Mais générer le plus de bénéfices, est-ce générer le plus de REVENUS ? ». 2 phrases : constat, puis question.",
    "s2":          "SIGNAL de « Puissance commerciale ». STRUCTURE : (1) constat — SGCI génère le plus gros PNB (montant) + 1 nuance sur son mix ; (2) UNE question de transition vers « Efficacité opérationnelle », du type « Mais le plus gros revenu devient-il le plus gros PROFIT ? ». 2 phrases : constat, puis question.",
    "s3":          "SIGNAL d'« Efficacité opérationnelle ». STRUCTURE : (1) constat — SGCI a de bons coûts (coefficient) MAIS une marge nette faible, donc le frein n'est pas les charges ; (2) UNE question de transition vers « Qualité du risque », du type « Alors où fuit le profit ? ». 2 phrases : constat, puis question.",
    "s4":          "SIGNAL de « Qualité du risque & création de valeur » (DERNIÈRE section, pas de question). STRUCTURE : (1) constat — le coût du risque est LE frein (chiffre le Mds en jeu) ; (2) la conclusion actionnable (ce que débloquerait sa réduction). 2 phrases : constat, puis conclusion.",
    # ── Analyses TEMPORELLES du graphe en ligne quand on bascule sur ROE / PNB ──
    "line_roe":    "ÉVOLUTION du ROE dans le temps (de X% à Y%, tendance) + sa place vs le meilleur ; le PARADOXE actionnaire (voir bloc roe) en une touche. 2 phrases chiffrées.",
    "line_pnb":    "ÉVOLUTION du PNB dans le temps (de X à Y Mds, croissance %) + sa place ; le concurrent qui accélère le plus vite en revenus. 2 phrases chiffrées.",
}


def _ef_cache():
    global _EF_LLM_CACHE
    if _EF_LLM_CACHE is None:
        try:
            with open(_EF_LLM_CACHE_FILE, encoding="utf-8") as f:
                _EF_LLM_CACHE = json.load(f)
        except Exception:
            _EF_LLM_CACHE = {}
    return _EF_LLM_CACHE


def _grands_nombres(text):
    """Extrait les nombres >= 1000 d'un texte (montants FCFA, agregats) - insensible aux
    espaces de separation des milliers (normaux ou insecables). Ignore les petits nombres
    (numerotation, comptes de services)."""
    out = set()
    for m in _re_rp.finditer(r"[\d\s]*\d", text or ""):
        raw = _re_rp.sub(r"\s", "", m.group(0))
        if raw.isdigit() and int(raw) >= 1000:
            out.add(int(raw))
    return out


def _chiffres_inventes(analyse, facts):
    """GARDE-FOU STRUCTUREL (2026-07-21, demande explicite « 0 HALLUCINATION » après plusieurs
    inventions malgré des instructions de prompt ignorées par le LLM — Groq notamment) : compare
    les grands nombres (≥1000, montants FCFA/agrégats) du texte généré à ceux RÉELLEMENT fournis
    dans `facts`. Si le LLM a inventé un montant/nombre de clients absent des données, on le détecte
    ICI, au niveau du code — pas seulement via une consigne de prompt qui peut être ignorée.
    Retourne l'ensemble des nombres inventés (vide = rien à signaler)."""
    return _grands_nombres(analyse) - _grands_nombres(facts)


def _llm_br(text):
    """Met UNE phrase par ligne : ajoute un <br> après chaque fin de phrase (. ! ?).
    NON DESTRUCTIF : préserve la structure existante (retours-ligne, <br>, listes) et
    n'ajoute un saut QUE là où deux phrases se suivent sans séparation. Réutilisable pour
    TOUTES les analyses LLM (CB, Santé Financière, Stratégie). Protège les décimales (1,84)."""
    if not text or not isinstance(text, str):
        return text
    t = _re_rp.sub(r"\r?\n+", "<br>", text.strip())                       # vrais retours-ligne → <br>
    t = _re_rp.sub(r"([.!?])[ \t]+(?!<br)(?=[«\"'A-ZÀ-ÖØ-Þ0-9])", r"\1<br>", t)  # phrase non déjà séparée
    t = _re_rp.sub(r"(?:<br>\s*){2,}", "<br>", t)                         # dédoublonne les <br>
    t = _re_rp.sub(r"(?:\s*<br>\s*)+$", "", t)                            # pas de <br> final (ligne vide)
    return t


# Queues de remplissage récurrentes du modèle (instructions négatives mal suivies → on nettoie).
_LLM_FILLER_TAILS = (
    ", notamment en comparaison avec les autres banques",
    " notamment en comparaison avec les autres banques",
    ", notamment par rapport aux autres banques",
    " notamment par rapport aux autres banques",
    ", notamment par rapport à ses concurrents",
    " pour maintenir sa position sur le marché et faire face à la concurrence",
    " et faire face à la concurrence",
    " pour maintenir sa position sur le marché",
    ", mais il est important de regarder les autres indicateurs pour comprendre la performance de l'entreprise",
    " mais il est important de regarder les autres indicateurs pour comprendre la performance de l'entreprise",
    " pour maximiser son résultat net",
    " pour maximiser le rendement de ses actionnaires",
    ", mais doit continuer à innover pour maintenir son avance",
    " mais doit continuer à innover pour maintenir son avance",
    " pour maintenir son avance sur ses concurrents et atteindre son plein potentiel",
    " et atteindre son plein potentiel",
    " pour maintenir son avance sur ses concurrents",
    " et maintenir son avance sur ses concurrents",
    " pour atteindre son plein potentiel",
    " pour maintenir sa position de leader sur le marché",
    " afin de maintenir sa position de leader sur le marché",
    " pour maintenir sa position de leader",
    " pour maintenir sa part de marché et son leadership",
    " pour rester compétitive",
    " et proactive pour maintenir sa part de marché",
)


def _llm_polish(text):
    """Retire les tics de remplissage du LLM en gardant le CONTENU chiffré utile :
    l'amorce vide « Cela signifie/implique/… que … » et les queues génériques répétées."""
    if not text or not isinstance(text, str):
        return text
    t = text
    # Gras markdown → HTML (le modèle mélange parfois **X** et <b>X</b>) : on normalise en <b>.
    t = _re_rp.sub(r"\*\*\s*(<b>.*?</b>)\s*\*\*", r"\1", t)   # **<b>X</b>** → <b>X</b>
    t = _re_rp.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)          # **X** → <b>X</b>
    # On ne retire ces queues QUE si elles TERMINENT la phrase (devant . ! ? <br> ou fin) — sinon on
    # casse la grammaire (ex. « …ses concurrents, qui affichent… » où le mot est l'antécédent d'une relative).
    for tail in _LLM_FILLER_TAILS:
        t = _re_rp.sub(_re_rp.escape(tail) + r"(?=\s*(?:<br>|[.!?]|$))", "", t)
    # « … ; cela/ce qui signifie/implique que X » (MI-phrase, connecteur creux) → coupe en nouvelle phrase.
    t = _re_rp.sub(
        r"\s*[;,]?\s*(?:cela|ce qui|ceci) (?:signifie|implique|montre|indique|veut dire) que\s+([a-zàâçéèêëîïôûù])",
        lambda m: ".<br>" + m.group(1).upper(), t, flags=_re_rp.I)
    # Méta-références internes (« Le fait marquant de la révélation rev_3 est que X… » → « X… »).
    t = _re_rp.sub(r"(^|<br>)\s*Le fait marquant (?:de la révélation rev_\d+\s*)?est que\s+([a-zàâçéèêëîïôûùA-ZÀ-Þ])",
                   lambda m: m.group(1) + m.group(2).upper(), t)
    t = _re_rp.sub(r"\s*de la révélation rev_\d+", "", t)
    # Phrases entières d'exhortation creuse (« Ceci implique que… », « SGCI doit prendre des mesures/être vigilante… »).
    t = _re_rp.sub(r"(?:<br>)?\s*Ceci implique que[^<]*", "", t)
    t = _re_rp.sub(r"(?:<br>)?\s*SGCI doit (?:prendre des mesures|être vigilante|constamment innover|réévaluer sa stratégie)[^<]*", "", t)
    # « Cela signifie que X… » → « X… » (début de phrase / après un <br>), on remonte la majuscule.
    t = _re_rp.sub(
        r"(^|<br>)\s*Cela (?:signifie|implique|signale|montre|indique|veut dire) que\s+([a-zàâçéèêëîïôûùA-ZÀ-Þ])",
        lambda m: m.group(1) + m.group(2).upper(), t)
    # « (mais) il est important de noter que X » → « (mais) X » (tic récurrent, mi-phrase).
    t = _re_rp.sub(r"\s*,?\s*il est important de noter que\s+", " ", t, flags=_re_rp.I)
    # Coupe les clauses de remplissage récurrentes des synthèses (le modèle les invente sans cesse) :
    t = _re_rp.sub(r",?\s*ce qui signifie qu'il y a un potentiel[^.<!?]*", "", t)
    t = _re_rp.sub(r",?\s*en regardant les (?:meilleures pratiques|tendances)[^.<!?]*", "", t)
    t = _re_rp.sub(r",?\s*en ajustant sa stratégie en conséquence", "", t)
    t = _re_rp.sub(r",?\s*(?:et\s+)?il est important de suivre[^.<!?]*", "", t)
    # Supprime les phrases entières de conclusion vide (jusqu'au <br> ou fin) :
    t = _re_rp.sub(r"(?:<br>)?\s*SGCI doit (?:donc )?(?:se concentrer|continuer)[^<]*", "", t)
    t = _re_rp.sub(r"(?:<br>)?\s*Cela repr[ée]sente (?:un|une)\s+(?:défi|enjeu|opportunité|signal|challenge)[^<]*", "", t)
    t = _re_rp.sub(r"(?:<br>)?\s*SGCI a un potentiel (?:de gain )?important[^<]*", "", t)
    # Clause de BUT creuse en fin de phrase (« …pour améliorer sa rentabilité et sa compétitivité sur le marché »)
    # → on garde la directive actionnable, on coupe la finalité vide.
    t = _re_rp.sub(
        r"\s+(?:afin de|pour)\s+(?:améliorer|renforcer|maintenir|assurer|garantir|préserver|consolider|accroître|"
        r"optimiser|rester|demeurer|conserver|soutenir)\b[^.<!?]*?"
        r"(?:compétiti\w+|rentabilit\w+|position\w*|croissance|part\w* de march\w+|sur le march\w+|leader)[^.<!?]*",
        "", t, flags=_re_rp.I)
    # Décimales à la française : 27.3% → 27,3% (point entre deux chiffres = séparateur décimal).
    t = _re_rp.sub(r"(?<=\d)\.(?=\d)", ",", t)
    # Nettoie une éventuelle ponctuation résiduelle en fin de phrase après suppression d'une queue.
    t = _re_rp.sub(r"\s+([.!?])", r"\1", t)
    t = _re_rp.sub(r"(<br>|^)([a-zàâçéèêëîïôûù])", lambda m: m.group(1) + m.group(2).upper(), t)
    t = _re_rp.sub(r"<br>\s*[.…;,]+\s*(?=<br>|$)", "", t)  # fragments orphelins (« <br>. ») après un strip
    t = _re_rp.sub(r"(?:<br>\s*){2,}", "<br>", t)          # dédoublonne les <br>
    t = _re_rp.sub(r"(?:\s*<br>\s*)+$", "", t.strip())     # pas de <br> final
    return t


def _ef_fmt(series, scale=1.0, unit="", dec=0):
    """Formate {banque:{annee:val}} en lignes compactes, triées par dernière valeur décroissante."""
    def _last(d):
        return d[max(d)] if d else 0
    out = []
    for b in sorted(series or {}, key=lambda x: -_last(series[x])):
        yrs = series.get(b) or {}
        if not yrs:
            continue
        cells = " ".join(
            f"{y}:{round(yrs[y] * scale, dec) if dec else int(round(yrs[y] * scale))}{unit}"
            for y in sorted(yrs)
        )
        out.append(f"  {b}: {cells}")
    return "\n".join(out) or "  (indisponible)"


@app.route("/api/ef_analyses_llm")
def api_ef_analyses_llm():
    """Analyses Santé Financière rédigées par le LLM (habillage), complémentaires & non répétitives,
    fondées sur les chiffres réels EF. Cache reproductible."""
    segment = request.args.get("segment", "Particuliers")
    anx     = int(request.args.get("anx", 3))
    S = AGENTS["EF"].structured
    try:
        rn     = S.resultat_net_series()
        pnb    = S.ef_pnb_series()
        roe    = S.ef_roe_series()
        coeff  = S.ef_coeff_series()
        cnr    = S.ef_cnr_series()
        growth = S.croissance_series()
        kp     = S.kpis_vue_ensemble(2026, "S1", segment, anx) or {}
    except Exception as e:
        return jsonify({"error": str(e), "analyses": {}}), 200

    cache = _ef_cache()
    # EMPREINTE DES DONNÉES DANS LA CLÉ (2026-07-30). La clé ne contenait que le segment et
    # l'ANx : les analyses EF ne pouvaient donc JAMAIS se régénérer d'elles-mêmes quand les
    # chiffres changeaient — il fallait incrémenter « v38 » à la main (l'historique du fichier
    # montre v9, v20, v25, v35, v38…). Concrètement, après l'ajout d'un exercice ou la
    # correction d'un montant, le dashboard continuait de servir une narration calculée sur les
    # ANCIENNES valeurs, sans aucun signal. En intégrant une empreinte des séries réellement
    # lues, tout changement de donnée produit une nouvelle clé, donc une régénération
    # automatique — et une donnée inchangée réutilise le cache, comme avant.
    import hashlib as _hef, json as _jef
    _sig_ef = _hef.md5(_jef.dumps(
        [rn, pnb, roe, coeff, cnr, growth,
         {k: v for k, v in sorted(kp.items()) if not k.endswith("_txt")}],
        sort_keys=True, default=str).encode("utf-8")).hexdigest()[:10]
    key = f"ef_v38_{segment}_{anx}_{_sig_ef}"
    if key in cache and cache[key]:
        # Ré-applique le polish courant au cache (nettoie les tics de remplissage même sur une version déjà générée).
        meta = _get_meta(cache, key)
        return jsonify({"analyses": {k: _llm_polish(v) for k, v in cache[key].items()}, "source": "cache",
                         "generated_at": meta.get("generated_at"), "stale": bool(meta.get("stale"))})

    # Mix commercial : part intérêts vs commissions dans le PNB, par banque.
    inte, comm, autr = kp.get("interets_data") or {}, kp.get("commissions_data") or {}, kp.get("autres_prod_data") or {}
    def _pc_comm(b):
        tot = (inte.get(b) or 0) + (comm.get(b) or 0) + (autr.get(b) or 0)
        return ((comm.get(b) or 0) / tot) if tot > 0 else 0
    mix_rows = []
    for b in sorted(set(list(inte) + list(comm)), key=lambda x: -_pc_comm(x)):
        tot = (inte.get(b) or 0) + (comm.get(b) or 0) + (autr.get(b) or 0)
        if tot <= 0:
            continue
        mix_rows.append(f"  {b}: intérêts {round((inte.get(b) or 0)/tot*100)}% / commissions {round((comm.get(b) or 0)/tot*100)}%")
    mix_txt = "\n".join(mix_rows) or "  (indisponible)"

    # Marge nette (RN/PNB, dernière année) — distincte du ROE.
    marge = kp.get("marge_nette_data") or {}
    marge_txt = ("  " + " · ".join(
        f"{b}:{round(v, 1)}%" for b, v in sorted(marge.items(), key=lambda x: -(x[1] or 0)) if v is not None
    )) if marge else "  (indisponible)"

    # Cascade de formation du résultat pour SGCI : PNB → RBE → RE → RN.
    rbe, re_, rnd, pnbd = kp.get("rbe_data") or {}, kp.get("re_data") or {}, kp.get("rn_data") or {}, kp.get("pnb_data") or {}
    p = pnbd.get("SGCI") or 0
    if p > 0:
        rb, r_, rn_ = rbe.get("SGCI") or 0, re_.get("SGCI") or 0, rnd.get("SGCI") or 0
        casc_txt = (
            f"  SGCI: PNB {round(p/1000)} Mds → RBE {round(rb/1000)} Mds ({round(rb/p*100)}% conservé après charges d'exploitation) "
            f"→ RE {round(r_/1000)} Mds ({round(r_/p*100)}% après coût du risque) "
            f"→ RN {round(rn_/1000)} Mds ({round(rn_/p*100)}% marge finale)"
        )
    else:
        casc_txt = "  (indisponible)"

    # Trajectoire de classement (bump) : rang par résultat net, première vs dernière année.
    # BUG TROUVÉ le 2026-07-22 (audit qualité) : comparer le MIN et le MAX globaux des années
    # (toutes banques confondues) ne fonctionne PAS ici — BACI (2021-2023) et BNI (2022-2024)
    # n'ont AUCUNE année en commun avec les 5 autres banques (2023-2025) : y0=2021 n'a QUE BACI,
    # y1=2025 n'a PAS BACI/BNI → zéro banque en commun → bump_txt toujours "(indisponible)",
    # et le LLM (au lieu de le dire honnêtement) avait fabriqué une analyse hors-sujet (chiffres
    # d'autres blocs, pas de rangs). Fix : choisir y0/y1 comme la PAIRE d'années qui maximise le
    # nombre de banques présentes aux DEUX dates (pas le min/max brut).
    yrs_rn = sorted({y for d in (rn or {}).values() for y in d})
    bump_txt, y0, y1 = "  (indisponible)", None, None
    if len(yrs_rn) >= 2:
        def _banks_at(y):
            return {b for b in rn if rn[b].get(y) is not None}
        best = (0, None, None)
        for i, ya in enumerate(yrs_rn):
            for yb in yrs_rn[i + 1:]:
                n_commun = len(_banks_at(ya) & _banks_at(yb))
                if n_commun > best[0]:
                    best = (n_commun, ya, yb)
        _, y0, y1 = best
        def _rank_at(y):
            vals = sorted(((b, (rn[b].get(y) or 0)) for b in rn if rn[b].get(y) is not None), key=lambda x: -x[1])
            return {b: i + 1 for i, (b, _) in enumerate(vals)}
        if y0 is not None and y1 is not None:
            r0, r1 = _rank_at(y0), _rank_at(y1)
            rows = []
            for b in sorted(r1, key=lambda x: r1[x]):
                if b in r0:
                    d = r0[b] - r1[b]
                    mv = f"↑{d}" if d > 0 else (f"↓{-d}" if d < 0 else "=")
                    rows.append(f"{b}:#{r0[b]}→#{r1[b]}({mv})")
            hors = sorted(b for b in rn if b not in r0 or b not in r1)
            bump_txt = ("  " + " · ".join(rows) + (f" [hors comparaison, données indisponibles en {y0} ou {y1} : {', '.join(hors)}]" if hors else "")) if rows else "  (indisponible)"

    # Ampleur de la domination (tree) : multiples de SGCI vs concurrents, dernière année.
    last_y = max(yrs_rn) if yrs_rn else None
    mult_txt = "  (indisponible)"
    if last_y is not None:
        lastvals = sorted(((b, (rn[b].get(last_y) or 0)) for b in rn), key=lambda x: -x[1])
        sg = dict(lastvals).get("SGCI", 0)
        others = [(b, v) for b, v in lastvals if b != "SGCI" and v > 0]
        if sg > 0 and others:
            to, lo = others[0], others[-1]
            mult_txt = (f"  SGCI {round(sg/1000)} Mds = {round(sg/to[1], 1)}× {to[0]} ({round(to[1]/1000)} Mds), "
                        f"{round(sg/lo[1], 1)}× {lo[0]} ({round(lo[1]/1000)} Mds)")

    # Podium / concentration (les 3 premiers du graphique 'podium') : noms + valeurs Mds + part cumulée.
    podium_txt = "  (indisponible)"
    if last_y is not None:
        _lv = sorted(((b, (rn[b].get(last_y) or 0)) for b in rn), key=lambda x: -x[1])
        _tot = sum(v for _, v in _lv) or 1
        _top3 = [(b, v) for b, v in _lv if v > 0][:3]
        if _top3:
            _t3share = round(sum(v for _, v in _top3) / _tot * 100)
            _sgshare = round((dict(_lv).get("SGCI", 0)) / _tot * 100)
            podium_txt = ("  Podium (résultat net) : " + ", ".join(f"{b} {round(v/1000, 1)} Mds" for b, v in _top3)
                          + f". À eux trois, ces établissements réunissent {_t3share}% des bénéfices du secteur ; "
                          + f"SGCI en concentre {_sgshare}% à lui seul.")

    # Levier de marge (share) : potentiel de RN si SGCI alignait sa marge sur la meilleure banque.
    sg_marge = marge.get("SGCI")
    best_m = max(marge.items(), key=lambda x: x[1] or 0) if marge else None
    share_txt = "  (indisponible)"
    if sg_marge and best_m and best_m[0] != "SGCI" and best_m[1]:
        gain = round((best_m[1] - sg_marge) / max(sg_marge, 1) * 100)
        share_txt = (f"  SGCI: part des bénéfices {kp.get('sgci_part_marche', '?')}%, marge nette {round(sg_marge, 1)}%. "
                     f"Meilleure marge du marché: {best_m[0]} {round(best_m[1], 1)}% (+{round(best_m[1] - sg_marge, 1)} pts). "
                     f"À PNB inchangé, aligner la marge sur {best_m[0]} ≈ +{gain}% de résultat net potentiel, sans un franc de crédit en plus.")

    # Transformation dépôts→crédits (cd).
    cred, dep = kp.get("credits_data") or {}, kp.get("depots_data") or {}
    cd_pairs = [(b, round((cred.get(b) or 0) / (dep.get(b) or 1) * 100)) for b in set(cred) & set(dep) if (dep.get(b) or 0) > 0]
    cd_txt = ("  " + " · ".join(f"{b}:{r}%" for b, r in sorted(cd_pairs, key=lambda x: -x[1]))) if cd_pairs else "  (indisponible)"

    # Coût du risque en % du PNB (= CE QU'AFFICHE le graphique 'ap-cr'), avec conversion FCFA + gain potentiel.
    crp = kp.get("cout_r_pnb_data") or {}
    sg_cr = crp.get("SGCI")
    pnb_sg = pnbd.get("SGCI") or 0
    risk_txt = "  (indisponible)"
    if sg_cr is not None and pnb_sg > 0:
        prov_sg = sg_cr / 100 * pnb_sg  # M FCFA de provisions
        pos = [(b, v) for b, v in crp.items() if v is not None and v > 0]
        parts = [f"SGCI provisionne {sg_cr:.1f}% de son PNB pour le risque crédit, soit ≈ {round(prov_sg/1000)} Mds FCFA qui ne deviennent jamais du profit"]
        if pos:
            best_b, best_v = min(pos, key=lambda x: x[1])
            if best_b != "SGCI" and best_v:
                gain = (sg_cr - best_v) / 100 * pnb_sg
                parts.append(f"le plus sain du marché est {best_b} à {best_v:.1f}% (SGCI provisionne {sg_cr/best_v:.0f}× plus)")
                parts.append(f"si SGCI ramenait ce taux au niveau de {best_b}, ce serait ≈ +{round(gain/1000)} Mds FCFA de résultat net, sans accorder un seul crédit de plus")
        risk_txt = "  " + " ; ".join(parts)

    # Coût du risque en POINTS DE BASE, ÉVOLUTION dans le temps (graphe 'ap-cnr-line') + contre-exemple d'amélioration.
    # NB : on ne retient QUE les années où SGCI a une vraie valeur (>0) — la série peut contenir une année vide (0) en tête.
    cnr_line_txt = "  (indisponible)"
    sg_years = sorted(y for y, v in (cnr.get("SGCI") or {}).items() if v)
    if len(sg_years) >= 2:
        cy0, cy1 = sg_years[0], sg_years[-1]
        sg0, sg1 = cnr["SGCI"][cy0], cnr["SGCI"][cy1]
        # Classement/médiane sur la DERNIÈRE valeur dispo de CHAQUE banque (certaines s'arrêtent en 2023) → les 7 banques.
        cnr_last = {b: v[max(v)] for b, v in cnr.items() if v}
        order = sorted(cnr_last.items(), key=lambda x: x[1])
        rank = [b for b, _ in order].index("SGCI") + 1 if "SGCI" in cnr_last else None
        lasts = sorted(cnr_last.values())
        med = lasts[len(lasts) // 2] if lasts else None
        # Contre-exemple : chaque banque comparée sur SES propres années à valeur réelle (>0).
        reducers = []
        for b, v in cnr.items():
            ys = sorted(y for y, val in v.items() if val)
            if b != "SGCI" and len(ys) >= 2 and v[ys[0]] > v[ys[-1]]:
                reducers.append((b, v[ys[0]], v[ys[-1]]))
        best_red = max(reducers, key=lambda x: x[1] - x[2]) if reducers else None
        parts = [f"SGCI : {round(sg0)}pb ({cy0}) → {round(sg1)}pb ({cy1}), soit une AUGMENTATION de {'+' if sg1 >= sg0 else ''}{round(sg1 - sg0)}pb (l'augmentation, PAS le niveau) ; rang #{rank}/{len(order)} (plus haut = pire) ; médiane du marché {round(med)}pb"]
        if best_red:
            parts.append(f"CONTRE-EXEMPLE {best_red[0]} : {round(best_red[1])}pb → {round(best_red[2])}pb (÷{best_red[1]/best_red[2]:.1f}), preuve qu'une forte réduction est atteignable avec une sélection crédit et un recouvrement plus stricts")
        if sg1 > 150:
            parts.append("SGCI se rapproche de la zone de surveillance BCEAO (>200pb)")
        cnr_line_txt = "  " + " ; ".join(parts)

    # Coefficient d'exploitation — ÉVOLUTION dans le temps (graphe 'ap-coeff-line'), plus BAS = mieux + banque qui s'améliore le plus.
    coeff_line_txt = "  (indisponible)"
    co_years = sorted(y for y, v in (coeff.get("SGCI") or {}).items() if v)
    if len(co_years) >= 2:
        oy0, oy1 = co_years[0], co_years[-1]
        so0, so1 = coeff["SGCI"][oy0], coeff["SGCI"][oy1]
        co_last = {b: v[max(v)] for b, v in coeff.items() if v}          # dernière valeur de chaque banque (7)
        o_order = sorted(co_last.items(), key=lambda x: x[1])            # bas = meilleur
        o_rank = [b for b, _ in o_order].index("SGCI") + 1 if "SGCI" in co_last else None
        improvers = []
        for b, v in coeff.items():
            ys = sorted(y for y, val in v.items() if val)
            if b != "SGCI" and len(ys) >= 2:
                improvers.append((b, v[ys[0]], v[ys[-1]], v[ys[0]] - v[ys[-1]]))
        best_imp = max(improvers, key=lambda x: x[3]) if improvers else None
        o_bceao = "excellence BCEAO (<40%)" if so1 < 40 else ("zone bon (<50%)" if so1 < 50 else "zone acceptable")
        parts_o = [f"SGCI : {so0:.1f}% ({oy0}) → {so1:.1f}% ({oy1}), soit {'+' if so1 >= so0 else '−'}{abs(so1 - so0):.1f}pt ; rang #{o_rank}/{len(o_order)} (plus bas = mieux), {o_bceao}"]
        if best_imp and best_imp[3] > 0:
            parts_o.append(f"la plus forte amélioration vient de {best_imp[0]} : {best_imp[1]:.1f}% → {best_imp[2]:.1f}% (−{best_imp[3]:.1f}pt), son écart avec SGCI se resserre nettement")
        coeff_line_txt = "  " + " ; ".join(parts_o)

    growth_txt = " ".join(
        f"{b}:+{round(v)}%" for b, v in sorted((growth or {}).items(), key=lambda x: -(x[1] or 0))
        if v is not None
    ) or "(indisponible)"

    # RANGS pré-calculés de SGCI (le LLM doit REPORTER ces rangs, pas recalculer la direction).
    def _last_map(series):
        out = {}
        for b, yv in (series or {}).items():
            if isinstance(yv, dict) and yv:
                out[b] = yv[max(yv)]
            elif yv is not None and not isinstance(yv, dict):
                out[b] = yv
        return out

    def _rank_txt(m, lower_better):
        m = {b: v for b, v in (m or {}).items() if v is not None}
        if "SGCI" not in m:
            return "(indisponible)"
        names = [b for b, _ in sorted(m.items(), key=lambda x: (x[1] if lower_better else -x[1]))]
        r = names.index("SGCI") + 1
        ahead = names[:r - 1]
        if ahead:
            return f"#{r}/{len(names)} — font mieux que SGCI : " + ", ".join(ahead)
        return f"#{r}/{len(names)} — " + ("SGCI a le plus BAS, donc le MEILLEUR du marché" if lower_better else "SGCI en tête, le meilleur du marché")

    cd_map = {b: r for b, r in cd_pairs}
    pos_txt = (
        f"  Marge nette (haut=mieux) : SGCI {_rank_txt(marge, False)}\n"
        f"  ROE (haut=mieux) : SGCI {_rank_txt(_last_map(roe), False)}\n"
        f"  Coefficient d'exploitation (BAS=mieux) : SGCI {_rank_txt(_last_map(coeff), True)}\n"
        f"  Coût du risque / PNB (BAS=mieux) : SGCI {_rank_txt(crp, True)}\n"
        f"  Ratio crédits/dépôts (le plus élevé transforme le plus) : SGCI {_rank_txt(cd_map, False)}\n"
        f"  Résultat net (haut=mieux) : SGCI {_rank_txt(_last_map(rn), False)}"
    )

    facts = (
        f"POSITIONS / RANGS DE SGCI (source de vérité pour la DIRECTION des comparaisons — reporte ces rangs, ne les recalcule pas):\n{pos_txt}\n\n"
        f"RÉSULTAT NET (Mds FCFA, par année):\n{_ef_fmt(rn, 1 / 1000)}\n\n"
        f"PODIUM — les 3 premières banques par résultat net (CE QU'AFFICHE le graphique 'podium', avec leurs montants) :\n{podium_txt}\n\n"
        f"CLASSEMENT par résultat net — trajectoire des RANGS ({y0}→{y1}, ↑ = monte):\n{bump_txt}\n\n"
        f"AMPLEUR — multiples de SGCI vs concurrents (résultat net, dernière année):\n{mult_txt}\n\n"
        f"PNB — Produit Net Bancaire (Mds FCFA):\n{_ef_fmt(pnb, 1 / 1000)}\n\n"
        f"TRANSFORMATION dépôts→crédits (ratio crédits/dépôts, ~80-100% = zone idéale BCEAO):\n{cd_txt}\n\n"
        f"LEVIER DE MARGE (part de marché bénéfices + potentiel si marge alignée sur la meilleure):\n{share_txt}\n\n"
        f"MARGE NETTE (résultat net / PNB, %, dernière année — NE PAS confondre avec le ROE):\n{marge_txt}\n\n"
        f"ROE — rentabilité des CAPITAUX PROPRES (%, distinct de la marge nette):\n{_ef_fmt(roe, 1, '%', 1)}\n\n"
        f"COEFFICIENT D'EXPLOITATION (charges/PNB, %, plus BAS = mieux):\n{_ef_fmt(coeff, 1, '%', 1)}\n\n"
        f"COEFFICIENT D'EXPLOITATION — ÉVOLUTION dans le temps (graphe séparé 'coeff_line', plus BAS = mieux) :\n{coeff_line_txt}\n"
        f"  (classement par banque, dernière valeur dispo, %) : {'  '.join(f'{b}:{v[max(v)]:.1f}%' for b, v in sorted(((b, v) for b, v in coeff.items() if v), key=lambda x: x[1][max(x[1])]))}\n\n"
        f"CASCADE de formation du résultat (comment le PNB devient RN, étape par étape):\n{casc_txt}\n\n"
        f"COÛT DU RISQUE en % du PNB (LE CHIFFRE DU GRAPHIQUE — provisions créances douteuses / PNB) :\n{risk_txt}\n"
        f"  (rappel des taux par banque, coût du risque/PNB %) : {'  '.join(f'{b}:{v:.1f}%' for b, v in sorted(crp.items(), key=lambda x: x[1] or 0) if v is not None)}\n\n"
        f"COÛT DU RISQUE en POINTS DE BASE — ÉVOLUTION dans le temps (graphe séparé 'cnr_line') :\n{cnr_line_txt}\n"
        f"  (classement par banque, dernière année, pb) : {'  '.join(f'{b}:{round(v)}pb' for b, v in sorted(_last_map(cnr).items(), key=lambda x: x[1]) if v is not None)}\n\n"
        f"CROISSANCE du résultat net cumulée sur la période: {growth_txt}\n\n"
        f"MIX COMMERCIAL du PNB (part intérêts vs commissions):\n{mix_txt}"
    )
    blocs = "\n".join(f'- "{k}" : {v}' for k, v in _EF_BLOCKS.items())
    prompt = f"""Tu es analyste financier senior du secteur bancaire ivoirien (UEMOA). Voici les états financiers RÉELS de SGCI (Société Générale Côte d'Ivoire) et de ses concurrents, sur plusieurs années :

{facts}

Rédige une courte analyse pour CHACUN de ces blocs (chacun affiché sous un graphique DIFFÉRENT) :
{blocs}

RÈGLES ABSOLUES :
1. Chaque bloc traite UNIQUEMENT son angle — NE JAMAIS répéter un constat déjà fait ailleurs (bannir « SGCI capte X% des bénéfices », « SGCI domine/leader », « effet de base » répétés partout).
2. INTERDIT DE RÉPÉTER UN THÈME : l'idée « SGCI est le plus gros / leader en VOLUME » ne s'énonce qu'UNE SEULE fois (bloc « signal »). « podium », « tree », « pnb » ne redisent PAS cette idée — chacun apporte un CHIFFRE NOUVEAU et précis sous un autre angle : podium = les 3 premières banques NOMMÉES avec leurs montants (SGCI, ECOBANK, SIB…) + la part des bénéfices qu'elles réunissent ; tree = ampleur de l'écart en MULTIPLES (ex. 1,6×, 2,8×) ; pnb = niveau de PNB comparé aux concurrents (garde les chiffres comparés). Reste toujours PRÉCIS et chiffré.
3. Raconte une HISTOIRE avec un FIL : SGCI est fort en volume (dit une fois), mais l'enjeu réel se déplace vers l'EFFICACITÉ (marge, ROE, coût du risque). Chaque bloc fait avancer ce fil et exploite l'ÉVOLUTION dans le temps quand la donnée le permet.
4. UNIQUEMENT les chiffres ci-dessus — n'invente AUCUN nombre, et fonde-toi sur les RANGS RÉELS fournis (ne présume pas le n°1 ; n'ajoute PAS de formule vague type « le rang peut évoluer »).
5. Point de vue SGCI : ce qui est un atout, ce qui est une menace, qui surveiller.
6. PÉDAGOGIE CHIFFRÉE OBLIGATOIRE : quand un bloc de facts te donne des Mds FCFA, un multiple (×) ou un gain potentiel, tu DOIS les réutiliser mot pour mot dans ton analyse (ne te contente pas du %). Ex. pour le coût du risque : reprends « ≈ X Mds FCFA de provisions », « Y× plus que [banque] », « +Z Mds FCFA de résultat net si SGCI s'alignait ». Chaque phrase = un ton simple et pro, accessible à un non-financier, qui explique D'OÙ vient le chiffre ET son « et alors ? ».
7. CHAQUE phrase doit contenir un CHIFFRE PRÉCIS et une conséquence concrète. Bannis « cela signifie que » SOUS TOUTES SES FORMES, y compris au milieu d'une phrase (« …, cela signifie que la banque domine » = INTERDIT) : dis directement le fait, sans ce connecteur creux. Bannis aussi « doit améliorer sa marge/son efficacité », « atteindre son plein potentiel », « regarder les autres indicateurs », « une certaine capacité à… », « il est important de… ». Si tu n'as rien de chiffré à ajouter, ARRÊTE-toi.
8. LONGUEUR & STRUCTURE : blocs de graphique = 2 phrases ; « cnr_line » et « coeff_line » = 3 phrases (trajectoire, contre-exemple, implication). SIGNAUX s1/s2/s3 = EXACTEMENT 2 phrases : (1) UN constat chiffré et étoffé de la section (le « et alors »), (2) UNE SEULE phrase de transition élégante vers la section suivante — une seule, en DERNIER, jamais deux questions, jamais un exemple recopié tel quel. Inspire-toi de ces AMORCES (ne les recopie pas mot pour mot, reformule) : s1→revenus « Reste à savoir si ce leadership en profit s'adosse aux revenus les plus élevés. » ; s2→efficacité « Encore faut-il que ce revenu record se convertisse en profit. » ; s3→risque « Se pose alors une question : où le profit s'évapore-t-il ? ». s4 = 2 phrases : constat + conclusion actionnable chiffrée (PAS de question). line_roe/line_pnb = 2 phrases. INTERDIT d'ajouter une phrase de conseil générique (« SGCI doit améliorer son efficacité… ») en plus. Chaque phrase finit par sa ponctuation suivie de « <br> ». <b> pour les chiffres.
9. SENS DES COMPARAISONS — appuie-toi sur le bloc « POSITIONS / RANGS DE SGCI » pour la direction (ne recalcule pas « supérieur/inférieur » toi-même, tu te trompes). Pour COEFFICIENT et COÛT DU RISQUE un chiffre PLUS BAS est MEILLEUR (37,2% est meilleur que 42,9%) ; pour marge, ROE, croissance, PNB, résultat net un chiffre PLUS HAUT est meilleur. Vérifie chaque nombre : ne dis jamais « supérieur » pour un nombre plus petit.
10. NIVEAU DE LANGUE SOUTENU (exigence forte) : rédige comme un analyste financier senior s'adressant au comité de direction — phrases bien construites, vocabulaire précis, verbes VARIÉS et justes (domine, réalise, affiche, dégage, s'établit à, demeure, s'impose, occupe le premier rang, accuse un retard…), connecteurs élégants (toutefois, néanmoins, en revanche, pour autant, dès lors, à l'inverse), ponctuation soignée (point-virgule, deux-points). BANNIS les tournures plates et répétitives : « est #1 », « avec X Mds », « ce qui est inférieur à celui/celle de… », « ce qui est supérieur à… », deux « mais » qui se suivent. À la place de « inférieur à », VARIE : « en retrait sur SIB (51,2%) », « loin derrière SIB », « à 14,5 points de SIB », « quand SIB culmine à 51,2% », « là où SIB atteint 51,2% », « soit deux tiers de la marge de SIB ». PAS de jargon obscur pour autant (INTERDITS : « oligopolistique », « structure du secteur », « il est important de noter »). EXEMPLE — AVANT (trop courant) : « SGCI est #1 en résultat net avec 101 Mds, mais son ROE est de 20,5%, ce qui est inférieur à celui de certains de ses concurrents. Mais générer le plus de bénéfices, est-ce générer le plus de revenus ? » → APRÈS (soutenu) : « SGCI domine le marché avec un résultat net de 101 Mds FCFA ; sa rentabilité des capitaux propres, à 20,5%, demeure toutefois en retrait sur ses pairs. Dès lors, une question s'impose : réaliser le plus gros bénéfice revient-il à générer le plus de revenus ? »
11. INTERDIT ABSOLU d'avouer qu'une donnée manque (« le poids exact n'est pas donné », « les chiffres ne sont pas précisés », « non communiqué ») : TOUTES les données nécessaires sont ci-dessus. CHAQUE analyse cite les CHIFFRES VISIBLES sur SON graphique (les montants, les banques affichées) — jamais une généralité qui pourrait s'appliquer à n'importe quelle banque.
12. TENSION RANG ACTUEL vs TRAJECTOIRE : si une banque citée dans un bloc (croissance, coût du risque, coefficient…) progresse fortement MAIS reste actuellement dernière ou en retard en volume/rang (et inversement : en tête en volume mais qui recule/stagne), dis-le explicitement dans LA MÊME PHRASE ou la suivante — ne laisse jamais cette contradiction implicite entre deux blocs séparés. Ex. : « BICICI, dernière du classement avec 37 Mds FCFA, est aussi celle qui progresse le plus vite (+119%) : un retard de volume qui pourrait ne pas durer. » Ne recopie pas cet exemple mot pour mot, adapte-le aux chiffres réels fournis.
13. EXIGENCE DE PROFONDEUR (niveau comité de direction, pas un résumé de chiffres) : chaque bloc doit apporter un ANGLE QUI NE SAUTE PAS AUX YEUX rien qu'en lisant le graphique — croise DEUX chiffres de blocs différents fournis ci-dessus (ex. ROE + coût du risque, marge + coefficient, croissance + rang) pour révéler un paradoxe, un levier caché ou une vulnérabilité que le lecteur n'aurait pas vue en regardant un seul chiffre isolé. Termine par une IMPLICATION concrète à 12-24 mois pour SGCI, ancrée dans les chiffres (pas une généralité du type « SGCI doit rester vigilante »). Si un bloc ne fait que reformuler le graphique sans ce niveau de lecture, il est raté — recommence-le mentalement avant de l'écrire.

FORMAT DE SORTIE (STRICT — PAS de JSON, PAS de guillemets) : pour chaque bloc, écris une ligne marqueur « @@clé@@ » seule, puis l'analyse en dessous (avec ses <br>). Enchaîne les 15 blocs. Exemple :
@@signal@@
SGCI est <b>#1</b> en résultat net…<br>…<br>…
@@podium@@
…
Utilise EXACTEMENT ces clés : {", ".join("@@%s@@" % k for k in _EF_BLOCKS)}."""

    # Santé Financière → Claude (2026-07-15, demande explicite). CB et Stratégie restent sur
    # Groq pour l'instant (pas de bascule globale, juste ce point d'appel précis).
    txt, engine = _rp_llm_json(prompt, max_tokens=7500, temperature=0.3, prefer_claude=True)
    parsed = None
    if txt:
        # Format à marqueurs @@clé@@ (robuste : le HTML/virgules/retours ligne ne cassent rien).
        segs = _re_rp.split(r"@@\s*([a-zA-Z0-9_]+)\s*@@", txt)
        parsed = {}
        for i in range(1, len(segs) - 1, 2):
            k = segs[i].strip()
            v = segs[i + 1].strip().strip("`").strip()
            v = _re_rp.sub(r"^json\s*", "", v)  # retire un éventuel reliquat de fence
            if k in _EF_BLOCKS and v:
                parsed[k] = _llm_polish(_llm_br(v))
    def _secours(motif):
        """Analyses calculées, quand le modèle n'a rien rendu d'exploitable.

        AJOUTÉ LE 2026-08-11. On renvoyait un jeu VIDE, et le front laissait ses quatre blocs
        « Signal Analytique » sur « Analyse en cours… » — définitivement, une fois les quatre
        reprises épuisées. Mesuré sur le service en ligne : vingt-huit blocs figés, alors que
        les chiffres étaient là (ils servaient à composer le prompt).
        """
        try:
            import redaction_secours as _sec
            textes = _sec.ef_signaux(kp)
            if textes:
                print(f"[ef_llm] {motif} → rédaction de secours ({len(textes)} blocs)")
                return jsonify({"analyses": textes, "source": "deterministe",
                                "mention": _sec.MENTION}), 200
        except Exception as e:
            print("[ef_llm] secours impossible :", str(e)[:160])
        return jsonify({"analyses": {}, "source": "none", "error": motif}), 200

    if not parsed or not isinstance(parsed, dict) or not parsed:
        return _secours("aucune analyse rendue")
    missing = [k for k in _EF_BLOCKS if k not in parsed]
    if missing:
        # Réponse tronquée (max_tokens atteint avant la fin) : on ne met PAS en cache un jeu de
        # blocs incomplet (sinon il serait servi comme définitif pour toujours, cf. bug trouvé le
        # 2026-07-15 sur Entreprises/anx=3 où s2/s3 manquaient silencieusement).
        print(f"[ef_llm] réponse incomplète ({engine}), blocs manquants : {missing}")
        return _secours("réponse incomplète")
    cache[key] = parsed
    _mark_fresh(cache, key)
    try:
        with open(_EF_LLM_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[ef_llm] persist:", e)
    meta = _get_meta(cache, key)
    return jsonify({"analyses": parsed, "source": engine or "groq",
                     "generated_at": meta.get("generated_at"), "stale": False})


_JUSTIF_CACHE = None
@app.route("/api/cb_justifications")
def api_cb_justifications():
    """Justifications PRÉCALCULÉES (analyste + sources publiques) du caractère exclusif /
    inimitable / transformatif. Servies depuis un cache fichier — aucun appel LLM en direct."""
    global _JUSTIF_CACHE
    if _JUSTIF_CACHE is None:
        import json as _json, os as _os
        try:
            p = _os.path.join(DOSSIER_DATA, "cb_justifications.json")
            with open(p, encoding="utf-8") as f:
                _JUSTIF_CACHE = _json.load(f)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify(_JUSTIF_CACHE)


_STRAT_CACHE = {}
_STRAT_BUILD_FILE = os.path.join(DOSSIER_CACHE, "strategie_build_cache.json")
# Faits de veille : c'est leur horodatage qui décide si le build Stratégie doit être refait.
WEB_FACTS_FILE = os.path.join(DOSSIER_DATA, "web_facts.json")


def _strat_build_load():
    """Charge le build Stratégie depuis le disque (persistant) → évite les ~100 s de reconstruction
    à chaque redémarrage.

    INVALIDATION ÉLARGIE (2026-07-30). Ce cache n'était purgé qu'à l'ingestion de données. Or la
    Stratégie s'appuie aussi sur la VEILLE (PESTEL, faits sectoriels, événements de marché) :
    après un passage de l'agent web, le dashboard continuait de servir une analyse construite sur
    l'état précédent du monde, sans aucun signal. Constaté en ajoutant les signaux de marché au
    PESTEL — ils n'apparaissaient nulle part alors que le code les produisait.
    On compare donc l'horodatage du cache à celui de web_facts.json : si la veille est plus
    récente, on repart de zéro. Le coût (une reconstruction) est payé une fois par collecte,
    pas à chaque requête.
    """
    if _STRAT_CACHE:
        return
    try:
        with open(_STRAT_BUILD_FILE, encoding="utf-8") as f:
            contenu = json.load(f)
    except Exception:
        return
    try:
        # CHEMIN CORRIGÉ le 2026-07-30. Il pointait encore sur dash_app/web_facts.json, alors que
        # le fichier a été déplacé dans data/ lors du rangement du dépôt. getmtime levait donc
        # FileNotFoundError, l'exception était avalée par le `except` ci-dessous, et le contrôle
        # de fraîcheur ne s'exécutait plus JAMAIS : le dashboard resservait indéfiniment une
        # analyse construite sur l'état précédent du monde. Une panne silencieuse — exactement
        # celle que ce bloc avait été écrit pour empêcher.
        veille = os.path.getmtime(WEB_FACTS_FILE)
        cache_t = os.path.getmtime(_STRAT_BUILD_FILE)
        if veille > cache_t:
            print("[strat] veille plus récente que le cache → reconstruction")
            return
    except Exception as e:
        print("[strat] contrôle de fraîcheur impossible :", str(e)[:120])
    _STRAT_CACHE.update(contenu)


def _json_default(o):
    """Types non-JSON que Flask jsonify accepte mais pas json.dump : Decimal → float (PRÉSERVE le
    type numérique, sinon le front casserait sur .toFixed), le reste → str."""
    import decimal
    if isinstance(o, decimal.Decimal):
        return float(o)
    return str(o)


def _strat_build_persist():
    try:
        # Écriture atomique (tmp puis rename) → jamais de fichier tronqué qui corromprait le cache.
        _tmp = _STRAT_BUILD_FILE + ".tmp"
        with open(_tmp, "w", encoding="utf-8") as f:
            json.dump(_STRAT_CACHE, f, ensure_ascii=False, default=_json_default)
        os.replace(_tmp, _STRAT_BUILD_FILE)
    except Exception as e:
        print("[strat_build] persist:", e)


def _strat_get(segment):
    """Build Stratégie : cache mémoire → disque (persistant) → construit + persiste. Évite les
    ~100 s de reconstruction (une seule fois, puis 0 s même après redémarrage)."""
    _strat_build_load()
    d = _STRAT_CACHE.get(segment)
    if d is None:
        d = strategie.build(segment)
        _STRAT_CACHE[segment] = d
        _strat_build_persist()
    return d


@app.route("/api/strategie")
def api_strategie():
    """STRATÉGIE — Niveau 3 du RAG : mobilise les agents EF + CB + REGL + WEB,
    produit le dossier de preuves sourcé, le diagnostic, SWOT, Porter, le plan
    d'action chiffré, la projection 3 ans et les métriques. 100 % déterministe.
    Résultat CACHÉ sur disque (reproductible) → chargement instantané après la 1ʳᵉ fois."""
    segment = request.args.get("segment", "Particuliers")
    _strat_build_load()
    if segment in _STRAT_CACHE:
        return jsonify(_STRAT_CACHE[segment])
    try:
        data = strategie.build(segment)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    _STRAT_CACHE[segment] = data
    _strat_build_persist()
    return jsonify(data)


@app.route("/api/strategie_diag_llm")
def api_strategie_diag_llm():
    """Habillage LLM du Diagnostic 360° (2026-07-16, demande explicite du directeur : « chaque
    moindre détail doit être fait par le LLM »). La DÉTECTION reste 100% déterministe (seuils
    calculés sur les vraies données, cf. detect_problems() dans strategie.py — ne doit JAMAIS
    dépendre d'un LLM, sinon un problème réel pourrait être manqué ou halluciné). Seule la PROSE
    de chaque « preuve » est reformulée par Claude, en gardant EXACTEMENT les mêmes chiffres.
    Retourne {preuves: {titre: texte_enrichi}} — le front garde le texte déterministe en secours
    si une entrée manque (LLM indisponible)."""
    segment = request.args.get("segment", "Particuliers")
    try:
        d = _strat_get(segment)
    except Exception as e:
        return jsonify({"preuves": {}, "source": "none", "error": str(e)}), 200
    probs = (d.get("problemes") or [])[:8]
    if not probs:
        return jsonify({"preuves": {}, "source": "none"}), 200

    facts = "\n".join(
        f"  {i+1}. « {p.get('titre')} » (gravité {p.get('gravite')}/3) — {p.get('preuve')}"
        for i, p in enumerate(probs)
    )
    import hashlib as _hl3
    key = f"strat_diag_v1_{segment}_{_hl3.md5(facts.encode('utf-8')).hexdigest()[:10]}"
    cache = _strat_narr_cache()
    if cache.get(key):
        return jsonify({"preuves": cache[key], "source": "cache"})

    prompt = f"""Tu es analyste financier senior du secteur bancaire ivoirien, plume du comité de direction de SGCI.
Voici {len(probs)} problèmes DÉJÀ DÉTECTÉS (seuils/calculs déterministes, ne remets PAS en cause leur existence ni leur gravité) :
{facts}

Pour CHACUN, réécris la « preuve » en 2 phrases d'analyste SOUTENUES (pas un résumé plat du chiffre) :
CROISE-la si possible avec un autre problème de la liste (ex. un problème EF qui explique/aggrave un problème CB, ou l'inverse) pour révéler un lien que la liste plate ne montre pas, et termine par une implication concrète à 12-24 mois. RECOPIE tous les chiffres EXACTEMENT comme donnés (n'en invente, n'en arrondis, n'en omets AUCUN). INTERDIT : « cela signifie que », « il est important de », conclusions vagues. <b> sur les chiffres. Phrases courtes, une par ligne (point puis <br>).

FORMAT (marqueurs, PAS de JSON) :
@@p1@@
…
@@p2@@
…
(un marqueur @@pN@@ par problème, dans l'ordre ci-dessus, jusqu'à @@p{len(probs)}@@)"""

    txt, engine = _rp_llm_json(prompt, max_tokens=3000, temperature=0.3, prefer_claude=True)
    preuves = {}
    if txt:
        segs = _re_rp.split(r"@@\s*p(\d+)\s*@@", txt)
        for i in range(1, len(segs) - 1, 2):
            try:
                idx = int(segs[i]) - 1
            except Exception:
                continue
            v = segs[i + 1].strip()
            if 0 <= idx < len(probs) and v:
                preuves[probs[idx]["titre"]] = _llm_polish(_llm_br(v))
    if not preuves:
        return jsonify({"preuves": {}, "source": "none"}), 200
    cache[key] = preuves
    _mark_fresh(cache, key)
    try:
        with open(_STRAT_NARR_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[strat_diag] persist:", e)
    return jsonify({"preuves": preuves, "source": engine or "groq"})


@app.route("/api/strategie_projection_llm")
def api_strategie_projection_llm():
    """Lecture stratégique de la Projection 3 scénarios (2026-07-16, demande explicite : « rajouter
    une intelligence derrière, quelque chose de WOW »). Le MODÈLE reste 100% déterministe (chiffres
    calculés, jamais inventés par un LLM — une projection financière ne doit jamais être « racontée »)
    : cette route ne fait QUE croiser les 3 métriques déjà calculées (PNB, coût du risque, résultat
    net) pour révéler ce qu'une lecture graphique isolée ne montre pas."""
    segment = request.args.get("segment", "Particuliers")
    try:
        d = _strat_get(segment)
    except Exception as e:
        return jsonify({"analyse": "", "source": "none", "error": str(e)}), 200
    proj = d.get("projection") or []
    if not proj:
        return jsonify({"analyse": "", "source": "none"}), 200

    facts = "\n\n".join(
        f"{p.get('nom')} (en {p.get('unite', p.get('nom'))}) :\n"
        f"  - Départ (AN0) : {p.get('depart')}\n"
        f"  - Sans rien changer (AN3) : {p.get('actuel_an3')}\n"
        f"  - Scénario central, plan tenu (AN3) : {p.get('central_an3')}\n"
        f"  - Fourchette prudent → optimiste (AN3) : {p.get('fourchette_an3')}\n"
        f"  - Hypothèse du modèle : {p.get('hypothese')}"
        for p in proj
    )
    import hashlib as _hl4
    key = f"strat_proj_v1_{segment}_{_hl4.md5(facts.encode('utf-8')).hexdigest()[:10]}"
    cache = _strat_narr_cache()
    if cache.get(key):
        return jsonify({"analyse": cache[key], "source": "cache"})

    prompt = f"""Tu es analyste financier senior, plume du comité de direction de SGCI (banque, Côte d'Ivoire).
Voici la projection à 3 ans DÉJÀ CALCULÉE (modèle déterministe, ne recalcule RIEN, n'invente AUCUN chiffre) :

{facts}

Rédige une LECTURE STRATÉGIQUE de cette projection, en 4 phrases denses et percutantes, niveau comité de direction :
1. CROISE au moins deux des trois métriques ci-dessus pour montrer LE MÉCANISME du scénario central (ex. comment la baisse du coût du risque ET la hausse du PNB se combinent sur le résultat net) — pas une simple liste des trois chiffres.
2. Chiffre L'ÉCART EN VALEUR ABSOLUE (Mds FCFA) entre « sans rien changer » et le scénario central à AN3 — c'est le prix concret de l'inaction.
3. Identifie LA condition la plus fragile du scénario (laquelle des hypothèses, si elle ne tient pas, fait le plus dérailler le plan) — sois spécifique, pas vague.
4. Termine par UNE phrase percutante et mémorable, formulée pour rester en tête d'un comité de direction (pas une question, une affirmation forte, ancrée sur un chiffre).
RÈGLES : recopie CHAQUE chiffre EXACTEMENT comme fourni (aucun arrondi différent). Si tu reprends UNE MÊME quantité (ex. l'écart AN3 de la phrase 2) dans une autre phrase, RÉUTILISE EXACTEMENT le même nombre — ne le recalcule jamais une seconde fois, copie-le tel quel. <b> sur les chiffres clés. Une phrase par ligne (point puis <br>). INTERDIT : « cela signifie que », « il est important de », toute généralité qui pourrait s'appliquer à n'importe quelle banque."""

    txt, engine = _rp_llm_json(prompt, max_tokens=1200, temperature=0.2, prefer_claude=True)
    if not txt:
        return jsonify({"analyse": "", "source": "none"}), 200
    analyse = _llm_polish(_llm_br(txt.strip()))
    _invente = _chiffres_inventes(analyse, facts)
    if _invente:
        print(f"[strat_proj] REJETÉ (0 hallucination) — chiffres non fournis détectés : {_invente}")
        return jsonify({"analyse": "", "source": "none"}), 200
    cache[key] = analyse
    _mark_fresh(cache, key)
    try:
        with open(_STRAT_NARR_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[strat_proj] persist:", e)
    return jsonify({"analyse": analyse, "source": engine or "groq"})


@app.route("/api/strategie_switch_llm")
def api_strategie_switch_llm():
    """Lecture stratégique des coûts de changement (cartes « Atout prix » / « Risque prix »,
    2026-07-16, demande explicite du directeur). Les MONTANTS restent 100% déterministes
    (prix réels CB, jamais inventés) — Claude n'ajoute qu'une lecture stratégique par-dessus."""
    segment = request.args.get("segment", "Particuliers")
    try:
        d = _strat_get(segment)
    except Exception as e:
        return jsonify({"analyse": "", "source": "none", "error": str(e)}), 200
    sw = d.get("couts_changement") or {}
    gains, fuites = sw.get("gains") or [], sw.get("fuites") or []
    if not gains and not fuites:
        return jsonify({"analyse": "", "source": "none"}), 200

    gains_txt = "\n".join(f"  - {g['phrase']}" for g in gains[:6]) or "  (aucun)"
    fuites_txt = "\n".join(f"  - {f['phrase']}" for f in fuites[:6]) or "  (aucun)"
    facts = (f"ATOUTS PRIX (SGCI moins chère, un client économise en la rejoignant) :\n{gains_txt}\n"
             f"  Total : {sw.get('n_gains', len(gains))} services, économie max {sw.get('max_gain', 0)} FCFA/an\n\n"
             f"RISQUES PRIX (SGCI plus chère, un client pourrait partir) :\n{fuites_txt}\n"
             f"  Total : {sw.get('n_fuites', len(fuites))} services, écart max {sw.get('max_fuite', 0)} FCFA/an")
    import hashlib as _hl5
    key = f"strat_switch_v2_{segment}_{_hl5.md5(facts.encode('utf-8')).hexdigest()[:10]}"
    cache = _strat_narr_cache()
    if cache.get(key):
        return jsonify({"analyse": cache[key], "source": "cache"})

    prompt = f"""Tu es analyste financier senior, plume du comité de direction de SGCI (banque, Côte d'Ivoire), segment {segment}.
Voici les écarts de prix RÉELS déjà calculés entre SGCI et ses concurrents, sur les services les plus demandés (jamais de chiffre à inventer) :

{facts}

Rédige une LECTURE STRATÉGIQUE en 3 phrases denses, niveau comité de direction :
1. Compare le RAPPORT DE FORCE entre les atouts prix et les risques prix (lequel pèse le plus, en nombre de services ET en montant) — qu'est-ce que ce déséquilibre révèle sur le positionnement prix global de SGCI ?
2. Nomme LE service ou la banque la plus significative de chaque côté (le plus gros atout, le plus gros risque) et ce que SGCI doit concrètement en faire (mettre en avant / corriger).
3. Termine par une implication actionnable pour la stratégie commerciale (pas une généralité) — QUALITATIVE (quoi faire, sur quel service, contre quelle banque), jamais un chiffre qui n'est pas dans les données ci-dessus.
RÈGLES : recopie CHAQUE chiffre EXACTEMENT comme fourni. <b> sur les chiffres clés. Une phrase par ligne (point puis <br>). INTERDIT : « cela signifie que », « il est important de », toute généralité qui pourrait s'appliquer à n'importe quelle banque. GARDE-FOU ANTI-INVENTION (2026-07-21, trouvé en test — le LLM a inventé « 1 000 nouveaux clients en 6 mois » et « 11 000 000 FCFA de gain total », des chiffres absents des données) : N'INVENTE JAMAIS un nombre de clients, un montant agrégé/total, un pourcentage ou un délai qui n'est pas explicitement dans les données ci-dessus — seuls les montants FCFA par service fournis existent."""

    txt, engine = _rp_llm_json(prompt, max_tokens=900, temperature=0.2, prefer_claude=True)
    if not txt:
        return jsonify({"analyse": "", "source": "none"}), 200
    analyse = _llm_polish(_llm_br(txt.strip()))
    _invente = _chiffres_inventes(analyse, facts)
    if _invente:
        print(f"[strat_switch] REJETÉ (0 hallucination) — chiffres non fournis détectés : {_invente}")
        return jsonify({"analyse": "", "source": "none"}), 200
    cache[key] = analyse
    _mark_fresh(cache, key)
    try:
        with open(_STRAT_NARR_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[strat_switch] persist:", e)
    return jsonify({"analyse": analyse, "source": engine or "groq"})


@app.route("/api/strategie_roadmap_llm")
def api_strategie_roadmap_llm():
    """Lecture stratégique du plan-trajectoire 3 ans (2026-07-16, demande explicite : « toute la
    partie Décision doit être faite avec le LLM »). Les actes/horizons/objectifs restent 100%
    déterministes (actions concrètes, chiffrage sourcé — pas de place à l'invention sur un plan
    d'action). Claude ajoute la LOGIQUE D'ENSEMBLE : pourquoi cet ordre, ce qui rend le plan
    cohérent, ce qui pourrait le faire dérailler."""
    segment = request.args.get("segment", "Particuliers")
    try:
        d = _strat_get(segment)
    except Exception as e:
        return jsonify({"analyse": "", "source": "none", "error": str(e)}), 200
    rm = d.get("roadmap") or {}
    horizons = rm.get("horizons") or []
    if not horizons:
        return jsonify({"analyse": "", "source": "none"}), 200

    horizons_txt = "\n\n".join(
        f"{h.get('horizon')} — {h.get('theme')} :\n" +
        "\n".join(f"  - Acte : {a.get('acte')}\n    Résultat attendu : {a.get('resultat')}"
                   for a in (h.get("actes") or []))
        for h in horizons
    )
    obj = rm.get("objectif") or {}
    obj_txt = "\n".join(f"  - {l}" for l in (obj.get("lignes") or []))
    facts = f"{horizons_txt}\n\nCAP CONSOLIDÉ À 3 ANS ({obj.get('titre', '')}) :\n{obj_txt}"

    import hashlib as _hl6
    key = f"strat_roadmap_v1_{segment}_{_hl6.md5(facts.encode('utf-8')).hexdigest()[:10]}"
    cache = _strat_narr_cache()
    if cache.get(key):
        return jsonify({"analyse": cache[key], "source": "cache"})

    prompt = f"""Tu es analyste financier senior, plume du comité de direction de SGCI (banque, Côte d'Ivoire), segment {segment}.
Voici le plan d'action à 3 ans DÉJÀ DÉFINI (actes concrets, jamais à recalculer ni inventer) :

{facts}

Rédige une LECTURE STRATÉGIQUE de ce plan en 3 phrases denses, niveau comité de direction :
1. Explique LA LOGIQUE DE SÉQUENÇAGE : pourquoi l'An 1 doit précéder l'An 2 puis l'An 3 (quel acte précédent est la CONDITION du suivant) — pas une liste, une chaîne de causalité.
2. Identifie LE risque d'exécution le plus critique du plan (quel acte, s'il échoue ou prend du retard, fait dérailler le cap consolidé à 3 ans) et pourquoi celui-là précisément.
3. Termine par ce que le succès du plan change concrètement pour SGCI face à ses concurrents, ancré sur un chiffre du cap consolidé.
RÈGLES : recopie CHAQUE chiffre EXACTEMENT comme fourni. <b> sur les chiffres clés. Une phrase par ligne (point puis <br>). INTERDIT : « cela signifie que », « il est important de », toute généralité qui pourrait s'appliquer à n'importe quelle banque."""

    txt, engine = _rp_llm_json(prompt, max_tokens=900, temperature=0.2, prefer_claude=True)
    if not txt:
        return jsonify({"analyse": "", "source": "none"}), 200
    analyse = _llm_polish(_llm_br(txt.strip()))
    _invente = _chiffres_inventes(analyse, facts)
    if _invente:
        print(f"[strat_roadmap] REJETÉ (0 hallucination) — chiffres non fournis détectés : {_invente}")
        return jsonify({"analyse": "", "source": "none"}), 200
    cache[key] = analyse
    _mark_fresh(cache, key)
    try:
        with open(_STRAT_NARR_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[strat_roadmap] persist:", e)
    return jsonify({"analyse": analyse, "source": engine or "groq"})


def _analyse_llm_cached(ckey, prompt):
    """Analyse « portée métier » : LLM CONTRAINT (70b puis repli 8b-instant, rotation des 12 clés)
    PUIS STOCKÉE (cache persistant cb_analyses_cache.json). Réutilisé par PESTEL et VRIST."""
    if ckey in _LLM_CB_CACHE and _LLM_CB_CACHE.get(ckey):
        _meta = _get_meta(_LLM_CB_CACHE, ckey)
        return {"analyse": _trim_incomplete(_LLM_CB_CACHE[ckey]), "source": "cache",
                "generated_at": _meta.get("generated_at"), "stale": bool(_meta.get("stale"))}
    _ctxt = _claude_call(prompt, 1200, 0.4)
    if _ctxt:
        analyse = _trim_incomplete(_ctxt.strip())
        # GARDE-FOU (2026-07-22, « jamais d'hallucination ») : chiffre inventé → pas accepté,
        # on continue vers Groq comme si Claude avait échoué.
        if not _chiffres_inventes(analyse, prompt):
            _LLM_CB_CACHE[ckey] = analyse
            _mark_fresh(_LLM_CB_CACHE, ckey)
            try:
                _persist_cb_cache()
            except Exception:
                pass
            _meta = _get_meta(_LLM_CB_CACHE, ckey)
            return {"analyse": analyse, "source": "claude",
                    "generated_at": _meta.get("generated_at"), "stale": False}
    from groq import Groq as _Groq
    keys = [k for k in ([os.getenv("GROQ_API_KEY", "")]
                        + [os.getenv(f"GROQ_API_KEY_{i}", "") for i in range(2, 13)]) if k]
    analyse, src = "", None
    for _model in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
        for _key in keys:
            try:
                _resp = _Groq(api_key=_key, timeout=40, max_retries=0).chat.completions.create(
                    model=_model, messages=[{"role": "user", "content": prompt}],
                    max_tokens=800, temperature=0.4)
                _cand = _trim_incomplete((_resp.choices[0].message.content or "").strip())
                # GARDE-FOU (2026-07-22) : rejette un candidat avec un chiffre inventé, essaie la
                # clé/le modèle suivant plutôt que d'accepter un texte halluciné.
                if _cand and _chiffres_inventes(_cand, prompt):
                    continue
                analyse = _cand
                src = _model
                break
            except Exception:
                continue
        if analyse:
            break
    if analyse:
        _LLM_CB_CACHE[ckey] = analyse
        _mark_fresh(_LLM_CB_CACHE, ckey)
        try:
            _persist_cb_cache()
        except Exception:
            pass
        _meta = _get_meta(_LLM_CB_CACHE, ckey)
        return {"analyse": analyse, "source": src, "generated_at": _meta.get("generated_at"), "stale": False}
    else:
        # Échec LLM (quota/panne) → on garde la DERNIÈRE analyse connue (même préfixe hors hash)
        # plutôt que de renvoyer vide : jamais de régression visible pour l'utilisateur.
        prefix = ckey.rsplit("_", 1)[0] + "_"
        stale_key = next((k for k in _LLM_CB_CACHE if k != ckey and k.startswith(prefix) and not k.endswith("@meta") and _LLM_CB_CACHE[k]), None)
        if stale_key:
            _mark_stale_from(_LLM_CB_CACHE, ckey, stale_key)
            _meta = _get_meta(_LLM_CB_CACHE, ckey)
            return {"analyse": _trim_incomplete(_LLM_CB_CACHE[stale_key]), "source": "cache_stale",
                    "generated_at": _meta.get("generated_at"), "stale": True}
    return {"analyse": analyse, "source": src}


@app.route("/api/pestel_analyse")
def api_pestel_analyse():
    """Analyse de PORTÉE du PESTEL pour le MÉTIER — rédigée par le LLM (CONTRAINT aux faits sourcés)
    PUIS STOCKÉE (cache reproductible cb_analyses_cache.json). Explique, force par force, ce que
    l'environnement externe IMPLIQUE concrètement pour SGCI + la conclusion à retenir."""
    import hashlib as _hl
    segment = request.args.get("segment", "Particuliers")
    try:
        d = _strat_get(segment)
        _STRAT_CACHE[segment] = d
    except Exception as e:
        return jsonify({"analyse": "", "error": str(e)})
    axes = ((d.get("pestel") or {}).get("axes")) or []
    if not axes:
        return jsonify({"analyse": ""})
    # Dossier PESTEL → faits sourcés passés au LLM (sa SEULE matière → groundedness préservée).
    faits = "\n".join(
        f"- {a.get('nom')} : {a.get('resume')} — "
        + " ; ".join((p.get("txt") or "") for p in (a.get("points") or []))
        for a in axes)
    ckey = "pestel_portee_v2_" + _hl.md5(faits.encode("utf-8")).hexdigest()[:12]
    prompt = (
        "Tu es analyste stratégique de SGCI (1ʳᵉ banque de Côte d'Ivoire), plume du comité de direction. "
        "Voici l'analyse PESTEL — des FAITS externes SOURCÉS (ta SEULE matière, n'invente AUCUN chiffre) :\n"
        + faits + "\n\n"
        "Rédige une ANALYSE DE PORTÉE pour le MÉTIER (dirigeants SGCI).\n"
        "EXIGENCES DE STYLE (impératives) : français SOUTENU et élégant, verbes variés et justes, connecteurs "
        "soignés (toutefois, dès lors, à l'inverse, aussi). Chaque force reçoit DEUX à TROIS phrases COMPLÈTES et "
        "construites — JAMAIS une énumération de mots séparés par des virgules, JAMAIS une liste télégraphique. "
        "Chaque affirmation est ANCRÉE sur le chiffre clé du fait correspondant (cite-le). INTERDIT : « cela signifie "
        "que », « il est important de », « SGCI doit rester vigilante », toute conclusion creuse.\n"
        "Format markdown EXACT :\n"
        "## Portée stratégique du PESTEL\n"
        "**Politique →** puis 2-3 phrases rédigées (l'implication concrète pour SGCI — opportunité à saisir OU menace "
        "à gérer — puis la direction d'action, chiffre à l'appui).\n"
        "Puis, sur le même modèle et à la ligne : **Économique →** …, **Social →** …, **Technologique →** …, "
        "**Environnemental →** …, **Légal →** ….\n"
        "### Ce que le métier doit retenir\n"
        "3 phrases de synthèse : où se joue véritablement l'avenir de SGCI dans cet environnement, et la priorité n°1."
    )
    return jsonify(_analyse_llm_cached(ckey, prompt))


@app.route("/api/vrist_analyse")
def api_vrist_analyse():
    """Analyse de PORTÉE du VRIST pour le MÉTIER — LLM CONTRAINT aux scores VRIST de SGCI PUIS
    STOCKÉE. Explique, dimension par dimension, ce que l'avantage concurrentiel DURABLE implique."""
    import hashlib as _hl
    segment = request.args.get("segment", "Particuliers")
    try:
        d = _strat_get(segment)
        _STRAT_CACHE[segment] = d
    except Exception as e:
        return jsonify({"analyse": "", "error": str(e)})
    sg = (((d.get("vrist") or {}).get("banques") or {}).get("SGCI")) or {}
    dims = sg.get("dimensions") or []
    if not dims:
        return jsonify({"analyse": ""})
    faits = "\n".join(
        f"- {dim.get('nom')} : {dim.get('score')}/10 — "
        + " ; ".join((dr.get("txt") or "") for dr in (dim.get("drivers") or []))
        for dim in dims)
    faits += f"\nScore global : {sg.get('global')}/10. {sg.get('synthese','')}"
    ckey = "vrist_portee_v1_" + _hl.md5(faits.encode("utf-8")).hexdigest()[:12]
    prompt = (
        "Tu es analyste stratégique de SGCI (1ʳᵉ banque de Côte d'Ivoire). Voici son profil VRIST — "
        "l'avantage concurrentiel DURABLE noté /10, CALCULÉ et sourcé (ta SEULE matière, n'invente AUCUN chiffre) :\n"
        + faits + "\n\n"
        "Rédige une ANALYSE DE PORTÉE pour le MÉTIER (dirigeants SGCI), claire et actionnable.\n"
        "Format markdown EXACT :\n"
        "## Portée stratégique du VRIST\n"
        "Pour CHACUNE des 5 dimensions, une ligne : **Valeur →** [ce que le score implique pour SGCI : "
        "force à exploiter OU faiblesse à corriger, + la direction d'action], en citant le score. "
        "Puis **Rareté →** …, **Inimitable →** …, **Durable →** …, **Transformatif →** ….\n"
        "### Ce que le métier doit retenir\n"
        "2 à 3 phrases : l'avantage de SGCI est-il DURABLE, son maillon faible, et la priorité d'investissement."
    )
    return jsonify(_analyse_llm_cached(ckey, prompt))


# ══════════════════════════════════════════════════════════════════════════════
#  RÉSUMÉ PDF — rédigé par le LLM (jamais par nous), ancré sur les faits calculés,
#  caché par hash → le bouton « Télécharger PDF » télécharge CE résumé.
# ══════════════════════════════════════════════════════════════════════════════
_RESUME_CACHE_FILE = os.path.join(DOSSIER_CACHE, "dashboard_resume_cache.json")
_RESUME_CACHE = None


def _resume_cache():
    global _RESUME_CACHE
    if _RESUME_CACHE is None:
        try:
            with open(_RESUME_CACHE_FILE, encoding="utf-8") as f:
                _RESUME_CACHE = json.load(f)
        except Exception:
            _RESUME_CACHE = {}
    return _RESUME_CACHE


def _resume_facts_ef(segment):
    # kpis_vue_ensemble résout DÉJÀ l'année cible par banque (rn_anx) → chaque *_data
    # est un {banque: valeur} PLAT (pas de dimension année à re-résoudre ici).
    # Couvre TOUTES les dimensions du dashboard Santé Financière (pas seulement RN/ROE) :
    # résultat net, PNB, marge nette, coefficient, coût du risque, croissance, mix revenus.
    S = AGENTS["EF"].structured
    kp = S.kpis_vue_ensemble(strategie.CB_ANNEE, strategie.CB_SEM, segment, 3) or {}
    rn, roe, coeff, cr, growth, pnb, marge = (
        kp.get("rn_data") or {}, kp.get("roe_data") or {}, kp.get("coeff_expl_data") or {},
        kp.get("cout_r_pnb_data") or {}, kp.get("growths_data") or {},
        kp.get("pnb_data") or {}, kp.get("marge_nette_data") or {})
    inte, comm = kp.get("interets_data") or {}, kp.get("commissions_data") or {}
    def _fmt_m(v):
        # Sépare les milliers à la française (« 101 352,0 ») — sinon le LLM reformate au hasard
        # (parfois avec l'espace, parfois sans), incohérence visible d'un résumé à l'autre.
        return f"{v:,.1f}".replace(",", " ").replace(".", ",") if isinstance(v, (int, float)) else v
    rows = []
    for b in sorted(rn, key=lambda x: -(rn.get(x) or 0)):
        mix = None
        if inte.get(b) and comm.get(b):
            tot = inte[b] + comm[b]
            mix = round(comm[b] / tot * 100) if tot else None
        rows.append(f"  {b}: RN {_fmt_m(rn.get(b))} · PNB {_fmt_m(pnb.get(b))} · ROE {roe.get(b)}% · marge nette {marge.get(b)}% · "
                    f"coefficient {coeff.get(b)}% · coût du risque {cr.get(b)}% · croissance {growth.get(b)}%"
                    + (f" · mix commissions {mix}%" if mix is not None else ""))
    podium = sorted(rn.items(), key=lambda x: -(x[1] or 0))[:3]
    podium_txt = ", ".join(f"{b} ({_fmt_m(v)})" for b, v in podium if v is not None)
    return (f"SANTÉ FINANCIÈRE — segment {segment}, dernier exercice (dashboard complet : résultat net, PNB, "
            f"ROE, marge nette, coefficient d'exploitation, coût du risque, croissance, mix revenus).\n"
            f"Rang SGCI en résultat net : #{kp.get('sgci_rang_rn')}. Part de marché : {kp.get('sgci_part_marche')}%.\n"
            f"Podium résultat net : {podium_txt}.\n"
            "Détail par banque (toutes les métriques du dashboard) :\n" + "\n".join(rows))


def _resume_facts_cb(segment):
    # Couvre TOUTES les sections du dashboard Conditions bancaires : catalogue, prix (win-rate),
    # exclusivités (Q3) et manques/gaps (Q5) — pas seulement le catalogue et le prix.
    CB = AGENTS["CB"].structured
    q6 = CB.cb_analyse_q6(strategie.CB_ANNEE, strategie.CB_SEM, segment) or []
    cmp = CB.cb_prix_competitivite(strategie.CB_ANNEE, strategie.CB_SEM, segment) or {}
    bycat = sorted([r for r in q6 if (r.get("n_services") or 0) > 0], key=lambda r: -(r.get("n_services") or 0))
    rang_cat = next((i + 1 for i, r in enumerate(bycat) if r["banque"] == "SGCI"), None)
    sgci_q6 = next((r for r in q6 if r["banque"] == "SGCI"), {})
    classes = cmp.get("classes") or []
    rows_cat = "\n".join(f"  #{i+1} {r['banque']}: {r.get('n_services')} services, {r.get('pct_gratuit')}% gratuits"
                          for i, r in enumerate(bycat))
    rows_prix = "\n".join(f"  #{i+1} {c['banque']}: win-rate {c['winrate']}% (sur {c['n']} services comparables)"
                           for i, c in enumerate(classes))
    try:
        excl = CB.cb_analyse_q3(strategie.CB_ANNEE, strategie.CB_SEM, segment) or []
    except Exception:
        excl = []
    n_excl = sum(1 for r in excl if r.get("verdict") in ("differenciant", "non_contredit"))
    try:
        gaps = CB.cb_analyse_q5(strategie.CB_ANNEE, strategie.CB_SEM, segment) or []
    except Exception:
        gaps = []
    gaps_reels = [g for g in gaps if (g.get("nb_banques") or 0) >= 3]
    # PAS d'exemple isolé injecté ici (« ex. X ») — juste le chiffre. Un exemple arbitraire
    # (le premier trouvé, pas forcément le plus pertinent) ne fait qu'ajouter du bruit au résumé
    # (retour utilisateur : « comme le service pour... / dont le rejet de chèque... c'est pas utile »).
    return (f"CONDITIONS BANCAIRES — segment {segment}, {strategie.CB_ANNEE} {strategie.CB_SEM} (dashboard complet : "
            f"catalogue, positionnement prix, exclusivités, manques face à la concurrence).\n"
            f"SGCI : catalogue #{rang_cat}/{len(bycat)} ({sgci_q6.get('n_services')} services, "
            f"{sgci_q6.get('pct_gratuit')}% gratuits) ; prix #{cmp.get('rang_sgci')} en win-rate "
            f"({(cmp.get('sgci') or {}).get('winrate')}%).\n"
            f"Exclusivités confirmées de SGCI : {n_excl}.\n"
            f"Manques de SGCI face à ≥3 concurrents : {len(gaps_reels)}.\n"
            f"Classement catalogue :\n{rows_cat}\nClassement prix (win-rate) :\n{rows_prix}")


def _resume_facts_strategie(segment):
    # Couvre TOUTES les sections du dashboard Stratégie : diagnostic, SWOT, Porter, VRIST,
    # révélations, plan 3 ans, projection à 3 scénarios — pas seulement diagnostic + 1 force/
    # faiblesse. 2026-07-24 : la Projection (section ⑧, la plus travaillée) manquait entièrement
    # du PDF — demande explicite du directeur (« le PDF doit être cohérent avec le dashboard »).
    d = _strat_get(segment)
    probs = (d.get("problemes") or [])[:5]
    diag_f = "\n".join(f"  - [{p.get('gravite')}] {p.get('titre')}" for p in probs)
    sw = d.get("swot") or {}
    sw_f = "\n".join(f"  {q.upper()}: " + " | ".join(str(it.get('txt'))[:100] for it in (sw.get(q) or [])[:2])
                      for q in ("forces", "faiblesses", "opportunites", "menaces") if sw.get(q))
    porter = ((d.get("porter") or {}).get("forces")) or []
    porter_f = "\n".join(f"  {f.get('force')}: intensité {f.get('intensite')}" for f in porter)
    vr = ((d.get("vrist") or {}).get("banques") or {}).get("SGCI") or {}
    vr_f = " · ".join(f"{x.get('nom') or x.get('cle')} {x.get('score')}/10" for x in (vr.get("dimensions") or []))
    revs = (d.get("revelations") or [])[:4]
    rev_f = "\n".join(f"  - {r.get('titre')}" for r in revs)
    pl = d.get("roadmap") or {}
    plan_f = "\n".join(f"  - {h.get('horizon')}: {h.get('theme')}" for h in (pl.get("horizons") or []))

    ph = d.get("projection_hypotheses") or {}
    proj_f = "\n".join(
        f"  - {s.get('nom')} ({s.get('pct_effet')}% de l'effet du plan, {s.get('certitude_pct')}% de "
        f"certitude) : {s.get('formulation')}"
        for s in (ph.get("scenarios") or [])
    )
    proj_metrics = d.get("projection") or []
    metr_f = "\n".join(
        f"  - {p.get('nom')} : {p.get('depart')} aujourd'hui → {p.get('central_an3')} à 3 ans "
        f"(scénario central), fourchette {p.get('fourchette_an3')}"
        for p in proj_metrics
    )
    concl = _re_rp.sub(r"<[^>]+>", "", ph.get("conclusion_strategique") or "")

    return (f"STRATÉGIE — segment {segment} (dashboard complet : diagnostic, SWOT, forces de Porter, "
            f"profil VRIST, révélations, plan d'action 3 ans, projection à 3 scénarios).\n"
            f"Problèmes prioritaires :\n{diag_f}\n\n"
            f"SWOT :\n{sw_f}\n\n"
            f"Forces de Porter (intensité concurrentielle) :\n{porter_f}\n\n"
            f"Profil VRIST de SGCI (avantage concurrentiel /10) : {vr_f}\n\n"
            f"Révélations clés :\n{rev_f}\n\n"
            f"Plan 3 ans :\n{plan_f}\n\n"
            f"Projection 3 ans — 3 scénarios (même plan, niveaux d'exécution différents) :\n{proj_f}\n\n"
            f"Métriques projetées à 3 ans :\n{metr_f}\n\n"
            f"Conclusion stratégique de la projection : {concl}")


def _pdf_plaintext(s):
    """Nettoyage TEXTE BRUT pour le résumé PDF (jsPDF dessine du texte, PAS du HTML) : contrairement
    aux autres endpoints LLM de l'app, ici un <br> ou <b> qui fuit s'affiche LITTÉRALEMENT dans le
    PDF. On applique le polish habituel PUIS on retire toute trace de balise et les artefacts de
    ponctuation double (« 17,0%,. » → « 17,0%. »)."""
    t = _llm_polish(s)
    if not t:
        return t
    t = _re_rp.sub(r"</?(?:br|b|i|em|strong)\s*/?>", " ", t, flags=_re_rp.I)
    t = _re_rp.sub(r"\s{2,}", " ", t).strip()
    t = _re_rp.sub(r",\s*([.!?])", r"\1", t)   # « ,. » ou « , . » → « . »
    t = _re_rp.sub(r"([.!?]){2,}", r"\1", t)   # ponctuation dupliquée
    return _trim_incomplete(t)   # jamais de phrase coupée en plein mot (max_tokens atteint)


@app.route("/api/dashboard_resume")
def api_dashboard_resume():
    """Résumé de dashboard RÉDIGÉ PAR LE LLM (jamais nous) — ancré sur les faits calculés,
    mis en cache par hash (évolutif). Consommé par le bouton « Télécharger PDF »."""
    import hashlib as _hlr
    section = (request.args.get("section") or "ef").lower()
    segment = request.args.get("segment", "Particuliers")
    try:
        if section == "cb":
            facts = _resume_facts_cb(segment)
            titre_dash = "Conditions bancaires"
        elif section == "strategie":
            facts = _resume_facts_strategie(segment)
            titre_dash = "Stratégie"
        else:
            facts = _resume_facts_ef(segment)
            titre_dash = "Santé financière"
    except Exception as e:
        return jsonify({"resume": None, "error": str(e)}), 200

    cache = _resume_cache()
    key = f"resume_v8_{section}_{segment}_{_hlr.md5(facts.encode('utf-8')).hexdigest()[:12]}"
    if cache.get(key):
        return jsonify({"resume": cache[key], "source": "cache"})

    prompt = f"""Tu es analyste senior de SGCI (1ʳᵉ banque de Côte d'Ivoire), plume du comité de direction.
Voici les faits RÉELS calculés (ta SEULE matière — n'invente AUCUN chiffre) pour le dashboard « {titre_dash} » :

{facts}

Rédige un RÉSUMÉ EXÉCUTIF destiné à un document PDF pour la direction. Il doit couvrir L'ENSEMBLE
DES SECTIONS listées ci-dessus (ne te limite pas à une seule dimension) — c'est un résumé COMPLET
du dashboard, pas un focus partiel. Français SOUTENU et élégant, phrases complètes et construites,
verbes variés (bannis la répétition de « SGCI doit » en tête de plusieurs points).
INTERDIT : « cela signifie que », « il est important de », « doit analyser ces résultats »,
« doit améliorer son offre/sa position » en fin de paragraphe sans action précise, toute
conclusion creuse ou générique qui ne s'appuie sur aucun chiffre. INTERDIT ABSOLU : toute balise
HTML (<br>, <b>, etc.) — ce texte va dans un PDF en TEXTE BRUT, sépare tes phrases par un simple
point, jamais par une balise. Les grands nombres sont DÉJÀ formatés dans les faits ci-dessus
(espace tous les 3 chiffres, virgule décimale) — RECOPIE-les à l'identique, ne les reformate pas.
INTERDIT AUSSI : accrocher un exemple isolé et arbitraire en fin de phrase avec « comme… » ou
« dont… » (ex. « 8 exclusivités, comme le service X » ou « 10 manques, dont le rejet de chèque »)
— cite le CHIFFRE seul, sans exemple d'illustration, sauf si CET exemple précis est explicitement
le sujet de la phrase (pas une simple parenthèse décorative).
RÈGLE CAPITALE — @@executif@@ et @@points@@ ONT DES RÔLES DIFFÉRENTS, NE LES CONFONDS PAS :
- @@points@@ = le détail chiffré, section par section (la liste) — RANGS et CHIFFRES EXACTS y vont.
- @@executif@@ = une VRAIE SYNTHÈSE DE HAUT NIVEAU, PAS un résumé phrase-par-phrase des points.
  C'est le SEUL paragraphe qu'un dirigeant pressé lira — il doit dégager LE FIL NARRATIF qui relie
  les sections (une cause probable, une tension entre deux constats, la place de SGCI dans son
  ensemble). N'énumère JAMAIS les mêmes rangs/chiffres/comptes que ceux détaillés dans @@points@@.
INTERDICTION STRICTE ET CONCRÈTE (erreurs déjà commises à ne PAS répéter) :
  - N'utilise JAMAIS dans @@executif@@ un RANG (« 4ème », « 5ème position »…) ou un COMPTE
    (« 10 manques », « 8 exclusivités »…) qui apparaît TEL QUEL dans @@points@@ — reformule en
    jugement QUALITATIF sans le chiffre exact (ex. « catalogue en retrait sur le marché », « des
    manques significatifs face à la concurrence »), jamais le nombre répété.
  - INTERDIT toute phrase generic qui s'appliquerait à N'IMPORTE QUELLE banque sans changer un mot
    (ex. « SGCI doit faire face à des défis importants », « SGCI doit renforcer son offre ») — si tu
    ne peux pas y accrocher un fait SPÉCIFIQUE à SGCI, ne l'écris pas.
  - INTERDIT de commenter la donnée elle-même (ex. « n'est pas fourni dans son intégralité », « les
    données sont incomplètes ») — n'utilise QUE ce qui est fourni, sans méta-commentaire dessus.
  Cette synthèse doit être IRRÉPROCHABLE : dense, sans une phrase de trop, chaque mot utile.

Réponds EXACTEMENT avec ces marqueurs :
@@titre@@
… (titre du rapport, 4 à 8 mots, sans point final)
@@executif@@
… (SYNTHÈSE DE HAUT NIVEAU en 3 à 4 phrases — le constat d'ensemble et l'enjeu principal, PAS une
liste de faits redondants avec @@points@@. Termine sur le fait le plus significatif, jamais un vœu pieux)
@@points@@
… (6 à 8 points clés, UN PAR LIGNE commençant par « - », chacun un chiffre réel DIFFÉRENT à l'appui
(deux points ne portent JAMAIS le même chiffre) — couvre CHAQUE section listée ci-dessus, pas
seulement la première ; chaque point est un FAIT CHIFFRÉ, jamais une recommandation ou un point sans
chiffre propre (interdit : « SGCI doit renforcer son offre » — un point sans chiffre n'a pas sa place ici))
@@analyse@@
… (analyse en 3 à 5 phrases : le POURQUOI derrière les chiffres, ce qui les relie)
@@conclusion@@
… (2 phrases : la priorité n°1 à retenir, chiffrée et actionnable — pas « doit améliorer X »)
FORMAT : marqueurs @@clé@@ (PAS de JSON)."""
    txt, engine = _rp_llm_json(prompt, max_tokens=1900, temperature=0.3)
    parsed = {}
    if txt:
        segs = _re_rp.split(r"@@\s*([a-zA-Z0-9_]+)\s*@@", txt)
        valid = {"titre", "executif", "points", "analyse", "conclusion"}
        for i in range(1, len(segs) - 1, 2):
            kk, vv = segs[i].strip(), segs[i + 1].strip().strip("`").strip()
            if kk in valid and vv and not vv.startswith("…"):
                parsed[kk] = _pdf_plaintext(vv) if kk != "points" else vv
    if not parsed.get("executif"):
        # Échec LLM (quota/panne) → sert le DERNIER résumé connu pour cette section/segment
        # (même préfixe hors hash) plutôt que rien — le PDF reste toujours téléchargeable.
        _prefix = key.rsplit("_", 1)[0] + "_"
        _stale_key = next((k for k in cache if k != key and k.startswith(_prefix) and not k.endswith("@meta") and cache[k]), None)
        if _stale_key:
            _mark_stale_from(cache, key, _stale_key)
            _meta = _get_meta(cache, key)
            return jsonify({"resume": cache[_stale_key], "source": "cache_stale",
                             "generated_at": _meta.get("generated_at"), "stale": True})
        return jsonify({"resume": None, "source": "none"}), 200
    parsed["points"] = [_pdf_plaintext(p.lstrip("-• ").strip()) for p in (parsed.get("points") or "").split("\n") if p.strip()]
    parsed["section"] = titre_dash
    parsed["segment"] = segment
    cache[key] = parsed
    _mark_fresh(cache, key)
    try:
        with open(_RESUME_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[dashboard_resume] persist:", e)
    _meta = _get_meta(cache, key)
    return jsonify({"resume": parsed, "source": engine or "groq",
                     "generated_at": _meta.get("generated_at"), "stale": False})


_STRAT_NARR_CACHE = None
_STRAT_NARR_FILE = os.path.join(DOSSIER_CACHE, "strategie_narr_cache.json")


def _strat_narr_cache():
    global _STRAT_NARR_CACHE
    if _STRAT_NARR_CACHE is None:
        try:
            with open(_STRAT_NARR_FILE, encoding="utf-8") as f:
                _STRAT_NARR_CACHE = json.load(f)
        except Exception:
            _STRAT_NARR_CACHE = {}
    return _STRAT_NARR_CACHE


@app.route("/api/strategie_narr")
def api_strategie_narr():
    """« L'essentiel » (verdict + 3 points + surveiller) RÉDIGÉ PAR LE LLM, ancré sur les faits
    calculés par strategie.build() → phrasé 100% dynamique et soutenu, zéro hallucination (contraint
    aux chiffres). Caché & reproductible ; le déterministe reste en fallback côté front."""
    segment = request.args.get("segment", "Particuliers")
    anx     = int(request.args.get("anx", 3))
    cache = _strat_narr_cache()
    # Faits calculés DIRECTEMENT depuis l'agent EF (rapide, indépendant du lourd strategie.build()).
    S = AGENTS["EF"].structured
    try:
        kp  = S.kpis_vue_ensemble(2026, "S1", segment, anx) or {}
        cnr = S.ef_cnr_series() or {}
    except Exception as e:
        return jsonify({"narr": {}, "source": "none", "error": str(e)}), 200

    def _rk(m, lb=False):
        m = {b: v for b, v in (m or {}).items() if v is not None}
        if "SGCI" not in m:
            return "?"
        order = sorted(m.items(), key=lambda x: (x[1] if lb else -x[1]))
        return [b for b, _ in order].index("SGCI") + 1

    rn = kp.get("rn_data") or {}
    n = len(rn) or 7
    crp = {b: v for b, v in (kp.get("cout_r_pnb_data") or {}).items() if v is not None}   # coût du risque / PNB (%)
    sg_cr = crp.get("SGCI")
    r_cr = _rk(crp, lb=True)
    best_cr = min(crp.items(), key=lambda x: x[1]) if crp else (None, None)
    meds = sorted(crp.values())
    med_cr = meds[len(meds) // 2] if meds else None
    pnb_sg = (kp.get("pnb_data") or {}).get("SGCI") or 0
    gain = round(pnb_sg * ((sg_cr - med_cr) / 100) / 1000) if (sg_cr and med_cr and sg_cr > med_cr) else None
    # Tendance du coût du risque : première vs dernière année à valeur réelle (série pb).
    sgy = sorted(y for y, v in (cnr.get("SGCI") or {}).items() if v)
    hausse = len(sgy) >= 2 and cnr["SGCI"][sgy[-1]] > cnr["SGCI"][sgy[0]]

    facts = (
        f"FAITS (secteur bancaire ivoirien, {n} banques ; chiffres RÉELS) :\n"
        f"- Résultat net : SGCI #{kp.get('sgci_rang_rn')}/{n} ; {kp.get('sgci_part_marche')}% des bénéfices ; avance sur le #2 ({kp.get('banque_2_nom')}) : {kp.get('ecart_pct_vs_2')}%\n"
        f"- Coefficient d'exploitation : SGCI #{_rk(kp.get('coeff_expl_data'), lb=True)}/{n} (bas = mieux → parmi les mieux gérées)\n"
        f"- Marge nette : SGCI #{_rk(kp.get('marge_nette_data'))}/{n} ; ROE : SGCI #{_rk(kp.get('roe_data'))}/{n}\n"
        f"- Coût du risque (% du PNB) : SGCI {round(sg_cr, 1) if sg_cr else '?'}%, #{r_cr}/{n} (bas = mieux → le PIRE du marché), {'en HAUSSE continue' if hausse else 'stable'} ; médiane {round(med_cr, 1) if med_cr else '?'}% ; meilleur {best_cr[0]} ({round(best_cr[1], 1) if best_cr[1] else '?'}%)\n"
        f"- Croissance du résultat net : SGCI #{_rk(kp.get('growths_data'))}/{n} (la plus lente) ; le plus rapide : {kp.get('fastest_b')} (+{round(kp.get('fastest_pct') or 0)}%)\n"
        + (f"- Gain de résultat net si le coût du risque revenait à la médiane du marché : ≈ +{gain} Mds FCFA/an\n" if gain else "")
    )
    # ÉVOLUTIF : la clé de cache dépend du HASH DES FAITS → de nouvelles données (banque, année,
    # chiffres) changent les faits → nouvelle clé → régénération AUTOMATIQUE, sans intervention.
    import hashlib as _hl2
    key = f"narr_v3_{segment}_{_hl2.md5(facts.encode('utf-8')).hexdigest()[:10]}"
    if cache.get(key):
        return jsonify({"narr": cache[key], "source": "cache"})
    prompt = f"""Tu es analyste financier senior du secteur bancaire ivoirien. Voici les faits RÉELS sur SGCI (Société Générale Côte d'Ivoire) :

{facts}
Rédige « L'essentiel » de la stratégie, en 5 blocs, dans un français SOUTENU, précis et clair (pour le comité de direction), SANS jargon obscur, chaque affirmation ANCRÉE sur un chiffre ci-dessus (n'invente AUCUN nombre) :
- verdict : 2 à 3 phrases — le message d'ensemble : SGCI domine en volume et figure parmi les mieux gérées, mais son coût du risque (le pire) et sa croissance lente la freinent ; maîtriser ce seul risque suffirait à la hisser au premier rang de la rentabilité.
- bien : 1 phrase chiffrée — ce qui va bien (rangs favorables : résultat net, coefficient).
- probleme : 1 à 2 phrases chiffrées — LE vrai problème : le coût du risque, le pire du marché, sa trajectoire.
- faire : 1 à 2 phrases chiffrées — l'action prioritaire (mieux sélectionner et suivre le risque de crédit) et le gain estimé.
- surveiller : 1 phrase — le concurrent le plus rapide et pourquoi le surveiller.

RÈGLES : registre soutenu (verbes variés, connecteurs élégants). PHRASES COURTES ET DISTINCTES, séparées par des POINTS puis « <br> » (une phrase par ligne) — BANNIS les phrases à rallonge qui enchaînent « toutefois … dès lors que … en revanche … » en une seule phrase interminable ; coupe en 2-3 phrases nettes. <b> autour des chiffres clés. INTERDIT « cela signifie que » (même au milieu d'une phrase), « il est important de », « doit améliorer son efficacité », les fins vagues (« cette situation impacte négativement la rentabilité », « cela pourrait indiquer des opportunités »).

FORMAT (marqueurs, PAS de JSON, PAS de guillemets) :
@@verdict@@
…
@@bien@@
…
@@probleme@@
…
@@faire@@
…
@@surveiller@@
…"""
    txt, engine = _rp_llm_json(prompt, max_tokens=2500, temperature=0.35, prefer_claude=True)
    parsed = {}
    if txt:
        segs = _re_rp.split(r"@@\s*([a-zA-Z_]+)\s*@@", txt)
        for i in range(1, len(segs) - 1, 2):
            kk = segs[i].strip()
            vv = segs[i + 1].strip().strip("`").strip()
            if kk in ("verdict", "bien", "probleme", "faire", "surveiller") and vv:
                parsed[kk] = _llm_polish(_llm_br(vv))
    if not parsed:
        # Échec LLM (quota/panne) → garde la DERNIÈRE version connue (même préfixe hors hash)
        # plutôt que de renvoyer vide : jamais de perte d'analyse déjà validée.
        _prefix = key.rsplit("_", 1)[0] + "_"
        _stale_key = next((k for k in cache if k != key and k.startswith(_prefix) and not k.endswith("@meta") and cache[k]), None)
        if _stale_key:
            _mark_stale_from(cache, key, _stale_key)
            _meta = _get_meta(cache, key)
            return jsonify({"narr": cache[_stale_key], "source": "cache_stale",
                             "generated_at": _meta.get("generated_at"), "stale": True})
        return jsonify({"narr": {}, "source": "none"}), 200
    cache[key] = parsed
    _mark_fresh(cache, key)
    try:
        with open(_STRAT_NARR_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[strat_narr] persist:", e)
    _meta = _get_meta(cache, key)
    return jsonify({"narr": parsed, "source": engine or "groq",
                     "generated_at": _meta.get("generated_at"), "stale": False})


@app.route("/api/strategie_narr2")
def api_strategie_narr2():
    """LECTURES STRATÉGIQUES rédigées par le LLM pour chaque section (diagnostic, SWOT, Porter,
    VRIST, plan) + le RÉCIT de chaque révélation — ancrées sur les faits calculés par
    strategie.build() (zéro hallucination). ÉVOLUTIF : clé de cache = hash des faits → toute
    nouvelle donnée régénère automatiquement. 1 appel LLM, format à marqueurs, caché."""
    import hashlib as _hl2
    segment = request.args.get("segment", "Particuliers")
    try:
        d = _strat_get(segment)
    except Exception as e:
        return jsonify({"narr": {}, "source": "none", "error": str(e)}), 200

    # ── Digest de FAITS par section (compact, 100% dérivé des données) ──
    probs = (d.get("problemes") or [])[:8]
    diag_f = "\n".join(f"  - [gravité {p.get('gravite')}] {p.get('titre')} — {str(p.get('preuve'))[:160]}" for p in probs)
    sw = d.get("swot") or {}
    sw_f = "\n".join(f"  {q.upper()}: " + " | ".join(str(it.get('txt'))[:110] for it in (sw.get(q) or [])[:4])
                     for q in ("forces", "faiblesses", "opportunites", "menaces"))
    po = (d.get("porter") or {}).get("forces") or []
    po_f = "\n".join(f"  - {f.get('force')} : intensité {f.get('intensite')} — {str(f.get('resume'))[:110]}" for f in po)
    vr = ((d.get("vrist") or {}).get("banques") or {}).get("SGCI") or {}
    vr_f = " · ".join(f"{x.get('nom') or x.get('cle')} ({x.get('cle')}) : {x.get('score')}/10" for x in (vr.get("dimensions") or []))
    pl = d.get("plan_action") or d.get("roadmap") or {}
    _hz = pl.get("horizons") if isinstance(pl, dict) else pl          # dict {horizons,objectif} OU liste directe
    pl_f = "\n".join(f"  - {h.get('horizon') or h.get('titre') or ''} ({h.get('sous_titre') or ''}) : {h.get('theme') or h.get('objectif') or ''}"
                     for h in (_hz or []) if isinstance(h, dict))
    _obj = pl.get("objectif") if isinstance(pl, dict) else ""
    revs = (d.get("revelations") or [])[:8]
    # 2026-07-17 (demande explicite du directeur) : NE PLUS donner la phrase déjà écrite comme
    # texte « à reformuler » (le LLM ne faisait alors que la paraphraser légèrement, d'où des
    # titres/textes quasi identiques à chaque régénération) — donner UNIQUEMENT les faits BRUTS
    # (les puces déjà validées, jamais de texte pré-rédigé) et laisser Claude construire lui-même
    # l'angle et la formulation, comme une vraie découverte, pas une relecture.
    rev_f = "\n".join(
        f"  rev_{i} [type: {r.get('type')}] :\n"
        f"      faits bruts (base TON analyse UNIQUEMENT là-dessus, n'invente aucun autre chiffre) : "
        + " ; ".join(str(x)[:100] for x in (r.get('preuves') or []) if x)
        for i, r in enumerate(revs))

    facts = (f"DIAGNOSTIC (problèmes détectés, gravité 3=max):\n{diag_f}\n\n"
             f"SWOT:\n{sw_f}\n\n"
             f"PORTER (5 forces):\n{po_f}\n\n"
             f"VRIST SGCI (scores /10): {vr_f} ; exclusivités confirmées: {(d.get('vrist') or {}).get('n_exclusivites')}\n\n"
             f"PLAN 3 ANS:\n{pl_f}\nObjectif: {str(_obj)[:200]}\n\n"
             f"RÉVÉLATIONS (faits croisés):\n{rev_f}")

    cache = _strat_narr_cache()
    key = f"narr2_v6_{segment}_{_hl2.md5(facts.encode('utf-8')).hexdigest()[:10]}"
    if cache.get(key):
        return jsonify({"narr": cache[key], "source": "cache"})

    rev_marks = "\n".join(f"@@rev_{i}@@\n… (« En clair » de rev_{i} : 2 phrases CONSTRUITES par toi à partir des faits bruts ci-dessus — le fait marquant que TU identifies + ce qu'il implique pour SGCI)" for i in range(len(revs)))
    rev_detail_marks = "\n".join(f"@@rev_detail_{i}@@\n… (« Détail chiffré » de rev_{i} : 3 à 4 phrases de prose analytique SOUTENUE, CONSTRUITES par toi à partir des faits bruts de rev_{i} — pas une paraphrase d'un texte existant, une VRAIE analyse qui explique le mécanisme et la portée pour SGCI, en réutilisant chaque chiffre fourni)" for i in range(len(revs)))
    prompt = f"""Tu es analyste financier senior du secteur bancaire ivoirien, plume du comité de direction de SGCI. Voici les faits RÉELS (calculés sur les données internes) :

{facts}

Rédige les LECTURES STRATÉGIQUES suivantes. EXIGENCES : français SOUTENU et élégant (verbes variés, connecteurs soignés), analyses PERTINENTES qui hiérarchisent et relient les faits (pas des paraphrases), chaque affirmation ancrée sur un fait ci-dessus (n'invente AUCUN chiffre). PHRASES COURTES, une par ligne (point puis « <br> »). <b> sur les chiffres. INTERDIT : « cela signifie que », « il est important de », conclusions creuses (« doit améliorer son efficacité »).
- @@diag@@ : 3 phrases — hiérarchise les problèmes (le plus grave d'abord), montre le FIL qui les relie, et ce qui n'est PAS un problème.
- @@swot@@ : 3 phrases — la force majeure, la faiblesse critique, et LA décision que cette matrice impose.
- @@porter@@ : 2 phrases — où la pression concurrentielle est maximale et l'implication pour SGCI.
- @@vrist@@ : 2 phrases — l'avantage le plus durable de SGCI et son maillon faible (scores à l'appui).
- @@plan@@ : 2 phrases — la logique d'ensemble An 1 → An 3 (pourquoi cet ordre) et ce qui conditionne la réussite.
{rev_marks}
{rev_detail_marks}

FORMAT : marqueurs @@clé@@ (PAS de JSON)."""
    # 2026-07-17 : séparé en DEUX appels (au lieu d'un seul mega-prompt) — constaté empiriquement
    # que le bloc combiné s'arrêtait TOUJOURS juste après rev_6, avant les rev_detail_*, même à
    # 18000 tokens (donc pas une simple coupure par manque de budget). Un second appel dédié,
    # plus court, dégage sans ambiguïté le budget nécessaire aux « Détail chiffré » (plus longs).
    txt, engine = _rp_llm_json(prompt, max_tokens=8000, temperature=0.35, prefer_claude=True)
    parsed = {}
    if txt:
        segs = _re_rp.split(r"@@\s*([a-zA-Z0-9_]+)\s*@@", txt)
        valid = ({"diag", "swot", "porter", "vrist", "plan"}
                 | {f"rev_{i}" for i in range(len(revs))})
        for i in range(1, len(segs) - 1, 2):
            kk, vv = segs[i].strip(), segs[i + 1].strip().strip("`").strip()
            if kk in valid and vv and not vv.startswith("…"):
                parsed[kk] = _llm_polish(_llm_br(vv))

    detail_marks = "\n".join(f"@@rev_detail_{i}@@\n… (rev_{i})" for i in range(len(revs)))
    detail_prompt = f"""Tu es analyste financier senior du secteur bancaire ivoirien, plume du comité de direction de SGCI.
Voici les faits BRUTS de {len(revs)} révélations déjà repérées (chiffres exacts, à conserver à l'identique — n'en invente AUCUN) :

{rev_f}

Pour CHACUNE, rédige un « Détail chiffré » de 3 à 4 phrases de prose analytique SOUTENUE et élégante (verbes variés,
connecteurs soignés), CONSTRUITES par toi à partir des faits bruts — pas une paraphrase, une VRAIE analyse qui
explique le mécanisme et la portée pour SGCI, en réutilisant chaque chiffre fourni EXACTEMENT (décimale et % inclus).
PHRASES COURTES, une par ligne (point puis « <br> »). <b> sur les chiffres. INTERDIT : « cela signifie que », « il
est important de », conclusions creuses.

Réponds avec CHAQUE marqueur ci-dessous :
{detail_marks}

FORMAT : marqueurs @@clé@@ (PAS de JSON)."""
    dtxt, dengine = _rp_llm_json(detail_prompt, max_tokens=8000, temperature=0.35, prefer_claude=True)
    if dtxt:
        dsegs = _re_rp.split(r"@@\s*([a-zA-Z0-9_]+)\s*@@", dtxt)
        dvalid = {f"rev_detail_{i}" for i in range(len(revs))}
        for i in range(1, len(dsegs) - 1, 2):
            kk, vv = dsegs[i].strip(), dsegs[i + 1].strip().strip("`").strip()
            if kk in dvalid and vv and not vv.startswith("…"):
                parsed[kk] = _llm_polish(_llm_br(vv))
        if not engine:
            engine = dengine

    if not parsed:
        _prefix = key.rsplit("_", 1)[0] + "_"
        _stale_key = next((k for k in cache if k != key and k.startswith(_prefix) and not k.endswith("@meta") and cache[k]), None)
        if _stale_key:
            _mark_stale_from(cache, key, _stale_key)
            _meta = _get_meta(cache, key)
            return jsonify({"narr": cache[_stale_key], "source": "cache_stale",
                             "generated_at": _meta.get("generated_at"), "stale": True})
        return jsonify({"narr": {}, "source": "none"}), 200
    cache[key] = parsed
    _mark_fresh(cache, key)
    try:
        with open(_STRAT_NARR_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[strat_narr2] persist:", e)
    _meta = _get_meta(cache, key)
    return jsonify({"narr": parsed, "source": engine or "groq",
                     "generated_at": _meta.get("generated_at"), "stale": False})


@app.route("/api/strategie_narr3")
def api_strategie_narr3():
    """REFORMULATION LLM de la couche STRUCTURELLE encore écrite « à la main » : puces SWOT,
    résumés Porter (punchlines), thèmes du plan-trajectoire, titres/actions des révélations.
    Le texte déterministe (avec ses vrais chiffres) devient la MATIÈRE que le LLM reformule en
    prose soutenue — CONSERVE les chiffres à l'identique, n'en invente AUCUN. ÉVOLUTIF : clé de
    cache = hash des faits → toute nouvelle donnée régénère automatiquement. 1 appel, caché."""
    import hashlib as _hl3
    segment = request.args.get("segment", "Particuliers")
    try:
        d = _strat_get(segment)
    except Exception as e:
        return jsonify({"narr": {}, "source": "none", "error": str(e)}), 200

    sw = d.get("swot") or {}
    swot_items = []   # (marker, texte_source)
    for qk, items in (("forces", sw.get("forces")), ("faiblesses", sw.get("faiblesses")),
                       ("opportunites", sw.get("opportunites")), ("menaces", sw.get("menaces"))):
        for i, it in enumerate((items or [])[:5]):
            swot_items.append((f"swot_{qk}_{i}", str(it.get("txt") or "")[:200]))
    swot_f = "\n".join(f"  @@{m}@@ : {t}" for m, t in swot_items)

    forces_p = ((d.get("porter") or {}).get("forces")) or []
    porter_items = [(f"porter_{f.get('cle')}", str(f.get("resume") or "")[:150]) for f in forces_p if f.get("cle")]
    porter_f = "\n".join(f"  @@{m}@@ : {t}" for m, t in porter_items)

    horizons = ((d.get("roadmap") or {}).get("horizons")) or []
    plan_items = [(f"plan_theme_{i}", str(h.get("theme") or "")[:150]) for i, h in enumerate(horizons[:3])]
    plan_f = "\n".join(f"  @@{m}@@ : {t}" for m, t in plan_items)

    # 2026-07-17 (demande explicite) : rev_titre_*/rev_action_* ne reçoivent PLUS le texte déjà
    # écrit à reformuler (ça ne faisait que le paraphraser, quasi identique à chaque régénération)
    # — seulement les faits bruts (preuves déjà validées) + le type, pour une VRAIE construction.
    revs = (d.get("revelations") or [])[:8]
    rev_items = []      # (marker, longueur_cible) — pas de texte source, juste un repère de format
    rev_raw_f = []
    for i, r in enumerate(revs):
        rev_items.append((f"rev_titre_{i}", ""))
        preuves_txt = " ; ".join(str(x)[:100] for x in (r.get("preuves") or []) if x)
        rev_raw_f.append(f"  rev_{i} [type: {r.get('type')}] : {preuves_txt}")
        if r.get("action"):
            rev_items.append((f"rev_action_{i}", ""))
    rev_raw = "\n".join(rev_raw_f)

    all_items = swot_items + porter_items + plan_items + rev_items
    if not all_items:
        return jsonify({"narr": {}, "source": "none"}), 200

    facts = (f"PUCES SWOT (matière factuelle, à reformuler une par une) :\n{swot_f}\n\n"
             f"RÉSUMÉS PORTER (punchlines courtes des 5 forces concurrentielles) :\n{porter_f}\n\n"
             f"THÈMES DU PLAN 3 ANS (titre de chaque horizon) :\n{plan_f}\n\n"
             f"FAITS BRUTS DES RÉVÉLATIONS (construis rev_titre_i et rev_action_i UNIQUEMENT à partir de ceci, "
             f"n'invente aucun autre chiffre) :\n{rev_raw}")

    cache = _strat_narr_cache()
    key = f"narr3_v6_{segment}_{_hl3.md5(facts.encode('utf-8')).hexdigest()[:10]}"
    if cache.get(key):
        return jsonify({"narr": cache[key], "source": "cache"})

    swot_porter_plan_marks = "\n".join(f"@@{m}@@\n… (reformulation de @@{m}@@)" for m, _ in (swot_items + porter_items + plan_items))
    rev_marks = "\n".join(
        f"@@rev_titre_{i}@@\n… (titre CONSTRUIT à partir des faits bruts de rev_{i})\n"
        + (f"@@rev_action_{i}@@\n… (action CONSTRUITE à partir des faits bruts de rev_{i})\n" if r.get("action") else "")
        for i, r in enumerate(revs))
    prompt = f"""Tu es la plume du comité de direction de SGCI (1ʳᵉ banque de Côte d'Ivoire). Voici des éléments de
texte, chacun accompagné de sa MATIÈRE FACTUELLE réelle (chiffres exacts, à conserver à l'identique — n'en invente
AUCUN) :

{facts}

CONSIGNE GÉNÉRALE : français SOUTENU et élégant (verbes justes, pas de tournure plate), chiffres EXACTS jamais inventés.
- swot_* : REFORMULE la puce SWOT fournie en UNE phrase, même sens, même longueur.
- porter_* : REFORMULE le résumé fourni en UNE punchline TRÈS COURTE (5 à 9 mots).
- plan_theme_* : REFORMULE le thème fourni en UN titre percutant (5 à 9 mots), pas de point final.
- rev_titre_* : PAS de texte à reformuler ici — CONSTRUIS toi-même, à partir des « faits bruts » de la révélation correspondante, UN titre court et frappant (4 à 8 mots, pas de point final) qui capture l'angle le plus marquant de CES chiffres précis.
- rev_action_* : PAS de texte à reformuler ici — CONSTRUIS toi-même, à partir des mêmes faits bruts, UNE phrase d'action impérative et concrète, ancrée sur au moins un chiffre.
INTERDIT : « cela signifie que », « il est important de », toute banalité vide. <b> autour des chiffres clés.
RÈGLE ABSOLUE SUR LES CHIFFRES : recopie CHAQUE nombre EXACTEMENT comme il apparaît dans la matière factuelle —
décimale ET symbole % inclus (« 13,9% » reste « 13,9% », JAMAIS « 13% » ni « 13»). Ne jamais arrondir, tronquer
ou retirer une décimale.

Réponds avec CHAQUE marqueur ci-dessous :
{swot_porter_plan_marks}
{rev_marks}

FORMAT : marqueurs @@clé@@ (PAS de JSON)."""
    txt, engine = _rp_llm_json(prompt, max_tokens=14000, temperature=0.3, prefer_claude=True)
    parsed = {}
    if txt:
        segs = _re_rp.split(r"@@\s*([a-zA-Z0-9_]+)\s*@@", txt)
        src_map = dict(all_items)
        valid = set(src_map)
        for i in range(1, len(segs) - 1, 2):
            kk, vv = segs[i].strip(), segs[i + 1].strip().strip("`").strip().rstrip(".")
            if kk not in valid or not vv or vv.startswith("…"):
                continue
            # Garde-fou anti-troncature : chaque nombre à décimale de la source (point OU virgule —
            # les faits Python utilisent le point) DOIT réapparaître dans la reformulation, sinon on
            # rejette la clé (le front garde alors le texte déterministe, jamais un chiffre dégradé).
            src_nums = _re_rp.findall(r"\d+[.,]\d+", src_map.get(kk, ""))
            vv_norm = vv.replace(",", ".")
            if src_nums and not all(n.replace(",", ".") in vv_norm for n in src_nums):
                continue
            parsed[kk] = _llm_polish(vv)
    if not parsed:
        _prefix = key.rsplit("_", 1)[0] + "_"
        _stale_key = next((k for k in cache if k != key and k.startswith(_prefix) and not k.endswith("@meta") and cache[k]), None)
        if _stale_key:
            _mark_stale_from(cache, key, _stale_key)
            _meta = _get_meta(cache, key)
            return jsonify({"narr": cache[_stale_key], "source": "cache_stale",
                             "generated_at": _meta.get("generated_at"), "stale": True})
        return jsonify({"narr": {}, "source": "none"}), 200
    cache[key] = parsed
    _mark_fresh(cache, key)
    try:
        with open(_STRAT_NARR_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[strat_narr3] persist:", e)
    _meta = _get_meta(cache, key)
    return jsonify({"narr": parsed, "source": engine or "groq",
                     "generated_at": _meta.get("generated_at"), "stale": False})


@app.route("/api/strategie_llm")
def api_strategie_llm():
    """VISION CRÉATIVE du Comité de Direction (IA générative CONTRAINTE).
    Le LLM reçoit TOUT le dossier de preuves (chiffres réels, déjà sourcés) et produit
    une vision audacieuse et créative — MAIS interdiction d'inventer un chiffre.
    Créativité = température élevée ; groundedness = il ne connaît que le dossier.
    Si le LLM est indisponible, la carte est simplement masquée côté front (fallback)."""
    import hashlib as _hl
    segment = request.args.get("segment", "Particuliers")
    try:
        d = _strat_get(segment)
        _STRAT_CACHE[segment] = d
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    dossier = strategie.dossier_pour_llm(d)
    # UN APPEL PAR DIRECTEUR (focalisé) → beaucoup plus de propositions, de façon fiable.
    _DIRECTEURS = [
        ("💰", "Directeur Financier",
         "AMÉLIORER LA QUALITÉ DU PORTEFEUILLE DE CRÉDIT (coût du risque 17% du PNB = le PIRE du marché). Tes leviers : MIEUX "
         "SÉLECTIONNER le risque EN AMONT et le COUVRIR — par des GARANTIES concrètes et NOMMÉES (hypothèque sur l'actif financé, "
         "nantissement de matériel/stock/créances, caution solidaire, domiciliation OBLIGATOIRE du salaire/des flux, assurance-crédit), "
         "un suivi rapproché des dossiers fragiles, et le recouvrement. Pour CHAQUE action, explique le MÉCANISME (en quoi ça réduit "
         "concrètement les impayés). "
         "INTERDIT ABSOLU : décréter un SEUIL DE SCORING chiffré (ex. « 700 ») ou un TAUX d'intérêt précis (ex. « 8% » / « 12% ») — "
         "c'est la POLITIQUE INTERNE de SGCI, PAS à l'IA de la fixer ; donne la DIRECTION (« moduler la tarification du risque », "
         "« exiger plus de garanties sur les segments fragiles »), JAMAIS le chiffre. "
         "INTERDIT (autres directions) : compte/épargne mobile, fidélité, parrainage, agence digitale, mobile money, conseil/relation "
         "client, marketing, changement de TARIF de service, « formation du personnel », « transparence », « sécurité »."),
        ("🤝", "Directeur Commercial",
         "MONÉTISER LES SERVICES SANS CASSER L'AVANTAGE CLIENT (tu es le SEUL à toucher un prix) + virage ENTREPRISES + cross-sell. "
         "MÉTHODE OBLIGATOIRE (modèle DG « Repricing & Valeur Digitale ») — dans cet ordre de préférence : "
         "(a) TARIFICATION DIFFÉRENCIÉE : rendre un service GRATUIT sur le canal DIGITAL (appli) et PAYANT en AGENCE au niveau du marché "
         "→ on capte la marge en réduisant le COÛT de délivrance, SANS augmenter le prix perçu par le client ; "
         "(b) FACTURER des services aujourd'hui GRATUITS chez SGCI mais tarifés ailleurs (nouvelles lignes de commissions, cite le service) ; "
         "(c) hausse TRÈS MODÉRÉE (+1 000 à +3 000 F MAX) UNIQUEMENT sur un acte administratif rare que le client NE COMPARE PAS — JAMAIS doubler un prix. "
         "INTERDIT (= contresens stratégique) : BAISSER un prix élevé qui est une BARRIÈRE DE SORTIE VOULUE (attestation de non redevance, "
         "levée d'opposition, frais de clôture/transfert → ils freinent le départ du client, on les GARDE chers) ; MONTER à la médiane un "
         "prix où SGCI est DÉJÀ moins chère et s'en sert pour ACQUÉRIR (ça tue le « pourquoi venir chez SGCI »). "
         "Tout repricing est ACCOMPAGNÉ d'un gain d'expérience (sinon attrition). "
         "INTERDIT (autres) : compte/épargne mobile, scoring, agence digitale, campagne marketing."),
        ("📣", "Directeur Marketing",
         "ACQUISITION par la COMMUNICATION des FORCES EXISTANTES. Tes MUNITIONS sont dans le dossier (sections CB) : la liste des "
         "services où SGCI est DÉJÀ MOINS CHÈRE que le marché, ses TAUX compétitifs, ses EXCLUSIVITÉS, sa marque de leader, la "
         "diaspora, l'inclusion. Construis CHAQUE proposition autour d'UN de ces éléments NOMMÉS pour viser une cible précise "
         "(jeunes, diaspora, PME, salariés…). "
         "Ton TITRE est une ACTION de communication/acquisition CIBLÉE (campagne, offre packagée, argumentaire pour un segment), "
         "JAMAIS un montant ni un taux comme titre (❌ « Frais de dossier à 6 000 F », « Taux débiteur 6% » ; "
         "✅ « Campagne ‘SGCI la moins chère’ sur le crédit conso auprès des salariés », « Offre diaspora packagée autour du PACK DIASPORA »). "
         "Tu CITES le prix/taux/exclusivité comme PREUVE dans le corps de l'acte. "
         "INTERDIT (= ÉCHEC) : coût du risque / crédit / octroi / scoring (c'est le Financier) ; créer un produit ou compte / "
         "épargne mobile (c'est l'Innovation) ; fixer ou modifier un TARIF (c'est le Commercial) ; tout titre VAGUE "
         "(« compétitivité », « services exclusifs », « optimisation »). Ton *Constat* parle de PRIX/ACQUISITION."),
        ("🚀", "Directeur Innovation",
         "NOUVEAUX PRODUITS / DIGITAL. Tes MUNITIONS dans le dossier : la liste des MANQUES (services qu'ont ≥3 concurrents, pas "
         "SGCI — à combler) et les INNOVATIONS concurrentes NOMMÉES (agence digitale ECOBANK, néobanque « Simple », épargne mobile "
         "Orange — à copier-dépasser). Construis CHAQUE proposition autour d'UN manque précis OU d'UNE innovation nommée. "
         "INTERDIT : scoring, tarifs, fidélité, formation, relation client, et tout produit déjà dans les exclusivités SGCI. "
         "EXIGE : cite QUI le fait déjà (fait web) + le texte BCEAO qui l'autorise [REGL: …] et CE qu'il dit. Ton *Constat* parle d'OFFRE/digital."),
    ]
    # ── Découpe le dossier en SECTIONS (# HEADER) → chaque directeur ne reçoit que SA tranche
    #    pertinente (≈ ÷4 tokens → tient dans le quota Groq/minute + périmètre plus net).
    _SEC, _cur = {}, None
    for _ln in dossier.split("\n"):
        if _ln.startswith("# "):
            _cur = _ln[2:].strip(); _SEC[_cur] = [_ln]
        elif _cur is not None:
            _SEC[_cur].append(_ln)
    _SEC = {k: "\n".join(v).strip() for k, v in _SEC.items()}
    def _slice(prefixes):
        return "\n\n".join(v for k, v in _SEC.items() if any(k.startswith(p) for p in prefixes))
    # Cadres stratégiques TRANSVERSAUX (compacts) → donnés à TOUS les directeurs pour que
    # chaque décision SYNTHÉTISE toutes les sections (demande explicite). Les grosses données
    # métier (CHIFFRES/CONDITIONS/INNOVATIONS) restent routées par domaine pour garder le focus.
    _COMMON = ["DIAGNOSTIC", "SWOT", "PORTER", "PESTEL", "VRIST", "RÉVÉLATIONS", "CONSIGNE"]
    _SLICES = {
        "Financier":  ["SITUATION", "CHIFFRES", "SEGMENT"] + _COMMON,
        "Commercial": ["SITUATION", "CONDITIONS", "SEGMENT"] + _COMMON,
        "Marketing":  ["SITUATION", "CONDITIONS", "CHIFFRES", "FAITS WEB"] + _COMMON,
        "Innovation": ["SITUATION", "CONDITIONS", "INNOVATIONS", "FAITS WEB"] + _COMMON,
    }

    _RULES = f"""PHILOSOPHIE (validée par la DG — « Repricing & Valeur Digitale ») :
• L'écart de COMMISSIONS est le signal le plus actionnable : tarifer ce qui a de la VALEUR, pas refondre le bilan.
• Le DIGITAL est un OUTIL DE MARGE : réduire le COÛT de délivrance capture de la rentabilité SANS hausser le prix perçu.
• Tout repricing est ACCOMPAGNÉ : sans amélioration perçue du service → attrition ; couplé à une meilleure expérience → fidélisation.

RÈGLES (éliminatoires) :
1. Propose EXACTEMENT 4 recommandations — ni plus, ni moins — les 4 PLUS PERTINENTES et ACTIONNABLES de ton domaine, classées de la
   plus forte à la moins forte. Ne rends JAMAIS une section vide : il y a TOUJOURS de la matière dans TON domaine (creuse le dossier).
   Chacune tranchante. Ton *Constat* porte sur TON domaine.
2. INTERDIT ABSOLU (banalités que SGCI fait DÉJÀ) : « formation du personnel », « améliorer la relation client / la
   transparence / la sécurité », « mettre en place un système / comité / processus », « campagne de sensibilisation »,
   « programme de fidélité » générique, « diversifier » sans dire QUOI. Si tu écris ça, tu as échoué.
3. CHAQUE acte est ANCRÉ sur un CHIFFRE PRÉCIS du dossier (un service NOMMÉ + son prix, un écart chiffré, un fait web
   daté, un % EF). Pas d'ancrage chiffré → supprime l'acte. INTERDIT : EMPILER/additionner plusieurs montants de services
   SANS RAPPORT (ex. « frais de dossier 6 000 + levée d'opposition 5 500 + tenue 2 350 ») pour fabriquer un faux « pack »
   ou une pseudo-économie — un acte = UN service nommé + SON prix réel ; on ne mélange pas des lignes hétérogènes.
4. RESPECTE ton périmètre et ta liste INTERDIT — ne propose JAMAIS le sujet d'un autre directeur, même bonne idée.
5. PRIX (Commercial uniquement) :
   • PRÉFÈRE la tarification DIFFÉRENCIÉE (gratuit digital / payant agence) et la FACTURATION de services non encore facturés,
     PLUTÔT que de monter un tarif existant.
   • COMPRENDS l'intention d'un prix : un prix ÉLEVÉ peut être une BARRIÈRE DE SORTIE voulue (attestation de non redevance,
     levée d'opposition, clôture/transfert) → NE PAS baisser ; un prix BAS est souvent une ARME d'acquisition → NE PAS monter à la médiane.
   • Hausse autorisée : sur un acte administratif rare que le client ne compare pas. JAMAIS doubler.
   • OBLIGATOIRE pour toute HAUSSE : cite la MÉDIANE marché du service (présente dans le dossier) et montre que le NOUVEAU prix
     reste ≤ à cette médiane → preuve qu'on récupère du revenu SANS devenir plus cher que la concurrence. Si la hausse dépasserait
     la médiane, NE la propose PAS. Format : « passer X de [prix actuel] à [nouveau prix], soit encore SOUS la médiane marché [médiane] ».
   • Reprends le service et ses prix EXACTEMENT du dossier ; n'invente AUCUN montant.
6. POLITIQUE INTERNE — ne décrète JAMAIS un chiffre qui relève de SGCI : seuil de scoring, taux d'intérêt, taux de provision,
   commission précise non observée. Donne la DIRECTION, pas le nombre. (Les prix CB observés dans le dossier, eux, se citent.)
7. PROFONDEUR (niveau 5) : ne t'arrête pas à l'intention. Si tu dis « garanties » → ÉNUMÈRE lesquelles ; « accompagnement » → dis
   COMMENT ; « segment risqué » → lequel. Explique toujours le MÉCANISME (en quoi l'action produit le résultat). Termine chaque
   reco par son IMPACT estimé (levier : marge d'intérêt / commissions / coût du risque) ET le réalisme opérationnel
   (ex. pilote sur quelques agences → généralisation, direction porteuse).
8. RÉGLEMENTATION : [REGL: nom exact] + résume EN UNE PHRASE ce que dit le texte. Tout fait WEB porte sa source.
   Ne JAMAIS opposer « coût du risque (%PNB) » et « marge nette ». Sources autorisées : [EF] [CB] [REGL] [WEB].
9. NIVEAU DE LANGUE SOUTENU (obligatoire) : rédige dans un français professionnel et élégant de comité de direction — phrases bien construites, verbes variés et justes, connecteurs soignés (toutefois, néanmoins, dès lors, à l'inverse), ponctuation précise. BANNIS le registre courant et les tournures plates (« est #1 », « ce qui est inférieur à celui de certains de ses concurrents », deux « mais » qui se suivent, « il est important de »). Reste NÉANMOINS clair et sans jargon obscur.

RÈGLE TITRE (déterminante) : le titre 💡 est une ACTION CONCRÈTE qui NOMME un instrument de TON périmètre, JAMAIS une catégorie.
  Forme : [VERBE d'action] + [service / garantie / canal PRÉCIS tiré de TON dossier] + [cible ou condition].
  ❌ catégories vagues : « Amélioration de… », « Optimisation des… », « Renforcement du… », « Tarification différenciée des services » (trop générique).
  ✅ un instrument NOMMÉ du dossier + un chiffre du dossier.
  TEST : si le titre pourrait coller à N'IMPORTE QUELLE banque, OU au périmètre d'un AUTRE directeur, il est mauvais → réécris-le.
  ⚠️ Tu n'as AUCUN libellé à recopier : CHAQUE reco part d'un élément RÉEL et DIFFÉRENT de TON dossier, dans TON SEUL périmètre.

FORMAT markdown STRICT (squelette à REMPLIR avec TES données — n'imite que la STRUCTURE, pas un contenu) :
## ICON NOM
*Constat :* [1 phrase chiffrée de TON domaine]
- 💡 **[action + instrument précis]** _(Segment)_ — [but en une phrase].
▸ **[Acte 1 concret]** — [développé AVEC un chiffre exact du dossier].
▸ **[Acte 2 = accompagnement / mécanisme]** — [COMMENT l'action produit le résultat].
→ Pourquoi : [fait chiffré] [SOURCE]. Impact estimé : [marge d'intérêt / commissions / coût du risque].

⛔ ÉCHECS AUTOMATIQUES (la reco est rejetée) : reprendre un libellé/sujet d'un AUTRE directeur ; sortir de ton périmètre ;
   doubler un prix ; BAISSER une barrière de sortie (attestation de non redevance, levée d'opposition) ; décréter un seuil de
   scoring ou un taux d'intérêt ; titre vague (« Optimisation », « Renforcer la compétitivité »)."""

    import time as _t
    base_key = f"strat_creatif_v27_{segment}_{_hl.md5(dossier.encode('utf-8')).hexdigest()[:10]}"
    # Prépare un job par directeur (prompt focalisé sur sa tranche).
    _jobs = []
    for icon, nom, perim in _DIRECTEURS:
        _short = nom.split()[-1]
        _dsl = _slice(_SLICES.get(_short, ["SITUATION", "CONDITIONS"]))
        p = (f"Tu es le {nom} de SGCI, 1ʳᵉ banque de Côte d'Ivoire — audacieux, créatif et CONCRET. "
             f"Ton périmètre exclusif : {perim}.\n\n"
             f"DOSSIER (ta tranche — chiffres 100% RÉELS, ta SEULE source de vérité) :\n{_dsl}\n\n{_RULES}"
             .replace("ICON NOM", f"{icon} {nom}"))
        _jobs.append((icon, nom, f"{base_key}_{_short[:4]}", p))

    def _gen_one(icon, nom, ckey, p):
        r = _groq_call_cb(p, ckey, max_tokens=1800, temperature=0.45, prefer_claude=True)
        a = (r.get("analyse") or "").strip()
        if a and not a.lstrip().startswith("##"):
            a = f"## {icon} {nom}\n" + a
        return a, (r.get("source") not in ("cache", None))

    results = {}
    _made = 0
    for icon, nom, ckey, p in _jobs:
        if _made > 0 and ckey not in _LLM_CB_CACHE:
            _t.sleep(8)   # espace les vrais appels (limite tokens/minute Groq)
        a, called = _gen_one(icon, nom, ckey, p)
        if a:
            results[ckey] = a
        if called:
            _made += 1
    # AUTO-RÉPARATION : les directeurs manquants (429 tokens/minute) sont retentés après reset TPM,
    # dans le MÊME appel → l'endpoint garantit les 4 directeurs sans passes manuelles. Caché ensuite.
    _missing = [(icon, nom, ckey, p) for icon, nom, ckey, p in _jobs if ckey not in results]
    if _missing:
        _t.sleep(65)   # fenêtre TPM Groq = 60 s → on attend qu'elle se réinitialise
        for _i, (icon, nom, ckey, p) in enumerate(_missing):
            if _i > 0:
                _t.sleep(12)
            a, _ = _gen_one(icon, nom, ckey, p)
            if a:
                results[ckey] = a
    parts = [results[ckey] for icon, nom, ckey, p in _jobs if ckey in results]   # ordre des directeurs préservé
    # Directeur(s) dont l'IA a échoué même après la nouvelle tentative (65 s) : leur volet est
    # absent du texte final. Signalé au frontend (au lieu de disparaître silencieusement),
    # même trou que celui déjà corrigé sur CB (stale/estimation jamais remonté au frontend).
    missing_noms = [nom for icon, nom, ckey, p in _jobs if ckey not in results]
    txt = "\n\n".join(parts)
    src = "groq" if parts else "fallback"
    if not txt:
        return jsonify({"analyse": "", "source": "fallback", "missing_directeurs": missing_noms})
    import re as _re
    # NETTOYAGE : le modèle recopie parfois mes RÈGLES internes dans sa sortie → on les retire.
    txt = _re.sub(r"\s*⛔[^\n]*", "", txt)                    # bloc « ⛔ ÉCHECS AUTOMATIQUES … »
    txt = "\n".join(ln for ln in txt.split("\n") if not _re.search(
        r"(?i)reprendre un libell|sortir de ton p[ée]rim|barri[èe]re de sortie\s*\(attestation|"
        r"d[ée]cr[ée]ter un seuil|la reco est rejet|titre vague\s*\(|ÉCHECS AUTOMATIQUES", ln))
    # GARDE-FOU déterministe : supprimer les puces « buzzword » creuses qui auraient glissé
    _BUZZ = _re.compile(r"(?i)blockchain|m[ée]tavers|\biot\b|internet of things|r[ée]alit[ée] augment|chatbot|big data|nft\b")
    txt = "\n".join(ln for ln in txt.split("\n")
                    if not (_re.match(r"^\s*[-•]", ln) and _BUZZ.search(ln)))
    # ANTI-RÉPÉTITION déterministe : un même THÈME ne peut apparaître que chez UN seul directeur
    _THEMES = {
        "compte mobile":  ("100% mobile", "compte mobile", "compte 100%", "néobanque", "neobanque"),
        "épargne mobile": ("épargne mobile", "épargne auto", "micro-épargne", "épargne automat", "épargne digit"),
        "scoring":        ("scoring", "sélection de crédit", "sélection des emprunteurs", "octroi"),
        "fidélité":       ("fidélit", "parrainage", "fidélisation"),
        "agence digitale":("agence digitale", "agence numérique"),
        "paiement mobile":("mobile money", "passerelle mobile", "service de paiement", "services de paiement"),
        "conseil":        ("service de conseil", "conseil à valeur", "relation client"),
        "transparence":   ("transparence",),
        "sécurité":       ("sécurité",),
    }
    import unicodedata as _ud
    def _norm_title(t):
        t = _ud.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
        return " ".join(_re.findall(r"[a-z0-9]+", t)[:6])     # signature = 6 premiers mots
    # BANALITÉS interdites en TITRE (le modèle les glisse malgré le prompt) → bloc rejeté
    _BANAL = _re.compile(r"(?i)\bformation\b|sensibilisation|gestion de (leurs |ses )?dossiers|"
                         r"relation client|am[ée]lioration de la (relation|transparence|comp[ée]titivit[ée]|rentabilit[ée])|"
                         r"\boptimisation\b|renforcer la comp[ée]titivit|mise en place d'un (syst[èe]me|comit[ée]|processus)")
    # BUG TROUVÉ le 2026-07-22 (audit qualité, demande directeur « 0 hallucination, garantir la
    # qualité même quand ça évolue ») : le thème était détecté sur la LIGNE ENTIÈRE (titre +
    # description après le tiret), pas seulement le TITRE — un mot anodin dans la DESCRIPTION d'un
    # acte (ex. « ...pas seulement à l'octroi ») pouvait déclencher un faux doublon de thème et
    # supprimer TOUT le bloc suivant, silencieusement (un directeur se retrouvait avec 3 actions
    # au lieu de 4, sans aucune alerte). Fix : ne détecter le thème QUE dans le TITRE (`titre`),
    # jamais dans le reste de la ligne — la description reste libre d'expliquer le mécanisme sans
    # risquer de faire disparaître le bloc qui la contient.
    _seen, _seen_titles, _kept, _skip = set(), set(), [], False
    _dir_counts = {}
    _cur_dir = None
    for ln in txt.split("\n"):
        if ln.startswith("## "):
            _skip = False; _cur_dir = ln; _dir_counts[_cur_dir] = 0; _kept.append(ln); continue
        if _re.match(r"^\s*-\s*💡", ln):
            mt = _re.search(r"💡\s*\*\*(.+?)\*\*", ln)
            titre = mt.group(1) if mt else ""
            titre_low = titre.lower()
            tsig = _norm_title(titre) if titre else ""
            th = next((t for t, kws in _THEMES.items() if any(k in titre_low for k in kws)), None)
            # doublon inter-directeur (thème OU libellé, dans le TITRE seulement) OU titre BANAL
            if (th and th in _seen) or (tsig and tsig in _seen_titles) or (titre and _BANAL.search(titre)):
                _skip = True; continue
            _skip = False
            if th:
                _seen.add(th)
            if tsig:
                _seen_titles.add(tsig)
            if _cur_dir:
                _dir_counts[_cur_dir] += 1
            _kept.append(ln); continue
        if _skip:
            continue
        _kept.append(ln)
    txt = "\n".join(_kept)
    # ALERTE (visible dans les logs, plus jamais silencieuse) : un directeur avec < 4 actions après
    # filtrage signale soit un doublon de thème trop agressif, soit un échec de génération partiel.
    for _d, _n in _dir_counts.items():
        if _n < 4:
            print(f"[strategie_llm] ATTENTION — {_d.strip()} n'a que {_n}/4 actions après filtrage anti-doublon.")
    # VÉRIFICATION : chaque chiffre généré doit exister dans le dossier (anti-hallucination)
    try:
        verif = strategie.verifier_chiffres(txt, dossier)
    except Exception:
        verif = None
    return jsonify({"analyse": txt, "source": src, "verif": verif, "missing_directeurs": missing_noms})


@app.route("/api/cb_evolutions_all")
def api_cb_evolutions_all():
    """Évolution sémantique (nApp/nDis/net) pour toutes les banques.

    MIS EN CACHE EN BASE (2026-08-10). Annoncé « lent ~13s » ; mesuré à 48,7 SECONDES sur le
    service hébergé, où chaque requête traverse le réseau. C'est le plus long appel restant de
    l'application, et il alimente le panneau « Évolution sur 3 ans » que le directeur voyait
    échouer. Le calcul ne dépend que de la base : à données inchangées, il est identique.
    """
    segment = request.args.get("segment", "Particuliers")
    cle = f"cb_evolutions_all:{segment}"
    garde = _cache_lire(cle)
    if garde is not None:
        return jsonify(garde)
    try:
        data = AGENTS["CB"].structured.cb_all_evolutions_summary(segment)
        _cache_ecrire(cle, data)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyse_strategique")
def api_analyse_strategique():
    """
    Analyses stratégiques CB — 6 questions management.
    Exécute le SQL, formate les données, appelle Groq pour synthèse intelligente.
    """
    from groq import Groq as _Groq

    q_id     = int(request.args.get("q", 1))
    annee    = int(request.args.get("annee", 2026))
    semestre = request.args.get("semestre", "S1")
    segment  = request.args.get("segment", "Particuliers")

    if q_id not in _QUESTIONS_STRATEGIQUES(annee, semestre):
        return jsonify({"error": "q invalide (1-6)"}), 400

    # ── 1. Récupérer les données SQL ─────────────────────────────────────
    try:
        if   q_id == 1: data = AGENTS["CB"].structured.cb_analyse_q1(segment)
        elif q_id == 2: data = AGENTS["CB"].structured.cb_analyse_q2(annee, semestre, segment)
        elif q_id in (3, 4): data = AGENTS["CB"].structured.cb_analyse_q3(annee, semestre, segment)
        elif q_id == 5: data = AGENTS["CB"].structured.cb_analyse_q5(annee, semestre, segment)
        elif q_id == 6: data = AGENTS["CB"].structured.cb_analyse_q6(annee, semestre, segment)
    except Exception as e:
        return jsonify({"error": f"Erreur SQL : {e}"}), 500

    # ── 2. Formater en texte structuré ───────────────────────────────────
    ctx      = _fmt_strategic_ctx(q_id, data, annee, semestre, segment)
    question = _QUESTIONS_STRATEGIQUES(annee, semestre)[q_id]

    _banks_list = ", ".join(db.BANKS) if db.BANKS else "SGCI, BACI, BICICI, BNI, ECOBANK, NSIA, SIB"
    SYSTEM = (
        "Tu es un analyste stratégique senior spécialisé en banque de détail (marché ivoirien, BCEAO/UEMOA). "
        f"Tu analyses les conditions tarifaires de {len(db.BANKS) or 7} banques : {_banks_list}. "
        "SGCI est la banque de référence. "
        "Règles : utilise UNIQUEMENT les données fournies — jamais tes connaissances générales. "
        "Chiffres exacts, conclusions directes, format markdown structuré. "
        "Commence par les faits clés, pas par un préambule. "
        "Langue : français."
    )
    user_msg = (
        f"QUESTION : {question}\n\n"
        f"SEGMENT : {segment} | PÉRIODE : {semestre} {annee}\n\n"
        f"DONNÉES :\n{ctx}\n\n"
        "Génère une analyse SYNTHÉTIQUE et actionnelle. "
        "Organise-la par AXE BCEAO pertinent (Packages & Comptes, Cartes Bancaires, "
        "Produits d'Épargne, Crédits & Financements, Assurances, Services Digitaux & Paiements, "
        "Services aux Marchés Financiers, Autres) — uniquement les axes qui ressortent des données. "
        "Pour chaque axe : 1 à 2 phrases maximum (constat chiffré + implication SGCI). "
        "Termine par 3 recommandations prioritaires en gras. "
        "PAS DE REMPLISSAGE — 350 mots maximum, va à l'essentiel."
    )

    # ── 3. Appel Groq avec rotation des clés ────────────────────────────
    groq_keys = [k for k in [
        os.getenv("GROQ_API_KEY_11", ""), os.getenv("GROQ_API_KEY_12", ""),
        os.getenv("GROQ_API_KEY_9",  ""), os.getenv("GROQ_API_KEY_10", ""),
        os.getenv("GROQ_API_KEY_8", ""), os.getenv("GROQ_API_KEY_6", ""),
        os.getenv("GROQ_API_KEY_7", ""), os.getenv("GROQ_API_KEY_5", ""),
        os.getenv("GROQ_API_KEY",   ""), os.getenv("GROQ_API_KEY_2", ""),
        os.getenv("GROQ_API_KEY_3", ""), os.getenv("GROQ_API_KEY_4", ""),
    ] if k]

    last_err = None
    for key in groq_keys:
        try:
            client = _Groq(api_key=key)
            resp   = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user",   "content": user_msg},
                ],
                temperature=0.3,
                max_tokens=2048,
            )
            answer = _trim_incomplete(resp.choices[0].message.content.strip())
            return jsonify({
                "question": question,
                "reponse":  answer,
                "source":   "analyse_strategique",
                "q_id":     q_id,
                "n_lignes": len(data),
            })
        except Exception as e:
            last_err = str(e)
            continue

    # Fallback : données brutes si Groq indisponible
    return jsonify({
        "question":      question,
        "reponse":       f"[IA indisponible — {last_err}] Données brutes retournées.",
        "source":        "offline",
        "donnees_brutes": data,
    })


# ── LLM CB : cache persistant fichier + rotation robuste ─────────────────────
_CB_CACHE_FILE = os.path.join(DOSSIER_CACHE, "cb_analyses_cache.json")
_LLM_CB_CACHE: dict = {}

# Instruction standard ajoutée à chaque prompt : bold markdown + question stratégique
_BOLD_INSTR = (
    "\nFormat : utilise **gras** pour les chiffres clés, les écarts importants et tes conclusions. "
    "Inclus obligatoirement une question stratégique ou de réflexion pour SGCI (phrase terminant par ?). "
    "Niveau d'analyse EXIGÉ (comité de direction, pas un résumé) : ne te contente jamais d'un seul chiffre isolé — "
    "relie-le à sa CONSÉQUENCE concrète pour SGCI (perte/gain de clientèle, marge, risque réglementaire) et, si "
    "les données le permettent, à sa TENDANCE (une banque moins chère aujourd'hui mais qui monte vite, ou l'inverse) "
    "plutôt qu'une photo figée. Bannis les généralités qui pourraient s'appliquer à n'importe quelle banque. "
    "EXIGENCE DE PROFONDEUR (2026-07-16, aller au-delà des attentes) : ne te limite pas à décrire le chiffre "
    "affiché — si d'autres faits te sont donnés dans ce prompt (prix d'autres services, rangs, autres banques), "
    "CROISE-en au moins deux pour révéler un angle qui ne saute pas aux yeux (ex. un service moins cher ET "
    "un autre plus cher chez la même banque, une hausse cohérente ou non avec une autre décision récente). "
    "Termine sur une implication concrète et chiffrée, jamais une généralité du type « SGCI doit rester attentive ». "
    "GARDE-FOU ANTI-INVENTION (2026-07-21, trouvé en audit — un LLM a halluciné « perte de 10% de clientèle en "
    "6 mois » alors qu'aucune donnée ne le permettait) : le chiffre final DOIT provenir des données fournies "
    "ci-dessus. Si les données réelles ne permettent PAS de chiffrer une conséquence (ex. données concurrentes "
    "indisponibles, aucun nouveau service), NE JAMAIS inventer un pourcentage, un délai ou un impact hypothétique "
    "— dis-le explicitement en une phrase courte (ex. « Impossible de chiffrer ce risque sans les données "
    "concurrentes actuelles. ») plutôt que d'inventer un chiffre qui semble plausible mais n'existe nulle part."
)

# Chargement du cache fichier au démarrage
def _load_cb_file_cache():
    try:
        if os.path.exists(_CB_CACHE_FILE):
            with open(_CB_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _LLM_CB_CACHE.update(data)
            print(f"[cache CB] {len(data)} analyses chargées depuis fichier")
    except Exception as e:
        print(f"[cache CB] Erreur chargement : {e}")

def _persist_cb_cache():
    try:
        with open(_CB_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_LLM_CB_CACHE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[cache CB] Erreur persistance : {e}")

_load_cb_file_cache()


_SENT_END = tuple(".!?…»\")")

def _coupe_repetition(text):
    """Coupe une analyse qui recommence depuis le début (boucle du LLM).

    VU le 2026-07-28 sur l'écran Q2 « SGCI vs SGCI » : le modèle, dérouté par un duel sans
    adversaire, écrivait son analyse, puis la REPRENAIT intégralement depuis la première
    phrase — l'utilisateur voyait le même texte deux fois, coupé au milieu de la seconde
    copie par max_tokens. La cause de fond (le prompt) est corrigée, mais un modèle peut
    boucler sur n'importe quel prompt : ce filet évite que ça atteigne l'écran, et il
    assainit aussi les réponses déjà en cache (il s'applique à la lecture du cache).

    Méthode : on prend l'amorce du texte (≥ 60 caractères, seuil assez long pour qu'une
    répétition soit forcément une boucle et non une tournure qui revient) et on cherche sa
    réapparition plus loin. Si on la trouve, tout ce qui suit est une reprise → on tronque.
    """
    if not text or len(text) < 160:
        return text
    amorce = text.strip()[:80].strip()
    if len(amorce) < 60:
        return text
    pos = text.find(amorce, 60)
    if pos > 0:
        text = text[:pos].rstrip()
    # Amorce de puce restée orpheline en fin de texte (« **2. », « 3) », « - ») : le modèle a
    # annoncé un point qu'il n'a pas écrit, soit qu'il ait bouclé, soit que max_tokens l'ait
    # coupé. Afficher un numéro seul fait croire à un contenu manquant plutôt qu'à une réponse
    # terminée. _trim_incomplete ne l'attrapait pas : « **2. » se termine par un point, donc
    # passait pour une phrase complète.
    text = _re.sub(r"\n\s*(?:\*\*)?\d{1,2}\s*[.)]\s*(?:\*\*)?\s*$", "", text)
    return text.rstrip()


def _trim_incomplete(text):
    """Garantit que l'analyse se termine par une phrase complète.
    Si le LLM a été coupé (max_tokens), on retire la dernière phrase tronquée
    en remontant au dernier signe de ponctuation terminal. Évite les coupures
    en plein mot du type '...perdre des parts de marché auprès des'."""
    if not text:
        return text
    text = _coupe_repetition(text)
    t = text.rstrip()
    if not t:
        return t
    # Déjà terminé proprement (ponctuation, gras markdown, ou liste)
    if t.endswith(_SENT_END) or t.endswith("**") or t.endswith("*"):
        return t
    # Cherche la dernière fin de phrase réelle (point suivi d'espace/fin)
    best = -1
    for m in re.finditer(r'[.!?…](?=\s|$)|[»)]', t):
        best = m.end()
    if best > 40:  # garde au moins une phrase
        return t[:best].rstrip()
    return t  # rien de mieux : on laisse tel quel

_LLM_DOWN_UNTIL = 0   # disjoncteur : si time() < cette valeur, on saute les appels LLM
_EXCL_RESULT_CACHE = {}   # cache réponse complète exclusivités/gaps (pré-filtre difflib ~5s)

# ── État de santé LLM (badge front) : "quota" (429/rate_limit) vs "indisponible" (panne réseau,
# clé invalide…). Mis à jour par CHAQUE point d'appel LLM (_groq_call_cb, _rp_llm_json). Le front
# interroge /api/llm_status pour afficher un message clair au lieu de laisser deviner l'utilisateur.
_LLM_HEALTH = {"ok": True, "reason": None, "since": None}


def _llm_health_reason(err_text):
    t = (err_text or "").lower()
    if "429" in t or "rate_limit" in t or "quota" in t or "insufficient_quota" in t:
        return "quota"
    return "indisponible"


def _llm_mark_down(err_text):
    import time as _t
    globals()["_LLM_HEALTH"] = {"ok": False, "reason": _llm_health_reason(err_text), "since": _t.time()}


def _llm_mark_up():
    if not _LLM_HEALTH.get("ok"):
        globals()["_LLM_HEALTH"] = {"ok": True, "reason": None, "since": None}


# Au-delà de ce délai sans nouvel échec, on considère l'incident clos. Sans cette péremption,
# un seul refus passager — un 429 sur un endpoint qu'on ne rappelle pas ensuite — laissait le
# bandeau rouge affiché indéfiniment, alors que tout le reste fonctionnait. Le bandeau perdait
# alors son sens : à force d'être là sans raison, on cesse de le lire.
_LLM_PEREMPTION_S = 900          # 15 minutes


@app.route("/api/llm_status")
def api_llm_status():
    """État courant du LLM (Groq/Gemini/Claude) — le front affiche un message si indisponible,
    plutôt que de laisser croire que les analyses affichées sont fraîches."""
    import time as _t
    etat = dict(_LLM_HEALTH)
    depuis = etat.get("since")
    if not etat.get("ok") and depuis and (_t.time() - depuis) > _LLM_PEREMPTION_S:
        # L'incident n'a pas été confirmé depuis un quart d'heure : on le considère clos.
        # Le prochain échec réel relèvera le drapeau immédiatement.
        _llm_mark_up()
        etat = dict(_LLM_HEALTH)
    return jsonify(etat)


# ── Traçabilité de fraîcheur des analyses LLM ────────────────────────────────────────────────
# Chaque cache dict stocke, à côté de la clé de contenu, une clé jumelle "<clé>@meta" avec
# {"generated_at": "...", "stale": bool}. Sert à répondre honnêtement à « l'utilisateur est-il
# informé qu'il regarde une analyse de secours (LLM en panne au dernier essai), pas la toute
# dernière ? » — jusqu'ici NON : le secours était indiscernable d'une génération fraîche.
def _meta_key(key):
    return key + "@meta"


def _mark_fresh(cache, key):
    """Une génération RÉUSSIE efface tout historique de secours — l'entrée redevient « à jour »."""
    cache[_meta_key(key)] = {"generated_at": _dt.datetime.now().isoformat(timespec="seconds"), "stale": False}


def _mark_stale_from(cache, key, source_key):
    """Bascule sur une ancienne entrée (échec LLM) : reprend SA date de génération d'origine
    (pas « maintenant » — le contenu n'est PAS neuf) et marque stale=True explicitement."""
    meta = dict(cache.get(_meta_key(source_key)) or {})
    meta["stale"] = True
    cache[_meta_key(key)] = meta


def _get_meta(cache, key):
    return cache.get(_meta_key(key)) or {"generated_at": None, "stale": False}


def _gemini_call_cb(prompt: str, max_tokens: int = 512, temperature: float = 0.3) -> str:
    """Fallback Gemini (REST) quand Groq est épuisé. Retourne le texte, ou None si KO.
    N'utilise que GEMINI_API_KEY (format AIza…) ; ignore les jetons OAuth (AQ.…)."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key or not key.startswith("AIza"):
        return None
    try:
        import requests as _rq
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               "gemini-2.0-flash:generateContent?key=" + key)
        r = _rq.post(url, timeout=18, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        })
        if r.status_code != 200:
            return None
        data = r.json()
        txt = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return _trim_incomplete(txt) if txt else None
    except Exception:
        return None

import hashlib as _hl_pr   # empreinte de prompt pour les clés de cache CB (cf. _groq_call_cb)


def _groq_call_cb(prompt: str, cache_key: str, max_tokens: int = 220, temperature: float = 0.3,
                   prefer_claude: bool = False) -> dict:
    """Appelle Groq avec rotation sur toutes les clés — cache persistant fichier.
    Disjoncteur : si tous les appels ont échoué récemment, on saute l'appel (réponse
    instantanée) pour ne pas ralentir le dashboard quand les clés sont coupées.
    `temperature` : 0.3 par défaut (précis) ; ~0.8 pour la stratégie créative.
    `prefer_claude=True` (2026-07-15, CB) : appelle Claude via OpenRouter en premier — même
    logique que `_rp_llm_json` (reasoning désactivé, clé OPENROUTER_API_KEY dédiée SpyBusiness).
    Si Claude échoue/renvoie vide, bascule sur Groq (pas d'échec silencieux)."""
    from groq import Groq as _Groq
    import time as _time
    # Plancher de tokens : empêche les coupures en plein mot des analyses CB.
    max_tokens = max(max_tokens, 512)

    # ── EMPREINTE DU PROMPT DANS LA CLÉ (2026-07-30) ─────────────────────────────────────
    # Plusieurs clés d'analyse ne contenaient que des COMPTEURS :
    #   q1_repricing_v3_{segment}_{annee}_{semestre}_{n_hausses}_{n_baisses}
    #   q3_top10_v5_{segment}_{n_total}_{n_grat}   ·   q5_gaps_v5_{segment}_{n_crit}_{n_imp}_…
    # Après un ajout de données, si le NOMBRE de hausses ou de services restait identique, la clé
    # ne changeait pas et l'ancien texte était resservi — alors que les MONTANTS cités dedans
    # avaient changé. L'analyse affichée devenait fausse, sans aucun signal.
    # Le prompt contient l'intégralité des données injectées : son empreinte est donc le seul
    # marqueur exhaustif. Ajoutée ici, au point d'entrée COMMUN, elle couvre d'un coup les neuf
    # analyses concernées — et toute analyse future, sans avoir à y penser.
    # Séparateur « _ » volontaire : le mécanisme de secours plus bas isole le dernier segment de
    # la clé (`parts[:-1]`) pour retrouver une version antérieure. Il continue donc de fonctionner —
    # au premier affichage après cette mise en service, une analyse absente du cache sera
    # régénérée si le LLM répond, ou servie depuis l'ancienne entrée MARQUÉE OBSOLÈTE (bandeau
    # d'avertissement existant) si le quota est épuisé. Aucune perte, aucun silence.
    cache_key = f"{cache_key}_{_hl_pr.md5(prompt.encode('utf-8')).hexdigest()[:8]}"

    if cache_key in _LLM_CB_CACHE:
        _meta = _get_meta(_LLM_CB_CACHE, cache_key)
        return {"analyse": _trim_incomplete(_LLM_CB_CACHE[cache_key]), "source": "cache",
                "generated_at": _meta.get("generated_at"), "stale": bool(_meta.get("stale"))}

    if prefer_claude:
        _txt = _claude_call(prompt, max_tokens, temperature)
        if _txt:
            analyse = _trim_incomplete(_txt.strip())
            # GARDE-FOU (2026-07-22, demande explicite : « jamais d'hallucination », étendu à TOUS
            # les endpoints CB via ce point d'entrée partagé) — même vérification que pour la
            # Stratégie : si Claude invente un chiffre absent du prompt, on n'accepte PAS ce texte,
            # on continue vers Groq comme si Claude avait échoué (pas de retour à moitié bon).
            if not _chiffres_inventes(analyse, prompt):
                _LLM_CB_CACHE[cache_key] = analyse
                _mark_fresh(_LLM_CB_CACHE, cache_key)
                _persist_cb_cache()
                _meta = _get_meta(_LLM_CB_CACHE, cache_key)
                return {"analyse": analyse, "source": "claude",
                        "generated_at": _meta.get("generated_at"), "stale": False}

    # DISJONCTEUR ouvert → pas d'attente : on tente un cache approchant, sinon vide.
    # EXCEPTION stratégie : on IGNORE le disjoncteur et on tente un VRAI appel (l'utilisateur
    # attend ces propositions ; Groq répond ~1s quand il marche). Pas de secours inter-directeur.
    if _time.time() < _LLM_DOWN_UNTIL and not cache_key.startswith("strat_creatif"):
        parts = cache_key.split("_"); prefix_base = "_".join(parts[:-1])
        stale_key = next((k for k in _LLM_CB_CACHE
                          if k.startswith(prefix_base + "_") and not k.endswith("@meta") and _LLM_CB_CACHE[k]), None)
        if stale_key:
            _mark_stale_from(_LLM_CB_CACHE, cache_key, stale_key)
            _meta = _get_meta(_LLM_CB_CACHE, cache_key)
            return {"analyse": _trim_incomplete(_LLM_CB_CACHE[stale_key]), "source": "skip",
                    "generated_at": _meta.get("generated_at"), "stale": True}
        return {"analyse": "", "source": "skip"}

    groq_keys = [k for k in [
        os.getenv("GROQ_API_KEY_11",""), os.getenv("GROQ_API_KEY_12",""),
        os.getenv("GROQ_API_KEY_9",""),  os.getenv("GROQ_API_KEY_10",""),
        os.getenv("GROQ_API_KEY_8",""),  os.getenv("GROQ_API_KEY_5",""),
        os.getenv("GROQ_API_KEY_6",""),  os.getenv("GROQ_API_KEY_7",""),
        os.getenv("GROQ_API_KEY",""),    os.getenv("GROQ_API_KEY_2",""),
        os.getenv("GROQ_API_KEY_3",""),  os.getenv("GROQ_API_KEY_4",""),
    ] if k]

    import time as _time
    last_err = None
    for key in groq_keys:
        try:
            client = _Groq(api_key=key, timeout=45.0, max_retries=0)
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            analyse = _trim_incomplete(resp.choices[0].message.content.strip())
            # GARDE-FOU (2026-07-22) : même vérification qu'au-dessus — un chiffre inventé par
            # Groq n'est PAS accepté, on continue vers la clé Groq suivante (traité comme un échec).
            if _chiffres_inventes(analyse, prompt):
                last_err = "chiffres non fournis détectés (rejeté, 0 hallucination)"
                continue
            _LLM_CB_CACHE[cache_key] = analyse
            _mark_fresh(_LLM_CB_CACHE, cache_key)
            _persist_cb_cache()
            _llm_mark_up()
            _meta = _get_meta(_LLM_CB_CACHE, cache_key)
            return {"analyse": analyse, "source": "groq", "generated_at": _meta.get("generated_at"), "stale": False}
        except Exception as e:
            last_err = str(e)
            # Les 12 clés couvrent PLUSIEURS organisations Groq (chacune son quota 100K/jour).
            # Donc sur 429 (org épuisée), on CONTINUE vers la clé suivante : une autre org a du quota.
            _time.sleep(0.2)  # courte pause avant la clé suivante (RPM limit)
            continue

    # FALLBACK GEMINI : toutes les clés Groq ont échoué (ex. 429 TPD) → on tente Gemini.
    gem = _gemini_call_cb(prompt, max_tokens, temperature)
    if gem and not _chiffres_inventes(gem, prompt):
        _LLM_CB_CACHE[cache_key] = gem
        _mark_fresh(_LLM_CB_CACHE, cache_key)
        _persist_cb_cache()
        _llm_mark_up()
        _meta = _get_meta(_LLM_CB_CACHE, cache_key)
        return {"analyse": gem, "source": "gemini", "generated_at": _meta.get("generated_at"), "stale": False}

    # Groq ET Gemini indisponibles → ouvrir le DISJONCTEUR : on saute les appels LLM
    # pendant 5 min pour que le dashboard reste RAPIDE (fallback instantané). Réessai auto.
    # EXCEPTION stratégie : un directeur en échec NE déclenche PAS le disjoncteur, sinon
    # il bloquerait les directeurs suivants du MÊME appel (→ seulement 1-2 directeurs).
    _llm_mark_down(last_err)
    if not cache_key.startswith("strat_creatif"):
        globals()["_LLM_DOWN_UNTIL"] = _time.time() + 300

    # Chercher un résultat de secours dans le cache.
    # Préfixe large (sans version ni segment ni hash) pour matcher v2 et v3.
    # Ex: "q3_axe5_v3_Particuliers_abc" → prefix_base "q3_axe5"
    # Ex: "q5_axe3_BICICI_v3_Particuliers_abc" → prefix_base "q5_axe3_BICICI"
    # Stratégie : pas de secours inter-directeur (cf. ci-dessus) → on rend vide.
    if cache_key.startswith("strat_creatif"):
        return {"analyse": None, "error": str(last_err)}
    parts = cache_key.split("_")
    # Utilise parts[:-1] pour ne striper que le hash, pas l'année/semestre
    # évite de servir un résultat 2026 pour une requête 2025
    prefix_base = "_".join(parts[:-1])
    stale_key = next((k for k in _LLM_CB_CACHE
                      if k.startswith(prefix_base + "_") and not k.endswith("@meta") and _LLM_CB_CACHE[k]), None)
    if stale_key:
        _mark_stale_from(_LLM_CB_CACHE, cache_key, stale_key)
        _meta = _get_meta(_LLM_CB_CACHE, cache_key)
        return {"analyse": _trim_incomplete(_LLM_CB_CACHE[stale_key]), "source": "cache_stale",
                "generated_at": _meta.get("generated_at"), "stale": True}

    return {"analyse": None, "error": str(last_err)}


@app.route("/api/cb_q1_llm", methods=["POST"])
def api_cb_q1_llm():
    """
    Q1 — 2 scopes :
      scope='ranking'   → positionnement SGCI dans les catalogues du marché
      scope='synthesis' → lecture stratégique de l'évolution du catalogue SGCI
    """
    body     = request.get_json(force=True, silent=True) or {}
    segment  = (body.get("segment") or "Particuliers").strip()
    scope    = (body.get("scope") or "synthesis").strip()
    annee    = int(body.get("annee") or 2026)
    semestre = (body.get("semestre") or "S1").strip()
    period   = (body.get("period") or f"2024 → {annee} {semestre}").strip()

    if scope == "ranking":
        sgci     = body.get("sgci") or {}
        all_banks = body.get("allBanks") or []
        mkt_avg  = body.get("mktAvgDelta", 0)

        banks_txt = "\n".join(
            f"  - {b['b']} : +{b['ajouts']} nouveaux services, -{b['retraits']} retirés "
            f"(catalogue actuel {b['catalogue']})"
            + (" ← SGCI" if b['b'] == "SGCI" else "")
            for b in all_banks
        ) or "  (données non disponibles)"

        prompt = f"""Tu es un analyste bancaire senior, marché ivoirien (UEMOA).
Évolution des catalogues tarifaires {period}, segment {segment} — données RÉELLES :

{banks_txt}

RÈGLE ABSOLUE : utilise EXCLUSIVEMENT les nombres ci-dessus (nouveaux services = le "+N",
retirés = le "-N", catalogue = le total). N'invente AUCUN autre chiffre, AUCUN pourcentage.
Cite les nombres exactement comme indiqués (ex. "NSIA +32 nouveaux services").

En 3 phrases PRÉCISES, en citant les banques par leur nom exact :
1. Les 2-3 concurrents qui ajoutent le plus de nouveaux services (cite leur "+N" exact) et ce que cela signifie pour SGCI (compare au +{sgci.get('ajouts',0)} de SGCI).
2. Le concurrent le plus menaçant à court terme et pourquoi (nb de nouveaux services + taille de catalogue).
3. UN objectif CHIFFRÉ et grounded dans les nombres ci-dessus (jamais générique type « réviser son offre », « proposer des tarifs compétitifs », « des services innovants ») : par exemple le rythme de nouveaux services que SGCI devrait atteindre par semestre pour réduire l'écart avec le concurrent le plus actif d'ici un horizon donné, EN PARTANT de son +{sgci.get('ajouts',0)} actuel.
Commence directement."""

        # Clé sensible aux ajouts/retraits de CHAQUE banque → jamais d'analyse périmée
        # servie quand les données concurrentes arrivent (evAll) après le 1er rendu.
        sig = "-".join(f"{b['b'][:3]}{b.get('ajouts',0)}.{b.get('retraits',0)}" for b in all_banks)
        cache_key = f"q1_rank_v6_{segment}_{annee}_{semestre}_{sig}"
        # Ne pas générer tant que les concurrents sont tous à 0 (données pas encore chargées)
        if all(b['b'] == 'SGCI' or b.get('ajouts', 0) == 0 for b in all_banks):
            return {"analyse": None, "error": "données concurrentes en cours de chargement"}
        result = _groq_call_cb(prompt+_BOLD_INSTR, cache_key, max_tokens=260, prefer_claude=True)

    else:  # synthesis
        n_app      = int(body.get("nApp") or 0)
        n_dis      = int(body.get("nDis") or 0)
        n_b        = int(body.get("nBaisses") or 0)
        n_h        = int(body.get("nHausses") or 0)
        apparus    = body.get("apparus") or []
        mkt_context = body.get("mktContext") or []

        services_list = "\n".join(
            f"  - {r.get('libelle','?')}"
            + (" [GRATUIT]" if r.get("est_gratuit") else "")
            + (f" [section {r.get('section','')}]" if r.get("section") else "")
            for r in apparus[:15]
        ) or "  (aucune nouvelle offre)"

        mkt_sorted = sorted(mkt_context[:6], key=lambda b: -b.get('delta', 0))
        mkt_txt = ", ".join(
            f"{b['b']} +{b['delta']} nouveaux services" for b in mkt_sorted
        ) or "données concurrentes non disponibles"

        # Ne pas générer tant que les concurrents sont tous à 0 (evAll pas encore chargé)
        # → évite de produire/figer "les concurrents ne proposent aucune offre".
        # Corrigé 2026-07-21 (audit) : un mkt_context VIDE (pas encore chargé) passait ce garde-fou
        # (all() sur liste vide = True mais le "and" court-circuitait), laissant le LLM halluciner
        # un risque chiffré sans aucune donnée concurrente réelle. Bloqué aussi dans ce cas.
        if not mkt_context or all(b.get('delta', 0) == 0 for b in mkt_context):
            return jsonify({"analyse": None, "error": "données concurrentes en cours de chargement"}), 503

        prompt = f"""Tu es un analyste bancaire senior, marché ivoirien (UEMOA), {period}, segment {segment}.

CHIFFRES RÉELS (à citer EXACTEMENT, n'en invente AUCUN autre) :
- SGCI : +{n_app} nouveaux services, -{n_dis} retraits, {n_h} hausses tarifaires, {n_b} baisses
- Nouveaux services ajoutés par les concurrents : {mkt_txt}

Nouvelles offres SGCI (exemples) :
{services_list}

RÈGLE ABSOLUE : utilise UNIQUEMENT les nombres ci-dessus. Pour SGCI c'est +{n_app} (pas un autre).
Ne dis JAMAIS qu'un concurrent ne propose "aucune" offre si son chiffre est > 0.

En 3 phrases PRÉCISES :
1. La direction de SGCI (+{n_app} nouveaux services) est-elle offensive ou en retard face au rythme des concurrents (cite les plus actifs avec leur "+N" exact) ?
2. Signal le plus fort des nouvelles offres SGCI (gratuité, digital, épargne…) et priorité révélée.
3. Risque concurrentiel précis face aux banques qui ajoutent le plus de services.
Commence directement. Sois précis et nominatif."""

        sig = "-".join(f"{b['b'][:3]}{b.get('delta',0)}" for b in mkt_sorted)
        cache_key = f"q1_synth_v5_{segment}_{annee}_{semestre}_{n_app}_{n_dis}_{n_b}_{n_h}_{sig}"
        result = _groq_call_cb(prompt+_BOLD_INSTR, cache_key, max_tokens=260, prefer_claude=True)

    if result.get("analyse"):
        return jsonify({"analyse": result["analyse"], "source": result.get("source","groq")})

    # ── RÉDACTION DE SECOURS (2026-08-10) ────────────────────────────────────────────
    # Jusqu'ici on rendait 503, et le front VIDAIT le bloc : l'utilisateur voyait un trou à
    # l'endroit d'une analyse, sans rien qui l'explique. Un jour de quota épuisé, l'application
    # paraissait cassée alors que tous ses chiffres étaient là.
    #
    # On rédige donc à partir des MÊMES faits que ceux envoyés au modèle. Ce n'est pas une
    # phrase toute faite : elle est calculée, donc elle change avec les données — si SGCI
    # passe du cinquième au troisième rang, le texte le dit sans qu'on y touche.
    try:
        import redaction_secours as _sec
        if scope == "ranking":
            texte = _sec.q1_classement(body.get("allBanks") or [], segment, period)
        else:
            texte = _sec.q1_synthese(n_app, n_dis, n_h, n_b,
                                     body.get("apparus") or [],
                                     body.get("mktContext") or [], segment)
        if texte:
            return jsonify({"analyse": texte, "source": "deterministe",
                            "mention": _sec.MENTION})
    except Exception as e:
        print("[secours] q1 :", str(e)[:160])
    return jsonify({"analyse": None, "error": result.get("error")}), 503


@app.route("/api/cb_q2_llm", methods=["POST"])
def api_cb_q2_llm():
    """Analyse stratégique LLM d'un concurrent pour Q2 (per-bank)."""
    body      = request.get_json(force=True, silent=True) or {}
    bank_name = (body.get("bankName") or "").strip()
    segment   = (body.get("segment") or "Particuliers").strip()
    annee     = int(body.get("annee") or 2026)
    semestre  = (body.get("semestre") or "S1").strip()
    period    = (body.get("period") or f"2024 → {annee} {semestre}").strip()
    n_app     = int(body.get("nApp") or 0)
    n_other   = int(body.get("nOther") or 0)
    other_seg = (body.get("otherSeg") or "").strip()
    rate      = body.get("rate")
    sgci_rate = body.get("sgciRate")
    apparus   = body.get("apparus") or []

    if not bank_name:
        return jsonify({"error": "bankName manquant"}), 400

    # v3 (2026-07-28) : la clé ne contient AUCUN hash du prompt — corriger le prompt sans
    # changer la version laisserait servir indéfiniment les réponses défectueuses déjà en cache.
    cache_key = f"q2v3_{bank_name}_{segment}_{annee}_{semestre}_{n_app}_{n_other}"
    services_list = "\n".join(
        f"  - {r.get('libelle','?')}"
        + (" [gratuit]" if r.get("est_gratuit") else "")
        + (f" [section {r.get('section','')}]" if r.get("section") else "")
        for r in apparus[:20]
    ) or "  (liste non disponible)"

    cross_note = (f"\nSur {other_seg} : {n_other} innovations (vs {n_app} ici)."
                  if other_seg and n_other >= 0 else "")
    rate_note  = (f"\nTaux innovation : {rate}% vs SGCI {sgci_rate}% (écart {round(float(rate)-float(sgci_rate),1):+.1f}pts)."
                  if rate is not None and sgci_rate is not None else "")

    # BUG SIGNALÉ le 2026-07-28 : quand la banque sélectionnée EST SGCI, ce prompt devenait
    # littéralement « SGCI vs SGCI ». Le modèle ouvrait alors sa réponse par une objection
    # méthodologique (« les données opposent SGCI à elle-même, l'exercice concurrentiel est
    # impossible »), improvisait une comparaison au marché, puis se répétait — la réponse
    # s'affichait deux fois et coupée. L'objection était JUSTE : on lui demandait de désigner
    # une menace concurrentielle dans un duel sans adversaire. Un écran par banque doit poser
    # une question différente quand la banque regardée est la nôtre : ce n'est plus « en quoi
    # ce concurrent me menace », c'est « où en suis-je face au marché ».
    if bank_name.strip().upper() == "SGCI":
        prompt = f"""Tu es un analyste bancaire senior, marché ivoirien (UEMOA).
Données réelles — innovation de SGCI (notre banque), {period}, segment {segment} :
• SGCI a lancé {n_app} nouvelles offres{cross_note}{rate_note}

Nouvelles offres de SGCI :
{services_list}

Il s'agit d'une auto-analyse : SGCI est notre propre banque, PAS un concurrent. Ne cherche
aucune « menace SGCI », ne compare pas SGCI à elle-même. Le point de comparaison est le
marché (BACI, BICICI, BNI, ECOBANK, NSIA, SIB) via le taux d'innovation ci-dessus.

En 3 phrases PRÉCISES :
1. Sur quels types de service SGCI a concentré ses nouveautés, et ce que ce choix révèle de sa stratégie.
2. Ce que son rythme d'innovation dit de sa position face au marché — nomme la ou les banques qui vont plus vite si l'écart est défavorable.
3. UNE décision spécifique et nommée (jamais générique type « élargir son offre ») : quel domaine SGCI laisse découvert au vu de ces nouveautés, et quoi lancer en priorité.
Commence directement par l'analyse, sans préambule et sans commentaire sur les données fournies."""
    else:
        prompt = f"""Tu es un analyste bancaire senior, marché ivoirien (UEMOA).
Données réelles — {bank_name} vs SGCI, {period}, segment {segment} :
• {bank_name} a lancé {n_app} nouvelles offres{cross_note}{rate_note}

Nouvelles offres de {bank_name} :
{services_list}

En 3 phrases PRÉCISES, en nommant {bank_name} explicitement :
1. Quelle est la stratégie réelle de {bank_name} — sur quel segment ou type de service concentre-t-il ses nouvelles offres et pourquoi c'est significatif pour SGCI ?
2. Dans quel(s) domaine(s) précis SGCI est-il le plus exposé face à {bank_name} (ex: monétique, virements, épargne, crédits) — cite les offres qui créent l'écart ?
3. UNE décision SPÉCIFIQUE et NOMMÉE face à {bank_name} (jamais générique type « proposer des tarifs compétitifs », « élargir son offre », « des services innovants ») : cite UN service précis parmi ceux listés ci-dessus sur lequel SGCI doit répliquer en priorité, et quel type de client cela retient/attire concrètement.
Commence directement. Cite {bank_name} par son nom dans chaque phrase. Sois précis et actionnable."""

    result = _groq_call_cb(prompt+_BOLD_INSTR, cache_key, max_tokens=260, prefer_claude=True)
    if result.get("analyse"):
        return jsonify({"analyse": result["analyse"], "source": result.get("source","groq")})
    return jsonify({"analyse": None, "error": result.get("error")}), 503


_Q2_MARKET_CACHE: dict = {}

@app.route("/api/cb_q2_market_llm", methods=["POST"])
def api_cb_q2_market_llm():
    """Synthèse LLM du positionnement marché SGCI (Q2 — panel taux d'innovation)."""
    body        = request.get_json(force=True, silent=True) or {}
    segment     = (body.get("segment") or "Particuliers").strip()
    annee       = int(body.get("annee") or 2026)
    semestre    = (body.get("semestre") or "S1").strip()
    sgci_rank   = int(body.get("sgciRank") or 0)
    total_banks = int(body.get("totalBanks") or 7)
    sgci_rate   = body.get("sgciRate", 0)
    mkt_avg     = body.get("mktAvg", 0)
    sgci_n_app  = int(body.get("sgciNApp") or 0)
    sgci_n_grat = int(body.get("sgciNGrat") or 0)
    all_banks   = body.get("allBanks") or []
    gratuit_banks = body.get("gratuitBanks") or []

    banks_txt = ", ".join(
        f"{b['b']} ({b['rate']}%, +{b['nApp']} offres)" for b in all_banks
    )
    gratuit_txt = ", ".join(gratuit_banks) or "aucun"

    # Dépassement : combien des nouveautés sont ABSENTES de SGCI (vraie menace) vs rattrapage.
    dep_txt, dep_sig = "", ""
    try:
        rd = AGENTS["CB"].structured.cb_rattrapage_depassement(segment)
        rd_sorted = sorted(rd, key=lambda x: -x.get("depassement", 0))
        dep_txt = " · ".join(
            f"{r['banque']} {r['depassement']} dépassent / {r['rattrapage']} rattrapent"
            for r in rd_sorted if r.get("total"))
        dep_sig = "-".join(f"{r['banque'][:3]}{r['depassement']}" for r in rd_sorted)
    except Exception:
        pass

    prompt = f"""Tu es un analyste bancaire senior, marché ivoirien (UEMOA).
Classement par taux d'innovation (nouvelles offres ÷ catalogue), 2024–{annee} {semestre}, segment {segment} :
{banks_txt}

SGCI est classé {sgci_rank}/{total_banks} avec un taux de {sgci_rate}% (moy. marché : {mkt_avg}%).
SGCI : {sgci_n_app} nouvelles offres dont {sgci_n_grat} gratuites.

DÉPASSEMENT (clé) — parmi les nouveautés de chaque concurrent, combien sont ABSENTES de SGCI
(= vraie avance/menace) vs combien ne font que RATTRAPER des services déjà chez SGCI :
{dep_txt or 'non disponible'}.

En 3 phrases PRÉCISES — cite les banques par leur nom :
1. Qui innove le plus vite (taux) — MAIS précise si c'est surtout du rattrapage de SGCI ou un vrai dépassement (un fort taux qui ne fait que rattraper SGCI est moins menaçant).
2. La menace RÉELLE = la banque qui DÉPASSE le plus SGCI (plus de services absents de SGCI) : nomme-la avec son nombre de dépassements, et dans quels domaines.
3. La décision que SGCI doit prendre face à ce dépassement (pas face au simple rattrapage).
Commence directement. Appuie-toi sur les chiffres de DÉPASSEMENT, pas seulement le taux brut."""

    cache_key = f"q2_mkt_v4dep_{segment}_{annee}_{semestre}_{sgci_rank}_{sgci_rate}_{dep_sig}"
    result = _groq_call_cb(prompt+_BOLD_INSTR, cache_key, max_tokens=260, prefer_claude=True)
    if result.get("analyse"):
        return jsonify({"analyse": result["analyse"], "source": result.get("source","groq")})
    return jsonify({"analyse": None, "error": result.get("error")}), 503


@app.route("/api/cb_q1_repricing_llm", methods=["POST"])
def api_cb_q1_repricing_llm():
    """Analyse stratégique LLM des mouvements tarifaires SGCI (Q1 — repricing)."""
    body      = request.get_json(force=True, silent=True) or {}
    segment   = (body.get("segment") or "Particuliers").strip()
    annee     = int(body.get("annee") or 2026)
    semestre  = (body.get("semestre") or "S1").strip()
    period    = (body.get("period") or f"2024 S1 → {annee} {semestre}").strip()
    n_hausses = int(body.get("nHausses") or 0)
    n_baisses = int(body.get("nBaisses") or 0)
    hausses   = body.get("hausses") or []
    baisses   = body.get("baisses") or []

    h_txt = "\n".join(
        f"- {h['libelle']} : {h['avant']} → {h['apres']} F (+{h['pct']}%)"
        for h in hausses
    ) or "Aucune"
    b_txt = "\n".join(
        f"- {b['libelle']} : {b['avant']} → {b['apres']} F ({b['pct']}%)"
        for b in baisses
    ) or "Aucune"

    prompt = f"""Tu es un analyste bancaire senior, marché ivoirien (UEMOA).
Mouvements tarifaires SGCI, segment {segment}, {period} — données réelles :

Hausses SGCI ({n_hausses} au total) :
{h_txt}

Baisses / gratuités SGCI ({n_baisses} au total) :
{b_txt}

Contexte concurrentiel : sur ce marché ivoirien, BICICI, SIB, ECOBANK et BNI rivalisent directement sur les mêmes segments.

En 3 phrases PRÉCISES et analytiques :
1. Ces hausses tarifaires sont-elles un signal de repositionnement premium ou de pression sur les marges — et par rapport à quelle banque concurrente ce mouvement est-il risqué ou opportun ?
2. Quelle est la cohérence de la combinaison hausses/baisses — SGCI cherche-t-il à monétiser certains services tout en rendant d'autres gratuits pour attirer un profil client précis ?
3. Quel concurrent précis (ex: BICICI, SIB) est le mieux positionné pour exploiter ces hausses SGCI et attirer des clients sensibles au prix — et sur quels services ?
Commence directement. Cite des noms de banques concurrentes et des catégories de services précises."""

    cache_key = f"q1_repricing_v3_{segment}_{annee}_{semestre}_{n_hausses}_{n_baisses}"
    result = _groq_call_cb(prompt+_BOLD_INSTR, cache_key, max_tokens=280, prefer_claude=True)
    if result.get("analyse"):
        return jsonify({"analyse": result["analyse"], "source": result.get("source", "groq")})
    return jsonify({"analyse": None, "error": result.get("error")}), 503


@app.route("/api/cb_q1_retrait_llm", methods=["POST"])
def api_cb_q1_retrait_llm():
    """Analyse stratégique LLM des services retirés du catalogue SGCI (Q1)."""
    body            = request.get_json(force=True, silent=True) or {}
    segment         = (body.get("segment") or "Particuliers").strip()
    annee           = int(body.get("annee") or 2026)
    semestre        = (body.get("semestre") or "S1").strip()
    period          = (body.get("period") or f"2024 S1 → {annee} {semestre}").strip()
    n_retraits      = int(body.get("nRetraits") or 0)
    avec_concurrence = int(body.get("avecConcurrence") or 0)
    services        = body.get("services") or []

    exposed = [s for s in services if s.get("concurrents")]
    safe    = [s for s in services if not s.get("concurrents")]

    exposed_txt = "\n".join(
        f"- {s['libelle']} (encore chez : {', '.join(s['concurrents'])})"
        for s in exposed[:5]
    ) or "Aucun"
    safe_txt = ", ".join(s['libelle'] for s in safe[:5]) or "Aucun"

    prompt = f"""Tu es un analyste bancaire senior, marché ivoirien (UEMOA).
SGCI a retiré {n_retraits} service(s) de son catalogue, segment {segment}, {period}.
Parmi eux, {avec_concurrence} sont ENCORE proposés par au moins un concurrent.

Services retirés toujours chez la concurrence (risque direct) :
{exposed_txt}

Services retirés sans concurrent actif :
{safe_txt}

En 3 phrases ANALYTIQUES et nominatives :
1. Ces {avec_concurrence} retraits "à risque" créent-ils concrètement une opportunité pour des banques comme BICICI, SIB ou ECOBANK d'attirer les clients SGCI mécontents — sur quels services précisément ?
2. La rationalisation globale ({n_retraits} retraits) est-elle une stratégie de simplification assumée ou un signe de fragilité de l'offre par rapport aux concurrents qui, eux, élargissent leur catalogue ?
3. Quelle décision SGCI doit-elle prendre pour les services retirés qui ont encore des concurrents actifs ?
Commence directement. Cite des banques concurrentes et des noms de services précis."""

    cache_key = f"q1_retrait_v3_{segment}_{annee}_{semestre}_{n_retraits}_{avec_concurrence}"
    result = _groq_call_cb(prompt+_BOLD_INSTR, cache_key, max_tokens=280, prefer_claude=True)
    if result.get("analyse"):
        return jsonify({"analyse": result["analyse"], "source": result.get("source", "groq")})
    return jsonify({"analyse": None, "error": result.get("error")}), 503


@app.route("/api/cb_q3_llm", methods=["POST"])
def api_cb_q3_llm():
    """Analyse stratégique LLM des exclusivités SGCI (Q3)."""
    body        = request.get_json(force=True, silent=True) or {}
    segment     = (body.get("segment") or "Particuliers").strip()
    scope       = body.get("scope", "strategy")
    n_total     = int(body.get("nTotal") or 0)
    n_grat      = int(body.get("nGrat") or 0)
    top_domains = body.get("topDomains") or []
    top_gratuits = body.get("topGratuits") or []
    top_payants = body.get("topPayants") or []

    dom_txt = ", ".join(
        f"{d['domaine']} ({d['n']} dont {d['nGrat']} gratuits)"
        for d in top_domains
    )
    grat_txt = ", ".join(g["libelle"] for g in top_gratuits[:6]) or "Aucun"
    pay_txt  = ", ".join(p["libelle"] for p in top_payants[:4]) or "Aucun"

    if scope == "domains":
        prompt = f"""Tu es un directeur commercial bancaire, marché ivoirien (UEMOA).
SGCI a {n_total} services exclusifs absents de {_concurrents_txt()}, segment {segment}.
Répartition par domaine : {dom_txt}.

En 2 phrases PRÉCISES et nominatives :
1. Dans quels 2 domaines cet avantage exclusif de SGCI est-il le plus redoutable face à BICICI ou SIB — et pourquoi ce domaine spécifiquement frappe là où les concurrents ont des lacunes ?
2. Si BICICI ou ECOBANK comble cet écart dans 12 mois, quelle clientèle SGCI perdra en premier et sur quel segment ?
Commence directement. Cite BICICI, SIB, ECOBANK ou d'autres concurrents par leur nom."""
        cache_key = f"q3_domains_v4_{segment}_{n_total}_{n_grat}"
        max_tok = 380
    else:
        prompt = f"""Tu es un directeur commercial bancaire, marché ivoirien (UEMOA).
SGCI possède {n_total} services exclusifs (absents de {_concurrents_txt()}) dont {n_grat} gratuits, segment {segment}.
Domaines leaders : {dom_txt}.
Exclusivités gratuites phares : {grat_txt}.
Exclusivités payantes : {pay_txt}.

En 3 points PRÉCIS et nominatifs — retour à la ligne entre chaque point :
1. Parmi ces exclusivités, lesquelles créent un avantage concurrentiel réel face aux banques les plus agressives (BICICI, SIB) — et pourquoi ces services précis font une différence dans l'argumentaire commercial ?
2. Comment les équipes commerciales SGCI doivent-elles positionner ces exclusivités face à un client qui compare avec BICICI ou ECOBANK — quel service citer en premier et quel bénéfice client mettre en avant ?
3. Quel risque précis SGCI court-il si BICICI ou ECOBANK lance des services similaires dans les 12 prochains mois — et sur quel segment serait l'impact le plus fort ?
Commence directement. Cite des noms de banques et des noms de services concrets. Ne coupe PAS ta réponse — complète les 3 points en entier."""
        cache_key = f"q3_strat_v4_{segment}_{n_total}_{n_grat}"
        max_tok = 480

    result = _groq_call_cb(prompt+_BOLD_INSTR, cache_key, max_tokens=max_tok, prefer_claude=True)
    if result.get("analyse"):
        return jsonify({"analyse": result["analyse"], "source": result.get("source", "groq")})
    return jsonify({"analyse": None, "error": result.get("error")}), 503


@app.route("/api/cb_q4_llm", methods=["POST"])
def api_cb_q4_llm():
    """Analyse stratégique LLM du score VRIST SGCI (Q4)."""
    body         = request.get_json(force=True, silent=True) or {}
    segment      = (body.get("segment") or "Particuliers").strip()
    annee        = int(body.get("annee") or 2026)
    semestre     = (body.get("semestre") or "S1").strip()
    scores       = body.get("scores") or {}
    global_score = body.get("global", 0)
    label        = body.get("label", "")
    n_excl       = int(body.get("nExclusifs") or 0)
    n_grat       = int(body.get("nGrat") or 0)
    n_sec        = int(body.get("nSec") or 0)
    top_domain   = body.get("topDomain", "—")
    point_faible = body.get("pointFaible", "Transformatif")

    scores_txt = " · ".join(
        f"{k}={v}/10" for k, v in scores.items()
    )

    top_exclusifs = body.get("topExclusifs") or []
    top_excl_txt  = ", ".join(top_exclusifs[:8]) if top_exclusifs else f"{n_excl} services exclusifs"
    top_gaps      = body.get("topGaps") or {}     # {banque: n_gaps}
    top_gaps_txt  = " | ".join(f"{b}: {n} gaps" for b, n in sorted(top_gaps.items(), key=lambda x:-x[1])[:4]) if top_gaps else "non disponible"

    prompt = f"""Tu es un analyste stratégique senior (marchés bancaires UEMOA).
Rédige une analyse VRIST de SGCI, segment {segment}, CLAIRE et AFFIRMATIVE.

RÈGLES ABSOLUES :
- Des phrases AFFIRMATIVES uniquement. JAMAIS de question (pas de « ? »).
- Pas de « pourrait », « probablement », « peut-être ». Tu affirmes.
- Chaque puce = 1 constat + 1 fait concret. Maximum 140 mots au total.

DONNÉES :
- Score VRIST global : {global_score}/10 ({label}). Détail : {scores_txt}.
- Exclusivités SGCI ({n_excl}) : {top_excl_txt}.
- Dimension la plus faible : {point_faible} ({scores.get('T', 4)}/10). Domaine le plus exclusif : {top_domain}.

STRUCTURE EXACTE (4 puces, 1–2 phrases chacune, mot-clé en gras) :
• **Positionnement** : affirme si {global_score}/10 est solide ou fragile, et NOMME le concurrent le plus proche.
• **Point faible** : nomme la dimension {point_faible} et cite UN service concret d'un concurrent qui l'exploite (que SGCI n'a pas).
• **Avantage durable** : cite 1–2 exclusivités SGCI vraiment inimitables et la raison (barrière réglementaire / réseau SG Group), puis 1 exclusivité facilement copiable.
• **Action 6 mois** : UNE action concrète commençant par un verbe (Lancer, Déployer, Tarifer…)."""

    cache_key = f"q4_vrist_v5clr_{segment}_{annee}_{semestre}_{global_score}_{n_excl}_{n_grat}_{len(top_exclusifs)}"
    result = _groq_call_cb(prompt+_BOLD_INSTR, cache_key, max_tokens=650, prefer_claude=True)
    if result.get("analyse"):
        return jsonify({"analyse": result["analyse"], "source": result.get("source", "groq")})
    return jsonify({"analyse": None, "error": result.get("error")}), 503


@app.route("/api/cb_q2_inno_llm", methods=["POST"])
def api_cb_q2_inno_llm():
    """Analyse stratégique LLM du panorama d'innovations — toutes banques."""
    body    = request.get_json(force=True, silent=True) or {}
    segment = (body.get("segment") or "Particuliers").strip()
    year    = body.get("year", "2026")
    sem     = body.get("sem", "S1")
    sgci_ct = int(body.get("sgciCount") or 0)
    banks   = body.get("banks") or []

    banks_txt = "\n".join(
        f"  • {b.get('banque','?')} : {b.get('nInno',0)} innovations "
        + f"({b.get('nGrat',0)} gratuites)"
        + (f" — domaines : {', '.join(b.get('topDomains',[]))}" if b.get('topDomains') else "")
        for b in sorted(banks, key=lambda x: -x.get('nInno', 0))
    ) or "  (données non disponibles)"

    # ── Pont CB × EF : position financière (Résultat Net) du dashboard Santé Financière ──
    # Sert UNIQUEMENT à donner un profil stratégique cohérent par banque (pas une corrélation).
    fin_txt, fin_sig = "", ""
    try:
        fin = AGENTS["CB"].structured.cb_innovation_vs_finance(segment)
        fin_ranked = sorted([f for f in fin if f.get("resultat_net") is not None],
                            key=lambda f: -f["resultat_net"])
        fin_txt = " · ".join(f"{f['banque']} #{i+1}" for i, f in enumerate(fin_ranked))
        fin_sig = "-".join(f"{f['banque'][:3]}{i+1}" for i, f in enumerate(fin_ranked))
    except Exception:
        pass

    prompt = f"""Tu es un analyste bancaire senior, marché ivoirien (UEMOA).
Innovations au catalogue lancées de 2024 à {year} {sem}, segment {segment} :

{banks_txt}

Position financière (Résultat Net, source États Financiers — classement marché) : {fin_txt or 'non disponible'}.

Analyse en 4-5 phrases nominatives et chiffrées :
1. Le leader de l'innovation et pourquoi (axe BCEAO, vitesse, gratuité).
2. Où se situe SGCI (force ou retard d'innovation).
3. PROFIL STRATÉGIQUE des 2-3 banques clés en croisant rythme d'innovation ET rang financier ci-dessus, selon cette grille :
   - innove beaucoup + bien classé financièrement = offensive soutenable (menace sérieuse) ;
   - innove beaucoup + mal classé = pari risqué / course aux parts de marché ;
   - innove peu + bien classé = position de rente, moyens sous-exploités (cas SGCI : #1 financier mais peu de nouveautés) ;
   - innove peu + mal classé = en difficulté.
4. CE QUI CHANGE pour le client : type de nouveauté dominant (digital, paiement, modèle tarifaire/gratuité, épargne-crédit) et avantage — déduit UNIQUEMENT des axes/services fournis, n'invente aucune technologie.
5. La question stratégique que SGCI doit se poser.

Utilise le rang financier fourni tel quel, n'invente aucun chiffre. Sois direct et critique."""

    cache_key = f"q2_inno_v6fin_{segment}_{year}_{sem}_{sgci_ct}_{len(banks)}_{fin_sig}"
    result = _groq_call_cb(prompt+_BOLD_INSTR, cache_key, max_tokens=320, prefer_claude=True)
    if result.get("analyse"):
        return jsonify({"analyse": result["analyse"], "source": result.get("source", "groq")})
    return jsonify({"analyse": None, "error": result.get("error")}), 503


@app.route("/api/cb_q1_conc_llm", methods=["POST"])
def api_cb_q1_conc_llm():
    """Analyse stratégique LLM d'un concurrent — vue détaillée Q1 par domaine."""
    body        = request.get_json(force=True, silent=True) or {}
    banque      = (body.get("banque") or "").strip()
    segment     = (body.get("segment") or "Particuliers").strip()
    annee       = int(body.get("annee") or 2026)
    semestre    = (body.get("semestre") or "S1").strip()
    period      = (body.get("period") or f"2024 S1 → {annee} {semestre}").strip()
    n_total     = int(body.get("nTotal") or 0)
    n_grat      = int(body.get("nGrat") or 0)
    top_domains = body.get("topDomains") or []
    overlap_pct = int(body.get("overlapPct") or 0)
    overlap_txt = body.get("overlapTxt", "")
    bank_rate   = body.get("bankRate")
    sgci_rate   = body.get("sgciRate")
    all_rates   = body.get("allRates", "")

    if not banque:
        return jsonify({"error": "banque manquant"}), 400

    grat_pct = round(n_grat / n_total * 100) if n_total else 0
    domains_txt = "\n".join(
        f"  - {d['domaine']} : +{d['n']} offres{' dont '+str(d['nGrat'])+' gratuites' if d.get('nGrat') else ''}"
        for d in top_domains
    ) or "  (non disponible)"

    rate_ctx = ""
    if bank_rate is not None and sgci_rate is not None:
        rate_ctx = f"\nTaux d'innovation : {banque} {bank_rate}% vs SGCI {sgci_rate}% (marché : {all_rates})"

    prompt = f"""Tu es un analyste bancaire senior, marché ivoirien (UEMOA).
Analyse de {banque} vs SGCI, {period}, segment {segment} :

• {banque} a lancé {n_total} nouvelles offres au total ({n_grat} gratuites, {grat_pct}%){rate_ctx}
• Concentration par domaine :
{domains_txt}
• Chevauchement avec les segments SGCI : {overlap_pct}% ({overlap_txt})

En 3 phrases PRÉCISES et nominatives — cite {banque} et SGCI par leur nom :
1. Quelle est la stratégie réelle de {banque} — sur quel domaine se concentre-t-elle et pourquoi c'est une menace directe ou indirecte pour SGCI sur le segment {segment} ?
2. Parmi ces {n_total} nouvelles offres, quelles sont les 2-3 qui créent le plus de risque de perte de clients SGCI — et pourquoi ces services précis font basculer le choix d'un client ?
3. Quelle réponse SGCI doit-elle préparer dans les 6 mois face à cette offensive de {banque} — sur quel domaine en priorité et avec quel type d'offre ?
Commence directement. Cite des noms de services ou de domaines précis. Sois incisif."""

    cache_key = f"q1_conc_v4axes_{banque}_{segment}_{annee}_{semestre}_{n_total}_{n_grat}_{overlap_pct}"
    result = _groq_call_cb(prompt+_BOLD_INSTR, cache_key, max_tokens=280, prefer_claude=True)
    if result.get("analyse"):
        return jsonify({"analyse": result["analyse"], "source": result.get("source","groq")})
    return jsonify({"analyse": None, "error": result.get("error")}), 503


@app.route("/api/cb_q3_exclusif_llm", methods=["POST"])
def api_cb_q3_exclusif_llm():
    """Top 10 exclusivités SGCI expliquées par le LLM — pourquoi exclusif et valeur stratégique."""
    body        = request.get_json(force=True, silent=True) or {}
    segment     = (body.get("segment") or "Particuliers").strip()
    n_total     = int(body.get("nTotal") or 0)
    n_grat      = int(body.get("nGrat") or 0)
    services    = body.get("services") or []

    services_txt = "\n".join(
        f"  {i+1}. {s.get('libelle','?')} "
        + ("[GRATUIT]" if s.get("est_gratuit") else f"[{s.get('tarif','payant')}]")
        + f" — domaine : {s.get('domaine','?')}"
        for i, s in enumerate(services[:20])
    ) or "  (liste non disponible)"

    prompt = f"""Tu es un analyste bancaire senior expert du marché ivoirien (UEMOA).
SGCI a {n_total} services identifiés comme EXCLUSIFS (absents de {_concurrents_txt()}) dont {n_grat} gratuits, segment {segment}.
La comparaison est sémantique (similarité ~72%) mais des erreurs restent possibles.

Services exclusifs candidats (extrait) :
{services_txt}

Ta DOUBLE mission :
1. VALIDER : Pour chaque service, est-ce VRAIMENT exclusif à SGCI ou un concurrent propose-t-il l'équivalent sous un nom différent ?
   - Si tu as un doute → signale [⚠ À VÉRIFIER] avec la raison ("BICICI a peut-être l'équivalent sous le nom X")
   - Si c'est clairement exclusif → [EXCLUSIF ✓]
2. EXPLIQUER (top 10 les plus stratégiques) : pourquoi SGCI est le SEUL à avoir ce service :
   - Héritage Société Générale Group (produit Groupe déployé localement) ?
   - Investissement technologique propre (plateforme propriétaire) ?
   - Positionnement segment (PME, Corporate, expats) ?
   - Partenariat exclusif ou agrément spécifique BCEAO ?

Format — liste numérotée 1 à 10 :
1. [NOM DU SERVICE] [EXCLUSIF ✓ / ⚠ À VÉRIFIER] — Exclusif car [raison précise]. Avantage concurrentiel : [bénéfice réel vs BICICI ou SIB].

Sois critique : ne valide pas un service comme exclusif si tu penses qu'un concurrent en a un équivalent. Cite des noms de banques concurrentes."""

    cache_key = f"q3_top10_v5_{segment}_{n_total}_{n_grat}"
    result = _groq_call_cb(prompt+_BOLD_INSTR, cache_key, max_tokens=800, prefer_claude=True)
    if result.get("analyse"):
        return jsonify({"analyse": result["analyse"], "source": result.get("source","groq")})
    return jsonify({"analyse": None, "error": result.get("error")}), 503


@app.route("/api/cb_q5_llm", methods=["POST"])
def api_cb_q5_llm():
    """Analyse LLM des gaps concurrentiels (Q5) — deux scopes : gaps et decision."""
    body        = request.get_json(force=True, silent=True) or {}
    segment     = (body.get("segment") or "Particuliers").strip()
    scope       = body.get("scope", "gaps")
    n_crit      = int(body.get("nCritiques") or 0)
    n_imp       = int(body.get("nImportants") or 0)
    n_total     = int(body.get("nTotal") or 0)
    n_grat_crit = int(body.get("nGratuitsCrit") or 0)
    top_gaps    = body.get("topGaps") or []
    combler     = body.get("combler") or []
    planifier   = body.get("planifier") or []

    gaps_txt = "\n".join(
        f"  {i+1}. {g.get('libelle','?')} "
        + (f"[GRATUIT chez {g.get('nb_banques',0)} banques]" if g.get("est_gratuit") else f"[{g.get('nb_banques',0)} banques]")
        + (f" — {g.get('banques','')}" if g.get("banques") else "")
        for i, g in enumerate(top_gaps[:8])
    ) or "  (aucun gap critique identifié)"

    bank_summary = body.get("bankSummary") or []
    bank_txt = "\n".join(
        f"  • {b.get('banque','?')} : {b.get('nGaps',0)} services absents chez SGCI dont {b.get('nGrat',0)} gratuits"
        for b in bank_summary
    ) or ""

    if scope == "gaps":
        prompt = f"""Tu es un analyste stratégique senior, banque SGCI sur le marché ivoirien (UEMOA).
SGCI présente {n_crit} gaps critiques (présents chez ≥3 banques concurrentes) dont {n_grat_crit} gratuits chez les concurrents, segment {segment}.
NB : la comparaison utilise une similarité sémantique (~72%) pour éviter les faux positifs liés aux variantes de noms.

Gaps critiques :
{gaps_txt}

Résumé par concurrent :
{bank_txt}

En 3 phrases nominatives et chiffrées :
1. Quel concurrent spécifique (parmi {_concurrents_txt()}) présente le plus fort avantage gap vs SGCI — combien de services uniques a-t-il, et comment en fait-il un argument commercial concret ?
2. Parmi les {n_grat_crit} gaps gratuits critiques, lesquels sont les plus visibles lors d'une comparaison — un client qui ouvre les tableaux de conditions bancaires de BICICI et SGCI côte à côte, que verra-t-il immédiatement ?
3. Si SGCI ne comble aucun de ces {n_crit} gaps dans 12 mois, quelle clientèle spécifique (segment, profil) risque de partir en premier vers quel concurrent ?"""
        cache_key = f"q5_gaps_v5_{segment}_{n_crit}_{n_imp}_{n_grat_crit}"
        max_tok = 500

    else:  # decision
        combler_txt  = ", ".join(combler[:3]) or "aucun identifié"
        planifier_txt = ", ".join(planifier[:3]) or "aucun identifié"
        prompt = f"""Tu es un directeur commercial bancaire, marché ivoirien (UEMOA).
SGCI doit gérer {n_total} gaps concurrentiels sur le segment {segment}. Matrice de priorité :
  - COMBLER (impact fort, coût faible) : {combler_txt}
  - PLANIFIER (impact fort, coût élevé) : {planifier_txt}

En 3 phrases précises et nominatives :
1. Par où commencer — quel gap spécifique SGCI doit-elle combler en priorité et dans quel délai réaliste (3 mois, 6 mois) pour ne pas perdre de clients face à BICICI ou SIB ?
2. Pour les gaps coûteux à combler, quelle réponse commerciale SGCI peut-elle donner immédiatement (communication, bundle, argument valeur) pour limiter l'impact pendant la phase de développement ?
3. Si ECOBANK ou NSIA accélère sur ces mêmes gaps dans les 6 prochains mois, quelle clientèle SGCI risque-t-elle de perdre en premier et sur quel segment ?"""
        cache_key = f"q5_dm_v4_{segment}_{n_crit}_{n_total}"
        max_tok = 480

    result = _groq_call_cb(prompt+_BOLD_INSTR, cache_key, max_tokens=max_tok, prefer_claude=True)
    if result.get("analyse"):
        return jsonify({"analyse": result["analyse"], "source": result.get("source", "groq")})
    return jsonify({"analyse": None, "error": result.get("error")}), 503


@app.route("/api/cb_q5_bank_llm", methods=["POST"])
def api_cb_q5_bank_llm():
    """Analyse LLM pour UNE banque spécifique en Q5 : ce que cette banque a que SGCI n'a pas."""
    body    = request.get_json(force=True, silent=True) or {}
    segment = (body.get("segment") or "Particuliers").strip()
    banque  = (body.get("banque") or "").strip()
    n_gaps  = int(body.get("nGaps") or 0)
    n_grat  = int(body.get("nGrat") or 0)
    gaps    = body.get("gaps") or []

    gaps_txt = "\n".join(
        f"  {i+1}. {g.get('libelle','?')} "
        + ("[GRATUIT chez " + banque + "]" if g.get("est_gratuit") else "[payant]")
        for i, g in enumerate(gaps[:15])
    ) or "  (liste non disponible)"

    prompt = f"""Tu es un analyste bancaire senior expert du marché ivoirien (UEMOA).
La banque {banque} propose {n_gaps} services sur le segment {segment} que SGCI ne propose PAS (ou pas sous un nom identifiable), dont {n_grat} gratuits.
La comparaison est sémantique (similarité ~72%) — certains peuvent être des services SGCI sous un nom différent.

Services de {banque} absents chez SGCI (extrait) :
{gaps_txt}

Ta DOUBLE mission — sois critique et nominatif :
1. VALIDER : Pour les 5 services les plus importants, est-ce que SGCI a VRAIMENT rien d'équivalent, ou a-t-elle peut-être un service similaire sous un nom différent ?
   - Si SGCI a probablement un équivalent → signale [⚠ SGCI a peut-être l'équivalent]
   - Si c'est un vrai manque → [MANQUE CONFIRMÉ ✓]

2. EXPLIQUER (top 5) : Pour chaque manque confirmé :
   a) Pourquoi {banque} propose ce service (stratégie commerciale, positionnement, partenariat) ?
   b) Pourquoi SGCI ne l'a pas (choix stratégique, coût, positionnement segment, délai de déploiement) ?
   c) Quel est le risque commercial concret pour SGCI si un client compare les deux offres ?

Format — liste numérotée 1 à 5 :
1. [NOM DU SERVICE] [MANQUE CONFIRMÉ ✓ / ⚠ SGCI a peut-être l'équivalent] — {banque} l'a car [raison]. SGCI ne l'a pas car [raison]. Risque : [impact commercial concret].

Termine par une question stratégique : SGCI devrait-elle prioritairement combler ce gap ou trouver un argument pour le contourner ?"""

    cache_key = f"q5_bank_v4_{segment}_{banque}_{n_gaps}_{n_grat}"
    result = _groq_call_cb(prompt+_BOLD_INSTR, cache_key, max_tokens=450, prefer_claude=True)
    if result.get("analyse"):
        return jsonify({"analyse": result["analyse"], "source": result.get("source", "groq")})
    return jsonify({"analyse": None, "error": result.get("error")}), 503


@app.route("/api/cb_q6_llm", methods=["POST"])
def api_cb_q6_llm():
    """Analyse LLM du benchmark prix (Q6) — deux scopes : price et strategy.
    Injecte les prix réels par section BCEAO pour des analyses non-génériques.
    """
    import hashlib as _hl
    body         = request.get_json(force=True, silent=True) or {}
    segment      = (body.get("segment") or "Particuliers").strip()
    annee        = str(body.get("year") or body.get("annee") or 2026)
    semestre     = (body.get("sem") or body.get("semestre") or "S1").strip()
    scope        = body.get("scope", "price")
    banks        = body.get("banks") or []
    # VALEURS DE REPLI SUPPRIMÉES (2026-07-30). Elles FABRIQUAIENT des faits concurrentiels
    # quand le front n'avait pas pu les calculer :
    #   sgciRang or 1        → affirmait que SGCI est PREMIÈRE du marché
    #   cheapestBank or "SIB"→ désignait SIB comme la moins chère
    #   costliestBank or "NSIA" → désignait NSIA comme la plus chère
    #   nBanks or 7          → figeait le marché à 7 banques, alors qu'une banque peut être ajoutée
    # Ces valeurs partaient telles quelles dans le prompt : le LLM produisait donc une analyse
    # concurrentielle nommant des banques sur la base d'un défaut de données, sans aucun signal.
    # Désormais : None/"" quand l'information est absente, et la phrase correspondante est omise
    # du prompt (cf. rang_txt plus bas). Une information manquante ne doit rien affirmer.
    sgci_rang    = int(body["sgciRang"]) if str(body.get("sgciRang") or "").strip().isdigit() else None
    n_banks      = int(body["nBanks"])   if str(body.get("nBanks")   or "").strip().isdigit() else None
    pct_cheap    = int(body.get("pctVsCheap") or 0)
    cheapest     = (body.get("cheapestBank") or "").strip()
    pct_costly   = int(body.get("pctVsCostly") or 0)
    costliest    = (body.get("costliestBank") or "").strip()
    # Phrase de rang : présente uniquement si rang ET effectif sont connus.
    rang_txt     = f"SGCI rang #{sgci_rang}/{n_banks}." if (sgci_rang and n_banks) else ""
    sgci_grat    = int(body.get("sgciPctGrat") or 0)
    sgci_nsvc         = int(body.get("sgciNSvc") or 0)
    excl_txt          = (body.get("excl_txt") or "").strip()
    gaps_txt2         = (body.get("gaps_txt") or "").strip()
    top_excl          = body.get("top_excl") or []  # [{libelle, montant, est_gratuit, axe_label}, ...]
    sgci_plus_cher    = (body.get("sgci_plus_cher") or "").strip()
    sgci_moins_cher   = (body.get("sgci_moins_cher") or "").strip()
    n_svcs_compares   = int(body.get("n_services_compares") or 0)

    # ── Données réelles par section BCEAO depuis la DB ─────────────────────────
    try:
        sec_data = AGENTS["CB"].structured.cb_par_section(int(annee), semestre, segment)
    except Exception:
        sec_data = []

    all_banks_ord = [b.get("banque","") for b in banks]
    def _fmt_fcfa(v):
        if v is None: return "—"
        if v == 0: return "Grat."
        return f"{int(v):,}".replace(",", " ") + " F"

    # Tableau section × banque
    rows_price = []
    wins_sgci, wins_conc = [], []
    for sec in sec_data:
        sgci_v = sec["banques"].get("SGCI", {}).get("montant_median")
        row = f"  {sec['roman']}. {sec['titre'][:40]:<40} | SGCI: {_fmt_fcfa(sgci_v):>12}"
        conc_vals = []
        for b in all_banks_ord:
            if b == "SGCI": continue
            v = sec["banques"].get(b, {}).get("montant_median")
            row += f"  {b}: {_fmt_fcfa(v):>12}"
            if sgci_v and v and sgci_v < v: conc_vals.append((b, v, "SGCI gagne"))
            elif sgci_v and v and sgci_v > v: conc_vals.append((b, v, f"{b} gagne"))
        rows_price.append(row)
        if sgci_v and conc_vals:
            all_cheaper = [c for c in conc_vals if "SGCI" in c[2]]
            all_costlier = [c for c in conc_vals if "gagne" in c[2] and "SGCI" not in c[2]]
            if len(all_cheaper) >= 3:
                wins_sgci.append(f"{sec['roman']}. {sec['titre'][:35]}")
            if len(all_costlier) >= 3:
                wins_conc.append(f"{sec['roman']}. {sec['titre'][:35]}")

    section_table = "\n".join(rows_price) or "  (données non disponibles)"

    # Top exclusivités SGCI avec prix réels
    excl_lines = ""
    if top_excl:
        excl_lines = "\n".join(
            f"  • {e.get('libelle','?')}"
            + (f" [GRATUIT]" if e.get("est_gratuit") else f" [{int(e.get('montant',0)):,} F]".replace(",", " ") if e.get("montant") else "")
            + (f" — {e.get('axe_label','')}" if e.get("axe_label") else "")
            for e in top_excl[:12]
        )

    banks_txt = "\n".join(
        f"  #{b.get('rang',i+1)}. {b.get('banque','?')} — {b.get('montant',0):,.0f} F moy. "
        + f"({b.get('n_services',0)} services, {int(b.get('pct_gratuit',0))}% gratuits)"
        for i, b in enumerate(banks[:7])
    ) or "  (données non disponibles)"

    if scope == "price":
        libelle_bloc = ""
        if sgci_plus_cher:
            libelle_bloc += f"\nSERVICES SGCI NETTEMENT PLUS CHERS QUE LE MARCHÉ (comparaison libellé exact) :\n"
            libelle_bloc += "\n".join(f"  • {s}" for s in sgci_plus_cher.split(" | ") if s)
        if sgci_moins_cher:
            libelle_bloc += f"\n\nSERVICES SGCI NETTEMENT MOINS CHERS QUE LE MARCHÉ (avantage compétitif réel) :\n"
            libelle_bloc += "\n".join(f"  • {s}" for s in sgci_moins_cher.split(" | ") if s)
        svcs_ctx = f"\n{n_svcs_compares} services comparés service par service (libellé → libellé).\n" if n_svcs_compares else ""

        prompt = f"""Tu es un analyste bancaire expert du marché ivoirien, segment {segment}.
ANNÉE DE RÉFÉRENCE STRICTE : {annee} {semestre}. Utilise UNIQUEMENT cette année dans ta réponse.

TARIFS MÉDIANS PAR CATÉGORIE BCEAO :
{section_table}
{svcs_ctx}{libelle_bloc}

{rang_txt} {f"{cheapest} est le moins cher (+{pct_cheap}% en faveur de {cheapest})." if (pct_cheap and cheapest) else ""}

RÈGLES : phrases AFFIRMATIVES, jamais de question. IGNORE toute valeur < 100 F (artefact
d'extraction) — ne cite jamais un tarif comme « 3 F » ou « 0,003 F ».

RÉPONDS EN 2 BLOCS COURTS (max 450 mots total) :

BLOC 1 — OÙ SGCI EST COMPÉTITIVE (cite 3 services ou catégories précis avec leurs tarifs réels) :
Pour chaque : "• [Nom exact du service] : SGCI [X F] vs médiane marché [Y F] → [verdict concis]"

BLOC 2 — OÙ SGCI EST VULNÉRABLE (cite 3 services ou catégories précis avec leurs tarifs réels) :
Pour chaque : "• [Nom exact du service] : SGCI [X F] vs [banque moins chère] [Y F] → [risque client concis]"

VERDICT FINAL (2 phrases AFFIRMATIVES max, chiffrées, sans aucune question) :
Affirme si SGCI est chère ou non et nomme le service où l'écart est le plus dangereux."""
        data_hash = _hl.md5((section_table+sgci_plus_cher+sgci_moins_cher+str(sgci_rang)).encode()).hexdigest()[:6]
        cache_key = f"q6_price_v8clr_{segment}_{annee}_{semestre}_{data_hash}"
        max_tok = 650

    else:  # strategy
        avantages_prix = sgci_moins_cher or ""
        vulnerabilites_prix = sgci_plus_cher or ""
        prompt = f"""Tu es directeur commercial de SGCI Côte d'Ivoire, segment {segment}.
ANNÉE DE RÉFÉRENCE STRICTE : {annee} {semestre}. Utilise UNIQUEMENT cette année dans ta réponse, jamais une autre.

POSITION PRIX (données réelles service par service) :
{rang_txt} {f"Concurrent le moins cher : {cheapest}." if cheapest else ""}
Catégories où SGCI gagne sur le prix : {', '.join(wins_sgci) or 'à vérifier'}
Catégories où SGCI est plus chère : {', '.join(wins_conc) or 'à vérifier'}
{f"Avantages prix concrets (libellé exact) : {avantages_prix}" if avantages_prix else ""}
{f"Vulnérabilités prix concrètes (libellé exact) : {vulnerabilites_prix}" if vulnerabilites_prix else ""}

EXCLUSIVITÉS SGCI CONFIRMÉES (produits réels absents chez les concurrents) :
{excl_lines or excl_txt or '(voir données Q3)'}

GAPS SGCI (services concurrents absents chez SGCI) :
{gaps_txt2 or '(voir données Q5)'}

GÉNÈRE 3 RECOMMANDATIONS STRATÉGIQUES PRÉCISES — avec des noms de produits réels et des chiffres :

ATTAQUER :
Sur quelles exclusivités ou avantages prix concrets SGCI doit-elle communiquer en priorité ?
→ Nomme 2-3 produits/services SGCI avec leurs tarifs réels (utilise les avantages prix ci-dessus si disponibles).

COMBLER :
Quel est le gap ou la vulnérabilité prix la plus dangereuse à adresser en priorité ?
→ Nomme le service, cite les chiffres réels, et l'impact si SGCI ne réagit pas.

COMMUNIQUER :
Quelle narrative tarifaire chiffrée SGCI doit-elle adopter pour retourner les écarts en avantage perçu ?
→ Propose un argument précis basé sur les données ci-dessus.

RÈGLES : réponses AFFIRMATIVES, chiffrées. IGNORE toute valeur < 100 F (artefact). Ne termine
PAS par une question — conclus par une phrase d'action."""
        data_hash2 = _hl.md5((excl_lines+gaps_txt2+avantages_prix+vulnerabilites_prix+str(sgci_rang)).encode()).hexdigest()[:6]
        cache_key = f"q6_strat_v7clr_{segment}_{annee}_{semestre}_{data_hash2}"
        max_tok = 800

    result = _groq_call_cb(prompt+_BOLD_INSTR, cache_key, max_tokens=max_tok, prefer_claude=True)
    if result.get("analyse"):
        return jsonify({"analyse": result["analyse"], "source": result.get("source", "groq")})
    return jsonify({"analyse": None, "error": result.get("error")}), 503


def _norm_lib_excl(s):
    """Normalisation canonique partagée (synonymes/pluriels unifiés) — voir cb_axes.canon_lib."""
    from cb_axes import canon_lib
    return canon_lib(s)


def _garde_vrai_exclusif(items, opposite_libelles, seuil=0.72):
    """GARDE-FOU FINAL (déterministe) : ne conserve QUE les items SANS équivalent dans le
    catalogue d'en face. Utilise la normalisation CANONIQUE (synonymes + pluriels unifiés),
    donc « tenue de compte » = « gestion de compte », « compte chèque » = « compte chèques ».
    Élimine les faux exclusifs/faux gaps dans les DEUX sens, pour TOUTES les banques.
    'exclusif c'est exclusif.'
    """
    from difflib import SequenceMatcher
    from cb_axes import canon_lib, canon_key
    opp      = list({canon_lib(l) for l in opposite_libelles if l})
    opp_keys = {canon_key(l) for l in opposite_libelles if l}
    kept = []
    for it in items:
        lib = it.get("libelle", "") if isinstance(it, dict) else str(it)
        n = canon_lib(lib)
        if not n:
            continue
        if canon_key(lib) in opp_keys:
            continue          # équivalent canonique EXACT en face → PAS exclusif
        if any(SequenceMatcher(None, n, o).ratio() >= seuil for o in opp):
            continue          # équivalent textuel proche en face → PAS exclusif
        kept.append(it)
    return kept


# Filtre CARTES : un « manque » de carte n'est PAS un vrai manque si SGCI a une carte
# du MÊME réseau + MÊME gamme, même nommée autrement (« Carte VISA PLATINUM » BACI vs
# « Première carte (VISA PLATINUM) » SGCI). Évite les faux manques de variantes de carte.
_CARD_NET  = {"visa", "mastercard", "gim"}
_CARD_TIER = {"classic", "gold", "premier", "premium", "platinum", "infinite",
              "horizon", "world", "elite", "business", "signature", "standard"}
def _card_sig(lib):
    import re as _r
    t = set(_r.findall(r"[a-zàâçéèêëîïôûü]+", (lib or "").lower().replace("platinium", "platinum")))
    if "carte" not in t and not (t & _CARD_NET):
        return None
    net, tier = t & _CARD_NET, t & _CARD_TIER
    return (net, tier) if (net or tier) else None

def _filtre_cartes_couvertes(items, opposite_libelles):
    """Retire les manques de carte dont SGCI possède l'équivalent (même réseau+gamme)."""
    opp_sigs = [s for s in (_card_sig(l) for l in opposite_libelles if l) if s]
    if not opp_sigs:
        return items
    def covered(sig):
        net, tier = sig
        for onet, otier in opp_sigs:
            if tier and (tier & otier) and (not net or (net & onet)):
                return True          # même gamme + réseau compatible → SGCI l'a
            if not tier and net and (net & onet):
                return True          # carte de marque (Balafon…) = même réseau générique
        return False
    out = []
    for it in items:
        lib = it.get("libelle", "") if isinstance(it, dict) else str(it)
        sig = _card_sig(lib)
        if sig and covered(sig):
            continue
        out.append(it)
    return out


import re as _re_pack
_PACK_RE = _re_pack.compile(r"\bpack(age)?s?\b|\bformule\b", _re_pack.IGNORECASE)
# Thématiques de niche que SGCI ne couvre par AUCUN pack (vérifié DB + web 2026-07-19) :
# un pack "Agripay Micro Farmer" reste un vrai manque même s'il contient le mot "pack",
# car ce n'est pas un compte packagé générique mais un produit agricole sectoriel absent chez SGCI.
_PACK_NICHE_RE = _re_pack.compile(r"agri|agricole|farmer|planteur|paysan|coop[eé]rativ", _re_pack.IGNORECASE)
def _filtre_packs_couverts(items, opposite_libelles):
    """Symétrique de _filtre_cartes_couvertes, pour les PACKS/FORMULES (2026-07-19, trouvé en
    miroir du fix Exclusivités : « Pack Elite Pro », « Pack Liberty Platinum »… chez un concurrent
    ne sont pas un vrai manque si SGCI a lui-même des packs/formules de marque (HORIZON, PREMIER,
    PRESTIBAD, BANQUE PATRIMONIALE…) — même principe universel de compte packagé/carte premium,
    juste un autre nom. Un manque de pack n'est réel que si SGCI n'a AUCUN pack du tout, OU si le
    pack cible une niche (agri…) que SGCI ne couvre par aucun de ses packs."""
    sgci_has_pack = any(_PACK_RE.search(l or "") for l in opposite_libelles)
    if not sgci_has_pack:
        return items
    out = []
    for it in items:
        lib = (it.get("libelle", "") if isinstance(it, dict) else str(it)) or ""
        if _PACK_RE.search(lib) and not _PACK_NICHE_RE.search(lib):
            continue
        out.append(it)
    return out


# ── Validation WEB des manques (agent web : run_veille_gaps.py → gaps_validation.json) ──
def _norm_lib_key(s):
    """Normalise une clé de libellé pour le matching gaps_validation : l'OCR/extraction produit
    tantôt une apostrophe droite (') tantôt courbe (') selon la banque/le PDF source — un
    mismatch silencieux ici fait qu'une validation écrite avec la "mauvaise" apostrophe ne
    s'applique jamais (bug trouvé le 2026-07-20). On plie les deux formes sur la droite."""
    return (s or "").strip().lower().replace("’", "'")

def _load_gaps_validation():
    import json as _j
    # Chemin corrigé le 2026-08-07 : visait dash_app/, le fichier est dans data/. Sans lui, la
    # validation web des manques d'offre était ignorée et les faux manques réapparaissaient.
    p = os.path.join(DOSSIER_DATA, "gaps_validation.json")
    try:
        raw = _j.load(open(p, encoding="utf-8")).get("services_auto", {})
        return {_norm_lib_key(k): v for k, v in raw.items()}
    except Exception:
        return {}

def _apply_gaps_validation(gaps, validation):
    """Pour chaque manque : si l'agent web a confirmé que SGCI l'A → on l'EXCLUT (faux manque) ;
    sinon on attache le RÔLE (« à quoi ça sert ») + la note sourcée pour l'affichage."""
    if not validation:
        return gaps
    out = []
    for g in gaps:
        lib = _norm_lib_key(g.get("libelle", "") if isinstance(g, dict) else str(g))
        v = validation.get(lib)
        if v:
            if v.get("sgci_a_equivalent"):
                continue   # validé web : SGCI possède l'équivalent → PAS un vrai manque
            if isinstance(g, dict):
                g = {**g, "web_role": v.get("role", ""), "web_note": v.get("note", ""),
                     "web_sources": (v.get("sources") or [])[:3], "web_ok": True}
        out.append(g)
    return out


# Bruit OCR / termes génériques qui ne sont PAS de vrais services distinctifs.
_EXCL_JUNK_EXACT = {"titulaire", "cotitulaire", "co titulaire", "deposit", "depot",
                    "gratuit", "sur demande", "neant", "ras", "autres", "divers",
                    "nous consulter", "voir conditions", "selon montant"}
import re as _re_excl
_EXCL_JUNK_START = _re_excl.compile(
    r"^(pour|par|de|du|des|y compris|dont|soit|au[- ]?dela|montant|cout|frais|a partir|jusqu)\b")

_GAP_NAME_JUNK_RE = _re_excl.compile(
    r"occurrence|param[eè]tre technique|pas un produit|→|\*\*|⚠|\bsgci a peut|"
    r"\b[eé]quivalent\b|inf[eé]rieur\s*[àa]|sup[eé]rieur\s*(ou\s*[eé]gal)?\s*[àa]|"
    r"^\d[\d\s]*(fcfa)?\s*(à|-|—)\s*\d|"          # pur palier de prix en tête ("10 000 001 à 50 000 FCFA")
    # 2026-07-20 (SIB « degeu ») — bruit d'extraction PDF récurrent, en plus des cas ci-dessus :
    r"^\d+[.,:]\s*\d|"                             # numérotation de section en tête ("2,2:29", "74,3", "1,119")
    r"^[«»\"']|"                                    # commence par un guillemet (fragment de citation coupé)
    r"\d[\d\s]*\s*(à|-|—)\s*\d+\s*$|"               # se termine par un palier de prix tronqué ("...500 000 à 30")
    r"\bwww\.|\.ci\b|actualis[eé]e? au|"            # mention/URL de site web (bavure de pied de page)
    r"\s(taux|frais|tarif)$|"                       # bavure d'en-tête de colonne en fin de libellé
    r"\d\s*/\s*$|"                                  # se termine par un chiffre suivi d'un slash ("18 000/")
    r"\bmontants?\s+indiqu[eé]s?\b|"                # phrase de pied de page ("Les montants indiqués...")
    r"^client\s+\w+$|"                              # fragment de citation nettoyé ("Client SIB")
    r":\s*\d[\d.,\s]*\d\s*$|:\s*\d\s*$|"            # tarif tronqué en fin de libellé ("Caution: 300", "Compte NSIA Banque (1) : 3 000")
    r"&lt;|&gt;",                                   # entité HTML non décodée (bavure d'extraction, ex. "Mont. Prêt &lt; 500.000")
    _re_excl.IGNORECASE,
)
def _looks_scrambled(name):
    """Détecte un libellé OCR éclaté lettre par lettre (ex. « C au o t m o m ris is »With) :
    si plus d'un tiers des tokens font 1-2 caractères, ce n'est pas du texte lisible."""
    toks = name.split()
    if len(toks) < 4:
        return False
    short = sum(1 for t in toks if len(t) <= 2)
    return (short / len(toks)) > 0.35


def _clean_gap_name(line):
    """Nettoie une ligne « • Nom — 5 mots » écrite par le LLM en un NOM DE PRODUIT propre.
    Bug trouvé le 2026-07-17 (relevé par le directeur, Manques « mélangé et dégueu ») : quand le
    LLM s'écarte du format strict (ex. variante du garde-fou « ⚠ SGCI a peut-être l'équivalent »),
    l'ancien code prenait TOUTE la ligne comme nom de produit — d'où des libellés du type
    « Mainlevée hypothèque → **Frais de main levée d'hypothèque SGCI** » affichés tels quels.
    Ici : on coupe au premier séparateur RÉEL (—, →, :, (⚠, [⚠) plutôt que seulement —/: , on
    retire le markdown, et on REJETTE (retourne None) tout nom qui contient encore un marqueur
    d'annotation interne après nettoyage (mieux vaut perdre un gap douteux qu'afficher un fragment)."""
    name = line.lstrip("•-").strip()
    # coupe au premier séparateur, quel qu'il soit (pas seulement — et :)
    cut = len(name)
    for sep in ("—", "→", "(⚠", "[⚠", "**"):
        idx = name.find(sep)
        if idx != -1:
            cut = min(cut, idx)
    name = name[:cut].strip().strip(":").strip()
    if not name or len(name) < 4:
        return None
    if _GAP_NAME_JUNK_RE.search(name) or _looks_scrambled(name):
        return None
    return name


# Qualificatifs qui CHANGENT le sens d'un montant : un plafond, un plancher ou une fourchette
# ne se lisent pas comme un prix ferme. Repérés sur la forme brute du tarif.
_RE_QUALIFICATIF = re.compile(
    r"(<=|>=|<|>|≤|≥|\bmax\b|\bmin\b|jusqu|a partir|à partir|minimum|maximum|plafond|"
    r"forfait|environ|par tranche|selon|negociable|négociable)", re.I)


def _valeur_qualifiee(it) -> str:
    """Valeur d'un tarif POUR UN PROMPT LLM, en conservant son qualificatif.

    BUG SIGNALÉ le 2026-07-28 par le directeur : l'analyse des exclusivités affirmait
    « SGCI propose une vraie exclusivité avec des 10 625 000 F de frais d'introduction en
    bourse », alors que la brochure dit « <= 10 625 000 Fcfa Forfait » — c'est un PLAFOND,
    pas un prix. Le LLM n'y est pour rien : le prompt ne lui transmettait que la colonne
    `montant` (un nombre nu, 10625000), en jetant `valeur_propre` qui porte le « <= ». Il a
    donc écrit exactement ce qu'on lui a donné.

    Un plafond présenté comme un prix ferme fausse tout raisonnement construit dessus
    (« quel est l'impact de ces 10 625 000 F sur la marge ? » n'a pas de sens sur un
    plafond), et c'est le genre de chiffre qui se retrouve ensuite dans une note au comité.
    On restitue donc la forme brute dès qu'elle contient un qualificatif, et on ne retombe
    sur le montant nu que lorsqu'il n'y a rien à préserver.
    """
    brute = (it.get("valeur_propre") or it.get("valeur_brute") or "").strip()
    if brute and _RE_QUALIFICATIF.search(brute):
        # Chiffres re-séparés par milliers pour rester lisibles ("10625000" → "10 625 000"),
        # le prompt exigeant déjà cette forme des nombres.
        lisible = re.sub(r"\d{4,}",
                          lambda m: f"{int(m.group(0)):,}".replace(",", " "), brute)
        return f" [{lisible[:60]}]"
    if it.get("est_gratuit"):
        return " [GRATUIT]"
    if it.get("type_valeur") == "TAUX_%" and it.get("montant"):
        return f" [{it['montant']}%]"      # un taux n'est pas un montant en FCFA
    if it.get("montant"):
        return f" [{int(it['montant']):,} F]".replace(",", " ")
    return ""


# La même ligne tarifaire est parfois classée sous un `section`/`contexte` différent selon le
# segment (ex. "Frais d'introduction en bourse" a un contexte rempli côté Particuliers mais vide
# côté Entreprises dans la grille SGCI) — sans ce repli, l'analyse LLM de l'un des deux segments
# reste vague faute de matière, alors que l'info existe juste à côté en base.
def _contexte_repli(banque: str, libelle: str) -> str:
    try:
        rows = db.query(
            "SELECT contexte FROM cb_tarifs WHERE banque=%s AND libelle=%s "
            "AND contexte IS NOT NULL AND TRIM(contexte) != '' LIMIT 1",
            (banque, libelle),
        )
        return (rows[0]["contexte"] if rows else "") or ""
    except Exception:
        return ""


# Un tarif isolé et un tarif qui fait partie d'une division entière ne racontent pas la même
# histoire — un LLM qui ne voit qu'UNE ligne ne peut que décrire cette ligne (d'où les analyses
# jugées vagues le 2026-07-29 : « capte seule les mandats liés à ce service »). On regroupe donc
# les AUTRES lignes de {banque} qui partagent le même `contexte` (le libellé de rubrique, ex.
# "Opérations du marché primaire") — PAS le même préfixe de `section` : testé sur ce cas précis,
# le code section "6.1" de SGCI regroupe par coïncidence deux rubriques sans rapport côté
# Entreprises (marché primaire ET change de devises), ce qui aurait produit une fausse parenté
# ("fait partie d'une gamme incluant l'achat de billets de banque en Euros" — faux). Le `contexte`
# est le seul champ qui porte le sens réel de la rubrique, indépendamment du numéro de section.
def _famille_siblings(banque: str, contexte: str, annee, semestre, libelle_exclu: str):
    contexte = (contexte or "").strip()
    if not contexte:
        return 0, []
    try:
        rows = db.query(
            "SELECT DISTINCT libelle FROM cb_tarifs WHERE banque=%s AND annee=%s AND semestre=%s "
            "AND LOWER(TRIM(contexte))=LOWER(TRIM(%s)) AND libelle != %s "
            "AND LENGTH(TRIM(libelle)) BETWEEN 8 AND 90 ORDER BY libelle LIMIT 4",
            (banque, annee, semestre, contexte, libelle_exclu),
        )
        n = db.query(
            "SELECT COUNT(DISTINCT libelle) AS n FROM cb_tarifs WHERE banque=%s AND annee=%s "
            "AND semestre=%s AND LOWER(TRIM(contexte))=LOWER(TRIM(%s)) AND libelle != %s",
            (banque, annee, semestre, contexte, libelle_exclu),
        )
        return (n[0]["n"] if n else 0), [r["libelle"] for r in rows]
    except Exception:
        return 0, []


def _filtre_bruit_excl(items):
    """Retire le bruit OCR/termes génériques d'une liste d'exclusifs ou de gaps
    (ex. 'Cotitulaire', 'Déposit', fragments) — sans toucher aux vrais produits."""
    import unicodedata as _ud
    out = []
    for it in items:
        lib = (it.get("libelle", "") if isinstance(it, dict) else str(it)).strip()
        low = "".join(c for c in _ud.normalize("NFD", lib.lower())
                      if _ud.category(c) != "Mn").strip(" .-•·")
        if len(lib) < 6:
            continue
        if low in _EXCL_JUNK_EXACT:
            continue
        if _EXCL_JUNK_START.match(low):
            continue
        # mot unique trop générique (un seul token, < 8 lettres) = pas un service nommé
        if low.count(" ") == 0 and len(low) < 8:
            continue
        out.append(it)
    return out


@app.route("/api/cb_exclusivites_axes", methods=["POST"])
def api_cb_exclusivites_axes():
    """
    Q3 v2 — Exclusivités SGCI validées par LLM, organisées par axe BCEAO.

    Approche :
      1. Récupère TOUS les libellés (y.c. section=NULL) via cb_libelles_tous().
      2. Pré-filtre Python (difflib) : élimine les libellés SGCI qui ont un
         équivalent textuel évident chez un concurrent.
      3. LLM : pour chaque axe non vide, valide sémantiquement les candidats.
         (ex. "Virement en FCFA" ≡ "Virement UEMOA" → non exclusif)
      4. Retourne les exclusivités confirmées organisées par axe.
    """
    import hashlib, re as _re, difflib as _difflib
    from cb_axes import AXES, AXE_COLORS, AXE_ICONS, classify_axe, prefilter_candidates, group_by_axe

    def _enrich_names(names, products):
        """Fuzzy-match LLM names back to product dicts to get contexte/montant."""
        by_lib = {p['libelle'].lower().strip(): p for p in products}
        libs = list(by_lib.keys())
        out, seen = [], set()
        for name in names:
            low = name.lower().strip()
            p = by_lib.get(low)
            if not p:
                m = _difflib.get_close_matches(low, libs, n=1, cutoff=0.55)
                p = by_lib[m[0]] if m else None
            lib = p['libelle'] if p else name
            if lib in seen: continue
            seen.add(lib)
            out.append({
                'libelle':     lib,
                'contexte':    (p.get('contexte') or '') if p else '',
                'montant':     (p.get('montant') or 0) if p else 0,
                'est_gratuit': bool(p.get('est_gratuit')) if p else False,
                'type_valeur': (p.get('type_valeur') or '') if p else '',
                'unite':       (p.get('unite') or '') if p else '',
            })
        return out

    _OCR_CONCAT = _re.compile(r'[a-zàâçéèêëîïôùûü][A-ZÀÂÇÉÈÊËÎÏÔÙÛÜ]')
    def _ocr_ok(p):
        lib = p.get("libelle", "")
        return not (len(lib) > 30 and _OCR_CONCAT.search(lib))

    body    = request.get_json(force=True, silent=True) or {}
    segment = (body.get("segment") or "Particuliers").strip()
    annee   = int(body.get("annee") or 2026)
    semestre = (body.get("semestre") or "S1").strip()
    banque  = (body.get("banque") or "SGCI").strip().upper()   # exclusivités de N'IMPORTE quelle banque

    _ckey = ("excl_webval4", banque, segment, annee, semestre)
    if _ckey in _EXCL_RESULT_CACHE:
        return jsonify(_EXCL_RESULT_CACHE[_ckey])
    import web_facts as _web_excl   # Agent Web : reclasse/retire les faux exclusifs

    # ── SOURCE UNIQUE D'EXCLUSIVITÉS (cohérence dashboard) ──────────────────────────
    # On dérive l'affichage de cb_exclusivites_banque — MÊME source/moteur que la Stratégie
    # (déjà classée par l'Agent Web : bruit retiré, verdicts). Fonctionne pour TOUTE banque.
    # On n'affiche pas les « partagé ». REPRODUCTIBLE : déterministe (DB + JSON sourcé).
    _rows = [r for r in (AGENTS["CB"].structured.cb_exclusivites_banque(banque, annee, semestre, segment) or [])
             if r.get("verdict") != "partage"]
    _byx = group_by_axe(_rows)
    _res = {str(i): {"axe_label": AXES[i], "color": AXE_COLORS[i], "icon": AXE_ICONS[i],
                     "exclusifs": _byx.get(i, []), "analyse": "", "n_candidats": len(_byx.get(i, []))}
            for i in range(1, 9)}

    # ── Habillage LLM (2026-07-16, corrigé 2026-07-17 — bug trouvé par le directeur) : la LISTE
    # reste 100% déterministe (fiabilité, web_facts déjà tranché "differenciant"/"non_contredit")
    # — seule la LECTURE STRATÉGIQUE par-dessus est confiée au LLM. BUG CORRIGÉ : le tri mettait
    # les items "differenciant" (juste un NOM de marque, PAS une vraie exclusivité de fonction —
    # ex. 5 produits qui partagent tous la même justification générique « packs de marque ») AVANT
    # les rares vrais "non_contredit" (aucun concurrent trouvé) — le LLM finissait par mélanger un
    # nom de marque et un vrai avantage unique dans la même phrase, comme s'ils avaient le même
    # poids → analyse incohérente. Corrigé : (1) non_contredit d'abord, (2) items "differenciant"
    # au verdict_note IDENTIQUE regroupés en UNE ligne (pas répétés individuellement).
    _analyse_llm = ""
    _uniques  = [r for r in _rows if r.get("verdict") == "non_contredit"]
    _marque   = [r for r in _rows if r.get("verdict") == "differenciant"]
    _uniques.sort(key=lambda r: r.get("montant") or 0, reverse=True)
    _marque_groups = {}
    for r in _marque:
        _marque_groups.setdefault((r.get("verdict_note") or "")[:120], []).append(r)
    if _uniques or _marque_groups:
        # UN SEUL produit passé au prompt (pas les 8 premiers) : quand la liste en montrait
        # plusieurs, le LLM ignorait la consigne « base-toi sur le premier uniquement » et
        # mélangeait un second produit/montant dans la phrase 2 (ex. « ... mais 20 000 F pour
        # les frais d'adhésion... ») malgré l'interdiction explicite. En ne montrant que le
        # produit réellement utilisé, l'erreur devient structurellement impossible plutôt que
        # seulement défendue par une consigne — un modèle ne peut pas citer ce qu'il ne voit pas.
        # Le `contexte` (ex. "Opérations du marché primaire") est ce qui rend l'analyse concrète
        # plutôt que du remplissage générique ("capte seule les mandats liés à ce service" —
        # jugé trop vague par le directeur, 2026-07-29) : sans lui, le LLM ne sait rien du
        # produit à part son nom et son prix, et ne peut donc QUE reformuler l'évidence.
        _top = _uniques[0] if _uniques else None
        _top_ctx = ""
        _famille_n, _famille_ex = 0, []
        if _top:
            _top_ctx = _top.get('contexte') or _contexte_repli(banque, _top.get('libelle', ''))
            _famille_n, _famille_ex = _famille_siblings(
                banque, _top_ctx, annee, semestre, _top.get('libelle', ''))
        _uniq_txt = "\n".join(
            f"  - {it.get('libelle','?')}"
            + _valeur_qualifiee(it)
            + (f" (rubrique : {_top_ctx})" if _top_ctx else "")
            + (f" — {(it.get('verdict_note') or '')[:140]}" if it.get('verdict_note') else "")
            + (f"\n    Fait partie d'un ensemble de {_famille_n} autres tarifs {banque} sous la "
               f"même rubrique, ex. : {', '.join(_famille_ex[:3])}." if _famille_n else "")
            for it in _uniques[:1]
        ) or "  (aucun — aucune exclusivité de fonction confirmée sur cette période)"
        _marque_txt = "\n".join(
            f"  - Groupe de {len(items)} produits ({', '.join(it.get('libelle','?') for it in items[:4])}"
            f"{'…' if len(items) > 4 else ''}) — {note or 'nom de marque, fonction universelle'}"
            for note, items in list(_marque_groups.items())[:6]
        ) or "  (aucun)"
        _prompt = f"""Tu es un analyste bancaire senior, marché ivoirien (UEMOA), segment {segment}.
Deux listes de produits {banque}, déjà validées par un agent web (absents des {_concurrents_txt()}) :

LISTE A — VRAIES EXCLUSIVITÉS (aucun concurrent trouvé proposant une fonction équivalente, pas juste un nom différent) :
{_uniq_txt}

LISTE B — NOMS DE MARQUE UNIQUEMENT (la FONCTION existe chez les concurrents sous un autre nom — PAS une vraie exclusivité, ne pas présenter comme un avantage concurrentiel) :
{_marque_txt}

En EXACTEMENT 2 phrases COURTES — ni 1, ni 3, ni une phrase de relance ou de conclusion ajoutée après la 2ᵉ — (max ~25 mots CHACUNE, sujet-verbe-complément, jamais deux idées reliées par une virgule ou un tiret), écrites pour un lecteur qui ne voit PAS ce prompt — n'utilise JAMAIS les mots « liste A », « liste B », « catégorie 1/2 » ou toute référence à cette structure interne ; parle directement des produits et de leur nature (vraie exclusivité vs simple nom de marque) :
1. Base-toi UNIQUEMENT sur le PREMIER produit de la liste A (le plus significatif, déjà trié en tête) pour identifier l'avantage concurrentiel réel de {banque} — cite ce produit exact. Si la liste A est vide, dis-le en une phrase courte et simple (ex. « SGCI n'a aucune vraie exclusivité de fonction sur ce marché. » — PAS « la catégorie 1 est vide ») plutôt que d'inventer un avantage à partir de la liste B.
2. Écris UNE phrase d'ANALYSE affirmative CONCRÈTE — INTERDIT la formule vague « permet de capter seule les mandats/clients liés à ce service » et INTERDIT aussi de te limiter à redire que c'est « un évènement rare » sans rien de plus (les deux jugées creuses : elles ne disent rien que la phrase 1 ne dise déjà). SI la note « Fait partie d'un ensemble de N autres tarifs {banque} sous la même rubrique » apparaît ci-dessus dans la liste A, base ta phrase LÀ-DESSUS en priorité : dis que ce produit n'est pas isolé mais fait partie d'une division/gamme structurée chez {banque} (cite 1 des exemples fournis, jamais un exemple que tu inventes), ce qui est un fait bien plus parlant qu'une généralité sur la rareté. SI cette note n'apparaît PAS (produit vraiment isolé), alors seulement, appuie-toi sur la rubrique/nature du produit pour dire ce qu'implique concrètement son caractère ponctuel ou récurrent. Exemple de bon niveau de précision quand une famille existe : « Ce forfait s'inscrit dans toute une gamme Marchés de Capitaux chez SGCI (structuration d'émissions, placement de titres, conservation), un pôle qu'aucun concurrent n'affiche. » (21 mots, se termine par un POINT). Adapte ce niveau de précision au produit réel de la phrase 1, sans y ajouter de clause supplémentaire même introduite par « mais », « jusqu'à ce que » ou « tant que ». TERMINE TOUJOURS PAR UN POINT — un point d'interrogation est INTERDIT ici, ce n'est pas une question. Base le raisonnement UNIQUEMENT sur le fait vérifié qu'aucun concurrent n'a été TROUVÉ dans les grilles tarifaires — INTERDIT d'inventer une raison technique/réglementaire à la difficulté de copier ce produit (« nécessite une infrastructure spécifique », « demande une expertise particulière »…) si elle n'est écrite NULLE PART ci-dessus, c'est aussi grave qu'inventer un chiffre. INTERDIT d'introduire un second produit, un second montant ou un second libellé différent de celui de la phrase 1 : une phrase = un seul produit du début à la fin. Si la liste A est vide, remplace cette phrase par UNE phrase affirmative simple sur le risque du naming (ex. « Un concurrent peut copier ce nom en quelques semaines. »), sans jamais dire « liste B ».
INTERDIT dans les 2 phrases : plus de 2 virgules par phrase, les tournures « ce qui interdit/empêche/implique que », les phrases à tiroirs avec plusieurs propositions enchaînées. Écris comme pour un SMS à un directeur pressé, pas comme un rapport juridique.
Commence directement. N'invente AUCUN chiffre hors de ceux ci-dessus, et recopie-les EXACTEMENT tels qu'écrits ci-dessus (espaces entre les milliers inclus, ex. "10 625 000 F" — jamais "10625000 F").
QUALIFICATIF OBLIGATOIRE : si un montant est précédé de « <= », « à partir de », « max », « forfait » ou tout autre qualificatif, GARDE-LE. Écris « jusqu'à 10 625 000 F » ou « plafonné à 10 625 000 F », JAMAIS « des 10 625 000 F ». Un plafond n'est pas un prix : le présenter comme un prix ferme rend fausse toute analyse construite dessus."""
        _items_hash = hashlib.md5((_uniq_txt + _marque_txt).encode()).hexdigest()[:8]
        _cache_key = f"q3_strat_v4_{banque}_{segment}_{_items_hash}"
        _result = _groq_call_cb(_prompt + _BOLD_INSTR, _cache_key, max_tokens=500, prefer_claude=True)
        _analyse_llm = _result.get("analyse") or ""
        # Filet de sécurité : malgré la consigne "EXACTEMENT 2 phrases", le LLM ajoute parfois
        # une 3e phrase de relance (souvent une question) — on la coupe plutôt que de compter
        # uniquement sur le respect du prompt, qui s'est montré peu fiable sur ce point précis.
        if _analyse_llm:
            _sents = re.split(r'(?<=[.!?])\s+', _analyse_llm.strip())
            _analyse_llm = " ".join(_sents[:2])
            # Même chose pour "termine toujours par un point" : la phrase 2 est une analyse
            # affirmative, pas une question, mais le LLM y revient régulièrement malgré la
            # consigne explicite — corrigé en dur plutôt que ré-espéré à chaque itération.
            if _analyse_llm.endswith("?"):
                _analyse_llm = _analyse_llm[:-1].rstrip() + "."

    _pl = {"axes": _res, "total_exclusifs": sum(len(v["exclusifs"]) for v in _res.values()),
           "banque": banque, "segment": segment, "annee": annee, "semestre": semestre,
           "n_sans_equivalent": sum(1 for r in _rows if r.get("verdict") == "non_contredit"),
           "n_differenciant":   sum(1 for r in _rows if r.get("verdict") == "differenciant"),
           "analyse_llm": _analyse_llm}
    _EXCL_RESULT_CACHE[_ckey] = _pl
    return jsonify(_pl)

    all_data = AGENTS["CB"].structured.cb_libelles_tous(annee, semestre, segment)
    if not all_data:
        return jsonify({"axes": {}, "error": "Aucune donnée"}), 404

    sgci_products    = [p for p in all_data.get("SGCI", []) if _ocr_ok(p)]
    other_banks      = {b: v for b, v in all_data.items() if b != "SGCI"}
    competitor_all   = [p for products in other_banks.values() for p in products if _ocr_ok(p)]

    # Pré-filtre : candidats SGCI sans équivalent textuel évident
    candidates = prefilter_candidates(sgci_products, competitor_all, cutoff=0.70)

    # Grouper les candidats par axe
    cand_by_axe = group_by_axe(candidates)
    comp_by_axe = group_by_axe(competitor_all)

    results = {}
    for axe_id in range(1, 9):
        axe_cands = cand_by_axe.get(axe_id, [])
        axe_comp  = comp_by_axe.get(axe_id, [])

        if not axe_cands:
            results[str(axe_id)] = {
                "axe_label": AXES[axe_id], "color": AXE_COLORS[axe_id],
                "icon": AXE_ICONS[axe_id], "exclusifs": [], "analyse": "",
                "n_candidats": 0,
            }
            continue

        # Formater pour le LLM
        cands_txt = "\n".join(
            f"  - {p['libelle']}"
            # _valeur_qualifiee : conserve « <= », « à partir de », « forfait »… au lieu de
            # n'envoyer que le nombre nu (cf. le bug du plafond 10 625 000 F du 2026-07-28).
            + _valeur_qualifiee(p)
            for p in axe_cands[:35]
        )
        # Compiler les libellés concurrents par banque pour contexte LLM
        comp_by_bank = {}
        for p in axe_comp:
            b = p["banque"]
            comp_by_bank.setdefault(b, []).append(p["libelle"])
        comp_txt = "\n".join(
            f"  {b}: " + " | ".join(items[:20])
            for b, items in sorted(comp_by_bank.items())
        ) or "  (aucun concurrent recensé dans cet axe)"

        hash_key  = hashlib.md5((cands_txt + comp_txt).encode()).hexdigest()[:8]
        cache_key = f"q3_axe{axe_id}_v3_{segment}_{hash_key}"

        prompt = f"""Tu es un analyste bancaire expert du marché ivoirien (UEMOA), segment {segment}.

AXE : {AXES[axe_id]}

Candidats SGCI (pré-filtrés, sans équivalent textuel évident chez les concurrents) :
{cands_txt}

Ce que les concurrents proposent dans cet axe :
{comp_txt}

MISSION : Valide quels produits SGCI sont VÉRITABLEMENT EXCLUSIFS (absents de toute banque concurrente, même sous un nom différent).

RÈGLES STRICTES :
✅ Cite un produit comme exclusif seulement s'il est fonctionnellement INTROUVABLE chez {_concurrents_txt()}
✅ Un produit nommé différemment mais fonctionnellement identique N'EST PAS exclusif (ex. "Virement FCFA" = "Virement UEMOA")
⚠️ Ajoute ⚠️ si un concurrent propose quelque chose de très proche

FORMAT :
EXCLUSIFS CONFIRMÉS :
• [Nom exact du produit] — [raison courte de l'exclusivité]
• …

SYNTHÈSE (2 phrases max) : Quel avantage concurrentiel cela représente-t-il pour SGCI dans cet axe ?"""

        result    = _groq_call_cb(prompt + _BOLD_INSTR, cache_key, max_tokens=700, prefer_claude=True)
        analyse   = result.get("analyse") or ""
        source    = result.get("source", "groq")
        if source == "groq":
            import time as _t; _t.sleep(2)  # respect RPM Groq entre axes

        # Extraire les exclusifs : d'abord entre "EXCLUSIFS CONFIRMÉS:" et "SYNTHÈSE"
        # Fallback : tous les "•" hors SYNTHÈSE si la section n'est pas trouvée
        exclusifs = []
        in_section = False
        in_synth   = False
        for line in analyse.splitlines():
            line = line.strip()
            up = line.upper()
            if "EXCLUSIFS" in up and ("CONFIRM" in up or ":" in line):
                in_section = True; in_synth = False
                continue
            if "SYNTH" in up:
                in_section = False; in_synth = True
                continue
            if in_section and (line.startswith("•") or line.startswith("-")):
                name_part = line.lstrip("•- ⚠").split("—")[0].split(":")[0].strip()
                if name_part and len(name_part) >= 4:
                    exclusifs.append(name_part)
        if not exclusifs and analyse:
            # Fallback : LLM n'a pas suivi le format — extraire tous les "•" hors SYNTHÈSE
            in_synth = False
            for line in analyse.splitlines():
                line = line.strip()
                if "SYNTH" in line.upper():
                    in_synth = True
                    continue
                if not in_synth and (line.startswith("•") or line.startswith("-")):
                    name_part = line.lstrip("•- ⚠").split("—")[0].split(":")[0].strip()
                    if name_part and len(name_part) >= 4:
                        exclusifs.append(name_part)

        # FALLBACK DÉTERMINISTE : si le LLM n'a rien renvoyé (indispo/disjoncteur),
        # on s'appuie sur les candidats pré-filtrés (déjà sans équivalent textuel ni
        # canonique chez les concurrents). Le garde-fou + filtre bruit les nettoient.
        # → les exclusivités s'affichent sur TOUTES les périodes, LLM ou non.
        names = exclusifs if exclusifs else [p["libelle"] for p in axe_cands]

        results[str(axe_id)] = {
            "axe_label": AXES[axe_id],
            "color":     AXE_COLORS[axe_id],
            "icon":      AXE_ICONS[axe_id],
            # Garde-fou final + VALIDATION AGENT WEB : retire le bruit, écarte les FAUX exclusifs
            # (fonction que des concurrents proposent aussi, ex. retrait sans carte → BNI/UBA/Ecobank),
            # et tague chaque item d'un verdict (non_contredit / differenciant) avec sources.
            "exclusifs": [c for c in _web_excl.classer_exclusivites(
                              _filtre_bruit_excl(_garde_vrai_exclusif(_enrich_names(names, axe_cands),
                                              [p["libelle"] for p in axe_comp])))
                          if c.get("verdict") != "partage"],
            "analyse":   analyse,
            "source":    source,
            "n_candidats": len(axe_cands),
        }

    total_exclusifs = sum(len(v["exclusifs"]) for v in results.values())
    payload = {
        "axes":           results,
        "total_exclusifs": total_exclusifs,
        "segment":        segment,
        "annee":          annee,
        "semestre":       semestre,
    }
    _EXCL_RESULT_CACHE[_ckey] = payload
    return jsonify(payload)


@app.route("/api/cb_gaps_axes", methods=["POST"])
def api_cb_gaps_axes():
    """
    Q5 v2 — Gaps d'une banque concurrente vs SGCI, validés par LLM par axe BCEAO.

    Approche identique à cb_exclusivites_axes mais côté concurrent :
    produits de {banque} absents chez SGCI → validés sémantiquement par LLM.
    """
    import hashlib, re as _re, difflib as _difflib
    from cb_axes import AXES, AXE_COLORS, AXE_ICONS, classify_axe, prefilter_gaps, group_by_axe

    def _enrich_names(names, products):
        by_lib = {p['libelle'].lower().strip(): p for p in products}
        libs = list(by_lib.keys())
        out, seen = [], set()
        for name in names:
            low = name.lower().strip()
            p = by_lib.get(low)
            if not p:
                m = _difflib.get_close_matches(low, libs, n=1, cutoff=0.55)
                p = by_lib[m[0]] if m else None
            lib = p['libelle'] if p else name
            if lib in seen: continue
            seen.add(lib)
            out.append({
                'libelle':     lib,
                'contexte':    (p.get('contexte') or '') if p else '',
                'montant':     (p.get('montant') or 0) if p else 0,
                'est_gratuit': bool(p.get('est_gratuit')) if p else False,
                'type_valeur': (p.get('type_valeur') or '') if p else '',
                'unite':       (p.get('unite') or '') if p else '',
            })
        return out

    _OCR_CONCAT = _re.compile(r'[a-zàâçéèêëîïôùûü][A-ZÀÂÇÉÈÊËÎÏÔÙÛÜ]')
    def _ocr_ok(p):
        lib = p.get("libelle", "")
        return not (len(lib) > 30 and _OCR_CONCAT.search(lib))

    body     = request.get_json(force=True, silent=True) or {}
    segment  = (body.get("segment") or "Particuliers").strip()
    annee    = int(body.get("annee") or 2026)
    semestre = (body.get("semestre") or "S1").strip()
    banque   = (body.get("banque") or "").strip()

    if not banque:
        return jsonify({"error": "Paramètre 'banque' manquant"}), 400

    _ckey = ("gaps", banque, segment, annee, semestre)
    if _ckey in _EXCL_RESULT_CACHE:
        return jsonify(_EXCL_RESULT_CACHE[_ckey])

    all_data = AGENTS["CB"].structured.cb_libelles_tous(annee, semestre, segment)
    if not all_data:
        return jsonify({"axes": {}, "error": "Aucune donnée"}), 404

    sgci_products = [p for p in all_data.get("SGCI", []) if _ocr_ok(p)]
    bank_products = [p for p in all_data.get(banque, []) if _ocr_ok(p)]

    if not bank_products:
        return jsonify({"axes": {}, "error": f"Aucune donnée pour {banque}"}), 404

    # Pré-filtre : produits de la banque sans équivalent évident chez SGCI
    candidates = prefilter_gaps(bank_products, sgci_products, cutoff=0.70)

    cand_by_axe = group_by_axe(candidates)
    sgci_by_axe = group_by_axe(sgci_products)

    _gaps_val = _load_gaps_validation()   # verdicts de l'agent web (run_veille_gaps.py)
    results = {}
    for axe_id in range(1, 9):
        axe_cands = cand_by_axe.get(axe_id, [])
        axe_sgci  = sgci_by_axe.get(axe_id, [])

        if not axe_cands:
            results[str(axe_id)] = {
                "axe_label": AXES[axe_id], "color": AXE_COLORS[axe_id],
                "icon": AXE_ICONS[axe_id], "gaps": [], "analyse": "",
                "n_candidats": 0,
            }
            continue

        cands_txt = "\n".join(
            f"  - {p['libelle']}"
            # _valeur_qualifiee : conserve « <= », « à partir de », « forfait »… au lieu de
            # n'envoyer que le nombre nu (cf. le bug du plafond 10 625 000 F du 2026-07-28).
            + _valeur_qualifiee(p)
            for p in axe_cands[:35]
        )
        sgci_txt = " | ".join(p["libelle"] for p in axe_sgci[:30]) or "(aucun)"

        hash_key  = hashlib.md5((cands_txt + sgci_txt + banque).encode()).hexdigest()[:8]
        cache_key = f"q5_axe{axe_id}_{banque}_v3_{segment}_{hash_key}"

        prompt = f"""Tu es un analyste bancaire expert du marché ivoirien (UEMOA), segment {segment}.

AXE : {AXES[axe_id]}

Produits de {banque} sans équivalent évident chez SGCI (pré-filtrés) :
{cands_txt}

Ce que SGCI propose dans cet axe :
{sgci_txt}

MISSION : Parmi ces produits de {banque}, lesquels représentent un VRAI manque chez SGCI (absent fonctionnellement, même sous un nom différent) ?

RÈGLES :
✅ Confirme un gap seulement si SGCI n'a VRAIMENT rien d'équivalent dans cet axe
✅ Si SGCI a un produit similaire sous un nom différent → signale [⚠ SGCI a peut-être l'équivalent]
✅ Sois critique : un virement générique n'est pas un gap si SGCI propose des virements

FORMAT :
GAPS CONFIRMÉS :
• [Nom exact du produit] — [5 mots max : ce que SGCI n'a pas]
• …

SYNTHÈSE RISQUE (2-3 phrases) : Ces gaps représentent-ils un VRAI danger pour SGCI sur cet axe ? SGCI est-elle globalement forte ou vulnérable ici ? Sur quels profils clients {banque} peut-elle vraiment mordre ?"""

        result  = _groq_call_cb(prompt + _BOLD_INSTR, cache_key, max_tokens=1000, prefer_claude=True)
        analyse = result.get("analyse") or ""
        if result.get("source") == "groq":
            import time as _t; _t.sleep(2)  # respect RPM Groq entre axes

        gaps = []
        in_gaps_section = False
        in_synth_g      = False
        for line in analyse.splitlines():
            line = line.strip()
            up = line.upper()
            if "GAPS" in up and ("CONFIRM" in up or ":" in line):
                in_gaps_section = True; in_synth_g = False
                continue
            if "SYNTH" in up:
                in_gaps_section = False; in_synth_g = True
                continue
            if in_gaps_section and (line.startswith("•") or line.startswith("-")):
                name_part = _clean_gap_name(line)
                if name_part:
                    gaps.append(name_part)
        if not gaps and analyse:
            in_synth_g = False
            for line in analyse.splitlines():
                line = line.strip()
                if "SYNTH" in line.upper():
                    in_synth_g = True
                    continue
                if not in_synth_g and (line.startswith("•") or line.startswith("-")):
                    name_part = _clean_gap_name(line)
                    if name_part:
                        gaps.append(name_part)

        # FALLBACK DÉTERMINISTE : LLM indispo/disjoncteur → on prend les candidats
        # pré-filtrés (services concurrents sans équivalent canonique chez SGCI). Même nettoyage
        # que la sortie LLM : un candidat pré-filtré peut lui aussi être un fragment de palier
        # tarifaire (ex. "Actif successoral inférieur à 100 000 FCFA") jamais un vrai produit.
        names_g = gaps if gaps else [p["libelle"] for p in axe_cands
                                      if not _GAP_NAME_JUNK_RE.search(p["libelle"]) and not _looks_scrambled(p["libelle"])]

        results[str(axe_id)] = {
            "axe_label":   AXES[axe_id],
            "color":       AXE_COLORS[axe_id],
            "icon":        AXE_ICONS[axe_id],
            # Garde-fou final : un gap (service concurrent absent de SGCI) ne doit avoir AUCUN
            # équivalent chez SGCI. Élimine les faux gaps (ex. 'Attestation bancaire pour VISA').
            # + filtre cartes (variantes que SGCI a déjà) + validation WEB (exclut les manques
            #   que l'agent web a confirmés présents chez SGCI, annote le rôle de chaque service).
            "gaps":        _apply_gaps_validation(
                               _filtre_packs_couverts(
                                   _filtre_cartes_couvertes(
                                       _filtre_bruit_excl(_garde_vrai_exclusif(_enrich_names(names_g, axe_cands),
                                                        [p["libelle"] for p in sgci_products])),
                                       [p["libelle"] for p in sgci_products]),
                                   [p["libelle"] for p in sgci_products]),
                               _gaps_val),
            "analyse":     analyse,
            "source":      result.get("source", "groq"),
            "n_candidats": len(axe_cands),
        }

    total_gaps = sum(len(v["gaps"]) for v in results.values())
    payload = {
        "axes":       results,
        "total_gaps": total_gaps,
        "banque":     banque,
        "segment":    segment,
    }
    _EXCL_RESULT_CACHE[_ckey] = payload
    return jsonify(payload)


@app.route("/api/cb_conclusion", methods=["POST"])
def api_cb_conclusion():
    """Conclusion stratégique globale — agrège Q3 (exclusivités) et Q5 (gaps par banque).
    Cache basé sur le hash des données → ne se recalcule qu'à l'ajout de nouvelles données.
    """
    import hashlib as _hl, json as _js
    body         = request.get_json(force=True, silent=True) or {}
    segment      = (body.get("segment") or "Particuliers").strip()
    annee        = str(body.get("annee") or 2026)
    semestre     = (body.get("semestre") or "S1").strip()
    excl_by_axe  = body.get("excl_by_axe") or {}   # {axe_label: count}
    gaps_by_bank = body.get("gaps_by_bank") or {}   # {banque: total_gaps}
    excl_total   = sum(excl_by_axe.values())

    data_str  = _js.dumps({"e": excl_by_axe, "g": gaps_by_bank}, sort_keys=True)
    hash_key  = _hl.md5(data_str.encode()).hexdigest()[:8]
    cache_key = f"conclusion_v2_{segment}_{annee}_{semestre}_{hash_key}"

    # Données section par section depuis la DB
    try:
        sec_data = AGENTS["CB"].structured.cb_par_section(int(annee), semestre, segment)
    except Exception:
        sec_data = []

    def _fmt(v):
        if v is None: return "—"
        if v == 0: return "Gratuit"
        return f"{int(v):,} F".replace(",", " ")

    # Sections où SGCI gagne (moins chère que la médiane des concurrents)
    sgci_wins, sgci_loses = [], []
    for sec in sec_data:
        sv = sec["banques"].get("SGCI", {}).get("montant_median")
        conc_vals = [b["montant_median"] for k, b in sec["banques"].items()
                     if k != "SGCI" and b.get("montant_median")]
        if not sv or not conc_vals: continue
        median_conc = sorted(conc_vals)[len(conc_vals)//2]
        if sv < median_conc * 0.9:
            sgci_wins.append(f"{sec['roman']}. {sec['titre']} (SGCI {_fmt(sv)} vs médiane conc. {_fmt(median_conc)})")
        elif sv > median_conc * 1.1:
            sgci_loses.append(f"{sec['roman']}. {sec['titre']} (SGCI {_fmt(sv)} vs médiane conc. {_fmt(median_conc)})")

    wins_txt  = "\n".join(f"  • {w}" for w in sgci_wins)  or "  (données insuffisantes)"
    loses_txt = "\n".join(f"  • {l}" for l in sgci_loses) or "  (données insuffisantes)"

    # Top exclusivités avec prix (passées par le frontend)
    top_excl_list = body.get("top_excl_list") or []
    excl_products_txt = "\n".join(
        f"  • {e.get('libelle','?')}"
        + (" [GRATUIT]" if e.get("est_gratuit") else
           f" [{int(e.get('montant',0)):,} F]".replace(",", " ") if e.get("montant") else "")
        + (f" — {e.get('axe_label','')}" if e.get("axe_label") else "")
        for e in top_excl_list[:15]
    ) or "\n".join(
        f"  • {axe} : {n} exclusivités"
        for axe, n in sorted(excl_by_axe.items(), key=lambda x: -x[1]) if n > 0
    ) or "  (aucune exclusivité confirmée)"

    gaps_txt = "\n".join(
        f"  • {bank} : {n} services présents chez eux mais absents chez SGCI"
        for bank, n in sorted(gaps_by_bank.items(), key=lambda x: -x[1])
    ) or "  (aucun gap identifié)"

    prompt = f"""Tu es un expert stratégique bancaire senior. Rédige un diagnostic complet de SGCI Côte d'Ivoire, segment {segment}.
ANNÉE DE RÉFÉRENCE STRICTE : {annee} {semestre}. Utilise UNIQUEMENT cette année dans ta réponse, jamais une autre.

PRIX RÉELS PAR CATÉGORIE BCEAO (médiane SGCI vs médiane concurrents) :
Catégories où SGCI est moins chère :
{wins_txt}
Catégories où SGCI est plus chère :
{loses_txt}

FORCES CONFIRMÉES — Exclusivités SGCI (produits absents chez tous les concurrents) :
{excl_products_txt}

FAIBLESSES — Services existant chez les concurrents mais absents chez SGCI :
{gaps_txt}

Rédige un diagnostic stratégique structuré en 4 sections, en citant des noms de produits et des montants réels :

💪 FORCES
Liste 5-6 avantages objectifs de SGCI. Pour chaque : le produit ou la catégorie, le chiffre clé, et l'argument commercial.

⚠ FAIBLESSES
Liste 4-5 points faibles réels. Pour chaque : le service manquant, quel concurrent l'a et à quel prix.

🚨 MENACES (classer par niveau de danger)
Pour chaque menace (fintechs, digital, concurrents spécifiques) :
- Niveau de danger : TRÈS ÉLEVÉ / ÉLEVÉ / MOYEN
- Sur quel terrain précis et quels clients sont à risque

🎯 CONCLUSION STRATÉGIQUE
3 phrases : SGCI est-elle en danger ? Son plus grand défi à 2 ans ? Son meilleur atout à défendre ?"""

    result = _groq_call_cb(prompt, cache_key, max_tokens=1100, prefer_claude=True)
    if result.get("analyse"):
        return jsonify({"analyse": result["analyse"], "source": result.get("source")})
    return jsonify({"analyse": None, "error": result.get("error")}), 503


# ══════════════════════════════════════════════════════════════════════
# AJOUT DE DONNÉES — upload d'un document → pipeline complète (async + aperçu)
#   1. /api/ajout/extraire : reçoit le fichier → extraction + nettoyage + APERÇU
#   2. /api/ajout/stocker  : confirme l'aperçu → INSERT CIBLÉ en base
#   Suivi de progression via /api/ajout/statut (jobs en arrière-plan).
#   Moteur : PIPELINE/ingest.py (sous-processus isolé, n'alourdit pas Flask).
# ══════════════════════════════════════════════════════════════════════
import uuid as _uuid, subprocess as _sub, threading as _th, tempfile as _tmp

_INGEST_SCRIPT = os.path.join(BACK_DIR, "PIPELINE", "ingest.py")
# En prod (image cloud allégée), PIPELINE/ingest.py n'est pas embarqué (dépendances lourdes
# d'extraction — docling/paddleocr/torch). Le bouton "Ajouter des données" est alors masqué
# côté front (/api/features) et les routes ci-dessous répondent une erreur claire plutôt
# que de tenter de lancer un script absent.
_INGEST_AVAILABLE = os.path.isfile(_INGEST_SCRIPT)
_JOBS = {}                       # job_id → {stage,status,result,log,type}
_JOBS_LOCK = _th.Lock()


@app.route("/api/features")
def api_features():
    return jsonify({"ingest_available": _INGEST_AVAILABLE, "chat_available": _RAG_OK})


def _run_ingest_job(job_id, args):
    """Exécute ingest.py et suit ses marqueurs @@STAGE / @@RESULT."""
    try:
        proc = _sub.Popen(
            [sys.executable, _INGEST_SCRIPT, *args],
            cwd=BACK_DIR, stdout=_sub.PIPE, stderr=_sub.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        res = None
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line.startswith("@@STAGE:"):
                with _JOBS_LOCK:
                    _JOBS[job_id]["stage"] = line[8:]
            elif line.startswith("@@RESULT:"):
                try:
                    res = json.loads(line[9:])
                except Exception:
                    res = {"ok": False, "message": "Réponse du moteur illisible."}
            elif line.strip():
                with _JOBS_LOCK:
                    _JOBS[job_id]["log"] = line[:300]
        proc.wait()
        with _JOBS_LOCK:
            if res is None:
                _JOBS[job_id].update(status="error",
                    result={"ok": False, "message": "Le traitement n'a pas abouti "
                                                    "(" + str(_JOBS[job_id].get("log") or "") + ")"})
            else:
                _JOBS[job_id].update(status=("done" if res.get("ok") else "error"), result=res)
                # Ajout réussi → recharge la liste des banques (données de base, PAS de LLM) pour que
                # la nouvelle banque/période soit immédiatement sélectionnable. VOLONTAIREMENT, on ne
                # touche PLUS ici aux caches d'analyses LLM (EF/Stratégie) : « Ajouter des données »
                # stocke, un clic explicite sur « Rafraîchir les analyses » (bouton dédié, avec
                # confirmation) déclenche la régénération LLM — cf. _refresh_analyses_now().
                if res.get("ok") and "store" in args:
                    try:
                        db.refresh_banks()
                    except Exception as _e:
                        print(f"[ajout] refresh_banks post-store: {_e}")
                    # Même chose côté chat (RAG/config.py) : sans cet appel, une banque tout
                    # juste ajoutée n'apparaissait dans les comparaisons du chat (ROE, PNB...)
                    # qu'après un redémarrage MANUEL du process — impraticable une fois
                    # déployé (pas d'accès serveur direct pour un utilisateur non technique).
                    try:
                        import config as _rag_config
                        _rag_config.refresh_banques_officielles()
                        _rag_config.refresh_etats_financiers_annees()
                        _rag_config.refresh_banque_aliases()
                    except Exception as _e:
                        print(f"[ajout] refresh_banques_officielles/annees_ef/aliases post-store: {_e}")
                    # Socle de faits du chat (2026-07-27) : la fiche marché est mise en cache
                    # 10 minutes pour ne pas refaire ~35 requêtes SQL à chaque question. Sans
                    # cette invalidation, une banque ou un exercice tout juste ajouté resterait
                    # absent des classements du chat pendant ce délai — exactement le décalage
                    # entre dashboard et chat que ce socle est censé supprimer.
                    try:
                        import fiche_marche as _rag_fiche
                        _rag_fiche.invalider()
                    except Exception as _e:
                        print(f"[ajout] invalidation fiche marché post-store: {_e}")
                    # CACHES MÉMOIRE DU SERVEUR (2026-07-30) — dernier trou de la chaîne de
                    # rafraîchissement. `db.refresh_banks()` vide bien les 34 @lru_cache de db.py,
                    # mais ces trois dictionnaires vivent dans server.py et n'étaient jamais
                    # purgés : après un ajout de données, l'onglet Stratégie, le tableau de
                    # repricing et les exclusivités continuaient de servir les résultats calculés
                    # sur les ANCIENNES données jusqu'au prochain redémarrage du process — sans
                    # aucun signal pour l'utilisateur, qui croyait voir ses nouvelles données.
                    for _nom, _c in (("_STRAT_CACHE", _STRAT_CACHE),
                                     ("_REPRICING_CACHE", _REPRICING_CACHE),
                                     ("_EXCL_RESULT_CACHE", _EXCL_RESULT_CACHE)):
                        try:
                            _n = len(_c)
                            _c.clear()
                            print(f"[ajout] {_nom} vidé ({_n} entrée(s))")
                        except Exception as _e:
                            print(f"[ajout] purge {_nom}: {_e}")
                    # Titres de section CB (chargés une fois par process, cf.
                    # retriever._charger_sections_cb) : ils servent à reconstruire le chemin
                    # « Successions > Frais de tenue de compte » qui donne son sens à chaque
                    # ligne tarifaire. Sans invalidation, les lignes d'une banque nouvellement
                    # ajoutée seraient servies SANS leur rubrique jusqu'au prochain redémarrage.
                    try:
                        import retriever as _rag_retriever
                        _rag_retriever.invalider_sections_cb()
                    except Exception as _e:
                        print(f"[ajout] invalidation sections CB post-store: {_e}")
    except Exception as e:
        with _JOBS_LOCK:
            _JOBS[job_id].update(status="error", result={"ok": False, "message": str(e)[:300]})


def _new_job(typ):
    jid = _uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _JOBS[jid] = {"stage": "En file d'attente", "status": "running",
                      "result": None, "log": None, "type": typ}
    return jid


# ══════════════════════════════════════════════════════════════════════════════
#  DÉTECTION DE NOUVELLES DONNÉES — signature légère (count + max id) par table.
#  Sert à n'autoriser « Rafraîchir les analyses » QUE s'il y a réellement du neuf
#  depuis le dernier rafraîchissement (évite de gaspiller le quota LLM pour rien).
# ══════════════════════════════════════════════════════════════════════════════
_REFRESH_STATE_FILE = os.path.join(DOSSIER_CACHE, "refresh_state.json")


def _refresh_state_load():
    try:
        with open(_REFRESH_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _refresh_state_save(state):
    try:
        with open(_REFRESH_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[refresh_state] persist:", e)


def _table_signature(table):
    try:
        rows = db.query(f"SELECT COUNT(*) AS n, COALESCE(MAX(id),0) AS max_id FROM {table}")
        r = rows[0] if rows else {}
        return {"count": r.get("n", 0), "max_id": r.get("max_id", 0)}
    except Exception as e:
        print(f"[refresh_state] signature {table}:", e)
        return {"count": 0, "max_id": 0}


def _current_signatures():
    return {"ef": _table_signature("ef_indicateurs"), "cb": _table_signature("cb_tarifs")}


def _has_new_data(section):
    """True si les données pertinentes pour `section` ont changé depuis le dernier rafraîchissement
    RÉUSSI de cette section (jamais rafraîchi → considéré comme neuf, pour établir une 1ʳᵉ référence)."""
    cur = _current_signatures()
    state = _refresh_state_load()
    keys = {"ef": ["ef"], "cb": ["cb"], "strategie": ["ef", "cb"]}.get(section, ["ef", "cb"])
    changed = False
    for k in keys:
        old = state.get(k)
        if not old or old != cur.get(k):
            changed = True
    return changed, cur


@app.route("/api/rafraichir_check")
def api_rafraichir_check():
    """Vérifie s'il y a de nouvelles données pour la section demandée AVANT de proposer le
    rafraîchissement — le front n'affiche le bouton de confirmation (rouge) QUE si has_new_data."""
    section = (request.args.get("section") or "strategie").lower()
    has_new, cur = _has_new_data(section)
    return jsonify({"has_new_data": has_new, "section": section})


def _refresh_analyses_job(job_id, section):
    """« Rafraîchir les analyses » — SEUL déclencheur de la régénération LLM (« Ajouter des
    données » ne fait que stocker, cf. _run_ingest_job). NON DESTRUCTIF par construction :
    - EF (clé fixe par segment/anx, PAS de hash) : on tente la régénération, et en cas d'échec
      on RESTAURE l'ancienne analyse (jamais de trou, jamais de perte).
    - Stratégie (clés à HASH des faits) : on force juste la reconstruction du dossier de FAITS
      (déterministe, sans LLM, sans risque) ; si le hash change, une régénération LLM est tentée
      et un ÉCHEC retombe automatiquement sur la dernière version connue (filet ajouté dans
      strategie_narr/narr2/narr3 et _analyse_llm_cached) — on ne supprime jamais l'ancien cache.
    - CB (clés signées par les faits déjà) : s'auto-régénère à la consultation dès qu'une donnée
      change ; rien à purger ici (purge = perte inutile du filet de sécurité)."""
    import time as _t
    def _stage(s):
        with _JOBS_LOCK:
            _JOBS[job_id]["stage"] = s

    _stage("Rechargement des banques…")
    try:
        db.refresh_banks()
    except Exception as e:
        print(f"[refresh] refresh_banks: {e}")

    # Les directives sont calculées à partir de la base : de nouvelles données les changent.
    # Sans ce vidage, l'écran « Stratégie opérationnelle » aurait continué de servir les cartes
    # d'avant l'ingestion, indéfiniment et sans le dire — le défaut même que le cache de
    # Stratégie avait connu et qu'on avait mis une semaine à voir. Le fichier disque doit
    # partir avec la mémoire, sinon il ressusciterait l'ancienne version au redémarrage.
    _SO_DIRECTIVES.clear()
    _stratop_vider()

    client = app.test_client()
    warmed, failed = [], []

    if section in ("strategie",):
        for seg in ("Particuliers", "Entreprises"):
            _STRAT_CACHE.pop(seg, None)   # force la RECONSTRUCTION DES FAITS (déterministe, 0 risque LLM)
            _stage(f"Reconstruction du dossier Stratégie — {seg}…")
            # NOTE (2026-07-22, audit robustesse) : 4 endpoints ajoutés le 2026-07-16/21 (coûts de
            # changement, projection, roadmap, diagnostic) manquaient ici — sans purge/hash-miss
            # proactif, un rafraîchissement manuel ne les régénérait qu'à la prochaine visite de la
            # page (lazy), pas immédiatement comme les autres. Alignés sur le même traitement.
            for path in (f"/api/strategie_narr2?segment={seg}", f"/api/strategie_narr3?segment={seg}",
                         f"/api/strategie_narr?segment={seg}", f"/api/pestel_analyse?segment={seg}",
                         f"/api/vrist_analyse?segment={seg}", f"/api/strategie_llm?segment={seg}",
                         f"/api/strategie_diag_llm?segment={seg}", f"/api/strategie_switch_llm?segment={seg}",
                         f"/api/strategie_projection_llm?segment={seg}", f"/api/strategie_roadmap_llm?segment={seg}"):
                try:
                    r = client.get(path)
                    (warmed if r.status_code == 200 else failed).append(path)
                except Exception:
                    failed.append(path)
                _t.sleep(2)   # laisse respirer le TPM Groq entre deux gros appels

    if section in ("ef",):
        # IMPORTANT : la fenêtre AN1/AN2/AN3 est PROPRE À CHAQUE BANQUE (ses 3 dernières années
        # disponibles, cf. kpis_vue_ensemble) — ajouter UNE SEULE année pour UNE SEULE banque
        # (ex. « BACI 2024 », « BICICI 2026 ») décale la fenêtre de CETTE banque uniquement, sans
        # toucher aux autres. La clé de cache EF n'est PAS un hash des faits (contrairement à la
        # Stratégie) → chaque combinaison (segment, anx=1/2/3) DÉJÀ CONSULTÉE doit être régénérée
        # explicitement ici, sinon elle reste figée pour toujours (bug corrigé le 2026-07-08 :
        # seul anx=3 était rafraîchi, anx=1/2 restaient gelés même après un rafraîchissement réussi).
        cache = _ef_cache()
        for seg in ("Particuliers", "Entreprises"):
            for anx in (1, 2, 3):
                key = f"ef_v38_{seg}_{anx}"
                if anx != 3 and key not in cache:
                    continue   # personne n'a jamais consulté cette vue → rien à rafraîchir, on économise le quota
                old = cache.get(key)
                old_meta = dict(cache.get(_meta_key(key)) or {})
                if key in cache:
                    del cache[key]   # force la régénération SANS jeter `old` (gardé en mémoire locale)
                _stage(f"Analyses Santé Financière — {seg} (Année {anx})…")
                ok = False
                try:
                    r = client.get(f"/api/ef_analyses_llm?segment={seg}&anx={anx}")
                    j = r.get_json(silent=True) or {}
                    ok = bool(j.get("analyses"))
                except Exception:
                    ok = False
                if ok:
                    warmed.append(f"ef:{seg}:{anx}")
                else:
                    failed.append(f"ef:{seg}:{anx}")
                    if old:   # ÉCHEC → on restaure l'ancienne analyse (jamais de perte, jamais de trou)
                        cache[key] = old
                        # Marque explicitement « obsolète » : garde SA date de génération d'origine
                        # (le contenu n'est pas neuf), pas la date de cette tentative échouée.
                        old_meta["stale"] = True
                        cache[_meta_key(key)] = old_meta
                        try:
                            with open(_EF_LLM_CACHE_FILE, "w", encoding="utf-8") as f:
                                json.dump(cache, f, ensure_ascii=False, indent=2)
                        except Exception as e:
                            print("[refresh] ef restore persist:", e)
                _t.sleep(2)

    if section in ("cb",):
        # La plupart des clés CB sont déjà signées par les faits (rang, win-rate…) → une donnée
        # qui change produit automatiquement une clé neuve à la prochaine consultation — pas
        # besoin d'y toucher (le filet de sécurité resterait sinon détruit pour rien).
        # MAIS deux caches CB sont keyés PAR PARAMÈTRES SEULS (banque/segment/année/semestre ou
        # service), PAS par un hash des données : une correction de valeur pour les MÊMES
        # paramètres ne serait jamais reprise sans purge explicite. Corrigé le 2026-07-08 :
        _EXCL_RESULT_CACHE.clear()        # exclusivités/gaps validés (axes BCEAO)
        _REPRICING_CACHE.clear()          # verdicts de repricing par service
        try:
            if os.path.exists(_REPRICING_CACHE_FILE):
                os.remove(_REPRICING_CACHE_FILE)
        except Exception:
            pass
        warmed.append("cb:auto+purge exclusivités/repricing")

    state = _refresh_state_load()
    _, cur = _has_new_data(section)
    if section in ("ef", "strategie"):
        state["ef"] = cur["ef"]
    if section in ("cb", "strategie"):
        state["cb"] = cur["cb"]
    _refresh_state_save(state)

    with _JOBS_LOCK:
        _JOBS[job_id].update(status="done", stage="Terminé",
                              result={"ok": True, "warmed": len(warmed), "failed": failed})


@app.route("/api/rafraichir_analyses", methods=["POST"])
def api_rafraichir_analyses():
    """Déclenche le rafraîchissement LLM (job async) — appelé UNIQUEMENT depuis le bouton dédié
    « Rafraîchir les analyses », après confirmation côté front. `section` = ef|cb|strategie.
    Poll via /api/ajout/statut?job=… (même infra que l'ingestion)."""
    section = (request.args.get("section") or "strategie").lower()
    if section not in ("ef", "cb", "strategie"):
        section = "strategie"
    jid = _new_job("refresh")
    _th.Thread(target=_refresh_analyses_job, args=(jid, section), daemon=True).start()
    return jsonify({"ok": True, "job": jid})


# Banques de Côte d'Ivoire au registre UEMOA/BCEAO (hors les 7 déjà suivies). Sert à
# proposer une LISTE DÉROULANTE pour ajouter une nouvelle banque (pas de saisie libre).
_UEMOA_BANKS_CI = [
    ("BOA",      "Bank of Africa — Côte d'Ivoire"),
    ("CORIS",    "Coris Bank International"),
    ("ORABANK",  "Orabank Côte d'Ivoire"),
    ("UBACI",    "United Bank for Africa (UBA Côte d'Ivoire)"),
    ("CITI",     "Citibank Côte d'Ivoire"),
    ("SCBCI",    "Standard Chartered Bank Côte d'Ivoire"),
    ("BGFI",     "BGFIBank Côte d'Ivoire"),
    ("STANBIC",  "Stanbic Bank Côte d'Ivoire"),
    ("BRIDGE",   "Bridge Bank Group Côte d'Ivoire"),
    ("BSIC",     "BSIC Côte d'Ivoire (Banque Sahélo-Saharienne)"),
    ("BPCI",     "Banque Populaire de Côte d'Ivoire"),
    ("VERSUS",   "Versus Bank"),
    ("BHCI",     "Banque de l'Habitat de Côte d'Ivoire"),
    ("MANSA",    "Mansa Bank"),
    ("GTBANK",   "GTBank Côte d'Ivoire"),
    ("AFRILAND", "Afriland First Bank Côte d'Ivoire"),
    ("ACCESS",   "Access Bank Côte d'Ivoire"),
    ("BDA",      "Banque d'Abidjan"),
]


@app.route("/api/ajout/banques")
def ajout_banques():
    """Banques en base (sélecteur) + banques UEMOA NON encore suivies (liste « nouvelle banque »)."""
    try:
        rows = db.query("SELECT code, nom_complet, groupe FROM banques ORDER BY code")
    except Exception:
        rows = []
    existants = {(r.get("code") or "").upper() for r in rows}
    # nouvelles = banques UEMOA/CI absentes de la base, par nom
    nouvelles = [{"code": c, "nom_complet": n} for c, n in _UEMOA_BANKS_CI
                 if c.upper() not in existants]
    nouvelles.sort(key=lambda b: b["nom_complet"])
    return jsonify({"banques": rows, "nouvelles": nouvelles})


@app.route("/api/ajout/prochaine_periode")
def ajout_prochaine_periode():
    """Détection dynamique de la prochaine période à ajouter (CB semestriel / EF annuel)."""
    import datetime
    typ = (request.args.get("type") or "CB").upper()
    banque = (request.args.get("banque") or "").upper().strip()
    seg = request.args.get("segment", "Particuliers")
    # L'analyse a DÉMARRÉ à 2024 → toute banque sans donnée commence à 2024 (S1 pour CB).
    cur_year = 2024
    try:
        if typ == "CB" and banque:
            rows = db.query(
                "SELECT annee, semestre FROM cb_tarifs WHERE banque=%s AND segment=%s "
                "ORDER BY annee DESC, semestre DESC LIMIT 1", (banque, seg))
            if rows:
                y = int(rows[0]["annee"]); s = (rows[0]["semestre"] or "S1").upper()
                if s == "S1":
                    return jsonify({"annee": y, "semestre": "S2", "existant": f"{y} S1"})
                return jsonify({"annee": y + 1, "semestre": "S1", "existant": f"{y} S2"})
            return jsonify({"annee": cur_year, "semestre": "S1", "existant": None})
        if typ == "EF" and banque:
            rows = db.query("SELECT MAX(annee_donnee) AS y FROM ef_indicateurs WHERE banque=%s",
                            (banque,))
            if rows and rows[0]["y"]:
                return jsonify({"annee": int(rows[0]["y"]) + 1, "semestre": None,
                                "existant": str(rows[0]["y"])})
            return jsonify({"annee": cur_year, "semestre": None, "existant": None})
    except Exception as e:
        print(f"[ajout] prochaine_periode err: {e}")
    return jsonify({"annee": cur_year, "semestre": "S1" if typ == "CB" else None, "existant": None})


@app.route("/api/ajout/extraire", methods=["POST"])
def ajout_extraire():
    """Reçoit le document + métadonnées → lance extraction+nettoyage+aperçu (async)."""
    if not _INGEST_AVAILABLE:
        return jsonify({"ok": False, "message": "Ajout de données indisponible sur cet environnement (pipeline d'extraction non installé ici). Utilisez un poste local avec le pipeline complet."}), 503
    f = request.files.get("fichier")
    if not f or not f.filename:
        return jsonify({"ok": False, "message": "Aucun fichier fourni."}), 400
    typ = (request.form.get("type") or "CB").upper()
    banque = (request.form.get("banque") or "").upper().strip()
    annee = (request.form.get("annee") or "").strip()
    semestre = (request.form.get("semestre") or "S1").upper()
    segment = request.form.get("segment", "Particuliers")
    if typ in ("CB", "EF") and not banque:
        return jsonify({"ok": False, "message": "La banque est obligatoire pour CB et EF."}), 400
    if typ in ("CB", "EF") and not annee:
        return jsonify({"ok": False, "message": "L'année est obligatoire."}), 400

    ext = os.path.splitext(f.filename)[1].lower() or ".pdf"
    up_dir = os.path.join(_tmp.gettempdir(), "spybiz_uploads")
    os.makedirs(up_dir, exist_ok=True)
    tmp_path = os.path.join(up_dir, _uuid.uuid4().hex + ext)
    f.save(tmp_path)

    args = ["--mode", "extract", "--type", typ, "--fichier", tmp_path]
    if banque:
        args += ["--banque", banque]
    if annee:
        args += ["--annee", annee]
    if typ == "CB":
        args += ["--semestre", semestre, "--segment", segment]
    nom = (request.form.get("banque_nom") or "").strip()
    grp = (request.form.get("banque_groupe") or "").strip()
    if nom:
        args += ["--banque-nom", nom]
    if grp:
        args += ["--banque-groupe", grp]

    jid = _new_job(typ)
    _th.Thread(target=_run_ingest_job, args=(jid, args), daemon=True).start()
    return jsonify({"ok": True, "job": jid})


@app.route("/api/ajout/stocker", methods=["POST"])
def ajout_stocker():
    """Confirme l'aperçu validé → stockage ciblé en base (async)."""
    if not _INGEST_AVAILABLE:
        return jsonify({"ok": False, "message": "Ajout de données indisponible sur cet environnement (pipeline d'extraction non installé ici). Utilisez un poste local avec le pipeline complet."}), 503
    b = request.get_json(force=True, silent=True) or {}
    typ = (b.get("type") or "CB").upper()
    banque = (b.get("banque") or "").upper().strip()
    annee = str(b.get("annee") or "").strip()
    semestre = (b.get("semestre") or "S1").upper()
    segment = b.get("segment", "Particuliers")
    stem = (b.get("stem") or "").strip()

    args = ["--mode", "store", "--type", typ]
    if banque:
        args += ["--banque", banque]
    if annee:
        args += ["--annee", annee]
    if stem:
        args += ["--stem", stem]
    if typ == "CB":
        args += ["--semestre", semestre, "--segment", segment]
    if b.get("banque_nom"):
        args += ["--banque-nom", str(b["banque_nom"])]
    if b.get("banque_groupe"):
        args += ["--banque-groupe", str(b["banque_groupe"])]

    jid = _new_job(typ)
    _th.Thread(target=_run_ingest_job, args=(jid, args), daemon=True).start()
    return jsonify({"ok": True, "job": jid})


@app.route("/api/ajout/statut")
def ajout_statut():
    """Suivi de progression d'un job d'ingestion."""
    jid = request.args.get("job", "")
    with _JOBS_LOCK:
        job = _JOBS.get(jid)
        if not job:
            return jsonify({"status": "unknown"}), 404
        return jsonify({"status": job["status"], "stage": job.get("stage"),
                        "result": job.get("result"), "log": job.get("log")})


# ── Logos des banques ────────────────────────────────────────────────────
# Reproductible & évolutif : la source de vérité est le DOSSIER assets/logos/.
# Une banque ajoutée peut y déposer son logo ; sinon l'UI génère un badge initiales.
_LOGO_DIR = os.path.join(HERE, "assets", "logos")
_LOGO_EXT_OK = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}


@app.route("/api/bank_logos")
def bank_logos():
    """Carte {CODE_BANQUE_MAJ: 'assets/logos/fichier'} pour tous les logos présents sur disque."""
    out = {}
    try:
        for fn in os.listdir(_LOGO_DIR):
            stem, ext = os.path.splitext(fn)
            if ext.lower() in _LOGO_EXT_OK:
                out[stem.upper()] = f"assets/logos/{fn}"
    except Exception:
        pass
    return jsonify(out)


@app.route("/api/ajout/logo", methods=["POST"])
def ajout_logo():
    """Enregistre le logo d'une (nouvelle) banque dans assets/logos/<CODE>.<ext>.
    Idempotent : remplace un éventuel logo existant de la même banque."""
    f = request.files.get("logo")
    banque = (request.form.get("banque") or "").upper().strip()
    if not f or not f.filename:
        return jsonify({"ok": False, "message": "Aucun logo fourni."}), 400
    if not banque:
        return jsonify({"ok": False, "message": "Banque manquante."}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in _LOGO_EXT_OK:
        return jsonify({"ok": False, "message": "Format non supporté (png/jpg/webp/gif/svg)."}), 400
    safe = "".join(c for c in banque if c.isalnum() or c in ("_", "-")) or "BANQUE"
    try:
        os.makedirs(_LOGO_DIR, exist_ok=True)
        # Supprime un ancien logo de la même banque (autre extension) pour éviter les doublons.
        for old in os.listdir(_LOGO_DIR):
            if os.path.splitext(old)[0].upper() == safe and os.path.splitext(old)[1].lower() in _LOGO_EXT_OK:
                try:
                    os.remove(os.path.join(_LOGO_DIR, old))
                except Exception:
                    pass
        dest = os.path.join(_LOGO_DIR, safe + ext)
        f.save(dest)
    except Exception as e:
        return jsonify({"ok": False, "message": f"Échec enregistrement : {e}"}), 500
    return jsonify({"ok": True, "path": f"assets/logos/{safe}{ext}"})


# ── PRÉCHAUFFAGE DES CACHES ──────────────────────────────────────────────────────────
# SORTI DU BLOC __main__ LE 2026-08-09, pour l'hébergement. Sous un serveur WSGI (gunicorn),
# server.py est IMPORTÉ, pas exécuté : `__name__` ne vaut pas « __main__ » et le préchauffage
# n'aurait jamais tourné. Ce n'est pas seulement une question de lenteur au premier appel — le
# commentaire de _strat_build_persist(), plus bas, le dit déjà : sans _warm(), _STRAT_CACHE
# reste vide, _strat_build_load() recharge le fichier disque, et l'application sert alors
# SILENCIEUSEMENT des analyses périmées. En production, personne ne s'en apercevrait.
_PRECHAUFFAGE_LANCE = False
# Pause entre deux calculs lourds du préchauffage, pour laisser passer les requêtes des
# utilisateurs. Réglable : 0 sur une machine puissante, davantage sur une instance bridée.
_PAUSE_WARM = float(os.getenv("PAUSE_PRECHAUFFAGE", "2"))


def demarrer_prechauffage():
    """Lance le préchauffage en arrière-plan, une seule fois par processus."""
    global _PRECHAUFFAGE_LANCE
    if _PRECHAUFFAGE_LANCE:
        return
    _PRECHAUFFAGE_LANCE = True
    import threading
    import time      # `time` n'est pas importé au niveau du module : sans cette ligne, la
                     # pause entre calculs lèverait NameError et tuerait le fil de
                     # préchauffage — silencieusement, puisqu'il tourne en arrière-plan.
    def _warm():
        # 1) Évolutions sémantiques (~13s)
        for seg in ("Particuliers", "Entreprises"):
            try:
                AGENTS["CB"].structured.cb_all_evolutions_summary(seg)
                print(f"[cache] cb_all_evolutions_summary({seg}) OK")
            except Exception as e:
                print(f"[cache] warm échoué evolutions ({seg}): {e}")
        # 2) Helpers par segment (évolution temporelle, rattrapage, innovation)
        for seg in ("Particuliers", "Entreprises"):
            for fn in (db.cb_analyse_q1, db.cb_serie_temporelle,
                       db.cb_rattrapage_depassement, db.cb_innovation_vs_finance):
                try:
                    fn(seg)
                except Exception as e:
                    print(f"[cache] warm échoué {fn.__name__}({seg}): {e}")
            try:
                AGENTS["CB"].structured.cb_evolution_details(seg, "SGCI")
            except Exception:
                pass
        # 3) Bundle des axes + prix — 15 à 30 secondes CHACUN.
        #
        # PÉRIODE COURANTE SEULEMENT PAR DÉFAUT (2026-08-10). Ce préchauffage balayait trois
        # années et deux semestres, soit DOUZE combinaisons : jusqu'à six minutes de calcul
        # continu. Sur une machine de bureau, c'est du temps mort pendant qu'on va chercher un
        # café. Sur l'instance hébergée, qui dispose d'un dixième de processeur, il sature ce
        # dixième et TOUTES les requêtes attendent derrière — y compris celles de la personne
        # qui vient de réveiller le service, et qui est la seule à regarder.
        #
        # C'est ce que le directeur constatait : « les données durent avant de s'afficher, et
        # pourtant c'est en cache ». Le cache était bien là ; c'est le préchauffage qui prenait
        # toute la machine pour remplir des périodes que personne ne consultait.
        #
        # On ne garde donc que la période affichée par défaut. Les périodes anciennes se
        # calculent à la demande, une fois, quand quelqu'un les ouvre vraiment. Le balayage
        # complet reste disponible par PRECHAUFFAGE_COMPLET=1, pour une machine qui en a les
        # moyens.
        complet = bool(os.getenv("PRECHAUFFAGE_COMPLET"))
        annees = (2026, 2025, 2024) if complet else (2026,)
        semestres = ("S1", "S2") if complet else ("S1",)
        print(f"[cache] préchauffage {'complet' if complet else 'de la période courante'} : "
              f"{len(annees) * len(semestres) * 2} combinaison(s)")
        for annee in annees:
            for sem in semestres:
                for seg in ("Particuliers", "Entreprises"):
                    try:
                        AGENTS["CB"].structured.cb_analyse_q2(annee, sem, seg)
                        AGENTS["CB"].structured.cb_analyse_q3(annee, sem, seg)
                        AGENTS["CB"].structured.cb_analyse_q5(annee, sem, seg)
                        AGENTS["CB"].structured.cb_analyse_q6(annee, sem, seg)
                        result = AGENTS["CB"].structured.cb_prix_par_libelle(annee, sem, seg)
                        AGENTS["CB"].structured.cb_prix_competitivite(annee, sem, seg)
                        n = sum(len(ss["services"]) for s in result for ss in s["sous_sections"])
                        print(f"[cache] bundle({annee},{sem},{seg}) → {n} services")
                    except Exception as e:
                        print(f"[cache] warm échoué bundle ({annee},{sem},{seg}): {e}")
                    # Respiration entre deux calculs lourds. Sans elle, le fil de préchauffage
                    # tient le processeur d'un bout à l'autre : sur une instance à un dixième
                    # de cœur, la requête d'un utilisateur attend la fin du calcul en cours au
                    # lieu de s'y intercaler. Deux secondes de pause coûtent quelques secondes
                    # au préchauffage et rendent l'application utilisable pendant ce temps.
                    time.sleep(_PAUSE_WARM)
        # 4) Stratégie (Niveau 3 du RAG) — pré-remplit _STRAT_CACHE → affichage instantané
        for seg in ("Particuliers", "Entreprises"):
            try:
                _STRAT_CACHE[seg] = strategie.build(seg)
                print(f"[cache] strategie({seg}) OK")
            except Exception as e:
                print(f"[cache] warm échoué strategie({seg}): {e}")
        # 5) Stratégie opérationnelle — LE PLUS LOURD DE TOUS. Mesuré sur le service hébergé :
        #    162 secondes au premier appel, 6 au second. On passe par l'ENDPOINT plutôt que par
        #    la seule fonction de directives, pour que le fichier disque soit écrit : sans lui,
        #    le prochain réveil du service recommencerait tout, et c'est le premier visiteur
        #    qui paierait — celui qu'il fallait servir.
        _client_warm = app.test_client()
        for seg in ("Particuliers", "Entreprises"):
            try:
                if _stratop_lire(2026, "S1", seg) is not None:
                    print(f"[cache] strat-op({seg}) déjà sur disque")
                    continue
                r = _client_warm.get("/api/strategie_operationnelle?annee=2026"
                                     f"&semestre=S1&segment={seg}")
                n = len((r.get_json() or {}).get("directives", {}).get("directives", []))
                print(f"[cache] strat-op({seg}) → {n} directives, persistées")
            except Exception as e:
                print(f"[cache] warm échoué strat-op({seg}): {e}")
        # 6) Repositionnement tarifaire — 48 secondes mesurées sur le service en ligne, à
        #    chaque appel. Le calculer ici plutôt qu'au premier clic évite qu'un visiteur
        #    attende trois quarts de minute sur l'écran « Conditions bancaires ».
        for seg in ("Particuliers", "Entreprises"):
            try:
                if _cache_lire(f"cb_repricing:2026:S1:{seg}") is not None:
                    print(f"[cache] repricing({seg}) déjà en base")
                    continue
                r = _client_warm.get(f"/api/cb_repricing?annee=2026&semestre=S1&segment={seg}")
                n = (r.get_json() or {}).get("n_actions")
                print(f"[cache] repricing({seg}) → {n} action(s), persistées")
            except Exception as e:
                print(f"[cache] warm échoué repricing({seg}): {e}")
            time.sleep(_PAUSE_WARM)
        # PERSISTE sur disque ce qui vient d'être reconstruit frais — sans ce _strat_build_persist(),
        # le fichier disque restait figé indéfiniment (trouvé le 2026-07-14 : dernier vécu le
        # 2026-07-07, une semaine avant la correction du bug de fenêtre glissante EF is_primary).
        # Aujourd'hui ça ne se voyait pas car _warm() tourne AVANT toute requête et laisse
        # _STRAT_CACHE non-vide, donc _strat_build_load() ne rechargeait jamais le disque périmé —
        # mais un redémarrage sans _warm() (crash, requête arrivant avant la fin du warmup) aurait
        # silencieusement servi les anciennes données depuis le disque, sans aucune alerte.
        _strat_build_persist()
    threading.Thread(target=_warm, daemon=True).start()


# Sous gunicorn, l'import du module suffit à armer le préchauffage.
demarrer_prechauffage()


if __name__ == "__main__":
    print("\n" + "="*55)
    print(" SpyBusiness · http://localhost:5000")
    print("="*55 + "\n")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False, threaded=True)
