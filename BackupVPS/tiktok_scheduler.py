# -*- coding: utf-8 -*-
"""
tiktok_scheduler.py
====================
Planificateur automatique : 4 canaux TikTok × 3 vidéos/jour.

Architecture :
  • 4 canaux TikTok (BJ, BG, AL, CD), chacun avec 9 comptes LATE (20 posts/mois)
  • 4 × 9 × 20 = 720 posts/mois capacité → 4 × 3 × 30 = 360 utilisés.
  • 3 créneaux/jour : 12h30 · 18h00 · 21h30
  • Tous les jours du mois
  • À chaque créneau : 4 pipelines séquentiels (un par canal)
  • Suppression FTP remplacée par CDN Late (presign + PUT)
"""

import os
import sys
import json
import logging
import subprocess
from datetime import datetime, date

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
except ImportError:
    print("❌ APScheduler non installé. Lance : pip install apscheduler")
    sys.exit(1)

BOT_SETTINGS_FILE = "bot_settings.json"


def _load_bot_settings() -> dict:
    """Charge les paramètres du bot (notifs on/off, etc.)"""
    if os.path.exists(BOT_SETTINGS_FILE):
        try:
            with open(BOT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"notifs_detail": False}


def _send_error_alert(canal_label: str, slot_label: str, reason: str):
    """Envoie une alerte Telegram immédiate en cas d'erreur (toujours actif)."""
    import requests as req
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    text = (
        f"❌ *[{canal_label}]* — {slot_label}\n"
        f"   Raison : {reason}\n"
        f"   ⏰ {datetime.now().strftime('%d/%m %H:%M')}"
    )
    try:
        req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception:
        pass

# ──────────────────────────────────────────────
# DÉFINITION DES 4 CANAUX
# Chaque canal a 9 comptes LATE (pool de rotation)
# ──────────────────────────────────────────────
CHANNELS = [
    {
        "id":    "BJ",
        "name":  "bestoftomy",
        "label": "BestOfJLTomy",
        "query_env":  "SCHEDULER_QUERY_BJ",
        "type_env":   "SCHEDULER_TYPE_BJ",
        "period_env": "SCHEDULER_PERIOD_BJ",
        "lang_env":   "SCHEDULER_LANG_BJ",
        "target_env": "SCHEDULER_TARGET_BJ",
        "late_accounts": [
            {"name": "BJ_1", "late_key_env": "LATE_KEY_BJ_1", "tiktok_id_env": "TIKTOK_ID_BJ_1", "reset_day": 28},
            {"name": "BJ_2", "late_key_env": "LATE_KEY_BJ_2", "tiktok_id_env": "TIKTOK_ID_BJ_2", "reset_day": 28},
        ] + [
            {"name": f"BJ_{i}", "late_key_env": f"LATE_KEY_BJ_{i}", "tiktok_id_env": f"TIKTOK_ID_BJ_{i}", "reset_day": 7}
            for i in range(3, 10)
        ],
    },
    {
        "id":    "BG",
        "name":  "bestofanyme0023",
        "label": "BestOfAnyme0023",
        "query_env":  "SCHEDULER_QUERY_BG",
        "type_env":   "SCHEDULER_TYPE_BG",
        "period_env": "SCHEDULER_PERIOD_BG",
        "lang_env":   "SCHEDULER_LANG_BG",
        "target_env": "SCHEDULER_TARGET_BG",
        "late_accounts": [
            {"name": f"BG_{i}", "late_key_env": f"LATE_KEY_BG_{i}", "tiktok_id_env": f"TIKTOK_ID_BG_{i}", "reset_day": 7}
            for i in range(1, 10)
        ],
    },
    {
        "id":    "AL",
        "name":  "bestofvioletet",
        "label": "BestOfYouladecad",
        "query_env":  "SCHEDULER_QUERY_AL",
        "type_env":   "SCHEDULER_TYPE_AL",
        "period_env": "SCHEDULER_PERIOD_AL",
        "lang_env":   "SCHEDULER_LANG_AL",
        "target_env": "SCHEDULER_TARGET_AL",
        "late_accounts": [
            {"name": f"AL_{i}", "late_key_env": f"LATE_KEY_AL_{i}", "tiktok_id_env": f"TIKTOK_ID_AL_{i}", "reset_day": 7}
            for i in range(1, 10)
        ],
    },
    {
        "id":    "CD",
        "name":  "bestofaenot",
        "label": "BestOfAenot",
        "query_env":  "SCHEDULER_QUERY_CD",
        "type_env":   "SCHEDULER_TYPE_CD",
        "period_env": "SCHEDULER_PERIOD_CD",
        "lang_env":   "SCHEDULER_LANG_CD",
        "target_env": "SCHEDULER_TARGET_CD",
        "late_accounts": [
            {"name": f"CD_{i}", "late_key_env": f"LATE_KEY_CD_{i}", "tiktok_id_env": f"TIKTOK_ID_CD_{i}", "reset_day": 7}
            for i in range(1, 10)
        ],
    },
    {
        "id":    "HS",
        "name":  "bestofterracid",
        "label": "BestOfTerracid",
        "query_env":  "SCHEDULER_QUERY_HS",
        "type_env":   "SCHEDULER_TYPE_HS",
        "period_env": "SCHEDULER_PERIOD_HS",
        "lang_env":   "SCHEDULER_LANG_HS",
        "target_env": "SCHEDULER_TARGET_HS",
        "late_accounts": [
            {"name": f"HS_{i}", "late_key_env": f"LATE_KEY_HS_{i}", "tiktok_id_env": f"TIKTOK_ID_HS_{i}", "reset_day": 8}
            for i in range(1, 10)
        ],
    },
    {
        "id":    "HP",
        "name":  "hopcore",
        "label": "Hopcore",
        "query_env":  "SCHEDULER_QUERY_HP",
        "type_env":   "SCHEDULER_TYPE_HP",
        "period_env": "SCHEDULER_PERIOD_HP",
        "lang_env":   "SCHEDULER_LANG_HP",
        "target_env": "SCHEDULER_TARGET_HP",
        "late_accounts": [
            {"name": f"HP_{i}", "late_key_env": f"LATE_KEY_HP_{i}", "tiktok_id_env": f"TIKTOK_ID_HP_{i}", "reset_day": 8}
            for i in range(1, 6)
        ],
    },
    {
        "id":    "PT",
        "name":  "peurtok",
        "label": "Peurtok",
        "query_env":  "SCHEDULER_QUERY_PT",
        "type_env":   "SCHEDULER_TYPE_PT",
        "period_env": "SCHEDULER_PERIOD_PT",
        "lang_env":   "SCHEDULER_LANG_PT",
        "target_env": "SCHEDULER_TARGET_PT",
        "late_accounts": [
            {"name": f"PT_{i}", "late_key_env": f"LATE_KEY_PT_{i}", "tiktok_id_env": f"TIKTOK_ID_PT_{i}", "reset_day": 8}
            for i in range(1, 6)
        ],
    },
    {
        "id":    "YBT",
        "name":  "bestoftwitchfr",
        "label": "BestOfTwitchFR",
        "query_env":  "SCHEDULER_QUERY_YBT",
        "type_env":   "SCHEDULER_TYPE_YBT",
        "period_env": "SCHEDULER_PERIOD_YBT",
        "lang_env":   "SCHEDULER_LANG_YBT",
        "target_env": "SCHEDULER_TARGET_YBT",
        "platform":   "youtube",
        "slots":      ["10:30", "12:30", "17:30", "20:30"],
        "late_accounts": [
            {"name": f"YBT_{i}", "late_key_env": f"LATE_KEY_YBT_{i}", "tiktok_id_env": f"YOUTUBE_ID_YBT_{i}", "reset_day": 8}
            for i in range(1, 9)
        ],
    },
    {
        "id":    "YC",
        "name":  "youtubecourt",
        "label": "Youtubecourt",
        "query_env":  "SCHEDULER_QUERY_YC",
        "type_env":   "SCHEDULER_TYPE_YC",
        "period_env": "SCHEDULER_PERIOD_YC",
        "lang_env":   "SCHEDULER_LANG_YC",
        "target_env": "SCHEDULER_TARGET_YC",
        "late_accounts": [
            {"name": f"YC_{i}", "late_key_env": f"LATE_KEY_YC_{i}", "tiktok_id_env": f"TIKTOK_ID_YC_{i}", "reset_day": 26}
            for i in range(1, 6)
        ],
    },
    {
        "id":    "AE5",
        "name":  "bestofaenot5",
        "label": "BestOFAenot5",
        "query_env":  "SCHEDULER_QUERY_AE5",
        "type_env":   "SCHEDULER_TYPE_AE5",
        "period_env": "SCHEDULER_PERIOD_AE5",
        "lang_env":   "SCHEDULER_LANG_AE5",
        "target_env": "SCHEDULER_TARGET_AE5",
        "late_accounts": [
            {"name": f"AE5_{i}", "late_key_env": f"LATE_KEY_AE5_{i}", "tiktok_id_env": f"TIKTOK_ID_AE5_{i}", "reset_day": 8}
            for i in range(1, 4)
        ],
    },
    {
        "id":    "GTA",
        "name":  "bestofidater02",
        "label": "BestOfIDATER02",
        "query_env":  "SCHEDULER_QUERY_GTA",
        "type_env":   "SCHEDULER_TYPE_GTA",
        "period_env": "SCHEDULER_PERIOD_GTA",
        "lang_env":   "SCHEDULER_LANG_GTA",
        "target_env": "SCHEDULER_TARGET_GTA",
        "late_accounts": [
            {"name": f"GTA_{i}", "late_key_env": f"LATE_KEY_GTA_{i}", "tiktok_id_env": f"TIKTOK_ID_GTA_{i}", "reset_day": 8}
            for i in range(1, 6)
        ],
    },
]

# Create a master list of SLOTS based on unique times from all channels
channel_slots = set()
for channel in CHANNELS:
    if "slots" in channel:
        for s in channel["slots"]:
            channel_slots.add(s)
    else:
        # Default slots if not specified
        channel["slots"] = ["12:30", "18:00", "21:30"]
        for s in channel["slots"]:
            channel_slots.add(s)

SLOTS = []
for s in sorted(list(channel_slots)):
    hour, minute = map(int, s.split(":"))
    SLOTS.append({"id": f"slot_{hour:02d}{minute:02d}", "label": f"{hour:02d}h{minute:02d}", "hour": hour, "minute": minute})

USAGE_FILE = "tiktok_usage.json"
SLOT_CHECKPOINT_FILE = "slot_checkpoint.json"

# Fenêtre de reprise après crash (en secondes) — 4h max
CHECKPOINT_MAX_AGE_SEC = 4 * 3600

# ──────────────────────────────────────────────
# GESTION DES COMPTEURS MENSUELS
# ──────────────────────────────────────────────

def _load_usage() -> dict:
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_usage(data: dict):
    try:
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"❌ Erreur sauvegarde tiktok_usage.json : {e}")


def _reset_needed(account_name: str, reset_day: int, usage_data: dict) -> bool:
    today          = date.today()
    last_reset_str = usage_data.get(account_name, {}).get("last_reset")
    if not last_reset_str:
        return True
    try:
        last_reset = date.fromisoformat(last_reset_str)
    except ValueError:
        return True

    if last_reset.day == reset_day:
        nm = last_reset.month + 1
        ny = last_reset.year
        if nm > 12:
            nm, ny = 1, ny + 1
        try:
            next_reset = date(ny, nm, reset_day)
        except ValueError:
            import calendar
            next_reset = date(ny, nm, calendar.monthrange(ny, nm)[1])
    else:
        try:
            next_reset = date(last_reset.year, last_reset.month, reset_day)
            if next_reset <= last_reset:
                nm = last_reset.month + 1
                ny = last_reset.year
                if nm > 12:
                    nm, ny = 1, ny + 1
                next_reset = date(ny, nm, reset_day)
        except ValueError:
            return False

    return today >= next_reset


def get_usage_info(account_name: str, reset_day: int = 7) -> dict:
    usage_data = _load_usage()
    if _reset_needed(account_name, reset_day, usage_data):
        logging.info(f"🔄 Reset mensuel '{account_name}' (reset_day={reset_day})")
        usage_data.setdefault(account_name, {})
        usage_data[account_name]["count"]      = 0
        usage_data[account_name]["last_reset"] = date.today().isoformat()
        _save_usage(usage_data)
    acc = usage_data.get(account_name, {})
    return {
        "count":      acc.get("count", 0),
        "limit":      20,
        "reset_day":  reset_day,
        "last_reset": acc.get("last_reset", "jamais"),
    }


def increment_usage(account_name: str):
    usage_data = _load_usage()
    usage_data.setdefault(account_name, {})
    usage_data[account_name]["count"] = usage_data[account_name].get("count", 0) + 1
    _save_usage(usage_data)
    logging.info(f"📊 Compteur '{account_name}' → {usage_data[account_name]['count']}")


def _force_usage_limit(account_name: str, limit: int = 20):
    usage_data = _load_usage()
    usage_data.setdefault(account_name, {})
    usage_data[account_name]["count"] = limit
    _save_usage(usage_data)
    logging.info(f"📊 Compteur '{account_name}' forcé à {limit} (QUOTA ATTEINT)")


def get_all_usage_stats() -> list:
    """Retourne stats de tous les comptes (utilisé par Telegram /tiktokstats)."""
    rows = []
    for ch in CHANNELS:
        for acc in ch["late_accounts"]:
            info = get_usage_info(acc["name"], acc["reset_day"])
            rows.append({
                "channel": ch["label"],
                "name":    acc["name"],
                **info,
            })
    return rows


# ──────────────────────────────────────────────
# SÉLECTION DU COMPTE LATE DISPONIBLE (PAR CANAL)
# ──────────────────────────────────────────────

def pick_account_for_channel(channel: dict) -> dict | None:
    """Sélectionne le premier compte LATE/Zernio disponible pour ce canal."""
    # 1. Essayer de charger les comptes dynamiques depuis zernio_accounts.json
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zernio_accounts.json")
    if not os.path.exists(json_path):
        json_path = "zernio_accounts.json"

    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                zernio_accs = json.load(f)
            
            ch_platform = channel.get("platform", "tiktok").lower()
            ch_name = channel.get("name", "").lower()
            
            for z_acc in zernio_accs:
                z_plat = z_acc.get("platform", "").lower()
                z_user = z_acc.get("username", "").lower()
                
                if z_plat == ch_platform and (ch_name in z_user or z_user in ch_name):
                    acc_name = f"{channel['id']}_{z_user}"
                    info = get_usage_info(acc_name, 8)
                    if info["count"] < info["limit"]:
                        logging.info(
                            f"✅ [{channel['id']}] Compte Zernio sélectionné via JSON : @{z_acc.get('username')} "
                            f"({info['count']}/{info['limit']} posts ce mois)"
                        )
                        return {
                            "name": acc_name,
                            "late_key": z_acc.get("zernio_api_key"),
                            "tiktok_id": z_acc.get("account_id"),
                            "usage_info": info,
                        }
        except Exception as e:
            logging.warning(f"⚠️ Erreur lecture zernio_accounts.json : {e}")

    # 2. Fallback classique via variables d'environnement
    for acc in channel["late_accounts"]:
        info     = get_usage_info(acc["name"], acc["reset_day"])
        late_key = os.getenv(acc["late_key_env"])
        tiktok_id = os.getenv(acc["tiktok_id_env"])

        if not late_key or not tiktok_id:
            logging.warning(f"⚠️ [{channel['id']}] Vars env manquantes : {acc['late_key_env']} / {acc['tiktok_id_env']}")
            continue

        if info["count"] < info["limit"]:
            logging.info(
                f"✅ [{channel['id']}] Compte sélectionné : {acc['name']} "
                f"({info['count']}/{info['limit']} posts ce mois)"
            )
            return {
                "name":       acc["name"],
                "late_key":   late_key,
                "tiktok_id":  tiktok_id,
                "usage_info": info,
            }

    logging.error(f"❌ [{channel['id']}] Tous les comptes LATE / Zernio sont saturés ce mois !")
    return None


# ──────────────────────────────────────────────
# PIPELINE POUR UN CANAL
# ──────────────────────────────────────────────

def run_channel_pipeline(channel: dict, slot_label: str):
    """Lance la génération + publication pour UN canal."""
    ch_id = channel["id"]
    logging.info(f"  ▶ [{ch_id}] Démarrage pipeline — {channel['label']}")

    while True:
        account = pick_account_for_channel(channel)
        if not account:
            reason = "Tous les comptes LATE saturés ce mois"
            _send_error_alert(channel['label'], slot_label, reason)
            return False, 0

        # Config contenu depuis .env
        query       = os.getenv(channel["query_env"],  "Gaming")
        search_type = os.getenv(channel["type_env"],   "game")
        period      = os.getenv(channel["period_env"], "7d")
        lang        = os.getenv(channel["lang_env"],   "fr")
        target      = os.getenv(channel["target_env"], "60")

        env = os.environ.copy()
        env["LATE_API_KEY"]                = account["late_key"]
        if channel.get("platform") == "youtube":
            env["YOUTUBE_ID_HAWAII"]       = account["tiktok_id"]
        else:
            env["TIKTOK_ACCOUNT_ID_HAWAII"]   = account["tiktok_id"]
        env["SCHEDULER_PLATFORM"]          = channel.get("platform", "tiktok")
        env["SCHEDULER_QUERY"]             = query
        env["SCHEDULER_TYPE"]              = search_type
        env["SCHEDULER_PERIOD"]            = period
        env["SCHEDULER_LANG"]              = lang
        env["SCHEDULER_TARGET_SECONDS"]    = target
        env["SCHEDULER_AUTO_POST"]         = "1"
        env["SCHEDULER_PUBLISH_NOW"]       = "1"
        env["SCHEDULER_SEND_TELEGRAM"]     = "0"
        env["SCHEDULER_ACCOUNT_NAME"]      = account["name"]
        env["SCHEDULER_CHANNEL_LABEL"]     = channel["label"]

        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler_runner.py")
        try:
            result = subprocess.run(
                [sys.executable, script],
                env=env,
                timeout=3600,
                capture_output=False,
            )
            if result.returncode == 0:
                increment_usage(account["name"])
                info = get_usage_info(account["name"], account["usage_info"]["reset_day"])
                logging.info(f"  ✅ [{ch_id}] Vidéo postée ! {info['count']}/{info['limit']} ce mois")
                # Mise à jour du viral brain pour ce canal
                try:
                    from viral_brain import update_brain
                    update_brain(channel["label"])
                except Exception as vb_e:
                    logging.warning(f"⚠️ [VB] Mise à jour brain échouée : {vb_e}")
                return True, 1
            elif result.returncode == 2:
                logging.info(f"  ℹ️ [{ch_id}] Aucun clip trouvé (code 2), on ignore.")
                return False, 0
            elif result.returncode == 4:
                reason = f"Quota API Late dépassé (code 4). Forçage de la limite locale."
                logging.error(f"  ❌ [{ch_id}] {reason}")
                info = get_usage_info(account["name"], account["usage_info"]["reset_day"])
                _force_usage_limit(account["name"], info["limit"])
                # Alert admin but continue retrying with the next valid account
                _send_error_alert(channel['label'], slot_label, reason)
                logging.info(f"  🔄 [{ch_id}] Bascule vers un autre compte...")
                continue
            else:
                reason = f"Erreur pipeline ou upload API CDN/Late (code {result.returncode})"
                logging.error(f"  ❌ [{ch_id}] Échec pipeline (code {result.returncode})")
                _send_error_alert(channel['label'], slot_label, reason)
                return False, 0
        except subprocess.TimeoutExpired:
            reason = "Timeout pipeline > 1h"
            logging.error(f"  ❌ [{ch_id}] Timeout > 1h !")
            _send_error_alert(channel['label'], slot_label, reason)
            return False, 0
        except Exception as e:
            reason = f"Exception : {e}"
            logging.error(f"  ❌ [{ch_id}] Exception : {e}")
            _send_error_alert(channel['label'], slot_label, reason)
            return False, 0


# ──────────────────────────────────────────────
# PIPELINE PRINCIPAL (déclenché par le scheduler)
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# CHECKPOINT ANTI-CRASH
# Sauvegarde les canaux traités pour reprendre
# après un redémarrage Docker en milieu de créneau
# ──────────────────────────────────────────────

def _save_checkpoint(slot_label: str, done_channel_ids: list):
    """Sauvegarde l'état du créneau en cours.
    Préserve le started_at original pour ne pas réinitialiser la fenêtre de 4h.
    """
    import time
    # Conserver le started_at original si le checkpoint existe déjà pour ce slot
    started_at = time.time()
    if os.path.exists(SLOT_CHECKPOINT_FILE):
        try:
            with open(SLOT_CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if existing.get("slot_label") == slot_label:
                started_at = existing.get("started_at", started_at)
        except Exception:
            pass
    data = {
        "slot_label":       slot_label,
        "done_channel_ids": done_channel_ids,
        "started_at":       started_at,
    }
    try:
        with open(SLOT_CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.warning(f"⚠️ Checkpoint non sauvegardé : {e}")


def _clear_checkpoint():
    """Efface le checkpoint une fois le créneau terminé."""
    try:
        if os.path.exists(SLOT_CHECKPOINT_FILE):
            os.remove(SLOT_CHECKPOINT_FILE)
    except Exception:
        pass


def _load_checkpoint() -> dict | None:
    """Charge le checkpoint si récent (< CHECKPOINT_MAX_AGE_SEC)."""
    import time
    if not os.path.exists(SLOT_CHECKPOINT_FILE):
        return None
    try:
        with open(SLOT_CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        age = time.time() - data.get("started_at", 0)
        if age > CHECKPOINT_MAX_AGE_SEC:
            logging.info(f"🕐 Checkpoint trop vieux ({age/3600:.1f}h) — ignoré.")
            _clear_checkpoint()
            return None
        return data
    except Exception:
        return None


def _resume_checkpoint():
    """
    Appelé au démarrage du scheduler.
    Si un créneau était en cours et n'est pas terminé,
    lance les canaux restants immédiatement.
    """
    cp = _load_checkpoint()
    if not cp:
        return
    slot_label    = cp.get("slot_label", "")
    done_ids      = set(cp.get("done_channel_ids", []))
    import time
    age_min = (time.time() - cp.get("started_at", 0)) / 60
    logging.info(f"🔄 REPRISE après crash — créneau {slot_label} (interrompu il y a {age_min:.0f} min)")
    logging.info(f"   Canaux déjà traités : {done_ids or 'aucun'}")

    settings = _load_bot_settings()
    autopost_config = settings.get("autopost", {})

    results   = {}
    vid_count = 0
    for channel in CHANNELS:
        ch_id = channel["id"]
        if ch_id in done_ids:
            logging.info(f"   ✅ [{ch_id}] déjà traité — skip")
            continue

        channel_slot_labels = [s.replace(":", "h") for s in channel.get("slots", [])]
        if slot_label not in channel_slot_labels:
            continue

        if autopost_config.get(ch_id, True) is False:
            logging.info(f"🚫 [{ch_id}] Canal désactivé via /autopost, on passe.")
            continue

        logging.info(f"   ▶ [{ch_id}] Reprise pipeline...")
        ok, vids = run_channel_pipeline(channel, slot_label)
        results[ch_id] = ok
        vid_count += vids
        done_ids.add(ch_id)
        _save_checkpoint(slot_label, list(done_ids))

    if results:
        ok_count  = sum(1 for v in results.values() if v)
        nok_count = sum(1 for v in results.values() if not v)
        logging.info(f"✅ Reprise terminée : {ok_count} réussis, {nok_count} échoués")
    else:
        logging.info("ℹ️ Reprise : aucun canal restant à traiter.")

    _clear_checkpoint()


def run_all_channels(slot_label: str, resume_done_ids: set = None):
    """
    Déclenché à chaque créneau.
    Lance séquentiellement le pipeline pour chacun des canaux.
    Envoie un seul message récap en fin de créneau.
    resume_done_ids : set de ch_id déjà traités (utilisé lors d'une reprise)
    """
    logging.info(f"\n{'='*60}")
    logging.info(f"🎬 CRÉNEAU {slot_label} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info(f"   {len(CHANNELS)} canaux × 1 vidéo = {len(CHANNELS)} publications à venir")
    logging.info(f"{'='*60}")

    settings = _load_bot_settings()
    autopost_config = settings.get("autopost", {})

    done_ids  = set(resume_done_ids or [])
    results   = {}
    vid_count = 0

    # Initialise le checkpoint pour ce créneau
    _save_checkpoint(slot_label, list(done_ids))

    for channel in CHANNELS:
        ch_id = channel["id"]

        channel_slot_labels = [s.replace(":", "h") for s in channel.get("slots", [])]
        if slot_label not in channel_slot_labels:
            continue

        if autopost_config.get(ch_id, True) is False:
            logging.info(f"🚫 [{ch_id}] Canal désactivé via /autopost, on passe.")
            continue

        ok, vids = run_channel_pipeline(channel, slot_label)
        results[channel["id"]] = ok
        vid_count += vids
        done_ids.add(ch_id)

        # ✅ Checkpoint mis à jour après chaque canal traité
        _save_checkpoint(slot_label, list(done_ids))

        logging.info("")  # Ligne vide entre chaque canal

    # Créneau terminé → on efface le checkpoint
    _clear_checkpoint()

    ok_count  = sum(1 for v in results.values() if v)
    nok_count = sum(1 for v in results.values() if not v)
    skipped_count = len(CHANNELS) - len(results)
    logging.info(f"📊 Bilan {slot_label} : {ok_count} réussis, {nok_count} échoués, {skipped_count} ignorés (Désactivés)")

    # ── Recap Telegram ─────────────────────────────────
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        err_icon = "❌" if nok_count > 0 else "✅"
        recap = (
            f"📊 *Récap {slot_label} — {datetime.now().strftime('%d/%m/%Y')}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ Vidéos postées : `{ok_count}/{len(CHANNELS)}`\n"
            f"📹 Ajoutées à video\_analytics : `{vid_count}`\n"
            f"{err_icon} Erreurs : `{nok_count}`\n"
            f"⏭️ Ignorées (Off) : `{skipped_count}`"
        )
        import requests as req
        try:
            req.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": recap, "parse_mode": "Markdown"},
                timeout=10,
            )
        except Exception:
            pass


# ──────────────────────────────────────────────
# UTILITAIRE TELEGRAM
# ──────────────────────────────────────────────

def _alert(text: str):
    import requests as req
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception:
        pass


# ──────────────────────────────────────────────
# POINT D'ENTRÉE
# ──────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    total_accounts = sum(len(ch["late_accounts"]) for ch in CHANNELS)
    total_capacity = total_accounts * 20
    logging.info("🕐 Démarrage du TikTok Scheduler")
    logging.info(f"   Canaux   : {len(CHANNELS)} ({', '.join(c['label'] for c in CHANNELS)})")
    logging.info(f"   Créneaux : {', '.join(s['label'] for s in SLOTS)}")
    logging.info(f"   Comptes  : {total_accounts} LATE × 20 posts = {total_capacity}/mois")
    logging.info(f"   Capacité : {len(CHANNELS)} × 3 × 30 = {len(CHANNELS)*3*30} posts/mois ✅ (Capacité max LATE: {total_capacity})")
    logging.info("")

    for ch in CHANNELS:
        logging.info(f"  📺 [{ch['id']}] {ch['label']} :")
        for acc in ch["late_accounts"]:
            info = get_usage_info(acc["name"], acc["reset_day"])
            late_ok = "✅" if os.getenv(acc["late_key_env"]) else "❌ MANQUANT"
            logging.info(
                f"      {late_ok} {acc['name']:<10} : {info['count']:>2}/{info['limit']} posts "
                f"| reset le {info['reset_day']}"
            )
        logging.info("")

    scheduler = BlockingScheduler(timezone="Europe/Paris")

    for slot in SLOTS:
        scheduler.add_job(
            lambda s=slot["label"]: run_all_channels(s),
            CronTrigger(hour=slot["hour"], minute=slot["minute"], timezone="Europe/Paris"),
            id=slot["id"],
            name=f"TikTok {slot['label']}",
            misfire_grace_time=3600,  # Tolère 1h de retard (was 600s)
        )

    def run_daily_followers_report():
        try:
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_followers_report.py")
            subprocess.run([sys.executable, script_path], check=False)
        except Exception as e:
            logging.error(f"❌ Erreur lors de l'exécution du rapport d'abonnés : {e}")

    scheduler.add_job(
        run_daily_followers_report,
        CronTrigger(hour=8, minute=0, timezone="Europe/Paris"),
        id="slot_0800_followers",
        name="Rapport Abonnés 8h00",
        misfire_grace_time=600,
    )

    def run_youtube_long_best_of():
        try:
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_long_best_of.py")
            subprocess.run([sys.executable, script_path], check=False)
        except Exception as e:
            logging.error(f"❌ Erreur lors de l'exécution du best-of YouTube long : {e}")

    scheduler.add_job(
        run_youtube_long_best_of,
        CronTrigger(hour=17, minute=0, timezone="Europe/Paris"),
        id="youtube_long_best_of_job",
        name="Best-Of YouTube Long 17h00",
        misfire_grace_time=3600,
    )

    def run_cleanup_clips():
        try:
            import glob
            folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clips_downloaded")
            if os.path.exists(folder):
                files = glob.glob(os.path.join(folder, "*"))
                count = 0
                for f in files:
                    try:
                        os.remove(f)
                        count += 1
                    except Exception as e:
                        logging.warning(f"⚠️ Impossible de supprimer {f}: {e}")
                logging.info(f"🧹 Nettoyage hebdomadaire terminé : {count} fichiers supprimés dans clips_downloaded.")
        except Exception as e:
            logging.error(f"❌ Erreur lors du nettoyage de clips_downloaded : {e}")

    scheduler.add_job(
        run_cleanup_clips,
        CronTrigger(day_of_week='sun', hour=0, minute=0, timezone="Europe/Paris"),
        id="slot_sunday_cleanup",
        name="Nettoyage clips_downloaded",
        misfire_grace_time=3600,
    )

    logging.info("✅ Scheduler démarré :")
    for job in scheduler.get_jobs():
        logging.info(f"   • {job.name}")

    # ── Reprise automatique après crash ─────────────────
    # Si le container a été tué en milieu de créneau,
    # on relance immédiatement les canaux qui n'ont pas tourné.
    _resume_checkpoint()
    # ─────────────────────────────────────────────────────

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("🛑 Scheduler arrêté.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--from-channel":
        if len(sys.argv) > 2:
            start_id = sys.argv[2].upper()
            found = False
            logging.info(f"🚀 Lancement manuel à partir du canal {start_id}...")
            for ch in CHANNELS:
                if ch["id"] == start_id:
                    found = True
                if found:
                    try:
                        logging.info(f"▶️ Exécution canal {ch['id']} ({ch['label']})...")
                        run_channel_pipeline(ch, f"Manuel FROM_{start_id}")
                    except Exception as e:
                        logging.error(f"❌ Erreur sur le canal {ch.get('id')}: {e}")
            sys.exit(0)
        else:
            logging.error("❌ Veuillez spécifier l'ID de départ (ex: --from-channel CD)")
            sys.exit(1)

    if len(sys.argv) > 1 and sys.argv[1] == "--channel":
        if len(sys.argv) > 2:
            target_id = sys.argv[2].upper()
            if target_id == "ALL":
                logging.info("🚀 Lancement manuel du post sur TOUS LES CANAUX...")
                for ch in CHANNELS:
                    try:
                        run_channel_pipeline(ch, "Manuel ALL")
                    except Exception as e:
                        logging.error(f"❌ Erreur sur le canal {ch.get('id')}: {e}")
                sys.exit(0)
            ch = next((c for c in CHANNELS if c["id"] == target_id), None)
            if ch:
                logging.info(f"🚀 Lancement manuel du canal {target_id} ({ch['label']})...")
                run_channel_pipeline(ch, "Manuel NOW")
                sys.exit(0)
            else:
                logging.error(f"❌ Canal {target_id} introuvable.")
                sys.exit(1)
        else:
            logging.error("❌ Veuillez spécifier l'ID du canal (ex: --channel YC)")
            sys.exit(1)
    main()
