"""Tkinter card for the Compass drive-by test readiness checklist."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from drive_by_controller import (
    REQUIRED_PHONE_CONFIRMATIONS,
    DriveByReport,
    run_preflight,
)
from metro_controller import MetroController

STATUS_COLORS = {
    "READY": "#27ae60",
    "NEEDS_PHONE": "#f39c12",
    "NOT_READY": "#c0392b",
}


class DriveByCard:
    """Builds the 'Compass Drive-By Test Readiness' card."""

    def __init__(
        self,
        parent: ttk.Widget,
        metro_controller: MetroController,
        project_path_var: tk.StringVar,
        settings: dict,
        on_settings_changed: Callable[[], None],
    ) -> None:
        self.metro_controller = metro_controller
        self.project_path_var = project_path_var
        self.settings = settings
        self.on_settings_changed = on_settings_changed
        self.report: DriveByReport | None = None

        self.frame = ttk.LabelFrame(
            parent, text="Compass Drive-By Test Readiness", padding=(10, 8)
        )
        self.frame.pack(fill="x", pady=(12, 0))

        # Top controls
        controls = ttk.Frame(self.frame)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Run Preflight", command=self._run_preflight).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(controls, text="Reset Checklist", command=self._reset_checklist).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(controls, text="Copy Test Worksheet", command=self._copy_worksheet).pack(
            side="left"
        )

        # Overall status
        status_row = ttk.Frame(self.frame)
        status_row.pack(fill="x", pady=(0, 4))
        ttk.Label(status_row, text="Overall:", font=("Segoe UI", 10, "bold")).pack(
            side="left"
        )
        self.status_label = ttk.Label(
            status_row,
            text="NOT READY",
            font=("Segoe UI", 10, "bold"),
            foreground=STATUS_COLORS["NOT_READY"],
        )
        self.status_label.pack(side="left", padx=(4, 0))

        self.timestamp_label = ttk.Label(self.frame, text="Last preflight: —")
        self.timestamp_label.pack(anchor="w", pady=(0, 8))

        # Phone confirmations
        phone_frame = ttk.LabelFrame(self.frame, text="Required iPhone Confirmations", padding=(8, 6))
        phone_frame.pack(fill="x", pady=(0, 8))
        self.phone_vars: dict[str, tk.BooleanVar] = {}
        for label in REQUIRED_PHONE_CONFIRMATIONS:
            var = tk.BooleanVar(value=False)
            self.phone_vars[label] = var
            ttk.Checkbutton(phone_frame, text=label, variable=var).pack(
                anchor="w", pady=1
            )

        # Expected region count
        region_frame = ttk.Frame(self.frame)
        region_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(region_frame, text="Expected monitored-region count:").pack(side="left")
        self.region_count_var = tk.StringVar(
            value=str(self.settings.get("expected_region_count", ""))
        )
        ttk.Entry(region_frame, textvariable=self.region_count_var, width=8).pack(
            side="left", padx=(4, 4)
        )
        self.region_count_confirmed_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            region_frame,
            text="Persisted monitored-region count on the phone matches this number.",
            variable=self.region_count_confirmed_var,
        ).pack(side="left")

        # Business rows
        business_outer = ttk.LabelFrame(
            self.frame, text="Test Businesses (1–10)", padding=(8, 6)
        )
        business_outer.pack(fill="x", pady=(0, 8))
        self.business_rows_frame = ttk.Frame(business_outer)
        self.business_rows_frame.pack(fill="x")
        ttk.Button(
            business_outer, text="+ Add Business", command=self._add_business_row
        ).pack(anchor="w", pady=(4, 0))
        self.business_rows: list[dict[str, Any]] = []
        loaded_businesses = self.settings.get("businesses", [])
        for business in loaded_businesses[:10]:
            self._add_business_row_with_values(business)
        if not self.business_rows:
            self._add_business_row()

        # Expandable details/log
        details_label = ttk.Label(self.frame, text="Preflight Details:", font=("Segoe UI", 9, "bold"))
        details_label.pack(anchor="w", pady=(8, 2))
        details_frame = ttk.Frame(self.frame)
        details_frame.pack(fill="both", expand=True)
        self.details_text = tk.Text(
            details_frame, height=10, wrap="word", state="disabled", font=("Consolas", 9)
        )
        details_scroll = ttk.Scrollbar(details_frame, command=self.details_text.yview)
        self.details_text.configure(yscrollcommand=details_scroll.set)
        self.details_text.pack(side="left", fill="both", expand=True)
        details_scroll.pack(side="right", fill="y")
        ttk.Button(self.frame, text="Clear Details", command=self._clear_details).pack(
            anchor="w", pady=(4, 0)
        )

        # Optional note about Metro
        ttk.Label(
            self.frame,
            text=(
                "Note: Metro is optional for the physical drive test after the current app bundle "
                "and regions have been prepared."
            ),
            wraplength=480,
            justify="left",
            foreground="gray",
        ).pack(anchor="w", pady=(8, 0))

    # -------------------------------------------------------------------------
    # Business rows
    # -------------------------------------------------------------------------

    def _add_business_row(self) -> None:
        if len(self.business_rows) >= 10:
            return
        self._add_business_row_with_values({})

    def _add_business_row_with_values(self, values: dict[str, Any]) -> None:
        row = ttk.Frame(self.business_rows_frame)
        row.pack(fill="x", pady=2)

        name_var = tk.StringVar(value=values.get("name", ""))
        intent_var = tk.StringVar(value=values.get("intent", ""))
        radius_var = tk.StringVar(value=str(values.get("radius", "")))
        cooldown_var = tk.BooleanVar(value=values.get("cooldown_reset", False))
        outside_var = tk.BooleanVar(value=values.get("outside", False))
        notes_var = tk.StringVar(value=values.get("notes", ""))

        ttk.Label(row, text="Name:").pack(side="left")
        ttk.Entry(row, textvariable=name_var, width=12).pack(side="left", padx=(2, 6))
        ttk.Label(row, text="Intent:").pack(side="left")
        ttk.Entry(row, textvariable=intent_var, width=14).pack(side="left", padx=(2, 6))
        ttk.Label(row, text="Radius:").pack(side="left")
        ttk.Entry(row, textvariable=radius_var, width=6).pack(side="left", padx=(2, 6))
        ttk.Checkbutton(row, text="Cooldown reset", variable=cooldown_var).pack(
            side="left", padx=(0, 4)
        )
        ttk.Checkbutton(row, text="Starting outside", variable=outside_var).pack(
            side="left", padx=(0, 4)
        )
        ttk.Label(row, text="Notes:").pack(side="left")
        ttk.Entry(row, textvariable=notes_var, width=14).pack(side="left", padx=(2, 4))
        ttk.Button(row, text="✕", width=2, command=lambda r=row: self._remove_business_row(r)).pack(
            side="left"
        )

        self.business_rows.append(
            {
                "frame": row,
                "name": name_var,
                "intent": intent_var,
                "radius": radius_var,
                "cooldown_reset": cooldown_var,
                "outside": outside_var,
                "notes": notes_var,
            }
        )

    def _remove_business_row(self, row: ttk.Frame) -> None:
        for entry in list(self.business_rows):
            if entry["frame"] is row:
                self.business_rows.remove(entry)
                row.destroy()
                break
        if not self.business_rows:
            self._add_business_row()
        self._persist_businesses()

    def _collect_businesses(self) -> list[dict[str, Any]]:
        businesses: list[dict[str, Any]] = []
        for entry in self.business_rows:
            business = {
                "name": entry["name"].get().strip(),
                "intent": entry["intent"].get().strip(),
                "radius": entry["radius"].get().strip(),
                "cooldown_reset": entry["cooldown_reset"].get(),
                "outside": entry["outside"].get(),
                "notes": entry["notes"].get().strip(),
            }
            businesses.append(business)
        return businesses

    def _persist_businesses(self) -> None:
        self.settings["businesses"] = self._collect_businesses()
        self.on_settings_changed()

    # -------------------------------------------------------------------------
    # Preflight
    # -------------------------------------------------------------------------

    def _parse_expected_region_count(self) -> int | None:
        raw = self.region_count_var.get().strip()
        if not raw:
            return None
        try:
            value = int(raw)
            return value if value > 0 else None
        except ValueError:
            return None

    def _run_preflight(self) -> None:
        self._persist_businesses()
        expected_count = self._parse_expected_region_count()
        if expected_count is not None:
            self.settings["expected_region_count"] = expected_count
            self.on_settings_changed()

        phone_confirmations = {
            label: var.get() for label, var in self.phone_vars.items()
        }

        report = run_preflight(
            controller=self.metro_controller,
            project_path=self.project_path_var.get(),
            phone_confirmations=phone_confirmations,
            expected_region_count=expected_count,
            region_count_confirmed=self.region_count_confirmed_var.get(),
            businesses=self._collect_businesses(),
        )
        self.report = report

        status_text = {
            "READY": "READY FOR DRIVE TEST",
            "NEEDS_PHONE": "NEEDS PHONE CONFIRMATION",
            "NOT_READY": "NOT READY",
        }.get(report.status, report.status)
        self.status_label.configure(
            text=status_text, foreground=STATUS_COLORS.get(report.status, "gray")
        )
        self.timestamp_label.configure(
            text=f"Last preflight: {report.timestamp or '—'}"
        )

        details = self._format_report(report)
        self._set_details(details)

    def _format_report(self, report: DriveByReport) -> str:
        lines: list[str] = []
        lines.append(f"Metro status: {report.metro_status}")
        lines.append(f"Mission Control owns Metro: {report.metro_owned}")
        lines.append(f"Port 8081 occupied: {report.port_occupied}")
        if report.metro_url:
            lines.append(f"LAN/Expo URL: {report.metro_url}")
        if report.controller_error:
            lines.append(f"Controller error: {report.controller_error}")
        lines.append("")

        for check in report.checks:
            symbol = "✓" if check.ok else "✗"
            lines.append(f"{symbol} {check.name}: {check.message}")
            if not check.ok:
                guidance = self._guidance_for(check.name)
                if guidance:
                    lines.append(f"   → {guidance}")
            for key, value in check.details.items():
                lines.append(f"   {key}: {value}")
        lines.append("")

        valid_businesses = [b for b in self._collect_businesses() if b.get("name", "").strip()]
        lines.append(f"Entered businesses: {len(valid_businesses)}")
        for business in valid_businesses:
            lines.append(
                f"  • {business['name']} ({business['intent']}) — radius {business['radius']} "
                f"| cooldown {'✓' if business['cooldown_reset'] else '✗'} "
                f"| outside {'✓' if business['outside'] else '✗'}"
            )
        return "\n".join(lines)

    def _guidance_for(self, check_name: str) -> str:
        guidance = {
            "Project Compass path": "Set a valid Project Compass path in the Metro card and validate it.",
            "Git working-tree status": "Ensure the path is a Git repository and Git is on PATH.",
            "Windows network availability": "Connect to a LAN/Wi-Fi network before testing.",
            "Metro status": "If Metro crashed, review the Metro log, stop it, and restart.",
        }
        return guidance.get(check_name, "Review this item before the drive test.")

    # -------------------------------------------------------------------------
    # Details log
    # -------------------------------------------------------------------------

    def _set_details(self, text: str) -> None:
        self.details_text.configure(state="normal")
        self.details_text.delete("1.0", "end")
        self.details_text.insert("end", text)
        self.details_text.see("end")
        self.details_text.configure(state="disabled")

    def _clear_details(self) -> None:
        self.details_text.configure(state="normal")
        self.details_text.delete("1.0", "end")
        self.details_text.configure(state="disabled")

    # -------------------------------------------------------------------------
    # Reset / worksheet
    # -------------------------------------------------------------------------

    def _reset_checklist(self) -> None:
        for var in self.phone_vars.values():
            var.set(False)
        self.region_count_confirmed_var.set(False)
        self.status_label.configure(text="NOT READY", foreground=STATUS_COLORS["NOT_READY"])
        self.timestamp_label.configure(text="Last preflight: —")
        self._set_details("Checklist reset. Run Preflight when ready.")

    def _copy_worksheet(self) -> None:
        import json
        import os
        import subprocess
        from datetime import datetime

        path = self.project_path_var.get()
        commit = "—"
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%h"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                commit = result.stdout.strip()
        except Exception:
            pass

        metro_status = self.report.metro_status if self.report else "Unknown"
        metro_url = self.report.metro_url if self.report else "—"
        region_count = self.region_count_var.get() or "—"

        lines: list[str] = [
            "Compass Drive-By Test",
            f"Date/time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Compass commit: {commit}",
            f"Expected monitored regions: {region_count}",
            f"Metro status: {metro_status}",
            f"LAN URL: {metro_url}",
            "",
        ]

        valid_businesses = [
            b for b in self._collect_businesses() if b.get("name", "").strip()
        ]
        for business in valid_businesses:
            lines.extend(
                [
                    f"Business: {business['name']}",
                    f"Associated Intent: {business['intent']}",
                    "Approximate arrival time:",
                    "Phone locked/backgrounded:",
                    "Notification appeared:",
                    "Correct business shown:",
                    "Correct Intent shown:",
                    "Approximate delay:",
                    "Native entry recorded:",
                    "Correct region ID:",
                    "Cooldown became active:",
                    "Duplicate notification:",
                    "Other issues:",
                    "",
                ]
            )

        if not valid_businesses:
            lines.append("(No businesses entered)\n")

        text = "\n".join(lines)
        try:
            self.frame.winfo_toplevel().clipboard_clear()
            self.frame.winfo_toplevel().clipboard_append(text)
            self._set_details("Test worksheet copied to clipboard.\n\n" + text)
        except Exception as exc:
            self._set_details(f"Failed to copy worksheet: {exc}")

    # -------------------------------------------------------------------------
    # Persistence helpers used by app.py
    # -------------------------------------------------------------------------

    def save_persistent_state(self) -> None:
        self._persist_businesses()
        count = self._parse_expected_region_count()
        if count is not None:
            self.settings["expected_region_count"] = count
        else:
            self.settings.pop("expected_region_count", None)
        self.on_settings_changed()
