import hashlib
import json
import re
import time

from app.core.database import get_connection
from app.core.logging import logger

DEFAULT_CACHE_TTL = 3600


def _normalize_text(text: str) -> str:
    """缓存 key 归一化：去首尾空白、小写、合并多余空格、去首尾常见标点。

    使 'Hello!' 和 'hello' 命中同一个缓存。
    """
    text = text.strip().lower()
    text = re.sub(r'\s+', ' ', text)
    text = text.strip(' \t\n\r!?.,;:。？！，、；：')
    return text


def _normalize_messages(messages: list[dict] | None) -> list[dict] | None:
    """对 messages 中的 content 做归一化。"""
    if not messages:
        return messages
    result = []
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            content = _normalize_text(content)
        elif isinstance(content, list):
            content = [_normalize_text(c) if isinstance(c, str) else c for c in content]
        result.append({"role": m.get("role", ""), "content": content})
    return result


def _hash_key(user_input: str, model_name: str, messages: list[dict] | None = None, temperature: float = 0.7) -> str:
    normalized_input = _normalize_text(user_input)
    normalized_msgs = _normalize_messages(messages)
    raw = json.dumps(
        {
            "input": normalized_input,
            "model": model_name,
            "messages": normalized_msgs or [],
            "temperature": temperature,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_get(user_input: str, model_name: str, messages: list[dict] | None = None, temperature: float = 0.7) -> dict | None:
    key = _hash_key(user_input, model_name, messages, temperature)
    conn = get_connection()
    row = conn.execute(
        "SELECT response_json, ttl_seconds FROM response_cache WHERE cache_key = ? "
        "AND (ttl_seconds <= 0 OR (julianday('now') - julianday(created_at)) * 86400 <= ttl_seconds) "
        "ORDER BY id DESC LIMIT 1",
        (key,),
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["response_json"])
    except (json.JSONDecodeError, TypeError):
        return None


def cache_set(
    user_input: str,
    model_name: str,
    response: dict,
    messages: list[dict] | None = None,
    temperature: float = 0.7,
    ttl_seconds: int = DEFAULT_CACHE_TTL,
):
    key = _hash_key(user_input, model_name, messages, temperature)
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO response_cache (cache_key, response_json, model_name, created_at, ttl_seconds) VALUES (?, ?, ?, datetime('now'), ?)",
        (key, json.dumps(response, ensure_ascii=False), model_name, ttl_seconds),
    )
    conn.commit()
    logger.debug("cache entry stored", extra={"cache_key": key[:16], "model": model_name, "ttl": ttl_seconds})


def cache_invalidate(user_input: str | None = None, model_name: str | None = None):
    conn = get_connection()
    removed = 0
    if user_input and model_name:
        key = _hash_key(user_input, model_name)
        cursor = conn.execute("DELETE FROM response_cache WHERE cache_key = ?", (key,))
        removed = cursor.rowcount
    elif model_name:
        cursor = conn.execute("DELETE FROM response_cache WHERE model_name = ?", (model_name,))
        removed = cursor.rowcount
    else:
        cursor = conn.execute("DELETE FROM response_cache")
        removed = cursor.rowcount
    conn.commit()
    logger.info("cache invalidated", extra={"entries_removed": removed, "model": model_name})
    return removed


def cache_stats() -> dict:
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as cnt FROM response_cache").fetchone()
    total = dict(row)["cnt"]
    return {"total_entries": total, "ttl_default": DEFAULT_CACHE_TTL}


def cache_cleanup():
    conn = get_connection()
    conn.execute(
        "DELETE FROM response_cache WHERE ttl_seconds > 0 AND (julianday('now') - julianday(created_at)) * 86400 > ttl_seconds"
    )
    conn.commit()
