import cv2
import numpy as np
import os, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

def cartoonize_image(img_path_or_bgr):
    """Transforme une photo/crop réelle de streamer en illustration Cartoon 2D."""
    if isinstance(img_path_or_bgr, str):
        img = cv2.imread(img_path_or_bgr)
    else:
        img = img_path_or_bgr
        
    if img is None:
        return None
        
    # 1. Réduction de bruit & lissage des couleurs (Bilateral Filter)
    num_bilateral = 7
    color = img
    for _ in range(num_bilateral):
        color = cv2.bilateralFilter(color, d=9, sigmaColor=35, sigmaSpace=35)
        
    # 2. Conversion en niveaux de gris & détection des contours (Canny/Adaptive Threshold)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray_blur = cv2.medianBlur(gray, 7)
    edges = cv2.adaptiveThreshold(
        gray_blur, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY,
        blockSize=9,
        C=4
    )
    
    # 3. Quantification des couleurs (Effet Aplats Cartoon 2D)
    data = np.float32(color).reshape((-1, 3))
    K = 12  # 12 couleurs dominantes
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.2)
    _, label, center = cv2.kmeans(data, K, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
    center = np.uint8(center)
    quantized = center[label.flatten()].reshape(color.shape)
    
    # 4. Fusion des contours noirs avec les aplats de couleurs
    edges_bgra = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
    cartoon = cv2.bitwise_and(quantized, edges_bgra)
    
    return cartoon

def build_wankil_style_thumbnail(streamer_crops, title_text="ILS ONT PÉTÉ UN CÂBLE !", output_path="cartoon_thumbnail_test.jpg"):
    """Assemble 3-4 streamers en mode Cartoon 2D avec poses et fond vibrant."""
    FINAL_W, FINAL_H = 1280, 720
    
    # Fond vert/jaune style Wankil / Cartoon
    bg_np = np.zeros((FINAL_H, FINAL_W, 3), dtype=np.uint8)
    bg_np[:, :] = (30, 180, 40) # Vert vibrant
    
    # Ajouter un motif dégradé / cercles
    cv2.circle(bg_np, (FINAL_W//2, FINAL_H//2), 600, (60, 220, 80), -1)
    cv2.circle(bg_np, (FINAL_W//2, FINAL_H//2), 350, (100, 240, 120), -1)
    
    bg_pil = Image.fromarray(cv2.cvtColor(bg_np, cv2.COLOR_BGR2RGB))
    bg_pil = bg_pil.filter(ImageFilter.GaussianBlur(10))
    
    # Positionner 3-4 streamers détourés et cartoonisés
    num_streamers = len(streamer_crops)
    if num_streamers > 0:
        spacing = FINAL_W // (num_streamers + 1)
        for i, crop_path in enumerate(streamer_crops[:4]):
            if os.path.exists(crop_path):
                c_img = cartoonize_image(crop_path)
                if c_img is not None:
                    c_rgb = cv2.cvtColor(c_img, cv2.COLOR_BGR2RGB)
                    pil_crop = Image.fromarray(c_rgb)
                    
                    # Redimensionner en grand (hauteur 420px)
                    h_target = 420
                    w_target = int(pil_crop.width * (h_target / pil_crop.height))
                    pil_crop = pil_crop.resize((w_target, h_target), Image.Resampling.LANCZOS)
                    
                    # Masque ovale
                    mask = Image.new("L", (w_target, h_target), 0)
                    ImageDraw.Draw(mask).ellipse((0, 0, w_target, h_target), fill=255)
                    mask = mask.filter(ImageFilter.GaussianBlur(6))
                    
                    # Contour noir cartoon épais
                    outline = Image.new("RGBA", (w_target+20, h_target+20), (0,0,0,0))
                    ImageDraw.Draw(outline).ellipse((5, 5, w_target+15, h_target+15), fill=(0,0,0,255))
                    
                    pos_x = int((i + 1) * spacing - w_target // 2)
                    pos_y = FINAL_H - h_target - 30
                    
                    bg_pil.paste(outline, (pos_x-10, pos_y-10), outline)
                    bg_pil.paste(pil_crop, (pos_x, pos_y), mask)

    # Ajouter le Texte Géant 3D Clickbait Pute-à-clique sur le haut
    draw = ImageDraw.Draw(bg_pil)
    font_path = "Nunito-Black.ttf" if os.path.exists("Nunito-Black.ttf") else None
    try: font = ImageFont.truetype(font_path, 85) if font_path else ImageFont.load_default()
    except: font = ImageFont.load_default()
    
    # Texte Ombré 3D
    tx, ty = 80, 80
    words = title_text.split()
    line1 = " ".join(words[:len(words)//2]) if len(words) > 2 else title_text
    line2 = " ".join(words[len(words)//2:]) if len(words) > 2 else ""
    
    def draw_3d_text(x, y, text_str, fill_color=(255, 235, 0)):
        for offset in range(12, 0, -1):
            draw.text((x + offset, y + offset), text_str, font=font, fill=(0, 0, 0))
        draw.text((x, y), text_str, font=font, fill=fill_color)
        
    draw_3d_text(tx, ty, line1, fill_color=(255, 255, 255))
    if line2:
        draw_3d_text(tx, ty + 100, line2, fill_color=(255, 220, 0))
        
    bg_pil.save(output_path, quality=95)
    print(f"✅ Miniature Style Cartoon Wankil créée : {os.path.abspath(output_path)}")
    return output_path

if __name__ == "__main__":
    crops = ["extracted_frame.jpg", "real_streamer_frame.jpg"]
    build_wankil_style_thumbnail(crops)
