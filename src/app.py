
import tkinter as tk
from tkinter import ttk
import subprocess, webbrowser, os
from pathlib import Path

PROJECTS = {
    "Project Compass": {
        "path": r"C:\Users\shawn\CascadeProjects\project-compass",
        "github": "https://github.com/skelley917/project-compass",
        "start": ["cmd","/c","start","cmd","/k",
                  'cd /d "C:\\Users\\shawn\\CascadeProjects\\project-compass" && npx.cmd expo start --clear']
    }
}

current = PROJECTS["Project Compass"]

def launch(cmd):
    subprocess.Popen(cmd)

def open_folder():
    os.startfile(current["path"])

def open_docs():
    os.startfile(os.path.join(current["path"],"docs"))

def vscode():
    subprocess.Popen(["cmd","/c","code",current["path"]])

def dev_server():
    launch(current["start"])

def open_url(url):
    webbrowser.open(url)

def get_git_status():
    path = current["path"]
    try:
        branch = subprocess.run(
            ["git","branch","--show-current"],
            cwd=path, capture_output=True, text=True, timeout=5
        ).stdout.strip() or "unknown"

        porcelain = subprocess.run(
            ["git","status","--porcelain"],
            cwd=path, capture_output=True, text=True, timeout=5
        ).stdout.strip()

        latest = subprocess.run(
            ["git","log","-1","--pretty=format:%h %s"],
            cwd=path, capture_output=True, text=True, timeout=5
        ).stdout.strip() or "—"

        if porcelain:
            indicator = "🟡 Working Tree Modified"
            tree = "Modified"
        else:
            indicator = "🟢 Ready to Build"
            tree = "Clean"

        return {
            "ok": True,
            "indicator": indicator,
            "branch": branch,
            "tree": tree,
            "latest": latest,
        }
    except Exception:
        return {"ok": False}

root=tk.Tk()
root.title("Mission Control")
root.geometry("520x660")
root.resizable(False,False)

title=ttk.Label(root,text="🧭 Mission Control",font=("Segoe UI",20,"bold"))
title.pack(pady=(15,4))
ttk.Label(root,text="Founder Platform v0.1").pack()

# --- Git Status Dashboard ---
git_outer = ttk.Frame(root, padding=(15,10,15,0))
git_outer.pack(fill="x")

git_info = get_git_status()

if not git_info["ok"]:
    ttk.Label(git_outer,
              text="🔴 Git Status Unavailable",
              font=("Segoe UI",11,"bold"),
              foreground="#c0392b").pack(anchor="w")
else:
    ttk.Label(git_outer,
              text=git_info["indicator"],
              font=("Segoe UI",11,"bold")).pack(anchor="w", pady=(0,6))

    git_grid = ttk.Frame(git_outer)
    git_grid.pack(fill="x")

    def git_row(label, value, wrap=False):
        row = ttk.Frame(git_grid)
        row.pack(fill="x", pady=1)
        ttk.Label(row, text=label, font=("Segoe UI",9), foreground="gray",
                  width=16, anchor="w").pack(side="left")
        lbl = ttk.Label(row, text=value, font=("Segoe UI",9), anchor="w")
        lbl.pack(side="left", fill="x", expand=True)
        if wrap:
            lbl.configure(wraplength=330, justify="left")

    git_row("Project:",      "Project Compass")
    git_row("Branch:",       git_info["branch"])
    git_row("Git Status:",   git_info["tree"])
    git_row("Latest Commit:", git_info["latest"], wrap=True)

ttk.Separator(root, orient="horizontal").pack(fill="x", padx=15, pady=(10,0))

# --- Action Buttons ---
frm=ttk.Frame(root,padding=15)
frm.pack(fill="both",expand=True)

def section(name):
    ttk.Label(frm,text=name,font=("Segoe UI",10,"bold")).pack(anchor="w",pady=(12,4))
def btn(text,cmd):
    ttk.Button(frm,text=text,command=cmd).pack(fill="x",pady=3)

section("Development")
btn("🚀 Start Dev Server",dev_server)
btn("💻 Open VS Code",vscode)
btn("📂 Open Project Folder",open_folder)

section("AI")
btn("🤖 Open Devin",lambda:open_url("https://app.devin.ai"))
btn("💬 Open ChatGPT",lambda:open_url("https://chatgpt.com"))

section("Project")
btn("🌐 GitHub",lambda:open_url(current["github"]))
btn("📚 Open Docs",open_docs)

ttk.Label(root,text="Build Quiet. Earn Trust.",foreground="gray").pack(pady=8)
root.mainloop()
