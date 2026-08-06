import cv2
import numpy as np
import os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

# Configurer UTF-8 pour la console Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def generate_wankil_character_sticker(input_image_path, output_png_path="wankil_character.png"):
    """
    Génère à partir de zéro un personnage 2D Cartoon / Wankil unique 
    avec FOND TRANSPARENT (PNG RGBA).
    """
    print(f"🎨 Génération du personnage Wankil 2D à partir de : {input_image_path}")

    if not os.path.exists(input_image_path):
        print(f"❌ Image d'entrée introuvable : {input_image_path}")
        return None

    img = cv2.imread(input_image_path)
    if img is None:
        return None

    h, w, _ = img.shape

    # 1. Détourage Automatique du Personnage (GrabCut / Segmentation)
    mask = np.zeros(img.shape[:2], np.uint8)
    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)

    # Rectangle englobant le personnage (marge intérieure de 5%)
    rect = (int(w * 0.05), int(h * 0.05), int(w * 0.9), int(h * 0.9))

    try:
        cv2.grabCut(img, mask, rect, bgdModel, fgdModel, 5, cv2.GC_INIT_WITH_RECT)
        fg_mask = np.where((mask == 2) | (mask == 0), 0, 1).astype('uint8')
    except Exception:
        # Fallback masque elliptique si GrabCut échoue
        fg_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.ellipse(fg_mask, (w // 2, h // 2), (w // 2 - 10, h // 2 - 10), 0, 0, 360, 1, -1)

    # Lisser le masque de détourage
    fg_mask_blur = cv2.GaussianBlur(fg_mask * 255, (7, 7), 0)

    # 2. Transformation Cartoon / Vectoriel 2D Wankil
    # a) Lissage des couleurs (Bilateral Filtering répétitif)
    color_smooth = img.copy()
    for _ in range(8):
        color_smooth = cv2.bilateralFilter(color_smooth, d=9, sigmaColor=40, sigmaSpace=40)

    # b) Quantification des couleurs (Aplats BD 2D)
    data = np.float32(color_smooth).reshape((-1, 3))
    K = 10  # 10 couleurs vives plates
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.2)
    _, labels, centers = cv2.kmeans(data, K, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
    centers = np.uint8(centers)
    quantized = centers[labels.flatten()].reshape(color_smooth.shape)

    # c) Création des traits noirs épais (Lineart Comic BD)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray_blur = cv2.medianBlur(gray, 5)
    edges = cv2.adaptiveThreshold(
        gray_blur, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY,
        blockSize=9,
        C=3
    )

    # Dilater légèrement les contours noirs pour l'effet Wankil
    kernel = np.ones((2, 2), np.uint8)
    edges_thick = cv2.erode(edges, kernel, iterations=1)
    edges_bgr = cv2.cvtColor(edges_thick, cv2.COLOR_GRAY2BGR)

    # Fusion de l'aplat de couleurs et des traits noirs
    cartoon = cv2.bitwise_and(quantized, edges_bgr)

    # 3. Assemblage de l'image RGBA avec Fond Transparent
    b, g, r = cv2.split(cartoon)
    rgba = cv2.merge([b, g, r, fg_mask_blur])

    # Convertir en Image PIL
    rgba_pil = Image.fromarray(cv2.cvtColor(rgba, cv2.COLOR_BGRA2RGBA))

    # 4. Ajout du Contour Extérieur Épais "Sticker BD" autour du personnage
    # Créer le contour extérieur du personnage
    alpha = rgba_pil.split()[3]
    outline = Image.new("RGBA", rgba_pil.size, (0, 0, 0, 0))
    draw_o = ImageDraw.Draw(outline)

    # Erodure / Dilatation de l'alpha pour tracer la ligne noire extérieure
    alpha_np = np.array(alpha)
    kernel_stroke = np.ones((12, 12), np.uint8)
    dilated_alpha = cv2.dilate(alpha_np, kernel_stroke, iterations=1)

    stroke_mask = Image.fromarray(dilated_alpha)
    outline_black = Image.new("RGBA", rgba_pil.size, (0, 0, 0, 255))

    # Assemblage final : Contour noir extérieur + Personnage 2D
    final_character = Image.new("RGBA", rgba_pil.size, (0, 0, 0, 0))
    final_character.paste(outline_black, (0, 0), stroke_mask)
    final_character.paste(rgba_pil, (0, 0), rgba_pil)

    # Sauvegarder le PNG transparent
    final_character.save(output_png_path, "PNG")
    print(f"✅ Personnage Wankil 2D généré avec FOND TRANSPARENT : {os.path.abspath(output_png_path)}")
    return output_png_path

if __name__ == "__main__":
    sample_image = "real_crop_clip_0.jpg"
    if not os.path.exists(sample_image):
        sample_image = "real_streamer_frame.jpg"
    generate_wankil_character_sticker(sample_image)
