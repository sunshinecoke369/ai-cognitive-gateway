import json
import time
import asyncio
import re

import httpx

from app.providers.base import BaseProvider, LocalModelOutput, CloudModelResponse
from app.providers.client import get_http_client
from app.admin.config_manager import resolve_runtime_local_config
from app.tokenflow.counter import count_tokens
from app.core.logging import logger


class OllamaProvider(BaseProvider):
    provider_name = "ollama"

    async def _call_ollama_chat(self, messages: list[dict], model_name: str, api_url: str, timeout: int, keep_alive: int = -1) -> str | None:
        url = api_url.rstrip("/") + "/api/chat"
        payload = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
        }
        try:
            client = get_http_client()
            resp = await client.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")
        except httpx.TimeoutException:
            logger.warning("ollama chat timed out", extra={"model": model_name, "timeout": timeout})
            return "[TIMEOUT]"
        except httpx.ConnectError as e:
            logger.error("ollama chat connect failed — check Ollama is running", extra={"url": url, "error": str(e)})
            return "[CONNECTION_FAILED]"
        except httpx.HTTPStatusError as e:
            logger.error("ollama chat returned error status", extra={"status": e.response.status_code, "body": e.response.text[:200]})
            return "[HTTP_ERROR]"
        except json.JSONDecodeError as e:
            logger.error("ollama chat returned non-JSON response", extra={"error": str(e)})
            return "[PARSE_ERROR]"
        except Exception as e:
            logger.error("ollama chat request failed", extra={"model": model_name, "error_type": type(e).__name__, "error": str(e)})
            return None

    async def _call_ollama_generate(self, prompt: str, model_name: str, api_url: str, timeout: int, keep_alive: int = -1) -> str | None:
        url = api_url.rstrip("/") + "/api/generate"
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive,
        }
        try:
            client = get_http_client()
            resp = await client.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
        except httpx.TimeoutException:
            logger.warning("ollama generate timed out", extra={"model": model_name, "timeout": timeout})
            return "[TIMEOUT]"
        except httpx.ConnectError as e:
            logger.error("ollama generate connect failed — check Ollama is running", extra={"url": url, "error": str(e)})
            return "[CONNECTION_FAILED]"
        except httpx.HTTPStatusError as e:
            logger.error("ollama generate returned error status", extra={"status": e.response.status_code, "body": e.response.text[:200]})
            return "[HTTP_ERROR]"
        except json.JSONDecodeError as e:
            logger.error("ollama generate returned non-JSON response", extra={"error": str(e)})
            return "[PARSE_ERROR]"
        except Exception as e:
            logger.error("ollama generate request failed", extra={"model": model_name, "error_type": type(e).__name__, "error": str(e)})
            return None

    async def preprocess(self, user_input: str, model_name: str | None = None, messages: list[dict] | None = None) -> LocalModelOutput:
        t0 = time.perf_counter()
        cfg = resolve_runtime_local_config()
        used_model = model_name or cfg["default_model"]
        timeout = cfg["timeout_seconds"]
        api_url = cfg["api_url"]
        keep_alive = cfg.get("keep_alive", -1)

        input_text = user_input
        if messages and not input_text:
            from app.providers.base import extract_text_from_messages
            input_text = extract_text_from_messages(messages)

        logger.info("ollama preprocessing started", extra={"input_length": len(input_text), "model": used_model})

        system = (
            "You are a text analyzer. Analyze the user input and respond ONLY with valid JSON. "
            "No markdown, no explanation. The JSON must have these fields:\n"
            '{\n'
            '  "intent": {"primary": "question|code|command|chat|general", "confidence": 0.0-1.0},\n'
            '  "summary": {"short": "one sentence summary"},\n'
            '  "risk": {"level": "low|medium|high", "flags": []}\n'
            '}'
        )
        prompt = f"{system}\n\nUser input: {input_text}\n\nJSON:"

        try:
            raw = await self._call_ollama_generate(prompt, model_name=used_model, api_url=api_url, timeout=timeout, keep_alive=keep_alive)
        except Exception:
            raw = None

        latency = (time.perf_counter() - t0) * 1000
        degraded = False

        parsed = None
        if raw:
            parsed = self._extract_json(raw)

        if parsed is None:
            degraded = True
            logger.info("ollama preprocessing degraded: fallback to raw input", extra={"latency_ms": latency})
            return LocalModelOutput(
                summary_short=input_text[:100],
                summary_detailed=input_text[:200],
                intent_primary="general",
                intent_confidence=0.0,
                filtered_text=input_text,
                risk_level="low",
                language="en",
                latency_ms=round(latency, 2),
                degraded=True,
            )

        intent_cfg = parsed.get("intent", {})
        summary_cfg = parsed.get("summary", {})
        risk_cfg = parsed.get("risk", {})
        if not isinstance(intent_cfg, dict):
            intent_cfg = {}
        if not isinstance(summary_cfg, dict):
            summary_cfg = {}
        if not isinstance(risk_cfg, dict):
            risk_cfg = {}

        confidence = float(intent_cfg.get("confidence", 0.0))
        if confidence < 0.6:
            degraded = True

        intent_primary = str(intent_cfg.get("primary", "general"))
        summary_short = str(summary_cfg.get("short", input_text[:100]))
        risk_level = str(risk_cfg.get("level", "low"))
        risk_flags = risk_cfg.get("flags", [])
        if isinstance(risk_flags, str):
            risk_flags = [risk_flags]

        logger.info("ollama preprocessing completed", extra={"latency_ms": latency, "degraded": degraded, "confidence": confidence})

        return LocalModelOutput(
            summary_short=summary_short,
            summary_detailed=summary_short,
            intent_primary=intent_primary,
            intent_confidence=confidence,
            filtered_text=input_text if degraded else summary_short,
            risk_level=risk_level,
            risk_flags=risk_flags,
            language=self._detect_language(input_text),
            latency_ms=round(latency, 2),
            degraded=degraded,
            should_store=not degraded,
            memory_importance=confidence,
            memory_tags=[intent_primary],
        )

    async def generate(
        self,
        enriched_prompt: str,
        model_name: str | None = None,
        context: dict | None = None,
        messages: list[dict] | None = None,
    ) -> CloudModelResponse:
        t0 = time.perf_counter()
        cfg = resolve_runtime_local_config()
        used_model = model_name or cfg["default_model"]
        timeout = cfg["timeout_seconds"]
        api_url = cfg["api_url"]
        keep_alive = cfg.get("keep_alive", -1)

        logger.info("ollama cloud generation started", extra={"model": used_model, "has_messages": messages is not None})

        if messages:
            text = await self._call_ollama_chat(messages, model_name=used_model, api_url=api_url, timeout=timeout, keep_alive=keep_alive)
        else:
            text = await self._call_ollama_generate(enriched_prompt, model_name=used_model, api_url=api_url, timeout=timeout, keep_alive=keep_alive)

        latency = (time.perf_counter() - t0) * 1000

        if text is None:
            text = f"[OLLAMA ERROR] Failed to get response from {used_model}"

        tokens_in = count_tokens(enriched_prompt)
        tokens_out = count_tokens(text) if text else 0

        return CloudModelResponse(
            text=text,
            model_used=f"ollama:{used_model}",
            latency_ms=round(latency, 2),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    def _extract_json(self, text: str) -> dict | None:
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None

    def _detect_language(self, text: str) -> str:
        if re.search(r"[\u4e00-\u9fff]", text):
            return "zh"
        return "en"
