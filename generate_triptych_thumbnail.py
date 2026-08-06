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

def get_3_distinct_valid_clips():
    """Récupère 3 clips vidéos 100% DISTINCTS et VALIDES."""
    all_clips = glob.glob("clips_downloaded/*.mp4") + glob.glob("**/*.mp4", recursive=True)
    distinct_clips = []
    
    for c_path in all_clips:
        if not os.path.exists(c_path) or os.path.getsize(c_path) < 10000:
            continue
        try:
            cap = cv2.VideoCapture(c_path)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None and frame.shape[0] > 100 and frame.shape[1] > 100:
                    if c_path not in distinct_clips:
                        distinct_clips.append(c_path)
                        print(f"🎬 Clip distinct {len(distinct_clips)} sélectionné : {os.path.basename(c_path)}")
                        if len(distinct_clips) >= 3:
                            break
        except Exception:
            pass
            
    return distinct_clips

def extract_tight_face_zoom(video_path, output_crop_path, model_path="yolov8n.pt"):
    """Extrait un ZOOM SERRÉ sur le VISAGE du streamer via YOLO."""
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
            
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 100)
        target = min(60, max(5, total // 3))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        ret, frame = cap.read()
        cap.release()
        
        if ret and frame is not None and frame.shape[0] > 0:
            h_img, w_img, _ = frame.shape
            
            # 1. Détection de la personne/streamer par YOLO
            if os.path.exists(model_path):
                try:
                    model = YOLO(model_path)
                    results = model.predict(source=frame, classes=[0], conf=0.25, save=False, verbose=False)
                    for r in results:
                        for box in r.boxes:
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            h_person = y2 - y1
                            w_person = x2 - x1
                            
                            # Zoom STRICT sur le VISAGE (Haut 35% du corps)
                            face_y2 = y1 + int(h_person * 0.35)
                            pad_w = int(w_person * 0.08)
                            pad_h = int(h_person * 0.04)
                            
                            fx1 = max(0, x1 - pad_w)
                            fy1 = max(0, y1 - pad_h)
                            fx2 = min(w_img, x2 + pad_w)
                            fy2 = min(h_img, face_y2 + pad_h)
                            
                            face_crop = frame[fy1:fy2, fx1:fx2]
                            if face_crop.size > 0 and face_crop.shape[0] > 40 and face_crop.shape[1] > 40:
                                cv2.imwrite(output_crop_path, face_crop)
                                return output_crop_path
                except Exception:
                    pass

            # Fallback Zoom Tête Centre-Haut
            crop_fallback = frame[int(h_img * 0.05):int(h_img * 0.45), int(w_img * 0.35):int(w_img * 0.65)]
            if crop_fallback.size > 0:
                cv2.imwrite(output_crop_path, crop_fallback)
                return output_crop_path
    except Exception:
        pass
    return None

def draw_text_stroke(draw, pos, txt, font, fill_color=(255, 255, 255), stroke_color=(0, 0, 0), stroke_w=6):
    x_p, y_p = pos
    for dx in range(-stroke_w, stroke_w + 1):
        for dy in range(-stroke_w, stroke_w + 1):
            if dx * dx + dy * dy <= stroke_w * stroke_w:
                draw.text((x_p + dx, y_p + dy), txt, font=font, fill=stroke_color)
    draw.text((x_p, y_p), txt, font=font, fill=fill_color)

def generate_triptych_reaction_thumbnail(
    header_text="MISTER MV & LES SAOUDIENS",
    quotes=['"Oh mon Dieu"', '"Après j\'arrête le stream"', '"C\'est grave ?!"'],
    output_path="thumbnail_3_panels_reaction.jpg"
):
    print("🖼️ Génération de la miniature 3 Panneaux avec ZOOM STRICT VISAGES...")
    FINAL_W, FINAL_H = 1280, 720
    panel_w = FINAL_W // 3  # 426 px par colonne

    clips = get_3_distinct_valid_clips()
    if len(clips) < 3:
        print("❌ Nombre insuffisant de clips vidéos distincts.")
        return None

    # Extrayons un ZOOM SERRÉ sur le visage de chaque streamer
    valid_crops = []
    for idx, clip_path in enumerate(clips):
        out_crop = f"tight_face_zoom_{idx}.jpg"
        res = extract_tight_face_zoom(clip_path, out_crop)
        if res and os.path.exists(res):
            valid_crops.append(res)
            print(f"✅ VISAGE ZOOMÉ {idx+1} extrait depuis {os.path.basename(clip_path)}")

    if len(valid_crops) < 3:
        print("❌ Échec d'extraction des visages zoomés.")
        return None

    canvas = Image.new("RGB", (FINAL_W, FINAL_H), (0, 0, 0))

    # Remplir les 3 Panneaux avec le ZOOM VISAGE au centre
    for i in range(3):
        c_path = valid_crops[i]
        c_img = Image.open(c_path).convert("RGB")
        
        # Booster la netteté, le contraste et la saturation pour un effet réaction intense
        c_img = ImageEnhance.Color(c_img).enhance(1.4)
        c_img = ImageEnhance.Contrast(c_img).enhance(1.25)
        c_img = ImageEnhance.Sharpness(c_img).enhance(1.3)

        # Redimensionner pour remplir le panneau (426 x 720) avec ZOOM MAX
        scale = max(panel_w / c_img.width, FINAL_H / c_img.height)
        new_w = int(c_img.width * scale)
        new_h = int(c_img.height * scale)
        c_img = c_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Cadrer le visage pile au milieu de la colonne
        crop_x = (new_w - panel_w) // 2
        crop_y = (new_h - FINAL_H) // 2
        panel_img = c_img.crop((crop_x, crop_y, crop_x + panel_w, crop_y + FINAL_H))

        canvas.paste(panel_img, (i * panel_w, 0))

    # Lignes de Séparation Verticales
    draw = ImageDraw.Draw(canvas)
    for i in range(1, 3):
        x_div = i * panel_w
        draw.line([(x_div - 2, 0), (x_div - 2, FINAL_H)], fill=(0, 0, 0), width=4)
        draw.line([(x_div + 2, 0), (x_div + 2, FINAL_H)], fill=(255, 255, 255), width=2)

    font_path = "Nunito-Black.ttf" if os.path.exists("Nunito-Black.ttf") else None

    # En-tête Titre Jaune en Haut ("MISTER MV & LES SAOUDIENS")
    try: font_header = ImageFont.truetype(font_path, 72) if font_path else ImageFont.load_default()
    except: font_header = ImageFont.load_default()

    header_overlay = Image.new("RGBA", (FINAL_W, 130), (0, 0, 0, 185))
    canvas.paste(header_overlay, (0, 0), header_overlay)

    draw = ImageDraw.Draw(canvas)
    
    if hasattr(font_header, 'getbbox'):
        bbox_h = font_header.getbbox(header_text)
        w_head = bbox_h[2] - bbox_h[0]
    else:
        w_head = len(header_text) * 40
        
    head_x = max(20, (FINAL_W - w_head) // 2)
    draw_text_stroke(draw, (head_x, 25), header_text, font_header, fill_color=(255, 235, 0), stroke_w=8)

    # Citations / Sous-titres sous chaque Visage Zoomé
    try: font_quote = ImageFont.truetype(font_path, 42) if font_path else ImageFont.load_default()
    except: font_quote = ImageFont.load_default()

    for i in range(min(3, len(quotes))):
        q_text = quotes[i]
        panel_x_start = i * panel_w
        
        if hasattr(font_quote, 'getbbox'):
            bbox_q = font_quote.getbbox(q_text)
            w_q = bbox_q[2] - bbox_q[0]
        else:
            w_q = len(q_text) * 20

        q_x = panel_x_start + max(10, (panel_w - w_q) // 2)
        q_y = FINAL_H - 120
        
        draw.rectangle([(q_x - 8, q_y - 4), (q_x + w_q + 8, q_y + 50)], fill=(0, 0, 0))
        draw_text_stroke(draw, (q_x, q_y), q_text, font_quote, fill_color=(255, 255, 255), stroke_w=5)

    canvas.save(output_path, quality=95)
    print(f"✅ Miniature 3 Panneaux ZOOM VISAGES créée avec succès : {os.path.abspath(output_path)}")
    return output_path

if __name__ == "__main__":
    generate_triptych_reaction_thumbnail()
