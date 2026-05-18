import json
import os
from datetime import datetime, timezone

from app.core.database import get_connection
from app.core.config import settings
from app.core.logging import logger

_AUDIT_SEQUENCE = 0


def _next_sequence() -> int:
    global _AUDIT_SEQUENCE
    _AUDIT_SEQUENCE += 1
    return _AUDIT_SEQUENCE


def _write_jsonl(entry: dict):
    try:
        audit_path = settings.audit_log_path
        os.makedirs(os.path.dirname(audit_path), exist_ok=True)
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("failed to write audit jsonl", extra={"error": str(e)})


def write_entry(
    request_id: str,
    event_type: str,
    actor: str,
    detail: dict | None = None,
):
    conn = get_connection()
    entry = {
        "sequence": _next_sequence(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "actor": actor,
        "detail": detail or {},
    }
    conn.execute(
        "INSERT INTO audit_log (request_id, event_type, actor, detail_json) VALUES (?, ?, ?, ?)",
        (request_id, event_type, actor, json.dumps(entry, ensure_ascii=False)),
    )
    conn.commit()
    _write_jsonl(entry)
    logger.debug("audit entry written", extra={"request_id": request_id, "event_type": event_type})


def write_step(
    request_id: str,
    session_id: str = "",
    client_id: str = "",
    request_source: str = "",
    step: str = "",
    latency_ms: float = 0.0,
    rule_hits: list | None = None,
    error: str | None = None,
):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "session_id": session_id,
        "client_id": client_id,
        "source": request_source,
        "step": step,
        "latency_ms": round(latency_ms, 2),
        "rule_hits": rule_hits or [],
        "error": error,
    }
    _write_jsonl(entry)


def write_governance_decision(
    request_id: str,
    allowed: bool,
    violations: list[str],
    rule_hits: list[int],
):
    write_entry(
        request_id=request_id,
        event_type="governance_decision",
        actor="police",
        detail={
            "allowed": allowed,
            "violations": violations,
            "rule_hits": rule_hits,
        },
    )


def write_model_routing(
    request_id: str,
    local_model: str,
    cloud_model: str,
):
    write_entry(
        request_id=request_id,
        event_type="model_routing",
        actor="gateway",
        detail={
            "local_model": local_model,
            "cloud_model": cloud_model,
        },
    )


def write_memory_operation(
    request_id: str,
    operation: str,
    memory_layer: str,
):
    write_entry(
        request_id=request_id,
        event_type="memory_operation",
        actor="gateway",
        detail={
            "operation": operation,
            "memory_layer": memory_layer,
        },
    )


def write_override_activated(reason: str):
    write_entry(
        request_id="system",
        event_type="human_override",
        actor="human_operator",
        detail={"reason": reason, "action": "activated"},
    )


def write_override_deactivated():
    write_entry(
        request_id="system",
        event_type="human_override",
        actor="human_operator",
        detail={"action": "deactivated"},
    )


def write_shutdown_requested():
    write_entry(
        request_id="system",
        event_type="shutdown",
        actor="human_operator",
        detail={"action": "shutdown_requested"},
    )


def query(limit: int = 100, offset: int = 0, event_type: str | None = None) -> list[dict]:
    conn = get_connection()
    if event_type:
        rows = conn.execute(
            "SELECT id, request_id, event_type, actor, detail_json, created_at FROM audit_log WHERE event_type = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (event_type, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, request_id, event_type, actor, detail_json, created_at FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    result = []
    for row in rows:
        entry = dict(row)
        try:
            entry["detail"] = json.loads(entry["detail_json"])
        except (json.JSONDecodeError, KeyError):
            entry["detail"] = {}
        entry.pop("detail_json", None)
        result.append(entry)
    return result


def count(event_type: str | None = None) -> int:
    conn = get_connection()
    if event_type:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM audit_log WHERE event_type = ?",
            (event_type,),
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) as cnt FROM audit_log").fetchone()
    return row["cnt"]
