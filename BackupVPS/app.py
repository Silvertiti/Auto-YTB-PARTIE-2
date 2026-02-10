# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, send_from_directory
import main          # Mode classique : récupérer des clips existants
import main_live     # Mode live : créer un clip en direct
import threading
import subprocess
import sys
import os
import json
import time
import uuid

app = Flask(__name__)
TRACKING_FILE = 'tracking.json'

# --- ETAT GLOBAL PARTAGÉ ---
job_list = [] 
job_lock = threading.Lock()

current_status = {
    "state": "idle",
    "current_job_name": None,
    "current_job_id": None,
    "current_mode": None,       # 'classic' ou 'live'
    "last_finished": None
}

def worker_loop():
    """Surveille la liste job_list et traite le premier élément"""
    global current_status
    print("👷 Worker Multi-Plateforme prêt !")
    print("   📦 Mode Classic (main.py) → /run")
    print("   🔴 Mode Live (main_live.py) → /run_live")
    
    while True:
        job_to_do = None
        
        with job_lock:
            if len(job_list) > 0:
                job_to_do = job_list.pop(0)
        
        if job_to_do:
            mode = job_to_do.get('mode', 'classic')
            mode_label = "🔴 LIVE" if mode == "live" else "📦 CLASSIC"
            
            current_status["state"] = "working"
            current_status["current_job_name"] = job_to_do['query']
            current_status["current_job_id"] = job_to_do['job_id']
            current_status["current_mode"] = mode
            
            print(f"🚀 [{mode_label}] Traitement de : {job_to_do['query']} (ID: {job_to_do['job_id']})")
            
            try:
                if mode == "live":
                    main_live.executer_pipeline(job_to_do)
                else:
                    main.executer_pipeline(job_to_do)
                    
                current_status["last_finished"] = f"{job_to_do['query']} ({mode})"
            except Exception as e:
                print(f"❌ Erreur [{mode_label}] : {e}")
                current_status["last_finished"] = f"Erreur-{job_to_do['query']}"
            finally:
                current_status["state"] = "idle"
                current_status["current_job_name"] = None
                current_status["current_job_id"] = None
                current_status["current_mode"] = None
        else:
            time.sleep(1)

# Lancement du worker au démarrage
threading.Thread(target=worker_loop, daemon=True).start()

# --- ROUTES API ---

@app.route('/queue', methods=['GET'])
def get_queue():
    """Renvoie la file d'attente complète + statut actuel"""
    with job_lock:
        waiting_names = [f"{'🔴' if j.get('mode') == 'live' else '📦'} {j['query']}" for j in job_list]
    
    response = {
        "status": current_status,
        "waiting_list": waiting_names,
        "count": len(waiting_names)
    }
    return jsonify(response)


@app.route('/run', methods=['POST'])
def add_to_queue_classic():
    """Mode CLASSIQUE : Récupère des clips existants → montage → post"""
    data = request.json
    
    job_id = str(uuid.uuid4())[:8]
    
    config = {
        "job_id": job_id,
        "mode": "classic",  # ← Mode classique
        "query": data.get('query', 'anyme023'),
        "type": data.get('type', 'channel'),
        "period": data.get('period', '24h'),
        "nb_videos": int(data.get('nb_videos', 1)),
        "lang": data.get('lang', 'fr'),
        "target_seconds": 60,
        "auto_post": data.get('auto_post', False),
        "send_telegram": data.get('send_telegram', True),
        "publish_now": True,
        "tiktok_account_key": data.get('tiktok_account', None)
    }

    with job_lock:
        job_list.append(config)
        position = len(job_list)

    return jsonify({
        "status": "queued", 
        "message": f"📦 [CLASSIC] {config['query']} ajouté à la file",
        "mode": "classic",
        "job_id": job_id,
        "position": position,
        "eta": position * 3
    })


@app.route('/run_live', methods=['POST'])
def add_to_queue_live():
    """Mode LIVE : Crée un clip en direct sur le stream → montage → post"""
    data = request.json
    
    job_id = str(uuid.uuid4())[:8]
    
    config = {
        "job_id": job_id,
        "mode": "live",  # ← Mode live
        "query": data.get('query', 'anyme023'),
        "type": "channel",  # Le mode live ne fonctionne qu'avec un channel
        "period": "24h",
        "nb_videos": 1,     # 1 clip = 1 vidéo en mode live
        "lang": data.get('lang', 'fr'),
        "target_seconds": 30,  # Un clip live fait ~30s
        "auto_post": data.get('auto_post', False),
        "send_telegram": data.get('send_telegram', True),
        "publish_now": True,
        "tiktok_account_key": data.get('tiktok_account', None)
    }

    with job_lock:
        job_list.append(config)
        position = len(job_list)

    return jsonify({
        "status": "queued", 
        "message": f"🔴 [LIVE] {config['query']} ajouté à la file",
        "mode": "live",
        "job_id": job_id,
        "position": position,
        "eta": position * 2  # Plus rapide en mode live (~2 min)
    })



# --- ROUTES CLASSIQUES ---
ANALYTICS_FILE = 'video_analytics.json'
TRACKING_FILE = 'tracking.json'
SCAN_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'get_last_10.py')

@app.route('/video_analytics.json')
def serve_analytics(): return send_from_directory('.', 'video_analytics.json')

@app.route('/force_scan', methods=['POST'])
def force_scan():
    """Lance le scan des stats TikTok en arrière-plan"""
    try:
        # Lancer get_last_10.py en background
        subprocess.Popen(
            [sys.executable, SCAN_SCRIPT],
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        return jsonify({"status": "success", "message": "🔄 Scan lancé en arrière-plan !"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erreur lancement scan : {e}"})

@app.route('/add_video', methods=['POST'])
def add_video():
    """Ajoute une vidéo TikTok au suivi"""
    data = request.json
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({"status": "error", "message": "URL manquante"})
    
    if 'tiktok.com' not in url:
        return jsonify({"status": "error", "message": "URL TikTok invalide"})

    # 1. Ajouter dans tracking.json (source pour le scan)
    tracking = []
    if os.path.exists(TRACKING_FILE):
        try:
            with open(TRACKING_FILE, 'r', encoding='utf-8') as f:
                tracking = json.load(f)
        except:
            tracking = []
    
    # Vérifier doublon
    existing_urls = []
    for item in tracking:
        if isinstance(item, dict):
            existing_urls.append(item.get('url', ''))
        else:
            existing_urls.append(item)
    
    if url in existing_urls:
        return jsonify({"status": "error", "message": "Cette vidéo est déjà suivie"})
    
    tracking.append({"url": url, "account": data.get('account', None)})
    
    with open(TRACKING_FILE, 'w', encoding='utf-8') as f:
        json.dump(tracking, f, indent=4, ensure_ascii=False)
    
    # 2. Ajouter aussi dans video_analytics.json (pour affichage immédiat)
    from datetime import datetime as dt
    analytics = []
    if os.path.exists(ANALYTICS_FILE):
        try:
            with open(ANALYTICS_FILE, 'r', encoding='utf-8') as f:
                analytics = json.load(f)
        except:
            analytics = []
    
    analytics.append({
        "url": url,
        "title": "En attente du scan...",
        "account": "N/A",
        "views": 0,
        "likes": 0,
        "last_updated": dt.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    
    with open(ANALYTICS_FILE, 'w', encoding='utf-8') as f:
        json.dump(analytics, f, indent=4, ensure_ascii=False)
    
    return jsonify({"status": "success", "message": "Vidéo ajoutée au suivi !"})

@app.route('/')
def index():
    accounts = [k.replace("TIKTOK_ACCOUNT_ID_", "") for k in os.environ.keys() if k.startswith("TIKTOK_ACCOUNT_ID_")]
    return render_template('index.html', accounts=accounts)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)