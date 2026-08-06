import sys
import os

# Configurer stdout/stderr pour UTF-8 sous Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import yt_dlp
import time
import json
import random
import tempfile
from datetime import datetime, timedelta
import requests
import re
from dotenv import load_dotenv

import database  # Module SQLite optimisé

# Charger les variables d'environnement (.env)
load_dotenv()

# --- CONFIGURATION ---
TRACKING_FILE = "tracking.json"
OUTPUT_FILE = "video_analytics.json"
EXPIRED_FILE = "expired_videos.json"  # Stocke les URLs qui ont dépassé 30 jours

YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
    'skip_download': True,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

def save_atomic_json(filepath, data):
    """Sauvegarde atomic du JSON pour éviter la corruption de fichier (0xFF bytes)."""
    dir_name = os.path.dirname(os.path.abspath(filepath))
    temp_fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(temp_path, filepath)
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise e

def load_atomic_json(filepath, default=None):
    """Lecture sécurisée avec fallback si fichier corrompu."""
    if default is None:
        default = []
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Erreur de lecture {filepath} : {e}")
        return default

def send_telegram_summary(scanned_count, duration_str, new_views, total_subscribers):
    """Envoie un résumé du scan sur Telegram."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("⚠️ Pas de config Telegram trouvée (TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant).")
        return

    message = (
        f"📊 *Rapport Stats Video*\n\n"
        f"✅ *Clips scannés :* {scanned_count}\n"
        f"👀 *Nouvelles vues :* {new_views:,}\n"
        f"⏱️ *Durée :* {duration_str}\n" 
        f"📅 *Date :* {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        requests.post(url, json=payload, timeout=10)
        print("📧 Rapport Telegram envoyé avec succès.")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi Telegram : {e}")

# ============================================================
# Gestion des expirations (> 30 jours)
# ============================================================

def load_expired():
    data = load_atomic_json(EXPIRED_FILE, [])
    return set(data) if isinstance(data, list) else set()

def save_expired(expired_set):
    save_atomic_json(EXPIRED_FILE, list(expired_set))

def is_older_than_30_days(date_str):
    """Vérifie si une date (au format YYYY-MM-DD HH:MM:SS) a plus de 30 jours."""
    if not date_str or date_str == "N/A":
        return False
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        diff = datetime.now() - date_obj
        return diff.days > 30
    except Exception:
        return False

def get_tiktok_followers(url):
    """Récupère le nombre d'abonnés via scraping direct (fallback yt-dlp)."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            html = res.text
            match = re.search(r'"authorStats":\{.*?"followerCount":(\d+)', html)
            if match:
                return int(match.group(1))
            
            match_simple = re.search(r'"followerCount":(\d+)', html)
            if match_simple:
                return int(match_simple.group(1))
                
    except Exception as e:
        print(f"   ⚠️ Impossible de récupérer les abonnés : {e}")
    
    return 0

# ============================================================
# Fonctions principales
# ============================================================

def load_tracking_list():
    return load_atomic_json(TRACKING_FILE, [])

def get_publication_date(info, video_id):
    if info.get('timestamp'):
        return datetime.fromtimestamp(info['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
    if info.get('upload_date'):
        d = str(info['upload_date'])
        if len(d) == 8:
            return f"{d[:4]}-{d[4:6]}-{d[6:]} 00:00:00"
    if video_id and str(video_id).isdigit():
        try:
            timestamp = int(video_id) >> 32
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
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
                'title': str(info.get('title', 'N/A'))[:50],
                'views': info.get('view_count', 0) or 0,
                'likes': info.get('like_count', 0) or 0,
                'comments': info.get('comment_count', 0) or 0,
                'shares': info.get('repost_count', 0) or 0,
                'followers': info.get('channel_follower_count') or info.get('uploader_subscribers') or get_tiktok_followers(url),
                'upload_date': pub_date,
                'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception:
            return None

def process_single_video(item, force, expired_set):
    """Traite une seule vidéo (exécuté dans un thread)."""
    if isinstance(item, dict):
        url = item.get('url')
        account = item.get('account')
    else:
        url = item
        account = None

    if not url: 
        return None, None, False

    if not force and url in expired_set:
        return None, None, True # Skipped because expired
    
    time.sleep(random.uniform(0.2, 1.0))
    stats = get_video_stats(url, account)
    
    url_to_expire = None
    if stats:
        if is_older_than_30_days(stats['upload_date']):
            url_to_expire = url
        
    return stats, url_to_expire, False

def main(force=False):
    """Lance le scan optimisé avec stockage SQLite."""
    import concurrent.futures
    
    start_time = datetime.now()
    print(f"📊 Scan optimisé (SQLite) lancé à {start_time.strftime('%H:%M:%S')}...")
    
    tracking_data = load_tracking_list()
    if not tracking_data:
        print("⚠️ Liste tracking.json vide.")
        return

    # S'assurer que SQLite est initialisé et importé
    database.import_from_json(OUTPUT_FILE)
    
    # Chargement ultra-rapide des dernières stats par URL depuis SQLite
    last_stats = database.get_latest_analytics_map()

    expired = load_expired()
    
    new_entries = []
    skipped_count = 0
    expired_count_added = 0
    
    if force:
        print("💪 Mode FORCE activé : On re-vérifie tout, même les expirés.")
        expired = set() 

    MAX_WORKERS = 5
    print(f"🚀 Traitement de {len(tracking_data)} vidéos avec {MAX_WORKERS} threads simultanés...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {
            executor.submit(process_single_video, item, force, expired): item 
            for item in tracking_data
        }
        
        completed_count = 0
        total_count = len(tracking_data)
        
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                stats, url_to_expire, skipped = future.result()
                completed_count += 1
                
                if skipped:
                    skipped_count += 1
                    continue

                if stats:
                    print(f"✅ [{completed_count}/{total_count}] {stats['title']} → {stats['views']} vues")
                    new_entries.append(stats)
                    
                    if url_to_expire:
                        print(f"   👴 Vidéo de +30 jours : Sera marquée EXPIRÉE.")
                        expired.add(url_to_expire)
                        expired_count_added += 1
                else:
                    print(f"❌ [{completed_count}/{total_count}] Erreur ou vidéo inaccessible.")
                    
            except Exception as exc:
                print(f"💥 Exception générée : {exc}")

    if new_entries:
        # 1. Insertion SQLite instantanée
        database.insert_analytics(new_entries)
        # 2. Synchronisation JSON pour compatibilité web
        database.export_to_json(OUTPUT_FILE)
        print(f"💾 Base SQLite et JSON mis à jour (+{len(new_entries)} entrées).")
    
    save_expired(expired)

    duration = datetime.now() - start_time
    duration_str = str(duration).split('.')[0]

    print(f"\n📋 BILAN (Durée: {duration_str}):")
    print(f"   ✅ Scannés : {len(new_entries)}")
    print(f"   ⏭️ Ignorés (>30j) : {skipped_count}")
    print(f"   👴 Nouveaux expirés : {expired_count_added}")

    total_new_views = 0
    accounts_subs = {}
    
    for entry in new_entries:
        url = entry.get('url')
        try:
            current_views = int(entry.get('views', 0))
        except Exception:
            current_views = 0

        if url in last_stats:
            try:
                prev_views = int(last_stats[url].get('views', 0))
            except Exception:
                prev_views = 0
            
            delta = current_views - prev_views
            if delta > 0:
                total_new_views += delta
        
        acct = entry.get('account')
        try:
            subs = int(entry.get('followers', 0))
        except Exception:
            subs = 0
        
        if acct:
            if acct not in accounts_subs:
                accounts_subs[acct] = subs
            else:
                accounts_subs[acct] = max(accounts_subs[acct], subs)

    total_subscribers = sum(accounts_subs.values())

    print(f"   👀 Nouvelles vues : {total_new_views}")
    print(f"   👥 Abonnés totaux : {total_subscribers}")

    send_telegram_summary(len(new_entries), duration_str, total_new_views, total_subscribers)

if __name__ == "__main__":
    force_mode = '--force' in sys.argv
    main(force=force_mode)