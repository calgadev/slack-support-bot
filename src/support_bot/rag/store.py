"""Chroma-backed vector store and retriever."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from support_bot.llm.client import LLMClient
from support_bot.rag.chunking import Chunk

COLLECTION = "knowledge_base"


class EmbeddingConfigMismatch(RuntimeError):
    """The index was built with a different embedding model or dimension."""


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    source: str
    title: str
    heading: str
    text: str
    score: float
    """Cosine similarity in [-1, 1] (1 = identical)."""

    @property
    def citation(self) -> str:
        return f"{self.title} > {self.heading}"


def format_document(chunk: Chunk) -> str:
    """Document-side prefix recommended for gemini-embedding-2 (it has no task_type)."""
    return f"title: {chunk.title} | text: {chunk.heading}\n{chunk.text}"


def format_query(query: str) -> str:
    return f"task: search result | query: {query}"


class VectorStore:
    def __init__(self, path: Path, embedding_model: str, embedding_dim: int) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.embedding_model = embedding_model
        self.embedding_dim = embedding_dim
        self._client = chromadb.PersistentClient(
            path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
        )
        self._collection = self._get_or_create()

    def _expected_metadata(self) -> dict[str, Any]:
        return {
            "hnsw:space": "cosine",
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
        }

    def _get_or_create(self) -> Any:
        # Do not use get_or_create_collection: passing metadata could overwrite the stored
        # embedding settings and hide a mismatch.
        try:
            return self._client.get_collection(name=COLLECTION, embedding_function=None)
        except Exception:  # chromadb raises NotFoundError (or ValueError in older versions)
            return self._client.create_collection(
                name=COLLECTION, metadata=self._expected_metadata(), embedding_function=None
            )

    def check_compatible(self) -> None:
        meta = self._collection.metadata or {}
        found = (meta.get("embedding_model"), meta.get("embedding_dim"))
        expected = (self.embedding_model, self.embedding_dim)
        if found != expected:
            raise EmbeddingConfigMismatch(
                f"Index was built with embedding model/dim {found}, but the configuration is "
                f"{expected}. Run `uv run support-bot-ingest --rebuild` to re-index."
            )

    def reset(self) -> None:
        self._client.delete_collection(COLLECTION)
        self._collection = self._get_or_create()

    def count(self) -> int:
        return self._collection.count()

    def all_ids(self) -> set[str]:
        return set(self._collection.get(include=[])["ids"])

    def upsert(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> None:
        if not chunks:
            return
        self._collection.upsert(
            ids=[c.id for c in chunks],
            embeddings=[list(e) for e in embeddings],
            documents=[c.text for c in chunks],
            metadatas=[c.metadata for c in chunks],
        )

    def delete(self, ids: Sequence[str]) -> None:
        if ids:
            self._collection.delete(ids=list(ids))

    def query(self, embedding: Sequence[float], k: int) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []
        result = self._collection.query(
            query_embeddings=[list(embedding)],
            n_results=min(k, self.count()),
            include=["documents", "metadatas", "distances"],
        )
        chunks: list[RetrievedChunk] = []
        for chunk_id, doc, meta, dist in zip(
            result["ids"][0],
            (result["documents"] or [[]])[0],
            (result["metadatas"] or [[]])[0],
            (result["distances"] or [[]])[0],
            strict=False,
        ):
            meta = meta or {}
            chunks.append(
                RetrievedChunk(
                    id=chunk_id,
                    source=str(meta.get("source", "")),
                    title=str(meta.get("title", "")),
                    heading=str(meta.get("heading", "")),
                    text=doc or "",
                    # Chroma's cosine "distance" is 1 - cosine similarity.
                    score=round(1.0 - float(dist), 4),
                )
            )
        return chunks


class Retriever:
    def __init__(self, store: VectorStore, llm: LLMClient, top_k: int) -> None:
        self.store = store
        self.llm = llm
        self.top_k = top_k

    def search(self, query: str, k: int | None = None) -> list[RetrievedChunk]:
        [vector] = self.llm.embed([format_query(query)])
        return self.store.query(vector, k or self.top_k)
