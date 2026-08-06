"""
Gemini Image Generator - Wankul Style
Utilise les vrais modeles image Gemini disponibles sur ce compte.
"""
import os, sys, base64, requests
from pathlib import Path
from dotenv import dotenv_values

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

env = dotenv_values(".env")
API_KEY = env.get("GEMINI_API_KEY", "")

PROMPT_WANKUL = (
    "Look at this photo. Draw this person as a 2D cartoon character "
    "in the exact style of Wankul Studio French YouTubers: "
    "thick uniform black freehand outlines, completely flat colors with zero shading, "
    "very simple minimalist face with small dot eyes, tiny simple nose, simple mouth line, "
    "franco-belgian bande dessinee ligne claire style, "
    "white clean background, partial side angle view. "
    "No anime, no 3D, no gradients, no shadows."
)


def try_gemini_image_model(image_path, prompt, output_path, model):
    """Essaie un modele Gemini generateContent avec image."""
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    mime = "image/jpeg" if image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
    payload = {
        "contents": [{
            "parts": [
                {"inlineData": {"mimeType": mime, "data": img_b64}},
                {"text": prompt}
            ]
        }],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}
    }

    resp = requests.post(url, json=payload, timeout=120)
    print(f"   Status {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "inlineData" in part:
                    img_bytes = base64.b64decode(part["inlineData"]["data"])
                    with open(output_path, "wb") as f:
                        f.write(img_bytes)
                    return True
                elif "text" in part:
                    print(f"   Texte : {part['text'][:150]}")
    elif resp.status_code == 404:
        print("   Modele non disponible")
    else:
        print(f"   Erreur: {resp.text[:200]}")
    return False


def try_imagen4(prompt, output_path):
    """Imagen 4.0 - meilleure qualite, prompt texte uniquement."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-generate-001:predict?key={API_KEY}"
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": "1:1", "outputMimeType": "image/png"}
    }
    resp = requests.post(url, json=payload, timeout=120)
    print(f"   Status {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        preds = data.get("predictions", [])
        if preds:
            b64 = preds[0].get("bytesBase64Encoded", "")
            if b64:
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(b64))
                return True
    else:
        print(f"   Erreur Imagen4: {resp.text[:200]}")
    return False


def generate(image_path, output_path="gemini_wankul.png"):
    print("=" * 60)
    print("   GEMINI IMAGE GENERATOR - WANKUL STYLE")
    print("=" * 60)

    # Modeles Gemini avec generation d'image (dans l'ordre de preference)
    gemini_image_models = [
        "gemini-3.1-flash-image",
        "gemini-3-pro-image",
        "gemini-2.5-flash-image",
        "gemini-3.1-flash-image-preview",
    ]

    for model in gemini_image_models:
        print(f"\n[*] Essai : {model}")
        try:
            ok = try_gemini_image_model(image_path, PROMPT_WANKUL, output_path, model)
            if ok:
                print(f"[OK] Image generee -> {os.path.abspath(output_path)}")
                return output_path
        except Exception as e:
            print(f"   Exception: {str(e)[:100]}")

    # Imagen 4 (texte seul, sans image de reference)
    print("\n[*] Imagen 4.0 (meilleure qualite, prompt seul)...")
    prompt_imagen = (
        "A young man with short dark messy hair, short beard, light tan skin, "
        "wearing a grey-white snapback cap (Red Bull style) and a black esport jersey. "
        "Draw him as a 2D cartoon character in the Wankul Studio style: "
        "thick black outlines, flat colors, simple minimalist face, "
        "franco-belgian ligne claire bande dessinee, white background, "
        "partial profile angle. No shading, no gradients, no anime style."
    )
    try:
        ok = try_imagen4(prompt_imagen, output_path)
        if ok:
            print(f"[OK] Imagen4 -> {os.path.abspath(output_path)}")
            return output_path
    except Exception as e:
        print(f"   Exception Imagen4: {str(e)[:100]}")

    print("\n[FAIL] Aucun modele n'a reussi.")
    return None


if __name__ == "__main__":
    img = sys.argv[1] if len(sys.argv) > 1 and os.path.exists(sys.argv[1]) else "test_gotaga.jpg"
    out = sys.argv[2] if len(sys.argv) > 2 else "gemini_wankul_result.png"
    generate(img, out)
