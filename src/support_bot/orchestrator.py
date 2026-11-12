"""Runs the Gemini function-calling loop and turns the result into a grounded reply."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from google.genai import types

from support_bot.llm.client import FunctionCall, LLMClient, LLMResponse
from support_bot.llm.prompts import (
    NO_ANSWER,
    SYSTEM_PROMPT,
    build_user_turn,
    search_results_payload,
)
from support_bot.logging_setup import get_logger
from support_bot.rag.store import RetrievedChunk, Retriever
from support_bot.tools import (
    TOOLS,
    TicketDraft,
    ToolArgumentError,
    parse_search_args,
    parse_ticket_args,
)

log = get_logger(__name__)

Outcome = Literal["answered", "low_confidence", "ticket_proposed"]

_CITATION = re.compile(r"\[(\d+)\]")


@dataclass
class ToolCallRecord:
    name: str
    args: dict[str, Any]
    result: str


@dataclass
class Answer:
    outcome: Outcome
    text: str = ""
    """Answer text without the sources list (empty unless outcome is ``answered``)."""
    citations: list[RetrievedChunk] = field(default_factory=list)
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    ticket: TicketDraft | None = None
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0


def extract_citations(
    text: str, chunks: Sequence[RetrievedChunk]
) -> tuple[str, list[RetrievedChunk]]:
    """Return text with citations renumbered 1..n in order of appearance, plus cited chunks.

    ``chunks[i]`` is document number ``i + 1``. Citations to unknown numbers are removed.
    Chunks that share the same title and heading are merged into one source.
    """
    mapping: dict[int, int] = {}
    cited: list[RetrievedChunk] = []
    seen: dict[str, int] = {}

    def replace(match: re.Match[str]) -> str:
        n = int(match.group(1))
        if not 1 <= n <= len(chunks):
            return ""
        if n not in mapping:
            chunk = chunks[n - 1]
            if chunk.citation not in seen:
                cited.append(chunk)
                seen[chunk.citation] = len(cited)
            mapping[n] = seen[chunk.citation]
        return f"[{mapping[n]}]"

    new_text = _CITATION.sub(replace, text)
    new_text = re.sub(r"(\[\d+\])(\1)+", r"\1", new_text)  # [1][1] -> [1]
    return new_text.strip(), cited


def to_slack_mrkdwn(text: str) -> str:
    """Convert common Markdown that models emit into Slack mrkdwn."""
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    return re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)


class Orchestrator:
    def __init__(
        self, llm: LLMClient, retriever: Retriever, min_score: float, max_steps: int = 4
    ) -> None:
        self.llm = llm
        self.retriever = retriever
        self.min_score = min_score
        self.max_steps = max_steps

    def answer(self, question: str) -> Answer:
        result = Answer(outcome="low_confidence")
        sources: list[RetrievedChunk] = []  # document number n == sources[n - 1]
        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=build_user_turn(question))])
        ]

        for step in range(self.max_steps):
            # The first call must use a tool, so every answer starts from a search
            # (or from a ticket draft when the user asks for one).
            response = self.llm.generate(
                contents, system_instruction=SYSTEM_PROMPT, tools=TOOLS, force_tool=step == 0
            )
            self._add_usage(result, response)
            if not response.function_calls:
                return self._finish(result, response.text, sources)
            if response.content is not None:
                contents.append(response.content)  # unchanged, keeps thought signatures

            parts: list[types.Part] = []
            for call in response.function_calls:
                if call.name == "create_ticket":
                    try:
                        result.ticket = parse_ticket_args(call.args)
                    except ToolArgumentError as exc:
                        parts.append(self._tool_error(call, result, str(exc)))
                        continue
                    result.tool_calls.append(
                        ToolCallRecord(call.name, result.ticket.to_payload(), "drafted")
                    )
                    result.outcome = "ticket_proposed"
                    return result
                if call.name == "search_docs":
                    parts.append(self._search(call, result, sources))
                else:
                    parts.append(self._tool_error(call, result, f"unknown tool {call.name}"))
            # Function responses go back in a "user" turn; the API rejects role="tool".
            contents.append(types.Content(role="user", parts=parts))

        log.warning("max_tool_steps_reached", steps=self.max_steps)
        return result

    # -- helpers --------------------------------------------------------------------

    def _search(
        self, call: FunctionCall, result: Answer, sources: list[RetrievedChunk]
    ) -> types.Part:
        try:
            query = parse_search_args(call.args)
        except ToolArgumentError as exc:
            return self._tool_error(call, result, str(exc))
        hits = self.retriever.search(query)
        result.retrieved.extend(hits)
        numbered: list[tuple[int, RetrievedChunk]] = []
        known = {chunk.id: n for n, chunk in enumerate(sources, start=1)}
        for hit in hits:
            if hit.score < self.min_score:
                continue
            if hit.id not in known:
                sources.append(hit)
                known[hit.id] = len(sources)
            numbered.append((known[hit.id], hit))
        result.tool_calls.append(
            ToolCallRecord(call.name, {"query": query}, f"{len(numbered)} relevant")
        )
        return _function_response(call, search_results_payload(numbered))

    @staticmethod
    def _tool_error(call: FunctionCall, result: Answer, message: str) -> types.Part:
        result.tool_calls.append(ToolCallRecord(call.name, call.args, f"error: {message}"))
        return _function_response(call, {"error": message})

    @staticmethod
    def _add_usage(result: Answer, response: LLMResponse) -> None:
        result.model = response.model
        result.input_tokens += response.input_tokens
        result.output_tokens += response.output_tokens
        result.llm_calls += 1

    @staticmethod
    def _finish(result: Answer, text: str, sources: list[RetrievedChunk]) -> Answer:
        if not text or NO_ANSWER in text or not sources:
            return result
        clean, cited = extract_citations(text, sources)
        if not cited:
            # An answer without valid citations is not grounded; do not show it.
            return result
        result.outcome = "answered"
        result.text = to_slack_mrkdwn(clean)
        result.citations = cited
        return result


def _function_response(call: FunctionCall, payload: dict[str, Any]) -> types.Part:
    return types.Part(
        function_response=types.FunctionResponse(id=call.id, name=call.name, response=payload)
    )
