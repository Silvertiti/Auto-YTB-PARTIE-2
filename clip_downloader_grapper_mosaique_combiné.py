import requests
from datetime import datetime, timedelta, timezone
import csv
import time
import random
import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

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

def download_twitch_clip(url, index, output_folder="clips"):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    filename = f"clip_{index}.mp4"
    path = os.path.join(output_folder, filename)
    command = f"streamlink --twitch-disable-ads {url} best -o \"{path}\""
    print(f"🎥 Téléchargement : {url}")
    os.system(command)
    print(f"💾 Sauvegarde dans : {path}")
    encoded_path = path.replace(".mp4", "_encoded.mp4")
    reencode_clip(path, encoded_path)
    os.remove(path)
    return encoded_path

def reencode_clip(input_file, output_file):
    command = f"ffmpeg -i \"{input_file}\" -vf fps=30 -c:v libx264 -preset veryfast -c:a aac -b:a 192k -y \"{output_file}\""
    subprocess.run(command, shell=True)

def extraire_image_clip(url, output_image):
    temp_file = "temp.ts"
    subprocess.run(f"streamlink --twitch-disable-ads {url} best -o \"{temp_file}\"", shell=True)
    subprocess.run(f"ffmpeg -i \"{temp_file}\" -ss 00:00:01 -vframes 1 \"{output_image}\" -y", shell=True)
    os.remove(temp_file)

def lire_et_incrementer_nombre(txt_path="nombre.txt"):
    if not os.path.exists(txt_path):
        with open(txt_path, 'w') as f:
            f.write('1')
        return 1
    else:
        with open(txt_path, 'r+') as f:
            n = int(f.read().strip()) + 1
            f.seek(0)
            f.write(str(n))
            f.truncate()
        return n

def creer_mosaique(images, logo_path, output="mosaique_avec_logo.jpg", nombre=1):
    imgs = [Image.open(img) for img in images]
    max_width, max_height = max(i.width for i in imgs), max(i.height for i in imgs)
    mosaique = Image.new('RGB', (max_width * 2, max_height * 2))
    positions = [(0,0), (max_width,0), (0,max_height), (max_width,max_height)]
    for pos, img in zip(positions, imgs):
        mosaique.paste(img, pos)
    logo = Image.open(logo_path).convert("RGBA")
    ratio = (max_width * 1) / logo.width
    logo = logo.resize((int(logo.width * ratio), int(logo.height * ratio)), Image.Resampling.LANCZOS)
    cx = (mosaique.width - logo.width)//2
    cy = (mosaique.height - logo.height)//2
    mosaique.paste(logo, (cx, cy), logo)
    draw = ImageDraw.Draw(mosaique)
    try:
        font = ImageFont.truetype("Nunito-Black.ttf", int(max_width*0.1))
    except:
        font = ImageFont.load_default()
    draw.text((10,10), f"#{nombre}", fill="white", font=font, stroke_width=2, stroke_fill="black")
    mosaique.save(output)
    print(f"✅ Mosaïque sauvegardée : {output}")

def concatener_videos(liste_fichiers, output_file="video_finale.mp4"):
    with open("liste_clips.txt", "w", encoding="utf-8") as f:
        for clip in liste_fichiers:
            f.write(f"file '{os.path.abspath(clip)}'\n")
    command = f"ffmpeg -f concat -safe 0 -i liste_clips.txt -c:v libx264 -c:a aac -strict -2 -y {output_file}"
    subprocess.run(command, shell=True)
    os.remove("liste_clips.txt")
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
    for i, clip in enumerate(final_clips, 1):
        path = download_twitch_clip(clip['url'], i)
        clips_paths.append(path)
    images = []
    os.makedirs("mosaique_temp", exist_ok=True)
    for i, clip in enumerate(final_clips[:4], 1):
        img = f"mosaique_temp/clip_{i}.jpg"
        extraire_image_clip(clip['url'], img)
        images.append(img)
    nombre = lire_et_incrementer_nombre()
    creer_mosaique(images, logo_path="logo.png", nombre=nombre)
    for img in images:
        os.remove(img)
    os.rmdir("mosaique_temp")
    concatener_videos(clips_paths)

if __name__ == "__main__":
    main()
