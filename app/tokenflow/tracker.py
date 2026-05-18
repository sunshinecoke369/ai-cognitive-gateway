import sqlite3

from app.core.database import get_connection
from app.core.logging import logger


def record_tokens(request_id: str, stage: str, tokens_in: int = 0, tokens_out: int = 0):
    conn = get_connection()
    conn.execute(
        "INSERT INTO token_usage (request_id, stage, tokens_in, tokens_out) VALUES (?, ?, ?, ?)",
        (request_id, stage, tokens_in, tokens_out),
    )
    conn.commit()
    logger.debug(
        "token usage recorded",
        extra={"request_id": request_id, "stage": stage, "tokens_in": tokens_in, "tokens_out": tokens_out},
    )


def get_usage_for_request(request_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, stage, tokens_in, tokens_out, created_at FROM token_usage WHERE request_id = ? ORDER BY id",
        (request_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_total_usage() -> dict:
    conn = get_connection()
    row = conn.execute(
        "SELECT COALESCE(SUM(tokens_in), 0) as total_in, COALESCE(SUM(tokens_out), 0) as total_out, COUNT(*) as entries FROM token_usage"
    ).fetchone()
    return dict(row)
