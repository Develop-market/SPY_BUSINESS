# Image de production du dashboard SpyBusiness (Cloud Run).
# Contexte de build = racine du dépôt (BACK/), pour pouvoir copier à la fois
# spybusiness/ (app Flask) et RAG/ (chaîne de recherche sémantique) dedans.
#
# Volontairement absent de cette image : PIPELINE/ (pipeline d'extraction PDF→BD,
# dépendances énormes — docling/paddleocr/torch-vision). Le bouton "Ajouter des
# données" se masque automatiquement côté app quand ce dossier est absent
# (voir /api/features dans server.py). L'extraction de nouveaux documents continue
# de se faire en local, en pointant sur la même base (Supabase) via le même .env.

FROM python:3.13-slim

# libgomp1 : requis par torch/numpy en CPU. build-essential : au cas où un wheel
# précompilé manquerait pour l'architecture cible et nécessiterait une compilation.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# BACK_DIR = /app explicitement : évite toute dépendance à la profondeur des
# dossiers du dépôt local (spybusiness/ est ici copié directement dans /app,
# pas sous "SGCI Strategic Intelligence — Design System/spybusiness/").
ENV BACK_DIR=/app
ENV PYTHONUNBUFFERED=1

COPY ["SGCI Strategic Intelligence — Design System/spybusiness/requirements-deploy.txt", "./requirements-deploy.txt"]
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY ["SGCI Strategic Intelligence — Design System/spybusiness/", "./"]
COPY RAG/ ./RAG/

EXPOSE 8080
CMD ["python", "server.py"]
