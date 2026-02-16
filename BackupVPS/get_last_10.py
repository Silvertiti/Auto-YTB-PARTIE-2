import yt_dlp
import time
import json
import random
import os
from datetime import datetime, timedelta

# --- CONFIGURATION ---
TRACKING_FILE = "tracking.json"
OUTPUT_FILE = "video_analytics.json"
EXPIRED_FILE = "expired_videos.json"  # Stocke les URLs qui ont dépassé 30 jours

YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
    'skip_download': True,
    'source_address': '0.0.0.0', 
    'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
}

# ============================================================
# Gestion des expirations (> 30 jours)
# ============================================================

def load_expired():
    if not os.path.exists(EXPIRED_FILE):
        return set()
    try:
        with open(EXPIRED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
        return set()

def save_expired(expired_set):
    with open(EXPIRED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(expired_set), f, indent=4, ensure_ascii=False)

def is_older_than_30_days(date_str):
    """Vérifie si une date (au format YYYY-MM-DD HH:MM:SS) a plus de 30 jours."""
    if not date_str or date_str == "N/A":
        return False
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        diff = datetime.now() - date_obj
        return diff.days > 30
    except:
        return False

# ============================================================
# Fonctions principales
# ============================================================

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
            
            tiktok_account = account_name or info.get('uploader') or info.get('channel') or "Inconnu"

            return {
                'url': url,
                'id': video_id,
                'account': tiktok_account,
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

def main(force=False):
    """
    Lance le scan.
    - Ignore les vidéos marquées comme 'expired' (> 30 jours).
    - force=True : Ignore la liste expired et rescanner tout.
    """
    print(f"📊 Scan lancé à {datetime.now().strftime('%H:%M:%S')}...")
    
    tracking_data = load_tracking_list()
    if not tracking_data:
        print("⚠️ Liste tracking.json vide.")
        return

    history = load_existing_history()
    expired = load_expired()
    
    new_entries = 0
    skipped_count = 0
    expired_count_added = 0
    
    if force:
        print("💪 Mode FORCE activé : On re-vérifie tout, même les expirés.")
        expired = set() # On vide temporairement la liste d'expiration

    for i, item in enumerate(tracking_data):
        # Gestion format tracking.json (dict ou str)
        if isinstance(item, dict):
            url = item.get('url')
            account = item.get('account')
        else:
            url = item
            account = None

        if not url: continue

        # 1. Vérifier si URL expirée (si pas force)
        if not force and url in expired:
            skipped_count += 1
            continue
        
        # 2. Récupérer stats
        stats = get_video_stats(url, account)
        
        if stats:
            print(f"✅ [{i+1}/{len(tracking_data)}] {stats['title']} → {stats['views']} vues")
            
            # 3. Vérifier l'âge de la vidéo
            if is_older_than_30_days(stats['upload_date']):
                print(f"   👴 Vidéo de +30 jours : Marquée comme EXPIRÉE (ne sera plus scannée).")
                expired.add(url)
                expired_count_added += 1
            
            history.append(stats)
            new_entries += 1
        
        time.sleep(random.randint(2, 5))
    
    # Sauvegarder historique
    if new_entries > 0:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4, ensure_ascii=False)
        print(f"💾 Historique mis à jour ({len(history)} entrées).")
    
    # Sauvegarder liste expirés
    save_expired(expired)

    print(f"\n📋 BILAN :")
    print(f"   ✅ Scannés : {new_entries}")
    print(f"   ⏭️ Ignorés (>30j) : {skipped_count}")
    print(f"   👴 Nouveaux expirés : {expired_count_added}")

if __name__ == "__main__":
    import sys
    force_mode = '--force' in sys.argv
    main(force=force_mode)