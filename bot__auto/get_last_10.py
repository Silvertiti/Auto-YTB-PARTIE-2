import yt_dlp
import time
import json
import random
import os
from datetime import datetime

# --- CONFIGURATION ---
TRACKING_FILE = "tracking.json"
OUTPUT_FILE = "video_analytics.json"

YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
    'skip_download': True,
    'source_address': '0.0.0.0', 
    'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
}

def load_tracking_list():
    if not os.path.exists(TRACKING_FILE):
        return []
    try:
        with open(TRACKING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def load_existing_history():
    if not os.path.exists(OUTPUT_FILE):
        return []
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except:
        return []

def get_publication_date(info, video_id):
    if info.get('timestamp'):
        return datetime.fromtimestamp(info['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
    if info.get('upload_date'):
        d = info['upload_date']
        return f"{d[:4]}-{d[4:6]}-{d[6:]} 00:00:00"
    if video_id and str(video_id).isdigit():
        try:
            timestamp = int(video_id) >> 32
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass
    return "N/A"

def get_video_stats(url, account_name=None):
    """Récupère les stats et ajoute le nom du compte."""
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            if info is None:
                return None
            
            video_id = info.get('id')
            pub_date = get_publication_date(info, video_id)
            
            # Si le compte n'est pas fourni, on essaie de le prendre dans les infos de la vidéo
            tiktok_account = account_name or info.get('uploader') or info.get('channel') or "Inconnu"

            return {
                'url': url,
                'id': video_id,
                'account': tiktok_account, # <--- Nouveau champ stocké
                'title': info.get('title', 'N/A')[:50],
                'views': info.get('view_count', 0),
                'likes': info.get('like_count', 0),
                'comments': info.get('comment_count', 0),
                'shares': info.get('repost_count', 0),
                'upload_date': pub_date,
                'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            print(f"❌ Erreur sur {url}: {e}")
            return None

def main():
    print(f"📊 Scan historique lancé à {datetime.now().strftime('%H:%M:%S')}...")
    
    tracking_data = load_tracking_list()
    if not tracking_data:
        print("⚠️ Liste tracking.json vide.")
        return

    history = load_existing_history()
    new_entries = 0

    for i, item in enumerate(tracking_data):
        # On gère si tracking.json est une liste d'URLs ou une liste d'objets
        if isinstance(item, dict):
            url = item.get('url')
            account = item.get('account')
        else:
            url = item
            account = None

        stats = get_video_stats(url, account)
        
        if stats:
            print(f"✅ [{i+1}/{len(tracking_data)}] [{stats['account']}] : {stats['title']}")
            history.append(stats)
            new_entries += 1
        
        time.sleep(random.randint(2, 5))

    if new_entries > 0:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4, ensure_ascii=False)
        print(f"💾 Historique mis à jour ({len(history)} entrées) dans {OUTPUT_FILE}")

if __name__ == "__main__":
    main()