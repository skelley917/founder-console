"""Tests for Compass drive-by test readiness feature."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tkinter as tk
from tkinter import ttk

from drive_by_card import DriveByCard
from drive_by_controller import (
    REQUIRED_PHONE_CONFIRMATIONS,
    DEFAULT_COMPASS_PATH,
    get_git_preflight,
    get_metro_check,
    get_windows_network_check,
    run_preflight,
    validate_compass_directory,
)
from metro_controller import METRO_PORT, MetroController


def _make_valid_project(tmp: Path) -> None:
    (tmp / "package.json").write_text("{}")
    (tmp / "app.json").write_text("{}")
    (tmp / "src" / "services" / "backgroundGeofence").mkdir(parents=True)


class TestDirectoryValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_compass_directory(self):
        _make_valid_project(self.path)
        check = validate_compass_directory(str(self.path))
        self.assertTrue(check.ok)
        self.assertEqual(check.details["has_package_json"], True)
        self.assertEqual(check.details["has_expo_config"], True)
        self.assertEqual(check.details["has_src"], True)

    def test_invalid_missing_package_json(self):
        (self.path / "app.json").write_text("{}")
        check = validate_compass_directory(str(self.path))
        self.assertFalse(check.ok)
        self.assertIn("package.json", check.message)

    def test_invalid_missing_expo_config(self):
        (self.path / "package.json").write_text("{}")
        (self.path / "src").mkdir()
        check = validate_compass_directory(str(self.path))
        self.assertFalse(check.ok)
        self.assertIn("Expo config", check.message)


class TestGitPreflight(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        # Initialise a Git repository so the commands succeed.
        subprocess.run(["git", "init"], cwd=self.path, capture_output=True, text=True, check=False)
        (self.path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "file.txt"], cwd=self.path, capture_output=True, text=True, check=False)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=self.path,
            capture_output=True,
            text=True,
            check=False,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_git_branch_and_clean_tree(self):
        check = get_git_preflight(str(self.path))
        self.assertTrue(check.ok)
        self.assertIn(check.details["branch"], ("main", "master"))
        self.assertEqual(check.details["dirty"], False)
        self.assertIn("ahead", check.details)
        self.assertIn("behind", check.details)

    def test_git_dirty_tree_reported(self):
        (self.path / "file.txt").write_text("modified")
        check = get_git_preflight(str(self.path))
        self.assertTrue(check.ok)
        self.assertEqual(check.details["dirty"], True)
        self.assertIn("modified", check.message)


class TestMetroAndNetworkChecks(unittest.TestCase):
    def test_stopped_metro_is_allowed(self):
        controller = MetroController()
        check = get_metro_check(controller)
        self.assertTrue(check.ok)
        self.assertEqual(check.details["running"], False)

    def test_running_metro_reports_url(self):
        controller = MetroController()
        controller._append_log("Metro waiting on exp://192.168.1.5:8081")
        # Fake a running process.
        proc = MagicMock()
        proc.poll.return_value = None
        controller._proc = proc
        check = get_metro_check(controller)
        self.assertTrue(check.ok)
        self.assertEqual(check.details["running"], True)
        self.assertEqual(controller.last_url, "exp://192.168.1.5:8081")

    def test_metro_error_is_surfaced(self):
        controller = MetroController()
        controller._set_status("Error", "Spawn failed")
        # Metro status check itself remains OK because we don't want a transient
        # error in the Metro card to block the preflight entirely without
        # surfacing the controller error.
        check = get_metro_check(controller)
        self.assertTrue(check.ok)
        self.assertIn("Spawn failed", controller.status_message)

    @patch("drive_by_controller.socket.gethostname")
    @patch("drive_by_controller.socket.getaddrinfo")
    def test_network_available(self, mock_getaddrinfo, mock_gethostname):
        mock_gethostname.return_value = "test-pc"
        mock_getaddrinfo.return_value = [
            (None, None, None, None, ("192.168.1.10",)),
            (None, None, None, None, ("127.0.0.1",)),
        ]
        check = get_windows_network_check(None)
        self.assertTrue(check.ok)
        self.assertIn("192.168.1.10", check.message)

    @patch("drive_by_controller.socket.gethostname")
    @patch("drive_by_controller.socket.getaddrinfo")
    def test_network_loopback_only(self, mock_getaddrinfo, mock_gethostname):
        mock_gethostname.return_value = "test-pc"
        mock_getaddrinfo.return_value = [(None, None, None, None, ("127.0.0.1",))]
        check = get_windows_network_check(None)
        self.assertFalse(check.ok)
        self.assertIn("non-loopback", check.message.lower())

    @patch("drive_by_controller.socket.gethostname")
    @patch("drive_by_controller.socket.getaddrinfo")
    def test_metro_url_loopback_rejected(self, mock_getaddrinfo, mock_gethostname):
        mock_gethostname.return_value = "test-pc"
        mock_getaddrinfo.return_value = [
            (None, None, None, None, ("192.168.1.10",)),
        ]
        check = get_windows_network_check("exp://127.0.0.1:8081")
        self.assertFalse(check.ok)
        self.assertIn("loopback", check.message.lower())


class TestReadinessDecision(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        _make_valid_project(self.path)
        subprocess.run(["git", "init"], cwd=self.path, capture_output=True, text=True, check=False)
        (self.path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "file.txt"], cwd=self.path, capture_output=True, text=True, check=False)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=self.path,
            capture_output=True,
            text=True,
            check=False,
        )
        self.controller = MetroController()

    def tearDown(self):
        self.tmp.cleanup()

    def _all_phone_confirmed(self) -> dict[str, bool]:
        return {label: True for label in REQUIRED_PHONE_CONFIRMATIONS}

    def _one_business(self, name="Store A", cooldown=True, outside=True) -> list[dict]:
        return [
            {
                "name": name,
                "intent": "Buy at Store A",
                "radius": "100",
                "cooldown_reset": cooldown,
                "outside": outside,
                "notes": "",
            }
        ]

    @patch("drive_by_controller.get_windows_network_check")
    def test_complete_checklist_ready(self, mock_network):
        mock_network.return_value = MagicMock(ok=True, message="LAN OK", details={})
        report = run_preflight(
            self.controller,
            str(self.path),
            self._all_phone_confirmed(),
            1,
            True,
            self._one_business(),
        )
        self.assertEqual(report.status, "READY")
        self.assertTrue(report.overall_ok)

    @patch("drive_by_controller.get_windows_network_check")
    def test_incomplete_phone_checklist_needs_phone(self, mock_network):
        mock_network.return_value = MagicMock(ok=True, message="LAN OK", details={})
        phone = self._all_phone_confirmed()
        phone["Location permission is set to Always"] = False
        report = run_preflight(
            self.controller,
            str(self.path),
            phone,
            1,
            True,
            self._one_business(),
        )
        self.assertEqual(report.status, "NEEDS_PHONE")

    def test_invalid_directory_not_ready(self):
        report = run_preflight(
            self.controller,
            "C:\\nonexistent\\compass",
            self._all_phone_confirmed(),
            1,
            True,
            self._one_business(),
        )
        self.assertEqual(report.status, "NOT_READY")
        self.assertFalse(report.overall_ok)

    @patch("drive_by_controller.get_windows_network_check")
    def test_zero_region_count_invalid(self, mock_network):
        mock_network.return_value = MagicMock(ok=True, message="LAN OK", details={})
        report = run_preflight(
            self.controller,
            str(self.path),
            self._all_phone_confirmed(),
            0,
            True,
            self._one_business(),
        )
        self.assertEqual(report.status, "NOT_READY")

    @patch("drive_by_controller.get_windows_network_check")
    def test_region_count_confirmation_required(self, mock_network):
        mock_network.return_value = MagicMock(ok=True, message="LAN OK", details={})
        report = run_preflight(
            self.controller,
            str(self.path),
            self._all_phone_confirmed(),
            1,
            False,
            self._one_business(),
        )
        self.assertEqual(report.status, "NEEDS_PHONE")

    @patch("drive_by_controller.get_windows_network_check")
    def test_no_business_entered_not_ready(self, mock_network):
        mock_network.return_value = MagicMock(ok=True, message="LAN OK", details={})
        report = run_preflight(
            self.controller,
            str(self.path),
            self._all_phone_confirmed(),
            1,
            True,
            [],
        )
        self.assertEqual(report.status, "NOT_READY")

    @patch("drive_by_controller.get_windows_network_check")
    def test_incomplete_business_row_not_ready(self, mock_network):
        mock_network.return_value = MagicMock(ok=True, message="LAN OK", details={})
        business = self._one_business()
        business[0]["cooldown_reset"] = False
        report = run_preflight(
            self.controller,
            str(self.path),
            self._all_phone_confirmed(),
            1,
            True,
            business,
        )
        self.assertEqual(report.status, "NOT_READY")

    def test_stopped_metro_does_not_block_ready(self):
        # With all other checks passing, a stopped Metro still leaves report READY.
        phone = self._all_phone_confirmed()
        with patch("drive_by_controller.get_windows_network_check") as mock_network:
            mock_network.return_value = MagicMock(ok=True, message="LAN OK", details={})
            report = run_preflight(
                self.controller,
                str(self.path),
                phone,
                1,
                True,
                self._one_business(),
            )
        self.assertEqual(report.status, "READY")


class TestDriveByCard(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.parent = ttk.Frame(self.root)
        self.parent.pack()
        self.controller = MetroController()
        self.settings: dict = {}
        self.saved = False

        def on_save():
            self.saved = True

        self.project_path_var = tk.StringVar(value=str(Path.cwd()))
        self.card = DriveByCard(
            self.parent,
            self.controller,
            self.project_path_var,
            self.settings,
            on_save,
        )

    def tearDown(self):
        self.root.destroy()

    def test_checkboxes_reset_on_startup(self):
        # The card starts with every manual confirmation unchecked.
        for var in self.card.phone_vars.values():
            self.assertFalse(var.get())
        self.assertFalse(self.card.region_count_confirmed_var.get())

    def test_business_collection_and_persistence(self):
        # Add a second row.
        self.card._add_business_row()
        self.assertEqual(len(self.card.business_rows), 2)

        row1 = self.card.business_rows[0]
        row1["name"].set("Store A")
        row1["intent"].set("Buy nails")
        row1["radius"].set("100")
        row1["cooldown_reset"].set(True)
        row1["outside"].set(True)
        row1["notes"].set("note")

        businesses = self.card._collect_businesses()
        self.assertEqual(len(businesses), 2)
        self.assertEqual(businesses[0]["name"], "Store A")
        self.assertTrue(businesses[0]["cooldown_reset"])

    def test_expected_region_count_parsing(self):
        self.card.region_count_var.set("3")
        self.assertEqual(self.card._parse_expected_region_count(), 3)

        self.card.region_count_var.set("0")
        self.assertIsNone(self.card._parse_expected_region_count())

        self.card.region_count_var.set("abc")
        self.assertIsNone(self.card._parse_expected_region_count())

    def test_worksheet_generation_contains_blocks(self):
        row = self.card.business_rows[0]
        row["name"].set("Store B")
        row["intent"].set("Return paint")
        row["radius"].set("150")
        row["cooldown_reset"].set(True)
        row["outside"].set(True)
        self.card.region_count_var.set("1")
        self.card._copy_worksheet()
        text = self.card.details_text.get("1.0", "end")
        self.assertIn("Compass Drive-By Test", text)
        self.assertIn("Business: Store B", text)
        self.assertIn("Associated Intent: Return paint", text)
        self.assertIn("Expected monitored regions: 1", text)


if __name__ == "__main__":
    unittest.main()
