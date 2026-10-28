"""Small shared helpers: size formatting/parsing, ANSI styling, bars."""
from __future__ import annotations

import argparse
import re

_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]
_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KMGTP]?B?)\s*$", re.IGNORECASE)


def human_size(n: float) -> str:
    for unit in _UNITS:
        if abs(n) < 1024 or unit == _UNITS[-1]:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def parse_size(text: str) -> int:
    """Parse '500', '10KB', '1.5GB' into bytes (argparse-friendly)."""
    m = _SIZE_RE.match(text)
    if not m:
        raise argparse.ArgumentTypeError(f"invalid size: {text!r} (try 100MB)")
    number, unit = float(m.group(1)), m.group(2).upper().rstrip("B")
    power = "KMGTP".index(unit) + 1 if unit else 0
    return int(number * 1024**power)


def bar(fraction: float, width: int = 20) -> str:
    filled = max(0, min(width, round(fraction * width)))
    return "█" * filled + "░" * (width - filled)


class Style:
    """ANSI colors, disabled automatically when output is not a terminal."""

    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _wrap(self, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.enabled else s

    def bold(self, s): return self._wrap("1", s)
    def dim(self, s): return self._wrap("2", s)
    def red(self, s): return self._wrap("31", s)
    def yellow(self, s): return self._wrap("33", s)
    def green(self, s): return self._wrap("32", s)
    def cyan(self, s): return self._wrap("36", s)
