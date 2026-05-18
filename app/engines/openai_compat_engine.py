import httpx
from app.core.logging import logger


async def list_openai_compat_models(api_url: str, timeout: int = 10) -> list[dict]:
    url = api_url.rstrip("/") + "/v1/models"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data", [])
            return [{"id": m.get("id", "")} for m in items]
    except Exception as e:
        logger.warning("failed to list vllm/openai-compat models", extra={"url": url, "error": str(e)})
        return []
