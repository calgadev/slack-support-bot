"""Index the Markdown knowledge base into Chroma.

Usage: ``uv run support-bot-ingest [--rebuild]`` or ``python -m support_bot.ingest``.

Idempotent: chunk ids are derived from content hashes, so unchanged chunks are
skipped (no embedding calls), changed chunks get new ids, and chunks that no
longer exist are deleted.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from support_bot.config import get_settings
from support_bot.llm.client import LLMClient
from support_bot.logging_setup import configure_logging, get_logger
from support_bot.rag.chunking import load_knowledge_base
from support_bot.rag.store import EmbeddingConfigMismatch, VectorStore, format_document

log = get_logger(__name__)

EMBED_BATCH_SIZE = 50


@dataclass(frozen=True)
class IngestReport:
    total: int
    added: int
    unchanged: int
    deleted: int


def ingest(
    kb_dir: Path, store: VectorStore, llm: LLMClient, *, rebuild: bool = False
) -> IngestReport:
    if rebuild:
        store.reset()
    store.check_compatible()

    chunks = load_knowledge_base(kb_dir)
    if not chunks:
        raise RuntimeError(f"No Markdown files found in {kb_dir}")
    wanted = {c.id for c in chunks}
    existing = store.all_ids()

    new_chunks = [c for c in chunks if c.id not in existing]
    stale = sorted(existing - wanted)

    for start in range(0, len(new_chunks), EMBED_BATCH_SIZE):
        batch = new_chunks[start : start + EMBED_BATCH_SIZE]
        vectors = llm.embed([format_document(c) for c in batch])
        store.upsert(batch, vectors)
    store.delete(stale)

    report = IngestReport(
        total=len(chunks),
        added=len(new_chunks),
        unchanged=len(chunks) - len(new_chunks),
        deleted=len(stale),
    )
    log.info("ingest_done", **report.__dict__, indexed=store.count())
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index the knowledge base into Chroma.")
    parser.add_argument("--rebuild", action="store_true", help="drop and rebuild the index")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)

    from support_bot.app import build_llm

    store = VectorStore(
        settings.chroma_dir, settings.gemini_embedding_model, settings.gemini_embedding_dim
    )
    try:
        report = ingest(
            settings.knowledge_base_dir, store, build_llm(settings), rebuild=args.rebuild
        )
    except EmbeddingConfigMismatch as exc:
        log.error("ingest_failed", error=str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        f"Indexed {report.total} chunks: {report.added} added, {report.unchanged} unchanged, "
        f"{report.deleted} deleted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
