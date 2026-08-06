import os
import sys
import subprocess
import cv2
import ftplib
import imageio_ffmpeg
import requests
import json  # <--- Ajouté pour gérer le JSON
import time  # <--- Ajouté pour le chronomètre
from datetime import datetime, timedelta
from ultralytics import YOLO

from groq import Groq
import urllib3

# -------- Viral Brain --------
try:
    from viral_brain import (
        detect_emotion, get_prompt_context,
        get_virality_score_for_clip, update_brain
    )
    VIRAL_BRAIN_AVAILABLE = True
except ImportError:
    VIRAL_BRAIN_AVAILABLE = False
    print("⚠️ viral_brain.py non trouvé — mode classique activé")

ERRORS_FILE = "errors.json"
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Désactivation des avertissements SSL (puisque nous allons utiliser verify=False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Groq Client Initialization
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# -------- Dépendance Shazam (Anti-Copyright) --------
import asyncio
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
        out = await shazam.recognize(file_path)
        if 'track' in out:
            title = out['track'].get('title', 'Unknown')
            artist = out['track'].get('subtitle', 'Unknown')
            return True, title, artist
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

# ========= CONFIG =========
NB_VIDEOS = 1        # << Nombre de vidéos finales à générer
TARGET_SECONDS = 75  # << Durée MINIMALE de clips BRUTS à assembler
# Note : la durée FINALE sera légèrement inférieure à cause du speedup x1.05 et du trim.
# Avec TARGET_SECONDS=75 : durée finale ~= (75 - 2*ANTI_DETECT_TRIM_SEC*NbClips) / ANTI_DETECT_SPEEDUP >= 60s
# SEARCH CONFIG
SEARCH_QUERY = "anyme023"   # Nom du streamer OU du jeu
SEARCH_TYPE = "channel"       # 'channel' ou 'game'
SEARCH_PERIOD = "24h"          # '24h', '7d', '30d', 'all'
CLIP_LANGUAGE = "fr"          # 'fr', 'en', etc. ou "" pour tout (ex: None)

# LOGS CONFIG
LOGS_FILE = "creation_logs.json" # <--- Fichier où on stocke les durées

# FTP CONFIG
FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
REMOTE_DIR = "www"
BASE_URL = "https://clipo.fr"

# POSTING CONFIG (Late API / TikTok)
LATE_API_KEY = os.getenv("LATE_API_KEY")

# On définit une valeur par défaut, mais elle sera écrasée par l'interface web
TIKTOK_ACCOUNT_ID = os.getenv("TIKTOK_ACCOUNT_ID_HAWAII") 
LATE_PLATFORM = "tiktok" # "tiktok" ou "youtube"

# Paramètres TikTok
TIKTOK_SETTINGS = {
    'privacy_level': 'PUBLIC_TO_EVERYONE', # 'PUBLIC_TO_EVERYONE', 'FRIENDS_ONLY', 'PRIVATE_TO_MYSELF'
    'allow_comment': True,
    'allow_duet': True,
    'allow_stitch': True,
    'content_preview_confirmed': True,
    'express_consent_given': True
}
PUBLISH_NOW = True # True pour publier direct, False pour brouillon/programmé
SCHEDULE_HOUR = 12   # Heure de programmation (0-23)
SCHEDULE_MINUTE = 0  # Minute de programmation (0-59)
AUTO_POST = False     # True = Post auto (FTP + API), False = Juste créer la vidéo localement
SEND_TELEGRAM = False # True = Envoi sur Telegram, False = Non
YOUTUBE_MODE = False  # True = YouTube Short (1 clip, pas de durée min, pas de TikTok)

# Chat ID Telegram override pour les clients (rempli par executer_pipeline depuis la licence)
# None = utilise le TELEGRAM_CHAT_ID du .env (le tien)
TELEGRAM_CHAT_ID_OVERRIDE = None
_CURRENT_LICENSE_KEY       = ''   # Clé de licence du job en cours (pour consume + stats)
IGNORE_HISTORY             = False # Si True, on autorise les clips déjà vus

# ========= CONFIG ANTI-DÉTECTION =========
# Ces réglages modifient subtilement la vidéo pour tromper les algorithmes de détection
# (Content ID, TikTok, YouTube...) sans que l'œil humain remarque quoi que ce soit.
ANTI_DETECT_ENABLED   = True    # Active/désactive l'ensemble du module
ANTI_DETECT_SPEEDUP   = 1.03    # Accélération légère (+3% imperceptible)
ANTI_DETECT_ZOOM      = True    # Micro-zoom 104% + recadrage (décale tous les pixels)
ANTI_DETECT_COLOR     = True    # Saturation +5%, contraste léger, grain 5% (change l'empreinte vidéo)
ANTI_DETECT_MIRROR    = False   # Miroir horizontal (désactivé sur demande)
ANTI_DETECT_ROTATE    = True    # Décalage pixel (micro crop+scale, rapide)
ANTI_DETECT_VIGNETTE  = True    # Vignette sombre sur les bords
ANTI_DETECT_WATERMARK = True    # Incrustation du filigrane avec le nom du compte TikTok
ANTI_DETECT_TRIM_SEC  = 0.5     # Coupe N secondes au début ET à la fin de chaque clip source
#   ↑ Content ID fingerprinte surtout les premières/dernières frames : les supprimer est très efficace

ENABLE_WEBCAM_OVERLAY = False  # False = Pas de superposition webcam (mode fond flou unique)
# ==========================================

# On interroge suffisamment de clips côté API, mais on ne télécharge qu'à la demande.
MAX_API_CLIPS = NB_VIDEOS * 250  # augmente si nécessaire
# ==========================

client_id = os.getenv("TWITCH_CLIENT_ID")
client_secret = os.getenv("TWITCH_CLIENT_SECRET")

# -------- Utils --------

def get_access_token():
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
    
    # Twitch limite 'first' à 100 maximum par requête
    params = {'first': min(first, 100)}
    if broadcaster_id:
        params['broadcaster_id'] = broadcaster_id
    if game_id:
        params['game_id'] = game_id
    if started_at:
        params['started_at'] = started_at
    
    all_clips = []
    
    while True:
        response = requests.get('https://api.twitch.tv/helix/clips', headers=headers, params=params, verify=False)
        response.raise_for_status()
        data = response.json()
        
        clips = data.get('data', [])
        all_clips.extend(clips)
        
        # Si on n'a plus de résultats ou qu'on a atteint la limite demandée
        if len(clips) == 0 or len(all_clips) >= first:
            break
            
        cursor = data.get('pagination', {}).get('cursor')
        if not cursor:
            break
            
        # Préparer la requête suivante
        params['after'] = cursor
    
    return all_clips[:first]

def telecharger_clip(url, output_file, thumbnail_url=None):
    import re
    print(f"⏬ Téléchargement de {url}...")
    
    # 1. Tentative avec Streamlink (sans l'option obsolète --twitch-disable-ads)
    cmd = [sys.executable, "-m", "streamlink", url, "best", "-o", output_file]
    try:
        print("   🎬 Essai 1 : Streamlink...")
        result = subprocess.run(cmd)
        if result.returncode == 0 and os.path.exists(output_file) and os.path.getsize(output_file) > 500000:
            print("   ✅ Succès avec Streamlink")
            return True
    except Exception as e:
        print(f"   ⚠️ Échec Streamlink : {e}")

    # 2. Fallback 1: Tentative avec yt-dlp
    cmd_yt = [sys.executable, "-m", "yt_dlp", url, "-o", output_file]
    try:
        print("   🔄 Essai 2 : Fallback avec yt-dlp...")
        result_yt = subprocess.run(cmd_yt)
        if result_yt.returncode == 0 and os.path.exists(output_file) and os.path.getsize(output_file) > 500000:
            print("   ✅ Succès avec yt-dlp")
            return True
    except Exception as e:
        print(f"   ⚠️ Échec yt-dlp : {e}")

    # 3. Fallback 2: Téléchargement direct via thumbnail_url
    if thumbnail_url:
        print("   🔄 Essai 3 : Fallback direct via thumbnail...")
        video_url = re.sub(r'-preview-\d+x\d+\.jpg$', '.mp4', thumbnail_url)
        if video_url:
            print(f"   URL direct : {video_url}")
            try:
                resp = requests.get(video_url, stream=True, verify=False, timeout=60)
                if resp.ok:
                    with open(output_file, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    if os.path.exists(output_file) and os.path.getsize(output_file) > 500000:
                        print("   ✅ Succès via téléchargement direct")
                        return True
            except Exception as e:
                print(f"   ⚠️ Échec téléchargement direct : {e}")
                
    return False

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

def save_creation_log(streamer, title, filename, duration_seconds, video_duration=0):
    """Sauvegarde les stats de création dans un JSON"""
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "streamer": streamer,
        "video_title": title,
        "filename": filename,
        "processing_time_seconds": round(duration_seconds, 2),
        "processing_time_human": str(timedelta(seconds=round(duration_seconds))),
        "video_duration_seconds": round(video_duration, 2)
    }
    
    data = []
    # Charger l'existant
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            pass # Fichier vide ou corrompu

    # Ajouter le nouveau
    data.append(entry)
    
    # Sauvegarder
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
    if img is None:
        return None
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
    import shutil
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def get_video_info(file_path):
    """Récupère durée, largeur, hauteur via FFmpeg (stderr)."""
    cmd = [get_ffmpeg_cmd(), "-i", file_path]
    # FFmpeg écrit les infos sur stderr
    result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    
    duration = 0.0
    width = 0
    height = 0
    
    # Parsing basique
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
                import re
                match = re.search(r'(\d{2,5})x(\d{2,5})', line)
                if match:
                    width = int(match.group(1))
                    height = int(match.group(2))
            except:
                pass
                
    return duration, width, height

# -------- Montage FFmpeg --------

def _build_anti_detect_vf(base_label):
    """
    Construit la chaîne de filtres vidéo anti-détection à insérer dans le filter_complex.
    Prend un label d'entrée (ex: '[outv]') et renvoie (nouvelle_chaine, nouveau_label).
    Les filtres sont fusionnés dans le graphe principal : 0 passe d'encodage supplémentaire.
    """
    if not ANTI_DETECT_ENABLED:
        return "", base_label

    chain_parts = []
    current = base_label
    step = 0

    def next_label():
        nonlocal step
        step += 1
        return f"[ad{step}]"

    # 1. SPEEDUP vidéo (setpts) — ajuste la vitesse de lecture
    speed = ANTI_DETECT_SPEEDUP
    pts = f"setpts={1.0/speed:.6f}*PTS"
    nxt = next_label()
    chain_parts.append(f"{current}{pts}{nxt}")
    current = nxt

    # 2. ZOOM + RECADRAGE au centre (110%)
    if ANTI_DETECT_ZOOM:
        zoom_filter = "scale=iw*1.10:ih*1.10,crop=iw/1.10:ih/1.10:(iw-iw/1.10)/2:(ih-ih/1.10)/2"
        nxt = next_label()
        chain_parts.append(f"{current}{zoom_filter}{nxt}")
        current = nxt

    # 3. COLORIMÉTRIE : saturation, contraste + noise (rapide, remplace geq)
    if ANTI_DETECT_COLOR:
        # eq = saturation/contraste léger
        eq_f = "eq=saturation=1.05:contrast=1.02:brightness=0.0"
        nxt = next_label()
        chain_parts.append(f"{current}{eq_f}{nxt}")
        current = nxt
        # noise = grain léger (c=12 = ~5% ; flags=a pour bruit aléatoire) — 50x plus rapide que geq
        noise_f = "noise=c0s=10:c0f=a+u,noise=c1s=10:c1f=a+u,noise=c2s=10:c2f=a+u"
        nxt = next_label()
        chain_parts.append(f"{current}{noise_f}{nxt}")
        current = nxt

    # 4. MIROIR HORIZONTAL (optionnel)
    if ANTI_DETECT_MIRROR:
        nxt = next_label()
        chain_parts.append(f"{current}hflip{nxt}")
        current = nxt

    # 5. DÉCALAGE PIXEL RAPIDE (remplace rotate)
    #    Principe : crop 2px d'un côté + scale retour taille originale
    #    → tous les pixels changent de position XY (même effet anti-détection que rotate 0.3°)
    #    → 100x plus rapide car pas d'interpolation trigonométrique
    if ANTI_DETECT_ROTATE:
        nxt = next_label()
        chain_parts.append(f"{current}crop=iw-2:ih-2:1:1,scale=iw+2:ih+2{nxt}")
        current = nxt

    # 6. VIGNETTE SOMBRE SUR LES BORDS
    if ANTI_DETECT_VIGNETTE:
        nxt = next_label()
        chain_parts.append(f"{current}vignette=PI/4:mode=forward{nxt}")
        current = nxt

    # 7. FILIGRANE NOM DU COMPTE TIKTOK (Au milieu de l'image, MAJUSCULE, sans @, 15% opacité)
    if getattr(sys.modules[__name__], 'ANTI_DETECT_WATERMARK', True):
        wm_user = os.getenv("TIKTOK_WATERMARK_USER", os.getenv("TIKTOK_ACCOUNT_ID", "BestOfTwitch_FR"))
        clean_user = wm_user.replace("@", "").replace("'", "").replace(":", "").replace("\\", "").upper()
        font_arg = "fontfile=Nunito-Black.ttf:" if os.path.exists("Nunito-Black.ttf") else ""
        wm_f = f"drawtext={font_arg}text='{clean_user}':fontcolor=white@0.15:fontsize=56:box=0:x=(w-text_w)/2:y=(h-text_h)/2"
        nxt = next_label()
        chain_parts.append(f"{current}{wm_f}{nxt}")
        current = nxt

    return ";".join(chain_parts), current


def montage_tiktok(clips_paths, crop_params, output_path, clip_durations=None):
    """clip_durations : dict optionnel {path -> durée_float} pour éviter les ffprobe en double."""
    print(f"🎞️ Montage final (FFmpeg - Safe Mode) : {output_path}")
    if not ANTI_DETECT_ENABLED:
        print("   🛡️ Anti-détection : DÉSACTIVÉE")
    else:
        flags = []
        if ANTI_DETECT_SPEEDUP != 1.0:          flags.append(f"⏱️ x{ANTI_DETECT_SPEEDUP}")
        if ANTI_DETECT_ZOOM:                    flags.append("🔍 Zoom")
        if ANTI_DETECT_COLOR:                   flags.append("🎨 Color+Grain")
        if ANTI_DETECT_MIRROR:                  flags.append("🪞 Miroir")
        if ANTI_DETECT_ROTATE:                  flags.append("🔄 Rotation")
        if ANTI_DETECT_VIGNETTE:                flags.append("🌑 Vignette")
        if getattr(sys.modules[__name__], 'ANTI_DETECT_WATERMARK', True): flags.append("💧 Filigrane TikTok")
        if ANTI_DETECT_TRIM_SEC > 0:            flags.append(f"✂️ Trim {ANTI_DETECT_TRIM_SEC}s")
        print(f"   🛡️ Anti-détection intégrée : {' | '.join(flags)}")

    if not clips_paths:
        return

    ffmpeg = get_ffmpeg_cmd()

    _, src_w, src_h = get_video_info(clips_paths[0])
    if src_w == 0 or src_h == 0:
        src_w, src_h = 1920, 1080

    cmd_inputs = []
    for path in clips_paths:
        cmd_inputs.extend(["-i", path])

    # --- TRIM PAR CLIP : coupe les N premières et dernières secondes de chaque source ---
    # On utilise clip_durations si disponible pour éviter les appels ffprobe en double.
    trim_sec = ANTI_DETECT_TRIM_SEC if ANTI_DETECT_ENABLED else 0.0
    pre_trim_filters = []
    concat_v_refs = ""

    for i, path in enumerate(clips_paths):
        if trim_sec > 0:
            # Utilise la durée déjà connue si disponible, sinon ffprobe (fallback)
            if clip_durations and path in clip_durations:
                dur = clip_durations[path]
            else:
                dur, _, _ = get_video_info(path)
            end = max(trim_sec + 0.1, dur - trim_sec)
            pre_trim_filters.append(
                f"[{i}:v]trim=start={trim_sec:.3f}:end={end:.3f},setpts=PTS-STARTPTS,setsar=1[tv{i}]"
            )
            pre_trim_filters.append(
                f"[{i}:a]atrim=start={trim_sec:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[ta{i}]"
            )
            concat_v_refs += f"[tv{i}][ta{i}]"
        else:
            pre_trim_filters.append(f"[{i}:v]setsar=1[tv{i}]")
            concat_v_refs += f"[tv{i}][{i}:a]"

    if trim_sec > 0:
        trim_block = ";".join(pre_trim_filters)
        filter_concat = f"{trim_block};{concat_v_refs}concat=n={len(clips_paths)}:v=1:a=1[joined_v][joined_a]"
    else:
        filter_concat = f"{concat_v_refs}concat=n={len(clips_paths)}:v=1:a=1[joined_v][joined_a]"

    # --- Montage (crop/overlay) ---
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
            f"[cam_ready][game_ready]vstack[pre_ad]"
        )
    else:
        filter_processing = (
            f"[joined_v]split=2[bg][fg];"
            f"[bg]scale=-2:1280,crop=720:1280,boxblur=20:10[bg_blurred];"
            f"[fg]scale=720:-2[fg_scaled];"
            f"[bg_blurred][fg_scaled]overlay=(W-w)/2:(H-h)/2[pre_ad]"
        )

    # --- Anti-détection intégrée dans le même graphe (0 encodage supplémentaire) ---
    ad_chain, final_label = _build_anti_detect_vf("[pre_ad]")

    # --- Audio : atempo pour le speedup (intégré dans filter_complex, obligatoire FFmpeg 7.x) ---
    # FFmpeg 7.x interdit -af sur un stream issu d'un filter_complex → on l'intègre dedans
    speed = ANTI_DETECT_SPEEDUP if ANTI_DETECT_ENABLED else 1.0
    if speed != 1.0:
        if speed <= 2.0:
            af_chain = f"atempo={speed:.4f}"
        else:
            af_chain = f"atempo=2.0,atempo={speed/2.0:.4f}"
        audio_filter = f";[joined_a]{af_chain}[out_a]"
        audio_output_label = "[out_a]"
    else:
        audio_filter = ""
        audio_output_label = "[joined_a]"

    if ad_chain:
        full_filter = f"{filter_concat};{filter_processing};{ad_chain}{audio_filter}"
    else:
        # Pas d'anti-détection : on inclut l'audio directement
        full_filter = f"{filter_concat};{filter_processing};[pre_ad]copy[ad1]{audio_filter}"
        final_label = "[ad1]"

    cmd = [ffmpeg]
    cmd.extend(cmd_inputs)
    cmd.extend([
        "-filter_complex", full_filter,
        "-map", final_label,
        "-map", audio_output_label,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-threads", "0",          # utilise tous les coeurs CPU dispos
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-r", "60",
        "-y", output_path
    ])

    print("   ⚙️ Encodage en cours (Concat + Montage + Anti-détection en 1 passe)...")
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ Exporté via FFmpeg : {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur FFmpeg : {e}")


# -------- Error Logging --------

def log_error(canal: str, error_type: str, message: str):
    """
    Stocke une erreur dans errors.json (max 20 entrées).
    """
    try:
        errors = []
        if os.path.exists(ERRORS_FILE) and os.path.getsize(ERRORS_FILE) > 0:
            try:
                with open(ERRORS_FILE, "r", encoding="utf-8") as f:
                    errors = json.load(f)
            except Exception:
                errors = []
        errors.append({
            "timestamp": datetime.now().strftime("%d/%m %H:%M"),
            "canal":     canal,
            "type":      error_type,
            "message":   message
        })
        # Garder seulement les 20 dernières
        errors = errors[-20:]
        with open(ERRORS_FILE, "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Impossible d'écrire errors.json : {e}")


# -------- Tracking Analytics --------

TRACKING_FILE = "tracking.json"

def add_to_tracking(tiktok_url: str, search_query: str = "", account_name: str = ""):
    """
    Ajoute une URL TikTok dans tracking.json pour qu'elle soit analysée
    par stats_daemon / get_last_10.py lors du prochain scan.
    """
    if not tiktok_url or not isinstance(tiktok_url, str):
        return
    try:
        data = []
        if os.path.exists(TRACKING_FILE):
            with open(TRACKING_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        # Vérifier que l'URL n'est pas déjà dans le tracking
        existing_urls = [
            (e.get('url') if isinstance(e, dict) else e) for e in data
        ]
        if tiktok_url in existing_urls:
            print(f"ℹ️ URL déjà dans tracking.json : {tiktok_url}")
            return
        # Ajouter sous forme de dict avec le compte
        entry = {
            "url": tiktok_url,
            "query": search_query,
            "account": account_name
        }
        data.append(entry)
        with open(TRACKING_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"📋 URL ajoutée au tracking analytics : {tiktok_url}")
    except Exception as e:
        print(f"⚠️ Impossible d'ajouter à tracking.json : {e}")


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

def generate_metadata(streamer_name: str, titre_clip_twitch: str, canal_label: str = "") -> str:
    print(f"🧠 Génération des métadonnées avec Groq pour : {titre_clip_twitch}...")

    # ── Viral Brain : détection émotion + contexte learné ──────────────────
    brain_context = ""
    if VIRAL_BRAIN_AVAILABLE and canal_label:
        emotion = detect_emotion(titre_clip_twitch)
        print(f"🎭 Émotion détectée : {emotion}")
        brain_context = get_prompt_context(canal_label, emotion)
    # ────────────────────────────────────────────────────────────────────────

    system_instruction = f"""
    Tu es un expert en viralité pour TikTok et YouTube Shorts.
    Ton but est de générer un TITRE EXPLOSIF et SÉCURISÉ pour maximiser le taux de clic (CTR).

    RÈGLES CRITIQUES (ANTI-BAN) :
    1. ⛔ INTERDIT ABSOLU : Mots violents, gore ou "dangereux" (ex: "Tuer", "Mort", "Sang", "Couteau", "Arme", "Couper", "Drogue", "Suicide"). Utilise plutôt : "DÉTRUIT" (figuré), "EXPLOSE", "FINI", "CHOC".
    2. ✅ STYLE : Court (< 50 caractères), Mots-clés principaux en MAJUSCULES, 2 à 3 émojis dynamiques (😱, 🔥, 🤣, 🚀, 🤯).

    INSTRUCTIONS :
    1. Analyse le NOM DU STREAMER et le TITRE DU CLIP fournis.
    2. Génère un TITRE CLICKBAIT (Formule de Question, de Défi ou de Réaction exagérée).
    3. Génère une liste de HASHTAGS pertinents (Génériques comme #TwitchFR + Spécifiques comme le Jeu ou le Streamer).

{brain_context}
    FORMAT DE RÉPONSE STRICT (2 lignes maximum, sans guillemets, sans préfixe) :
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

        titre    = lines[0].strip() if len(lines) > 0 else "TITRE VIRAL GENERE"
        hashtags = lines[1].strip() if len(lines) > 1 else "#Viral #Twitch"

        final_caption = f"{titre}\n{hashtags}"
        print(f"✨ Métadonnées générées :\n{final_caption}")
        return final_caption

    except Exception as e:
        print(f"❌ Erreur Groq : {e}")
        return f"Clip de {streamer_name} ! 🎬 #TwitchFR #BestOf #Viral"


def generate_first_comment(streamer_name: str, titre_clip_twitch: str) -> str:
    """
    Génère un premier commentaire automatique avec l'IA Groq :
    Question engageante/polémique citant obligatoirement le streamer et liée au sujet du clip.
    """
    system_instruction = (
        "Tu es un expert TikTok spécialiste des compilations Twitch FR.\n"
        "Génère UN SEUL commentaire très court (maximum 10 mots) sous forme de question polémique ou engageante "
        "pour faire débattre les abonnés dans l'espace commentaire.\n"
        "RÈGLES STRICTES:\n"
        f"1. CITE OBLIGATOIREMENT le nom du streamer '{streamer_name}' dans la question.\n"
        "2. Pose une question en rapport direct avec la vidéo.\n"
        "3. Termine par 1 emoji d'appel à l'action (ex: 👇, 💬 ou 😱).\n"
        "4. Réponds UNIQUEMENT avec la phrase du commentaire, sans guillemets ni fioritures."
    )
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Streamer: {streamer_name}\nTitre du clip: {titre_clip_twitch}"}
            ],
            temperature=0.8,
            max_tokens=80,
            top_p=1
        )
        comment = completion.choices[0].message.content.strip().strip('"')
        print(f"💬 Premier commentaire Groq généré : {comment}")
        return comment
    except Exception as e:
        print(f"⚠️ Erreur génération commentaire Groq : {e}")
        return f"Vous en pensez quoi de la réaction de {streamer_name} ? 👇"

# -------- Upload CDN Late (presign + PUT) --------

def upload_to_late_cdn(video_path: str) -> str | None:
    """
    Upload la vidéo sur le CDN Late en 2 étapes :
      1. Presign  : Late retourne une uploadUrl + publicUrl
      2. PUT      : on pousse le fichier directement (sans Authorization)
    Retourne l'URL publique Late (CDN), ou None si échec.
    TikTok tire depuis le CDN Late → beaucoup plus fiable qu'un domaine perso.
    """
    print("📤 Upload vidéo sur le CDN Late...")
    if not os.path.exists(video_path):
        print(f"❌ Fichier vidéo introuvable (probablement échec FFmpeg) : {video_path}")
        return None
        
    filename = os.path.basename(video_path)
    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)

    # Étape 1 : Presign
    try:
        presign_resp = requests.post(
            "https://getlate.dev/api/v1/media/presign",
            headers={"Authorization": f"Bearer {LATE_API_KEY}", "Content-Type": "application/json"},
            json={"filename": filename, "contentType": "video/mp4"},
            verify=False,
            timeout=30
        )
        presign_data = presign_resp.json()
        upload_url  = presign_data.get("uploadUrl")
        public_url  = presign_data.get("publicUrl")
        if not upload_url or not public_url:
            print(f"❌ Presign : réponse inattendue → {presign_data}")
            return None
        print(f"✅ Presign OK ({file_size_mb:.1f} MB à uploader)")
    except Exception as e:
        print(f"❌ Erreur presign Late : {e}")
        return None

    # Étape 2 : PUT du fichier (pas d'Authorization — URL signée)
    try:
        print(f"📤 Envoi du fichier vers le CDN Late...")
        with open(video_path, "rb") as f:
            put_resp = requests.put(
                upload_url,
                data=f,
                headers={"Content-Type": "video/mp4"},
                timeout=600  # 10 min max pour un gros fichier
            )
        if not put_resp.ok:
            print(f"❌ Erreur PUT CDN : HTTP {put_resp.status_code} — {put_resp.text[:200]}")
            return None
        print(f"✅ Upload CDN Late réussi → {public_url}")
        return public_url
    except Exception as e:
        print(f"❌ Erreur upload CDN Late : {e}")
        return None


# -------- API Late --------

def publish_to_late_api(video_url: str, caption_content: str, first_comment: str = None):
    """
    Poste la vidéo sur TikTok / YouTube Shorts via l'API Late (avec premier commentaire auto).
    video_url : URL publique complète (CDN Late ou autre)
    """
    print("🚀 Publication sur Late...")
    print(f"   URL vidéo : {video_url}")
    if first_comment:
        print(f"   💬 Auto-Commentaire inclus : {first_comment}")
    
    url = 'https://getlate.dev/api/v1/posts'
    headers = {
        'Authorization': f'Bearer {LATE_API_KEY}',
        'Content-Type': 'application/json'
    }

    # Préparation du payload
    data = {
        'content': caption_content,
        'mediaItems': [
            {
                'url': video_url, 
                'type': 'video' 
            }
        ],
        'platforms': [{'platform': LATE_PLATFORM, 'accountId': TIKTOK_ACCOUNT_ID}],
        'tiktokSettings': TIKTOK_SETTINGS,
        'publishNow': PUBLISH_NOW
    }

    if first_comment:
        data['firstComment'] = first_comment

    # Si on ne publie pas immédiatement, on ajoute la date de programmation
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
            # La réponse LATE a la structure : {"post": {...}, "message": "..."}
            post_data = res_data.get('post', res_data)
            post_id   = post_data.get('_id', res_data.get('id', ''))
            status    = post_data.get('status', '?')
            print(f"✅ Posté avec succès sur Late ! ID: {post_id} | Statut: {status}")

            try:
                platforms = post_data.get('platforms', [])
                if platforms:
                    p_data   = platforms[0].get('platformSpecificData', {})
                    pub_id   = p_data.get('tiktokPublishId', '')
                    username = p_data.get('__usernameSnapshot', '')
                    if pub_id and username:
                        print(f"ℹ️ TikTok upload en cours : @{username} | publishId: {pub_id}")
            except Exception:
                pass

            # Retourne le post_id pour permettre le polling de l'URL TikTok
            return post_id or True
        else:
            print("❌ L'API Late a renvoyé une erreur :", res_data)
            if isinstance(res_data, dict) and "limit reached" in str(res_data.get("error", "")).lower():
                return "QUOTA_EXCEEDED"
            return False
            
    except Exception as e:
        print("❌ Erreur lors de l'appel API Late :", e)
        return False


def _extract_tiktok_url(platform_data: dict) -> str | None:
    """
    Extrait l'URL TikTok depuis les donnees d'une plateforme LATE.

    Ordre de priorite :
    1. Champs URL directs (platformPostUrl, postUrl, shareUrl...)
    2. Scan de platformSpecificData pour URLs tiktok.com/video/
    3. platformPostId purement numerique (LATE le met à jour une fois
       que TikTok confirme l'upload, de 'v_pub_url~v2-xxx' → '76146...')

    On NE parse PAS le format 'v_pub_url~v2-1.xxx' : il donne un ID faux.
    Si platformPostId est encore en format v_pub_url~..., on retourne None
    pour que le polling continue jusqu'a ce que LATE mette a jour l'ID.
    """
    # 1. Champs URL directs
    direct = (
        platform_data.get("platformPostUrl")
        or platform_data.get("postUrl")
        or platform_data.get("url")
        or platform_data.get("shareUrl")
        or platform_data.get("link")
    )
    if direct and "tiktok.com" in str(direct):
        return direct

    # 2. Scan de platformSpecificData pour URLs tiktok.com/video/
    psd = platform_data.get("platformSpecificData", {})
    for val in psd.values():
        if isinstance(val, str) and "tiktok.com" in val and "/video/" in val:
            return val

    # 3. platformPostId numerique pur → LATE l'a mis à jour apres confirmation TikTok
    pub_id   = platform_data.get("platformPostId", "")
    username = psd.get("tiktokUsername") or psd.get("__usernameSnapshot", "")
    if pub_id and pub_id.isdigit() and len(pub_id) >= 15 and username:
        return f"https://www.tiktok.com/@{username}/video/{pub_id}"

    # platformPostId encore au format v_pub_url~v2-xxx → on attend
    return None


def fetch_and_track_tiktok_url(post_id: str, search_query: str, max_wait_sec: int = 900, account_name: str = ""):
    """
    Poll LATE API toutes les 30s pendant max_wait_sec pour recuperer
    l'URL TikTok via GET /api/v1/analytics/posts/{post_id}
    (champ platformPostUrl), puis l'ajoute au tracking.json.
    """
    print(f"⏳ Polling LATE pour URL TikTok (max {max_wait_sec}s, toutes les 30s)...")
    interval   = 30
    elapsed    = 0
    first_poll = True
    headers    = {"Authorization": f"Bearer {LATE_API_KEY}"}

    while elapsed < max_wait_sec:
        time.sleep(interval)
        elapsed += interval
        try:
            # 1) Endpoint analytics → contient platformPostUrl
            resp_analytics = requests.get(
                f"https://getlate.dev/api/v1/analytics/posts/{post_id}",
                headers=headers, verify=False, timeout=15
            )
            if resp_analytics.ok:
                analytics_data = resp_analytics.json()
                if first_poll:
                    print(f"🔍 [DEBUG analytics] {json.dumps(analytics_data, indent=2, ensure_ascii=False)[:2000]}")
                    first_poll = False
                tiktok_url = analytics_data.get("platformPostUrl")
                if tiktok_url and "tiktok.com" in str(tiktok_url):
                    print(f"🔗 URL TikTok (analytics) : {tiktok_url}")
                    add_to_tracking(tiktok_url, search_query, account_name)
                    return tiktok_url

            # 2) Fallback : endpoint posts standard
            resp_post = requests.get(
                f"https://getlate.dev/api/v1/posts/{post_id}",
                headers=headers, verify=False, timeout=15
            )
            if resp_post.ok:
                data      = resp_post.json()
                if first_poll:
                    print(f"🔍 [DEBUG posts] {json.dumps(data, indent=2, ensure_ascii=False)[:2000]}")
                    first_poll = False
                post_data = data.get("post", data)
                platforms = post_data.get("platforms", [])
                if platforms:
                    p   = platforms[0]
                    url = (
                        p.get("platformPostUrl")
                        or p.get("postUrl")
                        or p.get("shareUrl")
                        or p.get("link")
                    )
                    if url and "tiktok.com" in str(url):
                        print(f"🔗 URL TikTok (posts) : {url}")
                        add_to_tracking(url, search_query, account_name)
                        return url
                    # Cherche dans platformSpecificData
                    psd = p.get("platformSpecificData", {})
                    for val in psd.values():
                        if isinstance(val, str) and "tiktok.com" in val and "/video/" in val:
                            print(f"🔗 URL TikTok (psd) : {val}")
                            add_to_tracking(val, search_query, account_name)
                            return val

            print(f"⏳ ({elapsed}s/{max_wait_sec}s) URL TikTok pas encore disponible...")

        except Exception as e:
            print(f"⚠️ Polling LATE : {e}")

    # ── Retry unique après expiration du polling ──────────────────────────────
    print(f"⚠️ URL TikTok non disponible apres {max_wait_sec}s — 1 dernier essai...")
    try:
        resp_retry = requests.get(
            f"https://getlate.dev/api/v1/analytics/posts/{post_id}",
            headers={"Authorization": f"Bearer {LATE_API_KEY}"},
            verify=False, timeout=15
        )
        if resp_retry.ok:
            retry_data = resp_retry.json()
            tiktok_url = retry_data.get("platformPostUrl")
            if tiktok_url and "tiktok.com" in str(tiktok_url):
                print(f"🔗 URL TikTok (retry final) : {tiktok_url}")
                add_to_tracking(tiktok_url, search_query, account_name)
                return tiktok_url
    except Exception as e:
        print(f"⚠️ Retry final échoué : {e}")
    print(f"❌ URL TikTok non disponible après {max_wait_sec}s + retry — tracking non ajouté.")
    return None

# -------- Telegram --------

def _tg_raw_send(token: str, chat_id: str, video_path: str, caption: str) -> bool:
    """
    Envoi brut d'une vidéo Telegram vers UN chat_id donné.
    Retourne True si succès.
    """
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    try:
        with open(video_path, 'rb') as f:
            response = requests.post(
                url,
                files={'video': f},
                data={'chat_id': chat_id, 'caption': caption, 'parse_mode': 'Markdown'},
                timeout=120
            )
        if response.ok:
            return True
        print(f"   ⚠️ Telegram HTTP {response.status_code} : {response.text[:200]}")
        return False
    except requests.exceptions.Timeout:
        print("   ❌ Timeout Telegram")
        return False
    except Exception as e:
        print(f"   ❌ Exception Telegram : {e}")
        return False


def _tg_send_text(token: str, chat_id: str, text: str):
    """Envoi d'un message texte Telegram."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception:
        pass


def send_telegram_video(video_path, caption, client_info: dict = None):
    """
    Envoi double systématique :
      - Vers le CLIENT (uniquement sa vidéo, caption propre, sans stats)
      - Vers l'ADMIN (toutes les vidéos + stats détaillées)

    Args:
        video_path  : chemin vers la vidéo
        caption     : description/hashtags générés par Groq
        client_info : dict optionnel avec infos du client
                      {'name', 'plan_label', 'usage_today', 'videos_per_day',
                       'telegram_chat_id', 'license_key'}
                      None = usage admin direct (1 seul envoi)
    """
    print("📧 Envoi Telegram...")
    token    = os.getenv("TELEGRAM_BOT_TOKEN")
    admin_id = os.getenv("TELEGRAM_CHAT_ID")   # Toujours TON chat_id (le tien)

    if not token:
        print("❌ TELEGRAM_BOT_TOKEN manquant")
        return
    if not os.path.exists(video_path):
        print(f"❌ Fichier introuvable : {video_path}")
        return

    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    if file_size_mb > 50:
        print(f"⚠️ Fichier {file_size_mb:.1f} MB — limite Telegram 50 MB, l'envoi risque d'échouer")

    # ---- Cas 1 : vidéo générée pour un CLIENT ----
    if client_info and client_info.get('telegram_chat_id'):
        client_chat_id = client_info['telegram_chat_id']

        # 1a. Envoi au CLIENT — vidéo seule, caption propre (comme si c'était son propre bot)
        print(f"   📤 → Client '{client_info.get('name', '?')}' ({client_chat_id})...")
        ok_client = _tg_raw_send(token, client_chat_id, video_path, caption)
        client_status = "\u2705 Client OK" if ok_client else "\u274c Client échec"
        print(f"   {client_status}")

        # 1b. Envoi à l'ADMIN — même vidéo + stats complètes
        if admin_id:
            envoi_status = "\u2705 Envoyé au client" if ok_client else "\u274c Échec envoi client (pas de TG lié ?)"
            admin_caption = (
                f"🎞️ *Nouvelle vidéo générée*\n"
                f"\n"
                f"👤 Client   : `{client_info.get('name', '?')}`\n"
                f"📦 Plan     : `{client_info.get('plan_label', '?')}`\n"
                f"🎬 Quota    : `{client_info.get('usage_today', '?')}/{client_info.get('videos_per_day', '?')}` vidéos aujourd'hui\n"
                f"📌 Clé      : `{client_info.get('license_key', '?')}`\n"
                f"📁 Taille   : `{file_size_mb:.1f} MB`\n"
                f"\n"
                f"{envoi_status}\n"
                f"\n"
                f"📝 *Caption générée :*\n{caption[:300]}"
            )
            print(f"   📤 → Admin ({admin_id}) avec stats...")
            ok_admin = _tg_raw_send(token, admin_id, video_path, admin_caption)
            admin_status = "\u2705 Admin OK" if ok_admin else "\u274c Admin échec"
            print(f"   {admin_status}")

    # ---- Cas 2 : usage ADMIN direct (pas de client) ----
    else:
        if not admin_id:
            print("❌ TELEGRAM_CHAT_ID manquant dans .env")
            return
        print(f"   📤 → Admin ({admin_id}) [usage direct]...")
        ok = _tg_raw_send(token, admin_id, video_path, caption)
        direct_status = "\u2705 OK" if ok else "\u274c Échec"
        print(f"   {direct_status}")


# -------- Main --------

def main():
    output_folder = "clips_downloaded"
    fichier_tracking = "downloaded_clips.txt"

    os.makedirs(output_folder, exist_ok=True)
    
    # 1. Charger les IDs déjà faits
    deja_vus = charger_clips_deja_telecharges(fichier_tracking)
    print(f"📂 {len(deja_vus)} clips déjà traités trouvés dans l'historique.")

    os.makedirs(output_folder, exist_ok=True)

    access_token = get_access_token()
    
    broadcaster_id = None
    game_id = None

    print(f"🔍 Recherche en mode : {SEARCH_TYPE.upper()} ('{SEARCH_QUERY}')")

    if SEARCH_TYPE == "channel":
        broadcaster_id = get_user_id(access_token, SEARCH_QUERY)
        if not broadcaster_id:
            print(f"❌ Streamer '{SEARCH_QUERY}' non trouvé.")
            return 0
    elif SEARCH_TYPE == "game":
        game_id = get_game_id(access_token, SEARCH_QUERY)
        if not game_id:
            print(f"❌ Jeu '{SEARCH_QUERY}' non trouvé.")
            return 0
    else:
        print("❌ Mauvais SEARCH_TYPE (mettre 'channel' ou 'game')")
        return 0

    # Calcul de la date de départ (started_at) selon la période choisie
    started_at_str = None
    if SEARCH_PERIOD == "24h":
        started_at_str = (datetime.utcnow() - timedelta(days=1)).isoformat() + 'Z'
    elif SEARCH_PERIOD == "7d":
        started_at_str = (datetime.utcnow() - timedelta(days=7)).isoformat() + 'Z'
    elif SEARCH_PERIOD == "30d":
        started_at_str = (datetime.utcnow() - timedelta(days=30)).isoformat() + 'Z'
    elif SEARCH_PERIOD == "all":
        started_at_str = None # Pas de filtre de date
    else:
        print(f"⚠️ Période '{SEARCH_PERIOD}' inconnue, utilisation de 24h par défaut.")
        started_at_str = (datetime.utcnow() - timedelta(days=1)).isoformat() + 'Z'

    print(f"📅 Période de recherche : {SEARCH_PERIOD.upper()}")

    # On récupère une LISTE de candidats (non téléchargés)
    clips_data = get_clips(
        access_token, 
        broadcaster_id=broadcaster_id, 
        game_id=game_id,
        first=max(10, min(1000, MAX_API_CLIPS)),
        started_at=started_at_str
    )
    # ── Fallback automatique si pas assez de clips ──────────────────────────
    # Cas 1 : 0 clips retournés par l'API en 24h → on essaie directement 7j
    if not clips_data and SEARCH_PERIOD == "24h":
        print("⚠️ 0 clip en 24h — fallback automatique 7 jours...")
        started_at_7d = (datetime.utcnow() - timedelta(days=7)).isoformat() + 'Z'
        clips_data = get_clips(
            access_token,
            broadcaster_id=broadcaster_id,
            game_id=game_id,
            first=max(10, min(1000, MAX_API_CLIPS)),
            started_at=started_at_7d
        ) or []
        if CLIP_LANGUAGE and clips_data:
            clips_data = [c for c in clips_data if c.get('language') == CLIP_LANGUAGE]
        if clips_data:
            print(f"✅ Fallback 7j : {len(clips_data)} clips trouvés")
        else:
            print("⚠️ Toujours 0 clip en 7j — fallback 30 jours...")
            started_at_30d = (datetime.utcnow() - timedelta(days=30)).isoformat() + 'Z'
            clips_data = get_clips(
                access_token,
                broadcaster_id=broadcaster_id,
                game_id=game_id,
                first=max(10, min(1000, MAX_API_CLIPS)),
                started_at=started_at_30d
            ) or []
            if CLIP_LANGUAGE and clips_data:
                clips_data = [c for c in clips_data if c.get('language') == CLIP_LANGUAGE]
            if clips_data:
                print(f"✅ Fallback 30j : {len(clips_data)} clips trouvés")

    if not clips_data:
        print("❌ Aucun clip trouvé (24h + 7j + 30j).")
        return 0

    # Filtrage Langue (appliqué dans tous les cas)
    if CLIP_LANGUAGE:
        before_count = len(clips_data)
        clips_data = [c for c in clips_data if c.get('language') == CLIP_LANGUAGE]
        if before_count != len(clips_data):
            print(f"🔎 Filtrage par langue : {CLIP_LANGUAGE} ({len(clips_data)}/{before_count} clips gardés)")

        if not clips_data:
            print("❌ Aucun clip ne correspond à la langue demandée.")
            return 0

    # Cas 2 : quelques clips en 24h mais pas assez de nouveaux → on élargit à 7j, puis 30j
    MIN_CLIPS_FOR_VIDEO = 2
    clips_nouveaux = [c for c in clips_data if c['id'] not in deja_vus or IGNORE_HISTORY]
    if len(clips_nouveaux) < MIN_CLIPS_FOR_VIDEO and SEARCH_PERIOD == "24h":
        print(f"⚠️ Seulement {len(clips_nouveaux)} nouveau(x) clip(s) en 24h — fallback 7 jours...")
        started_at_7d = (datetime.utcnow() - timedelta(days=7)).isoformat() + 'Z'
        clips_7d = get_clips(
            access_token,
            broadcaster_id=broadcaster_id,
            game_id=game_id,
            first=max(10, min(1000, MAX_API_CLIPS)),
            started_at=started_at_7d
        )
        if clips_7d:
            if CLIP_LANGUAGE:
                clips_7d = [c for c in clips_7d if c.get('language') == CLIP_LANGUAGE]
            # Fusion sans doublons
            existing_ids = {c['id'] for c in clips_data}
            clips_7d_new = [c for c in clips_7d if c['id'] not in existing_ids]
            clips_data   = clips_data + clips_7d_new
            print(f"✅ Fallback 7j : {len(clips_7d_new)} clips supplémentaires ajoutés ({len(clips_data)} total)")
        else:
            print("⚠️ Aucun clip supplémentaire trouvé en 7j non plus.")

        # Re-vérifier s'il y a assez de nouveaux clips après le fallback 7j
        clips_nouveaux_apres_7d = [c for c in clips_data if c['id'] not in deja_vus or IGNORE_HISTORY]
        if len(clips_nouveaux_apres_7d) < MIN_CLIPS_FOR_VIDEO:
            print(f"⚠️ Toujours insuffisant ({len(clips_nouveaux_apres_7d)} nouveaux) après 7j — fallback 30 jours...")
            started_at_30d = (datetime.utcnow() - timedelta(days=30)).isoformat() + 'Z'
            clips_30d = get_clips(
                access_token,
                broadcaster_id=broadcaster_id,
                game_id=game_id,
                first=max(10, min(1000, MAX_API_CLIPS)),
                started_at=started_at_30d
            )
            if clips_30d:
                if CLIP_LANGUAGE:
                    clips_30d = [c for c in clips_30d if c.get('language') == CLIP_LANGUAGE]
                existing_ids_before_30d = {c['id'] for c in clips_data}
                clips_30d_new = [c for c in clips_30d if c['id'] not in existing_ids_before_30d]
                clips_data = clips_data + clips_30d_new
                print(f"✅ Fallback 30j : {len(clips_30d_new)} clips supplémentaires ajoutés ({len(clips_data)} total)")
            else:
                print("⚠️ Aucun clip supplémentaire trouvé en 30j non plus.")

    # Trier par score de viralité (buzz actuel > vues historiques)
    if VIRAL_BRAIN_AVAILABLE:
        clips_data = sorted(clips_data, key=get_virality_score_for_clip, reverse=True)
        print("🏆 Clips triés par score viral (vues/heure)")
    else:
        clips_data = sorted(clips_data, key=lambda c: c['view_count'], reverse=True)

    groupes = []
    idx_clip = 0  # pointeur dans la liste des clips API

    for video_index in range(1, NB_VIDEOS + 1):
        courant = []          # liste des chemins des clips
        durations_map = {}    # dict {path -> durée} pour éviter les ffprobe en double
        total = 0.0
        current_video_title = "Best Of Twitch"

        # Ajoute des clips tant qu'on n'a pas atteint la durée minimale
        while idx_clip < len(clips_data):
            clip = clips_data[idx_clip]
            idx_clip += 1

            clip_id = clip['id']
            clip_title = clip.get('title', 'SansTitre') # Pour info si besoin
            
            # CHECK DOUBLON
            if not IGNORE_HISTORY and clip_id in deja_vus:
                print(f"🚫 Clip déjà traité (SKIP) : {clip_id}")
                continue

            clip_url = clip['url']
            file_path = os.path.join(output_folder, f"{clip_id}.mp4")

            # Télécharge uniquement si nécessaire
            if not os.path.exists(file_path):
                ok = telecharger_clip(clip_url, file_path, clip.get('thumbnail_url', ''))
                if not ok:
                    continue  # essai clip suivant si échec

            # --- Détecteur Anti-Copyright Shazam ---
            is_copyrighted, copyright_title, copyright_artist = check_copyright_music(file_path)
            if is_copyrighted:
                print(f"   ⚠️ EXCLU (main.py) : Clip contenant '{copyright_title}' de '{copyright_artist}' (Copyright)")
                ajouter_clip_telecharge(fichier_tracking, clip_id, clip_title)
                deja_vus.add(clip_id)
                try: os.remove(file_path)
                except: pass
                continue

            # Mesure la durée
            try:
                d, _, _ = get_video_info(file_path)
            except Exception:
                continue  # clip illisible, on passe
            
            # Si c'est le premier clip du montage, on garde son titre comme titre principal
            if not courant:
                current_video_title = clip_title

            courant.append(file_path)
            durations_map[file_path] = d
            total += d
            
            # Enregistrer immédiatement pour ne pas le refaire au prochain run
            ajouter_clip_telecharge(fichier_tracking, clip_id, clip_title)
            deja_vus.add(clip_id)

            # Mode YouTube : 1 seul clip suffit, on sort immédiatement
            if YOUTUBE_MODE:
                print(f"▶️ Mode YouTube Short : 1 clip ({d:.1f}s), pas de durée minimale")
                break

            # Mode normal : on continue tant qu'on n'a pas atteint la durée cible
            if total >= TARGET_SECONDS:
                break

        # Vérification selon le mode
        if not courant:
            print(f"⛔ Aucun clip valide trouvé pour la vidéo {video_index}.")
            break

        if not YOUTUBE_MODE and total < TARGET_SECONDS:
            print(f"⛔ Pas assez de contenu pour fabriquer la vidéo {video_index} (manque {int(TARGET_SECONDS - total)} s).")
            break

        groupes.append({'paths': courant, 'title': current_video_title, 'durations': durations_map})


    if not groupes:
        err_msg = f"Pas assez de clips pour créer une vidéo complète (fallback 24h+7j+30j épuisé)"
        print(f"❌ {err_msg}")
        canal_label = os.getenv("SCHEDULER_CHANNEL_LABEL", SEARCH_QUERY)
        log_error(canal_label, "NO_CLIPS", err_msg)
        return 0

    # Génération + envoi
    # --- MULTI-PROCESSING OVERHAUL ---
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")  # Timestamp unique par run
    success_count = 0
    for idx, video_data in enumerate(groupes, start=1):
        # --- DEBUT TIMER ---
        start_time = time.time()
        # -------------------

        groupe = video_data['paths']
        video_title = video_data['title']
        clip_durations = video_data.get('durations', {})
        
        print(f"\n===== Génération de la vidéo {idx}/{len(groupes)} (≥ {TARGET_SECONDS}s) =====")
        first_clip = groupe[0]
        temp_frame = first_clip.replace(".mp4", f"_frame_{idx}.jpg")
        if not extraire_image(first_clip, temp_frame):
            print("❌ Erreur extraction image.")
            continue

        crop_params = None  # 100% Désactivé : toujours le format fond flou unique (pas de split-screen)
        # Nom unique : inclut timestamp du run + index pour éviter les écrasements
        output_final = os.path.join(output_folder, f"tiktok_final_{run_ts}_{idx}.mp4")
        
        montage_tiktok(groupe, None, output_final, clip_durations=clip_durations)

        # Génération de la description avec Groq + Viral Brain
        canal_label = os.getenv("SCHEDULER_CHANNEL_LABEL", SEARCH_QUERY)
        generated_caption = generate_metadata(SEARCH_QUERY, video_title, canal_label=canal_label)

        # Génération du premier commentaire Groq (question engageante citant le streamer)
        first_comment = generate_first_comment(SEARCH_QUERY, video_title)

        # Envoi Telegram
        if SEND_TELEGRAM:
            client_tg_id = TELEGRAM_CHAT_ID_OVERRIDE

            client_info = None
            if client_tg_id:
                try:
                    from license_manager import validate_license, consume_license
                    lic_data = validate_license(_CURRENT_LICENSE_KEY) if _CURRENT_LICENSE_KEY else {}
                    client_info = {
                        'name':         lic_data.get('client_name', 'Client'),
                        'plan_label':   lic_data.get('plan_label', '?'),
                        'usage_today':  lic_data.get('usage_today', '?'),
                        'videos_per_day': lic_data.get('videos_per_day', '?'),
                        'telegram_chat_id': client_tg_id,
                        'license_key':  _CURRENT_LICENSE_KEY,
                    }
                    consume_license(_CURRENT_LICENSE_KEY)
                except Exception:
                    client_info = {'telegram_chat_id': client_tg_id, 'name': 'Client', 'plan_label': '?',
                                   'usage_today': '?', 'videos_per_day': '?', 'license_key': ''}

            send_telegram_video(output_final, generated_caption, client_info=client_info)
        else:
            print("📧 Envoi Telegram désactivé (SEND_TELEGRAM = False)")

        # Si Auto-post activé
        if AUTO_POST:
            public_url = upload_to_late_cdn(output_final)
            if public_url:
                post_result = publish_to_late_api(public_url, generated_caption, first_comment=first_comment)
                if post_result == "QUOTA_EXCEEDED":
                    err_msg = "Échec publication Late : QUOTA MENSUEL ATTEINT"
                    print(f"❌ {err_msg}")
                    log_error(canal_label, "API_QUOTA", err_msg)
                    success_count = -2
                elif post_result:
                    print("✅ Vidéo publiée via CDN Late !")
                    success_count += 1
                    if isinstance(post_result, str) and len(post_result) > 5:
                        canal_label_for_tracking = os.getenv("SCHEDULER_CHANNEL_LABEL", SEARCH_QUERY)
                        account_name_for_tracking = os.getenv("SCHEDULER_ACCOUNT_NAME", "")
                        is_youtube_platform = LATE_PLATFORM == "youtube"
                        if is_youtube_platform:
                            # Pour YouTube : on skip le polling TikTok (qui échouerait toujours)
                            # L'URL YouTube est déjà dans la réponse de Late (platformPostUrl)
                            print("▶️ Plateforme YouTube : polling TikTok ignoré (non applicable).")
                        else:
                            # Pour TikTok : polling normal
                            fetch_and_track_tiktok_url(post_result, canal_label_for_tracking, account_name=account_name_for_tracking)
                    else:
                        print("ℹ️ post_id non disponible — tracking ignoré.")
                else:
                    err_msg = "Échec publication Late (API Late a renvoyé une erreur)"
                    print(f"❌ {err_msg}")
                    log_error(canal_label, "PUBLICATION", err_msg)
            else:
                err_msg = "Échec upload CDN Late — vidéo non postée"
                print(f"❌ {err_msg}")
                log_error(canal_label, "CDN_UPLOAD", err_msg)
        elif YOUTUBE_MODE:
            print(f"▶️ Mode YouTube Short : pas de post TikTok.")
            print(f"💾 Vidéo YouTube Short sauvegardée : {output_final}")
        else:
            print(f"💾 Vidéo sauvegardée localement uniquement : {output_final}")
            print("🚫 Auto-post désactivé (AUTO_POST = False).")

        # 🧹 Nettoyage
        print(f"🧹 Suppression des {len(groupe)} clips sources...")
        for clip_path in groupe:
            try:
                os.remove(clip_path)
                print(f"   🗑️ Supprimé : {clip_path}")
            except Exception as e:
                print(f"   ❌ Erreur suppression {clip_path} : {e}")

        if os.path.exists(temp_frame):
            try:
                os.remove(temp_frame)
            except:
                pass
        
        # --- FIN TIMER & SAUVEGARDE ---
        end_time = time.time()
        duration = end_time - start_time
        final_vid_duration, _, _ = get_video_info(output_final)
        ai_title = generated_caption.split('\n')[0].strip() if generated_caption else video_title

        save_creation_log(SEARCH_QUERY, ai_title, os.path.basename(output_final), duration, final_vid_duration)

    if AUTO_POST:
        if success_count == -2:
            return -2
        return success_count if success_count > 0 else -1
    return len(groupes)

def executer_pipeline(config_user):
    """
    Cette fonction est le point d'entrée pour l'interface Web (Flask).
    Elle met à jour les variables globales de configuration avant de lancer main().
    """
    global SEARCH_QUERY, SEARCH_TYPE, SEARCH_PERIOD, NB_VIDEOS, CLIP_LANGUAGE
    global AUTO_POST, TARGET_SECONDS, SEND_TELEGRAM, YOUTUBE_MODE
    global PUBLISH_NOW, SCHEDULE_HOUR, SCHEDULE_MINUTE, TIKTOK_ACCOUNT_ID
    global TELEGRAM_CHAT_ID_OVERRIDE, _CURRENT_LICENSE_KEY, LATE_PLATFORM

    # On écrase les configurations par défaut avec celles reçues du Web
    if 'query' in config_user: SEARCH_QUERY = config_user['query']
    if 'type' in config_user: SEARCH_TYPE = config_user['type']
    if 'period' in config_user: SEARCH_PERIOD = config_user['period']
    if 'nb_videos' in config_user:
        NB_VIDEOS = int(config_user['nb_videos'])
        # Recalcule MAX_API_CLIPS dynamiquement sinon on reste à la valeur initiale
        global MAX_API_CLIPS
        MAX_API_CLIPS = NB_VIDEOS * 250
    if 'lang' in config_user: CLIP_LANGUAGE = config_user['lang']
    if 'target_seconds' in config_user:
        desired_output_secs = int(config_user['target_seconds'])
        # L'interface envoie la durée FINALE souhaitée (ex: 60s).
        # TARGET_SECONDS = durée de clips BRUTS à assembler → compense speedup + trim
        trim_budget = ANTI_DETECT_TRIM_SEC * 2 * 4  # ~4 clips en moyenne = 4s trimmés
        TARGET_SECONDS = int(desired_output_secs * ANTI_DETECT_SPEEDUP) + int(trim_budget) + 3
        print(f"🎯 Durée souhaitée : {desired_output_secs}s → Target brut calculé : {TARGET_SECONDS}s")
    
    # --- Options Avancées ---
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

    if 'platform' in config_user:
        LATE_PLATFORM = config_user['platform']

    # --- Sélection dynamique du compte TikTok ---
    # L'interface envoie "HAWAII" ou "BLACKGEN". On doit trouver la variable ENV correspondante.
    selected_key = config_user.get('tiktok_account_key')
    if selected_key:
        prefix = "YOUTUBE_ID_" if LATE_PLATFORM == "youtube" else "TIKTOK_ACCOUNT_ID_"
        env_var_name = f"{prefix}{selected_key}"
        found_id = os.getenv(env_var_name)
        if found_id:
            TIKTOK_ACCOUNT_ID = found_id
            print(f"👤 Compte {LATE_PLATFORM} sélectionné : {selected_key} (ID: {found_id})")
        else:
            print(f"⚠️ Variable d'environnement {env_var_name} non trouvée. Utilisation du défaut.")

    # --- Mode YouTube ---
    if 'youtube_mode' in config_user:
        YOUTUBE_MODE = bool(config_user['youtube_mode'])
        if YOUTUBE_MODE:
            NB_VIDEOS = 1
            LATE_PLATFORM = "youtube"
            print("▶️ MODE YOUTUBE SHORT activé (1 clip, pas de durée min, plateforme youtube)")

    # --- Telegram client override (depuis la licence) ---
    # Si la licence du client contient un telegram_chat_id, ses vidéos lui sont envoyées à LUI
    # Sinon, pas envoyées sur Telegram (sauf si c'est toi qui utilises ton propre système)
    client_tg = config_user.get('client_telegram_chat_id', '').strip()
    _CURRENT_LICENSE_KEY = config_user.get('license_key', '').strip()
    if client_tg:
        TELEGRAM_CHAT_ID_OVERRIDE = client_tg
        print(f"📢 Telegram redirigé vers le client : chat_id {client_tg}")
    else:
        TELEGRAM_CHAT_ID_OVERRIDE = None  # Utilise le .env (ton propre Telegram)

    if 'ignore_history' in config_user:
        IGNORE_HISTORY = bool(config_user['ignore_history'])
        if IGNORE_HISTORY:
            print("📜 Mode : IGNORER L'HISTORIQUE (autorise les doublons)")

    # Log pour vérifier dans la console Docker
    mode_label = "▶️ YOUTUBE" if YOUTUBE_MODE else "📦 TIKTOK"
    tg_dest    = f"Client ({client_tg})" if client_tg else "Admin (.env)"
    print(f"🔄 PIPELINE : {SEARCH_QUERY} | Mode: {mode_label} | AutoPost: {AUTO_POST} | Telegram → {tg_dest}")
    if AUTO_POST and not PUBLISH_NOW:
        print(f"🕒 Programmation définie pour : {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}")

    # On lance la fonction principale existante
    return main()

if __name__ == "__main__":
    main()