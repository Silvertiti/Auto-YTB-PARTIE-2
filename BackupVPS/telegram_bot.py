# -*- coding: utf-8 -*-
"""
Bot Telegram en mode POLLING (pas de webhook nécessaire).
Gère les commandes /start, /setup, /status, /stats, /clients.
"""

import os
import time
import json
import requests
from datetime import datetime, timedelta

# Charger le .env manuellement si dotenv dispo
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_ID = os.getenv("TELEGRAM_CHAT_ID", "")

API = f"https://api.telegram.org/bot{TOKEN}"


def send_message(chat_id, text):
    try:
        requests.post(f"{API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=10)
    except Exception as e:
        print(f"⚠️ Erreur envoi TG : {e}")


def handle_message(message):
    chat_id  = str(message.get("chat", {}).get("id", ""))
    text     = (message.get("text") or "").strip()
    prenom   = message.get("from", {}).get("first_name", "")
    username = message.get("from", {}).get("username", "")

    if not chat_id or not text:
        return

    print(f"📩 {prenom} (@{username}) | chat_id={chat_id} | '{text}'")

    # ==== /start ====
    if text.startswith("/start"):
        send_message(chat_id,
            f"👋 Bonjour *{prenom}* !\n\n"
            f"Bienvenue sur *Clipo Automation* 🎬\n\n"
            f"🆔 Ton *Chat ID Telegram* est :\n"
            f"`{chat_id}`\n\n"
            f"📋 Copie cet ID et envoie-le à ton administrateur "
            f"pour recevoir tes vidéos directement ici !\n\n"
            f"_Tu peux aussi l'enregistrer toi-même via la commande /setup_\n\n"
            f"Tape /help pour voir toutes les commandes."
        )

    # ==== /help ====
    elif text.startswith("/help"):
        is_admin = chat_id == ADMIN_ID
        msg = (
            "🤖 *Commandes disponibles*\n"
            "────────────────────\n"
            "👤 *Commandes utilisateur*\n"
            "`/start` — Affiche ton Chat ID\n"
            "`/setup CLI-xxx` — Lie ton Telegram a ta licence\n"
            "`/status CLI-xxx` — Statut de ta licence\n"
        )
        if is_admin:
            msg += (
                "\n🔐 *Commandes admin*\n"
                "`/tiktokstats` — Quotas LATE de tous les comptes\n"
                "`/canaux` — Canaux TikTok et comptes LATE associés\n"
                "`/autopost [CANAL] on|off` — Activer/désactiver l'auto-post\n"
                "`/post BJ` — Post manuel BestOfJLTomy\n"
                "`/post BG` — Post manuel BestOfAnyme0023\n"
                "`/post AL` — Post manuel BestOfYouladecad\n"
                "`/post CD` — Post manuel BestOfAenot\n"
                "`/post HS` — Post manuel BestOfTerracid\n"
                "`/post all` — Post manuel sur les 8 canaux\n"
                "`/stats` — Statistiques générales\n"
                "`/clients` — Liste des licences\n"
                "\n📊 *Statistiques viralité*\n"
                "`/stats24h` — Vues par compte sur les 24 dernières heures\n"
                "`/count @compte` — Total des vidéos réelles et stats d'un compte TikTok\n"
                "`/allcounts` — Bilan des vidéos réelles postées sur TOUS vos comptes\n"
                "`/viral_brain` — État de l'IA auto-adaptative\n"
                "`/meilleurs_creneaux` — Créneaux les plus performants\n"
                "`/lasterrors` — 10 dernières erreurs\n"
                "`/notifs on|off` — Activer/désactiver notifs détaillées\n"
            )
        else:
            msg += "\n_Certaines commandes sont reservees a l'administrateur._"
        send_message(chat_id, msg)

    # ==== /setup SIL-XXX ====
    elif text.startswith("/setup"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id,
                "❓ Usage : `/setup CLI-TACLÉ`\n\n"
                "Exemple : `/setup CLI-ABC123DEF456GH78IJ`"
            )
        else:
            from license_manager import validate_license, _load_licenses, _save_licenses
            key = parts[1].strip()
            check = validate_license(key)
            if not check.get("valid"):
                send_message(chat_id,
                    f"❌ Clé invalide : *{check.get('reason')}*\n"
                    "Vérifie ta clé et réessaie."
                )
            else:
                licenses = _load_licenses()
                licenses[key]["telegram_chat_id"] = chat_id
                _save_licenses(licenses)
                print(f"✅ Auto-setup Telegram : {check['client_name']} → chat_id {chat_id}")
                send_message(chat_id,
                    f"✅ *Parfait {check['client_name']} !*\n\n"
                    f"Ton Telegram est maintenant lié à ta licence *{check['plan_label']}*.\n"
                    f"Tu recevras tes vidéos directement ici ! 🎬\n\n"
                    f"📅 Licence valide jusqu'au : `{check['expires_at']}`\n"
                    f"🎬 Quota : `{check['usage_today']}/{check['videos_per_day']}` vidéos aujourd'hui"
                )

    # ==== /status SIL-XXX ====
    elif text.startswith("/status"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "❓ Usage : `/status CLI-TACLÉ`")
        else:
            from license_manager import validate_license
            key   = parts[1].strip()
            check = validate_license(key)
            if check.get("valid"):
                send_message(chat_id,
                    f"📊 *Statut de ta licence*\n\n"
                    f"👤 Client  : `{check['client_name']}`\n"
                    f"📦 Plan    : `{check['plan_label']}`\n"
                    f"📅 Expire  : `{check['expires_at']}` ({check['remaining_days']} jours)\n"
                    f"🎬 Quota   : `{check['usage_today']}/{check['videos_per_day']}` vidéos aujourd'hui"
                )
            else:
                send_message(chat_id, f"❌ *{check.get('reason')}*")

    # ==== /canaux (ADMIN ONLY) ====
    elif text.startswith("/canaux"):
        if chat_id != ADMIN_ID:
            send_message(chat_id, "🚫 Commande reservee a l'administrateur.")
        else:
            try:
                from tiktok_scheduler import CHANNELS, get_usage_info
                for ch in CHANNELS:
                    query  = os.getenv(ch["query_env"],  "?")
                    period = os.getenv(ch["period_env"], "?")
                    lines  = [
                        f"📺 *{ch['label']}* (`{ch['id']}`)",
                        f"   🎯 Source : `{query}` | Periode : `{period}`",
                        ""
                    ]
                    for acc in ch["late_accounts"]:
                        info      = get_usage_info(acc["name"], acc["reset_day"])
                        tiktok_id = os.getenv(acc["tiktok_id_env"], "MANQUANT")
                        late_key  = os.getenv(acc["late_key_env"], "")
                        key_short = f"...{late_key[-8:]}" if late_key else "❌ MANQUANT"
                        status    = "🔴" if info["count"] >= info["limit"] else "🟢"
                        lines.append(
                            f"   {status} `{acc['name']}` | "
                            f"Cle : `{key_short}` | "
                            f"`{info['count']}/{info['limit']}`posts"
                        )
                    send_message(chat_id, "\n".join(lines))
            except Exception as e:
                send_message(chat_id, f"❌ Erreur /canaux : `{e}`")

    # ==== /tiktokstats (ADMIN ONLY) ====
    elif text.startswith("/tiktokstats"):
        if chat_id != ADMIN_ID:
            send_message(chat_id, "🚫 Commande réservée à l'administrateur.")
        else:
            try:
                from tiktok_scheduler import get_all_usage_stats
                stats = get_all_usage_stats()

                total_used  = sum(s["count"] for s in stats)
                total_limit = sum(s["limit"] for s in stats)
                dispo       = sum(1 for s in stats if s["count"] < s["limit"])

                # Message 1 : résumé global
                sep = "─" * 30
                header = (
                    f"📊 *Quotas TikTok — {len(stats)} comptes LATE*\n"
                    f"📅 Mois en cours\n\n"
                    f"📦 Total utilisé : `{total_used}/{total_limit}` posts\n"
                    f"✅ Comptes dispo : `{dispo}/{len(stats)}`\n"
                    f"{sep}"
                )
                send_message(chat_id, header)

                # Message(s) : détail par compte (3 par message pour rester compact)
                chunk_size = 3
                for i in range(0, len(stats), chunk_size):
                    chunk = stats[i:i+chunk_size]
                    lines = []
                    for s in chunk:
                        used   = s["count"]
                        limit  = s["limit"]
                        filled = int((used / limit) * 8) if limit > 0 else 0
                        bar    = "🟩" * filled + "⬜" * (8 - filled)
                        status = "🔴 SATURÉ" if used >= limit else "🟢 OK"
                        lines.append(
                            f"{status} *{s['name']}*\n"
                            f"   {bar} `{used}/{limit}`\n"
                            f"   🔄 Reset : *{s['reset_day']}* du mois • Dernier : `{s['last_reset']}`"
                        )
                    send_message(chat_id, "\n\n".join(lines))

            except Exception as e:
                send_message(chat_id, f"❌ Erreur lecture stats TikTok : `{e}`")

    # ==== /post [BJ|BG|AL|CD|all] (ADMIN ONLY) ====
    elif text.startswith("/post"):
        if chat_id != ADMIN_ID:
            send_message(chat_id, "🚫 Commande réservée à l'administrateur.")
        else:
            parts  = text.split()
            target = parts[1].upper() if len(parts) > 1 else "ALL"

            from tiktok_scheduler import CHANNELS
            valid_ids = {c["id"] for c in CHANNELS}.union({"ALL"})
            if target not in valid_ids:
                help_msg = (
                    f"❓ Canal inconnu : `{target}`\n\n"
                    f"Usage : `/post [{ '|'.join([c['id'] for c in CHANNELS]) }|ALL]`\n\n"
                )
                for c in CHANNELS:
                    help_msg += f"• `{c['id']}` → {c['label']}\n"
                help_msg += "• `ALL` → Tous les canaux"
                send_message(chat_id, help_msg)
            else:
                import threading
                label = "tous les canaux" if target == "ALL" else target
                send_message(chat_id,
                    f"🚀 *Lancement manuel* — `{label}`\n"
                    f"⏳ La vidéo est en cours de génération...\n"
                    f"_Tu recevras une notification à la fin._"
                )

                def _run_post(t, cid):
                    try:
                        from tiktok_scheduler import CHANNELS, run_channel_pipeline, run_all_channels
                        if t == "ALL":
                            run_all_channels("Manuel Telegram")
                        else:
                            ch = next((c for c in CHANNELS if c["id"] == t), None)
                            if ch:
                                run_channel_pipeline(ch, "Manuel Telegram")
                            else:
                                send_message(cid, f"❌ Canal `{t}` introuvable dans le scheduler.")
                    except Exception as ex:
                        send_message(cid, f"❌ Erreur pipeline `/post {t}` : `{ex}`")

                threading.Thread(target=_run_post, args=(target, chat_id), daemon=True).start()

    # ==== /autopost [CANAL] [on|off] (ADMIN ONLY) ====
    elif text.startswith("/autopost"):
        if chat_id != ADMIN_ID:
            send_message(chat_id, "🚫 Commande réservée à l'administrateur.")
        else:
            parts = text.split()
            if len(parts) < 3:
                send_message(chat_id, "❓ Usage : `/autopost [CANAL] [on|off]`\nEx: `/autopost BJ off`")
            else:
                target = parts[1].upper()
                state_str = parts[2].lower()
                
                from tiktok_scheduler import CHANNELS
                valid_ids = {c["id"] for c in CHANNELS}
                if target not in valid_ids:
                    send_message(chat_id, f"❌ Canal inconnu : `{target}`\nCanaux valides : `{', '.join(sorted(valid_ids))}`")
                elif state_str not in ("on", "off"):
                    send_message(chat_id, "❌ L'état doit être `on` ou `off`.")
                else:
                    state = (state_str == "on")
                    settings = {}
                    if os.path.exists("bot_settings.json"):
                        try:
                            with open("bot_settings.json", "r", encoding="utf-8") as f:
                                settings = json.load(f)
                        except:
                            pass
                    
                    if "autopost" not in settings:
                        settings["autopost"] = {}
                        
                    settings["autopost"][target] = state
                    with open("bot_settings.json", "w", encoding="utf-8") as f:
                        json.dump(settings, f, indent=2)
                        
                    status_text = "🟢 ACTIVÉ" if state else "🔴 DÉSACTIVÉ"
                    send_message(chat_id, f"✅ Auto-post pour `{target}` est maintenant {status_text}.")

    # ==== /notifs on|off (ADMIN ONLY) ====
    elif text.startswith("/notifs"):
        if chat_id != ADMIN_ID:
            send_message(chat_id, "🚫 Commande réservée à l'administrateur.")
        else:
            parts = text.split()
            if len(parts) < 2 or parts[1].lower() not in ("on", "off"):
                send_message(chat_id, "❓ Usage : `/notifs on` ou `/notifs off`")
            else:
                state = parts[1].lower() == "on"
                settings = {}
                if os.path.exists("bot_settings.json"):
                    try:
                        with open("bot_settings.json", "r", encoding="utf-8") as f:
                            settings = json.load(f)
                    except Exception:
                        pass
                settings["notifs_detail"] = state
                with open("bot_settings.json", "w", encoding="utf-8") as f:
                    json.dump(settings, f, indent=2)
                icon = "🔔" if state else "🔕"
                label = "ACTIVÉES" if state else "DÉSACTIVÉES"
                send_message(chat_id,
                    f"{icon} *Notifications détaillées : {label}*\n"
                    f"_{('Chaque vidéo postée sera notifiée.' if state else 'Seulement le récap de créneau + erreurs.')}_"
                )

    # ==== /lasterrors (ADMIN ONLY) ====
    elif text.startswith("/lasterrors"):
        if chat_id != ADMIN_ID:
            send_message(chat_id, "🚫 Commande réservée à l'administrateur.")
        else:
            errors_file = "errors.json"
            if not os.path.exists(errors_file) or os.path.getsize(errors_file) == 0:
                send_message(chat_id, "✅ Aucune erreur enregistrée.")
            else:
                try:
                    with open(errors_file, "r", encoding="utf-8") as f:
                        errors = json.load(f)
                except Exception:
                    errors = []
                    if not errors:
                        send_message(chat_id, "✅ Aucune erreur enregistrée.")
                    else:
                        lines = ["🐛 *10 dernières erreurs*\n━━━━━━━━━━━━━━━━━━"]
                        for i, err in enumerate(reversed(errors[:10]), 1):
                            lines.append(
                                f"{i}. [{err.get('timestamp', '?')}] ❌ *[{err.get('canal', '?')}]*\n"
                                f"   `{err.get('type', '?')}` : {err.get('message', '?')}"
                            )
                        send_message(chat_id, "\n".join(lines))
                except Exception as e:
                    send_message(chat_id, f"❌ Erreur lecture errors.json : `{e}`")

    # ==== /stats24h (ADMIN ONLY) ====
    elif text.startswith("/stats24h"):
        if chat_id != ADMIN_ID:
            send_message(chat_id, "🚫 Commande réservée à l'administrateur.")
        else:
            analytics_file = "video_analytics.json"
            if not os.path.exists(analytics_file):
                send_message(chat_id, "⚠️ `video_analytics.json` introuvable.")
            else:
                try:
                    with open(analytics_file, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    videos = raw if isinstance(raw, list) else raw.get("videos", [])

                    cutoff = datetime.now() - timedelta(hours=24)
                    recent = []
                    for v in videos:
                        if not isinstance(v, dict):
                            continue
                        ts_str = v.get("posted_at") or v.get("created_at") or v.get("timestamp", "")
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", ""))
                            if ts >= cutoff:
                                recent.append(v)
                        except Exception:
                            pass

                    if not recent:
                        send_message(chat_id, "📊 Aucune vidéo dans les 24 dernières heures.")
                    else:
                        # Regrouper par compte
                        by_account = {}
                        for v in recent:
                            acc = v.get("account") or v.get("channel") or v.get("query", "inconnu")
                            if acc not in by_account:
                                by_account[acc] = {"count": 0, "views": 0}
                            by_account[acc]["count"] += 1
                            views = v.get("views") or v.get("view_count") or 0
                            by_account[acc]["views"] += int(views)

                        lines = [f"📊 *Stats dernières 24H — {datetime.now().strftime('%d/%m/%Y')}*\n━━━━━━━━━━━━━━━━━━━━━"]
                        total_vids  = 0
                        total_views = 0
                        for acc, data in sorted(by_account.items(), key=lambda x: x[1]["views"], reverse=True):
                            avg = data["views"] // data["count"] if data["count"] else 0
                            lines.append(
                                f"📺 `{acc}`\n"
                                f"   └ {data['count']} vidéos | 👁 {data['views']:,} vues | avg {avg:,}/vidéo"
                            )
                            total_vids  += data["count"]
                            total_views += data["views"]
                        lines.append(f"\n🏆 *Total* : {total_vids} vidéos | {total_views:,} vues")
                        send_message(chat_id, "\n".join(lines))
                except Exception as e:
                    send_message(chat_id, f"❌ Erreur lecture analytics : `{e}`")

    # ==== /meilleurs_creneaux (ADMIN ONLY) ====
    elif text.startswith("/meilleurs_creneaux"):
        if chat_id != ADMIN_ID:
            send_message(chat_id, "🚫 Commande réservée à l'administrateur.")
        else:
            analytics_file = "video_analytics.json"
            if not os.path.exists(analytics_file):
                send_message(chat_id, "⚠️ `video_analytics.json` introuvable.")
            else:
                try:
                    with open(analytics_file, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    videos = raw if isinstance(raw, list) else raw.get("videos", [])

                    cutoff = datetime.now() - timedelta(days=30)
                    creneaux = {}
                    for v in videos:
                        if not isinstance(v, dict):
                            continue
                        ts_str = v.get("posted_at") or v.get("created_at") or v.get("timestamp", "")
                        views  = v.get("views") or v.get("view_count") or 0
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", ""))
                            if ts < cutoff:
                                continue
                            hour_slot = f"{ts.hour:02d}h{ts.minute // 30 * 30:02d}"
                            if hour_slot not in creneaux:
                                creneaux[hour_slot] = {"total": 0, "count": 0}
                            creneaux[hour_slot]["total"] += int(views)
                            creneaux[hour_slot]["count"] += 1
                        except Exception:
                            pass

                    if not creneaux:
                        send_message(chat_id, "📊 Pas assez de données (30 jours).")
                    else:
                        ranked = sorted(
                            creneaux.items(),
                            key=lambda x: (x[1]["total"] / x[1]["count"]) if x[1]["count"] else 0,
                            reverse=True
                        )
                        medals = ["🥇", "🥈", "🥉"]
                        lines = ["📈 *Meilleurs créneaux (30j)*\n━━━━━━━━━━━━━━━━━━"]
                        for i, (slot, data) in enumerate(ranked):
                            avg  = data["total"] // data["count"] if data["count"] else 0
                            icon = medals[i] if i < 3 else "📉"
                            lines.append(f"{icon} {slot} → avg {avg:,} vues ({data['count']} vidéos)")
                        send_message(chat_id, "\n".join(lines))
                except Exception as e:
                    send_message(chat_id, f"❌ Erreur analyse créneaux : `{e}`")

    # ==== /viral_brain (ADMIN ONLY) ====
    elif text.startswith("/viral_brain"):
        if chat_id != ADMIN_ID:
            send_message(chat_id, "🚫 Commande réservée à l'administrateur.")
        else:
            try:
                from viral_brain import get_brain_stats
                brain = get_brain_stats()
                if not brain:
                    send_message(chat_id,
                        "🧠 *Viral Brain* — Pas encore de données.\n"
                        "_Le brain apprend dès que des vidéos sont trackées dans video\_analytics.json_"
                    )
                else:
                    lines = ["🧠 *Viral Brain — État actuel*\n━━━━━━━━━━━━━━━━━━"]
                    for canal, data in brain.items():
                        top_words = [w["word"] for w in data.get("top_words", [])[:4]]
                        top_tags  = [h["tag"] for h in data.get("top_hashtags", [])[:4]]
                        avg       = int(data.get("avg_views", 0))
                        samples   = data.get("learning_samples", 0)
                        lines.append(
                            f"\n📺 *{canal}*\n"
                            f"   🏆 Top mots : `{', '.join(top_words) or 'N/A'}`\n"
                            f"   #️⃣ Top hashtags : `{' '.join(top_tags) or 'N/A'}`\n"
                            f"   📊 Vues moy. : `{avg:,}/vidéo` ({samples} samples)"
                        )
                    send_message(chat_id, "\n".join(lines))
            except Exception as e:
                send_message(chat_id, f"❌ Erreur /viral\_brain : `{e}`")

    # ==== /count @username (ADMIN ONLY) ====
    elif text.startswith("/count") or text.startswith("/ttcount"):
        if chat_id != ADMIN_ID:
            send_message(chat_id, "🚫 Commande réservée à l'administrateur.")
        else:
            parts = text.split()
            if len(parts) < 2:
                send_message(chat_id, "❓ Usage : `/count @nom_du_compte`\nExemple : `/count @youtubecourt`")
            else:
                target_user = parts[1].strip()
                send_message(chat_id, f"🔍 Analyse du profil TikTok `{target_user}` en cours...")
                try:
                    from get_tiktok_count import get_tiktok_profile_stats
                    stats = get_tiktok_profile_stats(target_user)
                    if stats:
                        send_message(chat_id,
                            f"📊 *Statistiques TikTok : {stats['username']}*\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"🎬 *Vidéos postées au TOTAL* : `{stats['video_count']}`\n"
                            f"👥 *Abonnés* : `{stats['follower_count']}`\n"
                            f"❤️ *Likes totaux* : `{stats['heart_count']}`"
                        )
                    else:
                        send_message(chat_id, f"❌ Impossible de récupérer les données pour `{target_user}`.")
                except Exception as e:
                    send_message(chat_id, f"❌ Erreur /count : `{e}`")

    # ==== /allcounts (ADMIN ONLY) ====
    elif text.startswith("/allcounts") or text.startswith("/totalvids"):
        if chat_id != ADMIN_ID:
            send_message(chat_id, "🚫 Commande réservée à l'administrateur.")
        else:
            send_message(chat_id, "⏳ Analyse globale de tous vos comptes TikTok en cours...")
            try:
                from tiktok_scheduler import CHANNELS
                from get_tiktok_count import get_tiktok_profile_stats
                
                lines = ["📊 *Statistiques Réelles de Vos Comptes*\n━━━━━━━━━━━━━━━━━━"]
                total_videos_global = 0
                
                for ch in CHANNELS:
                    if ch.get("platform") == "youtube":
                        continue
                    handle = ch.get("name", "")
                    label  = ch.get("label", handle)
                    if not handle:
                        continue
                    stats = get_tiktok_profile_stats(handle)
                    if stats and isinstance(stats.get("video_count"), int):
                        v_count = stats["video_count"]
                        f_count = stats["follower_count"]
                        l_count = stats["heart_count"]
                        total_videos_global += v_count
                        lines.append(
                            f"📺 *{label}* (`@{handle}`)\n"
                            f"   🎬 Vidéos : `{v_count}` | 👥 Abonnés : `{f_count}` | ❤️ Likes : `{l_count}`"
                        )
                    else:
                        lines.append(f"📺 *{label}* (`@{handle}`) — ⚠️ Données indisponibles")
                
                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append(f"🔥 *TOTAL VIDÉOS PUBLIÉES TOUS COMPTES* : `{total_videos_global}`")
                send_message(chat_id, "\n".join(lines))
            except Exception as e:
                send_message(chat_id, f"❌ Erreur /allcounts : `{e}`")



    # ==== /stats et /clients (ADMIN ONLY) ====
    elif text.startswith("/stats") or text.startswith("/clients"):
        if chat_id != ADMIN_ID:
            send_message(chat_id, "🚫 Commande réservée à l'administrateur.")
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

                send_message(chat_id,
                    f"📊 *Statistiques Clipo*\n\n"
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
                    send_message(chat_id, "📭 Aucune licence créée.")
                else:
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
                        send_message(chat_id, f"*Clients {i}/{len(chunks)} :*\n\n" + "\n\n".join(lines))


def main():
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN manquant dans .env")
        return

    print(f"🤖 Bot Telegram démarré en mode POLLING")
    print(f"   Token: ...{TOKEN[-8:]}")
    print(f"   Admin ID: {ADMIN_ID}")

    offset = 0
    while True:
        try:
            resp = requests.get(f"{API}/getUpdates", params={
                "offset": offset,
                "timeout": 30
            }, timeout=35)

            data = resp.json()
            if not data.get("ok"):
                print(f"⚠️ Telegram API erreur : {data}")
                time.sleep(5)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message")
                if msg:
                    handle_message(msg)

        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            print(f"⚠️ Erreur polling : {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
