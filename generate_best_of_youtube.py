import os
import sys
import json
import subprocess
import time
import shutil
from datetime import datetime, timedelta
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import requests
import urllib3

# Désactivation des avertissements SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Charger les variables d'environnement
load_dotenv()

# Fix Unicode issues on Windows consoles
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Configuration
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
OUTPUT_DIR = "youtube_crashes_output"
TEMP_DIR = os.path.join(OUTPUT_DIR, "temp_clips")
TRASH_DIR = os.path.join(OUTPUT_DIR, "processed_chunks")
FINAL_VIDEO_PATH = os.path.join(OUTPUT_DIR, "best_of_twitch_24h.mp4")
THUMBNAIL_PATH = os.path.join(OUTPUT_DIR, "thumbnail.jpg")
LOGO_PATH = "logo2.png"
FONT_PATH = "Nunito-Black.ttf"
STREAMERS_FILE = "streamers.txt"
MIN_DURATION_SECONDS = 600  # 10 minutes
MAX_CLIPS_PER_STREAMER = 3  # <--- NOUVEAU : Maximum 3 clips par personne
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3" 

# Nettoyage et création des dossiers
if os.path.exists(TEMP_DIR):
    try: shutil.rmtree(TEMP_DIR)
    except: pass
if os.path.exists(TRASH_DIR):
    try: shutil.rmtree(TRASH_DIR)
    except: pass

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(TRASH_DIR, exist_ok=True)

# Création du fichier streamers.txt s'il n'existe pas
if not os.path.exists(STREAMERS_FILE):
    with open(STREAMERS_FILE, "w", encoding="utf-8") as f:
        f.write("Squeezie\nGotaga\nKamet0\nJLTomy\nAminematue")
    print(f"⚠️ Fichier {STREAMERS_FILE} créé. Ajoutez-y vos streamers.")

def get_twitch_token():
    url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': TWITCH_CLIENT_ID,
        'client_secret': TWITCH_CLIENT_SECRET,
        'grant_type': 'client_credentials'
    }
    response = requests.post(url, params=params, verify=False)
    response.raise_for_status()
    return response.json()['access_token']

def get_game_id(headers, game_name):
    url = 'https://api.twitch.tv/helix/games'
    params = {'name': game_name}
    response = requests.get(url, headers=headers, params=params, verify=False)
    if response.status_code == 200:
        data = response.json().get('data', [])
        if data:
            return data[0]['id']
    return None

def get_clips_for_game(headers, game_id, start_time, end_time, limit=100):
    url = 'https://api.twitch.tv/helix/clips'
    params = {
        'game_id': game_id,
        'first': limit,
        'started_at': start_time,
        'ended_at': end_time
    }
    response = requests.get(url, headers=headers, params=params, verify=False)
    if response.status_code == 200:
        return response.json()['data']
    return []

def download_clip(url, output_path):
    print(f"📥 DL: {url}")
    cmd = [sys.executable, "-m", "streamlink", "--twitch-disable-ads", url, "best", "-o", output_path]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0 and os.path.exists(output_path)

def get_video_duration(file_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=startupinfo)
        return float(result.stdout.strip())
    except:
        return 0.0

def standardize_video(input_path, output_path, streamer_name):
    print(f"⚙️ Encodage + Overlay texte ({streamer_name}) : {os.path.basename(input_path)}")
    safe_name = streamer_name.replace(":", "").replace("'", "")
    abs_font_path = os.path.abspath(FONT_PATH).replace("\\", "/").replace(":", "\\:")

    vf_chain = (
        f"scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,"
        f"drawtext=fontfile='{abs_font_path}':text='{safe_name}':"
        f"fontcolor=white:fontsize=60:x=50:y=50:"
        f"shadowcolor=black:shadowx=3:shadowy=3" 
    )

    cmd = [
        "ffmpeg", "-y", "-i", input_path, "-vf", vf_chain,
        "-c:v", "libx264", "-preset", "fast", "-r", "30",
        "-c:a", "aac", "-ar", "44100", "-b:a", "192k",
        "-f", "mp4", output_path
    ]
    
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.exists(output_path)

def extract_frame(video_path, image_path):
    cmd = ["ffmpeg", "-y", "-ss", "00:00:02", "-i", video_path, "-vframes", "1", "-q:v", "2", image_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.exists(image_path)

def generate_ollama_metadata(streamers):
    # On nettoie la liste des streamers (pas de doublons)
    unique_streamers = list(set(streamers))
    streamers_str = ", ".join(unique_streamers)
    
    # On prépare la liste formatée avec les manettes pour le prompt
    formatted_list_example = "\n".join([f"🎮 {s}" for s in unique_streamers])

    # PROMPT STRICT POUR OLLAMA
    prompt = f"""
    Tu es un expert YouTube et Community Manager spécialisé dans GTA 5 RP.
    Tu dois générer un titre VIRAL (TOUT EN MAJUSCULES) et une description pour une vidéo compilation "Best Of" du serveur GTA 5 RP "Flashback".
    
    Contexte : C'est le récap de la soirée d'hier sur Flashback.

    Voici les streamers présents : {streamers_str}

    RÈGLES STRICTES POUR LA DESCRIPTION :
    1. Commence par une phrase d'accroche fun et explosive spécifiquement sur GTA RP / Flashback avec des emojis (🔥😂🚔).
    2. Ensuite, liste les streamers EXACTEMENT sous ce format :
    👾 Streamers présents dans ce best-of :
    🎮 [Nom du Streamer 1]
    🎮 [Nom du Streamer 2]
    ...
    3. Finis par ce bloc de texte EXACT :
    ❤️ Merci à tous ces streamers de Flashback pour leurs scènes incroyables !
    🔔 Abonne-toi et active la cloche pour le récap quotidien de Flashback !
    📺 Tous les clips sont issus du serveur GTA 5 RP Flashback.
    👉 Pour suivre les aventures, check leurs chaînes Twitch !

    4. Ajoute des hashtags pertinents à la fin (#GTA5RP #Flashback #FlashbackRP #GTARP #TwitchFR + nom des streamers).

    Format de sortie JSON attendu :
    {{
        "title": "TITRE VIRAL SUR FLASHBACK ICI (ex: IL SE FAIT ARRÊTER PAR LA POLICE ?! 🚨)",
        "description": "DESCRIPTION COMPLETE ICI"
    }}
    """
    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }
    
    print("🧠 Génération métadonnées Ollama (Style Crazy Town)...")
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60, verify=False)
        if response.status_code == 200:
            return json.loads(response.json()['response'])
    except Exception as e:
        print(f"⚠️ Ollama n'a pas répondu ({e}), utilisation du template par défaut.")
    
    # --- FALLBACK (SI OLLAMA PLANTE) ---
    # On génère le texte manuellement en Python pour être sûr d'avoir le style demandé
    fallback_streamers_list = "\n".join([f"🎮 {s}" for s in unique_streamers])
    
    # On crée des hashtags dynamiques basés sur les streamers
    hashtags = "#BestOfTwitch #TwitchFR #ClipsTwitch #LiveFail #MomentsDrôles " + " ".join([f"#{s.replace(' ', '')}" for s in unique_streamers[:5]])

    return {
        "title": f"BEST OF GTA RP FLASHBACK DE LA VEILLE ! 💥😂 ({unique_streamers[0] if unique_streamers else 'Multi'} et les autres !)",
        "description": f"""💥 Retour sur la soirée d'hier sur Flashback ! Des scènes RP légendaires, des courses-poursuites et des fous rires ! 🔥😂
        
👾 Streamers présents dans ce best-of :
{fallback_streamers_list}

❤️ Merci à tous ces streamers de Flashback pour leurs scènes incroyables !
🔔 Abonne-toi et active la cloche pour le récap quotidien de Flashback !

📺 Tous les clips sont issus du serveur GTA 5 RP Flashback.
👉 Pour suivre les aventures, check leurs chaînes Twitch !

{hashtags} #GTA5RP #Flashback #FlashbackRP"""
    }

def create_thumbnail(image_paths, output_path):
    print("🖼️ Création de la miniature (Logo Only)...")
    valid_images = [img for img in image_paths if os.path.exists(img)]
    
    if not valid_images: return

    # Préparation de la mosaïque (4 images)
    images = [Image.open(p).convert("RGB") for p in valid_images[:4]]
    while len(images) < 4: images.append(images[-1])

    target_size = (1280, 720)
    images = [img.resize(target_size) for img in images]
    
    w, h = target_size
    mosaic = Image.new('RGB', (w*2, h*2))
    mosaic.paste(images[0], (0, 0))
    mosaic.paste(images[1], (w, 0))
    mosaic.paste(images[2], (0, h))
    mosaic.paste(images[3], (w, h))
    
    # --- AJOUT DU LOGO (Taillex1.5) ---
    if os.path.exists(LOGO_PATH):
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            
            logo_w = int(mosaic.width * 0.55) 
            
            ratio = logo_w / logo.width
            logo_h = int(logo.height * ratio)
            
            logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            
            # Centrage parfait
            x = (mosaic.width - logo_w) // 2
            y = (mosaic.height - logo_h) // 2
            
            mosaic.paste(logo, (x, y), logo)
        except Exception as e:
            print(f"⚠️ Erreur logo : {e}")

    # --- PAS DE TEXTE (Supprimé) ---

    # Redimensionnement final pour YouTube (1280x720)
    final_thumb = mosaic.resize((1280, 720), Image.Resampling.LANCZOS)
    final_thumb.save(output_path, quality=95)
    print(f"✅ Miniature sauvegardée : {output_path}")
def main():
    print("🚀 Démarrage du générateur Best Of GTA RP Flashback...")
    
    try:
        token = get_twitch_token()
        headers = {'Client-ID': TWITCH_CLIENT_ID, 'Authorization': f'Bearer {token}'}
    except Exception as e:
        print(f"❌ Erreur Auth Twitch : {e}")
        return

    # --- 1. Récupération de l'ID du jeu GTA V ---
    game_id = get_game_id(headers, "Grand Theft Auto V")
    if not game_id:
        print("❌ Impossible de trouver l'ID pour Grand Theft Auto V.")
        return
    print(f"🎮 GTA V Game ID: {game_id}")

    # --- 2. Définition de la période (Soirée d'hier 18h -> Aujourd'hui 6h) ---
    now = datetime.utcnow()
    # On considère 'hier' pour définir la soirée
    yesterday_date = now - timedelta(days=1)
    
    # Début : Hier 18:00
    start_time = yesterday_date.replace(hour=18, minute=0, second=0, microsecond=0)
    # Fin : Aujourd'hui 06:00
    end_time = now.replace(hour=6, minute=0, second=0, microsecond=0)
    
    # Si on est en train de tourner le script AVANT 6h du mat (ex: à 3h du mat le Mardi), 
    # la "soirée d'hier" est celle de Dimanche soir -> Lundi matin.
    # Mais le code ci-dessus prendrait Lundi (Hier) -> Mardi (Aujourd'hui).
    # Si 'now' est mardi 03:00, yesterday est Lundi. Start Lundi 18:00 -> End Mardi 06:00. 
    # Cela inclut le présent. C'est correct pour attraper les clips qui viennent de se passer.
    # Si 'now' est mardi 15:00, yesterday est Lundi. Start Lundi 18:00 -> End Mardi 06:00. 
    # C'est bien la soirée de la veille.
    
    start_str = start_time.isoformat() + "Z"
    end_str = end_time.isoformat() + "Z"
    
    print(f"⏳ Période analysée : {start_str} -> {end_str}")

    # --- 3. Récupération des clips ---
    print(f"🔍 Recherche des clips GTA V...")
    raw_clips = get_clips_for_game(headers, game_id, start_str, end_str, limit=100)
    
    # --- 4. Filtrage "Flashback" ---
    clips_pool = []
    print(f"🧹 Filtrage 'Flashback' parmi {len(raw_clips)} clips...")
    for clip in raw_clips:
        title = clip['title'].lower()
        # Mots-clés pour identifier Flashback (ajuster si besoin)
        if "flashback" in title:
            clips_pool.append(clip)
            
    print(f"✅ Clips retenus (Mention 'Flashback') : {len(clips_pool)}")


    clips_pool.sort(key=lambda x: x['view_count'], reverse=True)
    
    unique_clips = []
    seen = set()
    for c in clips_pool:
        if c['url'] not in seen:
            unique_clips.append(c)
            seen.add(c['url'])

    processed_clips = []
    total_duration = 0
    final_streamers_list = []
    thumbnails_candidates = []
    
    # --- NOUVEAU : DICTIONNAIRE POUR COMPTER LES CLIPS PAR STREAMER ---
    streamer_counts = {}

    for clip in unique_clips:
        if total_duration >= MIN_DURATION_SECONDS: break
        
        streamer_name = clip['broadcaster_name']
        
        # --- VÉRIFICATION DE LA LIMITE ---
        current_count = streamer_counts.get(streamer_name, 0)
        if current_count >= MAX_CLIPS_PER_STREAMER:
            continue # On saute ce clip car ce streamer en a déjà 3
        
        clip_id = clip['id']
        raw_path = os.path.join(TEMP_DIR, f"{clip_id}_raw.mp4")
        std_path = os.path.join(TRASH_DIR, f"{clip_id}_std.mp4")

        if download_clip(clip['url'], raw_path):
            duration = get_video_duration(raw_path)
            if duration < 5: 
                try: os.remove(raw_path)
                except: pass
                continue 
                
            frame_path = os.path.join(TEMP_DIR, f"{clip_id}.jpg")
            if extract_frame(raw_path, frame_path):
                thumbnails_candidates.append(frame_path)
            
            if standardize_video(raw_path, std_path, streamer_name):
                processed_clips.append(std_path)
                total_duration += duration
                final_streamers_list.append(streamer_name)
                
                # --- ON INCRÉMENTE LE COMPTEUR ---
                streamer_counts[streamer_name] = current_count + 1
                
                print(f"   ✅ Ajouté ({total_duration:.1f}s) : {streamer_name} (Clip #{streamer_counts[streamer_name]})")
                try: os.remove(raw_path)
                except: pass
            else:
                try: os.remove(raw_path)
                except: pass

    if not processed_clips:
        print("❌ Aucun clip valide.")
        return

    print("🎬 Assemblage final...")
    inputs_txt_path = os.path.join(OUTPUT_DIR, "inputs.txt")
    with open(inputs_txt_path, "w", encoding="utf-8") as f:
        for path in processed_clips:
            safe_path = path.replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    cmd_concat = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", inputs_txt_path, "-c", "copy", FINAL_VIDEO_PATH]
    subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    create_thumbnail(thumbnails_candidates, THUMBNAIL_PATH)
    metadata = generate_ollama_metadata(final_streamers_list)
    
    with open(os.path.join(OUTPUT_DIR, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)

    print("\n✅ TERMINÉ !")

if __name__ == "__main__":
    main()