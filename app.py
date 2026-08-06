# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from functools import wraps
import hmac
import main          # Mode classique : récupérer des clips existants
import main_live     # Mode live : créer un clip en direct
import threading
import subprocess
import sys
import os
import json
import time
import uuid
from license_manager import register_license_routes, validate_license, consume_license

app = Flask(__name__)
app.secret_key = os.getenv("ADMIN_SECRET", "clipo_super_secret_key_2024")
register_license_routes(app)   # 🔑 Active les routes /license/check + /admin/...

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Check session (for browser access)
        if session.get('admin_logged_in'):
            return f(*args, **kwargs)
        
        # 2. Check header (for API calls)
        from license_manager import ADMIN_SECRET
        header_secret = request.headers.get("X-Admin-Secret", "")
        if header_secret and hmac.compare_digest(str(header_secret), str(ADMIN_SECRET)):
            return f(*args, **kwargs)
            
        # 3. Fail
        if request.is_json or request.headers.get('Accept') == 'application/json':
            return jsonify({"error": "Non autorisé"}), 401
        return redirect(url_for('admin_login'))
    return decorated_function

# ---- CORS : autorise clipo.fr (label) à appeler l'API ----
@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin', '')
    # Autoriser silvertiti.fr ET accès direct (localhost/VPS)
    allowed = ['https://silvertiti.fr', 'http://silvertiti.fr', 'http://localhost', 'http://127.0.0.1']
    if origin in allowed or not origin:  # pas d'origin = appel direct (curl, Postman)
        response.headers['Access-Control-Allow-Origin']  = origin or '*'
    else:
        response.headers['Access-Control-Allow-Origin']  = 'https://silvertiti.fr'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Admin-Secret'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

@app.before_request
def handle_options():
    """Répond immédiatement aux pré-vols CORS (OPTIONS)"""
    if request.method == 'OPTIONS':
        from flask import Response
        res = Response()
        res.headers['Access-Control-Allow-Origin']  = request.headers.get('Origin', '*')
        res.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Admin-Secret'
        res.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        return res

# --- ETAT GLOBAL PARTAGÉ ---
QUEUE_FILE = 'job_queue.json'
job_list = [] 
job_lock = threading.RLock()

def save_queue():
    """Sauvegarde la file d'attente actuelle dans un fichier JSON."""
    with job_lock:
        try:
            with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
                json.dump(job_list, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Erreur sauvegarde file d'attente : {e}")

def load_queue():
    """Charge la file d'attente depuis le fichier JSON au démarrage."""
    global job_list
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    job_list = loaded
                    print(f"📥 {len(job_list)} jobs restaurés depuis la sauvegarde.")
        except Exception as e:
            print(f"⚠️ Erreur chargement file d'attente : {e}")

load_queue() # On charge au démarrage

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
                save_queue() # On a retiré un job, on sauvegarde
        
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

    # --- VÉRIFICATION LICENCE OU ADMIN ---
    license_key = data.get('license_key', '').strip()
    lic_result  = {}
    is_client   = False
    
    if license_key:
        lic_result = validate_license(license_key)
        if not lic_result.get('valid'):
            return jsonify({
                "status": "error",
                "message": f"❌ {lic_result.get('reason')}"
            }), 403
        is_client = True
    else:
        # Pas de clé de licence ? Vérifier si l'utilisateur est admin
        is_admin = session.get('admin_logged_in')
        header_secret = request.headers.get("X-Admin-Secret", "")
        from license_manager import ADMIN_SECRET
        if not is_admin and not (header_secret and hmac.compare_digest(str(header_secret), str(ADMIN_SECRET))):
            return jsonify({"status": "error", "message": "❌ Accès refusé : Licence requise ou identifiants admin incorrects."}), 403
    # ----------------------------

    # --- CONSOMMATION & LIMITES CLIENT ---
    requested_nb = int(data.get('nb_videos', 1))
    if is_client:
        # 1. Cooldown & crédit
        consume_license(license_key)
        # 2. Force 1 vidéo max par requête pour les clients (pour respecter le cooldown de 5min)
        requested_nb = 1
    # -------------------------------------

    job_id = str(uuid.uuid4())[:8]

    # Récupère le telegram_chat_id du client depuis sa licence (vide si admin)
    client_telegram_chat_id = lic_result.get('telegram_chat_id', '').strip() if lic_result else ''

    config = {
        "job_id": job_id,
        "license_key":            license_key,
        "client_telegram_chat_id": client_telegram_chat_id,  # ← Envoi Telegram vers LE CLIENT
        "mode": "classic",
        "query": data.get('query', 'anyme023'),
        "type": data.get('type', 'channel'),
        "period": data.get('period', '24h'),
        "nb_videos": requested_nb,
        "lang": data.get('lang', 'fr'),
        "target_seconds": 60,
        "auto_post": data.get('auto_post', False),
        "send_telegram": data.get('send_telegram', True),
        "publish_now": True,
        "tiktok_account_key": data.get('tiktok_account', None),
        "youtube_mode": data.get('youtube_mode', False),
        "ignore_history": data.get('ignore_history', False)
    }

    with job_lock:
        job_list.append(config)
        save_queue()
        position = len(job_list)

    lic_info = f" | Plan: {lic_result['plan_label']}" if license_key else " | 👑 Accès Admin"
    return jsonify({
        "status": "queued",
        "message": f"📦 [CLASSIC] {config['query']} ajouté à la file{lic_info}",
        "mode": "classic",
        "job_id": job_id,
        "position": position,
        "eta": position * 3
    })


@app.route('/run_live', methods=['POST'])
@require_admin
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
        "tiktok_account_key": data.get('tiktok_account', None),
        "ignore_history": data.get('ignore_history', False)
    }

    with job_lock:
        job_list.append(config)
        save_queue()
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
SCAN_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'get_last_10.py')

@app.route('/video_analytics.json')
@require_admin
def serve_analytics(): return send_from_directory('.', 'video_analytics.json')

@app.route('/creation_logs.json')
@require_admin
def serve_creation_logs(): return send_from_directory('.', 'creation_logs.json')

@app.route('/force_scan', methods=['POST'])
@require_admin
def force_scan():
    """Lance le scan des stats TikTok en arrière-plan (force = re-vérifie TOUTES les vidéos)"""
    try:
        # Lancer get_last_10.py en background avec --force
        subprocess.Popen(
            [sys.executable, SCAN_SCRIPT, '--force'],
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        return jsonify({"status": "success", "message": "🔄 Scan FORCÉ lancé (toutes les vidéos, y compris dormantes) !"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erreur lancement scan : {e}"})

@app.route('/add_video', methods=['POST'])
@require_admin
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
def home():
    """Page d'accueil (Landing Page)."""
    return render_template('home.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Page de connexion administrateur."""
    if request.method == 'POST':
        from license_manager import ADMIN_SECRET
        password = request.json.get('password', '')
        if hmac.compare_digest(str(password), str(ADMIN_SECRET)):
            session['admin_logged_in'] = True
            return jsonify({"status": "success"})
        return jsonify({"status": "error"}), 401
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('home'))

@app.route('/admin/dashboard')
@require_admin
def index_admin():
    """Dashboard administrateur."""
    accounts = [k.replace("TIKTOK_ACCOUNT_ID_", "") for k in os.environ.keys() if k.startswith("TIKTOK_ACCOUNT_ID_")]
    return render_template('index.html', accounts=accounts)

@app.route('/admin/manage-licenses')
@require_admin
def admin_licenses_page():
    """Page de gestion des licences (anciennement /admin)."""
    return render_template('admin.html')

@app.route('/client')
def client_page():
    """Page de configuration client (licence + Telegram)."""
    return render_template('client_index.html')

@app.route('/client/generate')
def client_generate_page():
    """Page de génération de vidéos pour les clients."""
    return render_template('client_generate.html')


# ============================================================
#  WEBHOOK TELEGRAM — Le bot répond au /start avec le chat_id
# ============================================================

def _tg_send_message(chat_id: str, text: str):
    """Envoie un message texte via le bot Telegram."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return
    try:
        import requests as req
        req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"⚠️ Erreur envoi message Telegram : {e}")


@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    """
    Reçoit les mises à jour Telegram (messages envoyés au bot).
    Quand un utilisateur envoie /start, le bot lui répond avec son chat_id.

    Pour activer ce webhook, appelle /admin/telegram/setup-webhook
    (voir ci-dessous).
    """
    data = request.json or {}
    message = data.get("message", {})

    chat_id  = str(message.get("chat", {}).get("id", ""))
    text     = message.get("text", "").strip()
    username = message.get("from", {}).get("username", "")
    prenom   = message.get("from", {}).get("first_name", "")

    if not chat_id:
        return jsonify({"ok": True})

    print(f"📩 Telegram message reçu : {prenom} (@{username}) | chat_id={chat_id} | texte='{text}'")

    if text.startswith("/start") or text.startswith("/help"):
        reply = (
            f"👋 Bonjour *{prenom}* !\n\n"
            f"Bienvenue sur *Silvertiti Automation* 🎬\n\n"
            f"🆔 Ton *Chat ID Telegram* est :\n"
            f"`{chat_id}`\n\n"
            f"🎮 *Commandes disponibles :*\n"
            f"• `/post_tiktok [NomStreamer]` : Generer & poster un Shorts/TikTok\n"
            f"• `/post_youtube` : Generer & poster la compilation YouTube Longue (16:9)\n"
            f"• `/status [Licence]` : Afficher l'etat de ta licence\n"
            f"• `/setup [Licence]` : Enregistrer ton chat ID"
        )
        _tg_send_message(chat_id, reply)

    elif text.startswith("/setup"):
        # /setup SIL-XXXXX  → lie automatiquement le chat_id à la licence
        parts = text.split()
        if len(parts) < 2:
            _tg_send_message(chat_id,
                "❓ Usage : `/setup SIL-TACLÉ`\n\n"
                "Exemple : `/setup SIL-ABC123DEF456GH78IJ`"
            )
        else:
            from license_manager import validate_license, _load_licenses, _save_licenses
            key = parts[1].strip()
            check = validate_license(key)
            if not check.get("valid"):
                _tg_send_message(chat_id,
                    f"❌ Clé invalide : *{check.get('reason')}*\n"
                    "Vérifie ta clé et réessaie."
                )
            else:
                # Enregistre le chat_id
                licenses = _load_licenses()
                licenses[key]["telegram_chat_id"] = chat_id
                _save_licenses(licenses)
                print(f"✅ Auto-setup Telegram : {check['client_name']} → chat_id {chat_id}")
                _tg_send_message(chat_id,
                    f"✅ *Parfait {check['client_name']} !*\n\n"
                    f"Ton Telegram est maintenant lié à ta licence *{check['plan_label']}*.\n"
                    f"Tu recevras tes vidéos directement ici ! 🎬\n\n"
                    f"📅 Licence valide jusqu'au : `{check['expires_at']}`\n"
                    f"🎬 Quota : `{check['usage_today']}/{check['videos_per_day']}` vidéos aujourd'hui"
                )

    elif text.startswith("/status"):
        # /status SIL-XXXXX → affiche le statut de la licence
        parts = text.split()
        if len(parts) < 2:
            _tg_send_message(chat_id, "❓ Usage : `/status SIL-TACLÉ`")
        else:
            from license_manager import validate_license
            key   = parts[1].strip()
            check = validate_license(key)
            if check.get("valid"):
                _tg_send_message(chat_id,
                    f"📊 *Statut de ta licence*\n\n"
                    f"👤 Client  : `{check['client_name']}`\n"
                    f"📦 Plan    : `{check['plan_label']}`\n"
                    f"📅 Expire  : `{check['expires_at']}` ({check['remaining_days']} jours)\n"
                    f"🎬 Quota   : `{check['usage_today']}/{check['videos_per_day']}` vidéos aujourd'hui"
                )
            else:
                _tg_send_message(chat_id, f"❌ *{check.get('reason')}*")

    elif text.startswith("/post_tiktok") or text.startswith("/post_shorts") or text.startswith("/post_short"):
        # /post_tiktok [streamer] -> génère un short et le poste
        parts = text.split(None, 1)
        if len(parts) < 2:
            _tg_send_message(chat_id, "❓ Usage : `/post_tiktok [NomStreamer]`\nExemple : `/post_tiktok Gotaga`")
        else:
            streamer = parts[1].strip()
            job_id = str(uuid.uuid4())[:8]
            job = {
                "job_id": job_id,
                "query": streamer,
                "type": "channel",
                "period": "24h",
                "nb_videos": 1,
                "lang": "fr",
                "target_seconds": 60,
                "auto_post": True,
                "send_telegram": True,
                "telegram_chat_id_override": chat_id,
                "mode": "classic"
            }
            with job_lock:
                job_list.append(job)
                save_queue()
            _tg_send_message(chat_id, f"✅ Job Shorts/TikTok ajouté à la file d'attente pour @{streamer} ! (ID: `{job_id}`)")

    elif text.startswith("/post_ytb") or text.startswith("/post_youtube") or text.startswith("/post_long"):
        # /post_ytb -> lance la compilation longue YouTube
        def run_ytb_long_thread(cid):
            _tg_send_message(cid, "⏳ Lancement de la compilation YouTube Longue (16:9)... Cela va prendre 5 à 10 minutes.")
            try:
                script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_long_best_of.py")
                subprocess.run([sys.executable, script_path], check=False)
            except Exception as e:
                _tg_send_message(cid, f"❌ Erreur lors de la génération YouTube : {e}")

        threading.Thread(target=run_ytb_long_thread, args=(chat_id,), daemon=True).start()

    elif text.startswith("/stats") or text.startswith("/clients"):
        # ---- Commandes réservées à l'ADMIN ----
        admin_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if chat_id != admin_chat_id:
            _tg_send_message(chat_id, "🚫 Commande réservée à l'administrateur.")
        else:
            from license_manager import list_licenses
            licenses = list_licenses()

            if text.startswith("/stats"):
                total      = len(licenses)
                actives    = sum(1 for l in licenses if l.get("active") and l.get("remaining_days", 0) >= 0)
                expires    = sum(1 for l in licenses if l.get("active") and l.get("remaining_days", -1) < 0)
                revoked    = sum(1 for l in licenses if not l.get("active"))
                vids_today = sum(l.get("usage_today", 0) for l in licenses)
                vids_total = sum(l.get("total_uses", 0) for l in licenses)
                tg_linked  = sum(1 for l in licenses if l.get("telegram_chat_id"))

                _tg_send_message(chat_id,
                    f"📊 *Statistiques Silvertiti*\n\n"
                    f"👥 Clients total   : `{total}`\n"
                    f"✅ Actifs           : `{actives}`\n"
                    f"⏰ Expirés          : `{expires}`\n"
                    f"🚫 Révoqués         : `{revoked}`\n"
                    f"📲 TG liés          : `{tg_linked}/{total}`\n\n"
                    f"🎬 Vidéos aujourd'hui : `{vids_today}`\n"
                    f"🎬 Vidéos total       : `{vids_total}`\n\n"
                    f"💡 `/clients` → liste détaillée"
                )

            elif text.startswith("/clients"):
                if not licenses:
                    _tg_send_message(chat_id, "📭 Aucune licence créée.")
                else:
                    # Envoie par blocs de 5 pour éviter les messages trop longs
                    chunks = [licenses[i:i+5] for i in range(0, len(licenses), 5)]
                    for i, chunk in enumerate(chunks, 1):
                        lines = []
                        for l in chunk:
                            tg    = "📲" if l.get("telegram_chat_id") else "📵"
                            quota = f"{l.get('usage_today', 0)}/{l.get('videos_per_day', '?')}"
                            lines.append(
                                f"{l.get('status', '?')} *{l.get('client_name', '?')}* {tg}\n"
                                f"  `{l.get('key','?')[:20]}`\n"
                                f"  📦 {l.get('plan_label','?')} | "
                                f"📅 {l.get('remaining_days', '?')}j | "
                                f"🎬 {quota}/j | "
                                f"🔢 {l.get('total_uses', 0)} total"
                            )
                        _tg_send_message(chat_id, f"*Clients {i}/{len(chunks)} :*\n\n" + "\n\n".join(lines))

    return jsonify({"ok": True})


@app.route("/admin/telegram/setup-webhook", methods=["POST"])
def admin_setup_telegram_webhook():
    """
    Active le webhook Telegram pour que le bot réponde aux messages.
    À appeler UNE SEULE FOIS après le déploiement.

    Body JSON : {"url": "https://ton-domaine.fr"}
    Header requis : X-Admin-Secret

    Le webhook sera enregistré sur : https://ton-domaine.fr/telegram/webhook
    """
    from license_manager import ADMIN_SECRET
    import hmac as _hmac
    import requests as req

    secret = request.headers.get("X-Admin-Secret", "")
    if not _hmac.compare_digest(secret, ADMIN_SECRET):
        return jsonify({"error": "Accès refusé"}), 403

    data  = request.json or {}
    base_url = data.get("url", "").rstrip("/")
    if not base_url:
        return jsonify({"error": "url requis (ex: https://silvertiti.fr)"}), 400

    token       = os.getenv("TELEGRAM_BOT_TOKEN")
    webhook_url = f"{base_url}/telegram/webhook"

    try:
        resp = req.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url},
            timeout=10
        )
        result = resp.json()
        if result.get("ok"):
            print(f"✅ Webhook Telegram activé : {webhook_url}")
            return jsonify({
                "success": True,
                "message": f"✅ Webhook activé sur {webhook_url}",
                "telegram_response": result
            })
        else:
            return jsonify({"error": "Telegram a refusé le webhook", "details": result}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
