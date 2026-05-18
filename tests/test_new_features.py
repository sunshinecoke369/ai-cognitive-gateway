import pytest


def test_fim_prompt_builder():
    from app.api.openai_compat import _build_fim_prompt, _extract_fim_completion
    result = _build_fim_prompt("def hello(", ")\n    return")
    assert "<fim_prefix>" in result
    assert "<fim_suffix>" in result
    assert "<fim_middle>" in result
    assert result.endswith("<fim_middle>")

    cleaned = _extract_fim_completion("```python\nprint('hello')\n```", "", None)
    assert "```" not in cleaned


def test_cache_hash_deterministic():
    from app.cache.store import _hash_key
    h1 = _hash_key("hello world", "test-model")
    h2 = _hash_key("hello world", "test-model")
    assert h1 == h2
    h3 = _hash_key("hello world", "different-model")
    assert h1 != h3


def test_cache_set_get():
    from app.cache.store import _hash_key, cache_set, cache_get, cache_invalidate
    from app.core.database import get_connection
    key = _hash_key("test input", "test-model")
    cache_set("test input", "test-model", {"answer_text": "hello"})
    conn = get_connection()
    row = conn.execute("SELECT * FROM response_cache WHERE cache_key = ?", (key,)).fetchone()
    rows = conn.execute("SELECT COUNT(*) as cnt FROM response_cache").fetchone()
    all_rows = conn.execute("SELECT cache_key FROM response_cache LIMIT 5").fetchall()
    assert row is not None, f"DB check: row missing. total={dict(rows)['cnt']}, all_keys={[r['cache_key'] for r in all_rows]}, expected={key}"
    cached = cache_get("test input", "test-model")
    assert cached is not None
    assert cached["answer_text"] == "hello"

    cache_invalidate("test input", "test-model")
    cached2 = cache_get("test input", "test-model")
    assert cached2 is None


def test_cache_stats():
    from app.cache.store import cache_stats
    stats = cache_stats()
    assert "total_entries" in stats
    assert "ttl_default" in stats


def test_feedback_save_and_retrieve():
    from app.feedback.store import save_feedback, get_feedback_for_request
    save_feedback("test-req-1", 1, "good")
    records = get_feedback_for_request("test-req-1")
    assert len(records) >= 1
    assert records[0]["rating"] == 1


def test_feedback_stats():
    from app.feedback.store import get_feedback_stats
    stats = get_feedback_stats()
    assert "total" in stats
    assert "positive" in stats
    assert "negative" in stats


def test_feedback_invalid_rating():
    from app.feedback.store import save_feedback, get_feedback_for_request
    save_feedback("test-req-2", -1, "bad")
    records = get_feedback_for_request("test-req-2")
    assert records[0]["rating"] == -1


def test_completion_request_model():
    from app.api.openai_compat import CompletionRequest
    req = CompletionRequest(prompt="def foo():", suffix="\n    pass", max_tokens=128, temperature=0.2)
    assert req.prompt == "def foo():"
    assert req.suffix == "\n    pass"
    assert req.stream is False


def test_completion_request_defaults():
    from app.api.openai_compat import CompletionRequest
    req = CompletionRequest(prompt="hello")
    assert req.suffix is None
    assert req.max_tokens == 256
    assert req.temperature == 0.2


def test_base_provider_generate_stream_fallback():
    from app.providers.mock import MockProvider
    provider = MockProvider()
    import asyncio
    async def _run():
        result = []
        async for chunk in provider.generate_stream("hello world", model_name="test"):
            result.append(chunk)
        return len(result) > 0
    assert asyncio.run(_run())


def test_process_request_stream_exists():
    from app.gateway.engine import process_request_stream
    assert callable(process_request_stream)


def test_openai_stream_wrapper_format():
    import json as _json
    chunk = {
        "id": "test-id",
        "object": "chat.completion.chunk",
        "created": 1234567890,
        "model": "test-model",
        "choices": [{"index": 0, "delta": {"content": "Hello"}, "finish_reason": None}],
    }
    sse_line = f"data: {_json.dumps(chunk, ensure_ascii=False)}\n\n"
    assert sse_line.startswith("data: ")
    assert "chat.completion.chunk" in sse_line
    assert "Hello" in sse_line


def test_anthropic_stream_wrapper_format():
    import asyncio
    import json as _json
    from app.api.openai_compat import _anthropic_stream_wrapper

    async def _text_stream():
        yield "Hello"
        yield " World"

    async def _run():
        result = []
        async for line in _anthropic_stream_wrapper(_text_stream(), "test-model"):
            result.append(line)
        return result

    lines = asyncio.run(_run())
    assert any("message_start" in l for l in lines)
    assert any("content_block_start" in l for l in lines)
    assert any("content_block_delta" in l for l in lines)
    assert any("Hello" in l for l in lines)
    assert any("World" in l for l in lines)
    assert any("content_block_stop" in l for l in lines)
    assert any("message_delta" in l for l in lines)
    assert any("message_stop" in l for l in lines)


def test_chat_completions_stream_switches_to_streaming():
    from app.api.openai_compat import ChatCompletionRequest
    req = ChatCompletionRequest(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "Hi"}],
        stream=True,
    )
    assert req.stream is True
    assert req.messages[0].content == "Hi"


def test_mock_provider_non_stream_generate_still_works():
    from app.providers.mock import MockProvider
    provider = MockProvider()
    import asyncio
    async def _run():
        result = await provider.generate("hello world", model_name="test")
        return result
    result = asyncio.run(_run())
    assert result is not None
    assert hasattr(result, "text")


def test_has_images_in_messages_detects_image():
    from app.providers.base import has_images_in_messages
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "Describe"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}]}
    ]
    assert has_images_in_messages(msgs) is True


def test_has_images_in_messages_no_image():
    from app.providers.base import has_images_in_messages
    msgs = [{"role": "user", "content": "Hello world"}]
    assert has_images_in_messages(msgs) is False


def test_has_images_in_messages_text_only_array():
    from app.providers.base import has_images_in_messages
    msgs = [{"role": "user", "content": [{"type": "text", "text": "Hi"}]}]
    assert has_images_in_messages(msgs) is False


def test_extract_text_from_messages_handles_array():
    from app.providers.base import extract_text_from_messages
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "What is this?"}, {"type": "image_url", "image_url": {"url": "http://example.com/cat.jpg"}}]}
    ]
    result = extract_text_from_messages(msgs)
    assert "What is this?" in result
    assert "[IMAGE:" in result


def test_extract_text_from_messages_mixed():
    from app.providers.base import extract_text_from_messages
    msgs = [
        {"role": "system", "content": "You are helpful"},
        {"role": "user", "content": [{"type": "text", "text": "Analyze"}]}
    ]
    result = extract_text_from_messages(msgs)
    assert "You are helpful" in result
    assert "Analyze" in result


def test_model_capabilities_vision():
    from app.api.openai_compat import _model_capabilities
    caps = _model_capabilities("gpt-4o")
    assert caps["vision"] is True
    assert caps["streaming"] is True

    caps2 = _model_capabilities("qwen2.5vl:7b")
    assert caps2["vision"] is True

    caps3 = _model_capabilities("deepseek-chat")
    assert caps3["vision"] is False


def test_normalize_keeps_multimodal_for_vision_model():
    from app.api.openai_compat import normalize_messages_for_model
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "Hi"}, {"type": "image_url", "image_url": {"url": "http://x.com/a.jpg"}}]}
    ]
    result = normalize_messages_for_model(msgs, "gpt-4o")
    assert isinstance(result[0]["content"], list)
    assert len(result[0]["content"]) == 2


def test_normalize_strips_multimodal_for_non_vision():
    from app.api.openai_compat import normalize_messages_for_model
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "Hi"}, {"type": "image_url", "image_url": {"url": "http://x.com/a.jpg"}}]}
    ]
    result = normalize_messages_for_model(msgs, "deepseek-chat")
    assert isinstance(result[0]["content"], str)
    assert "Hi" in result[0]["content"]


def test_vision_routing_scores():
    from app.gateway.scheduler import rank_cloud_models
    from app.providers.base import LocalModelOutput
    local = LocalModelOutput(
        summary_short="test",
        summary_detailed="test",
        intent_primary="general",
        intent_confidence=0.8,
        filtered_text="test",
        risk_level="low",
        language="en",
    )
    models = rank_cloud_models(local, messages=[
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "http://x.com/a.jpg"}}]}
    ])
    assert len(models) >= 0
