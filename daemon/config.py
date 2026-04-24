import json
import aiosqlite
import os
from models import Config
from db import _db_path

async def load_config() -> Config:
    path = _db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT key, value FROM config")
        rows = await cursor.fetchall()
    data = {}
    for row in rows:
        try:
            data[row["key"]] = json.loads(row["value"])
        except json.JSONDecodeError as e:
            raise ValueError(f"Config key '{row['key']}' has invalid JSON: {e}") from e
    return Config(**data)

async def save_config(cfg: Config) -> None:
    path = _db_path()
    async with aiosqlite.connect(path) as db:
        try:
            for key, value in cfg.model_dump().items():
                await db.execute(
                    "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                    (key, json.dumps(value))
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
