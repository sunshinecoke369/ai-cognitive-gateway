from app.providers.base import BaseProvider
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.admin.config_manager import resolve_runtime_local_config, resolve_runtime_cloud_config
from app.core.logging import logger


_providers: dict[str, BaseProvider] = {}


def _init_providers():
    global _providers
    if _providers:
        return

    _providers["mock"] = MockProvider()
    _providers["ollama"] = OllamaProvider()
    _providers["openai-compatible"] = OpenAICompatibleProvider()
    logger.info("provider registry initialized", extra={"providers": list(_providers.keys())})


def get_local_provider() -> BaseProvider:
    _init_providers()
    cfg = resolve_runtime_local_config()
    mode = cfg.get("provider", "mock")
    if mode not in _providers:
        logger.warning("unknown local provider, falling back to mock", extra={"provider": mode})
        return _providers["mock"]
    return _providers[mode]


def get_cloud_provider() -> BaseProvider:
    _init_providers()
    cfg = resolve_runtime_cloud_config()
    mode = cfg.get("provider", "openai-compatible")
    if mode in _providers:
        return _providers[mode]
    if mode == "ollama" and "ollama" in _providers:
        return _providers["ollama"]
    logger.warning("unknown cloud provider, falling back to ollama", extra={"provider": mode})
    return _providers["ollama"]
