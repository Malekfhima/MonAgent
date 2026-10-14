"""Interface du CLI : thème violet/cyan avec rich et prompt_toolkit.

Tout l'affichage utilisateur est centralisé ici, pour que cli.py reste
focalisé sur la boucle et que tools.py ne s'occupe que de la logique.
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
from rich.box import HEAVY, ROUNDED
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

VERSION = "0.2.0"
VIOLET = "#A855F7"
CYAN = "#22D3EE"

console = Console()

# Rend le terminal UTF-8 sous Windows PowerShell (accents, symboles ◆ ● ❯)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass

LOGO = r"""
███╗   ███╗ ██████╗ ███╗   ██╗  █████╗  ██████╗ ███████╗ ███╗   ██╗ ████████╗
████╗ ████║██╔════╝ ████╗  ██║ ██╔══██╗██╔════╝ ██╔════╝ ████╗  ██║ ╚══██╔══╝
██╔████╔██║██║  ███╗██╔██╗ ██║ ███████║██║  ███╗█████╗   ██╔██╗ ██║    ██║
██║╚██╔╝██║██║   ██║██║╚██╗██║ ██╔══██║██║   ██║██╔══╝   ██║╚██╗██║    ██║
██║ ╚═╝ ██║╚██████╔╝██║ ╚████║ ██║  ██║╚██████╔╝███████╗ ██║ ╚████║    ██║
╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝ ╚═╝  ╚═══╝    ╚═╝
""".strip("\n")


# --- bannière ---------------------------------------------------------------

def _gradient(lines: list[str]) -> Text:
    """Colorie le logo en dégradé violet → cyan, colonne par colonne."""
    width = max(len(line) for line in lines)
    start = (168, 85, 247)  # violet
    end = (34, 211, 238)  # cyan
    text = Text()
    for line in lines:
        for col, ch in enumerate(line):
            t = col / max(width - 1, 1)
            r, g, b = (round(s + (e - s) * t) for s, e in zip(start, end))
            text.append(ch, style=f"#{r:02X}{g:02X}{b:02X}")
        text.append("\n")
    return text


def banner(model: str, root: Path) -> None:
    """Affiche le logo, les infos de session et deux astuces de démarrage."""
    console.clear()
    console.print()
    console.print(_gradient(LOGO.splitlines()))
    infos = Table(show_header=False, box=None, padding=(0, 2))
    infos.add_row("[bold]Modèle  [/]", f"[magenta]{model}[/]")
    infos.add_row("[bold]Dossier [/]", str(root))
    infos.add_row("[bold]Version [/]", VERSION)
    console.print(infos)
    console.print(Text("Astuce : /help pour les commandes · /clear pour repartir de zéro · /exit pour quitter", style="dim"))
    console.print(Rule(style=VIOLET))
    console.print()


# --- affichage général ------------------------------------------------------

def info(msg: str) -> None:
    console.print(f"[bold magenta]◆[/] {msg}")


def success(msg: str) -> None:
    console.print(f"[bold cyan]✔[/] {msg}")


def warn(msg: str) -> None:
    console.print(f"[bold yellow]⚠[/] {msg}")


def error_panel(title: str, body: str) -> None:
    """Erreur dans un panneau rouge lisible."""
    console.print(Panel(Text(str(body)), title=f"[bold red]{title}[/]", border_style="red", box=HEAVY))


def render_markdown(text: str) -> None:
    """Réponse du modèle dans un panneau Markdown (coloration du code incluse)."""
    console.print(Panel(Markdown(text or "(réponse vide)"), border_style=VIOLET, box=ROUNDED, padding=(1, 2)))


def stream_markdown(chunks, model: str) -> tuple[str, int]:
    """Affiche la réponse en streaming : spinner puis Markdown progressif.

    Retourne (texte complet, tokens). Les exceptions remontent à cli.py.
    """
    buf: list[str] = []
    usage = None
    live: Live | None = None
    status = console.status(" Réflexion…", spinner="dots", spinner_style=VIOLET)
    status.start()
    try:
        for chunk in chunks:
            if getattr(chunk, "usage_metadata", None) is not None:
                usage = chunk.usage_metadata
            for cand in (getattr(chunk, "candidates", None) or []):
                for part in (getattr(getattr(cand, "content", None), "parts", None) or []):
                    piece = getattr(part, "text", None)
                    if not piece:
                        continue
                    if live is None:
                        status.stop()
                        live = Live(console=console, refresh_per_second=12)
                        live.start()
                    buf.append(piece)
                    live.update(Panel(Markdown("".join(buf)), border_style=VIOLET, box=ROUNDED, padding=(1, 2), title=f"[bold magenta]◆ {model}[/]"), refresh=True)
    finally:
        status.stop()
        if live is not None:
            live.stop()
    if not buf:
        return "", int(getattr(usage, "total_token_count", 0) or 0)
    console.print()
    return "".join(buf), int(getattr(usage, "total_token_count", 0) or 0)


# --- affichage des outils ---------------------------------------------------

_TOOL_COLORS = {
    "list_dir": "cyan",
    "read_file": "cyan",
    "search": "cyan",
    "write_file": "yellow",
    "edit_file": "yellow",
    "run_shell": "red",
}


def tool_call(name: str, arg: str = "") -> None:
    """« ● read_file  src/app.py » avec une couleur par famille d'outil."""
    color = _TOOL_COLORS.get(name, VIOLET)
    console.print(Text.assemble((f"● {name}", f"bold {color}"), ("  " + arg, "dim")))


def tool_result(text: str, max_lines: int = 8) -> None:
    """Affiche un résultat court, élagué au-delà de `max_lines` lignes."""
    lines = (text or "").rstrip().splitlines()
    shown, extra = lines[:max_lines], len(lines) - max_lines
    out = Text("   ", style="dim")
    out.append("\n   ".join(shown) if shown else "(aucune sortie)")
    if extra > 0:
        out.append(f"\n   … ({extra} lignes de plus)", style="cyan italic")
    console.print(out, style="dim")


def show_diff(path: str, old: str, new: str) -> bool:
    """Diff coloré (vert/rouge) avec numéros de ligne. True si une écriture est proposée."""
    import difflib

    hunks = list(difflib.unified_diff(old.splitlines(), new.splitlines(), fromfile=path, tofile=path, lineterm=""))
    if not hunks:
        return False
    console.print(Text.assemble(("  diff ", "bold"), (path, "bold yellow")))
    old_no = new_no = 0
    text = Text("\n")
    for line in hunks[2:]:
        if line.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            old_no, new_no = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
            text.append(f"{line}\n", style="bold cyan")
        elif line.startswith("+"):
            text.append(f"{new_no:>5} │ ", style="dim")
            text.append(f"{line}\n", style="green")
            new_no += 1
        elif line.startswith("-"):
            text.append(f"{old_no:>5} │ ", style="dim")
            text.append(f"{line}\n", style="red")
            old_no += 1
        else:
            text.append(f"{old_no:>5} │ ", style="bright_black")
            text.append(f"{line}\n", style="bright_black")
            old_no += 1
            new_no += 1
    console.print(text)
    return True


def ask_confirm(question: str) -> str:
    """Confirmation 3 choix : 'y' oui, 'n' non, 'a' toujours (pour la session)."""
    while True:
        try:
            rep = console.input(
                f"[bold yellow]❔ {question}[/] [yellow]\\[y][/]=[bold]oui[/] · [dim]\\[n]non[/] · [cyan]\\[a]toujours[/] : "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "n"
        if rep in ("y", "o", "oui"):
            return "y"
        if rep in ("a", "always", "toujours"):
            return "a"
        if rep in ("n", "non", "no", ""):
            return "n"


# --- commandes slash --------------------------------------------------------

def help_table() -> None:
    table = Table(title="Commandes", title_style=VIOLET, box=ROUNDED, header_style="bold", padding=(0, 2))
    table.add_column("Commande", style=f"bold {VIOLET}")
    table.add_column("Description")
    rows = [("/help", "affiche ce tableau"), ("/model [nom]", "affiche ou change de modèle"),
            ("/yes", "active/désactive l'auto-confirmation (y/n/a)"), ("/clear", "réinitialise la conversation"),
            ("/exit", "quitte le programme")]
    for cmd, desc in rows:
        table.add_row(cmd, desc)
    console.print(table)


# --- barre d'état (prompt_toolkit) -------------------------------------------

PROMPT_FRAGMENT = FormattedText([("class:prompt", " ❯ ")])

PTK_STYLE = Style.from_dict({
    "prompt": "#A855F7 bold",
    "vio": "bg:#A855F7 #14001f bold",
    "cyan": "#22D3EE bold",
    "sep": "#666",
    "ok": "#22D3EE",
    "dim": "#777",
})


def status_toolbar(model: str, root: Path, auto: bool, tokens):
    """Fragments de la barre d'état basse (modèle, dossier, mode, tokens)."""
    tok = f"{tokens} tokens" if tokens else "—"
    return [
        ("class:vio", f" {model} "),
        ("class:sep", " │ "),
        ("class:cyan", f" {root.name or root} "),
        ("class:sep", " │ "),
        ("class:ok" if auto else "class:warn", f" {'auto-oui' if auto else 'confirm'} "),
        ("class:sep", " │ "),
        ("class:dim", f" {tok} "),
    ]
