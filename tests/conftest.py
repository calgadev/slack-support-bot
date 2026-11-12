from pathlib import Path

import pytest

from support_bot.rag.store import Retriever, VectorStore
from tests.fakes import FakeLLM

REPO_ROOT = Path(__file__).resolve().parents[1]
KB_DIR = REPO_ROOT / "knowledge_base"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep tests independent from any local .env file or real tokens."""
    monkeypatch.chdir(tmp_path)
    for var in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def store(tmp_path: Path) -> VectorStore:
    return VectorStore(tmp_path / "chroma", embedding_model="fake-embed", embedding_dim=64)


@pytest.fixture
def indexed_store(store: VectorStore) -> VectorStore:
    from support_bot.ingest import ingest

    ingest(KB_DIR, store, FakeLLM())
    return store


@pytest.fixture
def retriever(indexed_store: VectorStore) -> Retriever:
    return Retriever(indexed_store, FakeLLM(), top_k=4)
