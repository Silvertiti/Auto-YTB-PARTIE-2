FROM python:3.11-slim

# 1. DÉPENDANCES SYSTÈME
# - ffmpeg : Pour le montage vidéo
# - libgl1... / libglib... : Indispensables pour OpenCV (cv2)
# - libfontconfig1 : CRUCIAL pour que FFmpeg puisse écrire du texte (drawtext)
# - libgomp1 : Souvent requis par PyTorch/YOLO (best.pt) pour les calculs CPU
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    libxext6 \
    libfontconfig1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. INSTALLATION PYTHON (Optimisation du cache Docker)
# On copie d'abord requirements.txt pour ne pas réinstaller les libs
# si tu changes juste une ligne de code dans main.py
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 3. COPIE DU PROJET
COPY . .

# 4. EXPOSITION DU PORT (Pour l'interface Web Flask)
EXPOSE 5000

# 5. COMMANDE PAR DÉFAUT
# (Celle-ci lance le site web. Le docker-compose écrasera cette ligne
# pour le deuxième conteneur de stats).
CMD ["python", "app.py"]