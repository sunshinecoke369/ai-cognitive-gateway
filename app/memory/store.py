import json
import sqlite3

from app.core.database import get_connection
from app.core.logging import logger


def save_entry(
    request_id: str,
    content: str,
    importance: float = 0.0,
    tags: list[str] | None = None,
    layer: str = "user",
):
    conn = get_connection()
    tags_json = json.dumps(tags or [], ensure_ascii=False)
    conn.execute(
        "INSERT INTO memory_entries (request_id, layer, content, importance, tags) VALUES (?, ?, ?, ?, ?)",
        (request_id, layer, content, importance, tags_json),
    )
    conn.commit()
    logger.info("memory entry saved", extra={"request_id": request_id, "layer": layer, "importance": importance})


def retrieve_recent(limit: int = 10, layer: str | None = None) -> list[dict]:
    conn = get_connection()
    if layer:
        rows = conn.execute(
            "SELECT id, request_id, layer, content, importance, tags, created_at FROM memory_entries WHERE layer = ? ORDER BY id DESC LIMIT ?",
            (layer, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, request_id, layer, content, importance, tags, created_at FROM memory_entries ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def retrieve_summary_context(layer: str | None = None) -> str:
    entries = retrieve_recent(5, layer=layer)
    if not entries:
        return ""
    parts = []
    for entry in entries:
        content = entry["content"]
        if content:
            parts.append(content[:200])
    return "\n---\n".join(parts)


def list_all(limit: int = 50, offset: int = 0, layer: str | None = None) -> list[dict]:
    conn = get_connection()
    if layer:
        rows = conn.execute(
            "SELECT id, request_id, layer, content, importance, tags, created_at FROM memory_entries WHERE layer = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (layer, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, request_id, layer, content, importance, tags, created_at FROM memory_entries ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(row) for row in rows]


def get_count(layer: str | None = None) -> int:
    conn = get_connection()
    if layer:
        row = conn.execute("SELECT COUNT(*) as cnt FROM memory_entries WHERE layer = ?", (layer,)).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) as cnt FROM memory_entries").fetchone()
    return row["cnt"]


def clean_layer(layer: str):
    conn = get_connection()
    conn.execute("DELETE FROM memory_entries WHERE layer = ?", (layer,))
    conn.commit()
    logger.warning("memory layer cleaned", extra={"layer": layer})


def compress_low_value(threshold: float = 0.2):
    conn = get_connection()
    conn.execute("DELETE FROM memory_entries WHERE importance < ?", (threshold,))
    conn.commit()
    logger.info("low value memory compressed", extra={"threshold": threshold})
