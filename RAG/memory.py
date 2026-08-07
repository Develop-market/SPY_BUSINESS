"""
═══════════════════════════════════════════════════════════
  08d_rag_memory.py
  MÉMOIRE CONVERSATIONNELLE
  ─────────────────────────────────────────────────────────
  Rôle : Garder l'historique de la conversation pour que
         l'IA comprenne les questions de suivi.

  Ex: Q1 "Quels sont les frais BACI ?"
      Q2 "Et pour SGCI ?"  ← l'IA sait que "Et" = frais
═══════════════════════════════════════════════════════════
"""

import sys
import os
import importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

config = importlib.import_module("config")
MEMORY_MAX_TURNS = config.MEMORY_MAX_TURNS

# ═══════════════════════════════════════════════════════════
#  CLASSE MÉMOIRE
# ═══════════════════════════════════════════════════════════

class ConversationMemory:
    """
    Gère l'historique de la conversation.

    Structure interne :
    [
      {"role": "user",      "content": "Quels sont les frais BACI ?"},
      {"role": "assistant", "content": "Les frais de tenue de compte..."},
      ...
    ]

    Limite : MEMORY_MAX_TURNS tours (question + réponse = 1 tour)
    Au-delà, les plus anciens sont supprimés (fenêtre glissante).
    """

    def __init__(self, max_turns: int = MEMORY_MAX_TURNS):
        self.max_turns = max_turns      # nombre de tours max conservés
        self.history   = []             # liste des échanges

    def add_user(self, message: str):
        """Ajoute une question utilisateur à l'historique."""
        self.history.append({
            "role"    : "user",
            "content" : message.strip(),
        })
        self._trim()

    def add_assistant(self, message: str):
        """Ajoute une réponse de l'assistant à l'historique."""
        self.history.append({
            "role"    : "assistant",
            "content" : message.strip(),
        })
        self._trim()

    def _trim(self):
        """
        Applique la fenêtre glissante.
        1 tour = 1 message user + 1 message assistant = 2 entrées.
        On conserve max_turns * 2 entrées.
        """
        max_entries = self.max_turns * 2
        if len(self.history) > max_entries:
            # Supprimer les entrées les plus anciennes
            self.history = self.history[-max_entries:]

    def format_for_prompt(self) -> str:
        """
        Formate l'historique en texte lisible pour le LLM.

        Format :
        Utilisateur : Quels sont les frais BACI ?
        Assistant   : Les frais de tenue de compte BACI sont...

        Utilisateur : Et pour SGCI ?
        Assistant   : Pour SGCI, les frais sont...
        """
        if not self.history:
            return "Aucun historique — début de conversation."

        # 2026-07-25 (audit chat, problème #10) : la DERNIÈRE réponse assistant reste ENTIÈRE —
        # c'est celle qu'une relance immédiate ("et pour X ?", "explique ce chiffre") référence
        # le plus souvent ; la tronquer à 500 caractères pouvait couper exactement l'info utile.
        # Seules les réponses plus ANCIENNES restent tronquées pour ne pas surcharger le contexte.
        dernier_index_assistant = max(
            (i for i, m in enumerate(self.history) if m["role"] == "assistant"), default=-1
        )

        lignes = []
        for i, msg in enumerate(self.history):
            role    = "Utilisateur" if msg["role"] == "user" else "Assistant"
            contenu = msg["content"]

            if msg["role"] == "assistant" and i != dernier_index_assistant and len(contenu) > 500:
                contenu = contenu[:500] + "... [réponse tronquée]"

            lignes.append(f"{role} : {contenu}")

        return "\n\n".join(lignes)

    def get_last_question(self) -> str | None:
        """Retourne la dernière question posée (utile pour le contexte)."""
        for msg in reversed(self.history):
            if msg["role"] == "user":
                return msg["content"]
        return None

    def clear(self):
        """Réinitialise complètement la mémoire."""
        self.history = []
        print("🧹 Mémoire effacée.")

    def summary(self) -> str:
        """Résumé de l'état de la mémoire."""
        nb_user      = sum(1 for m in self.history if m["role"] == "user")
        nb_assistant = sum(1 for m in self.history if m["role"] == "assistant")
        return (
            f"Mémoire : {nb_user} question(s) | "
            f"{nb_assistant} réponse(s) | "
            f"max {self.max_turns} tours"
        )


# ═══════════════════════════════════════════════════════════
#  TEST DIRECT
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("═" * 55)
    print("  TEST — MÉMOIRE CONVERSATIONNELLE")
    print("═" * 55)

    mem = ConversationMemory(max_turns=3)

    # Simuler une conversation
    echanges = [
        ("Quels sont les frais de tenue de compte BACI en 2024 ?",
         "Les frais de tenue de compte BACI pour les entreprises "
         "au S2 2024 sont de 5 000 FCFA/mois."),

        ("Et pour SGCI ?",
         "Pour SGCI, les frais de tenue de compte s'élèvent "
         "à 4 500 FCFA/mois au S1 2024."),

        ("Quelle banque est la moins chère ?",
         "Sur la base des données disponibles, SGCI est "
         "légèrement moins chère que BACI."),

        ("Et ECOBANK ?",
         "Les frais ECOBANK pour la tenue de compte sont "
         "de 6 000 FCFA/mois en 2024."),
    ]

    for question, reponse in echanges:
        mem.add_user(question)
        mem.add_assistant(reponse)
        print(f"\n➕ Ajout : {question[:50]}...")
        print(f"   {mem.summary()}")

    print("\n" + "─" * 55)
    print("HISTORIQUE FORMATÉ POUR LE LLM :")
    print("─" * 55)
    print(mem.format_for_prompt())

    print("\n" + "─" * 55)
    print("TEST CLEAR :")
    mem.clear()
    print(f"Après clear : {mem.summary()}")
    print("\n✅ Mémoire opérationnelle.")