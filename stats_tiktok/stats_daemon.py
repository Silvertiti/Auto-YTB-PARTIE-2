import time
import get_last_10  # Ton script qui récupère les stats
from datetime import datetime
import sys

# Intervalle : 21600 secondes = 6 heures
CHECK_INTERVAL = 21600 

print("🚀 Démarrage du Démon de Statistiques TikTok (IPv6)...")
sys.stdout.flush() # Force l'affichage des logs dans Docker

while True:
    print(f"\n⏰ Lancement du scan : {datetime.now()}")
    sys.stdout.flush()
    
    try:
        # Lance la fonction main() de ton script get_last_10.py
        get_last_10.main()
    except Exception as e:
        print(f"❌ Erreur : {e}")
        sys.stdout.flush()
    
    print(f"💤 Pause de {CHECK_INTERVAL/3600} heures...")
    sys.stdout.flush()
    time.sleep(CHECK_INTERVAL)