import json
import aiosqlite
import os
from models import Config
from db import DB_PATH

async def load_config() -> Config:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT key, value FROM config")
        rows = await cursor.fetchall()
    data = {row["key"]: json.loads(row["value"]) for row in rows}
    return Config(**data)

async def save_config(cfg: Config):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        for key, value in cfg.model_dump().items():
            await db.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                (key, json.dumps(value))
            )
        await db.commit()
