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
try:
    from moviepy.editor import VideoFileClip, concatenate_videoclips, CompositeVideoClip
except ImportError:
    from moviepy import VideoFileClip, concatenate_videoclips, CompositeVideoClip
from groq import Groq
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Groq Client Initialization
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ========= CONFIG =========
NB_VIDEOS = 1        # << Nombre de vidéos finales à générer
TARGET_SECONDS = 60  # << Durée MINIMALE par vidéo
STREAMER_NAME = "anyme023"

# FTP CONFIG
FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
REMOTE_DIR = "www"
BASE_URL = "https://silvertiti.fr"

# POSTING CONFIG (Late API / TikTok)
LATE_API_KEY = os.getenv("LATE_API_KEY")
#TIKTOK_ACCOUNT_ID = os.getenv("TIKTOK_ACCOUNT_ID_HAWAII") # HAWAIISERVICE
TIKTOK_ACCOUNT_ID = os.getenv("TIKTOK_ACCOUNT_ID_BLACKGEN") # BlackGEN


# Paramètres TikTok
TIKTOK_SETTINGS = {
    'privacy_level': 'PUBLIC_TO_EVERYONE', # 'PUBLIC_TO_EVERYONE', 'FRIENDS_ONLY', 'PRIVATE_TO_MYSELF'
    'allow_comment': True,
    'allow_duet': True,
    'allow_stitch': True,
    'content_preview_confirmed': True,
    'express_consent_given': True
}
PUBLISH_NOW = True # True pour publier direct, False pour brouillon

# On interroge suffisamment de clips côté API, mais on ne télécharge qu'à la demande.
MAX_API_CLIPS = NB_VIDEOS * 40  # augmente si nécessaire
# ==========================

client_id = os.getenv("TWITCH_CLIENT_ID")
client_secret = os.getenv("TWITCH_CLIENT_SECRET")

# -------- Utils --------

def get_access_token():
    url = 'https://id.twitch.tv/oauth2/token'
    params = {'client_id': client_id, 'client_secret': client_secret, 'grant_type': 'client_credentials'}
    response = requests.post(url, params=params)
    response.raise_for_status()
    return response.json()['access_token']

def get_user_id(access_token, username):
    headers = {'Client-ID': client_id, 'Authorization': f'Bearer {access_token}'}
    response = requests.get('https://api.twitch.tv/helix/users', headers=headers, params={'login': username})
    response.raise_for_status()
    data = response.json().get('data', [])
    return data[0]['id'] if data else None

def get_clips(access_token, broadcaster_id, first=50, started_at=None):
    headers = {'Client-ID': client_id, 'Authorization': f'Bearer {access_token}'}
    params = {'broadcaster_id': broadcaster_id, 'first': first}
    if started_at:
        params['started_at'] = started_at
    response = requests.get('https://api.twitch.tv/helix/clips', headers=headers, params=params)
    response.raise_for_status()
    return response.json().get('data', [])

def telecharger_clip(url, output_file):
    print(f"⏬ Téléchargement de {url}...")
    # Use python -m streamlink to ensure we use the installed module even if not in PATH
    cmd = [sys.executable, "-m", "streamlink", "--twitch-disable-ads", url, "best", "-o", output_file]
    result = subprocess.run(cmd)
    return result.returncode == 0 and os.path.exists(output_file)

def extraire_image(video_file, output_image):
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
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

# -------- Compatibility Helpers (MoviePy v1 vs v2) --------

def apply_crop(clip, x1=None, y1=None, x2=None, y2=None, width=None, height=None, x_center=None, y_center=None):
    if hasattr(clip, 'crop'):
        return clip.crop(x1=x1, y1=y1, x2=x2, y2=y2, width=width, height=height, x_center=x_center, y_center=y_center)
    else:
        # MoviePy v2
        from moviepy.video.fx import Crop
        return clip.with_effects([Crop(x1=x1, y1=y1, x2=x2, y2=y2, width=width, height=height, x_center=x_center, y_center=y_center)])

def apply_resize(clip, width=None, height=None):
    if hasattr(clip, 'resize'):
        return clip.resize(width=width, height=height)
    else:
        # MoviePy v2
        from moviepy.video.fx import Resize
        return clip.with_effects([Resize(width=width, height=height)])

def apply_position(clip, pos):
    if hasattr(clip, 'set_position'):
        return clip.set_position(pos)
    else:
        return clip.with_position(pos)

def apply_audio(clip, audio):
    if hasattr(clip, 'set_audio'):
        return clip.set_audio(audio)
    else:
        return clip.with_audio(audio)

def apply_fl_image(clip, func):
    if hasattr(clip, 'fl_image'):
        return clip.fl_image(func)
    else:
        # MoviePy v2
        return clip.image_transform(func)

# -------- Montage --------

def montage_tiktok(clips_paths, crop_params, output_path):
    print(f"🎞️ Montage final : {output_path}")
    clips = [VideoFileClip(p) for p in clips_paths]
    try:
        full_clip = concatenate_videoclips(clips)

        if crop_params:
            x, y, w, h = crop_params
            
            # Correction v2 : apply_crop / apply_resize / apply_position
            webcam_clip = apply_crop(full_clip, x1=x, y1=y, x2=x + w, y2=y + h)
            webcam_clip = apply_resize(webcam_clip, width=720)
            
            webcam_height = webcam_clip.h
            clip_height = 1280 - webcam_height
            reduction_factor = 0.24
            new_width = min(full_clip.w, int(720 + 720 * reduction_factor))
            
            clip_cropped = apply_crop(full_clip, width=new_width, x_center=full_clip.w // 2)
            clip_cropped = apply_resize(clip_cropped, height=clip_height, width=720)
            
            final = CompositeVideoClip(
                [
                    apply_position(webcam_clip, ("center", "top")),
                    apply_position(clip_cropped, ("center", webcam_height)),
                ],
                size=(720, 1280)
            )
            # Duration is kept from full_clip or set on Composite if needed, 
            # usually Composite takes duration of longest clip or we set it explicitly.
            if hasattr(final, 'set_duration'):
                final = final.set_duration(full_clip.duration)
            else:
                final = final.with_duration(full_clip.duration)

            if full_clip.audio:
                final = apply_audio(final, full_clip.audio)
        else:
            base_clip = apply_resize(full_clip, width=720)
            # Pour le flou, fl_image existe toujours en v2
            # Correction v2: fl_image -> apply_fl_image
            blurred = apply_resize(base_clip, height=1280)
            blurred = apply_fl_image(blurred, lambda f: blur_frame(f, 35))
            
            final = CompositeVideoClip(
                [
                    blurred,
                    apply_position(base_clip, "center"),
                ],
                size=(720, 1280)
            )
            if hasattr(final, 'set_duration'):
                 final = final.set_duration(full_clip.duration)
            else:
                 final = final.with_duration(full_clip.duration)

            if full_clip.audio:
                final = apply_audio(final, full_clip.audio)

        final.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            logger='bar' # << Barre de chargement activée
        )
        print(f"✅ Exporté : {output_path}")
    finally:
        for c in clips:
            c.close()


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
                    "content": f"Streamer: {streamer_name}\nTitre du clip: {titre_clip_twitch}"
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
        final_caption = f"{titre}\n\n{hashtags}"
        print(f"✨ Métadonnées générées :{final_caption}")
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

    try:
        response = requests.post(url, headers=headers, json=data)
        
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
    user_id = get_user_id(access_token, STREAMER_NAME)
    if not user_id:
        print("❌ Streamer non trouvé.")
        return

    # On récupère une LISTE de candidats (non téléchargés)
    clips_data = get_clips(
        access_token, user_id,
        first=max(10, min(100, MAX_API_CLIPS)),
        started_at=(datetime.utcnow() - timedelta(hours=24)).isoformat() + 'Z'
    )
    if not clips_data:
        print("❌ Aucun clip trouvé.")
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
                with VideoFileClip(file_path) as v:
                    d = v.duration
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
        
        # Envoi FTP
        remote_filename = os.path.basename(output_final)
        if upload_to_ftp(output_final, remote_filename):
            
            # Génération de la description avec Groq
            generated_caption = generate_metadata(STREAMER_NAME, video_title)
            
            # Publication API
            if publish_to_late_api(remote_filename, generated_caption):
                
                # Si publié avec succès, on supprime du FTP
                delete_file_from_ftp(remote_filename)


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
