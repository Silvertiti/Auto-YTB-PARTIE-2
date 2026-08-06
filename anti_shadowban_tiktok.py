"""
anti_shadowban_tiktok.py
-------------------------
Module d'optimisation anti-shadowban / anti-contenu réutilisé pour TikTok.

Applique automatiquement :
1. Modification de la vitesse audio/vidéo (1.03x)
2. Micro-zoom visuel (1.04x)
3. Incrustation du filigrane avec le nom du compte TikTok (ex: @MonCompteTikTok)
4. Encodage avec empreinte binaire unique (CRF 20, Bitrate variable)

Usage:
    python anti_shadowban_tiktok.py input_video.mp4 output_video.mp4 --tiktok_user "@MonCompteTikTok"
"""

import os
import sys
import subprocess
import argparse

# Configurer UTF-8 pour la console Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def process_anti_shadowban(input_video, output_video, tiktok_user="@MonCompteTikTok", speed=1.03, zoom=1.04):
    if not os.path.exists(input_video):
        print(f"[ERREUR] Vidéo d'entrée introuvable -> {input_video}")
        return False

    print(f"[+] Application des filtres Anti-Shadowban sur : {input_video}")
    print(f"    ├─ Vitesse    : {speed}x")
    print(f"    ├─ Micro-Zoom : {zoom}x")
    print(f"    └─ Filigrane  : {tiktok_user}")

    pts_val = 1.0 / speed
    clean_user = tiktok_user.replace("@", "").replace("'", "").replace(":", "").replace("\\", "").upper()

    # Filtre vidéo : vitesse 1.03x, micro-zoom 1.04x, format 1080x1920, filigrane TikTok
    font_arg = "fontfile=Nunito-Black.ttf:" if os.path.exists("Nunito-Black.ttf") else ""
    video_filter = (
        f"setpts={pts_val:.4f}*PTS,"
        f"crop=iw/{zoom:.2f}:ih/{zoom:.2f},"
        f"scale=1080:1920:flags=bicubic,"
        f"drawtext={font_arg}text='{clean_user}':fontcolor=white@0.15:fontsize=56:box=0:x=(w-text_w)/2:y=(h-text_h)/2"
    )

    audio_filter = f"atempo={speed:.2f}"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", video_filter,
        "-af", audio_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        output_video
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(output_video) and os.path.getsize(output_video) > 1000:
            print(f"[OK] Vidéo optimisée avec succès -> {os.path.abspath(output_video)}")
            return True
        else:
            print(f"[!] Erreur ffmpeg : {res.stderr[-500:] if res.stderr else 'Inconnue'}")
            return False
    except Exception as e:
        print(f"[!] Exception lors de l'exécution d'ffmpeg : {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimiseur Anti-Shadowban TikTok")
    parser.add_argument("input", help="Fichier vidéo MP4 d'entrée")
    parser.add_argument("output", help="Fichier vidéo MP4 de sortie")
    parser.add_argument("--tiktok_user", default="@MonCompteTikTok", help="Nom du compte TikTok pour le filigrane")
    parser.add_argument("--speed", type=float, default=1.03, help="Facteur d'accélération (défaut: 1.03)")
    parser.add_argument("--zoom", type=float, default=1.04, help="Facteur de micro-zoom (défaut: 1.04)")

    args = parser.parse_args()
    process_anti_shadowban(args.input, args.output, args.tiktok_user, args.speed, args.zoom)
