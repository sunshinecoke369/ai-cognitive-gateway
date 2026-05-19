import time
import uuid
import json
import asyncio

from app.core.logging import logger
from app.core.doctrine import is_override_active, is_shutdown_requested, check_capability
from app.core.audit import write_governance_decision, write_model_routing, write_memory_operation, write_entry, write_step
from app.providers.registry import get_local_provider, get_cloud_provider
from app.providers.base import LocalModelOutput, CloudModelResponse, extract_text_from_messages
from app.providers.model_validator import resolve_cloud_model
from app.governance.engine import police_check, police_check_messages
from app.governance.judge import adjudicate
from app.memory.store import save_entry, retrieve_summary_context
from app.tokenflow.tracker import record_tokens
from app.tokenflow.counter import count_tokens
from app.prompts.templates import build_cloud_prompt
from app.core.database import get_connection
from app.gateway.scheduler import pick_cloud_model, get_fallback_chain


class GatewayResponse:
    def __init__(
        self,
        request_id: str,
        answer_text: str,
        answer_structured: dict | None,
        used_model: str,
        latency_ms: float,
        blocked: bool,
        rules_applied: list[str],
        should_write_memory: bool,
        memory_content: str,
        local_model_output: LocalModelOutput | None,
        cloud_model_response: CloudModelResponse | None,
        judge_verdict: str = "allow",
        override_active: bool = False,
        local_model_name: str = "",
        cloud_model_name: str = "",
        local_degraded: bool = False,
    ):
        self.request_id = request_id
        self.answer_text = answer_text
        self.answer_structured = answer_structured
        self.used_model = used_model
        self.latency_ms = latency_ms
        self.blocked = blocked
        self.rules_applied = rules_applied
        self.should_write_memory = should_write_memory
        self.memory_content = memory_content
        self.local_model_output = local_model_output
        self.cloud_model_response = cloud_model_response
        self.judge_verdict = judge_verdict
        self.override_active = override_active
        self.local_model_name = local_model_name
        self.cloud_model_name = cloud_model_name
        self.local_degraded = local_degraded

    def to_dict(self) -> dict:
        result = {
            "request_id": self.request_id,
            "answer": {
                "text": self.answer_text,
                "structured": self.answer_structured or {},
            },
            "trace": {
                "local_model_used": self.local_model_name,
                "cloud_model_used": self.cloud_model_name,
                "local_degraded": self.local_degraded,
                "rule_hits": self.rules_applied,
                "memory_read": bool(self.should_write_memory),
                "latency_ms": self.latency_ms,
            },
            "governance_trace": {
                "blocked": self.blocked,
                "rules_applied": self.rules_applied,
                "judge_verdict": self.judge_verdict,
                "override_active": self.override_active,
            },
            "memory_writeback": {
                "should_write": self.should_write_memory,
                "content": self.memory_content,
            },
        }
        return result


async def process_request(
    user_input: str = "",
    local_model_name: str = "",
    cloud_model_name: str = "",
    client_id: str = "",
    session_id: str = "",
    request_source: str = "",
    messages: list[dict] | None = None,
    skip_cache: bool = False,
) -> GatewayResponse:
    request_id = str(uuid.uuid4())
    t_start = time.perf_counter()
    _pt = t_start

    def _log_phase_timing(name: str):
        nonlocal _pt
        now = time.perf_counter()
        elapsed = (now - _pt) * 1000
        _pt = now
        logger.info("perf:phase_timing", extra={"phase": name, "latency_ms": round(elapsed, 2), "request_id": request_id})

    has_messages = messages is not None and len(messages) > 0
    input_text = user_input
    if has_messages and not input_text:
        input_text = extract_text_from_messages(messages)

    logger.info("gateway request started", extra={
        "request_id": request_id,
        "input_length": len(input_text),
        "local_model": local_model_name or "default",
        "cloud_model": cloud_model_name or "default",
        "has_messages": has_messages,
        "client_id": client_id,
        "source": request_source,
    })

    resolved_cloud = cloud_model_name or resolve_cloud_model()
    if not skip_cache:
        from app.cache.store import cache_get
        cached = cache_get(input_text, resolved_cloud, messages)
        if cached:
            cached_latency = (time.perf_counter() - t_start) * 1000
            logger.info("cache hit, returning cached response", extra={"request_id": request_id, "model": resolved_cloud})
            return GatewayResponse(
                request_id=request_id,
                answer_text=cached.get("answer_text", ""),
                answer_structured=cached.get("answer_structured"),
                used_model=f"cache:{resolved_cloud}",
                latency_ms=round(cached_latency, 2),
                blocked=False,
                rules_applied=[],
                should_write_memory=False,
                memory_content="",
                local_model_output=None,
                cloud_model_response=None,
                judge_verdict="allow",
                local_model_name=local_model_name,
                cloud_model_name=resolved_cloud,
            )

    if not check_capability("chat"):
        write_entry(request_id, "capability_denied", "gateway", {"capability": "chat"})
        return GatewayResponse(
            request_id=request_id,
            answer_text="Chat capability is currently suspended or revoked.",
            answer_structured={"reason": "capability_denied"},
            used_model="none",
            latency_ms=0,
            blocked=True,
            rules_applied=[],
            should_write_memory=False,
            memory_content="",
            local_model_output=None,
            cloud_model_response=None,
            judge_verdict="capability_denied",
            local_model_name=local_model_name,
            cloud_model_name=cloud_model_name,
        )

    if is_shutdown_requested():
        write_entry(request_id, "shutdown_blocked", "gateway", {})
        return GatewayResponse(
            request_id=request_id,
            answer_text="System shutdown has been requested. New requests are not accepted.",
            answer_structured={"reason": "shutdown_requested"},
            used_model="none",
            latency_ms=0,
            blocked=True,
            rules_applied=[],
            should_write_memory=False,
            memory_content="",
            local_model_output=None,
            cloud_model_response=None,
            judge_verdict="shutdown",
            local_model_name=local_model_name,
            cloud_model_name=cloud_model_name,
        )

    override_active = is_override_active()
    logger.info("phase:governance_check", extra={"request_id": request_id, "override_active": override_active, "has_messages": has_messages})

    if has_messages and messages:
        police_result = police_check_messages(messages)
    else:
        police_result = police_check(input_text)

    write_governance_decision(
        request_id=request_id,
        allowed=police_result["allowed"],
        violations=police_result.get("violations", []),
        rule_hits=police_result.get("rule_hits", []),
    )

    write_step(request_id=request_id, session_id=session_id, client_id=client_id, request_source=request_source, step="governance", latency_ms=0, rule_hits=police_result.get("rule_hits", []))

    judge_result = adjudicate(police_result)

    if judge_result["verdict"] == "blocked":
        _log_phase_timing("governance")
        total_latency = (time.perf_counter() - t_start) * 1000
        logger.warning("request blocked by judge", extra={"request_id": request_id, "verdict": judge_result})
        return GatewayResponse(
            request_id=request_id,
            answer_text="请求已被安全策略拦截",
            answer_structured={"blocked_reason": police_result.get("violations", []), "judge_reason": judge_result["reason"]},
            used_model="none",
            latency_ms=round(total_latency, 2),
            blocked=True,
            rules_applied=police_result["rule_hits"],
            should_write_memory=False,
            memory_content="",
            local_model_output=None,
            cloud_model_response=None,
            judge_verdict=judge_result["verdict"],
            override_active=override_active,
            local_model_name=local_model_name,
            cloud_model_name=cloud_model_name,
        )

    _log_phase_timing("governance")
    local_provider = get_local_provider()
    resolved_local_model = local_model_name or ""
    local_output = await local_provider.preprocess(input_text, model_name=resolved_local_model or None, messages=messages)

    local_degraded = local_output.degraded
    logger.info("phase:local_preprocess", extra={"request_id": request_id, "local_model": local_model_name or "default", "degraded": local_degraded, "intent": local_output.intent_primary, "confidence": local_output.intent_confidence})
    _log_phase_timing("local_preprocess")

    effective_input = local_output.filtered_text if not local_degraded else input_text

    memory_context = retrieve_summary_context(layer="user")

    logger.info("phase:cloud_prompt_build", extra={"request_id": request_id, "input_length": len(effective_input), "degraded": local_degraded, "intent": local_output.intent_primary})
    _log_phase_timing("prompt_build")

    cloud_prompt = build_cloud_prompt(
        user_input=effective_input,
        intent=local_output.intent_primary,
        memory_context=memory_context,
        safety_rules="Standard content policy",
        response_style="concise",
        origin_model=f"local_model_{local_provider.provider_name}",
        confidence=local_output.intent_confidence,
    )

    record_tokens(request_id, "local_preprocess", tokens_out=count_tokens(local_output.summary_detailed))

    scheduled = pick_cloud_model(local_output, messages=messages)
    fallback_chain = get_fallback_chain(local_output, messages=messages)
    if not fallback_chain and cloud_model_name:
        fallback_chain = [{"name": cloud_model_name, "provider": "openai-compatible", "api_url": "", "api_key": "", "timeout_seconds": 60, "weight": 1, "tags": ["general"]}]
    if not fallback_chain:
        fallback_chain = [{"name": "default", "provider": "openai-compatible", "api_url": "", "api_key": "", "timeout_seconds": 60, "weight": 1, "tags": ["general"]}]
    resolved_cloud_model = scheduled["name"] if scheduled else cloud_model_name or "default"

    write_model_routing(
        request_id=request_id,
        local_model=resolved_local_model or local_provider.provider_name,
        cloud_model=f"{resolved_cloud_model} (chain of {len(fallback_chain)})",
    )

    logger.info("phase:cloud_schedule", extra={
        "request_id": request_id,
        "primary_model": resolved_cloud_model,
        "fallback_chain": [m["name"] for m in fallback_chain],
    })
    _log_phase_timing("cloud_schedule")

    cloud_provider = get_cloud_provider()
    cloud_output = None
    for idx, fallback_model in enumerate(fallback_chain):
        fallback_name = fallback_model["name"]
        resolved_cloud_model = fallback_name
        logger.info("phase:cloud_generate", extra={"request_id": request_id, "model": fallback_name, "attempt": idx + 1})
        if idx == 0:
            _log_phase_timing("cloud_generate")
        logger.info("cloud generation attempt", extra={"request_id": request_id, "model": fallback_name, "attempt": idx + 1})
        cloud_output = await cloud_provider.generate(
            enriched_prompt=cloud_prompt,
            model_name=fallback_name or None,
            context={"memory": memory_context},
            messages=messages,
        )
        if cloud_output.text and not cloud_output.text.startswith("["):
            break
        logger.warning("cloud model failed, trying next fallback", extra={"request_id": request_id, "failed_model": fallback_name})
    if cloud_output is None:
        cloud_output = CloudModelResponse(text="[all models failed]", model_used="none", latency_ms=0, tokens_in=0, tokens_out=0)

    record_tokens(
        request_id,
        "cloud_generation",
        tokens_in=cloud_output.tokens_in,
        tokens_out=cloud_output.tokens_out,
    )

    total_latency = (time.perf_counter() - t_start) * 1000

    memory_content = ""
    if local_output.should_store:
        memory_content = json.dumps(
            {
                "summary": local_output.summary_short,
                "intent": local_output.intent_primary,
                "tags": local_output.memory_tags,
                "local_model": resolved_local_model,
                "cloud_model": resolved_cloud_model,
            },
            ensure_ascii=False,
        )
        save_entry(
            request_id=request_id,
            content=memory_content,
            importance=local_output.memory_importance,
            tags=local_output.memory_tags,
            layer="user",
        )
        write_memory_operation(request_id, "write", "user")

    _persist_request(
        request_id=request_id,
        user_input=input_text,
        messages=messages,
        request_source=request_source,
        local_output=local_output,
        governance_result=police_result,
        cloud_output=cloud_output,
        total_latency=total_latency,
    )

    _log_phase_timing("persist")
    logger.info("phase:completed", extra={
        "request_id": request_id,
        "latency_ms": total_latency,
        "local_degraded": local_degraded,
        "cloud_model": resolved_cloud_model,
        "blocked": False,
        "memory_written": local_output.should_store,
    })

    gateway_response = GatewayResponse(
        request_id=request_id,
        answer_text=cloud_output.text,
        answer_structured=None,
        used_model=f"{local_provider.provider_name} + {cloud_output.model_used}",
        latency_ms=round(total_latency, 2),
        blocked=False,
        rules_applied=police_result["rule_hits"],
        should_write_memory=local_output.should_store,
        memory_content=memory_content,
        local_model_output=local_output,
        cloud_model_response=cloud_output,
        judge_verdict=judge_result["verdict"],
        override_active=override_active,
        local_model_name=resolved_local_model,
        cloud_model_name=resolved_cloud_model,
        local_degraded=local_degraded,
    )

    if not skip_cache and cloud_output.text and not cloud_output.text.startswith("["):
        from app.cache.store import DEFAULT_CACHE_TTL, cache_set
        cache_set(
            user_input=input_text,
            model_name=resolved_cloud_model,
            response={
                "answer_text": cloud_output.text,
                "answer_structured": None,
            },
            messages=messages,
            ttl_seconds=DEFAULT_CACHE_TTL,
        )

    return gateway_response


async def process_request_stream(
    user_input: str = "",
    local_model_name: str = "",
    cloud_model_name: str = "",
    client_id: str = "",
    session_id: str = "",
    request_source: str = "",
    messages: list[dict] | None = None,
):
    request_id = str(uuid.uuid4())
    t_start = time.perf_counter()
    _pt = t_start

    def _log_phase_timing(name: str):
        nonlocal _pt
        now = time.perf_counter()
        elapsed = (now - _pt) * 1000
        _pt = now
        logger.info("perf:phase_timing", extra={"phase": name, "latency_ms": round(elapsed, 2), "request_id": request_id})

    has_messages = messages is not None and len(messages) > 0
    input_text = user_input
    if has_messages and not input_text:
        input_text = extract_text_from_messages(messages)

    logger.info("streaming gateway request started", extra={
        "request_id": request_id,
        "input_length": len(input_text),
        "local_model": local_model_name or "default",
        "cloud_model": cloud_model_name or "default",
        "has_messages": has_messages,
        "client_id": client_id,
        "source": request_source,
    })

    if not check_capability("chat"):
        write_entry(request_id, "capability_denied", "gateway", {"capability": "chat"})
        yield f"data: {json.dumps({'error': 'Chat capability is currently suspended or revoked.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    if is_shutdown_requested():
        write_entry(request_id, "shutdown_blocked", "gateway", {})
        yield f"data: {json.dumps({'error': 'System shutdown has been requested.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    override_active = is_override_active()
    logger.info("phase:governance_check", extra={"request_id": request_id, "override_active": override_active, "has_messages": has_messages})

    if has_messages and messages:
        police_result = police_check_messages(messages)
    else:
        police_result = police_check(input_text)

    write_governance_decision(
        request_id=request_id,
        allowed=police_result["allowed"],
        violations=police_result.get("violations", []),
        rule_hits=police_result.get("rule_hits", []),
    )

    write_step(request_id=request_id, session_id=session_id, client_id=client_id, request_source=request_source, step="governance", latency_ms=0, rule_hits=police_result.get("rule_hits", []))

    judge_result = adjudicate(police_result)

    if judge_result["verdict"] == "blocked":
        _log_phase_timing("governance")
        logger.warning("streaming request blocked by judge", extra={"request_id": request_id, "verdict": judge_result})
        yield f"data: {json.dumps({'error': '请求已被安全策略拦截', 'request_id': request_id})}\n\n"
        yield "data: [DONE]\n\n"
        return

    _log_phase_timing("governance")
    logger.info("phase:local_preprocess", extra={"request_id": request_id, "local_model": local_model_name or "default", "input_length": len(input_text)})

    local_provider = get_local_provider()
    resolved_local_model = local_model_name or ""
    local_output = await local_provider.preprocess(input_text, model_name=resolved_local_model or None, messages=messages)

    local_degraded = local_output.degraded
    effective_input = local_output.filtered_text if not local_degraded else input_text
    _log_phase_timing("local_preprocess")

    memory_context = retrieve_summary_context(layer="user")

    logger.info("phase:cloud_prompt_build", extra={"request_id": request_id, "degraded": local_degraded, "intent": local_output.intent_primary})
    _log_phase_timing("prompt_build")

    cloud_prompt = build_cloud_prompt(
        user_input=effective_input,
        intent=local_output.intent_primary,
        memory_context=memory_context,
        safety_rules="Standard content policy",
        response_style="concise",
        origin_model=f"local_model_{local_provider.provider_name}",
        confidence=local_output.intent_confidence,
    )

    record_tokens(request_id, "local_preprocess", tokens_out=count_tokens(local_output.summary_detailed))

    resolved_cloud = cloud_model_name or resolve_cloud_model()
    scheduled = pick_cloud_model(local_output, messages=messages)
    resolved_cloud_model = scheduled["name"] if scheduled else resolved_cloud

    write_model_routing(
        request_id=request_id,
        local_model=resolved_local_model or local_provider.provider_name,
        cloud_model=resolved_cloud_model,
    )

    logger.info("phase:cloud_schedule", extra={
        "request_id": request_id,
        "primary_model": resolved_cloud_model,
    })
    _log_phase_timing("cloud_schedule")

    cloud_provider = get_cloud_provider()
    collected_text = ""

    logger.info("phase:cloud_generate", extra={"request_id": request_id, "model": resolved_cloud_model, "streaming": True})
    _log_phase_timing("cloud_generate")

    async for text_chunk in cloud_provider.generate_stream(
        enriched_prompt=cloud_prompt,
        model_name=resolved_cloud_model or None,
        messages=messages,
    ):
        collected_text += text_chunk
        yield text_chunk

    total_latency = (time.perf_counter() - t_start) * 1000

    record_tokens(
        request_id,
        "cloud_generation",
        tokens_in=count_tokens(cloud_prompt),
        tokens_out=count_tokens(collected_text),
    )

    memory_content = ""
    if local_output.should_store:
        memory_content = json.dumps(
            {
                "summary": local_output.summary_short,
                "intent": local_output.intent_primary,
                "tags": local_output.memory_tags,
                "local_model": resolved_local_model,
                "cloud_model": resolved_cloud_model,
            },
            ensure_ascii=False,
        )
        save_entry(
            request_id=request_id,
            content=memory_content,
            importance=local_output.memory_importance,
            tags=local_output.memory_tags,
            layer="user",
        )
        write_memory_operation(request_id, "write", "user")

    cloud_output = CloudModelResponse(
        text=collected_text,
        model_used=resolved_cloud_model,
        latency_ms=round(total_latency, 2),
        tokens_in=count_tokens(cloud_prompt),
        tokens_out=count_tokens(collected_text),
    )

    _persist_request(
        request_id=request_id,
        user_input=input_text,
        messages=messages,
        request_source=request_source,
        local_output=local_output,
        governance_result=police_result,
        cloud_output=cloud_output,
        total_latency=total_latency,
    )

    _log_phase_timing("persist")
    logger.info("phase:completed", extra={
        "request_id": request_id,
        "latency_ms": total_latency,
        "local_degraded": local_degraded,
        "cloud_model": resolved_cloud_model,
        "streaming": True,
        "memory_written": local_output.should_store,
    })

    if collected_text and not collected_text.startswith("["):
        from app.cache.store import DEFAULT_CACHE_TTL, cache_set
        cache_set(
            user_input=input_text,
            model_name=resolved_cloud_model,
            response={"answer_text": collected_text, "answer_structured": None},
            messages=messages,
            ttl_seconds=DEFAULT_CACHE_TTL,
        )

    logger.info("streaming gateway request completed", extra={"request_id": request_id, "latency_ms": total_latency, "local_degraded": local_degraded})


def _persist_request(
    request_id: str,
    user_input: str,
    messages: list[dict] | None,
    request_source: str,
    local_output: LocalModelOutput,
    governance_result: dict,
    cloud_output: CloudModelResponse,
    total_latency: float,
):
    raw_text = user_input
    if messages:
        raw_text = json.dumps(messages, ensure_ascii=False)
    conn = get_connection()
    conn.execute(
        """INSERT INTO requests (id, user_input_raw, local_model_output, governance_result, routing_decision, cloud_model_response, final_response, latency_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            request_id,
            raw_text,
            json.dumps(local_output.__dict__, ensure_ascii=False, default=str),
            json.dumps(governance_result, ensure_ascii=False),
            json.dumps({"selected_model": local_output.model_suggestion, "strategy": local_output.routing_reason, "source": request_source}, ensure_ascii=False),
            json.dumps(cloud_output.__dict__, ensure_ascii=False, default=str),
            cloud_output.text,
            round(total_latency, 2),
        ),
    )
    conn.commit()


def get_request_history(limit: int = 50, offset: int = 0) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, timestamp, user_input_raw, latency_ms FROM requests ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [dict(row) for row in rows]


def get_request_detail(request_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if row is None:
        return None
    return dict(row)
