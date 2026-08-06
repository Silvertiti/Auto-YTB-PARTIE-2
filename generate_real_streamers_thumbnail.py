import cv2
import numpy as np
import os, sys, glob, shutil
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from ultralytics import YOLO

# Configurer UTF-8 pour la console Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def convert_photo_to_wankil_cartoon(img_bgr):
    """Convertit localement la photo d'un streamer en illustration 2D Cartoon Wankil (100% Gratuit & Local)."""
    if img_bgr is None or img_bgr.size == 0:
        return None
        
    try:
        # 1. Stylisation lissage des couleurs (Look BD / Dessin vectoriel 2D)
        style = cv2.stylization(img_bgr, sigma_s=55, sigma_r=0.42)
        
        # 2. Rehaussement des contours et des détails du visage
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        blur_g = cv2.medianBlur(gray, 5)
        edges = cv2.adaptiveThreshold(blur_g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 3)
        edges_bgr = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        
        # 3. Fusion des aplats de couleurs BD et des contours noirs
        cartoon = cv2.bitwise_and(style, edges_bgr)
        return cartoon
    except Exception:
        return img_bgr

def get_valid_unique_clips(limit=4):
    """Sélectionne jusqu'à N clips vidéos uniques et lisibles."""
    all_clips = glob.glob("clips_downloaded/*.mp4") + glob.glob("**/*.mp4", recursive=True)
    valid_clips = []
    
    for c_path in all_clips:
        if not os.path.exists(c_path) or os.path.getsize(c_path) < 10000:
            continue
        try:
            cap = cv2.VideoCapture(c_path)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None and frame.shape[0] > 100 and frame.shape[1] > 100:
                    if c_path not in valid_clips:
                        valid_clips.append(c_path)
                        if len(valid_clips) >= limit:
                            break
        except Exception:
            pass
            
    return valid_clips

def extract_real_face_crop(video_path, output_crop_path):
    """Extrait le VRAI crop du visage/streamer depuis un clip."""
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
            
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 100)
        target = min(60, max(5, total // 3))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        ret, frame = cap.read()
        cap.release()
        
        if not ret or frame is None or frame.shape[0] == 0:
            return None

        # Détection YOLO de la personne/streamer
        model_path = "yolov8n.pt"
        if os.path.exists(model_path):
            try:
                model = YOLO(model_path)
                results = model.predict(source=frame, classes=[0], conf=0.25, save=False, verbose=False)
                for r in results:
                    for box in r.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        h_person = y2 - y1
                        head_y2 = y1 + int(h_person * 0.40)
                        x1_c = max(0, x1 - 10)
                        y1_c = max(0, y1 - 10)
                        x2_c = min(frame.shape[1], x2 + 10)
                        y2_c = min(frame.shape[0], head_y2)
                        
                        crop = frame[y1_c:y2_c, x1_c:x2_c]
                        if crop.size > 0 and crop.shape[0] > 40 and crop.shape[1] > 40:
                            cv2.imwrite(output_crop_path, crop)
                            return output_crop_path
            except Exception:
                pass

        h, w, _ = frame.shape
        crop_fallback = frame[int(h * 0.05):int(h * 0.50), int(w * 0.30):int(w * 0.70)]
        if crop_fallback.size > 0:
            cv2.imwrite(output_crop_path, crop_fallback)
            return output_crop_path
    except Exception:
        pass
        
    return None

def build_wankil_multi_clips_thumbnail(title_line1="JLTOMY ET INOXTAG !", title_line2="ILS ONT PÉTÉ UN CÂBLE", output_path="thumbnail_heads_scene.jpg"):
    print("🖼️ Génération de la miniature Cartoon Wankil (IA Locale OpenCV Stylization)...")
    FINAL_W, FINAL_H = 1280, 720

    clips = get_valid_unique_clips(limit=4)
    if not clips:
        print("❌ Aucun clip vidéo valide trouvé.")
        return None

    # 1. Arrière-plan Cartoon Gaming Wankil (Vert lime avec rayons manga)
    bg_np = np.zeros((FINAL_H, FINAL_W, 3), dtype=np.uint8)
    bg_np[:, :] = (30, 180, 45)
    
    cx, cy = FINAL_W // 2, FINAL_H // 2
    for angle in range(0, 360, 12):
        rad = np.radians(angle)
        x2 = int(cx + 1000 * np.cos(rad))
        y2 = int(cy + 1000 * np.sin(rad))
        cv2.line(bg_np, (cx, cy), (x2, y2), (70, 225, 90), 4)
        
    bg_pil = Image.fromarray(cv2.cvtColor(bg_np, cv2.COLOR_BGR2RGB))
    bg_pil = bg_pil.filter(ImageFilter.GaussianBlur(5))

    # 2. Extraire et transformer chaque visage de streamer en Cartoon 2D
    crop_files = []
    for idx, clip_path in enumerate(clips):
        out_f = f"real_crop_clip_{idx}.jpg"
        res = extract_real_face_crop(clip_path, out_f)
        if res and os.path.exists(res):
            # Application de l'IA locale Cartoon Wankil sur le crop
            img_bgr = cv2.imread(res)
            cartoon_bgr = convert_photo_to_wankil_cartoon(img_bgr)
            out_cartoon = f"cartoon_head_{idx}.jpg"
            cv2.imwrite(out_cartoon, cartoon_bgr)
            crop_files.append(out_cartoon)

    num = len(crop_files)
    if num > 0:
        spacing = FINAL_W // (num + 1)
        for i, crop_p in enumerate(crop_files):
            raw_img = Image.open(crop_p).convert("RGB")
            
            # Rehausser la saturation pour l'effet BD
            raw_img = ImageEnhance.Color(raw_img).enhance(1.3)

            target_w = 260
            target_h = int(raw_img.height * (target_w / raw_img.width))
            raw_img = raw_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

            # Masque Rectangle aux bords légèrement arrondis (Sticker Cutout)
            mask = Image.new("L", (target_w, target_h), 0)
            draw_m = ImageDraw.Draw(mask)
            radius = 18
            draw_m.rounded_rectangle((0, 0, target_w, target_h), radius=radius, fill=255)

            # Glow Jaune Néon
            glow_padding = 16
            glow = Image.new("RGBA", (target_w + glow_padding * 2, target_h + glow_padding * 2), (0, 0, 0, 0))
            draw_g = ImageDraw.Draw(glow)
            draw_g.rounded_rectangle((0, 0, target_w + glow_padding * 2, target_h + glow_padding * 2), radius=radius + 8, fill=(255, 230, 0, 240))
            glow = glow.filter(ImageFilter.GaussianBlur(12))

            # Contour Noir Épais Wankil BD
            border_b = Image.new("RGBA", (target_w + 12, target_h + 12), (0, 0, 0, 0))
            draw_b = ImageDraw.Draw(border_b)
            draw_b.rounded_rectangle((0, 0, target_w + 12, target_h + 12), radius=radius + 4, fill=(0, 0, 0, 255))

            pos_x = int((i + 1) * spacing - target_w // 2)
            pos_y = FINAL_H - target_h - 35

            bg_pil.paste(glow, (pos_x - glow_padding, pos_y - glow_padding), glow)
            bg_pil.paste(border_b, (pos_x - 6, pos_y - 6), border_b)
            bg_pil.paste(raw_img, (pos_x, pos_y), mask)

    # 3. Incrustation du Texte 3D Clickbait
    draw = ImageDraw.Draw(bg_pil)
    font_path = "Nunito-Black.ttf" if os.path.exists("Nunito-Black.ttf") else None
    
    max_l = max(len(title_line1), len(title_line2))
    f_size = 88 if max_l <= 14 else (70 if max_l <= 22 else 58)
    
    try: font = ImageFont.truetype(font_path, f_size) if font_path else ImageFont.load_default()
    except: font = ImageFont.load_default()

    def draw_3d_text(x, y, txt, fill_c=(255, 235, 0)):
        for off in range(12, 0, -1):
            draw.text((x + off, y + off), txt, font=font, fill=(0, 0, 0))
        draw.text((x, y), txt, font=font, fill=fill_c)

    tx = 60
    draw_3d_text(tx, 45, title_line1, fill_c=(255, 255, 255))
    if title_line2:
        draw_3d_text(tx, 45 + f_size + 15, title_line2, fill_c=(255, 220, 0))

    bg_pil.save(output_path, quality=95)
    print(f"✅ Miniature Wankil Cartoon créée avec succès : {os.path.abspath(output_path)}")
    return output_path

if __name__ == "__main__":
    build_wankil_multi_clips_thumbnail()
