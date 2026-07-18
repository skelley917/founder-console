"""Automatic preflight checks for the Compass drive-by test readiness card."""

from __future__ import annotations

import re
import socket
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from metro_controller import METRO_PORT, MetroController

DEFAULT_COMPASS_PATH = r"C:\Users\shawn\CascadeProjects\project-compass"

REQUIRED_PHONE_CONFIRMATIONS = [
    "Compass development build is installed",
    "Compass was opened successfully after the latest build/code update",
    "Location permission is set to Always",
    "Precise Location is On",
    "Notifications are Allowed",
    "Background Readiness says Ready",
    "Native geofencing task says Registered",
    "Persisted monitored-region count matches the intended businesses",
    "Each intended business has coordinates and a radius",
    "Execute Reconciliation completed successfully",
    "Cooldowns were reset for the businesses being tested",
    "Test Intents are Active or Captured",
    "Compass will remain backgrounded and will not be force-closed",
    "Test starts from outside the monitored regions",
]


@dataclass
class DriveByCheck:
    name: str
    ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DriveByReport:
    timestamp: Optional[str]
    overall_ok: bool
    status: str  # 'READY', 'NEEDS_PHONE', 'NOT_READY'
    checks: list[DriveByCheck]
    metro_status: str
    metro_owned: bool
    metro_url: Optional[str]
    port_occupied: bool
    controller_error: Optional[str]


def _run_git_command(args: list[str], cwd: str, timeout: int = 5) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as exc:
        return False, str(exc)


def get_git_preflight(path: str) -> DriveByCheck:
    details: dict[str, Any] = {}
    if not Path(path).is_dir():
        return DriveByCheck("Git working-tree status", False, "Project path is not a directory", details)

    ok, branch = _run_git_command(["git", "branch", "--show-current"], path)
    if not ok or not branch:
        return DriveByCheck("Git working-tree status", False, "Unable to determine Git branch", details)

    details["branch"] = branch

    ok, porcelain = _run_git_command(["git", "status", "--porcelain"], path)
    dirty = bool(porcelain)
    details["dirty"] = dirty

    ok, latest = _run_git_command(
        ["git", "log", "-1", "--pretty=format:%h %s"], path
    )
    details["short_commit"] = latest.split()[0] if latest else "—"
    details["latest_message"] = latest

    ahead = "0"
    behind = "0"
    ok, ab = _run_git_command(
        ["git", "rev-list", "--left-right", "--count", "origin/main...main"], path
    )
    if ok:
        parts = ab.split()
        if len(parts) == 2:
            behind, ahead = parts
    details["ahead"] = ahead
    details["behind"] = behind

    message = f"{branch} | {details['short_commit']} | ahead {ahead}, behind {behind}"
    if dirty:
        message += " | working tree modified"
    return DriveByCheck("Git working-tree status", True, message, details)


def validate_compass_directory(path: str) -> DriveByCheck:
    details: dict[str, Any] = {"path": path}
    root = Path(path)
    if not root.exists():
        return DriveByCheck("Project Compass path", False, f"Path does not exist: {path}", details)
    if not root.is_dir():
        return DriveByCheck("Project Compass path", False, f"Path is not a directory: {path}", details)

    has_package = (root / "package.json").is_file()
    details["has_package_json"] = has_package

    has_expo_config = (
        (root / "app.json").is_file()
        or (root / "app.config.js").is_file()
        or (root / "app.config.ts").is_file()
    )
    details["has_expo_config"] = has_expo_config

    has_src = (root / "src").is_dir()
    details["has_src"] = has_src

    has_geofence_service = (root / "src" / "services" / "backgroundGeofence").is_dir()
    details["has_geofence_service"] = has_geofence_service

    if not has_package:
        return DriveByCheck("Project Compass path", False, "Missing package.json", details)
    if not has_expo_config:
        return DriveByCheck("Project Compass path", False, "Missing Expo config", details)
    if not has_src:
        return DriveByCheck("Project Compass path", False, "Missing src/ directory", details)

    return DriveByCheck(
        "Project Compass path",
        True,
        f"Valid Expo project ({'has geofence service' if has_geofence_service else 'has src'})",
        details,
    )


def get_windows_network_check(metro_url: Optional[str]) -> DriveByCheck:
    """Confirm an active non-loopback IPv4 address exists."""
    details: dict[str, Any] = {}
    try:
        hostname = socket.gethostname()
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_INET)
        ips = {info[4][0] for info in addr_info}
        non_loopback = {ip for ip in ips if not ip.startswith("127.")}
        details["hostname"] = hostname
        details["addresses"] = sorted(non_loopback)
    except Exception as exc:
        return DriveByCheck("Windows network availability", False, f"Could not enumerate addresses: {exc}", details)

    if not non_loopback:
        return DriveByCheck("Windows network availability", False, "No active non-loopback IPv4 address found", details)

    metro_host_loopback = False
    if metro_url:
        match = re.search(r"//([\w.]+):", metro_url)
        if match:
            host = match.group(1)
            details["metro_host"] = host
            metro_host_loopback = host.startswith("127.")

    if metro_host_loopback:
        return DriveByCheck(
            "Windows network availability",
            False,
            f"LAN IPs available, but Metro URL is loopback: {metro_url}",
            details,
        )

    return DriveByCheck(
        "Windows network availability",
        True,
        f"LAN address(es): {', '.join(non_loopback)}",
        details,
    )


def _is_port_occupied(port: int = METRO_PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        try:
            sock.connect(("127.0.0.1", port))
            return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False


def get_metro_check(controller: MetroController) -> DriveByCheck:
    running = controller.is_running
    owned = running
    port_occupied = _is_port_occupied(METRO_PORT)
    url = controller.last_url

    details = {
        "running": running,
        "owned": owned,
        "port_occupied": port_occupied,
        "url": url,
    }

    if running:
        message = f"Running (Mission Control owns PID)"
        if url:
            message += f" | URL: {url}"
    elif port_occupied:
        message = "Another process is using port 8081"
    else:
        message = "Stopped (Metro is optional for the physical drive test after bundle/regions prepared)"

    return DriveByCheck("Metro status", True, message, details)


def run_preflight(
    controller: MetroController,
    project_path: str,
    phone_confirmations: dict[str, bool],
    expected_region_count: Optional[int],
    region_count_confirmed: bool,
    businesses: list[dict[str, Any]],
) -> DriveByReport:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    path_check = validate_compass_directory(project_path)
    git_check = get_git_preflight(project_path)
    metro_check = get_metro_check(controller)
    network_check = get_windows_network_check(controller.last_url)

    controller_error: Optional[str] = None
    if controller.status == "Error":
        controller_error = controller.status_message

    checks = [path_check, git_check, metro_check, network_check]

    auto_ok = all(c.ok for c in checks)
    blocking_metro_error = controller.status == "Error" and controller.is_running is False

    all_phone_confirmed = all(phone_confirmations.get(k, False) for k in REQUIRED_PHONE_CONFIRMATIONS)

    valid_businesses = [b for b in businesses if b.get("name", "").strip()]
    businesses_present = len(valid_businesses) > 0
    businesses_complete = businesses_present and all(
        b.get("cooldown_reset", False) and b.get("outside", False)
        for b in valid_businesses
    )

    region_count_valid = (
        isinstance(expected_region_count, int)
        and expected_region_count > 0
    )
    region_count_ok = region_count_valid and region_count_confirmed

    config_ok = region_count_valid and businesses_present

    overall_ok = (
        auto_ok
        and not blocking_metro_error
        and all_phone_confirmed
        and region_count_ok
        and businesses_complete
    )

    if overall_ok:
        status = "READY"
    elif not auto_ok or blocking_metro_error or not config_ok or not businesses_complete:
        status = "NOT_READY"
    else:
        status = "NEEDS_PHONE"

    return DriveByReport(
        timestamp=timestamp,
        overall_ok=overall_ok,
        status=status,
        checks=checks,
        metro_status=controller.status,
        metro_owned=metro_check.details.get("owned", False),
        metro_url=controller.last_url,
        port_occupied=metro_check.details.get("port_occupied", False),
        controller_error=controller_error,
    )
