import hashlib
import json
import time

from app.core.database import get_connection
from app.core.logging import logger

DEFAULT_CACHE_TTL = 3600


def _hash_key(user_input: str, model_name: str, messages: list[dict] | None = None, temperature: float = 0.7) -> str:
    raw = json.dumps(
        {
            "input": user_input,
            "model": model_name,
            "messages": messages or [],
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
