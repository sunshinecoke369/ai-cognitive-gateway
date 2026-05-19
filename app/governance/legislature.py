"""
Legislature — 立法院

统一的策略定义和管理入口，替代分散在代码中的硬编码策略。

分层职责：
  Police（警察）   → 实时检测，规则执行
  Judge（法官）    → 风险评估，行为裁定
  Legislature     → 规则定义，策略管理（本模块）

本模块在应用启动时注册默认策略，并将其同步到运行时。
所有策略变更应通过此处，而非直接改代码。
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.core.logging import logger


class PolicyDomain(str, Enum):
    """策略域，按功能领域划分。"""
    GOVERNANCE = "governance"       # Police 治理规则
    CAPABILITY = "capability"       # Capability 默认状态
    ROUTING = "routing"             # 调度策略
    MEMORY = "memory"               # 记忆生命周期


@dataclass
class Policy:
    """一条策略的定义。"""
    id: str                          # 唯一标识，如 'gov.prompt_injection'
    domain: PolicyDomain             # 所属域
    name: str                        # 人类可读名称
    spec: dict                       # 策略内容（规则/Capability/配置）
    description: str = ""
    enabled: bool = True
    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "domain": self.domain.value,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "version": self.version,
            "spec": self.spec,
            "created_at": self.created_at,
        }


# ── 注册中心 ──

_registry: dict[str, Policy] = {}
_applied: bool = False


def register(policy: Policy):
    """注册一条策略。"""
    _registry[policy.id] = policy
    logger.info("policy registered", extra={"id": policy.id, "domain": policy.domain.value, "policy_name": policy.name})


def get_policy(policy_id: str) -> Policy | None:
    return _registry.get(policy_id)


def get_policies(domain: PolicyDomain | None = None) -> list[Policy]:
    if domain:
        return [p for p in _registry.values() if p.domain == domain]
    return list(_registry.values())


def toggle(policy_id: str, enabled: bool) -> bool:
    """启用/停用一条策略。"""
    if policy_id not in _registry:
        return False
    _registry[policy_id].enabled = enabled
    logger.info("policy toggled", extra={"id": policy_id, "enabled": enabled})
    return True


def apply():
    """将注册的策略同步到运行时（Police 规则表 + Capability 状态）。"""
    global _applied
    if _applied:
        logger.warning("policies already applied, skipping")
        return

    from app.core.database import get_connection
    from app.core.doctrine import register_capability, grant_capability, CapabilityState

    for policy in _registry.values():
        if not policy.enabled:
            continue

        if policy.domain == PolicyDomain.CAPABILITY:
            spec = policy.spec
            register_capability(
                name=spec.get("name", policy.id),
                description=spec.get("description", ""),
                default_state=CapabilityState(spec.get("default_state", "denied")),
                requires_human_approval=spec.get("requires_human_approval", True),
            )
            if spec.get("grant_by_default", False):
                grant_capability(spec.get("name", policy.id))

        elif policy.domain == PolicyDomain.GOVERNANCE:
            conn = get_connection()
            # 仅在规则表为空时插入，防重启重复
            existing = conn.execute("SELECT COUNT(*) as cnt FROM governance_rules").fetchone()
            if existing and existing["cnt"] > 0:
                logger.debug("governance rules already exist, skipping seed", extra={"count": existing["cnt"]})
                continue
            spec = policy.spec
            rule_type = spec.get("rule_type", "custom")
            pattern = spec.get("pattern", "")
            action = spec.get("action", "block")
            priority = spec.get("priority", 0)
            conn.execute(
                "INSERT INTO governance_rules (rule_type, pattern, action, priority) VALUES (?, ?, ?, ?)",
                (rule_type, pattern, action, priority),
            )
            conn.commit()

    _applied = True
    logger.info("policies applied", extra={"total": len(_registry), "domains": list(set(p.domain.value for p in _registry.values()))})


def is_applied() -> bool:
    return _applied


def reset():
    """重置注册中心（用于测试）。"""
    _registry.clear()
    global _applied
    _applied = False


def list_all() -> list[dict]:
    return [p.to_dict() for p in _registry.values()]


def export() -> dict:
    """导出所有策略为可序列化 dict。"""
    return {
        "version": 2,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "policies": [p.to_dict() for p in _registry.values()],
    }
