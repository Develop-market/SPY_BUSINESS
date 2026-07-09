@echo off
title Dashboard SGCI - Demarrage
echo ============================================
echo   DEMARRAGE DU DASHBOARD SGCI
echo ============================================
echo.

echo [1/3] Demarrage de PostgreSQL...
"C:\Program Files\PostgreSQL\17\bin\pg_ctl" start -D "C:\pgdata" -w
echo.

echo [2/3] Ouverture du navigateur...
start "" http://localhost:5000
echo.

echo [3/3] Demarrage du serveur dashboard...
echo (Laisse cette fenetre OUVERTE tant que tu utilises le dashboard)
echo Pour arreter : ferme cette fenetre.
echo.

rem Se place dans le dossier du .bat (BACK), puis trouve le dossier SGCI quel que soit son nom
cd /d "%~dp0"
for /d %%D in ("SGCI Strategic Intelligence*") do cd /d "%%D\spybusiness"

python server.py

pause
