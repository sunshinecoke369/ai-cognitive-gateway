import httpx
from app.core.logging import logger


async def list_ollama_models(api_url: str, timeout: int = 10) -> list[dict]:
    url = api_url.rstrip("/") + "/api/tags"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            return [{"id": m.get("name", ""), "size": m.get("size", 0)} for m in models]
    except Exception as e:
        logger.warning("failed to list ollama models", extra={"url": url, "error": str(e)})
        return []
