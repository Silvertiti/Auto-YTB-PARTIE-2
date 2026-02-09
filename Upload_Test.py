import requests
import os

url = 'https://getlate.dev/api/v1/posts'
headers = {
    'Authorization': 'Bearer ' + (os.getenv('LATE_API_KEY') or ''),
    'Content-Type': 'application/json'
}

data = {
    'content': 'Anyme pète les plombs sur de la culture G... C\'est un désastre ! 😂😭#Anyme #CultureG #RageQuit #TwitchFR #ClipTwitch #BestOfTwitch #ShortsYT #LiveFail #CoupDeFolie #StreamerFR #Drole',
    
    # --- CORRECTION ICI ---
    # Il fallait ajouter 'type': 'video'
    'mediaItems': [
        {
            'url': 'https://silvertiti.fr/tiktok_final_4.mp4', 
            'type': 'video' 
        }
    ],
    # ----------------------

    'platforms': [{'platform': 'tiktok', 'accountId': '697a153677637c5c857c9c47'}],
    'tiktokSettings': {
        'privacy_level': 'PUBLIC_TO_EVERYONE',
        'allow_comment': True,
        'allow_duet': True,
        'allow_stitch': True,
        'content_preview_confirmed': True,
        'express_consent_given': True
    },
    'publishNow': True
}

# Envoi de la requête
print("Envoi de la requête à Late...")
response = requests.post(url, headers=headers, json=data)

try:
    res_data = response.json()
    if response.ok:
        print(f"✅ Posté avec succès ! ID: {res_data.get('_id', res_data.get('id', 'Inconnu'))}")
    else:
        print("❌ L'API a renvoyé une erreur :", res_data)
except Exception as e:
    print("❌ Erreur lors de la lecture du JSON :", e)
    print("Réponse brute :", response.text)