# -*- coding: utf-8 -*-
"""
creer_compte_test.py
====================
Crée ou met à jour le compte 'test' avec mot de passe 'test1234'
en RETIRANT l'assistant conversationnel ('chat') de ses droits.

Usage:
    python creer_compte_test.py
    python creer_compte_test.py --remote   (pour exécuter sur DATABASE_URL_CIBLE / Supabase)
"""
import os
import sys
from pathlib import Path

# Ajouter dash_app au PYTHONPATH
dash_app_dir = Path(__file__).resolve().parent / "SGCI Strategic Intelligence — Design System" / "spybusiness" / "dash_app"
sys.path.insert(0, str(dash_app_dir))

import psycopg2
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

load_dotenv()

# Droits pour le compte test : tous les écrans d'analyse, SANS le chat, SANS ajout, SANS admin
DROITS_TEST = "apercu,cb,strategie,stratop"
IDENTIFIANT = "test"
MDP = "test1234"

def get_connection():
    if "--remote" in sys.argv:
        url = os.getenv("DATABASE_URL_CIBLE") or os.getenv("DATABASE_URL")
        if not url:
            raise ValueError("DATABASE_URL_CIBLE ou DATABASE_URL non définie dans le .env")
        print(f"[config] Connexion à la base distante : {url.split('@')[-1] if '@' in url else '***'}")
        return psycopg2.connect(url)
    else:
        # Base locale
        from db import DB
        print(f"[config] Connexion à la base locale : {DB.get('host')}:{DB.get('port')}/{DB.get('dbname')}")
        return psycopg2.connect(**DB)

def configurer_compte_test():
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Vérifier si l'utilisateur existe déjà
        cur.execute("SELECT id, identifiant, role, droits FROM utilisateurs WHERE LOWER(identifiant) = %s", (IDENTIFIANT,))
        row = cur.fetchone()
        
        empreinte = generate_password_hash(MDP)
        
        if row:
            print(f"[securite] L'utilisateur '{IDENTIFIANT}' existe déjà (id={row[0]}). Mise à jour du mot de passe et des droits...")
            cur.execute("""
                UPDATE utilisateurs 
                SET empreinte = %s, role = 'lecture', droits = %s, actif = TRUE 
                WHERE id = %s
            """, (empreinte, DROITS_TEST, row[0]))
        else:
            print(f"[securite] Création de l'utilisateur '{IDENTIFIANT}'...")
            cur.execute("""
                INSERT INTO utilisateurs (identifiant, empreinte, role, droits, actif)
                VALUES (%s, %s, 'lecture', %s, TRUE)
            """, (IDENTIFIANT, empreinte, DROITS_TEST))
        
        conn.commit()
        
        # Vérification
        cur.execute("SELECT identifiant, role, droits, actif FROM utilisateurs WHERE LOWER(identifiant) = %s", (IDENTIFIANT,))
        res = cur.fetchone()
        print("=" * 60)
        print(" COMPTE TEST CONFIGURÉ AVEC SUCCÈS")
        print(f"   Identifiant : {res[0]}")
        print(f"   Mot de passe: {MDP}")
        print(f"   Rôle        : {res[1]}")
        print(f"   Droits      : {res[2]}")
        print(f"   Chat (LLM)  : NON INCLUS (retiré comme exigé)")
        print("=" * 60)
        
        cur.close()
        conn.close()
    except Exception as e:
        print("[erreur] Échec de la configuration du compte test :", e)

if __name__ == "__main__":
    configurer_compte_test()
