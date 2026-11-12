"""Turns a user question into a reply using the LLM."""

from __future__ import annotations

from dataclasses import dataclass

from google.genai import types

from support_bot.llm.client import LLMClient
from support_bot.llm.prompts import SYSTEM_PROMPT


@dataclass
class Answer:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class Orchestrator:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def answer(self, question: str) -> Answer:
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=question)])]
        response = self.llm.generate(contents, system_instruction=SYSTEM_PROMPT)
        return Answer(
            text=response.text,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
