"""The "status" message: uptime, index size and request metrics from the last 24 hours."""

from __future__ import annotations

import time
from collections.abc import Callable

from support_bot.i18n import Lang
from support_bot.storage.db import Database

STATUS_WORDS = {"status", "/status", "status?"}


def is_status_request(text: str) -> bool:
    return text.strip().lower() in STATUS_WORDS


def format_duration(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


_LABELS: dict[Lang, dict[str, str]] = {
    "en": {
        "title": "Support Bot status",
        "uptime": "Uptime",
        "chunks": "Indexed chunks",
        "window": "Last 24 hours",
        "requests": "Requests",
        "errors": "Errors",
        "latency": "Average latency",
        "na": "n/a",
    },
    "pt": {
        "title": "Status do Support Bot",
        "uptime": "Tempo no ar",
        "chunks": "Chunks indexados",
        "window": "Últimas 24 horas",
        "requests": "Requisições",
        "errors": "Erros",
        "latency": "Latência média",
        "na": "n/d",
    },
}


class StatusService:
    def __init__(
        self,
        db: Database,
        chunk_count: Callable[[], int],
        started_at: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.db = db
        self.chunk_count = chunk_count
        self.started_at = started_at
        self.clock = clock

    def render(self, lang: Lang = "en") -> str:
        labels = _LABELS[lang]
        stats = self.db.request_stats(24 * 3600)
        try:
            chunks = str(self.chunk_count())
        except Exception:
            chunks = labels["na"]
        latency = (
            f"{stats.avg_latency_ms / 1000:.2f} s"
            if stats.avg_latency_ms is not None
            else labels["na"]
        )
        return "\n".join(
            [
                f"*{labels['title']}*",
                f"• {labels['uptime']}: {format_duration(self.clock() - self.started_at)}",
                f"• {labels['chunks']}: {chunks}",
                f"*{labels['window']}*",
                f"• {labels['requests']}: {stats.requests}",
                f"• {labels['errors']}: {stats.errors}",
                f"• {labels['latency']}: {latency}",
            ]
        )
