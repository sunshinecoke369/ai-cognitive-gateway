"""
向后兼容导入层。

engine 功能已合并到 app/providers/registry.py。
此模块保留导入别名，确保现有 import 不中断。
将在下个主要版本移除。
"""
from app.providers.registry import (  # noqa: F401
    list_engine_models,
    SUPPORTED_ENGINES,
    ENGINE_REGISTRY,
)
