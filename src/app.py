
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

root=tk.Tk()
root.title("Mission Control")
root.geometry("520x560")
root.resizable(False,False)

title=ttk.Label(root,text="🧭 Mission Control",font=("Segoe UI",20,"bold"))
title.pack(pady=(15,4))
ttk.Label(root,text="Founder Platform v0.1").pack()

status=ttk.Label(root,text="Project: Project Compass\nStatus: Ready to Build",
                 font=("Segoe UI",11))
status.pack(pady=12)

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
