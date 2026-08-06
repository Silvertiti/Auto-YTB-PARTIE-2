---
name: vps_deploy
description: Déploie automatiquement les fichiers sur le VPS OVH et reconstruit le conteneur Docker lorsque l'utilisateur demande de publier, poster, push ou déployer sur le VPS.
---

# VPS Deploy & Docker Rebuild Skill

## Déclencheurs (Triggers)
- "publie" / "publier"
- "poster"
- "push sur le vps"
- "déploie sur le vps"

## Actions à exécuter

1. **Transfert SCP / PSCP** :
   ```cmd
   .\pscp.exe -batch -hostkey "ssh-ed25519 255 SHA256:UYxPMgt6qAy1jtidmDVev8zf474AvFcOJWis2NkEZwg" -pw "Iankee01" <fichiers...> ubuntu@51.91.56.161:/home/ubuntu/twitch_bot/
   ```

2. **Rebuild & Relance Docker** :
   ```cmd
   .\plink.exe -batch -hostkey "ssh-ed25519 255 SHA256:UYxPMgt6qAy1jtidmDVev8zf474AvFcOJWis2NkEZwg" -pw "Iankee01" ubuntu@51.91.56.161 "cd /home/ubuntu/twitch_bot && sudo docker compose down && sudo docker compose build && sudo docker compose up -d"
   ```
