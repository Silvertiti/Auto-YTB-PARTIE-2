import os
import subprocess
import cv2
import requests
from datetime import datetime, timedelta
from ultralytics import YOLO
try:
    from moviepy.editor import VideoFileClip, concatenate_videoclips, CompositeVideoClip
except ImportError:
    from moviepy import VideoFileClip, concatenate_videoclips, CompositeVideoClip

# ========= CONFIG =========
NB_VIDEOS = 1        # << Nombre de vidéos finales à générer
TARGET_SECONDS = 60  # << Durée MINIMALE par vidéo
STREAMER_NAME = "anyme023"
BOT_TOKEN = "7342966721:AAE6_C_LuyvcXaAuArlQ2AUz-lQUIFQ3Y4s"
CHAT_ID = "1998327169"

# On interroge suffisamment de clips côté API, mais on ne télécharge qu'à la demande.
MAX_API_CLIPS = NB_VIDEOS * 40  # augmente si nécessaire
# ==========================

client_id = 'nhplbk0cauctrdgh13rf75sv387lye'
client_secret = 'cycmd8gr3xozmxacw8yj7v3tb9d1qz'

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
    result = subprocess.run(["streamlink", "--twitch-disable-ads", url, "best", "-o", output_file])
    return result.returncode == 0 and os.path.exists(output_file)

def extraire_image(video_file, output_image):
    subprocess.run(
        ["ffmpeg", "-y", "-ss", "00:00:01", "-i", video_file, "-frames:v", "1", output_image],
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

def detecter_webcam(image_path, model_path="runs/detect/train6/weights/best.pt"):
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
            logger=None
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

# -------- Telegram --------

def envoyer_telegram(file_path, bot_token, chat_id):
    print("📲 Envoi sur Telegram…")
    url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
    with open(file_path, 'rb') as f:
        response = requests.post(
            url,
            data={'chat_id': chat_id, 'caption': "Voici ta vidéo TikTok 🥳"},
            files={'video': f}
        )
    if response.status_code == 200:
        print("✅ Vidéo envoyée sur Telegram !")
    else:
        print(f"❌ Erreur Telegram : {response.text}")

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

            courant.append(file_path)
            total += d
            
            # Enregistrer immédiatement pour ne pas le refaire au prochain run
            ajouter_clip_telecharge(fichier_tracking, clip_id, clip_title)
            deja_vus.add(clip_id)

        # Si on n'a pas réussi à atteindre la durée minimale, on s'arrête là (pas de vidéo incomplète)
        if total < TARGET_SECONDS:
            print(f"⛔ Pas assez de contenu pour fabriquer la vidéo {video_index} (manque {int(TARGET_SECONDS - total)} s).")
            break

        groupes.append(courant)

    if not groupes:
        print("❌ Pas assez de clips pour créer une vidéo complète.")
        return

    # Génération + envoi
    for idx, groupe in enumerate(groupes, start=1):
        print(f"\n===== Génération de la vidéo {idx}/{len(groupes)} (≥ {TARGET_SECONDS}s) =====")
        first_clip = groupe[0]
        temp_frame = first_clip.replace(".mp4", f"_frame_{idx}.jpg")
        if not extraire_image(first_clip, temp_frame):
            print("❌ Erreur extraction image.")
            continue

        crop_params = detecter_webcam(temp_frame)
        output_final = os.path.join(output_folder, f"tiktok_final_{idx}.mp4")
        montage_tiktok(groupe, crop_params, output_final)
        envoyer_telegram(output_final, BOT_TOKEN, CHAT_ID)

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
