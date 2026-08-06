#!/bin/bash
echo "=== DEBUT NETTOYAGE DAILY - $(date) ==="

# Nettoyer Docker (images inutilisées, conteneurs arrêtés, cache de build)
echo "1. Nettoyage de Docker..."
docker system prune -af
docker builder prune -af

# Nettoyer les fichiers de clips temporaires et résidus de crashs vieux de plus de 2 jours
echo "2. Nettoyage des fichiers temporaires du bot..."
find /home/ubuntu/twitch_bot/clips_downloaded/ -type f -mtime +2 -delete
find /home/ubuntu/twitch_bot/youtube_crashes_output/processed_chunks/ -type f -mtime +2 -delete
find /home/ubuntu/twitch_bot/youtube_crashes_output/temp_clips/ -type f -mtime +2 -delete

# S'assurer que les fichiers temporaires vides (0 octet) de clips_downloaded sont supprimés immédiatement
find /home/ubuntu/twitch_bot/clips_downloaded/ -type f -size 0 -delete

echo "3. Espace disque restant :"
df -h /

echo "=== FIN NETTOYAGE DAILY - $(date) ==="
