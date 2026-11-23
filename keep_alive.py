# -*- coding: utf-8 -*-
"""
keep_alive.py
=============
Envoie un ping toutes les 10 minutes à l'application Render pour
l'empêcher de s'endormir (maintient le service 100% chaud et rapide).
"""
import time
import urllib.request
import datetime

URL = "https://spybusiness.onrender.com/sante"
INTERVAL_SECONDS = 600  # 10 minutes

def ping():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "SpyBusiness-KeepAlive/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"[{now}] Ping réussi : {resp.status} - {resp.read().decode('utf-8').strip()}")
    except Exception as e:
        print(f"[{now}] Erreur lors du ping : {e}")

if __name__ == "__main__":
    print(f"Démarrage du Keep-Alive pour {URL}...")
    print(f"Intervalle : toutes les {INTERVAL_SECONDS // 60} minutes. (Appuyez sur Ctrl+C pour arrêter)")
    # Premier ping immédiat
    ping()
    while True:
        time.sleep(INTERVAL_SECONDS)
        ping()
