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
async def test_start_scan_returns_accepted(client):
    from models import Config
    with patch("main.run_scan", AsyncMock()), \
         patch("main.load_config", AsyncMock(return_value=Config(
             source_path="/mnt/src", dest_path="/mnt/dest"
         ))):
        r = await client.post("/api/scan/start")
    assert r.status_code == 202

@pytest.mark.asyncio
async def test_approve_empty_list_returns_ok(client):
    r = await client.post("/api/scan/approve", json={"approved_ids": [], "write_tags": False})
    assert r.status_code == 200

@pytest.mark.asyncio
async def test_get_manual_review_empty(client):
    r = await client.get("/api/manual-review")
    assert r.status_code == 200
    assert r.json() == []

@pytest.mark.asyncio
async def test_move_to_unidentified_returns_404_when_no_such_id(client):
    r = await client.post("/api/manual-review/nonexistent/move-unidentified")
    assert r.status_code == 404
