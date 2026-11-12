"""Heartbeat file used by the Docker HEALTHCHECK (no HTTP server needed).

The bot writes the current UNIX time to the heartbeat file only while the Socket Mode
connection is active. ``python -m support_bot.health`` exits 0 if the file is fresh.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path


def write_heartbeat(path: Path, now: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(f"{now if now is not None else time.time():.3f}", encoding="utf-8")
    tmp.replace(path)


def heartbeat_age(path: Path, now: float | None = None) -> float | None:
    """Seconds since the last heartbeat, or None if missing/unreadable."""
    try:
        written = float(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return (now if now is not None else time.time()) - written


def is_healthy(path: Path, max_age_seconds: float, now: float | None = None) -> bool:
    age = heartbeat_age(path, now)
    return age is not None and age <= max_age_seconds


def main() -> int:
    # Import lazily so the check stays light and does not need Slack tokens.
    from support_bot.config import get_settings

    settings = get_settings()
    ok = is_healthy(settings.heartbeat_path, settings.heartbeat_max_age_seconds)
    print("healthy" if ok else "unhealthy")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
