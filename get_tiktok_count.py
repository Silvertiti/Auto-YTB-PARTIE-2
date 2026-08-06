# -*- coding: utf-8 -*-
import sys
import re
import json
import requests

def get_tiktok_profile_stats(username):
    if not username.startswith("@"):
        username = f"@{username}"
        
    url = f"https://www.tiktok.com/{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            print(f"❌ Erreur HTTP {res.status_code} lors du chargement du profil {username}")
            return None

        html = res.text
        
        # Recherche des statistiques dans les balises JSON réhydratées par TikTok
        video_count_match = re.search(r'"videoCount"\s*:\s*(\d+)', html)
        follower_count_match = re.search(r'"followerCount"\s*:\s*(\d+)', html)
        heart_count_match = re.search(r'"heartCount"\s*:\s*(\d+)', html)
        
        stats = {
            "username": username,
            "video_count": int(video_count_match.group(1)) if video_count_match else "Inconnu",
            "follower_count": int(follower_count_match.group(1)) if follower_count_match else "Inconnu",
            "heart_count": int(heart_count_match.group(1)) if heart_count_match else "Inconnu",
        }
        
        return stats
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des données : {e}")
        return None

if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    user = sys.argv[1] if len(sys.argv) > 1 else "@youtubecourt"
    data = get_tiktok_profile_stats(user)
    if data:
        print("\n" + "="*50)
        print(f"COMPTE TIKTOK : {data['username']}")
        print(f"Nombre TOTAL de vidéos publiées : {data['video_count']}")
        print(f"Nombre d'abonnés : {data['follower_count']}")
        print(f"Nombre total de J'aime (Likes) : {data['heart_count']}")
        print("="*50 + "\n")
