"""Thin wrapper around the google-genai SDK with timeouts, retries and typed results.

Only this module talks to the Gemini API. The rest of the code depends on the
``LLMClient`` protocol so tests can use an in-memory fake.
"""

from __future__ import annotations

from collections.abc import Sequence
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


class LLMError(Exception):
    """Raised when the LLM call fails after all retries. Safe to show a generic message."""

    def __init__(self, message: str, *, retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


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


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, genai_errors.APIError):
        return exc.code in RETRYABLE_STATUS
    return isinstance(exc, httpx.TimeoutException | httpx.TransportError)


def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    log.warning(
        "llm_retry",
        attempt=state.attempt_number,
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
        self._retry = retry(
            reraise=True,
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential_jitter(
                initial=retry_initial_wait, max=10, jitter=retry_initial_wait
            ),
            retry=retry_if_exception(_is_retryable),
            before_sleep=_log_retry,
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
            raise LLMError(
                f"Gemini API error {exc.code}", retryable=_is_retryable(exc), status=exc.code
            ) from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
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
            raise LLMError(
                f"Gemini embedding error {exc.code}", retryable=_is_retryable(exc), status=exc.code
            ) from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
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
