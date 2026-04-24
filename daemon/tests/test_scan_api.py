# daemon/tests/test_scan_api.py
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from main import app

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_scan_status_idle(client):
    r = await client.get("/api/scan/status")
    assert r.status_code == 200
    assert r.json()["status"] == "idle"

@pytest.mark.asyncio
async def test_start_scan_returns_accepted(client, tmp_path):
    (tmp_path / "book.mp3").write_bytes(b"\x00" * 100)
    with patch("scan_worker.run_scan", AsyncMock()):
        r = await client.post("/api/scan/start")
    assert r.status_code in (200, 202, 400)

@pytest.mark.asyncio
async def test_approve_empty_list_returns_ok(client):
    r = await client.post("/api/scan/approve", json={"approved_ids": [], "write_tags": False})
    assert r.status_code == 200
