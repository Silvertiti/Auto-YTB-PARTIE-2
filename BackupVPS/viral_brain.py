# -*- coding: utf-8 -*-
"""
viral_brain.py
==============
Module IA auto-adaptative pour maximiser la viralité des titres et hashtags TikTok.

Fonctionnement :
  1. Lit video_analytics.json pour trouver les meilleures vidéos d'un canal
  2. Extrait les patterns gagnants (mots viraux, hashtags performants)
  3. Injecte ces patterns dans le prompt Groq pour améliorer les futurs titres
  4. Se met à jour automatiquement après chaque créneau
  5. Détecte l'émotion du clip Twitch (fail, clutch, rage, win...) pour un hook ciblé
"""

import os
import json
import re
from datetime import datetime, timedelta
from collections import Counter

BRAIN_FILE    = "viral_brain.json"
ANALYTICS_FILE = "video_analytics.json"

# ── Mots-clés par catégorie d'émotion ──────────────────────────────────────────
EMOTION_KEYWORDS = {
    "CHOC": ["choc", "surprise", "réaction", "reaction", "incroyable", "impossible",
             "unreal", "no way", "fou", "dingue", "direct", "live", "mastu", "record"],
    "FAIL": ["fail", "tombe", "bug", "crash", "mort", "lose", "perdu", "raté", "oops",
             "mauvais", "nul", "catastrophe", "bide", "flop", "kek"],
    "CLUTCH": ["clutch", "1vs5", "1v5", "seul", "alone", "1v1", "duel", "comeback",
               "ace", "penta", "rampage", "insane", "incroyable", "insane", "détruit", "explose"],
    "RAGE": ["rage", "colère", "énervé", "angry", "tilté", "toxic", "ragequit",
             "énorme", "naze", "cheat", "hack", "triche", "tricheur"],
    "WIN": ["win", "gagne", "victoire", "top1", "champion", "winner", "best",
            "premier", "first", "unbeatable", "unkillable"],
    "FUNNY": ["lol", "mdr", "xd", "rire", "drôle", "bizarre", "wtf", "absurde",
              "délire", "trop marrant", "hilarant", "comique", "joke", "gag"],
}

EMOTION_HOOKS = {
    "CHOC":   ("EXPLOSE TOUT EN DIRECT", "😱🔥"),
    "FAIL":   ("FAIL LÉGENDAIRE", "😂🤦"),
    "CLUTCH": ("DÉTRUIT TOUT SEUL", "🔥😤"),
    "RAGE":   ("IL PÈTE UN CÂBLE", "😤🤬"),
    "WIN":    ("VICTOIRE INCROYABLE", "🏆🔥"),
    "FUNNY":  ("MOMENT TROP DRÔLE", "😂🤣"),
    "NEUTRE": ("PEUT-IL VRAIMENT FAIRE ÇA ?", "😱🔥"),
}

# ── Hashtags viraux de base (remplacés par ceux du .env si définis) ─────────────
DEFAULT_VIRAL_HASHTAGS = [
    "#TwitchFR", "#GamingLive", "#Gaming",
    "#Live", "#Viral", "#Fail", "#Clutch", "#BestOfTwitch"
]

# ─────────────────────────────────────────────────────────────────────────────────
# FONCTIONS UTILITAIRES
# ─────────────────────────────────────────────────────────────────────────────────

def _load_brain() -> dict:
    """Charge le fichier de mémoire viral_brain.json."""
    if os.path.exists(BRAIN_FILE):
        try:
            with open(BRAIN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_brain(data: dict):
    """Sauvegarde la mémoire dans viral_brain.json."""
    try:
        with open(BRAIN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ [VB] Impossible de sauvegarder viral_brain.json : {e}")


def _load_analytics() -> list:
    """Charge video_analytics.json."""
    if os.path.exists(ANALYTICS_FILE):
        try:
            with open(ANALYTICS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Peut être une liste ou un dict avec clé "videos"
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return data.get("videos", [])
        except Exception:
            pass
    return []


def _get_viral_hashtags_from_env() -> list:
    """Récupère les hashtags viraux depuis la variable d'environnement."""
    raw = os.getenv("VIRAL_HASHTAGS_FR", "")
    if raw:
        return [h.strip() for h in raw.split() if h.startswith("#")]
    return DEFAULT_VIRAL_HASHTAGS


# ─────────────────────────────────────────────────────────────────────────────────
# DÉTECTION D'ÉMOTION
# ─────────────────────────────────────────────────────────────────────────────────

def detect_emotion(clip_title: str) -> str:
    """
    Détecte l'émotion dominante d'un titre de clip Twitch.
    Retourne : 'FAIL', 'CLUTCH', 'RAGE', 'WIN', 'FUNNY', 'CHOC', ou 'NEUTRE'
    """
    if not clip_title:
        return "NEUTRE"
    
    title_lower = clip_title.lower()
    scores = {emotion: 0 for emotion in EMOTION_KEYWORDS}
    
    for emotion, keywords in EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in title_lower:
                scores[emotion] += 1
    
    best_emotion = max(scores, key=scores.get)
    if scores[best_emotion] == 0:
        return "NEUTRE"
    
    return best_emotion


def get_emotion_hook(emotion: str) -> tuple[str, str]:
    """
    Retourne (label_hook, emojis) pour l'émotion donnée.
    """
    return EMOTION_HOOKS.get(emotion, EMOTION_HOOKS["NEUTRE"])


# ─────────────────────────────────────────────────────────────────────────────────
# ANALYSE DES PERFORMANCES
# ─────────────────────────────────────────────────────────────────────────────────

def _extract_words_from_title(title: str) -> list[str]:
    """Extrait les mots significatifs (>3 chars, sans stopwords) d'un titre."""
    stopwords = {
        "avec", "dans", "pour", "mais", "sur", "par", "son", "ses", "les", "des",
        "une", "que", "qui", "est", "pas", "tout", "plus", "leur", "cette",
        "fait", "avec", "bien", "très", "fois", "comme", "même", "sous",
        "the", "and", "for", "with", "his", "her", "they", "that", "this",
        "sur", "aux", "ces", "aussi", "dit", "lui", "si", "car", "trop",
    }
    words = re.findall(r'\b[^\W\d_]{3,}\b', title.upper())
    return [w for w in words if w.lower() not in stopwords]


def update_brain(canal_label: str):
    """
    Met à jour la mémoire viral_brain.json pour un canal donné.
    À appeler après chaque créneau de publication.
    
    - Lit les vidéos récentes du canal dans video_analytics.json
    - Trie par vues
    - Extrait les mots et hashtags des top 5 vidéos
    - Marque les top performers (>200% de la moyenne)
    - Sauvegarde dans viral_brain.json
    """
    print(f"🧠 [VB] Mise à jour du brain pour : {canal_label}")
    
    analytics = _load_analytics()
    if not analytics:
        print("⚠️ [VB] video_analytics.json vide ou introuvable.")
        return

    # Filtrer sur ce canal (cherche dans url ou account)
    canal_videos = [
        v for v in analytics
        if isinstance(v, dict) and (
            canal_label.lower() in str(v.get("account", "")).lower()
            or canal_label.lower() in str(v.get("channel", "")).lower()
            or canal_label.lower() in str(v.get("query", "")).lower()
        )
    ]
    
    if not canal_videos:
        # Fallback : toutes les vidéos si pas de filtre canal
        canal_videos = [v for v in analytics if isinstance(v, dict)]
    
    if len(canal_videos) < 3:
        print(f"⚠️ [VB] Pas assez de données pour {canal_label} ({len(canal_videos)} vidéos)")
        return

    # Trier par vues décroissantes
    def get_views(v):
        return v.get("views", v.get("view_count", v.get("vues", 0))) or 0
    
    canal_videos_sorted = sorted(canal_videos, key=get_views, reverse=True)
    
    # Calcul de la moyenne
    all_views   = [get_views(v) for v in canal_videos]
    avg_views   = sum(all_views) / len(all_views) if all_views else 1
    
    # Top 5 vidéos
    top_videos = canal_videos_sorted[:5]
    
    # Extraction des mots viraux depuis les titres des top vidéos
    word_counter  = Counter()
    hash_counter  = Counter()
    top_performers = []
    
    for vid in top_videos:
        title = vid.get("title", vid.get("caption", vid.get("ai_title", ""))) or ""
        views = get_views(vid)
        
        # Mots du titre
        words = _extract_words_from_title(title)
        word_counter.update(words)
        
        # Hashtags
        hashtags = re.findall(r'#\w+', title)
        hash_counter.update(hashtags)
        
        # Top performer : >200% de la moyenne
        is_top = views > (avg_views * 2) and views > 0
        if is_top:
            top_performers.append({
                "title": title,
                "views": views,
                "is_top": True
            })
    
    # Construction des top_words avec boost pour top performers
    top_word_list = []
    for word, count in word_counter.most_common(15):
        # Vérifier si ce mot apparaît dans un top performer
        in_top = any(
            word in (tp.get("title", "").upper()) 
            for tp in top_performers
        )
        top_word_list.append({
            "word": word,
            "score": round(count * (2.0 if in_top else 1.0), 1),
            "top_performer": in_top
        })
    
    # Top hashtags (merge avec hashtags env)
    env_hashtags = _get_viral_hashtags_from_env()
    top_hash_list = []
    for tag, count in hash_counter.most_common(8):
        top_hash_list.append({"tag": tag, "freq": count})
    
    # Ajouter les hashtags env manquants
    existing_tags = {h["tag"] for h in top_hash_list}
    for etag in env_hashtags[:5]:
        if etag not in existing_tags:
            top_hash_list.append({"tag": etag, "freq": 0})
    
    # Sauvegarder
    brain = _load_brain()
    brain[canal_label] = {
        "top_words":        top_word_list,
        "top_hashtags":     top_hash_list,
        "avg_views":        round(avg_views, 0),
        "top_performers":   top_performers[:3],
        "learning_samples": len(canal_videos),
        "last_updated":     datetime.now().isoformat()
    }
    _save_brain(brain)
    
    top_words_str = ", ".join([w["word"] for w in top_word_list[:5]])
    print(f"✅ [VB] Brain mis à jour pour {canal_label} | {len(canal_videos)} samples | Top mots : {top_words_str}")


# ─────────────────────────────────────────────────────────────────────────────────
# GÉNÉRATION DU CONTEXTE POUR GROQ
# ─────────────────────────────────────────────────────────────────────────────────

def get_prompt_context(canal_label: str, emotion: str = "NEUTRE") -> str:
    """
    Génère le contexte à injecter dans le prompt Groq pour ce canal.
    
    Retourne une chaîne de texte prête à être insérée dans le system_instruction.
    """
    brain  = _load_brain()
    canal_data = brain.get(canal_label, {})
    
    # Hook émotionnel
    hook_label, hook_emojis = get_emotion_hook(emotion)
    emotion_context = (
        f"🎭 ÉMOTION DÉTECTÉE : {emotion}\n"
        f"   → Utilise impérativement le style ou la phrase : \"{hook_label} {hook_emojis}\"\n"
        f"   ⛔ RÈGLE ABSOLUE : N'utilise JAMAIS les mots 'SECRET' ou 'REVELE', ils font un flop total.\n"
        f"   ✅ MOTS RECOMMANDÉS : 'EXPLOSE', 'DÉTRUIT', 'EN DIRECT', 'LIVE', questions ('EST-IL ?', 'PEUT-IL ?').\n"
    )
    
    # Hashtags de base depuis env
    env_hashtags = _get_viral_hashtags_from_env()
    hashtag_pool = " ".join(env_hashtags[:6])
    
    # Si pas encore de données brain pour ce canal
    if not canal_data:
        return (
            f"{emotion_context}\n"
            f"#️⃣ HASHTAGS RECOMMANDÉS (pool de base) : {hashtag_pool}\n"
        )
    
    # Données brain disponibles
    top_words    = canal_data.get("top_words", [])
    top_hashtags = canal_data.get("top_hashtags", [])
    top_perfs    = canal_data.get("top_performers", [])
    avg_views    = canal_data.get("avg_views", 0)
    samples      = canal_data.get("learning_samples", 0)
    
    # Top mots viraux pour ce canal
    top_word_strs = []
    for w in top_words[:6]:
        marker = " 🏆" if w.get("top_performer") else ""
        top_word_strs.append(f"{w['word']}{marker}")
    
    # Top hashtags
    top_hash_strs = [h["tag"] for h in top_hashtags[:6]]
    if not top_hash_strs:
        top_hash_strs = env_hashtags[:6]
    
    # Exemples de titres gagnants
    examples_str = ""
    if top_perfs:
        examples_str = "\n📊 TES MEILLEURES VIDÉOS RÉCENTES (IMITE CE STYLE) :\n"
        for tp in top_perfs[:3]:
            examples_str += f"   → \"{tp.get('title', '?')}\" ({int(tp.get('views', 0)):,} vues)\n"
    
    context = (
        f"{emotion_context}"
        f"\n🧠 DONNÉES LEARNT pour ce canal ({samples} vidéos analysées, avg {int(avg_views):,} vues) :\n"
        f"   🔥 Mots viraux qui fonctionnent : {', '.join(top_word_strs)}\n"
        f"   #️⃣ Hashtags performants : {' '.join(top_hash_strs)}\n"
        f"{examples_str}"
    )
    
    return context


# ─────────────────────────────────────────────────────────────────────────────────
# STATS (pour la commande Telegram /viral_brain)
# ─────────────────────────────────────────────────────────────────────────────────

def get_brain_stats() -> dict:
    """Retourne l'état actuel du brain pour tous les canaux."""
    return _load_brain()


def get_virality_score_for_clip(clip: dict) -> float:
    """
    Calcule un score de viralité pour un clip Twitch.
    Score = vues / ancienneté_en_heures
    → Favorise les clips qui buzzent maintenant.
    """
    views = clip.get("view_count", 0) or 0
    created_at_str = clip.get("created_at", "")
    
    if not created_at_str:
        return float(views)
    
    try:
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        now = datetime.now(created_at.tzinfo)
        age_hours = max(1.0, (now - created_at).total_seconds() / 3600)
        return views / age_hours
    except Exception:
        return float(views)
