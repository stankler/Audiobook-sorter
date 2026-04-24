import aiosqlite
import os
from typing import AsyncGenerator

def _db_path() -> str:
    return os.environ.get("DB_PATH", "/boot/config/plugins/audiobook-organizer/state.db")

async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        yield db

async def init_db():
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scan_state (
                id INTEGER PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'idle',
                data TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS google_books_cache (
                query_hash TEXT PRIMARY KEY,
                response TEXT NOT NULL,
                cached_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rollback_log (
                id INTEGER PRIMARY KEY,
                moves TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        await db.commit()
        await db.execute(
            "INSERT OR IGNORE INTO scan_state (id, status, data) VALUES (1, 'idle', '{}')"
        )
        await db.commit()
