import aiosqlite
import os

DB_PATH = os.environ.get("DB_PATH", "/boot/config/plugins/audiobook-organizer/state.db")

async def get_db() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row

    try:
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
        # Ensure scan_state has one row
        await db.execute(
            "INSERT OR IGNORE INTO scan_state (id, status, data) VALUES (1, 'idle', '{}')"
        )
        await db.commit()
    finally:
        await db.close()
