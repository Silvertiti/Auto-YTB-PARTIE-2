import sys
import os
import glob
import cv2
import shutil
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from ultralytics import YOLO

# Configurer UTF-8 pour la console Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def remove_emojis(text):
    """Supprime les émojis et caractères spéciaux non supportés par la police."""
    return ''.join(c for c in text if ord(c) < 0x2000 or (0x20A0 <= ord(c) <= 0x25FF)).strip()

def detect_face_or_person(image_path, model_path="yolov8n.pt"):
    """Détecte la position exacte du streamer (personne / visage) via YOLOv8."""
    if os.path.exists(model_path):
        try:
            model = YOLO(model_path)
            results = model.predict(source=image_path, classes=[0], conf=0.3, save=False, verbose=False)
            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    marge = 25
                    img = cv2.imread(image_path)
                    if img is not None:
                        h, w, _ = img.shape
                        return (
                            max(0, x1 - marge),
                            max(0, y1 - marge),
                            min(w, x2 + marge) - max(0, x1 - marge),
                            min(h, y2 + marge) - max(0, y1 - marge)
                        )
        except Exception:
            pass

    return (650, 80, 500, 580)

def extract_valid_frame(video_path, output_frame, offset_sec=5):
    """Extrait une frame lisible et nette depuis un clip vidéo à un timestamp précis."""
    try:
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 100)
            target_frame = min(total_frames - 5, max(5, int(offset_sec * fps)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None and frame.shape[0] > 0:
                cv2.imwrite(output_frame, frame)
                return output_frame
    except Exception:
        pass
    return None

def fit_font_size(text, font_path, initial_size, max_w):
    """Ajuste automatiquement la taille de police pour qu'elle rentre strictement dans max_w."""
    txt_clean = remove_emojis(text)
    size = initial_size
    while size >= 28:
        try:
            font = ImageFont.truetype(font_path, size) if font_path and os.path.exists(font_path) else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()
            
        if hasattr(font, 'getbbox'):
            bbox = font.getbbox(txt_clean)
            w = bbox[2] - bbox[0]
        else:
            w = len(txt_clean) * (size * 0.55)
            
        if w <= max_w:
            return font, size, int(w)
        size -= 3
    return font, size, int(max_w)

def draw_text_stroke(draw, pos, txt, font, fill_color=(255, 235, 0), stroke_color=(0, 0, 0), stroke_w=8):
    txt_clean = remove_emojis(txt)
    if not txt_clean:
        return
    x_p, y_p = pos
    for dx in range(-stroke_w, stroke_w + 1):
        for dy in range(-stroke_w, stroke_w + 1):
            if dx * dx + dy * dy <= stroke_w * stroke_w:
                draw.text((x_p + dx, y_p + dy), txt_clean, font=font, fill=stroke_color)
    draw.text((x_p, y_p), txt_clean, font=font, fill=fill_color)

def generate_dynamic_thumbnail(pattern_id, video_path, output_path, line1, line2=""):
    FINAL_W, FINAL_H = 1280, 720
    frame_tmp = f"temp_frame_{pattern_id}.jpg"
    
    extracted = extract_valid_frame(video_path, frame_tmp, offset_sec=pattern_id * 2 + 3)
    if not extracted or not os.path.exists(extracted):
        extracted = "real_streamer_frame.jpg" if os.path.exists("real_streamer_frame.jpg") else "extracted_frame.jpg"
        
    base_img = Image.open(extracted).convert("RGB").resize((FINAL_W, FINAL_H), Image.Resampling.LANCZOS)
    
    # 1. Détection de la position du streamer
    crop_box = detect_face_or_person(extracted)
    x, y, w, h = crop_box
    orig_w, orig_h = Image.open(extracted).size
    scale_x = FINAL_W / orig_w
    scale_y = FINAL_H / orig_h
    
    crop_x1 = int(x * scale_x)
    crop_y1 = int(y * scale_y)
    crop_x2 = int((x + w) * scale_x)
    crop_y2 = int((y + h) * scale_y)
    
    subject = base_img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
    target_w, target_h = subject.width, subject.height
    
    # 2. Calcul du placement du streamer et de la largeur maximale autorisée pour le texte
    head_center_x = (crop_x1 + crop_x2) / 2
    
    if head_center_x > FINAL_W * 0.5:
        # Streamer à DROITE -> Texte à GAUCHE (Marge sécurité [50, max_w])
        pos_x = FINAL_W - target_w - 40
        text_align_x = 55
        max_text_w = min(620, pos_x - 70)
    else:
        # Streamer à GAUCHE -> Texte à DROITE
        pos_x = 40
        text_align_x = max(550, pos_x + target_w + 30)
        max_text_w = FINAL_W - text_align_x - 55

    pos_y = max(30, min(FINAL_H - target_h - 20, FINAL_H - (crop_y2 - crop_y1) - 20))
    
    mask = Image.new("L", (target_w, target_h), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, target_w, target_h), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(8))

    # 3. Calcul anti-débordement dynamique de la police d'écriture
    font_path = "Nunito-Black.ttf" if os.path.exists("Nunito-Black.ttf") else None
    
    font1, size1, w1 = fit_font_size(line1, font_path, initial_size=82, max_w=max_text_w)
    font2, size2, w2 = fit_font_size(line2, font_path, initial_size=75, max_w=max_text_w) if line2 else (font1, 0, 0)
    
    text_y1 = 180 if head_center_x > FINAL_W * 0.5 else 160

    # 4. Rendus des 10 Styles Visuels
    bg = base_img.filter(ImageFilter.GaussianBlur(16))
    bg = ImageEnhance.Brightness(bg).enhance(0.38)

    if pattern_id == 1: # Neon Yellow
        glow_m = 45
        glow = Image.new("RGBA", (target_w + glow_m*2, target_h + glow_m*2), (0,0,0,0))
        ImageDraw.Draw(glow).ellipse((glow_m, glow_m, glow_m+target_w, glow_m+target_h), fill=(255, 220, 0, 230))
        glow = glow.filter(ImageFilter.GaussianBlur(30))
        bg.paste(glow, (pos_x - glow_m, pos_y - glow_m), glow)
        bg.paste(subject, (pos_x, pos_y), mask)
        draw = ImageDraw.Draw(bg)
        draw_text_stroke(draw, (text_align_x, text_y1), line1, font1, fill_color=(255, 235, 0))
        if line2: draw_text_stroke(draw, (text_align_x, text_y1 + size1 + 15), line2, font2, fill_color=(255, 255, 255))

    elif pattern_id == 2: # Cyberpunk Cyan/Red
        glow_m = 50
        glow = Image.new("RGBA", (target_w + glow_m*2, target_h + glow_m*2), (0,0,0,0))
        ImageDraw.Draw(glow).ellipse((glow_m-10, glow_m, glow_m+target_w-10, glow_m+target_h), fill=(255, 0, 80, 230))
        ImageDraw.Draw(glow).ellipse((glow_m+10, glow_m, glow_m+target_w+10, glow_m+target_h), fill=(0, 240, 255, 230))
        glow = glow.filter(ImageFilter.GaussianBlur(25))
        bg.paste(glow, (pos_x - glow_m, pos_y - glow_m), glow)
        bg.paste(subject, (pos_x, pos_y), mask)
        draw = ImageDraw.Draw(bg)
        draw_text_stroke(draw, (text_align_x, text_y1), line1, font1, fill_color=(0, 240, 255), stroke_color=(255, 0, 80))
        if line2: draw_text_stroke(draw, (text_align_x, text_y1 + size1 + 15), line2, font2, fill_color=(255, 255, 255))

    elif pattern_id == 3: # Slash Orange / Clash
        draw = ImageDraw.Draw(bg)
        slash_x = 620 if head_center_x > FINAL_W * 0.5 else 640
        draw.polygon([(slash_x, 0), (slash_x + 60, 0), (slash_x - 80, 720), (slash_x - 140, 720)], fill=(255, 60, 0))
        bg.paste(subject, (pos_x, pos_y), mask)
        draw_text_stroke(draw, (text_align_x, text_y1), line1, font1, fill_color=(255, 60, 0))
        if line2: draw_text_stroke(draw, (text_align_x, text_y1 + size1 + 15), line2, font2, fill_color=(255, 220, 0))

    elif pattern_id == 4: # Gold Masterclass
        glow_m = 40
        glow = Image.new("RGBA", (target_w + glow_m*2, target_h + glow_m*2), (0,0,0,0))
        ImageDraw.Draw(glow).ellipse((glow_m, glow_m, glow_m+target_w, glow_m+target_h), fill=(255, 180, 0, 240))
        glow = glow.filter(ImageFilter.GaussianBlur(20))
        bg.paste(glow, (pos_x - glow_m, pos_y - glow_m), glow)
        bg.paste(subject, (pos_x, pos_y), mask)
        draw = ImageDraw.Draw(bg)
        draw_text_stroke(draw, (text_align_x, text_y1), line1, font1, fill_color=(255, 215, 0), stroke_color=(70, 45, 0))
        if line2: draw_text_stroke(draw, (text_align_x, text_y1 + size1 + 15), line2, font2, fill_color=(255, 255, 255))

    elif pattern_id == 5: # Danger Warning Red
        draw = ImageDraw.Draw(bg)
        for i in range(0, 1300, 60):
            draw.polygon([(i, 0), (i + 30, 0), (i - 20, 40), (i - 50, 40)], fill=(255, 30, 30))
            draw.polygon([(i, 680), (i + 30, 680), (i - 20, 720), (i - 50, 720)], fill=(255, 30, 30))
        glow_m = 40
        glow = Image.new("RGBA", (target_w + glow_m*2, target_h + glow_m*2), (0,0,0,0))
        ImageDraw.Draw(glow).ellipse((glow_m, glow_m, glow_m+target_w, glow_m+target_h), fill=(255, 0, 0, 230))
        glow = glow.filter(ImageFilter.GaussianBlur(25))
        bg.paste(glow, (pos_x - glow_m, pos_y - glow_m), glow)
        bg.paste(subject, (pos_x, pos_y), mask)
        draw_text_stroke(draw, (text_align_x, text_y1), line1, font1, fill_color=(255, 40, 40))
        if line2: draw_text_stroke(draw, (text_align_x, text_y1 + size1 + 15), line2, font2, fill_color=(255, 255, 255))

    elif pattern_id == 6: # Purple Pink Wave
        glow_m = 45
        glow = Image.new("RGBA", (target_w + glow_m*2, target_h + glow_m*2), (0,0,0,0))
        ImageDraw.Draw(glow).ellipse((glow_m, glow_m, glow_m+target_w, glow_m+target_h), fill=(200, 0, 255, 230))
        glow = glow.filter(ImageFilter.GaussianBlur(30))
        bg.paste(glow, (pos_x - glow_m, pos_y - glow_m), glow)
        bg.paste(subject, (pos_x, pos_y), mask)
        draw = ImageDraw.Draw(bg)
        draw_text_stroke(draw, (text_align_x, text_y1), line1, font1, fill_color=(255, 0, 200), stroke_color=(50, 0, 80))
        if line2: draw_text_stroke(draw, (text_align_x, text_y1 + size1 + 15), line2, font2, fill_color=(0, 255, 230))

    elif pattern_id == 7: # Manga Speed Lines
        draw = ImageDraw.Draw(bg)
        cx, cy = FINAL_W // 2, FINAL_H // 2
        for angle in range(0, 360, 15):
            rad = np.radians(angle)
            x2 = int(cx + 1000 * np.cos(rad))
            y2 = int(cy + 1000 * np.sin(rad))
            draw.line([(cx, cy), (x2, y2)], fill=(255, 255, 255, 25), width=4)
        glow_m = 35
        glow = Image.new("RGBA", (target_w + glow_m*2, target_h + glow_m*2), (0,0,0,0))
        ImageDraw.Draw(glow).ellipse((glow_m, glow_m, glow_m+target_w, glow_m+target_h), fill=(255, 255, 0, 240))
        glow = glow.filter(ImageFilter.GaussianBlur(15))
        bg.paste(glow, (pos_x - glow_m, pos_y - glow_m), glow)
        bg.paste(subject, (pos_x, pos_y), mask)
        draw_text_stroke(draw, (text_align_x, text_y1), line1, font1, fill_color=(255, 230, 0), stroke_w=11)
        if line2: draw_text_stroke(draw, (text_align_x, text_y1 + size1 + 15), line2, font2, fill_color=(255, 255, 255), stroke_w=11)

    elif pattern_id == 8: # Drama Vignette Cyan
        glow_m = 50
        glow = Image.new("RGBA", (target_w + glow_m*2, target_h + glow_m*2), (0,0,0,0))
        ImageDraw.Draw(glow).ellipse((glow_m, glow_m, glow_m+target_w, glow_m+target_h), fill=(0, 230, 255, 240))
        glow = glow.filter(ImageFilter.GaussianBlur(28))
        bg.paste(glow, (pos_x - glow_m, pos_y - glow_m), glow)
        bg.paste(subject, (pos_x, pos_y), mask)
        draw = ImageDraw.Draw(bg)
        draw_text_stroke(draw, (text_align_x, text_y1), line1, font1, fill_color=(0, 230, 255))
        if line2: draw_text_stroke(draw, (text_align_x, text_y1 + size1 + 15), line2, font2, fill_color=(255, 255, 255))

    elif pattern_id == 9: # Fire Flame Explosion
        glow_m = 50
        glow = Image.new("RGBA", (target_w + glow_m*2, target_h + glow_m*2), (0,0,0,0))
        ImageDraw.Draw(glow).ellipse((glow_m, glow_m, glow_m+target_w, glow_m+target_h), fill=(255, 80, 0, 240))
        glow = glow.filter(ImageFilter.GaussianBlur(25))
        bg.paste(glow, (pos_x - glow_m, pos_y - glow_m), glow)
        bg.paste(subject, (pos_x, pos_y), mask)
        draw = ImageDraw.Draw(bg)
        draw_text_stroke(draw, (text_align_x, text_y1), line1, font1, fill_color=(255, 100, 0), stroke_color=(80, 10, 0))
        if line2: draw_text_stroke(draw, (text_align_x, text_y1 + size1 + 15), line2, font2, fill_color=(255, 220, 0))

    else: # Pattern 10: Pill Highlight Box
        glow_m = 40
        glow = Image.new("RGBA", (target_w + glow_m*2, target_h + glow_m*2), (0,0,0,0))
        ImageDraw.Draw(glow).ellipse((glow_m, glow_m, glow_m+target_w, glow_m+target_h), fill=(255, 255, 255, 220))
        glow = glow.filter(ImageFilter.GaussianBlur(20))
        bg.paste(glow, (pos_x - glow_m, pos_y - glow_m), glow)
        bg.paste(subject, (pos_x, pos_y), mask)
        draw = ImageDraw.Draw(bg)
        
        # Rectangles de surlignage sous le texte dimensionnés exactement à w1 et w2
        draw.rectangle([(text_align_x - 10, text_y1 - 5), (text_align_x + w1 + 20, text_y1 + size1 + 10)], fill=(255, 220, 0))
        draw.text((text_align_x, text_y1), line1, font=font1, fill=(0, 0, 0))
        
        if line2:
            draw.rectangle([(text_align_x - 10, text_y1 + size1 + 15), (text_align_x + w2 + 20, text_y1 + size1 + size2 + 30)], fill=(255, 255, 255))
            draw.text((text_align_x, text_y1 + size1 + 20), line2, font=font2, fill=(0, 0, 0))

    bg.save(output_path, quality=95)
    
    if os.path.exists(frame_tmp):
        try: os.remove(frame_tmp)
        except: pass
        
    return output_path

if __name__ == "__main__":
    out_dir = "thumbnails_variations"
    os.makedirs(out_dir, exist_ok=True)
    artifact_dir = r"C:\Users\PC THEOTIM\.gemini\antigravity-ide\brain\084a3cfa-f9a1-49a8-92dd-c8f902c40ce6"
    
    clips = glob.glob("clips_downloaded/*.mp4") + glob.glob("**/*.mp4", recursive=True)
    print(f"🎬 {len(clips)} clips trouvés pour les tests...")

    variations = [
        (1, "IL PÈTE UN CÂBLE !", "EN DIRECT SUR TWITCH"),
        (2, "PETAGE DE PLOMB !", "EN PLEIN STREAM"),
        (3, "CLASH AU SOMMET !", "IL A TOUT PERDU"),
        (4, "MASTERCLASS EN LIVE !", "LE CLIP INCROYABLE"),
        (5, "DANGER IMMINENT !", "NE FAITES PAS CA"),
        (6, "C'EST TOTALEMENT FOU !", "REACTION EXTREME"),
        (7, "LE PIRE MOMENT !", "IL S'EST FAIT AVOIR"),
        (8, "C'EST QUOI CE BORDEL ?!", "EXPLICABLE OU PAS"),
        (9, "RAGE QUITTE EN DIRECT !", "IL BRISE SON ÉCRAN"),
        (10, "TOUT EST FINI...", "C'ÉTAIT SÛR EN FAIT")
    ]
    
    for idx, (pid, l1, l2) in enumerate(variations):
        video_p = clips[idx * 3 % len(clips)] if clips else "real_streamer_frame.jpg"
        out_name = f"pattern_{pid}.jpg"
        out_p = os.path.join(out_dir, out_name)
        
        generate_dynamic_thumbnail(pid, video_p, out_p, l1, l2)
        shutil.copy2(out_p, os.path.join(artifact_dir, out_name))
        print(f"✅ Pattern {pid} généré sans débordement sur clip ({os.path.basename(video_p)}) : {out_p}")
