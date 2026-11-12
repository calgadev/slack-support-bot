"""In-memory fakes for Slack and Gemini. No network access."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable, Sequence
from typing import Any

from google.genai import types

from support_bot.llm.client import FunctionCall, LLMResponse

_STOPWORDS = {"task", "search", "result", "query", "title", "text", "none", "the", "and", "how"}


class FakeSlackClient:
    def __init__(self) -> None:
        self.posted: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []
        self.ephemeral: list[dict[str, Any]] = []

    def chat_postEphemeral(self, **kwargs: Any) -> dict[str, Any]:
        self.ephemeral.append(kwargs)
        return {"ok": True}

    def chat_postMessage(self, **kwargs: Any) -> dict[str, Any]:
        self.posted.append(kwargs)
        return {"ok": True, "ts": f"1700000000.{len(self.posted):06d}"}

    def chat_update(self, **kwargs: Any) -> dict[str, Any]:
        self.updated.append(kwargs)
        return {"ok": True}

    @property
    def texts(self) -> list[str]:
        return [p.get("text", "") for p in self.posted]


def text_response(text: str, model: str = "fake-model") -> LLMResponse:
    content = types.Content(role="model", parts=[types.Part.from_text(text=text)])
    return LLMResponse(
        text=text, function_calls=[], content=content, model=model, input_tokens=10, output_tokens=5
    )


def call_response(name: str, args: dict[str, Any], model: str = "fake-model") -> LLMResponse:
    part = types.Part(function_call=types.FunctionCall(name=name, args=args, id=f"call-{name}"))
    content = types.Content(role="model", parts=[part])
    return LLMResponse(
        text="",
        function_calls=[FunctionCall(name=name, args=args, id=f"call-{name}")],
        content=content,
        model=model,
        input_tokens=10,
        output_tokens=5,
    )


def bag_of_words(text: str, dim: int = 64) -> list[float]:
    """Deterministic, normalized bag-of-words vector, good enough for retrieval tests."""
    vec = [0.0] * dim
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if len(word) < 3 or word in _STOPWORDS:
            continue
        vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeLLM:
    """Returns scripted responses in order and embeds text with ``bag_of_words``."""

    def __init__(
        self,
        responses: Sequence[LLMResponse | Exception] | None = None,
        embedder: Callable[[str], list[float]] | None = None,
    ) -> None:
        self.model = "fake-model"
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []
        self.embed_calls: list[list[str]] = []
        self._embedder = embedder or bag_of_words

    def generate(
        self, contents, *, system_instruction, tools=None, force_tool=False, json_schema=None
    ) -> LLMResponse:
        self.calls.append(
            {
                "contents": list(contents),
                "system_instruction": system_instruction,
                "tools": tools,
                "force_tool": force_tool,
            }
        )
        if not self.responses:
            raise AssertionError("FakeLLM ran out of scripted responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.embed_calls.append(list(texts))
        return [self._embedder(t) for t in texts]
