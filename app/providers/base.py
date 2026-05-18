from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import asyncio


@dataclass
class LocalModelOutput:
    summary_short: str
    summary_detailed: str
    intent_primary: str
    intent_secondary: list[str] = field(default_factory=list)
    intent_confidence: float = 0.0
    filtered_text: str = ""
    removed_parts: list[str] = field(default_factory=list)
    risk_level: str = "low"
    risk_flags: list[str] = field(default_factory=list)
    model_suggestion: str = "cloud"
    routing_reason: str = ""
    should_store: bool = False
    memory_importance: float = 0.0
    memory_tags: list[str] = field(default_factory=list)
    language: str = "en"
    latency_ms: float = 0.0
    degraded: bool = False


@dataclass
class CloudModelResponse:
    text: str
    model_used: str
    latency_ms: float
    tokens_in: int = 0
    tokens_out: int = 0


class BaseProvider(ABC):

    @abstractmethod
    async def preprocess(self, user_input: str, model_name: str | None = None, messages: list[dict] | None = None) -> LocalModelOutput:
        pass

    @abstractmethod
    async def generate(
        self,
        enriched_prompt: str,
        model_name: str | None = None,
        context: Optional[dict] = None,
        messages: list[dict] | None = None,
    ) -> CloudModelResponse:
        pass

    async def generate_stream(
        self,
        enriched_prompt: str,
        model_name: str | None = None,
        messages: list[dict] | None = None,
    ):
        result = await self.generate(enriched_prompt, model_name=model_name, messages=messages)
        if result.text:
            for char in result.text:
                yield char
            await asyncio.sleep(0)

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass


def extract_text_from_messages(messages: list[dict] | None) -> str:
    if not messages:
        return ""
    texts = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            role = msg.get("role", "user")
            texts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text" and isinstance(block.get("text"), str):
                        texts.append(block["text"])
                    elif block.get("type") == "image_url":
                        url = ""
                        if isinstance(block.get("image_url"), dict):
                            url = block["image_url"].get("url", "")[:60]
                        texts.append(f"[IMAGE: {url}]")
    return " ".join(texts)


def has_images_in_messages(messages: list[dict] | None) -> bool:
    if not messages:
        return False
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "image_url":
                    return True
    return False
