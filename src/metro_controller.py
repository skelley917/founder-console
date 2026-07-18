"""Managed Metro process controller for Mission Control (Windows-only).

Provides start/stop/restart of ``npx expo start --dev-client --lan --clear`` for a
configurable Expo project directory, duplicate-start prevention, port 8081 conflict
checking, bounded log capture, and graceful + forced process-tree shutdown.
"""

from __future__ import annotations

import collections
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Deque, Optional

METRO_PORT = 8081
METRO_COMMAND = ["npx.cmd", "expo", "start", "--dev-client", "--lan", "--clear"]
MAX_LOG_LINES = 500
LOG_TAIL_LINES = 250
GRACEFUL_STOP_TIMEOUT_SECONDS = 10.0
FORCED_KILL_TIMEOUT_SECONDS = 5.0
URL_RE = re.compile(r"(exp://[\w\-.]+:[0-9]+|http://[\w\-.]+:[0-9]+|https://[\w\-.]+:[0-9]+)")


class MetroController:
    """Owns a single Metro child process and its captured output."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._status = "Stopped"
        self._status_message = "Metro is not running"
        self._last_url: Optional[str] = None
        self._exit_code: Optional[int] = None
        self._logs: Deque[str] = collections.deque(maxlen=MAX_LOG_LINES)
        self._lock = threading.Lock()
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self._listeners: list[Callable[[], None]] = []

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def status_message(self) -> str:
        with self._lock:
            return self._status_message

    @property
    def last_url(self) -> Optional[str]:
        with self._lock:
            return self._last_url

    @property
    def exit_code(self) -> Optional[int]:
        with self._lock:
            return self._exit_code

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    # -------------------------------------------------------------------------
    # Status helpers
    # -------------------------------------------------------------------------

    def _set_status(self, status: str, message: str) -> None:
        with self._lock:
            self._status = status
            self._status_message = message
        self._notify()

    def _notify(self) -> None:
        for listener in self._listeners:
            try:
                listener()
            except Exception:
                pass

    def add_listener(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    # -------------------------------------------------------------------------
    # Directory validation
    # -------------------------------------------------------------------------

    @staticmethod
    def validate_project_directory(path: str) -> tuple[bool, str]:
        """Return (ok, message) for a candidate Expo project directory."""
        root = Path(path)
        if not root.exists():
            return False, f"Directory does not exist: {path}"
        if not root.is_dir():
            return False, f"Path is not a directory: {path}"
        package_json = root / "package.json"
        if not package_json.is_file():
            return False, f"Missing package.json in {path}"
        has_expo_config = (
            (root / "app.json").is_file()
            or (root / "app.config.js").is_file()
            or (root / "app.config.ts").is_file()
        )
        if not has_expo_config:
            return False, f"Missing Expo config (app.json/app.config.*) in {path}"
        return True, "Valid Expo project directory"

    # -------------------------------------------------------------------------
    # Port check
    # -------------------------------------------------------------------------

    @staticmethod
    def is_port_in_use(port: int = METRO_PORT) -> bool:
        """Check whether something is listening on localhost:port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            try:
                sock.connect(("127.0.0.1", port))
                return True
            except (socket.timeout, ConnectionRefusedError, OSError):
                return False

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------

    def _append_log(self, line: str) -> None:
        stripped = line.rstrip()
        if not stripped:
            return
        with self._lock:
            self._logs.append(stripped)
            match = URL_RE.search(stripped)
            if match:
                self._last_url = match.group(1)
        self._notify()

    def get_logs(self, tail: int = LOG_TAIL_LINES) -> list[str]:
        with self._lock:
            return list(self._logs)[-tail:]

    def clear_logs(self) -> None:
        with self._lock:
            self._logs.clear()
        self._notify()

    # -------------------------------------------------------------------------
    # Process readers
    # -------------------------------------------------------------------------

    def _read_stream(self, stream) -> None:
        try:
            for raw in iter(stream.readline, b""):
                try:
                    line = raw.decode("utf-8", errors="replace")
                except Exception:
                    line = str(raw)
                self._append_log(line)
        except Exception as exc:
            self._append_log(f"[Mission Control] stream reader exited: {exc}")
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def _watchdog(self) -> None:
        """Wait for the process to exit and update status."""
        proc = self._proc
        if proc is None:
            return
        try:
            code = proc.wait()
        except Exception as exc:
            code = -1
            self._append_log(f"[Mission Control] watchdog error: {exc}")

        with self._lock:
            self._exit_code = code
            self._proc = None

        if code == 0:
            self._set_status("Stopped", "Metro exited normally")
        elif code == -1:
            self._set_status("Error", "Metro process disappeared unexpectedly")
        else:
            self._set_status("Error", f"Metro exited with code {code}")

    # -------------------------------------------------------------------------
    # Start / stop / restart
    # -------------------------------------------------------------------------

    def start(self, project_path: str) -> tuple[bool, str]:
        """Start Metro if it is not already owned by Mission Control."""
        if self.is_running:
            return False, f"Metro is already {self.status.lower()} (owned by Mission Control)."

        if self.is_port_in_use(METRO_PORT):
            return (
                False,
                f"Port {METRO_PORT} is already in use. Another Metro or process may be running.",
            )

        ok, message = self.validate_project_directory(project_path)
        if not ok:
            self._set_status("Error", message)
            return False, message

        self._set_status("Starting", "Starting Metro…")
        self._exit_code = None
        self._last_url = None

        env = os.environ.copy()
        for key in (
            "TCL_LIBRARY",
            "TK_LIBRARY",
            "_MEIPASS",
            "_PYI_APPLICATION_HOME_DIR",
            "PYTHONHOME",
        ):
            env.pop(key, None)

        try:
            proc = subprocess.Popen(
                METRO_COMMAND,
                cwd=project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        except Exception as exc:
            self._set_status("Error", f"Failed to start Metro: {exc}")
            return False, str(exc)

        with self._lock:
            self._proc = proc

        self._stdout_thread = threading.Thread(
            target=self._read_stream, args=(proc.stdout,), daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stream, args=(proc.stderr,), daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        self._watchdog_thread = threading.Thread(target=self._watchdog, daemon=True)
        self._watchdog_thread.start()

        if proc.poll() is None:
            self._set_status("Running", f"Metro running (PID {proc.pid})")
        self._append_log(f"[Mission Control] Started Metro in {project_path}")
        return True, "Metro started"

    def stop(self) -> tuple[bool, str]:
        """Gracefully stop Metro; force-kill the process tree if necessary."""
        proc = self._proc
        if proc is None:
            self._set_status("Stopped", "Metro is not running")
            return False, "Metro is not running"

        if proc.poll() is not None:
            self._set_status("Stopped", "Metro already exited")
            with self._lock:
                self._proc = None
            return False, "Metro already exited"

        self._set_status("Stopping", "Stopping Metro (graceful)…")
        self._append_log("[Mission Control] Requesting graceful shutdown…")

        try:
            os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
        except Exception as exc:
            self._append_log(f"[Mission Control] CTRL_BREAK failed: {exc}")

        deadline = time.monotonic() + GRACEFUL_STOP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            time.sleep(0.1)

        if proc.poll() is None:
            self._append_log("[Mission Control] Graceful shutdown timed out; forcing process tree…")
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    text=True,
                    timeout=FORCED_KILL_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                self._append_log(f"[Mission Control] taskkill failed: {exc}")

            final_deadline = time.monotonic() + FORCED_KILL_TIMEOUT_SECONDS
            while time.monotonic() < final_deadline:
                if proc.poll() is not None:
                    break
                time.sleep(0.1)

        if proc.poll() is None:
            self._set_status("Error", "Metro could not be stopped")
            return False, "Metro could not be stopped"

        self._set_status("Stopped", "Metro stopped")
        return True, "Metro stopped"

    def restart(self, project_path: str) -> tuple[bool, str]:
        """Stop the owned Metro process and start a fresh one."""
        if self.is_running:
            ok, message = self.stop()
            if not ok:
                return False, f"Restart failed during stop: {message}"
            # Brief yield so the port is released.
            for _ in range(20):
                if not self.is_running and not self.is_port_in_use(METRO_PORT):
                    break
                time.sleep(0.1)
        return self.start(project_path)
