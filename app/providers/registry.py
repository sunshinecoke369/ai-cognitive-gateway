from app.providers.base import BaseProvider
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider, list_ollama_models
from app.providers.openai_compatible import OpenAICompatibleProvider, list_openai_compat_models
from app.admin.config_manager import resolve_runtime_local_config, resolve_runtime_cloud_config
from app.core.logging import logger

# ── Provider 注册表 ──

_providers: dict[str, BaseProvider] = {}

# ── Engine 模型发现注册表 ──

ENGINE_REGISTRY = {
    "ollama": list_ollama_models,
    "vllm": list_openai_compat_models,
    "sglang": list_openai_compat_models,
    "openai-compatible": list_openai_compat_models,
    "localai": list_openai_compat_models,
    "mock": lambda url, timeout: [],
}

SUPPORTED_ENGINES = [
    {"id": "ollama", "name": "Ollama"},
    {"id": "vllm", "name": "vLLM"},
    {"id": "sglang", "name": "SGLang"},
    {"id": "openai-compatible", "name": "OpenAI Compatible"},
    {"id": "localai", "name": "LocalAI"},
]


async def list_engine_models(provider: str, api_url: str, timeout: int = 10) -> list[dict]:
    """查询指定 Provider 的可用模型列表。"""
    handler = ENGINE_REGISTRY.get(provider, lambda url, t: [])
    return await handler(api_url, timeout)


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
