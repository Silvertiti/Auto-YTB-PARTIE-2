import requests
from datetime import datetime, timedelta, timezone
import csv
import time
import random
import os

client_id = 'nhplbk0cauctrdgh13rf75sv387lye'
client_secret = 'cycmd8gr3xozmxacw8yj7v3tb9d1qz'

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

def get_game_name(access_token, game_id):
    if not game_id:
        return 'N/A'
    url = 'https://api.twitch.tv/helix/games'
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    params = {'id': game_id}
    response = requests.get(url, headers=headers, params=params)
    data = response.json().get('data', [])
    return data[0]['name'] if data else 'N/A'

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
    try:
        data = response.json()['data']
    except KeyError:
        print("⚠️ Réponse inattendue :", response.json())
        return []
    return data

def scrape_clips_for_streamers(streamer_list, max_clips_per_streamer=5):
    access_token = get_access_token()
    started_at = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    all_clips = []
    game_id_cache = {}

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

        clips_sorted = sorted(clips, key=lambda x: x['view_count'], reverse=True)[:max_clips_per_streamer]

        for clip in clips_sorted:
            game_id = clip.get('game_id', None)
            if game_id not in game_id_cache:
                game_name = get_game_name(access_token, game_id)
                game_id_cache[game_id] = game_name
                time.sleep(0.5)
            else:
                game_name = game_id_cache[game_id]

            clip_info = {
                'streamer': streamer,
                'title': clip['title'],
                'url': clip['url'],
                'views': clip['view_count'],
                'duration': clip['duration'],
                'created_at': clip['created_at'],
                'category': game_name
            }
            all_clips.append(clip_info)

        time.sleep(1)

    return all_clips

def save_clips_to_csv_and_download(clips, filename='clips_24h_filtered.csv', max_duration=720):
    sorted_clips = sorted(clips, key=lambda x: x['views'], reverse=True)

    selected_clips = []
    total_duration = 0

    for clip in sorted_clips:
        clip_duration = clip['duration']
        if total_duration + clip_duration <= max_duration:
            selected_clips.append(clip)
            total_duration += clip_duration
        else:
            break

    if not selected_clips:
        print("❌ Aucun clip ne respecte la limite de durée.")
        return

    # Le meilleur clip en premier, le reste mélangé
    best_clip = selected_clips[0]
    remaining_clips = selected_clips[1:]
    random.shuffle(remaining_clips)
    final_clips = [best_clip] + remaining_clips

    # Sauvegarde CSV
    with open(filename, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['streamer', 'title', 'url', 'views', 'duration', 'created_at', 'category'])
        writer.writeheader()
        writer.writerows(final_clips)

    print(f"✅ {len(final_clips)} clips enregistrés dans {filename} (1er clip = le meilleur, le reste mélangé).")
    
    # Télécharge tous les clips finaux
    for clip in final_clips:
        download_twitch_clip(clip['url'])

def get_next_filename(folder, base_name, ext):
    i = 1
    while True:
        filename = f"{base_name}_{i}{ext}"
        full_path = os.path.join(folder, filename)
        if not os.path.exists(full_path):
            return full_path
        i += 1

def download_twitch_clip(url, output_folder="clips"):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    output_file = get_next_filename(output_folder, "clip", ".mp4")
    command = f"streamlink --twitch-disable-ads {url} best -o \"{output_file}\""

    print(f"🔗 Téléchargement du clip : {url}")
    print(f"💾 Sauvegarde dans : {output_file}")

    os.system(command)
    print("✅ Téléchargement terminé.")

def main():
    desired_category = "Minecraft"

    with open('streamers.txt', 'r', encoding='utf-8') as f:
        streamer_list = [line.strip() for line in f if line.strip()]

    if not streamer_list:
        print("❌ Aucun streamer dans le fichier streamers.txt")
        return

    all_clips = scrape_clips_for_streamers(streamer_list, max_clips_per_streamer=5)

    if not all_clips:
        print("❌ Aucun clip trouvé pour la liste fournie.")
        return

    filtered_clips = [clip for clip in all_clips if clip['category'].lower() == desired_category.lower()]

    if not filtered_clips:
        print(f"❌ Aucun clip trouvé pour la catégorie {desired_category}.")
        return

    save_clips_to_csv_and_download(filtered_clips, max_duration=720)

if __name__ == "__main__":
    main()
