import json
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

OUTPUT_FILE = "video_analytics.json"
HISTORY_FILE = "follower_history.json"

def send_telegram_msg(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("⚠️ Pas de config Telegram trouvée.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
        print("📧 Rapport quotidien d'abonnés envoyé avec succès.")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi du rapport quotidien : {e}")

def main():
    print(f"📊 Lancement du rapport d'abonnés quotidien (8h) {datetime.now()}")
    if not os.path.exists(OUTPUT_FILE):
        print("⚠️ Fichier video_analytics.json introuvable.")
        return
        
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Erreur lecture analytiques : {e}")
        return
        
    # Dictionary { account_name: current_followers }
    current_followers = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        account = entry.get('account') or entry.get('channel') or entry.get('query')
        if not account:
            continue
        try:
            followers = int(entry.get('followers', 0))
        except:
            followers = 0
            
        current_followers[account] = max(current_followers.get(account, 0), followers)
        
    # Ne garder que ceux qui ont des abonnés (pour éviter de polluer avec des stats vides)
    current_followers = {k: v for k, v in current_followers.items() if v > 0}
        
    # Charger l'historique d'hier
    history = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass
            
    lines = [f"📈 *Rapport Abonnés — {datetime.now().strftime('%d/%m/%Y')}*\n━━━━━━━━━━━━━━━━━━━━"]
    total_gained = 0
    total_subs = 0
    
    sorted_accounts = sorted(current_followers.items(), key=lambda x: x[1], reverse=True)
    
    for account, subs in sorted_accounts:
        yesterday_subs = int(history.get(account, subs))
        gained = subs - yesterday_subs
        
        total_gained += gained
        total_subs += subs
        
        sign = "+" if gained >= 0 else ""
        lines.append(f"👤 *{account}* : {subs:,} ({sign}{gained:,})")
        
        # Mettre à jour l'historique pour demain
        history[account] = subs
        
    lines.append(f"\n🏆 *Total* : {total_subs:,} ({'+' if total_gained >= 0 else ''}{total_gained:,})")
    
    if len(lines) > 2:
        send_telegram_msg("\n".join(lines).replace(",", " "))
        
    # Sauvegarder les stats pour le rapport de demain
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Erreur sauvegarde historique abonnés : {e}")

if __name__ == "__main__":
    main()
