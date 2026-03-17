import sqlite3
import time
from .base_tool import DB_PATH


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at REAL
        )
    '''
    )
    conn.commit()
    conn.close()


def get_colab_url() -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM config WHERE key = "colab_url"')
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else ""
    except Exception as exc:
        print(f"DB Read Error: {exc}")
        return ""


def set_colab_url(url: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT OR REPLACE INTO config (key, value, updated_at)
        VALUES (?, ?, ?)
    ''',
        ("colab_url", url.strip(), time.time()),
    )
    conn.commit()
    conn.close()
