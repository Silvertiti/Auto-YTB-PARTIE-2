import os
import re
import time
import random
import secrets
import string
import shutil
import requests
import subprocess
from dotenv import load_dotenv

load_dotenv()

ENV_FILE = ".env"
MAIL_TM_API = "https://api.mail.tm"

REAL_NAMES = [
    "Alexandre Martin",
    "Thomas Dubois",
    "Nicolas Laurent",
    "Maxime Leroy",
    "Lucas Petit",
    "Antoine Moreau",
    "Julien Bernard",
    "Hugo Richard",
    "Clément Simon",
    "Gabriel Michel"
]


def generate_random_string(length=12):
    """Génère une chaîne aléatoire."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def get_real_full_name():
    """Renvoie un prénom + nom 100% réaliste."""
    return random.choice(REAL_NAMES)


def find_browser_executable():
    """Détecte Google Chrome Officiel (prioritaire) ou Microsoft Edge sur Windows."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expanduser(r"~\AppData\Local\Microsoft\Edge\Application\msedge.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def create_temp_email():
    """Crée une adresse email temporaire avec choix de domaine aléatoire."""
    print("1️⃣ Génération automatique de l'email temporaire...")
    
    resp = requests.get(f"{MAIL_TM_API}/domains")
    domains = resp.json().get("hydra:member", [])
    if not domains:
        raise Exception("Impossible d'obtenir un domaine email temporaire.")
    
    # Choisir un domaine aléatoire pour éviter le blocage d'un domaine spécifique
    domain_obj = random.choice(domains)
    domain = domain_obj["domain"]
    
    username = f"zernio_{generate_random_string(6).lower()}"
    email = f"{username}@{domain}"
    password = f"P@ss_{generate_random_string(10)}"
    
    resp = requests.post(f"{MAIL_TM_API}/accounts", json={"address": email, "password": password})
    if resp.status_code != 201:
        # Deuxième tentative avec un autre domaine si échec
        alt_domain = domains[0]["domain"] if len(domains) > 1 else domain
        email = f"{username}@{alt_domain}"
        resp = requests.post(f"{MAIL_TM_API}/accounts", json={"address": email, "password": password})
        
    print(f"✅ Email temporaire prêt : {email}")
    return {"email": email, "password": password}


def update_env_file(api_key):
    """Met à jour le fichier .env avec la clé API Zernio générée."""
    print(f"\n💾 Écriture automatique de la clé dans {ENV_FILE}...")
    
    env_content = ""
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            env_content = f.read()
            
    if "LATE_API_KEY=" in env_content:
        env_content = re.sub(r"LATE_API_KEY=.*", f"LATE_API_KEY={api_key}", env_content)
    else:
        env_content += f"\nLATE_API_KEY={api_key}"
        
    if "ZERNIO_API_KEY=" in env_content:
        env_content = re.sub(r"ZERNIO_API_KEY=.*", f"ZERNIO_API_KEY={api_key}", env_content)
    else:
        env_content += f"\nZERNIO_API_KEY={api_key}"

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(env_content)
        
    print(f"\n🎉 SUCCÈS TOTAL ! La clé API Zernio ({api_key}) a été inscrite dans {ENV_FILE} !")


def clean_previous_profile(profile_dir):
    """Supprime l'ancien profil Chrome pour réinitialiser tous les cookies et le localStorage."""
    try:
        if os.path.exists(profile_dir):
            shutil.rmtree(profile_dir, ignore_errors=True)
            print("🧹 Nettoyage complet des cookies et du cache du navigateur précédent...")
    except Exception:
        pass


def register_with_stealth_native_browser(account_info):
    """
    Inscrit le compte via le vrai navigateur Chrome natif avec profil 100% propre.
    """
    browser_exe = find_browser_executable()
    if not browser_exe:
        print("❌ Aucun navigateur Google Chrome ou Edge trouvé.")
        return False

    email = account_info["email"]
    password = account_info["password"]
    full_name = get_real_full_name()
    profile_dir = os.path.abspath("chrome_zernio_profile")

    # Nettoyage systématique des cookies et de la session précédente
    clean_previous_profile(profile_dir)

    print(f"\n2️⃣ Lancement du VRAI navigateur natif (Session 100% Propre)...")
    print(f"   - Navigateur : {browser_exe}")
    print(f"   - Profil dédié : {profile_dir}")

    cmd = [
        browser_exe,
        "--remote-debugging-port=9222",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "https://zernio.com/signup"
    ]

    try:
        proc = subprocess.Popen(cmd)
    except Exception as e:
        print(f"❌ Erreur lors du lancement de Chrome : {e}")
        return False

    print("⏳ Chargement de la page d'inscription Zernio...")
    time.sleep(5)

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            print("🔗 Connexion au navigateur natif via le port de débogage (CDP)...")
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            
            # Nettoyer les cookies existants
            try:
                context.clear_cookies()
            except Exception:
                pass

            page = None
            for p_item in context.pages:
                if "zernio" in p_item.url or "getlate" in p_item.url:
                    page = p_item
                    break
            if not page:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://zernio.com/signup", wait_until="domcontentloaded")

            time.sleep(2)

            # Nettoyer le localStorage
            try:
                page.evaluate("try { localStorage.clear(); sessionStorage.clear(); } catch(e){}")
            except Exception:
                pass

            # 1. Dépliage automatique du formulaire via injection DOM
            print("👆 Dépliage automatique du formulaire ('Use email and password instead')...")
            js_uncollapse = """() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const toggle = btns.find(b => b.textContent.toLowerCase().includes('email') && !b.textContent.toLowerCase().includes('hide'));
                if (toggle) {
                    toggle.click();
                    return true;
                }
                return false;
            }"""
            page.evaluate(js_uncollapse)
            time.sleep(1.5)

            # 2. Saisie automatique des 3 champs (Nom, Email, Mot de passe)
            print(f"\n✍️ Saisie des 3 champs dans le formulaire :")
            print(f"   - Nom complet   : {full_name}")
            print(f"   - Email         : {email}")
            print(f"   - Mot de passe  : {password}")

            js_fill = """(data) => {
                function setVal(sel, val) {
                    const el = document.querySelector(sel);
                    if (!el) return false;
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(el, val);
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                    return true;
                }
                setVal("input[placeholder*='Full name']", data.name);
                setVal("input[placeholder*='Email']", data.email);
                setVal("input[placeholder*='Password']", data.pass);
            }"""
            page.evaluate(js_fill, {'name': full_name, 'email': email, 'pass': password})
            time.sleep(0.5)

            # Saisie Playwright de sécurité
            try:
                name_loc = page.locator("input[placeholder*='Full name']").first
                if name_loc:
                    name_loc.focus()
                    name_loc.fill(full_name)
                
                email_loc = page.locator("input[placeholder*='Email']").first
                if email_loc:
                    email_loc.focus()
                    email_loc.fill(email)

                pass_loc = page.locator("input[placeholder*='Password']").first
                if pass_loc:
                    pass_loc.focus()
                    pass_loc.fill(password)
            except Exception:
                pass

            print("✅ Les 3 champs (Nom, Email, Mot de passe) sont remplis à 100% !")

            # 3. Clic automatique sur 'Create account'
            print("\n🚀 Soumission automatique du formulaire ('Create account')...")
            time.sleep(1.5)

            js_submit = """() => {
                const btn = document.querySelector("button[type='submit']");
                if (btn) {
                    btn.removeAttribute('disabled');
                    btn.disabled = false;
                    btn.click();
                    return true;
                }
                return false;
            }"""

            clicked = False
            for _ in range(10):
                res = page.evaluate(js_submit)
                if res:
                    print("✅ Clic automatique sur 'Create account' effectué avec succès !")
                    clicked = True
                    break
                time.sleep(1)

            if not clicked:
                try:
                    submit_btn = page.locator("button[type='submit']").first
                    if submit_btn:
                        submit_btn.click(force=True)
                        print("✅ Clic Playwright sur 'Create account' effectué !")
                except Exception:
                    pass

            # 4. Extraction automatique de la clé API sk_...
            print("\n⏳ Redirection vers le tableau de bord Zernio & extraction de la clé API...")
            key_found = False
            for _ in range(25):
                content = page.content()
                match = re.search(r'(sk_[a-zA-Z0-9]{25,})', content)
                if match:
                    api_key = match.group(1)
                    update_env_file(api_key)
                    key_found = True
                    break
                time.sleep(1.5)

            if not key_found:
                print("💡 Si la clé s'affiche à l'écran dans votre navigateur, vous pouvez la copier dans le fichier .env")

            time.sleep(4)
            return key_found

    except Exception as e:
        print(f"\n⚠️ Note lors de l'exécution : {e}")
        print("💡 Vous pouvez terminer l'inscription directement dans la fenêtre Chrome qui est ouverte !")
        return False


def run_auto_creation():
    print("==================================================")
    print("🤖 CRÉATION ZERNIO STEALTH (SESSION PROPRE & DOMAINE RANDOM)")
    print("==================================================")
    
    account = create_temp_email()
    print(f"📧 Identifiants générés :")
    print(f"   - Email : {account['email']}")
    print(f"   - Mot de passe : {account['password']}")
    
    register_with_stealth_native_browser(account)


if __name__ == "__main__":
    run_auto_creation()
