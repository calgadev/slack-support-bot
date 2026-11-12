"""Request-level observability helpers: user id hashing and the per-request record."""

from __future__ import annotations

import hashlib
import hmac

from support_bot.orchestrator import Answer
from support_bot.storage.db import RequestRecord


def hash_user_id(user_id: str, salt: str) -> str:
    """Pseudonymize a Slack user id for logs and metrics (keyed hash, truncated)."""
    return hmac.new(salt.encode(), user_id.encode(), hashlib.sha256).hexdigest()[:16]


def build_request_record(
    *,
    request_id: str,
    user_hash: str,
    channel_id: str,
    lang: str,
    latency_ms: int,
    outcome: str,
    answer: Answer | None,
    error: str | None,
) -> RequestRecord:
    if answer is None:
        return RequestRecord(
            id=request_id,
            user_hash=user_hash,
            channel_id=channel_id,
            lang=lang,
            outcome=outcome,
            latency_ms=latency_ms,
            error=error,
        )
    return RequestRecord(
        id=request_id,
        user_hash=user_hash,
        channel_id=channel_id,
        lang=lang,
        outcome=outcome,
        latency_ms=latency_ms,
        model=answer.model,
        input_tokens=answer.input_tokens,
        output_tokens=answer.output_tokens,
        llm_calls=answer.llm_calls,
        retrieved=[{"id": c.id, "source": c.source, "score": c.score} for c in answer.retrieved],
        tool_calls=[
            {"name": call.name, "args": call.args, "result": call.result}
            for call in answer.tool_calls
        ],
        error=error,
    )
