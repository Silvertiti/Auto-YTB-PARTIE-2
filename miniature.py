import csv
import os
import subprocess

def extraire_image_clip(url, output_image):
    temp_file = "clip_temp.mp4"

    # 1️⃣ Télécharger le clip
    print("⏬ Téléchargement du clip...")
    streamlink_cmd = [
        "streamlink", "--twitch-disable-ads", url, "best", "-o", temp_file
    ]
    result = subprocess.run(streamlink_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Vérifie si le fichier a bien été créé
    if not os.path.exists(temp_file):
        print("❌ Échec du téléchargement avec streamlink. Image non extraite.")
        return

    # 2️⃣ Extraire l'image à 1s avec ffmpeg
    print("🎥 Extraction de l'image...")
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-ss", "00:00:01",
        "-i", temp_file,
        "-frames:v", "1",
        output_image
    ]
    subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3️⃣ Nettoyer
    os.remove(temp_file)

def main():
    csv_file = "clips_24h_with_category.csv"
    output_folder = "thumbnails"
    os.makedirs(output_folder, exist_ok=True)

    # Lis les URLs du CSV
    urls = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            urls.append(row['url'])

    if not urls:
        print("❌ Aucun URL trouvé dans le CSV.")
        return

    # Extraire une image pour chaque URL
    for i, url in enumerate(urls, 1):
        output_image = os.path.join(output_folder, f"clip_{i}.jpg")
        print(f"📸 Extraction image clip {i}/{len(urls)} : {url}")
        extraire_image_clip(url, output_image)

    print("✅ Extraction terminée. Toutes les images disponibles sont dans le dossier 'thumbnails'.")

if __name__ == "__main__":
    main()
