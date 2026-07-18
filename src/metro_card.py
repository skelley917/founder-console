"""Tkinter UI card for the Mission Control Metro controller."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from metro_controller import MetroController

STATUS_COLORS = {
    "Stopped": "gray",
    "Starting": "#f39c12",
    "Running": "#27ae60",
    "Stopping": "#f39c12",
    "Error": "#c0392b",
}


class MetroCard:
    """Builds the Project Compass — Metro card in a parent frame."""

    def __init__(
        self,
        parent: ttk.Widget,
        controller: MetroController,
        project_path_var: tk.StringVar,
        on_save_settings: Callable[[], None],
    ) -> None:
        self.controller = controller
        self.project_path_var = project_path_var
        self.on_save_settings = on_save_settings

        frame = ttk.LabelFrame(parent, text="Project Compass — Metro", padding=(10, 8))
        frame.pack(fill="x", pady=(12, 0))

        # Status row
        status_row = ttk.Frame(frame)
        status_row.pack(fill="x", pady=(0, 6))
        ttk.Label(status_row, text="Status:", font=("Segoe UI", 9)).pack(side="left")
        self.status_value = ttk.Label(
            status_row, text="Stopped", font=("Segoe UI", 9, "bold")
        )
        self.status_value.pack(side="left", padx=(4, 0))

        self.status_message = ttk.Label(
            frame, text="Metro is not running", wraplength=420, justify="left"
        )
        self.status_message.pack(fill="x", pady=(0, 6))

        # URL row
        url_row = ttk.Frame(frame)
        url_row.pack(fill="x", pady=(0, 6))
        ttk.Label(url_row, text="URL:", font=("Segoe UI", 9)).pack(side="left")
        self.url_value = ttk.Label(
            url_row, text="—", font=("Segoe UI", 9, "bold"), foreground="#2980b9"
        )
        self.url_value.pack(side="left", padx=(4, 0))

        # Controls
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 6))
        self.start_btn = ttk.Button(
            controls, text="Start Metro", command=self._on_start
        )
        self.start_btn.pack(side="left", padx=(0, 4))
        self.stop_btn = ttk.Button(
            controls, text="Stop Metro", command=self._on_stop, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=(0, 4))
        self.restart_btn = ttk.Button(
            controls, text="Restart Metro", command=self._on_restart, state="disabled"
        )
        self.restart_btn.pack(side="left")

        # Path / Settings
        path_frame = ttk.Frame(frame)
        path_frame.pack(fill="x", pady=(6, 0))
        ttk.Label(path_frame, text="Project path:").pack(side="left")
        self.path_entry = ttk.Entry(path_frame, textvariable=project_path_var)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(4, 4))
        ttk.Button(path_frame, text="Validate", command=self._on_validate).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(path_frame, text="Save", command=self._on_save).pack(side="left")

        self.validation_label = ttk.Label(frame, text="", wraplength=420)
        self.validation_label.pack(fill="x", pady=(2, 0))

        # Expandable log area
        ttk.Label(frame, text="Log:", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", pady=(10, 2)
        )
        log_frame = ttk.Frame(frame)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(
            log_frame,
            height=10,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        log_controls = ttk.Frame(frame)
        log_controls.pack(fill="x", pady=(4, 0))
        ttk.Button(log_controls, text="Clear Log", command=self._on_clear_log).pack(
            side="left"
        )
        ttk.Button(log_controls, text="Open Project Folder", command=self._on_open_folder).pack(
            side="left", padx=(4, 0)
        )

        controller.add_listener(self._refresh)
        self._refresh()

    # -------------------------------------------------------------------------
    # UI callbacks
    # -------------------------------------------------------------------------

    def _on_start(self) -> None:
        path = self.project_path_var.get()
        ok, message = self.controller.start(path)
        if not ok:
            self.validation_label.configure(text=message, foreground="#c0392b")
        else:
            self.validation_label.configure(text=message, foreground="#27ae60")

    def _on_stop(self) -> None:
        self.controller.stop()

    def _on_restart(self) -> None:
        path = self.project_path_var.get()
        ok, message = self.controller.restart(path)
        if not ok:
            self.validation_label.configure(text=message, foreground="#c0392b")
        else:
            self.validation_label.configure(text=message, foreground="#27ae60")

    def _on_validate(self) -> None:
        ok, message = MetroController.validate_project_directory(
            self.project_path_var.get()
        )
        if ok:
            self.validation_label.configure(text=message, foreground="#27ae60")
        else:
            self.validation_label.configure(text=message, foreground="#c0392b")

    def _on_save(self) -> None:
        self.on_save_settings()
        self.validation_label.configure(text="Settings saved", foreground="#27ae60")

    def _on_clear_log(self) -> None:
        self.controller.clear_logs()
        self._render_logs()

    def _on_open_folder(self) -> None:
        import os

        os.startfile(self.project_path_var.get())

    # -------------------------------------------------------------------------
    # Refresh
    # -------------------------------------------------------------------------

    def _refresh(self) -> None:
        status = self.controller.status
        self.status_value.configure(
            text=status, foreground=STATUS_COLORS.get(status, "gray")
        )
        self.status_message.configure(text=self.controller.status_message)
        url = self.controller.last_url
        self.url_value.configure(text=url if url else "—")

        running = self.controller.is_running
        self.start_btn.configure(state="normal" if not running else "disabled")
        self.stop_btn.configure(state="normal" if running else "disabled")
        self.restart_btn.configure(state="normal" if running else "disabled")

        self._render_logs()

    def _render_logs(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        for line in self.controller.get_logs():
            self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
