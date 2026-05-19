import json
import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel

from app.admin.config_manager import (
    get_config,
    update_local_config,
    update_cloud_config,
    reload_config,
    get_local_config,
    get_cloud_config,
    resolve_runtime_local_config,
    resolve_runtime_cloud_config,
    get_cloud_models,
    add_cloud_model,
    update_cloud_model,
    delete_cloud_model,
)
from app.admin import api_keys
from app.governance.engine import list_rules, add_rule, toggle_rule, delete_rule
from app.core.config import settings
from app.core.logging import logger
from app.core.database import get_connection
from app.providers.model_validator import get_allowed_local_models, get_allowed_cloud_models
from app.providers.registry import list_engine_models, SUPPORTED_ENGINES

admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/config")
async def admin_config():
    return get_config(mask_secrets=True)


class LocalConfigUpdate(BaseModel):
    provider: str | None = None
    api_url: str | None = None
    default_model: str | None = None
    timeout_seconds: int | None = None
    max_tokens: int | None = None
    api_key: str | None = None


@admin_router.post("/config/local")
async def admin_config_local(req: LocalConfigUpdate):
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="no fields to update")
    update_local_config(data)
    return {"status": "ok", "updated": list(data.keys())}


class CloudConfigUpdate(BaseModel):
    provider: str | None = None
    api_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None
    timeout_seconds: int | None = None


@admin_router.post("/config/cloud")
async def admin_config_cloud(req: CloudConfigUpdate):
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="no fields to update")
    if ("provider" in data or "api_url" in data or "api_key" in data) and "default_model" not in data and "default" not in data:
        raise HTTPException(
            status_code=400,
            detail="use /admin/config/cloud/models for per-model config. to set default model, send {\"default_model\": \"...\"}"
        )
    update_cloud_config(data)
    return {"status": "ok", "updated": list(data.keys())}


class CloudModelCreate(BaseModel):
    name: str
    provider: str = "openai-compatible"
    api_url: str = ""
    api_key: str = ""
    timeout_seconds: int = 60
    weight: int = 1
    tags: list[str] = ["general"]


@admin_router.get("/config/cloud/models")
async def admin_cloud_models():
    return {"models": get_cloud_models()}


@admin_router.post("/config/cloud/models")
async def admin_cloud_model_add(req: CloudModelCreate):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="model name is required")
    add_cloud_model(req.name, req.model_dump())
    return {"status": "ok", "model": req.name}


@admin_router.put("/config/cloud/models/{name}")
async def admin_cloud_model_update(name: str, req: CloudModelCreate):
    if not name.strip():
        raise HTTPException(status_code=400, detail="model name is required")
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    update_cloud_model(name, data)
    return {"status": "ok", "model": name}


@admin_router.delete("/config/cloud/models/{name}")
async def admin_cloud_model_delete(name: str):
    delete_cloud_model(name)
    return {"status": "ok", "model": name}


@admin_router.post("/config/cloud/default")
async def admin_cloud_default(name: str = Query(...)):
    update_cloud_config({"default": name})
    return {"status": "ok", "default": name}


@admin_router.post("/config/reload")
async def admin_config_reload():
    reload_config()
    return {"status": "ok", "message": "configuration reloaded from disk"}


@admin_router.get("/rules")
async def admin_rules():
    return {"rules": list_rules()}


class RuleCreate(BaseModel):
    rule_type: str
    pattern: str
    action: str = "block"
    priority: int = 0


@admin_router.post("/rules")
async def admin_rule_add(req: RuleCreate):
    if not req.rule_type.strip() or not req.pattern.strip():
        raise HTTPException(status_code=400, detail="rule_type and pattern are required")
    add_rule(req.rule_type, req.pattern, req.action, req.priority)
    return {"status": "ok"}


@admin_router.put("/rules/{rule_id}/toggle")
async def admin_rule_toggle(rule_id: int, enabled: bool = Query(True)):
    toggle_rule(rule_id, enabled)
    return {"status": "ok", "rule_id": rule_id, "enabled": enabled}


@admin_router.delete("/rules/{rule_id}")
async def admin_rule_delete(rule_id: int):
    delete_rule(rule_id)
    return {"status": "ok", "rule_id": rule_id}


class ApiKeyCreate(BaseModel):
    alias: str


def resolve_client_from_header(authorization: str | None = Header(None), strict: bool = False) -> tuple[str, str]:
    if not authorization:
        if strict:
            raise HTTPException(status_code=401, detail="Missing API Key. Use Authorization: Bearer sk-gw-...")
        return "anonymous", "direct"
    raw = authorization.removeprefix("Bearer ").removeprefix("bearer ").strip()
    if not raw or raw == "sk-gateway":
        if strict:
            raise HTTPException(status_code=401, detail="Invalid API Key. Generate a key from the console.")
        return "anonymous", "direct"
    entry = api_keys.validate_key(raw)
    if entry:
        api_keys.record_key_usage(raw)
        return entry["client_id"], f"key:{entry['alias']}"
    if strict:
        raise HTTPException(status_code=401, detail="Invalid API Key. Key not recognized or has been disabled.")
    return "unauthorized", "direct"


@admin_router.get("/api-keys")
async def admin_api_keys():
    return {"keys": api_keys.list_keys()}


@admin_router.post("/api-keys")
async def admin_api_key_create(req: ApiKeyCreate):
    key = api_keys.generate_key(req.alias)
    return {"api_key": key, "alias": req.alias}


@admin_router.delete("/api-keys")
async def admin_api_key_delete(key_prefix: str = Query(...), key_hash: str = Query(...)):
    ok = api_keys.delete_key(key_prefix, key_hash)
    if not ok:
        raise HTTPException(status_code=404, detail="key not found")
    return {"status": "ok"}


@admin_router.post("/api-keys/toggle")
async def admin_api_key_toggle(key_prefix: str = Query(...), key_hash: str = Query(...), enabled: bool = Query(...)):
    ok = api_keys.toggle_key(key_prefix, key_hash, enabled)
    if not ok:
        raise HTTPException(status_code=404, detail="key not found")
    return {"status": "ok", "enabled": enabled}


@admin_router.get("/overview")
async def admin_overview():
    conn = get_connection()

    requests_row = conn.execute("SELECT COUNT(*) as cnt FROM requests").fetchone()
    total_requests = dict(requests_row)["cnt"]

    token_row = conn.execute(
        "SELECT COALESCE(SUM(tokens_in),0) as tokens_in, COALESCE(SUM(tokens_out),0) as tokens_out FROM token_usage"
    ).fetchone()
    token_data = dict(token_row)
    total_tokens_in = token_data["tokens_in"]
    total_tokens_out = token_data["tokens_out"]

    preprocess_row = conn.execute(
        "SELECT COUNT(*) as cnt FROM requests WHERE local_model_output IS NOT NULL"
    ).fetchone()

    memory_row = conn.execute("SELECT COUNT(*) as cnt FROM memory_entries").fetchone()
    total_memory = dict(memory_row)["cnt"]

    blocked_row = conn.execute(
        "SELECT COUNT(*) as cnt FROM audit_log WHERE event_type = 'governance_decision'"
    ).fetchone()
    blocked_cnt = dict(blocked_row)["cnt"]

    blocked_detail = conn.execute(
        "SELECT detail_json FROM audit_log WHERE event_type = 'governance_decision' ORDER BY id DESC LIMIT 200"
    ).fetchall()
    blocked_total = 0
    high_risk_total = 0
    for row in blocked_detail:
        try:
            detail = json.loads(row["detail_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not detail.get("allowed", True):
            blocked_total += 1
        if detail.get("violations"):
            high_risk_total += 1

    local_cfg = resolve_runtime_local_config()
    cloud_cfg = resolve_runtime_cloud_config()
    config_mask = get_config(mask_secrets=True)

    return {
        "gateway_info": {
            "host": settings.host,
            "port": settings.port,
            "api_base": f"http://localhost:{settings.port}/v1",
            "api_key_placeholder": "sk-gateway",
            "model_placeholder": "auto",
            "console_url": f"http://localhost:{settings.port}/console",
            "docs_url": f"http://localhost:{settings.port}/docs",
        },
        "models": {
            "local": {
                "default": local_cfg.get("default_model", ""),
                "allowed_count": len(get_allowed_local_models()),
            },
            "cloud": {
                "default": cloud_cfg.get("default_model", ""),
                "allowed_count": len(get_allowed_cloud_models()),
            },
        },
        "metrics": {
            "total_requests": total_requests,
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "total_tokens": total_tokens_in + total_tokens_out,
            "preprocess_calls": dict(preprocess_row)["cnt"],
            "memory_entries": total_memory,
            "blocked_requests": blocked_total,
            "high_risk_flags": high_risk_total,
            "governance_decisions": blocked_cnt,
        },
        "current_config": config_mask,
    }


@admin_router.get("/clients")
async def admin_clients(
    hours: int = Query(24, ge=1, le=720),
):
    audit_path = settings.audit_log_path
    if not os.path.exists(audit_path):
        return {"clients": [], "total": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    clients: dict[str, dict] = {}

    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = entry.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                except (ValueError, TypeError):
                    continue
                if ts < cutoff:
                    continue
                client_id = entry.get("client_id", "") or entry.get("session_id", "") or "unknown"
                if client_id not in clients:
                    clients[client_id] = {
                        "client_id": client_id,
                        "first_seen": ts_str,
                        "last_seen": ts_str,
                        "request_count": 0,
                    }
                clients[client_id]["last_seen"] = ts_str
                clients[client_id]["request_count"] += 1
    except Exception as e:
        logger.error("failed to read audit log for clients", extra={"error": str(e)})
        return {"clients": [], "total": 0, "error": str(e)}

    client_list = sorted(clients.values(), key=lambda x: x["request_count"], reverse=True)
    return {"clients": client_list, "total": len(client_list)}


@admin_router.get("/token-trend")
async def admin_token_trend(hours: int = Query(24, ge=1, le=168)):
    conn = get_connection()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:00:00")
    rows = conn.execute(
        "SELECT created_at, COALESCE(SUM(tokens_in),0) as tin, COALESCE(SUM(tokens_out),0) as tout "
        "FROM token_usage WHERE created_at >= ? "
        "GROUP BY substr(created_at, 1, 13) ORDER BY created_at ASC",
        (cutoff,)
    ).fetchall()
    result = []
    for row in rows:
        row_dict = dict(row)
        hour = row_dict["created_at"][11:13] + ":00"
        result.append({"hour": hour, "tokens": row_dict["tin"] + row_dict["tout"]})
    return {"hours": hours, "data": result}


class AllowedModelsUpdate(BaseModel):
    local: list[str] = []
    cloud: list[str] = []


@admin_router.get("/engines/models")
async def admin_engine_models(refresh: bool = Query(False)):
    cfg = get_config()
    local = cfg.get("local", {})
    provider = local.get("provider", "mock")
    api_url = local.get("api_url", "")
    allowed = get_allowed_local_models()
    engine_models = []
    if refresh and provider != "mock":
        engine_models = await list_engine_models(provider, api_url)
    return {
        "provider": provider,
        "api_url": api_url,
        "engine_models": engine_models,
        "allowed_models": allowed,
        "supported_engines": SUPPORTED_ENGINES,
    }


@admin_router.get("/allowed-models")
async def admin_get_allowed_models():
    return {
        "local": get_allowed_local_models(),
        "cloud": get_allowed_cloud_models(),
    }


@admin_router.put("/allowed-models")
async def admin_set_allowed_models(req: AllowedModelsUpdate):
    path = settings.allowed_models_path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"local": req.local, "cloud": req.cloud}, f, ensure_ascii=False, indent=2)
    return {"status": "ok", "local": req.local, "cloud": req.cloud}


@admin_router.get("/cache/stats")
async def admin_cache_stats():
    from app.cache.store import cache_stats
    return cache_stats()


@admin_router.post("/cache/invalidate")
async def admin_cache_invalidate(model_name: str | None = Query(None)):
    from app.cache.store import cache_invalidate
    removed = cache_invalidate(model_name=model_name)
    return {"status": "ok", "entries_removed": removed}


@admin_router.post("/cache/cleanup")
async def admin_cache_cleanup():
    from app.cache.store import cache_cleanup
    cache_cleanup()
    return {"status": "ok", "message": "expired cache entries cleaned"}


@admin_router.get("/feedback")
async def admin_feedback(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    conn = get_connection()
    rows = conn.execute(
        "SELECT f.id, f.request_id, f.rating, f.comment, f.created_at, r.user_input_raw "
        "FROM feedback f LEFT JOIN requests r ON f.request_id = r.id "
        "ORDER BY f.created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) as cnt FROM feedback").fetchone()
    return {"items": [dict(row) for row in rows], "total": dict(total)["cnt"], "limit": limit, "offset": offset}


@admin_router.get("/feedback/stats")
async def admin_feedback_stats():
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as total, COALESCE(SUM(CASE WHEN rating > 0 THEN 1 ELSE 0 END), 0) as positive, "
        "COALESCE(SUM(CASE WHEN rating < 0 THEN 1 ELSE 0 END), 0) as negative "
        "FROM feedback"
    ).fetchone()
    return dict(row)
