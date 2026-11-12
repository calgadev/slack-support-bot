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
        "few minutes, or open a ticket with the draft below.",
        "pt": "Desculpe, estou com dificuldade para acessar o serviço de IA agora. Tente novamente "
        "em alguns minutos ou abra um chamado com o rascunho abaixo.",
    },
    "quota_exhausted": {
        "en": "Sorry, I've reached my daily limit for the AI service, so I can't answer questions "
        "until it resets. You can still open a ticket with the draft below.",
        "pt": "Desculpe, atingi o limite diário do serviço de IA e não consigo responder perguntas "
        "até ele ser renovado. Você ainda pode abrir um chamado com o rascunho abaixo.",
    },
    "internal_error": {
        "en": "Sorry, something went wrong on my side. The error was logged.",
        "pt": "Desculpe, algo deu errado do meu lado. O erro foi registrado.",
    },
    "low_confidence": {
        "en": "I couldn't find a reliable answer to this in the Acme knowledge base, so I'd "
        "rather not guess. Would you like me to open a support ticket? I drafted one below.",
        "pt": "Não encontrei uma resposta confiável para isso na base de conhecimento da Acme, "
        "então prefiro não chutar. Quer que eu abra um chamado? Deixei um rascunho abaixo.",
    },
    "ticket_draft": {
        "en": "Here is the ticket draft. Nothing is created until you confirm.",
        "pt": "Aqui está o rascunho do chamado. Nada é criado até você confirmar.",
    },
    "ticket_fields": {
        "en": "*Title:* {title}\n*Priority:* {priority}\n*Description:* {description}",
        "pt": "*Título:* {title}\n*Prioridade:* {priority}\n*Descrição:* {description}",
    },
    "feedback_prompt": {"en": "Was this helpful?", "pt": "Isso ajudou?"},
    "feedback_thanks": {
        "en": "Thanks for the feedback!",
        "pt": "Obrigado pelo feedback!",
    },
    "btn_confirm": {"en": "Open ticket", "pt": "Abrir chamado"},
    "btn_cancel": {"en": "Cancel", "pt": "Cancelar"},
    "ticket_created": {
        "en": ":white_check_mark: Ticket *{key}* created: {title} (priority {priority}).",
        "pt": ":white_check_mark: Chamado *{key}* criado: {title} (prioridade {priority}).",
    },
    "ticket_cancelled": {
        "en": "Ticket draft cancelled. Nothing was created.",
        "pt": "Rascunho cancelado. Nenhum chamado foi criado.",
    },
    "ticket_expired": {
        "en": "This draft expired, so nothing was created. Ask me again to start a new one.",
        "pt": "Este rascunho expirou e nenhum chamado foi criado. Peça de novo para começar outro.",
    },
    "ticket_already": {
        "en": "This draft was already handled.",
        "pt": "Este rascunho já foi tratado.",
    },
    "ticket_not_owner": {
        "en": "Only the person who asked for this ticket can confirm or cancel it.",
        "pt": "Só quem pediu este chamado pode confirmar ou cancelar.",
    },
    "ticket_not_found": {
        "en": "I couldn't find this ticket draft anymore. Ask me again to start a new one.",
        "pt": "Não encontrei mais este rascunho. Peça de novo para começar outro.",
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


def t(key: str, lang: Lang, /, **kwargs: object) -> str:
    return MESSAGES[key][lang].format(**kwargs)
