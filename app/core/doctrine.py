from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.core.logging import logger

"""
WARNING: 全局状态（Capability / Override / Shutdown）是纯内存变量。
         不跨 uvicorn worker 共享。如果配置 workers > 1，不同 worker
         看到的 Capability 状态、Override 状态、Shutdown 状态将不一致。

约束：
- systemd 服务的 ExecStart 必须使用单 worker（默认）
- 如需多 worker/多进程部署，必须将状态迁移到 SQLite 或 Redis
"""


class CapabilityState(Enum):
    GRANTED = "granted"
    DENIED = "denied"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    THROTTLED = "throttled"


@dataclass
class Capability:
    name: str
    description: str
    default_state: CapabilityState = CapabilityState.DENIED
    requires_human_approval: bool = True


_CAPABILITY_REGISTRY: dict[str, Capability] = {}

_CAPABILITY_STATES: dict[str, CapabilityState] = {}

_HUMAN_OVERRIDE_ACTIVE: bool = False
_HUMAN_OVERRIDE_REASON: str = ""


def register_capability(
    name: str,
    description: str,
    default_state: CapabilityState = CapabilityState.DENIED,
    requires_human_approval: bool = True,
):
    if name in _CAPABILITY_REGISTRY:
        logger.debug("capability already registered, skipping", extra={"capability": name})
        return
    cap = Capability(
        name=name,
        description=description,
        default_state=default_state,
        requires_human_approval=requires_human_approval,
    )
    _CAPABILITY_REGISTRY[name] = cap
    _CAPABILITY_STATES[name] = default_state
    logger.info("capability registered", extra={"capability": name, "default_state": default_state.value})


def grant_capability(name: str):
    if name not in _CAPABILITY_REGISTRY:
        raise ValueError(f"unknown capability: {name}")
    _CAPABILITY_STATES[name] = CapabilityState.GRANTED
    logger.info("capability granted", extra={"capability": name})


def deny_capability(name: str):
    if name not in _CAPABILITY_REGISTRY:
        raise ValueError(f"unknown capability: {name}")
    _CAPABILITY_STATES[name] = CapabilityState.DENIED
    logger.info("capability denied", extra={"capability": name})


def suspend_capability(name: str):
    if name not in _CAPABILITY_REGISTRY:
        raise ValueError(f"unknown capability: {name}")
    _CAPABILITY_STATES[name] = CapabilityState.SUSPENDED
    logger.info("capability suspended", extra={"capability": name})


def revoke_capability(name: str):
    if name not in _CAPABILITY_REGISTRY:
        raise ValueError(f"unknown capability: {name}")
    _CAPABILITY_STATES[name] = CapabilityState.REVOKED
    logger.info("capability revoked", extra={"capability": name})


def check_capability(name: str) -> bool:
    if name not in _CAPABILITY_REGISTRY:
        return False
    return _CAPABILITY_STATES.get(name) == CapabilityState.GRANTED


def list_capabilities() -> list[dict]:
    result = []
    for name, cap in _CAPABILITY_REGISTRY.items():
        state = _CAPABILITY_STATES.get(name, cap.default_state)
        result.append({
            "name": cap.name,
            "description": cap.description,
            "state": state.value,
            "requires_human_approval": cap.requires_human_approval,
        })
    return result


def activate_override(reason: str = ""):
    global _HUMAN_OVERRIDE_ACTIVE, _HUMAN_OVERRIDE_REASON
    _HUMAN_OVERRIDE_ACTIVE = True
    _HUMAN_OVERRIDE_REASON = reason
    logger.warning("human override activated", extra={"reason": reason})


def deactivate_override():
    global _HUMAN_OVERRIDE_ACTIVE, _HUMAN_OVERRIDE_REASON
    _HUMAN_OVERRIDE_ACTIVE = False
    _HUMAN_OVERRIDE_REASON = ""
    logger.info("human override deactivated")


def is_override_active() -> bool:
    return _HUMAN_OVERRIDE_ACTIVE


def get_override_status() -> dict:
    return {
        "active": _HUMAN_OVERRIDE_ACTIVE,
        "reason": _HUMAN_OVERRIDE_REASON,
    }


_SHUTDOWN_REQUESTED: bool = False


def request_shutdown():
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = True
    logger.warning("system shutdown requested by human operator")


def is_shutdown_requested() -> bool:
    return _SHUTDOWN_REQUESTED


def reset_shutdown():
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = False


def _init_default_capabilities():
    register_capability("chat", "Core chat capability", CapabilityState.GRANTED, False)
    register_capability("memory_write", "Write to memory store", CapabilityState.GRANTED, False)
    register_capability("memory_read", "Read from memory store", CapabilityState.GRANTED, False)
    register_capability("cloud_model", "Access cloud LLM", CapabilityState.GRANTED, True)
    register_capability("local_model", "Access local small model", CapabilityState.GRANTED, False)
    register_capability("governance_modify", "Modify governance rules", CapabilityState.DENIED, True)
    register_capability("system_config", "Modify system configuration", CapabilityState.DENIED, True)
    register_capability("audit_read", "Read audit logs", CapabilityState.DENIED, True)
    register_capability("agent_deploy", "Deploy external agent", CapabilityState.DENIED, True)
