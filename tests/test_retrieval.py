from support_bot.rag.store import Retriever, VectorStore
from tests.fakes import FakeLLM


def test_retrieves_relevant_document_first(retriever: Retriever) -> None:
    hits = retriever.search("printer paper jam hardware fault printer ID")
    assert hits[0].source == "printer-issues.md"
    assert len(hits) == 4


def test_scores_are_cosine_similarities_sorted(retriever: Retriever) -> None:
    hits = retriever.search("mailbox quota full online archive")
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(-1.0 <= s <= 1.0 for s in scores)
    assert hits[0].source == "email-problems.md"


def test_query_uses_query_prefix(indexed_store: VectorStore) -> None:
    llm = FakeLLM()
    Retriever(indexed_store, llm, top_k=2).search("vpn")
    assert llm.embed_calls == [["task: search result | query: vpn"]]


def test_empty_store_returns_nothing(store: VectorStore) -> None:
    assert Retriever(store, FakeLLM(), top_k=3).search("anything") == []


def test_citation_label(retriever: Retriever) -> None:
    hit = retriever.search("SSL certificate renewal CSR private key")[0]
    assert hit.citation == f"{hit.title} > {hit.heading}"
