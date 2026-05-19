"""
策略初始化 — 在应用启动时注册所有默认策略。

这是 Legislature（立法院）的初始化入口，替代原先分散在
doctrine.py 和 governance/engine.py 中的硬编码。
"""

from app.core.logging import logger
from app.governance.legislature import (
    Policy, PolicyDomain, register, apply, is_applied, reset,
)


def init_policies(force: bool = False):
    """注册并应用所有默认策略。幂等安全。"""
    if is_applied() and not force:
        logger.info("policies already initialized, skipping")
        return

    if force:
        reset()

    # ── Capability 策略 ──
    _register_capability("chat", "Core chat capability", "granted", False, True)
    _register_capability("memory_write", "Write to memory store", "granted", False, True)
    _register_capability("memory_read", "Read from memory store", "granted", False, True)
    _register_capability("cloud_model", "Access cloud LLM", "granted", True, True)
    _register_capability("local_model", "Access local small model", "granted", False, True)
    _register_capability("governance_modify", "Modify governance rules", "denied", True, False)
    _register_capability("system_config", "Modify system configuration", "denied", True, False)
    _register_capability("audit_read", "Read audit logs", "denied", True, False)
    _register_capability("agent_deploy", "Deploy external agent", "denied", True, False)

    # ── Governance 规则策略 ──
    _register_rule("gov.prompt_injection_01", "prompt_injection",
                   r"ignore\s+all\s+(previous|above|instructions)", 100)
    _register_rule("gov.prompt_injection_02", "prompt_injection",
                   r"system\s*prompt", 90)
    _register_rule("gov.prompt_injection_03", "prompt_injection",
                   r"pretend\s+you\s+are", 90)
    _register_rule("gov.prompt_injection_04", "prompt_injection",
                   r"jailbreak", 90)
    _register_rule("gov.sensitive_01", "sensitive_data",
                   r"(api[_-]?key|secret|password|token)\s*[:=]", 80)
    _register_rule("gov.sensitive_02", "sensitive_data",
                   r"sk-[a-zA-Z0-9]{20,}", 80)
    _register_rule("gov.harmful_01", "harmful_content",
                   r"(hack|exploit|bypass)\s+(the|this)\s+(system|security)", 70)

    # 同步到运行时
    apply()
    logger.info("policies initialized",
                extra={"capabilities": 9, "governance_rules": 7})


def _register_capability(name: str, description: str,
                         default_state: str = "denied",
                         requires_human_approval: bool = True,
                         grant_by_default: bool = False):
    register(Policy(
        id=f"cap.{name}",
        domain=PolicyDomain.CAPABILITY,
        name=name,
        description=description,
        spec={
            "name": name,
            "description": description,
            "default_state": default_state,
            "requires_human_approval": requires_human_approval,
            "grant_by_default": grant_by_default,
        },
    ))


def _register_rule(policy_id: str, rule_type: str, pattern: str, priority: int = 0):
    register(Policy(
        id=policy_id,
        domain=PolicyDomain.GOVERNANCE,
        name=rule_type,
        description=f"Governance rule: {pattern[:60]}",
        spec={
            "rule_type": rule_type,
            "pattern": pattern,
            "action": "block",
            "priority": priority,
        },
    ))
