import requests
import json
import os
import time
import urllib3

# Désactiver SSL pour éviter les blocages Windows/Ecole
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= CONFIGURATION =================
# REMETTEZ VOS CLES ICI
CLIENT_KEY = "sbawnoy3t57hi8x7an"
CLIENT_SECRET = "6Q3PGv1Wd6CbJuVo07xNfVN6dl3jVVnh"
REDIRECT_URI = "https://www.google.com"
# =================================================

dossier_script = os.path.dirname(os.path.abspath(__file__))
FICHIER_SAUVEGARDE = os.path.join(dossier_script, "mes_comptes.txt")

def sauvegarder_compte(nouveau_compte):
    comptes = []
    if os.path.exists(FICHIER_SAUVEGARDE):
        with open(FICHIER_SAUVEGARDE, "r", encoding="utf-8") as f:
            comptes = json.load(f)
    
    existe = False
    for i, compte in enumerate(comptes):
        if compte.get("open_id") == nouveau_compte.get("open_id"):
            comptes[i] = nouveau_compte
            existe = True
            break
    if not existe: comptes.append(nouveau_compte)

    with open(FICHIER_SAUVEGARDE, "w", encoding="utf-8") as f:
        json.dump(comptes, f, indent=4, ensure_ascii=False)
    print(f"\n💾 Compte enregistré dans : {FICHIER_SAUVEGARDE}")

def authentification_tiktok():
    # C'EST ICI LA CLÉ DU SUCCÈS : LES SCOPES COMPLETS
    # On demande explicitement le droit de poster et d'uploader
    scope = "user.info.basic,video.publish,video.upload"
    
    auth_url = (
        f"https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={CLIENT_KEY}"
        f"&scope={scope}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state=init_auth"
    )

    print("\n" + "="*60)
    print("👉  CLIQUEZ ICI POUR RE-AUTORISER LE COMPTE (OBLIGATOIRE) :")
    print(f"{auth_url}")
    print("="*60)
    
    url_input = input("\nCollez l'URL finale (Google) ou le CODE ici : ").strip()

    if "code=" in url_input:
        auth_code = url_input.split("code=")[1].split("&")[0]
    else:
        auth_code = url_input

    print("🔄 Génération du nouveau Token blindé...")
    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = {
        'client_key': CLIENT_KEY,
        'client_secret': CLIENT_SECRET,
        'code': auth_code,
        'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI
    }

    try:
        response = requests.post(token_url, headers=headers, data=data, verify=False)
        json_data = response.json()
        
        if "access_token" in json_data:
            nom_interne = input("✍️  Nom du compte (ex: HistoirePeur) : ")
            donnees = {
                "nom_interne": nom_interne,
                "open_id": json_data.get("open_id"),
                "access_token": json_data.get("access_token"),
                "refresh_token": json_data.get("refresh_token"),
                "expires_in": json_data.get("expires_in")
            }
            sauvegarder_compte(donnees)
            print("✅ SUCCÈS ! Token régénéré avec les droits 'Direct Post'.")
        else:
            print(f"❌ ERREUR : {json_data}")
            
    except Exception as e:
        print(f"❌ Crash : {e}")

if __name__ == "__main__":
    authentification_tiktok()