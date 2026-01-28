# 📂 Documentation des Scripts - Auto YTB

Ce dossier contient une suite d'outils d'automatisation pour la récupération de clips Twitch, le montage vidéo (Shorts/TikTok ou Compilations) et la génération de miniatures.

Voici le détail des scripts classés par fonctionnalité.

## 🤖 Générateurs Vidéos TikTok / Shorts (Vertical 9:16)

Ces scripts sont conçus pour créer automatiquement des vidéos courtes format vertical (1080x1920) optimisées pour TikTok/Shorts/Reels. Ils incluent la détection de visage (Webcam) et le montage automatique.

| Script                                               | Description & Fonctionnalités                                                                                                                                                                                                                               |
| :--------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`Auto_crop_vidéo_tiktok_telegram_1min _live.py`**  | **⭐ RECOMMANDÉ POUR LE DIRECT**<br>• Cible **1 Streamer** spécifique.<br>• **Mode Live** : Priorise les clips du stream _en cours_.<br>• **Mode Fallback** : Si pas de live, prend les dernières 6h.<br>• Montage 1 min, Auto-Crop Webcam, Envoi Telegram. |
| **`Auto_crop_vidéo_tiktok_telegram_1min.py`**        | **Standard 24h**<br>• Cible **1 Streamer** spécifique.<br>• Récupère les meilleurs clips des **dernières 24h**.<br>• Montage 1 min, Auto-Crop Webcam, Envoi Telegram.                                                                                       |
| **`Auto_crop_vidéo_tiktok_telegram_1min_langue.py`** | **Viralité Globale**<br>• Ne cible _pas_ un streamer mais une **Langue** (ex: "fr").<br>• Scanne les **Top Jeux** du moment.<br>• Crée des vidéos basées sur les clips les plus vus de la langue.                                                           |
| **`auto_crop_vidéo_tiktok.py`**                      | Version simplifiée ou ancienne du générateur TikTok (sans Telegram/Logique avancée).                                                                                                                                                                        |

---

## 🎬 Créateurs de Compilations (Horizontal 16:9)

Ces scripts sont conçus pour créer des vidéos longues (Best-of) pour YouTube classique, souvent à partir d'une liste de streamers.

| Script                                            | Description & Fonctionnalités                                                                                                                                                                                                                                                          |
| :------------------------------------------------ | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`clip_downloader_grapper_mosaique_combiné.py`** | **⭐ SOLUTION COMPLÈTE BEST-OF**<br>• Lit `streamers.txt`.<br>• Filtre par **Catégorie** (ex: Minecraft).<br>• Sélectionne des clips pour atteindre ~12 min.<br>• **Génère la Miniature (Mosaïque)** avec logo.<br>• Télécharge et **Concatène** la vidéo finale (`video_finale.mp4`). |
| **`top.py`**                                      | **Créateur Vidéo Simple**<br>• Similaire au précédent mais plus orienté "Top Clips".<br>• Télécharge et Concatène avec _MoviePy_.<br>• Ne semble pas générer de miniature mosaïque automatique.                                                                                        |
| **`clip_downloader_grapper_mosaique.py`**         | **Téléchargement + Miniature (Sans Montage)**<br>• Prépare les fichiers pour un montage manuel.<br>• Récupère les clips, génère la **Mosaïque**.<br>• **Ne concatène pas** les vidéos en un seul fichier (télécharge juste les MP4).                                                   |

---

## 📊 Scrapers & Récupérateurs de Données (CSV)

Ces scripts servent à repérer le contenu sans forcément télécharger ou monter la vidéo immédiatement. Utile pour la veille.

| Script                              | Description                                                                                                                     | Fichier de Sortie        |
| :---------------------------------- | :------------------------------------------------------------------------------------------------------------------------------ | :----------------------- |
| **`clipgrapper_catégory_durer.py`** | • Lit `streamers.txt`.<br>• Filtre par **Catégorie**.<br>• Sélectionne un lot de clips pour une **durée précise** (ex: 13 min). | `clips_24h_filtered.csv` |
| **`clipgrapper_multi.py`**          | • Lit `streamers.txt`.<br>• Récupère tous les clips populaires (24h) de la liste.<br>• Pas de filtre de catégorie strict.       | `clips_24h.csv`          |
| **`clipgrapper_solo.py`**           | • Cible **1 Streamer** (hardcodé ou à modifier).<br>• Liste simplement les clips dans la console.                               | _Affichage Console_      |

---

## 🛠️ Outils & Utilitaires

| Script                            | Fonction                                                                             |
| :-------------------------------- | :----------------------------------------------------------------------------------- |
| **`telegram.py`**                 | Script de test pour l'envoi de fichiers/messages vers Telegram.                      |
| **`flush_clips.py`**              | (Probable) Nettoie les dossiers de clips téléchargés/temporaires.                    |
| **`annoter.py` / `trainyolo.py`** | Scripts liés à l'entraînement ou la gestion du modèle de détection de visage (YOLO). |
| **`mosaique.py`**                 | Script autonome pour générer une miniature mosaïque à partir d'images.               |
| **`streamers.txt`**               | Liste des chaînes Twitch à surveiller pour les scripts "multi" et "compilation".     |

## ⚠️ Pré-requis

- Les scripts nécessitent un fichier `yolov8n.pt` (ou similaire) dans `runs/` pour la détection de visage.
- Les clés API Twitch (`client_id`, `client_secret`) doivent être valides.
- Pour Telegram, le `BOT_TOKEN` et `CHAT_ID` doivent être configurés.
