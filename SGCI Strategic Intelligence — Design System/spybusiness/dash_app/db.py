"""
Accès PostgreSQL — base 'intelligence_bancaire'.

Lit la config depuis BACK/.env (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD).
Toutes les pages d'analyse appellent ces helpers (PAS le RAG) pour la vitesse.

Si la base n'est pas disponible, les fonctions retombent sur des données
représentatives (mock) pour que l'UI reste démontrable hors-ligne.
"""

import os
import re
import statistics
from functools import lru_cache

try:
    import psycopg2
    import psycopg2.extras
    _HAS_PG = True
except ImportError:
    _HAS_PG = False

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except Exception:
    pass

def _config_bd():
    """Paramètres de connexion — depuis DATABASE_URL si elle existe, sinon les cinq variables.

    AJOUTÉ POUR L'HÉBERGEMENT (2026-08-09). Render et Supabase ne donnent pas cinq variables :
    ils donnent UNE chaîne, `postgresql://utilisateur:motdepasse@hôte:port/base`. Sans lecture
    de cette chaîne, l'application déployée retombait silencieusement sur « localhost », où il
    n'y a pas de base — et db.query() rendant [] plutôt que de lever, le tableau de bord se
    serait affiché VIDE sans dire pourquoi. C'est exactement le genre de panne muette qu'on
    passe une soirée à chercher.

    DATABASE_URL est prioritaire : là où elle existe, c'est l'hébergeur qui l'a posée, et elle
    fait autorité sur un .env laissé dans l'image.

    sslmode=require en prod : Supabase et Render exigent TLS, et un mot de passe de base qui
    voyage en clair sur l'internet public n'est plus un mot de passe.
    """
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        from urllib.parse import unquote, urlparse
        u = urlparse(url)
        cfg = dict(
            host=u.hostname or "localhost",
            port=str(u.port or 5432),
            dbname=(u.path or "/postgres").lstrip("/") or "postgres",
            user=unquote(u.username or "postgres"),
            # Le mot de passe est encodé dans l'URL : un « @ » ou un « / » non décodé
            # produirait un refus d'authentification incompréhensible.
            password=unquote(u.password or ""),
        )
        if "sslmode=" in (u.query or ""):
            cfg["sslmode"] = dict(p.split("=", 1) for p in u.query.split("&")
                                  if "=" in p)["sslmode"]
        elif cfg["host"] not in ("localhost", "127.0.0.1"):
            cfg["sslmode"] = "require"
        return cfg
    return dict(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "intelligence_bancaire"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )


DB = _config_bd()

BANKS = ["BACI", "BICICI", "BNI", "ECOBANK", "NSIA", "SGCI", "SIB"]

# Libellés qui sont des labels de SEGMENT/catégorie captés par erreur comme un service
# (ex. ligne « Entreprises » avec un prix). On les exclut des comparaisons/exclusivités.
_NON_SERVICE_LIBELLES = (
    "entreprises", "entreprise", "professionnels", "professionnel", "particuliers",
    "particulier", "pme", "pmi", "corporate", "retail", "clientele", "clients",
    "client", "divers", "autres", "neant", "n/a", "na",
)
def _not_segment_sql(col="libelle"):
    """Clause SQL : le libellé n'est pas un simple label de segment/catégorie."""
    vals = ",".join("'%s'" % v for v in _NON_SERVICE_LIBELLES)
    return f"LOWER(TRIM({col})) NOT IN ({vals})"

# Fragments = paliers/sous-lignes (crédit, montants) captés comme un service à part.
_FRAGMENT_RE = re.compile(
    r"^(montant\s+(compris|sup[ée]rieur|inf[ée]rieur)|sup[ée]rieur\s+à|inf[ée]rieur\s+à"
    r"|dur[ée]e\s+(comprise|de)|entre\s+\d|de\s+\d)", re.I)
def _is_fragment_lib(lib):
    """True si le libellé est un fragment de palier (pas un vrai service comparable)."""
    return bool(_FRAGMENT_RE.match((lib or "").strip()))

def _median_robuste(vals):
    """Médiane en écartant les valeurs > 12× ou < 1/12 de la médiane brute.
    Évite qu'un appariement hétérogène (services différents sous un même libellé,
    ex. « Frais de dossier 6 000 … 220 000 F ») fausse la médiane marché."""
    vals = [float(v) for v in vals if v and float(v) > 0]
    if len(vals) < 2:
        return None
    m0 = statistics.median(vals)
    clean = [v for v in vals if (m0 / 12) <= v <= (m0 * 12)] if m0 > 0 else vals
    if len(clean) < 2:
        return None
    return round(statistics.median(clean))

import cb_sections
import cb_subsections
import cb_axes


def get_conn():
    if not _HAS_PG:
        raise RuntimeError("psycopg2 non installé")
    return psycopg2.connect(**DB)


def query(sql, params=None):
    """Run a SELECT, return list[dict].

    Une erreur de CONNEXION (PostgreSQL arrêté) est PROPAGÉE — surtout pas
    transformée en [] : sinon une fonction @lru_cache mémoriserait un résultat
    vide tant que le serveur tourne (cache empoisonné). lru_cache ne mémorise
    pas les exceptions → un simple redémarrage de PG suffit à tout réparer.
    Les autres erreurs (SQL ponctuel) gardent le fallback [] gracieux.
    """
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        print(f"[db] CONNEXION PostgreSQL échouée — propagation ({e})")
        raise
    except Exception as e:
        print(f"[db] query fallback ({e})")
        return []


def execute(sql, params=None):
    """Exécute une écriture (INSERT / UPDATE / CREATE) et valide la transaction.

    Ajouté le 2026-08-07 pour le module de sécurité. Contrairement à query(), qui se rabat
    silencieusement sur [] quand le SQL échoue, execute() PROPAGE l'erreur : une écriture qui
    échoue sans le dire est bien pire qu'une lecture vide. Créer un compte, journaliser un
    accès ou enregistrer une connexion doit réussir ou se signaler — jamais échouer en
    silence. C'est exactement le défaut qui a rendu invisibles cinq chemins morts et une
    requête invalide dans ce même fichier.

    Renvoie le nombre de lignes affectées.
    """
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(sql, params or ())
        n = cur.rowcount
        conn.commit()
        cur.close()
        return n
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Liste des banques — DYNAMIQUE depuis la base (flexible / évolutif / reproductible).
# Une banque ajoutée via « Ajouter des données » se propage PARTOUT sans hardcoding.
# ---------------------------------------------------------------------------
def _load_banks_from_db():
    """Banques réellement présentes en base (distinct cb_tarifs). SGCI garanti. None si base KO."""
    try:
        rows = query("SELECT DISTINCT banque FROM cb_tarifs "
                     "WHERE banque IS NOT NULL AND TRIM(banque) <> ''")
        found = sorted({(r.get("banque") or "").strip() for r in rows if (r.get("banque") or "").strip()})
        if found:
            if "SGCI" not in found:
                found.append("SGCI")
            return sorted(found)
    except Exception as e:
        print(f"[db] liste banques dynamique indisponible → fallback ({e})")
    return None


def refresh_banks():
    """Recharge BANKS EN PLACE (les ~24 usages `for b in BANKS` voient la MAJ, sans redémarrage) et
    invalide TOUTES les fonctions @lru_cache de ce module. Appelé à l'import ET après un ajout de
    données.
    IMPORTANT (bug corrigé le 2026-07-08) : cette fonction ne vidait AVANT que 8 caches nommés en
    dur, alors que le fichier en compte 31 — 25 fonctions (cb_analyse_q1/q2/q5/q6, cb_evolution_
    details, ef_cout_risque_3ans, …) restaient donc figées en mémoire pour toujours après un ajout
    de données, jusqu'au redémarrage du process. Fix : on parcourt maintenant DYNAMIQUEMENT tous
    les objets du module ayant un `cache_clear` (donc TOUT lru_cache, présent OU futur) — plus
    aucune fonction ne peut être oubliée dans une liste à maintenir à la main."""
    fresh = _load_banks_from_db()
    if fresh:
        BANKS[:] = fresh
    for _name, _f in list(globals().items()):
        if callable(_f) and hasattr(_f, "cache_clear"):
            try:
                _f.cache_clear()
            except Exception:
                pass
    return list(BANKS)


# Charge la liste réelle dès l'import (si PG est up ; sinon la valeur par défaut ci-dessus reste).
refresh_banks()


# ---------------------------------------------------------------------------
# Mocks représentatifs (fallback hors-ligne)
# ---------------------------------------------------------------------------

MOCK_FRAIS_TENUE = {
    "BACI": 5000, "BICICI": 5200, "BNI": 1000, "ECOBANK": 5500,
    "NSIA": 5400, "SGCI": None, "SIB": 4900,
}
MOCK_CARTE_ANNUELLE = {
    "BACI": 15000, "BICICI": 7000, "BNI": 12000, "ECOBANK": 10000,
    "NSIA": 5000, "SGCI": 10500, "SIB": None,
}
MOCK_VIREMENT = {
    "BACI": 1000, "BICICI": None, "BNI": 10000, "ECOBANK": 4400,
    "NSIA": None, "SGCI": 5000, "SIB": 1000,
}
MOCK_RN_2025 = {
    "SGCI": 101228, "ECOBANK": 57477, "BACI": 38229, "SIB": 31540,
    "BICICI": 28760, "NSIA": 22310, "BNI": 18940,
}
MOCK_RN_SERIES = {
    "SGCI":    {2021: 72000, 2022: 80500, 2023: 88200, 2024: 94100, 2025: 101228},
    "ECOBANK": {2021: 41000, 2022: 46500, 2023: 50200, 2024: 54100, 2025:  57477},
    "BACI":    {2021: 26000, 2022: 29500, 2023: 32800, 2024: 35600, 2025:  38229},
    "SIB":     {2021: 22000, 2022: 24800, 2023: 27200, 2024: 29400, 2025:  31540},
    "BICICI":  {2021: 20500, 2022: 22900, 2023: 25100, 2024: 26800, 2025:  28760},
    "NSIA":    {2021: 15200, 2022: 17600, 2023: 19400, 2024: 20900, 2025:  22310},
    "BNI":     {2021: 12800, 2022: 14500, 2023: 15900, 2024: 17300, 2025:  18940},
}


# ---------------------------------------------------------------------------
# CB — Conditions Bancaires
# ---------------------------------------------------------------------------

@lru_cache(maxsize=16)
def frais_tenue_compte(annee=2026, semestre="S1", segment="Particuliers"):
    """
    Frais de tenue de compte de base par banque (tarif minimum publié).
    Exclut les comptes en section Successions.
    Retourne None pour les banques ne publiant pas ce tarif.
    """
    rows = query(
        """
        SELECT banque, MIN(montant) AS montant
        FROM cb_tarifs
        WHERE (libelle ILIKE %s OR libelle ILIKE %s
               OR contexte ILIKE %s)
          AND annee = %s AND semestre = %s AND segment = %s
          AND is_header = false
          AND type_valeur = 'MONTANT_FCFA'
          AND montant IS NOT NULL
          AND montant BETWEEN 500 AND 100000
          AND (contexte NOT ILIKE %s OR contexte IS NULL)
        GROUP BY banque
        ORDER BY montant ASC
        """,
        ("%tenue%compte%", "%gestion%compte%", "%tenue%compte%",
         annee, semestre, segment, "%succession%"),
    )
    if rows:
        result = {b: None for b in BANKS}
        for r in rows:
            result[r["banque"]] = float(r["montant"])
        return result
    return dict(MOCK_FRAIS_TENUE)


@lru_cache(maxsize=16)
def frais_tenue_compte_detail(annee=2026, semestre="S1", segment="Particuliers"):
    """Détail des frais de tenue de compte par type de compte."""
    rows = query(
        """
        SELECT banque, libelle, montant
        FROM cb_tarifs
        WHERE (libelle ILIKE %s OR libelle ILIKE %s
               OR contexte ILIKE %s)
          AND annee = %s AND semestre = %s AND segment = %s
          AND is_header = false
          AND type_valeur = 'MONTANT_FCFA'
          AND montant IS NOT NULL
          AND montant BETWEEN 500 AND 100000
          AND (contexte NOT ILIKE %s OR contexte IS NULL)
        ORDER BY banque, montant ASC
        """,
        ("%tenue%compte%", "%gestion%compte%", "%tenue%compte%",
         annee, semestre, segment, "%succession%"),
    )
    return rows or []


@lru_cache(maxsize=16)
def cartes_annuelles(annee=2026, semestre="S1", segment="Particuliers"):
    """Cotisation carte bancaire standard par banque (tarif de base)."""
    rows = query(
        """
        SELECT banque, MIN(montant) AS montant
        FROM cb_tarifs
        WHERE libelle ILIKE %s
          AND libelle NOT ILIKE %s
          AND libelle NOT ILIKE %s
          AND libelle NOT ILIKE %s
          AND annee = %s AND semestre = %s AND segment = %s
          AND is_header = false
          AND type_valeur = 'MONTANT_FCFA'
          AND montant BETWEEN 5000 AND 150000
        GROUP BY banque
        ORDER BY montant ASC
        """,
        ("%carte%",
         "%remplacement%", "%opposition%", "%destruction%",
         annee, semestre, segment),
    )
    if rows:
        result = {b: None for b in BANKS}
        for r in rows:
            result[r["banque"]] = float(r["montant"])
        return result
    return dict(MOCK_CARTE_ANNUELLE)


@lru_cache(maxsize=16)
def virements_locaux(annee=2026, semestre="S1", segment="Particuliers"):
    """Frais virement local UEMOA par banque (tarif de base)."""
    rows = query(
        """
        SELECT banque, MIN(montant) AS montant
        FROM cb_tarifs
        WHERE (libelle ILIKE %s OR libelle ILIKE %s)
          AND (libelle ILIKE %s OR libelle ILIKE %s
               OR libelle ILIKE %s OR libelle ILIKE %s)
          AND annee = %s AND semestre = %s AND segment = %s
          AND is_header = false
          AND type_valeur = 'MONTANT_FCFA'
          AND montant BETWEEN 100 AND 50000
        GROUP BY banque
        ORDER BY montant ASC
        """,
        ("%virement%", "%transfert%",
         "%place%", "%local%", "%uemoa%", "%interne%",
         annee, semestre, segment),
    )
    if rows:
        result = {b: None for b in BANKS}
        for r in rows:
            result[r["banque"]] = float(r["montant"])
        return result
    return dict(MOCK_VIREMENT)


@lru_cache(maxsize=8)
def categories_disponibles(annee=2026, semestre="S1", segment="Particuliers"):
    """Liste des catégories CB (premier niveau du contexte)."""
    rows = query(
        """
        SELECT DISTINCT
            CASE WHEN contexte ILIKE %s
                 THEN TRIM(SPLIT_PART(contexte, '|', 1))
                 ELSE TRIM(contexte)
            END AS categorie
        FROM cb_tarifs
        WHERE annee = %s AND semestre = %s AND segment = %s
          AND is_header = false
          AND contexte IS NOT NULL
          AND contexte NOT ILIKE %s
        ORDER BY 1
        """,
        ("%|%", annee, semestre, segment, "%succession%"),
    )
    return [r["categorie"] for r in rows if r["categorie"]] if rows else []


@lru_cache(maxsize=32)
def tarifs_par_categorie(categorie, annee=2026, semestre="S1", segment="Particuliers"):
    """Tous les tarifs d'une catégorie pour toutes les banques."""
    pat = f"%{categorie}%"
    rows = query(
        """
        SELECT banque, libelle, montant, type_valeur, valeur_brute
        FROM cb_tarifs
        WHERE (contexte ILIKE %s OR libelle ILIKE %s)
          AND annee = %s AND semestre = %s AND segment = %s
          AND is_header = false
          AND (contexte NOT ILIKE %s OR contexte IS NULL)
          AND (montant IS NULL OR montant < 500000)
        ORDER BY banque, libelle
        """,
        (pat, pat, annee, semestre, segment, "%succession%"),
    )
    return rows or []


@lru_cache(maxsize=32)
def service_toutes_banques(libelle_pattern, annee=2026, semestre="S1", segment="Particuliers"):
    """
    Pour un service donné (ex: 'tenue de compte'), retourne TOUS les types
    de comptes de TOUTES les banques avec leurs tarifs.
    C'est la requête principale pour les comparaisons inter-banques.
    """
    rows = query(
        """
        SELECT banque, section, contexte, libelle, montant, type_valeur, valeur_brute
        FROM cb_tarifs
        WHERE libelle ILIKE %s
          AND annee = %s AND semestre = %s AND segment = %s
          AND is_header = false
          AND (contexte NOT ILIKE %s OR contexte IS NULL)
          AND (montant IS NULL OR montant < 500000)
        ORDER BY banque, section, libelle
        """,
        (f"%{libelle_pattern}%", annee, semestre, segment, "%succession%"),
    )
    return rows or []


# ---------------------------------------------------------------------------
# CB — Positionnement concurrentiel (données réelles BD)
# ---------------------------------------------------------------------------

# Catalogue de produits clés avec leurs conditions SQL (paramètres %s psycopg2)
# Format : (nom_affichage, condition_WHERE, tuple_params_ilike, montant_min, montant_max)
_CB_CATALOG = {
    "Particuliers": [
        ("Tenue de compte",
         "libelle ILIKE %s AND (contexte NOT ILIKE %s OR contexte IS NULL)",
         ("%tenue%compte%", "%succession%"), 500, 100000),
        ("Virement UEMOA",
         "(libelle ILIKE %s OR libelle ILIKE %s)",
         ("%uemoa%", "%zone uemoa%"), 50, 50000),
        ("Virement local",
         "libelle ILIKE %s AND libelle NOT ILIKE %s AND libelle NOT ILIKE %s AND libelle NOT ILIKE %s",
         ("%virement%local%", "%uemoa%", "%international%", "%swift%"), 50, 50000),
        ("Attestation de solde",
         "libelle ILIKE %s",
         ("%attestation%solde%",), 1000, 200000),
        ("Rejet cheque",
         "(libelle ILIKE %s OR (libelle ILIKE %s AND libelle ILIKE %s))",
         ("%rejet%ch%que%", "%ch%que%", "%impa%"), 1000, 200000),
        ("Opposition",
         "libelle ILIKE %s AND libelle NOT ILIKE %s",
         ("%opposition%", "%saisie%"), 100, 100000),
        ("Chequier",
         "libelle ILIKE %s AND libelle NOT ILIKE %s",
         ("%ch%quier%", "%destruction%"), 500, 50000),
        ("Carte bancaire",
         "libelle ILIKE %s AND (libelle ILIKE %s OR libelle ILIKE %s OR libelle ILIKE %s OR libelle ILIKE %s)",
         ("%carte%", "%visa%", "%national%", "%classique%", "%basic%"), 2000, 100000),
    ],
    "Entreprises": [
        ("Tenue de compte",
         "libelle ILIKE %s AND (contexte NOT ILIKE %s OR contexte IS NULL)",
         ("%tenue%compte%", "%succession%"), 500, 500000),
        ("Virement UEMOA",
         "(libelle ILIKE %s OR libelle ILIKE %s)",
         ("%uemoa%", "%zone uemoa%"), 50, 100000),
        ("Attestation de solde",
         "libelle ILIKE %s",
         ("%attestation%solde%",), 1000, 200000),
        ("Opposition",
         "libelle ILIKE %s AND libelle NOT ILIKE %s",
         ("%opposition%", "%saisie%"), 100, 100000),
        ("Rejet cheque",
         "(libelle ILIKE %s OR (libelle ILIKE %s AND libelle ILIKE %s))",
         ("%rejet%ch%que%", "%ch%que%", "%impa%"), 1000, 500000),
        ("Frais Swift",
         "libelle ILIKE %s",
         ("%swift%",), 1000, 100000),
        ("Virement local",
         "libelle ILIKE %s AND libelle NOT ILIKE %s AND libelle NOT ILIKE %s",
         ("%virement%", "%uemoa%", "%swift%"), 50, 50000),
        ("Carte bancaire",
         "libelle ILIKE %s AND (libelle ILIKE %s OR libelle ILIKE %s OR libelle ILIKE %s OR libelle ILIKE %s)",
         ("%carte%", "%visa%", "%national%", "%classique%", "%basic%"), 2000, 200000),
    ],
}


# Seuil en-dessous duquel une CB (banque, période, segment) est jugée
# "insuffisante" — convention reprise de run_qualite_complete.py / audit_cb_exhaustivite.py
CB_SEUIL_INSUFFISANT = 200


def _cb_semestre_alterne(semestre):
    return "S2" if semestre == "S1" else "S1"


def _cb_rang_periode(periode):
    """Ordonne chronologiquement (annee, semestre) : S1 avant S2 d'une même année."""
    annee, semestre = periode
    return annee * 2 + (0 if semestre == "S1" else 1)


@lru_cache(maxsize=32)
def cb_imputations(annee=2026, semestre="S1", segment="Particuliers"):
    """
    Règle d'imputation métier, en deux temps (déclenchée par l'INSUFFISANCE
    de données — < CB_SEUIL_INSUFFISANT lignes — quelle qu'en soit la cause,
    pas seulement l'absence pure) :

    1) Même année d'abord : si l'autre semestre (S1<->S2) de la MÊME année
       contient davantage de données, on l'utilise — c'est l'hypothèse
       métier de base ("les conditions de banque ne changent généralement
       pas radicalement d'un semestre à l'autre").
    2) Si cette option est elle-même absente/insuffisante (ex. "S2 2026"
       qui n'existe pas encore pour aucune banque), on cherche, dans
       l'ordre chronologique — d'abord les périodes ANTÉRIEURES (la plus
       récente en premier), puis à défaut les POSTÉRIEURES — la première
       période où la banque dispose d'assez de données. On ne bascule
       que si la période candidate apporte réellement plus de lignes que
       la période demandée (jamais de substitution à l'aveugle).

    Retourne, par banque, le détail nécessaire à un affichage transparent :
    {banque: {annee_demandee, semestre_demande, annee_utilisee,
              semestre_utilise, impute, lignes_demande, lignes_utilise}}
    """
    rows = query(
        "SELECT banque, annee, semestre, COUNT(*) AS n FROM cb_tarifs "
        "WHERE segment=%s AND is_header=FALSE "
        "GROUP BY banque, annee, semestre",
        (segment,),
    )
    counts, periodes = {}, set()
    for r in rows:
        counts.setdefault(r["banque"], {})[(r["annee"], r["semestre"])] = r["n"]
        periodes.add((r["annee"], r["semestre"]))

    demandee = (annee, semestre)
    rang = _cb_rang_periode(demandee)
    anterieures = sorted((p for p in periodes if _cb_rang_periode(p) < rang), key=_cb_rang_periode, reverse=True)
    posterieures = sorted((p for p in periodes if _cb_rang_periode(p) > rang), key=_cb_rang_periode)
    alterne = (annee, _cb_semestre_alterne(semestre))
    candidats = [alterne] + [p for p in anterieures + posterieures if p != alterne]

    result = {}
    for banque in BANKS:
        n_demande = counts.get(banque, {}).get(demandee, 0)
        meilleure, n_meilleure = demandee, n_demande
        if n_demande < CB_SEUIL_INSUFFISANT:
            for cand in candidats:
                n_cand = counts.get(banque, {}).get(cand, 0)
                if n_cand > n_meilleure:
                    meilleure, n_meilleure = cand, n_cand
                    if n_cand >= CB_SEUIL_INSUFFISANT:
                        break
        result[banque] = {
            "annee_demandee": annee,
            "semestre_demande": semestre,
            "annee_utilisee": meilleure[0],
            "semestre_utilise": meilleure[1],
            "impute": meilleure != demandee,
            "lignes_demande": n_demande,
            "lignes_utilise": n_meilleure,
        }
    return result


def _cb_period_filter(imputations):
    """
    Fragment SQL (+ paramètres) sélectionnant, pour chaque banque, sa
    période EFFECTIVE (année + semestre) après imputation éventuelle.
    Remplace la simple clause `annee=%s AND semestre=%s` pour permettre
    à chaque banque d'utiliser sa propre période réelle — y compris,
    si nécessaire, une année différente de celle demandée.
    """
    parts, params = [], []
    for banque, info in imputations.items():
        parts.append("(banque=%s AND annee=%s AND semestre=%s)")
        params.extend([banque, info["annee_utilisee"], info["semestre_utilise"]])
    return "(" + " OR ".join(parts) + ")", params


@lru_cache(maxsize=32)
def cb_positionnement_bd(annee=2026, semestre="S1", segment="Particuliers"):
    """
    Positionnement CB réel depuis PostgreSQL.
    Retourne {service: {bank: min_montant_ou_null}}.
    Chaque valeur = tarif de base minimum publié par la banque (hors succession).
    Applique la règle d'imputation banque par banque (même année S1<->S2
    en priorité, sinon période chronologiquement la plus proche avec
    assez de données) — voir cb_imputations() pour le détail transparent.
    """
    catalog = _CB_CATALOG.get(segment, _CB_CATALOG["Particuliers"])
    imputations = cb_imputations(annee, semestre, segment)
    period_sql, period_params = _cb_period_filter(imputations)
    result = {}
    for svc_name, cond_sql, cond_params, m_min, m_max in catalog:
        params = (segment,) + tuple(period_params) + (m_min, m_max) + cond_params
        rows = query(
            "SELECT banque, MIN(montant) AS val FROM cb_tarifs "
            "WHERE segment=%s "
            "AND " + period_sql + " "
            "AND montant BETWEEN %s AND %s "
            "AND is_header=FALSE "
            "AND (" + cond_sql + ") "
            "GROUP BY banque",
            params,
        )
        bank_vals = {r["banque"]: float(r["val"]) for r in rows if r.get("val") is not None}
        result[svc_name] = {b: bank_vals.get(b) for b in BANKS}
    return result


def cb_annees_disponibles():
    """Années CB disponibles dans la BD (dynamique)."""
    rows = query("SELECT DISTINCT annee FROM cb_tarifs ORDER BY annee")
    return [r["annee"] for r in rows] if rows else [2024, 2025, 2026]


def cb_exhaustif(annee=2026, semestre="S1", segment="Particuliers"):
    """
    TOUS les tarifs publiés par toutes les banques — sans agrégation MIN.
    Retourne une liste plate de lignes pour analyse exhaustive + gap analysis.
    Inclut MONTANT_FCFA, GRATUIT, TAUX_%, SUR_DEMANDE, NUMERIQUE.
    Exclut ENTETE_SECTION, NON_APPLICABLE, AUTRE.
    Applique la règle d'imputation banque par banque (même année S1<->S2
    en priorité, sinon période chronologiquement la plus proche avec assez
    de données) — chaque ligne porte son `annee`/`semestre` réels ; voir
    cb_imputations() pour le mapping transparent demandé/utilisé par banque.

    Chaque ligne porte aussi sa SECTION CANONIQUE BCEAO (`section_roman`,
    `section_titre`, via cb_sections.canonical_section) — le seul
    regroupement fiable pour comparer les catalogues entre banques. Le
    regroupement par `contexte` brut (texte d'en-tête de la brochure
    d'origine, qui diffère d'une banque à l'autre pour un même service —
    ex. SGCI range ses attestations sous "Conditions générales des
    comptes" quand BACI/BICICI/BNI ont un en-tête "Attestations
    bancaires") produit de fausses "absences" : un service que SGCI
    propose réellement apparaît "ABSENT" simplement parce qu'il est rangé
    sous un intitulé différent. La section canonique élimine ce biais.

    Chaque ligne porte aussi sa SOUS-SECTION (`sous_section_id`,
    `sous_section_libelle`, via cb_subsections.classify_subsection — même
    classification déterministe par contenu que `cb_par_sous_section`) :
    nécessaire pour construire, côté frontend, le comparatif détaillé
    ligne-par-ligne (SGCI vs concurrent choisi) à l'intérieur de chaque
    sous-famille, sans devoir refaire un aller-retour serveur par section.
    """
    imputations = cb_imputations(annee, semestre, segment)
    period_sql, period_params = _cb_period_filter(imputations)
    rows = query(
        "SELECT banque, annee, semestre, section, contexte, libelle, "
        "       valeur_propre, montant, unite, type_valeur, est_gratuit "
        "FROM cb_tarifs "
        "WHERE segment=%s "
        "AND " + period_sql + " "
        "AND is_header = FALSE "
        "AND type_valeur IN ('MONTANT_FCFA','GRATUIT','TAUX_%%','SUR_DEMANDE','NUMERIQUE') "
        "ORDER BY section, libelle, banque",
        tuple([segment] + period_params),
    )
    result = []
    for r in rows:
        d = dict(r)
        sid, roman, titre = cb_sections.canonical_section(d["banque"], d["section"], d["libelle"], d["contexte"])
        d["section_roman"] = roman
        d["section_titre"] = titre
        sub_id, sub_label = cb_subsections.classify_subsection(sid, d["libelle"], d["contexte"])
        d["sous_section_id"] = sub_id
        d["sous_section_libelle"] = sub_label
        result.append(d)
    return result


@lru_cache(maxsize=32)
def cb_par_section(annee=2026, semestre="S1", segment="Particuliers"):
    """
    Agrégation des tarifs CB par SECTION CANONIQUE BCEAO (I à IX) — la
    seule granularité de comparaison fiable entre banques dont les grilles
    tarifaires emploient des libellés et découpages différents pour des
    services équivalents (cf. cb_sections.canonical_section).

    Remplace la comparaison par libellé isolé (_CB_CATALOG / ILIKE), qui
    génère l'essentiel des "Non disponible" du dashboard : deux banques
    proposant le même service sous des intitulés différents ne se
    rapprochent jamais par correspondance exacte de libellé, alors
    qu'elles appartiennent à la même section officielle du document.

    Retourne une liste ordonnée (I → IX) :
    [{id, roman, titre, banques: {banque: {n_lignes, n_gratuit,
      pct_gratuit, n_montants, montant_median, montant_min, montant_max,
      n_services_distincts}}}, ...]
    montant_* ne portent que sur les lignes de type MONTANT_FCFA.
    Le prix "typique" d'une section est la MÉDIANE (pas la moyenne) :
    une section mélange des montants de nature très différente (frais
    fixes, plafonds de crédit, commissions à 4 chiffres), et la moyenne
    se laisse écraser par un seul montant exceptionnel — ex. SGCI
    "Autres services" Particuliers 2026-S1 : moyenne tirée à 507 426 F
    par une unique ligne "Frais d'introduction en bourse" à 10 625 000 F,
    alors que la médiane (15 500 F) reflète fidèlement le tarif typique
    des 24 lignes de la section. La médiane est insensible à ce biais.
    """
    rows = cb_exhaustif(annee, semestre, segment)
    sections = cb_sections.all_sections()
    agg = {sid: {b: {"n": 0, "n_gratuit": 0, "montants": [], "libelles": set()} for b in BANKS}
           for sid, _, _ in sections}
    for r in rows:
        sid, _, _ = cb_sections.canonical_section(r["banque"], r["section"], r["libelle"], r["contexte"])
        bucket = agg[sid][r["banque"]]
        bucket["n"] += 1
        if r["type_valeur"] == "GRATUIT" or r["est_gratuit"]:
            bucket["n_gratuit"] += 1
        if r["type_valeur"] == "MONTANT_FCFA" and r["montant"] is not None:
            bucket["montants"].append(float(r["montant"]))
        if r["libelle"]:
            bucket["libelles"].add(r["libelle"])

    result = []
    for sid, roman, titre in sections:
        banques = {}
        for b in BANKS:
            d = agg[sid][b]
            montants = d["montants"]
            banques[b] = {
                "n_lignes": d["n"],
                "n_gratuit": d["n_gratuit"],
                "pct_gratuit": round(100 * d["n_gratuit"] / d["n"], 1) if d["n"] else None,
                "n_montants": len(montants),
                "montant_median": round(statistics.median(montants)) if montants else None,
                "montant_min": min(montants) if montants else None,
                "montant_max": max(montants) if montants else None,
                "n_services_distincts": len(d["libelles"]),
            }
        result.append({"id": sid, "roman": roman, "titre": titre, "banques": banques})
    return result


@lru_cache(maxsize=32)
def cb_par_sous_section(annee=2026, semestre="S1", segment="Particuliers"):
    """
    Agrégation des tarifs CB par SOUS-SECTION (cf. cb_subsections), un niveau
    sous `cb_par_section` : pour chaque section canonique I-IX, le détail par
    sous-section (ex. I → "Ouverture de compte" / "Clôture de compte" / ...).

    Sépare ce que `cb_par_section` mélange par construction — deux familles
    de tarifs hétérogènes au sein d'une même section (ouverture vs clôture de
    compte, cartes vs virements, etc.) finissent dans une médiane commune qui
    ne reflète ni l'une ni l'autre fidèlement. Même motif d'agrégation et
    même garde-fou que `cb_par_section` (cf. son docstring pour la
    justification de la médiane) — garde-fou *renforcé* d'un niveau : chaque
    ligne est désormais rattachée à SECTION *et* SOUS-SECTION avant d'entrer
    dans le panier de comparaison, condition même de la granularité demandée.

    Retourne une liste ordonnée (I → IX), chacune contenant ses sous-sections
    dans leur ordre de priorité de classification :
    [{id, roman, titre, sous_sections: [{id, libelle, banques: {banque: {
      n_lignes, n_gratuit, pct_gratuit, n_montants, montant_median,
      montant_min, montant_max, n_services_distincts}}}, ...]}, ...]
    montant_* ne portent que sur les lignes de type MONTANT_FCFA — jamais de
    mélange %/F CFA (cf. règle "PLUS JAMAIS DE CE GENRE D'ERREUR").
    """
    rows = cb_exhaustif(annee, semestre, segment)
    sections = cb_sections.all_sections()
    agg = {}
    for sid, _, _ in sections:
        agg[sid] = {sub_id: {b: {"n": 0, "n_gratuit": 0, "montants": [], "libelles": set()} for b in BANKS}
                    for sub_id, _ in cb_subsections.all_subsections(sid)}
        default_id, _ = cb_subsections._DEFAULT_SUBSECTION.get(sid, (0, "Non classé"))
        agg[sid].setdefault(default_id, {b: {"n": 0, "n_gratuit": 0, "montants": [], "libelles": set()} for b in BANKS})

    for r in rows:
        sid, _, _ = cb_sections.canonical_section(r["banque"], r["section"], r["libelle"], r["contexte"])
        sub_id, _ = cb_subsections.classify_subsection(sid, r["libelle"], r["contexte"])
        bucket = agg[sid][sub_id][r["banque"]]
        bucket["n"] += 1
        if r["type_valeur"] == "GRATUIT" or r["est_gratuit"]:
            bucket["n_gratuit"] += 1
        if r["type_valeur"] == "MONTANT_FCFA" and r["montant"] is not None:
            bucket["montants"].append(float(r["montant"]))
        if r["libelle"]:
            bucket["libelles"].add(r["libelle"])

    result = []
    for sid, roman, titre in sections:
        sous_sections = []
        for sub_id, sub_label in cb_subsections.all_subsections(sid):
            sous_sections.append(_cb_sous_section_stats(sub_id, sub_label, agg[sid][sub_id]))
        default_id, default_label = cb_subsections._DEFAULT_SUBSECTION.get(sid, (0, "Non classé"))
        if any(agg[sid][default_id][b]["n"] for b in BANKS):
            sous_sections.append(_cb_sous_section_stats(default_id, default_label, agg[sid][default_id]))
        result.append({"id": sid, "roman": roman, "titre": titre, "sous_sections": sous_sections})
    return result


def _cb_sous_section_stats(sub_id, label, agg_par_banque):
    banques = {}
    for b in BANKS:
        d = agg_par_banque[b]
        montants = d["montants"]
        banques[b] = {
            "n_lignes": d["n"],
            "n_gratuit": d["n_gratuit"],
            "pct_gratuit": round(100 * d["n_gratuit"] / d["n"], 1) if d["n"] else None,
            "n_montants": len(montants),
            "montant_median": round(statistics.median(montants)) if montants else None,
            "montant_min": min(montants) if montants else None,
            "montant_max": max(montants) if montants else None,
            "n_services_distincts": len(d["libelles"]),
        }
    return {"id": sub_id, "libelle": label, "banques": banques}


# ---------------------------------------------------------------------------
# EF — États Financiers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=4)
def resultat_net(annee=2025):
    """Résultat net par banque — année demandée ou la plus récente disponible."""
    rows = query(
        """
        SELECT DISTINCT ON (banque) banque, annee_donnee, montant AS valeur
        FROM ef_indicateurs
        WHERE (libelle ILIKE %s OR libelle ILIKE %s)
          AND libelle NOT ILIKE %s
          AND is_primary = TRUE
          AND annee_donnee <= %s
        ORDER BY banque, annee_donnee DESC,
          CASE WHEN libelle ~ '^[[:ascii:]]+$' THEN 0 ELSE 1 END,
          montant DESC
        """,
        ("%sultat%net%", "%exercice%", "%avant%imp%", annee),
    )
    if rows:
        return {r["banque"]: float(r["valeur"]) for r in rows}
    return dict(MOCK_RN_2025)


@lru_cache(maxsize=1)
def resultat_net_series():
    rows = query(
        """
        SELECT DISTINCT ON (banque, annee_donnee) banque, annee_donnee AS annee, montant AS valeur
        FROM ef_indicateurs
        WHERE (libelle ILIKE %s OR libelle ILIKE %s)
          AND libelle NOT ILIKE %s
          AND is_primary = TRUE
        ORDER BY banque, annee_donnee,
          CASE WHEN libelle ~ '^[[:ascii:]]+$' THEN 0 ELSE 1 END,
          montant DESC
        """,
        ("%sultat%net%", "%exercice%", "%avant%imp%"),
    )
    if rows:
        series = {}
        for r in rows:
            series.setdefault(r["banque"], {})[r["annee"]] = float(r["valeur"])
        return series
    return dict(MOCK_RN_SERIES)


def ef_pnb_series():
    """Série PNB par banque et par année — is_primary=TRUE prioritaire, fallback FALSE."""
    pat = "%produit%net%bancaire%"
    sql = """SELECT banque, annee_donnee, AVG(montant) AS val
             FROM ef_indicateurs
             WHERE is_primary=%s AND montant IS NOT NULL AND montant > 0
               AND libelle ILIKE %s
             GROUP BY banque, annee_donnee"""
    series = {}
    for r in query(sql, (True, pat)):
        series.setdefault(r["banque"], {})[int(r["annee_donnee"])] = float(r["val"])
    # Fallback : bank/année absents du primaire
    for r in query(sql, (False, pat)):
        b, yr = r["banque"], int(r["annee_donnee"])
        if b not in series or yr not in series[b]:
            series.setdefault(b, {})[yr] = float(r["val"])
    # 3 dernières années par banque
    return {b: dict(list(sorted(yv.items()))[-3:]) for b, yv in series.items()}


def ef_roe_series():
    """Série ROE (RN/CP) par banque et par année depuis ef_indicateurs."""
    rn_s = resultat_net_series()
    cp_pat = "%capitaux%propres%"
    cp_sql = """SELECT banque, annee_donnee, AVG(montant) AS val
                FROM ef_indicateurs
                WHERE is_primary=%s AND montant IS NOT NULL AND montant > 0
                  AND libelle ILIKE %s
                GROUP BY banque, annee_donnee"""
    cp_s = {}
    for r in query(cp_sql, (True, cp_pat)):
        cp_s.setdefault(r["banque"], {})[int(r["annee_donnee"])] = float(r["val"])
    for r in query(cp_sql, (False, cp_pat)):
        b, yr = r["banque"], int(r["annee_donnee"])
        if b not in cp_s or yr not in cp_s[b]:
            cp_s.setdefault(b, {})[yr] = float(r["val"])
    series = {}
    for bank in set(list(rn_s.keys()) + list(cp_s.keys())):
        rn_yrs = rn_s.get(bank, {})
        cp_yrs = cp_s.get(bank, {})
        for yr in sorted(set(rn_yrs) & set(cp_yrs)):
            cp = cp_yrs[yr]
            if cp and cp > 0:
                roe = round(rn_yrs[yr] / cp * 100, 2)
                series.setdefault(bank, {})[yr] = roe
    # 3 dernières années par banque
    return {b: dict(list(sorted(yv.items()))[-3:]) for b, yv in series.items()}


def ef_coeff_series():
    """Série coefficient d'exploitation (Charges générales / PNB) par banque et année.
    Méthode 1 (directe) : libellé Charges générales ou Frais Généraux.
    Méthode 2 (fallback) : PNB − RBE (Résultat Brut d'Exploitation) quand les charges
    ne sont pas libellées explicitement (cas ECOBANK 2025).
    """
    pnb_s = ef_pnb_series()

    # Méthode 1 — charges libellées directement
    chg_sql = """SELECT banque, annee_donnee, AVG(montant) AS val
                 FROM ef_indicateurs
                 WHERE is_primary=%s AND montant IS NOT NULL AND montant > 0
                   AND (libelle ILIKE %s OR libelle ILIKE %s)
                 GROUP BY banque, annee_donnee"""
    pat1 = "%charges%rales%"
    pat2 = "%frais%n%raux%"
    chg_s = {}
    for r in query(chg_sql, (True, pat1, pat2)):
        chg_s.setdefault(r["banque"], {})[int(r["annee_donnee"])] = float(r["val"])
    for r in query(chg_sql, (False, pat1, pat2)):
        b, yr = r["banque"], int(r["annee_donnee"])
        if b not in chg_s or yr not in chg_s[b]:
            chg_s.setdefault(b, {})[yr] = float(r["val"])

    # Méthode 2 — fallback PNB − RBE pour les banque/année manquantes
    rbe_sql = """SELECT banque, annee_donnee, MAX(montant) AS val
                 FROM ef_indicateurs
                 WHERE is_primary=%s AND montant IS NOT NULL AND montant > 0
                   AND libelle ILIKE %s
                 GROUP BY banque, annee_donnee"""
    rbe_pat = "%resultat%brut%exploitation%"
    rbe_s = {}
    for r in query(rbe_sql, (True, rbe_pat)):
        rbe_s.setdefault(r["banque"], {})[int(r["annee_donnee"])] = float(r["val"])
    for bank, p_yrs in pnb_s.items():
        for yr, pnb in p_yrs.items():
            if bank not in chg_s or yr not in chg_s[bank]:
                rbe = rbe_s.get(bank, {}).get(yr)
                if rbe and pnb and pnb > 0 and rbe < pnb:
                    chg_s.setdefault(bank, {})[yr] = pnb - rbe

    series = {}
    for bank in set(list(pnb_s.keys()) + list(chg_s.keys())):
        p_yrs = pnb_s.get(bank, {})
        c_yrs = chg_s.get(bank, {})
        for yr in sorted(set(p_yrs) & set(c_yrs)):
            if p_yrs[yr] and p_yrs[yr] > 0:
                series.setdefault(bank, {})[yr] = round(c_yrs[yr] / p_yrs[yr] * 100, 1)
    return {b: dict(list(sorted(yv.items()))[-3:]) for b, yv in series.items()}


def ef_cnr_series():
    """Ratio CNR / Encours de crédit en points de base (pb) par banque et année.
    CNR = Coût Net du Risque ; Encours = Créances sur la clientèle.

    BUG CORRIGÉ le 2026-07-22 (repéré par le directeur sur le graphe : « pourquoi BNI va de
    2021 à 2023 ??? ») : l'ancien fallback is_primary=FALSE ajoutait systématiquement une 4ᵉ
    année PÉRIMÉE pour presque toutes les banques (chacune a exactement 3 années is_primary=TRUE
    + 1 année is_primary=FALSE plus ancienne, sauf BACI) — ce graphe montrait donc 4 ans quand
    TOUS les autres indicateurs EF (résultat net, ROE, coefficient, PNB) respectent strictement
    la fenêtre des 3 dernières années par banque. Fix : is_primary=TRUE UNIQUEMENT, comme
    resultat_net_series()/ef_roe_series()/ef_coeff_series() — cohérence garantie entre tous les
    graphiques de l'onglet Santé Financière.
    """
    sql = """SELECT banque, annee_donnee, AVG(montant) AS val
             FROM ef_indicateurs
             WHERE is_primary=%s AND montant IS NOT NULL AND montant > 0
               AND libelle ILIKE %s
             GROUP BY banque, annee_donnee"""

    # Coût du risque
    cnr_s = {}
    for r in query(sql, (True, "%co%t%risque%")):
        cnr_s.setdefault(r["banque"], {})[int(r["annee_donnee"])] = float(r["val"])

    # Encours de crédit (créances sur la clientèle brutes)
    enc_s = {}
    for r in query(sql, (True, "%cr%ances%client%")):
        enc_s.setdefault(r["banque"], {})[int(r["annee_donnee"])] = float(r["val"])
    # Fallback ECOBANK : nom de libellé ALTERNATIF, pas de bascule is_primary (toujours TRUE) —
    # ECOBANK nomme cet indicateur différemment ("Crédits nets à la clientèle"), légitime.
    for r in query(sql, (True, "%cr%dits%nets%client%")):
        b, yr = r["banque"], int(r["annee_donnee"])
        if b not in enc_s or yr not in enc_s[b]:
            enc_s.setdefault(b, {})[yr] = float(r["val"])

    series = {}
    for bank in set(list(cnr_s.keys()) + list(enc_s.keys())):
        c_yrs = cnr_s.get(bank, {})
        e_yrs = enc_s.get(bank, {})
        for yr in sorted(set(c_yrs) & set(e_yrs)):
            if e_yrs[yr] and e_yrs[yr] > 0:
                pb = round(c_yrs[yr] / e_yrs[yr] * 10000, 1)
                series.setdefault(bank, {})[yr] = pb
    return {b: dict(list(sorted(yv.items()))[-3:]) for b, yv in series.items()}


@lru_cache(maxsize=1)
def cb_periodes():
    """Semestres réellement disponibles PAR ANNÉE : {"2024": ["S1","S2"], "2026": ["S1"]}.

    Ajouté le 2026-07-30. Le sélecteur du dashboard proposait S1 et S2 en dur pour toute année
    (app.main.js), alors que 2026 ne contient que S1 : cliquer sur « 2026 S2 » plaçait l'écran
    dans un état incohérent — les agrégats par section répondaient (via l'imputation
    S2→S1 documentée dans cb_exhaustif) tandis que le comparatif détaillé revenait vide.
    En dérivant les boutons de cette fonction, une période absente n'est plus proposée, et
    l'ajout de données 2026 S2 fera apparaître le bouton automatiquement.
    """
    rows = query("SELECT DISTINCT annee, semestre FROM cb_tarifs "
                 "WHERE annee IS NOT NULL AND semestre IS NOT NULL "
                 "ORDER BY annee, semestre")
    out = {}
    for r in rows:
        out.setdefault(str(r["annee"]), []).append(r["semestre"])
    return out


def stats_globales():
    """Volumétrie de la base — ce sur quoi les analyses s'appuient réellement.

    Sert de point de contrôle : si un chiffre affiché surprend, on commence par vérifier ici que
    la donnée sous-jacente est bien présente. Écrite le 2026-07-30 — /api/stats l'appelait depuis
    l'origine alors qu'elle n'avait jamais été définie, et répondait donc 500 (l'endpoint n'étant
    consommé par aucune page, personne ne l'avait vu).
    """
    def n(sql):
        try:
            return query(sql)[0]["n"]
        except Exception:
            return None

    return {
        "cb_tarifs": n("SELECT COUNT(*) AS n FROM cb_tarifs"),
        "ef_indicateurs": n("SELECT COUNT(*) AS n FROM ef_indicateurs"),
        "regl_documents": n("SELECT COUNT(*) AS n FROM regl_documents"),
        "banques": [r["banque"] for r in query(
            "SELECT DISTINCT banque FROM cb_tarifs WHERE banque IS NOT NULL ORDER BY banque")],
        "periodes_cb": cb_periodes(),
        "segments": [r["segment"] for r in query(
            "SELECT DISTINCT segment FROM cb_tarifs WHERE segment IS NOT NULL ORDER BY segment")],
        "cb_vectorise": n("SELECT COUNT(*) AS n FROM cb_tarifs WHERE embedding IS NOT NULL"),
    }


def cb_annees():
    """Liste des années disponibles dans cb_tarifs."""
    rows = query("SELECT DISTINCT annee FROM cb_tarifs ORDER BY annee")
    if rows:
        return [r["annee"] for r in rows]
    return [2024, 2025, 2026]


def kpis_vue_ensemble(frais_annee=2026, frais_sem="S1", frais_seg="Particuliers", rn_anx=3):
    """KPIs Vue d'ensemble. rn_anx = INDEX dans la fenêtre propre de chaque banque (1=AN1, 2=AN2, 3=AN3).
    PRINCIPE : chaque banque utilise SES 3 dernières années disponibles.
      SGCI/BICICI/ECOBANK/NSIA/SIB  → AN1=2023, AN2=2024, AN3=2025
      BACI/BNI (données jusqu'à 2023) → AN1=2021, AN2=2022, AN3=2023
    Tout est dynamique : cliquer Année 2 → chaque banque affiche son AN2 (année calendaire différente selon banque)."""
    import unicodedata

    def _norm(s):
        s = (s or "").lower()
        return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

    rn_anx_c = max(1, min(3, rn_anx))

    # ── 1. Séries RN — source de vérité pour les années disponibles par banque ──
    # resultat_net_series() est cached → {bank: {year: rn_value}}
    _series = resultat_net_series()

    # ── 2. Par banque : sa propre fenêtre AN1/AN2/AN3 = ses 3 dernières années ──
    bank_anx = {}   # {bank: {1: year, 2: year, 3: year}}
    for bank, yr_data in _series.items():
        bank_years = sorted(yr_data.keys())
        last3 = bank_years[-3:] if len(bank_years) >= 3 else bank_years
        bank_anx[bank] = {i + 1: yr for i, yr in enumerate(last3)}

    # anx_legend = {bank: {AN1: "2021", AN2: "2022", AN3: "2023"}} — affiché dans l'en-tête
    anx_legend = {
        bank: {f"AN{n}": str(yr) for n, yr in anx.items()}
        for bank, anx in bank_anx.items()
    }

    # ── 3. RN pour l'ANx sélectionné — chaque banque à sa propre année ──────
    rn_data     = {}
    rn_year_map = {}   # {bank: année calendaire réelle}
    for bank, anx in bank_anx.items():
        yr_data   = _series.get(bank, {})
        target_yr = anx.get(rn_anx_c)
        if target_yr is None:
            # banque avec moins de 3 ans : prendre son AN le plus proche
            target_yr = anx.get(len(anx))
        if target_yr and target_yr in yr_data:
            rn_data[bank]     = yr_data[target_yr]
            rn_year_map[bank] = target_yr

    if not rn_data:
        rn_data = dict(MOCK_RN_2025)

    # ── 4. Croissance AN1→AN3 — fenêtre propre de chaque banque ─────────────
    growths_data = {}
    for bank, anx in bank_anx.items():
        yr_data = _series.get(bank, {})
        v1 = yr_data.get(anx.get(1))
        v3 = yr_data.get(anx.get(3))
        if v1 and v3 and v1 != 0 and anx.get(1) != anx.get(3):
            growths_data[bank] = round((v3 - v1) / abs(v1) * 100, 1)
    _full_growth = croissance_series()
    for b in BANKS:
        if b not in growths_data and b in _full_growth:
            growths_data[b] = _full_growth[b]
    if not growths_data:
        growths_data = _full_growth

    # ── 5. Champs pré-calculés ────────────────────────────────────────────
    sorted_rn      = sorted(rn_data.items(), key=lambda x: x[1], reverse=True)
    sgci_rn        = rn_data.get("SGCI", 0)
    sgci_rang_rn   = next((i+1 for i, (b, _) in enumerate(sorted_rn) if b == "SGCI"), len(sorted_rn))
    b2             = next(((b, v) for b, v in sorted_rn if b != "SGCI"), ("?", 0))
    banque_2_nom, banque_2_rn = b2
    ecart_pct_vs_2 = round((sgci_rn - banque_2_rn) / banque_2_rn * 100, 1) if banque_2_rn else 0
    total_all      = sum(rn_data.values())
    sgci_part      = round(sgci_rn / total_all * 100, 1) if total_all else 0
    sgci_growth    = growths_data.get("SGCI", 0)
    fastest        = max(growths_data.items(), key=lambda x: x[1]) if growths_data else ("?", 0)
    fastest_b, fastest_pct = fastest
    sgci_rn_annee  = str(rn_year_map.get("SGCI", ""))

    # ── 6. Indicateurs EF — par banque à SON année cible ─────────────────
    # Une seule requête sur toutes les années cibles, filtrage Python par banque
    target_years_set = set(rn_year_map.values())

    pnb_data = {}; cp_data = {}; charges_gen_data = {}; cout_r_raw = {}
    roa_data = {}; credits_data = {}; depots_data = {}; interets_data = {}
    commissions_data = {}; autres_prod_data = {}; rbe_data = {}; re_data = {}

    if target_years_set:
        ef_rows = query(
            """
            SELECT banque, libelle, annee_donnee, AVG(montant) AS valeur
            FROM ef_indicateurs
            WHERE is_primary=TRUE AND annee_donnee = ANY(%s) AND montant IS NOT NULL
            GROUP BY banque, libelle, annee_donnee
            """,
            (list(target_years_set),),
        )
        for r in ef_rows:
            b = r["banque"]
            # Garder seulement la ligne correspondant à l'année cible de cette banque
            if r["annee_donnee"] != rn_year_map.get(b):
                continue
            lib = _norm(r["libelle"])
            val = float(r["valeur"])

            if ("produit" in lib and "net" in lib and "bancaire" in lib) or lib.strip() == "pnb":
                pnb_data[b] = val
            elif "capitaux" in lib and "propres" in lib:
                cp_data[b] = val
            elif ("charges" in lib and "generales" in lib) or \
                 ("frais" in lib and ("generaux" in lib or "general" in lib)):
                if b not in charges_gen_data or val > charges_gen_data[b]:
                    charges_gen_data[b] = val
            elif "cout" in lib and "risque" in lib:
                cout_r_raw[b] = val
            elif "roa" in lib:
                roa_data[b] = val
            elif ("credit" in lib or "creance" in lib) and "clientele" in lib \
                 and "interbancaire" not in lib:
                if b not in credits_data or "credit" in lib:
                    credits_data[b] = val
            elif ("depot" in lib or ("dette" in lib and "clientele" in lib)) \
                 and "interbancaire" not in lib:
                if b not in depots_data or "depot" in lib:
                    depots_data[b] = val
            elif "interet" in lib and "assimile" in lib and "charge" not in lib:
                interets_data[b] = val
            elif "commission" in lib and "produit" in lib:
                commissions_data[b] = val
            elif "resultat brut" in lib or lib.strip() == "rbe":
                rbe_data[b] = val
            elif "resultat" in lib and "exploitation" in lib and "avant" not in lib:
                re_data[b] = val
            elif "autre" in lib and "produit" in lib:
                autres_prod_data[b] = val

    # ── 7. Indicateurs dérivés ────────────────────────────────────────────
    roe_data = {}
    for b, rn_v in rn_data.items():
        cp = cp_data.get(b)
        if cp and cp > 0:
            roe_data[b] = round(rn_v / cp * 100, 1)

    marge_nette_data = {}
    for b, rn_v in rn_data.items():
        pnb = pnb_data.get(b)
        if pnb and pnb > 0:
            marge_nette_data[b] = round(rn_v / pnb * 100, 1)

    coeff_expl_data = {}
    for b, pnb in pnb_data.items():
        if pnb <= 0:
            continue
        if b in rbe_data:
            coeff_expl_data[b] = round((pnb - rbe_data[b]) / pnb * 100, 1)
        elif b in charges_gen_data:
            coeff_expl_data[b] = round(charges_gen_data[b] / pnb * 100, 1)

    cout_r_pnb_data = {}
    for b, cr_raw in cout_r_raw.items():
        pnb = pnb_data.get(b)
        if pnb and pnb > 0:
            cout_r_pnb_data[b] = round(cr_raw / pnb * 100, 1)

    # ── 8. Données CB ─────────────────────────────────────────────────────
    frais_min     = frais_tenue_compte(frais_annee, frais_sem, frais_seg)
    virement_data = virements_locaux(frais_annee, frais_sem, frais_seg)
    sgci_virement = (virement_data or {}).get("SGCI") or 0

    return {
        "sgci_rang_rn":    sgci_rang_rn,
        "sgci_rn":         sgci_rn,
        "sgci_rn_annee":   sgci_rn_annee,
        "sgci_part_marche":sgci_part,
        "banque_2_nom":    banque_2_nom,
        "banque_2_rn":     banque_2_rn,
        "ecart_pct_vs_2":  ecart_pct_vs_2,
        "sgci_growth_pct": sgci_growth,
        "fastest_b":       fastest_b,
        "fastest_pct":     fastest_pct,
        "growths_data":    growths_data,
        "anx_legend":      anx_legend,
        "rn_annees":       {b: str(yr) for b, yr in rn_year_map.items()},
        "sgci_virement":   sgci_virement,
        "virement_data":   virement_data or {},
        "frais_min":       frais_min,
        "frais_data":      frais_min,
        "rn_data":         rn_data,
        "pnb_data":        pnb_data,
        "roe_data":        roe_data,
        "marge_nette_data":marge_nette_data,
        "coeff_expl_data": coeff_expl_data,
        "cout_r_pnb_data": cout_r_pnb_data,
        "roa_data":        roa_data,
        "credits_data":    credits_data,
        "depots_data":     depots_data,
        "interets_data":   interets_data,
        "commissions_data":commissions_data,
        "autres_prod_data":autres_prod_data,
        "rbe_data":        rbe_data,
        "re_data":         re_data,
    }


def resilience_data(anx=3):
    """Ratios de résilience / solidité bancaire par banque.
    Même principe que kpis_vue_ensemble : chaque banque utilise SON ANx (sa propre année)."""
    anx_c   = max(1, min(3, anx))
    _series = resultat_net_series()  # cached

    # Année cible par banque (ses 3 dernières années disponibles)
    bank_target = {}
    for bank, yr_data in _series.items():
        bank_years = sorted(yr_data.keys())
        last3 = bank_years[-3:] if len(bank_years) >= 3 else bank_years
        if anx_c <= len(last3):
            bank_target[bank] = last3[anx_c - 1]
        elif last3:
            bank_target[bank] = last3[-1]

    target_years_set = set(bank_target.values())
    if not target_years_set:
        return {b: {} for b in BANKS}

    rows = query(
        """
        SELECT banque, libelle, montant, annee_donnee FROM ef_indicateurs
        WHERE is_primary = TRUE
          AND (
              libelle ILIKE %s OR libelle ILIKE %s OR libelle ILIKE %s
              OR libelle ILIKE %s OR libelle ILIKE %s OR libelle ILIKE %s
          )
          AND annee_donnee = ANY(%s)
        ORDER BY banque, libelle
        """,
        ("%capital%", "%fonds propres%", "%ratio%", "%solvabilit%",
         "%liquidit%", "%tier%", list(target_years_set)),
    )
    result = {b: {} for b in BANKS}
    for r in rows:
        b = r["banque"]
        if r["annee_donnee"] != bank_target.get(b):
            continue
        if r["montant"] is not None:
            result[b][r["libelle"]] = float(r["montant"])
    return result


def rn_by_anx(anx=3):
    """RN par banque pour l'ANx demandé — toutes les 7 banques (données les plus récentes ≤ ANx year).
    anx = index dans la fenêtre 3 ans (1=AN1, 2=AN2, 3=AN3) — même logique que kpis_vue_ensemble.
    Retourne {bank: {"montant": float, "annee": int}}."""
    yr_rows = query(
        "SELECT DISTINCT annee_donnee FROM ef_indicateurs WHERE is_primary=TRUE ORDER BY annee_donnee DESC"
    )
    all_years = [r["annee_donnee"] for r in yr_rows] if yr_rows else []
    global_3    = sorted(all_years[:3])
    anx_c       = max(1, min(3, anx))
    target_year = global_3[anx_c - 1] if len(global_3) >= anx_c else (global_3[-1] if global_3 else 2025)

    rows = query(
        """
        SELECT DISTINCT ON (banque) banque, annee_donnee, montant
        FROM ef_indicateurs
        WHERE (libelle ILIKE %s OR libelle ILIKE %s)
          AND libelle NOT ILIKE %s
          AND is_primary = TRUE
          AND annee_donnee <= %s
        ORDER BY banque, annee_donnee DESC,
          CASE WHEN libelle ~ '^[[:ascii:]]+$' THEN 0 ELSE 1 END,
          montant DESC
        """,
        ("%sultat%net%", "%exercice%", "%avant%imp%", target_year),
    )
    if rows:
        return {r["banque"]: {"montant": float(r["montant"]), "annee": r["annee_donnee"]} for r in rows}
    return {b: {"montant": v, "annee": 2025} for b, v in MOCK_RN_2025.items()}


def roe_by_anx(anx=3):
    """ROE = RN / Capitaux propres × 100 — Formule #6 FORMULES_ET_SOURCES.
    Retourne {bank: roe_pct}."""
    yr_rows = query(
        "SELECT DISTINCT annee_donnee FROM ef_indicateurs WHERE is_primary=TRUE ORDER BY annee_donnee DESC"
    )
    all_years = [r["annee_donnee"] for r in yr_rows] if yr_rows else []
    avail = sorted(all_years[:anx])
    target_year = avail[-1] if avail else 2025

    rn = rn_by_anx(anx)

    cp_rows = query(
        """
        SELECT DISTINCT ON (banque) banque, montant
        FROM ef_indicateurs
        WHERE libelle ILIKE %s AND is_primary=TRUE AND annee_donnee <= %s
        ORDER BY banque, annee_donnee DESC,
          CASE WHEN libelle ~ '^[[:ascii:]]+$' THEN 0 ELSE 1 END
        """,
        ("%capitaux%propres%", target_year),
    )
    cp = {r["banque"]: float(r["montant"]) for r in cp_rows} if cp_rows else {}

    result = {}
    for bank, d in rn.items():
        rn_val = d["montant"]
        cp_val = cp.get(bank)
        if cp_val and cp_val > 0:
            result[bank] = round(rn_val / cp_val * 100, 1)
    return result


def croissance_series():
    """Taux de croissance AN1→AN3 par banque — Formule #1 FORMULES_ET_SOURCES.
    Utilise la première et la dernière année de la fenêtre 3 ans par banque (7 banques).
    Conforme au doc : SGCI +4.2% → #6/7 → score 29/100.

    Retronque explicitement à 3 ans (comme ef_cout_risque_3ans/kpis_vue_ensemble) au lieu
    de faire confiance à is_primary pour ne JAMAIS renvoyer plus de 3 années — trouvé le
    2026-07-14 : is_primary a eu un bug de fenêtre glissante (4 banques avec 4 années
    actives au lieu de 3), corrigé en base, mais cette fonction ne se protégeait pas elle-
    même contre une récidive future du même bug en amont."""
    series = resultat_net_series()  # {bank: {year: value}}
    growths = {}
    for bank, year_data in series.items():
        years = sorted(year_data.keys())[-3:]
        if len(years) >= 2:
            v1, v3 = year_data[years[0]], year_data[years[-1]]
            if v1 != 0:
                growths[bank] = round((v3 - v1) / abs(v1) * 100, 1)
    return growths


@lru_cache(maxsize=2)
def ef_cout_risque_3ans():
    """Coût du risque / PNB par banque — VERSION ROBUSTE : moyenne des 3 derniers
    exercices de chaque banque + tendance (le snapshot mono-année est volatil).
    Retourne {bank: {ratios:[(an,val)], moyenne, latest, latest_an, tendance, n}}.

    Pourquoi : ex. SGCI 10,9→13,8→17,0 (hausse) ; NSIA 3,7→0,5→7,5 (volatil).
    La moyenne lisse le bruit, la tendance révèle la trajectoire réelle.
    """
    import unicodedata as _ud
    def _n(s):
        s = (s or "").lower()
        return "".join(c for c in _ud.normalize("NFD", s) if _ud.category(c) != "Mn")
    rows = query(
        """SELECT banque, annee_donnee, libelle, AVG(montant) v
           FROM ef_indicateurs
           WHERE is_primary=TRUE AND montant IS NOT NULL
           GROUP BY banque, annee_donnee, libelle""")
    cr = {}; pnb = {}
    for r in rows:
        lib = _n(r["libelle"]); b = r["banque"]; y = r["annee_donnee"]; v = float(r["v"])
        if "cout" in lib and "risque" in lib:
            cr.setdefault(b, {})[y] = v
        elif ("produit" in lib and "net" in lib and "bancaire" in lib) or lib.strip() == "pnb":
            pnb.setdefault(b, {})[y] = v
    out = {}
    for b in cr:
        yrs = sorted(y for y in cr[b] if pnb.get(b, {}).get(y))
        last3 = yrs[-3:]
        ratios = [(y, round(cr[b][y] / pnb[b][y] * 100, 1)) for y in last3]
        if not ratios:
            continue
        vals = [v for _, v in ratios]
        moy = round(sum(vals) / len(vals), 1)
        tend = "stable"
        if len(vals) >= 2:
            if vals[-1] > vals[0] + 1.5:   tend = "hausse"
            elif vals[-1] < vals[0] - 1.5: tend = "baisse"
        out[b] = {"ratios": ratios, "moyenne": moy, "latest": vals[-1],
                  "latest_an": ratios[-1][0], "tendance": tend, "n": len(vals)}
    return out


def ef_series_all_for_agent():
    """Séries RN complètes pour le contexte agent — toutes banques.
    Retourne {bank: {"series": [{"anx":1,"annee":2023,"montant":97230}, ...], "croissance_an1_an3": 4.2}}.

    Retronque explicitement à 3 ans — même raison que croissance_series() ci-dessus
    (défense en profondeur contre une récidive du bug de fenêtre glissante is_primary)."""
    series = resultat_net_series()
    result = {}
    for bank, year_data in series.items():
        years = sorted(year_data.keys())[-3:]
        pts = [{"anx": i + 1, "annee": yr, "montant": year_data[yr]} for i, yr in enumerate(years)]
        g = None
        if len(years) >= 2:
            v1, v3 = year_data[years[0]], year_data[years[-1]]
            if v1 != 0:
                g = round((v3 - v1) / abs(v1) * 100, 1)
        result[bank] = {"series": pts, "croissance_an1_an3": g}
    return result


def _libelle_section(r):
    """Libellé lisible de la section BCEAO d'une ligne tarifaire.

    DEUX défauts se cachaient derrière le COALESCE(canon_section, section, …) que cette fonction
    remplace :

    1. `canon_section` est un SMALLINT et `section` du TEXT. PostgreSQL refuse de rapprocher les
       deux types, la requête échouait — et comme query() se rabat silencieusement sur une liste
       vide, les fonctions appelantes renvoyaient ZÉRO ligne sans jamais le signaler. C'est ce
       qui vidait la table comparative et, plus grave, tout le contexte CB de l'agent.
    2. Même corrigé, lire la colonne n'aurait rien donné : `canon_section` est NULL sur la
       totalité des lignes en base. Elle n'a jamais été alimentée à l'ingestion.

    La section canonique est donc calculée à la volée, comme partout ailleurs dans ce module, par
    cb_sections.canonical_section() — qui utilise la numérotation du document quand elle est
    fiable et se rabat sur le contenu du libellé sinon.
    """
    try:
        _, _, titre = cb_sections.canonical_section(
            r.get("banque"), r.get("section"), r.get("libelle") or r.get("label"),
            r.get("contexte"))
        if titre:
            return titre
    except Exception:
        pass
    return r.get("section") or "Autres"


def cb_all_for_period(annee=2026, semestre="S1", segment="Particuliers"):
    """Tous les tarifs CB pour une période — utilisé par le contexte agent."""
    rows = query(
        """
        SELECT banque, libelle,
               valeur_propre AS valeur,
               section, contexte,
               montant, est_gratuit
        FROM cb_tarifs
        WHERE annee=%s AND semestre=%s AND segment=%s
          AND is_header = FALSE
        ORDER BY banque, canon_section, libelle
        """,
        (annee, semestre, segment),
    )
    result = {}
    for r in rows:
        result.setdefault(r["banque"], []).append({
            "libelle": r["libelle"],
            "valeur": r["valeur"],
            "categorie": _libelle_section(r),
            "montant": r.get("montant"),
            "est_gratuit": r.get("est_gratuit"),
        })
    return result


def cb_comparatif(annee=2026, semestre="S1", segment="Particuliers"):
    """Table comparative service × banque (vue Analyse → Tarifs).
    Structure attendue par le front : {"rows": [{cat, label, <BANQUE>: {num, raw}}, ...]}.
    Déterministe (DB) — alignement best-effort par (section canonique, libellé)."""
    rows = query(
        """
        SELECT banque, section, contexte,
               TRIM(libelle) AS label, montant, valeur_propre, est_gratuit
        FROM cb_tarifs
        WHERE annee=%s AND semestre=%s AND LOWER(segment)=LOWER(%s)
          AND is_header = FALSE AND section IS NOT NULL
          AND LENGTH(TRIM(libelle)) BETWEEN 5 AND 90
        ORDER BY section, label, banque
        """,
        (annee, semestre, segment),
    )
    table = {}
    for r in rows:
        cat = _libelle_section(r)          # cf. _libelle_section : le COALESCE SQL était invalide
        key = (cat, (r["label"] or "").lower())
        ent = table.setdefault(key, {"cat": cat, "label": r["label"]})
        if r["est_gratuit"]:
            num, raw = 0, "Gratuit"
        elif r["montant"] is not None:
            num, raw = float(r["montant"]), (r["valeur_propre"] or str(r["montant"]))
        else:
            num, raw = None, (r["valeur_propre"] or "—")
        ent[r["banque"]] = {"num": num, "raw": raw}
    return {"rows": list(table.values()), "annee": annee, "semestre": semestre, "segment": segment}


def invalidate_cb_cache():
    """Vider le cache CB (utile après rechargement des données)."""
    frais_tenue_compte.cache_clear()
    frais_tenue_compte_detail.cache_clear()
    cartes_annuelles.cache_clear()
    virements_locaux.cache_clear()
    categories_disponibles.cache_clear()
    tarifs_par_categorie.cache_clear()
    service_toutes_banques.cache_clear()
    cb_imputations.cache_clear()


# ────────────────────────────────────────────────────────────────────────────
# ANALYSES STRATÉGIQUES CB — 6 questions management
# ────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=16)
def cb_analyse_q1(segment="Particuliers"):
    """Q1 : Evolution 3 ans — volume de services et niveau de prix par banque.

    n_services : même périmètre qualité que cb_evolution_details (section IS NOT NULL,
    longueur 8–110 chars, type_valeur tarifaire) pour que les deltas du graphique soient
    cohérents avec les apparus/disparus affichés dans le détail évolution.
    """
    rows = query(
        """
        SELECT banque, annee, semestre,
               COUNT(DISTINCT libelle) FILTER (
                   WHERE is_header = FALSE
                     AND LENGTH(TRIM(libelle)) BETWEEN 8 AND 110
                     AND type_valeur IN ('MONTANT_FCFA','GRATUIT','TAUX_%%','SUR_DEMANDE')
               ) AS n_services,
               COUNT(DISTINCT libelle) FILTER (
                   WHERE is_header = FALSE
               ) AS n_services_brut,
               COUNT(*) FILTER (WHERE est_gratuit = TRUE AND is_header = FALSE) AS n_gratuit,
               ROUND(AVG(montant) FILTER (
                   WHERE type_valeur = 'MONTANT_FCFA' AND montant > 0
               )::numeric) AS montant_moyen,
               ROUND(MIN(montant) FILTER (
                   WHERE type_valeur = 'MONTANT_FCFA' AND montant > 0
               )::numeric) AS montant_min,
               ROUND(MAX(montant) FILTER (
                   WHERE type_valeur = 'MONTANT_FCFA' AND montant > 0
               )::numeric) AS montant_max
        FROM cb_tarifs
        WHERE LOWER(segment) = LOWER(%s)
          AND is_header = FALSE
        GROUP BY banque, annee, semestre
        ORDER BY banque, annee, semestre
        """,
        (segment,),
    )
    return [dict(r) for r in rows]


@lru_cache(maxsize=32)
def cb_evolution_details(segment="Particuliers", banque="SGCI"):
    """Q1 détail : services apparus, disparus et re-tarifés pour une banque donnée."""
    # Première et dernière période disponibles
    periodes = query(
        "SELECT DISTINCT annee, semestre FROM cb_tarifs "
        "WHERE LOWER(segment)=LOWER(%s) ORDER BY annee, semestre",
        (segment,),
    )
    if len(periodes) < 2:
        return {"apparus": [], "disparus": [], "reprices": [], "debut": "", "fin": ""}
    fa, fs = periodes[0]["annee"], periodes[0]["semestre"]
    la, ls = periodes[-1]["annee"], periodes[-1]["semestre"]

    # Années intermédiaires STRICTEMENT entre fa et la (ex: 2025 pour fa=2024 la=2026)
    # N'inclut PAS fa (l'année de référence) — sinon la corroboration contredirait NOT EXISTS
    inter_years = sorted({p["annee"] for p in periodes
                          if p["annee"] > fa and p["annee"] < la})

    # ── Apparus : présents en (la,ls) mais absents en (fa,fs) ────────────────
    # Règle 1 — type_valeur : seulement les vrais services tarifés.
    #   Élimine 'NUMERIQUE' (J-1, J+2…) et entrées purement informationnelles.
    # Règle 2 — NOT EXISTS libellé seul (niveau concept) :
    #   Si "Remise de chèque même banque" existait en 2024 sous une section
    #   différente (reclassification OCR), on ne le compte pas comme nouveau.
    # Règle 3 — Corroboration période intermédiaire (2025) :
    #   Un vrai nouveau service doit exister dans au moins une période entre
    #   2024 et 2026. Élimine les artefacts OCR ponctuels d'une seule période.
    _app_sql = (
        "SELECT DISTINCT n.libelle, "
        "       n.section, "
        "       COALESCE(n.contexte, '') AS contexte, "
        "       n.valeur_propre, n.montant, n.est_gratuit, n.type_valeur, n.unite "
        "FROM cb_tarifs n "
        "WHERE n.banque=%s AND n.annee=%s AND n.semestre=%s "
        "  AND LOWER(n.segment)=LOWER(%s) AND n.is_header=FALSE "
        "  AND n.section IS NOT NULL "
        "  AND LENGTH(TRIM(n.libelle)) BETWEEN 8 AND 110 "
        "  AND n.type_valeur IN ('MONTANT_FCFA','GRATUIT','TAUX_%%','SUR_DEMANDE') "
        "  AND NOT EXISTS ( "
        "      SELECT 1 FROM cb_tarifs o "
        "      WHERE o.banque=%s AND o.annee=%s AND o.semestre=%s "
        "        AND LOWER(o.segment)=LOWER(%s) "
        # Matching anti-faux-positifs OCR : exact OU très similaire (trigram >0.7).
        # Seuil élevé : ne masque que les vraies variations de formatage, pas les vrais nouveaux.
        "        AND ( LOWER(TRIM(o.libelle))=LOWER(TRIM(n.libelle)) "
        "           OR similarity(LOWER(TRIM(o.libelle)), LOWER(TRIM(n.libelle))) > 0.7 ) "
        "  ) "
    )
    _app_params = [banque, la, ls, segment, banque, fa, fs, segment]
    _app_sql += "ORDER BY n.section, n.libelle LIMIT 200"
    apparus = query(_app_sql, tuple(_app_params))

    # ── Disparus : présents en (fa,fs) mais absents en (la,ls) ───────────────
    # NOT EXISTS sans is_header sur la cible : un service devenu en-tête (is_header=TRUE)
    # en 2026 n'est PAS réellement disparu.
    # OR LIKE : si le libellé 2026 COMMENCE PAR le libellé 2024, c'est le même service
    # avec une description enrichie dans la nouvelle extraction (ex. "Rappel plus" →
    # "Rappel plus Le montant minimum du crédit est de 600 000 F CFA...")
    disparus = query(
        "SELECT DISTINCT o.libelle, "
        "       o.section, "
        "       COALESCE(o.contexte, '') AS contexte, "
        "       o.valeur_propre, o.montant, o.est_gratuit, o.type_valeur, o.unite "
        "FROM cb_tarifs o "
        "WHERE o.banque=%s AND o.annee=%s AND o.semestre=%s "
        "  AND LOWER(o.segment)=LOWER(%s) AND o.is_header=FALSE "
        "  AND o.section IS NOT NULL "
        "  AND LENGTH(TRIM(o.libelle)) BETWEEN 8 AND 110 "
        "  AND o.type_valeur IN ('MONTANT_FCFA','GRATUIT','TAUX_%%','SUR_DEMANDE') "
        "  AND NOT EXISTS ( "
        "      SELECT 1 FROM cb_tarifs n "
        "      WHERE n.banque=%s AND n.annee=%s AND n.semestre=%s "
        "        AND LOWER(n.segment)=LOWER(%s) "
        # Matching anti-faux-positifs OCR : exact, OU préfixe enrichi, OU très similaire (>0.7).
        # Seuil élevé : ne masque que les variations de formatage, garde les vrais retraits.
        "        AND (LOWER(TRIM(n.libelle))=LOWER(TRIM(o.libelle)) "
        "          OR LOWER(n.libelle) LIKE LOWER(TRIM(o.libelle)) || '%%' "
        "          OR similarity(LOWER(TRIM(n.libelle)), LOWER(TRIM(o.libelle))) > 0.7 ) "
        "  ) "
        "ORDER BY o.section, o.libelle LIMIT 100",
        (banque, fa, fs, segment, banque, la, ls, segment),
    )

    # Re-tarifés : même (libelle + contexte + section), montant différent entre deux périodes
    # DISTINCT ON : une seule ligne par service (la variation la plus forte en valeur absolue)
    # Filtre OCR : section IS NOT NULL + LENGTH 8–110 sur les deux périodes comparées
    reprices = query(
        """
        SELECT DISTINCT ON (o.libelle, COALESCE(o.contexte,''), COALESCE(o.section,''), o.rang)
               o.libelle,
               o.section,
               n.section AS section_actuelle,
               o.rang,
               COALESCE(o.contexte, '') AS contexte,
               COALESCE(n.contexte, '') AS contexte_actuelle,
               o.montant AS montant_avant, n.montant AS montant_apres,
               CASE WHEN o.montant>0
                    THEN ROUND(((n.montant-o.montant)::numeric/o.montant)*100)
                    ELSE NULL END AS delta_pct
        FROM cb_tarifs o
        JOIN cb_tarifs n
          ON n.banque=%s AND n.annee=%s AND n.semestre=%s
         AND LOWER(n.segment)=LOWER(%s) AND n.is_header=FALSE
         AND LOWER(TRIM(n.libelle))=LOWER(TRIM(o.libelle))
         AND n.rang=o.rang
         AND n.montant IS NOT NULL AND n.montant<>o.montant
         AND n.montant >= 100
         AND n.section IS NOT NULL
         AND LENGTH(TRIM(n.libelle)) BETWEEN 8 AND 110
        WHERE o.banque=%s AND o.annee=%s AND o.semestre=%s
          AND LOWER(o.segment)=LOWER(%s)
          AND o.montant IS NOT NULL AND o.montant >= 100
          AND o.section IS NOT NULL
          AND LENGTH(TRIM(o.libelle)) BETWEEN 8 AND 110
          AND ABS((n.montant-o.montant)::numeric/o.montant)*100 <= 280
          AND NOT EXISTS (
              SELECT 1 FROM cb_tarifs stable
              WHERE stable.banque=n.banque AND stable.annee=n.annee AND stable.semestre=n.semestre
                AND LOWER(stable.segment)=LOWER(n.segment)
                AND LOWER(TRIM(stable.libelle))=LOWER(TRIM(o.libelle))
                AND stable.montant=o.montant
                AND stable.rang=o.rang
          )
          AND NOT EXISTS (
              SELECT 1 FROM cb_tarifs preexist
              WHERE preexist.banque=o.banque AND preexist.annee=o.annee AND preexist.semestre=o.semestre
                AND LOWER(preexist.segment)=LOWER(o.segment)
                AND LOWER(TRIM(preexist.libelle))=LOWER(TRIM(o.libelle))
                AND preexist.montant=n.montant
                AND preexist.rang=o.rang
          )
        ORDER BY o.libelle, COALESCE(o.contexte,''), COALESCE(o.section,''), o.rang,
                 ABS(n.montant-o.montant) DESC
        LIMIT 80
        """,
        (banque, la, ls, segment, banque, fa, fs, segment),
    )

    import re as _re

    import unicodedata as _ud

    _STOPWORDS = {'les','des','une','sur','par','aux','pour','avec','dans','est',
                  'son','ses','leur','qui','que','par','pas','plus','tout','tous',
                  'bon','bas','haut','meme','tres','bien','sans','entre','avant'}

    def _nl(s):
        # Réunit les mots coupés par tiret+espace (artefact OCR de coupure de ligne)
        s = _re.sub(r'\-\s+', '', (s or '').lower())
        # Normalise les accents pour la comparaison floue (é=e, è=e, etc.)
        s = _ud.normalize('NFKD', s).encode('ascii', 'ignore').decode()
        return _re.sub(r'[\s\-\.\,;/()\[\]<>=]+', ' ', s).strip()

    def _kw(s):
        """Mots clés significatifs : longueur > 2, non-numériques, hors stop words."""
        return {w for w in _nl(s).split()
                if len(w) > 2 and not w.isdigit() and w not in _STOPWORDS}

    def _overlap(wa, wb):
        if not wa or not wb: return 0.0
        exact = len(wa & wb)
        # Gère les troncatures OCR : "porte" (2024 tronqué) vs "portefeuille" (2026 complet)
        # Vérifie les deux sens : a préfixe de b OU b préfixe de a (longueur min 4 chars)
        prefix = sum(1 for a in (wa - wb) for b in (wb - wa)
                     if min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)))
        return (exact + prefix) / max(len(wa), len(wb))

    # Baseline individuelle — tous les libellés 2024 (y compris section=None et is_header=True)
    _base_rows = query(
        "SELECT DISTINCT libelle FROM cb_tarifs "
        "WHERE banque=%s AND annee=%s "
        "  AND LENGTH(TRIM(libelle)) >= 8",
        (banque, fa),
    )
    _base_kw = [_kw(r["libelle"]) for r in _base_rows]

    # Baseline fusionnée par contexte — recolle les fragments OCR multi-lignes.
    # Ex : "• Frais de dossier (un..." + "caisse)T2" → libellé reconstitué.
    # Un fragment commence par minuscule ou ) quand le prétraitement a coupé la ligne.
    _ctx_rows = query(
        "SELECT contexte, libelle, montant FROM cb_tarifs "
        "WHERE banque=%s AND annee=%s AND semestre=%s "
        "  AND LOWER(segment)=LOWER(%s) AND section IS NULL "
        "  AND contexte IS NOT NULL AND LENGTH(TRIM(libelle)) >= 3 "
        "ORDER BY contexte, id",
        (banque, fa, fs, segment),
    )
    _frag_map: dict = {}  # ctx → {lib, montant} du fragment courant
    _frag_services: list = []  # services reconstitués (lib_merged, montant, ctx)
    for r in _ctx_rows:
        ctx = (r["contexte"] or "").strip()
        lib = (r["libelle"] or "").strip()
        mnt = r["montant"]
        first = lib[0] if lib else ""
        if ctx in _frag_map and (first.islower() or first == ")"):
            # Continuation — coller avec espace
            prev = _frag_map[ctx]
            _frag_map[ctx] = {"lib": prev["lib"].rstrip() + " " + lib, "montant": prev["montant"] or mnt}
        else:
            if ctx in _frag_map:
                _frag_services.append(_frag_map[ctx] | {"ctx": ctx})
            _frag_map[ctx] = {"lib": lib, "montant": mnt}
    for v in _frag_map.values():
        _frag_services.append(v)
    for svc in _frag_services:
        kws = _kw(svc["lib"])
        if kws:
            _base_kw.append(kws)

    # Seuil de recouvrement : ≥ 65% des mots-clés en commun = même service (OCR différent)
    OVERLAP_THRESH = 0.65

    app_list = [dict(r) for r in apparus]
    dis_list = [dict(r) for r in disparus]
    # Artefacts OCR : fragment incomplet commençant par une minuscule (ex. "la même banque)")
    dis_list = [d for d in dis_list if not d["libelle"].strip()[:1].islower()]
    app_norms = {_nl(r["libelle"]) for r in app_list}
    dis_norms = {_nl(r["libelle"]) for r in dis_list}

    # 1) Retirer les services présents dans les deux listes (même service, OCR différent)
    #    _nl() réunit les mots coupés par tiret+espace avant de comparer
    app_list = [r for r in app_list if _nl(r["libelle"]) not in dis_norms]
    dis_list = [r for r in dis_list if _nl(r["libelle"]) not in app_norms]

    # 1b) Déduplication fuzzy croisée entre app_list et dis_list :
    #     un "apparu" qui fuzzy-matche un "disparu" = renommage du même service
    #     → retirer des deux listes (ni apparu ni disparu, juste reformulé)
    #     Ex. : "Découvert ACT" (dis) ↔ "Découvert Avance Conventionnelle de Trésorerie (ACT)" (app)
    # _overlap() utilise max(len) → trop pénalisant quand un libellé est beaucoup plus court
    # (ex. "Découvert ACT" 2 mots vs 5 mots → 2/5=0.4 < seuil).
    # _sub_ov() utilise min(len) = mesure sous-ensemble : si tous les mots du libellé court
    # sont dans le long → 1.0 → détecte les abréviations dans les deux sens.
    def _sub_ov(wa, wb):
        if not wa or not wb: return 0.0
        return len(wa & wb) / min(len(wa), len(wb))

    _dis_kw_list = [_kw(d["libelle"]) for d in dis_list]
    _app_kw_raw  = [_kw(r["libelle"]) for r in app_list]
    # Calculer les masques d'abord (avant de modifier les listes) — évite le problème
    # d'ordre : si on filtre app_list en premier, _app_kw_raw est déjà réduit quand
    # on filtre dis_list, et les paires disparaissent dans le vide.
    _app_keeps = [not any(_sub_ov(akw, dkw) >= OVERLAP_THRESH for dkw in _dis_kw_list)
                  for akw in _app_kw_raw]
    _dis_keeps = [not any(_sub_ov(dkw, akw) >= OVERLAP_THRESH for akw in _app_kw_raw)
                  for dkw in _dis_kw_list]
    app_list = [r for r, keep in zip(app_list, _app_keeps) if keep]
    dis_list = [d for d, keep in zip(dis_list, _dis_keeps) if keep]

    # Fuzzy filter : retirer les "disparus" dont le libellé flou-matche (≥65%) un libellé 2026
    # Utilise _sub_ov (min-based) et non _overlap (max-based) pour détecter les sous-ensembles :
    # ex. "Taux d'intérêt durée comprise entre 3 et 10 ans" (5 mots) ↔ "durée comprise entre 3
    # et 10 ans" (3 mots, section=NULL en 2026) → _sub_ov = 3/3 = 1.0, _overlap = 3/5 = 0.6 (raté).
    _new_libs_2026 = query(
        "SELECT DISTINCT LOWER(TRIM(libelle)) AS lib FROM cb_tarifs "
        "WHERE banque=%s AND annee=%s AND semestre=%s AND LOWER(segment)=LOWER(%s) "
        "  AND is_header=FALSE "
        "  AND LENGTH(TRIM(libelle)) >= 5",
        (banque, la, ls, segment),
    )
    _new_kw_2026 = [_kw(r["lib"]) for r in _new_libs_2026 if r["lib"] and _kw(r["lib"])]
    dis_list = [
        d for d in dis_list
        if not any(_sub_ov(_kw(d["libelle"]), nkw) >= OVERLAP_THRESH for nkw in _new_kw_2026)
    ]

    # Enrichir chaque service retiré avec la liste des concurrents qui l'ont encore en (la,ls)
    if dis_list:
        _dis_lower = list({d["libelle"].lower().strip() for d in dis_list})
        _ph = ','.join(['%s'] * len(_dis_lower))
        _conc_rows = query(
            "SELECT DISTINCT banque, LOWER(TRIM(libelle)) AS lib_low "
            "FROM cb_tarifs "
            "WHERE annee=%s AND semestre=%s AND LOWER(segment)=LOWER(%s) "
            "  AND banque<>%s AND is_header=FALSE "
            "  AND LOWER(TRIM(libelle)) IN (" + _ph + ")",
            (la, ls, segment, banque, *_dis_lower),
        )
        _conc_map: dict = {}
        for r in _conc_rows:
            _conc_map.setdefault(r["lib_low"], []).append(r["banque"])
        for d in dis_list:
            d["concurrent_ont"] = sorted(_conc_map.get(d["libelle"].lower().strip(), []))

    # 2a) Filtrer les artefacts structurels OCR :
    #     - libellé commençant par un chiffre = bracket de plage (ex: "0 <=M <= 1 Mos")
    #     - libellé entièrement en majuscules = en-tête non capturé par is_header
    #     - libellé commençant par "- " = sous-ligne bullet-point (ex: "- Salaire entre...")
    #     - contexte commençant par "- " = ligne orpheline dont le contexte est un bracket OCR
    #     - valeur_propre contenant "|" = contenu de tableau markdown collé par erreur d'extraction
    app_list = [
        r for r in app_list
        if not (r["libelle"].strip() and r["libelle"].strip()[0].isdigit())
        and r["libelle"] != r["libelle"].upper()
        and not r["libelle"].strip().startswith('- ')
        and not r.get("contexte", "").strip().startswith('- ')
        and '|' not in (r.get("valeur_propre", "") or "")
    ]

    # 2b) Matching flou : retirer les apparus sémantiquement similaires à un service
    #     de l'année de référence (même service rendu différemment par l'OCR)
    _app_kw_list = [_kw(r["libelle"]) for r in app_list]
    app_list = [
        r for r, rkw in zip(app_list, _app_kw_list)
        if not any(_overlap(rkw, bkw) >= OVERLAP_THRESH for bkw in _base_kw)
    ]

    # 3) Dédoublonnage par libellé normalisé (même service dans plusieurs sections)
    _seen = set()
    _app_deduped = []
    for r in app_list:
        _key = _nl(r["libelle"])[:50]
        if _key not in _seen:
            _seen.add(_key)
            _app_deduped.append(r)
    app_list = _app_deduped

    # Filtre cross-produit : si la section a changé ET le contexte est incompatible → faux reprice
    # Ex : "Frais de dossier" Prêt Personnel (10.3.3) apparié avec Découvert (7.3.7)
    def _ctx_overlap(r):
        if r.get("section") == r.get("section_actuelle"):
            return True  # même section, pas de risque cross-produit
        c_old = r.get("contexte", "")
        c_new = r.get("contexte_actuelle", "")
        if not c_old or not c_new:
            return True  # pas de contexte = on ne peut pas filtrer
        return _overlap(_kw(c_old), _kw(c_new)) >= 0.25
    reprices = [r for r in reprices if _ctx_overlap(r)]

    # Reprices sur fragments OCR (section=None en 2024, libellés reconstitués)
    # Ex : "Frais de dossier (uniquement par caisse)T2" mnt=7000 → 2026 mnt=6000
    _reprices_list = [dict(r) for r in reprices]
    if _frag_services:
        _new_rows_all = query(
            "SELECT libelle, section, COALESCE(contexte,'') AS contexte, montant "
            "FROM cb_tarifs "
            "WHERE banque=%s AND annee=%s AND semestre=%s "
            "  AND LOWER(segment)=LOWER(%s) AND is_header=FALSE "
            "  AND section IS NOT NULL AND montant >= 100 "
            "  AND LENGTH(TRIM(libelle)) BETWEEN 8 AND 110",
            (banque, la, ls, segment),
        )
        # Dedup par (montant_avant, section_ou_contexte, libelle)
        # — section=NULL : utilise contexte[:20] comme discriminant
        def _rep_key(mnt_av, sec, ctx, lib):
            loc = (sec or ctx or '')[:20]
            return f"{mnt_av}|{loc}|{_nl(lib)[:40]}"
        _seen_rep = {_rep_key(r.get("montant_avant"), r.get("section"),
                               r.get("contexte",""), r["libelle"])
                     for r in _reprices_list}
        # Libellés déjà couverts par le SQL — le fragment scan ne duplique pas
        _sql_covered_kw = [_kw(r.get("libelle", "")) for r in reprices if r.get("libelle")]
        for svc in _frag_services:
            if not svc.get("montant") or svc["montant"] < 100:
                continue
            svc_kw = _kw(svc.get("lib",""))
            if not svc_kw:
                continue
            for nw in _new_rows_all:
                if nw.get("montant") is None or nw["montant"] == svc["montant"]:
                    continue
                nk = _rep_key(svc["montant"], nw.get("section"), nw.get("contexte",""), nw["libelle"])
                if nk in _seen_rep:
                    continue
                if _overlap(svc_kw, _kw(nw["libelle"])) >= OVERLAP_THRESH:
                    # Skip si le SQL a déjà un reprice pour ce libellé
                    nw_kw = _kw(nw["libelle"])
                    if any(_overlap(nw_kw, sql_kw) >= OVERLAP_THRESH for sql_kw in _sql_covered_kw):
                        continue
                    # Montant stable : l'ancienne valeur existe encore en 2026 pour ce service
                    if any(nw2.get("montant") == svc["montant"]
                           and _overlap(svc_kw, _kw(nw2["libelle"])) >= OVERLAP_THRESH
                           for nw2 in _new_rows_all):
                        continue
                    delta = round((nw["montant"] - svc["montant"]) / svc["montant"] * 100)
                    if abs(delta) <= 280:
                        _seen_rep.add(nk)
                        _reprices_list.append({
                            "libelle":      nw["libelle"],
                            "section":      nw["section"],
                            "contexte":     nw["contexte"],
                            "montant_avant": svc["montant"],
                            "montant_apres": nw["montant"],
                            "delta_pct":    delta,
                        })

    # Enrichir chaque apparu avec sa date de première apparition réelle dans la BD
    # (la période (la, ls) est celle du snapshot courant, mais le service peut être
    # présent depuis (la-1, ls) ou avant → l'analyste voit "présent depuis 2025 S1"
    # plutôt que "apparu en 2026 S1" pour un service introduit en 2025)
    if app_list:
        _app_libs_low = list({r["libelle"].lower().strip() for r in app_list})
        _ph_a = ','.join(['%s'] * len(_app_libs_low))
        _debut_rows = query(
            "SELECT LOWER(TRIM(libelle)) AS lib, annee, semestre "
            "FROM cb_tarifs "
            "WHERE banque=%s AND LOWER(segment)=LOWER(%s) "
            "  AND is_header=FALSE "
            "  AND LOWER(TRIM(libelle)) IN (" + _ph_a + ") "
            "ORDER BY annee, semestre",
            (banque, segment, *_app_libs_low),
        )
        _debut_map: dict = {}
        for r in _debut_rows:
            if r["lib"] not in _debut_map:
                _debut_map[r["lib"]] = (r["annee"], r["semestre"])
        for a in app_list:
            debut = _debut_map.get(a["libelle"].lower().strip())
            if debut:
                a["depuis_annee"]    = debut[0]
                a["depuis_semestre"] = debut[1]

    # Enrichissement axe BCEAO (même taxonomie que Q3/Q5) : chaque service est
    # classé dans l'un des 8 axes (Packages, Cartes, Épargne, Crédits, Assurances,
    # Digital, Marchés, Autres) pour un affichage organisé et cohérent dans tout le dashboard.
    def _add_axe(rows):
        for r in rows:
            aid = cb_axes.classify_axe(r.get("libelle", ""), r.get("contexte", ""))
            r["axe_id"]    = aid
            r["axe_label"] = cb_axes.AXES.get(aid, "Autres Services Distinctifs")
            r["axe_icon"]  = cb_axes.AXE_ICONS.get(aid, "🔧")
            r["axe_color"] = cb_axes.AXE_COLORS.get(aid, "#6B7280")
        return rows

    return {
        "apparus":  _add_axe(app_list),
        "disparus": _add_axe(dis_list),
        "reprices": _add_axe(_reprices_list),
        "debut":    f"{fa} {fs}",
        "fin":      f"{la} {ls}",
    }


@lru_cache(maxsize=4)
def cb_all_evolutions_summary(segment="Particuliers"):
    """Résumé évolution sémantique (nApp, nDis, net) pour toutes les banques.

    Utilisé par le bar chart Q1 pour afficher des deltas cohérents (matching label
    par label) plutôt que le simple comptage brut qui inclut le bruit OCR.
    """
    result = {}
    for b in BANKS:
        try:
            ev = cb_evolution_details(segment=segment, banque=b)
            n_app = len(ev.get("apparus", []))
            n_dis = len(ev.get("disparus", []))
            result[b] = {
                "nApp": n_app, "nDis": n_dis, "net": n_app - n_dis,
                "apparus": [
                    {"libelle": r["libelle"], "section": r.get("section"),
                     "est_gratuit": bool(r.get("est_gratuit", False)),
                     "contexte": r.get("contexte", ""),
                     "montant": r.get("montant"), "type_valeur": r.get("type_valeur"),
                     "unite": r.get("unite"),
                     "axe_id": r.get("axe_id"), "axe_label": r.get("axe_label"),
                     "axe_icon": r.get("axe_icon"), "axe_color": r.get("axe_color")}
                    for r in ev.get("apparus", [])
                ],
            }
        except Exception:
            result[b] = {"nApp": 0, "nDis": 0, "net": None, "apparus": []}
    return result


@lru_cache(maxsize=32)
def cb_analyse_q2(annee=2026, semestre="S1", segment="Particuliers"):
    """Q2 : Nouveaux services SGCI apparus depuis 2024 jusqu'à (annee, semestre) inclus.

    Clé de comparaison : (libelle + section) pour distinguer les sous-produits homonymes.
    Filtre OCR : section IS NOT NULL + longueur 8–110 + pas de libellé commençant par chiffre/symbole.
    """
    rows = query(
        """
        SELECT DISTINCT t_new.libelle, t_new.section,
                        COALESCE(t_new.contexte, '') AS contexte,
                        t_new.annee AS annee_apparition,
                        t_new.valeur_propre, t_new.est_gratuit, t_new.type_valeur
        FROM cb_tarifs t_new
        WHERE t_new.banque = 'SGCI'
          AND t_new.annee > 2024
          AND (t_new.annee < %s OR (t_new.annee = %s AND t_new.semestre <= %s))
          AND t_new.is_header = FALSE
          AND LOWER(t_new.segment) = LOWER(%s)
          AND t_new.section IS NOT NULL
          AND LENGTH(TRIM(t_new.libelle)) BETWEEN 8 AND 110
          AND t_new.type_valeur IN ('MONTANT_FCFA','GRATUIT','TAUX_%%','SUR_DEMANDE','NUMERIQUE')
          AND NOT EXISTS (
              SELECT 1 FROM cb_tarifs t_old
              WHERE t_old.banque = 'SGCI'
                AND t_old.annee = 2024
                AND t_old.is_header = FALSE
                AND LOWER(TRIM(t_old.libelle)) = LOWER(TRIM(t_new.libelle))
          )
        ORDER BY t_new.annee, t_new.section, t_new.libelle
        """,
        (annee, annee, semestre, segment),
    )
    return [dict(r) for r in rows]


@lru_cache(maxsize=32)
def cb_exclusivites_banque(banque="SGCI", annee=2026, semestre="S1", segment="Particuliers"):
    """Services présents chez `banque` mais absents chez TOUTES les autres banques (exclusivité
    de grille), PUIS validés par l'Agent Web (bruit retiré + verdict partage/differenciant/
    non_contredit). REPRODUCTIBLE : déterministe (même DB + même JSON → même résultat).

    Comparaison sémantique : trigram 0.62 + patterns synonymes (virement FCFA ≡ UEMOA, etc.).
    Fonctionne pour N'IMPORTE QUELLE banque (SGCI, BICICI, NSIA, ECOBANK, SIB, BNI, BACI)."""
    rows = query(
        """
        SELECT DISTINCT s.libelle, s.section,
                        COALESCE(s.contexte, '') AS contexte,
                        s.valeur_propre, s.montant, s.est_gratuit, s.type_valeur
        FROM cb_tarifs s
        WHERE s.banque = %s
          AND s.annee = %s AND s.semestre = %s
          AND LOWER(s.segment) = LOWER(%s)
          AND s.is_header = FALSE
          AND s.section IS NOT NULL
          AND LENGTH(TRIM(s.libelle)) BETWEEN 8 AND 110
          AND s.type_valeur IN ('MONTANT_FCFA','GRATUIT','TAUX_%%','SUR_DEMANDE','NUMERIQUE')
          AND s.libelle !~ '\\m[A-Za-z]\\M\\s+\\m[A-Za-z]\\M\\s+\\m[A-Za-z]\\M'
          AND NOT EXISTS (
              SELECT 1 FROM cb_tarifs o
              WHERE o.banque != %s
                AND o.annee = %s AND o.semestre = %s
                AND LOWER(o.segment) = LOWER(%s)
                AND o.is_header = FALSE
                AND o.section IS NOT NULL
                AND LENGTH(TRIM(o.libelle)) BETWEEN 8 AND 110
                AND o.libelle !~ '\\m[A-Za-z]\\M\\s+\\m[A-Za-z]\\M\\s+\\m[A-Za-z]\\M'
                AND (
                    similarity(LOWER(TRIM(o.libelle)), LOWER(TRIM(s.libelle))) > 0.62
                    OR word_similarity(LOWER(TRIM(o.libelle)), LOWER(TRIM(s.libelle))) > 0.7
                    OR word_similarity(LOWER(TRIM(s.libelle)), LOWER(TRIM(o.libelle))) > 0.7
                    OR (
                        LOWER(s.libelle) ~ 'virement.{0,15}(fcfa|f cfa|franc)'
                        AND LOWER(o.libelle) ~ 'virement.{0,30}(uemoa|sica|star|national|interne|agence|tiers)'
                    )
                    OR (
                        LOWER(s.libelle) ~ 'virement.{0,10}euro'
                        AND LOWER(o.libelle) ~ 'virement.{0,30}(euro|swift|hors|international|devis)'
                    )
                )
          )
        ORDER BY s.section, s.libelle
        """,
        (banque, annee, semestre, segment, banque, annee, semestre, segment),
    )
    rows = [dict(r) for r in rows]
    # VALIDATION WEB (Agent Web) : retire le bruit + reclasse (partage/differenciant/non_contredit).
    try:
        import web_facts as _web
        rows = _web.classer_exclusivites(rows)
    except Exception:
        pass
    return rows


def cb_analyse_q3(annee=2026, semestre="S1", segment="Particuliers"):
    """Q3 : exclusivités SGCI (alias historique de cb_exclusivites_banque('SGCI', …))."""
    return cb_exclusivites_banque("SGCI", annee, semestre, segment)


@lru_cache(maxsize=32)
def cb_analyse_q5(annee=2026, semestre="S1", segment="Particuliers"):
    """Q5 : Services présents chez ≥1 concurrent mais absents chez SGCI.

    La comparaison 'SGCI n'a pas ce libellé' reste sur libelle seul (niveau concept).
    Filtre OCR appliqué sur LES DEUX CÔTÉS de la comparaison :
    - Les services concurrents affichés doivent avoir section IS NOT NULL
    - La vérification 'SGCI n'a pas ce service' exclut aussi les artefacts côté SGCI
    """
    rows = query(
        """
        SELECT o.libelle, o.section,
               COALESCE(MAX(o.contexte), '') AS contexte,
               MAX(o.valeur_propre) AS valeur_propre,
               MAX(o.montant) AS montant,
               bool_or(o.est_gratuit) AS est_gratuit,
               MAX(o.type_valeur) AS type_valeur,
               STRING_AGG(DISTINCT o.banque, ', ' ORDER BY o.banque) AS banques_concurrentes,
               COUNT(DISTINCT o.banque) AS nb_banques
        FROM cb_tarifs o
        WHERE o.banque != 'SGCI'
          AND o.annee = %s AND o.semestre = %s
          AND LOWER(o.segment) = LOWER(%s)
          AND o.is_header = FALSE
          AND o.section IS NOT NULL
          AND LENGTH(TRIM(o.libelle)) BETWEEN 8 AND 110
          AND o.type_valeur IN ('MONTANT_FCFA','GRATUIT','TAUX_%%','SUR_DEMANDE','NUMERIQUE')
          AND o.libelle !~ '\\m[A-Za-z]\\M\\s+\\m[A-Za-z]\\M\\s+\\m[A-Za-z]\\M'
          AND NOT EXISTS (
              SELECT 1 FROM cb_tarifs s
              WHERE s.banque = 'SGCI'
                AND s.annee = %s AND s.semestre = %s
                AND s.is_header = FALSE
                AND s.section IS NOT NULL
                AND LENGTH(TRIM(s.libelle)) BETWEEN 8 AND 110
                AND s.libelle !~ '\\m[A-Za-z]\\M\\s+\\m[A-Za-z]\\M\\s+\\m[A-Za-z]\\M'
                AND (
                    similarity(LOWER(TRIM(s.libelle)), LOWER(TRIM(o.libelle))) > 0.62
                    OR word_similarity(LOWER(TRIM(s.libelle)), LOWER(TRIM(o.libelle))) > 0.7
                    OR word_similarity(LOWER(TRIM(o.libelle)), LOWER(TRIM(s.libelle))) > 0.7
                    OR (
                        LOWER(o.libelle) ~ 'virement.{0,30}(uemoa|sica|star|national|interne|agence|tiers)'
                        AND LOWER(s.libelle) ~ 'virement.{0,15}(fcfa|f cfa|franc)'
                    )
                    OR (
                        LOWER(o.libelle) ~ 'virement.{0,30}(euro|swift|hors|international|devis)'
                        AND LOWER(s.libelle) ~ 'virement.{0,10}euro'
                    )
                )
          )
        GROUP BY o.libelle, o.section
        ORDER BY nb_banques DESC, o.section, o.libelle
        """,
        (annee, semestre, segment, annee, semestre),
    )
    return [dict(r) for r in rows]


@lru_cache(maxsize=32)
def cb_libelles_tous(annee=2026, semestre="S1", segment="Particuliers"):
    """Tous les libellés par banque, y compris section IS NULL.

    Utilisé par les routes /api/cb_exclusivites_axes et /api/cb_gaps_axes pour
    l'analyse LLM par axe BCEAO. Inclut les lignes section=NULL (ex. : certains
    packs SGCI, virements) qui étaient invisibles au filtre OCR de Q3/Q5.
    """
    rows = query(
        """
        SELECT banque, libelle,
               COALESCE(section::text, '') AS section,
               COALESCE(contexte, '')      AS contexte,
               COALESCE(montant, 0)        AS montant,
               COALESCE(est_gratuit, FALSE) AS est_gratuit,
               COALESCE(type_valeur, 'SUR_DEMANDE') AS type_valeur,
               COALESCE(unite, '')         AS unite
        FROM cb_tarifs
        WHERE annee = %s AND semestre = %s
          AND LOWER(segment) = LOWER(%s)
          AND is_header = FALSE
          AND LENGTH(TRIM(libelle)) BETWEEN 5 AND 100
          AND type_valeur NOT IN ('NON_APPLICABLE')
          AND """ + _not_segment_sql("libelle") + """
        ORDER BY banque, libelle
        """,
        (annee, semestre, segment),
    )
    result = {}
    for r in rows:
        b = r["banque"]
        if b not in result:
            result[b] = []
        result[b].append(dict(r))
    return result


@lru_cache(maxsize=32)
def cb_analyse_q6(annee=2026, semestre="S1", segment="Particuliers"):
    """Q6 : Classement statistique du marché — qui est le plus cher / moins cher.

    Filtre OCR appliqué pour éviter que des montants aberrants (lignes sans section)
    faussent les moyennes. Seuil montant : 100 F min (évite les valeurs taux ou entiers bruts).

    montant_median (2026-07-24, bug trouvé en creusant l'indice prix de la Projection) :
    montant_moyen (AVG) est une moyenne ARITHMÉTIQUE brute — quelques frais exceptionnels
    mélangés aux tarifs courants (ex. SGCI "Frais d'introduction en bourse" = 10 625 000 F,
    "Frais de dossier" = 1 000 000 F) l'écrasent complètement : constaté en le comparant à
    l'indice prix de cb_serie_temporelle, qui donnait SGCI à 566%/741% du marché — absurde.
    montant_median (PERCENTILE_CONT) n'est PAS sensible à ces quelques valeurs extrêmes et
    reste représentatif du tarif "typique" — utilisé par cb_serie_temporelle pour l'indice
    prix. montant_moyen est CONSERVÉ tel quel (rien d'existant ne doit changer d'affichage)."""
    rows = query(
        """
        SELECT banque,
               COUNT(DISTINCT libelle) FILTER (
                   WHERE is_header = FALSE AND section IS NOT NULL
                   AND LENGTH(TRIM(libelle)) BETWEEN 8 AND 110
               ) AS n_services,
               COUNT(*) FILTER (
                   WHERE est_gratuit = TRUE AND is_header = FALSE
                   AND section IS NOT NULL
               ) AS n_gratuit,
               ROUND(100.0 * COUNT(*) FILTER (
                   WHERE est_gratuit = TRUE AND is_header = FALSE AND section IS NOT NULL
               ) / NULLIF(COUNT(*) FILTER (
                   WHERE is_header = FALSE AND section IS NOT NULL
               ), 0), 1) AS pct_gratuit,
               ROUND(AVG(montant) FILTER (
                   WHERE type_valeur = 'MONTANT_FCFA' AND montant >= 100
                   AND is_header = FALSE AND section IS NOT NULL
               )::numeric) AS montant_moyen,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY montant) FILTER (
                   WHERE type_valeur = 'MONTANT_FCFA' AND montant >= 100
                   AND is_header = FALSE AND section IS NOT NULL
               )::numeric) AS montant_median,
               ROUND(MIN(montant) FILTER (
                   WHERE type_valeur = 'MONTANT_FCFA' AND montant >= 100
                   AND is_header = FALSE AND section IS NOT NULL
               )::numeric) AS montant_min,
               ROUND(MAX(montant) FILTER (
                   WHERE type_valeur = 'MONTANT_FCFA' AND montant >= 100
                   AND is_header = FALSE AND section IS NOT NULL
               )::numeric) AS montant_max
        FROM cb_tarifs
        WHERE annee = %s AND semestre = %s
          AND LOWER(segment) = LOWER(%s)
          AND is_header = FALSE
          AND type_valeur IN ('MONTANT_FCFA', 'GRATUIT', 'TAUX_%%', 'SUR_DEMANDE', 'NUMERIQUE')
        GROUP BY banque
        ORDER BY montant_moyen NULLS LAST
        """,
        (annee, semestre, segment),
    )
    return [dict(r) for r in rows]


def cb_analyse_q6_tous_segments(annee=2026, semestre="S1"):
    """Variante de cb_analyse_q6 SANS filtre segment (2026-07-22, demande explicite du directeur :
    « tous les onglets doivent tenir compte de TOUTES les données » — Particuliers ET Entreprises
    ensemble, pas juste un résumé donné au LLM). Seules deux valeurs de segment existent en base
    (Particuliers, Entreprises) — on les combine ici pour un rang catalogue / gratuité GLOBAUX.
    COUNT(DISTINCT libelle) compte un même nom de service UNE fois même s'il existe dans les deux
    segments (ex. « Frais de tenue de compte ») — c'est le nombre de services DISTINCTS que SGCI
    propose au global, pas une somme artificielle qui doublonnerait les noms partagés."""
    rows = query(
        """
        SELECT banque,
               COUNT(DISTINCT libelle) FILTER (
                   WHERE is_header = FALSE AND section IS NOT NULL
                   AND LENGTH(TRIM(libelle)) BETWEEN 8 AND 110
               ) AS n_services,
               COUNT(*) FILTER (
                   WHERE est_gratuit = TRUE AND is_header = FALSE
                   AND section IS NOT NULL
               ) AS n_gratuit,
               ROUND(100.0 * COUNT(*) FILTER (
                   WHERE est_gratuit = TRUE AND is_header = FALSE AND section IS NOT NULL
               ) / NULLIF(COUNT(*) FILTER (
                   WHERE is_header = FALSE AND section IS NOT NULL
               ), 0), 1) AS pct_gratuit,
               ROUND(AVG(montant) FILTER (
                   WHERE type_valeur = 'MONTANT_FCFA' AND montant >= 100
                   AND is_header = FALSE AND section IS NOT NULL
               )::numeric) AS montant_moyen,
               ROUND(MIN(montant) FILTER (
                   WHERE type_valeur = 'MONTANT_FCFA' AND montant >= 100
                   AND is_header = FALSE AND section IS NOT NULL
               )::numeric) AS montant_min,
               ROUND(MAX(montant) FILTER (
                   WHERE type_valeur = 'MONTANT_FCFA' AND montant >= 100
                   AND is_header = FALSE AND section IS NOT NULL
               )::numeric) AS montant_max
        FROM cb_tarifs
        WHERE annee = %s AND semestre = %s
          AND is_header = FALSE
          AND type_valeur IN ('MONTANT_FCFA', 'GRATUIT', 'TAUX_%%', 'SUR_DEMANDE', 'NUMERIQUE')
        GROUP BY banque
        ORDER BY montant_moyen NULLS LAST
        """,
        (annee, semestre),
    )
    return [dict(r) for r in rows]


@lru_cache(maxsize=8)
def cb_serie_temporelle(segment="Particuliers"):
    """Série temporelle SGCI sur toutes les périodes (pour la vue Évolution).

    Pour chaque (annee, semestre) disponible : rang catalogue SGCI, taux de gratuité
    SGCI, taux de gratuité médian marché, indice prix SGCI vs médiane marché.
    """
    periodes = query(
        """SELECT DISTINCT annee, semestre FROM cb_tarifs
           WHERE LOWER(segment) = LOWER(%s) ORDER BY annee, semestre""",
        (segment,),
    )
    out = []
    for p in periodes:
        annee, sem = p["annee"], p["semestre"]
        stats = cb_analyse_q6(annee, sem, segment)
        if not stats:
            continue
        actifs = [s for s in stats if (s.get("n_services") or 0) > 0]
        if not actifs:
            continue
        par_cat = sorted(actifs, key=lambda s: -(s.get("n_services") or 0))
        sgci = next((s for s in actifs if s["banque"] == "SGCI"), None)
        if not sgci:
            continue
        rang = [s["banque"] for s in par_cat].index("SGCI") + 1
        grats = sorted(float(s["pct_gratuit"]) for s in actifs if s.get("pct_gratuit") is not None)
        med_grat = grats[len(grats) // 2] if grats else 0
        # montant_median (pas montant_moyen) : la moyenne brute est écrasée par quelques frais
        # exceptionnels (bourse, dossiers de gros crédits) mélangés aux tarifs courants — cf.
        # docstring de cb_analyse_q6. La médiane par banque reste représentative du tarif typique.
        moys = sorted(float(s["montant_median"]) for s in actifs if s.get("montant_median"))
        med_moy = moys[len(moys) // 2] if moys else 0
        sgci_moy = float(sgci["montant_median"]) if sgci.get("montant_median") else None
        out.append({
            "periode": f"{annee} {sem}",
            "annee": annee, "semestre": sem,
            "sgci_rang": rang, "nb_banques": len(actifs),
            "sgci_pct_grat": float(sgci["pct_gratuit"]) if sgci.get("pct_gratuit") is not None else 0,
            "marche_pct_grat": round(med_grat, 1),
            "sgci_n_services": sgci.get("n_services") or 0,
            "indice_prix": round(sgci_moy / med_moy * 100) if (sgci_moy and med_moy) else None,
        })
    return out


@lru_cache(maxsize=8)
def cb_rattrapage_depassement(segment="Particuliers"):
    """Pour chaque concurrent : ses NOUVEAUX services (depuis 2024) sont-ils déjà offerts
    par SGCI (= RATTRAPAGE, il comble son retard) ou absents de SGCI (= DÉPASSEMENT, il
    creuse un écart) ?

    Cohérent avec l'affichage : réutilise les apparus OFFICIELS (cb_all_evolutions_summary,
    même comptage que les badges) puis teste la présence chez SGCI par similarité (difflib,
    comme la logique des gaps). 100% dynamique, aucun chiffre en dur.
    """
    import unicodedata as _ud
    from difflib import SequenceMatcher

    def _nrm(s):
        s = _ud.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()
        return " ".join(s.replace("-", " ").split())

    periodes = query(
        "SELECT DISTINCT annee, semestre FROM cb_tarifs WHERE LOWER(segment)=LOWER(%s) "
        "ORDER BY annee, semestre", (segment,))
    if len(periodes) < 2:
        return []
    la, ls = periodes[-1]["annee"], periodes[-1]["semestre"]

    # Catalogue SGCI actuel (référence pour "déjà offert")
    sgci_rows = query(
        "SELECT DISTINCT libelle FROM cb_tarifs WHERE banque='SGCI' AND annee=%s AND semestre=%s "
        "AND LOWER(segment)=LOWER(%s) AND is_header=FALSE AND LENGTH(TRIM(libelle))>=6",
        (la, ls, segment))
    sgci_norms = [_nrm(r["libelle"]) for r in sgci_rows if r["libelle"]]

    def _sgci_a_deja(lib):
        n = _nrm(lib)
        if not n:
            return False
        return any(SequenceMatcher(None, n, s).ratio() >= 0.6 for s in sgci_norms)

    evo = cb_all_evolutions_summary(segment)   # apparus OFFICIELS (lru_cached)
    # Taille de catalogue actuelle par banque (pour le taux d'innovation) — source unique
    cat = {r["banque"]: int(r.get("n_services") or 0) for r in cb_analyse_q6(la, ls, segment)}
    out = []
    for b in BANKS:
        if b == "SGCI":
            continue
        apparus = evo.get(b, {}).get("apparus", [])
        total = len(apparus)
        rattr = sum(1 for a in apparus if _sgci_a_deja(a.get("libelle", "")))
        catalogue = cat.get(b, 0)
        out.append({"banque": b, "total": total,
                    "rattrapage": rattr, "depassement": total - rattr,
                    "catalogue": catalogue,
                    "taux": round(total / catalogue * 100) if catalogue else 0})
    out.sort(key=lambda x: -x["depassement"])
    return out


@lru_cache(maxsize=8)
def cb_innovation_vs_finance(segment="Particuliers"):
    """Croisement Volonté × Moyens : innovation (nouveaux services CB) vs force financière (Résultat Net EF).

    100% dynamique : recalculé depuis cb_all_evolutions_summary (apparus CB, matching robuste)
    et resultat_net_series (EF). Aucune valeur en dur. Sert à repérer les banques qui
    innovent ET ont les moyens financiers de soutenir l'offensive (menace prioritaire SGCI).
    """
    evo = cb_all_evolutions_summary(segment)
    rn = resultat_net_series()
    out = []
    for b in BANKS:
        rn_yrs = rn.get(b, {})
        rn_last = rn_yrs[max(rn_yrs)] if rn_yrs else None
        out.append({
            "banque": b,
            "innovation": int(evo.get(b, {}).get("nApp", 0)),   # nouveaux services (CB)
            "retraits":   int(evo.get(b, {}).get("nDis", 0)),
            "resultat_net": round(float(rn_last)) if rn_last is not None else None,  # Mds/M FCFA (EF)
            "rn_annee": (max(rn_yrs) if rn_yrs else None),
        })
    return out


@lru_cache(maxsize=32)
def cb_analyse_q6_paired(annee=2026, semestre="S1", segment="Particuliers"):
    """Q6 : Comparaison prix SGCI vs chaque concurrent SUR SERVICES COMMUNS uniquement.

    On apparie les services par similarité sémantique entre SGCI et chaque concurrent,
    puis on compare les prix sur cet ensemble commun seulement. Évite le biais de mix-service
    (comparer la moyenne de catalogues de tailles et natures différentes n'a aucun sens).
    """
    rows = query(
        """
        WITH sgci_svcs AS (
            SELECT DISTINCT ON (LOWER(TRIM(libelle)))
                   libelle, montant, est_gratuit, type_valeur
            FROM cb_tarifs
            WHERE banque = 'SGCI'
              AND annee = %s AND semestre = %s
              AND LOWER(segment) = LOWER(%s)
              AND is_header = FALSE AND section IS NOT NULL
              AND LENGTH(TRIM(libelle)) BETWEEN 8 AND 110
              AND type_valeur IN ('MONTANT_FCFA','GRATUIT','TAUX_%%','SUR_DEMANDE','NUMERIQUE')
              AND libelle !~ '\\m[A-Za-z]\\M\\s+\\m[A-Za-z]\\M\\s+\\m[A-Za-z]\\M'
            ORDER BY LOWER(TRIM(libelle)), montant DESC NULLS LAST
        ),
        pairs AS (
            SELECT o.banque,
                   o.montant        AS mont_conc,
                   s.montant        AS mont_sgci,
                   o.est_gratuit    AS grat_conc,
                   s.est_gratuit    AS grat_sgci,
                   o.type_valeur    AS tv_conc,
                   s.type_valeur    AS tv_sgci,
                   o.libelle        AS lib_conc,
                   s.libelle        AS lib_sgci
            FROM cb_tarifs o
            JOIN sgci_svcs s ON (
                similarity(LOWER(TRIM(o.libelle)), LOWER(TRIM(s.libelle))) > 0.55
                OR word_similarity(LOWER(TRIM(s.libelle)), LOWER(TRIM(o.libelle))) > 0.65
                OR word_similarity(LOWER(TRIM(o.libelle)), LOWER(TRIM(s.libelle))) > 0.65
                OR (
                    LOWER(o.libelle) ~ 'virement.{0,30}(uemoa|sica|star|national|interne|agence|tiers)'
                    AND LOWER(s.libelle) ~ 'virement.{0,15}(fcfa|f cfa|franc)'
                )
                OR (
                    LOWER(o.libelle) ~ 'virement.{0,30}(euro|swift|hors|international|devis)'
                    AND LOWER(s.libelle) ~ 'virement.{0,10}euro'
                )
            )
            WHERE o.banque != 'SGCI'
              AND o.annee = %s AND o.semestre = %s
              AND LOWER(o.segment) = LOWER(%s)
              AND o.is_header = FALSE AND o.section IS NOT NULL
              AND LENGTH(TRIM(o.libelle)) BETWEEN 8 AND 110
              AND o.type_valeur IN ('MONTANT_FCFA','GRATUIT','TAUX_%%','SUR_DEMANDE','NUMERIQUE')
              AND o.libelle !~ '\\m[A-Za-z]\\M\\s+\\m[A-Za-z]\\M\\s+\\m[A-Za-z]\\M'
        )
        SELECT banque, lib_sgci, lib_conc, mont_conc, mont_sgci,
               grat_conc, grat_sgci, tv_conc, tv_sgci
        FROM pairs
        """,
        (annee, semestre, segment, annee, semestre, segment),
    )

    # ── FILTRE DE COMPARABILITÉ (ajouté le 2026-07-30) ───────────────────────────────────
    # L'agrégation était faite directement en SQL, donc SANS passer par _comparable() — alors
    # que cette fonction existait déjà et était appliquée par cb_prix_par_libelle(). Ce
    # comparatif reposait ainsi sur la seule similarité trigramme, aveugle au sens, et
    # produisait des paires fausses mesurées sur 2026 S1 Particuliers :
    #   « Première carte (frais de destruction) » 10 000  ⇔  « Frais de destruction de chéquier » 15 500
    #   « Levée d'opposition sur CARTE » 5 500            ⇔  « Levée d'opposition sur CHÈQUE » 15 000
    #   « CONFECTION de carte en urgence »                ⇔  « CONFISCATION de la carte » 25 000
    #   « Taxe de transfert » 0,6 %                       ⇔  « Transfert de carte à carte » 909 F
    # Chacune faussait la moyenne de prix du concurrent, donc le classement de compétitivité.
    # On récupère désormais les paires brutes et on filtre en Python, seul endroit où
    # _comparable() est accessible.
    from collections import defaultdict
    acc = defaultdict(lambda: {"libs": set(), "mc": [], "ms": [], "gc": 0, "gs": 0})
    n_rejets = 0
    for r in rows:
        if not _comparable(r["lib_sgci"], r["lib_conc"]):
            n_rejets += 1
            continue
        # Un TAUX ne se compare pas à un MONTANT : 0,6 % et 909 F ne sont pas commensurables.
        # GRATUIT reste comparable à MONTANT_FCFA (c'est un prix de zéro, pas une autre unité).
        _PRIX = {"MONTANT_FCFA", "GRATUIT"}
        tvc, tvs = (r["tv_conc"] or ""), (r["tv_sgci"] or "")
        if (tvc in _PRIX) != (tvs in _PRIX):
            n_rejets += 1
            continue
        a = acc[r["banque"]]
        a["libs"].add(r["lib_conc"])
        if tvc == "MONTANT_FCFA" and (r["mont_conc"] or 0) >= 100:
            a["mc"].append(float(r["mont_conc"]))
        if tvs == "MONTANT_FCFA" and (r["mont_sgci"] or 0) >= 100:
            a["ms"].append(float(r["mont_sgci"]))
        if r["grat_conc"]:
            a["gc"] += 1
        if r["grat_sgci"]:
            a["gs"] += 1

    if n_rejets:
        print(f"[db] q6_paired {annee} {semestre} {segment} : {n_rejets} paire(s) non comparable(s) écartée(s)")

    out = []
    for banque, a in acc.items():
        out.append({
            "banque":      banque,
            "n_communs":   len(a["libs"]),
            "moy_conc":    round(sum(a["mc"]) / len(a["mc"])) if a["mc"] else None,
            "moy_sgci":    round(sum(a["ms"]) / len(a["ms"])) if a["ms"] else None,
            "n_grat_conc": a["gc"],
            "n_grat_sgci": a["gs"],
        })
    # Même ordre qu'avant : moyenne concurrent croissante, valeurs absentes en fin de liste.
    out.sort(key=lambda d: (d["moy_conc"] is None, d["moy_conc"] or 0))
    return out


# Chaîne BRUTE : les contre-obliques ne doivent PAS être doublées ici, contrairement aux mêmes
# motifs écrits en clair dans les requêtes ci-dessus. \m et \M sont les bornes de mot du moteur
# d'expressions régulières de PostgreSQL, pas de Python.
_OCR_RE = r"\m[A-Za-z]\M\s+\m[A-Za-z]\M\s+\m[A-Za-z]\M"


_OV_STOP = {"de", "la", "le", "les", "des", "du", "un", "une", "et", "a", "à", "pour", "par", "sur",
            "en", "ou", "d", "l", "aux", "au", "avec", "sans", "non", "tout", "toute", "autres", "autre"}


def _sig_words(s):
    return set(w for w in re.findall(r"[a-zàâäéèêëîïôöùûüç]{3,}", (s or "").lower()) if w not in _OV_STOP)


def _word_overlap(a, b):
    """Chevauchement sémantique (Jaccard) entre deux libellés, avec appariement par PRÉFIXE (4 car.)
    pour tolérer le singulier/pluriel (comptes/compte, chèques/chèque). Sert à écarter les
    appariements de COÏNCIDENCE de sous-chaîne : « autorisation de change » vs « Pin change »,
    « certificat de titres » vs « certification de chèque », en-tête générique « Prélèvements » vs
    un frais précis. Retourne 1.0 si l'un des libellés n'a pas de mot significatif (on ne rejette pas)."""
    wa, wb = _sig_words(a), _sig_words(b)
    if not wa or not wb:
        return 1.0

    def _m(x, y):
        """Même mot, à la flexion près.

        BUG CORRIGÉ le 2026-07-30 : la règle était « mêmes 4 premiers caractères », ce qui
        confondait des mots de sens opposé partageant leur début — « CONFection de carte » et
        « CONFiscation de la carte » obtenaient un recouvrement de 1,00 et étaient donc jugés
        comparables. Idem « correction »/« confection ». L'intention initiale était de tolérer le
        singulier/pluriel (chèque/chèques, compte/comptes) : cela s'obtient en exigeant que le
        mot le plus court soit un PRÉFIXE de l'autre, et non un simple début commun.
        « chèque » ⊂ « chèques » reste vrai ; « confection » n'est pas un préfixe de
        « confiscation » — le faux appariement disparaît."""
        if x == y:
            return True
        court, long = (x, y) if len(x) <= len(y) else (y, x)
        return len(court) >= 4 and long.startswith(court)
    inter = sum(1 for x in wa if any(_m(x, y) for y in wb))
    union = len(wa) + len(wb) - inter
    return inter / union if union else 1.0


@lru_cache(maxsize=4096)
def _comparable(a, b):
    """Deux services sont-ils COMPARABLES (même périmètre) ? On REJETTE l'appariement si, dans une
    MÊME dimension discriminante (rail de virement, type de compte, réseau/gamme de carte, canal,
    devise, géographie), les deux libellés portent des valeurs DIFFÉRENTES → services hétérogènes.
    Ex. « Virement UEMOA (SICA) » vs « Virement UEMOA (STAR-UEMOA) » → rails différents → NON comparable.
    Conservateur : on ne rejette que sur conflit CLAIR (token présent des deux côtés mais différent)."""
    a, b = (a or "").lower(), (b or "").lower()
    # Garde-fou SÉMANTIQUE : trop peu de mots significatifs communs = appariement de coïncidence.
    if _word_overlap(a, b) < 0.34:
        return False
    _CATS = {
        # TYPE D'OPÉRATION — la dimension la plus discriminante : virement ≠ retrait ≠ consultation…
        # (corrige « Virement vers confrères » apparié à tort à « Retrait au GAB des confrères »).
        "operation": {"virement": r"virement|transfert",
                      "retrait":  r"retrait|cash\s*advance|\bgab\b|\bdab\b|distributeur|guichet\s+automatique",
                      "consult":  r"consultation|historique|mini.?relev|\bsolde\b",
                      "attestation": r"attestation|certificat",
                      "opposition": r"opposition|mainlev|lev[ée]e\s+d",
                      "prelevement": r"pr[ée]l[èe]vement",
                      "decouvert": r"d[ée]couvert|d[ée]passement|agios",
                      # CYCLE DE VIE D'UN MOYEN DE PAIEMENT (ajouté le 2026-07-30). Sur un même
                      # instrument et un même canal, l'ACTION reste discriminante : fabriquer une
                      # carte, la confisquer, la corriger ou la détruire sont quatre services
                      # distincts, facturés différemment. Faux appariements réellement produits :
                      # « CONFECTION de carte en urgence » ⇔ « CONFISCATION de la carte en
                      # urgence » (25 000 F) et ⇔ « CORRECTION de la carte en urgence ». Le reste
                      # du libellé étant identique, aucune autre dimension ne pouvait les séparer.
                      # « confection » couvre volontairement « re-confection » : refaire une carte
                      # reste le même service que la fabriquer, on ne rejette que sur conflit clair.
                      "confection":   r"confection",
                      "confiscation": r"confiscation|confisqu",
                      "correction":   r"correction|corrig",
                      "destruction":  r"destruction|d[ée]truit",
                      "renouvellement": r"renouvel",
                      "remplacement": r"remplac"},
        "rail":   {"sica": r"\bsica\b", "star": r"\bstar\b", "rtgs": r"\brtgs\b", "swift": r"\bswift\b"},
        "compte": {"cheque": r"compte\s+ch[èe]ques?\b", "epargne": r"[ée]pargne", "courant": r"courant",
                   "joint": r"\bjoint", "indivis": r"indivis", "terme": r"\bterme\b"},
        # INSTRUMENT — ajouté le 2026-07-30. Dimension aussi discriminante que le rail de virement,
        # et elle manquait : rien n'empêchait d'apparier des frais portant sur une CARTE à des frais
        # portant sur un CHÉQUIER. Faux appariements réellement produits par le comparatif des
        # services communs : « Première carte (frais de destruction) » ⇔ « Frais de destruction de
        # chéquier », « Levée d'opposition sur carte » ⇔ « Levée d'opposition sur chèque »,
        # « Confection de carte en urgence » ⇔ « Confection d'un code en urgence ». Le reste du
        # libellé étant identique, ni la similarité trigramme ni le recouvrement de mots ne
        # pouvaient les écarter — seul le nom de l'instrument les distingue.
        "instrument": {"carte": r"\bcartes?\b|\bcb\b",
                       "chequier": r"ch[ée]quiers?",
                       "cheque": r"\bch[èe]ques?\b",
                       "code": r"\bcodes?\b|\bpin\b",
                       "rib": r"\brib\b|relev[ée]\s+d.identit"},
        "reseau": {"visa": r"\bvisa\b", "mastercard": r"master\s?card", "gim": r"\bgim\b"},
        # GAMMES DE CARTE — enrichi le 2026-07-30 après lecture du comparatif réel.
        # « horizon » ajouté : c'est une gamme propre à SGCI (Première carte VISA HORIZON,
        # 15 000 F) qui n'était reconnue par aucun motif. Faute de gamme identifiée d'un côté,
        # aucun conflit n'était détecté et elle se retrouvait appariée à « Carte VISA GOLD »
        # de BACI (77 000 F) — deux gammes, deux positionnements, comparaison sans sens.
        # « premier » est en revanche rattaché à GOLD volontairement : sur ce marché les deux
        # désignent le même niveau de gamme, et BICICI l'écrit noir sur blanc dans son propre
        # libellé — « Carte Visa Premier OU Carte Visa Gold ». Les séparer aurait supprimé une
        # comparaison légitime (SGCI VISA PREMIER 70 000 ⇔ BACI VISA GOLD 77 000).
        "gamme":  {"classic": r"classi", "gold": r"\bgold\b|\bpremier\b", "infinite": r"infinite",
                   "platinum": r"platin", "horizon": r"horizon", "electron": r"electron",
                   "prepaid": r"pr[ée]pay", "business": r"business"},
        "canal":  {"agence": r"agence|guichet|caisse", "ligne": r"en ligne|internet|\bweb\b",
                   "mobile": r"\bmobile\b", "connect": r"connect"},
        "devise": {"fcfa": r"\bf\s?cfa\b|franc", "eur": r"\beuros?\b|\beur\b", "usd": r"\bdollars?\b|\busd\b"},
        "geo":    {"uemoa": r"\buemoa\b", "national": r"national",
                   "international": r"international|[ée]tranger|\bhors\b", "surplace": r"sur\s+place"},
    }
    for toks in _CATS.values():
        va = next((k for k, p in toks.items() if re.search(p, a)), None)
        vb = next((k for k, p in toks.items() if re.search(p, b)), None)
        if va and vb and va != vb:
            return False
    # Opérations TRÈS spécifiques : si l'une est présente d'un SEUL côté → services différents
    # (corrige « Vers confrères » [virement] apparié à « Retrait au GAB des confrères » ;
    #  « Attestation de virement » apparié à « Virement » ; variante urgente/RTGS vs standard).
    for _pat in (r"retrait|cash\s*advance|\bgab\b|\bdab\b|distributeur|guichet\s+automatique",  # retrait au DAB
                 r"attestation|certificat",                                                      # attestation/certificat
                 r"urgent|\brtgs\b|imm[ée]diat|instantan"):                                       # virement urgent/RTGS
        if bool(re.search(_pat, a)) != bool(re.search(_pat, b)):
            return False
    return True


def _flag_outliers(out, factor=10):
    """Marque suspect=True toute valeur ABERRANTE (> factor× ou < 1/factor de la médiane du MÊME
    service, même type de valeur) → erreur d'extraction probable (ex. commission « 5% » au lieu de
    « 0,05% », frais « 1 000 000 F » au lieu de « 33 000 »). Affichée « réf. CB » côté front et
    EXCLUE des comparaisons (win-rate, coûts de changement…). NE MODIFIE PAS la base — flag en mémoire."""
    import statistics as _st
    for sec in out:
        for ss in sec.get("sous_sections", []):
            for svc in ss.get("services", []):
                for tv in ("MONTANT_FCFA", "TAUX_%", "TAUX_%%"):
                    cells = []
                    sg = svc.get("sgci") or {}
                    if sg.get("tv") == tv and sg.get("montant") and float(sg["montant"]) > 0:
                        cells.append(sg)
                    for c in (svc.get("concurrents") or {}).values():
                        if c and c.get("tv") == tv and c.get("montant") and float(c["montant"]) > 0:
                            cells.append(c)
                    if len(cells) < 3:
                        continue
                    vals = [float(c["montant"]) for c in cells]
                    med = _st.median(vals)
                    if med <= 0:
                        continue
                    for c in cells:
                        v = float(c["montant"])
                        if v > med * factor or v < med / factor:
                            c["suspect"] = True
                            c["suspect_med"] = round(med, 4)
    return out


def cb_prix_par_libelle(annee=2026, semestre="S1", segment="Particuliers"):
    """Comparaison service par service : pour chaque libellé SGCI, trouve le meilleur
    correspondant chez chaque concurrent et retourne les prix côte à côte.

    Structuré section canonique I-IX → sous-section → libellé SGCI → prix par banque.
    C'est la seule manière rigoureuse de comparer "Frais de tenue de compte — compte
    courant" chez SGCI à "Frais de tenue de compte — compte courant ordinaire" chez BACI
    sans confondre des services hétérogènes dans une même moyenne.
    """
    # ── 1. Services SGCI (point de référence) ───────────────────────────────
    sgci_rows = query(
        """
        SELECT DISTINCT libelle, section, COALESCE(contexte,'') AS contexte,
               montant, est_gratuit, type_valeur, COALESCE(unite,'') AS unite
        FROM cb_tarifs
        WHERE banque = 'SGCI'
          AND annee = %s AND semestre = %s
          AND LOWER(segment) = LOWER(%s)
          AND is_header = FALSE
          -- ANCRAGE STRUCTUREL (2026-07-30) : « section IS NOT NULL » servait de filtre anti-OCR,
          -- mais il écartait aussi des lignes parfaitement valides dont le numéro de section n'a
          -- pas été capturé à l'extraction. Conséquence mesurée sur 2026 S1 Particuliers : les DIX
          -- produits carte de SGCI (Première/Seconde carte VISA CLASSIC, HORIZON, PREMIER,
          -- PLATINUM, INFINITE) ont section = NULL et disparaissaient donc du comparatif — la
          -- gamme carte, l'un des postes les plus comparables du marché, était structurellement
          -- absente. 86 lignes SGCI sur 334, soit un quart du catalogue, etaient ainsi perdues.
          -- On accepte désormais une ligne dès qu'elle possède UN ancrage : section OU contexte
          -- (94 lignes sur 100 sans section ont un contexte). L'effet anti-bruit est conserve --
          -- une ligne sans aucun des deux reste écartée — et canonical_section() sait déjà
          -- classer par contenu quand la section manque (cf. sa docstring).
          AND (section IS NOT NULL OR NULLIF(TRIM(COALESCE(contexte,'')),'') IS NOT NULL)
          AND type_valeur IN ('MONTANT_FCFA','GRATUIT','TAUX_%%','SUR_DEMANDE','NUMERIQUE')
          AND libelle !~ %s
          AND LENGTH(TRIM(libelle)) BETWEEN 6 AND 110
          AND """ + _not_segment_sql("libelle") + """
        -- TRI COMPLET, PAS SEULEMENT (section, libelle) — 2026-08-09. Le DISTINCT porte sur
        -- SEPT colonnes : un même service peut donc survivre plusieurs fois, à des montants
        -- différents (« Frais de dossier » en est le cas type). Trier sur deux colonnes
        -- seulement laissait l'ordre de ces jumeaux à la discrétion de PostgreSQL, et le
        -- premier arrivé l'emportait plus loin dans la chaîne. Résultat mesuré en migrant vers
        -- l'hébergeur : 116 services comparables ici, 117 sur une copie au contenu identique.
        -- On trie donc sur tout ce qui distingue les lignes, NULLS FIRST explicite pour que
        -- les montants absents se rangent toujours du même côté.
        ORDER BY section, libelle, contexte, montant NULLS FIRST, est_gratuit, unite
        """,
        (annee, semestre, segment, _OCR_RE),
    )

    # ── 2. Meilleur match par (libelle_sgci, banque_concurrente) ────────────
    match_rows = query(
        """
        SELECT DISTINCT ON (s.libelle, o.banque)
               s.libelle       AS lib_sgci,
               o.banque        AS banque,
               o.libelle       AS lib_conc,
               o.montant       AS prix_conc,
               o.est_gratuit   AS grat_conc,
               o.type_valeur   AS tv_conc,
               s.type_valeur   AS tv_sgci,
               COALESCE(o.unite,'') AS unite_conc
        FROM cb_tarifs s
        JOIN cb_tarifs o ON (
            o.banque != 'SGCI'
            AND o.annee  = s.annee  AND o.semestre = s.semestre
            AND LOWER(o.segment) = LOWER(s.segment)
            AND o.is_header = FALSE   -- cf. note ANCRAGE STRUCTUREL ci-dessus
            AND (o.section IS NOT NULL OR NULLIF(TRIM(COALESCE(o.contexte,'')),'') IS NOT NULL)
            AND o.type_valeur IN ('MONTANT_FCFA','GRATUIT','TAUX_%%','SUR_DEMANDE','NUMERIQUE')
            AND o.libelle !~ %s
            AND LENGTH(TRIM(o.libelle)) BETWEEN 6 AND 110
            AND """ + _not_segment_sql("o.libelle") + """
            AND (
                similarity(LOWER(TRIM(o.libelle)), LOWER(TRIM(s.libelle))) > 0.52
                OR word_similarity(LOWER(TRIM(s.libelle)), LOWER(TRIM(o.libelle))) > 0.62
                OR word_similarity(LOWER(TRIM(o.libelle)), LOWER(TRIM(s.libelle))) > 0.62
                OR (LOWER(o.libelle) ~ 'virement.{0,30}(uemoa|sica|star|national|interne|agence|tiers)'
                    AND LOWER(s.libelle) ~ 'virement.{0,15}(fcfa|f cfa|franc)')
                OR (LOWER(o.libelle) ~ 'virement.{0,30}(euro|swift|hors|international|devis)'
                    AND LOWER(s.libelle) ~ 'virement.{0,10}euro')
            )
        )
        WHERE s.banque = 'SGCI'
          AND s.annee = %s AND s.semestre = %s
          AND LOWER(s.segment) = LOWER(%s)
          AND s.is_header = FALSE   -- cf. note ANCRAGE STRUCTUREL ci-dessus
          AND (s.section IS NOT NULL OR NULLIF(TRIM(COALESCE(s.contexte,'')),'') IS NOT NULL)
          AND s.type_valeur IN ('MONTANT_FCFA','GRATUIT','TAUX_%%','SUR_DEMANDE','NUMERIQUE')
          AND s.libelle !~ %s
          AND LENGTH(TRIM(s.libelle)) BETWEEN 6 AND 110
          AND """ + _not_segment_sql("s.libelle") + """
        -- DÉPARTAGE DÉTERMINISTE (2026-08-09). Le tri s'arrêtait au score de similarité : quand
        -- deux lignes concurrentes obtenaient EXACTEMENT le même score — ce qui arrive dès que
        -- deux libellés se ressemblent autant — laquelle survivait au DISTINCT ON dépendait de
        -- l'ordre PHYSIQUE des lignes dans la table, que PostgreSQL ne garantit pas.
        --
        -- Trouvé en migrant vers l'hébergeur : sur une copie au contenu rigoureusement
        -- identique, le panier comparable rendait 117 services au lieu de 118, et trois
        -- services changeaient. Rien n'était « cassé » — les deux résultats étaient également
        -- défendables — mais des chiffres qui bougent sans que la donnée bouge ne sont pas
        -- des chiffres qu'on présente à un comité. Un VACUUM aurait suffi à les déplacer.
        --
        -- On ajoute donc des critères stables : le libellé du concurrent, son identifiant,
        -- PUIS L'IDENTIFIANT DE LA LIGNE SGCI. Ce dernier est le moins évident et c'est le
        -- seul qui refermait vraiment le problème : le DISTINCT ON groupe par LIBELLÉ SGCI,
        -- or un même libellé existe en plusieurs exemplaires — « Frais de dossier » compte
        -- trois lignes SGCI, à des sections et des types de valeur différents. Une même ligne
        -- concurrente s'apparie donc à plusieurs d'entre elles avec le MÊME score, et rien ne
        -- disait laquelle fournissait le `tv_sgci` retenu. Le résultat changeait alors d'une
        -- base à l'autre sans qu'aucune donnée ne change.
        -- À score égal, c'est désormais toujours la même ligne qui gagne, sur n'importe quelle
        -- base et après n'importe quelle réorganisation.
        ORDER BY s.libelle, o.banque,
                 GREATEST(
                     similarity(LOWER(TRIM(o.libelle)), LOWER(TRIM(s.libelle))),
                     word_similarity(LOWER(TRIM(s.libelle)), LOWER(TRIM(o.libelle))),
                     word_similarity(LOWER(TRIM(o.libelle)), LOWER(TRIM(s.libelle)))
                 ) DESC,
                 o.libelle, o.id, s.id
        """,
        (_OCR_RE, annee, semestre, segment, _OCR_RE),
    )

    # ── 3. Index des matches par libelle_sgci ───────────────────────────────
    #    + FILTRE « périmètre comparable » : on écarte les appariements hétérogènes
    #    (rail/type de compte/carte/canal/devise/géo différents) → fiabilise TOUTES
    #    les comparaisons croisées (repricing, win-rate, exclusivités, coûts de changement).
    matches = {}  # lib_sgci → {banque: {libelle, prix, grat, tv}}
    _rejets = 0
    # Un TAUX ne se compare pas à un MONTANT (2026-07-30). Constaté dans le comparatif réel :
    # « Distributeurs Automatiques (DAB) par cartes étrangères » SGCI 3 500 F apparié à la ligne
    # BICICI valant 4,5 — qui est un POURCENTAGE de retrait, pas un tarif fixe. Le tableau
    # affichait donc « 3 500 » face à « 4,5 » comme si SGCI était 778 fois plus chère.
    # GRATUIT reste comparable à MONTANT_FCFA : c'est un prix de zéro, pas une autre unité.
    _UNITE_PRIX = {"MONTANT_FCFA", "GRATUIT"}
    for r in match_rows:
        if not _comparable(r["lib_sgci"], r["lib_conc"]):
            _rejets += 1
            continue
        if ((r["tv_conc"] or "") in _UNITE_PRIX) != ((r["tv_sgci"] or "") in _UNITE_PRIX):
            _rejets += 1
            continue
        matches.setdefault(r["lib_sgci"], {})[r["banque"]] = {
            "libelle": r["lib_conc"],
            "montant": r["prix_conc"],
            "grat":    r["grat_conc"],
            "tv":      r["tv_conc"],
            "unite":   r.get("unite_conc", ""),
        }
    if _rejets:
        print(f"[cb_prix] {_rejets} appariements écartés (périmètre non comparable)")

    # ── 4. Classement section → sous-section → services ─────────────────────
    CONC_BANKS = [b for b in BANKS if b != "SGCI"]  # ordre alpha
    sections_map = {}   # section_id → {roman, titre, ss_map}
    # Dédoublonnage : même libellé peut apparaître plusieurs fois dans cb_tarifs
    # avec des section/contexte différents mais mappés à la même sous-section canonique.
    # On garde la première occurrence (ORDER BY section, libelle dans la requête SQL).
    seen_svc_keys: set = set()

    # Nettoyage OCR : préfixes non-alphanumériques (• ¤ etc.) + suffixes T1/T2/T3
    _pfx_re  = re.compile(r'^\W+', re.UNICODE)
    _sfx_re  = re.compile(r'\s*[T]\d+\s*$', re.UNICODE)

    for r in sgci_rows:
        lib_raw = r["libelle"]                                              # brut, pour lookup matches
        lib     = _sfx_re.sub('', _pfx_re.sub('', lib_raw)).strip()       # nettoyé, pour affichage
        if not lib:
            continue
        if _is_fragment_lib(lib):   # palier/sous-ligne (ex. « Montant compris entre… ») → pas un service
            continue
        sid, roman, titre = cb_sections.canonical_section(
            "SGCI", r["section"], lib, r["contexte"]
        )
        sub_id, sub_lbl = cb_subsections.classify_subsection(sid, lib, r["contexte"])

        # Ignorer les doublons : clé CANONIQUE (synonymes/pluriels unifiés) dans la
        # même sous-section → « compte chèque » = « compte chèques » = 1 seule ligne.
        dedup_key = (sid, sub_id, cb_axes.canon_key(lib) or lib.lower().strip())
        if dedup_key in seen_svc_keys:
            continue
        seen_svc_keys.add(dedup_key)

        if sid not in sections_map:
            sections_map[sid] = {"roman": roman, "titre": titre, "ss": {}}
        ss_map = sections_map[sid]["ss"]
        if sub_id not in ss_map:
            ss_map[sub_id] = {"libelle": sub_lbl, "services": []}

        svc_matches = matches.get(lib_raw, {})   # lookup sur libellé brut = clé SQL
        # Médiane marché : montants FCFA fixes PLAUSIBLES uniquement.
        # PLANCHER 100 F : un vrai frais bancaire ≥ ~100 F. Les valeurs < 100 (ex.
        # « 0,003 F », « 3 F », « 2,4 F ») sont des artefacts d'extraction (un % ou un
        # OCR pris pour un montant) — les inclure fausse la médiane ET l'analyse LLM.
        conc_montants = [
            float(v["montant"]) for v in svc_matches.values()
            if v.get("tv") == "MONTANT_FCFA" and v.get("montant") is not None
               and float(v["montant"]) >= 100
        ]
        # Médiane ROBUSTE : écarte les valeurs > 12× la médiane (appariement hétérogène,
        # ex. « Frais de dossier 6 000 … 220 000 F » = services différents regroupés).
        mkt_median = _median_robuste(conc_montants)
        # Valeur SGCI douteuse (FCFA mais < 100 F) → signalée pour affichage « réf. CB »
        _sg_m = r["montant"]
        _sg_suspect = (r["type_valeur"] == "MONTANT_FCFA" and _sg_m is not None
                       and 0 < float(_sg_m) < 100)

        ss_map[sub_id]["services"].append({
            "libelle": lib,
            "sgci": {
                "montant": r["montant"],
                "grat":    r["est_gratuit"],
                "tv":      r["type_valeur"],
                "unite":   r.get("unite", ""),
                "suspect": _sg_suspect,
            },
            "concurrents": {b: svc_matches.get(b) for b in CONC_BANKS},
            "mkt_median":  mkt_median,
            "n_conc_presents": len(svc_matches),
        })

    # ── 5. Sérialisation ordonnée I → IX ────────────────────────────────────
    out = []
    for sid in sorted(sections_map):
        s = sections_map[sid]
        ss_list = []
        for sub_id in sorted(s["ss"]):
            ss = s["ss"][sub_id]
            # Trier services : d'abord ceux présents chez ≥1 concurrent, puis SGCI only
            svcs = sorted(
                ss["services"],
                key=lambda x: (-x["n_conc_presents"], x["libelle"]),
            )
            ss_list.append({"libelle": ss["libelle"], "services": svcs})
        out.append({
            "roman":        s["roman"],
            "titre":        s["titre"],
            "sous_sections": ss_list,
        })
    return _flag_outliers(out)


@lru_cache(maxsize=32)
def cb_prix_competitivite(annee=2026, semestre="S1", segment="Particuliers"):
    """Indice de compétitivité tarifaire (win-rate) — ADDITIF, déterministe.

    Répond à « qui est le plus souvent le moins cher ? » (complément du rang catalogue
    qui, lui, ne mesure que la LARGEUR de l'offre).

    Méthode (rigoureuse, à la BCEAO) :
      • Panier = services SGCI ayant un comparatif marché valide (≥ 2 prix concurrents
        FCFA) — c.-à-d. des services réellement comparables d'une banque à l'autre.
      • Pour chaque service du panier on relève le prix de chaque banque présente
        (montant FCFA > 0, ou gratuit = 0). On calcule la médiane de référence sur
        TOUTES les banques présentes pour ce service.
      • Une banque « gagne » le service si son prix ≤ médiane (gratuit gagne toujours).
      • Win-rate banque = victoires / nb de services comparables où elle est présente.
      • Classement par win-rate décroissant → #1 = la plus souvent la moins chère.

    Garde-fous : jamais de mélange %/FCFA (TAUX_% et SUR_DEMANDE exclus), médiane
    (robuste), min. 3 banques présentes par service, min. 8 services pour être classé.
    Réutilise l'appariement déjà éprouvé de cb_prix_par_libelle.
    """
    data = cb_prix_par_libelle(annee, semestre, segment)
    stat = {b: {"wins": 0, "n": 0} for b in BANKS}
    n_panier = 0

    def _prix_banque(cell):
        """Retourne le prix comparable d'une cellule (0 si gratuit, FCFA si fixe), sinon None."""
        if not cell or cell.get("suspect"):     # valeur aberrante (réf. CB) → hors comparaison
            return None
        if cell.get("grat"):
            return 0.0
        if cell.get("tv") == "MONTANT_FCFA" and cell.get("montant") and float(cell["montant"]) > 0:
            return float(cell["montant"])
        return None

    for sec in data:
        for ss in sec["sous_sections"]:
            for svc in ss["services"]:
                if svc.get("mkt_median") is None:
                    continue  # pas ≥2 concurrents FCFA → hors panier comparable
                prix = {}
                p_sgci = _prix_banque(svc.get("sgci"))
                if p_sgci is not None:
                    prix["SGCI"] = p_sgci
                for b, cell in (svc.get("concurrents") or {}).items():
                    p = _prix_banque(cell)
                    if p is not None:
                        prix[b] = p
                if len(prix) < 3:
                    continue  # trop peu de banques pour un classement sensé
                ref = statistics.median(prix.values())
                n_panier += 1
                for b, p in prix.items():
                    stat[b]["n"] += 1
                    if p <= ref:
                        stat[b]["wins"] += 1

    classement = []
    for b in BANKS:
        n = stat[b]["n"]
        if n == 0:
            continue
        classement.append({
            "banque":  b,
            "winrate": round(100 * stat[b]["wins"] / n, 1),
            "wins":    stat[b]["wins"],
            "n":       n,
        })
    classes = sorted([c for c in classement if c["n"] >= 8],
                     key=lambda c: (-c["winrate"], -c["n"]))
    rang_sgci = next((i + 1 for i, c in enumerate(classes) if c["banque"] == "SGCI"), None)
    sgci = next((c for c in classement if c["banque"] == "SGCI"), None)
    return {
        "annee": annee, "semestre": semestre, "segment": segment,
        "n_services_panier": n_panier,
        "classement": classes,
        "n_classees": len(classes),
        "sgci": sgci,
        "rang_sgci": rang_sgci,
    }


@lru_cache(maxsize=8)
def cb_prix_competitivite_tous_segments(annee=2026, semestre="S1"):
    """Variante de cb_prix_competitivite COMBINANT Particuliers + Entreprises dans le MÊME panier
    (2026-07-22, demande explicite du directeur : « tous les onglets doivent tenir compte de TOUTES
    les données »). Réutilise EXACTEMENT la même logique de duel de prix (médiane par service,
    victoire si prix ≤ médiane) — seule différence : le panier est l'union des services comparables
    des deux segments, pas d'un seul. Mêmes garde-fous (≥3 banques présentes, ≥8 services classés)."""
    stat = {b: {"wins": 0, "n": 0} for b in BANKS}
    n_panier = 0

    def _prix_banque(cell):
        if not cell or cell.get("suspect"):
            return None
        if cell.get("grat"):
            return 0.0
        if cell.get("tv") == "MONTANT_FCFA" and cell.get("montant") and float(cell["montant"]) > 0:
            return float(cell["montant"])
        return None

    for seg in ("Particuliers", "Entreprises"):
        data = cb_prix_par_libelle(annee, semestre, seg)
        for sec in data:
            for ss in sec["sous_sections"]:
                for svc in ss["services"]:
                    if svc.get("mkt_median") is None:
                        continue
                    prix = {}
                    p_sgci = _prix_banque(svc.get("sgci"))
                    if p_sgci is not None:
                        prix["SGCI"] = p_sgci
                    for b, cell in (svc.get("concurrents") or {}).items():
                        p = _prix_banque(cell)
                        if p is not None:
                            prix[b] = p
                    if len(prix) < 3:
                        continue
                    ref = statistics.median(prix.values())
                    n_panier += 1
                    for b, p in prix.items():
                        stat[b]["n"] += 1
                        if p <= ref:
                            stat[b]["wins"] += 1

    classement = []
    for b in BANKS:
        n = stat[b]["n"]
        if n == 0:
            continue
        classement.append({
            "banque":  b,
            "winrate": round(100 * stat[b]["wins"] / n, 1),
            "wins":    stat[b]["wins"],
            "n":       n,
        })
    classes = sorted([c for c in classement if c["n"] >= 8],
                     key=lambda c: (-c["winrate"], -c["n"]))
    rang_sgci = next((i + 1 for i, c in enumerate(classes) if c["banque"] == "SGCI"), None)
    sgci = next((c for c in classement if c["banque"] == "SGCI"), None)
    return {
        "annee": annee, "semestre": semestre, "segment": "Tous",
        "n_services_panier": n_panier,
        "classement": classes,
        "n_classees": len(classes),
        "sgci": sgci,
        "rang_sgci": rang_sgci,
    }


# ════════════════════════════════════════════════════════════════════════════
#  AGENT RÉGL — récupération SÉMANTIQUE réelle sur regl_documents (pgvector)
# ════════════════════════════════════════════════════════════════════════════
_REGL_MODEL = None

# ── NETTOYAGE DES MARQUEURS D'EXTRACTION (2026-07-30) ────────────────────────────────────
# Les chunks de regl_documents portent les marqueurs techniques du pipeline d'extraction —
# « [PAGE 4] » et « [METRICS chars=2803 density=5.5929 ocr_pct=0.0 tables=NON ocr_conf=N/A] » —
# insérés au fil du texte à chaque changement de page. 85 chunks sur 88 en contiennent.
# Ils étaient servis tels quels : au dashboard (endpoint /api/regl) comme au RAG du chat, qui
# les recevait donc dans le contexte réglementaire transmis au LLM. Nettoyage à la LECTURE
# seulement — la base n'est pas modifiée, l'information de page reste disponible si un jour on
# veut l'exploiter comme métadonnée plutôt que comme texte.
_RE_MARQUEURS_EXTRACTION = re.compile(r"\[(?:PAGE\s+\d+|METRICS[^\]]{0,200})\]\s*")


def nettoyer_texte_regl(t):
    """Retire les marqueurs [PAGE n] / [METRICS ...] d'un contenu réglementaire."""
    if not t:
        return t
    return _RE_MARQUEURS_EXTRACTION.sub(" ", t).strip()


def _regl_embed(text):
    """Encode une requête en vecteur 768d (modèle multilingue, chargé une fois)."""
    global _REGL_MODEL
    if _REGL_MODEL is None:
        from sentence_transformers import SentenceTransformer
        _REGL_MODEL = SentenceTransformer("sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
    v = _REGL_MODEL.encode([text], normalize_embeddings=True)[0]
    return "[" + ",".join(f"{x:.8f}" for x in v) + "]"


@lru_cache(maxsize=64)
def regl_semantic(q, k=3):
    """Recherche SÉMANTIQUE (cosine pgvector) sur les textes réglementaires.
    Retourne [{fichier, contenu, score}]. Vrai RAG sémantique sur regl_documents."""
    try:
        vec = _regl_embed(q)
        rows = query(
            """SELECT fichier, contenu, 1 - (embedding <=> %s::vector) AS score
               FROM regl_documents
               WHERE embedding IS NOT NULL
               ORDER BY embedding <=> %s::vector
               LIMIT %s""",
            (vec, vec, k))
        out = [{"fichier": r["fichier"], "contenu": nettoyer_texte_regl(r["contenu"])[:320],
                "score": round(float(r["score"]), 3)} for r in rows if r.get("contenu")]
        if out:
            return out
    except Exception as e:
        print(f"[regl] sémantique indisponible ({e}) → repli mots-clés")
    return regl_keyword(q, k)


@lru_cache(maxsize=64)
def regl_keyword(q, k=3):
    """Repli : recherche plein-texte (ILIKE) sur regl_documents — toujours disponible."""
    terms = [t for t in re.findall(r"[a-zàâçéèêëîïôùûü]{4,}", (q or "").lower())][:4]
    if not terms:
        return []
    conds = " OR ".join(["LOWER(contenu) LIKE %s"] * len(terms))
    params = [f"%{t}%" for t in terms] + [k]
    rows = query(
        f"""SELECT fichier, contenu FROM regl_documents
            WHERE {conds} ORDER BY chunk_index LIMIT %s""", params)
    return [{"fichier": r["fichier"], "contenu": nettoyer_texte_regl(r["contenu"])[:320], "score": None}
            for r in rows if r.get("contenu")]
