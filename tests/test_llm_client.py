from unittest.mock import MagicMock

import httpx
import pytest
from google.genai import errors as genai_errors
from google.genai import types

from support_bot.llm.client import GeminiClient, LLMError, _to_llm_response


def make_client(max_attempts: int = 3) -> GeminiClient:
    client = GeminiClient(
        api_key="test-key",
        model="test-model",
        embedding_model="test-embed",
        embedding_dim=8,
        timeout_seconds=1,
        max_attempts=max_attempts,
        retry_initial_wait=0,
    )
    client._client = MagicMock()
    return client


def ok_response(text: str = "hi") -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(content=types.Content(role="model", parts=[types.Part(text=text)]))
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=12, candidates_token_count=3
        ),
    )


def user(text: str) -> list[types.Content]:
    return [types.Content(role="user", parts=[types.Part.from_text(text=text)])]


def test_retries_server_errors_then_succeeds() -> None:
    client = make_client()
    client._client.models.generate_content.side_effect = [
        genai_errors.ServerError(503, {"error": {"message": "overloaded"}}),
        ok_response("hello"),
    ]
    result = client.generate(user("q"), system_instruction="s")
    assert result.text == "hello"
    assert result.input_tokens == 12 and result.output_tokens == 3
    assert client._client.models.generate_content.call_count == 2


def test_does_not_retry_client_errors() -> None:
    client = make_client()
    client._client.models.generate_content.side_effect = genai_errors.ClientError(
        400, {"error": {"message": "bad request"}}
    )
    with pytest.raises(LLMError) as info:
        client.generate(user("q"), system_instruction="s")
    assert info.value.status == 400 and not info.value.retryable
    assert "bad request" in str(info.value)  # API message kept for diagnosis
    assert client._client.models.generate_content.call_count == 1


def test_rate_limit_is_retried_until_attempts_exhausted() -> None:
    client = make_client(max_attempts=3)
    client._client.models.generate_content.side_effect = genai_errors.ClientError(
        429, {"error": {"message": "quota"}}
    )
    with pytest.raises(LLMError) as info:
        client.generate(user("q"), system_instruction="s")
    assert info.value.status == 429
    assert client._client.models.generate_content.call_count == 3


def test_timeout_becomes_retryable_llm_error() -> None:
    client = make_client(max_attempts=2)
    client._client.models.generate_content.side_effect = httpx.ReadTimeout("slow")
    with pytest.raises(LLMError) as info:
        client.generate(user("q"), system_instruction="s")
    assert info.value.retryable
    assert client._client.models.generate_content.call_count == 2


@pytest.mark.parametrize("module", ["httpx", "httpx2"])
def test_transport_errors_from_both_http_libraries_are_retried(module: str) -> None:
    lib = pytest.importorskip(module)
    client = make_client(max_attempts=2)
    client._client.models.generate_content.side_effect = [lib.ReadTimeout("slow"), ok_response()]
    assert client.generate(user("q"), system_instruction="s").text == "hi"
    client._client.models.embed_content.side_effect = lib.ConnectError("down")
    with pytest.raises(LLMError) as info:
        client.embed(["a"])
    assert info.value.retryable


def test_parses_function_calls_and_skips_thoughts() -> None:
    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(text="thinking...", thought=True),
                        types.Part(
                            function_call=types.FunctionCall(
                                name="search_docs", args={"query": "vpn"}, id="c1"
                            )
                        ),
                    ],
                )
            )
        ]
    )
    parsed = _to_llm_response(response, "m")
    assert parsed.text == ""
    assert parsed.function_calls[0].name == "search_docs"
    assert parsed.function_calls[0].args == {"query": "vpn"}
    assert parsed.function_calls[0].id == "c1"


def test_empty_response_is_handled() -> None:
    parsed = _to_llm_response(types.GenerateContentResponse(candidates=[]), "m")
    assert parsed.text == "" and parsed.function_calls == [] and parsed.input_tokens == 0


def test_embed_returns_one_vector_per_text() -> None:
    client = make_client()
    client._client.models.embed_content.return_value = types.EmbedContentResponse(
        embeddings=[
            types.ContentEmbedding(values=[0.1] * 8),
            types.ContentEmbedding(values=[0.2] * 8),
        ]
    )
    vectors = client.embed(["a", "b"])
    assert len(vectors) == 2 and vectors[1][0] == 0.2
    sent = client._client.models.embed_content.call_args.kwargs["contents"]
    assert len(sent) == 2  # one Content per text, so embeddings are not pooled
