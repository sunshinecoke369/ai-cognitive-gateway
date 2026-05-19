import time
import uuid
import asyncio
import re

from app.providers.base import BaseProvider, LocalModelOutput, CloudModelResponse
from app.core.config import settings
from app.core.logging import logger
from app.tokenflow.counter import count_tokens


class MockProvider(BaseProvider):
    provider_name = "mock"

    async def preprocess(self, user_input: str, model_name: str | None = None, messages: list[dict] | None = None) -> LocalModelOutput:
        t0 = time.perf_counter()
        used_model = model_name or settings.default_local_model
        logger.info("mock preprocessing started", extra={"input_length": len(user_input), "model": used_model})

        try:
            language = self._detect_language(user_input)
            intent = self._infer_intent(user_input)
            filtered = self._filter_noise(user_input)
            risk = self._assess_risk(user_input)
            routing = self._suggest_routing(user_input, risk["level"])
            memory = self._memory_hint(user_input, intent)

            latency = (time.perf_counter() - t0) * 1000
            degraded = False

            if intent["confidence"] < settings.local_model_confidence_threshold:
                degraded = True
                logger.info("mock preprocessing degraded due to low confidence", extra={"confidence": intent["confidence"]})

            logger.info("mock preprocessing completed", extra={"latency_ms": latency, "degraded": degraded})

            return LocalModelOutput(
                summary_short=self._summarize_short(user_input),
                summary_detailed=self._summarize_detailed(user_input),
                intent_primary=intent["primary"],
                intent_secondary=intent.get("secondary", []),
                intent_confidence=intent["confidence"],
                filtered_text=filtered["clean"],
                removed_parts=filtered.get("removed", []),
                risk_level=risk["level"],
                risk_flags=risk["flags"],
                model_suggestion=routing["suggestion"],
                routing_reason=routing["reason"],
                should_store=memory["should_store"],
                memory_importance=memory["importance"],
                memory_tags=memory["tags"],
                language=language,
                latency_ms=round(latency, 2),
                degraded=degraded,
            )
        except asyncio.TimeoutError:
            latency = (time.perf_counter() - t0) * 1000
            logger.warning("mock preprocessing timed out", extra={"latency_ms": latency})
            return LocalModelOutput(
                summary_short=user_input[:100],
                summary_detailed=user_input[:200],
                intent_primary="general",
                intent_confidence=0.0,
                filtered_text=user_input,
                risk_level="low",
                language="en",
                latency_ms=round(latency, 2),
                degraded=True,
            )

    async def generate(
        self,
        enriched_prompt: str,
        model_name: str | None = None,
        context: dict | None = None,
        messages: list[dict] | None = None,
    ) -> CloudModelResponse:
        t0 = time.perf_counter()
        used_model = model_name or "mock-cloud-model"
        logger.info("mock cloud generation started", extra={"model": used_model})

        try:
            await asyncio.sleep(0.01)
        except asyncio.TimeoutError:
            pass

        response_text = (
            f"[MOCK RESPONSE] Model: {used_model}. "
            f"Received prompt ({len(enriched_prompt)} chars). "
            f"This is a simulated cloud model response. "
            f"In production, this would call an actual LLM API."
        )
        if context and context.get("memory"):
            response_text += f" Context: {context['memory'][:100]}..."

        latency = (time.perf_counter() - t0) * 1000
        tokens_in = count_tokens(enriched_prompt)
        tokens_out = count_tokens(response_text)

        return CloudModelResponse(
            text=response_text,
            model_used=used_model,
            latency_ms=round(latency, 2),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    def _detect_language(self, text: str) -> str:
        if re.search(r"[\u4e00-\u9fff]", text):
            return "zh"
        return "en"

    def _summarize_short(self, text: str) -> str:
        if len(text) <= 60:
            return text
        return text[:57] + "..."

    def _summarize_detailed(self, text: str) -> str:
        lines = text.strip().split("\n")
        summary_lines = []
        for line in lines[:5]:
            if line.strip():
                summary_lines.append(line.strip()[:100])
        return " | ".join(summary_lines)

    def _infer_intent(self, text: str) -> dict:
        text_lower = text.lower()

        intent_map = {
            "code": ["code", "function", "debug", "error", "bug", "fix", "implement", "test"],
            "question": ["what", "how", "why", "explain", "?", "？"],
            "data": ["analyze", "extract", "summarize", "report", "convert"],
            "chat": ["hello", "hi", "thanks", "ok", "yes", "no"],
            "command": ["run", "start", "stop", "build", "deploy", "install"],
        }

        scores = {}
        for intent, keywords in intent_map.items():
            scores[intent] = sum(1 for kw in keywords if kw in text_lower)

        if not scores or max(scores.values()) == 0:
            return {"primary": "general", "secondary": [], "confidence": 0.3}

        primary = max(scores, key=scores.get)
        secondary = [k for k, v in scores.items() if v > 0 and k != primary]
        max_kw = len(intent_map[primary])
        confidence = min(scores[primary] / max(max_kw, 1), 1.0)

        return {"primary": primary, "secondary": secondary, "confidence": round(confidence, 2)}

    def _filter_noise(self, text: str) -> dict:
        noise_patterns = [
            r"um+[,\s]",
            r"uh+[,\s]",
            r"like,\s",
            r"you know[,\s]",
        ]
        clean = text
        removed = []
        for pat in noise_patterns:
            matches = re.findall(pat, clean, re.IGNORECASE)
            if matches:
                removed.extend(matches)
                clean = re.sub(pat, "", clean, flags=re.IGNORECASE)

        return {"clean": clean.strip(), "removed": removed}

    def _assess_risk(self, text: str) -> dict:
        text_lower = text.lower()
        flags = []

        high_risk = ["ignore all instructions", "system prompt", "pretend you are", "jailbreak"]
        medium_risk = ["password", "api_key", "secret", "token=", "admin override"]

        for kw in high_risk:
            if kw in text_lower:
                flags.append("prompt_injection")
                return {"level": "high", "flags": flags}

        for kw in medium_risk:
            if kw in text_lower:
                flags.append("sensitive_data")

        level = "medium" if flags else "low"
        return {"level": level, "flags": flags}

    def _suggest_routing(self, text: str, risk_level: str) -> dict:
        if risk_level == "high":
            return {"suggestion": "local", "reason": "高风险输入，拒绝转发云端"}

        text_len = len(text)
        if text_len < 50:
            return {"suggestion": "cloud", "reason": "简单输入，直接云端处理"}
        if text_len < 500:
            return {"suggestion": "cloud", "reason": "中等长度，云端处理"}
        return {"suggestion": "hybrid", "reason": "长输入，本地预处理后云端"}

    def _memory_hint(self, text: str, intent: dict) -> dict:
        importance = 0.0
        tags = []

        if intent["primary"] in ("code", "data"):
            importance = 0.7
            tags.append(intent["primary"])
        elif intent["primary"] == "question":
            importance = 0.3
        else:
            importance = 0.1

        text_lower = text.lower()
        topic_keywords = {
            "python": "python",
            "api": "api",
            "database": "db",
            "docker": "docker",
            "security": "security",
        }
        for kw, tag in topic_keywords.items():
            if kw in text_lower:
                tags.append(tag)

        should_store = importance >= 0.3 or len(tags) > 0
        return {"should_store": should_store, "importance": importance, "tags": tags[:5]}
