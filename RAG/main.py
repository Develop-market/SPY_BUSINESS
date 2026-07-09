"""
main.py — Interface conversationnelle RAG SpyBusiness
======================================================
Lancement : python RAG/main.py

Commandes spéciales :
  /reset   — Effacer la mémoire conversationnelle
  /quit    — Quitter
  /aide    — Afficher l'aide
"""

import sys
import os
import warnings

# Nettoyer les warnings non pertinents
warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chain as c
import config


AIDE = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SPYBUSINESS — INTELLIGENCE BANCAIRE IVOIRIENNE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Banques : BACI · BICICI · BNI · ECOBANK · NSIA · SGCI · SIB
Période : 2024 · 2025 · 2026
Données : Conditions tarifaires · États financiers · Réglementation

Exemples de questions :
  → Quels sont les frais de tenue de compte SGCI en 2024 S1 ?
  → Comparer les frais de virement entre toutes les banques en 2025
  → Quel est le résultat net de ECOBANK en 2024 ?
  → Quelle banque est la plus avantageuse pour une PME ?
  → Quelles lois encadrent les frais bancaires en Côte d'Ivoire ?

Commandes :
  /reset   — Effacer la mémoire conversationnelle
  /aide    — Afficher ce message
  /quit    — Quitter

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


def main():
    print()
    print("=" * 55)
    print("  SPYBUSINESS — Intelligence Bancaire Ivoirienne")
    print(f"  LLM : {config.GROQ_MODEL if config.LLM_PROVIDER == 'groq' else config.GEMINI_MODEL}")
    print(f"  Base : PostgreSQL intelligence_bancaire")
    print("=" * 55)

    # Initialisation
    try:
        chain = c.init_chain()
    except Exception as e:
        print(f"\n[ERREUR INIT] {e}")
        print("Vérifiez votre .env (GROQ_API_KEY, DB_PASSWORD)")
        sys.exit(1)

    print(AIDE)
    print("Posez votre question (ou /aide) :\n")

    while True:
        try:
            question = input("Vous > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nAu revoir.")
            break

        if not question:
            continue

        # Commandes spéciales
        if question.lower() in ("/quit", "/exit", "quit", "exit"):
            print("Au revoir.")
            break

        if question.lower() in ("/reset", "reset"):
            chain["memory"].clear()
            print("Mémoire effacée.\n")
            continue

        if question.lower() in ("/aide", "/help", "aide"):
            print(AIDE)
            continue

        # Question normale
        print()
        try:
            reponse = c.ask(chain, question)
            print(f"\nSpyBusiness > {reponse}\n")
        except Exception as e:
            print(f"\n[ERREUR] {e}\n")


if __name__ == "__main__":
    main()
