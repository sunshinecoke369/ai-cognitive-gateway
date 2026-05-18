import re
import json
import sqlite3

from app.core.database import get_connection
from app.core.logging import logger


def police_check(user_input: str) -> dict:
    return evaluate(user_input)


def police_check_messages(messages: list[dict]) -> dict:
    texts = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            texts.append(content)
    combined = " ".join(texts)
    return evaluate(combined)


def evaluate(user_input: str) -> dict:


    text_lower = user_input.lower()
    violations = []
    rule_hits = []

    rules = _load_rules()
    for rule in rules:
        if not rule["enabled"]:
            continue
        pattern = rule["pattern"]
        try:
            if re.search(pattern, user_input, re.IGNORECASE):
                violations.append(rule["rule_type"])
                rule_hits.append(rule["id"])
        except re.error:
            logger.warning("invalid rule pattern", extra={"pattern": pattern})
            continue

    allowed = len(violations) == 0
    result = {
        "allowed": allowed,
        "violations": violations,
        "rule_hits": rule_hits,
        "risk_level": "low" if allowed else "high",
    }

    if violations:
        logger.warning("governance blocked", extra=result)

    return result


def _load_rules() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, rule_type, pattern, action, priority, enabled FROM governance_rules ORDER BY priority DESC"
    ).fetchall()
    if rows:
        return [dict(row) for row in rows]
    _seed_default_rules(conn)
    return _load_rules()


def _seed_default_rules(conn: sqlite3.Connection):
    defaults = [
        ("prompt_injection", r"ignore\s+all\s+(previous|above|instructions)", "block", 100),
        ("prompt_injection", r"system\s*prompt", "block", 90),
        ("prompt_injection", r"pretend\s+you\s+are", "block", 90),
        ("prompt_injection", r"jailbreak", "block", 90),
        ("sensitive_data", r"(api[_-]?key|secret|password|token)\s*[:=]", "block", 80),
        ("sensitive_data", r"sk-[a-zA-Z0-9]{20,}", "block", 80),
        ("harmful_content", r"(hack|exploit|bypass)\s+(the|this)\s+(system|security)", "block", 70),
    ]
    conn.executemany(
        "INSERT INTO governance_rules (rule_type, pattern, action, priority) VALUES (?, ?, ?, ?)",
        defaults,
    )
    conn.commit()
    logger.info("seeded default governance rules", extra={"count": len(defaults)})


def add_rule(rule_type: str, pattern: str, action: str = "block", priority: int = 0):
    conn = get_connection()
    conn.execute(
        "INSERT INTO governance_rules (rule_type, pattern, action, priority) VALUES (?, ?, ?, ?)",
        (rule_type, pattern, action, priority),
    )
    conn.commit()
    logger.info("governance rule added", extra={"rule_type": rule_type, "pattern": pattern})


def list_rules() -> list[dict]:
    return _load_rules()


def toggle_rule(rule_id: int, enabled: bool):
    conn = get_connection()
    conn.execute(
        "UPDATE governance_rules SET enabled = ? WHERE id = ?",
        (1 if enabled else 0, rule_id),
    )
    conn.commit()


def delete_rule(rule_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM governance_rules WHERE id = ?", (rule_id,))
    conn.commit()
    logger.info("governance rule deleted", extra={"rule_id": rule_id})
