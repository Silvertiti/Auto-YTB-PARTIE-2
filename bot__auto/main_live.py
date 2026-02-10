import os
import sys
import subprocess
import re
import cv2
import ftplib
import imageio_ffmpeg
import requests
import json
import time
from datetime import datetime, timedelta
from ultralytics import YOLO

from groq import Groq
import urllib3
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Désactivation des avertissements SSL (puisque nous allons utiliser verify=False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Groq Client Initialization
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ========= CONFIG =========
NB_VIDEOS = 1        # << Nombre de vidéos finales à générer
TARGET_SECONDS = 60  # << Durée MINIMALE par vidéo (pour mode fetch)
# SEARCH CONFIG
SEARCH_QUERY = "naroy"   # Nom du streamer
SEARCH_TYPE = "channel"       # 'channel' ou 'game'
SEARCH_PERIOD = "24h"          # '24h', '7d', '30d', 'all'
CLIP_LANGUAGE = "fr"          # 'fr', 'en', etc. ou "" pour tout

# LOGS CONFIG
LOGS_FILE = "creation_logs.json"

# FTP CONFIG
FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
REMOTE_DIR = "www"
BASE_URL = "https://silvertiti.fr"

# POSTING CONFIG (Late API / TikTok)
LATE_API_KEY = os.getenv("LATE_API_KEY")

# On définit une valeur par défaut, mais elle sera écrasée par l'interface web
TIKTOK_ACCOUNT_ID = os.getenv("TIKTOK_ACCOUNT_ID_HAWAII") 

# Paramètres TikTok
TIKTOK_SETTINGS = {
    'privacy_level': 'PUBLIC_TO_EVERYONE',
    'allow_comment': True,
    'allow_duet': True,
    'allow_stitch': True,
    'content_preview_confirmed': True,
    'express_consent_given': True
}
PUBLISH_NOW = True
SCHEDULE_HOUR = 12
SCHEDULE_MINUTE = 0
AUTO_POST = False
SEND_TELEGRAM = True

MAX_API_CLIPS = NB_VIDEOS * 250
# ==========================

client_id = os.getenv("TWITCH_CLIENT_ID")
client_secret = os.getenv("TWITCH_CLIENT_SECRET")

# -------- Utils --------

def get_access_token():
    """Token APP (client_credentials) - pour les requêtes classiques"""
    url = 'https://id.twitch.tv/oauth2/token'
    params = {'client_id': client_id, 'client_secret': client_secret, 'grant_type': 'client_credentials'}
    response = requests.post(url, params=params, verify=False)
    response.raise_for_status()
    return response.json()['access_token']

def get_user_id(access_token, username):
    headers = {'Client-ID': client_id, 'Authorization': f'Bearer {access_token}'}
    response = requests.get('https://api.twitch.tv/helix/users', headers=headers, params={'login': username}, verify=False)
    response.raise_for_status()
    data = response.json().get('data', [])
    return data[0]['id'] if data else None

def get_game_id(access_token, game_name):
    headers = {'Client-ID': client_id, 'Authorization': f'Bearer {access_token}'}
    response = requests.get('https://api.twitch.tv/helix/games', headers=headers, params={'name': game_name}, verify=False)
    response.raise_for_status()
    data = response.json().get('data', [])
    return data[0]['id'] if data else None

def get_clips(access_token, broadcaster_id=None, game_id=None, first=50, started_at=None):
    headers = {'Client-ID': client_id, 'Authorization': f'Bearer {access_token}'}
    params = {'first': first}
    if broadcaster_id:
        params['broadcaster_id'] = broadcaster_id
    if game_id:
        params['game_id'] = game_id
    if started_at:
        params['started_at'] = started_at
    
    response = requests.get('https://api.twitch.tv/helix/clips', headers=headers, params=params, verify=False)
    response.raise_for_status()
    return response.json().get('data', [])

def telecharger_clip(url, output_file):
    print(f"⏬ Téléchargement de {url}...")
    cmd = [sys.executable, "-m", "streamlink", "--twitch-disable-ads", url, "best", "-o", output_file]
    result = subprocess.run(cmd)
    return result.returncode == 0 and os.path.exists(output_file)

def extraire_image(video_file, output_image):
    ffmpeg_exe = get_ffmpeg_cmd()
    subprocess.run(
        [ffmpeg_exe, "-y", "-ss", "00:00:01", "-i", video_file, "-frames:v", "1", output_image],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return os.path.exists(output_image)

# Flou OpenCV
def blur_frame(image, ksize=35):
    k = ksize if ksize % 2 == 1 else ksize + 1
    if k < 3:
        k = 3
    return cv2.GaussianBlur(image, (k, k), 0)

# -------- LOGGING TIME --------

def save_creation_log(streamer, title, filename, duration_seconds):
    """Sauvegarde les stats de création dans un JSON"""
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "streamer": streamer,
        "video_title": title,
        "filename": filename,
        "processing_time_seconds": round(duration_seconds, 2),
        "processing_time_human": str(timedelta(seconds=round(duration_seconds)))
    }
    
    data = []
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            pass

    data.append(entry)
    
    try:
        with open(LOGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"📊 Stats sauvegardées : {duration_seconds:.2f}s pour générer cette vidéo.")
    except Exception as e:
        print(f"❌ Erreur sauvegarde logs : {e}")


# -------- Détection webcam --------

def detecter_webcam(image_path, model_path="best.pt"):
    model = YOLO(model_path)
    img = cv2.imread(image_path)
    results = model.predict(source=image_path, conf=0.25, save=False, show=False)
    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            marge = 20
            return (
                max(0, x1 - marge),
                max(0, y1 - marge),
                min(img.shape[1], x2 + marge) - max(0, x1 - marge),
                min(img.shape[0], y2 + marge) - max(0, y1 - marge)
            )
    return None

# -------- FFmpeg Utils --------

def get_ffmpeg_cmd():
    return imageio_ffmpeg.get_ffmpeg_exe()

def get_video_info(file_path):
    """Récupère durée, largeur, hauteur via FFmpeg (stderr)."""
    cmd = [get_ffmpeg_cmd(), "-i", file_path]
    result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    
    duration = 0.0
    width = 0
    height = 0
    
    for line in result.stderr.split('\n'):
        line = line.strip()
        if line.startswith("Duration:"):
            try:
                time_str = line.split(",")[0].split(" ")[1]
                h, m, s = time_str.split(":")
                duration = int(h) * 3600 + int(m) * 60 + float(s)
            except:
                pass
        
        if "Video:" in line:
            try:
                match = re.search(r'(\d{2,5})x(\d{2,5})', line)
                if match:
                    width = int(match.group(1))
                    height = int(match.group(2))
            except:
                pass
                
    return duration, width, height

# -------- Montage FFmpeg --------

def montage_tiktok(clips_paths, crop_params, output_path):
    print(f"🎞️ Montage final (FFmpeg - Safe Mode) : {output_path}")
    
    if not clips_paths:
        return

    ffmpeg = get_ffmpeg_cmd()
    
    _, src_w, src_h = get_video_info(clips_paths[0])
    if src_w == 0 or src_h == 0:
        src_w, src_h = 1920, 1080 # Fallback

    cmd_inputs = []
    for path in clips_paths:
        cmd_inputs.extend(["-i", path])

    concat_segments = ""
    for i in range(len(clips_paths)):
        concat_segments += f"[{i}:v][{i}:a]"
    
    filter_concat = f"{concat_segments}concat=n={len(clips_paths)}:v=1:a=1[joined_v][joined_a]"

    filter_processing = ""

    if crop_params:
        x, y, w, h = crop_params
        
        target_cam_w = 720
        target_cam_h = int(h * (target_cam_w / w))
        if target_cam_h % 2 != 0: target_cam_h += 1

        remaining_h = 1280 - target_cam_h
        
        reduction_factor = 0.24
        game_crop_w = min(src_w, int(720 * (1 + reduction_factor)))
        game_crop_x = (src_w - game_crop_w) // 2
        
        filter_processing = (
            f"[joined_v]split=2[cam][game];"
            f"[cam]crop={w}:{h}:{x}:{y},scale={target_cam_w}:{target_cam_h}[cam_ready];"
            f"[game]crop={game_crop_w}:{src_h}:{game_crop_x}:0,scale=720:{remaining_h}[game_ready];"
            f"[cam_ready][game_ready]vstack[outv]"
        )

    else:
        filter_processing = (
            f"[joined_v]split=2[bg][fg];"
            f"[bg]scale=-2:1280,crop=720:1280,boxblur=20:10[bg_blurred];"
            f"[fg]scale=720:-2[fg_scaled];"
            f"[bg_blurred][fg_scaled]overlay=(W-w)/2:(H-h)/2[outv]"
        )

    full_filter = f"{filter_concat};{filter_processing}"

    cmd = [ffmpeg]
    cmd.extend(cmd_inputs)
    cmd.extend([
        "-filter_complex", full_filter,
        "-map", "[outv]", 
        "-map", "[joined_a]", 
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-r", "60",
        "-y", output_path
    ])
    
    print("   ⚙️ Encodage en cours (Concat + Montage)...")
    
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ Exporté via FFmpeg : {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur FFmpeg : {e}")


# -------- Gestion des doublons --------

def charger_clips_deja_telecharges(fichier_txt):
    if not os.path.exists(fichier_txt):
        return set()
    with open(fichier_txt, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def ajouter_clip_telecharge(fichier_txt, clip_id, clip_title):
    with open(fichier_txt, "a", encoding="utf-8") as f:
        f.write(f"{clip_id}\n")
    print(f"📝 Clip noté comme téléchargé : {clip_id}")


# -------- FTP --------

def upload_to_ftp(local_path, remote_name):
    if not os.path.exists(local_path):
        print(f"❌ Erreur : Le fichier local '{local_path}' n'existe pas.")
        return False

    try:
        print(f"🚀 Connexion FTP vers {FTP_HOST}...")
        with ftplib.FTP(FTP_HOST, FTP_USER, FTP_PASS) as ftp:
            ftp.cwd(REMOTE_DIR)
            print(f"📂 Dossier FTP : {ftp.pwd()}")

            print(f"📤 Envoi de '{local_path}' vers '{remote_name}'...")
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_name}", f)
            
            print("✅ Upload FTP terminé avec succès !")
            return True

    except Exception as e:
        print(f"❌ Erreur Upload FTP : {e}")
        return False

def delete_file_from_ftp(remote_name):
    try:
        print(f"🗑️ Suppression FTP de '{remote_name}'...")
        with ftplib.FTP(FTP_HOST, FTP_USER, FTP_PASS) as ftp:
            ftp.cwd(REMOTE_DIR)
            ftp.delete(remote_name)
        print("✅ Fichier supprimé du FTP avec succès !")
        return True
    except Exception as e:
        print(f"❌ Erreur suppression FTP : {e}")
        return False

# -------- Groq Metadata Generation --------

def generate_metadata(streamer_name, titre_clip_twitch):
    print(f"🧠 Génération des métadonnées avec Groq pour : {titre_clip_twitch}...")
    
    system_instruction = """
Tu es un expert en viralité pour TikTok et YouTube Shorts.
Ton but est de générer les métadonnées pour un clip vidéo.

INSTRUCTIONS:
1. Analyse le NOM DU STREAMER et le TITRE DU CLIP fournis.
2. Génère un TITRE CLICKBAIT (Court, mots-clés en MAJUSCULES, 2-3 emojis).
3. Génère une liste de HASHTAGS. Tu dois mélanger des hashtags génériques (comme #TwitchFR #BestOfTwitch) ET des hashtags précis liés au sujet du clip (ex: le nom du jeu, le thème "CultureG", "Minecraft", etc.).

FORMAT DE RÉPONSE STRICT (2 lignes maximum, pas de guillemets, pas de préfixe "Titre:"):
[LIGNE 1 : TON TITRE ICI]
[LIGNE 2 : TES HASHTAGS ICI]
"""
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": system_instruction
                },
                {
                    "role": "user",
                    "content": f"Streamer: {streamer_name}\nTitre du clip: {titre_clip_twitch}"
                }
            ],
            temperature=0.7,
            max_tokens=200,
            top_p=1,
            stream=False,
            stop=None
        )
        
        response_text = completion.choices[0].message.content.strip()
        lines = response_text.split('\n')
        
        titre = lines[0].strip() if len(lines) > 0 else "TITRE VIRAL GENERE"
        hashtags = lines[1].strip() if len(lines) > 1 else "#Viral #Twitch"
        
        final_caption = f"{titre}\n{hashtags}"
        print(f"✨ Métadonnées générées :\n{final_caption}")
        return final_caption

    except Exception as e:
        print(f"❌ Erreur Groq : {e}")
        return f"Clip de {streamer_name} ! 🎬 #TwitchFR #BestOf #Viral"

# -------- API Late --------

def publish_to_late_api(video_filename, caption_content):
    print("🚀 Préparation de la publication sur Late...")
    
    video_url = f"{BASE_URL}/{video_filename}"
    
    url = 'https://getlate.dev/api/v1/posts'
    headers = {
        'Authorization': f'Bearer {LATE_API_KEY}',
        'Content-Type': 'application/json'
    }

    data = {
        'content': caption_content,
        'mediaItems': [
            {
                'url': video_url, 
                'type': 'video' 
            }
        ],
        'platforms': [{'platform': 'tiktok', 'accountId': TIKTOK_ACCOUNT_ID}],
        'tiktokSettings': TIKTOK_SETTINGS,
        'publishNow': PUBLISH_NOW
    }

    if not PUBLISH_NOW:
        now = datetime.now()
        scheduled_date = now.replace(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE, second=0, microsecond=0)
        
        if scheduled_date < now:
             scheduled_date += timedelta(days=1)

        scheduled_iso = scheduled_date.astimezone().isoformat()
        print(f"📅 Programmation du post pour : {scheduled_iso}")
        data['scheduledFor'] = scheduled_iso
    else:
        print("⚡ Publication IMMÉDIATE demandée (PUBLISH_NOW = True)")

    try:
        response = requests.post(url, headers=headers, json=data, verify=False)
        
        print(f"📡 Status Code API Late : {response.status_code}")
        print(f"📄 Réponse brute : {response.text}")

        try:
            res_data = response.json()
        except ValueError:
            print("❌ Impossible de lire le JSON (réponse vide ou HTML).")
            return False
        
        if response.ok:
            print(f"✅ Posté avec succès sur Late ! ID: {res_data.get('_id', res_data.get('id', 'Inconnu'))}")
            return True
        else:
            print("❌ L'API Late a renvoyé une erreur :", res_data)
            return False
            
    except Exception as e:
        print("❌ Erreur lors de l'appel API Late :", e)
        return False

# -------- Telegram --------

def send_telegram_video(video_path, caption):
    print("📧 Préparation envoi Telegram...")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    print(f"   🔑 Token présent : {'Oui' if token else 'NON ❌'}")
    print(f"   💬 Chat ID présent : {'Oui' if chat_id else 'NON ❌'}")

    if not token or not chat_id:
        print("❌ Config Telegram manquante (TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID).")
        return

    if not os.path.exists(video_path):
        print(f"❌ Le fichier vidéo n'existe pas : {video_path}")
        return
    
    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    print(f"   📁 Fichier : {video_path}")
    print(f"   📏 Taille : {file_size_mb:.1f} MB")
    
    if file_size_mb > 50:
        print(f"⚠️ ATTENTION : Le fichier fait {file_size_mb:.1f} MB, la limite Telegram Bot est de 50 MB !")
        print("   L'envoi va probablement échouer.")

    url = f"https://api.telegram.org/bot{token}/sendVideo"
    
    try:
        print("   📤 Envoi en cours vers Telegram (peut prendre du temps)...")
        with open(video_path, 'rb') as f:
            files = {'video': f}
            data = {
                'chat_id': chat_id, 
                'caption': caption,
                'parse_mode': 'Markdown'
            }
            response = requests.post(url, files=files, data=data, timeout=120)
            
        if response.ok:
            print("✅ Vidéo envoyée sur Telegram avec succès !")
        else:
            print(f"❌ Erreur Telegram (HTTP {response.status_code}) : {response.text}")
    except requests.exceptions.Timeout:
        print(f"❌ Timeout lors de l'envoi Telegram (fichier trop gros ? {file_size_mb:.1f} MB)")
    except Exception as e:
        print(f"❌ Exception lors de l'envoi Telegram : {e}")


# ================================================================
# ========== NOUVEAU : OAuth Token Management ====================
# ================================================================

def get_user_token():
    """Récupère le token utilisateur Twitch depuis les variables d'env"""
    token = os.getenv("TWITCH_USER_TOKEN")
    if not token:
        print("❌ TWITCH_USER_TOKEN manquant dans .env !")
        print("   👉 Lance 'python setup_twitch_token.py' pour l'obtenir.")
        return None
    return token

def refresh_user_token():
    """Rafraîchit le token utilisateur via l'API Twitch"""
    refresh_token = os.getenv("TWITCH_REFRESH_TOKEN")
    if not refresh_token:
        print("❌ TWITCH_REFRESH_TOKEN manquant ! Relance setup_twitch_token.py")
        return None
    
    print("🔄 Rafraîchissement du token Twitch...")
    
    url = 'https://id.twitch.tv/oauth2/token'
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret
    }
    
    try:
        response = requests.post(url, data=data, verify=False)
        
        if response.ok:
            tokens = response.json()
            new_access = tokens['access_token']
            new_refresh = tokens.get('refresh_token', refresh_token)
            
            # Mettre à jour le .env
            update_env_file("TWITCH_USER_TOKEN", new_access)
            update_env_file("TWITCH_REFRESH_TOKEN", new_refresh)
            
            # Mettre à jour dans le process actuel
            os.environ["TWITCH_USER_TOKEN"] = new_access
            os.environ["TWITCH_REFRESH_TOKEN"] = new_refresh
            
            print("✅ Token Twitch rafraîchi avec succès !")
            return new_access
        else:
            print(f"❌ Erreur refresh token : {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ Exception refresh token : {e}")
        return None

def update_env_file(key, value):
    """Met à jour une clé spécifique dans le fichier .env"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()
    
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    
    if not found:
        lines.append(f"{key}={value}\n")
    
    with open(env_path, 'w') as f:
        f.writelines(lines)


# ================================================================
# ========== NOUVEAU : Live Stream & Clip Creation ===============
# ================================================================

def check_is_live(access_token, username):
    """Vérifie si un streamer Twitch est actuellement en live"""
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(
        'https://api.twitch.tv/helix/streams',
        headers=headers,
        params={'user_login': username},
        verify=False
    )
    response.raise_for_status()
    data = response.json().get('data', [])
    
    if data:
        stream = data[0]
        print(f"🔴 {username} est EN LIVE !")
        print(f"   📺 Titre : {stream.get('title', 'N/A')}")
        print(f"   🎮 Jeu : {stream.get('game_name', 'N/A')}")
        print(f"   👁️ Viewers : {stream.get('viewer_count', 0)}")
        return True, stream
    else:
        print(f"⚪ {username} n'est PAS en live.")
        return False, None


def create_twitch_clip(user_token, broadcaster_id, has_delay=False):
    """
    Crée un clip sur un stream Twitch en live.
    has_delay=False → clip capturé immédiatement
    has_delay=True  → léger délai pour compenser le lag réseau
    Retourne (clip_id, edit_url) ou (None, None)
    """
    print("✂️ Création du clip Twitch en cours...")
    
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {user_token}'
    }
    params = {
        'broadcaster_id': broadcaster_id,
        'has_delay': str(has_delay).lower()
    }
    
    response = requests.post(
        'https://api.twitch.tv/helix/clips',
        headers=headers,
        params=params,
        verify=False
    )
    
    # Si token expiré (401), on tente un refresh
    if response.status_code == 401:
        print("🔄 Token expiré, tentative de refresh automatique...")
        new_token = refresh_user_token()
        if new_token:
            headers['Authorization'] = f'Bearer {new_token}'
            response = requests.post(
                'https://api.twitch.tv/helix/clips',
                headers=headers,
                params=params,
                verify=False
            )
        else:
            print("❌ Impossible de rafraîchir le token.")
            return None, None
    
    if response.ok:
        data = response.json().get('data', [])
        if data:
            clip_id = data[0]['id']
            edit_url = data[0]['edit_url']
            print(f"✅ Clip créé avec succès !")
            print(f"   🆔 ID : {clip_id}")
            print(f"   ✏️ Edit URL : {edit_url}")
            return clip_id, edit_url
    
    # Gestion des erreurs spécifiques
    if response.status_code == 403:
        print(f"❌ ERREUR 403 : Ce streamer a DÉSACTIVÉ la création de clips sur sa chaîne.")
        print(f"   💡 Essaie avec un autre streamer qui autorise les clips.")
    elif response.status_code == 404:
        print(f"❌ ERREUR 404 : Le stream n'a pas été trouvé (peut-être hors ligne).")
    else:
        print(f"❌ Erreur création clip : {response.status_code} - {response.text}")
    return None, None


def wait_for_clip_ready(access_token, clip_id, max_wait=120):
    """
    Attend que le clip Twitch soit traité et disponible (polling toutes les 5s).
    Retourne les données du clip (dict) ou None si timeout.
    """
    print(f"⏳ Attente du traitement du clip... (max {max_wait}s)")
    
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    
    start = time.time()
    attempt = 0
    
    while time.time() - start < max_wait:
        attempt += 1
        time.sleep(5)
        
        try:
            response = requests.get(
                'https://api.twitch.tv/helix/clips',
                headers=headers,
                params={'id': clip_id},
                verify=False
            )
            
            if response.ok:
                data = response.json().get('data', [])
                if data:
                    clip = data[0]
                    thumbnail = clip.get('thumbnail_url', '')
                    if thumbnail:
                        elapsed = time.time() - start
                        print(f"✅ Clip prêt en {elapsed:.0f}s !")
                        print(f"   🏷️ Titre : {clip.get('title', 'N/A')}")
                        print(f"   ⏱️ Durée : {clip.get('duration', 0):.1f}s")
                        print(f"   🔗 URL : {clip.get('url', 'N/A')}")
                        return clip
            
            print(f"   ⏳ Tentative {attempt}... (clip en cours de traitement)")
        except Exception as e:
            print(f"   ⚠️ Erreur polling : {e}")
    
    print(f"❌ Timeout : le clip n'est pas disponible après {max_wait}s")
    return None


def get_clip_video_url(thumbnail_url):
    """
    Dérive l'URL de téléchargement direct depuis le thumbnail du clip.
    Thumbnail : https://clips-media-assets2.twitch.tv/xxx-preview-480x272.jpg
    Vidéo     : https://clips-media-assets2.twitch.tv/xxx.mp4
    """
    if not thumbnail_url:
        return None
    video_url = re.sub(r'-preview-\d+x\d+\.jpg$', '.mp4', thumbnail_url)
    return video_url


# ================================================================
# ========== MAIN - Mode Clip Live ===============================
# ================================================================

def main():
    """
    Flux principal : Crée un clip sur le stream live du streamer,
    puis fait le montage TikTok, génère les métadonnées, et envoie.
    """
    output_folder = "clips_downloaded"
    os.makedirs(output_folder, exist_ok=True)
    
    start_time = time.time()
    
    print("\n" + "=" * 55)
    print("  🎬 MODE CLIP LIVE - Création automatique de clip")
    print("=" * 55)
    
    # ---- 1. Obtenir les tokens ----
    app_token = get_access_token()
    user_token = get_user_token()
    
    if not user_token:
        print("\n❌ Impossible de continuer sans TWITCH_USER_TOKEN.")
        print("   Lance : python setup_twitch_token.py")
        return
    
    # ---- 2. Trouver le streamer ----
    print(f"\n🔍 Recherche du streamer : {SEARCH_QUERY}")
    broadcaster_id = get_user_id(app_token, SEARCH_QUERY)
    if not broadcaster_id:
        print(f"❌ Streamer '{SEARCH_QUERY}' non trouvé sur Twitch.")
        return
    print(f"   ✅ Broadcaster ID : {broadcaster_id}")
    
    # ---- 3. Vérifier qu'il est en live ----
    is_live, stream_info = check_is_live(app_token, SEARCH_QUERY)
    if not is_live:
        print(f"\n❌ {SEARCH_QUERY} n'est pas en live ! Impossible de créer un clip.")
        print("   Le streamer doit être en live pour cette fonctionnalité.")
        return
    
    stream_title = stream_info.get('title', 'Live Stream') if stream_info else 'Live Stream'
    game_name = stream_info.get('game_name', 'Inconnu') if stream_info else 'Inconnu'
    
    # ---- 4. Créer le clip ----
    clip_id, edit_url = create_twitch_clip(user_token, broadcaster_id, has_delay=False)
    if not clip_id:
        print("\n❌ La création du clip a échoué. Abandon.")
        return
    
    # ---- 5. Attendre que le clip soit traité ----
    clip_data = wait_for_clip_ready(app_token, clip_id, max_wait=120)
    if not clip_data:
        print("\n❌ Le clip n'a pas pu être traité à temps. Abandon.")
        return
    
    clip_url = clip_data.get('url', '')
    clip_title = clip_data.get('title', stream_title)
    clip_duration = clip_data.get('duration', 30)
    
    print(f"\n📎 Clip : \"{clip_title}\" ({clip_duration:.0f}s)")
    
    # ---- 6. Télécharger le clip ----
    file_path = os.path.join(output_folder, f"{clip_id}.mp4")
    
    # On utilise d'abord streamlink (méthode la plus fiable pour les clips Twitch)
    download_ok = False
    
    print(f"⏬ Téléchargement du clip avec streamlink...")
    download_ok = telecharger_clip(clip_url, file_path)
    
    # Vérifier que le fichier n'est pas vide/corrompu (min 500 KB pour une vidéo de 30s)
    if download_ok and os.path.exists(file_path):
        file_size = os.path.getsize(file_path)
        if file_size < 500_000:  # Moins de 500 KB = suspect
            print(f"⚠️ Fichier trop petit ({file_size} octets), probablement corrompu.")
            download_ok = False
            try: os.remove(file_path)
            except: pass
        else:
            size_mb = file_size / (1024 * 1024)
            print(f"✅ Clip téléchargé ({size_mb:.1f} MB)")
    
    # Fallback : téléchargement direct depuis l'URL dérivée du thumbnail
    if not download_ok:
        thumbnail_url = clip_data.get('thumbnail_url', '')
        video_url = get_clip_video_url(thumbnail_url)
        
        if video_url:
            print(f"🔄 Fallback : téléchargement direct...")
            print(f"   URL : {video_url}")
            try:
                resp = requests.get(video_url, stream=True, verify=False, timeout=60)
                if resp.ok:
                    with open(file_path, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                    if file_size > 500_000:
                        download_ok = True
                        size_mb = file_size / (1024 * 1024)
                        print(f"✅ Clip téléchargé via direct ({size_mb:.1f} MB)")
                    else:
                        print(f"⚠️ Fichier direct trop petit ({file_size} octets)")
                        try: os.remove(file_path)
                        except: pass
            except Exception as e:
                print(f"⚠️ Échec téléchargement direct : {e}")
    
    if not download_ok or not os.path.exists(file_path):
        print("❌ Impossible de télécharger le clip. Abandon.")
        return
    
    # ---- 7. Montage TikTok ----
    print(f"\n{'=' * 55}")
    print("  🎞️ MONTAGE TIKTOK")
    print(f"{'=' * 55}")
    
    temp_frame = os.path.join(output_folder, f"{clip_id}_frame.jpg")
    if not extraire_image(file_path, temp_frame):
        print("❌ Erreur extraction image pour détection webcam.")
        return
    
    crop_params = detecter_webcam(temp_frame)
    if crop_params:
        print(f"   📷 Webcam détectée : x={crop_params[0]}, y={crop_params[1]}, w={crop_params[2]}, h={crop_params[3]}")
    else:
        print("   📷 Pas de webcam détectée → mode fond flou")
    
    output_final = os.path.join(output_folder, f"tiktok_live_{clip_id}.mp4")
    montage_tiktok([file_path], crop_params, output_final)
    
    if not os.path.exists(output_final):
        print("❌ Le montage a échoué.")
        return
    
    final_size_mb = os.path.getsize(output_final) / (1024 * 1024)
    print(f"✅ Vidéo montée ({final_size_mb:.1f} MB)")
    
    # ---- 8. Génération des métadonnées ----
    generated_caption = generate_metadata(SEARCH_QUERY, clip_title)
    
    # ---- 9. Envoi Telegram ----
    print(f"\n📧 SEND_TELEGRAM = {SEND_TELEGRAM}")
    if SEND_TELEGRAM:
        print(f"📧 Lancement envoi Telegram pour : {output_final}")
        send_telegram_video(output_final, generated_caption)
    else:
        print("📧 Envoi Telegram désactivé (SEND_TELEGRAM = False)")
    
    # ---- 10. Auto-post TikTok ----
    if AUTO_POST:
        remote_filename = os.path.basename(output_final)
        if upload_to_ftp(output_final, remote_filename):
            if publish_to_late_api(remote_filename, generated_caption):
                delete_file_from_ftp(remote_filename)
    else:
        print(f"\n💾 Vidéo sauvegardée localement : {output_final}")
        print("🚫 Auto-post désactivé (AUTO_POST = False)")
        print(f"📝 Métadonnées générées :\n{generated_caption}")
    
    # ---- 11. Nettoyage ----
    print(f"\n🧹 Nettoyage des fichiers temporaires...")
    for f_path in [file_path, temp_frame]:
        if os.path.exists(f_path):
            try:
                os.remove(f_path)
                print(f"   🗑️ Supprimé : {os.path.basename(f_path)}")
            except Exception as e:
                print(f"   ❌ Erreur suppression : {e}")
    
    # ---- Timer & Logs ----
    end_time = time.time()
    duration = end_time - start_time
    save_creation_log(SEARCH_QUERY, clip_title, os.path.basename(output_final), duration)
    
    print(f"\n{'=' * 55}")
    print(f"  🎉 TERMINÉ en {duration:.0f}s !")
    print(f"  📎 Clip Twitch : {clip_url}")
    print(f"  🎬 Vidéo TikTok : {output_final}")
    print(f"{'=' * 55}\n")


# ================================================================
# ========== Pipeline pour l'interface Web (Flask) ===============
# ================================================================

def executer_pipeline(config_user):
    """
    Point d'entrée pour l'interface Web (Flask) / app.py.
    Met à jour les variables globales puis lance main().
    """
    global SEARCH_QUERY, SEARCH_TYPE, SEARCH_PERIOD, NB_VIDEOS, CLIP_LANGUAGE
    global AUTO_POST, TARGET_SECONDS, SEND_TELEGRAM
    global PUBLISH_NOW, SCHEDULE_HOUR, SCHEDULE_MINUTE, TIKTOK_ACCOUNT_ID

    # Config de base
    if 'query' in config_user: SEARCH_QUERY = config_user['query']
    if 'type' in config_user: SEARCH_TYPE = config_user['type']
    if 'period' in config_user: SEARCH_PERIOD = config_user['period']
    if 'nb_videos' in config_user: NB_VIDEOS = int(config_user['nb_videos'])
    if 'lang' in config_user: CLIP_LANGUAGE = config_user['lang']
    if 'target_seconds' in config_user: TARGET_SECONDS = int(config_user['target_seconds'])
    
    # Options avancées
    if 'auto_post' in config_user: 
        AUTO_POST = bool(config_user['auto_post'])
    
    if 'send_telegram' in config_user:
        SEND_TELEGRAM = bool(config_user['send_telegram'])
        
    if 'publish_now' in config_user:
        PUBLISH_NOW = bool(config_user['publish_now'])
        
    if 'schedule_hour' in config_user:
        SCHEDULE_HOUR = int(config_user['schedule_hour'])
        
    if 'schedule_minute' in config_user:
        SCHEDULE_MINUTE = int(config_user['schedule_minute'])

    # Sélection dynamique du compte TikTok
    selected_key = config_user.get('tiktok_account_key')
    if selected_key:
        env_var_name = f"TIKTOK_ACCOUNT_ID_{selected_key}"
        found_id = os.getenv(env_var_name)
        if found_id:
            TIKTOK_ACCOUNT_ID = found_id
            print(f"👤 Compte TikTok sélectionné : {selected_key} (ID: {found_id})")
        else:
            print(f"⚠️ Variable {env_var_name} non trouvée. Utilisation du défaut.")

    # Log de démarrage
    print(f"🔄 PIPELINE CLIP LIVE : {SEARCH_QUERY} | AutoPost: {AUTO_POST} | Telegram: {SEND_TELEGRAM}")

    # Lancement
    main()

if __name__ == "__main__":
    main()