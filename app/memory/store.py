import json
import sqlite3

from app.core.database import get_connection
from app.core.logging import logger
from app.memory.layers import MemoryLayer

# ── 写操作 ──


def save_entry(
    request_id: str,
    content: str,
    importance: float = 0.0,
    tags: list[str] | None = None,
    layer: str = "user",
):
    """写入记忆条目。

    参数:
        layer: 记忆层级（session / user / agent / governance），默认 user。
    """
    conn = get_connection()
    tags_json = json.dumps(tags or [], ensure_ascii=False)
    conn.execute(
        "INSERT INTO memory_entries (request_id, layer, content, importance, tags) VALUES (?, ?, ?, ?, ?)",
        (request_id, layer, content, importance, tags_json),
    )
    conn.commit()
    logger.info("memory entry saved", extra={"request_id": request_id, "layer": layer, "importance": importance})


# ── 读操作 ──


def retrieve_recent(limit: int = 10, layer: str | None = None) -> list[dict]:
    """获取最近的记忆条目，可按层级过滤。"""
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
    """获取记忆摘要上下文（用于拼入 prompt）。"""
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
    """分页列出记忆条目。"""
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
    """获取记忆条目总数。"""
    conn = get_connection()
    if layer:
        row = conn.execute("SELECT COUNT(*) as cnt FROM memory_entries WHERE layer = ?", (layer,)).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) as cnt FROM memory_entries").fetchone()
    return row["cnt"]


# ── 层管理 ──


def get_layer_stats() -> dict[str, int]:
    """返回各层记忆条目数。"""
    conn = get_connection()
    stats = {}
    for layer in MemoryLayer:
        row = conn.execute("SELECT COUNT(*) as cnt FROM memory_entries WHERE layer = ?", (layer.value,)).fetchone()
        stats[layer.value] = row["cnt"]
    return stats


def compress_expired():
    """清理所有已过 TTL 的层级记忆条目。

    根据各层定义的 ttl_seconds 删除过期条目。
    session 层 1h、agent 层 30d。
    """
    conn = get_connection()
    total = 0
    for layer in MemoryLayer:
        ttl = layer.ttl_seconds
        if ttl is None:
            continue
        removed = conn.execute(
            "DELETE FROM memory_entries WHERE layer = ? AND (julianday('now') - julianday(created_at)) * 86400 > ?",
            (layer.value, ttl),
        ).rowcount
        if removed:
            logger.info("expired memory cleaned", extra={"layer": layer.value, "entries_removed": removed})
        total += removed
    conn.commit()
    return total


def clean_layer(layer: str):
    """清空指定层全部记忆。"""
    conn = get_connection()
    conn.execute("DELETE FROM memory_entries WHERE layer = ?", (layer,))
    conn.commit()
    logger.warning("memory layer cleaned", extra={"layer": layer})


def compress_low_value(threshold: float = 0.2):
    """删除低重要性记忆（跨所有层）。"""
    conn = get_connection()
    conn.execute("DELETE FROM memory_entries WHERE importance < ?", (threshold,))
    conn.commit()
    logger.info("low value memory compressed", extra={"threshold": threshold})
