import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.gateway.engine import process_request, get_request_history, get_request_detail
from app.memory.store import list_all as memory_list, get_count as memory_count, retrieve_summary_context
from app.governance.engine import list_rules, add_rule, toggle_rule
from app.tokenflow.tracker import get_total_usage
from app.providers.model_validator import resolve_local_model, resolve_cloud_model, get_allowed_local_models, get_allowed_cloud_models
from app.admin.router import admin_router, resolve_client_from_header
from app.admin.auth import AdminAuthMiddleware
from app.core.ratelimit import RateLimitMiddleware
from app.core.metrics import metrics_router
from app.api.openai_compat import openai_router
from app.core.config import settings


def _init_doctrine():
    from app.core.doctrine import _init_default_capabilities
    _init_default_capabilities()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_doctrine()
    yield


app = FastAPI(title="AI Cognitive Gateway", lifespan=lifespan)
app.add_middleware(AdminAuthMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
router = APIRouter()


class ModelSelection(BaseModel):
    local: str | None = None
    cloud: str | None = None


class ChatRequest(BaseModel):
    user_input: str
    session_id: str | None = None
    model: ModelSelection | None = None
    metadata: dict | None = None


@router.post("/chat")
async def chat(req: ChatRequest, authorization: str | None = Header(None)):
    if not req.user_input.strip():
        raise HTTPException(status_code=400, detail="user_input is required")

    local_model = ""
    cloud_model = ""

    try:
        if req.model:
            local_model = resolve_local_model(req.model.local)
            cloud_model = resolve_cloud_model(req.model.cloud)
        else:
            local_model = resolve_local_model()
            cloud_model = resolve_cloud_model()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    client_id = ""
    if req.metadata and isinstance(req.metadata, dict):
        client_id = req.metadata.get("client_id", "") or ""
    if not client_id:
        client_id = req.session_id or ""

    header_client_id, request_source = resolve_client_from_header(authorization)
    if header_client_id != "anonymous":
        client_id = header_client_id

    if not client_id:
        client_id = "legacy_chat"

    result = await process_request(
        req.user_input,
        local_model_name=local_model,
        cloud_model_name=cloud_model,
        client_id=client_id,
        session_id=req.session_id or "",
        request_source=request_source,
    )
    return result.to_dict()


@router.get("/models")
async def allowed_models():
    return {
        "local": get_allowed_local_models(),
        "cloud": get_allowed_cloud_models(),
    }


@router.get("/history")
async def history(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    rows = get_request_history(limit=limit, offset=offset)
    return {"items": rows, "limit": limit, "offset": offset}


@router.get("/history/{request_id}")
async def history_detail(request_id: str):
    detail = get_request_detail(request_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="request not found")
    return detail


@router.get("/memory")
async def memory(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    rows = memory_list(limit=limit, offset=offset)
    return {"items": rows, "total": memory_count(), "limit": limit, "offset": offset}


@router.get("/memory/context")
async def memory_context():
    context = retrieve_summary_context()
    return {"context": context}


@router.post("/memory/compress")
async def memory_compress(threshold: float = Query(0.2, ge=0.0, le=0.9)):
    from app.memory.store import compress_low_value
    compress_low_value(threshold)
    return {"status": "ok", "threshold": threshold}


@router.get("/governance/rules")
async def governance_rules():
    return {"rules": list_rules()}


class AddRuleRequest(BaseModel):
    rule_type: str
    pattern: str
    action: str = "block"
    priority: int = 0


@router.post("/governance/rules")
async def governance_add_rule(req: AddRuleRequest):
    if req.action not in ("block", "allow"):
        raise HTTPException(status_code=400, detail="action must be 'block' or 'allow'")
    add_rule(req.rule_type, req.pattern, req.action, req.priority)
    return {"status": "ok"}


@router.put("/governance/rules/{rule_id}/toggle")
async def governance_toggle_rule(rule_id: int, enabled: bool = Query(True)):
    toggle_rule(rule_id, enabled)
    return {"status": "ok", "rule_id": rule_id, "enabled": enabled}


@router.get("/token-usage")
async def token_usage():
    return get_total_usage()


@router.get("/admin/override")
async def admin_override_status():
    from app.core.doctrine import get_override_status
    return get_override_status()


class OverrideRequest(BaseModel):
    reason: str = ""


@router.post("/admin/override/activate")
async def admin_override_activate(req: OverrideRequest):
    from app.core.doctrine import activate_override
    from app.core.audit import write_override_activated
    activate_override(req.reason)
    write_override_activated(req.reason)
    return {"status": "ok", "override_active": True}


@router.post("/admin/override/deactivate")
async def admin_override_deactivate():
    from app.core.doctrine import deactivate_override
    from app.core.audit import write_override_deactivated
    deactivate_override()
    write_override_deactivated()
    return {"status": "ok", "override_active": False}


@router.post("/admin/shutdown")
async def admin_shutdown():
    from app.core.doctrine import request_shutdown
    from app.core.audit import write_shutdown_requested
    request_shutdown()
    write_shutdown_requested()
    return {"status": "ok", "shutdown_requested": True, "message": "New requests will be rejected. Restart server to resume."}


@router.get("/admin/capabilities")
async def admin_capabilities():
    from app.core.doctrine import list_capabilities
    return {"capabilities": list_capabilities()}


class CapabilityRequest(BaseModel):
    name: str


@router.post("/admin/capabilities/grant")
async def admin_capability_grant(req: CapabilityRequest):
    from app.core.doctrine import grant_capability
    grant_capability(req.name)
    return {"status": "ok", "capability": req.name, "state": "granted"}


@router.post("/admin/capabilities/suspend")
async def admin_capability_suspend(req: CapabilityRequest):
    from app.core.doctrine import suspend_capability
    suspend_capability(req.name)
    return {"status": "ok", "capability": req.name, "state": "suspended"}


@router.post("/admin/capabilities/revoke")
async def admin_capability_revoke(req: CapabilityRequest):
    from app.core.doctrine import revoke_capability
    revoke_capability(req.name)
    return {"status": "ok", "capability": req.name, "state": "revoked"}


@router.get("/audit")
async def audit_log(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: str | None = Query(None),
):
    from app.core.audit import query as audit_query, count as audit_count
    entries = audit_query(limit=limit, offset=offset, event_type=event_type)
    return {"items": entries, "total": audit_count(event_type=event_type), "limit": limit, "offset": offset}


@router.get("/console", response_class=HTMLResponse)
async def admin_console():
    console_path = Path(__file__).parent.parent / "admin" / "static" / "index.html"
    if not console_path.exists():
        raise HTTPException(status_code=404, detail="console not found")
    return HTMLResponse(console_path.read_text(encoding="utf-8"))


app.include_router(router)
app.include_router(admin_router)
app.include_router(openai_router)
app.include_router(metrics_router)


@app.get("/health")
async def health():
    """Health check endpoint for load balancer and monitoring."""
    from app.core.config import settings
    from app.core.doctrine import is_override_active, is_shutdown_requested
    from app.core.database import get_connection

    services = {
        "server": {"status": "ok"},
        "database": {"status": "unknown"},
        "local_model": {"mode": settings.local_model_mode},
        "cloud_model": {"default": settings.default_cloud_model},
    }

    try:
        conn = get_connection()
        conn.execute("SELECT 1")
        services["database"]["status"] = "ok"
    except Exception as e:
        services["database"]["status"] = "error"
        services["database"]["detail"] = str(e)

    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": services,
        "runtime": {
            "override_active": is_override_active(),
            "shutdown_requested": is_shutdown_requested(),
        },
    }


_static_dir = Path(__file__).parent.parent / "admin" / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
