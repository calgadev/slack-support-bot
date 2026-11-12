"""Offline checks of the eval harness. The real evaluation calls Gemini and is not run in CI."""

from evals.run import (
    DATASETS,
    GoldenItem,
    ItemResult,
    compute_metrics,
    evaluate_item,
    judge,
    load_golden,
    render_markdown,
)
from support_bot.llm.prompts import NO_ANSWER
from support_bot.orchestrator import Orchestrator
from support_bot.rag.store import Retriever
from tests.conftest import KB_DIR
from tests.fakes import FakeLLM, call_response, text_response


def test_golden_set_is_well_formed() -> None:
    items = load_golden()
    assert 25 <= len(items) <= 30
    assert len({i.id for i in items}) == len(items)
    sources = {p.name for p in KB_DIR.glob("*.md")}
    for item in items:
        assert item.lang in {"en", "pt"}
        if item.answerable:
            assert item.expected_source in sources, item.id
        else:
            assert item.expected_source is None
    assert sum(not i.answerable for i in items) >= 4
    assert sum(i.lang == "pt" for i in items) >= 5


def test_judge_parses_structured_output() -> None:
    llm = FakeLLM([text_response('{"score": 2, "reason": "matches"}')])
    item = GoldenItem("x", "en", True, "q", "a.md", "ref")
    assert judge(llm, item, "answer") == (2, "matches")


def test_evaluate_item_end_to_end_with_fakes(retriever: Retriever) -> None:
    item = GoldenItem(
        "mail", "en", True, "mailbox quota full online archive", "email-problems.md", "50 GB"
    )
    llm = FakeLLM(
        [call_response("search_docs", {"query": item.question}), text_response("50 GB [1].")]
    )
    judge_llm = FakeLLM([text_response('{"score": 2, "reason": "ok"}')])
    result = evaluate_item(item, retriever, 4, Orchestrator(llm, retriever, 0.1), judge_llm)
    assert result.rank == 1 and result.outcome == "answered"
    assert result.cited_sources == ["email-problems.md"] and result.judge_score == 2


def test_unanswerable_refusal_is_not_judged(retriever: Retriever) -> None:
    item = GoldenItem("na", "en", False, "cafeteria menu", None, "-")
    llm = FakeLLM([call_response("search_docs", {"query": "menu"}), text_response(NO_ANSWER)])
    judge_llm = FakeLLM([])
    result = evaluate_item(item, retriever, 4, Orchestrator(llm, retriever, 0.1), judge_llm)
    assert result.outcome == "low_confidence" and result.judge_score is None


def r(id_, answerable, rank, top, outcome, cited=(), score=None, expected="a.md"):
    return ItemResult(
        id=id_,
        answerable=answerable,
        expected_source=expected if answerable else None,
        retrieved_sources=[],
        top_score=top,
        rank=rank,
        outcome=outcome,
        cited_sources=list(cited),
        judge_score=score,
        latency_ms=1000,
    )


def test_metrics_and_report() -> None:
    results = [
        r("a1", True, 1, 0.8, "answered", ["a.md"], 2),
        r("a2", True, 3, 0.6, "answered", ["b.md"], 1),
        r("a3", True, None, 0.4, "low_confidence"),
        r("u1", False, None, 0.35, "low_confidence"),
        r("u2", False, None, 0.65, "answered"),
    ]
    m = compute_metrics(results, k=4)
    assert m["hit_at_1"] == 1 / 3 and m["hit_at_k"] == 2 / 3
    assert m["answer_correct"] == 1 / 3  # refusals count as incorrect
    assert m["citation_accuracy"] == 1 / 3
    assert m["false_refusal_rate"] == 1 / 3 and m["correct_refusal_rate"] == 1 / 2
    row = next(c for c in m["calibration"] if c["threshold"] == 0.5)
    assert row == {"threshold": 0.5, "answerable_kept": 2 / 3, "unanswerable_blocked": 1 / 2}

    meta = {
        "date": "d",
        "model": "m",
        "judge_model": "j",
        "embedding_model": "e",
        "embedding_dim": 768,
        "min_score": 0.5,
    }
    md = render_markdown(results, m, meta)
    assert "| Retrieval hit@4 | 67% |" in md and "same model family" in md


def test_holdout_set_is_well_formed_and_disjoint_from_golden() -> None:
    holdout = load_golden(DATASETS["holdout"][0])
    golden = load_golden()
    assert 8 <= len(holdout) <= 15
    assert not {i.id for i in holdout} & {i.id for i in golden}
    assert not {i.question for i in holdout} & {i.question for i in golden}
    sources = {p.name for p in KB_DIR.glob("*.md")}
    for item in holdout:
        assert (
            (item.expected_source in sources) if item.answerable else item.expected_source is None
        )
    assert any(not i.answerable for i in holdout)
