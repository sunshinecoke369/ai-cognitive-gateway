import json
import os
import threading

import yaml

from app.core.config import settings
from app.core.logging import logger

_config_cache: dict | None = None
_config_mtime: float = 0

# 文件级写锁，防止并发写 YAML 损坏
_config_write_lock = threading.Lock()

try:
    import fcntl

    def _lock_file(fd):
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock_file(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)

    _HAS_FCNTL = True
except ImportError:
    # Windows 或其他不支持 fcntl 的平台，退化到 threading lock
    def _lock_file(fd):
        pass

    def _unlock_file(fd):
        pass

    _HAS_FCNTL = False


def _config_path() -> str:
    return settings.config_file_path


def _ensure_file():
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        _write_default_config(path)


def _write_default_config(path: str):
    default = {
        "local": {
            "provider": settings.local_model_mode,
            "api_url": settings.ollama_url,
            "default_model": settings.default_local_model,
            "timeout_seconds": settings.request_timeout_sec,
            "max_tokens": 2048,
            "api_key": "",
            "keep_alive": -1,
        },
        "cloud": {
            "default": settings.default_cloud_model,
            "models": {
                settings.default_cloud_model: {
                    "provider": "openai-compatible",
                    "api_url": settings.openai_base_url,
                    "api_key": settings.openai_api_key,
                    "timeout_seconds": 30,
                    "weight": 5,
                    "tags": ["general"],
                    "enabled": True,
                }
            }
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(default, f, default_flow_style=False, allow_unicode=True)
    logger.info("created default gateway config", extra={"path": path})


def _migrate_cloud_config(cfg: dict) -> dict:
    cloud = cfg.get("cloud", {})
    if "models" in cloud:
        return cfg
    default_model = cloud.get("default_model", settings.default_cloud_model)
    cfg["cloud"] = {
        "default": default_model,
        "models": {
            default_model: {
                "provider": cloud.get("provider", "openai-compatible"),
                "api_url": cloud.get("api_url", settings.openai_base_url),
                "api_key": cloud.get("api_key", settings.openai_api_key),
                "timeout_seconds": cloud.get("timeout_seconds", 30),
                "weight": 5,
                "tags": ["general"],
                "enabled": True,
            }
        }
    }
    _save_config(cfg)
    logger.info("cloud config migrated to multi-model format", extra={"model": default_model})
    return cfg


def _load_config() -> dict:
    global _config_cache, _config_mtime
    path = _config_path()
    _ensure_file()
    mtime = os.path.getmtime(path)
    if _config_cache is not None and mtime == _config_mtime:
        return _config_cache
    with open(path, "r", encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f) or {}
    _config_mtime = mtime
    _config_cache = _migrate_cloud_config(_config_cache)
    _apply_to_settings(_config_cache)
    return _config_cache


def get_config(mask_secrets: bool = True) -> dict:
    cfg = _load_config()
    if not mask_secrets:
        return cfg
    masked = {}
    local = cfg.get("local", {})
    masked_local = dict(local)
    key = str(masked_local.get("api_key", ""))
    if key and len(key) > 8:
        masked_local["api_key"] = key[:4] + "*" * (len(key) - 8) + key[-4:]
    elif key and len(key) > 2:
        masked_local["api_key"] = key[:2] + "***"
    masked["local"] = masked_local

    cloud = cfg.get("cloud", {})
    masked_models = {}
    for name, model in cloud.get("models", {}).items():
        m = dict(model)
        k = str(m.get("api_key", ""))
        if k and len(k) > 8:
            m["api_key"] = k[:4] + "*" * (len(k) - 8) + k[-4:]
        elif k and len(k) > 2:
            m["api_key"] = k[:2] + "***"
        masked_models[name] = m
    masked["cloud"] = {"default": cloud.get("default", ""), "models": masked_models}
    return masked


def get_local_config() -> dict:
    return _load_config().get("local", {})


def get_cloud_config() -> dict:
    cloud = _load_config().get("cloud", {})
    return cloud


def get_cloud_models() -> dict:
    cloud = get_cloud_config()
    return cloud.get("models", {})


def get_cloud_default_model() -> str:
    cloud = get_cloud_config()
    return cloud.get("default") or list(get_cloud_models().keys())[0] if get_cloud_models() else settings.default_cloud_model


def update_local_config(data: dict):
    cfg = _load_config()
    local = cfg.get("local", {})
    for key in ("provider", "api_url", "default_model", "timeout_seconds", "max_tokens", "api_key"):
        if key in data:
            local[key] = data[key]
    cfg["local"] = local
    _save_config(cfg)
    _apply_to_settings(cfg)
    _sync_local_allowed_models(cfg)


def _sync_local_allowed_models(cfg: dict):
    model_name = cfg.get("local", {}).get("default_model", "")
    if not model_name:
        return
    path = settings.allowed_models_path
    try:
        with open(path, "r", encoding="utf-8") as f:
            allowed = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        allowed = {"local": [], "cloud": []}
    local_list = allowed.get("local", [])
    if model_name not in local_list:
        local_list.append(model_name)
        allowed["local"] = local_list
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(allowed, f, ensure_ascii=False, indent=2)
        logger.info("auto-synced local model to allowed list", extra={"model": model_name})


def update_cloud_config(data: dict):
    cfg = _load_config()
    cloud = cfg.get("cloud", {})
    if "default" in data:
        cloud["default"] = data["default"]
    cfg["cloud"] = cloud
    _save_config(cfg)
    _apply_to_settings(cfg)


def add_cloud_model(name: str, config: dict):
    cfg = _load_config()
    if "cloud" not in cfg:
        cfg["cloud"] = {"default": name, "models": {}}
    cfg["cloud"]["default"] = cfg["cloud"].get("default") or name
    cfg["cloud"]["models"][name] = {
        "provider": config.get("provider", "openai-compatible"),
        "api_url": config.get("api_url", ""),
        "api_key": config.get("api_key", ""),
        "timeout_seconds": config.get("timeout_seconds", 60),
        "weight": config.get("weight", 1),
        "tags": config.get("tags", ["general"]),
        "enabled": config.get("enabled", True),
    }
    _save_config(cfg)
    _apply_to_settings(cfg)
    _sync_allowed_models(cfg)


def _sync_allowed_models(cfg: dict):
    path = settings.allowed_models_path
    try:
        with open(path, "r", encoding="utf-8") as f:
            allowed = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        allowed = {"local": [], "cloud": []}
    cloud_models = list(cfg.get("cloud", {}).get("models", {}).keys())
    existing = set(allowed.get("cloud", []))
    changed = False
    for name in cloud_models:
        if name not in existing:
            allowed.setdefault("cloud", []).append(name)
            changed = True
    if changed:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(allowed, f, ensure_ascii=False, indent=2)


def update_cloud_model(name: str, data: dict):
    cfg = _load_config()
    models = cfg.setdefault("cloud", {}).setdefault("models", {})
    if name not in models:
        raise KeyError(f"model {name} not found")
    for key in ("provider", "api_url", "api_key", "timeout_seconds", "weight", "tags", "enabled"):
        if key in data:
            models[name][key] = data[key]
    cfg["cloud"]["models"] = models
    _save_config(cfg)
    _apply_to_settings(cfg)


def delete_cloud_model(name: str):
    cfg = _load_config()
    models = cfg.get("cloud", {}).get("models", {})
    if name not in models:
        raise KeyError(f"model {name} not found")
    del models[name]
    if cfg["cloud"].get("default") == name:
        cfg["cloud"]["default"] = list(models.keys())[0] if models else ""
    cfg["cloud"]["models"] = models
    _save_config(cfg)
    _apply_to_settings(cfg)


def _validate_cloud_models(cfg: dict):
    cloud = cfg.get("cloud", {})
    if "models" in cloud:
        models = cloud["models"]
        if not isinstance(models, dict):
            raise ValueError("cloud.models must be a dict, got " + type(models).__name__)
        for name, model in models.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("cloud model name must be a non-empty string")
            if not isinstance(model, dict):
                raise ValueError(f"cloud model '{name}' value must be a dict")
            if "provider" not in model:
                raise ValueError(f"cloud model '{name}' missing 'provider'")
            if "api_url" not in model or not model["api_url"]:
                raise ValueError(f"cloud model '{name}' missing 'api_url'")
            if model.get("weight") is not None:
                w = model["weight"]
                if not isinstance(w, (int, float)) or w < 1:
                    raise ValueError(f"cloud model '{name}' weight must be >= 1")
            tags = model.get("tags")
            if tags is not None and not isinstance(tags, list):
                raise ValueError(f"cloud model '{name}' tags must be a list")


def _save_config(cfg: dict):
    global _config_cache, _config_mtime
    _validate_cloud_models(cfg)
    path = _config_path()
    with _config_write_lock:
        # 文件级锁（fcntl）防止多进程并发写
        with open(path, "w", encoding="utf-8") as f:
            if _HAS_FCNTL:
                _lock_file(f)
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
            if _HAS_FCNTL:
                _unlock_file(f)
        _config_cache = cfg
        _config_mtime = os.path.getmtime(path)
    logger.info("gateway config saved", extra={"path": path})


def reload_config():
    global _config_cache, _config_mtime
    _config_cache = None
    _config_mtime = 0
    cfg = _load_config()
    _apply_to_settings(cfg)
    logger.info("gateway config reloaded")
    return cfg


def _apply_to_settings(cfg: dict):
    local = cfg.get("local", {})
    if local.get("api_url"):
        settings.ollama_url = local["api_url"]
    if local.get("default_model"):
        settings.default_local_model = local["default_model"]
    if local.get("timeout_seconds") is not None:
        settings.request_timeout_sec = local["timeout_seconds"]

    cloud = cfg.get("cloud", {})
    models = cloud.get("models", {})
    default_name = cloud.get("default", "")
    default_model = models.get(default_name, {})
    if default_model:
        if default_model.get("api_url"):
            settings.openai_base_url = default_model["api_url"]
        if default_model.get("api_key"):
            settings.openai_api_key = default_model["api_key"]
        settings.default_cloud_model = default_name
    elif models:
        first = list(models.values())[0]
        if first.get("api_url"):
            settings.openai_base_url = first["api_url"]
        if first.get("api_key"):
            settings.openai_api_key = first["api_key"]


def resolve_runtime_local_config() -> dict:
    cfg = _load_config()
    local = cfg.get("local", {})
    return {
        "provider": local.get("provider", settings.local_model_mode),
        "api_url": local.get("api_url", settings.ollama_url),
        "default_model": local.get("default_model", settings.default_local_model),
        "timeout_seconds": local.get("timeout_seconds", settings.request_timeout_sec),
        "keep_alive": local.get("keep_alive", -1),
    }


def resolve_runtime_cloud_config() -> dict:
    cfg = _load_config()
    cloud = cfg.get("cloud", {})
    models = cloud.get("models", {})
    default_name = cloud.get("default", "")
    model = models.get(default_name, list(models.values())[0] if models else {})
    return {
        "provider": model.get("provider", "openai-compatible"),
        "api_url": model.get("api_url", settings.openai_base_url),
        "api_key": model.get("api_key", settings.openai_api_key),
        "default_model": default_name or settings.default_cloud_model,
        "timeout_seconds": model.get("timeout_seconds", 30),
    }


def resolve_runtime_cloud_models() -> list[dict]:
    cloud = _load_config().get("cloud", {})
    models = cloud.get("models", {})
    result = []
    for name, model in models.items():
        if model.get("enabled", True):
            result.append({
                "name": name,
                "provider": model.get("provider", "openai-compatible"),
                "api_url": model.get("api_url", ""),
                "api_key": model.get("api_key", ""),
                "timeout_seconds": model.get("timeout_seconds", 60),
                "weight": model.get("weight", 1),
                "tags": model.get("tags", ["general"]),
            })
    return result
