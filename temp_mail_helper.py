# -*- coding: utf-8 -*-
"""
temp_mail_helper.py
===================
Script de génération d'emails temporaires pour contourner les filtres antispam.
Utilise l'API Guerrilla Mail (domaines : @sharklasers.com, @guerrillamail.com, etc.).
"""

import sys
import time
import random
import string
import re
import requests

DOMAINS = [
    "sharklasers.com",
    "guerrillamail.com",
    "guerrillamail.net",
    "pokemail.net",
    "grr.la"
]

def clean_html(raw_html):
    """Enlève les balises HTML pour afficher le texte propre."""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext.strip()

def create_guerrilla_email(domain_choice=0):
    domain = DOMAINS[domain_choice % len(DOMAINS)]
    try:
        res = requests.get("https://api.guerrillamail.com/ajax.php?f=get_email_address", timeout=10).json()
        sid = res["sid_token"]
        username = res["email_addr"].split("@")[0]
        email = f"{username}@{domain}"
        
        print("\n" + "="*55)
        print(f"📧 ADRESSE EMAIL GÉNÉRÉE : {email}")
        print("="*55 + "\n")
        print("👉 Copiez-collez cette adresse sur le formulaire d'inscription.")
        print("⏳ En attente de la réception du mail de confirmation...\n")
        return email, sid
    except Exception as e:
        print(f"❌ Erreur lors de la génération du mail : {e}")
        return None, None

def listen_for_messages(sid_token, timeout_seconds=120):
    start_time = time.time()
    seen_ids = set()

    # On ignore le mail d'accueil par défaut de Guerrilla Mail
    try:
        init_res = requests.get(f"https://api.guerrillamail.com/ajax.php?f=get_email_list&sid_token={sid_token}&offset=0", timeout=10).json()
        for m in init_res.get("list", []):
            seen_ids.add(m.get("mail_id"))
    except Exception:
        pass

    while time.time() - start_time < timeout_seconds:
        try:
            res = requests.get(f"https://api.guerrillamail.com/ajax.php?f=get_email_list&sid_token={sid_token}&offset=0", timeout=10).json()
            mail_list = res.get("list", [])
            
            for mail in mail_list:
                mail_id = mail.get("mail_id")
                if mail_id not in seen_ids:
                    seen_ids.add(mail_id)
                    
                    # Récupération du message complet
                    detail = requests.get(f"https://api.guerrillamail.com/ajax.php?f=fetch_email&email_id={mail_id}&sid_token={sid_token}", timeout=10).json()
                    
                    subject = detail.get("mail_subject", "Sans objet")
                    body_html = detail.get("mail_body", "")
                    body_text = clean_html(body_html) if body_html else detail.get("mail_excerpt", "")
                    sender = detail.get("mail_from", "Inconnu")
                    
                    print("\n" + "🎉 "*10)
                    print(f"📬 NOUVEAU MAIL REÇU !")
                    print(f"   De     : {sender}")
                    print(f"   Sujet  : {subject}")
                    print("-" * 50)
                    print("📄 CONTENU DU MAIL :")
                    print(body_text[:1000]) # Affiche les 1000 premiers caractères
                    print("🎉 "*10 + "\n")
                    return True
        except Exception:
            pass
            
        time.sleep(4)

    print("⏰ Temps écoulé (120s). Aucun nouveau mail reçu.")
    return False

if __name__ == "__main__":
    print("Sélectionnez le domaine à utiliser :")
    for i, d in enumerate(DOMAINS):
        print(f"  [{i+1}] @{d}")
    
    choice = input("\nVotre choix (1 par défaut) : ").strip()
    idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(DOMAINS) else 0
    
    email, sid = create_guerrilla_email(idx)
    if email and sid:
        listen_for_messages(sid)
