# -*- coding: utf-8 -*-
"""
scheduler_runner.py
====================
Script intermédiaire lancé par tiktok_scheduler.py pour chaque post.
Il récupère la config via les variables d'environnement injectées par le scheduler
et exécute le pipeline de génération + publication de main.py.
"""

import os
import sys

# Charger le .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Récupération de la config depuis les variables d'environnement (injectées par tiktok_scheduler.py)
QUERY          = os.getenv("SCHEDULER_QUERY",          "anyme023")
TYPE           = os.getenv("SCHEDULER_TYPE",           "channel")
PERIOD         = os.getenv("SCHEDULER_PERIOD",         "7d")
LANG           = os.getenv("SCHEDULER_LANG",           "fr")
TARGET_SECONDS = int(os.getenv("SCHEDULER_TARGET_SECONDS", "75"))
AUTO_POST      = os.getenv("SCHEDULER_AUTO_POST",      "1") == "1"
PUBLISH_NOW    = os.getenv("SCHEDULER_PUBLISH_NOW",    "1") == "1"
SEND_TELEGRAM  = os.getenv("SCHEDULER_SEND_TELEGRAM",  "1") == "1"
ACCOUNT_NAME   = os.getenv("SCHEDULER_ACCOUNT_NAME",   "metheotim")
PLATFORM       = os.getenv("SCHEDULER_PLATFORM",       "tiktok")

print(f"🤖 scheduler_runner.py — Compte : {ACCOUNT_NAME} | Plateforme : {PLATFORM}")
print(f"   Query: {QUERY} | Type: {TYPE} | Période: {PERIOD} | Langue: {LANG}")
print(f"   Target: {TARGET_SECONDS}s | AutoPost: {AUTO_POST} | PublishNow: {PUBLISH_NOW}")

# Import et exécution du pipeline depuis main.py
try:
    import main as main_module
    config_user = {
        "query":          QUERY,
        "type":           TYPE,
        "period":         PERIOD,
        "nb_videos":      1,
        "lang":           LANG,
        "target_seconds": TARGET_SECONDS,
        "auto_post":      AUTO_POST,
        "send_telegram":  SEND_TELEGRAM,
        "publish_now":    PUBLISH_NOW,
        "ignore_history": False,
        # On utilise le compte sélectionné par le scheduler
        # LATE_API_KEY et TIKTOK_ACCOUNT_ID_HAWAII/YOUTUBE_ID_HAWAII sont déjà dans l'env
        "tiktok_account_key": "HAWAII",
        "platform":       PLATFORM,
    }

    # Override dynamique de la clé TIKTOK_ACCOUNT_ID utilisée par main.py
    # main.py lit TIKTOK_ACCOUNT_ID_HAWAII par défaut dans .env,
    # mais on a injecté la bonne valeur dans TIKTOK_ACCOUNT_ID_HAWAII
    # via env_override dans tiktok_scheduler.py
    res = main_module.executer_pipeline(config_user)
    if res > 0:
        print("✅ scheduler_runner.py : pipeline terminé avec succès.")
        sys.exit(0)
    elif res == 0:
        print("ℹ️ scheduler_runner.py : aucun clip trouvé.")
        sys.exit(2)
    elif res == -2:
        print("❌ scheduler_runner.py : échec du pipeline (QUOTA ATTEINT).")
        sys.exit(4)
    else:
        print("❌ scheduler_runner.py : échec du pipeline (erreur API/upload).")
        sys.exit(3)

except Exception as e:
    print(f"❌ scheduler_runner.py : Erreur lors du pipeline : {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
