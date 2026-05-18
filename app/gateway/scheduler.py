from app.admin.config_manager import resolve_runtime_cloud_models, get_cloud_default_model
from app.providers.base import LocalModelOutput, has_images_in_messages
from app.core.logging import logger


def rank_cloud_models(local_output: LocalModelOutput | None = None, messages: list[dict] | None = None) -> list[dict]:
    models = resolve_runtime_cloud_models()
    if not models:
        return []

    if local_output is None:
        models.sort(key=lambda m: m.get("weight", 1), reverse=True)
        return models

    intent = (local_output.intent_primary or "").lower()
    language = (local_output.language or "").lower()
    risk = (local_output.risk_level or "").lower()
    degraded = local_output.degraded
    has_images = has_images_in_messages(messages)

    scored = []
    for m in models:
        tags = [t.lower() for t in m.get("tags", [])]
        score = m.get("weight", 1)

        if has_images and "vision" in tags:
            score += 10
        if has_images and "vision" not in tags:
            score -= 5
        if intent and intent in tags:
            score += 3
        if intent == "code" and "coding" in tags:
            score += 5
        if intent == "command" and "fast" in tags:
            score += 3
        if language == "zh" and "chinese" in tags:
            score += 4
        if risk == "high" and "safe" in tags:
            score += 2
        if degraded and "fast" in tags:
            score += 2

        scored.append((m, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    logger.info(
        "cloud model scored",
        extra={
            "intent": intent,
            "language": language,
            "has_images": has_images,
            "scores": [(s[0]["name"], s[1]) for s in scored],
        },
    )

    return [s[0] for s in scored]


def pick_cloud_model(local_output: LocalModelOutput | None = None, messages: list[dict] | None = None) -> dict:
    ranked = rank_cloud_models(local_output, messages=messages)
    return ranked[0] if ranked else {}


def get_fallback_chain(local_output: LocalModelOutput | None = None, messages: list[dict] | None = None) -> list[dict]:
    return rank_cloud_models(local_output, messages=messages)
