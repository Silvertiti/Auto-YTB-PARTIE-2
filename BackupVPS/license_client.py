# -*- coding: utf-8 -*-
"""
====================================================
  LICENSE CLIENT — Silvertiti Automation Suite
====================================================
Module côté CLIENT pour valider la clé de licence
au démarrage du script.

Usage :
    from license_client import check_license_or_exit
    check_license_or_exit()   # Bloque si clé invalide

La clé est lue depuis la variable d'environnement
LICENSE_KEY ou demandée interactivement.
====================================================
"""

import os
import sys
import json
import hashlib
import hmac
import time
import requests

# ============================================
#  CONFIG
# ============================================

# URL de TON serveur de licence (ton VPS)
LICENSE_SERVER_URL = os.getenv(
    "LICENSE_SERVER_URL",
    "https://silvertiti.fr"          # ← Remplace par ton domaine si différent
)

# Clé HMAC partagée avec le serveur (même valeur que HMAC_SECRET dans .env)
HMAC_SECRET_CLIENT = os.getenv("HMAC_SECRET", "changeme_hmac_secret")

# Fichier cache local (évite un appel serveur à chaque lancement)
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".license_cache")
CACHE_TTL  = 3600  # 1h en secondes


# ============================================
#  CORE
# ============================================

def _sign(payload: str) -> str:
    return hmac.new(
        HMAC_SECRET_CLIENT.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()


def _load_cache() -> dict:
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                data = json.load(f)
            if time.time() - data.get("ts", 0) < CACHE_TTL:
                return data
    except Exception:
        pass
    return {}


def _save_cache(data: dict):
    try:
        data["ts"] = time.time()
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def _verify_server_sig(key: str, response: dict) -> bool:
    """Vérifie que la réponse vient bien de ton serveur (anti-falsification)."""
    window = int(time.time() // 300)
    for delta in (0, -1, 1):
        payload  = f"{key}:{response.get('valid')}:{window + delta}"
        expected = _sign(payload)
        if hmac.compare_digest(response.get("sig", ""), expected):
            return True
    return False


def validate_key(key: str) -> dict:
    """
    Valide la clé auprès du serveur de licence.

    Returns:
        dict {"valid": bool, "reason": str, ...infos plan...}
    """
    # 1. Essai depuis le cache local
    cache = _load_cache()
    if cache.get("key") == key and cache.get("valid"):
        return cache

    # 2. Appel serveur
    try:
        resp = requests.post(
            f"{LICENSE_SERVER_URL}/license/check",
            json={"key": key},
            timeout=10,
            verify=True
        )
        data = resp.json()

        # Vérification signature serveur
        if not _verify_server_sig(key, data):
            return {"valid": False, "reason": "⚠️ Signature serveur invalide — possible attaque ?"}

        data["key"] = key
        if data.get("valid"):
            _save_cache(data)

        return data

    except requests.exceptions.ConnectionError:
        # Serveur injoignable → on utilise le cache même expiré (mode offline 24h max)
        old_cache = {}
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, "r") as f:
                    old_cache = json.load(f)
        except Exception:
            pass

        if old_cache.get("key") == key and old_cache.get("valid"):
            age_h = (time.time() - old_cache.get("ts", 0)) / 3600
            if age_h < 24:
                print(f"⚠️  Serveur injoignable — utilisation du cache ({age_h:.1f}h)")
                return old_cache

        return {"valid": False, "reason": "Serveur de licence injoignable et pas de cache valide"}

    except Exception as e:
        return {"valid": False, "reason": f"Erreur réseau : {e}"}


def check_license_or_exit(silent: bool = False) -> dict:
    """
    Point d'entrée principal.
    Vérifie la licence au démarrage. Si invalide → affiche l'erreur et quitte.

    Args:
        silent : Si True, n'affiche rien en cas de succès

    Returns:
        dict avec les infos de la licence si valide

    Usage:
        from license_client import check_license_or_exit
        lic = check_license_or_exit()
    """
    key = os.getenv("LICENSE_KEY", "").strip()

    # Si pas de clé dans .env, on la demande interactivement
    if not key:
        print("\n" + "="*55)
        print("  🔑 SILVERTITI AUTOMATION — Clé de Licence Requise")
        print("="*55)
        print("  Achète ton accès sur : [ton lien Discord/Gumroad]")
        print("="*55)
        try:
            key = input("  Entre ta clé de licence : ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n❌ Annulé.")
            sys.exit(1)

    if not key:
        print("❌ Aucune clé fournie. Arrêt.")
        sys.exit(1)

    print(f"🔑 Vérification de la licence...")
    result = validate_key(key)

    if not result.get("valid"):
        print("\n" + "="*55)
        print("  ❌ LICENCE INVALIDE")
        print(f"  Raison : {result.get('reason', 'Inconnue')}")
        print("="*55)
        print("  Pour acheter/renouveler : [ton lien]")
        print("="*55 + "\n")
        sys.exit(1)

    if not silent:
        print(f"  ✅ Licence valide !")
        print(f"  👤 Client    : {result.get('client_name', '?')}")
        print(f"  📦 Plan      : {result.get('plan_label', '?')}")
        print(f"  📅 Expire    : {result.get('expires_at', '?')} ({result.get('remaining_days', '?')} jours)")
        print(f"  🎬 Quota     : {result.get('usage_today', 0)}/{result.get('videos_per_day', '?')} vidéos aujourd'hui\n")

    return result
