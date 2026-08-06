import requests, sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from dotenv import dotenv_values
env = dotenv_values(".env")
API_KEY = env.get("GEMINI_API_KEY", "")

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
resp = requests.get(url, timeout=30)
data = resp.json()

print("Modeles disponibles :")
for m in data.get("models", []):
    name = m.get("name", "")
    methods = m.get("supportedGenerationMethods", [])
    if "generateContent" in methods or "predict" in methods:
        print(f"  {name}  ->  {methods}")
