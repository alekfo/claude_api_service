import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "data/logs.db")


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS request_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                model TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                total_tokens INTEGER,
                elapsed_seconds REAL,
                stop_reason TEXT,
                prompt_preview TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def log_request(model: str, input_tokens: int, output_tokens: int,
                elapsed: float, stop_reason: str, prompt_preview: str):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO request_log
               (model, input_tokens, output_tokens, total_tokens, elapsed_seconds, stop_reason, prompt_preview)
               VALUES (?,?,?,?,?,?,?)""",
            (model, input_tokens, output_tokens, input_tokens + output_tokens,
             elapsed, stop_reason, prompt_preview[:100]),
        )
        conn.commit()
    finally:
        conn.close()


def get_today_stats() -> dict:
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) as requests,
                COALESCE(SUM(input_tokens), 0)  as input_tokens,
                COALESCE(SUM(output_tokens), 0) as output_tokens,
                COALESCE(SUM(total_tokens), 0)  as total_tokens,
                COALESCE(AVG(elapsed_seconds), 0) as avg_elapsed
            FROM request_log
            WHERE DATE(created_at) = DATE('now')
        """).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_month_stats() -> dict:
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) as requests,
                COALESCE(SUM(input_tokens), 0)  as input_tokens,
                COALESCE(SUM(output_tokens), 0) as output_tokens,
                COALESCE(SUM(total_tokens), 0)  as total_tokens,
                COALESCE(AVG(elapsed_seconds), 0) as avg_elapsed
            FROM request_log
            WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_recent_requests(n: int = 10) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT created_at, model, input_tokens, output_tokens, total_tokens,
                   elapsed_seconds, stop_reason, prompt_preview
            FROM request_log
            ORDER BY created_at DESC
            LIMIT ?
        """, (n,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_today_total_tokens() -> int:
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT COALESCE(SUM(total_tokens), 0) as total
            FROM request_log
            WHERE DATE(created_at) = DATE('now')
        """).fetchone()
        return row["total"]
    finally:
        conn.close()


def get_month_total_tokens() -> int:
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT COALESCE(SUM(total_tokens), 0) as total
            FROM request_log
            WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """).fetchone()
        return row["total"]
    finally:
        conn.close()