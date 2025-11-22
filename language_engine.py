# language_engine.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")

# Supported DeepL language codes
SUPPORTED_LANGUAGES = {"fr", "de", "es", "zh"}

def translate(text, target_lang):
    if target_lang not in SUPPORTED_LANGUAGES:
        return text  # No translation needed

    url = "https://api-free.deepl.com/v2/translate"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "auth_key": DEEPL_API_KEY,
        "text": text,
        "target_lang": target_lang.upper()
    }

    try:
        response = requests.post(url, data=data, headers=headers)
        result = response.json()
        return result["translations"][0]["text"]
    except Exception as e:
        print(f"Translation error: {e}")
        return text  # Fallback to original
