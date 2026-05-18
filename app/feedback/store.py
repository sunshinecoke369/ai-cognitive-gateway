import json

from app.core.database import get_connection
from app.core.logging import logger


def save_feedback(request_id: str, rating: int, comment: str = "") -> dict:
    conn = get_connection()
    conn.execute(
        "INSERT INTO feedback (request_id, rating, comment) VALUES (?, ?, ?)",
        (request_id, rating, comment),
    )
    conn.commit()

    mem_rows = conn.execute(
        "SELECT id, importance FROM memory_entries WHERE request_id = ?",
        (request_id,),
    ).fetchall()

    if mem_rows:
        delta = 0.1 if rating > 0 else -0.1
        for row in mem_rows:
            new_importance = max(0.0, min(1.0, row["importance"] + delta))
            conn.execute(
                "UPDATE memory_entries SET importance = ? WHERE id = ?",
                (new_importance, row["id"]),
            )
        conn.commit()
        logger.info("feedback applied to memory weights", extra={
            "request_id": request_id,
            "rating": rating,
            "entries_updated": len(mem_rows),
            "delta": delta,
        })

    logger.info("feedback saved", extra={"request_id": request_id, "rating": rating})
    return {"status": "ok", "rating": rating, "memory_entries_updated": len(mem_rows)}


def get_feedback_for_request(request_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, rating, comment, created_at FROM feedback WHERE request_id = ? ORDER BY id DESC",
        (request_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_feedback_stats() -> dict:
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as total, "
        "COALESCE(SUM(CASE WHEN rating > 0 THEN 1 ELSE 0 END), 0) as positive, "
        "COALESCE(SUM(CASE WHEN rating < 0 THEN 1 ELSE 0 END), 0) as negative "
        "FROM feedback"
    ).fetchone()
    return dict(row)
