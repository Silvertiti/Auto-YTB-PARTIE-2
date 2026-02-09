import os
import subprocess
import cv2
import requests
from datetime import datetime, timedelta, timezone
from ultralytics import YOLO
from moviepy.editor import VideoFileClip, concatenate_videoclips, CompositeVideoClip

# ========= CONFIG =========
NB_VIDEOS = 6         # Nombre de vidéos finales à générer
TARGET_SECONDS = 60   # Durée MINIMALE par vidéo (>= 60 s)
STREAMER_NAME = "anyme023"
BOT_TOKEN = "7342966721:AAE6_C_LuyvcXaAuArlQ2AUz-lQUIFQ3Y4s"
CHAT_ID = "1998327169"

# Fenêtre de secours si pas de live (en heures)
FALLBACK_WINDOW_HOURS = 6

# Nombre max de clips à demander côté API (on NE télécharge pas tout, juste ce qu'il faut)
MAX_API_CLIPS = 100
# ==========================

client_id = os.getenv("TWITCH_CLIENT_ID")
client_secret = os.getenv("TWITCH_CLIENT_SECRET")


# -------- Utils Twitch --------

def get_access_token():
    url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'client_credentials'
    }
    r = requests.post(url, params=params)
    r.raise_for_status()
    return r.json()['access_token']

def twitch_headers(access_token):
    return {
        'Client-ID': client_id,
        'Authorization': f'Bearer {access_token}'
    }

def get_user_id(access_token, username):
    r = requests.get(
        'https://api.twitch.tv/helix/users',
        headers=twitch_headers(access_token),
        params={'login': username}
    )
    r.raise_for_status()
    data = r.json().get('data', [])
    return data[0]['id'] if data else None

def get_current_stream_start(access_token, user_id):
    """
    Retourne l'ISO datetime du début du stream actuel si LIVE, sinon None.
    """
    r = requests.get(
        'https://api.twitch.tv/helix/streams',
        headers=twitch_headers(access_token),
        params={'user_id': user_id}
    )
    r.raise_for_status()
    data = r.json().get('data', [])
    if not data:
        return None  # pas live
    stream = data[0]
    if stream.get('type') != 'live':
        return None
    # started_at est déjà ISO 8601 en UTC (ex: '2025-08-22T14:03:00Z')
    return stream.get('started_at')

def get_clips(access_token, broadcaster_id, first=50, started_at=None, ended_at=None):
    """
    Récupère des clips; peut filtrer par intervalle [started_at, ended_at].
    """
    params = {
        'broadcaster_id': broadcaster_id,
        'first': min(first, 100)  # limite Helix
    }
    if started_at:
        params['started_at'] = started_at
    if ended_at:
        params['ended_at'] = ended_at

    r = requests.get(
        'https://api.twitch.tv/helix/clips',
        headers=twitch_headers(access_token),
        params=params
    )
    r.raise_for_status()
    return r.json().get('data', [])

# -------- Téléchargement / Frame --------

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

# -------- Flou OpenCV --------

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

# -------- Montage --------

def montage_tiktok(clips_paths, crop_params, output_path):
    print(f"🎞️ Montage final : {output_path}")
    clips = [VideoFileClip(p) for p in clips_paths]
    try:
        full_clip = concatenate_videoclips(clips)

        if crop_params:
            x, y, w, h = crop_params
            webcam_clip = full_clip.crop(x1=x, y1=y, x2=x + w, y2=y + h).resize(width=720)
            webcam_height = webcam_clip.h
            clip_height = 1280 - webcam_height
            reduction_factor = 0.24
            new_width = min(full_clip.w, int(720 + 720 * reduction_factor))
            clip_cropped = full_clip.crop(width=new_width, x_center=full_clip.w // 2).resize(height=clip_height, width=720)
            final = CompositeVideoClip(
                [
                    webcam_clip.set_position(("center", "top")),
                    clip_cropped.set_position(("center", webcam_height)),
                ],
                size=(720, 1280)
            ).set_duration(full_clip.duration)
            if full_clip.audio:
                final = final.set_audio(full_clip.audio)
        else:
            base_clip = full_clip.resize(width=720)
            blurred = base_clip.resize(height=1280).fl_image(lambda f: blur_frame(f, 35))
            final = CompositeVideoClip(
                [
                    blurred,
                    base_clip.set_position("center"),
                ],
                size=(720, 1280)
            ).set_duration(full_clip.duration)
            if full_clip.audio:
                final = final.set_audio(full_clip.audio)

        final.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            verbose=False,
            logger=None
        )
        print(f"✅ Exporté : {output_path}")
    finally:
        for c in clips:
            c.close()

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
    os.makedirs(output_folder, exist_ok=True)

    access_token = get_access_token()
    user_id = get_user_id(access_token, STREAMER_NAME)
    if not user_id:
        print("❌ Streamer non trouvé.")
        return

    # 1) Cherche le stream en cours
    live_started_at = get_current_stream_start(access_token, user_id)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if live_started_at:
        print(f"🔴 Live détecté, début: {live_started_at}")
        started_at = live_started_at
        ended_at = now_iso
    else:
        # 2) Pas de live → fallback sur une fenêtre récente
        ended_at_dt = datetime.now(timezone.utc)
        started_at_dt = ended_at_dt - timedelta(hours=FALLBACK_WINDOW_HOURS)
        started_at = started_at_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        ended_at = ended_at_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"⚪ Pas de live. Fallback clips entre {started_at} et {ended_at} (~{FALLBACK_WINDOW_HOURS}h).")

    # Récupère candidats (NON téléchargés)
    clips_data = get_clips(
        access_token, user_id,
        first=min(MAX_API_CLIPS, 100),
        started_at=started_at,
        ended_at=ended_at
    )
    if not clips_data:
        print("❌ Aucun clip trouvé dans l'intervalle.")
        return

    # Classe par popularité (meilleurs en premier)
    clips_data = sorted(clips_data, key=lambda c: c.get('view_count', 0), reverse=True)

    groupes = []
    idx_clip = 0

    for video_index in range(1, NB_VIDEOS + 1):
        courant = []
        total = 0.0

        # Ajoute des clips jusqu'à atteindre AU MINIMUM la durée cible
        while total < TARGET_SECONDS and idx_clip < len(clips_data):
            clip = clips_data[idx_clip]
            idx_clip += 1

            clip_id = clip['id']
            clip_url = clip['url']
            file_path = os.path.join(output_folder, f"{clip_id}.mp4")

            # Télécharge le clip si nécessaire
            if not os.path.exists(file_path):
                ok = telecharger_clip(clip_url, file_path)
                if not ok:
                    continue

            # Mesure la durée
            try:
                with VideoFileClip(file_path) as v:
                    d = v.duration
            except Exception:
                continue

            courant.append(file_path)
            total += d

        if total < TARGET_SECONDS:
            print(f"⛔ Pas assez de clips pour fabriquer la vidéo {video_index} (manque {int(TARGET_SECONDS - total)} s).")
            break

        groupes.append(courant)

    if not groupes:
        print("❌ Pas assez de clips pour créer une vidéo complète.")
        return

    # Génère & envoie
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

if __name__ == "__main__":
    main()
