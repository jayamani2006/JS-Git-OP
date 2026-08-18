# GitForge Studio

**"Git Bash, rebuilt as a developer cockpit."**

GitForge Studio is a visual command center that sits *on top of* your real,
already-installed Git and Git Bash. It does not replace Git. It does not
store your GitHub password. It always shows you the exact `git` command it
is about to run, before it runs it.

This is the **V1** build: a fully working desktop app in a single Python
file, launched with `run.bat`, exactly like the rest of your JS SoftTools
lineup (PyInstaller/Inno-Setup-ready).

## Run it

```
run.bat
```

The script checks for Python and Git, then launches `gitforge_studio.py`.
No pip installs are required — V1 uses only the Python standard library
(`tkinter`, `subprocess`, `pathlib`).

Requires:
- Python 3.8+ with tkinter (default on python.org Windows installers)
- Git for Windows (`git.exe` on PATH)

## What V1 includes

- **Dashboard** — open repositories at a glance, one click to jump to any of them
- **Open Folder / Clone / Create Repository** wizards
- **Per-repo tabs**, each with:
  - live `git status` (branch, ahead/behind, changed file count)
  - Changes panel — stage/discard/diff selected files, stage all
  - Branches panel — checkout, merge into current, delete
  - Stash panel — pop / apply / drop
  - Commit history panel
  - One-click Fetch / Pull / Push / **Sync** (fetch → pull --rebase → push)
- **Command Palette** (`Ctrl+K`) — search the real Git command catalog
  (built from the official [Git cheat sheet](https://git-scm.com/cheat-sheet)),
  fill in the blanks, see the command, run it
- **Transparent terminal/activity log** — every command GitForge runs is
  echoed here with its real `git ...` invocation, output, and duration
- **Safety layer** — destructive commands (`reset --hard`, `push --force`,
  `clean -f`, `branch -D`, discarding all local edits) always require an
  explicit confirmation that explains the risk in plain language
- **Git Doctor** — checks Git install, version, global `user.name` /
  `user.email`, and optional GitHub CLI presence

See `DEEP_ANALYSIS.md` for the full product analysis: how this compares to
Git Bash / GitHub Desktop / GitKraken / VS Code's Git support, why the
underlying-engine architecture matters, the V2/V3 roadmap, and the risks.

## Design rule that drives everything

> Never hide Git. Every button GitForge shows you maps to a real,
> visible `git` command — so beginners get the button, and experienced
> developers keep their trust (and their muscle memory).

## Project layout

```
GitForgeStudio/
├── gitforge_studio.py   ← the whole app (single file, stdlib only)
├── run.bat               ← launcher / environment checker
├── requirements.txt
├── README.md
└── DEEP_ANALYSIS.md      ← product & market analysis
```
