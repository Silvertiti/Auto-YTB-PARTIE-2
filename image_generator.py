"""
╔══════════════════════════════════════════════════════════════════╗
║       GENERATEUR D'IMAGE GRATUIT  –  Style Gemini               ║
║  Image + Prompt → Nouvelle image générée par IA                 ║
║                                                                  ║
║  APIs utilisées (TOUTES GRATUITES) :                            ║
║   1. Hugging Face Inference API  (img2img, FLUX, SD)            ║
║   2. Pollinations.ai             (text2img, sans clé)           ║
╚══════════════════════════════════════════════════════════════════╝

SETUP (une seule fois) :
  1. Créer un compte gratuit sur https://huggingface.co
  2. Aller sur https://huggingface.co/settings/tokens
  3. Créer un token "Read" (gratuit, pas de CB)
  4. Le coller dans ce script ou dans la variable d'env HF_TOKEN

USAGE :
  python image_generator.py <image> "<prompt>" [options]

EXEMPLES :
  python image_generator.py photo.jpg "cartoon 2D style wankul studio, bold black outlines"
  python image_generator.py gotaga.jpg "anime character, vibrant colors" -o anime.png
  python image_generator.py photo.jpg "comic book hero" --mode pollinations
"""

import os
import sys
import argparse
import base64
import requests
import json
from pathlib import Path
from io import BytesIO

# Support UTF-8 Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIG — Colle ton token HuggingFace ici (ou variable d'env HF_TOKEN)
# ─────────────────────────────────────────────────────────────────────────────
HF_TOKEN = os.getenv("HF_TOKEN", "")   # ← Remplace par ton token HF si pas d'env var

# Modèles img2img disponibles gratuitement sur HuggingFace
HF_MODELS = {
    "flux-dev":     "black-forest-labs/FLUX.1-dev",
    "flux-schnell": "black-forest-labs/FLUX.1-schnell",
    "sdxl":         "stabilityai/stable-diffusion-xl-base-1.0",
    "sd3":          "stabilityai/stable-diffusion-3-medium-diffusers",
}


# ══════════════════════════════════════════════════════════════════
#  MÉTHODE 1 : HUGGING FACE INFERENCE API  (image + prompt)
# ══════════════════════════════════════════════════════════════════
def generate_with_huggingface(
    image_path: str,
    prompt: str,
    output_path: str = "generated.png",
    model_key: str = "flux-schnell",
    strength: float = 0.75,
) -> str | None:
    """
    Génère une image à partir d'une image source + prompt
    via l'API Hugging Face (gratuite avec token).
    """
    if not HF_TOKEN:
        print("[HF] Aucun token HF détecté. Définis HF_TOKEN ou modifie ce script.")
        print("     Token gratuit : https://huggingface.co/settings/tokens")
        return None

    model_id = HF_MODELS.get(model_key, HF_MODELS["flux-schnell"])
    print(f"[HF] Modèle : {model_id}")
    print(f"[HF] Prompt : {prompt}")

    # Lire et encoder l'image en base64
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
    }

    # Payload img2img
    payload = {
        "inputs": prompt,
        "parameters": {
            "image": image_b64,
            "strength": strength,
            "num_inference_steps": 30,
            "guidance_scale": 7.5,
        }
    }

    api_url = f"https://api-inference.huggingface.co/models/{model_id}"
    print(f"[HF] Envoi de la requête à {api_url}...")

    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=120)

        # Si le modèle est en train de charger → attendre
        if resp.status_code == 503:
            wait_time = resp.json().get("estimated_time", 30)
            print(f"[HF] Modèle en chargement, attente {wait_time:.0f}s...")
            import time
            time.sleep(min(wait_time + 5, 60))
            resp = requests.post(api_url, headers=headers, json=payload, timeout=120)

        if resp.status_code == 200:
            content_type = resp.headers.get("Content-Type", "")
            if "image" in content_type:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                print(f"[HF] Image sauvegardée : {os.path.abspath(output_path)}")
                return output_path
            else:
                print(f"[HF] Réponse inattendue : {resp.text[:300]}")
                return None
        else:
            print(f"[HF] Erreur {resp.status_code} : {resp.text[:300]}")
            return None

    except requests.exceptions.Timeout:
        print("[HF] Timeout — le modèle prend trop de temps. Réessaie dans quelques secondes.")
        return None
    except Exception as e:
        print(f"[HF] Exception : {e}")
        return None


# ══════════════════════════════════════════════════════════════════
#  MÉTHODE 1b : HF via InferenceClient (méthode alternative propre)
# ══════════════════════════════════════════════════════════════════
def generate_with_huggingface_client(
    image_path: str,
    prompt: str,
    output_path: str = "generated.png",
    model_key: str = "flux-schnell",
) -> str | None:
    """
    Version utilisant huggingface_hub InferenceClient (plus robuste).
    """
    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        print("[HF Client] huggingface_hub non installé. Lance : pip install huggingface_hub")
        return None

    if not HF_TOKEN:
        print("[HF Client] Aucun token HF. Définis HF_TOKEN.")
        return None

    model_id = HF_MODELS.get(model_key, HF_MODELS["flux-schnell"])
    print(f"[HF Client] Modèle : {model_id}")

    client = InferenceClient(token=HF_TOKEN)

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    try:
        print(f"[HF Client] Génération en cours...")
        result = client.image_to_image(
            image=image_bytes,
            prompt=prompt,
            model=model_id,
        )
        result.save(output_path)
        print(f"[HF Client] Image sauvegardée : {os.path.abspath(output_path)}")
        return output_path
    except Exception as e:
        print(f"[HF Client] Erreur : {e}")
        return None


# ══════════════════════════════════════════════════════════════════
#  MÉTHODE 2 : POLLINATIONS.AI  (text-to-image, SANS CLÉ)
# ══════════════════════════════════════════════════════════════════
def generate_with_pollinations(
    image_path: str,
    prompt: str,
    output_path: str = "generated.png",
    width: int = 1024,
    height: int = 1024,
    model: str = "flux",
) -> str | None:
    """
    Génère une image via pollinations.ai — GRATUIT, SANS CLÉ.
    Note : Le prompt inclut la description de l'image source pour guider.
    """
    # Analyser l'image pour enrichir le prompt
    try:
        from PIL import Image as PILImage
        import numpy as np
        img = PILImage.open(image_path).convert("RGB")
        img_np = np.array(img)
        # Couleur dominante
        dominant = np.median(img_np.reshape(-1, 3), axis=0)
        color_hint = f"dominant colors rgb({int(dominant[0])},{int(dominant[1])},{int(dominant[2])})"
    except Exception:
        color_hint = ""

    # Enrichir le prompt avec contexte de l'image
    full_prompt = f"{prompt}, {color_hint}, high quality, detailed, 4k".strip(", ")
    encoded_prompt = requests.utils.quote(full_prompt)

    # Pollinations text-to-image API
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"
    params = {
        "width": width,
        "height": height,
        "model": model,
        "nologo": "true",
        "enhance": "true",
        "seed": 42,
    }

    print(f"[Pollinations] Prompt : {full_prompt[:100]}...")
    print(f"[Pollinations] Modèle : {model}")
    print(f"[Pollinations] Génération en cours (peut prendre 30-60s)...")

    try:
        resp = requests.get(url, params=params, timeout=120)
        if resp.status_code == 200 and "image" in resp.headers.get("Content-Type", ""):
            with open(output_path, "wb") as f:
                f.write(resp.content)
            print(f"[Pollinations] Image sauvegardée : {os.path.abspath(output_path)}")
            return output_path
        else:
            print(f"[Pollinations] Erreur {resp.status_code}")
            return None
    except requests.exceptions.Timeout:
        print("[Pollinations] Timeout — serveur surchargé, réessaie.")
        return None
    except Exception as e:
        print(f"[Pollinations] Exception : {e}")
        return None


# ══════════════════════════════════════════════════════════════════
#  MÉTHODE 3 : AI HORDE (Stable Diffusion communautaire, GRATUIT)
# ══════════════════════════════════════════════════════════════════
def generate_with_ai_horde(
    image_path: str,
    prompt: str,
    output_path: str = "generated.png",
    api_key: str = "0000000000",  # Clé anonyme par défaut
) -> str | None:
    """
    Génère via AI Horde (Stable Horde) — 100% gratuit, communautaire.
    Fonctionne sans compte, avec la clé anonyme "0000000000".
    Plus lent (GPU volunteers), mais totalement libre.
    """
    import time, base64

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    headers = {
        "apikey": api_key,
        "Content-Type": "application/json",
    }

    payload = {
        "prompt": prompt,
        "params": {
            "sampler_name": "k_euler",
            "cfg_scale": 7.5,
            "denoising_strength": 0.75,
            "seed": "42",
            "height": 768,
            "width": 768,
            "steps": 25,
            "n": 1,
        },
        "source_image": img_b64,
        "source_processing": "img2img",
        "models": ["Deliberate"],
        "r2": True,
        "nsfw": False,
        "censor_nsfw": True,
    }

    print("[AI Horde] Soumission de la requête...")
    try:
        resp = requests.post(
            "https://aihorde.net/api/v2/generate/async",
            headers=headers, json=payload, timeout=30
        )
        if resp.status_code not in (200, 202):
            print(f"[AI Horde] Erreur soumission : {resp.status_code} {resp.text[:200]}")
            return None

        job_id = resp.json().get("id")
        print(f"[AI Horde] Job ID : {job_id}")
        print("[AI Horde] En attente du résultat (GPU volunteers)...")

        # Polling du statut
        for attempt in range(30):
            time.sleep(10)
            status_resp = requests.get(
                f"https://aihorde.net/api/v2/generate/check/{job_id}",
                headers=headers, timeout=15
            )
            status = status_resp.json()
            wait = status.get("wait_time", "?")
            done = status.get("done", False)
            print(f"  Attente : {wait}s restantes... (tentative {attempt+1}/30)")

            if done:
                result_resp = requests.get(
                    f"https://aihorde.net/api/v2/generate/status/{job_id}",
                    headers=headers, timeout=30
                )
                result = result_resp.json()
                generations = result.get("generations", [])
                if generations:
                    img_data = generations[0].get("img", "")
                    if img_data.startswith("http"):
                        img_resp = requests.get(img_data, timeout=30)
                        with open(output_path, "wb") as f:
                            f.write(img_resp.content)
                    else:
                        img_bytes = base64.b64decode(img_data)
                        with open(output_path, "wb") as f:
                            f.write(img_bytes)
                    print(f"[AI Horde] Image sauvegardée : {os.path.abspath(output_path)}")
                    return output_path

        print("[AI Horde] Timeout — le job a pris trop de temps.")
        return None

    except Exception as e:
        print(f"[AI Horde] Exception : {e}")
        return None


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="Générateur d'images IA GRATUIT (image + prompt)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXEMPLES :
  # Style Wankul depuis une photo (Hugging Face)
  python image_generator.py gotaga.jpg "cartoon 2D character wankul studio style, bold black outlines, flat colors" -o wankul.png

  # Sans clé API (Pollinations.ai)
  python image_generator.py gotaga.jpg "anime version of this person, vibrant" --mode pollinations

  # Communautaire (AI Horde, sans compte)
  python image_generator.py photo.jpg "comic book superhero version" --mode horde

MODELS HF disponibles : flux-schnell, flux-dev, sdxl, sd3
        """
    )
    parser.add_argument("image",  help="Image source (JPG/PNG)")
    parser.add_argument("prompt", help="Description de l'image à générer")
    parser.add_argument("-o", "--output", default="generated.png", help="Fichier de sortie (défaut: generated.png)")
    parser.add_argument("-m", "--mode",
                        choices=["huggingface", "pollinations", "horde"],
                        default="huggingface",
                        help="API à utiliser (défaut: huggingface)")
    parser.add_argument("--model",
                        choices=list(HF_MODELS.keys()),
                        default="flux-schnell",
                        help="Modèle HuggingFace (défaut: flux-schnell)")
    parser.add_argument("--strength", type=float, default=0.75,
                        help="Force de transformation 0.0-1.0 (défaut: 0.75)")
    parser.add_argument("--token", default="",
                        help="Token HuggingFace (ou définis HF_TOKEN en variable d'env)")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"[ERREUR] Image introuvable : {args.image}")
        sys.exit(1)

    if args.token:
        global HF_TOKEN
        HF_TOKEN = args.token

    print("=" * 60)
    print("   IMAGE GENERATOR IA — GRATUIT")
    print("=" * 60)
    print(f"Image  : {args.image}")
    print(f"Prompt : {args.prompt}")
    print(f"Mode   : {args.mode}")
    print(f"Sortie : {args.output}")
    print("-" * 60)

    result = None

    if args.mode == "huggingface":
        # Essayer d'abord via InferenceClient (plus propre)
        result = generate_with_huggingface_client(
            args.image, args.prompt, args.output, args.model
        )
        # Fallback sur l'API directe
        if result is None:
            print("[HF] Tentative via API directe...")
            result = generate_with_huggingface(
                args.image, args.prompt, args.output, args.model, args.strength
            )

    elif args.mode == "pollinations":
        result = generate_with_pollinations(args.image, args.prompt, args.output)

    elif args.mode == "horde":
        result = generate_with_ai_horde(args.image, args.prompt, args.output)

    print("-" * 60)
    if result:
        print(f"[OK] Image generee : {os.path.abspath(result)}")
    else:
        print("[ECHEC] La génération a échoué. Essaie un autre mode.")
        print("\nConseils :")
        print("  - Sans token HF : python image_generator.py image.jpg 'prompt' --mode pollinations")
        print("  - Avec token HF : obtiens-le sur https://huggingface.co/settings/tokens")
        print("  - 100% gratuit sans compte : --mode horde  (mais lent)")
    print("=" * 60)


if __name__ == "__main__":
    main()
