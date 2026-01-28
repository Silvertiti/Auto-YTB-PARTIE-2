import requests
from datetime import datetime, timedelta, timezone
import csv
import time
import random
import os
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, concatenate_videoclips

client_id = 'nhplbk0cauctrdgh13rf75sv387lye'
client_secret = 'cycmd8gr3xozmxacw8yj7v3tb9d1qz'

def get_access_token():
    url = 'https://id.twitch.tv/oauth2/token'
    params = {'client_id': client_id, 'client_secret': client_secret, 'grant_type': 'client_credentials'}
    response = requests.post(url, params=params)
    return response.json()['access_token']

def get_user_id(access_token, username):
    url = 'https://api.twitch.tv/helix/users'
    headers = {'Client-ID': client_id, 'Authorization': f'Bearer {access_token}'}
    params = {'login': username}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()['data']
    return data[0]['id'] if data else None

def get_game_name(access_token, game_id):
    if not game_id:
        return 'N/A'
    url = 'https://api.twitch.tv/helix/games'
    headers = {'Client-ID': client_id, 'Authorization': f'Bearer {access_token}'}
    params = {'id': game_id}
    response = requests.get(url, headers=headers, params=params)
    data = response.json().get('data', [])
    return data[0]['name'] if data else 'N/A'

def get_clips(access_token, broadcaster_id, first=20, started_at=None):
    url = 'https://api.twitch.tv/helix/clips'
    headers = {'Client-ID': client_id, 'Authorization': f'Bearer {access_token}'}
    params = {'broadcaster_id': broadcaster_id, 'first': first}
    if started_at:
        params['started_at'] = started_at
    response = requests.get(url, headers=headers, params=params)
    try:
        return response.json()['data']
    except KeyError:
        print("⚠️ Réponse inattendue :", response.json())
        return []

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
                time.sleep(0.2)
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
        time.sleep(0.5)
    return all_clips

def save_clips_to_csv(clips, filename='clips_24h_filtered.csv', max_duration=720):
    sorted_clips = sorted(clips, key=lambda x: x['views'], reverse=True)
    selected_clips = []
    total_duration = 0
    for clip in sorted_clips:
        if total_duration + clip['duration'] <= max_duration:
            selected_clips.append(clip)
            total_duration += clip['duration']
    if not selected_clips:
        print("❌ Aucun clip ne respecte la limite de durée.")
        return []
    best_clip = selected_clips[0]
    random.shuffle(selected_clips[1:])
    final_clips = [best_clip] + selected_clips[1:]
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['streamer', 'title', 'url', 'views', 'duration', 'created_at', 'category'])
        writer.writeheader()
        writer.writerows(final_clips)
    print(f"✅ {len(final_clips)} clips sauvegardés dans {filename}")
    return final_clips

def download_twitch_clip(url, output_folder="clips", clip_number=1):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    filename = f"clip_{clip_number}.mp4"
    path = os.path.join(output_folder, filename)
    command = f"streamlink --twitch-disable-ads {url} best -o \"{path}\""
    print(f"🎥 Téléchargement clip {clip_number} : {url}")
    os.system(command)
    print(f"💾 Sauvegardé : {path}")
    return path

def concatener_videos_moviepy(liste_fichiers, output_file="video_finale.mp4"):
    print("🎬 Concaténation avec MoviePy…")
    clips = [VideoFileClip(f).fx(lambda clip: clip.set_audio(clip.audio)) for f in liste_fichiers]
    final_clip = concatenate_videoclips(clips, method="compose")
    final_clip.write_videofile(output_file, codec="libx264", audio_codec="aac")
    print(f"✅ Vidéo finale créée : {output_file}")

def main():
    category = "Minecraft"
    with open('streamers.txt', 'r', encoding='utf-8') as f:
        streamer_list = [line.strip() for line in f if line.strip()]
    all_clips = scrape_clips_for_streamers(streamer_list, max_clips_per_streamer=5)
    filtered_clips = [c for c in all_clips if c['category'].lower() == category.lower()]
    final_clips = save_clips_to_csv(filtered_clips, max_duration=720)
    if not final_clips:
        return
    clips_paths = []
    for i, clip in enumerate(final_clips, start=1):
        path = download_twitch_clip(clip['url'], clip_number=i)
        clips_paths.append(path)
    concatener_videos_moviepy(clips_paths)

if __name__ == "__main__":
    main()
