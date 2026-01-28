import csv
import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

def extraire_image_clip(url, output_image):
    temp_file = "temp.ts"
    command_streamlink = f"streamlink --twitch-disable-ads {url} best -o \"{temp_file}\""
    subprocess.run(command_streamlink, shell=True)

    command_ffmpeg = f"ffmpeg -i \"{temp_file}\" -ss 00:00:01 -vframes 1 \"{output_image}\" -y"
    subprocess.run(command_ffmpeg, shell=True)

    os.remove(temp_file)

def lire_et_incrementer_nombre(txt_path="nombre.txt"):
    if not os.path.exists(txt_path):
        with open(txt_path, 'w') as f:
            f.write('1')
        return 1
    else:
        with open(txt_path, 'r+') as f:
            n = int(f.read().strip())
            n += 1
            f.seek(0)
            f.write(str(n))
            f.truncate()
        return n

def creer_mosaique(images, logo_path, output_mosaique="mosaique_avec_logo.jpg", nombre=1):
    # Ouvre les images
    img_objs = [Image.open(img) for img in images]
    widths, heights = zip(*(i.size for i in img_objs))

    max_width = max(widths)
    max_height = max(heights)

    # Crée la mosaïque 2x2
    mosaique = Image.new('RGB', (max_width * 2, max_height * 2))
    positions = [
        (0, 0),
        (max_width, 0),
        (0, max_height),
        (max_width, max_height)
    ]

    for pos, img in zip(positions, img_objs):
        mosaique.paste(img, pos)

    # Ajoute le logo
    logo = Image.open(logo_path).convert("RGBA")
    logo_width = int(max_width * 0.5)
    ratio = logo_width / logo.width
    logo_height = int(logo.height * ratio)
    logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)

    center_x = (mosaique.width - logo_width) // 2
    center_y = (mosaique.height - logo_height) // 2
    mosaique.paste(logo, (center_x, center_y), logo)

    # Ajoute le nombre en haut à gauche avec police arrondie DejaVuSans
    draw = ImageDraw.Draw(mosaique)
    font_size = int(max_width * 0.1)
    try:
        font = ImageFont.truetype("Nunito-Black.ttf", font_size)
    except:
        font = ImageFont.load_default()

    text = f"#{nombre}"
    draw.text((10, 10), text, fill="white", font=font, stroke_width=2, stroke_fill="black")

    mosaique.save(output_mosaique)
    print(f"✅ Mosaïque finale avec logo et numéro sauvegardée : {output_mosaique}")

def main():
    csv_file = "clips_24h_filtered.csv"
    output_folder = "mosaique_temp"
    os.makedirs(output_folder, exist_ok=True)
    logo_path = "logo.png"

    # Récupère les 4 premiers liens de clips
    urls = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i < 4:
                urls.append(row['url'])
            else:
                break

    if len(urls) < 4:
        print("❌ Pas assez de clips pour créer la mosaïque.")
        return

    images = []
    for i, url in enumerate(urls, 1):
        output_image = os.path.join(output_folder, f"clip_{i}.jpg")
        print(f"📸 Extraction image clip {i} : {url}")
        extraire_image_clip(url, output_image)
        images.append(output_image)

    # Lire et incrémenter le nombre
    nombre = lire_et_incrementer_nombre()

    # Crée la mosaïque finale avec le logo et le numéro
    creer_mosaique(images, logo_path, output_mosaique="mosaique_avec_logo.jpg", nombre=nombre)

    # Nettoie les images temporaires
    for img in images:
        os.remove(img)
    os.rmdir(output_folder)

if __name__ == "__main__":
    main()
