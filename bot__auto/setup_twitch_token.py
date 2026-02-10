"""
=============================================================
  SETUP TWITCH TOKEN - À exécuter UNE SEULE FOIS
=============================================================
Ce script t'aide à obtenir un token utilisateur Twitch
avec le scope 'clips:edit' (nécessaire pour créer des clips).

AVANT DE LANCER CE SCRIPT :
1. Va sur https://dev.twitch.tv/console/apps
2. Clique sur ton application
3. Note quelle URL est dans "OAuth Redirect URLs"
   (ex: http://localhost ou https://localhost)
4. Le script te demandera cette URL

Ensuite lance : python setup_twitch_token.py
=============================================================
"""

import os
import sys
import webbrowser
import requests
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

# Config
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
SCOPES = "clips:edit"


def update_env_file(key, value):
    """Ajoute ou met à jour une clé dans le fichier .env"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()
    
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    
    if not found:
        lines.append(f"{key}={value}\n")
    
    with open(env_path, 'w') as f:
        f.writelines(lines)


def main():
    print("=" * 55)
    print("  🔑 SETUP TOKEN TWITCH (clips:edit)")
    print("=" * 55)
    
    if not CLIENT_ID or not CLIENT_SECRET:
        print("❌ TWITCH_CLIENT_ID ou TWITCH_CLIENT_SECRET manquant dans .env !")
        sys.exit(1)
    
    print(f"\n📋 Client ID : {CLIENT_ID[:10]}...")
    
    # 1. Demander le redirect URI
    print("\n" + "-" * 55)
    print("� ÉTAPE 1 : Quelle Redirect URL est dans ton app Twitch ?")
    print("   (Va sur https://dev.twitch.tv/console/apps pour vérifier)")
    print("")
    print("   Exemples courants :")
    print("     1. http://localhost")
    print("     2. https://localhost")
    print("     3. http://localhost:3000")
    print("")
    
    redirect_uri = input("Colle ta Redirect URL ici (ou appuie Entrée pour 'http://localhost') : ").strip()
    if not redirect_uri:
        redirect_uri = "http://localhost"
    
    print(f"\n✅ Redirect URI : {redirect_uri}")
    
    # 2. Construire l'URL d'autorisation
    auth_url = (
        f"https://id.twitch.tv/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
        f"&response_type=code"
        f"&scope={urllib.parse.quote(SCOPES)}"
    )
    
    # 3. Ouvrir le navigateur
    print("\n" + "-" * 55)
    print("📌 ÉTAPE 2 : Autorisation dans le navigateur")
    print("-" * 55)
    print("\n🌐 Ouverture du navigateur...")
    print("   → Connecte-toi à Twitch et clique 'Autoriser'")
    print("   → Tu vas être redirigé vers une page (qui peut afficher une erreur)")
    print("   → C'EST NORMAL ! L'important c'est l'URL dans la barre d'adresse.\n")
    
    webbrowser.open(auth_url)
    
    # 4. L'utilisateur copie l'URL de redirection
    print("-" * 55)
    print("📌 ÉTAPE 3 : Copier l'URL")
    print("-" * 55)
    print("")
    print("   Après avoir autorisé, regarde la BARRE D'ADRESSE de ton navigateur.")
    print("   Tu verras quelque chose comme :")
    print(f"   {redirect_uri}/?code=XXXXXXXXXXXXXXXXXX")
    print("")
    print("   Copie TOUTE l'URL et colle-la ici :")
    print("")
    
    pasted_url = input("👉 URL complète : ").strip()
    
    # 5. Extraire le code de l'URL
    if not pasted_url:
        print("❌ Aucune URL fournie.")
        sys.exit(1)
    
    # Parser l'URL pour extraire le code
    parsed = urllib.parse.urlparse(pasted_url)
    params = urllib.parse.parse_qs(parsed.query)
    
    if 'code' not in params:
        # Peut-être que l'utilisateur a juste collé le code directement
        if len(pasted_url) > 10 and '?' not in pasted_url and '/' not in pasted_url:
            auth_code = pasted_url  # C'est probablement juste le code
        else:
            print(f"❌ Pas de 'code' trouvé dans l'URL : {pasted_url}")
            print("   Vérifie que tu as bien copié l'URL complète avec ?code=...")
            
            if 'error' in params:
                print(f"   Erreur Twitch : {params.get('error_description', params.get('error', ['Inconnue']))}")
            sys.exit(1)
    else:
        auth_code = params['code'][0]
    
    print(f"\n✅ Code d'autorisation reçu : {auth_code[:15]}...")
    
    # 6. Échanger le code contre un token
    print("\n🔄 Échange du code contre un token...")
    
    token_response = requests.post('https://id.twitch.tv/oauth2/token', data={
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': auth_code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri
    })
    
    if not token_response.ok:
        print(f"❌ Erreur : {token_response.status_code}")
        print(f"   {token_response.text}")
        sys.exit(1)
    
    tokens = token_response.json()
    access_token = tokens.get('access_token')
    refresh_token = tokens.get('refresh_token')
    
    if not access_token:
        print(f"❌ Pas d'access_token dans la réponse : {tokens}")
        sys.exit(1)
    
    print(f"✅ Access Token  : {access_token[:15]}...")
    print(f"✅ Refresh Token : {refresh_token[:15]}..." if refresh_token else "⚠️ Pas de refresh token")
    
    # 7. Vérifier que le token marche (optionnel mais utile)
    print("\n🔍 Vérification du token...")
    validate_resp = requests.get('https://id.twitch.tv/oauth2/validate', headers={
        'Authorization': f'OAuth {access_token}'
    })
    if validate_resp.ok:
        info = validate_resp.json()
        print(f"   ✅ Token valide !")
        print(f"   👤 Login : {info.get('login', '?')}")
        print(f"   🔐 Scopes : {info.get('scopes', [])}")
        print(f"   ⏰ Expire dans : {info.get('expires_in', 0) // 3600}h")
    else:
        print(f"   ⚠️ Vérification échouée (le token peut quand même marcher)")
    
    # 8. Sauvegarder dans le .env
    print("\n💾 Sauvegarde dans .env...")
    update_env_file("TWITCH_USER_TOKEN", access_token)
    if refresh_token:
        update_env_file("TWITCH_REFRESH_TOKEN", refresh_token)
    
    print("\n" + "=" * 55)
    print("  🎉 SETUP TERMINÉ AVEC SUCCÈS !")
    print("=" * 55)
    print("\n✅ Tu peux maintenant utiliser main.py pour créer des clips.")
    print("   Le token sera automatiquement rafraîchi quand il expire.")
    print("")


if __name__ == "__main__":
    main()
