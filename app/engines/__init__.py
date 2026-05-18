from app.engines.ollama_engine import list_ollama_models
from app.engines.openai_compat_engine import list_openai_compat_models

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
    handler = ENGINE_REGISTRY.get(provider, lambda url, timeout: [])
    return await handler(api_url, timeout)
