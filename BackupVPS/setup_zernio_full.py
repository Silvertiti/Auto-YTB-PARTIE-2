import os
import sys
import time
import json
import re
import requests
import webbrowser
from dotenv import load_dotenv

# Encodage UTF-8 pour la console Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Charger l'environnement
load_dotenv()

ENV_FILE = ".env"
TOKENS_FILE = "zernio_accounts.json"
ZERNIO_BASE_URL = "https://zernio.com/api/v1"

# Importer Zernio SDK si présent
try:
    from zernio import Zernio
    ZERNIO_SDK_AVAILABLE = True
except ImportError:
    ZERNIO_SDK_AVAILABLE = False


def print_header(title):
    print("\n" + "=" * 60)
    print(f"🚀 {title}")
    print("=" * 60)


def print_step(step_num, title):
    print(f"\n--------------------------------------------------")
    print(f"📌 ÉTAPE {step_num} : {title}")
    print("--------------------------------------------------")


def get_all_stored_api_keys():
    """Récupère toutes les clés API Zernio stockées dans l'environnement / .env."""
    keys = []
    
    # Vérifier ZERNIO_API_KEYS (séparées par virgules)
    raw_keys = os.getenv("ZERNIO_API_KEYS", "")
    if raw_keys:
        for k in raw_keys.split(","):
            k_clean = k.strip()
            if k_clean and k_clean not in keys:
                keys.append(k_clean)

    # Vérifier ZERNIO_API_KEY et LATE_API_KEY
    for env_var in ["ZERNIO_API_KEY", "LATE_API_KEY"]:
        val = os.getenv(env_var, "").strip()
        if val and val not in keys:
            keys.append(val)

    # Vérifier ZERNIO_API_KEY_1, ZERNIO_API_KEY_2...
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("ZERNIO_API_KEY_") or line.startswith("LATE_API_KEY_"):
                    parts = line.strip().split("=", 1)
                    if len(parts) == 2:
                        val = parts[1].strip()
                        if val and val not in keys:
                            keys.append(val)

    return keys


def add_api_key_to_env(new_key):
    """Ajoute une nouvelle clé API Zernio dans .env sans écraser les anciennes."""
    existing_keys = get_all_stored_api_keys()
    if new_key in existing_keys:
        print("ℹ️ Cette clé API est déjà présente dans .env.")
        return

    existing_keys.append(new_key)
    
    env_content = ""
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            env_content = f.read()

    # Mettre à jour ZERNIO_API_KEYS (liste complète séparée par des virgules)
    keys_str = ",".join(existing_keys)
    if "ZERNIO_API_KEYS=" in env_content:
        env_content = re.sub(r"^ZERNIO_API_KEYS=.*", f"ZERNIO_API_KEYS={keys_str}", env_content, flags=re.MULTILINE)
    else:
        if env_content and not env_content.endswith("\n"):
            env_content += "\n"
        env_content += f"ZERNIO_API_KEYS={keys_str}\n"

    # Mettre à jour ZERNIO_API_KEY avec la première clé par défaut si absente
    if "ZERNIO_API_KEY=" not in env_content:
        env_content += f"ZERNIO_API_KEY={new_key}\n"

    # Ajouter l'index spécifique (ZERNIO_API_KEY_N)
    key_idx = len(existing_keys)
    env_content += f"ZERNIO_API_KEY_{key_idx}={new_key}\n"

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(env_content)

    os.environ["ZERNIO_API_KEYS"] = keys_str
    os.environ["ZERNIO_API_KEY"] = existing_keys[0]
    print(f"💾 Nouvelle clé API enregistrée dans .env (Total : {len(existing_keys)} clé(s) Zernio) !")


def step_1_authenticate_zernio():
    """Étape 1 : Authentification CLI Zernio & Ajout de clé API."""
    print_step(1, "AUTHENTIFICATION ZERNIO & CLÉS API")
    
    existing_keys = get_all_stored_api_keys()
    if existing_keys:
        print(f"🔑 {len(existing_keys)} clé(s) API Zernio déjà enregistrée(s) :")
        for i, k in enumerate(existing_keys, 1):
            print(f"   [{i}] {k[:8]}...")
            
        print("\nQue souhaitez-vous faire ?")
        print("1. Conserver les clés existantes et continuer")
        print("2. Ajouter un NOUVEAU compte / clé API Zernio")
        choice = input("Votre choix (1/2) [défaut: 1] : ").strip()
        
        if choice != '2':
            print("✅ Clés API existantes conservées.")
            return existing_keys

    print("\n📡 Demande d'autorisation pour un NOUVEAU compte Zernio...")
    try:
        init_resp = requests.post(
            "https://zernio.com/api/auth/cli/initiate",
            json={"deviceName": f"Agent Setup CLI {len(existing_keys) + 1}"},
            timeout=10
        ).json()
    except Exception as e:
        print(f"❌ Erreur de connexion au serveur Zernio : {e}")
        sys.exit(1)

    device_code = init_resp.get("deviceCode")
    browser_url = init_resp.get("browserUrl")
    interval = init_resp.get("interval", 5)

    print("\n👉 LIEN D'AUTHENTIFICATION ZERNIO :")
    print(f"🔗 {browser_url}\n")
    print("Ouverture automatique dans votre navigateur...")
    try:
        webbrowser.open(browser_url)
    except Exception:
        pass

    print("⏳ Attente de votre autorisation dans le navigateur (veuillez vous connecter au compte Zernio souhaité et cliquer sur Authorize)...")
    headers = {"Authorization": f"Bearer {device_code}"}
    
    start_time = time.time()
    new_api_key = None
    while time.time() - start_time < 900:
        try:
            poll_resp = requests.get("https://zernio.com/api/auth/cli/poll", headers=headers, timeout=10)
            if poll_resp.status_code == 410:
                print("\n❌ La session d'autorisation a expiré.")
                sys.exit(1)
            elif poll_resp.status_code == 200:
                data = poll_resp.json()
                status = data.get("status")
                if status == "pending":
                    print(".", end="", flush=True)
                elif status == "authorized":
                    new_api_key = data.get("apiKey")
                    if new_api_key:
                        print(f"\n\n🎉 Authentification réussie ! Nouvelle clé API obtenue : {new_api_key[:8]}...")
                        add_api_key_to_env(new_api_key)
                        break
                    else:
                        print("\n✅ Autorisé !")
                        break
                elif status == "denied":
                    print("\n❌ Autorisation refusée.")
                    sys.exit(1)
        except Exception as e:
            print(f"\n⚠️ Erreur de polling : {e}")
            
        time.sleep(interval)

    all_keys = get_all_stored_api_keys()
    if not all_keys:
        print("❌ Aucune clé API Zernio disponible.")
        sys.exit(1)

    return all_keys


def step_2_connect_social_accounts(api_keys):
    """Étape 2 : Association de comptes TikTok et/ou YouTube sur une clé API choisie."""
    print_step(2, "ASSOCIATION DE COMPTES RÉSEAUX SOCIAUX (TikTok / YouTube)")
    
    print("Sur quel compte Zernio souhaitez-vous associer de nouveaux comptes ?")
    for i, k in enumerate(api_keys, 1):
        print(f"   [{i}] Clé Zernio {i} ({k[:8]}...)")
    
    try:
        idx_str = input(f"Sélectionnez le compte Zernio (1-{len(api_keys)}) [défaut: {len(api_keys)}] : ").strip()
        selected_idx = int(idx_str) - 1 if idx_str else len(api_keys) - 1
        if selected_idx < 0 or selected_idx >= len(api_keys):
            selected_idx = len(api_keys) - 1
    except ValueError:
        selected_idx = len(api_keys) - 1

    selected_key = api_keys[selected_idx]
    print(f"👉 Compte Zernio sélectionné : Clé #{selected_idx + 1} ({selected_key[:8]}...)")

    headers = {
        "Authorization": f"Bearer {selected_key}",
        "Content-Type": "application/json"
    }

    # Choisir la plateforme
    print("\nQuel type de compte souhaitez-vous ajouter ?")
    print("1. TikTok")
    print("2. YouTube")
    p_choice = input("Votre choix (1/2) [défaut: 1] : ").strip()
    platform_name = "youtube" if p_choice == "2" else "tiktok"
    platform_label = "YouTube" if platform_name == "youtube" else "TikTok"

    # Récupérer les profils
    profiles = []
    if ZERNIO_SDK_AVAILABLE:
        try:
            client = Zernio(api_key=selected_key)
            res = client.profiles.list()
            profiles = getattr(res, "profiles", []) if hasattr(res, "profiles") else (res.get("profiles", []) if isinstance(res, dict) else [])
        except Exception:
            pass

    if not profiles:
        try:
            resp = requests.get(f"{ZERNIO_BASE_URL}/profiles", headers=headers, timeout=10)
            if resp.status_code == 200:
                profiles = resp.json().get("profiles", [])
        except Exception:
            pass

    try:
        nb_str = input(f"\nCombien de comptes {platform_label} souhaitez-vous associer sur ce compte Zernio ? (ex: 1) : ").strip()
        count = int(nb_str)
    except ValueError:
        count = 1

    for idx in range(1, count + 1):
        print(f"\n--- Association du compte {platform_label} n°{idx} ---")
        
        target_profile_id = None
        if idx == 1:
            for p in profiles:
                p_dict = p if isinstance(p, dict) else (p.__dict__ if hasattr(p, "__dict__") else {})
                if p_dict.get("isDefault") or getattr(p, "isDefault", False):
                    target_profile_id = getattr(p, "field_id", None) or p_dict.get("_id") or p_dict.get("id")
                    break
            if not target_profile_id and profiles:
                p = profiles[0]
                p_dict = p if isinstance(p, dict) else (p.__dict__ if hasattr(p, "__dict__") else {})
                target_profile_id = getattr(p, "field_id", None) or p_dict.get("_id") or p_dict.get("id")
        
        if not target_profile_id:
            profile_name = f"{platform_label} Account {len(profiles) + idx}"
            print(f"⚙️ Création d'un nouveau profil Zernio : '{profile_name}'...")
            try:
                if ZERNIO_SDK_AVAILABLE:
                    client = Zernio(api_key=selected_key)
                    new_p = client.profiles.create(name=profile_name)
                    p_obj = getattr(new_p, "profile", new_p)
                    target_profile_id = getattr(p_obj, "field_id", None) or getattr(p_obj, "id", None)
                if not target_profile_id:
                    resp = requests.post(f"{ZERNIO_BASE_URL}/profiles", headers=headers, json={"name": profile_name}, timeout=10)
                    data = resp.json()
                    p_obj = data.get("profile", data)
                    target_profile_id = p_obj.get("_id") or p_obj.get("id")
            except Exception as e:
                print(f"⚠️ Erreur lors de la création du profil : {e}")

        if not target_profile_id:
            print(f"❌ Impossible d'obtenir un profileId.")
            continue

        print(f"🔗 Génération du lien {platform_label} (Profile {target_profile_id})...")
        try:
            connect_resp = requests.get(
                f"{ZERNIO_BASE_URL}/connect/{platform_name}?profileId={target_profile_id}",
                headers=headers,
                timeout=10
            )
            connect_data = connect_resp.json()
            auth_url = connect_data.get("authUrl")
            
            if auth_url:
                print(f"\n👉 OUVREZ CE LIEN DANS VOTRE NAVIGATEUR :")
                print(f"🔗 {auth_url}\n")
                try:
                    webbrowser.open(auth_url)
                except Exception:
                    pass
                input(f"➡️ Une fois l'autorisation {platform_label} validée, appuyez sur [Entrée] pour continuer...")
            else:
                print(f"ℹ️ Réponse Zernio : {connect_data}")
        except Exception as e:
            print(f"⚠️ Erreur lors de la génération du lien {platform_label} : {e}")


def step_3_fetch_and_store_all(api_keys):
    """Étape 3 : Récupération des comptes TikTok et YouTube de TOUTES les clés Zernio et enregistrement combiné."""
    print_step(3, "RÉCUPÉRATION & ENREGISTREMENT COMBINÉ DANS zernio_accounts.json")
    
    all_social_accounts = []

    for key_idx, api_key in enumerate(api_keys, 1):
        print(f"📡 Scan du compte Zernio #{key_idx} ({api_key[:8]}...)...")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        raw_accounts = []
        if ZERNIO_SDK_AVAILABLE:
            try:
                client = Zernio(api_key=api_key)
                res = client.accounts.list()
                raw_accounts = getattr(res, "accounts", []) if hasattr(res, "accounts") else (res.get("accounts", []) if isinstance(res, dict) else [])
            except Exception as e:
                print(f"  ℹ️ Remarque SDK : {e}")

        if not raw_accounts:
            try:
                resp = requests.get(f"{ZERNIO_BASE_URL}/accounts", headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_accounts = data.get("accounts", data.get("data", data if isinstance(data, list) else []))
            except Exception as e:
                print(f"  ❌ Erreur REST : {e}")

        for acc in raw_accounts:
            acc_dict = acc if isinstance(acc, dict) else (acc.__dict__ if hasattr(acc, "__dict__") else {})
            
            platform_val = getattr(acc, "platform", None) or acc_dict.get("platform")
            if hasattr(platform_val, "value"):
                platform_str = str(platform_val.value).lower()
            else:
                platform_str = str(platform_val).lower()
                
            account_id = getattr(acc, "field_id", None) or acc_dict.get("_id") or acc_dict.get("id") or acc_dict.get("accountId")
            username = getattr(acc, "username", None) or acc_dict.get("username") or acc_dict.get("name") or "Inconnu"
            status = getattr(acc, "status", None) or acc_dict.get("status") or "active"
            
            profile_obj = getattr(acc, "profileId", None) or acc_dict.get("profileId")
            profile_id = getattr(profile_obj, "field_id", None) if profile_obj else None

            # Support TikTok, YouTube et autres réseaux sociaux
            if any(p in platform_str for p in ["tiktok", "youtube", "instagram", "twitter"]):
                account_entry = {
                    "account_id": account_id,
                    "platform": platform_str,
                    "username": username,
                    "status": status,
                    "zernio_api_key": api_key,
                    "profile_id": profile_id,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                # Éviter les doublons par account_id
                if not any(a["account_id"] == account_id for a in all_social_accounts):
                    all_social_accounts.append(account_entry)

    if not all_social_accounts:
        print("⚠️ Aucun compte connecté n'a été trouvé.")
        return []

    # Sauvegarder dans zernio_accounts.json
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_social_accounts, f, indent=4, ensure_ascii=False)

    print(f"\n🎉 SUCCÈS ! {len(all_social_accounts)} compte(s) au total sauvegardé(s) dans {TOKENS_FILE} !")
    for idx, acc in enumerate(all_social_accounts, 1):
        print(f"   [{idx}] [{acc['platform'].upper()}] Compte : @{acc['username']} | Account ID : {acc['account_id']} | Clé Zernio : {acc['zernio_api_key'][:8]}...")

    return all_social_accounts


if __name__ == "__main__":
    print_header("INSTALLATION & SYNCHRONISATION MULTI-COMPTES (TIKTOK / YOUTUBE)")
    
    # 1. Gestion & Ajout de clés API
    api_keys = step_1_authenticate_zernio()
    
    # 2. Association des comptes (TikTok ou YouTube)
    step_2_connect_social_accounts(api_keys)
    
    # 3. Récupération & Stockage JSON multi-clés & multi-plateformes
    accounts = step_3_fetch_and_store_all(api_keys)
    
    print_header("CONFIGURATION TERMINÉE AVEC SUCCÈS")
    print(f"📁 Vos {len(api_keys)} clés Zernio sont dans : {ENV_FILE}")
    print(f"📁 Vos comptes (TikTok/YouTube) sont synchronisés dans : {TOKENS_FILE}")
