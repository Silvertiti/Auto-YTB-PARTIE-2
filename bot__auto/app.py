from flask import Flask, render_template, request, jsonify
import main
import threading
import os

app = Flask(__name__)

@app.route('/')
def index():
    # On cherche toutes les variables qui commencent par TIKTOK_ACCOUNT_ID_
    # Ex: TIKTOK_ACCOUNT_ID_HAWAII -> On garde juste "HAWAII"
    accounts = [
        key.replace("TIKTOK_ACCOUNT_ID_", "") 
        for key in os.environ.keys() 
        if key.startswith("TIKTOK_ACCOUNT_ID_")
    ]
    # On envoie cette liste à la page HTML
    return render_template('index.html', accounts=accounts)

@app.route('/run', methods=['POST'])
def run_bot():
    data = request.json
    
    config = {
        "query": data.get('query', 'anyme023'),
        "type": data.get('type', 'channel'),
        "period": data.get('period', '24h'),
        "nb_videos": int(data.get('nb_videos', 1)),
        "lang": data.get('lang', 'fr'),
        "target_seconds": 60,
        "auto_post": data.get('auto_post', False),
        "send_telegram": data.get('send_telegram', False),
        "publish_now": data.get('publish_now', True),
        "schedule_hour": int(data.get('schedule_hour', 12)),
        "schedule_minute": int(data.get('schedule_minute', 0)),
        
        # Le compte choisi (ex: "HAWAII")
        "tiktok_account_key": data.get('tiktok_account', None)
    }

    thread = threading.Thread(target=main.executer_pipeline, args=(config,))
    thread.start()

    return jsonify({
        "status": "success", 
        "message": f"Bot lancé sur {config['tiktok_account_key'] or 'Défaut'} pour {config['query']} !"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)