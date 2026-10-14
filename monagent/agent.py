import os
import platform
from google import genai
from google.genai import types
from .tools import ALL_TOOLS, ROOT

MODEL = os.environ.get("MONAGENT_MODEL", "gemini-flash-lite-latest")  # alias = toujours la dernière version flash-lite du moment

SYSTEM_PROMPT = f"""Tu es un agent de code qui tourne dans le terminal de l'utilisateur.
Système : {platform.system()} (les commandes shell s'exécutent via cmd/PowerShell si Windows).
Dossier du projet : {ROOT}
Règles :
- Explore le projet (list_dir, search, read_file) avant de modifier quoi que ce soit.
- Préfère edit_file à write_file pour les petites modifications.
- Après une modification, vérifie avec run_shell (tests, lint) si c'est pertinent.
- Utilise des commandes adaptées au système de l'utilisateur.
- Réponds de façon courte et claire, dans la langue de l'utilisateur."""

def _user_env_key_windows():
    """Lit GEMINI_API_KEY dans la variable persistante Windows (HKCU\\Environment)
    si elle n'a pas été héritée par la session courante."""
    if platform.system() != "Windows":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            val, _ = winreg.QueryValueEx(k, "GEMINI_API_KEY")
            return val or None
    except OSError:
        return None


_client = None  # client global : il doit rester référencé pour ne pas être fermé


def _get_client():
    global _client
    if _client is None:
        key = os.environ.get("GEMINI_API_KEY") or _user_env_key_windows()
        if not key:
            raise SystemExit("Variable GEMINI_API_KEY manquante.")
        _client = genai.Client(api_key=key)
    return _client


def create_chat():
    return _get_client().chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=ALL_TOOLS,  # le SDK exécute les outils automatiquement en boucle
        ),
    )