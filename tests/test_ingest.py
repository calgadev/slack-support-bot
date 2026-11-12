import shutil
from pathlib import Path

import pytest

from support_bot.ingest import ingest
from support_bot.rag.store import EmbeddingConfigMismatch, Retriever, VectorStore
from tests.conftest import KB_DIR
from tests.fakes import FakeLLM


@pytest.fixture
def kb(tmp_path: Path) -> Path:
    target = tmp_path / "kb"
    shutil.copytree(KB_DIR, target)
    return target


def test_ingest_is_idempotent(kb: Path, store: VectorStore) -> None:
    llm = FakeLLM()
    first = ingest(kb, store, llm)
    assert first.added == first.total > 0 and first.deleted == 0
    embed_calls = len(llm.embed_calls)

    second = ingest(kb, store, llm)
    assert second.added == 0 and second.unchanged == first.total and second.deleted == 0
    assert len(llm.embed_calls) == embed_calls  # nothing re-embedded
    assert store.count() == first.total


def test_changed_and_deleted_documents_are_synced(kb: Path, store: VectorStore) -> None:
    llm = FakeLLM()
    first = ingest(kb, store, llm)

    vpn = kb / "vpn-access.md"
    vpn.write_text(vpn.read_text(encoding="utf-8").replace("12 hours", "10 hours"), "utf-8")
    (kb / "printer-issues.md").unlink()

    report = ingest(kb, store, llm)
    assert report.added == 1
    assert report.deleted >= 1 + 5  # the changed chunk plus all printer chunks
    assert store.count() == report.total < first.total
    assert not any(
        c.source == "printer-issues.md" for c in Retriever(store, llm, 20).search("printer")
    )


def test_embedding_model_change_fails_clearly_then_rebuild_works(
    kb: Path, store: VectorStore, tmp_path: Path
) -> None:
    ingest(kb, store, FakeLLM())
    other = VectorStore(tmp_path / "chroma", embedding_model="other-embed", embedding_dim=64)
    with pytest.raises(EmbeddingConfigMismatch, match="--rebuild"):
        ingest(kb, other, FakeLLM())
    report = ingest(kb, other, FakeLLM(), rebuild=True)
    assert report.added == report.total
    other.check_compatible()


def test_documents_are_embedded_with_title_prefix(kb: Path, store: VectorStore) -> None:
    llm = FakeLLM()
    ingest(kb, store, llm)
    assert all(text.startswith("title: ") for batch in llm.embed_calls for text in batch)
