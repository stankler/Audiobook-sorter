import pytest
import os
os.environ["DB_PATH"] = "/tmp/test-ao-config.db"

from httpx import AsyncClient, ASGITransport
from main import app

@pytest.fixture(autouse=True)
async def reset_db():
    db_path = os.environ["DB_PATH"]
    if os.path.exists(db_path):
        os.remove(db_path)
    from db import init_db
    await init_db()
    yield

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_get_config_defaults(client):
    r = await client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert data["confidence_threshold"] == 0.85
    assert data["stt_engine"] == "none"

@pytest.mark.asyncio
async def test_save_config(client):
    payload = {
        "source_path": "/mnt/user/audiobooks-raw",
        "dest_path": "/mnt/user/audiobooks",
        "google_books_api_key": "test-key",
        "stt_engine": "local_whisper",
        "whisper_model": "small",
        "stt_api_key": "",
        "confidence_threshold": 0.80,
    }
    r = await client.post("/api/config", json=payload)
    assert r.status_code == 200
    r2 = await client.get("/api/config")
    assert r2.json()["source_path"] == "/mnt/user/audiobooks-raw"
    assert r2.json()["confidence_threshold"] == 0.80
