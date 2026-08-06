# -*- coding: utf-8 -*-
"""
====================================================
  LICENSE MANAGER — Clipo Automation Suite
====================================================
Gère la création, validation et révocation des clés
de licence pour les clients.

Côté ADMIN  : créer/révoquer des clés via /admin/...
Côté CLIENT : valider sa clé au démarrage de l'app
====================================================
"""

import os
import json
import uuid
import hashlib
import hmac
import time
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify

# ============================================
#  CONFIG — à mettre dans ton .env
# ============================================
# ADMIN_SECRET : mot de passe pour accéder aux routes /admin
# Génère-le dans ton .env :  ADMIN_SECRET=UnMotDePasseTresLong123!
ADMIN_SECRET   = os.getenv("ADMIN_SECRET", "changeme_super_secret")

# HMAC_SECRET : secret pour signer les réponses de validation (anti-falsification)
HMAC_SECRET    = os.getenv("HMAC_SECRET", "changeme_hmac_secret")

# Fichier de stockage des licences
LICENSES_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "licenses.json")

# ============================================
#  PLANS DISPONIBLES
# ============================================
PLANS = {
    "trial":    {"label": "Essai Gratuit",   "days": 7,    "videos_per_day": 3},
    "starter":  {"label": "Starter",         "days": 30,   "videos_per_day": 10},
    "pro":      {"label": "Pro",             "days": 30,   "videos_per_day": 50},
    "lifetime": {"label": "Lifetime",        "days": 36500, "videos_per_day": 999},
    "express":  {"label": "Express (48h)",   "days": 2,    "videos_per_day": 10, "total_limit": 10},
}


# ============================================
#  HELPERS — Lecture / Écriture JSON
# ============================================

def _load_licenses() -> dict:
    if not os.path.exists(LICENSES_FILE):
        return {}
    try:
        with open(LICENSES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_licenses(data: dict):
    with open(LICENSES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _sign(payload: str) -> str:
    """Génère une signature HMAC-SHA256 pour sécuriser les réponses."""
    return hmac.new(
        HMAC_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()


def _require_admin(f):
    """Décorateur : vérifie le header X-Admin-Secret sur les routes admin.
    Laisse passer les pré-vols CORS (OPTIONS) sans vérification.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Pré-vol CORS → on laisse passer (le vrai check viendra ensuite)
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        secret = request.headers.get("X-Admin-Secret", "")
        try:
            ok = hmac.compare_digest(str(secret), str(ADMIN_SECRET))
        except Exception:
            ok = False
        if not ok:
            return jsonify({"error": "Accès refusé — secret admin invalide"}), 403
        return f(*args, **kwargs)
    return decorated


# ============================================
#  CORE — Génération & Validation
# ============================================

def generate_license(plan: str, client_name: str, note: str = "", telegram_chat_id: str = "") -> dict:
    """
    Crée une nouvelle clé de licence.

    Args:
        plan             : 'trial', 'starter', 'pro', 'lifetime'
        client_name      : Nom/pseudo du client
        note             : Note libre (ex: "Payé via PayPal le 23/02")
        telegram_chat_id : Chat ID Telegram du client (pour lui envoyer ses vidéos)
                           Le client peut aussi le renseigner lui-même via /license/setup-telegram

    Returns:
        dict avec la clé et toutes les infos
    """
    if plan not in PLANS:
        raise ValueError(f"Plan inconnu : {plan}. Plans dispo : {list(PLANS.keys())}")

    plan_info  = PLANS[plan]
    key        = "SIL-" + str(uuid.uuid4()).upper().replace("-", "")[:20]
    now        = datetime.utcnow()
    expires_at = (now + timedelta(days=plan_info["days"])).strftime("%Y-%m-%d")

    license_data = {
        "key":              key,
        "client_name":      client_name,
        "plan":             plan,
        "plan_label":       plan_info["label"],
        "videos_per_day":   plan_info["videos_per_day"],
        "total_limit":      plan_info.get("total_limit", 0),  # 0 = pas de limite totale
        "created_at":       now.strftime("%Y-%m-%d %H:%M:%S"),
        "expires_at":       expires_at,
        "active":           True,
        "note":             note,
        "telegram_chat_id": telegram_chat_id,
        "usage_today":      0,
        "usage_today_date": now.strftime("%Y-%m-%d"),
        "total_uses":       0,
        "last_use_at":      0,  # Timestamp de la dernière utilisation
    }

    licenses = _load_licenses()
    licenses[key] = license_data
    _save_licenses(licenses)

    tg_status = f"Telegram: {telegram_chat_id}" if telegram_chat_id else "Telegram: non configuré"
    print(f"✅ Licence créée : [{plan.upper()}] {client_name} → {key} (expire: {expires_at} | {tg_status})")
    return license_data


def validate_license(key: str) -> dict:
    """
    Vérifie si une clé est valide.

    Returns:
        {"valid": True/False, "reason": str, "plan": ..., "remaining_days": ...}
    """
    licenses = _load_licenses()

    if key not in licenses:
        return {"valid": False, "reason": "Clé introuvable"}

    lic = licenses[key]

    if not lic.get("active", False):
        return {"valid": False, "reason": "Licence révoquée"}

    # Vérification expiration
    try:
        expires = datetime.strptime(lic["expires_at"], "%Y-%m-%d")
        remaining = (expires - datetime.utcnow()).days
        if remaining < 0:
            return {"valid": False, "reason": f"Licence expirée depuis {abs(remaining)} jours"}
    except Exception:
        remaining = 0

    # Vérification quota journalier
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if lic.get("usage_today_date") != today:
        lic["usage_today"] = 0
        lic["usage_today_date"] = today

    usage_today   = lic.get("usage_today", 0)
    videos_per_day = lic.get("videos_per_day", 0)
    total_uses     = lic.get("total_uses", 0)
    total_limit    = lic.get("total_limit", 0)

    # Cooldown 5 minutes (300 secondes)
    last_use = lic.get("last_use_at", 0)
    now_ts = time.time()
    if now_ts - last_use < 300:
        remaining_wait = int(300 - (now_ts - last_use))
        return {
            "valid": False,
            "reason": f"Veuillez patienter encore {remaining_wait // 60}m {remaining_wait % 60}s avant la prochaine vidéo."
        }

    # Limite totale (abonnement 48h / 10 vidéos)
    if total_limit > 0 and total_uses >= total_limit:
        return {
            "valid": False,
            "reason": f"Limite totale atteinte ({total_uses}/{total_limit} vidéos). Votre abonnement est terminé."
        }

    if usage_today >= videos_per_day:
        return {
            "valid":  False,
            "reason": f"Quota journalier atteint ({usage_today}/{videos_per_day} vidéos aujourd'hui). Reviens demain !"
        }

    return {
        "valid":            True,
        "reason":           "OK",
        "client_name":      lic["client_name"],
        "plan":             lic["plan"],
        "plan_label":       lic["plan_label"],
        "remaining_days":   remaining,
        "usage_today":      usage_today,
        "videos_per_day":   videos_per_day,
        "expires_at":       lic["expires_at"],
        "telegram_chat_id": lic.get("telegram_chat_id", ""),  # ← Renvoyé au pipeline
    }


def consume_license(key: str) -> bool:
    """
    Incrémente le compteur d'utilisation après une génération de vidéo.
    Appelle cette fonction APRÈS avoir généré une vidéo avec succès.

    Returns:
        True si succès, False si clé introuvable
    """
    licenses = _load_licenses()
    if key not in licenses:
        return False

    lic  = licenses[key]
    today = datetime.utcnow().strftime("%Y-%m-%d")

    if lic.get("usage_today_date") != today:
        lic["usage_today"] = 0
        lic["usage_today_date"] = today

    lic["usage_today"]  = lic.get("usage_today", 0) + 1
    lic["total_uses"]   = lic.get("total_uses", 0) + 1
    lic["last_use_at"]  = time.time()
    licenses[key] = lic
    _save_licenses(licenses)
    return True


def revoke_license(key: str) -> bool:
    """Désactive une licence (client arrête de payer, abus, etc.)"""
    licenses = _load_licenses()
    if key not in licenses:
        return False
    licenses[key]["active"] = False
    _save_licenses(licenses)
    print(f"🚫 Licence révoquée : {key}")
    return True


def list_licenses() -> list:
    """Renvoie toutes les licences avec leur statut."""
    licenses = _load_licenses()
    result = []
    for key, lic in licenses.items():
        try:
            expires = datetime.strptime(lic["expires_at"], "%Y-%m-%d")
            remaining = (expires - datetime.utcnow()).days
            status = "✅ Active" if lic["active"] and remaining >= 0 else ("🚫 Révoquée" if not lic["active"] else "⏰ Expirée")
        except Exception:
            remaining = 0
            status = "❓ Inconnu"

        result.append({
            **lic,
            "remaining_days": remaining,
            "status": status
        })
    # Tri par date de création (plus récent en premier)
    result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return result


# ============================================
#  ROUTES FLASK — à enregistrer dans app.py
# ============================================

def register_license_routes(app):
    """
    Appelle cette fonction dans app.py pour enregistrer toutes
    les routes de gestion des licences.

    Usage dans app.py :
        from license_manager import register_license_routes
        register_license_routes(app)
    """

    # --- ROUTE CLIENT : valider sa clé ---
    @app.route("/license/check", methods=["POST"])
    def license_check():
        """
        Appelé par le client pour vérifier sa clé.
        Body JSON : {"key": "SIL-XXXX"}
        """
        data = request.json or {}
        key  = data.get("key", "").strip()

        if not key:
            return jsonify({"valid": False, "reason": "Clé manquante"}), 400

        result = validate_license(key)

        payload   = f"{key}:{result['valid']}:{int(time.time() // 300)}"
        result["sig"] = _sign(payload)

        return jsonify(result), 200 if result["valid"] else 403


    # --- ROUTE CLIENT : enregistrer son Telegram ---
    @app.route("/license/setup-telegram", methods=["POST"])
    def license_setup_telegram():
        """
        Permet au client de lier son Telegram à sa licence.

        Body JSON : {"key": "SIL-XXXX", "telegram_chat_id": "123456789"}

        Comment trouver son chat_id :
        1. Ouvrir Telegram et envoyer /start au bot @userinfobot
        2. Il te répond avec ton ID numérique
        """
        data             = request.json or {}
        key              = data.get("key", "").strip()
        telegram_chat_id = str(data.get("telegram_chat_id", "")).strip()

        if not key or not telegram_chat_id:
            return jsonify({"error": "key et telegram_chat_id requis"}), 400

        # Vérifier que la clé est valide avant d'autoriser la modification
        check = validate_license(key)
        if not check.get("valid"):
            return jsonify({"error": f"Clé invalide : {check.get('reason')}"}), 403

        # Sauvegarder le chat_id
        licenses = _load_licenses()
        licenses[key]["telegram_chat_id"] = telegram_chat_id
        _save_licenses(licenses)

        print(f"📢 Telegram lié : {licenses[key]['client_name']} → chat_id {telegram_chat_id}")
        return jsonify({
            "success":         True,
            "message":         f"✅ Telegram {telegram_chat_id} associé à ta licence !",
            "client_name":     check["client_name"],
            "telegram_chat_id": telegram_chat_id
        })


    # --- ROUTES ADMIN ---

    @app.route("/admin/licenses", methods=["GET"])
    @_require_admin
    def admin_list_licenses():
        """Liste toutes les licences. Header requis : X-Admin-Secret"""
        return jsonify({"licenses": list_licenses(), "count": len(list_licenses())})


    @app.route("/admin/licenses/create", methods=["POST"])
    @_require_admin
    def admin_create_license():
        """
        Crée une nouvelle licence.
        Body JSON : {"plan": "starter", "client_name": "Jean Dupont", "note": "Payé PayPal",
                     "telegram_chat_id": "123456789"}  ← optionnel, le client peut le faire lui-même
        Header requis : X-Admin-Secret
        """
        data             = request.json or {}
        plan             = data.get("plan", "starter")
        client_name      = data.get("client_name", "").strip()
        note             = data.get("note", "")
        telegram_chat_id = str(data.get("telegram_chat_id", "")).strip()

        if not client_name:
            return jsonify({"error": "client_name requis"}), 400

        try:
            lic = generate_license(plan, client_name, note, telegram_chat_id)
            return jsonify({"success": True, "license": lic}), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400


    @app.route("/admin/licenses/set-telegram", methods=["POST"])
    @_require_admin
    def admin_set_telegram():
        """
        Permet à l'admin de forcer le telegram_chat_id d'un client
        (si le client n'arrive pas à le faire lui-même).
        Body JSON : {"key": "SIL-XXXX", "telegram_chat_id": "123456789"}
        Header requis : X-Admin-Secret
        """
        data             = request.json or {}
        key              = data.get("key", "").strip()
        telegram_chat_id = str(data.get("telegram_chat_id", "")).strip()

        if not key or not telegram_chat_id:
            return jsonify({"error": "key et telegram_chat_id requis"}), 400

        licenses = _load_licenses()
        if key not in licenses:
            return jsonify({"error": "Clé introuvable"}), 404

        licenses[key]["telegram_chat_id"] = telegram_chat_id
        _save_licenses(licenses)
        return jsonify({"success": True, "message": f"Telegram {telegram_chat_id} associé à {key}"})


    @app.route("/admin/licenses/revoke", methods=["POST"])
    @_require_admin
    def admin_revoke_license():
        """
        Révoque une licence.
        Body JSON : {"key": "SIL-XXXX"}
        Header requis : X-Admin-Secret
        """
        data = request.json or {}
        key  = data.get("key", "").strip()
        if not key:
            return jsonify({"error": "key requis"}), 400

        ok = revoke_license(key)
        if ok:
            return jsonify({"success": True, "message": f"Licence {key} révoquée"})
        return jsonify({"error": "Clé introuvable"}), 404


    @app.route("/admin/plans", methods=["GET"])
    @_require_admin
    def admin_list_plans():
        """Liste les plans disponibles."""
        return jsonify({"plans": PLANS})

    print("🔑 Routes de licence enregistrées : /license/check + /license/setup-telegram + /admin/licenses/...")
