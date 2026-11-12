"""Thin wrapper around the google-genai SDK with timeouts, retries and typed results.

Only this module talks to the Gemini API. The rest of the code depends on the
``LLMClient`` protocol so tests can use an in-memory fake.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from support_bot.logging_setup import get_logger

log = get_logger(__name__)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def _transport_errors() -> tuple[type[BaseException], ...]:
    """Network errors from httpx and from httpx2.

    google-genai uses httpx2 (a fork with its own import namespace) when it is installed,
    and its exceptions are not subclasses of the httpx ones, so both must be listed.
    """
    errors: list[type[BaseException]] = [httpx.TimeoutException, httpx.TransportError]
    try:
        import httpx2

        errors += [httpx2.TimeoutException, httpx2.TransportError]
    except ImportError:  # pragma: no cover - depends on the installed SDK extras
        pass
    return tuple(errors)


TRANSPORT_ERRORS = _transport_errors()


class LLMError(Exception):
    """Raised when the LLM call fails after all retries. Safe to show a generic message.

    ``quota_exhausted`` is True for a daily quota (retrying today will not help) and
    ``retry_after`` holds the server's suggested delay in seconds, when it sent one.
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status: int | None = None,
        quota_exhausted: bool = False,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.status = status
        self.quota_exhausted = quota_exhausted
        self.retry_after = retry_after


@dataclass(frozen=True)
class QuotaInfo:
    """What a 429 RESOURCE_EXHAUSTED response says about the exceeded quota."""

    retry_delay: float | None
    """Seconds from ``google.rpc.RetryInfo.retryDelay`` (e.g. "37s"), if present."""
    daily: bool
    """True when a violated quota is per day (e.g. GenerateRequestsPerDay...)."""
    quota_ids: tuple[str, ...] = ()


_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)s\s*$")


def _parse_duration(value: Any) -> float | None:
    """Parse a protobuf Duration string such as "37s" or "1.5s"."""
    match = _DURATION.match(str(value or ""))
    return float(match.group(1)) if match else None


def parse_quota_error(exc: genai_errors.APIError) -> QuotaInfo | None:
    """Read RetryInfo and QuotaFailure details from a 429 error. None for other errors."""
    if exc.code != 429:
        return None
    body = exc.details if isinstance(exc.details, dict) else {}
    error = body.get("error", body)
    details = error.get("details", []) if isinstance(error, dict) else []
    retry_delay: float | None = None
    quota_ids: list[str] = []
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        kind = str(detail.get("@type", ""))
        if kind.endswith("google.rpc.RetryInfo"):
            retry_delay = _parse_duration(detail.get("retryDelay"))
        elif kind.endswith("google.rpc.QuotaFailure"):
            for violation in detail.get("violations", []) or []:
                if isinstance(violation, dict) and violation.get("quotaId"):
                    quota_ids.append(str(violation["quotaId"]))
    daily = any("perday" in q.lower() for q in quota_ids)
    return QuotaInfo(retry_delay=retry_delay, daily=daily, quota_ids=tuple(quota_ids))


@dataclass(frozen=True)
class FunctionCall:
    name: str
    args: dict[str, Any]
    id: str | None = None


@dataclass
class LLMResponse:
    text: str
    function_calls: list[FunctionCall]
    content: types.Content | None
    """The model turn exactly as returned; must be sent back unchanged (thought signatures)."""
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    model: str

    def generate(
        self,
        contents: Sequence[types.Content],
        *,
        system_instruction: str,
        tools: Sequence[types.Tool] | None = None,
        force_tool: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed already-formatted texts (see ``support_bot.rag.embeddings``)."""
        ...


def _is_retryable(exc: BaseException, max_retry_delay: float = float("inf")) -> bool:
    """Retry transient errors, except quotas that will not recover soon.

    A 429 is not retried when the daily quota is exhausted, or when the server asks us
    to wait longer than ``max_retry_delay`` (a user in Slack should not wait that long).
    """
    if isinstance(exc, genai_errors.APIError):
        quota = parse_quota_error(exc)
        if quota is not None:
            if quota.daily:
                return False
            if quota.retry_delay is not None and quota.retry_delay > max_retry_delay:
                return False
        return exc.code in RETRYABLE_STATUS
    return isinstance(exc, TRANSPORT_ERRORS)


def _to_llm_error(exc: genai_errors.APIError, what: str, max_retry_delay: float) -> LLMError:
    quota = parse_quota_error(exc)
    return LLMError(
        f"Gemini {what} error {exc.code}: {_api_message(exc)}",
        retryable=_is_retryable(exc, max_retry_delay),
        status=exc.code,
        quota_exhausted=bool(quota and quota.daily),
        retry_after=quota.retry_delay if quota else None,
    )


def _api_message(exc: genai_errors.APIError) -> str:
    """Short, single-line API error message for logs and the requests table."""
    return " ".join(str(exc.message or exc.status or "").split())[:300]


def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    sleep = state.next_action.sleep if state.next_action else None
    log.warning(
        "llm_retry",
        attempt=state.attempt_number,
        sleep_seconds=round(sleep, 2) if sleep is not None else None,
        error_type=type(exc).__name__ if exc else None,
        error=str(exc)[:300] if exc else None,
    )


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        embedding_model: str,
        embedding_dim: int,
        timeout_seconds: float,
        max_attempts: int,
        max_output_tokens: int = 1024,
        retry_initial_wait: float = 1.0,
        max_retry_delay: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self.embedding_model = embedding_model
        self.embedding_dim = embedding_dim
        self.max_output_tokens = max_output_tokens
        # SDK timeouts are in milliseconds. Retries are handled by tenacity below.
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )
        self.max_retry_delay = max_retry_delay
        backoff = wait_exponential_jitter(
            initial=retry_initial_wait, max=10, jitter=retry_initial_wait
        )

        def wait(state: RetryCallState) -> float:
            # Honor the server's RetryInfo delay on 429s; otherwise exponential backoff.
            exc = state.outcome.exception() if state.outcome else None
            if isinstance(exc, genai_errors.APIError):
                quota = parse_quota_error(exc)
                if quota is not None and quota.retry_delay is not None:
                    return quota.retry_delay
            return backoff(state)

        self._retry = retry(
            reraise=True,
            stop=stop_after_attempt(max_attempts),
            wait=wait,
            retry=retry_if_exception(lambda e: _is_retryable(e, self.max_retry_delay)),
            before_sleep=_log_retry,
            sleep=sleep,
        )

    def generate(
        self,
        contents: Sequence[types.Content],
        *,
        system_instruction: str,
        tools: Sequence[types.Tool] | None = None,
        force_tool: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Generate a reply.

        ``force_tool`` makes the model call one of the tools (mode ANY). ``json_schema``
        requests structured JSON output (used by the eval judge).
        """
        tool_config = None
        if tools and force_tool:
            tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=types.FunctionCallingConfigMode.ANY
                )
            )
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=list(tools) if tools else None,
            tool_config=tool_config,
            response_mime_type="application/json" if json_schema else None,
            response_json_schema=json_schema,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=self.max_output_tokens,
        )
        try:
            response = self._retry(self._client.models.generate_content)(
                model=self.model, contents=list(contents), config=config
            )
        except genai_errors.APIError as exc:
            raise _to_llm_error(exc, "API", self.max_retry_delay) from exc
        except TRANSPORT_ERRORS as exc:
            raise LLMError(f"Gemini transport error: {type(exc).__name__}", retryable=True) from exc
        return _to_llm_response(response, self.model)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        # One Content per text so each gets its own embedding (parts in one Content are pooled).
        contents = [types.Content(parts=[types.Part.from_text(text=t)]) for t in texts]
        config = types.EmbedContentConfig(output_dimensionality=self.embedding_dim)
        try:
            result = self._retry(self._client.models.embed_content)(
                model=self.embedding_model, contents=contents, config=config
            )
        except genai_errors.APIError as exc:
            raise _to_llm_error(exc, "embedding", self.max_retry_delay) from exc
        except TRANSPORT_ERRORS as exc:
            raise LLMError(f"Gemini transport error: {type(exc).__name__}", retryable=True) from exc
        vectors = [list(e.values or []) for e in (result.embeddings or [])]
        if len(vectors) != len(texts):
            raise LLMError(f"Expected {len(texts)} embeddings, got {len(vectors)}")
        return vectors


def _to_llm_response(response: types.GenerateContentResponse, model: str) -> LLMResponse:
    candidate = response.candidates[0] if response.candidates else None
    content = candidate.content if candidate else None
    text_parts: list[str] = []
    calls: list[FunctionCall] = []
    for part in (content.parts or []) if content else []:
        if part.function_call is not None:
            fc = part.function_call
            calls.append(FunctionCall(name=fc.name or "", args=dict(fc.args or {}), id=fc.id))
        elif part.text and not part.thought:
            text_parts.append(part.text)
    usage = response.usage_metadata
    finish = candidate.finish_reason if candidate else None
    return LLMResponse(
        text="".join(text_parts).strip(),
        function_calls=calls,
        content=content,
        model=model,
        input_tokens=(usage.prompt_token_count or 0) if usage else 0,
        output_tokens=(usage.candidates_token_count or 0) if usage else 0,
        finish_reason=str(finish) if finish else None,
    )
