import os
import subprocess
import cv2
from ultralytics import YOLO

# ✏️ Lien du clip Twitch à traiter
url = "https://www.twitch.tv/anyme023/clip/ShortAssiduousPineappleCeilingCat-82gw1vNvDvnBj2td"  # Remplace par ton lien

def telecharger_clip(url, output_file):
    print("⏬ Téléchargement du clip...")
    cmd = ["streamlink", "--twitch-disable-ads", url, "best", "-o", output_file]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.exists(output_file)

def extraire_image(video_file, output_image):
    print("🎥 Extraction de l'image à 1s...")
    cmd = [
        "ffmpeg", "-y", "-ss", "00:00:01",
        "-i", video_file,
        "-frames:v", "1",
        output_image
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
            x1 = max(0, x1 - marge)
            y1 = max(0, y1 - marge)
            x2 = min(img.shape[1], x2 + marge)
            y2 = min(img.shape[0], y2 + marge)
            print(f"✅ Zone détectée : ({x1}, {y1}) - ({x2}, {y2})")
            return x1, y1, x2 - x1, y2 - y1  # format ffmpeg crop=w:h:x:y
    return None

def rogner_clip(input_video, output_video, crop_params):
    print("✂️ Rognage du clip complet...")
    x, y, w, h = crop_params
    crop_filter = f"crop={w}:{h}:{x}:{y}"
    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", crop_filter,
        "-c:a", "copy",  # garder l'audio original
        output_video
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"🎉 Clip rogné disponible ici : {output_video}")

def main():
    output_folder = "clips_cropped"
    os.makedirs(output_folder, exist_ok=True)

    clip_file = os.path.join(output_folder, "clip.mp4")
    image_file = os.path.join(output_folder, "clip.jpg")
    output_cropped = os.path.join(output_folder, "clip_cropped.mp4")

    # Télécharger le clip
    if not telecharger_clip(url, clip_file):
        print("❌ Échec du téléchargement.")
        return

    # Extraire la première image
    if not extraire_image(clip_file, image_file):
        print("❌ Impossible d'extraire l'image.")
        return

    # Détecter la webcam
    crop_params = detecter_webcam(image_file)
    if not crop_params:
        print("❌ Aucune webcam détectée.")
        return

    # Rogner la vidéo
    rogner_clip(clip_file, output_cropped, crop_params)
    print("\n✅ Tout est prêt ! Clip rogné terminé.")

if __name__ == "__main__":
    main()
