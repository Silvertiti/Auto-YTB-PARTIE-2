FROM python:3.11-slim

# Installation de FFmpeg (pour la vidéo) et git/outils
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie de tout le code
COPY . .

# Par défaut, on ne lance rien ici, c'est le docker-compose qui décide