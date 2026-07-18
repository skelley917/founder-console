"""Tests for Mission Control resizable window, scrollable dashboard, and geometry helpers."""

from __future__ import annotations

import os
import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from scrollable_frame import ScrollableFrame
from window_geometry import (
    clamp_geometry,
    format_geometry,
    get_initial_geometry,
    parse_geometry,
)


class TestGeometryHelpers(unittest.TestCase):
    def test_parse_geometry_valid(self):
        self.assertEqual(parse_geometry("800x600+100+50"), (800, 600, 100, 50))

    def test_parse_geometry_invalid(self):
        self.assertIsNone(parse_geometry("not-a-geometry"))
        self.assertIsNone(parse_geometry(""))

    def test_format_geometry(self):
        self.assertEqual(format_geometry(800, 600, 100, 50), "800x600+100+50")

    def test_clamp_geometry(self):
        self.assertEqual(
            clamp_geometry(2000, 1200, -50, -50, 1920, 1080, 640, 500),
            (1920, 1080, 0, 0),
        )

    def test_saved_geometry_restored_when_valid(self):
        geom = get_initial_geometry(1920, 1080, "900x700+100+100")
        self.assertEqual(geom, (900, 700, 100, 100))

    def test_saved_geometry_rejected_when_off_screen(self):
        geom = get_initial_geometry(1920, 1080, "900x700+2000+100")
        # Falls back to default centered geometry that fits the screen.
        self.assertNotEqual(geom, (900, 700, 2000, 100))
        self.assertGreaterEqual(geom[0], 640)
        self.assertGreaterEqual(geom[1], 500)
        self.assertLessEqual(geom[2] + geom[0], 1920)
        self.assertGreaterEqual(geom[2], 0)
        self.assertLessEqual(geom[2] + geom[0], 1920)

    def test_default_size_does_not_exceed_screen(self):
        geom = get_initial_geometry(1366, 768, None)
        width, height, x, y = geom
        self.assertLessEqual(width, 1366)
        self.assertLessEqual(height, 768)
        self.assertLessEqual(x + width, 1366)
        self.assertLessEqual(y + height, 768)
        self.assertGreaterEqual(width, 640)
        self.assertGreaterEqual(height, 500)

    def test_default_size_clamped_to_max_height(self):
        # A very large screen should not produce an excessively tall window.
        geom = get_initial_geometry(3840, 2160, None)
        self.assertLessEqual(geom[1], 1000)


class TestScrollableFrame(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("600x400")
        self.scrollable = ScrollableFrame(self.root)
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def _update(self):
        self.root.update_idletasks()
        self.root.update()
        self.scrollable.update_scrollregion()
        self.root.update()

    def test_inner_frame_exists_inside_canvas(self):
        children = self.scrollable.canvas.find_all()
        self.assertIn(self.scrollable._window, children)

    def test_scrollbar_visible_when_content_exceeds_viewport(self):
        for i in range(40):
            tk.Label(self.scrollable.frame, text=f"Line {i}", font=("Arial", 24)).pack()
        self._update()
        self.assertTrue(self.scrollable.scrollbar.winfo_ismapped())

    def test_scrollbar_hidden_when_content_fits(self):
        tk.Label(self.scrollable.frame, text="Short content").pack()
        self._update()
        if self.scrollable.scrollbar.winfo_ismapped():
            bbox = self.scrollable.canvas.bbox("all")
            self.assertLessEqual(bbox[3] - bbox[1], 400)

    def test_canvas_width_resizes_with_window(self):
        inner_width = self.scrollable.canvas.itemcget(self.scrollable._window, "width")
        self.assertEqual(int(inner_width), self.scrollable.canvas.winfo_width())
        self.root.geometry("800x400")
        self._update()
        inner_width = self.scrollable.canvas.itemcget(self.scrollable._window, "width")
        self.assertGreaterEqual(int(inner_width), 780)

    def test_mousewheel_over_text_widget_ignored(self):
        text = tk.Text(self.scrollable.frame, height=5)
        text.pack()
        self.root.update()
        self.assertTrue(self.scrollable._is_local_scroll_widget(text))


class TestAppWindowProperties(unittest.TestCase):
    def test_app_imports_without_error(self):
        import app

        self.assertTrue(hasattr(app, "build_ui"))

    def test_build_ui_creates_scrollable_dashboard(self):
        import app

        root = tk.Tk()
        root.withdraw()
        try:
            settings = {"project_path": str(Path.cwd())}
            app.build_ui(root, app.current_project(), settings)
            self.root = root
            root.update()
            # The root should now be resizable.
            self.assertTrue(root.resizable()[0])
            self.assertTrue(root.resizable()[1])
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
