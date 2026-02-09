import os
import requests
from datetime import datetime, timedelta
import csv
import time

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

def scrape_clips_for_streamers(streamer_list):
    access_token = get_access_token()
    started_at = (datetime.utcnow() - timedelta(hours=24)).isoformat() + 'Z'

    all_clips = []
    for streamer in streamer_list:
        print(f"🔎 Récupération des clips de {streamer}…")
        user_id = get_user_id(access_token, streamer)
        if not user_id:
            print(f"❌ Streamer {streamer} non trouvé.")
            continue

        clips = get_clips(access_token, user_id, first=20, started_at=started_at)
        if not clips:
            print(f"❌ Aucun clip trouvé pour {streamer}.")
            continue

        for clip in clips:
            clip_info = {
                'streamer': streamer,
                'title': clip['title'],
                'url': clip['url'],
                'views': clip['view_count'],
                'created_at': clip['created_at'],
                'duration': clip['duration']  # Ajout de la durée en secondes
            }
            all_clips.append(clip_info)

        time.sleep(1)  # Pause pour éviter le spam

    return all_clips

def save_clips_to_csv(clips, filename='clips_24h.csv'):
    # Trie les clips par nombre de vues (descendant)
    sorted_clips = sorted(clips, key=lambda x: x['views'], reverse=True)

    with open(filename, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['streamer', 'title', 'url', 'views', 'duration', 'created_at'])
        writer.writeheader()
        writer.writerows(sorted_clips)

    print(f"✅ {len(sorted_clips)} clips enregistrés dans {filename} (triés par vues) !")

def main():
    # Lis les pseudos depuis un fichier texte
    with open('streamers.txt', 'r', encoding='utf-8') as f:
        streamer_list = [line.strip() for line in f if line.strip()]

    if not streamer_list:
        print("❌ Aucun streamer dans le fichier streamers.txt")
        return

    # Récupère les clips
    all_clips = scrape_clips_for_streamers(streamer_list)

    if not all_clips:
        print("❌ Aucun clip trouvé pour la liste fournie.")
        return

    # Sauvegarde en CSV trié par nombre de vues
    save_clips_to_csv(all_clips)

if __name__ == "__main__":
    main()
