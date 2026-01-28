import os
import sys

def get_next_filename(folder, base_name, ext):
    """
    Cherche le prochain nom de fichier disponible en incrémentant le suffixe (_1, _2, etc.)
    
    :param folder: Dossier de destination
    :param base_name: Nom de base (ex: clip)
    :param ext: Extension (ex: .mp4)
    :return: Nom de fichier complet
    """
    i = 1
    while True:
        filename = f"{base_name}_{i}{ext}"
        full_path = os.path.join(folder, filename)
        if not os.path.exists(full_path):
            return full_path
        i += 1

def download_twitch_clip(url, output_folder="clips"):
    """
    Télécharge un clip Twitch et l'enregistre dans un dossier 'clips' avec nom unique.
    
    :param url: Lien du clip Twitch
    :param output_folder: Dossier de sortie (défaut: 'clips')
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    # Cherche le prochain nom de fichier disponible
    output_file = get_next_filename(output_folder, "clip", ".mp4")
    
    # Commande pour télécharger le clip via streamlink
    command = f"streamlink --twitch-disable-ads {url} best -o \"{output_file}\""
    
    print(f"🔗 Téléchargement du clip : {url}")
    print(f"💾 Sauvegarde dans : {output_file}")
    
    # Exécution de la commande
    os.system(command)
    
    print("✅ Téléchargement terminé.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("❌ Utilisation : python download_twitch_clip.py <lien_du_clip>")
        sys.exit(1)
    
    clip_url = sys.argv[1]
    download_twitch_clip(clip_url)
