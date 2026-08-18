#!/usr/bin/env python3
"""
GitForge Studio  —  "Git Bash, rebuilt as a developer cockpit."

A visual command center that sits ON TOP of your real, already-installed
Git / Git Bash. It never replaces Git, never stores your GitHub password,
and always shows you the exact git command it is about to run before it
runs it.

Architecture (see DEEP_ANALYSIS.md for the full writeup):

    Tkinter UI  --calls-->  GitEngine (subprocess wrapper around git.exe)
                                  |
                            every call is logged to the on-screen
                            Terminal pane AND to command_history

Single-file by design so the whole cockpit can be launched with one
`python gitforge_studio.py` / run.bat, no build step, no bundler.

Requires: Python 3.8+, Git for Windows (git.exe on PATH). Nothing else.
"""

import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

APP_NAME = "GitForge Studio"
APP_VERSION = "1.0.0 (V1)"
CONFIG_DIR = Path.home() / ".gitforge_studio"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "command_history.json"

DESTRUCTIVE_MARKERS = [
    ("reset --hard", "This can permanently discard uncommitted changes in your working tree."),
    ("push --force", "This can overwrite/rewrite the remote branch's history for everyone."),
    ("push -f", "This can overwrite/rewrite the remote branch's history for everyone."),
    ("clean -f", "This permanently deletes untracked files. There is no undo."),
    ("branch -D", "This force-deletes a branch even if it has unmerged work."),
    ("checkout -- .", "This discards ALL local edits in the working tree."),
    ("restore .", "This discards ALL local edits in the working tree."),
]

# A compact version of the official Git cheat sheet (git-scm.com/cheat-sheet),
# used to power the Command Palette / "Explain This Command" features.
COMMAND_CATALOG = [
    ("Getting Started", "git init", "Create a new local repository in the current folder."),
    ("Getting Started", "git clone <url>", "Clone a repository into a new directory."),
    ("Getting Started", "git config --global user.name \"<name>\"", "Set the name used for your commits."),
    ("Getting Started", "git config --global user.email \"<email>\"", "Set the email used for your commits."),
    ("Changes", "git status", "Show modified/staged/untracked files."),
    ("Changes", "git add <file>", "Stage a file's changes for the next commit."),
    ("Changes", "git add .", "Stage every changed file in the working tree."),
    ("Changes", "git add -p", "Interactively choose which hunks/lines to stage."),
    ("Changes", "git restore <file>", "Discard unstaged changes to a file."),
    ("Changes", "git restore --staged <file>", "Unstage a file (keep the edits)."),
    ("Changes", "git commit -m \"<message>\"", "Record staged changes as a new commit."),
    ("Changes", "git commit --amend", "Edit the most recent commit instead of creating a new one."),
    ("Branches", "git branch", "List local branches."),
    ("Branches", "git switch -c <name>", "Create and switch to a new branch."),
    ("Branches", "git switch <name>", "Switch to an existing branch."),
    ("Branches", "git merge <branch>", "Merge another branch into the current branch."),
    ("Branches", "git branch -d <name>", "Delete a branch that has been merged."),
    ("Branches", "git branch -D <name>", "Force-delete a branch, merged or not. (Destructive)"),
    ("History", "git log --oneline --graph --all", "Show a compact, graphical commit history."),
    ("History", "git show <sha>", "Show the details/diff of one commit."),
    ("History", "git diff", "Show unstaged changes vs the last commit."),
    ("History", "git diff --staged", "Show staged changes vs the last commit."),
    ("History", "git blame <file>", "Show who last changed each line of a file."),
    ("Stash", "git stash", "Temporarily shelve uncommitted changes."),
    ("Stash", "git stash list", "List all stashes."),
    ("Stash", "git stash pop", "Re-apply and remove the most recent stash."),
    ("Merge/Rebase", "git rebase <branch>", "Replay current branch's commits on top of another branch."),
    ("Merge/Rebase", "git rebase -i HEAD~<n>", "Interactively edit/squash the last n commits."),
    ("Remote", "git remote -v", "List configured remotes and their URLs."),
    ("Remote", "git fetch", "Download remote history without merging it."),
    ("Remote", "git pull", "Fetch and merge (or rebase) the remote branch."),
    ("Remote", "git pull --rebase", "Fetch and rebase local commits on top of remote."),
    ("Remote", "git push", "Upload local commits to the remote branch."),
    ("Remote", "git push --force-with-lease", "Force-push, but abort if remote has new commits you haven't seen. (Safer force)"),
    ("Undo", "git reset HEAD^", "Undo the last commit, keep the changes in your working tree."),
    ("Undo", "git reset --hard HEAD~1", "Undo the last commit AND discard the changes. (Destructive)"),
    ("Undo", "git revert <sha>", "Create a new commit that undoes a previous commit (safe for shared history)."),
]


def is_destructive(cmd_str: str):
    for marker, warning in DESTRUCTIVE_MARKERS:
        if marker in cmd_str:
            return warning
    return None


# --------------------------------------------------------------------------
# Git engine — the only place that ever touches subprocess.
# --------------------------------------------------------------------------

@dataclass
class GitResult:
    cmd: list
    cwd: str
    returncode: int
    stdout: str
    stderr: str
    duration: float


class GitEngine:
    """Thin, transparent wrapper around the real git executable."""

    def __init__(self, on_log=None):
        self.git_path = shutil.which("git")
        self.on_log = on_log  # callback(cmd_str, output_str, ok:bool)
        self.history = []

    def available(self):
        return self.git_path is not None

    def version(self):
        if not self.available():
            return None
        r = self.run(["--version"], cwd=str(Path.home()), log=False)
        return r.stdout.strip() if r.returncode == 0 else None

    def run(self, args, cwd, log=True, timeout=120):
        cmd = [self.git_path or "git"] + args
        cmd_str = "git " + " ".join(args)
        start = time.time()
        try:
            proc = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
            )
            out, err, rc = proc.stdout, proc.stderr, proc.returncode
        except FileNotFoundError:
            out, err, rc = "", "git executable not found on PATH.", 127
        except subprocess.TimeoutExpired:
            out, err, rc = "", f"Command timed out after {timeout}s.", 124
        duration = time.time() - start
        result = GitResult(cmd, cwd, rc, out, err, duration)
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "cmd": cmd_str,
            "cwd": cwd,
            "ok": rc == 0,
            "duration": round(duration, 2),
        }
        self.history.append(entry)
        if log and self.on_log:
            combined = (out or "") + (("\n" + err) if err else "")
            self.on_log(cmd_str, combined.strip(), rc == 0, duration)
        return result

    # ---- convenience wrappers -------------------------------------------------

    def is_repo(self, path):
        r = self.run(["rev-parse", "--is-inside-work-tree"], cwd=path, log=False)
        return r.returncode == 0

    def status_porcelain(self, path):
        r = self.run(["status", "--porcelain=v1", "-b"], cwd=path, log=False)
        return r.stdout.splitlines() if r.returncode == 0 else []

    def current_branch(self, path):
        r = self.run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=path, log=False)
        return r.stdout.strip() if r.returncode == 0 else "?"

    def branches(self, path):
        r = self.run(["branch", "--format=%(refname:short)"], cwd=path, log=False)
        return [b for b in r.stdout.splitlines() if b.strip()] if r.returncode == 0 else []

    def remote_branches(self, path):
        r = self.run(["branch", "-r", "--format=%(refname:short)"], cwd=path, log=False)
        return [b for b in r.stdout.splitlines() if b.strip() and "HEAD" not in b] if r.returncode == 0 else []

    def log(self, path, n=25):
        fmt = "%h\x1f%an\x1f%ar\x1f%s"
        r = self.run(["log", f"-n{n}", f"--pretty=format:{fmt}"], cwd=path, log=False)
        commits = []
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                parts = line.split("\x1f")
                if len(parts) == 4:
                    commits.append(dict(zip(["sha", "author", "when", "subject"], parts)))
        return commits

    def stashes(self, path):
        r = self.run(["stash", "list"], cwd=path, log=False)
        return r.stdout.splitlines() if r.returncode == 0 else []

    def ahead_behind(self, path):
        r = self.run(["rev-list", "--left-right", "--count", "HEAD...@{u}"], cwd=path, log=False)
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().split()
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
        return 0, 0

    def remotes(self, path):
        r = self.run(["remote", "-v"], cwd=path, log=False)
        return r.stdout.splitlines() if r.returncode == 0 else []

    def global_identity(self):
        name = self.run(["config", "--global", "user.name"], cwd=str(Path.home()), log=False).stdout.strip()
        email = self.run(["config", "--global", "user.email"], cwd=str(Path.home()), log=False).stdout.strip()
        return name, email


# --------------------------------------------------------------------------
# One tab per repository
# --------------------------------------------------------------------------

class RepoPanel(ttk.Frame):
    def __init__(self, master, app, path: str):
        super().__init__(master)
        self.app = app
        self.engine: GitEngine = app.engine
        self.path = path
        self._build_ui()
        self.refresh()

    # ---------------------------------------------------------------- UI ----

    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        self.header_var = tk.StringVar(value=self.path)
        ttk.Label(top, textvariable=self.header_var, font=("Segoe UI", 11, "bold")).pack(side="left")

        self.status_var = tk.StringVar(value="…")
        ttk.Label(top, textvariable=self.status_var, foreground="#0a7").pack(side="right")

        toolbar = ttk.Frame(self, padding=(8, 0))
        toolbar.pack(fill="x")
        actions = [
            ("⟳ Fetch", self.act_fetch),
            ("↓ Pull", self.act_pull),
            ("↑ Push", self.act_push),
            ("⇅ Sync", self.act_sync),
            ("＋ Stage All", self.act_stage_all),
            ("✎ Commit", self.act_commit),
            ("⎇ New Branch", self.act_new_branch),
            ("▤ Stash", self.act_stash),
        ]
        for label, cmd in actions:
            ttk.Button(toolbar, text=label, command=cmd).pack(side="left", padx=3, pady=4)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=4)

        # Left: changes
        left = ttk.Frame(body)
        ttk.Label(left, text="CHANGES", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.changes_list = tk.Listbox(left, height=10, selectmode="extended", activestyle="none")
        self.changes_list.pack(fill="both", expand=True, pady=(2, 6))
        cbtns = ttk.Frame(left)
        cbtns.pack(fill="x")
        ttk.Button(cbtns, text="Stage Selected", command=self.act_stage_selected).pack(side="left", padx=2)
        ttk.Button(cbtns, text="Discard Selected", command=self.act_discard_selected).pack(side="left", padx=2)
        ttk.Button(cbtns, text="Diff Selected", command=self.act_diff_selected).pack(side="left", padx=2)
        body.add(left, weight=2)

        # Middle: branches + stashes
        mid = ttk.Frame(body)
        ttk.Label(mid, text="BRANCHES", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.branch_list = tk.Listbox(mid, height=8, activestyle="none")
        self.branch_list.pack(fill="both", expand=True, pady=(2, 6))
        self.branch_list.bind("<Double-Button-1>", lambda e: self.act_checkout_selected_branch())
        bbtns = ttk.Frame(mid)
        bbtns.pack(fill="x")
        ttk.Button(bbtns, text="Checkout", command=self.act_checkout_selected_branch).pack(side="left", padx=2)
        ttk.Button(bbtns, text="Merge Into Current", command=self.act_merge_selected).pack(side="left", padx=2)
        ttk.Button(bbtns, text="Delete", command=self.act_delete_branch).pack(side="left", padx=2)

        ttk.Label(mid, text="STASHES", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 0))
        self.stash_list = tk.Listbox(mid, height=5, activestyle="none")
        self.stash_list.pack(fill="both", expand=True, pady=(2, 6))
        sbtns = ttk.Frame(mid)
        sbtns.pack(fill="x")
        ttk.Button(sbtns, text="Pop", command=self.act_stash_pop).pack(side="left", padx=2)
        ttk.Button(sbtns, text="Apply", command=self.act_stash_apply).pack(side="left", padx=2)
        ttk.Button(sbtns, text="Drop", command=self.act_stash_drop).pack(side="left", padx=2)
        body.add(mid, weight=2)

        # Right: log
        right = ttk.Frame(body)
        ttk.Label(right, text="COMMIT HISTORY", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.log_list = tk.Listbox(right, height=16, activestyle="none")
        self.log_list.pack(fill="both", expand=True, pady=(2, 6))
        ttk.Button(right, text="Refresh", command=self.refresh).pack(anchor="e")
        body.add(right, weight=3)

    # -------------------------------------------------------------- data ----

    def refresh(self):
        if not self.engine.is_repo(self.path):
            self.status_var.set("Not a git repository")
            return
        branch = self.engine.current_branch(self.path)
        ahead, behind = self.engine.ahead_behind(self.path)
        lines = self.engine.status_porcelain(self.path)
        changed = [l for l in lines if not l.startswith("##")]
        self.header_var.set(f"{Path(self.path).name}   ({self.path})")
        arrows = f"  ↑{ahead} ↓{behind}" if (ahead or behind) else ""
        self.status_var.set(f"● {branch}   {len(changed)} changed{arrows}")

        self.changes_list.delete(0, tk.END)
        self._change_lines = changed
        for l in changed:
            self.changes_list.insert(tk.END, l)

        self.branch_list.delete(0, tk.END)
        for b in self.engine.branches(self.path):
            prefix = "● " if b == branch else "○ "
            self.branch_list.insert(tk.END, prefix + b)

        self.stash_list.delete(0, tk.END)
        for s in self.engine.stashes(self.path):
            self.stash_list.insert(tk.END, s)

        self.log_list.delete(0, tk.END)
        for c in self.engine.log(self.path):
            self.log_list.insert(tk.END, f"{c['sha']}  {c['subject']}  — {c['author']}, {c['when']}")

        self.app.set_status(f"Refreshed {self.path}")

    def _selected_paths(self, widget, lines_source):
        out = []
        for i in widget.curselection():
            line = lines_source[i]
            # porcelain format: XY <path>  (path may be quoted, handle simple case)
            fname = line[3:].strip()
            if " -> " in fname:  # renames
                fname = fname.split(" -> ")[-1]
            out.append(fname)
        return out

    # ------------------------------------------------------------ actions ----

    def _confirm_and_run(self, args, note=None, refresh=True):
        cmd_str = "git " + " ".join(args)
        warning = is_destructive(cmd_str)
        if warning:
            ok = messagebox.askyesno(
                "⚠ Destructive Git Command",
                f"You are about to run:\n\n    {cmd_str}\n\n{warning}\n\nContinue?",
                icon="warning",
            )
            if not ok:
                return None
        elif self.app.confirm_before_run.get():
            proceed = messagebox.askokcancel("Confirm Git Command", f"About to run:\n\n    {cmd_str}\n\n{note or ''}")
            if not proceed:
                return None
        result = self.engine.run(args, cwd=self.path)
        if refresh:
            self.refresh()
        return result

    def act_fetch(self):
        self._confirm_and_run(["fetch", "--all"])

    def act_pull(self):
        self._confirm_and_run(["pull", "--rebase"])

    def act_push(self):
        self._confirm_and_run(["push"])

    def act_sync(self):
        # Fetch -> pull --rebase -> push, stop on first failure, always show each step
        for args in (["fetch", "--all"], ["pull", "--rebase"], ["push"]):
            r = self._confirm_and_run(args, refresh=False)
            if r is None or r.returncode != 0:
                self.refresh()
                messagebox.showwarning("Sync stopped", f"Sync stopped at: git {' '.join(args)}\nCheck the terminal log for details.")
                return
        self.refresh()
        self.app.set_status("Sync complete.")

    def act_stage_all(self):
        self._confirm_and_run(["add", "."], note="Stages every changed file for the next commit.")

    def act_stage_selected(self):
        paths = self._selected_paths(self.changes_list, self._change_lines)
        if not paths:
            messagebox.showinfo("Stage", "Select one or more files in CHANGES first.")
            return
        self._confirm_and_run(["add", "--"] + paths)

    def act_discard_selected(self):
        paths = self._selected_paths(self.changes_list, self._change_lines)
        if not paths:
            messagebox.showinfo("Discard", "Select one or more files in CHANGES first.")
            return
        self._confirm_and_run(["checkout", "--"] + paths, note="Discards local edits to these files. Cannot be undone.")

    def act_diff_selected(self):
        paths = self._selected_paths(self.changes_list, self._change_lines)
        args = ["diff"] + (["--"] + paths if paths else [])
        r = self.engine.run(args, cwd=self.path)
        DiffWindow(self, "Diff", r.stdout or "(no differences — file may be staged; try 'git diff --staged')")

    def act_commit(self):
        msg = simpledialog.askstring("Commit", "Commit message:", parent=self)
        if not msg:
            return
        self._confirm_and_run(["commit", "-m", msg])

    def act_new_branch(self):
        name = simpledialog.askstring("New Branch", "New branch name:", parent=self)
        if not name:
            return
        self._confirm_and_run(["switch", "-c", name])

    def act_checkout_selected_branch(self):
        sel = self.branch_list.curselection()
        if not sel:
            return
        name = self.branch_list.get(sel[0]).lstrip("● ○").strip()
        self._confirm_and_run(["switch", name])

    def act_merge_selected(self):
        sel = self.branch_list.curselection()
        if not sel:
            return
        name = self.branch_list.get(sel[0]).lstrip("● ○").strip()
        self._confirm_and_run(["merge", name], note=f"Merges '{name}' into the current branch.")

    def act_delete_branch(self):
        sel = self.branch_list.curselection()
        if not sel:
            return
        name = self.branch_list.get(sel[0]).lstrip("● ○").strip()
        self._confirm_and_run(["branch", "-d", name])

    def act_stash(self):
        self._confirm_and_run(["stash"])

    def act_stash_pop(self):
        self._confirm_and_run(["stash", "pop"])

    def act_stash_apply(self):
        self._confirm_and_run(["stash", "apply"])

    def act_stash_drop(self):
        self._confirm_and_run(["stash", "drop"], note="Permanently deletes the stash entry.")


class DiffWindow(tk.Toplevel):
    def __init__(self, master, title, text):
        super().__init__(master)
        self.title(title)
        self.geometry("760x560")
        txt = tk.Text(self, wrap="none", font=("Consolas", 10))
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", text)
        for i, line in enumerate(text.splitlines(), start=1):
            tag = None
            if line.startswith("+") and not line.startswith("+++"):
                tag = "add"
            elif line.startswith("-") and not line.startswith("---"):
                tag = "del"
            if tag:
                txt.tag_add(tag, f"{i}.0", f"{i}.end")
        txt.tag_config("add", foreground="#0a7d29")
        txt.tag_config("del", foreground="#c1121f")
        txt.config(state="disabled")


# --------------------------------------------------------------------------
# Command Palette (Ctrl+K)
# --------------------------------------------------------------------------

class CommandPalette(tk.Toplevel):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.overrideredirect(True)
        self.geometry(f"560x360+{master.winfo_rootx()+80}+{master.winfo_rooty()+60}")
        self.configure(bg="#1e1e1e")

        self.query = tk.StringVar()
        entry = ttk.Entry(self, textvariable=self.query, font=("Segoe UI", 13))
        entry.pack(fill="x", padx=8, pady=8)
        entry.focus_set()
        entry.bind("<KeyRelease>", self._filter)
        entry.bind("<Return>", self._run_selected)
        entry.bind("<Escape>", lambda e: self.destroy())
        self.bind("<FocusOut>", lambda e: self.after(150, self._maybe_close))

        self.results = tk.Listbox(self, font=("Consolas", 11), activestyle="none")
        self.results.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.results.bind("<Double-Button-1>", self._run_selected)

        self._filter()

    def _maybe_close(self):
        try:
            if self.focus_get() is None:
                self.destroy()
        except tk.TclError:
            pass

    def _filter(self, event=None):
        q = self.query.get().lower()
        self.results.delete(0, tk.END)
        self._matches = []
        for category, cmd, desc in COMMAND_CATALOG:
            hay = f"{category} {cmd} {desc}".lower()
            if all(tok in hay for tok in q.split()):
                self._matches.append((category, cmd, desc))
        for category, cmd, desc in self._matches[:30]:
            self.results.insert(tk.END, f"[{category}]  {cmd}   —  {desc}")

    def _run_selected(self, event=None):
        sel = self.results.curselection()
        idx = sel[0] if sel else 0
        if idx >= len(self._matches):
            self.destroy()
            return
        category, cmd, desc = self._matches[idx]
        self.destroy()
        self.app.explain_and_maybe_run(cmd, desc)


# --------------------------------------------------------------------------
# Main application
# --------------------------------------------------------------------------

class GitForgeStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — Git Bash, rebuilt as a developer cockpit")
        self.geometry("1180x760")
        self.minsize(980, 640)

        self.confirm_before_run = tk.BooleanVar(value=False)
        self.engine = GitEngine(on_log=self._log_to_terminal)
        self.repo_panels = {}

        self._build_menu()
        self._build_layout()
        self._doctor_check(startup=True)
        self.bind_all("<Control-k>", lambda e: CommandPalette(self, self))
        self.bind_all("<Control-o>", lambda e: self.open_folder())
        self.bind_all("<Control-l>", lambda e: self.notebook.select(self.terminal_tab))

    # ---------------------------------------------------------------- menu ----

    def _build_menu(self):
        menubar = tk.Menu(self)
        filem = tk.Menu(menubar, tearoff=0)
        filem.add_command(label="Open Folder…\tCtrl+O", command=self.open_folder)
        filem.add_command(label="Clone Repository…", command=self.clone_repo)
        filem.add_command(label="Create Repository…", command=self.create_repo)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=filem)

        gitm = tk.Menu(menubar, tearoff=0)
        gitm.add_command(label="Command Palette…\tCtrl+K", command=lambda: CommandPalette(self, self))
        gitm.add_command(label="Git Doctor", command=lambda: self._doctor_check(startup=False))
        gitm.add_checkbutton(label="Confirm every command before running", variable=self.confirm_before_run)
        menubar.add_cascade(label="Git", menu=gitm)

        helpm = tk.Menu(menubar, tearoff=0)
        helpm.add_command(label="Official Git Cheat Sheet", command=lambda: self._open_url("https://git-scm.com/cheat-sheet"))
        helpm.add_command(label="About", command=self._about)
        menubar.add_cascade(label="Help", menu=helpm)

        self.config(menu=menubar)

    def _open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def _about(self):
        messagebox.showinfo(APP_NAME, f"{APP_NAME} {APP_VERSION}\n\nGit Bash remains the engine.\nThis is the cockpit on top of it.")

    # -------------------------------------------------------------- layout ----

    def _build_layout(self):
        outer = ttk.Panedwindow(self, orient="vertical")
        outer.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(outer)
        outer.add(self.notebook, weight=4)

        # Home / dashboard tab
        self.home_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.home_tab, text="🏠 Dashboard")
        self._build_dashboard(self.home_tab)

        # Terminal / activity log (shared across repos)
        term_frame = ttk.Frame(outer)
        outer.add(term_frame, weight=2)
        head = ttk.Frame(term_frame)
        head.pack(fill="x")
        ttk.Label(head, text="TERMINAL / ACTIVITY LOG", font=("Segoe UI", 9, "bold")).pack(side="left", padx=8, pady=4)
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(head, textvariable=self.status_var, foreground="#888").pack(side="right", padx=8)
        self.terminal = tk.Text(term_frame, height=12, bg="#0d1117", fg="#c9d1d9", insertbackground="white",
                                 font=("Consolas", 10))
        self.terminal.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.terminal.tag_config("cmd", foreground="#79c0ff")
        self.terminal.tag_config("ok", foreground="#7ee787")
        self.terminal.tag_config("fail", foreground="#ff7b72")
        self.terminal_tab = term_frame

    def _build_dashboard(self, parent):
        top = ttk.Frame(parent, padding=16)
        top.pack(fill="x")
        ttk.Label(top, text="GitForge Studio", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(top, text="Every Git command. One workspace. Git Bash remains the engine.",
                  foreground="#666").pack(anchor="w")

        btns = ttk.Frame(parent, padding=(16, 0))
        btns.pack(fill="x")
        ttk.Button(btns, text="📂 Open Folder", command=self.open_folder).pack(side="left", padx=4, pady=8)
        ttk.Button(btns, text="⬇ Clone Repository", command=self.clone_repo).pack(side="left", padx=4)
        ttk.Button(btns, text="＋ Create Repository", command=self.create_repo).pack(side="left", padx=4)
        ttk.Button(btns, text="🩺 Git Doctor", command=lambda: self._doctor_check(startup=False)).pack(side="left", padx=4)
        ttk.Button(btns, text="⌘ Command Palette (Ctrl+K)", command=lambda: CommandPalette(self, self)).pack(side="left", padx=4)

        ttk.Label(parent, text="OPEN REPOSITORIES", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(16, 4))
        self.repo_overview = tk.Listbox(parent, height=10)
        self.repo_overview.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.repo_overview.bind("<Double-Button-1>", self._focus_repo_from_overview)

    # ------------------------------------------------------------- helpers ----

    def set_status(self, text):
        self.status_var.set(text)

    def _log_to_terminal(self, cmd_str, output, ok, duration):
        self.terminal.insert(tk.END, f"\n> {cmd_str}   ({duration:.2f}s)\n", "cmd")
        if output:
            self.terminal.insert(tk.END, output + "\n", "ok" if ok else "fail")
        elif not ok:
            self.terminal.insert(tk.END, "(command failed, no output)\n", "fail")
        self.terminal.see(tk.END)

    def explain_and_maybe_run(self, cmd_template, desc):
        # If the template has placeholders, ask the user to fill them.
        cmd = cmd_template
        if "<" in cmd:
            filled = simpledialog.askstring(
                "Fill in command", f"{desc}\n\nTemplate:\n{cmd}\n\nType the full command to run (edit as needed):",
                initialvalue=cmd, parent=self,
            )
            if not filled:
                return
            cmd = filled
        panel = self._active_panel()
        if panel is None:
            messagebox.showinfo("No repository open", "Open or select a repository tab first.")
            return
        args = cmd.split()[1:]  # strip leading "git"
        panel._confirm_and_run(args, note=desc)

    def _active_panel(self):
        try:
            current = self.notebook.select()
            widget = self.notebook.nametowidget(current)
            if isinstance(widget, RepoPanel):
                return widget
        except Exception:
            pass
        return None

    def _focus_repo_from_overview(self, event):
        sel = self.repo_overview.curselection()
        if not sel:
            return
        path = list(self.repo_panels.keys())[sel[0]]
        self.notebook.select(self.repo_panels[path])

    def _refresh_overview(self):
        self.repo_overview.delete(0, tk.END)
        for path, panel in self.repo_panels.items():
            branch = self.engine.current_branch(path)
            lines = self.engine.status_porcelain(path)
            changed = len([l for l in lines if not l.startswith("##")])
            state = "✓ Clean" if changed == 0 else f"● {changed} changes"
            self.repo_overview.insert(tk.END, f"{Path(path).name:<24} {state:<16} {branch}   ({path})")

    # ------------------------------------------------------------- actions ----

    def open_folder(self):
        path = filedialog.askdirectory(title="Open Folder")
        if not path:
            return
        self._open_repo_path(path)

    def _open_repo_path(self, path):
        path = str(Path(path))
        if path in self.repo_panels:
            self.notebook.select(self.repo_panels[path])
            return
        if not self.engine.is_repo(path):
            init = messagebox.askyesno(
                "Not a Git repository",
                f"{path}\n\nThis folder isn't a Git repository yet.\n\nCommand:\n    git init\n\nInitialize it now?",
            )
            if not init:
                return
            self.engine.run(["init"], cwd=path)
        panel = RepoPanel(self.notebook, self, path)
        self.notebook.add(panel, text=Path(path).name)
        self.repo_panels[path] = panel
        self.notebook.select(panel)
        self._refresh_overview()

    def clone_repo(self):
        url = simpledialog.askstring("Clone Repository", "Repository URL:", parent=self)
        if not url:
            return
        dest_parent = filedialog.askdirectory(title="Choose destination parent folder")
        if not dest_parent:
            return
        name = url.rstrip("/").split("/")[-1].removesuffix(".git")
        dest = str(Path(dest_parent) / name)
        r = self.engine.run(["clone", url, dest], cwd=dest_parent)
        if r.returncode == 0:
            self._open_repo_path(dest)
        else:
            messagebox.showerror("Clone failed", r.stderr or "See terminal log.")

    def create_repo(self):
        win = tk.Toplevel(self)
        win.title("Create Repository")
        win.geometry("420x260")
        ttk.Label(win, text="Project Name").pack(anchor="w", padx=12, pady=(12, 0))
        name_var = tk.StringVar()
        ttk.Entry(win, textvariable=name_var).pack(fill="x", padx=12)

        ttk.Label(win, text="Parent Folder").pack(anchor="w", padx=12, pady=(12, 0))
        folder_var = tk.StringVar()
        row = ttk.Frame(win); row.pack(fill="x", padx=12)
        ttk.Entry(row, textvariable=folder_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=lambda: folder_var.set(filedialog.askdirectory() or folder_var.get())).pack(side="left")

        readme_var = tk.BooleanVar(value=True)
        gitignore_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(win, text="Create README.md", variable=readme_var).pack(anchor="w", padx=12, pady=(12, 0))
        ttk.Checkbutton(win, text="Create .gitignore", variable=gitignore_var).pack(anchor="w")

        def do_create():
            name, folder = name_var.get().strip(), folder_var.get().strip()
            if not name or not folder:
                messagebox.showwarning("Missing info", "Project name and parent folder are required.")
                return
            path = Path(folder) / name
            path.mkdir(parents=True, exist_ok=True)
            self.engine.run(["init"], cwd=str(path))
            if readme_var.get():
                (path / "README.md").write_text(f"# {name}\n")
            if gitignore_var.get():
                (path / ".gitignore").write_text("__pycache__/\n*.pyc\n.venv/\nnode_modules/\n.vscode/\n")
            self.engine.run(["add", "."], cwd=str(path))
            self.engine.run(["commit", "-m", "Initial commit"], cwd=str(path))
            win.destroy()
            self._open_repo_path(str(path))

        ttk.Button(win, text="Create Project", command=do_create).pack(pady=16)

    # ----------------------------------------------------------- doctor ----

    def _doctor_check(self, startup=False):
        checks = []
        ok_git = self.engine.available()
        checks.append(("Git installed", ok_git))
        version = self.engine.version() if ok_git else None
        checks.append((f"Git version ({version or 'unknown'})", bool(version)))
        name, email = self.engine.global_identity() if ok_git else ("", "")
        checks.append((f"Global user.name ({name or 'not set'})", bool(name)))
        checks.append((f"Global user.email ({email or 'not set'})", bool(email)))
        gh = shutil.which("gh")
        checks.append(("GitHub CLI (gh) found — optional", bool(gh)))

        lines = []
        all_critical_ok = ok_git and bool(version)
        for label, ok in checks:
            lines.append(f"{'✓' if ok else '⚠'}  {label}")
        report = "\n".join(lines)

        if startup and all_critical_ok:
            self.set_status("Git Doctor: environment OK. " + (version or ""))
            return
        if not ok_git:
            messagebox.showerror(
                "Git Doctor",
                "Git was not detected on PATH.\n\nGitForge Studio requires Git for Windows "
                "(https://git-scm.com/downloads).\n\n" + report,
            )
        else:
            messagebox.showinfo("Git Doctor", report)


def main():
    CONFIG_DIR.mkdir(exist_ok=True)
    app = GitForgeStudio()
    app.mainloop()


if __name__ == "__main__":
    main()
