import hashlib
import json
import asyncio
import httpx
from datetime import datetime, timezone
from db import _db_path
import aiosqlite

BOOKS_API_URL = "https://www.googleapis.com/books/v1/volumes"
_rate_limit = asyncio.Semaphore(1)
_last_request_time = 0.0

async def query_google_books(
    title: str, author: str | None, api_key: str
) -> list[dict]:
    if not api_key or not title:
        return []

    query = f'intitle:"{title}"'
    if author:
        query += f' inauthor:"{author}"'
    cache_key = hashlib.md5(query.encode()).hexdigest()

    cached = await _get_cache(cache_key)
    if cached is not None:
        return cached

    global _last_request_time
    async with _rate_limit:
        import time
        elapsed = time.time() - _last_request_time
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    BOOKS_API_URL,
                    params={"q": query, "key": api_key, "maxResults": 5, "printType": "books"},
                )
                r.raise_for_status()
                data = r.json()
                items = data.get("items", [])
        except Exception:
            return []
        finally:
            _last_request_time = time.time()

    await _set_cache(cache_key, items)
    return items

async def _get_cache(key: str) -> list[dict] | None:
    path = _db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT response FROM google_books_cache WHERE query_hash = ?", (key,)
        )
        row = await cursor.fetchone()
        if row:
            return json.loads(row["response"])
    return None

async def _set_cache(key: str, items: list[dict]):
    path = _db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO google_books_cache (query_hash, response, cached_at) VALUES (?, ?, ?)",
            (key, json.dumps(items), datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
