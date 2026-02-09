FROM python:3.11-slim

# Dépendances système pour OpenCV, FFmpeg et le Web
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installation des libs Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copie du projet
COPY . .

# Exposition du port Flask
EXPOSE 5000

# Lancement de l'interface
CMD ["python", "app.py"]