import os
import subprocess
import cv2
import requests
from datetime import datetime, timedelta, timezone
from ultralytics import YOLO
from moviepy.editor import VideoFileClip, concatenate_videoclips, CompositeVideoClip

# ========= CONFIG =========
NB_VIDEOS = 5         # Nombre de vidéos finales à générer
TARGET_SECONDS = 60   # Durée MINIMALE par vidéo (>= 60 s)
LANGUAGE = "fr"       # Code langue des clips ("fr", "en", "es", "de", ...)
WINDOW_HOURS = 24     # Dernières X heures
TOP_GAMES = 20        # Nombre de jeux populaires à sonder
CLIPS_PER_GAME = 50   # Nombre max de clips à demander par jeu (on ne télécharge pas tout)
# ==========================

BOT_TOKEN = "7342966721:AAE6_C_LuyvcXaAuArlQ2AUz-lQUIFQ3Y4s"
CHAT_ID = "1998327169"

# Identifiants app Twitch
client_id = 'nhplbk0cauctrdgh13rf75sv387lye'
client_secret = 'cycmd8gr3xozmxacw8yj7v3tb9d1qz'


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

def get_top_games(access_token, first=20):
    r = requests.get(
        'https://api.twitch.tv/helix/games/top',
        headers=twitch_headers(access_token),
        params={'first': min(100, first)}
    )
    r.raise_for_status()
    return r.json().get('data', [])

def get_clips_by_game(access_token, game_id, first=50, started_at=None, ended_at=None):
    params = {
        'game_id': game_id,
        'first': min(100, first)
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


# -------- Collecte “meilleurs clips 24h par langue” --------

def collect_best_clips_last_24h_by_language(access_token, language, window_hours, top_games, clips_per_game):
    """
    1) Prend la liste des jeux populaires.
    2) Pour chaque jeu, récupère les clips dans la fenêtre [now-window_hours, now].
    3) Filtre par langue du clip (clip.language == language), classe par vues.
    """
    ended_at_dt = datetime.now(timezone.utc)
    started_at_dt = ended_at_dt - timedelta(hours=window_hours)
    started_at = started_at_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    ended_at = ended_at_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    games = get_top_games(access_token, first=top_games)
    all_clips = []

    for g in games:
        gid = g.get('id')
        if not gid:
            continue
        try:
            clips = get_clips_by_game(
                access_token,
                game_id=gid,
                first=clips_per_game,
                started_at=started_at,
                ended_at=ended_at
            )
            all_clips.extend(clips)
        except Exception:
            continue

    # Filtre stricte par langue
    filtered = [c for c in all_clips if c.get('language', '').lower() == language.lower()]

    # Si trop peu après filtre strict, on priorise par langue mais on garde le reste
    if len(filtered) < 20:
        def keyfunc(c):
            return (c.get('language', '').lower() == language.lower(), c.get('view_count', 0))
        ranked = sorted(all_clips, key=keyfunc, reverse=True)
    else:
        ranked = sorted(filtered, key=lambda c: c.get('view_count', 0), reverse=True)

    return ranked


# -------- Main --------

def main():
    output_folder = "clips_downloaded"
    os.makedirs(output_folder, exist_ok=True)

    access_token = get_access_token()

    # Meilleurs clips des dernières 24h par langue (tous streamers confondus)
    candidates = collect_best_clips_last_24h_by_language(
        access_token=access_token,
        language=LANGUAGE,
        window_hours=WINDOW_HOURS,
        top_games=TOP_GAMES,
        clips_per_game=CLIPS_PER_GAME
    )

    if not candidates:
        print("❌ Aucun clip trouvé pour cette langue sur les dernières 24h.")
        return

    # Construction des NB_VIDEOS vidéos en téléchargeant le strict nécessaire
    groupes = []
    idx = 0

    for video_index in range(1, NB_VIDEOS + 1):
        courant = []
        total = 0.0

        while total < TARGET_SECONDS and idx < len(candidates):
            clip = candidates[idx]
            idx += 1
            clip_url = clip['url']
            clip_id = clip['id']
            file_path = os.path.join(output_folder, f"{clip_id}.mp4")

            # Télécharge uniquement si nécessaire
            if not os.path.exists(file_path):
                if not telecharger_clip(clip_url, file_path):
                    continue

            # Durée
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

    # Génération + envoi
    for idx_g, groupe in enumerate(groupes, start=1):
        print(f"\n===== Génération de la vidéo {idx_g}/{len(groupes)} (≥ {TARGET_SECONDS}s) =====")
        first_clip = groupe[0]
        temp_frame = first_clip.replace(".mp4", f"_frame_{idx_g}.jpg")
        if not extraire_image(first_clip, temp_frame):
            print("❌ Erreur extraction image.")
            continue

        crop_params = detecter_webcam(temp_frame)
        output_final = os.path.join(output_folder, f"tiktok_final_{idx_g}.mp4")
        montage_tiktok(groupe, crop_params, output_final)
        envoyer_telegram(output_final, BOT_TOKEN, CHAT_ID)

if __name__ == "__main__":
    main()
