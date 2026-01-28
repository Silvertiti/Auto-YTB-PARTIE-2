import os

def vider_dossier_clips(dossier="clips"):
    if not os.path.exists(dossier):
        print(f"❌ Le dossier '{dossier}' n'existe pas.")
        return

    for filename in os.listdir(dossier):
        file_path = os.path.join(dossier, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)
            print(f"🗑️ Fichier supprimé : {file_path}")

    print(f"✅ Tous les fichiers du dossier '{dossier}' ont été supprimés.")

if __name__ == "__main__":
    vider_dossier_clips()
