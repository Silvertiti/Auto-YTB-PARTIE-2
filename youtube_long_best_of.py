# -*- coding: utf-8 -*-
"""
youtube_long_best_of.py
========================
Pipeline complet de génération et publication de best-of longs (16:9) sur YouTube.
"""

import os
import sys
import json
import time
import shutil
import math
import asyncio
import subprocess
import requests
import urllib3
import ftplib
import glob
from datetime import datetime, timedelta
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from ultralytics import YOLO

# Désactiver les avertissements SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Charger les variables d'environnement
load_dotenv()

# Fix Unicode sur console Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# ==================== CONFIGURATION ====================
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
LATE_API_KEY = os.getenv("LATE_API_KEY")

# On cherche les infos de compte YouTube dans Late
YOUTUBE_ACCOUNT_ID = os.getenv("YOUTUBE_ID_YBT_1") # Compte YouTube principal Late par défaut

OUTPUT_DIR = "youtube_crashes_output"
TEMP_DIR = os.path.join(OUTPUT_DIR, "temp_clips")
TRASH_DIR = os.path.join(OUTPUT_DIR, "processed_chunks")
FINAL_VIDEO_PATH = os.path.join(OUTPUT_DIR, "best_of_twitch_24h.mp4")
THUMBNAIL_PATH = os.path.join(OUTPUT_DIR, "thumbnail.jpg")
LOGO_PATH = "logo2.png"
FONT_PATH = "Nunito-Black.ttf"
STREAMERS_FILE = "streamers.txt"

MIN_DURATION_SECONDS = 600  # 10 minutes minimum
MAX_CLIPS_PER_STREAMER = 3
TARGET_HEIGHT = 1080
TARGET_WIDTH = 1920

# Configuration Anti-Détection
AD_SPEEDUP = 1.0
AD_ZOOM = False
AD_COLOR = False
AD_ROTATE = False
AD_VIGNETTE = False
AD_TRIM_SEC = 0.0

# Options d'affichage de texte sur la vidéo / miniature
DRAW_STREAMER_NAME = True      # Réactive l'incrustation du nom du streamer en haut à gauche
DRAW_SUBSCRIBE_OVERLAY = False   # Désactive l'incrustation du bouton d'abonnement / like
DRAW_THUMBNAIL_TEXT = False      # Désactive l'écriture du texte "CHOQUANT ! 😱" sur la miniature



# Musique Lo-Fi
LOFI_URL = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3"  # Musique de secours libre de droits
LOFI_PATH = "lofi_background.mp3"

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# ========================================================

# Création des dossiers
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(TRASH_DIR, exist_ok=True)

def pick_and_increment_youtube_account():
    # On charge l'historique d'usage
    usage_file = "tiktok_usage.json"
    usage = {}
    if os.path.exists(usage_file):
        try:
            with open(usage_file, "r", encoding="utf-8") as f:
                usage = json.load(f)
        except: pass
        
    for i in range(1, 9): # YBT_1 à YBT_8
        acc_name = f"YBT_{i}"
        late_key = os.getenv(f"LATE_KEY_YBT_{i}")
        youtube_id = os.getenv(f"YOUTUBE_ID_YBT_{i}")
        
        if not late_key or not youtube_id:
            continue
            
        count = usage.get(acc_name, {}).get("count", 0)
        if count < 20:
            usage.setdefault(acc_name, {})
            usage[acc_name]["count"] = count + 1
            if "last_reset" not in usage[acc_name]:
                usage[acc_name]["last_reset"] = datetime.now().date().isoformat()
            try:
                with open(usage_file, "w", encoding="utf-8") as f:
                    json.dump(usage, f, indent=4, ensure_ascii=False)
            except: pass
            print(f"📊 Rotation YouTube : Compte '{acc_name}' selectionne ({count+1}/20 posts)")
            return late_key, youtube_id
            
    print("⚠️ Attention : Tous les comptes YouTube Zernio ont atteint leur limite de 20 posts. Fallback sur YBT_1.")
    return os.getenv("LATE_KEY_YBT_1"), os.getenv("YOUTUBE_ID_YBT_1")

# -------- Dépendance Shazam (Anti-Copyright) --------
try:
    from shazamio import Shazam
    SHAZAM_AVAILABLE = True
except ImportError:
    SHAZAM_AVAILABLE = False
    print("⚠️ shazamio non installé. Exclure la détection de musique.")

async def check_copyright_music_async(file_path):
    if not SHAZAM_AVAILABLE:
        return False, None, None
    shazam = Shazam()
    try:
        # Scan 1 : Début du fichier
        out = await shazam.recognize(file_path)
        if 'track' in out:
            title = out['track'].get('title', 'Unknown')
            artist = out['track'].get('subtitle', 'Unknown')
            return True, title, artist
            
        # Scan 2 : Échantillon au milieu de la vidéo (évite la musique de fond masquée)
        temp_sample = file_path + "_sample.mp3"
        cmd = ["ffmpeg", "-y", "-ss", "00:00:15", "-t", "10", "-i", file_path, "-vn", "-acodec", "mp3", temp_sample]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(temp_sample):
            try:
                out_mid = await shazam.recognize(temp_sample)
                os.remove(temp_sample)
                if 'track' in out_mid:
                    title = out_mid['track'].get('title', 'Unknown')
                    artist = out_mid['track'].get('subtitle', 'Unknown')
                    return True, title, artist
            except Exception:
                if os.path.exists(temp_sample):
                    try: os.remove(temp_sample)
                    except: pass

        return False, None, None
    except Exception as e:
        print(f"   ⚠️ Erreur Shazam : {e}")
        return False, None, None

def check_copyright_music(file_path):
    if not SHAZAM_AVAILABLE:
        return False, None, None
    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        return loop.run_until_complete(check_copyright_music_async(file_path))
    except Exception as e:
        print(f"   ⚠️ Erreur d'exécution Shazam : {e}")
        return False, None, None


# -------- Utils Twitch --------

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

def get_user_id(headers, username):
    url = 'https://api.twitch.tv/helix/users'
    params = {'login': username}
    response = requests.get(url, headers=headers, params=params, verify=False)
    if response.status_code == 200:
        data = response.json().get('data', [])
        if data:
            return data[0]['id']
    return None

def get_clips_for_broadcaster(headers, broadcaster_id, started_at, first=30):
    url = 'https://api.twitch.tv/helix/clips'
    params = {
        'broadcaster_id': broadcaster_id,
        'first': first,
        'started_at': started_at
    }
    response = requests.get(url, headers=headers, params=params, verify=False)
    if response.status_code == 200:
        return response.json().get('data', [])
    return []

def download_clip(url, output_path):
    print(f"📥 Téléchargement Twitch : {url}")
    # Utiliser streamlink
    cmd = [sys.executable, "-m", "streamlink", url, "best", "-o", output_path]
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 100000:
            return True
    except Exception as e:
        print(f"   ⚠️ Échec Streamlink : {e}")
        
    # Fallback yt-dlp
    cmd_yt = [sys.executable, "-m", "yt_dlp", url, "-o", output_path]
    try:
        result_yt = subprocess.run(cmd_yt, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result_yt.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 100000:
            return True
    except Exception as e:
        print(f"   ⚠️ Échec yt-dlp : {e}")
        
    return False

def get_video_duration(file_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except:
        return 0.0

def get_video_dimensions(file_path):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0", 
        "-show_entries", "stream=width,height", 
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines = result.stdout.strip().split('\n')
        if len(lines) >= 2:
            return int(lines[0]), int(lines[1])
    except:
        pass
    return 1920, 1080

def detect_webcam(image_path, model_path="best.pt"):
    if not os.path.exists(model_path):
        return None
    try:
        model = YOLO(model_path)
        img = cv2 = None
        # On va tenter d'importer cv2 dynamiquement
        import cv2
        img = cv2.imread(image_path)
        if img is None: return None
        results = model.predict(source=image_path, conf=0.25, save=False, show=False)
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                marge = 15
                return (
                    max(0, x1 - marge),
                    max(0, y1 - marge),
                    min(img.shape[1], x2 + marge) - max(0, x1 - marge),
                    min(img.shape[0], y2 + marge) - max(0, y1 - marge)
                )
    except Exception as e:
        print(f"   ⚠️ Détection webcam échouée : {e}")
    return None

def extract_frame(video_path, image_path):
    cmd = ["ffmpeg", "-y", "-ss", "00:00:02", "-i", video_path, "-vframes", "1", "-q:v", "2", image_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.exists(image_path)


# -------- Étape 3 : Suppression des Silences (Jump-Cut) --------

def remove_silence(input_path, output_path):
    print(f"✂️ Détection et suppression des silences (Jump-Cut)...")
    cmd = [
        "ffmpeg", "-i", input_path,
        "-af", "silencedetect=noise=-30dB:d=1.2",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
    
    silences = []
    current_start = None
    
    for line in result.stderr.split('\n'):
        if "silence_start:" in line:
            try:
                current_start = float(line.split("silence_start:")[1].strip().split()[0])
            except:
                pass
        elif "silence_end:" in line:
            try:
                end = float(line.split("silence_end:")[1].strip().split()[0])
                if current_start is not None:
                    silences.append((current_start, end))
                    current_start = None
            except:
                pass
                
    if not silences:
        shutil.copy(input_path, output_path)
        return True
        
    dur = get_video_duration(input_path)
    if dur <= 0:
        return False
        
    # Calcul des segments actifs
    active_segments = []
    last_end = 0.0
    for start, end in silences:
        if start - last_end > 0.2:
            active_segments.append((last_end, start))
        last_end = end
    if dur - last_end > 0.2:
        active_segments.append((last_end, dur))
        
    if not active_segments:
        shutil.copy(input_path, output_path)
        return True
        
    if len(active_segments) == 1 and active_segments[0][0] <= 0.1 and active_segments[0][1] >= dur - 0.1:
        shutil.copy(input_path, output_path)
        return True
        
    # Construire la commande de coupe/concaténation
    filter_parts = []
    concat_v = ""
    concat_a = ""
    for idx, (start, end) in enumerate(active_segments):
        filter_parts.append(f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{idx}]")
        filter_parts.append(f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{idx}]")
        concat_v += f"[v{idx}]"
        concat_a += f"[a{idx}]"
        
    filter_parts.append(f"{concat_v}concat=n={len(active_segments)}:v=1:a=0[outv]")
    filter_parts.append(f"{concat_a}concat=n={len(active_segments)}:v=0:a=1[outa]")
    
    filter_complex = ";".join(filter_parts)
    
    cmd_cut = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ]
    res = subprocess.run(cmd_cut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0 and os.path.exists(output_path)


# -------- Étape 4 : Standardisation & Effets 16:9 (Ken Burns / normalisation) --------

def standardize_video(input_path, output_path, streamer_name):
    dur = get_video_duration(input_path)
    if dur <= 0: return False
    
    src_w, src_h = get_video_dimensions(input_path)
    abs_font_path = os.path.abspath(FONT_PATH).replace("\\", "/").replace(":", "\\:")
    safe_name = streamer_name.replace(":", "").replace("'", "")
    
    # 1. Vérification webcam (YOLO)
    temp_frame = input_path.replace(".mp4", "_frame.jpg")
    crop_params = None
    if extract_frame(input_path, temp_frame):
        crop_params = detect_webcam(temp_frame)
        try: os.remove(temp_frame)
        except: pass

    # 2. Construction de la commande FFmpeg
    # On applique les filtres en 1 seule passe d'encodage
    vf_parts = [
        # Normalisation aspect ratio
        "scale=1920:1080:force_original_aspect_ratio=decrease",
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "setsar=1"
    ]
    
    # Effet Ken Burns (Zoom)
    if crop_params:
        # Zoom sur la webcam
        cx, cy, cw, ch = crop_params
        # Définir l'overlay dynamique
        zoom_expr = f"scale='{cw}*(1+0.08*t/{dur})':'{ch}*(1+0.08*t/{dur})':eval=frame"
        overlay_x = f"{cx}-({cw}*(1+0.08*t/{dur})-{cw})/2"
        overlay_y = f"{cy}-({ch}*(1+0.08*t/{dur})-{ch})/2"
        
        # Filtre complexe pour séparer, zoomer et ré-incruster
        filter_complex = (
            f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,split=2[base][cam];"
            f"[cam]crop={cw}:{ch}:{cx}:{cy},{zoom_expr}[cam_zoomed];"
            f"[base][cam_zoomed]overlay={overlay_x}:{overlay_y}[pre_text]"
        )
        vf_input_label = "[pre_text]"
    else:
        # Pas de webcam : zoom léger sur la vidéo entière (3%)
        filter_complex = (
            f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,"
            f"scale='1920*(1+0.03*t/{dur})':'1080*(1+0.03*t/{dur})':eval=frame,crop=1920:1080:(iw-1920)/2:(ih-1080)/2[pre_text]"
        )
        vf_input_label = "[pre_text]"
        
    # Construction de la chaîne de filtres vidéo appliquée après l'incrustation / le zoom
    v_filters = []
    if DRAW_STREAMER_NAME:
        v_filters.append(
            f"drawtext=fontfile='{abs_font_path}':text='{safe_name}':"
            f"fontcolor=white:fontsize=48:x=60:y=60:"
            f"shadowcolor=black:shadowx=3:shadowy=3"
        )
        
    # Anti-détection
    if AD_ZOOM:
        v_filters.append("scale=iw*1.05:ih*1.05,crop=iw/1.05:ih/1.05:(iw-iw/1.05)/2:(ih-ih/1.05)/2")
    if AD_COLOR:
        v_filters.append("eq=saturation=1.04:contrast=1.02:brightness=0.0")
        v_filters.append("noise=c0s=8:c0f=a+u,noise=c1s=8:c1f=a+u,noise=c2s=8:c2f=a+u")
    if AD_ROTATE:
        v_filters.append("rotate=0.00349:fillcolor=black:ow=iw:oh=ih")
    if AD_VIGNETTE:
        v_filters.append("vignette=PI/5")
        
    # Fades (transitions)
    fade_filters = f"fade=in:st=0:d=0.3,fade=out:st={dur-0.3:.3f}:d=0.3"
    v_filters.append(fade_filters)
    
    # Assembler la chaîne vidéo complète
    full_vf = f"{filter_complex};{vf_input_label}{','.join(v_filters)}[out_v]"
    
    # Filtrage audio (Normalisation + Fades)
    # dynaudnorm égalise le son
    af_chain = f"dynaudnorm=f=150:g=15,afade=in:st=0:d=0.3,afade=out:st={dur-0.3:.3f}:d=0.3"
    if AD_SPEEDUP != 1.0:
        af_chain = f"atempo={AD_SPEEDUP:.4f},{af_chain}"
        
    full_af = f"[0:a]{af_chain}[out_a]"
    
    # Si trim de début/fin activé
    cmd = ["ffmpeg", "-y"]
    if AD_TRIM_SEC > 0:
        trim_dur = max(0.1, dur - 2 * AD_TRIM_SEC)
        cmd += ["-ss", str(AD_TRIM_SEC), "-t", str(trim_dur)]
        # recalculer dur pour les filtres
        dur = trim_dur
        # recréer les filtres avec la nouvelle durée
        v_filters = []
        if DRAW_STREAMER_NAME:
            v_filters.append(
                f"drawtext=fontfile='{abs_font_path}':text='{safe_name}':"
                f"fontcolor=white:fontsize=48:x=60:y=60:"
                f"shadowcolor=black:shadowx=3:shadowy=3"
            )
        if AD_ZOOM:
            v_filters.append("scale=iw*1.05:ih*1.05,crop=iw/1.05:ih/1.05:(iw-iw/1.05)/2:(ih-ih/1.05)/2")
        if AD_COLOR:
            v_filters.append("eq=saturation=1.04:contrast=1.02:brightness=0.0")
            v_filters.append("noise=c0s=8:c0f=a+u,noise=c1s=8:c1f=a+u,noise=c2s=8:c2f=a+u")
        if AD_ROTATE:
            v_filters.append("rotate=0.00349:fillcolor=black:ow=iw:oh=ih")
        if AD_VIGNETTE:
            v_filters.append("vignette=PI/5")
            
        fade_filters = f"fade=in:st=0:d=0.3,fade=out:st={dur-0.3:.3f}:d=0.3"
        v_filters.append(fade_filters)
        
        full_vf = f"{filter_complex};{vf_input_label}{','.join(v_filters)}[out_v]"
        
        af_chain = f"dynaudnorm=f=150:g=15,afade=in:st=0:d=0.3,afade=out:st={dur-0.3:.3f}:d=0.3"
        if AD_SPEEDUP != 1.0:
            af_chain = f"atempo={AD_SPEEDUP:.4f},{af_chain}"
        full_af = f"[0:a]{af_chain}[out_a]"
        
    cmd += [
        "-i", input_path,
        "-filter_complex", f"{full_vf};{full_af}",
        "-map", "[out_v]", "-map", "[out_a]",
        "-c:v", "libx264", "-preset", "superfast", "-r", "60",
        "-c:a", "aac", "-ar", "44100", "-b:a", "192k",
        "-y", output_path
    ]
    
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0 and os.path.exists(output_path)


# -------- Étape 5 : Outro de Fin (7 secondes) --------

def generate_outro_video(background_image_path, output_path):
    print("🔚 Génération de l'Outro de fin (7 secondes)...")
    if not os.path.exists(background_image_path):
        return False
        
    # Flouter l'image pour l'arrière-plan de l'outro
    try:
        img = Image.open(background_image_path)
        img_blur = img.filter(ImageFilter.GaussianBlur(15))
        
        # Diminuer la luminosité pour faire ressortir le texte
        enhancer = ImageEnhance.Brightness(img_blur)
        img_outro = enhancer.enhance(0.4)
        
        # Dessiner le texte "MERCI D'AVOIR REGARDÉ !"
        draw = ImageDraw.Draw(img_outro)
        try:
            font = ImageFont.truetype(FONT_PATH, 70)
            font_sub = ImageFont.truetype(FONT_PATH, 35)
        except:
            font = ImageFont.load_default()
            font_sub = ImageFont.load_default()
            
        text = "MERCI D'AVOIR REGARDÉ !"
        sub_text = "N'hésite pas à t'abonner et à liker la vidéo 👍"
        
        # Centrer le texte
        w, h = img_outro.size
        draw.text((w//2, h//2 - 50), text, font=font, fill=(255, 200, 0), anchor="mm")
        draw.text((w//2, h//2 + 50), sub_text, font=font_sub, fill=(255, 255, 255), anchor="mm")
        
        outro_img_path = os.path.join(OUTPUT_DIR, "outro_temp.jpg")
        img_outro.save(outro_img_path, quality=95)
    except Exception as e:
        print(f"⚠️ Erreur création image outro : {e}")
        return False
        
    # Créer la vidéo depuis l'image (7 secondes, muette)
    temp_outro_no_audio = os.path.join(OUTPUT_DIR, "outro_no_audio.mp4")
    cmd_outro_v = [
        "ffmpeg", "-y", "-loop", "1", "-i", outro_img_path,
        "-c:v", "libx264", "-t", "7", "-pix_fmt", "yuv420p",
        "-vf", "scale=1920:1080,fade=in:st=0:d=0.5,fade=out:st=6.5:d=0.5",
        "-r", "60", temp_outro_no_audio
    ]
    subprocess.run(cmd_outro_v, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Ajouter une piste audio silencieuse
    cmd_outro_a = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-i", temp_outro_no_audio,
        "-c:v", "copy", "-c:a", "aac", "-shortest", output_path
    ]
    subprocess.run(cmd_outro_a, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Nettoyage
    for f in [outro_img_path, temp_outro_no_audio]:
        try: os.remove(f)
        except: pass
        
    return os.path.exists(output_path)


# -------- Étape 6 : Téléchargement de la Musique Lo-Fi --------

def download_lofi_music():
    if os.path.exists(LOFI_PATH):
        return True
    print("🎵 Téléchargement d'une piste Lo-Fi libre de droits...")
    try:
        resp = requests.get(LOFI_URL, timeout=60)
        if resp.ok:
            with open(LOFI_PATH, "wb") as f:
                f.write(resp.content)
            print("✅ Musique Lo-Fi téléchargée.")
            return True
    except Exception as e:
        print(f"⚠️ Échec téléchargement Lo-Fi : {e}")
    return False


# -------- Étape 7 : Miniature Clickbait --------

def create_clickbait_thumbnail(image_paths, output_path, title_text):
    print("🖼️ Création de la miniature clickbait dynamique...")
    valid_images = [img for img in image_paths if os.path.exists(img)]
    if not valid_images: return
    
    FINAL_W, FINAL_H = 1280, 720
    CELL_W, CELL_H = FINAL_W // 2, FINAL_H // 2
    
    # Charger les 4 images
    raw_images = [Image.open(p).convert("RGB") for p in valid_images[:4]]
    while len(raw_images) < 4:
        raw_images.append(raw_images[-1].copy())
        
    # Quadrants
    overlays = [
        (30, 60, 180, 255), (180, 30, 30, 255),
        (20, 140, 60, 255), (100, 10, 150, 255)
    ]
    styled_cells = []
    
    for i, img in enumerate(raw_images):
        # Pour la case principale (top-left, 0), on applique un zoom de 150% (Zoom émotion)
        zoom = 1.5 if i == 0 else 1.08
        zw, zh = int(img.width * zoom), int(img.height * zoom)
        img_zoom = img.resize((zw, zh), Image.Resampling.LANCZOS)
        
        left = (zw - img.width) // 2
        top = (zh - img.height) // 2
        img_cropped = img_zoom.crop((left, top, left + img.width, top + img.height))
        
        # Saturation et contraste
        img_cropped = ImageEnhance.Contrast(img_cropped).enhance(1.3)
        img_cropped = ImageEnhance.Color(img_cropped).enhance(1.4)
        
        # Color overlay
        overlay = Image.new('RGBA', img_cropped.size, overlays[i])
        base = img_cropped.convert('RGBA')
        img_ready = Image.blend(base, overlay, 0.25).convert('RGB')
        
        img_ready = img_ready.resize((CELL_W, CELL_H), Image.Resampling.LANCZOS)
        styled_cells.append(img_ready)
        
    # Assembler
    mosaic = Image.new('RGB', (FINAL_W, FINAL_H), (0, 0, 0))
    positions = [(0, 0), (CELL_W, 0), (0, CELL_H), (CELL_W, CELL_H)]
    for cell, pos in zip(styled_cells, positions):
        mosaic.paste(cell, pos)
        
    draw = ImageDraw.Draw(mosaic, "RGBA")
    
    # 1. Bordure rouge vif sur la case principale (Top-Left)
    draw.rectangle([0, 0, CELL_W, CELL_H], outline=(255, 0, 0, 255), width=10)
    
    # 2. Dessiner une flèche rouge clickbait pointant vers la case 1 (Top-Right)
    # Flèche pointant vers (CELL_W + CELL_W//2, CELL_H//2)
    cx, cy = CELL_W + CELL_W//2, CELL_H//2
    draw.line([cx + 100, cy - 80, cx + 15, cy - 15], fill=(255, 0, 0, 255), width=15)
    draw.polygon([
        (cx + 15, cy - 15),
        (cx + 45, cy - 15),
        (cx + 15, cy - 45)
    ], fill=(255, 0, 0, 255))
    
    # 3. Séparation centrale (orange)
    sep_color = (255, 165, 0)
    draw.rectangle([0, FINAL_H//2 - 3, FINAL_W, FINAL_H//2 + 3], fill=sep_color)
    draw.rectangle([FINAL_W//2 - 3, 0, FINAL_W//2 + 3, FINAL_H], fill=sep_color)
    
    # 4. Ajout Logo
    if os.path.exists(LOGO_PATH):
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            logo_w = int(FINAL_W * 0.45)
            ratio = logo_w / logo.width
            logo = logo.resize((logo_w, int(logo.height * ratio)), Image.Resampling.LANCZOS)
            mosaic.paste(logo, ((FINAL_W - logo.width)//2, (FINAL_H - logo.height)//2), logo)
        except Exception as e:
            print(f"⚠️ Erreur logo miniature : {e}")
            
    # 5. Texte d'accroche géant (Clickbait)
    if DRAW_THUMBNAIL_TEXT:
        try:
            font = ImageFont.truetype(FONT_PATH, 95)
        except:
            font = ImageFont.load_default()
            
        text_clickbait = "CHOQUANT ! 😱"
        tx, ty = 40, FINAL_H - 140
        
        # Ombre noire épaisse
        for dx, dy in [(-3,-3), (3,-3), (-3,3), (3,3), (-3,0), (3,0), (0,-3), (0,3)]:
            draw.text((tx + dx, ty + dy), text_clickbait, font=font, fill=(0, 0, 0))
        draw.text((tx, ty), text_clickbait, font=font, fill=(255, 235, 0)) # Jaune clickbait
    
    # Enregistrer la miniature
    mosaic.save(output_path, quality=95)
    print(f"✅ Miniature sauvegardée : {output_path}")


# -------- Étape 8 & 9 : Late API & Telegram --------

def upload_to_late_cdn(file_path):
    print(f"📤 Upload de {os.path.basename(file_path)} sur Late CDN...")
    if not os.path.exists(file_path):
        return None
        
    filename = os.path.basename(file_path)
    content_type = "video/mp4" if filename.endswith(".mp4") else "image/jpeg"
    
    try:
        # Étape 1 : Demande de pré-signature
        resp = requests.post(
            "https://getlate.dev/api/v1/media/presign",
            headers={"Authorization": f"Bearer {LATE_API_KEY}", "Content-Type": "application/json"},
            json={"filename": filename, "contentType": content_type},
            verify=False, timeout=30
        )
        data = resp.json()
        upload_url = data.get("uploadUrl")
        public_url = data.get("publicUrl")
        
        if not upload_url or not public_url:
            print(f"❌ Échec pré-signature Late CDN : {data}")
            return None
            
        # Étape 2 : PUT du fichier
        with open(file_path, "rb") as f:
            put_resp = requests.put(
                upload_url,
                data=f,
                headers={"Content-Type": content_type},
                timeout=600
            )
            
        if put_resp.ok:
            print(f"✅ Upload Late CDN réussi : {public_url}")
            return public_url
    except Exception as e:
        print(f"❌ Exception lors de l'upload Late CDN : {e}")
        
    return None

def publish_to_youtube_late(video_url, thumbnail_url, caption_content):
    print("🚀 Publication YouTube via Late API (Zernio)...")
    url = "https://getlate.dev/api/v1/posts"
    
    # La première ligne de caption_content sert de titre pour YouTube, le reste est la description
    lines = caption_content.strip().split('\n')
    title = lines[0].strip() if len(lines) > 0 else "Best of Twitch"
    
    # Tronquer le titre si trop long (limite YouTube 100 caractères)
    if len(title) > 95:
        title = title[:92] + "..."
        
    # Créer le payload
    data = {
        'content': caption_content,
        'mediaItems': [
            {
                'url': video_url,
                'type': 'video',
                'thumbnail': thumbnail_url
            }
        ],
        'platforms': [{'platform': 'youtube', 'accountId': YOUTUBE_ACCOUNT_ID}],
        'publishNow': True
    }
    
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {LATE_API_KEY}", "Content-Type": "application/json"},
            json=data,
            verify=False, timeout=30
        )
        print(f"   📡 Statut API Late : {resp.status_code}")
        if resp.ok:
            print("✅ Post créé avec succès sur YouTube via Late API !")
            return True
        else:
            print(f"❌ Erreur API Late : {resp.text}")
    except Exception as e:
        print(f"❌ Exception API Late : {e}")
    return False

def send_telegram_recap(thumbnail_path, message_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    print("📧 Envoi du rapport et de la miniature sur Telegram...")
    
    # Envoi de la photo (miniature) avec la description en caption
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(thumbnail_path, "rb") as f:
            files = {"photo": f}
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": message_text,
                "parse_mode": "Markdown"
            }
            # Si le texte est trop long, Telegram limite caption à 1024 caractères
            if len(message_text) > 1024:
                data["caption"] = message_text[:1000] + "..."
                # Envoi du message texte complet après la photo
                requests.post(url, files=files, data=data, timeout=30)
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": TELEGRAM_CHAT_ID, "text": message_text, "parse_mode": "Markdown"},
                    timeout=30
                )
            else:
                requests.post(url, files=files, data=data, timeout=30)
            print("✅ Rapport Telegram envoyé.")
    except Exception as e:
        print(f"⚠️ Échec envoi Telegram : {e}")


# -------- Main Pipeline --------

def main():
    print("=" * 60)
    print("🎬 DÉMARRAGE DU GÉNÉRATEUR BEST-OF YOUTUBE LONG (16:9) 🎬")
    print("=" * 60)
    
    # Vérification des fichiers et variables
    if not os.path.exists(STREAMERS_FILE):
        print(f"❌ Fichier {STREAMERS_FILE} introuvable.")
        return
        
    with open(STREAMERS_FILE, "r", encoding="utf-8") as f:
        streamers = [line.strip() for line in f if line.strip()]
        
    if not streamers:
        print("❌ Liste de streamers vide.")
        return
        
    # Authentification Twitch
    try:
        twitch_token = get_twitch_token()
        headers = {'Client-ID': TWITCH_CLIENT_ID, 'Authorization': f'Bearer {twitch_token}'}
    except Exception as e:
        print(f"❌ Échec Authentification Twitch : {e}")
        return
        
    # Téléchargement musique Lo-Fi
    download_lofi_music()
    
    # Période de recherche (les dernières 24 heures)
    started_at = (datetime.utcnow() - timedelta(days=1)).isoformat() + 'Z'
    print(f"🔎 Analyse des clips créés depuis : {started_at}")
    
    all_clips = []
    
    # Récupérer les clips de chaque streamer
    for idx, name in enumerate(streamers, start=1):
        print(f"  [{idx}/{len(streamers)}] Récupération des clips de @{name}...", end="\r")
        uid = get_user_id(headers, name)
        if not uid:
            continue
        clips = get_clips_for_broadcaster(headers, uid, started_at, first=15)
        for clip in clips:
            all_clips.append(clip)
            
    print(f"\n✅ {len(all_clips)} clips bruts récupérés au total.")
    
    if not all_clips:
        print("❌ Aucun clip trouvé.")
        return
        
    # Trier par popularité combinée (index du streamer dans la liste + vues du clip)
    streamer_ranks = {name.lower(): idx for idx, name in enumerate(streamers)}
    def get_clip_score(c):
        b_name = c['broadcaster_name'].lower()
        rank = streamer_ranks.get(b_name, len(streamers))
        weight = max(1, len(streamers) - rank)
        return c['view_count'] * weight

    all_clips.sort(key=get_clip_score, reverse=True)
    
    # Charger l'historique des doublons
    fichier_tracking = "downloaded_clips.txt"
    deja_vus = set()
    if os.path.exists(fichier_tracking):
        with open(fichier_tracking, "r", encoding="utf-8") as f:
            deja_vus = set(line.strip() for line in f if line.strip())
            
    processed_clips = []
    thumbnail_frames = []
    total_duration = 0.0
    streamers_presents = []
    clip_durations = {}
    
    streamer_counts = {}
    
    # Filtrer, télécharger et assembler
    for clip in all_clips:
        if total_duration >= MIN_DURATION_SECONDS:
            break
            
        clip_id = clip['id']
        streamer_name = clip['broadcaster_name']
        
        # Éviter les doublons
        if clip_id in deja_vus:
            continue
            
        # Éviter de saturer un seul streamer dans la vidéo
        count = streamer_counts.get(streamer_name, 0)
        if count >= MAX_CLIPS_PER_STREAMER:
            continue
            
        raw_path = os.path.join(TEMP_DIR, f"{clip_id}_raw.mp4")
        jump_path = os.path.join(TRASH_DIR, f"{clip_id}_jump.mp4")
        std_path = os.path.join(TRASH_DIR, f"{clip_id}_std.mp4")
        
        # Téléchargement
        if not download_clip(clip['url'], raw_path):
            continue
            
        # --- Étape 1 : Détecteur Anti-Copyright Shazam ---
        is_copyrighted, title, artist = check_copyright_music(raw_path)
        if is_copyrighted:
            print(f"   ⚠️ EXCLU : Clip contenant '{title}' de '{artist}' (Copyright)")
            # Marquer comme vu pour ne pas reboucler dessus
            with open(fichier_tracking, "a", encoding="utf-8") as f:
                f.write(f"{clip_id}\n")
            deja_vus.add(clip_id)
            try: os.remove(raw_path)
            except: pass
            continue
            
        # --- Étape 2 : Jump-Cut ---
        if not remove_silence(raw_path, jump_path):
            try: os.remove(raw_path)
            except: pass
            continue
            
        # --- Étape 3 : Standardisation, Transitions & Zoom ---
        if not standardize_video(jump_path, std_path, streamer_name):
            for f in [raw_path, jump_path]:
                try: os.remove(f)
                except: pass
            continue
            
        # Extraire une frame pour la miniature
        frame_path = os.path.join(TEMP_DIR, f"{clip_id}.jpg")
        if extract_frame(std_path, frame_path):
            thumbnail_frames.append(frame_path)
            
        # Enregistrement des données du clip
        clip_dur = get_video_duration(std_path)
        total_duration += clip_dur
        processed_clips.append(std_path)
        clip_durations[std_path] = clip_dur
        streamers_presents.append(streamer_name)
        streamer_counts[streamer_name] = count + 1
        
        # Ajouter à l'historique
        with open(fichier_tracking, "a", encoding="utf-8") as f:
            f.write(f"{clip_id}\n")
        deja_vus.add(clip_id)
        
        print(f"   ✅ Clip validé ({clip_dur:.1f}s) : @{streamer_name} | Cumulé : {total_duration:.1f}s")
        
        # Nettoyage des clips bruts intermédiaires
        for f in [raw_path, jump_path]:
            try: os.remove(f)
            except: pass
            
    if not processed_clips:
        print("❌ Aucun clip valide n'a pu être traité.")
        return
        
    print(f"\n🎬 {len(processed_clips)} clips validés pour une durée totale de {total_duration:.1f}s.")
    
    # Générer l'Outro de fin
    outro_path = os.path.join(TRASH_DIR, "outro.mp4")
    has_outro = False
    if thumbnail_frames and generate_outro_video(thumbnail_frames[0], outro_path):
        has_outro = True
        
    # Assemblage final
    print("🔗 Assemblage de la compilation...")
    inputs_txt_path = os.path.join(OUTPUT_DIR, "inputs.txt")
    
    # 1. Sélectionner le Teaser (Hook de 5s du meilleur clip)
    best_clip_path = processed_clips[0]
    teaser_path = os.path.join(TRASH_DIR, "teaser.mp4")
    cmd_teaser = [
        "ffmpeg", "-y", "-ss", "0", "-t", "5", "-i", best_clip_path,
        "-c", "copy", teaser_path
    ]
    subprocess.run(cmd_teaser, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # On écrit la liste des clips à concaténer dans inputs.txt
    # Ordre : Teaser -> Compilation -> Outro
    with open(inputs_txt_path, "w", encoding="utf-8") as f:
        if os.path.exists(teaser_path):
            f.write(f"file '{os.path.abspath(teaser_path)}'\n")
        for path in processed_clips:
            f.write(f"file '{os.path.abspath(path)}'\n")
        if has_outro and os.path.exists(outro_path):
            f.write(f"file '{os.path.abspath(outro_path)}'\n")
            
    # Concaténation ultra-rapide des clips standardisés
    temp_concat_video = os.path.join(OUTPUT_DIR, "compilation_sans_musique.mp4")
    cmd_concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", inputs_txt_path,
        "-c", "copy", temp_concat_video
    ]
    subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # --- Étape 5 : Mixage de la Musique Lo-Fi et Incrustation de l'Overlay d'Abonnement ---
    print("🎵 Mixage final (Musique Lo-Fi + Bouton d'abonnement)...")
    final_duration = get_video_duration(temp_concat_video)
    
    # On planifie l'affichage du bouton d'abonnement (à 30% et 70% de la vidéo)
    t1_30 = int(final_duration * 0.3)
    t1_end = t1_30 + 5
    t2_70 = int(final_duration * 0.7)
    t2_end = t2_70 + 5
    
    abs_font_path = os.path.abspath(FONT_PATH).replace("\\", "/").replace(":", "\\:")
    
    cmd_mix = ["ffmpeg", "-y", "-i", temp_concat_video]
    
    # Si le fichier de musique Lo-Fi est disponible, on le mixe sous la vidéo
    if os.path.exists(LOFI_PATH):
        if DRAW_SUBSCRIBE_OVERLAY:
            vf_mixed = (
                f"drawtext=fontfile='{abs_font_path}':text='🔔 REJOINS LA COMMUNAUTE ET ABONNE-TOI !':"
                f"fontcolor=white:fontsize=36:x=(w-text_w)/2:y=h-100:box=1:boxcolor=red@0.8:boxborderw=18:"
                f"enable='between(t,{t1_30},{t1_end})',"
                f"drawtext=fontfile='{abs_font_path}':text='👍 LAISSE UN PETIT LIKE POUR SOUTENIR !':"
                f"fontcolor=white:fontsize=36:x=(w-text_w)/2:y=h-100:box=1:boxcolor=red@0.8:boxborderw=18:"
                f"enable='between(t,{t2_70},{t2_end})'"
            )
            v_filter_complex = f"[0:v]{vf_mixed}[out_v]"
        else:
            v_filter_complex = "[0:v]null[out_v]"
            
        cmd_mix.extend([
            "-stream_loop", "-1", "-i", LOFI_PATH,
            "-filter_complex", f"{v_filter_complex};[1:a]volume=0.06[bg_a];[0:a][bg_a]amix=inputs=2:duration=first[out_a]",
            "-map", "[out_v]", "-map", "[out_a]"
        ])
    else:
        if DRAW_SUBSCRIBE_OVERLAY:
            vf_mixed = (
                f"drawtext=fontfile='{abs_font_path}':text='🔔 REJOINS LA COMMUNAUTE ET ABONNE-TOI !':"
                f"fontcolor=white:fontsize=36:x=(w-text_w)/2:y=h-100:box=1:boxcolor=red@0.8:boxborderw=18:"
                f"enable='between(t,{t1_30},{t1_end})',"
                f"drawtext=fontfile='{abs_font_path}':text='👍 LAISSE UN PETIT LIKE POUR SOUTENIR !':"
                f"fontcolor=white:fontsize=36:x=(w-text_w)/2:y=h-100:box=1:boxcolor=red@0.8:boxborderw=18:"
                f"enable='between(t,{t2_70},{t2_end})'"
            )
            cmd_mix.extend([
                "-vf", vf_mixed,
                "-c:a", "copy"
            ])
        else:
            cmd_mix.extend([
                "-c:v", "copy",
                "-c:a", "copy"
            ])
            
    subprocess.run(cmd_mix, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # --- Création de la Miniature Miniature ---
    create_clickbait_thumbnail(thumbnail_frames, THUMBNAIL_PATH, "Compilation Twitch")
    
    # --- Étape 6 : Description & Chapitres (Timestamps) ---
    print("📝 Rédaction de la description avec timestamps...")
    
    # Calcul des timestamps
    timestamps = []
    current_time = 0.0
    
    # Si le teaser de 5s est présent
    if os.path.exists(teaser_path):
        timestamps.append(f"00:00 - Introduction & Teaser 🪝")
        current_time += 5.0
        
    # Liste des chapitres par clip
    for idx, path in enumerate(processed_clips):
        mm = int(current_time // 60)
        ss = int(current_time % 60)
        streamer = streamers_presents[idx]
        timestamps.append(f"{mm:02d}:{ss:02d} - {streamer}")
        current_time += clip_durations[path]
        
    # Outro
    if has_outro:
        mm = int(current_time // 60)
        ss = int(current_time % 60)
        timestamps.append(f"{mm:02d}:{ss:02d} - Outro final 🔚")
        
    timestamps_text = "\n".join(timestamps)
    
    # Liens Twitch
    twitch_links = "\n".join([f"🎮 {s} : https://twitch.tv/{s}" for s in set(streamers_presents)])
    
    # Titre Clickbait unique SEO (Sans date du jour générique pour éviter le classement en contenu dupliqué)
    main_streamer = streamers_presents[0] if streamers_presents else "Twitch"
    fallback_hook = f"LES MOMENTS LES PLUS FOUS SUR TWITCH ! 😱 ({main_streamer})"
    video_title = fallback_hook
    seo_intro = "📌 Retrouvez les meilleurs moments, clutchs et fous rires Twitch de la semaine !"
    
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_api_key)
            prompt_title = (
                f"Tu es un expert SEO YouTube spécialisé dans les compilations Twitch/Gaming. "
                f"Génère UN SEUL TITRE YouTube sensationnel, unique et viral (max 70 caractères, en français). "
                f"Le titre doit créer une forte curiosité/drama autour de ces streamers : {', '.join(list(set(streamers_presents))[:5])}. "
                f"Exemples : 'JLTOMY PERD 10 000€ EN DIRECT SUR STUMBLE GUYS ! 😱', 'LE PIRE CRASH EN STREAM DE L'HISTOIRE... 🤦‍♂️'. "
                f"IMPORTANT : N'inclus AUCUNE date, ni 'Best of du 04/08', ni aucun suffixe générique. "
                f"Réponds STRICTEMENT avec uniquement le titre, sans guillemets, sans aucun autre texte."
            )
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt_title}],
                max_tokens=60
            )
            generated_title = completion.choices[0].message.content.strip().strip('"').strip("'").strip()
            if generated_title:
                video_title = generated_title
                
            prompt_seo = (
                f"Rédige un paragraphe de description SEO optimisé pour la recherche YouTube (3-4 phrases captivantes) "
                f"pour une vidéo compilation gaming/Twitch réunissant les streamers : {', '.join(list(set(streamers_presents))[:6])}. "
                f"Inclus naturellement des mots-clés de recherche populaires (ex: clips drôles, moments forts Twitch FR, best of gaming). "
                f"Ne mets pas de titre dans ta réponse."
            )
            completion_seo = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt_seo}],
                max_tokens=200
            )
            gen_seo = completion_seo.choices[0].message.content.strip()
            if gen_seo:
                seo_intro = gen_seo
        except Exception as e:
            print(f"⚠️ Erreur génération titre/SEO Groq : {e}")
            
    if len(video_title) > 95:
        video_title = video_title[:92] + "..."
            
    # Construction de la description enrichie SEO (Point 3)
    full_description = f"""{video_title}

{seo_intro}

👾 Streamers présents dans ce best-of :
{twitch_links}

📖 Chapitres :
{timestamps_text}

❤️ Merci à tous les streamers pour leurs clips incroyables !
🔔 Abonne-toi et active la cloche pour soutenir la chaîne et ne rater aucun best-of !
👉 Retrouve leurs lives complets directement sur leurs chaînes Twitch.

#TwitchFR #BestOfTwitch #ClipsTwitch #GamingFR #BestOfGaming #Shorts #TwitchFrance"""

    # Enregistrer la description localement
    with open(os.path.join(OUTPUT_DIR, "description_youtube.txt"), "w", encoding="utf-8") as f:
        f.write(full_description)
        
    # --- Publication via Late API (si configuré) ---
    late_post_success = False
    
    dyn_late_key, dyn_youtube_id = pick_and_increment_youtube_account()
    if dyn_late_key and dyn_youtube_id:
        global LATE_API_KEY, YOUTUBE_ACCOUNT_ID
        original_late_key = LATE_API_KEY
        original_youtube_id = YOUTUBE_ACCOUNT_ID
        
        LATE_API_KEY = dyn_late_key
        YOUTUBE_ACCOUNT_ID = dyn_youtube_id
        
        # 1. Pousser la miniature
        pub_thumb_url = upload_to_late_cdn(THUMBNAIL_PATH)
        # 2. Pousser la vidéo
        pub_video_url = upload_to_late_cdn(FINAL_VIDEO_PATH)
        
        if pub_video_url and pub_thumb_url:
            # 3. Publier
            late_post_success = publish_to_youtube_late(pub_video_url, pub_thumb_url, full_description)
            
        # Restaurer les valeurs globales
        LATE_API_KEY = original_late_key
        YOUTUBE_ACCOUNT_ID = original_youtube_id
            
    # --- Rapport Telegram ---
    tg_message = (
        f"📢 *Compilation YouTube Longue Générée !*\n\n"
        f"📝 *Titre :* `{video_title}`\n"
        f"⏳ *Durée :* `{final_duration:.1f}s`\n"
        f"📈 *Clips insérés :* `{len(processed_clips)}`\n"
        f"🚀 *Statut Late API :* `{'✅ Publiée' if late_post_success else '❌ Non postée'}`\n\n"
        f"📌 *Streamers présents :*\n"
        f"{', '.join(set(streamers_presents))}"
    )
    send_telegram_recap(THUMBNAIL_PATH, tg_message)
    
    # 🧹 Nettoyage des dossiers temporaires
    print("🧹 Nettoyage final des fichiers temporaires...")
    for f in glob.glob(os.path.join(TEMP_DIR, "*")):
        try: os.remove(f)
        except: pass
    for f in glob.glob(os.path.join(TRASH_DIR, "*")):
        try: os.remove(f)
        except: pass
    for f in [temp_concat_video, inputs_txt_path, teaser_path]:
        if os.path.exists(f):
            try: os.remove(f)
            except: pass
            
    print("\n✅ PIPELINE YOUTUBE TERMINÉ AVEC SUCCÈS !")

if __name__ == "__main__":
    main()
