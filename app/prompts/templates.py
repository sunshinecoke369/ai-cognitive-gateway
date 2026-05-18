DEFAULT_CLOUD_PROMPT_TEMPLATE = """
## Task
Intent: {intent}
Instructions: Process the user input below and respond appropriately.

## Context
User Input: {user_input}
Memory Context: {memory_context}

## Constraints
- Safety rules: {safety_rules}
- Response style: {response_style}
- Be concise and accurate.

## Meta
- Origin model: {origin_model}
- Confidence: {confidence}
""".strip()


def build_cloud_prompt(
    user_input: str,
    intent: str = "general",
    memory_context: str = "",
    safety_rules: str = "Standard content policy",
    response_style: str = "concise",
    origin_model: str = "local_model_mock",
    confidence: float = 0.5,
) -> str:
    return DEFAULT_CLOUD_PROMPT_TEMPLATE.format(
        intent=intent,
        user_input=user_input,
        memory_context=memory_context or "None",
        safety_rules=safety_rules,
        response_style=response_style,
        origin_model=origin_model,
        confidence=confidence,
    )


def build_cloud_messages(
    user_input: str,
    intent: str = "general",
    memory_context: str = "",
    origin_model: str = "local_model_mock",
    confidence: float = 0.5,
) -> list[dict]:
    system_content = (
        f"你是一个智能助手。当前意图: {intent}。"
        f"参考上下文: {memory_context or '无'}。"
        f"请简洁专业地回答用户。"
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_input},
    ]
