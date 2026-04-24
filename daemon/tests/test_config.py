import pytest
from httpx import AsyncClient, ASGITransport
from main import app

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

@pytest.mark.asyncio
async def test_config_rejects_invalid_confidence(client):
    r = await client.post("/api/config", json={"confidence_threshold": 0.50})
    assert r.status_code == 422
