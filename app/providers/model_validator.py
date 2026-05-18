import json
import os

from app.core.config import settings
from app.core.logging import logger
from app.admin.config_manager import get_local_config, get_cloud_default_model, get_cloud_models


def _load_allowed_models() -> dict:
    path = settings.allowed_models_path
    if not os.path.exists(path):
        logger.warning("allowed_models.json not found, using empty list", extra={"path": path})
        return {"local": [], "cloud": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_local_model(model_name: str) -> bool:
    allowed = _load_allowed_models()
    return model_name in allowed.get("local", [])


def validate_cloud_model(model_name: str) -> bool:
    allowed = _load_allowed_models()
    return model_name in allowed.get("cloud", [])


def get_allowed_local_models() -> list[str]:
    return _load_allowed_models().get("local", [])


def get_allowed_cloud_models() -> list[str]:
    models = get_cloud_models()
    return list(models.keys())


def resolve_local_model(request_model: str | None = None) -> str:
    model_name = request_model or get_local_config().get("default_model", settings.default_local_model)
    if not validate_local_model(model_name):
        raise ValueError(f"local model not allowed: {model_name}")
    return model_name


def resolve_cloud_model(request_model: str | None = None) -> str:
    model_name = request_model or get_cloud_default_model()
    if not model_name:
        raise ValueError("no cloud model configured")
    if not validate_cloud_model(model_name):
        raise ValueError(f"cloud model not allowed: {model_name}")
    return model_name
