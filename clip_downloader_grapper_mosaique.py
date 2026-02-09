import requests
from datetime import datetime, timedelta, timezone
import csv
import time
import random
import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

client_id = os.getenv("TWITCH_CLIENT_ID")
client_secret = os.getenv("TWITCH_CLIENT_SECRET")

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
    if not game_id: return 'N/A'
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
    if started_at: params['started_at'] = started_at
    response = requests.get(url, headers=headers, params=params)
    try: return response.json()['data']
    except KeyError: print("⚠️ Réponse inattendue :", response.json()); return []

def scrape_clips_for_streamers(streamer_list, max_clips_per_streamer=5):
    access_token = get_access_token()
    started_at = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    all_clips = []
    game_id_cache = {}
    for streamer in streamer_list:
        print(f"🔎 Récupération des clips de {streamer}…")
        user_id = get_user_id(access_token, streamer)
        if not user_id: print(f"❌ Streamer {streamer} non trouvé."); continue
        clips = get_clips(access_token, user_id, first=20, started_at=started_at)
        if not clips: print(f"❌ Aucun clip trouvé pour {streamer}."); continue
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

def save_clips_to_csv(clips, filename='clips_24h_filtered.csv', max_duration=720):
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
        print("❌ Aucun clip ne respecte la limite de durée."); return []
    best_clip = selected_clips[0]
    remaining_clips = selected_clips[1:]
    random.shuffle(remaining_clips)
    final_clips = [best_clip] + remaining_clips
    with open(filename, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['streamer', 'title', 'url', 'views', 'duration', 'created_at', 'category'])
        writer.writeheader()
        writer.writerows(final_clips)
    print(f"✅ {len(final_clips)} clips enregistrés dans {filename} (1er clip = le meilleur, le reste mélangé).")
    return final_clips

def get_next_filename(folder, base_name, ext):
    i = 1
    while True:
        filename = f"{base_name}_{i}{ext}"
        full_path = os.path.join(folder, filename)
        if not os.path.exists(full_path): return full_path
        i += 1

def download_twitch_clip(url, output_folder="clips"):
    if not os.path.exists(output_folder): os.makedirs(output_folder)
    output_file = get_next_filename(output_folder, "clip", ".mp4")
    command = f"streamlink --twitch-disable-ads {url} best -o \"{output_file}\""
    print(f"🔗 Téléchargement du clip : {url}")
    os.system(command)
    print(f"💾 Sauvegarde dans : {output_file}")
    return output_file

def extraire_image_clip(url, output_image):
    temp_file = "temp.ts"
    subprocess.run(f"streamlink --twitch-disable-ads {url} best -o \"{temp_file}\"", shell=True)
    subprocess.run(f"ffmpeg -i \"{temp_file}\" -ss 00:00:01 -vframes 1 \"{output_image}\" -y", shell=True)
    os.remove(temp_file)

def lire_et_incrementer_nombre(txt_path="nombre.txt"):
    if not os.path.exists(txt_path):
        with open(txt_path, 'w') as f: f.write('1'); return 1
    else:
        with open(txt_path, 'r+') as f:
            n = int(f.read().strip()) + 1
            f.seek(0); f.write(str(n)); f.truncate()
        return n

def creer_mosaique(images, logo_path, output_mosaique="mosaique_avec_logo.jpg", nombre=1):
    img_objs = [Image.open(img) for img in images]
    max_width = max(i.width for i in img_objs)
    max_height = max(i.height for i in img_objs)
    mosaique = Image.new('RGB', (max_width * 2, max_height * 2))
    positions = [(0, 0), (max_width, 0), (0, max_height), (max_width, max_height)]
    for pos, img in zip(positions, img_objs):
        mosaique.paste(img, pos)
    logo = Image.open(logo_path).convert("RGBA")
    logo_width = int(max_width * 1)
    ratio = logo_width / logo.width
    logo_height = int(logo.height * ratio)
    logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
    center_x = (mosaique.width - logo_width) // 2
    center_y = (mosaique.height - logo_height) // 2
    mosaique.paste(logo, (center_x, center_y), logo)
    draw = ImageDraw.Draw(mosaique)
    font_size = int(max_width * 0.1)
    try: font = ImageFont.truetype("Nunito-Black.ttf", font_size)
    except: font = ImageFont.load_default()
    draw.text((10, 10), f"#{nombre}", fill="white", font=font, stroke_width=2, stroke_fill="black")
    mosaique.save(output_mosaique)
    print(f"✅ Mosaïque finale sauvegardée : {output_mosaique}")

def main():
    desired_category = "Minecraft"
    with open('streamers.txt', 'r', encoding='utf-8') as f:
        streamer_list = [line.strip() for line in f if line.strip()]
    if not streamer_list: print("❌ Aucun streamer."); return
    all_clips = scrape_clips_for_streamers(streamer_list, max_clips_per_streamer=5)
    if not all_clips: print("❌ Aucun clip trouvé."); return
    filtered_clips = [clip for clip in all_clips if clip['category'].lower() == desired_category.lower()]
    if not filtered_clips: print(f"❌ Aucun clip trouvé pour {desired_category}."); return
    final_clips = save_clips_to_csv(filtered_clips, max_duration=720)
    if not final_clips: return
    # Télécharge les clips (et récupère leurs images)
    images = []
    output_folder = "mosaique_temp"
    os.makedirs(output_folder, exist_ok=True)
    for i, clip in enumerate(final_clips[:4], 1):
        print(f"📸 Extraction image clip {i} : {clip['url']}")
        output_image = os.path.join(output_folder, f"clip_{i}.jpg")
        extraire_image_clip(clip['url'], output_image)
        images.append(output_image)
    nombre = lire_et_incrementer_nombre()
    creer_mosaique(images, logo_path="logo.png", nombre=nombre)
    for img in images: os.remove(img)
    os.rmdir(output_folder)
    # Télécharge tous les clips finaux
    for clip in final_clips: download_twitch_clip(clip['url'])

if __name__ == "__main__":
    main()
