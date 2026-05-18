from app.core.logging import logger
from app.core.doctrine import is_override_active


def adjudicate(police_result: dict, context: dict | None = None) -> dict:
    if is_override_active():
        return {
            "verdict": "override",
            "allowed": True,
            "risk_assessment": "human_override",
            "reason": "Human override is active. All requests pass.",
            "mitigation": None,
        }

    if not police_result.get("allowed", True):
        return {
            "verdict": "blocked",
            "allowed": False,
            "risk_assessment": police_result.get("risk_level", "high"),
            "reason": f"Violations detected: {police_result.get('violations', [])}",
            "mitigation": "Request blocked. No further action.",
        }

    risk_level = police_result.get("risk_level", "low")

    if risk_level == "high":
        return {
            "verdict": "blocked",
            "allowed": False,
            "risk_assessment": "high",
            "reason": "High risk assessment from Police layer.",
            "mitigation": "Manual review required.",
        }

    if risk_level == "medium":
        return {
            "verdict": "conditional_allow",
            "allowed": True,
            "risk_assessment": "medium",
            "reason": "Medium risk, allowing with monitoring.",
            "mitigation": "Log and monitor this request.",
        }

    return {
        "verdict": "allow",
        "allowed": True,
        "risk_assessment": "low",
        "reason": "No violations or risks detected.",
        "mitigation": None,
    }
