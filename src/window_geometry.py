"""Helpers for safe Mission Control window sizing and geometry persistence."""

from __future__ import annotations

import re
from typing import Optional, Tuple


def parse_geometry(geometry: str) -> Optional[Tuple[int, int, int, int]]:
    """Parse 'WxH+X+Y' into (width, height, x, y)."""
    if not geometry:
        return None
    match = re.fullmatch(r"(\d+)x(\d+)\+([\-+]?\d+)\+([\-+]?\d+)", geometry)
    if not match:
        return None
    return tuple(int(g) for g in match.groups())


def clamp_geometry(
    width: int,
    height: int,
    x: int,
    y: int,
    screen_width: int,
    screen_height: int,
    min_width: int = 640,
    min_height: int = 500,
) -> Tuple[int, int, int, int]:
    """Ensure a window geometry fits on the available screen and satisfies minima."""
    width = max(min_width, min(width, screen_width))
    height = max(min_height, min(height, screen_height))
    x = max(0, min(x, screen_width - width))
    y = max(0, min(y, screen_height - height))
    return width, height, x, y


def get_initial_geometry(
    screen_width: int,
    screen_height: int,
    saved_geometry: Optional[str] = None,
    default_ratio_width: float = 0.70,
    default_ratio_height: float = 0.75,
    max_height: int = 1000,
    min_width: int = 640,
    min_height: int = 500,
) -> Tuple[int, int, int, int]:
    """Choose a sensible initial window size/position based on the current screen.

    Restores the saved geometry only if it fits on the current screen; otherwise
    falls back to a centered default derived from screen dimensions.
    """
    if saved_geometry:
        parsed = parse_geometry(saved_geometry)
        if parsed:
            width, height, x, y = parsed
            if (
                width >= min_width
                and height >= min_height
                and x + width <= screen_width
                and y + height <= screen_height
                and x >= 0
                and y >= 0
            ):
                return width, height, x, y

    width = max(min_width, int(screen_width * default_ratio_width))
    height = max(min_height, min(int(screen_height * default_ratio_height), max_height))

    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 4)
    return width, height, x, y


def format_geometry(width: int, height: int, x: int, y: int) -> str:
    return f"{width}x{height}+{x}+{y}"
