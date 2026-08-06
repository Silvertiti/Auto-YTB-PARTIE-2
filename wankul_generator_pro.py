"""
╔══════════════════════════════════════════════════════════════════╗
║              WANKUL AI GENERATOR PRO  v4.0                       ║
║  Transforme une photo réelle en personnage Wankul 2D exact.      ║
║                                                                  ║
║  Services supportés :                                            ║
║   1. Google Imagen 3 API  (Même qualité exacte que la démo)      ║
║   2. Replicate API        (img2img SDXL / Flux)                  ║
║   3. Fal.ai API           (img2img ultra rapide)                 ║
╚══════════════════════════════════════════════════════════════════╝

USAGE :
    python wankul_generator_pro.py <image_source> [options]

EXEMPLES :
    python wankul_generator_pro.py gotaga.jpg
    python wankul_generator_pro.py gotaga.jpg -o mon_wankul.png
"""

import os
import sys
import argparse
import base64
import requests
from dotenv import dotenv_values

# UTF-8 Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

env = dotenv_values(".env")
GEMINI_KEY = env.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
REPLICATE_KEY = env.get("REPLICATE_API_TOKEN") or os.getenv("REPLICATE_API_TOKEN", "")
FAL_KEY = env.get("FAL_KEY") or os.getenv("FAL_KEY", "")

# Prompt Ligne Claire BD exact
WANKUL_PROMPT = (
    "A hand-drawn 2D bust portrait illustration in the exact minimalist Franco-Belgian "
    "'ligne claire' comic book graphic style of Wankul Studio (French YouTube cartoon). "
    "The character is based on the person in the reference image: preserve hair color, "
    "hair style, facial hair, skin tone, glasses, hat or cap, and shirt design. "
    "Clean thick uniform black freehand lineart outline, completely flat basic colors, "
    "zero shading, no gradients, no 3D effects, no anime style. "
    "Simple minimalist face with tiny dot eyes and simple line mouth. "
    "Clean solid white background."
)

# ══════════════════════════════════════════════════════════════════
#  MÉTHODE 1 : GOOGLE IMAGEN 3 (Exactement le modèle de la démo)
# ══════════════════════════════════════════════════════════════════
def generate_imagen4(image_path: str, output_path: str) -> str | None:
    """Génère l'image via Google Imagen 4 API."""
    if not GEMINI_KEY:
        print("[Imagen 4] Clé GEMINI_API_KEY manquante.")
        return None

    print("[Imagen 4] Envoi de la requête à Google Imagen 4.0...")
    
    # Endpoint Imagen 4.0
    url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-generate-001:predict?key={GEMINI_KEY}"

    payload = {
        "instances": [
            {
                "prompt": WANKUL_PROMPT,
            }
        ],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": "1:1",
            "outputMimeType": "image/png"
        }
    }

    try:
        resp = requests.post(url, json=payload, timeout=120)
        if resp.status_code == 200:
            predictions = resp.json().get("predictions", [])
            if predictions:
                b64_out = predictions[0].get("bytesBase64Encoded", "")
                if b64_out:
                    with open(output_path, "wb") as f:
                        f.write(base64.b64decode(b64_out))
                    print(f"✅ Imagen 4.0 OK -> {os.path.abspath(output_path)}")
                    return output_path
        elif resp.status_code == 429:
            print("[Imagen 4] Quota 429 : La clé Google nécessite d'activer la facturation (Billing GCP).")
        else:
            print(f"[Imagen 4] Erreur {resp.status_code}: {resp.text[:250]}")
    except Exception as e:
        print(f"[Imagen 4] Exception : {e}")

    # Fallback Gemini 3.1 Flash Image
    print("[Gemini 3.1 Image] Tentative via gemini-3.1-flash-image...")
    url_gemini = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image:generateContent?key={GEMINI_KEY}"
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
    mime_type = "image/jpeg" if image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"

    payload_gemini = {
        "contents": [{
            "parts": [
                {"inlineData": {"mimeType": mime_type, "data": img_b64}},
                {"text": WANKUL_PROMPT}
            ]
        }],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}
    }

    try:
        resp = requests.post(url_gemini, json=payload_gemini, timeout=120)
        if resp.status_code == 200:
            for candidate in resp.json().get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "inlineData" in part:
                        with open(output_path, "wb") as f:
                            f.write(base64.b64decode(part["inlineData"]["data"]))
                        print(f"✅ Gemini 3.1 Image OK -> {os.path.abspath(output_path)}")
                        return output_path
        elif resp.status_code == 429:
            print("[Gemini 3.1 Image] Quota 429 : Activer la facturation sur aistudio.google.com pour la génération d'images.")
        else:
            print(f"[Gemini 3.1 Image] Erreur {resp.status_code}: {resp.text[:250]}")
    except Exception as e:
        print(f"[Gemini 3.1 Image] Exception : {e}")

    return None


# ══════════════════════════════════════════════════════════════════
#  MÉTHODE 2 : REPLICATE API (SDXL / Flux Image-to-Image)
# ══════════════════════════════════════════════════════════════════
def generate_replicate(image_path: str, output_path: str) -> str | None:
    """Génère l'image via Replicate API (SDXL img2img)."""
    if not REPLICATE_KEY:
        print("[Replicate] Token REPLICATE_API_TOKEN manquant dans .env")
        return None

    print("[Replicate] Génération img2img SDXL...")

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    mime_type = "image/jpeg" if image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
    data_uri = f"data:{mime_type};base64,{img_b64}"

    headers = {
        "Authorization": f"Bearer {REPLICATE_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "version": "da77bc59ee60423279c869415c61213700d044b7b46f32e9f317fe51084b6c55", # SDXL img2img
        "input": {
            "image": data_uri,
            "prompt": WANKUL_PROMPT,
            "prompt_strength": 0.75,
            "num_inference_steps": 30,
        }
    }

    try:
        resp = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload, timeout=30)
        if resp.status_code == 201:
            prediction = resp.json()
            get_url = prediction["urls"]["get"]
            import time
            for _ in range(30):
                time.sleep(3)
                poll = requests.get(get_url, headers=headers, timeout=15).json()
                status = poll.get("status")
                if status == "succeeded":
                    output_url = poll.get("output", [])[0]
                    img_data = requests.get(output_url, timeout=30).content
                    with open(output_path, "wb") as f:
                        f.write(img_data)
                    print(f"✅ Replicate OK -> {os.path.abspath(output_path)}")
                    return output_path
                elif status == "failed":
                    print(f"[Replicate] Échec : {poll.get('error')}")
                    break
        else:
            print(f"[Replicate] Erreur {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[Replicate] Exception : {e}")

    return None


# ══════════════════════════════════════════════════════════════════
#  MÉTHODE 3 : FAL.AI API (Flux Image-to-Image)
# ══════════════════════════════════════════════════════════════════
def generate_fal(image_path: str, output_path: str) -> str | None:
    """Génère l'image via Fal.ai API."""
    if not FAL_KEY:
        print("[Fal.ai] Clé FAL_KEY manquante dans .env")
        return None

    print("[Fal.ai] Génération via Fal.ai Flux...")
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    mime_type = "image/jpeg" if image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
    data_uri = f"data:{mime_type};base64,{img_b64}"

    headers = {
        "Authorization": f"Key {FAL_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "prompt": WANKUL_PROMPT,
        "image_url": data_uri,
        "strength": 0.75,
    }

    try:
        resp = requests.post("https://fal.run/fal-ai/flux/dev/image-to-image", headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            images = resp.json().get("images", [])
            if images:
                img_url = images[0].get("url")
                img_data = requests.get(img_url, timeout=30).content
                with open(output_path, "wb") as f:
                    f.write(img_data)
                print(f"✅ Fal.ai OK -> {os.path.abspath(output_path)}")
                return output_path
        else:
            print(f"[Fal.ai] Erreur {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[Fal.ai] Exception : {e}")

    return None


def main():
    parser = argparse.ArgumentParser(description="Générateur de personnage Wankul Pro (Image-to-Image)")
    parser.add_argument("image", help="Chemin vers l'image source (JPG/PNG)")
    parser.add_argument("-o", "--output", default="wankul_pro_result.png", help="Nom du fichier PNG de sortie")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"❌ Fichier introuvable : {args.image}")
        sys.exit(1)

    print("=" * 60)
    print("   WANKUL AI GENERATOR PRO — PHOTO TO WANKUL")
    print("=" * 60)
    print(f"📸 Image source : {args.image}")

    # 1. Essai Imagen 4 / Gemini Image
    res = generate_imagen4(args.image, args.output)
    if res:
        return

    # 2. Essai Replicate
    res = generate_replicate(args.image, args.output)
    if res:
        return

    # 3. Essai Fal.ai
    res = generate_fal(args.image, args.output)
    if res:
        return

    print("\n⚠️ Aucun service d'API Image-to-Image n'a pu s'exécuter.")
    print("Pour obtenir exactement le rendu de la démo en script Python autonome :")
    print("  - Soit tu actives le Billing sur ta clé Google AI Studio (Imagen 3)")
    print("  - Soit tu ajoutes un token gratuit Replicate (REPLICATE_API_TOKEN) ou Fal.ai (FAL_KEY) dans ton fichier .env")


if __name__ == "__main__":
    main()
