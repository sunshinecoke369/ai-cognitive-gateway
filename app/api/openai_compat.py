import json
import time
from typing import Union

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.gateway.engine import process_request, process_request_stream
from app.providers.model_validator import resolve_local_model, resolve_cloud_model, get_allowed_local_models, get_allowed_cloud_models
from app.providers.base import has_images_in_messages
from app.admin.router import resolve_client_from_header
from app.core.config import settings
from app.core.logging import logger

openai_router = APIRouter(prefix="/v1")


def extract_text_content(content: str | list[dict]) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for p in content:
        if isinstance(p, dict):
            if p.get("type") == "text" and isinstance(p.get("text"), str):
                parts.append(p["text"])
            if p.get("type") == "image_url" and isinstance(p.get("image_url"), dict):
                url = p["image_url"].get("url", "")
                if url:
                    parts.append(f"[IMAGE: {url[:80]}]")
            if p.get("type") == "input_audio":
                parts.append("[AUDIO INPUT]")
    return " ".join(parts)


def normalize_messages_for_model(messages: list[dict], model_name: str) -> list[dict]:
    caps = _model_capabilities(model_name)
    if caps.get("vision"):
        return messages
    normalized = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            content = extract_text_content(content)
        normalized.append({"role": msg["role"], "content": content})
    return normalized


def count_content_tokens(content: str | list[dict]) -> int:
    text = extract_text_content(content)
    return len(text.split()) if text.strip() else 0


class ChatMessage(BaseModel):
    role: str
    content: Union[str, list[dict]]


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@openai_router.get("/models")
async def list_models():
    local = get_allowed_local_models()
    cloud = get_allowed_cloud_models()
    data = [
        {"id": "auto", "object": "model", "owned_by": "gateway", "capabilities": {"streaming": True, "vision": False, "tool_calling": True, "reasoning": False, "fim": True}},
        {"id": "gateway", "object": "model", "owned_by": "gateway", "capabilities": {"streaming": True, "vision": False, "tool_calling": True, "reasoning": False, "fim": True}},
    ]
    for m in cloud:
        caps = _model_capabilities(m)
        data.append({"id": m, "object": "model", "owned_by": "cloud", "capabilities": caps})
    for m in local:
        lcaps = _model_capabilities(m)
        data.append({"id": m, "object": "model", "owned_by": "local", "capabilities": lcaps})
    return {"object": "list", "data": data}


def _model_capabilities(model_name: str) -> dict:
    name_lower = model_name.lower()
    vision = any(k in name_lower for k in ("gpt-4o", "claude-3", "claude-3.5", "gemini", "vision", "vl", "gpt-4-turbo"))
    reasoning = any(k in name_lower for k in ("deepseek-reasoner", "o1", "o3", "reasoning", "thinking"))
    return {
        "streaming": True,
        "vision": vision,
        "tool_calling": not reasoning,
        "reasoning": reasoning,
        "fim": not vision,
    }


def _build_openai_stream_chunk(request_id: str, model: str, delta_text: str, finish: bool = False) -> str:
    choice = {
        "index": 0,
        "delta": {} if finish else {"content": delta_text},
        "finish_reason": "stop" if finish else None,
    }
    chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [choice],
    }
    return json.dumps(chunk, ensure_ascii=False)


async def _openai_stream_generator(request_id: str, model: str, content: str):
    yield f"data: {_build_openai_stream_chunk(request_id, model, content)}\n\n"
    yield f"data: {_build_openai_stream_chunk(request_id, model, '', finish=True)}\n\n"
    yield "data: [DONE]\n\n"


@openai_router.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest, authorization: str | None = Header(None)):
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages is required")

    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    gateway_local = resolve_local_model()
    gateway_cloud = req.model or resolve_cloud_model()

    if has_images_in_messages(messages) and not _model_capabilities(gateway_cloud).get("vision"):
        from app.admin.config_manager import resolve_runtime_cloud_models
        models = resolve_runtime_cloud_models()
        vision_models = [m for m in models if "vision" in [t.lower() for t in m.get("tags", [])]]
        if vision_models:
            gateway_cloud = vision_models[0]["name"]
            logger.warning("auto-routing image request to vision model", extra={"from": req.model or "default", "to": gateway_cloud})

    messages = normalize_messages_for_model(messages, gateway_cloud)

    client_id, request_source = resolve_client_from_header(authorization, strict=True)

    if req.stream:
        async def _openai_stream_wrapper():
            async for text_chunk in process_request_stream(
                user_input="",
                local_model_name=gateway_local,
                cloud_model_name=gateway_cloud,
                client_id=client_id,
                request_source=request_source,
                messages=messages,
            ):
                chunk = {
                    "id": f"chatcmpl-stream",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": gateway_cloud,
                    "choices": [{"index": 0, "delta": {"content": text_chunk}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            final = {
                "id": f"chatcmpl-stream",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": gateway_cloud,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            _openai_stream_wrapper(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    t0 = time.perf_counter()
    result = await process_request(
        user_input="",
        local_model_name=gateway_local,
        cloud_model_name=gateway_cloud,
        client_id=client_id,
        request_source=request_source,
        messages=messages,
    )
    latency = round((time.perf_counter() - t0) * 1000, 2)

    content = result.to_dict().get("answer", {}).get("text", "")

    choice = ChatCompletionChoice(
        message=ChatMessage(role="assistant", content=content),
    )

    prompt_tokens = sum(count_content_tokens(m.get("content", "")) for m in messages)
    completion_tokens = len(content.split())
    return {
        "id": result.request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": gateway_cloud,
        "choices": [choice.model_dump()],
        "usage": ChatCompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ).model_dump(),
        "gateway_trace": {
            "request_id": result.request_id,
            "local_model_used": result.local_model_name,
            "cloud_model_used": result.cloud_model_name,
            "local_degraded": result.local_degraded,
            "blocked": result.blocked,
            "latency_ms": latency,
        },
    }


class FeedbackRequest(BaseModel):
    request_id: str
    rating: int = 0
    comment: str = ""


@openai_router.post("/feedback")
async def submit_feedback(req: FeedbackRequest, authorization: str | None = Header(None)):
    from app.admin.router import resolve_client_from_header
    resolve_client_from_header(authorization, strict=True)

    from app.feedback.store import save_feedback
    if req.rating not in (-1, 0, 1):
        raise HTTPException(status_code=400, detail="rating must be -1, 0, or 1")
    result = save_feedback(req.request_id, req.rating, req.comment)
    return result


class AnthropicTextContent(BaseModel):
    type: str = "text"
    text: str


class AnthropicImageSource(BaseModel):
    type: str = "base64"
    media_type: str
    data: str


class AnthropicImageContent(BaseModel):
    type: str = "image"
    source: AnthropicImageSource


class AnthropicMessage(BaseModel):
    role: str
    content: Union[str, list[Union[AnthropicTextContent, AnthropicImageContent]]]


class AnthropicMessagesRequest(BaseModel):
    model: str = "auto"
    messages: list[AnthropicMessage]
    max_tokens: int = 4096
    system: str | None = None
    stream: bool = False
    temperature: float | None = None


def _anthropic_content_to_str(content) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict):
            t = block.get("type", "")
            if t == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
            if t == "image":
                parts.append("[IMAGE]")
        else:
            t = getattr(block, "type", "")
            if t == "text" and hasattr(block, "text"):
                parts.append(block.text)
            if t == "image":
                parts.append("[IMAGE]")
    return " ".join(parts)


def _anthropic_normalize_messages(req: AnthropicMessagesRequest, cloud_model: str) -> list[dict]:
    messages: list[dict] = []
    if req.system:
        messages.append({"role": "system", "content": req.system})
    for m in req.messages:
        content_raw = getattr(m, "content", m.content if hasattr(m, "content") else "")
        normalized_content = _anthropic_content_to_str(content_raw)
        messages.append({"role": m.role, "content": normalized_content})
    return normalize_messages_for_model(messages, cloud_model)


async def _anthropic_stream_wrapper(stream_generator, model: str):
    import uuid
    msg_id = str(uuid.uuid4())
    yield "event: message_start\n"
    yield f"data: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'model': model, 'content': []}})}\n\n"
    yield "event: content_block_start\n"
    yield f"data: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"
    output_tokens = 0
    async for text_chunk in stream_generator:
        output_tokens += 1
        yield "event: content_block_delta\n"
        yield f"data: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': text_chunk}})}\n\n"
    yield "event: content_block_stop\n"
    yield f"data: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
    yield "event: message_delta\n"
    yield f"data: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}, 'usage': {'output_tokens': output_tokens}})}\n\n"
    yield "event: message_stop\n"
    yield f"data: {json.dumps({'type': 'message_stop'})}\n\n"


class CompletionRequest(BaseModel):
    model: str | None = None
    prompt: str = ""
    suffix: str | None = None
    max_tokens: int = 256
    temperature: float = 0.2
    stop: list[str] | None = None
    stream: bool = False


def _build_fim_prompt(prompt: str, suffix: str | None) -> str:
    if not suffix:
        return prompt
    return f"<fim_prefix>{prompt}<fim_suffix>{suffix}<fim_middle>"


def _extract_fim_completion(raw: str, prompt: str, suffix: str | None) -> str:
    text = raw
    for token in ["<fim_prefix>", "<fim_suffix>", "<fim_middle>", "```"]:
        text = text.replace(token, "")
    text = text.strip()
    return text


async def _call_cloud_completion(prompt: str, model_name: str, suffix: str | None, max_tokens: int, temperature: float) -> tuple[str, int, int]:
    from app.admin.config_manager import resolve_runtime_cloud_config, get_cloud_models
    cfg = resolve_runtime_cloud_config()
    models = get_cloud_models()
    model_cfg = models.get(model_name, {})

    api_url = model_cfg.get("api_url", cfg.get("api_url", ""))
    api_key = model_cfg.get("api_key", cfg.get("api_key", ""))
    timeout = model_cfg.get("timeout_seconds", cfg.get("timeout_seconds", 60))

    import httpx
    from app.core.logging import logger

    fim_prompt = _build_fim_prompt(prompt, suffix)

    url = api_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a code completion engine. Complete the code between <fim_prefix> and <fim_suffix>. Return ONLY the code that goes in the middle, no explanations."},
            {"role": "user", "content": fim_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            raw = choices[0].get("message", {}).get("content", "") if choices else ""
            completion = _extract_fim_completion(raw, prompt, suffix)
            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens", len(prompt.split()))
            tokens_out = usage.get("completion_tokens", len(completion.split()))
            return completion, tokens_in, tokens_out
    except Exception as e:
        logger.error("cloud completion failed", extra={"model": model_name, "error": str(e)})
        return "", 0, 0


@openai_router.post("/completions")
async def completions(req: CompletionRequest, authorization: str | None = Header(None)):
    gateway_cloud = resolve_cloud_model()
    model = req.model or gateway_cloud

    from app.admin.router import resolve_client_from_header
    client_id, _ = resolve_client_from_header(authorization, strict=True)

    import time as _time
    t0 = _time.perf_counter()

    completion, tokens_in, tokens_out = await _call_cloud_completion(
        prompt=req.prompt,
        model_name=model,
        suffix=req.suffix,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
    )

    latency = round((_time.perf_counter() - t0) * 1000, 2)

    if req.stream:
        import uuid
        rid = str(uuid.uuid4())

        def _gen():
            yield f"data: {json.dumps({'id': rid, 'object': 'text_completion.chunk', 'created': int(_time.time()), 'model': model, 'choices': [{'index': 0, 'text': completion, 'finish_reason': 'stop', 'logprobs': None}]})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    return {
        "id": f"cmpl-{int(_time.time())}",
        "object": "text_completion",
        "created": int(_time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "text": completion,
                "finish_reason": "stop",
                "logprobs": None,
            }
        ],
        "usage": {
            "prompt_tokens": tokens_in,
            "completion_tokens": tokens_out,
            "total_tokens": tokens_in + tokens_out,
        },
    }


@openai_router.post("/messages")
async def anthropic_messages(req: AnthropicMessagesRequest, authorization: str | None = Header(None)):
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages is required")

    gateway_local = resolve_local_model()
    gateway_cloud = req.model or resolve_cloud_model()

    messages = _anthropic_normalize_messages(req, gateway_cloud)

    if has_images_in_messages(messages) and not _model_capabilities(gateway_cloud).get("vision"):
        from app.admin.config_manager import resolve_runtime_cloud_models
        models = resolve_runtime_cloud_models()
        vision_models = [m for m in models if "vision" in [t.lower() for t in m.get("tags", [])]]
        if vision_models:
            gateway_cloud = vision_models[0]["name"]
            logger.warning("auto-routing image request to vision model (anthropic)", extra={"from": req.model or "default", "to": gateway_cloud})

    client_id, request_source = resolve_client_from_header(authorization, strict=True)

    if req.stream:
        stream_gen = process_request_stream(
            user_input="",
            local_model_name=gateway_local,
            cloud_model_name=gateway_cloud,
            client_id=client_id,
            request_source=request_source,
            messages=messages,
        )
        return StreamingResponse(
            _anthropic_stream_wrapper(stream_gen, gateway_cloud),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    t0 = time.perf_counter()
    result = await process_request(
        user_input="",
        local_model_name=gateway_local,
        cloud_model_name=gateway_cloud,
        client_id=client_id,
        request_source=request_source,
        messages=messages,
    )
    latency = round((time.perf_counter() - t0) * 1000, 2)

    answer_text = result.to_dict().get("answer", {}).get("text", "")

    prompt_tokens = sum(count_content_tokens(m.get("content", "")) for m in messages)
    completion_tokens = len(answer_text.split())

    return {
        "id": result.request_id,
        "type": "message",
        "role": "assistant",
        "model": gateway_cloud,
        "content": [{"type": "text", "text": answer_text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
        },
        "gateway_trace": {
            "request_id": result.request_id,
            "local_model_used": result.local_model_name,
            "cloud_model_used": result.cloud_model_name,
            "local_degraded": result.local_degraded,
            "blocked": result.blocked,
            "latency_ms": latency,
        },
    }
