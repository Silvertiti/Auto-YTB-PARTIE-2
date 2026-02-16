import customtkinter as ctk
import requests
import threading
import json
import os
import time
import keyboard
from plyer import notification

# --- CONFIGURATION ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")
CONFIG_FILE = "config_client.json"
API_URL = "http://51.91.56.161:5000"

# --- COULEURS PERSONNALISÉES ---
COLOR_BG_CARD = "#2b2b2b"
COLOR_ACCENT = "#10b981"       # Vert (Classic)
COLOR_ACCENT_HOVER = "#059669"
COLOR_LIVE = "#ef4444"         # Rouge (Live)
COLOR_LIVE_HOVER = "#dc2626"
COLOR_BLUE = "#3b82f6"
COLOR_RED = "#ef4444"
COLOR_TEXT_GRAY = "#a1a1aa"

class ModernQueueClient(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Manager Bot V3")
        self.geometry("420x720")
        self.resizable(False, True)
        
        self.current_hotkey = "f10"
        self.is_listening = False
        self.current_mode = "classic"  # 'classic' ou 'live'
        self.load_config()

        # Titre Principal
        self.lbl_title = ctk.CTkLabel(self, text="DASHBOARD BOT", font=("Roboto", 24, "bold"), text_color="white")
        self.lbl_title.pack(pady=(20, 10))

        # --- 1. CARTE STATUT ---
        self.card_status = ctk.CTkFrame(self, fg_color=COLOR_BG_CARD, corner_radius=15)
        self.card_status.pack(fill="x", padx=20, pady=10)

        self.lbl_status_icon = ctk.CTkLabel(self.card_status, text="⚪", font=("Arial", 24))
        self.lbl_status_icon.pack(side="left", padx=(15, 10), pady=15)

        self.lbl_status_text = ctk.CTkLabel(self.card_status, text="Connexion...", font=("Roboto", 16, "bold"))
        self.lbl_status_text.pack(side="left", pady=15)

        # --- 2. SÉLECTEUR DE MODE (Flip Switch) ---
        self.frame_mode = ctk.CTkFrame(self, fg_color=COLOR_BG_CARD, corner_radius=15)
        self.frame_mode.pack(fill="x", padx=20, pady=10)

        self.frame_switch_row = ctk.CTkFrame(self.frame_mode, fg_color="transparent")
        self.frame_switch_row.pack(pady=(12, 5))

        self.lbl_classic = ctk.CTkLabel(self.frame_switch_row, text="📦 CLASSIC", font=("Roboto", 14, "bold"), text_color=COLOR_ACCENT)
        self.lbl_classic.pack(side="left", padx=(15, 10))

        self.switch_mode = ctk.CTkSwitch(
            self.frame_switch_row, text="", width=60,
            switch_width=50, switch_height=26,
            progress_color=COLOR_LIVE, fg_color=COLOR_ACCENT,
            button_color="white", button_hover_color="#e4e4e7",
            command=self.on_switch_toggle
        )
        self.switch_mode.pack(side="left", padx=5)

        self.lbl_live = ctk.CTkLabel(self.frame_switch_row, text="🔴 LIVE", font=("Roboto", 14, "bold"), text_color=COLOR_TEXT_GRAY)
        self.lbl_live.pack(side="left", padx=(10, 15))

        self.lbl_mode_info = ctk.CTkLabel(self.frame_mode, text="Récupère les meilleurs clips existants", 
                                           font=("Roboto", 11), text_color=COLOR_TEXT_GRAY)
        self.lbl_mode_info.pack(padx=15, pady=(0, 12))

        # --- 3. CARTE ACTION ---
        self.card_input = ctk.CTkFrame(self, fg_color=COLOR_BG_CARD, corner_radius=15)
        self.card_input.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(self.card_input, text="NOUVELLE VIDÉO", font=("Roboto", 12, "bold"), text_color=COLOR_TEXT_GRAY).pack(anchor="w", padx=15, pady=(15, 5))

        self.entry_streamer = ctk.CTkEntry(self.card_input, placeholder_text="Nom du Streamer", height=50, font=("Roboto", 16), border_width=0, fg_color="#18181b")
        self.entry_streamer.pack(fill="x", padx=15, pady=5)
        self.entry_streamer.insert(0, "JLTomy")
        self.entry_streamer.bind('<Return>', lambda event: self.send_job())

        self.btn_add = ctk.CTkButton(self.card_input, text="📦 AJOUTER (CLASSIC)", command=self.send_job, 
                                     height=50, font=("Roboto", 15, "bold"), fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, corner_radius=8)
        self.btn_add.pack(fill="x", padx=15, pady=(10, 15))

        # --- 4. CONFIGURATION TOUCHE ---
        self.frame_bind = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_bind.pack(fill="x", padx=20, pady=0)
        
        self.btn_bind = ctk.CTkButton(self.frame_bind, text=f"Raccourci actuel : {self.current_hotkey.upper()}", 
                                      fg_color="transparent", border_width=1, border_color=COLOR_TEXT_GRAY, 
                                      text_color=COLOR_TEXT_GRAY, hover_color="#3f3f46", command=self.start_listening, height=30)
        self.btn_bind.pack(fill="x")

        # --- 5. FILE D'ATTENTE ---
        ctk.CTkLabel(self, text="FILE D'ATTENTE GLOBALE", font=("Roboto", 12, "bold"), text_color=COLOR_TEXT_GRAY).pack(anchor="w", padx=25, pady=(20, 5))

        self.frame_queue = ctk.CTkScrollableFrame(self, fg_color=COLOR_BG_CARD, corner_radius=15, label_text="")
        self.frame_queue.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        self.lbl_queue_content = ctk.CTkLabel(self.frame_queue, text="Chargement...", justify="left", font=("Roboto", 14), anchor="w")
        self.lbl_queue_content.pack(fill="both", padx=10, pady=10)

        # Logique
        self.update_hotkey_binding()
        threading.Thread(target=self.monitor_loop, daemon=True).start()

    # --- MODE ---

    def on_switch_toggle(self):
        """Appelé quand le switch change de position"""
        if self.switch_mode.get() == 1:  # Switch activé = LIVE
            self.current_mode = "live"
            self.lbl_classic.configure(text_color=COLOR_TEXT_GRAY)
            self.lbl_live.configure(text_color=COLOR_LIVE)
            self.btn_add.configure(text="🔴 AJOUTER (LIVE)", fg_color=COLOR_LIVE, hover_color=COLOR_LIVE_HOVER)
            self.lbl_mode_info.configure(text="⚠️ Le streamer doit être EN LIVE !")
        else:  # Switch désactivé = CLASSIC
            self.current_mode = "classic"
            self.lbl_classic.configure(text_color=COLOR_ACCENT)
            self.lbl_live.configure(text_color=COLOR_TEXT_GRAY)
            self.btn_add.configure(text="📦 AJOUTER (CLASSIC)", fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER)
            self.lbl_mode_info.configure(text="Récupère les meilleurs clips existants")

    # --- HOTKEY ---

    def start_listening(self):
        self.is_listening = True
        self.btn_bind.configure(text="Appuyez sur une touche...", fg_color=COLOR_RED, border_color=COLOR_RED, text_color="white")
        threading.Thread(target=self.listen_for_key, daemon=True).start()

    def listen_for_key(self):
        event = keyboard.read_event()
        if event.event_type == keyboard.KEY_DOWN:
            new_key = event.name
            if new_key not in ['shift', 'ctrl', 'alt', 'windows']:
                self.current_hotkey = new_key
                self.after(0, self.finish_listening)

    def finish_listening(self):
        self.is_listening = False
        self.btn_bind.configure(text=f"Raccourci actuel : {self.current_hotkey.upper()}", fg_color="transparent", border_color=COLOR_TEXT_GRAY, text_color=COLOR_TEXT_GRAY)
        self.update_hotkey_binding()
        self.save_config()
        notification.notify(title="Raccourci mis à jour", message=f"Nouvelle touche : {self.current_hotkey.upper()}")

    def update_hotkey_binding(self):
        try: keyboard.unhook_all()
        except: pass
        try:
            if self.current_hotkey:
                keyboard.add_hotkey(self.current_hotkey, self.send_job)
        except Exception as e: print(f"Bind Error: {e}")

    def save_config(self):
        data = {"hotkey": self.current_hotkey, "mode": self.current_mode}
        with open(CONFIG_FILE, "w") as f: json.dump(data, f)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    self.current_hotkey = data.get("hotkey", "f10")
                    self.current_mode = data.get("mode", "classic")
            except: pass

    # --- ENVOI ---

    def send_job(self):
        if self.is_listening: return
        query = self.entry_streamer.get().strip()
        if not query: return
        threading.Thread(target=self._post_request, args=(query,)).start()

    def _post_request(self, query):
        try:
            # Choisir la route selon le mode
            if self.current_mode == "live":
                endpoint = f"{API_URL}/run_live"
                mode_label = "🔴 LIVE"
            else:
                endpoint = f"{API_URL}/run"
                mode_label = "📦 CLASSIC"
            
            payload = {
                "query": query, 
                "type": "channel", 
                "tiktok_account": "HAWAII", 
                "send_telegram": True
            }
            
            res = requests.post(endpoint, json=payload, timeout=5)
            if res.status_code == 200:
                self.after(0, lambda: notification.notify(
                    title=f"✅ {mode_label}", 
                    message=f"{query} ajouté à la file !"
                ))
                self.refresh_ui()
            else:
                print(f"Erreur API: {res.status_code}")
        except Exception as e: print(f"Err: {e}")

    # --- UI UPDATE ---

    def refresh_ui(self):
        try:
            res = requests.get(f"{API_URL}/queue", timeout=3)
            if res.status_code == 200:
                self.update_display(res.json())
        except:
            self.lbl_status_icon.configure(text="🔴", text_color=COLOR_RED)
            self.lbl_status_text.configure(text="Hors Ligne")

    def update_display(self, data):
        status = data['status']
        waiting = data['waiting_list']

        if status['state'] == "working":
            mode = status.get('current_mode', 'classic')
            if mode == "live":
                self.lbl_status_icon.configure(text="🔴")
                self.lbl_status_text.configure(text=f"LIVE : {status['current_job_name']}")
                self.card_status.configure(border_color=COLOR_LIVE, border_width=2)
            else:
                self.lbl_status_icon.configure(text="🟠")
                self.lbl_status_text.configure(text=f"CLASSIC : {status['current_job_name']}")
                self.card_status.configure(border_color="#f59e0b", border_width=2)
        else:
            self.lbl_status_icon.configure(text="🟢")
            self.lbl_status_text.configure(text="DISPONIBLE")
            self.card_status.configure(border_width=0)
        
        if not waiting:
            txt = "La file d'attente est vide."
        else:
            txt = ""
            for i, name in enumerate(waiting):
                txt += f"{i+1}. {name}\n"
        
        self.lbl_queue_content.configure(text=txt)

    def monitor_loop(self):
        while True:
            if not self.is_listening:
                self.refresh_ui()
            time.sleep(60)

if __name__ == "__main__":
    app = ModernQueueClient()
    # Appliquer le mode sauvegardé
    if app.current_mode == "live":
        app.switch_mode.select()  # Active le switch
        app.on_switch_toggle()    # Met à jour l'UI
    app.mainloop()