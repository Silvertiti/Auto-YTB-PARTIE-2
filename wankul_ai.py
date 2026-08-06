"""
╔══════════════════════════════════════════════════════════════════╗
║      WANKUL AI GENERATOR  v3  —  Style BD Ligne Claire          ║
║  Photo → Analyse → Prompt BD précis → Image style Wankul        ║
╚══════════════════════════════════════════════════════════════════╝

Le style Wankul est du "Ligne Claire" franco-belge :
  - Traits noirs nets et uniformes (pas d'épaisseur variable)
  - Couleurs plates, sans dégradé, sans ombre complexe
  - Visage ultra-simplifié : petit nez, yeux simples, bouche minimaliste
  - Corps légèrement stylisé, pas chibi/anime
  - Style bande dessinée française

USAGE :
  python wankul_ai.py <image>
  python wankul_ai.py gotaga.jpg
  python wankul_ai.py gotaga.jpg -o resultat.png
"""

import os, sys, argparse, time
import cv2
import numpy as np
import requests
from dotenv import dotenv_values

# UTF-8 Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

env = dotenv_values(".env")
HF_TOKEN = env.get("HF_TOKEN") or os.getenv("HF_TOKEN", "")


# ══════════════════════════════════════════════════════════════════
#  ANALYSE DE LA PHOTO
# ══════════════════════════════════════════════════════════════════
def analyze_image(image_path: str) -> dict:
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Impossible de lire : {image_path}")
    h, w = img.shape[:2]

    def roi(y1p, y2p, x1p, x2p):
        y1, y2 = max(0, int(h*y1p)), min(h, int(h*y2p))
        x1, x2 = max(0, int(w*x1p)), min(w, int(w*x2p))
        return img[y1:y2, x1:x2] if y2 > y1 and x2 > x1 else None

    def dominant(region, default=(180, 150, 120)):
        if region is None or region.size == 0:
            return default
        pixels = region.reshape(-1, 3).astype(np.float32)
        k = min(3, max(1, len(pixels)//10))
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 0.5)
        _, labels, centers = cv2.kmeans(pixels, k, None, crit, 3, cv2.KMEANS_RANDOM_CENTERS)
        counts = np.bincount(labels.flatten())
        c = centers[np.argmax(counts)]
        return (int(c[2]), int(c[1]), int(c[0]))  # BGR→RGB

    def lum(rgb):
        return 0.299*rgb[0] + 0.587*rgb[1] + 0.114*rgb[2]

    def rgb_desc(rgb):
        r, g, b = rgb
        l = lum(rgb)
        if l < 45:   return "black"
        if l > 220:  return "white"
        if l < 85:   return "dark"
        if r > g+40 and r > b+40: return "red"
        if g > r+30 and g > b+20: return "green"
        if b > r+40 and b > g+30: return "blue"
        if r > 160 and g > 130 and b < 90: return "yellow"
        if r > 130 and g > 80 and b < 80:  return "orange"
        if r > 100 and b > 100 and g < 80: return "purple"
        if l > 170: return "light grey"
        if l > 110: return "grey"
        return "dark grey"

    def skin_desc(rgb):
        l = lum(rgb)
        if l > 195: return "very fair"
        if l > 160: return "fair"
        if l > 130: return "light tan"
        if l > 100: return "tan, mediterranean"
        if l > 70:  return "brown, north african"
        return "dark brown"

    # Zones
    skin = dominant(roi(0.25, 0.55, 0.3,  0.7))
    hair = dominant(roi(0.0,  0.25, 0.2,  0.8))
    shirt = dominant(roi(0.6,  0.95, 0.1,  0.9))
    cap   = dominant(roi(0.0,  0.18, 0.15, 0.85))

    # Barbe : zone menton/joues
    beard_roi = roi(0.55, 0.75, 0.25, 0.75)
    has_beard = False
    beard_rgb = hair
    if beard_roi is not None and beard_roi.size > 0:
        b_rgb = dominant(beard_roi)
        if lum(b_rgb) < lum(skin) * 0.72:
            has_beard = True
            beard_rgb = b_rgb

    # Lunettes : densité de contours dans la zone yeux
    eye_roi = roi(0.28, 0.48, 0.18, 0.82)
    has_glasses = False
    if eye_roi is not None and eye_roi.size > 0:
        gray = cv2.cvtColor(eye_roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 70, 170)
        has_glasses = float(np.mean(edges)) > 25

    # Casquette : le haut doit être nettement différent de la peau
    has_cap = abs(lum(cap) - lum(skin)) > 35

    traits = {
        "skin":       skin_desc(skin),
        "hair":       rgb_desc(hair),
        "shirt":      rgb_desc(shirt),
        "cap":        rgb_desc(cap),
        "has_cap":    has_cap,
        "has_beard":  has_beard,
        "beard":      rgb_desc(beard_rgb),
        "has_glasses": has_glasses,
        # Raw RGB pour debug
        "_skin_rgb":  skin,
        "_hair_rgb":  hair,
        "_shirt_rgb": shirt,
    }

    print("\n📊 Analyse :")
    print(f"  Peau      : {traits['skin']} {skin}")
    print(f"  Cheveux   : {traits['hair']} {hair}")
    print(f"  Vêtement  : {traits['shirt']} {shirt}")
    print(f"  Casquette : {'Oui → ' + traits['cap'] if has_cap else 'Non'}")
    print(f"  Barbe     : {'Oui → ' + traits['beard'] if has_beard else 'Non'}")
    print(f"  Lunettes  : {'Oui' if has_glasses else 'Non'}")
    return traits


# ══════════════════════════════════════════════════════════════════
#  CONSTRUCTION DU PROMPT LIGNE CLAIRE / WANKUL
# ══════════════════════════════════════════════════════════════════
def build_prompt(traits: dict) -> tuple[str, str]:
    """Retourne (positive_prompt, negative_prompt)"""

    # ── Positive ────────────────────────────────────────────────────
    pos = [
        # Style de base EXACT du Wankul
        "ligne claire style",
        "franco-belgian bande dessinee cartoon",
        "clean uniform black ink outlines",
        "flat colors no shading no gradients",
        "simple minimalist 2D cartoon face",
        "small simple nose",
        "simple round eyes",
        "simple mouth",
        "cartoon character portrait",
        "white background",
    ]

    # Peau
    pos.append(f"{traits['skin']} skin")

    # Cheveux
    pos.append(f"{traits['hair']} hair")

    # Casquette
    if traits["has_cap"]:
        pos.append(f"wearing a {traits['cap']} snapback cap")

    # Barbe
    if traits["has_beard"]:
        pos.append(f"short {traits['beard']} beard stubble")

    # Lunettes
    if traits["has_glasses"]:
        pos.append("wearing simple rectangular glasses")

    # Vêtement
    pos.append(f"{traits['shirt']} t-shirt or sweater")

    # Finitions style
    pos += [
        "cel shaded",
        "comic book art",
        "french animation style",
        "simple character design",
        "sticker art",
        "high quality illustration",
    ]

    # ── Negative ────────────────────────────────────────────────────
    neg = (
        "3d, realistic, photorealistic, photograph, hyperrealistic, "
        "shading, shadows, gradients, depth, lighting effects, "
        "anime, chibi, manga, japanese style, "
        "detailed texture, skin pores, wrinkles, hair strands, "
        "blurry, watermark, text, signature, nsfw, "
        "deformed, distorted, ugly, bad anatomy, "
        "cross-hatching, hatching, sketch, pencil"
    )

    positive = ", ".join(pos)
    print(f"\n✍️  Prompt :\n  {positive[:120]}...\n")
    return positive, neg


# ══════════════════════════════════════════════════════════════════
#  GÉNÉRATION — PLUSIEURS APIs ESSAYÉES EN CASCADE
# ══════════════════════════════════════════════════════════════════
def generate(image_path: str, prompt_pos: str, prompt_neg: str, output_path: str) -> str | None:

    # ── 1. Together AI (FLUX.1-schnell gratuit) ──────────────────────
    together_key = env.get("TOGETHER_API_KEY") or os.getenv("TOGETHER_API_KEY", "")
    if together_key:
        print("🤖 [Together AI] FLUX.1-schnell...")
        result = _try_together(together_key, prompt_pos, output_path)
        if result:
            return result

    # ── 2. HuggingFace Inference (img2img) ───────────────────────────
    if HF_TOKEN:
        print("🤖 [HuggingFace] Tentative img2img...")
        result = _try_huggingface(image_path, prompt_pos, output_path)
        if result:
            return result

    # ── 3. Pollinations.ai (FLUX - sans clé) ─────────────────────────
    print("🤖 [Pollinations.ai] FLUX (sans clé)...")
    result = _try_pollinations(prompt_pos, prompt_neg, output_path)
    if result:
        return result

    return None


def _try_together(api_key: str, prompt: str, output_path: str) -> str | None:
    try:
        import base64
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "black-forest-labs/FLUX.1-schnell-Free",
            "prompt": prompt,
            "width": 768,
            "height": 768,
            "steps": 4,
            "n": 1,
            "response_format": "b64_json"
        }
        resp = requests.post(
            "https://api.together.xyz/v1/images/generations",
            headers=headers, json=payload, timeout=90
        )
        if resp.status_code == 200:
            data = resp.json()
            img_b64 = data["data"][0]["b64_json"]
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(img_b64))
            print(f"   ✅ Together AI OK → {output_path}")
            return output_path
        else:
            print(f"   ❌ Together AI {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        print(f"   ❌ Together AI exception: {e}")
    return None


def _try_huggingface(image_path: str, prompt: str, output_path: str) -> str | None:
    import base64
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}

    models = [
        ("stabilityai/stable-diffusion-2-1",       "SD 2.1"),
        ("stabilityai/stable-diffusion-xl-base-1.0","SDXL"),
    ]

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    for model_id, label in models:
        try:
            print(f"   Modèle : {label} ({model_id})")
            payload = {
                "inputs": prompt,
                "parameters": {
                    "image": img_b64,
                    "strength": 0.85,
                    "num_inference_steps": 30,
                    "guidance_scale": 9.0,
                }
            }
            url = f"https://api-inference.huggingface.co/models/{model_id}"
            resp = requests.post(url, headers=headers, json=payload, timeout=90)

            if resp.status_code == 503:
                wait = resp.json().get("estimated_time", 30)
                print(f"   ⏳ Chargement modèle, attente {wait:.0f}s...")
                time.sleep(min(float(wait)+5, 60))
                resp = requests.post(url, headers=headers, json=payload, timeout=90)

            if resp.status_code == 200 and "image" in resp.headers.get("Content-Type",""):
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                print(f"   ✅ HuggingFace OK → {output_path}")
                return output_path
            else:
                print(f"   ❌ HF {resp.status_code}")
        except Exception as e:
            print(f"   ❌ HF exception ({label}): {str(e)[:80]}")
    return None


def _try_pollinations(prompt: str, neg_prompt: str, output_path: str) -> str | None:
    """
    Pollinations.ai — FLUX, gratuit, sans clé.
    On utilise le mode POST avec negative_prompt pour plus de contrôle.
    """
    try:
        # Essai POST (plus de contrôle)
        payload = {
            "prompt": prompt,
            "negative_prompt": neg_prompt,
            "model": "flux",
            "width": 768,
            "height": 768,
            "seed": 1234,
            "nologo": True,
            "enhance": False,
        }
        resp = requests.post(
            "https://image.pollinations.ai/prompt",
            json=payload, timeout=120
        )

        if resp.status_code != 200 or "image" not in resp.headers.get("Content-Type",""):
            # Fallback GET
            encoded = requests.utils.quote(prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded}"
            params = {"model": "flux", "width": 768, "height": 768,
                      "nologo": "true", "seed": "1234"}
            resp = requests.get(url, params=params, timeout=120)

        if resp.status_code == 200 and "image" in resp.headers.get("Content-Type",""):
            with open(output_path, "wb") as f:
                f.write(resp.content)
            print(f"   ✅ Pollinations OK → {output_path}")
            return output_path
        else:
            print(f"   ❌ Pollinations {resp.status_code}")
    except Exception as e:
        print(f"   ❌ Pollinations exception: {e}")
    return None


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Génère un personnage style Wankul BD desde une photo")
    parser.add_argument("image", help="Photo source")
    parser.add_argument("-o", "--output", default="wankul_ai_result.png")
    parser.add_argument("--prompt-only", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"❌ Image introuvable : {args.image}")
        sys.exit(1)

    print("=" * 60)
    print("   WANKUL AI GENERATOR  v3  —  Style BD Ligne Claire")
    print("=" * 60)

    traits = analyze_image(args.image)
    prompt_pos, prompt_neg = build_prompt(traits)

    if args.prompt_only:
        print(f"\nPROMPT POSITIF :\n{prompt_pos}")
        print(f"\nPROMPT NEGATIF :\n{prompt_neg}")
        sys.exit(0)

    print("🎨 Génération en cours...")
    result = generate(args.image, prompt_pos, prompt_neg, args.output)

    print("\n" + "=" * 60)
    if result:
        print(f"✅ SUCCÈS → {os.path.abspath(result)}")
    else:
        print("❌ Échec total. Vérifie ta connexion internet.")
    print("=" * 60)


if __name__ == "__main__":
    main()
