import os
import sys
import subprocess
import cv2
import ftplib
import imageio_ffmpeg
import requests
import ftplib
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
TARGET_SECONDS = 60  # << Durée MINIMALE par vidéo
# SEARCH CONFIG
SEARCH_QUERY = "anyme023"   # Nom du streamer OU du jeu
SEARCH_TYPE = "channel"       # 'channel' ou 'game'
SEARCH_PERIOD = "24h"          # '24h', '7d', '30d', 'all'
CLIP_LANGUAGE = "fr"          # 'fr', 'en', etc. ou "" pour tout (ex: None)

# FTP CONFIG
FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
REMOTE_DIR = "www"
BASE_URL = "https://silvertiti.fr"

# POSTING CONFIG (Late API / TikTok)
LATE_API_KEY = os.getenv("LATE_API_KEY")
TIKTOK_ACCOUNT_ID = os.getenv("TIKTOK_ACCOUNT_ID_HAWAII") # HAWAIISERVICE
#TIKTOK_ACCOUNT_ID = os.getenv("TIKTOK_ACCOUNT_ID_BLACKGEN") # BlackGEN


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
SEND_TELEGRAM = True # True = Envoi sur Telegram, False = Non

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
    # Use python -m streamlink to ensure we use the installed module even if not in PATH
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
    # FFmpeg écrit les infos sur stderr
    result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    
    duration = 0.0
    width = 0
    height = 0
    
    # Parsing basique
    for line in result.stderr.split('\n'):
        line = line.strip()
        # Duration: 00:00:30.50, ...
        if line.startswith("Duration:"):
            try:
                # Ex: Duration: 00:00:10.54, start: ...
                time_str = line.split(",")[0].split(" ")[1]
                h, m, s = time_str.split(":")
                duration = int(h) * 3600 + int(m) * 60 + float(s)
            except:
                pass
        
        # Stream #0:0(und): Video: h264 (High) (avc1 / 0x31637661), yuv420p, 1920x1080 [SAR 1:1 DAR 16:9], ...
        if "Video:" in line:
            try:
                # Recherche de la résolution (ex: 1920x1080)
                import re
                match = re.search(r'(\d{2,5})x(\d{2,5})', line)
                if match:
                    width = int(match.group(1))
                    height = int(match.group(2))
            except:
                pass
                
    return duration, width, height

# -------- Montage FFmpeg --------

# -------- Montage FFmpeg --------

def montage_tiktok(clips_paths, crop_params, output_path):
    print(f"🎞️ Montage final (FFmpeg - Safe Mode) : {output_path}")
    
    if not clips_paths:
        return

    ffmpeg = get_ffmpeg_cmd()
    
    # On récupère les infos du premier clip pour reference (dimensions)
    _, src_w, src_h = get_video_info(clips_paths[0])
    if src_w == 0 or src_h == 0:
        src_w, src_h = 1920, 1080 # Fallback

    # Construction de la commande
    # On passe TOUS les clips en input pour utiliser le filtre "concat" (plus sûr que -c copy)
    cmd_inputs = []
    for path in clips_paths:
        cmd_inputs.extend(["-i", path])

    # Préparation du filtre concat
    # Ex: [0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[joined_v][joined_a]
    concat_segments = ""
    for i in range(len(clips_paths)):
        concat_segments += f"[{i}:v][{i}:a]"
    
    filter_concat = f"{concat_segments}concat=n={len(clips_paths)}:v=1:a=1[joined_v][joined_a]"

    # Ensuite on applique la logique de crop/montage sur [joined_v]
    # On remplace [0:v] par [joined_v] dans la logique précédente
    
    filter_processing = ""

    if crop_params:
        # --- CAS AVEC WEBCAM ---
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
        # --- CAS SANS WEBCAM ---
        filter_processing = (
            f"[joined_v]split=2[bg][fg];"
            f"[bg]scale=-2:1280,crop=720:1280,boxblur=20:10[bg_blurred];"
            f"[fg]scale=720:-2[fg_scaled];"
            f"[bg_blurred][fg_scaled]overlay=(W-w)/2:(H-h)/2[outv]"
        )

    # Assemblage complet du filter_complex
    full_filter = f"{filter_concat};{filter_processing}"

    # Commande finale
    cmd = [ffmpeg]
    cmd.extend(cmd_inputs)
    cmd.extend([
        "-filter_complex", full_filter,
        "-map", "[outv]", 
        "-map", "[joined_a]", # On utilise l'audio concaténé
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", # Important pour compatibilité player
        "-r", "60", # Force 60fps constant pour éviter sync issues
        "-y", output_path
    ])
    
    print("   ⚙️ Encodage en cours (Concat + Montage)...")
    # print("   DEBUG CMD:", " ".join(cmd)) # Décommenter pour debug
    
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
        # On nettoie les lignes (virer \n et espaces)
        return set(line.strip() for line in f if line.strip())

def ajouter_clip_telecharge(fichier_txt, clip_id, clip_title):
    with open(fichier_txt, "a", encoding="utf-8") as f:
        # On peut stocker ID et Titre pour la lisibilité
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

INSTRUCTIONS :
1. Analyse le NOM DU STREAMER et le TITRE DU CLIP fournis.
2. Génère un TITRE CLICKBAIT (Court, mots-clés en MAJUSCULES, 2-3 emojis).
3. Génère une liste de HASHTAGS. Tu dois mélanger des hashtags génériques (comme #TwitchFR #BestOfTwitch) ET des hashtags précis liés au sujet du clip (ex: le nom du jeu, le thème "CultureG", "Minecraft", etc.).

FORMAT DE RÉPONSE STRICT (2 lignes maximum, pas de guillemets, pas de préfixe "Titre:") :
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
                    "content": f"Streamer: {streamer_name}Titre du clip: {titre_clip_twitch}"
                }
            ],
            temperature=0.7,
            max_tokens=200,
            top_p=1,
            stream=False,
            stop=None
        )
        
        # Le contenu est dans completion.choices[0].message.content
        response_text = completion.choices[0].message.content.strip()
        lines = response_text.split('\n')
        
        # Nettoyage basique pour récupérer titre et hashtags
        titre = lines[0].strip() if len(lines) > 0 else "TITRE VIRAL GENERE"
        hashtags = lines[1].strip() if len(lines) > 1 else "#Viral #Twitch"
        
        # On combine pour la description finale
        final_caption = f"{titre}\n{hashtags}"
        print(f"✨ Métadonnées générées :\\n{final_caption}")
        return final_caption

    except Exception as e:
        print(f"❌ Erreur Groq : {e}")
        # Fallback si erreur
        return f"Clip de {streamer_name} ! 🎬 #TwitchFR #BestOf #Viral"

# -------- API Late --------

def publish_to_late_api(video_filename, caption_content):
    print("🚀 Préparation de la publication sur Late...")
    
    # URL publique du fichier sur le FTP
    video_url = f"{BASE_URL}/{video_filename}"
    
    url = 'https://getlate.dev/api/v1/posts'
    headers = {
        'Authorization': f'Bearer {LATE_API_KEY}',
        'Content-Type': 'application/json'
    }

    # Préparation du payloads
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

    # Si on ne publie pas immédiatement, on ajoute la date de programmation
    if not PUBLISH_NOW:
        # Calcul de la date de programmation : Aujourd'hui à l'heure définie
        now = datetime.now()
        scheduled_date = now.replace(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE, second=0, microsecond=0)
        
        # Si la date programmée est déjà passée, on programme pour demain même heure 
        # (Optionnel, mais évite les erreurs d'API si on lance le script à 14h alors que SCHEDULE_HOUR est 12h)
        if scheduled_date < now:
             scheduled_date += timedelta(days=1)

        # Conversion en ISO 8601 avec fuseau horaire
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

    if not token or not chat_id:
        print("❌ Config Telegram manquante (TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID).")
        return

    url = f"https://api.telegram.org/bot{token}/sendVideo"
    
    try:
        with open(video_path, 'rb') as f:
            files = {'video': f}
            data = {
                'chat_id': chat_id, 
                'caption': caption,
                'parse_mode': 'Markdown' # ou HTML si besoin
            }
            response = requests.post(url, files=files, data=data)
            
        if response.ok:
            print("✅ Vidéo envoyée sur Telegram avec succès !")
        else:
            print(f"❌ Erreur Telegram : {response.text}")
    except Exception as e:
        print(f"❌ Exception lors de l'envoi Telegram : {e}")

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
    access_token = get_access_token()
    
    broadcaster_id = None
    game_id = None

    print(f"🔍 Recherche en mode : {SEARCH_TYPE.upper()} ('{SEARCH_QUERY}')")

    if SEARCH_TYPE == "channel":
        broadcaster_id = get_user_id(access_token, SEARCH_QUERY)
        if not broadcaster_id:
            print(f"❌ Streamer '{SEARCH_QUERY}' non trouvé.")
            return
    elif SEARCH_TYPE == "game":
        game_id = get_game_id(access_token, SEARCH_QUERY)
        if not game_id:
            print(f"❌ Jeu '{SEARCH_QUERY}' non trouvé.")
            return
    else:
        print("❌ Mauvais SEARCH_TYPE (mettre 'channel' ou 'game')")
        return

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
        first=max(10, min(100, MAX_API_CLIPS)),
        started_at=started_at_str
    )
    if not clips_data:
        print("❌ Aucun clip trouvé.")
        return

    # Filtrage Langue si demandé
    if CLIP_LANGUAGE:
        print(f"🔎 Filtrage par langue : {CLIP_LANGUAGE}")
        before_count = len(clips_data)
        clips_data = [c for c in clips_data if c.get('language') == CLIP_LANGUAGE]
        print(f"   (Reste {len(clips_data)} clips sur {before_count})")

        if not clips_data:
            print("❌ Aucun clip ne correspond à la langue demandée.")
            return

    # Trier par vues décroissantes (on veut les meilleurs d'abord)
    clips_data = sorted(clips_data, key=lambda c: c['view_count'], reverse=True)

    groupes = []
    idx_clip = 0  # pointeur dans la liste des clips API

    for video_index in range(1, NB_VIDEOS + 1):
        courant = []
        total = 0.0
        current_video_title = "Best Of Twitch" # Valeur par défaut

        # Ajoute des clips tant qu'on n'a pas atteint la durée minimale
        while total < TARGET_SECONDS and idx_clip < len(clips_data):
            clip = clips_data[idx_clip]
            idx_clip += 1

            clip_id = clip['id']
            clip_title = clip.get('title', 'SansTitre') # Pour info si besoin
            
            # CHECK DOUBLON
            if clip_id in deja_vus:
                print(f"🚫 Clip déjà traité (SKIP) : {clip_id}")
                continue

            clip_url = clip['url']
            file_path = os.path.join(output_folder, f"{clip_id}.mp4")

            # Télécharge uniquement si nécessaire
            if not os.path.exists(file_path):
                ok = telecharger_clip(clip_url, file_path)
                if not ok:
                    continue  # essai clip suivant si échec

            # Mesure la durée
            try:
                d, _, _ = get_video_info(file_path)
            except Exception:
                continue  # clip illisible, on passe
            
            # Si c'est le premier clip du montage, on garde son titre comme titre principal
            if not courant:
                current_video_title = clip_title

            courant.append(file_path)
            total += d
            
            # Enregistrer immédiatement pour ne pas le refaire au prochain run
            ajouter_clip_telecharge(fichier_tracking, clip_id, clip_title)
            deja_vus.add(clip_id)

        # Si on n'a pas réussi à atteindre la durée minimale, on s'arrête là (pas de vidéo incomplète)
        if total < TARGET_SECONDS:
            print(f"⛔ Pas assez de contenu pour fabriquer la vidéo {video_index} (manque {int(TARGET_SECONDS - total)} s).")
            break

        groupes.append({'paths': courant, 'title': current_video_title})

    if not groupes:
        print("❌ Pas assez de clips pour créer une vidéo complète.")
        return

    # Génération + envoi
    for idx, video_data in enumerate(groupes, start=1):
        groupe = video_data['paths']
        video_title = video_data['title']
        
        print(f"\\n===== Génération de la vidéo {idx}/{len(groupes)} (≥ {TARGET_SECONDS}s) =====")
        first_clip = groupe[0]
        temp_frame = first_clip.replace(".mp4", f"_frame_{idx}.jpg")
        if not extraire_image(first_clip, temp_frame):
            print("❌ Erreur extraction image.")
            continue

        crop_params = detecter_webcam(temp_frame)
        output_final = os.path.join(output_folder, f"tiktok_final_{idx}.mp4")
        montage_tiktok(groupe, crop_params, output_final)
        
        # Si Auto-post activé
        # Génération de la description avec Groq (toujours, peu importe AUTO_POST)
        generated_caption = generate_metadata(SEARCH_QUERY, video_title)

        # Envoi Telegram (si activé)
        if SEND_TELEGRAM:
            send_telegram_video(output_final, generated_caption)

        # Si Auto-post activé
        if AUTO_POST:
            # Envoi FTP
            remote_filename = os.path.basename(output_final)
            if upload_to_ftp(output_final, remote_filename):
                
                # Publication API
                if publish_to_late_api(remote_filename, generated_caption):
                    
                    # Si publié avec succès, on supprime du FTP
                    delete_file_from_ftp(remote_filename)
        else:
            print(f"💾 Vidéo sauvegardée localement uniquement : {output_final}")
            print("🚫 Auto-post désactivé (AUTO_POST = False).")
            print("📝 Météadonnées générées pour information :")
            print(generated_caption)


        # 🧹 Nettoyage des clips sources utilisés
        print(f"🧹 Suppression des {len(groupe)} clips sources...")
        for clip_path in groupe:
            try:
                os.remove(clip_path)
                print(f"   🗑️ Supprimé : {clip_path}")
            except Exception as e:
                print(f"   ❌ Erreur suppression {clip_path} : {e}")

        # On peut aussi supprimer la frame temporaire
        if os.path.exists(temp_frame):
            try:
                os.remove(temp_frame)
            except:
                pass

if __name__ == "__main__":
    main()
