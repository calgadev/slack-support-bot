"""Tiny Portuguese/English detection for fixed (non-LLM) bot messages."""

from __future__ import annotations

import re
from typing import Literal

Lang = Literal["en", "pt"]

_PT_MARKERS = {
    "não",
    "nao",
    "como",
    "para",
    "minha",
    "meu",
    "senha",
    "acesso",
    "você",
    "voce",
    "está",
    "esta",
    "preciso",
    "quero",
    "obrigado",
    "obrigada",
    "olá",
    "ola",
    "bom",
    "dia",
    "porque",
    "por",
    "que",
    "qual",
    "quando",
    "onde",
    "erro",
    "consigo",
    "ajuda",
    "uma",
    "um",
    "do",
    "da",
    "dos",
    "das",
    "no",
    "na",
    "com",
    "sem",
    "é",
    "abrir",
    "chamado",
    "impressora",
}
_EN_MARKERS = {
    "the",
    "how",
    "what",
    "my",
    "is",
    "are",
    "can",
    "cannot",
    "can't",
    "i",
    "to",
    "do",
    "does",
    "password",
    "access",
    "please",
    "help",
    "error",
    "when",
    "where",
    "why",
    "with",
    "open",
    "ticket",
    "printer",
    "a",
    "an",
    "of",
    "for",
    "it",
    "not",
}
_PT_CHARS = re.compile(r"[ãõçáéíóúâêô]", re.IGNORECASE)
_WORD = re.compile(r"[\wçãõáéíóúâêô']+", re.IGNORECASE)

MESSAGES: dict[str, dict[Lang, str]] = {
    "llm_error": {
        "en": "Sorry, I'm having trouble reaching the AI service right now. Please try again in a "
        "few minutes, or ask me to open a ticket.",
        "pt": "Desculpe, estou com dificuldade para acessar o serviço de IA agora. Tente novamente "
        "em alguns minutos ou peça para eu abrir um chamado.",
    },
    "internal_error": {
        "en": "Sorry, something went wrong on my side. The error was logged.",
        "pt": "Desculpe, algo deu errado do meu lado. O erro foi registrado.",
    },
    "low_confidence": {
        "en": "I couldn't find a reliable answer to this in the Acme knowledge base, so I'd "
        "rather not guess. Would you like me to open a support ticket for you?",
        "pt": "Não encontrei uma resposta confiável para isso na base de conhecimento da Acme, "
        "então prefiro não chutar. Quer que eu abra um chamado para você?",
    },
    "sources": {"en": "Sources", "pt": "Fontes"},
    "too_long": {
        "en": "Your message is too long ({length} characters, limit {limit}). Please shorten it.",
        "pt": "Sua mensagem é longa demais ({length} caracteres, limite {limit}). Por favor, "
        "resuma.",
    },
    "empty": {
        "en": "Hi! Ask me a question about Acme IT support, or say `status`.",
        "pt": "Oi! Faça uma pergunta sobre o suporte de TI da Acme, ou diga `status`.",
    },
}


def detect_language(text: str) -> Lang:
    words = [w.lower() for w in _WORD.findall(text)]
    pt = sum(w in _PT_MARKERS for w in words) + 2 * len(_PT_CHARS.findall(text))
    en = sum(w in _EN_MARKERS for w in words)
    return "pt" if pt > en else "en"


def t(key: str, lang: Lang, **kwargs: object) -> str:
    return MESSAGES[key][lang].format(**kwargs)
