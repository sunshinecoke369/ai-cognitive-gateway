import time
import asyncio
import re

import httpx

from app.providers.base import BaseProvider, LocalModelOutput, CloudModelResponse
from app.admin.config_manager import resolve_runtime_cloud_config, get_cloud_models
from app.core.logging import logger


class OpenAICompatibleProvider(BaseProvider):
    provider_name = "openai-compatible"

    async def _call_api(self, prompt: str, model_name: str, api_url: str, api_key: str, timeout: int, messages: list[dict] | None = None) -> str | None:
        url = api_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if messages:
            msgs = messages
        else:
            msgs = [
                {"role": "system", "content": "你是一个智能助手，请简洁专业地回答用户问题。"},
                {"role": "user", "content": prompt},
            ]

        payload = {
            "model": model_name,
            "messages": msgs,
            "temperature": 0.7,
            "max_tokens": 2048,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return None
        except httpx.TimeoutException:
            logger.warning("openai-compatible request timed out", extra={"model": model_name, "url": url, "timeout": timeout})
            return "[TIMEOUT]"
        except httpx.ConnectError as e:
            logger.error("openai-compatible connection failed", extra={"model": model_name, "url": url, "error": str(e)})
            return "[CONNECTION_FAILED]"
        except httpx.HTTPStatusError as e:
            logger.error("openai-compatible returned error status", extra={"model": model_name, "status": e.response.status_code, "body": e.response.text[:200]})
            return "[HTTP_ERROR]"
        except json.JSONDecodeError as e:
            logger.error("openai-compatible returned non-JSON response", extra={"model": model_name, "error": str(e)})
            return "[PARSE_ERROR]"
        except Exception as e:
            logger.error("openai-compatible request failed", extra={"model": model_name, "url": url, "error_type": type(e).__name__, "error": str(e)})
            return None

    async def preprocess(self, user_input: str, model_name: str | None = None) -> LocalModelOutput:
        t0 = time.perf_counter()
        cfg = resolve_runtime_cloud_config()
        used_model = model_name or cfg["default_model"]
        timeout = cfg["timeout_seconds"]
        api_url = cfg["api_url"]
        api_key = cfg.get("api_key", "")

        logger.info("openai-compatible preprocessing started", extra={"input_length": len(user_input), "model": used_model})

        system = (
            "Analyze the user input. Respond ONLY with valid JSON:\n"
            '{"intent":{"primary":"question|code|command|chat|general","confidence":0.5},"summary":{"short":"..."},"risk":{"level":"low|medium|high","flags":[]}}'
        )

        try:
            raw = await self._call_api(system + "\n\nUser: " + user_input, used_model, api_url, api_key, timeout)
        except Exception:
            raw = None

        latency = (time.perf_counter() - t0) * 1000
        degraded = False

        if raw is None:
            degraded = True
            logger.info("openai-compatible preprocessing degraded", extra={"latency_ms": latency})
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

        parsed = self._extract_json(raw)
        intent_cfg = parsed.get("intent", {}) if parsed else {}
        summary_cfg = parsed.get("summary", {}) if parsed else {}
        risk_cfg = parsed.get("risk", {}) if parsed else {}
        if not isinstance(intent_cfg, dict):
            intent_cfg = {}
        if not isinstance(summary_cfg, dict):
            summary_cfg = {}
        if not isinstance(risk_cfg, dict):
            risk_cfg = {}

        confidence = float(intent_cfg.get("confidence", 0.5))
        intent_primary = str(intent_cfg.get("primary", "general"))
        summary_short = str(summary_cfg.get("short", user_input[:100]))
        risk_level = str(risk_cfg.get("level", "low"))
        risk_flags = risk_cfg.get("flags", []) if isinstance(risk_cfg.get("flags"), list) else []

        logger.info("openai-compatible preprocessing completed", extra={"latency_ms": latency, "confidence": confidence})

        return LocalModelOutput(
            summary_short=summary_short,
            summary_detailed=summary_short,
            intent_primary=intent_primary,
            intent_confidence=confidence,
            filtered_text=user_input if confidence < 0.6 else summary_short,
            risk_level=risk_level,
            risk_flags=risk_flags,
            language=self._detect_language(user_input),
            latency_ms=round(latency, 2),
            degraded=confidence < 0.6,
            should_store=True,
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
        cfg = resolve_runtime_cloud_config()
        used_model = model_name or cfg["default_model"]
        models = get_cloud_models()
        model_cfg = models.get(used_model, {})
        timeout = model_cfg.get("timeout_seconds", cfg.get("timeout_seconds", 60))
        api_url = model_cfg.get("api_url", cfg.get("api_url", ""))
        api_key = model_cfg.get("api_key", cfg.get("api_key", ""))

        logger.info("openai-compatible generation started", extra={"model": used_model, "has_messages": messages is not None})

        text = await self._call_api(enriched_prompt, used_model, api_url, api_key, timeout, messages=messages)

        latency = (time.perf_counter() - t0) * 1000

        if text is None:
            text = f"[{used_model}] Request failed or timed out"

        tokens_in = len(enriched_prompt.split())
        tokens_out = len(text.split())

        return CloudModelResponse(
            text=text,
            model_used=used_model,
            latency_ms=round(latency, 2),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    async def generate_stream(
        self,
        enriched_prompt: str,
        model_name: str | None = None,
        messages: list[dict] | None = None,
    ):
        cfg = resolve_runtime_cloud_config()
        used_model = model_name or cfg["default_model"]
        models = get_cloud_models()
        model_cfg = models.get(used_model, {})

        api_url = model_cfg.get("api_url", cfg.get("api_url", ""))
        api_key = model_cfg.get("api_key", cfg.get("api_key", ""))
        timeout = model_cfg.get("timeout_seconds", cfg.get("timeout_seconds", 60))

        url = api_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if messages:
            msgs = messages
        else:
            msgs = [
                {"role": "system", "content": "你是一个智能助手，请简洁专业地回答用户问题。"},
                {"role": "user", "content": enriched_prompt},
            ]

        payload = {
            "model": used_model,
            "messages": msgs,
            "temperature": 0.7,
            "max_tokens": 2048,
            "stream": True,
        }

        logger.info("openai-compatible streaming started", extra={"model": used_model, "has_messages": messages is not None})

        tokens_in = len(enriched_prompt.split())
        tokens_out = 0

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=15.0)) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        raw = line.removeprefix("data:").strip()
                        if raw == "[DONE]":
                            break
                        try:
                            chunk = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "") or ""
                            if content:
                                tokens_out += 1
                                yield content
                        usage = chunk.get("usage", {})
                        if usage:
                            tokens_in = usage.get("prompt_tokens", tokens_in)
                            tokens_out = usage.get("completion_tokens", tokens_out)
        except httpx.TimeoutException:
            logger.warning("openai-compatible stream timed out", extra={"model": used_model, "url": url})
            yield f"[{used_model}] Request timed out"
        except httpx.ConnectError as e:
            logger.error("openai-compatible stream connect failed", extra={"model": used_model, "url": url, "error": str(e)})
            yield f"[{used_model}] Connection failed"
        except httpx.HTTPStatusError as e:
            logger.error("openai-compatible stream returned error status", extra={"model": used_model, "status": e.response.status_code})
            yield f"[{used_model}] HTTP {e.response.status_code}"
        except Exception as e:
            logger.error("openai-compatible stream failed", extra={"model": used_model, "url": url, "error_type": type(e).__name__, "error": str(e)})
            yield f"[{used_model}] Request failed or timed out"

    def _extract_json(self, text: str) -> dict | None:
        import json as _json
        try:
            return _json.loads(text.strip())
        except _json.JSONDecodeError:
            pass
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return _json.loads(match.group(0))
            except _json.JSONDecodeError:
                pass
        return None

    def _detect_language(self, text: str) -> str:
        if re.search(r"[\u4e00-\u9fff]", text):
            return "zh"
        return "en"
