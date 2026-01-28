import ftplib
import os

# --- Configuration ---
FTP_HOST = "ftp.cluster129.hosting.ovh.net"
FTP_USER = "silvero"
FTP_PASS = "Iankee01"
REMOTE_DIR = "www"

def upload_file(local_path, remote_name):

    if not os.path.exists(local_path):
        print(f"Erreur : Le fichier local '{local_path}' n'existe pas.")
        return

    try:
        print(f"Connexion au serveur {FTP_HOST}...")
        with ftplib.FTP(FTP_HOST, FTP_USER, FTP_PASS) as ftp:
            # Changer de dossier
            ftp.cwd(REMOTE_DIR)
            print(f"Dossier sur le serveur : {ftp.pwd()}")

            # Envoi du fichier
            print(f"Envoi de '{local_path}' vers '{remote_name}'...")
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_name}", f)
            
            print("✅ Upload terminé avec succès !")

    except Exception as e:
        print(f"❌ Une erreur est survenue : {e}")

# --- Exécution ---
if __name__ == "__main__":
    upload_file("blabla.txt", "blabla.txt")