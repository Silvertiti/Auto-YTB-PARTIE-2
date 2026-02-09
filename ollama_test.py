from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()

# Ta clé API
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# === LES DONNÉES D'ENTRÉE (C'est ça que ton script principal enverra) ===
streamer_name = "Anyme"
titre_clip_twitch = "Gros fail sur une question de géographie facile" 
# ========================================================================

# Le prompt système optimisé pour JUSTE le Titre et les Hashtags
system_instruction = """
Tu es un expert en viralité pour TikTok et YouTube Shorts.
Ton but est de générer les métadonnées pour un clip vidéo.

INSTRUCTIONS :
1. Analyse le NOM DU STREAMER et le TITRE DU CLIP fournis.
2. Génère un TITRE CLICKBAIT (Court, mots-clés en MAJUSCULES, 2-3 emojis).
3. Génère une liste de HASHTAGS. Tu dois mélanger des hashtags génériques (comme #TwitchFR #BestOfTwitch) ET des hashtags précis liés au sujet du clip (ex: le nom du jeu, le thème "CultureG", "Minecraft", etc.).

FORMAT DE RÉPONSE STRICT (2 lignes maximum, pas de guillemets, pas de préfixe "Titre:") :
[LIGNE 1 : TON TITRE ICI]
[LIGNE 2 : TES HASHTAGS ICI]
"""

try:
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile", 
        messages=[
            {
                "role": "system", 
                "content": system_instruction
            },
            {
                "role": "user", 
                # On injecte dynamiquement le contexte ici
                "content": f"Streamer: {streamer_name}\nTitre du clip: {titre_clip_twitch}"
            }
        ],
        temperature=0.7,
        max_tokens=200, # Pas besoin de plus pour 2 lignes
        top_p=1,
        stream=True,
        stop=None
    )

    print(f"\n--- Résultat pour le clip : '{titre_clip_twitch}' ---\n")
    
    # Récupération et affichage propre
    full_response = ""
    for chunk in completion:
        text_chunk = chunk.choices[0].delta.content or ""
        print(text_chunk, end="")
        full_response += text_chunk
    print("\n")

except Exception as e:
    print(f"Erreur API : {e}")