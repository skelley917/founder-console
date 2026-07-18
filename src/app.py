import json
import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from drive_by_card import DriveByCard
from metro_card import MetroCard
from metro_controller import MetroController
from scrollable_frame import ScrollableFrame
from window_geometry import format_geometry, get_initial_geometry, parse_geometry

PROJECTS = {
    "Project Compass": {
        "path": r"C:\Users\shawn\CascadeProjects\project-compass",
        "github": "https://github.com/skelley917/project-compass",
    }
}

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "settings.json"


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"project_path": PROJECTS["Project Compass"]["path"]}


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass


def current_project() -> dict:
    return PROJECTS["Project Compass"]


def open_folder(path: str) -> None:
    os.startfile(path)


def open_docs(path: str) -> None:
    os.startfile(os.path.join(path, "docs"))


def vscode(path: str) -> None:
    subprocess.Popen(["cmd", "/c", "code", path])


def open_url(url: str) -> None:
    import webbrowser

    webbrowser.open(url)


def get_git_status(path: str) -> dict:
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=path, capture_output=True, text=True, timeout=5
        ).stdout.strip() or "unknown"

        porcelain = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path, capture_output=True, text=True, timeout=5
        ).stdout.strip()

        latest = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%h %s"],
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


def build_ui(root: tk.Tk, project: dict, settings: dict) -> None:
    project_path_var = tk.StringVar(value=settings.get("project_path", project["path"]))
    metro_controller = MetroController()

    def persist_settings() -> None:
        save_settings(settings)

    def persist_path() -> None:
        settings["project_path"] = project_path_var.get()
        persist_settings()

    def save_window_geometry() -> None:
        try:
            geom = root.geometry()
            parsed = parse_geometry(geom)
            if parsed:
                settings["window_geometry"] = geom
                save_settings(settings)
        except Exception:
            pass

    def on_closing() -> None:
        drive_by_card.save_persistent_state()
        save_window_geometry()
        root.destroy()

    root.title("Mission Control")
    root.minsize(640, 500)
    root.resizable(True, True)

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    saved_geometry = settings.get("window_geometry")
    width, height, x, y = get_initial_geometry(screen_w, screen_h, saved_geometry)
    root.geometry(format_geometry(width, height, x, y))

    root.protocol("WM_DELETE_WINDOW", on_closing)

    # Header stays fixed at the top.
    ttk.Label(root, text="🧭 Mission Control", font=("Segoe UI", 20, "bold")).pack(
        pady=(15, 4)
    )
    ttk.Label(root, text="Founder Platform v0.1").pack()

    ttk.Separator(root, orient="horizontal").pack(fill="x", padx=15, pady=(10, 0))

    # Scrollable dashboard area.
    scrollable = ScrollableFrame(root)
    scrollable.canvas.pack_configure(fill="both", expand=True)
    content = scrollable.frame

    # --- Git Status Dashboard ---
    git_outer = ttk.Frame(content, padding=(15, 10, 15, 0))
    git_outer.pack(fill="x")

    git_info = get_git_status(project["path"])

    if not git_info["ok"]:
        ttk.Label(
            git_outer,
            text="🔴 Git Status Unavailable",
            font=("Segoe UI", 11, "bold"),
            foreground="#c0392b",
        ).pack(anchor="w")
    else:
        ttk.Label(
            git_outer,
            text=git_info["indicator"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 6))

        git_grid = ttk.Frame(git_outer)
        git_grid.pack(fill="x")

        def git_row(label: str, value: str, wrap: bool = False) -> None:
            row = ttk.Frame(git_grid)
            row.pack(fill="x", pady=1)
            ttk.Label(
                row,
                text=label,
                font=("Segoe UI", 9),
                foreground="gray",
                width=16,
                anchor="w",
            ).pack(side="left")
            lbl = ttk.Label(row, text=value, font=("Segoe UI", 9), anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            if wrap:
                lbl.configure(wraplength=330, justify="left")

        git_row("Project:", "Project Compass")
        git_row("Branch:", git_info["branch"])
        git_row("Git Status:", git_info["tree"])
        git_row("Latest Commit:", git_info["latest"], wrap=True)

    ttk.Separator(content, orient="horizontal").pack(fill="x", padx=15, pady=(10, 0))

    # --- Action Buttons ---
    frm = ttk.Frame(content, padding=15)
    frm.pack(fill="both", expand=True)

    def section(name: str) -> None:
        ttk.Label(frm, text=name, font=("Segoe UI", 10, "bold")).pack(
            anchor="w", pady=(12, 4)
        )

    def btn(text: str, cmd) -> None:
        ttk.Button(frm, text=text, command=cmd).pack(fill="x", pady=3)

    # --- Metro Card ---
    MetroCard(frm, metro_controller, project_path_var, persist_path)

    # --- Drive-By Readiness Card ---
    drive_by_card = DriveByCard(
        frm, metro_controller, project_path_var, settings, persist_settings
    )

    section("Development")
    btn("💻 Open VS Code", lambda: vscode(project["path"]))
    btn("📂 Open Project Folder", lambda: open_folder(project["path"]))

    section("AI")
    btn("🤖 Open Devin", lambda: open_url("https://app.devin.ai"))
    btn("💬 Open ChatGPT", lambda: open_url("https://chatgpt.com"))

    section("Project")
    btn("🌐 GitHub", lambda: open_url(project["github"]))
    btn("📚 Open Docs", lambda: open_docs(project["path"]))

    ttk.Label(content, text="Build Quiet. Earn Trust.", foreground="gray").pack(pady=8)

    # Keep the scroll region current as cards expand, collapse, or change content.
    def refresh_scrollregion(_event=None) -> None:
        scrollable.update_scrollregion()

    content.bind("<Configure>", refresh_scrollregion)

    # Notify cards when content changes so the scroll region stays current.
    original_drive_by_notify = drive_by_card._set_details if hasattr(drive_by_card, "_set_details") else None
    if original_drive_by_notify:
        def patched_set_details(text: str) -> None:
            original_drive_by_notify(text)
            refresh_scrollregion()
        drive_by_card._set_details = patched_set_details

    scrollable.update_scrollregion()


def main() -> None:
    root = tk.Tk()
    project = current_project()
    settings = load_settings()
    build_ui(root, project, settings)
    root.mainloop()


if __name__ == "__main__":
    main()
