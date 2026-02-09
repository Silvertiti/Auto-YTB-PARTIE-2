import os
import requests
from datetime import datetime, timedelta

client_id = os.getenv("TWITCH_CLIENT_ID")
client_secret = os.getenv("TWITCH_CLIENT_SECRET")

def get_access_token():
    url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'client_credentials'
    }
    response = requests.post(url, params=params)
    return response.json()['access_token']

def get_user_id(access_token, username):
    url = 'https://api.twitch.tv/helix/users'
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    params = {'login': username}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()['data']
    return data[0]['id'] if data else None

def get_clips(access_token, broadcaster_id, first=20, started_at=None):
    url = 'https://api.twitch.tv/helix/clips'
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    params = {
        'broadcaster_id': broadcaster_id,
        'first': first,
    }
    if started_at:
        params['started_at'] = started_at
    response = requests.get(url, headers=headers, params=params)
    data = response.json()['data']
    return data

def main():
    streamer_name = 'anyme023'  # Remplace par le pseudo du streamer
    access_token = get_access_token()
    user_id = get_user_id(access_token, streamer_name)
    if not user_id:
        print("Streamer non trouvé.")
        return

    # Date d'il y a 24 heures au format ISO UTC
    started_at = (datetime.utcnow() - timedelta(hours=24)).isoformat() + 'Z'
    
    clips = get_clips(access_token, user_id, first=20, started_at=started_at)
    if not clips:
        print("Aucun clip trouvé pour les dernières 24h.")
        return

    print(f"Clips des dernières 24h de {streamer_name} :")
    for clip in clips:
        title = clip['title']
        url = clip['url']
        views = clip['view_count']
        created_at = clip['created_at']
        print(f"- {title} ({created_at}) : {url} ({views} vues)")

if __name__ == "__main__":
    main()
