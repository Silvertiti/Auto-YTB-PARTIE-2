# Directives et Règles du Projet Auto YTB

## Déploiement VPS & Rebuild Docker
Quand l'utilisateur demande de **publier**, **poster**, ou **push sur le vps** (ex: "publie", "poste les modifs", "push sur le vps", "déploie") :

1. **Transférer les fichiers** modifiés du projet local vers le VPS via `pscp.exe` :
   - **Hôte** : `51.91.56.161`
   - **Utilisateur** : `ubuntu`
   - **Mot de passe** : `Iankee01`
   - **Dossier distant** : `/home/ubuntu/twitch_bot/`
   - **Empreinte Hostkey** : `ssh-ed25519 255 SHA256:UYxPMgt6qAy1jtidmDVev8zf474AvFcOJWis2NkEZwg`
   - **Exemple de commande** :
     ```cmd
     .\pscp.exe -batch -hostkey "ssh-ed25519 255 SHA256:UYxPMgt6qAy1jtidmDVev8zf474AvFcOJWis2NkEZwg" -pw "Iankee01" <fichiers...> ubuntu@51.91.56.161:/home/ubuntu/twitch_bot/
     ```

2. **Reconstruire et relancer le conteneur Docker sur le VPS** via `plink.exe` :
   - **Commande à exécuter à distance** :
     ```cmd
     .\plink.exe -batch -hostkey "ssh-ed25519 255 SHA256:UYxPMgt6qAy1jtidmDVev8zf474AvFcOJWis2NkEZwg" -pw "Iankee01" ubuntu@51.91.56.161 "cd /home/ubuntu/twitch_bot && sudo docker compose down && sudo docker compose build && sudo docker compose up -d"
     ```
