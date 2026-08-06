import cv2
import numpy as np
import os, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def create_gotaga_wankil_character(output_path="gotaga_wankil.png"):
    """
    Génère le personnage 2D Wankil Studio de Gotaga 
    (Casquette RedBull, Barbe, Maillot Vitality noir & jaune)
    avec FOND TRANSPARENT (PNG RGBA).
    """
    W, H = 600, 750
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Corps / Maillot Vitality Noir
    # Torse
    draw.polygon([(180, 480), (420, 480), (460, 750), (140, 750)], fill=(20, 20, 25))
    # Manches
    draw.polygon([(180, 480), (100, 620), (150, 650), (220, 520)], fill=(25, 25, 30))
    draw.polygon([(420, 480), (500, 620), (450, 650), (380, 520)], fill=(25, 25, 30))

    # Motif Jaune Vitality (V)
    draw.polygon([(260, 520), (300, 640), (340, 520), (310, 520), (300, 580), (290, 520)], fill=(255, 215, 0))
    draw.polygon([(220, 500), (300, 670), (380, 500), (350, 500), (300, 610), (250, 500)], fill=(255, 215, 0))

    # Rayures blanches Adidas sur l'épaule
    for off in [0, 15, 30]:
        draw.line([(190 + off, 480), (130 + off, 560)], fill=(240, 240, 240), width=6)

    # Logo HP rond blanc sur la manche
    draw.ellipse((120, 570, 165, 615), fill=(255, 255, 255))
    draw.text((130, 578), "hp", fill=(10, 10, 10))

    # 2. Cou & Tête (Teinte de peau Gotaga)
    skin_color = (225, 175, 135)
    # Cou
    draw.rectangle((260, 420, 340, 500), fill=skin_color)
    # Visage (Tête Wankil arrondie)
    draw.ellipse((190, 200, 410, 460), fill=skin_color)

    # 3. Barbe & Moustache Gotaga (Brun foncé)
    beard_color = (40, 30, 25)
    # Contour de la barbe le long de la mâchoire
    draw.arc((200, 280, 400, 455), start=20, end=160, fill=beard_color, width=28)
    # Moustache
    draw.polygon([(260, 370), (300, 360), (340, 370), (300, 390)], fill=beard_color)
    # Bouc sous la lèvre
    draw.ellipse((285, 405, 315, 425), fill=beard_color)

    # 4. Yeux Wankil Caractéristiques (Grands yeux ronds Wankil)
    # Œil Gauche
    draw.ellipse((240, 290, 285, 335), fill=(255, 255, 255))
    draw.ellipse((257, 307, 273, 323), fill=(40, 25, 15)) # Pupille marron
    draw.ellipse((265, 310, 270, 315), fill=(255, 255, 255)) # Reflet

    # Œil Droit
    draw.ellipse((315, 290, 360, 335), fill=(255, 255, 255))
    draw.ellipse((327, 307, 343, 323), fill=(40, 25, 15)) # Pupille marron
    draw.ellipse((335, 310, 340, 315), fill=(255, 255, 255)) # Reflet

    # Sourcils épais bruns
    draw.polygon([(230, 275), (290, 280), (285, 270), (235, 268)], fill=beard_color)
    draw.polygon([(310, 280), (370, 275), (365, 268), (315, 270)], fill=beard_color)

    # Nez Wankil
    draw.line([(300, 315), (295, 345), (308, 347)], fill=(160, 110, 80), width=4)

    # Bouche / Sourire confiant
    draw.arc((270, 385, 330, 420), start=10, end=170, fill=(80, 40, 30), width=4)

    # 5. Casquette Snapback RedBull Gotaga (Gris clair avec visière rouge)
    # Visière rouge
    draw.polygon([(170, 230), (430, 230), (410, 265), (190, 265)], fill=(210, 30, 30))
    # Dôme gris
    draw.chord((180, 110, 420, 240), start=180, end=360, fill=(195, 195, 200))

    # Logo RedBull (Taureaux rouges + Soleil jaune)
    draw.ellipse((280, 160, 320, 200), fill=(255, 215, 0)) # Soleil
    draw.polygon([(250, 185), (290, 175), (280, 195)], fill=(200, 20, 20)) # Taureau L
    draw.polygon([(350, 185), (310, 175), (320, 195)], fill=(200, 20, 20)) # Taureau R

    # 6. Traits Noirs BD Épais (Outline Lineart Wankil)
    np_img = np.array(img)
    alpha = np_img[:, :, 3]
    
    # Dilater l'alpha pour dessiner le contour sticker noir
    kernel = np.ones((10, 10), np.uint8)
    dilated = cv2.dilate(alpha, kernel, iterations=1)
    
    stroke_mask = Image.fromarray(dilated)
    black_bg = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    
    final = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    final.paste(black_bg, (0, 0), stroke_mask)
    final.paste(img, (0, 0), img)

    final.save(output_path, "PNG")
    print(f"✅ Personnage Wankil Gotaga créé avec FOND TRANSPARENT : {os.path.abspath(output_path)}")
    return output_path

if __name__ == "__main__":
    create_gotaga_wankil_character()
