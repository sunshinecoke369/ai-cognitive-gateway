import hashlib
import json
import os
import secrets
import string
import time
from datetime import datetime, timezone

from app.core.logging import logger

_KEYS_PATH = "data/api_keys.json"
_alphabet = string.ascii_letters + string.digits


def _keys_path() -> str:
    os.makedirs(os.path.dirname(_KEYS_PATH), exist_ok=True)
    return _KEYS_PATH


def _load_keys() -> dict:
    path = _keys_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save_keys(data: dict):
    path = _keys_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _migrate_legacy_keys(keys: dict) -> dict:
    """将旧格式（完全明文字典键）迁移为哈希格式。幂等安全。"""
    migrated = {}
    for k, entry in keys.items():
        if k.startswith("sk-gw-"):
            # 旧格式：k 是完整明文 key → 哈希化
            hashed = hashlib.sha256(k.encode()).hexdigest()
            entry["key_hash"] = hashlib.sha256(k.encode()).hexdigest()[:16]
            migrated[hashed] = entry
        else:
            # 已经是哈希格式
            migrated[k] = entry
    if len(migrated) != len(keys):
        logger.info("legacy api keys migrated to hash storage", extra={"count": len(migrated)})
    return migrated


def generate_key(alias: str) -> str:
    ts = hex(int(time.time() * 1000))[2:]
    rand = secrets.token_hex(4)
    key = f"sk-gw-{ts}{rand}"
    client_id = alias.lower().replace(" ", "-") if alias.strip() else "agent"

    key_hash_full = hashlib.sha256(key.encode()).hexdigest()
    keys = _load_keys()
    keys = _migrate_legacy_keys(keys)
    keys[key_hash_full] = {
        "alias": alias.strip() or "Agent",
        "client_id": client_id,
        "key_hash": key_hash_full[:16],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_used": None,
        "request_count": 0,
        "enabled": True,
    }
    _save_keys(keys)
    logger.info("api key generated", extra={"alias": alias, "client_id": client_id})
    # 只返回一次明文，不存储
    return key


def validate_key(raw_key: str) -> dict | None:
    keys = _load_keys()
    keys = _migrate_legacy_keys(keys)
    raw_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    entry = keys.get(raw_hash)
    if entry is None:
        return None
    if not entry.get("enabled", True):
        return None
    return entry


def record_key_usage(raw_key: str):
    keys = _load_keys()
    keys = _migrate_legacy_keys(keys)
    raw_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    if raw_hash not in keys:
        return
    keys[raw_hash]["last_used"] = datetime.now(timezone.utc).isoformat()
    keys[raw_hash]["request_count"] = keys[raw_hash].get("request_count", 0) + 1
    _save_keys(keys)


def list_keys() -> list[dict]:
    keys = _load_keys()
    keys = _migrate_legacy_keys(keys)
    result = []
    for k, v in keys.items():
        result.append({
            "key_prefix": k[:14] + "***",
            "key_hash": v.get("key_hash", ""),
            "alias": v.get("alias", ""),
            "client_id": v.get("client_id", ""),
            "created_at": v.get("created_at", ""),
            "last_used": v.get("last_used"),
            "request_count": v.get("request_count", 0),
            "enabled": v.get("enabled", True),
        })
    return sorted(result, key=lambda x: x["created_at"], reverse=True)


def delete_key(key_prefix: str, key_hash: str) -> bool:
    keys = _load_keys()
    keys = _migrate_legacy_keys(keys)
    for k in list(keys.keys()):
        entry = keys[k]
        if k.startswith(key_prefix.replace("***", "")) and entry.get("key_hash", "") == key_hash:
            del keys[k]
            _save_keys(keys)
            logger.info("api key deleted", extra={"alias": entry.get("alias", "")})
            return True
    return False


def toggle_key(key_prefix: str, key_hash: str, enabled: bool) -> bool:
    keys = _load_keys()
    keys = _migrate_legacy_keys(keys)
    for k in list(keys.keys()):
        entry = keys[k]
        if k.startswith(key_prefix.replace("***", "")) and entry.get("key_hash", "") == key_hash:
            keys[k]["enabled"] = enabled
            _save_keys(keys)
            logger.info("api key toggled", extra={"alias": entry.get("alias", ""), "enabled": enabled})
            return True
    return False
