# -*- coding: utf-8 -*-
"""
YouTube Shorts Uploader - API YouTube Data v3 (SANS Late.dev)
=============================================================
Upload automatique de vidéos courtes (<60s, 9:16) en tant que YouTube Shorts.

SETUP (une seule fois) :
1. Va sur https://console.cloud.google.com/
2. Crée un projet → Active "YouTube Data API v3"
3. Identifiants → Créer ID client OAuth 2.0 → "Application de bureau"
4. Télécharge le JSON → renomme-le "client_secrets.json" dans ce dossier
5. Lance ce script une première fois → il ouvrira le navigateur pour te connecter
6. Après ça, le token sera sauvegardé et tout sera automatique !
"""

import os
import sys
import json
import time
import httplib2
import random
from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# ============ CONFIG ============
CLIENT_SECRETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_secrets.json")
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_token.json")

# Scopes nécessaires pour uploader des vidéos
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]

API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

# Retry config pour les uploads
MAX_RETRIES = 10
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

# Catégories YouTube courantes
CATEGORIES = {
    "gaming": "20",
    "entertainment": "24",
    "people": "22",
    "comedy": "23",
    "education": "27",
    "sports": "17",
    "music": "10",
}
# ================================


def get_authenticated_service():
    """
    Authentification OAuth 2.0 avec sauvegarde du token.
    - Première fois : ouvre le navigateur pour se connecter
    - Ensuite : utilise le token sauvegardé (refresh automatique)
    """
    credentials = None

    # Charger le token existant
    if os.path.exists(TOKEN_FILE):
        try:
            credentials = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            print("🔑 Token YouTube chargé depuis le fichier.")
        except Exception as e:
            print(f"⚠️ Erreur chargement token : {e}")
            credentials = None

    # Si pas de token ou token expiré
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            print("🔄 Refresh du token YouTube...")
            try:
                credentials.refresh(Request())
                print("✅ Token rafraîchi avec succès !")
            except Exception as e:
                print(f"❌ Erreur refresh token : {e}")
                credentials = None

        if not credentials:
            # Première authentification
            if not os.path.exists(CLIENT_SECRETS_FILE):
                print("=" * 60)
                print("❌ FICHIER client_secrets.json INTROUVABLE !")
                print("=" * 60)
                print()
                print("Pour configurer l'upload YouTube :")
                print("1. Va sur https://console.cloud.google.com/")
                print("2. Crée un projet → Active 'YouTube Data API v3'")
                print("3. Identifiants → Créer ID client OAuth 2.0")
                print("   → Type : 'Application de bureau'")
                print("4. Télécharge le fichier JSON")
                print(f"5. Renomme-le 'client_secrets.json' et place-le dans :")
                print(f"   {os.path.dirname(os.path.abspath(__file__))}")
                print("=" * 60)
                return None

            print("🌐 Ouverture du navigateur pour l'authentification YouTube...")
            print("   (Connecte-toi avec le compte Google lié à ta chaîne YouTube)")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=8090, prompt="consent")
            print("✅ Authentification réussie !")

        # Sauvegarder le token pour la prochaine fois
        with open(TOKEN_FILE, "w") as token_file:
            token_file.write(credentials.to_json())
        print(f"💾 Token sauvegardé dans {TOKEN_FILE}")

    # Construire le service YouTube
    youtube = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
    return youtube


def upload_youtube_short(
    video_path,
    title,
    description="",
    tags=None,
    category="gaming",
    privacy="public",
    made_for_kids=False
):
    """
    Upload une vidéo en tant que YouTube Short.
    
    Args:
        video_path (str): Chemin vers le fichier vidéo (.mp4)
        title (str): Titre de la vidéo (max 100 chars)
        description (str): Description de la vidéo
        tags (list): Liste de tags (ex: ["twitch", "gaming", "shorts"])
        category (str): Catégorie ("gaming", "entertainment", etc.)
        privacy (str): "public", "private", ou "unlisted"
        made_for_kids (bool): Si la vidéo est destinée aux enfants
    
    Returns:
        dict: Infos de la vidéo uploadée (id, url, etc.) ou None si erreur
    """
    
    if not os.path.exists(video_path):
        print(f"❌ Fichier vidéo introuvable : {video_path}")
        return None

    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    print(f"📁 Fichier : {video_path} ({file_size_mb:.1f} MB)")

    # Authentification
    youtube = get_authenticated_service()
    if not youtube:
        return None

    # S'assurer que #Shorts est dans le titre ou la description
    if "#Shorts" not in title and "#shorts" not in title.lower():
        title = f"{title} #Shorts"
    
    # Tronquer le titre si trop long (max 100 chars pour YouTube)
    if len(title) > 100:
        title = title[:96] + "..."

    # Ajouter #Shorts à la description aussi
    if "#Shorts" not in description:
        description = f"{description}\n\n#Shorts"

    # Catégorie YouTube ID
    category_id = CATEGORIES.get(category.lower(), "24")  # Default: Entertainment

    # Tags par défaut si non fournis
    if tags is None:
        tags = ["shorts", "twitch", "gaming", "clip", "viral", "twitchfr"]

    # Construire le body de la requête
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
            "defaultLanguage": "fr",
            "defaultAudioLanguage": "fr"
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": made_for_kids,
            "embeddable": True,
            "publicStatsViewable": True
        }
    }

    print(f"📺 Upload YouTube Short...")
    print(f"   📝 Titre : {title}")
    print(f"   🏷️ Catégorie : {category} (ID: {category_id})")
    print(f"   🔒 Visibilité : {privacy}")
    print(f"   #️⃣ Tags : {', '.join(tags[:5])}...")

    # Préparer le media (upload resumable pour les gros fichiers)
    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 5  # Chunks de 5 MB
    )

    # Lancer l'upload
    try:
        insert_request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = _resumable_upload(insert_request)
        
        if response:
            video_id = response.get("id")
            video_url = f"https://youtube.com/shorts/{video_id}"
            print(f"✅ YouTube Short uploadé avec succès !")
            print(f"   🔗 URL : {video_url}")
            print(f"   🆔 ID : {video_id}")
            return {
                "id": video_id,
                "url": video_url,
                "title": title,
                "status": response.get("status", {}).get("privacyStatus", "unknown")
            }
        
    except HttpError as e:
        print(f"❌ Erreur API YouTube : {e}")
        if e.resp.status == 403:
            print("   💡 Vérifie que l'API YouTube Data v3 est bien activée dans Google Cloud Console")
            print("   💡 Vérifie aussi ton quota API (10 000 unités/jour par défaut)")
        return None
    except Exception as e:
        print(f"❌ Erreur inattendue : {e}")
        return None


def _resumable_upload(insert_request):
    """
    Upload resumable avec retry automatique.
    Gère les erreurs réseau et les interruptions.
    """
    response = None
    error = None
    retry = 0

    while response is None:
        try:
            print("   ⏫ Envoi en cours...", end="", flush=True)
            status, response = insert_request.next_chunk()
            
            if status:
                progress = int(status.progress() * 100)
                print(f"\r   ⏫ Progression : {progress}%", end="", flush=True)
            
            if response is not None:
                print(f"\r   ⏫ Progression : 100%")
                if "id" in response:
                    return response
                else:
                    print(f"❌ Réponse inattendue : {response}")
                    return None

        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                error = f"Erreur HTTP retriable {e.resp.status} : {e.content}"
            else:
                raise

        except (httplib2.HttpLib2Error, IOError) as e:
            error = f"Erreur réseau : {e}"

        if error is not None:
            print(f"\n   ⚠️ {error}")
            retry += 1
            if retry > MAX_RETRIES:
                print("❌ Nombre maximum de tentatives atteint. Abandon.")
                return None

            sleep_seconds = random.random() * (2 ** retry)
            print(f"   🔄 Retry {retry}/{MAX_RETRIES} dans {sleep_seconds:.1f}s...")
            time.sleep(sleep_seconds)
            error = None

    return None


def upload_from_caption(video_path, generated_caption, category="gaming", privacy="public"):
    """
    Fonction simplifiée qui prend le format caption de ton pipeline existant.
    Compatible avec le format de generate_metadata() (titre + hashtags).
    
    Args:
        video_path: Chemin vers la vidéo
        generated_caption: Le texte généré par Groq (ligne 1 = titre, ligne 2 = hashtags)
        category: Catégorie YouTube
        privacy: Visibilité
    """
    lines = generated_caption.strip().split('\n')
    
    title = lines[0].strip() if len(lines) > 0 else "Best Of Twitch #Shorts"
    hashtags = lines[1].strip() if len(lines) > 1 else "#TwitchFR #Shorts"
    
    # Extraire les tags depuis les hashtags
    tags = [tag.strip().replace("#", "") for tag in hashtags.split("#") if tag.strip()]
    if "Shorts" not in tags and "shorts" not in tags:
        tags.append("Shorts")
    
    # Description complète
    description = f"{title}\n\n{hashtags}\n\n#Shorts #YouTube"
    
    return upload_youtube_short(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        category=category,
        privacy=privacy
    )


# ============ TEST ============
if __name__ == "__main__":
    print("=" * 50)
    print("🎬 YouTube Shorts Uploader - Test")
    print("=" * 50)
    
    # Test 1 : Vérifier l'authentification
    print("\n--- Test Authentification ---")
    youtube = get_authenticated_service()
    
    if youtube:
        print("✅ Connexion YouTube OK !")
        
        # Lister les infos de la chaîne connectée
        try:
            channels = youtube.channels().list(part="snippet", mine=True).execute()
            if channels.get("items"):
                channel = channels["items"][0]["snippet"]
                print(f"   📺 Chaîne : {channel['title']}")
                print(f"   📝 Description : {channel.get('description', 'N/A')[:50]}...")
            else:
                print("   ⚠️ Aucune chaîne trouvée pour ce compte.")
        except Exception as e:
            print(f"   ⚠️ Impossible de lister les chaînes : {e}")
        
        # Test 2 : Upload si un fichier est fourni en argument
        if len(sys.argv) > 1:
            video_file = sys.argv[1]
            caption = sys.argv[2] if len(sys.argv) > 2 else "Test Upload #Shorts\n#TwitchFR #Gaming"
            
            print(f"\n--- Upload de {video_file} ---")
            result = upload_from_caption(video_file, caption)
            
            if result:
                print(f"\n🎉 Succès ! Vidéo disponible sur : {result['url']}")
            else:
                print("\n❌ L'upload a échoué.")
        else:
            print("\n💡 Pour tester un upload :")
            print(f"   python youtube_uploader.py <chemin_video.mp4> [caption]")
    else:
        print("❌ Authentification échouée. Suis les instructions ci-dessus.")
