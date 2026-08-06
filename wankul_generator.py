"""
╔══════════════════════════════════════════════════════════════════╗
║          WANKUL CHARACTER GENERATOR  v2.0                       ║
║  Génère un personnage 2D style Wankul Studio à partir d'une     ║
║  photo. Fonctionne avec OpenCV 5+ (sans CascadeClassifier).     ║
╚══════════════════════════════════════════════════════════════════╝

Dépendances : opencv-python, Pillow, numpy
Usage :
  python wankul_generator.py <image> [options]

Options :
  -o / --output   Chemin de sortie PNG  (défaut : wankul_character.png)
  -m / --mode     vector | filter       (défaut : vector)
                  vector = Dessin vectoriel 2D Wankul depuis la photo
                  filter = Effet BD / Cartoon appliqué sur la photo
"""

import os
import sys
import argparse
import cv2
import numpy as np
from PIL import Image, ImageDraw

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
#  ANALYSE DE L'IMAGE
# ══════════════════════════════════════════════════════════════════
class WankulAnalyzer:
    def __init__(self, image_path: str):
        self.image_path = image_path
        self.img_bgr = cv2.imread(image_path)
        if self.img_bgr is None:
            raise ValueError(f"Impossible de lire l'image : {image_path}")
        self.h, self.w = self.img_bgr.shape[:2]

    def _detect_face(self):
        """Retourne (x, y, w, h) - zone visage ou zone centrale intelligente."""
        model_candidates = ["face_detection_yunet_2023mar.onnx"]
        for m in model_candidates:
            if os.path.isfile(m):
                try:
                    detector = cv2.FaceDetectorYN_create(m, "", (self.w, self.h))
                    _, faces = detector.detect(self.img_bgr)
                    if faces is not None and len(faces) > 0:
                        fx, fy, fw, fh = int(faces[0][0]), int(faces[0][1]), int(faces[0][2]), int(faces[0][3])
                        return fx, fy, fw, fh
                except Exception:
                    pass

        # Fallback : haut de l'image zone centrale lumineuse
        region = self.img_bgr[:self.h // 2, self.w // 4:3 * self.w // 4]
        gray_r = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        _, _, _, max_loc = cv2.minMaxLoc(gray_r)
        cx = max_loc[0] + self.w // 4
        cy = max_loc[1]
        fw = int(self.w * 0.42)
        fh = int(self.h * 0.45)
        fx = max(0, cx - fw // 2)
        fy = max(0, cy - fh // 5)
        return fx, fy, fw, fh

    def analyze(self) -> dict:
        fx, fy, fw, fh = self._detect_face()

        def safe_roi(y1, y2, x1, x2):
            y1, y2 = max(0, y1), min(self.h, y2)
            x1, x2 = max(0, x1), min(self.w, x2)
            if y2 <= y1 or x2 <= x1:
                return None
            return self.img_bgr[y1:y2, x1:x2]

        def median_rgb(roi, default=(200, 160, 120)):
            if roi is None or roi.size == 0:
                return default
            b, g, r = np.median(roi[:, :, 0]), np.median(roi[:, :, 1]), np.median(roi[:, :, 2])
            return (int(r), int(g), int(b))

        skin_roi  = safe_roi(fy + int(fh*0.35), fy + int(fh*0.65), fx + int(fw*0.3), fx + int(fw*0.7))
        skin_rgb  = median_rgb(skin_roi, (210, 170, 135))

        hair_roi  = safe_roi(max(0, fy - int(fh*0.3)), fy + int(fh*0.15), fx + int(fw*0.2), fx + int(fw*0.8))
        hair_rgb  = median_rgb(hair_roi, (35, 30, 25))
        if sum(hair_rgb) > sum(skin_rgb) * 0.88:
            hair_rgb = (int(hair_rgb[0]*0.38), int(hair_rgb[1]*0.38), int(hair_rgb[2]*0.38))

        shirt_roi = safe_roi(fy + fh, min(self.h, fy + fh + int(fh*0.7)), fx, fx + fw)
        shirt_rgb = median_rgb(shirt_roi, (30, 30, 30))

        # Casquette : zone TRÈS haute au-dessus du visage
        cap_roi   = safe_roi(max(0, fy - int(fh*0.55)), max(0, fy - int(fh*0.05)), fx, fx + fw)
        cap_rgb   = median_rgb(cap_roi, (200, 200, 200))

        # Barbe
        beard_roi = safe_roi(fy + int(fh*0.68), fy + fh, fx + int(fw*0.2), fx + int(fw*0.8))
        has_beard = False
        beard_rgb = tuple(max(0, c - 30) for c in hair_rgb)
        if beard_roi is not None and beard_roi.size > 0:
            b_bgr = (np.median(beard_roi[:,:,0]), np.median(beard_roi[:,:,1]), np.median(beard_roi[:,:,2]))
            skin_lum  = skin_rgb[0]*0.299 + skin_rgb[1]*0.587 + skin_rgb[2]*0.114
            beard_lum = b_bgr[2]*0.299 + b_bgr[1]*0.587 + b_bgr[0]*0.114
            if beard_lum < skin_lum * 0.74:
                has_beard = True
                beard_rgb = (int(b_bgr[2]), int(b_bgr[1]), int(b_bgr[0]))

        # Lunettes
        eye_roi = safe_roi(fy + int(fh*0.25), fy + int(fh*0.5), fx + int(fw*0.1), fx + int(fw*0.9))
        has_glasses = False
        if eye_roi is not None and eye_roi.size > 0:
            edges = cv2.Canny(cv2.cvtColor(eye_roi, cv2.COLOR_BGR2GRAY), 80, 180)
            if np.mean(edges) > 30:
                has_glasses = True

        print(f"  Zone visage  : x={fx} y={fy} w={fw} h={fh}")
        print(f"  Peau         : {skin_rgb}")
        print(f"  Cheveux      : {hair_rgb}")
        print(f"  Casquette    : {cap_rgb}")
        print(f"  Vêtement     : {shirt_rgb}")
        print(f"  Barbe        : {'Oui' if has_beard else 'Non'}  {beard_rgb if has_beard else ''}")
        print(f"  Lunettes     : {'Oui' if has_glasses else 'Non'}")

        return {
            "skin_color": skin_rgb,
            "hair_color": hair_rgb,
            "cap_color":  cap_rgb,
            "shirt_color": shirt_rgb,
            "has_beard": has_beard,
            "beard_color": beard_rgb,
            "has_glasses": has_glasses,
        }


# ══════════════════════════════════════════════════════════════════
#  RENDU VECTORIEL 2D WANKUL
# ══════════════════════════════════════════════════════════════════
class WankulRenderer:
    W, H = 800, 960

    def render(self, traits: dict, output_path: str = "wankul_character.png") -> str:
        img  = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d    = ImageDraw.Draw(img)

        skin    = traits.get("skin_color",  (225, 180, 140))
        hair    = traits.get("hair_color",  (38, 32, 26))
        cap     = traits.get("cap_color",   (210, 210, 215))
        shirt   = traits.get("shirt_color", (22, 22, 25))
        beard_c = traits.get("beard_color", (42, 34, 26))
        has_beard   = traits.get("has_beard",   False)
        has_glasses = traits.get("has_glasses", False)

        lc = (12, 12, 18)   # ligne noire BD
        sw = 7               # stroke width

        # ── Corps ──────────────────────────────────────────────────────
        d.polygon([(215, 570), (585, 570), (660, 960), (140, 960)],
                  fill=shirt, outline=lc, width=sw)
        d.polygon([(215, 570), (95, 750), (165, 788), (270, 620)],
                  fill=shirt, outline=lc, width=sw)
        d.polygon([(585, 570), (705, 750), (635, 788), (530, 620)],
                  fill=shirt, outline=lc, width=sw)

        # Rayures blanches Adidas (épaule gauche)
        for k in range(3):
            ox = k * 18
            d.line([(215+ox, 572), (145+ox, 670)], fill=(240, 240, 240), width=8)

        # Logo HP (manche gauche)
        d.ellipse((108, 690, 164, 746), fill=(255, 255, 255), outline=lc, width=4)
        d.text((118, 703), "hp", fill=(10, 10, 10))

        # Logo Vitality jaune
        vit_pts = [(360, 590), (400, 700), (440, 590), (415, 590), (400, 655), (385, 590)]
        d.polygon(vit_pts, fill=(255, 210, 0), outline=lc, width=4)

        # Col
        d.polygon([(330, 570), (400, 615), (470, 570)],
                  fill=skin, outline=lc, width=sw)

        # ── Cou ────────────────────────────────────────────────────────
        d.rectangle((345, 500, 455, 590), fill=skin, outline=lc, width=sw)

        # ── Oreilles ───────────────────────────────────────────────────
        d.ellipse((228, 360, 278, 435), fill=skin, outline=lc, width=sw)
        d.ellipse((522, 360, 572, 435), fill=skin, outline=lc, width=sw)

        # ── Tête ───────────────────────────────────────────────────────
        d.ellipse((255, 190, 545, 520), fill=skin, outline=lc, width=sw)

        # ── Casquette Snapback ──────────────────────────────────────────
        # Visière (rouge légèrement différent de la casquette)
        visor_c = (min(255, cap[0]+10), max(0, cap[1]-60), max(0, cap[2]-60))
        d.polygon([(175, 248), (625, 248), (600, 285), (200, 285)],
                  fill=visor_c, outline=lc, width=sw)
        # Dôme
        d.chord((248, 105, 552, 258), start=180, end=360, fill=cap, outline=lc, width=sw)
        # Bouton du dessus
        d.ellipse((382, 108, 418, 130), fill=tuple(max(0,c-20) for c in cap), outline=lc, width=4)

        # ── Barbe ──────────────────────────────────────────────────────
        if has_beard:
            d.arc((270, 360, 530, 515), start=22, end=158, fill=beard_c, width=28)
            mous = [(355, 444), (400, 428), (445, 444), (400, 466)]
            d.polygon(mous, fill=beard_c, outline=lc, width=4)

        # ── Yeux Wankul ────────────────────────────────────────────────
        d.ellipse((308, 308, 378, 378), fill=(255,255,255), outline=lc, width=sw)
        d.ellipse((334, 330, 358, 354), fill=(28,20,14))
        d.ellipse((347, 333, 354, 340), fill=(255,255,255))

        d.ellipse((422, 308, 492, 378), fill=(255,255,255), outline=lc, width=sw)
        d.ellipse((436, 330, 460, 354), fill=(28,20,14))
        d.ellipse((449, 333, 456, 340), fill=(255,255,255))

        # Sourcils
        d.polygon([(298, 296), (382, 288), (378, 272), (304, 278)], fill=hair, outline=lc, width=4)
        d.polygon([(418, 288), (502, 296), (496, 278), (422, 272)], fill=hair, outline=lc, width=4)

        # ── Nez ────────────────────────────────────────────────────────
        nose_c = tuple(max(0, c-55) for c in skin)
        d.line([(400, 350), (388, 398), (416, 400)], fill=nose_c, width=5)

        # ── Bouche sourire ─────────────────────────────────────────────
        d.arc((360, 436, 440, 482), start=10, end=170, fill=lc, width=6)
        d.arc((368, 438, 432, 470), start=15, end=165, fill=(255,255,255), width=8)

        # ── Lunettes ───────────────────────────────────────────────────
        if has_glasses:
            fc = tuple(max(0, c-60) for c in hair)
            d.rectangle((298, 302, 386, 382), outline=fc, width=9)
            d.rectangle((414, 302, 502, 382), outline=fc, width=9)
            d.line([(386, 338), (414, 338)], fill=fc, width=9)
            d.line([(298, 338), (238, 350)], fill=fc, width=8)
            d.line([(502, 338), (562, 350)], fill=fc, width=8)

        # ── Contour sticker noir épais ─────────────────────────────────
        alpha  = np.array(img)[:, :, 3]
        kernel = np.ones((16, 16), np.uint8)
        dilated = cv2.dilate(alpha, kernel, iterations=1)

        stroke_mask = Image.fromarray(dilated)
        black_bg    = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 255))
        final       = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        final.paste(black_bg, (0, 0), stroke_mask)
        final.paste(img,      (0, 0), img)

        final.save(output_path, "PNG")
        return output_path


# ══════════════════════════════════════════════════════════════════
#  MODE FILTRE BD / CARTOON
# ══════════════════════════════════════════════════════════════════
def apply_wankul_filter(input_path: str, output_path: str = "wankul_filter.png") -> str:
    img = cv2.imread(input_path)
    if img is None:
        raise ValueError(f"Impossible de lire l'image {input_path}")

    h, w = img.shape[:2]

    mask = np.zeros((h, w), np.uint8)
    bgdM = np.zeros((1, 65), np.float64)
    fgdM = np.zeros((1, 65), np.float64)
    rect = (int(w*0.04), int(h*0.04), int(w*0.92), int(h*0.92))
    try:
        cv2.grabCut(img, mask, rect, bgdM, fgdM, 5, cv2.GC_INIT_WITH_RECT)
        alpha_mask = np.where((mask == 2) | (mask == 0), 0, 255).astype(np.uint8)
    except Exception:
        alpha_mask = np.full((h, w), 255, dtype=np.uint8)
    alpha_mask = cv2.GaussianBlur(alpha_mask, (5, 5), 0)

    color = img.copy()
    for _ in range(7):
        color = cv2.bilateralFilter(color, d=9, sigmaColor=38, sigmaSpace=38)

    data  = np.float32(color).reshape((-1, 3))
    crit  = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.2)
    _, labels, centers = cv2.kmeans(data, 12, None, crit, 10, cv2.KMEANS_RANDOM_CENTERS)
    centers   = np.uint8(centers)
    quantized = centers[labels.flatten()].reshape(color.shape)

    gray   = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges  = cv2.adaptiveThreshold(
        cv2.medianBlur(gray, 5), 255,
        cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 3
    )
    edges  = cv2.erode(edges, np.ones((2,2), np.uint8), iterations=1)
    cartoon = cv2.bitwise_and(quantized, cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR))

    b, g, r = cv2.split(cartoon)
    pil = Image.fromarray(cv2.cvtColor(cv2.merge([b, g, r, alpha_mask]), cv2.COLOR_BGRA2RGBA))

    a_np    = np.array(pil.split()[3])
    dilated = cv2.dilate(a_np, np.ones((12, 12), np.uint8), iterations=1)

    stroke_mask  = Image.fromarray(dilated)
    black_layer  = Image.new("RGBA", pil.size, (0, 0, 0, 255))
    final        = Image.new("RGBA", pil.size, (0, 0, 0, 0))
    final.paste(black_layer, (0, 0), stroke_mask)
    final.paste(pil,         (0, 0), pil)
    final.save(output_path, "PNG")
    return output_path


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Générateur de personnage style Wankul Studio 2D")
    parser.add_argument("image", help="Chemin de l'image source (JPG/PNG)")
    parser.add_argument("-o", "--output", default="wankul_character.png")
    parser.add_argument("-m", "--mode", choices=["vector", "filter"], default="vector")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"[ERREUR] Fichier introuvable : {args.image}")
        sys.exit(1)

    print("=" * 60)
    print("   WANKUL CHARACTER GENERATOR  v2.0")
    print("=" * 60)
    print(f"Image  : {args.image}")
    print(f"Mode   : {args.mode}")
    print(f"Sortie : {args.output}")
    print("-" * 60)

    if args.mode == "vector":
        print("[1/2] Analyse de l'image...")
        traits = WankulAnalyzer(args.image).analyze()
        print("[2/2] Dessin du personnage 2D Wankul...")
        out = WankulRenderer().render(traits, args.output)
    else:
        print("[1/1] Application du filtre Cartoon/BD Wankul...")
        out = apply_wankul_filter(args.image, args.output)

    print("-" * 60)
    print(f"[OK] => {os.path.abspath(out)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
