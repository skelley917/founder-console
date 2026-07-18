"""Unit tests for Mission Control's MetroController.

Run from the repository root with:
    python -m pytest tests/test_metro_controller.py
or
    python -m unittest discover tests
"""

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

# Make the source modules importable.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from metro_controller import (
    FORCED_KILL_TIMEOUT_SECONDS,
    GRACEFUL_STOP_TIMEOUT_SECONDS,
    MAX_LOG_LINES,
    METRO_PORT,
    MetroController,
)


class FakeStream:
    """Iterable stream for subprocess stdout/stderr mocks."""

    def __init__(self, lines):
        self._lines = [line.encode("utf-8") for line in lines] + [b""]
        self._idx = 0

    def readline(self):
        line = self._lines[self._idx]
        self._idx += 1
        return line

    def close(self):
        pass


class FakeProcess:
    """Subprocess mock supporting poll/wait/kill and stream readers."""

    def __init__(self, pid=12345, exit_code=None, stdout_lines=None, stderr_lines=None):
        self.pid = pid
        self._exit_code = exit_code
        self._finished = exit_code is not None
        self.stdout = FakeStream(stdout_lines or [])
        self.stderr = FakeStream(stderr_lines or [])
        self.killed = False
        self.terminated = False

    def poll(self):
        if self._finished:
            return self._exit_code
        return None

    def wait(self, timeout=None):
        # Simulate a process that exits when the test asks for it.
        deadline = time.monotonic() + (timeout or 1.0)
        while not self._finished and time.monotonic() < deadline:
            time.sleep(0.01)
        if not self._finished:
            raise subprocess.TimeoutExpired([], timeout)
        return self._exit_code

    def terminate(self):
        self.terminated = True
        self._exit_code = -1
        self._finished = True

    def kill(self):
        self.killed = True
        self._exit_code = -9
        self._finished = True

    def finish(self, code):
        self._exit_code = code
        self._finished = True


class TestDirectoryValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_project_directory(self):
        (self.root / "package.json").write_text("{}")
        (self.root / "app.json").write_text("{}")
        ok, message = MetroController.validate_project_directory(str(self.root))
        self.assertTrue(ok)
        self.assertIn("Valid", message)

    def test_missing_package_json(self):
        (self.root / "app.json").write_text("{}")
        ok, message = MetroController.validate_project_directory(str(self.root))
        self.assertFalse(ok)
        self.assertIn("package.json", message)

    def test_missing_expo_config(self):
        (self.root / "package.json").write_text("{}")
        ok, message = MetroController.validate_project_directory(str(self.root))
        self.assertFalse(ok)
        self.assertIn("Missing Expo config", message)

    def test_nonexistent_directory(self):
        ok, message = MetroController.validate_project_directory("C:\\nonexistent\\path")
        self.assertFalse(ok)
        self.assertIn("does not exist", message)


class TestPortCheck(unittest.TestCase):
    @patch("metro_controller.socket.socket")
    def test_port_in_use(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = lambda _: None
        mock_socket_cls.return_value.__enter__.return_value = mock_sock
        self.assertTrue(MetroController.is_port_in_use(METRO_PORT))

    @patch("metro_controller.socket.socket")
    def test_port_free(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = ConnectionRefusedError()
        mock_socket_cls.return_value.__enter__.return_value = mock_sock
        self.assertFalse(MetroController.is_port_in_use(METRO_PORT))


class TestStartAndStop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        (self.project / "package.json").write_text("{}")
        (self.project / "app.config.js").write_text("module.exports = {};")
        self.controller = MetroController()
        self._open_patches = []

    def tearDown(self):
        # Give any reader threads a moment to finish before tearing down temp dirs.
        time.sleep(0.05)
        for p in self._open_patches:
            p.stop()
        self.tmp.cleanup()

    def _patch_subprocess_popen(self, proc):
        popen_patch = patch("metro_controller.subprocess.Popen", return_value=proc)
        self._open_patches.append(popen_patch)
        return popen_patch.start()

    def _patch_port_free(self):
        port_patch = patch("metro_controller.MetroController.is_port_in_use", return_value=False)
        self._open_patches.append(port_patch)
        return port_patch.start()

    def test_start_while_stopped(self):
        proc = FakeProcess(stdout_lines=["Metro waiting on exp://192.168.1.2:8081"])
        self._patch_subprocess_popen(proc)
        self._patch_port_free()

        ok, message = self.controller.start(str(self.project))
        self.assertTrue(ok)
        self.assertEqual(self.controller.status, "Running")
        self.assertTrue(self.controller.is_running)
        self.assertEqual(self.controller.last_url, "exp://192.168.1.2:8081")

    def test_duplicate_start_prevention(self):
        proc = FakeProcess()
        self._patch_subprocess_popen(proc)
        self._patch_port_free()

        ok1, _ = self.controller.start(str(self.project))
        self.assertTrue(ok1)

        ok2, message = self.controller.start(str(self.project))
        self.assertFalse(ok2)
        self.assertIn("already", message.lower())

    def test_occupied_port_prevents_start(self):
        self._patch_subprocess_popen(FakeProcess())
        with patch("metro_controller.MetroController.is_port_in_use", return_value=True):
            ok, message = self.controller.start(str(self.project))
        self.assertFalse(ok)
        self.assertIn("Port 8081", message)
        self.assertEqual(self.controller.status, "Stopped")

    def test_invalid_directory_prevents_start(self):
        self._patch_subprocess_popen(FakeProcess())
        self._patch_port_free()
        ok, message = self.controller.start("C:\\not_a_real_project")
        self.assertFalse(ok)
        self.assertIn("does not exist", message)
        self.assertEqual(self.controller.status, "Error")

    def test_graceful_stop(self):
        proc = FakeProcess()
        self._patch_subprocess_popen(proc)
        self._patch_port_free()

        self.controller.start(str(self.project))
        self.assertTrue(self.controller.is_running)

        with patch("metro_controller.os.kill") as mock_kill:
            # Simulate the process exiting gracefully right after CTRL_BREAK.
            def finish_on_kill(pid, sig):
                self.assertEqual(pid, proc.pid)
                proc.finish(0)

            mock_kill.side_effect = finish_on_kill
            ok, message = self.controller.stop()

        self.assertTrue(ok)
        self.assertEqual(self.controller.status, "Stopped")
        self.assertFalse(self.controller.is_running)

    def test_forced_stop_after_graceful_timeout(self):
        proc = FakeProcess()
        self._patch_subprocess_popen(proc)
        self._patch_port_free()

        self.controller.start(str(self.project))

        with patch("metro_controller.os.kill") as mock_kill:
            # CTRL_BREAK does nothing; process ignores it.
            mock_kill.side_effect = lambda _pid, _sig: None

            def fake_taskkill(*args, **kwargs):
                proc.kill()

            with patch("metro_controller.subprocess.run", side_effect=fake_taskkill) as mock_run:
                ok, message = self.controller.stop()

        self.assertTrue(ok)
        self.assertEqual(self.controller.status, "Stopped")
        # taskkill should have been invoked.
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("taskkill", args)

    def test_restart_stops_and_starts_fresh(self):
        proc1 = FakeProcess(pid=100)
        mock_popen = self._patch_subprocess_popen(proc1)
        self._patch_port_free()

        self.controller.start(str(self.project))
        self.assertEqual(proc1.pid, 100)

        proc2 = FakeProcess(pid=200)
        mock_popen.return_value = proc2
        # Finish the old process when stop requests it.
        with patch("metro_controller.os.kill") as mock_kill:
            mock_kill.side_effect = lambda _pid, _sig: proc1.finish(0)
            ok, _ = self.controller.restart(str(self.project))

        self.assertTrue(ok)
        self.assertEqual(self.controller.status, "Running")
        self.assertEqual(self.controller.is_running, True)

    def test_unexpected_process_exit_updates_status(self):
        proc = FakeProcess(exit_code=42)
        self._patch_subprocess_popen(proc)
        self._patch_port_free()

        ok, _ = self.controller.start(str(self.project))
        self.assertTrue(ok)
        # Wait for the watchdog to observe the pre-set exit code.
        deadline = time.monotonic() + 3.0
        while self.controller.status not in ("Stopped", "Error") and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.controller.status, "Error")
        self.assertEqual(self.controller.exit_code, 42)


class TestLogRetention(unittest.TestCase):
    def test_logs_are_bounded(self):
        controller = MetroController()
        for i in range(MAX_LOG_LINES + 100):
            controller._append_log(f"line {i}")
        self.assertLessEqual(len(controller.get_logs()), MAX_LOG_LINES)
        # Most recent entries should be retained.
        self.assertIn("line {}".format(MAX_LOG_LINES + 99), controller.get_logs()[-1])

    def test_url_extraction(self):
        controller = MetroController()
        controller._append_log("Metro is waiting on exp://192.168.1.5:8081")
        self.assertEqual(controller.last_url, "exp://192.168.1.5:8081")


class TestStatusTransitions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        (self.project / "package.json").write_text("{}")
        (self.project / "app.json").write_text("{}")
        self.controller = MetroController()

    def tearDown(self):
        time.sleep(0.05)
        self.tmp.cleanup()

    def test_status_starts_as_stopped(self):
        self.assertEqual(self.controller.status, "Stopped")
        self.assertFalse(self.controller.is_running)

    @patch("metro_controller.subprocess.Popen")
    @patch("metro_controller.MetroController.is_port_in_use", return_value=False)
    def test_starting_then_running_status(self, _port_mock, popen_mock):
        proc = FakeProcess()
        popen_mock.return_value = proc
        self.controller.start(str(self.project))
        # Status may briefly be Starting but settles to Running.
        self.assertEqual(self.controller.status, "Running")

    @patch("metro_controller.subprocess.Popen")
    @patch("metro_controller.MetroController.is_port_in_use", return_value=False)
    def test_stopping_status(self, _port_mock, popen_mock):
        proc = FakeProcess()
        popen_mock.return_value = proc
        self.controller.start(str(self.project))

        with patch("metro_controller.os.kill") as mock_kill:
            mock_kill.side_effect = lambda _pid, _sig: proc.finish(0)
            self.controller.stop()

        self.assertEqual(self.controller.status, "Stopped")


if __name__ == "__main__":
    unittest.main()
