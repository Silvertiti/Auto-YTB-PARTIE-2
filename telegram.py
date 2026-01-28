import requests

# Remplace par ton **Token d'API** donné par BotFather
bot_token = "7342966721:AAE6_C_LuyvcXaAuArlQ2AUz-lQUIFQ3Y4s"

# Ton **Chat ID** → pour l'envoyer à toi-même
# Obtiens-le facilement en parlant à @userinfobot ou via l'API /getUpdates si tu veux
chat_id = "TON_CHAT_ID"

# Chemin de ta vidéo finale
file_path = "clips_downloaded/IncredulousViscousChamoisFutureMan-tBZYxjSCoCXLAD9V_tiktok.mp4"

def envoyer_video_telegram(file_path, bot_token, chat_id):
    print("🚀 Envoi sur Telegram…")
    url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
    with open(file_path, 'rb') as video_file:
        files = {'video': video_file}
        data = {'chat_id': chat_id, 'caption': "Voici ta vidéo TikTok 🥳"}
        response = requests.post(url, files=files, data=data)
        if response.status_code == 200:
            print("✅ Vidéo envoyée avec succès !")
        else:
            print(f"❌ Erreur lors de l'envoi ({response.status_code}): {response.text}")

envoyer_video_telegram(file_path, bot_token, chat_id)
