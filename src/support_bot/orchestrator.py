"""Turns a user question into a grounded, cited reply."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from google.genai import types

from support_bot.llm.client import LLMClient
from support_bot.llm.prompts import NO_ANSWER, SYSTEM_PROMPT, build_user_turn
from support_bot.rag.store import RetrievedChunk, Retriever

Outcome = Literal["answered", "low_confidence"]

_CITATION = re.compile(r"\[(\d+)\]")


@dataclass
class Answer:
    outcome: Outcome
    text: str
    """Answer text without the sources list ("" when outcome is low_confidence)."""
    citations: list[RetrievedChunk] = field(default_factory=list)
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


def extract_citations(
    text: str, chunks: Sequence[RetrievedChunk]
) -> tuple[str, list[RetrievedChunk]]:
    """Return text with citations renumbered 1..n in order of appearance, plus cited chunks.

    Citations that point to unknown document numbers are removed. Chunks that share the
    same title and heading are merged into one source.
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
    def __init__(self, llm: LLMClient, retriever: Retriever, min_score: float) -> None:
        self.llm = llm
        self.retriever = retriever
        self.min_score = min_score

    def answer(self, question: str) -> Answer:
        retrieved = self.retriever.search(question)
        relevant = [c for c in retrieved if c.score >= self.min_score]
        if not relevant:
            return Answer(outcome="low_confidence", text="", retrieved=retrieved)

        contents = [
            types.Content(
                role="user", parts=[types.Part.from_text(text=build_user_turn(question, relevant))]
            )
        ]
        response = self.llm.generate(contents, system_instruction=SYSTEM_PROMPT)
        usage = {
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        }
        if not response.text or NO_ANSWER in response.text:
            return Answer(outcome="low_confidence", text="", retrieved=retrieved, **usage)

        text, cited = extract_citations(response.text, relevant)
        if not cited:
            # An answer without citations is not grounded; do not show it.
            return Answer(outcome="low_confidence", text="", retrieved=retrieved, **usage)
        return Answer(
            outcome="answered",
            text=to_slack_mrkdwn(text),
            citations=cited,
            retrieved=retrieved,
            **usage,
        )
