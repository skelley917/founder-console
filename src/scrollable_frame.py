"""Reusable vertically scrollable frame for Tkinter dashboards."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


class ScrollableFrame:
    """A canvas-backed frame that scrolls vertically and tracks content size."""

    def __init__(self, parent: tk.Widget) -> None:
        self.parent = parent
        self.canvas = tk.Canvas(parent, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(
            parent, orient="vertical", command=self.canvas.yview
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.frame = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window(
            (0, 0), window=self.frame, anchor="nw", tags="inner"
        )

        self.frame.bind("<Configure>", lambda _event: self.update_scrollregion())
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Windows mouse-wheel support. Binding to the canvas alone does not fire
        # when the pointer is over a child widget, so we bind at the application
        # level and ignore events whose source is a local scrollable widget.
        self._wheel_binding = self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    # -------------------------------------------------------------------------
    # Layout / scrollregion
    # -------------------------------------------------------------------------

    def _on_canvas_configure(self, event: tk.Event) -> None:
        """Keep the inner frame as wide as the visible canvas area."""
        self.canvas.itemconfig(self._window, width=event.width)
        self.update_scrollregion()

    def update_scrollregion(self) -> None:
        """Recalculate the canvas scroll region from the current content."""
        self.canvas.update_idletasks()
        bbox = self.canvas.bbox("all")
        if bbox:
            self.canvas.configure(scrollregion=bbox)
        self._update_scrollbar_visibility()

    def _update_scrollbar_visibility(self) -> None:
        """Show the scrollbar only when the content exceeds the viewport."""
        self.canvas.update_idletasks()
        bbox = self.canvas.bbox("all")
        if not bbox:
            return
        content_height = bbox[3] - bbox[1]
        viewport_height = self.canvas.winfo_height()
        if content_height > viewport_height:
            if not self.scrollbar.winfo_ismapped():
                self.scrollbar.pack(side="right", fill="y")
        else:
            if self.scrollbar.winfo_ismapped():
                self.scrollbar.pack_forget()
            # Reset to top when everything fits.
            self.canvas.yview_moveto(0.0)

    # -------------------------------------------------------------------------
    # Mouse wheel
    # -------------------------------------------------------------------------

    def _on_mousewheel(self, event: tk.Event) -> None:
        """Scroll the dashboard unless the pointer is over a local text/scrollbar."""
        widget = event.widget
        if widget is None:
            return
        if self._is_local_scroll_widget(widget):
            return

        # event.delta is typically ±120 on Windows.
        delta = event.delta
        if delta == 0:
            return
        steps = int(-1 * (delta / 120))
        self.canvas.yview_scroll(steps, "units")

    @staticmethod
    def _is_local_scroll_widget(widget: tk.Widget) -> bool:
        """Return True if the widget (or an ancestor) is a Text or local Scrollbar."""
        current: tk.Widget | str | None = widget
        while current and isinstance(current, tk.Widget):
            cls = current.winfo_class()
            if cls == "Text" or cls.endswith("Scrollbar"):
                return True
            try:
                current = current.winfo_parent()
            except tk.TclError:
                break
            if current == ".":
                break
        return False

    # -------------------------------------------------------------------------
    # Public helpers
    # -------------------------------------------------------------------------

    def scroll_to_bottom(self) -> None:
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0.0)

    def set_content_update_callback(self, callback: Callable[[], None]) -> None:
        """Optional hook so cards can request a scroll-region refresh."""
        self._content_update_callback = callback

    def notify_content_changed(self) -> None:
        self.update_scrollregion()
        if hasattr(self, "_content_update_callback") and self._content_update_callback:
            self._content_update_callback()
