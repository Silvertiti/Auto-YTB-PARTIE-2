"""
╔══════════════════════════════════════════════════════════════════╗
║              WANKUL AI GENERATOR — PYTHON SCRIPT                 ║
║  Transforme n'importe quelle photo en personnage style Wankul.   ║
║  Utilise la vision OpenCV pour analyser la photo et construire   ║
║  le prompt Ligne Claire BD exact de Wankul Studio.               ║
╚══════════════════════════════════════════════════════════════════╝

USAGE :
    python generate_wankul_ai.py <image_source> [options]

EXEMPLES :
    python generate_wankul_ai.py ma_photo.jpg
    python generate_wankul_ai.py gotaga.jpg -o gotaga_wankul.png
"""

import os
import sys
import argparse
import requests
import cv2
import numpy as np
from PIL import Image

# Forcer l'affichage console UTF-8 sur Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def analyze_photo_features(image_path: str) -> dict:
    """Analyse visuelle avancée de la photo source avec OpenCV."""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Impossible de lire l'image : {image_path}")

    h, w = img.shape[:2]

    def get_roi(y1_pct, y2_pct, x1_pct, x2_pct):
        y1, y2 = max(0, int(h * y1_pct)), min(h, int(h * y2_pct))
        x1, x2 = max(0, int(w * x1_pct)), min(w, int(w * x2_pct))
        if y2 <= y1 or x2 <= x1:
            return None
        return img[y1:y2, x1:x2]

    def get_color_name(rgb):
        r, g, b = rgb
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        if lum < 40:
            return "black"
        elif lum > 220:
            return "white"
        elif lum < 80:
            return "dark grey"

        if r > 150 and g < 100 and b < 100:
            return "red"
        elif r > 160 and g > 140 and b < 80:
            return "yellow"
        elif r < 90 and g < 90 and b > 140:
            return "blue"
        elif r < 90 and g > 130 and b < 90:
            return "green"
        elif r > 160 and g > 100 and b < 80:
            return "orange"
        elif lum > 160:
            return "light grey"
        else:
            return "grey"

    def get_skin_description(rgb):
        lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
        if lum > 190:
            return "fair light skin"
        elif lum > 150:
            return "light tan skin"
        elif lum > 110:
            return "mediterranean tan skin"
        elif lum > 75:
            return "brown skin"
        else:
            return "dark brown skin"

    def dominant_rgb(roi_img, default=(180, 150, 120)):
        if roi_img is None or roi_img.size == 0:
            return default
        pixels = roi_img.reshape(-1, 3).astype(np.float32)
        k = min(3, max(1, len(pixels) // 20))
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 0.5)
        _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 3, cv2.KMEANS_RANDOM_CENTERS)
        counts = np.bincount(labels.flatten())
        best_bgr = centers[np.argmax(counts)]
        return (int(best_bgr[2]), int(best_bgr[1]), int(best_bgr[0]))

    # Zones d'analyse
    skin_rgb = dominant_rgb(get_roi(0.25, 0.55, 0.3, 0.7), default=(210, 170, 135))
    hair_rgb = dominant_rgb(get_roi(0.0, 0.25, 0.2, 0.8), default=(35, 28, 22))
    shirt_rgb = dominant_rgb(get_roi(0.6, 0.95, 0.1, 0.9), default=(30, 30, 30))
    top_rgb = dominant_rgb(get_roi(0.0, 0.15, 0.15, 0.85), default=(200, 200, 200))

    # Casquette / Chapeau
    skin_lum = 0.299 * skin_rgb[0] + 0.587 * skin_rgb[1] + 0.114 * skin_rgb[2]
    top_lum = 0.299 * top_rgb[0] + 0.587 * top_rgb[1] + 0.114 * top_rgb[2]
    has_cap = abs(top_lum - skin_lum) > 35

    # Barbe
    beard_roi = get_roi(0.55, 0.75, 0.25, 0.75)
    has_beard = False
    beard_color = "dark"
    if beard_roi is not None and beard_roi.size > 0:
        beard_rgb = dominant_rgb(beard_roi)
        beard_lum = 0.299 * beard_rgb[0] + 0.587 * beard_rgb[1] + 0.114 * beard_rgb[2]
        if beard_lum < skin_lum * 0.72:
            has_beard = True
            beard_color = get_color_name(beard_rgb)

    # Lunettes
    eye_roi = get_roi(0.28, 0.48, 0.18, 0.82)
    has_glasses = False
    if eye_roi is not None and eye_roi.size > 0:
        gray_eyes = cv2.cvtColor(eye_roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray_eyes, 70, 170)
        has_glasses = float(np.mean(edges)) > 26

    features = {
        "skin_desc": get_skin_description(skin_rgb),
        "hair_color": get_color_name(hair_rgb),
        "shirt_color": get_color_name(shirt_rgb),
        "has_cap": has_cap,
        "cap_color": get_color_name(top_rgb) if has_cap else None,
        "has_beard": has_beard,
        "beard_color": beard_color if has_beard else None,
        "has_glasses": has_glasses,
    }

    return features


def build_wankul_prompt(features: dict) -> str:
    """Construit le prompt Ligne Claire exact de Wankul Studio."""
    subject_details = []
    
    # Description de la personne
    subject_details.append(f"{features['skin_desc']}")
    subject_details.append(f"short {features['hair_color']} hair")
    
    if features["has_cap"]:
        subject_details.append(f"wearing a {features['cap_color']} snapback cap")
        
    if features["has_beard"]:
        subject_details.append(f"short {features['beard_color']} beard stubble")
        
    if features["has_glasses"]:
        subject_details.append("wearing glasses")
        
    subject_details.append(f"wearing a {features['shirt_color']} t-shirt")

    details_str = ", ".join(subject_details)

    prompt = (
        "A hand-drawn 2D bust portrait illustration in the exact minimalist Franco-Belgian "
        "'ligne claire' comic book graphic style of Wankul Studio (French YouTube cartoon). "
        f"The character is a person with {details_str}. "
        "Clean thick uniform black freehand lineart outline, completely flat basic colors, "
        "zero shading, no gradients, no 3D effects, no anime style. "
        "Simple minimalist face with tiny dot eyes and simple line mouth. "
        "Clean solid white background."
    )

    return prompt


def generate_wankul_character(image_path: str, output_path: str = "wankul_generated.png") -> str:
    """Génère l'image du personnage Wankul."""
    print("=" * 60)
    print("   WANKUL AI GENERATOR — PYTHON SCRIPT")
    print("=" * 60)
    print(f"📸 Image source : {image_path}")

    # 1. Analyse
    print("[1/3] Analyse de la photo...")
    features = analyze_photo_features(image_path)
    print(f"  • Peau      : {features['skin_desc']}")
    print(f"  • Cheveux   : {features['hair_color']}")
    print(f"  • Vêtement  : {features['shirt_color']}")
    print(f"  • Casquette : {'Oui (' + str(features['cap_color']) + ')' if features['has_cap'] else 'Non'}")
    print(f"  • Barbe     : {'Oui' if features['has_beard'] else 'Non'}")
    print(f"  • Lunettes  : {'Oui' if features['has_glasses'] else 'Non'}")

    # 2. Construction du prompt
    print("[2/3] Génération du prompt Wankul Ligne Claire...")
    prompt = build_wankul_prompt(features)

    # 3. Génération via Pollinations avec le prompt exact
    print("[3/3] Génération du personnage Wankul en cours...")
    encoded_prompt = requests.utils.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"
    params = {
        "model": "flux",
        "width": 1024,
        "height": 1024,
        "nologo": "true",
        "seed": "42",
        "enhance": "false"
    }

    try:
        response = requests.get(url, params=params, timeout=120)
        if response.status_code == 200 and "image" in response.headers.get("Content-Type", ""):
            with open(output_path, "wb") as f:
                f.write(response.content)
            print("-" * 60)
            print(f"✅ SUCCÈS ! Personnage sauvegardé : {os.path.abspath(output_path)}")
            print("=" * 60)
            return output_path
        else:
            print(f"❌ Erreur lors de la génération : {response.status_code}")
    except Exception as e:
        print(f"❌ Exception : {e}")

    return None


def main():
    parser = argparse.ArgumentParser(description="Génère un personnage Wankul IA depuis une photo")
    parser.add_argument("image", help="Chemin vers l'image source (JPG/PNG)")
    parser.add_argument("-o", "--output", default="wankul_generated.png", help="Fichier de sortie PNG")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"❌ Fichier introuvable : {args.image}")
        sys.exit(1)

    generate_wankul_character(args.image, args.output)


if __name__ == "__main__":
    main()
