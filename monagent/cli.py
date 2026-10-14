"""Boucle du terminal : saisie prompt_toolkit, commandes slash, appels Gemini."""
from __future__ import annotations

import re
import time
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings

from google.genai import errors as genai_errors

from . import agent, tools, ui

MAX_RETRIES = 5
RETRY_CODES = (429, 500, 502, 503)  # codes réessayables côté Google

TOKENS = {"total": 0}  # tokens cumulés de la session (affichés dans la barre)

COMMANDS = {
    "/help": "affiche les commandes",
    "/model": "affiche ou change de modèle (/model <nom>)",
    "/yes": "active/désactive l'auto-confirmation",
    "/clear": "réinitialise la conversation",
    "/exit": "quitte",
}

# --- saisie prompt_toolkit ---------------------------------------------------

_COMPLETER = WordCompleter(list(COMMANDS), meta_dict=COMMANDS, sentence=True, ignore_case=False)

_KB = KeyBindings()


@_KB.add("enter")
def _(event):  # Entrée envoie la ligne (même en mode multiligne)
    event.current_buffer.validate_and_handle()


@_KB.add("escape", "enter")  # Alt+Entrée : passage à la ligne
def _(event):
    event.current_buffer.insert_text("\n")


def _history_path() -> Path:
    path = Path.home() / ".monagent" / "history"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _make_session() -> PromptSession:
    return PromptSession(
        history=FileHistory(str(_history_path())),
        completer=_COMPLETER,
        complete_while_typing=True,
        multiline=True,
        key_bindings=_KB,
        style=ui.PTK_STYLE,
    )


# --- appels API --------------------------------------------------------------

def _api_call(chat, prompt: str) -> tuple[str, int]:
    """Un appel : streaming si possible, sinon flux classique.

    Retourne (texte, tokens de la réponse). Si le SDK refuse le streaming
    (cas possible pendant l'appel d'outils), on bascule en non-streamé.
    """
    try:
        return ui.stream_markdown(chat.send_message_stream(prompt), agent.MODEL)
    except genai_errors.APIError:
        raise  # les erreurs API suivent la logique de réessai habituelle
    except Exception as e:
        msg = str(e).lower()
        if "stream" in msg or "function" in msg or "automatic" in msg:
            resp = chat.send_message(prompt)
            tokens = getattr(resp.usage_metadata, "total_token_count", 0) or 0
            ui.render_markdown(resp.text or "(réponse vide)")
            print()
            return resp.text or "", int(tokens)
        raise


def _error_code(e: Exception) -> int:
    code = getattr(e, "code", None)
    if code:
        return int(code)
    m = re.search(r"\b(4\d\d|5\d\d)\b", str(e))
    return int(m.group(1)) if m else 0


def _countdown(code: int, wait: int, attempt: int) -> None:
    """Compte à rebours avant un nouvel essai (503/429)."""
    ui.warn(f"API indisponible ({code}), nouvel essai dans {wait}s ({attempt}/{MAX_RETRIES - 1})…")
    for remaining in range(wait, 0, -1):
        print(f"\r  nouvel essai dans {remaining:>2}s ", end="", flush=True)
        time.sleep(1)
    print("\r" + " " * 30, end="\r")


def respond(chat, prompt: str) -> tuple[str, int]:
    """Envoie le prompt avec réessais (429/503). Retourne (texte, tokens) ou (None, 0)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = _api_call(chat, prompt)
            return result
        except genai_errors.APIError as e:
            code = _error_code(e)
            if code in RETRY_CODES and attempt < MAX_RETRIES:
                _countdown(code, 2 ** attempt, attempt)
            else:
                ui.error_panel("Erreur API", str(e))
                return None, 0
        except Exception as e:  # erreur non-HTTP : on l'affiche sans réessayer
            ui.error_panel("Erreur", str(e))
            return None, 0
    return None, 0


# --- commandes slash ---------------------------------------------------------

def _cmd_model(arg: str) -> None:
    if not arg:
        ui.info(f"Modèle actuel : [magenta]{agent.MODEL}[/] — usage : /model <nom>")
        return
    try:  # on valide le nom auprès de l'API avant de l'adopter
        agent._get_client().models.get(model=arg)
    except Exception as e:
        ui.error_panel("Modèle invalide", f"{arg} → {e}")
        return
    agent.MODEL = arg
    ui.success(f"Nouveau modèle : {agent.MODEL}")


def handle_command(line: str) -> str | None:
    """Traite une commande slash. Retourne 'exit', 'clear' ou None."""
    parts = line.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip().split()[0] if len(parts) > 1 and parts[1].strip() else ""
    if cmd == "/exit":
        return "exit"
    if cmd == "/clear":
        return "clear"
    if cmd == "/help":
        ui.help_table()
    elif cmd == "/yes":
        auto = not tools.get_auto()
        tools.set_auto(auto)
        ui.success(f"Auto-confirmation {'activée' if auto else 'désactivée'}.")
    elif cmd == "/model":
        _cmd_model(arg)
    else:
        ui.warn(f"Commande inconnue : {cmd} — tape /help.")
    return None


# --- boucle principale -------------------------------------------------------

def main() -> None:
    session = _make_session()
    ui.banner(agent.MODEL, Path.cwd())

    chat = None
    while True:
        toolbar = lambda: ui.status_toolbar(agent.MODEL, Path.cwd(), tools.get_auto(), TOKENS["total"])  # noqa: E731
        try:
            prompt = session.prompt(message=ui.PROMPT_FRAGMENT, bottom_toolbar=toolbar).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not prompt:
            continue
        try:
            if prompt.startswith("/"):
                action = handle_command(prompt)
                if action == "exit":
                    break
                if action == "clear":
                    chat = agent.create_chat()
                    ui.info("Conversation réinitialisée.")
                continue

            if chat is None:  # création paresseuse : la clé ne peut pas manquer
                chat = agent.create_chat()
            text, tokens = respond(chat, prompt)
            if text is not None:
                TOKENS["total"] += tokens
        except (KeyboardInterrupt, EOFError):  # Ctrl+C pendant un appel/outil
            ui.warn("Interrompu.")
        except SystemExit as e:  # clé API manquante (message de agent.py)
            ui.error_panel("Clé API", str(e))
            continue


if __name__ == "__main__":
    main()
