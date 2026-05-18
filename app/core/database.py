import sqlite3
import os

from app.core.config import settings

_connection: sqlite3.Connection | None = None


def _db_path() -> str:
    os.makedirs(os.path.dirname(settings.database_path), exist_ok=True)
    return settings.database_path


def get_connection() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(_db_path(), check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL")
        _init_tables(_connection)
    return _connection


def close_connection():
    global _connection
    if _connection:
        _connection.close()
        _connection = None


def _init_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS requests (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            user_input_raw TEXT NOT NULL,
            local_model_output TEXT,
            governance_result TEXT,
            routing_decision TEXT,
            cloud_model_response TEXT,
            final_response TEXT,
            latency_ms INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS memory_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            layer TEXT NOT NULL DEFAULT 'user',
            content TEXT NOT NULL,
            importance REAL DEFAULT 0.0,
            tags TEXT DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (request_id) REFERENCES requests(id)
        );

        CREATE TABLE IF NOT EXISTS governance_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_type TEXT NOT NULL,
            pattern TEXT NOT NULL,
            action TEXT NOT NULL DEFAULT 'block',
            priority INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS token_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (request_id) REFERENCES requests(id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'system',
            detail_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp);
        CREATE INDEX IF NOT EXISTS idx_memory_tags ON memory_entries(tags);
        CREATE INDEX IF NOT EXISTS idx_memory_layer ON memory_entries(layer);
        CREATE INDEX IF NOT EXISTS idx_token_usage_request ON token_usage(request_id);
        CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log(event_type);
        CREATE INDEX IF NOT EXISTS idx_audit_request_id ON audit_log(request_id);
        CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at);

        CREATE TABLE IF NOT EXISTS response_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cache_key TEXT NOT NULL UNIQUE,
            response_json TEXT NOT NULL,
            model_name TEXT NOT NULL,
            ttl_seconds INTEGER DEFAULT 3600,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_cache_key ON response_cache(cache_key);

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            rating INTEGER NOT NULL DEFAULT 0,
            comment TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (request_id) REFERENCES requests(id)
        );

        CREATE INDEX IF NOT EXISTS idx_feedback_request ON feedback(request_id);
        CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at);
    """)
    conn.commit()
