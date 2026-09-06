"""
agent_tools.py — Outils LangChain pour l'agent de secours du chat (2026-07-25)
==============================================================================
Contexte : l'audit du chat a identifié que le routage repose sur 4 détecteurs
regex/mots-clés séparés (_detect_comparatif, _detect_factuel_ef_unique,
_detect_comparaison_ef_banques, _detect_comparaison_cb_service dans chain.py),
patchés au cas par cas à chaque nouveau bug trouvé en testant. Réécrire ce
routage entier en agent LangChain aurait été risqué (code déjà très éprouvé) —
au lieu de ça, cet agent sert de FILET DE SECOURS : il n'intervient QUE quand
TOUS les détecteurs existants ET la détection de domaine par mots-clés ont
échoué (question qui aurait sinon été rejetée "hors périmètre"). Il ne peut
donc JAMAIS dégrader un cas qui fonctionnait déjà — il ne fait que rattraper
des cas auparavant 100% perdus.

Chaque outil est un wrapper FIN autour de structured_tools.py (même source SQL
déterministe que le reste de l'app) — l'agent ne fait QUE choisir quel outil
appeler et avec quels paramètres ; il n'invente jamais de chiffre lui-même.
"""
import os
import sys
import importlib
from typing import Optional, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
structured_tools = importlib.import_module("structured_tools")

from langchain_core.tools import tool

# BUG TROUVÉ EN TESTANT (2026-07-25) : `banques: list = None` génère un schéma JSON qui exige
# un tableau, incompatible avec la valeur `null` que le modèle envoie pour "pas de filtre" —
# Groq rejetait l'appel en 400 ("expected array, but got null"). `Optional[List[str]] = None`
# génère un schéma qui accepte explicitement null.


@tool
def comparer_indicateur_financier(indicateur: str, mode: str = "AN3", banques: Optional[List[str]] = None) -> str:
    """Compare un indicateur des états financiers (PNB, résultat net, capitaux propres,
    total bilan, coût du risque, charges générales) entre les banques ivoiriennes.
    indicateur : nom de l'indicateur en français (ex. "PNB", "résultat net", "total bilan").
    mode : "AN3" (année la plus récente, défaut) ou "AN1" (année la plus ancienne des 3 dernières).
    banques : liste de codes banque à comparer (ex. ["SGCI", "BICICI"]) ou None pour les 7 banques.
    Utilise CET outil pour toute question de classement/comparaison sur un indicateur financier."""
    d = structured_tools.comparer_ef(indicateur, mode, banques)
    txt, gagnant = structured_tools.format_comparaison(d, "millions FCFA", "max")
    return f"{txt}\n\n(Valeur la plus élevée : {gagnant})" if gagnant else txt


@tool
def valeur_indicateur_banque(banque: str, indicateur: str, annee: Optional[int] = None) -> str:
    """Donne la valeur d'UN indicateur financier pour UNE SEULE banque, à une année précise.
    banque : code banque (SGCI, BICICI, BNI, ECOBANK, NSIA, SIB, BACI).
    indicateur : nom de l'indicateur en français (ex. "PNB", "résultat net", "ROE").
    annee : année précise demandée, ou None pour la plus récente disponible.
    Utilise CET outil pour une question factuelle simple sur UNE banque et UN indicateur."""
    if (indicateur or "").strip().lower() in ("roe", "rentabilité", "rentabilite", "return on equity"):
        d = structured_tools.comparer_roe("AN3" if not annee else "AN1")
        info = d.get(banque)
        return f"ROE de {banque} : {info['valeur']} % ({info['annee']})" if info else "Donnée non trouvée."
    if "coefficient" in (indicateur or "").lower():
        d = structured_tools.comparer_coefficient_exploitation("AN3" if not annee else "AN1")
        info = d.get(banque)
        return f"Coefficient d'exploitation de {banque} : {info['valeur']} % ({info['annee']})" if info else "Donnée non trouvée."
    info = structured_tools.valeur_ef(banque, indicateur, annee)
    if not info:
        return "Donnée non trouvée dans la base pour cette banque/cet indicateur/cette année."
    if info.get("ambigu"):
        # « if not info » ne suffit pas : {"valeur": None, "ambigu": True} est un dict NON
        # VIDE — aurait plante sur {info['valeur']:,.0f} (None) plus bas.
        vals = ', '.join(f"{v:,.0f}".replace(',', ' ') for v in info["valeurs_conflictuelles"])
        return (f"Donnée ambiguë en base pour {indicateur} de {banque} en {info['annee']} "
                f"({vals} — valeurs contradictoires, aucune fiable sans vérification).")
    return f"{indicateur} de {banque} en {info['annee']} : {info['valeur']:,.0f} millions FCFA".replace(",", " ")


@tool
def comparer_rentabilite(critere: str, mode: str = "AN3", banques: Optional[List[str]] = None) -> str:
    """Compare le ROE (rentabilité des fonds propres) ou le coefficient d'exploitation
    (efficience opérationnelle) entre les banques ivoiriennes.
    critere : "roe" ou "coefficient d'exploitation".
    mode : "AN3" (récent, défaut) ou "AN1" (ancien).
    banques : liste de codes banque ou None pour les 7.
    Pour le coefficient d'exploitation, PLUS BAS = meilleur (plus efficient)."""
    if "coefficient" in (critere or "").lower():
        d = structured_tools.comparer_coefficient_exploitation(mode, banques)
        txt, gagnant = structured_tools.format_comparaison(d, "%", "min")
        return f"{txt}\n\n(Coefficient le plus bas = le plus efficient : {gagnant})"
    d = structured_tools.comparer_roe(mode, banques)
    txt, gagnant = structured_tools.format_comparaison(d, "%", "max")
    return f"{txt}\n\n(ROE le plus élevé : {gagnant})"


@tool
def comparer_tarif_bancaire(service: str, annee: int, semestre: str, segment: str = "Particuliers") -> str:
    """Compare le tarif d'UN service bancaire précis (ex. "tenue de compte", "virement",
    "carte", "retrait") entre les 7 banques ivoiriennes, à une période donnée.
    service : nom du service en français.
    annee : année (2024, 2025 ou 2026).
    semestre : "S1" ou "S2".
    segment : "Particuliers" (défaut) ou "Entreprises".
    Utilise CET outil pour une comparaison de tarif sur un service précis et une période précise."""
    d = structured_tools.comparer_cb(service, annee, semestre, segment)
    txt, gagnant = structured_tools.format_comparaison(d, "FCFA", "min")
    return f"{txt}\n\n(Le moins cher : {gagnant})" if gagnant else txt


ALL_TOOLS = [
    comparer_indicateur_financier,
    valeur_indicateur_banque,
    comparer_rentabilite,
    comparer_tarif_bancaire,
]
