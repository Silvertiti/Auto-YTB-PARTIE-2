import sys
import os

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

import sqlite3
import json
import tempfile
from datetime import datetime

DB_FILE = "analytics.db"

def get_connection():
    """Crée une connexion SQLite optimisée avec WAL mode pour de hautes performances."""
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    """Initialise la table analytics et les index si non existants."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS video_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    video_id TEXT,
                    account TEXT,
                    title TEXT,
                    views INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    followers INTEGER DEFAULT 0,
                    upload_date TEXT,
                    last_updated TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_url ON video_analytics(url);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_account ON video_analytics(account);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_last_updated ON video_analytics(last_updated);")
            conn.commit()
    except sqlite3.DatabaseError:
        print("⚠️ Fichier SQLite corrompu/incomplet détecté. Réinitialisation...")
        if os.path.exists(DB_FILE):
            try:
                os.remove(DB_FILE)
            except Exception:
                pass
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS video_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    video_id TEXT,
                    account TEXT,
                    title TEXT,
                    views INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    followers INTEGER DEFAULT 0,
                    upload_date TEXT,
                    last_updated TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_url ON video_analytics(url);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_account ON video_analytics(account);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_last_updated ON video_analytics(last_updated);")
            conn.commit()

def import_from_json(json_file="video_analytics.json"):
    """Importe l'historique JSON dans la base SQLite si SQLite est vide."""
    init_db()
    if not os.path.exists(json_file):
        return 0

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM video_analytics")
        count = cursor.fetchone()[0]
        if count > 0:
            return count

        print(f"📦 Migration de {json_file} vers SQLite...")
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"❌ Erreur de lecture de {json_file}: {e}")
            return 0

        records = []
        for item in data:
            if not isinstance(item, dict):
                continue
            records.append((
                item.get('url', ''),
                item.get('id', ''),
                item.get('account', ''),
                item.get('title', ''),
                int(item.get('views', 0) or 0),
                int(item.get('likes', 0) or 0),
                int(item.get('comments', 0) or 0),
                int(item.get('shares', 0) or 0),
                int(item.get('followers', 0) or 0),
                item.get('upload_date', ''),
                item.get('last_updated', '')
            ))

        cursor.executemany("""
            INSERT INTO video_analytics (
                url, video_id, account, title, views, likes, comments, shares, followers, upload_date, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, records)
        conn.commit()
        print(f"✅ Migration réussie : {len(records)} entrées insérées dans {DB_FILE}.")
        return len(records)

def insert_analytics(entries):
    """Insère un lot de nouvelles métriques en une seule transaction ultra-rapide."""
    if not entries:
        return
    init_db()
    records = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        records.append((
            item.get('url', ''),
            item.get('id', ''),
            item.get('account', ''),
            item.get('title', ''),
            int(item.get('views', 0) or 0),
            int(item.get('likes', 0) or 0),
            int(item.get('comments', 0) or 0),
            int(item.get('shares', 0) or 0),
            int(item.get('followers', 0) or 0),
            item.get('upload_date', ''),
            item.get('last_updated', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ))

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT INTO video_analytics (
                url, video_id, account, title, views, likes, comments, shares, followers, upload_date, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, records)
        conn.commit()

def load_all_analytics():
    """Charge toutes les entrées sous forme de liste de dictionnaires (pour compatibilité)."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM video_analytics ORDER BY id ASC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def get_latest_analytics_map():
    """Retourne la dernière entrée connue pour chaque URL (pour calcul des deltas)."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM video_analytics 
            WHERE id IN (SELECT MAX(id) FROM video_analytics GROUP BY url)
        """)
        rows = cursor.fetchall()
        return {r['url']: dict(r) for r in rows}

def export_to_json(json_file="video_analytics.json"):
    """Génère le fichier JSON pour compatibilité si nécessaire."""
    data = load_all_analytics()
    dir_name = os.path.dirname(os.path.abspath(json_file))
    temp_fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(temp_path, json_file)
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        print(f"⚠️ Erreur export JSON: {e}")

if __name__ == "__main__":
    import_from_json()
