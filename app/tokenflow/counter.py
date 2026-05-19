"""
Token 计数工具

使用 tiktoken 精确计数（如果已安装），否则回退到 len(text.split())。

精确计数对中英文混写场景尤其重要——len(text.split()) 会将中文每个字算作一个 token，
实际中文约 1.5-2 字/token，误差可达 2-3 倍。
"""

import logging

logger = logging.getLogger("ai_cognitive_gateway")

try:
    import tiktoken

    _ENCODING_CACHE: dict[str, "tiktoken.Encoding"] = {}

    def _get_encoding(model_name: str = "gpt-4") -> "tiktoken.Encoding":
        if model_name not in _ENCODING_CACHE:
            try:
                _ENCODING_CACHE[model_name] = tiktoken.encoding_for_model(model_name)
            except KeyError:
                _ENCODING_CACHE[model_name] = tiktoken.get_encoding("cl100k_base")
        return _ENCODING_CACHE[model_name]

    def count_tokens(text: str, model_name: str = "gpt-4") -> int:
        """精确 token 计数（tiktoken）。"""
        if not text:
            return 0
        encoding = _get_encoding(model_name)
        return len(encoding.encode(text))

    HAS_TIKTOKEN = True
    logger.info("tiktoken available — using precise token counting")

except ImportError:
    HAS_TIKTOKEN = False

    def count_tokens(text: str, model_name: str = "gpt-4") -> int:
        """回退 token 计数（近似值）。"""
        if not text:
            return 0
        # 中英文混写时此值可能误差 2-3 倍
        return len(text.split())

    logger.info("tiktoken not installed — falling back to approximate token counting")
