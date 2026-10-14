# MonAgent — agent de code dans le terminal (Gemini)

MonAgent est un assistant de code en ligne de commande, inspiré de Claude Code / Gemini CLI :
tu discutes dans le terminal, l'agent explore ton projet, lit/écrit des fichiers, lance des
commandes shell — avec affichage coloré, Markdown, streaming et confirmations avant toute écriture.

## Fonctionnalités

- 🔎 **Outils** : `list_dir`, `read_file`, `search`, `write_file`, `edit_file`, `run_shell`
- 🎨 **Interface riche** (rich + prompt_toolkit) : logo dégradé, Markdown, diff colorés,
  spinner pendant la réflexion, barre d'état (modèle · dossier · mode · tokens)
- ⌨️ **Saisie confortable** : historique persistant (`~/.monagent/history`), autocomplétion
  des commandes, multiligne (Alt+Entrée)
- 🔒 **Sécurité** : confirmation `y/n/a` avant écriture ou commande shell, mode auto `/yes`
- 🔁 **Résilience** : réessais automatiques avec compte à rebours sur 429/503, clé API lue
  dans l'environnement ou dans les variables utilisateur Windows

## Installation

```powershell
git clone https://github.com/<ton-compte>/monagent.git
cd monagent
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS : source .venv/bin/activate
pip install -e .
```

Configure ta clé API Gemini (gratuite sur [aistudio.google.com/apikey](https://aistudio.google.com/apikey)) :

```powershell
[Environment]::SetEnvironmentVariable('GEMINI_API_KEY', 'TA_CLE', 'User')  # persistant Windows
# Linux/macOS : export GEMINI_API_KEY="TA_CLE"  (dans ~/.bashrc par ex.)
```

## Utilisation

```powershell
cd <ton-projet>      # l'agent opère dans le dossier courant
monagent
```

| Commande   | Effet                                                    |
|------------|----------------------------------------------------------|
| `/help`    | liste des commandes                                      |
| `/model`   | affiche ou change de modèle (`/model gemini-3.5-flash`)  |
| `/yes`     | active/désactive l'auto-confirmation (y/n/a)             |
| `/clear`   | réinitialise la conversation                             |
| `/exit`    | quitte                                                   |

Le modèle se change aussi au démarrage : `$env:MONAGENT_MODEL = "..."` (défaut : `gemini-flash-lite-latest`).

## Architecture

```
monagent/
├── monagent/
│   ├── ui.py       # interface : thème, bannière, markdown, diffs, confirmations, barre d'état
│   ├── cli.py      # boucle du terminal : saisie, commandes slash, streaming, réessais
│   ├── agent.py    # connexion Gemini (client global, prompt système, chat)
│   └── tools.py    # outils exécutés par le modèle (sandbox, y/n/a)
└── pyproject.toml
```

## Sécurité

La clé API reste dans ton environnement — jamais dans le code. Les écritures de fichiers et
commandes shell demandent toujours une confirmation sauf si tu as choisi `a` ou `/yes`.
