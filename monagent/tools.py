"""Outils exécutés par le modèle (liste, lecture, écriture, édition, recherche, shell).

La logique est inchangée : seuls les affichages passent désormais par ui.py
(journal ● des appels, diff coloré, troncature) et la confirmation propose
[y] oui / [n] non / [a] toujours-oui pour la session (toggle /yes).
"""
import subprocess
from pathlib import Path

from . import ui

ROOT = Path.cwd().resolve()  # l'agent reste dans le dossier où il est lancé
IGNORED = {".git", ".venv", "node_modules", "__pycache__"}

_auto_yes = False


def set_auto(on: bool) -> None:
    """Mode auto-confirmation : plus aucune question y/n/a n'est posée."""
    global _auto_yes
    _auto_yes = bool(on)


def get_auto() -> bool:
    return _auto_yes


def _safe(path: str) -> Path:
    p = (ROOT / path).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise ValueError("Chemin en dehors du projet")
    return p


def _confirm(question: str) -> bool:
    if _auto_yes:
        return True
    rep = ui.ask_confirm(question)
    if rep == "a":
        set_auto(True)
        return True
    return rep == "y"


def list_dir(path: str = ".") -> str:
    """Liste les fichiers et dossiers d'un répertoire du projet."""
    ui.tool_call("list_dir", str(path))
    try:
        p = _safe(path)
        items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        out = "\n".join(f"{i.name}{'/' if i.is_dir() else ''}" for i in items)
        ui.tool_result(out)
        return out
    except Exception as e:
        return f"Erreur : {e}"


def read_file(path: str) -> str:
    """Lit le contenu d'un fichier texte du projet."""
    ui.tool_call("read_file", str(path))
    try:
        out = _safe(path).read_text(encoding="utf-8")[:50_000]
        ui.tool_result(out)
        return out
    except Exception as e:
        return f"Erreur : {e}"


def write_file(path: str, content: str) -> str:
    """Crée ou remplace entièrement un fichier avec le contenu donné."""
    ui.tool_call("write_file", str(path))
    try:
        p = _safe(path)
        old = p.read_text(encoding="utf-8") if p.exists() else ""
        ui.show_diff(path, old, content)
        if not _confirm(f"Écrire {path} ?"):
            return "Refusé par l'utilisateur."
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        ui.success(f"{path} écrit.")
        return f"{path} écrit."
    except Exception as e:
        return f"Erreur : {e}"


def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Remplace une portion exacte de texte dans un fichier (old_text doit exister une seule fois)."""
    ui.tool_call("edit_file", str(path))
    try:
        p = _safe(path)
        content = p.read_text(encoding="utf-8")
        count = content.count(old_text)
        if count != 1:
            return f"Erreur : old_text trouvé {count} fois (doit être 1)."
        return write_file(path, content.replace(old_text, new_text))
    except Exception as e:
        return f"Erreur : {e}"


def search(pattern: str, path: str = ".") -> str:
    """Cherche un texte dans les fichiers du projet (comme grep)."""
    ui.tool_call("search", str(pattern))
    results = []
    try:
        for f in _safe(path).rglob("*"):
            if f.is_file() and not (set(f.parts) & IGNORED):
                try:
                    for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                        if pattern in line:
                            results.append(f"{f.relative_to(ROOT)}:{n}: {line.strip()}")
                except (UnicodeDecodeError, OSError):
                    continue
        out = "\n".join(results[:100]) or "Aucun résultat."
        ui.tool_result(out, max_lines=12)
        return out
    except Exception as e:
        return f"Erreur : {e}"


def run_shell(command: str) -> str:
    """Exécute une commande shell (PowerShell/cmd sous Windows) dans le dossier du projet et retourne la sortie."""
    ui.tool_call("run_shell", str(command))
    if not _confirm(f"Exécuter `{command}` ?"):
        return "Refusé par l'utilisateur."
    try:
        r = subprocess.run(command, shell=True, cwd=ROOT, capture_output=True, text=True, timeout=60)
        out = (r.stdout + r.stderr)[-10_000:] or "(aucune sortie)"
        ui.tool_result(out)
        return out
    except subprocess.TimeoutExpired:
        return "Erreur : timeout (60 s)."


# La boucle d'appel d'outils du SDK exécute ces fonctions automatiquement.
ALL_TOOLS = [list_dir, read_file, write_file, edit_file, search, run_shell]
