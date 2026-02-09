import os
import subprocess
import cv2
import requests
from datetime import datetime, timedelta
from ultralytics import YOLO
from moviepy.editor import VideoFileClip, CompositeVideoClip

client_id = os.getenv("TWITCH_CLIENT_ID")
client_secret = os.getenv("TWITCH_CLIENT_SECRET")

def get_access_token():
    url = 'https://id.twitch.tv/oauth2/token'
    params = {'client_id': client_id, 'client_secret': client_secret, 'grant_type': 'client_credentials'}
    response = requests.post(url, params=params)
    return response.json()['access_token']

def get_user_id(access_token, username):
    url = 'https://api.twitch.tv/helix/users'
    headers = {'Client-ID': client_id, 'Authorization': f'Bearer {access_token}'}
    response = requests.get(url, headers=headers, params={'login': username})
    data = response.json()['data']
    return data[0]['id'] if data else None

def get_clips(access_token, broadcaster_id, first=20, started_at=None):
    url = 'https://api.twitch.tv/helix/clips'
    headers = {'Client-ID': client_id, 'Authorization': f'Bearer {access_token}'}
    params = {'broadcaster_id': broadcaster_id, 'first': first}
    if started_at:
        params['started_at'] = started_at
    response = requests.get(url, headers=headers, params=params)
    return response.json()['data']

def telecharger_clip(url, output_file):
    print("⏬ Téléchargement du clip...")
    result = subprocess.run(["streamlink", "--twitch-disable-ads", url, "best", "-o", output_file])
    return result.returncode == 0 and os.path.exists(output_file)

def extraire_image(video_file, output_image):
    print("🎥 Extraction de l'image à 1s...")
    subprocess.run([
        "ffmpeg", "-y", "-ss", "00:00:01", "-i", video_file,
        "-frames:v", "1", output_image
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.exists(output_image)

def detecter_webcam(image_path, model_path="runs/detect/train6/weights/best.pt"):
    print("🔍 Détection de la webcam...")
    model = YOLO(model_path)
    img = cv2.imread(image_path)
    results = model.predict(source=image_path, conf=0.25, save=False, show=False)
    for result in results:
        boxes = result.boxes
        for box in boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            marge = 20
            x1, y1 = max(0, x1 - marge), max(0, y1 - marge)
            x2, y2 = min(img.shape[1], x2 + marge), min(img.shape[0], y2 + marge)
            print(f"✅ Zone détectée : ({x1}, {y1}) - ({x2}, {y2})")
            return x1, y1, x2 - x1, y2 - y1
    return None

def montage_tiktok(clip_path, crop_params, output_path):
    print("🎞️ Montage final TikTok...")
    clip = VideoFileClip(clip_path)
    x, y, w, h = crop_params
    webcam_clip = clip.crop(x1=x, y1=y, x2=x + w, y2=y + h).resize(width=720)
    webcam_height = webcam_clip.h
    clip_height = 1280 - webcam_height

    reduction_factor = 0.24
    new_width = int(720 + 720 * reduction_factor)
    new_width = min(clip.w, new_width)

    clip_cropped = clip.crop(width=new_width, x_center=clip.w // 2).resize(height=clip_height, width=720)
    final = CompositeVideoClip([
        webcam_clip.set_position(("center", "top")),
        clip_cropped.set_position(("center", webcam_height))
    ], size=(720, 1280)).set_duration(clip.duration).set_audio(clip.audio)

    final.write_videofile(output_path, codec="libx264", audio_codec="aac", verbose=False, logger=None)
    print(f"✅ Exporté : {output_path}")

def upload_to_pixeldrain(file_path):
    print("🌐 Upload sur Pixeldrain...")
    with open(file_path, 'rb') as f:
        response = requests.post('https://pixeldrain.com/api/file', files={'file': f})
        if response.status_code == 200:
            file_id = response.json()['id']
            link = f"https://pixeldrain.com/u/{file_id}"
            print(f"✅ Lien de téléchargement : {link}")
            return link
        else:
            print("❌ Erreur upload Pixeldrain.")
            print(response.text)
            return None

def main():
    streamer_name = 'anyme023'
    output_folder = "clips_downloaded"
    os.makedirs(output_folder, exist_ok=True)

    access_token = get_access_token()
    user_id = get_user_id(access_token, streamer_name)
    if not user_id:
        print("❌ Streamer non trouvé.")
        return

    started_at = (datetime.utcnow() - timedelta(hours=24)).isoformat() + 'Z'
    clips = get_clips(access_token, user_id, first=20, started_at=started_at)
    if not clips:
        print("❌ Aucun clip trouvé.")
        return

    clips = sorted(clips, key=lambda c: c['view_count'], reverse=True)

    for clip in clips:
        clip_id = clip['id']
        clip_url = clip['url']
        clip_file = os.path.join(output_folder, f"{clip_id}.mp4")
        if os.path.exists(clip_file):
            print(f"⚠️ Clip déjà téléchargé ({clip_url}), on passe au suivant.")
            continue

        print(f"🔗 Clip sélectionné : {clip_url}")
        if telecharger_clip(clip_url, clip_file):
            print(f"✅ Clip téléchargé : {clip_file}")

            frame_file = os.path.join(output_folder, f"{clip_id}_frame.jpg")
            if not extraire_image(clip_file, frame_file):
                print("❌ Erreur extraction image.")
                return

            crop_params = detecter_webcam(frame_file)
            if not crop_params:
                print("❌ Webcam non détectée.")
                return

            final_output = os.path.join(output_folder, f"{clip_id}_tiktok.mp4")
            montage_tiktok(clip_file, crop_params, final_output)

            link = upload_to_pixeldrain(final_output)
            if link:
                print(f"✅ Lien final prêt : {link}")
            else:
                print("❌ Upload échoué.")
            break
    else:
        print("❌ Tous les clips ont déjà été traités !")

if __name__ == "__main__":
    main()
