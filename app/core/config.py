from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    local_model_mode: str = "mock"
    default_local_model: str = "qwen2.5:3b"
    ollama_url: str = "http://localhost:11434"
    local_model_confidence_threshold: float = 0.6
    request_timeout_sec: int = 10

    default_cloud_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    allowed_models_path: str = "data/allowed_models.json"

    config_file_path: str = "data/gateway_config.yaml"

    governance_mode: str = "keyword"

    database_path: str = "data/gateway.db"
    audit_log_path: str = "logs/audit.jsonl"

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    log_file: str = "logs/gateway.log"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
